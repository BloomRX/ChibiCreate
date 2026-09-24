"""Verificacao objetiva de LOCALIDADE de um inpaint.

A pergunta desta fase e: o inpaint mexeu SO onde a mascara permitia?

Isto NAO julga qualidade artistica. Mede apenas quanto da imagem fora da
mascara permaneceu inalterada. Um resultado pode ter localidade perfeita e
ainda assim ser feio — a avaliacao estetica continua humana.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# Diferenca por canal, em niveis 0-255, abaixo da qual consideramos um pixel
# inalterado. Nao e zero porque o VAE do SDXL e lossy: ele reencoda a imagem
# inteira, entao ate a area preservada volta com ruido de quantizacao de
# alguns niveis. Exigir identidade exata reprovaria todo inpaint, inclusive
# um perfeito.
TOLERANCIA_VAE = 2


class InpaintCheckError(RuntimeError):
    pass


def _rgb(caminho_ou_img) -> np.ndarray:
    img = (caminho_ou_img if isinstance(caminho_ou_img, Image.Image)
           else Image.open(caminho_ou_img))
    return np.asarray(img.convert("RGB"), dtype=np.int16)


def _mascara_bool(caminho_ou_img, shape) -> np.ndarray:
    img = (caminho_ou_img if isinstance(caminho_ou_img, Image.Image)
           else Image.open(caminho_ou_img))
    m = np.asarray(img.convert("L"))
    if m.shape != shape:
        raise InpaintCheckError(
            f"mascara {m.shape} nao bate com a imagem {shape}. "
            "Redimensionar a mascara aqui esconderia um erro de preparacao.")
    return m > 127


def comparar(source, output, mask, *, tolerancia: int = TOLERANCIA_VAE) -> dict:
    """Metricas de localidade entre a source e o output do inpaint."""
    s, o = _rgb(source), _rgb(output)
    if s.shape != o.shape:
        raise InpaintCheckError(
            f"source {s.shape} e output {o.shape} tem tamanhos diferentes; "
            "comparacao pixel a pixel seria sem sentido.")

    dentro = _mascara_bool(mask, s.shape[:2])
    fora = ~dentro
    total = int(s.shape[0] * s.shape[1])

    diff = np.abs(s - o).max(axis=2)          # maior desvio entre os canais
    mudou = diff > tolerancia

    n_fora = int(fora.sum())
    n_dentro = int(dentro.sum())
    mudou_fora = int((mudou & fora).sum())

    return {
        "mask_area_pixels": n_dentro,
        "mask_area_percentage": round(100.0 * n_dentro / total, 4),
        "outside_mask_pixels": n_fora,
        "outside_mask_changed_pixels": mudou_fora,
        "outside_mask_changed_percentage": (
            round(100.0 * mudou_fora / n_fora, 4) if n_fora else 0.0),
        "outside_mask_preserved_percentage": (
            round(100.0 * (n_fora - mudou_fora) / n_fora, 4) if n_fora else 0.0),
        "outside_mask_mean_abs_diff": (
            round(float(diff[fora].mean()), 4) if n_fora else 0.0),
        "outside_mask_max_abs_diff": (
            int(diff[fora].max()) if n_fora else 0),
        "inside_mask_mean_abs_diff": (
            round(float(diff[dentro].mean()), 4) if n_dentro else 0.0),
        "tolerance_used": tolerancia,
        "tolerance_note": (
            "O VAE do SDXL e lossy e reencoda a imagem inteira, entao a area "
            "preservada volta com ruido de alguns niveis. Diferenca <= "
            f"{tolerancia} conta como inalterada."),
        "interpretation_note": (
            "Estas metricas medem LOCALIDADE, nao qualidade. Preservacao alta "
            "significa que o inpaint respeitou a mascara — nao que o "
            "resultado esteja bonito. Avaliacao estetica e humana."),
    }


def diferenca_visivel(source, output, *, ganho: int = 8) -> Image.Image:
    """Mapa de diferenca amplificado, para inspecao humana."""
    d = np.abs(_rgb(source) - _rgb(output)).max(axis=2)
    return Image.fromarray(np.clip(d * ganho, 0, 255).astype(np.uint8), "L")


def overlap_protegido(mask, protected) -> int:
    """Pixels da mascara que caem em regiao protegida. DEVE ser 0.

    Espelha `mask_engine.mask_protected_overlap_pixels`, mas opera sobre
    imagens carregadas do disco (a mascara de inpaint e desenhada a mao no
    espaco da imagem-alvo, nao derivada da arte-fonte).
    """
    m = _mascara_bool(mask, np.asarray(
        (mask if isinstance(mask, Image.Image) else Image.open(mask))
        .convert("L")).shape)
    p = _mascara_bool(protected, m.shape)
    return int(np.count_nonzero(m & p))


def overlay(source, mask, *, cor=(255, 0, 0), alpha: float = 0.45) -> Image.Image:
    """Source com a regiao editavel destacada, para revisao humana."""
    base = (source if isinstance(source, Image.Image)
            else Image.open(source)).convert("RGB")
    m = np.asarray((mask if isinstance(mask, Image.Image)
                    else Image.open(mask)).convert("L").resize(base.size)) > 127
    arr = np.asarray(base).astype(float)
    tint = np.zeros_like(arr)
    tint[..., 0], tint[..., 1], tint[..., 2] = cor
    arr[m] = arr[m] * (1 - alpha) + tint[m] * alpha
    return Image.fromarray(arr.astype(np.uint8), "RGB")

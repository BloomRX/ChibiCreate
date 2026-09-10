"""FASE B — SDXL inpaint MASCARADO (segundo estagio, condicional).

So deve rodar se a FASE A (restauracao seletiva nao-generativa) nao produzir
resultado suficiente. A avaliacao de "suficiente" e **humana**.

Regra que define esta camada:

    o SDXL NUNCA recebe a imagem inteira para redesenhar a personagem.

Ele edita **apenas dentro da mascara transformada**, e o resultado e
recomposto sobre a Run 003 original de forma que todo pixel fora da mascara
volte a ser byte a byte o original. Duas defesas independentes:

  1. `mask_image` restringe o que o modelo pode alterar;
  2. `recompose()` reescreve os bytes originais fora da mascara, mesmo que o
     decoder do VAE tenha tocado neles (e ele toca — o VAE e lossy e altera
     a imagem inteira, ainda que sutilmente).

A defesa 2 nao e redundancia decorativa: sem ela,
`outside_mask_pixel_difference` seria diferente de zero por causa do
round-trip do autoencoder, e a Run 003 estaria silenciosamente degradada.

Este modulo NAO baixa modelo. Downloads sao explicitos, no notebook.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

# Checkpoint verificado em fonte primaria (huggingface.co, 2026-09-09).
# Registrado tambem em config/models.lock.yaml.
MODEL = {
    "key": "sdxl_inpainting_01",
    "repo": "diffusers/stable-diffusion-xl-1.0-inpainting-0.1",
    "revision": "115134f363124c53c7d878647567d04daf26e41e",
    "license": "CreativeML Open RAIL++-M",
    "license_url": ("https://huggingface.co/stabilityai/"
                    "stable-diffusion-xl-base-1.0/blob/main/LICENSE.md"),
    "base_model": "stabilityai/stable-diffusion-xl-base-1.0",
    "params": "3B",
    "native_resolution": 1024,
    "vram_fp16_gb": 8.0,
    "variant": "fp16",
    "commercial_status": "permitido_com_clausulas_de_uso_restrito",
    "commercial_note": (
        "OpenRAIL++-M permite uso comercial mas impoe restricoes de uso "
        "(anexo de usos proibidos) que precisam ser propagadas. "
        "[HUMAN REVIEW REQUIRED] antes de qualquer distribuicao."),
}

# Parametros default. `strength` abaixo de 1.0 e exigencia do model card: em
# 1.0 o inpaint parte de latente totalmente mascarado e a qualidade cai.
DEFAULTS = {
    "guidance_scale": 8.0,
    "num_inference_steps": 20,      # o card recomenda 15-30
    "strength": 0.85,
    "seed": 42,
}


class InpaintError(RuntimeError):
    pass


@dataclass
class InpaintPlan:
    """O que sera enviado ao modelo — inspecionavel ANTES de gastar GPU."""
    prompt: str
    negative_prompt: str
    mask_pixels: int
    mask_pct: float
    regions: list[str]
    params: dict
    protected_overlap: int
    resolution: tuple[int, int]

    def as_dict(self) -> dict:
        return {"prompt": self.prompt, "negative_prompt": self.negative_prompt,
                "mask_pixels": self.mask_pixels,
                "mask_pct": round(self.mask_pct, 3),
                "regions": list(self.regions), "params": dict(self.params),
                "protected_overlap": self.protected_overlap,
                "resolution": list(self.resolution),
                "model": dict(MODEL)}


def build_edit_mask(target_masks: dict[str, np.ndarray],
                    regions: list[str],
                    protected: np.ndarray | None = None,
                    dilate: int = 0) -> np.ndarray:
    """Uniao das regioes autorizadas, menos tudo que e protegido.

    A subtracao do protegido e a ULTIMA operacao de proposito: qualquer
    dilatacao acontece antes, para que nem a borda dilatada possa invadir
    rosto, cabelo ou chifres.
    """
    if not regions:
        raise InpaintError("nenhuma regiao selecionada para inpaint")
    ref = next(iter(target_masks.values()))
    m = np.zeros(ref.shape, bool)
    for nome in regions:
        if nome not in target_masks:
            raise InpaintError(f"regiao desconhecida: {nome}")
        m |= target_masks[nome]
    if dilate > 0:
        # `binary_dilation` sai na skimage 0.28 e o Colab roda 0.25.x, onde
        # `dilation` ja existe. Usar `dilation` cobre as duas versoes.
        from skimage.morphology import dilation, disk
        m = dilation(m, disk(dilate)).astype(bool)
    if protected is not None:
        m = m & ~protected
    return m


def plan_inpaint(target_img: Image.Image,
                 edit_mask: np.ndarray,
                 regions: list[str],
                 prompt: str,
                 negative_prompt: str = "",
                 protected: np.ndarray | None = None,
                 params: dict | None = None) -> InpaintPlan:
    p = dict(DEFAULTS)
    p.update(params or {})
    if not 0.0 < p["strength"] < 1.0:
        raise InpaintError(
            "strength precisa ficar entre 0 e 1 (exclusivo). O model card "
            "avisa que 1.0 degrada a imagem.")
    overlap = (int((edit_mask & protected).sum())
               if protected is not None else 0)
    if overlap:
        raise InpaintError(
            f"mascara invade {overlap} px de regiao protegida — PARE")
    total = edit_mask.size
    return InpaintPlan(
        prompt=prompt, negative_prompt=negative_prompt,
        mask_pixels=int(edit_mask.sum()),
        mask_pct=100 * float(edit_mask.sum()) / total,
        regions=list(regions), params=p, protected_overlap=overlap,
        resolution=target_img.size)


def mask_to_image(mask: np.ndarray) -> Image.Image:
    """Mascara booleana -> L. Branco = editar, preto = preservar."""
    return Image.fromarray((mask.astype(np.uint8) * 255), "L")


def recompose(original: Image.Image, generated: Image.Image,
              edit_mask: np.ndarray) -> Image.Image:
    """Devolve os bytes ORIGINAIS fora da mascara.

    O VAE do SDXL e lossy: mesmo com `mask_image`, a imagem retornada difere
    do original em toda a area, por reconstrucao. Sem este passo a Run 003
    sairia degradada e `outside_mask_pixel_difference` nao seria zero.
    """
    a = np.array(original.convert("RGBA"))
    b = np.array(generated.convert("RGBA"))
    if a.shape != b.shape:
        b = np.array(generated.convert("RGBA").resize(
            original.size, Image.LANCZOS))
    out = a.copy()
    out[edit_mask] = b[edit_mask]
    return Image.fromarray(out, "RGBA")


@dataclass
class InpaintResult:
    image: Image.Image
    plan: InpaintPlan
    raw: Image.Image | None = None
    metrics: dict = field(default_factory=dict)


def run_inpaint(pipe, target_img: Image.Image, edit_mask: np.ndarray,
                plan: InpaintPlan, generator=None) -> InpaintResult:
    """Executa o pipeline `StableDiffusionXLInpaintPipeline` ja carregado.

    O pipeline e injetado, nao construido aqui: carregar pesos e decisao
    explicita do notebook, nunca efeito colateral de importar um modulo.
    """
    if pipe is None:
        raise InpaintError("pipeline nao carregado")

    w, h = target_img.size
    # SDXL foi treinado em 1024; multiplos de 8 sao exigencia do VAE.
    tw, th = (max(512, (w // 8) * 8), max(512, (h // 8) * 8))

    img_in = target_img.convert("RGB").resize((tw, th), Image.LANCZOS)
    mask_in = mask_to_image(edit_mask).resize((tw, th), Image.NEAREST)

    saida = pipe(
        prompt=plan.prompt,
        negative_prompt=plan.negative_prompt or None,
        image=img_in,
        mask_image=mask_in,
        guidance_scale=plan.params["guidance_scale"],
        num_inference_steps=int(plan.params["num_inference_steps"]),
        strength=plan.params["strength"],
        generator=generator,
    ).images[0]

    if saida.size != target_img.size:
        saida = saida.resize(target_img.size, Image.LANCZOS)

    final = recompose(target_img, saida, edit_mask)
    return InpaintResult(image=final, plan=plan, raw=saida)

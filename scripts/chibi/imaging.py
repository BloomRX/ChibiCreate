"""Operacoes de imagem do FLOW 01.

Responsabilidade: normalizar, isolar sujeito e recortar regioes.
NAO gera arte nova. NAO inventa conteudo. Apenas transforma o que existe.

Todas as operacoes sao deterministicas (sem IA, sem aleatoriedade), o que
torna o FLOW 01 completamente reprodutivel e executavel na maquina local.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# Pillow >= 10 moveu as constantes de resample para Image.Resampling.
LANCZOS = Image.Resampling.LANCZOS
NEAREST = Image.Resampling.NEAREST

#: Limiar de alpha acima do qual um pixel conta como "sujeito".
ALPHA_THRESHOLD = 8


class ImagingError(RuntimeError):
    pass


@dataclass(frozen=True)
class BBox:
    """Caixa delimitadora inclusiva-exclusiva, no padrao do Pillow."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)

    def expand(self, margin: int, bounds: tuple[int, int]) -> "BBox":
        """Expande a caixa em `margin` px, sem sair dos limites da imagem."""
        w, h = bounds
        return BBox(
            max(0, self.left - margin),
            max(0, self.top - margin),
            min(w, self.right + margin),
            min(h, self.bottom + margin),
        )

    def to_square(self, bounds: tuple[int, int]) -> "BBox":
        """Converte para quadrado centrado, respeitando os limites."""
        w, h = bounds
        side = min(max(self.width, self.height), w, h)
        cx = (self.left + self.right) // 2
        cy = (self.top + self.bottom) // 2
        left = max(0, min(cx - side // 2, w - side))
        top = max(0, min(cy - side // 2, h - side))
        return BBox(left, top, left + side, top + side)


def load_rgba(path: Path) -> Image.Image:
    """Carrega qualquer formato suportado como RGBA."""
    try:
        img = Image.open(path)
    except Exception as exc:  # noqa: BLE001
        raise ImagingError(f"nao foi possivel abrir {path.name}: {exc}") from exc
    return img.convert("RGBA")


def has_alpha(path: Path) -> bool:
    """A imagem original ja possui canal alpha com transparencia real?"""
    try:
        img = Image.open(path)
    except Exception:  # noqa: BLE001
        return False
    if img.mode not in ("RGBA", "LA", "PA"):
        return False
    alpha = np.array(img.convert("RGBA").getchannel("A"))
    return bool((alpha < 255).any())


def subject_bbox(img: Image.Image, threshold: int = ALPHA_THRESHOLD) -> BBox | None:
    """Caixa do sujeito, definida pelos pixels com alpha acima do limiar.

    Retorna None se a imagem for inteiramente transparente.
    """
    alpha = np.array(img.getchannel("A"))
    mask = alpha > threshold
    if not mask.any():
        return None
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    return BBox(int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def normalize(
    img: Image.Image,
    canvas: tuple[int, int],
    *,
    subject_height_ratio: float = 0.85,
    floor_margin_ratio: float = 0.05,
    background: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> tuple[Image.Image, dict]:
    """Coloca o sujeito num canvas fixo, com escala e ancoragem consistentes.

    O sujeito e escalado para ocupar `subject_height_ratio` da altura do canvas
    e ancorado horizontalmente ao centro, verticalmente pelos "pes"
    (`floor_margin_ratio` de margem inferior).

    Essa padronizacao e o que permite, mais tarde, que o mesmo script de
    recorte de rig funcione para todas as personagens (ADR-002).

    Retorna a imagem normalizada e um dicionario com a transformacao aplicada,
    para registro na metadata.
    """
    cw, ch = canvas
    bbox = subject_bbox(img)
    if bbox is None:
        raise ImagingError("imagem totalmente transparente — sem sujeito para normalizar")

    subject = img.crop(bbox.as_tuple())
    target_h = max(1, int(round(ch * subject_height_ratio)))
    scale = target_h / subject.height
    target_w = max(1, int(round(subject.width * scale)))

    # Se ficar largo demais para o canvas, a largura passa a ser o limitante.
    if target_w > cw:
        scale = cw / subject.width
        target_w = cw
        target_h = max(1, int(round(subject.height * scale)))

    resized = subject.resize((target_w, target_h), LANCZOS)

    out = Image.new("RGBA", canvas, background)
    x = (cw - target_w) // 2
    y = ch - target_h - int(round(ch * floor_margin_ratio))
    y = max(0, min(y, ch - target_h))
    out.alpha_composite(resized, (x, y))

    transform = {
        "source_bbox": list(bbox.as_tuple()),
        "scale": round(scale, 6),
        "placed_at": [x, y],
        "subject_size": [target_w, target_h],
        "canvas": [cw, ch],
        "resample": "lanczos",
    }
    return out, transform


def crop_region(
    img: Image.Image,
    bbox: BBox,
    *,
    size: int | None = None,
    margin: int = 0,
    square: bool = True,
) -> Image.Image:
    """Recorta uma regiao, opcionalmente quadrada e redimensionada."""
    bounds = img.size
    box = bbox.expand(margin, bounds)
    if square:
        box = box.to_square(bounds)
    out = img.crop(box.as_tuple())
    if size:
        out = out.resize((size, size), LANCZOS)
    return out


def fit_within(img: Image.Image, max_side: int) -> Image.Image:
    """Reduz a imagem para caber em max_side, preservando a proporcao.

    Nao amplia imagens menores que o limite — ampliar so adicionaria peso
    sem informacao nova.
    """
    if max(img.size) <= max_side:
        return img
    scale = max_side / max(img.size)
    size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    return img.resize(size, LANCZOS)


def region_by_fraction(
    img: Image.Image,
    *,
    top: float,
    bottom: float,
    left: float = 0.0,
    right: float = 1.0,
) -> BBox:
    """Regiao definida por fracoes da CAIXA DO SUJEITO, nao do canvas.

    Usar a caixa do sujeito evita que margens vazias distorcam o recorte.
    """
    sb = subject_bbox(img)
    if sb is None:
        raise ImagingError("sem sujeito na imagem")
    return BBox(
        sb.left + int(sb.width * left),
        sb.top + int(sb.height * top),
        sb.left + int(sb.width * right),
        sb.top + int(sb.height * bottom),
    )


def trim_alpha(img: Image.Image, threshold: int = ALPHA_THRESHOLD) -> Image.Image:
    """Remove bordas totalmente transparentes."""
    bbox = subject_bbox(img, threshold)
    return img if bbox is None else img.crop(bbox.as_tuple())


def alpha_stats(img: Image.Image) -> dict:
    """Estatisticas de alpha usadas pelos quality gates."""
    alpha = np.array(img.getchannel("A"))
    total = int(alpha.size)
    opaque = int((alpha == 255).sum())
    transparent = int((alpha == 0).sum())
    semi = total - opaque - transparent
    return {
        "total_pixels": total,
        "opaque_ratio": round(opaque / total, 6) if total else 0.0,
        "transparent_ratio": round(transparent / total, 6) if total else 0.0,
        "semitransparent_ratio": round(semi / total, 6) if total else 0.0,
        "touches_edge": bool(
            max(
                int(alpha[0, :].max()),
                int(alpha[-1, :].max()),
                int(alpha[:, 0].max()),
                int(alpha[:, -1].max()),
            )
            == 255
        ),
    }


def save_png(img: Image.Image, path: Path) -> Path:
    """Salva PNG de forma atomica, para nao deixar arquivo corrompido."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    img.save(tmp, "PNG", optimize=True)
    tmp.replace(path)
    return path

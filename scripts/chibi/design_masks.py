"""Segmentacao de vestuario com REGIOES PROTEGIDAS (etapa MASK REVIEW).

Substitui a segmentacao ingenua de `design_transfer.build_masks`, que tratava
"toda regiao escura" como roupa e por isso engolia cabelo e meias-calcas.

Metodo. Nenhuma mascara sai de cor sozinha. Cada uma combina:

  cor  AND  posicao  AND  conectividade  AND  geometria  AND  alpha
       AND  exclusao explicita das PROTECTED_REGIONS

Discriminador cromatico medido na arte real (`full_body.png`), dentro do
sujeito e restrito a pixels escuros (max(RGB) < 110):

    capa (tecido)      R-B = -6.7   -> FRIO
    meia-calca (coxa)  R-B = +15.7  -> QUENTE
    meia-calca (canela) R-B = +6.6  -> QUENTE
    cabelo             R-B =  +0.4  -> NEUTRO

Ou seja: `R-B` separa capa de meia-calca, algo que luminancia sozinha nao
faz — as duas sao "escuras". O cabelo fica no meio e por isso NAO e separado
por cor: e isolado por conectividade com a regiao da cabeca.

Este modulo nao usa IA generativa, nao baixa nada e nao modifica arte-fonte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from .design_transfer import (
    DesignTransferError,
    bbox_of,
    is_gold,
    load_rgba,
    mask_sha256,
    subject_mask,
)

# ---------------------------------------------------------------------------
# parametros — cromaticos e geometricos, todos explicitos
# ---------------------------------------------------------------------------

#: Limiar de luminancia para "tecido escuro". max(RGB) < DARK_MAX.
DARK_MAX = 110

#: R-B <= COOL_MAX  -> tecido frio (capa).
COOL_MAX = -2
#: R-B >= WARM_MIN  -> tecido quente (meia-calca) => PROTEGIDO.
WARM_MIN = 3

#: Fracoes da altura da caixa do sujeito.
HEAD_BOTTOM = 0.155      # abaixo disto acaba o queixo
HAIR_MAX_BOTTOM = 0.46   # o cabelo mais longo nao passa daqui
SHOULDER_TOP = 0.175     # onde comeca o tronco vestido
HIP = 0.52               # divisa tronco / pernas
#: Cintura: MINIMO medido no perfil vertical do tecido frio (faixa 0.50-0.55
#: tem 642 px contra ~4500 acima e ~1900 abaixo). Divide mangas de capa.
WAIST = 0.52
#: A capa comeca na cintura; acima disso o tecido frio lateral e manga.
CAPE_TOP = WAIST
SHOE_TOP = 0.93          # sapatos
#: Os sapatos ocupam apenas a coluna das pernas. Medido pelas meias-calcas:
#: x_rel [0.29, 0.78]. Sem esse limite lateral a faixa dos pes atravessaria a
#: largura toda e protegeria a barra da capa, que desce ate o chao.
LEG_LEFT = 0.26
LEG_RIGHT = 0.81

#: Nomes das regioes protegidas. A composicao NUNCA pode escrever aqui.
PROTECTED_REGIONS = (
    "cabeca",     # rosto, olhos, boca, chifres
    "cabelo",
    "pele",       # maos, pernas, tronco exposto
    "meias",      # pele das pernas coberta por meia-calca
    "sapatos",
)

#: Pecas de vestuario a segmentar.
GARMENT_REGIONS = (
    "torso",
    "mangas",
    "capa_esquerda",
    "capa_direita",
    "ornamentos",
    "inferiores",
)

RIGIDITY: dict[str, str] = {
    "torso": "semi_rigid",
    "mangas": "cloth",
    "capa_esquerda": "cloth",
    "capa_direita": "cloth",
    "ornamentos": "rigid",
    "inferiores": "rigid",
}


class MaskError(DesignTransferError):
    pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    from skimage.measure import label

    lab = label(mask, connectivity=2)
    return lab, int(lab.max())


def _largest(mask: np.ndarray, n: int = 1) -> np.ndarray:
    """Mantem os n maiores componentes conexos."""
    lab, count = _label(mask)
    if count == 0:
        return mask
    sizes = [(int((lab == i).sum()), i) for i in range(1, count + 1)]
    sizes.sort(reverse=True)
    keep = np.zeros_like(mask)
    for _, idx in sizes[:n]:
        keep |= lab == idx
    return keep


def _drop_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    lab, count = _label(mask)
    out = np.zeros_like(mask)
    for i in range(1, count + 1):
        comp = lab == i
        if int(comp.sum()) >= min_area:
            out |= comp
    return out


def _connected_to(mask: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Componentes de `mask` que tocam `seed`. Base do isolamento do cabelo."""
    lab, count = _label(mask)
    out = np.zeros_like(mask)
    hit = set(np.unique(lab[seed & mask]))
    for i in hit:
        if i:
            out |= lab == i
    return out


def _fill(mask: np.ndarray) -> np.ndarray:
    from scipy.ndimage import binary_fill_holes  # noqa: F401  (opcional)

    return binary_fill_holes(mask)


def _close(mask: np.ndarray, radius: int = 2) -> np.ndarray:
    from skimage.morphology import closing, disk

    if not mask.any():
        return mask
    return np.asarray(closing(mask, disk(radius)), dtype=bool)


def _band(shape: tuple[int, int], bbox, top_f: float, bot_f: float) -> np.ndarray:
    l, t, r, b = bbox
    h = b - t
    m = np.zeros(shape, dtype=bool)
    m[t + int(h * top_f):t + int(h * bot_f), :] = True
    return m


# ---------------------------------------------------------------------------
# regioes protegidas
# ---------------------------------------------------------------------------


def build_protected(source: Image.Image) -> dict[str, np.ndarray]:
    """Regioes onde a composicao NUNCA pode escrever.

    Rosto, olhos, boca, chifres e cabelo saem por geometria + conectividade,
    nao por cor: o cabelo e cromaticamente proximo da capa.
    """
    arr = np.array(source)
    rgb = arr[..., :3].astype(int)
    subj = subject_mask(source)
    bbox = bbox_of(subj)
    l, t, r, b = bbox
    h, w = b - t, r - l
    shape = rgb.shape[:2]
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    out: dict[str, np.ndarray] = {}

    # cabeca: rosto, olhos, boca, chifres. Faixa geometrica dura.
    out["cabeca"] = subj & _band(shape, bbox, 0.0, HEAD_BOTTOM)

    # cabelo: escuro, conectado a cabeca, sem descer alem do limite conhecido.
    #
    # A conectividade sozinha NAO basta: cabelo e capa se tocam, entao o
    # flood-fill vazava do cabelo para as mangas e a parte alta da capa,
    # roubando-as do vestuario. Medido na arte real (pixels escuros):
    #     cabelo   R-B = -0.5 a -2.5  (neutro)
    #     manga    R-B = -8.0 a -8.7  (frio)
    #     capa alta R-B = -12.4       (frio)
    # Por isso o crescimento e restrito a pixels NAO-frios: o tecido frio
    # funciona como barreira natural e o cabelo para onde a roupa comeca.
    dark = (rgb.max(2) < DARK_MAX) & subj
    not_cool = (R - B) > COOL_MAX
    seed = subj & _band(shape, bbox, 0.0, HEAD_BOTTOM * 0.9)
    hair = _connected_to(
        dark & not_cool & _band(shape, bbox, 0.0, HAIR_MAX_BOTTOM), seed
    )
    out["cabelo"] = _close(hair)

    # pele exposta: maos, pernas, tronco.
    skin = (R > 170) & (G > 120) & (B > 105) & (R > B + 18) & subj
    out["pele"] = _close(_drop_small(skin, 80))

    # meia-calca: escura e QUENTE, abaixo do quadril. E perna, nao vestuario
    # transferivel — protegida para nao ser confundida com a capa.
    warm = (R - B) >= WARM_MIN
    meias = dark & warm & _band(shape, bbox, HIP - 0.06, 1.0)
    out["meias"] = _close(_drop_small(meias, 200))

    # sapatos: faixa dos pes LIMITADA a coluna das pernas. A capa se espalha
    # pelo chao na mesma altura; proteger a largura inteira roubaria a barra.
    xs_all = np.arange(shape[1])[None, :]
    leg_cols = np.repeat(
        (xs_all >= l + int(w * LEG_LEFT)) & (xs_all <= l + int(w * LEG_RIGHT)),
        shape[0], axis=0,
    )
    out["sapatos"] = subj & _band(shape, bbox, SHOE_TOP, 1.0) & leg_cols

    return out


def protected_union(protected: dict[str, np.ndarray]) -> np.ndarray:
    u = None
    for m in protected.values():
        u = m.copy() if u is None else (u | m)
    if u is None:
        raise MaskError("nenhuma regiao protegida")
    return u


# ---------------------------------------------------------------------------
# vestuario
# ---------------------------------------------------------------------------


def build_garment(
    source: Image.Image,
    protected: dict[str, np.ndarray] | None = None,
    min_area: int = 120,
) -> dict[str, np.ndarray]:
    """Mascaras por peca, ja subtraidas das regioes protegidas."""
    arr = np.array(source)
    rgb = arr[..., :3].astype(int)
    subj = subject_mask(source)
    bbox = bbox_of(subj)
    l, t, r, b = bbox
    h, w = b - t, r - l
    shape = rgb.shape[:2]
    R, B = rgb[..., 0], rgb[..., 2]

    if protected is None:
        protected = build_protected(source)
    banned = protected_union(protected)
    allowed = subj & ~banned

    dark = (rgb.max(2) < DARK_MAX) & subj
    cool = (R - B) <= COOL_MAX
    gold = is_gold(rgb) & subj

    masks: dict[str, np.ndarray] = {}

    # ornamentos: ouro e o unico elemento realmente separavel por cor (~1%).
    # 'inferiores' primeiro: reivindica o ouro do calcado. As faixas se
    # tocam, entao 'ornamentos' e definido por EXCLUSAO para as duas pecas
    # nao dividirem os mesmos pixels.
    masks["inferiores"] = _drop_small(
        _close(gold & subj & _band(shape, bbox, SHOE_TOP - 0.03, 1.0), 1),
        max(min_area // 8, 8),
    )
    masks["ornamentos"] = _drop_small(
        _close(gold & ~banned & _band(shape, bbox, SHOULDER_TOP, SHOE_TOP), 1),
        max(min_area // 8, 8),
    ) & ~masks["inferiores"]

    # A cintura e um MINIMO medido no perfil vertical do tecido frio: a faixa
    # 0.50-0.55 tem 642 px contra ~4500 acima e ~1900 abaixo. E onde as mangas
    # sino terminam e o corpo da capa comeca. Usar esse minimo como divisor e
    # geometria observada, nao numero escolhido a gosto.
    capa = dark & cool & allowed & _band(shape, bbox, CAPE_TOP, 1.0)
    capa = _drop_small(_close(capa), min_area * 4)
    # separar por lado em relacao ao eixo do sujeito
    cx = l + w // 2
    xs = np.arange(shape[1])[None, :]
    left_half = np.repeat(xs < cx, shape[0], axis=0)
    lab, count = _label(capa)
    esq = np.zeros_like(capa)
    dir_ = np.zeros_like(capa)
    for i in range(1, count + 1):
        comp = lab == i
        # componente vai para o lado onde esta a maior parte de sua area
        if int((comp & left_half).sum()) >= int(comp.sum()) / 2:
            esq |= comp
        else:
            dir_ |= comp
    masks["capa_esquerda"] = esq
    masks["capa_direita"] = dir_

    # Torso e mangas: NAO separar por uma coluna central fixa. O vestuario
    # alarga de x_rel [0.40,0.61] no colarinho para [0.24,0.75] na cintura;
    # qualquer divisa vertical rigida corta a manga ao meio e rotula parte
    # dela como torso. A separacao correta e por LARGURA LOCAL: em cada
    # linha, o tecido proximo ao eixo do corpo e torso; o que se afasta
    # alem do meio-corpo e manga.
    upper = dark & cool & allowed & _band(shape, bbox, SHOULDER_TOP, WAIST) & ~capa
    upper = _drop_small(_close(upper), min_area)

    torso = np.zeros_like(upper)
    mangas = np.zeros_like(upper)
    #: metade da largura do tronco vestido, em fracao da largura do sujeito.
    #: 0.115 corresponde ao colarinho medido ([0.40,0.61] => raio 0.105).
    half = max(int(w * 0.115), 1)
    for y in np.nonzero(upper.any(axis=1))[0]:
        cols = np.nonzero(upper[y])[0]
        near = np.abs(cols - cx) <= half
        torso[y, cols[near]] = True
        mangas[y, cols[~near]] = True

    masks["torso"] = _drop_small(_close(torso), min_area)
    # a manga precisa de area minima maior: respingos laterais sao sombra
    masks["mangas"] = _drop_small(_close(mangas & ~masks["torso"]), min_area * 2)

    # ouro tem prioridade: define o design
    orn = masks["ornamentos"] | masks["inferiores"]
    for k in ("torso", "mangas", "capa_esquerda", "capa_direita"):
        masks[k] = masks[k] & ~orn

    # garantia final: nada de vestuario dentro do protegido
    for k in list(masks):
        masks[k] = masks[k] & ~banned

    return masks


# ---------------------------------------------------------------------------
# metricas e revisao
# ---------------------------------------------------------------------------


def mask_protected_overlap_pixels(mask: np.ndarray, banned: np.ndarray) -> int:
    """Pixels de uma mascara que caem em regiao protegida. DEVE ser 0."""
    return int(np.count_nonzero(mask & banned))


def bbox_fractions(mask: np.ndarray, subject_bbox) -> dict[str, float]:
    """Caixa da mascara em fracoes da caixa do sujeito — plausibilidade."""
    if not mask.any():
        return {}
    l, t, r, b = subject_bbox
    h, w = b - t, r - l
    ys, xs = np.nonzero(mask)
    return {
        "top": round((ys.min() - t) / h, 4),
        "bottom": round((ys.max() + 1 - t) / h, 4),
        "left": round((xs.min() - l) / w, 4),
        "right": round((xs.max() + 1 - l) / w, 4),
    }


@dataclass
class MaskReview:
    """Resultado da etapa MASK REVIEW. `approved` e sempre humano."""

    protected: dict[str, np.ndarray]
    garment: dict[str, np.ndarray]
    subject: np.ndarray
    subject_bbox: tuple[int, int, int, int]
    metrics: dict[str, Any] = field(default_factory=dict)
    approved: bool = False

    @property
    def banned(self) -> np.ndarray:
        return protected_union(self.protected)

    def all_clear(self) -> bool:
        """Todas as verificacoes objetivas passaram? Nao substitui o humano."""
        return all(
            m["protected_overlap"] == 0 and m["pixels"] > 0
            for m in self.metrics.values()
        )


def review_masks(source: Image.Image, min_area: int = 120) -> MaskReview:
    subj = subject_mask(source)
    bbox = bbox_of(subj)
    protected = build_protected(source)
    garment = build_garment(source, protected, min_area=min_area)
    banned = protected_union(protected)

    metrics: dict[str, Any] = {}
    total = int(np.count_nonzero(subj))
    for name, m in garment.items():
        px = int(np.count_nonzero(m))
        metrics[name] = {
            "pixels": px,
            "pct_subject": round(100 * px / total, 3),
            "protected_overlap": mask_protected_overlap_pixels(m, banned),
            "bbox_fractions": bbox_fractions(m, bbox),
            "rigidity": RIGIDITY.get(name),
            "mask_sha256": mask_sha256(m),
        }
    return MaskReview(protected, garment, subj, bbox, metrics)


# ---------------------------------------------------------------------------
# visualizacao
# ---------------------------------------------------------------------------

GARMENT_COLORS: dict[str, tuple[int, int, int]] = {
    "torso": (0, 150, 255),
    "mangas": (0, 220, 200),
    "capa_esquerda": (255, 70, 190),
    "capa_direita": (170, 60, 255),
    "ornamentos": (255, 205, 0),
    "inferiores": (255, 120, 0),
}
PROTECTED_COLOR = (255, 0, 0)


def overlay(
    base: Image.Image,
    masks: dict[str, np.ndarray],
    colors: dict[str, tuple[int, int, int]] | None = None,
    alpha: float = 0.5,
) -> Image.Image:
    colors = colors or GARMENT_COLORS
    arr = np.array(base.convert("RGBA")).astype(np.float64)
    for name, m in masks.items():
        if m is None or not m.any():
            continue
        c = np.array(colors.get(name, PROTECTED_COLOR), dtype=np.float64)
        arr[m, :3] = arr[m, :3] * (1 - alpha) + c * alpha
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def overlay_single(base: Image.Image, mask: np.ndarray, color=(0, 150, 255),
                   alpha: float = 0.55) -> Image.Image:
    return overlay(base, {"m": mask}, {"m": color}, alpha)


__all__ = [
    "PROTECTED_REGIONS", "GARMENT_REGIONS", "RIGIDITY", "GARMENT_COLORS",
    "MaskError", "MaskReview", "build_protected", "build_garment",
    "protected_union", "mask_protected_overlap_pixels", "bbox_fractions",
    "review_masks", "overlay", "overlay_single", "load_rgba",
]

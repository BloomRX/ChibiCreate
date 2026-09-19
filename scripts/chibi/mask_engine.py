"""Motor GENERICO de segmentacao de vestuario.

Nenhum numero medido na waifu_001 aparece neste arquivo. Todos os limiares
chegam prontos em `ResolvedParams`, vindos de:

  1. derivacao a partir da propria imagem  (`mask_profile.derive_params`)
  2. override opcional da personagem       (`characters/<id>/masks.yaml`)

O que ESTE modulo contem sao estrategias — "tecido central e torso",
"tecido lateral acima da cintura e manga", "cor de destaque e ornamento" —
que valem para qualquer personagem em pose frontal de corpo inteiro.

Fluxo:

    mask generator -> estrategias genericas -> overrides -> mascaras
                   -> MASK REVIEW HUMANA -> warp/composicao (bloqueado)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .design_transfer import bbox_of, load_rgba, mask_sha256, subject_mask
from .mask_profile import (
    DEFAULT_PRIORITY,
    MaskProfile,
    ResolvedParams,
    derive_params,
    load_profile,
    resolve_params,
)

PROTECTED_REGIONS = ("cabeca", "cabelo", "pele", "meias", "sapatos")

#: Excecao DECLARADA e estreita: a ornamentacao do calcado vive, por
#: definicao, dentro da regiao 'sapatos'. Qualquer outra combinacao peca x
#: regiao protegida continua proibida e vale 0 na metrica de overlap.
ALLOWED_PROTECTED_OVERLAP: dict[str, frozenset[str]] = {
    "inferiores": frozenset({"sapatos"}),
}
GARMENT_REGIONS = (
    "torso", "mangas", "capa_esquerda", "capa_direita",
    "ornamentos", "inferiores",
)


class MaskError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# primitivas
# ---------------------------------------------------------------------------


def _label(mask: np.ndarray):
    from skimage.measure import label

    lab = label(mask, connectivity=2)
    return lab, int(lab.max())


def _drop_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    lab, n = _label(mask)
    out = np.zeros_like(mask)
    for i in range(1, n + 1):
        comp = lab == i
        if int(comp.sum()) >= min_area:
            out |= comp
    return out


def _close(mask: np.ndarray, radius: int = 2) -> np.ndarray:
    from skimage.morphology import closing, disk

    if not mask.any():
        return mask
    return np.asarray(closing(mask, disk(radius)), dtype=bool)


def _connected_to(mask: np.ndarray, seed: np.ndarray) -> np.ndarray:
    lab, _ = _label(mask)
    out = np.zeros_like(mask)
    for i in np.unique(lab[seed & mask]):
        if i:
            out |= lab == i
    return out


def _band(shape, bbox, top_f: float, bot_f: float) -> np.ndarray:
    l, t, r, b = bbox
    h = b - t
    m = np.zeros(shape, dtype=bool)
    m[t + int(h * top_f):t + int(h * bot_f), :] = True
    return m


def _cols(shape, bbox, left_f: float, right_f: float) -> np.ndarray:
    l, t, r, b = bbox
    w = r - l
    xs = np.arange(shape[1])[None, :]
    return np.repeat((xs >= l + int(w * left_f)) & (xs <= l + int(w * right_f)),
                     shape[0], axis=0)


def accent_mask(rgb: np.ndarray, hints: dict | None = None) -> np.ndarray:
    """Cor de destaque (ornamentos).

    Generico: destaque = pixel cromaticamente saturado e claro em relacao ao
    resto. Se a personagem declarar `color_hints.accent_rgb`, usa-se
    proximidade aquela cor em vez da regra generica.
    """
    r = rgb[..., 0].astype(int)
    g = rgb[..., 1].astype(int)
    b = rgb[..., 2].astype(int)
    hints = hints or {}
    ref = hints.get("accent_rgb")
    if ref:
        ref = np.array(ref[:3], dtype=int)
        tol = int(hints.get("accent_tolerance", 60))
        return (np.abs(rgb[..., :3].astype(int) - ref).sum(axis=2) <= tol)
    # Destaque = saturacao alta e razoavelmente claro. NAO usar `r >= b`:
    # isso codificaria "ouro" e falharia em ornamento ciano ou prateado.
    mx = rgb[..., :3].max(axis=2).astype(int)
    mn = rgb[..., :3].min(axis=2).astype(int)
    sat = mx - mn
    return (sat >= 40) & (mx >= 110)


def skin_mask(rgb: np.ndarray, hints: dict | None = None) -> np.ndarray:
    """Pele exposta.

    Generico: pixels claros e quentes. `color_hints.skin_rgb` sobrescreve.
    """
    hints = hints or {}
    ref = hints.get("skin_rgb")
    if ref:
        ref = np.array(ref[:3], dtype=int)
        tol = int(hints.get("skin_tolerance", 70))
        return (np.abs(rgb[..., :3].astype(int) - ref).sum(axis=2) <= tol)
    r = rgb[..., 0].astype(int)
    g = rgb[..., 1].astype(int)
    b = rgb[..., 2].astype(int)
    return (r > 150) & (g > 100) & (b > 90) & (r > b + 15)


# ---------------------------------------------------------------------------
# regioes protegidas
# ---------------------------------------------------------------------------


def build_protected(
    source: Image.Image, params: ResolvedParams, subject=None, bbox=None
) -> dict[str, np.ndarray]:
    """Regioes onde a composicao NUNCA escreve."""
    arr = np.array(source)
    rgb = arr[..., :3]
    subj = subject_mask(source) if subject is None else subject
    bbox = bbox_of(subj) if bbox is None else bbox
    l, t, r, b = bbox
    shape = rgb.shape[:2]
    an = params.anatomy
    R = rgb[..., 0].astype(int)
    B = rgb[..., 2].astype(int)
    rb = R - B

    dark = (rgb.max(axis=2) <= params["dark_max"]) & subj
    out: dict[str, np.ndarray] = {}

    # cabeca: faixa superior. Estrutural, nao calibrada.
    out["cabeca"] = subj & _band(shape, bbox, 0.0, an["head_bottom"])

    # cabelo: escuro, conectado a cabeca. O crescimento evita o tecido
    # (pixels frios) para nao vazar do cabelo para a roupa — estrategia
    # generica: o material vizinho de cor distinta funciona como barreira.
    not_cool = rb > params["cool_max"]
    seed = subj & _band(shape, bbox, 0.0, an["head_bottom"] * 0.9)
    hair = _connected_to(
        dark & not_cool & _band(shape, bbox, 0.0, an["hair_max_bottom"]), seed
    )
    out["cabelo"] = _close(hair)

    # pele exposta
    out["pele"] = _close(_drop_small(
        skin_mask(rgb, params.profile.color_hints) & subj, 80))

    # tecido quente das pernas (meia-calca / calca): protegido, e perna
    warm = rb >= params["warm_min"]
    out["meias"] = _close(_drop_small(
        dark & warm & _band(shape, bbox, max(params["waist"] - 0.06, 0.0), 1.0),
        200))

    # calcado: faixa baixa LIMITADA as colunas das pernas, para nao capturar
    # tecido espalhado pelo chao
    out["sapatos"] = (
        subj
        & _band(shape, bbox, an["shoe_top"], 1.0)
        & _cols(shape, bbox, params["leg_left"], params["leg_right"])
    )

    # overrides declarativos da personagem
    for name, spec in (params.profile.protected_regions or {}).items():
        extra = _region_from_spec(spec, shape, bbox, subj)
        if extra is None:
            continue
        out[name] = (out.get(name, np.zeros(shape, bool)) | extra) & subj

    return out


def _region_from_spec(spec, shape, bbox, subj) -> np.ndarray | None:
    """Converte {top,bottom,left,right} em fracoes numa mascara."""
    if not isinstance(spec, dict):
        return None
    keys = ("top", "bottom", "left", "right")
    if not any(k in spec for k in keys):
        return None
    m = _band(shape, bbox, float(spec.get("top", 0.0)),
              float(spec.get("bottom", 1.0)))
    m &= _cols(shape, bbox, float(spec.get("left", 0.0)),
               float(spec.get("right", 1.0)))
    return m & subj


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
    params: ResolvedParams,
    protected: dict[str, np.ndarray],
    min_area: int = 120,
    subject=None,
    bbox=None,
) -> dict[str, np.ndarray]:
    arr = np.array(source)
    rgb = arr[..., :3]
    subj = subject_mask(source) if subject is None else subject
    bbox = bbox_of(subj) if bbox is None else bbox
    l, t, r, b = bbox
    w = r - l
    cx = l + w // 2
    shape = rgb.shape[:2]
    an = params.anatomy
    rb = rgb[..., 0].astype(int) - rgb[..., 2].astype(int)

    banned = protected_union(protected)
    allowed = subj & ~banned
    dark = (rgb.max(axis=2) <= params["dark_max"]) & subj
    # TECIDO por exclusao, nao por um tom estreito de "frio": e o material
    # escuro que sobrou depois de retirar pele, cabelo e as pernas (essas ja
    # protegidas via `warm_min`). Definir tecido como "R-B <= cool_max"
    # quebrava quando duas pecas da mesma roupa tinham tons ligeiramente
    # diferentes — a de tom maior era descartada e a peca sumia.
    cool = allowed
    accent = accent_mask(rgb, params.profile.color_hints) & subj

    masks: dict[str, np.ndarray] = {}

    # --- cor de destaque, faixa baixa primeiro (prioridade evita disputa)
    # 'inferiores' e a ornamentacao DO CALCADO: por definicao ela vive dentro
    # da regiao 'sapatos'. Subtrair o protegido aqui a zeraria sempre — por
    # isso ela e a unica peca autorizada a ocupar essa regiao, e apenas ela.
    shoe_zone = protected.get("sapatos", np.zeros(shape, bool))
    masks["inferiores"] = _drop_small(
        _close(accent & subj
               & _band(shape, bbox, max(an["shoe_top"] - 0.03, 0.0), 1.0), 1),
        max(min_area // 8, 8))
    masks["ornamentos"] = _drop_small(
        _close(accent & ~banned & _band(shape, bbox, an["shoulder_top"],
                                        an["shoe_top"]), 1),
        max(min_area // 8, 8)) & ~masks["inferiores"]

    # --- capa: tecido da cintura para baixo, separada por lado
    capa = dark & cool & allowed & _band(shape, bbox, params["waist"], 1.0)
    capa = _drop_small(_close(capa), min_area * 4)
    xs = np.arange(shape[1])[None, :]
    left_half = np.repeat(xs < cx, shape[0], axis=0)
    lab, n = _label(capa)
    esq = np.zeros_like(capa)
    dir_ = np.zeros_like(capa)
    for i in range(1, n + 1):
        comp = lab == i
        n_left = int((comp & left_half).sum())
        n_right = int(comp.sum()) - n_left
        # Um componente que ocupa os dois lados de forma relevante e uma capa
        # unica atravessando o eixo (ou duas metades unidas pela barra, que se
        # tocam atras das pernas). Nesse caso divide-se POR PIXEL; atribuir o
        # componente inteiro a um lado esvaziaria o outro.
        if n_left > 0 and n_right > 0 and min(n_left, n_right) >= 0.15 * int(comp.sum()):
            esq |= comp & left_half
            dir_ |= comp & ~left_half
        elif n_left >= n_right:
            esq |= comp
        else:
            dir_ |= comp
    masks["capa_esquerda"] = esq
    masks["capa_direita"] = dir_

    # --- torso x mangas: separacao por LARGURA LOCAL, nao coluna fixa.
    # O vestuario alarga do colarinho para a cintura em praticamente qualquer
    # personagem; uma divisa vertical rigida cortaria a manga ao meio.
    upper = (dark & cool & allowed
             & _band(shape, bbox, an["shoulder_top"], params["waist"]) & ~capa)
    upper = _drop_small(_close(upper), min_area)
    half = max(int(w * params["torso_half_width"]), 1)
    torso = np.zeros_like(upper)
    mangas = np.zeros_like(upper)
    for y in np.nonzero(upper.any(axis=1))[0]:
        cols = np.nonzero(upper[y])[0]
        near = np.abs(cols - cx) <= half
        torso[y, cols[near]] = True
        mangas[y, cols[~near]] = True
    masks["torso"] = _drop_small(_close(torso), min_area)
    masks["mangas"] = _drop_small(_close(mangas & ~masks["torso"]), min_area * 2)

    # --- prioridade e exclusoes finais
    prio = np.zeros(shape, bool)
    for key in DEFAULT_PRIORITY:
        prio |= masks.get(key, np.zeros(shape, bool))
    for key in masks:
        if key not in DEFAULT_PRIORITY:
            masks[key] = masks[key] & ~prio
        if key == "inferiores":
            # unica excecao: pode ficar dentro de 'sapatos' (e o ornamento do
            # proprio calcado), mas nao em nenhuma outra regiao protegida.
            outros = protected_union(
                {k: v for k, v in protected.items() if k != "sapatos"})
            masks[key] = masks[key] & ~outros
        else:
            masks[key] = masks[key] & ~banned

    # `closing` dilata a mascara e pode empurra-la para fora da silhueta.
    # Reancorar no sujeito e obrigatorio: mascara fora do corpo vira pixel
    # pintado no vazio durante a composicao.
    for key in masks:
        masks[key] = masks[key] & subj

    # --- restricoes geometricas declaradas pela personagem
    for name, spec in (params.profile.region_definitions or {}).items():
        if name in masks:
            box = _region_from_spec(spec, shape, bbox, subj)
            if box is not None:
                masks[name] = masks[name] & box

    return masks


# ---------------------------------------------------------------------------
# revisao
# ---------------------------------------------------------------------------


def mask_protected_overlap_pixels(
    mask: np.ndarray,
    banned: np.ndarray,
    region: str | None = None,
    protected: dict[str, np.ndarray] | None = None,
) -> int:
    """Pixels da mascara em regiao protegida. DEVE ser 0.

    `region` + `protected` habilitam a excecao declarada em
    ALLOWED_PROTECTED_OVERLAP (hoje: so ornamento de calcado dentro de
    'sapatos'). Sem esses argumentos a checagem e estrita.
    """
    allowed = ALLOWED_PROTECTED_OVERLAP.get(region or "", frozenset())
    if allowed and protected:
        banned = protected_union(
            {k: v for k, v in protected.items() if k not in allowed})
    return int(np.count_nonzero(mask & banned))


def bbox_fractions(mask: np.ndarray, subject_bbox) -> dict[str, float]:
    if not mask.any():
        return {}
    l, t, r, b = subject_bbox
    h, w = b - t, r - l
    ys, xs = np.nonzero(mask)
    return {
        "top": round(float((ys.min() - t) / h), 4),
        "bottom": round(float((ys.max() + 1 - t) / h), 4),
        "left": round(float((xs.min() - l) / w), 4),
        "right": round(float((xs.max() + 1 - l) / w), 4),
    }


@dataclass
class MaskReview:
    protected: dict[str, np.ndarray]
    garment: dict[str, np.ndarray]
    subject: np.ndarray
    subject_bbox: tuple[int, int, int, int]
    params: ResolvedParams
    metrics: dict[str, Any] = field(default_factory=dict)
    approved: bool = False

    @property
    def banned(self) -> np.ndarray:
        return protected_union(self.protected)

    @property
    def character_id(self):
        return self.params.profile.character_id

    def all_clear(self) -> bool:
        return all(m["protected_overlap"] == 0 and m["pixels"] > 0
                   for m in self.metrics.values())

    def provenance_report(self) -> str:
        from .mask_profile import describe

        return describe(self.params)


def review_masks(
    source: Image.Image,
    character_id: str | None = None,
    profile: MaskProfile | None = None,
    min_area: int = 120,
    root: Path | None = None,
) -> MaskReview:
    """Ponto de entrada. Sem `character_id` e sem `profile`, roda 100% generico."""
    subj = subject_mask(source)
    bbox = bbox_of(subj)
    rgb = np.array(source)[..., :3]

    if profile is None:
        profile = load_profile(character_id, root)
    derived = derive_params(rgb, subj, bbox)
    params = resolve_params(derived, profile)

    protected = build_protected(source, params, subj, bbox)
    garment = build_garment(source, params, protected, min_area, subj, bbox)
    banned = protected_union(protected)

    total = int(np.count_nonzero(subj))
    metrics: dict[str, Any] = {}
    for name, m in garment.items():
        px = int(np.count_nonzero(m))
        metrics[name] = {
            "pixels": px,
            "pct_subject": round(100 * px / total, 3) if total else 0.0,
            "protected_overlap": mask_protected_overlap_pixels(
                m, banned, name, protected),
            "bbox_fractions": bbox_fractions(m, bbox),
            "rigidity": params.rigidity.get(name),
            "strategy": params.strategy.get(name),
            "mask_sha256": mask_sha256(m),
        }
    return MaskReview(protected, garment, subj, bbox, params, metrics)


# ---------------------------------------------------------------------------
# visualizacao
# ---------------------------------------------------------------------------

GARMENT_COLORS = {
    "torso": (0, 150, 255),
    "mangas": (0, 220, 200),
    "capa_esquerda": (255, 70, 190),
    "capa_direita": (170, 60, 255),
    "ornamentos": (255, 205, 0),
    "inferiores": (255, 120, 0),
}


def overlay(base: Image.Image, masks: dict[str, np.ndarray],
            colors=None, alpha: float = 0.5) -> Image.Image:
    colors = colors or GARMENT_COLORS
    arr = np.array(base.convert("RGBA")).astype(np.float64)
    for name, m in masks.items():
        if m is None or not m.any():
            continue
        c = np.array(colors.get(name, (255, 0, 0)), dtype=np.float64)
        arr[m, :3] = arr[m, :3] * (1 - alpha) + c * alpha
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def overlay_single(base, mask, color=(0, 150, 255), alpha: float = 0.55):
    return overlay(base, {"m": mask}, {"m": color}, alpha)


__all__ = [
    "PROTECTED_REGIONS", "GARMENT_REGIONS", "GARMENT_COLORS", "MaskError",
    "MaskReview", "accent_mask", "skin_mask", "bbox_fractions",
    "build_garment", "build_protected", "load_rgba",
    "mask_protected_overlap_pixels", "overlay", "overlay_single",
    "protected_union", "review_masks",
]

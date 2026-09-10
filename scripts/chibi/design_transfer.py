"""Design / outfit transfer NAO-GENERATIVO para a linha experimental run_003.

Objetivo: preservar a base chibi da Run 003 (identidade, rosto, cabelo,
chifres, silhueta) e transferir o DESIGN da roupa/capa/ornamentos vindo de
`characters/<id>/reference/full_body.png`.

Ver docs/research/2026-09-09-design-transfer.md.

Invariantes desta implementacao:

* A fonte e SEMPRE `full_body.png` + mascara. `outfit.png` NAO e usado: e um
  recorte retangular heuristico que contem pele, pernas e fundo.
* Segmentacao NUNCA e por cor isolada: capa e cabelo tem distancia RGB ~29.5
  e sao inseparaveis por cor. Toda mascara e cor AND regiao geometrica AND
  alpha do sujeito.
* Fora da mascara transformada o output e byte-identico a Run 003. Isso e
  garantido por construcao (np.where) e verificado por
  `outside_mask_pixel_difference`, que DEVE ser 0.
* Nada de generativo. Nada de download. Nenhum arquivo-fonte e modificado.

Este modulo NAO substitui FLUX, Flow 01, quality gates nem o pipeline
oficial, e nao produz `master.png`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# dependencias e licencas — registradas por exigencia da diretiva
# ---------------------------------------------------------------------------

#: Toda dependencia usada aqui e permissiva e compativel com uso comercial.
LIBRARY_LICENSES: dict[str, str] = {
    "numpy": "BSD-3-Clause",
    "pillow": "MIT-CMU",
    "scikit-image": "BSD-3-Clause",
}

ALPHA_THRESHOLD = 128

#: Regioes geometricas, em fracoes da CAIXA DO SUJEITO, que delimitam onde
#: cada peca do design pode existir. Elas NAO sao um recorte estetico: servem
#: para desambiguar pixels que a cor sozinha nao separa (capa x cabelo).
#: Derivadas de DEFAULT_REGIONS['outfit'] (top=0.18) do flow01: acima disso e
#: cabeca/cabelo/chifres, que esta linha NAO pode tocar.
#: [HUMAN REVIEW REQUIRED] herdam a natureza heuristica do identity kit.
DESIGN_REGIONS: dict[str, dict[str, float]] = {
    # roupa principal: tronco. Comeca abaixo da cabeca e termina no quadril.
    "roupa": {"top": 0.18, "bottom": 0.52, "left": 0.0, "right": 1.0},
    # capa: tecido, desce ate a base e se alarga.
    "capa": {"top": 0.24, "bottom": 1.0, "left": 0.0, "right": 1.0},
    # ornamentos dourados: aparecem da ombreira aos pes.
    "ornamentos": {"top": 0.18, "bottom": 1.0, "left": 0.0, "right": 1.0},
}

#: Rigidez por regiao. Peca rigida nao pode ser deformada livremente: o
#: formato E o design. Tecido tolera deformacao ampla.
REGION_RIGIDITY: dict[str, str] = {
    "roupa": "semi_rigid",
    "capa": "cloth",
    "ornamentos": "rigid",
}

MASK_REGIONS = ("roupa", "capa", "ornamentos")


class DesignTransferError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------


def load_rgba(path: Path) -> Image.Image:
    """Carrega em RGBA sem modificar o arquivo de origem."""
    path = Path(path)
    if not path.exists():
        raise DesignTransferError(f"arquivo nao encontrado: {path}")
    with Image.open(path) as img:
        return img.convert("RGBA")


def subject_mask(img: Image.Image) -> np.ndarray:
    """Mascara booleana do sujeito.

    Usa alpha quando ele existe de fato. Quando a imagem e totalmente opaca
    (caso de saidas de modelo, que vem com fundo solido), cai para deteccao
    de fundo uniforme pelas bordas — nunca inventa transparencia.
    """
    arr = np.array(img)
    alpha = arr[..., 3]
    if int(alpha.min()) < ALPHA_THRESHOLD:
        return alpha >= ALPHA_THRESHOLD
    rgb = arr[..., :3].astype(np.int16)
    corners = np.concatenate([
        rgb[:8, :, :].reshape(-1, 3), rgb[-8:, :, :].reshape(-1, 3),
        rgb[:, :8, :].reshape(-1, 3), rgb[:, -8:, :].reshape(-1, 3),
    ])
    bg = np.median(corners, axis=0)
    if np.abs(corners - bg).mean() > 12.0:
        # bordas nao sao um fundo liso: nao ha o que remover.
        return np.ones(rgb.shape[:2], dtype=bool)
    return np.abs(rgb - bg).sum(axis=2) > 30


def bbox_of(mask: np.ndarray) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) exclusivo do conteudo True."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        raise DesignTransferError("mascara vazia: nao ha sujeito")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _region_box(bbox: tuple[int, int, int, int], frac: dict[str, float]) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    w, h = right - left, bottom - top
    return (
        left + int(round(w * frac["left"])),
        top + int(round(h * frac["top"])),
        left + int(round(w * frac["right"])),
        top + int(round(h * frac["bottom"])),
    )


def _in_box(shape: tuple[int, int], box: tuple[int, int, int, int]) -> np.ndarray:
    m = np.zeros(shape, dtype=bool)
    l, t, r, b = box
    m[max(t, 0):max(b, 0), max(l, 0):max(r, 0)] = True
    return m


# ---------------------------------------------------------------------------
# segmentacao: cor AND geometria AND alpha  (nunca cor sozinha)
# ---------------------------------------------------------------------------


def is_gold(rgb: np.ndarray) -> np.ndarray:
    """Ornamentos dourados. Separaveis por cor: ~0.9% dos pixels, R >> B."""
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    return (r > 120) & (g > 90) & (b < 110) & (r > b + 40) & (r >= g)


def is_dark(rgb: np.ndarray) -> np.ndarray:
    """Tecido escuro (roupa e capa). NAO distingue capa de cabelo sozinho."""
    return rgb.max(axis=2) < 90


def clean_mask(mask: np.ndarray, min_area: int = 64, close_radius: int = 2) -> np.ndarray:
    """Remove ilhas pequenas e fecha buracos. Determinista."""
    from skimage.morphology import closing, disk, remove_small_holes, remove_small_objects

    if not mask.any():
        return mask
    out = closing(mask, disk(close_radius))
    out = remove_small_objects(out, max_size=max(min_area - 1, 0))
    out = remove_small_holes(out, max_size=max(min_area - 1, 0))
    return out.astype(bool)


def build_masks(
    source: Image.Image,
    regions: dict[str, dict[str, float]] | None = None,
    min_area: int = 64,
) -> dict[str, np.ndarray]:
    """Constroi as mascaras de design a partir de `full_body.png`.

    Cada mascara e a intersecao de tres evidencias independentes:
    cor, regiao geometrica e pertencimento ao sujeito.
    """
    regions = regions or DESIGN_REGIONS
    arr = np.array(source)
    rgb = arr[..., :3]
    subj = subject_mask(source)
    bbox = bbox_of(subj)
    shape = rgb.shape[:2]

    gold = is_gold(rgb)
    dark = is_dark(rgb)

    masks: dict[str, np.ndarray] = {}

    orn = gold & subj & _in_box(shape, _region_box(bbox, regions["ornamentos"]))
    masks["ornamentos"] = clean_mask(orn, min_area=min_area // 4 or 1)

    roupa = dark & subj & _in_box(shape, _region_box(bbox, regions["roupa"]))
    masks["roupa"] = clean_mask(roupa, min_area=min_area)

    capa = dark & subj & _in_box(shape, _region_box(bbox, regions["capa"]))
    # a capa nao reivindica o que ja e roupa de tronco
    capa = capa & ~masks["roupa"]
    masks["capa"] = clean_mask(capa, min_area=min_area * 4)

    # ornamentos tem prioridade: sao o elemento que define o design
    for key in ("roupa", "capa"):
        masks[key] = masks[key] & ~masks["ornamentos"]

    return masks


# ---------------------------------------------------------------------------
# geometria: pontos de controle e transformacoes
# ---------------------------------------------------------------------------


def control_points(bbox: tuple[int, int, int, int], rows: int = 5, cols: int = 5) -> np.ndarray:
    """Grade de pontos (x, y) sobre a caixa do sujeito.

    Sem detector de pose treinado para chibi, os pares vem de landmarks
    geometricos da silhueta. E aproximacao declarada, nao correspondencia
    anatomica. Ver limitacao 4 do relatorio.
    """
    left, top, right, bottom = bbox
    xs = np.linspace(left, right - 1, cols)
    ys = np.linspace(top, bottom - 1, rows)
    return np.array([[x, y] for y in ys for x in xs], dtype=float)


def affine_map(
    src_bbox: tuple[int, int, int, int],
    dst_bbox: tuple[int, int, int, int],
) -> dict[str, float]:
    """Parametros da transformacao global (variante A): escala + translacao."""
    sl, st, sr, sb = src_bbox
    dl, dt, dr, db = dst_bbox
    sw, sh = sr - sl, sb - st
    dw, dh = dr - dl, db - dt
    return {
        "scale_x": dw / sw if sw else 1.0,
        "scale_y": dh / sh if sh else 1.0,
        "translate_x": float(dl - sl),
        "translate_y": float(dt - st),
        "src_bbox": [sl, st, sr, sb],
        "dst_bbox": [dl, dt, dr, db],
    }


def warp_affine(
    layer: np.ndarray,
    src_bbox: tuple[int, int, int, int],
    dst_bbox: tuple[int, int, int, int],
    output_shape: tuple[int, int],
    order: int = 1,
) -> np.ndarray:
    """Variante A: uma unica escala/translacao para tudo."""
    from skimage.transform import AffineTransform, warp

    p = affine_map(src_bbox, dst_bbox)
    sx, sy = p["scale_x"], p["scale_y"]
    sl, st = src_bbox[0], src_bbox[1]
    dl, dt = dst_bbox[0], dst_bbox[1]
    # mapeia destino -> origem (warp usa inverse map)
    tf = (
        AffineTransform(translation=(-dl, -dt))
        + AffineTransform(scale=(1.0 / sx, 1.0 / sy))
        + AffineTransform(translation=(sl, st))
    )
    return warp(layer, tf, output_shape=output_shape, order=order,
                mode="constant", cval=0.0, preserve_range=True)


def warp_tps(
    layer: np.ndarray,
    src_pts: np.ndarray,
    dst_pts: np.ndarray,
    output_shape: tuple[int, int],
    order: int = 1,
) -> np.ndarray:
    """Variante B: deformacao suave por pares de pontos de controle.

    scikit-image espera o mapeamento inverso: `from_estimate(dst, src)`.
    Verificado empiricamente antes do uso.
    """
    from skimage.transform import ThinPlateSplineTransform, warp

    tf = ThinPlateSplineTransform.from_estimate(np.asarray(dst_pts, float),
                                                np.asarray(src_pts, float))
    if not tf:
        raise DesignTransferError("TPS nao convergiu para os pontos dados")
    return warp(layer, tf, output_shape=output_shape, order=order,
                mode="constant", cval=0.0, preserve_range=True)


# ---------------------------------------------------------------------------
# composicao
# ---------------------------------------------------------------------------


def composite(
    base: np.ndarray,
    layer_rgb: np.ndarray,
    layer_alpha: np.ndarray,
    feather: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compoe `layer` sobre `base` e devolve (resultado, mascara_efetiva).

    A mascara efetiva marca todo pixel que PODE ter mudado (alpha > 0). Fora
    dela o resultado e byte-identico a base, por construcao.
    """
    a = np.clip(layer_alpha.astype(np.float64), 0.0, 1.0)
    if feather > 0:
        from skimage.filters import gaussian

        a = gaussian(a, sigma=feather, preserve_range=True)
        a = np.clip(a, 0.0, 1.0)

    touched = a > 0.0
    out = base.astype(np.float64).copy()
    a3 = a[..., None]
    blended = layer_rgb.astype(np.float64) * a3 + out[..., :3] * (1.0 - a3)
    out[..., :3] = np.where(touched[..., None], blended, out[..., :3])
    return np.clip(out, 0, 255).astype(np.uint8), touched


def outside_mask_pixel_difference(
    before: np.ndarray, after: np.ndarray, mask: np.ndarray
) -> int:
    """Numero de pixels que mudaram FORA da mascara. Deve ser 0."""
    if before.shape != after.shape:
        raise DesignTransferError("dimensoes divergentes na verificacao")
    diff = np.any(before[..., :3] != after[..., :3], axis=2)
    return int(np.count_nonzero(diff & ~mask))


def overlay_masks(
    base: Image.Image,
    masks: dict[str, np.ndarray],
    colors: dict[str, tuple[int, int, int]] | None = None,
    alpha: float = 0.45,
) -> Image.Image:
    """Overlay visual das mascaras sobre a base, para inspecao humana."""
    colors = colors or {
        "roupa": (0, 160, 255),
        "capa": (255, 80, 200),
        "ornamentos": (255, 210, 0),
    }
    arr = np.array(base.convert("RGBA")).astype(np.float64)
    for name, mask in masks.items():
        if mask is None or not mask.any():
            continue
        c = np.array(colors.get(name, (0, 255, 0)), dtype=np.float64)
        sel = mask.astype(bool)
        arr[sel, :3] = arr[sel, :3] * (1 - alpha) + c * alpha
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


# ---------------------------------------------------------------------------
# variantes
# ---------------------------------------------------------------------------


@dataclass
class TransferResult:
    variant: str
    image: Image.Image
    effective_mask: np.ndarray
    masks: dict[str, np.ndarray]
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    elapsed_s: float = 0.0


def _layers_from(source: Image.Image, masks: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    src = np.array(source)
    union = np.zeros(src.shape[:2], dtype=bool)
    for m in masks.values():
        union |= m
    return src[..., :3], union.astype(np.float64)


def run_variant_a(
    base: Image.Image,
    source: Image.Image,
    masks: dict[str, np.ndarray],
    feather: float = 0.0,
) -> TransferResult:
    """A — controle: uma transformacao global para todas as regioes."""
    t0 = time.perf_counter()
    base_arr = np.array(base.convert("RGBA"))
    out_shape = base_arr.shape[:2]

    src_bbox = bbox_of(subject_mask(source))
    dst_bbox = bbox_of(subject_mask(base))

    rgb, union = _layers_from(source, masks)
    w_rgb = warp_affine(rgb.astype(np.float64), src_bbox, dst_bbox, out_shape, order=1)
    w_a = warp_affine(union, src_bbox, dst_bbox, out_shape, order=0)
    w_a = (w_a > 0.5).astype(np.float64)

    img, touched = composite(base_arr, w_rgb, w_a, feather=feather)
    params = {
        "algorithm": "affine_global+alpha_composite",
        "transform": affine_map(src_bbox, dst_bbox),
        "feather": feather,
        "interpolation_order": {"rgb": 1, "alpha": 0},
        "regions": "uniao (sem controle por regiao)",
    }
    result = TransferResult("A", Image.fromarray(img, "RGBA"), touched, masks, params)
    result.metrics["outside_mask_pixel_difference"] = outside_mask_pixel_difference(
        base_arr, img, touched)
    result.metrics["pixels_changed"] = int(np.count_nonzero(touched))
    result.elapsed_s = round(time.perf_counter() - t0, 3)
    return result


def run_variant_b(
    base: Image.Image,
    source: Image.Image,
    masks: dict[str, np.ndarray],
    grid: int = 5,
    feather: float = 0.6,
) -> TransferResult:
    """B — mascaras separadas + TPS por regiao + composicao.

    Cada regiao recebe tratamento conforme sua rigidez: ornamentos (rigid)
    usam transformacao global, para nao terem o formato destruido; capa
    (cloth) e roupa (semi_rigid) usam TPS.
    """
    t0 = time.perf_counter()
    base_arr = np.array(base.convert("RGBA"))
    out_shape = base_arr.shape[:2]

    src_bbox = bbox_of(subject_mask(source))
    dst_bbox = bbox_of(subject_mask(base))
    src_pts = control_points(src_bbox, grid, grid)
    dst_pts = control_points(dst_bbox, grid, grid)

    src = np.array(source)
    rgb = src[..., :3].astype(np.float64)

    per_region: dict[str, Any] = {}
    acc_rgb = np.zeros((*out_shape, 3), dtype=np.float64)
    acc_a = np.zeros(out_shape, dtype=np.float64)

    # ornamentos por ultimo: prioridade de desenho
    for name in ("capa", "roupa", "ornamentos"):
        mask = masks.get(name)
        if mask is None or not mask.any():
            per_region[name] = {"skipped": "mascara vazia"}
            continue
        rigidity = REGION_RIGIDITY[name]
        layer_a = mask.astype(np.float64)
        if rigidity == "rigid":
            w_rgb = warp_affine(rgb, src_bbox, dst_bbox, out_shape, order=1)
            w_a = warp_affine(layer_a, src_bbox, dst_bbox, out_shape, order=0)
            method = "affine_global (peca rigida: formato preservado)"
        else:
            w_rgb = warp_tps(rgb, src_pts, dst_pts, out_shape, order=1)
            w_a = warp_tps(layer_a, src_pts, dst_pts, out_shape, order=0)
            method = f"tps_grid_{grid}x{grid}"
        w_a = (w_a > 0.5).astype(np.float64)
        # regiao desenhada depois sobrescreve a anterior
        sel = w_a > 0
        acc_rgb[sel] = w_rgb[sel]
        acc_a[sel] = 1.0
        per_region[name] = {
            "rigidity": rigidity,
            "method": method,
            "source_pixels": int(np.count_nonzero(mask)),
            "warped_pixels": int(np.count_nonzero(sel)),
        }

    img, touched = composite(base_arr, acc_rgb, acc_a, feather=feather)
    params = {
        "algorithm": "per_region_masks+tps+affine_rigid+alpha_composite",
        "grid": grid,
        "control_points": int(grid * grid),
        "feather": feather,
        "interpolation_order": {"rgb": 1, "alpha": 0},
        "transform": affine_map(src_bbox, dst_bbox),
        "per_region": per_region,
        "draw_order": ["capa", "roupa", "ornamentos"],
    }
    result = TransferResult("B", Image.fromarray(img, "RGBA"), touched, masks, params)
    result.metrics["outside_mask_pixel_difference"] = outside_mask_pixel_difference(
        base_arr, img, touched)
    result.metrics["pixels_changed"] = int(np.count_nonzero(touched))
    result.elapsed_s = round(time.perf_counter() - t0, 3)
    return result


# ---------------------------------------------------------------------------
# recipe
# ---------------------------------------------------------------------------


def pixel_sha256(img: Image.Image) -> str:
    """Hash do CONTEUDO de pixels, independente de metadata do arquivo."""
    import hashlib

    arr = np.array(img.convert("RGBA"))
    h = hashlib.sha256()
    h.update(f"{arr.shape}".encode())
    h.update(arr.tobytes())
    return h.hexdigest()


def mask_sha256(mask: np.ndarray) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(f"{mask.shape}".encode())
    h.update(np.packbits(mask.astype(bool)).tobytes())
    return h.hexdigest()


def build_recipe(
    result: TransferResult,
    inputs: dict[str, Path],
    output_path: Path,
    mask_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Recipe reproduzivel. Separa artifact_sha256 de output_pixel_sha256."""
    import platform

    from .hashing import sha256_file

    import numpy as _np
    import PIL as _pil
    import skimage as _sk

    inp = {}
    for role, path in inputs.items():
        p = Path(path)
        inp[role] = {
            "path": str(p),
            "sha256": sha256_file(p) if p.exists() else None,
            "bytes": p.stat().st_size if p.exists() else None,
        }

    recipe: dict[str, Any] = {
        "kind": "design_transfer",
        "status": "experimental",
        "approval_status": "experimental",
        "variant": result.variant,
        "generative": False,
        "inputs": inp,
        "masks": {
            name: {
                "mask_sha256": mask_sha256(m),
                "pixels": int(_np.count_nonzero(m)),
                "rigidity": REGION_RIGIDITY.get(name),
                "path": str(mask_paths[name]) if mask_paths and name in mask_paths else None,
            }
            for name, m in result.masks.items()
        },
        "algorithm": result.params.get("algorithm"),
        "parameters": result.params,
        "resolution": list(result.image.size),
        "metrics": result.metrics,
        "elapsed_s": result.elapsed_s,
        "output": {
            "path": str(output_path),
            "artifact_sha256": sha256_file(output_path) if Path(output_path).exists() else None,
            "output_pixel_sha256": pixel_sha256(result.image),
        },
        "libraries": {
            "numpy": _np.__version__,
            "pillow": _pil.__version__,
            "scikit-image": _sk.__version__,
            "python": platform.python_version(),
        },
        "licenses": LIBRARY_LICENSES,
        "human_review_required": [
            "[HUMAN REVIEW REQUIRED] Avaliacao artistica (STYLE / IDENTITY / "
            "DESIGN_PRESERVATION) e humana. O agente nao escolhe vencedor.",
            "[HUMAN REVIEW REQUIRED] As mascaras sao heuristicas (cor AND "
            "geometria AND alpha), nao segmentacao semantica.",
        ],
    }
    return recipe

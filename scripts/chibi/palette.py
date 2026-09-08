"""Extracao e comparacao de paleta.

A paleta e a ancora OBJETIVA de identidade: se o chibi gerado tem paleta
distante da arte-fonte, houve drift de cor — e isso e mensuravel sem
julgamento artistico.

Conversao sRGB -> CIELAB implementada com numpy puro para evitar dependencia
extra (nao precisamos de scikit-image so para isso).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .imaging import ALPHA_THRESHOLD

#: Ponto branco D65, referencia padrao para conversao sRGB -> XYZ -> Lab.
_D65 = np.array([0.95047, 1.00000, 1.08883])

_RGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    """Remove a curva gamma do sRGB. Entrada e saida em [0, 1]."""
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB [0,255] -> CIELAB. Aceita (N,3) ou (3,)."""
    arr = np.atleast_2d(np.asarray(rgb, dtype=np.float64)) / 255.0
    xyz = srgb_to_linear(arr) @ _RGB_TO_XYZ.T / _D65

    eps = 216 / 24389
    kappa = 24389 / 27
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16) / 116)

    lab = np.stack(
        [
            116 * f[:, 1] - 16,
            500 * (f[:, 0] - f[:, 1]),
            200 * (f[:, 1] - f[:, 2]),
        ],
        axis=1,
    )
    return lab


def delta_e(lab_a: np.ndarray, lab_b: np.ndarray) -> float:
    """Distancia CIE76 (euclidiana em Lab).

    Escolhida sobre CIEDE2000 por ser simples, previsivel e suficiente para
    detectar DRIFT de paleta. Nao e metrica perceptual de precisao.
    """
    return float(np.linalg.norm(np.asarray(lab_a) - np.asarray(lab_b)))


def _kmeans(
    data: np.ndarray, k: int, *, seed: int = 0, iters: int = 50
) -> tuple[np.ndarray, np.ndarray]:
    """k-means com inicializacao k-means++ e seed fixa (reprodutivel)."""
    rng = np.random.default_rng(seed)
    n = len(data)
    k = min(k, n)

    # k-means++: primeiro centro aleatorio, demais proporcionais a D^2.
    centers = [data[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min(
            ((data[:, None, :] - np.array(centers)[None, :, :]) ** 2).sum(axis=2),
            axis=1,
        )
        total = d2.sum()
        probs = d2 / total if total > 0 else np.full(n, 1 / n)
        centers.append(data[rng.choice(n, p=probs)])
    centers = np.array(centers, dtype=np.float64)

    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        dists = ((data[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dists.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for i in range(k):
            member = data[labels == i]
            if len(member):
                centers[i] = member.mean(axis=0)
    return centers, labels


def extract(
    path: Path,
    *,
    n_colors: int = 8,
    max_samples: int = 20000,
    seed: int = 0,
) -> dict:
    """Extrai a paleta dominante dos pixels opacos de uma imagem.

    Amostragem com seed fixa => resultado reprodutivel para a mesma entrada.
    """
    img = Image.open(path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]
    pixels = arr[:, :, :3][alpha > ALPHA_THRESHOLD]

    if len(pixels) == 0:
        return {
            "source": path.name,
            "n_colors": 0,
            "colors": [],
            "note": "nenhum pixel opaco encontrado",
        }

    rng = np.random.default_rng(seed)
    if len(pixels) > max_samples:
        pixels = pixels[rng.choice(len(pixels), max_samples, replace=False)]

    data = pixels.astype(np.float64)
    centers, labels = _kmeans(data, n_colors, seed=seed)

    counts = np.bincount(labels, minlength=len(centers))
    order = np.argsort(-counts)

    colors = []
    for idx in order:
        if counts[idx] == 0:
            continue
        rgb = [int(round(c)) for c in centers[idx]]
        lab = rgb_to_lab(np.array([rgb]))[0]
        colors.append(
            {
                "hex": "#{:02X}{:02X}{:02X}".format(*rgb),
                "rgb": rgb,
                "lab": [round(float(v), 2) for v in lab],
                "weight": round(float(counts[idx] / counts.sum()), 4),
            }
        )

    return {
        "source": path.name,
        "n_colors": len(colors),
        "sampled_pixels": int(len(pixels)),
        "method": "kmeans++ (seed fixa)",
        "seed": seed,
        "colors": colors,
    }


def compare(palette_a: dict, palette_b: dict) -> dict:
    """Compara duas paletas por pareamento guloso de cor mais proxima.

    Usado pelo gate PALETTE_VALID para detectar drift de cor entre a
    arte-fonte e o chibi gerado.
    """
    colors_a = palette_a.get("colors", [])
    colors_b = palette_b.get("colors", [])
    if not colors_a or not colors_b:
        return {"comparable": False, "reason": "paleta vazia"}

    labs_b = [np.array(c["lab"]) for c in colors_b]
    distances: list[float] = []
    pairs = []
    for ca in colors_a:
        lab_a = np.array(ca["lab"])
        dists = [delta_e(lab_a, lb) for lb in labs_b]
        best = int(np.argmin(dists))
        distances.append(dists[best])
        pairs.append(
            {
                "a": ca["hex"],
                "b": colors_b[best]["hex"],
                "delta_e": round(dists[best], 2),
            }
        )

    # Media ponderada pelo peso da cor: dominantes importam mais.
    weights = np.array([c.get("weight", 1.0) for c in colors_a])
    weights = weights / weights.sum() if weights.sum() else weights

    return {
        "comparable": True,
        "mean_distance": round(float(np.average(distances, weights=weights)), 2),
        "max_distance": round(float(max(distances)), 2),
        "pairs": pairs,
    }

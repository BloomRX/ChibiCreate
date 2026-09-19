"""Fixture sintetico: personagem com paleta OPOSTA a da waifu_001.

Nao e arte e nao pretende ser: e um alvo geometrico para provar que o motor
de segmentacao nao depende das cores da waifu_001.

Inversoes deliberadas em relacao a waifu_001:

| aspecto            | waifu_001              | sintetica              |
|--------------------|------------------------|------------------------|
| tecido da capa     | escuro e FRIO (R-B<0)  | escuro e QUENTE (R-B>0)|
| pernas/meias       | escuro e QUENTE        | escuro e FRIO          |
| cabelo             | escuro neutro          | CLARO                  |
| cor de destaque    | dourada                | ciano/prateada         |
| pele               | clara e quente         | clara e rosada         |
| silhueta           | alta e estreita        | baixa e larga          |

Se o motor tiver qualquer numero da waifu_001 embutido, ele falha aqui.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# paleta, deliberadamente diferente
BACKGROUND = (250, 250, 250)
SKIN = (245, 205, 215)        # clara, rosada
HAIR = (235, 230, 120)        # CLARA (a da waifu e escura)
CLOAK = (60, 44, 30)          # escura e QUENTE (R > B)
SLEEVE = (66, 48, 32)         # idem
TORSO = (58, 42, 28)          # idem
LEGS = (30, 40, 62)           # escura e FRIA (R < B)  -> oposto da waifu
ACCENT = (90, 230, 235)       # ciano (a da waifu e dourada)
SHOE = (40, 46, 60)

W, H = 400, 520


def make_synthetic(size: tuple[int, int] = (W, H)) -> Image.Image:
    """Personagem sintetica, baixa e larga, RGBA com alpha real."""
    w, h = size
    arr = np.zeros((h, w, 4), dtype=np.uint8)

    def rect(x0, y0, x1, y1, color):
        arr[int(y0):int(y1), int(x0):int(x1), :3] = color
        arr[int(y0):int(y1), int(x0):int(x1), 3] = 255

    cx = w // 2

    # cabeca grande (proporcao chibi) — CLARA, ao contrario da waifu
    rect(cx - 70, 30, cx + 70, 150, HAIR)
    rect(cx - 45, 60, cx + 45, 145, SKIN)          # rosto

    # tronco vestido: estreito no alto, alargando
    rect(cx - 34, 155, cx + 34, 300, TORSO)

    # mangas largas, laterais e BEM abaixo da linha dos ombros, para que a
    # faixa anatomica generica (shoulder_top) as alcance sem calibracao
    rect(cx - 130, 215, cx - 40, 330, SLEEVE)
    rect(cx + 40, 215, cx + 130, 330, SLEEVE)

    # capa dos dois lados, comecando abaixo das mangas e descendo ate a base
    rect(cx - 150, 345, cx - 30, 500, CLOAK)
    rect(cx + 30, 345, cx + 150, 500, CLOAK)

    # pernas escuras e FRIAS (invertido em relacao a waifu)
    rect(cx - 28, 300, cx - 4, 470, LEGS)
    rect(cx + 4, 300, cx + 28, 470, LEGS)

    # ornamentos em cor de destaque ciano
    rect(cx - 30, 168, cx + 30, 182, ACCENT)       # gola
    rect(cx - 110, 210, cx - 60, 224, ACCENT)      # ombreira esq
    rect(cx + 60, 210, cx + 110, 224, ACCENT)      # ombreira dir
    rect(cx - 26, 330, cx - 6, 344, ACCENT)        # coxa esq
    rect(cx + 6, 330, cx + 26, 344, ACCENT)        # coxa dir

    # calcado
    rect(cx - 32, 470, cx - 2, 500, SHOE)
    rect(cx + 2, 470, cx + 32, 500, SHOE)
    rect(cx - 30, 478, cx - 6, 488, ACCENT)
    rect(cx + 6, 478, cx + 30, 488, ACCENT)

    # maos
    rect(cx - 138, 330, cx - 108, 356, SKIN)
    rect(cx + 108, 330, cx + 138, 356, SKIN)

    return Image.fromarray(arr, "RGBA")


def synthetic_profile() -> dict:
    """Override plausivel para a sintetica — usado para testar isolamento."""
    return {
        "id": "synthetic_002",
        "color_hints": {"accent_rgb": list(ACCENT), "accent_tolerance": 90},
        "thresholds": {"leg_left": 0.30, "leg_right": 0.70},
        "notes": "fixture sintetico; nada aqui vem da waifu_001",
    }


__all__ = ["make_synthetic", "synthetic_profile", "ACCENT", "CLOAK", "LEGS",
           "HAIR", "SKIN", "W", "H"]

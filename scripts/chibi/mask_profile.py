"""Perfis de segmentacao por personagem.

Separa TRES coisas que estavam misturadas em `design_masks.py`:

* **GLOBAL**   — algoritmo valido para qualquer personagem. Nao contem
  nenhum numero medido na waifu_001. Quando um parametro e necessario, ele
  e DERIVADO da propria imagem (Otsu, percentis, caixa do sujeito).
* **CHARACTER-SPECIFIC** — calibracao de UMA personagem, declarada em
  `characters/<id>/masks.yaml`. Opcional: sem o arquivo, vale o generico.
* **REGIONAL** — o que pertence a uma peca (rigidez, ordem de desenho).

Regra que este modulo existe para garantir: **os valores da waifu_001 nunca
sao default global**. Uma personagem sem override e segmentada apenas pela
estrategia generica, e cada parametro carrega sua PROCEDENCIA (`derived` ou
`override`) para que isso seja verificavel — e testavel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# REGIONAL — pertence a peca, nao a personagem
# ---------------------------------------------------------------------------

#: Rigidez de cada peca. E propriedade do TIPO de peca (ornamento e rigido em
#: qualquer personagem), nao de uma personagem especifica.
DEFAULT_RIGIDITY: dict[str, str] = {
    "torso": "semi_rigid",
    "mangas": "cloth",
    "capa_esquerda": "cloth",
    "capa_direita": "cloth",
    "ornamentos": "rigid",
    "inferiores": "rigid",
}

#: Estrategia de segmentacao por peca. Nomes de algoritmo, nao numeros.
DEFAULT_STRATEGY: dict[str, str] = {
    "torso": "central_fabric",
    "mangas": "lateral_fabric",
    "capa_esquerda": "fabric_side_left",
    "capa_direita": "fabric_side_right",
    "ornamentos": "accent_color",
    "inferiores": "accent_color_low",
}

#: Peca que reivindica pixels antes das outras (o ouro define o design).
DEFAULT_PRIORITY: tuple[str, ...] = ("inferiores", "ornamentos")


# ---------------------------------------------------------------------------
# GLOBAL — estrutura, sem numeros de personagem
# ---------------------------------------------------------------------------

#: Fracoes ESTRUTURAIS, validas para qualquer bipede em pose frontal de corpo
#: inteiro. Nao foram calibradas na waifu_001: descrevem anatomia generica e
#: sao propositalmente conservadoras. Qualquer personagem pode sobrescreve-las.
STRUCTURAL_ANATOMY: dict[str, float] = {
    # a cabeca ocupa a porcao superior; chibi tem cabeca maior, por isso a
    # faixa e ampla e serve so como semente, nao como recorte final
    "head_bottom": 0.20,
    # cabelo nao costuma passar da metade do corpo
    "hair_max_bottom": 0.50,
    # ombros logo abaixo da cabeca
    "shoulder_top": 0.20,
    # quadril aproximadamente na metade
    "hip": 0.50,
    # calcado no ultimo decimo
    "shoe_top": 0.90,
}


@dataclass
class DerivedParams:
    """Parametros calculados A PARTIR DA IMAGEM, nunca fixados no codigo."""

    dark_max: float
    cool_max: float
    warm_min: float
    waist: float
    leg_left: float
    leg_right: float
    torso_half_width: float
    provenance: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, float]:
        return {
            "dark_max": self.dark_max,
            "cool_max": self.cool_max,
            "warm_min": self.warm_min,
            "waist": self.waist,
            "leg_left": self.leg_left,
            "leg_right": self.leg_right,
            "torso_half_width": self.torso_half_width,
        }


def derive_params(
    rgb: np.ndarray, subject: np.ndarray, bbox: tuple[int, int, int, int]
) -> DerivedParams:
    """Deriva todos os limiares da propria arte.

    Nenhum valor da waifu_001 entra aqui. Se a derivacao nao for possivel
    (por exemplo, sem tecido escuro), cai em fracoes estruturais neutras.
    """
    from skimage.filters import threshold_otsu

    l, t, r, b = bbox
    h, w = b - t, r - l
    prov: dict[str, str] = {}

    # --- luminancia: Otsu sobre o sujeito separa tecido escuro do resto
    lum = rgb.max(axis=2)[subject]
    try:
        dark_max = float(threshold_otsu(lum))
        prov["dark_max"] = "derived:otsu_luminance"
    except Exception:  # pragma: no cover - imagem degenerada
        dark_max = float(np.percentile(lum, 35))
        prov["dark_max"] = "derived:percentile_fallback"

    dark = (rgb.max(axis=2) < dark_max) & subject

    # --- eixo cromatico R-B: separa tecido frio de tecido quente.
    # Os limiares saem dos percentis da PROPRIA distribuicao, nao de numeros
    # fixos. Uma personagem de roupa quente e pele fria inverte os sinais
    # sozinha, porque os percentis acompanham os dados.
    if int(dark.sum()) > 64:
        rb = (rgb[..., 0].astype(int) - rgb[..., 2].astype(int))[dark]
        p40 = float(np.percentile(rb, 40))
        p70 = float(np.percentile(rb, 70))
        if p70 > p40:
            # distribuicao com espalhamento: os percentis separam os materiais
            cool_max, warm_min = p40, p70
            prov["cool_max"] = "derived:percentile40_rb"
            prov["warm_min"] = "derived:percentile70_rb"
        else:
            # Distribuicao concentrada (p40 == p70): quase todo o tecido tem o
            # mesmo tom. Separar por percentil aqui cortaria a peca principal
            # ao meio. O corte vai para a MEDIANA inclusiva, e o "quente"
            # comeca so acima dela — assim o material dominante conta como
            # tecido em vez de ser descartado.
            med = float(np.median(rb))
            cool_max, warm_min = med, med + 1.0
            prov["cool_max"] = "derived:median_rb_degenerate"
            prov["warm_min"] = "derived:median_rb_degenerate"
    else:
        cool_max, warm_min = 0.0, 1.0
        prov["cool_max"] = prov["warm_min"] = "derived:insufficient_data"

    # --- cintura: MINIMO do perfil vertical do tecido frio. E um metodo
    # generico (procurar o estrangulamento), nao a constante 0.52.
    cool = dark & ((rgb[..., 0].astype(int) - rgb[..., 2].astype(int)) <= cool_max)
    waist = _find_waist(cool, bbox)
    prov["waist"] = "derived:min_cool_fabric_profile"

    # --- colunas das pernas: onde ha sujeito na faixa baixa, excluindo o que
    # se espalha pelo chao (percentis laterais, nao min/max absolutos).
    leg_left, leg_right = _leg_columns(subject, bbox)
    prov["leg_left"] = prov["leg_right"] = "derived:lower_subject_percentiles"

    # --- meia-largura do tronco: medida no topo do torso vestido.
    torso_half = _torso_half_width(cool, bbox)
    prov["torso_half_width"] = "derived:collar_width"

    return DerivedParams(dark_max, cool_max, warm_min, waist,
                         leg_left, leg_right, torso_half, prov)


def _find_waist(cool: np.ndarray, bbox, lo: float = 0.30, hi: float = 0.80) -> float:
    """Altura onde a roupa deixa de ser tronco/manga e vira capa/saia.

    Duas evidencias genericas, nesta ordem:

    1. **Vale** — um estrangulamento real do tecido (faixa com menos area que
       a vizinhanca dos dois lados). E o sinal mais confiavel quando existe:
       corresponde a cintura anatomica.
    2. **Alargamento sustentado** — quando nao ha vale (roupa de largura
       constante), a capa se anuncia por ficar mais larga que o que vem
       acima, em duas faixas seguidas.

    Nao usar o minimo GLOBAL: em silhuetas de manga estreita ele cai na borda
    da janela de busca e devolve um valor sem significado anatomico.
    """
    l, t, r, b = bbox
    h = b - t
    if h <= 0 or not cool.any():
        return STRUCTURAL_ANATOMY["hip"]

    step = max(h // 60, 1)
    fracs: list[float] = []
    areas: list[int] = []
    widths: list[float] = []
    for y in range(t + int(h * lo), t + int(h * hi), step):
        seg = cool[y:y + step]
        fracs.append((y - t) / h)
        areas.append(int(seg.sum()))
        if seg.any():
            xs = np.nonzero(seg.any(axis=0))[0]
            widths.append(float(xs.max() - xs.min() + 1))
        else:
            widths.append(0.0)

    if len(fracs) < 5:
        return STRUCTURAL_ANATOMY["hip"]

    # (1) vale: minimo local estrito, com tecido dos dois lados
    best = None
    for i in range(1, len(areas) - 1):
        a = areas[i]
        if a <= 0:
            continue
        left = max(areas[:i])
        right = max(areas[i + 1:])
        if left <= 0 or right <= 0:
            continue
        if a < left * 0.6 and a < right * 0.6:
            if best is None or a < areas[best]:
                best = i
    if best is not None:
        return round(fracs[best], 4)

    # (2) alargamento sustentado
    for i in range(2, len(widths) - 1):
        prev = [w for w in widths[:i] if w > 0]
        if not prev:
            continue
        base = float(np.median(prev))
        if base > 0 and widths[i] > base * 1.35 and widths[i + 1] > base * 1.35:
            return round(fracs[i], 4)

    return STRUCTURAL_ANATOMY["hip"]


def _leg_columns(subject: np.ndarray, bbox, band: float = 0.75) -> tuple[float, float]:
    """Colunas ocupadas pelas pernas na porcao baixa do sujeito."""
    l, t, r, b = bbox
    h, w = b - t, r - l
    low = subject[t + int(h * band):b, :]
    if not low.any():
        return 0.0, 1.0
    col_counts = low.sum(axis=0).astype(float)
    if col_counts.sum() == 0:
        return 0.0, 1.0
    # o corpo concentra massa; tecido no chao e esparso. Usar a mediana da
    # ocupacao como corte separa perna de barra espalhada.
    strong = np.nonzero(col_counts >= np.median(col_counts[col_counts > 0]))[0]
    if strong.size == 0:
        return 0.0, 1.0
    return (
        round(max((strong.min() - l) / w, 0.0), 4),
        round(min((strong.max() + 1 - l) / w, 1.0), 4),
    )


def _torso_half_width(cool: np.ndarray, bbox) -> float:
    """Meia-largura do tecido no alto do tronco (gola)."""
    l, t, r, b = bbox
    h, w = b - t, r - l
    top = t + int(h * STRUCTURAL_ANATOMY["shoulder_top"])
    bot = t + int(h * (STRUCTURAL_ANATOMY["shoulder_top"] + 0.10))
    seg = cool[top:bot]
    if not seg.any():
        return 0.15
    xs = np.nonzero(seg.any(axis=0))[0]
    return round(max(((xs.max() - xs.min()) / 2.0) / w, 0.02), 4)


# ---------------------------------------------------------------------------
# CHARACTER-SPECIFIC — overrides opcionais
# ---------------------------------------------------------------------------

#: Chaves aceitas em masks.yaml. Qualquer outra e rejeitada, para um erro de
#: digitacao nao virar "parametro ignorado silenciosamente".
OVERRIDE_KEYS = frozenset({
    "strategy", "thresholds", "protected_regions", "region_definitions",
    "geometric_constraints", "color_hints", "connectivity_seeds",
    "manual_hints", "rigidity", "notes",
})

THRESHOLD_KEYS = frozenset({
    "dark_max", "cool_max", "warm_min", "waist", "leg_left", "leg_right",
    "torso_half_width",
})

GEOMETRY_KEYS = frozenset(STRUCTURAL_ANATOMY)


class ProfileError(ValueError):
    pass


@dataclass
class MaskProfile:
    """Perfil de uma personagem. Todos os campos sao OPCIONAIS."""

    character_id: str | None = None
    strategy: dict[str, str] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    protected_regions: dict[str, Any] = field(default_factory=dict)
    region_definitions: dict[str, Any] = field(default_factory=dict)
    geometric_constraints: dict[str, float] = field(default_factory=dict)
    color_hints: dict[str, Any] = field(default_factory=dict)
    connectivity_seeds: dict[str, Any] = field(default_factory=dict)
    manual_hints: dict[str, Any] = field(default_factory=dict)
    rigidity: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    source_path: Path | None = None

    @property
    def is_empty(self) -> bool:
        """Perfil vazio = personagem usa apenas a estrategia generica."""
        return not any([
            self.strategy, self.thresholds, self.protected_regions,
            self.region_definitions, self.geometric_constraints,
            self.color_hints, self.connectivity_seeds, self.manual_hints,
            self.rigidity,
        ])

    @classmethod
    def empty(cls, character_id: str | None = None) -> "MaskProfile":
        return cls(character_id=character_id)

    @classmethod
    def from_dict(cls, data: dict, character_id=None, source_path=None) -> "MaskProfile":
        if data is None:
            return cls.empty(character_id)
        if not isinstance(data, dict):
            raise ProfileError("masks.yaml deve conter um mapeamento")
        unknown = set(data) - OVERRIDE_KEYS - {"id", "character_id"}
        if unknown:
            raise ProfileError(
                f"chaves desconhecidas em masks.yaml: {sorted(unknown)}. "
                f"aceitas: {sorted(OVERRIDE_KEYS)}"
            )
        th = dict(data.get("thresholds") or {})
        bad = set(th) - THRESHOLD_KEYS
        if bad:
            raise ProfileError(f"thresholds desconhecidos: {sorted(bad)}")
        geo = dict(data.get("geometric_constraints") or {})
        badg = set(geo) - GEOMETRY_KEYS
        if badg:
            raise ProfileError(f"geometric_constraints desconhecidos: {sorted(badg)}")
        return cls(
            character_id=data.get("id") or data.get("character_id") or character_id,
            strategy=dict(data.get("strategy") or {}),
            thresholds=th,
            protected_regions=dict(data.get("protected_regions") or {}),
            region_definitions=dict(data.get("region_definitions") or {}),
            geometric_constraints=geo,
            color_hints=dict(data.get("color_hints") or {}),
            connectivity_seeds=dict(data.get("connectivity_seeds") or {}),
            manual_hints=dict(data.get("manual_hints") or {}),
            rigidity=dict(data.get("rigidity") or {}),
            notes=data.get("notes") or "",
            source_path=source_path,
        )


def profile_path_for(character_id: str, root: Path | None = None) -> Path:
    root = root or Path(__file__).resolve().parents[2]
    return root / "characters" / character_id / "masks.yaml"


def load_profile(character_id: str | None, root: Path | None = None) -> MaskProfile:
    """Carrega o perfil. Ausencia de arquivo NAO e erro: e o caso comum."""
    if not character_id:
        return MaskProfile.empty()
    path = profile_path_for(character_id, root)
    if not path.exists():
        return MaskProfile.empty(character_id)
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return MaskProfile.from_dict(data, character_id, path)


# ---------------------------------------------------------------------------
# resolucao: generico + override, com procedencia
# ---------------------------------------------------------------------------


@dataclass
class ResolvedParams:
    """Parametros finais e de onde cada um veio."""

    values: dict[str, float]
    anatomy: dict[str, float]
    strategy: dict[str, str]
    rigidity: dict[str, str]
    provenance: dict[str, str]
    profile: MaskProfile

    def __getitem__(self, key: str) -> float:
        return self.values[key]

    def source_of(self, key: str) -> str:
        return self.provenance.get(key, "unknown")

    @property
    def overridden(self) -> list[str]:
        return sorted(k for k, v in self.provenance.items()
                      if v.startswith("override"))

    @property
    def derived(self) -> list[str]:
        return sorted(k for k, v in self.provenance.items()
                      if v.startswith("derived"))


def resolve_params(derived: DerivedParams, profile: MaskProfile) -> ResolvedParams:
    """Combina derivacao generica com overrides da personagem."""
    values = derived.as_dict()
    prov = dict(derived.provenance)

    for key, val in profile.thresholds.items():
        values[key] = float(val)
        prov[key] = f"override:{profile.character_id or 'profile'}"

    anatomy = dict(STRUCTURAL_ANATOMY)
    for key in anatomy:
        prov.setdefault(key, "structural:generic_anatomy")
    for key, val in profile.geometric_constraints.items():
        anatomy[key] = float(val)
        prov[key] = f"override:{profile.character_id or 'profile'}"

    strategy = dict(DEFAULT_STRATEGY)
    strategy.update(profile.strategy)
    rigidity = dict(DEFAULT_RIGIDITY)
    rigidity.update(profile.rigidity)

    return ResolvedParams(values, anatomy, strategy, rigidity, prov, profile)


def describe(resolved: ResolvedParams) -> str:
    """Relatorio legivel de procedencia — usado no notebook e na revisao."""
    lines = ["parametro            valor      procedencia"]
    for key in sorted(resolved.values):
        lines.append(f"  {key:20}{resolved.values[key]:9.4f}  "
                     f"{resolved.source_of(key)}")
    for key in sorted(resolved.anatomy):
        lines.append(f"  {key:20}{resolved.anatomy[key]:9.4f}  "
                     f"{resolved.source_of(key)}")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_RIGIDITY", "DEFAULT_STRATEGY", "DEFAULT_PRIORITY",
    "STRUCTURAL_ANATOMY", "OVERRIDE_KEYS", "THRESHOLD_KEYS", "GEOMETRY_KEYS",
    "DerivedParams", "MaskProfile", "ProfileError", "ResolvedParams",
    "derive_params", "load_profile", "profile_path_for", "resolve_params",
    "describe",
]

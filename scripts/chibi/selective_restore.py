"""FASE A — restauracao seletiva NAO-GENERATIVA.

Premissa corrigida pelo usuario: o problema da Run 003 e **deriva de design**
(o FLUX redesenhou/simplificou a roupa), nao recusa de seguranca. Trocar de
modelo nao resolve isso. O que resolve e **restringir a edicao a regiao certa**.

A ideia central desta camada e simples e conservadora:

    se uma peca ja esta correta na Run 003, NAO substituir.

Por isso nada aqui redesenha a roupa inteira. Medimos, peca por peca, o quanto
o design se afastou da referencia; so as pecas que realmente derivaram entram
na composicao.

Ordem obrigatoria (nunca pular etapas):

    full_body REAL -> mascara da roupa -> correspondencia REAL<->CHIBI
        -> mascara no espaco da RUN 003 -> deteccao de deriva
        -> restauracao apenas do que derivou

Nenhum modelo generativo participa desta fase.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from . import character_correspondence as cc
from . import mask_engine as me

# ---------------------------------------------------------------------------
# eixos de comparacao
# ---------------------------------------------------------------------------

# Pesos dos sinais que compoem o score de deriva. Sao parametros de TRIAGEM,
# nao verdades esteticas: servem para ordenar o que olhar primeiro, nunca para
# aprovar ou reprovar arte. A aprovacao e humana.
DRIFT_WEIGHTS = {
    "gold_presence": 0.40,   # ornamentos dourados sumindo e o sintoma nº1
    "luminance": 0.25,       # peca clareou/escureceu (perdeu sombreado/volume)
    "saturation": 0.15,      # cor lavada
    "detail": 0.20,          # variancia local: detalhe estrutural achatado
}

# Acima disto a peca entra na lista de candidatas a restauracao. Abaixo, a
# peca e considerada "ja correta na Run 003" e NAO deve ser substituida.
# Configuravel; nao e um julgamento artistico.
DRIFT_THRESHOLD_DEFAULT = 0.25


class RestoreError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# descritores por regiao
# ---------------------------------------------------------------------------


def _rgb_float(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGB"), float)


def _gold_fraction(rgb: np.ndarray, mask: np.ndarray) -> float:
    """Fracao de pixels dourados dentro da mascara.

    Reaproveita o discriminador ja existente em `design_transfer.is_gold`,
    para nao inventar um segundo criterio de "ouro" no projeto.
    """
    from .design_transfer import is_gold

    if not mask.any():
        return 0.0
    return float((is_gold(rgb.astype(np.uint8)) & mask).sum() / mask.sum())


def _detail_score(rgb: np.ndarray, mask: np.ndarray) -> float:
    """Quanta variacao local existe na regiao (proxy de detalhe estrutural).

    Gradiente medio normalizado. Uma peca que perdeu ornamentos, costuras e
    dobras fica visivelmente mais "chapada" — e isso aparece aqui mesmo
    quando a cor media continua igual.
    """
    if not mask.any():
        return 0.0
    lum = rgb.mean(axis=2)
    gy, gx = np.gradient(lum)
    grad = np.hypot(gx, gy)
    return float(grad[mask].mean() / 255.0)


def _saturation(rgb: np.ndarray, mask: np.ndarray) -> float:
    if not mask.any():
        return 0.0
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = np.zeros_like(mx)
    nz = mx > 0
    sat[nz] = (mx[nz] - mn[nz]) / mx[nz]
    return float(sat[mask].mean())


def describe_region(img: Image.Image, mask: np.ndarray) -> dict:
    """Descritores invariantes a ESCALA — obrigatorio aqui.

    A REAL e a CHIBI tem tamanhos e proporcoes diferentes, entao qualquer
    medida em pixels absolutos seria incomparavel. Tudo abaixo e fracao ou
    media dentro da propria mascara.
    """
    rgb = _rgb_float(img)
    if not mask.any():
        return {"pixels": 0, "gold_presence": 0.0, "luminance": 0.0,
                "saturation": 0.0, "detail": 0.0, "empty": True}
    return {
        "pixels": int(mask.sum()),
        "gold_presence": _gold_fraction(rgb, mask),
        "luminance": float(rgb.mean(axis=2)[mask].mean() / 255.0),
        "saturation": _saturation(rgb, mask),
        "detail": _detail_score(rgb, mask),
        "empty": False,
    }


# ---------------------------------------------------------------------------
# deriva
# ---------------------------------------------------------------------------


@dataclass
class RegionDrift:
    name: str
    source: dict
    target: dict
    deltas: dict
    score: float
    drifted: bool
    reason: str

    def as_dict(self) -> dict:
        return {"region": self.name, "score": round(self.score, 4),
                "drifted": self.drifted, "reason": self.reason,
                "source": {k: round(v, 4) if isinstance(v, float) else v
                           for k, v in self.source.items()},
                "target": {k: round(v, 4) if isinstance(v, float) else v
                           for k, v in self.target.items()},
                "deltas": {k: round(v, 4) for k, v in self.deltas.items()}}


def detect_drift(source_img: Image.Image,
                 target_img: Image.Image,
                 source_masks: dict[str, np.ndarray],
                 target_masks: dict[str, np.ndarray],
                 threshold: float = DRIFT_THRESHOLD_DEFAULT,
                 weights: dict | None = None) -> dict[str, RegionDrift]:
    """Compara peca a peca e diz QUAIS derivaram.

    O sinal mais importante e `gold_presence`: ornamentos dourados que somem
    sao o modo de falha classico deste pipeline. Por isso ele tem o maior
    peso e ainda dispara uma razao propria no relatorio.
    """
    w = dict(DRIFT_WEIGHTS if weights is None else weights)
    out: dict[str, RegionDrift] = {}

    for nome in source_masks:
        s = describe_region(source_img, source_masks[nome])
        t = describe_region(target_img, target_masks.get(
            nome, np.zeros(np.array(target_img).shape[:2], bool)))

        if s["empty"]:
            out[nome] = RegionDrift(nome, s, t, {}, 0.0, False,
                                    "peca ausente na referencia — nada a comparar")
            continue
        if t["empty"]:
            out[nome] = RegionDrift(nome, s, t, {}, 1.0, True,
                                    "regiao vazia no alvo apos a transformacao")
            continue

        deltas = {k: abs(s[k] - t[k]) for k in w}
        score = float(sum(w[k] * deltas[k] for k in w) / sum(w.values()))

        # Ouro que sumiu tem tratamento proprio: e o sintoma que motivou
        # esta fase inteira, e some sem mexer muito nas outras medidas.
        perdeu_ouro = (s["gold_presence"] > 0.02
                       and t["gold_presence"] < s["gold_presence"] * 0.5)
        drifted = score >= threshold or perdeu_ouro

        if perdeu_ouro:
            razao = (f"perdeu ornamento dourado: {s['gold_presence']:.1%} "
                     f"-> {t['gold_presence']:.1%}")
        elif not drifted:
            razao = "dentro do limiar — JA CORRETA na Run 003, nao substituir"
        else:
            pior = max(deltas, key=deltas.get)
            razao = f"deriva em {pior} (delta {deltas[pior]:.3f})"

        out[nome] = RegionDrift(nome, s, t, deltas, score, drifted, razao)

    return out


def regions_to_restore(drift: dict[str, RegionDrift]) -> list[str]:
    """So o que realmente derivou. Ordenado pelo pior caso primeiro."""
    return [d.name for d in
            sorted(drift.values(), key=lambda d: -d.score) if d.drifted]


# ---------------------------------------------------------------------------
# composicao seletiva
# ---------------------------------------------------------------------------


@dataclass
class RestoreResult:
    image: Image.Image
    restored: list[str]
    skipped: list[str]
    metrics: dict = field(default_factory=dict)


def selective_restore(target_img: Image.Image,
                      source_img: Image.Image,
                      target_masks: dict[str, np.ndarray],
                      corr: cc.Correspondence,
                      regions: list[str],
                      protected: np.ndarray | None = None,
                      feather: int = 2) -> RestoreResult:
    """Escreve na Run 003 SOMENTE dentro das regioes pedidas.

    A arte da REAL e levada ao espaco da CHIBI pela mesma transformacao ja
    validada na etapa de correspondencia — nao ha segundo alinhamento, nem
    warp arbitrario.

    Fora das mascaras a Run 003 e preservada **byte a byte**: a base e
    copiada e so os pixels da mascara sao sobrescritos. E isso que sustenta
    `outside_mask_pixel_difference == 0`.
    """
    from skimage.transform import warp

    base = np.array(target_img.convert("RGBA")).copy()
    shape = base.shape[:2]

    # arte da REAL reamostrada para o espaco do ALVO
    src = np.array(source_img.convert("RGBA"), float)
    warped_rgba = np.zeros((*shape, 4), float)
    for c in range(4):
        warped_rgba[..., c] = warp(src[..., c], corr.transform,
                                   output_shape=shape, order=1,
                                   mode="constant", cval=0.0,
                                   preserve_range=True)

    aplicado = np.zeros(shape, bool)
    for nome in regions:
        m = target_masks.get(nome)
        if m is None or not m.any():
            continue
        if protected is not None:
            m = m & ~protected          # invariante: nunca tocar protegido
        aplicado |= m

    if feather > 0 and aplicado.any():
        # Borda suave evita costura dura, mas o alpha e reancorado na
        # mascara: nenhum pixel fora dela pode receber peso.
        from scipy.ndimage import gaussian_filter
        alpha = gaussian_filter(aplicado.astype(float), feather)
        alpha = np.clip(alpha, 0.0, 1.0) * aplicado
    else:
        alpha = aplicado.astype(float)

    a3 = alpha[..., None]
    base_f = base.astype(float)
    out = base_f * (1 - a3) + warped_rgba * a3
    # Fora da mascara, devolver os bytes ORIGINAIS (sem ida e volta em float).
    out[~aplicado] = base_f[~aplicado]

    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
    todas = list(target_masks)
    return RestoreResult(
        image=img,
        restored=list(regions),
        skipped=[n for n in todas if n not in regions],
        metrics={"pixels_written": int(aplicado.sum()),
                 "pct_of_target": round(100 * aplicado.sum() / aplicado.size, 3)},
    )


def outside_mask_pixel_difference(before: Image.Image, after: Image.Image,
                                  written: np.ndarray) -> int:
    """Quantos pixels mudaram FORA da area autorizada. Tem que ser 0."""
    a = np.array(before.convert("RGBA"))
    b = np.array(after.convert("RGBA"))
    if a.shape != b.shape:
        raise RestoreError("tamanhos diferentes — comparacao invalida")
    dif = (a != b).any(axis=2)
    return int((dif & ~written).sum())

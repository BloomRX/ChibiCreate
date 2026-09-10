"""Correspondencia geometrica REAL <-> CHIBI.

Problema que este modulo resolve: a mascara da roupa e definida no espaco
geometrico da personagem REAL. A Run 003 e CHIBI — outras proporcoes, outra
escala, outras posicoes. Aplicar a mascara da real diretamente sobre a chibi
e um erro conceitual.

Pipeline correto:

    REAL -> segmentacao -> correspondencia REAL<->CHIBI -> mascara no espaco
    CHIBI -> MASK REVIEW -> warp/composicao

TPS aparece aqui como **transformacao**, nunca como etapa de correspondencia:
ele consome os pares de landmarks, nao os descobre.

Metodo escolhido (ver docs/research/2026-09-09-correspondence.md): landmarks
derivados do CONTORNO, correspondencia esparsa por papel anatomico, e
transformacao TPS/afim estimada sobre os pares validos.

Nao ha detector de pose neste modulo. Todos os estimadores de pose para
personagens ilustradas que encontramos sao redes neurais treinadas
(bizarre-pose-estimator, Khungurn et al.), o que contraria a restricao de
metodos 2D baratos e explicaveis — e nenhum deles conhece proporcao chibi.

Landmarks podem vir de quatro fontes, nesta ordem de precedencia:

  1. `manual`  — revisados por humano (`characters/<id>/landmarks.yaml`)
  2. `config`  — declarados na configuracao da personagem
  3. `derived` — extraidos do contorno da silhueta (padrao)
  4. ausentes  — correspondencia PARCIAL e explicitamente suportada
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .design_transfer import bbox_of, load_rgba

# ---------------------------------------------------------------------------
# vocabulario de landmarks
# ---------------------------------------------------------------------------

#: Landmarks reconhecidos. NENHUM e obrigatorio: uma personagem sem pernas
#: visiveis, de saia longa ou com capa fechada simplesmente nao produz alguns.
#: A correspondencia trabalha com o subconjunto presente nas DUAS imagens.
LANDMARK_NAMES = (
    "top_of_head",
    "chin",
    "neck",
    "shoulder_left", "shoulder_right",
    "elbow_left", "elbow_right",
    "wrist_left", "wrist_right",
    "waist",
    "hip_left", "hip_right",
    "knee_left", "knee_right",
    "ankle_left", "ankle_right",
    "silhouette_bottom",
)

#: Minimo de pares para cada tipo de transformacao.
MIN_PAIRS = {"similarity": 2, "affine": 3, "tps": 4}


class CorrespondenceError(RuntimeError):
    pass


@dataclass
class Landmark:
    name: str
    x: float
    y: float
    source: str = "derived"      # derived | config | manual
    confidence: float = 1.0

    def as_xy(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass
class LandmarkSet:
    """Landmarks de UMA imagem, com a caixa do sujeito para normalizar."""

    landmarks: dict[str, Landmark] = field(default_factory=dict)
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    image_size: tuple[int, int] = (0, 0)
    subject: np.ndarray | None = None

    def __contains__(self, name: str) -> bool:
        return name in self.landmarks

    def __getitem__(self, name: str) -> Landmark:
        return self.landmarks[name]

    def names(self) -> list[str]:
        return sorted(self.landmarks)

    def add(self, lm: Landmark) -> None:
        self.landmarks[lm.name] = lm

    def normalized(self, name: str) -> tuple[float, float]:
        """Posicao em fracao da caixa do sujeito — comparavel entre escalas."""
        l, t, r, b = self.bbox
        lm = self.landmarks[name]
        return ((lm.x - l) / max(r - l, 1), (lm.y - t) / max(b - t, 1))


# ---------------------------------------------------------------------------
# silhueta
# ---------------------------------------------------------------------------


def silhouette(image: Image.Image) -> np.ndarray:
    """Silhueta real do personagem.

    Cuidado necessario: em `full_body.png` o canal alpha e um RETANGULO
    solido (568 px de largura em toda linha) — usa-lo como silhueta daria um
    perfil constante e landmarks sem sentido. Quando o alpha e degenerado
    assim, a silhueta vem da cor de fundo lisa.
    """
    arr = np.array(image.convert("RGBA"))
    rgb = arr[..., :3].astype(int)
    alpha = arr[..., 3]
    inside = alpha > 128
    if not inside.any():
        raise CorrespondenceError("imagem totalmente transparente")

    # o alpha e util? um alpha "recortado" varia de largura entre as linhas
    rows = np.nonzero(inside.any(axis=1))[0]
    widths = [int(inside[y].sum()) for y in rows[:: max(len(rows) // 40, 1)]]
    alpha_util = len(set(widths)) > 3

    if alpha_util:
        return inside

    # alpha degenerado: separar por cor de fundo uniforme
    sample = rgb[inside][::97]
    if sample.size == 0:
        return inside
    vals, counts = np.unique(sample.reshape(-1, 3), axis=0, return_counts=True)
    bg = vals[int(np.argmax(counts))]
    body = inside & (np.abs(rgb - bg).sum(axis=2) > 30)
    return body if body.any() else inside


def width_profile(sil: np.ndarray, bbox, bins: int = 64) -> np.ndarray:
    """Largura da silhueta por faixa, em fracao da largura total."""
    l, t, r, b = bbox
    h, w = b - t, r - l
    out = np.zeros(bins)
    step = max(h // bins, 1)
    for i in range(bins):
        y0 = t + int(h * i / bins)
        seg = sil[y0:y0 + step]
        if seg.any():
            xs = np.nonzero(seg.any(axis=0))[0]
            out[i] = (xs.max() - xs.min() + 1) / max(w, 1)
    return out


def _row_extent(sil: np.ndarray, y: int) -> tuple[int, int] | None:
    xs = np.nonzero(sil[y])[0]
    if xs.size == 0:
        return None
    return int(xs.min()), int(xs.max())


# ---------------------------------------------------------------------------
# deteccao de landmarks a partir do contorno
# ---------------------------------------------------------------------------


def derive_landmarks(image: Image.Image, sil: np.ndarray | None = None) -> LandmarkSet:
    """Landmarks extraidos do CONTORNO. Correspondencia parcial e normal.

    Nada aqui e especifico da waifu_001: sao propriedades do perfil de
    largura (onde a silhueta se alarga, estrangula, se divide em duas pernas).
    Landmark que nao puder ser identificado com seguranca simplesmente NAO e
    emitido — melhor ausente do que inventado.
    """
    sil = silhouette(image) if sil is None else sil
    ys, xs = np.nonzero(sil)
    if ys.size == 0:
        raise CorrespondenceError("silhueta vazia")
    bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    l, t, r, b = bbox
    h, w = b - t, r - l
    ls = LandmarkSet(bbox=bbox, image_size=image.size, subject=sil)

    def frac_y(f: float) -> int:
        return int(t + h * f)

    # topo da cabeca e base: extremos do contorno, sempre disponiveis
    top_row = _row_extent(sil, t)
    if top_row:
        ls.add(Landmark("top_of_head", (top_row[0] + top_row[1]) / 2, t))
    bot_row = _row_extent(sil, b - 1)
    if bot_row:
        ls.add(Landmark("silhouette_bottom",
                        (bot_row[0] + bot_row[1]) / 2, b - 1))

    prof = width_profile(sil, bbox, bins=64)

    # NOTA IMPORTANTE sobre o que NAO e detectavel pelo contorno.
    #
    # Pescoco, cintura, quadril, cotovelo e punho NAO sao emitidos por
    # heuristica de silhueta. Medido na waifu_001: o perfil de largura sobe
    # de forma quase monotona da cabeca ate a base (0.17 -> 0.52 -> 1.0), sem
    # estrangulamento no pescoco — cabelo longo funde cabeca e ombros — e sem
    # cintura visivel, porque a capa cobre o contorno lateral.
    #
    # Uma versao anterior tentava adivinhar esses pontos e colocava 'neck' na
    # ponta do chifre, 'waist' na altura das costelas, 'hip' na borda da capa
    # e os tornozelos na barra do manto. Landmark errado e pior que landmark
    # ausente: ele arrasta a transformacao inteira.
    #
    # Portanto so sao derivados os pontos que o CONTORNO realmente sustenta:
    # extremos verticais e a linha de maior largura dos ombros/manto. Os
    # demais entram por `landmarks.yaml` (config ou revisao humana), e a
    # correspondencia parcial e um caminho normal, nao uma falha.

    # linha de maior largura na METADE SUPERIOR: em pose frontal de corpo
    # inteiro corresponde a extensao dos ombros/mangas. Nao e o ombro
    # anatomico, e a extremidade lateral — util para ancorar escala em X.
    half = int(64 * 0.55)
    upper = prof[:half]
    if upper.size and upper.max() > 0:
        i = int(np.argmax(upper))
        y = frac_y(i / 64)
        ext = _row_extent(sil, y)
        if ext and (ext[1] - ext[0]) > w * 0.15:
            ls.add(Landmark("shoulder_left", ext[0], y, confidence=0.45))
            ls.add(Landmark("shoulder_right", ext[1], y, confidence=0.45))

    # tornozelos: na base, se a silhueta se divide em duas pernas
    ankles = _split_legs(sil, bbox)
    if ankles:
        (lx, ly), (rx, ry) = ankles
        # duas pernas plausiveis: separadas, porem nao nas bordas extremas
        # (a barra de um manto tambem se divide em dois blocos largos)
        span = abs(rx - lx)
        if 0.03 * w < span < 0.45 * w:
            ls.add(Landmark("ankle_left", lx, ly, confidence=0.4))
            ls.add(Landmark("ankle_right", rx, ry, confidence=0.4))

    return ls


def _split_legs(sil: np.ndarray, bbox, search=(0.80, 0.99), max_leg_frac=0.18):
    """Duas pernas separadas na porcao baixa? Se nao houver, devolve None.

    Exige que CADA bloco seja estreito (<= `max_leg_frac` da largura). Sem
    isso, a barra de um manto — que tambem se divide em dois blocos ao redor
    dos pes — e confundida com as pernas, e os tornozelos vao parar na ponta
    do tecido. Medido na waifu_001: os blocos do manto ocupam ~0.30 da
    largura cada, enquanto uma perna calcada fica bem abaixo disso.
    """
    from skimage.measure import label

    l, t, r, b = bbox
    h, w = b - t, r - l
    for f in np.linspace(search[0], search[1], 12):
        y = int(t + h * f)
        if y >= sil.shape[0]:
            continue
        lab = label(sil[y].astype(int))
        if int(lab.max()) != 2:
            continue
        blocks = []
        for i in (1, 2):
            xs = np.nonzero(lab == i)[0]
            blocks.append((xs.size, float(xs.mean()), float(y)))
        if not all(size <= max_leg_frac * w for size, _, _ in blocks):
            continue
        blocks.sort(key=lambda t_: t_[1])
        (_, lx, ly), (_, rx, ry) = blocks
        # Duas pernas sao aproximadamente SIMETRICAS em torno do eixo do
        # corpo. Medido na waifu_001, o par que sobrevive ao filtro de
        # largura e (canto do manto, pe) — centros em 0.25 e 0.50, cujo ponto
        # medio cai em 0.37, longe do eixo. Exigir simetria descarta esse
        # falso par em vez de emitir tornozelos na barra do tecido.
        axis = l + w / 2.0
        meio = (lx + rx) / 2.0
        if abs(meio - axis) > 0.08 * w:
            continue
        return (lx, ly), (rx, ry)
    return None


# ---------------------------------------------------------------------------
# landmarks vindos de configuracao / revisao manual
# ---------------------------------------------------------------------------


def landmarks_path_for(character_id: str, root: Path | None = None) -> Path:
    root = root or Path(__file__).resolve().parents[2]
    return root / "characters" / character_id / "landmarks.yaml"


def load_landmark_overrides(character_id: str | None,
                            root: Path | None = None) -> dict[str, dict]:
    """Landmarks declarados/revisados. Ausencia NAO e erro."""
    if not character_id:
        return {}
    path = landmarks_path_for(character_id, root)
    if not path.exists():
        return {}
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    out: dict[str, dict] = {}
    for role in ("source", "target"):
        block = data.get(role) or {}
        bad = set(block) - set(LANDMARK_NAMES)
        if bad:
            raise CorrespondenceError(
                f"landmarks desconhecidos em {role}: {sorted(bad)}")
        out[role] = block
    return out


def apply_overrides(ls: LandmarkSet, overrides: dict,
                    source: str = "manual") -> LandmarkSet:
    """Sobrescreve/acrescenta landmarks revisados por humano.

    Aceita coordenadas absolutas (`x`, `y`) ou normalizadas pela caixa do
    sujeito (`nx`, `ny`) — normalizado e preferivel, porque sobrevive a
    mudanca de resolucao.
    """
    l, t, r, b = ls.bbox
    w, h = max(r - l, 1), max(b - t, 1)
    for name, spec in (overrides or {}).items():
        # Nome fora de LANDMARK_NAMES e erro, nao aviso: um 'shoulder_lft'
        # digitado errado no YAML seria silenciosamente ignorado e o par
        # simplesmente nao existiria, degradando a transformacao sem que
        # ninguem percebesse.
        if name not in LANDMARK_NAMES:
            raise CorrespondenceError(
                f"landmark desconhecido: {name!r}. "
                f"Nomes validos: {', '.join(LANDMARK_NAMES)}")
        if spec is None:
            ls.landmarks.pop(name, None)     # remocao explicita
            continue
        if "nx" in spec or "ny" in spec:
            x = l + float(spec.get("nx", 0.5)) * w
            y = t + float(spec.get("ny", 0.5)) * h
        else:
            x, y = float(spec["x"]), float(spec["y"])
        ls.add(Landmark(name, x, y, source=source,
                        confidence=float(spec.get("confidence", 1.0))))
    return ls


# ---------------------------------------------------------------------------
# correspondencia
# ---------------------------------------------------------------------------


@dataclass
class Correspondence:
    """Pares REAL<->CHIBI e a transformacao estimada."""

    source: LandmarkSet
    target: LandmarkSet
    pairs: list[str]
    kind: str
    transform: Any = None
    confidence: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def n_pairs(self) -> int:
        return len(self.pairs)

    def src_points(self) -> np.ndarray:
        return np.array([self.source[n].as_xy() for n in self.pairs], float)

    def dst_points(self) -> np.ndarray:
        return np.array([self.target[n].as_xy() for n in self.pairs], float)

    def residuals(self) -> dict:
        """Erro de reprojecao por par, em pixels do ALVO.

        `self.transform` e a INVERSA (alvo -> origem), entao medimos onde cada
        landmark do alvo cai na origem e comparamos com o par correspondente.
        Sem isto, `confidence` seria a unica evidencia numerica — e ela e
        agregada demais para mostrar QUAL ponto esta ruim.

        ATENCAO ao interpretar: o TPS **interpola** os landmarks exatamente,
        entao o residual dele e ~0 por construcao. Residual zero em TPS NAO
        significa correspondencia boa — significa apenas que a spline passou
        pelos pontos que voce deu. Se os landmarks estiverem errados, o
        residual continua zero e a deformacao continua errada. Para afim e
        similaridade (que sao sobre-determinadas) o numero e informativo.
        Quem valida o TPS e o olho, no overlay.
        """
        if not self.pairs:
            return {"per_landmark": {}, "max": None, "mean": None, "rmse": None}
        dst = np.array([self.target[n].as_xy() for n in self.pairs], float)
        src = np.array([self.source[n].as_xy() for n in self.pairs], float)
        try:
            proj = np.asarray(self.transform(dst), float)
        except Exception:                          # pragma: no cover
            return {"per_landmark": {}, "max": None, "mean": None,
                    "rmse": None, "error": "transformacao nao inversivel"}
        err = np.linalg.norm(proj - src, axis=1)
        return {
            "per_landmark": {n: round(float(e), 3)
                             for n, e in zip(self.pairs, err)},
            "max": round(float(err.max()), 3),
            "mean": round(float(err.mean()), 3),
            "rmse": round(float(np.sqrt((err ** 2).mean())), 3),
            "unit": "pixels_no_espaco_da_origem",
        }

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "n_pairs": self.n_pairs,
            "pairs": list(self.pairs),
            "confidence": round(self.confidence, 4),
            "residuals": self.residuals(),
            "source_landmarks": {
                n: {"x": round(self.source[n].x, 2),
                    "y": round(self.source[n].y, 2),
                    "origin": self.source[n].source}
                for n in self.source.names()},
            "target_landmarks": {
                n: {"x": round(self.target[n].x, 2),
                    "y": round(self.target[n].y, 2),
                    "origin": self.target[n].source}
                for n in self.target.names()},
            "source_bbox": list(self.source.bbox),
            "target_bbox": list(self.target.bbox),
            "diagnostics": self.diagnostics,
        }


def _corner_anchors(ls: LandmarkSet) -> list[tuple[float, float]]:
    """Cantos da caixa do sujeito, para ancorar a transformacao."""
    l, t, r, b = ls.bbox
    return [(l, t), (r - 1, t), (l, b - 1), (r - 1, b - 1)]


def build_correspondence(
    source: LandmarkSet,
    target: LandmarkSet,
    kind: str = "auto",
    use_bbox_anchors: bool = True,
) -> Correspondence:
    """Pareia landmarks presentes NAS DUAS imagens e estima a transformacao.

    Correspondencia parcial e suportada por construcao: o par so entra se o
    landmark existir dos dois lados. Se sobrarem poucos pares, a
    transformacao degrada para afim ou similaridade em vez de falhar — e
    isso fica registrado em `kind` e `confidence`.
    """
    pairs = [n for n in LANDMARK_NAMES if n in source and n in target]

    if kind == "auto":
        if len(pairs) >= MIN_PAIRS["tps"]:
            kind = "tps"
        elif len(pairs) >= MIN_PAIRS["affine"]:
            kind = "affine"
        else:
            kind = "similarity"

    src = [source[n].as_xy() for n in pairs]
    dst = [target[n].as_xy() for n in pairs]

    # ancoras nos cantos: evitam que o TPS exploda fora da regiao coberta
    # pelos landmarks. Sao correspondencia de ENQUADRAMENTO, nao anatomica.
    n_anchors = 0
    if use_bbox_anchors and kind == "tps":
        sa, ta = _corner_anchors(source), _corner_anchors(target)
        src.extend(sa)
        dst.extend(ta)
        n_anchors = len(sa)

    src_arr = np.array(src, float)
    dst_arr = np.array(dst, float)

    # Pontos duplicados no ALVO quebram o TPS: o sistema linear fica singular
    # e a estimativa nao converge. Isso acontece de verdade — numa chibi de
    # teste, `shoulder_left/right` e `top_of_head` cairam todos na mesma
    # linha do topo da caixa, colidindo com as ancoras de canto.
    _, keep = np.unique(dst_arr.round(3), axis=0, return_index=True)
    if len(keep) < len(dst_arr):
        keep = np.sort(keep)
        src_arr, dst_arr = src_arr[keep], dst_arr[keep]
        n_pares_validos = int(np.sum(keep < len(pairs)))
        pairs = [p_ for i, p_ in enumerate(pairs) if i in set(keep.tolist())]
        diag_dup = len(dst) - len(keep)
    else:
        diag_dup = 0

    # A degradacao precisa acontecer DEPOIS de descartar duplicatas: sobrando
    # poucos pontos distintos, insistir em TPS so produz erro. Cair para afim
    # ou similaridade e melhor que falhar a etapa inteira.
    tf = None
    tentativas = [k for k in ("tps", "affine", "similarity")
                  if MIN_PAIRS[k] <= len(dst_arr)]
    ordem = [kind] + [k for k in reversed(tentativas) if k != kind]
    erros = []
    for tentativa in ordem:
        if len(dst_arr) < MIN_PAIRS[tentativa]:
            continue
        try:
            tf = _estimate(tentativa, src_arr, dst_arr)
            kind = tentativa
            break
        except CorrespondenceError as exc:
            erros.append(f"{tentativa}: {exc}")
    if tf is None:
        raise CorrespondenceError(
            "nenhuma transformacao convergiu — " + "; ".join(erros))

    conf = _confidence(pairs, source, target, tf, kind)

    diag = {
        "n_anchors": n_anchors,
        "duplicate_points_dropped": diag_dup,
        "fallbacks_tried": erros,
        "landmarks_source_only": sorted(set(source.names()) - set(pairs)),
        "landmarks_target_only": sorted(set(target.names()) - set(pairs)),
        "partial": len(pairs) < len(LANDMARK_NAMES),
    }
    return Correspondence(source, target, pairs, kind, tf, conf, diag)


def _estimate(kind: str, src: np.ndarray, dst: np.ndarray):
    """Estima a transformacao INVERSA (destino -> origem), que e o que
    `skimage.transform.warp` consome."""
    from skimage.transform import (
        AffineTransform,
        SimilarityTransform,
        ThinPlateSplineTransform,
    )

    if kind == "tps":
        if hasattr(ThinPlateSplineTransform, "from_estimate"):
            tf = ThinPlateSplineTransform.from_estimate(dst, src)
            if not tf:
                raise CorrespondenceError("TPS nao convergiu")
        else:  # pragma: no cover - scikit-image 0.25
            tf = ThinPlateSplineTransform()
            if tf.estimate(dst, src) is False:
                raise CorrespondenceError("TPS nao convergiu")
        return tf
    cls = AffineTransform if kind == "affine" else SimilarityTransform
    if hasattr(cls, "from_estimate"):
        tf = cls.from_estimate(dst, src)
        if not tf:
            raise CorrespondenceError(f"{kind} nao convergiu")
        return tf
    tf = cls()  # pragma: no cover
    if tf.estimate(dst, src) is False:
        raise CorrespondenceError(f"{kind} nao convergiu")
    return tf


def _confidence(pairs, source, target, tf, kind) -> float:
    """Confianca combinando cobertura, concordancia de posicao e residuo.

    Nao e probabilidade: e um indicador para a revisao humana decidir se
    vale confiar na correspondencia.
    """
    if not pairs:
        return 0.0
    cobertura = len(pairs) / len(LANDMARK_NAMES)

    # concordancia: landmarks correspondentes devem cair em posicoes
    # relativas parecidas nas duas caixas
    difs = []
    for n in pairs:
        sx, sy = source.normalized(n)
        tx, ty = target.normalized(n)
        difs.append(abs(sx - tx) + abs(sy - ty))
    acordo = max(0.0, 1.0 - float(np.mean(difs)))

    # confianca declarada dos proprios landmarks
    base = float(np.mean([min(source[n].confidence, target[n].confidence)
                          for n in pairs]))

    peso = {"tps": 1.0, "affine": 0.85, "similarity": 0.7}[kind]
    return round(float(np.clip(0.4 * cobertura + 0.4 * acordo + 0.2 * base, 0, 1)
                       * peso), 4)


# ---------------------------------------------------------------------------
# transporte das mascaras
# ---------------------------------------------------------------------------


def transform_mask(mask: np.ndarray, corr: Correspondence,
                   output_shape: tuple[int, int]) -> np.ndarray:
    """Leva UMA mascara do espaco da REAL para o espaco da CHIBI."""
    from skimage.transform import warp

    out = warp(mask.astype(float), corr.transform, output_shape=output_shape,
               order=0, mode="constant", cval=0.0, preserve_range=True)
    return out > 0.5


def transform_masks(masks: dict[str, np.ndarray], corr: Correspondence,
                    output_shape: tuple[int, int]) -> dict[str, np.ndarray]:
    return {k: transform_mask(m, corr, output_shape) for k, m in masks.items()}


def clip_to_target(masks: dict[str, np.ndarray], target_subject: np.ndarray,
                   banned: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Mantem a mascara dentro do alvo e fora das regioes protegidas DELE.

    Isto e obrigatorio: o warp e continuo e pode empurrar pixels para fora do
    corpo ou por cima do rosto da chibi. O criterio pedido —
    `mask_protected_overlap_pixels == 0` no espaco do alvo — depende disto.
    """
    out = {}
    for k, m in masks.items():
        mm = m & target_subject
        if banned is not None:
            mm = mm & ~banned
        out[k] = mm
    return out


# ---------------------------------------------------------------------------
# visualizacao
# ---------------------------------------------------------------------------

LANDMARK_COLOR = (255, 40, 40)


def draw_landmarks(image: Image.Image, ls: LandmarkSet, radius: int = 6,
                   color=LANDMARK_COLOR, labels: bool = True) -> Image.Image:
    from PIL import ImageDraw

    img = image.convert("RGBA").copy()
    d = ImageDraw.Draw(img)
    for name, lm in sorted(ls.landmarks.items()):
        c = color if lm.source == "derived" else (40, 180, 255)
        d.ellipse([lm.x - radius, lm.y - radius, lm.x + radius, lm.y + radius],
                  fill=c + (255,), outline=(255, 255, 255, 255), width=2)
        if labels:
            d.text((lm.x + radius + 3, lm.y - 6), name,
                   fill=(20, 20, 20, 255))
    return img


def draw_correspondence(source_img: Image.Image, target_img: Image.Image,
                        corr: Correspondence, radius: int = 6) -> Image.Image:
    """Lado a lado com linhas ligando os pares."""
    from PIL import ImageDraw

    a = source_img.convert("RGBA")
    b = target_img.convert("RGBA")
    h = max(a.height, b.height)
    canvas = Image.new("RGBA", (a.width + b.width, h), (255, 255, 255, 255))
    canvas.alpha_composite(a, (0, 0))
    canvas.alpha_composite(b, (a.width, 0))
    d = ImageDraw.Draw(canvas)

    palette = [(255, 60, 60), (60, 200, 90), (60, 130, 255), (255, 170, 0),
               (200, 60, 255), (0, 200, 200), (255, 100, 180)]
    for i, name in enumerate(corr.pairs):
        c = palette[i % len(palette)] + (255,)
        s = corr.source[name]
        t = corr.target[name]
        p1 = (s.x, s.y)
        p2 = (t.x + a.width, t.y)
        d.line([p1, p2], fill=c, width=2)
        for p in (p1, p2):
            d.ellipse([p[0] - radius, p[1] - radius,
                       p[0] + radius, p[1] + radius],
                      fill=c, outline=(255, 255, 255, 255), width=2)
        d.text((p1[0] + radius + 3, p1[1] - 6), name, fill=(20, 20, 20, 255))
    return canvas


__all__ = [
    "LANDMARK_NAMES", "MIN_PAIRS", "CorrespondenceError", "Landmark",
    "LandmarkSet", "Correspondence", "silhouette", "width_profile",
    "derive_landmarks", "load_landmark_overrides", "apply_overrides",
    "landmarks_path_for", "build_correspondence", "transform_mask",
    "transform_masks", "clip_to_target", "draw_landmarks",
    "draw_correspondence", "load_rgba",
]


def mask_metrics(source_masks: dict[str, np.ndarray],
                 warped_masks: dict[str, np.ndarray],
                 clipped_masks: dict[str, np.ndarray],
                 target_subject: np.ndarray,
                 protected: np.ndarray | None = None) -> dict:
    """Metricas por peca, no espaco do ALVO.

    Separa `warped` de `clipped` de proposito: a diferenca entre os dois e
    exatamente quanto a transformacao jogou para fora do personagem ou por
    cima de regiao protegida. Se `clipping_pixels` for alto, a
    correspondencia esta ruim — mesmo que o overlap final seja zero, porque
    o clip mascara o problema.
    """
    out = {}
    for nome in source_masks:
        origem = int(source_masks[nome].sum())
        bruto = int(warped_masks[nome].sum())
        final = int(clipped_masks[nome].sum())
        fora = int((warped_masks[nome] & ~target_subject).sum())
        ov = (int((clipped_masks[nome] & protected).sum())
              if protected is not None else 0)
        out[nome] = {
            "mask_area_source": origem,
            "mask_area_target_raw": bruto,
            "mask_area_target": final,
            "area_ratio": round(final / origem, 4) if origem else None,
            "clipping_pixels": bruto - final,
            "clipping_pct": round(100 * (bruto - final) / bruto, 2) if bruto else 0.0,
            "out_of_bounds_pixels": fora,
            "out_of_bounds_pct": round(100 * fora / bruto, 2) if bruto else 0.0,
            "mask_protected_overlap_pixels": ov,
        }
    out["_total"] = {
        "mask_protected_overlap_pixels":
            sum(v["mask_protected_overlap_pixels"] for v in out.values()),
        "out_of_bounds_pixels":
            sum(v["out_of_bounds_pixels"] for v in out.values()),
        "clipping_pixels": sum(v["clipping_pixels"] for v in out.values()),
    }
    return out

"""Testes da etapa MASK REVIEW.

Motivacao: `outside_mask_pixel_difference == 0` prova que nada FORA da
mascara mudou, mas nao prova que a mascara CORRESPONDE a roupa. Estes
testes atacam a segunda pergunta.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.chibi import design_masks as dm  # noqa: E402

FULL_BODY = ROOT / "characters" / "waifu_001" / "reference" / "full_body.png"


@pytest.fixture(scope="module")
def source() -> Image.Image:
    return dm.load_rgba(FULL_BODY)


@pytest.fixture(scope="module")
def review(source):
    return dm.review_masks(source)


# ---------------------------------------------------------------------------
# 1 + metrica exigida: mask_protected_overlap_pixels == 0
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("region", dm.GARMENT_REGIONS)
def test_mask_protected_overlap_pixels_e_zero(review, region):
    """Requisito central: nenhuma mascara toca regiao protegida."""
    assert review.metrics[region]["protected_overlap"] == 0


def test_metrica_de_overlap_detecta_violacao(review):
    """A metrica precisa acusar sobreposicao quando ela existe."""
    banned = review.banned
    assert dm.mask_protected_overlap_pixels(banned, banned) > 0
    vazia = np.zeros_like(banned)
    assert dm.mask_protected_overlap_pixels(vazia, banned) == 0


# ---------------------------------------------------------------------------
# 2. rosto/cabelo com intersecao zero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("protegida", ["cabeca", "cabelo"])
@pytest.mark.parametrize("region", dm.GARMENT_REGIONS)
def test_intersecao_zero_com_rosto_e_cabelo(review, region, protegida):
    inter = review.garment[region] & review.protected[protegida]
    assert int(np.count_nonzero(inter)) == 0


@pytest.mark.parametrize("region", dm.GARMENT_REGIONS)
def test_intersecao_zero_com_pele_meias_e_sapatos(review, region):
    for protegida in ("pele", "meias", "sapatos"):
        inter = review.garment[region] & review.protected[protegida]
        assert int(np.count_nonzero(inter)) == 0, f"{region} x {protegida}"


def test_todas_as_regioes_protegidas_existem(review):
    assert set(review.protected) == set(dm.PROTECTED_REGIONS)
    for nome, m in review.protected.items():
        assert m.any(), f"regiao protegida '{nome}' vazia"


# ---------------------------------------------------------------------------
# 3. non-empty  /  4. dentro do subject  /  5. bbox plausivel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("region", dm.GARMENT_REGIONS)
def test_mascaras_sao_nao_vazias(review, region):
    assert review.metrics[region]["pixels"] > 0


@pytest.mark.parametrize("region", dm.GARMENT_REGIONS)
def test_mascaras_dentro_do_subject(review, region):
    assert not (review.garment[region] & ~review.subject).any()


def test_todas_as_pecas_foram_segmentadas(review):
    assert set(review.garment) == set(dm.GARMENT_REGIONS)


#: Caixas plausiveis em fracoes da caixa do sujeito. Derivadas da anatomia
#: da arte, nao de gosto: gola no alto e centrada, mangas laterais na altura
#: dos bracos, capas descendo ate o chao, cada uma do seu lado.
BBOX_PLAUSIVEL = {
    "torso":         {"top": (0.10, 0.30), "bottom": (0.35, 0.60), "left": (0.25, 0.50), "right": (0.50, 0.75)},
    "mangas":        {"top": (0.20, 0.45), "bottom": (0.45, 0.60), "left": (0.15, 0.35), "right": (0.65, 0.85)},
    "capa_esquerda": {"top": (0.40, 0.65), "bottom": (0.85, 1.00), "left": (0.00, 0.25), "right": (0.30, 0.55)},
    "capa_direita":  {"top": (0.40, 0.65), "bottom": (0.85, 1.00), "left": (0.45, 0.70), "right": (0.75, 1.00)},
    "ornamentos":    {"top": (0.10, 0.30), "bottom": (0.70, 1.00), "left": (0.20, 0.45), "right": (0.55, 0.85)},
    "inferiores":    {"top": (0.85, 0.95), "bottom": (0.88, 1.00), "left": (0.35, 0.55), "right": (0.45, 0.65)},
}


@pytest.mark.parametrize("region", dm.GARMENT_REGIONS)
def test_bounding_box_plausivel(review, region):
    bb = review.metrics[region]["bbox_fractions"]
    for aresta, (lo, hi) in BBOX_PLAUSIVEL[region].items():
        v = bb[aresta]
        assert lo <= v <= hi, f"{region}.{aresta} = {v:.3f}, esperado [{lo},{hi}]"


def test_capas_estao_em_lados_opostos(review):
    esq = review.metrics["capa_esquerda"]["bbox_fractions"]
    dir_ = review.metrics["capa_direita"]["bbox_fractions"]
    assert esq["left"] < dir_["left"]
    assert esq["right"] < dir_["right"]


def test_mangas_sao_mais_largas_que_o_torso(review):
    """A gola e estreita; as mangas sino se abrem para os lados."""
    t = review.metrics["torso"]["bbox_fractions"]
    m = review.metrics["mangas"]["bbox_fractions"]
    assert (m["right"] - m["left"]) > (t["right"] - t["left"])


def test_torso_fica_acima_das_capas(review):
    t = review.metrics["torso"]["bbox_fractions"]
    for lado in ("capa_esquerda", "capa_direita"):
        assert t["top"] < review.metrics[lado]["bbox_fractions"]["top"]


def test_mascaras_nao_se_sobrepoem(review):
    nomes = list(dm.GARMENT_REGIONS)
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            inter = review.garment[a] & review.garment[b]
            assert int(np.count_nonzero(inter)) == 0, f"{a} x {b}"


# ---------------------------------------------------------------------------
# nao usar: cor sozinha, bbox como segmentacao, tudo-escuro-e-roupa
# ---------------------------------------------------------------------------


def test_nem_toda_regiao_escura_virou_roupa(source, review):
    """Meias-calcas e cabelo sao escuros e NAO podem ser vestuario."""
    rgb = np.array(source)[..., :3].astype(int)
    dark = (rgb.max(2) < dm.DARK_MAX) & review.subject
    vest = np.zeros_like(dark)
    for m in review.garment.values():
        vest |= m
    assert int(vest.sum()) < int(dark.sum()) * 0.85


def test_mascara_nao_e_um_retangulo(review):
    """Bbox nao substitui segmentacao: a peca nao pode preencher sua caixa."""
    for region in ("capa_esquerda", "capa_direita", "mangas"):
        m = review.garment[region]
        ys, xs = np.nonzero(m)
        area_bbox = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
        assert int(m.sum()) / area_bbox < 0.92, f"{region} parece retangular"


def test_cabelo_nao_vaza_para_as_mangas(review):
    """Regressao real: o flood-fill do cabelo engolia mangas e capa alta.

    O cabelo e neutro (R-B ~ -0.5) e o tecido e frio (R-B ~ -8); sem essa
    barreira cromatica o cabelo descia ate a cintura.
    """
    bb = dm.bbox_fractions(review.protected["cabelo"], review.subject_bbox)
    assert bb["bottom"] < 0.46, "cabelo desceu demais — vazou para a roupa"
    assert review.metrics["mangas"]["pixels"] > 2000, "mangas foram engolidas"


def test_capa_alcanca_a_barra(review):
    """Regressao real: a faixa dos sapatos protegia a largura inteira e
    roubava a barra da capa, que desce ate o chao."""
    for lado in ("capa_esquerda", "capa_direita"):
        assert review.metrics[lado]["bbox_fractions"]["bottom"] > 0.95


def test_sapatos_nao_ocupam_a_largura_toda(review):
    bb = dm.bbox_fractions(review.protected["sapatos"], review.subject_bbox)
    assert bb["left"] > 0.20 and bb["right"] < 0.85


# ---------------------------------------------------------------------------
# 6. overlays  /  7. fonte imutavel
# ---------------------------------------------------------------------------


def test_overlays_sao_gerados(source, review):
    ov = dm.overlay(source, review.garment)
    assert ov.size == source.size
    antes = np.array(source.convert("RGBA"))
    depois = np.array(ov)
    uniao = np.zeros(antes.shape[:2], dtype=bool)
    for m in review.garment.values():
        uniao |= m
    assert not np.array_equal(antes[uniao][..., :3], depois[uniao][..., :3])
    assert np.array_equal(antes[~uniao][..., :3], depois[~uniao][..., :3])


@pytest.mark.parametrize("region", dm.GARMENT_REGIONS)
def test_overlay_individual_por_peca(source, review, region):
    ov = dm.overlay_single(source, review.garment[region])
    assert ov.size == source.size


def test_overlay_das_protegidas(source, review):
    ov = dm.overlay(source, review.protected,
                    {k: (255, 0, 0) for k in review.protected})
    assert ov.size == source.size


def test_fonte_original_permanece_imutavel():
    antes = hashlib.sha256(FULL_BODY.read_bytes()).hexdigest()
    src = dm.load_rgba(FULL_BODY)
    rv = dm.review_masks(src)
    dm.overlay(src, rv.garment)
    depois = hashlib.sha256(FULL_BODY.read_bytes()).hexdigest()
    assert antes == depois
    assert antes == "2fdcd5f428f5980d63e31d4bf4a67aecbc11c1b101c19ca75f819db616cb8177"


# ---------------------------------------------------------------------------
# reprodutibilidade e portao humano
# ---------------------------------------------------------------------------


def test_mascaras_sao_deterministas(source):
    a = dm.review_masks(source)
    b = dm.review_masks(source)
    for k in dm.GARMENT_REGIONS:
        assert a.metrics[k]["mask_sha256"] == b.metrics[k]["mask_sha256"]


def test_aprovacao_nao_e_automatica(review):
    """O agente nao aprova mascara. `all_clear` e objetivo; `approved` e humano."""
    assert review.approved is False
    assert review.all_clear() is True


def test_rigidez_declarada_para_cada_peca():
    for region in dm.GARMENT_REGIONS:
        assert dm.RIGIDITY[region] in ("rigid", "cloth", "semi_rigid")


def test_sem_dependencia_generativa():
    fonte = (ROOT / "scripts" / "chibi" / "design_masks.py").read_text().lower()
    for proibido in ("torch", "diffusers", "comfy", "safetensors", "gguf"):
        assert proibido not in fonte

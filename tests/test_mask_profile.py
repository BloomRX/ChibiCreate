"""Arquitetura de mascaras: generico x especifico da personagem.

Pergunta central destes testes: os numeros medidos na waifu_001 conseguem
vazar para outra personagem? A resposta tem de ser nao.
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

from scripts.chibi import mask_engine as me  # noqa: E402
from scripts.chibi import mask_profile as mp  # noqa: E402
from tests.fixtures.synthetic_character import (  # noqa: E402
    ACCENT,
    CLOAK,
    LEGS,
    make_synthetic,
    synthetic_profile,
)

FULL_BODY = ROOT / "characters" / "waifu_001" / "reference" / "full_body.png"
WAIFU_YAML = ROOT / "characters" / "waifu_001" / "masks.yaml"

#: Valores medidos na waifu_001. NENHUM deles pode aparecer como default.
WAIFU_MAGIC = {
    "dark_max": 110, "cool_max": -2, "warm_min": 3, "waist": 0.52,
    "leg_left": 0.26, "leg_right": 0.81, "torso_half_width": 0.115,
}


@pytest.fixture(scope="module")
def waifu() -> Image.Image:
    return me.load_rgba(FULL_BODY)


@pytest.fixture(scope="module")
def synthetic() -> Image.Image:
    return make_synthetic()


# ---------------------------------------------------------------------------
# 1. algoritmo generico nao contem numeros da waifu_001
# ---------------------------------------------------------------------------


def test_motor_generico_nao_tem_constantes_da_waifu():
    """O codigo do motor nao pode conter os valores calibrados."""
    fonte = (ROOT / "scripts" / "chibi" / "mask_engine.py").read_text()
    # numeros calibrados na waifu_001 nao podem estar escritos no motor
    for proibido in ("0.52", "0.26", "0.81", "0.115", "0.1206", "0.5195"):
        assert proibido not in fonte, f"constante {proibido} no motor"
    # e o motor nao pode definir limiares proprios: todos vem de params[...]
    for key in ("dark_max", "cool_max", "warm_min", "waist"):
        assert f'params["{key}"]' in fonte, f"{key} deveria vir do perfil"


def test_perfil_estrutural_nao_contem_calibracao():
    """STRUCTURAL_ANATOMY e anatomia generica, nao medida da waifu."""
    for key, val in mp.STRUCTURAL_ANATOMY.items():
        assert val != WAIFU_MAGIC.get("waist"), key
    # valores redondos == genericos, nao medidos
    for val in mp.STRUCTURAL_ANATOMY.values():
        assert round(val, 2) == val


def test_todos_os_limiares_sao_derivados_sem_override(waifu):
    rv = me.review_masks(waifu)
    assert rv.params.profile.is_empty
    assert rv.params.overridden == []
    for key in mp.THRESHOLD_KEYS:
        assert rv.params.source_of(key).startswith("derived"), key


def test_derivacao_reencontra_a_cintura_sem_saber_o_valor(waifu):
    """A cintura derivada tem de bater com a medida a mao (0.52), mas sem
    que 0.52 esteja escrito em lugar nenhum."""
    rv = me.review_masks(waifu)
    assert abs(rv.params["waist"] - 0.52) < 0.05


# ---------------------------------------------------------------------------
# 2. ausencia de override nao injeta os numeros da waifu_001
# ---------------------------------------------------------------------------


def test_personagem_sem_perfil_usa_so_o_generico(synthetic):
    rv = me.review_masks(synthetic)
    assert rv.params.profile.is_empty
    assert rv.params.overridden == []


def test_perfil_inexistente_nao_e_erro():
    prof = mp.load_profile("personagem_que_nao_existe")
    assert prof.is_empty
    assert prof.character_id == "personagem_que_nao_existe"


def test_limiares_da_sintetica_diferem_dos_da_waifu(waifu, synthetic):
    """Se os parametros fossem globais, seriam iguais nas duas."""
    a = me.review_masks(waifu).params
    b = me.review_masks(synthetic).params
    diferentes = [k for k in mp.THRESHOLD_KEYS if a[k] != b[k]]
    assert len(diferentes) >= 3, f"apenas {diferentes} diferiram"


def test_nenhum_valor_da_waifu_aparece_na_sintetica(synthetic):
    rv = me.review_masks(synthetic)
    for key, magico in WAIFU_MAGIC.items():
        if key in ("leg_left", "leg_right"):
            continue  # podem coincidir por acaso em silhueta simetrica
        assert rv.params[key] != magico, f"{key} veio da waifu_001"


# ---------------------------------------------------------------------------
# 3. o algoritmo nao depende das cores da waifu_001
# ---------------------------------------------------------------------------


def test_fixture_tem_paleta_oposta():
    """Garante que o fixture realmente inverte o que importa."""
    assert (CLOAK[0] - CLOAK[2]) > 0, "capa da sintetica deve ser QUENTE"
    assert (LEGS[0] - LEGS[2]) < 0, "pernas da sintetica devem ser FRIAS"
    assert ACCENT[2] > ACCENT[0], "destaque deve ser ciano, nao dourado"


def test_segmenta_personagem_de_cores_invertidas(synthetic):
    rv = me.review_masks(synthetic)
    assert rv.all_clear(), rv.metrics
    for region in me.GARMENT_REGIONS:
        assert rv.metrics[region]["pixels"] > 0, region


def test_destaque_nao_assume_dourado(synthetic):
    """accent_mask nao pode ter viés de ouro (r >= b)."""
    rgb = np.array(synthetic)[..., :3]
    assert int(me.accent_mask(rgb).sum()) > 0
    fonte = (ROOT / "scripts" / "chibi" / "mask_engine.py").read_text()
    assert "(r >= b)" not in fonte


def test_ambas_as_personagens_passam_no_mesmo_pipeline(waifu, synthetic):
    for img in (waifu, synthetic):
        rv = me.review_masks(img)
        assert rv.all_clear()


# ---------------------------------------------------------------------------
# 4. parametros de uma personagem nao vazam para outra
# ---------------------------------------------------------------------------


def test_override_da_waifu_nao_afeta_a_sintetica(synthetic):
    antes = me.review_masks(synthetic)
    me.review_masks(me.load_rgba(FULL_BODY), character_id="waifu_001")
    depois = me.review_masks(synthetic)
    for k in me.GARMENT_REGIONS:
        assert (antes.metrics[k]["mask_sha256"]
                == depois.metrics[k]["mask_sha256"]), k


def test_override_da_sintetica_nao_afeta_a_waifu(waifu):
    antes = me.review_masks(waifu, character_id="waifu_001")
    prof = mp.MaskProfile.from_dict(synthetic_profile())
    me.review_masks(make_synthetic(), profile=prof)
    depois = me.review_masks(waifu, character_id="waifu_001")
    for k in me.GARMENT_REGIONS:
        assert (antes.metrics[k]["mask_sha256"]
                == depois.metrics[k]["mask_sha256"]), k


def test_perfis_sao_objetos_independentes():
    a = mp.load_profile("waifu_001")
    b = mp.MaskProfile.from_dict(synthetic_profile())
    a.thresholds["leg_left"] = 0.99
    assert b.thresholds.get("leg_left") != 0.99
    c = mp.load_profile("waifu_001")
    assert c.thresholds["leg_left"] != 0.99, "mutacao vazou pelo cache"


def test_trocar_perfil_muda_o_resultado(waifu):
    gen = me.review_masks(waifu)
    ovr = me.review_masks(waifu, character_id="waifu_001")
    assert ovr.params.overridden == ["leg_left", "leg_right"]
    assert (gen.metrics["capa_esquerda"]["mask_sha256"]
            != ovr.metrics["capa_esquerda"]["mask_sha256"])


def test_override_da_waifu_melhora_a_barra_da_capa(waifu):
    """O override existe por um motivo verificavel, nao por gosto."""
    gen = me.review_masks(waifu)
    ovr = me.review_masks(waifu, character_id="waifu_001")
    assert ovr.metrics["capa_esquerda"]["bbox_fractions"]["bottom"] > \
        gen.metrics["capa_esquerda"]["bbox_fractions"]["bottom"]


# ---------------------------------------------------------------------------
# perfil: validacao e opcionalidade
# ---------------------------------------------------------------------------


def test_masks_yaml_da_waifu_e_valido():
    prof = mp.load_profile("waifu_001")
    assert prof.character_id == "waifu_001"
    assert not prof.is_empty
    assert set(prof.thresholds) <= mp.THRESHOLD_KEYS


def test_chave_desconhecida_e_rejeitada():
    with pytest.raises(mp.ProfileError):
        mp.MaskProfile.from_dict({"coisa_inventada": 1})


def test_threshold_desconhecido_e_rejeitado():
    with pytest.raises(mp.ProfileError):
        mp.MaskProfile.from_dict({"thresholds": {"nao_existe": 1}})


def test_perfil_vazio_e_valido():
    assert mp.MaskProfile.from_dict({}).is_empty
    assert mp.MaskProfile.from_dict(None).is_empty


def test_todas_as_chaves_documentadas_sao_aceitas():
    pedidas = {"strategy", "thresholds", "protected_regions",
               "region_definitions", "geometric_constraints", "color_hints",
               "connectivity_seeds", "manual_hints"}
    assert pedidas <= mp.OVERRIDE_KEYS


def test_color_hints_permitem_paleta_atipica(synthetic):
    prof = mp.MaskProfile.from_dict(
        {"color_hints": {"accent_rgb": list(ACCENT), "accent_tolerance": 90}})
    rv = me.review_masks(synthetic, profile=prof)
    assert rv.metrics["ornamentos"]["pixels"] > 0


# ---------------------------------------------------------------------------
# invariantes preservadas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("region", me.GARMENT_REGIONS)
def test_mask_protected_overlap_zero_waifu(waifu, region):
    rv = me.review_masks(waifu, character_id="waifu_001")
    assert rv.metrics[region]["protected_overlap"] == 0


@pytest.mark.parametrize("region", me.GARMENT_REGIONS)
def test_mask_protected_overlap_zero_sintetica(synthetic, region):
    rv = me.review_masks(synthetic)
    assert rv.metrics[region]["protected_overlap"] == 0


def test_excecao_de_overlap_e_estreita_e_declarada():
    """So o ornamento do calcado pode viver dentro de 'sapatos'."""
    assert set(me.ALLOWED_PROTECTED_OVERLAP) == {"inferiores"}
    assert me.ALLOWED_PROTECTED_OVERLAP["inferiores"] == frozenset({"sapatos"})


def test_overlap_estrito_ainda_detecta_violacao(waifu):
    rv = me.review_masks(waifu, character_id="waifu_001")
    banned = rv.banned
    assert me.mask_protected_overlap_pixels(banned, banned) > 0


def test_source_immutable():
    antes = hashlib.sha256(FULL_BODY.read_bytes()).hexdigest()
    src = me.load_rgba(FULL_BODY)
    rv = me.review_masks(src, character_id="waifu_001")
    me.overlay(src, rv.garment)
    assert hashlib.sha256(FULL_BODY.read_bytes()).hexdigest() == antes
    assert antes == "2fdcd5f428f5980d63e31d4bf4a67aecbc11c1b101c19ca75f819db616cb8177"


def test_mascaras_dentro_do_subject(waifu, synthetic):
    for img, cid in ((waifu, "waifu_001"), (synthetic, None)):
        rv = me.review_masks(img, character_id=cid)
        for k in me.GARMENT_REGIONS:
            assert not (rv.garment[k] & ~rv.subject).any(), k


def test_deterministico(waifu):
    a = me.review_masks(waifu, character_id="waifu_001")
    b = me.review_masks(waifu, character_id="waifu_001")
    for k in me.GARMENT_REGIONS:
        assert a.metrics[k]["mask_sha256"] == b.metrics[k]["mask_sha256"]


def test_aprovacao_continua_humana(waifu):
    rv = me.review_masks(waifu, character_id="waifu_001")
    assert rv.approved is False


def test_procedencia_e_reportavel(waifu):
    rv = me.review_masks(waifu, character_id="waifu_001")
    rel = rv.provenance_report()
    assert "override:waifu_001" in rel
    assert "derived:" in rel


def test_sem_dependencia_generativa():
    for mod in ("mask_engine.py", "mask_profile.py"):
        fonte = (ROOT / "scripts" / "chibi" / mod).read_text().lower()
        for proibido in ("torch", "diffusers", "comfy", "safetensors"):
            assert proibido not in fonte, f"{mod}: {proibido}"


def test_nao_executa_warp_nem_composicao():
    """Esta etapa para na MASK REVIEW."""
    fonte = (ROOT / "scripts" / "chibi" / "mask_engine.py").read_text()
    for proibido in ("warp_tps", "run_variant_a", "run_variant_b", "composite"):
        assert proibido not in fonte

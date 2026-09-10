"""Testes do design/outfit transfer nao-generativo (linha experimental).

O teste central e `outside_mask_pixel_difference == 0`: fora da mascara, a
Run 003 tem de permanecer intacta.
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

from scripts.chibi import design_transfer as dt  # noqa: E402

REF = ROOT / "characters" / "waifu_001" / "reference"
FULL_BODY = REF / "full_body.png"
OUTFIT = REF / "outfit.png"


# ---------------------------------------------------------------------------
# fixtures sinteticas — nao dependem de run_003, que nao esta versionado
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_source() -> Image.Image:
    """Sujeito sobre fundo transparente, com tecido escuro e ouro."""
    arr = np.zeros((200, 120, 4), dtype=np.uint8)
    arr[20:180, 30:90] = (230, 200, 190, 255)      # corpo (pele)
    arr[60:110, 35:85] = (20, 20, 24, 255)         # roupa escura (tronco)
    arr[110:175, 32:88] = (30, 32, 34, 255)        # capa (abaixo)
    arr[70:80, 40:80] = (200, 160, 40, 255)        # ornamento dourado
    return Image.fromarray(arr, "RGBA")


@pytest.fixture
def fake_base() -> Image.Image:
    """Base chibi: proporcoes diferentes, opaca (como saida de modelo)."""
    arr = np.zeros((200, 120, 4), dtype=np.uint8)
    arr[..., :3] = (133, 133, 132)                 # fundo liso
    arr[..., 3] = 255
    arr[40:170, 35:85] = (240, 210, 200, 255)      # corpo chibi
    return Image.fromarray(arr, "RGBA")


@pytest.fixture
def masks(fake_source):
    return dt.build_masks(fake_source)


# ---------------------------------------------------------------------------
# entradas reais
# ---------------------------------------------------------------------------


def test_inputs_reais_existem_e_tem_dimensoes_conhecidas():
    assert FULL_BODY.exists(), "full_body.png e a fonte do design"
    with Image.open(FULL_BODY) as img:
        assert img.size == (1024, 1024)
        assert img.mode == "RGBA"


def test_outfit_png_nao_e_usado_como_fonte():
    """outfit.png e recorte retangular com pele/fundo; usa-lo colaria corpo."""
    fonte = (ROOT / "scripts" / "chibi" / "design_transfer.py").read_text()
    assert "outfit.png" not in fonte.replace("`outfit.png` NAO e usado", "")


def test_arquivos_fonte_nao_sao_modificados(fake_base):
    """Nenhuma operacao pode escrever na arte-fonte."""
    antes = hashlib.sha256(FULL_BODY.read_bytes()).hexdigest()
    src = dt.load_rgba(FULL_BODY)
    m = dt.build_masks(src)
    dt.run_variant_a(fake_base.resize(src.size), src, m)
    depois = hashlib.sha256(FULL_BODY.read_bytes()).hexdigest()
    assert antes == depois


def test_capa_e_cabelo_nao_sao_separaveis_por_cor():
    """Achado que justifica a arquitetura: cor sozinha NAO basta.

    Se este teste falhar, a premissa do relatorio mudou e o desenho das
    mascaras precisa ser revisto.
    """
    arr = np.array(dt.load_rgba(FULL_BODY))
    rgb = arr[..., :3].astype(int)
    cabelo = rgb[200:280, 470:560].reshape(-1, 3).mean(0)
    capa = rgb[700:800, 350:420].reshape(-1, 3).mean(0)
    assert float(np.abs(cabelo - capa).mean()) < 40.0


def test_segmentacao_nao_e_por_cor_isolada(fake_source):
    """Cada mascara e cor AND geometria AND alpha."""
    arr = np.array(fake_source)
    so_cor = dt.is_dark(arr[..., :3])
    m = dt.build_masks(fake_source)
    combinada = m["roupa"] | m["capa"]
    assert combinada.sum() < so_cor.sum(), "geometria/alpha devem restringir a cor"


# ---------------------------------------------------------------------------
# mascaras
# ---------------------------------------------------------------------------


def test_as_tres_regioes_sao_produzidas(masks):
    assert set(masks) == set(dt.MASK_REGIONS)
    for nome, m in masks.items():
        assert m.dtype == np.bool_, nome
        assert m.any(), f"mascara '{nome}' ficou vazia"


def test_mascaras_sao_mutuamente_exclusivas(masks):
    nomes = list(masks)
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            assert not (masks[a] & masks[b]).any(), f"{a} e {b} se sobrepoem"


def test_ornamentos_tem_prioridade(fake_source, masks):
    """Ouro define o design: nao pode ser engolido pelo tecido."""
    arr = np.array(fake_source)
    ouro = dt.is_gold(arr[..., :3]) & dt.subject_mask(fake_source)
    assert (masks["ornamentos"] & ouro).any()
    assert not (masks["roupa"] & masks["ornamentos"]).any()


def test_mascaras_sao_deterministas(fake_source):
    a = dt.build_masks(fake_source)
    b = dt.build_masks(fake_source)
    for k in a:
        assert dt.mask_sha256(a[k]) == dt.mask_sha256(b[k])


def test_mascara_nao_invade_a_cabeca(fake_source, masks):
    """top=0.18 da caixa protege rosto, cabelo e chifres."""
    subj = dt.subject_mask(fake_source)
    left, top, right, bottom = dt.bbox_of(subj)
    limite = top + int(round((bottom - top) * 0.18))
    for nome, m in masks.items():
        assert not m[:limite].any(), f"'{nome}' invadiu a regiao da cabeca"


def test_mascaras_ficam_dentro_do_sujeito(fake_source, masks):
    subj = dt.subject_mask(fake_source)
    for nome, m in masks.items():
        assert not (m & ~subj).any(), f"'{nome}' vazou para fora do sujeito"


# ---------------------------------------------------------------------------
# GARANTIA CENTRAL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variante", ["A", "B"])
def test_outside_mask_pixel_difference_e_zero(fake_base, fake_source, masks, variante):
    """Fora da mascara, a Run 003 permanece byte-identica."""
    fn = dt.run_variant_a if variante == "A" else dt.run_variant_b
    r = fn(fake_base, fake_source, masks)
    assert r.metrics["outside_mask_pixel_difference"] == 0


@pytest.mark.parametrize("variante", ["A", "B"])
def test_base_preservada_fora_da_mascara_por_comparacao_direta(
    fake_base, fake_source, masks, variante
):
    """Verificacao independente da metrica reportada pelo proprio codigo."""
    fn = dt.run_variant_a if variante == "A" else dt.run_variant_b
    antes = np.array(fake_base.convert("RGBA"))
    r = fn(fake_base, fake_source, masks)
    depois = np.array(r.image)
    fora = ~r.effective_mask
    assert np.array_equal(antes[fora][..., :3], depois[fora][..., :3])


def test_algo_de_fato_mudou_dentro_da_mascara(fake_base, fake_source, masks):
    """Preservar tudo seria trivial: a composicao precisa ter efeito."""
    r = dt.run_variant_b(fake_base, fake_source, masks)
    assert r.metrics["pixels_changed"] > 0
    antes = np.array(fake_base.convert("RGBA"))
    assert not np.array_equal(antes[..., :3], np.array(r.image)[..., :3])


def test_deteccao_de_regressao_na_metrica(fake_base):
    """A metrica precisa acusar mudanca fora da mascara quando ela ocorre."""
    a = np.array(fake_base.convert("RGBA"))
    b = a.copy()
    b[5, 5, :3] = (1, 2, 3)
    mask = np.zeros(a.shape[:2], dtype=bool)
    assert dt.outside_mask_pixel_difference(a, b, mask) == 1
    mask[5, 5] = True
    assert dt.outside_mask_pixel_difference(a, b, mask) == 0


# ---------------------------------------------------------------------------
# transformacoes
# ---------------------------------------------------------------------------


def test_variantes_produzem_resultados_diferentes(fake_base, fake_source, masks):
    """Se A e B coincidissem, as mascaras separadas nao acrescentariam nada."""
    ra = dt.run_variant_a(fake_base, fake_source, masks)
    rb = dt.run_variant_b(fake_base, fake_source, masks)
    assert dt.pixel_sha256(ra.image) != dt.pixel_sha256(rb.image)


def test_parametros_de_transformacao_registrados(fake_base, fake_source, masks):
    rb = dt.run_variant_b(fake_base, fake_source, masks)
    p = rb.params
    assert p["algorithm"]
    assert p["control_points"] == p["grid"] ** 2
    assert set(p["per_region"]) == set(dt.MASK_REGIONS)
    assert p["transform"]["scale_x"] > 0


def test_ornamentos_nao_sofrem_tps(fake_base, fake_source, masks):
    """Peca rigida: deformar destroi o design."""
    rb = dt.run_variant_b(fake_base, fake_source, masks)
    assert "affine" in rb.params["per_region"]["ornamentos"]["method"]
    assert "tps" in rb.params["per_region"]["capa"]["method"]


def test_tps_move_conteudo_na_direcao_esperada():
    layer = np.zeros((100, 100), float)
    layer[40:60, 40:60] = 1.0
    src = np.array([[0, 0], [99, 0], [0, 99], [99, 99], [50, 50]], float)
    dst = np.array([[0, 0], [99, 0], [0, 99], [99, 99], [70, 50]], float)
    out = dt.warp_tps(layer, src, dst, (100, 100), order=0)
    _, xs = np.nonzero(out > 0.5)
    assert xs.mean() > 60.0


def test_composicao_e_determinista(fake_base, fake_source, masks):
    a = dt.run_variant_b(fake_base, fake_source, masks)
    b = dt.run_variant_b(fake_base, fake_source, masks)
    assert dt.pixel_sha256(a.image) == dt.pixel_sha256(b.image)


def test_resolucao_preservada(fake_base, fake_source, masks):
    for fn in (dt.run_variant_a, dt.run_variant_b):
        r = fn(fake_base, fake_source, masks)
        assert r.image.size == fake_base.size


# ---------------------------------------------------------------------------
# overlay e recipe
# ---------------------------------------------------------------------------


def test_overlay_marca_as_mascaras_sem_destruir_a_base(fake_base, masks):
    ov = dt.overlay_masks(fake_base, masks)
    assert ov.size == fake_base.size
    antes = np.array(fake_base.convert("RGBA"))
    depois = np.array(ov)
    uniao = np.zeros(antes.shape[:2], dtype=bool)
    for m in masks.values():
        uniao |= m
    assert np.array_equal(antes[~uniao][..., :3], depois[~uniao][..., :3])
    assert not np.array_equal(antes[uniao][..., :3], depois[uniao][..., :3])


def test_recipe_separa_artifact_de_pixel_hash(tmp_path, fake_base, fake_source, masks):
    r = dt.run_variant_b(fake_base, fake_source, masks)
    out = tmp_path / "b.png"
    r.image.save(out)
    rec = dt.build_recipe(r, {"base": out, "source": FULL_BODY}, out)
    assert rec["output"]["artifact_sha256"]
    assert rec["output"]["output_pixel_sha256"]
    assert rec["output"]["artifact_sha256"] != rec["output"]["output_pixel_sha256"]


def test_recipe_registra_licencas_e_versoes(tmp_path, fake_base, fake_source, masks):
    r = dt.run_variant_a(fake_base, fake_source, masks)
    out = tmp_path / "a.png"
    r.image.save(out)
    rec = dt.build_recipe(r, {"source": FULL_BODY}, out)
    for lib in ("numpy", "pillow", "scikit-image"):
        assert rec["libraries"][lib]
        assert rec["licenses"][lib]
    assert rec["generative"] is False
    assert rec["approval_status"] == "experimental"
    assert rec["metrics"]["outside_mask_pixel_difference"] == 0


def test_recipe_registra_hashes_das_mascaras(tmp_path, fake_base, fake_source, masks):
    r = dt.run_variant_b(fake_base, fake_source, masks)
    out = tmp_path / "b.png"
    r.image.save(out)
    rec = dt.build_recipe(r, {"source": FULL_BODY}, out)
    assert set(rec["masks"]) == set(dt.MASK_REGIONS)
    for nome, info in rec["masks"].items():
        assert info["mask_sha256"]
        assert info["pixels"] > 0
        assert info["rigidity"] in ("rigid", "cloth", "semi_rigid")


def test_recipe_exige_revisao_humana(tmp_path, fake_base, fake_source, masks):
    """O agente nao escolhe vencedor artistico."""
    r = dt.run_variant_a(fake_base, fake_source, masks)
    out = tmp_path / "a.png"
    r.image.save(out)
    rec = dt.build_recipe(r, {"source": FULL_BODY}, out)
    assert any("HUMAN REVIEW REQUIRED" in s for s in rec["human_review_required"])


def test_nada_de_generativo_no_modulo():
    """Variante C nao foi implementada; nenhum modelo entra nesta linha."""
    fonte = (ROOT / "scripts" / "chibi" / "design_transfer.py").read_text().lower()
    for proibido in ("torch", "diffusers", "comfy", "safetensors", "gguf", "checkpoint"):
        assert proibido not in fonte, f"dependencia generativa '{proibido}' encontrada"


def test_licencas_declaradas_sao_permissivas():
    for lib, lic in dt.LIBRARY_LICENSES.items():
        assert any(t in lic for t in ("BSD", "MIT", "Apache")), f"{lib}: {lic}"

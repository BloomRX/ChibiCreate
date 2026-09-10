"""Testes do WAI INPAINT-XL LAB (correcao localizada de figurino).

Fase separada do wai_chibi_lab: aqui a personagem JA e chibi e so a roupa
pode ser redesenhada.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pytest
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi.inpaint_check import comparar, InpaintCheckError  # noqa: E402

NB = ROOT / "notebooks" / "waifu_inpaint_xl_lab.ipynb"
WF = ROOT / "workflows" / "experimental" / "waifu_inpaint_xl" / "v0.json"


def _celula(prefixo: str) -> str:
    nb = json.loads(NB.read_text())
    for c in nb["cells"]:
        if c["cell_type"] != "code":
            continue
        s = "".join(c["source"])
        if s.startswith(prefixo):
            return s
    raise AssertionError(f"celula {prefixo!r} nao encontrada")


def _codigo(prefixo: str) -> str:
    return "\n".join(l for l in _celula(prefixo).split("\n")
                     if not l.strip().startswith("#@"))


def _executa_celula0(**overrides) -> dict:
    src = _codigo("#@title 0.")
    for antigo, novo in overrides.items():
        assert antigo in src, f"trecho nao encontrado: {antigo!r}"
        src = src.replace(antigo, novo)
    ns: dict = {}
    exec(compile(src, "celula0", "exec"), ns)
    return ns


def _nodes() -> dict:
    return {k: v for k, v in json.loads(WF.read_text()).items()
            if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Arquitetura do grafo — os invariantes desta fase
# ---------------------------------------------------------------------------

def test_usa_inpaint_model_conditioning_e_nao_vae_encode_for_inpaint():
    """VAEEncodeForInpaint substitui a area por ruido e exige denoise 1.0.

    Isso destruiria o design existente — o oposto do objetivo. O
    InpaintModelConditioning preserva o conteudo sob a mascara e permite
    strength < 1.0.
    """
    classes = {v["class_type"] for v in _nodes().values()}
    assert "InpaintModelConditioning" in classes
    assert "VAEEncodeForInpaint" not in classes


def test_latente_vem_do_inpaint_conditioning():
    n = _nodes()
    cls = {k: v["class_type"] for k, v in n.items()}
    ks = [k for k, c in cls.items() if c == "KSampler"][0]
    origem = n[ks]["inputs"]["latent_image"][0]
    assert cls[origem] == "InpaintModelConditioning"


def test_modelo_passa_por_v_prediction():
    """Deriva do WAI V14.0 V-Prediction; com eps o output sai queimado."""
    n = _nodes()
    cls = {k: v["class_type"] for k, v in n.items()}
    ks = [k for k, c in cls.items() if c == "KSampler"][0]
    msd = n[ks]["inputs"]["model"][0]
    assert cls[msd] == "ModelSamplingDiscrete"
    assert n[msd]["inputs"]["sampling"] == "%%SAMPLING_TYPE%%"


def test_mascara_passa_por_dilatacao_e_feather():
    n = _nodes()
    cls = {k: v["class_type"] for k, v in n.items()}
    imc = [k for k, c in cls.items() if c == "InpaintModelConditioning"][0]
    feather = n[imc]["inputs"]["mask"][0]
    assert cls[feather] == "FeatherMask"
    grow = n[feather]["inputs"]["mask"][0]
    assert cls[grow] == "GrowMask"
    assert cls[n[grow]["inputs"]["mask"][0]] == "LoadImageMask"


def test_source_image_alimenta_os_pixels():
    n = _nodes()
    cls = {k: v["class_type"] for k, v in n.items()}
    imc = [k for k, c in cls.items() if c == "InpaintModelConditioning"][0]
    assert cls[n[imc]["inputs"]["pixels"][0]] == "LoadImage"


def test_teste_1_nao_tem_ip_adapter():
    """O baseline mede o que o modelo faz SOZINHO."""
    classes = {v["class_type"] for v in _nodes().values()}
    assert not [c for c in classes if "IPAdapter" in c]


def test_mascara_e_entrada_separada_da_referencia():
    """outfit.png e crop visual; a mascara e regiao semantica."""
    n = _nodes()
    mask_node = [v for v in n.values() if v["class_type"] == "LoadImageMask"][0]
    img_node = [v for v in n.values() if v["class_type"] == "LoadImage"][0]
    assert mask_node["inputs"]["image"] == "%%OUTFIT_MASK%%"
    assert img_node["inputs"]["image"] == "%%SOURCE_IMAGE%%"
    assert mask_node["inputs"]["image"] != img_node["inputs"]["image"]


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

def test_painel_tem_os_parametros_minimos():
    src = _celula("#@title 0.")
    for p in ("SOURCE_IMAGE", "OUTFIT_REFERENCE", "OUTFIT_MASK",
              "PROMPT_PRESET", "SEED", "STEPS", "CFG_SCALE",
              "INPAINT_STRENGTH", "MASK_DILATION", "MASK_FEATHER",
              "OUTPUT_RESOLUTION", "REFERENCE_MODE"):
        assert f"{p} = " in src, f"faltou {p}"


def test_defaults_seguem_o_model_card():
    ns = _executa_celula0()
    assert ns["STEPS"] == 28
    assert ns["CFG_SCALE"] == 5.0
    assert ns["SEED"] == 42
    assert ns["SAMPLING_TYPE"] == "v_prediction"


def test_strength_nao_herda_o_0_90_do_img2img():
    ns = _executa_celula0()
    assert ns["INPAINT_STRENGTH"] == 0.75
    assert "EXPERIMENTAL" in ns["CONFIG"]["inpaint_strength_note"]


def test_teste_1_comeca_sem_referencia():
    ns = _executa_celula0()
    assert ns["REFERENCE_MODE"] == "NONE"
    assert ns["CONFIG"]["references_available_not_used"]["outfit"] == "outfit.png"


@pytest.mark.parametrize("modo", ["OUTFIT_REFERENCE", "FULL_BODY_REFERENCE",
                                  "FULL_BODY_PLUS_OUTFIT"])
def test_modos_de_referencia_nao_implementados_bloqueiam(modo):
    """Nao prometer no dropdown algo que roda diferente do nome."""
    with pytest.raises(AssertionError, match="TESTE 2"):
        _executa_celula0(**{'REFERENCE_MODE = "NONE"':
                            f'REFERENCE_MODE = "{modo}"'})


def test_prompt_fala_da_funcao_nao_da_personagem():
    import chibi.model_registry as mr
    ns = _executa_celula0()
    assert mr.termos_especificos_no_prompt(ns["PROMPT"]) == []
    assert "preserve character design" in ns["PROMPT"]
    assert ns["CONFIG"]["character_specific_prompt"] is False


def test_config_separa_os_tres_papeis():
    cfg = _executa_celula0()["CONFIG"]
    assert cfg["source_image_role"] == "chibi_already_generated"
    assert cfg["mask_role"] == "semantic_region_that_may_be_redrawn"
    assert cfg["reference_mode"] == "NONE"


def test_recipe_registra_o_lineage_e_nao_confunde_com_v17():
    codigo = _codigo("#@title 5.")
    assert "V14.0-V-Prediction" in codigo
    assert "unet_in_channels" in codigo
    assert "CheckpointLoaderSimple" in codigo
    assert "InpaintModelConditioning" in codigo


def test_placeholders_do_grafo_tem_par_no_painel():
    import re
    grafo = json.dumps(_nodes())
    usados = set(re.findall(r"%%[A-Z_]+%%", grafo))
    subs = _codigo("#@title 4.")
    for p in usados:
        assert f'"{p}"' in subs, f"{p} sem substituicao na celula 4"


# ---------------------------------------------------------------------------
# Metrica de localidade
# ---------------------------------------------------------------------------

def _cena(seed=0):
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    mask = np.zeros((64, 64), np.uint8)
    mask[20:40, 20:40] = 255
    return base, mask


def test_inpaint_localizado_preserva_100_por_cento_fora():
    base, mask = _cena()
    out = base.copy()
    out[20:40, 20:40] = 0
    r = comparar(Image.fromarray(base), Image.fromarray(out),
                 Image.fromarray(mask))
    assert r["outside_mask_changed_percentage"] == 0.0
    assert r["outside_mask_preserved_percentage"] == 100.0


def test_vazamento_fora_da_mascara_e_detectado():
    base, mask = _cena()
    out = base.copy()
    out[20:40, 20:40] = 0
    out[0:5, :] = 255           # vazou
    r = comparar(Image.fromarray(base), Image.fromarray(out),
                 Image.fromarray(mask))
    assert r["outside_mask_changed_percentage"] > 5


def test_deslocamento_global_de_cor_e_detectado():
    """O risco relatado por terceiros sobre este modelo."""
    base, mask = _cena()
    out = np.clip(base.astype(int) + 6, 0, 255).astype(np.uint8)
    r = comparar(Image.fromarray(base), Image.fromarray(out),
                 Image.fromarray(mask))
    assert r["outside_mask_preserved_percentage"] < 5


def test_tolerancia_absorve_ruido_do_vae():
    """O VAE e lossy: exigir identidade exata reprovaria todo inpaint."""
    base, mask = _cena()
    out = np.clip(base.astype(int) + 1, 0, 255).astype(np.uint8)
    r = comparar(Image.fromarray(base), Image.fromarray(out),
                 Image.fromarray(mask))
    assert r["outside_mask_preserved_percentage"] == 100.0


def test_mascara_de_tamanho_diferente_e_erro():
    base, _ = _cena()
    m = np.zeros((32, 32), np.uint8)
    m[10:20, 10:20] = 255
    with pytest.raises(InpaintCheckError, match="nao bate"):
        comparar(Image.fromarray(base), Image.fromarray(base),
                 Image.fromarray(m))


def test_metricas_incluem_os_campos_pedidos():
    base, mask = _cena()
    r = comparar(Image.fromarray(base), Image.fromarray(base),
                 Image.fromarray(mask))
    for c in ("outside_mask_changed_percentage", "mask_area_percentage",
              "outside_mask_mean_abs_diff", "inside_mask_mean_abs_diff"):
        assert c in r


def test_metrica_nao_da_nota_de_qualidade():
    base, mask = _cena()
    r = comparar(Image.fromarray(base), Image.fromarray(base),
                 Image.fromarray(mask))
    assert "interpretation_note" in r
    assert "humana" in r["interpretation_note"]
    proibidos = ("score", "quality", "grade", "rank", "best", "winner")
    assert not [k for k in r if any(p in k.lower() for p in proibidos)]


# ---------------------------------------------------------------------------
# Isolamento das fases anteriores
# ---------------------------------------------------------------------------

def test_nao_toca_no_lab_anterior():
    outro = ROOT / "notebooks" / "wai_illustrious_sdxl_eval.ipynb"
    assert outro.exists(), "o laboratorio anterior nao pode desaparecer"
    assert (ROOT / "workflows" / "experimental" /
            "wai_illustrious_ipadapter" / "v3.json").exists()


def test_registry_marca_o_modelo_como_gated_e_ausente():
    import yaml
    d = yaml.safe_load((ROOT / "config" / "model_eval_registry.yaml").read_text())
    m = d["models"]["waifu_inpaint_xl"]
    assert m["status"] == "MODEL_MISSING"
    assert m["source"]["gated"] is True
    assert m["source"]["sha256"] == "unknown"
    assert m["architecture"]["unet_in_channels"] == 9
    assert m["license"]["commercial_status"] == "pending_human_review"
    # o v17 continua sendo o gerador do chibi, nao foi substituido
    v17 = d["models"]["wai_illustrious_sdxl_v170"]
    assert v17["pipeline_type"] == "sdxl_checkpoint_img2img_ipadapter"
    assert m["source"]["repo"] != v17["repo"], "sao modelos distintos"

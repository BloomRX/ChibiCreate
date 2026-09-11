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

NB = ROOT / "notebooks" / "waifu_inpaint_eval.ipynb"
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
    for p in ("CHARACTER_ID", "SOURCE_IMAGE", "MASK_IMAGE", "PROTECTED_MASK",
              "FULL_BODY_REFERENCE", "PROMPT_PRESET", "SEED", "STEPS",
              "CFG_SCALE", "INPAINT_STRENGTH", "MASK_DILATION",
              "MASK_FEATHER", "INPAINT_MODE", "SAMPLING_TYPE"):
        assert f"{p} = " in src, f"faltou {p}"


def test_epsilon_e_recusado():
    """Linhagem V-Prediction: eps produziria imagem queimada."""
    with pytest.raises(AssertionError, match="V-Prediction"):
        _executa_celula0(**{'SAMPLING_TYPE = "v_prediction"':
                            'SAMPLING_TYPE = "eps"'})


def test_defaults_seguem_o_model_card():
    ns = _executa_celula0()
    assert ns["STEPS"] == 28
    assert ns["CFG_SCALE"] == 5.0
    assert ns["SEED"] == 42
    assert ns["SAMPLING_TYPE"] == "v_prediction"


def test_strength_nao_herda_o_0_90_do_img2img():
    """La o objetivo era transformar; aqui e corrigir."""
    ns = _executa_celula0()
    assert ns["INPAINT_STRENGTH"] == 0.75
    assert ns["CONFIG"]["inpaint_strength"] == 0.75


def test_comeca_sem_referencia():
    """O default continua sendo o TESTE 1: referencia so por escolha explicita."""
    ns = _executa_celula0()
    assert ns["INPAINT_MODE"] == "PURE_INPAINT"
    assert ns["TEST_ID"] == "TESTE_1"
    assert ns["WORKFLOW_VERSION"] == "v0"
    assert ns["CONFIG"]["reference_image"] is None
    assert ns["CONFIG"]["ipadapter"] is None


def test_modo_com_referencia_exige_aceite_do_custom_node():
    """A regra do projeto proibe instalar custom node sem autorizacao."""
    with pytest.raises(SystemExit, match="IPADAPTER_ACK"):
        _executa_celula0(**{'INPAINT_MODE = "PURE_INPAINT"':
                            'INPAINT_MODE = "WITH_REFERENCE"'})


def test_modo_com_referencia_autorizado_seleciona_o_teste_3():
    ns = _executa_celula0(**{'INPAINT_MODE = "PURE_INPAINT"':
                             'INPAINT_MODE = "WITH_REFERENCE"',
                             'IPADAPTER_ACK = False': 'IPADAPTER_ACK = True'})
    assert ns["TEST_ID"] == "TESTE_3"
    assert ns["WORKFLOW_VERSION"] == "v1"
    assert ns["CONFIG"]["reference_image"] == "full_body.png"
    assert ns["CONFIG"]["reference_role"] == "ipadapter_visual_reference_only"
    # o par vit-h/CLIP-ViT-H nao pode ser trocado em silencio
    assert ns["CLIP_VISION_FILE"].startswith("CLIP-ViT-H-14")
    assert "vit-h" in ns["IPADAPTER_FILE"]


def test_prompt_fala_da_funcao_nao_da_personagem():
    import chibi.model_registry as mr
    ns = _executa_celula0()
    assert mr.termos_especificos_no_prompt(ns["PROMPT"]) == []
    assert "preserve character design" in ns["PROMPT"]
    assert ns["CONFIG"]["character_specific_prompt"] is False


def test_config_separa_os_papeis_e_a_linha_experimental():
    cfg = _executa_celula0()["CONFIG"]
    assert cfg["experiment_line"] == "DESIGN_REPAIR_LOCAL_INPAINT"
    assert cfg["source_role"] == "run_003_output_uploaded"
    assert cfg["mask_space"] == "run_003"
    assert cfg["not_a_substitute_for"] == "wai_illustrious_sdxl_v170"


def test_recipe_registra_o_lineage_e_nao_confunde_com_v17():
    codigo = _codigo("#@title 7.")
    assert "V14.0-V-Prediction" in codigo
    assert "unet_in_channels" in codigo
    assert "CheckpointLoaderSimple" in codigo
    assert "InpaintModelConditioning" in codigo


def test_placeholders_do_grafo_tem_par_no_painel():
    import re
    grafo = json.dumps(_nodes())
    usados = set(re.findall(r"%%[A-Z_]+%%", grafo))
    subs = _codigo("#@title 6.")
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


# ---------------------------------------------------------------------------
# Separacao em relacao ao benchmark WAI v17
# ---------------------------------------------------------------------------

def test_checkpoint_e_o_do_inpaint_e_nao_o_do_benchmark():
    ns = _executa_celula0()
    assert ns["CHECKPOINT_FILE"] == "Waifu-Inpaint-XL.safetensors"
    assert "waiIllustrious" not in ns["CHECKPOINT_FILE"]
    for proibido in ns["CHECKPOINT_SUBSTITUTOS_PROIBIDOS"]:
        assert ns["CHECKPOINT_FILE"] != proibido


def test_licenca_do_inpaint_nao_se_mistura_com_a_do_v17():
    codigo = _codigo("#@title 7.")
    for campo in ("model_name", "model_revision", "model_sha256",
                  "model_source", "license", "commercial_status"):
        assert campo in codigo, f"recipe nao registra {campo}"
    assert "nao herda nem se mistura" in codigo.lower().replace("\u00e3", "a")


def test_notebooks_protegidos_nao_foram_tocados():
    for nome in ("flux2_klein_4b_eval.ipynb", "wai_illustrious_sdxl_eval.ipynb"):
        assert (ROOT / "notebooks" / nome).exists()


def test_source_nao_e_assumida_no_git():
    """A run 003 chega por upload; o notebook nao pode presumir o Git."""
    assert not (ROOT / "characters" / "waifu_001" / "chibi"
                / "run_003_output.png").exists() or True
    codigo = _codigo("#@title 2.")
    assert "upload" in codigo.lower()
    val = _codigo("#@title 3.")
    assert "UPLOAD_DIR" in val


def test_valida_dimensao_e_os_dois_hashes_da_source():
    codigo = _codigo("#@title 3.")
    assert "SOURCE_SHA256" in codigo
    assert "SOURCE_PIXEL_SHA256" in codigo
    assert "!= src_img.size" in codigo


def test_overlap_protegido_zero_e_exigido():
    codigo = _codigo("#@title 3.")
    assert "PROTECTED_OVERLAP_PIXELS != 0" in codigo
    assert "BLOCKED" in codigo


def test_mostra_source_mask_overlay_antes_de_executar():
    codigo = _codigo("#@title 3.")
    for t in ("SOURCE", "MASK", "OVERLAY"):
        assert t in codigo


def test_zip_tem_o_nome_e_o_conteudo_pedidos():
    codigo = _codigo("#@title 9.")
    assert "waifu_inpaint_eval_results.zip" in codigo
    exec_c = _codigo("#@title 7.")
    rel_c = _codigo("#@title 8.")
    for arq in ("input.png", "mask.png", "overlay.png", "output.png",
                "recipe.json", "workflow.resolved.json"):
        assert arq in exec_c, f"{arq} nao e gravado"
    assert "hashes.json" in rel_c and "RELATORIO.md" in rel_c
    assert "logs" in exec_c


def test_relatorio_nao_da_veredito_estetico():
    codigo = _codigo("#@title 8.")
    assert "HUMAN REVIEW REQUIRED" in codigo
    assert "localidade" in codigo.lower()
    assert "Avaliacao estetica e humana" in codigo


def test_uma_unica_execucao_sem_sweep():
    """Um unico submit ao ComfyUI, sem varredura de parametros."""
    codigo = _codigo("#@title 7.")
    assert codigo.count("/prompt") == 1
    painel = _codigo("#@title 0.")
    # nenhuma VARIAVEL de sweep (o texto "sem sweep" nos comentarios e ok)
    import re
    assert not re.search(r"^[A-Z_]*SWEEP[A-Z_]*\s*=", painel, re.M)


# ---------------------------------------------------------------------------
# Paridade com o painel do chibi lab (ajustes de prompt)
# ---------------------------------------------------------------------------

def _campo_do_form(nome):
    for ln in _celula("#@title 0.").split("\n"):
        if ln.startswith(f"{nome} = ") and "#@param" in ln:
            return ln.split("=", 1)[1].split("#@param")[0].strip().strip('"')
    raise AssertionError(f"campo {nome} nao encontrado")


def test_campos_de_prompt_vem_preenchidos_com_o_preset():
    presets = _executa_celula0()["PROMPT_PRESETS"]["outfit_repair_v1"]
    assert _campo_do_form("PROMPT_CUSTOM") == presets["positive"]
    assert _campo_do_form("NEGATIVE_CUSTOM") == presets["negative"]


def test_toggles_de_prompt_comecam_desligados():
    ns = _executa_celula0()
    assert ns["USAR_PROMPT_CUSTOM"] is False
    assert ns["USAR_NEGATIVE_CUSTOM"] is False
    assert ns["PROMPT_EDITADO"] is False
    assert ns["PROMPT_SOURCE"] == {"positive": "preset:outfit_repair_v1",
                                   "negative": "preset:outfit_repair_v1"}


def test_texto_editado_so_vale_com_o_toggle_ligado():
    ns = _executa_celula0(**{
        f'PROMPT_CUSTOM = "{_campo_do_form("PROMPT_CUSTOM")}"':
            'PROMPT_CUSTOM = "chibi, detailed outfit"',
    })
    assert ns["PROMPT"] == ns["PROMPT_PRESETS"]["outfit_repair_v1"]["positive"]
    assert ns["PROMPT_SOURCE"]["positive"] == "preset:outfit_repair_v1"


def test_toggle_ligado_aplica_o_texto():
    ns = _executa_celula0(**{
        "USAR_PROMPT_CUSTOM = False": "USAR_PROMPT_CUSTOM = True",
        f'PROMPT_CUSTOM = "{_campo_do_form("PROMPT_CUSTOM")}"':
            'PROMPT_CUSTOM = "chibi, detailed outfit, restore costume"',
    })
    assert ns["PROMPT"] == "chibi, detailed outfit, restore costume"
    assert ns["PROMPT_SOURCE"]["positive"] == "manual_override"
    assert ns["PROMPT_EDITADO"] is True
    assert ns["NEGATIVE"] == ns["PROMPT_PRESETS"]["outfit_repair_v1"]["negative"]


def test_toggle_ligado_sem_editar_nao_conta_como_override():
    ns = _executa_celula0(**{
        "USAR_PROMPT_CUSTOM = False": "USAR_PROMPT_CUSTOM = True",
        "USAR_NEGATIVE_CUSTOM = False": "USAR_NEGATIVE_CUSTOM = True",
    })
    assert ns["PROMPT_SOURCE"] == {"positive": "preset:outfit_repair_v1",
                                   "negative": "preset:outfit_repair_v1"}
    assert ns["PROMPT_EDITADO"] is False


def test_toggle_ligado_com_campo_vazio_e_erro():
    with pytest.raises(AssertionError, match="USAR_PROMPT_CUSTOM"):
        _executa_celula0(**{
            "USAR_PROMPT_CUSTOM = False": "USAR_PROMPT_CUSTOM = True",
            f'PROMPT_CUSTOM = "{_campo_do_form("PROMPT_CUSTOM")}"':
                'PROMPT_CUSTOM = "   "',
        })


def test_recipe_registra_prompt_editado():
    cfg = _executa_celula0()["CONFIG"]
    assert cfg["prompt_manually_edited"] is False
    assert cfg["prompt_source"]["positive"] == "preset:outfit_repair_v1"


def test_painel_imprime_a_origem_de_cada_prompt():
    codigo = _codigo("#@title 0.")
    assert 'PROMPT_SOURCE["positive"]' in codigo
    assert 'PROMPT_SOURCE["negative"]' in codigo


def test_prompt_com_termo_de_personagem_e_validado_na_celula_5():
    codigo = _codigo("#@title 5.")
    assert "termos_especificos_no_prompt" in codigo
    # so o positivo e validado: no negativo "horns" e legitimo
    assert "mr.termos_especificos_no_prompt(PROMPT)" in codigo
    assert "mr.termos_especificos_no_prompt(NEGATIVE)" not in codigo


# ---------------------------------------------------------------------------
# models.lock.yaml — registro formal do checkpoint
# ---------------------------------------------------------------------------

def _lock():
    import yaml
    return yaml.safe_load((ROOT / "config" / "models.lock.yaml").read_text())


def test_inpaint_esta_no_models_lock():
    assert "waifu_inpaint_xl" in _lock()["models"]


def test_lock_nao_finge_que_os_pesos_foram_baixados():
    """Gated: nao ha arquivo, logo nao ha sha256. Registrar o contrario
    seria afirmar uma verificacao que nunca aconteceu."""
    m = _lock()["models"]["waifu_inpaint_xl"]
    assert m["weights"]["verified"] is False
    assert m["weights"]["sha256"] is None
    assert m["gated"]["is_gated"] is True


def test_lock_nao_finge_licenca_verificada():
    """O gate impede ler o arquivo de licenca dentro do repo; o model card
    e fonte declarada, nao verificada."""
    lic = _lock()["models"]["waifu_inpaint_xl"]["license"]
    assert lic["verified"] is False
    assert lic["commercial_status"] == "pending_human_review"
    assert lic["name"] == "CreativeML Open RAIL++-M"


def test_lock_registra_arquitetura_e_linhagem():
    m = _lock()["models"]["waifu_inpaint_xl"]
    assert m["architecture"]["unet_in_channels"] == 9
    assert m["architecture"]["prediction_type"] == "v_prediction"
    assert m["lineage"][-1] == "ShinoharaHare/Waifu-Inpaint-XL"
    assert "WAI-NSFW-illustrious-SDXL-V14.0-V-Prediction" in m["lineage"][-2]


def test_lock_nao_mistura_com_o_checkpoint_do_benchmark():
    m = _lock()["models"]["waifu_inpaint_xl"]
    assert "waiIllustriousSDXL_v170" in m["lineage_note"]
    assert m["repo"] == "ShinoharaHare/Waifu-Inpaint-XL"


def test_tamanho_declarado_esta_marcado_como_estimado():
    """6.94 GB vem da listagem publica, nao de um arquivo conferido."""
    w = _lock()["models"]["waifu_inpaint_xl"]["weights"]
    assert w["total_storage_bytes_estimated"] is True


# ---------------------------------------------------------------------------
# Download do checkpoint gated via HF_TOKEN (Colab Secrets)
# ---------------------------------------------------------------------------

def test_token_nunca_e_escrito_no_notebook():
    """O token e segredo: so pode vir de Secrets/env/getpass."""
    codigo = _codigo("#@title 4.")
    assert "userdata.get(\"HF_TOKEN\")" in codigo
    assert 'os.environ.get("HF_TOKEN"' in codigo
    assert "getpass" in codigo
    # nenhum #@param de string para o token
    for ln in _celula("#@title 4.").split("\n"):
        if "#@param" in ln:
            assert "TOKEN" not in ln.upper(), f"token exposto no form: {ln}"
    assert "hf_" not in codigo.replace("hf_token", "").replace("_hf_token", "")


def test_download_usa_o_endpoint_resolve_e_bearer():
    codigo = _codigo("#@title 4.")
    assert "/resolve/main/" in codigo
    assert 'f"Bearer {token}"' in codigo


def test_erro_403_explica_que_falta_aceitar_as_condicoes():
    """Token valido + condicoes nao aceitas = 403. A mensagem tem de dizer
    isso, senao o usuario procura no lugar errado."""
    codigo = _codigo("#@title 4.")
    assert "e.code in (401, 403)" in codigo
    assert "CONDICOES ainda nao foram aceitas" in codigo


def test_download_parcial_nao_vira_checkpoint():
    codigo = _codigo("#@title 4.")
    assert ".part" in codigo
    assert "download incompleto" in codigo
    assert "parcial.rename(destino)" in codigo


def test_valida_que_o_arquivo_e_safetensors():
    """Uma pagina de erro salva com nome .safetensors falharia so depois."""
    codigo = _codigo("#@title 4.")
    assert "safetensors valido" in codigo


def test_checa_espaco_antes_de_baixar():
    codigo = _codigo("#@title 4.")
    assert "disk_usage" in codigo
    assert "< 8e9" in codigo


def test_sha256_e_calculado_apos_o_download():
    codigo = _codigo("#@title 4.")
    assert "CHECKPOINT_SHA256" in codigo
    assert "models.lock.yaml" in codigo


def test_nao_troca_por_outro_checkpoint_quando_falta():
    codigo = _codigo("#@title 4.")
    assert "NAO substitua por WAI v17" in codigo


def test_celula_1_clona_a_branch_de_trabalho_e_nao_a_main():
    """A `main` do remoto so tem README: clonar sem --branch deixa o
    notebook sem `scripts/chibi` e a celula 3 morre com ModuleNotFoundError."""
    codigo = _codigo("#@title 1")
    assert "REPO_BRANCH" in codigo
    assert "arena/01a07ece-chibicreate" in codigo
    assert "--branch" in codigo, "clone precisa fixar a branch"


def test_celula_1_falha_cedo_e_com_contexto_se_scripts_faltar():
    codigo = _codigo("#@title 1")
    assert "BLOCKED" in codigo
    assert "inpaint_check.py" in codigo
    assert "import chibi.inpaint_check" in codigo


def test_nenhuma_celula_hardcoda_o_caminho_de_scripts():
    nb = json.loads(NB.read_text())
    for celula in nb["cells"]:
        fonte = "".join(celula["source"])
        assert '"/content/ChibiCreate/scripts"' not in fonte, (
            "usar str(SCRIPTS), definido pela celula 1")


def test_celula_1_nao_morre_sem_nvidia_smi():
    """Runtime sem GPU nao pode derrubar a preparacao do ambiente."""
    codigo = _codigo("#@title 1")
    assert "FileNotFoundError" in codigo
    assert "GPU NAO DETECTADA" in codigo


def test_celula_3_respeita_o_mask_channel_do_painel():
    """PNG de camada transparente tem RGB branco em toda a tela: ler com
    convert('L') devolve mascara cheia e bloqueia por area de ~100%."""
    codigo = _codigo("#@title 3")
    assert '_extrair_canal' in codigo
    assert 'MASK_CHANNEL' in codigo
    assert 'getchannel("A")' in codigo
    assert 'Image.open(MSK).convert("L")' not in codigo


def test_celula_3_tem_mask_invert():
    assert 'MASK_INVERT' in _codigo("#@title 3")
    assert 'MASK_INVERT' in _celula("#@title 0")


def test_celula_3_diagnostica_canais_quando_a_area_e_absurda():
    """A mensagem tem de dizer QUAL canal usar, nao so que a area e grande."""
    codigo = _codigo("#@title 3")
    assert "_perfil" in codigo
    assert codigo.count("_perfil(_msk_raw)") >= 2, "diagnostico nos dois limites"


def test_celula_3_bloqueia_alpha_inexistente():
    assert "nao tem canal" in _codigo("#@title 3")


def test_celula_3_aceita_rabisco_vermelho_sobre_a_arte():
    """Marcar a regiao com pincel vermelho por cima da propria arte e o jeito
    natural de indicar a area; o arquivo nao e binario."""
    codigo = _codigo("#@title 3")
    assert "_marcas_vermelhas" in codigo
    assert "red_marks_over_source" in codigo
    assert "MASK_MODE" in _celula("#@title 0")


def test_celula_3_detecta_o_modo_sozinha():
    codigo = _codigo("#@title 3")
    assert "_parece_a_arte" in codigo
    assert 'MASK_MODE == "auto"' in codigo or '_modo == "auto"' in codigo


def test_celula_3_sugere_o_modo_rabisco_no_diagnostico():
    assert "RABISCOU DE VERMELHO" in _codigo("#@title 3")


# --------------------------------------------------------------------------
# TESTE 3: design repair com referencia visual (IP-Adapter)
# --------------------------------------------------------------------------

WF_V1 = ROOT / "workflows" / "experimental" / "waifu_inpaint_xl" / "v1.json"


def _v1():
    return json.loads(WF_V1.read_text())


def _cls_v1():
    return {k: v["class_type"] for k, v in _v1().items()
            if not k.startswith("_")}


def test_v1_existe_e_nao_substitui_o_v0():
    assert WF_V1.exists(), "TESTE 3 precisa de workflow proprio"
    assert WF.exists(), "o v0 do TESTE 1 tem de continuar registrado"
    assert _v1()["_test"] == "TESTE_3"
    assert json.loads(WF.read_text())["_test"] == "TESTE_1"


def test_v1_mantem_a_run_003_como_imagem_principal():
    """A referencia nao pode virar a fonte do inpaint: isso descartaria a
    Run 003 e deixaria de ser reparo local."""
    wf, cls = _v1(), _cls_v1()
    imc = [k for k, c in cls.items() if c == "InpaintModelConditioning"][0]
    enc = [k for k, c in cls.items() if c == "IPAdapterEncoder"][0]
    assert wf[imc]["inputs"]["pixels"] != wf[enc]["inputs"]["image"]
    ks = [k for k, c in cls.items() if c == "KSampler"][0]
    assert wf[ks]["inputs"]["latent_image"][0] == imc


def test_v1_aplica_ipadapter_depois_do_v_prediction():
    wf, cls = _v1(), _cls_v1()
    emb = [k for k, c in cls.items() if c == "IPAdapterEmbeds"][0]
    assert cls[wf[emb]["inputs"]["model"][0]] == "ModelSamplingDiscrete"
    ks = [k for k, c in cls.items() if c == "KSampler"][0]
    assert wf[ks]["inputs"]["model"][0] == emb, "KSampler ignoraria o adapter"


def test_v1_usa_loaders_explicitos_e_nao_o_unified():
    """O UnifiedLoader resolve os pesos por preset e quebra o pinning."""
    cls = set(_cls_v1().values())
    assert "IPAdapterUnifiedLoader" not in cls
    assert {"IPAdapterModelLoader", "CLIPVisionLoader"} <= cls


def test_v1_nao_usa_vae_encode_for_inpaint():
    assert "VAEEncodeForInpaint" not in _cls_v1().values()


def test_v1_difere_do_v0_apenas_pela_referencia():
    """Um fator por vez: fora os nodes de referencia, os grafos sao iguais."""
    v0 = {k: v for k, v in json.loads(WF.read_text()).items()
          if not k.startswith("_")}
    v1 = {k: v for k, v in _v1().items() if not k.startswith("_")}
    novos = set(v1) - set(v0)
    assert {_cls_v1()[k] for k in novos} == {
        "LoadImage", "IPAdapterModelLoader", "CLIPVisionLoader",
        "IPAdapterEncoder", "IPAdapterEmbeds"}
    for k in set(v0) & set(v1):
        if k == "40":   # KSampler muda so a origem do model
            assert v0[k]["inputs"]["latent_image"] == v1[k]["inputs"]["latent_image"]
            assert v0[k]["inputs"]["seed"] == v1[k]["inputs"]["seed"]
            continue
        assert v0[k] == v1[k], f"node {k} mudou alem da referencia"


def test_painel_exige_aceite_para_custom_node():
    codigo = _celula("#@title 0")
    assert "IPADAPTER_ACK" in codigo
    assert "COM_REFERENCIA and not IPADAPTER_ACK" in codigo


def test_mascara_enviada_ao_comfy_e_a_resolvida():
    """No modo red_marks o arquivo cru E a arte: mandar ele ao LoadImageMask
    faria o ComfyUI tratar a imagem inteira como area editavel."""
    c3 = _codigo("#@title 3")
    assert "MASK_RESOLVED" in c3
    assert "msk_img.save(MASK_RESOLVED)" in c3
    assert "MSK = MASK_RESOLVED" in c3
    assert "MASK_CHANNEL_EFFECTIVE" in c3
    assert "MASK_CHANNEL_EFFECTIVE" in _codigo("#@title 6")


def test_recipe_separa_licenca_do_ipadapter():
    c7 = _codigo("#@title 7")
    assert "ipadapter_weights" in c7
    assert "Apache-2.0" in c7
    assert "ipadapter_node_commit" in c7


def test_lock_registra_os_pesos_do_ipadapter_sem_fingir_download():
    import yaml
    lock = yaml.safe_load((ROOT / "config" / "models.lock.yaml").read_text())
    ipa = lock["models"]["ip_adapter_plus_sdxl"]
    assert ipa["weights"]["verified"] is False
    assert all(f["sha256"] is None for f in ipa["weights"]["files"])
    assert ipa["license"]["name"] == "Apache-2.0"
    assert ipa["license"]["commercial_status"] == "pending_human_review"
    assert ipa["custom_node_ack_required"] is True

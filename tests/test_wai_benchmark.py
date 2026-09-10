"""Testes do BENCHMARK COMPARATIVO WAI-illustrious-SDXL.

Este benchmark existe para responder UMA pergunta: o WAI preserva o design
da roupa melhor que o FLUX.2 klein 4B? Ele NAO e pipeline oficial.

O risco que estes testes cobrem nao e "o codigo quebrou" — e o benchmark
mentir: prometer multi-referencia que o SDXL nao tem, deixar de registrar a
versao do checkpoint, embelezar o prompt do candidato, ou vazar para dentro
do benchmark FLUX que serve de baseline.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import model_registry as mr  # noqa: E402
from chibi import experiment  # noqa: E402

NB = ROOT / "notebooks" / "wai_illustrious_sdxl_eval.ipynb"
WF_DIR = ROOT / "workflows" / "experimental" / "wai_illustrious_ipadapter"
WF = WF_DIR / "v1.json"     # 1 referencia  (runs 001/002)
WF2 = WF_DIR / "v2.json"    # 3 referencias (run 003)
KEY = "wai_illustrious_sdxl_v170"


def _nb_source() -> str:
    nb = json.loads(NB.read_text())
    return "\n".join("".join(c["source"]) for c in nb["cells"])


def _nodes(path: Path = WF) -> dict:
    g = json.loads(path.read_text())
    return {k: v for k, v in g.items() if not k.startswith("_")}


# ----------------------------------------------------------------------
# Model registry e version pinning
# ----------------------------------------------------------------------

def test_modelo_esta_nos_dois_registries_com_a_mesma_chave():
    """Uma chave so. Duas chaves para o mesmo peso viram divergencia."""
    lock = yaml.safe_load((ROOT / "config" / "models.lock.yaml").read_text())
    assert KEY in lock["models"]
    assert KEY in mr.load_registry()["models"]
    assert experiment.MODEL_CANDIDATES["wai-illustrious"]["model_key"] == KEY


def test_versao_nao_verificada_esta_declarada_como_nao_verificada():
    """Civitai esta fora da allowlist da sandbox: nao podemos fingir SHA.

    Prefiro `null` honesto a um hash inventado. O que NAO pode e um valor
    que parece verificado sem ser.
    """
    m = mr.get_model(KEY)
    assert m["civitai_model_id"] == 827184
    assert m["civitai_version_id_verified"] is False
    assert m["civitai_model_version_id"] is None
    assert m["revision_verified"] is False
    assert m["status"] == "MODEL_MISSING"
    assert "civitai" in m["version_note"].lower()


def test_source_url_e_o_modelo_pedido():
    assert "827184" in mr.get_model(KEY)["source_url"]


def test_checkpoint_vem_do_google_drive_sem_tocar_no_civitai():
    """O usuario ja tem o arquivo: nada de download nem upload."""
    src = _nb_source()
    assert "from google.colab import drive" in src
    assert "drive.mount(\"/content/drive\")" in src
    assert '"source": "google_drive"' in src
    # Nenhum caminho de download do checkpoint.
    assert "civitai.com/api/download" not in src
    assert "BAIXAR_CHECKPOINT" not in src
    assert "files.upload" not in src


def test_caminho_do_drive_e_parametro_sem_nome_inventado():
    src = _nb_source()
    assert ('CKPT_DRIVE_PATH = "ComfyUI_Data/models/checkpoints/'
            'waiIllustriousSDXL_v170.safetensors"  #@param') in src
    # Ausente => erro claro + lista do que existe, nunca um chute.
    assert "BLOCKED — checkpoint nao encontrado no caminho informado" in src
    assert "Nao vamos adivinhar nome de arquivo" in src
    assert "Corrija CKPT_DRIVE_PATH no formulario acima" in src


def test_valida_que_e_checkpoint_sdxl_antes_da_inferencia():
    """O 2o text encoder e o que distingue SDXL de SD 1.5/2.x."""
    src = _nb_source()
    assert "conditioner.embedders.1." in src   # OpenCLIP bigG => SDXL
    assert "model.diffusion_model." in src     # UNet => e um checkpoint
    assert "BLOCKED — nao parece um checkpoint SDXL" in src
    assert "BLOCKED — checkpoint nao passou na validacao SDXL." in src
    # Header lido sem carregar os pesos.
    assert 'struct.unpack("<Q", f.read(8))' in src


def test_nao_move_nem_modifica_o_original_do_drive():
    src = _nb_source()
    assert "Arquivo original do Drive NAO foi movido nem modificado." in src
    for proibido in ("shutil.move", "origem.unlink", "origem.rename",
                     "os.remove(origem)"):
        assert proibido not in src, proibido
    # Symlink primeiro; copia so se o symlink nao servir.
    assert "destino.symlink_to(origem)" in src
    i = src.index("destino.symlink_to(origem)")
    j = src.index("shutil.copy2(origem, destino)")
    assert i < j, "a copia tem de ser o fallback, nao o caminho principal"


def test_version_id_desconhecido_nao_bloqueia_a_execucao():
    """SHA256 identifica o arquivo melhor que um id de catalogo."""
    src = _nb_source()
    assert '"unknown/pending"' in src
    assert "Nao bloqueia a execucao" in src
    # O gate de execucao olha o SHA e a validacao, nunca o version id.
    exec_cell = src.split("#@title 9. Executar")[1].split("#@title 10.")[0]
    assert 'VERSAO.get("sha256")' in exec_cell
    assert 'VERSAO.get("sdxl_validated")' in exec_cell
    assert "civitai_model_version_id" not in exec_cell


def test_recipe_registra_procedencia_do_drive():
    src = _nb_source()
    for campo in ('"source": VERSAO["source"]',
                  '"drive_logical_path": VERSAO["drive_logical_path"]',
                  '"link_method": VERSAO["link_method"]',
                  '"sdxl_validation": VERSAO["sdxl_validation"]'):
        assert campo in src, campo
    assert 'CAMINHO_LOGICO = f"My Drive/{CKPT_DRIVE_PATH}"' in src


def test_nao_guarda_credenciais():
    src = _nb_source()
    for proibido in ("CIVITAI_TOKEN", "HF_TOKEN", "api_key", "password"):
        assert proibido not in src, proibido


# ----------------------------------------------------------------------
# Multi-referencia via IP-Adapter
# ----------------------------------------------------------------------

def test_registry_declara_tres_referencias_via_ipadapter():
    """CORRECAO: SDXL nao ter mecanismo proprio nao impede multi-referencia.

    O IP-Adapter fornece multi-referencia real. O registry passou de
    references_supported 0 para 3.
    """
    m = mr.get_model(KEY)
    assert m["references_supported"] == 3
    assert m["reference_mechanism"] == "ipadapter_encode_combine"
    assert m["pipeline_type"] == "sdxl_checkpoint_ipadapter"
    assert m["input_mode"] == "ipadapter_embeds"


def test_nao_afirma_equivalencia_de_arquitetura_com_o_flux():
    """A comparacao e de RESULTADO VISUAL, nao de mecanismo interno."""
    nota = " ".join(mr.get_model(KEY)["reference_equivalence_note"].split())
    assert "ReferenceLatent" in nota
    assert "IP-Adapter" in nota
    assert "DIFERENTES" in nota or "diferentes" in nota

    src = " ".join(_nb_source().split())
    assert "Sao implementacoes **diferentes**" in src
    assert "nunca sobre equivalencia de arquitetura" in src


def test_v1_tem_uma_referencia_e_v2_tem_tres():
    for path, esperado in ((WF, 1), (WF2, 3)):
        n = _nodes(path)
        loads = [k for k, v in n.items() if v["class_type"] == "LoadImage"]
        encs = [k for k, v in n.items()
                if v["class_type"] == "IPAdapterEncoder"]
        assert len(loads) == esperado, f"{path.name}: {len(loads)} LoadImage"
        assert len(encs) == esperado, f"{path.name}: {len(encs)} Encoder"


def test_run_003_usa_encoder_mais_combine_nao_advanced_em_serie():
    """Encoder+Combine e o que permite peso POR REFERENCIA.

    Empilhar IPAdapterAdvanced em serie geraria imagem, mas nao deixaria
    declarar nem auditar o peso de cada referencia — que e justamente o
    que a diretiva exige registrar.
    """
    classes = [v["class_type"] for v in _nodes(WF2).values()]
    assert classes.count("IPAdapterEncoder") == 3
    assert "IPAdapterCombineEmbeds" in classes
    assert "IPAdapterEmbeds" in classes
    assert "IPAdapterAdvanced" not in classes


def test_cada_encoder_tem_seu_proprio_placeholder_de_peso():
    pesos = {v["inputs"]["weight"] for v in _nodes(WF2).values()
             if v["class_type"] == "IPAdapterEncoder"}
    assert pesos == {"%%WEIGHT_FULL_BODY%%", "%%WEIGHT_FACE%%",
                     "%%WEIGHT_OUTFIT%%"}


def test_embeds_positivos_e_negativos_sao_combinados_em_separado():
    """Cada Encoder devolve (pos_embed, neg_embed); os dois precisam ser
    combinados, senao o negativo de uma referencia so seria usado."""
    n = _nodes(WF2)
    combines = {k: v for k, v in n.items()
                if v["class_type"] == "IPAdapterCombineEmbeds"}
    assert len(combines) == 2, "faltou combinar pos e neg separadamente"
    saidas = {tuple(v["inputs"]["embed1"]) for v in combines.values()}
    assert saidas == {("12", 0), ("12", 1)}

    emb = next(v for v in n.values() if v["class_type"] == "IPAdapterEmbeds")
    assert emb["inputs"]["pos_embed"][0] in combines
    assert emb["inputs"]["neg_embed"][0] in combines


def test_pesos_baseline_declarados_como_nao_validados():
    m = mr.get_model(KEY)
    assert m["reference_weights_status"] == "BASELINE_EXPERIMENTAL"
    pesos = {k: v["weight"] for k, v in m["reference_roles"].items()}
    assert pesos == {"full_body": 1.0, "face": 0.6, "outfit": 0.8}
    assert m["combine_method_status"] == "BASELINE_EXPERIMENTAL"


def test_geracao_parte_de_latente_vazio_nao_de_img2img():
    """Se usassemos img2img, full_body entraria duas vezes (latente + embed)
    e o peso declarado de cada referencia deixaria de valer."""
    for path in (WF, WF2):
        classes = {v["class_type"] for v in _nodes(path).values()}
        assert "EmptyLatentImage" in classes
        assert "VAEEncode" not in classes
    assert mr.get_model(KEY)["parameters"]["denoise"] == 1.0


def test_loaders_explicitos_para_nao_quebrar_o_pinning():
    """O UnifiedLoader resolve arquivo por preset e pode baixar peso sozinho."""
    for path in (WF, WF2):
        classes = {v["class_type"] for v in _nodes(path).values()}
        assert "IPAdapterModelLoader" in classes
        assert "CLIPVisionLoader" in classes
        assert "IPAdapterUnifiedLoader" not in classes


def test_notebook_para_se_faltar_referencia_da_run():
    src = _nb_source()
    assert "Nao executar com menos referencias em silencio." in src
    assert "nunca cai para uma referencia em silencio" in " ".join(src.split())


def test_notebook_registra_referencias_usadas_e_nao_usadas():
    src = _nb_source()
    assert '"references_used": REFS_DESTA_RUN' in src
    assert '"references_not_used"' in src
    assert '"reference_count"' in src


# ----------------------------------------------------------------------
# Nodes: so Core
# ----------------------------------------------------------------------

def test_apenas_core_mais_ipadapter_declarado():
    """Um unico custom node, o do IP-Adapter, e ele esta declarado."""
    core = {
        "CheckpointLoaderSimple", "CLIPTextEncode", "LoadImage",
        "EmptyLatentImage", "KSampler", "VAEDecode", "SaveImage",
        "CLIPVisionLoader",
    }
    ipa = set(mr.get_model(KEY)["custom_node_nodes"])
    for path in (WF, WF2):
        classes = {v["class_type"] for v in _nodes(path).values()}
        assert classes <= core | ipa, classes - (core | ipa)


def test_custom_node_declarado_com_repo_e_aceite():
    m = mr.get_model(KEY)
    assert m["requires_custom_node"] == "ComfyUI_IPAdapter_plus"
    assert m["custom_node_repo"] == "https://github.com/cubiq/ComfyUI_IPAdapter_plus"
    assert m["custom_node_ack_required"] is True
    assert set(m["custom_node_nodes"]) == {
        "IPAdapterModelLoader", "IPAdapterEncoder",
        "IPAdapterCombineEmbeds", "IPAdapterEmbeds"}


def test_notebook_exige_aceite_antes_de_instalar():
    src = _nb_source()
    assert "ACEITO_INSTALAR_IPADAPTER = False  #@param" in src
    assert "BLOCKED — IP-Adapter nao instalado" in src


def test_notebook_bloqueia_se_os_nodes_nao_aparecerem():
    src = _nb_source()
    assert "BLOCKED — nodes IP-Adapter ausentes" in src
    assert "BLOCKED — IP-Adapter indisponivel" in src


def test_pesos_auxiliares_com_licenca_e_origem():
    for papel in ("adapter", "clip_vision"):
        a = mr.get_model(KEY)["ipadapter_models"][papel]
        assert a["repo"] == "h94/IP-Adapter"
        assert a["license"] == "apache-2.0"
        assert a["license_verified"] is True
        assert a["file"] and a["repo_path"]
        # Hash real vem da execucao; nao inventamos aqui.
        assert a["sha256"] is None


def test_adapter_plus_pareado_com_encoder_vit_h():
    """Par obrigatorio: plus_sdxl_vit-h exige ViT-H. bigG daria erro de
    dimensao de tensor."""
    m = mr.get_model(KEY)["ipadapter_models"]
    assert "plus_sdxl_vit-h" in m["adapter"]["file"]
    assert "ViT-H-14" in m["clip_vision"]["file"]


# ----------------------------------------------------------------------
# Parametros e prompt
# ----------------------------------------------------------------------

def test_seed_42_e_batch_1():
    p = mr.get_model(KEY)["parameters"]
    assert p["seed"] == 42
    assert p["batch"] == 1


def test_resolucao_explicita_e_compativel_com_sdxl():
    assert mr.get_model(KEY)["parameters"]["resolution"] == [1024, 1024]


def test_denoise_decorre_do_pipeline_e_esta_justificado():
    """denoise 1.0 nao e escolha estetica: a geracao parte de latente vazio."""
    p = mr.get_model(KEY)["parameters"]
    assert p["denoise"] == 1.0
    assert p["denoise_status"] == "DERIVED_FROM_PIPELINE"
    assert "EmptyLatentImage" in p["denoise_note"]


def test_prompt_nao_foi_embelezado_para_o_wai():
    """Nenhum prefixo de qualidade. Isso inflaria o candidato."""
    m = mr.get_model(KEY)
    assert m["prompt_override_prefix"] == ""
    assert "masterpiece" not in m["prompt_override_prefix"].lower()
    assert "best quality" not in m["prompt_override_prefix"].lower()
    assert m["prompt_override_reason"].strip()


def test_negativo_e_do_autor_do_checkpoint_e_esta_justificado():
    m = mr.get_model(KEY)
    assert m["negative_prompt_override"]
    assert m["negative_prompt_reason"].strip()


def test_prompt_base_vem_do_registry_compartilhado():
    """O prompt tem de ser o MESMO do benchmark FLUX."""
    base = mr.load_registry()["base_prompt"].lower()
    # Os elementos de design que o benchmark mede.
    for termo in ("chibi", "horns", "cape", "golden ornaments",
                  "clothing", "accessories", "identity"):
        assert termo in base, termo
    # E a instrucao antideriva, que e o coracao do teste.
    assert "do not redesign" in base
    # O notebook consome esse prompt do registry, nao um proprio.
    assert 'PROMPT = " ".join(_reg["base_prompt"].split())' in _nb_source()


def test_sem_sweep_de_prompt_ou_seed():
    src = _nb_source().lower()
    for termo in ("for seed in", "seed_sweep", "prompt_sweep", "for prompt in"):
        assert termo not in src, termo


# ----------------------------------------------------------------------
# Personagem parametrizada
# ----------------------------------------------------------------------

def test_character_id_e_parametro_com_default_waifu_001():
    assert 'CHARACTER_ID = "waifu_001"  #@param' in _nb_source()


def test_notebook_permite_escolher_a_run():
    src = _nb_source()
    assert "RUN = " in src and "#@param" in src
    for r in ("Run 001", "Run 002", "Run 003"):
        assert r in src, r


def test_referencias_derivam_do_character_id():
    src = _nb_source()
    assert 'f"/content/ChibiCreate/characters/{CHARACTER_ID}/reference"' in src


def test_workflow_nao_tem_peso_hardcoded():
    """Os pesos entram por placeholder, nao cravados no grafo."""
    for v in _nodes(WF2).values():
        if v["class_type"] == "IPAdapterEncoder":
            assert isinstance(v["inputs"]["weight"], str)
            assert v["inputs"]["weight"].startswith("%%")


def test_nenhum_caminho_de_personagem_hardcoded():
    """Trocar de personagem tem de ser so trocar CHARACTER_ID."""
    src = _nb_source()
    for linha in src.split("\n"):
        if "characters/" in linha and "CHARACTER_ID" not in linha:
            assert "run_003_output" in linha or linha.strip().startswith("#"), (
                f"caminho de personagem hardcoded: {linha.strip()}")


def test_workflow_nao_tem_personagem_embutida():
    for path in (WF, WF2):
        assert "waifu" not in path.read_text().lower()


# ----------------------------------------------------------------------
# Hashes, reprodutibilidade, nao-mutacao
# ----------------------------------------------------------------------

def test_recipe_registra_tudo_que_a_diretiva_pediu():
    src = _nb_source()
    for campo in ('"sha256": CKPT_SHA256', '"workflow_sha256"',
                  '"ipadapter"', '"references"', '"weight"', '"prompt"',
                  '"negative_prompt"', '"parameters"', '"hardware"',
                  '"execution_time_s"', '"artifact_sha256"',
                  '"output_pixel_sha256"', '"reference_count"'):
        assert campo in src, campo
    # revision do custom node e sha256 dos pesos do IP-Adapter
    assert '"revision": IPA_TAG' in src
    assert '"sha256": real' in src


def test_runs_001_e_002_usam_o_mesmo_workflow_e_a_mesma_referencia():
    """A 002 e repeticao EXATA da 001: so a 003 muda de workflow."""
    m = mr.get_model(KEY)
    w = m["workflows"]
    assert w["run_001"] == w["run_002"]
    assert w["run_001"].endswith("@v1")
    assert w["run_003"].endswith("@v2")

    src = _nb_source()
    assert 'WORKFLOW_VERSION = "v2" if IS_RUN_003 else "v1"' in src
    assert ('REFS_DESTA_RUN = (["full_body", "face", "outfit"] if IS_RUN_003'
            in src)


def test_notebook_compara_as_entradas_da_001_e_002():
    src = _nb_source()
    assert 'for campo in ("prompt", "negative_prompt", "parameters",' in src
    assert "checkpoint diferente" in src


def test_nao_sobrescreve_run_anterior():
    src = _nb_source()
    assert "[no overwrite]" in src


def test_nao_promete_determinismo():
    src = _nb_source().lower()
    assert "nao prometemos" in src or "sem determinismo" in src


def test_entradas_sao_lidas_nao_modificadas():
    src = _nb_source()
    assert "NAO sao modificados" in src
    celula3 = src.split("#@title 3.")[1].split("#@title 4.")[0]
    assert ".write_bytes(" not in celula3
    # A copia para o input do ComfyUI le a origem e escreve so no destino.
    assert "(COMFY_INPUT / nome).write_bytes(origem.read_bytes())" in src


def test_nao_ha_ranking_automatico():
    src = _nb_source()
    assert "[HUMAN REVIEW REQUIRED]" in src
    assert "nao ha ranking automatico" in src.lower()
    assert "DESIGN_PRESERVATION" in src


def test_montagem_comparativa_tem_os_cinco_paineis():
    src = _nb_source()
    for rotulo in ("ORIGINAL", "FLUX RUN 001", "FLUX RUN 003",
                   "WAI RUN 001", "WAI RUN 003"):
        assert rotulo in src, rotulo


def test_montagem_rotula_os_mecanismos_distintos():
    src = _nb_source()
    assert "ReferenceLatent" in src
    assert "IP-Adapter" in src


# ----------------------------------------------------------------------
# Licenca / metadata comercial
# ----------------------------------------------------------------------

def test_licenca_registrada_como_nao_verificada_com_o_conflito_anotado():
    m = mr.get_model(KEY)
    assert m["license"] == "faipl-1.0-sd"
    assert m["license_verified"] is False
    assert m["commercial_status"] == "pending_human_review"
    # Os dois lados da divergencia ficam registrados, sem reinterpretacao.
    assert "Commercial use allowed" in m["license_conflict_note"]
    assert m["license_source"].strip()


def test_licenca_do_base_nao_se_mistura_com_a_da_variante():
    m = mr.get_model(KEY)
    assert "Illustrious" in m["base_model"]
    assert "Herdada do Illustrious" in m["license_source"]


def test_conteudo_adulto_declarado_para_revisao_humana():
    assert "[HUMAN REVIEW REQUIRED]" in mr.get_model(KEY)["notes"]


# ----------------------------------------------------------------------
# Isolamento: o benchmark nao contamina nada
# ----------------------------------------------------------------------

def test_benchmark_se_declara_nao_oficial():
    src = _nb_source()
    assert '"is_official_pipeline": False' in src
    assert "NAO E PIPELINE OFICIAL" in src


def test_nao_toca_no_baseline_flux():
    """O notebook do FLUX e protegido: este benchmark so LE resultados dele."""
    src = _nb_source()
    assert "flux2_klein_4b_eval.ipynb" not in src.replace(
        "notebooks/flux2_klein_4b_eval.ipynb`", "")  # so a mencao no cabecalho
    for proibido in ("os.remove", "shutil.rmtree"):
        assert proibido not in src, proibido
    # A run_003 do FLUX so pode ser LIDA na montagem comparativa.
    for linha in src.split("\n"):
        if "run_003_output.png" in linha:
            proibido = ("write" in linha or "open(" in linha
                        and "_abrir(" not in linha)
            assert not proibido, f"escrita na run_003 do FLUX: {linha}"


def test_nao_implementa_o_que_esta_fora_de_escopo():
    """Proibido IMPLEMENTAR. Mencionar na lista de nao-escopo e desejavel.

    Por isso o teste olha o WORKFLOW (onde uma implementacao teria de
    aparecer) e, no notebook, so as celulas de codigo.
    """
    classes = set()
    for path in (WF, WF2):
        classes |= {v["class_type"] for v in _nodes(path).values()}
    # IP-Adapter agora E escopo; LoRA, ControlNet e inpaint continuam fora.
    for proibido in ("LoraLoader", "LoraLoaderModelOnly", "ControlNetLoader",
                     "VAEEncodeForInpaint", "InpaintModelConditioning"):
        assert proibido not in classes, proibido

    nb = json.loads(NB.read_text())
    codigo = "\n".join("".join(c["source"]) for c in nb["cells"]
                       if c["cell_type"] == "code").lower()
    for proibido in ("loraloader", "controlnetloader", "lora_name",
                     "vaeencodeforinpaint", "thinplate"):
        assert proibido not in codigo, proibido
    # \btps\b para nao casar dentro de "https".
    assert not re.search(r"\btps\b", codigo), "TPS esta fora de escopo"


@pytest.mark.parametrize("campo", [
    "label", "pipeline_type", "references_supported", "reference_mechanism",
    "reference_mechanism_note", "reference_equivalence_note",
    "reference_roles", "reference_weights_status", "combine_method",
    "requires_custom_node", "custom_node_repo", "custom_node_nodes",
    "ipadapter_models", "workflows", "parameters", "license", "license_name",
    "license_verified", "commercial_status", "status", "vram_gb",
    "download_gb",
])
def test_campos_obrigatorios_presentes(campo):
    assert campo in mr.get_model(KEY)

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
WF0 = WF_DIR / "v0.json"    # img2img puro (runs 001/002)
WF = WF_DIR / "v1.json"     # 1 referencia via IP-Adapter (sem uso)
WF2 = WF_DIR / "v2.json"    # 3 referencias (run 003)
KEY = "wai_illustrious_sdxl_v170"


def _nb_source() -> str:
    nb = json.loads(NB.read_text())
    return "\n".join("".join(c["source"]) for c in nb["cells"])


def _nodes(path: Path = WF) -> dict:
    g = json.loads(path.read_text())
    return {k: v for k, v in g.items() if not k.startswith("_")}


def _celula_de_codigo(prefixo: str) -> str:
    """Codigo de UMA celula, por prefixo do titulo.

    Testar o notebook inteiro como string faz assertion casar em prosa de
    markdown; isto restringe ao codigo da celula certa.
    """
    nb = json.loads(NB.read_text())
    for c in nb["cells"]:
        if c["cell_type"] != "code":
            continue
        src = "".join(c["source"])
        if src.startswith(prefixo):
            return src
    raise AssertionError(f"celula {prefixo!r} nao encontrada")


def _workflow(versao: str) -> dict:
    """Nodes de uma versao do workflow, sem as chaves de metadado `_*`."""
    return _nodes(WF_DIR / f"{versao}.json")


# Nodes que vem no ComfyUI de fabrica. Tudo fora disto e custom node e
# precisa estar declarado no registry.
_CORE = {
    "CheckpointLoaderSimple", "CLIPTextEncode", "LoadImage", "VAEEncode",
    "VAEDecode", "KSampler", "SaveImage", "EmptyLatentImage",
}

# O prompt do FLUX (906 chars) foi escrito para um modelo que entende frase
# longa. Serve so como referencia de tamanho: o do WAI tem de ser menor.
FLUX_PROMPT_LEN_REF = "x" * 906


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
    # `origem` e o arquivo do Drive: nada pode escrever nele.
    for proibido in ("origem.unlink", "origem.rename", "os.remove(origem)",
                     "shutil.move(str(origem)", "open(origem, \"w\")"):
        assert proibido not in src, proibido
    # shutil.move existe, mas so na mesclagem do clone do ComfyUI.
    for linha in src.split("\n"):
        if "shutil.move" in linha:
            assert "item" in linha or "sub" in linha, (
                f"shutil.move fora da mesclagem do clone: {linha.strip()}")
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
    # O gate de execucao olha o SHA e a validacao SDXL, nunca o version id.
    exec_cell = _celula_de_codigo("#@title 9.")
    assert 'VERSAO.get("sha256")' in exec_cell
    assert 'VERSAO.get("sdxl_validated")' in exec_cell
    assert "modelVersionId" not in exec_cell
    assert "version_id" not in exec_cell


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


def test_run_003_usa_full_body_em_papel_duplo():
    """Na Run 003 full_body e latente inicial E referencia do IP-Adapter."""
    wf = _workflow("v2")
    classes = {k: v["class_type"] for k, v in wf.items()}
    fb = next(k for k, v in wf.items()
              if v["class_type"] == "LoadImage"
              and v["inputs"]["image"] == "%%REF_FULL_BODY%%")
    usos = {classes[k] for k, v in wf.items()
            if any(isinstance(x, list) and x[0] == fb
                   for x in v["inputs"].values())}
    assert {"VAEEncode", "IPAdapterEncoder"} <= usos, usos
    assert sum(1 for c in classes.values() if c == "IPAdapterEncoder") == 3
    ks = next(k for k, c in classes.items() if c == "KSampler")
    assert classes[wf[ks]["inputs"]["model"][0]] == "IPAdapterEmbeds"


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



def test_geracao_parte_da_imagem_original_nao_de_latente_vazio():
    """O benchmark e PERSONAGEM -> WAI -> CHIBI, entao e img2img.

    O latente inicial TEM de vir de full_body.png. Se viesse de
    EmptyLatentImage o modelo inventaria uma personagem nova e a
    referencia estaria sendo descartada.
    """
    for ver in ("v0", "v2"):
        wf = _workflow(ver)
        classes = {k: v["class_type"] for k, v in wf.items()}
        assert "EmptyLatentImage" not in classes.values(), ver
        enc = [k for k, c in classes.items() if c == "VAEEncode"]
        assert len(enc) == 1, ver
        ks = next(k for k, c in classes.items() if c == "KSampler")
        assert wf[ks]["inputs"]["latent_image"] == [enc[0], 0], ver
        fonte = wf[enc[0]]["inputs"]["pixels"][0]
        assert classes[fonte] == "LoadImage"
        assert wf[fonte]["inputs"]["image"] == "%%REF_FULL_BODY%%", ver


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


# ----------------------------------------------------------------------
# BASELINE WAI PURO (v0) — diagnostico do checkpoint
# ----------------------------------------------------------------------


def test_run_001_e_img2img_so_com_nodes_core():
    """v0 = img2img puro, sem nenhum custom node."""
    wf = _workflow("v0")
    classes = sorted({v["class_type"] for v in wf.values()})
    assert classes == sorted([
        "CheckpointLoaderSimple", "CLIPTextEncode", "LoadImage",
        "VAEEncode", "KSampler", "VAEDecode", "SaveImage",
    ]), classes



def test_run_001_nao_tem_ipadapter_lora_controlnet_nem_hires():
    """Run 001 isola a imagem original: nada de condicionamento extra."""
    wf = _workflow("v0")
    classes = " ".join(v["class_type"] for v in wf.values()).lower()
    for proibido in ("ipadapter", "lora", "controlnet", "upscale", "adetailer"):
        assert proibido not in classes, proibido
    ks = next(v for v in wf.values() if v["class_type"] == "KSampler")
    assert ks["inputs"]["denoise"] == "%%DENOISE%%"


def test_baseline_usa_o_vae_integrado_do_checkpoint():
    """'VAE integrado' = saida 2 do CheckpointLoaderSimple, sem VAELoader."""
    n = _nodes(WF0)
    dec = next(v for v in n.values() if v["class_type"] == "VAEDecode")
    assert dec["inputs"]["vae"] == ["1", 2]
    assert not any(v["class_type"] == "VAELoader" for v in n.values())



def test_full_body_e_consumida_em_todas_as_runs():
    """Nenhuma referencia declarada pode ser descartada em silencio.

    Em img2img a imagem original NAO e opcional: ela e o ponto de
    partida. Isto trava a regressao para o baseline txt2img antigo,
    onde full_body era declarada mas nao consumida.
    """
    for ver, esperadas in (("v0", {"%%REF_FULL_BODY%%"}),
                           ("v2", {"%%REF_FULL_BODY%%", "%%REF_FACE%%",
                                   "%%REF_OUTFIT%%"})):
        wf = _workflow(ver)
        carregadas = {v["inputs"]["image"] for v in wf.values()
                      if v["class_type"] == "LoadImage"}
        assert carregadas == esperadas, (ver, carregadas)


def test_runs_001_002_pulam_a_instalacao_do_ipadapter():
    src = _nb_source()
    assert "Run\", RUN_ID, \"= baseline puro: IP-Adapter NAO e usado." in src
    assert "IPADAPTER_META = None" in src



def test_parametros_seguem_a_recomendacao_do_autor():
    """steps/CFG/sampler vem do autor do v17.0; denoise e resolucao nao."""
    par = mr.get_model(KEY)["parameters"]
    assert 15 <= par["steps"] <= 30
    assert 5.0 <= par["cfg"] <= 7.0
    assert par["sampler"] == "euler_ancestral"
    assert par["hires_fix"] is False
    fonte = par["parameters_source"].lower()
    assert "denoise" in fonte and "img2img" in fonte


def test_prompt_e_negative_seguem_o_estilo_curto_do_autor():
    m = mr.get_model(KEY)
    prompt = " ".join(m["prompt_override"].split())
    assert len(prompt) < len(FLUX_PROMPT_LEN_REF), "prompt do FLUX nao serve"
    neg = m["negative_prompt_override"]
    assert len(neg.split(",")) <= 10, neg
    assert neg.startswith("bad quality, worst quality, worst detail, sketch")



def test_diferenca_de_prompt_em_relacao_ao_flux_esta_registrada():
    m = mr.get_model(KEY)
    assert "FLUX" in m["prompt_override_reason"]
    assert "1:1" in m["prompt_override_reason"]


def test_notebook_orienta_o_diagnostico_das_tres_causas():
    src = _nb_source()
    assert "IP-Adapter esta INOCENTE" in src
    assert "causa (A)" in src and "causa (B)" in src and "causa (C)" in src
    assert "UM fator por vez" in src



def test_erro_registra_a_etapa_exata():
    """Falhar sem dizer ONDE obriga a re-executar tudo para descobrir."""
    exec_cell = _celula_de_codigo("#@title 9.")
    for etapa in ("submissao_do_grafo", "execucao_do_grafo",
                  "timeout_execucao"):
        assert etapa in exec_cell, etapa
    # o detalhe do erro tem de sobreviver ao fim da sessao
    assert "erro_wai.txt" in exec_cell
    assert exec_cell.count("BLOCKED na etapa") >= 3


def test_zip_com_nome_exato_e_download():
    src = _nb_source()
    assert "wai_illustrious_eval_results.zip" in src
    assert "from google.colab import files" in src
    assert "files.download(str(ZIP_PATH))" in src
    # Caminho impresso mesmo se o download automatico falhar.
    assert "Baixe pelo painel de arquivos a esquerda:" in src


def test_zip_inclui_tudo_que_foi_pedido():
    src = _nb_source()
    for item in ("output.png", "recipe.json", "workflow.resolved.json",
                 "logs", "comparison.png", "RELATORIO.md", "hashes.json"):
        assert item in src, item


def test_workflow_resolvido_e_gravado_com_os_valores_reais():
    """O grafo COM substituicoes e o que de fato rodou."""
    src = _nb_source()
    assert '(RUN_DIR / "workflow.resolved.json").write_text(' in src
    assert "json.dumps(GRAFO, indent=2)" in src


def test_cada_run_tem_diretorio_proprio_sem_mistura():
    src = _nb_source()
    assert 'f"/content/ChibiCreate/experiments/model_eval/{MODEL_KEY}/run_{RUN_ID}"' in src
    assert "[no overwrite]" in src


def test_notebook_registra_referencias_declaradas_e_consumidas():
    """Declarada != consumida: no baseline a diferenca e o ponto principal."""
    src = _nb_source()
    assert '"references_declared": REFS_DECLARADAS' in src
    assert '"references_consumed": REFS_CONSUMIDAS' in src
    assert '"reference_count": len(REFS_CONSUMIDAS)' in src


# ----------------------------------------------------------------------
# Nodes: so Core
# ----------------------------------------------------------------------


def test_v2_usa_apenas_core_mais_ipadapter():
    wf = _workflow("v2")
    extras = {v["class_type"] for v in wf.values()
              if v["class_type"] not in _CORE}
    assert extras and all(c.startswith("IPAdapter") or c == "CLIPVisionLoader"
                          for c in extras), extras


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



def test_resolucao_e_herdada_da_imagem_de_partida_sem_deformar():
    """Nao ha resize: redimensionar deformaria a arte original.

    full_body.png e quadrado (1024x1024). Forcar 1024x1344 mudaria o
    aspect de 1.0 para 0.76, esticando a personagem.
    """
    par = mr.get_model(KEY)["parameters"]
    assert par["resolution"] == "from_source_image"
    assert "deform" in par["resolution_note"].lower()
    for ver in ("v0", "v2"):
        classes = " ".join(v["class_type"] for v in _workflow(ver).values())
        assert "Scale" not in classes and "Resize" not in classes, ver



def test_denoise_e_menor_que_um_e_marcado_como_experimental():
    """denoise 1.0 destruiria o latente inicial e viraria txt2img."""
    par = mr.get_model(KEY)["parameters"]
    assert 0.0 < par["denoise"] < 1.0, par["denoise"]
    assert par["denoise_status"] == "BASELINE_EXPERIMENTAL"
    nota = par["denoise_note"].lower()
    assert "nao otimizado" in nota.replace("\u00e3", "a") or "nao" in nota
    assert "txt2img" in nota



def test_prompt_manda_adaptar_e_nao_redesenhar():
    """O prompt nao pode pedir uma personagem nova.

    Em img2img um prompt que descreve uma personagem do zero compete
    com a imagem de partida. Este manda ADAPTAR o design original.
    """
    m = mr.get_model(KEY)
    prompt = " ".join(m["prompt_override"].split()).lower()
    assert "input character" in prompt
    assert "preserve the same character identity" in prompt
    assert "adapt the original design" in prompt
    assert "rather than redesigning" in prompt
    assert m["prompt_mode"] == "img2img_adapt_not_redesign"


def test_negativo_e_do_autor_do_checkpoint_e_esta_justificado():
    m = mr.get_model(KEY)
    assert m["negative_prompt_override"]
    assert m["negative_prompt_reason"].strip()


def test_prompt_vem_do_registry_nao_do_notebook():
    """O prompt e versionado no registry, nao digitado no notebook."""
    assert 'PROMPT = " ".join(CFG["prompt_override"].split())' in _nb_source()
    assert 'NEGATIVE = CFG["negative_prompt_override"]' in _nb_source()


def test_divergencia_de_prompt_com_o_flux_esta_declarada():
    """WAI deixou de usar o base_prompt do FLUX — isso tem de estar escrito."""
    razao = mr.get_model(KEY)["prompt_override_reason"]
    assert "base_prompt" in razao
    assert "FLUX" in razao
    assert "CONSEQUENCIA REGISTRADA" in razao


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
    assert w["run_001"].endswith("@v0"), "001/002 usam o BASELINE puro"
    assert w["run_003"].endswith("@v2")

    src = _nb_source()
    assert 'WORKFLOW_VERSION = "v2" if IS_RUN_003 else "v0"' in src


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
    assert "(COMFY_INPUT / nome).write_bytes(origem_ref.read_bytes())" in src


def test_nao_ha_ranking_automatico():
    src = _nb_source()
    assert "[HUMAN REVIEW REQUIRED]" in src
    assert "sem ranking automatico" in src.lower()
    assert "DESIGN_PRESERVATION" in src


def test_avalia_limpeza_tecnica_antes_do_julgamento_artistico():
    src = _nb_source()
    assert "PRIMEIRO: a imagem esta tecnicamente limpa?" in src
    assert "sem artefato cromatico" in src


def test_montagem_comparativa_tem_os_cinco_paineis():
    src = _nb_source()
    for rotulo in ("ORIGINAL", "FLUX RUN 003", "WAI RUN 001",
                   "WAI RUN 002", "WAI RUN 003"):
        assert rotulo in src, rotulo


def test_nao_reexecuta_o_flux_dentro_deste_notebook():
    """A run_003 do FLUX entra como imagem JA EXISTENTE, so leitura.

    Testa o codigo, nao a prosa: mencionar o FLUX no texto e desejavel;
    carregar o modelo ou submeter um grafo dele e que seria violacao.
    """
    nb = json.loads(NB.read_text())
    codigo = "\n".join("".join(c["source"]) for c in nb["cells"]
                        if c["cell_type"] == "code")
    # Nenhum peso/loader do FLUX e carregado aqui.
    for proibido in ("FluxGuidance", "UNETLoader", "DualCLIPLoader",
                     "flux1-", "t5xxl", "ae.safetensors"):
        assert proibido not in codigo, proibido

    # O nome do FLUX so pode aparecer em string (rotulo, relatorio,
    # nome do benchmark) ou lendo o PNG pronto — nunca como chamada.
    for linha in codigo.split("\n"):
        low = linha.lower()
        if "flux" not in low:
            continue
        e_string = ('"' in linha or "'" in linha)
        assert e_string, f"uso do FLUX fora de string: {linha.strip()}"
        assert "urlopen" not in low and "subprocess" not in low, (
            f"execucao envolvendo FLUX: {linha.strip()}")


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
    for proibido in ("os.remove",):
        assert proibido not in src, proibido
    # rmtree so em diretorios de trabalho nossos (clone temporario do
    # ComfyUI e staging do ZIP), nunca no Drive nem no repositorio.
    for linha in src.split("\n"):
        if "shutil.rmtree" in linha:
            assert any(t in linha for t in ("tmp", "STAGE")), (
                f"rmtree fora de diretorio de trabalho: {linha.strip()}")
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


# ----------------------------------------------------------------------
# Regressao: celula 4 (Drive) cria /content/ComfyUI antes da celula 5
# ----------------------------------------------------------------------

def test_instalacao_do_comfy_nao_confia_so_na_pasta_existir():
    """Bug real: `git rev-parse HEAD` saiu com 128.

    A celula 4 cria /content/ComfyUI/models/checkpoints para colocar o
    symlink do Drive. A celula 5 via a pasta existindo, pulava o clone e
    rodava git num diretorio que nao era repositorio.
    """
    src = _nb_source()
    # O marcador de "instalado" e o .git + main.py, nao a pasta.
    assert ('instalado = (COMFY / ".git").is_dir() and '
            '(COMFY / "main.py").is_file()') in src
    assert 'if not pathlib.Path("/content/ComfyUI").exists():' not in src


def test_clone_lida_com_diretorio_nao_vazio():
    """git clone recusa diretorio nao vazio: clonar ao lado e mesclar."""
    src = _nb_source()
    assert "if COMFY.exists() and any(COMFY.iterdir()):" in src
    assert "_comfy_tmp" in src
    # O que a celula 4 ja colocou nao pode ser sobrescrito.
    assert "if not destino.exists():" in src
    assert "elif not alvo.exists():" in src


def test_erro_claro_se_a_pasta_nao_for_um_clone():
    src = _nb_source()
    assert 'if not (COMFY / ".git").is_dir():' in src
    assert "BLOCKED — {COMFY} nao e um clone do ComfyUI" in src


def test_subir_comfy_reaproveita_servidor_ja_no_ar():
    src = _nb_source()
    assert "ja estava no ar; reaproveitando." in src


def test_reinicio_tolera_proc_none():
    """PROC e None quando o servidor ja estava no ar."""
    src = _nb_source()
    assert "if PROC is not None:" in src
    assert 'subprocess.run(["pkill", "-f", "ComfyUI/main.py"], check=False)' in src


def test_celula_5_confere_o_checkpoint_do_drive():
    """A mesclagem nao pode ter comido o symlink."""
    src = _nb_source()
    assert "AUSENTE — reexecute a celula 4" in src

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
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import model_registry as mr  # noqa: E402
from chibi import experiment  # noqa: E402

NB = ROOT / "notebooks" / "wai_illustrious_sdxl_eval.ipynb"
WF = ROOT / "workflows" / "experimental" / "wai_illustrious_chibi" / "v1.json"
KEY = "wai_illustrious_sdxl_v170"


def _nb_source() -> str:
    nb = json.loads(NB.read_text())
    return "\n".join("".join(c["source"]) for c in nb["cells"])


def _wf() -> dict:
    return json.loads(WF.read_text())


def _nodes() -> dict:
    return {k: v for k, v in _wf().items() if not k.startswith("_")}


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


def test_notebook_exige_a_versao_antes_de_baixar():
    """Sem modelVersionId o download tem de parar, nao improvisar."""
    src = _nb_source()
    assert "CIVITAI_VERSION_ID" in src
    assert "CKPT_SHA256_ESPERADO" in src
    assert "PARE: fixe a versao na celula 4 antes de baixar." in src
    assert "PARE: SHA256 diverge do declarado na celula 4." in src


# ----------------------------------------------------------------------
# A limitacao central: SDXL nao tem multi-referencia
# ----------------------------------------------------------------------

def test_registry_declara_zero_referencias():
    m = mr.get_model(KEY)
    assert m["references_supported"] == 0
    assert m["pipeline_type"] == "sdxl_checkpoint_img2img"
    assert "IP-Adapter" in m["reference_limitation"]


def test_workflow_tem_exatamente_um_loadimage():
    """Se alguem adicionar um segundo LoadImage, a limitacao mudou de fato
    e o registry/documentacao precisam mudar junto."""
    loads = [k for k, v in _nodes().items() if v["class_type"] == "LoadImage"]
    assert len(loads) == 1, f"esperado 1 LoadImage, achei {len(loads)}"


def test_workflow_nao_finge_mecanismo_de_referencia():
    """SDXL nao tem ReferenceLatent (FLUX) nem TextEncodeQwenImageEdit."""
    classes = {v["class_type"] for v in _nodes().values()}
    for proibido in ("ReferenceLatent", "TextEncodeQwenImageEditPlus",
                     "TextEncodeQwenImageEdit", "IPAdapter",
                     "IPAdapterApply", "ControlNetApply",
                     "ControlNetApplyAdvanced"):
        assert proibido not in classes, f"{proibido} nao pertence a este benchmark"


def test_run_003_nunca_e_chamada_de_equivalente_a_tres_referencias():
    """A proibicao textual mais importante da diretiva."""
    src = _nb_source().lower()

    # O termo pode aparecer, mas SOMENTE sendo repudiado. Toda ocorrencia
    # tem de estar na frase que diz que usa-lo seria mentira.
    for termo in ("3-reference equivalent", "equivalente a 3 referencias"):
        i = 0
        while (i := src.find(termo, i)) != -1:
            ctx = src[max(0, i - 120):i + 120]
            assert ("seria mentira" in ctx or "nao chamar" in ctx), (
                f"{termo!r} usado como afirmacao: ...{ctx}...")
            i += len(termo)

    # E precisa afirmar o contrario, explicitamente.
    assert "**nao e** equivalente a run 003 do flux" in " ".join(src.split())
    assert "1 referencia (full_body), nao 3" in src


def test_notebook_registra_quais_referencias_entraram_e_quais_nao():
    src = _nb_source()
    assert '"references_used": ["full_body"]' in src
    assert '"references_not_used"' in src
    assert '"multi_reference_supported": False' in src


# ----------------------------------------------------------------------
# Nodes: so Core
# ----------------------------------------------------------------------

def test_somente_nodes_core():
    permitidos = {
        "CheckpointLoaderSimple", "CLIPTextEncode", "LoadImage",
        "VAEEncode", "KSampler", "VAEDecode", "SaveImage",
    }
    classes = {v["class_type"] for v in _nodes().values()}
    assert classes <= permitidos, classes - permitidos


def test_notebook_declara_zero_custom_nodes():
    assert '"custom_nodes": []' in _nb_source()


# ----------------------------------------------------------------------
# Parametros e prompt
# ----------------------------------------------------------------------

def test_seed_42_e_batch_1():
    p = mr.get_model(KEY)["parameters"]
    assert p["seed"] == 42
    assert p["batch"] == 1


def test_resolucao_explicita_e_compativel_com_sdxl():
    assert mr.get_model(KEY)["parameters"]["resolution"] == [1024, 1024]


def test_denoise_e_hipotese_declarada_nao_valor_otimizado():
    p = mr.get_model(KEY)["parameters"]
    assert p["denoise_status"] == "BASELINE_HYPOTHESIS"
    assert p["denoise_note"].strip()


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
    assert 'PROMPT = _reg["base_prompt"]' in _nb_source()


def test_sem_sweep_de_prompt_ou_seed():
    src = _nb_source().lower()
    for termo in ("for seed in", "seed_sweep", "prompt_sweep", "for prompt in"):
        assert termo not in src, termo


# ----------------------------------------------------------------------
# Personagem parametrizada
# ----------------------------------------------------------------------

def test_character_id_e_parametro_com_default_waifu_001():
    assert 'CHARACTER_ID = "waifu_001"  #@param' in _nb_source()


def test_nenhum_caminho_de_personagem_hardcoded():
    """Trocar de personagem tem de ser so trocar CHARACTER_ID."""
    src = _nb_source()
    for linha in src.split("\n"):
        if "characters/" in linha and "CHARACTER_ID" not in linha:
            assert "run_003_output" in linha or linha.strip().startswith("#"), (
                f"caminho de personagem hardcoded: {linha.strip()}")


def test_workflow_nao_tem_personagem_embutida():
    assert "waifu" not in WF.read_text().lower()


# ----------------------------------------------------------------------
# Hashes, reprodutibilidade, nao-mutacao
# ----------------------------------------------------------------------

def test_hashes_de_artefato_e_de_pixel_sao_registrados_separados():
    src = _nb_source()
    assert "artifact_sha256" in src
    assert "output_pixel_sha256" in src
    assert "pixel_sha256" in src


def test_run_002_repete_a_001_com_a_mesma_seed():
    """Mesma seed, mesmo prompt, mesmos parametros — repeticao real."""
    src = _nb_source()
    i1 = src.index("#@title 8. RUN 001")
    i2 = src.index("#@title 9. RUN 002")
    i3 = src.index("#@title 10. RUN 003")
    r1, r2 = src[i1:i2], src[i2:i3]
    for bloco in (r1, r2):
        assert "--seed $SEED" in bloco
        assert '--prompt "$PROMPT"' in bloco
    # A 002 nao pode introduzir override que a 001 nao tinha.
    assert "--denoise" not in r2


def test_nao_promete_determinismo():
    src = _nb_source().lower()
    assert "nao prometemos" in src or "sem determinismo" in src


def test_entradas_sao_lidas_nao_modificadas():
    src = _nb_source()
    assert "NAO sao modificados" in src
    assert ".write_bytes(" not in src.split("#@title 3.")[1].split("#@title 4.")[0]


def test_nao_ha_ranking_automatico():
    src = _nb_source()
    assert "[HUMAN REVIEW REQUIRED]" in src
    assert "nao ha ranking automatico" in src.lower()
    assert "DESIGN_PRESERVATION" in src


def test_montagem_comparativa_tem_os_cinco_paineis():
    src = _nb_source()
    for rotulo in ("ORIGINAL", "FLUX RUN 001", "FLUX RUN 003", "WAI RUN"):
        assert rotulo in src, rotulo


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
    for proibido in ("run_003_output.png\", \"w", "shutil.copy", "os.remove",
                     "unlink()", "shutil.rmtree"):
        assert proibido not in src, proibido


def test_nao_implementa_o_que_esta_fora_de_escopo():
    """Proibido IMPLEMENTAR. Mencionar na lista de nao-escopo e desejavel.

    Por isso o teste olha o WORKFLOW (onde uma implementacao teria de
    aparecer) e, no notebook, so as celulas de codigo.
    """
    classes = {v["class_type"] for v in _nodes().values()}
    for proibido in ("LoraLoader", "ControlNetLoader", "IPAdapterModelLoader",
                     "VAEEncodeForInpaint", "InpaintModelConditioning"):
        assert proibido not in classes, proibido

    nb = json.loads(NB.read_text())
    codigo = "\n".join("".join(c["source"]) for c in nb["cells"]
                       if c["cell_type"] == "code").lower()
    for proibido in ("loraloader", "controlnetloader", "ipadapter",
                     "lora_name", "vaeencodeforinpaint"):
        assert proibido not in codigo, proibido


@pytest.mark.parametrize("campo", [
    "label", "pipeline_type", "references_supported", "reference_limitation",
    "parameters", "license", "license_name", "license_verified",
    "commercial_status", "status", "vram_gb", "download_gb",
])
def test_campos_obrigatorios_presentes(campo):
    assert campo in mr.get_model(KEY)

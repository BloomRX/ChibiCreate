"""Testes do notebook de pose transfer (ADR-007, EXPERIMENTAL).

O notebook implementa a estrategia (A) do ADR-002, que foi descartada para
producao. Estes testes garantem que ele continue se apresentando como
experimento e que as guardas de insumo nao sejam afrouxadas.
"""

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
NOTEBOOK = RAIZ / "notebooks" / "pose_transfer_eval.ipynb"
WORKFLOW = RAIZ / "workflows" / "experimental" / "pose_transfer" / "v1.json"
ADR = RAIZ / "docs" / "decisions" / "ADR-007-pose-transfer-experimento.md"
MANNEQUIN_DIR = RAIZ / "styles" / "chibi" / "pose_bank" / "mannequin"


def _nb() -> dict:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def _celula(prefixo: str) -> str:
    for celula in _nb()["cells"]:
        if celula["cell_type"] != "code":
            continue
        fonte = "".join(celula["source"])
        if fonte.startswith(prefixo):
            return fonte
    raise AssertionError(f"celula {prefixo!r} nao encontrada")


def _codigo(prefixo: str) -> str:
    return "\n".join(
        l for l in _celula(prefixo).split("\n") if not l.strip().startswith("#@")
    )


def _todo_codigo() -> str:
    return "\n".join(
        "".join(c["source"]) for c in _nb()["cells"] if c["cell_type"] == "code"
    )


# --- integridade ----------------------------------------------------------


def test_notebook_e_valido():
    nbformat = pytest.importorskip("nbformat")
    nbformat.validate(nbformat.reads(NOTEBOOK.read_text(encoding="utf-8"), as_version=4))


def test_todas_as_celulas_de_codigo_sao_colapsaveis():
    for celula in _nb()["cells"]:
        if celula["cell_type"] != "code":
            continue
        primeira = "".join(celula["source"]).split("\n")[0]
        assert primeira.startswith("#@title"), primeira
        assert 'display-mode: "form"' in primeira, primeira


def test_nenhum_global_maiusculo_com_dois_significados():
    """Licao do bug do REPO: nome reusado entre celulas apaga o valor certo.

    POSE_FRAMES e excecao declarada — e relido do mesmo diretorio, com o
    mesmo significado, para tornar as celulas re-executaveis isoladamente.
    """
    permitidos = {"POSE_FRAMES"}
    defs: dict[str, set[str]] = collections.defaultdict(set)
    for celula in _nb()["cells"]:
        if celula["cell_type"] != "code":
            continue
        fonte = "".join(celula["source"])
        titulo = fonte.split("\n")[0]
        for linha in fonte.split("\n"):
            if linha.strip().startswith("#"):
                continue
            m = re.match(r"^([A-Z][A-Z0-9_]{1,})\s*=\s*", linha)
            if m:
                defs[m.group(1)].add(titulo)
    repetidos = {k: v for k, v in defs.items() if len(v) > 1 and k not in permitidos}
    assert not repetidos, repetidos


# --- notebooks protegidos -------------------------------------------------


@pytest.mark.parametrize(
    "nome",
    ["flux2_klein_4b_eval.ipynb", "wai_illustrious_sdxl_eval.ipynb",
     "chibi_from_concept.ipynb"],
)
def test_notebooks_anteriores_nao_sao_tocados(nome):
    assert (RAIZ / "notebooks" / nome).is_file()


# --- honestidade sobre o ADR-002 -----------------------------------------


def test_notebook_declara_que_e_experimental_e_nao_promove_a_rota():
    texto = NOTEBOOK.read_text(encoding="utf-8")
    assert "EXPERIMENTAL" in texto
    assert "ADR-002" in texto
    assert "ADR-007" in texto
    assert "flicker" in texto.lower() or "cintila" in texto.lower()


def test_adr_007_nao_reverte_o_adr_002():
    texto = ADR.read_text(encoding="utf-8")
    assert "nao substitui o ADR-002" in texto.lower().replace("ã", "a").replace(
        "ó", "o"
    ) or "Não substitui o ADR-002" in texto
    assert "rig cutout" in texto.lower()


def test_avaliacao_e_por_loop_e_em_escala_de_jogo():
    """O flicker e invisivel frame a frame: exigir GIF e escalas pequenas."""
    codigo = _codigo("#@title 8.")
    assert "loop" in codigo.lower()
    assert "gif" in codigo.lower()
    assert "64" in _celula("#@title 0.")


def test_delta_e_declarado_diagnostico_e_nao_qualidade():
    codigo = _celula("#@title 8.")
    assert "DIAGNOSTICO" in codigo
    baixo = codigo.lower()
    assert "nao qualidade" in baixo or "nao avaliacao" in baixo


def test_agente_nao_julga_o_resultado():
    codigo = _todo_codigo()
    assert "[HUMAN REVIEW REQUIRED]" in codigo
    assert "approval_status" in codigo
    assert '"experimental"' in codigo


# --- guardas de insumo ----------------------------------------------------


def test_sheet_com_grade_errada_e_bloqueado():
    codigo = _codigo("#@title 2.")
    assert "nao divide exatamente" in codigo
    assert "BLOCKED" in codigo


def test_valida_pivot_canvas_e_alfa():
    codigo = _codigo("#@title 3.")
    assert "pivot" in codigo.lower()
    assert "canvas inconsistente" in codigo
    assert "transparente" in codigo


def test_nao_corrige_proporcao_automaticamente():
    """Compensar proporcao em codigo esconderia a causa real da falha."""
    codigo = _celula("#@title 3.")
    assert "NAO corrige proporcao" in codigo
    assert "[HUMAN REVIEW REQUIRED]" in codigo


def test_celula_de_execucao_confere_o_repo():
    codigo = _codigo("#@title 7.")
    assert "nao aponta para o clone do ChibiCreate" in codigo


def test_placeholders_nao_resolvidos_sao_bloqueados():
    codigo = _codigo("#@title 7.")
    assert "%%" in codigo and "nao resolvido" in codigo


# --- prompt ---------------------------------------------------------------


def test_prompt_generico_nao_cita_tracos_da_personagem():
    import sys

    sys.path.insert(0, str(RAIZ / "scripts"))
    from chibi.model_registry import termos_especificos_no_prompt

    fonte = _celula("#@title 0.")
    m = re.search(r'PROMPT_GENERICO = \(\n(.*?)\n\)', fonte, re.S)
    assert m, "PROMPT_GENERICO nao encontrado"
    prompt = " ".join(re.findall(r'"([^"]*)"', m.group(1)))
    assert prompt.strip()
    assert termos_especificos_no_prompt(prompt) == []


def test_prompt_especifico_marcado_como_generico_e_bloqueado():
    codigo = _codigo("#@title 6.")
    assert "termos_especificos_no_prompt" in codigo
    assert "BLOCKED" in codigo
    assert "character_specific_prompt" in _todo_codigo()


def test_personagem_nao_e_hardcodada_no_codigo():
    """CHARACTER_ID e #@param; nenhuma outra celula pode fixar a personagem."""
    for celula in _nb()["cells"]:
        if celula["cell_type"] != "code":
            continue
        fonte = "".join(celula["source"])
        if fonte.startswith("#@title 0."):
            continue
        assert "waifu_001" not in fonte, fonte.split("\n")[0]


# --- workflow -------------------------------------------------------------


def test_workflow_existe_e_documenta_a_ordem_dos_slots():
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    assert wf["_slots"]["INPUT_IMAGE"] == "pose_frame"
    assert wf["_slots"]["INPUT_IMAGE_2"] == "chibi_master"
    nodes = {k: v for k, v in wf.items() if not k.startswith("_")}
    assert sum(1 for v in nodes.values()
               if v["class_type"] == "ReferenceLatent") >= 2
    assert sum(1 for v in nodes.values() if v["class_type"] == "LoadImage") >= 2


def test_workflow_nao_usa_empty_latent_como_unica_fonte():
    """A identidade tem de entrar por referencia, nao ser inventada do zero."""
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    nodes = {k: v for k, v in wf.items() if not k.startswith("_")}
    assert any(v["class_type"] == "ReferenceLatent" for v in nodes.values())


# --- licenca --------------------------------------------------------------


def test_licenca_do_mixamo_registrada_com_as_duas_proibicoes():
    meta = json.loads((MANNEQUIN_DIR / "mannequin.metadata.json").read_text("utf-8"))
    lic = meta["_licenca_global"]
    assert lic["uso_comercial"] is True
    assert "PROIBID" in lic["redistribuicao_de_arquivos_brutos"].upper()
    assert "PROIBIDO" in lic["uso_para_treino_de_ml"].upper()


def test_recipe_registra_licenca_do_mannequin():
    codigo = _codigo("#@title 9.")
    assert "mannequin_license" in codigo
    assert "workflow_sha256" in codigo
    assert "chibi_pixel_sha256" in codigo


def test_readme_do_mannequin_alerta_sobre_proporcao():
    texto = (MANNEQUIN_DIR / "README.md").read_text(encoding="utf-8")
    assert "cabeças" in texto or "cabecas" in texto
    assert "Mixamo" in texto
    assert "pivot" in texto.lower()


def test_nenhum_binario_de_rig_versionado():
    """Mixamo proibe redistribuir arquivos brutos: so PNG pode entrar."""
    proibidos = {".fbx", ".blend", ".dae", ".bvh"}
    achados = [
        p for p in MANNEQUIN_DIR.rglob("*") if p.suffix.lower() in proibidos
    ]
    assert not achados, achados


# --- modos de pose (dropdown) --------------------------------------------

MODOS = ["render_direto", "dwpose_skeleton", "depth_map", "depth_map_lora"]


def test_dropdown_lista_exatamente_os_modos_suportados():
    fonte = _celula("#@title 0.")
    m = re.search(r'POSE_INPUT_MODE = "\w+"\s+#@param (\[[^\]]*\])', fonte)
    assert m, "POSE_INPUT_MODE nao e um dropdown"
    assert json.loads(m.group(1)) == MODOS


def test_nao_oferece_controlnet_real_que_nao_existe_para_klein_4b():
    """Nao ha ControlNet dedicado para FLUX.2 klein 4B (pesquisa 2026-09-19).

    Oferecer a opcao criaria um dropdown com valor inexistente.
    """
    fonte = _celula("#@title 0.")
    m = re.search(r'POSE_INPUT_MODE = "\w+"\s+#@param (\[[^\]]*\])', fonte)
    for modo in json.loads(m.group(1)):
        assert "controlnet" not in modo.lower()
    assert "ControlNetLoader" not in _todo_codigo()


def test_preprocessador_e_validado_contra_object_info():
    """Nao criar dropdown com opcao inexistente; nao degradar em silencio."""
    codigo = _codigo("#@title 3b.")
    assert "/object_info" in codigo
    assert "nao existe neste servidor" in codigo
    assert "BLOCKED" in codigo


def test_custom_node_e_pinado_por_commit():
    codigo = _codigo("#@title 1.")
    assert "AUX_COMMIT" in codigo
    assert "59b1fc411ede8623b2997855b8018f0b3b6cf49f" in codigo
    assert "esperado" in codigo  # verifica o HEAD apos o checkout


def test_lora_so_no_modo_que_a_usa():
    painel = _celula("#@title 0.")
    assert 'USA_LORA = POSE_INPUT_MODE == "depth_map_lora"' in painel
    v1 = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    assert not any(
        isinstance(v, dict) and str(v.get("class_type", "")).startswith("Lora")
        for v in v1.values()
    ), "v1 nao pode ter LoRA"


def test_v2_encadeia_a_lora_no_caminho_do_model():
    """Validar a CADEIA, nao o vizinho direto."""
    caminho = WORKFLOW.parent / "v2.json"
    wf = json.loads(caminho.read_text(encoding="utf-8"))
    nodes = {k: v for k, v in wf.items() if not k.startswith("_")}
    ks = next(k for k, v in nodes.items() if v["class_type"] == "KSampler")
    cadeia, cur = [], nodes[ks]["inputs"]["model"]
    while isinstance(cur, list):
        cadeia.append(nodes[cur[0]]["class_type"])
        cur = nodes[cur[0]]["inputs"].get("model")
    assert "LoraLoaderModelOnly" in cadeia
    assert "UNETLoader" in cadeia


def test_lora_tem_sha256_pinado_e_licenca_registrada():
    yaml = pytest.importorskip("yaml")
    lock = yaml.safe_load((RAIZ / "config" / "models.lock.yaml").read_text("utf-8"))
    ent = lock["models"]["refcontrol_klein_4b_depth_lora"]
    assert ent["license"]["spdx"] == "Apache-2.0"
    assert ent["license"]["commercial_use"] == "allowed"
    arq = ent["files"]["flux2_klein_4b_refcontrol_depth.safetensors"]
    assert len(arq["sha256"]) == 64
    assert ent["revision"] == "0ae1ef7f9acc4e55ec2237360943c3c3032d3583"


def test_base_mismatch_da_lora_esta_documentado():
    """A LoRA declara base NAO destilada; o pipeline usa a destilada.

    Isso degrada em silencio. Tem de estar visivel no lock e no notebook.
    """
    yaml = pytest.importorskip("yaml")
    lock = yaml.safe_load((RAIZ / "config" / "models.lock.yaml").read_text("utf-8"))
    ent = lock["models"]["refcontrol_klein_4b_depth_lora"]
    assert ent["base_mismatch"] is True
    assert "base_mismatch" in _todo_codigo()
    assert "[TEST REQUIRED]" in _celula("#@title 6.")


def test_variante_9b_nao_comercial_e_recusada():
    yaml = pytest.importorskip("yaml")
    lock = yaml.safe_load((RAIZ / "config" / "models.lock.yaml").read_text("utf-8"))
    ent = lock["models"]["refcontrol_klein_4b_depth_lora"]
    assert "NAO USAR" in ent["variantes_9b_disponiveis"]
    assert "9B" not in _todo_codigo() or "nao-comercial" in _todo_codigo().lower()


def test_sha256_da_lora_e_conferido_antes_de_usar():
    codigo = _codigo("#@title 6.")
    assert "sha256" in codigo.lower()
    assert "nao confere" in codigo


def test_custom_node_registrado_no_lock():
    yaml = pytest.importorskip("yaml")
    lock = yaml.safe_load((RAIZ / "config" / "models.lock.yaml").read_text("utf-8"))
    ent = lock["models"]["comfyui_controlnet_aux"]
    assert ent["license"]["spdx"] == "Apache-2.0"
    assert ent["revision"] == "59b1fc411ede8623b2997855b8018f0b3b6cf49f"


def test_saidas_nao_se_sobrescrevem_entre_modos():
    """Comparar os 4 modos exige que cada um grave num arquivo proprio."""
    assert "POSE_INPUT_MODE" in _codigo("#@title 9.")  # nome do zip
    codigo8 = _codigo("#@title 8.")
    assert "POSE_INPUT_MODE" in codigo8  # sheet e gif


def test_recipe_registra_o_modo_e_o_preprocessador():
    codigo = _codigo("#@title 9.")
    assert "pose_input_mode" in codigo
    assert "preprocessor" in codigo

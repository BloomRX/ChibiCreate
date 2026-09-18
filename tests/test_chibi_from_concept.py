"""Testes do notebook CHIBI FROM CONCEPT.

Fluxo: upload da concept art -> FLOW 01 -> FLUX.2 klein -> 2 ZIPs.
A personagem nasce no notebook; nada precisa ir para o Git.
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "chibi_from_concept.ipynb"
BASELINE = ROOT / "notebooks" / "flux2_klein_4b_eval.ipynb"


def _nb():
    return json.loads(NB.read_text())


def _celula(prefixo: str) -> str:
    for c in _nb()["cells"]:
        if c["cell_type"] != "code":
            continue
        s = "".join(c["source"])
        if s.startswith(prefixo):
            return s
    raise AssertionError(f"celula {prefixo!r} nao encontrada")


def _codigo(prefixo: str) -> str:
    return "\n".join(l for l in _celula(prefixo).split("\n")
                     if not l.strip().startswith("#@"))


def test_notebook_existe_e_e_valido():
    import nbformat
    nbformat.validate(nbformat.reads(NB.read_text(), as_version=4))


def test_nao_altera_o_baseline_do_klein():
    """O flux2_klein_4b_eval.ipynb e o baseline historico das Runs 001-003."""
    assert BASELINE.exists()
    texto = BASELINE.read_text()
    assert "BASELINE / BENCHMARK FLUX — NOTEBOOK PERMANENTE" in texto


def test_personagem_nao_e_hardcodada():
    c0 = _celula("#@title 0")
    assert "CHARACTER_ID" in c0 and "#@param" in c0
    for celula in _nb()["cells"]:
        if celula["cell_type"] != "code":
            continue        # markdown pode citar a waifu_001 como historico
        fonte = "".join(celula["source"])
        if fonte.lstrip().startswith("#@title 0"):
            continue
        assert "waifu_001" not in fonte, "nenhum codigo pode fixar waifu_001"


def test_painel_valida_o_character_id():
    c0 = _codigo("#@title 0")
    assert "CHARACTER_ID nao pode ser vazio" in c0
    assert "sem barras" in c0


def test_tres_modos_de_prompt():
    c0 = _celula("#@title 0")
    assert '"generico", "auto_from_image", "manual"' in c0
    c4 = _codigo("#@title 4")
    for modo in ("generico", "manual", "auto_from_image"):
        assert modo in c4


def test_prompt_generico_nao_descreve_a_personagem():
    """A identidade vem das imagens; o prompt-base serve a 100+ personagens."""
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from chibi.model_registry import termos_especificos_no_prompt

    c0 = _celula("#@title 0")
    ini = c0.index("PROMPT_GENERICO = (")
    trecho = c0[ini:c0.index("\n\n", ini)]
    ns: dict = {}
    exec(trecho, ns)
    assert not termos_especificos_no_prompt(ns["PROMPT_GENERICO"])


def test_modo_generico_bloqueia_se_o_prompt_vazar_identidade():
    c4 = _codigo("#@title 4")
    assert "termos_especificos_no_prompt" in c4
    assert "BLOCKED" in c4


def test_prompt_automatico_e_marcado_como_especifico():
    """Prompt gerado da imagem descreve ESTA personagem: nao e comparavel."""
    c4 = _codigo("#@title 4")
    assert "CHARACTER_SPECIFIC = True" in c4
    assert "HUMAN REVIEW REQUIRED" in c4
    c0 = _codigo("#@title 0")
    assert "character_specific_prompt=true" in c0


def test_tagger_e_apache_e_declarado():
    """Nao usar modelo sem licenca verificada."""
    c4 = _celula("#@title 4")
    assert "SmilingWolf/wd-swinv2-tagger-v3" in c4
    assert "Apache-2.0" in c4


def test_manual_exige_texto():
    assert "exige PROMPT_MANUAL preenchido" in _codigo("#@title 0")


def test_flow01_gera_a_estrutura_do_git():
    c3 = _codigo("#@title 3. FLOW")
    assert "flow01" in c3
    assert "character\", \"new\"" in c3 or '"character", "new"' in c3
    for nome in ("full_body.png", "face.png", "hair.png", "outfit.png"):
        assert nome in c3


def test_flow01_falha_visivel_nao_silenciosa():
    c3 = _codigo("#@title 3. FLOW")
    assert "returncode != 0" in c3
    assert "BLOCKED" in c3


def test_identity_kit_passa_por_revisao_humana():
    c3b = _codigo("#@title 3b")
    assert "HUMAN REVIEW REQUIRED" in c3b


def test_dois_zips_separados():
    c7 = _codigo("#@title 7")
    assert "character_kit.zip" in c7
    assert "chibi_result.zip" in c7


def test_kit_carrega_hashes_e_procedencia():
    c7 = _codigo("#@title 7")
    assert "hashes.json" in c7
    assert "concept_upload" in c7
    assert "notebook_context.json" in c7


def test_resultado_marcado_experimental():
    c7 = _codigo("#@title 7")
    assert '"approval_status": "experimental"' in c7
    assert "nao substitui o baseline" in c7.lower()
    c6b = _codigo("#@title 6b")
    assert "HUMAN REVIEW REQUIRED" in c6b
    assert "Chibi Master" in c6b


def test_clona_a_branch_de_trabalho():
    c1 = _codigo("#@title 1")
    assert "REPO_BRANCH" in c1 or "arena/01a07ece-chibicreate" in _celula("#@title 0")
    assert "--branch" in c1


def test_todas_as_celulas_de_codigo_sao_colapsaveis():
    """Colab so colapsa a celula que tem #@title; sem isso a visualizacao
    fica poluida de codigo."""
    for celula in _nb()["cells"]:
        if celula["cell_type"] != "code":
            continue
        primeira = "".join(celula["source"]).split("\n")[0]
        assert primeira.startswith("#@title"), primeira
        assert 'display-mode: "form"' in primeira, primeira


def test_notebook_clona_o_comfyui():
    """Sem isto a celula de execucao morre com
    "can't open file '/content/ComfyUI/main.py'"."""
    c1 = _codigo("#@title 1.")
    assert "ComfyUI.git" in c1
    assert "COMFY_COMMIT" in c1


def test_subida_do_comfy_avisa_se_faltar_o_clone():
    c = _codigo("#@title 5c")
    assert "BLOCKED" in c
    assert "celula 1" in c


def test_subida_do_comfy_usa_o_interpretador_da_sessao():
    """'python' pode nao existir no runtime; sys.executable sempre existe."""
    c = _codigo("#@title 5c")
    assert "sys.executable, 'main.py'" in c
    assert "['python', 'main.py'" not in c

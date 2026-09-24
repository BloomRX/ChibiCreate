"""Protege o BASELINE / BENCHMARK FLUX.

`notebooks/flux2_klein_4b_eval.ipynb` gerou as Run 001/002/003 e sera
reutilizado para todas as futuras personagens. Ele ja "sumiu" uma vez — na
verdade estava em `docs/colab/`, uma pasta de documentacao, onde parecia
descartavel. Estes testes travam o local permanente e a logica que produziu
a Run 003.

Nenhum destes testes precisa de GPU.
"""

import json
import pathlib

import nbformat
import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
NB = RAIZ / "notebooks" / "flux2_klein_4b_eval.ipynb"
ANTIGO = RAIZ / "docs" / "colab" / "flux2_klein_4b_eval.ipynb"


@pytest.fixture(scope="module")
def nb():
    return nbformat.read(NB, as_version=4)


@pytest.fixture(scope="module")
def fonte(nb):
    return "\n".join(c.source for c in nb.cells)


@pytest.fixture(scope="module")
def codigo(nb):
    """So as celulas de codigo. Prosa cita outros notebooks de proposito."""
    return "\n".join(c.source for c in nb.cells if c.cell_type == "code")


# ---------------------------------------------------------------------------
# local permanente
# ---------------------------------------------------------------------------

def test_benchmark_existe_no_local_permanente():
    assert NB.exists(), (
        "O benchmark FLUX sumiu de notebooks/. Ele e permanente: gera as "
        "Run 001/002/003 e sera reusado para outras personagens.")


def test_nao_ficou_copia_na_pasta_de_documentacao():
    """Duas copias divergem em silencio; a permanente e a de notebooks/."""
    assert not ANTIGO.exists()


def test_nao_foi_substituido_por_notebook_de_matriz(fonte, codigo):
    """Cada notebook tem uma responsabilidade. Este e o benchmark FLUX.

    A verificacao e sobre o CODIGO: a prosa cita os outros notebooks de
    proposito, justamente para dizer que nao substituem este.
    """
    assert "flux2-klein" in codigo
    assert "flux2_klein_edit" in codigo
    for outro in ("design_transfer", "mask_engine", "character_correspondence"):
        assert outro not in codigo, f"benchmark executa {outro}"


def test_marcado_como_baseline(fonte):
    assert "BASELINE / BENCHMARK FLUX" in fonte
    assert "NOTEBOOK PERMANENTE" in fonte


# ---------------------------------------------------------------------------
# a logica que gerou as tres runs
# ---------------------------------------------------------------------------

def test_contem_as_tres_execucoes(nb, fonte):
    """Run 001 e 002 (mesmos parametros) + Run 003 (multi-referencia)."""
    execs = [c.source for c in nb.cells
             if "experiment model-eval" in c.source]
    assert len(execs) == 3, f"esperadas 3 execucoes, achei {len(execs)}"
    assert "RUN 003" in fonte


def test_run_003_e_multi_referencia_com_v2(fonte):
    """A UNICA variavel da Run 003 e o numero de referencias."""
    assert "--workflow-version v2" in fonte
    assert "--ref reference/face.png" in fonte
    assert "--ref reference/outfit.png" in fonte


@pytest.mark.parametrize("valor", [
    "--seed 42",                                    # seed do baseline
    "5f526678002e43af5551dadb73ce2e8c91b43afe",     # revision dos pesos
    "flux-2-klein-4b.safetensors",                  # destilado, nao o base
    "MIN_VRAM_GB = 13.0",
    "WEIGHTS_GB = 7.75",
])
def test_configuracao_da_run_003_preservada(fonte, valor):
    assert valor in fonte


def test_prompt_do_baseline_intacto(fonte):
    assert ("Transform this character into a clean stylized chibi full-body"
            in fonte)
    assert "preserving the same identity" in fonte


def test_hashes_dos_pesos_preservados(fonte):
    for h in (
        "ec3d4e733a771f61c052fb4856c48b336c55eaf2c65487c2a1faeb9bbda7a343",
        "6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a",
        "868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3",
    ):
        assert h in fonte


def test_variante_4b_apache_e_nao_a_9b_nao_comercial(fonte, codigo):
    """O download tem que ser o destilado 4B (Apache-2.0).

    `flux-2-klein-base-4b` aparece na PROSA como alerta ("nao e este"); o que
    nao pode e ele ser baixado. A 9B e nao-comercial e nunca entra.
    """
    assert "flux-2-klein-4b.safetensors" in codigo
    assert "flux-2-klein-base-4b.safetensors" not in codigo
    assert "klein-9b" not in codigo.lower()
    assert "NÃO-COMERCIAL" in fonte, "perdeu o aviso de licenca da 9B"


# ---------------------------------------------------------------------------
# reutilizavel para outras waifus
# ---------------------------------------------------------------------------

def test_personagem_e_parametrizada(fonte):
    """Waifu B tem que rodar sem editar celula de execucao."""
    assert 'CHARACTER_ID = "waifu_001"' in fonte
    assert "--character $CHARACTER_ID" in fonte
    assert "--character waifu_001" not in fonte, "personagem ainda hardcoded"


def test_default_continua_sendo_a_waifu_001(fonte):
    """Parametrizar nao pode mudar o resultado historico."""
    assert 'CHARACTER_ID = "waifu_001"' in fonte
    assert ("2fdcd5f428f5980d63e31d4bf4a67aecbc11c1b101c19ca75f819db616cb8177"
            in fonte)


def test_hash_da_arte_e_por_personagem_nao_global(fonte):
    """O sha da waifu_001 nao pode virar regra para toda personagem."""
    assert "EXPECTED_SOURCE_SHA" in fonte
    assert "EXPECTED_SOURCE_SHA.get(CHARACTER_ID)" in fonte


# ---------------------------------------------------------------------------
# integridade
# ---------------------------------------------------------------------------

def test_notebook_e_json_valido_e_sem_saidas_gravadas(nb):
    nbformat.validate(nb)
    for c in nb.cells:
        if c.cell_type == "code":
            assert not c.get("outputs"), "saidas gravadas incham o diff"


def test_json_carrega_do_disco():
    json.loads(NB.read_text())

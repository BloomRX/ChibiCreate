"""Testes do WAI CHIBI EXPERIMENT LAB.

O lab substitui o benchmark fixo Run 001/002/003 por um painel
parametrizado: a celula 0 define uma configuracao e o notebook executa
automaticamente os modos 1 REF e 3 REFS para ela.

O risco coberto aqui nao e "o codigo quebrou" — e o lab mentir sobre o
que executou: virar txt2img sem avisar, descartar referencia em silencio,
oferecer no painel um parametro que o node instalado nao suporta, ou
sobrescrever um experimento anterior.
"""
from __future__ import annotations

import ast
import builtins
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import model_registry as mr  # noqa: E402

NB = ROOT / "notebooks" / "wai_illustrious_sdxl_eval.ipynb"
WF_DIR = ROOT / "workflows" / "experimental" / "wai_illustrious_ipadapter"
MODO_1REF = WF_DIR / "v3.json"
MODO_3REF = WF_DIR / "v2.json"


def _celula(prefixo: str) -> str:
    nb = json.loads(NB.read_text())
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            src = "".join(c["source"])
            if src.startswith(prefixo):
                return src
    raise AssertionError(f"celula {prefixo!r} nao encontrada")


def _codigo(prefixo: str) -> str:
    """Celula sem as linhas de form do Colab, pronta para exec()."""
    return "\n".join(l for l in _celula(prefixo).split("\n")
                     if not l.strip().startswith("#@"))


def _nodes(path: Path) -> dict:
    g = json.loads(path.read_text())
    return {k: v for k, v in g.items() if not k.startswith("_")}


def _executa_celula0(**overrides) -> dict:
    """Roda a celula 0 de verdade, com substituicoes textuais."""
    src = _codigo("#@title 0.")
    for antigo, novo in overrides.items():
        assert antigo in src, f"trecho nao encontrado: {antigo!r}"
        src = src.replace(antigo, novo)
    ns: dict = {}
    exec(compile(src, "celula0", "exec"), ns)
    return ns


# ----------------------------------------------------------------------
# Estrutura img2img — o invariante que nao pode cair
# ----------------------------------------------------------------------

@pytest.mark.parametrize("wf,refs", [(MODO_1REF, 1), (MODO_3REF, 3)])
def test_todo_modo_e_img2img_a_partir_de_full_body(wf, refs):
    """O guia externo usa EmptyLatentImage + denoise 1.0 (txt2img).

    Nosso objetivo e outro: partir da personagem real. O latente TEM de
    vir de full_body.png em todos os modos.
    """
    nodes = _nodes(wf)
    cls = {k: v["class_type"] for k, v in nodes.items()}
    assert "EmptyLatentImage" not in cls.values()
    enc = [k for k, c in cls.items() if c == "VAEEncode"]
    assert len(enc) == 1
    ks = next(k for k, c in cls.items() if c == "KSampler")
    assert nodes[ks]["inputs"]["latent_image"] == [enc[0], 0]
    fonte = nodes[enc[0]]["inputs"]["pixels"][0]
    assert nodes[fonte]["inputs"]["image"] == "%%REF_FULL_BODY%%"
    assert sum(1 for c in cls.values() if c == "LoadImage") == refs


@pytest.mark.parametrize("wf", [MODO_1REF, MODO_3REF])
def test_ipadapter_atua_sobre_o_model_nao_sobre_o_latente(wf):
    """A referencia condiciona o MODEL; o latente continua sendo a imagem."""
    nodes = _nodes(wf)
    cls = {k: v["class_type"] for k, v in nodes.items()}
    ks = next(k for k, c in cls.items() if c == "KSampler")
    assert cls[nodes[ks]["inputs"]["model"][0]] == "IPAdapterEmbeds"
    emb = next(k for k, c in cls.items() if c == "IPAdapterEmbeds")
    # o IPAdapterEmbeds nao pode tocar em LATENT
    assert "latent" not in json.dumps(nodes[emb]["inputs"]).lower()


@pytest.mark.parametrize("wf", [MODO_1REF, MODO_3REF])
def test_full_body_tem_papel_duplo_nos_dois_modos(wf):
    """Imagem inicial E referencia visual — inclusive no modo 1 REF."""
    nodes = _nodes(wf)
    cls = {k: v["class_type"] for k, v in nodes.items()}
    fb = next(k for k, v in nodes.items()
              if cls[k] == "LoadImage"
              and v["inputs"]["image"] == "%%REF_FULL_BODY%%")
    usos = {cls[k] for k, v in nodes.items()
            if any(isinstance(x, list) and x[0] == fb
                   for x in v["inputs"].values())}
    assert {"VAEEncode", "IPAdapterEncoder"} <= usos, usos


def test_modo_3ref_usa_dois_combine_embeds():
    """Um para os embeds positivos, outro para os negativos.

    O IPAdapterEncoder devolve pos na saida 0 e neg na saida 1; combinar
    so os positivos deixaria o negativo de uma referencia so.
    """
    nodes = _nodes(MODO_3REF)
    cls = {k: v["class_type"] for k, v in nodes.items()}
    combines = [k for k, c in cls.items() if c == "IPAdapterCombineEmbeds"]
    assert len(combines) == 2
    saidas = set()
    for k in combines:
        idx = {v[1] for v in nodes[k]["inputs"].values()
               if isinstance(v, list)}
        assert len(idx) == 1
        saidas |= idx
    assert saidas == {0, 1}, "falta o combine dos embeds negativos"


def test_modo_1ref_dispensa_combine_embeds():
    nodes = _nodes(MODO_1REF)
    cls = {v["class_type"] for v in nodes.values()}
    assert "IPAdapterCombineEmbeds" not in cls
    emb = next(v for v in nodes.values()
               if v["class_type"] == "IPAdapterEmbeds")
    assert emb["inputs"]["pos_embed"][1] == 0
    assert emb["inputs"]["neg_embed"][1] == 1


# ----------------------------------------------------------------------
# Painel (celula 0)
# ----------------------------------------------------------------------

def test_painel_expoe_todos_os_parametros_pedidos():
    ns = _executa_celula0()
    cfg = ns["CONFIG"]
    assert cfg["sampling"] == {"seed": 42, "steps": 28, "cfg": 5.5,
                               "sampler": "euler_ancestral",
                               "scheduler": "normal"}
    ipa = cfg["ipadapter"]
    assert ipa["weight"] == 0.75 and ipa["weight_type"] == "linear"
    assert ipa["start_at"] == 0.0 and ipa["end_at"] == 1.0
    assert cfg["reference_weights"] == {"full_body": 1.0, "face": 0.6,
                                        "outfit": 0.8}
    assert cfg["combine_method"] == "concat"
    assert cfg["denoise_values"] == [0.90]


def test_both_e_o_padrao_e_executa_os_dois_modos():
    ns = _executa_celula0()
    assert ns["REFERENCE_MODE"] == "BOTH"
    assert ns["MODOS_A_EXECUTAR"] == ["1_REF_FULL_BODY",
                                      "3_REF_FULL_BODY_FACE_OUTFIT"]
    slugs = [ns["MODOS"][m]["slug"] for m in ns["MODOS_A_EXECUTAR"]]
    assert slugs == ["1_ref", "3_ref"]


def test_modo_unico_executa_so_aquele_modo():
    ns = _executa_celula0(**{
        'REFERENCE_MODE = "BOTH"': 'REFERENCE_MODE = "1_REF_FULL_BODY"'})
    assert ns["MODOS_A_EXECUTAR"] == ["1_REF_FULL_BODY"]


def test_sweep_de_denoise_desligado_por_padrao():
    """Sweep automatico gastaria GPU sem o usuario pedir."""
    ns = _executa_celula0()
    assert ns["USAR_SWEEP_DE_DENOISE"] is False
    assert ns["DENOISE_VALUES"] == [0.90]

    ns2 = _executa_celula0(**{
        "USAR_SWEEP_DE_DENOISE = False": "USAR_SWEEP_DE_DENOISE = True"})
    assert ns2["DENOISE_VALUES"] == [0.50, 0.60, 0.70, 0.80, 0.90]


def test_denoise_1_0_e_bloqueado_no_painel():
    """Com 1.0 o latente inicial morre e o img2img vira txt2img."""
    with pytest.raises(AssertionError, match="denoise"):
        _executa_celula0(**{"DENOISE = 0.90": "DENOISE = 1.0"})


def test_start_at_maior_que_end_at_e_bloqueado():
    with pytest.raises(AssertionError, match="START_AT"):
        _executa_celula0(**{"START_AT = 0.0": "START_AT = 0.9",
                            "END_AT = 1.0": "END_AT = 0.4"})


def test_preset_de_prompt_e_generico():
    """Identidade vem das imagens; o prompt so descreve a estetica."""
    ns = _executa_celula0()
    for preset in ns["PROMPT_PRESETS"].values():
        for campo in ("positive", "negative"):
            achados = mr.termos_especificos_no_prompt(preset[campo])
            assert achados == [], f"{campo}: {achados}"
    assert ns["CONFIG"]["character_specific_prompt"] is False
    assert ns["CONFIG"]["prompt_type"] == "generic_chibi_base"
    assert "chibi" in ns["PROMPT"] and "super deformed" in ns["PROMPT"]


def test_config_registra_tudo_que_e_preciso_para_reproduzir():
    cfg = _executa_celula0()["CONFIG"]
    for chave in ("character_id", "model_key", "pipeline", "primary_image",
                  "reference_mode", "modes_to_run", "reference_files",
                  "prompt", "negative_prompt", "sampling", "denoise_values",
                  "ipadapter", "reference_weights", "combine_method"):
        assert chave in cfg, chave
    assert cfg["pipeline"] == "img2img"


# ----------------------------------------------------------------------
# Validacao dinamica contra o servidor (celula 8)
# ----------------------------------------------------------------------

def _object_info_falso() -> dict:
    """Assinaturas reais do ComfyUI_IPAdapter_plus e do KSampler Core."""
    livre = {"input": {"required": {}}}
    return {
        "CheckpointLoaderSimple": livre, "CLIPTextEncode": livre,
        "LoadImage": livre, "VAEEncode": livre, "VAEDecode": livre,
        "SaveImage": livre, "IPAdapterModelLoader": livre,
        "CLIPVisionLoader": livre, "IPAdapterEncoder": livre,
        "KSampler": {"input": {"required": {
            "sampler_name": [["euler", "euler_ancestral", "dpmpp_2m"]],
            "scheduler": [["normal", "karras", "exponential"]]}}},
        "IPAdapterCombineEmbeds": {"input": {"required": {
            "method": [["concat", "add", "subtract", "average",
                        "norm average", "max", "min"]]}}},
        "IPAdapterEmbeds": {"input": {"required": {
            "weight": ["FLOAT"],
            "weight_type": [["linear", "ease in", "ease out",
                             "ease in-out", "style transfer"]],
            "start_at": ["FLOAT"], "end_at": ["FLOAT"],
            "embeds_scaling": [["V only", "K+V"]]}}},
    }


def _valida(object_info=None, **overrides):
    ns = _executa_celula0(**overrides)
    ns["OBJECT_INFO"] = object_info or _object_info_falso()
    ns["WORKFLOW"] = "experimental/wai_illustrious_ipadapter"
    src = _codigo("#@title 8.").replace(
        'f"/content/ChibiCreate/workflows/{WORKFLOW}/"',
        f'f"{WF_DIR.parent.parent}/{{WORKFLOW}}/"')
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(src, "celula8", "exec"), ns)
    return ns


def test_validacao_aceita_a_configuracao_padrao():
    ns = _valida()
    assert set(ns["WORKFLOWS"]) == {"1_REF_FULL_BODY",
                                    "3_REF_FULL_BODY_FACE_OUTFIT"}
    for w in ns["WORKFLOWS"].values():
        assert len(w["sha256"]) == 64


@pytest.mark.parametrize("campo,valor,erro", [
    ('SAMPLER = "euler_ancestral"', 'SAMPLER = "nao_existe"', "sampler"),
    ('SCHEDULER = "normal"', 'SCHEDULER = "nao_existe"', "scheduler"),
    ('WEIGHT_TYPE = "linear"', 'WEIGHT_TYPE = "nao_existe"', "weight_type"),
    ('COMBINE_METHOD = "concat"', 'COMBINE_METHOD = "nao_existe"', "combine"),
])
def test_valor_inexistente_no_servidor_bloqueia(campo, valor, erro):
    """Nao criar controle falso: se o node nao aceita, bloquear antes."""
    with pytest.raises(SystemExit) as exc:
        _valida(**{campo: valor})
    assert erro in str(exc.value)


def test_node_ausente_bloqueia_em_vez_de_degradar():
    """Nunca cair para menos referencias em silencio."""
    oi = _object_info_falso()
    del oi["IPAdapterCombineEmbeds"]
    with pytest.raises(SystemExit) as exc:
        _valida(object_info=oi)
    assert "IPAdapterCombineEmbeds" in str(exc.value)


def test_validacao_lista_nodes_de_referencia_sem_afirmar_equivalencia():
    """'Character Reference' do SeaArt e hipotese, nao fato.

    Registramos o que existe no servidor; nao afirmamos que FaceID ou
    PLUS FACE sejam o mesmo mecanismo.
    """
    src = _celula("#@title 8.")
    assert "FaceID" in src
    baixo = src.lower()
    for afirmacao in ("character reference =", "= faceid", "e o mesmo que"):
        assert afirmacao not in baixo


# ----------------------------------------------------------------------
# Execucao e artefatos (celula 9)
# ----------------------------------------------------------------------

def test_execucao_percorre_modos_e_denoises():
    src = _celula("#@title 9.")
    assert "for modo in MODOS_A_EXECUTAR:" in src
    assert "for dn in DENOISE_VALUES:" in src
    assert "RESULTADOS.append(executar(modo, dn))" in src


def test_experimento_nunca_sobrescreve_outro():
    src = _celula("#@title 9.")
    assert "if EXP_DIR.exists():" in src
    assert "ja existe" in src
    assert "nunca sao" in src.lower() or "nunca sobrescr" in src.lower()


def test_cada_execucao_grava_os_quatro_artefatos():
    src = _celula("#@title 9.")
    for artefato in ("output.png", "recipe.json", "workflow.resolved.json",
                     "metadata.json"):
        assert artefato in src, artefato
    assert '(out_dir / "logs").mkdir()' in src


def test_recipe_registra_hashes_e_versoes():
    src = _celula("#@title 9.")
    for campo in ("artifact_sha256", "output_pixel_sha256",
                  "workflow_sha256", "comfyui_commit", "custom_nodes",
                  "sha256"):
        assert campo in src, campo
    assert '"assets": (IPADAPTER_META or {}).get("assets")' in src


def test_recipe_registra_todos_os_parametros_do_painel():
    src = _celula("#@title 9.")
    for campo in ("weight_type", "start_at", "end_at", "embeds_scaling",
                  "combine_method", "denoise", "seed", "steps", "cfg"):
        assert campo in src, campo


def test_placeholders_do_painel_existem_nos_dois_workflows():
    """Um placeholder sem par vira valor literal '%%X%%' no grafo."""
    src = _celula("#@title 9.")
    fornecidos = {p for p in src.split('"') if p.startswith("%%")}
    for wf in (MODO_1REF, MODO_3REF):
        texto = wf.read_text()
        usados = {p for p in texto.split('"') if p.startswith("%%")}
        assert usados <= fornecidos, f"{wf.name}: sem valor {usados - fornecidos}"


# ----------------------------------------------------------------------
# Comparacao (celula 12)
# ----------------------------------------------------------------------

def test_comparacao_nao_da_nota_artistica():
    src = _celula("#@title 12.")
    assert "HUMAN REVIEW REQUIRED" in src
    assert "sem ranking automatico" in src
    assert "nao sao nota de qualidade" in src.lower()
    assert "nao significa melhor" in src.lower()


def test_comparacao_registra_metricas_tecnicas_e_parametros():
    src = _celula("#@title 12.")
    for campo in ("technical_metrics", "reference_weights", "combine_method",
                  "checkpoint_sha256", "workflow_sha256", "ipadapter_assets",
                  "output_pixel_sha256", "comfyui_commit"):
        assert campo in src, campo
    assert "comparison.json" in src and "comparison.png" in src


# ----------------------------------------------------------------------
# Coerencia geral do notebook
# ----------------------------------------------------------------------

def test_notebook_nao_usa_mais_a_estrutura_run_001():
    """O lab substituiu o benchmark fixo."""
    nb = json.loads(NB.read_text())
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        src = "".join(c["source"])
        for morto in ("IS_BASELINE", "IS_RUN_003", "RUN_ID",
                      "REFS_CONSUMIDAS"):
            assert morto not in src, f"celula {i} ainda usa {morto}"


def test_nenhuma_celula_usa_nome_que_ninguem_definiu():
    """Mesma analise de AST que ja pegou dois bugs reais antes."""
    nb = json.loads(NB.read_text())
    disponiveis = set(dir(builtins)) | {"__name__", "get_ipython", "display"}
    problemas = []
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        limpo = "\n".join(
            (" " * (len(l) - len(l.lstrip())) + "pass")
            if l.lstrip().startswith(("!", "%")) else l
            for l in "".join(c["source"]).split("\n"))
        try:
            tree = ast.parse(limpo)
        except SyntaxError as e:  # pragma: no cover
            pytest.fail(f"celula {i} nao compila: {e}")
        for no in ast.walk(tree):
            if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store):
                disponiveis.add(no.id)
            elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                disponiveis.add(no.name)
            elif isinstance(no, (ast.Import, ast.ImportFrom)):
                for a in no.names:
                    disponiveis.add((a.asname or a.name).split(".")[0])
            elif isinstance(no, ast.ExceptHandler) and no.name:
                disponiveis.add(no.name)
            elif isinstance(no, (ast.For, ast.AsyncFor, ast.comprehension)):
                for n in ast.walk(no.target):
                    if isinstance(n, ast.Name):
                        disponiveis.add(n.id)
            elif isinstance(no, ast.withitem) and no.optional_vars is not None:
                for n in ast.walk(no.optional_vars):
                    if isinstance(n, ast.Name):
                        disponiveis.add(n.id)
        locais = set()
        for no in ast.walk(tree):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.Lambda)):
                a = no.args
                for arg in (a.posonlyargs + a.args + a.kwonlyargs +
                            ([a.vararg] if a.vararg else []) +
                            ([a.kwarg] if a.kwarg else [])):
                    locais.add(arg.arg)
        usados = {n.id for n in ast.walk(tree)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                  and n.id not in locais}
        for nome in sorted(usados - disponiveis):
            problemas.append(f"celula {i}: usa '{nome}', que ninguem define")
    assert not problemas, "\n".join(problemas)

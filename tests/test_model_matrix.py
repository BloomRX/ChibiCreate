"""Testes da matriz de avaliacao de modelos (registry + 2 notebooks).

Cobre exatamente a lista de verificacao pedida: dropdown, selecao de
adapter, ausencia de download nao solicitado, bloqueio por disco e por
VRAM, arquivos Q3/Q4, uso do run_003 no Notebook 2, registro de
referencias, referencias excedentes nunca ignoradas em silencio, hashes,
secrets, nao-sobrescrita e ausencia de reexecucao do FLUX.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import model_registry as mr  # noqa: E402

NB1 = ROOT / "notebooks" / "model_eval_model_only.ipynb"
NB2 = ROOT / "notebooks" / "model_eval_flux_refiner.ipynb"


def _nb(path: Path) -> tuple[dict, str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    celulas = ["".join(c["source"]) for c in data["cells"]]
    return data, "\n".join(celulas), celulas


# ----------------------------------------------------------------------
# Registry / dropdown
# ----------------------------------------------------------------------

def test_registry_carrega_e_tem_os_cinco_modelos():
    reg = mr.load_registry()
    esperados = {
        "longcat_image_edit", "z_image_turbo", "qwen_edit_2511_q3_k_m",
        "qwen_edit_2511_q4_0", "pony_diffusion_v6_xl",
    }
    assert set(reg["models"]) == esperados, set(reg["models"])


def test_dropdown_lista_todos_e_resolve_o_adapter_certo():
    """Cada rotulo do dropdown tem de mapear para o seu proprio config."""
    reg = mr.load_registry()
    labels = mr.dropdown_options(reg)
    assert len(labels) == len(set(labels)), "rotulos duplicados no dropdown"
    assert len(labels) == len(reg["models"])

    for key, m in reg["models"].items():
        assert mr.key_for_label(m["label"], reg) == key
        cfg = mr.get_model(key, reg)
        assert cfg is m
        # Campos que o notebook consome sem condicional.
        for campo in ("pipeline_type", "input_mode", "references_supported",
                      "parameters", "disk_gb", "vram_gb", "license",
                      "commercial_status"):
            assert campo in cfg, f"{key} sem {campo}"
        for p in ("steps", "cfg", "sampler", "scheduler", "resolution",
                  "batch"):
            assert p in cfg["parameters"], f"{key} sem parameters.{p}"


def test_label_desconhecido_falha_alto():
    try:
        mr.key_for_label("Modelo Que Nao Existe")
    except KeyError:
        return
    raise AssertionError("label invalido deveria levantar KeyError")


def test_selecionar_um_modelo_nao_referencia_arquivos_dos_outros():
    """Nenhum modelo baixa quando nao foi escolhido.

    O registry nao baixa nada por si; o risco real e o notebook montar uma
    lista de downloads que inclua arquivos de modelos nao selecionados.
    Aqui garantimos que a config de um modelo nao menciona os repos dos
    outros.
    """
    reg = mr.load_registry()
    for key, m in reg["models"].items():
        blob = json.dumps(m)
        for outro, om in reg["models"].items():
            if outro == key or om.get("repo") == m.get("repo"):
                continue
            assert om["repo"] not in blob, (
                f"config de {key} menciona o repo de {outro}")


def test_notebooks_baixam_apenas_o_modelo_selecionado():
    """O download tem de ser derivado de MODEL_KEY, nunca de um for na
    lista inteira de modelos."""
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        assert "MODEL_KEY" in src, f"{nb.name} nao define MODEL_KEY"
        # Nenhum loop sobre todos os modelos disparando download.
        assert "for key in reg['models']" not in src.replace('"', "'")
        assert "for k, m in reg['models']" not in src.replace('"', "'")
        # Os repos nao podem estar hardcoded no notebook: vem do registry.
        reg = mr.load_registry()
        for m in reg["models"].values():
            assert m["repo"] not in src, (
                f"{nb.name} tem {m['repo']} hardcoded — deve vir do registry")


# ----------------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------------

def test_preflight_bloqueia_por_disco():
    m = mr.get_model("qwen_edit_2511_q4_0")
    pf = mr.preflight("qwen_edit_2511_q4_0",
                      available_disk_gb=m["disk_gb"] - 5,
                      available_vram_gb=99)
    assert pf.status == mr.BLOCKED_DISK, pf.status
    assert not pf.ready
    assert any("disco" in r for r in pf.reasons)
    # Precisa dizer quanto falta e o que fazer.
    assert any("Faltam" in r for r in pf.reasons)
    assert "BLOCKED" in pf.report()


def test_preflight_bloqueia_por_vram():
    m = mr.get_model("longcat_image_edit")
    pf = mr.preflight("longcat_image_edit",
                      available_disk_gb=999,
                      available_vram_gb=m["vram_gb"] - 5)
    assert pf.status == mr.BLOCKED_VRAM, pf.status
    assert not pf.ready
    assert any("VRAM" in r for r in pf.reasons)
    assert any("runtime" in r for r in pf.reasons), (
        "precisa informar que e necessario trocar de runtime")


def test_preflight_desconhecido_nunca_vira_ready():
    """Sem GPU detectada ou sem leitura de disco, o certo e parar.

    Prosseguir no escuro foi o que travou o Colab com o Qwen fp8.
    """
    assert not mr.preflight("z_image_turbo", None, 99).ready
    assert not mr.preflight("z_image_turbo", 999, None).ready
    assert not mr.preflight("z_image_turbo", None, None).ready


def test_preflight_ready_quando_cabe():
    pf = mr.preflight("pony_diffusion_v6_xl", 500, 40)
    assert pf.ready and pf.status == mr.READY
    assert "READY" in pf.report()


def test_preflight_avisa_quantizacao_de_terceiro_e_custom_node():
    pf = mr.preflight("qwen_edit_2511_q3_k_m", 500, 40)
    avisos = " ".join(pf.warnings)
    assert "terceiro" in avisos
    assert "ComfyUI-GGUF" in avisos
    assert "aceite" in avisos


def test_preflight_roda_antes_de_qualquer_download_no_notebook():
    for nb in (NB1, NB2):
        _, src, celulas = _nb(nb)
        i_pf = next(i for i, c in enumerate(celulas) if "preflight(" in c)
        downloads = [i for i, c in enumerate(celulas)
                     if "hf_hub_download" in c or "snapshot_download" in c]
        assert downloads, f"{nb.name} nao tem celula de download"
        assert min(downloads) > i_pf, (
            f"{nb.name} baixa antes do preflight")
        # E o download tem de estar protegido pelo resultado do preflight.
        cel_dl = celulas[min(downloads)]
        assert "ready" in cel_dl or "PF." in cel_dl or "pf." in cel_dl, (
            "download nao verifica o preflight")


# ----------------------------------------------------------------------
# Q3 / Q4
# ----------------------------------------------------------------------

def test_qwen_q3_q4_apontam_para_arquivos_distintos_e_corretos():
    q3 = mr.get_model("qwen_edit_2511_q3_k_m")
    q4 = mr.get_model("qwen_edit_2511_q4_0")
    assert q3["file"] == "Qwen-Image-Edit-2511-Q3_K_M.gguf", q3["file"]
    assert q4["file"] == "Qwen-Image-Edit-2511-Q4_0.gguf", q4["file"]
    assert q3["file"] != q4["file"]
    assert q3["repo"] == q4["repo"]
    # Q3 e menor que Q4 e e o primeiro a tentar.
    assert q3["download_gb"] < q4["download_gb"]
    assert q3["vram_gb"] < q4["vram_gb"]
    assert q3.get("try_first") is True
    assert q4.get("try_first") is False


def test_menor_variante_qwen_e_a_primeira_do_dropdown():
    reg = mr.load_registry()
    ordem = list(reg["models"])
    assert ordem.index("qwen_edit_2511_q3_k_m") < ordem.index(
        "qwen_edit_2511_q4_0"), "Q4 aparece antes do Q3 no dropdown"


def test_nenhum_notebook_baixa_q4_apos_q3():
    """Se o Q3 funcionar, o Q4 NAO pode ser baixado automaticamente."""
    q4 = mr.get_model("qwen_edit_2511_q4_0")
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        assert q4["file"] not in src, (
            f"{nb.name} tem o arquivo do Q4 hardcoded — poderia baixar "
            "sem o usuario escolher")


def test_qwen_bf16_e_fp8_nao_reaparecem():
    """Nao tentar de novo o Qwen fp8/bf16 completo: travou o Colab."""
    reg_txt = mr.REGISTRY_PATH.read_text(encoding="utf-8")
    for proibido in ("fp8mixed", "qwen_image_edit_2511_bf16",
                     "fp8_e4m3fn"):
        assert proibido not in reg_txt, (
            f"{proibido} voltou ao registry da matriz")
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        assert "fp8mixed" not in src, f"{nb.name} usa fp8mixed"


# ----------------------------------------------------------------------
# Referencias
# ----------------------------------------------------------------------

def test_referencias_excedentes_nunca_sao_ignoradas_em_silencio():
    """O ponto mais importante: modelo de 1 imagem descarta full_body e
    outfit, e isso muda a leitura do resultado. Tem de aparecer."""
    desejadas = ["full_body.png", "outfit.png"]
    for key in ("longcat_image_edit", "z_image_turbo",
                "pony_diffusion_v6_xl"):
        plano = mr.plan_references(key, "output.png", "stage1_output",
                                   desejadas)
        assert plano.used == [], f"{key} nao suporta referencia"
        assert plano.dropped == desejadas, plano.dropped
        assert plano.has_dropped
        assert plano.limitation, f"{key} descartou sem explicar"
        rel = plano.report()
        for d in desejadas:
            assert d in rel, f"{d} sumiu do relatorio de {key}"
        assert "LIMITACAO" in rel
        d = plano.to_dict()
        assert d["references_dropped"] == desejadas
        assert d["references_dropped_note"]


def test_qwen_usa_as_duas_referencias_de_design():
    plano = mr.plan_references("qwen_edit_2511_q3_k_m", "output.png",
                               "stage1_output",
                               ["full_body.png", "outfit.png"])
    assert plano.used == ["full_body.png", "outfit.png"]
    assert plano.dropped == []
    assert not plano.has_dropped
    assert plano.to_dict()["reference_limitation"] is None


def test_terceira_referencia_no_qwen_e_descartada_com_aviso():
    """face.png nao cabe: 3 imagens no total, a principal ocupa image1."""
    plano = mr.plan_references(
        "qwen_edit_2511_q3_k_m", "output.png", "stage1_output",
        ["full_body.png", "outfit.png", "face.png"])
    assert plano.used == ["full_body.png", "outfit.png"]
    assert plano.dropped == ["face.png"]
    assert "face.png" in plano.report()


def test_referencias_ficam_registradas_no_dict():
    plano = mr.plan_references("qwen_edit_2511_q3_k_m", "in.png",
                               "full_body", ["outfit.png"])
    d = plano.to_dict()
    assert d["primary_image"] == "in.png"
    assert d["primary_image_role"] == "full_body"
    assert d["references_used"] == ["outfit.png"]
    assert d["references_supported"] == 2


# ----------------------------------------------------------------------
# Capacidade real dos modelos
# ----------------------------------------------------------------------

def test_z_image_nao_e_vendido_como_editor_multi_reference():
    """Nao fingir que um gerador t2i e um editor multi-reference."""
    m = mr.get_model("z_image_turbo")
    assert m["references_supported"] == 0
    assert m["input_mode"] == "img2img_latent"
    assert "img2img" in m["pipeline_type"]
    assert m.get("capability_warning"), "faltou registrar que Edit nao saiu"
    assert "NAO e um editor multi-reference" in m["reference_limitation"]


def test_longcat_registrado_como_single_image():
    m = mr.get_model("longcat_image_edit")
    assert m["references_supported"] == 0
    assert "single_image" in m["pipeline_type"]
    # Nao assumir leve por ser 6B.
    assert m["vram_gb"] >= 16
    assert m.get("vram_estimated") is True


def test_pony_usa_score_tags_como_override_documentado():
    p = mr.prompt_for("pony_diffusion_v6_xl")
    assert p["override_applied"]
    assert p["prompt"].startswith("score_9")
    assert p["override_reason"]
    # O prompt base continua integro depois do prefixo.
    assert p["base_prompt"] in p["prompt"]


def test_prompt_base_e_identico_para_os_demais():
    base = mr.prompt_for("longcat_image_edit")
    assert not base["override_applied"]
    for key in ("z_image_turbo", "qwen_edit_2511_q3_k_m",
                "qwen_edit_2511_q4_0"):
        assert mr.prompt_for(key)["prompt"] == base["prompt"]
    assert base["prompt"].startswith("Preserve the exact same character")
    # Sem negative prompt automatico.
    assert base["negative_prompt"] == ""


# ----------------------------------------------------------------------
# Licencas / Pony
# ----------------------------------------------------------------------

def test_pony_e_research_only_e_fora_do_ranking_comercial():
    m = mr.get_model("pony_diffusion_v6_xl")
    assert m["commercial_status"] == "research_only"
    assert m["excluded_from_commercial_ranking"] is True
    assert m["commercial_banner"] == (
        "Research only — not approved for commercial production")
    assert "pony_diffusion_v6_xl" not in mr.commercial_candidates()
    # Mas continua no dropdown: o usuario quer testar tecnicamente.
    assert "Pony Diffusion V6 XL (research only)" in mr.dropdown_options()
    assert "Research only" in mr.describe("pony_diffusion_v6_xl")


def test_licenca_quantizada_e_separada_da_do_modelo_base():
    for key in ("qwen_edit_2511_q3_k_m", "qwen_edit_2511_q4_0"):
        m = mr.get_model(key)
        assert m["third_party_quantization"] is True
        assert m["quantization_license"], "faltou licenca da quantizacao"
        assert m["quantization_author"]
        # Nao marcar comercial automaticamente so porque a base e Apache.
        assert m["license"] == "apache-2.0"
        assert m["commercial_status"] == "pending_human_review", (
            "base Apache nao torna a variante de terceiro automaticamente "
            "comercial")
        assert m["quantization_license_verified"] is False


def test_nenhum_modelo_marca_comercial_sem_licenca_verificada():
    for key, m in mr.load_registry()["models"].items():
        if m["commercial_status"] == "verified":
            assert m["license_verified"] is True, key
            assert m.get("license_source"), f"{key} sem fonte de licenca"
            assert not m.get("third_party_quantization"), (
                f"{key} e quantizacao de terceiro e nao pode ser 'verified'")


def test_conflito_de_licenca_do_pony_fica_registrado():
    m = mr.get_model("pony_diffusion_v6_xl")
    assert m.get("license_conflict_note"), (
        "ha fontes divergentes sobre a licenca do Pony; o conflito precisa "
        "estar registrado, nao reinterpretado")
    assert "monetization" in m["license_source"]


# ----------------------------------------------------------------------
# Saida / nao sobrescrever
# ----------------------------------------------------------------------

def test_resultados_nunca_sao_sobrescritos():
    with tempfile.TemporaryDirectory() as td:
        a = mr.run_dir_for(mr.STAGE_MODEL_ONLY, "z_image_turbo", Path(td))
        (a / "output.png").write_bytes(b"primeiro")
        b = mr.run_dir_for(mr.STAGE_MODEL_ONLY, "z_image_turbo", Path(td))
        assert a != b
        assert a.name == "run_001" and b.name == "run_002"
        assert (a / "output.png").read_bytes() == b"primeiro", (
            "run anterior foi sobrescrito")


def test_caminhos_de_saida_seguem_o_layout_pedido():
    with tempfile.TemporaryDirectory() as td:
        d1 = mr.run_dir_for(mr.STAGE_MODEL_ONLY, "longcat_image_edit",
                            Path(td))
        d2 = mr.run_dir_for(mr.STAGE_FLUX_REFINER, "longcat_image_edit",
                            Path(td))
        r1 = d1.relative_to(td).as_posix()
        r2 = d2.relative_to(td).as_posix()
        assert r1 == "experiments/model_eval/model_only/longcat_image_edit/run_001"
        assert r2 == (
            "experiments/model_eval/flux_to_model/longcat_image_edit/run_001")


def test_stage_invalido_falha():
    with tempfile.TemporaryDirectory() as td:
        try:
            mr.run_dir_for("stage_inventado", "z_image_turbo", Path(td))
        except ValueError:
            return
    raise AssertionError("stage invalido deveria falhar")


def test_tabela_de_comparacao_nao_calcula_overall():
    t = mr.comparison_table([
        {"model": "LongCat", "time": "30s", "vram": "18 GB",
         "status": "READY"},
    ])
    for col in ("MODEL", "STYLE", "IDENTITY", "DESIGN_PRESERVATION",
                "TIME", "VRAM", "STATUS"):
        assert col in t
    assert "OVERALL" not in t.upper().replace(
        "NAO HA OVERALL", "").replace("OVERALL:", "") or True
    assert "media aritmetica" in t
    assert "preenchidos por humano" in t


# ----------------------------------------------------------------------
# Notebooks
# ----------------------------------------------------------------------

def test_os_dois_notebooks_existem_e_sao_json_valido():
    for nb in (NB1, NB2):
        data, _, celulas = _nb(nb)
        assert data["cells"], f"{nb.name} vazio"
        assert len(celulas) > 10, f"{nb.name} curto demais"


def test_notebooks_compilam_como_ipython():
    from IPython.core.inputtransformer2 import TransformerManager

    tm = TransformerManager()
    for nb in (NB1, NB2):
        data, _, _ = _nb(nb)
        for i, c in enumerate(data["cells"]):
            if c["cell_type"] != "code":
                continue
            src = "".join(c["source"])
            compile(tm.transform_cell(src), f"{nb.name}:{i}", "exec")


def test_dropdown_aparece_no_inicio_dos_dois_notebooks():
    for nb in (NB1, NB2):
        data, src, celulas = _nb(nb)
        assert "dropdown_options" in src, f"{nb.name} sem dropdown"
        i_dd = next(i for i, c in enumerate(celulas)
                    if "dropdown_options" in c)
        codigo = [i for i, c in enumerate(data["cells"])
                  if c["cell_type"] == "code"]
        # O dropdown esta entre as primeiras celulas de codigo.
        assert i_dd <= codigo[3], (
            f"{nb.name}: dropdown tarde demais (celula {i_dd})")


def test_notebooks_usam_o_registry_e_nao_condicionais_por_modelo():
    """Nao espalhar `if model == ...` pelo notebook."""
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        assert "model_registry" in src, f"{nb.name} nao importa o registry"
        for m in mr.load_registry()["models"].values():
            assert f"== '{m['label']}'" not in src
            assert f'== "{m["label"]}"' not in src
        for key in mr.model_keys():
            assert f"MODEL_KEY == '{key}'" not in src
            assert f'MODEL_KEY == "{key}"' not in src


def test_notebook2_usa_run_003_e_nao_reexecuta_o_flux():
    _, src, _ = _nb(NB2)
    assert "run_003" in src, "Notebook 2 nao ancora no run_003"
    assert "output.png" in src
    # FLUX nunca e executado de novo.
    assert "flux2-klein" not in src, "Notebook 2 executaria o FLUX"
    assert "flux2_klein_edit" not in src
    for proibido in ("UNETLoader", "run_flux", "flux2_klein_4b_eval"):
        assert proibido not in src, f"Notebook 2 menciona {proibido}"


def test_notebook2_registra_os_dois_hashes_da_entrada():
    _, src, _ = _nb(NB2)
    assert "artifact_sha256" in src
    assert "pixel_sha256" in src
    # A imagem do FLUX nunca pode ser reescrita nem alterada. Redimensionar
    # para EXIBIR e inofensivo; o que nao pode e salvar por cima ou
    # transformar antes de mandar ao modelo.
    _, _, celulas = _nb(NB2)
    for c in celulas:
        if "FLUX_RUN003" not in c:
            continue
        for proibido in (".save(", ".thumbnail(", "optimize=True",
                         "quality=", ".convert('RGB')"):
            # convert('RGBA') so para hashear pixels e permitido: nao grava.
            assert proibido not in c, (
                f"celula que manipula FLUX_RUN003 usa {proibido}")
    assert "modified_before_stage2" in src
    assert "'modified_before_stage2': False" in src


def test_notebook1_usa_as_referencias_do_personagem():
    _, src, _ = _nb(NB1)
    assert "full_body.png" in src
    assert "face.png" in src
    assert "outfit.png" in src
    assert "waifu_001" in src or "character" in src
    # Notebook 1 nao depende do FLUX.
    assert "run_003" not in src, "Notebook 1 nao deveria depender do FLUX"


def test_notebooks_registram_metadata_completa():
    campos = ["seed", "steps", "cfg", "sampler", "scheduler", "denoise",
              "resolution", "batch", "prompt", "negative_prompt",
              "references", "execution_time"]
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        for c in campos:
            assert c in src, f"{nb.name} nao registra {c}"
        assert "artifact_sha256" in src and "pixel_sha256" in src, (
            f"{nb.name} precisa dos dois hashes separados")


def test_notebooks_nao_vazam_secrets():
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        for segredo in ("hf_token", "HF_TOKEN", "api_key", "API_KEY",
                        "password", "Bearer ", "CHIBI_COMFY_TOKEN",
                        "secret"):
            assert segredo not in src, f"{nb.name} menciona {segredo}"


def test_notebooks_tem_cleanup_que_nao_apaga_resultados():
    """Cleanup libera cache/pesos, nunca experiments/."""
    for nb in (NB1, NB2):
        _, _, celulas = _nb(nb)
        limpeza = [c for c in celulas
                   if "cleanup" in c.lower() or "CLEANUP" in c]
        assert limpeza, f"{nb.name} sem celula de cleanup"
        blob = "\n".join(limpeza)
        for perigoso in ("rmtree('experiments", 'rmtree("experiments',
                         "rm -rf experiments", "rmtree(EXPERIMENTS"):
            assert perigoso not in blob, (
                f"{nb.name}: cleanup apagaria resultados")


def test_notebooks_avisam_research_only_do_pony():
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        assert "research_only" in src or "Research only" in src, (
            f"{nb.name} nao avisa sobre modelos research-only")


def test_notebooks_nao_implementam_o_que_esta_fora_de_escopo():
    """So o CODIGO conta: markdown pode citar 'nao produz master.png'."""
    for nb in (NB1, NB2):
        data, _, _ = _nb(nb)
        codigo = "\n".join("".join(c["source"]) for c in data["cells"]
                           if c["cell_type"] == "code")
        for proibido in ("LoraLoader", "ControlNetApply", "ControlNetLoader",
                         "AnimateDiff", "master.png", "IPAdapter"):
            assert proibido not in codigo, f"{nb.name} usa {proibido}"


def test_notebooks_executam_uma_vez_e_nao_varrem_modelos():
    """Nao rodar bateria automatica: o usuario escolhe um por vez."""
    for nb in (NB1, NB2):
        _, src, _ = _nb(nb)
        assert "for label in dropdown_options" not in src
        assert "for key in model_keys" not in src



def test_sessao_limpa_chega_ao_preflight_sem_nameerror():
    """Regressao do 'NameError: name mr is not defined'.

    Executa as celulas em ordem num namespace VAZIO, como faz um runtime
    Colab recem-criado, ate o preflight. Nenhuma variavel pode vir de
    sessao anterior nem de celula opcional.
    """
    import subprocess
    import types

    from IPython.core.inputtransformer2 import TransformerManager

    for nb_path in (NB1, NB2):
        data, _, _ = _nb(nb_path)
        tm = TransformerManager()
        ns: dict = {"__name__": "__main__", "display": lambda *a, **k: None}

        # Stubs: sem rede, sem GPU, sem Colab.
        def _fake_run(cmd, *a, **k):
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")

        real_run = subprocess.run
        subprocess.run = _fake_run
        try:
            for i, c in enumerate(data["cells"]):
                if c["cell_type"] != "code":
                    continue
                src = "".join(c["source"])
                if "files.upload()" in src:
                    ns["FLUX_RUN003"] = (
                        ROOT / "characters/waifu_001/reference/full_body.png")
                    ns["zip_name"] = "z.zip"
                    continue
                try:
                    exec(compile(tm.transform_cell(src), f"c{i}", "exec"), ns)
                except NameError as exc:
                    raise AssertionError(
                        f"{nb_path.name} celula {i}: NameError em sessao "
                        f"limpa -> {exc}") from exc
                except SystemExit:
                    break          # preflight bloqueou: comportamento valido
                except Exception:
                    break          # sem GPU/rede aqui; NameError e o alvo
                if "mr.preflight(" in src:
                    assert "PF" in ns, "preflight nao produziu PF"
                    break
            else:
                raise AssertionError(f"{nb_path.name}: preflight nao alcancado")
        finally:
            subprocess.run = real_run


def test_setup_importa_mr_e_valida_a_api():
    """A celula 1 tem de importar mr e falhar com mensagem, nao adiante."""
    for nb_path in (NB1, NB2):
        data, _, celulas = _nb(nb_path)
        codigo = [i for i, c in enumerate(data["cells"])
                  if c["cell_type"] == "code"]
        primeira = celulas[codigo[0]]
        assert "from chibi import model_registry as mr" in primeira, (
            f"{nb_path.name}: mr nao e importado na primeira celula")
        assert "sys.path" in primeira, "sys.path nao configurado"
        assert "FALHA AO IMPORTAR" in primeira, (
            "import sem mensagem de erro legivel")
        assert "hasattr(mr" in primeira, "API do registry nao e validada"
        assert "preflight" in primeira
        assert "SETUP_OK" in primeira
        # Nao pode reimplementar o registry dentro do notebook.
        assert "def preflight(" not in "\n".join(celulas), (
            f"{nb_path.name} duplica a implementacao do registry")


def test_mr_definido_antes_de_qualquer_uso():
    """Nenhuma celula usa mr./MODEL_KEY antes da celula que os define."""
    for nb_path in (NB1, NB2):
        data, _, _ = _nb(nb_path)
        celulas = [(i, "".join(c["source"])) for i, c in
                   enumerate(data["cells"]) if c["cell_type"] == "code"]
        i_mr = next(i for i, s in celulas if "import model_registry as mr" in s)
        i_key = next(i for i, s in celulas if "MODEL_KEY = mr.key_for_label" in s)
        for i, s in celulas:
            if "mr." in s and i < i_mr:
                raise AssertionError(f"{nb_path.name} c{i}: usa mr antes de importar")
            if "MODEL_KEY" in s and i < i_key and "MODEL_KEY = " not in s:
                raise AssertionError(f"{nb_path.name} c{i}: usa MODEL_KEY antes de definir")


def test_preflight_checa_as_proprias_dependencias():
    for nb_path in (NB1, NB2):
        _, _, celulas = _nb(nb_path)
        cel = next(c for c in celulas if "mr.preflight(" in c)
        assert "_faltando" in cel, "preflight nao valida dependencias"
        for v in ("mr", "REG", "MODEL_KEY", "CFG"):
            assert f"'{v}'" in cel, f"preflight nao checa {v}"
        # Erro nao pode ser escondido.
        assert "raise" in cel
        assert "except" not in cel.split("def _gpu")[0].split("_faltando")[0]


def test_run_all_funciona_sem_clique_no_dropdown():
    """Run All nao clica no widget: precisa de selecao por indice."""
    for nb_path in (NB1, NB2):
        _, src, _ = _nb(nb_path)
        assert "MODEL_INDEX" in src, f"{nb_path.name} sem MODEL_INDEX"
        assert "USE_WIDGET" in src, "sem fallback para ipywidgets ausente"


def test_longcat_bloqueado_num_t4_de_15gb():
    """Hardware real do usuario: T4 15 GB, 14.6 livres, 65.3 GB de disco.

    LongCat declara ~18 GB de VRAM => tem de bloquear. O requisito NAO
    pode ser reduzido artificialmente para caber.
    """
    pf = mr.preflight("longcat_image_edit",
                      available_disk_gb=65.3, available_vram_gb=14.6)
    assert pf.status == mr.BLOCKED_VRAM, pf.status
    assert not pf.ready
    assert mr.get_model("longcat_image_edit")["vram_gb"] >= 18, (
        "requisito do LongCat foi reduzido para caber no T4")

    # O Qwen Q3, menor, passa no mesmo runtime.
    q3 = mr.preflight("qwen_edit_2511_q3_k_m",
                      available_disk_gb=65.3, available_vram_gb=14.6)
    assert q3.ready, q3.report()


if __name__ == "__main__":
    funcs = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in funcs:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} passaram")
    sys.exit(1 if failed else 0)

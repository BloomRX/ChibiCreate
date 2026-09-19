"""Testes da fundacao (Fase 1).

Rodar:  ./.venv/bin/python -m pytest tests/ -q
        (ou ./.venv/bin/python tests/test_foundation.py para modo standalone)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import config, paths, status as status_mod  # noqa: E402
from chibi.hashing import sha256_bytes, sha256_file, sha256_json  # noqa: E402
from chibi.recipe import Recipe, RecipeError, recipe_path_for  # noqa: E402


# --- config -----------------------------------------------------------------

def test_configs_load():
    assert config.project()["project"]["name"] == "ChibiCreate"
    assert "models" in config.models_lock()
    assert "gates" in config.quality_gates()


def test_dotted_get():
    assert config.get("resolution.master.width") == 1024
    assert config.get("nao.existe", "fallback") == "fallback"


def test_style_lora_disabled_in_mvp():
    """spec §16: LoRA nao pode ser dependencia obrigatoria no MVP."""
    assert config.get("style.lora.enabled") is False


def test_gameplay_resolution_not_frozen():
    """spec §15: nao congelar resolucao sem dados."""
    assert config.get("resolution.gameplay_output.display_height") is None


def test_legibility_sizes():
    assert config.get("resolution.legibility_test.sizes") == [64, 96, 128]


def test_animation_defaults():
    assert config.get("animation.defaults.idle.frames") == 4
    assert config.get("animation.defaults.walk.frames") == 6


def test_environments_load():
    assert config.environment("local")["capabilities"]["gpu_inference"] is False
    assert config.environment("cloud")["capabilities"]["gpu_inference"] is True


# --- licenciamento ----------------------------------------------------------

def test_no_model_is_executable_yet():
    """Licenca e pesos sao niveis independentes (models.lock schema v2).

    Desde 2026-09-08 duas licencas foram verificadas em fonte primaria, entao
    'commercially_usable' pode ser True. O que continua obrigatoriamente falso
    e a disponibilidade dos PESOS: nada foi baixado, logo nenhum modelo e
    executavel. O agente nao baixa checkpoints.
    """
    for key in config.models_lock()["models"]:
        ok, why = config.weights_available(key)
        assert ok is False, f"{key}: pesos nao deveriam estar disponiveis ({why})"
        ok, why = config.executable(key)
        assert ok is False, f"{key}: nao deveria ser executavel ({why})"


def test_license_verification_requires_evidence():
    """So passa por 'commercially_usable' quem tem fonte, revisao e data."""
    for key in config.models_lock()["models"]:
        ok, _ = config.commercially_usable(key)
        if not ok:
            continue
        entry = config.model(key)
        assert entry["license"]["verified"] is True
        assert entry["license"]["verified_on"]
        assert entry["license"]["source_url"].startswith("http")
        assert entry["revision"], f"{key}: licenca verificada exige revisao fixada"


def test_rejected_models_are_refused():
    for key in ("bria_rmbg_2_0", "flux_dev_family", "noobai_xl", "seedvr2"):
        ok, why = config.commercially_usable(key)
        assert ok is False
        assert "REJEITADO" in why


def test_flagged_model_is_refused():
    ok, why = config.commercially_usable("illustrious_xl")
    assert ok is False
    assert "SINALIZADO" in why


def test_unknown_model_is_refused():
    ok, _ = config.commercially_usable("modelo_inventado")
    assert ok is False


# --- hashing ----------------------------------------------------------------

def test_sha256_file_matches_bytes():
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(b"chibi")
        tmp = Path(handle.name)
    try:
        assert sha256_file(tmp) == sha256_bytes(b"chibi")
    finally:
        tmp.unlink()


def test_sha256_json_is_key_order_stable():
    assert sha256_json({"a": 1, "b": 2}) == sha256_json({"b": 2, "a": 1})


# --- status -----------------------------------------------------------------

def test_state_order():
    assert status_mod.STATES[0] == "SOURCE"
    assert status_mod.STATES[-1] == "GODOT_VALIDATED"


def test_transition_rules():
    assert status_mod.can_transition("SOURCE", "REFERENCE_READY")
    assert not status_mod.can_transition("SOURCE", "CHIBI_APPROVED")
    assert status_mod.can_transition("POSES_READY", "SOURCE")  # rework permitido


def test_agent_cannot_approve_chibi():
    with tempfile.TemporaryDirectory() as tmpdir:
        sp = Path(tmpdir) / "STATUS.md"
        status_mod.init_file(sp, "t")
        for state in ("REFERENCE_READY", "CHIBI_CANDIDATES"):
            status_mod.transition(sp, state, by="agent")
        try:
            status_mod.transition(sp, "CHIBI_APPROVED", by="agent")
        except status_mod.StatusError as exc:
            assert "humana" in str(exc)
        else:
            raise AssertionError("agente nao deveria poder aprovar")
        status_mod.transition(sp, "CHIBI_APPROVED", by="human")
        assert status_mod.read(sp) == "CHIBI_APPROVED"


# --- recipes ----------------------------------------------------------------

def test_recipe_path_naming():
    assert recipe_path_for(Path("a/master.png")).name == "master.recipe.json"


def test_recipe_validate_catches_missing_fields():
    r = Recipe(artifact="x/master.png", flow="02_chibi_master")
    problems = r.validate(config.quality_gates())
    assert any("artifact_sha256" in p for p in problems)
    assert any("base_model" in p for p in problems)


def test_recipe_agent_cannot_approve():
    r = Recipe(artifact="x.png", flow="02")
    for actor in ("agent", "AgentAI", "ai", "bot", ""):
        try:
            r.approve(actor)
        except RecipeError:
            pass
        else:
            raise AssertionError(f"'{actor}' nao deveria poder aprovar")
    r.approve("kaio", selected_from_batch=3)
    assert r.approval_status == "approved"
    assert r.approved_by == "kaio"


def test_recipe_roundtrip_and_hash():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        art = tmp / "master.png"
        art.write_bytes(b"fake-png")

        r = Recipe(artifact="master.png", flow="02_chibi_master", seed=42)
        r.stamp_artifact(art)
        r.add_input(art, role="full_body")
        out = r.save(recipe_path_for(art))

        data = json.loads(out.read_text())
        assert data["seed"] == 42
        assert data["artifact_sha256"] == sha256_file(art)
        assert data["input_hashes"] == [sha256_file(art)]
        assert "recipe_self_sha256" in data
        assert data["schema_version"] == 1

        loaded = Recipe.load(out)
        assert loaded.seed == 42
        assert loaded.artifact_sha256 == r.artifact_sha256


def test_recipe_rejects_missing_input():
    r = Recipe(artifact="x.png", flow="02")
    try:
        r.add_input(Path("/nao/existe.png"), role="face")
    except RecipeError:
        pass
    else:
        raise AssertionError("deveria recusar input inexistente")


# --- paths ------------------------------------------------------------------

def test_character_paths():
    cp = paths.CharacterPaths("waifu_test")
    assert cp.master.name == "master.png"
    assert cp.master_recipe.name == "master.recipe.json"
    # work/ e temporario e deve ficar FORA de characters/
    assert paths.CHARACTERS_DIR not in cp.work.parents
    assert cp.work.is_relative_to(paths.WORK_DIR)


def test_repo_structure_exists():
    for d in (paths.CONFIG_DIR, paths.STYLES_DIR, paths.WORKFLOWS_DIR,
              paths.CHARACTERS_DIR, paths.POSE_BANK_DIR, paths.DOCS_DIR):
        assert d.is_dir(), f"faltando: {d}"


def test_gitignore_protects_work_and_models():
    text = (paths.ROOT / ".gitignore").read_text()
    for pattern in ("work/", "*.safetensors", "candidates/", ".env"):
        assert pattern in text, f"faltando no .gitignore: {pattern}"


# --- stubs de fases futuras -------------------------------------------------

def test_future_modules_fail_loudly():
    """Modulos de fases futuras precisam falhar alto, nao silenciosamente.

    ComfyClient saiu desta lista na FASE 3A: agora e implementado de verdade
    (ver tests/test_comfy.py). O que ele ainda deve fazer e recusar um
    ambiente sem backend configurado — coberto por
    test_local_environment_refuses_by_default.
    """
    from chibi import spritesheet, godot_export, sheet

    for fn in (spritesheet.pack, godot_export.write_spriteframes,
               sheet.build_contact_sheet):
        try:
            fn()
        except NotImplementedError:
            pass
        else:
            raise AssertionError(f"{fn} deveria levantar NotImplementedError")


# --- runner standalone ------------------------------------------------------


# ---------------------------------------------------------------------------
# STYLE SPECIFICATION v0 — estrutura e separacao STYLE/IDENTITY
# ---------------------------------------------------------------------------


def test_style_references_structure():
    """styles/chibi/references/{chibi,splash}/ e a estrutura acordada."""
    base = ROOT / "styles" / "chibi" / "references"
    assert base.is_dir(), "styles/chibi/references/ ausente"
    for sub in ("chibi", "splash"):
        assert (base / sub).is_dir(), f"references/{sub}/ ausente"
    # A pasta antiga nao pode ressurgir em paralelo.
    assert not (ROOT / "styles" / "chibi" / "reference_sheets").exists(), \
        "reference_sheets/ voltou — a estrutura acordada e references/"


def test_no_character_art_inside_styles():
    """Arte das NOSSAS personagens nunca entra em styles/.

    Regra do usuario: personagens vivem so em characters/<id>/source/ e
    characters/<id>/reference/. Misturar os eixos contamina a avaliacao —
    deixa de ficar claro se um resultado veio da identidade ou do exemplo
    de estilo.
    """
    style_dir = ROOT / "styles"
    imgs = [p for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp")
            for p in style_dir.rglob(ext)]
    char_ids = {d.name for d in (ROOT / "characters").iterdir() if d.is_dir()}
    for img in imgs:
        for cid in char_ids:
            assert cid not in img.name, \
                f"arte de personagem em styles/: {img.relative_to(ROOT)}"


def test_style_yaml_v0_values_have_a_declared_source():
    """Todo valor de estilo precisa de FONTE declarada.

    Duas fontes sao aceitaveis:
      - o agente leu os pixels            (references.analyzed = true)
      - revisao visual externa declarada  (source.analyzed_by_external_visual_review)

    Sem nenhuma das duas, os campos observacionais tem de ficar null. O que
    o teste impede nao e "valor preenchido", e "valor sem procedencia".
    """
    import yaml

    data = yaml.safe_load((ROOT / "styles" / "chibi" / "style.yaml").read_text())
    style = data["style"]
    assert style["id"] == "chibi_v0"
    assert style["status"] == "experimental"

    src = style["source"]
    refs = style["references"]
    agent_read = refs.get("analyzed", False)
    external = src.get("analyzed_by_external_visual_review", False)

    # Honestidade: se o agente nao leu os pixels, nao pode alegar que leu.
    if not agent_read:
        assert src.get("agent_pixel_access") is False, (
            "references.analyzed=false mas agent_pixel_access nao e false"
        )

    if not (agent_read or external):
        for section in ("proportions", "face", "rendering"):
            for key, value in style[section].items():
                assert value is None, (
                    f"style.{section}.{key} = {value!r} sem fonte. "
                    "Preencher exige leitura de pixels ou revisao externa declarada."
                )

    if external:
        # Observacao externa e provisoria e nao pode se disfarcar de medida.
        assert src.get("status") == "provisional_observation", src
        assert src.get("agent_verified") is False, src
        ratio = style["proportions"]["head_to_body_ratio"]
        if isinstance(ratio, dict):
            assert ratio.get("exact") is False, "proporcao aproximada marcada como exata"
            assert "confidence" in ratio, "proporcao sem grau de confianca"


def test_style_yaml_has_no_invented_generation_parameters():
    """Observacao de estilo NAO autoriza fixar parametro de geracao.

    Sampler, cfg, steps, prompt e LoRA continuam vazios: nada disso foi
    observado nas referencias, e inventar aqui contaminaria a avaliacao de
    modelos com um chute.
    """
    import yaml

    data = yaml.safe_load((ROOT / "styles" / "chibi" / "style.yaml").read_text())
    for key, value in data["sampling"].items():
        assert value is None, f"sampling.{key} = {value!r} nao foi observado"
    for key, value in data["prompt"].items():
        assert value == "", f"prompt.{key} preenchido sem evidencia"
    assert data["lora"]["enabled"] is False, "Style LoRA precisa continuar desabilitado"


def test_style_vs_identity_documented():
    """A separacao dos dois eixos precisa estar escrita."""
    doc = (ROOT / "docs" / "style-vs-identity.md").read_text(encoding="utf-8")
    for term in ("STYLE", "IDENTITY", "DESIGN PRESERVATION",
                 "global", "por personagem"):
        assert term in doc, f"'{term}' ausente de style-vs-identity.md"
    # A distincao design != identidade precisa estar escrita, nao subentendida.
    assert "Simplificar é remover detalhe" in doc
    # E a proveniencia externa dos valores tem de estar declarada.
    assert "externa" in doc, "proveniencia das observacoes nao declarada"


def test_eval_sheet_separates_style_and_identity():
    """A ficha precisa de STYLE e IDENTITY separados, e OVERALL humano."""
    sheet = (ROOT / "docs" / "model-eval" / "ficha-avaliacao.md").read_text(
        encoding="utf-8")
    # Tres eixos distintos: um modelo pode preservar a personagem e perder o
    # design dela. Sem o terceiro eixo isso passa despercebido.
    for axis in ("STYLE SCORE", "IDENTITY SCORE", "DESIGN PRESERVATION SCORE"):
        assert axis in sheet, f"eixo ausente da ficha: {axis}"
    assert "[HUMAN REVIEW REQUIRED]" in sheet
    # OVERALL nao pode ser apresentado como calculo automatico.
    assert "Não é média aritmética" in sheet


def test_source_art_of_all_characters_is_present():
    """Toda personagem registrada tem arte-fonte (ponteiro LFS conta)."""
    for cdir in sorted((ROOT / "characters").iterdir()):
        if not cdir.is_dir():
            continue
        src = cdir / "source"
        assert src.is_dir(), f"{cdir.name}: source/ ausente"
        arts = [p for p in src.iterdir() if p.suffix.lower() in
                (".png", ".jpg", ".jpeg", ".webp")]
        assert arts, f"{cdir.name}: nenhuma arte-fonte em source/"



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

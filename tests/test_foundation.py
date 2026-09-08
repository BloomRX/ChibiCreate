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

def test_no_model_is_commercially_usable_yet():
    """Nenhum modelo foi verificado. Todos devem ser recusados."""
    for key in config.models_lock()["models"]:
        ok, why = config.commercially_usable(key)
        assert ok is False, f"{key} nao deveria estar liberado ainda ({why})"


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
    from chibi.comfy_client import ComfyClient, ComfyClientNotConfigured
    from chibi import spritesheet, godot_export, sheet

    try:
        ComfyClient()
    except ComfyClientNotConfigured:
        pass
    else:
        raise AssertionError("ComfyClient deveria recusar instanciacao")

    for fn in (spritesheet.pack, godot_export.write_spriteframes,
               sheet.build_contact_sheet):
        try:
            fn()
        except NotImplementedError:
            pass
        else:
            raise AssertionError(f"{fn} deveria levantar NotImplementedError")


# --- runner standalone ------------------------------------------------------

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

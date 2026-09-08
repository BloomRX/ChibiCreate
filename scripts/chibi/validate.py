"""Quality gates tecnicos (spec §24).

Nenhum gate aqui julga qualidade artistica. Eles verificam propriedades
mensuraveis: formato, dimensao, alpha, hash, presenca de recipe.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import config, paths
from .recipe import Recipe, recipe_path_for


@dataclass
class GateResult:
    gate: str
    passed: bool
    severity: str
    message: str
    subject: str | None = None

    @property
    def blocking(self) -> bool:
        return not self.passed and self.severity == "error"

    def __str__(self) -> str:
        icon = "PASS" if self.passed else ("FAIL" if self.blocking else "WARN")
        subj = f" [{self.subject}]" if self.subject else ""
        return f"  {icon:<4} {self.gate}{subj}: {self.message}"


def _gate_cfg(name: str) -> dict[str, Any]:
    return config.quality_gates().get("gates", {}).get(name, {})


def _enabled(name: str) -> bool:
    return bool(_gate_cfg(name).get("enabled", False))


def _severity(name: str) -> str:
    return _gate_cfg(name).get("severity", "error")


def _params(name: str) -> dict[str, Any]:
    return _gate_cfg(name).get("params", {}) or {}


def _skip(name: str, why: str) -> GateResult:
    return GateResult(name, True, "warn", f"pulado ({why})")


# --- helpers de imagem ------------------------------------------------------

def _load_image(path: Path):
    try:
        from PIL import Image
    except ImportError:
        return None, "Pillow nao instalado"
    try:
        return Image.open(path), None
    except Exception as exc:  # noqa: BLE001
        return None, f"nao foi possivel abrir: {exc}"


# --- gates ------------------------------------------------------------------

def gate_input_valid(path: Path) -> GateResult:
    name = "INPUT_VALID"
    if not _enabled(name):
        return _skip(name, "desabilitado")
    p = _params(name)
    subject = path.name

    if not path.is_file():
        return GateResult(name, False, _severity(name), "arquivo nao existe", subject)

    ext = path.suffix.lower().lstrip(".")
    allowed = [str(f).lower() for f in p.get("allowed_formats", [])]
    if allowed and ext not in allowed:
        return GateResult(
            name, False, _severity(name),
            f"formato '{ext}' nao permitido (aceitos: {', '.join(allowed)})", subject,
        )

    img, err = _load_image(path)
    if img is None:
        return GateResult(name, False, _severity(name), err or "erro", subject)

    w, h = img.size
    if w < p.get("min_width", 0) or h < p.get("min_height", 0):
        return GateResult(
            name, False, _severity(name),
            f"dimensao {w}x{h} abaixo do minimo "
            f"{p.get('min_width')}x{p.get('min_height')}", subject,
        )
    if w * h > p.get("max_pixels", float("inf")):
        return GateResult(
            name, False, _severity(name),
            f"imagem excede max_pixels ({w * h})", subject,
        )
    return GateResult(name, True, _severity(name), f"ok ({w}x{h}, {ext})", subject)


def gate_alpha_valid(path: Path) -> GateResult:
    name = "ALPHA_VALID"
    if not _enabled(name):
        return _skip(name, "desabilitado")
    p = _params(name)
    subject = path.name

    img, err = _load_image(path)
    if img is None:
        return GateResult(name, False, _severity(name), err or "erro", subject)

    if img.mode != "RGBA":
        if p.get("require_alpha", True):
            return GateResult(
                name, False, _severity(name),
                f"sem canal alpha (mode={img.mode})", subject,
            )
        return GateResult(name, True, _severity(name), "alpha nao exigido", subject)

    try:
        import numpy as np
    except ImportError:
        return _skip(name, "numpy nao instalado")

    alpha = np.array(img.getchannel("A"))
    total = alpha.size
    semi = int(((alpha > 0) & (alpha < 255)).sum())
    ratio = semi / total if total else 0.0

    max_ratio = p.get("max_semitransparent_ratio", 1.0)
    if ratio > max_ratio:
        return GateResult(
            name, False, _severity(name),
            f"alpha parcial em {ratio:.1%} dos pixels (max {max_ratio:.0%}) "
            "— possivel halo", subject,
        )

    if p.get("forbid_edge_contact", False):
        edges = [alpha[0, :], alpha[-1, :], alpha[:, 0], alpha[:, -1]]
        if any(int(e.max()) == 255 for e in edges):
            return GateResult(
                name, False, _severity(name),
                "pixel opaco toca a borda do canvas (personagem cortada?)", subject,
            )

    return GateResult(
        name, True, _severity(name), f"ok (alpha parcial {ratio:.1%})", subject
    )


def gate_canvas_valid(path: Path, expected: tuple[int, int]) -> GateResult:
    name = "CANVAS_VALID"
    if not _enabled(name):
        return _skip(name, "desabilitado")
    subject = path.name
    tol = _params(name).get("tolerance_px", 0)

    img, err = _load_image(path)
    if img is None:
        return GateResult(name, False, _severity(name), err or "erro", subject)

    w, h = img.size
    ew, eh = expected
    if abs(w - ew) > tol or abs(h - eh) > tol:
        return GateResult(
            name, False, _severity(name),
            f"canvas {w}x{h}, esperado {ew}x{eh} (tol {tol}px)", subject,
        )
    return GateResult(name, True, _severity(name), f"ok ({w}x{h})", subject)


def gate_asset_hashed(recipe: Recipe) -> GateResult:
    name = "ASSET_HASHED"
    if not _enabled(name):
        return _skip(name, "desabilitado")
    if not recipe.artifact_sha256:
        return GateResult(name, False, _severity(name), "artifact_sha256 ausente",
                          recipe.artifact)
    return GateResult(name, True, _severity(name), "ok", recipe.artifact)


def gate_recipe_present(artifact: Path) -> GateResult:
    name = "RECIPE_PRESENT"
    if not _enabled(name):
        return _skip(name, "desabilitado")
    subject = artifact.name
    rpath = recipe_path_for(artifact)
    if not rpath.is_file():
        return GateResult(name, False, _severity(name),
                          f"recipe ausente: {rpath.name}", subject)
    try:
        recipe = Recipe.load(rpath)
    except Exception as exc:  # noqa: BLE001
        return GateResult(name, False, _severity(name),
                          f"recipe ilegivel: {exc}", subject)
    problems = recipe.validate(config.quality_gates())
    if problems:
        return GateResult(name, False, _severity(name),
                          "; ".join(problems), subject)
    return GateResult(name, True, _severity(name), "ok", subject)


def gate_model_licensing() -> list[GateResult]:
    """Nao e um gate de arquivo: verifica se algum modelo tratado como
    dependencia comercial esta sem licenca documentada (spec §18)."""
    name = "MODEL_LICENSE"
    results: list[GateResult] = []
    lock = config.models_lock()
    for key in lock.get("models", {}):
        ok, why = config.commercially_usable(key)
        results.append(
            GateResult(
                name, ok, "warn",
                "liberado para uso comercial" if ok
                else f"NAO liberado para producao comercial — {why}",
                key,
            )
        )
    return results


# --- orquestracao -----------------------------------------------------------

def validate_character(character_id: str) -> list[GateResult]:
    """Valida o que EXISTE hoje da personagem. Ausencia de etapas futuras
    nao e erro — a personagem simplesmente ainda nao chegou la."""
    cp = paths.CharacterPaths(character_id)
    results: list[GateResult] = []

    if not cp.exists():
        return [GateResult("CHARACTER_EXISTS", False, "error",
                           f"character.yaml nao encontrado em {cp.root}")]
    results.append(GateResult("CHARACTER_EXISTS", True, "error", "ok", character_id))

    # character.yaml legivel e com campos minimos
    import yaml
    try:
        meta = yaml.safe_load(cp.character_yaml.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        results.append(GateResult("CHARACTER_YAML", False, "error",
                                  f"ilegivel: {exc}", character_id))
        return results

    missing = [k for k in ("id", "display_name", "difficulty") if k not in meta]
    results.append(
        GateResult("CHARACTER_YAML", not missing, "error",
                   "ok" if not missing else f"campos ausentes: {', '.join(missing)}",
                   character_id)
    )

    # source art
    sources = _images_in(cp.source)
    if not sources:
        results.append(GateResult("INPUT_VALID", False, "error",
                                  "nenhuma arte em source/", character_id))
    for src in sources:
        results.append(gate_input_valid(src))

    # chibi master, se ja existir
    if cp.master.is_file():
        expected = (
            int(config.get("resolution.master.width", 1024)),
            int(config.get("resolution.master.height", 1024)),
        )
        results.append(gate_canvas_valid(cp.master, expected))
        results.append(gate_alpha_valid(cp.master))
        results.append(gate_recipe_present(cp.master))

    return results


def _images_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(p for p in directory.iterdir()
                  if p.is_file() and p.suffix.lower() in exts)


def summarize(results: Iterable[GateResult]) -> tuple[int, int, int]:
    results = list(results)
    passed = sum(1 for r in results if r.passed)
    warns = sum(1 for r in results if not r.passed and not r.blocking)
    errors = sum(1 for r in results if r.blocking)
    return passed, warns, errors

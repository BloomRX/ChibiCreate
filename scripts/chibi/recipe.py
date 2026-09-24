"""Sistema de recipes (spec §7).

Uma recipe descreve como um artefato APROVADO foi produzido, com detalhe
suficiente para reconstrucao APROXIMADA do processo.

Nao prometemos determinismo perfeito: versoes de biblioteca, kernels de GPU e
nao-determinismo de atencao podem variar o resultado. A recipe registra o que
foi usado, nao garante bit-exatidao.
"""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .hashing import sha256_file, sha256_json

SCHEMA_VERSION = 1

REQUIRED_FIELDS = (
    "artifact",
    "artifact_sha256",
    "flow",
    "workflow",
    "base_model",
    "input_images",
    "seed",
    "approval_status",
)

APPROVAL_STATES = ("pending", "approved", "rejected")


class RecipeError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def environment_block() -> dict[str, Any]:
    """Snapshot do ambiente. Deliberadamente modesto — o que da para afirmar."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "chibi_version": _chibi_version(),
        "comfyui_version": None,   # preenchido pelo comfy_client quando houver
        "gpu": None,
    }


def _chibi_version() -> str:
    from . import __version__
    return __version__


@dataclass
class Recipe:
    """Recipe de um artefato. Campos None = desconhecido, nao 'vazio'."""

    artifact: str
    flow: str
    artifact_sha256: str | None = None

    workflow: str | None = None
    workflow_sha256: str | None = None

    base_model: str | None = None
    model_revision: str | None = None
    model_sha256: str | None = None
    model_license: str | None = None

    loras: list[dict[str, Any]] = field(default_factory=list)

    input_images: list[dict[str, Any]] = field(default_factory=list)

    seed: int | None = None
    sampler: str | None = None
    steps: int | None = None
    cfg: float | None = None
    width: int | None = None
    height: int | None = None

    prompt: str | None = None
    negative_prompt: str | None = None

    environment: dict[str, Any] = field(default_factory=environment_block)
    timestamp: str = field(default_factory=_now)

    approval_status: str = "pending"
    approved_by: str | None = None
    approved_at: str | None = None
    selected_from_batch: int | None = None

    schema_version: int = SCHEMA_VERSION
    notes: str | None = None

    # --- derivados ---------------------------------------------------------

    @property
    def input_hashes(self) -> list[str]:
        return [i.get("sha256") for i in self.input_images if i.get("sha256")]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["input_hashes"] = self.input_hashes
        return data

    # --- ciclo de vida -----------------------------------------------------

    def stamp_artifact(self, artifact_path: Path) -> None:
        """Calcula o hash do artefato final."""
        if not artifact_path.is_file():
            raise RecipeError(f"Artefato inexistente: {artifact_path}")
        self.artifact_sha256 = sha256_file(artifact_path)

    def add_input(self, path: Path, role: str) -> None:
        if not path.is_file():
            raise RecipeError(f"Input inexistente: {path}")
        self.input_images.append(
            {
                "role": role,
                "path": _rel(path),
                "sha256": sha256_file(path),
            }
        )

    def approve(self, by: str, selected_from_batch: int | None = None) -> None:
        """Aprovacao e SEMPRE humana. `by` deve identificar a pessoa."""
        if not by or by.lower() in {"agent", "agentai", "ai", "bot"}:
            raise RecipeError(
                "Aprovacao artistica exige um humano identificado (spec §21)."
            )
        self.approval_status = "approved"
        self.approved_by = by
        self.approved_at = _now()
        self.selected_from_batch = selected_from_batch

    def validate(self, gates: dict | None = None) -> list[str]:
        """Retorna lista de problemas. Vazia = ok."""
        required = REQUIRED_FIELDS
        if gates:
            params = gates.get("gates", {}).get("RECIPE_PRESENT", {}).get("params", {})
            required = tuple(params.get("required_fields", REQUIRED_FIELDS))

        problems: list[str] = []
        data = self.to_dict()
        for fieldname in required:
            value = data.get(fieldname)
            if value is None or value == [] or value == "":
                problems.append(f"campo obrigatorio ausente/vazio: {fieldname}")

        if self.approval_status not in APPROVAL_STATES:
            problems.append(f"approval_status invalido: {self.approval_status}")
        if self.approval_status == "approved" and not self.approved_by:
            problems.append("approved sem approved_by")
        return problems

    # --- io ----------------------------------------------------------------

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        data["recipe_self_sha256"] = sha256_json(data)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "Recipe":
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.pop("recipe_self_sha256", None)
        raw.pop("input_hashes", None)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(paths.ROOT))
    except ValueError:
        return str(path)


def recipe_path_for(artifact: Path) -> Path:
    """master.png -> master.recipe.json"""
    return artifact.with_name(artifact.stem + ".recipe.json")

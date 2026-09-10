"""Resolucao de caminhos canonicos do repositorio.

Regra de ouro: nada fora daqui deve montar caminho com string concatenada.
CANONICAL (versionado) vs TEMPORARY (work/, gitignored) e a distincao central.
"""

from __future__ import annotations

from pathlib import Path


def repo_root(start: Path | None = None) -> Path:
    """Sobe a arvore ate achar a raiz do repo (marcada por config/project.yaml)."""
    current = (start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "project.yaml").is_file():
            return candidate
    raise FileNotFoundError(
        "Raiz do repositorio nao encontrada (procurando config/project.yaml)."
    )


ROOT = repo_root()

CONFIG_DIR = ROOT / "config"
ENVIRONMENTS_DIR = CONFIG_DIR / "environments"
PROJECT_CONFIG = CONFIG_DIR / "project.yaml"
MODELS_LOCK = CONFIG_DIR / "models.lock.yaml"
QUALITY_GATES = CONFIG_DIR / "quality_gates.yaml"

CHARACTERS_DIR = ROOT / "characters"
STYLES_DIR = ROOT / "styles"
WORKFLOWS_DIR = ROOT / "workflows"
WORK_DIR = ROOT / "work"
DOCS_DIR = ROOT / "docs"

CHIBI_STYLE_DIR = STYLES_DIR / "chibi"
POSE_BANK_DIR = CHIBI_STYLE_DIR / "pose_bank"


class CharacterPaths:
    """Caminhos de uma personagem. CANONICAL salvo onde indicado."""

    def __init__(self, character_id: str) -> None:
        self.id = character_id
        self.root = CHARACTERS_DIR / character_id

    # --- canonical ---------------------------------------------------------
    @property
    def character_yaml(self) -> Path:
        return self.root / "character.yaml"

    @property
    def status_md(self) -> Path:
        return self.root / "STATUS.md"

    @property
    def source(self) -> Path:
        """Arte original. IMUTAVEL — nunca escrever aqui apos a criacao."""
        return self.root / "source"

    @property
    def reference(self) -> Path:
        return self.root / "reference"

    @property
    def chibi(self) -> Path:
        return self.root / "chibi"

    @property
    def master(self) -> Path:
        return self.chibi / "master.png"

    @property
    def master_recipe(self) -> Path:
        return self.chibi / "master.recipe.json"

    @property
    def poses(self) -> Path:
        return self.root / "poses"

    @property
    def animation(self) -> Path:
        return self.root / "animation"

    def anim_frames(self, anim: str) -> Path:
        return self.animation / anim / "frames"

    @property
    def rig(self) -> Path:
        return self.root / "rig"

    @property
    def export(self) -> Path:
        return self.root / "export"

    # --- temporary (gitignored) -------------------------------------------
    @property
    def work(self) -> Path:
        return WORK_DIR / self.id

    @property
    def candidates(self) -> Path:
        return self.work / "candidates"

    def exists(self) -> bool:
        return self.character_yaml.is_file()

    def canonical_dirs(self) -> list[Path]:
        return [
            self.source,
            self.reference,
            self.chibi,
            self.poses,
            self.animation,
            self.rig,
            self.export,
        ]

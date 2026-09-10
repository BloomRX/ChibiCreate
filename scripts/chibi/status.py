"""Maquina de estados da personagem (spec §25).

Cada transicao e explicita e registrada em STATUS.md com timestamp e ator.
Transicoes que exigem julgamento artistico so podem ser feitas por humano.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

STATES: list[str] = [
    "SOURCE",
    "REFERENCE_READY",
    "CHIBI_CANDIDATES",
    "CHIBI_APPROVED",
    "POSES_READY",
    "RIG_READY",
    "ANIMATION_READY",
    "EXPORT_READY",
    "GODOT_VALIDATED",
]

#: Estados cuja entrada exige aprovacao humana explicita (spec §21).
HUMAN_GATED: set[str] = {"CHIBI_APPROVED"}

_HEADER = "# STATUS"
_STATE_RE = re.compile(r"^-\s+state:\s*(\w+)\s*$", re.MULTILINE)


class StatusError(RuntimeError):
    pass


def index_of(state: str) -> int:
    try:
        return STATES.index(state)
    except ValueError as exc:
        raise StatusError(f"Estado desconhecido: {state}") from exc


def can_transition(current: str, target: str) -> bool:
    """Permite avancar exatamente um passo, ou repetir o estado atual.
    Retroceder e permitido (rework acontece)."""
    ci, ti = index_of(current), index_of(target)
    return ti <= ci + 1


def read(status_path: Path) -> str:
    if not status_path.is_file():
        return "SOURCE"
    matches = _STATE_RE.findall(status_path.read_text(encoding="utf-8"))
    return matches[-1] if matches else "SOURCE"


def init_file(status_path: Path, character_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        f"{_HEADER} — {character_id}\n\n"
        "Estados possiveis (ordem):\n"
        + "".join(f"{i}. {s}\n" for i, s in enumerate(STATES))
        + "\nTransicoes marcadas com `by: human` exigem aprovacao artistica humana.\n"
        "\n## Historico\n\n"
        f"- state: SOURCE\n  at: {now}\n  by: agent\n  note: personagem criada\n",
        encoding="utf-8",
    )


def transition(
    status_path: Path,
    target: str,
    *,
    by: str = "agent",
    note: str = "",
    force: bool = False,
) -> str:
    current = read(status_path)
    if not force and not can_transition(current, target):
        raise StatusError(
            f"Transicao invalida {current} -> {target}. "
            "Avance um estado por vez (ou use force explicitamente)."
        )
    if target in HUMAN_GATED and by != "human":
        raise StatusError(
            f"Estado '{target}' exige aprovacao humana. "
            "O agente nao pode aprovar arte (spec §21)."
        )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(status_path, "a", encoding="utf-8") as handle:
        handle.write(f"- state: {target}\n  at: {now}\n  by: {by}\n")
        if note:
            handle.write(f"  note: {note}\n")
    return target

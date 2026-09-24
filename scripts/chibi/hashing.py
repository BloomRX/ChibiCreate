"""Hashing de artefatos.

Todo asset canonico precisa de sha256 (gate ASSET_HASHED).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    """sha256 de um arquivo, em streaming."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    """Hash estavel de uma estrutura (chaves ordenadas, sem espaco supérfluo)."""
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(payload)


def hash_entry(path: Path, root: Path | None = None, role: str | None = None) -> dict:
    """Entrada padrao {role?, path, sha256, bytes} usada em recipes."""
    entry: dict[str, Any] = {
        "path": str(path.relative_to(root)) if root else str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }
    if role:
        entry = {"role": role, **entry}
    return entry

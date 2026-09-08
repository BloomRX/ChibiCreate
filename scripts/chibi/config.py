"""Carregamento e validacao leve das configuracoes do projeto."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import paths


class ConfigError(RuntimeError):
    pass


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"Config ausente: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ConfigError(f"Config invalida (esperado mapping): {path}")
    return data


@lru_cache(maxsize=None)
def project() -> dict:
    return _load_yaml(paths.PROJECT_CONFIG)


@lru_cache(maxsize=None)
def models_lock() -> dict:
    return _load_yaml(paths.MODELS_LOCK)


@lru_cache(maxsize=None)
def quality_gates() -> dict:
    return _load_yaml(paths.QUALITY_GATES)


@lru_cache(maxsize=None)
def environment(name: str | None = None) -> dict:
    name = name or project().get("runtime", {}).get("default_environment", "local")
    data = _load_yaml(paths.ENVIRONMENTS_DIR / f"{name}.yaml")
    # Resolve credenciais/URLs a partir de env vars, nunca do arquivo.
    comfy = data.get("comfyui", {})
    if url_env := comfy.get("base_url_env"):
        comfy["base_url"] = os.environ.get(url_env) or comfy.get("base_url")
    if token_env := comfy.get("token_env"):
        comfy["token"] = os.environ.get(token_env)
    return data


def get(dotted: str, default: Any = None) -> Any:
    """Acesso por caminho pontuado: get('resolution.master.width')."""
    node: Any = project()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


# --- consultas sobre models.lock -------------------------------------------

def model(key: str) -> dict:
    entry = models_lock().get("models", {}).get(key)
    if entry is None:
        raise ConfigError(f"Modelo '{key}' nao registrado em models.lock.yaml")
    return entry


def commercially_usable(key: str) -> tuple[bool, str]:
    """Um modelo so e tratado como dependencia comercial se estiver verified
    E com licenca marcada como allowed. Qualquer outra coisa e recusada."""
    lock = models_lock()
    if key in lock.get("rejected", {}):
        return False, f"modelo REJEITADO: {lock['rejected'][key].get('reason', '')}"
    if key in lock.get("flagged", {}):
        return False, f"modelo SINALIZADO (decisao juridica pendente): {key}"
    entry = lock.get("models", {}).get(key)
    if entry is None:
        return False, "nao registrado em models.lock.yaml"
    if entry.get("status") != "verified":
        return False, f"status='{entry.get('status')}' (exigido: verified)"
    lic = entry.get("license", {})
    if lic.get("commercial_use") != "allowed":
        return False, f"license.commercial_use='{lic.get('commercial_use')}'"
    if not lic.get("verified_on"):
        return False, "license.verified_on ausente"
    return True, "ok"

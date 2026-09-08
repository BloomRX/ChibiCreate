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
    """A licenca permite uso comercial E foi conferida em fonte primaria?

    Nao diz nada sobre os pesos estarem disponiveis — para isso use
    `executable()`. Um modelo pode ter licenca verificada sem pesos baixados.
    """
    lock = models_lock()
    if key in lock.get("rejected", {}):
        return False, f"modelo REJEITADO: {lock['rejected'][key].get('reason', '')}"
    if key in lock.get("flagged", {}):
        return False, f"modelo SINALIZADO (decisao juridica pendente): {key}"
    entry = lock.get("models", {}).get(key)
    if entry is None:
        return False, "nao registrado em models.lock.yaml"

    lic = entry.get("license", {}) or {}
    if not lic.get("verified"):
        return False, "licenca NAO conferida em fonte primaria"
    if lic.get("commercial_use") != "allowed":
        return False, f"license.commercial_use='{lic.get('commercial_use')}'"
    if not lic.get("verified_on"):
        return False, "license.verified_on ausente"
    if not lic.get("source_url"):
        return False, "license.source_url ausente (fonte primaria obrigatoria)"
    if not entry.get("revision"):
        return False, "revision nao registrada"
    return True, f"{lic.get('spdx')} (conferido em {lic['verified_on']})"


def weights_available(key: str) -> tuple[bool, str]:
    """Os pesos foram baixados e o sha256 conferido?"""
    entry = models_lock().get("models", {}).get(key)
    if entry is None:
        return False, "nao registrado em models.lock.yaml"
    weights = entry.get("weights", {}) or {}
    if not weights.get("verified"):
        return False, "pesos nao baixados/verificados"
    if not weights.get("sha256"):
        return False, "weights.sha256 ausente"
    return True, "ok"


def executable(key: str) -> tuple[bool, str]:
    """Pode ser executado em producao: licenca ok E pesos ok."""
    ok, why = commercially_usable(key)
    if not ok:
        return False, why
    return weights_available(key)


def license_caveat(key: str) -> str | None:
    """Ressalva registrada na licenca (ex.: texto conflitante no README)."""
    entry = models_lock().get("models", {}).get(key, {})
    return (entry.get("license", {}) or {}).get("caveat")


def models_for_phase(phase: int) -> dict[str, dict]:
    """Modelos declarados como necessarios para uma fase."""
    return {
        key: entry
        for key, entry in models_lock().get("models", {}).items()
        if entry.get("required_for_phase") == phase
    }

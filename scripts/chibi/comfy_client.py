"""Cliente HTTP do ComfyUI.  [FASE 3A]

Fala com um servidor ComfyUI pela API HTTP nativa. Nao importa se ele roda
local ou em GPU alugada: o endereco vem sempre de `config/environments/`,
nunca de path absoluto ou localhost hardcoded no codigo.

Fluxo de uma execucao:

    client = ComfyClient.from_environment("cloud")
    client.ping()                       # o servidor esta vivo?
    client.upload_image(path)           # manda o input
    job = client.submit(workflow)       # POST /prompt
    outputs = client.wait(job)          # poll em /history/<id>
    client.download(outputs[0], dest)   # GET /view

Usa apenas a stdlib (urllib). Nao adicionamos `requests` so por isso — menos
dependencia, menos superficie de licenca.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config


class ComfyError(RuntimeError):
    """Falha ao falar com o ComfyUI."""


class ComfyClientNotConfigured(ComfyError):
    """Ambiente sem backend ComfyUI utilizavel."""


class ComfyTimeout(ComfyError):
    """O job nao terminou dentro do prazo."""


class ComfyExecutionError(ComfyError):
    """O ComfyUI aceitou o workflow mas a execucao falhou."""


@dataclass
class ComfyJob:
    prompt_id: str
    client_id: str
    submitted_at: float = field(default_factory=time.time)


@dataclass
class ComfyOutput:
    filename: str
    subfolder: str = ""
    type: str = "output"
    node_id: str | None = None


def _env_value(env_block: dict[str, Any], direct_key: str, env_key: str) -> str | None:
    """Le um valor que pode vir do YAML ou de variavel de ambiente.

    Credenciais e URLs de servidor nunca ficam versionadas: o YAML guarda o
    NOME da variavel, e o valor vem do ambiente.
    """
    if name := env_block.get(env_key):
        if value := os.environ.get(str(name)):
            return value.strip()
    if value := env_block.get(direct_key):
        return str(value).strip()
    return None


class ComfyClient:
    """Cliente minimo da API HTTP do ComfyUI."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: int = 900,
        poll_interval_seconds: float = 2.0,
        connect_timeout: int = 10,
        environment: str = "unknown",
    ) -> None:
        if not base_url:
            raise ComfyClientNotConfigured("base_url vazia")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.connect_timeout = connect_timeout
        self.environment = environment
        self.client_id = str(uuid.uuid4())

    # -- construcao a partir da configuracao ---------------------------------

    @classmethod
    def from_environment(cls, name: str | None = None) -> ComfyClient:
        """Monta o cliente a partir de `config/environments/<name>.yaml`."""
        name = name or config.get("environment", "local") or "local"
        try:
            env = config.environment(name)
        except Exception as exc:  # noqa: BLE001 - ConfigError e afins
            raise ComfyClientNotConfigured(
                f"ambiente '{name}' nao existe em config/environments/ ({exc})"
            ) from exc
        if not env:
            raise ComfyClientNotConfigured(
                f"ambiente '{name}' nao existe em config/environments/"
            )

        block = env.get("comfyui", {}) or {}
        if not block.get("enabled", False):
            raise ComfyClientNotConfigured(
                f"ambiente '{name}': comfyui.enabled = false. "
                f"{(block.get('notes') or '').strip()}"
            )

        base_url = _env_value(block, "base_url", "base_url_env")
        if not base_url:
            env_var = block.get("base_url_env", "CHIBI_COMFY_URL")
            raise ComfyClientNotConfigured(
                f"ambiente '{name}': endereco do ComfyUI nao definido. "
                f"Exporte {env_var}=http://<host>:<porta>"
            )

        return cls(
            base_url,
            token=_env_value(block, "token", "token_env"),
            timeout_seconds=int(block.get("timeout_seconds", 900)),
            poll_interval_seconds=float(block.get("poll_interval_seconds", 2)),
            environment=name,
        )

    # -- HTTP ----------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        content_type: str | None = None,
        timeout: int | None = None,
    ) -> bytes:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, data=data, method=method)
        if content_type:
            req.add_header("Content-Type", content_type)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(
                req, timeout=timeout or self.connect_timeout
            ) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", "replace")[:800]
            except Exception:  # noqa: BLE001
                pass
            raise ComfyError(f"{method} {path} -> HTTP {exc.code}. {body}") from exc
        except urllib.error.URLError as exc:
            raise ComfyError(
                f"{method} {path} -> servidor inacessivel em {self.base_url} "
                f"({exc.reason})"
            ) from exc
        except TimeoutError as exc:
            raise ComfyError(f"{method} {path} -> timeout de conexao") from exc

    def _get_json(self, path: str, timeout: int | None = None) -> Any:
        raw = self._request("GET", path, timeout=timeout)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ComfyError(f"GET {path} devolveu resposta nao-JSON") from exc

    # -- operacoes -----------------------------------------------------------

    def ping(self) -> dict[str, Any]:
        """O servidor responde? Devolve estatisticas do sistema."""
        return self._get_json("/system_stats")

    def server_info(self) -> dict[str, Any]:
        """Resumo do backend, para registrar no recipe."""
        info: dict[str, Any] = {"base_url": self.base_url,
                                "environment": self.environment}
        try:
            stats = self.ping()
        except ComfyError as exc:
            info["reachable"] = False
            info["error"] = str(exc)
            return info

        info["reachable"] = True
        system = stats.get("system", {}) or {}
        info["comfyui_version"] = system.get("comfyui_version")
        info["python_version"] = system.get("python_version")
        info["pytorch_version"] = system.get("pytorch_version")
        info["os"] = system.get("os")
        devices = []
        for dev in stats.get("devices", []) or []:
            devices.append({
                "name": dev.get("name"),
                "type": dev.get("type"),
                "vram_total": dev.get("vram_total"),
                "vram_free": dev.get("vram_free"),
            })
        info["devices"] = devices
        return info

    def object_info(self, node_class: str | None = None) -> dict[str, Any]:
        """Nodes disponiveis no servidor. Usado para validar um workflow."""
        path = "/object_info"
        if node_class:
            path += f"/{urllib.parse.quote(node_class)}"
        return self._get_json(path, timeout=60)

    def available_models(self, folder: str = "diffusion_models") -> list[str]:
        """Arquivos de modelo que o servidor enxerga na pasta indicada."""
        try:
            data = self._get_json(
                f"/models/{urllib.parse.quote(folder)}", timeout=60
            )
        except ComfyError:
            return []
        return [str(x) for x in data] if isinstance(data, list) else []

    def upload_image(self, path: Path, *, subfolder: str = "chibi",
                     overwrite: bool = True) -> str:
        """Envia uma imagem para o input/ do servidor. Devolve o nome usado."""
        path = Path(path)
        if not path.is_file():
            raise ComfyError(f"input nao existe: {path}")

        boundary = f"----chibi{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts: list[bytes] = []

        def field(name: str, value: str) -> None:
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; "
                f'name="{name}"\r\n\r\n{value}\r\n'.encode()
            )

        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
            f'filename="{path.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
        )
        parts.append(path.read_bytes())
        parts.append(b"\r\n")
        field("overwrite", "true" if overwrite else "false")
        if subfolder:
            field("subfolder", subfolder)
        parts.append(f"--{boundary}--\r\n".encode())

        raw = self._request(
            "POST", "/upload/image",
            data=b"".join(parts),
            content_type=f"multipart/form-data; boundary={boundary}",
            timeout=120,
        )
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ComfyError("/upload/image devolveu resposta nao-JSON") from exc

        name = info.get("name") or path.name
        sub = info.get("subfolder") or ""
        return f"{sub}/{name}" if sub else name

    def submit(self, workflow: dict[str, Any]) -> ComfyJob:
        """Enfileira um workflow em formato de API. Devolve o job."""
        if not isinstance(workflow, dict) or not workflow:
            raise ComfyError("workflow vazio ou invalido")

        payload = json.dumps(
            {"prompt": workflow, "client_id": self.client_id}
        ).encode("utf-8")
        raw = self._request(
            "POST", "/prompt", data=payload,
            content_type="application/json", timeout=120,
        )
        try:
            info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ComfyError("/prompt devolveu resposta nao-JSON") from exc

        if errors := info.get("node_errors"):
            raise ComfyExecutionError(f"workflow rejeitado: {errors}")
        prompt_id = info.get("prompt_id")
        if not prompt_id:
            raise ComfyExecutionError(f"/prompt nao devolveu prompt_id: {info}")
        return ComfyJob(prompt_id=str(prompt_id), client_id=self.client_id)

    def history(self, prompt_id: str) -> dict[str, Any]:
        data = self._get_json(f"/history/{urllib.parse.quote(prompt_id)}")
        return data.get(prompt_id, {}) if isinstance(data, dict) else {}

    def wait(self, job: ComfyJob, timeout: int | None = None) -> list[ComfyOutput]:
        """Espera o job terminar e devolve os outputs de imagem."""
        limit = timeout if timeout is not None else self.timeout_seconds
        deadline = time.time() + limit

        while time.time() < deadline:
            entry = self.history(job.prompt_id)
            if entry:
                status = entry.get("status", {}) or {}
                if status.get("status_str") == "error" or (
                    status.get("completed") is False and status.get("messages")
                ):
                    if err := _first_error(status):
                        raise ComfyExecutionError(err)
                if status.get("completed") or entry.get("outputs"):
                    outputs = _collect_outputs(entry.get("outputs", {}) or {})
                    if outputs:
                        return outputs
                    if status.get("completed"):
                        raise ComfyExecutionError(
                            "execucao terminou sem produzir imagem"
                        )
            time.sleep(self.poll_interval_seconds)

        raise ComfyTimeout(
            f"job {job.prompt_id} nao terminou em {limit}s. "
            "O servidor pode estar carregando o modelo (a primeira execucao do "
            "Qwen costuma demorar) ou travado."
        )

    def download(self, output: ComfyOutput, dest: Path) -> Path:
        """Baixa um output para o disco local."""
        query = urllib.parse.urlencode({
            "filename": output.filename,
            "subfolder": output.subfolder,
            "type": output.type,
        })
        raw = self._request("GET", f"/view?{query}", timeout=300)
        if not raw:
            raise ComfyError(f"download vazio: {output.filename}")

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_bytes(raw)
        tmp.replace(dest)
        return dest


def _first_error(status: dict[str, Any]) -> str | None:
    for message in status.get("messages", []) or []:
        if isinstance(message, list) and len(message) >= 2:
            kind, payload = message[0], message[1]
            if kind == "execution_error" and isinstance(payload, dict):
                return (
                    f"{payload.get('node_type', '?')} "
                    f"({payload.get('node_id', '?')}): "
                    f"{payload.get('exception_message', 'erro desconhecido')}"
                )
    if status.get("status_str") == "error":
        return "execucao falhou (sem detalhe no historico)"
    return None


def _collect_outputs(outputs: dict[str, Any]) -> list[ComfyOutput]:
    found: list[ComfyOutput] = []
    for node_id, node_out in outputs.items():
        for image in (node_out or {}).get("images", []) or []:
            if image.get("type") == "temp":
                continue
            found.append(ComfyOutput(
                filename=image.get("filename", ""),
                subfolder=image.get("subfolder", "") or "",
                type=image.get("type", "output") or "output",
                node_id=str(node_id),
            ))
    return [o for o in found if o.filename]

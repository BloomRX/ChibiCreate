"""Preflight do backend remoto.  [FASE 3B.1]

Responde "da para executar?" **sem executar inferencia** — nenhum passo aqui
carrega modelo, ocupa GPU ou gasta tempo pago. E a checagem que se faz antes
de queimar minuto de GPU descobrindo que faltava um node.

Cada checagem devolve um `Check` com um codigo estavel, para que outra
ferramenta possa reagir ao resultado sem interpretar texto:

    OK                     tudo certo
    ENDPOINT_UNREACHABLE   servidor nao respondeu
    OBJECT_INFO_MISSING    /object_info indisponivel ou malformado
    WORKFLOW_INCOMPATIBLE  falta node exigido pelo workflow
    MODEL_MISSING          arquivo de modelo esperado nao esta no servidor
    GPU_MISSING            servidor nao reporta GPU alguma
    GPU_INSUFFICIENT       VRAM abaixo do minimo do ambiente
    UNKNOWN                a API nao informou; nao da para afirmar

Regra: **nunca inventar valor**. Quando a API nao informa, o resultado e
UNKNOWN, nao um palpite otimista.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import config
from .comfy_client import ComfyClient, ComfyClientNotConfigured, ComfyError

# codigos de status
OK = "OK"
ENDPOINT_UNREACHABLE = "ENDPOINT_UNREACHABLE"
OBJECT_INFO_MISSING = "OBJECT_INFO_MISSING"
WORKFLOW_INCOMPATIBLE = "WORKFLOW_INCOMPATIBLE"
MODEL_MISSING = "MODEL_MISSING"
GPU_MISSING = "GPU_MISSING"
GPU_INSUFFICIENT = "GPU_INSUFFICIENT"
NOT_CONFIGURED = "NOT_CONFIGURED"
UNKNOWN = "UNKNOWN"

# pastas do ComfyUI onde cada papel de modelo costuma morar. Consultamos
# varias porque a organizacao muda entre instalacoes.
MODEL_FOLDERS: dict[str, tuple[str, ...]] = {
    "unet": ("diffusion_models", "unet", "checkpoints"),
    "clip": ("text_encoders", "clip"),
    "vae": ("vae",),
}


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def blocking(self) -> bool:
        """UNKNOWN nao bloqueia: e falta de informacao, nao falha."""
        return self.status not in (OK, UNKNOWN)


@dataclass
class PreflightReport:
    environment: str
    checks: list[Check] = field(default_factory=list)
    server: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return not any(c.blocking for c in self.checks)

    @property
    def blockers(self) -> list[Check]:
        return [c for c in self.checks if c.blocking]

    @property
    def unknowns(self) -> list[Check]:
        return [c for c in self.checks if c.status == UNKNOWN]

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "ready": self.ready,
            "server": self.server,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail,
                 "data": c.data}
                for c in self.checks
            ],
        }


def _vram_check(server: dict[str, Any], min_vram_gb: float | None) -> Check:
    devices = server.get("devices") or []
    if not devices:
        return Check("gpu", GPU_MISSING,
                     "o servidor nao reporta nenhum device de GPU")

    gpus = [d for d in devices if (d.get("type") or "").lower() != "cpu"]
    if not gpus:
        return Check("gpu", GPU_MISSING,
                     "o servidor so reporta CPU — inferencia seria inviavel",
                     {"devices": devices})

    first = gpus[0]
    total = first.get("vram_total")
    name = first.get("name") or "?"
    data = {
        "name": name,
        "type": first.get("type"),
        "device_count": len(gpus),
        "vram_total_bytes": total,
        "vram_free_bytes": first.get("vram_free"),
    }

    if total is None:
        return Check("gpu", UNKNOWN,
                     f"{name}: servidor nao informou VRAM total", data)

    total_gb = total / 1024**3
    data["vram_total_gb"] = round(total_gb, 2)
    if min_vram_gb is None:
        return Check("gpu", OK, f"{name} — {total_gb:.1f} GB "
                     "(sem minimo definido no ambiente)", data)
    if total_gb + 0.5 < float(min_vram_gb):
        return Check(
            "gpu", GPU_INSUFFICIENT,
            f"{name} tem {total_gb:.1f} GB; o ambiente exige "
            f"{min_vram_gb} GB. Use uma GPU maior ou uma quantizacao menor "
            "(e registre a mudanca em cloud.yaml).", data)
    return Check("gpu", OK,
                 f"{name} — {total_gb:.1f} GB (minimo {min_vram_gb} GB)", data)


def _model_check(client: ComfyClient, models: dict[str, Any]) -> Check:
    """O servidor tem os arquivos de modelo esperados?

    Nao confia em convencao de nome: pergunta ao servidor o que existe.
    """
    expected = {role: models.get(role) for role in ("unet", "clip", "vae")}
    if not any(expected.values()):
        return Check("models", UNKNOWN,
                     "comfyui.models nao definido em config/environments/")

    listings: dict[str, list[str]] = {}
    for role, folders in MODEL_FOLDERS.items():
        found: list[str] = []
        for folder in folders:
            found.extend(client.available_models(folder))
        listings[role] = found

    any_listing = any(listings.values())
    if not any_listing:
        return Check(
            "models", UNKNOWN,
            "o servidor nao expos as listas de modelos (endpoint /models "
            "ausente nesta versao). Impossivel confirmar sem executar.",
            {"expected": expected})

    missing: dict[str, str] = {}
    present: dict[str, str] = {}
    for role, filename in expected.items():
        if not filename:
            continue
        names = listings.get(role) or []
        # comparacao pelo nome-base: o servidor pode devolver subpasta
        if any(str(n).replace("\\", "/").split("/")[-1] == filename
               for n in names):
            present[role] = filename
        else:
            missing[role] = filename

    data = {"expected": expected, "present": present, "missing": missing,
            "server_has": {k: v[:40] for k, v in listings.items()}}

    if missing:
        lines = ", ".join(f"{r}={f}" for r, f in missing.items())
        return Check(
            "models", MODEL_MISSING,
            f"ausente(s) no servidor: {lines}. Baixe os arquivos no servidor "
            "ou corrija comfyui.models em config/environments/. "
            "NAO troque de modelo por conta propria.", data)
    return Check("models", OK,
                 f"{len(present)} arquivo(s) de modelo presentes", data)


def _workflow_check(client: ComfyClient, workflow_name: str) -> Check:
    from . import experiment

    try:
        workflow = experiment.load_workflow(workflow_name)
    except experiment.ExperimentError as exc:
        return Check("workflow", WORKFLOW_INCOMPATIBLE, str(exc))

    nodes = experiment.workflow_nodes(workflow)
    classes = sorted({n["class_type"] for n in nodes.values()})

    try:
        available = client.object_info()
    except ComfyError as exc:
        return Check("workflow", OBJECT_INFO_MISSING,
                     f"/object_info indisponivel: {exc}")
    if not isinstance(available, dict) or not available:
        return Check("workflow", OBJECT_INFO_MISSING,
                     "/object_info devolveu resposta vazia ou malformada")

    missing = [c for c in classes if c not in available]
    data = {"required": classes, "missing": missing,
            "server_node_count": len(available)}
    if missing:
        return Check(
            "workflow", WORKFLOW_INCOMPATIBLE,
            f"node(s) ausente(s): {', '.join(missing)}. Instale o pacote "
            "correspondente no servidor ou corrija o workflow — nao mascare "
            "a incompatibilidade.", data)

    # sockets: conferir que os inputs usados existem na definicao do node
    mismatches = _socket_mismatches(nodes, available)
    if mismatches:
        data["socket_mismatches"] = mismatches
        return Check(
            "workflow", WORKFLOW_INCOMPATIBLE,
            f"{len(mismatches)} input(s) nao reconhecido(s) pelo servidor. "
            "Ver detalhe: workflow node / expected / actual.", data)

    return Check("workflow", OK,
                 f"{len(classes)} classes e seus inputs conferem", data)


def _socket_mismatches(
    nodes: dict[str, dict], available: dict[str, Any]
) -> list[dict[str, Any]]:
    """Inputs do nosso workflow que o servidor nao reconhece."""
    problems: list[dict[str, Any]] = []
    for node_id, node in nodes.items():
        cls = node["class_type"]
        spec = available.get(cls)
        if not isinstance(spec, dict):
            continue
        input_spec = spec.get("input") or {}
        known: set[str] = set()
        for group in ("required", "optional", "hidden"):
            section = input_spec.get(group)
            if isinstance(section, dict):
                known.update(section.keys())
        if not known:
            continue  # servidor nao detalhou; nao inventar problema
        for key in (node.get("inputs") or {}):
            if key not in known:
                problems.append({
                    "workflow_node": f"{node_id} ({cls})",
                    "expected": key,
                    "actual": sorted(known),
                })
    return problems


def run(
    environment_name: str | None = None,
    *,
    workflow_name: str | None = None,
) -> PreflightReport:
    """Roda todas as checagens. Nunca executa inferencia."""
    from . import experiment

    env_name = environment_name or config.get(
        "runtime.default_environment", "local"
    )
    workflow_name = workflow_name or experiment.DEFAULT_WORKFLOW
    report = PreflightReport(environment=env_name)

    try:
        client = ComfyClient.from_environment(env_name)
    except ComfyClientNotConfigured as exc:
        report.checks.append(Check("endpoint", NOT_CONFIGURED, str(exc)))
        return report

    report.server["base_url"] = client.safe_url

    info = client.server_info()
    if not info.get("reachable"):
        report.checks.append(
            Check("endpoint", ENDPOINT_UNREACHABLE, info.get("error", ""))
        )
        return report

    report.server.update({
        "comfyui_version": info.get("comfyui_version"),
        "pytorch_version": info.get("pytorch_version"),
        "python_version": info.get("python_version"),
        "cuda_version": info.get("cuda_version"),
        "os": info.get("os"),
        "devices": info.get("devices", []),
    })
    report.checks.append(
        Check("endpoint", OK, f"{client.safe_url} respondeu")
    )

    version = info.get("comfyui_version")
    report.checks.append(
        Check("comfyui_version", OK if version else UNKNOWN,
              str(version) if version else
              "servidor nao informou a versao do ComfyUI")
    )

    env_cfg = config.environment(env_name) or {}
    min_vram = (env_cfg.get("requirements", {}) or {}).get("min_vram_gb")
    report.checks.append(_vram_check(info, min_vram))

    report.checks.append(_workflow_check(client, workflow_name))

    models = (env_cfg.get("comfyui", {}) or {}).get("models", {}) or {}
    report.checks.append(_model_check(client, models))

    return report

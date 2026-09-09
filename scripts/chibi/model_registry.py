"""Registry central dos modelos da matriz de avaliacao (FASE 3B).

Toda a logica que os dois notebooks precisam mora AQUI, nao no .ipynb:
celula de notebook nao e testavel, funcao Python e. Os notebooks viram
casca fina que chama estas funcoes.

Os dois notebooks (`model_eval_model_only` e `model_eval_flux_refiner`)
compartilham este mesmo registry, entao o dropdown e identico nos dois e
so existe uma lista de modelos para manter.

Principios que este modulo aplica de forma dura:

- Nenhum modelo e baixado por existir no registry. So o selecionado.
- Referencia nao suportada NUNCA e descartada em silencio: vira um aviso
  explicito em `ReferencePlan.dropped`.
- Preflight bloqueia; nao "avisa e continua".
- Pony e research_only e fica fora de qualquer ranking comercial.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .paths import CONFIG_DIR

REGISTRY_PATH = CONFIG_DIR / "model_eval_registry.yaml"

# Notebook 1: Original -> Modelo. Notebook 2: FLUX run_003 -> Modelo.
STAGE_MODEL_ONLY = "model_only"
STAGE_FLUX_REFINER = "flux_to_model"

READY = "READY"
BLOCKED_DISK = "BLOCKED — insufficient disk"
BLOCKED_VRAM = "BLOCKED — insufficient VRAM"


def load_registry(path: Path | None = None) -> dict[str, Any]:
    p = path or REGISTRY_PATH
    with p.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict) or "models" not in data:
        raise ValueError(f"registry invalido em {p}")
    return data


def model_keys(registry: dict[str, Any] | None = None) -> list[str]:
    reg = registry or load_registry()
    return list(reg["models"])


def dropdown_options(registry: dict[str, Any] | None = None) -> list[str]:
    """Rotulos exibidos no dropdown, na ordem do registry.

    A ordem importa: o Qwen Q3_K_M (`try_first`) deve aparecer antes do Q4.
    """
    reg = registry or load_registry()
    return [m["label"] for m in reg["models"].values()]


def key_for_label(label: str, registry: dict[str, Any] | None = None) -> str:
    reg = registry or load_registry()
    for key, m in reg["models"].items():
        if m["label"] == label:
            return key
    raise KeyError(f"nenhum modelo com label {label!r}")


def get_model(key: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    reg = registry or load_registry()
    if key not in reg["models"]:
        raise KeyError(
            f"modelo {key!r} nao existe no registry. "
            f"Disponiveis: {list(reg['models'])}")
    return reg["models"][key]


# ----------------------------------------------------------------------
# Prompt
# ----------------------------------------------------------------------

def prompt_for(key: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    """Prompt base comum, com override por modelo quando documentado.

    O unico override hoje e o prefixo de score tags do Pony, que e
    exigencia do proprio modelo — nao invencao artistica nossa.
    """
    reg = registry or load_registry()
    m = get_model(key, reg)
    base = " ".join(reg["base_prompt"].split())
    prefix = m.get("prompt_override_prefix", "")
    return {
        "prompt": prefix + base,
        "negative_prompt": m.get(
            "negative_prompt_override", reg.get("base_negative_prompt", "")),
        "base_prompt": base,
        "override_applied": bool(prefix),
        "override_reason": m.get("prompt_override_reason"),
    }


# ----------------------------------------------------------------------
# Referencias
# ----------------------------------------------------------------------

@dataclass
class ReferencePlan:
    """O que sera de fato enviado ao modelo, e o que ficou de fora.

    `dropped` existir e o ponto central: uma referencia que o modelo nao
    comporta precisa aparecer no relatorio e no recipe, nunca sumir.
    """

    primary: str
    primary_role: str
    used: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    limitation: str | None = None
    supported: int = 0

    @property
    def has_dropped(self) -> bool:
        return bool(self.dropped)

    def report(self) -> str:
        linhas = [
            f"PRIMARY IMAGE : {self.primary}  (role={self.primary_role})",
            f"REFERENCES SUPPORTED : {self.supported}",
        ]
        linhas.append("REFERENCES USED : "
                      + (", ".join(self.used) if self.used else "(nenhuma)"))
        if self.dropped:
            linhas.append("")
            linhas.append("REFERENCIAS NAO USADAS — LIMITACAO DO MODELO:")
            for d in self.dropped:
                linhas.append(f"  - {d}")
            if self.limitation:
                linhas.append(f"  motivo: {self.limitation}")
            linhas.append("  (registrado no recipe; nao foi ignorado "
                          "silenciosamente)")
        return "\n".join(linhas)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_image": self.primary,
            "primary_image_role": self.primary_role,
            "references_used": list(self.used),
            "references_dropped": list(self.dropped),
            "references_supported": self.supported,
            "reference_limitation": self.limitation,
            "references_dropped_note": (
                "Referencias listadas em references_dropped NAO foram "
                "enviadas ao modelo porque o pipeline dele nao as comporta. "
                "Registrado explicitamente."
                if self.dropped else None),
        }


def plan_references(
    key: str,
    primary: str,
    primary_role: str,
    desired: list[str],
    registry: dict[str, Any] | None = None,
) -> ReferencePlan:
    """Casa as referencias desejadas com o que o modelo realmente suporta.

    Corta pelo limite declarado no registry e registra o excedente em
    `dropped`. Modelos com `references_supported: 0` (LongCat, Z-Image,
    Pony) descartam TODAS as referencias — e isso precisa ficar visivel,
    porque muda completamente a leitura do resultado.
    """
    m = get_model(key, registry)
    n = int(m.get("references_supported", 0))
    usadas = list(desired[:n])
    descartadas = list(desired[n:])
    return ReferencePlan(
        primary=primary,
        primary_role=primary_role,
        used=usadas,
        dropped=descartadas,
        limitation=m.get("reference_limitation") if descartadas else None,
        supported=n,
    )


# ----------------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------------

@dataclass
class Preflight:
    model_key: str
    label: str
    status: str
    expected_disk_gb: float
    expected_vram_gb: float
    available_disk_gb: float | None
    available_vram_gb: float | None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == READY

    def report(self) -> str:
        def fmt(v):
            return "desconhecido" if v is None else f"{v:.1f} GB"

        linhas = [
            "=" * 64,
            f"SELECTED MODEL:\n    {self.label}",
            "",
            f"EXPECTED DISK:\n    {self.expected_disk_gb:.1f} GB",
            f"EXPECTED VRAM:\n    {self.expected_vram_gb:.1f} GB",
            "",
            f"AVAILABLE DISK:\n    {fmt(self.available_disk_gb)}",
            f"AVAILABLE VRAM:\n    {fmt(self.available_vram_gb)}",
            "",
            f"STATUS:\n    {self.status}",
        ]
        for r in self.reasons:
            linhas.append(f"    {r}")
        if self.warnings:
            linhas.append("")
            linhas.append("AVISOS:")
            linhas.extend(f"    {w}" for w in self.warnings)
        linhas.append("=" * 64)
        return "\n".join(linhas)


def preflight(
    key: str,
    available_disk_gb: float | None,
    available_vram_gb: float | None,
    registry: dict[str, Any] | None = None,
    vram_margin_gb: float = 0.5,
) -> Preflight:
    """Decide READY / BLOCKED ANTES de qualquer download pesado.

    Existe por causa de um problema real: o Qwen fp8/bf16 travou o Colab
    durante o carregamento. Baixar 30 GB para descobrir que nao cabe custa
    tempo e pode derrubar a sessao. Aqui a conta e feita antes.

    VRAM ou disco desconhecido NAO vira READY — vira BLOCKED. Nao dar para
    medir e motivo para parar e o usuario decidir, nao para prosseguir no
    escuro.
    """
    m = get_model(key, registry)
    disco = float(m["disk_gb"])
    vram = float(m["vram_gb"])

    razoes: list[str] = []
    avisos: list[str] = []

    if m.get("download_estimated") or m.get("vram_estimated"):
        avisos.append(
            "Requisitos vem do model card, nao de medicao nossa "
            "(estimated: true).")
    if m.get("third_party_quantization"):
        avisos.append(
            f"Quantizacao de terceiro ({m.get('quantization_author')}): "
            "licenca da variante e separada da do modelo-base.")
    if m.get("requires_custom_node"):
        avisos.append(
            f"Exige o custom node {m['requires_custom_node']} — precisa de "
            "aceite explicito antes de instalar.")
    if m.get("commercial_status") == "research_only":
        avisos.append(m.get("commercial_banner", "Research only"))

    status = READY

    # Disco primeiro: e o que impede o download de sequer comecar.
    if available_disk_gb is None:
        status = BLOCKED_DISK
        razoes.append("Espaco em disco desconhecido — nao inicio download "
                      "as cegas.")
    elif available_disk_gb < disco:
        status = BLOCKED_DISK
        falta = disco - available_disk_gb
        razoes.append(
            f"Faltam {falta:.1f} GB de disco "
            f"({available_disk_gb:.1f} disponivel, {disco:.1f} necessario).")
        razoes.append("Troque de runtime ou rode a celula de cleanup.")

    if available_vram_gb is None:
        if status == READY:
            status = BLOCKED_VRAM
        razoes.append("VRAM desconhecida — sem GPU detectada ou nao "
                      "reportada.")
    elif available_vram_gb + vram_margin_gb < vram:
        if status == READY:
            status = BLOCKED_VRAM
        falta = vram - available_vram_gb
        razoes.append(
            f"Faltam ~{falta:.1f} GB de VRAM "
            f"({available_vram_gb:.1f} disponivel, {vram:.1f} necessario).")
        razoes.append("Troque para um runtime com GPU maior "
                      "(Colab: Runtime > Change runtime type).")

    if status == READY:
        razoes.append("Requisitos declarados cabem no runtime atual.")

    return Preflight(
        model_key=key,
        label=m["label"],
        status=status,
        expected_disk_gb=disco,
        expected_vram_gb=vram,
        available_disk_gb=available_disk_gb,
        available_vram_gb=available_vram_gb,
        reasons=razoes,
        warnings=avisos,
    )


def describe(key: str, registry: dict[str, Any] | None = None) -> str:
    """Ficha mostrada logo apos a escolha no dropdown, antes de baixar."""
    m = get_model(key, registry)
    quant = ""
    if m.get("third_party_quantization"):
        quant = (f"\nQuantization license : {m.get('quantization_license')} "
                 f"(por {m.get('quantization_author')}, "
                 f"verificada: {m.get('quantization_license_verified')})")
    linhas = [
        "-" * 64,
        "MODEL EVALUATION",
        "-" * 64,
        f"Selected model       : {m['label']}",
        f"Repo                 : {m.get('repo')}",
        f"License              : {m.get('license')} "
        f"(verificada: {m.get('license_verified')})" + quant,
        f"Commercial status    : {m.get('commercial_status')}",
        f"Estimated disk       : {m['disk_gb']} GB",
        f"Estimated VRAM       : {m['vram_gb']} GB",
        f"References supported : {m.get('references_supported')}",
        f"Pipeline type        : {m.get('pipeline_type')}",
    ]
    if m.get("commercial_status") == "research_only":
        linhas += ["", "*" * 64,
                   m.get("commercial_banner", "Research only"),
                   "Resultado NAO entra no ranking comercial.",
                   "*" * 64]
    if m.get("capability_warning"):
        linhas += ["", "LIMITE DE CAPACIDADE:",
                   "  " + " ".join(m["capability_warning"].split())]
    if m.get("reference_limitation"):
        linhas += ["", "REFERENCIAS:",
                   "  " + " ".join(m["reference_limitation"].split())]
    linhas.append("-" * 64)
    return "\n".join(linhas)


def needs_confirmation(key: str, registry: dict[str, Any] | None = None,
                       threshold_gb: float = 10.0) -> bool:
    """Confirmacao so quando ha risco real: download grande, custom node
    de terceiro ou modelo research-only."""
    m = get_model(key, registry)
    return (float(m["download_gb"]) >= threshold_gb
            or bool(m.get("requires_custom_node"))
            or m.get("commercial_status") == "research_only")


def commercial_candidates(registry: dict[str, Any] | None = None) -> list[str]:
    """Modelos elegiveis a ranking comercial. Pony fica fora."""
    reg = registry or load_registry()
    return [k for k, m in reg["models"].items()
            if not m.get("excluded_from_commercial_ranking")]


# ----------------------------------------------------------------------
# Ambiente / saida
# ----------------------------------------------------------------------

def free_disk_gb(path: str | Path = "/") -> float:
    return shutil.disk_usage(str(path)).free / 1024 ** 3


def run_dir_for(stage: str, key: str, root: Path,
                registry: dict[str, Any] | None = None) -> Path:
    """`experiments/model_eval/<stage>/<model>/<run_id>/`, sem sobrescrever.

    O run_id sempre avanca para o proximo livre: reexecutar o mesmo modelo
    depois de um reset nunca apaga o resultado anterior.
    """
    if stage not in (STAGE_MODEL_ONLY, STAGE_FLUX_REFINER):
        raise ValueError(f"stage invalido: {stage!r}")
    get_model(key, registry)  # valida a chave
    base = Path(root) / "experiments" / "model_eval" / stage / key
    base.mkdir(parents=True, exist_ok=True)
    existentes = sorted(d.name for d in base.glob("run_*") if d.is_dir())
    n = 1
    if existentes:
        n = max(int(e.split("_")[1]) for e in existentes) + 1
    d = base / f"run_{n:03d}"
    d.mkdir()
    return d


def comparison_table(rows: list[dict[str, Any]]) -> str:
    """Tabela final. STYLE/IDENTITY/DESIGN_PRESERVATION saem vazios de
    proposito: sao preenchidos por humano. Nao existe OVERALL."""
    cab = ["MODEL", "STYLE", "IDENTITY", "DESIGN_PRESERVATION",
           "TIME", "VRAM", "STATUS"]
    linhas = ["| " + " | ".join(cab) + " |",
              "|" + "|".join(["---"] * len(cab)) + "|"]
    for r in rows:
        linhas.append("| " + " | ".join([
            str(r.get("model", "")),
            str(r.get("style", "")),
            str(r.get("identity", "")),
            str(r.get("design_preservation", "")),
            str(r.get("time", "")),
            str(r.get("vram", "")),
            str(r.get("status", "")),
        ]) + " |")
    linhas += [
        "",
        "STYLE / IDENTITY / DESIGN_PRESERVATION sao preenchidos por humano.",
        "Nao ha OVERALL: nao e media aritmetica e o agente nao escolhe "
        "vencedor artistico.",
    ]
    return "\n".join(linhas)

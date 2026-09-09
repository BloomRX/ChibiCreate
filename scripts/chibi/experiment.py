"""Execucoes experimentais contra o ComfyUI.  [FASE 3A]

Um experimento NAO e um asset do projeto. Ele existe para responder
perguntas tecnicas ("o motor executa?", "a config e reproduzivel?"), nao
para produzir arte aprovada. Por isso:

  - a saida vai para `experiments/`, nunca para `characters/<id>/chibi/`;
  - o recipe nasce com `approval_status: "experimental"`;
  - nada aqui promove um arquivo a Chibi Master. Isso e decisao humana.

Estrutura por execucao:

    experiments/qwen_edit_2511/run_001/
        input.png
        output.png
        recipe.json
        workflow.resolved.json
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config, paths
from .comfy_client import ComfyClient, ComfyError
from .hashing import sha256_file

EXPERIMENTS_DIRNAME = "experiments"
DEFAULT_WORKFLOW = "experimental/qwen_edit_minimal"

# FASE 3B = MODEL EVALUATION. Candidatos avaliados no MESMO experimento
# padronizado (mesmo input, prompt, seed). Nenhum e "o vencedor" — a escolha
# e humana, apos revisao visual.
#
# Cada entrada amarra model_key + workflow + ambiente, para que trocar de
# candidato nao exija lembrar tres flags coerentes entre si.
MODEL_CANDIDATES: dict[str, dict[str, str]] = {
    "qwen-edit": {
        "model_key": "qwen_image_edit_2511",
        "workflow": "experimental/qwen_edit_minimal",
        "environment": "cloud",
        "label": "Qwen-Image-Edit-2511",
    },
    "flux2-klein": {
        "model_key": "flux2_klein_4b",
        "workflow": "experimental/flux2_klein_edit",
        "environment": "colab_flux2",
        "label": "FLUX.2 [klein] 4B",
    },
    # Estagio 2 do experimento FLUX -> QWEN. Mesmo modelo do "qwen-edit",
    # workflow diferente (multi-referencia + img2img a partir da imagem
    # principal). Separado para nao mexer no candidato original.
    "qwen-refiner": {
        "model_key": "qwen_image_edit_2511",
        "workflow": "experimental/qwen_edit_multiref",
        "environment": "cloud",
        "label": "Qwen-Image-Edit-2511 (refiner)",
    },
    # Candidato 3: checkpoint SDXL. Ecossistema DIFERENTE dos outros dois —
    # nao e modelo de edicao, so tem img2img. Ver o _comment do workflow.
    "wai-illustrious": {
        "model_key": "wai_illustrious_sdxl_v170",
        "workflow": "experimental/wai_illustrious_chibi",
        "environment": "cloud",
        "label": "WAI-illustrious-SDXL v17.0",
    },
}

# Subdiretorio da avaliacao comparativa: experiments/model_eval/<model_key>/
MODEL_EVAL_DIRNAME = "model_eval"

# Defaults do experimento minimo. Nao sao "os parametros certos" para arte —
# sao um ponto de partida conservador para validar o motor.
DEFAULT_PARAMS: dict[str, Any] = {
    "seed": 42,
    "steps": 20,
    "cfg": 2.5,
    "sampler": "euler",
    "scheduler": "simple",
    "denoise": 1.0,
    "negative_prompt": "",
}


class ExperimentError(RuntimeError):
    pass


@dataclass
class ExperimentResult:
    run_id: str
    run_dir: Path
    output_path: Path | None
    recipe_path: Path
    params: dict[str, Any] = field(default_factory=dict)
    server: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def experiments_root() -> Path:
    return paths.ROOT / EXPERIMENTS_DIRNAME


def workflow_path(name: str = DEFAULT_WORKFLOW, version: str = "v1") -> Path:
    return paths.ROOT / "workflows" / name / f"{version}.json"


def load_workflow(name: str = DEFAULT_WORKFLOW, version: str = "v1") -> dict:
    path = workflow_path(name, version)
    if not path.is_file():
        raise ExperimentError(f"workflow nao encontrado: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ExperimentError(f"workflow invalido ({path.name}): {exc}") from exc
    if not isinstance(data, dict):
        raise ExperimentError(f"workflow deve ser objeto JSON: {path}")
    return data


def workflow_nodes(workflow: dict) -> dict[str, dict]:
    """Nodes reais do grafo, ignorando as chaves de comentario (_comment)."""
    return {
        k: v for k, v in workflow.items()
        if not k.startswith("_") and isinstance(v, dict) and "class_type" in v
    }


def next_run_id(model_dir: Path) -> str:
    """run_001, run_002, ... Nunca reusa um id existente."""
    used = 0
    if model_dir.is_dir():
        for child in model_dir.iterdir():
            if m := re.fullmatch(r"run_(\d+)", child.name):
                used = max(used, int(m.group(1)))
    return f"run_{used + 1:03d}"


def resolve_workflow(workflow: dict, values: dict[str, Any]) -> dict:
    """Substitui os placeholders %%NOME%% preservando o tipo do valor.

    Um placeholder sozinho no campo vira o valor com o tipo certo
    (`"%%SEED%%"` -> `42`, inteiro). Placeholder no meio de texto vira string.
    """
    missing: set[str] = set()

    def convert(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: convert(v) for k, v in node.items()}
        if isinstance(node, list):
            return [convert(v) for v in node]
        if not isinstance(node, str):
            return node

        if m := re.fullmatch(r"%%([A-Z0-9_]+)%%", node):
            key = m.group(1)
            if key not in values:
                missing.add(key)
                return node
            return values[key]

        def sub(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in values:
                missing.add(key)
                return m.group(0)
            return str(values[key])

        return re.sub(r"%%([A-Z0-9_]+)%%", sub, node)

    resolved = {k: convert(v) for k, v in workflow.items() if not k.startswith("_")}
    if missing:
        raise ExperimentError(
            "placeholders sem valor no workflow: " + ", ".join(sorted(missing))
        )
    return resolved


def _model_files(env_name: str) -> dict[str, str]:
    """Nomes dos arquivos de modelo, como o SERVIDOR os enxerga."""
    env = config.environment(env_name) or {}
    models = (env.get("comfyui", {}) or {}).get("models", {}) or {}
    missing = [k for k in ("unet", "clip", "vae") if not models.get(k)]
    if missing:
        raise ExperimentError(
            f"ambiente '{env_name}': falta comfyui.models.{{{','.join(missing)}}} "
            "em config/environments/. Sao os nomes dos arquivos no servidor "
            "ComfyUI, nao caminhos locais."
        )
    return {
        "unet": str(models["unet"]),
        "clip": str(models["clip"]),
        "vae": str(models["vae"]),
        "weight_dtype": str(models.get("weight_dtype", "default")),
    }


def _free_vram(server: dict[str, Any]) -> int | None:
    devices = server.get("devices") or []
    return devices[0].get("vram_free") if devices else None


def _gpu_block(server: dict[str, Any]) -> dict[str, Any]:
    """Hardware que EXECUTOU, lido do proprio servidor.

    Nada aqui e presumido: se o backend nao informou, fica None. Um recipe
    que mente sobre o hardware e pior que um recipe incompleto.
    """
    devices = server.get("devices") or []
    first = devices[0] if devices else {}
    total = first.get("vram_total")
    return {
        "name": first.get("name"),
        "type": first.get("type"),
        "vram_total_bytes": total,
        "vram_total_gb": round(total / 1024**3, 2) if total else None,
        "vram_free_bytes_at_start": first.get("vram_free"),
        "device_count": len(devices),
    }


def estimate_cost(
    execution_seconds: float | None, usd_per_hour: float | None
) -> dict[str, Any]:
    """Custo aproximado de UMA execucao.

    Baseline, nao previsao de producao: nao inclui tempo ocioso, cold start,
    download de pesos nem as execucoes descartadas.
    """
    if execution_seconds is None or usd_per_hour is None:
        return {
            "usd": None,
            "usd_per_hour": usd_per_hour,
            "note": "sem dado suficiente para estimar",
        }
    return {
        "usd": round(usd_per_hour * (execution_seconds / 3600.0), 4),
        "usd_per_hour": usd_per_hour,
        "execution_seconds": round(execution_seconds, 2),
        "note": (
            "Custo apenas do tempo desta execucao. NAO e custo de producao: "
            "exclui cold start, download de pesos, tempo ocioso e tentativas "
            "descartadas."
        ),
    }


def build_recipe(
    *,
    run_id: str,
    model_key: str,
    workflow_name: str,
    workflow_version: str,
    workflow_sha: str,
    params: dict[str, Any],
    input_path: Path,
    output_path: Path | None,
    server: dict[str, Any],
    environment_name: str,
    model_files: dict[str, str],
    timings: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recipe da execucao experimental.

    `approval_status` nasce "experimental" de proposito: nenhum caminho de
    codigo aqui pode marcar um artefato como aprovado.
    """
    from .recipe import environment_block

    entry = config.model(model_key) or {}
    lic = entry.get("license", {}) or {}

    env_block = environment_block()
    env_block["environment_name"] = environment_name
    env_block["comfyui_version"] = server.get("comfyui_version")
    env_block["pytorch_version"] = server.get("pytorch_version")
    env_block["server_os"] = server.get("os")
    env_block["devices"] = server.get("devices", [])

    return {
        "kind": "experiment",
        "run_id": run_id,
        "approval_status": "experimental",
        "approved_by": None,
        "approved_at": None,
        "note": (
            "Execucao EXPERIMENTAL de validacao de motor. NAO e um asset "
            "aprovado, NAO e Chibi Master. Aprovacao artistica e humana."
        ),

        "model": entry.get("repo", model_key),
        "model_key": model_key,
        "revision": entry.get("revision"),
        "model_sha256": (entry.get("weights", {}) or {}).get("sha256"),
        "model_files_on_server": model_files,
        "license": lic.get("spdx"),
        "license_verified": bool(lic.get("verified")),
        "license_source": lic.get("source_url"),
        "commercial_status": lic.get("commercial_status", "unverified"),

        "workflow": f"{workflow_name}/{workflow_version}.json",
        "workflow_sha256": workflow_sha,

        "seed": params.get("seed"),
        "prompt": params.get("prompt"),
        "negative_prompt": params.get("negative_prompt"),
        "parameters": {
            "steps": params.get("steps"),
            "cfg": params.get("cfg"),
            "sampler": params.get("sampler"),
            "scheduler": params.get("scheduler"),
            "denoise": params.get("denoise"),
            "width": params.get("width"),
            "height": params.get("height"),
        },

        "quantization": model_files.get("weight_dtype"),
        "dtype": model_files.get("weight_dtype"),
        "offload": server.get("offload"),
        "backend": "comfyui",
        "device": server.get("devices", [{}])[0].get("name")
        if server.get("devices") else None,

        # hardware e custo (secoes 13/14/17 da spec da fase 3B)
        "gpu": _gpu_block(server),
        "vram_peak_bytes": (timings or {}).get("vram_peak_bytes"),
        "cuda": server.get("cuda_version"),
        "comfyui_version": server.get("comfyui_version"),
        "execution_time": (timings or {}).get("execution_seconds"),
        "timings": timings or {},
        "cost_estimate": cost or estimate_cost(None, None),

        "input_sha256": sha256_file(input_path) if input_path.is_file() else None,
        "input_filename": input_path.name,
        "output_sha256": sha256_file(output_path)
        if output_path and output_path.is_file() else None,
        "output_filename": output_path.name if output_path else None,

        "environment": env_block,
        "timestamp": _now(),
    }


def _prune_unused_image_slots(workflow: dict, n_extra: int) -> dict:
    """Remove LoadImage/entradas de referencia que nao serao preenchidas.

    O workflow multi-referencia declara o maximo de slots. Quando a execucao
    usa menos, os placeholders restantes ficariam sem valor e o grafo seria
    invalido. Poda-los mantem o grafo executado igual ao experimento
    declarado — nada de imagem placeholder para "preencher buraco".
    """
    import copy
    import json as _json

    wf = copy.deepcopy(workflow)
    for i in range(n_extra + 2, 12):
        token = f"%%INPUT_IMAGE_{i}%%"
        if token not in _json.dumps(wf):
            continue
        alvo = [k for k, v in wf.items()
                if isinstance(v, dict)
                and v.get("inputs", {}).get("image") == token]
        for nid in alvo:
            del wf[nid]
            for v in wf.values():
                if not isinstance(v, dict):
                    continue
                for campo, ligacao in list(v.get("inputs", {}).items()):
                    if (isinstance(ligacao, list) and len(ligacao) == 2
                            and ligacao[0] == nid):
                        del v["inputs"][campo]
    return wf


def pixel_sha256(path: Path) -> str | None:
    """Hash dos PIXELS, nao do arquivo.

    Dois PNGs podem ter bytes diferentes (metadata, timestamp, compressao) e
    a mesma imagem. Comparar so o sha256 do arquivo confundiria "arquivo
    diferente" com "imagem diferente" — e a pergunta do experimento e sobre
    a imagem. Fica em campo SEPARADO de output_sha256, nunca no lugar dele.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            return hashlib.sha256(
                im.convert("RGBA").tobytes()
            ).hexdigest()
    except Exception:
        return None


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_qwen_edit(
    character_id: str,
    *,
    input_rel: str = "reference/full_body.png",
    extra_refs: tuple[str, ...] = (),
    prompt: str,
    environment_name: str | None = None,
    model_key: str = "qwen_image_edit_2511",
    workflow_name: str = DEFAULT_WORKFLOW,
    workflow_version: str = "v1",
    overrides: dict[str, Any] | None = None,
    dry_run: bool = False,
    eval_mode: bool = False,
) -> ExperimentResult:
    """Executa um experimento de edicao. Com `dry_run`, nao chama o servidor.

    O dry-run resolve o workflow, monta o recipe e escreve tudo em disco, para
    que a estrutura seja testavel sem GPU.
    """
    cp = paths.CharacterPaths(character_id)
    if not cp.root.is_dir():
        raise ExperimentError(f"personagem '{character_id}' nao existe")

    # A imagem principal pode vir de fora do personagem: no experimento
    # FLUX -> QWEN ela e a SAIDA do estagio anterior. Caminho absoluto ou
    # relativo ao repo tem precedencia sobre reference/.
    external = Path(input_rel)
    if external.is_file():
        input_path = external
    else:
        input_path = cp.root / input_rel
    if not input_path.is_file():
        raise ExperimentError(
            f"input nao encontrado: {input_path}. Rode 'chibi flow01 "
            f"{character_id}' antes, ou aponte --input para a saida do "
            "estagio anterior."
        )

    # Multi-referencia: cada ref extra vira INPUT_IMAGE_2, _3, ... O workflow
    # precisa ter o placeholder correspondente, senao a referencia seria
    # aceita na CLI e silenciosamente ignorada no grafo.
    extra_paths: list[Path] = []
    for rel in extra_refs:
        cand = Path(rel)
        rp = cand if cand.is_file() else cp.root / rel
        if not rp.is_file():
            raise ExperimentError(f"referencia extra nao encontrada: {rp}")
        extra_paths.append(rp)

    ok, why = config.technically_usable(model_key)
    if not ok:
        raise ExperimentError(f"modelo '{model_key}' nao liberado: {why}")

    environment_name = environment_name or config.get(
        "runtime.default_environment", "local"
    )

    workflow = load_workflow(workflow_name, workflow_version)
    wf_sha = sha256_file(workflow_path(workflow_name, workflow_version))

    params: dict[str, Any] = dict(DEFAULT_PARAMS)

    # O ambiente pode sobrepor os defaults de sampling. Necessario porque
    # modelos destilados exigem parametros proprios: o FLUX.2 klein roda com
    # cfg 1.0 e 4 passos, enquanto o default (cfg 2.5, 20 passos) serve ao
    # Qwen. Aplicar cfg 2.5 no FLUX produz imagem lavada. A precedencia e
    # DEFAULT_PARAMS < ambiente < overrides da linha de comando.
    env_cfg_early = config.environment(environment_name) or {}
    for key, value in (env_cfg_early.get("sampling") or {}).items():
        if key in DEFAULT_PARAMS:
            params[key] = value

    params.update({
        "prompt": prompt,
        "width": config.get("resolution.master.width", 1024),
        "height": config.get("resolution.master.height", 1024),
    })
    params.update(overrides or {})

    # Avaliacao comparativa vai para experiments/model_eval/<model_key>/,
    # separada das execucoes avulsas.
    base = experiments_root() / MODEL_EVAL_DIRNAME if eval_mode else experiments_root()
    model_dir = base / model_key
    run_id = next_run_id(model_dir)
    run_dir = model_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    server: dict[str, Any] = {}
    output_path: Path | None = None
    timings: dict[str, Any] = {}
    cost: dict[str, Any] | None = None

    # o input vai junto: o experimento tem que ser auditavel sozinho
    local_input = run_dir / f"input{input_path.suffix}"
    shutil.copy2(input_path, local_input)

    model_files = _model_files(environment_name) if not dry_run else \
        _model_files_or_placeholder(environment_name, warnings)

    values = {
        "UNET_NAME": model_files["unet"],
        "CLIP_NAME": model_files["clip"],
        "VAE_NAME": model_files["vae"],
        "WEIGHT_DTYPE": model_files["weight_dtype"],
        "INPUT_IMAGE": input_path.name,
        "PROMPT": params["prompt"],
        "NEGATIVE_PROMPT": params["negative_prompt"],
        "SEED": params["seed"],
        "STEPS": params["steps"],
        "CFG": params["cfg"],
        "SAMPLER": params["sampler"],
        "SCHEDULER": params["scheduler"],
        "DENOISE": params["denoise"],
        "WIDTH": params["width"],
        "HEIGHT": params["height"],
        "OUTPUT_PREFIX": f"chibi_exp/{character_id}_{run_id}",
    }
    for i, rp in enumerate(extra_paths, start=2):
        values[f"INPUT_IMAGE_{i}"] = rp.name

    # Guarda: referencia passada mas sem lugar no grafo = ref ignorada.
    # Este e o modo de falhar mais perigoso do experimento — a execucao
    # termina normalmente e a imagem sai plausivel, so que a referencia nunca
    # entrou. Abortar ANTES de gastar GPU, sem fallback silencioso.
    _wf_text = json.dumps(workflow)
    for i in range(2, len(extra_paths) + 2):
        if f"%%INPUT_IMAGE_{i}%%" not in _wf_text:
            disponiveis = sum(
                1 for j in range(2, 12) if f"%%INPUT_IMAGE_{j}%%" in _wf_text
            )
            raise ExperimentError(
                f"workflow '{workflow_name}/{workflow_version}' comporta "
                f"{disponiveis} referencia(s) extra(s), mas foram passadas "
                f"{len(extra_paths)}. A referencia #{i} seria IGNORADA "
                "silenciosamente. Nenhum fallback aplicado."
            )

    # o input extra tambem vai junto, para o run ser auditavel sozinho
    local_extras: list[Path] = []
    for i, rp in enumerate(extra_paths, start=2):
        dst = run_dir / f"input_{i}{rp.suffix}"
        shutil.copy2(rp, dst)
        local_extras.append(dst)

    # Slots de referencia nao usados sao PODADOS do grafo. Sem isso, o teste
    # A (1 imagem) e o B (2 imagens) quebrariam num workflow que declara 3
    # slots. Podar e mais honesto que mandar imagem falsa: o grafo executado
    # passa a refletir exatamente as referencias que existem.
    workflow = _prune_unused_image_slots(workflow, len(extra_paths))

    resolved = resolve_workflow(workflow, values)
    (run_dir / "workflow.resolved.json").write_text(
        json.dumps(resolved, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if dry_run:
        warnings.append(
            "DRY RUN: nada foi enviado ao ComfyUI. Workflow resolvido e recipe "
            "escritos; nenhuma imagem gerada."
        )
    else:
        import time as _time

        client = ComfyClient.from_environment(environment_name)
        t0 = _time.time()
        server = client.server_info()
        if not server.get("reachable"):
            raise ExperimentError(
                f"ComfyUI inacessivel: {server.get('error')}"
            )
        timings["connect_seconds"] = round(_time.time() - t0, 2)

        vram_before = _free_vram(server)

        t_up = _time.time()
        uploaded = client.upload_image(input_path)
        timings["upload_seconds"] = round(_time.time() - t_up, 2)

        values["INPUT_IMAGE"] = uploaded
        for i, rp in enumerate(extra_paths, start=2):
            values[f"INPUT_IMAGE_{i}"] = client.upload_image(rp)
        resolved = resolve_workflow(workflow, values)
        (run_dir / "workflow.resolved.json").write_text(
            json.dumps(resolved, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        t_exec = _time.time()
        job = client.submit(resolved)
        outputs = client.wait(job)
        timings["execution_seconds"] = round(_time.time() - t_exec, 2)

        # VRAM: a diferenca entre o livre antes e depois e o melhor proxy que
        # a API do ComfyUI oferece. Nao e o pico real dentro da execucao.
        after = client.server_info()
        vram_after = _free_vram(after)
        if vram_before is not None and vram_after is not None:
            timings["vram_used_bytes"] = max(0, vram_before - vram_after)
            timings["vram_peak_bytes"] = timings["vram_used_bytes"]
            timings["vram_note"] = (
                "Aproximacao: vram_free antes menos depois, via /system_stats. "
                "NAO e o pico instantaneo durante a inferencia."
            )

        t_dl = _time.time()
        output_path = run_dir / "output.png"
        client.download(outputs[0], output_path)
        timings["download_seconds"] = round(_time.time() - t_dl, 2)
        timings["total_seconds"] = round(_time.time() - t0, 2)

        env_cfg = config.environment(environment_name) or {}
        cost = estimate_cost(
            timings.get("execution_seconds"),
            (env_cfg.get("cost", {}) or {}).get("estimated_usd_per_hour"),
        )

        if len(outputs) > 1:
            warnings.append(
                f"{len(outputs)} imagens retornadas; salvei a primeira."
            )

    recipe = build_recipe(
        run_id=run_id,
        model_key=model_key,
        workflow_name=workflow_name,
        workflow_version=workflow_version,
        workflow_sha=wf_sha,
        params=params,
        input_path=local_input,
        output_path=output_path,
        server=server,
        environment_name=environment_name,
        model_files=model_files,
        timings=timings,
        cost=cost,
    )
    if output_path and output_path.is_file():
        # Campo proprio: "imagem igual" e "arquivo igual" sao perguntas
        # diferentes e nao podem colidir no mesmo campo.
        recipe["output_pixel_sha256"] = pixel_sha256(output_path)
        recipe["pixel_hash_note"] = (
            "Hash dos pixels RGBA decodificados. NAO substitui "
            "output_sha256 (hash do arquivo)."
        )
    recipe["input_pixel_sha256"] = pixel_sha256(local_input)

    all_refs = [local_input] + local_extras
    # O papel da imagem principal NAO e sempre "full_body": no experimento
    # FLUX -> QWEN ela e a saida do estagio anterior. Rotular errado
    # inverteria a leitura do experimento.
    main_role = "primary_image"
    if input_path.name == "full_body.png":
        main_role = "full_body"
    elif "output" in input_path.name or "flux" in input_path.name.lower():
        main_role = "stage1_output"
    roles = [main_role] + [Path(r).stem for r in extra_refs]
    recipe["reference_count"] = len(all_refs)
    recipe["references"] = [
        {"role": role, "file": rp.name, "sha256": sha256_file(rp),
         "pixel_sha256": pixel_sha256(rp)}
        for role, rp in zip(roles, all_refs)
    ]
    recipe["primary_image_role"] = main_role
    if dry_run:
        recipe["dry_run"] = True
    recipe_path = run_dir / "recipe.json"
    recipe_path.write_text(
        json.dumps(recipe, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return ExperimentResult(
        run_id=run_id,
        run_dir=run_dir,
        output_path=output_path,
        recipe_path=recipe_path,
        params=params,
        server=server,
        warnings=warnings,
    )


def _model_files_or_placeholder(
    env_name: str, warnings: list[str]
) -> dict[str, str]:
    try:
        return _model_files(env_name)
    except ExperimentError as exc:
        warnings.append(f"{exc} (dry-run: usando placeholders)")
        return {
            "unet": "<NAO CONFIGURADO>",
            "clip": "<NAO CONFIGURADO>",
            "vae": "<NAO CONFIGURADO>",
            "weight_dtype": "<NAO CONFIGURADO>",
        }


def compare_runs(run_a: Path, run_b: Path) -> dict[str, Any]:
    """Compara duas execucoes. Responde a pergunta da secao 9 da spec.

    NAO afirma determinismo: mede e reporta.
    """
    def load(run: Path) -> dict:
        path = run / "recipe.json"
        if not path.is_file():
            raise ExperimentError(f"recipe ausente: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    ra, rb = load(run_a), load(run_b)

    def same(field_: str) -> bool:
        return ra.get(field_) == rb.get(field_)

    identical_output = (
        ra.get("output_sha256") is not None
        and ra.get("output_sha256") == rb.get("output_sha256")
    )
    return {
        "run_a": run_a.name,
        "run_b": run_b.name,
        "same_seed": same("seed"),
        "same_prompt": same("prompt"),
        "same_parameters": ra.get("parameters") == rb.get("parameters"),
        "same_model_revision": same("revision"),
        "same_workflow": same("workflow_sha256"),
        "same_quantization": same("quantization"),
        "same_input": same("input_sha256"),
        "same_device": same("device"),
        "output_a_sha256": ra.get("output_sha256"),
        "output_b_sha256": rb.get("output_sha256"),
        "identical_output": identical_output,
        "verdict": (
            "configuracao reproduzida e bytes identicos"
            if identical_output else
            "configuracao reproduzida, bytes DIFERENTES"
            if ra.get("output_sha256") and rb.get("output_sha256") else
            "sem output para comparar (dry-run?)"
        ),
    }

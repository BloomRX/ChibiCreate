#!/usr/bin/env python3
"""ChibiCreate CLI.

Fase 1 implementa: character new, validate, status, models, selftest, report.
Os comandos de flow (flow01..export, rig, animate, benchmark) existem como
stubs que falham com mensagem explicita indicando a fase correspondente.

Uso:
    python -m chibi.cli <comando> [...]
    (ou ./chibi a partir da raiz do repositorio)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, config, paths, status as status_mod
from .validate import (
    gate_model_licensing,
    summarize,
    validate_character,
)

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_NOT_IMPLEMENTED = 3


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _echo(msg: str = "") -> None:
    print(msg)


def _header(title: str) -> None:
    _echo(f"\n{title}\n{'-' * len(title)}")


def _not_implemented(command: str, phase: str, depends_on: str = "") -> int:
    _echo(f"[NAO IMPLEMENTADO] '{command}' pertence a {phase}.")
    if depends_on:
        _echo(f"  Depende de: {depends_on}")
    _echo("  Fase 1 (fundacao) e o unico escopo entregue ate agora.")
    return EXIT_NOT_IMPLEMENTED


CHARACTER_YAML_TEMPLATE = """\
# Identidade canonica da personagem.
#
# REGRA: descreva o MINIMO necessario. Descricoes textuais de rosto/cabelo
# COMPETEM com as imagens de referencia e sao a causa nº1 de drift de
# identidade. Deixe a aparencia para reference/, use texto so para o que
# nao da para ver numa imagem.

id: {id}
display_name: "{display_name}"
created: "{created}"

# Por que esta personagem foi escolhida / quao dificil ela e (spec §26).
difficulty:
  rating: null        # 1-5, preencher manualmente
  reasons: []         # ex: [arma complexa, muitos acessorios, cabelo longo]

# Traços que NAO podem se perder. Usado como checklist humano de revisao,
# nao como prompt.
identity_anchors: []
# exemplo:
#   - heterocromia (olho direito ambar)
#   - fita vermelha no cabelo, lado esquerdo
#   - lanterna presa ao cinto

# Papeis de referencia disponiveis. Preenchido automaticamente pelo flow01.
reference_roles: {{}}

# Overrides dos recortes do identity kit, em fracoes da CAIXA DO SUJEITO
# (0.0 = topo/esquerda do sujeito, 1.0 = base/direita).
# Use quando o recorte heuristico do flow01 sair errado.
# Exemplo:
#   reference_regions:
#     face:
#       top: 0.03
#       bottom: 0.18
#       left: 0.25
#       right: 0.75
reference_regions: {{}}

# Overrides do rig padrao definido em config/project.yaml.
rig:
  parts: null         # null = usa o default do projeto
  extra_parts: []
  omit_parts: []

# Notas livres para a equipe.
notes: ""
"""


# ---------------------------------------------------------------------------
# comandos — Fase 1
# ---------------------------------------------------------------------------

def cmd_character_new(args: argparse.Namespace) -> int:
    cp = paths.CharacterPaths(args.id)
    if cp.exists():
        _echo(f"Personagem '{args.id}' ja existe em {cp.root}")
        return EXIT_FAIL

    for directory in cp.canonical_dirs():
        directory.mkdir(parents=True, exist_ok=True)
        gk = directory / ".gitkeep"
        if not any(directory.iterdir()):
            gk.touch()
    for anim in config.get("animation.defaults", {}):
        frames = cp.anim_frames(anim)
        frames.mkdir(parents=True, exist_ok=True)
        (frames / ".gitkeep").touch()

    cp.character_yaml.write_text(
        CHARACTER_YAML_TEMPLATE.format(
            id=args.id,
            display_name=args.name or args.id,
            created=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
        encoding="utf-8",
    )
    status_mod.init_file(cp.status_md, args.id)
    cp.work.mkdir(parents=True, exist_ok=True)

    _echo(f"Personagem criada: {cp.root.relative_to(paths.ROOT)}")

    copied = 0
    for src in args.source or []:
        s = Path(src)
        if not s.is_file():
            _echo(f"  aviso: source inexistente, ignorado: {s}")
            continue
        shutil.copy2(s, cp.source / s.name)
        copied += 1
    if copied:
        _echo(f"  {copied} arquivo(s) copiado(s) para source/ (originais intactos)")

    _echo("\nProximos passos:")
    _echo(f"  1. coloque a arte original em {cp.source.relative_to(paths.ROOT)}/")
    _echo(f"  2. preencha difficulty e identity_anchors em "
          f"{cp.character_yaml.relative_to(paths.ROOT)}")
    _echo(f"  3. rode: chibi validate {args.id}")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    _header(f"Validando personagem: {args.id}")
    results = validate_character(args.id)
    for r in results:
        _echo(str(r))
    passed, warns, errors = summarize(results)
    _echo(f"\n{passed} passou · {warns} aviso(s) · {errors} erro(s)")
    return EXIT_FAIL if errors else EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    cp = paths.CharacterPaths(args.id)
    if not cp.exists():
        _echo(f"Personagem '{args.id}' nao encontrada.")
        return EXIT_FAIL

    current = status_mod.read(cp.status_md)
    if not args.set:
        _header(f"Status: {args.id}")
        for i, state in enumerate(status_mod.STATES):
            mark = ">>" if state == current else ("  " if i > status_mod.index_of(current) else "ok")
            gated = "  (gate humano)" if state in status_mod.HUMAN_GATED else ""
            _echo(f"  {mark} {state}{gated}")
        return EXIT_OK

    try:
        status_mod.transition(
            cp.status_md, args.set, by=args.by, note=args.note or "", force=args.force
        )
    except status_mod.StatusError as exc:
        _echo(f"ERRO: {exc}")
        return EXIT_FAIL
    _echo(f"{args.id}: {current} -> {args.set} (por: {args.by})")
    return EXIT_OK


def cmd_models(args: argparse.Namespace) -> int:
    _header("Modelos registrados (config/models.lock.yaml)")
    lock = config.models_lock()
    _echo(f"  ultima revisao: {lock.get('last_reviewed', '?')}\n")

    for key, entry in lock.get("models", {}).items():
        com_ok, com_why = config.commercially_usable(key)
        tec_ok, tec_why = config.technically_usable(key)
        status = config.commercial_status(key)
        w_ok, w_why = config.weights_available(key)
        lic = entry.get("license", {}) or {}

        _echo(f"  {entry.get('display_name')}")
        _echo(f"     papel        : {entry.get('role')} | roda em: {entry.get('runs_on')}"
              f" | fase: {entry.get('required_for_phase', '?')}")
        _echo(f"     licenca      : {lic.get('spdx') or 'DESCONHECIDA'}")
        _echo(f"     uso tecnico  : {'LIBERADO' if tec_ok else 'BLOQUEADO'} — {tec_why}")

        rotulo = {
            "approved": "APROVADO",
            "pending_human_review": "PENDENTE DE REVISAO HUMANA",
            "unverified": "NAO VERIFICADO",
        }.get(status, status.upper())
        _echo(f"     uso comercial: {rotulo}")
        if not com_ok:
            _echo(f"                    -> {com_why}")
        if lic.get("source_url"):
            _echo(f"     fonte licenca: {lic.get('source_url')}")
        if rev := entry.get("revision"):
            _echo(f"     revision     : {rev}")
        _echo(f"     pesos        : {'baixados/conferidos' if w_ok else w_why}")
        if caveat := config.license_caveat(key):
            _echo(f"     [!] RESSALVA : {' '.join(caveat.split())[:200]}")
        _echo("")

    if rejected := lock.get("rejected", {}):
        _echo("  REJEITADOS:")
        for key, e in rejected.items():
            _echo(f"    - {e.get('display_name', key)}: {e.get('reason', '').strip()}")
        _echo("")
    if flagged := lock.get("flagged", {}):
        _echo("  SINALIZADOS (decisao juridica pendente):")
        for key, e in flagged.items():
            _echo(f"    - {e.get('display_name', key)}: {e.get('issue', '').strip()}")
    _echo("\nNenhum modelo foi baixado. Nenhum hash foi calculado.")
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    _header("ChibiCreate — relatorio")
    _echo(f"  versao da CLI: {__version__}")
    _echo(f"  raiz: {paths.ROOT}")

    chars = sorted(
        p.name for p in paths.CHARACTERS_DIR.iterdir()
        if p.is_dir() and (p / "character.yaml").is_file()
    ) if paths.CHARACTERS_DIR.is_dir() else []

    _echo(f"\n  personagens: {len(chars)}")
    if not chars:
        _echo("    (nenhuma — use 'chibi character new <id>')")
    for cid in chars:
        cp = paths.CharacterPaths(cid)
        state = status_mod.read(cp.status_md)
        results = validate_character(cid)
        _, warns, errors = summarize(results)
        flag = "ERRO" if errors else ("aviso" if warns else "ok")
        _echo(f"    - {cid:<24} {state:<18} [{flag}]")

    _echo("\n  fases implementadas: 1 (fundacao)")
    _echo("  fases pendentes: 2-8 (flows, rig, export, benchmark)")
    return EXIT_OK


def cmd_selftest(args: argparse.Namespace) -> int:
    """Checagem de sanidade da fundacao. Nao substitui os testes unitarios."""
    _header("Selftest")
    checks: list[tuple[str, bool, str]] = []

    for name, path in (
        ("config/project.yaml", paths.PROJECT_CONFIG),
        ("config/models.lock.yaml", paths.MODELS_LOCK),
        ("config/quality_gates.yaml", paths.QUALITY_GATES),
    ):
        checks.append((name, path.is_file(), str(path)))

    try:
        config.project()
        config.models_lock()
        config.quality_gates()
        checks.append(("configs parseadas", True, ""))
    except Exception as exc:  # noqa: BLE001
        checks.append(("configs parseadas", False, str(exc)))

    try:
        env = config.environment("local")
        checks.append(("environment local", env.get("name") == "local", ""))
    except Exception as exc:  # noqa: BLE001
        checks.append(("environment local", False, str(exc)))

    for mod_name in ("yaml", "PIL", "numpy"):
        try:
            __import__(mod_name)
            checks.append((f"dependencia {mod_name}", True, ""))
        except ImportError:
            checks.append((f"dependencia {mod_name}", False, "ausente"))

    for name, dirpath in (
        ("characters/", paths.CHARACTERS_DIR),
        ("styles/chibi/pose_bank/", paths.POSE_BANK_DIR),
        ("workflows/", paths.WORKFLOWS_DIR),
        ("work/", paths.WORK_DIR),
    ):
        checks.append((f"diretorio {name}", dirpath.is_dir(), str(dirpath)))

    ok = True
    for name, passed, detail in checks:
        _echo(f"  {'PASS' if passed else 'FAIL'}  {name}"
              + (f"  ({detail})" if detail and not passed else ""))
        ok = ok and passed

    _echo(f"\n{'Selftest OK' if ok else 'Selftest FALHOU'}")
    return EXIT_OK if ok else EXIT_FAIL


# ---------------------------------------------------------------------------
# fase 3A — comfyui e experimentos
# ---------------------------------------------------------------------------

def cmd_comfy(args: argparse.Namespace) -> int:
    """`chibi comfy status|validate` — o backend esta utilizavel?"""
    from . import comfy_client, experiment

    env_name = getattr(args, "env", None) or config.get(
        "runtime.default_environment", "local"
    )

    if args.subcommand == "status":
        _header(f"ComfyUI — ambiente '{env_name}'")
        try:
            client = comfy_client.ComfyClient.from_environment(env_name)
        except comfy_client.ComfyClientNotConfigured as exc:
            _echo(f"  NAO CONFIGURADO: {exc}")
            _echo("\n  Para apontar para um backend:")
            _echo("    export CHIBI_COMFY_URL=http://<host>:<porta>")
            _echo("    chibi comfy status --env cloud")
            return EXIT_FAIL

        _echo(f"  endereco : {client.base_url}")
        info = client.server_info()
        if not info.get("reachable"):
            _echo(f"  estado   : INACESSIVEL\n  erro     : {info.get('error')}")
            return EXIT_FAIL

        _echo("  estado   : ONLINE")
        _echo(f"  comfyui  : {info.get('comfyui_version')}")
        _echo(f"  pytorch  : {info.get('pytorch_version')}")
        for dev in info.get("devices", []):
            total = dev.get("vram_total") or 0
            free = dev.get("vram_free") or 0
            _echo(f"  device   : {dev.get('name')} "
                  f"({total / 1024**3:.1f} GB, livre {free / 1024**3:.1f} GB)")
        return EXIT_OK

    if args.subcommand == "preflight":
        from . import preflight

        _header(f"Preflight — ambiente '{env_name}'")
        report = preflight.run(env_name,
                               workflow_name=getattr(args, "workflow", None))

        if report.server.get("base_url"):
            _echo(f"  endereco : {report.server['base_url']}")
        for key, label in (("comfyui_version", "comfyui"),
                           ("pytorch_version", "pytorch"),
                           ("cuda_version", "cuda")):
            if value := report.server.get(key):
                _echo(f"  {label:9}: {value}")
        _echo("")

        marks = {preflight.OK: "OK  ", preflight.UNKNOWN: "?   "}
        for check in report.checks:
            mark = marks.get(check.status, "FALHA")
            _echo(f"  [{mark}] {check.name}: {check.status}")
            if check.detail:
                _echo(f"          {check.detail}")
            for mismatch in check.data.get("socket_mismatches", [])[:10]:
                _echo(f"            node    : {mismatch['workflow_node']}")
                _echo(f"            expected: {mismatch['expected']}")
                _echo(f"            actual  : {mismatch['actual']}")

        _echo("")
        if report.ready:
            _echo("  PRONTO para uma execucao real.")
            if report.unknowns:
                _echo(f"  ({len(report.unknowns)} item(ns) que o servidor nao "
                      "informou — ver '?' acima)")
            return EXIT_OK

        _echo(f"  NAO PRONTO — {len(report.blockers)} bloqueio(s):")
        for check in report.blockers:
            _echo(f"    - {check.status} em '{check.name}'")
        return EXIT_FAIL

    # validate
    wf_name = getattr(args, "workflow", None) or experiment.DEFAULT_WORKFLOW
    _header(f"Validando workflow: {wf_name}")
    try:
        workflow = experiment.load_workflow(wf_name)
    except experiment.ExperimentError as exc:
        _echo(f"  ERRO: {exc}")
        return EXIT_FAIL

    nodes = experiment.workflow_nodes(workflow)
    classes = sorted({n["class_type"] for n in nodes.values()})
    _echo(f"  JSON valido, {len(nodes)} nodes, {len(classes)} classes")
    for c in classes:
        _echo(f"    - {c}")

    try:
        client = comfy_client.ComfyClient.from_environment(env_name)
        available = client.object_info()
    except (comfy_client.ComfyClientNotConfigured, comfy_client.ComfyError) as exc:
        _echo(f"\n  [TEST REQUIRED] Nao foi possivel conferir contra um servidor:")
        _echo(f"    {exc}")
        _echo("  A estrutura do JSON esta ok, mas os nomes de node NAO foram")
        _echo("  verificados. Rode de novo com o ComfyUI acessivel.")
        return EXIT_OK

    missing = [c for c in classes if c not in available]
    if missing:
        _echo(f"\n  FALTAM {len(missing)} node(s) no servidor:")
        for c in missing:
            _echo(f"    - {c}")
        _echo("\n  Instale os pacotes correspondentes ou ajuste o workflow.")
        return EXIT_FAIL

    _echo("\n  Todos os nodes existem no servidor.")
    return EXIT_OK


def cmd_experiment(args: argparse.Namespace) -> int:
    """`chibi experiment qwen-edit` — execucao EXPERIMENTAL, nunca aprovada."""
    from . import experiment

    if args.subcommand == "compare":
        from pathlib import Path

        _header("Comparando execucoes")
        try:
            report = experiment.compare_runs(Path(args.run_a), Path(args.run_b))
        except experiment.ExperimentError as exc:
            _echo(f"  ERRO: {exc}")
            return EXIT_FAIL
        for key, value in report.items():
            _echo(f"  {key:22}: {value}")
        return EXIT_OK

    # `model-eval` amarra candidato -> model_key + workflow + ambiente, para
    # nao depender de tres flags coerentes digitadas a mao.
    eval_mode = args.subcommand == "model-eval"
    if eval_mode:
        candidate = experiment.MODEL_CANDIDATES.get(args.model)
        if candidate is None:
            _echo(f"  ERRO: candidato desconhecido '{args.model}'. "
                  f"Conhecidos: {', '.join(experiment.MODEL_CANDIDATES)}")
            return EXIT_FAIL
        model_key = candidate["model_key"]
        workflow_name = candidate["workflow"]
        env_name = getattr(args, "env", None) or candidate["environment"]
        _header(f"MODEL EVALUATION — {candidate['label']}: {args.character}")
    else:
        model_key = "qwen_image_edit_2511"
        workflow_name = experiment.DEFAULT_WORKFLOW
        env_name = getattr(args, "env", None)
        _header(f"EXPERIMENTO — qwen-edit: {args.character}")

    overrides: dict = {}
    for field_ in ("seed", "steps", "cfg", "sampler", "scheduler", "denoise"):
        if (value := getattr(args, field_, None)) is not None:
            overrides[field_] = value

    try:
        result = experiment.run_qwen_edit(
            args.character,
            input_rel=args.input,
            prompt=args.prompt,
            environment_name=env_name,
            model_key=model_key,
            workflow_name=workflow_name,
        workflow_version=getattr(args, "workflow_version", "v1"),
        extra_refs=tuple(getattr(args, "extra_refs", []) or ()),
            overrides=overrides,
            dry_run=getattr(args, "dry_run", False),
            eval_mode=eval_mode,
        )
    except experiment.ExperimentError as exc:
        _echo(f"  ERRO: {exc}")
        return EXIT_FAIL
    except Exception as exc:  # noqa: BLE001
        _echo(f"  ERRO ({type(exc).__name__}): {exc}")
        return EXIT_FAIL

    _echo(f"  run      : {result.run_id}")
    _echo(f"  diretorio: {result.run_dir.relative_to(paths.ROOT)}")
    _echo(f"  seed     : {result.params.get('seed')}")
    if result.output_path:
        _echo(f"  output   : {result.output_path.name}")
    _echo(f"  recipe   : {result.recipe_path.name}")
    for w in result.warnings:
        _echo(f"  aviso    : {w}")
    _echo("\n  [HUMAN REVIEW REQUIRED] Resultado marcado EXPERIMENTAL.")
    _echo("  Nao e Chibi Master e nao esta aprovado. Avaliacao artistica e humana.")
    return EXIT_OK


# ---------------------------------------------------------------------------
# stubs — fases 2..8
# ---------------------------------------------------------------------------

def cmd_flow01(args: argparse.Namespace) -> int:
    """FLOW 01 — character reference. Deterministico, roda 100% local."""
    from . import flow01

    _header(f"FLOW 01 — character reference: {args.id}")
    try:
        result = flow01.run(
            args.id, source_name=getattr(args, "source", None),
            force=getattr(args, "force", False),
        )
    except flow01.Flow01Error as exc:
        _echo(f"ERRO: {exc}")
        return EXIT_FAIL

    _echo(f"  fonte principal: {result.primary_source}")
    norm = result.metadata.get("normalization", {})
    if norm:
        _echo(f"  normalizacao   : escala {norm.get('scale')} -> canvas "
              f"{norm.get('canvas')} (sujeito {norm.get('subject_size')})")
    _echo(f"  alpha          : {result.metadata.get('alpha_origin')}")

    _echo("\n  Arquivos gerados:")
    for path in sorted(result.outputs):
        _echo(f"    {path.relative_to(paths.ROOT)}")

    if result.warnings:
        _echo("\n  Avisos:")
        for w in result.warnings:
            _echo(f"    - {w}")

    if result.human_review:
        _echo("")
        for item in result.human_review:
            _echo(f"  {item}")

    _echo("\n  Proximos passos:")
    _echo(f"    1. inspecione characters/{args.id}/reference/sheet.png")
    _echo(f"    2. rode: chibi validate {args.id}")
    _echo(f"    3. se aprovado: chibi status {args.id} --set REFERENCE_READY "
          f"--by <seu-nome>")
    return EXIT_OK


def cmd_flow02(a): return _not_implemented(
    "flow02", "FASE 3", "backend ComfyUI (config/environments/cloud.yaml) + "
    "Qwen-Image-Edit-2511 verificado em models.lock.yaml")


def cmd_approve(a): return _not_implemented(
    "approve", "FASE 4", "flow02 (candidatos + contact sheet)")


def cmd_flow03(a): return _not_implemented(
    "flow03", "FASE 5", "Chibi Master aprovado + pose_bank populado")


def cmd_rig(a): return _not_implemented("rig", "FASE 6", "Chibi Master aprovado")


def cmd_animate(a): return _not_implemented("animate", "FASE 6", "rig")


def cmd_export(a): return _not_implemented("export", "FASE 7", "animate")


def cmd_benchmark(a): return _not_implemented(
    "benchmark", "FASE 8", "export + projeto Godot")


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def experiment_candidates() -> dict:
    """Candidatos de modelo, importados tarde para o parser seguir barato."""
    from .experiment import MODEL_CANDIDATES

    return MODEL_CANDIDATES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chibi",
        description="ChibiCreate — pipeline de arte IA (MVP v0.1, Fase 1)",
    )
    parser.add_argument("--version", action="version", version=f"chibi {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # character
    p_char = sub.add_parser("character", help="gerenciar personagens")
    char_sub = p_char.add_subparsers(dest="subcommand", required=True)
    p_new = char_sub.add_parser("new", help="criar estrutura de uma personagem")
    p_new.add_argument("id")
    p_new.add_argument("--name", help="nome de exibicao")
    p_new.add_argument("--source", nargs="*", help="arquivos de arte original a copiar")
    p_new.set_defaults(func=cmd_character_new)

    p_val = sub.add_parser("validate", help="rodar quality gates tecnicos")
    p_val.add_argument("id")
    p_val.set_defaults(func=cmd_validate)

    p_st = sub.add_parser("status", help="ver ou alterar o estado da personagem")
    p_st.add_argument("id")
    p_st.add_argument("--set", choices=status_mod.STATES, help="nova transicao")
    p_st.add_argument("--by", default="agent", help="quem executou (humano p/ gates de arte)")
    p_st.add_argument("--note", help="observacao")
    p_st.add_argument("--force", action="store_true", help="pular checagem de ordem")
    p_st.set_defaults(func=cmd_status)

    p_mod = sub.add_parser("models", help="listar modelos e situacao de licenca")
    p_mod.set_defaults(func=cmd_models)

    p_rep = sub.add_parser("report", help="visao geral do projeto")
    p_rep.set_defaults(func=cmd_report)

    p_self = sub.add_parser("selftest", help="checagem de sanidade da fundacao")
    p_self.set_defaults(func=cmd_selftest)

    p_f1 = sub.add_parser("flow01", help="character reference (deterministico, local)")
    p_f1.add_argument("id")
    p_f1.add_argument("--source", help="nome do arquivo em source/ a usar como principal")
    p_f1.add_argument("--force", action="store_true", help="sobrescrever reference/")
    p_f1.set_defaults(func=cmd_flow01)

    # fase 3A — comfyui
    p_comfy = sub.add_parser("comfy", help="backend ComfyUI")
    comfy_sub = p_comfy.add_subparsers(dest="subcommand", required=True)
    p_cs = comfy_sub.add_parser("status", help="o servidor esta acessivel?")
    p_cs.add_argument("--env", help="ambiente (default: config/project.yaml)")
    p_cs.set_defaults(func=cmd_comfy)
    p_pf = comfy_sub.add_parser(
        "preflight", help="tudo pronto para executar? (nao usa GPU)")
    p_pf.add_argument("--env")
    p_pf.add_argument("--workflow")
    p_pf.set_defaults(func=cmd_comfy)
    p_cv = comfy_sub.add_parser("validate", help="conferir nodes do workflow")
    p_cv.add_argument("--env")
    p_cv.add_argument("--workflow", help="ex: experimental/qwen_edit_minimal")
    p_cv.set_defaults(func=cmd_comfy)

    # fase 3A — experimentos
    p_exp = sub.add_parser("experiment", help="execucoes experimentais")
    exp_sub = p_exp.add_subparsers(dest="subcommand", required=True)
    p_qe = exp_sub.add_parser("qwen-edit", help="edicao experimental via Qwen")
    p_qe.add_argument("--character", required=True)
    p_qe.add_argument("--input", default="reference/full_body.png")
    p_qe.add_argument("--prompt", required=True,
                      help="o que MUDAR. Nao descrever rosto/cabelo.")
    p_qe.add_argument("--env")
    p_qe.add_argument("--seed", type=int)
    p_qe.add_argument("--steps", type=int)
    p_qe.add_argument("--cfg", type=float)
    p_qe.add_argument("--sampler")
    p_qe.add_argument("--scheduler")
    p_qe.add_argument("--denoise", type=float)
    p_qe.add_argument("--dry-run", action="store_true", dest="dry_run",
                      help="resolver workflow e recipe sem chamar o servidor")
    p_qe.set_defaults(func=cmd_experiment)

    # FASE 3B = MODEL EVALUATION: mesmo experimento, candidatos diferentes.
    p_me = exp_sub.add_parser(
        "model-eval",
        help="avaliar um candidato (mesmo input/prompt/seed para todos)")
    p_me.add_argument("--model", required=True,
                      choices=sorted(experiment_candidates()),
                      help="candidato a avaliar")
    p_me.add_argument("--character", required=True)
    p_me.add_argument("--input", default="reference/full_body.png")
    p_me.add_argument("--ref", action="append", default=[], dest="extra_refs",
                      metavar="REL",
                      help="referencia ADICIONAL (repetivel). Exige workflow "
                           "multi-referencia. Ex: --ref reference/face.png")
    p_me.add_argument("--workflow-version", default="v1",
                      dest="workflow_version",
                      help="versao do workflow (v2 = multi-referencia)")
    p_me.add_argument("--prompt", required=True,
                      help="o que MUDAR. Nao descrever rosto/cabelo.")
    p_me.add_argument("--env", help="sobrepoe o ambiente do candidato")
    p_me.add_argument("--seed", type=int)
    p_me.add_argument("--steps", type=int)
    p_me.add_argument("--cfg", type=float)
    p_me.add_argument("--sampler")
    p_me.add_argument("--scheduler")
    p_me.add_argument("--denoise", type=float)
    p_me.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_me.set_defaults(func=cmd_experiment)

    p_cmp = exp_sub.add_parser("compare", help="comparar duas execucoes")
    p_cmp.add_argument("run_a")
    p_cmp.add_argument("run_b")
    p_cmp.set_defaults(func=cmd_experiment)

    # stubs
    for name, func, helptext in (
        ("flow02", cmd_flow02, "[fase 3] chibi master (candidatos)"),
        ("approve", cmd_approve, "[fase 4] aprovacao humana"),
        ("flow03", cmd_flow03, "[fase 5] poses"),
        ("rig", cmd_rig, "[fase 6] decomposicao em partes"),
        ("animate", cmd_animate, "[fase 6] idle / walk"),
        ("export", cmd_export, "[fase 7] spritesheet + Godot"),
        ("benchmark", cmd_benchmark, "[fase 8] teste de performance"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("id", nargs="?")
        p.add_argument("args", nargs="*")
        p.set_defaults(func=func)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _echo("\ninterrompido")
        return 130
    except Exception as exc:  # noqa: BLE001
        _echo(f"ERRO: {type(exc).__name__}: {exc}")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())

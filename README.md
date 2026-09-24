# ChibiCreate

Pipeline de geração e preparação de arte com IA para um jogo 2D comercial em
Godot, inspirado no modelo de gameplay de Vampire Survivors.

Transforma splash arts / concept arts de personagens em **sprites chibi
animados**, preservando a identidade visual de cada personagem e mantendo uma
linguagem chibi consistente entre todas.

> **Estado: MVP v0.1 — FASE 1 (fundação) implementada.**
> Os flows 01–05 ainda não existem. Seus comandos falham com mensagem explícita
> indicando a fase correspondente.

---

## Princípio

```
IDENTIDADE > CONSISTÊNCIA > REPRODUTIBILIDADE > AUTOMAÇÃO > ESCALA
```

O objetivo não é gerar 100 personagens rápido. É gerar 100 personagens **sem
que a identidade delas se degrade**.

---

## Início rápido

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

./chibi selftest                    # sanidade da fundação
./chibi models                      # situação de licença dos modelos
./chibi character new waifu_001 --name "Nome" --source ./arte/*.png
./chibi validate waifu_001
./chibi report
```

---

## Comandos

| Comando | Fase | Situação |
|---|---|---|
| `chibi character new <id>` | 1 | ✅ |
| `chibi validate <id>` | 1 | ✅ |
| `chibi status <id> [--set ...]` | 1 | ✅ |
| `chibi models` | 1 | ✅ |
| `chibi report` | 1 | ✅ |
| `chibi selftest` | 1 | ✅ |
| `chibi flow01 <id>` | 2 | ⛔ stub |
| `chibi flow02 <id> --candidates 8` | 3 | ⛔ stub |
| `chibi approve <id> chibi --pick <n>` | 4 | ⛔ stub |
| `chibi flow03 <id> --pose <pose>` | 5 | ⛔ stub |
| `chibi rig <id>` / `chibi animate <id>` | 6 | ⛔ stub |
| `chibi export <id> --target godot` | 7 | ⛔ stub |
| `chibi benchmark` | 8 | ⛔ stub |

---

## Arquitetura

```
SOURCE → FLOW 01 reference → FLOW 02 chibi master → [APROVAÇÃO HUMANA]
       → FLOW 03 pose → rig/cutout → idle + walk
       → FLOW 05 export → Godot → benchmark
```

- **Motor de identidade:** modelo de edição multi-referência (candidato:
  Qwen-Image-Edit-2511, Apache 2.0) — ver [ADR-001](docs/decisions/ADR-001-qwen-image-edit.md)
- **Animação:** rig cutout a partir do Master aprovado, **não** geração de
  frames por IA — ver [ADR-002](docs/decisions/ADR-002-animation-strategy.md)
- **Orquestração:** ComfyUI como executor; **Git como fonte da verdade** —
  ver [ADR-003](docs/decisions/ADR-003-comfyui-orchestration.md)

---

## Gates humanos

O agente **pode**: validar, gerar candidatos, montar contact sheets, executar
workflows, calcular hashes, gerar recipes, montar spritesheets, criar arquivos
Godot, abrir PRs.

O agente **não pode**: escolher qual arte é melhor, aprovar o Chibi Master,
decidir que algo "está bonito", alterar a personagem artisticamente.

Isso é imposto em código — `Recipe.approve()` recusa `by="agent"`, e a
transição para `CHIBI_APPROVED` exige `by=human`.

---

## Licenciamento

Projeto **comercial**. Nenhum modelo entra na pipeline sem licença verificada e
registrada em [`LICENSES.md`](LICENSES.md) e
[`config/models.lock.yaml`](config/models.lock.yaml).

`chibi models` recusa qualquer modelo que não esteja `verified` — no momento,
**todos os quatro candidatos**. Isso é intencional.

> A pipeline **não baixa modelos automaticamente**.

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/pipeline.md`](docs/pipeline.md) | Guia operacional completo |
| [`docs/research/`](docs/research/) | Relatório de pesquisa técnica |
| [`docs/decisions/`](docs/decisions/) | ADRs |
| [`LICENSES.md`](LICENSES.md) | Conformidade de licenças |

---

## Estrutura

```
config/          project.yaml, models.lock.yaml, quality_gates.yaml, environments/
styles/chibi/    style.yaml, pose_bank/ (GLOBAL), references/{chibi,splash}/
characters/<id>/ character.yaml, STATUS.md, source/, reference/, chibi/,
                 poses/, animation/, rig/, export/
workflows/       templates ComfyUI versionados, por flow
scripts/chibi/   CLI e módulos
work/            ⛔ gitignored — candidatos e temporários
tests/           testes da fundação
```

**CANONICAL vs TEMPORARY:** se foi aprovado, é canônico e tem recipe
obrigatória. Se não foi, mora em `work/` e pode sumir sem perda.

---

## Testes

```bash
./.venv/bin/python tests/test_foundation.py     # 25 testes
```

---

## Avisos conhecidos

- ⚠️ **git-lfs não está instalado.** As regras existem em `.gitattributes`, mas
  só valem após `git lfs install`. Faça isso **antes** de commitar a primeira
  arte pesada.
- ⚠️ **Resolução de gameplay não decidida** (`resolution.gameplay_output.display_height: null`).
  Depende da resolução alvo do jogo e do teste de legibilidade 64/96/128 px.
- ⚠️ **Licença de `Qwen-Image-ControlNet-Union` não confirmada.**
- ⚠️ **RX 580 (Polaris/gfx803) não roda a inferência pesada** — AMD removeu o
  suporte no ROCm 5.x. Inferência vai para GPU cloud.

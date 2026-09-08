# ChibiCreate — Pipeline

Documentação operacional do pipeline de arte IA.

**Estado atual: FASE 1 (fundação) implementada.** Os flows 01–05 ainda não
existem — seus comandos na CLI falham com mensagem explícita indicando a fase.

---

## Índice

- [Princípio](#princípio)
- [Fluxo geral](#fluxo-geral)
- [Pré-requisitos](#pré-requisitos)
- [Setup](#setup)
- [Execução local vs cloud](#execução-local-vs-cloud)
- [Como criar uma personagem](#como-criar-uma-personagem)
- [Como aprovar arte](#como-aprovar-arte)
- [Como gerar poses](#como-gerar-poses)
- [Como gerar animações](#como-gerar-animações)
- [Como exportar para Godot](#como-exportar-para-godot)
- [Como adicionar um modelo](#como-adicionar-um-modelo)
- [Como atualizar um modelo](#como-atualizar-um-modelo)
- [Como atualizar um workflow](#como-atualizar-um-workflow)
- [Resolução](#resolução)
- [Estados da personagem](#estados-da-personagem)
- [Estrutura do repositório](#estrutura-do-repositório)

---

## Princípio

```
IDENTIDADE > CONSISTÊNCIA > REPRODUTIBILIDADE > AUTOMAÇÃO > ESCALA
```

O objetivo não é gerar 100 personagens rápido. É gerar 100 personagens **sem
que a identidade delas se degrade**. Prove 1 → prove 3 → prove 10 → automatize.

---

## Fluxo geral

```
SOURCE ART  (splash / concept, imutável)
    │
    ▼  FLOW 01 — CHARACTER REFERENCE                        [FASE 2]
       recorte, normalização, identity kit, palette, sheet
    │
    ▼  FLOW 02 — CHIBI MASTER                               [FASE 3]
       N candidatos + contact sheet
    │
    ▼  APROVAÇÃO HUMANA                                     [FASE 4]
       ⛔ o agente não escolhe, não aprova
    │
    ▼  FLOW 03 — POSE                                       [FASE 5]
       Master + pose bank global
    │
    ▼  RIG / CUTOUT                                         [FASE 6]
       decomposição em partes reutilizável
    │
    ▼  IDLE (4 frames) + WALK (6 frames)                    [FASE 6]
    │
    ▼  FLOW 05 — EXPORT                                     [FASE 7]
       spritesheet + atlas + pivots + SpriteFrames.tres
    │
    ▼  GODOT + BENCHMARK                                    [FASE 8]
       200 / 500 / 1000 instâncias
```

---

## Pré-requisitos

| Requisito | Situação | Nota |
|---|---|---|
| Python 3.11+ | ✅ | |
| PyYAML, Pillow, numpy | ✅ (venv) | |
| Git | ✅ | |
| **git-lfs** | ❌ **não instalado** | Necessário **antes** de commitar arte pesada |
| Backend ComfyUI | ❌ não configurado | Necessário na FASE 3 |
| Godot 4.x | ❌ não verificado | Necessário na FASE 8 |

> ⚠️ **git-lfs.** As regras já estão em `.gitattributes`, mas só têm efeito após
> `git lfs install`. Rode isso antes de adicionar a primeira splash art, ou
> binários grandes entram no histórico do Git como blobs comuns — e tirá-los
> depois exige reescrever o histórico.

---

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install pyyaml pillow numpy

./chibi selftest      # confirma que a fundação está sã
./chibi --version
```

O script `./chibi` usa `.venv` automaticamente se existir.

---

## Execução local vs cloud

Configurado em `config/environments/`.

### local (`local.yaml`)

Hardware: Ryzen 5 5500 / RX 580 8 GB / 16 GB RAM.

**Fato:** a AMD removeu Polaris/GCN4 (gfx803) do ROCm na v5.x. ComfyUI +
ControlNet + Qwen-Edit **não** são considerados executáveis de forma confiável
nesta GPU.

Serve para: CLI, validação, scripts de imagem, Real-ESRGAN (Vulkan/ncnn),
rigging, Godot, retoque, GUI do ComfyUI apontando para backend remoto.

### cloud (`cloud.yaml`)

Serve para: Qwen-Image-Edit-2511, ControlNet, geração de candidatos, treino de
LoRA (fase futura). Mínimo ~24 GB de VRAM.

Credenciais **nunca** em arquivo — apenas variáveis de ambiente:

```bash
export CHIBI_COMFY_URL=https://...
export CHIBI_COMFY_TOKEN=...
```

---

## Como criar uma personagem

```bash
./chibi character new waifu_001 --name "Nome" --source ./arte/*.png
./chibi validate waifu_001
```

Depois, **manualmente**, preencha em `characters/waifu_001/character.yaml`:

- `difficulty.rating` e `difficulty.reasons`
- `identity_anchors` — traços que **não podem** se perder

> **Regra de identidade:** descreva o mínimo. Descrições textuais de rosto e
> cabelo **competem** com as imagens de referência e são a causa nº 1 de drift.
> `identity_anchors` é checklist humano de revisão, **não** prompt.

### Escolha da personagem do MVP

Use a **mais difícil** disponível: mais acessórios, roupa complexa, cabelo
complexo, arma complexa, silhueta difícil. Validar com a mais fácil é
auto-engano.

---

## Como aprovar arte

`[FASE 4 — não implementado]`

```bash
./chibi flow02 waifu_001 --candidates 8    # gera candidatos + contact sheet
# → humano inspeciona work/waifu_001/candidates/contact_sheet.png
./chibi approve waifu_001 chibi --pick 3 --by "seu-nome"
```

**O agente não pode:** escolher qual arte é melhor, aprovar o Chibi Master,
decidir que algo "está bonito", remover acessórios por achar que ficaram ruins,
alterar a personagem artisticamente.

Isso é imposto em código: `Recipe.approve()` recusa `by="agent"`, e a transição
para `CHIBI_APPROVED` exige `by=human`.

---

## Como gerar poses

`[FASE 5 — não implementado]`

```bash
./chibi flow03 waifu_001 --pose walk_00
```

O pose bank em `styles/chibi/pose_bank/` é **global**. Uma pose é criada uma vez
e reutilizada por N personagens.

---

## Como gerar animações

`[FASE 6 — não implementado]`

```bash
./chibi rig waifu_001
./chibi animate waifu_001 --anim idle
./chibi animate waifu_001 --anim walk
```

Estratégia: cutout a partir do Master aprovado (ADR-002). O artwork aprovado é
preservado exatamente.

---

## Como exportar para Godot

`[FASE 7 — não implementado]`

```bash
./chibi export waifu_001 --target godot
```

Gera automaticamente: frames, spritesheet, atlas metadata, pivots,
`SpriteFrames.tres`. Não deve exigir montagem manual no editor.

No Godot: `AnimatedSprite2D` como padrão; `AnimationPlayer` onde houver
sincronização de hitbox/SFX/eventos; `AnimationTree` só com necessidade real de
blending. Nunca os dois controlando o mesmo atributo visual.

---

## Como adicionar um modelo

Ver procedimento completo em [`LICENSES.md`](../LICENSES.md).

Resumo: ler a licença **no card oficial** → registrar em
`config/models.lock.yaml` como `candidate` → baixar **manualmente** → calcular
sha256 → preencher licença e `verified_on` → mudar para `verified`.

```bash
./chibi models     # mostra situação de licença de todos
```

Enquanto não estiver `verified`, o modelo é reportado como **não liberado para
produção comercial**. Isso é intencional.

> A pipeline **não baixa modelos automaticamente**, por decisão de projeto.

---

## Como atualizar um modelo

1. Nova entrada ou nova `revision` em `models.lock.yaml` — **não** sobrescrever
   a antiga se houver recipe aprovada apontando para ela.
2. Recalcular hash, reverificar licença, atualizar `verified_on`.
3. Assets já aprovados **não** são regerados automaticamente. Suas recipes
   apontam para a versão antiga, e isso é correto.

---

## Como atualizar um workflow

1. Criar `v2.json` ao lado de `v1.json`. **Nunca** editar um template já
   referenciado por recipe aprovada.
2. Atualizar o template usado por padrão na configuração do flow.
3. Recipes antigas continuam apontando para `v1.json` com seu hash — é assim
   que a rastreabilidade sobrevive à evolução.

---

## Resolução

Nada congelado. Tudo em `config/project.yaml → resolution`.

| Asset | Trabalho | Nota |
|---|---|---|
| Source | nativo | imutável |
| Chibi Master | 1024² (ou 1536²) | canvas quadrado fixo |
| Frames de animação | ~512 px de altura | |
| Gameplay | `display_height × integer_factor` | ⚠️ `display_height` **não decidido** |
| Menu/UI | 512–1024 | |

**Regra de ouro:** um único downscale, no fim, com filtro adequado. Downscales
encadeados destroem line art.

O MVP deve emitir a comparação em **64 / 96 / 128 px** para avaliação humana
antes de congelar qualquer número.

`[TEST REQUIRED]` Falta decidir: resolução alvo do jogo e altura do sprite em
tela.

---

## Estados da personagem

```
SOURCE → REFERENCE_READY → CHIBI_CANDIDATES → CHIBI_APPROVED
       → POSES_READY → RIG_READY → ANIMATION_READY
       → EXPORT_READY → GODOT_VALIDATED
```

`CHIBI_APPROVED` exige `by=human`. Registrado em `characters/<id>/STATUS.md`.

```bash
./chibi status waifu_001
./chibi status waifu_001 --set REFERENCE_READY --by agent --note "flow01 ok"
```

---

## Estrutura do repositório

```
config/          project.yaml, models.lock.yaml, quality_gates.yaml, environments/
styles/chibi/    style.yaml, pose_bank/ (GLOBAL), reference_sheets/
characters/<id>/ character.yaml, STATUS.md, source/, reference/, chibi/,
                 poses/, animation/, rig/, export/
workflows/       templates ComfyUI versionados, por flow
scripts/chibi/   CLI e módulos
work/            ⛔ gitignored — candidatos e temporários
docs/            research/, decisions/ (ADRs), pipeline.md
tests/           testes da fundação
```

**CANONICAL vs TEMPORARY:** se foi aprovado, é canônico e tem recipe
obrigatória. Se não foi, mora em `work/` e pode sumir sem perda.

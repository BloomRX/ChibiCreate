# Pose transfer — mannequin → chibi animada (EXPERIMENTAL)

**ADR-007.** Estratégia **(A)** do ADR-002, que foi descartada para produção
por drift e flicker. Este documento não a promove a rota oficial: o **rig
cutout** continua sendo a estratégia primária.

## Fluxo

```
Blender (rig Mixamo, proporção corrigida)
   └─> walk_00.png … walk_05.png          frames de pose
                    │
       upload ──────┤
                    ├─> [validação: canvas, pivot, alfa]   ← para se inválido
                    │
   chibi master ────┘
   (upload)
                    └─> FLUX.2 klein + ReferenceLatent
                            1 execução por frame
                                  │
                                  └─> frames + sheet + GIF 64/96/128 px
                                            │
                                            └─> [HUMAN REVIEW REQUIRED]
```

## O que o notebook NÃO faz, de propósito

| Não faz | Porquê |
|---|---|
| Corrigir proporção humana → chibi | Esconderia a causa real da falha. Corrija no Blender. |
| Declarar sucesso ou escolher parâmetro vencedor | Avaliação é humana (ADR-002, regra do projeto). |
| Usar o delta entre frames como nota de qualidade | Métrica de movimento ≠ métrica de beleza. |
| Adicionar ControlNet automaticamente | Exige modelo novo em `models.lock.yaml` e decisão humana. |
| Alterar o pipeline oficial ou os notebooks anteriores | Linha experimental separada, como foi o inpaint. |

## Modo de falha previsto

O ADR-002 prevê **cintilação entre frames**. Ela é **invisível frame a
frame** — cada quadro isolado parece bom, e o defeito só aparece no loop, na
escala real de exibição. Por isso a célula 8 gera GIF em 64/96/128 px, e não
apenas a grade de frames.

Sintomas a procurar no loop: franja que muda de forma, chifre que encolhe,
contorno que "ferve", cor que oscila de um quadro para o outro.

## Modos de pose (dropdown `POSE_INPUT_MODE`)

Todos usam o **mesmo checkpoint**. Muda só a imagem que entra no slot de pose
— e, no último, uma LoRA. Compare **um fator de cada vez**.

| Modo | Sinal de controle | Custo extra |
|---|---|---|
| `render_direto` | render cinza do mannequin | nenhum |
| `dwpose_skeleton` | esqueleto DWPose | custom node |
| `depth_map` | mapa de profundidade | custom node |
| `depth_map_lora` | depth + RefControl LoRA | custom node + 92 MB |

Cada modo grava ZIP, sheet e GIF com o nome do modo, para não sobrescrever os
anteriores.

### Por que o esqueleto tende a ser melhor para chibi

O render sólido carrega **proporção humana e volume de adulto** — exatamente o
que contamina a chibi. Um esqueleto carrega **só articulação**. Como observado
na comunidade: sem elementos visuais extras na imagem de pose, o modelo não
reproduz detalhes indesejados dela.

`[TEST REQUIRED]` — hipótese, não fato medido.

## Por que NÃO há opção "ControlNet"

Pesquisa em 2026-09-19: **não existe ControlNet dedicado para FLUX.2 klein
4B**. O que existe não serve:

| Opção | Base | Impedimento |
|---|---|---|
| InstantX Union, XLabs | FLUX.1 dev | base errada |
| Alibaba Fun ControlNet Union | FLUX.2 dev | base errada |
| RefControl pose/lineart/canny/normal | klein **9B** | **licença não-comercial** |
| RefControl depth | klein **4B** | ✓ único viável |

A 9B é não-comercial por decisão da própria BFL, já registrada em
`models.lock.yaml`. As LoRAs de **pose** da família RefControl só existem para
9B — por isso o modo com LoRA usa **depth**, não pose.

Oferecer um modo "ControlNet" seria criar dropdown com opção inexistente.

## Risco da LoRA: `base_mismatch`

A RefControl declara base `FLUX.2-klein-base-4B` — a variante **não
destilada**. O pipeline usa `flux-2-klein-4b.safetensors`, a **destilada**.
São pesos diferentes.

Aplicar LoRA na base errada normalmente **degrada em silêncio**: gera imagem
plausível com aderência fraca e **nenhum erro**. Se `depth_map_lora` render
pouco, a causa pode ser esta, não a técnica. Registrado como
`base_mismatch: true` no lock e impresso no notebook.

`[TEST REQUIRED]`

## Limitação técnica conhecida

`ReferenceLatent` **não é ControlNet**. A pose do mannequin *influencia* a
geração; não a *trava*. Aderência frouxa é resultado esperado e deve ser
reportada, nunca compensada em silêncio.

Se a aderência for insuficiente, o passo seguinte é ControlNet/OpenPose real
— decisão humana, modelo novo, entrada em `models.lock.yaml`.

## Risco de proporção

Mannequin do Mixamo: ~7 cabeças. Chibi: ~2–3. Se o frame de pose chegar em
proporção humana, o resultado tende a personagem alongada ou cabeça grande em
corpo adulto. Mitigação em `styles/chibi/pose_bank/mannequin/README.md`:
corrigir no Blender, encurtando membros e aumentando a cabeça, **preservando
o arco e o timing** da caminhada — que é o que se está aproveitando do Mixamo.

## Licença do mannequin

Mixamo (Adobe), verificado em 2026-09-19: uso comercial livre, sem
atribuição. **Proibido** redistribuir arquivos brutos (FBX, rig, keyframes) e
**proibido** usar o conteúdo para treinar modelos de ML.

Este repo versiona **apenas PNG renderizado** e **não treina nada**
(`style.lora.enabled: false`). Registrado em
`styles/chibi/pose_bank/mannequin/mannequin.metadata.json` e replicado no
`recipe.json` de cada execução, separado da licença do FLUX.

## Saída

`{character}_{anim}_pose_transfer.zip`:

```
frames/        frames gerados
pose_input/    frames do mannequin usados
loop/          GIFs 64/96/128 px  ← avalie AQUI
{id}_{anim}_sheet.png
input/         chibi e referência
recipe.json    inclui workflow_sha256, pixel sha, licença, seed por frame
workflow.resolved.json
RELATORIO.md
```

## Aproveitamento em caso de falha

Se (A) for reprovada, os sheets de mannequin **não se perdem**: servem como
referência de pose para o rig cutout da rota B, que o ADR-002 define como
primária. O trabalho no Blender é útil nos dois cenários.

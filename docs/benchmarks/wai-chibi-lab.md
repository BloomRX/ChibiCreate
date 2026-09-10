# WAI CHIBI EXPERIMENT LAB

Laboratório de configurações para converter uma personagem real em chibi
com o WAI-illustrious-SDXL. Substitui o benchmark fixo `Run 001/002/003`:
em vez de runs numeradas criadas à mão, a **célula 0** define uma
configuração e o notebook executa automaticamente os dois modos de
referência para ela.

> **Não é pipeline oficial.** O benchmark FLUX, o Flow 01, os
> quality gates e o design-transfer não foram tocados.

## Caminho estrutural (fixo)

```
full_body.png → LoadImage → VAEEncode → latent_image → KSampler → VAEDecode
```

O IP-Adapter atua **adicionalmente sobre o MODEL**, nunca substituindo o
latente. **Não existe `EmptyLatentImage` neste lab.**

Isso diverge de propósito do guia externo do SeaArt, que usa
`EmptyLatentImage` + `denoise 1.0` — ou seja, txt2img + IP-Adapter. Aquilo
gera uma personagem nova guiada por referência; nós precisamos transformar
*esta* personagem, preservando design.

## Os dois modos

### 1 REF — `v3.json`, 12 nodes

```
[4] LoadImage(full_body) ─┬─→ [5] VAEEncode ────────────→ latent ─┐
                          │                                       │
                          └─→ [12] IPAdapterEncoder ─┐            │
[10] IPAdapterModelLoader ───────────────────────────┤            │
[11] CLIPVisionLoader ───────────────────────────────┘            │
                                       │                          │
                    [20] IPAdapterEmbeds (pos :0, neg :1)          │
                                       │                          │
                              MODEL → [40] KSampler ←─────────────┘
```

Sem `CombineEmbeds`: com uma referência só, o Encoder alimenta o
`IPAdapterEmbeds` direto.

### 3 REFS — `v2.json`, 18 nodes

O ramo do latente é **idêntico**. Muda só o MODEL:

```
[12] Encoder(full_body, w=1.0) ─┐
[13] Encoder(face,      w=0.6) ─┼─→ [15] CombineEmbeds POS (saídas :0)
[14] Encoder(outfit,    w=0.8) ─┼─→ [16] CombineEmbeds NEG (saídas :1)
                                 │            │
                    [20] IPAdapterEmbeds ←────┘
                                 │
                    MODEL → [40] KSampler
```

São **dois** `CombineEmbeds` porque o Encoder devolve embed positivo na
saída 0 e negativo na saída 1. Combinar só os positivos deixaria o negativo
de uma única referência.

Como o ramo do latente é igual nos dois modos, comparar 1 REF × 3 REFS
**isola o efeito das referências extras**.

### `full_body.png` tem papel duplo nos DOIS modos

1. imagem inicial do img2img (`VAEEncode`);
2. referência visual do IP-Adapter (`IPAdapterEncoder`).

Intencional, registrado no recipe como `reference_roles`.

## Parâmetros da célula 0

| grupo | parâmetro | inicial |
|---|---|---|
| entradas | `CHARACTER_ID`, `SOURCE_IMAGE`, `REFERENCE_FACE`, `REFERENCE_OUTFIT` | `waifu_001`, `full_body.png`, `face.png`, `outfit.png` |
| modo | `REFERENCE_MODE` | `BOTH` |
| prompt | `PROMPT_PRESET` | `chibi_v1` |
| denoise | `DENOISE` · `USAR_SWEEP_DE_DENOISE` · `DENOISE_SWEEP` | `0.90` · `False` · `0.50…0.90` |
| sampling | `STEPS` · `CFG` · `SAMPLER` · `SCHEDULER` · `SEED` | `28` · `5.5` · `euler_ancestral` · `normal` · `42` |
| IP-Adapter | `IPADAPTER_WEIGHT` · `WEIGHT_TYPE` · `START_AT` · `END_AT` · `EMBEDS_SCALING` | `0.75` · `linear` · `0.0` · `1.0` · `V only` |
| multi-ref | `FULL_BODY_WEIGHT` · `FACE_WEIGHT` · `OUTFIT_WEIGHT` · `COMBINE_METHOD` | `1.0` · `0.6` · `0.8` · `concat` |
| rótulo | `EXPERIMENT_LABEL` | automático |

`REFERENCE_MODE = "BOTH"` executa 1 REF e 3 REFS para a mesma configuração.

O sweep de denoise existe mas vem **desligado**: ligado, multiplica as
execuções (5 valores × 2 modos = 10 gerações).

## Validação antes de executar

A célula 8 bloqueia com `BLOCKED` se algo não bater:

1. nodes necessários presentes no `/object_info`;
2. `SAMPLER`/`SCHEDULER` existem no `KSampler` **daquele** servidor;
3. `WEIGHT_TYPE`, `EMBEDS_SCALING`, `COMBINE_METHOD` existem no node instalado;
4. `start_at`/`end_at`/`weight` existem no `IPAdapterEmbeds` — se não
   existirem, o painel avisa em vez de fingir que o controle funciona;
5. em cada grafo: sem `EmptyLatentImage`, latente vindo de `full_body`,
   MODEL condicionado pelo IP-Adapter, papel duplo, número de referências
   e placeholders batendo com o modo.

`denoise < 1.0` e `START_AT < END_AT` são barrados já na célula 0.

**Nada degrada em silêncio para menos referências.**

## Estrutura de saída

```
experiments/wai_chibi_lab/experiment_YYYYMMDD_HHMMSS/
├── config.json
├── 1_ref/{output.png, recipe.json, workflow.resolved.json, metadata.json, logs/}
├── 3_ref/{output.png, recipe.json, workflow.resolved.json, metadata.json, logs/}
├── comparison.png
└── comparison.json
```

Com sweep, os diretórios viram `1_ref_d0.50`, `1_ref_d0.60`, etc.
Experimentos **nunca são sobrescritos**: se o diretório existir, bloqueia.

## Comparação

`comparison.json` registra parâmetros completos, hashes (checkpoint,
IP-Adapter, CLIP Vision, workflow, artifact, pixel), versões e métricas
**técnicas**: distância da imagem original, RMSE, densidade de bordas,
saturação média.

Elas **não são nota de qualidade** e não ordenam os resultados: distância
maior significa mais transformação, não "melhor". A avaliação em
STYLE / IDENTITY / DESIGN_PRESERVATION continua humana.

## "Character Reference" — hipótese, não fato

O guia externo do SeaArt chama o recurso de "Character Reference" e atribui
a função principalmente ao rosto. **Não afirmamos** que isso seja FaceID
nem IP-Adapter PLUS FACE: não há evidência pública de qual mecanismo o
SeaArt usa internamente.

A célula 8 apenas **lista** os nodes IPAdapter/FaceID presentes no
servidor, para consulta. Testar equivalência é objetivo da fase, não
premissa dela.

## Fora de escopo por ora

FaceDetailer (preparado, não adicionado), LoRA, troca de checkpoint,
sweep grande automático. Primeiro entender o efeito puro de
`img2img + IP-Adapter`.

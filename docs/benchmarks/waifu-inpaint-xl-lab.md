# WAI INPAINT-XL LAB — correção localizada de figurino

**Hipótese:** em vez de retransformar a personagem inteira, mascarar só a
roupa e deixar um modelo de inpainting redesenhar apenas ela.

```
CHIBI JÁ GERADO (WAI v17) → máscara da roupa → Waifu-Inpaint-XL → resto intacto
```

A pergunta é objetiva: **conseguimos consertar a roupa sem deformar o resto
da personagem?**

Não substitui o `wai_illustrious_sdxl_v170`, que continua gerando o chibi de
entrada. O laboratório anterior segue intacto.

## Estado: BLOQUEADO em dois pontos

Ambos exigem uma ação humana. A infraestrutura está pronta e validada.

### 1. O modelo é gated

`ShinoharaHare/Waifu-Inpaint-XL` exige aceitar termos e compartilhar
contato antes de liberar os arquivos:

> *You need to agree to share your contact information to access this model.*

A listagem é pública (é assim que sabemos que o arquivo é
`Waifu-Inpaint-XL.safetensors`, 6.94 GB), mas o download precisa de login e
aceite. **É um ato pessoal, feito na sua conta** — não dá para automatizar,
e contornar o gate está fora de questão.

Passos: aceitar em `https://huggingface.co/ShinoharaHare/Waifu-Inpaint-XL`,
baixar o `.safetensors` e colocar em
`My Drive/ComfyUI_Data/models/checkpoints/`. O SHA-256 é calculado e
registrado na célula 1.

### 2. A máscara não existe

`characters/waifu_001/masks/outfit_mask.png` precisa ser pintada à mão.
Requisitos em `characters/waifu_001/masks/README.md`. Máscara manual é
escolha desta fase: segmentação automática é outro problema, e uma máscara
ruim invalidaria o experimento inteiro.

Falta também a `SOURCE_IMAGE` — o melhor chibi do lab anterior, que ainda
não foi executado.

## Achados técnicos (o item 1 da entrega)

### O modelo NÃO é um checkpoint WAI comum

| aspecto | valor | consequência |
|---|---|---|
| UNet | **9 canais** (4 latente + 1 máscara + 4 latente mascarado) | exige `InpaintModelConditioning` |
| predição | **v_prediction** | exige `ModelSamplingDiscrete` |
| linhagem | WAI **V14.0-V-Prediction** | ≠ nosso v17.0 (eps) |
| licença | CreativeML Open RAIL++-M | `pending_human_review` |

**Não é o nosso WAI v17.** A cadeia é
`kohaku-xl-beta5 → Illustrious-xl-early-release-v0 → WAI-NSFW-illustrious-SDXL-V14.0-V-Prediction → Waifu-Inpaint-XL`.
Tratar os dois como intercambiáveis seria erro.

### `InpaintModelConditioning`, não `VAEEncodeForInpaint`

Decisão mais importante do workflow. `VAEEncodeForInpaint` **substitui a
área mascarada por ruído puro e exige `denoise 1.0`** — destruiria o design
existente, o oposto do objetivo. `InpaintModelConditioning` preserva o
conteúdo sob a máscara e permite `INPAINT_STRENGTH < 1.0`.

`CheckpointLoaderSimple` carrega o arquivo, mas sozinho não alimenta os
canais extras; quem faz isso é o `InpaintModelConditioning`. Ambos são nodes
de fábrica — **nenhum custom node** no Teste 1.

### v-prediction não é opcional

Herdado do V14.0-V-Prediction. Com `eps` o output sai queimado. Se o
ComfyUI não autodetectar, o `ModelSamplingDiscrete` no grafo garante.

`zsnr` fica em `False`: **o autor não declara**, nem todo v-pred usa, e
aplicá-lo indevidamente também queima a imagem. Parâmetro exposto para
testar isoladamente.

### Alerta de terceiros

Relato em r/comfyui (2026): *"it changes the color of the whole image
slightly"*. Fonte secundária, não verificada — mas é **exatamente** o risco
desta fase, e o motivo de `outside_mask_changed_percentage` ser a métrica
principal.

## O grafo (`v0.json`, 12 nodes)

```
[1] CheckpointLoaderSimple (Waifu-Inpaint-XL, 9ch)
      ├── MODEL → [5] ModelSamplingDiscrete (v_prediction) ──┐
      ├── CLIP  → [2] positivo  ─┐                           │
      │           [3] negativo  ─┤                           │
      └── VAE ───────────────────┤                           │
                                 │                           │
[10] LoadImage(SOURCE) ──────────┤                           │
[11] LoadImageMask ─→ [12] GrowMask ─→ [13] FeatherMask ─────┤
                                 │                           │
                    [20] InpaintModelConditioning            │
                         (positive, negative, latent)        │
                                 └──────→ [40] KSampler ←────┘
                                              ↓
                                   [41] VAEDecode → [42] SaveImage
```

## As três entradas são coisas diferentes

| entrada | é | papel |
|---|---|---|
| `SOURCE_IMAGE` | chibi **já gerado** | imagem a corrigir |
| `OUTFIT_MASK` | região semântica | onde **pode** redesenhar |
| `OUTFIT_REFERENCE` | crop visual | design (**não** usado no Teste 1) |

`outfit.png` **não é máscara**. Nunca foi.

## Teste 1 — inpaint puro (o que está pronto)

Sem IP-Adapter. Mede o que o modelo faz sozinho, antes de somar variáveis.

`REFERENCE_MODE` já existe no painel com as quatro opções, mas qualquer
valor diferente de `NONE` **bloqueia**: o Teste 2 precisa de IP-Adapter
sobre um modelo de 9 canais, combinação ainda não validada. Oferecer a
opção e rodar inpaint puro seria mentir sobre o que foi executado.

## Parâmetros

| grupo | parâmetro | inicial | origem |
|---|---|---|---|
| strength | `INPAINT_STRENGTH` | `0.75` | **experimental** |
| máscara | `MASK_DILATION` · `MASK_FEATHER` | `8` · `6` | conservador |
| sampling | `STEPS` · `CFG_SCALE` | `28` · `5.0` | model card |
| sampling | `SAMPLER` · `SCHEDULER` · `SEED` | `euler_ancestral` · `normal` · `42` | |
| v-pred | `SAMPLING_TYPE` · `ZSNR` | `v_prediction` · `False` | linhagem |

`INPAINT_STRENGTH` **não herda o 0.90** do img2img: lá o objetivo era
transformar, aqui é corrigir. Sem sweep automático nesta fase.

## Métrica: localidade, não beleza

`scripts/chibi/inpaint_check.py` compara source e output **fora da máscara**:

- `outside_mask_changed_percentage` / `outside_mask_preserved_percentage`
- `outside_mask_mean_abs_diff` · `outside_mask_max_abs_diff`
- `inside_mask_mean_abs_diff` · `mask_area_percentage`

Tolerância de **2 níveis** por canal: o VAE do SDXL é lossy e reencoda a
imagem inteira, então até a área preservada volta com ruído de quantização.
Exigir identidade exata reprovaria todo inpaint, inclusive um perfeito.

**Isto não é nota de qualidade.** Localidade perfeita e resultado feio são
compatíveis. A avaliação estética continua humana —
`[HUMAN REVIEW REQUIRED]`.

`comparison.png` mostra source · máscara · output · diferença (×8).

## Estrutura de saída

```
experiments/inpaint_lab/experiment_YYYYMMDD_HHMMSS/
├── config.json · recipe.json · workflow.resolved.json
├── comparison.png · comparison.json · hashes.json
├── source/ · mask/ · reference/ · output/ · logs/
```

Nunca sobrescreve: se o diretório existir, bloqueia.

## Validação já executada

Fora do Colab, com `/object_info` simulado: a configuração válida passa, o
grafo resolve 100% dos placeholders, e **6 testes negativos bloqueiam** —
sampler, scheduler, canal de máscara e sampling type inexistentes,
`InpaintModelConditioning` ausente, `FeatherMask` ausente.

A célula 2 bloqueia máscara ausente, de tamanho diferente da source, toda
preta, com menos de 1% ou **mais de 60%** de área. Acima de 60% deixa de ser
correção localizada e vira retransformação.

27 testes em `tests/test_inpaint_lab.py`.

## Se a resposta for NÃO

Registrar exatamente por quê e partir para outra técnica. **Não mascarar um
resultado ruim com pós-processamento.**

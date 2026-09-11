# DESIGN REPAIR / LOCAL INPAINT

Linha experimental própria, **separada do benchmark do
`waiIllustriousSDXL_v170`**, que permanece válido e intocado. Este
checkpoint não o substitui: são modelos, licenças e finalidades diferentes.

`RUN 003 → máscara da roupa → Waifu-Inpaint-XL → roupa corrigida`

A pergunta é objetiva: **o Waifu-Inpaint-XL consegue corrigir a roupa da
Run 003 com boa integração visual, sem alterar o resto?**

## Entradas

| entrada | origem | papel |
|---|---|---|
| `run_003_output.png` | **upload** (não está no Git) | imagem a corrigir |
| `outfit_mask.png` | upload, pintada à mão | onde **pode** editar |
| `protected_mask.png` | upload, opcional | overlap exigido = **0** |
| `full_body.png` | declarada | **não usada** neste teste |

A máscara está no **espaço da Run 003**, não no da arte original: o alvo da
edição já é a Run 003.

Validado da source: dimensão, SHA-256 do arquivo e SHA-256 dos pixels.

## Regiões protegidas

Rosto, olhos, cabelo, chifres, mãos e o que estiver fora da roupa. Se a
`protected_mask.png` for enviada, o overlap com a máscara de roupa tem de
ser **zero** — qualquer pixel invadido bloqueia a execução.

Sem ela, o notebook **avisa** que a verificação automática não é possível e
a conferência visual passa a ser a única garantia. Não finge que checou.

Antes de qualquer geração o notebook mostra **SOURCE, MASK e OVERLAY** e
para se a máscara não for válida.

## Estado: BLOQUEADO em dois pontos

Ambos exigem uma ação humana. A infraestrutura está pronta e validada.

### 1. O modelo é gated

`ShinoharaHare/Waifu-Inpaint-XL` exige aceitar termos e compartilhar
contato antes de liberar os arquivos:

> *You need to agree to share your contact information to access this model.*

**O aceite é pessoal e continua sendo seu** — o agente não pode aceitar
termos em seu nome. Mas **o download em si é automático** depois disso,
usando um token seu:

1. aceite as condições em
   `https://huggingface.co/ShinoharaHare/Waifu-Inpaint-XL` (logado);
2. crie um token de leitura em `huggingface.co/settings/tokens`;
3. no Colab: painel lateral → chave 🔑 (Secrets) → `+ Adicionar novo
   secret`, nome **HF_TOKEN**, com acesso ao notebook.

A célula 4 lê o token de Secrets (ou de `HF_TOKEN` no ambiente, ou via
`pedir_token()`), baixa direto para o Drive e calcula o SHA-256. **O token
nunca é escrito no notebook** — não há campo de formulário para ele.

Proteções do download, todas testadas contra um servidor local:

| situação | comportamento |
|---|---|
| token ausente | bloqueia com os passos do aceite |
| HTTP 401/403 | bloqueia dizendo que faltam **aceitar as condições** |
| menos de 8 GB livres | bloqueia antes de começar |
| download truncado | descarta o `.part`, não cria o arquivo final |
| HTML de erro salvo como `.safetensors` | bloqueia na checagem de cabeçalho |

Baixa para um `.part` e só renomeia no fim: um checkpoint pela metade
falharia dentro do ComfyUI com erro obscuro.

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


## TESTE 3 — reparo com referencia visual (IP-Adapter)

### Por que existe

O TESTE 1 (inpaint puro) rodou e esta **encerrado como resultado negativo
limpo**: dentro da mascara o modelo pintou algo plausivel — mais preto —
em vez de reconstruir o design. Nao foi falha de execucao. O grafo do
`v0.json` entrega ao modelo exatamente tres coisas: a Run 003, a mascara e
um prompt **deliberadamente generico** (sem cor, roupa ou acessorio, por
regra do projeto). Nenhuma delas carrega o design da personagem. O modelo
nao tinha como saber o que reconstruir.

`preserve character design` no prompt nao preserva nada: e texto, e o
modelo nao conhece o design.

### A pergunta do TESTE 3

Uma referencia **visual** permite reconstruir a roupa sem descrever a
personagem no prompt? Se sim, o prompt continua generico e reutilizavel
para 100+ personagens — a identidade vem da imagem, como manda a regra.

### O que muda em relacao ao TESTE 1

**Um unico fator.** Mesma source, mesma mascara, mesmos parametros de
amostragem, mesmo prompt. A unica diferenca e `full_body.png` entrando
como referencia de IP-Adapter.

| | TESTE 1 | TESTE 3 |
|---|---|---|
| workflow | `v0.json` | `v1.json` |
| nodes | 12, so de fabrica | 17, + `ComfyUI_IPAdapter_plus` |
| referencia | declarada, nao usada | `full_body.png` via IP-Adapter |

### Arquitetura

```
run_003 ──> LoadImage(10) ──> InpaintModelConditioning(20) ──> latente ──┐
mascara ──> GrowMask ──> FeatherMask ──────────> (20)                    │
                                                                         v
checkpoint ──> ModelSamplingDiscrete(5, v_pred) ──> IPAdapterEmbeds(34) ──> KSampler(40)
                                                          ^
full_body ──> LoadImage(30) ──> IPAdapterEncoder(33) ─────┘
                                CLIPVisionLoader(32) ─────┘
                                IPAdapterModelLoader(31) ─┘
```

Tres propriedades que o notebook **verifica no grafo**, nao assume:

1. **A imagem principal continua sendo a Run 003.** O latente sai do
   `InpaintModelConditioning`, alimentado pelo `LoadImage(10)`. A
   referencia nunca vira imagem principal — se virasse, a Run 003 seria
   descartada e isso deixaria de ser reparo local.
2. **O IP-Adapter atua sobre o MODEL, em paralelo, nunca sobre o latente.**
3. **Ordem `ModelSamplingDiscrete` → `IPAdapterEmbeds` → `KSampler`.** O
   adapter patcha o model **depois** do v-prediction, nunca antes.

### Decisoes de implementacao

**Loaders explicitos, nao `IPAdapterUnifiedLoader`.** O Unified resolve
arquivo e encoder a partir de um preset, o que quebraria o pinning por
SHA256 e a auditoria. Usamos `IPAdapterModelLoader` + `CLIPVisionLoader`.

**`IPAdapterEncoder` + `IPAdapterEmbeds`, nao `IPAdapterAdvanced`.**
Mantem o padrao ja auditado em `wai_illustrious_ipadapter/v3.json` e
permite declarar o peso da referencia separadamente.

**Pareamento vit-h.** `ip-adapter-plus_sdxl_vit-h` exige o encoder
**CLIP-ViT-H**, nao o bigG. Errar o par nao levanta erro claro — degrada
em silencio. Ambos os pesos estao em `models.lock.yaml` sob
`ip_adapter_plus_sdxl`, com licenca **Apache-2.0 propria**, separada da do
Waifu-Inpaint-XL.

**Custom node exige aceite.** A regra do projeto proibe instalar custom
node sem autorizacao: `IPADAPTER_ACK` bloqueia enquanto nao for marcado. O
commit do node vai para o recipe.

### O que este teste NAO faz

Sem sweep de denoise, sem sweep de prompt, sem alterar a mascara, sem
trocar o checkpoint. O TESTE 1 permanece registrado e o benchmark do
WAI v17 continua intacto.

### Interpretacao

`outside_mask_changed_percentage` e `protected_overlap_pixels` continuam
medindo **localidade, nao qualidade**. Se a roupa ficou mais fiel ao
design e **avaliacao humana** — nenhuma metrica aqui responde isso.

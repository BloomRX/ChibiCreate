# Benchmark comparativo — WAI-illustrious-SDXL vs FLUX.2 klein 4B

**Status:** preparado, NÃO executado · **Tipo:** benchmark comparativo · **Não é pipeline oficial**

> **Correção desta rodada.** O resultado anterior saiu com artefatos. Antes
> de culpar o modelo ou o IP-Adapter, as Runs 001/002 passam a ser um
> **baseline WAI puro** (txt2img, só nodes Core), com os parâmetros do
> próprio autor do v17.0. O objetivo é diagnóstico: separar **(A)**
> configuração incorreta de **(B)** WAI + IP-Adapter e de **(C)** WAI
> funcionando mas artisticamente inferior ao FLUX.

## Diagnóstico: três causas, uma de cada vez

| observação | causa | conclusão |
|---|---|---|
| Run 001 já suja | **(A)** configuração / checkpoint | IP-Adapter **inocente** — nem participou |
| 001 limpa, 003 suja | **(B)** WAI + IP-Adapter | investigar um fator por vez |
| ambas limpas | **(C)** questão artística | comparar com o FLUX |

As Runs 001/002 usam o workflow `v0`: `CheckpointLoaderSimple` →
`CLIPTextEncode` ×2 → `EmptyLatentImage` → `KSampler` → `VAEDecode` →
`SaveImage`. Nada mais. Sem IP-Adapter, ControlNet, LoRA, Hires ou
ADetailer — qualquer extra invalidaria o diagnóstico.

### `full_body` é declarada, mas não consumida

Ponto que precisa ficar explícito: o pedido diz "Run 001 com uma referência:
`full_body`", mas também proíbe IP-Adapter. **Sem IP-Adapter o SDXL não tem
por onde receber uma imagem de referência** — e com `denoise 1.0` um img2img
descartaria o latente de qualquer forma.

Então a Run 001 é txt2img e o recipe registra os dois campos separados:

```
references_declared: ["full_body"]
references_consumed: []
```

A referência não é omitida em silêncio. A Run 001 mede **o checkpoint**, não
a fidelidade à imagem.

### Parâmetros do autor do v17.0

| | valor | origem |
|---|---|---|
| steps | 20 | meio da faixa do autor (15–30) |
| CFG | 6.0 | meio da faixa do autor (5–7) |
| sampler | `euler_ancestral` | "Euler a" do A1111 |
| scheduler | `normal` | **escolha nossa** — o autor não declara |
| resolução | **1024×1344** | exemplo do autor (nativo > 1024²) |
| denoise | 1.0 | txt2img |
| VAE | integrado ao checkpoint | saída 2 do loader |
| Hires fix | **desligado** | proibido nesta rodada |

Antes usávamos 30 steps / CFG 7.0 (topo da faixa) e 1024×1024. **Gerar
abaixo da resolução nativa é causa conhecida de artefato em SDXL**, então
1024×1024 era candidato real a explicar o resultado ruim.

### Prompt curto

O autor avisa que excesso de quality tags e negativos longos **reduzem** a
qualidade em modelos Illustrious. Trocamos o `base_prompt` de 906 caracteres
(compartilhado com o FLUX) pelo formato recomendado:

> `masterpiece, best quality, amazing quality, clean polished stylized chibi full-body character, preserve the same character identity, black hair, red eyes, horns, black outfit, long black cape and golden ornaments, cute game/gacha chibi character, full body, centered composition`

Negativo: `bad quality, worst quality, worst detail, sketch, censor`

### Limitações registradas

Duas assimetrias novas em relação ao FLUX, declaradas em vez de escondidas:

1. **Resolução:** WAI gera 1024×1344, FLUX gera 1024×1024.
2. **Prompt:** deixaram de ser idênticos.

Ambas enfraquecem a comparação direta — mas são necessárias para responder
primeiro "o checkpoint funciona?". As imagens de referência **não** foram
alteradas.

## A pergunta

> É possível gerar nossa chibi diretamente com WAI-illustrious-SDXL e obter
> uma roupa mais fiel ao design original do que com FLUX.2 klein 4B?

- **Sim** → WAI vira candidato à ROTA DIRETA.
- **Não** → FLUX segue como baseline.

A resposta é **humana**. Não há ranking automático, nem métrica única, nem
decisão do agente.

## Multi-referência via IP-Adapter

O checkpoint SDXL não tem mecanismo próprio de referência como o
`ReferenceLatent` do FLUX. Isso **não** significa que não consiga usar várias
referências — o **IP-Adapter** fornece multi-referência real:

```
full_body ──► IPAdapterEncoder (peso 1.0) ──┐
face      ──► IPAdapterEncoder (peso 0.6) ──┼──► IPAdapterCombineEmbeds
outfit    ──► IPAdapterEncoder (peso 0.8) ──┘             │
                                                  IPAdapterEmbeds
                                                          │
                                                      KSampler
```

Usamos `IPAdapterEncoder` + `IPAdapterCombineEmbeds` em vez de empilhar
`IPAdapterAdvanced` em série porque só essa rota permite **declarar e
auditar o peso de cada referência** separadamente — que é o que a diretiva
exige registrar.

Detalhe de implementação: cada `IPAdapterEncoder` devolve `pos_embed` **e**
`neg_embed`, então o grafo tem **dois** nós de combine (um para cada), senão
o negativo de uma única referência acabaria valendo por todas.

### Mecanismos diferentes — sem afirmar equivalência

| | mecanismo | onde atua |
|---|---|---|
| FLUX.2 klein | `ReferenceLatent` (próprio) | espaço latente |
| WAI / SDXL | **IP-Adapter** | embeddings CLIP-Vision, cross-attention paralela |

São implementações **diferentes**. A comparação é sobre o **resultado visual
com as mesmas referências de entrada**, nunca sobre equivalência de
arquitetura.

### Geração, não img2img

O grafo parte de `EmptyLatentImage` com `denoise: 1.0`. Se usássemos img2img,
`full_body` entraria duas vezes — uma como latente inicial, outra como
embed — e o peso declarado de cada referência deixaria de valer.

## Dependência de terceiro — aceite explícito

| item | arquivo | licença |
|---|---|---|
| custom node | `cubiq/ComfyUI_IPAdapter_plus` | Apache-2.0 |
| adapter | `ip-adapter-plus_sdxl_vit-h.safetensors` | Apache-2.0 (`h94/IP-Adapter`) |
| encoder | `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` | Apache-2.0 (`h94/IP-Adapter`) |

A variante *plus* usa patch embeddings e fica mais próxima da referência —
exatamente o eixo medido. O encoder ViT-H é o par obrigatório dela; trocar
por bigG daria erro de dimensão de tensor.

Este custom node não é arbitrário: é a implementação de referência do
IP-Adapter em ComfyUI, exigida pela diretiva. O notebook pede aceite
explícito, registra `commit` e `revision`, e calcula o SHA256 de cada peso
baixado. **Se os nós não aparecerem no `/object_info`, o benchmark PARA** — a
Run 003 nunca cai para uma referência em silêncio.

Usamos loaders explícitos (`IPAdapterModelLoader` + `CLIPVisionLoader`) em
vez do `IPAdapterUnifiedLoader`, que resolve arquivo por preset e pode baixar
peso sozinho, quebrando o pinning por SHA256.

## Checkpoint: vem do Google Drive

O arquivo já existe no Drive do usuário, então o notebook **não baixa e não
pede upload**. O Civitai não é acessado.

```
My Drive/ComfyUI_Data/models/checkpoints/waiIllustriousSDXL_v170.safetensors
```

A célula 4 faz, em ordem: monta o Drive (integração nativa do Colab),
localiza o arquivo, **valida que é mesmo um checkpoint SDXL**, calcula o
SHA256 e liga o arquivo ao ComfyUI.

**O original nunca é movido nem modificado.** A ligação tenta `symlink`
primeiro — instantâneo, sem duplicar ~7 GB — e só cai para cópia se o
symlink não for legível neste ambiente. O método efetivamente usado
(`symlink` ou `copia`) vai para o recipe.

### Validação antes da inferência

Lemos apenas o header do `safetensors` (8 bytes de tamanho + JSON), sem
carregar os pesos:

| verificação | por quê |
|---|---|
| `model.diffusion_model.*` | é um checkpoint, não um LoRA ou VAE solto |
| `conditioner.embedders.1.*` | **segundo text encoder (OpenCLIP bigG) = SDXL** |
| `conditioner.embedders.0.*` | primeiro text encoder (CLIP-L) |
| `first_stage_model.*` | VAE embutido |
| tamanho ≥ 3 GB | descarta arquivo truncado |

O segundo text encoder é o que distingue SDXL de SD 1.5/2.x. Um LoRA ou um
SD 1.5 renomeado é recusado com `BLOCKED` antes de qualquer inferência.

### Se o arquivo não estiver lá

Erro claro, e o notebook **lista os `.safetensors` que realmente existem** na
pasta (ou sobe até o ancestral existente e mostra as subpastas). Você corrige
`CKPT_DRIVE_PATH` no formulário e reexecuta. Nenhum nome de arquivo é
adivinhado.

### `modelVersionId` não bloqueia

O `modelVersionId` do Civitai fica `unknown/pending` quando desconhecido e
**não impede a execução** — o SHA256 do arquivo real identifica o checkpoint
de forma mais forte que um id de catálogo, e fica gravado no recipe. Os
metadados podem ser preenchidos depois.

A versão é lida do nome do arquivo (`v170`) e registrada como
`revision_from_filename`. Nenhum outro WAI/Illustrious é aceito no lugar.

### Nova sessão do Colab

O fluxo é reentrante: montar → localizar → validar → subir o ComfyUI →
executar. A célula 4 detecta Drive já montado e checkpoint já ligado, então
reexecutar é barato. Nenhum token ou credencial é armazenado.

## Licença — pendente de revisão humana

| eixo | situação |
|---|---|
| licença citada | Fair AI Public License 1.0-SD (herdada do Illustrious-XL) |
| fonte | **secundária** (espelhos HuggingFace). Civitai inacessível daqui |
| UI do Civitai | "Commercial use allowed" — observação do usuário |
| conflito | a FAIPL restringe monetização proprietária closed-source |
| `commercial_status` | **`pending_human_review`** |

Os dois lados ficam registrados sem reinterpretação. Os botões do Civitai são
metadados preenchidos pelo autor e já divergiram do texto da licença em
outros modelos.

`[HUMAN REVIEW REQUIRED]` O projeto chama-se originalmente
**WAI-NSFW-illustrious-SDXL**, com foco declarado em conteúdo adulto. Nenhuma
tag NSFW foi adicionada aos prompts; registra-se porque afeta o
comportamento do modelo.

## Configuração

| | valor | origem |
|---|---|---|
| resolução | 1024×1024 | nativo SDXL, igual ao FLUX |
| seed | 42 | diretiva |
| batch | 1 | diretiva |
| steps | 30 | recomendação do autor |
| cfg | 7.0 | recomendação do autor |
| sampler / scheduler | euler_ancestral / normal | recomendação do autor |
| denoise | 1.0 | `DERIVED_FROM_PIPELINE` — parte de latente vazio |
| prompt | `base_prompt` do registry | **idêntico ao do FLUX** |
| prefixo de qualidade | **nenhum** | embelezaria o candidato |
| negativo | `bad quality, worst quality, worst detail, sketch, censor` | declarado pelo autor |

Parâmetros de benchmark controlado, **não** copiados de screenshots do
Civitai. Sem sweep de prompt e sem sweep de seed.

## Runs

| run | workflow | refs consumidas | o que testa |
|---|---|---|---|
| 001 | `v0` | — (txt2img) | **o checkpoint funciona?** |
| 002 | `v0` | — (txt2img) | reprodutibilidade — repetição exata da 001 |
| 003 | `v2` | `full_body` + `face` + `outfit` | multi-referência via IP-Adapter |

Pesos da Run 003 — **BASELINE EXPERIMENTAL**, não validados:

| referência | peso | papel |
|---|---|---|
| `full_body` | 1.0 | composição, silhueta, proporção |
| `face` | 0.6 | identidade facial |
| `outfit` | 0.8 | roupa, capa, ornamentos dourados |

Método de combinação: `concat` (preserva os tokens de cada referência em vez
de mediá-los, então roupa e rosto não se dissolvem um no outro).

**Sem sweep nesta rodada:** uma única configuração, com os três pesos
registrados individualmente. A calibração fica para uma rodada própria.

`artifact_sha256` e `output_pixel_sha256` são registrados separadamente. Hash
diferente entre 001 e 002 é **resultado**, não falha: não prometemos
determinismo absoluto.

## Como rodar no Colab

1. Abrir `notebooks/wai_illustrious_sdxl_eval.ipynb` no Colab.
2. `Runtime → Change runtime type → T4 GPU`.
3. **Célula 0** — escolher `CHARACTER_ID` e a **run** (001, 002 ou 003).
4. **Célula 2** — preflight. Se `BLOCKED`, **pare**: sem fallback silencioso.
5. **Célula 4** — montar o Drive e validar o checkpoint. Autorize o acesso
   quando o Colab pedir; ajuste `CKPT_DRIVE_PATH` se o seu caminho diferir.
6. **Célula 6** — só para a Run 003: marcar `ACEITO_INSTALAR_IPADAPTER`.
   Nas Runs 001/002 ela se autodesativa e não instala nada.
7. Células 7→13 em ordem.

Rode a **Run 001 primeiro** e olhe a imagem. Se já vier com artefatos, pare:
a causa é **(A)** e o IP-Adapter não tem culpa. Só siga para a 003 se a 001
estiver limpa.

Ao final, a **célula 13** gera `wai_illustrious_eval_results.zip` em
`/content/` e dispara o download.

Para as três runs: repita as células 8→10 mudando `RUN` na célula 0. A
célula 11 compara 001 × 002; a 12 monta a comparação final.

Toda a configuração é feita por **Colab forms**. Não é preciso editar código.

## Hardware

| requisito | valor |
|---|---|
| GPU | T4 16 GB (mínimo verificado: 12 GB VRAM) |
| disco | 20 GB |
| RAM | 10 GB |

SDXL fp16 (~8-10 GB) mais IP-Adapter (~1 GB) e CLIP-Vision ViT-H (~2.5 GB no
encode) dão ~12 GB — cabe na T4, com folga menor que a rota img2img.
Estimativa de registry, **não medida** por nós: o preflight mede de verdade e
emite `BLOCKED` se não couber.

## Escopo

**Faz:** medir `ORIGINAL → WAI` e comparar com `ORIGINAL → FLUX` no eixo
DESIGN_PRESERVATION.

**Não faz:** modificar o benchmark FLUX, as Runs 001/002/003, o Flow 01, os
quality gates ou o design transfer; implementar Design Transfer, TPS, LoRA,
ControlNet ou inpainting; gerar animação ou master; criar pipeline oficial;
sweep de prompt ou seed; testar Pony ou outro checkpoint WAI.

**PARE após o benchmark.** A rota `FLUX RUN 003 → WAI` só se discute **se** o
WAI mostrar vantagem real em DESIGN_PRESERVATION.

## Arquivos

- `notebooks/wai_illustrious_sdxl_eval.ipynb` — o benchmark
- `workflows/experimental/wai_illustrious_ipadapter/v0.json` — **baseline puro** (runs 001/002)
- `workflows/experimental/wai_illustrious_ipadapter/v1.json` — 1 referência via IP-Adapter (sem uso nesta rodada)
- `workflows/experimental/wai_illustrious_ipadapter/v2.json` — 3 referências
- `workflows/experimental/wai_illustrious_chibi/v1.json` — rota img2img anterior, mantida
- `config/model_eval_registry.yaml` → `wai_illustrious_sdxl_v170`
- `config/models.lock.yaml` → `wai_illustrious_sdxl_v170` (`MODEL_MISSING`)
- `tests/test_wai_benchmark.py` — 100 testes

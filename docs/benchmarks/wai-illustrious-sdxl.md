# Benchmark comparativo — WAI-illustrious-SDXL vs FLUX.2 klein 4B

**Status:** preparado, NÃO executado · **Tipo:** benchmark comparativo · **Não é pipeline oficial**

> **Correção aplicada nesta rodada.** A versão anterior deste benchmark
> tratava "SDXL não tem multi-referência nativa" como se fosse "SDXL não
> consegue usar múltiplas referências". São coisas distintas: o IP-Adapter
> fornece multi-referência real, e a Run 003 agora usa as três referências.

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

## Bloqueio de versão — [HUMAN REVIEW REQUIRED]

A diretiva pede `modelVersionId`, arquivo e SHA256 do checkpoint exato de
`civitai.red/models/827184`.

**`civitai.red` e `civitai.com` estão fora da allowlist de egress da sandbox**
(HTTP 000, handshake TLS interrompido). Portanto:

- `civitai_model_version_id: null`
- `sha256: null`
- `license_verified: false`

Nada disso foi inventado nem substituído por outra versão por conta própria.
O notebook tem a **célula 4**, onde você — que enxerga o Civitai no Colab —
fixa esses valores. A célula 5 confere o SHA256 do arquivo baixado contra o
que você declarou e **para** se divergir.

> Nota: o repositório já continha uma entrada apontando **v17.0**, também não
> verificada. A busca indica que a **v14 trocou de modelo-base** (saiu do
> Illustrious-XL 2.0), então a versão importa e precisa de decisão humana.

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

| run | referências | workflow | o que testa |
|---|---|---|---|
| 001 | `full_body` | `v1` | linha de base |
| 002 | `full_body` | `v1` | reprodutibilidade — repetição exata da 001 |
| 003 | `full_body` + `face` + `outfit` | `v2` | multi-referência via IP-Adapter |

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
5. **Célula 4** — fixar `modelVersionId`, arquivo e SHA256 lidos no Civitai.
6. **Célula 6** — marcar `ACEITO_INSTALAR_IPADAPTER` (custom node + 2 pesos).
7. Subir o `.safetensors` do WAI para `/content/ComfyUI/models/checkpoints/`.
8. Células 7→12 em ordem.

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
- `workflows/experimental/wai_illustrious_ipadapter/v1.json` — 1 referência
- `workflows/experimental/wai_illustrious_ipadapter/v2.json` — 3 referências
- `workflows/experimental/wai_illustrious_chibi/v1.json` — rota img2img anterior, mantida
- `config/model_eval_registry.yaml` → `wai_illustrious_sdxl_v170`
- `config/models.lock.yaml` → `wai_illustrious_sdxl_v170` (`MODEL_MISSING`)
- `tests/test_wai_benchmark.py` — 71 testes

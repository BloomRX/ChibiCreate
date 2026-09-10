# Benchmark comparativo — WAI-illustrious-SDXL vs FLUX.2 klein 4B

**Status:** preparado, NÃO executado · **Tipo:** benchmark comparativo · **Não é pipeline oficial**

## A pergunta

> É possível gerar nossa chibi diretamente com WAI-illustrious-SDXL e obter
> uma roupa mais fiel ao design original do que com FLUX.2 klein 4B?

- **Sim** → WAI vira candidato à ROTA DIRETA.
- **Não** → FLUX segue como baseline.

A resposta é **humana**. Não há ranking automático, nem métrica única, nem
decisão do agente.

## Resultado principal desta preparação

**SDXL não tem multi-referência nativa.** Isso não é configuração ausente; é
diferença de arquitetura:

| modelo | mecanismo de referência | referências |
|---|---|---|
| FLUX.2 klein 4B | `ReferenceLatent` (nativo) | 1, 2, 3… encadeáveis |
| Qwen-Image-Edit-2511 | `TextEncodeQwenImageEditPlus` | múltiplos slots |
| **WAI-illustrious-SDXL** | **não existe** | **1** (img2img) |

O único caminho com nodes Core é `VAEEncode → KSampler(denoise<1.0)`: aceita
**uma** imagem e preserva **composição e cores**, não **identidade**.

**Consequência declarada:** a RUN 003 do WAI **não é** equivalente à RUN 003
do FLUX. Ela roda com 1 referência, não 3. Conforme a diretiva, isso é
documentado como limitação e **não** chamado de "3-reference equivalent".

Precedente já registrado no projeto: `pony_diffusion_v6_xl`, também SDXL,
tem `references_supported: 0` pelo mesmo motivo. IP-Adapter e ControlNet
resolveriam, mas estão **fora de escopo** por instrução explícita.

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
| denoise | 0.5 | `BASELINE_HYPOTHESIS` — mesmo valor do resto do projeto |
| prompt | `base_prompt` do registry | **idêntico ao do FLUX** |
| prefixo de qualidade | **nenhum** | embelezaria o candidato |
| negativo | `bad quality, worst quality, worst detail, sketch, censor` | declarado pelo autor |

Parâmetros de benchmark controlado, **não** copiados de screenshots do
Civitai. Sem sweep de prompt e sem sweep de seed.

## Runs

| run | referências | o que testa |
|---|---|---|
| 001 | `full_body` | linha de base |
| 002 | `full_body` | reprodutibilidade — repetição exata da 001 |
| 003 | `full_body` | ⚠️ **1 referência, não 3** — só varia `denoise` |

`artifact_sha256` e `output_pixel_sha256` são registrados separadamente. Hash
diferente entre 001 e 002 é **resultado**, não falha: não prometemos
determinismo absoluto.

## Como rodar no Colab

1. Abrir `notebooks/wai_illustrious_sdxl_eval.ipynb` no Colab.
2. `Runtime → Change runtime type → T4 GPU`.
3. **Célula 0** — escolher `CHARACTER_ID` (default `waifu_001`).
4. **Célula 2** — preflight. Se `BLOCKED`, **pare**: sem fallback silencioso.
5. **Célula 4** — fixar `modelVersionId`, arquivo e SHA256 lidos no Civitai.
6. **Célula 5** — marcar `BAIXAR_CHECKPOINT` (precisa de token) ou subir o
   `.safetensors` para `/content/ComfyUI/models/checkpoints/`.
7. Células 6→13 em ordem.

Toda a configuração é feita por **Colab forms**. Não é preciso editar código.

## Hardware

| requisito | valor |
|---|---|
| GPU | T4 16 GB (mínimo verificado: 10 GB VRAM) |
| disco | 12 GB |
| RAM | 10 GB |

SDXL fp16 usa ~8-10 GB e cabe na T4. Estimativa de registry, **não medida**
por nós. Se não couber, o preflight emite `BLOCKED` e para.

## Escopo

**Faz:** medir `ORIGINAL → WAI` e comparar com `ORIGINAL → FLUX` no eixo
DESIGN_PRESERVATION.

**Não faz:** modificar o benchmark FLUX, as Runs 001/002/003, o Flow 01, os
quality gates ou o design transfer; implementar LoRA, ControlNet, IP-Adapter
ou inpainting; gerar animação ou master; criar pipeline oficial; sweep de
prompt ou seed.

**PARE após o benchmark.** A rota `FLUX RUN 003 → WAI` só se discute **se** o
WAI mostrar vantagem real em DESIGN_PRESERVATION.

## Arquivos

- `notebooks/wai_illustrious_sdxl_eval.ipynb` — o benchmark
- `workflows/experimental/wai_illustrious_chibi/v1.json` — workflow (só nodes Core)
- `config/model_eval_registry.yaml` → `wai_illustrious_sdxl_v170`
- `config/models.lock.yaml` → `wai_illustrious_sdxl_v170` (`MODEL_MISSING`)
- `tests/test_wai_benchmark.py` — 45 testes

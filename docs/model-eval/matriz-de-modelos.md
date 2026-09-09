# Matriz de avaliação de modelos — dois notebooks, um dropdown

Avaliação da FASE 3B em duas etapas independentes, com a **mesma** lista de
modelos nos dois notebooks.

```
ETAPA 1 (Notebook 1)          ETAPA 2 (Notebook 2)

PERSONAGEM ORIGINAL           PERSONAGEM ORIGINAL
       |                             |
       v                        FLUX.2 klein 4B  (já executado)
MODELO SELECIONADO                   |
       |                        run_003/output.png
       v                             |
    OUTPUT                           v
                              MODELO SELECIONADO
                                     |
                                     v
                                OUTPUT FINAL
```

A matriz responde duas perguntas separadas: **qual modelo é melhor sozinho** e
**qual é melhor como refiner do FLUX**. São perguntas distintas — um modelo
pode vencer numa e perder na outra. Só com as duas etapas dá para saber se
`FLUX + modelo` supera o FLUX puro, se um modelo sozinho já supera o FLUX, ou
se o segundo estágio não melhora nada.

## Arquivos

| Caminho | O que é |
|---|---|
| `notebooks/model_eval_model_only.ipynb` | Notebook 1 — Original → Modelo |
| `notebooks/model_eval_flux_refiner.ipynb` | Notebook 2 — FLUX run_003 → Modelo |
| `config/model_eval_registry.yaml` | **Fonte única da verdade** dos modelos |
| `scripts/chibi/model_registry.py` | Lógica compartilhada (dropdown, preflight, referências, saída) |
| `tests/test_model_matrix.py` | 44 testes da matriz |

Toda a lógica mora no módulo Python, não nas células: célula de notebook não é
testável, função é. Os notebooks são casca fina.

**Para adicionar ou mudar um modelo, edite apenas o registry.** Não há
condicional por modelo espalhado pelos notebooks.

## Modelos e requisitos

| Modelo | Pipeline | Refs | Download | VRAM | Disco | Licença | Comercial |
|---|---|---|---|---|---|---|---|
| LongCat-Image-Edit | edição por instrução, 1 imagem | 0 | ~24 GB | ~18 GB¹ | 30 GB | Apache-2.0 | ✅ verified |
| Z-Image Turbo | t2i usado em img2img | 0 | ~14 GB | ~16 GB | 20 GB | Apache-2.0 | ✅ verified |
| Qwen-Edit-2511 **Q3_K_M** | edição multi-imagem | **2** | ~18.5 GB | ~10 GB² | 25 GB | Apache-2.0 (base) | ⚠️ pending review |
| Qwen-Edit-2511 **Q4_0** | edição multi-imagem | **2** | ~21.5 GB | ~13 GB² | 28 GB | Apache-2.0 (base) | ⚠️ pending review |
| Pony Diffusion V6 XL | SDXL img2img | 0 | ~7 GB | ~10 GB | 12 GB | FAIPL-1.0-SD mod. | ⛔ **research_only** |

¹ com `enable_model_cpu_offload()`; sem offload é maior.
² com text encoder e VAE descarregados para a RAM.

**Todos os números são `estimated: true`** — vêm do model card, não de medição
nossa. O preflight compara contra eles, mas eles não são medida do agente.

## Capacidades reais — leia antes de interpretar resultados

Três dos cinco modelos **não aceitam referências de design**. Isso não é
detalhe de implementação: muda o que o resultado significa.

- **LongCat-Image-Edit** documenta **uma** imagem de entrada. Multi-image foi
  anunciado pelos autores como prioridade da próxima versão — ou seja, não
  existe hoje. No Notebook 2 ele recebe só a saída do FLUX.
- **Z-Image Turbo é text-to-image.** Z-Image-Edit foi anunciado mas não
  lançado. Usá-lo com a saída do FLUX é img2img latente (VAEEncode +
  denoise), **não** edição por instrução, e não há slot para `full_body` nem
  `outfit`. Um pipeline de geração não é um editor multi-reference, e o
  notebook não finge que é.
- **Pony é um checkpoint SDXL.** Sem IP-Adapter nem ControlNet — ambos fora de
  escopo por instrução — o único modo com imagem é img2img latente.
- **Só o Qwen** aceita `full_body` + `outfit`. O node Core
  `TextEncodeQwenImageEditPlus` comporta 3 imagens; a principal ocupa
  `image1`, sobrando 2 slots. `face.png` fica de fora.

Quando uma referência não cabe, ela **nunca some em silêncio**: aparece em
`references_dropped` no recipe e num aviso destacado no notebook. Se o design
se perder num modelo sem referências, pode ser falta de referência, não
fraqueza do modelo.

## Licenças

Registradas a partir do texto do autor, não do nome do modelo.

**LongCat-Image-Edit** e **Z-Image Turbo** — Apache 2.0 confirmada nos model
cards oficiais. Comercialmente claras.

**Qwen Q3_K_M / Q4_0** — duas licenças distintas:
- modelo-base `Qwen/Qwen-Image-Edit-2511`: Apache 2.0, verificada;
- quantização `unsloth/…-GGUF`: declara Apache 2.0 herdada, **não verificada
  por nós** (sem revision nem hash conferidos).

Base Apache **não** torna a variante de terceiro automaticamente comercial:
ambas ficam `pending_human_review`. Além disso, GGUF só carrega pelo custom
node `ComfyUI-GGUF` (city96) — o notebook exige aceite explícito antes de
instalar qualquer coisa.

**Pony Diffusion V6 XL** — Fair AI Public License 1.0-SD **modificada**. Texto
do autor:

> You are not permitted to run inference of this model on websites or
> applications allowing any form of monetization (paid inference, faster
> tiers, etc.). This applies to any derivative models or model merges.

Permissão comercial explícita apenas para CivitAI e Hugging Face; outros casos
exigem contato com o autor. A restrição incide sobre **inferência monetizada**,
não só sobre redistribuição.

> Há fontes de terceiros afirmando "CreativeML OpenRAIL-M" e
> "cdla-permissive-2.0" para este modelo. Divergem do texto do próprio autor.
> Prevalece o texto do autor; a divergência fica registrada sem
> reinterpretação.

Por isso: `commercial_status: research_only`,
`excluded_from_commercial_ranking: true`. Ele **aparece no dropdown** — a
avaliação técnica é permitida e desejada — mas um resultado do Pony nunca
altera o candidato comercial vencedor.

## Preflight

Roda **antes** de qualquer download pesado, e existe por causa de um problema
real: o Qwen fp8/bf16 travou o Colab durante o carregamento. Baixar 30 GB para
descobrir que não cabe custa tempo e pode derrubar a sessão.

```
SELECTED MODEL:   Qwen-Image-Edit-2511 Q3_K_M
EXPECTED DISK:    25.0 GB      AVAILABLE DISK:   78.2 GB
EXPECTED VRAM:    10.0 GB      AVAILABLE VRAM:   14.7 GB
STATUS:           READY
```

Estados: `READY` · `BLOCKED — insufficient disk` · `BLOCKED — insufficient
VRAM`. Em bloqueio o notebook **para** com `SystemExit`, informa quanto falta
e se é preciso trocar de runtime. Nada é baixado.

**Disco ou VRAM desconhecido não vira READY** — vira BLOCKED. Não dar para
medir é motivo para parar, não para prosseguir no escuro.

O Qwen fp8/bf16 completo **não** está no registry, por instrução. Um teste
garante que `fp8mixed` e `fp8_e4m3fn` não voltem.

## Ordem recomendada

1. **Notebook 1 · Qwen Q3_K_M** — menor variante registrada, a com chance real
   de executar, e a única que aceita referências de design.
2. **Notebook 2 · Qwen Q3_K_M** — a comparação mais direta com o experimento
   FLUX → Qwen já documentado.
3. **Notebook 1 · LongCat-Image-Edit** — editor por instrução dedicado, o
   concorrente mais forte do Qwen em preservação.
4. **Notebook 2 · LongCat-Image-Edit**.
5. **Z-Image Turbo** (ambos) — barato e rápido; serve de piso de comparação.
6. **Qwen Q4_0** — só depois de ver o Q3. Se o Q3 funcionar, **não** baixe o Q4
   automaticamente: resete o Colab e escolha no dropdown.
7. **Pony** — por último, e só como referência técnica.

Um modelo por sessão. Entre um e outro: exporte o ZIP, rode o cleanup, resete.

## Ciclo de uso

```
abrir notebook → dropdown → ficha do modelo → preflight → confirmar
    → baixar SÓ o escolhido → executar 1× → analisar
    → exportar ZIP → cleanup → resetar → próximo modelo
```

### Interface

As células usam **Colab forms** (`#@title` + `#@param`): o código fica
colapsado e você vê só os controles e o log. Para editar, duplo-clique na
célula.

| Célula | Controle |
|---|---|
| 1 · Setup | `forcar_reclone` (checkbox) |
| 2 · Escolher modelo | `modelo` (**dropdown**), `seed` |
| 3 · Preflight | — (só log) |
| 4 · Autorizar download | `autorizo_o_download` (checkbox, começa desmarcado) |

O dropdown é o widget nativo do Colab, então `Runtime > Run all` funciona sem
clique: o valor escolhido fica gravado no próprio código.

Colab forms exigem a lista de opções literal no fonte. Um teste
(`test_lista_do_dropdown_bate_com_o_registry`) falha se alguém adicionar um
modelo ao registry e esquecer de atualizar o dropdown.

O cleanup remove `/content/models` e o cache do HF. **Nunca apaga
`experiments/`** — há um teste garantindo isso. Ainda assim, exporte o ZIP
antes de resetar: o disco do Colab não sobrevive ao reset.

Resultados vão para
`experiments/model_eval/{model_only,flux_to_model}/<model>/<run_id>/`, com
`run_id` sempre avançando. Reexecutar o mesmo modelo nunca sobrescreve o
resultado anterior.

## O que é registrado por execução

seed · steps · cfg · sampler · scheduler · denoise (+ `denoise_status`) ·
resolution · batch · prompt · negative prompt · referências usadas · **e
descartadas** · input role · repo/revision · hashes dos pesos baixados ·
GPU · VRAM · CUDA · Torch · RAM · tempo de execução · limitações conhecidas.

Dois hashes **separados** para cada imagem: `artifact_sha256` (arquivo) e
`pixel_sha256` (pixels). Metadados PNG mudam o primeiro sem mudar o segundo.

No Notebook 2, a imagem do `run_003` entra exatamente como está — sem
redimensionar, recomprimir ou editar — e isso fica registrado em
`modified_before_stage2: false` e `flux_reexecuted: false`.

## Estado atual e limitação principal

**Prontos e testados:** registry, dropdown, seleção de adapter, preflight com
bloqueio, plano de referências, layout de saída sem sobrescrita, recipes,
hashes, cleanup seguro, exportação.

**Não implementado:** a chamada de inferência de cada pipeline. A célula de
execução levanta `NotImplementedError` de propósito.

Motivo: os quatro pipelines são diferentes entre si (diffusers para
LongCat/Z-Image, ComfyUI + custom node GGUF para Qwen, SDXL para Pony) e
**nenhum foi executado contra GPU real** — este ambiente não tem GPU. Escrever
quatro adapters nunca executados e entregá-los como prontos produziria código
que aparenta funcionar e falha na primeira execução, no meio de um download de
20 GB. Marcado `[TEST REQUIRED]`.

Outras limitações: uma execução por modelo não permite afirmar determinismo; a
seed não atravessa estágios (42 no refiner não reproduz o ruído do FLUX);
`denoise: 0.5` é `BASELINE_HYPOTHESIS`, não calibrado; os requisitos de
VRAM/disco são declarados, não medidos.

## Fora de escopo

Sem LoRA, ControlNet, IP-Adapter, animação, `master.png`, alteração do Flow 01
ou dos workflows/notebooks do FLUX. O `run_003` continua sendo o baseline e o
FLUX **não** é reexecutado. Testes automatizados verificam cada um desses
pontos.

A decisão artística é humana. Não há OVERALL, não é média aritmética, e o
agente não escolhe vencedor.

## Download dos pesos (correcao pos-404)

A primeira execucao real da celula de download falhou em producao com
`RemoteEntryNotFoundError: 404`: o nome do GGUF no registry tinha sido
inferido, nao conferido. O repo `unsloth/Qwen-Image-Edit-2511-GGUF`
publica os arquivos com **prefixo em minusculo**:

- correto ... `qwen-image-edit-2511-Q3_K_M.gguf` (9.92 GB)
- errado .... `Qwen-Image-Edit-2511-Q3_K_M.gguf` (nao existe -> 404)

Segundo defeito encontrado na mesma investigacao: **o GGUF sozinho nao
roda**. `UnetLoaderGGUF` carrega apenas o difusor; sem o text encoder e o
VAE o workflow so falharia depois de ~10 GB baixados. O conjunto completo
esta agora em `auxiliary_files` no registry.

Plano real por modelo Qwen (`mr.download_plan(key)`):

| role | repo | arquivo | destino | GB |
|---|---|---|---|---|
| diffusion_model | unsloth/Qwen-Image-Edit-2511-GGUF | qwen-image-edit-2511-Q3_K_M.gguf | `unet/` | 9.92 |
| text_encoder | Comfy-Org/Qwen-Image_ComfyUI | qwen_2.5_vl_7b_fp8_scaled.safetensors | `text_encoders/` | 9.38 |
| vae | Comfy-Org/Qwen-Image_ComfyUI | qwen_image_vae.safetensors | `vae/` | 0.25 |

Total Q3_K_M **19.6 GB**, Q4_0 **20.7 GB** (`download_estimated: false`).
No T4 do usuario (65.3 GB livres) continua `READY`.

Duas defesas foram adicionadas para que isso nao se repita:

1. `mr.verify_remote_files(key)` lista a arvore do repo no Hugging Face e
   marca cada arquivo como existente ou nao. Quando nao existe, compara
   sem diferenciar maiusculas e devolve o nome real em `hint`. A celula de
   download chama isso **antes** de baixar e aborta com `SystemExit`
   mostrando repo, nome errado e nome correto.
2. O campo `file_verified` no registry marca os nomes ja conferidos contra
   a arvore real do repo. Nome nao verificado nao deve ser usado.

A verificacao custa uma chamada de API e roda antes de qualquer byte de
peso ser transferido.

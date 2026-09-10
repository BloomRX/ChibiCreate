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

## Execucao real: ComfyUI dentro do Colab (Notebook 1)

A celula de execucao vinha com `NotImplementedError` de proposito: nao havia
GPU para validar nenhum caminho de inferencia. Com o T4 disponivel, o
Notebook 1 passou a executar de verdade `Original -> Qwen-Image-Edit-2511
Q3_K_M`, com ComfyUI instalado no proprio runtime.

### Ordem das celulas (a ordem e o mecanismo de seguranca)

    7  instalar ComfyUI + ComfyUI-GGUF, subir o servidor, /object_info
    8  baixar os pesos
    9  executar

O ComfyUI sobe **antes** do download: os ~20 GB so descem depois que o
servidor provou que tem os nodes necessarios. A celula 7 aborta com
`SystemExit` se faltar qualquer node, e nao troca de modelo para contornar.

### O que e validado antes de gastar GPU

| verificacao | onde | falha => |
|---|---|---|
| GPU, VRAM, RAM, disco, CUDA, Torch | celula 3 | `BLOCKED` |
| nomes dos arquivos no repo HF | celula 8 | `SystemExit` com o nome real |
| nodes do workflow em `/object_info` | celula 7 | `SystemExit` + link do node |
| peso visivel no `UnetLoaderGGUF` | celula 9 | `SystemExit` |

A validacao contra `/object_info`, ate aqui **nunca realizada**, passou a
acontecer a cada execucao.

### Adapter: um ponto unico, sem condicional por modelo

`model_registry.ADAPTERS` mapeia `pipeline_type` -> workflow, nodes exigidos
e chave do lock. As celulas chamam `mr.run_model(...)` sem saber qual modelo
esta rodando, e `run_model` reusa `experiment.run_qwen_edit` — nao existe uma
segunda implementacao de inferencia no projeto. Um teste falha se aparecer
condicional por modelo em qualquer celula.

Modelo sem adapter levanta `AdapterIndisponivel` dizendo o que falta.
Hoje so o `instruction_edit_multi_image` (Qwen GGUF) tem adapter: LongCat e
Z-Image estao BLOCKED por VRAM no T4 e Pony ficou fora por decisao do
usuario. Nenhum deles cai em outro modelo por fallback.

### Workflow

`workflows/experimental/qwen_edit_gguf/v1.json`, derivado do
`qwen_edit_multiref/v1`. Unica diferenca: o node 1 e `UnetLoaderGGUF` em vez
de `UNETLoader`, porque o loader core nao le `.gguf`. O text encoder fp8
continua no `CLIPLoader` core de proposito — usar o loader GGUF com um
safetensors fp8 scaled da "Mixing scaled FP8 with GGUF is not supported".

### Licenca da variante nao herda a do modelo-base

O recipe de uma variante quantizada grava
`commercial_status: pending_human_review`, mesmo com o modelo-base Apache 2.0
`approved`, e registra o status do base em `base_model_commercial_status`.
Quem redistribuiu os pesos e outro autor, com licenca nao conferida por nos.

### O que continua valendo

Q4_0 nao e baixado e nao ha fallback automatico para ele: reset do runtime e
escolha no dropdown. O recipe nasce `approval_status: experimental`. Uma
execucao nao afirma determinismo. **Nenhum vencedor e escolhido por metrica
automatica** — a avaliacao dos tres eixos e humana.

## Travamento nas celulas 3 e 9: RAM, nao VRAM

Sintoma: as celulas 3 e 9 **travavam** (nao davam erro) no Colab T4.

Causa raiz: o preflight media disco e VRAM, mas **ignorava a RAM**. No T4:

| recurso | disponivel | exigido Q3_K_M | veredito |
|---|---|---|---|
| disco | 65.3 GB | 25 GB | cabe |
| VRAM | 14.6 GB | 10 GB | cabe |
| **RAM** | **12.7 GB** | **16 GB** | **NAO cabe** |

Como disco e VRAM cabiam, o preflight dizia `READY` e a execucao seguia ate
travar. E o requisito de RAM nao e um detalhe do GGUF: **e a razao de ele
existir**. A economia de VRAM do Q3_K_M vem de manter o text encoder (9.38
GB) e o VAE na RAM do sistema, e o `--lowvram` reforca isso movendo pesos da
VRAM para a RAM. Com 12.7 GB o processo entra em swap.

**Por que travou em vez de dar erro:** falta de VRAM levanta
`CUDA out of memory`; falta de RAM nao levanta nada — o kernel pagina para
disco e tudo congela. Comportamento confirmado em relatos de usuarios de
ComfyUI com Qwen GGUF: `--lowvram` sobe o consumo de RAM e derruba a sessao
quando ela acaba.

Os dois travamentos tinham gatilhos diferentes:

- **celula 3**: `nvidia-smi` via `subprocess.run` **sem timeout**. Com o
  runtime ja em swap, a chamada nunca retornava e a celula ficava pendurada
  sem imprimir nada. Todas as chamadas externas dos notebooks passaram a ter
  timeout.
- **celula 9**: a inferencia real, sem nenhum sinal de vida. Uma execucao
  lenta era indistinguivel de um travamento. A celula agora imprime a cada
  20 s a fila do ComfyUI e a VRAM livre.

### Correcoes

1. `preflight()` recebe `available_ram_gb` e tem um terceiro veredito,
   `BLOCKED — insufficient RAM`. RAM desconhecida nao vira `READY`.
2. Timeout em todas as chamadas de rede/subprocesso dos dois notebooks.
3. Monitor de progresso na celula de execucao.
4. `ram_gb: 16` marcado com `ram_estimated: true` e `[TEST REQUIRED]`: e
   valor conservador nosso, nao medicao.

### Consequencia: Qwen Q3_K_M fica BLOCKED no T4

    LongCat ........... BLOCKED - insufficient VRAM
    Z-Image ........... BLOCKED - insufficient VRAM
    Qwen Q3_K_M ....... BLOCKED - insufficient RAM   (era READY, errado)
    Qwen Q4_0 ......... BLOCKED - insufficient RAM
    Pony .............. READY  (research_only)

Nenhum requisito foi reduzido para caber, e nenhum fallback automatico foi
adicionado. **A escolha do proximo passo e humana** — ver o relatorio ao
usuario.

## RAM DIAGNOSTIC — medir em vez de estimar

O bloqueio do Qwen Q3_K_M no T4 vem de `ram_gb: 16`, que e uma **estimativa
conservadora nossa**, nunca medida. O T4 tem ~12.7 GB. Antes de decidir
qualquer coisa, e preciso saber se a estimativa procede.

### O bloqueio continua; a estimativa e que fica sob teste

`preflight()` separa tres numeros que antes se confundiam:

    EXPECTED RAM (estimated) : 16.0 GB     <- valor nosso, nao medido
    AVAILABLE RAM            : 12.7 GB     <- medido no runtime
    OBSERVED PEAK RAM        : nunca medido — rode o RAM DIAGNOSTIC

O status virou `BLOCKED — insufficient RAM (estimated)`. O sufixo sai quando
houver medicao. **O requisito continua 16 GB**: nada foi reduzido para caber.

### Como rodar

Celula 3, marcar `prosseguir_apenas_para_medir_ram`. Isso **nao** remove o
bloqueio: libera so a celula 10. A porta e condicionada a
`PF.blocked_by_ram and ram_estimated` — bloqueio por VRAM ou disco continua
terminal, porque la o numero e medido e nao ha o que descobrir.

A celula 9 (benchmark oficial) permanece recusando sob bloqueio.

### O que e medido

`scripts/chibi/memprobe.py` amostra em thread daemon (1-5 s): RAM total,
disponivel e usada, RSS do Python, RSS do processo ComfyUI e filhos, swap
total e usada, VRAM livre e usada. Cada amostra carrega a **fase**
(`COMFYUI_BOOT`, `MODEL_LOAD`, `TEXT_ENCODER`, `VAE`, `WORKFLOW_PREP`,
`QUEUE`, `INFERENCE`, `UNLOAD`), o que permite dizer *onde* o consumo
estourou — e disso depende a escolha entre trocar de runtime e trocar o
text encoder.

Protecoes: `nvidia-smi` com timeout, heartbeat a cada 20 s, watchdog que
encerra a espera e marca `TIMEOUT`, e evento `RAM_PRESSURE` registrado em
vez de congelamento silencioso. O watchdog **nao tenta resolver** o OOM.
Erro no coletor nunca derruba a execucao medida.

### Conclusao

| conclusao | criterio |
|---|---|
| `FIT` | terminou, sem swap, folga >= 1.5 GB |
| `BORDERLINE` | terminou, sem swap, folga < 1.5 GB |
| `DOES_NOT_FIT` | OOM/freeze/timeout, **ou** swap > 0.5 GB |
| `INCONCLUSIVE` | sem amostras ou execucao nao concluida |

Swap usada conta como `DOES_NOT_FIT` mesmo se a execucao terminar: terminar
nao prova que coube. A conclusao e sobre **caber**, nada mais — nao aprova
o modelo nem escolhe runtime. Isso e humano.

Saida em `experiments/model_eval/model_only/<model>/<run>/ram_diagnostic.json`.

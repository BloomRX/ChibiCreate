# Experimento FLUX → Qwen (avaliação, não produção)

Testa se o Qwen-Image-Edit-2511 consegue **corrigir o DESIGN** que o FLUX
reinterpreta, sem destruir STYLE nem IDENTITY.

> Fase exclusivamente de avaliação. Não é Flow 02, não produz `master.png`,
> nenhum artefato é aprovado.

## Contexto

O FLUX entrega STYLE e IDENTITY bons, mas reinterpreta roupa/acessórios.
Adicionar referências (run_003, 3 refs) **não resolveu** sozinho. A hipótese
agora é usar o Qwen como *refiner* de um chibi já pronto.

## Os três testes

| | Pipeline | image1 (editada) | image2 | image3 |
|---|---|---|---|---|
| **A** | Original → Qwen | `full_body` | — | — |
| **B** | Original → FLUX → Qwen | saída FLUX | `full_body` | — |
| **C** | Original → FLUX → Qwen | saída FLUX | `full_body` | `outfit` |

**A** mede o Qwen sozinho. **B** e **C** medem o encadeamento; a diferença
entre eles isola o efeito de uma referência a mais.

### Limite estrutural do TESTE C

`TextEncodeQwenImageEditPlus` é node **Core** e aceita **3 imagens**. Com a
saída do FLUX ocupando `image1`, sobram **2 slots** para 3 referências
(`full_body` + `face` + `outfit`). **Não cabe.**

O teste C roda com `full_body + outfit` — priorizando o design da roupa, que
é o alvo. Passar as três aborta com erro explícito, sem fallback:

```
ERRO: workflow comporta 2 referencia(s) extra(s), mas foram passadas 3.
A referencia #4 seria IGNORADA silenciosamente. Nenhum fallback aplicado.
```

Para 4+ imagens seria preciso o custom node `Comfyui-QwenEditUtils`
(até 5) — **não instalado**, exigiria autorização.

## Comandos (Colab, após o ComfyUI subir)

Validar antes de gastar GPU:

```bash
python -m scripts.chibi.cli comfy validate --env cloud \
    --workflow experimental/qwen_edit_multiref
```

Prompt do Qwen (usar **exatamente** este na primeira rodada):

```bash
QP="Preserve the exact same character identity, face, hair, eyes, horns, body proportions, color palette, and overall chibi style from the input image. Preserve the original character design shown in the reference images, especially the clothing, cape, golden ornaments, accessories, and their shapes and placement. Do not redesign, replace, modernize, sexualize, simplify away, or invent clothing elements. Redraw the character as a clean polished game/gacha chibi character while keeping the original outfit design recognizable and faithful to the references. Only make changes necessary to adapt the original design naturally to the chibi proportions. Full body, front-facing, clean silhouette, consistent lineart, polished game art, soft shading, highly readable at small size. The output should look like the same original character converted into chibi form, not a new character inspired by the original."
```

**TESTE A** — Qwen sozinho:

```bash
python -m scripts.chibi.cli experiment model-eval \
    --model qwen-refiner --character waifu_001 --seed 42 \
    --input reference/full_body.png --prompt "$QP"
```

**TESTE B** — FLUX → Qwen, 1 referência. `FLUX_OUT` é o `output.png` do
run FLUX escolhido como base:

```bash
FLUX_OUT=experiments/model_eval/flux2_klein_4b/run_001/output.png

python -m scripts.chibi.cli experiment model-eval \
    --model qwen-refiner --character waifu_001 --seed 42 \
    --input "$FLUX_OUT" --ref reference/full_body.png --prompt "$QP"
```

**TESTE C** — FLUX → Qwen, 2 referências:

```bash
python -m scripts.chibi.cli experiment model-eval \
    --model qwen-refiner --character waifu_001 --seed 42 \
    --input "$FLUX_OUT" \
    --ref reference/full_body.png --ref reference/outfit.png \
    --prompt "$QP"
```

Cada execução grava em `experiments/model_eval/qwen_image_edit_2511/run_NNN/`:
`output.png`, `recipe.json`, `workflow.resolved.json` e as imagens de entrada.

## O que o recipe registra

Modelo, revision, `model_sha256`, licença, workflow + sha256, seed, prompt
completo, sampling, quantização/dtype, GPU, VRAM, CUDA, versão do ComfyUI,
tempos, custo, `reference_count`, e por referência: `role`, `sha256` e
`pixel_sha256`.

**`output_pixel_sha256` é campo separado de `output_sha256`.** Reencodar um
PNG muda os bytes e mantém a imagem; misturar os dois faria "arquivo
diferente" parecer "imagem diferente".

A URL do ComfyUI é redigida — tokens de túnel nunca entram no recipe.

## Avaliação

Três eixos separados (`docs/style-vs-identity.md`), **OVERALL não é média**:

- **STYLE** — proporção, simplificação facial, olhos, cabelo, rendering,
  shading, silhueta, cara de personagem de jogo
- **IDENTITY** — rosto, cabelo, cor dos olhos, chifres, traços distintivos
- **DESIGN PRESERVATION** — roupa, mangas, capa, ornamentos dourados,
  calçado, acessórios, formas principais

Perguntas desta rodada:

1. O Qwen sozinho (A) preserva design melhor que o FLUX?
2. FLUX → Qwen (B) melhora o resultado do FLUX?
3. A referência extra (C vs B) melhora DESIGN PRESERVATION?
4. O Qwen destrói STYLE ou IDENTITY ao tentar preservar DESIGN?
5. O tempo/custo extra do segundo estágio compensa?

**Nenhum vencedor automático.** O agente produz evidência; a decisão é humana.

## Limitações conhecidas

- `denoise` controla quanto da base é preservado e **não foi calibrado**.
  Muito alto redesenha; muito baixo não corrige nada. `[TEST REQUIRED]`
- Nenhuma negativa foi adicionada ao prompt, por instrução — medir o
  comportamento base primeiro.
- Testes A/B/C **não** compartilham seed efetiva entre estágios distintos:
  seed 42 no Qwen não reproduz o ruído do FLUX.
- O TESTE C não usa `face.png` (limite de 3 slots).
- Determinismo **não** é afirmado; `compare_runs` mede e reporta.


## PRIMARY EXPERIMENT (correção pós-inspeção visual)

Após inspeção visual dos resultados FLUX, o usuário determinou que
`run_003/output.png` é a entrada correta do estágio Qwen — **não**
`run_001/output.png`.

| | chibi | design preservado |
|---|---|---|
| `run_001` | mais forte | reinterpretou mais roupa e design |
| **`run_003`** | menos chibi | preserva estrutura, roupa, capa, cabelo, ornamentos |

O estágio Qwen cobre exatamente o que falta ao `run_003`: partir de um design
fiel e aproximar as proporções do chibi alvo. Partir do `run_001` seria pedir
ao Qwen que reconstruísse um design já perdido no estágio 1.

```
Original -> FLUX run_003 (já existe) -> Qwen -> resultado final
```

- `primary_image_role`: `stage1_output`
- referências: `full_body.png`, `outfit.png`
- `face.png` fica fora: `TextEncodeQwenImageEditPlus` (Core) comporta 3
  imagens no total, e a principal já ocupa `image1`.

Objetivo declarado: manter a identidade do `run_003`, preservar o design
original, aproximar as proporções do chibi, não inventar roupa e manter
cabelo, chifres e ornamentos.

### Rodadas

| pasta | pipeline | image1 | image2 | image3 |
|---|---|---|---|---|
| `primary_run003_2refs` | **PRIMARY** | saída run_003 | `full_body` | `outfit` |
| `cmp_a_qwen_only` | Qwen sozinho | `full_body` | — | — |
| `cmp_b_run003_1ref` | sem `outfit` | saída run_003 | `full_body` | — |
| `cmp_c_run001_2refs` | entrada run_001 | saída run_001 | `full_body` | `outfit` |

A/B/C são **comparação**, não candidatos concorrentes: A isola o Qwen sozinho,
B isola o efeito da segunda referência, C isola o efeito de trocar a entrada
do estágio 1 — ou seja, mede a própria decisão registrada acima.

A comparação C é pulada automaticamente se `run_001` não vier no ZIP.

### Limitações desta rodada

- A escolha do `run_003` vem de **inspeção visual humana**, não de métrica.
- `denoise` continua **não calibrado** (`BASELINE_HYPOTHESIS`).
- Um run por rodada: não afirma determinismo.
- `face.png` fora de todas as rodadas.


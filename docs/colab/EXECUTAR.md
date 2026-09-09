# Como executar a avaliação do FLUX.2 klein 4B no Colab

Passo a passo operacional. O ambiente do agente **não tem GPU** — esta é a
única via de execução real hoje.

**Nenhuma credencial é pedida em lugar nenhum.** O repositório é público e o
notebook só faz `git clone` de leitura. Se algum passo pedir token ou senha,
pare: não faz parte deste fluxo.

## Referência

| | |
|---|---|
| Notebook | `docs/colab/flux2_klein_4b_eval.ipynb` |
| Repositório | `https://github.com/BloomRX/ChibiCreate` |
| **Branch** | **`arena/01a07ece-chibicreate`** |
| Revision mínima | `b54ee3a` (ou posterior) |
| Modelo | FLUX.2 [klein] 4B — `e7b7dc27f91deacad38e78976d1f2b499d76a294` |
| Personagem | `waifu_001` |
| Seed | 42 |

> A branch importa: `main` está em `65b4bb7` e **não** contém a pipeline.

## A — Abrir o notebook

Em <https://colab.research.google.com> → aba **GitHub** → cole:

```
https://github.com/BloomRX/ChibiCreate/blob/arena/01a07ece-chibicreate/docs/colab/flux2_klein_4b_eval.ipynb
```

## B — Selecionar GPU NVIDIA

`Ambiente de execução` → `Alterar o tipo de ambiente` → **T4** (ou melhor).

A primeira célula detecta e registra a GPU real. **Não assuma T4** — o Colab
não garante o modelo. Se a VRAM for insuficiente, o notebook para com
`COLAB_GPU_INSUFFICIENT`; isso é resultado válido, não falha.

## C — Clonar (célula de setup)

Já vem com a branch correta. Confirme na saída que não é `65b4bb7`.

## D — Confirmar o input

A célula verifica `characters/waifu_001/reference/full_body.png` e o sha256:

```
2fdcd5f428f5980d63e31d4bf4a67aecbc11c1b101c19ca75f819db616cb8177
```

Hash diferente = arte errada. **Pare.**

## E — Iniciar o ComfyUI

Baixa ComfyUI (revision fixa) e os 3 arquivos do klein (~16 GB): diffusion
model, text encoder Qwen3-4B e VAE. Sobe em `127.0.0.1:8188`.

Os pesos ficam **só** no Colab. Nunca entram no Git.

## F, G, H — Verificações antes de gastar GPU

```bash
chibi comfy status      # servidor responde?
chibi comfy preflight   # modelos no lugar, ambiente coerente?
chibi comfy validate    # nomes de node conferidos contra /object_info
```

`validate` é o passo que confirma o workflow contra o servidor real. **Se
reprovar, pare** e reporte `node / expected / actual`. Não edite o workflow
para "fazer passar" — isso mascara incompatibilidade.

## I, J — RUN 001 e RUN 002

Single-reference (`full_body`), workflow `v1`, seed 42. Idênticos de
propósito: **medem repetibilidade do ambiente real**.

Hashes de saída podem divergir mesmo com tudo igual. Isso é observação, não
defeito — o projeto não promete determinismo.

## K — RUN 003 (multi-referência)

Workflow `v2`, três referências:

```bash
--workflow-version v2 --ref reference/face.png --ref reference/outfit.png
```

A célula **valida a cadeia antes de executar**: se alguma referência não
alcançar `KSampler.positive`, ela aborta. Sem essa checagem, uma referência
ignorada passaria despercebida — o resultado sairia normal, só que errado.

Única variável vs. runs 001/002: `reference_count` 1 → 3. Há teste
automatizado travando cfg, steps, sampler, prompt e resolução entre v1 e v2.

## Depois — baixar e parar

A última célula empacota `experiments/` em zip. Baixe: a sessão é efêmera.

**Pare após o RUN 003.** Nada de 8 candidatos, `master.png`, LoRA, ControlNet,
Flow 02 ou animação.

Commite o zip descompactado em `experiments/` e preencha
`docs/model-eval/ficha-avaliacao.md` — os três eixos (STYLE, IDENTITY,
DESIGN PRESERVATION) e o OVERALL, que **não** é média automática.

## Limitações a registrar honestamente

- Sessão efêmera: GPU e tempos valem só para aquela execução.
- `cost: 0` é o observado no Colab; **não extrapolar** para produção.
- VRAM vem de `/system_stats` (livre antes − depois): aproximação, **não** é
  pico instantâneo.
- A ordem da cadeia no `v2` termina em `outfit`. É escolha, não resultado
  medido — pode influenciar o peso relativo das referências.

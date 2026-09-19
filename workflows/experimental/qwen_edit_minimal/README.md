# Workflow experimental — Qwen-Image-Edit-2511 (mínimo)

**Fase 3A.** Prova que o motor executa de forma controlável pela nossa CLI.
**Não** é o Flow 02 e **não** produz Chibi Master.

## Estado

`[TEST REQUIRED]` — **este grafo nunca foi executado.** Não há GPU neste
ambiente (ver ADR-006). As classes de node seguem o template oficial
`image_qwen_image_edit_2511` do ComfyUI, mas só uma execução real confirma
nomes e sockets.

Antes da primeira execução de verdade:

```bash
chibi comfy validate --workflow experimental/qwen_edit_minimal
```

Isso compara cada `class_type` contra o `/object_info` do servidor e falha
com a lista exata do que estiver faltando, em vez de estourar no meio da
execução.

## Grafo

```
UNETLoader ──────────┐
CLIPLoader ──┬───────┤
VAELoader ───┤       │
LoadImage ───┴─> TextEncodeQwenImageEditPlus (+)
             └─> TextEncodeQwenImageEditPlus (−)
                          ↓
EmptySD3LatentImage ─> KSampler ─> VAEDecode ─> SaveImage
```

`UNETLoader` + `CLIPLoader` + `VAELoader` em vez de `CheckpointLoaderSimple`
porque o Qwen-Image-Edit é distribuído em componentes separados no ComfyUI, e
porque assim dá para escolher `weight_dtype` (fp8) sem trocar de arquivo.

## Placeholders

Substituídos pela CLI. Os que vêm de `config/` estão marcados.

| Placeholder | Origem |
|---|---|
| `%%UNET_NAME%%` `%%CLIP_NAME%%` `%%VAE_NAME%%` | `config/environments/<env>.yaml` → `comfyui.models` |
| `%%WEIGHT_DTYPE%%` | idem (`fp8_e4m3fn`, `default`, …) |
| `%%INPUT_IMAGE%%` | nome devolvido pelo upload |
| `%%PROMPT%%` `%%NEGATIVE_PROMPT%%` | argumento da CLI |
| `%%SEED%%` `%%STEPS%%` `%%CFG%%` `%%SAMPLER%%` `%%SCHEDULER%%` `%%DENOISE%%` | argumento da CLI / defaults do experimento |
| `%%WIDTH%%` `%%HEIGHT%%` | `config/project.yaml` → `resolution.master` |
| `%%OUTPUT_PREFIX%%` | gerado por execução |

## Regra de identidade

O prompt **não deve descrever rosto nem cabelo**. Descrição textual compete
com a imagem de referência e é a causa nº 1 de perda de identidade. A
identidade vem da imagem em `image1`; o prompt diz apenas o que **mudar**.

## Versionamento

Nunca editar `v1.json` depois de uma execução registrada em recipe — o
`workflow_sha256` do recipe deixaria de bater. Criar `v2.json`.

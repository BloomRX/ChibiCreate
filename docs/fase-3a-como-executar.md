# Fase 3A — como executar quando houver GPU

O código está pronto e testado. Falta apenas um backend ComfyUI com GPU.
Ver `docs/decisions/ADR-006-execucao-qwen-ambiente.md` para o porquê.

## 1. Subir um ComfyUI com GPU

Requisitos mínimos: **24 GB de VRAM** (fp8) e ~60 GB de disco.

Modelos que o servidor precisa ter (download exige **aprovação humana** —
o agente não baixa checkpoints):

| Pasta no ComfyUI | Arquivo |
|---|---|
| `models/unet/` | `qwen_image_edit_2511_fp8_e4m3fn.safetensors` |
| `models/clip/` | `qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| `models/vae/` | `qwen_image_vae.safetensors` |

Repositório oficial: `Qwen/Qwen-Image-Edit-2511`, revisão
`6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9`, Apache-2.0.

Se os nomes no servidor forem outros, ajuste `comfyui.models` em
`config/environments/cloud.yaml`. **Não** edite o código.

## 2. Apontar a CLI para ele

```bash
export CHIBI_COMFY_URL=http://<host>:8188
export CHIBI_COMFY_TOKEN=<token>     # se o backend exigir
```

## 3. Conferir antes de gastar GPU

```bash
chibi comfy status    --env cloud   # servidor vivo? qual GPU? quanta VRAM?
chibi comfy preflight --env cloud   # TUDO pronto? (endpoint+GPU+nodes+modelos)
chibi comfy validate  --env cloud   # so os nodes do workflow
```

`comfy preflight` é a checagem completa e é a recomendada: cobre endpoint,
VRAM, nodes, sockets e presença dos arquivos de modelo, sem gastar GPU.
Ver `docs/fase-3b-como-conectar-gpu.md`.

`comfy validate` compara cada `class_type` contra o `/object_info` do
servidor. É a checagem que evita descobrir um nome de node errado no meio de
uma execução paga.

## 4. Primeiro experimento

```bash
chibi experiment qwen-edit \
  --character waifu_001 \
  --input reference/full_body.png \
  --prompt "full body chibi proportions, large head, small body" \
  --env cloud --seed 42
```

> **Regra de identidade:** o prompt diz o que **mudar**. Não descreva rosto
> nem cabelo — texto compete com a imagem de referência e é a causa nº 1 de
> perda de identidade.

Saída em `experiments/qwen_image_edit_2511/run_NNN/`: `input.png`,
`output.png`, `recipe.json`, `workflow.resolved.json`.

## 5. Teste de reprodução (seção 9 da spec)

```bash
chibi experiment qwen-edit --character waifu_001 --prompt "..." --seed 42 --env cloud
chibi experiment compare \
  experiments/qwen_image_edit_2511/run_001 \
  experiments/qwen_image_edit_2511/run_002
```

O comando compara seed, prompt, parâmetros, revisão do modelo, workflow,
quantização, input e device — e diz se os **bytes** bateram. Não afirmamos
determinismo: medimos e registramos.

## 6. Testes de integração

```bash
CHIBI_COMFY_URL=http://<host>:8188 .venv/bin/python tests/test_comfy.py
```

Com a variável definida, os dois `[integration test]` deixam de ser pulados
e rodam contra o servidor real.

## O que continua proibido

Nada aqui aprova arte. O recipe nasce `approval_status: "experimental"` e
nenhum caminho de código o promove. Chibi Master é decisão humana.

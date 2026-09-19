# Como conectar uma GPU remota

A Fase 3B está `[BLOCKED]` só por falta de um ComfyUI acessível. **Nenhuma
alteração de código é necessária** — basta apontar a URL.

---

## A) Obter um ComfyUI acessível por HTTP

Você precisa de um ComfyUI rodando numa máquina com GPU NVIDIA, alcançável
por HTTP a partir daqui. Requisitos:

| Item | Valor |
|---|---|
| VRAM | ≥ 24 GB (definido em `cloud.yaml` → `requirements.min_vram_gb`) |
| Disco | ~60 GB para os pesos |
| Modelo | `Qwen/Qwen-Image-Edit-2511`, revisão `6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9`, Apache-2.0 |

Arquivos que o servidor precisa ter:

| Pasta | Arquivo esperado |
|---|---|
| `models/unet/` (ou `diffusion_models/`) | `qwen_image_edit_2511_fp8_e4m3fn.safetensors` |
| `models/clip/` (ou `text_encoders/`) | `qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| `models/vae/` | `qwen_image_vae.safetensors` |

Se os nomes forem outros, ajuste `comfyui.models` em
`config/environments/cloud.yaml`. **Não edite o código.**

O ComfyUI precisa aceitar conexões externas — normalmente
`--listen 0.0.0.0`. Se estiver atrás de firewall, um túnel SSH resolve:

```bash
ssh -N -L 8188:localhost:8188 usuario@servidor-gpu
# a URL passa a ser http://127.0.0.1:8188
```

## B) Definir a URL

```bash
export CHIBI_COMFY_URL=http://<host>:8188
export CHIBI_COMFY_TOKEN=<token>     # só se o backend exigir
```

> **Segurança.** Nunca escreva URL ou token em arquivo versionado. O
> `cloud.yaml` guarda apenas o *nome* da variável. URLs com credencial
> embutida (`https://user:senha@host`) são redigidas antes de qualquer log,
> mensagem de erro ou recipe.

## C) O servidor responde?

```bash
chibi comfy status --env cloud
```

Mostra versão do ComfyUI, PyTorch, GPU e VRAM livre.

## D) Está tudo pronto? (recomendado)

```bash
chibi comfy preflight --env cloud
```

Verifica **sem gastar GPU**: endpoint, `/object_info`, versão, GPU, VRAM,
nodes do workflow, sockets de cada node e presença dos arquivos de modelo.

Códigos possíveis:

| Código | Significado |
|---|---|
| `OK` | pronto |
| `NOT_CONFIGURED` | falta `CHIBI_COMFY_URL` |
| `ENDPOINT_UNREACHABLE` | servidor não respondeu |
| `OBJECT_INFO_MISSING` | `/object_info` indisponível |
| `WORKFLOW_INCOMPATIBLE` | falta node, ou input não reconhecido |
| `MODEL_MISSING` | arquivo de modelo ausente no servidor |
| `GPU_MISSING` | nenhuma GPU reportada |
| `GPU_INSUFFICIENT` | VRAM abaixo do mínimo |
| `UNKNOWN` | a API não informou — **não bloqueia**, mas fica visível |

Numa incompatibilidade de socket, ele imprime exatamente:

```
node    : 8 (KSampler)
expected: denoise
actual  : ['cfg', 'latent_image', 'model', ...]
```

Corrija o workflow **só com essa evidência na mão**. Não mascare a
incompatibilidade.

## E) Conferir só o workflow

```bash
chibi comfy validate --env cloud
```

## F) Primeira execução real

```bash
chibi experiment qwen-edit \
  --character waifu_001 \
  --seed 42 \
  --env cloud \
  --prompt "Transform this character into a clean stylized chibi full-body character, preserving the same identity, black hair, red eyes, horns, black outfit, long black cape and golden ornaments."
```

Saída em `experiments/qwen_image_edit_2511/run_NNN/`: `input.png`,
`output.png`, `recipe.json`, `workflow.resolved.json`.

Rode **duas vezes** com a mesma seed e compare:

```bash
chibi experiment compare \
  experiments/qwen_image_edit_2511/run_001 \
  experiments/qwen_image_edit_2511/run_002
```

## O que continua valendo

- O resultado nasce `approval_status: "experimental"`. Não é Chibi Master.
- Nenhum código promove artefato a aprovado — isso é decisão humana.
- Baixar os pesos exige **autorização explícita**; o agente não baixa
  checkpoints sozinho.
- Se o Qwen não executar, a fase é `BLOCKED`. Não se troca de modelo.

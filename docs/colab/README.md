# Colab — infraestrutura EXPERIMENTAL e TEMPORÁRIA

`qwen_edit_2511_setup.ipynb` existe para uma finalidade única: destravar a
**primeira execução real** do Qwen-Image-Edit-2511 na FASE 3B.

**Colab não é, e não vai virar, infraestrutura do projeto.** A arquitetura
permanece:

```
LOCAL → Python CLI → REMOTE COMFYUI → NVIDIA GPU → Qwen → output → LOCAL
```

O Colab apenas ocupa, por uma sessão, a caixa "NVIDIA GPU". Nenhum código do
projeto sabe que o Colab existe: o notebook exporta `CHIBI_COMFY_URL` e chama
a CLI que já existe desde a FASE 3A.

## Antes de abrir o notebook — o problema da VRAM

| Tier | GPU | VRAM | Serve? |
|---|---|---|---|
| Gratuito | T4 | 16 GB (~15 utilizáveis) | **não** |
| Pro | L4 | 22.5 GB | provavelmente — `[TEST REQUIRED]` |
| Pro+ | A100 | 40 GB | sim |

A menor variante oficial do 2511 tem **20.5 GB só de pesos**. O Colab gratuito
não comporta este experimento. A célula 1 detecta e para com
`COLAB_GPU_INSUFFICIENT` — esse é o comportamento correto.

Não contornar com inferência em CPU, quantização comunitária ou troca de
modelo. Se a GPU não serve, o resultado do experimento é "GPU não serve", e a
FASE 3B continua `BLOCKED`.

## Correção de bug encontrada ao montar o notebook

O `cloud.yaml` apontava para `qwen_image_edit_2511_fp8_e4m3fn.safetensors`.
**Esse arquivo não existe.** Conferido no repositório oficial
`Comfy-Org/Qwen-Image-Edit_ComfyUI` (sha `984166f6`): existe `fp8_e4m3fn` para
o **2509** e para o Qwen-Image-Edit original, mas as variantes do **2511** são
`bf16`, `fp8mixed` e `int8_convrot`.

Era um nome plausível por analogia, nunca confrontado com a realidade — exatamente
o tipo de erro que a marcação `[TEST REQUIRED]` no arquivo previa. Corrigido
para `fp8mixed`, com os SHA256 reais dos três arquivos registrados em
`config/models.lock.yaml`.

Sem essa correção o preflight falharia com `MODEL_MISSING` já no Colab, depois
de ~30 GB de download.

## Procedência dos pesos

Os três arquivos vêm de repositórios **Comfy-Org**, Apache-2.0, redistribuição
oficial em arquivo único para ComfyUI. **Não são quantizações comunitárias
arbitrárias** — a distinção importa para a regra da seção 4.

| Arquivo | Repo | Tamanho |
|---|---|---|
| `qwen_image_edit_2511_fp8mixed` | `Comfy-Org/Qwen-Image-Edit_ComfyUI` @ `984166f6` | 20.5 GB |
| `qwen_2.5_vl_7b_fp8_scaled` | `Comfy-Org/Qwen-Image_ComfyUI` @ `7beb7b64` | 9.4 GB |
| `qwen_image_vae` | `Comfy-Org/Qwen-Image_ComfyUI` @ `7beb7b64` | 0.25 GB |

SHA256 de cada um em `models.lock.yaml`, conferidos pela célula 4b após o
download. `weights.verified` continua `false` até um download real confirmar.

> **Nota de procedência:** o repo `Comfy-Org/Qwen-Image-Edit_ComfyUI` declara
> como base também `FireRedTeam/FireRed-Image-Edit-1.0`, por hospedar aquele
> modelo. Os arquivos `qwen_image_edit_2511_*` derivam de
> `Qwen/Qwen-Image-Edit-2511` (Apache-2.0). A conferência de que o peso
> corresponde à revisão `6f3ccc0b…` é **humana** — o ComfyUI não expõe isso.

## Limitações do Colab

- Sessão efêmera: tudo em `/content` some ao desconectar. **A célula 11 é
  obrigatória**, senão os outputs se perdem.
- GPU não garantida: pode mudar entre sessões. Por isso a célula 1 registra o
  que foi de fato alocado, sem presumir.
- Desconexão por inatividade interrompe execuções longas.
- Custo não é observável por execução; registramos `cost: 0` com a ressalva de
  não extrapolar.

## Ordem de execução

Células 1 → 11, na ordem. A célula 1 (GPU) e a célula 6 (preflight) são
**portões**: se falharem, pare.

Termina em duas execuções reais + `[HUMAN REVIEW REQUIRED]`.

Não seguir para Flow 02, candidatos, `master.png`, ControlNet, LoRA ou
animação.

## Estado

`docs/fase-3b-checklist.md` é a lista de 15 itens a marcar.
**FASE 3B só vira COMPLETE após duas execuções reais** — não por este notebook
existir.

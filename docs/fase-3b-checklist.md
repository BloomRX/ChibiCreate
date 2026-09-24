# FASE 3B — checklist de execução remota

Marcar item por item, **na ordem**, quando houver uma GPU NVIDIA e um endpoint
ComfyUI real. Cada item é uma verificação objetiva, não uma impressão.

**Regra de parada:** se um item falhar, pare ali e registre o erro. Não pule
para o seguinte, não troque de modelo, não force execução local.

```
[ ] endpoint ComfyUI acessível
[ ] GPU NVIDIA detectada
[ ] VRAM registrada
[ ] CUDA registrada
[ ] ComfyUI version registrada
[ ] /object_info acessível
[ ] workflow validado
[ ] Qwen model encontrado
[ ] revision correta
[ ] primeira execução real
[ ] output recuperado
[ ] recipe criada
[ ] segunda execução real
[ ] comparação concluída
[ ] human review
```

---

## Como verificar cada item

Os nove primeiros itens são cobertos por **um único comando**:

```bash
export CHIBI_COMFY_URL=http://<host>:8188
chibi comfy preflight --env cloud
```

| Item | Como comprovar | Código de falha |
|---|---|---|
| endpoint ComfyUI acessível | `chibi comfy status --env cloud` responde | `NOT_CONFIGURED`, `ENDPOINT_UNREACHABLE` |
| GPU NVIDIA detectada | `/system_stats` → `devices[].type == "cuda"` | `GPU_MISSING` |
| VRAM registrada | `vram_total` presente e ≥ o exigido pelo dtype | `GPU_INSUFFICIENT` |
| CUDA registrada | derivada de `pytorch_version` (`2.6.0+cu124` → `12.4`) | `UNKNOWN` (não bloqueia) |
| ComfyUI version registrada | `/system_stats` → `system.comfyui_version` | `UNKNOWN` (não bloqueia) |
| `/object_info` acessível | endpoint responde JSON | `OBJECT_INFO_MISSING` |
| workflow validado | todo `class_type` existe e todo socket confere | `WORKFLOW_INCOMPATIBLE` |
| Qwen model encontrado | os 3 arquivos de `cloud.yaml` aparecem no servidor | `MODEL_MISSING` |
| revision correta | conferida por humano contra `models.lock.yaml` | — |

> `UNKNOWN` significa "o servidor não informou", não "está errado". **Não
> bloqueia** a execução; fica registrado como lacuna no recipe.

**Revisão (item 9):** o ComfyUI não expõe a revisão do repositório de origem.
A conferência é humana: o peso instalado deve vir de
`Qwen/Qwen-Image-Edit-2511` na revisão `6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9`
(Apache-2.0). Se veio de um repositório de quantização de terceiros, isso é
**outra procedência e outra licença** — registre no recipe antes de seguir.

### Itens 10–14 — execução

| Item | Como comprovar |
|---|---|
| primeira execução real | `chibi experiment qwen-edit --character waifu_001 --seed 42 --env cloud` termina com exit 0 |
| output recuperado | existe um PNG com dimensões e modo esperados |
| recipe criada | `recipe.json` com `artifact_sha256`, `input_hashes`, `workflow_sha256`, `gpu`, `cuda`, `timings` |
| segunda execução real | mesma seed, mesmo prompt, mesmo workflow |
| comparação concluída | `chibi experiment compare <run_001> <run_002>` |

> Hash diferente entre as duas execuções é **resultado válido**, não falha.
> O objetivo é medir a variação, não provar determinismo — que nunca foi
> prometido.

### Item 15 — human review

**[HUMAN REVIEW REQUIRED]** — fora do alcance do agente.

O agente pode reportar se traços presentes na arte-fonte continuam
identificáveis. Não pode decidir se o resultado é bom, escolher entre duas
saídas nem aprovar um Chibi Master. Isso é decisão humana.

---

## Depois do item 15

Pare. A FASE 3B termina em "duas execuções reais + revisão humana".

Não seguir para: Flow 02, geração de candidatos, `master.png`, ControlNet,
LoRA ou animação — nada disso faz parte desta fase.

---

Passo a passo operacional: `docs/fase-3b-runbook.md`.
Motivo do bloqueio atual: `docs/fase-3b-BLOCKED.md`.

# FASE 3B — BLOCKED

**Data:** 2026-09-08 · **Status:** `[BLOCKED]` — parado conforme a seção 20 da spec.

> A Fase 3B só é SUCCESS com GPU cloud funcionando. Não há como provisionar
> GPU a partir deste ambiente. Parei e reportei, sem improvisar outro modelo
> e sem forçar execução local.

---

## Por que está bloqueado

### 1. Nenhuma credencial de cloud

```
env | grep -i (runpod|vast|modal|aws|gcp|azure|replicate|hf_|token)
  -> GH_TOKEN, GITHUB_TOKEN     (apenas GitHub)

~/.aws  ~/.config/gcloud  ~/.runpod  ~/.modal.toml  ~/.vast_api_key
  -> nenhum existe
```

### 2. Nenhuma CLI de provider

`runpodctl` `aws` `gcloud` `az` `modal` `vastai` `docker` `kubectl`
`terraform` — **todas ausentes**. Só existe `ssh`.

### 3. Egress bloqueado para todos os providers

```
RunPod API    BLOQUEADO      PyPI      HTTP 200
Vast.ai       BLOQUEADO      GitHub    HTTP 200
Modal         BLOQUEADO
Replicate     BLOQUEADO
HuggingFace   BLOQUEADO   <- impede baixar os pesos mesmo com GPU
HF CDN        BLOQUEADO
```

A rede deste sandbox libera apenas PyPI e GitHub. Mesmo que houvesse GPU
local, **os pesos não poderiam ser baixados**: o Hugging Face está bloqueado.

### 4. Hardware local (inalterado desde o ADR-006)

Sem GPU · 3 GB de RAM · 20 GB de disco, contra 57,7 GB de pesos.

### Conclusão

São **quatro bloqueios independentes**, e cada um sozinho já impede a fase.
A autorização de download dos pesos (seção 7) não pôde ser exercida porque o
host de download está inacessível.

---

## O que a seção 20 exige, e o estado de cada item

| # | Critério | Estado |
|---|---|---|
| 1 | GPU cloud funcionando | ❌ impossível neste ambiente |
| 2 | ComfyUI funcionando | ❌ depende de (1) |
| 3 | Qwen carregando | ❌ depende de (1) |
| 4 | Workflow validado contra `/object_info` | ⚠️ mecanismo pronto e testado; não confrontado com servidor real |
| 5 | Primeira execução real | ❌ depende de (1) |
| 6 | Segunda execução real | ❌ depende de (1) |
| 7 | Output recuperado | ⚠️ caminho completo testado contra backend simulado |
| 8 | Recipes criadas | ✅ estrutura completa, incluindo os campos novos |
| 9 | Hashes registrados | ✅ input e output |
| 10 | VRAM medida | ⚠️ instrumentação pronta; sem GPU para medir |
| 11 | Tempo medido | ⚠️ instrumentação pronta |
| 12 | Custo estimado | ⚠️ cálculo pronto e testado |
| 13 | Resultado visual para revisão humana | ❌ depende de (1) |

---

## O que foi feito nesta fase (sem GPU)

A spec pedia campos de recipe (seção 14) e cobertura de erros (seção 16) que
**não** dependem de GPU. Isso foi implementado, para que a execução real, ao
acontecer, já grave tudo:

### Campos novos no recipe

`gpu` (nome, tipo, VRAM total, VRAM livre no início, nº de devices) ·
`vram_peak_bytes` · `cuda` · `execution_time` · `timings` (connect, upload,
execution, download, total) · `cost_estimate`.

Todos lidos **do próprio servidor**. Quando o backend não informa, o campo
fica `None`: um recipe que mente sobre hardware é pior que um incompleto.

### Honestidade das medições

- `vram_peak_bytes` é `vram_free` antes menos depois, via `/system_stats`.
  **Não é o pico instantâneo** durante a inferência — e o recipe diz isso no
  campo `vram_note`.
- `cost_estimate` traz, no próprio JSON: *"NÃO é custo de produção: exclui
  cold start, download de pesos, tempo ocioso e tentativas descartadas."*
- `cuda` é extraído de `pytorch_version` (`2.6.0+cu124` → `12.4`) quando o
  ComfyUI não expõe o campo diretamente.

### Cobertura de erros (seção 16)

| Erro exigido | Teste |
|---|---|
| ComfyUI offline | `test_comfyui_unavailable` |
| model missing / class_type inválido | `test_invalid_workflow_is_rejected` |
| workflow inválido | `test_empty_workflow_refused_before_network` |
| malformed input | `test_upload_missing_file` |
| timeout | `test_timeout_is_raised_and_explains` |
| empty output | `test_completed_without_image_is_an_error` |
| **OOM** | `test_oom_during_real_execution_is_readable` |
| retry infinito | `test_no_retry_on_failure` |

OOM produz `KSampler (8): CUDA out of memory` — legível, com o node
identificado. **Não há retry** em lugar nenhum: verificado por teste que
conta as submissões (exatamente 1) e por varredura do fonte.

### Execução ponta a ponta contra backend

Seis testes novos exercitam o caminho **não-dry-run** completo — upload,
submit, wait, download, medição, recipe — contra um ComfyUI simulado que fala
o protocolo real. Inclui o teste das duas execuções da seção 11 e a garantia
de que o servidor **nunca** recebe `%%PLACEHOLDER%%` cru.

**115 testes passando** (26 + 46 + 43).

---

## Como destravar

Qualquer uma das opções, **por decisão humana**:

1. **Fornecer um endpoint ComfyUI já rodando** (o mais simples):
   ```bash
   export CHIBI_COMFY_URL=http://<host>:8188
   export CHIBI_COMFY_TOKEN=<token>
   chibi comfy status --env cloud
   ```
   Basta que o host seja alcançável a partir deste sandbox.

2. **Liberar egress + credenciais** para um provider, e instalar a CLI dele.

3. **Executar noutro ambiente**: rodar `chibi experiment qwen-edit` de uma
   máquina com acesso à GPU. O código não depende deste sandbox — é o ponto
   do ADR-006.

O procedimento completo está em `docs/fase-3a-como-executar.md`.

# ADR-006 — Onde executar o Qwen-Image-Edit-2511

- **Data:** 2026-09-08
- **Status:** aceito
- **Fase:** 3A — infraestrutura ComfyUI

---

## Contexto

A Fase 3A pede para provar que o Qwen-Image-Edit-2511 executa de forma
controlável dentro da nossa infraestrutura. A primeira pergunta é onde.

### Ambiente medido (não presumido)

```
SO        : Debian GNU/Linux 12 (bookworm), kernel 6.1.158+
CPU       : Intel Xeon @ 2.60GHz — 2 vCPU
RAM       : 3.8 GB total / 3.6 GB disponível
Disco     : 20 GB livres
GPU       : NENHUMA
            nvidia-smi        -> command not found
            /dev/nvidia*      -> ausente
            /dev/dri          -> ausente
torch     : não instalado
Python    : 3.11.2
Rede      : PyPI OK · GitHub OK · huggingface.co BLOQUEADO
```

### Requisitos do modelo (fonte primária)

Endpoint `/api/models/Qwen/Qwen-Image-Edit-2511`, revisão
`6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9`:

- 20.430.401.088 parâmetros, BF16
- `usedStorage`: **57.715.696.541 bytes ≈ 57,7 GB**
- VRAM estimada: Q4_0 ~11,9 GB · FP8 ~20,5 GB · BF16 ~40,9 GB

## Decisão

**Não executar o Qwen neste ambiente.** Construir a infraestrutura completa,
testável sem GPU, e deixar a execução real para um backend com GPU.

A conta é simples e não tem contorno razoável:

| Recurso | Disponível | Necessário (mínimo) | Veredito |
|---|---|---|---|
| VRAM | 0 GB | ~11,9 GB (Q4_0) | impossível |
| RAM | 3,8 GB | ~20 GB (offload CPU) | impossível |
| Disco | 20 GB | 57,7 GB (BF16) | impossível |
| Acesso ao HF | bloqueado | necessário p/ baixar | impossível |

Qualquer uma dessas quatro linhas já bloqueia sozinha. Inferência em CPU com
2 vCPU e 3,8 GB de RAM não é "lenta": é inviável — o modelo não carrega.

### Por que não instalar o ComfyUI mesmo assim

Instalar ComfyUI + PyTorch (~2,5 GB) para depois não conseguir baixar nem
carregar modelo algum consumiria metade do disco e não responderia nenhuma
das perguntas da fase. A regra do projeto é não fazer implementação
especulativa.

O que **importa validar** — e foi validado — é a camada que escrevemos:
cliente HTTP, resolução de workflow, captura de recipe, tratamento de erro.
Essa camada é exercitada por um **servidor ComfyUI falso** em `http.server`
que fala o mesmo protocolo (`tests/test_comfy.py`), incluindo os caminhos de
falha que mais doem em produção: OOM de CUDA, timeout, workflow rejeitado,
output vazio, servidor fora do ar.

### Arquitetura consequente

A infraestrutura é **desacoplada do local de execução**, como a spec exige:

```
CLI (chibi)  ->  ComfyClient (HTTP)  ->  [ ComfyUI + GPU ]  ->  recipe
                        ^
                config/environments/<env>.yaml
```

- O endereço do backend **nunca** aparece no código. Vem de
  `config/environments/`, e a URL/token vêm de variável de ambiente
  (`CHIBI_COMFY_URL`, `CHIBI_COMFY_TOKEN`). Há um teste que varre o
  fonte procurando `localhost:8188` hardcoded e falha se encontrar.
- Trocar de local de execução é trocar de arquivo YAML, não de código.
- `local.yaml` tem `comfyui.enabled: false`. O CLI recusa com mensagem
  acionável em vez de tentar e falhar feio.

### Quantização escolhida

`fp8_e4m3fn`, registrada em `cloud.yaml` e no recipe. Motivo: ~20,5 GB cabe
numa GPU de 24 GB, que é a faixa de aluguel mais barata. BF16 exigiria ~41 GB
(A100/H100, bem mais caro). `[TEST REQUIRED]` — não medimos qualidade fp8 vs
BF16; a escolha é por viabilidade de custo, não por qualidade comprovada.

## Consequências

**Positivas**

- Toda a camada de orquestração está escrita e testada (37 testes) sem gastar
  um centavo de GPU.
- Quando houver backend, o caminho é: exportar `CHIBI_COMFY_URL`, rodar
  `chibi comfy status`, `chibi comfy validate`, `chibi experiment qwen-edit`.
- Os erros que aparecerão primeiro (nome de node errado, modelo ausente) já
  têm mensagem específica em vez de stack trace.

**Negativas / riscos assumidos**

- **O workflow nunca foi executado.** `[TEST REQUIRED]`. As classes de node
  seguem o template oficial `image_qwen_image_edit_2511`, mas só uma execução
  real confirma nomes, sockets e tipos. É exatamente para isso que existe
  `chibi comfy validate`, que compara contra `/object_info` **antes** de
  gastar tempo de GPU.
- Os nomes de arquivo em `cloud.yaml` (`qwen_image_edit_2511_fp8_e4m3fn.
  safetensors` etc.) são os convencionais da distribuição ComfyUI, **não
  confirmados**. Ajustar conforme o servidor real.
- A seção 9 da spec (duas execuções, comparar hashes) só pôde ser exercitada
  em dry-run: a mecânica de reprodução de configuração foi validada, a
  reprodutibilidade de **bytes de imagem** continua em aberto.

## Como destravar

Qualquer uma das opções, por decisão humana:

1. **GPU alugada** (RunPod, Vast.ai, Modal): subir `worker-comfyui`, exportar
   `CHIBI_COMFY_URL`. Custo estimado US$ 0,35–0,80/h.
2. **Máquina do usuário**, se tiver GPU adequada: rodar o ComfyUI e apontar a
   URL. A RX 580 documentada em `local.yaml` **não** serve (ROCm removeu
   gfx803).
3. **Sandbox com GPU**, se o ambiente de execução do agente passar a ter uma.

Em todos os casos o download dos pesos exige **aprovação humana explícita** —
o agente não baixa checkpoints (`AGENTS.md` §3).

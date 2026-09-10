# Relatório Técnico — Pipeline de Geração e Preparação de Arte com IA

**Projeto:** ChibiCreate — jogo 2D indie comercial em Godot (estilo Vampire Survivors, personagens "waifu")
**Data da pesquisa:** 2026-09-07
**Status:** Proposta de arquitetura — **nada implementado, nada instalado, nenhum modelo baixado**

> **Legenda de confiança**
> **[F]** Fato verificável em fonte citada · **[R]** Recomendação minha (juízo de engenharia) · **[H]** Hipótese a validar no MVP

---

## Índice

1. [Resumo executivo](#1-resumo-executivo)
2. [Pipeline recomendado](#2-pipeline-recomendado)
3. [Ferramentas recomendadas](#3-ferramentas-recomendadas-por-etapa)
4. [Modelos candidatos](#4-modelos-candidatos--comparação-e-licença)
5. [Hardware](#5-hardware--rx-580-8-gb--r5-5500--16-gb-ram)
6. [Consistência de personagens](#6-consistência-de-personagem--a-estratégia)
7. [Animação](#7-animação--comparação-honesta)
8. [Integração com Godot](#8-integração-com-godot)
9. [Arquitetura do Git](#9-arquitetura-do-git)
10. [Automação](#10-automação-o-que-o-agente-faz-depois)
11. [MVP](#11-mvp--menor-experimento-que-prova-a-tese)
12. [Riscos](#12-riscos)
13. [Plano de implementação](#13-plano-de-implementação-ordem-recomendada)
14. [Recomendação objetiva final](#recomendação-objetiva-final)
15. [Perguntas em aberto](#perguntas-em-aberto)
16. [Fontes](#fontes)

---

## 1. Resumo executivo

**Recomendação central [R]:** um pipeline **híbrido — "IA gera identidade, humano + ferramenta clássica controla movimento"** — orquestrado em **ComfyUI rodando em GPU cloud sob demanda**, com o **repositório Git como fonte da verdade de configuração e metadados** (não de binários pesados).

Os quatro pilares:

1. **Motor de identidade = modelo de edição multi-referência**, não texto-para-imagem.
   Concretamente **Qwen-Image-Edit-2511** (Apache 2.0, aceita até 3 imagens de referência, foco explícito em consistência de personagem e redução de drift) **[F]** [[1]](#f1) [[2]](#f2). É a peça que transforma splash art → chibi preservando cabelo / olhos / roupa / arma.

2. **Estilo chibi global = 1 Style LoRA** treinada sobre o modelo base, mais um *style kit* textual/visual versionado.
   **Sem LoRA por personagem no início** — só treinar LoRA individual para personagens "problemáticas" (regra de exceção, não regra geral) **[R]**.

3. **Animação = NÃO gerar vídeo IA para gameplay.**
   Para um Vampire Survivors, a IA gera **um Chibi Master + poses-chave**, e o movimento vem de **rig recortado (cutout/skeletal)**, exportado como spritesheet. Isso elimina flicker e drift, que são o assassino de sprites gerados frame a frame **[R]**.

4. **Reprodutibilidade = "receita, não resultado".**
   Todo asset final tem um `.recipe.json` versionado (modelo + hash, LoRA + versão, seed, prompt, hash do workflow, imagens de input por hash). Regerar deve ser um comando, não uma sessão de cliques **[R]**.

### O que NÃO recomendo

| Descartado | Motivo |
|---|---|
| Treinar LoRA por personagem antes do MVP | Custo por personagem não escala para 100+; o modelo de edição já preserva identidade |
| FLUX.1 / FLUX.2 **[dev]** | Licença não-comercial; exige licença paga da BFL **[F]** [[3]](#f3) |
| FLUX.2 **[klein] 9B** | Não-comercial **[F]** [[7]](#f7) (o **klein 4B** é Apache 2.0 e está liberado) |
| NoobAI-XL / Pony | Model card adiciona proibição explícita de comercialização sobre a licença Illustrious **[F]** [[4]](#f4) |
| BRIA RMBG-2.0 (pesos) | CC BY-NC 4.0; produção exige contrato pago **[F]** [[5]](#f5) |
| SeedVR2 (upscaler) | Licença restringe uso comercial **[F]** [[11]](#f11) |

---

## 2. Pipeline recomendado

```
                    ┌── FLOW 06 (independente) ────┐
Splash / Concept ───┤  separação de camadas → PSD  │→ Live2D Cubism → Gacha
                    └──────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ FLOW 01  CHARACTER REFERENCE                                    │
│   splash + concept                                              │
│   → BiRefNet (recorte) → normalização (canvas, DPI, cor)        │
│   → extração de "identity kit":                                 │
│       crop de rosto · crop de cabelo · crop de acessórios/arma  │
│       paleta (k-means → palette.json)                           │
│   → character sheet A-pose (Qwen-Edit multi-angle / turnaround) │
│   → character.yaml (descrição textual canônica + refs)          │
│   ✔ GATE HUMANO: sheet aprovado?                                │
└─────────────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ FLOW 02  CHIBI MASTER                                           │
│   character sheet + splash + identity kit (até 3 refs)          │
│   + chibi_style LoRA + chibi_style prompt block                 │
│   → N candidatos (seeds variadas, batch)                        │
│   → curadoria humana (1 escolhido)                              │
│   → retoque/inpaint dirigido de rosto e arma                    │
│   → upscale (Real-ESRGAN anime) → BiRefNet alpha → cleanup      │
│   → chibi_master.png (RGBA, corpo inteiro, A-pose, canvas fixo) │
│   ✔ GATE HUMANO: este é o cânone da personagem. CONGELA.        │
└─────────────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ FLOW 03  POSE                                                   │
│   chibi_master (referência de identidade)                       │
│   + ControlNet openpose/lineart a partir de um POSE BANK GLOBAL │
│   → mesma personagem em pose X                                  │
│   (o pose bank é compartilhado: toda personagem usa exatamente  │
│    os mesmos esqueletos → consistência ENTRE personagens)       │
│   ✔ GATE: comparação automática de paleta + revisão humana      │
└─────────────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ FLOW 04  ANIMATION   (estratégia primária = C+D, ver §7)        │
│   A) chibi_master → recorte em partes                           │
│      (cabeça, torso, braços, pernas, arma, cabelo-back)         │
│      → rig cutout → idle/walk keyframes → bake p/ spritesheet   │
│   B) (fallback/menu) pose-guided: 4–8 frames via ControlNet     │
│      a partir de um pose bank de walk cycle → limpeza           │
└─────────────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ FLOW 05  GAME EXPORT                                            │
│   frames → dedupe/alinhamento por pivot                         │
│   → alpha cleanup (halo/despill/dilate)                         │
│   → downscale único p/ resolução de gameplay (fator inteiro)    │
│   → controle de paleta → pack em spritesheet (power-of-two)     │
│   → .tres SpriteFrames + config de import                       │
│   → Godot AnimatedSprite2D                                      │
└─────────────────────────────────────────────────────────────────┘
```

**Por que o Chibi Master é o único cânone:** todas as poses e animações derivam *dele*, nunca da splash art. Isso corta a cadeia de drift em um único ponto controlado **[R]**.

---

## 3. Ferramentas recomendadas por etapa

| Etapa | Recomendado | Alternativas | Nota |
|---|---|---|---|
| Orquestração | **ComfyUI** — workflow = JSON diffável, API HTTP nativa, re-execução só do que mudou **[F]** [[6]](#f6) | InvokeAI (canvas/artista), SwarmUI, Forge | ver §3.1 |
| Recorte / alpha | **BiRefNet** — código **e** pesos MIT **[F]** [[5]](#f5); nativo no ComfyUI desde mai/2026 **[F]** [[24]](#f24) | SAM 2 (máscaras guiadas), rembg (wrapper) | evitar RMBG-2.0 (NC) |
| Edição de identidade | **Qwen-Image-Edit-2511** (Apache 2.0) | FLUX.2 [klein] 4B (Apache 2.0, mais rápido, menos fiel) **[F]** [[7]](#f7) | núcleo do pipeline |
| Estilo chibi | **LoRA de estilo própria** sobre o base escolhido | prompt-only, IP-Adapter de estilo | você é dono → licença limpa |
| Controle de pose | **ControlNet Union (InstantX) p/ Qwen-Image** — canny/softedge/depth/pose **[F]** [[8]](#f8); ou Union DiffSynth LoRA **[F]** [[9]](#f9) | ControlNet SDXL (ecossistema mais maduro) | pose bank à mão / DWPose |
| Upscale | **Real-ESRGAN x4plus-anime-6B** (BSD-3) **[F]** [[10]](#f10) | Real-CUGAN (2D) | SeedVR2 é NC — evitar **[F]** [[11]](#f11) |
| Animação (rig) | **Godot Skeleton2D / cutout** ou DragonBones (open) | Spine (licença paga por seat) | ver §7 |
| Interpolação | **RIFE** via Video2X **[F]** [[12]](#f12) | — | só menus; verificar licença do checkpoint |
| Vídeo → frames | **Wan 2.2 / Wan-Animate-2** (Apache 2.0) **[F]** [[13]](#f13) [[14]](#f14) | LTX | cinematics/gacha, **não** sprites |
| Treino de LoRA | **diffusion-pipe** (GPL-3.0; suporta Qwen-Image-Edit, Wan; block swap p/ low-VRAM) **[F]** [[7]](#f7) | kohya_ss, OneTrainer, ai-toolkit | roda em cloud |
| Cloud | RunPod Serverless + worker ComfyUI oficial **[F]** [[15]](#f15) | Vast.ai, Colab Pro (A100/L4), Modal | imagem Docker versionada |
| Live2D | **Live2D Cubism** (obrigatório) + prep de camadas | anysplit, live2dlayer (só raster) | ver §Live2D |

### 3.1 ComfyUI é a escolha certa?

**Sim para este caso [R]** — e não por popularidade. Os critérios exigidos mapeiam diretamente:

| Requisito | ComfyUI | A1111 | Forge | InvokeAI |
|---|---|---|---|---|
| Workflow como arquivo | JSON — grafo completo **[F]** [[6]](#f6) | metadata PNG (parcial) | idem A1111 | export de projeto |
| Versionamento Git | nativo (diff textual) **[F]** [[6]](#f6) | disciplina manual | manual | zip/manifest |
| Determinismo | mesmo grafo = mesmo resultado **[F]** [[6]](#f6) | aproximado | aproximado | aproximado |
| CI/CD | nativo (HTTP API + JSON) **[F]** [[6]](#f6) | possível (REST) | possível | possível |
| Trilha de auditoria | excelente, nível de nó **[F]** [[6]](#f6) | fraca | fraca | moderada |
| Batch / parameter sweep | forte **[F]** [[6]](#f6) | básico | básico | limitado |
| Caminho p/ serverless | worker oficial RunPod **[F]** [[15]](#f15) | — | — | — |

A1111 está em declínio (perdeu terreno em Flux, vídeo e performance) **[F]** [[16]](#f16). Forge é ótimo para iteração manual rápida, mas não entrega grafo reprodutível **[F]** [[6]](#f6). InvokeAI é superior para trabalho de canvas/inpaint por artista — vale como ferramenta *complementar* de retoque, não como orquestrador.

**Mitigação de lock-in [R]:** trate o ComfyUI como **executor**, não como o pipeline. A verdade fica no `recipe.json` + scripts Python; o workflow JSON é um **artefato gerado** a partir de um template com placeholders. Migrar para Diffusers puro depois vira reescrever um adaptador, não o projeto.

---

## 4. Modelos candidatos — comparação e licença

### 4.1 Geração / edição de imagem

| Modelo | Licença | Comercial | VRAM prático | Força | Fraqueza |
|---|---|---|---|---|---|
| **Qwen-Image-Edit-2511** (20B MMDiT) | Apache 2.0 **[F]** [[1]](#f1) | ✅ livre | Q4_0 GGUF 11.9 GB (12 GB) · Q4_K_M 13.2 GB (16 GB) · FP8 20.5 GB (24 GB) · BF16 40.9 GB **[F]** [[17]](#f17) | Melhor edição instrucional aberta; até 3 refs; multi-ângulo de 1 ref; identidade facial **[F]** [[2]](#f2) | Pesado (20B) |
| Qwen-Image / 2512 (base t2i) | Apache 2.0 **[F]** [[18]](#f18) | ✅ | ~12–24 GB | Base p/ ControlNet Union e LoRA | menos "anime" nativo |
| SDXL 1.0 | CreativeML OpenRAIL++-M **[F]** [[19]](#f19) | ✅ | 6–8 GB | Ecossistema LoRA/ControlNet incomparável; barato de treinar | qualidade base inferior |
| Illustrious-XL 1.1 | FAIPL 1.0, redistribuído sob CreativeML Open RAIL (SDXL); comercial permitido, mas **proíbe monetização proprietária closed-source** **[F]** [[20]](#f20) [[21]](#f21) | ⚠️ **ambíguo** | 6–8 GB | Estilo anime nativo, excelente | cláusula problemática p/ jogo fechado |
| FLUX.1 / 2 **[dev]** | BFL Non-Commercial **[F]** [[3]](#f3) | ❌ | 12–32 GB | qualidade | **descartar** |
| FLUX.2 **[klein] 4B** | Apache 2.0 **[F]** [[18]](#f18) | ✅ | ~13 GB (4-bit ~6–8 GB) **[F]** [[7]](#f7) | rápido, edição decente | fidelidade < Qwen-Edit |
| FLUX.2 **[klein] 9B** | Non-commercial **[F]** [[7]](#f7) | ❌ | ~6–8 GB (4-bit) | qualidade/tamanho | **descartar** |
| Z-Image Turbo 6B | Apache 2.0 **[F]** [[22]](#f22) | ✅ | <16 GB | velocidade/custo | variante de edição imatura |
| Step1X-Edit v1.2 | Apache 2.0 **[F]** [[7]](#f7) | ✅ | 18 GB (FP8 + offload) | instruções que exigem raciocínio | menos maduro |
| NoobAI-XL / Pony | Illustrious + adendo com **proibição de comercialização** **[F]** [[4]](#f4) | ❌ | — | qualidade anime | **descartar** |

> ⚠️ **Sinalização de dúvida séria de licença — Illustrious / FAIPL**
> A licença diz que "o output não é coberto" mas também "proíbe monetização proprietária closed-source"; interpretações conflitam publicamente **[F]** [[4]](#f4) [[20]](#f20).
> **Posição [R]:** usar Illustrious/SDXL **apenas em prototipagem e exploração de estilo**. Para os assets que entram no build, gerar com **Qwen (Apache 2.0)** ou SDXL base + LoRAs próprias. Levar Illustrious ao produto final é decisão **jurídica**, não técnica.

> ⚠️ **Risco residual de proveniência de dataset**
> Quase nenhum desses modelos revela o dataset de treino. A licença cobre os **pesos**, não elimina risco de terceiros sobre o **conteúdo**. Bria é a exceção que vende exatamente essa garantia (dados 100% licenciados) **[F]** [[23]](#f23).

### 4.2 Modelos auxiliares

| Modelo | Licença | Comercial | Observação |
|---|---|---|---|
| **BiRefNet** | MIT (código **e** pesos) **[F]** [[5]](#f5) | ✅ | Venceu teste comparativo em cabelo/transparência/clutter **[F]** [[5]](#f5) |
| BRIA RMBG-2.0 | CC BY-NC 4.0 **[F]** [[5]](#f5) | ❌ sem contrato | API a $0.018/img **[F]** [[23]](#f23) — opção se quiser garantia jurídica de dataset |
| **Real-ESRGAN** (x4plus-anime-6B) | BSD-3 **[F]** [[10]](#f10) | ✅ | Checkpoint anime dedicado |
| BasicVSR++ | Apache 2.0 **[F]** [[11]](#f11) | ✅ | VSR temporal — provavelmente desnecessário aqui |
| SeedVR2 | NC **[F]** [[11]](#f11) | ❌ | evitar |
| **Wan 2.2 / Wan-Animate-2** | Apache 2.0 **[F]** [[13]](#f13) [[14]](#f14) | ✅ | 14B: ~24 GB fp8; GGUF ~8–12 GB @480p **[F]** [[25]](#f25); nós nativos ComfyUI **[F]** [[31]](#f31) |
| LayerDiffuse | — (era SDXL/Flux-1) | verificar | 97% de preferência vs. gerar+matting **[F]** [[26]](#f26); **sem port maduro p/ Qwen/Flux.2** **[F]** [[27]](#f27) — **[H]** testar no ramo SDXL |
| SAM 2 / SAM 3.1 | Meta | verificar | máscaras guiadas para separação Live2D |

---

## 5. Hardware — RX 580 8 GB / R5 5500 / 16 GB RAM

### Fatos duros sobre Polaris (gfx803)

- A AMD **removeu Polaris/GCN4 do ROCm na v5.x**; não há suporte oficial **[F]** [[28]](#f28) [[30]](#f30)
- **DirectML quebra com ComfyUI** (`NotImplementedError: Cannot access storage of OpaqueTensorImpl`) e foi abandonado pela Microsoft **[F]** [[28]](#f28)
- OpenVINO + Forge falha (extensão mira arquitetura antiga do A1111) **[F]** [[28]](#f28)
- **Existe** caminho via **Vulkan / stable-diffusion.cpp** — roda SD 1.5 e FLUX schnell GGUF em híbrido GPU+CPU **[F]** [[28]](#f28) [[29]](#f29)
- Recompilar ROCm 5.1.3 para gfx803 é possível, com relatos de artefatos e glitches **[F]** [[30]](#f30)

Nenhum desses caminhos entrega ComfyUI + ControlNet + Qwen-Edit de forma confiável.

### Veredito [R]

> **Trate a RX 580 como estação de trabalho de artista e de CPU — não como GPU de inferência.**

| Tarefa | Onde | Por quê |
|---|---|---|
| ComfyUI GUI (montar grafos, backend remoto) | **local** | leve, é só front-end |
| BiRefNet, Real-ESRGAN (ncnn/Vulkan), ffmpeg, PIL/OpenCV, pack de spritesheet, scripts | **local** | Real-ESRGAN/Video2X têm backend Vulkan p/ AMD, ~4 GB VRAM **[F]** [[12]](#f12) |
| Godot, rigging, retoque (Krita/Photoshop), Live2D Cubism | **local** | onde você mais vai gastar tempo |
| Qwen-Image-Edit-2511, ControlNet, geração de candidatos | **cloud 24 GB** (L4 / A10 / 4090) | FP8 = 20.5 GB **[F]** [[17]](#f17) |
| Treino de LoRA de estilo | **cloud 24–48 GB** | diffusion-pipe com block swap |
| Wan 2.2 14B (se usado) | **cloud 24–48 GB** **[F]** [[14]](#f14) | 720p sem quantização pede A6000 48 GB |

### Alertas

- **RAM é o gargalo real [F/R]:** 16 GB é apertado até para trabalho local — o `WanAnimate2Cache` sozinho pede ~12,5 GB de **RAM de sistema** **[F]** [[31]](#f31). **O upgrade com melhor retorno no seu setup não é a GPU — é ir para 32 GB de RAM.** GPU você aluga; RAM você não.
- **Custo cloud [H]:** ~$0,35–0,80/h em GPU classe A6000/4090 **[F]** [[14]](#f14). Uma personagem completa (FLOW 01–03) deve caber em 1–3 h → **~$1–3/personagem**. Treino de LoRA de estilo one-off: ~$10–30. Para 100 personagens isso é ruído no orçamento — **o gargalo é seu tempo de curadoria, não compute.**

---

## 6. Consistência de personagem — a estratégia

Decomponha em **três eixos ortogonais** e ancore cada um em um mecanismo diferente. Misturar eixos é a causa raiz do character drift.

| Eixo | Mecanismo | Artefato versionado |
|---|---|---|
| **Estilo chibi global** (proporção, traço, olhos, sombreamento) | 1 **Style LoRA** + bloco de prompt fixo + parâmetros travados | `styles/chibi_v1/` |
| **Identidade da personagem** | **Imagens de referência** via Qwen-Edit multi-ref (splash + face crop + arma crop) + `character.yaml` | `characters/<id>/reference/` |
| **Pose / movimento** | **ControlNet** a partir de um **pose bank global**, idêntico para todas | `styles/pose_bank/` |

### Escada de escalonamento — não pule degraus

```
Nível 0   prompt + imagens de referência              ← COMECE AQUI
Nível 1   + style LoRA chibi (global)                 ← quase certo que precisa
Nível 2   + inpaint dirigido de rosto/arma            ← barato, resolve muito
Nível 3   + LoRA de personagem individual             ← só se 0–2 falharem PARA ELA
```

**Por que não LoRA por personagem de saída [R]:** o modelo de edição já foi treinado para preservar identidade a partir de referência — o 2511 melhora explicitamente consistência de personagem e reduz drift **[F]** [[1]](#f1). LoRA individual custa dataset + treino + versionamento **por personagem**, o que não escala para 100 personagens e é exatamente o "processo manual" que se quer evitar.

**Vantagem estrutural:** uma vez que o Chibi Master existe e você tem 5–10 poses aprovadas, **você já tem o dataset da LoRA de graça** — o pipeline se alimenta. Treine LoRA *depois*, com dados do próprio pipeline, não antes.

### Duas alavancas subestimadas [R]

1. **Nunca descreva rosto/cabelo em texto.** Prompts descritivos **sobrepõem** a imagem de referência — é a causa nº 1 de "o rosto mudou" **[F]** [[32]](#f32). Descreva a *ação e o enquadramento*; deixe a identidade 100% na referência.
2. **Verificação automática de consistência.** Compare a paleta (distância em Lab entre os ~8 clusters dominantes) e um embedding de imagem do crop de rosto contra o Chibi Master. Falhou o threshold → rejeita o candidato **antes** do humano ver. É isso que faz o pipeline escalar para 100 personagens.

---

## 7. Animação — comparação honesta

| Estratégia | Consistência | Legível em 64–128 px | Custo comp. | Facilidade de alterar | Godot |
|---|---|---|---|---|---|
| **A)** Frames individuais por IA | ❌ ruim — cada frame é nova amostragem; flicker inevitável | média | médio | ruim (regerar tudo) | ok |
| **B)** Vídeo IA → frames (Wan/Wan-Animate) | ⚠️ boa temporalmente, mas saída ~24 fps, 480p, **sem alpha** | ruim (soft/blur) | **alto** | péssimo | ruim |
| **C)** Animação por partes (cutout) | ✅ **perfeita** — os pixels são literalmente os mesmos | ✅ boa | **baixíssimo** | ✅ ótima | ✅ nativo |
| **D)** Skeletal 2D (Skeleton2D/DragonBones/Spine) | ✅ perfeita | ✅ boa | baixo | ✅ ótima | ✅ nativo (custo por bone) |
| **E)** Pose-guided (ControlNet) + limpeza | ⚠️ média — bom p/ poses-chave, ruim p/ ciclos | boa | médio | média | ok |

### Recomendação [R]

> **C como padrão · D onde precisar de deformação · E como gerador de poses-chave · B só para cinematics/gacha · A nunca para gameplay.**

**Raciocínio:** em Vampire Survivors o sprite tem ~64–96 px de altura e há **centenas na tela**. Nessa escala, um walk de **4 a 6 frames** é não só suficiente como *melhor* — mais legível, mais "game-y". Gastar GPU em vídeo IA de 81 frames para depois descartar 75 é desperdício de duas ordens de grandeza. E flicker de IA, imperceptível a 1024 px, vira ruído epilético a 64 px com 200 instâncias.

### O truque de produção que faz isso escalar

Um **rig cutout genérico compartilhado**: mesma decomposição de partes para todas (cabeça, torso, braço L/R, perna L/R, arma, cabelo-back). O Chibi Master é sempre gerado na **mesma A-pose e no mesmo canvas** → o script de recorte é o mesmo → **o mesmo idle/walk se aplica a 100 personagens sem trabalho adicional**. Personagens de silhueta atípica ganham override do rig.

> ⚠️ **Cuidado com Godot:** performance de animação esquelética não é ponto forte da engine, e cada bone animado adiciona custo **[F]** [[33]](#f33). Por isso: **bake para spritesheet antes de shippar** (§8).

---

## 8. Integração com Godot

**Recomendação [R]: bake tudo para spritesheet e use `AnimatedSprite2D`.**

| Caso | Nó | Justificativa |
|---|---|---|
| Inimigos, hordas, NPCs | **`AnimatedSprite2D`** | Feito para frame-a-frame; menos overhead por instância que `AnimationPlayer`; mensuravelmente mais rápido com centenas de inimigos e animações simples **[F]** [[34]](#f34) |
| Player e bosses | **`AnimationPlayer`** | Sincronizar hitbox / SFX / partículas com um frame específico na mesma timeline **[F]** [[35]](#f35) |
| Blending de estados do player | `AnimationTree` | Transição e blend entre múltiplas animações **[F]** [[35]](#f35) |
| Personagem de destaque em menu (1 na tela) | `Skeleton2D` / `Polygon2D` ao vivo | Rig ao vivo só onde o custo é irrelevante |

### Regras de higiene

- ⚠️ **Nunca deixe `AnimatedSprite2D` e `AnimationPlayer` dirigindo o mesmo visual** — causa flicker e animações cortadas **[F]** [[35]](#f35).
- Spritesheets em **potência de dois** (256/512/1024); não-PoT funciona mas gasta mais VRAM por padding **[F]** [[34]](#f34).
- Import: `Filter = Nearest` se o look for crisp; `Mipmaps` off.
- **Pivot consistente**, definido no FLOW 05 — não no editor.
- Gere o `.tres` de `SpriteFrames` **por script**: adicionar uma personagem não deve exigir cliques no editor.
- FPS de referência: ~10 fps para walk, 6–8 fps para idle **[F]** [[34]](#f34).

---

## 9. Arquitetura do Git

A estrutura sugerida por você está boa. Ajusto três coisas: **separar cânone de descartável**, **elevar `styles/` a cidadão de primeira classe**, e **tirar binários grandes do Git**.

```
.
├── README.md
├── CONTRIBUTING.md              # runbook humano: como adicionar personagem
├── LICENSES.md                  # ⚠️ registro por modelo/LoRA: licença, URL, data de verificação
├── .gitattributes               # Git LFS: *.png *.psd *.safetensors
├── .gitignore                   # ignora work/ e cache/
│
├── config/
│   ├── project.yaml             # resoluções canônicas, fps, canvas, paleta do jogo
│   ├── models.lock.yaml         # nome, repo, revisão, sha256, licença de CADA modelo
│   ├── environments/
│   │   ├── comfy-local.yaml
│   │   └── comfy-runpod.yaml
│   └── quality_gates.yaml       # thresholds de paleta, alpha, dimensão
│
├── styles/
│   └── chibi/
│       ├── style.yaml           # prompt block, params travados, modelo base
│       ├── lora/                # ponteiro + hash (peso via LFS ou storage externo)
│       ├── pose_bank/           # ⭐ GLOBAL: a_pose.png, walk_00..05, idle_00..03
│       └── reference_sheets/    # exemplos aprovados = a "bíblia visual"
│
├── characters/
│   └── waifu_001_<slug>/
│       ├── character.yaml       # ⭐ identidade canônica: descrição, cores, tags, overrides
│       ├── source/              # splash/concept originais (imutável, LFS)
│       ├── reference/           # FLOW 01: recortes, identity kit, sheet, palette.json
│       ├── chibi/
│       │   ├── master.png       # ⭐ o cânone
│       │   ├── master.recipe.json
│       │   └── candidates/      # (gitignored — vive em work/)
│       ├── poses/<pose_id>/
│       ├── animation/<anim>/frames/
│       ├── export/              # spritesheet.png + .tres + atlas.json
│       └── STATUS.md            # em que gate a personagem está
│
├── workflows/                   # templates ComfyUI com placeholders {{...}}
│   ├── 01_character_reference/
│   ├── 02_chibi_master/
│   ├── 03_pose/
│   ├── 04_animation/
│   ├── 05_export/
│   └── 06_live2d_prep/
│
├── scripts/
│   ├── chibi/                   # pacote Python
│   │   ├── cli.py
│   │   ├── recipe.py
│   │   ├── comfy_client.py
│   │   ├── validate.py
│   │   ├── sheet.py
│   │   ├── spritesheet.py
│   │   └── godot_export.py
│   └── hooks/
│
├── work/                        # ⛔ gitignored: candidatos, temporários, logs
└── docs/
    ├── research/                # este relatório
    ├── decisions/               # ADRs: por que Qwen e não Flux, etc.
    └── pipeline.md
```

### O que armazenar para reprodutibilidade — sim, tudo isso [R]

Formato `*.recipe.json`, ao lado de **cada artefato aprovado**:

```jsonc
{
  "artifact": "characters/waifu_001/chibi/master.png",
  "artifact_sha256": "…",
  "flow": "02_chibi_master",
  "workflow": {
    "template": "workflows/02_chibi_master/v3.json",
    "sha256": "…"
  },
  "base_model": {
    "name": "Qwen-Image-Edit-2511",
    "quant": "fp8",
    "sha256": "…",
    "license": "Apache-2.0"
  },
  "loras": [
    { "name": "chibi_style", "version": "v1.2", "sha256": "…", "weight": 0.8 }
  ],
  "inputs": [
    { "role": "character_sheet", "path": "…/reference/sheet.png", "sha256": "…" },
    { "role": "face_crop",       "path": "…/reference/face.png",  "sha256": "…" }
  ],
  "params": {
    "seed": 128873, "steps": 20, "cfg": 2.5,
    "sampler": "euler", "scheduler": "beta"
  },
  "prompt": { "positive": "…", "negative": "…" },
  "env": { "comfyui": "0.3.x", "commit": "…", "gpu": "L40S" },
  "human": { "approved_by": "…", "date": "2026-09-08", "selected_from_batch": 7 }
}
```

Isso é o que transforma *"gerei uma imagem bonita"* em *"posso regerar este asset daqui a 18 meses"*.

**Regra prática [R]:** se o artefato foi **aprovado**, a receita é **obrigatória**; se não foi, o artefato mora em `work/` e pode sumir.

**Binários:** Git LFS para `source/`, `master.png` e `export/`. **Modelos e LoRAs nunca no Git** — apenas hash em `models.lock.yaml` + script de download. Com 100+ personagens, sem essa disciplina o clone vira dezenas de GB.

---

## 10. Automação (o que o agente faz depois)

CLI unificada, cada comando idempotente e reprodutível:

```bash
chibi character new waifu_006 --name "…" --source ./art/*.png
chibi validate     waifu_006                   # resolução, alpha, canvas, campos do yaml
chibi flow01       waifu_006                   # recorte + normalização + identity kit + sheet
chibi flow02       waifu_006 --candidates 8
chibi approve      waifu_006 chibi --pick 3    # grava recipe + promove de work/ p/ repo
chibi flow03       waifu_006 --poses walk,attack
chibi flow04       waifu_006 --anim idle,walk
chibi export       waifu_006 --target godot
chibi report       --all                       # dashboard de status/consistência
```

### O agente faz bem

Validar inputs · montar workflows a partir de templates · disparar jobs na cloud · aplicar gates automáticos (paleta, alpha, dimensão) · gerar folhas de contato para escolha · escrever as receitas · montar spritesheets · gerar os `.tres` · abrir PR com o diff.

### O agente NÃO deve fazer

Escolher o candidato final · aprovar o Chibi Master · julgar "isso está fofo".

> **Os gates humanos são de propósito.** São eles que impedem o drift de se acumular silenciosamente ao longo de 100 personagens. Um pipeline totalmente automático aqui produziria 100 personagens levemente erradas.

### Fluxo de PR sugerido

`chibi character new` cria a branch e um PR em rascunho → cada gate aprovado é um commit → a personagem entra na `main` quando `export/` valida. **Revisão de arte = revisão de código.**

---

## 11. MVP — menor experimento que prova a tese

**Uma personagem. Uma pergunta: a identidade sobrevive à cadeia inteira?**

> **Escopo deliberadamente cruel:** escolha a personagem **mais difícil** das 5 — mais acessórios, arma complexa, cabelo elaborado. Se funcionar com ela, funciona com as outras. Validar com a mais fácil é auto-engano.

### Entregáveis

1. `waifu_001/reference/sheet.png` + `character.yaml` + `palette.json`
2. `waifu_001/chibi/master.png` (RGBA, A-pose) + `master.recipe.json`
3. Uma **segunda pose** (ex.: `attack_wind_up`) derivada do master
4. **`idle`** (4 frames) e **`walk`** (6 frames) via rig cutout
5. `export/waifu_001_sheet.png` + `SpriteFrames.tres`
6. **Cena Godot com 200 instâncias** do sprite andando, com contador de FPS

O **item 6** é o que a maioria dos pipelines esquece e é onde eles morrem.

### Teste de legibilidade (obrigatório)

O mesmo sprite renderizado a **64, 96 e 128 px** lado a lado, visto a distância. É isso que define sua resolução final — não uma escolha a priori.

### Restrições do MVP

- **Não treine nenhuma LoRA.** Se o Nível 0/2 já entregar, você economizou semanas. Se não entregar, o MVP te disse exatamente *o que* a LoRA precisa corrigir.
- Prazo estimado **[H]:** 2–4 dias de trabalho concentrado — a maior parte em curadoria e rig, não em compute.

---

## Resolução (o que decidir depois)

Não dá para fixar números sem duas informações:

1. **Resolução alvo do jogo** — 1080p? 1440p? Steam Deck 1280×800?
2. **Altura do sprite na tela** — em VS, inimigos ~32–64 px, player ~64–96 px

Estrutura recomendada **[R]**, independente do número final — trabalhe sempre **acima** e faça downscale **uma vez só** no FLOW 05:

| Asset | Resolução de trabalho | Entrega | Nota |
|---|---|---|---|
| Splash/concept (source) | nativo (≥2048) | arquivo | imutável |
| **Chibi Master** | **1024² ou 1536², canvas quadrado fixo** | arquivo | é o cânone — gere grande |
| Poses | mesma do master | arquivo | |
| Frames de animação | ~512 px de altura | intermediário | |
| **Sprite de gameplay** | — | **múltiplo inteiro do alvo** (ex.: 128 p/ exibir a 64) | ⚠️ fator inteiro evita shimmer |
| Assets de menu/UI | 512–1024 | final | aqui vale animação mais rica |

> **Regra de ouro:** um único downscale, no fim, com filtro adequado (Lanczos ou area). Downscales encadeados destroem line art.

---

## FLOW 06 — Live2D (separado, não misturar)

```
Splash/Concept → separação de elementos → PSD estruturado → Live2D Cubism
```

Fatos operacionais:

- O Cubism importa **PSD**, não PNG solto. Formato: **PSD, RGB, 8 bit/canal**. PNG só serve para rascunho/fundo/substituição de textura **[F]** [[36]](#f36)
- **1 parte = 1 camada**, com line art e pintura já mescladas; **nomes de camada únicos** — nomes duplicados causam problema depois **[F]** [[36]](#f36)
- Ferramentas de auto-layer (anysplit, live2dlayer, imagetolayers) entregam **apenas camadas raster** — **não** criam ArtMeshes, deformers, parâmetros ou física; isso continua sendo trabalho manual no Cubism **[F]** [[37]](#f37)
- O valor real dessas ferramentas está no **inpainting de áreas ocluídas** (o que está atrás do cabelo, atrás do braço), que é a parte mais tediosa da preparação **[F]** [[37]](#f37)

**Recomendação [R]:** deixe o FLOW 06 para a **Fase 4**. Ele compartilha com o pipeline chibi apenas o `source/` e o `character.yaml`. Não force reuso de workflow — os objetivos são opostos (chibi quer *simplificar*; Live2D quer *preservar e decompor*).

---

## 12. Riscos

| Risco | Severidade | Mitigação |
|---|---|---|
| **Character drift** entre poses | 🔴 alta | Tudo deriva do Chibi Master congelado; verificação automática de paleta + face; gates humanos |
| **Roupas/acessórios mudam** | 🔴 alta | Crops dedicados como refs; inpaint dirigido; **nunca descrever em texto o que está na referência** **[F]** [[32]](#f32) |
| **Arma inconsistente** | 🟠 média | Tratar a arma como **peça separada do rig** — não deixar a IA regerá-la a cada pose |
| **Mãos** | 🟠 média | Chibi tem mãos simplificadas (vantagem estrutural); a 64 px é quase irrelevante; inpaint quando necessário |
| **Flicker em animação** | 🔴 alta *se* usar frames IA | Estratégia C/D elimina por construção (§7) |
| **Alpha sujo / halo** | 🟠 média | BiRefNet + despill/dilate no FLOW 05; testar LayerDiffuse no ramo SDXL **[H]** |
| **Licença de modelo** | 🔴 **crítica** | `LICENSES.md` com data de verificação; travar em Apache 2.0 / MIT / BSD; ⚠️ Illustrious/FAIPL e NoobAI pendentes de decisão jurídica **[F]** [[4]](#f4) [[20]](#f20) |
| **Proveniência do dataset de treino** | 🟠 média, difícil de mitigar | Risco residual mesmo com pesos Apache; considerar Bria em etapas críticas **[F]** [[23]](#f23) |
| **VRAM / AMD** | 🟠 média | Resolvido movendo inferência para cloud (§5); Polaris sem ROCm é fato consumado **[F]** [[28]](#f28) |
| **16 GB de RAM** | 🟠 média | Upgrade para 32 GB — melhor custo-benefício do setup |
| **Custo cloud** | 🟢 baixa | ~$1–3/personagem **[H]**; cap por job; serverless com scale-to-zero |
| **Lock-in em ComfyUI** | 🟠 média | Lógica em Python; workflow é artefato **gerado**; ADR documentando a rota de saída |
| **Churn do ecossistema** | 🟠 média | Pin de versões em `models.lock.yaml`; imagem Docker versionada |
| **Curadoria humana vira gargalo em 100 personagens** | 🟠 média — **o risco mais subestimado** | Gates automáticos filtram antes; folhas de contato em lote; meta explícita de **≤15 min de humano por personagem** |

---

## 13. Plano de implementação (ordem recomendada)

### Fase 0 — Fundação (sem GPU)
1. Estrutura de diretórios + `.gitattributes`/LFS + `config/project.yaml`
2. `LICENSES.md` e `models.lock.yaml` — **antes** de baixar qualquer peso
3. Esqueleto da CLI + esquema do `recipe.json` + `character new` / `validate`

### Fase 1 — MVP com uma personagem
4. FLOW 01 (BiRefNet + normalização) — roda local
5. Backend ComfyUI na cloud + cliente HTTP + primeiro template de workflow
6. FLOW 02 até um Chibi Master aprovado (**sem LoRA**)
7. Pose bank global + FLOW 03
8. Rig cutout + idle/walk + FLOW 05 + cena Godot com 200 instâncias
9. **Retrospectiva:** decidir resolução final e se a style LoRA é necessária

### Fase 2 — Endurecer
10. Gates automáticos de qualidade e consistência
11. Style LoRA chibi (se a Fase 1 indicar) e sua versionagem
12. Segunda e terceira personagem → **medir tempo humano por personagem**

### Fase 3 — Escala
13. Batch/paralelismo, dashboard de status, automação de PR
14. Animações adicionais (attack / hurt / death / skills / victory) reusando o rig

### Fase 4 — Live2D (separado)
15. Prep de camadas + PSD (1 parte = 1 camada, RGB 8-bit) → rigging manual no Cubism

---

## Recomendação objetiva final

> **Se eu estivesse construindo este jogo hoje:**
>
> - **Identidade e transformação chibi (A):** **Qwen-Image-Edit-2511** (Apache 2.0), multi-referência, em GPU cloud de 24 GB. É o único modelo aberto que junta qualidade de edição, consistência de personagem e licença limpa para produto comercial.
> - **Estilo (B):** **uma única Style LoRA chibi treinada por mim** (diffusion-pipe), aplicada a todas as personagens. **Zero LoRA por personagem até que o MVP prove necessidade.**
> - **Pose (C):** **ControlNet Union** dirigido por um **pose bank global** feito à mão — mesma pose, todas as personagens.
> - **Animação (D):** **rig cutout a partir do Chibi Master, bakeado em spritesheet.** Nada de vídeo IA para gameplay. Wan 2.2 fica reservado para cinematics de gacha.
> - **Limpeza (E):** **BiRefNet** (MIT) para alpha, **Real-ESRGAN anime** (BSD-3) para upscale — ambos rodam na RX 580 via Vulkan.
> - **Godot (F):** `AnimatedSprite2D` + spritesheets power-of-two; `AnimationPlayer` só onde hitbox/SFX precisam de sincronia por frame.
> - **Infra (G):** **ComfyUI como executor** atrás de uma CLI Python própria; workflows são templates gerados, não a fonte da verdade. RunPod serverless para o compute pesado; RX 580 para tudo o que é artesanal.
> - **Git (H):** cânone versionado (`source/`, `master.png`, `export/`) + **receita obrigatória por artefato aprovado** + candidatos em `work/` gitignored + modelos fora do Git, travados por hash em `models.lock.yaml`. Estilo e pose bank são globais e de primeira classe — é isso que faz 100 personagens compartilharem uma linguagem visual.
>
> **E começaria hoje pelo MVP com a personagem mais difícil**, porque a única pergunta que importa é: *a identidade sobrevive à cadeia inteira?* Todo o resto é engenharia depois de saber a resposta.

---

## Perguntas em aberto

Preciso destas respostas antes de criar qualquer estrutura:

1. **Resolução alvo do jogo e altura do sprite na tela** — destrava a seção de Resolução.
2. **Decisão sobre Illustrious / FAIPL** — se for "não usar nada com licença ambígua", travo tudo em Apache/MIT/BSD e o SDXL vira apenas plano B.
3. **Confirmação do veredito de animação** (rig cutout em vez de frames IA) — é a decisão mais consequente do relatório e muda o FLOW 04 inteiro.

---

## Fontes

Consultadas em 2026-09-07. Ecossistema de IA generativa muda rápido — **reverificar licenças antes de qualquer decisão comercial definitiva.**

<a id="f1"></a>[1] Comfy.org — Qwen-Image-Edit workflows / build 2511 · https://comfy.org/workflows/model/qwen-image-edit/
<a id="f2"></a>[2] Thunder Compute — Qwen Image ComfyUI (2026) · https://www.thundercompute.com/blog/qwen-image-edit-comfyui
<a id="f3"></a>[3] Thunder Compute — Best Open-Source Image Generation Models (2026) · https://www.thundercompute.com/blog/best-open-source-image-generation-models
<a id="f4"></a>[4] r/StableDiffusion — Pony, Illustrious e NOOB: questões de licença · https://www.reddit.com/r/StableDiffusion/comments/1ib9v9s/pony_illustrious_and_noob_have_licensing_issues/
<a id="f5"></a>[5] aireiter — Best Background Removal API (teste de 5 pipelines; BiRefNet MIT vs RMBG-2.0 CC BY-NC) · https://aireiter.com/blog/best-background-removal-api
<a id="f6"></a>[6] OfflineCreator — ComfyUI vs AUTOMATIC1111 vs InvokeAI 2026 · https://offlinecreator.com/compare/comfyui-vs-automatic1111-vs-invokeai-2026
<a id="f7"></a>[7] BuilderAI — Instruction Image Editing 2026: Kontext vs Qwen vs Step1X · https://builderai.tools/blog/ai-image-editing-flux-kontext-qwen-image-edit-step1x
<a id="f8"></a>[8] Hugging Face — InstantX/Qwen-Image-ControlNet-Union · https://huggingface.co/InstantX/Qwen-Image-ControlNet-Union
<a id="f9"></a>[9] Blog ComfyUI — Qwen Image ControlNet & LoRA · https://blog.comfy.org/p/comfyui-now-supports-qwen-image-controlnet
<a id="f10"></a>[10] OneGen — Real-ESRGAN: guia prático (licença BSD-3, modelo anime 6B) · https://onegen.ai/project/enhancing-image-quality-with-real-esrgan-a-comprehensive-guide/
<a id="f11"></a>[11] Fora Soft — Real-ESRGAN / BasicVSR++ playbook 2026 (licenças) · https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/real-esrgan-basicvsr-ott-archive-upscaling
<a id="f12"></a>[12] VanceAI — Video2X Review 2026 (engines Vulkan, RIFE, requisitos) · https://vanceai.com/video-upscaler/video2x-review/
<a id="f13"></a>[13] Open Source For U — Alibaba open-sources Wan-Animate-2 (Apache 2.0) · https://www.opensourceforu.com/2026/08/alibaba-open-sources-wan-animate-2/
<a id="f14"></a>[14] Thunder Compute — Wan 2.2 ComfyUI (VRAM, licença, custo) · https://www.thundercompute.com/blog/wan-2-2-comfyui-ai-video-model
<a id="f15"></a>[15] Runpod Docs — ComfyUI-to-API / Serverless · https://docs.runpod.io/community-solutions/comfyui-to-api/overview
<a id="f16"></a>[16] Lewdly — Forge UI vs ComfyUI 2026 (declínio do A1111, benchmarks) · https://lewdly.ai/blog/forge-ui-vs-comfyui-nsfw-2026
<a id="f17"></a>[17] Local AI Master — Qwen-Image-Edit local: requisitos de VRAM · https://localaimaster.com/blog/qwen-image-edit-local-guide
<a id="f18"></a>[18] Simplismart — The Best Open-Source Image Models of 2026 (licenças) · https://www.simplismart.ai/comparisons/best-open-source-image-generation-models-to-deploy-in-2026
<a id="f19"></a>[19] Botmonster — Local image models 2026: Qwen vs FLUX vs SDXL · https://botmonster.com/ai/best-local-image-generation-models-2026/
<a id="f20"></a>[20] Hugging Face — Discussão de licença Illustrious-XL v2.0 (resposta oficial OnomaAI) · https://huggingface.co/OnomaAIResearch/Illustrious-XL-v2.0/discussions/1
<a id="f21"></a>[21] Site oficial Illustrious XL (FAIPL / OpenRAIL-M, restrição closed-source) · https://illustriousxl.org/
<a id="f22"></a>[22] Pixazo — Best Open-Source AI Image Generation Models 2026 · https://www.pixazo.ai/blog/top-open-source-image-generation-models
<a id="f23"></a>[23] fal.ai — Bria RMBG 2.0 (dados licenciados, $0.018/img, pesos comerciais sob contrato) · https://fal.ai/models/fal-ai/bria/background/remove
<a id="f24"></a>[24] Comfy.icu — BiRefNet Remove Background (MIT, nativo no ComfyUI desde mai/2026) · https://comfy.icu/node/BiRefNet_Remove_Background
<a id="f25"></a>[25] Artokun — WAN Animate 2.2 in ComfyUI (Apache 2.0, VRAM) · https://artokun.mintlify.app/blog/wan-animate-comfyui
<a id="f26"></a>[26] Lvmin Zhang & Maneesh Agrawala — LayerDiffuse (página do projeto) · https://lllyasviel.github.io/pages/layerdiffuse/ · arXiv 2402.17113
<a id="f27"></a>[27] r/StableDiffusion — ausência de saída com alpha em modelos novos · https://www.reddit.com/r/StableDiffusion/comments/1rldv6s/is_there_a_way_flux_klein_9b_can_output_an_image/
<a id="f28"></a>[28] GitHub — aivisionslab-studios/rx580-local-ai-guide (autópsia: ROCm, DirectML, OpenVINO) · https://github.com/aivisionslab-studios/rx580-local-ai-guide
<a id="f29"></a>[29] Medium — Running Local AI on an AMD RX 580 in 2026: Vulkan guide · https://medium.com/@aivisionslab/running-local-ai-on-an-amd-rx-580-in-2026-the-complete-vulkan-guide-7c2592cdb020
<a id="f30"></a>[30] rentry — Stable Diffusion com RX580 (gfx803): recompilar ROCm 5.1.3 · https://rentry.co/sd-amd-gfx803-gentoo
<a id="f31"></a>[31] ComfyUI Wiki — Wan-Animate-2 e Lite (nós nativos, ~12,5 GB de RAM p/ cache) · https://comfyui-wiki.com/en/news/2026-08-07-wan-animate-2
<a id="f32"></a>[32] Earngenix — ComfyUI Character Consistency (prompt sobrepõe referência) · https://www.earngenix.com/tutorials/character-consistency-comfyui
<a id="f33"></a>[33] r/godot — Handling Multiple Animations Efficiently in Godot (custo por bone) · https://www.reddit.com/r/godot/comments/1h8fkpf/handling_multiple_animations_efficiently_in_godot/
<a id="f34"></a>[34] Spritesheets.ai — Godot Spritesheet Animation: AnimatedSprite2D vs AnimationPlayer · https://www.spritesheets.ai/blog/godot-spritesheet-animation-guide
<a id="f35"></a>[35] Uhiyama Lab — [Godot] AnimatedSprite2D vs AnimationPlayer · https://uhiyama-lab.com/en/notes/godot/animatedsprite2d-vs-animationplayer-comparison/
<a id="f36"></a>[36] note.com (referenciando docs.live2d.com) — criar modelo Live2D a partir de partes PNG → PSD · https://note.com/sagi3000/n/n5dd7b37773a7?hl=en
<a id="f37"></a>[37] imagetolayers — AI Layer Splitter for Live2D (entrega raster; não cria rig) · https://www.imagetolayers.com/character-to-layers/live2d

---

*Documento de pesquisa. Nenhuma ferramenta foi instalada, nenhum modelo baixado, nenhum treinamento iniciado, nenhum workflow definitivo criado.*

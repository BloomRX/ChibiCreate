# Pesquisa — DESIGN / OUTFIT TRANSFER para a Run 003

Data: 2026-09-09 · Linha EXPERIMENTAL · Fase: pesquisa antes de implementar

> Não substitui FLUX, Flow 01, quality gates, `style.yaml` nem o pipeline
> oficial. Não cria master, animação nem LoRA.

---

## 1. Problema

A `run_003/output.png` já entrega identidade, rosto, cabelo, chifres,
proporção e silhueta. Falta fidelidade em **roupa, capa, ornamentos
dourados e acessórios**. A hipótese é preservar a base chibi e transferir o
design original, em vez de regerar a personagem.

## 2. Inspeção dos artefatos reais (feita antes de qualquer decisão)

| arquivo | tamanho | modo | observação |
|---|---|---|---|
| `characters/waifu_001/reference/full_body.png` | 1024×1024 | RGBA | alpha real (47% opaco) |
| `characters/waifu_001/reference/outfit.png` | 407×512 | RGBA | **alpha todo 255** |
| `characters/waifu_001/reference/face.png` | 512×512 | RGBA | alpha real |
| `run_003/output.png` | — | — | **NÃO existe no repositório** |

Três constatações que mudam o desenho da solução:

**(a) `outfit.png` não é uma peça de roupa segmentada.** É um recorte
retangular de `full_body.png` (casamento exato em x=289, y=338 — verificado
por varredura), gerado por "recorte heurístico baseado em frações da caixa
do sujeito", como o próprio `reference.metadata.json` declara, com
`[HUMAN REVIEW REQUIRED]` registrado. Ele contém corpo, pele, pernas e
fundo, não só a roupa. **Compor `outfit.png` diretamente sobre a Run 003
colaria pedaços de corpo da personagem original.**

**(b) Cabelo e capa não são separáveis por cor.** Medido:
cabelo ≈ RGB(108, 91, 86), capa ≈ RGB(63, 66, 68), distância média **29,5**
— abaixo de qualquer limiar utilizável. 26,8% do sujeito é escuro e ambos
caem nesse bloco. Segmentação por cor/k-means **falha** para separar capa de
cabelo. Os ornamentos dourados, em contraste, são **0,9%** dos pixels e
altamente distintos (R > B + 40): esses sim são segmentáveis por cor.

**(c) `run_003/output.png` está fora do Git** (`experiments/**/*.png` é
gitignored, por regra do projeto). Entra por upload, como o NB2 já faz.

## 3. Técnicas avaliadas

### 3.1 Não-generativas (preferidas pela diretiva)

| técnica | adequação ao caso | veredito |
|---|---|---|
| **Affine / perspective (OpenCV)** | 4+ pontos, transformação global. Não acomoda torso chibi mais curto e cabeça maior ao mesmo tempo | base útil, insuficiente sozinha |
| **Thin Plate Spline (TPS)** | deformação suave por pares de pontos de controle; padrão histórico em virtual try-on | **melhor candidata** |
| **Piecewise affine** | malha triangulada; controla regiões independentemente | boa para peças rígidas (ornamentos) |
| **Alpha matting / composição** | necessário no fim de qualquer rota | obrigatório |
| **Segmentação por cor (k-means/threshold)** | **falha**: capa e cabelo indistinguíveis (2b) | descartada como método único |
| **GrabCut / watershed (OpenCV)** | segmentação assistida por semente geométrica | viável para máscaras |

Sobre TPS, a literatura é explícita quanto ao limite: Mir et al. (CVPR 2020,
Pix2Surf) e SwapNet (ECCV 2018) usam *shape context + TPS* como **baseline**
e mostram que ele **não é preciso o bastante** quando as geometrias diferem
muito. Isso é exatamente o nosso caso (proporções realistas → chibi). É um
argumento para **não prometer** que o warping resolve sozinho.

### 3.2 Modelos de edição mascarada (para registro; NÃO implementar agora)

| modelo | licença | comercial | VRAM | máscara | referência |
|---|---|---|---|---|---|
| **FLUX.1 Fill [dev]** | FLUX-1-dev Non-Commercial | **não** | ~24 GB | sim | não nativa |
| **Step1X-Edit** | Apache 2.0 | sim | ~24 GB+ (FP8 menor) | não nativa | instrução |
| **SDXL Inpainting** | CreativeML OpenRAIL-M | com ressalvas | ~8-10 GB | sim | via IP-Adapter |
| **Ideogram 4.0** | Non-Commercial Model Agreement | **não** | ~24 GB | — | — |
| **A²-Edit** | pesquisa (backbone FLUX.1 Fill) | **não** | alto | sim | **sim, nativa** |
| **Qwen-Image-Edit** | Apache 2.0 | sim | ver fase anterior | sim | sim |

Conclusão: **não há hoje um editor mascarado open-weight, comercialmente
livre, com suporte nativo a imagem de referência e leve para T4.** O que
mais se aproxima funcionalmente (A²-Edit) tem backbone não-comercial. O
único comercialmente limpo com referência é o Qwen — que a diretiva manda
não reimplementar agora, e que está `BLOCKED` por RAM no T4.

## 4. Ranking

1. **B — máscaras separadas + TPS por região + composição** (recomendada)
2. **A — máscara única + transformação global** (baseline de comparação)
3. **C — editor mascarado** — *não implementar*: sem candidato viável (§3.2)

## 5. Recomendação e justificativa

Implementar **A e B, ambas 100% não-generativas**, com A servindo de
controle para medir o que as máscaras separadas de fato acrescentam.

Por que máscaras separadas: os elementos têm rigidez diferente. Ornamentos
dourados são peças rígidas de formato reconhecível — deformá-los destrói o
design. A capa é tecido e tolera deformação ampla. Aplicar o mesmo warp aos
dois é o erro previsível.

Como as máscaras são construídas, dado (2b): **não por cor apenas**. Ouro sai
por cor (é separável); capa e roupa saem por **cor escura ∩ região geométrica
∩ alpha do sujeito**, com a geometria vindo de `DEFAULT_REGIONS`/caixa do
sujeito — que já existe no projeto e **não será alterada por preferência
estética**, conforme GATE 2.1. Todas as máscaras são salvas em disco
(`source`, `cleaned`, `transformed`) e versionadas.

## 6. Limitações — declaradas antes de implementar

1. **TPS não resolve sozinho** (§3.1). Esperar costuras e proporção
   imperfeita, sobretudo na transição capa/pernas.
2. **`outfit.png` é inadequado como fonte** (2a). A fonte correta é
   `full_body.png` + máscara. Usar `outfit.png` cru transferiria corpo.
3. **Máscaras heurísticas** herdam o `[HUMAN REVIEW REQUIRED]` do
   `reference.metadata.json`. Não são segmentação semântica.
4. **Pontos de controle**: sem detector de pose treinado para chibi, os pares
   vêm de landmarks geométricos da silhueta (ombros, cintura, base). É
   aproximação, não correspondência anatômica.
5. **Estilo**: a arte original tem sombreado realista; a Run 003 é chibi.
   Composição direta pode gerar shading incompatível — é um risco conhecido,
   não um bug.
6. **Sem run_003 no repo**, a execução A/B depende de upload.

## 7. Dependências e licenças

| biblioteca | versão | licença | comercial |
|---|---|---|---|
| numpy | 2.4.6 | BSD-3-Clause | sim |
| Pillow | 12.3.0 | MIT-CMU | sim |
| scikit-image | 0.26.0 | BSD-3-Clause | sim |
| opencv-python-headless | 5.0.0 | Apache 2.0 | sim |

Todas permissivas e compatíveis com uso comercial. Nenhum peso de modelo,
nenhum download, nenhuma dependência nova de licença duvidosa.

## 8. Critério de sucesso

Não "mais bonita". O alvo é: *a personagem da Run 003 usando o design
original* — não uma personagem nova inspirada nela. Eixo principal
**DESIGN_PRESERVATION**; avaliação **humana**.

Verificação objetiva possível e exigida: **fora da máscara, diferença de
pixels == 0**. Isso é testável e é o que garante que rosto, olhos, cabelo,
chifres e silhueta da Run 003 permaneçam intactos.

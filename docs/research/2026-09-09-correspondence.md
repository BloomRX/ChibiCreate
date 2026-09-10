# Correspondencia geometrica REAL <-> CHIBI

Data: 2026-09-09 · Status: implementado em `scripts/chibi/character_correspondence.py`
Escopo: **apenas correspondencia e transformacao de mascara.** Nao ha composicao,
nao ha warp da arte, nao ha geracao. A Run 003 nao e alterada.

---

## 1. O erro que motivou este documento

A mascara da roupa e definida no espaco geometrico da personagem **REAL**
(`full_body.png`). A Run 003 e **CHIBI**: outras proporcoes, outra escala,
outras posicoes. Aplicar a mascara da real diretamente sobre a chibi e
invalido — os dois espacos nao coincidem.

Pipeline correto, nesta ordem:

```
REAL -> segmentacao da roupa -> correspondencia REAL<->CHIBI
     -> mascara em coordenadas CHIBI -> MASK REVIEW -> warp/composicao
```

**TPS e transformacao, nunca a etapa de correspondencia.** A ordem
`mascara -> TPS arbitrario -> composicao` esta proibida.

---

## 2. Pesquisa: o que existe e o que foi descartado

### 2.1 Estimadores de pose para personagens ilustradas — DESCARTADOS

Tudo que foi encontrado e rede neural treinada:

| Metodo | Natureza | Por que nao serve |
|---|---|---|
| `ShuhongChen/bizarre-pose-estimator` (WACV 2022) | transfer learning + checkpoints | viola "2D, explicavel, barato"; exige download de pesos |
| Khungurn & Chou | CNN treinada em ~1M renders | idem |
| AnimeDrawingsDataset | dataset + modelo | idem |
| OpenPose (usado por SegAnimeChara) | rede treinada, esqueleto humano | idem |

Alem do custo, nenhum deles conhece **proporcao chibi**. Um survey da area
registra que modelos SMPL/UDP "nao lidam com as formas corporais diversas de
personagens anime" — o que reforca o descarte para o nosso caso, em que a
cabeca pode ocupar de 1/3 a 1/2 da altura.

### 2.2 Shape context (Belongie et al.) — base conceitual adotada

Pipeline canonico: (1) amostrar pontos nas bordas, (2) descritor log-polar por
ponto, (3) correspondencia como **problema de atribuicao linear**, (4) **TPS
regularizado como transformacao alinhadora**. A licao aproveitada e a
**separacao entre correspondencia e transformacao**, exatamente o que a
diretiva exige.

Nao adotamos o shape context completo: ele pareia pontos de borda por
similaridade de forma, e duas silhuetas com proporcoes tao diferentes (adulto
esbelto vs chibi cabecudo) nao tem forma comparavel. Adotamos correspondencia
esparsa por **papel anatomico**, que e mais explicavel e revisavel a mao.

### 2.3 TPS — ressalvas registradas

- O parametro de regularizacao **precisa ser ajustado a mao**; para partes
  rigidas, afim por landmarks costuma dar resultado melhor que TPS.
- TPS **nao e inverso-consistente**: trocar origem/destino nao devolve a inversa.
- `cv2.ThinPlateSplineShapeTransformer` "nao e solucao geral de warping, e
  parte interna do processo de shape matching". Usamos
  `skimage.transform.ThinPlateSplineTransform`.

**Nao assumir que warping simples sera suficiente.** Por isso a etapa de
review visual vem antes de qualquer composicao.

---

## 3. Descoberta critica: o alpha de `full_body.png` e inutil como silhueta

O canal alpha e um **retangulo solido**: 568 px de largura em *toda* linha,
valores so `{0, 255}`, 494.160 px no total. `subject_mask()` devolve esse
retangulo, o que produz perfil de largura **constante 1.000** e landmarks sem
sentido algum.

A silhueta real vem da separacao pela cor de fundo lisa `(133,133,132)`, com
criterio `|rgb - bg|.sum() > 30`:

| medida | valor |
|---|---|
| pixels de corpo | **189.667** (vs 494.160 do alpha) |
| bbox do sujeito | `(228, 103, 796, 973)` |
| altura / largura | 870 / 568 |

`silhouette()` detecta o alpha degenerado automaticamente e cai para a
separacao por cor de fundo. Ha teste travando os dois numeros.

---

## 4. O que o contorno pode e o que NAO pode afirmar

Perfil de largura medido (fracao da altura -> largura relativa):

```
0.05 -> 0.181   0.40 -> 0.451   0.65 -> 0.431   0.90 -> 0.776
0.15 -> 0.211   0.45 -> 0.504   0.75 -> 0.489   0.95 -> 1.000
0.25 -> 0.283   0.50 -> 0.523   0.85 -> 0.585
0.35 -> 0.349   0.55 -> 0.403
```

O perfil sobe de forma quase monotona. **Nao ha estrangulamento de pescoco**
(cabelo longo funde cabeca e ombros) e **nao ha cintura visivel** (a capa
cobre o contorno lateral). O maximo em 0.95 e a **barra do manto**, nao os pes.

Uma primeira versao tentou adivinhar esses pontos assim mesmo. Resultado
verificado na imagem:

| landmark chutado | onde foi parar |
|---|---|
| `neck` | ponta do chifre (ny 0.031) |
| `waist` | altura das costelas |
| `hip_left/right` | borda lateral da capa |
| `ankle_left/right` | barra do manto |

**Landmark errado e pior que landmark ausente**: ele arrasta a transformacao
inteira. Esses chutes foram removidos.

Detalhe do falso par de tornozelos: na porcao baixa a barra da capa se divide
em dois blocos ao redor dos pes. Em `f=0.99` sobram dois blocos estreitos com
centros relativos **0.253 e 0.495** — canto do manto + pe. Passa no filtro de
largura, mas o ponto medio (0.37) fica longe do eixo do corpo. Por isso o
detector exige tambem **simetria em torno do eixo**, e nesta arte corretamente
**nao emite tornozelos**.

### Landmarks efetivamente derivados

| landmark | norm (x, y) | conf | base |
|---|---|---|---|
| `top_of_head` | (0.470, 0.000) | 1.0 | extremo vertical |
| `silhouette_bottom` | (0.505, 0.999) | 1.0 | extremo vertical |
| `shoulder_left` | (0.259, 0.484) | 0.45 | maior largura da metade superior |
| `shoulder_right` | (0.746, 0.484) | 0.45 | idem |

`shoulder_*` e a **extremidade lateral** (manga/manto), nao a articulacao
anatomica — util para ancorar escala em X, e a confianca baixa (0.45) declara
isso. O resto entra por `characters/waifu_001/landmarks.yaml`.

---

## 5. Arquitetura

Quatro fontes de landmark, por precedencia: **`manual` > `config` > `derived` > ausente.**

```
characters/<id>/landmarks.yaml
  source:  landmarks da personagem REAL
  target:  landmarks da personagem CHIBI
```

Aceita `x,y` absoluto ou `nx,ny` normalizado (preferivel — sobrevive a
mudanca de resolucao). `None` remove um landmark. **Nome fora de
`LANDMARK_NAMES` e erro**, para que um `shoulder_lft` digitado errado nao seja
ignorado em silencio.

Correspondencia: so entra o par que existe **nos dois lados**. Parcial e o
modo normal de operacao; o que sobra fica em
`diagnostics.landmarks_source_only`.

Escolha automatica da transformacao:

| pares | transformacao | peso na confianca |
|---|---|---|
| >= 4 | TPS | 1.00 |
| 3 | afim | 0.85 |
| 2 | similaridade | 0.70 |
| < 2 | `CorrespondenceError` | — |

`confidence = 0.4 * cobertura + 0.4 * acordo posicional + 0.2 * confianca base`,
ponderada pelo tipo. E um numero de **triagem**, nao um selo de aprovacao.

`clip_to_target(masks, target_subject, banned)` e obrigatorio depois do warp:
o warp e continuo e pode empurrar pixels para fora do corpo ou por cima do
rosto da chibi. E ele que sustenta o criterio
`mask_protected_overlap_pixels == 0` **no espaco do alvo**.

`Correspondence.as_dict()` registra no recipe: `kind`, `n_pairs`, `pairs`,
`confidence`, landmarks e bboxes dos dois lados, e `diagnostics`.

---

## 6. Estado do teste com waifu_001

SOURCE = `full_body.png` — pronto e conferido visualmente (4 derivados + 13 de config).

TARGET = `run_003/output.png` — **AUSENTE do repositorio** (`experiments/**/*.png`
e gitignored; upload-only). Consequencias:

- `target: {}` em `landmarks.yaml`, vazio de proposito. Preencher valores sem
  ver a imagem seria invencao.
- Os seis artefatos visuais pedidos (landmarks na real, landmarks na chibi,
  linhas de correspondencia, mascara original, mascara transformada, overlay)
  **nao podem ser gerados** para a Run 003.
- O caminho completo foi validado contra um **alvo sintetico de proporcao
  chibi** (cabeca 210 px, corpo 180 px): TPS com 7 pares, `confidence 0.572`,
  mascara de 60.000 px -> 5.613 px, apos clip 5.019 px, **overlap protegido = 0**.

**[HUMAN REVIEW REQUIRED]** Subir `run_003/output.png` e preencher o bloco
`target`. Ate la a validacao visual real esta bloqueada.

---

## 7. Limites declarados

- Os valores de `source` em `landmarks.yaml` sao **calibracao da waifu_001**.
  Nao virar regra global — vale o mesmo que ja valia para `0.52`, `x 0.26-0.81`
  e as faixas de R-B.
- `confidence` nao decide nada sozinho. **Aprovacao e humana.**
- Nenhum modelo generativo foi adicionado. Dependencias: `numpy`, `Pillow`,
  `scikit-image`, `scipy` — todas ja presentes, licencas BSD.
- **PARADA OBRIGATORIA** apos o CORRESPONDENCE REVIEW. Nada de warp da arte,
  composicao ou geracao final antes da validacao visual humana.

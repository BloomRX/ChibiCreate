# ADR-005 — Ajustes do FLOW 01 após validação com arte real (GATE 2.1)

- **Data:** 2026-09-08
- **Status:** aceito
- **Gate:** 2.1 — validação do FLOW 01 com arte-fonte real
- **Personagem:** `waifu_001` (768×1152, RGB, **sem canal alpha**)

---

## Contexto

A Fase 2 foi implementada e testada apenas com fixtures sintéticas. O GATE 2.1
exigiu rodar o FLOW 01 sobre a arte real da personagem difícil do MVP:
cabelo longo, dois chifres, ornamentos de cabeça, mangas largas, **manto longo
que se espalha pelo chão**, detalhes dourados, elementos escuros adjacentes e
silhueta complexa.

A arte real expôs **duas falhas geométricas** que a fixture sintética não
podia expor, porque a fixture tinha canal alpha e a arte real não tem.

---

## Falha 1 — `subject_bbox` devolvia o canvas inteiro em arte sem alpha

### Evidência

```
source          : (768, 1152) RGB
subject_bbox    : (0, 0, 768, 1152)  -> 768x1152
bbox == canvas? : True

bbox real do sujeito (por contraste com o fundo):
  (28, 27, 746, 1126)  -> 718x1099
```

### Impacto

`region_by_fraction` calcula as regiões como frações da **caixa do sujeito**.
Com a caixa igual ao canvas, **todas** as frações passaram a ser medidas sobre
a imagem inteira — incluindo a moldura de fundo vazio. Todo o identity kit
saía deslocado. Esta é a falha raiz; as regiões em si não estavam erradas.

### Correção

Nova função `imaging.opaque_subject_bbox()`: quando o alpha é inteiramente
opaco, detecta o sujeito por **contraste com um fundo liso**, inferido pela
mediana dos quatro cantos. `subject_bbox()` recorre a ela apenas quando a
caixa por alpha coincide exatamente com o canvas.

Salvaguardas — a função devolve `None` (e nada acontece) se:

- os quatro cantos não concordarem entre si (`BG_CORNER_TOLERANCE = 45`);
- o resultado for degenerado (sujeito > 99,5% ou < 2% da imagem);
- não houver pixel algum diferente do fundo.

Linhas e colunas com menos de `0,2%` de pixels são descartadas como ruído de
compressão JPEG/PNG.

> **Isto não é remoção de fundo.** Nenhum pixel é alterado. Só se **mede** onde
> o sujeito está. A remoção continua sendo trabalho do BiRefNet (pesos não
> baixados) ou de uma fonte com alpha, e o aviso `[HUMAN REVIEW REQUIRED]`
> sobre ausência de alpha continua sendo emitido.

---

## Falha 2 — `outfit` cortava a base e as laterais do manto

### Evidência

Medição da silhueta real de `waifu_001` (fração da caixa do sujeito):

```
extremos da silhueta:
  esquerda: 0.0000   direita: 0.9982
  topo    : 0.0000   base   : 0.9989

outfit com left=0.05 / right=0.95 / bottom=0.95:
  margem inferior: -0.0489   <- negativo = CORTA
  silhueta perdida abaixo de bottom: 9.117 px (4,81%)
  essas linhas ocupam y = 0.949 .. 0.999
```

O conteúdo perdido era a **barra do manto** e a **ponta dos pés dourados**.

### Causa

As margens de 5% assumiam que a silhueta teria folga dentro da própria caixa.
Isso é falso por construção: a caixa do sujeito é justamente o menor retângulo
que contém a silhueta, então ela **sempre** encosta nas quatro bordas. Em
personagens com manto, capa ou saia longa, a área encostada é grande.

### Correção (mínima)

```diff
- "outfit": {"top": 0.18, "bottom": 0.95, "left": 0.05, "right": 0.95, ...}
+ "outfit": {"top": 0.18, "bottom": 1.0,  "left": 0.0,  "right": 1.0,  ...}
```

`top: 0.18` foi **mantido** — é o que define o recorte como "do tronco para
baixo", e não corta silhueta indevidamente.

### O que NÃO foi alterado

`face` e `hair` foram medidos e **mantidos como estavam**:

| Região | Faixa vertical | Silhueta ocupa | Limites atuais | Veredito |
|---|---|---|---|---|
| `hair` | y 0.00–0.28 | x 0.328–0.648 | 0.10–0.90 | folgado, não corta |
| `face` | y 0.02–0.20 | x 0.400–0.625 | 0.20–0.80 | folgado, não corta |

Havia uma "perda lateral" aparente de 0,83%/0,62% em `hair`, mas a inspeção
mostrou ser conteúdo de **outras partes do corpo**, fora da faixa vertical da
região — não é o cabelo sendo cortado. Alterar aqui seria mexer por estética,
o que o gate proíbe.

---

## Falha 3 (correlata) — paleta dominada pelo fundo

### Evidência

```
antes:  #858584 peso=0.661   <- cinza do fundo, 66% do peso
        #232527 peso=0.117
        #09090A peso=0.107
```

A paleta é a base do futuro gate `PALETTE_VALID`, que detecta *drift* de cor
entre o reference e o chibi master. Com dois terços do peso sendo o fundo do
splash art, a comparação mediria o cenário, não a personagem.

### Correção

`palette.extract()` passa a excluir os pixels de fundo **por cor** quando a
imagem não tem alpha útil, reaproveitando a mesma detecção de fundo liso.
Funciona tanto na fonte crua quanto no `full_body.png` já normalizado (que tem
bordas transparentes mas mantém o fundo original na área do sujeito). A
exclusão é registrada no campo `note` do `palette.json`.

```
depois: #25272A peso=0.303   cabelo / manto
        #121314 peso=0.185
        #030303 peso=0.180
        #EFD7CD peso=0.110   pele
        #4B3C36 peso=0.082
        #795E51 peso=0.056   dourados / meias
```

---

## Testes de regressão

Sete testes novos em `tests/test_flow01.py`, com a fixture
`make_flat_background_art()` — RGB, fundo cinza liso, silhueta encostando nas
bordas, imitando a geometria de `waifu_001`.

Cada teste foi verificado por **reversão deliberada** do conserto:

| Conserto revertido | Teste que falha | Mensagem |
|---|---|---|
| `outfit` para 0.05/0.95 | `test_flow01_outfit_loses_no_silhouette_on_flat_bg_art` | `24396 px de silhueta cortados na base` |
| idem | `test_outfit_region_covers_full_silhouette_width_and_base` | `cortaria a base do manto e os pes` |
| fallback de bbox | `test_subject_bbox_falls_back_when_no_alpha` | `caiu de volta no canvas inteiro` |

Um teste de regressão que não falha na presença do bug não vale nada — por
isso a verificação por reversão.

**Suíte completa: 71 testes (26 fundação + 45 fase 2), todos passando.**

---

## Consequências

- O FLOW 01 passa a funcionar em arte **sem alpha com fundo liso**, que é o
  formato mais comum de splash art / referência de personagem.
- Arte com fundo complexo (cenário detalhado) continua **sem** detecção: a
  função devolve `None` e a caixa volta a ser o canvas. `[TEST REQUIRED]` —
  ainda não validado com arte de fundo não-liso.
- `DEFAULT_REGIONS` continua sendo heurística, e continua marcada
  `[HUMAN REVIEW REQUIRED]` a cada execução. `reference_regions` no
  `character.yaml` continua sendo o mecanismo de correção por personagem.
- `top: 0.18` do `outfit` não foi validado contra personagens de proporção
  muito diferente (criança, mascote, quadrúpede). `[TEST REQUIRED]`.

# Arquitetura de mascaras — GLOBAL / CHARACTER-SPECIFIC / REGIONAL

Data: 2026-09-09 · Linha EXPERIMENTAL · Etapa: MASK REVIEW generalizada

> Nao altera Run 003, FLUX, Flow 01, quality gates nem o pipeline oficial.
> Nao executa warp nem composicao.

---

## 1. Problema que motivou a refatoracao

A primeira versao funcionava na waifu_001 — e so nela. Valores como
`cool_max = -2`, `waist = 0.52` e `leg_left = 0.26` estavam escritos no
codigo como se fossem verdades universais. Eram evidencias de **uma** arte.
Outra personagem herdaria silenciosamente numeros que nao descrevem o corpo
nem a roupa dela.

## 2. As tres camadas

```
mask generator
    v
estrategias genericas          <- GLOBAL
    v
overrides da personagem        <- CHARACTER-SPECIFIC (opcional)
    v
mascaras (+ rigidez por peca)  <- REGIONAL
    v
MASK REVIEW HUMANA
    v
warp / composicao              <- BLOQUEADO ate aprovacao
```

### GLOBAL — `scripts/chibi/mask_engine.py` + `mask_profile.derive_params`

Vale para qualquer personagem. **Nao contem nenhum numero da waifu_001** —
ha um teste que le o arquivo e falha se algum aparecer.

Quando um limiar e necessario, ele e **derivado da propria arte**:

| parametro | como e obtido | procedencia |
|---|---|---|
| `dark_max` | Otsu sobre a luminancia do sujeito | `derived:otsu_luminance` |
| `cool_max` / `warm_min` | percentis 40/70 de `R-B` nos pixels escuros | `derived:percentile*_rb` |
| `waist` | vale do perfil vertical do tecido; se nao houver, alargamento sustentado | `derived:min_cool_fabric_profile` |
| `leg_left` / `leg_right` | colunas de maior ocupacao na porcao baixa | `derived:lower_subject_percentiles` |
| `torso_half_width` | largura do tecido no alto do tronco | `derived:collar_width` |

Estrategias — o que o motor sabe fazer, em linguagem de algoritmo e nao de
numero: *tecido central acima da cintura e torso*; *tecido lateral e manga*;
*tecido abaixo da cintura e capa, dividida por lado*; *cor de destaque e
ornamento*; *cabelo e isolado por conectividade a partir da cabeca*.

`STRUCTURAL_ANATOMY` guarda fracoes anatomicas genericas (cabeca no topo,
calcado no ultimo decimo). Sao propositalmente redondas e conservadoras —
descrevem um bipede frontal, nao a waifu_001.

### CHARACTER-SPECIFIC — `characters/<id>/masks.yaml`

**Opcional.** Sem o arquivo, a personagem roda 100% generica. Segue a mesma
convencao de `character.yaml`, que ja usa overrides opcionais vazios.

Chaves aceitas: `strategy`, `thresholds`, `protected_regions`,
`region_definitions`, `geometric_constraints`, `color_hints`,
`connectivity_seeds`, `manual_hints`, `rigidity`, `notes`.
Chave desconhecida e **erro**, para que um typo nao vire parametro ignorado.

O perfil da waifu_001 sobrescreve **apenas dois** valores, e por um motivo
verificavel: a derivacao generica acerta luminancia, eixo cromatico e ate a
cintura (0.5253 contra 0.52 medido a mao), mas falha em `leg_left/leg_right`
porque a barra da capa se espalha pelo chao e a ocupacao das colunas cobre a
largura inteira. Sem o override, a faixa do calcado protege a largura toda e
a capa para em `bottom = 0.90` em vez de `0.995`. Ha um teste que exige essa
melhora — o override precisa se justificar.

### REGIONAL — `mask_profile.DEFAULT_RIGIDITY` / `DEFAULT_STRATEGY`

Propriedade do **tipo de peca**, nao da personagem: ornamento e `rigid` em
qualquer arte (o formato *e* o design); tecido e `cloth`; o tronco e
`semi_rigid`. Uma personagem pode sobrescrever, mas raramente precisa.

## 3. Validacao

Dois fixtures, como pedido:

1. **waifu_001** — arte real, inalterada.
2. **sintetica** (`tests/fixtures/synthetic_character.py`) — nao e arte: e um
   alvo geometrico com a paleta **invertida**.

| aspecto | waifu_001 | sintetica |
|---|---|---|
| capa | escura e FRIA (`R-B<0`) | escura e QUENTE (`R-B>0`) |
| pernas | escuras e QUENTES | escuras e FRIAS |
| cabelo | escuro | CLARO |
| destaque | dourado | ciano |
| silhueta | alta e estreita | baixa e larga |

Se o motor tivesse qualquer dependencia das cores da waifu_001, a sintetica
falharia. Ela passa com `all_clear`, e os limiares derivados diferem entre as
duas em pelo menos tres parametros.

**Verificacao de vazamento entre personagens:** rodar a waifu com perfil e
depois a sintetica (e vice-versa) nao altera hash nenhum de mascara. Mutar um
perfil carregado nao contamina o proximo carregamento.

## 4. Defeitos reais encontrados durante a refatoracao

Nenhum foi detectado por teste — todos por inspecao dos dados ou dos overlays:

1. **`accent_mask` tinha viés de ouro** (`r >= b`). Falhava em ornamento
   ciano. Corrigido: saturacao alta basta, sem preferencia de matiz.
2. **"Tecido = R-B <= cool_max" era fragil.** Quando duas pecas da mesma
   roupa tinham tons ligeiramente diferentes, a de tom maior era descartada e
   a peca sumia (mangas da sintetica). Tecido passou a ser definido por
   **exclusao**: material escuro que sobrou apos remover pele, cabelo e pernas.
3. **Divisao da capa por componente inteiro** esvaziava um dos lados quando
   as duas metades se tocam. Agora, componente que ocupa os dois lados de
   forma relevante e dividido **por pixel**.
4. **`closing` empurrava mascara para fora da silhueta.** Reancoragem no
   sujeito ao final.
5. **`inferiores` era sempre zerada** por viver dentro de `sapatos`. Criada
   uma excecao **declarada e estreita** (`ALLOWED_PROTECTED_OVERLAP`), em vez
   de enfraquecer a invariante para todos.
6. **Cintura por minimo global** caia na borda da janela em silhueta de manga
   estreita. Trocado por vale local, com alargamento como fallback.

## 5. Invariantes mantidas

* `mask_protected_overlap_pixels == 0` para toda peca, nas duas personagens.
  Unica excecao, declarada em codigo e coberta por teste: ornamento de
  calcado dentro de `sapatos`.
* `outside_mask_pixel_difference == 0` continua garantido em
  `design_transfer.py`, intocado nesta etapa.
* **Fonte imutavel** — sha256 de `full_body.png` conferido antes e depois.
* **Aprovacao e humana.** `all_clear()` cobre so o objetivo (overlap zero,
  mascara nao vazia); `approved` permanece `False`.

## 6. Status

Etapa parada na MASK REVIEW, aguardando avaliacao visual. Warp e composicao
nao foram executados e nenhum output novo foi gerado.

# STYLE vs IDENTITY

A distinção mais importante da pipeline. Ela decide o que é global e o que é
por personagem — e, mais adiante, o que um Style LoRA poderia aprender e o que
ele **nunca** deve tocar.

---

## A separação

**IDENTIDADE** = quem é a personagem.
**ESTILO** = como essa personagem é desenhada em versão chibi.

| | STYLE | IDENTITY |
|---|---|---|
| Escopo | global (todas) | por personagem |
| Onde mora | `styles/chibi/` | `characters/<id>/` |
| Muda quando | redefinimos a linguagem visual | trocamos de personagem |
| Controla | proporções, rendering, simplificação facial, linguagem chibi, tratamento visual | cabelo (design e cor), cor dos olhos, roupa, armas, acessórios, traços distintivos, silhueta específica |

## Por que isso importa

O objetivo não é gerar "uma personagem chibi bonita". É gerar personagens que
**pareçam pertencer ao mesmo jogo**.

Uma pipeline que trata cada personagem isoladamente produz 20 chibis que não
conversam entre si — proporções diferentes, olhos diferentes, densidade de
detalhe diferente. Consistência não emerge sozinha: precisa de um eixo global
explícito.

A regra prática:

> Se mudar isso afeta **todas** as personagens → é STYLE.
> Se afeta **uma** → é IDENTITY.

## O teste de decisão

Casos que costumam confundir:

| Elemento | Eixo | Por quê |
|---|---|---|
| "olhos grandes" | STYLE | é a proporção do olho na linguagem chibi |
| "olhos vermelhos" | IDENTITY | é a cor daquela personagem |
| "cabelo simplificado em poucas mechas" | STYLE | é o nível de simplificação |
| "cabelo preto com franja reta" | IDENTITY | é o design daquela personagem |
| "roupa simplificada" | STYLE | é quanto detalhe sobrevive |
| "manto preto com ornamentos dourados" | IDENTITY | é a roupa daquela personagem |
| "shading suave" | STYLE | é o acabamento |
| "chifres" | IDENTITY | é um traço distintivo |

## Consequência para o prompt

Regra já em vigor no `style.yaml`, e que esta separação explica:

> O bloco de prompt de estilo descreve **apenas** estilo e enquadramento.
> **Nunca** rosto, cabelo, cor de olho, roupa ou acessório.

Motivo (registrado na pesquisa): descrever traços no texto **compete com a
imagem de referência** e é a causa nº 1 de o rosto mudar. A identidade deve
vir da imagem; o estilo, do texto.

## Consequência para a avaliação de modelos

Um modelo pode acertar um eixo e errar o outro:

- **estilo bom, identidade ruim** → chibi bonito de outra personagem
- **identidade boa, estilo ruim** → a personagem certa, mas fora da linguagem
  visual do jogo

São falhas diferentes, com soluções diferentes. Por isso a ficha de avaliação
pontua **STYLE e IDENTITY separadamente**, e `OVERALL` **não** é média
aritmética — é julgamento humano.

## Consequência para a estratégia futura

```
STYLE    → global    → candidato a Style LoRA (fase futura, hoje desabilitado)
IDENTITY → por personagem → vem das imagens de referência
```

Se um dia treinarmos um Style LoRA, ele deve aprender **apenas** o eixo
esquerdo. Um LoRA que aprendeu identidade junto contamina todas as
personagens seguintes com traços de quem estava no dataset.

**Hoje:** `style.lora.enabled: false`. Não treinar. A arquitetura fica
preparada, a decisão fica humana.

## Limite do agente

O agente **não** define estilo por conta própria. Pode registrar e organizar o
que é observável nas referências fornecidas; não pode inventar proporção,
tratamento de shading ou qualquer decisão artística sem evidência visual.

Marcar `[TEST REQUIRED]` para o que não foi verificado, e
`[HUMAN REVIEW REQUIRED]` para o que exige olho humano.

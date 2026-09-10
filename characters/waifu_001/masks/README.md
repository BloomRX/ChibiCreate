# Máscaras de inpaint — waifu_001

Máscara **manual** para o WAI INPAINT-XL LAB. Nesta fase é de propósito:
segmentação automática é outro problema, e uma máscara ruim invalidaria o
experimento inteiro.

## `outfit_mask.png` — [ARQUIVO AUSENTE, precisa ser criado]

| requisito | valor |
|---|---|
| tamanho | **idêntico** ao da `SOURCE_IMAGE` |
| formato | PNG, tons de cinza ou RGB |
| **branco** | a roupa — o que **pode** ser redesenhado |
| **preto** | tudo que deve ser preservado |

Preto obrigatório em: rosto, cabelo, olhos, chifres, pele fora da roupa,
braços e pernas fora da roupa, acessórios fora da região, fundo.
Calçados só entram se o experimento disser explicitamente.

Não precisa de margem: `MASK_DILATION` (default 8 px) e `MASK_FEATHER`
(6 px) são aplicados no grafo. Deixe a máscara **colada no contorno** da
roupa — a dilatação já dá a folga para reconstruir as bordas.

A célula 2 bloqueia se a máscara não existir, se o tamanho não bater com a
source, se for toda preta, se cobrir menos de 1% ou mais de 60% da imagem.
Acima de 60% deixa de ser correção localizada e vira retransformação, que é
o que esta fase evita.

`outfit.png` (em `reference/`) **não serve como máscara**: é um crop visual
do design, não uma região semântica.

# CHIBI FROM CONCEPT — da concept art ao chibi

`notebooks/chibi_from_concept.ipynb`

## O problema que resolve

O `flux2_klein_4b_eval.ipynb` exige a personagem ja versionada em
`characters/<id>/reference/`. Isso obriga a commitar arte pesada. Hoje a
`waifu_002` e a `waifu_003` estao no repo como **ponteiros LFS de 132
bytes** — o conteudo real nao chega ao clone, e o notebook nao roda.

Aqui a arte entra por **upload** e nada precisa ser commitado.

## Fluxo

```
upload da concept art
  -> FLOW 01 (deterministico, local)  -> source/ + reference/
  -> FLUX.2 klein 4B                  -> chibi
  -> 2 ZIPs
```

O FLOW 01 ja existia e nao foi reescrito: `chibi character new` +
`chibi flow01 <id>` produzem `full_body`, `face`, `hair`, `outfit`,
`palette`, `sheet` em ~2 s, sem IA e sem aleatoriedade.

## Os tres modos de prompt

| modo | quando usar | consequencia |
|---|---|---|
| `generico` | padrao | reutilizavel para 100+ personagens; identidade vem das imagens |
| `auto_from_image` | descoberta | tagger le a arte; prompt deixa de ser comparavel |
| `manual` | controle total | validado, mas por sua conta |

O modo generico **bloqueia** se o texto vazar identidade — a validacao usa
`termos_especificos_no_prompt`, a mesma do WAI e do inpaint lab.

### Sobre o prompt automatico

Tagger: **WD14 SwinV2 v3** (`SmilingWolf/wd-swinv2-tagger-v3`),
**Apache-2.0**, ONNX em CPU. E o tagger consagrado para arte anime e nao
precisa de GPU nem chave de API.

Ele **nao entende** a personagem: devolve tags Danbooru por confianca. Tag
errada vira design errado no chibi, entao a saida e sempre
`[HUMAN REVIEW REQUIRED]` e o recipe registra
`character_specific_prompt: true` mais a lista de tags com a confianca de
cada uma.

**Consequencia que importa:** um prompt automatico descreve *aquela*
personagem. Duas execucoes com prompts automaticos diferentes nao sao
comparaveis entre si.

## Os dois ZIPs

| ZIP | conteudo | para que serve |
|---|---|---|
| `<id>_character_kit.zip` | `source/` + `reference/` + `character.yaml` + `hashes.json` | e o que iria para o Git; descompacte em `characters/` para reusar nos outros notebooks |
| `<id>_chibi_result.zip` | chibi + `recipe.json` + workflow resolvido + concept original e normalizada + `notebook_context.json` | o resultado desta execucao |

## Limites

- **Nao substitui** o `flux2_klein_4b_eval.ipynb`, que continua sendo o
  baseline historico das Runs 001/002/003 da waifu_001.
- Os recortes do identity kit sao **heuristicos** (fracoes da caixa do
  sujeito). A celula 3b mostra os quatro lado a lado para conferencia.
- O resultado sai `EXPERIMENTAL`. Nao e Chibi Master, nao esta aprovado:
  **avaliacao artistica e humana**.
- Arte sem canal alpha nao tem o fundo removido; o FLOW 01 avisa.

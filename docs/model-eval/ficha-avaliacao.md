# Ficha de avaliação — candidato a Chibi Master

**[HUMAN REVIEW REQUIRED]** — esta ficha é preenchida por uma pessoa. O agente
não pontua identidade, não escolhe vencedor e não declara que uma arte ficou
boa.

Copie este arquivo para
`experiments/model_eval/<model_key>/avaliacao.md` e preencha após olhar os
outputs.

---

## Identificação

| Campo | Valor |
|---|---|
| Modelo | |
| Revision | |
| Runs avaliados | `run_001`, `run_002` |
| Data | |
| Avaliador | |

## IDENTITY SCORE — HUMAN

Escala sugerida: 0 = ausente · 1 = irreconhecível · 2 = parcial ·
3 = reconhecível · 4 = fiel · 5 = idêntico.

A escala é uma ferramenta de conversa, não uma métrica objetiva. Se um número
não descrever bem o que você viu, escreva a observação — ela vale mais.

| Item | run_001 | run_002 | Observação |
|---|---|---|---|
| HAIR (cabelo preto) | | | |
| FACE | | | |
| EYES (olhos vermelhos) | | | |
| HORNS (chifres) | | | |
| OUTFIT (roupa preta) | | | |
| CAPE (manto longo) | | | |
| ACCESSORIES (ornamentos dourados) | | | |
| SILHOUETTE | | | |
| **OVERALL** | | | |

## Perguntas do critério (seção 12)

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Preserva identidade? | |
| 2 | Gera chibi convincente? | |
| 3 | Pode ser usado comercialmente? | |
| 4 | Executa com custo aceitável? | |
| 5 | Integra bem com a pipeline? | |

> O item 3 é o único que **não** depende do olho: já está resolvido em
> `models.lock.yaml` com verificação em fonte primária.

## Consistência entre as duas execuções

Mesma seed e mesmos parâmetros. Hash diferente é esperado — nunca prometemos
determinismo. O que importa é se a **identidade** se manteve estável.

- [ ] as duas são reconhecivelmente a mesma personagem
- [ ] variação apenas de detalhe
- [ ] variação estrutural relevante (descrever)

Observação: ___

## Conclusão

Marque **uma**:

- [ ] `PROMISING` — vale manter como candidato
- [ ] `INSUFFICIENT` — não atende
- [ ] `BLOCKED` — não foi possível avaliar (motivo: ___)

### Decisão sobre o próximo passo

- [ ] (A) testar também o Qwen-Image-Edit-2511
- [ ] (B) este candidato já basta — dispensar o Qwen por ora
- [ ] (C) ajustar prompt/parâmetros e repetir

> Nada de LoRA, ControlNet, 8 candidatos, `master.png` ou Flow 02 antes desta
> decisão.

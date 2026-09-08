# Ficha de avaliação — candidato a Chibi Master

**[HUMAN REVIEW REQUIRED]** — preenchida por uma pessoa. O agente não pontua
identidade, não pontua estilo, não escolhe vencedor e não declara que uma arte
ficou boa.

Copie para `experiments/model_eval/<model_key>/avaliacao.md` e preencha após
olhar os outputs.

---

## Por que duas notas

Um modelo pode acertar um eixo e errar o outro:

- **estilo bom, identidade ruim** → chibi bonito de *outra* personagem
- **identidade boa, estilo ruim** → a personagem certa, fora da linguagem
  visual do jogo

São falhas diferentes, com soluções diferentes. Uma nota só esconderia isso.
Ver `docs/style-vs-identity.md`.

## Identificação

| Campo | Valor |
|---|---|
| Modelo | |
| Revision | |
| Runs avaliados | `run_001`, `run_002` |
| Style spec | `chibi_v0` |
| Data | |
| Avaliador | |

---

## STYLE SCORE — HUMAN

*O resultado pertence à linguagem visual do jogo?*

Escala: 0 = ausente · 1 = muito fora · 2 = parcial · 3 = aceitável ·
4 = bom · 5 = exatamente o alvo.

A escala é ferramenta de conversa, não métrica objetiva. Se um número não
descrever o que você viu, escreva a observação — ela vale mais.

| Item | run_001 | run_002 | Observação |
|---|---|---|---|
| HEAD PROPORTION (proporção da cabeça) | | | |
| FACIAL STYLE (simplificação facial) | | | |
| EYE TREATMENT (tratamento dos olhos) | | | |
| BODY SIMPLIFICATION | | | |
| RENDERING (lineart, shading, highlights) | | | |
| SILHOUETTE LANGUAGE | | | |
| **STYLE — impressão geral** | | | |

### Game character vs generic chibi

> Parece "personagem deste jogo" ou "chibi anime genérico"?

- [ ] parece pertencer ao mesmo jogo
- [ ] chibi genérico
- [ ] indefinido

Observação: ___

---

## IDENTITY SCORE — HUMAN

*Continua sendo a mesma personagem?*

Escala: 0 = ausente · 1 = irreconhecível · 2 = parcial · 3 = reconhecível ·
4 = fiel · 5 = idêntico.

| Item | run_001 | run_002 | Observação |
|---|---|---|---|
| FACE | | | |
| HAIR (design e cor) | | | |
| EYES (cor) | | | |
| CLOTHING | | | |
| WEAPON (quando visível) | | | |
| ACCESSORIES | | | |
| DISTINCTIVE FEATURES | | | |
| CHARACTER SILHOUETTE | | | |
| **IDENTITY — impressão geral** | | | |

### Preservação da roupa

Simplificada é esperado. **Reinterpretada não é.**

- [ ] cores principais preservadas
- [ ] silhueta preservada
- [ ] peças principais preservadas
- [ ] elementos característicos preservados
- [ ] padrões importantes preservados

### Acessórios core

Marque os que existem na arte-fonte e sobreviveram:

| Acessório (da arte-fonte) | Sobreviveu? |
|---|---|
| | |
| | |

> Quais são "core" depende da arte-fonte da personagem — não presumir por
> categoria.

---

## OVERALL

**Não é média aritmética.** É julgamento humano, e pode divergir das notas
acima com justificativa.

| | Valor |
|---|---|
| OVERALL | |
| Justificativa | |

---

## Consistência entre as duas execuções

Mesma seed e mesmos parâmetros. Hash diferente é esperado — nunca prometemos
determinismo. O que importa é se a identidade se manteve estável.

- [ ] as duas são reconhecivelmente a mesma personagem
- [ ] variação apenas de detalhe
- [ ] variação estrutural relevante (descrever)

Observação: ___

---

## Perguntas do critério

| # | Pergunta | Resposta |
|---|---|---|
| 1 | Preserva identidade? | |
| 2 | Gera chibi convincente? | |
| 3 | Pode ser usado comercialmente? | |
| 4 | Executa com custo aceitável? | |
| 5 | Integra bem com a pipeline? | |

> O item 3 é o único que **não** depende do olho: já está resolvido em
> `models.lock.yaml`, verificado em fonte primária.

## Conclusão

Marque **uma**:

- [ ] `PROMISING` — vale manter como candidato
- [ ] `INSUFFICIENT` — não atende
- [ ] `BLOCKED` — não foi possível avaliar (motivo: ___)

### Próximo passo

- [ ] (A) testar também o Qwen-Image-Edit-2511
- [ ] (B) este candidato já basta — dispensar o Qwen por ora
- [ ] (C) ajustar prompt/parâmetros e repetir

> Nada de LoRA, ControlNet, 8 candidatos, `master.png` ou Flow 02 antes desta
> decisão.

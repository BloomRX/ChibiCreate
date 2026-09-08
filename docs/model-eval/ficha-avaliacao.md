# Ficha de avaliação — candidato a Chibi Master

**[HUMAN REVIEW REQUIRED]** — preenchida por uma pessoa. O agente não pontua
identidade, não pontua estilo, não escolhe vencedor e não declara que uma arte
ficou boa.

Copie para `experiments/model_eval/<model_key>/avaliacao.md` e preencha após
olhar os outputs.

---

## Por que três notas

Um modelo pode acertar um eixo e errar outro:

- **estilo bom, identidade ruim** → chibi bonito de *outra* personagem
- **identidade boa, estilo ruim** → a personagem certa, fora da linguagem
  visual do jogo
- **identidade boa, design ruim** → é ela, mas com outra roupa

O terceiro caso é o mais fácil de deixar passar: a personagem continua
reconhecível, então "parece certo" — mas o design que foi desenhado e aprovado
não sobreviveu. São falhas diferentes, com soluções diferentes. Uma nota só
esconderia isso. Ver `docs/style-vs-identity.md`.

> **Referência de estilo:** `styles/chibi/style.yaml` (`chibi_v0`). Os valores
> ali vieram de análise visual externa e são `provisional_observation`, não
> medidas. Use-os como guia de julgamento, não como régua.

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

### Conformidade com `chibi_v0`

Marque o que o resultado cumpre (referência: `styles/chibi/style.yaml`):

- [ ] cabeça grande (~2,5–3 cabeças de altura — aproximado, não régua)
- [ ] torso curto, membros encurtados
- [ ] mãos e pés pequenos
- [ ] olhos grandes, íris legível
- [ ] rosto simplificado (nariz mínimo, boca pequena)
- [ ] lineart limpo
- [ ] shading suave, highlights contidos
- [ ] pouca textura / densidade de detalhe média
- [ ] legível em escala pequena

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

## DESIGN PRESERVATION SCORE — HUMAN

*O design original sobreviveu à simplificação?*

**Não é a mesma pergunta que identidade.** Aqui não se pergunta "é ela?", e
sim "é o design dela?". Uma personagem reconhecível com a roupa reinterpretada
pontua bem em IDENTITY e mal aqui.

Escala: 0 = redesenhado · 1 = pouco resta · 2 = parcial · 3 = reconhecível ·
4 = bem preservado · 5 = fiel ao design.

| Item | run_001 | run_002 | Observação |
|---|---|---|---|
| Forma principal | | | |
| Cores | | | |
| Cabelo (estrutura) | | | |
| Roupa (peças e cortes) | | | |
| Acessórios principais | | | |
| Silhueta | | | |
| **DESIGN PRESERVATION — geral** | | | |

### Simplificado ou redesenhado?

> **Simplificar é remover detalhe. Redesenhar é trocar o design.**
> A primeira é o objetivo; a segunda é falha.

- [ ] simplificado — detalhe removido, design intacto
- [ ] parcialmente redesenhado (descrever o quê)
- [ ] redesenhado — design diferente

O que foi **removido** (aceitável: microdetalhe, dobras pequenas, textura,
ornamento secundário): ___

O que foi **trocado** (não aceitável): ___

---

## OVERALL

**Não é média aritmética.** É julgamento humano, e pode divergir das notas
acima com justificativa.

| Eixo | Nota |
|---|---|
| STYLE | |
| IDENTITY | |
| DESIGN PRESERVATION | |
| **OVERALL** | |

Justificativa do OVERALL: ___

> Um eixo fraco pode condenar o conjunto mesmo com os outros dois altos —
> por isso não há fórmula. Registre o raciocínio, não só o número.

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

# ADR-004 — Separar status técnico de status comercial de licença

- **Data:** 2026-09-08
- **Status:** aceito
- **Contexto da fase:** GATE 2.1 (entre a Fase 2 e a Fase 3)

---

## Contexto

A verificação de licenças da Fase 2 encontrou um caso ambíguo em
`InstantX/Qwen-Image-ControlNet-Union`:

- os **metadados estruturados** do repositório (endpoint `/api/models`,
  `cardData.license` e a tag `license:apache-2.0`) declaram **Apache-2.0**;
- o **README do mesmo repositório**, na seção *Acknowledgements*, diz
  **"All copyright reserved"**.

O schema v2 do `models.lock.yaml` já separava `license.verified` (documental)
de `weights.verified` (material). Mas essa modelagem tinha só dois desfechos
para a licença: verificada ou não. A ambiguidade não cabia em nenhum dos dois.

Tratá-la como "não verificada" seria factualmente errado — a licença **foi**
lida em fonte primária, com revisão fixada. Tratá-la como "verificada e
liberada" esconderia um risco jurídico real numa flag booleana.

O efeito colateral prático era pior: como `commercially_usable()` era a única
porta, uma ressalva jurídica bloquearia também qualquer **teste técnico** do
modelo — o que atrasa a engenharia por um problema que é do jurídico.

## Decisão

Modelar licença em **dois eixos independentes**, ambos explícitos no
`models.lock.yaml`:

```yaml
license:
  technical_status: verified            # a licença foi lida em fonte primária
  commercial_status: pending_human_review   # approved | pending_human_review | unverified
  commercial_blocker: >
    Descrição do que impede a aprovação comercial.
```

No código (`scripts/chibi/config.py`):

| Função | Pergunta que responde | Efeito da ressalva |
|---|---|---|
| `technically_usable(key)` | Posso experimentar com este modelo? | **não bloqueia** |
| `commercially_usable(key)` | Posso enviar isto para produção? | **bloqueia** |
| `commercial_status(key)` | Qual é o estado exato? | informativo |
| `weights_available(key)` | Os pesos estão baixados e conferidos? | ortogonal |
| `executable(key)` | Dá para rodar agora? | exige licença + pesos |

Regras:

1. `commercial_status` ausente equivale a `approved` — não há penalidade
   retroativa para entradas sem ressalva registrada.
2. `commercial_use: forbidden` bloqueia os **dois** eixos. Licença
   explicitamente não-comercial não se testa "só para experimentar".
3. Uma ressalva **nunca** é resolvida pelo agente. `pending_human_review` só
   vira `approved` por decisão humana registrada.

## Consequências

**Positivas**

- A engenharia não fica bloqueada por pendência jurídica, conforme instrução
  explícita do usuário no GATE 2.1 ("não bloquear testes técnicos por isso").
- O risco fica visível como estado nomeado, não enterrado num comentário.
  `chibi models` imprime as duas linhas separadamente.
- A distinção é auditável e testável.

**Negativas / riscos**

- Mais um eixo de estado para manter em dia. Mitigação: `chibi models` mostra
  tudo, e os testes checam a coerência entre os campos.
- Risco de um modelo `pending_human_review` chegar à produção por descuido. É
  o motivo de `commercially_usable()` continuar sendo a porta única para
  qualquer decisão de produção — e de ela ser **mais** restritiva que antes.

## Situação atual

| Modelo | Técnico | Comercial |
|---|---|---|
| Qwen-Image-ControlNet-Union | verified | **pending_human_review** (ressalva) |
| BiRefNet | verified | approved (MIT) |
| Qwen-Image-Edit-2511 | não lido | unverified |
| RealESRGAN_x4plus_anime_6B | não lido | unverified |

Nenhum peso baixado ⇒ nenhum modelo executável.

## Como resolver a pendência do ControlNet

Opções, para decisão humana:

- **(a)** Pedir esclarecimento ao InstantX Team e registrar a resposta.
- **(b)** Trocar por ControlNet SDXL (ecossistema OpenRAIL++).
- **(c)** Aplicar poses por **rig** em vez de por modelo — caminho que o
  ADR-002 já favorece, o que reduz bastante a criticidade desta decisão.

Enquanto nenhuma for tomada, o campo permanece `pending_human_review`.

# ADR-007 — Pose transfer por IA: experimento autorizado, não reversão do ADR-002

- **Status:** aceito (como **experimento**)
- **Data:** 2026-09-19
- **Relacionado:** ADR-002 (estratégia de animação)

## Contexto

O ADR-002 decidiu **rig cutout** como estratégia primária de animação e
descartou explicitamente a estratégia **(A) frames individuais por IA**, por
drift e flicker. Essa decisão continua de pé.

O usuário pediu uma rota em que um **sprite sheet de mannequin** (renderizado
no Blender a partir do Mixamo) forneça a pose e a personagem chibi seja
"substituída" nela. Essa é, na prática, a estratégia (A).

Duas circunstâncias justificam testar mesmo assim:

1. **O ambiente de execução é o Colab, não a máquina local.** O rig cutout
   (rota B) roda na RX 580 sem GPU NVIDIA, e o usuário decidiu conduzi-lo em
   **outra sessão, separada**, para não misturar as duas linhas de raciocínio.
   Esta sessão fica com a rota que depende de GPU.
2. **O ADR-002 não proíbe (A) em absoluto.** Ele diz, textualmente:
   *"Nenhuma das duas é proibida em absoluto — (E) e (B) permanecem
   disponíveis para poses-chave e conteúdo fora de gameplay."* Pose-guided é
   a estratégia (E), e é exatamente o que um mannequin habilita.

## Decisão

Autorizar **uma linha experimental separada** de pose transfer por IA, com as
mesmas salvaguardas usadas na fase de inpaint:

1. Notebook próprio, `notebooks/pose_transfer_eval.ipynb`. **Não alterar**
   `chibi_from_concept.ipynb`, `flux2_klein_4b_eval.ipynb` nem
   `wai_illustrious_sdxl_eval.ipynb`.
2. Workflow próprio, versionado em
   `workflows/experimental/pose_transfer/`.
3. **Não substitui o ADR-002.** O rig cutout segue sendo a estratégia
   primária. Este ADR não promove (A) a rota de produção.
4. A promoção de (A) a produção exigiria um ADR novo, sustentado por
   **avaliação visual humana do loop em escala real de jogo** — não por
   métrica isolada e não por frames vistos individualmente.

## Critério de avaliação

O modo de falha previsto pelo ADR-002 é **flicker entre frames**, e ele é
invisível quadro a quadro. Portanto:

- a avaliação obrigatória é o **loop animado**, não a grade de frames;
- nas escalas reais de exibição, `config/project.yaml → legibility_test.sizes`
  (64, 96, 128 px), não a 1024 px;
- a decisão é **humana**. O agente não declara sucesso.

Métricas de consistência inter-frame, se houver, são **diagnóstico** —
respondem "quanto mudou entre frames", não "ficou bom". Mesma regra da fase de
inpaint: métrica boa ≠ resultado bom.

## Risco geométrico registrado

O mannequin do Mixamo é bípede realista (~7 cabeças). Chibi tem ~2–3. Se o
frame de pose chegar em proporção humana, o resultado tende a ser personagem
alongada ou cabeça grande em corpo adulto. A mitigação escolhida é **corrigir
a proporção no Blender antes do render** — decisão artística humana,
documentada em `styles/chibi/pose_bank/mannequin/README.md`.

O experimento **não** compensa proporção automaticamente: fazer isso
esconderia a causa da falha.

## Licença

Mixamo permite uso comercial e proíbe (a) redistribuir arquivos brutos e
(b) usar o conteúdo para treinar modelos de ML. O repo versiona **apenas PNG
renderizado** e **não treina nada**. Registrado em
`styles/chibi/pose_bank/mannequin/mannequin.metadata.json`.

## Consequências

- **Positiva:** decide (A) com evidência real em vez de argumento, e produz um
  resultado negativo limpo se falhar — como o TESTE 1 do inpaint.
- **Positiva:** o mannequin renderizado serve às **duas** rotas. Se (A)
  falhar, os sheets continuam úteis como referência de pose para o rig cutout
  da rota B. O trabalho no Blender não se perde em nenhum cenário.
- **Negativa:** consome GPU e atenção humana numa rota já avaliada como
  arriscada.

## Pendências

- [ ] `[HUMAN REVIEW REQUIRED]` Avaliar o loop de walk a 64/96/128 px.
- [ ] `[TEST REQUIRED]` Confirmar se a proporção corrigida no Blender elimina
      o alongamento.

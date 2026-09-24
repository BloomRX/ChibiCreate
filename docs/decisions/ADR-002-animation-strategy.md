# ADR-002 — Estratégia de animação: rig cutout, não geração de frames por IA

- **Status:** aceito
- **Data:** 2026-09-08
- **Contexto:** MVP v0.1, gameplay estilo Vampire Survivors

## Contexto

O jogo precisa de `idle` e `walk` inicialmente, com `attack`, `hurt`, `death`,
`skills`, `victory` e expressões no futuro. Sprites aparecem em **centenas de
instâncias simultâneas**, em ~64–96 px de altura.

Havia cinco estratégias em disputa: (A) frames individuais por IA, (B) vídeo IA
→ frames, (C) animação por partes/cutout, (D) skeletal 2D, (E) pose-guided.

## Decisão

Para **gameplay**:

1. **Rig cutout** a partir do Chibi Master aprovado — estratégia primária.
2. **Skeletal 2D** onde houver necessidade real de deformação.
3. **IA para gerar poses-chave** quando o rig não der conta.
4. **IA de vídeo apenas fora do gameplay** (cinematics, gacha).

Bake final para **spritesheet**, sempre.

## Razões

1. **Consistência é absoluta, não estatística.** No cutout, os pixels do braço
   são literalmente os pixels do braço do Master aprovado. Não há amostragem,
   logo não há drift nem flicker. Nenhuma quantidade de tuning em geração
   frame-a-frame alcança essa garantia.
2. **Escala de exibição favorece poucos frames.** A 64 px, 4–6 frames são
   suficientes e frequentemente *melhores* (mais legíveis, mais "game-y").
3. **Flicker é catastrófico nessa escala.** Ruído imperceptível a 1024 px vira
   cintilação agressiva a 64 px multiplicada por 200 instâncias.
4. **Custo.** Gerar 81 frames de vídeo para aproveitar 6 é desperdício de duas
   ordens de grandeza.
5. **Escala de produção.** Um rig genérico compartilhado (mesma decomposição,
   mesmo canvas, mesma A-pose) permite aplicar **a mesma animação a N
   personagens** sem trabalho adicional. É o mecanismo central de escala.
6. **Facilidade de alteração.** Ajustar um walk = mexer numa curva. Com frames
   IA = regerar e recurar tudo.

## Alternativas descartadas

| Estratégia | Motivo |
|---|---|
| (A) Frames individuais por IA | Drift e flicker inevitáveis; custo alto de correção |
| (B) Vídeo IA → frames | Saída ~24 fps / 480p / **sem alpha**; extrair 6 frames limpos é caro e ruim |

Nenhuma das duas é proibida em absoluto — (E) e (B) permanecem disponíveis para
poses-chave e conteúdo fora de gameplay, respectivamente.

## Consequências

- **Positiva:** consistência garantida por construção; custo de GPU quase zero
  na etapa de animação; alterações baratas.
- **Negativa:** exige trabalho de rig por personagem (mitigado pelo rig
  compartilhado) e limita deformações complexas.
- **Negativa:** o Chibi Master precisa ser gerado em pose e canvas
  **rigorosamente padronizados**, senão o recorte automático quebra. Isso vira
  um requisito duro do FLOW 02.

## Pendências

- [ ] `[TEST REQUIRED]` Validar que a decomposição padrão de 10 partes cobre a
      personagem difícil do MVP.
- [ ] `[TEST REQUIRED]` **Não presumir que Skeleton2D é lento.** Medir no
      benchmark de 200/500/1000 instâncias antes de concluir qualquer coisa
      sobre custo de bones.
- [ ] `[TEST REQUIRED]` Confirmar que 4 frames de idle e 6 de walk bastam
      visualmente na escala real de jogo.

## Revisão

Reavaliar se: o benchmark mostrar que spritesheets pré-bakeados não são
necessários, ou se surgir modelo de vídeo com saída nativa em alpha, alta
consistência e resolução adequada para sprites.

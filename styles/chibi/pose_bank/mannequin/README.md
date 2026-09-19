# Mannequin — sheets de pose renderizados no Blender

Fonte de **pose por frame**, global e compartilhada por todas as personagens
(spec §8). Um mannequin é renderizado **uma vez** e serve para N personagens.

## Onde colocar

```
styles/chibi/pose_bank/mannequin/
├── walk/
│   ├── walk_00.png … walk_05.png     # frames individuais (preferido)
│   └── walk_sheet.png                # sheet montado (opcional)
├── idle/                              # idle_00 … idle_03
└── mannequin.metadata.json            # procedência e licença
```

Um diretório por animação. Nomes seguem a convenção do pose bank:
`<anim>_<index:02d>.png`. A contagem de frames vem de
`config/project.yaml → animation`, hoje idle=4 / walk=6.

## Git

PNG **não** está em LFS neste repo (a regra está comentada em
`.gitattributes`), então estes arquivos entram como blobs normais. Isso é
adequado: render de mannequin sem textura é quase flat color e comprime muito.

Manter cada frame **abaixo de ~300 KB**. Se um sheet passar de alguns MB,
avisar antes de commitar — aí a conversa é sobre LFS, não sobre o arquivo.

## Requisitos de cada frame

Herdados de `styles/chibi/pose_bank/README.md`, mais os específicos de render:

| Requisito | Porquê |
|---|---|
| Mesmo canvas em todos os frames | O bake do sheet assume grade regular |
| **Pivot fixo** (mesma posição do chão/pés em todo frame) | Senão o sprite "pula" no loop |
| Fundo **transparente** ou chroma sólido uniforme | Fundo variável vira ruído de condicionamento |
| Câmera **ortográfica**, imóvel entre frames | Perspectiva muda a silhueta e quebra a consistência |
| Sem textura, sem sombra projetada, sem DOF | O mannequin informa pose, não estilo |
| Iluminação chapada e idêntica entre frames | Variação de luz vira flicker no resultado |
| **Proporção chibi** (ver abaixo) | O ponto mais importante |

## Proporção — ler antes de renderizar

O mannequin do Mixamo é bípede realista, ~7–7,5 cabeças de altura. Um chibi
tem ~2–3. Se o frame de pose chegar com proporção humana, o modelo é puxado
para ela: sai personagem alongada, ou cabeça chibi colada em corpo adulto.

**Recomendação: corrigir a proporção no Blender, antes do render.** É barato
lá e elimina o maior modo de falha da rota A. Na prática, no rig do Mixamo:

- escalar o osso `Head` (e o canvas de render) até a cabeça ocupar ~1/3 da
  altura total;
- encurtar `UpperArm`/`Forearm` e `UpperLeg`/`Shin` — chibi é **stubby**, de
  membro curto, não é humano em miniatura;
- manter o **arco e o timing** da caminhada do Mixamo: é isso que se está
  aproveitando, e é a parte difícil de acertar à mão.

Um walk chibi também costuma ter passada mais curta e menos rotação de tronco
que o walk humano. Ajustar isso é decisão artística humana, não do agente.

## Licença — Mixamo

Verificado em 2026-09-19 na FAQ oficial da Adobe:

- uso **comercial livre**, royalty-free, sem exigência de atribuição;
- **proibido redistribuir os arquivos brutos** de personagem/animação (FBX,
  rig, keyframes) como produto ou asset avulso;
- **proibido usar o conteúdo para treinar modelos de machine learning.**

Consequências para este repo:

1. **Não commitar FBX, .blend com o rig do Mixamo, nem dados de keyframe.**
   Só PNG renderizado, que é obra derivada dentro do projeto.
2. O mannequin serve como **condicionamento em inferência**, nunca como
   dataset de treino. O MVP não treina nada (`style.lora.enabled: false`),
   então isso já está coberto — mas fica registrado.

Registrar a procedência em `mannequin.metadata.json` a cada sheet adicionado.

## [HUMAN REVIEW REQUIRED]

A proporção e o timing do mannequin são decisão artística. O agente não
ajusta nem julga — só verifica canvas, pivot, contagem de frames e alfa.

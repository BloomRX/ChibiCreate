# Pose Bank — GLOBAL

Este banco de poses é **compartilhado por todas as personagens** (spec §8).

Uma pose é criada **uma vez** e reutilizada por N personagens. Nunca criar uma
versão manual de cada pose para cada personagem — é isso que faz o pipeline
escalar de 5 para 100.

## Estado atual

**Vazio.** Populado na FASE 5.

## Convenção de nomes

```
<anim>_<index:02d>.png      idle_00.png, walk_03.png, attack_00.png
```

## Alvo do MVP

| Animação | Frames | Arquivos |
|---|---|---|
| idle | 4 | `idle_00` … `idle_03` |
| walk | 6 | `walk_00` … `walk_05` |

Contagens vêm de `config/project.yaml → animation.defaults` e são configuráveis.

## Requisitos de cada pose

- Mesmo canvas e mesma escala do Chibi Master (`styles/chibi/style.yaml → master_canvas`)
- Pivot na mesma posição em todos os frames de uma animação
- Formato: esqueleto OpenPose, lineart ou silhueta — a definir na FASE 5
  conforme o que o modelo de controle aceitar

## Nota sobre a estratégia

O pose bank serve a **duas** rotas, e isso é deliberado:

1. **Rota primária (rig cutout):** as poses guiam o posicionamento manual das
   partes recortadas do Master. Preserva 100% do artwork aprovado.
2. **Rota secundária (pose-guided IA):** as mesmas poses alimentam ControlNet
   quando for preciso gerar uma pose-chave que o rig não consegue fazer bem
   (ex.: rotação de 3/4, mudança de expressão).

O mesmo banco alimenta as duas — não duplicar.

# pose_transfer — EXPERIMENTAL (ADR-007)

Rota (A) do ADR-002: gerar cada frame por IA, guiado por um frame de
mannequin. **Não é a estratégia de produção** — o rig cutout continua sendo.

## v1.json

Derivado de `flux2_klein_edit/v2.json`, que encadeia `ReferenceLatent`.

| Placeholder | Papel |
|---|---|
| `%%INPUT_IMAGE%%` | frame do mannequin — **a pose** |
| `%%INPUT_IMAGE_2%%` | chibi master — **a identidade** |
| `%%INPUT_IMAGE_3%%` | referência extra opcional (face/outfit) |

A ordem da cadeia importa: nós `7 → 15 → 18` empilham os latentes de
referência sobre o condicionamento, e o primeiro é a pose.

## Limitação conhecida

FLUX.2 klein via `ReferenceLatent` **não é um ControlNet**. Ele é
*influenciado* pela pose, não *travado* nela. Aderência frouxa é resultado
esperado, não bug — registrar e reportar, não compensar em silêncio.

Se a aderência for insuficiente, o passo seguinte é ControlNet/OpenPose de
verdade — o que exige modelo próprio, e **não** deve ser adicionado sem
decisão humana e entrada em `models.lock.yaml`.

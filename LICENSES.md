# LICENÇAS — registro de conformidade

**Projeto comercial.** Nenhum modelo, LoRA, dataset ou serviço entra na pipeline sem uma entrada verificada aqui e em [`config/models.lock.yaml`](config/models.lock.yaml).

**Última revisão:** 2026-09-08
**Status geral:** ⚠️ nenhum modelo foi baixado ou verificado ainda. Todos estão como `candidate`.

---

## Aviso jurídico importante

A licença dos **pesos** de um modelo **não resolve automaticamente**:

1. **Proveniência do dataset de treino** — a maioria dos modelos abertos não divulga o dataset. Licença Apache 2.0 nos pesos não elimina risco de terceiros sobre o *conteúdo* gerado.
2. **Status dos outputs** — varia por jurisdição e ainda está em disputa em vários países.
3. **Termos de serviços hospedados** — usar um modelo via API (RunPod, fal, Replicate) adiciona os termos *daquele serviço* por cima da licença do modelo.
4. **Similaridade substancial** — gerar algo reconhecivelmente derivado de obra protegida continua sendo problema, independente da licença do modelo.

Este arquivo é uma ferramenta de **engenharia e rastreabilidade**, não um parecer jurídico. Antes do lançamento comercial, revisão por advogado.

---

## Modelos aprovados para uso comercial

Nenhum ainda. Um modelo só passa a `verified` depois de: pesos baixados, hash calculado, licença lida no card/repo oficial, e `verified_on` preenchido.

---

## Candidatos (pesquisados, não verificados)

| Modelo | Papel | Licença declarada | Comercial | Verificado |
|---|---|---|---|---|
| Qwen-Image-Edit-2511 | edição / identidade | Apache-2.0 | ✅ declarado | ❌ pendente |
| Qwen-Image-ControlNet-Union (InstantX) | controle de pose | **desconhecida** | ⚠️ **não confirmado** | ❌ pendente |
| BiRefNet | remoção de fundo | MIT (código e pesos) | ✅ declarado | ❌ pendente |
| RealESRGAN_x4plus_anime_6B | upscale | BSD-3-Clause | ✅ declarado | ❌ pendente |

> ⚠️ **`Qwen-Image-ControlNet-Union` é o ponto fraco atual.** A pesquisa não confirmou a licença. Precisa ser lida no card oficial antes de virar dependência. Se não houver licença clara, alternativas: ControlNet SDXL (ecossistema OpenRAIL++) ou pose bank aplicado por rig em vez de por modelo.

---

## Rejeitados para dependência comercial

| Modelo | Motivo | Alternativa adotada |
|---|---|---|
| **BRIA RMBG-2.0** | Pesos CC BY-NC 4.0; produção exige contrato pago ou API | BiRefNet (MIT) |
| **FLUX.1 [dev] / FLUX.2 [dev] / FLUX.2 [klein] 9B** | Licença não-comercial da Black Forest Labs | Qwen-Image-Edit-2511 |
| **NoobAI-XL / Pony** | Model card adiciona proibição explícita de comercialização | Qwen-Image-Edit-2511 |
| **SeedVR2** | Licença restringe uso comercial | Real-ESRGAN |

---

## Sinalizados — decisão jurídica pendente

### Illustrious-XL (família FAIPL)

**Conflito:** a licença afirma que *"o output não é coberto por esta licença"*, mas o material oficial também declara que o modelo *"proíbe monetização proprietária closed-source"*. Interpretações da comunidade divergem publicamente e a OnomaAI reconheceu ambiguidade, migrando a redistribuição para CreativeML Open RAIL.

**Decisão atual:** `pending_legal`.
**Uso permitido enquanto isso:** prototipagem e exploração de estilo apenas. **Não** em assets que entram no build.

---

## Software da pipeline

| Componente | Licença | Nota |
|---|---|---|
| ComfyUI | GPL-3.0 | Usado como **executor externo**, não linkado ao jogo. Não contamina o código do jogo. |
| diffusion-pipe (treino de LoRA, fase futura) | GPL-3.0 | Idem: ferramenta externa. |
| Godot Engine | MIT | |
| Python / Pillow / numpy / PyYAML | PSF / MIT-CMU / BSD / MIT | |
| Este repositório | a definir | ⚠️ escolher antes de tornar público |

---

## Procedimento para adicionar um modelo

1. Ler a licença **no card/repo oficial** — não em blog ou agregador.
2. Adicionar entrada em `config/models.lock.yaml` com `status: candidate`.
3. Baixar os pesos manualmente (a pipeline **não** baixa automaticamente).
4. Calcular sha256 e registrar em `sha256` e `files`.
5. Preencher `license.spdx`, `license.commercial_use`, `license.source_url`, `license.verified_on`.
6. Mudar `status` para `verified`.
7. Registrar aqui na tabela de aprovados.
8. `chibi models` deve mostrar o modelo como liberado.

Enquanto um modelo não estiver `verified`, `chibi models` o reporta como **não liberado para produção comercial** — e isso é intencional.

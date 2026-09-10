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

## Dois níveis de verificação

`config/models.lock.yaml` (schema v2) separa duas coisas que costumam ser confundidas:

- **`license.technical_status`** — a licença foi lida em **fonte primária** (arquivo `LICENSE` do repositório oficial ou endpoint `/api/models/<id>` do Hugging Face), com `source_url`, `verified_on` e `revision` fixada registrados. É uma verificação *documental*.
- **`weights.verified`** — o arquivo de pesos foi **baixado** e o `sha256` conferido. É uma verificação *material*.

Um modelo só é **executável** quando os dois são verdadeiros. Hoje **nenhum peso foi baixado** — o agente não baixa checkpoints (ver `AGENTS.md`). Portanto nenhum modelo é executável, mesmo os de licença já verificada.

### Terceiro eixo: uso técnico × uso comercial (ADR-004)

Ler a licença não é o mesmo que aprová-la para produção. Quando a fonte
primária é ambígua, o estado fica explícito:

| Campo | Valores | Bloqueia o quê |
|---|---|---|
| `technical_status` | `verified` / ausente | experimentação técnica |
| `commercial_status` | `approved` · `pending_human_review` · `unverified` | uso em produção |

Uma ressalva jurídica pendente **não bloqueia teste técnico** — a engenharia
não fica parada esperando o jurídico. Mas `commercially_usable()` continua
recusando, e é ela a porta única para qualquer decisão de produção.

`commercial_use: forbidden` bloqueia os **dois** eixos: licença
explicitamente não-comercial não se testa "só para experimentar".

Só um humano muda `pending_human_review` para `approved`.

Consulte o estado atual com `chibi models`.

---

## Licenças verificadas em fonte primária

| Modelo | Papel | Licença | Uso comercial | Fonte consultada | Revisão fixada |
|---|---|---|---|---|---|
| Qwen-Image-ControlNet-Union (InstantX) | controle de pose | **Apache-2.0** | ⚠️ **pending_human_review** | [`/api/models/…`](https://huggingface.co/api/models/InstantX/Qwen-Image-ControlNet-Union) (`license` + `cardData.license`) | `b13036f066d6dee7c20513e263d3d673055e9de8` |
| BiRefNet | remoção de fundo | **MIT** | ✅ approved | [`LICENSE` no GitHub oficial](https://github.com/ZhengPeng7/BiRefNet/blob/main/LICENSE) + `cardData.license` no HF | `e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4` |

### ✅ FLUX.2 [klein] 4B — Apache-2.0 (verificado 2026-09-08)

**Candidato experimental** para Chibi Master, adicionado na FASE 3B
(MODEL EVALUATION).

| Campo | Valor |
|---|---|
| Repositório | `black-forest-labs/FLUX.2-klein-4B` |
| Revision | `e7b7dc27f91deacad38e78976d1f2b499d76a294` |
| Licença | Apache-2.0 |
| Verificado em | 2026-09-08 |
| Fonte primária | `LICENSE.md` do repositório + model card |

Duas fontes primárias conferidas: o `LICENSE.md` contém o texto integral da
Apache License 2.0, e o card afirma *"Open weights available for commercial
use under the Apache 2.0 license"*.

> #### ⚠️ 4B é comercial. 9B NÃO é.
>
> A própria Black Forest Labs escreve no card: *"the release of the open-weight
> FLUX.2 [klein] 4B models under an Apache 2.0 license and the release of the
> FLUX.2 [klein] 9B models under a **non-commercial** license"*.
>
> **Somente a variante 4B pode ser usada neste projeto.** Baixar "FLUX.2 klein"
> sem conferir o tamanho é um erro de conformidade, não de configuração.

O card lista restrições de uso (conteúdo ilegal, CSAM, NCII, assédio,
desinformação) e declara explicitamente que nada nele restringe ou modifica a
licença. São limites de conduta, não restrição comercial.

Arquivos para ComfyUI vêm de `Comfy-Org/vae-text-encorder-for-flux-klein-4b`
(rev `5f526678`, Apache-2.0) — redistribuição oficial, com SHA256 registrados
em `models.lock.yaml`.

> **Atenção ao nome:** usar `flux-2-klein-4b.safetensors` (destilado), não
> `flux-2-klein-base-4b.safetensors`. Mesmo tamanho, modelos diferentes.

---

### ⚠️ Ressalva registrada — ControlNet Union

O README do mesmo repositório traz, na seção *Acknowledgements*, a frase **"All copyright reserved"**, que aparenta conflitar com a tag `apache-2.0` declarada nos metadados estruturados e no `cardData`.

**Posição adotada:** para fins de *registro documental* prevalece a licença declarada formalmente nos metadados do repositório (Apache-2.0), que é o campo com significado jurídico no Hugging Face. Mas o **uso comercial fica em `pending_human_review`** (ADR-004): teste técnico liberado, produção bloqueada até decisão humana. A ressalva é impressa por `chibi models`.

**[HUMAN REVIEW REQUIRED]** Antes de uso comercial em produção, um humano deve decidir se essa ambiguidade é aceitável ou se convém: (a) pedir esclarecimento ao mantenedor, ou (b) trocar por ControlNet SDXL (ecossistema OpenRAIL++), ou (c) aplicar poses por rig em vez de por modelo (o que o ADR-002 já favorece).

> Lição de método: ler apenas o corpo do model card **não basta**. Neste caso o corpo do card e os metadados divergiam. Sempre conferir o endpoint `/api/models/<id>` e, quando existir, o arquivo `LICENSE` do repositório de código.

---

## Licenças ainda não verificadas

| Modelo | Papel | Licença declarada | Situação |
|---|---|---|---|
| Qwen-Image-Edit-2511 | edição / identidade | Apache-2.0 | `[TEST REQUIRED]` — declarada em fontes secundárias; falta leitura em fonte primária |
| RealESRGAN_x4plus_anime_6B | upscale | BSD-3-Clause | `[TEST REQUIRED]` — idem |

Estes dois são recusados por `config.commercially_usable()` até que a verificação seja feita e registrada.

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

### WAI-illustrious-SDXL v17.0 (candidato 3 da FASE 3B)

**Tipo:** checkpoint SDXL completo (não LoRA, não adapter). Autor: WAI0731.
**Fonte:** `https://civitai.red/models/827184/wai-illustrious-sdxl`
**Licença indicada:** Fair AI Public License 1.0-SD, herdada do Illustrious-XL.
**Verificada em fonte primária:** ❌ não — Civitai e HuggingFace estão fora da
allowlist de rede desta sandbox. A licença foi corroborada por model cards
espelho (`John6666/wai-nsfw-illustrious-*`, que declaram `license_name:
faipl-1.0-sd`), **não** lida na página oficial.

Os quatro eixos, deliberadamente **separados** — a diretiva proíbe tratá-los
como uma coisa só:

| Eixo | Situação |
|---|---|
| Uso do checkpoint | Permitido |
| Uso dos **outputs** | ⚠️ `pending_human_review` |
| Redistribuição do checkpoint | Restrito (share-alike FAIPL) |
| Derivados (merge, LoRA) | Restrito (herdam FAIPL) |

**Sobre o output — o ponto que não pode ser distorcido:** a FAIPL-1.0-SD tem
cláusula de *Output* em que o licenciante não reivindica direitos sobre o que
foi gerado. Existe, em paralelo, interpretação pública de que a licença
proíbe "monetização proprietária closed-source". **Não afirmamos que o uso
comercial do output é proibido** — afirmamos que é ambíguo. Como este projeto
é um jogo closed-source, a decisão é jurídica e humana.

**Decisão atual:** `commercial_status: pending_human_review`.
**Status do arquivo:** `MODEL_MISSING` — os pesos não foram obtidos.

**Observação factual, não julgamento:** o checkpoint nasceu como
"WAI-NSFW-illustrious-SDXL" e tem foco declarado em conteúdo adulto. Não
adicionamos tags NSFW a nenhum prompt; registramos porque afeta comportamento
do modelo e adequação ao projeto.

---

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

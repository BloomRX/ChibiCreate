# ADR-003 — ComfyUI como executor, Git como fonte da verdade

- **Status:** aceito
- **Data:** 2026-09-08
- **Contexto:** MVP v0.1

## Contexto

A pipeline precisa de workflows reprodutíveis, versionáveis, automatizáveis,
integráveis a scripts, capazes de processar em lote e de rodar em GPU cloud.
Candidatos: ComfyUI, Forge, AUTOMATIC1111, InvokeAI, SwarmUI, Diffusers puro.

## Decisão

**ComfyUI é o executor de inferência. Ele NÃO é a fonte da verdade do projeto.**

A fonte da verdade é o repositório Git:

```
config/            parâmetros e models.lock
workflows/         templates versionados com placeholders
*.recipe.json      o que foi usado para produzir cada artefato aprovado
characters/        assets canônicos aprovados
```

O workflow JSON enviado ao ComfyUI é um **artefato gerado** a partir de um
template + parâmetros. A CLI Python é a camada de orquestração.

## Razões

1. **Workflow como arquivo diffável.** ComfyUI serializa o grafo completo em
   JSON — versionável e revisável em PR. A1111/Forge guardam apenas metadados
   parciais em PNG.
2. **API HTTP nativa** e caminho direto para serverless, viabilizando execução
   em GPU cloud sem GUI.
3. **Batch e parameter sweep** de primeira classe, necessários para gerar
   N candidatos com seeds controladas.
4. **A1111 está em declínio**; Forge é bom para iteração manual mas não entrega
   grafo reprodutível; InvokeAI é superior para canvas/inpaint por artista e
   fica como ferramenta **complementar** de retoque, não como orquestrador.

## A parte não óbvia: por que não deixar o ComfyUI ser o projeto

Tentação comum é deixar workflows e histórico do ComfyUI virarem o registro do
projeto. Recusado porque:

- O histórico do ComfyUI não é versionado, não é revisável e não sobrevive a
  reinstalação.
- Amarra o projeto a uma ferramenta específica indefinidamente.
- Não registra **aprovação humana**, que é informação de projeto, não de
  ferramenta.

Com a lógica em Python e as receitas em Git, trocar o backend por Diffusers
puro é escrever um adaptador — não reescrever o projeto.

## Consequências

- **Positiva:** reprodutibilidade auditável; automação natural; lock-in contido.
- **Positiva:** licença GPL-3.0 do ComfyUI é irrelevante para o jogo, pois ele é
  processo externo, não código linkado.
- **Negativa:** camada extra de indireção (template + preenchimento) em vez de
  usar a GUI direto. Custo aceito conscientemente.
- **Negativa:** exige disciplina — um workflow editado à mão na GUI e não
  salvo no repo quebra a rastreabilidade.

## Sobre determinismo

A recipe permite **reconstrução aproximada**, não bit-exatidão. Versões de
biblioteca, kernels de GPU e não-determinismo de atenção podem variar o
resultado. Isso está documentado no módulo `recipe.py` e **não deve ser
prometido como determinismo absoluto**.

## Pendências

- [ ] `[TEST REQUIRED]` Definir provedor de GPU cloud e medir custo real por
      personagem.
- [ ] `[TEST REQUIRED]` Confirmar formato de export de workflow (API vs
      completo) que melhor serve ao preenchimento de placeholders.

## Revisão

Reavaliar se: o overhead de templates se mostrar maior que o benefício em
escala pequena, ou se um orquestrador melhor surgir com as mesmas garantias de
versionamento.

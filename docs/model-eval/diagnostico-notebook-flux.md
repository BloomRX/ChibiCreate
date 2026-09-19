# Diagnóstico: o que aconteceu com `flux2_klein_4b_eval.ipynb`

Data: 2026-09-09 · Investigação por histórico Git

---

## Resposta curta

**O notebook nunca foi perdido.** Não foi excluído, não foi sobrescrito e não
foi substituído. Ele estava em `docs/colab/flux2_klein_4b_eval.ipynb` desde o
commit em que nasceu, e continuou lá o tempo todo, íntegro e com as células da
Run 003 intactas.

O que houve foi **um problema de localização, não de perda**: um notebook
permanente estava guardado dentro de uma pasta de *documentação*, ao lado de
`EXECUTAR.md` e `README.md`, enquanto os outros notebooks do projeto moravam em
`notebooks/`. Quem procurasse em `notebooks/` não o encontrava.

Restaurado em: **`notebooks/flux2_klein_4b_eval.ipynb`**.

---

## As sete hipóteses, verificadas uma a uma

| | Hipótese | Veredito | Evidência |
|---|---|---|---|
| A | movido | **NÃO** (até hoje) | um único caminho em todo o histórico |
| B | renomeado | **NÃO** | `git log --follow` não mostra rename |
| C | em outro diretório | **SIM** | `docs/colab/`, não `notebooks/` |
| D | sobrescrito | **NÃO** | só 2 commits tocaram o arquivo; o 2º **acrescentou** conteúdo |
| E | excluído | **NÃO** | `git log --diff-filter=D -- '*.ipynb'` retorna vazio |
| F | substituído | **NÃO** | os 4 notebooks de `notebooks/` foram todos **criados** (`A`), nenhum sobre este |
| G | existe em outro commit/branch | **SIM, e no HEAD** | presente e íntegro na ponta do branch |

### Comandos usados

```
git log --all --oneline --name-status -- '*flux2_klein*'
git log --all --follow --oneline --name-status -- docs/colab/flux2_klein_4b_eval.ipynb
git log --all --oneline --diff-filter=A --name-status -- 'notebooks/*'
git log --all --diff-filter=D --name-status --oneline -- '*.ipynb'
```

### Histórico completo do arquivo — só dois commits

```
a9fe21f  A  docs/colab/flux2_klein_4b_eval.ipynb   (criação)
3ddb849  M  docs/colab/flux2_klein_4b_eval.ipynb   (+76 linhas, −1)
```

O commit `3ddb849` **adicionou** a seção RUN 003 (multi-referência, workflow
`v2`, validação da cadeia de 3 referências). Não removeu nada relevante: a
única linha deletada foi o fechamento do JSON, consequência natural de
acrescentar células no fim.

### Por que os outros notebooks não o substituíram

```
4c116bc  A  notebooks/model_eval_flux_to_qwen.ipynb
f85912a  A  notebooks/model_eval_model_only.ipynb
f85912a  A  notebooks/model_eval_flux_refiner.ipynb
506d7f5  A  notebooks/design_transfer_eval.ipynb
```

Todos com status `A` (added). Nenhum é uma renomeação deste, nenhum escreveu
por cima dele.

---

## Comparação com a cópia do usuário

A cópia fornecida fora do repositório foi comparada contra a versão do repo.
**Zero divergências.** Todos os valores críticos conferem:

| item | valor | confere |
|---|---|---|
| modelo | `flux-2-klein-4b.safetensors` (destilado, Apache-2.0) | sim |
| revision | `5f526678002e43af5551dadb73ce2e8c91b43afe` | sim |
| seed | 42 | sim |
| VRAM mínima / pesos | 13.0 GB / 7.75 GB | sim |
| sha256 dos 3 pesos | diffusion, text encoder, VAE | sim |
| sha256 da arte-fonte | `2fdcd5f4…cb8177` | sim |
| prompt | "Transform this character into a clean stylized chibi full-body…" | sim |
| Run 003 | `--workflow-version v2` + `--ref face.png` + `--ref outfit.png` | sim |

**Não houve substituição silenciosa.** O arquivo restaurado é byte a byte o
mesmo que já estava versionado — `git mv` preservou o conteúdo
(`sha256 bc3fce5d88d6c9e5bb9ee51d27b906224d63197f9a31e481e389af2c2add0af9`
antes e depois do move; o hash mudou só depois, ao adicionar o cabeçalho de
BENCHMARK e a parametrização, ambos descritos abaixo).

---

## Configuração que produziu a Run 003

Registrada no cabeçalho do próprio notebook, para não depender deste documento:

| campo | valor |
|---|---|
| modelo | FLUX.2 [klein] **4B** — Apache-2.0 (a **9B é não-comercial** e nunca foi usada) |
| repo dos pesos | `Comfy-Org/vae-text-encorder-for-flux-klein-4b` |
| revision | `5f526678002e43af5551dadb73ce2e8c91b43afe` |
| workflow | `experimental/flux2_klein_edit` — **v2** |
| seed | **42** |
| referências | **3**: `full_body.png` + `face.png` + `outfit.png` |
| prompt | "Transform this character into a clean stylized chibi full-body character, preserving the same identity, black hair, red eyes, horns, black outfit, long black cape and golden ornaments." |
| cfg / steps | `cfg = 1.0`, **4 passos** (modelo destilado) — em `config/environments/colab_flux2.yaml` |
| personagem | `waifu_001` |

**A única variável entre Run 001/002 e Run 003 é o número de referências.**
Modelo, prompt, seed, cfg, steps, sampler e resolução são idênticos; o `v2`
difere do `v1` apenas por encadear mais dois `ReferenceLatent`.

---

## Mudanças feitas na restauração

Três, todas conservadoras:

1. **`git mv` para `notebooks/`** — conteúdo inalterado, histórico preservado
   (Git registra como `R`, rename).

2. **Cabeçalho BASELINE / BENCHMARK FLUX** — célula markdown nova no topo,
   declarando que o notebook é permanente, que gerou as Run 001/002/003, que
   não deve voltar para pasta de experimento e que os outros notebooks o
   **referenciam** em vez de substituí-lo.

3. **Personagem parametrizada** — nova célula 0 com
   `CHARACTER_ID = "waifu_001"`. As três células de execução passaram de
   `--character waifu_001` para `--character $CHARACTER_ID`.

   **Impacto no resultado: nenhum.** O default continua `waifu_001` e nenhum
   parâmetro de geração foi tocado. O hash esperado da arte-fonte virou um
   dicionário `EXPECTED_SOURCE_SHA` indexado por personagem — o sha da
   `waifu_001` **não** virou regra global; personagem nova entra sem hash e o
   notebook apenas avisa.

Agora o fluxo pretendido funciona sem editar célula de execução:

```
Waifu B  ->  CHARACTER_ID = "waifu_002"  ->  FLUX  ->  run 001/002/003
```

### Proteção contra repetição

`tests/test_flux_benchmark_notebook.py` — 19 testes, sem GPU. Travam: o
caminho permanente, a ausência de cópia duplicada em `docs/colab/`, a marca de
BASELINE, as **três** execuções, a configuração da Run 003 (seed, revision,
workflow v2, as 3 referências), os hashes dos pesos, o aviso de licença da 9B,
a parametrização da personagem e o default `waifu_001`.

---

## Bônus: as 6 falhas de `test_comfy.py` — resolvidas

Estavam pendentes de investigação. **Causa raiz: poluição entre testes, não
defeito de produto.**

`tests/test_model_adapter.py` substituía o atributo global
`experiment.ComfyClient` por um `FakeClient` no momento do import e **nunca
restaurava**. Rodando sozinho, `test_comfy.py` passa nos 89 testes; rodando
depois do adapter, 6 quebram, porque o `FakeClient` afirma
`assert name == "colab_comfy_gguf"` e derruba qualquer teste que use outro
ambiente (ex.: `"cloud"`).

Correção: guardar o original e devolvê-lo no fim do módulo.

**Suíte: 382 passed, 0 failed.** Nada foi silenciado ou marcado como skip.

---

## Estado da correspondência REAL ↔ CHIBI

Continua **parada no ponto correto**, aguardando a Run 003 real.

- Fluxo de upload com **validação de SHA256** implementado (célula 2):
  `artifact_sha256` (bytes) e `pixel_sha256` (conteúdo RGBA) registrados
  separadamente; `full_body.png` é conferido contra o hash conhecido e a
  execução **para** se divergir.
- `.gitignore` **não** foi alterado. `experiments/**/*.png` continua ignorado.
- Métricas novas: `correspondence points`, `rejected points`, `transform type`,
  `residual` (rmse/max/por landmark), `confidence`, `mask_area_source`,
  `mask_area_target`, `clipping_pixels`, `out_of_bounds_pct`.
- **Ressalva importante sobre o residual:** o TPS **interpola** os landmarks
  exatamente, então seu residual é ~0 por construção. Residual zero em TPS não
  significa correspondência boa — significa que a spline passou pelos pontos
  fornecidos. Quem valida o TPS é o olho, no overlay. Para afim e similaridade
  o número é informativo.
- Landmarks do target **não foram fabricados**: o bloco `target` de
  `landmarks.yaml` segue vazio de propósito.

**Não houve warp nem composição.** A Run 003 não foi alterada nem regerada.

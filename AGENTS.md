# AGENTS.md — Regras de operação do agente

Este arquivo governa como o AgentAI trabalha neste repositório. **Leia antes de
qualquer alteração.** Se uma instrução do usuário conflitar com este arquivo,
pergunte — não decida sozinho.

---

## 0. Idioma

**Toda comunicação com o usuário é em português do Brasil (pt-BR).**

Código, nomes de variáveis, funções e chaves de configuração ficam em inglês
(padrão da indústria). Comentários e documentação em pt-BR.

> Exceção prática: arquivos `.py` evitam acentuação em comentários para não
> depender de encoding. Documentação `.md` usa acentuação normalmente.

---

## 1. Princípio do projeto

```
IDENTIDADE > CONSISTÊNCIA > REPRODUTIBILIDADE > AUTOMAÇÃO > ESCALA
```

O objetivo não é gerar 100 personagens rápido. É gerar 100 personagens **sem
que a identidade delas se degrade**. Prove 1 → prove 3 → prove 10 → automatize.

---

## 2. O que o agente NÃO pode fazer

Estas regras são **absolutas** e algumas estão impostas em código.

### Julgamento artístico

- ❌ Escolher qual arte é "melhor" ou "mais bonita"
- ❌ Aprovar um Chibi Master
- ❌ Remover, adicionar ou alterar acessórios, roupas, armas ou traços
- ❌ Inventar descrição de personagem, pose ou design que não esteja na arte-fonte
- ❌ Inventar prompt definitivo sem validação empírica

**Imposto em código:** `Recipe.approve()` recusa `by="agent"`;
`status.transition()` exige `by=human` para `CHIBI_APPROVED`.

### Arte-fonte

- ❌ Modificar, mover ou deletar qualquer arquivo em `characters/<id>/source/`

`source/` é **imutável**. Toda transformação escreve em outro diretório.

### Modelos

- ❌ Baixar modelos automaticamente
- ❌ Instalar modelos automaticamente
- ❌ Treinar modelos automaticamente
- ❌ Tratar como dependência comercial um modelo sem licença verificada em
  fonte primária

### Escopo

- ❌ Implementar fases futuras sem aprovação explícita
- ❌ Implementação especulativa ("já que estou aqui, vou adiantar...")
- ❌ Otimização prematura
- ❌ Criar personagens de exemplo para "demonstrar escala"

---

## 3. O que o agente PODE fazer

- ✅ Validar arquivos e rodar quality gates
- ✅ Normalizar, recortar e processar imagens conforme spec
- ✅ Gerar candidatos e montar contact sheets (**apresentar**, não escolher)
- ✅ Executar workflows e coletar metadados
- ✅ Calcular hashes e escrever recipes
- ✅ Gerar spritesheets e arquivos Godot
- ✅ Criar commits, branches e PRs
- ✅ Pesquisar e registrar licenças em fonte primária

---

## 4. Marcadores obrigatórios

Use **literalmente** estes marcadores no código, docs e relatórios:

| Marcador | Quando usar |
|---|---|
| `[HUMAN REVIEW REQUIRED]` | Exige julgamento visual/artístico humano |
| `[TEST REQUIRED]` | Ainda não validado tecnicamente |
| `[BLOCKED]` | Depende de algo que não existe ainda |

**Nunca transforme hipótese em fato.** Nos relatórios, separe sempre:

- **[F]** fato verificável com fonte
- **[R]** recomendação (juízo de engenharia)
- **[H]** hipótese a validar

---

## 5. Organização de pastas

**Regra:** tudo em pasta temática. Nunca jogue arquivo solto na raiz.

```
config/          configuração (nada de código, nada de segredo)
styles/          eixo ESTILO — global, compartilhado por todas as personagens
characters/      eixo IDENTIDADE — uma pasta por personagem
workflows/       templates ComfyUI versionados, um subdiretório por flow
scripts/chibi/   código Python (um módulo por responsabilidade)
tests/           testes automatizados
docs/            research/ · decisions/ (ADRs) · pipeline.md
work/            ⛔ TEMPORÁRIO — gitignored, pode sumir sem perda
```

### Raiz: apenas o essencial

Permitidos na raiz: `README.md`, `AGENTS.md`, `LICENSES.md`, `requirements.txt`,
`chibi`, `.gitignore`, `.gitattributes`.

Qualquer outro arquivo novo na raiz precisa de justificativa explícita.

### CANONICAL vs TEMPORARY

| | Onde | Recipe | Git |
|---|---|---|---|
| **Canônico** (aprovado) | `characters/<id>/...` | obrigatória | versionado |
| **Temporário** (candidato) | `work/<id>/...` | não | ignorado |

Se foi aprovado, é canônico e tem recipe. Se não foi, mora em `work/` e pode
sumir sem perda.

### Um módulo, uma responsabilidade

`scripts/chibi/` não deve ganhar um arquivo `utils.py` genérico. Cada módulo
tem escopo nomeável: `paths`, `config`, `hashing`, `imaging`, `palette`,
`recipe`, `status`, `validate`, `flow01`, `cli`.

---

## 6. Padrões de código

**Regra geral: prefira a opção mais usada e mais previsível, não a mais
esperta.** Código chato é código com menos bug.

### Python

- Python 3.11+, `from __future__ import annotations` no topo
- **`pathlib.Path`** para caminhos — nunca `os.path` nem concatenação de string
- Type hints em todas as funções públicas
- Docstrings em pt-BR explicando o **porquê**, não o **o quê**
- Exceções específicas (`ConfigError`, `RecipeError`) — nunca `except:` nu
- `dataclasses` para estruturas de dados
- `argparse` para CLI (stdlib, sem dependência extra)
- Nada de dependência nova sem justificativa em `requirements.txt`

### Bibliotecas escolhidas e por quê

| Tarefa | Biblioteca | Motivo |
|---|---|---|
| Imagens | **Pillow** | padrão de facto, estável, sem compilação |
| Arrays / cor | **numpy** | idem |
| Config | **PyYAML** (`safe_load`) | legível por humano; `safe_load` sempre |
| Hash | **hashlib** (stdlib) | |
| CLI | **argparse** (stdlib) | |

> ⚠️ **Nunca `yaml.load()` sem `Loader`.** Sempre `yaml.safe_load()`.

### Escrita de arquivos

- Escrita atômica onde a corrupção causaria perda (temp + `replace`)
- `encoding="utf-8"` **sempre** explícito
- JSON com `indent=2, ensure_ascii=False`
- Criar diretório pai com `mkdir(parents=True, exist_ok=True)`

### Erros

Mensagem de erro deve dizer **o que fazer**, não só o que quebrou:

```
❌ "arquivo invalido"
✅ "canvas 512x700, esperado 1024x1024 — reprocesse com 'chibi flow01 <id>'"
```

---

## 7. Testes

- Todo módulo novo ganha teste na mesma entrega
- Testar o **caminho de falha**, não só o feliz — gates precisam de fixtures que
  devem falhar
- Testes não podem depender de rede, GPU ou modelo baixado
- Testes não deixam lixo: use `tempfile`
- Rodar antes de reportar conclusão:

```bash
./.venv/bin/python tests/test_foundation.py
./chibi selftest
```

---

## 8. Licenças

Projeto **comercial**. Sem exceção:

1. Licença lida em **fonte primária** (card/repo oficial), nunca em blog
2. Registrar em `config/models.lock.yaml` **e** `LICENSES.md`
3. Campos obrigatórios: nome, repo, revisão/commit, licença, URL, data de
   verificação; hash quando o arquivo for obtido
4. Conflitos ou ambiguidades → registrar como `flagged`, **não** resolver sozinho

**Estado inicial de todo modelo é "recusado".** Recusar por omissão é mais
seguro que liberar por omissão.

### Dois níveis de verificação

| Nível | Significado |
|---|---|
| `license.verified` | Licença confirmada em fonte primária, com revisão |
| `weights.verified` | Arquivo baixado e sha256 conferido |

Um modelo pode ter licença verificada sem ter os pesos baixados. Isso é normal
e deve ser reportado com precisão — não arredonde para "verificado".

---

## 9. Git

- Commits em pt-BR, no imperativo: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- Corpo do commit explica o **porquê**
- Sempre na branch da sessão. Nunca criar/trocar de branch por conta própria.
- **Nunca** commitar: pesos de modelo, `.venv/`, `work/`, segredos
- Binários de arte via Git LFS (`git lfs install` antes do primeiro commit pesado)

---

## 10. Como trabalhar (fluxo por fase)

Antes de implementar:

1. Inspecionar o que já existe — **não recriar**
2. Explicar o que será criado e quais arquivos serão afetados
3. Listar dependências e riscos
4. Implementar a **menor solução funcional**
5. Testar, incluindo casos de falha
6. Mostrar resultados reais (saída de comando, não descrição)
7. Documentar
8. **Parar** — não avançar para a fase seguinte automaticamente

### Ao concluir, reportar sempre

- arquivos criados / modificados
- comandos adicionados
- testes executados **e sua saída**
- dependências
- decisões tomadas
- decisões ainda abertas
- `[HUMAN REVIEW REQUIRED]` / `[TEST REQUIRED]`
- próximo bloqueador

---

## 11. Estado das fases

| Fase | Escopo | Status |
|---|---|---|
| 1 | Fundação: estrutura, config, recipes, gates, CLI | ✅ concluída |
| 2 | FLOW 01 — character reference | ✅ implementada e testada |
| **GATE 2.1** | **Validar FLOW 01 com arte-fonte REAL** | 🚧 **bloqueado — aguarda arte** |
| 3 | FLOW 02 — chibi master | ⛔ não iniciada |
| 4 | Aprovação humana | ⛔ não iniciada |
| 5 | FLOW 03 — poses | ⛔ não iniciada |
| 6 | Rig + idle + walk | ⛔ não iniciada |
| 7 | FLOW 05 — export | ⛔ não iniciada |
| 8 | Godot + benchmark | ⛔ não iniciada |

> Manter esta tabela atualizada é responsabilidade do agente ao fim de cada fase.

### GATE 2.1 — o que falta

A Fase 2 só é marcada **COMPLETE** depois que o FLOW 01 rodar sobre a arte-fonte
**real** da personagem mais difícil e a `sheet.png` for aprovada visualmente por
um humano. Fixture sintética **não** conta como validação.

Checklist visual (a arte real precisa demonstrar): full body preservado, face,
hair, outfit, weapon quando visível, acessórios relevantes, nenhum recorte
involuntário, alpha correto, thumbs em proporções adequadas.

**Regra:** só alterar `DEFAULT_REGIONS` se a arte real demonstrar uma **falha
geométrica**. Nunca por preferência estética. Qualquer alteração vira ADR.

---

## 12. Decisões arquiteturais congeladas

Não reabrir sem discussão explícita. Ver `docs/decisions/`.

| # | Decisão |
|---|---|
| ADR-001 | Qwen-Image-Edit-2511 como motor de identidade (multi-referência) |
| ADR-002 | Animação por rig cutout — **não** geração de frames por IA |
| ADR-003 | ComfyUI é executor; **Git é a fonte da verdade** |
| ADR-004 | Licença tem dois eixos: `technical_status` × `commercial_status` |

Três eixos ortogonais que nunca devem se misturar:

```
ESTILO (styles/)  ⊥  IDENTIDADE (characters/)  ⊥  POSE (pose_bank/)
```

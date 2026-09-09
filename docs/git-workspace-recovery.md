# Regressão do workspace para `65b4bb7` — diagnóstico e recuperação

> Investigado em 2026-09-08 após a **quarta** ocorrência.
> Conclusão: **não é bug do Git nem automação destrutiva.** É o ambiente
> efêmero sendo reprovisionado. **Nenhum dado foi perdido em nenhuma das
> quatro vezes.**

## A evidência decisiva

O reflog do repositório tem exatamente duas linhas:

```
65b4bb7 HEAD@{2026-09-09 01:39:46}: checkout: moving from main to arena/01a07ece-chibicreate
65b4bb7 HEAD@{2026-09-09 01:39:46}: clone: from https://github.com/BloomRX/ChibiCreate.git
```

Isso encerra a questão. Se algum processo tivesse rodado `git reset`,
`git checkout`, `git restore` ou `git clean` sobre o repositório, **haveria
registro no reflog** — é justamente o que ele existe para gravar. Não há.

O que há é um `clone` recente. Confirmado pelos timestamps:

```
.git            criado   01:39:45
.git/config     criado   01:39:46
.git/HEAD       criado   01:39:46
```

O `.git` inteiro nasceu segundos antes do turno. Não é o mesmo `.git` de
antes — é um clone novo de um repositório que, no default branch, ainda
aponta para `65b4bb7`.

Corroborando: os commits do trabalho **não existem no objectstore local**.

```
b54ee3a  AUSENTE      c620287  AUSENTE
e85ccf6  AUSENTE      054c7cf  AUSENTE
in-pack: 3 objetos    (um clone recém-feito e mínimo)
```

Um `reset` teria mantido os objetos e o reflog. A ausência de ambos só é
compatível com **repositório recriado do zero**.

## As sete perguntas

| # | Pergunta | Resposta baseada em evidência |
|---|---|---|
| 1 | O que causa o reset? | Nada. Não há reset — o `.git` é recriado. |
| 2 | Mecanismo externo restaurando? | Sim: reprovisionamento da sandbox. |
| 3 | Ambiente efêmero? | **Sim — esta é a causa.** |
| 4 | Problema de branch/worktree? | Não. Branch correta, worktree única. |
| 5 | Arquivos não commitados se perdem? | **Não** nas 4 ocorrências (ver abaixo). |
| 6 | `.venv` some junto? | **Sim** — é ignorado, não vem no clone. |
| 7 | Automação rodando reset/clean? | **Não.** Reflog limpo prova. |

## Por que nada foi perdido

O working tree **não** volta ao estado inicial junto com o `.git`. Os arquivos
continuam em disco; só o histórico é que é novo. Verificação do turno:

```
arquivos no commit remoto b54ee3a : 103
idênticos em disco                : 103
ausentes                          : 0
diferentes                        : 0
```

Por isso o `git status` mostra dezenas de `??` (untracked): do ponto de vista
do clone novo, esses arquivos nunca foram commitados — mas o **conteúdo** está
intacto, byte a byte.

O risco real seria commitar/pushar por cima sem perceber. Daí o procedimento
abaixo.

## Recuperação (testada 4 vezes)

```bash
git fetch origin arena/01a07ece-chibicreate
git reset <sha-do-ultimo-commit>     # MISTO. Nunca --hard, nunca --soft
python3 -m venv .venv && ./.venv/bin/pip install -q pyyaml pillow numpy
```

- `--hard` apagaria trabalho não commitado em disco.
- `--soft` deixaria tudo staged, escondendo divergências reais.
- O reset **misto** reconcilia o índice mantendo o disco — que é onde o
  trabalho está.

Descobrir o sha correto: `git ls-remote origin` (o remoto é a fonte da
verdade) ou `git log --oneline -3 FETCH_HEAD`.

## Proteção mínima recomendada

Deliberadamente **não** reestruturamos o Git. Só o necessário:

1. **Sempre pushar ao fim do turno.** É o que tornou as 4 recuperações
   triviais. O remoto é o único estado durável.
2. **Verificar antes de commitar** após qualquer turno que comece estranho:
   `git log --oneline -1` — se disser `65b4bb7 Initial commit`, houve
   reprovisionamento: recupere **antes** de trabalhar.
3. **Nunca `git reset --hard`** neste repositório.
4. **Registrar o upstream** quando útil:
   `git branch --set-upstream-to=origin/arena/01a07ece-chibicreate`
   (some no reprovisionamento; é conveniência, não proteção).
5. **Conferir hashes dos assets críticos** após recuperar — sobretudo
   `characters/waifu_001/reference/full_body.png`
   (`2fdcd5f428f5980d63e31d4bf4a67aecbc11c1b101c19ca75f819db616cb8177`).

## O que NÃO fazer

- Não "consertar" com outro reset antes de entender o estado.
- Não `git clean` — apagaria os untracked, que aqui são o trabalho real.
- Não recriar branch nem mudar de branch: a sessão está atada a
  `arena/01a07ece-chibicreate`.

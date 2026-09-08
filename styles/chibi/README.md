# styles/chibi — o eixo ESTILO

Este diretório define **como** as personagens são desenhadas em versão chibi.
Ele é ortogonal ao eixo **identidade** (`characters/<id>/`).

```
styles/
└── chibi/
    ├── references/
    │   ├── chibi/      exemplos do RESULTADO visual desejado
    │   └── splash/     exemplos da ARTE ORIGINAL e da relação splash → chibi
    ├── pose_bank/
    ├── style.yaml
    └── README.md
```

## Regra de separação — não misturar os dois eixos

> **Nunca colocar arte das nossas personagens em `styles/`.**
>
> As nossas personagens vivem **exclusivamente** em:
> - `characters/<id>/source/` — arte-fonte original, nunca modificada
> - `characters/<id>/reference/` — derivados gerados pelo Flow 01
>
> `styles/chibi/references/` guarda **exemplos de terceiros**, usados para
> descrever a linguagem visual alvo. São material de referência de estilo, não
> assets do jogo.

Confundir os dois contamina a avaliação: se uma arte nossa entra na pasta de
estilo, deixa de ficar claro se um resultado veio da identidade da personagem
ou do exemplo de estilo.

## `references/chibi/`

Exemplos do **resultado** que queremos alcançar: personagens já em versão
chibi, no tipo de acabamento que o projeto busca.

Servem para responder: *como deve ser o produto final?*

## `references/splash/`

Exemplos da **arte original** e, quando existir, do par splash → chibi da
mesma personagem.

O par é o material mais valioso: mostra **o que foi preservado e o que foi
simplificado** na transição — que é exatamente a decisão que a nossa pipeline
precisa tomar.

## STYLE vs IDENTITY

| STYLE (global, este diretório) | IDENTITY (por personagem) |
|---|---|
| proporções | design do cabelo |
| rendering / shading | cor do cabelo |
| simplificação facial | cor dos olhos |
| linguagem chibi | design da roupa |
| tratamento visual geral | armas |
| | acessórios |
| | traços distintivos |
| | silhueta específica |

**STYLE é global** — muda para todas as personagens ao mesmo tempo.
**IDENTITY é por personagem** — muda uma personagem só.

Essa separação é o que permite que 5, 20 ou 100 personagens pareçam pertencer
ao mesmo jogo. Detalhes em `docs/style-vs-identity.md`.

## ⚠️ Referências recebidas, mas ainda não analisadas

**12 arquivos** versionados no commit `3f138a5`: 6 em `references/chibi/` e
6 em `references/splash/`. Inventário com sha256 e tamanho em
`references/references.metadata.json`.

**O agente não conseguiu abrir nenhum deles.** Estão em Git LFS; `git-lfs` não
está instalado no ambiente e o CDN (`github-cloud.githubusercontent.com`) está
bloqueado por egress. Caminhos testados:

| Caminho | Resultado |
|---|---|
| LFS batch API | URLs assinadas obtidas — download falha no TLS |
| tarball via `codeload` | acessível, mas devolve ponteiros |
| `github.com/.../raw/...` | bloqueado |
| API contents (`Accept: raw`) | devolve ponteiro |

Por isso `style.yaml` tem `references.analyzed: false` e os 28 campos
observacionais seguem `null`. **Listar não é analisar** — descrever proporção
ou shading sem ter visto a imagem seria inventar.

**Para destravar:** `git lfs pull` numa máquina com acesso, ou anexar as
imagens diretamente na conversa.

## Estado

`style.yaml` está em **v0, experimental**. Campos sem evidência visual
permanecem `null` com `[TEST REQUIRED]`.

> Enquanto `references/` estiver vazio, **nenhum valor de estilo pode ser
> preenchido**. Inventar proporção ou tratamento de shading sem referência
> seria criar conteúdo artístico — o que o agente não pode fazer.

## Regras

- Não modificar as imagens originais de referência.
- Se precisar anotar, criar cópia; manter o original intacto.
- Nomes descritivos + metadata (`.metadata.json` ao lado, quando útil).
- Registrar origem de cada referência. Imagem de terceiros é material de
  estudo interno; **não** entra em arte publicada.
- Style LoRA continua desabilitado (`style.lora.enabled: false`).

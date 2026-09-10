# Amostras de personagem para avaliação

Três personagens, escolhidas para cobrir dificuldades **diferentes**. Não é
demonstração de escala — é cobertura de casos difíceis.

| ID | Papel | Estado na pipeline |
|---|---|---|
| `waifu_001` | personagem difícil / complexa | ativa — Flow 01 executado, GATE 2.1 |
| `waifu_002` | pose / oclusão / contexto complexo | **arte-fonte registrada**, fora da pipeline |
| `waifu_003` | controle simples | **arte-fonte registrada**, fora da pipeline |

## Estado atual

Só a `waifu_001` está na pipeline. As outras duas têm a arte-fonte
versionada, mas **não** foram processadas: nenhum `character.yaml`, nenhum
Flow 01, nenhuma entrada em `STATUS.md`.

Isso é intencional. Registrar a arte é barato e evita perdê-la; processá-la
antes da Style Specification estar aprovada seria trabalho especulativo.

```
characters/
├── waifu_001/          personagem ativa do MVP
│   ├── source/         arte-fonte, nunca modificada
│   ├── reference/      derivados do Flow 01
│   └── ...
├── waifu_002/
│   └── source/waifu_002.png    registrada, não processada
└── waifu_003/
    └── source/waifu_003.png    registrada, não processada
```

## Por que três dificuldades diferentes

| Personagem | O que ela testa |
|---|---|
| `waifu_001` | densidade de detalhe — muitos acessórios, ornamentos, manto |
| `waifu_002` | geometria — pose, oclusão, contexto que confunde recorte e proporção |
| `waifu_003` | o caso simples — se falhar aqui, o problema é do pipeline, não da arte |

A `waifu_003` é o **controle**. Sem ela, uma falha é ambígua: arte difícil
demais ou pipeline ruim? Com ela, a resposta fica clara.

## Regras

- **Não modificar arte-fonte.** `source/` é imutável.
- **Não processar 002 e 003** antes da aprovação da Style Specification v0.
- Não criar personagens novas para demonstrar escala.
- Ao ativar uma delas: `chibi character new` → `flow01` → validação humana,
  a mesma sequência da `waifu_001`.

## Nota técnica — Git LFS

As artes de `waifu_002` e `waifu_003` estão versionadas via **Git LFS**
(conforme `.gitattributes`). No ambiente do agente elas aparecem como
ponteiros de texto: `git-lfs` não está instalado e o CDN
(`github-cloud.githubusercontent.com`) está bloqueado por egress — medido, não
presumido.

Consequência prática: **o agente não consegue ver estas imagens.** Qualquer
análise visual delas depende de uma máquina com `git lfs pull`.

Os ponteiros registram tamanho e sha256, então a integridade está garantida:

| Arquivo | sha256 (LFS oid) | Tamanho |
|---|---|---|
| `waifu_002/source/waifu_002.png` | `e6ea0dcc…1ba38b8` | 1 293 855 B |
| `waifu_003/source/waifu_003.png` | `51d70cf8…b49a72a4` | 362 562 B |

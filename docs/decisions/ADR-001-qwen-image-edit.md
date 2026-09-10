# ADR-001 — Qwen-Image-Edit-2511 como motor de identidade

- **Status:** aceito (candidato — não verificado)
- **Data:** 2026-09-08
- **Contexto:** MVP v0.1

## Contexto

O pipeline precisa transformar splash art de alta resolução em uma versão chibi
que preserve rosto, cabelo, olhos, roupa, acessórios, arma, silhueta e paleta.
O projeto é **comercial**, o que torna a licença um critério eliminatório, não
um detalhe.

## Decisão

Usar **Qwen-Image-Edit-2511** como primeiro candidato para transformação de
identidade, operando em **modo de edição multi-referência** (1 a 3 imagens),
não em modo texto-para-imagem.

## Razões

1. **Licença Apache 2.0** nos pesos — sem taxa, sem cláusula não-comercial.
2. **Multi-referência nativa** (até 3 imagens) — permite alimentar `full_body`
   + `face` + `weapon` separadamente, que é exatamente a decomposição de
   identidade que o projeto precisa.
3. **Foco declarado em consistência de personagem** e redução de drift entre
   edições, em relação à versão 2509.
4. Ecossistema maduro em ComfyUI, com quantizações GGUF que viabilizam
   execução em GPUs de 12–16 GB na nuvem.

## Alternativas descartadas

| Alternativa | Motivo |
|---|---|
| FLUX.1/2 [dev], klein 9B | Licença não-comercial — eliminatório |
| NoobAI-XL / Pony | Proibição explícita de comercialização no card |
| Illustrious-XL | Cláusula FAIPL ambígua sobre monetização closed-source → `pending_legal` |
| FLUX.2 [klein] 4B | Apache 2.0 e rápido, mas menor fidelidade de identidade. **Mantido como plano B.** |
| SDXL + IP-Adapter | Ecossistema mais maduro, mas identidade menos fiel que um modelo de edição instrucional. Plano C. |

## Consequências

- **Positiva:** licença limpa, arquitetura de referência alinhada ao problema.
- **Negativa:** modelo de 20B. Não roda na RX 580. Cria dependência de GPU
  cloud com ≥24 GB (FP8 ~20.5 GB). Ver ADR-003.
- **Risco aceito:** o modelo **não** é garantia de identidade perfeita. A
  pipeline assume que drift acontece e prevê gates de verificação (paleta) e
  inpaint dirigido como Nível 2 da escada de consistência.

## Pendências

- [ ] `[TEST REQUIRED]` Baixar, calcular hash, ler licença no card oficial,
      marcar `verified` em `config/models.lock.yaml`.
- [ ] `[TEST REQUIRED]` Validar empiricamente se 1, 2 ou 3 referências dão o
      melhor resultado. **Não assumir que 3 é sempre melhor.**
- [ ] `[TEST REQUIRED]` Determinar se Style LoRA é necessária (só após MVP).

## Revisão

Reavaliar se: a personagem difícil do MVP falhar no Nível 0+2 da escada de
consistência, ou se surgir modelo de edição aberto com fidelidade
comprovadamente superior e licença compatível.

# workflows/05_export

Templates de workflow ComfyUI para este flow. **Vazio na Fase 1.**

## Regras

- Um template é um JSON de workflow com **placeholders** `{{nome}}`, nunca com
  caminhos ou parâmetros hardcoded que possam ser configurados.
- Versionar como `v1.json`, `v2.json`... Nunca editar um template já usado por
  uma recipe aprovada — crie a próxima versão.
- O `workflow_sha256` registrado na recipe aponta para o arquivo exato usado.
- Exportar do ComfyUI em formato **API** para execução programática, e manter o
  export completo ao lado quando útil para inspeção humana.

## Placeholders convencionados

| Placeholder | Significado |
|---|---|
| `{{seed}}` | seed do sampler |
| `{{steps}}`, `{{cfg}}`, `{{sampler}}` | parâmetros de amostragem |
| `{{width}}`, `{{height}}` | dimensões de saída |
| `{{prompt}}`, `{{negative_prompt}}` | texto |
| `{{input_0}}`, `{{input_1}}`, `{{input_2}}` | imagens de referência (1 a 3) |
| `{{model}}`, `{{lora}}` | resolvidos via config/models.lock.yaml |

# FASE 3B — runbook para executar na sua máquina

Sequência exata a rodar onde houver acesso à GPU. **Cole o output aqui** que
eu analiso os recipes, comparo as execuções e escrevo o relatório final.

Se algo falhar, **pare e me mande o erro** — não force o passo seguinte.

---

## 0. Preparar o repositório

```bash
git clone -b arena/01a07ece-chibicreate https://github.com/BloomRX/ChibiCreate.git
cd ChibiCreate
git log --oneline -1        # deve mostrar 9a89ab3 (ou mais recente)

python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Confira que a arte e a referência vieram junto:

```bash
sha256sum characters/waifu_001/reference/full_body.png
# esperado: 2fdcd5f428f5980d63e31d4bf4a67aecbc11c1b101c19ca75f819db616cb8177
```

Se o `reference/` estiver vazio, regenere (é determinístico):

```bash
./chibi flow01 waifu_001 --force
```

## 1. Subir o ComfyUI com o Qwen

Numa máquina com **≥24 GB de VRAM** e ~60 GB livres. Os três arquivos:

| Pasta do ComfyUI | Arquivo |
|---|---|
| `models/unet/` (ou `diffusion_models/`) | `qwen_image_edit_2511_fp8_e4m3fn.safetensors` |
| `models/clip/` (ou `text_encoders/`) | `qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| `models/vae/` | `qwen_image_vae.safetensors` |

Repositório oficial: `Qwen/Qwen-Image-Edit-2511`, revisão
`6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9`, Apache-2.0. **Só este modelo.**

Suba com `--listen 0.0.0.0` se for acessar de outra máquina.

> Se os nomes dos arquivos forem diferentes, **não edite código**: ajuste
> `comfyui.models` em `config/environments/cloud.yaml`.

## 2. Apontar a CLI

```bash
export CHIBI_COMFY_URL=http://<host>:8188
# export CHIBI_COMFY_TOKEN=<token>    # só se o seu backend exigir
```

Não coloque isso em arquivo versionado. Se a URL tiver credencial embutida,
tudo bem — ela é redigida antes de ir para log ou recipe.

---

## FASE A — preflight (não usa GPU)

```bash
./chibi comfy status    --env cloud
./chibi comfy preflight --env cloud
./chibi comfy validate  --env cloud
```

**Ponto de parada.** Só siga se o preflight disser `PRONTO para uma execução
real`. Se aparecer `WORKFLOW_INCOMPATIBLE`, ele imprime `node/expected/actual`
— me mande essas linhas, é o dado que preciso para corrigir o workflow com
evidência.

`UNKNOWN` (ex.: servidor sem `/models`) **não** bloqueia.

## FASE B — primeira execução real

```bash
./chibi experiment qwen-edit \
  --character waifu_001 \
  --input reference/full_body.png \
  --seed 42 \
  --env cloud \
  --prompt "Transform this character into a clean stylized chibi full-body character, preserving the same identity, black hair, red eyes, horns, black outfit, long black cape and golden ornaments."
```

Uma vez só.

## FASE C — validar tecnicamente

```bash
ls -la experiments/qwen_image_edit_2511/run_001/
sha256sum experiments/qwen_image_edit_2511/run_001/*.png
python3 -c "from PIL import Image; im=Image.open('experiments/qwen_image_edit_2511/run_001/output.png'); print(im.size, im.mode)"
cat experiments/qwen_image_edit_2511/run_001/recipe.json
```

## FASE E — segunda execução (mesma configuração)

Só depois que a primeira estiver validada.

```bash
./chibi experiment qwen-edit \
  --character waifu_001 \
  --input reference/full_body.png \
  --seed 42 \
  --env cloud \
  --prompt "Transform this character into a clean stylized chibi full-body character, preserving the same identity, black hair, red eyes, horns, black outfit, long black cape and golden ornaments."

./chibi experiment compare \
  experiments/qwen_image_edit_2511/run_001 \
  experiments/qwen_image_edit_2511/run_002
```

SHA256 diferente entre as duas é **aceitável** — registramos a diferença, não
prometemos determinismo.

## PARAR

Depois da segunda execução, pare. Nada de 8 candidatos, `master.png`,
aprovação, LoRA, ControlNet, animação ou Flow 03.

---

## O que me mandar

1. Output completo das FASES A, B, C e E (pode colar o texto).
2. Os dois `recipe.json`.
3. As duas `output.png` — commite e faça push, ou anexe aqui:
   ```bash
   git add experiments/ -f && git commit -m "FASE 3B: execucoes reais" && git push
   ```
   (`experiments/**/*.png` está no `.gitignore`; o `-f` é intencional para
   estas duas provas.)

Com isso eu escrevo o relatório A–U e a inspeção de identidade da FASE D.

## Se algo der errado

| Sintoma | Provável causa |
|---|---|
| `ENDPOINT_UNREACHABLE` | ComfyUI sem `--listen 0.0.0.0`, ou firewall |
| `MODEL_MISSING` | nomes diferentes → ajuste `comfyui.models` no `cloud.yaml` |
| `WORKFLOW_INCOMPATIBLE` | me mande `node/expected/actual` |
| `CUDA out of memory` | VRAM insuficiente para fp8 — me diga a GPU |
| Timeout na 1ª execução | normal carregar 20B na primeira vez; aumente `timeout_seconds` no `cloud.yaml` |

"""Cliente HTTP do ComfyUI.  [FASE 3]

Ainda nao implementado. Contrato pretendido, para referencia:

    client = ComfyClient.from_environment("cloud")
    job = client.submit(workflow_template, params, inputs)
    result = client.wait(job, timeout=...)   # -> paths dos outputs

Responsabilidades planejadas:
  - carregar template de workflows/<flow>/*.json e preencher placeholders
  - enviar via POST /prompt, acompanhar via /history
  - baixar outputs para work/<character>/
  - devolver metadata suficiente para montar a Recipe

Nao implementar antes de existir um backend real configurado em
config/environments/cloud.yaml (variaveis CHIBI_COMFY_URL / CHIBI_COMFY_TOKEN).
"""

from __future__ import annotations


class ComfyClientNotConfigured(RuntimeError):
    pass


class ComfyClient:  # pragma: no cover - stub de fase futura
    def __init__(self, *_args, **_kwargs) -> None:
        raise ComfyClientNotConfigured(
            "ComfyClient e da FASE 3. Configure um backend ComfyUI antes."
        )

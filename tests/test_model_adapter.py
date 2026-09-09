"""Teste ponta a ponta do adapter da matriz contra um ComfyUI falso.

Nao substitui execucao real em GPU: valida que o GRAFO submetido, os
parametros e o recipe sao os que o registry declara.
"""
import sys, json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from chibi import model_registry as mr, experiment, comfy_client

SUBMETIDO = {}

class FakeJob:
    prompt_id = "p1"
class FakeOut:
    filename = "x.png"

class FakeClient:
    @classmethod
    def from_environment(cls, name):
        assert name == "colab_comfy_gguf", name
        return cls()
    def server_info(self):
        return {"reachable": True, "comfyui_version": "abc123",
                "pytorch_version": "2.11.0", "os": "Linux",
                "devices": [{"name": "Tesla T4", "vram_free": 14_000_000_000,
                             "vram_total": 15_000_000_000}]}
    def upload_image(self, p): return "up_" + pathlib.Path(p).name
    def submit(self, wf):
        SUBMETIDO.update(wf); return FakeJob()
    def wait(self, job): return [FakeOut()]
    def download(self, out, dest):
        from PIL import Image
        Image.new("RGBA", (64, 64), (10, 20, 30, 255)).save(dest)
        return dest

experiment.ComfyClient = FakeClient

import tempfile, shutil
TMP = pathlib.Path(tempfile.mkdtemp(prefix="chibi_e2e_"))
run_dir = TMP / "run_001"

res = mr.run_model(
    "qwen_edit_2511_q3_k_m",
    character_id="waifu_001",
    input_rel="reference/full_body.png",
    extra_refs=("reference/outfit.png",),
    prompt="PROMPT DE TESTE",
    run_dir=run_dir,
    models_dir=pathlib.Path("/tmp"),
    environment_name="colab_comfy_gguf",
    seed=42,
)
print("run_dir:", res.run_dir)
loader = next(v for v in SUBMETIDO.values()
              if v.get("class_type") == "UnetLoaderGGUF")
print("unet submetido:", loader["inputs"])
assert loader["inputs"]["unet_name"] == "qwen-image-edit-2511-Q3_K_M.gguf"
assert "weight_dtype" not in loader["inputs"]

ks = next(v for v in SUBMETIDO.values() if v.get("class_type") == "KSampler")
print("ksampler:", {k: ks["inputs"][k] for k in
                    ("seed","steps","cfg","sampler_name","scheduler","denoise")})
assert ks["inputs"]["steps"] == 20 and ks["inputs"]["cfg"] == 2.5
assert ks["inputs"]["denoise"] == 0.5 and ks["inputs"]["seed"] == 42

enc = [v for v in SUBMETIDO.values()
       if v.get("class_type") == "TextEncodeQwenImageEditPlus"]
pos = next(v for v in enc if v["inputs"].get("image1"))
slots = [k for k in pos["inputs"] if k.startswith("image")]
print("slots de imagem usados:", slots)
assert slots == ["image1", "image2"], "slot nao usado deveria ter sido podado"

r = json.loads((run_dir / "recipe.json").read_text())
print("model_key      :", r["model_key"])
print("workflow       :", r["workflow"])
print("license        :", r["license"], "| commercial:", r["commercial_status"])
print("batch          :", r["parameters"]["batch"])
print("refs           :", [(x["role"], x["file"]) for x in r["references"]])
print("primary role   :", r["primary_image_role"])
print("output_sha256  :", r["output_sha256"][:16])
print("pixel_sha256   :", r["output_pixel_sha256"][:16])
assert r["output_sha256"] != r["output_pixel_sha256"]
assert r["approval_status"] == "experimental"
assert r["model_files_on_server"]["unet"].startswith("qwen-image-edit")
# A variante quantizada NAO pode herdar o status comercial do modelo-base.
print("commercial     :", r["commercial_status"])
assert r["commercial_status"] == "pending_human_review", (
    "variante de terceiro herdou o status do modelo-base")
assert r["base_model_commercial_status"] == "approved"
assert r["base_model_key"] == "qwen_image_edit_2511"
assert r["commercial_status_note"]

shutil.rmtree(TMP, ignore_errors=True)
print("\nOK ponta a ponta")

"""Testes da FASE 3A — cliente ComfyUI e execucoes experimentais.

Nenhum teste aqui exige GPU nem rede externa. Onde e preciso um servidor,
subimos um ComfyUI FALSO em http.server no localhost, que fala o mesmo
protocolo. Testes que exigem GPU real ficam marcados [integration test] e
sao pulados quando nao ha backend configurado.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import comfy_client, config, experiment, paths, preflight  # noqa: E402
from chibi.comfy_client import (ComfyClient, ComfyClientNotConfigured,  # noqa: E402
                                ComfyError, ComfyExecutionError, ComfyJob,
                                ComfyOutput, ComfyTimeout)

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c6360000002000100ffff03000006"
    "00057b7d5f0000000049454e44ae426082"
)



def _clear_config_cache() -> None:
    """Limpa os loaders cacheados de config (lru_cache)."""
    for name in ("project", "models_lock", "quality_gates"):
        fn = getattr(config, name, None)
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()



_PATH_ATTRS = ("ROOT", "CONFIG_DIR", "ENVIRONMENTS_DIR", "PROJECT_CONFIG",
               "MODELS_LOCK", "QUALITY_GATES", "CHARACTERS_DIR")
_REAL_PATHS = {name: getattr(paths, name) for name in _PATH_ATTRS}


def _point_paths_at(root: Path) -> None:
    paths.ROOT = root
    paths.CONFIG_DIR = root / "config"
    paths.ENVIRONMENTS_DIR = root / "config" / "environments"
    paths.PROJECT_CONFIG = root / "config" / "project.yaml"
    paths.MODELS_LOCK = root / "config" / "models.lock.yaml"
    paths.QUALITY_GATES = root / "config" / "quality_gates.yaml"
    paths.CHARACTERS_DIR = root / "characters"
    _clear_config_cache()


def _use_real_repo() -> None:
    """Garante que o teste ve o repositorio real, nao um temporario."""
    for name, value in _REAL_PATHS.items():
        setattr(paths, name, value)
    _clear_config_cache()


# --- servidor ComfyUI falso -------------------------------------------------

class FakeComfyState:
    def __init__(self) -> None:
        self.mode = "ok"            # ok | error | slow | empty | badjson
        self.submitted: list[dict] = []
        self.uploaded: list[str] = []
        self.polls = 0


def make_handler(state: FakeComfyState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):  # silencio
            pass

        def _send(self, code: int, payload, raw: bytes | None = None):
            body = raw if raw is not None else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/system_stats":
                if state.mode == "badjson":
                    return self._send(200, None, raw=b"<html>nao json</html>")
                system = {"comfyui_version": "0.3.99",
                          "python_version": "3.12.0",
                          "pytorch_version": "2.6.0+cu124",
                          "os": "posix"}
                if state.mode == "no_gpu":
                    devices = []
                elif state.mode == "cpu_only":
                    devices = [{"name": "cpu", "type": "cpu",
                                "vram_total": 0, "vram_free": 0}]
                elif state.mode == "small_gpu":
                    devices = [{"name": "NVIDIA RTX 2070", "type": "cuda",
                                "vram_total": 8 * 1024**3,
                                "vram_free": 7 * 1024**3}]
                elif state.mode == "no_vram_info":
                    devices = [{"name": "NVIDIA L40S", "type": "cuda"}]
                else:
                    devices = [{"name": "NVIDIA L40S", "type": "cuda",
                                "vram_total": 48 * 1024**3,
                                "vram_free": 47 * 1024**3}]
                return self._send(200, {"system": system, "devices": devices})
            if self.path == "/object_info":
                if state.mode == "no_object_info":
                    return self._send(200, {})
                nodes = {"UNETLoader": {}, "CLIPLoader": {}, "VAELoader": {},
                         "LoadImage": {}, "TextEncodeQwenImageEditPlus": {},
                         "EmptySD3LatentImage": {}, "KSampler": {},
                         "VAEDecode": {}, "SaveImage": {}}
                if state.mode == "missing_node":
                    nodes.pop("TextEncodeQwenImageEditPlus")
                if state.mode == "bad_socket":
                    # servidor conhece o node, mas com outros inputs
                    nodes["KSampler"] = {"input": {"required": {
                        "seed": [], "steps": [], "cfg": [],
                        "sampler_name": [], "scheduler": [],
                        "model": [], "positive": [], "negative": [],
                        "latent_image": []}}}   # 'denoise' ausente de proposito
                return self._send(200, nodes)
            if self.path.startswith("/models/"):
                folder = self.path.rsplit("/", 1)[-1]
                if state.mode == "with_models":
                    return self._send(200, {
                        # Nome REAL do repo oficial Comfy-Org (sha 984166f6).
                        # Nao existe variante fp8_e4m3fn do 2511 — so bf16,
                        # fp8mixed e int8_convrot.
                        "diffusion_models":
                            ["qwen_image_edit_2511_fp8mixed.safetensors"],
                        "text_encoders":
                            ["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
                        "vae": ["qwen_image_vae.safetensors"],
                    }.get(folder, []))
                if state.mode == "no_models":
                    return self._send(200, {
                        "diffusion_models": ["outro_modelo.safetensors"],
                        "text_encoders": [], "vae": [],
                    }.get(folder, []))
                return self._send(404, {"error": "sem endpoint /models"})
            if self.path.startswith("/history/"):
                state.polls += 1
                if state.mode == "slow" and state.polls < 1000:
                    return self._send(200, {})
                pid = self.path.rsplit("/", 1)[-1]
                if state.mode == "error":
                    return self._send(200, {pid: {"status": {
                        "status_str": "error", "completed": False,
                        "messages": [["execution_error", {
                            "node_id": "8", "node_type": "KSampler",
                            "exception_message": "CUDA out of memory"}]]}}})
                if state.mode == "empty":
                    return self._send(200, {pid: {
                        "status": {"status_str": "success", "completed": True},
                        "outputs": {}}})
                return self._send(200, {pid: {
                    "status": {"status_str": "success", "completed": True},
                    "outputs": {"10": {"images": [
                        {"filename": "out_0001.png", "subfolder": "chibi_exp",
                         "type": "output"}]}}}})
            if self.path.startswith("/view"):
                return self._send(200, None, raw=PNG_1PX)
            return self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            if self.path == "/upload/image":
                state.uploaded.append(str(len(body)))
                return self._send(200, {"name": "input.png",
                                        "subfolder": "chibi", "type": "input"})
            if self.path == "/prompt":
                payload = json.loads(body)
                state.submitted.append(payload)
                if state.mode == "reject":
                    return self._send(200, {"node_errors": {
                        "1": {"errors": [{"message": "node desconhecido"}]}}})
                return self._send(200, {"prompt_id": "fake-prompt-123",
                                        "number": 1})
            return self._send(404, {"error": "not found"})

    return Handler


class FakeComfy:
    def __init__(self, mode: str = "ok"):
        self.state = FakeComfyState()
        self.state.mode = mode

    def __enter__(self) -> FakeComfy:
        self.server = HTTPServer(("127.0.0.1", 0), make_handler(self.state))
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False

    def client(self, **kw) -> ComfyClient:
        kw.setdefault("poll_interval_seconds", 0.01)
        kw.setdefault("timeout_seconds", 5)
        return ComfyClient(self.url, **kw)


# --- cliente: caminho feliz -------------------------------------------------

def test_ping_and_server_info():
    with FakeComfy() as fake:
        info = fake.client().server_info()
        assert info["reachable"] is True
        assert info["comfyui_version"] == "0.3.99"
        assert info["devices"][0]["name"] == "NVIDIA L40S"


def test_submit_and_wait_returns_outputs():
    with FakeComfy() as fake:
        client = fake.client()
        job = client.submit({"1": {"class_type": "SaveImage", "inputs": {}}})
        assert job.prompt_id == "fake-prompt-123"
        outputs = client.wait(job)
        assert len(outputs) == 1
        assert outputs[0].filename == "out_0001.png"
        assert outputs[0].subfolder == "chibi_exp"


def test_download_writes_file_atomically():
    with FakeComfy() as fake, tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / "sub" / "out.png"
        fake.client().download(ComfyOutput("out_0001.png", "chibi_exp"), dest)
        assert dest.is_file() and dest.read_bytes() == PNG_1PX
        assert not list(Path(tmpdir).rglob("*.tmp"))


def test_upload_image_sends_multipart():
    with FakeComfy() as fake, tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "input.png"
        src.write_bytes(PNG_1PX)
        name = fake.client().upload_image(src)
        assert name == "chibi/input.png"
        assert fake.state.uploaded


# --- cliente: caminhos de falha ---------------------------------------------

def test_comfyui_unavailable():
    """Servidor fora do ar."""
    client = ComfyClient("http://127.0.0.1:1", connect_timeout=2)
    info = client.server_info()
    assert info["reachable"] is False
    assert "inacessivel" in info["error"]


def test_wrong_endpoint_gives_clear_error():
    with FakeComfy() as fake:
        try:
            fake.client()._get_json("/rota/que/nao/existe")
        except ComfyError as exc:
            assert "404" in str(exc)
        else:
            raise AssertionError("deveria falhar")


def test_invalid_workflow_is_rejected():
    with FakeComfy(mode="reject") as fake:
        try:
            fake.client().submit({"1": {"class_type": "NaoExiste", "inputs": {}}})
        except ComfyExecutionError as exc:
            assert "rejeitado" in str(exc)
        else:
            raise AssertionError("deveria recusar workflow invalido")


def test_empty_workflow_refused_before_network():
    client = ComfyClient("http://127.0.0.1:1")
    for bad in ({}, None, "texto"):
        try:
            client.submit(bad)  # type: ignore[arg-type]
        except ComfyError:
            pass
        else:
            raise AssertionError(f"deveria recusar {bad!r}")


def test_execution_error_surfaces_node_and_message():
    """Erro de GPU precisa chegar legivel ao usuario."""
    with FakeComfy(mode="error") as fake:
        try:
            fake.client().wait(ComfyJob("fake-prompt-123", "c"))
        except ComfyExecutionError as exc:
            assert "KSampler" in str(exc)
            assert "CUDA out of memory" in str(exc)
        else:
            raise AssertionError("deveria propagar o erro de execucao")


def test_timeout_is_raised_and_explains():
    with FakeComfy(mode="slow") as fake:
        client = fake.client(timeout_seconds=1, poll_interval_seconds=0.05)
        try:
            client.wait(ComfyJob("fake-prompt-123", "c"), timeout=1)
        except ComfyTimeout as exc:
            assert "nao terminou" in str(exc)
        else:
            raise AssertionError("deveria estourar timeout")


def test_completed_without_image_is_an_error():
    with FakeComfy(mode="empty") as fake:
        try:
            fake.client().wait(ComfyJob("fake-prompt-123", "c"), timeout=2)
        except ComfyExecutionError as exc:
            assert "sem produzir imagem" in str(exc)
        else:
            raise AssertionError("deveria reclamar de output ausente")


def test_non_json_response():
    with FakeComfy(mode="badjson") as fake:
        try:
            fake.client().ping()
        except ComfyError as exc:
            assert "nao-JSON" in str(exc)
        else:
            raise AssertionError("deveria detectar resposta nao-JSON")


def test_upload_missing_file():
    with FakeComfy() as fake:
        try:
            fake.client().upload_image(Path("/nao/existe.png"))
        except ComfyError as exc:
            assert "nao existe" in str(exc)
        else:
            raise AssertionError("deveria falhar")


# --- configuracao: nada de localhost hardcoded ------------------------------

def test_local_environment_refuses_by_default():
    _use_real_repo()
    try:
        ComfyClient.from_environment("local")
    except ComfyClientNotConfigured as exc:
        assert "enabled" in str(exc)
    else:
        raise AssertionError("ambiente local nao deveria estar habilitado")


def test_unknown_environment_refused():
    _use_real_repo()
    try:
        ComfyClient.from_environment("ambiente_inexistente")
    except ComfyClientNotConfigured:
        pass
    else:
        raise AssertionError("deveria recusar ambiente inexistente")


def test_cloud_needs_url_from_env_var():
    _use_real_repo()
    saved = os.environ.pop("CHIBI_COMFY_URL", None)
    try:
        ComfyClient.from_environment("cloud")
    except ComfyClientNotConfigured as exc:
        assert "CHIBI_COMFY_URL" in str(exc)
    else:
        raise AssertionError("deveria exigir a variavel de ambiente")
    finally:
        if saved:
            os.environ["CHIBI_COMFY_URL"] = saved


def test_url_comes_from_environment_variable():
    _use_real_repo()
    saved = os.environ.get("CHIBI_COMFY_URL")
    os.environ["CHIBI_COMFY_URL"] = "http://gpu-box.example:8188"
    try:
        _clear_config_cache()
        client = ComfyClient.from_environment("cloud")
        assert client.base_url == "http://gpu-box.example:8188"
    finally:
        if saved is None:
            os.environ.pop("CHIBI_COMFY_URL", None)
        else:
            os.environ["CHIBI_COMFY_URL"] = saved
        _clear_config_cache()


def test_no_hardcoded_localhost_in_source():
    """O endereco do backend nunca pode estar cravado no codigo."""
    for name in ("comfy_client.py", "experiment.py"):
        src = (ROOT / "scripts" / "chibi" / name).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in src.splitlines()
            if not line.strip().startswith("#")
        )
        for bad in ("127.0.0.1:8188", "localhost:8188"):
            assert bad not in code, f"{name} tem {bad} hardcoded"


# --- workflow ---------------------------------------------------------------

def test_workflow_file_is_valid_json():
    _use_real_repo()
    wf = experiment.load_workflow()
    nodes = experiment.workflow_nodes(wf)
    assert len(nodes) >= 8
    assert all("class_type" in n for n in nodes.values())


def test_workflow_has_save_and_load_nodes():
    _use_real_repo()
    nodes = experiment.workflow_nodes(experiment.load_workflow())
    classes = {n["class_type"] for n in nodes.values()}
    assert "LoadImage" in classes and "SaveImage" in classes


def test_missing_workflow_fails_clearly():
    _use_real_repo()
    try:
        experiment.load_workflow("nao/existe")
    except experiment.ExperimentError as exc:
        assert "nao encontrado" in str(exc)
    else:
        raise AssertionError("deveria falhar")


def test_resolve_workflow_preserves_types():
    """%%SEED%% sozinho vira int, nao string."""
    wf = {"8": {"class_type": "KSampler",
                "inputs": {"seed": "%%SEED%%", "cfg": "%%CFG%%",
                           "text": "prefixo %%NAME%% sufixo"}}}
    out = experiment.resolve_workflow(
        wf, {"SEED": 42, "CFG": 2.5, "NAME": "x"}
    )
    assert out["8"]["inputs"]["seed"] == 42
    assert isinstance(out["8"]["inputs"]["seed"], int)
    assert out["8"]["inputs"]["cfg"] == 2.5
    assert out["8"]["inputs"]["text"] == "prefixo x sufixo"


def test_resolve_workflow_detects_missing_placeholder():
    try:
        experiment.resolve_workflow(
            {"1": {"class_type": "X", "inputs": {"a": "%%NAO_TENHO%%"}}}, {}
        )
    except experiment.ExperimentError as exc:
        assert "NAO_TENHO" in str(exc)
    else:
        raise AssertionError("deveria detectar placeholder sem valor")


def test_resolve_workflow_strips_comments():
    resolved = experiment.resolve_workflow(
        {"_comment": ["nota"], "1": {"class_type": "X", "inputs": {}}}, {}
    )
    assert "_comment" not in resolved


# --- experimento ------------------------------------------------------------

class TempExperimentRepo:
    """Repo temporario com waifu-like pronta para experimento."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "config/environments").mkdir(parents=True)
        for rel in ("config/project.yaml", "config/models.lock.yaml",
                    "config/quality_gates.yaml",
                    "config/environments/local.yaml",
                    "config/environments/cloud.yaml"):
            shutil.copy2(ROOT / rel, self.root / rel)
        wf_dir = self.root / "workflows/experimental/qwen_edit_minimal"
        wf_dir.mkdir(parents=True)
        shutil.copy2(
            ROOT / "workflows/experimental/qwen_edit_minimal/v1.json",
            wf_dir / "v1.json",
        )
        cdir = self.root / "characters/t01/reference"
        cdir.mkdir(parents=True)
        (cdir / "full_body.png").write_bytes(PNG_1PX)
        (self.root / "characters/t01/character.yaml").write_text(
            "id: t01\n", encoding="utf-8"
        )
        self._saved = (paths.ROOT, paths.CHARACTERS_DIR, paths.ENVIRONMENTS_DIR)
        paths.ROOT = self.root
        paths.CHARACTERS_DIR = self.root / "characters"
        paths.ENVIRONMENTS_DIR = self.root / "config/environments"
        _clear_config_cache()
        return self

    def __exit__(self, *exc):
        (paths.ROOT, paths.CHARACTERS_DIR, paths.ENVIRONMENTS_DIR) = self._saved
        _clear_config_cache()
        self._tmp.cleanup()
        return False


def test_experiment_dry_run_produces_recipe():
    with TempExperimentRepo() as repo:
        result = experiment.run_qwen_edit(
            "t01", prompt="teste", environment_name="cloud", dry_run=True
        )
        assert result.run_id == "run_001"
        recipe = json.loads(result.recipe_path.read_text())
        assert recipe["approval_status"] == "experimental"
        assert recipe["dry_run"] is True
        assert recipe["input_sha256"]
        assert recipe["output_sha256"] is None
        assert (result.run_dir / "workflow.resolved.json").is_file()
        assert (result.run_dir / "input.png").is_file()
        _ = repo


def test_experiment_never_marks_approved():
    """Nenhum caminho de codigo pode aprovar um experimento."""
    with TempExperimentRepo():
        result = experiment.run_qwen_edit(
            "t01", prompt="p", environment_name="cloud", dry_run=True
        )
        recipe = json.loads(result.recipe_path.read_text())
        assert recipe["approval_status"] == "experimental"
        assert recipe["approved_by"] is None
        assert recipe["approved_at"] is None
        assert "NAO e um asset" in recipe["note"]


def test_experiment_writes_outside_character_dir():
    """Experimento nao contamina characters/<id>/."""
    with TempExperimentRepo() as repo:
        result = experiment.run_qwen_edit(
            "t01", prompt="p", environment_name="cloud", dry_run=True
        )
        assert "experiments" in result.run_dir.parts
        assert not (repo.root / "characters/t01/chibi").exists()


def test_experiment_run_ids_increment():
    with TempExperimentRepo():
        a = experiment.run_qwen_edit("t01", prompt="p",
                                     environment_name="cloud", dry_run=True)
        b = experiment.run_qwen_edit("t01", prompt="p",
                                     environment_name="cloud", dry_run=True)
        assert (a.run_id, b.run_id) == ("run_001", "run_002")


def test_experiment_missing_character():
    with TempExperimentRepo():
        try:
            experiment.run_qwen_edit("fantasma", prompt="p",
                                     environment_name="cloud", dry_run=True)
        except experiment.ExperimentError as exc:
            assert "nao existe" in str(exc)
        else:
            raise AssertionError("deveria falhar")


def test_experiment_missing_input():
    with TempExperimentRepo() as repo:
        (repo.root / "characters/t01/reference/full_body.png").unlink()
        try:
            experiment.run_qwen_edit("t01", prompt="p",
                                     environment_name="cloud", dry_run=True)
        except experiment.ExperimentError as exc:
            assert "flow01" in str(exc)
        else:
            raise AssertionError("deveria exigir o input")


def test_experiment_refuses_unverified_model():
    with TempExperimentRepo():
        try:
            experiment.run_qwen_edit(
                "t01", prompt="p", environment_name="cloud",
                model_key="real_esrgan_anime_6b", dry_run=True,
            )
        except experiment.ExperimentError as exc:
            assert "nao liberado" in str(exc)
        else:
            raise AssertionError("modelo sem licenca verificada deveria ser barrado")


def test_experiment_refuses_rejected_model():
    with TempExperimentRepo():
        try:
            experiment.run_qwen_edit("t01", prompt="p",
                                     environment_name="cloud",
                                     model_key="bria_rmbg_2_0", dry_run=True)
        except experiment.ExperimentError:
            pass
        else:
            raise AssertionError("modelo rejeitado deveria ser barrado")


def test_recipe_has_all_required_fields():
    """Campos exigidos pela secao 11 da spec da fase 3A."""
    with TempExperimentRepo():
        result = experiment.run_qwen_edit("t01", prompt="p",
                                          environment_name="cloud", dry_run=True)
        recipe = json.loads(result.recipe_path.read_text())
        for field_ in ("model", "revision", "model_sha256", "license",
                       "workflow", "workflow_sha256", "seed", "prompt",
                       "parameters", "quantization", "dtype", "device",
                       "environment", "input_sha256", "output_sha256",
                       "timestamp"):
            assert field_ in recipe, f"recipe sem o campo '{field_}'"


def test_recipe_records_exact_model_revision():
    with TempExperimentRepo():
        result = experiment.run_qwen_edit("t01", prompt="p",
                                          environment_name="cloud", dry_run=True)
        recipe = json.loads(result.recipe_path.read_text())
        assert recipe["revision"] == "6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9"
        assert recipe["license"] == "Apache-2.0"
        assert recipe["license_verified"] is True


def test_compare_runs_detects_same_config():
    with TempExperimentRepo():
        a = experiment.run_qwen_edit("t01", prompt="p", environment_name="cloud",
                                     dry_run=True)
        b = experiment.run_qwen_edit("t01", prompt="p", environment_name="cloud",
                                     dry_run=True)
        report = experiment.compare_runs(a.run_dir, b.run_dir)
        assert report["same_seed"] and report["same_prompt"]
        assert report["same_workflow"] and report["same_model_revision"]
        assert report["identical_output"] is False   # dry-run: sem bytes


def test_compare_runs_detects_different_seed():
    with TempExperimentRepo():
        a = experiment.run_qwen_edit("t01", prompt="p", environment_name="cloud",
                                     dry_run=True)
        b = experiment.run_qwen_edit("t01", prompt="p", environment_name="cloud",
                                     overrides={"seed": 999}, dry_run=True)
        assert experiment.compare_runs(a.run_dir, b.run_dir)["same_seed"] is False


def test_compare_runs_missing_recipe():
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            experiment.compare_runs(Path(tmpdir), Path(tmpdir))
        except experiment.ExperimentError as exc:
            assert "recipe ausente" in str(exc)
        else:
            raise AssertionError("deveria falhar")


# --- integracao (exigem GPU real) -------------------------------------------

def _integration_enabled() -> bool:
    return bool(os.environ.get("CHIBI_COMFY_URL"))


def test_integration_real_backend_reachable():
    """[integration test] Exige CHIBI_COMFY_URL apontando para GPU real."""
    if not _integration_enabled():
        return  # pulado: sem backend configurado
    client = ComfyClient.from_environment("cloud")
    info = client.server_info()
    assert info["reachable"], info.get("error")
    assert info.get("devices"), "backend sem GPU visivel"


def test_integration_workflow_nodes_exist():
    """[integration test] Confere os class_type contra o servidor real."""
    if not _integration_enabled():
        return
    client = ComfyClient.from_environment("cloud")
    available = client.object_info()
    nodes = experiment.workflow_nodes(experiment.load_workflow())
    missing = [n["class_type"] for n in nodes.values()
               if n["class_type"] not in available]
    assert not missing, f"nodes ausentes no servidor: {missing}"




# --- execucao REAL contra backend (servidor falso) --------------------------
# Estes testes exercitam o caminho nao-dry-run por inteiro: upload, submit,
# wait, download, medicao de tempo/VRAM e recipe. E o mais perto de uma
# execucao de GPU que da para chegar sem GPU.

def test_full_execution_path_against_backend():
    with TempExperimentRepo(), FakeComfy() as fake:
        os.environ["CHIBI_COMFY_URL"] = fake.url
        try:
            _clear_config_cache()
            result = experiment.run_qwen_edit(
                "t01", prompt="teste real", environment_name="cloud",
                dry_run=False,
            )
        finally:
            os.environ.pop("CHIBI_COMFY_URL", None)

        assert result.output_path is not None
        assert result.output_path.is_file()
        assert result.output_path.read_bytes() == PNG_1PX

        recipe = json.loads(result.recipe_path.read_text())
        assert recipe["output_sha256"], "output sem hash"
        assert recipe["input_sha256"], "input sem hash"
        # (o servidor falso devolve o mesmo PNG que recebeu, entao aqui os
        # dois hashes coincidem por construcao — nao ha o que comparar)
        assert recipe["approval_status"] == "experimental"
        # hardware veio do servidor, nao presumido
        assert recipe["gpu"]["name"] == "NVIDIA L40S"
        assert recipe["gpu"]["vram_total_gb"] == 48.0
        assert recipe["cuda"] == "12.4"
        assert recipe["comfyui_version"] == "0.3.99"
        assert recipe["execution_time"] is not None
        # servidor falso responde instantaneamente: 0.0 e valido, None nao
        assert isinstance(recipe["cost_estimate"]["usd"], float)
        assert "NAO e custo de producao" in recipe["cost_estimate"]["note"]
        assert recipe["timings"]["total_seconds"] >= 0


def test_two_runs_produce_comparable_recipes():
    """Secao 11: duas execucoes reais, comparar metadata."""
    with TempExperimentRepo(), FakeComfy() as fake:
        os.environ["CHIBI_COMFY_URL"] = fake.url
        try:
            _clear_config_cache()
            a = experiment.run_qwen_edit("t01", prompt="p",
                                         environment_name="cloud", dry_run=False)
            b = experiment.run_qwen_edit("t01", prompt="p",
                                         environment_name="cloud", dry_run=False)
        finally:
            os.environ.pop("CHIBI_COMFY_URL", None)

        report = experiment.compare_runs(a.run_dir, b.run_dir)
        assert report["same_seed"] and report["same_prompt"]
        assert report["same_model_revision"] and report["same_workflow"]
        assert report["same_input"] and report["same_quantization"]
        assert report["identical_output"] is True   # servidor falso: bytes iguais
        assert "identicos" in report["verdict"]


def test_workflow_sent_to_server_has_no_placeholders():
    """O servidor nunca pode receber %%PLACEHOLDER%% cru."""
    with TempExperimentRepo(), FakeComfy() as fake:
        os.environ["CHIBI_COMFY_URL"] = fake.url
        try:
            _clear_config_cache()
            experiment.run_qwen_edit("t01", prompt="p",
                                     environment_name="cloud", dry_run=False)
        finally:
            os.environ.pop("CHIBI_COMFY_URL", None)

        sent = json.dumps(fake.state.submitted[0]["prompt"])
        assert "%%" not in sent
        assert fake.state.submitted[0]["prompt"]["8"]["inputs"]["seed"] == 42


def test_oom_during_real_execution_is_readable():
    """Secao 16: OOM precisa virar mensagem legivel, sem retry."""
    with TempExperimentRepo(), FakeComfy(mode="error") as fake:
        os.environ["CHIBI_COMFY_URL"] = fake.url
        try:
            _clear_config_cache()
            experiment.run_qwen_edit("t01", prompt="p",
                                     environment_name="cloud", dry_run=False)
        except ComfyExecutionError as exc:
            assert "CUDA out of memory" in str(exc)
            assert "KSampler" in str(exc)
        else:
            raise AssertionError("OOM deveria propagar")
        finally:
            os.environ.pop("CHIBI_COMFY_URL", None)
        # sem retry: exatamente uma submissao
        assert len(fake.state.submitted) == 1


def test_no_retry_on_failure():
    """Nao pode haver retry infinito (secao 16)."""
    with TempExperimentRepo(), FakeComfy(mode="empty") as fake:
        os.environ["CHIBI_COMFY_URL"] = fake.url
        try:
            _clear_config_cache()
            experiment.run_qwen_edit("t01", prompt="p",
                                     environment_name="cloud", dry_run=False)
        except ComfyExecutionError:
            pass
        finally:
            os.environ.pop("CHIBI_COMFY_URL", None)
        assert len(fake.state.submitted) == 1


def test_estimate_cost_is_honest():
    assert experiment.estimate_cost(None, 0.6)["usd"] is None
    assert experiment.estimate_cost(120, None)["usd"] is None
    c = experiment.estimate_cost(3600, 0.60)
    assert c["usd"] == 0.60
    c2 = experiment.estimate_cost(120, 0.60)
    assert c2["usd"] == 0.02
    assert "NAO e custo de producao" in c2["note"]


# --- FASE 3B.1: preflight remoto -------------------------------------------

def _preflight_against(fake, **kw):
    os.environ["CHIBI_COMFY_URL"] = fake.url
    try:
        _clear_config_cache()
        return preflight.run("cloud", **kw)
    finally:
        os.environ.pop("CHIBI_COMFY_URL", None)


def test_preflight_all_green_on_healthy_server():
    _use_real_repo()
    with FakeComfy() as fake:
        report = _preflight_against(fake)
        assert report.ready is True, [c.status for c in report.blockers]
        assert report.server["comfyui_version"] == "0.3.99"
        assert report.server["cuda_version"] == "12.4"
        names = {c.name: c.status for c in report.checks}
        assert names["endpoint"] == preflight.OK
        assert names["gpu"] == preflight.OK
        assert names["workflow"] == preflight.OK


def test_preflight_endpoint_unreachable():
    _use_real_repo()
    os.environ["CHIBI_COMFY_URL"] = "http://127.0.0.1:1"
    try:
        _clear_config_cache()
        report = preflight.run("cloud")
    finally:
        os.environ.pop("CHIBI_COMFY_URL", None)
    assert report.ready is False
    assert report.checks[0].status == preflight.ENDPOINT_UNREACHABLE


def test_preflight_not_configured_without_url():
    _use_real_repo()
    saved = os.environ.pop("CHIBI_COMFY_URL", None)
    try:
        _clear_config_cache()
        report = preflight.run("cloud")
    finally:
        if saved:
            os.environ["CHIBI_COMFY_URL"] = saved
    assert report.ready is False
    assert report.checks[0].status == preflight.NOT_CONFIGURED


def test_preflight_detects_missing_node():
    """WORKFLOW_INCOMPATIBLE quando falta um class_type."""
    _use_real_repo()
    with FakeComfy(mode="missing_node") as fake:
        report = _preflight_against(fake)
        wf = next(c for c in report.checks if c.name == "workflow")
        assert wf.status == preflight.WORKFLOW_INCOMPATIBLE
        assert "TextEncodeQwenImageEditPlus" in wf.data["missing"]
        assert report.ready is False


def test_preflight_detects_socket_mismatch():
    """Input que o servidor nao reconhece: expected vs actual documentado."""
    _use_real_repo()
    with FakeComfy(mode="bad_socket") as fake:
        report = _preflight_against(fake)
        wf = next(c for c in report.checks if c.name == "workflow")
        assert wf.status == preflight.WORKFLOW_INCOMPATIBLE
        mismatches = wf.data["socket_mismatches"]
        assert mismatches
        assert all({"workflow_node", "expected", "actual"} <= set(m)
                   for m in mismatches)


def test_preflight_object_info_missing():
    _use_real_repo()
    with FakeComfy(mode="no_object_info") as fake:
        report = _preflight_against(fake)
        wf = next(c for c in report.checks if c.name == "workflow")
        assert wf.status == preflight.OBJECT_INFO_MISSING
        assert report.ready is False


def test_preflight_model_missing():
    """MODEL_MISSING: o arquivo esperado nao esta no servidor."""
    _use_real_repo()
    with FakeComfy(mode="no_models") as fake:
        report = _preflight_against(fake)
        models = next(c for c in report.checks if c.name == "models")
        assert models.status == preflight.MODEL_MISSING
        assert "unet" in models.data["missing"]
        assert "NAO troque de modelo" in models.detail


def test_preflight_model_present():
    _use_real_repo()
    with FakeComfy(mode="with_models") as fake:
        report = _preflight_against(fake)
        models = next(c for c in report.checks if c.name == "models")
        assert models.status == preflight.OK, models.detail


def test_preflight_model_unknown_when_server_has_no_endpoint():
    """Sem /models, nao da para afirmar: UNKNOWN, e UNKNOWN nao bloqueia."""
    _use_real_repo()
    with FakeComfy() as fake:   # modo ok: /models devolve 404
        report = _preflight_against(fake)
        models = next(c for c in report.checks if c.name == "models")
        assert models.status == preflight.UNKNOWN
        assert models.blocking is False


def test_preflight_gpu_missing():
    _use_real_repo()
    with FakeComfy(mode="no_gpu") as fake:
        report = _preflight_against(fake)
        gpu = next(c for c in report.checks if c.name == "gpu")
        assert gpu.status == preflight.GPU_MISSING
        assert report.ready is False


def test_preflight_cpu_only_is_gpu_missing():
    _use_real_repo()
    with FakeComfy(mode="cpu_only") as fake:
        gpu = next(c for c in _preflight_against(fake).checks
                   if c.name == "gpu")
        assert gpu.status == preflight.GPU_MISSING


def test_preflight_gpu_insufficient_vram():
    """cloud.yaml exige 24GB; servidor oferece 8GB."""
    _use_real_repo()
    with FakeComfy(mode="small_gpu") as fake:
        gpu = next(c for c in _preflight_against(fake).checks
                   if c.name == "gpu")
        assert gpu.status == preflight.GPU_INSUFFICIENT
        assert "8.0 GB" in gpu.detail and "24" in gpu.detail


def test_preflight_vram_unknown_does_not_block():
    _use_real_repo()
    with FakeComfy(mode="no_vram_info") as fake:
        report = _preflight_against(fake)
        gpu = next(c for c in report.checks if c.name == "gpu")
        assert gpu.status == preflight.UNKNOWN
        assert gpu.blocking is False


def test_preflight_malformed_response():
    _use_real_repo()
    with FakeComfy(mode="badjson") as fake:
        report = _preflight_against(fake)
        assert report.ready is False
        assert report.checks[0].status == preflight.ENDPOINT_UNREACHABLE


def test_preflight_never_runs_inference():
    """Preflight nao pode enfileirar job algum."""
    _use_real_repo()
    with FakeComfy(mode="with_models") as fake:
        _preflight_against(fake)
        assert fake.state.submitted == [], "preflight enviou job para a GPU!"
        assert fake.state.uploaded == []


def test_preflight_report_serializes():
    _use_real_repo()
    with FakeComfy() as fake:
        data = _preflight_against(fake).to_dict()
        json.dumps(data)   # nao pode explodir
        assert set(data) >= {"environment", "ready", "server", "checks"}


# --- FASE 3B.1: seguranca ---------------------------------------------------

def test_redact_url_strips_credentials():
    from chibi.comfy_client import redact_url
    assert redact_url("https://u:p@h:8188/x") == "https://***@h:8188/x"
    assert "abc123" not in redact_url("http://h:8188/?token=abc123")
    assert redact_url(None) == "<nao definida>"
    assert redact_url("http://h:8188") == "http://h:8188"


def test_client_never_exposes_raw_url_in_errors():
    """URL com credencial nao pode vazar em mensagem de erro."""
    client = ComfyClient("http://user:segredo@127.0.0.1:1", connect_timeout=2)
    info = client.server_info()
    assert "segredo" not in json.dumps(info)
    assert "segredo" not in info["error"]
    assert info["base_url"] == "http://***@127.0.0.1:1"


def test_token_never_lands_in_recipe():
    """Authorization/token jamais entram no recipe."""
    with TempExperimentRepo(), FakeComfy() as fake:
        os.environ["CHIBI_COMFY_URL"] = fake.url
        os.environ["CHIBI_COMFY_TOKEN"] = "SEGREDO-NAO-VAZAR"
        try:
            _clear_config_cache()
            result = experiment.run_qwen_edit(
                "t01", prompt="p", environment_name="cloud", dry_run=False)
        finally:
            os.environ.pop("CHIBI_COMFY_URL", None)
            os.environ.pop("CHIBI_COMFY_TOKEN", None)
        blob = result.recipe_path.read_text()
        assert "SEGREDO-NAO-VAZAR" not in blob
        assert "Authorization" not in blob
        assert "Bearer" not in blob


def test_no_credentials_committed_in_config():
    """Nenhum segredo literal nos YAML versionados."""
    import re
    suspicious = re.compile(
        r"(hf_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]{12,}"
        r"|(api[_-]?key|password|secret)\s*:\s*['\"]?[A-Za-z0-9._-]{12,})",
        re.IGNORECASE)
    for path in (ROOT / "config").rglob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert not suspicious.search(text), f"possivel segredo em {path.name}"


def test_cloud_config_has_no_hardcoded_url_or_token():
    _use_real_repo()
    env = config.environment("cloud")
    block = env["comfyui"]
    assert block.get("base_url_env") == "CHIBI_COMFY_URL"
    assert block.get("token_env") == "CHIBI_COMFY_TOKEN"
    saved = os.environ.pop("CHIBI_COMFY_URL", None)
    try:
        _clear_config_cache()
        assert config.environment("cloud")["comfyui"].get("base_url") is None
    finally:
        if saved:
            os.environ["CHIBI_COMFY_URL"] = saved
        _clear_config_cache()


def test_cloud_config_has_no_local_machine_paths():
    text = (ROOT / "config/environments/cloud.yaml").read_text(encoding="utf-8")
    for bad in ("/home/user", "/Users/", "C:\\", "/tmp/"):
        assert bad not in text, f"path especifico da maquina: {bad}"


# --- runner -----------------------------------------------------------------

if __name__ == "__main__":
    funcs = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = skipped = 0
    for name, fn in funcs:
        if name.startswith("test_integration_") and not _integration_enabled():
            skipped += 1
            print(f"  SKIP  {name} [integration test: sem CHIBI_COMFY_URL]")
            continue
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    total = len(funcs) - skipped
    print(f"\n{total - failed}/{total} passaram" +
          (f" ({skipped} pulados)" if skipped else ""))
    sys.exit(1 if failed else 0)

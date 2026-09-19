"""Medicao de RAM/swap/VRAM durante uma execucao real.

Existe por um motivo concreto: o requisito `ram_gb: 16` do Qwen Q3_K_M e uma
ESTIMATIVA conservadora nossa, nunca medida. O Colab T4 tem ~12.7 GB, entao o
preflight bloqueia — mas nao sabemos se o bloqueio e correto ou pessimista.
Este modulo produz o numero medido que falta para decidir.

Nao e o benchmark oficial e nao decide nada sozinho: coleta amostras,
identifica em qual FASE ocorreu o pico e devolve um veredito
FIT / BORDERLINE / DOES_NOT_FIT / INCONCLUSIVE para leitura humana.

Amostragem em thread daemon, com intervalo configuravel. Toda leitura e
defensiva: um erro de medicao nunca pode derrubar (nem travar) a execucao
que esta sendo medida.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any

GB = 1024 ** 3

# Fases do pipeline. A ordem importa: o relatorio diz em qual delas o
# consumo estourou, que e o que permite decidir entre trocar de runtime e
# trocar o text encoder.
FASE_INICIO = "STARTUP"
FASE_COMFY = "COMFYUI_BOOT"
FASE_MODEL = "MODEL_LOAD"
FASE_TEXT_ENCODER = "TEXT_ENCODER"
FASE_VAE = "VAE"
FASE_WORKFLOW = "WORKFLOW_PREP"
FASE_QUEUE = "QUEUE"
FASE_INFERENCIA = "INFERENCE"
FASE_DESCARGA = "UNLOAD"

FIT = "FIT"
BORDERLINE = "BORDERLINE"
DOES_NOT_FIT = "DOES_NOT_FIT"
INCONCLUSIVE = "INCONCLUSIVE"

SUCESSO = "success"
OOM = "oom"
FREEZE = "freeze"
TIMEOUT = "timeout"


@dataclass
class Amostra:
    t: float
    fase: str
    ram_total_gb: float | None = None
    ram_disponivel_gb: float | None = None
    ram_usada_gb: float | None = None
    rss_gb: float | None = None
    rss_comfyui_gb: float | None = None
    swap_total_gb: float | None = None
    swap_usada_gb: float | None = None
    vram_livre_gb: float | None = None
    vram_usada_gb: float | None = None


def _vram() -> tuple[float | None, float | None]:
    """VRAM (usada, livre) em GB. Timeout obrigatorio.

    `nvidia-smi` sem timeout ja pendurou o notebook uma vez: num runtime em
    swap a chamada pode nao retornar.
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip().split("\n")[0]
        usada, livre = [float(x.strip()) / 1024 for x in out.split(",")[:2]]
        return usada, livre
    except Exception:
        return None, None


class MemoryProbe:
    """Amostra memoria em background enquanto o pipeline roda.

    Uso:
        probe = MemoryProbe(intervalo_s=2.0)
        probe.start()
        probe.fase(FASE_MODEL)
        ...
        probe.stop()
        print(probe.report())
    """

    def __init__(self, intervalo_s: float = 2.0,
                 comfyui_pid: int | None = None,
                 ram_pressure_gb: float = 0.5,
                 on_sample=None) -> None:
        self.intervalo_s = max(0.5, float(intervalo_s))
        self.comfyui_pid = comfyui_pid
        # Abaixo desta RAM disponivel o sistema esta em pressao extrema:
        # registrar em vez de ficar congelado em silencio.
        self.ram_pressure_gb = ram_pressure_gb
        self.on_sample = on_sample

        self.amostras: list[Amostra] = []
        self.eventos: list[dict[str, Any]] = []
        self._fase = FASE_INICIO
        self._marcos: list[tuple[float, str]] = []
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = 0.0
        self.resultado: str | None = None
        self._lock = threading.Lock()

    # -- controle -----------------------------------------------------
    def start(self) -> "MemoryProbe":
        self._t0 = time.time()
        self._marcos.append((0.0, self._fase))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._amostrar()
        return self

    def fase(self, nome: str) -> None:
        """Marca a fase atual. A amostra imediata evita perder um pico curto."""
        with self._lock:
            self._fase = nome
            self._marcos.append((time.time() - self._t0, nome))
        self._amostrar()

    def stop(self, resultado: str | None = None) -> "MemoryProbe":
        self._amostrar()
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=self.intervalo_s * 2 + 5)
        if resultado is not None:
            self.resultado = resultado
        return self

    def __enter__(self) -> "MemoryProbe":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        # Excecao durante a medicao ainda produz relatorio: um OOM e
        # justamente um dos resultados que queremos registrar.
        if exc_type is not None and self.resultado is None:
            nome = getattr(exc_type, "__name__", "").lower()
            texto = str(exc).lower()
            if "outofmemory" in nome or "out of memory" in texto:
                self.resultado = OOM
            elif "timeout" in nome or "timeout" in texto:
                self.resultado = TIMEOUT
        self.stop(self.resultado or (SUCESSO if exc_type is None else None))

    # -- coleta -------------------------------------------------------
    def _loop(self) -> None:
        while not self._parar.is_set():
            self._parar.wait(self.intervalo_s)
            if self._parar.is_set():
                break
            self._amostrar()

    def _amostrar(self) -> None:
        try:
            a = Amostra(t=round(time.time() - self._t0, 2), fase=self._fase)
            try:
                import psutil
                vm = psutil.virtual_memory()
                sw = psutil.swap_memory()
                a.ram_total_gb = vm.total / GB
                a.ram_disponivel_gb = vm.available / GB
                a.ram_usada_gb = (vm.total - vm.available) / GB
                a.swap_total_gb = sw.total / GB
                a.swap_usada_gb = sw.used / GB
                a.rss_gb = psutil.Process().memory_info().rss / GB
                if self.comfyui_pid:
                    try:
                        p = psutil.Process(self.comfyui_pid)
                        total = p.memory_info().rss
                        for f in p.children(recursive=True):
                            try:
                                total += f.memory_info().rss
                            except Exception:
                                pass
                        a.rss_comfyui_gb = total / GB
                    except Exception:
                        a.rss_comfyui_gb = None
            except Exception:
                pass
            a.vram_usada_gb, a.vram_livre_gb = _vram()

            with self._lock:
                self.amostras.append(a)

            if (a.ram_disponivel_gb is not None
                    and a.ram_disponivel_gb < self.ram_pressure_gb):
                self._evento("RAM_PRESSURE", a)
            if self.on_sample:
                try:
                    self.on_sample(a)
                except Exception:
                    pass
        except Exception:
            # Medicao nunca derruba a execucao medida.
            pass

    def _evento(self, tipo: str, a: Amostra) -> None:
        ev = {"tipo": tipo, "t": a.t, "fase": a.fase,
              "ram_disponivel_gb": a.ram_disponivel_gb,
              "swap_usada_gb": a.swap_usada_gb}
        with self._lock:
            if not self.eventos or self.eventos[-1]["tipo"] != tipo:
                self.eventos.append(ev)

    # -- analise ------------------------------------------------------
    def _pico(self, campo: str) -> tuple[float | None, str | None]:
        melhor, fase = None, None
        for a in self.amostras:
            v = getattr(a, campo)
            if v is not None and (melhor is None or v > melhor):
                melhor, fase = v, a.fase
        return melhor, fase

    def _minimo(self, campo: str) -> float | None:
        vals = [getattr(a, campo) for a in self.amostras
                if getattr(a, campo) is not None]
        return min(vals) if vals else None

    def metrics(self) -> dict[str, Any]:
        pico_ram, fase_ram = self._pico("ram_usada_gb")
        pico_rss, fase_rss = self._pico("rss_gb")
        pico_comfy, fase_comfy = self._pico("rss_comfyui_gb")
        pico_swap, fase_swap = self._pico("swap_usada_gb")
        pico_vram, fase_vram = self._pico("vram_usada_gb")

        base_swap = next((a.swap_usada_gb for a in self.amostras
                          if a.swap_usada_gb is not None), None)
        swap_delta = (None if pico_swap is None or base_swap is None
                      else max(0.0, pico_swap - base_swap))

        return {
            "samples": len(self.amostras),
            "interval_s": self.intervalo_s,
            "duration_s": round(self.amostras[-1].t, 1)
            if self.amostras else 0.0,
            "ram_total_gb": self.amostras[0].ram_total_gb
            if self.amostras else None,
            "ram_min_available_gb": self._minimo("ram_disponivel_gb"),
            "ram_peak_used_gb": pico_ram,
            "ram_peak_phase": fase_ram,
            "rss_peak_gb": pico_rss,
            "rss_peak_phase": fase_rss,
            "comfyui_rss_peak_gb": pico_comfy,
            "comfyui_rss_peak_phase": fase_comfy,
            "swap_total_gb": self.amostras[0].swap_total_gb
            if self.amostras else None,
            "swap_peak_used_gb": pico_swap,
            "swap_delta_gb": swap_delta,
            "swap_peak_phase": fase_swap,
            "vram_min_free_gb": self._minimo("vram_livre_gb"),
            "vram_peak_used_gb": pico_vram,
            "vram_peak_phase": fase_vram,
            "phases": [{"t": t, "phase": f} for t, f in self._marcos],
            "events": list(self.eventos),
            "result": self.resultado,
        }

    def verdict(self, margem_borderline_gb: float = 1.5) -> dict[str, Any]:
        """Classifica o resultado. NAO decide o proximo passo.

        A conclusao e sobre CABER, nao sobre qualidade nem sobre qual runtime
        usar — essa escolha e humana.
        """
        m = self.metrics()
        total = m["ram_total_gb"]
        pico = m["ram_peak_used_gb"]
        swap = m["swap_delta_gb"]

        if self.resultado in (OOM, FREEZE, TIMEOUT):
            return {
                "conclusion": DOES_NOT_FIT,
                "reason": f"execucao terminou como '{self.resultado}' na fase "
                          f"{m.get('ram_peak_phase')}.",
                "headroom_gb": None,
            }
        if not self.amostras or total is None or pico is None:
            return {"conclusion": INCONCLUSIVE,
                    "reason": "sem amostras suficientes de memoria.",
                    "headroom_gb": None}
        if self.resultado != SUCESSO:
            return {"conclusion": INCONCLUSIVE,
                    "reason": "a execucao nao foi concluida com sucesso; o "
                              "pico pode nao representar o consumo total.",
                    "headroom_gb": None}

        folga = total - pico
        # Swap usada e evidencia direta de que a RAM nao bastou, mesmo que a
        # execucao tenha terminado.
        if swap is not None and swap > 0.5:
            return {
                "conclusion": DOES_NOT_FIT,
                "reason": f"usou {swap:.1f} GB de swap (pico na fase "
                          f"{m.get('swap_peak_phase')}): a RAM nao bastou, "
                          "ainda que a execucao tenha terminado.",
                "headroom_gb": round(folga, 2),
            }
        if folga < margem_borderline_gb:
            return {
                "conclusion": BORDERLINE,
                "reason": f"coube, mas com apenas {folga:.1f} GB de folga "
                          f"(pico de {pico:.1f} GB na fase "
                          f"{m.get('ram_peak_phase')}).",
                "headroom_gb": round(folga, 2),
            }
        return {
            "conclusion": FIT,
            "reason": f"pico de {pico:.1f} GB com {folga:.1f} GB de folga "
                      f"(fase {m.get('ram_peak_phase')}).",
            "headroom_gb": round(folga, 2),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "ram_diagnostic",
            "note": "Diagnostico de memoria. NAO e o benchmark oficial e nao "
                    "aprova nem reprova o modelo.",
            "metrics": self.metrics(),
            "verdict": self.verdict(),
            "samples": [asdict(a) for a in self.amostras],
        }

    def report(self, titulo: str = "RAM DIAGNOSTIC") -> str:
        m = self.metrics()
        v = self.verdict()

        def g(x):
            return "n/d" if x is None else f"{x:.2f} GB"

        linhas = [
            "=" * 64,
            titulo,
            "=" * 64,
            f"  amostras           : {m['samples']} a cada "
            f"{m['interval_s']}s ({m['duration_s']}s)",
            "",
            f"  RAM total          : {g(m['ram_total_gb'])}",
            f"  RAM min disponivel : {g(m['ram_min_available_gb'])}",
            f"  RAM pico usada     : {g(m['ram_peak_used_gb'])}"
            f"   <- fase {m['ram_peak_phase']}",
            f"  RSS pico (python)  : {g(m['rss_peak_gb'])}"
            f"   <- fase {m['rss_peak_phase']}",
            f"  RSS pico (ComfyUI) : {g(m['comfyui_rss_peak_gb'])}"
            f"   <- fase {m['comfyui_rss_peak_phase']}",
            f"  swap total         : {g(m['swap_total_gb'])}",
            f"  swap pico usada    : {g(m['swap_peak_used_gb'])}"
            f"   (delta {g(m['swap_delta_gb'])})",
            f"  VRAM min livre     : {g(m['vram_min_free_gb'])}",
            f"  VRAM pico usada    : {g(m['vram_peak_used_gb'])}"
            f"   <- fase {m['vram_peak_phase']}",
            "",
            f"  resultado          : {m['result']}",
            f"  CONCLUSAO          : {v['conclusion']}",
            f"    {v['reason']}",
        ]
        if m["events"]:
            linhas.append("")
            linhas.append("  EVENTOS DE PRESSAO DE MEMORIA:")
            for e in m["events"]:
                linhas.append(
                    f"    [{e['t']:.0f}s] {e['tipo']} na fase {e['fase']} — "
                    f"disponivel {g(e['ram_disponivel_gb'])}")
        linhas.append("")
        linhas.append("  Medicao de UMA execucao neste runtime. Nao afirma")
        linhas.append("  determinismo nem substitui o benchmark oficial.")
        linhas.append("=" * 64)
        return "\n".join(linhas)

"""Testes do RAM DIAGNOSTIC.

O ponto central: o veredito tem de dizer DOES_NOT_FIT quando a RAM nao
bastou, INCONCLUSIVE quando nao da para saber, e nunca FIT por omissao —
e essa distincao que vai embasar a decisao entre T4, Colab com mais RAM ou
trocar o text encoder.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import memprobe as mp  # noqa: E402


def _probe(amostras, resultado=mp.SUCESSO, **kw):
    """Probe com amostras injetadas, sem depender da maquina do teste."""
    p = mp.MemoryProbe(**kw)
    p.amostras = [mp.Amostra(**a) for a in amostras]
    p.resultado = resultado
    return p


def test_pico_identifica_a_fase_certa():
    p = _probe([
        dict(t=0, fase=mp.FASE_COMFY, ram_total_gb=12.7, ram_usada_gb=2.0),
        dict(t=2, fase=mp.FASE_MODEL, ram_total_gb=12.7, ram_usada_gb=6.0),
        dict(t=4, fase=mp.FASE_TEXT_ENCODER, ram_total_gb=12.7,
             ram_usada_gb=11.5),
        dict(t=6, fase=mp.FASE_INFERENCIA, ram_total_gb=12.7,
             ram_usada_gb=9.0),
    ])
    m = p.metrics()
    assert m["ram_peak_used_gb"] == 11.5
    assert m["ram_peak_phase"] == mp.FASE_TEXT_ENCODER, (
        "saber QUAL fase estourou e o que permite decidir o proximo passo")


def test_swap_usada_significa_que_nao_coube():
    """Terminar sem erro nao prova que coube: swap e a evidencia."""
    p = _probe([
        dict(t=0, fase=mp.FASE_COMFY, ram_total_gb=12.7, ram_usada_gb=2.0,
             swap_usada_gb=0.0),
        dict(t=4, fase=mp.FASE_TEXT_ENCODER, ram_total_gb=12.7,
             ram_usada_gb=12.4, swap_usada_gb=3.2),
    ])
    v = p.verdict()
    assert v["conclusion"] == mp.DOES_NOT_FIT, v
    assert "swap" in v["reason"]
    assert p.metrics()["swap_delta_gb"] == 3.2


def test_folga_pequena_e_borderline_nao_fit():
    p = _probe([
        dict(t=0, fase=mp.FASE_INFERENCIA, ram_total_gb=12.7,
             ram_usada_gb=12.0, swap_usada_gb=0.0),
    ])
    assert p.verdict()["conclusion"] == mp.BORDERLINE


def test_folga_confortavel_e_fit():
    p = _probe([
        dict(t=0, fase=mp.FASE_INFERENCIA, ram_total_gb=12.7,
             ram_usada_gb=7.0, swap_usada_gb=0.0),
    ])
    v = p.verdict()
    assert v["conclusion"] == mp.FIT
    assert v["headroom_gb"] == 5.7


def test_crash_ou_freeze_nunca_vira_fit():
    for res in (mp.OOM, mp.FREEZE, mp.TIMEOUT):
        p = _probe([dict(t=0, fase=mp.FASE_MODEL, ram_total_gb=12.7,
                         ram_usada_gb=3.0)], resultado=res)
        assert p.verdict()["conclusion"] == mp.DOES_NOT_FIT, res


def test_sem_amostras_e_inconclusivo():
    p = _probe([], resultado=mp.SUCESSO)
    assert p.verdict()["conclusion"] == mp.INCONCLUSIVE
    # Execucao incompleta tambem nao autoriza concluir que cabe.
    p2 = _probe([dict(t=0, fase=mp.FASE_MODEL, ram_total_gb=12.7,
                      ram_usada_gb=3.0)], resultado=None)
    assert p2.verdict()["conclusion"] == mp.INCONCLUSIVE


def test_pressao_de_memoria_vira_evento_registrado():
    """Em vez de congelar em silencio, o estado fica registrado."""
    p = mp.MemoryProbe(intervalo_s=0.5, ram_pressure_gb=999999)
    p.start()
    time.sleep(0.2)
    p.stop(mp.SUCESSO)
    eventos = [e["tipo"] for e in p.metrics()["events"]]
    assert "RAM_PRESSURE" in eventos


def test_medicao_nao_derruba_a_execucao_medida():
    """Erro no coletor nao pode propagar para o pipeline."""
    p = mp.MemoryProbe(intervalo_s=0.5, on_sample=lambda a: 1 / 0)
    p.start()
    time.sleep(0.2)
    p.stop(mp.SUCESSO)
    assert p.metrics()["samples"] >= 1


def test_context_manager_classifica_oom_automaticamente():
    class OutOfMemoryError(RuntimeError):
        pass

    p = mp.MemoryProbe(intervalo_s=0.5)
    try:
        with p:
            raise OutOfMemoryError("CUDA out of memory")
    except OutOfMemoryError:
        pass
    assert p.resultado == mp.OOM
    assert p.verdict()["conclusion"] == mp.DOES_NOT_FIT


def test_nvidia_smi_tem_timeout():
    """Sem timeout, um runtime em swap pendura a coleta — ja aconteceu."""
    import inspect
    src = inspect.getsource(mp._vram)
    assert "timeout=" in src


def test_probe_real_coleta_e_relata():
    p = mp.MemoryProbe(intervalo_s=0.5).start()
    p.fase(mp.FASE_MODEL)
    time.sleep(0.6)
    p.stop(mp.SUCESSO)
    m = p.metrics()
    assert m["samples"] >= 2
    assert m["ram_total_gb"] and m["ram_total_gb"] > 0
    assert m["rss_peak_gb"] and m["rss_peak_gb"] > 0
    fases = [f["phase"] for f in m["phases"]]
    assert mp.FASE_INICIO in fases and mp.FASE_MODEL in fases
    rel = p.report()
    for esperado in ("RAM pico usada", "CONCLUSAO", "swap", "VRAM"):
        assert esperado in rel
    # O relatorio nao pode se vender como benchmark oficial.
    assert "NAO e o benchmark oficial" in p.to_dict()["note"]


def test_dict_serializa_para_json():
    import json
    p = mp.MemoryProbe(intervalo_s=0.5).start()
    time.sleep(0.1)
    p.stop(mp.SUCESSO)
    json.dumps(p.to_dict())


if __name__ == "__main__":
    testes = [(n, f) for n, f in sorted(globals().items())
              if n.startswith("test_") and callable(f)]
    falhas = 0
    for nome, fn in testes:
        try:
            fn()
            print(f"  PASS  {nome}")
        except Exception as exc:
            falhas += 1
            print(f"  FAIL  {nome}: {type(exc).__name__}: {exc}")
    print(f"{len(testes) - falhas}/{len(testes)} passaram")
    sys.exit(1 if falhas else 0)

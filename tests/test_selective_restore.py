"""FASE A (restauracao seletiva) e FASE B (SDXL inpaint mascarado).

As duas invariantes que estes testes existem para proteger:

    outside_mask_pixel_difference == 0
    mask_protected_overlap_pixels == 0

E a regra de conservacao que motivou a fase inteira: **se uma peca ja esta
correta na Run 003, nao substituir.**

Nenhum teste aqui baixa modelo ou usa GPU. O SDXL e exercitado com um
pipeline falso que imita o comportamento REAL que nos preocupa: o VAE
devolvendo a imagem inteira alterada.
"""

import numpy as np
import pytest
import yaml
from PIL import Image

from scripts.chibi import character_correspondence as cc
from scripts.chibi import design_transfer as dt
from scripts.chibi import mask_engine as me
from scripts.chibi import sdxl_inpaint as si
from scripts.chibi import selective_restore as sr

FULL_BODY = "characters/waifu_001/reference/full_body.png"


# ---------------------------------------------------------------------------
# cenario compartilhado: REAL -> correspondencia -> mascaras no espaco CHIBI
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cenario():
    source = dt.load_rgba(FULL_BODY)
    review = me.review_masks(source, character_id="waifu_001", min_area=120)

    # Alvo com proporcao chibi. NAO e a Run 003 (que nao esta versionada):
    # serve para exercitar o codigo, nunca para validar arte.
    a = np.zeros((512, 512, 4), np.uint8)
    a[40:250, 180:340] = (240, 220, 200, 255)
    a[250:430, 200:320] = (60, 60, 70, 255)
    target = Image.fromarray(a)

    sl = cc.apply_overrides(
        cc.derive_landmarks(source),
        cc.load_landmark_overrides("waifu_001")["source"], source="config")
    corr = cc.build_correspondence(sl, cc.derive_landmarks(target))

    shape = np.array(target).shape[:2]
    subj = dt.subject_mask(target)
    prot = np.zeros(shape, bool)
    for m in review.protected.values():
        prot |= cc.transform_mask(m, corr, shape)
    warped = cc.clip_to_target(
        cc.transform_masks(review.garment, corr, shape), subj, prot)

    return {"source": source, "target": target, "corr": corr,
            "source_masks": review.garment, "target_masks": warped,
            "protected": prot, "subject": subj}


# ---------------------------------------------------------------------------
# FASE A — deteccao de deriva
# ---------------------------------------------------------------------------

def test_descritores_sao_invariantes_a_escala():
    """REAL e CHIBI tem tamanhos diferentes; medida em px seria incomparavel."""
    img = dt.load_rgba(FULL_BODY)
    m = np.zeros(np.array(img).shape[:2], bool)
    m[300:700, 300:700] = True
    grande = sr.describe_region(img, m)

    metade = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
    m2 = np.zeros(np.array(metade).shape[:2], bool)
    m2[150:350, 150:350] = True
    pequeno = sr.describe_region(metade, m2)

    for chave in ("gold_presence", "luminance", "saturation"):
        assert abs(grande[chave] - pequeno[chave]) < 0.12, chave


def test_regiao_identica_nao_acusa_deriva():
    img = dt.load_rgba(FULL_BODY)
    m = np.zeros(np.array(img).shape[:2], bool)
    m[300:700, 300:700] = True
    d = sr.detect_drift(img, img, {"x": m}, {"x": m})
    assert d["x"].score == pytest.approx(0.0, abs=1e-9)
    assert not d["x"].drifted
    assert "nao substituir" in d["x"].reason


def test_perda_de_ouro_e_detectada_mesmo_com_score_baixo():
    """Ornamento dourado sumindo e o modo de falha nº1 deste pipeline."""
    a = np.zeros((100, 100, 4), np.uint8)
    a[..., 3] = 255
    a[:, :] = (200, 170, 60, 255)              # dourado
    com_ouro = Image.fromarray(a)
    b = a.copy()
    b[:, :] = (60, 60, 62, 255)                # ouro virou cinza escuro
    sem_ouro = Image.fromarray(b)

    m = np.ones((100, 100), bool)
    d = sr.detect_drift(com_ouro, sem_ouro, {"orn": m}, {"orn": m})
    assert d["orn"].drifted
    assert "ornamento dourado" in d["orn"].reason


def test_regiao_vazia_no_alvo_e_deriva_maxima():
    img = dt.load_rgba(FULL_BODY)
    m = np.zeros(np.array(img).shape[:2], bool)
    m[300:700, 300:700] = True
    vazio = np.zeros((512, 512), bool)
    alvo = Image.new("RGBA", (512, 512), (0, 0, 0, 255))
    d = sr.detect_drift(img, alvo, {"x": m}, {"x": vazio})
    assert d["x"].score == 1.0 and d["x"].drifted


def test_apenas_o_que_derivou_entra_na_restauracao(cenario):
    d = sr.detect_drift(cenario["source"], cenario["target"],
                        cenario["source_masks"], cenario["target_masks"])
    regs = sr.regions_to_restore(d)
    assert regs, "nada foi marcado — deteccao inerte"
    assert len(regs) < len(cenario["source_masks"]), (
        "TUDO foi marcado: isso e substituir a roupa inteira, nao restaurar")
    # ordenado pelo pior caso primeiro
    scores = [d[n].score for n in regs]
    assert scores == sorted(scores, reverse=True)


def test_threshold_alto_nao_restaura_nada(cenario):
    d = sr.detect_drift(cenario["source"], cenario["target"],
                        cenario["source_masks"], cenario["target_masks"],
                        threshold=10.0)
    # so sobra o que dispara a regra do ouro, que e independente do limiar
    for nome in sr.regions_to_restore(d):
        assert "ornamento dourado" in d[nome].reason


# ---------------------------------------------------------------------------
# FASE A — composicao
# ---------------------------------------------------------------------------

def _written(cenario, regs):
    w = np.zeros(cenario["protected"].shape, bool)
    for n in regs:
        if n in cenario["target_masks"]:
            w |= cenario["target_masks"][n] & ~cenario["protected"]
    return w


def test_restauracao_nao_altera_nada_fora_da_mascara(cenario):
    d = sr.detect_drift(cenario["source"], cenario["target"],
                        cenario["source_masks"], cenario["target_masks"])
    regs = sr.regions_to_restore(d)
    res = sr.selective_restore(cenario["target"], cenario["source"],
                               cenario["target_masks"], cenario["corr"],
                               regs, protected=cenario["protected"])
    assert sr.outside_mask_pixel_difference(
        cenario["target"], res.image, _written(cenario, regs)) == 0


def test_restauracao_nunca_toca_regiao_protegida(cenario):
    """Mesmo forcando TODAS as regioes, o protegido continua intacto."""
    todas = list(cenario["target_masks"])
    res = sr.selective_restore(cenario["target"], cenario["source"],
                               cenario["target_masks"], cenario["corr"],
                               todas, protected=cenario["protected"])
    antes = np.array(cenario["target"].convert("RGBA"))
    depois = np.array(res.image.convert("RGBA"))
    mudou = (antes != depois).any(axis=2)
    assert int((mudou & cenario["protected"]).sum()) == 0


def test_pecas_puladas_sao_reportadas(cenario):
    res = sr.selective_restore(cenario["target"], cenario["source"],
                               cenario["target_masks"], cenario["corr"],
                               ["ornamentos"], protected=cenario["protected"])
    assert res.restored == ["ornamentos"]
    assert "torso" in res.skipped and "capa_esquerda" in res.skipped


def test_restaurar_nada_devolve_a_run_003_intacta(cenario):
    res = sr.selective_restore(cenario["target"], cenario["source"],
                               cenario["target_masks"], cenario["corr"],
                               [], protected=cenario["protected"])
    assert np.array_equal(np.array(res.image),
                          np.array(cenario["target"].convert("RGBA")))


# ---------------------------------------------------------------------------
# FASE B — SDXL mascarado
# ---------------------------------------------------------------------------

def test_modelo_registrado_no_models_lock():
    d = yaml.safe_load(open("config/models.lock.yaml"))
    assert si.MODEL["key"] in d["models"], "SDXL nao registrado"
    assert si.MODEL["key"] not in d["rejected"]
    m = d["models"][si.MODEL["key"]]
    assert m["revision"] == si.MODEL["revision"]
    assert m["license"]["verified"] is True
    assert m["weights"]["verified"] is False, "pesos nao foram baixados"


def test_mascara_de_edicao_exclui_protegido(cenario):
    m = si.build_edit_mask(cenario["target_masks"], ["torso", "ornamentos"],
                           protected=cenario["protected"], dilate=3)
    assert int((m & cenario["protected"]).sum()) == 0, (
        "dilatacao invadiu regiao protegida")


def test_plano_falha_se_a_mascara_invadir_protegido(cenario):
    ruim = cenario["protected"].copy()
    with pytest.raises(si.InpaintError):
        si.plan_inpaint(cenario["target"], ruim, ["x"], "p",
                        protected=cenario["protected"])


def test_strength_1_e_rejeitado(cenario):
    m = si.build_edit_mask(cenario["target_masks"], ["torso"],
                           protected=cenario["protected"])
    with pytest.raises(si.InpaintError):
        si.plan_inpaint(cenario["target"], m, ["torso"], "p",
                        params={"strength": 1.0})


def test_regiao_desconhecida_e_erro(cenario):
    with pytest.raises(si.InpaintError):
        si.build_edit_mask(cenario["target_masks"], ["nao_existe"])


class _FakePipe:
    """Imita o comportamento que de fato quebra a invariante.

    O VAE do SDXL e lossy: a imagem volta alterada em TODA a area, nao so
    dentro da mascara. Sem `recompose`, a Run 003 sairia degradada.
    """
    def __init__(self):
        self.chamado = {}

    def __call__(self, **kw):
        self.chamado = kw
        img = kw["image"]
        arr = np.array(img.convert("RGB")).astype(int)
        arr = np.clip(arr + 7, 0, 255).astype(np.uint8)   # ruido global
        class R:
            images = [Image.fromarray(arr, "RGB")]
        return R()


def test_sdxl_preserva_tudo_fora_da_mascara(cenario):
    pipe = _FakePipe()
    m = si.build_edit_mask(cenario["target_masks"], ["torso", "ornamentos"],
                           protected=cenario["protected"])
    plan = si.plan_inpaint(cenario["target"], m, ["torso", "ornamentos"],
                           "restore golden ornaments",
                           protected=cenario["protected"])
    res = si.run_inpaint(pipe, cenario["target"], m, plan)

    antes = np.array(cenario["target"].convert("RGBA"))
    depois = np.array(res.image.convert("RGBA"))
    mudou = (antes != depois).any(axis=2)
    assert int((mudou & ~m).sum()) == 0, (
        "SDXL alterou pixels fora da mascara — recompose falhou")
    assert int((mudou & cenario["protected"]).sum()) == 0


def test_sdxl_recebe_mascara_e_nao_a_imagem_inteira(cenario):
    pipe = _FakePipe()
    m = si.build_edit_mask(cenario["target_masks"], ["torso"],
                           protected=cenario["protected"])
    plan = si.plan_inpaint(cenario["target"], m, ["torso"], "p",
                           protected=cenario["protected"])
    si.run_inpaint(pipe, cenario["target"], m, plan)
    assert "mask_image" in pipe.chamado, "chamou sem mascara"
    assert pipe.chamado["strength"] < 1.0
    mk = np.array(pipe.chamado["mask_image"])
    assert mk.max() == 255 and mk.min() == 0, "mascara nao e binaria"
    assert (mk > 0).sum() < mk.size * 0.5, (
        "mascara cobre a imagem quase toda — isso e redesenhar, nao editar")


def test_recompose_e_exato_fora_da_mascara():
    orig = Image.fromarray(
        np.random.RandomState(0).randint(0, 255, (64, 64, 4), np.uint8), "RGBA")
    ger = Image.fromarray(
        np.random.RandomState(1).randint(0, 255, (64, 64, 4), np.uint8), "RGBA")
    m = np.zeros((64, 64), bool)
    m[20:40, 20:40] = True
    out = np.array(si.recompose(orig, ger, m))
    assert np.array_equal(out[~m], np.array(orig)[~m])
    assert np.array_equal(out[m], np.array(ger)[m])


def test_plano_serializa_para_o_recipe(cenario):
    m = si.build_edit_mask(cenario["target_masks"], ["ornamentos"],
                           protected=cenario["protected"])
    d = si.plan_inpaint(cenario["target"], m, ["ornamentos"], "p",
                        protected=cenario["protected"]).as_dict()
    assert d["model"]["revision"] == si.MODEL["revision"]
    assert d["protected_overlap"] == 0
    assert d["params"]["seed"] == 42

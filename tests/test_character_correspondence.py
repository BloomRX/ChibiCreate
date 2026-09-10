"""Testes da camada de correspondencia REAL <-> CHIBI.

O que estes testes protegem, em ordem de importancia:

1. Landmark ERRADO e pior que landmark AUSENTE. A deteccao por contorno so
   pode emitir o que o contorno sustenta; inventar pescoco/cintura/quadril
   arrasta a transformacao inteira.
2. Correspondencia PARCIAL e um caminho normal, nao uma falha.
3. A mascara transformada nunca encosta em regiao protegida do ALVO.
"""

import numpy as np
import pytest
from PIL import Image

from scripts.chibi import character_correspondence as cc

FULL_BODY = "characters/waifu_001/reference/full_body.png"


# ---------------------------------------------------------------------------
# silhueta
# ---------------------------------------------------------------------------

def test_silhouette_ignora_alpha_retangular():
    """O alpha de full_body.png e um retangulo solido (568 px em toda linha).

    Usa-lo como silhueta da perfil de largura constante 1.0 e landmarks sem
    sentido. `silhouette()` precisa detectar isso e cair para a separacao por
    cor de fundo.
    """
    img = cc.load_rgba(FULL_BODY)
    sil = cc.silhouette(img)
    alpha = np.array(img)[..., 3] > 0
    assert int(alpha.sum()) == 494160          # o retangulo degenerado
    assert int(sil.sum()) == 189667            # o corpo de verdade
    assert sil.sum() < alpha.sum() * 0.5


def test_width_profile_tem_estrutura_nao_constante():
    img = cc.load_rgba(FULL_BODY)
    sil = cc.silhouette(img)
    ls = cc.derive_landmarks(img)
    prof = cc.width_profile(sil, ls.bbox, bins=32)
    assert prof.max() > prof.min() + 0.3, "perfil chapado = silhueta errada"


# ---------------------------------------------------------------------------
# o que a deteccao pode e o que NAO pode afirmar
# ---------------------------------------------------------------------------

def test_derive_nao_inventa_landmarks_internos():
    """Nesta arte o contorno nao sustenta pescoco/cintura/quadril.

    Cabelo longo funde cabeca e ombros; a capa cobre o contorno lateral do
    tronco. Uma versao anterior colocava 'neck' na ponta do chifre e 'waist'
    nas costelas. Estes pontos devem vir de configuracao, nunca de chute.
    """
    ls = cc.derive_landmarks(cc.load_rgba(FULL_BODY))
    for nome in ("neck", "waist", "hip_left", "hip_right",
                 "elbow_left", "wrist_right", "knee_left"):
        assert nome not in ls, f"{nome} foi adivinhado a partir do contorno"


def test_derive_nao_poe_tornozelo_na_barra_do_manto():
    """A barra da capa se divide em dois blocos ao redor dos pes.

    Sem os filtros de largura e simetria, o par (canto do manto, pe) — centros
    relativos 0.253 e 0.495 — vira 'tornozelos'.
    """
    ls = cc.derive_landmarks(cc.load_rgba(FULL_BODY))
    assert "ankle_left" not in ls and "ankle_right" not in ls


def test_derive_emite_os_pontos_defensaveis():
    ls = cc.derive_landmarks(cc.load_rgba(FULL_BODY))
    assert set(ls.names()) == {
        "top_of_head", "silhouette_bottom", "shoulder_left", "shoulder_right"}
    assert ls.normalized("top_of_head")[1] == pytest.approx(0.0, abs=0.01)
    assert ls.normalized("silhouette_bottom")[1] == pytest.approx(1.0, abs=0.01)


def test_extremos_verticais_tem_confianca_maior_que_derivados():
    ls = cc.derive_landmarks(cc.load_rgba(FULL_BODY))
    assert ls["top_of_head"].confidence > ls["shoulder_left"].confidence


# ---------------------------------------------------------------------------
# overrides por personagem
# ---------------------------------------------------------------------------

def test_overrides_da_waifu_completam_os_ausentes():
    img = cc.load_rgba(FULL_BODY)
    ls = cc.apply_overrides(cc.derive_landmarks(img),
                            cc.load_landmark_overrides("waifu_001")["source"])
    for nome in ("neck", "waist", "hip_left", "ankle_right"):
        assert nome in ls
        assert ls[nome].source in ("config", "manual")
    # dentro da caixa do sujeito
    l, t, r, b = ls.bbox
    for nome in ls.names():
        assert l <= ls[nome].x <= r and t <= ls[nome].y <= b


def test_target_da_waifu_esta_vazio_de_proposito():
    """run_003 nao esta versionada; medir seus landmarks aqui seria invencao."""
    assert cc.load_landmark_overrides("waifu_001").get("target") == {}


def test_personagem_sem_arquivo_nao_e_erro():
    assert cc.load_landmark_overrides("personagem_inexistente_xyz") == {}


def test_chave_desconhecida_e_erro():
    ls = cc.LandmarkSet(bbox=(0, 0, 10, 10))
    with pytest.raises(cc.CorrespondenceError):
        cc.apply_overrides(ls, {"terceiro_joelho": {"nx": 0.5, "ny": 0.5}})


def test_override_none_remove_landmark():
    ls = cc.LandmarkSet(bbox=(0, 0, 100, 100))
    ls.add(cc.Landmark("waist", 50, 50))
    assert "waist" not in cc.apply_overrides(ls, {"waist": None})


# ---------------------------------------------------------------------------
# correspondencia parcial e escolha da transformacao
# ---------------------------------------------------------------------------

def _par(nomes_origem, nomes_alvo):
    a = cc.LandmarkSet(bbox=(0, 0, 200, 400))
    b = cc.LandmarkSet(bbox=(0, 0, 100, 120))
    for i, n in enumerate(nomes_origem):
        a.add(cc.Landmark(n, 20 + i * 25, 30 + i * 40))
    for i, n in enumerate(nomes_alvo):
        b.add(cc.Landmark(n, 15 + i * 12, 10 + i * 15))
    return a, b


def test_apenas_landmarks_comuns_viram_pares():
    a, b = _par(["top_of_head", "neck", "waist", "ankle_left"],
                ["top_of_head", "neck", "waist", "wrist_left"])
    c = cc.build_correspondence(a, b)
    assert set(c.pairs) == {"top_of_head", "neck", "waist"}
    assert "ankle_left" in c.as_dict()["diagnostics"]["landmarks_source_only"]


@pytest.mark.parametrize("n,esperado", [(2, "similarity"), (3, "affine")])
def test_degrada_conforme_o_numero_de_pares(n, esperado):
    nomes = ["top_of_head", "neck", "waist", "hip_left"][:n]
    a, b = _par(nomes, nomes)
    assert cc.build_correspondence(a, b, use_bbox_anchors=False).kind == esperado


def test_pares_insuficientes_falha_explicitamente():
    a, b = _par(["top_of_head"], ["top_of_head"])
    with pytest.raises(cc.CorrespondenceError):
        cc.build_correspondence(a, b, use_bbox_anchors=False)


def test_confianca_cresce_com_mais_pares():
    poucos = _par(["top_of_head", "neck", "waist"],
                  ["top_of_head", "neck", "waist"])
    muitos = _par(["top_of_head", "neck", "waist", "hip_left", "ankle_left"],
                  ["top_of_head", "neck", "waist", "hip_left", "ankle_left"])
    c1 = cc.build_correspondence(*poucos, use_bbox_anchors=False)
    c2 = cc.build_correspondence(*muitos, use_bbox_anchors=False)
    assert c2.confidence > c1.confidence
    assert 0.0 <= c1.confidence <= 1.0 and 0.0 <= c2.confidence <= 1.0


# ---------------------------------------------------------------------------
# transformacao de mascara
# ---------------------------------------------------------------------------

def _alvo_chibi():
    """Alvo sintetico com proporcao chibi: cabeca grande, corpo curto."""
    a = np.zeros((512, 512, 4), np.uint8)
    a[40:250, 180:340] = (240, 220, 200, 255)
    a[250:430, 200:320] = (60, 60, 70, 255)
    img = Image.fromarray(a)
    ls = cc.LandmarkSet(bbox=(180, 40, 340, 430))
    pontos = {"top_of_head": (0.5, 0.0), "chin": (0.5, 0.52),
              "neck": (0.5, 0.56), "shoulder_left": (0.20, 0.62),
              "shoulder_right": (0.80, 0.62), "waist": (0.5, 0.80),
              "silhouette_bottom": (0.5, 1.0)}
    l, t, r, b = ls.bbox
    for n, (nx, ny) in pontos.items():
        ls.add(cc.Landmark(n, l + nx * (r - l), t + ny * (b - t),
                           confidence=0.7, source="config"))
    cabeca = np.zeros((512, 512), bool)
    cabeca[40:250, 180:340] = True
    return img, ls, cabeca


def _corr_real_para_chibi():
    src = cc.load_rgba(FULL_BODY)
    sl = cc.apply_overrides(cc.derive_landmarks(src),
                            cc.load_landmark_overrides("waifu_001")["source"])
    tgt, tl, cabeca = _alvo_chibi()
    return src, tgt, cc.build_correspondence(sl, tl), cabeca


def test_mascara_transformada_cai_no_espaco_do_alvo():
    src, tgt, corr, _ = _corr_real_para_chibi()
    m = np.zeros(src.size[::-1], bool)
    m[400:600, 350:650] = True
    out = cc.transform_mask(m, corr, (512, 512))
    assert out.shape == (512, 512)
    assert out.any(), "a mascara sumiu na transformacao"
    # a chibi e menor: a area precisa encolher, nao crescer
    assert out.sum() < m.sum()


def test_clip_zera_invasao_de_regiao_protegida():
    """Criterio da diretiva: mask_protected_overlap_pixels == 0 no alvo."""
    src, tgt, corr, cabeca = _corr_real_para_chibi()
    m = np.zeros(src.size[::-1], bool)
    m[150:600, 300:700] = True          # sobe ate a cabeca de proposito
    out = cc.transform_mask(m, corr, (512, 512))
    subj = np.array(tgt)[..., 3] > 0
    clipped = cc.clip_to_target({"torso": out}, subj, cabeca)["torso"]
    assert int((clipped & cabeca).sum()) == 0
    assert int((clipped & ~subj).sum()) == 0, "vazou para fora do personagem"
    assert clipped.any()


def test_recipe_registra_a_transformacao():
    _, _, corr, _ = _corr_real_para_chibi()
    d = corr.as_dict()
    assert d["kind"] in {"tps", "affine", "similarity"}
    assert d["n_pairs"] == len(d["pairs"])
    assert 0.0 <= d["confidence"] <= 1.0
    for chave in ("source_landmarks", "target_landmarks",
                  "source_bbox", "target_bbox", "diagnostics"):
        assert chave in d


def test_visualizacoes_saem_sem_erro():
    src, tgt, corr, _ = _corr_real_para_chibi()
    ls = cc.derive_landmarks(src)
    assert cc.draw_landmarks(src, ls).size == src.size
    lado = cc.draw_correspondence(src, tgt, corr)
    assert lado.width == src.width + tgt.width

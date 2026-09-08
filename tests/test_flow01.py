"""Testes do FLOW 01 (Fase 2) e dos modulos imaging/palette.

Nao dependem de rede, GPU ou modelo baixado. Usam fixtures sinteticas geradas
em tempo de execucao e um repositorio temporario, para nao sujar o real.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chibi import config, flow01, imaging, palette, paths  # noqa: E402
from chibi.hashing import sha256_file  # noqa: E402
from chibi.imaging import BBox  # noqa: E402


# --- fixtures ---------------------------------------------------------------

def make_character_art(with_alpha: bool = True, size=(700, 1000)) -> Image.Image:
    """Personagem esquematica com regioes de cor distintas e verificaveis."""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0) if with_alpha else (20, 120, 40, 255))
    d = ImageDraw.Draw(img)
    cx = w // 2
    d.ellipse((cx - 150, 75, cx + 150, 390), fill=(255, 90, 140, 255))    # cabelo
    d.ellipse((cx - 105, 130, cx + 105, 350), fill=(255, 224, 196, 255))  # rosto
    d.ellipse((cx - 65, 215, cx - 25, 255), fill=(40, 190, 220, 255))     # olho
    d.ellipse((cx + 25, 215, cx + 65, 255), fill=(40, 190, 220, 255))
    d.polygon([(cx - 130, 380), (cx + 130, 380), (cx + 165, 750),
               (cx - 165, 750)], fill=(60, 80, 200, 255))                 # roupa
    d.rectangle((cx - 165, 750, cx - 30, 950), fill=(35, 45, 120, 255))   # pernas
    d.rectangle((cx + 30, 750, cx + 165, 950), fill=(35, 45, 120, 255))
    return img


def make_repo(tmp: Path, character_id: str = "t01", with_alpha: bool = True) -> Path:
    """Repositorio temporario minimo com uma personagem pronta para o flow01."""
    for name in ("config", "styles/chibi"):
        (tmp / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths.PROJECT_CONFIG, tmp / "config/project.yaml")
    shutil.copy2(paths.QUALITY_GATES, tmp / "config/quality_gates.yaml")
    shutil.copy2(paths.MODELS_LOCK, tmp / "config/models.lock.yaml")
    shutil.copy2(paths.CHIBI_STYLE_DIR / "style.yaml", tmp / "styles/chibi/style.yaml")

    cdir = tmp / "characters" / character_id
    (cdir / "source").mkdir(parents=True)
    (cdir / "reference").mkdir(parents=True)
    make_character_art(with_alpha).save(cdir / "source" / "splash.png")
    (cdir / "character.yaml").write_text(
        f"id: {character_id}\n"
        f'display_name: "Teste"\n'
        "difficulty:\n  rating: null\n  reasons: []\n"
        "identity_anchors: []\n"
        "reference_roles: {}\n"
        "reference_regions: {}\n",
        encoding="utf-8",
    )
    return cdir


class TempRepo:
    """Redireciona os paths do modulo para um repo temporario."""

    def __init__(self, with_alpha: bool = True, character_id: str = "t01"):
        self.with_alpha = with_alpha
        self.character_id = character_id

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cdir = make_repo(self.root, self.character_id, self.with_alpha)
        self._saved = (paths.ROOT, paths.CHARACTERS_DIR, paths.CHIBI_STYLE_DIR,
                       paths.PROJECT_CONFIG, paths.QUALITY_GATES)
        paths.ROOT = self.root
        paths.CHARACTERS_DIR = self.root / "characters"
        paths.CHIBI_STYLE_DIR = self.root / "styles" / "chibi"
        return self

    def __exit__(self, *exc):
        (paths.ROOT, paths.CHARACTERS_DIR, paths.CHIBI_STYLE_DIR,
         paths.PROJECT_CONFIG, paths.QUALITY_GATES) = self._saved
        self._tmp.cleanup()
        return False


# --- imaging ----------------------------------------------------------------

def test_bbox_geometry():
    b = BBox(10, 20, 110, 220)
    assert (b.width, b.height) == (100, 200)
    assert b.expand(5, (200, 300)).as_tuple() == (5, 15, 115, 225)
    assert b.expand(50, (200, 300)).left == 0          # nao passa do limite
    sq = b.to_square((200, 300))
    assert sq.width == sq.height


def test_subject_bbox_finds_content():
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((20, 30, 59, 79), fill=(255, 0, 0, 255))
    bbox = imaging.subject_bbox(img)
    assert bbox.as_tuple() == (20, 30, 60, 80)


def test_subject_bbox_none_when_empty():
    assert imaging.subject_bbox(Image.new("RGBA", (50, 50), (0, 0, 0, 0))) is None


def test_normalize_canvas_and_anchor():
    img = make_character_art()
    out, tf = imaging.normalize(img, (1024, 1024),
                                subject_height_ratio=0.85, floor_margin_ratio=0.05)
    assert out.size == (1024, 1024)
    assert out.mode == "RGBA"
    bbox = imaging.subject_bbox(out)
    # sujeito ocupa ~85% da altura
    assert 0.80 <= bbox.height / 1024 <= 0.90
    # centrado horizontalmente (tolerancia de 2%)
    assert abs((bbox.left + bbox.right) / 2 - 512) < 20
    assert tf["canvas"] == [1024, 1024]
    assert tf["resample"] == "lanczos"


def test_normalize_is_deterministic():
    img = make_character_art()
    a, _ = imaging.normalize(img, (512, 512))
    b, _ = imaging.normalize(img, (512, 512))
    assert np.array_equal(np.array(a), np.array(b))


def test_normalize_rejects_empty_image():
    try:
        imaging.normalize(Image.new("RGBA", (100, 100), (0, 0, 0, 0)), (512, 512))
    except imaging.ImagingError:
        pass
    else:
        raise AssertionError("deveria recusar imagem vazia")


def test_fit_within_preserves_ratio_and_never_upscales():
    img = Image.new("RGBA", (400, 800))
    out = imaging.fit_within(img, 200)
    assert out.size == (100, 200)
    small = Image.new("RGBA", (50, 60))
    assert imaging.fit_within(small, 200).size == (50, 60)


def test_alpha_stats():
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((10, 10, 49, 49), fill=(255, 0, 0, 255))
    stats = imaging.alpha_stats(img)
    assert abs(stats["opaque_ratio"] - 0.16) < 0.01
    assert stats["touches_edge"] is False

    edge = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    assert imaging.alpha_stats(edge)["touches_edge"] is True


def test_has_alpha_detection():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        make_character_art(True).save(tmp / "a.png")
        make_character_art(False).convert("RGB").save(tmp / "b.png")
        assert imaging.has_alpha(tmp / "a.png") is True
        assert imaging.has_alpha(tmp / "b.png") is False


def test_save_png_is_atomic():
    """Nenhum .tmp deve sobrar apos a escrita."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "sub" / "x.png"
        imaging.save_png(Image.new("RGBA", (10, 10)), out)
        assert out.is_file()
        assert not list(Path(tmpdir).rglob("*.tmp"))


# --- palette ----------------------------------------------------------------

def test_rgb_to_lab_known_values():
    """Valores de referencia conhecidos para sRGB -> CIELAB (D65)."""
    white = palette.rgb_to_lab(np.array([[255, 255, 255]]))[0]
    assert abs(white[0] - 100) < 0.5 and abs(white[1]) < 0.5 and abs(white[2]) < 0.5

    black = palette.rgb_to_lab(np.array([[0, 0, 0]]))[0]
    assert abs(black[0]) < 0.5

    red = palette.rgb_to_lab(np.array([[255, 0, 0]]))[0]
    assert abs(red[0] - 53.24) < 1.0
    assert abs(red[1] - 80.09) < 1.0


def test_delta_e_zero_for_identical():
    lab = palette.rgb_to_lab(np.array([[120, 60, 200]]))[0]
    assert palette.delta_e(lab, lab) == 0.0


def test_palette_extract_finds_dominant_colors():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "a.png"
        img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, 199, 99), fill=(255, 0, 0, 255))
        d.rectangle((0, 100, 199, 199), fill=(0, 0, 255, 255))
        img.save(p)

        result = palette.extract(p, n_colors=4)
        assert result["n_colors"] >= 2
        hexes = [c["hex"] for c in result["colors"][:2]]
        assert any(h.startswith("#F") or h.startswith("#E") for h in hexes)  # vermelho
        assert sum(c["weight"] for c in result["colors"]) > 0.99


def test_palette_ignores_transparent_pixels():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "a.png"
        img = Image.new("RGBA", (100, 100), (0, 255, 0, 0))   # verde TRANSPARENTE
        ImageDraw.Draw(img).rectangle((40, 40, 59, 59), fill=(255, 0, 0, 255))
        img.save(p)
        result = palette.extract(p, n_colors=3)
        # o verde transparente nao pode aparecer
        for color in result["colors"]:
            assert color["rgb"][1] < 200 or color["rgb"][0] > 200


def test_palette_is_deterministic():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "a.png"
        make_character_art().save(p)
        a = palette.extract(p, n_colors=6)
        b = palette.extract(p, n_colors=6)
        assert [c["hex"] for c in a["colors"]] == [c["hex"] for c in b["colors"]]


def test_palette_compare_identical_is_zero():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "a.png"
        make_character_art().save(p)
        pal = palette.extract(p, n_colors=5)
        cmp = palette.compare(pal, pal)
        assert cmp["comparable"] is True
        assert cmp["mean_distance"] < 0.01


def test_palette_compare_detects_drift():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        a = tmp / "a.png"
        b = tmp / "b.png"
        Image.new("RGBA", (60, 60), (255, 0, 0, 255)).save(a)
        Image.new("RGBA", (60, 60), (0, 0, 255, 255)).save(b)
        cmp = palette.compare(palette.extract(a, n_colors=2),
                              palette.extract(b, n_colors=2))
        assert cmp["mean_distance"] > 50   # vermelho vs azul: drift enorme


def test_palette_empty_image():
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "a.png"
        Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(p)
        assert palette.extract(p)["n_colors"] == 0


# --- flow01 -----------------------------------------------------------------

def test_flow01_produces_expected_outputs():
    with TempRepo() as repo:
        result = flow01.run("t01")
        ref = repo.cdir / "reference"
        for name in ("full_body.png", "face.png", "hair.png", "outfit.png",
                     "palette.json", "sheet.png", "reference.metadata.json"):
            assert (ref / name).is_file(), f"faltando {name}"
        assert result.primary_source == "splash.png"


def test_flow01_never_touches_source():
    with TempRepo() as repo:
        src = repo.cdir / "source" / "splash.png"
        before = sha256_file(src)
        flow01.run("t01")
        assert sha256_file(src) == before, "source/ foi modificado!"
        assert len(list((repo.cdir / "source").iterdir())) == 1


def test_flow01_is_deterministic():
    with TempRepo() as repo:
        flow01.run("t01")
        h1 = sha256_file(repo.cdir / "reference" / "full_body.png")
        flow01.run("t01", force=True)
        h2 = sha256_file(repo.cdir / "reference" / "full_body.png")
        assert h1 == h2


def test_flow01_refuses_overwrite_without_force():
    with TempRepo():
        flow01.run("t01")
        try:
            flow01.run("t01")
        except flow01.Flow01Error as exc:
            assert "force" in str(exc)
        else:
            raise AssertionError("deveria recusar sobrescrita")


def test_flow01_normalized_canvas_matches_config():
    with TempRepo() as repo:
        flow01.run("t01")
        with Image.open(repo.cdir / "reference" / "full_body.png") as img:
            assert img.size == (config.get("resolution.master.width"),
                                config.get("resolution.master.height"))
            assert img.mode == "RGBA"


def test_flow01_metadata_hashes_are_correct():
    with TempRepo() as repo:
        flow01.run("t01")
        meta = json.loads(
            (repo.cdir / "reference" / "reference.metadata.json").read_text()
        )
        assert meta["deterministic"] is True
        assert meta["flow"] == "01_character_reference"
        assert len(meta["outputs"]) >= 6
        for output in meta["outputs"]:
            path = repo.cdir / "reference" / output["filename"]
            assert path.is_file()
            assert sha256_file(path) == output["sha256"]
        src = repo.cdir / "source" / meta["primary_source"]["filename"]
        assert sha256_file(src) == meta["primary_source"]["sha256"]


def test_flow01_warns_when_source_has_no_alpha():
    with TempRepo(with_alpha=False):
        result = flow01.run("t01")
        assert any("alpha" in w.lower() for w in result.warnings)
        assert any("HUMAN REVIEW REQUIRED" in h for h in result.human_review)


def test_flow01_always_flags_heuristic_crops():
    """Recortes heuristicos NUNCA podem passar sem sinalizar revisao humana."""
    with TempRepo():
        result = flow01.run("t01")
        assert any("HEURISTICOS" in h for h in result.human_review)


def test_flow01_updates_character_yaml_preserving_content():
    with TempRepo() as repo:
        flow01.run("t01")
        text = (repo.cdir / "character.yaml").read_text()
        assert "full_body: full_body.png" in text
        assert "face: face.png" in text
        assert "identity_anchors:" in text     # conteudo anterior preservado
        assert "difficulty:" in text


def test_flow01_respects_region_overrides():
    with TempRepo() as repo:
        yaml_path = repo.cdir / "character.yaml"
        yaml_path.write_text(
            yaml_path.read_text().replace(
                "reference_regions: {}",
                "reference_regions:\n"
                "  face:\n    top: 0.0\n    bottom: 0.5\n"
                "    left: 0.0\n    right: 1.0\n",
            ),
            encoding="utf-8",
        )
        flow01.run("t01", force=True)
        meta = json.loads(
            (repo.cdir / "reference" / "reference.metadata.json").read_text()
        )
        assert "face" in json.dumps(meta)


def test_flow01_missing_character():
    with TempRepo():
        try:
            flow01.run("nao_existe")
        except flow01.Flow01Error as exc:
            assert "nao existe" in str(exc)
        else:
            raise AssertionError("deveria falhar")


def test_flow01_no_source_art():
    with TempRepo() as repo:
        (repo.cdir / "source" / "splash.png").unlink()
        try:
            flow01.run("t01")
        except flow01.Flow01Error as exc:
            assert "source" in str(exc).lower()
        else:
            raise AssertionError("deveria falhar sem arte-fonte")


def test_pick_primary_source_is_mechanical():
    """Criterio de selecao e area em pixels — nunca estetico."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        Image.new("RGBA", (100, 100)).save(tmp / "small.png")
        Image.new("RGBA", (900, 900)).save(tmp / "big.png")
        sources = sorted(tmp.glob("*.png"))
        assert flow01.pick_primary_source(sources).name == "big.png"
        assert flow01.pick_primary_source(sources, "small.png").name == "small.png"

        try:
            flow01.pick_primary_source(sources, "inexistente.png")
        except flow01.Flow01Error:
            pass
        else:
            raise AssertionError("deveria falhar com source inexistente")


def test_weapon_has_no_heuristic():
    """'weapon' nao pode ter recorte inventado — posicao varia demais."""
    assert "weapon" not in flow01.DEFAULT_REGIONS
    assert "weapon" in flow01.MANUAL_REGIONS


# --- licenciamento (correcoes administrativas) ------------------------------

def test_controlnet_license_verified():
    ok, why = config.commercially_usable("qwen_image_controlnet_union")
    assert ok is True, why
    entry = config.model("qwen_image_controlnet_union")
    assert entry["license"]["spdx"] == "Apache-2.0"
    assert entry["revision"] == "b13036f066d6dee7c20513e263d3d673055e9de8"
    assert entry["license"]["verified_on"] == "2026-09-08"
    assert config.license_caveat("qwen_image_controlnet_union")  # conflito registrado


def test_birefnet_license_verified():
    ok, why = config.commercially_usable("birefnet")
    assert ok is True, why
    entry = config.model("birefnet")
    assert entry["license"]["spdx"] == "MIT"
    assert entry["revision"] == "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"
    assert "github.com/ZhengPeng7/BiRefNet" in entry["license"]["source_url"]


def test_unverified_models_still_refused():
    for key in ("qwen_image_edit_2511", "real_esrgan_anime_6b"):
        ok, _ = config.commercially_usable(key)
        assert ok is False, f"{key} nao foi verificado, nao pode passar"


def test_no_weights_are_downloaded():
    """Licenca verificada NAO significa pesos baixados."""
    for key in config.models_lock()["models"]:
        ok, _ = config.weights_available(key)
        assert ok is False, f"{key}: pesos nao deveriam estar marcados como baixados"
        assert config.executable(key)[0] is False


# --- runner standalone ------------------------------------------------------

if __name__ == "__main__":
    funcs = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in funcs:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} passaram")
    sys.exit(1 if failed else 0)

"""FLOW 01 — CHARACTER REFERENCE.

    source art -> normalizacao -> isolamento -> identity kit -> reference sheet

Este flow e DETERMINISTICO: nao usa IA generativa, nao inventa conteudo, nao
tem aleatoriedade. Roda inteiramente na maquina local e produz sempre o mesmo
resultado para a mesma entrada.

O que ele NAO faz (por decisao, ver AGENTS.md §2):
  - nao inventa descricao da personagem
  - nao inventa pose ou design
  - nao gera arte nova
  - nao escolhe qual arte-fonte e "melhor"

Os recortes do identity kit sao HEURISTICOS (fracoes da caixa do sujeito) e
por isso sempre marcados [HUMAN REVIEW REQUIRED]. Eles servem como ponto de
partida para o humano corrigir, nao como verdade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from . import config, imaging, palette, paths
from .hashing import sha256_file
from .imaging import BBox, ImagingError

#: Recortes heuristicos do identity kit, em fracoes da CAIXA DO SUJEITO.
#: Estes valores sao um ponto de partida razoavel para arte de personagem em
#: pose frontal de corpo inteiro. [TEST REQUIRED] validar com arte real.
#: `square: false` preserva a proporcao da regiao — necessario para 'outfit',
#: que e alto e estreito e ficaria cortado se forcado a quadrado.
DEFAULT_REGIONS: dict[str, dict[str, Any]] = {
    "face":   {"top": 0.02, "bottom": 0.20, "left": 0.20, "right": 0.80, "square": True},
    "hair":   {"top": 0.00, "bottom": 0.28, "left": 0.10, "right": 0.90, "square": True},
    # left/right/bottom cobrem a caixa inteira: em personagens com manto, capa
    # ou saia longa a silhueta encosta nas bordas da propria caixa do sujeito.
    # Medido em waifu_001: silhueta de 0.000 a 0.998 nos dois eixos; as margens
    # antigas (0.05/0.95) cortavam 4.81% da silhueta na base — a barra do manto
    # e a ponta dos pes. Ver GATE 2.1 em docs/decisions/ADR-005.
    "outfit": {"top": 0.18, "bottom": 1.0, "left": 0.0, "right": 1.0, "square": False},
}

#: 'weapon' NAO tem heuristica: a posicao de uma arma varia demais entre
#: personagens. Deve ser recortada manualmente pelo humano e declarada em
#: character.yaml. Inventar um recorte aqui seria adivinhacao.
MANUAL_REGIONS = ("weapon", "accessory")

CROP_SIZE = 512


class Flow01Error(RuntimeError):
    pass


@dataclass
class Flow01Result:
    """Resultado da execucao, para relatorio e testes."""

    character_id: str
    primary_source: str
    outputs: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    human_review: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_output(self, path: Path) -> None:
        self.outputs.append(path)


# ---------------------------------------------------------------------------
# selecao da arte-fonte
# ---------------------------------------------------------------------------

def list_sources(character_id: str) -> list[Path]:
    cp = paths.CharacterPaths(character_id)
    if not cp.source.is_dir():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(
        p for p in cp.source.iterdir() if p.is_file() and p.suffix.lower() in exts
    )


def pick_primary_source(sources: list[Path], explicit: str | None = None) -> Path:
    """Escolhe a arte-fonte principal.

    Criterio deliberadamente MECANICO (maior area em pixels), nunca estetico:
    o agente nao julga qual arte e melhor (AGENTS.md §2). Se o humano quiser
    outra, passa --source explicitamente.
    """
    if not sources:
        raise Flow01Error(
            "nenhuma arte em source/. Coloque a splash/concept art e rode de novo."
        )
    if explicit:
        for candidate in sources:
            if candidate.name == explicit:
                return candidate
        raise Flow01Error(
            f"source '{explicit}' nao encontrada. Disponiveis: "
            + ", ".join(s.name for s in sources)
        )

    def area(path: Path) -> int:
        with Image.open(path) as img:
            return img.width * img.height

    return max(sources, key=area)


# ---------------------------------------------------------------------------
# etapas
# ---------------------------------------------------------------------------

def _isolate(img: Image.Image, source: Path, result: Flow01Result) -> Image.Image:
    """Garante alpha utilizavel.

    Se a arte-fonte ja tem alpha, usamos o que existe — e sempre melhor que
    qualquer segmentacao automatica. Se nao tem, sinalizamos: o FLOW 01 NAO
    remove fundo automaticamente nesta fase, porque isso exigiria o BiRefNet
    (pesos nao baixados) e produziria resultado que precisa de revisao humana
    de qualquer forma.
    """
    if imaging.has_alpha(source):
        result.metadata["alpha_origin"] = "arte-fonte (preservado)"
        return img

    result.metadata["alpha_origin"] = "ausente na fonte"
    result.warnings.append(
        f"'{source.name}' nao possui canal alpha — fundo NAO foi removido."
    )
    result.human_review.append(
        "[HUMAN REVIEW REQUIRED] A arte-fonte nao tem transparencia. Opcoes: "
        "(a) fornecer versao com alpha, ou (b) habilitar isolamento por "
        "BiRefNet (requer baixar os pesos; ver 'chibi models'). "
        "O reference sheet foi gerado com o fundo original."
    )
    return img


def _extract_regions(
    normalized: Image.Image,
    meta: dict,
    result: Flow01Result,
    out_dir: Path,
) -> dict[str, str]:
    """Recorta as regioes heuristicas do identity kit."""
    produced: dict[str, str] = {}

    regions = dict(DEFAULT_REGIONS)
    for name, override in (meta.get("reference_regions") or {}).items():
        if isinstance(override, dict) and {"top", "bottom"} <= set(override):
            regions[name] = override
            result.metadata.setdefault("region_overrides", []).append(name)

    for name, spec in regions.items():
        frac = {k: v for k, v in spec.items() if k != "square"}
        square = bool(spec.get("square", True))
        try:
            bbox = imaging.region_by_fraction(normalized, **frac)
            crop = imaging.crop_region(
                normalized, bbox, size=CROP_SIZE if square else None, square=square
            )
            if not square:
                crop = imaging.fit_within(crop, CROP_SIZE)
        except ImagingError as exc:
            result.warnings.append(f"regiao '{name}' nao pode ser recortada: {exc}")
            continue

        path = imaging.save_png(crop, out_dir / f"{name}.png")
        result.add_output(path)
        produced[name] = path.name

    if produced:
        result.human_review.append(
            "[HUMAN REVIEW REQUIRED] Os recortes "
            f"({', '.join(sorted(produced))}) sao HEURISTICOS, baseados em "
            "fracoes da caixa do sujeito. Confira cada um e, se estiver errado, "
            "ajuste 'reference_regions' em character.yaml e rode o flow de novo."
        )

    for name in MANUAL_REGIONS:
        target = out_dir / f"{name}.png"
        if target.is_file():
            produced[name] = target.name
            result.metadata.setdefault("manual_regions_found", []).append(name)

    return produced


def _build_sheet(
    normalized: Image.Image,
    crops: dict[str, Path],
    palette_data: dict,
) -> Image.Image:
    """Monta o reference sheet: sujeito + recortes + faixa de paleta.

    E um documento de CONSULTA para o humano e de entrada para o FLOW 02.
    Fundo cinza medio para que tanto areas claras quanto escuras fiquem
    legiveis.
    """
    bg = (54, 54, 60, 255)
    pad = 24
    main_h = 768
    strip = 160
    swatch_h = 64

    ratio = normalized.width / normalized.height
    main_w = max(1, int(main_h * ratio))
    main = normalized.resize((main_w, main_h), imaging.LANCZOS)

    n_crops = max(1, len(crops))
    crops_w = n_crops * strip + (n_crops - 1) * pad

    width = pad + main_w + pad + max(crops_w, 320) + pad
    height = pad + main_h + pad + swatch_h + pad

    sheet = Image.new("RGBA", (width, height), bg)

    # xadrez sutil atras do sujeito, para tornar a transparencia visivel
    checker = Image.new("RGBA", (main_w, main_h), (72, 72, 78, 255))
    dark = Image.new("RGBA", (16, 16), (60, 60, 66, 255))
    for y in range(0, main_h, 16):
        for x in range(0, main_w, 16):
            if (x // 16 + y // 16) % 2 == 0:
                checker.alpha_composite(dark, (x, y))
    sheet.alpha_composite(checker, (pad, pad))
    sheet.alpha_composite(main, (pad, pad))

    x = pad + main_w + pad
    y = pad
    row_h = 0
    for _, path in sorted(crops.items()):
        with Image.open(path) as crop_img:
            thumb = imaging.fit_within(crop_img.convert("RGBA"), strip)
        if x + thumb.width > width - pad and x > pad + main_w + pad:
            x = pad + main_w + pad
            y += row_h + pad
            row_h = 0
        if y + thumb.height > pad + main_h:
            break
        sheet.alpha_composite(thumb, (x, y))
        x += thumb.width + pad
        row_h = max(row_h, thumb.height)

    # faixa de paleta na base, largura proporcional ao peso de cada cor
    colors = palette_data.get("colors", [])
    if colors:
        sy = height - pad - swatch_h
        sx = pad
        avail = width - 2 * pad
        for color in colors:
            w = max(8, int(avail * color.get("weight", 1 / len(colors))))
            swatch = Image.new("RGBA", (w, swatch_h), tuple(color["rgb"]) + (255,))
            sheet.alpha_composite(swatch, (sx, sy))
            sx += w
            if sx >= width - pad:
                break

    return sheet


# ---------------------------------------------------------------------------
# orquestracao
# ---------------------------------------------------------------------------

def run(
    character_id: str,
    *,
    source_name: str | None = None,
    force: bool = False,
) -> Flow01Result:
    """Executa o FLOW 01 completo para uma personagem."""
    cp = paths.CharacterPaths(character_id)
    if not cp.exists():
        raise Flow01Error(
            f"personagem '{character_id}' nao existe. "
            f"Rode: chibi character new {character_id}"
        )

    meta = yaml.safe_load(cp.character_yaml.read_text(encoding="utf-8")) or {}

    sources = list_sources(character_id)
    primary = pick_primary_source(sources, source_name)

    result = Flow01Result(character_id=character_id, primary_source=primary.name)

    if cp.reference.is_dir() and any(
        p.suffix == ".png" for p in cp.reference.iterdir()
    ) and not force:
        raise Flow01Error(
            "reference/ ja contem arquivos. Use --force para sobrescrever "
            "(a arte em source/ nunca e tocada)."
        )

    cp.reference.mkdir(parents=True, exist_ok=True)

    # 1. carregar e isolar
    img = imaging.load_rgba(primary)
    img = _isolate(img, primary, result)

    # 2. normalizar para o canvas canonico
    canvas = (
        int(config.get("resolution.master.width", 1024)),
        int(config.get("resolution.master.height", 1024)),
    )
    style = _load_style()
    normalized, transform = imaging.normalize(
        img,
        canvas,
        subject_height_ratio=float(
            style.get("master_canvas", {}).get("subject_height_ratio", 0.85)
        ),
        floor_margin_ratio=float(
            style.get("master_canvas", {}).get("floor_margin_ratio", 0.05)
        ),
    )
    normalized_path = imaging.save_png(normalized, cp.reference / "full_body.png")
    result.add_output(normalized_path)
    result.metadata["normalization"] = transform

    # 3. identity kit
    produced = _extract_regions(normalized, meta, result, cp.reference)

    # 4. paleta (da imagem normalizada: so pixels do sujeito)
    palette_data = palette.extract(
        normalized_path,
        n_colors=int(
            config.quality_gates()
            .get("gates", {})
            .get("PALETTE_VALID", {})
            .get("params", {})
            .get("n_clusters", 8)
        ),
    )
    palette_path = cp.reference / "palette.json"
    _write_json(palette_path, palette_data)
    result.add_output(palette_path)

    # 5. reference sheet
    crop_paths = {
        name: cp.reference / filename
        for name, filename in produced.items()
        if (cp.reference / filename).is_file()
    }
    sheet = _build_sheet(normalized, crop_paths, palette_data)
    sheet_path = imaging.save_png(sheet, cp.reference / "sheet.png")
    result.add_output(sheet_path)

    # 6. metadata com hashes de tudo
    metadata = _build_metadata(
        cp, primary, sources, normalized_path, produced, transform, result
    )
    meta_path = cp.reference / "reference.metadata.json"
    _write_json(meta_path, metadata)
    result.add_output(meta_path)
    result.metadata["reference_roles"] = metadata["reference_roles"]

    # 7. registrar papeis no character.yaml (sem tocar em nada mais)
    _update_character_yaml(cp.character_yaml, metadata["reference_roles"])

    return result


def _load_style() -> dict:
    style_path = paths.CHIBI_STYLE_DIR / "style.yaml"
    if not style_path.is_file():
        return {}
    return yaml.safe_load(style_path.read_text(encoding="utf-8")) or {}


def _build_metadata(
    cp: paths.CharacterPaths,
    primary: Path,
    sources: list[Path],
    normalized_path: Path,
    produced: dict[str, str],
    transform: dict,
    result: Flow01Result,
) -> dict:
    with Image.open(primary) as src:
        src_size = list(src.size)
        src_mode = src.mode

    normalized = imaging.load_rgba(normalized_path)

    roles: dict[str, str] = {"full_body": normalized_path.name}
    roles.update(produced)

    return {
        "schema_version": 1,
        "flow": "01_character_reference",
        "character_id": cp.id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "deterministic": True,
        "method": "normalizacao + recorte heuristico (sem IA generativa)",
        "primary_source": {
            "filename": primary.name,
            "sha256": sha256_file(primary),
            "size": src_size,
            "mode": src_mode,
            "selection": "maior area em pixels (criterio mecanico, nao estetico)",
        },
        "all_sources": [
            {"filename": s.name, "sha256": sha256_file(s)} for s in sources
        ],
        "normalization": transform,
        "alpha": {
            "origin": result.metadata.get("alpha_origin"),
            "stats": imaging.alpha_stats(normalized),
        },
        "reference_roles": roles,
        "outputs": [
            {"filename": p.name, "sha256": sha256_file(p)}
            for p in sorted(result.outputs)
            if p.is_file()
        ],
        "warnings": result.warnings,
        "human_review_required": result.human_review,
    }


def _write_json(path: Path, data: Any) -> Path:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)
    return path


def _update_character_yaml(path: Path, roles: dict[str, str]) -> None:
    """Atualiza SOMENTE reference_roles, preservando o resto do arquivo.

    Edicao textual em vez de reescrever o YAML: um round-trip com PyYAML
    apagaria os comentarios explicativos, que sao parte do valor do arquivo.
    """
    text = path.read_text(encoding="utf-8")
    block = "reference_roles:\n" + "".join(
        f"  {name}: {filename}\n" for name, filename in sorted(roles.items())
    )

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        if lines[i].startswith("reference_roles:"):
            out.append(block)
            i += 1
            # consome o bloco antigo (linhas indentadas ou vazias)
            while i < len(lines) and (
                lines[i].startswith((" ", "\t")) or not lines[i].strip()
            ):
                if not lines[i].strip():
                    break
                i += 1
            replaced = True
            continue
        out.append(lines[i])
        i += 1

    if not replaced:
        out.append("\n" + block)

    path.write_text("".join(out), encoding="utf-8")

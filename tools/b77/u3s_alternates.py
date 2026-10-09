#!/usr/bin/env python3
"""Beta 77 u3s: author a 2026 alternate into a free uniform style slot (the "derive" recipe) and compile it.

A style slot is two kit packages (``<code>h<S>.iff`` home, ``<code>a<S>.iff`` road) plus its Team Select cards
(``unif_/helm_<h|a><code>_<S>``), all already on the disc (``tools/b77/u3s_slots.py`` and
``data/nfl2k5_uniform_slots_2026.json`` say which slots are free). A "derive" alternate is built from the team's own
shipped 2026 kit: every texture of the donor kit goes into the slot, then the recipe's recolours, socks and atlas
rules turn it into the alternate (White Bengal = the 2026 road kit, white helmet, white socks). Every edit goes
through the Studio's own fixed-span importers (the same calls as tools/b77/u1_patriots.py ``compile``), so the kit
packages keep their sizes and layouts and every span is checked against the shipped bytes.

  export  --disc DISC --selectors 06A0,06H4,06A4 --cards 06:4 --out EXPORT
          the kit packages and every decoded texture (equipment mud twins too), plus the slot's Team Select cards
  author  --recipes data/nfl2k5_uniform_alternates_2026.json --key CIN:4 --export EXPORT --out ART
          ART/<selector>/<texture>.png for both kits of the slot and ART/edits.json (the Studio's edit kinds)
  cards   --art ART --key CIN:4 --recipes ... --export EXPORT --models DIR --shellc JSON --out CARDS
          the three Team Select cards per kit (k2's layout and cameras through tools/b77/u1_cards.py), then the
          cards join ART/edits.json
  compile --art ART --export EXPORT --index RETAIL_INDEX --out COMPILED
          COMPILED/native_manifest.json: the exact spans for tools/b77/u3s_repair.py (before/after SHA-256 against
          the shipped resource bytes)

Game-derived inputs and outputs stay in private scratch; the repository holds only the recipe and the tools.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77"), str(ROOT / "tools/b765")]
import nfl2k5_team_2026_art as art  # noqa: E402

RECIPES_SCHEMA = "nfl2k5_uniform_alternates_2026/v1"
UNIFORM_MARKS = Path("/media/noah/Storage/.b76-research/uw/marks/manifest.json")   # the pinned NFL shield and swoosh masters
BUILD_TYPES = ("derive", "modernize", "spec")
MANIFEST_SCHEMA = "b77/u3s/texture-repair/v1"
TSET_KINDS = {1: "torso", 2: "pants", 3: "sleeve"}
P8_CHUNKS = {"logo": 49, "chiclet": 50, "splayer": 51, "flipchip": 52}
HELMETS = ("helmet00", "helmet02")
EQUIPMENT_CHUNKS = range(4, 11)
CARD_FAMILIES = (("unif", 256), ("helm", 256), ("helm", 128))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def name_id(name: str) -> int:
    return zlib.crc32(name.upper().encode("utf-16le")) & 0xFFFFFFFF


def selector_parts(selector: str) -> tuple[str, str, int]:
    return selector[:2], selector[2], int(selector[3:])


# ----------------------------------------------------------------------------------------------- export

def export(disc: Path, selectors: list[str], cards: list[str], out: Path) -> dict:
    """Every texture of each kit package (clean and mud), and the slot's Team Select cards, read from the disc."""
    from nfl2k5_playbook_position_recode import OuterImage
    from nfl_txtr import decode_chunk, encode_rgba_png, parse_chunks, parse_texture, texture_to_rgba
    import u1_audit
    out.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "b77/u3s/kit-export/v1", "disc": str(disc), "kits": {}, "cards": []}
    with OuterImage(disc) as archive:
        lookup = {e.name_id: e for e in archive.entries}
        for selector in selectors:
            entry = lookup[name_id(f"{selector}.IFF")]
            package = archive.read(entry.virtual_offset, entry.size)
            (out / "resources").mkdir(exist_ok=True)
            (out / "resources" / f"{selector}.IFF").write_bytes(package)
            folder = out / "uniforms" / selector
            folder.mkdir(parents=True, exist_ok=True)
            assets = []
            for chunk in parse_chunks(package):
                if chunk.kind not in {"TSET", "TXTR"}:
                    continue
                decoded, _info = decode_chunk(package, chunk)
                if chunk.kind == "TSET":
                    count = struct.unpack_from("<I", decoded, 4)[0]
                    textures = [(i, u1_audit.tset_texture(decoded, i)) for i in range(count)]
                else:
                    textures = [(0, parse_texture(decoded, chunk))]
                for index, texture in textures:
                    rgba = texture_to_rgba(decoded, chunk, texture)
                    if chunk.kind == "TSET" and chunk.index in TSET_KINDS:
                        if texture.name.endswith("_mud"):
                            continue
                        file = TSET_KINDS[chunk.index]
                    elif chunk.kind == "TSET":
                        file = texture.name
                    elif chunk.index in (11, 12):
                        file = "helmet_" + texture.name
                    elif 13 <= chunk.index <= 42:
                        file = u1_audit.digit_filename(chunk.index, texture.name)[:-4]
                    else:
                        file = texture.name
                    (folder / f"{file}.png").write_bytes(encode_rgba_png(texture.width, texture.height, rgba))
                    assets.append({"file": f"{file}.png", "name": texture.name, "chunk": chunk.index,
                                   "kind": chunk.kind, "tset_index": index, "size": [texture.width, texture.height]})
            doc["kits"][selector] = {"outer_index": entry.index, "size": len(package), "sha256": sha(package),
                                     "unif": unif_words(package), "assets": assets}
        if cards:
            doc["cards"] = export_cards(archive, cards, out / "cards")
    (out / "export.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return doc


def _walk_chunks(data: bytes):
    from nfl_txtr import HEADER, Chunk
    offset, index = 0, 0
    while offset + HEADER.size <= len(data):
        fields = HEADER.unpack_from(data, offset)
        if fields[0] == b"\0\0\0\0":
            offset += 16
            continue
        require(all(0x20 <= b <= 0x7E for b in fields[0]), f"foreign chunk at {offset:#x}")
        chunk = Chunk(index, offset, fields[0].decode("ascii"), *fields[1:])
        yield chunk
        index += 1
        offset = chunk.end_offset


def export_cards(archive, slots: list[str], out: Path) -> list[dict]:
    """The Team Select cards of the given ``code:style`` slots, located by texture name in every card resource."""
    from nfl_txtr import decode_chunk, encode_rgba_png, parse_texture, texture_to_rgba
    out.mkdir(parents=True, exist_ok=True)
    wanted = set()
    for slot in slots:
        code, style = slot.split(":")
        wanted |= {f"{family}_{side}{code}_{style}" for family in ("unif", "helm") for side in "ha"}
    rows = []
    for outer in (3102, 3105):
        entry = archive.entries[outer]
        data = archive.read(entry.virtual_offset, entry.size)
        for chunk in _walk_chunks(data):
            if chunk.kind != "TXTR":
                continue
            decoded, _ = decode_chunk(data, chunk)
            try:
                texture = parse_texture(decoded, chunk)
            except Exception:  # noqa: BLE001 - non-card TXTR in the aggregate
                continue
            if texture.name not in wanted:
                continue
            span = data[chunk.offset:chunk.end_offset]
            png = f"{texture.name}_{texture.width}.png"
            (out / png).write_bytes(encode_rgba_png(texture.width, texture.height,
                                                    texture_to_rgba(decoded, chunk, texture)))
            rows.append({"outer_index": outer, "name": texture.name, "width": texture.width,
                         "chunk_index": chunk.index, "chunk_offset": chunk.offset, "span_size": len(span),
                         "span_sha256": sha(span), "png": png})
    (out / "cards.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8", newline="\n")
    return rows


UNIF_COLOURS = 0x50          # the kit package's Unif record: facemask/faceshield word, then the turtleneck word


def unif_words(package: bytes) -> dict:
    """The two colour words of a kit package's Unif record (nfl2k5_unif_color_writer's record layout)."""
    require(package[:5] == b"UnifP" and package[0x2C:0x30] == b"Unif"
            and package[0x40:0x50] == "uniform\0".encode("utf-16le"), "foreign Unif record header")
    facemask, turtleneck = struct.unpack_from("<II", package, UNIF_COLOURS)
    return {"facemask": f"{facemask:08X}", "turtleneck": f"{turtleneck:08X}"}


# ----------------------------------------------------------------------------------------------- author

def load_recipe(recipes: Path, key: str) -> dict:
    doc = json.loads(recipes.read_text())
    require(doc.get("schema") == RECIPES_SCHEMA, "unexpected recipes schema")
    recipe = doc["alternates"].get(key)
    require(recipe is not None, f"no recipe {key}")
    require(recipe.get("build_type") in BUILD_TYPES or recipe.get("paint"),
            f"this tool builds the {BUILD_TYPES} recipes and the painted ('paint') ones")
    return recipe


def hex_rgb(text: str) -> np.ndarray:
    text = text.lstrip("#")
    return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0


def remix(rgb: np.ndarray, sources: list[np.ndarray], targets: list[np.ndarray], tolerance: float,
          moved: int | None = 0) -> np.ndarray:
    """Every texel that is a blend of the source colours (anti-aliased edges, baked shading toward black) is
    rebuilt from the same weights over the target colours (a soft sum-to-one least squares per texel, as the art
    tool's socks transfer); texels that are no such blend (flags, hardware, the NFL shield), or hold none of the
    ``moved`` source colour, stay as they are."""
    a = np.stack(sources, axis=1).astype(np.float64)              # 3 x k
    b = np.stack(targets, axis=1).astype(np.float64)
    x = rgb.reshape(-1, 3).T.astype(np.float64)
    weights, *_ = np.linalg.lstsq(np.vstack([a, np.full((1, a.shape[1]), 3.0)]),
                                  np.vstack([x, np.full((1, x.shape[1]), 3.0)]), rcond=None)
    weights = np.clip(weights, 0.0, None)
    weights /= np.maximum(weights.sum(axis=0, keepdims=True), 1e-6)
    residual = np.linalg.norm(x - a @ weights, axis=0)
    m = art.smooth_threshold(np.clip(1.0 - residual / tolerance, 0.0, 1.0), 0.3, 0.7)
    if moved is not None:                    # None: every texel that is a blend of the sources moves (a colour swap)
        m *= np.clip(weights[moved] / 0.02, 0.0, 1.0)
    new = (b @ weights).T
    out = x.T * (1 - m[:, None]) + new * m[:, None]
    return np.clip(out, 0.0, 1.0).reshape(rgb.shape).astype(np.float32)


def greys_to(rgb: np.ndarray, to: np.ndarray, saturation: float, shade: list, min_luma: float = 0.0) -> np.ndarray:
    """Every near-grey texel (white, grey and the cool-white shading of folds) becomes the target colour with the
    texel's own luminance as shading (target x (lo + (hi - lo) x luma)); coloured texels (logos, stripes) stay."""
    luma = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    m = np.clip(1.0 - sat / saturation, 0.0, 1.0)[..., None]
    if min_luma > 0.0:
        m = m * np.clip((luma[..., None] - min_luma) / 0.15, 0.0, 1.0)      # dark marks (stripes) stay
    new = np.clip(to[None, None, :] * (shade[0] + (shade[1] - shade[0]) * luma[..., None]), 0.0, 1.0)
    return rgb * (1 - m) + new * m


def speckle(rgb: np.ndarray, base: np.ndarray, tint: np.ndarray, density: float, strength: float, distance: float,
            seed: str) -> np.ndarray:
    """A sandstorm texture on a flat fabric: single texels of the tint colour scattered over every texel near the
    base colour (deterministic: the generator is seeded from the rule), plus a faint low-frequency mottling."""
    from scipy import ndimage
    rng = np.random.default_rng(zlib.crc32(seed.encode()))
    h, w = rgb.shape[:2]
    on = (np.linalg.norm(rgb - base[None, None, :], axis=2) < distance)
    dots = (rng.random((h, w)) < density).astype(np.float32)
    dots = np.maximum(dots, ndimage.maximum_filter(dots, size=2) * (rng.random((h, w)) < 0.35))
    mottle = ndimage.gaussian_filter(rng.standard_normal((h, w)).astype(np.float32), 2.5) * 0.12
    out = rgb.copy()
    m = (dots * strength * on)[..., None]
    out = out * (1 - m) + tint[None, None, :] * m
    out = out + (mottle * on)[..., None] * 0.25
    return np.clip(out, 0.0, 1.0)


def darks_to(rgb: np.ndarray, to: np.ndarray, threshold: float) -> np.ndarray:
    """Near-black texels (the shell of a black helmet and the shading toward black of its edges) take the target
    colour; anything with a channel above the threshold (logos, coloured stripes, hardware) stays."""
    mx = rgb.max(axis=2)
    m = np.clip((threshold - mx) / (0.5 * threshold), 0.0, 1.0)[..., None]
    return rgb * (1 - m) + to[None, None, :] * m


def hue_to(rgb: np.ndarray, hue: str, to: np.ndarray, reference: float) -> np.ndarray:
    """Saturated texels of one hue family (``purple``: blue above red, green lowest) take the target colour scaled by
    their own brightness against ``reference`` (stripes keep their gradient)."""
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if hue == "purple":
        family = (b >= r) & (g <= r * 0.85 + 0.02)
    elif hue == "blue":
        family = (b >= r * 1.6) & (b >= g * 1.15)
    else:
        raise SystemExit(f"unknown hue family {hue}")
    m = (np.clip((sat - 0.35) / 0.25, 0.0, 1.0) * family)[..., None]
    new = np.clip(to[None, None, :] * np.clip(mx / reference, 0.0, 1.35)[..., None], 0.0, 1.0)
    return rgb * (1 - m) + new * m


def tone_on_tone(rgb: np.ndarray, bg: np.ndarray, to_bg: np.ndarray, tint: np.ndarray, distance: float) -> np.ndarray:
    """The background colour becomes ``to_bg``; every other texel (a logo) turns monochrome in ``tint`` keeping its
    own brightness (a tone-on-tone patch)."""
    d = np.linalg.norm(rgb - bg[None, None, :], axis=2)
    m = np.clip(d / distance - 0.5, 0.0, 1.0)[..., None]                  # 0 on the background, 1 on a logo
    luma = rgb.mean(axis=2, keepdims=True)
    mono = np.clip(tint[None, None, :] * (0.25 + 0.95 * luma), 0.0, 1.0)
    flat = rgb * 0.0 + to_bg[None, None, :]
    return flat * (1 - m) + mono * m


def recolour(rgba: np.ndarray, rule: dict, boxes: dict | None = None) -> tuple[np.ndarray, int]:
    """Inside the rule's region and outside its exclusions: ``remix`` (from/to lists of colours, the first moved)
    or the art tool's shading-keeping family recolour (one colour)."""
    out = rgba.copy()
    rgb = out[..., :3]
    if rule.get("kind") == "speckle":
        new = speckle(rgb, hex_rgb(rule["base"]), hex_rgb(rule["tint"]), float(rule.get("density", 0.03)),
                      float(rule.get("strength", 0.5)), float(rule.get("distance", 0.16)), str(rule.get("seed", "u3a")))
    elif rule.get("kind") == "darks":
        new = darks_to(rgb, hex_rgb(rule["to"]), float(rule.get("threshold", 0.12)))
    elif rule.get("kind") == "hue":
        new = hue_to(rgb, rule["hue"], hex_rgb(rule["to"]), float(rule.get("reference", 0.42)))
    elif rule.get("kind") == "tone":
        new = tone_on_tone(rgb, hex_rgb(rule["from_bg"]), hex_rgb(rule["to_bg"]), hex_rgb(rule["tint"]),
                           float(rule.get("distance", 0.12)))
    elif rule.get("kind") == "greys":
        new = greys_to(rgb, hex_rgb(rule["to"]), float(rule.get("saturation", 0.18)), rule.get("range", [0.5, 1.5]),
                         float(rule.get("min_luma", 0.0)))
    elif isinstance(rule["from"], list):
        new = remix(rgb, [hex_rgb(c) for c in rule["from"]], [hex_rgb(c) for c in rule["to"]],
                    float(rule.get("tolerance", 0.08)), rule.get("moved", 0))
    else:
        new = art._recolour_family(rgb, hex_rgb(rule["from"]), hex_rgb(rule["to"]), float(rule.get("tolerance", 0.2)))
    h, w = rgba.shape[:2]
    mask = np.ones((h, w), np.float32)
    if rule.get("region") and boxes:
        mask = np.zeros((h, w), np.float32)
        x0, y0, x1, y1 = boxes[rule["region"]]
        mask[y0:y1, x0:x1] = 1.0
    if rule.get("box"):
        x0, y0, x1, y1 = rule["box"]
        limit = np.zeros((h, w), np.float32)
        limit[y0:y1, x0:x1] = 1.0
        mask *= limit
    if rule.get("include"):                       # only inside these boxes (native pixels), u3c
        mask = np.zeros((h, w), np.float32)
        for x0, y0, x1, y1 in rule["include"]:
            mask[y0:y1, x0:x1] = 1.0
    for x0, y0, x1, y1 in rule.get("exclude", []):
        mask[y0:y1, x0:x1] = 0.0
    out[..., :3] = rgb * (1 - mask[..., None]) + new * mask[..., None]
    changed = int((np.abs(out[..., :3] - rgba[..., :3]).max(axis=2) > 1.5 / 255).sum())
    return out, changed


def apply_marks(stem: str, rgba: np.ndarray, cfg: dict) -> np.ndarray:
    """The 2026 maker and league marks on a retail-era texture (the 'modernize' step): the retail maker marks are
    filled from the fabric, then the pinned official masters go where the 2026 jerseys carry them (the art tool's
    own placement: collar shield on the torso, swoosh on both sleeves, swoosh and hip shield on the pants)."""
    out = art.upscale(rgba)
    if stem == "torso":
        for box in art.TORSO_SLEEVE_MARKS:
            out = art._clear_old_mark(out, box)
        if cfg.get("collar_shield", True):
            c = art.COLLAR_SHIELD
            top = art.TORSO_V_TIP[1] + float(cfg.get("collar_trim_px", 0.0)) + c["gap_px"]
            art.place_mark(out, "nfl_shield", (art.TORSO_V_TIP[0] * art.MASTER, (top + c["height_px"] / 2.0) * art.MASTER),
                           c["width_px"] * art.MASTER, c["height_px"] * art.MASTER)
    elif stem == "sleeve":
        for arm in ("R", "L"):
            art.sleeve_swoosh(out, hex_rgb(cfg["swoosh"]), arm, offset=tuple(cfg.get("offset", (0.0, 0.0))))
    elif stem == "pants":
        for box in (art.PANTS_SHIELD_BOX, art.PANTS_MAKER_BOX):
            out = art._clear_old_mark(out, box)
        ps = art.PANTS_SWOOSH
        art.place_mark(out, "nike_swoosh", (ps["centre"][0] * art.MASTER, ps["centre"][1] * art.MASTER),
                       ps["width_px"] * art.MASTER, ps["height_px"] * art.MASTER, colour=hex_rgb(cfg["swoosh"]))
        if cfg.get("hip_shield", True):
            sh = art.PANTS_SHIELD
            art.place_mark(out, "nfl_shield", (sh["centre"][0] * art.MASTER, sh["centre"][1] * art.MASTER),
                           sh["width_px"] * art.MASTER, sh["height_px"] * art.MASTER)
        out[..., 3] = 1.0
    return art.downscale(out)


def white_socks(colour: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """One solid sock colour with the reference socks' fabric shading (the art tool's socks rule: the luminance
    against its own row median, so a striped reference gives no bands)."""
    luma = reference[..., :3].mean(axis=2)
    ratio = np.clip(1.0 + (luma - np.median(luma, axis=1, keepdims=True)) * 0.6, 0.85, 1.1)[..., None]
    out = np.ones_like(reference)
    out[..., :3] = np.clip(colour[None, None, :] * ratio, 0.0, 1.0)
    return out


TEAM_MARKS = Path("/media/noah/Storage/.b76-research/u1/teams")      # per-team mark masks (outside the repository)


def deep_merge(base: dict, over: dict) -> dict:
    out = json.loads(json.dumps(base))
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def make_mark(source: Path, target: Path, how: dict) -> None:
    """A coloured mark made from team masks: ``fill`` colours the silhouette of ``from``; ``outline`` {"colour", "px"}
    puts a border of that colour (the mask dilated by px texels) under it. ``layers`` [{"from", "fill"}, ...] stacks
    several masks of one canvas (bottom first) instead."""
    from PIL import ImageFilter

    def rgb(text):
        return tuple(int(text.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    if how.get("layers"):
        first = Image.open(source.parent / how["layers"][0]["from"]).convert("RGBA")
        out = Image.new("RGBA", first.size, (0, 0, 0, 0))
        for layer in how["layers"]:
            mask = Image.open(source.parent / layer["from"]).convert("RGBA").getchannel("A")
            out.paste(Image.new("RGBA", first.size, rgb(layer["fill"]) + (255,)), (0, 0), mask)
        out.save(target)
        return
    mask = Image.open(source).convert("RGBA").getchannel("A")
    size = mask.size
    pad = int(how.get("outline", {}).get("px", 0)) + 2
    canvas = Image.new("L", (size[0] + 2 * pad, size[1] + 2 * pad), 0)
    canvas.paste(mask, (pad, pad))
    out = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    if how.get("outline"):
        grown = canvas.filter(ImageFilter.MaxFilter(2 * int(how["outline"]["px"]) + 1))
        out.paste(Image.new("RGBA", canvas.size, rgb(how["outline"]["colour"]) + (255,)), (0, 0), grown)
    out.paste(Image.new("RGBA", canvas.size, rgb(how["fill"]) + (255,)), (0, 0), canvas)
    out.save(target)


def run_spec(recipe: dict, export_dir: Path, out: Path, uniform_marks: Path) -> Path:
    """The 'spec' build: the team's own 2026 spec (data/nfl2k5_teams_2026/<TEAM>.json) with this alternate's kits
    (``spec.kits.<H|A>``: ``from`` home/away, ``merge`` overrides) and extra albedo colours, authored by the art tool
    (tools/nfl2k5_team_2026_art.py author) into OUT/spec_art/retail/<selector>/. Returns that folder."""
    import types
    team = recipe["team"]
    base = json.loads((ROOT / f"data/nfl2k5_teams_2026/{team}.json").read_text())
    spec = recipe["spec"]
    kits = {}
    for side, row in spec["kits"].items():
        kit = deep_merge(base["kits"][row.get("from", "home" if side == "H" else "away")], row.get("merge", {}))
        for drop in row.get("drop", []):
            kit.pop(drop, None)
        kit["selector"] = f"{recipe['code']}{side}{int(recipe['style'])}"
        kit.pop("outer_index", None)
        kits["home" if side == "H" else "away"] = kit
    base["kits"] = kits
    base["albedo"] = dict(base["albedo"], **spec.get("albedo", {}))
    base["marks"] = dict(base["marks"], **spec.get("marks", {}))
    out.mkdir(parents=True, exist_ok=True)
    spec_path = out / "spec.json"
    spec_path.write_text(json.dumps(base, indent=1) + "\n", encoding="utf-8", newline="\n")
    stage = out / "retail_stage"                      # the art tool names the nameplate glyphs "nameplate", the export "names"
    for folder in sorted((export_dir / "uniforms").iterdir()):
        target = stage / folder.name
        target.mkdir(parents=True, exist_ok=True)
        for file in folder.iterdir():
            link = target / file.name
            if not link.exists():
                link.symlink_to(file.resolve())
        if (folder / "names.png").exists() and not (target / "nameplate.png").exists():
            (target / "nameplate.png").symlink_to((folder / "names.png").resolve())
    for card in (export_dir / "cards").glob("*_*_*_*.png"):       # unif_h00_7_256.png -> <00H7>/team-select_unif_256.png
        family, side, style, res = card.stem.split("_")
        target = stage / f"{side[1:]}{side[0].upper()}{style}"
        target.mkdir(parents=True, exist_ok=True)
        if not (target / f"team-select_{family}_{res}.png").exists():
            (target / f"team-select_{family}_{res}.png").symlink_to(card.resolve())
    marks_dir = Path(spec.get("marks_dir") or TEAM_MARKS / team / "marks")
    if spec.get("derived_marks"):
        derived = out / "marks"
        derived.mkdir(parents=True, exist_ok=True)
        for file in marks_dir.iterdir():
            if not (derived / file.name).exists():
                (derived / file.name).symlink_to(file.resolve())
        for name, how in spec["derived_marks"].items():
            make_mark(marks_dir / how.get("from", name), derived / name, how)
        marks_dir = derived
    args = types.SimpleNamespace(spec=str(spec_path), retail=str(stage),
                                 marks=str(marks_dir),
                                 uniform_marks=str(uniform_marks), equipment=None, outer_home=0, outer_away=0,
                                 out=str(out / "spec_art"))
    art.use_uniform_marks(uniform_marks)
    import shutil
    shutil.rmtree(out / "spec_art", ignore_errors=True)          # never leave a stale texture of an earlier recipe
    require(art.cmd_author(args) == 0, "the art tool failed")
    return out / "spec_art" / "retail"


def author(recipe: dict, export_dir: Path, out: Path, uniform_marks: Path = UNIFORM_MARKS) -> dict:
    if recipe.get("marks"):
        art.use_uniform_marks(uniform_marks)
    spec_dir = run_spec(recipe, export_dir, out, uniform_marks) if recipe.get("spec") else None
    exp = json.loads((export_dir / "export.json").read_text())
    code, style = recipe["code"], int(recipe["style"])
    out.mkdir(parents=True, exist_ok=True)
    edits, receipts = [], {}
    for side, kit in sorted(recipe["kits"].items()):
        selector = f"{code}{side}{style}"
        donor = kit["donor"]
        target = exp["kits"][selector]
        donor_assets = {a["file"]: a for a in exp["kits"][donor]["assets"]}
        folder = out / selector
        folder.mkdir(parents=True, exist_ok=True)
        notes = []
        for asset in target["assets"]:
            file = asset["file"]
            stem = file[:-4]
            if stem.startswith("bump_"):
                continue                                        # relief maps stay the slot's own
            file_donor = donor
            for pattern, other in (kit.get("file_donors") or {}).items():
                if fnmatch.fnmatch(stem, pattern):
                    file_donor = other                           # this file comes from another shipped kit
            use = next((d for d, stems in (kit.get("take") or {}).items()
                        if any(fnmatch.fnmatchcase(stem, pattern) for pattern in stems)), file_donor)
            if use != file_donor:                               # a component taken from another kit (u3c)
                file_donor = use
            src = {a["file"]: a for a in exp["kits"][file_donor]["assets"]}.get(file)
            require(src is not None and src["size"] == asset["size"] or stem.startswith(("digit_arm_", "digit_helmet_")),
                    f"{selector}: donor {file_donor} has no {file} of the same size")
            rgba = art.load(export_dir / "uniforms" / file_donor / file)
            spec_name = "nameplate.png" if file == "names.png" else file
            if spec_dir is not None and (spec_dir / selector / spec_name).exists():
                rgba = art.load(spec_dir / selector / spec_name)
                notes.append(f"{file}: authored by the art tool from the recipe's spec")
            if file_donor != donor:
                notes.append(f"{file}: from {file_donor}")
            if list(rgba.shape[1::-1]) != asset["size"]:
                rgba = np.asarray(Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").resize(
                    tuple(asset["size"]), Image.LANCZOS), np.float32) / 255.0
                notes.append(f"{file}: donor {src['size']} resized to the slot's {asset['size']}")
            if any(Path(file).match(pattern + ".png") for pattern in recipe.get("blank", [])):
                rgba = np.zeros_like(rgba)                       # the Studio draws a blank glyph as nothing
                notes.append(f"{file}: blank")
            for rule in recipe.get("recolour", []):
                if rule.get("kit") not in (None, side):
                    continue                                     # a rule for the other kit of the slot
                if any(fnmatch.fnmatch(stem, pattern) for pattern in rule["components"]):
                    rgba, n = recolour(rgba, rule, art.SPLAYER if stem == "splayer" else None)
                    notes.append(f"{file}: {rule.get('from', 'greys')} -> {rule.get('to', rule.get('to_bg'))} ({n} texels)")
            if recipe.get("marks", {}).get(stem) is not None:
                rgba = apply_marks(stem, rgba, recipe["marks"][stem])
                notes.append(f"{file}: 2026 marks ({json.dumps(recipe['marks'][stem])})")
            if stem in ("socks00", "socks00_mud") and recipe.get("socks") and recipe["socks"].get("kit") in (None, side):
                reference = art.load(export_dir / "uniforms" / selector / "socks00.png")
                rgba = white_socks(hex_rgb(recipe["socks"]["colour"]), reference)
                if stem.endswith("_mud"):
                    rgba[..., :3] *= 0.6                         # the retail darken_60 mud rule
                notes.append(f"{file}: socks {recipe['socks']['colour']} with the slot's retail fabric shading")
            splayer_socks = recipe.get("splayer_socks")
            if isinstance(splayer_socks, dict):
                splayer_socks = splayer_socks.get(side)
            if stem == "splayer" and splayer_socks:
                own = art.load(export_dir / "uniforms" / selector / "splayer.png")
                h, w = rgba.shape[:2]
                boxes = [art.SPLAYER["sock"], art.SPLAYER["sock_low"]]
                colour = hex_rgb(splayer_socks)
                for x0, y0, x1, y1 in boxes:
                    patch = own[y0:y1, x0:x1, :3].mean(axis=2)
                    shade = np.clip(1.0 + (patch - np.median(patch)) * 0.8, 0.8, 1.1)
                    rgba[y0:y1, x0:x1, :3] = np.clip(colour[None, None, :] * shade[..., None], 0, 1)
                notes.append(f"splayer: socks {splayer_socks} with the slot's own atlas shading")
            if recipe.get("paint"):                              # a new design: painted marks (u3c_paint.py)
                import u3c_paint
                painted = u3c_paint.apply(recipe["paint"], stem, rgba, {"selector": selector, "side": side})
                if painted is not rgba:
                    notes.append(f"{file}: painted ({recipe['paint']})")
                rgba = painted
            png = folder / file
            native = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
            Image.fromarray(native, "RGBA").save(png)
            own = np.asarray(Image.open(export_dir / "uniforms" / selector / file).convert("RGBA"))
            if np.array_equal(native, own):
                notes.append(f"{file}: already the slot's own texture, no edit")
                continue
            edits.extend(edit_for(selector, asset, target["outer_index"], png))
        want = dict(exp["kits"][donor]["unif"])
        want.update({k: v for k, v in (recipe.get("unif") or {}).items() if k in want})
        if want != target["unif"]:
            edits.append({"kind": "unif_color", "selector": selector, "facemask": want["facemask"],
                          "turtleneck": want["turtleneck"]})
            notes.append(f"Unif colours {target['unif']} -> {want}")
        receipts[selector] = {"donor": donor, "notes": notes}
    doc = {"schema": "b77/u3s/alternate-art/v1", "key": f"{recipe['team']}:{style}", "set": recipe["set"],
           "edits": edits, "receipts": receipts}
    (out / "edits.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return doc


def edit_for(selector: str, asset: dict, outer: int, png: Path) -> list[dict]:
    code, side, variant = selector_parts(selector)
    stem, chunk = asset["file"][:-4], asset["chunk"]
    base = {"asset_code": code, "side": side, "variant": variant}
    if asset["kind"] == "TSET" and chunk in TSET_KINDS:
        return [dict(base, kind=TSET_KINDS[chunk], clean_png=str(png), mud_png=None, mud_mode="darken_60")]
    if asset["kind"] == "TSET" and chunk in EQUIPMENT_CHUNKS:
        return [{"kind": "uniform_equipment_texture", "asset_id": f"tset:{outer}:{chunk}:{asset['tset_index']}:{stem}",
                 "png": str(png)}]
    if chunk in (11, 12):
        return [dict(base, kind="live_helmet", family=stem.removeprefix("helmet_"), png=str(png))]
    if 13 <= chunk <= 42:
        family = {"jersey": "jersey_digit", "helmet": "helmet_digit", "arm": "arm_digit"}[stem.split("_")[1]]
        return [dict(base, kind="live_number_nameplate", family=family, digit=int(stem[-1]), png=str(png))]
    if chunk == 43:
        return [dict(base, kind="live_number_nameplate", family="nameplate", digit=None, png=str(png))]
    if stem in P8_CHUNKS:
        return [{"kind": "p8_texture", "asset_id": f"p8:{outer}:{stem}", "png": str(png)}]
    raise SystemExit(f"{selector}: no importer for {asset['file']} (chunk {chunk})")


# ----------------------------------------------------------------------------------------------- cards

def cards(recipe: dict, art_dir: Path, export_dir: Path, models: Path, shellc: Path, out: Path,
          number: str = "30") -> dict:
    """Team Select cards from the authored textures (k2's layout, cameras and light: tools/b77/u1_cards.py)."""
    import subprocess
    import tempfile
    import u1_cards as uc
    code, style = recipe["code"], int(recipe["style"])
    exp = json.loads((export_dir / "export.json").read_text())
    donor = next(iter(recipe["kits"].values()))["donor"]
    facemask = (recipe.get("unif") or {}).get("facemask") or exp["kits"][donor]["unif"]["facemask"]
    facemask = recipe.get("card_facemask") or facemask[-6:]           # the card renders the kit's facemask word
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)
    items, plans = [], []
    for side in sorted(recipe["kits"]):
        sel = f"{code}{side}{style}"
        a = art_dir / sel
        tex = {"UNIF_jersey": uc.torso_card(a / "torso.png", work / f"torso_card_{sel}.png"),
               "UNIF_sleeve": str(a / "sleeve.png"), "UNIF_pants": str(a / "pants.png")}
        master = work / f"helmet02_{sel}_x4.png"
        art.save(art.upscale(art.load(a / "helmet_helmet02.png")), master)
        tex.update({k: str(master) for k in ("HI_HELMET_C", "HELMET_C_accessories", "LOGO_helmet_C")})
        for pos, digit in (("L", number[0]), ("R", number[1])):
            tex[f"NUMBER_{pos}"] = str(a / f"digit_jersey_{digit}.png")
            for sh in ("shoulder_A", "shoulder_B"):
                tex[f"NUMBER_{sh}_{pos}"] = str(a / f"digit_arm_{digit}.png")
        layers = {n: work / f"{sel}_{n}.png" for n in ("jersey", "pants", "helmet", "helm_card")}
        items.append({"tex": tex, "hide": ["NUMBER_M", "NUMBER_shoulder_A_M", "NUMBER_shoulder_B_M"] + uc.BODY_HIDE
                      + uc.HEAD_HIDE, "uv_scale": uc.UV_SCALE,
                      "facemask_rgb": [int(facemask[i:i + 2], 16) for i in (0, 2, 4)], "facemask": "FACEMASK12",
                      "shell": "C", "views": [uc.view(n, side, p) for n, p in layers.items()]})
        plans.append((sel, side, layers))
    job = {"head": str(models / "hi_head_o3c115.gltf"), "body": str(models / "hi_body_o3c114.gltf"),
           "arms_down": uc.LAYOUT["arms_down"], "morphs": uc.LAYOUT["morphs"],
           "replace_parts": uc.native_shellc(shellc), "items": items}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=work) as handle:
        json.dump(job, handle)
        job_path = handle.name
    run = subprocess.run(["blender", "-b", "-t", "2", "--python-exit-code", "1", "-P", str(uc.BLENDER_SCRIPT), "--",
                          job_path], capture_output=True, text=True)
    require(run.returncode == 0, f"blender failed: {run.stdout[-1500:]}{run.stderr[-800:]}")
    size, manifest = 256 * uc.M, {}
    edits = []
    for sel, side, layers in plans:
        mdir, ndir = out / "master4x" / sel, out / sel
        mdir.mkdir(parents=True, exist_ok=True)
        ndir.mkdir(parents=True, exist_ok=True)
        card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        for name in ("pants", "jersey", "helmet"):
            card = Image.alpha_composite(card, uc.saturate(Image.open(layers[name])))
        card.save(mdir / "team-select_unif_256.png")
        uc.box_reduce(card, 256).save(ndir / "team-select_unif_256.png")
        helm = np.asarray(uc.saturate(Image.open(layers["helm_card"]))).copy()
        bar_png = export_dir / "cards" / f"helm_{side.lower()}{code}_{style}_256.png"
        bar = np.asarray(Image.open(bar_png).convert("RGBA").resize((size, size), Image.NEAREST))
        helm[uc.HELM_BAR_TOP * uc.M:] = bar[uc.HELM_BAR_TOP * uc.M:]
        hm = Image.fromarray(helm)
        hm.save(mdir / "team-select_helm_256.png")
        uc.box_reduce(hm, 256).save(ndir / "team-select_helm_256.png")
        h128 = uc.box_reduce(hm, 512)
        uc.box_reduce(h128, 128).save(ndir / "team-select_helm_128.png")
        manifest[sel] = [str(ndir / f"team-select_{k}.png") for k in ("unif_256", "helm_256", "helm_128")]
        for family, resolution in CARD_FAMILIES:
            edits.append({"kind": "team_select", "asset_code": code, "side": "home" if side == "H" else "away",
                          "style": style, "family": family, "resolution": resolution,
                          "png": str(ndir / f"team-select_{family}_{resolution}.png")})
    (out / "cards_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    doc_path = art_dir / "edits.json"
    doc = json.loads(doc_path.read_text())
    doc["edits"] = [e for e in doc["edits"] if e["kind"] != "team_select"] + edits
    doc_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest


# ----------------------------------------------------------------------------------------------- compile

def _chunk_span(resource: bytes, index: int) -> tuple[int, int]:
    from nfl_txtr import parse_chunks
    for chunk in parse_chunks(resource):
        if chunk.index == index:
            return chunk.offset, chunk.end_offset - chunk.offset
    raise SystemExit(f"chunk {index} absent")


def compile_edits(art_dir: Path, export_dir: Path, index: Path, out: Path) -> dict:
    """Every edit through the Studio's own importer; spans recorded against the shipped resource bytes."""
    import nfl2k5_jersey_png_workflow as defaults
    import nfl_jersey_tset_png_import as jersey_import
    import nfl_jersey_tset_targets as jersey_targets
    import nfl_pants_tset_png_import as pants_import
    import nfl_pants_tset_targets as pants_targets
    import nfl_sleeve_tset_png_import as sleeve_import
    import nfl_sleeve_tset_targets as sleeve_targets
    import nfl_live_numbers_nameplate_png_import as digit_import
    import nfl_live_numbers_nameplate_targets as digit_targets
    import nfl_live_helmet_txtr_png_import as helmet_import
    import nfl_live_helmet_txtr_targets as helmet_targets
    import nfl_team_select_card_png_import as card_import
    from mod_editor.core import nfl2k5_p8_texture_writer as p8_writer
    from mod_editor.core import nfl2k5_uniform_equipment_writer as equipment_writer
    doc = json.loads((art_dir / "edits.json").read_text())
    exp = json.loads((export_dir / "export.json").read_text())
    card_index = {(c["name"], c["width"]): c for c in exp.get("cards", [])}
    outer_name = {str(k["outer_index"]): name for name, k in exp["kits"].items()}
    out.mkdir(parents=True, exist_ok=True)
    (out / "decoded").mkdir(exist_ok=True)
    spans: dict[str, list] = {}
    reports, resources = [], {}

    def resource(name: str) -> bytes:
        if name not in resources:
            resources[name] = (export_dir / "resources" / f"{name}.IFF").read_bytes()
        return resources[name]

    def record(key: str, offset: int, span: bytes, before: bytes, label: str):
        require(len(span) == len(before), f"{label}: stored span size changed")
        path = out / f"{sha(span)}.span"
        path.write_bytes(span)
        spans.setdefault(key, []).append({"offset": offset, "length": len(span), "label": label,
                                          "before_sha256": sha(before), "after_sha256": sha(span),
                                          "replacement": path.name})

    tset = {"torso": (jersey_targets, jersey_import), "sleeve": (sleeve_targets, sleeve_import),
            "pants": (pants_targets, pants_import)}
    groups: dict[tuple[str, int], list] = {}
    for edit in doc["edits"]:
        kind = edit["kind"]
        if kind in tset:
            targets, importer = tset[kind]
            selector = f"{edit['asset_code']}{edit['side']}{edit['variant']}"
            _, _, _, target = targets.select_target(edit["asset_code"], edit["side"], edit["variant"],
                                                    targets.DEFAULT_REPORT)
            span, previews, receipt = importer.import_png(index, defaults.DEFAULT_INVENTORY, targets.DEFAULT_REPORT,
                                                          target, Path(edit["clean_png"]), None, edit["mud_mode"])
            data = resource(selector)
            record(f"{selector}.IFF", target.chunk_offset, span,
                   data[target.chunk_offset:target.chunk_offset + target.span_size], kind)
            (out / "decoded" / f"{selector}_{kind}.png").write_bytes(previews[0][1])
            reports.append({"resource": selector, "kind": kind, "receipt": receipt})
        elif kind == "live_number_nameplate":
            selector = f"{edit['asset_code']}{edit['side']}{edit['variant']}"
            _, _, target = digit_targets.select_target(edit["family"], edit["asset_code"], edit["side"],
                                                       edit["variant"], edit["digit"], digit_targets.DEFAULT_REPORT)
            try:
                span, png, receipt = digit_import.build_import(index, digit_targets.DEFAULT_REPORT, edit["family"],
                                                               edit["asset_code"], edit["side"], edit["variant"],
                                                               edit["digit"], Path(edit["png"]))
            except Exception as error:  # noqa: BLE001 - say which glyph does not fit
                raise SystemExit(f"{selector} {edit['family']} digit {edit['digit']}: {error}") from error
            data = resource(selector)
            label = f"{edit['family']}_{edit['digit']}" if edit["digit"] is not None else edit["family"]
            record(f"{selector}.IFF", target.chunk_offset, span,
                   data[target.chunk_offset:target.chunk_offset + target.span_size], label)
            (out / "decoded" / f"{selector}_{label}.png").write_bytes(png)
            reports.append({"resource": selector, "kind": kind, "label": label, "receipt": receipt})
        elif kind == "live_helmet":
            selector = f"{edit['asset_code']}{edit['side']}{edit['variant']}"
            _, _, _, target = helmet_targets.select_target(edit["asset_code"], edit["side"], edit["variant"],
                                                           edit["family"], helmet_targets.DEFAULT_REPORT)
            span, previews, receipt = helmet_import.build_import(index, helmet_targets.DEFAULT_REPORT,
                                                                 edit["asset_code"], edit["side"], edit["variant"],
                                                                 edit["family"], Path(edit["png"]))
            data = resource(selector)
            record(f"{selector}.IFF", target.chunk_offset, span,
                   data[target.chunk_offset:target.chunk_offset + target.span_size], edit["family"])
            (out / "decoded" / f"{selector}_{edit['family']}.png").write_bytes(previews[0][1])
            reports.append({"resource": selector, "kind": kind, "family": edit["family"], "receipt": receipt})
        elif kind == "p8_texture":
            _p8, outer, name = edit["asset_id"].split(":")
            selector = outer_name[outer]
            span, previews, report, _sel, _rec = p8_writer.build_unified_p8_texture_import(
                index, edit["asset_id"], Path(edit["png"]))
            data = resource(selector)
            start, length = _chunk_span(data, P8_CHUNKS[name])
            record(f"{selector}.IFF", start, span, data[start:start + length], name)
            for _label, preview in previews[:1]:
                (out / "decoded" / f"{selector}_{name}.png").write_bytes(preview)
            reports.append({"resource": selector, "kind": kind, "name": name, "report": report})
        elif kind == "unif_color":
            import nfl_uniform_color_xiso_direct_patch as colour_writer
            selector = edit["selector"]
            data = resource(selector)
            unif_words(data)
            span = colour_writer.pack_colors(int(edit["facemask"], 16), int(edit["turtleneck"], 16))
            record(f"{selector}.IFF", UNIF_COLOURS, span, data[UNIF_COLOURS:UNIF_COLOURS + 8], "unif_color")
            reports.append({"resource": selector, "kind": kind, "facemask": edit["facemask"],
                            "turtleneck": edit["turtleneck"]})
        elif kind == "uniform_equipment_texture":
            _t, outer, chunk, _i, _n = edit["asset_id"].split(":")
            groups.setdefault((outer, int(chunk)), []).append((edit["asset_id"], Path(edit["png"])))
        elif kind == "team_select":
            span, preview, receipt = card_import.build_import(
                index, ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json", edit["family"],
                edit["asset_code"], edit["side"], edit["style"], edit["resolution"], Path(edit["png"]))
            tex = f"{edit['family']}_{edit['side'][0]}{edit['asset_code']}_{edit['style']}"
            row = card_index.get((tex, edit["resolution"]))
            require(row is not None, f"{tex} {edit['resolution']} is not in the shipped card index")
            require(len(span) == row["span_size"], f"{tex}: card span size changed")
            path = out / f"{sha(span)}.span"
            path.write_bytes(span)
            spans.setdefault(f"outer:{row['outer_index']}", []).append(
                {"offset": row["chunk_offset"], "length": len(span), "label": f"{tex}_{edit['resolution']}",
                 "before_sha256": row["span_sha256"], "after_sha256": sha(span), "replacement": path.name})
            (out / "decoded" / f"{tex}_{edit['resolution']}.png").write_bytes(preview)
            reports.append({"resource": f"outer:{row['outer_index']}", "kind": kind, "card": tex, "receipt": receipt})
        else:
            raise SystemExit(f"unowned edit kind {kind}")
    for (outer, chunk), rows in sorted(groups.items()):
        selector = outer_name[outer]
        rebuilt, previews, report, _sel, _rec = equipment_writer.build_unified_uniform_equipment_imports(
            index, rows, suggest_fit=False)
        data = resource(selector)
        start, length = _chunk_span(data, chunk)
        record(f"{selector}.IFF", start, rebuilt, data[start:start + length], f"equipment_chunk_{chunk}")
        for label, png in previews:
            (out / "decoded" / f"{selector}_{label}").write_bytes(png)
        reports.append({"resource": selector, "kind": "uniform_equipment_texture", "chunk": chunk, "report": report})
    for patches in spans.values():
        patches.sort(key=lambda p: p["offset"])
    manifest = {"schema": MANIFEST_SCHEMA, "key": doc["key"], "set": doc["set"], "resources": spans}
    (out / "native_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                              encoding="utf-8", newline="\n")
    (out / "compile_receipts.json").write_text(json.dumps(reports, indent=1, sort_keys=True, default=str) + "\n",
                                               encoding="utf-8", newline="\n")
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("export")
    s.add_argument("--disc", type=Path, required=True)
    s.add_argument("--selectors", required=True)
    s.add_argument("--cards", default="")
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("author")
    s.add_argument("--recipes", type=Path, default=ROOT / "data/nfl2k5_uniform_alternates_2026.json")
    s.add_argument("--key", required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("cards")
    s.add_argument("--recipes", type=Path, default=ROOT / "data/nfl2k5_uniform_alternates_2026.json")
    s.add_argument("--key", required=True)
    s.add_argument("--art", type=Path, required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--models", type=Path, required=True)
    s.add_argument("--shellc", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("compile")
    s.add_argument("--art", type=Path, required=True)
    s.add_argument("--export", type=Path, required=True)
    s.add_argument("--index", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.command == "export":
        doc = export(a.disc, a.selectors.split(","), [c for c in a.cards.split(",") if c], a.out)
        print(json.dumps({k: len(v["assets"]) for k, v in doc["kits"].items()}), len(doc["cards"]), "cards")
    elif a.command == "author":
        doc = author(load_recipe(a.recipes, a.key), a.export, a.out)
        print(len(doc["edits"]), "edits;", json.dumps(doc["receipts"])[:600])
    elif a.command == "cards":
        print(json.dumps(cards(load_recipe(a.recipes, a.key), a.art, a.export, a.models, a.shellc, a.out)))
    elif a.command == "compile":
        manifest = compile_edits(a.art, a.export, a.index, a.out)
        print(json.dumps({k: len(v) for k, v in manifest["resources"].items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

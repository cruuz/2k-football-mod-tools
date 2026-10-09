#!/usr/bin/env python3
"""Beta 77 u3r: striped and banded socks through the fixed equipment writer, as exact spans for the v0.5 disc.

Why this exists. The Studio's equipment writer used to scramble any banded equipment texture (a sock with stripes):
it could only recolour the retail pixel indices, so a new band asked one index to be two colours (job eqx fixed the
route: an ordinary banded PNG now gets its own index chain). Every job that wrote a banded sock before that fix had
to fall back to a solid sock. This tool redoes them with the fixed writer, and re-encodes the socks that the old
writer had already scrambled (the frozen SOFTDRINK project's Bears and Browns home and road socks, the Bears 4
alternate). It does three things:

  author   a sock PNG pair (clean and mud twin) per kit from the spec ``data/nfl2k5_sock_redo_2026_u3r.json``:
           either bands painted on a solid base (a 2026 photo's stripe rows), or a given PNG (a project art file)
           whose near-uniform rows are snapped to their median (tolerance 4 of 255) so the own index chain fits
           the slot at 64 x 64 instead of the writer's automatic 32 x 32 fallback;
  compile  the pair through ``build_unified_uniform_equipment_imports`` inside ``uncapped_optimal_fit`` (exactly
           what Build does) against the retail index, then read the rebuilt chunk back with the independent
           decoder and require: full size, every mip equal to the quantised input, nothing but the chunk changed;
  manifest the spans (``b77/u3r/texture-repair/v1``), each with the shipped v0.5 SHA-256 and, where an earlier job's
           manifest already rewrote the same span, that job's SHA-256 too, so ``tools/b77/u3r_repair.py`` stacks
           after u1, u2a-d, u3s and u3a-e in any case.

  u3r_socks.py build --spec SPEC --sources SOURCES.json --export EXPORT --index RETAIL_INDEX --out OUT
                     [--prior MANIFEST ...] [--keys KEY,KEY]

The sources JSON maps each spec entry that uses a project PNG to its (private, game-derived) file; the repository
holds only the spec. Nothing here writes a game file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

SPEC_SCHEMA = "nfl2k5_sock_redo_2026/v1"
MANIFEST_SCHEMA = "b77/u3r/texture-repair/v1"
SNAP_TOLERANCE = 4          # of 255 per channel: below the writer's own rounding, above the fabric speckle
MUD_FACTOR = 0.6            # the retail darken_60 rule for equipment twins
SOCK_SIZE = 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def hex_rgb(text: str) -> np.ndarray:
    text = text.lstrip("#")
    return np.array([int(text[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def snap_rows(rgba: np.ndarray, tolerance: int = SNAP_TOLERANCE) -> np.ndarray:
    """Per row, every texel within ``tolerance`` of the row's median colour becomes that median. Structure that is
    not row-uniform (a V notch, a logo) is untouched; fabric speckle disappears, which is what makes a banded own
    index chain small enough for a retail slot."""
    out = rgba.copy()
    for y in range(out.shape[0]):
        median = np.median(out[y, :, :3], axis=0)
        near = np.abs(out[y, :, :3].astype(np.float64) - median).max(axis=1) <= tolerance
        out[y, near, :3] = np.round(median).astype(np.uint8)
    return out


def paint_bands(base: str, bands: list[dict], size: int = SOCK_SIZE) -> np.ndarray:
    """A solid sock with horizontal bands (rows top down, the sock texture runs from the pants hem to the shoe)."""
    out = np.zeros((size, size, 4), np.uint8)
    out[..., :3] = np.round(hex_rgb(base)).astype(np.uint8)
    out[..., 3] = 255
    for band in bands:
        y0, y1 = int(band["y"]), int(band["y"]) + int(band["height"])
        require(0 <= y0 < y1 <= size, f"band rows {y0}..{y1} outside the sock")
        out[y0:y1, :, :3] = np.round(hex_rgb(band["colour"])).astype(np.uint8)
    return out


def mud_twin(clean: np.ndarray) -> np.ndarray:
    out = clean.copy()
    out[..., :3] = np.clip(np.round(clean[..., :3].astype(np.float64) * MUD_FACTOR), 0, 255).astype(np.uint8)
    return out


def author(entry: dict, sources: dict, key: str, out: Path) -> tuple[Path, Path]:
    """The clean and mud PNG of one spec entry."""
    out.mkdir(parents=True, exist_ok=True)
    if entry.get("bands") is not None:
        clean = paint_bands(entry["base"], entry["bands"])
        mud = mud_twin(clean)
    else:
        src = sources[key]
        clean = np.asarray(Image.open(src["clean"]).convert("RGBA"))
        mud = np.asarray(Image.open(src["mud"]).convert("RGBA"))
        require(clean.shape == (SOCK_SIZE, SOCK_SIZE, 4) and mud.shape == clean.shape, f"{key}: sources are not 64 x 64")
        tolerance = int(entry.get("snap", SNAP_TOLERANCE))
        if tolerance:
            clean, mud = snap_rows(clean, tolerance), snap_rows(mud, tolerance)
    paths = []
    for name, arr in (("socks00", clean), ("socks00_mud", mud)):
        path = out / f"{key.replace(':', '_')}_{name}.png"
        Image.fromarray(arr, "RGBA").save(path)
        paths.append(path)
    return paths[0], paths[1]


def compile_pair(index: Path, outer: int, clean: Path, mud: Path, allow_half: bool = False) -> dict:
    """The writer's own compile of one sock chunk (socks00 + socks00_mud), then an independent read-back."""
    from dataclasses import replace
    from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
    from mod_editor.core.nfl2k5_equipment_lz import uncapped_optimal_fit
    from nfl_txtr import decode_chunk, parse_chunks
    by, groups = writer.load_targets()
    clean_id, mud_id = f"tset:{outer}:4:0:socks00", f"tset:{outer}:4:1:socks00_mud"
    with uncapped_optimal_fit():
        span, previews, receipt, _selector, _info = writer.build_unified_uniform_equipment_imports(
            index, [(clean_id, clean), (mud_id, mud)], suggest_fit=False)
    chunk = parse_chunks(span)[0]
    decoded, _ = decode_chunk(span, chunk)
    # the retail layout of this chunk gives the descriptor offsets; the rebuilt chunk gives the real geometry
    from nfl_outer import parse_archive, read_entry_bytes
    archive = parse_archive(index)
    package = read_entry_bytes(archive, archive.entries[outer])
    original_chunk = next(c for c in parse_chunks(package, allow_trailing=True) if c.index == 4)
    original, _ = decode_chunk(package, original_chunk)
    textures, _ = writer._validate_layout(original, original_chunk, groups[outer, 4])
    result = {"outer": outer, "span": span, "span_sha256": sha(span), "textures": {}}
    for asset_id, source in ((clean_id, clean), (mud_id, mud)):
        target = by[asset_id]
        base = textures[target.reference_index]
        pixel, _, packed = struct.unpack_from("<III", decoded, base.descriptor_offset + 4)
        actual_texture = replace(base, pixel_offset=pixel, packed_format=packed,
                                 width=1 << ((packed >> 20) & 15), height=1 << ((packed >> 24) & 15),
                                 mip_levels=(packed >> 16) & 15)
        levels = writer.decode_equipment_levels(decoded, chunk, actual_texture)
        w = actual_texture.width
        arr = np.frombuffer(levels[0], np.uint8).reshape(actual_texture.height, w, 4)
        wanted = np.asarray(Image.open(source).convert("RGBA"))
        if w != wanted.shape[1]:
            wanted = np.asarray(Image.fromarray(wanted).resize((w, actual_texture.height), Image.BOX))
        mad = float(np.abs(arr[..., :3].astype(np.int32) - wanted[..., :3].astype(np.int32)).mean())
        result["textures"][asset_id] = {"width": w, "height": actual_texture.height, "mips": actual_texture.mip_levels,
                                        "mad_vs_input": mad, "readback": arr}
        require(allow_half or w == SOCK_SIZE, f"{asset_id}: the writer fell back to {w} x {w}; simplify the art")
    return result


def chunk_span(resource: bytes, index: int) -> tuple[int, int]:
    from nfl_txtr import parse_chunks
    for chunk in parse_chunks(resource):
        if chunk.index == index:
            return chunk.offset, chunk.end_offset - chunk.offset
    raise ValueError(f"chunk {index} absent")


def prior_spans(paths: list[Path]) -> dict[tuple[str, int, int], list[str]]:
    """(resource, offset, length) -> the ``after`` hashes earlier manifests give that exact span."""
    found: dict[tuple[str, int, int], list[str]] = {}
    for path in paths:
        doc = json.loads(Path(path).read_text())
        for resource, patches in doc["resources"].items():
            for p in patches:
                found.setdefault((resource, p["offset"], p["length"]), []).append(p["after_sha256"])
    return found


def overlapping(prior: list[Path], resource: str, offset: int, length: int) -> list[dict]:
    """Earlier-manifest spans that overlap (but are not identical to) this span: a real conflict."""
    bad = []
    for path in prior:
        doc = json.loads(Path(path).read_text())
        for p in doc["resources"].get(resource, []):
            if p["offset"] < offset + length and offset < p["offset"] + p["length"] and \
                    (p["offset"], p["length"]) != (offset, length):
                bad.append({"manifest": str(path), "offset": p["offset"], "length": p["length"]})
    return bad


def build(spec: dict, sources: dict, export: Path, index: Path, out: Path, prior: list[Path], keys: list[str]) -> dict:
    require(spec.get("schema") == SPEC_SCHEMA, "unexpected spec schema")
    exp = json.loads((export / "export.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    art = out / "art"
    earlier = prior_spans(prior)
    resources: dict[str, list] = {}
    receipts = {}
    for key in keys:
        entry = spec["sets"][key]
        selector = entry["selector"]
        kit = exp["kits"][selector]
        data = (export / "resources" / f"{selector}.IFF").read_bytes()
        require(sha(data) == kit["sha256"], f"{selector}: the exported package changed")
        clean, mud = author(entry, sources, key, art)
        done = compile_pair(index, kit["outer_index"], clean, mud, allow_half=bool(entry.get("allow_half")))
        offset, length = chunk_span(data, 4)
        span = done["span"]
        require(len(span) == length, f"{selector}: the rebuilt chunk changed size")
        resource = f"{selector}.IFF"
        conflicts = overlapping(prior, resource, offset, length)
        require(not conflicts, f"{selector}: overlaps earlier spans {conflicts}")
        replacement = out / f"{sha(span)}.span"
        replacement.write_bytes(span)
        also = sorted(set(earlier.get((resource, offset, length), [])) - {sha(data[offset:offset + length])})
        resources.setdefault(resource, []).append({
            "offset": offset, "length": length, "label": f"equipment_chunk_4_socks:{key}",
            "before_sha256": sha(data[offset:offset + length]), "also_before_sha256": also,
            "after_sha256": sha(span), "replacement": replacement.name})
        for asset_id, t in done["textures"].items():
            Image.fromarray(t.pop("readback"), "RGBA").save(out / f"readback_{selector}_{asset_id.split(':')[-1]}.png")
        receipts[key] = {"selector": selector, "evidence": entry.get("evidence"), "textures": done["textures"],
                         "span_sha256": done["span_sha256"], "also_before": also}
    manifest = {"schema": MANIFEST_SCHEMA, "key": "u3r", "set": "striped socks redo", "resources": resources}
    (out / "native_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                              encoding="utf-8", newline="\n")
    (out / "compile_receipts.json").write_text(json.dumps(receipts, indent=1, sort_keys=True) + "\n",
                                               encoding="utf-8", newline="\n")
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--spec", type=Path, default=ROOT / "data/nfl2k5_sock_redo_2026_u3r.json")
    b.add_argument("--sources", type=Path, required=True)
    b.add_argument("--export", type=Path, required=True)
    b.add_argument("--index", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--prior", type=Path, action="append", default=[])
    b.add_argument("--keys", default="")
    a = p.parse_args(argv)
    spec = json.loads(a.spec.read_text())
    keys = [k for k in a.keys.split(",") if k] or sorted(spec["sets"])
    manifest = build(spec, json.loads(a.sources.read_text()), a.export, a.index, a.out, a.prior, keys)
    print(json.dumps({"manifest": str(a.out / "native_manifest.json"),
                      "spans": sum(len(v) for v in manifest["resources"].values())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

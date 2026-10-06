#!/usr/bin/env python3
"""Export the actual shipped kits, without the retail-template hash assumptions.

This read-only evidence tool uses the repo's XISO/resource/texture decoders.
Game-derived outputs belong in private scratch, never the source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from nfl2k5_playbook_position_recode import OuterImage
from nfl_txtr import (TextureInfo, decode_chunk, encode_rgba_png, parse_chunks,
                     parse_texture, texture_to_rgba)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digit_filename(chunk_index: int, native_name: str) -> str:
    """Validate each native family name before assigning a human-facing label."""
    if not 13 <= chunk_index <= 42:
        raise ValueError("not a live digit chunk")
    family, prefix = (("jersey", ""), ("helmet", "hn"), ("arm", "an"))[(chunk_index - 13) // 10]
    digit = (chunk_index - 13) % 10
    if native_name != prefix + str(48 + digit):
        raise ValueError(f"digit chunk/name disagree: {chunk_index} {native_name}")
    return f"digit_{family}_{digit}.png"


def tset_texture(decoded: bytes, reference: int) -> TextureInfo:
    base = 0x18 + reference * 0x24
    name_at = base + 4 + struct.unpack_from("<i", decoded, base + 4)[0] - 1
    desc_at = base + 8 + struct.unpack_from("<i", decoded, base + 8)[0] - 1
    end = name_at
    while decoded[end:end + 2] != b"\0\0":
        end += 2
    name = decoded[name_at:end].decode("utf-16le")
    _, pixel, palette, fmt, size, flags = struct.unpack_from("<6I", decoded, desc_at)
    width = size & 0xffff if size else 1 << ((fmt >> 20) & 15)
    height = size >> 16 if size else 1 << ((fmt >> 24) & 15)
    return TextureInfo(name, name_at, desc_at, pixel, palette, fmt, size,
                       flags, (fmt >> 4) & 15, (fmt >> 8) & 255, "P8",
                       (fmt >> 16) & 15, width, height, 1 << ((fmt >> 28) & 15))


def kit_jobs() -> list[dict]:
    jobs = []
    for path in sorted((ROOT / "data/nfl2k5_teams_2026").glob("*.json")):
        doc = json.loads(path.read_text())
        if "kits" not in doc:
            continue
        for side in ("home", "away"):
            jobs.append({"team": path.stem, "selector": doc["kits"][side]["selector"]})
    for style in (10, 11, 12):
        for side in "HA":
            jobs.append({"team": "LAR", "selector": f"23{side}{style}"})
    if len(jobs) != 70 or len({j["selector"] for j in jobs}) != 70:
        raise ValueError("expected the 70 distinct shipped 2026 sets")
    return jobs


def export_package(package: bytes, job: dict, out: Path) -> dict:
    """Decode the stored bytes, including readback from a repaired resource."""
    selector = job["selector"]
    folder = out / "uniforms" / selector
    folder.mkdir(parents=True, exist_ok=True)
    resource = out / "resources" / (selector + ".IFF")
    resource.parent.mkdir(exist_ok=True)
    resource.write_bytes(package)
    assets = []
    for chunk in parse_chunks(package):
        if chunk.kind not in {"TSET", "TXTR", "Unif"}:
            continue
        decoded, _info = decode_chunk(package, chunk)
        span = package[chunk.offset:chunk.end_offset]
        if chunk.kind == "Unif":
            facemask = struct.unpack_from("<I", decoded, 0x30)[0]
            job["facemask"] = f"#{facemask & 0xffffff:06X}"
            job["facemask_argb"] = f"{facemask:08X}"
            continue
        if chunk.kind == "TSET":
            count = struct.unpack_from("<I", decoded, 4)[0]
            textures = [tset_texture(decoded, i) for i in range(count)]
        else:
            textures = [parse_texture(decoded, chunk)]
        for texture in textures:
            if texture.name.endswith("_mud"):
                continue
            rgba = texture_to_rgba(decoded, chunk, texture)
            n = {1: "torso", 2: "pants", 3: "sleeve"}.get(chunk.index)
            if chunk.index in (11, 12):
                n = "helmet_" + texture.name
            elif 13 <= chunk.index <= 42:
                n = digit_filename(chunk.index, texture.name).removesuffix(".png")
            n = n or texture.name
            dest = folder / f"{n}.png"
            png = encode_rgba_png(texture.width, texture.height, rgba)
            dest.write_bytes(png)
            assets.append({"name": texture.name, "png": str(dest),
                           "chunk_index": chunk.index, "chunk_kind": chunk.kind,
                           "offset": chunk.offset, "length": len(span),
                           "span_sha256": sha(span), "decoded_sha256": sha(decoded),
                           "rgba_sha256": sha(rgba), "png_sha256": sha(png),
                           "dimensions": [texture.width, texture.height]})
    return dict(job, resource_path=str(resource), resource_sha256=sha(package),
                resource_size=len(package), art=str(folder), assets=assets)


def export_updated(baseline: Path, patched: Path, out: Path) -> dict:
    """Keep unchanged resources pinned and decode only repaired native files."""
    out = out.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("game-derived evidence must stay outside the repository")
    doc = json.loads(baseline.read_text())
    known = {row["selector"] + ".IFF" for row in doc["sets"]}
    present = {p.name for p in patched.glob("*.IFF")}
    if not present or present - known:
        raise ValueError("patched resources must be a nonempty subset of audited kits")
    rows = []
    for row in doc["sets"]:
        path = patched / (row["selector"] + ".IFF")
        if path.name in present:
            rows.append(export_package(path.read_bytes(), row, out))
        else:
            if sha(Path(row["resource_path"]).read_bytes()) != row["resource_sha256"]:
                raise ValueError("unchanged baseline resource hash changed")
            rows.append(row)
    doc.update(source=str(patched.resolve()), baseline_export=str(baseline.resolve()), sets=rows)
    out.mkdir(parents=True, exist_ok=True)
    (out / "export.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def export(source: Path, out: Path) -> dict:
    out = out.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("game-derived evidence must stay outside the repository")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with OuterImage(source) as archive:
        lookup = {e.name_id: e for e in archive.entries}
        for job in kit_jobs():
            selector = job["selector"]
            name = selector + ".IFF"
            name_id = zlib.crc32(name.encode("utf-16le")) & 0xffffffff
            entry = lookup[name_id]
            package = archive.read(entry.virtual_offset, entry.size)
            row = export_package(package, dict(job, outer_index=entry.index,
                                              virtual_offset=entry.virtual_offset), out)
            rows.append(row)
            print(selector, len(row["assets"]), flush=True)
    doc = {"schema": "b765/u1/actual-kit-export/v1", "source": str(source.resolve()),
           "sets": rows, "set_count": len(rows)}
    (out / "export.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path)
    p.add_argument("--baseline-export", type=Path)
    p.add_argument("--patched-resources", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if args.source and not (args.baseline_export or args.patched_resources):
        export(args.source, args.out)
    elif args.baseline_export and args.patched_resources and not args.source:
        export_updated(args.baseline_export, args.patched_resources, args.out)
    else:
        p.error("provide --source, or both --baseline-export and --patched-resources")


if __name__ == "__main__":
    main()

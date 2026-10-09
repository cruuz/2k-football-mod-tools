#!/usr/bin/env python3
"""Apply UNI sealed texture spans AFTER kitx, sh1 and a5k.

Only the scoped Seattle, Denver and Pittsburgh gold helmets, Giants home numbers and the explicitly
listed Team Select cards are owned. Every input span must match its before or after hash.
The index and unrelated pack bytes are retained exactly. No disc build is made.

  uni_repair.py --input STACK/vc_53450030 --output NEW/vc_53450030
                --manifest native_manifest.json --receipt receipt.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import sh1_repair as shared
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from nfl_txtr import parse_chunks, decode_chunk, parse_texture
from nfl_outer import PACK_NAMES

SCHEMA = "b77/uni/texture-repair/v1"
SCOPE = ROOT / "data/nfl2k5_uniform_uni_scope.json"
sha, require = shared.sha, shared.require


def scope() -> dict:
    doc = json.loads(SCOPE.read_text(encoding="utf-8"))
    require(doc.get("schema") == "b77/uni/scope/v1", "unsupported UNI scope")
    return doc


def load_manifest(path: Path) -> dict:
    shared._b765().refuse_links(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    require(doc.get("schema") == SCHEMA, "unsupported UNI manifest")
    require(doc.get("scope_sha256") == sha(SCOPE.read_bytes()), "UNI scope differs from compile")
    owned = scope()
    names = {s + ".IFF" for s in owned["helmet_selectors"] + owned["digit_selectors"]}
    names |= {"outer:3102", "outer:3105"}
    require(bool(doc.get("resources")) and set(doc["resources"]) <= names, "unowned UNI resource")
    require(all(bool(p) for p in doc["resources"].values()), "empty UNI patch list")
    return doc


def validate_resource(name: str, raw: bytes, patches: list, base: Path) -> None:
    owned = scope()
    chunks = parse_chunks(raw) if not name.startswith("outer:") else None
    cards = {f"{f}_{s[2].lower()}{s[:2]}_{int(s[3:])}" for s in owned["card_selectors"] for f in ("unif", "helm")}
    for p in patches:
        at, n = p["offset"], p["length"]
        require(type(at) is int and type(n) is int and n > 0 and 0 <= at <= len(raw)-n,
                "invalid UNI span bounds")
        data = shared._b765().replacement_bytes(base, p["replacement"])
        require(len(data) == n and sha(data) == p["after_sha256"], "replacement size/hash changed")
        current = raw[at:at+n]
        require(sha(current) in {p["before_sha256"], p["after_sha256"]}, "unexpected input span")
        if chunks is not None:
            sel = name[:-4]
            allowed = set()
            if sel in owned["helmet_selectors"]:
                families = owned.get("helmet_families", {}).get(sel, ["helmet00", "helmet02"])
                allowed |= {(chunks[i].offset, chunks[i].end_offset-chunks[i].offset,
                             "helmet00" if i == 11 else "helmet02") for i in (11, 12)
                            if ("helmet00" if i == 11 else "helmet02") in families}
            if sel in owned["digit_selectors"]:
                allowed |= {(chunks[i].offset, chunks[i].end_offset-chunks[i].offset, f"digit_{i}")
                            for i in range(13, 33)}
            require((at, n, p["label"]) in allowed, "UNI kit patch is outside owned texture chunks")
        else:
            old_chunk = parse_chunks(current)
            new_chunk = parse_chunks(data)
            require(len(old_chunk) == len(new_chunk) == 1 and old_chunk[0].kind == new_chunk[0].kind == "TXTR",
                    "UNI card span must be one TXTR")
            before = parse_texture(decode_chunk(current, old_chunk[0])[0], old_chunk[0])
            after = parse_texture(decode_chunk(data, new_chunk[0])[0], new_chunk[0])
            require((before.name, before.width, before.height, before.packed_format) ==
                    (after.name, after.width, after.height, after.packed_format), "UNI card identity changed")
            require(before.name in cards and before.width == before.height and
                    (before.width in (128, 256)) and
                    (name == "outer:3102" if before.width == 256 else name == "outer:3105") and
                    p["label"] == f"{before.name}_{before.width}", "unowned UNI card")


def repair(source: Path, output: Path, manifest: dict, base: Path) -> dict:
    b = shared._b765()
    b.refuse_links(source); b.refuse_links(output); b.refuse_links(base)
    require(source.resolve() != output.resolve() and not output.resolve().is_relative_to(source.resolve()),
            "output must be separate from input")
    ancestor = output
    while not ancestor.exists():
        ancestor = ancestor.parent
    pack_names = set()
    with bump._Image.open(source, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        for name, patches in manifest["resources"].items():
            entry = index.entries[int(name.split(":")[1])] if name.startswith("outer:") else by_name.get(name)
            require(entry is not None, f"resource absent: {name}")
            raw = b"".join(image.read_pack(o, at, n) for o, at, n in index.sub_extents(entry, 0, entry.size))
            validate_resource(name, raw, patches, base)
            for p in patches:
                parts = index.sub_extents(entry, p["offset"], p["length"])
                require(len(parts) == 1, "cross-pack UNI patch refused")
                pack_names.add(parts[0][0])
        needed = sum(image.pack_size(o) for o in pack_names if not (output / PACK_NAMES[o]).exists())
        if 0 not in pack_names and not (output / "0").exists():
            needed += image.index_size
        reserve = 50*1024**3 if ancestor.stat().st_dev == Path("/").stat().st_dev else 0
        require(shutil.disk_usage(ancestor).free-needed >= reserve, "writes would cross the disk floor")
        require(shutil.disk_usage("/").free >= 50*1024**3, "root filesystem is below the 50 GiB floor")
    receipt = shared.repair_packs(source, output, manifest, base)
    receipt.update(schema="b77/uni/repair-receipt/v1", order=["kitx", "sh1", "a5k", "uni"],
                   scope_sha256=sha(SCOPE.read_bytes()), runtime_witnessed=False, directory_growth=0)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("input", "output", "manifest", "receipt"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        b = shared._b765()
        b.refuse_links(args.receipt)
        require(args.receipt.resolve() != args.manifest.resolve() and
                not args.receipt.resolve().is_relative_to(args.input.resolve()) and
                args.receipt.resolve() not in {args.output.resolve()/n for n in PACK_NAMES}, "unsafe receipt path")
        doc = load_manifest(args.manifest)
        receipt = repair(args.input, args.output, doc, args.manifest.parent)
        receipt["manifest_sha256"] = sha(args.manifest.read_bytes())
        b.atomic_write(args.receipt, (json.dumps(receipt, indent=2)+"\n").encode())
        print(json.dumps({"receipt": str(args.receipt), "outside_scope_identical": True}))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"UNI refused: {exc}\n")


if __name__ == "__main__":
    main()

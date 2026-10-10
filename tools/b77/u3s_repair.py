#!/usr/bin/env python3
"""Beta 77 u3s: install built 2026 alternates in their uniform style slots on the SOFTDRINK 2K28 v0.5 disc files.

Two kinds of bytes, both owned by this job and both checked against the shipped bytes before anything is written:

* the alternate's spans in its two kit packages (``<code>H<S>.IFF`` / ``<code>A<S>.IFF``) and its Team Select cards
  (``outer:3102`` 256 px cards, ``outer:3105`` 128 px helm cards), from ``tools/b77/u3s_alternates.py compile``
  manifests: each span must read as its ``before`` (or, on a second pass, its ``after``) SHA-256;
* the style's year pair in the main roster (``ROST`` outer 0x4A37581D, team record +0x15A + 4 (S - 1)): 4 bytes
  that make Team Select read "2026  Alternate n". The team record is found by its asset code when the repair runs,
  so other jobs' roster edits elsewhere in the file do not move it; the pair must read the retail pair (or the new
  one) first.

Only the index and the packs that hold a change are written to ``--output``; every byte outside the declared spans is
proved identical, a second pass over the output is a no-op, and unexpected input is refused.

  u3s_repair.py --input "SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso" --output OUT/vc_53450030 \\
      --manifest COMPILED/native_manifest.json [--manifest ...] --recipes data/nfl2k5_uniform_alternates_2026.json \\
      --keys CIN:5 --receipt OUT/receipt.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
from mod_editor.core import nfl2k5_uniform_slots as us  # noqa: E402
from nfl_outer import PACK_NAMES  # noqa: E402

MANIFEST_SCHEMA = "b77/u3s/texture-repair/v1"
RECEIPT_SCHEMA = "b77/u3s/repair-receipt/v1"
ROSTER_ID = 0x4A37581D
KIT = re.compile(r"[0-9]{2}[HA][0-9]{1,2}\.IFF")
CARDS = re.compile(r"outer:(3102|3105)")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _b765():
    name = "b765_u1_repair"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools/b765/u1_repair.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def load_manifests(paths: list[Path], recipes: dict, keys: list[str]) -> list[tuple[dict, Path]]:
    """Each manifest must be one of the requested alternates and name only that slot's kits and the card files."""
    out = []
    for path in paths:
        doc = json.loads(path.read_text())
        require(doc.get("schema") == MANIFEST_SCHEMA, f"{path}: unsupported manifest")
        key = doc.get("key")
        require(key in keys, f"{path}: alternate {key} was not requested")
        recipe = recipes["alternates"][key]
        own = {f"{recipe['code']}{side}{recipe['style']}.IFF" for side in recipe["kits"]}
        for name in doc["resources"]:
            require(name in own or CARDS.fullmatch(name), f"{path}: {name} is not this alternate's resource")
        out.append((doc, path.parent))
    return out


def roster_patch(roster: bytes, code: str, style: int, before: tuple[int, int], after: tuple[int, int]) -> dict:
    """The 4-byte year pair of one style in the main roster, located by the team's asset code."""
    from mod_editor.core import nfl2k5_historic_styles as hs
    records = [(at, c) for at, c in hs.team_records(roster)[:32] if c == code]
    require(len(records) == 1, f"the main roster has {len(records)} team records with asset code {code}")
    at = 32 + records[0][0] + us.TABLE + 4 * (style - 1)
    current = struct.unpack_from("<HH", roster, at)
    require(current in (tuple(before), tuple(after)),
            f"team {code} style {style} reads {current}; expected {tuple(before)} (or {tuple(after)} when applied)")
    data = struct.pack("<HH", *after)
    return {"offset": at, "length": 4, "label": f"uniform_years_{code}_{style}",
            "before_sha256": sha(struct.pack("<HH", *before)), "after_sha256": sha(data), "data": data}


def apply_patches(original: bytes, patches: list[dict]) -> tuple[bytes, dict]:
    result = bytearray(original)
    occupied, spans = [], []
    for patch in sorted(patches, key=lambda p: p["offset"]):
        offset, length, data = patch["offset"], patch["length"], patch["data"]
        require(0 <= offset <= len(original) - length and len(data) == length, "patch span exceeds the file")
        require(not occupied or occupied[-1][1] <= offset, "overlapping patch spans")
        require(sha(data) == patch["after_sha256"], "replacement bytes changed")
        before = original[offset:offset + length]
        require(sha(before) in (patch["before_sha256"], patch["after_sha256"]),
                f"unexpected input bytes for {patch['resource']} {patch['label']} at {offset:#x}")
        result[offset:offset + length] = data
        occupied.append((offset, offset + length))
        spans.append({"resource": patch["resource"], "label": patch["label"],
                      "resource_offset": patch["resource_offset"], "pack_offset": offset, "length": length,
                      "before_sha256": sha(before), "after_sha256": sha(data), "already_applied": before == data})
    cursor, outside = 0, hashlib.sha256()
    for start, end in occupied + [(len(original), len(original))]:
        require(original[cursor:start] == result[cursor:start], "outside-scope bytes changed")
        outside.update(original[cursor:start])
        cursor = end
    return bytes(result), {"before_sha256": sha(original), "after_sha256": sha(result), "size": len(original),
                           "outside_scope_sha256": outside.hexdigest(), "outside_scope_identical": True,
                           "spans": spans}


def repair(source: Path, output: Path, manifests: list[tuple[dict, Path]], recipes: dict, keys: list[str]) -> dict:
    b = _b765()
    b.refuse_links(source)
    b.refuse_links(output)
    require(source.resolve() != output.resolve(), "source/output must differ")
    require(not (source.is_dir() and output.resolve().is_relative_to(source.resolve())),
            "output must not be inside the input directory")
    pack_patches: dict[int, list[dict]] = {}
    resources: dict[str, dict] = {}
    with bump._Image.open(source, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}

        def place(name: str, entry, patch: dict):
            parts = index.sub_extents(entry, patch["offset"], patch["length"])
            require(len(parts) == 1, f"{name}: a span crosses a pack")
            ordinal, offset, length = parts[0]
            require(length == patch["length"], "patch segment size changed")
            pack_patches.setdefault(ordinal, []).append(dict(patch, offset=offset, resource=name,
                                                            resource_offset=patch["offset"]))
            resources.setdefault(name, {"outer_index": entry.table_index, "spans": 0})["spans"] += 1

        for doc, base in manifests:
            for name, patches in doc["resources"].items():
                m = CARDS.fullmatch(name)
                entry = index.entries[int(m.group(1))] if m else by_name.get(name)
                require(entry is not None, f"resource absent: {name}")
                for patch in patches:
                    data = b.replacement_bytes(base, patch["replacement"])
                    place(name, entry, dict(patch, data=data))
        roster_entry = next((e for e in index.entries if e.name_id == ROSTER_ID), None)
        require(roster_entry is not None, "the main roster is missing")
        roster = b"".join(image.read_pack(o, off, n) for o, off, n in index.sub_extents(roster_entry, 0, roster_entry.size))
        labels = []
        for key in keys:
            recipe = recipes["alternates"][key]
            code, style = recipe["code"], int(recipe["style"])
            before = tuple(recipe["retail_pair"])
            after = tuple(recipe["label"])
            patch = roster_patch(roster, code, style, before, after)
            place("ROST", roster_entry, patch)
            labels.append({"key": key, "code": code, "style": style, "before": list(before), "after": list(after),
                           "reads_after": us.style_label(style, *after)})
        compiled = []
        for ordinal, patches in sorted(pack_patches.items()):
            size = image.pack_size(ordinal)
            require(size >= index.slots[ordinal] * bump.SECTOR_SIZE,
                    "physical archive is shorter than its declared allocation")
            original = image.read_pack(ordinal, 0, size)
            data, receipt = apply_patches(original, patches)
            compiled.append((PACK_NAMES[ordinal], data, receipt))
        outputs = [(output / name, data) for name, data, _ in compiled]
        if 0 not in pack_patches:
            outputs.insert(0, (output / "0", image.read_index_range(0, image.index_size)))
        b.publish_batch(outputs)
    return {"schema": RECEIPT_SCHEMA, "keys": keys, "labels": labels, "resources": resources,
            "disc_files": {f"vc_53450030/{name}": dict(r, readback=True) for name, _, r in compiled},
            "index_copied_unchanged": 0 not in pack_patches}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path, action="append")
    p.add_argument("--recipes", type=Path, default=ROOT / "data/nfl2k5_uniform_alternates_2026.json")
    p.add_argument("--keys", required=True)
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args(argv)
    b = _b765()
    receipt_path = b.refuse_links(a.receipt).resolve()
    source_path = b.refuse_links(a.input).resolve()
    require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
            "receipt must not overwrite any input file")
    recipes = json.loads(a.recipes.read_text())
    keys = [k for k in a.keys.split(",") if k]
    for key in keys:
        require(key in recipes["alternates"], f"no recipe {key}")
    manifests = load_manifests(a.manifest, recipes, keys)
    receipt = repair(a.input, a.output, manifests, recipes, keys)
    receipt["manifest_sha256"] = {str(path): sha(path.read_bytes()) for path in a.manifest}
    receipt["recipes_sha256"] = sha(a.recipes.read_bytes())
    b.atomic_write(a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(a.receipt), "scope_verified": True, "labels": receipt["labels"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Beta 77 u3r: write the redone socks (job u3r) into the SOFTDRINK 2K28 v0.5 disc files, after every other uniform job.

The spans come from ``tools/b77/u3r_socks.py build`` (manifest schema ``b77/u3r/texture-repair/v1``). Each span is one
equipment chunk (socks00 and its mud twin) of a kit package. A span must read as one of

  * the shipped v0.5 bytes (``before_sha256``),
  * the bytes an earlier job's repair left there (``also_before_sha256``: u3a's Bears 4 socks, u3b's Browns 4 socks),
  * or, on a second pass, this job's own ``after_sha256``,

otherwise the repair refuses. So it stacks after u1, u2a-d, u3s and u3a-e (and w1, which owns no equipment chunk) in
any order those jobs ran among themselves, and a second pass over its own output changes nothing. Only the declared
spans are written; every byte outside them is proved identical. Pack files that hold no span are not written.

  u3r_repair.py --input DISC_OR_PACK_DIR --output OUT/vc_53450030 --manifest COMPILED/native_manifest.json \\
      --receipt OUT/receipt.json
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
from nfl_outer import PACK_NAMES  # noqa: E402

MANIFEST_SCHEMA = "b77/u3r/texture-repair/v1"
CARDS = re.compile(r"outer:(3102|3105)")
KIT = re.compile(r"[0-9]{2}[HA][0-9]{1,2}\.IFF")
RECEIPT_SCHEMA = "b77/u3r/repair-receipt/v1"


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


def apply_patches(original: bytes, patches: list[dict]) -> tuple[bytes, dict]:
    result = bytearray(original)
    occupied, spans = [], []
    for patch in sorted(patches, key=lambda p: p["offset"]):
        offset, length, data = patch["offset"], patch["length"], patch["data"]
        require(0 <= offset <= len(original) - length and len(data) == length, "patch span exceeds the file")
        require(not occupied or occupied[-1][1] <= offset, "overlapping patch spans")
        require(sha(data) == patch["after_sha256"], "replacement bytes changed")
        before = original[offset:offset + length]
        accepted = {patch["before_sha256"], patch["after_sha256"], *patch.get("also_before_sha256", [])}
        require(sha(before) in accepted, f"unexpected input bytes for {patch['resource']} {patch['label']} at {offset:#x}")
        result[offset:offset + length] = data
        occupied.append((offset, offset + length))
        state = ("already_applied" if before == data else
                 "shipped_v05" if sha(before) == patch["before_sha256"] else "earlier_job_output")
        spans.append({"resource": patch["resource"], "label": patch["label"], "resource_offset": patch["resource_offset"],
                      "pack_offset": offset, "length": length, "input_state": state,
                      "before_sha256": sha(before), "after_sha256": sha(data)})
    cursor, outside = 0, hashlib.sha256()
    for start, end in occupied + [(len(original), len(original))]:
        require(original[cursor:start] == result[cursor:start], "outside-scope bytes changed")
        outside.update(original[cursor:start])
        cursor = end
    return bytes(result), {"before_sha256": sha(original), "after_sha256": sha(result), "size": len(original),
                           "outside_scope_sha256": outside.hexdigest(), "outside_scope_identical": True,
                           "spans": spans}


def repair(source: Path, output: Path, manifests: list[tuple[dict, Path]]) -> dict:
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
        for doc, base in manifests:
            for name, patches in doc["resources"].items():
                card = CARDS.fullmatch(name)
                entry = index.entries[int(card.group(1))] if card else by_name.get(name)
                require(entry is not None, f"resource absent: {name}")
                for patch in patches:
                    data = b.replacement_bytes(base, patch["replacement"])
                    parts = index.sub_extents(entry, patch["offset"], patch["length"])
                    require(len(parts) == 1, f"{name}: a span crosses a pack")
                    ordinal, offset, length = parts[0]
                    require(length == patch["length"], "patch segment size changed")
                    pack_patches.setdefault(ordinal, []).append(
                        dict(patch, data=data, offset=offset, resource=name, resource_offset=patch["offset"]))
                    resources.setdefault(name, {"outer_index": entry.table_index, "spans": 0})["spans"] += 1
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
    return {"schema": RECEIPT_SCHEMA, "resources": resources,
            "disc_files": {f"vc_53450030/{name}": dict(r, readback=True) for name, _, r in compiled},
            "index_copied_unchanged": 0 not in pack_patches}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path, action="append")
    p.add_argument("--receipt", required=True, type=Path)
    a = p.parse_args(argv)
    b = _b765()
    receipt_path = b.refuse_links(a.receipt).resolve()
    source_path = b.refuse_links(a.input).resolve()
    require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
            "receipt must not overwrite any input file")
    manifests = []
    for path in a.manifest:
        doc = json.loads(path.read_text())
        require(doc.get("schema") == MANIFEST_SCHEMA, f"{path}: unsupported manifest")
        for name in doc["resources"]:
            require(KIT.fullmatch(name) or CARDS.fullmatch(name), f"{path}: {name} is not a kit package or a card file")
        manifests.append((doc, path.parent))
    receipt = repair(a.input, a.output, manifests)
    receipt["manifest_sha256"] = {str(path): sha(path.read_bytes()) for path in a.manifest}
    b.atomic_write(a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(a.receipt), "scope_verified": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

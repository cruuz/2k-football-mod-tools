#!/usr/bin/env python3
"""Beta 77 sh1: apply the corrected Seahawks helmet spans (side logos facing the rear, the back wrap joined to them).

Runs AFTER kitx (the combined kit layer) on its output folder, or on the v0.5 image: the spans are the Seahawks'
``helmet02`` textures (chunk 12 of ``26H0``, ``26A0``, ``26H3``, ``26A3``, ``26H4``, ``26A4``) and the left-side logo
of the two alternates drawn with the same-image decal route (``00H7``, ``00A7``, ``16H9``, ``16A9``), which no earlier
job touches, plus the Team Select cards of those kits (resource 3102/3105 spans).

Only pinned spans are written: every span must read back as its exact ``before`` bytes (the v0.5 bytes; kitx leaves
these spans alone), or, on a second pass, its ``after`` bytes, and every byte outside the declared spans is proved
identical. Any other input is refused. The manifest and replacement binaries are private, game-derived build evidence
(``tools/b77/sh1_helmet.py compile``).

Resources are named ``<code><H|A><style>.IFF`` (the ten kit packages above) or ``outer:<index>`` (the Team Select card
resources 3102 and 3105; their spans are located in the bytes the input holds).

  # loose resources (as exported), e.g. for a quick decode check
  sh1_repair.py --resource-files --input DIR --output DIR --manifest native_manifest.json --receipt r.json
  # the disc: reads the image or an extracted vc_53450030 folder (kitx output), writes only the changed packs
  sh1_repair.py --input OUT_OF_KITX/vc_53450030 --output OUT/vc_53450030 --manifest ... --receipt ...
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

SCHEMA = "b77/sh1/texture-repair/v1"
RECEIPT_SCHEMA = "b77/sh1/repair-receipt/v1"
KIT = re.compile(r"(26[HA][034]|00[HA]7|16[HA]9)\.IFF")
OUTER = re.compile(r"outer:(3102|3105)")     # the Team Select card resources (unif/helm 256, helm 128)


def _b765():
    name = "b765_u1_repair"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "tools/b765/u1_repair.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_manifest(path: Path) -> dict:
    doc = json.loads(path.read_text())
    require(doc.get("schema") == SCHEMA, "unsupported manifest")
    require(set(doc["resources"]) and all(KIT.fullmatch(k) or OUTER.fullmatch(k) for k in doc["resources"]),
            "manifest names a resource this repair does not own")
    return doc


def repair_resources(source: Path, output: Path, manifest: dict, base: Path) -> dict:
    b = _b765()
    b.refuse_links(source); b.refuse_links(output)
    require(source.resolve() != output.resolve(), "source/output must differ")
    compiled = []
    for name, patches in manifest["resources"].items():
        require(KIT.fullmatch(name) is not None, "loose-resource mode handles the kit packages only")
        path = source / name
        b.refuse_links(path)
        require(path.is_file(), f"input resource missing: {name}")
        data, receipt = b.apply_spans(path.read_bytes(), patches, base)
        compiled.append((name, data, receipt))
    b.publish_batch([(output / name, data) for name, data, _ in compiled])
    return {"schema": RECEIPT_SCHEMA, "resources": {n: dict(r, readback=True) for n, _, r in compiled}}


def repair_packs(source: Path, output: Path, manifest: dict, base: Path) -> dict:
    """The source is the v0.5 image or an extracted (possibly already stacked) vc_53450030 folder.

    Only the index and the affected packs are materialized; full pack before/after hashes and the outside-scope
    proof show every resource outside the manifest stays exact."""
    b = _b765()
    b.refuse_links(source); b.refuse_links(output)
    require(source.resolve() != output.resolve(), "source/output must differ")
    require(not (source.is_dir() and output.resolve().is_relative_to(source.resolve())),
            "output must not be inside the input directory")
    pack_patches: dict[int, list[dict]] = {}
    mapping = []
    with bump._Image.open(source, writable=False) as image:
        index = bump._parsed_index(image)
        by_name = {bump.logical_name_for(e.name_id): e for e in index.entries}
        for name, patches in manifest["resources"].items():
            m = OUTER.fullmatch(name)
            entry = index.entries[int(m.group(1))] if m else by_name.get(name)
            require(entry is not None, f"resource absent: {name}")
            for patch in patches:
                require(type(patch["offset"]) is int and type(patch["length"]) is int and patch["length"] > 0,
                        "invalid resource span coordinates")
                parts = index.sub_extents(entry, patch["offset"], patch["length"])
                require(len(parts) == 1, "cross-pack patch needs explicitly segmented handling")
                ordinal, offset, length = parts[0]
                require(length == patch["length"], "patch segment size changed")
                pack_patches.setdefault(ordinal, []).append(dict(patch, offset=offset, resource=name,
                                                                resource_offset=patch["offset"]))
                mapping.append({"resource": name, "label": patch.get("label"), "resource_offset": patch["offset"],
                                "length": patch["length"], "pack": f"vc_53450030/{PACK_NAMES[ordinal]}",
                                "pack_offset": offset})
        compiled = []
        for ordinal, patches in sorted(pack_patches.items()):
            size = image.pack_size(ordinal)
            require(size >= index.slots[ordinal] * bump.SECTOR_SIZE,
                    "physical archive is shorter than its declared allocation")
            original = image.read_pack(ordinal, 0, size)
            data, receipt = b.apply_spans(original, patches, base)
            compiled.append((PACK_NAMES[ordinal], data, receipt))
        outputs = [(output / name, data) for name, data, _ in compiled]
        if 0 not in pack_patches:
            outputs.insert(0, (output / "0", image.read_index_range(0, image.index_size)))
        b.publish_batch(outputs)
    return {"schema": RECEIPT_SCHEMA,
            "disc_files": {f"vc_53450030/{n}": dict(r, readback=True) for n, _, r in compiled},
            "index_copied_unchanged": 0 not in pack_patches, "span_mapping": mapping}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--receipt", required=True, type=Path)
    p.add_argument("--resource-files", action="store_true")
    a = p.parse_args()
    b = _b765()
    receipt_path = b.refuse_links(a.receipt).resolve()
    source_path = b.refuse_links(a.input).resolve()
    require(receipt_path != source_path and not (source_path.is_dir() and receipt_path.is_relative_to(source_path)),
            "receipt must not overwrite any input file")
    require(receipt_path != a.manifest.resolve(), "receipt must not overwrite the repair manifest")
    manifest = load_manifest(a.manifest)
    fn = repair_resources if a.resource_files else repair_packs
    receipt = fn(a.input, a.output, manifest, a.manifest.parent)
    receipt["manifest_sha256"] = sha(a.manifest.read_bytes())
    b.atomic_write(a.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(json.dumps({"receipt": str(a.receipt), "scope_verified": True}))


if __name__ == "__main__":
    main()

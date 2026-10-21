#!/usr/bin/env python3
"""Correct v0.6 source target collisions, preserving its native installer payload.

No installed game byte changes here. The separate V1C native repair updates
Anniversary gameplay. This tool keeps the v0.6 full-install equality contract.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import modpack as m, modpack_files as f, modpack_sources as s

V06_SHA256 = "8f38472ec12d1c4d9745683d10e5df15d426b8b339ab9ff4a886bcfaf6caceb0"
PROJECT = "assets/documents/league-project.json"


def correct(source, output):
    source, output = f._path(source), f._output_path(output)
    m._require(m.hash_file(source) == V06_SHA256, "unexpected v0.6 pack hash")
    pack = m.load(source)
    manifest = copy.deepcopy(pack.manifest.raw)
    with zipfile.ZipFile(source) as original:
        document = json.loads(original.read(PROJECT))
        fixed = s.compose_project(document)
        content = (json.dumps(fixed, indent=2, sort_keys=True) + "\n").encode()
        with f._transaction(output, (source,)) as part:
            # Stream large native payloads; do not materialize a disc or assets.
            with zipfile.ZipFile(part, "w", allowZip64=True) as archive:
                for item in original.infolist():
                    if item.filename == "manifest.json":
                        continue
                    info = copy.copy(item)
                    info.compress_size = info.CRC = info.header_offset = 0
                    if item.filename == PROJECT:
                        archive.writestr(info, content)
                    else:
                        with original.open(item) as inp, archive.open(info, "w", force_zip64=True) as out:
                            shutil.copyfileobj(inp, out, 8 * 1024 * 1024)
                for asset in manifest["assets"]:
                    actual = archive.getinfo(asset["member"])
                    asset["compressed_bytes"] = actual.compress_size
                    if asset["member"] == PROJECT:
                        asset["length"] = len(content)
                        asset["sha256"] = hashlib.sha256(content).hexdigest()
                archive.writestr(original.getinfo("manifest.json"),
                    (json.dumps(manifest, indent=2) + "\n").encode())
    result = m.load(output)
    m._require(result.manifest.raw["files"] == pack.manifest.raw["files"]
               and result.manifest.raw["metadata"] == pack.manifest.raw["metadata"]
               and result.manifest.raw["result"] == pack.manifest.raw["result"], "native contract changed")
    with zipfile.ZipFile(output) as repaired, zipfile.ZipFile(source) as original:
        for name in original.namelist():
            if name in (PROJECT, "manifest.json"):
                continue
            # CRCs are not the proof: compare every uncompressed byte.
            with original.open(name) as a, repaired.open(name) as b:
                while True:
                    first, second = a.read(8 * 1024 * 1024), b.read(8 * 1024 * 1024)
                    m._require(first == second, "unowned pack member changed: " + name)
                    if not first:
                        break
    return dict(schema="b771/v1c/corrected-pack/v1", before_sha256=V06_SHA256,
                after_sha256=m.hash_file(output), before_edits=len(document["edits"]),
                after_edits=len(fixed["edits"]), merged_targets=len(document["edits"]) - len(fixed["edits"]),
                unchanged_native_contract=True, outside_scope_members_identical=True,
                result_sha256=manifest["result"]["sha256"], size=output.stat().st_size)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = correct(args.input, args.output)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", newline="\n")
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        receipt["after_sha256"] + "  " + args.output.name + "\n", newline="\n")
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

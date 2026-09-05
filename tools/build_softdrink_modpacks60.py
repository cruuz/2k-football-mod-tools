#!/usr/bin/env python3
"""Rebuild beta-60 packs and prove applications using disposable workspace copies.

Private inputs and outputs are never committed. Run from this checkout:
  python3 tools/build_softdrink_modpacks60.py --retail '/path/to/retail.xiso.iso'
The report contains whole-image and individual XDVDFS-file SHA-256 evidence.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build, modpack, nfl2k5_depth_chart_rows as rows
from mod_editor.core import nfl2k5_source_cache, nfl2k5_bump_strength as strength

PRESETS = {
    "basic": ("0.9", "2004 game, just the 2K5 fixes"),
    "advanced": ("1.2", "everything modern, including X / Z / SLOT and nickel / dime playbook roles"),
    "experimental": ("0.5", "advanced + widescreen + dynamic kickoff + practice squads + FG laces + SPECIAL depth-chart tab; experimental and unwitnessed"),
}


def files(path):
    fd = modpack._open(path, os.O_RDONLY)
    try:
        entries, _ = modpack._xdvdfs_module().parse_xdvdfs(fd, path.stat().st_size)
        result = {}
        for name, entry in entries.items():
            if entry.attributes & 0x10:
                continue
            h = modpack.hashlib.sha256()
            for at in range(0, entry.size, modpack.BLOCK):
                h.update(modpack._pread_exact(fd, min(modpack.BLOCK, entry.size - at), entry.byte_offset + at, name))
            result[name] = {"sector": entry.sector, "size": entry.size, "sha256": h.hexdigest()}
        e = entries["default.xbe"]
        xbe = modpack._pread_exact(fd, e.size, e.byte_offset, "default.xbe")
        result["default.xbe"]["rows_status"] = rows.status(xbe)
        result["default.xbe"]["section_digests_valid"] = all(
            s.stored_digest == strength.section_digest(xbe, s) for s in strength._sections(xbe) if s.raw_size)
        return result
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / ".scratch" / "softdrink60")
    parser.add_argument("--preset", choices=tuple(PRESETS), action="append")
    args = parser.parse_args()
    work = args.output.resolve()
    if ROOT / ".scratch" not in work.parents:
        raise SystemExit("Proof outputs must live below this checkout's .scratch directory")
    work.mkdir(parents=True, exist_ok=True)
    (ROOT / ".scratch" / ".gitignore").write_text("*\n", encoding="utf-8")
    # Keep generated art within the writable workspace, retaining the existing
    # source-cache ownership, mode, input-digest, and generated-art checks.
    private_cache = work / "private-cache"
    nfl2k5_source_cache.default_cache_root = lambda: private_cache
    base = args.retail.resolve()
    before = base.stat()
    base_sha = modpack.hash_file(base)
    if before.st_size != modpack.RETAIL_XISO_SIZE or base_sha != modpack.RETAIL_XISO_SHA256:
        raise SystemExit("Proof requires the pinned retail XISO")
    base_files = files(base)
    report_path = work / "proof.json"
    proof = json.loads(report_path.read_text()) if report_path.exists() else {
        "schema": "astra_modpack_grow_proof/v1", "retail": {"path": str(base), "size": before.st_size,
            "sha256": base_sha, "files": base_files}, "presets": {}}
    last = [None]
    def progress(stage, done, total):
        if stage != last[0]:
            print(time.strftime("%H:%M:%S"), stage, flush=True)
            last[0] = stage
    for preset in args.preset or PRESETS:
        version, description = PRESETS[preset]
        disc = work / f"{preset}.built.xiso.iso"
        applied = work / f"{preset}.applied.xiso.iso"
        pack = work / f"SOFTDRINK-patch-{preset}-v{version}.2k5patch"
        if disc.exists():
            disc.unlink()
        plan = mod_build.apply_preset(mod_build.BuildPlan(source=str(base), target=str(disc)), f"softdrink_{preset}")
        assert plan.depth_chart_rows == (preset == "experimental")
        print(f"BUILD {preset} SPECIAL={plan.depth_chart_rows}", flush=True)
        build = mod_build.build(plan, progress)
        (work / f"{preset}.build.json").write_text(json.dumps(build, indent=2, default=lambda obj: dataclasses.asdict(obj) if dataclasses.is_dataclass(obj) else str(obj)), encoding="utf-8")
        exported = modpack.export(base, disc, pack, {"name": f"SOFTDRINK patch: {preset}",
            "version": version, "author": "SOFTDRINKTV", "description": f"beta-60 {preset.upper()}: {description}"},
            overwrite=True, progress=progress)
        checked = modpack.check(pack, base)
        assert checked["state"] == "ready", checked
        applied_receipt = modpack.apply(pack, base, applied, overwrite=True, progress=progress)
        assert applied_receipt["target"]["matches_author_result"], applied_receipt
        after_check = modpack.check(pack, applied)
        assert after_check["state"] == "applied", after_check
        built_files, applied_files = files(disc), files(applied)
        assert built_files == applied_files
        assert base_files.keys() == applied_files.keys()
        assert applied_files["default.xbe"]["section_digests_valid"]
        if preset == "experimental":
            assert applied_files["default.xbe"]["rows_status"] == "applied"
        for name, entry in applied_files.items():
            if name != "default.xbe":
                assert (entry["sector"], entry["size"]) == (base_files[name]["sector"], base_files[name]["size"])
        proof["presets"][preset] = {"build_steps": [s["step"] for s in build["steps"]],
            "pack": str(pack), "pack_bytes": pack.stat().st_size, "pack_sha256": modpack.hash_file(pack),
            "format": modpack.inspect(pack)["format"], "export": exported,
            "check_base": checked["state"], "check_applied": after_check["state"], "apply": applied_receipt,
            "files": applied_files, "all_files_equal_build": True,
            "unchanged_retail_files": [n for n in base_files if base_files[n]["sha256"] == applied_files[n]["sha256"]]}
        report_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
        print(f"PROVED {preset}: {applied_receipt['target']}", flush=True)
        # Preserve the experimental build and apply pair for independent review.
        if preset != "experimental":
            disc.unlink()
            applied.unlink()
    after = base.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    assert modpack.hash_file(base) == base_sha
    proof["retail_unchanged_after_proof"] = True
    report_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print("PATCHES_DONE", report_path, flush=True)


if __name__ == "__main__":
    main()

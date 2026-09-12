#!/usr/bin/env python3
"""Measure baseline/cold/warm/one-PNG builds; remove all private outputs.

Real-disc mode requires a prepared 402-edit canonical project and writable
Storage. --synthetic uses two small fabricated spans and makes no retail claim.
Export the old tool with git show BASE:tools/nfl2k5_visual_mod_project.py > baseline.py.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/mod_editor")]


def load_tool(path, name):
    # Preserve the real tool's repo root for its imports and compatibility pins.
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/nfl2k5_visual_mod_project.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def instrument(module, records):
    for name in ("validate_source", "prepare_project", "bind_prepared_to_source", "verify_union",
                 "copy_artifacts", "verify_prepared_pins", "verify_artifacts"):
        original = getattr(module, name)
        def wrapped(*args, _name=name, _original=original, **kwargs):
            start = time.perf_counter()
            try:
                return _original(*args, **kwargs)
            finally:
                records[_name] = records.get(_name, 0.0) + time.perf_counter() - start
        setattr(module, name, wrapped)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-tool", type=Path, required=True)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--source", type=Path, default=Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
    parser.add_argument("--index", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--scratch", type=Path, default=Path("/media/noah/Storage/.b68-t1"))
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.synthetic and (args.project is None or args.index is None or args.inventory is None):
        parser.error("real-disc mode needs --project (402 edits), --index and --inventory")
    args.scratch.mkdir(parents=True, exist_ok=True)
    if not args.synthetic and args.scratch.stat().st_dev == Path("/").stat().st_dev:
        parser.error("real-disc benchmark must not write large files on /")
    old = load_tool(args.baseline_tool, "_b68_baseline")
    new = load_tool(ROOT / "tools/nfl2k5_visual_mod_project.py", "_b68_current")
    report = {"scope": "synthetic two-edit real-codec workflow" if args.synthetic else "402-edit retail-derived workflow", "runs": []}
    with tempfile.TemporaryDirectory(prefix="benchmark-", dir=args.scratch) as folder:
        root = Path(folder).resolve()
        if args.synthetic:
            import b661_build_fixture as fixture
            from nfl_txtr import encode_rgba_png
            equipment, _ = fixture.create(root)
            fixture.configure(old, root)
            fixture.configure(new, root)
            source, index, inventory = root / "source.iso", root / "0", root / "inventory.json"
            png = root / "jersey.png"
            png.write_bytes(encode_rgba_png(512, 256, bytes((30, 190, 220, 255)) * (512 * 256)))
            asset, equip_png = equipment.png(independent=False, rgba=bytes((20, 150, 80, 255)) * (32 * 32))
            value = dict(schema=new.SCHEMA, purpose="T1 bounded timing proof", edits=[
                dict(kind="torso", asset_code="18", side="H", variant=0, clean_png=str(png), mud_png=None, mud_mode="darken_60"),
                dict(kind="uniform_equipment_texture", asset_id=asset, png=str(equip_png))])
        else:
            source, index, inventory = args.source, args.index, args.inventory
            original = new.read_project(args.project)
            if len(original.value["edits"]) != 402:
                parser.error("real-disc project must contain exactly 402 edits")
            value = json.loads(original.payload)
            # Freeze private benchmark inputs. Never edit the caller's artwork.
            copies = {}
            for pin in new.pin_project_inputs(original).values():
                destination = root / f"input-{len(copies):04d}{pin.path.suffix}"
                destination.write_bytes(pin.payload)
                copies[str(pin.path)] = destination
            for edit in value["edits"]:
                for field in ("png", "clean_png", "mud_png", "recipe", "wav"):
                    if edit.get(field):
                        original_path = (original.path.parent / edit[field]).resolve()
                        edit[field] = str(copies[str(original_path)])
            # Choose an independent texture so one change means one compile unit.
            first = next(row for row in value["edits"] if row["kind"] in {"torso", "sleeve", "pants", "live_helmet", "team_select"})
            png = Path(first.get("clean_png", first.get("png")))
        report["edit_count"] = len(value["edits"])
        report["kinds"] = sorted({row["kind"] for row in value["edits"]})
        project = root / "project.json"
        project.write_bytes(new.canonical_json(value))
        old_stats, new_stats = {}, {}
        instrument(old, old_stats)
        instrument(new, new_stats)
        for label, module in (("before", old), ("cold", new), ("warm", new), ("one_change", new)):
            if label == "one_change":
                from PIL import Image
                with Image.open(png) as image:
                    rgba = image.convert("RGBA")
                # Change a visible block, large enough to survive quantization.
                for y in range(min(32, rgba.height)):
                    for x in range(min(32, rgba.width)):
                        r, g, b, a = rgba.getpixel((x, y))
                        rgba.putpixel((x, y), (255-r, 255-g, 255-b, a))
                rgba.save(png)
            stats = old_stats if label == "before" else new_stats
            stats.clear()
            out, manifest, artifacts = root / (label + ".iso"), root / (label + ".json"), root / label
            log = io.StringIO()
            os.environ["NFL2K5_DISABLE_NATIVE_LZ"] = "1" if label == "before" else "0"
            start = time.perf_counter()
            with contextlib.redirect_stdout(log):
                result = module.build(project, source, out, manifest, artifacts, index, inventory)
                built = time.perf_counter()
                if label == "before":
                    module.verify(project, source, out, manifest, artifacts, index, inventory)
                else:
                    module.verify_written(project, source, out, manifest, artifacts, module.file_digest(manifest))
                verified = time.perf_counter()
            row = dict(run=label, build_s=built-start, verify_s=verified-built, total_s=verified-start,
                       phases=dict(stats), backend_log=log.getvalue().splitlines(),
                       output_sha256=module.file_digest(out))
            report["runs"].append(row)
            # Release each disc immediately; the independent full hash remains.
            out.unlink()
        hashes = [row["output_sha256"] for row in report["runs"]]
        if not hashes[0] == hashes[1] == hashes[2]:
            raise RuntimeError("baseline/cold/warm XISO bytes differ")
        if hashes[2] == hashes[3]:
            raise RuntimeError("the one-PNG edit did not change the output")
        report["baseline_cold_warm_byte_identical"] = True
    args.report.write_bytes((json.dumps(report, indent=2, sort_keys=True)+"\n").encode())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Private offline file-pack proof. Never invokes a disc builder or emulator.

Requires space for the pack, one synthetic input, and one output. Generated
images are deleted after each successful case; receipts retain only hashes.
Run with /usr/bin/time -v for external Linux peak-RSS evidence. When two full
images exceed the scratch budget, --stream-fixtures applies retail to disk and
reconstructs raw/reordered fixtures directly into a byte comparison with E.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import modpack as m, modpack_files as f, xdvdfs_compact as xc


def files(path):
    with path.open("rb", buffering=0) as stream:
        layout = xc.read_layout(stream)
        return {p: dict(size=e.size, sha256=f._digest(stream, e.byte_offset, e.size))
                for p, e in layout.entries.items() if not e.attributes & 0x10}


def synthetic(source, target, *, raw=False):
    if target.exists():
        raise ValueError(f"Refusing to overwrite a proof input: {target}")
    with source.open("rb", buffering=0) as src, target.open("w+b", buffering=0) as dst:
        layout = xc.read_layout(src)
        if raw:
            base = 0x18300000
            # A real XDVDFS video filesystem before the game, not just zeros.
            header = bytearray(xc.SECTOR)
            header[:20] = header[-20:] = xc.xiso.XDVDFS_MAGIC
            name = b"VIDEO_TS"
            directory = struct.pack("<HHIIBB", 0, 0, 0, 0, 0x10, len(name)) + name
            directory += bytes(xc.align(len(directory), 4) - len(directory))
            struct.pack_into("<II", header, 20, 33, len(directory))
            xc.write_at(dst, 32 * xc.SECTOR, header)
            xc.write_at(dst, 33 * xc.SECTOR, directory)
            for at in range(0, layout.size - layout.base, f.BLOCK):
                data = xc.read_at(src, layout.base + at, min(f.BLOCK, layout.size - layout.base - at))
                if data.strip(b"\0"):
                    xc.write_at(dst, base + at, data)
            dst.truncate(base + layout.size - layout.base)
        else:
            plan = xc.plan(layout)
            cursor = min(r["offset"] for r in plan["files"] if r["size"])
            rows = []
            for row in reversed(plan["files"]):
                row = dict(row, offset=cursor if row["size"] else 0)
                rows.append(row)
                parent, field = layout.nodes[row["path"]]
                struct.pack_into("<I", plan["directories"][parent], field, row["offset"] // xc.SECTOR)
                cursor += xc.align(row["size"]) + 3 * xc.SECTOR
            xc.write_at(dst, 32 * xc.SECTOR, plan["header"])
            for path, data in plan["directories"].items():
                xc.write_at(dst, plan["destinations"][path], data)
            for row in rows:
                for at in range(0, row["size"], f.BLOCK):
                    data = xc.read_at(src, row["source_offset"] + at, min(f.BLOCK, row["size"] - at))
                    if data.strip(b"\0"):
                        xc.write_at(dst, row["offset"] + at, data)
            dst.truncate(xc.align(cursor, 32 * xc.SECTOR))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("retail", "finished", "pack", "work"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--scratch-limit", type=int, default=20_000_000_000)
    parser.add_argument("--stream-fixtures", action="store_true",
                        help="prove raw/reordered reconstruction without allocating a second full image")
    parser.add_argument("--keep-output", action="store_true", help="retain only the final applied image for manual xemu acceptance")
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if args.stream_fixtures and args.keep_output:
        raise SystemExit("--stream-fixtures cannot retain a fixture output")
    source_bytes = args.retail.stat().st_size + 0x18300000
    image_bytes = max(source_bytes, args.finished.stat().st_size) if args.stream_fixtures else source_bytes + args.finished.stat().st_size
    # Include existing receipts/bundles, plus the pack when stored outside work.
    existing = sum(p.stat().st_size for p in work.rglob("*") if p.is_file())
    if not args.pack.resolve().is_relative_to(work):
        existing += args.pack.stat().st_size
    needed = existing + image_bytes
    if needed > args.scratch_limit:
        raise SystemExit(f"Need at most {needed:,} bytes for this proof; scratch limit is {args.scratch_limit:,}")
    if needed > __import__('shutil').disk_usage(work).free + args.pack.stat().st_size:
        raise SystemExit("Not enough free space for the complete three-layout proof")
    pack = m.load(args.pack)
    before_stat = args.retail.stat()
    before = files(args.retail)
    expected = files(args.finished)
    receipt_path = work / "proof-E.json"
    proof = dict(schema="softdrink_file_pack_proof/v1", pack_sha256=m.hash_file(args.pack),
                 expected=expected, retail=before, cases={}, negatives={}, scratch_upper_bound_bytes=needed)
    def save(): receipt_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    def progress(stage, done, total):
        if stage != progress.last:
            print(time.strftime("%H:%M:%S"), stage, flush=True)
            progress.last = stage
    progress.last = None
    for case in ("retail", "raw", "repacked"):
        source = args.retail if case == "retail" else work / f"synthetic-{case}.iso"
        out = work / f"applied-{case}.xiso.iso"
        if case != "retail":
            print("Creating", case, flush=True)
            synthetic(args.retail, source, raw=case == "raw")
            assert files(source) == before
        print("Applying", case, flush=True)
        streamed = args.stream_fixtures and case != "retail"
        if streamed:
            result = f.verify_against(pack, source, args.finished, progress=progress)
            result["proof_mode"] = "streamed reconstruction; no output image allocated"
        else:
            result = m.apply(pack, source, out, progress=progress)
            observed = files(out)
            assert observed == expected
            with args.finished.open("rb", buffering=0) as author, out.open("rb", buffering=0) as actual:
                left, right = xc.read_layout(author), xc.read_layout(actual)
                for path in expected:
                    a, b = left.entries[path], right.entries[path]
                    for offset in range(0, a.size, f.BLOCK):
                        count = min(f.BLOCK, a.size - offset)
                        assert xc.read_at(author, a.byte_offset + offset, count) == xc.read_at(actual, b.byte_offset + offset, count)
            result["proof_mode"] = "disk apply plus independent read-back byte comparison"
        result["all_files_equal_finished"] = True
        result["independent_byte_comparison"] = True
        result["output_allocated_bytes"] = 0 if streamed else getattr(out.stat(), "st_blocks", 0) * 512
        result["scratch_logical_bytes"] = sum(p.stat().st_size for p in work.rglob("*") if p.is_file())
        assert result["scratch_logical_bytes"] <= args.scratch_limit
        proof["cases"][case] = result
        save()
        if streamed:
            pass
        elif case != "repacked" or not args.keep_output:
            out.unlink()
        else:
            proof["retained_output"] = str(out)
        if case != "retail":
            # Negative fixtures reuse only our disposable synthetic source.
            with source.open("r+b", buffering=0) as stream:
                layout = xc.read_layout(stream)
                entry = layout.entries["default.xbe"]
                old = xc.read_at(stream, entry.byte_offset, 1)
                xc.write_at(stream, entry.byte_offset, bytes([old[0] ^ 1]))
            negative = m.check(pack, source)
            assert negative["state"] == "mismatch"
            proof["negatives"]["modded-" + case] = negative["explanation"]
            with source.open("r+b") as stream:
                stream.truncate(layout.base + 100 * xc.SECTOR)
            negative = m.check(pack, source)
            assert negative["state"] == "mismatch"
            proof["negatives"]["truncated-" + case] = negative["explanation"]
            source.unlink()
            save()
    wrong = work / "wrong-game.iso"
    with wrong.open("wb") as stream:
        stream.truncate(65536)
        stream.seek(0x8000)
        stream.write(b"\1CD001")
        stream.seek(0x9000)
        stream.write(b"SYSTEM.CNF")
    negative = m.check(pack, wrong)
    assert negative["state"] == "mismatch"
    proof["negatives"]["ps2"] = negative["explanation"]
    wrong.unlink()
    with wrong.open("wb") as stream:
        header = bytearray(xc.SECTOR)
        header[:20] = header[-20:] = xc.xiso.XDVDFS_MAGIC
        name, data = b"default.xbe", b"XBEH-other-game"
        record = struct.pack("<HHIIBB", 0, 0, 34, len(data), 0x80, len(name)) + name
        record += bytes(xc.align(len(record), 4) - len(record))
        struct.pack_into("<II", header, 20, 33, len(record))
        stream.seek(32 * xc.SECTOR); stream.write(header)
        stream.seek(33 * xc.SECTOR); stream.write(record)
        stream.seek(34 * xc.SECTOR); stream.write(data)
    negative = m.check(pack, wrong)
    assert negative["state"] == "mismatch"
    proof["negatives"]["wrong-xbox-game"] = negative["explanation"]
    wrong.unlink()
    assert files(args.retail) == before
    assert args.retail.stat().st_mtime_ns == before_stat.st_mtime_ns
    proof["retail_unchanged"] = True
    try:
        import resource
        proof["peak_rss_kib_linux"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        pass
    save()
    print("PROVED OFFLINE", receipt_path, flush=True)


if __name__ == "__main__":
    main()

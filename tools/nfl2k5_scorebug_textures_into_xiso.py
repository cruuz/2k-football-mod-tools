#!/usr/bin/env python3
"""Put replacement scorebug textures into an already-modified NFL 2K5 XISO (local, xemu-only).

The shipped workflow (`tools/nfl_scorebug_xiso_workflow.py`) is fail-closed to the retail XISO
hash.  This tool reuses its strict PNG importer (`nfl_scorebug_png_import.build_import`, which
quantizes to P8 and refits the fixed VC-LZ span) but writes the resulting span into any XISO
whose target span still holds the retail bytes, in place.  Targets: score_buga (64x64 frame
atlas), shield_espn (128x64 ESPN strip), digital_font (128x128 shared digits).

usage: nfl2k5_scorebug_textures_into_xiso.py XISO --score-buga PNG --shield-espn PNG [--index INDEX] [--audit AUDIT]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os


def _pread(fd: int, count: int, offset: int) -> bytes:
    """Positional read; Windows has no os.pread, so seek/read/restore there."""
    preader = getattr(os, "pread", None)
    if preader is not None:
        return preader(fd, count, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.read(fd, count)
    finally:
        os.lseek(fd, here, os.SEEK_SET)


def _pwrite(fd: int, data: bytes, offset: int) -> int:
    """Positional write; Windows has no os.pwrite, so seek/write/restore there."""
    pwriter = getattr(os, "pwrite", None)
    if pwriter is not None:
        return pwriter(fd, data, offset)
    here = os.lseek(fd, 0, os.SEEK_CUR)
    try:
        os.lseek(fd, offset, os.SEEK_SET)
        return os.write(fd, data)
    finally:
        os.lseek(fd, here, os.SEEK_SET)
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import nfl_uniform_color_xiso_direct_patch as xc  # noqa: E402
from nfl_scorebug_png_import import DEFAULT_AUDIT, build_import  # noqa: E402

DEFAULT_INDEX = Path(os.environ.get("NFL2K5_RETAIL_INDEX", "retail-packs/0"))   # extracted pack index, developer machines only


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xiso")
    ap.add_argument("--score-buga")
    ap.add_argument("--shield-espn")
    ap.add_argument("--digital-font")
    ap.add_argument("--index", default=str(DEFAULT_INDEX))
    ap.add_argument("--audit", default=str(ROOT / DEFAULT_AUDIT))
    args = ap.parse_args()
    jobs = [(n, p) for n, p in (("score_buga", args.score_buga), ("shield_espn", args.shield_espn),
                                ("digital_font", args.digital_font)) if p]
    if not jobs:
        raise SystemExit("nothing to do")
    receipts = []
    fd = os.open(args.xiso, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        image_size = os.fstat(fd).st_size
        pack_extents: dict[str, tuple[int, int]] = {}
        for name, png in jobs:
            replacement, _preview, value = build_import(Path(args.index), Path(args.audit), name, Path(png))
            target = value["target"]
            # The audit's xiso_absolute_span_offset is where the span sat in the rip the audit was
            # taken on.  This image may lay its packs out differently, so the pack is resolved
            # through ITS directory and only the pack-relative offset is trusted.
            pack_path = str(target.get("xiso_pack_path") or target.get("pack_path") or "vc_53450030/0")
            if pack_path not in pack_extents:
                pack_extents[pack_path] = xc.pack_extent(fd, image_size, pack_path)
            pack_offset, pack_size = pack_extents[pack_path]
            audited_size = int(target.get("xiso_pack_size") or target.get("pack_size") or 0)
            if audited_size and audited_size != pack_size:
                raise SystemExit(f"{name}: {pack_path} in {args.xiso} is {pack_size} bytes, "
                                 f"not the audited {audited_size}")
            absolute = pack_offset + int(target["pack_offset"])
            current = _pread(fd, len(replacement), absolute)
            # Keep the wrapper retail: refill the stream to the stored body instead of raising the
            # in-place scratch word (the loader hangs on large raised values; see nfl_vc_lz_fill).
            import nfl_txtr
            import nfl_vc_lz_fill
            if sha(current) == target["span_sha256"]:
                template = current
            else:
                template = None
            chunk = nfl_txtr.parse_chunks(replacement, allow_trailing=True)[0]
            decoded, _ = nfl_txtr.decode_chunk(replacement, chunk)
            if template is not None:
                replacement, fill = nfl_vc_lz_fill.rebuild_fixed_span_filled(template, decoded)
                print(f"{name}: filled {fill.filled_bytes}/{fill.stored_size}, scratch {fill.scratch_bytes} (retail), wrapper identical {fill.wrapper_identical}")
            if sha(current) == target["span_sha256"]:
                state = "retail"
            elif current == replacement:
                state = "already"
            else:
                raise SystemExit(f"{name}: span at {absolute:#x} is neither retail nor this replacement")
            if state == "retail":
                _pwrite(fd, replacement, absolute)
                if _pread(fd, len(replacement), absolute) != replacement:
                    raise SystemExit(f"{name}: readback failed")
            receipts.append({"target": name, "png": str(png), "absolute": absolute, "pack_byte_offset": pack_offset,
                             "span_size": len(replacement),
                             "state_before": state, "span_sha256_after": sha(replacement),
                             "quantization": value.get("quantization") or value.get("import", {}).get("quantization")})
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps(receipts, indent=1, default=str)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

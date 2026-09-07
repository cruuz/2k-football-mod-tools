"""Generic MyCareer disc recipe. EXPERIMENTAL / UNWITNESSED.

Streams a new image through temporary staging and the existing XBE relocation
writer. No player name, prepared save or setup file is an input. This is a
development recipe until the playable-loop acceptance in the report is met.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_throw_tuning as disc
from mod_editor.core import nfl2k5_depth_chart_storage as storage
from mod_editor.core import platform_compat as io
from tools.nfl2k5_xbe_space import read_requests

MIN_FREE = 100_000_000_000
CHUNK = 4 * 1024**2


def build(source, target, requests):
    source = Path(source).expanduser().resolve(strict=True)
    target = Path(target).expanduser().resolve()
    if source == target or target.exists():
        raise ValueError("output must be a separate new image")
    target.parent.mkdir(parents=True, exist_ok=True)
    root = Path(target.anchor)
    with source.open("rb") as original:
        before = os.fstat(original.fileno())
        off, length = disc.image_xbe_extent(original.fileno(), before.st_size)
        if not 0 < length <= 16 * 1024**2:
            raise ValueError("default.xbe extent exceeds 16 MiB")
        executable = io.pread(original.fileno(), length, off)
        if len(executable) != length:
            raise ValueError("short read of source default.xbe")
        allocated, allocation = mode.space.apply(executable, requests, scaleout=True)
        patched, patch = mode.apply(allocated)
        allowance = before.st_size + len(patched) + 2048
        free = shutil.disk_usage(target.parent).free
        if shutil.disk_usage(root).free < MIN_FREE:
            raise ValueError("root drive must retain at least 100 GB free")
        reserve = MIN_FREE if os.stat(target.parent).st_dev == os.stat(root).st_dev else 0
        if free - allowance < reserve:
            raise ValueError("insufficient space for the image and required free-space reserve")
        digest = hashlib.sha256()
        with tempfile.TemporaryDirectory(prefix="mycareer-disc-", dir=target.parent) as folder:
            staged = Path(folder).resolve() / "generic.xiso.iso"
            with staged.open("w+b") as output:
                copied = 0
                original.seek(0)
                while copied < before.st_size:
                    chunk = original.read(min(CHUNK, before.st_size - copied))
                    if not chunk:
                        raise ValueError("source image shrank during the copy")
                    output.write(chunk)
                    digest.update(chunk)
                    copied += len(chunk)
                output.flush()
                now = os.fstat(original.fileno())
                if (now.st_size, now.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                    raise ValueError("source image changed during the copy")
                relocation = storage.write_image_xbe(output.fileno(), patched)
                new_off, new_length = disc.image_xbe_extent(output.fileno(), os.fstat(output.fileno()).st_size)
                if new_length != len(patched) or io.pread(output.fileno(), new_length, new_off) != patched:
                    raise ValueError("written default.xbe differs")
                os.fsync(output.fileno())
                size = os.fstat(output.fileno()).st_size
            receipt = {
                "schema": "nfl2k5.mycareer.generic-disc.v1", "experimental": True,
                "runtime_witnessed": False, "m2_accepted": False,
                "source_sha256": digest.hexdigest(), "source_size": before.st_size,
                "output_size": size, "file_growth": size - before.st_size,
                "source_xbe_sha256": hashlib.sha256(executable).hexdigest(),
                "output_xbe_sha256": hashlib.sha256(patched).hexdigest(),
                "allocation": allocation, "patch": patch, "relocation": relocation,
                "setup_files": 0, "executable_seed_bytes": 0, "journal_files": 0,
            }
            # Every reader/writer of the stage is closed before replacement.
            if target.exists():
                raise ValueError("output appeared during the build")
            os.replace(staged, target)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--requests", type=Path, required=True, help="complete allocator request union JSON")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.receipt.exists() or args.receipt.resolve() in (args.source.resolve(), args.output.resolve()):
            raise ValueError("receipt must be a separate new file")
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt = build(args.source, args.output, read_requests(args.requests))
        args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"MyCareer disc: {exc}\n")
    print(f"Wrote {args.output}; EXPERIMENTAL / UNWITNESSED; M2 acceptance remains pending.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

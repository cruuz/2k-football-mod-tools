#!/usr/bin/env python3
"""Build the PS2 Save Toolkit release archive.

The toolkit is the command-line half of the PlayStation 2 save lane: the
writer, its independent verifier, the validator, and the small set of
repo-local modules they import.  Everything is standard-library Python, so the
archive has no dependencies beyond Python 3 -- no PyQt5, no Pillow, no build
step for the person who downloads it.

The archive is built **deterministically** (fixed mtimes, sorted order,
normalised ownership and permissions) so the same source tree always produces
the same bytes and the same SHA-256.

A retail-free gate runs before anything is written: every payload file must be
one of the declared modules, must be plain text, and must not contain game
data, disc images, memory-card images or save payloads.  This repository never
ships game bytes and the toolkit is no exception -- the user brings their own
save.

Usage::

    python3 packaging/build_ps2_save_toolkit.py --output-dir dist/
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import tarfile
import io

ROOT = Path(__file__).resolve().parents[1]

# Fixed timestamp so archives are byte-reproducible (2026-01-01T00:00:00Z).
SOURCE_DATE_EPOCH = 1767225600

TOOLKIT_NAME = "NFL2K5-PS2-Save-Toolkit"

# The transitive import closure of the two entry points, plus the validator.
PAYLOAD = (
    "tools/nfl2k5_ps2_save.py",
    "tools/nfl2k5_ps2_save_verify.py",
    "tools/validate_nfl2k5_ps2_save.sh",
    "tools/nfl_outer.py",
    "tools/nfl_roster.py",
    "tools/nfl_scene_probe.py",
    "tools/nfl_txtr.py",
    "docs/product/NFL2K5_PS2_SAVE_PIPELINE.md",
    "LICENSE",
)

# Leading signatures of the binary formats this project must never ship.
# These are matched at the head of a file, not searched throughout it: the
# toolkit's own source legitimately *mentions* magic strings like the
# memory-card header because it has to recognise them.
FORBIDDEN_SIGNATURES = (
    (b"Sony PS2 Memory Card Format", "PS2 memory-card image"),
    (b"MICROSOFT*XBOX*MEDIA", "Xbox disc image"),
    (b"XBEH", "Xbox executable"),
    (b"XEX2", "Xbox 360 executable"),
    (b"\x7fELF", "extracted executable"),
    (b"ROST", "ROST save payload"),
    (b"CD001", "disc image"),
)

# Source files are small; anything larger is not code and warrants a look.
MAX_PAYLOAD_BYTES = 512 * 1024

README = """NFL 2K5 PS2 Save Toolkit
========================

Command-line tools for reading, editing and writing ESPN NFL 2K5
(PlayStation 2, SLUS-20919) memory-card saves.

Requires only Python 3 (3.9 or newer). No other dependencies.
This package contains NO game data -- bring your own save.

Quick start
-----------

Look at a save (a .psu, an extracted save folder, or a .ps2 memory-card
image straight out of PCSX2):

    python3 tools/nfl2k5_ps2_save.py --input <your-save> --inspect

List the player name slots and how much room each one has:

    python3 tools/nfl2k5_ps2_save.py --input <your-save> --list-players

Change a name and write a new save file:

    python3 tools/nfl2k5_ps2_save.py --input <your-save> \\
        --set-player-name '0:last=Smith' --output edited.psu

Check the result independently -- this re-reads both files and proves only
the bytes that were supposed to change actually changed:

    python3 tools/nfl2k5_ps2_save_verify.py \\
        --original <your-save> --edited edited.psu

Then import edited.psu with mymc / PS2 Save Builder, or load it in PCSX2.

Notes
-----

* Your original save is never modified. Output always goes to a new file.
* Names must fit the space the old name used; the tool refuses to grow the
  file rather than risk corrupting it.
* Reading works from .psu, an extracted save folder, or a .ps2 card image.
  Writing produces .psu.
* This is a preview build of the command-line tools. The graphical editor
  does not expose PS2 saves yet.
* The file-side checks all pass, but an edited save has not yet been
  confirmed loading in-game -- that test is the next step. Keep a backup of
  any card you work from.

See docs/product/NFL2K5_PS2_SAVE_PIPELINE.md for the full write-up.

Self-test (no save required):

    bash tools/validate_nfl2k5_ps2_save.sh
"""


class BuildError(RuntimeError):
    pass


def _gate(relative: str, data: bytes) -> None:
    """Refuse anything that is not plain source, or that is game data.

    Every shipped file is source or documentation, so the decisive test is
    simply that it decodes as UTF-8 text: disc images, memory cards, saves and
    executables are all binary and cannot pass it.  The signature check then
    runs against the *head* of the file to name anything binary that slipped
    in, and a size ceiling catches a blob smuggled in as text.
    """
    if len(data) > MAX_PAYLOAD_BYTES:
        raise BuildError(
            f"{relative}: {len(data)} bytes exceeds the {MAX_PAYLOAD_BYTES}-byte "
            "source ceiling; refusing to package"
        )
    head = data[:64]
    for signature, label in FORBIDDEN_SIGNATURES:
        if head.startswith(signature) or signature in data[:6]:
            raise BuildError(f"{relative}: looks like a {label}; refusing to package")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(
            f"{relative}: not UTF-8 text, so it is not source; refusing to package"
        ) from exc


def build(output_dir: Path, version: str) -> tuple[Path, Path]:
    stem = f"{TOOLKIT_NAME}-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{stem}.tar.gz"

    members: list[tuple[str, bytes]] = []
    for relative in PAYLOAD:
        source = ROOT / relative
        if not source.is_file():
            raise BuildError(f"missing declared payload file: {relative}")
        if source.is_symlink():
            raise BuildError(f"{relative}: symlinks are not packaged")
        data = source.read_bytes()
        _gate(relative, data)
        members.append((f"{stem}/{relative}", data))
    members.append((f"{stem}/README.txt", README.encode("utf-8")))
    members.sort(key=lambda item: item[0])

    # gzip with mtime=0 plus fixed tar metadata => reproducible bytes.
    import gzip

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = SOURCE_DATE_EPOCH
            info.mode = 0o755 if name.endswith(".sh") else 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(data))
    with open(archive_path, "wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", mtime=0) as gz:
            gz.write(raw.getvalue())

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    sha_path = output_dir / f"{stem}.tar.gz.sha256"
    sha_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, sha_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--version", default="preview1")
    args = parser.parse_args(argv)

    archive, sha = build(args.output_dir, args.version)
    print(f"built  {archive}")
    print(f"sha256 {sha.read_text(encoding='utf-8').strip()}")
    print(f"files  {len(PAYLOAD) + 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

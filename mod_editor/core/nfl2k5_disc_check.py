"""Check a SOFTDRINK 2K28 disc image against the released disc, file by file (b780 n4).

Why.  Smuzz's freezes ("the game freezes at this exact screen and commentators repeat lines", 9/20, 10/30, 11/02)
could not be reproduced on the released disc, and the game reads commentary and other resources from the disc all
through the post-play and play-call screens.  A copy that is damaged or cut short (an SD card, a partial transfer, a
full drive while installing) stalls or fails exactly there, and the stall looks like a game bug: the picture stops and
the sound card keeps repeating its last buffer.  This check tells the two apart in plain words: it hashes the files
of the user's image and compares them with the released disc's file list (``data/nfl2k5_released_discs.json``),
naming each file that differs and where in it (in MiB), or saying that the image matches the release byte for byte.

It reads only.  It accepts an ``.xiso`` and a raw (redump-style) dump alike, because files are found through the
disc's own directory.  A disc made with Customize SOFTDRINK or other Build options is a different disc on purpose;
the check says so instead of calling it damaged when most files differ.

Command line::

    python3 -m mod_editor.core.nfl2k5_disc_check "SOFTDRINK 2K28 v0.8.xiso.iso"

Making the file list for a new release (release step, from the published image)::

    python3 -m mod_editor.core.nfl2k5_disc_check --make-entry "SOFTDRINK 2K28 v0.9" IMAGE > entry.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "nfl2k5_released_discs.json"
SCHEMA = "nfl2k5_released_discs/v1"
CHUNK = 8 << 20            # bytes per chunk hash: small enough to say where a copy is damaged, few enough to ship
PREFIX = 16                # hex digits kept per chunk hash (64 bits: plenty to detect damage, not a security check)
MIB = 1 << 20

Progress = Callable[[str, int, int], None]


class DiscCheckError(ValueError):
    pass


def _xdvdfs():
    from . import modpack
    return modpack._xdvdfs_module()


def _read_exact(fd: int, offset: int, length: int) -> bytes:
    out = bytearray()
    while len(out) < length:
        if hasattr(os, "pread"):
            part = os.pread(fd, length - len(out), offset + len(out))
        else:  # Windows
            os.lseek(fd, offset + len(out), os.SEEK_SET)
            part = os.read(fd, length - len(out))
        if not part:
            break
        out += part
    return bytes(out)


def load_releases(path: Path = DATA) -> list[dict[str, Any]]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA:
        raise DiscCheckError(f"{path.name} is not a released-disc list ({SCHEMA})")
    return list(document["discs"])


def _entries(fd: int, size: int, *, lenient: bool = False) -> tuple[int, dict[str, Any]]:
    xc = _xdvdfs()
    try:
        base = int(xc.locate_xdvdfs_base(fd, size))
        try:
            entries, _info = xc.parse_xdvdfs(fd, size, base)
        except Exception as exc:  # noqa: BLE001
            if not (lenient and "outside image" in str(exc)):
                raise
            # the directory is readable but files run past the end: an image cut short. Read the directory as if the
            # image were whole, so the comparison can say how much of each file is there.
            entries, _info = xc.parse_xdvdfs(fd, 1 << 40, base)
    except Exception as exc:  # noqa: BLE001 - any parse failure: not a readable Xbox disc image
        raise DiscCheckError(
            "This file is not a readable Xbox disc image (its disc directory could not be read). "
            f"It may be damaged, cut short, or not a disc image at all. Detail: {exc}") from exc
    return base, entries


def _file_hashes(fd: int, image_size: int, base: int, entry, progress: Progress | None, done: int, total: int):
    """(sha256 of the file, chunk hash prefixes, bytes actually readable)."""
    start = base + entry.sector * 2048
    whole = hashlib.sha256()
    chunks: list[str] = []
    readable = 0
    offset = 0
    while offset < entry.size:
        want = min(CHUNK, entry.size - offset)
        data = _read_exact(fd, start + offset, want)
        readable += len(data)
        whole.update(data)
        chunks.append(hashlib.sha256(data).hexdigest()[:PREFIX])
        offset += want
        if progress:
            progress(f"Hashing {entry.path}", done + offset, total)
        if len(data) < want:
            # the image ends inside this file: the rest cannot be compared
            break
    return whole.hexdigest(), chunks, readable


def make_entry(name: str, image: Path | str, progress: Progress | None = None) -> dict[str, Any]:
    """The released-disc record for a published image (run once per release)."""
    path = Path(image)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        base, entries = _entries(fd, size)
        total = sum(e.size for e in entries.values())
        files, done = {}, 0
        image_hash = hashlib.sha256()
        for key in sorted(entries):
            e = entries[key]
            digest, chunks, readable = _file_hashes(fd, size, base, e, progress, done, total)
            if readable != e.size:
                raise DiscCheckError(f"{e.path} is cut short in the source image; refusing to record it")
            files[e.path] = dict(size=e.size, sha256=digest, chunks=chunks)
            done += e.size
        os.lseek(fd, 0, os.SEEK_SET)
        while block := os.read(fd, 8 << 20):
            image_hash.update(block)
    finally:
        os.close(fd)
    return dict(name=name, image_size=size, image_sha256=image_hash.hexdigest(), partition_base=base, chunk=CHUNK,
                files=files)


def _closest(releases: list[dict[str, Any]], names: set[str]) -> dict[str, Any] | None:
    best, score = None, -1
    for r in releases:
        common = len(names & set(f.lower() for f in r["files"]))
        if common > score:
            best, score = r, common
    return best if score > 0 else None


def check(image: Path | str, *, releases: Iterable[dict[str, Any]] | None = None, progress: Progress | None = None) -> dict[str, Any]:
    """Compare an image with the released discs. Returns a result dict; ``describe(result)`` says it in plain words.

    state: "matches" (every file equals a released disc), "damaged" (a few files or places differ, or the image is cut
    short: a bad copy), "different" (most of the disc differs: a different build, e.g. Customize SOFTDRINK), or
    "unreadable" (no disc directory)."""
    path = Path(image)
    rel = list(releases) if releases is not None else load_releases()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        try:
            base, entries = _entries(fd, size, lenient=True)
        except DiscCheckError as exc:
            return dict(state="unreadable", image=str(path), image_size=size, detail=str(exc))
        by_lower = {k.lower(): e for k, e in entries.items()}
        target = _closest(rel, set(by_lower))
        if target is None:
            return dict(state="different", image=str(path), image_size=size, release=None,
                        detail="none of this disc's files are on a released SOFTDRINK disc")
        files = {k.lower(): (k, v) for k, v in target["files"].items()}
        total = sum(v["size"] for _k, v in files.values())
        done = 0
        differing, missing, extra, cut = [], [], [], []
        for low in sorted(files):
            name, want = files[low]
            entry = by_lower.get(low)
            if entry is None:
                missing.append(name)
                done += want["size"]
                continue
            if entry.size != want["size"]:
                differing.append(dict(file=name, reason="size", expected=want["size"], found=entry.size, mib=[]))
                done += want["size"]
                continue
            digest, chunks, readable = _file_hashes(fd, size, base, entry, progress, done, total)
            done += want["size"]
            if readable < entry.size:
                cut.append(dict(file=name, readable_mib=round(readable / MIB, 1), size_mib=round(entry.size / MIB, 1)))
            if digest != want["sha256"]:
                bad = [i for i, (a, b) in enumerate(zip(chunks, want["chunks"])) if a != b]
                if len(chunks) < len(want["chunks"]):
                    bad += list(range(len(chunks), len(want["chunks"])))
                differing.append(dict(file=name, reason="content", chunks=len(bad),
                                      mib=_ranges(bad, target.get("chunk", CHUNK), entry.size)))
        for low, e in by_lower.items():
            if low not in files:
                extra.append(e.path)
    finally:
        os.close(fd)
    changed_bytes = sum(len(d.get("mib", [])) for d in differing)
    share = (sum(d.get("chunks", 0) for d in differing) * target.get("chunk", CHUNK)) / max(1, total)
    if not differing and not missing and not cut and not extra:
        state = "matches"
    elif cut or (share < 0.25 and not missing):
        state = "damaged"
    else:
        state = "different"
    return dict(state=state, image=str(path), image_size=size, partition_base=base, release=target["name"],
                release_sha256=target.get("image_sha256"), release_size=target.get("image_size"),
                differing=differing, missing=missing, extra=extra, cut_short=cut, differing_share=round(share, 4),
                ranges=changed_bytes)


def _ranges(chunks: list[int], chunk: int, size: int) -> list[list[float]]:
    out: list[list[int]] = []
    for c in sorted(set(chunks)):
        if out and out[-1][1] == c:
            out[-1][1] = c + 1
        else:
            out.append([c, c + 1])
    return [[round(a * chunk / MIB, 1), round(min(b * chunk, size) / MIB, 1)] for a, b in out]


def describe(result: dict[str, Any]) -> str:
    state = result["state"]
    name = result.get("release") or "a released SOFTDRINK disc"
    if state == "unreadable":
        return result["detail"]
    if state == "matches":
        return (f"This image matches {name} file for file. The disc copy is good, so a freeze on it is a real game "
                "problem: please report it with the steps and, if you can, a freeze capture.")
    lines = []
    if state == "damaged":
        lines.append(f"This image is a damaged or incomplete copy of {name}. Copy or install the disc again "
                     "(from the Studio's Install SOFTDRINK 2K28, or a fresh download) and check it again.")
    else:
        lines.append(f"This image is a different disc from {name}: most of it differs. That is expected for a disc "
                     "made with Customize SOFTDRINK or other Build options, so this check cannot judge it. To test "
                     "the released disc, install it with Install SOFTDRINK 2K28 and check that image.")
    for c in result.get("cut_short", []):
        lines.append(f"- {c['file']} is cut short: only {c['readable_mib']} of {c['size_mib']} MiB can be read "
                     "(the image file ends early).")
    for d in result.get("differing", [])[:12]:
        if d["reason"] == "size":
            lines.append(f"- {d['file']} has the wrong size ({d['found']:,} bytes, the release has {d['expected']:,}).")
        else:
            where = ", ".join(f"{a}-{b} MiB" for a, b in d["mib"][:6]) + (" and more" if len(d["mib"]) > 6 else "")
            lines.append(f"- {d['file']} differs at {where}.")
    if len(result.get("differing", [])) > 12:
        lines.append(f"- and {len(result['differing']) - 12} more files differ.")
    for m in result.get("missing", []):
        lines.append(f"- {m} is missing.")
    for e in result.get("extra", [])[:6]:
        lines.append(f"- {e} is not on the released disc.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a SOFTDRINK 2K28 disc image against the released disc.")
    parser.add_argument("image", help="the .xiso.iso (or raw dump) to check")
    parser.add_argument("--make-entry", metavar="NAME", help="print the released-disc record for this image instead")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    last = [None]

    def progress(stage: str, done: int, total: int) -> None:
        pct = int(100 * done / max(1, total))
        if (stage, pct // 5) != last[0]:
            last[0] = (stage, pct // 5)
            print(f"  {pct:3d}%  {stage}", file=sys.stderr, flush=True)

    if args.make_entry:
        print(json.dumps(make_entry(args.make_entry, args.image, progress), indent=1))
        return 0
    result = check(args.image, progress=progress)
    print(json.dumps(result, indent=1) if args.json else describe(result))
    return 0 if result["state"] == "matches" else 1


if __name__ == "__main__":
    sys.exit(main())

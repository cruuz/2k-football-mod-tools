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
    from .platform_compat import pread  # b780-int: os.pread is POSIX-only; the shared helper falls back on Windows
    out = bytearray()
    while len(out) < length:
        part = pread(fd, length - len(out), offset + len(out))
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
            if e.attributes & 0x10:
                files[e.path]["directory"] = True
            done += e.size
        os.lseek(fd, 0, os.SEEK_SET)
        while block := os.read(fd, 8 << 20):
            image_hash.update(block)
    finally:
        os.close(fd)
    return dict(name=name, image_size=size, image_sha256=image_hash.hexdigest(), partition_base=base, chunk=CHUNK,
                files=files)


def _closest(releases: list[dict[str, Any]], names: set[str]) -> dict[str, Any] | None:
    """The release sharing the most file names (kept for callers that have only names)."""
    best, score = None, -1
    for r in releases:
        common = len(names & set(f.lower() for f in r["files"]))
        if common > score:
            best, score = r, common
    return best if score > 0 else None


def _candidates(releases: list[dict[str, Any]], by_lower: dict[str, Any]) -> list[dict[str, Any]]:
    """The releases sharing at least one file name with the disc, in record order."""
    return [r for r in releases if set(f.lower() for f in r["files"]) & set(by_lower)]


def _rank(result: dict[str, Any], target: dict[str, Any], image_size: int, order: int) -> tuple:
    """Match the game contents first. Repacking or trimming padding can give a disc another release's size."""
    return (result["files_matching"], result["sizes_matching"], result["names_matching"],
            target.get("image_size") == image_size, -order)


def check(image: Path | str, *, releases: Iterable[dict[str, Any]] | None = None, progress: Progress | None = None) -> dict[str, Any]:
    """Compare an image with the released discs. Returns a result dict; ``describe(result)`` says it in plain words.

    The existing "damaged" state includes both localized mismatches and truncated files. A nonempty
    "cut_short" list proves that the image ends inside a listed file. Otherwise the differing bytes
    can also come from a custom build. "matches" compares game-file contents, "different" indicates
    broader changes, and "unreadable" means the disc directory could not be read."""
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
        candidates = _candidates(rel, by_lower)
        if not candidates:
            return dict(state="different", image=str(path), image_size=size, release=None,
                        detail="none of this disc's files are on a released SOFTDRINK disc")
        # every candidate is compared, but each file is hashed at most once; a release that matches fully wins,
        # otherwise the best-ranked comparison (_rank) is the one reported
        hashed: dict[str, tuple] = {}
        compared = [(_compare(target, fd, size, base, by_lower, hashed, progress), target, order)
                    for order, target in enumerate(candidates)]
    finally:
        os.close(fd)
    full = [item for item in compared if item[0]["state"] == "matches"]
    best = max(full or compared, key=lambda item: _rank(item[0], item[1], size, item[2]))[0]
    return dict(best, image=str(path), image_size=size, partition_base=base)


def _compare(target, fd, size, base, by_lower, hashed, progress) -> dict[str, Any]:
    files = {k.lower(): (k, v) for k, v in target["files"].items()}
    # Older records include the sector tables as entries without a directory flag.
    parents = {name.rpartition("/")[0] for name in files if "/" in name}
    checked_directories = set()
    total = sum(v["size"] for _k, v in files.values())
    done = changed_bytes = 0
    chunk = target.get("chunk", CHUNK)
    compared_bytes = 0
    differing, missing, extra, cut = [], [], [], []
    for low in sorted(files):
        name, want = files[low]
        entry = by_lower.get(low)
        if entry is None:
            missing.append(name)
            changed_bytes += want["size"]
            compared_bytes += want["size"]
            done += want["size"]
            continue
        if low in parents or want.get("directory"):
            # The parser already read this table and validated its tree. Its sector offsets and
            # padding can change during a repack. Every child is checked by path and contents.
            if entry.attributes & 0x10:
                checked_directories.add(low)
            else:
                differing.append(dict(file=name, reason="directory", mib=[]))
                changed_bytes += max(entry.size, want["size"])
                compared_bytes += max(entry.size, want["size"])
            done += want["size"]
            continue
        span = max(entry.size, want["size"])
        compared_bytes += span
        if low not in hashed:
            hashed[low] = _file_hashes(fd, size, base, entry, progress, done, total)
        digest, chunks, readable = hashed[low]
        done += want["size"]
        if readable < entry.size:
            cut.append(dict(file=name, readable_mib=round(readable / MIB, 1), size_mib=round(entry.size / MIB, 1)))
        if digest != want["sha256"] or entry.size != want["size"]:
            bad = [i for i, (a, b) in enumerate(zip(chunks, want["chunks"])) if a != b]
            bad.extend(range(min(len(chunks), len(want["chunks"])), max(len(chunks), len(want["chunks"]))))
            changed_bytes += sum(min(chunk, span - index * chunk) for index in bad)
            difference = dict(file=name, reason="content", chunks=len(bad), mib=_ranges(bad, chunk, span))
            if entry.size != want["size"]:
                difference.update(reason="size", expected=want["size"], found=entry.size)
            differing.append(difference)
    for low, e in by_lower.items():
        if low not in files:
            extra.append(e.path)
            compared_bytes += e.size
            changed_bytes += e.size
    names = [low for low in files if low in by_lower]
    same_size = {low for low in names if low in checked_directories or by_lower[low].size == files[low][1]["size"]}
    sizes_matching = len(same_size)
    differing_names = {d["file"].lower() for d in differing} | {c["file"].lower() for c in cut}
    files_matching = len(same_size - differing_names)
    ranges = sum(len(d["mib"]) for d in differing)
    share = changed_bytes / max(1, compared_bytes)
    if not differing and not missing and not cut and not extra:
        state = "matches"
    elif cut or (share < 0.25 and sizes_matching and not missing and not extra):
        state = "damaged"
    else:
        state = "different"
    return dict(state=state, release=target["name"], release_sha256=target.get("image_sha256"),
                release_size=target.get("image_size"), differing=differing, missing=missing, extra=extra,
                cut_short=cut, differing_share=round(share, 4), ranges=ranges,
                names_matching=len(names), sizes_matching=sizes_matching, files_matching=files_matching)


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
        return (f"This image matches {name} file for file. The game files are intact. For a freeze, report the steps "
                "leading up to it, your console or emulator setup and a capture if available.")
    lines = []
    if result.get("cut_short"):
        lines.append(f"This image ends inside a game file from {name}. Install the game again from your clean disc "
                     "with Install SOFTDRINK 2K28, then check the new image.")
    elif state == "damaged":
        lines.append(f"This image differs from {name} in the places listed below. "
                     "If you expected the official release, this may be a damaged or incomplete copy. "
                     "Use Install SOFTDRINK 2K28 with your clean disc and check the new image. "
                     "If you customized this disc, compare the listed files with your Build summary.")
    else:
        lines.append(f"This disc’s game files differ from {name}. Customize SOFTDRINK and other Build options "
                     "can change the files or their contents. To check the official release, use Install "
                     "SOFTDRINK 2K28 with your clean disc and check the new image.")
    for c in result.get("cut_short", []):
        lines.append(f"- {c['file']} is cut short: only {c['readable_mib']} of {c['size_mib']} MiB can be read "
                     "(the image file ends early).")
    for d in result.get("differing", [])[:12]:
        if d["reason"] == "directory":
            lines.append(f"- {d['file']} is a file where the release has a folder.")
        elif d["reason"] == "size":
            lines.append(f"- {d['file']} is {d['found']:,} bytes. The release has {d['expected']:,}.")
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

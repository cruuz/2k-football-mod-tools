"""Bus Jibber's authored live face and portrait (b778-ss1), patched into the two retail pack extents.

The face/portrait importers in ``tools/`` produce fixed spans for a free retail id (304, no roster record in the
released v0.6.1 roster references it). This module ships those spans and patches the build image at the pack
offsets the importers recorded; the pack files are found through the image's own XDVDFS directory, so a rebuilt
image with the packs in other sectors still works. Nothing grows: every replacement is the retail span size.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/nfl2k5_classic_teams/face"
PATCH = DATA / "patch.json"


class ClassicFaceError(ValueError):
    """A face target is absent, another job changed it, or the image is not an XISO."""


def require(ok, message):
    if not ok:
        raise ClassicFaceError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _doc():
    doc = json.loads(PATCH.read_text(encoding="utf-8"))
    require(doc.get("schema") == "nfl2k5_classic_face_patch/v1", "face patch schema")
    require(doc.get("face_id") == 304 and doc.get("targets"), "face patch targets")
    for row in doc["targets"]:
        require(row["kind"] in ("live_face", "player_portrait"), "face target kind")
        span = DATA / row["span_file"]
        require(span.is_file() and span.stat().st_size == row["size"], f"missing face span {span.name}")
        require(len(row["retail_sha256"]) == 64 and len(row["replacement_sha256"]) == 64, "face hashes")
    return doc


def _entries(fd):
    from tools.nfl_uniform_color_xiso_direct_patch import parse_xdvdfs
    size = os.fstat(fd).st_size
    entries, _dirs = parse_xdvdfs(fd, size)
    return {key.replace("\\", "/").lstrip("/"): value for key, value in entries.items()}


def _locate(entries, pack_path):
    for key in (pack_path, pack_path.replace("/", "\\"), "\\" + pack_path.replace("/", "\\")):
        if key in entries:
            return entries[key]
    raise ClassicFaceError(f"pack {pack_path} is not in the image")


def _targets(fd, doc):
    entries = _entries(fd)
    out = []
    for row in doc["targets"]:
        entry = _locate(entries, row["pack_path"])
        at = entry.byte_offset + int(row["pack_offset"])
        out.append((row, at, (DATA / row["span_file"]).read_bytes()))
    return out


def status(path):
    """'applied' (every face/portrait span is authored), 'retail' (every span is retail), else 'foreign'."""
    try:
        doc = _doc()
        fd = os.open(Path(path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            targets = _targets(fd, doc)
            states = set()
            for row, at, span in targets:
                current = os.pread(fd, len(span), at)
                digest = _sha(current)
                states.add("applied" if digest == row["replacement_sha256"]
                           else "retail" if digest == row["retail_sha256"] else "foreign")
            return states.pop() if len(states) == 1 else "foreign"
        finally:
            os.close(fd)
    except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError):
        return "foreign"


def patch_image(path):
    """Patch the two pack extents in place; replay is a no-op, a foreign span refuses before any write."""
    doc = _doc()
    path = Path(path).resolve()
    fd = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        targets = _targets(fd, doc)
        planned, already = [], 0
        for row, at, span in targets:
            current = os.pread(fd, len(span), at)
            digest = _sha(current)
            if digest == row["replacement_sha256"]:
                already += 1
                continue
            require(digest == row["retail_sha256"], f"{row['kind']} {row.get('family', '')}: the span is another job's")
            planned.append((row, at, span))
        for row, at, span in planned:
            require(os.pwrite(fd, span, at) == len(span), "short face patch write")
        os.fsync(fd)
        for row, at, span in planned:
            require(_sha(os.pread(fd, len(span), at)) == row["replacement_sha256"], "face patch read-back")
    finally:
        os.close(fd)
    return dict(status="applied" if planned else "already_applied", changed_spans=len(planned), already=already)

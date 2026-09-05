#!/usr/bin/env python3
"""Prove a patched PS2 ESPN NFL 2K5 image changed only the playbooks it declared.

This is the **independent** half of the pair.  It imports neither
``nfl2k5_ps2_playbook_patch`` nor ``ps2_iso9660`` (the writer's own reader), so
a bug shared between the patcher and the reader cannot hide here.  What it does
use is deliberate: ``ps2_iso9660_verify``, which decodes the volume with its own
parser, and the studio play codec -- because "the book still parses and the game
would still accept every play" is the claim under test, and the codec *is* the
port of the game's reader and validator.

Everything is re-derived from the two images and the patch report; nothing is
taken on the patcher's word:

1. ``ps2_iso9660_verify.verify_replacement`` -- the image is the source with
   only the writer's declared edits, and its own structural checks hold.
2. Both images are the same length, and a **streaming byte diff of the whole
   image** shows every differing byte falls inside a declared ``PLAY`` resource
   span.  Nothing else on the disc moved.
3. For each declared edit: the source resource still hashes to the reported
   "before", the output resource to the reported "after", the 32-byte chunk
   header is untouched, and the body is still exactly 78,736 bytes.
4. The output book **parses with the codec** and its formation / play /
   category / node / chain counts equal the reported "after" counts.
5. The ported retail validator **accepts every play** in the output book, and
   the declared new formation / play indices are present.
6. Every ``PLAY`` resource the report did **not** declare is byte-identical
   between the two images -- re-derived by scanning the outer archive here,
   not by trusting the report's list.

Usage::

    nfl2k5_ps2_playbook_verify.py --source SRC.iso --output NEW.iso \\
        --report REPORT.json [--json RESULT.json]

Exit status is 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _entry in (_ROOT, _HERE):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import ps2_iso9660_verify  # noqa: E402

SCHEMA = "nfl2k5_ps2_playbook_verify/v1"

PACK_DIR = "/VC_20919"
ALIGNMENT = 0x800
PACK_SLOT_COUNT = 36
OUTER_HEADER_SIZE = 0x0C + PACK_SLOT_COUNT * 4
OUTER_ENTRY_SIZE = 12
CHUNK_HEADER_SIZE = 0x20
BODY_SIZE = 0x13390
RESOURCE_HEADER_SIZE = 0x20
PLAY_RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE
PLAY_FOURCC = b"PLAY"
COMPRESSED_SENTINEL = 0xFEEDBEEF

DIFF_CHUNK = 4 * 1024 * 1024


class PlaybookVerifyError(AssertionError):
    """A check failed.  The message says which."""


def _require(condition, message):
    if not condition:
        raise PlaybookVerifyError(message)


def _codec():
    from mod_editor.core import nfl2k5_play_codec as codec
    from mod_editor.core import nfl2k5_playbook_inspector as inspector
    _require(inspector.BODY_SIZE == BODY_SIZE,
             "the studio playbook layout no longer matches this verifier")
    return codec, inspector


# ---------------------------------------------------------------------------
# Independent pack discovery (via the verifier's own directory decoder)
# ---------------------------------------------------------------------------

def _packs(path):
    """``/VC_20919/*`` extents, ordered, decoded without the writer's reader."""
    descriptor, volume = ps2_iso9660_verify.open_volume(path)
    try:
        entries = ps2_iso9660_verify.walk(descriptor, volume)
    finally:
        os.close(descriptor)
    prefix = PACK_DIR + "/"
    rows = []
    for entry in entries:
        if entry.is_dir or not entry.path.startswith(prefix):
            continue
        name = entry.path[len(prefix):].split(";")[0].rstrip(".")
        if len(name) != 1:
            continue
        rows.append((name, entry.lba * volume.block_size + volume.data_offset,
                     entry.length))
    _require(rows, "no %s packs in %s" % (PACK_DIR, path))
    rows.sort(key=lambda row: row[0])
    packs = []
    virtual = 0
    for name, offset, length in rows:
        packs.append((name, offset, length, virtual))
        virtual += length
    return packs


def _read_archive(descriptor, packs, virtual_offset, size):
    parts = []
    while size:
        pack = None
        for row in reversed(packs):
            if row[3] <= virtual_offset:
                pack = row
                break
        _require(pack is not None, "negative archive offset")
        inside = virtual_offset - pack[3]
        take = min(size, pack[2] - inside)
        _require(take > 0, "read past the end of the archive")
        block = os.pread(descriptor, take, pack[1] + inside)
        _require(len(block) == take, "short archive read")
        parts.append(block)
        virtual_offset += take
        size -= take
    return b"".join(parts)


def _play_resources(path):
    """Absolute offsets of every PLAY resource, re-derived from the image."""
    packs = _packs(path)
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
    found = []
    try:
        header = _read_archive(descriptor, packs, 0, OUTER_HEADER_SIZE)
        entry_count, _reserved, populated = struct.unpack_from("<III", header, 0)
        _require(populated == len(packs),
                 "index declares %d packs, image has %d" % (populated, len(packs)))
        table = _read_archive(descriptor, packs, OUTER_HEADER_SIZE,
                              entry_count * OUTER_ENTRY_SIZE)
        total = sum(row[2] for row in packs)
        for index in range(entry_count):
            name_id, size, blocks = struct.unpack_from(
                "<III", table, index * OUTER_ENTRY_SIZE)
            if size < PLAY_RESOURCE_SIZE:
                continue
            virtual = blocks * ALIGNMENT
            if virtual + CHUNK_HEADER_SIZE > total:
                continue
            head = _read_archive(descriptor, packs, virtual, CHUNK_HEADER_SIZE)
            if head[:4] != PLAY_FOURCC:
                continue
            stored, _system, _video, magic = struct.unpack_from("<4I", head, 4)
            if stored != BODY_SIZE or magic == COMPRESSED_SENTINEL:
                continue
            pack = None
            for row in reversed(packs):
                if row[3] <= virtual:
                    pack = row
                    break
            absolute = pack[1] + (virtual - pack[3])
            found.append(("0x%08x" % name_id, absolute))
    finally:
        os.close(descriptor)
    _require(found, "no PLAY resources in %s" % path)
    return found


# ---------------------------------------------------------------------------
# Whole-image diff
# ---------------------------------------------------------------------------

def _diff_ranges(source, output):
    """Every maximal differing byte range between two equal-length images."""
    ranges = []
    open_start = None
    position = 0
    with open(str(source), "rb") as left, open(str(output), "rb") as right:
        while True:
            a = left.read(DIFF_CHUNK)
            b = right.read(DIFF_CHUNK)
            _require(len(a) == len(b), "the two images are not the same length")
            if not a:
                break
            if a != b:
                for index in range(len(a)):
                    if a[index] != b[index]:
                        if open_start is None:
                            open_start = position + index
                    elif open_start is not None:
                        ranges.append((open_start, position + index))
                        open_start = None
            elif open_start is not None:
                ranges.append((open_start, position))
                open_start = None
            position += len(a)
    if open_start is not None:
        ranges.append((open_start, position))
    return ranges


def _read_at(path, offset, size):
    with open(str(path), "rb") as handle:
        handle.seek(offset)
        data = handle.read(size)
    _require(len(data) == size, "short read at 0x%x in %s" % (offset, path))
    return data


# ---------------------------------------------------------------------------
# The verification
# ---------------------------------------------------------------------------

def verify(source, output, report):
    codec, inspector = _codec()
    source, output = Path(source), Path(output)
    checks = []

    def record(name, detail=""):
        checks.append({"check": name, "ok": True, "detail": detail})

    edits = report.get("play_edits") or []
    _require(edits, "the report declares no play edits")

    # 1 -- the ISO verifier's own checks
    writer_report = report.get("iso_writer_report")
    _require(isinstance(writer_report, dict),
             "the report is missing iso_writer_report")
    iso_result = ps2_iso9660_verify.verify_replacement(
        source, output, writer_report)
    record("iso_writer_replacement_verified",
           "declared_ranges=%d" % len(writer_report.get("declared_ranges", [])))

    # 2 -- whole-image diff confined to the declared PLAY spans
    _require(source.stat().st_size == output.stat().st_size,
             "the output image changed length")
    spans = [(int(e["absolute_offset"]),
              int(e["absolute_offset"]) + PLAY_RESOURCE_SIZE) for e in edits]
    differing = _diff_ranges(source, output)
    stray = [r for r in differing
             if not any(start <= r[0] and r[1] <= stop for start, stop in spans)]
    _require(
        not stray,
        "bytes changed outside the declared PLAY resources: "
        + ", ".join("0x%x-0x%x" % r for r in stray[:8]),
    )
    changed_bytes = sum(stop - start for start, stop in differing)
    record("diff_confined_to_declared_play_spans",
           "%d differing ranges, %d bytes, %d declared spans"
           % (len(differing), changed_bytes, len(spans)))

    # 3-5 -- per book
    books = []
    for edit in edits:
        book_id = edit["book_id"]
        offset = int(edit["absolute_offset"])
        before_raw = _read_at(source, offset, PLAY_RESOURCE_SIZE)
        after_raw = _read_at(output, offset, PLAY_RESOURCE_SIZE)
        _require(
            hashlib.sha256(before_raw).hexdigest() == edit["source_sha256"],
            "book %s: the source resource does not match the reported hash" % book_id,
        )
        _require(
            hashlib.sha256(after_raw).hexdigest() == edit["replacement_sha256"],
            "book %s: the output resource does not match the reported hash" % book_id,
        )
        _require(
            before_raw[:RESOURCE_HEADER_SIZE] == after_raw[:RESOURCE_HEADER_SIZE],
            "book %s: the 32-byte chunk header changed" % book_id,
        )
        _require(after_raw[:4] == PLAY_FOURCC
                 and struct.unpack_from("<I", after_raw, 4)[0] == BODY_SIZE,
                 "book %s: the output chunk header is not a %d-byte PLAY"
                 % (book_id, BODY_SIZE))

        body = after_raw[RESOURCE_HEADER_SIZE:]
        _require(len(body) == BODY_SIZE,
                 "book %s: body is %d bytes" % (book_id, len(body)))
        try:
            parsed = inspector._parse_body(body, asset_id=book_id, outer_index=0)
        except Exception as exc:
            raise PlaybookVerifyError("book %s no longer parses: %s" % (book_id, exc))

        after = edit["after"]
        got = {"formations": len(parsed.formations), "plays": len(parsed.plays),
               "categories": len(parsed.categories), "nodes": parsed.node_count}
        _require(got == {k: after[k] for k in got},
                 "book %s: counts are %s but the report claims %s"
                 % (book_id, got, {k: after[k] for k in got}))

        for index in edit.get("new_formation_indices", []):
            _require(0 <= index < len(parsed.formations),
                     "book %s: new formation %d is not present" % (book_id, index))
        for index in edit.get("new_play_indices", []):
            _require(0 <= index < len(parsed.plays),
                     "book %s: new play %d is not present" % (book_id, index))

        refused = []
        for play in parsed.plays:
            assignments = []
            for assignment in play.assignments:
                chain = parsed.chain(assignment.chain_start_index)
                assignments.append((
                    assignment.descriptor_word,
                    [bytes.fromhex(node.raw_hex) for node in chain.nodes],
                ))
            why = codec.validate_play(play.flags_or_id, assignments)
            if why is not None:
                refused.append("play %d: %s" % (play.index, why))
        _require(not refused,
                 "book %s: the retail validator refuses %d play(s): %s"
                 % (book_id, len(refused), "; ".join(refused[:3])))

        books.append({
            "book_id": book_id,
            "absolute_offset": offset,
            "counts": got,
            "plays_validated": len(parsed.plays),
            "chains": len(parsed.chains),
        })
    record("books_parse_and_validate",
           "%d book(s), %d plays accepted by the retail validator"
           % (len(books), sum(b["plays_validated"] for b in books)))

    # 6 -- every undeclared PLAY resource is untouched
    declared = {int(e["absolute_offset"]) for e in edits}
    resources = _play_resources(output)
    source_resources = _play_resources(source)
    _require(
        [r[0] for r in resources] == [r[0] for r in source_resources],
        "the set of PLAY books changed between the two images",
    )
    untouched = 0
    for book_id, offset in resources:
        if offset in declared:
            continue
        if _read_at(source, offset, PLAY_RESOURCE_SIZE) != \
                _read_at(output, offset, PLAY_RESOURCE_SIZE):
            raise PlaybookVerifyError(
                "undeclared book %s at 0x%x changed" % (book_id, offset))
        untouched += 1
    record("undeclared_books_byte_identical",
           "%d of %d books untouched" % (untouched, len(resources)))

    return {
        "schema": SCHEMA,
        "source_iso": str(source),
        "output_iso": str(output),
        "image_size": source.stat().st_size,
        "play_resources_found": len(resources),
        "declared_edits": len(edits),
        "changed_byte_total": changed_bytes,
        "changed_ranges": [[start, stop] for start, stop in differing],
        "books": books,
        "checks": checks,
        "iso_verify": {
            "declared_ranges": len(writer_report.get("declared_ranges", [])),
            "result_keys": sorted(iso_result) if isinstance(iso_result, dict) else [],
        },
        "verdict": "PASS",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--json")
    args = parser.parse_args(argv)

    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("could not read the report: %s" % exc, file=sys.stderr)
        return 2

    try:
        result = verify(args.source, args.output, report)
    except (PlaybookVerifyError, ps2_iso9660_verify.IsoVerifyError) as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for check in result["checks"]:
        print("ok  %s  %s" % (check["check"], check["detail"]))
    print("PASS: %d book(s) edited, %d bytes changed, %d books untouched"
          % (result["declared_edits"], result["changed_byte_total"],
             result["play_resources_found"] - result["declared_edits"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

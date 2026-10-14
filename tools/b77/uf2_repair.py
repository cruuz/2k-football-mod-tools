#!/usr/bin/env python3
"""Fix the 2026 alternate, throwback and Rivalries kit art (b772 uf2) IN PLACE on the one uf1 disc.

  uf2_repair.py --disc DISC.iso --receipts DIR            patch (input must be the uf1 disc, or this tool's output)
  uf2_repair.py --disc DISC.iso --receipts DIR --rollback write the recorded uf1 bytes back

There is no room for a second 6 GB copy, so the disc is patched where it lies. Before the first write the tool
records the uf1 bytes of every owned span (``uf1_owned_spans.bin`` + ``.json`` in the receipt folder). The full-disc
scope check streams all 6,004,408,320 bytes with those recorded bytes substituted for the owned spans and requires the
uf1 SHA-256: that proves no byte outside the owned spans changed, and the same record is the rollback.

The input is accepted only as the exact uf1 disc (or an output this tool wrote, proven by the same substitution).
The Studio's kit finish pass (``mod_editor.core.nfl2k5_kit_fixes_2026.apply_alternates``, strict) performs the
writes. Receipts: the write, a zero-byte replay, the full-disc scope, Studio byte equality (each span recompiled
from the recorded uf1 bytes), a check that no other archive entry shares an owned byte, and the xiso files touched
(never default.xbe or vc_53450030/0, /8, /9). Kits whose package lies in one of those packs (ARI home styles 6
and 7 sit in /9) are left to the Studio and listed as deferred.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as native  # noqa: E402

UF1_SHA256 = "351bf0949d26583ba0cb5fec546069b14f183fbfb1519d543a4bb64f13a13759"   # uf1 output disc
DISC_SIZE = 6004408320
BLOCK = 4 * 1024 * 1024
FORBIDDEN_PACKS = {"0", "8", "9"}           # Noah's test disc changes these; uf2 must not
BACKUP = "uf1_owned_spans"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def binary(path, flags):
    return os.open(path, flags | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o644)


def file_sha(path):
    with os.fdopen(binary(path, os.O_RDONLY), "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, document):
    require(not path.is_symlink(), "receipt is a symlink")
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, indent=2)
        stream.write("\n")


def read_resources(path, document):
    """Every kit package the document owns: raw bytes, owned disc ranges (with pack file and resource offset) and
    the pack extents of every OTHER archive entry."""
    wanted = fixes.selectors(document)
    raws, ranges, extents = {}, [], []
    with native._outer_image()(path) as image:
        ids = {native.name_id(s + ".IFF"): s for s in wanted}
        seen = {}
        for entry in image.entries:
            selector = ids.get(entry.name_id)
            if selector is None:
                extents.extend((pack.image_offset + offset, pack.image_offset + offset + length)
                               for pack, offset, length in image._segments(entry.virtual_offset, entry.size))
                continue
            require(selector not in seen, selector + " kit package duplicated")
            seen[selector] = entry
        require(set(seen) == set(wanted), "a kit package is absent")
        for selector, entry in sorted(seen.items()):
            raws[selector] = image.read(entry.virtual_offset, entry.size)
            for row in [r for r in document["textures"] if r["selector"] == selector]:
                inner = 0
                for pack, offset, length in image._segments(entry.virtual_offset + row["offset"], row["length"]):
                    start = pack.image_offset + offset
                    ranges.append(dict(start=start, end=start + length, selector=selector, chunk=row["chunk"],
                                       texture=row["texture"], file="vc_53450030/" + pack.name, pack_offset=offset,
                                       resource_offset=row["offset"] + inner))
                    inner += length
    return raws, sorted(ranges, key=lambda r: r["start"]), extents


def alias_check(ranges, extents):
    extents = sorted(extents)
    starts = [e[0] for e in extents]
    hits = []
    for r in ranges:
        i = bisect.bisect_right(starts, r["end"]) - 1
        while i >= 0 and extents[i][0] < r["end"]:
            if extents[i][1] > r["start"]:
                hits.append(dict(r, other_extent=list(extents[i])))
            i -= 1
            if len(hits) > 50:
                break
    return hits


def read_spans(path, ranges):
    out = bytearray()
    with os.fdopen(binary(path, os.O_RDONLY), "rb") as stream:
        for r in ranges:
            stream.seek(r["start"])
            data = stream.read(r["end"] - r["start"])
            require(len(data) == r["end"] - r["start"], "short span read")
            out += data
    return bytes(out)


def scope(path, ranges, recorded):
    """Stream the whole disc with the recorded uf1 bytes substituted for the owned spans: the result must be the uf1
    disc (nothing outside the owned spans changed). Also counts the changed bytes inside the spans."""
    import numpy as np
    require(path.stat().st_size == DISC_SIZE, "disc length changed")
    substituted, actual = hashlib.sha256(), hashlib.sha256()
    changed = 0
    pieces = []
    at = 0
    for r in ranges:
        n = r["end"] - r["start"]
        pieces.append((r["start"], r["end"], recorded[at:at + n]))
        at += n
    starts = [p[0] for p in pieces]
    with os.fdopen(binary(path, os.O_RDONLY), "rb") as stream:
        offset = 0
        while True:
            block = stream.read(BLOCK)
            if not block:
                break
            actual.update(block)
            end = offset + len(block)
            i = max(bisect.bisect_right(starts, offset) - 1, 0)
            work = None
            while i < len(pieces) and pieces[i][0] < end:
                s, e, data = pieces[i]
                lo, hi = max(offset, s), min(end, e)
                if lo < hi:
                    if work is None:
                        work = bytearray(block)
                    old = data[lo - s:hi - s]
                    now = block[lo - offset:hi - offset]
                    changed += int((np.frombuffer(old, np.uint8) != np.frombuffer(now, np.uint8)).sum())
                    work[lo - offset:hi - offset] = old
                i += 1
            substituted.update(work if work is not None else block)
            offset = end
    return dict(schema="b772/uf2/disc-scope/v1", compared_bytes=offset, disc_sha256=actual.hexdigest(),
                with_recorded_uf1_spans_sha256=substituted.hexdigest(), uf1_sha256=UF1_SHA256,
                changed_bytes_inside_owned=changed, owned_ranges=len(ranges),
                owned_bytes=sum(r["end"] - r["start"] for r in ranges))


def originals(raws, ranges, recorded):
    """The uf1 kit packages, rebuilt from the current packages and the recorded uf1 span bytes."""
    out = {s: bytearray(raw) for s, raw in raws.items()}
    at = 0
    for r in ranges:
        n = r["end"] - r["start"]
        out[r["selector"]][r["resource_offset"]:r["resource_offset"] + n] = recorded[at:at + n]
        at += n
    return {s: bytes(b) for s, b in out.items()}


def rollback(disc, receipts):
    """Write the recorded uf1 bytes back over the recorded spans (the record, not the current data, names them)."""
    blob, meta = receipts / (BACKUP + ".bin"), receipts / (BACKUP + ".json")
    require(blob.is_file() and meta.is_file(), "no uf1 span record to roll back from")
    recorded = blob.read_bytes()
    record = json.loads(meta.read_text(encoding="utf-8"))
    require(record["sha256"] == hashlib.sha256(recorded).hexdigest(), "the uf1 span record is damaged")
    ranges = record["ranges"]
    prior = scope(disc, ranges, recorded)
    require(prior["with_recorded_uf1_spans_sha256"] == UF1_SHA256,
            "the disc differs from uf1 outside the recorded spans: refused")
    with os.fdopen(binary(disc, os.O_RDWR), "r+b") as stream:
        at = 0
        for r in ranges:
            n = r["end"] - r["start"]
            stream.seek(r["start"])
            stream.write(recorded[at:at + n])
            at += n
        stream.flush()
        os.fsync(stream.fileno())
    final = file_sha(disc)
    require(final == UF1_SHA256, "rollback did not restore the uf1 disc")
    return dict(rolled_back=True, ranges=len(ranges), output_sha256=final)


def run(args):
    disc = args.disc.absolute()
    require(disc.is_file() and not args.disc.is_symlink(), "the disc must be a regular file (no symlinks)")
    require(disc.stat().st_size == DISC_SIZE, "unexpected disc size")
    receipts = args.receipts.resolve()
    if args.rollback:
        return rollback(disc, receipts)
    receipts.mkdir(parents=True, exist_ok=True)
    full = fixes.alternates()
    _, all_ranges, _ = read_resources(disc, full)
    deferred = sorted({r["selector"] for r in all_ranges if r["file"].split("/")[-1] in FORBIDDEN_PACKS})
    # kits whose package lies in a pack Noah's test disc rewrites stay Studio-only here (reported, not written)
    document = dict(full, textures=[r for r in full["textures"] if r["selector"] not in deferred])
    raws, ranges, extents = read_resources(disc, document)
    bad = sorted({r["file"] for r in ranges if r["file"].split("/")[-1] in FORBIDDEN_PACKS})
    require(not bad, "an owned span lies in a forbidden pack: " + ", ".join(bad))
    aliases = alias_check(ranges, extents)
    require(not aliases, "another archive entry shares an owned byte: " + json.dumps(aliases[:3]))
    blob, meta = receipts / (BACKUP + ".bin"), receipts / (BACKUP + ".json")
    digest = file_sha(disc)
    plan = [dict(start=r["start"], end=r["end"], selector=r["selector"], chunk=r["chunk"], file=r["file"])
            for r in ranges]
    if digest == UF1_SHA256:
        recorded = read_spans(disc, ranges)
        for selector, raw in raws.items():
            replacements, receipt = fixes.compile_resource(selector, raw, strict=True, document=document)
            require(receipt["state"] == "applied" and replacements, selector + ": input is not the pinned uf1 kit")
        if blob.exists():
            require(blob.read_bytes() == recorded, "an older span record differs from this uf1 disc")
        else:
            require(not blob.is_symlink() and not meta.is_symlink(), "span record is a symlink")
            with os.fdopen(binary(blob, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as stream:
                stream.write(recorded)
                stream.flush()
                os.fsync(stream.fileno())
            write_json(meta, dict(schema="b772/uf2/uf1-owned-spans/v1", uf1_sha256=UF1_SHA256,
                                  sha256=hashlib.sha256(recorded).hexdigest(), bytes=len(recorded), ranges=plan))
    else:
        require(blob.is_file() and meta.is_file(), "unknown disc and no uf1 span record: refused")
        recorded = blob.read_bytes()
        record = json.loads(meta.read_text(encoding="utf-8"))
        require(record["ranges"] == plan and record["sha256"] == hashlib.sha256(recorded).hexdigest(),
                "the uf1 span record does not match this disc's owned spans")
        prior = scope(disc, ranges, recorded)
        require(prior["with_recorded_uf1_spans_sha256"] == UF1_SHA256,
                "the disc differs from uf1 outside the owned spans: refused")
    base = originals(raws, ranges, recorded)
    expected = {}
    for selector, raw in sorted(base.items()):
        replacements, receipt = fixes.compile_resource(selector, raw, strict=True, document=document)
        require(receipt["state"] == "applied" and replacements, selector + ": recorded uf1 kit does not compile")
        expected[selector] = replacements
    receipt = fixes.apply_to_image(disc, strict=True, document=document)
    write_json(receipts / "disc_write.json", dict(schema="b772/uf2/disc-write/v1", disc=str(disc),
                                                  input_sha256=digest, deferred_kits=deferred,
                                                  deferred_reason="kit package in vc_53450030/" +
                                                  "/".join(sorted(FORBIDDEN_PACKS)) + " (Noah's test disc)",
                                                  **receipt))
    replay = fixes.apply_to_image(disc, strict=True, document=document)
    require(replay["written_spans"] == replay["written_bytes"] == replay["changed_bytes"] == 0,
            "repair replay wrote bytes")
    write_json(receipts / "disc_replay.json", dict(schema="b772/uf2/disc-replay/v1", **replay))
    result = scope(disc, ranges, recorded)
    require(result["with_recorded_uf1_spans_sha256"] == UF1_SHA256, "full-disc byte-scope check failed")
    write_json(receipts / "disc_scope.json", dict(result, ranges=plan))
    write_json(receipts / "disc_alias.json", dict(schema="b772/uf2/alias-check/v1", owned_ranges=len(ranges),
                                                  other_entry_extents=len(extents), overlapping=aliases))
    actual, now_ranges, _ = read_resources(disc, document)
    require([(r["start"], r["end"]) for r in now_ranges] == [(r["start"], r["end"]) for r in ranges],
            "resource mapping changed")
    equality = []
    for selector, replacements in sorted(expected.items()):
        for at, data in replacements:
            got = actual[selector][at:at + len(data)]
            equality.append(dict(selector=selector, offset=at, length=len(data), studio_sha256=fixes.sha(data),
                                 disc_sha256=fixes.sha(got), equal=got == data))
    require(all(r["equal"] for r in equality), "disc differs from the Studio compiler")
    write_json(receipts / "disc_studio_equality.json", dict(schema="b772/uf2/studio-equality/v1",
               compiler="mod_editor.core.nfl2k5_kit_fixes_2026.compile_resource (alternates document)",
               all_equal=True, spans=equality))
    files = {}
    for r in ranges:
        files.setdefault(r["file"], set()).add((r["selector"], r["chunk"]))
    summary = {f: {"spans": len(v), "kits_chunks": sorted("%s c%d" % k for k in v)} for f, v in sorted(files.items())}
    write_json(receipts / "disc_files.json", dict(schema="b772/uf2/disc-files/v1", files=summary))
    final = file_sha(disc)
    require(final == result["disc_sha256"], "disc changed during the receipts")
    return dict(kits=len(expected), deferred_kits=deferred, owned_spans=len(ranges),
                written_spans=receipt["written_spans"],
                written_bytes=receipt["written_bytes"], changed_bytes=result["changed_bytes_inside_owned"],
                replay_written_bytes=0, changed_outside_owned=0, aliased_owned_bytes=0, studio_equal=True,
                files=sorted(files), output_sha256=final)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disc", required=True, type=Path)
    parser.add_argument("--receipts", required=True, type=Path)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args)))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, "uf2_repair: REFUSED: " + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

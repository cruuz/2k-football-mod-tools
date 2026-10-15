#!/usr/bin/env python3
"""Apply the uf3 (b773) uniform fixes IN PLACE on a copy of the v0.6.1 base disc.

  uf3_repair.py --disc COPY.iso --receipts DIR            patch (input must be the base disc, or this tool's output)
  uf3_repair.py --disc COPY.iso --receipts DIR --rollback write the recorded base bytes back

The copy is patched where it lies. Before the first write the tool records the base bytes of every owned span
(``base_owned_spans.bin`` + ``.json`` in the receipt folder). The full-disc scope check streams all 6,004,408,320
bytes with those recorded bytes substituted for the owned spans and requires the base SHA-256: that proves no byte
outside the owned spans changed, and the same record is the rollback.

The input is accepted only as the exact base disc (the v0.6.1 fixes disc Noah played, 520429...) or an output this
tool wrote, proven by the same substitution. The Studio's finish pass (``mod_editor.core.nfl2k5_kit_fixes_2026``,
``apply_finish``, strict) performs the writes; nameplate rows read their donor kit (unchanged, pinned) from the same
disc. Receipts: the write, a zero-byte replay, the full-disc scope, Studio byte equality (each span recompiled from
the recorded base bytes), a check that no other archive entry shares an owned byte, the xiso files touched (never
default.xbe or vc_53450030/0), and byte-disjointness from st1's stadium-shadow ranges (``ST1_RANGES``) so the
coordinator's stack tool can combine jobs.
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

BASE_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"   # v0.6.1 fixes disc (base)
DISC_SIZE = 6004408320
BLOCK = 4 * 1024 * 1024
FORBIDDEN_PACKS = {"0"}                     # Noah's test disc rewrites vc_53450030/0; uf3 owns no byte there
# st1's stadium-shadow spans on Noah's test disc (whole-image byte offsets, half-open), from the coordinator's
# fix1/st1_ranges.txt: every uf3 span must be disjoint from them.
ST1_RANGES = ((98189312, 99736736), (99737600, 101366032))
BACKUP = "base_owned_spans"


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


def donor_selectors(document):
    return fixes.donor_kits(document)


def read_resources(path, document, donors=None):
    """Every kit package the document owns: raw bytes, owned disc ranges (with pack file and resource offset) and
    the pack extents of every OTHER archive entry. ``donors`` (a dict) receives the donor kits' bytes (read only)."""
    wanted = fixes.selectors(document)
    want_donors = {native.name_id(s + ".IFF"): s for s in donor_selectors(document)}
    raws, ranges, extents = {}, [], []
    with native._outer_image()(path) as image:
        ids = {native.name_id(s + ".IFF"): s for s in wanted}
        seen = {}
        for entry in image.entries:
            if donors is not None and entry.name_id in want_donors:
                donors[want_donors[entry.name_id]] = image.read(entry.virtual_offset, entry.size)
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
    """Stream the whole disc with the recorded base bytes substituted for the owned spans: the result must be the base
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
    return dict(schema="b773/uf3/disc-scope/v1", compared_bytes=offset, disc_sha256=actual.hexdigest(),
                with_recorded_base_spans_sha256=substituted.hexdigest(), base_sha256=BASE_SHA256,
                changed_bytes_inside_owned=changed, owned_ranges=len(ranges),
                owned_bytes=sum(r["end"] - r["start"] for r in ranges))


def originals(raws, ranges, recorded):
    """The base kit packages, rebuilt from the current packages and the recorded base span bytes."""
    out = {s: bytearray(raw) for s, raw in raws.items()}
    at = 0
    for r in ranges:
        n = r["end"] - r["start"]
        out[r["selector"]][r["resource_offset"]:r["resource_offset"] + n] = recorded[at:at + n]
        at += n
    return {s: bytes(b) for s, b in out.items()}


def st1_disjointness(ranges):
    """Overlap and nearest gap between every owned span and st1's ranges (whole-image byte offsets)."""
    overlap, nearest, rows = 0, None, []
    for r in ranges:
        for lo, hi in ST1_RANGES:
            both = max(0, min(r["end"], hi) - max(r["start"], lo))
            overlap += both
            gap = max(lo - r["end"], r["start"] - hi, 0)
            if nearest is None or gap < nearest[0]:
                nearest = (gap, r["selector"], r["chunk"], r["file"], r["start"], r["end"], lo, hi)
    in_89 = [dict(selector=r["selector"], chunk=r["chunk"], file=r["file"], start=r["start"], end=r["end"])
             for r in ranges if r["file"].split("/")[-1] in ("8", "9")]
    return dict(schema="b773/uf3/st1-disjoint/v1", st1_ranges=[list(x) for x in ST1_RANGES], owned_spans=len(ranges),
                owned_spans_in_packs_8_9=in_89, overlapping_bytes=overlap,
                nearest=dict(gap_bytes=nearest[0], selector=nearest[1], chunk=nearest[2], file=nearest[3],
                             span=[nearest[4], nearest[5]], st1_range=[nearest[6], nearest[7]]) if nearest else None)


def rollback(disc, receipts):
    """Write the recorded base bytes back over the recorded spans (the record, not the current data, names them)."""
    blob, meta = receipts / (BACKUP + ".bin"), receipts / (BACKUP + ".json")
    require(blob.is_file() and meta.is_file(), "no base span record to roll back from")
    recorded = blob.read_bytes()
    record = json.loads(meta.read_text(encoding="utf-8"))
    require(record["sha256"] == hashlib.sha256(recorded).hexdigest(), "the base span record is damaged")
    ranges = record["ranges"]
    prior = scope(disc, ranges, recorded)
    require(prior["with_recorded_base_spans_sha256"] == BASE_SHA256,
            "the disc differs from the base outside the recorded spans: refused")
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
    require(final == BASE_SHA256, "rollback did not restore the base disc")
    return dict(rolled_back=True, ranges=len(ranges), output_sha256=final)


def run(args):
    disc = args.disc.absolute()
    require(disc.is_file() and not args.disc.is_symlink(), "the disc must be a regular file (no symlinks)")
    require(disc.stat().st_size == DISC_SIZE, "unexpected disc size")
    receipts = args.receipts.resolve()
    if args.rollback:
        return rollback(disc, receipts)
    receipts.mkdir(parents=True, exist_ok=True)
    document = fixes.finish()
    donors = {}
    raws, ranges, extents = read_resources(disc, document, donors)
    require(set(donors) == set(donor_selectors(document)), "a donor kit package is absent")
    bad = sorted({r["file"] for r in ranges if r["file"].split("/")[-1] in FORBIDDEN_PACKS})
    require(not bad, "an owned span lies in a forbidden pack: " + ", ".join(bad))
    disjoint = st1_disjointness(ranges)
    require(disjoint["overlapping_bytes"] == 0, "an owned span overlaps st1's stadium-shadow ranges")
    aliases = alias_check(ranges, extents)
    require(not aliases, "another archive entry shares an owned byte: " + json.dumps(aliases[:3]))
    blob, meta = receipts / (BACKUP + ".bin"), receipts / (BACKUP + ".json")
    digest = file_sha(disc)
    plan = [dict(start=r["start"], end=r["end"], selector=r["selector"], chunk=r["chunk"], file=r["file"])
            for r in ranges]
    if digest == BASE_SHA256:
        recorded = read_spans(disc, ranges)
        for selector, raw in raws.items():
            replacements, receipt = fixes.compile_resource(selector, raw, strict=True, document=document,
                                                           kits=donors)
            require(receipt["state"] == "applied" and replacements, selector + ": input is not the pinned base kit")
        if blob.exists():
            require(blob.read_bytes() == recorded, "an older span record differs from this base disc")
        else:
            require(not blob.is_symlink() and not meta.is_symlink(), "span record is a symlink")
            with os.fdopen(binary(blob, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as stream:
                stream.write(recorded)
                stream.flush()
                os.fsync(stream.fileno())
            write_json(meta, dict(schema="b773/uf3/base-owned-spans/v1", base_sha256=BASE_SHA256,
                                  sha256=hashlib.sha256(recorded).hexdigest(), bytes=len(recorded), ranges=plan))
    else:
        require(blob.is_file() and meta.is_file(), "unknown disc and no base span record: refused")
        recorded = blob.read_bytes()
        record = json.loads(meta.read_text(encoding="utf-8"))
        require(record["ranges"] == plan and record["sha256"] == hashlib.sha256(recorded).hexdigest(),
                "the base span record does not match this disc's owned spans")
        prior = scope(disc, ranges, recorded)
        require(prior["with_recorded_base_spans_sha256"] == BASE_SHA256,
                "the disc differs from the base outside the owned spans: refused")
    base = originals(raws, ranges, recorded)
    expected = {}
    for selector, raw in sorted(base.items()):
        replacements, receipt = fixes.compile_resource(selector, raw, strict=True, document=document, kits=donors)
        require(receipt["state"] == "applied" and replacements, selector + ": recorded base kit does not compile")
        expected[selector] = replacements
    receipt = fixes.apply_to_image(disc, strict=True, document=document)
    write_json(receipts / "disc_write.json", dict(schema="b773/uf3/disc-write/v1", disc=str(disc),
                                                  input_sha256=digest,
                                                  **receipt))
    replay = fixes.apply_to_image(disc, strict=True, document=document)
    require(replay["written_spans"] == replay["written_bytes"] == replay["changed_bytes"] == 0,
            "repair replay wrote bytes")
    write_json(receipts / "disc_replay.json", dict(schema="b773/uf3/disc-replay/v1", **replay))
    result = scope(disc, ranges, recorded)
    require(result["with_recorded_base_spans_sha256"] == BASE_SHA256, "full-disc byte-scope check failed")
    write_json(receipts / "disc_scope.json", dict(result, ranges=plan))
    write_json(receipts / "disc_alias.json", dict(schema="b773/uf3/alias-check/v1", owned_ranges=len(ranges),
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
    write_json(receipts / "disc_studio_equality.json", dict(schema="b773/uf3/studio-equality/v1",
               compiler="mod_editor.core.nfl2k5_kit_fixes_2026.compile_resource (uf3 document)",
               all_equal=True, spans=equality))
    files = {}
    for r in ranges:
        files.setdefault(r["file"], set()).add((r["selector"], r["chunk"]))
    summary = {f: {"spans": len(v), "kits_chunks": sorted("%s c%d" % k for k in v)} for f, v in sorted(files.items())}
    write_json(receipts / "disc_files.json", dict(schema="b773/uf3/disc-files/v1", files=summary))
    final = file_sha(disc)
    require(final == result["disc_sha256"], "disc changed during the receipts")
    write_json(receipts / "disc_st1_disjoint.json", disjoint)
    return dict(kits=len(expected), owned_spans=len(ranges), st1_overlapping_bytes=0,
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
        parser.exit(2, "uf3_repair: REFUSED: " + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

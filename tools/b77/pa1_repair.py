#!/usr/bin/env python3
"""Apply the pa1 (b773, N32) above-the-knee pants hem IN PLACE on a copy of the v0.6.1 base disc.

  pa1_repair.py --disc COPY.iso --receipts DIR              patch (input: the base disc or this tool's output)
  pa1_repair.py --disc COPY.iso --receipts DIR --rollback   write the recorded base bytes back
  pa1_repair.py --disc BASE.iso --receipts DIR --check      read only: compile every span to its pin, check layout

The copy is patched where it lies. Before the first write the tool records the base bytes of every owned span
(``base_owned_spans.bin`` + ``.json`` in the receipt folder): the pants, bump and sideline-player chunks of every
current-season kit in ``data/nfl2k5_pants_hem_2026.json``. The full-disc scope check streams every byte with those
recorded bytes substituted for the owned spans and requires the base SHA-256: that proves no byte outside the owned
spans changed, and the same record is the rollback.

The input is accepted only as the exact base disc (the v0.6.1 fixes disc Noah played, 520429...) or an output this
tool wrote, proven by the same substitution. The Studio's pass (``mod_editor.core.nfl2k5_pants_hem_2026``, strict)
performs the writes. Receipts: the write, a zero-byte replay, the full-disc scope, Studio byte equality (each span
recompiled from the recorded base bytes), a check that no other archive entry shares an owned byte, the xiso files
touched (never default.xbe or vc_53450030/0), byte-disjointness from st1's stadium-shadow ranges and from the uf3
kit spans on the same disc, so the coordinator's stack tool can combine jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "b77"))
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from mod_editor.core import nfl2k5_pants_hem_2026 as hem  # noqa: E402
from mod_editor.core import nfl2k5_modern_metlife as native  # noqa: E402
import uf3_repair as uf3  # noqa: E402

BASE_SHA256 = uf3.BASE_SHA256
DISC_SIZE = uf3.DISC_SIZE
FORBIDDEN_PACKS = uf3.FORBIDDEN_PACKS
ST1_RANGES = uf3.ST1_RANGES
BACKUP = "base_owned_spans"

require = uf3.require
binary = uf3.binary
file_sha = uf3.file_sha
write_json = uf3.write_json
alias_check = uf3.alias_check
read_spans = uf3.read_spans


def read_resources(path, document):
    """Every kit package the document owns: raw bytes, owned disc ranges (with pack file and resource offset) and
    the pack extents of every OTHER archive entry."""
    wanted = hem.selectors(document)
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


def scope(path, ranges, recorded):
    result = uf3.scope(path, ranges, recorded)
    result["schema"] = "b773/pa1/disc-scope/v1"
    return result


def originals(raws, ranges, recorded):
    return uf3.originals(raws, ranges, recorded)


def st1_disjointness(ranges):
    result = uf3.st1_disjointness(ranges)
    result["schema"] = "b773/pa1/st1-disjoint/v1"
    return result


def uf3_disjointness(path, ranges):
    """Overlap between the owned spans and the uf3 kit document's spans on the same disc (the two jobs stack)."""
    _raws, theirs, _extents = uf3.read_resources(path, fixes.finish(), {})
    overlap = sum(max(0, min(a["end"], b["end"]) - max(a["start"], b["start"])) for a in ranges for b in theirs
                  if a["start"] < b["end"] and b["start"] < a["end"])
    shared = sorted({r["selector"] for r in ranges} & {r["selector"] for r in theirs})
    return dict(schema="b773/pa1/uf3-disjoint/v1", owned_spans=len(ranges), uf3_kit_spans=len(theirs),
                kits_in_both=shared, overlapping_bytes=overlap)


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


def check(disc, receipts):
    """Read only, on the base disc itself: every owned span compiled by the Studio module to its output pin, the owned
    spans' layout (files, aliasing, st1 and uf3 disjointness). The disc is opened read only and never written."""
    require(file_sha(disc) == BASE_SHA256, "the check runs on the exact base disc only")
    receipts.mkdir(parents=True, exist_ok=True)
    document = hem.spec()
    raws, ranges, extents = read_resources(disc, document)
    bad = sorted({r["file"] for r in ranges if r["file"].split("/")[-1] in FORBIDDEN_PACKS})
    aliases = alias_check(ranges, extents)
    disjoint = st1_disjointness(ranges)
    stack = uf3_disjointness(disc, ranges)
    cache, spans, owned = {}, [], {}
    for row in document["textures"]:
        owned.setdefault(row["selector"], []).append((row["offset"], row["offset"] + row["length"]))
    for selector, raw in sorted(raws.items()):
        replacements, receipt = hem.compile_resource(selector, raw, strict=True, document=document, cache=cache)
        require(receipt["state"] == "applied" and len(replacements) == len(owned[selector]),
                selector + ": base kit does not compile to its pins")
        new = bytearray(raw)
        for at, data in replacements:
            new[at:at + len(data)] = data
        again, replay = hem.compile_resource(selector, bytes(new), strict=True, document=document)
        require(not again and replay["changed_bytes"] == 0, selector + ": the compiled kit is not a no-op replay")
        for part in receipt["parts"]:
            spans.append(dict(selector=selector, chunk=part["chunk_index"], offset=part["offset"],
                              length=part["length"], before_sha256=part["before_sha256"],
                              after_sha256=part["after_sha256"], changed_bytes=part["changed_bytes"]))
    files = {}
    for r in ranges:
        files.setdefault(r["file"], set()).add((r["selector"], r["chunk"]))
    result = dict(schema="b773/pa1/offline-check/v1", disc_sha256=BASE_SHA256, kits=len(raws), owned_spans=len(ranges),
                  owned_bytes=sum(r["end"] - r["start"] for r in ranges), compiled_to_pins=len(spans),
                  replay_no_op=True, changed_bytes=sum(s["changed_bytes"] for s in spans),
                  forbidden_packs=bad, aliased=aliases, st1_overlapping_bytes=disjoint["overlapping_bytes"],
                  uf3_overlapping_bytes=stack["overlapping_bytes"], kits_also_in_uf3=len(stack["kits_in_both"]),
                  files={f: len(v) for f, v in sorted(files.items())})
    write_json(receipts / "check_compile.json", dict(result, spans=spans))
    write_json(receipts / "check_st1_disjoint.json", disjoint)
    write_json(receipts / "check_uf3_disjoint.json", stack)
    require(not bad and not aliases and disjoint["overlapping_bytes"] == 0 and stack["overlapping_bytes"] == 0,
            "the owned spans are not cleanly separable")
    require(file_sha(disc) == BASE_SHA256, "the disc changed during the check")
    return {k: v for k, v in result.items() if k != "aliased"}


def run(args):
    disc = args.disc.absolute()
    require(disc.is_file() and not args.disc.is_symlink(), "the disc must be a regular file (no symlinks)")
    require(disc.stat().st_size == DISC_SIZE, "unexpected disc size")
    receipts = args.receipts.resolve()
    if args.rollback:
        return rollback(disc, receipts)
    if getattr(args, "check", False):
        return check(disc, receipts)
    receipts.mkdir(parents=True, exist_ok=True)
    document = hem.spec()
    raws, ranges, extents = read_resources(disc, document)
    bad = sorted({r["file"] for r in ranges if r["file"].split("/")[-1] in FORBIDDEN_PACKS})
    require(not bad, "an owned span lies in a forbidden pack: " + ", ".join(bad))
    disjoint = st1_disjointness(ranges)
    require(disjoint["overlapping_bytes"] == 0, "an owned span overlaps st1's stadium-shadow ranges")
    aliases = alias_check(ranges, extents)
    require(not aliases, "another archive entry shares an owned byte: " + json.dumps(aliases[:3]))
    stack = uf3_disjointness(disc, ranges)
    require(stack["overlapping_bytes"] == 0, "an owned span overlaps a uf3 kit span")
    blob, meta = receipts / (BACKUP + ".bin"), receipts / (BACKUP + ".json")
    digest = file_sha(disc)
    plan = [dict(start=r["start"], end=r["end"], selector=r["selector"], chunk=r["chunk"], file=r["file"])
            for r in ranges]
    if digest == BASE_SHA256:
        recorded = read_spans(disc, ranges)
        if blob.exists():
            require(blob.read_bytes() == recorded, "an older span record differs from this base disc")
        else:
            require(not blob.is_symlink() and not meta.is_symlink(), "span record is a symlink")
            with os.fdopen(binary(blob, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as stream:
                stream.write(recorded)
                stream.flush()
                os.fsync(stream.fileno())
            write_json(meta, dict(schema="b773/pa1/base-owned-spans/v1", base_sha256=BASE_SHA256,
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
    expected, cache = {}, {}
    for selector, raw in sorted(base.items()):
        replacements, receipt = hem.compile_resource(selector, raw, strict=True, document=document, cache=cache)
        require(receipt["state"] == "applied" and replacements, selector + ": recorded base kit does not compile")
        expected[selector] = replacements
    receipt = hem.apply_to_image(disc, strict=True, document=document)
    write_json(receipts / "disc_write.json", dict(schema="b773/pa1/disc-write/v1", disc=disc.name,
                                                  input_sha256=digest, **receipt))
    replay = hem.apply_to_image(disc, strict=True, document=document)
    require(replay["written_spans"] == replay["written_bytes"] == replay["changed_bytes"] == 0,
            "repair replay wrote bytes")
    write_json(receipts / "disc_replay.json", dict(schema="b773/pa1/disc-replay/v1", **replay))
    result = scope(disc, ranges, recorded)
    require(result["with_recorded_base_spans_sha256"] == BASE_SHA256, "full-disc byte-scope check failed")
    write_json(receipts / "disc_scope.json", dict(result, ranges=plan))
    write_json(receipts / "disc_alias.json", dict(schema="b773/pa1/alias-check/v1", owned_ranges=len(ranges),
                                                  other_entry_extents=len(extents), overlapping=aliases))
    actual, now_ranges, _ = read_resources(disc, document)
    require([(r["start"], r["end"]) for r in now_ranges] == [(r["start"], r["end"]) for r in ranges],
            "resource mapping changed")
    equality = []
    for selector, replacements in sorted(expected.items()):
        for at, data in replacements:
            got = actual[selector][at:at + len(data)]
            equality.append(dict(selector=selector, offset=at, length=len(data), studio_sha256=hem.sha(data),
                                 disc_sha256=hem.sha(got), equal=got == data))
    require(all(r["equal"] for r in equality), "disc differs from the Studio compiler")
    write_json(receipts / "disc_studio_equality.json", dict(schema="b773/pa1/studio-equality/v1",
               compiler="mod_editor.core.nfl2k5_pants_hem_2026.compile_resource", all_equal=True, spans=equality))
    files = {}
    for r in ranges:
        files.setdefault(r["file"], set()).add((r["selector"], r["chunk"]))
    summary = {f: {"spans": len(v), "kits_chunks": sorted("%s c%d" % k for k in v)} for f, v in sorted(files.items())}
    write_json(receipts / "disc_files.json", dict(schema="b773/pa1/disc-files/v1", files=summary))
    final = file_sha(disc)
    require(final == result["disc_sha256"], "disc changed during the receipts")
    write_json(receipts / "disc_st1_disjoint.json", disjoint)
    write_json(receipts / "disc_uf3_disjoint.json", stack)
    return dict(kits=len(expected), owned_spans=len(ranges), st1_overlapping_bytes=0, uf3_overlapping_bytes=0,
                written_spans=receipt["written_spans"], written_bytes=receipt["written_bytes"],
                changed_bytes=result["changed_bytes_inside_owned"], replay_written_bytes=0, changed_outside_owned=0,
                aliased_owned_bytes=0, studio_equal=True, files=sorted(files), output_sha256=final)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--disc", required=True, type=Path)
    parser.add_argument("--receipts", required=True, type=Path)
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="read only on the base disc: compile every span to its pin and check the layout")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args)))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, "pa1_repair: REFUSED: " + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

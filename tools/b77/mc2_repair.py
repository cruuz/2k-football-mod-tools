#!/usr/bin/env python3
"""Pinned mc2 MyCareer repair for the SOFTDRINK 2K28 v0.6.1 (2026-10-13) disc, with native and disc receipts.

mc2 fixes, all inside the MyCareer owner (tools/mycareer_mode/runtime.c, mod_editor/core/nfl2k5_my_career_mode.py):
the controller that drives the MyCareer menus owns MyPlayer (was always port 1), B on the entry screen and the
Apartment quits to the main menu with the native confirmation, a backup is asked before kickoff (start him or
Supersim to his snaps), and the draft-path creation fix (see the mc2 report).

The Studio compiler supplies all owner bytes and hook destinations. Only this owner's code, its hooks, allocator
seals and derived section digests may change. Disc commands need a separate existing copy of the pinned base disc;
unknown hashes refuse before any write. Never point this at Noah's own disc folder.

    xbe   --input default.xbe --output NEW.xbe --receipt R.json     repair one executable, replay must write 0
    disc  --disc COPY.iso --receipt R.json                          write the fixed spans into the disc copy
    scope --before BASE.iso --after COPY.iso --receipt R.json       every differing byte is in a declared span
    predict --base BASE.iso --receipt R.json                        expected output disc hash, read only
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import xdvdfs_compact as xd
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tools.b77.g2_repair import read, scope_receipt, sha, write_new
from tools.b77.sp1_repair import open_binary, digest_disc, require

# Beta 80 recorded both hashes from the complete October 13 disc. Its exact owner remains reproducible.
# Projecting that executable back into any accepted revision verifies every other disc byte before writing.
BASE_DISC_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"
BASE_XBE_SHA256 = "1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f"
BETA80_XBE_SHA256 = "4939def556918bb24ebe2d9075b284fac17c53db9fb8791b759ec2c3206b1b8f"
BETA80_DISC_SHA256 = "9adcb4ef06f0fa7e2c9a9b538dda35ca630ff13c35c3d17a9938260f87803703"
REPAIRED_XBE_SHA256 = "9f2d7b6b5b5f8327f0ca95446d324af9382767350956f0cb20dbf78f52317610"
DISC_SIZE, XBE_OFFSET, XBE_SIZE = 6004408320, 2398208, 12300288


def studio_owner(payload: bytes, code: dict, state: dict, *, previous=False) -> tuple[bytes, dict]:
    """Exactly what mode.apply would install on this executable (graded or not)."""
    from mod_editor.core import nfl2k5_letter_grades as grades
    graded = XbeImage(payload).read(0x541288, 4) == grades.GRADE_FLAGS
    return mode.code_for(code["va"], state["va"], letter_grades=graded,
                         grade_bands=grades._owned_state(payload)[2] if graded else None, previous=previous)


def repair(payload: bytes) -> tuple[bytes, dict]:
    digest = sha(payload)
    if digest not in (BASE_XBE_SHA256, BETA80_XBE_SHA256, REPAIRED_XBE_SHA256):
        raise ValueError(f"unrecognized mc2 executable: {digest}")
    result, receipt = build(payload)
    if sha(result) != REPAIRED_XBE_SHA256:
        raise ValueError("repair template differs from the validated revision")
    return result, receipt


def build(payload: bytes, *, previous=False) -> tuple[bytes, dict]:
    """The Studio owner on this executable, with every postcondition except the output pin."""
    if space.status(payload) != "applied":
        raise ValueError("invalid allocator seals")
    image = XbeImage(payload)
    code, state = mode.legacy.allocations(payload)
    requests = space._read_scale_directory(payload)
    content, labels = studio_owner(payload, code, state, previous=previous)
    spans = [(code["raw"], code["size"])]
    buf = bytearray(payload)
    buf[code["raw"]:code["raw"] + code["size"]] = content
    # Relinking the owner's template also moves its native hook destinations.
    sites = mode.sites(code["va"], state["va"], season_birth_dates=True, previous=previous)
    if previous:
        historical_sites = {va for _, va, _, _ in sites}
        sites = list(sites)
        for name, va, before, after in mode.sites(code["va"], state["va"], season_birth_dates=True):
            if va not in historical_sites:
                sites.append((name, va, after, before))
    for _name, va, _before, after in sites:
        at = image.offset(va, len(after))
        spans.append((at, len(after)))
        buf[at:at + len(after)] = after
    spans += [(space.SCALE_DIRECTORY + 12, 32),
              (space.DIRECTORY + len(space.SCALE_TAG) + 8, 32)]
    space._seal_scaleout(buf, requests)
    for section in _sections(buf):
        lo, size = section.raw_offset, section.raw_size
        if payload[lo:lo + size] != buf[lo:lo + size]:
            at = section.header_offset + 36
            spans.append((at, 20))
            buf[at:at + 20] = section_digest(bytes(buf), section)
    result = bytes(buf)
    # The shipped (10-13) executable carries older templates of owners revised since (draft AI, economy, honors,
    # overtime), which the whole-image check of the neighbours cannot recognize; the MyCareer owner itself is checked.
    if mode.status(result, context=False) != ("previous" if previous else "applied"):
        raise ValueError("the repaired MyCareer owner does not validate")
    if space.status(result) != "applied" or space._read_scale_directory(result) != requests:
        raise ValueError("allocator postcondition failed")
    allocations = space.layout(payload)["allocations"]
    if space.layout(result)["allocations"] != allocations:
        raise ValueError("an owner allocation moved")
    preserved = []
    for row in allocations:
        if (row["owner"] == mode.OWNER and row["kind"] == "code") or row["owner"] == space.DIRECTORY_OWNER:
            continue
        at, size = row["raw"], row["size"]
        if payload[at:at + size] != result[at:at + size]:
            raise ValueError(f"changed another reservation: {row['owner']}")
        preserved.append(dict(owner=row["owner"], kind=row["kind"],
                              va=hex(row["va"]), size=size, sha256=sha(result[at:at + size])))
    receipt = dict(schema="b774/mc2-native-repair/v1",
                   status="already_applied" if result == payload else "repaired",
                   file="default.xbe", scope=scope_receipt(payload, result, sorted(set(spans))),
                   code=code, primary_state=state, extra_state_va=hex(mode.EXTRA_VA),
                   code_padding=code["va"] + mode.TAG_OFFSET - labels["content_end"],
                   preserved_reservations=preserved,
                   studio_equal=True, outside_scope_changed_bytes=0)
    return result, receipt


def disc_xbe(stream):
    entry = xd.read_layout(stream).entries["default.xbe"]
    require((entry.byte_offset, entry.size) == (XBE_OFFSET, XBE_SIZE), "foreign XBE extent")
    stream.seek(XBE_OFFSET)
    return stream.read(XBE_SIZE)


def projected_disc_hash(stream, executable):
    return digest_disc(stream, [(XBE_OFFSET, executable)])


def verify_disc_input(stream, raw, before):
    """Authenticate the complete disc, including a replay with the current compiler's output."""
    native_hash = sha(raw)
    if native_hash == BASE_XBE_SHA256:
        require(before == BASE_DISC_SHA256, "unknown complete input disc hash")
    elif native_hash == BETA80_XBE_SHA256:
        require(before == BETA80_DISC_SHA256, "unknown complete input disc hash")
    else:
        require(native_hash == REPAIRED_XBE_SHA256, "unrecognized mc2 executable")
        historical, _ = build(raw, previous="beta-80")
        require(sha(historical) == BETA80_XBE_SHA256, "historical executable identity mismatch")
        require(projected_disc_hash(stream, historical) == BETA80_DISC_SHA256, "unknown complete input disc hash")


def repair_disc(path):
    with open_binary(path, writable=True) as stream:
        before = digest_disc(stream)
        raw = disc_xbe(stream)
        verify_disc_input(stream, raw, before)
        fixed, receipt = repair(raw)
        expected = before if fixed == raw else projected_disc_hash(stream, fixed)
        written = 0
        for row in receipt["scope"]["scope"]:
            lo, size = row["offset"], row["size"]
            if raw[lo:lo + size] == fixed[lo:lo + size]:
                continue
            stream.seek(XBE_OFFSET + lo)
            require(stream.write(fixed[lo:lo + size]) == size, "short fixed-span write")
            written += size
        stream.flush()
        os.fsync(stream.fileno())
        require(disc_xbe(stream) == fixed, "disc readback mismatch")
        after = digest_disc(stream)
        require(after == expected, "unexpected complete output disc hash")
        receipt.update(disc_before_sha256=before, disc_after_sha256=after,
                       bytes_written=written, disc_size=DISC_SIZE)
        return receipt


def compare_discs(before, after):
    require(before.resolve() != after.resolve(), "scope needs separate files")
    with open_binary(before) as a, open_binary(after) as b:
        require(digest_disc(a) == BASE_DISC_SHA256, "comparison source is not the pinned base")
        raw = disc_xbe(a)
        fixed, receipt = repair(raw)
        expected = projected_disc_hash(a, fixed)
        spans = sorted((XBE_OFFSET + r["offset"], r["size"]) for r in receipt["scope"]["scope"])
        require(disc_xbe(b) == fixed, "disc differs from the Studio compiler output")
        a.seek(0)
        b.seek(0)
        at = changed = 0
        while old := a.read(8 << 20):
            new = b.read(len(old))
            require(len(new) == len(old), "disc length changed")
            restored = bytearray(new)
            for lo, size in spans:
                start, end = max(lo, at), min(lo + size, at + len(old))
                if start < end:
                    restored[start - at:end - at] = old[start - at:end - at]
            require(restored == old, f"outside-scope change near {at:#x}")
            if old != new:
                changed += sum(x != y for x, y in zip(old, new))
            at += len(old)
        require(at == DISC_SIZE and not b.read(1), "unexpected disc size")
        require(digest_disc(b) == expected, "unknown output disc hash")
    return dict(schema="b774/mc2-disc-scope/v1", changed_bytes=changed,
                outside_scope_changed_bytes=0, studio_equal=True, size=at, disc_after_sha256=expected,
                scope=[dict(offset=lo, size=size) for lo, size in spans])


def predict(base):
    """Expected repaired-disc hash, streamed read-only from the pinned base (no disc copy is written)."""
    with open_binary(base) as stream:
        require(digest_disc(stream) == BASE_DISC_SHA256, "prediction source is not the pinned base")
        raw = disc_xbe(stream)
        fixed, receipt = repair(raw)
        after = projected_disc_hash(stream, fixed)
    return dict(schema="b774/mc2-disc-prediction/v2", base_sha256=BASE_DISC_SHA256, predicted_sha256=after,
                xbe_sha256=sha(fixed), spans=len(receipt["scope"]["scope"]),
                changed_bytes=receipt["scope"]["changed_bytes"])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    x = sub.add_parser("xbe")
    x.add_argument("--input", type=Path, required=True)
    x.add_argument("--output", type=Path, required=True)
    d = sub.add_parser("disc")
    d.add_argument("--disc", type=Path, required=True)
    c = sub.add_parser("scope")
    c.add_argument("--before", type=Path, required=True)
    c.add_argument("--after", type=Path, required=True)
    q = sub.add_parser("predict")
    q.add_argument("--base", type=Path, required=True)
    for parser in (x, d, c, q):
        parser.add_argument("--receipt", type=Path, required=True)
    args = p.parse_args(argv)
    inputs = [v.resolve() for k, v in vars(args).items() if isinstance(v, Path) and k != "receipt"]
    require(args.receipt.resolve() not in inputs, "receipt must be separate")
    if args.command == "xbe":
        require(args.input.resolve() != args.output.resolve(), "XBE output must be separate")
        fixed, result = repair(read(args.input))
        again, replay = repair(fixed)
        require(again == fixed and replay["scope"]["changed_bytes"] == 0, "replay differs")
        result["replay_changed_bytes"] = 0
        write_new(args.output, fixed)
    elif args.command == "predict":
        result = predict(args.base)
    elif args.command == "disc":
        result = repair_disc(args.disc)
    else:
        result = compare_discs(args.before, args.after)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

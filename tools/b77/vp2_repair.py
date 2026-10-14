#!/usr/bin/env python3
"""Fixed-span automatic coach-AI repair for a verified v0.6.1-family copy.

apply-disc writes ONLY the supplied private copy. All 32 profiles and the XBE
are prepared before the first write. Portrait textures and saves are untouched.
Other native repairs compose through an exact approved input-XBE SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_coach_ai as ai, nfl2k5_cpu_money_downs as money
from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_throw_tuning as tt
from mod_editor.core import platform_compat as io
from mod_editor.core.nfl2k5_cave_manifest import changed_runs
from nfl2k5_playbook_position_recode import OuterImage

SIZE = 12300288
KNOWN_INPUTS = frozenset((
    "ffc5a33c99819d83017d75b2e4173d988328870834fd465ce67af0674d9b4118",
    "30adaffa0c75efc790f551f229dbef4e072ef636082f23184d7ee3ed54c6d589",
))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def repair_xbe(source, *, approved=()):
    ai.require(len(source) == SIZE and space.is_scaleout(source) and space.status(source) == "applied",
               "Expected a sealed, fixed-size v0.6.1-family executable")
    ai.require(all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) for h in approved),
               "Approved input hashes must be lowercase SHA-256")
    state = ai.status(source)
    ai.require(state != "foreign", "Foreign coach-AI prerequisites or mixed owner hooks")
    ai.require(sha(source) in KNOWN_INPUTS | set(approved) or state == "applied",
               f"Unapproved composed input XBE {sha(source)}; supply its exact --approved-input-xbe-sha256")
    ai.require(money.status(source) == "applied", "Expected an installed recognized CPU policy")
    candidate, policy = money.upgrade_to_modern2(source)
    candidate, feature = ai.apply(candidate)
    ai.require(len(candidate) == len(source), "XBE repair changed file size")
    ai.require(ai.apply(candidate)[0] == candidate and money.upgrade_to_modern2(candidate)[0] == candidate,
               "Native repair is not idempotent")
    runs = list(changed_runs(source, candidate))
    before_allocations = space.layout(source)["allocations"]
    ai.require(all(row in space.layout(candidate)["allocations"] for row in before_allocations),
               "Native repair moved an existing allocator owner")
    receipt = dict(schema="b77/vp2_native_xbe_repair/v1", status="applied" if runs else "already_applied",
                   before_sha256=sha(source), after_sha256=sha(candidate), size=len(candidate),
                   changed_bytes=sum(b - a for a, b in runs), idempotent=True, existing_allocations_unchanged=True,
                   modern2=policy, coach_ai=feature,
                   spans=[dict(offset=a, size=b - a, before_sha256=sha(source[a:b]), after_sha256=sha(candidate[a:b]))
                          for a, b in runs], runtime_witness=False)
    return candidate, receipt


def hashes(path, excluded=()):
    """Whole-file and outside-write-span hashes in one bounded streaming pass."""
    whole, outside = hashlib.sha256(), hashlib.sha256()
    spans = sorted((a, a + n) for a, n in excluded)
    ai.require(all(a >= 0 and b > a for a, b in spans), "Invalid excluded span")
    ai.require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "Overlapping disc write spans")
    pos, index = 0, 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            whole.update(chunk)
            end, at = pos + len(chunk), pos
            while index < len(spans) and spans[index][1] <= pos:
                index += 1
            j = index
            while j < len(spans) and spans[j][0] < end:
                a, b = spans[j]
                if a > at:
                    outside.update(chunk[at - pos:a - pos])
                at = max(at, min(end, b))
                j += 1
            if at < end:
                outside.update(chunk[at - pos:])
            pos = end
    ai.require(not spans or spans[-1][1] <= pos, "Write span lies beyond file")
    return whole.hexdigest(), outside.hexdigest()


def receipt_preflight(path, before, after=None):
    if not path.exists():
        return None
    ai.require(path.is_file() and not path.is_symlink(), "Receipt must be a regular file")
    previous = json.loads(path.read_text())
    ai.require(previous.get("schema", "").startswith("b77/vp2_native_"), "Foreign receipt file")
    ai.require(previous.get("after_sha256") == before or
               (after is not None and previous.get("before_sha256") == before and previous.get("after_sha256") == after),
               "Existing receipt does not describe this exact input/output")
    return previous


def publish(path, receipt, previous):
    if previous is not None:
        ai.require(previous["after_sha256"] == receipt["after_sha256"], "Existing receipt output differs")
        return
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")


def apply_disc(path, receipt_path, *, approved=()):
    ai.require(path.is_file() and not path.is_symlink(), "Choose a regular private disc copy")
    ai.require(path.resolve() != receipt_path.resolve(), "Receipt overlaps disc")
    print("Preflighting executable and 32 final playbooks", flush=True)
    with path.open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        off, length = tt.image_xbe_extent(stream.fileno(), size)
        ai.require(length == SIZE, "Unexpected executable extent")
        source = io.pread(stream.fileno(), length, off)
    candidate, xbe_receipt = repair_xbe(source, approved=approved)
    prepared = ai.plan_profiles(path, progress=lambda line: print(line, flush=True))
    scope = [(off, length)]
    with OuterImage(path) as archive:
        for index, before, after, report in prepared:
            virtual = archive.entries[index].virtual_offset + 32 + ai.PROFILE_OFFSET
            for pack, offset, count in archive._segments(virtual, ai.PROFILE_SIZE):
                scope.append((pack.image_offset + offset, count))
    before_sha, outside = hashes(path, scope)
    previous = receipt_preflight(receipt_path, before_sha)
    if previous is not None:
        ai.require(candidate == source and all(a == b for _, a, b, _ in prepared),
                   "Existing receipt accompanies an incomplete or changed repair")
    print("Preflight complete; writing fixed spans and checking readback", flush=True)
    resource_receipt = ai.write_profiles(path, prepared)
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        ai.require(os.fstat(fd).st_size == size and io.pread(fd, length, off) == source,
                   "Executable or disc size changed after preflight")
        if candidate != source:
            ai.require(io.pwrite(fd, candidate, off) == length, "Short XBE write")
        os.fsync(fd)
        ai.require(io.pread(fd, length, off) == candidate, "XBE readback failed")
        ai.require(os.fstat(fd).st_size == size, "Disc size changed")
    finally:
        os.close(fd)
    after_sha, outside_after = hashes(path, scope)
    ai.require(outside == outside_after, "Disc changed outside the declared fixed spans")
    receipt = dict(schema="b77/vp2_native_disc_repair/v1", status="already_applied" if before_sha == after_sha else "applied",
                   before_sha256=before_sha, after_sha256=after_sha, size=size, xbe=xbe_receipt,
                   resources=resource_receipt, readback_verified=True, outside_spans_sha256=outside,
                   outside_spans_unchanged=True, write_spans=[dict(offset=a, size=n) for a, n in scope],
                   runtime_witness=False, portraits="Native routing only; no portrait textures changed", saves_changed=[])
    publish(receipt_path, receipt, previous)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    xbe = commands.add_parser("apply-xbe")
    xbe.add_argument("--xbe", type=Path, required=True)
    xbe.add_argument("--output", type=Path, required=True)
    disc = commands.add_parser("apply-disc")
    disc.add_argument("--image", type=Path, required=True, help="private COPY to modify in place")
    for command in (xbe, disc):
        command.add_argument("--receipt", type=Path, required=True)
        command.add_argument("--approved-input-xbe-sha256", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "apply-disc":
            report = apply_disc(args.image, args.receipt, approved=args.approved_input_xbe_sha256)
        else:
            ai.require(args.xbe.resolve() != args.output.resolve(), "XBE input and output must differ")
            ai.require(args.receipt.resolve() not in (args.xbe.resolve(), args.output.resolve()), "Receipt overlaps XBE")
            with args.xbe.open("rb") as stream:
                source = stream.read(SIZE + 1)
            result, report = repair_xbe(source, approved=args.approved_input_xbe_sha256)
            previous = receipt_preflight(args.receipt, sha(source), sha(result))
            if args.output.exists():
                ai.require(args.output.is_file() and not args.output.is_symlink() and args.output.read_bytes() == result,
                           "Refusing to overwrite a different output")
            else:
                with args.output.open("xb") as stream:
                    stream.write(result)
                    stream.flush()
                    os.fsync(stream.fileno())
            ai.require(args.output.read_bytes() == result, "XBE file readback failed")
            report["readback_verified"] = True
            publish(args.receipt, report, previous)
        print(json.dumps({k: report[k] for k in ("status", "before_sha256", "after_sha256")}), flush=True)
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

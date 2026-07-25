#!/usr/bin/env python3
"""Independently verify an edited ESPN NFL 2K5 (PS2) save.

This is the deterministic check that stands behind the save writer: it reads
the original and edited saves and re-derives, from the bytes alone, that

  1. no file was added, removed or renamed, and every sidecar other than
     ``EXTRA`` is byte-identical;
  2. the payload changed *only* inside the byte ranges the writer declared;
  3. ``EXTRA`` equals the CRC-32 of the edited payload (and the original's
     ``EXTRA`` matched its own payload, so the baseline was sound);
  4. the ROST arena still parses and every table count is unchanged, i.e. the
     edit stayed inside its fixed allocation instead of moving the arena.

It shares no code path with the writer beyond the save reader, and it never
trusts the writer's report: the declared ranges are an input to be checked,
not evidence.  Exit status is nonzero if any check fails.

Usage::

    nfl2k5_ps2_save_verify.py --original <before.psu> --edited <after.psu> \\
        --changes <write-report.json>
    nfl2k5_ps2_save_verify.py --selftest
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zlib

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_save as save_lib  # noqa: E402


class VerifyError(AssertionError):
    """A verification contract was violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def changed_ranges(before: bytes, after: bytes) -> list[tuple[int, int]]:
    """Coalesce differing byte positions into (offset, length) spans."""
    _require(len(before) == len(after),
             f"payload size changed: {len(before)} -> {len(after)}")
    spans: list[tuple[int, int]] = []
    start = None
    for index, (lhs, rhs) in enumerate(zip(before, after)):
        if lhs != rhs:
            if start is None:
                start = index
        elif start is not None:
            spans.append((start, index - start))
            start = None
    if start is not None:
        spans.append((start, len(before) - start))
    return spans


def verify(original: save_lib.Ps2Save, edited: save_lib.Ps2Save,
           declared: list[dict] | None = None) -> dict:
    report: dict[str, object] = {"schema": "nfl2k5_ps2_save_verify/v1"}

    _require(original.directory == edited.directory,
             f"save directory changed: {original.directory} -> {edited.directory}")
    _require(set(original.files) == set(edited.files),
             "the set of save files changed: "
             f"{sorted(set(original.files) ^ set(edited.files))}")

    payload_name = original.payload_name
    for name in sorted(original.files):
        if name in (payload_name, "EXTRA"):
            continue
        _require(original.files[name] == edited.files[name],
                 f"sidecar {name} changed but only the payload and EXTRA may")

    _require(original.crc_is_valid(),
             "the ORIGINAL save's EXTRA does not match its payload; "
             "the baseline is not a sound reference")
    _require(edited.crc_is_valid(),
             "the edited save's EXTRA does not match its payload CRC-32")

    spans = changed_ranges(original.payload, edited.payload)
    report["changed_spans"] = [{"offset": off, "length": length} for off, length in spans]
    report["changed_bytes"] = sum(length for _off, length in spans)

    if declared is not None:
        allowed = [(int(item["offset"]), int(item["length"])) for item in declared]
        for off, length in spans:
            covered = any(
                off >= a_off and off + length <= a_off + a_len
                for a_off, a_len in allowed
            )
            _require(covered,
                     f"payload changed at 0x{off:x}+{length}, which no declared "
                     "edit covers")
        report["declared_ranges"] = [
            {"offset": off, "length": length} for off, length in allowed
        ]

    before_tables = save_lib.parse_roster(original)["tables"]
    after_tables = save_lib.parse_roster(edited)["tables"]
    _require(set(before_tables) == set(after_tables), "ROST table set changed")
    for name in before_tables:
        lhs = before_tables[name]
        rhs = after_tables[name]
        _require(lhs["count"] == rhs["count"],
                 f"ROST table {name} count changed "
                 f"{lhs['count']} -> {rhs['count']}")
        _require(lhs["offset"] == rhs["offset"],
                 f"ROST table {name} moved; the arena must not be relocated")
    report["tables_checked"] = len(before_tables)
    report["payload_bytes"] = len(edited.payload)
    report["crc32"] = zlib.crc32(edited.payload) & 0xFFFFFFFF
    report["result"] = "PASS"
    return report


def selftest() -> int:
    import tempfile

    original = save_lib._synthetic_save()
    edited = save_lib._synthetic_save()
    change = save_lib.set_player_name(edited, 0, "first", "Delta")
    edited.reseal()

    report = verify(original, edited, [change])
    assert report["result"] == "PASS", report
    # Differing bytes are bounded by the declared slot; they need not fill it
    # (UTF-16LE high bytes and shared letters often match the original).
    assert 0 < report["changed_bytes"] <= change["length"], report

    # A forged save whose EXTRA was not updated must be rejected.
    forged = save_lib._synthetic_save()
    save_lib.set_player_name(forged, 0, "first", "Delta")  # no reseal
    try:
        verify(original, forged, [change])
    except VerifyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("stale EXTRA must fail verification")

    # An edit outside the declared range must be rejected.
    sneaky = save_lib._synthetic_save()
    first = save_lib.set_player_name(sneaky, 0, "first", "Delta")
    save_lib.set_player_name(sneaky, 1, "first", "Echo")
    sneaky.reseal()
    try:
        verify(original, sneaky, [first])
    except VerifyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("undeclared edit must fail verification")

    del tempfile
    print("NFL2K5_PS2_SAVE_VERIFY_SELFTEST_PASS "
          "accepts=sealed-declared rejects=stale-crc,undeclared-edit")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--original", type=Path, help="save before the edit")
    parser.add_argument("--edited", type=Path, help="save after the edit")
    parser.add_argument("--changes", type=Path,
                        help="writer report JSON whose declared ranges must bound the diff")
    parser.add_argument("--directory", help="save directory when reading a card image")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.original or not args.edited:
        parser.error("--original and --edited are required unless --selftest is given")

    declared = None
    if args.changes:
        payload = json.loads(args.changes.read_text(encoding="utf-8"))
        declared = payload.get("changes", payload)

    report = verify(
        save_lib.load_save(args.original, args.directory),
        save_lib.load_save(args.edited, args.directory),
        declared,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

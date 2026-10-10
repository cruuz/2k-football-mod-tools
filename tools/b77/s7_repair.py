#!/usr/bin/env python3
"""Field-scoped SOFTDRINK v0.5 SportsCenter playoff repair (beta 77, job S7); writes a separate default.xbe.

The v0.5 disc carries the 9/5 seven-seed Playoff Picture work, but native emulation of the real executable
(tools/b77/s7_sportscenter_probe.py) showed four SportsCenter leftovers of the old twelve-team / 17-week game:

* the Playoff Picture labelled the seventh SEED "On The Bubble" (the first-team-out sticker still sat on row 7);
* that label switched to "Better Luck Next Year" one week early (week 17 of 18);
* the show banner named every postseason round one round early ("Wildcard Week" after Week 18, ...);
* the primetime card's NEXT WEEK line said "Playoffs" with one regular-season week left.

Only ``default.xbe`` is touched, and only these bytes (virtual addresses; the file offsets are in the receipt):

  .text   0x2CD456  1 byte   0xEF -> 0xEE   show banner round table base (add eax,-0x12)
  .text   0x220E8E  1 byte   0x10 -> 0x11   Playoff Picture sticker: last regular week
  .text   0x264233  1 byte   0x10 -> 0x11   primetime card: NEXT WEEK 'Playoffs' week
  .rdata  0x50FAB8  4 bytes  4 -> 5         widget 0x133D3780 (row 8 Clinched cell) becomes the sticker label
  .rdata  0x50FAC4  4 bytes  5 -> 4         widget 0x7362B270 (old sticker) becomes a blank rank-7 status cell
  .rdata  0x50FAC8  4 bytes  0 -> 7         (its rank)
  Second pass (week-label audit, same day), all .text:
  0x358C8D 1 byte 0xEF -> 0xEE   by-week schedule browser header (FUN_00358bf0): round table base, row 17 = Week 18
  0x24C8C8 1 byte 0xEF -> 0xEE   label of a team idle in a round / bye (FUN_0024c8a0): same base
  0x2CF4C0 1 byte 0x04 -> 0x05   SportsCenter menu teaser (FUN_002cf4b0): six cases (weeks played 12..17), not five
  0x2CF4C3 4 bytes               its out-of-range jump now lands on the shared epilogue 0x2CF4EA
  0x2CF4CA 4 bytes               its jump table pointer 0x2CF60C -> 0x2CF604
  0x2CF601 31 bytes              old default block + 5-entry table -> nops + 6-entry table (inside the same function)
  plus the stored SHA-1 section digest of .text and .rdata (20 bytes each, recomputed from the final bytes).

Every other byte of the file is identical (the receipt proves it).  The repair is a function of those bytes only:
other jobs' repairs of ``default.xbe`` (shared) can run before or after, because the section digests are
recomputed from whatever the section holds when this runs.  Deterministic and idempotent; an input whose owned
bytes are neither the v0.5 values nor the repaired values is refused.

Usage::

    python3 tools/b77/s7_repair.py --xbe v05/default.xbe --out-dir s7_out
        [--expected-xbe-sha256 HEX]   # for a stacked input (another job's repair ran first)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_playoff_picture as picture  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _section_for_offset, _sections, section_digest  # noqa: E402

V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
OWNER = "s7_sportscenter_playoffs"

# (label, va, v0.5 bytes, repaired bytes)
OWNED = (
    ("show_banner_round_base", 0x002CD456, b"\xef", b"\xee"),
    ("picture_bubble_last_week", 0x00220E8E, b"\x10", b"\x11"),
    ("primetime_next_week_playoffs", 0x00264233, b"\x10", b"\x11"),
    ("bubble_label_on_first_out", 0x0050FAB8, struct.pack("<I", 4), struct.pack("<I", 5)),
    ("retired_bubble_sticker_kind", 0x0050FAC4, struct.pack("<I", 5), struct.pack("<I", 4)),
    ("retired_bubble_sticker_rank", 0x0050FAC8, struct.pack("<I", 0), struct.pack("<I", 7)),
    # second pass (week-label audit, 2026-10-08)
    ("week_browser_header_round_base", 0x00358C8D, b"\xef", b"\xee"),
    ("idle_team_label_round_base", 0x0024C8C8, b"\xef", b"\xee"),
    ("teaser_dispatch_bound", 0x002CF4C0, b"\x04", b"\x05"),
    ("teaser_default_target", 0x002CF4C3, struct.pack("<I", 0x13A), struct.pack("<I", 0x23)),
    ("teaser_table_pointer", 0x002CF4CA, struct.pack("<I", 0x2CF60C), struct.pack("<I", 0x2CF604)),
    ("teaser_table", 0x002CF601, picture.TEASER_BLOCK_RETAIL, picture.TEASER_BLOCK_PATCHED),
)


class RepairError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RepairError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read()


def write_new(path: Path, data: bytes) -> None:
    if path.exists():
        require(read(path) == data, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def scope_receipt(before: bytes, after: bytes, spans: list[tuple[int, int]]) -> dict:
    require(len(before) == len(after), "repair changed the file size")
    restored = bytearray(after)
    for offset, size in spans:
        require(0 <= offset and size >= 0 and offset + size <= len(before), "invalid repair scope")
        restored[offset:offset + size] = before[offset:offset + size]
    require(bytes(restored) == before, "repair changed bytes outside the declared scope")
    return {"before_sha256": sha(before), "after_sha256": sha(after), "size": len(after),
            "scope": [{"offset": offset, "size": size} for offset, size in spans],
            "outside_scope_identical": True, "outside_scope_restored_sha256": sha(bytes(restored))}


def owned_state(xbe: bytes, sections) -> dict[str, str]:
    result = {}
    for label, va, before, after in OWNED:
        at = season._offset(xbe, va, sections)
        got = xbe[at:at + len(before)]
        result[label] = "v05" if got == before else "repaired" if got == after else "foreign"
    return result


def inherited_ok(xbe: bytes, sections) -> None:
    """The input must already be a seven-seed, 18-week executable; every OTHER presentation site is applied."""
    bad = [group for group in season.GROUPS if season.group_status(xbe, group) != "applied"]
    mine = {label for label, *_ in OWNED}
    for site in picture.sites():
        if site.label not in mine and picture._state(xbe, site, sections) != "applied":
            bad.append(f"picture:{site.label}")
    if bad:
        raise RepairError("the input is not a seven-seed 18-week executable (not applied: "
                          + ", ".join(bad[:6]) + ")")


def check_library_agrees() -> None:
    """The Studio module and this script must describe exactly the same bytes (drift guard)."""
    known = {s.label: s for s in picture.week_sites() + picture.sites()}
    for label, va, before, after in OWNED:
        site = known.get(label)
        require(site is not None, f"library site {label} missing")
        require(site.va == va and site.patched == after and site.retail == before,
                f"library site {label} differs from the repair table")


def repair_xbe(payload: bytes) -> tuple[bytes, dict]:
    check_library_agrees()
    sections = _sections(payload)
    state = owned_state(payload, sections)
    require("foreign" not in state.values(), f"unexpected bytes at owned sites: {state}")
    require(len(set(state.values())) == 1, f"owned sites are partially repaired: {state}")
    inherited_ok(payload, sections)
    if set(state.values()) == {"repaired"}:
        receipt = scope_receipt(payload, payload, [])
        return payload, {**receipt, "disc_file": "default.xbe", "owner": OWNER, "state": "already repaired",
                         "owned_sites": state, "sections_repinned": [], "changed_bytes": 0}
    out = bytearray(payload)
    spans: list[tuple[int, int]] = []
    touched: set[int] = set()
    sites = []
    for label, va, before, after in OWNED:
        at = season._offset(payload, va, sections)
        section = _section_for_offset(sections, at)
        require(at + len(after) <= section.raw_offset + section.raw_size, f"{label} crosses its section")
        out[at:at + len(after)] = after
        spans.append((at, len(after)))
        touched.add(section.index)
        sites.append({"label": label, "va": hex(va), "file_offset": hex(at), "section": section.index,
                      "before": before.hex(), "after": after.hex()})
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            out[at:at + 20] = section_digest(bytes(out), section)
            spans.append((at, 20))
    after_bytes = bytes(out)
    for section in _sections(after_bytes):
        if section.index in touched:
            require(section_digest(after_bytes, section) == section.stored_digest,
                    f"section {section.index} digest does not match its bytes")
    require(set(owned_state(after_bytes, _sections(after_bytes)).values()) == {"repaired"}, "read-back failed")
    spans.sort()
    receipt = scope_receipt(payload, after_bytes, spans)
    return after_bytes, {**receipt, "disc_file": "default.xbe", "owner": OWNER, "state": "repaired",
                         "sites": sites, "sections_repinned": sorted(touched),
                         "changed_bytes": sum(a != b for a, b in zip(payload, after_bytes))}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", required=True, type=Path, help="default.xbe of the v0.5 disc (or a stacked copy)")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-xbe-sha256", help="accept this exact input instead of the v0.5 hash")
    args = parser.parse_args(argv)
    payload = read(args.xbe)
    expected = args.expected_xbe_sha256 or V05_XBE_SHA256
    require(sha(payload) == expected, f"unexpected input hash for {args.xbe.name}: {sha(payload)}")
    fixed, receipt = repair_xbe(payload)
    destination = args.out_dir / "default.xbe"
    require(destination.resolve() != args.xbe.resolve(), "output must be a separate copy")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_new(destination, fixed)
    require(sha(read(destination)) == sha(fixed), "write verification failed")
    result = {"job": "s7", "files": [receipt], "gameplay_witness": False,
              "composition": "week-keyed compare immediates and round-table bases, the SportsCenter teaser dispatch (bound, default target, table pointer, 6-entry table), three .rdata descriptor dwords, two section digests"}
    text = json.dumps(result, indent=2) + "\n"
    receipt_path = args.out_dir / "s7_scope_receipt.json"
    if receipt_path.exists():
        require(receipt_path.read_text(encoding="utf-8") == text, "refusing to replace a different receipt")
    else:
        receipt_path.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"xbe": receipt["after_sha256"], "changed_bytes": receipt.get("changed_bytes", 0),
                      "state": receipt["state"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

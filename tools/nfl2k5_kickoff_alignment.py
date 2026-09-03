#!/usr/bin/env python3
"""Dynamic-kickoff alignment for ESPN NFL 2K5 (playbook data patch, PHASE 1 of the 2024+ kickoff).

What the retail disc holds (read out of every one of the 37 ``PLAY`` resources in the outer archive
``vc_53450030``; the special-teams formations are byte-identical across all 37 books):

* ``Kickoff`` (formation type 8): the kicker (slot 0) stands 8.92 yd behind the ball (x +1.0 yd), the
  other ten 10.0 yd behind it (x -21.8 .. +22.0 yd).  Slot positions are **relative to the line of
  scrimmage** (the ball), so the 35-yard kickoff moved every one of them 5 yd downfield with the ball:
  the kicker's run-up is the retail 8.9 yd - "he lines up way further back and runs up to the 35" is
  the retail distance, not a bug.
* ``Kick Return`` (type 9): two returners 69.3 yd from the ball (from the 35 that is 4.3 yd deep in the
  end zone), a front five 15.0 yd from the ball, two at 42 yd and two at 30-32 yd.

The 2026 rule (NFL Rule 6, as amended in 2024 and 2025; see KICK_RULES_2026-09-03_NIGHT.md for the
citations): the ball is kicked from the 35; the ten other kicking-team players line up with a foot on
the receiving team's 40 (the restraining line); at least nine receiving-team players line up in the
setup zone between their 35 and 30, at least seven of them on their 35, no more than one of the
others in each third of the field; at most two returners stand in the landing zone (goal line to the
20) or the end zone; nobody but the kicker and the returners may move until the ball touches the
ground or a player in the landing zone / end zone; a kick into the end zone that is downed or goes out
is a touchback at the 35; a kick short of the landing zone puts the ball on the receiving team's 40.

This tool writes the **alignment** part of that into the two formation records of every book, in
line-of-scrimmage units (cm, 1 yd = 91.44) assuming the kickoff spot is the 35 (the kick-rules
executable patch):

* Kickoff: kicker at ``kicker_depth_yd`` behind the ball (default 5.0 yd - Noah asked for a shorter
  run-up; the retail ``Safety Kick`` formation already starts its kicker 3 yd back, so the engine
  copes), the ten others 25 yd **ahead** of the ball (the receiving 40), retail x spread.
* Kick Return: seven on the receiving 35 (30 yd from the ball) across the width, two more in the
  setup zone on the receiving 31 (34 yd), one per outside third, two returners at the receiving 1 and
  5 (64 / 60 yd), inside the landing zone.

Everything else is untouched: ``Onside Kickoff``, ``Onside Kick Return``, ``Safety Kick``, the play
chains (the coverage players' first action node still waits for the kick), the AI.  The hold-until-
landing rule and the short-kick spot are engine work (see the report); this is data only.

Recognition is byte-exact: every book's two records must carry the retail slot bytes ("retail"), or
the tool's own bytes for some kicker depth ("applied"); anything else is "foreign" and refused.

Usage::

    nfl2k5_kickoff_alignment.py inspect IMAGE.xiso.iso            # both formations, retail vs 2026, per book
    nfl2k5_kickoff_alignment.py status  IMAGE.xiso.iso
    nfl2k5_kickoff_alignment.py apply   COPY.xiso.iso [--kicker-depth-yd 5] [--receipt PATH]

``apply`` only ever writes into the image it is given: copy the disc first.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys
from typing import Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_playbook_position_recode as recode  # noqa: E402
from mod_editor.core.nfl2k5_playbook_inspector import FORMATION_BASE, FORMATION_SIZE, parse_playbook_resource  # noqa: E402

YARD_CM = 91.44
SLOT_BASE = 0x1A            # first slot record inside the 0xB4 formation record
SLOT_STRIDE = 14
SLOT_COUNT = 11
SLOTS_SIZE = SLOT_STRIDE * SLOT_COUNT      # 154 bytes: the part of a record this tool owns
KICKOFF_TYPE = 8
KICK_RETURN_TYPE = 9
KICKOFF_NAME = "Kickoff"
KICK_RETURN_NAME = "Kick Return"

RETAIL_KICKER_DEPTH_YD = 8.92
DEFAULT_KICKER_DEPTH_YD = 5.0
COVERAGE_LINE_YD = 25.0     # the receiving 40 when the ball is on the kicking 35
RESTRAINING_LINE_YD = 30.0  # the receiving 35
SETUP_ZONE_BACK_YD = 34.0   # the receiving 31 (inside the 35..30 zone)
RETURNER_DEEP_YD = 64.0     # the receiving 1
RETURNER_SHORT_YD = 60.0    # the receiving 5

# retail slot (x, depth) in cm, slot order 0..10; depth: - = behind the ball (kicking team), + = toward
# the receiving team's goal
RETAIL_KICKOFF_XZ: tuple[tuple[int, int], ...] = (
    (91, -816), (1210, -914), (-1192, -914), (785, -914), (2016, -914), (-1992, -914),
    (1606, -914), (-1592, -914), (374, -914), (-357, -914), (-757, -914),
)
RETAIL_KICK_RETURN_XZ: tuple[tuple[int, int], ...] = (
    (-696, 6348), (696, 6331), (-1489, 1371), (-670, 1371), (1389, 1371), (17, 1371), (661, 1371),
    (901, 3849), (-862, 3879), (-1227, 2738), (1105, 2886),
)


def _cm(yd: float) -> int:
    return int(round(yd * YARD_CM))


def kickoff_xz_2026(kicker_depth_yd: float = DEFAULT_KICKER_DEPTH_YD) -> tuple[tuple[int, int], ...]:
    """Kicker ``kicker_depth_yd`` behind the ball, the other ten on the receiving 40 (retail x spread)."""

    if not 1.0 <= float(kicker_depth_yd) <= 15.0:
        raise recode.RecodeError("kicker depth must be between 1 and 15 yards")
    rows = [(RETAIL_KICKOFF_XZ[0][0], -_cm(kicker_depth_yd))]
    rows += [(x, _cm(COVERAGE_LINE_YD)) for x, _z in RETAIL_KICKOFF_XZ[1:]]
    return tuple(rows)


# slots 0/1 = returners (the return plays' deep chains), 2..6 = the retail front line, 7/8 the two
# off-line setup-zone men (one per outside third), 9/10 fill the seven-man restraining line
KICK_RETURN_XZ_2026: tuple[tuple[int, int], ...] = (
    (-400, _cm(RETURNER_DEEP_YD)), (400, _cm(RETURNER_SHORT_YD)),
    (-2000, _cm(RESTRAINING_LINE_YD)), (-1330, _cm(RESTRAINING_LINE_YD)), (-670, _cm(RESTRAINING_LINE_YD)),
    (0, _cm(RESTRAINING_LINE_YD)), (670, _cm(RESTRAINING_LINE_YD)),
    (-1000, _cm(SETUP_ZONE_BACK_YD)), (1000, _cm(SETUP_ZONE_BACK_YD)),
    (1330, _cm(RESTRAINING_LINE_YD)), (2000, _cm(RESTRAINING_LINE_YD)),
)


def slots_xz(record_slots: bytes) -> tuple[tuple[int, int], ...]:
    """(x, depth) of column 0 for the 11 slots of a 154-byte slot block."""

    return tuple((struct.unpack_from("<h", record_slots, s * SLOT_STRIDE + 2)[0],
                  struct.unpack_from("<h", record_slots, s * SLOT_STRIDE + 8)[0]) for s in range(SLOT_COUNT))


def with_xz(record_slots: bytes, xz: Sequence[tuple[int, int]]) -> bytes:
    """The slot block with every column of x and depth replaced (stance / mirror bytes kept)."""

    out = bytearray(record_slots)
    for s, (x, z) in enumerate(xz):
        base = s * SLOT_STRIDE
        struct.pack_into("<hhh", out, base + 2, x, x, x)
        struct.pack_into("<hhh", out, base + 8, z, z, z)
    return bytes(out)


@dataclass(frozen=True)
class FormationRef:
    book: str
    index: int
    name: str
    type_code: int
    body_offset: int            # of the slot block inside the book body
    virtual_offset: int         # of the slot block inside the outer archive
    slots: bytes                # the 154 bytes as found


def _formation_refs(book: recode.Book, raw: bytes) -> dict[str, FormationRef]:
    parsed = parse_playbook_resource(raw)
    refs: dict[str, FormationRef] = {}
    for f in parsed.formations:
        rec = FORMATION_BASE + f.index * FORMATION_SIZE
        flags = struct.unpack_from("<I", book.body, rec + 4)[0]
        type_code = (flags >> 8) & 0x3F
        if (f.name, type_code) not in ((KICKOFF_NAME, KICKOFF_TYPE), (KICK_RETURN_NAME, KICK_RETURN_TYPE)):
            continue
        off = rec + SLOT_BASE
        refs[f.name] = FormationRef(book.name, f.index, f.name, type_code, off,
                                    book.virtual_offset + recode.RESOURCE_HEADER_SIZE + off,
                                    book.body[off: off + SLOTS_SIZE])
    return refs


def _state_of(ref: FormationRef) -> tuple[str, float | None]:
    """('retail' | 'applied' | 'foreign', kicker depth in yd when applied)."""

    xz = slots_xz(ref.slots)
    if ref.name == KICKOFF_NAME:
        if xz == RETAIL_KICKOFF_XZ:
            return "retail", None
        depth_yd = -xz[0][1] / YARD_CM
        try:
            expected = kickoff_xz_2026(depth_yd)
        except recode.RecodeError:
            return "foreign", None
        if xz == expected and ref.slots == with_xz(ref.slots, expected):
            return "applied", round(depth_yd, 2)
        return "foreign", None
    if xz == RETAIL_KICK_RETURN_XZ:
        return "retail", None
    if xz == KICK_RETURN_XZ_2026 and ref.slots == with_xz(ref.slots, KICK_RETURN_XZ_2026):
        return "applied", None
    return "foreign", None


def _load(archive: recode.OuterImage) -> list[tuple[recode.Book, dict[str, FormationRef]]]:
    """Every book with both formations; books without a kickoff pair (practice / editor books) are skipped."""

    out = []
    for book in recode.load_books(archive):
        raw = archive.read_entry(book.entry_index)
        refs = _formation_refs(book, raw)
        if not refs:
            continue
        recode._require(set(refs) == {KICKOFF_NAME, KICK_RETURN_NAME},
                        f"{book.name}: expected a '{KICKOFF_NAME}' (type 8) and a '{KICK_RETURN_NAME}' (type 9) formation")
        out.append((book, refs))
    recode._require(len(out) >= 32, f"only {len(out)} books carry the kickoff formations")
    return out


def inspect_rows(path: Path | str) -> list[dict[str, object]]:
    rows = []
    with recode.OuterImage(path) as archive:
        for book, refs in _load(archive):
            for name in (KICKOFF_NAME, KICK_RETURN_NAME):
                ref = refs[name]
                state, depth = _state_of(ref)
                rows.append({"book": book.name, "formation": name, "index": ref.index, "state": state,
                             "kicker_depth_yd": depth, "virtual_offset": f"0x{ref.virtual_offset:x}",
                             "slots_yd": [(round(x / YARD_CM, 2), round(z / YARD_CM, 2)) for x, z in slots_xz(ref.slots)]})
    return rows


def status(path: Path | str) -> dict[str, object]:
    rows = inspect_rows(path)
    states = {row["state"] for row in rows}
    if states == {"retail"}:
        overall = "retail"
    elif states == {"applied"}:
        overall = "applied"
    else:
        overall = "foreign"
    depths = {row["kicker_depth_yd"] for row in rows if row["kicker_depth_yd"] is not None}
    return {"status": overall, "books": len({row["book"] for row in rows}),
            "kicker_depth_yd": sorted(depths)[0] if len(depths) == 1 else None,
            "foreign": [f"{row['book']}/{row['formation']}" for row in rows if row["state"] == "foreign"],
            "rows": rows}


def apply(path: Path | str, *, kicker_depth_yd: float = DEFAULT_KICKER_DEPTH_YD,
          progress: Callable[[str], None] | None = None) -> dict[str, object]:
    """Write the 2026 alignment into every book of the image at ``path`` (a COPY); byte-exact receipt."""

    progress = progress or (lambda _m: None)
    kickoff_xz = kickoff_xz_2026(kicker_depth_yd)
    edits: list[dict[str, object]] = []
    changed = 0
    with recode.OuterImage(path, writable=True) as archive:
        loaded = _load(archive)
        for book, refs in loaded:
            for ref in refs.values():
                state, _depth = _state_of(ref)
                recode._require(state == "retail", f"{book.name}/{ref.name}: slot bytes are {state}, not retail")
        for book, refs in loaded:
            progress(f"{book.name}: kickoff coverage to the receiving 40, return setup zone 35-30")
            for name, xz in ((KICKOFF_NAME, kickoff_xz), (KICK_RETURN_NAME, KICK_RETURN_XZ_2026)):
                ref = refs[name]
                new = with_xz(ref.slots, xz)
                if new == ref.slots:
                    continue
                archive.write(ref.virtual_offset, new)
                back = archive.read(ref.virtual_offset, SLOTS_SIZE)
                recode._require(back == new, f"{book.name}/{name}: read-back differs after the write")
                delta = sum(1 for a, b in zip(ref.slots, new) if a != b)
                changed += delta
                edits.append({"book": book.name, "formation": name, "index": ref.index,
                              "image_offset": f"0x{archive.image_offset(ref.virtual_offset):x}",
                              "virtual_offset": f"0x{ref.virtual_offset:x}", "changed_bytes": delta})
    after = status(path)
    recode._require(after["status"] == "applied", "post-apply verification failed")
    return {"status": after["status"], "kicker_depth_yd": float(kicker_depth_yd), "changed_bytes": changed,
            "books": after["books"], "edits": edits,
            "kickoff_xz_cm": list(kickoff_xz), "kick_return_xz_cm": list(KICK_RETURN_XZ_2026),
            "assumes_kickoff_yard": 35, "rule": "NFL Rule 6 (2024 dynamic kickoff, 2025 amendments), 2026 season"}


def format_inspect(rows: Sequence[Mapping[str, object]]) -> str:
    lines = []
    for row in rows:
        depth = f" kicker {row['kicker_depth_yd']} yd" if row["kicker_depth_yd"] is not None else ""
        lines.append(f"{row['book']:>9} {row['formation']:<12} #{row['index']:<3} {row['state']:<8}{depth} @ {row['virtual_offset']}")
        lines.append("            " + " ".join(f"({x:+.1f},{z:+.1f})" for x, z in row["slots_yd"]))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_inspect = sub.add_parser("inspect", help="both formations per book, yards from the ball (no writes)")
    p_inspect.add_argument("path")
    p_status = sub.add_parser("status", help="retail / applied / foreign")
    p_status.add_argument("path")
    p_apply = sub.add_parser("apply", help="write the 2026 alignment into the image (a COPY)")
    p_apply.add_argument("path")
    p_apply.add_argument("--kicker-depth-yd", type=float, default=DEFAULT_KICKER_DEPTH_YD)
    p_apply.add_argument("--receipt", help="write the JSON receipt here")
    args = parser.parse_args(argv)
    if args.command == "inspect":
        print(format_inspect(inspect_rows(args.path)))
        return 0
    if args.command == "status":
        result = status(args.path)
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))
        return 0
    receipt = apply(args.path, kicker_depth_yd=args.kicker_depth_yd, progress=print)
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps({k: receipt[k] for k in ("status", "kicker_depth_yd", "changed_bytes", "books")}, indent=1))
    return 0


__all__ = ["DEFAULT_KICKER_DEPTH_YD", "KICK_RETURN_XZ_2026", "RETAIL_KICKOFF_XZ", "RETAIL_KICK_RETURN_XZ",
           "RETAIL_KICKER_DEPTH_YD", "apply", "inspect_rows", "kickoff_xz_2026", "slots_xz", "status", "with_xz"]


if __name__ == "__main__":
    raise SystemExit(main())

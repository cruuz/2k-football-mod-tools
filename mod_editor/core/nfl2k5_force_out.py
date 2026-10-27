"""Modern sideline catches: no force-out credit from the 2008 season on, USA retail. EXPERIMENTAL.

Report (b778, v0.6.1): a receiver carried out of bounds by a defender is ruled a catch without either foot down. The NFL
removed that "force-out" rule from the 2008 season: a receiver must get both feet (or another body part) down in
bounds, and contact that carries him out no longer counts.

The retail ruling (static disassembly of the USA executable, b778 fo1 report):

- While a catch is in progress (ball state ``[0xE602C0] == 4``: the ball is in the receiver's hands but the catch is
  not yet a completion) the boundary handler 0x157930 runs every frame. When a body point of the holder that touches
  the ground is out of bounds (0x236B10 returns 3), it decides the play:
- 0x157995..0x1579BC, the force-out credit: if ``[[0xE602EC]+0x168]`` is set and the holder's current animation
  category (``[[[holder+0x10]+4]+3]``) is 0x1C, 0x1A or 0x0A (the being-tackled / contact states), the catch is
  completed at once (0x157A23: 0x0B9B50 completes it, 0x0A0820 blows the play dead) whatever his feet did.
  ``+0x168`` is set when the ball attaches to the receiver (0x1C71D0 -> 0x0A0F20 -> 0x0B7820): his lateral position
  half a second ahead (x + 0.5 * vx) is still inside the sideline (|x| < 2438.4 cm), i.e. he "would have come down in
  bounds".
- Otherwise 0x236700 needs at least two in-bounds foot-downs (``[holder+0x40]+0x5C``, counted per frame by 0x158A20
  with the in-bounds foot test 0x1578D0 / 0x157460) and 0.1 s of control: a catch then, else incomplete.

This owner hooks the read of the credit (``mov edx, [ecx+0x168]`` at 0x15799B) with a jump into a small cave that
keeps the credit only in an ESPN 25th Anniversary moment whose season is before 2008 (game mode ``[0xE5FF80] == 8``,
Situation flag ``[0xE6014C] == 0``, physical row ``[0xBF1858]`` in a 51-bit mask built from the moment catalog, the
same season source the era ball and the Anniversary rules use). Everywhere else the credit reads as zero, so the
retail two-feet test above decides. Nothing else changes: a receiver who got both feet down and is then carried out is
still a catch, the end lines never had the credit, and fumbles, interceptions and the replay challenge are untouched.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

OWNER = "nfl2k5_force_out"
CODE_SIZE = 96
MASK_OFFSET = CODE_SIZE - 8
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
MODERN_FROM_SEASON = 2008          # the NFL dropped the force-out rule for the 2008 season
BUILD_CAPTION = "Modern sideline catches: no force-out (experimental)"
HELP_TEXT = ("EXPERIMENTAL. A receiver pushed or carried out of bounds by a defender before he gets both feet down "
             "is ruled incomplete, as in the NFL since 2008. Retail still uses the old force-out rule and credits the "
             "catch. Anniversary moments from seasons before 2008 keep the force-out rule of their time. A receiver "
             "who got both feet down in bounds before going out is still a catch.")
ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "data/nfl2k5_espn25_fields.json"
MODE, SITUATION_FLAG, MOMENT = 0xE5FF80, 0xE6014C, 0xBF1858   # game mode (8), Situation mode flag, physical row 0..50
MOMENT_COUNT = 51
HOOK = ("force_out_credit", 0x0015799B, bytes.fromhex("8b9168010000"))   # mov edx, dword ptr [ecx+0x168]
RESUME = 0x001579A1                # test edx, edx
GUARDS = (
    (0x00157930, 556, "a772b5769403856a55d93a7eebbb34c0f73cfd9b59c7096aa5cab092a549ca94"),   # boundary handler
    (0x00236700, 136, "c4999fc15714503e614d3ebebbdac7877771adcbacfda36885e2e23e9b96024e"),   # two-feet test
    (0x000B7820, 149, "a90b8531b1065c4e13df8c6178f2232d4a5fae77d0c2f8ac9dd51ca82528a9f0"),   # credit at the catch
    (0x000A0F20, 40, "6b860001619da4f4fa45b9ef42a75b1797f609c318227dffd084207a7bd21664"),    # ball attach event
    (0x00158A20, 360, "f1aab69c15d2b5078d4b1a3ae4f2b3097a3258e4eb425b6e52ce717833cee782"),   # foot-down counter
    (0x001578D0, 80, "3ff590d2041878682a205c4dc6f0d835391b9406892bd1e70172b22385c1e595"),    # foot in bounds
    (0x00157460, 80, "449b8fade9181e27c8eda7c4eea7e06482fa045c516c09dd8ad5e8ef3c6966ed"),    # field rectangle
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError)


class ForceOutError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ForceOutError(message)


def old_rule_rows(catalog=None):
    """Anniversary rows (1-based) whose season is before 2008: they keep the force-out catch."""
    doc = json.loads(CATALOG.read_text(encoding="utf-8")) if catalog is None else catalog
    moments = doc["moments"]
    require(sorted(m["row"] for m in moments) == list(range(1, MOMENT_COUNT + 1)), "moment catalog rows")
    for m in moments:
        require(type(m["season"]) is int and 1920 <= m["season"] <= 2100, f"row {m['row']}: season")
    return sorted(m["row"] for m in moments if m["season"] < MODERN_FROM_SEASON)


def row_mask(catalog=None):
    """Bit (row - 1) set for every row that keeps the force-out rule (the cave tests the 0-based physical row)."""
    return sum(1 << (r - 1) for r in old_rule_rows(catalog))


def code_for(code_va, mask=None):
    """The cave (CODE_SIZE bytes, the row mask in its last 8). Only EDX and the flags change; both are dead or
    recomputed at 0x1579A1 (test edx, edx), and ECX still holds the situation object for the second read."""
    from .nfl2k5_draft_ai import _Asm
    mask = row_mask() if mask is None else mask
    require(0 <= mask < 1 << MOMENT_COUNT, "row mask")
    a = _Asm(code_va)
    a.b(HOOK[2].hex())                                            # mov edx, [ecx+0x168]  (the retail credit)
    a.b("85d2")                                                   # test edx, edx
    a.j8("74", "resume")                                          # no credit: nothing to decide
    a.b("833d" + struct.pack("<I", MODE).hex() + "08")            # cmp dword [mode], 8
    a.j8("75", "modern")
    a.b("833d" + struct.pack("<I", SITUATION_FLAG).hex() + "00")  # cmp dword [situation], 0
    a.j8("75", "modern")
    a.b("8b15" + struct.pack("<I", MOMENT).hex())                 # mov edx, [row]
    a.b("83fa" + bytes([MOMENT_COUNT]).hex())                     # cmp edx, 51
    a.j8("73", "modern")
    a.b("0fa315" + struct.pack("<I", code_va + MASK_OFFSET).hex())  # bt [mask], edx
    a.j8("73", "modern")                                          # jnc: 2008 or later
    a.b(HOOK[2].hex())                                            # pre-2008 moment: the retail credit again
    a.j8("eb", "resume")
    a.label("modern")
    a.b("31d2")                                                   # xor edx, edx: no force-out credit
    a.label("resume")
    a.jmp_abs(RESUME)
    body = a.assemble()
    require(len(body) <= MASK_OFFSET, "force-out cave exceeds its allocation")
    return body.ljust(MASK_OFFSET, b"\xcc") + struct.pack("<Q", mask)


def sites(code_va=0):
    name, va, before = HOOK
    return [(name, va, before, (b"\xe9" + struct.pack("<i", code_va - va - 5)).ljust(len(before), b"\x90"))]


def allocation(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16),
            "Missing or foreign force-out allocation")
    return rows[0]


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocation(payload) if present else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        raw = image.read(owned["va"], CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(owned["va"]) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed force-out site/code")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign force-out prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except _ERRORS:
        return "foreign"


def read_settings(payload):
    out = {"status": status(payload)}
    if out["status"] == "applied":
        from .nfl2k5_cave_oracle import XbeImage
        mask = struct.unpack("<Q", XbeImage(payload).read(allocation(payload)["va"] + MASK_OFFSET, 8))[0]
        out["old_rule_rows"] = [i + 1 for i in range(MOMENT_COUNT) if mask >> i & 1]
    return out


def apply(payload):
    """Install, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except _ERRORS as exc:
        raise ForceOutError(f"foreign/mixed force-out input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, modern_from_season=MODERN_FROM_SEASON)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "Modern sideline catches need the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    code_va = allocation(payload)["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(code_va))
    edits = sites(code_va)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"force-out site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == "applied" and space.status(result) == "applied", "force-out postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va), old_rule_rows=old_rule_rows(),
                        before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                        allocation=allocation_receipt,
                        edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits],
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "HOOK", "GUARDS", "MODERN_FROM_SEASON", "old_rule_rows", "row_mask", "code_for",
           "sites", "allocation", "status", "read_settings", "apply"]

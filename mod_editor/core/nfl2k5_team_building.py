"""CPU team building (beta 81; lane team-building, coordinator rulings of 2026-11-25): computer clubs draft and sign to
their weakest starters, judged by the shared team-need rule (tools/common/team_need.h; Python mirror
nfl2k5_team_need), so trades, signings and the draft pull the same way.

Owner's report: "the chiefs are starting horrible wrs, teams need to make moves to stay relevant, priotize signing
their weaknesses and drafting weaknesses high especially at premium positions". Measured on stored ten-season panels: a
CPU club with a bottom-quarter WR1/WR2 still has one the next season 72 percent of the time (real NFL 55), because the
draft's need is a roster count (one fixed board for every club in round 1) and the free-agent wishes compare the best
free agent with the average of every man at the position.

What it installs (code in tools/team_building/runtime.c, built by tools/team_building/assemble.py into 29 proven
unreferenced retail functions listed in tools/team_building/dead_code.py):
- the draft: the draft AI's need call in its pick head (0x31E121, `call 0x31DEA0`) goes to tb_order, which keeps the
  retail order for a club a person runs and otherwise moves the club's holes to the front (header need seats read as
  the next depth sort will set them, the league's bottom quarter, one season of aging read in, premium positions 3:2,
  QB included; not a position the club already drafted in this draft, nor in rounds 1 and 2 one where it holds an
  unseated development asset);
- free agency: the draft AI's wish body jump (0x324414, `jmp 0x10B40`) goes to tb_wish_entry: a club a person runs
  goes on to the draft AI's own cave unchanged; QB, K, P and FB keep the draft AI's own score (ranked with the count
  deficits when short of the roster minimum, a missing K or P above the holes); every other position wishes for the
  best free agent the club can pay, weakness first, one wish a position pool.
It needs the draft AI (current head) and the franchise economy at revision 9 or later (economy_value and
economy_room_for_signing, the economy's one affordability routine, are called). No save field; no writable data.
Retail puts the retail window bytes and the draft AI's own targets back.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from . import nfl2k5_team_need as tn
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

STUDIO_LABEL = "CPU team building (needs-based draft and signings)"
# b81 integration: Build-tab captions stay at 60 characters or fewer (test_ux_build_plan_coverage_qt); the help text
# and the progress line keep the long wording (CPU clubs draft and sign to their weakest starters)
BUILD_CAPTION = "Franchise: CPU clubs draft and sign for need (experimental)"
HELP_TEXT = ("EXPERIMENTAL. Computer clubs judge each starting spot against the league: when a club's weakest starter at "
             "a position rates in the league's bottom quarter (read one season ahead for aging starters), its draft "
             "takes that position first in every round, quarterbacks included, and its free agency first bids on the "
             "best free agent it can afford who would start there. Wide receivers, tackles, edge rushers, corners, "
             "defensive tackles and quarterbacks count first. Clubs stop bidding on players who would not start for "
             "them, and a club that has just signed a starter stops bidding at that spot. Quarterback, kicker, punter "
             "and fullback signings keep the draft AI's rules. Your own club is never changed, even with CPU roster "
             "moves for your club turned on. Needs the draft AI and the 2026 franchise economy.")
HEAD_CALL_VA = 0x31E121          # draft_ai _prefix_bytes: e8 rel32 -> 0x31DEA0 (FN_NEED)
WISH_JUMP_VA = 0x324414          # draft_ai body_patch: e9 rel32 -> 0x10B40 (the wish cave)
DRAFT_NEED_VA = 0x31DEA0
DRAFT_CAVE_VA = 0x10B40
HOLE = tn.SCALE // 4
MARGIN = 3
PREMIUM_KEY = 171                # x/256: premium positions 3:2
AGE_DROP_MAX = 4


class TeamBuildingError(ValueError):
    """The team-building owner cannot be applied to this executable."""


def _code():
    from . import nfl2k5_team_building_code as code
    return code


def _windows():
    """{window: (size, retail sha256)} as tools/team_building/dead_code.py proved them (copied into the template)."""
    code = _code()
    return {va: (len(blob), code.RETAIL_SHA256[va]) for va, blob in code.WINDOWS.items()}


def _offset(payload: bytes, va: int) -> int:
    for section in _sections(payload):
        if section.virtual_address <= va < section.virtual_address + section.raw_size:
            return section.raw_offset + (va - section.virtual_address)
    raise TeamBuildingError(f"VA 0x{va:x} is in no section")


def _rel(payload: bytes, va: int, opcode: int) -> int | None:
    off = _offset(payload, va)
    if payload[off] != opcode:
        return None
    return (va + 5 + struct.unpack_from("<i", payload, off + 1)[0]) & 0xFFFFFFFF


def _branch(va: int, opcode: int, target: int) -> bytes:
    return bytes((opcode,)) + struct.pack("<i", target - (va + 5))


def entries() -> dict[str, int]:
    symbols = _code().SYMBOLS
    return {"order": symbols["tb_order"], "wish": symbols["tb_wish_entry"]}


def _retail_branch_bytes():
    """The retail executable's bytes at the two branch sites (inside the retail pick routine and the retail wish body)."""
    from . import nfl2k5_draft_ai as draft
    head = draft.RETAIL_PICK_FN[HEAD_CALL_VA - draft.PICK_FN_VA:][:5]
    body = draft.RETAIL_BODY[:5]
    return head, body


def _sites(payload: bytes):
    """(label, file offset, retail sha256 or retail bytes, ours, draft-AI bytes or None) for every byte written."""
    code, windows, e = _code(), _windows(), entries()
    head, body = _retail_branch_bytes()
    sites = []
    for va, blob in code.WINDOWS.items():
        size, digest = windows[va]
        if len(blob) != size:
            raise TeamBuildingError(f"window 0x{va:x}: template is {len(blob)} bytes, the proof {size}")
        sites.append((f"window_{va:x}", _offset(payload, va), digest, blob, None))
    sites.append(("draft_need_call", _offset(payload, HEAD_CALL_VA), head, _branch(HEAD_CALL_VA, 0xE8, e["order"]),
                  _branch(HEAD_CALL_VA, 0xE8, DRAFT_NEED_VA)))
    sites.append(("wish_jump", _offset(payload, WISH_JUMP_VA), body, _branch(WISH_JUMP_VA, 0xE9, e["wish"]),
                  _branch(WISH_JUMP_VA, 0xE9, DRAFT_CAVE_VA)))
    return sites


def _is_retail(got: bytes, pin) -> bool:
    return hashlib.sha256(got).hexdigest() == pin if isinstance(pin, str) else got == pin


def as_draft_ai(payload: bytes) -> bytes:
    """The executable with the draft AI's two retargeted branches put back (for the draft AI's own status), when this
    owner is applied; otherwise unchanged."""
    if status(payload) != "applied":
        return payload
    buf = bytearray(payload)
    for label, off, _digest, ours, theirs in _sites(payload):
        if theirs is not None:
            buf[off: off + len(theirs)] = theirs
    return bytes(buf)


def _needs(payload: bytes) -> list[str]:
    from . import nfl2k5_draft_ai as draft
    from . import nfl2k5_franchise_economy as economy
    missing = []
    if draft.status(payload) != "applied":
        missing.append("the draft AI")
    if economy.status(payload) != "applied":
        missing.append("the franchise economy")
    return missing


def status(payload: bytes) -> str:
    """retail (windows retail; branches as retail or the draft AI wrote them) | applied | foreign. 'retail' says
    nothing about the needs; needs_met() does."""
    try:
        sites = _sites(payload)
    except (TeamBuildingError, ValueError, struct.error, KeyError):
        return "foreign"
    states = set()
    for label, off, digest, ours, theirs in sites:
        got = payload[off: off + len(ours)]
        if got == ours:
            states.add("applied")
        elif _is_retail(got, digest) or (theirs is not None and got == theirs):
            states.add("retail")       # a retail window, or a branch as retail or the draft AI wrote it
        else:
            states.add("foreign")
    return states.pop() if len(states) == 1 else "foreign"


def needs_met(payload: bytes) -> bool:
    return status(payload) == "applied" or not _needs(as_draft_ai(payload))


def _write(payload: bytes, pieces) -> bytes:
    buf = bytearray(payload)
    sections = _sections(payload)
    touched = set()
    for off, data in pieces:
        buf[off: off + len(data)] = data
        touched.add(_section_for_offset(sections, off).index)
    for section in sections:
        if section.index in touched:
            d = section.header_offset + 36
            buf[d: d + 20] = section_digest(bytes(buf), section)
    return bytes(buf)


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    state = status(payload)
    if state == "applied":
        return payload, {"status": "applied", "edits": [], "changed_bytes": 0}
    if state != "retail":
        raise TeamBuildingError(f"team-building sites are {state}, not retail")
    missing = _needs(payload)
    if missing:
        raise TeamBuildingError("CPU team building needs " + " and ".join(missing))
    sites = _sites(payload)
    patched = _write(payload, [(off, ours) for _l, off, _d, ours, _t in sites])
    if status(patched) != "applied":
        raise TeamBuildingError("post-apply verification failed")
    from . import nfl2k5_draft_ai as draft
    if draft.status(patched) != "applied":
        raise TeamBuildingError("the draft AI no longer reads applied")
    used = sum(len(b.rstrip(b"\xcc")) for b in _code().WINDOWS.values())
    return patched, {"status": "applied", "edits": [{"label": l, "file_offset": f"0x{off:x}", "bytes": len(o)}
                                                   for l, off, _d, o, _t in sites],
                     "changed_bytes": sum(1 for a, b in zip(payload, patched) if a != b), "code_bytes": used,
                     "windows": len(_code().WINDOWS), "hole_percentile": HOLE / tn.SCALE, "margin": MARGIN}


def restore(payload: bytes, retail: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Retail: the windows' retail bytes (from the retail executable) and the draft AI's own branches."""
    state = status(payload)
    if state == "retail":
        return payload, {"status": "retail", "edits": []}
    if state != "applied":
        raise TeamBuildingError(f"team-building sites are {state}")
    pieces = []
    for label, off, digest, ours, theirs in _sites(payload):
        if theirs is not None:
            pieces.append((off, theirs))
        else:
            va = int(label.split("_")[1], 16)
            ro = _offset(retail, va)
            data = retail[ro: ro + len(ours)]
            if not _is_retail(data, digest):
                raise TeamBuildingError(f"retail bytes at 0x{va:x} differ from the proof's pin")
            pieces.append((off, data))
    restored = _write(payload, pieces)
    if status(restored) != "retail":
        raise TeamBuildingError("post-restore verification failed")
    return restored, {"status": "retail", "edits": [label for label, *_ in _sites(payload)]}


# ---------------------------------------------------------------------------------------------------------------
# Python oracle of tools/team_building/runtime.c, over any league reader (a memory image in tests, closing saves in
# the lane's offline draft replay). Mirrors the C function by function.

@dataclass
class Man:
    ref: int                 # pointer or index: whatever the reader uses
    pos: int
    points: int              # 0x246D80(p, 0) in whole points
    row: int
    pro: int
    present: bool


@dataclass
class View:
    weak: list = field(default_factory=lambda: [0] * 17)
    wpro: list = field(default_factory=lambda: [0] * 17)
    young: list = field(default_factory=lambda: [0] * 17)
    drafted: list = field(default_factory=lambda: [0] * 17)
    scale: list = field(default_factory=lambda: [[] for _ in range(17)])
    olb: bool = False        # some rostered man carries OLB (10): the two-pool scheme


def seats(roster: Sequence[Man]) -> list[list]:
    """Each pool's first two present men by row (ties: list order); None where a pool has fewer."""
    out = [[] for _ in range(17)]
    for m in roster:
        if m.pos >= 17 or not m.present:
            continue
        s = out[tn.POOL[m.pos]]
        if not s or m.row < s[0].row:
            s.insert(0, m)
            del s[2:]
        elif len(s) < 2 or m.row < s[1].row:
            s[1:] = [m]
    return [s + [None] * (2 - len(s)) for s in out]


def _seated(seat: Sequence, k: int, m: Man) -> bool:
    return any(seat[j] is m for j in range(k))


def bench(roster: Sequence[Man], men: list[list]) -> None:
    """tb_bench: the own club's need seats as the next depth sort will set them. In roster order, an unseated present
    man rated MARGIN or more above the weakest seat's man (an empty seat rates 0; the first of equals) takes that seat."""
    for m in roster:
        if m.pos >= 17 or not m.present:
            continue
        seat, k = men[tn.POOL[m.pos]], tn.NEED_SEATS[tn.POOL[m.pos]]
        if not k or _seated(seat, k, m):
            continue
        w, low = 0, 256
        for j in range(k):
            r = seat[j].points if seat[j] else 0
            if r < low:
                w, low = j, r
        if m.points >= low + MARGIN:
            seat[w] = m


def view(clubs: Sequence[Sequence[Man]], own: int) -> View:
    v = View()
    for i, roster in enumerate(clubs):
        men = seats(roster)
        v.olb |= any(m.pos == 10 for m in roster)
        for pool in range(17):
            for j in range(tn.NEED_SEATS[pool]):
                if len(v.scale[pool]) < 64:          # the depth-row seats; an empty seat rates 0 (header 1fbb90087)
                    v.scale[pool].append(men[pool][j].points if men[pool][j] else 0)
        if i != own:
            continue
        bench(roster, men)
        for m in roster:
            if m.pos >= 17 or not m.pro or m.pro > tn.YOUNG_YEARS:
                continue
            pool = tn.POOL[m.pos]
            if m.pro == 1:
                v.drafted[pool] = 1
            if m.present and not _seated(men[pool], tn.NEED_SEATS[pool], m) and m.points > v.young[pool]:
                v.young[pool] = m.points
        for pool in range(17):
            k = tn.NEED_SEATS[pool]
            weak, wpro = 255, 0
            for j in range(k):
                m = men[pool][j]
                r = m.points if m else 0
                if r < weak:
                    weak, wpro = r, (m.pro if m else 0)
            if k:
                v.weak[pool], v.wpro[pool] = weak, wpro
    for pool in range(17):
        v.scale[pool].sort()
    return v


def percentile(scale: Sequence[int], rating: int) -> int:
    """tb_pct: the header's mid-rank percentile in 256ths (nfl2k5_team_need.percentile, header 1fbb90087)."""
    return tn.percentile(scale, rating)


def ahead(v: View, pool: int, decline_after: Sequence[int]) -> int:
    over = v.wpro[pool] + 1
    drop = min(AGE_DROP_MAX, over - decline_after[pool]) if over > decline_after[pool] else 0
    return max(0, v.weak[pool] - drop)


def key(v: View, pool: int, rnd: int, decline_after: Sequence[int]) -> int:
    if not tn.NEED_SEATS[pool] or v.drafted[pool]:
        return 255
    pct = percentile(v.scale[pool], ahead(v, pool, decline_after))
    n = len(v.scale[pool])
    if pct >= HOLE or (rnd < 2 and v.young[pool] > (v.scale[pool][n // 2] if n else 0)):
        return 255
    return pct * PREMIUM_KEY >> 8 if tn.PREMIUM[pool] else pct


def order(retail: Sequence[int], v: View, rnd: int, decline_after: Sequence[int], *, human: bool = False) -> list[int]:
    """tb_order: the retail need order with the club's holes moved to the front."""
    if human:
        return list(retail)
    keys = [255 if p == 10 and not v.olb else key(v, tn.POOL[p], rnd, decline_after) for p in range(17)]
    out = []
    for k in range(256):
        out += [p for p in retail if keys[p] == k]
    return out


def new_score(v: View, pos: int, cand: int, deficit: int, jitter: int = 0) -> int:
    """tb_new_score (x 100); `jitter` is the game RNG's low byte (0..255)."""
    from . import nfl2k5_team_building_code as code
    pool = tn.POOL[pos]
    weak = v.weak[pool]
    pct = percentile(v.scale[pool], weak)
    up = cand >= weak + MARGIN
    if up and pct < HOLE:
        return 100000 + (HOLE - pct) * (2 + tn.PREMIUM[pool])
    if deficit > 0:
        return 50000 + 1200 * deficit
    if up:
        return (cand - weak) * code.INPUTS["value_x100"][pos] + jitter * 600 // 256
    return -1


KEPT = (0, 1, 2, 8)      # QB and the positions without need seats (K, P, FB): the draft AI's own score


def kept_score(pos: int, old: int, deficit: int, count: int) -> int:
    """tb_kept: `old` is the draft AI's score x 100 (tb_old_score). The draft AI decides whether to wish; short of the
    roster minimum the wish ranks with the count deficits, a K or P the club has none of above the holes."""
    if old <= 0 or deficit <= 0:
        return old
    return old // 16 + (200000 if pos in (1, 2) and not count else 50000 + 1200 * deficit)


def decline_after() -> list[int]:
    return list(_code().INPUTS["decline_after"])


__all__ = ["TeamBuildingError", "STUDIO_LABEL", "HEAD_CALL_VA", "WISH_JUMP_VA", "apply", "as_draft_ai", "entries",
           "needs_met", "restore", "status", "Man", "View", "seats", "bench", "view", "key", "order", "new_score",
           "kept_score", "KEPT", "percentile", "decline_after"]

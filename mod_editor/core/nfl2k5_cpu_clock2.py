"""Modern CPU clock management (b780 b-clock, job B "cpu_clock2"). EXPERIMENTAL / UNWITNESSED.

The retail CPU only manages the clock in the last 5:00 of the game and the last 2:00 of the first half: its
time-needed estimate (0x20A4D0) and urgency (0x2079B0) are zero before 5:00 of Q4 whatever the score, CPU timeouts
need 2:00 or less and the two-minute warning (0x1885F0), the play clock is run down only for a kneel, the field-goal
run-down or a field goal / punt PLAY in the last 2:00 (0x2D3360), the kneel test (0x206F10) needs the late window, so
the CPU never kneels before halftime, and overtime counts as early in every routine that asks the late window
(0x205FE0, 26 callers). This late owner adds, without editing any other owner:

* two scores down: in Q4 with up to 10:00 left a team down 9 or more gets the native estimate and urgency (so it
  hurries, uses the sideline and goes out of bounds, and the leader gets the matching negative urgency); the onside
  test keeps the native estimate, so this adds no onside kicks;
* four-minute offense: a leading CPU offense in Q4 runs the play clock down (snap with 0.8 to 2.2 s left) from 5:00
  instead of 2:00, on every PLAY;
* early defensive timeouts: a CPU defense that trails in Q4 may call its timeouts before 2:00 and before the
  two-minute warning; the native rules still decide (late window, timeout permitted, the defense needs the ball back
  with time: t < its estimate, which gives about 2:55 when down 1 to 8 and 5:00 when down 9 or more);
* end-of-half kneel: in Q2 a CPU offense on its own side (50 to 92 yards out), down 1 to 3, with 60 s or less left,
  that its native estimate does not send to score, kneels when the native kneel formula says the half runs out;
* kneel runoff: after a Take Knee PLAY by a CPU team, or by a human team that leads in Q4, in Q2 or Q4, when the downs
  left can kneel out the whole clock even if the defense uses every timeout (and no two-minute warning is still to
  come), the clock goes to 0:00 and stops, exactly as when time runs out during a play, and the native clock tick ends
  the half or the game. b780 hunt7: a human kneel in Q2, or tied or behind in Q4, keeps the native clock, because that
  team may still call its own timeout and kick (a kneel to set up the walk-off field goal ended a tied game at once);
* overtime (a separate build choice, off unless selected): overtime counts as the late window only where the end of
  the period can end the game, i.e. franchise pre/regular season (mode 7, period 5, a tie) and any non-playoff mode
  while the scores differ (modern overtime); playoffs (modes 5 and 6) play another period, so they stay native.

The CPU spike already exists in retail (0x189D10 -> 0x207310 -> the book's Spike Ball PLAY stored at
selector +0x2C by 0x204C80); its rule (no usable timeout, clock running, 15 s or less on any of downs 1 to 3, or first
down when less than half the needed time is left) matches the NFL 2022-2025 spikes, so this owner does not add a
second spike path (overtime makes the native one available there).

Everything is a pinned five-to-ten-byte hook at a retail instruction boundary, the displaced instructions are
re-executed, and the routines hooked or called are guarded by hash. One late allocation (1,152 bytes), no writable data.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_cpu_clock2_code as assembly

OWNER = "nfl2k5_cpu_clock2"
CODE_SIZE = 1152
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "Modern CPU clock management (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL. Off in Basic; on in the Advanced and Experimental presets. CPU teams manage the clock like "
    "modern NFL teams: a team down two scores (9 points or more) starts its hurry-up offense with up to 10:00 "
    "left in the fourth quarter, a leading CPU offense runs the play clock down from 5:00 (the four-minute "
    "offense), a trailing CPU defense calls its timeouts before the two-minute warning when it needs the ball "
    "back, the CPU kneels at the end of the first half when it is backed up and not trying to score, and after "
    "a CPU Take Knee, or yours while you lead in the fourth quarter, the clock runs out at once when the remaining "
    "kneels would end the half or the game anyway (your own kneel while tied or behind, or before halftime, keeps "
    "the clock running normally, so you can still call a timeout and kick). "
    "The CPU spike was already in the game and is unchanged.")
OT_CAPTION = "Modern CPU clock management in overtime (experimental)"
OT_HELP_TEXT = (
    "EXPERIMENTAL. Needs Modern CPU clock management. In overtime the CPU uses its end-of-game clock rules "
    "(hurry-up, timeouts, kneel, Hail Mary, late fourth downs) in the last 5:00 of the period when the end of "
    "overtime can decide the game: Franchise regular season (where overtime can end in a tie) and, in other "
    "modes, while one team leads. Playoff overtime keeps playing periods, so it stays as before.")

SYMBOLS = dict(late_native=0x205FE0, late_time=0x205FEF, half_time=0x205F80, margin_fn=0x205F40,
               need_fn=0x205F50, distance_fn=0x203370, permit_fn=0x207270, timer_stop=0xAF4F0,
               snap_back=0x2D341B, snap_special=0x2D33E2, snap_normal=0x2D3427, poll_back=0x18861D,
               poll_return=0x18873C, poll_take=0x188722, kneel_back=0x206F1A, lineup_back=0x189086)
# (label, site VA, retail bytes, opcode, code label). Calls replace a retail call; jumps replace whole instructions.
SITES = (
    ("estimate_window", 0x20A79B, "e840b8ffff", 0xE8, "estimate_lw"),
    ("urgency_window", 0x207A36, "e8a5e5ffff", 0xE8, "urgency_lw"),
    ("hurry_window", 0x18C0E8, "e8f39e0700", 0xE8, "hurry_lw"),
    ("onside_estimate", 0x206ED9, "e872f0ffff", 0xE8, "onside_need"),
    ("four_minute_route", 0x2D33D8, "3b7e3c74053b7e407545", 0xE9, "four_minute_route"),
    ("four_minute", 0x2D340C, "8b0d8c02e600d94110", 0xE9, "four_minute"),
    ("early_timeout", 0x188614, "d94010d81d586d4e00", 0xE9, "early_timeout"),
    ("half_kneel", 0x206F10, "83ec0c568b358002e600", 0xE9, "half_kneel"),
    ("kneel_runoff", 0x189080, "51a18002e600", 0xE9, "kneel_runoff"),
)
OT_SITE = ("overtime_window", 0x205FE0, "a1c402e600", 0xE9, "ot_window")
# Full retail routines this owner hooks, re-enters or calls (USA default.xbe), hashed with this owner's own hook
# bytes restored to retail. A foreign edit inside any of them refuses the build.
GUARDS = (
    (0x205F40, 13, "d54bba762b7c388fc96c30a8e018f448d84dc37dceb3a521af61cf475d9fe425"),
    (0x205F50, 40, "179b4e2b4ca7e06fa347e00405f9caa421da67099e275334030dc29be699928c"),
    (0x205F80, 85, "f13f49dd43be5f9600a610544ea03a4a8871df044aed2e2e23754c05804e6365"),
    (0x205FE0, 42, "268911a0ee7f1d24f67089e86f7a0a3ee0e613f7e3c5d9365dee10d5efee74df"),
    (0x203370, 72, "75bd8e37a99d691e3afc48d8ddf9d6a2cdda24bd9535cfa85b059855ef5403d2"),
    (0x207270, 158, "32fadb4ed2ba8000a97b1cd58aed7b5c5687f1e5ae7cd8240debc4ed47272c42"),
    (0x0AF3B0, 32, "4d88aa19da62c5f443446d967262395df19c14b8d3abfd4c9b7e9092af61340c"),
    (0x0AF4F0, 19, "8be70b203b7f7ce7afe2d8773f9e4ede9eb9ff7f1971a7a79d3406c45c669067"),
    (0x20A4D0, 796, "2dea9fcdc8f23beb4aa389fa23597c112e59bacbcc630c10f19733ce701b6a76"),
    (0x2079B0, 298, "478cf5496b1674e27177093d800cd301e9e6f92c5239828568aea366e1bf687f"),
    (0x20AC70, 782, "423797254be2fe507182590755569ed290c47e10ca575a5d2ca6cbf01d03fa61"),
    (0x18C0B0, 319, "d2e6adfed83043af5ddd061bdffbc289973b7d600040e5e7f69441259510935b"),
    (0x206EB0, 88, "5449e2655f1119fd2fa2a28f6da0373fc40b620ecd175499a1f4a37527b93f51"),
    (0x2D3360, 662, "f6b7088a115868411891a7b4a6ac8b15ef7b96a123c004a5e3a8d7378ec31d19"),
    (0x1885F0, 337, "ce95813721a18913552fe1f22d977c8246411ff5f99d5d26cfc3bbeb80cf9de5"),
    (0x206F10, 310, "3cf69a165b02e484e5a188308bda4c97c9b72813f5d00a7cfe1c8e9c93d04296"),
    (0x189080, 183, "d4d1e9e0ab681598615fcc851024063f628a23d1f59071316fbda1aedc0e7e2f"),
)
SETTINGS = ("overtime",)


class CpuClock2Error(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CpuClock2Error(message)


def code_for(va):
    """The owner's code at its allocated VA, padded with int3 to the reservation."""
    out = bytearray(assembly.CODE)
    symbols = dict(SYMBOLS, code=va)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, offset)[0]
        if kind == 2:
            target -= va + offset
        struct.pack_into("<I", out, offset, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, "CPU clock code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def _rows(overtime):
    return SITES + ((OT_SITE,) if overtime else ())


def sites(va, *, overtime=False):
    """(label, site VA, retail bytes, patched bytes) for an allocation at ``va``."""
    result = []
    for name, site, before, opcode, label in _rows(overtime):
        before = bytes.fromhex(before)
        after = bytes((opcode,)) + struct.pack("<i", va + assembly.LABELS[label] - site - 5)
        result.append((name, site, before, after + b"\x90" * (len(before) - 5)))
    return result


def allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) <= 1, "Duplicate CPU clock allocation")
    if rows:
        row = rows[0]
        require((row["kind"], row["size"], row["align"]) == ("code", CODE_SIZE, 16), "Foreign CPU clock allocation")
    return rows[0] if rows else None


def _guards(image):
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for _, site, before, *_ in _rows(True):
            before = bytes.fromhex(before)
            if va <= site and site + len(before) <= va + size:
                blob[site - va:site - va + len(before)] = before
        require(hashlib.sha256(blob).hexdigest() == digest, f"Foreign CPU clock prerequisite at {va:#x}")


def inspect(payload):
    """None for a retail image, {'overtime': bool} for an installed owner; raises on mixed or foreign bytes."""
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    row = allocations(payload)
    _guards(image)
    va = row["va"] if row else 0
    main = sites(va)
    ot = sites(va, overtime=True)[-1]
    states = set()
    for name, site, before, after in main:
        raw = image.read(site, len(before))
        states.add("retail" if raw == before else "applied" if row and raw == after else "foreign")
    require(len(states) == 1 and "foreign" not in states, "Mixed or foreign CPU clock hooks")
    raw = image.read(ot[1], len(ot[2]))
    overtime = raw == ot[3] and row is not None
    require(raw == ot[2] or overtime, "Foreign late-window entry 0x205FE0")
    if states == {"retail"}:
        require(not overtime, "Overtime clock hook without the CPU clock owner")
        if row:
            require(image.read(va, CODE_SIZE) == b"\xcc" * CODE_SIZE, "Foreign CPU clock code")
        return None
    require(image.read(va, CODE_SIZE) == code_for(va), "Foreign CPU clock code, relocation or padding")
    return {"overtime": overtime}


def status(payload):
    try:
        return "applied" if inspect(payload) is not None else "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def read_settings(payload):
    try:
        return inspect(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return None


def verify(payload, *, overtime=None):
    settings = inspect(payload)
    require(settings is not None, "CPU clock owner is not installed")
    if overtime is not None:
        require(settings["overtime"] == bool(overtime), "CPU clock overtime choice differs from the requested build")
    return dict(status="applied", owner=OWNER, settings=settings, experimental=True, runtime_witnessed=False)


def normalized_sites(payload):
    """This owner's installed hooks (for neighbors that hash a routine containing one); [] on retail."""
    settings = inspect(payload)
    if settings is None:
        return []
    return sites(allocations(payload)["va"], overtime=settings["overtime"])


def apply(payload, *, overtime=False):
    """Install the owner (idempotent for the same choice; a different overtime choice needs a clean base)."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    overtime = bool(overtime)
    settings = inspect(payload)
    if settings is not None:
        require(settings["overtime"] == overtime, "Different CPU clock overtime choice; rebuild from a clean base")
        return payload, dict(owner=OWNER, status="already_applied", settings=settings, changed_bytes=0, edits=[])
    before_sha = hashlib.sha256(payload).hexdigest()
    row = allocations(payload)
    if row is None:
        if space.status(payload) == "retail":
            allocated, allocation = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "CPU clock owner needs the scale-out allocator")
            allocated, allocation = space.extend_scaleout(payload, REQUESTS)
    else:
        allocated, allocation = payload, dict(status="already_allocated", allocations=[row])
    va = allocations(allocated)["va"]
    installed, _ = space.install_code(allocated, OWNER, code_for(va))
    image = XbeImage(installed)
    buf = bytearray(installed)
    edits = []
    for name, site, before, after in sites(va, overtime=overtime):
        off = image.offset(site, len(before))
        require(bytes(buf[off:off + len(before)]) == before, f"CPU clock site {site:#x} is not retail")
        buf[off:off + len(before)] = after
        edits.append(dict(label=name, va=hex(site), before=before.hex(), after=after.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(inspect(result) == {"overtime": overtime}, "CPU clock postcondition failed")
    return result, dict(owner=OWNER, status="applied", settings={"overtime": overtime},
                        changed_bytes=space.count_differing_bytes(payload, result),
                        file_growth=len(result) - len(payload), allocation=allocation, edits=edits,
                        before_sha256=before_sha, after_sha256=hashlib.sha256(result).hexdigest(),
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER] +
                        [dict(owner=OWNER, start=hex(e[1]), end=hex(e[1] + len(e[2])), size=len(e[2]),
                              basis="pinned live rule hook; not a cave") for e in sites(va, overtime=overtime)],
                        experimental=True, runtime_witnessed=False)


def main(argv=None):
    """``status XBE`` or ``apply XBE --output OUT [--overtime]`` (offline; never touches a disc)."""
    import argparse
    import json
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Modern CPU clock management (EXPERIMENTAL / UNWITNESSED)")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("status")
    show.add_argument("xbe", type=Path)
    make = sub.add_parser("apply")
    make.add_argument("xbe", type=Path)
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--overtime", action="store_true")
    args = parser.parse_args(argv)
    payload = args.xbe.read_bytes()
    if args.command == "status":
        print(json.dumps({"status": status(payload), "settings": read_settings(payload)}))
        return 0
    result, receipt = apply(payload, overtime=args.overtime)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(result)
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("reservations",)}, default=str))
    return 0


__all__ = ["OWNER", "CODE_SIZE", "REQUESTS", "BUILD_CAPTION", "HELP_TEXT", "OT_CAPTION", "OT_HELP_TEXT", "SYMBOLS",
           "SITES", "OT_SITE", "GUARDS", "CpuClock2Error", "code_for", "sites", "allocations", "inspect", "status",
           "read_settings", "verify", "normalized_sites", "apply", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

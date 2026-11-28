"""Booth lines for the 2026 calendar: the franchise Super Bowl and Berman's sign-offs (beta 81, job sb-booth).
EXPERIMENTAL; the Super Bowl welcome and coin toss are witnessed, the sign-offs are not (see below).

The owner, testing a beta 81 disc after simming a new franchise's first season to the Super Bowl on the 2026 calendar:
"why is the super bowl in jacksonville lmao", then "nevermind it is in sofi, commetary just said jascksonville". The
game is played at SoFi (row s40 carries the SoFi model); only the booth named Jacksonville.

How the booth picks its Super Bowl lines (static RE, job sb-venue; the retail and built-disc bytes were compared)
---------------------------------------------------------------------------------------------------------------
* The booth says a recorded sentence by its 16-bit phrase key: a director instruction ``9F <key, big-endian>``
  (handler 0x59010 -> 0x582F0, the booth queue 0xB28A70) resolves the key through the ``lines`` SPCI table (outer 3)
  with FUN_0013CBA0 to one ``lines.bin`` stream. The city and the Super Bowl number are spoken inside the recording.
* The in-game director (DRCT, outer 4) event 113 is the booth intro. Its Super Bowl children are chosen by the
  franchise season index (global variable 277 -> 0x260A80 -> 0xC4EB0, the index FUN_001332B0 also uses for the
  venue) and say, for seasons 0 to 3, the retail welcomes of Super Bowls XXXIX to XLII:

  ====  =====  ======  ===========================================================================================
  key   lines  child   recording (transcribed)
  ====  =====  ======  ===========================================================================================
  14047 1479   13      "... Welcome to ESPN's coverage of Super Bowl 39 here in Jacksonville, Florida."
  14048 1480   29      "... welcome to the Motor City, Detroit, home of Super Bowl 40 here on ESPN."
  14049 1481   30      "Hello, and welcome to ESPN's broadcast of Super Bowl 41 here in Miami, Florida ..."
  14050 1482   31      "Greetings from Tempe, Arizona, home of Super Bowl 42, here on ESPN ..."
  ====  =====  ======  ===========================================================================================

  and the coin-toss lead-ins (children 28, 23, 26) "Super Bowl 39 / 40 / 41 about to get underway" (keys 2956, 2957,
  2958; lines 1048 to 1050). The pregame director (outer 1194) event 113 holds the same four welcomes (children 72, 73,
  75, 74) and the halftime/postgame director (outer 1195) event 131 Chris Berman's sign-offs "That wraps up our
  production of Super Bowl 39 / 40 / 41" (children 72, 75, 76; keys 39811 to 39813; lines 2737 to 2739).
* On the 2026 calendar the franchise's first Super Bowl is LXI (SoFi Stadium, Inglewood), then LXII to LXIV, so every
  one of those lines names the wrong game and three of the welcomes the wrong city. The game recorded no line for
  any later Super Bowl.

Berman's postgame sign-offs (stale-line audit, revision 2)
---------------------------------------------------------
The halftime/postgame director (outer 1195) event 131 also ends ordinary broadcasts with ESPN's 2004 anniversary:
child 67 (key 39795, regular season, both takes: "...celebrating 25 years as the worldwide leader in sports", "...for
25 years and counting"), child 65 (key 39797, preseason, both takes) and children 68/69 (key 39799, AFC wild card). The
same event already holds the recorded generic sign-offs: child 64 (key 39796, three takes, "Thanks for watching the
NFL on ESPN, the worldwide leader in sports...") and child 66 (key 39798, two takes, the preseason). Revision 2 points
39795 at 39796 and 39797 at 39798 (4 more bytes in outer 1195). Revision 3 (review N1) points 39799 at key 39800, lines
2731, the same AFC wild-card sign-off without the anniversary: "That concludes this AFC wildcard game. Thanks so much
for watching the NFL and ESPN, the worldwide leader in sports. I'm Chris Berman ... a great New Year." (no director
site says 39800 in retail). A disc with revision 1 or 2 upgrades in place: each site may hold its retail key, an
earlier revision's key or the current one, and the entry with every site at the current key must be the pinned one.

Other byte matches in the in-game director (not changed, not gated): outer 4 also holds the big-endian values of 2956,
2957, 2958, 39811 and 39813 after bytes other than 0x9F (0x00, 0x01, 0x4D; for example body +0x13C4C, +0x189D8 and
+0x46D13 to +0x4756C). They are not operands of the say instruction this owner edits; what they are is not traced, and
no witness heard those lines outside the sites below.

What this owner does
--------------------
Each of those say operands is pointed at the retail line the game already recorded for the same moment without a
city or a number: key 14051, lines 1483 "Hi there, I'm Dan Stevens and welcome to the Super Bowl here on ESPN"
(the line the Anniversary moments' welcome, nfl2k5_moment_booth, also uses); key 2959, lines 1051 "And the Super Bowl
is about to get underway. Let's go to the coin toss"; key 39815, lines 2740 "That does it for our coverage of the
Super Bowl on ESPN ...", and the anniversary sign-offs at the generic ones above. 18 bytes (the low byte of each key)
in three director entries that the disc stores uncompressed; every entry keeps its size, the executable, the speech tables and the audio are untouched, and no
other director data changes. The Anniversary moments never run event 113 (0x67E80 skips it in game mode 8), so
they are not affected. Saves do not hold director data: an existing franchise hears the new lines at its next
Super Bowl. The build runs this with the 2026 season (``season_2026``); on the retail 2004 calendar the retail lines
are right and stay.

Witnessed (xemu, 2026-11-25, revision 1): Super Bowls on a 2029 save at season index 0 (written before play) and 3
(natural) said 14051, 2950-2953/2955 and 2959, never a numbered or city line; venues s40 (SoFi) and h41 (Nissan).
The sign-offs (revisions 1 to 3) are unwitnessed: no witness reached the end of a broadcast.

The user's own recordings: a site whose retail line the user replaced through the commentary replacement
(``keep_streams``, lines streams) keeps (or gets back) its retail key, so the user's recording is still said; the
release gate then ignores that key.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Callable

OWNER = "nfl2k5_super_bowl_booth"
SCHEMA = "nfl2k5_super_bowl_booth/v1"
LABEL = "EXPERIMENTAL / SIGN-OFFS UNWITNESSED"
#: what a witness saw (sb3, sb4: the Super Bowl welcome and coin toss); the sign-offs were never reached
WITNESSED = {"super_bowl_welcome": True, "super_bowl_coin_toss": True, "sign_offs": False}
WRAPPER = 0x20          # resource wrapper before the DRCT body inside each outer entry
SAY = 0x9F              # the director's say instruction; the key follows big-endian
WELCOME, COIN_TOSS, SIGN_OFF = 14051, 2959, 39815
SIGN_OFF_GAME, SIGN_OFF_PRESEASON, SIGN_OFF_AFC_WILD_CARD = 39796, 39798, 39800
#: the generic lines this owner points at -> their lines.bin streams (39796 and 39798 have several takes)
GENERIC_LINES = {WELCOME: (1483,), COIN_TOSS: (1051,), SIGN_OFF: (2740,), SIGN_OFF_GAME: (9440, 9441, 9442),
                 SIGN_OFF_PRESEASON: (9445, 9446), SIGN_OFF_AFC_WILD_CARD: (2731,)}
#: the retail keys this owner moves -> their lines.bin streams (what a user's commentary replacement would replace)
RETAIL_STREAMS = {14047: (1479,), 14048: (1480,), 14049: (1481,), 14050: (1482,), 2956: (1048,), 2957: (1049,),
                  2958: (1050,), 39811: (2737,), 39812: (2738,), 39813: (2739,), 39795: (9438, 9439),
                  39797: (9443, 9444), 39799: (2730,)}


@dataclass(frozen=True)
class Site:
    outer: int          # outer archive entry (DRCT)
    body_offset: int    # offset of the 0x9F byte inside the DRCT body
    event: int          # director fixed slot
    child: int          # the event's child (decision-tree leaf)
    retail: int         # retail phrase key
    generic: int        # the key this owner writes
    line: int           # first retail lines.bin stream of the retail key
    revision: int = 1   # 1: the Super Bowl lines (40c10fb79); 2: the anniversary sign-offs; 3: 39799 -> 39800
    earlier: tuple[int, ...] = ()   # keys an earlier revision wrote at this site


SITES = (
    Site(4, 0x417D2, 113, 13, 14047, WELCOME, 1479),
    Site(4, 0x419AE, 113, 29, 14048, WELCOME, 1480),
    Site(4, 0x419DA, 113, 30, 14049, WELCOME, 1481),
    Site(4, 0x41A06, 113, 31, 14050, WELCOME, 1482),
    Site(4, 0x41988, 113, 28, 2956, COIN_TOSS, 1048),
    Site(4, 0x4190C, 113, 23, 2957, COIN_TOSS, 1049),
    Site(4, 0x41960, 113, 26, 2958, COIN_TOSS, 1050),
    Site(1194, 0x829A, 113, 72, 14047, WELCOME, 1479),
    Site(1194, 0x82C2, 113, 73, 14048, WELCOME, 1480),
    Site(1194, 0x8312, 113, 75, 14049, WELCOME, 1481),
    Site(1194, 0x82EA, 113, 74, 14050, WELCOME, 1482),
    Site(1195, 0x30D0, 131, 72, 39811, SIGN_OFF, 2737),
    Site(1195, 0x310C, 131, 75, 39812, SIGN_OFF, 2738),
    Site(1195, 0x3120, 131, 76, 39813, SIGN_OFF, 2739),
    Site(1195, 0x306C, 131, 67, 39795, SIGN_OFF_GAME, 9438, 2),
    Site(1195, 0x3044, 131, 65, 39797, SIGN_OFF_PRESEASON, 9443, 2),
    Site(1195, 0x3080, 131, 68, 39799, SIGN_OFF_AFC_WILD_CARD, 2730, 3, (SIGN_OFF_GAME,)),
    Site(1195, 0x3094, 131, 69, 39799, SIGN_OFF_AFC_WILD_CARD, 2730, 3, (SIGN_OFF_GAME,)),
)
#: the retail keys that name Super Bowls XXXIX to XLII (and, for the welcomes, their cities) or ESPN's 2004 anniversary
STALE_KEYS = frozenset(site.retail for site in SITES)
OUTERS = (4, 1194, 1195)
ROLES = {4: "in-game director", 1194: "pregame director", 1195: "halftime and postgame director"}
#: outer entry size and SHA-256 of the whole entry (wrapper + body), retail and with this owner applied
ENTRY_PINS = {
    4: {"size": 505_600,
        "retail": "dd3e4bc323f8e3b2a80292e2cf0129c2ad84cc891149fe8bc8ee64a4b229306d",
        "applied": "5d9e2374e0b763e609ed377e29d96aa90755d9cd245b1becf8d1480a27942d51"},
    1194: {"size": 73_712,
           "retail": "7d3de460e8d98d9cce9fc38a80badd2cf9314dd57a11137d7dc9681c9888c60d",
           "applied": "de1fc5e361ada65c585e0c2b095a786e521c8d6a786beb78efd422a8543a041e"},
    1195: {"size": 29_200,
           "retail": "644f445868afa7e75d3c50ed055bb2506ea4c909886d683a439b668395f70494",
           "applied": "f8333979822974e4a52bbd074f7221afc4e73826b858cf38494bf1800300b49d",
           # revision 1 (40c10fb79): the three Super Bowl sign-offs only; revision 2 (298c1fb22): 39799 -> 39796
           "previous": ("4913b9d9ad33cf4a37261702b94ecb871e244fcc136b1f2822eb79338be405d2",
                        "a2057f6807b5ed177bd1f0284c050ee6c0f6e2aa35b4c3b73fcbbde409b2c56e")},
}
UI_TEXT = ("EXPERIMENTAL. With the 2026 season: franchise Super Bowls get the booth's own Super Bowl welcome, coin toss "
           "and sign-off without a city or a number, instead of the retail lines for Super Bowls XXXIX to XLII in "
           "Jacksonville, Detroit, Miami and Tempe, and Berman's sign-offs no longer celebrate ESPN's 25th year.")


class SuperBowlBoothError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SuperBowlBoothError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def sites_for(outer: int) -> tuple[Site, ...]:
    return tuple(site for site in SITES if site.outer == outer)


def _key_at(entry: bytes, site: Site) -> int | None:
    at = WRAPPER + site.body_offset
    if len(entry) < at + 3 or entry[at] != SAY:
        return None
    return int.from_bytes(entry[at + 1:at + 3], "big")


def _canonical(outer: int, entry: bytes) -> bytes | None:
    """The entry with every site at this revision's key, or None when a site holds a key this owner never wrote."""
    out = bytearray(entry)
    for site in sites_for(outer):
        key = _key_at(out, site)
        if key not in (site.retail, site.generic, *site.earlier):
            return None
        at = WRAPPER + site.body_offset + 1
        out[at:at + 2] = site.generic.to_bytes(2, "big")
    return bytes(out)


def entry_state(outer: int, entry: bytes) -> str:
    """retail / previous / applied / partial / foreign for one director entry (pinned by its whole-entry SHA-256).

    ``partial``: this owner's entry with some sites at their retail key (the user's own recordings) or at an earlier
    revision's key; with every site at the current key it is the pinned applied entry."""
    pins = ENTRY_PINS[outer]
    if len(entry) != pins["size"] or entry[:4] != b"DRCT":
        return "foreign"
    digest = sha(entry)
    if digest == pins["retail"]:
        return "retail"
    if digest == pins["applied"]:
        return "applied"
    if digest in pins.get("previous", ()):
        return "previous"
    canonical = _canonical(outer, entry)
    return "partial" if canonical is not None and sha(canonical) == pins["applied"] else "foreign"


def kept_keys(keep_streams: Any = ()) -> frozenset[int]:
    """The retail keys whose recording the user replaced (``keep_streams``: lines streams); their sites stay retail."""
    keep = frozenset(keep_streams)
    return frozenset(key for key, streams in RETAIL_STREAMS.items() if keep & set(streams))


def patch_entry(outer: int, entry: bytes, keep: frozenset[int] = frozenset()) -> tuple[bytes, dict[str, Any]]:
    """The entry with its say operands retargeted (the sites of a ``keep`` key at their retail key). Retail, previous,
    partial or applied; an entry already in that shape is returned unchanged."""
    state = entry_state(outer, entry)
    require(state != "foreign",
            f"outer entry {outer} ({ROLES[outer]}) is not the pinned retail, previous or applied director; refusing")
    out = bytearray(entry)
    pending = 0
    for site in sites_for(outer):
        want = site.retail if site.retail in keep else site.generic
        at = WRAPPER + site.body_offset + 1
        if _key_at(out, site) != want:
            out[at:at + 2] = want.to_bytes(2, "big")
            pending += 1
    result = bytes(out)
    canonical = _canonical(outer, result)
    require(canonical is not None and sha(canonical) == ENTRY_PINS[outer]["applied"],
            f"outer entry {outer}: the patched director is not the pinned one")
    changed = [i for i, (a, b) in enumerate(zip(entry, result)) if a != b]
    require(len(changed) <= pending, f"outer entry {outer}: {len(changed)} bytes changed for {pending} sites")
    kept = sorted({site.retail for site in sites_for(outer) if site.retail in keep})
    receipt = {"outer": outer, "state": entry_state(outer, result), "from": state, "already_applied": not changed,
               "changed_bytes": len(changed), "kept_for_user_recordings": kept}
    if changed:
        receipt.update({"entry_offsets": [f"0x{i:X}" for i in changed], "before_sha256": sha(entry),
                        "after_sha256": sha(result)})
    return result, receipt


def stale_lines(outer: int, entry: bytes, keep: frozenset[int] = frozenset()) -> list[dict[str, Any]]:
    """Every ``9F <key>`` in the entry whose key is one of the retail stale lines (the release gate), except the keys
    the user's own recordings keep.

    A whole-entry byte scan, wider than the site table: on the retail directors it finds exactly the 18 sites."""
    hits = []
    for key in sorted(STALE_KEYS - keep):
        needle = bytes([SAY]) + key.to_bytes(2, "big")
        at = entry.find(needle)
        while at != -1:
            hits.append({"outer": outer, "body_offset": f"0x{at - WRAPPER:X}", "key": key})
            at = entry.find(needle, at + 1)
    return hits


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


def _entry(archive: Any, outer: int) -> Any:
    entries = archive.entries
    require(len(entries) > outer, f"the archive has no outer entry {outer}")
    entry = entries[outer]
    require(entry.size == ENTRY_PINS[outer]["size"],
            f"outer entry {outer} is 0x{entry.size:X} bytes, not the {ROLES[outer]}")
    return entry


def read_entries(path: Path | str) -> dict[int, bytes]:
    """The three director entries of a disc image or a loose pack folder (read-only)."""
    with _outer_image()(path) as archive:
        return {outer: archive.read(_entry(archive, outer).virtual_offset, _entry(archive, outer).size)
                for outer in OUTERS}


def image_state(path: Path | str) -> str:
    """retail / previous / applied / partial / mixed / foreign for a disc image or a loose pack folder."""
    try:
        states = {entry_state(outer, raw) for outer, raw in read_entries(path).items()}
    except (OSError, ValueError, KeyError, IndexError):
        return "foreign"
    if "foreign" in states:
        return "foreign"
    if "partial" in states and states <= {"partial", "applied"}:
        return "partial"                                  # applied, with the user's own lines kept
    return states.pop() if len(states) == 1 else "mixed"


def check_image(path: Path | str, keep_streams: Any = ()) -> list[dict[str, Any]]:
    """Release gate: the stale say operands left in the three directors (empty = pass); ``keep_streams`` as in
    apply_to_image."""
    keep = kept_keys(keep_streams)
    hits: list[dict[str, Any]] = []
    for outer, raw in read_entries(path).items():
        hits.extend(stale_lines(outer, raw, keep))
    return hits


def apply_to_image(path: Path | str, *, keep_streams: Any = (),
                   progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Retarget the 18 say operands on a built COPY (in place, read back). Idempotent; upgrades revisions 1 and 2 in
    place; leaves the sites of a line the user replaced (``keep_streams``) at their retail key; refuses foreign
    directors (and then writes nothing)."""
    say = progress or (lambda _m: None)
    keep = kept_keys(keep_streams)
    entries: list[dict[str, Any]] = []
    with _outer_image()(path, writable=True) as archive:
        plans = []
        for outer in OUTERS:
            entry = _entry(archive, outer)
            before = archive.read(entry.virtual_offset, entry.size)
            after, receipt = patch_entry(outer, before, keep)
            plans.append((entry, before, after, receipt))
        for entry, before, after, receipt in plans:
            if not receipt["already_applied"]:
                say(f"Booth lines: {ROLES[receipt['outer']]} ({receipt['changed_bytes']} bytes)")
                for site in sites_for(receipt["outer"]):
                    at = WRAPPER + site.body_offset + 1
                    if before[at:at + 2] == after[at:at + 2]:
                        continue
                    require(archive.write(entry.virtual_offset + at, after[at:at + 2]) == 2,
                            f"short write in outer entry {receipt['outer']}")
                readback = archive.read(entry.virtual_offset, entry.size)
                require(readback == after, f"outer entry {receipt['outer']}: read-back differs")
            entries.append(receipt)
    left = check_image(path, keep_streams)
    require(not left, f"stale booth lines left after the write: {left}")
    return {"owner": OWNER, "schema": SCHEMA, "label": LABEL, "state": "applied", "runtime_witnessed": dict(WITNESSED),
            "changed_bytes": sum(item["changed_bytes"] for item in entries), "entries": entries,
            "kept_for_user_recordings": sorted(keep),
            "generic_lines": {str(key): list(lines) for key, lines in GENERIC_LINES.items()}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Booth lines for the 2026 calendar (Super Bowl, Berman sign-offs).")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("status", "retail / previous / applied / partial / mixed / foreign"),
                       ("check", "release gate: exit 1 when a stale Super Bowl or sign-off line is still said")):
        command = sub.add_parser(name, help=text)
        command.add_argument("image", type=Path, help="disc image or loose vc_53450030 folder (read only)")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_state(args.image))
        return 0
    hits = check_image(args.image)
    print(json.dumps({"owner": OWNER, "image": str(args.image), "pass": not hits, "hits": hits}, indent=1))
    return 0 if not hits else 1


if __name__ == "__main__":
    sys.exit(main())

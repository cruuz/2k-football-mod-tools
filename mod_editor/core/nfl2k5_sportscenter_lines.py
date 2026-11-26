"""SportsCenter's playoff picture, sign-off and Primetime Players lines for the 2026 calendar (b81 sportscenter).
EXPERIMENTAL / UNWITNESSED.

How the weekly show picks these lines (static reading of the USA executable and the disc's dir_wrapup.iff, outer
19): each SportsCenter segment fires one event of the wrapup director; an event's
children are its alternative lines and a decision tree picks among them. The tree (read by FUN_00269750) is a list of
rules, each testing one director variable against byte constants. Three rules key on the number of weeks played
(director variable 65, 0x15E8D0 = last played week + 1) with the retail 17-week season in their constants:

* Playoff picture (event 182, rule 2): 17 weeks played = the final picture, 16 = the late picture (the #1 seed's
  "home field throughout ... rest on Wild Card weekend"), 15 = the end of the mid-season pictures. On the 18-week
  calendar the final picture's lines ("the regular season now in the books", the seed-by-seed summary) played after
  Week 17 with a week still to go, and after Week 18 none of them could play.
* Show sign-off (event 165, rule 2): 18 = "we'll see you for the division championships", 19 = the conference
  championships, 20 = the Super Bowl, 21 = next season. On the 18-week calendar each named the round one week early
  (after Week 18 Chris Berman sent viewers to the division championships).
* Berman's Primetime Players (event 170, rule 1) named weeks and rounds the same 17-week way: "two weeks to go now"
  after Week 15, "And then there were 12 ... the final game of the regular season" after Week 17, "this special
  wildcard edition" after Week 18, "as the field narrows to four" after the wild card round and "today's conference
  championships" after the divisional round. Its compares 15, 18, 16, 19, 20 become 16, 19, 19, 20, 21 (coordinator's
  ruling, 11/25): "two weeks to go now" after Week 16, the wildcard / final four / conference lines after the wild card,
  divisional and conference rounds, and only the generic game-ball line (always a candidate) after Weeks 15, 17 and 18.
  "Pivotal Week 16" and "And then there were 12" no longer play ("Pivotal Week 14" and the early-season lines stay).

And the final picture's seed lines (event 182, rule 5, by the spotlighted team's spot) were recorded for the six-seed
field. The spotlight (FUN_00220AE0, unchanged by the mod) picks spot = rand % 7 + 1 from each conference's eight-team
buffer (FUN_00220960: four division winners, then the four best other clubs, both sorted), so spots 1..7 are picked
and spot 8 never is. Spot 2 says 3277 "They'll be the two seed, which means they'll get to take a week off before
they return to host a game in the divisional round", and spot 7 (retail's first team out) says 3284 "...by virtue of
a tiebreak, on the outside looking in". In the seven-seed field only the #1 seed has a bye and spot 7 is the seventh
SEED, so both lines are false, and no recorded line fits either club (none names a seven seed or a 2-v-7 game; the
division-champion lines are chosen by a different rule). The director then picks no line for that club: its card
stays up for the spotlight's minimum time (FUN_00220B30, 5.0 s at 0x4E63A8) without narration. Spots 1, 3, 4, 5 and 6
keep their lines (#1: home field throughout; the 3 seed hosts the 6; the 4 meets the 5; the 5 goes to the 4; the 6 is
"the second wild card club or the number six seed"), all true in the seven-seed field. The late picture's 2-seed bye
line (3247, classifier case 1) cannot play on a seven-seed disc: nfl2k5_playoff_picture's recap_obsolete_bye_script
(0x221001) already removed the classifier's bye cases.

What this owner changes: 16 bytes of the wrapup director (an uncompressed outer entry of fixed size; nothing moves):
  * event 182 rule 2: the week constants 17, 15, 16, 16 become 18, 16, 17, 17;
  * event 182 rule 5: the spot-2 leaf (pick child 43, line 3277) becomes the end-of-rule byte 0xFF twice; the spot-7
    compare becomes 8 (the spotlight selector 0x220AE0 never picks spot 8 in the seven-seed field);
  * event 165 rule 2: the week constants 19, 18, 20, 21 become 20, 19, 21, 22;
  * event 170 rule 1: the week constants 15, 18, 16, 19, 20 become 16, 19, 19, 20, 21.
The whole entry is pinned by SHA-256 (retail and applied); anything else is refused and nothing is written. Saves hold
no director data, so an existing franchise hears the new choices at its next show. The build runs it with the 2026
season, after the season patch, and only when the executable has both 18 regular weeks and the fourteen-team bracket
(``wanted``); on the retail calendar the retail lines are right and stay. The Studio's executable-only update cannot
carry it (it is disc data): it lands with a rebuild.

Not changed (LATER, coordinator 11/25): the final picture's outro key 51655 has two takes, one of them "Time to see
which of these 12 teams will emerge as Super Bowl champs" (11431); a take count lives in the shared speech index
(outer 3), which this owner does not touch.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Callable

OWNER = "nfl2k5_sportscenter_lines"
SCHEMA = "nfl2k5_sportscenter_lines/v1"
LABEL = "EXPERIMENTAL / UNWITNESSED"
OUTER = 19                 # dir_wrapup.iff, the SportsCenter (franchise show) director
WRAPPER = 0x20             # resource wrapper before the DRCT body inside the outer entry


@dataclass(frozen=True)
class Site:
    label: str
    body_offset: int       # offset inside the DRCT body
    event: int             # director fixed slot (event number)
    rule: int              # rule of the event's tree
    retail: bytes
    applied: bytes


SITES = (
    Site("picture_final_week", 0x53B3, 182, 2, bytes([17]), bytes([18])),
    Site("picture_mid_last_week", 0x53BD, 182, 2, bytes([15]), bytes([16])),
    Site("picture_late_week_le", 0x53C8, 182, 2, bytes([16]), bytes([17])),
    Site("picture_late_week_eq", 0x53CE, 182, 2, bytes([16]), bytes([17])),
    Site("picture_final_spot2_bye_line", 0x5461, 182, 5, bytes([0x80, 0x2B]), bytes([0xFF, 0xFF])),
    Site("picture_final_spot7_outside_line", 0x547A, 182, 5, bytes([7]), bytes([8])),
    Site("signoff_division_round", 0x30E6, 165, 2, bytes([18]), bytes([19])),
    Site("signoff_conference_round", 0x30E2, 165, 2, bytes([19]), bytes([20])),
    Site("signoff_super_bowl", 0x30EC, 165, 2, bytes([20]), bytes([21])),
    Site("signoff_next_season", 0x30F1, 165, 2, bytes([21]), bytes([22])),
    Site("primetime_two_weeks_to_go", 0x323A, 170, 1, bytes([15]), bytes([16])),
    Site("primetime_wildcard_edition", 0x3253, 170, 1, bytes([18]), bytes([19])),
    Site("primetime_week16_and_then_there_were_12", 0x3257, 170, 1, bytes([16]), bytes([19])),
    Site("primetime_field_narrows_to_four", 0x3262, 170, 1, bytes([19]), bytes([20])),
    Site("primetime_conference_championships", 0x3267, 170, 1, bytes([20]), bytes([21])),
)
CHANGED_BYTES = sum(len(site.retail) for site in SITES)
#: outer entry size and SHA-256 of the whole entry (wrapper + body), retail and with this owner applied
ENTRY_PINS = {"size": 36_192,
              "retail": "860ac6bd6760179a78ae3f533d96fa5ded6c7acb2c60bbe12c91586929e55263",
              "applied": "3dbf6c7ad35d63c7d6c1c00ba97a50379fb0b90cbbedb6914a735d742b298fdf"}
UI_TEXT = ("EXPERIMENTAL / UNWITNESSED. With the 2026 season: SportsCenter's playoff picture, sign-off and Primetime "
           "Players follow the 18-week calendar, and the final picture says nothing false about the 2 and 7 seeds.")


class SportsCenterLinesError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise SportsCenterLinesError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def _sites_state(entry: bytes) -> str:
    states = set()
    for site in SITES:
        at = WRAPPER + site.body_offset
        raw = bytes(entry[at:at + len(site.retail)])
        states.add("retail" if raw == site.retail else "applied" if raw == site.applied else "foreign")
    return states.pop() if len(states) == 1 else "foreign"


def _apply_sites(entry: bytes) -> bytes:
    out = bytearray(entry)
    for site in SITES:
        at = WRAPPER + site.body_offset
        out[at:at + len(site.applied)] = site.applied
    return bytes(out)


def entry_state(entry: bytes) -> str:
    """retail / applied / foreign for the wrapup director entry (pinned by its whole-entry SHA-256)."""
    if len(entry) != ENTRY_PINS["size"] or entry[:4] != b"DRCT":
        return "foreign"
    digest = sha(entry)
    if digest == ENTRY_PINS["retail"]:
        return "retail"
    if digest == ENTRY_PINS["applied"]:
        return "applied"
    return "foreign"


def patch_entry(entry: bytes) -> tuple[bytes, dict[str, Any]]:
    """The entry with this owner's bytes. Retail only; an applied entry is returned unchanged."""
    state = entry_state(entry)
    if state == "applied":
        return bytes(entry), {"outer": OUTER, "state": "applied", "already_applied": True, "changed_bytes": 0}
    require(state == "retail", f"outer entry {OUTER} (the SportsCenter director) is not the pinned retail or applied "
                               "director; refusing")
    require(_sites_state(entry) == "retail", "the SportsCenter director's sites are not retail")
    result = _apply_sites(entry)
    require(entry_state(result) == "applied", "the patched SportsCenter director is not the pinned one")
    changed = [i for i, (a, b) in enumerate(zip(entry, result)) if a != b]
    require(len(changed) == CHANGED_BYTES, f"{len(changed)} bytes changed")
    return result, {"outer": OUTER, "state": "applied", "already_applied": False, "changed_bytes": len(changed),
                    "sites": [{"label": s.label, "event": s.event, "rule": s.rule,
                               "body_offset": f"0x{s.body_offset:X}", "retail": s.retail.hex(),
                               "applied": s.applied.hex()} for s in SITES],
                    "before_sha256": sha(entry), "after_sha256": sha(result)}


def wanted(xbe: bytes) -> bool:
    """True when the executable plays the 2026 calendar these bytes assume: 18 regular weeks and seven seeds."""
    from . import nfl2k5_playoff_picture as picture
    from . import nfl2k5_season_length as season
    try:
        return picture.season_weeks(xbe) == 18 and season.group_status(xbe, "playoffs_14") == "applied"
    except (ValueError, KeyError, IndexError, struct.error):
        return False


def _outer_image():
    from . import nfl2k5_roster_records as rr
    return rr._outer_image()


def _entry(archive: Any) -> Any:
    entries = archive.entries
    require(len(entries) > OUTER, f"the archive has no outer entry {OUTER}")
    entry = entries[OUTER]
    require(entry.size == ENTRY_PINS["size"],
            f"outer entry {OUTER} is 0x{entry.size:X} bytes, not the SportsCenter director")
    return entry


def read_entry(path: Path | str) -> bytes:
    """The wrapup director entry of a disc image or a loose pack folder (read-only)."""
    with _outer_image()(path) as archive:
        entry = _entry(archive)
        return archive.read(entry.virtual_offset, entry.size)


def image_state(path: Path | str) -> str:
    """retail / applied / foreign for a disc image or a loose pack folder."""
    try:
        return entry_state(read_entry(path))
    except (OSError, ValueError, KeyError, IndexError):
        return "foreign"


def check_image(path: Path | str) -> list[dict[str, Any]]:
    """Release gate for a 2026-calendar disc: the sites still holding retail (17-week, six-seed) bytes; empty = pass."""
    entry = read_entry(path)
    left = []
    for site in SITES:
        at = WRAPPER + site.body_offset
        if bytes(entry[at:at + len(site.retail)]) != site.applied:
            left.append({"label": site.label, "event": site.event, "body_offset": f"0x{site.body_offset:X}",
                         "found": bytes(entry[at:at + len(site.retail)]).hex()})
    return left


def apply_to_image(path: Path | str, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Write this owner's bytes on a built COPY (in place, read back). Idempotent; refuses a foreign director."""
    say = progress or (lambda _m: None)
    with _outer_image()(path, writable=True) as archive:
        entry = _entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        after, receipt = patch_entry(before)
        if not receipt["already_applied"]:
            say("SportsCenter playoff picture, sign-off and Primetime Players lines "
                f"({receipt['changed_bytes']} bytes)")
            for site in SITES:
                at = WRAPPER + site.body_offset
                require(archive.write(entry.virtual_offset + at, after[at:at + len(site.applied)]) == len(site.applied),
                        f"short write in outer entry {OUTER}")
            readback = archive.read(entry.virtual_offset, entry.size)
            require(readback == after, f"outer entry {OUTER}: read-back differs")
    left = check_image(path)
    require(not left, f"17-week or six-seed SportsCenter lines left after the write: {left}")
    return {"owner": OWNER, "schema": SCHEMA, "label": LABEL, "state": "applied", "runtime_witnessed": False,
            "changed_bytes": receipt["changed_bytes"], "entry": receipt}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SportsCenter playoff picture and sign-off lines (2026 calendar).")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("status", "retail / applied / foreign"),
                       ("check", "release gate: exit 1 when a 17-week or six-seed site is left")):
        command = sub.add_parser(name, help=text)
        command.add_argument("image", type=Path)
    args = parser.parse_args(argv)
    if args.command == "status":
        print(image_state(args.image))
        return 0
    left = check_image(args.image)
    print(json.dumps({"image": str(args.image), "pass": not left, "left": left}, indent=1))
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())

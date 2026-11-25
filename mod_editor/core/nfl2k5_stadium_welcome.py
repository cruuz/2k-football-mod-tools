"""The pregame welcome skips a stadium whose recorded name the build has replaced (beta 81, sb-booth). EXPERIMENTAL.

Stale-line audit finding 1 (coordinator's ruling: "a missing welcome beats a wrong one; keep the correct ones").

How the welcome is picked (static RE, retail executable and data)
-----------------------------------------------------------------
* The pregame director (DRCT outer 1194) event 113 child 67 is the regular-season welcome: it says phrase key 14039.
  In the ``lines`` speech index (SPCI, outer 3) 14039 is a context key (the third table): its one variant uses context
  list 2936 (body +0x6AA6: a u16 count of 70, then 70 u16 values) and stream 18029 + j plays for the j-th value. The
  values are the stadium numbers (the digits of the stadium's asset code: 20 is the Raiders' "s20", 37 Reliant, 32 the
  practice facility); stream 18049 (s20) is "Hi there, I'm Dan Stevens and welcome to the Oakland Coliseum".
* 14039's context handler (0x137EC0) returns the current stadium's number if 14039 has a recording for it, else 999.
  The lookup FUN_0013CBA0 scans the list for the context; when no value matches, the booth's resolver 0x67560 (the
  speech sequencer's +0x1050 hook) retries context 999 and the other speaker variant, and when those fail too the
  sequencer FUN_000C32C0 drops the phrase (0xC3424 -> 0xC33D9): nothing is said and the intro goes on.
* List 2936 belongs to 14039 alone (no other key of the table uses it), and 14039 has no context 997, 998 or 999, so
  a removed stadium is always skipped (nfl2k5_stale_speech.spoken models this).

What this owner does
--------------------
For each of the 20 stadiums whose recording names a building or city the 2026 product no longer shows, and only when
the built disc's stadium row really shows another name (its display name differs from the retail one, ignoring spaces
and case), the stadium's
value in list 2936 becomes 0xFFFF, which no stadium number matches. That stadium's welcome is then skipped; every
other value, stream and key keeps its bytes. A disc without the venue renames is left alone (the recording still
matches the row). A stadium whose welcome recording the user replaced through the commentary replacement
(``keep_streams``) keeps its value, so the user's recording stays reachable. Data only: two bytes per stadium in the
one ``lines`` SPCI, which the disc stores uncompressed.

Witnessed (xemu, 2026-11-25): Commanders at Giants on a disc with the list edited: the pregame looked up 14039 with
context 18 (MetLife Stadium, row s18), the scan reported no match (0x13CE33) and the booth went on to its next line;
team-context lines in the same pregame matched (0x13CE3F). Not witnessed: a kept stadium's welcome.
"""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any, Callable

OWNER = "nfl2k5_stadium_welcome"
SCHEMA = "nfl2k5_stadium_welcome/v1"
LABEL = "EXPERIMENTAL"
SPCI_OUTER_INDEX = 3
SPCI_STORED = 45_424                     # the lines SPCI body (stored size; the 0x20 wrapper precedes it)
SPCI_NAME = "lines"
KEY = 14039
LIST_OFFSET = 0x6AA6                     # body offset of list 2936: u16 count, then the values
LIST_COUNT = 70
FIRST_STREAM = 18029                     # lines.bin stream of the list's first value (stream = FIRST_STREAM + j)
RETAIL_VALUES = tuple(range(0, 33)) + (36, 37, 48) + tuple(range(51, 72)) + tuple(range(73, 86))
SKIP = 0xFFFF
#: stadium number -> (the recorded welcome, the retail display name of its row)
STALE = {
    1: ("the Georgia Dome", "The Georgia Dome"),
    3: ("Ralph Wilson Stadium", "Ralph Wilson Stadium"),
    6: ("Paul Brown Stadium", "Paul Brown Stadium"),
    7: ("Texas Stadium", "Texas Stadium"),
    8: ("Invesco Field at Mile High Stadium", "INVESCO Field at Mile High Stadium"),
    11: ("the RCA Dome", "The RCA Dome"),
    12: ("Alltel Stadium", "ALLTEL Stadium"),
    14: ("Pro Player Stadium", "Pro Player Stadium"),
    15: ("the Hubert H. Humphrey Metrodome", "H. H. H. Metrodome"),
    17: ("the Louisiana Superdome", "The Louisiana Super Dome"),
    18: ("Giants Stadium", "Giants Stadium"),
    19: ("Jets Stadium", "Giants Stadium"),
    20: ("the Oakland Coliseum", "Network Associates Coliseum"),
    22: ("Heinz Field", "Heinz Field"),
    23: ("the Edward Jones Dome", "Edward Jones Dome "),
    24: ("Qualcomm Stadium", "QUALCOMM Stadium"),
    25: ("San Francisco, California", "San Francisco Park"),
    27: ("Tampa Bay Stadium", "Tampa Bay Stadium"),
    28: ("the Titans Coliseum", "Titans Coliseum"),
    30: ("Browns Stadium", "The Cleveland Browns Stadium"),
}


class StadiumWelcomeError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise StadiumWelcomeError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def find_spci(entry: bytes) -> int:
    """Offset of the lines SPCI wrapper inside outer entry 3, found by content (magic, stored size, name)."""
    needle = b"SPCI" + struct.pack("<I", SPCI_STORED)
    name = SPCI_NAME.encode("utf-16-le")
    hits, at = [], entry.find(needle)
    while at != -1:
        body = at + 0x20
        if entry[body + 0x0C:body + 0x10] == b"SPCI" and entry[body + 0x20:body + 0x20 + len(name)] == name:
            hits.append(at)
        at = entry.find(needle, at + 1)
    require(len(hits) == 1, f"expected exactly one lines speech index in outer entry 3, found {len(hits)}")
    return hits[0]


def same_name(a: str, b: str) -> bool:
    """Display names compared without case and extra spaces ("Edward Jones Dome " is "Edward Jones Dome")."""
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def stream_of(stadium: int) -> int:
    return FIRST_STREAM + RETAIL_VALUES.index(stadium)


def list_values(body: bytes) -> tuple[int, ...]:
    count = struct.unpack_from("<H", body, LIST_OFFSET)[0]
    require(count == LIST_COUNT, f"the welcome's stadium list holds {count} values, not {LIST_COUNT}")
    return struct.unpack_from(f"<{count}H", body, LIST_OFFSET + 2)


def list_state(body: bytes) -> tuple[str, list[int]]:
    """('retail' | 'applied' | 'foreign', the skipped stadium numbers)."""
    try:
        values = list_values(body)
    except (StadiumWelcomeError, struct.error):
        return "foreign", []
    skipped = []
    for want, have in zip(RETAIL_VALUES, values):
        if have == want:
            continue
        if have == SKIP and want in STALE:
            skipped.append(want)
            continue
        return "foreign", []
    return ("applied" if skipped else "retail"), skipped


def stale_rows(stadiums: dict[int, str]) -> list[int]:
    """The stale stadium numbers whose row on this disc shows another name than retail (``stadiums``: number ->
    display name read from the built disc's main roster)."""
    return sorted(n for n, (_said, retail) in STALE.items() if n in stadiums and not same_name(stadiums[n], retail))


def kept_for_user(stadiums: list[int], keep_streams: Any = ()) -> list[int]:
    """The stadiums among ``stadiums`` whose welcome recording the user replaced (left alone)."""
    keep = frozenset(keep_streams)
    return sorted(n for n in stadiums if stream_of(n) in keep)


def patch_body(body: bytes, skip: list[int]) -> tuple[bytes, dict[str, Any]]:
    """The SPCI body with the given stadiums' values replaced by 0xFFFF (retail or a previous subset only)."""
    state, already = list_state(body)
    require(state in ("retail", "applied"), "the welcome's stadium list is not the retail one; refusing")
    require(set(skip) <= set(STALE), f"not a stale stadium: {sorted(set(skip) - set(STALE))}")
    out = bytearray(body)
    for n in skip:
        at = LIST_OFFSET + 2 + 2 * RETAIL_VALUES.index(n)
        struct.pack_into("<H", out, at, SKIP)
    result = bytes(out)
    new_state, now = list_state(result)
    require(sorted(now) == sorted(set(already) | set(skip)), "the patched list does not read back")
    changed = [i for i, (a, b) in enumerate(zip(body, result)) if a != b]
    return result, {"state": new_state, "skipped": now, "newly_skipped": sorted(set(skip) - set(already)),
                    "changed_bytes": len(changed), "before_sha256": sha(body), "after_sha256": sha(result)}


def _stadium_names(path: Path | str) -> dict[int, str]:
    from . import nfl2k5_modern_metlife as mm
    from . import nfl2k5_roster_records as rr
    with rr._outer_image()(path) as archive:
        body = archive.read_entry(rr.ROST_OUTER_INDEX)[rr.RESOURCE_HEADER_SIZE:]
    names = {}
    for _offset, fields in mm._stadium_records(body):
        code = fields["asset_code"][1]
        if len(code) == 3 and code[0] == "s" and code[1:].isdigit():
            names.setdefault(int(code[1:]), fields["display_name"][1])
    return names


def status(path: Path | str, keep_streams: Any = ()) -> dict[str, Any]:
    from . import nfl2k5_roster_records as rr
    with rr._outer_image()(path) as archive:
        entry = archive.entries[SPCI_OUTER_INDEX]
        raw = archive.read(entry.virtual_offset, entry.size)
    at = find_spci(raw)
    state, skipped = list_state(raw[at + 0x20:at + 0x20 + SPCI_STORED])
    stale = stale_rows(_stadium_names(path))
    kept = kept_for_user(stale, keep_streams)
    return {"state": state, "skipped": skipped, "stale_rows": stale, "kept_for_user_recordings": kept,
            "expected": sorted(set(stale) - set(kept))}


def apply_to_image(path: Path | str, *, keep_streams: Any = (),
                   progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Skip the welcome for every stale stadium whose row this disc renamed (in place on a built COPY, read back).

    A disc whose main roster has no stadium rows this module can read, or that renamed none of the 18 stadiums, is left
    alone and reported (state ``skipped`` / ``not_needed``); a disc that needs the change but whose speech index is not
    the retail one refuses, writing nothing."""
    from . import nfl2k5_roster_records as rr
    say = progress or (lambda _m: None)
    head = {"owner": OWNER, "schema": SCHEMA, "label": LABEL, "runtime_witnessed": False, "key": KEY}
    try:
        names = _stadium_names(path)
    except (OSError, ValueError, KeyError, IndexError, struct.error) as exc:
        return {**head, "state": "skipped", "reason": f"no readable stadium rows: {exc}", "changed_bytes": 0}
    stale = stale_rows(names)
    kept = kept_for_user(stale, keep_streams)
    skip = sorted(set(stale) - set(kept))
    if not skip:
        return {**head, "state": "not_needed", "reason": "no stale stadium row is renamed on this disc",
                "kept_for_user_recordings": kept, "changed_bytes": 0}
    with rr._outer_image()(path, writable=True) as archive:
        entry = archive.entries[SPCI_OUTER_INDEX]
        raw = archive.read(entry.virtual_offset, entry.size)
        at = find_spci(raw)
        body = raw[at + 0x20:at + 0x20 + SPCI_STORED]
        result, receipt = patch_body(body, skip)
        if receipt["changed_bytes"]:
            say(f"Pregame welcome: skipping {len(receipt['newly_skipped'])} renamed stadiums")
            start = entry.virtual_offset + at + 0x20 + LIST_OFFSET + 2
            span = result[LIST_OFFSET + 2:LIST_OFFSET + 2 + 2 * LIST_COUNT]
            require(archive.write(start, span) == len(span), "short write of the stadium list")
            back = archive.read(entry.virtual_offset + at + 0x20, SPCI_STORED)
            require(back == result, "the speech index did not read back")
    return {**head, "skipped_stadiums": receipt["skipped"], "kept_with_retail_names": sorted(set(STALE) - set(stale)),
            "kept_for_user_recordings": kept,
            **{k: v for k, v in receipt.items() if k not in ("skipped",)}}

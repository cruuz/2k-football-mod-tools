"""Final commentary pass of an image build (beta 77, job c2; Noah 2026-10-07: "the 00 is on the replays").

What the announcer says for a player is a 16-bit id stored in the player's record (``pbp_id``, +0x04). The commentary
engine looks it up in the cue table of the ``players`` bank (the SPCI resource inside outer entry 3). Ids 9000..9099
are the recorded number calls ("number fifteen"), and **9100 is the recorded "double zero"** (the six clips "double
zero", "number double zero", ...). When an id has no recorded clip for the situation, the game's own resolver
(``FUN_00067150``) falls back to ``9000 + the live uniform number``; the recorded "double zero" is only ever heard
when the stored id *is* 9100 (or the uniform bits hold 100). Every voice (live calls, replays, halftime, the stadium
PA) is built by the one sequencer ``FUN_000C32C0`` and corrected by that one resolver, so there is no separate replay
path: a replay says "double zero" exactly when a player record the replay is built from carries 9100.

Beta 76.0 to 76.4 wrote 9100 into about half of the roster as a "jersey number fallback" (job c1 of beta 76.5 found
that and repaired the main roster only). Two kinds of copies were left behind, and this module covers both:

1. **Disc rosters nobody finalized.** The ESPN 25th Anniversary team-season rosters (packs E and F) copy a matched
   person's play-by-play id from the main roster of the day, and the 35 shared historic rosters keep the retail
   placeholder's id after the writer changed the player and his number. Both writers defer the commentary word to a
   "final pass" that only ever ran on the main roster. ``finalize_resources`` is that pass for every other ROST
   resource of the image: only the u16 at record +0x04 of populated players can change, by c1's rules
   (``nfl2k5_roster_records.commentary_id``).
2. **Copies no disc repair can reach**: older saved rosters and franchises (a franchise embeds its whole roster) and the
   players inside saved weekly highlights, which the halftime and wrap-up shows replay. ``retire_cue`` removes the cause
   at the cue table: the one id 9100 in the sorted type-2 id array of the ``players`` SPCI becomes 9199 (nothing uses
   it), which keeps the array sorted and every stream index unchanged. A player whose stored id is 9100 is then not
   found in the table, so the resolver takes its normal fallback and the announcer says the live number, in every
   context. #0 players are unaffected (9000 is "zero"/"number zero"). The Studio keeps uniform numbers to 0..99, so no
   player can legitimately wear the recorded "00" (a stored 100 would now be called "this guy"). The six recorded
   "double zero" clips stay in the bank, reachable as the explicit id 9199, should a real 00 ever be wanted.

Data only: one byte in a 19,712-byte table plus the u16 id words of the changed players; the executable is not touched.
The main roster resource is not touched here (``nfl2k5_roster_records.apply`` owns it). Unwitnessed in a played game.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any, Callable

from . import nfl2k5_roster_records as _rost

OWNER = "nfl2k5_commentary_final"
SCHEMA = OWNER + "/v1"

# ------------------------------------------------------------------------------------------- the cue table
SPCI_OUTER_INDEX = 3                  # the package holding the three commentary cue tables (lines, players, teams)
SPCI_SIZE = 0x4D00                    # wrapper + body of the players table
SPCI_MAGIC = b"SPCI"
SPCI_BODY_SIZE = 0x4CE0               # the u32 at +4
SPCI_NAME_OFFSET = 0x40               # UTF-16 "players" inside the wrapper (after the inner SPCI chunk header)
ID_TABLE_OFFSET = 0x78                # 1,396 sorted u16 ids (the type-2 table: number calls, names, coaches ...)
ID_COUNT = 1396
OLD_CUE = 9100                        # the recorded "double zero"
NEW_CUE = 9199                        # unused: between 9099 and the next id 9204 of the sorted array
RETAIL_SPCI_SHA256 = "87ba7b8de47d0181d1c26c33ca8f6a314a3fa5a42e40718dca57ae4eda22a2af"
APPLIED_SPCI_SHA256 = "507c3c8a865b94e5014a8f17cb01b112f7879e410d4e25b605b87a1f2a82ce36"
EXPECTED_ID_INDEX = 1371              # position of the id in the array (byte offset 0xB2E inside the table)
EXPECTED_ID_OFFSET = ID_TABLE_OFFSET + 2 * EXPECTED_ID_INDEX
EXPECTED_SPCI_OFFSET_IN_ENTRY = 0x240E90   # retail position; the code finds the table by content

# ------------------------------------------------------------------------------------------- the rosters
MAIN_ROSTER_MIN_SIZE = 0x90000        # the main ROST (0x90F80, or 0x92060 grown) belongs to nfl2k5_roster_records.apply
MAX_RESOURCE = 0x90000                # bounded read: one-team historic and Anniversary files are 7 to 14 KB


class CommentaryFinalError(ValueError):
    """The table or image is not one this pass can prove."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CommentaryFinalError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------------------------------- the cue table
def ids(table: bytes) -> tuple[int, ...]:
    """The sorted id array of a players SPCI table."""
    _require(len(table) >= ID_TABLE_OFFSET + 2 * ID_COUNT, "players cue table is truncated")
    return struct.unpack_from(f"<{ID_COUNT}H", table, ID_TABLE_OFFSET)


def table_status(table: bytes) -> str:
    """'retail' (9100 present), 'applied' (9100 retired) or 'foreign' for the 0x4D00-byte players cue table."""
    if len(table) != SPCI_SIZE or table[:4] != SPCI_MAGIC:
        return "foreign"
    digest = sha256(table)
    if digest == RETAIL_SPCI_SHA256:
        return "retail"
    if digest == APPLIED_SPCI_SHA256:
        return "applied"
    return "foreign"


def patch_table(table: bytes) -> tuple[bytes, dict[str, Any]]:
    """The table with the one id changed. Retail only; an applied table is returned unchanged."""
    state = table_status(table)
    if state == "applied":
        return bytes(table), {"status": "applied", "already_applied": True, "changed_bytes": 0}
    _require(state == "retail", "the players cue table is not the pinned retail table; refusing")
    array = ids(table)
    _require(list(array) == sorted(set(array)), "the id array is not strictly sorted")
    _require(array.index(OLD_CUE) == EXPECTED_ID_INDEX and NEW_CUE not in array,
             "the cue ids are not where the retail table has them")
    _require(array[EXPECTED_ID_INDEX - 1] < NEW_CUE < array[EXPECTED_ID_INDEX + 1],
             "the new id would break the sorted order")
    out = bytearray(table)
    struct.pack_into("<H", out, EXPECTED_ID_OFFSET, NEW_CUE)
    result = bytes(out)
    _require(table_status(result) == "applied", "patched table does not match the pinned applied table")
    changed = [i for i, (a, b) in enumerate(zip(table, result)) if a != b]
    return result, {"status": "applied", "already_applied": False, "changed_bytes": len(changed),
                    "table_offsets": changed, "before_sha256": sha256(table), "after_sha256": sha256(result),
                    "old_cue": OLD_CUE, "new_cue": NEW_CUE, "id_index": EXPECTED_ID_INDEX}


def find_table(entry: bytes) -> int:
    """Offset of the players SPCI table inside outer entry 3, found by content (magic, size field, 'players')."""
    needle = SPCI_MAGIC + struct.pack("<I", SPCI_BODY_SIZE)
    marker = "players".encode("utf-16-le")
    hits, at = [], entry.find(needle)
    while at != -1:
        if entry[at + SPCI_NAME_OFFSET: at + SPCI_NAME_OFFSET + len(marker)] == marker and at + SPCI_SIZE <= len(entry):
            hits.append(at)
        at = entry.find(needle, at + 1)
    _require(len(hits) == 1, f"expected exactly one players cue table in the commentary package, found {len(hits)}")
    return hits[0]


def _cue_entry(archive: Any) -> Any:
    entries = archive.entries
    _require(len(entries) > SPCI_OUTER_INDEX, f"the archive has no outer entry {SPCI_OUTER_INDEX}")
    entry = entries[SPCI_OUTER_INDEX]
    _require(entry.size >= SPCI_SIZE, "outer entry 3 is too small to hold the players cue table")
    return entry


def read_table(path: Path | str) -> tuple[bytes, int]:
    """(table bytes, virtual offset of its first byte) from a disc image or a loose pack folder."""
    with _rost._outer_image()(path) as archive:
        entry = _cue_entry(archive)
        data = archive.read(entry.virtual_offset, entry.size)
        at = find_table(data)
        return data[at: at + SPCI_SIZE], entry.virtual_offset + at


def cue_status(path: Path | str) -> str:
    """retail | applied | foreign for a disc image or a loose pack folder."""
    try:
        return table_status(read_table(path)[0])
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def retire_cue(archive: Any, *, say: Callable[[str], None] = lambda _m: None) -> dict[str, Any]:
    """Retire the cue in an open WRITABLE archive: one byte, read back and verified."""
    entry = _cue_entry(archive)
    data = archive.read(entry.virtual_offset, entry.size)
    at = find_table(data)
    before = data[at: at + SPCI_SIZE]
    patched, receipt = patch_table(before)
    if receipt["already_applied"]:
        return {**receipt, "outer_index": SPCI_OUTER_INDEX, "virtual_offset": f"0x{entry.virtual_offset + at:x}"}
    say("Retiring the recorded double-zero call-out in the commentary cue table")
    write_at = entry.virtual_offset + at + EXPECTED_ID_OFFSET
    count = archive.write(write_at, patched[EXPECTED_ID_OFFSET: EXPECTED_ID_OFFSET + 2])
    _require(count == 2, "short write of the cue id")
    after = archive.read(entry.virtual_offset, entry.size)
    _require(after[at: at + SPCI_SIZE] == patched, "read-back of the cue table differs")
    _require(after[:at] + after[at + SPCI_SIZE:] == data[:at] + data[at + SPCI_SIZE:], "bytes outside the cue table changed")
    return {**receipt, "outer_index": SPCI_OUTER_INDEX, "virtual_offset": f"0x{entry.virtual_offset + at:x}",
            "written_virtual_offset": f"0x{write_at:x}", "written_bytes": 2}


# ------------------------------------------------------------------------------------------- the rosters
def roster_entries(archive: Any) -> list[Any]:
    """Every outer entry that is a ROST resource other than the main roster, found by content."""
    out = []
    for entry in archive.entries:
        if 0x60 < entry.size < MAX_RESOURCE and archive.read(entry.virtual_offset, 4) == b"ROST":
            out.append(entry)
    return out


def plan_resources(archive: Any, *, strict: bool = True, skipped: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The pending commentary edits per roster resource (nothing is written).

    ``strict`` refuses an unreadable resource (the disc repair does). The build step is not strict: a resource that merely
    starts with ROST but is not a roster this module can read is left alone and listed in ``skipped``.
    """
    plans = []
    for entry in roster_entries(archive):
        raw = archive.read(entry.virtual_offset, entry.size)
        try:
            fixed, receipt = _rost.repair_commentary_resource(raw)
        except (ValueError, IndexError, KeyError, struct.error) as exc:
            if strict:
                raise CommentaryFinalError(f"outer entry {entry.index}: not a readable roster ({exc})") from exc
            if skipped is not None:
                skipped.append({"outer_index": entry.index, "name_id": entry.name_id, "size": entry.size, "reason": str(exc)})
            continue
        plans.append({"entry": entry, "raw": raw, "fixed": fixed, "receipt": receipt})
    return plans


def finalize_resources(archive: Any, *, say: Callable[[str], None] = lambda _m: None, strict: bool = True) -> dict[str, Any]:
    """Final commentary pass on an open WRITABLE archive: only pbp_id words of populated players change."""
    skipped: list[dict[str, Any]] = []
    plans = plan_resources(archive, strict=strict, skipped=skipped)
    changed, resources, words = 0, [], 0
    for plan in plans:
        entry, receipt = plan["entry"], plan["receipt"]
        if not receipt["players_changed"]:
            continue
        for edit in receipt["edits"]:
            at = entry.virtual_offset + _rost.RESOURCE_HEADER_SIZE + edit["offset"]
            _require(archive.write(at, struct.pack("<H", edit["after"])) == 2, "short write of a play-by-play id")
            words += 1
        check = archive.read(entry.virtual_offset, entry.size)
        _require(check == plan["fixed"], f"read-back of outer entry {entry.index} differs")
        allowed = {_rost.RESOURCE_HEADER_SIZE + e["offset"] + k for e in receipt["edits"] for k in (0, 1)}
        _require(all(a == b or i in allowed for i, (a, b) in enumerate(zip(plan["raw"], check))),
                 f"outer entry {entry.index} changed outside pbp_id")
        changed += 1
        resources.append({"outer_index": entry.index, "name_id": entry.name_id, "size": entry.size,
                          "players_changed": receipt["players_changed"],
                          "before_sha256": sha256(plan["raw"]), "after_sha256": sha256(check)})
    if changed:
        say(f"Finalized the play-by-play ids of {changed} historic and Anniversary rosters")
    return {"resources_scanned": len(plans) + len(skipped), "resources_changed": changed, "words_written": words,
            "field": "pbp_id", "record_offset": 4, "resources": resources, "unreadable_skipped": skipped}


def rosters_status(path: Path | str) -> str:
    """'applied' (no roster resource would change), 'pending' (some would), or 'foreign' (unreadable)."""
    try:
        with _rost._outer_image()(path) as archive:
            pending = sum(p["receipt"]["players_changed"] for p in plan_resources(archive, strict=False))
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"
    return "pending" if pending else "applied"


def status(path: Path | str) -> str:
    """'applied' when the cue is retired and no roster is pending; 'retail' when neither half has been done."""
    cue, rosters = cue_status(path), rosters_status(path)
    if "foreign" in (cue, rosters):
        return "foreign"
    if cue == "applied" and rosters == "applied":
        return "applied"
    return "retail" if cue == "retail" else "partial"


def apply(path: Path | str, *, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Both halves on the disc image at ``path`` (a private COPY). Idempotent.

    The build step must never break a build over a disc it does not recognise: a cue table that is not the pinned
    retail or applied table is left alone and reported as skipped, and so is a ROST-looking resource that is not a
    readable roster. (The native disc repair, ``tools/b77/c2_repair.py``, is strict.)
    """
    say = progress or (lambda _m: None)
    with _rost._outer_image()(path, writable=True) as archive:
        try:
            cue = retire_cue(archive, say=say)
        except CommentaryFinalError as exc:
            cue = {"status": "skipped", "reason": str(exc), "changed_bytes": 0}
        rosters = finalize_resources(archive, say=say, strict=False)
    return {"owner": OWNER, "schema": SCHEMA, "status": status(path), "cue": cue, "rosters": rosters}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", type=Path, help="disc image or loose pack folder (read-only)")
    args = parser.parse_args(argv)
    print(json.dumps({"owner": OWNER, "status": status(args.image), "cue": cue_status(args.image),
                      "rosters": rosters_status(args.image)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

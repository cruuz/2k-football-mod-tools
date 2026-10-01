"""The practicing team's logo at the practice field's midfield (job pf, P1). EXPERIMENTAL / UNWITNESSED.

The engine (PROVED OFFLINE by static reading, the pf report section 3): once a venue's field scene is loaded (the SCNE
named ``field``, 0x9C185), the field swap at 0x9C5DE..0x9C669 walks seven name pairs at .rdata 0x4F0090 (``center_logo``
to ``center_logo``, ``endzone_N_L`` to ``endzone_north_left`` ... ``endzone_S_R`` to ``endzone_south_right``). For each
pair the field scene's material of the first name takes the first loaded TXTR of the second name (the lookup 0x449E0
walks every loaded package); a material the field lacks, or a TXTR no loaded package carries, changes nothing (the
write at 0x9C659 needs both).

This owner copies the seven pairs into a 64-byte read-only allocation of ``nfl2k5_xbe_space`` with an eighth pair, the
field material ``teamlogo`` (the UTF-16 string at 0xE7C9D8) to the TXTR ``logo`` (0xE65BF0), both strings the
executable already carries, and re-points the loop's two bounds: the start at 0x9C5E2 (0x4F0094 to the table + 4) and
the end at 0x9C661 (0x4F00CC to the table + 0x44). The practice facility's field names its midfield material
``teamlogo`` when the Build's ``modern_practice_field_team_logo`` is on, so the practice field takes the ``logo`` TXTR
of a loaded uniform package (all 634 retail uniform packages carry one; PROVED OFFLINE). No retail scene carries the
name ``teamlogo`` (PROVED OFFLINE over every SCNE in the archive), so every other venue's field is unchanged; when no
``logo`` is loaded the midfield keeps its own texture.

Which logo shows with two teams loaded (Scrimmage, MyCareer) is the first the lookup finds (INFERRED: one of the two;
the lab records it). Basic Training dresses both sides in the practice kits 31h0/31a0, whose ``logo`` is the game's own
2004 NFL shield.

Status: ``retail`` (the two bounds retail; the table absent or reserved and empty), ``applied`` (the exact table and
both bounds), else ``foreign``. The loop, the retail table, the two strings and the field binding are pinned by
SHA-256. ``revert`` restores exactly: the two bounds back and the table empty again (the reservation stays, as every
owner's does on a union build).
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_team_logo_swap"
LABEL = "EXPERIMENTAL / UNWITNESSED"
BUILD_KEY = "modern_practice_field_team_logo"
BUILD_CAPTION = "Practice field: team logo at midfield (experimental)"
HELP_TEXT = (
    "With the Modern practice facility on, the practice field's midfield shows the logo of a team on the field instead "
    "of the league shield: the game's field swap gets one more pair in a small executable table, and the practice "
    "field's midfield takes the logo from the uniform package the game has loaded. With two different teams the game "
    "picks one of them; Basic Training's practice kits carry the game's own NFL shield. Every other stadium is "
    "unchanged. Off in every preset; needs a disc image; appearance in game is unwitnessed."
)
#: 64 bytes of read-only space, placed after every existing read-only owner (the name sorts last), so no other owner's
#: address moves
REQUESTS = ((OWNER, "read_only", 64, 4),)

RETAIL_TABLE_VA = 0x4F0090
RETAIL_PAIRS = ((0xE66350, 0xE66350), (0xE66368, 0xE66380), (0xE663A8, 0xE663C0), (0xE663EC, 0xE66404),
                (0xE6642C, 0xE66444), (0xE6646C, 0xE66484), (0xE664B0, 0xE664C8))
TEAM_LOGO_MATERIAL_VA, LOGO_TXTR_VA = 0xE7C9D8, 0xE65BF0
TEAM_LOGO_PAIR = (TEAM_LOGO_MATERIAL_VA, LOGO_TXTR_VA)
TABLE = b"".join(struct.pack("<II", *p) for p in RETAIL_PAIRS + (TEAM_LOGO_PAIR,))
START_SITE, RETAIL_START = 0x9C5E2, RETAIL_TABLE_VA + 4          # mov dword [esp+0xC], imm32 (the first pair's +4)
END_SITE, RETAIL_END = 0x9C661, RETAIL_TABLE_VA + 4 + 8 * len(RETAIL_PAIRS)   # cmp edi, imm32
#: (va, size, SHA-256) of the retail bytes this owner relies on, with its two bounds read as retail
GUARDS = (
    (0x9C5DE, 0xDB, "bf869361c8e6b49cf08213f30d38767b8c14f03e369f8f167dfbb0857612c582"),    # the swap loop
    (RETAIL_TABLE_VA, 56, "5a73c30d0eb969ec00e0a5bd24b9035c7e65e53ed29bd276beff5d26b020f80d"),  # the seven pairs
    (TEAM_LOGO_MATERIAL_VA, 18, "0d47c413701b73669c13c11ddb03a8eb262d9d54da9a4b55a6ba2017e2ae8b18"),  # L"teamlogo"
    (LOGO_TXTR_VA, 10, "2c53c8ddc2f8bfec98a484d0fc08515f270c0db3ecfc783c613b91a6b2feb718"),  # L"logo"
    (0x9C185, 0x18, "7bcff3e6281d98b3998b43fc920f20e9d9c4b44367c4f74f0beec553d4b4c5f2"),  # the field SCNE binding
)


class TeamLogoSwapError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise TeamLogoSwapError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


assert len(TABLE) == 64 and RETAIL_END == 0x4F00CC


def allocation(payload):
    """This owner's read-only allocation, or None when the executable has no space or does not reserve it."""
    if space.status(payload) != "applied":
        return None
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == REQUESTS[0][1:],
             "foreign team-logo allocation geometry")
    return rows[0]


def sites(place):
    """(label, va, retail bytes, applied bytes) of the two loop bounds for the table at ``place``."""
    table = place["va"]
    return [("team_logo_swap_start", START_SITE, struct.pack("<I", RETAIL_START), struct.pack("<I", table + 4)),
            ("team_logo_swap_end", END_SITE, struct.pack("<I", RETAIL_END),
             struct.pack("<I", table + 4 + len(TABLE)))]


def inspect(payload):
    """True when applied, False when retail (reserved or not); raises on anything else."""
    _require(isinstance(payload, bytes) and len(payload) <= space.SCALE_FILE_SIZE, "expected bounded default.xbe bytes")
    image = XbeImage(payload)
    place = allocation(payload)
    installed = False
    if place is not None:
        content = image.read(place["va"], place["size"])
        installed = content == TABLE
        _require(installed or content == bytes(len(TABLE)), "foreign team-logo table")
    bounds = sites(place) if place is not None else [
        ("team_logo_swap_start", START_SITE, struct.pack("<I", RETAIL_START), None),
        ("team_logo_swap_end", END_SITE, struct.pack("<I", RETAIL_END), None)]
    for label, va, before, after in bounds:
        _require(image.read(va, 4) == (after if installed else before), f"mixed or foreign {label}")
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for _label, at, before, _after in bounds:
            if va <= at and at + 4 <= va + size:
                blob[at - va:at - va + 4] = before
        _require(_sha(bytes(blob)) == digest, f"foreign prerequisite at {va:#x}")
    return installed


def status(payload):
    try:
        return "applied" if inspect(payload) else "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, zlib.error):
        return "foreign"


def verify(payload):
    installed = inspect(payload)
    place = allocation(payload) if installed else None
    return dict(status="applied" if installed else "retail", owner=OWNER, label=LABEL, experimental=True,
                runtime_witnessed=False, table_va=hex(place["va"]) if place else None,
                pairs=len(RETAIL_PAIRS) + (1 if installed else 0))


def apply(payload):
    """The eighth pair: the table in this owner's read-only allocation (reserved here on an executable without space;
    a union build reserves it with the other owners first), then the two loop bounds, each digest re-sealed."""
    if inspect(payload):
        return payload, dict(**verify(payload), changed_bytes=0, edits=[])
    allocated, allocation_receipt = (space.apply(payload, REQUESTS, scaleout=True)
                                    if space.status(payload) == "retail" else (payload, {}))
    place = allocation(allocated)
    _require(place is not None, "reserve the team-logo swap with the complete owner union on a clean base")
    installed, _ = space.install_read_only(allocated, OWNER, TABLE)
    result, patch = rdata.apply(installed, sites(place), OWNER)
    _require(status(result) == "applied", "the team-logo swap read-back failed")
    return result, dict(
        **verify(result), allocation=allocation_receipt, sections_repinned=patch["sections_repinned"],
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
        file_growth=len(result) - len(payload), before_sha256=_sha(payload), after_sha256=_sha(result),
        edits=[dict(label=label, va=hex(va), before=before.hex(), after=after.hex())
               for label, va, before, after in sites(place)],
        reservations=reservations(result))


def revert(payload):
    """The exact inverse of ``apply`` on a reserved executable: the two bounds back to retail and the table empty
    again, byte for byte (the reservation stays)."""
    if not inspect(payload):
        return payload, dict(status="retail", changed_bytes=0, edits=[])
    place = allocation(payload)
    back, _ = rdata.apply(payload, [(label, va, after, before) for label, va, before, after in sites(place)],
                          OWNER + " revert")
    result, _ = space.uninstall_read_only(back, OWNER)
    _require(status(result) == "retail", "the team-logo swap revert read-back failed")
    return result, dict(status="reverted", owner=OWNER, changed_bytes=sum(a != b for a, b in zip(payload, result)))


def reservations(payload):
    """The cave manifest's rows: the named read-only allocation and the two re-pointed operands."""
    place = allocation(payload)
    _require(place is not None and inspect(payload), "the team-logo swap is not installed")
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + 4), size=4, basis="pinned live loop bound; not a cave")
                   for _label, va, _before, _after in sites(place)]


def xbe_of(source):
    """default.xbe's bytes from an executable, a folder of extracted files (or its parent) or a disc image."""
    path = Path(source)
    if path.is_dir():
        for candidate in (path / "default.xbe", path.parent / "default.xbe"):
            if candidate.is_file():
                return candidate.read_bytes()
        raise TeamLogoSwapError("the source folder has no default.xbe")
    if path.suffix.lower() == ".xbe":
        return path.read_bytes()
    from . import nfl2k5_music_archive as archive
    with archive.Disc(path, descriptors=()) as disc:
        entry = disc.entries["default.xbe"]
        _require(entry.size <= 16 * archive.BLOCK, "oversized XBE")
        return disc.read(entry.size, entry.byte_offset)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_team_logo_swap")
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status", help="retail / applied / foreign, and the table's address when applied")
    st.add_argument("source", help="default.xbe, an extracted folder or a disc image")
    args = parser.parse_args(argv)
    payload = xbe_of(args.source)
    state = status(payload)
    place = allocation(payload) if state == "applied" else None
    print(state if place is None else f"{state} table=0x{place['va']:x}")
    return 0 if state != "foreign" else 1


if __name__ == "__main__":
    raise SystemExit(main())

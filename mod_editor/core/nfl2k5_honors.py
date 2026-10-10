"""Player Card honors page (job F5, beta 77): award history on a second card page, live through Franchise. EXPERIMENTAL.

Noah, 2026-10-07: "add another page you can switch to with the bumper buttons on player cards showing award history
for MVPs, Super Bowls, DPOY, ROY, etc. ... (and this dynamically updates throughout MyNFL)".

What the retail game has (static RE of the USA ``default.xbe``; job F5 report)
---------------------------------------------------------------------------
* Season awards are computed once a season, in ``FUN_00116920`` when the week index is 16 (``cmp ebp, 0x10`` at
  0x116D6C), into the season object 0xE5A2F0 (``FUN_000C5C00``): slots ``{player*, team*}`` at +0x5800 MVP,
  +0x5808 Coach of the Year, +0x5810 OPOY, +0x5818 DPOY, +0x5820 OROY, +0x5828 DROY, +0x5830..+0x5878 the season's
  best player in ten position groups (QB RB WR TE OL DL LB DB K P; computed, never shown: a cut All-Pro team) and
  +0x5880 the rushing title (the ``jmp 0x1160C0`` tail). The Super Bowl MVP is +0x5888, chosen per game by
  ``FUN_001167D0`` when ``FUN_00133A30`` (stage 9, Super Bowl row) is true.
* Only the current season is kept: no award history, no record book, no Hall of Fame.

What this owner adds
--------------------
* Storage: one history field per honor in the player's career-stat stream (``player+0x2C``; the stream the card's
  stats table reads, saved with the roster in the franchise save): field 96 MVP, 97 OPOY, 98 DPOY, 99 OROY,
  100 DROY, 101 Super Bowl champion, 102 Super Bowl MVP, 103 Pro Bowl, 104 All-Pro, 105 rushing title. Value 1 in
  the season slot it was won, regular-season class (the rollover wipes postseason words).
* Live updates: after the game's season awards (the tail jump at 0x116E5F) the MVP, OPOY, DPOY, OROY, DROY, the ten
  best-at-position players (as All-Pro) and the rushing champion get their honor; after a game commit
  (``FUN_00135310``'s last call, 0x1356B4) that ``FUN_00133A30`` calls the Super Bowl, every player of the winning
  team and the Super Bowl MVP get theirs. Franchise only (``[0xE576A0] == 2``). Pro Bowl honors are seeded, not live.
* The history fold (``FUN_0014EFE0``, run when the pool is full) merges a season by sum or max from ``.data``
  0xAA26C0[field]; past field 86 that lookup reads unrelated variables, so the honor fields get a fixed rule: sum.
  Every other field keeps the retail lookup.
* The card: the Black/White buttons (LB/RB on a modern pad in xemu) and the triggers (the game's L1/R1) flip the
  card to an honors page and back (with the menu cursor sound); every card opens on the retail page. On the honors
  page the ten rating slots show the honor counts and the bio lines show the years of the top three honors, in the
  card's own fonts, colour and positions. The stats table, header, photo and model are unchanged.

Allocation: a late owner (``nfl2k5_xbe_space.LATE_OWNERS``, the last one), code + a 16-byte RW block. The complete
union has no free RX or RW bytes for it, so (job i1) its 2,560 code bytes sit in the 8 KiB MyCareer footprint
(``GAP_OWNERS``: unreferenced 0xCC padding once M3 promotes the old request) and its 16 RW bytes at the top of the legacy
RW page (``TAIL_OWNERS``). It is part of ``dormant_union()``; on an image without a promoted MyCareer the code is appended
after the other late owners.

Coexistence (job f5b): the ``history_fold`` site (0x14F168) lies inside ``nfl2k5_defensive_try``'s pinned history-engine
context (0x14E7E0, 3,216 bytes). No site outside that span can carry the edit (the rule table's three readers and the
fold's two callers are all inside it). defensive_try restores the site's retail bytes before it hashes its context, and
only while ``fold_site_edit`` says this owner is exactly applied; the hook returns the retail value for every field
except 96..105 and defensive_try writes field 59 only. Proof: tests/mod_editor/test_nfl2k5_honors_defensive_try.py.

Evidence (job F5 report): static RE, then the real code under Unicorn (the card input loop, both page drawers with
the text calls captured, the award commits through the game's own history writer, the Super Bowl commit, the fold).
Not witnessed in game.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_honors_code as runtime
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_honors"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 2560
DATA_SIZE = 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))

UI_LABEL = "Player Card honors page (award history)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the Franchise Player Card has one page and the game forgets every season's "
    "awards. Patch: the bumpers (Black/White; LB/RB in xemu) and the triggers flip any Player Card to an honors page: "
    "MVP, offensive and defensive player of the year, rookies of the year, Super Bowls, Super Bowl MVP, Pro Bowls, "
    "All-Pro and rushing titles, with the years. Each honor is saved in the player's career history, so it moves "
    "with him and survives saves; the game adds this season's winners itself (awards after the regular season, the "
    "Super Bowl champions and MVP after the game). Pair with the sourced award history for the 2026 rosters.")
BUILD_CAPTION = UI_LABEL

FIELD0 = 96
HONORS = ("mvp", "opoy", "dpoy", "oroy", "droy", "super_bowl", "super_bowl_mvp", "pro_bowl", "all_pro",
          "rushing_title")
FIELDS = {name: FIELD0 + i for i, name in enumerate(HONORS)}
LABELS_SHOWN = ("MVP", "OFF. POY", "DEF. POY", "OFF. ROOKIE", "DEF. ROOKIE", "SUPER BOWLS", "SB MVP", "PRO BOWLS",
                "ALL-PRO", "RUSH TITLES")
# season object award slots -> honor (FUN_00116920 / FUN_001160C0 / FUN_001167D0)
AWARDS_VA = 0x00E5A2F0
SEASON_SLOTS = ((0x5800, "mvp"), (0x5810, "opoy"), (0x5818, "dpoy"), (0x5820, "oroy"), (0x5828, "droy")) + tuple(
    (0x5830 + 8 * i, "all_pro") for i in range(10)) + ((0x5880, "rushing_title"),)
SUPER_BOWL_MVP_SLOT = 0x5888

# (label, VA, retail bytes, entry label, opcode, length). Each site becomes a call/jmp rel32 to the entry, padded
# with NOPs to its retail length.
SITE_TABLE = (
    ("card_input", 0x00320D7B, bytes.fromhex("a920020000"), "honors_page_input", 0xE8, 5),
    ("card_enter", 0x00320210, bytes.fromhex("8b0d4802c900"), "honors_page_enter", 0xE8, 6),
    ("card_ratings", 0x00320B75, bytes.fromhex("e886f9ffff"), "honors_page_ratings", 0xE8, 5),
    ("card_bio", 0x00320B7A, bytes.fromhex("e8e1fbffff"), "honors_page_bio", 0xE8, 5),
    ("season_awards", 0x00116E5F, bytes.fromhex("e95cf2ffff"), "honors_season_hook", 0xE9, 5),
    ("game_commit", 0x001356B4, bytes.fromhex("e8c7c50800"), "honors_sb_hook", 0xE8, 5),
    ("history_fold", 0x0014F168, bytes.fromhex("8b04b5c026aa00"), "honors_fold_rule", 0xE8, 7),
)

# Dependencies the runtime calls or reads, pinned by SHA-256 of their retail bytes. Two spans carry a byte other
# patches legitimately change: the Super Bowl row immediate (0x133A41: 0x14 retail, 0x15 with the 18-week season)
# and the card's year base (0x3204AD..0x3204B0: 2004 + 11 retail, the season year + 11 with the year patch); those
# bytes are masked before hashing and checked separately.
GUARDS = (
    ('text init', 0x00046920, 0x16, "715bb82c65136312646957ed6be69fef751004cc7d44f88d321e3c4fd01129e2"),
    ('text font', 0x000469B0, 0xD, "df8e500f21e4fa0b671d89bca38e9934bda6334fe78b372e232d4be9c78d290a"),
    ('text align', 0x00046A00, 0x4, "ed9f6a32e4498f2cf61fbd7a2e9e3cbf505eff408f8aaa0a4a1e0c7ad34271f4"),
    ('text position', 0x00046A70, 0x40, "609c0623574545c3cd4d670b7fa88fc8d2645e4708fd5c09afed1c2c97f92633"),
    ('text colour', 0x00046B50, 0x4, "d3487a2010908a5c9425b41cd1561e0ab67114b078cf02d794fa438402749070"),
    ('text width', 0x00046C50, 0x10, "a4811f90dee5e4196749b5faf93acb5b0a597f9cd633294ca07276d451ee897a"),
    ('text draw', 0x000F1C70, 0x10, "65f6ef40cd75472c38615e4ecf846fc3b3f8bbf6744062b29f2befcd66ade68f"),
    ('font table', 0x000EF850, 0x8, "2b749cc28858f48edd6c85faf49916486d941f55a861696947a0ab14cb1946e4"),
    ('history class set', 0x0014EDB0, 0x7, "d865ebcc76568491ae0bd0c5d7759826052fed67e74abe915e831d299326bef6"),
    ('history set current slot', 0x0014F430, 0x17, "c50c4461b01c36f097954be45394d9aaec9804b89a26d32584689153ecd02151"),
    ('history set slot', 0x0014F3B0, 0x80, "29cd906bd7140161d8e11738e766d70da30aff6144c4f7bf09458f57dd8ab175"),
    ('history search', 0x0014E800, 0x76, "7740102873f81fa61c382775fcc9b793507bf040ef3f88698619a62ba11e4d81"),
    ('history append', 0x0014F220, 0x13A, "fa878dba4f4fb741cb5c7d976311f99fe922cf6487a2119bc15b1b863ee31b1b"),
    ('history fold', 0x0014EFE0, 0x188, "ec6f22000989fe87568948564af27b48e00c78bebd85c03e936d66c6b5ec40bb"),
    ('super bowl predicate', 0x00133A30, 0x1D, "d3e0c6181c3bc2e5e9dbd094122cb687186e766c9f015df24aad1dc278b9e907"),
    ('cell home score', 0x000C5110, 0x36, "7602534cb462964558267d05bb6b12bb885f271c9a5a5510525f958f9383773d"),
    ('cell away score', 0x000C5150, 0x36, "062a264af2bf7428751275cdebc248618869ad7153369f80ea69f2f19d0249c7"),
    ('cell home team', 0x000C4E00, 0x12, "85b4401e850c9a15ab8d953502a50a19a5c5cf14e909987422b9a78157dea3b0"),
    ('cell away team', 0x000C4E20, 0x12, "9a29fc4c3b49d2b68d0f2b3af8b4c25ae6a766d69331ee91f204e2d07dc424d9"),
    ('team first player', 0x000C3E70, 0x10, "d2dca284a4b79a29764b40ba0a6b4917a7f7efa2a22033e1cc8f89bcc193143b"),
    ('team next player', 0x000C3E80, 0x10, "5215f6bb8c45e4866d42661900f17be8b21674bcb0b5ca1c940816a6fab10319"),
    ('season object', 0x000C5C00, 0x6, "edd64758765e448260b1c654bcee0bdb4865c3a2f3bb56dce067d49f5cf25166"),
    ('season awards', 0x00116D6C, 0xFD, "a2add87556435157a60dd8fc1d077720ee5ad17eccc4de176a23b366f30c8a91"),
    ('rushing title', 0x001160C0, 0xB0, "616d08d815f22fbbe6fd1857c3d514cf723cb601b8e299902f896fd80e2c14f9"),
    ('super bowl mvp', 0x001167D0, 0x142, "0dbedbb1c503ac3434d5ee20261a926d02cbeda8e01abab61f9e1d9656558fe1"),
    ('game commit tail', 0x00135694, 0x2C, "b85e12d8dcc3cac82a6e6142babf09fa60961b4a14d9f2f9e2eb41256ef95f37"),
    ('commit restore', 0x001C1C80, 0x10, "90baf67185a3ac002e7e1b5da29c029de41fdba79c689889c17135054f119494"),
    ('menu sound', 0x00038650, 0x10, "e3748cb7822a5af10d575696311650ef9305a14bd68438172ff70d41551fe455"),
    ('sound play', 0x00089DA0, 0x10, "7d7a843ebe16c862c0a1b68a60fb3dac9b899497961b0f7481b51f5eceb65b1b"),
    ('card pad loop', 0x00320D40, 0x53, "67114411d1ed39794abb9fa079bf6daa88f10fe62e6d5da14dbfe88d5ea9a185"),
    ('card draw', 0x00320B70, 0x19, "3f0c1e3186eb2345c6f31c8d3ad6bcebd97971aebf6ea03e4a253491e47cc747"),
    ('card enter', 0x00320210, 0x20, "e32ce94cf6e53a086b10835ba1809aa8d20e036feb358b55977fa1b994713f0e"),
    ('card ratings', 0x00320500, 0x10, "dcec9be654ee739102e2c18f19f1408e379865439a4a5b69bfa9ad725779f580"),
    ('card bio', 0x00320760, 0x10, "bdaf90c36d5848917c1aadd539ad6ef4cbc047bc96358aa58a3c738bddc67bb6"),
    ('card year getter', 0x003204A7, 0xE, "d5e02722189accc6a0718e4a8ebfbcb227c2a3299af8861dbc95a4cc503c770f"),
)
# bytes inside guarded spans that other patches change: (VA, size)
VARIABLE_BYTES = ((0x00133A41, 1), (0x003204AD, 4))
SUPER_BOWL_ROWS = (0x14, 0x15)


class HonorsError(ValueError):
    """Unsupported executable, foreign or mixed installation."""


def _require(condition, message):
    if not condition:
        raise HonorsError(message)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def code_for(code_va: int, data_va: int) -> bytes:
    """The owned RX content with the template's relocations applied, padded to CODE_SIZE with int3."""

    symbols = {"code": code_va, "state": data_va}
    result = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "the honors runtime exceeds its fixed budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def labels(code_va: int) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes)."""

    at = labels(code_va)
    out = []
    for label, va, before, entry, opcode, length in SITE_TABLE:
        after = bytes([opcode]) + _rel32(va + 5, at[entry]) + b"\x90" * (length - 5)
        out.append((label, va, before, after))
    return out


def _guard_digest(image: XbeImage, va: int, size: int, checked_sites) -> str:
    content = bytearray(image.read(va, size))
    for _label, address, before, _after in checked_sites:
        if va <= address and address + len(before) <= va + size:
            content[address - va:address - va + len(before)] = before
    for address, length in VARIABLE_BYTES:
        if va <= address and address + length <= va + size:
            content[address - va:address - va + length] = bytes(length)
    return hashlib.sha256(content).hexdigest()


def guard_digests(payload: bytes) -> dict[str, str]:
    """The masked digests of every guarded span (used to pin GUARD_PINS from the retail executable)."""

    image = XbeImage(payload)
    return {name: _guard_digest(image, va, size, sites(0x14DA000)) for name, va, size, _d in GUARDS}


def _check_guards(image: XbeImage, checked_sites) -> None:
    for name, va, size, digest in GUARDS:
        _require(_guard_digest(image, va, size, checked_sites) == digest, f"foreign honors dependency: {name} ({va:#x})")
    _require(image.read(0x00133A41, 1)[0] in SUPER_BOWL_ROWS, "foreign Super Bowl row predicate")
    base = struct.unpack("<I", image.read(0x003204AD, 4))[0] - 11
    _require(2004 <= base <= 2100, "foreign Player Card year base")


def allocations(payload: bytes) -> dict[str, dict]:
    """{"code": row, "data": row} of an installed allocation, {} when the owner is not allocated."""

    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    found = {r["kind"]: r for r in rows}
    _require(len(rows) == len(found) == 2 and set(found) == {"code", "data"}
             and all((found[k]["size"], found[k]["align"]) == (size, align) for _o, k, size, align in REQUESTS),
             "foreign honors allocation")
    return found


def _owned_state(payload: bytes):
    """-> ("retail" | "applied", allocations | None); anything else raises."""

    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocations(payload)
    if not found:
        retail_sites = sites(0x14DA000)  # the retail bytes do not depend on the pages
        _require(rdata.status(payload, retail_sites) == "retail", "honors sites changed without an allocation")
        _check_guards(image, retail_sites)
        return "retail", None
    code_va, data_va = found["code"]["va"], found["data"]["va"]
    code = image.read(code_va, CODE_SIZE)
    if code == b"\xcc" * CODE_SIZE:
        edits = sites(code_va)
        _require(rdata.status(payload, edits) == "retail", "honors sites changed with an empty allocation")
        _check_guards(image, edits)
        return "retail", found
    _require(code == code_for(code_va, data_va), "foreign honors code")
    edits = sites(code_va)
    _require(rdata.status(payload, edits) == "applied", "mixed honors sites")
    _check_guards(image, edits)
    return "applied", found


def status(payload: bytes) -> str:
    try:
        return _owned_state(payload)[0]
    except (ValueError, IndexError, KeyError, TypeError, struct.error, OverflowError):
        return "foreign"


def fold_site_edit(payload: bytes) -> list[tuple[int, bytes]]:
    """[(VA, retail bytes)] of the history-fold edit while this owner is *exactly* applied, else [].

    b77-f5b: ``nfl2k5_defensive_try`` pins the whole history engine (0x14E7E0, 3,216 bytes) because it writes field 59
    through the engine's writer. This owner's only edit inside that span is the 7-byte rule-table load of the fold
    (``history_fold``, 0x14F168); it returns the retail value for every field outside the ten honor fields, so field
    59 behaves as retail (proved in tests/mod_editor/test_nfl2k5_honors_defensive_try.py). defensive_try restores
    these retail bytes before it hashes its context, and only when the whole honors installation validates here.
    """

    if status(payload) != "applied":
        return []
    return [(va, before) for label, va, before, _after in sites(allocations(payload)["code"]["va"]) if label == "history_fold"]


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "honors_page": state == "applied", "fields": dict(FIELDS) if state == "applied" else None}


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    base = allocations(payload)
    edits = sites(base["code"]["va"] if base else 0x14DA000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the owner and its seven sites. Idempotent."""

    state, found = _owned_state(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": len(runtime.CODE), "owner_bytes": CODE_SIZE + DATA_SIZE,
              "fields": dict(FIELDS)}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0}
    before = payload
    if not found:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocations(payload)
    _require(bool(found), "reserve the honors allocation first")
    code_va, data_va = found["code"]["va"], found["data"]["va"]
    installed, code_receipt = space.install_code(payload, OWNER, code_for(code_va, data_va))
    result, site_receipt = rdata.apply(installed, sites(code_va), OWNER)
    _require(status(result) == "applied", "honors postcondition failed")
    changed = sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before))
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(code_va), "data_va": hex(data_va), "changed_bytes": changed,
                    "sites": [{"label": label, "va": hex(va), "size": len(before_bytes)}
                              for label, va, before_bytes, _after in sites(code_va)],
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def main(argv=None) -> int:
    """python3 -m mod_editor.core.nfl2k5_honors {status,apply} source.xbe [output.xbe]"""

    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=UI_LABEL)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    _require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "apply":
        result, receipt = apply(payload)
        with args.output.open("xb") as stream:
            stream.write(result)
    else:
        receipt = {**read_settings(payload), "owner": OWNER, "experimental": True}
    print(json.dumps(receipt, indent=2, default=str))
    return 0


__all__ = ["OWNER", "REQUESTS", "UI_LABEL", "HELP_TEXT", "BUILD_CAPTION", "FIELDS", "HONORS", "HonorsError", "code_for",
           "sites", "labels", "allocations", "apply", "status", "read_settings", "reservations", "guard_digests",
           "fold_site_edit"]


if __name__ == "__main__":
    raise SystemExit(main())

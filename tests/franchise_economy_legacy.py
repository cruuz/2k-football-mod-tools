"""Test helper: an exact franchise-economy image of an earlier revision, built from the pinned retail XBE.

Revision 1 (beta-77.1 / v0.6.1, b77) and revision 2 (b778 fa1) share one code template, kept as the test
fixture tests/franchise_economy_revision2_code.py; revision 2 adds the two fa1 sites. Revision 3 (b778 fa2)
sites are left retail. No retail code is stored here.
"""
from __future__ import annotations

import struct

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests import franchise_economy_revision2_code as old


def _jump(op, address, target, size):
    return op + struct.pack("<i", target - address - 5) + b"\x90" * (size - 5)


def legacy_image(retail: bytes, revision: int = 2) -> bytes:
    if revision not in (1, 2):
        raise ValueError("revision 1 or 2")
    retail_image = XbeImage(retail)
    edits = {va: retail_image.read(va, len(code)) for va, code in economy.WINDOWS.items()}
    for site in economy.sites():
        edits.setdefault(site.va, retail_image.read(site.va, len(site.patched)))
    edits.update(old.WINDOWS)
    edits[old.ROOKIE_TABLE_VA] = old.ROOKIE_TABLE
    edits[0x13EF17] = bytes.fromhex("c70578c2e300") + struct.pack("<I", economy.GAME_CAP)
    edits[0x4FE7A0] = struct.pack("<f", economy.CAP_GROWTH)
    edits[0x2BACCA] = bytes.fromhex("6a01")
    edits[0x247BC6] = _jump(b"\xe8", 0x247BC6, old.SYMBOLS["economy_reconcile"], 5)
    edits[0x322BB0] = _jump(b"\xe9", 0x322BB0, old.SYMBOLS["economy_fill_gate"], 6)
    edits[0x323BB3] = _jump(b"\xe9", 0x323BB3, old.SYMBOLS["economy_offer_gate"], 6)
    edits[0x322EB0] = _jump(b"\xe9", 0x322EB0, old.SYMBOLS["economy_renew_gate"], 7)
    edits[0x13ED30] = _jump(b"\xe9", 0x13ED30, old.SYMBOLS["economy_penalty"], 5)
    edits[0x13ECA0] = _jump(b"\xe9", 0x13ECA0, old.SYMBOLS["economy_cap"], 5)
    if revision == 2:
        edits[economy.VETERAN_CUT_SURPLUS] = economy.VETERAN_CUT_PATCHED
        edits[economy.ROLLOVER_DECREMENT] = economy.ROLLOVER_DECREMENT_PATCHED
    out = bytearray(retail)
    for va, code in edits.items():
        offset = retail_image.offset(va, len(code))
        out[offset:offset + len(code)] = code
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


def no_restructure_room(m, team, keep):
    """b778 fa2: give every other player of the club a one-year contract (same money this season), so the
    revision-3 restructure step finds nothing to restructure and the retail veteran cut is tested alone."""
    for i in range(m.uc.mem_read(team + 0x11C, 1)[0]):
        p = m.get(team + 4 * i)
        if p in keep:
            continue
        raw = bytearray(m.uc.mem_read(p, 84))
        if raw[0x24] & 15:
            charge = m.call(0xE6380, ecx=p) + m.call(0xE6020, ecx=struct.unpack_from("<H", raw, 10)[0],
                                                        edx=raw[0x26] >> 4, args=(raw[0x27] & 15,))
            struct.pack_into("<H", raw, 10, min((charge + 9) // 10, 65535))
            raw[0x24] = (raw[0x24] & 0xF0) | 1
            raw[0x26] = 2
            raw[0x27] = (raw[0x27] & 0xF0) | 1
            m.uc.mem_write(p, bytes(raw))

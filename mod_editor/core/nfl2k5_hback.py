"""Team depth roles over the single native fullback pool (enum 8).

H-B is a depth role, never a new position ID. All position selectors keep
their original count/getter pairs and share the FB / H-back category. The
two depth text readers return immutable records, using the selected team's
native asset ID, without modifying shared tables or saved player bytes.
"""
from __future__ import annotations

import datetime
import struct
from collections.abc import Mapping

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_modern_positions as modern
from . import nfl2k5_position_pools as pools
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm
from .nfl2k5_draft_picks import TEAMS

LEGACY_OWNER = "nfl2k5_hback"
OWNER = LEGACY_OWNER + "_spill"
SCHEMA = "2k5_mod_studio_hback/v1"
SIZE = 1024
REQUESTS = ((OWNER, "code", SIZE, 16),)
TEAM_IDS = (25, 5, 6, 3, 8, 30, 27, 0, 24, 13, 11, 7, 14, 21, 1, 18,
            12, 19, 9, 10, 4, 16, 20, 23, 2, 29, 17, 26, 22, 37, 28, 15)
MASK_OFFSET, RECORD_OFFSET, STRINGS_OFFSET = 256, 304, 384
TEXT = {"abbr": "F/H", "long": "FB / H-back", "plural": "FB / H-backs",
        "blocking": "Blocking F/H", "catching": "Catching F/H",
        "balanced": "Balanced F/H", "package": "|SQUARE| SUB F/H"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def mask_for(plan):
    require(isinstance(plan, Mapping) and plan.get("schema") == SCHEMA, "Unknown H-back schema")
    datetime.date.fromisoformat(plan["as_of"])
    rows = plan.get("teams")
    require(isinstance(rows, list) and len(rows) == 32, "All 32 team decisions are required")
    seen, mask = set(), bytearray(38)
    for row in rows:
        team = row.get("team")
        require(team in TEAMS and team not in seen, "Unknown or duplicate H-back team")
        seen.add(team)
        require(row.get("role") in ("FB", "H-B", "unconfirmed"), "Invalid backfield role")
        require(row.get("sources") and all(isinstance(s, str) and s.startswith("https://")
                                          for s in row["sources"]), "Role evidence is required")
        require(isinstance(row.get("resolution"), str) and row["resolution"].strip(), "Role resolution is required")
        mask[TEAM_IDS[TEAMS.index(team)]] = int(row["role"] == "H-B")
    return bytes(mask)


def strings(va):
    data, addresses = bytearray(), {}
    for key, value in TEXT.items():
        addresses[key] = va + STRINGS_OFFSET + len(data)
        data += (value + "\0").encode("utf-16le")
    return bytes(data), addresses


def code_for(va, table, mask):
    require(len(mask) == 38 and set(mask) <= {0, 1}, "Invalid H-back mask")
    a = _Asm(va)
    # Entry 0: the slot getter has already computed EAX. Preserve its flags
    # and every other register, returning either that record or the H-B view.
    a.b("9c52")
    a.b("3d" + struct.pack("<I", table + 2 * 0x48).hex())
    a.j8("75", "done")
    a.b("8b159c74c10085d2")
    a.j8("74", "done")
    a.b("83ba2801000000")  # NFL team kind, excludes historic/special teams
    a.j8("75", "done")
    # +118 is a WORD; +11A is the franchise index, populated at initialization.
    a.b("0fb7921801000083fa25")
    a.j8("77", "done")
    a.b("80ba" + struct.pack("<I", va + MASK_OFFSET).hex() + "01")
    a.j8("75", "done")
    a.b("b8" + struct.pack("<I", va + RECORD_OFFSET).hex())
    a.label("done")
    a.b("5a9dc3")
    first = a.assemble()
    # Entry 128: native tab-header tail call, EDX points to record+0xA.
    a = _Asm(va + 128)
    a.b("9c508d42f6")
    a.call(va)
    a.b("8d500a589d")
    a.jmp_abs(0xF3670)
    header = a.assemble()
    text, _ = strings(va)
    record = modern.slot_text("H-B", "H-BACK") + struct.pack("<II", 8, 0)
    result = (first.ljust(128, b"\xcc") + header.ljust(128, b"\xcc")
              + mask.ljust(RECORD_OFFSET - MASK_OFFSET, b"\0") + record)
    result = result.ljust(STRINGS_OFFSET, b"\0") + text
    require(len(first) <= 128 and len(header) <= 128 and len(result) <= SIZE, "H-back allocation overflow")
    return result.ljust(SIZE, b"\xcc")


def sites(va):
    _, addresses = strings(va)
    result = [("backfield category", at, struct.pack("<I", old), struct.pack("<I", addresses[key]))
              for at, old, key in POINTERS]
    for at, before, target in ((0x243AF4, bytes.fromhex("c390909090"), va),
                               (0x243E2C, bytes.fromhex("e93ff8eaff"), va + 128)):
        result.append(("team depth role", at, before, b"\xe9" + struct.pack("<i", target-at-5)))
    return result


def allocation(payload):
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] in (OWNER, LEGACY_OWNER)] if space.status(payload) == "applied" else []
    require(not rows or len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", SIZE, 16), "Foreign H-back allocation")
    return rows[0] if rows else None


def _state(payload):
    require(space.status(payload) != "foreign", "Foreign executable geometry or digest")
    require(pools.status(payload) == "applied", "Complete modern pools are required")
    table = modern.layout_table(payload)
    require(modern.read_record(payload, 0, 2) == dict(unit=0, slot=2, va=table+144,
            abbreviation="FB", long_name="FULL BACK", position=8, chain=0), "Foreign fullback slot")
    image, row = XbeImage(payload), allocation(payload)
    require(image.read(0x243AE0, 20) == bytes.fromhex("a1b874c1006bc00b03c18d04c08d04c5") + struct.pack("<I", table),
            "Foreign depth record getter")
    require(image.read(0x243E0F, 29) == bytes.fromhex("a1b874c1008b0d7874c1006bc00b03c18d14c08bce8d14d5")
            + struct.pack("<I", table + 10) + b"\x5e", "Foreign depth header reader")
    state = rdata.status(payload, sites(row["va"] if row else 0x14DA000))
    require(state in ("retail", "applied"), "Foreign backfield label sites")
    if row:
        raw = image.read(row["va"], SIZE)
        if raw == b"\xcc" * SIZE:
            require(state == "retail", "H-back hook has no implementation")
        else:
            mask = raw[MASK_OFFSET:MASK_OFFSET+38]
            require(state == "applied" and raw == code_for(row["va"], table, mask), "Foreign H-back implementation")
    else:
        require(state == "retail", "H-back hook has no allocation")
    return state, row, table


def status(payload):
    try:
        return _state(payload)[0]
    except (ValueError, KeyError, TypeError, IndexError, struct.error):
        return "foreign"


def apply(payload, plan):
    mask = mask_for(plan)
    state, row, table = _state(payload)
    before = payload
    if state == "applied":
        require(XbeImage(payload).read(row["va"] + MASK_OFFSET, 38) == mask, "A different H-back plan is installed")
        return payload, dict(owner=row["owner"], already_applied=True, changed_bytes=0)
    if row is None:
        payload, _ = space.extend_scaleout(payload, REQUESTS)
        row = allocation(payload)
    payload, _ = space.install_code(payload, row["owner"], code_for(row["va"], table, mask))
    payload, receipt = rdata.apply(payload, sites(row["va"]), row["owner"])
    require(status(payload) == "applied", "H-back installation failed readback")
    return payload, dict(receipt, owner=row["owner"], code_va=hex(row["va"]),
                         hback_teams=[r["team"] for r in plan["teams"] if r["role"] == "H-B"],
                         native_position=8, new_positions=0,
                         changed_bytes=sum(a != b for a, b in zip(before, payload)))
POINTERS = (
    (0x4F26A8, 0xE69C20, 'abbr'),
    (0x4F26F0, 0xE69C20, 'abbr'),
    (0x4F2738, 0xE69D18, 'long'),
    (0x4F2780, 0xE69EBC, 'plural'),
    (0x4F6924, 0xE6C288, 'abbr'),
    (0x520F14, 0xE98708, 'plural'),
    (0x538D50, 0xEA402C, 'plural'),
    (0x539B18, 0xEA402C, 'plural'),
    (0x53A7C0, 0xEA402C, 'plural'),
    (0x53D400, 0xEA4420, 'plural'),
    (0x53F060, 0xEA4660, 'plural'),
    (0x5492B8, 0xEA9AC8, 'plural'),
    (0x5504C8, 0xEAB358, 'plural'),
    (0x551CA8, 0xEAB56C, 'plural'),
    (0x553AF8, 0xEAB8F8, 'plural'),
    (0x555B00, 0xEABCAC, 'long'),
    (0x556C98, 0xEAC654, 'blocking'),
    (0x556D0C, 0xEAC66C, 'catching'),
    (0x556D80, 0xEAC684, 'balanced'),
    (0x557E88, 0xEAD380, 'long'),
    (0x5588C0, 0xEAD97C, 'plural'),
    (0x55E7E0, 0xEAE7EC, 'plural'),
    (0x5701F0, 0xEAF47C, 'plural'),
    (0x57F230, 0xEB39FC, 'plural'),
    (0x581B18, 0xEB5758, 'plural'),
    (0x587570, 0xEBBEF8, 'plural'),
    (0xA8990C, 0xE67690, 'package'),
    (0xAAB7A8, 0xE83C1C, 'long'),
    (0xAAB7F8, 0xE83D54, 'abbr'),
    (0xAC2694, 0xE87EC8, 'abbr'),
)

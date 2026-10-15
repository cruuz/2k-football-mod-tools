"""Seed the two native pick banks at NEW franchise initialization only.

Each bank is seven rounds of 32 owner bytes, indexed by original club. The
first bank is the draft following the starting season, the second is one year
later. Native trading, draft ordering, serialization and annual rollover remain
untouched. Conditional obligations must be resolved explicitly by the data
author: the game stores owners, not real-world trade conditions.
"""
from __future__ import annotations

import datetime
import hashlib
import struct
from collections.abc import Mapping

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_season_length as season
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_draft_picks"
SCHEMA = "2k5_mod_studio_draft_picks/v1"
TEAMS = tuple("SF CHI CIN BUF DEN CLE TB ARI LAC KC IND DAL MIA PHI ATL NYG JAX NYJ DET GB CAR NE LV LAR BAL WAS NO SEA PIT HOU TEN MIN".split())
CODE_SIZE = 544
TABLE_OFFSET = 96
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BANK = 0xE3C0B4
SITE = 0x13EF89
ORIGINAL = bytes.fromhex("bf611fe500")
GUARDS = (
    ("initialization", 0x13EF60, 0x33, "7747045499586b3703869fad57302d1705d72964c160328b1d1a206967b4b26d"),
    ("annual rollover", 0x31E430, 0x150, "f865ca49ce15a61317aee68313d51b51f18e0e0b424c64c95d7b49d26cc43414"),
    ("draft owner lookup", 0x3254D0, 0x20, "77a2842feb19a62d33dbd0cc986949386b11989aec4bc855b9a9b555c62dd8ac"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def table_for(plan):
    """Require all 448 unique identities, with explicit evidence and resolution."""
    require(isinstance(plan, Mapping) and plan.get("schema") == SCHEMA, "Unsupported draft-pick schema")
    year = plan.get("base_season")
    require(type(year) is int and 2004 <= year <= 2098, "Invalid starting season")
    datetime.date.fromisoformat(plan["as_of"])
    rows = plan.get("picks")
    require(isinstance(rows, list) and len(rows) == 448, "Exactly 448 picks are required")
    table = bytearray([255] * 448)
    for row in rows:
        y, r = row.get("year"), row.get("round")
        require(type(y) is int and y in (year + 1, year + 2), "Pick year must follow the starting season")
        require(type(r) is int and 1 <= r <= 7, "Invalid pick round")
        require(row.get("original_team") in TEAMS and row.get("owner") in TEAMS, "Unknown pick team")
        require(row.get("status") in ("confirmed", "retained", "conditional_projection", "unconfirmed"), "Missing ownership status")
        require(isinstance(row.get("sources"), list) and row["sources"]
                and all(isinstance(s, str) and s.startswith("https://") for s in row["sources"]), "Pick sources required")
        require(isinstance(row.get("resolution"), str) and row["resolution"].strip(), "Pick resolution required")
        at = (y - year - 1) * 224 + (r - 1) * 32 + TEAMS.index(row["original_team"])
        require(table[at] == 255, "Duplicate pick identity")
        table[at] = TEAMS.index(row["owner"])
    require(255 not in table, "Incomplete pick table")
    return bytes(table)


def code_for(va, table):
    require(len(table) == 448 and max(table) < 32, "Invalid owner table")
    # Preserve flags and all registers. The overwritten MOV executes on either
    # path. Runtime mode guard is additional to the pinned new-franchise site.
    code = bytearray.fromhex("9c60833da076e500027512fcbe")
    code += struct.pack("<I", va + TABLE_OFFSET)
    code += b"\xbf" + struct.pack("<I", BANK)
    code += b"\xb9" + struct.pack("<I", 112) + b"\xf3\xa5"
    code += b"\x61\x9d" + ORIGINAL + b"\xc3"
    require(len(code) <= TABLE_OFFSET, "Draft initializer exceeds its budget")
    return bytes(code).ljust(TABLE_OFFSET, b"\xcc") + table


def sites(va):
    return [("new franchise pick owners", SITE, ORIGINAL, b"\xe8" + struct.pack("<i", va - SITE - 5))]


def allocation(payload):
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return None
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) == ("code", CODE_SIZE, 16), "Foreign draft-pick allocation")
    return rows[0]


def _state(payload):
    require(space.status(payload) != "foreign", "Foreign executable geometry or digest")
    image = XbeImage(payload)
    row = allocation(payload)
    edits = sites(row["va"] if row else 0x14DA000)
    state = rdata.status(payload, edits)
    require(state in ("retail", "applied"), "Foreign initialization site")
    for name, va, length, digest in GUARDS:
        raw = bytearray(image.read(va, length))
        if va <= SITE < va + length:
            raw[SITE - va:SITE - va + 5] = ORIGINAL
        require(hashlib.sha256(raw).hexdigest() == digest, "Foreign draft dependency: " + name)
    if row:
        raw = image.read(row["va"], CODE_SIZE)
        if raw == b"\xcc" * CODE_SIZE:
            require(state == "retail", "Hook without installed initializer")
        else:
            table = raw[TABLE_OFFSET:]
            require(state == "applied" and raw == code_for(row["va"], table), "Foreign draft initializer")
    else:
        require(state == "retail", "Hook without allocation")
    return state, row


def status(payload):
    try:
        return _state(payload)[0]
    except (ValueError, KeyError, TypeError, IndexError, struct.error):
        return "foreign"


def apply(payload, plan):
    table = table_for(plan)
    require(season.read_year(payload) == plan["base_season"], "Draft years disagree with the executable's starting season")
    state, row = _state(payload)
    before = payload
    if state == "applied":
        require(XbeImage(payload).read(row["va"] + TABLE_OFFSET, 448) == table, "A different ownership table is already installed")
        return payload, dict(owner=OWNER, already_applied=True, changed_bytes=0)
    if row is None:
        payload, _ = (space.apply(payload, REQUESTS, scaleout=True) if space.status(payload) == "retail"
                      else space.extend_scaleout(payload, REQUESTS))
        row = allocation(payload)
    payload, _ = space.install_code(payload, OWNER, code_for(row["va"], table))
    payload, _ = rdata.apply(payload, sites(row["va"]), OWNER)
    require(status(payload) == "applied", "Draft initializer failed readback")
    return payload, dict(owner=OWNER, already_applied=False,
                         changed_bytes=sum(a != b for a, b in zip(before, payload)) + abs(len(before) - len(payload)),
                         code_va=hex(row["va"]), table_sha256=hashlib.sha256(table).hexdigest(),
                         years=[plan["base_season"] + 1, plan["base_season"] + 2],
                         picks=448, transferred=sum(row["owner"] != row["original_team"] for row in plan["picks"]))

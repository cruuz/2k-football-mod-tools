"""Pass rush stats: pressures, QB hits, and pressures / QB hits / sacks allowed, plus targets on the Player Card.

EXPERIMENTAL. Noah (2026-10-28): "we should include pressures as a stat, targets for receivers if they're not
already there... offensive linemen should show like pressures given up and QB hits allowed and then sacks
allowed... defensive players should have a new stat for pressures, QB hits."

What the retail game has (static RE of the USA ``default.xbe``, job b779 st1 report)
-------------------------------------------------------------------------------------
* Targets already exist: selector 56 "Thrown To" (live receiver block, getter 0xCAA90) is merged by the post-game
  sum table at 0x4FC528 into history field 50 for receivers in played and simulated games, and League Leaders
  show it (TT, descriptor 0x544E78). Only the Player Card lacks it, so this owner adds a TGT column.
* "Hurries" (selector 21) is a QB-side live count, never merged and never credited to a defender. There are no
  QB hits, pressures or allowed stats, and the offensive line's card (0x320C44: C, G, T use screen 6,
  0x536CB8) has no stats sheet at all.

What this owner adds
--------------------
Definitions (PFR / Sports Info Solutions charting): a hurry is a throw made under pressure, a knockdown (QB hit)
is contact on or after the throw, a sack is the native sack, and pressures = hurries + knockdowns + sacks. QB hits
follow the NFL's official count, which includes sacks (nflverse ``def_qb_hits``). In played games a defender
within 2 yards of the passer at the release gets a pressure (within 1 yard also a QB hit); the sacker gets a
pressure and a QB hit; the blocker each of them beat on that play (the engaged-block tick 0x233040 returning
"shed") gets the matching pressure / QB hit / sack allowed. Simulated games draw the same stats from NFL per-game
rates driven by Pass Rush and Pass Blocking and the engine's own sacks. History fields (player+0x2C stream):
106 pressures, 107 QB hits, 108 pressures allowed, 109 QB hits allowed, 110 sacks allowed.

Player Card: TGT on the HB/FB and WR/TE sheets, PRS and QBH after SACK on the defensive sheet, and a new
offensive-line sheet (Games, PA, HA, SA) by routing C/G/T to the defensive card definition and switching the
sheet's column list at the card's own selector. The column lists are copies in the owner's read-only block; the
retail lists (and the TEAM column's in-place edits) are untouched. Fields 106-110 fold by sum when the honors
owner is installed (its fold rule covers fields 96-127).
"""

from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_pass_rush_stats_code as runtime

OWNER = "nfl2k5_pass_rush_stats"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 3328
READ_ONLY_SIZE = 2304
DATA_SIZE = 1152
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "read_only", READ_ONLY_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))

BUILD_CAPTION = "Pass rush stats: pressures, QB hits, allowed stats, targets (experimental)"
HELP_TEXT = ("EXPERIMENTAL. Adds pressures and QB hits for defenders, pressures, QB hits and sacks allowed for "
             "offensive linemen, and shows targets for receivers. Played games count them on the field (a "
             "defender within 2 yards of the passer at the throw, the sacker, and the blocker he beat); simulated "
             "games draw them from NFL rates using Pass Rush and Pass Blocking. The Player Card shows TGT for "
             "backs and receivers, PRS and QBH for defenders and a new PA / HA / SA sheet for linemen. Each value "
             "is saved in the player's season history (about 1,300 more history words per franchise season).")

FIELD0 = 106
STATS = ("pressures", "qb_hits", "pressures_allowed", "qb_hits_allowed", "sacks_allowed")
FIELDS = {name: FIELD0 + i for i, name in enumerate(STATS)}
TARGETS_SELECTOR = 0x38           # selector 56 "Thrown To" -> history field 50 (retail)
TARGETS_FIELD = 50

# Live per-game counters for other jobs (pr1): RW block of this owner, State layout of runtime.c.
STATE_COUNTERS_OFF = 0x24         # u8 cnt[136][5], index = play-log player code (0xBBAA0), order PRS QBH PA HA SA
STATE_DIAGNOSTICS = ("live", "throws", "sacks", "sheds", "credits", "last_defenders", "last_min_mm", "commits", "rng")
NCODE, NSTAT = 136, 5
STATE_SIZE = 4 * len(STATE_DIAGNOSTICS) + NCODE * NSTAT + NCODE + 2 * NCODE

# Tunables: (label, value). The template holds the same values; code_for() writes these.
# Positions are in centimetres (91.44 a yard: 210 uses of 91.44 in the retail XBE; xemu RAM of prsA2/prsA3).
TUNING = (("prs_hurry_mm2", 182.88 ** 2), ("prs_hit_mm2", 91.44 ** 2), ("prs_rush_share", 0.71),
          ("prs_hit_share", 0.53), ("prs_ol_per_game", 4.3), ("prs_ol_hit_share", 0.45),
          ("prs_ol_sack_share", 0.60))

# (label, VA, retail bytes, entry label, kind) - kind "call" = call rel32, "jmp" = jmp rel32 + NOP padding
SITE_TABLE = (
    ("shed", 0x0023477A, bytes.fromhex("6a006a006a0356"), "prs_shed", "jmp"),
    ("throw", 0x002DB2CA, bytes.fromhex("e841fcffff"), "prs_throw", "call"),
    ("sack_log", 0x000CE32A, bytes.fromhex("e831deffff"), "prs_sack1", "call"),
    ("sack_log_entry", 0x000CE2A4, bytes.fromhex("e847dfffff"), "prs_sack2", "call"),
    ("commit", 0x00134E1F, bytes.fromhex("6a00ba4c000000"), "prs_commit", "jmp"),
    ("reset_played", 0x000A78EF, bytes.fromhex("e80c550200"), "prs_reset1", "call"),
    ("reset_simulated", 0x0010B427, bytes.fromhex("e8d419fcff"), "prs_reset2", "call"),
)
# 0x320C28[i]: the card's screen entries this owner takes over (label, entry VA, retail target, stub label)
CARD_JUMPS = (("card_wr", 0x00320C34, 0x00320BD2, "prs_card_wr"),
              ("card_def", 0x00320C38, 0x00320BE3, "prs_card_def"),
              ("card_rb", 0x00320C3C, 0x00320BC1, "prs_card_rb"))
CARD_POSITION_TABLE = 0x00320C44  # 17 bytes, position -> screen index; C, G, T (12..14) retail 6
OL_POSITIONS = (12, 13, 14)
# the sheets' column-list pointer fields (.rdata, runtime writable; the stubs write them when a card opens) and
# their retail lists. defensive_try's card hook writes all six fields at the selector's entry; ours run later.
LIST_FIELDS = {"rb": (0x0053582C, 0x00535258), "wr": (0x0053592C, 0x00535320), "def": (0x00535A2C, 0x005353E8)}
LIST_SIZE, LIST_POINTERS_OFF, LIST_SLOTS = 0xD8, 0x9C, 15
LIST_STRIDE = 0xE0                # 0x9C header + up to 15 pointers + a zero dword
DT_LIST_INDEX = {"rb": 1, "wr": 2, "def": 3}   # defensive_try's six cloned lists: QB, RB, WR, DEF, K, P
YR, GAMES, REC, SACK = 0x00535020, 0x005350D0, 0x00533CE0, 0x00534050
TEAM_DESCRIPTOR = 0x00047370      # nfl2k5_team_column.DESCRIPTOR_VA (kept if present in a list)
DESCRIPTOR_SIZE = 0xB0
CARD_GETTER = 0x00320430
# new columns: (key, abbreviation, long name, stat id)
COLUMNS = (("tgt", "TGT", "Targets", TARGETS_SELECTOR),
           ("prs", "PRS", "Pressures", FIELDS["pressures"]),
           ("qbh", "QBH", "QB Hits", FIELDS["qb_hits"]),
           ("pa", "PA", "Pressures Allowed", FIELDS["pressures_allowed"]),
           ("ha", "HA", "QB Hits Allowed", FIELDS["qb_hits_allowed"]),
           ("sa", "SA", "Sacks Allowed", FIELDS["sacks_allowed"]))

# Retail spans the runtime calls into or relies on, pinned by SHA-256 of their retail bytes (spans avoid every
# byte another owner edits: team column 0x134E0A, weekly progression 0x134E05, pass protection 0x233162,
# QB accuracy 0x2DAF10+0x190, honors 0x14F168).
GUARDS = (
    ("live code", 0x000BBAA0, 0x58), ("live arrays", 0x00061B60, 0x16), ("live next", 0x00061B90, 0x20),
    ("stage", 0x000C4BB0, 0x10), ("class set", 0x0014EDB0, 0x7), ("history get", 0x0014EE40, 0x1F),
("history ago", 0x0014EF20, 0x40), ("history set", 0x0014F430, 0x17),
    ("sacker", 0x000D2C20, 0x14), ("sack writers", 0x000CC160, 0xCE), ("play log reset", 0x000CCE00, 0x34),
    ("shed caller", 0x00234725, 0x6A), ("release call", 0x002DB2B0, 0x23), ("sack branches", 0x000CE29C, 0xA3),
    ("commit tail", 0x00134E11, 0x1F), ("card selector", 0x00320B95, 0xC0), ("card getter", 0x00320430, 0x2C),
)

GUARD_SHA256_PINNED = {
    "live code": "cff8e37c309bcd7591a790e627fa90435365161736a1ae5460511ddb1f5de27f",
    "live arrays": "347de136b17b08efb5206b0415188dc8efad2f58c125d923c105ad65b75dd5ee",
    "live next": "faa90367a2072a3eea71a9318233475beee234180063d22304f2b1d0806286be",
    "stage": "da7b8f9d35c4c885e4ac9ea571ea84d93c2dbf01f796788c36bc930c4f4a6111",
    "class set": "d865ebcc76568491ae0bd0c5d7759826052fed67e74abe915e831d299326bef6",
    "history get": "fc126037b6c785bd0575f57a96d322c442e7e6786cab43d75368c4d3a4a4ccd3",
    "history ago": "795a4ff7527d7110297f24037cd41050a221155399e3ef33abaa8126d6ef4922",
    "history set": "c50c4461b01c36f097954be45394d9aaec9804b89a26d32584689153ecd02151",
    "sacker": "3d8b3abb91b34bcc3345542637cf0698c659dd261e029485d872063e9b000023",
    "sack writers": "583bbb089eacfd5346b1ab235c7938b3cc7294528523883ca0b6a6cab2e97ae8",
    "play log reset": "54e31ed95213c9a526c55c86542414a1a1dcf6a0f24a70eabe8be5c8cc87bb67",
    "shed caller": "e5dcd785a744456367183b3d170c81819f05a69e3d6935bd8595791fdaf3bb1f",
    "release call": "46b8903fa8eae4ab8d66f2ae314684f43be1e1de5b2d0fd28a122296b9f31b19",
    "sack branches": "cb9fcce380c1efd97a8686e8c4b21c4f2eec02d11fb6bf2847801245ea2f554e",
    "commit tail": "f350723032751912322c54d32afb1242e4fe5157a4e4b1a5845acd73f5d898fb",
    "card selector": "d907c98b2980b2b6d62b9fea93fdb90ead22e13dccd2b0a6c51cb15b761ccfbf",
    "card getter": "ac219e0b1b91c514ee1b0f58898e33ac9b211048592ca5455f917f1c8b577155",
}


class PassRushStatsError(ValueError):
    pass


def _require(ok, message):
    if not ok:
        raise PassRushStatsError(message)


def labels(code_va):
    return {name: code_va + off for name, off in runtime.LABELS.items()}


def code_for(code_va, data_va, read_only_va):
    symbols = {"code": code_va, "state": data_va}
    out = bytearray(runtime.CODE)
    for off, kind, symbol, value in runtime.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<i", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    for label, value in TUNING:
        struct.pack_into("<f", out, runtime.LABELS[label], value)
    lay = read_only_layout(read_only_va)
    for key in ("rb", "wr", "def", "ol"):
        struct.pack_into("<I", out, runtime.LABELS["prs_list_" + key], lay["list_" + key])
    _require(len(out) <= CODE_SIZE, "the pass rush runtime exceeds its fixed budget")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def _utf16(text):
    return text.encode("utf-16-le") + b"\0\0"


def read_only_layout(read_only_va):
    """VA of every object in the read-only block: strings, the six descriptors, the four column lists."""
    at = read_only_va
    out = {}
    for key, abbr, long_name, _sid in COLUMNS:
        out["s_" + key] = at
        at += len(_utf16(abbr))
        out["l_" + key] = at
        at += len(_utf16(long_name))
    at = (at + 15) & ~15
    for key, *_rest in COLUMNS:
        out["d_" + key] = at
        at += DESCRIPTOR_SIZE
    for key in ("rb", "wr", "def", "ol"):
        out["list_" + key] = at
        at += LIST_STRIDE
    out["end"] = at
    _require(at - read_only_va <= READ_ONLY_SIZE, "the pass rush read-only block exceeds its budget")
    return out


def _descriptor(template, getter, abbr_va, long_va, stat_id):
    d = bytearray(template)
    _require(struct.unpack_from("<I", d, 0x00)[0] == 4 and struct.unpack_from("<I", d, 0x0C)[0] == 0x200B3,
             "the REC column descriptor is not the retail integer stat column")
    for off in (0x68, 0x80, 0x98):
        _require(struct.unpack_from("<II", d, off) == (0x0027CCD0, 0x10000), "column descriptor text shape")
    struct.pack_into("<I", d, 0x08, getter)
    struct.pack_into("<I", d, 0x70, abbr_va)
    struct.pack_into("<I", d, 0x88, long_va)
    struct.pack_into("<I", d, 0xA0, stat_id)
    return bytes(d)


def _list_pointers(raw):
    words = list(struct.unpack_from(f"<{LIST_SLOTS}I", raw, LIST_POINTERS_OFF)) + [0]
    out = []
    for w in words:
        if not w:
            break
        out.append(w)
    return out


def _spliced(pointers, key, lay):
    p = list(pointers)
    if key in ("rb", "wr"):
        _require(REC in p, "the receiving column is missing from a back/receiver list")
        p.insert(p.index(REC), lay["d_tgt"])
    elif key == "def":
        _require(SACK in p, "the sack column is missing from the defensive list")
        i = p.index(SACK) + 1
        p[i:i] = [lay["d_prs"], lay["d_qbh"]]
    _require(len(p) < LIST_SLOTS, "a column list is full")
    return p


def _ol_pointers(def_pointers, lay):
    p = [YR]
    if len(def_pointers) > 1 and def_pointers[1] == TEAM_DESCRIPTOR:
        p.append(TEAM_DESCRIPTOR)
    p += [GAMES, lay["d_pa"], lay["d_ha"], lay["d_sa"]]
    return p


def _list_copy(raw, pointers):
    out = bytearray(raw[:LIST_POINTERS_OFF]) + bytes(LIST_STRIDE - LIST_POINTERS_OFF)
    struct.pack_into(f"<{LIST_SLOTS}I", out, LIST_POINTERS_OFF, *(list(pointers) + [0] * (LIST_SLOTS - len(pointers))))
    return bytes(out)


def source_lists(payload):
    """The column lists a card shows before this owner: defensive_try's clones (the TEAM variant when the TEAM
    column is installed) when that owner is applied, else the retail list structs (with TEAM's in-place column)."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    vas = {k: v[1] for k, v in LIST_FIELDS.items()}
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == "nfl2k5_defensive_try_stats"
            and r["kind"] == "read_only"] if space.status(payload) != "retail" else []
    if rows:
        from . import nfl2k5_defensive_try as dt, nfl2k5_team_column as tc
        _require(dt.status(payload) == "applied", "defensive try stats are allocated but not applied")
        table, lists = dt.stat_tables(payload, rows[0]["va"])
        _require(image.read(rows[0]["va"], len(table)) == table, "foreign defensive try card tables")
        variant = lists[1 if tc.status(payload) == "applied" else 0]
        vas = {k: variant[i] for k, i in DT_LIST_INDEX.items()}
    return {k: image.read(va, LIST_POINTERS_OFF + 4 * LIST_SLOTS) for k, va in vas.items()}


def read_only_bytes(image, code_va, read_only_va, source_lists):
    """The read-only block: strings, the six column descriptors and the four spliced column lists."""
    lay = read_only_layout(read_only_va)
    buf = bytearray(READ_ONLY_SIZE)

    def put(va, data):
        o = va - read_only_va
        buf[o:o + len(data)] = data

    for key, abbr, long_name, _sid in COLUMNS:
        put(lay["s_" + key], _utf16(abbr))
        put(lay["l_" + key], _utf16(long_name))
    template = image.read(REC, DESCRIPTOR_SIZE)
    getter = labels(code_va)["prs_card_value"]
    for key, _abbr, _long, sid in COLUMNS:
        put(lay["d_" + key], _descriptor(template, CARD_GETTER if key == "tgt" else getter,
                                         lay["s_" + key], lay["l_" + key], sid))
    lists = source_lists
    def_pointers = _list_pointers(lists["def"])
    for key in ("rb", "wr", "def"):
        put(lay["list_" + key], _list_copy(lists[key], _spliced(_list_pointers(lists[key]), key, lay)))
    put(lay["list_ol"], _list_copy(lists["def"], _ol_pointers(def_pointers, lay)))
    return bytes(buf)


def sites(code_va):
    """Every code edit as (label, VA, retail bytes, patched bytes)."""
    at = labels(code_va)
    out = []
    for label, va, before, entry, kind in SITE_TABLE:
        op = b"\xe9" if kind == "jmp" else b"\xe8"
        after = op + struct.pack("<i", at[entry] - (va + 5))
        after += b"\x90" * (len(before) - len(after))
        out.append((label, va, before, after))
    return out


def data_edits(code_va):
    """The table edits in .text: (label, VA, retail bytes, patched bytes)."""
    at = labels(code_va)
    out = [(label, va, struct.pack("<I", retail), struct.pack("<I", at[stub])) for label, va, retail, stub in CARD_JUMPS]
    out.append(("card_ol_screens", CARD_POSITION_TABLE + OL_POSITIONS[0], bytes([6, 6, 6]), bytes([4, 4, 4])))
    return out


def _allocation(payload, kind):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER and r["kind"] == kind]
    return rows[0] if len(rows) == 1 else None


def allocations(payload):
    rows = {k: _allocation(payload, k) for k in ("code", "read_only", "data")}
    sizes = {"code": CODE_SIZE, "read_only": READ_ONLY_SIZE, "data": DATA_SIZE}
    for k, r in rows.items():
        _require(r is not None and r["size"] == sizes[k], "missing or foreign pass rush allocation")
    return rows


def _guard_digest(image, va, size):
    content = bytearray(image.read(va, size))
    # mask this owner's own edits back to retail
    for label, sva, before, _e, _k in SITE_TABLE:
        for i, b in enumerate(before):
            if va <= sva + i < va + size:
                content[sva + i - va] = b
    for _label, jva, retail, _stub in CARD_JUMPS:
        for i, b in enumerate(struct.pack("<I", retail)):
            if va <= jva + i < va + size:
                content[jva + i - va] = b
    for i, pos in enumerate(OL_POSITIONS):
        a = CARD_POSITION_TABLE + pos
        if va <= a < va + size:
            content[a - va] = 6
    return hashlib.sha256(bytes(content)).hexdigest()


def guard_digests(payload):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    return {label: _guard_digest(image, va, size) for label, va, size in GUARDS}


def _check_guards(image):
    for label, va, size in GUARDS:
        _require(_guard_digest(image, va, size) == GUARD_SHA256_PINNED[label], f"pass rush dependency changed: {label}")


def _recognize(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    _check_guards(image)
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]) if space.status(payload) != "retail" else False
    rows = allocations(payload) if present else None
    code_va = rows["code"]["va"] if rows else 0
    ro_va = rows["read_only"]["va"] if rows else 0
    states = set()
    for _l, va, before, after in sites(code_va):
        got = image.read(va, len(before))
        states.add("retail" if got == before else "applied" if rows and got == after else "foreign")
    for _l, va, before, after in data_edits(code_va):
        got = image.read(va, len(before))
        states.add("retail" if got == before else "applied" if rows and got == after else "foreign")
    if rows:
        code = image.read(code_va, CODE_SIZE)
        states.add("retail" if code == b"\xcc" * CODE_SIZE else
                   "applied" if code == code_for(code_va, rows["data"]["va"], ro_va) else "foreign")
        ro = image.read(ro_va, READ_ONLY_SIZE)
        if ro != bytes(READ_ONLY_SIZE):
            states.add("applied" if ro == read_only_bytes(image, code_va, ro_va, source_lists(payload)) else "foreign")
    _require(states in ({"retail"}, {"applied"}), "foreign or mixed pass rush stats bytes")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, OSError):
        return "foreign"


def apply(payload):
    """Install, or replay an identical installation. Needs a sealed scale-out image or retail."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = status(payload)
    _require(state != "foreign", "the source executable is not retail or pass rush stats")
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, fields=dict(FIELDS),
                  targets_field=TARGETS_FIELD)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    before = payload
    allocation_receipt = {}
    if not any(r["owner"] == OWNER for r in (space.layout(payload)["allocations"] if space.status(payload) != "retail" else [])):
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
        else:
            _require(space.is_scaleout(payload), "pass rush stats needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
    rows = allocations(payload)
    code_va, ro_va, data_va = rows["code"]["va"], rows["read_only"]["va"], rows["data"]["va"]
    image = XbeImage(payload)
    ro = read_only_bytes(image, code_va, ro_va, source_lists(payload))
    payload, _ = space.install_code(payload, OWNER, code_for(code_va, data_va, ro_va))
    payload, _ = space.install_read_only(payload, OWNER, ro)
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = []
    for label, va, old, new in sites(code_va) + data_edits(code_va):
        off = image.offset(va, len(old))
        _require(bytes(buf[off:off + len(old)]) == old, f"pass rush site {va:#x} is not retail")
        buf[off:off + len(new)] = new
        edits.append(dict(label=label, va=hex(va), before=old.hex(), after=new.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(_recognize(result) == "applied" and space.status(result) == "applied", "pass rush postcondition failed")
    return result, dict(common, status="applied", code_va=hex(code_va), read_only_va=hex(ro_va), data_va=hex(data_va),
                        counters_va=hex(data_va + STATE_COUNTERS_OFF),
                        before_sha256=hashlib.sha256(before).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest(),
                        changed_bytes=space.count_differing_bytes(before, result),
                        file_growth=len(result) - len(before), allocation=allocation_receipt, edits=edits,
                        reservations=[r for r in space.reservations(result) if r["owner"] == OWNER])



__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "READ_ONLY_SIZE", "DATA_SIZE", "FIELDS", "FIELD0", "STATS",
           "TARGETS_FIELD", "TARGETS_SELECTOR", "BUILD_CAPTION", "HELP_TEXT", "SITE_TABLE", "GUARDS", "TUNING",
           "code_for", "read_only_bytes", "read_only_layout", "sites", "data_edits", "allocations", "status", "apply",
           "guard_digests", "PassRushStatsError", "STATE_COUNTERS_OFF", "STATE_SIZE"]

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
retail lists (and the TEAM column's in-place edits) are untouched.

League Leaders and the stats sheets (Noah 10/28: "new stats yes"): the blocked-kick columns (FBK field goal blocks, XBK extra
point blocks, PBK punt blocks) give their slots to PRS, QBH and SA in place; every other column is unchanged. The new
columns are integer stat columns cloned from FBK (cookie 0x307BA) with this owner's getter in place of 0x3216C0. Fields 106-110 fold by sum when the honors
owner is installed (its fold rule covers fields 96-127).

b780 b5-sim (SWeaR 11/01: "the league leader in the new pressure stat only seems to be getting like 30 pressures max when
simming"; "add a category for offensive lineman in League Leaders that tracks their sacks allowed and pressure allowed"):
* The sheets pick and rank their rows with the native getters 0x3216A0 ("has this stat", League Leaders' filter 0x321CEC) and
  0x3216C0 (the sort value, League Leaders' builder 0x321D40 at 0x321DE6), keyed by the column's stat id. Ids 106-110 fell
  to native selectors 106-110, which have no history field, so a PRS sort kept the top 40 by the category's qualifier
  (tackles) and showed the best pass rusher among the top tacklers. Both getters now send ids 106-110 to this owner's
  reader (hooks at their first instruction), so the rows are the real leaders.
* League Leaders' Defense tab is a copy of the retail tab (same header, same default sort) with FBK back in its place and
  PRS and QBH added at the end; a new eighth tab, Offensive Line, lists # NAME TEAM PA HA SA. The tab list of the League
  Leaders spreadsheet (0x54A13C, null-terminated, read by the spreadsheet's own walker 0x174D00) takes the new tab in its
  old terminator slot 0x54A158; the next word (0x54A15C, alignment padding) is the new terminator. The new tab uses the
  Special Teams header (filter index 6: any player with a value in one of the tab's columns), so only linemen appear.
* Simulated draws moved from PFR's charting level to PFF's (the counts players quote): prs_rush_share 0.71 -> 1.2, QB hits
  kept at the NFL's official level (prs_hit_share 0.53 -> 0.33), interior linemen 0.15 + 1.80 -> 0.20 + 2.40, the line's
  charge 4.3 -> 6.8 a game, line QB hits 0.45 -> 0.33, line sacks 60% -> 40% of the team's sacks (worst linemen
  about 45-55 pressures and 12-15 sacks allowed a 17-game season, PFF's range).
"""

from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_pass_rush_stats_code as runtime

OWNER = "nfl2k5_pass_rush_stats"
EVIDENCE = "EXPERIMENTAL"
CODE_SIZE = 3328
READ_ONLY_SIZE = 3584
DATA_SIZE = 1152
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "read_only", READ_ONLY_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))

BUILD_CAPTION = "Pass rush stats: pressures, QB hits, targets (experimental)"
HELP_TEXT = ("EXPERIMENTAL. Adds pressures and QB hits for defenders, pressures, QB hits and sacks allowed for "
             "offensive linemen, and shows targets for receivers. Played games count them on the field (a "
             "defender within 2 yards of the passer at the throw, the sacker, and the blocker he beat); simulated "
             "games draw them from NFL rates using Pass Rush and Pass Blocking. The Player Card shows TGT for "
             "backs and receivers, PRS and QBH for defenders and a new PA / HA / SA sheet for linemen; League "
             "Leaders rank by them: the Defense tab adds PRS and QBH and a new Offensive Line tab shows PA, HA and SA. "
             "Simulated games draw at the level of PFF's pressure counts (league leaders about 80 to 95 a season), "
             "with QB hits at the NFL's official level. Each value is saved in the player's season history (about "
             "1,300 more history words per franchise season).")

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
# b780 b5-sim: simulated draws at PFF's level (2023 Hutchinson 101, Parsons and Bosa over 100; 2024 Garrett and
# Hendrickson 83, Greenard 80, Verse 77, tenth about 63), QB hits at the official level (nflverse def_qb_hits leaders
# 36-47); calibrated on two simulated seasons (sim/calib_prs.py, calib_ol.py in the b5-sim scratch).
TUNING = (("prs_hurry_mm2", 182.88 ** 2), ("prs_hit_mm2", 91.44 ** 2), ("prs_rush_share", 1.2),
          ("prs_hit_share", 0.33), ("prs_ol_per_game", 6.8), ("prs_ol_hit_share", 0.33),
          ("prs_ol_sack_share", 0.40))

# (label, VA, retail bytes, entry label, kind) - kind "call" = call rel32, "jmp" = jmp rel32 + NOP padding
SITE_TABLE = (
    ("shed", 0x0023477A, bytes.fromhex("6a006a006a0356"), "prs_shed", "jmp"),
    ("throw", 0x002DB2CA, bytes.fromhex("e841fcffff"), "prs_throw", "call"),
    ("sack_log", 0x000CE32A, bytes.fromhex("e831deffff"), "prs_sack1", "call"),
    ("sack_log_entry", 0x000CE2A4, bytes.fromhex("e847dfffff"), "prs_sack2", "call"),
    ("commit", 0x00134E1F, bytes.fromhex("6a00ba4c000000"), "prs_commit", "jmp"),
    ("reset_played", 0x000A78EF, bytes.fromhex("e80c550200"), "prs_reset1", "call"),
    ("reset_simulated", 0x0010B427, bytes.fromhex("e8d419fcff"), "prs_reset2", "call"),
    # b780 b5-sim: the stats sheets' row pickers ("cmp edx, 0xE9" at each entry), ids 106-110 to this owner's reader
    ("leaders_filter", 0x003216A0, bytes.fromhex("81fae9000000"), "prs_leader_a", "jmp"),
    ("leaders_sort", 0x003216C0, bytes.fromhex("81fae9000000"), "prs_leader_c", "jmp"),
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
# League Leaders / stats sheets (Noah 10/28: "new stats yes"): the blocked-kick columns give their slots to the new
# stats in place. (slot VA, retail descriptor, new column). Lists: 0x547C2C, 0x548224, 0x548E6C (defense; FBK only) and
# 0x548854 (defense with TEAM; FBK, XBK, PBK). Every other pointer of every list is unchanged.
FBK, XBK, PBK = 0x00545AD8, 0x00545B88, 0x00545C38
LEADER_SLOTS = ((0x00547C6C, FBK, "prs"), (0x00548268, FBK, "prs"), (0x00548EAC, FBK, "prs"),
                (0x005488A0, FBK, "prs"), (0x005488A4, XBK, "qbh"), (0x005488A8, PBK, "sa"))
LEADER_KEYS = ("prs", "qbh", "sa")
LEADER_GETTER = 0x003216C0
# b780 b5-sim: League Leaders tabs. The spreadsheet's null-terminated tab list, its Defense entry and the old terminator,
# the retail Defense tab (0x9C header + 18 columns), the Special Teams tab (its header, filter index 6, is the new
# tab's), the retail Defense columns, and the new tab's columns. The tab's default-sort list is [column, -999].
LEADER_TABS = 0x0054A13C
DEFENSE_TAB_SLOT, NEW_TAB_SLOT, TABS_TERMINATOR = 0x0054A148, 0x0054A158, 0x0054A15C
DEFENSE_TAB, SPECIAL_TEAMS_TAB = 0x00548188, 0x00548438
TAB_HEADER = 0x9C
TAB_TITLE_OFF, TAB_FILTER_OFF, TAB_SORT_OFF = 0x08, 0x20, 0x94
JERSEY, NAME_COLUMN, TEAM_NAME = 0x00540998, 0x00543928, 0x005439D8
DEFENSE_COLUMNS = (JERSEY, NAME_COLUMN, TEAM_NAME, 0x00544FD8, 0x00545088, 0x00545138, 0x005451E8, 0x00545298,
                   0x00545348, 0x005453F8, 0x005454A8, 0x00545608, 0x005456B8, 0x00545CE8, 0x00545768, 0x00545818,
                   0x005458C8)    # # NAME TEAM TKL AST SACK YDS AVG PD INT YDS AVG LNG TD TFL FF FR, then FBK (0x548268)
OL_TAB_TITLE = "Offensive Line"
OL_LEADER_KEYS = ("pa", "ha")     # SA's leader column already exists (LEADER_KEYS)
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
    # b780 b5-sim: the League Leaders tabs this owner copies, and the padding word that becomes the tab list's terminator
    ("defense tab header", 0x00548188, 0x9C), ("defense tab columns", 0x00548224, 0x44),
    ("special teams tab header", 0x00548438, 0x9C), ("tab list padding", 0x0054A15C, 0x4),
    ("leader getters", 0x003216A6, 0x2D), ("tab walker", 0x00174D00, 0x2D),
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
    "defense tab header": "e05dd50daa809d056ad5fe3e0c95164b55cae3c8f9f7330e66eeacde5ea9ecce",
    "defense tab columns": "63eb614f6a404150daf99f55089c51e323103fbe774aae27d4204d94782ff523",
    "special teams tab header": "1eaa9c2f10737066534f763a2ad2cc00fb90d0a10b5f2dbe7162b701bf8855b7",
    "tab list padding": "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119",
    "leader getters": "f4c791d1942343440c23a0a1b9d27b7cd9aea7ea616c6306ac135781c714f543",
    "tab walker": "db4741bbbfb6a913d3e2d2bd18c3bee4ecae2506e8647badb3fccc096b6d74ff",
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
    for key in LEADER_KEYS:
        out["ld_" + key] = at
        at += DESCRIPTOR_SIZE
    # b780 b5-sim: the Offensive Line tab's leader columns, its title and default sort, the copied Defense tab, the new tab
    for key in OL_LEADER_KEYS:
        out["ld_" + key] = at
        at += DESCRIPTOR_SIZE
    out["t_ol"] = at
    at = (at + len(_utf16(OL_TAB_TITLE)) + 3) & ~3
    out["sort_ol"] = at
    at += 8
    out["tab_def"] = at
    at += TAB_HEADER + 4 * (len(DEFENSE_COLUMNS) + 4)       # + FBK, PRS, QBH and the terminator
    out["tab_ol"] = at
    at += TAB_HEADER + 4 * 7                                # # NAME TEAM PA HA SA and the terminator
    out["end"] = at
    _require(at - read_only_va <= READ_ONLY_SIZE, "the pass rush read-only block exceeds its budget")
    return out


def _descriptor(template, getter, abbr_va, long_va, stat_id, cookie=0x200B3):
    d = bytearray(template)
    _require(struct.unpack_from("<I", d, 0x00)[0] == 4 and struct.unpack_from("<I", d, 0x0C)[0] == cookie,
             "the template is not the retail integer stat column")
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
    leader_template = image.read(FBK, DESCRIPTOR_SIZE)
    _require(struct.unpack_from("<I", leader_template, 0x08)[0] == LEADER_GETTER, "the FBK leaders column is not retail")
    leader = labels(code_va)["prs_leader_value"]
    field_of = {"prs": "pressures", "qbh": "qb_hits", "sa": "sacks_allowed", "pa": "pressures_allowed",
                "ha": "qb_hits_allowed"}
    for key in LEADER_KEYS + OL_LEADER_KEYS:
        put(lay["ld_" + key], _descriptor(leader_template, leader, lay["s_" + key], lay["l_" + key],
                                          FIELDS[field_of[key]], cookie=0x307BA))
    for va, data in league_leader_tabs(image, lay):
        put(va, data)
    return bytes(buf)


def league_leader_tabs(image, lay):
    """b780 b5-sim: (VA, bytes) of the League Leaders tab copies. Defense: the retail tab's header (same filter, default
    sort and row callbacks) with its retail columns, FBK back in its place, then PRS and QBH. Offensive Line: the Special
    Teams header (filter index 6: a player with a value in any column of the tab) with this owner's title and a default
    sort on its first stat column, and the columns # NAME TEAM PA HA SA."""
    defense = image.read(DEFENSE_TAB, TAB_HEADER)
    _require(struct.unpack_from(f"<{len(DEFENSE_COLUMNS)}I", image.read(DEFENSE_TAB + TAB_HEADER, 4 * len(DEFENSE_COLUMNS)))
             == DEFENSE_COLUMNS, "the League Leaders defense tab is not retail")
    tab_def = defense + struct.pack(f"<{len(DEFENSE_COLUMNS) + 4}I", *DEFENSE_COLUMNS, FBK, lay["ld_prs"], lay["ld_qbh"], 0)
    header = bytearray(image.read(SPECIAL_TEAMS_TAB, TAB_HEADER))
    _require(struct.unpack_from("<3I", header, TAB_FILTER_OFF - 8) == (0x0027CCD0, 0x10000, 6),
             "the League Leaders special teams tab is not retail")
    struct.pack_into("<I", header, TAB_TITLE_OFF, lay["t_ol"])
    struct.pack_into("<I", header, TAB_SORT_OFF, lay["sort_ol"])
    tab_ol = bytes(header) + struct.pack("<7I", JERSEY, NAME_COLUMN, TEAM_NAME, lay["ld_pa"], lay["ld_ha"], lay["ld_sa"], 0)
    return [(lay["t_ol"], _utf16(OL_TAB_TITLE)), (lay["sort_ol"], struct.pack("<2i", 3, -999)),
            (lay["tab_def"], tab_def), (lay["tab_ol"], tab_ol)]


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


def data_edits(code_va, read_only_va=0):
    """The table edits: the card jump table and screen bytes (.text), the League Leaders slots (.rdata)."""
    at = labels(code_va)
    lay = read_only_layout(read_only_va) if read_only_va else None
    out = [(label, va, struct.pack("<I", retail), struct.pack("<I", at[stub])) for label, va, retail, stub in CARD_JUMPS]
    out.append(("card_ol_screens", CARD_POSITION_TABLE + OL_POSITIONS[0], bytes([6, 6, 6]), bytes([4, 4, 4])))
    for va, retail, key in LEADER_SLOTS:
        out.append((f"leaders_{key}_{va:x}", va, struct.pack("<I", retail),
                    struct.pack("<I", lay["ld_" + key] if lay else 0)))
    out.append(("leaders_defense_tab", DEFENSE_TAB_SLOT, struct.pack("<I", DEFENSE_TAB),
                struct.pack("<I", lay["tab_def"] if lay else 0)))
    out.append(("leaders_offensive_line_tab", NEW_TAB_SLOT, bytes(4), struct.pack("<I", lay["tab_ol"] if lay else 0)))
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
    for _l, va, before, after in data_edits(code_va, ro_va):
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
    for label, va, old, new in sites(code_va) + data_edits(code_va, ro_va):
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

"""14-team playoffs (the 2020+ NFL format) for ESPN NFL 2K5's franchise mode (executable patch).

Retail seeds six teams per conference (four division winners sorted by the tiebreaker comparator,
then the two best of the rest), plays four wild-card games (3v6 and 4v5 per conference), gives the
top two seeds a bye and reseeds the divisional round so the #1 seed hosts the lowest surviving seed.
The 2020+ format seeds SEVEN per conference, only the #1 seed rests, and the wild-card round is
2v7 / 3v6 / 4v5 (six games); the divisional round still reseeds (#1 hosts the lowest survivor, the
other two winners meet with the higher seed at home), then conference championships and the Super
Bowl as before.  Everything below was read from the retail ``default.xbe`` (Ghidra + capstone) and
is unwitnessed at runtime.

What retail does and where (virtual addresses, image base 0x10000):

* ``FUN_002a7d60(conf, int out[6])`` -- seeding.  Division winners via ``FUN_002a7d00(division)``
  (conf 0 = AFC = divisions 7,4,5,6; conf 1 = NFC = 3,0,1,2 of the table at 0xACEE38), sorted by
  ``FUN_002a7c40`` (shell sort over ``FUN_002a7a40``: win points, head-to-head, conference record,
  common games, conference net points, net points, pointer order), then every other conference team
  sorted the same way; ``out[4..5]`` = the best two.  Callers keep a six-int array on the stack.
* ``FUN_002a7e50`` -- season start (stage 8): seeds both conferences, optionally forces the user's
  team in as the sixth seed, stores the twelve seeds in the 12-entry table at 0xE578F4 (saved as 12
  bytes at +0x0B of the season block by FUN_000c5310), then copies the twelve 8-byte kickoff records
  at 0xACD6C8 into the grid: WC row slots 0..3 = AFC 4v5, AFC 3v6, NFC 4v5, NFC 3v6 (flags 1/1),
  DIV row slots 0..3 with only the home team (#1/#2 seeds, flags 1/0), CONF and SB empty (0/0).
* ``FUN_00247690`` -- called after every postseason game (FUN_000c7a20, stage 9): seven routines
  at 0x2471B0..0x247690 fill the divisional away teams (the lowest surviving seed to the #1 seed, via
  the seed table lookup ``FUN_000c51f0``), the conference games (higher seed hosts) and the Super
  Bowl (home by season parity).  They hard-code rows 0x11..0x14.
* ``FUN_002476c0(team)`` -- "team is in the bracket": the 8 wild-card teams and 4 divisional hosts.
* ``FUN_00132ed0`` (clinch level: 4 home field, 3 bye, 2 division, 1 berth) and ``FUN_00133cf0``
  (still alive) simulate the remaining games, reseed with ``FUN_002a7d60`` and look for the team
  among the six seeds; 6 = not in.
* ``cb_00368395`` -- the Playoff Picture list: four division leaders plus 6/5/4 teams in the hunt,
  and exactly two once the regular season is over (``mov eax,2`` at 0x36848C).

The patch (``playoffs_14`` group, every site pattern-checked against retail, section digests
recomputed by the season-length module's ``apply``):

1. ``FUN_002a7d60`` rewritten in place (240 bytes): same seeding, ``out[0..5]`` as before and the
   SEVENTH seed in a spare saved dword (``LAST7_VA`` = 0xE57924, entry 0 of a 12-dword table whose
   only accessors have no callers), so the six-int callers keep their frames.
2. ``FUN_002a7e50`` 0x2A7E57..0x2A8152 rewritten in place: seven seeds per conference (the user's
   team is forced in as the seventh when the caller asks), the twelve old-format seeds still stored
   for the save, then a 13-entry game table (row offset, slot, home seed, away seed, flags) writes
   WC slots 0..5 = AFC 2v7, 3v6, 4v5, NFC 2v7, 3v6, 4v5; DIV slots 0/2 with the #1 seeds at home,
   slots 1/3 empty; CONF 0/1 and SB empty, using its own 13 kickoff records (``CALENDAR_2026_14``),
   then rejoins the retail tail at 0x2A8152 with esi = the Super Bowl row.
3. ``FUN_00247690`` jumps into a cave in the dead function ``FUN_00325e70`` (no reference anywhere in
   the executable, 979 bytes): the advance routine derives seeds from the wild-card records
   themselves (home of WC slot k = seed 2+k, away = 7-k, #1 = home of DIV slot 0/2) instead of the
   unsaved seed table, fills DIV slot 2c (away = lowest survivor) and 2c+1 (higher seed at home),
   the conference games and the Super Bowl exactly like retail.  Rows come from the stage table's
   Season week count (``.rdata`` 0x5151C4: 17 retail, 18 with the season-length patch).
4. ``FUN_002476c0`` jumps to a cave loop over six wild-card games and four divisional hosts.
5. The two seed-compare chains (0x133180 and 0x133F08, 68 bytes each) become loops that also test
   the seventh seed; "not in" becomes 7 (``and ebx,6`` -> 7 at 0x132F01, ``cmp esi,6`` -> 7 at
   0x133212 / 0x13324F / 0x133F75); the clinch levels become 4 = #1 seed (home field and the only
   bye), 2 = seeds 2-4 (division title), 1 = seeds 5-7 (``cmp ebx,2`` -> ``cmp ebx,1`` at 0x13326E).
6. The Playoff Picture shows seven teams once the regular season is over (0x36848D: 2 -> 3).

Not changed (documented limits): the Playoff Tree screen's widget table (``.data`` 0xAEF4D0..) has
two wild-card boxes per conference, so the third wild-card game of each conference is visible on the
schedule/results screens but not in the tree; the standings legend keeps its four letters (the "z"
first-round-bye line is never earned by a #2 seed any more); the tiebreaker order is retail's.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Sequence

IMAGE_BASE = 0x10000

# --- retail routines the new code calls (all __fastcall unless noted) -------------------------------
FN_SEED_DIVISION = 0x002A7D00   # ecx = division -> eax = its best team (tiebreaker sort)
FN_SORT_TEAMS = 0x002A7C40      # ecx = int*, edx = count: shell sort by FUN_002a7a40
FN_TEAM_COUNT = 0x000C4BE0      # -> eax = number of teams in the league
FN_TEAM_AT = 0x000C4C50         # ecx = index -> eax = team record
FN_TEAM_INDEX = 0x000C4CA0      # ecx = team record -> eax = index (0xffff for 0)
FN_CONFERENCE = 0x00133B10      # ecx = team -> eax = conference (0 AFC, 1 NFC)
FN_USER_TEAM = 0x000C4D70       # -> eax = first user-controlled team
FN_STAGE_WEEKS = 0x000C4E50     # -> eax = DAT_00e576b0 (the wild-card row at season start)
FN_SEASON_INDEX = 0x000C4EB0    # -> eax = season index
FN_RECORD = 0x000C4F10          # (week, slot) -> eax = 8-byte grid record
FN_FLAG_HOME = 0x000C4F50       # (week, slot, [esp+4] = flag)   ret 4
FN_FLAG_AWAY = 0x000C4F70       # (week, slot, [esp+4] = flag)   ret 4
FN_GAME_TYPE = 0x000C4FD0       # (week, slot) -> eax = record type (3 = played, 7 = empty)
FN_WINNER = 0x000C5190          # (week, slot) -> eax = winning team
FN_HOME = 0x000C4E00            # (week, slot) -> eax = home team
FN_AWAY = 0x000C4E20            # (week, slot) -> eax = away team
FN_WRITE_RECORD = 0x000C6900    # (week, slot, [esp+4] = record*) memcpy 8   ret 4
FN_SEED_STORE = 0x000C7320      # ecx = team, edx = index -> the 12-entry seed table (saved)

STAGE_SEASON_WEEKS_VA = 0x005151C4     # .rdata stage table 0x515140, Season row (8) byte +4 = the wild-card row
LAST7_VA = 0x00E57924                  # spare saved dword: the seventh seed of the last seeding

SEED_FN_VA = 0x002A7D60
SEED_FN_SIZE = 0xF0
BUILDER_VA = 0x002A7E57                # after "sub esp,0x34; push esi; mov esi,ecx; push edi"
BUILDER_END_VA = 0x002A8152            # retail tail: FUN_000c5230(0) ... (esi = Super Bowl row)
BUILDER_SIZE = BUILDER_END_VA - BUILDER_VA
CAVE_VA = 0x00325E70                   # FUN_00325e70: dead (no call, jump or pointer to it)
CAVE_SIZE = 0x3D3
DISPATCH_VA = 0x00247690               # FUN_00247690: seven advance calls -> jmp cave
IN_BRACKET_VA = 0x002476C0             # FUN_002476c0 -> jmp cave
CLINCH_CHAIN_VA = 0x00133180
ELIM_CHAIN_VA = 0x00133F08
CHAIN_SIZE = 0x44
CLINCH_MODE_MASK_VA = 0x00132F01       # and ebx,6
CLINCH_SENTINEL_A_VA = 0x00133212      # cmp esi,6
CLINCH_SENTINEL_B_VA = 0x0013324F      # cmp esi,6
CLINCH_BYE_LEVEL_VA = 0x0013326E       # cmp ebx,2
ELIM_SENTINEL_VA = 0x00133F75          # cmp esi,6
PICTURE_FINAL_COUNT_VA = 0x0036848C    # mov eax,2

SEEDS_PER_CONFERENCE = 7
WILD_CARD_GAMES = 6
POSTSEASON_GAMES_14 = 13

# Wild card: Sat Jan 16 2027 (2), Sun Jan 17 (3), Mon Jan 18 (1); divisional Sat Jan 23 / Sun Jan 24;
# conference championships Sun Jan 31; Super Bowl LXI Sun Feb 14 2027 (NFL, May 14 2026 release).
# Kickoffs are the standard windows until the league publishes them (January 2027).  Order = WC slots
# 0..5 (AFC 2v7, AFC 3v6, AFC 4v5, NFC 2v7, NFC 3v6, NFC 4v5), DIV slots 0..3, CONF 0..1, SB.
CALENDAR_2026_14 = (
    (1, 16, 4, 30), (1, 16, 8, 15), (1, 17, 1, 0), (1, 17, 4, 30), (1, 17, 8, 15), (1, 18, 8, 15),
    (1, 23, 4, 30), (1, 23, 8, 15), (1, 24, 3, 0), (1, 24, 6, 30),
    (1, 31, 3, 0), (1, 31, 6, 30),
    (2, 14, 6, 30),
)
# Retail-shaped dates for a 17-week season (the 2004-05 windows plus a Monday wild-card game).
CALENDAR_RETAIL_14 = (
    (1, 8, 0, 30), (1, 8, 4, 5), (1, 9, 0, 35), (1, 9, 4, 15), (1, 9, 8, 15), (1, 10, 8, 15),
    (1, 15, 0, 35), (1, 15, 4, 15), (1, 16, 0, 40), (1, 16, 4, 15),
    (1, 23, 1, 35), (1, 23, 4, 15),
    (1, 30, 4, 0),
)
POSTSEASON_LABELS_14 = ("wild_card_afc_2v7", "wild_card_afc_3v6", "wild_card_afc_4v5", "wild_card_nfc_2v7",
                        "wild_card_nfc_3v6", "wild_card_nfc_4v5", "divisional_afc_1", "divisional_afc_2",
                        "divisional_nfc_1", "divisional_nfc_2", "conference_afc", "conference_nfc", "super_bowl")

# Game table consumed by the builder: (row offset from the wild-card row, slot, home seed byte, away
# seed byte, home-known flag, away-known flag).  Seed bytes index the 14-byte seed list: 0..6 = AFC
# seeds 1..7, 7..13 = NFC seeds 1..7, 0xFF = nobody yet.
NONE = 0xFF
GAME_TABLE: tuple[tuple[int, int, int, int, int, int], ...] = (
    (0, 0, 1, 6, 1, 1), (0, 1, 2, 5, 1, 1), (0, 2, 3, 4, 1, 1),
    (0, 3, 8, 13, 1, 1), (0, 4, 9, 12, 1, 1), (0, 5, 10, 11, 1, 1),
    (1, 0, 0, NONE, 1, 0), (1, 1, NONE, NONE, 0, 0), (1, 2, 7, NONE, 1, 0), (1, 3, NONE, NONE, 0, 0),
    (2, 0, NONE, NONE, 0, 0), (2, 1, NONE, NONE, 0, 0),
    (3, 0, NONE, NONE, 0, 0),
)


class Playoffs14Error(ValueError):
    """The 14-team playoff patch cannot be applied to this executable."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Playoffs14Error(message)


@dataclass(frozen=True)
class Site:
    label: str
    va: int
    retail: bytes
    patched: bytes
    note: str

    @property
    def size(self) -> int:
        return len(self.retail)


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _imm(va: int) -> str:
    return _u32(va).hex()


# --- a tiny assembler with labels (same shape as the draft-AI cave's) ------------------------------

class _Asm:
    def __init__(self, base: int) -> None:
        self.base = base
        self.items: list = []
        self.labels: dict[str, int] = {}

    def b(self, hexs: str) -> None:
        self.items.append(bytes.fromhex(hexs))

    def raw(self, data: bytes) -> None:
        self.items.append(bytes(data))

    def label(self, name: str) -> None:
        self.items.append(("label", name))

    def j8(self, opcode: str, label: str) -> None:
        self.items.append(("j8", bytes.fromhex(opcode), label))

    def j32(self, opcode: str, label: str) -> None:
        self.items.append(("j32", bytes.fromhex(opcode), label))

    def call(self, va: int) -> None:
        self.items.append(("call", va))

    def call_label(self, label: str) -> None:
        self.items.append(("j32", b"\xe8", label))

    def jmp_abs(self, va: int) -> None:
        self.items.append(("jmpabs", va))

    def lea_label(self, reg_modrm_hex: str, label: str) -> None:
        """An absolute disp32 that points at a label inside this blob (e.g. lea esi,[edi*8+disp32])."""
        self.items.append(("abs32", bytes.fromhex(reg_modrm_hex), label))

    @staticmethod
    def _size(item) -> int:
        if isinstance(item, bytes):
            return len(item)
        kind = item[0]
        if kind == "label":
            return 0
        if kind == "j8":
            return 2
        if kind in ("j32", "abs32"):
            return len(item[1]) + 4
        return 5

    def assemble(self) -> bytes:
        pos = 0
        for item in self.items:
            if isinstance(item, tuple) and item[0] == "label":
                self.labels[item[1]] = pos
            pos += self._size(item)
        out = bytearray()
        for item in self.items:
            here = len(out)
            if isinstance(item, bytes):
                out += item
            elif item[0] == "label":
                continue
            elif item[0] == "j8":
                rel = self.labels[item[2]] - (here + 2)
                _require(-128 <= rel <= 127, f"rel8 out of range for {item[2]}")
                out += item[1] + struct.pack("<b", rel)
            elif item[0] == "j32":
                rel = self.labels[item[2]] - (here + len(item[1]) + 4)
                out += item[1] + struct.pack("<i", rel)
            elif item[0] == "abs32":
                out += item[1] + _u32(self.base + self.labels[item[2]])
            elif item[0] == "call":
                out += b"\xe8" + struct.pack("<i", item[1] - (self.base + here + 5))
            elif item[0] == "jmpabs":
                out += b"\xe9" + struct.pack("<i", item[1] - (self.base + here + 5))
        return bytes(out)

    def va(self, label: str) -> int:
        return self.base + self.labels[label]


# --- 1. seed7: FUN_002a7d60 rewritten ----------------------------------------------------------------

def seed_fn_bytes() -> bytes:
    """ecx = conference, edx = int out[6].  out[0..3] = the division winners (sorted), out[4..5] = the
    best two of the rest, [LAST7_VA] = the third best of the rest (the seventh seed).  Frame: 16
    candidate slots at [esp] (a conference has 12 non-winners), team count at [esp+0x40]."""

    a = _Asm(SEED_FN_VA)
    a.b("53565755")                      # push ebx; push esi; push edi; push ebp
    a.b("83ec44")                        # sub esp,0x44
    a.b("8bf2")                          # mov esi,edx            ; out
    a.b("8be9")                          # mov ebp,ecx            ; conference
    a.b("33db")                          # xor ebx,ebx
    a.label("div")
    a.b("8d4b03")                        # lea ecx,[ebx+3]
    a.b("83e103")                        # and ecx,3              ; NFC: 3,0,1,2
    a.b("85ed")                          # test ebp,ebp
    a.j8("75", "div_nfc")                # jne div_nfc
    a.b("83c104")                        # add ecx,4              ; AFC: 7,4,5,6
    a.label("div_nfc")
    a.call(FN_SEED_DIVISION)             # eax = division winner
    a.b("89049e")                        # mov [esi+ebx*4],eax
    a.b("43")                            # inc ebx
    a.b("83fb04")                        # cmp ebx,4
    a.j8("7c", "div")                    # jl div
    a.b("8bce")                          # mov ecx,esi
    a.b("ba04000000")                    # mov edx,4
    a.call(FN_SORT_TEAMS)                # sort the division winners
    a.call(FN_TEAM_COUNT)
    a.b("89442440")                      # mov [esp+0x40],eax
    a.b("33ff")                          # xor edi,edi            ; candidates
    a.b("33db")                          # xor ebx,ebx            ; team index
    a.label("teams")
    a.b("3b5c2440")                      # cmp ebx,[esp+0x40]
    a.j8("7d", "teams_done")             # jge teams_done
    a.b("8bcb")                          # mov ecx,ebx
    a.call(FN_TEAM_AT)                   # eax = team
    a.b("3b06")                          # cmp eax,[esi]
    a.j8("74", "teams_next")
    a.b("3b4604")                        # cmp eax,[esi+4]
    a.j8("74", "teams_next")
    a.b("3b4608")                        # cmp eax,[esi+8]
    a.j8("74", "teams_next")
    a.b("3b460c")                        # cmp eax,[esi+0xc]
    a.j8("74", "teams_next")
    a.b("8904bc")                        # mov [esp+edi*4],eax    ; tentative
    a.b("8bc8")                          # mov ecx,eax
    a.call(FN_CONFERENCE)
    a.b("3bc5")                          # cmp eax,ebp
    a.j8("75", "teams_next")             # other conference: the slot is reused
    a.b("47")                            # inc edi
    a.label("teams_next")
    a.b("43")                            # inc ebx
    a.j8("eb", "teams")                  # jmp teams
    a.label("teams_done")
    a.b("8bcc")                          # mov ecx,esp
    a.b("8bd7")                          # mov edx,edi
    a.call(FN_SORT_TEAMS)                # sort the rest
    a.b("8b0424")                        # mov eax,[esp]
    a.b("894610")                        # mov [esi+0x10],eax     ; seed 5
    a.b("8b442404")                      # mov eax,[esp+4]
    a.b("894614")                        # mov [esi+0x14],eax     ; seed 6
    a.b("8b442408")                      # mov eax,[esp+8]
    a.b("a3" + _imm(LAST7_VA))           # mov [LAST7],eax        ; seed 7
    a.b("83c444")                        # add esp,0x44
    a.b("5d5f5e5b")                      # pop ebp; pop edi; pop esi; pop ebx
    a.b("c3")                            # ret
    code = a.assemble()
    _require(len(code) <= SEED_FN_SIZE, f"seed routine is {len(code)} bytes, over {SEED_FN_SIZE}")
    return code + b"\xcc" * (SEED_FN_SIZE - len(code))


# --- 2. the season-start bracket builder (inside FUN_002a7e50) ---------------------------------------

def postseason_record_14(month: int, day: int, hour12: int, minute: int) -> bytes:
    _require(1 <= month <= 12 and 1 <= day <= 31, "postseason date out of range")
    _require(0 <= hour12 <= 12 and 0 <= minute <= 59, "postseason kickoff out of range")
    return bytes([0, 0, 0, month, day, 0, hour12 % 12, minute])


def date_table_14(records: Sequence[tuple[int, int, int, int]]) -> bytes:
    _require(len(records) == POSTSEASON_GAMES_14, f"exactly {POSTSEASON_GAMES_14} postseason records")
    return b"".join(postseason_record_14(*r) for r in records)


def game_table_bytes() -> bytes:
    _require(len(GAME_TABLE) == POSTSEASON_GAMES_14, "13 games")
    return b"".join(bytes([row, slot, home, away, fa, fb, 0, 0]) for row, slot, home, away, fa, fb in GAME_TABLE)


def builder_bytes(calendar: Sequence[tuple[int, int, int, int]] = CALENDAR_2026_14) -> bytes:
    """Replaces 0x2A7E57..0x2A8152 of FUN_002a7e50.  On entry: ``sub esp,0x34; push esi; push edi``
    done, esi = the caller's flag (force the user's team in).  Locals: AFC seeds [esp+0..0x1c),
    NFC seeds [esp+0x1c..0x38) as team pointers, then the same 14 entries as index bytes at
    [esp+0..0xe), the scratch record at [esp+0x10], the wild-card row at [esp+0x18]."""

    a = _Asm(BUILDER_VA)
    a.b("8d1424")                        # lea edx,[esp]
    a.b("33c9")                          # xor ecx,ecx
    a.call(SEED_FN_VA)                   # AFC seeds 1..6
    a.b("a1" + _imm(LAST7_VA))           # mov eax,[LAST7]
    a.b("89442418")                      # mov [esp+0x18],eax     ; AFC seed 7
    a.b("8d54241c")                      # lea edx,[esp+0x1c]
    a.b("b901000000")                    # mov ecx,1
    a.call(SEED_FN_VA)                   # NFC seeds 1..6
    a.b("a1" + _imm(LAST7_VA))           # mov eax,[LAST7]
    a.b("89442434")                      # mov [esp+0x34],eax     ; NFC seed 7
    a.b("85f6")                          # test esi,esi
    a.j8("74", "force_done")             # je force_done
    a.call(FN_USER_TEAM)
    a.b("8bf8")                          # mov edi,eax
    a.b("33c9")                          # xor ecx,ecx
    a.label("force_scan")
    a.b("393c8c")                        # cmp [esp+ecx*4],edi
    a.j8("74", "force_done")             # already seeded
    a.b("41")                            # inc ecx
    a.b("83f90e")                        # cmp ecx,14
    a.j8("7c", "force_scan")
    a.b("8bcf")                          # mov ecx,edi
    a.call(FN_CONFERENCE)
    a.b("85c0")                          # test eax,eax
    a.j8("75", "force_nfc")
    a.b("897c2418")                      # mov [esp+0x18],edi     ; AFC seed 7 = user
    a.j8("eb", "force_done")
    a.label("force_nfc")
    a.b("897c2434")                      # mov [esp+0x34],edi     ; NFC seed 7 = user
    a.label("force_done")
    a.b("33ff")                          # xor edi,edi
    a.label("store")                     # the twelve old-format seeds (saved with the season)
    a.b("8b0cbc")                        # mov ecx,[esp+edi*4]
    a.b("8bd7")                          # mov edx,edi
    a.call(FN_SEED_STORE)
    a.b("8b4cbc1c")                      # mov ecx,[esp+edi*4+0x1c]
    a.b("8d5706")                        # lea edx,[edi+6]
    a.call(FN_SEED_STORE)
    a.b("47")                            # inc edi
    a.b("83ff06")                        # cmp edi,6
    a.j8("7c", "store")
    a.b("33ff")                          # xor edi,edi
    a.label("convert")                   # team pointers -> index bytes, in place
    a.b("8b0cbc")                        # mov ecx,[esp+edi*4]
    a.call(FN_TEAM_INDEX)
    a.b("88043c")                        # mov [esp+edi],al
    a.b("47")                            # inc edi
    a.b("83ff0e")                        # cmp edi,14
    a.j8("7c", "convert")
    a.call(FN_STAGE_WEEKS)
    a.b("89442418")                      # mov [esp+0x18],eax     ; wild-card row
    a.b("33ff")                          # xor edi,edi
    a.label("game")
    a.lea_label("8d34fd", "games")       # lea esi,[edi*8+games]
    a.lea_label("8b04fd", "dates")       # mov eax,[edi*8+dates]
    a.b("89442410")                      # mov [esp+0x10],eax
    a.lea_label("8b04fd", "dates_hi")    # mov eax,[edi*8+dates+4]
    a.b("89442414")                      # mov [esp+0x14],eax
    a.b("0fb64602")                      # movzx eax,byte [esi+2] ; home seed byte
    a.b("3cff")                          # cmp al,0xff
    a.j8("74", "game_home_done")
    a.b("0fb60404")                      # movzx eax,byte [esp+eax]
    a.b("88442411")                      # mov [esp+0x11],al
    a.label("game_home_done")
    a.b("0fb64603")                      # movzx eax,byte [esi+3] ; away seed byte
    a.b("3cff")                          # cmp al,0xff
    a.j8("74", "game_away_done")
    a.b("0fb60404")                      # movzx eax,byte [esp+eax]
    a.b("88442412")                      # mov [esp+0x12],al
    a.label("game_away_done")
    a.b("0fb60e")                        # movzx ecx,byte [esi]
    a.b("034c2418")                      # add ecx,[esp+0x18]     ; row
    a.b("0fb65601")                      # movzx edx,byte [esi+1] ; slot
    a.b("8d442410")                      # lea eax,[esp+0x10]
    a.b("50")                            # push eax
    a.call(FN_WRITE_RECORD)              # ret 4
    a.b("0fb60e")                        # movzx ecx,byte [esi]
    a.b("034c2418")                      # add ecx,[esp+0x18]
    a.b("0fb65601")                      # movzx edx,byte [esi+1]
    a.b("0fb64604")                      # movzx eax,byte [esi+4]
    a.b("50")                            # push eax
    a.call(FN_FLAG_HOME)                 # ret 4
    a.b("0fb60e")                        # movzx ecx,byte [esi]
    a.b("034c2418")                      # add ecx,[esp+0x18]
    a.b("0fb65601")                      # movzx edx,byte [esi+1]
    a.b("0fb64605")                      # movzx eax,byte [esi+5]
    a.b("50")                            # push eax
    a.call(FN_FLAG_AWAY)                 # ret 4
    a.b("47")                            # inc edi
    a.b("83ff0d")                        # cmp edi,13
    a.j32("0f8c", "game")                # jl game
    a.b("8b742418")                      # mov esi,[esp+0x18]
    a.b("83c603")                        # add esi,3              ; the Super Bowl row for the tail
    a.jmp_abs(BUILDER_END_VA)
    a.b("cccccccc")                      # padding to an 8-byte boundary for the tables
    while (a.base + sum(a._size(i) for i in a.items)) % 8:
        a.b("cc")
    a.label("games")
    a.raw(game_table_bytes())
    a.label("dates")
    dates = date_table_14(calendar)
    a.raw(dates[:4])
    a.label("dates_hi")
    a.raw(dates[4:])
    code = a.assemble()
    _require(len(code) <= BUILDER_SIZE, f"builder is {len(code)} bytes, over {BUILDER_SIZE}")
    return code + b"\xcc" * (BUILDER_SIZE - len(code))


# --- 3/4. the cave: advance14, in_bracket14, seed_of ---------------------------------------------------

def _stage_row(a: _Asm, dst_hex: str) -> None:
    """movzx <reg>, byte [STAGE_SEASON_WEEKS_VA] -- the wild-card row (17 retail, 18 patched)."""
    a.b("0fb6" + dst_hex + _imm(STAGE_SEASON_WEEKS_VA))


def cave_asm() -> _Asm:
    a = _Asm(CAVE_VA)

    # ---- advance14 (void, preserves ebx/esi/edi/ebp) -----------------------------------------------
    # locals: w[3] at [esp], s[3] at [esp+0xc], wild-card row [esp+0x18], scratch [esp+0x20/0x24]
    a.label("advance")
    a.b("53565755")                      # push ebx; push esi; push edi; push ebp
    a.b("83ec28")                        # sub esp,0x28
    _stage_row(a, "05")                  # movzx eax,byte [stage]
    a.b("89442418")                      # mov [esp+0x18],eax
    a.b("33ed")                          # xor ebp,ebp            ; conference
    a.label("div_conf")
    a.b("33db")                          # xor ebx,ebx
    a.label("div_check")                 # all three wild-card games of this conference played?
    a.b("8d546d00")                      # lea edx,[ebp+ebp*2]
    a.b("03d3")                          # add edx,ebx
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.call(FN_GAME_TYPE)
    a.b("83f803")                        # cmp eax,3
    a.j32("0f85", "div_next")            # jne div_next
    a.b("43")                            # inc ebx
    a.b("83fb03")                        # cmp ebx,3
    a.j8("7c", "div_check")
    a.b("33db")                          # xor ebx,ebx
    a.label("div_winners")
    a.b("8d546d00")                      # lea edx,[ebp+ebp*2]
    a.b("03d3")                          # add edx,ebx
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.call(FN_WINNER)
    a.b("89049c")                        # mov [esp+ebx*4],eax    ; w[k]
    a.b("8bc8")                          # mov ecx,eax
    a.b("8bd5")                          # mov edx,ebp
    a.call_label("seed_of")
    a.b("89449c0c")                      # mov [esp+ebx*4+0xc],eax ; s[k]
    a.b("43")                            # inc ebx
    a.b("83fb03")                        # cmp ebx,3
    a.j8("7c", "div_winners")
    a.b("33ff")                          # xor edi,edi            ; m = index of the lowest seed
    a.b("8b442410")                      # mov eax,[esp+0x10]     ; s[1]
    a.b("3b44bc0c")                      # cmp eax,[esp+edi*4+0xc]
    a.j8("7e", "div_m1")
    a.b("bf01000000")                    # mov edi,1
    a.label("div_m1")
    a.b("8b442414")                      # mov eax,[esp+0x14]     ; s[2]
    a.b("3b44bc0c")                      # cmp eax,[esp+edi*4+0xc]
    a.j8("7e", "div_m2")
    a.b("bf02000000")                    # mov edi,2
    a.label("div_m2")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx                ; divisional row
    a.b("8d146d00000000")                # lea edx,[ebp*2]        ; slot 2c (#1 seed at home)
    a.call(FN_RECORD)
    a.b("8bf0")                          # mov esi,eax
    a.b("8b0cbc")                        # mov ecx,[esp+edi*4]    ; w[m]
    a.call(FN_TEAM_INDEX)
    a.b("884602")                        # mov [esi+2],al         ; away = lowest survivor
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d146d00000000")                # lea edx,[ebp*2]
    a.b("6a01")                          # push 1
    a.call(FN_FLAG_AWAY)
    a.b("33c0")                          # xor eax,eax            ; a = first index != m
    a.b("85ff")                          # test edi,edi
    a.j8("75", "div_a")
    a.b("40")                            # inc eax
    a.label("div_a")
    a.b("b902000000")                    # mov ecx,2              ; b = last index != m
    a.b("83ff02")                        # cmp edi,2
    a.j8("75", "div_b")
    a.b("49")                            # dec ecx
    a.label("div_b")
    a.b("8b54840c")                      # mov edx,[esp+eax*4+0xc] ; s[a]
    a.b("3b548c0c")                      # cmp edx,[esp+ecx*4+0xc] ; s[b]
    a.j8("7e", "div_order")
    a.b("91")                            # xchg eax,ecx           ; better seed first
    a.label("div_order")
    a.b("89442420")                      # mov [esp+0x20],eax     ; home index
    a.b("894c2424")                      # mov [esp+0x24],ecx     ; away index
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d542d01")                      # lea edx,[ebp+ebp+1]    ; slot 2c+1
    a.call(FN_RECORD)
    a.b("8bf0")                          # mov esi,eax
    a.b("8b442420")                      # mov eax,[esp+0x20]
    a.b("8b0c84")                        # mov ecx,[esp+eax*4]
    a.call(FN_TEAM_INDEX)
    a.b("884601")                        # mov [esi+1],al
    a.b("8b442424")                      # mov eax,[esp+0x24]
    a.b("8b0c84")                        # mov ecx,[esp+eax*4]
    a.call(FN_TEAM_INDEX)
    a.b("884602")                        # mov [esi+2],al
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d542d01")                      # lea edx,[ebp+ebp+1]
    a.b("6a01")                          # push 1
    a.call(FN_FLAG_HOME)
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d542d01")                      # lea edx,[ebp+ebp+1]
    a.b("6a01")                          # push 1
    a.call(FN_FLAG_AWAY)
    a.label("div_next")
    a.b("45")                            # inc ebp
    a.b("83fd02")                        # cmp ebp,2
    a.j32("0f8c", "div_conf")            # jl div_conf

    a.b("33ed")                          # xor ebp,ebp
    a.label("conf_loop")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d146d00000000")                # lea edx,[ebp*2]
    a.call(FN_GAME_TYPE)
    a.b("83f803")                        # cmp eax,3
    a.j32("0f85", "conf_next")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d542d01")                      # lea edx,[ebp+ebp+1]
    a.call(FN_GAME_TYPE)
    a.b("83f803")                        # cmp eax,3
    a.j32("0f85", "conf_next")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d146d00000000")                # lea edx,[ebp*2]
    a.call(FN_WINNER)
    a.b("890424")                        # mov [esp],eax          ; w0
    a.b("8bc8")                          # mov ecx,eax
    a.b("8bd5")                          # mov edx,ebp
    a.call_label("seed_of")
    a.b("8944240c")                      # mov [esp+0xc],eax      ; s0
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("41")                            # inc ecx
    a.b("8d542d01")                      # lea edx,[ebp+ebp+1]
    a.call(FN_WINNER)
    a.b("89442404")                      # mov [esp+4],eax        ; w1
    a.b("8bc8")                          # mov ecx,eax
    a.b("8bd5")                          # mov edx,ebp
    a.call_label("seed_of")
    a.b("89442410")                      # mov [esp+0x10],eax     ; s1
    a.b("3b44240c")                      # cmp eax,[esp+0xc]
    a.j8("7d", "conf_order")             # jge: w0 keeps home
    a.b("8b0424")                        # mov eax,[esp]
    a.b("87442404")                      # xchg eax,[esp+4]
    a.b("890424")                        # mov [esp],eax          ; higher seed at home
    a.label("conf_order")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c102")                        # add ecx,2              ; conference row
    a.b("8bd5")                          # mov edx,ebp
    a.call(FN_RECORD)
    a.b("8bf0")                          # mov esi,eax
    a.b("8b0c24")                        # mov ecx,[esp]
    a.call(FN_TEAM_INDEX)
    a.b("884601")                        # mov [esi+1],al
    a.b("8b4c2404")                      # mov ecx,[esp+4]
    a.call(FN_TEAM_INDEX)
    a.b("884602")                        # mov [esi+2],al
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c102")                        # add ecx,2
    a.b("8bd5")                          # mov edx,ebp
    a.b("6a01")                          # push 1
    a.call(FN_FLAG_HOME)
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c102")                        # add ecx,2
    a.b("8bd5")                          # mov edx,ebp
    a.b("6a01")                          # push 1
    a.call(FN_FLAG_AWAY)
    a.label("conf_next")
    a.b("45")                            # inc ebp
    a.b("83fd02")                        # cmp ebp,2
    a.j32("0f8c", "conf_loop")

    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c102")                        # add ecx,2
    a.b("33d2")                          # xor edx,edx
    a.call(FN_GAME_TYPE)
    a.b("83f803")                        # cmp eax,3
    a.j32("0f85", "sb_done")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c102")                        # add ecx,2
    a.b("ba01000000")                    # mov edx,1
    a.call(FN_GAME_TYPE)
    a.b("83f803")                        # cmp eax,3
    a.j32("0f85", "sb_done")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c102")                        # add ecx,2
    a.b("33d2")                          # xor edx,edx
    a.call(FN_WINNER)
    a.b("890424")                        # mov [esp],eax          ; AFC champion
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c102")                        # add ecx,2
    a.b("ba01000000")                    # mov edx,1
    a.call(FN_WINNER)
    a.b("89442404")                      # mov [esp+4],eax        ; NFC champion
    a.call(FN_SEASON_INDEX)
    a.b("a801")                          # test al,1
    a.j8("75", "sb_home")                # odd seasons: AFC at home (retail parity)
    a.b("8b0424")                        # mov eax,[esp]
    a.b("87442404")                      # xchg eax,[esp+4]
    a.b("890424")                        # mov [esp],eax          ; even seasons: NFC at home
    a.label("sb_home")
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c103")                        # add ecx,3              ; Super Bowl row
    a.b("33d2")                          # xor edx,edx
    a.call(FN_RECORD)
    a.b("8bf0")                          # mov esi,eax
    a.b("8b0c24")                        # mov ecx,[esp]
    a.call(FN_TEAM_INDEX)
    a.b("884601")                        # mov [esi+1],al
    a.b("8b4c2404")                      # mov ecx,[esp+4]
    a.call(FN_TEAM_INDEX)
    a.b("884602")                        # mov [esi+2],al
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c103")                        # add ecx,3
    a.b("33d2")                          # xor edx,edx
    a.b("6a01")                          # push 1
    a.call(FN_FLAG_HOME)
    a.b("8b4c2418")                      # mov ecx,[esp+0x18]
    a.b("83c103")                        # add ecx,3
    a.b("33d2")                          # xor edx,edx
    a.b("6a01")                          # push 1
    a.call(FN_FLAG_AWAY)
    a.label("sb_done")
    a.b("83c428")                        # add esp,0x28
    a.b("5d5f5e5b")                      # pop ebp; pop edi; pop esi; pop ebx
    a.b("c3")                            # ret

    # ---- seed_of: ecx = team, edx = conference -> eax = 1..7 (8 = not in the bracket) --------------
    a.label("seed_of")
    a.b("53565755")                      # push ebx; push esi; push edi; push ebp
    a.b("8bf1")                          # mov esi,ecx
    a.b("8bea")                          # mov ebp,edx
    _stage_row(a, "3d")                  # movzx edi,byte [stage]
    a.b("8d4f01")                        # lea ecx,[edi+1]        ; divisional row
    a.b("8d146d00000000")                # lea edx,[ebp*2]        ; slot 2c: the #1 seed's home game
    a.call(FN_HOME)
    a.b("3bc6")                          # cmp eax,esi
    a.j8("75", "seed_wc")
    a.b("b801000000")                    # mov eax,1
    a.j8("eb", "seed_out")
    a.label("seed_wc")
    a.b("33db")                          # xor ebx,ebx
    a.label("seed_loop")
    a.b("8d546d00")                      # lea edx,[ebp+ebp*2]
    a.b("03d3")                          # add edx,ebx            ; wild-card slot 3c+k
    a.b("8bcf")                          # mov ecx,edi
    a.call(FN_HOME)
    a.b("3bc6")                          # cmp eax,esi
    a.j8("75", "seed_away")
    a.b("8d4302")                        # lea eax,[ebx+2]        ; home of slot k = seed 2+k
    a.j8("eb", "seed_out")
    a.label("seed_away")
    a.b("8d546d00")                      # lea edx,[ebp+ebp*2]
    a.b("03d3")                          # add edx,ebx
    a.b("8bcf")                          # mov ecx,edi
    a.call(FN_AWAY)
    a.b("3bc6")                          # cmp eax,esi
    a.j8("75", "seed_next")
    a.b("b807000000")                    # mov eax,7
    a.b("2bc3")                          # sub eax,ebx            ; away of slot k = seed 7-k
    a.j8("eb", "seed_out")
    a.label("seed_next")
    a.b("43")                            # inc ebx
    a.b("83fb03")                        # cmp ebx,3
    a.j8("7c", "seed_loop")
    a.b("b808000000")                    # mov eax,8
    a.label("seed_out")
    a.b("5d5f5e5b")                      # pop ebp; pop edi; pop esi; pop ebx
    a.b("c3")                            # ret

    # ---- in_bracket14: ecx = team -> eax = 1 when the team is in the bracket ------------------------
    a.label("in_bracket")
    a.b("565753")                        # push esi; push edi; push ebx
    a.b("8bf1")                          # mov esi,ecx
    _stage_row(a, "3d")                  # movzx edi,byte [stage]
    a.b("33db")                          # xor ebx,ebx
    a.label("inb_wc")
    a.b("8bcf")                          # mov ecx,edi
    a.b("8bd3")                          # mov edx,ebx
    a.call(FN_HOME)
    a.b("3bc6")                          # cmp eax,esi
    a.j8("74", "inb_yes")
    a.b("8bcf")                          # mov ecx,edi
    a.b("8bd3")                          # mov edx,ebx
    a.call(FN_AWAY)
    a.b("3bc6")                          # cmp eax,esi
    a.j8("74", "inb_yes")
    a.b("43")                            # inc ebx
    a.b("83fb06")                        # cmp ebx,6
    a.j8("7c", "inb_wc")
    a.b("33db")                          # xor ebx,ebx
    a.label("inb_div")
    a.b("8d4f01")                        # lea ecx,[edi+1]
    a.b("8bd3")                          # mov edx,ebx
    a.call(FN_HOME)
    a.b("3bc6")                          # cmp eax,esi
    a.j8("74", "inb_yes")
    a.b("43")                            # inc ebx
    a.b("83fb04")                        # cmp ebx,4
    a.j8("7c", "inb_div")
    a.b("33c0")                          # xor eax,eax
    a.j8("eb", "inb_out")
    a.label("inb_yes")
    a.b("b801000000")                    # mov eax,1
    a.label("inb_out")
    a.b("5b5f5e")                        # pop ebx; pop edi; pop esi
    a.b("c3")                            # ret
    a.label("end")
    return a


def cave_bytes() -> bytes:
    a = cave_asm()
    code = a.assemble()
    _require(len(code) <= CAVE_SIZE, f"cave is {len(code)} bytes, over {CAVE_SIZE}")
    return code + b"\xcc" * (CAVE_SIZE - len(code))


def cave_labels() -> dict[str, int]:
    a = cave_asm()
    a.assemble()
    return {name: a.va(name) for name in ("advance", "seed_of", "in_bracket", "end")}


def _jmp_to(src: int, dst: int) -> bytes:
    return b"\xe9" + struct.pack("<i", dst - (src + 5))


# --- 5. the seed-compare chains -----------------------------------------------------------------------

def chain_bytes(base: int, team_reg_modrm: str, array_disp8: str, cmp_reg_hex: str) -> bytes:
    """A 68-byte replacement for ``cmp [esp+X],reg / mov esi,N`` x6: loop over the six stack seeds,
    then test the seventh (``[LAST7]``).  esi = seed index 0..6, or 7 for 'not in'."""

    a = _Asm(base)
    a.b("33c0")                                  # xor eax,eax
    a.b("be07000000")                            # mov esi,7
    a.label("loop")
    a.b("39" + team_reg_modrm + "84" + array_disp8)  # cmp [esp+eax*4+X],reg
    a.j8("75", "next")
    a.b("8bf0")                                  # mov esi,eax
    a.label("next")
    a.b("40")                                    # inc eax
    a.b("83f806")                                # cmp eax,6
    a.j8("7c", "loop")
    a.b("3b" + cmp_reg_hex + _imm(LAST7_VA))     # cmp reg,[LAST7]
    a.j8("75", "done")
    a.b("be06000000")                            # mov esi,6
    a.label("done")
    code = a.assemble()
    _require(len(code) <= CHAIN_SIZE, "chain too long")
    return code + b"\x90" * (CHAIN_SIZE - len(code))


# --- retail bytes of every rewritten region (sha256 73105b17... default.xbe) -------------------------

RETAIL_SEED_FN = bytes.fromhex(
    "81ec880000008bc18944240483e800568bf2742e480f85cd000000b903000000e87bffffff33c98906e872ffffffb901"
    "000000894604e865ffffffb902000000eb28b907000000e854ffffffb9040000008906e848ffffffb905000000894604"
    "e83bffffffb906000000894608e82effffff5355ba040000008bce89460ce85dfeffff33ede8f6cde1ff33db85c08944"
    "240c7e39578bcbe854cee1ff8bf83b3e74213b7e04741c3b7e0874173b7e0c74128bcfe8f8bce8ff3b4424147505897c"
    "ac18458b442410433bd87cc95f8bd58d4c2414e808feffff8b4424148b4c24185d894610894e145b5e81c488000000c3"
)
RETAIL_BUILDER = bytes.fromhex(
    "8d54240c33c9e8fefeffff8d542424b901000000e8f0feffff85f67435e8f7cee1ff8bf033c08d49003974040c742339"
    "740424741d83c00483f8187cec8bcee875bce8ff85c0750689742420eb048974243833f6eb038d49008b4cb40c8bd6e8"
    "65f4e1ff4683fe067cef33f68b4cb4248d5606e851f4e1ff4683fe067ceee876cfe1ff8b4c24188bf0e8bbcde1ff8b4c"
    "241ca2c9d6ac00e8adcde1ff68c8d6ac0033d28bcea2cad6ac00e8fae9e1ff6a0133d28bcee83fd0e1ff6a0133d28bce"
    "e854d0e1ff8b4c2414e87bcde1ff8b4c2420a2d1d6ac00e86dcde1ff68d0d6ac00ba010000008bcea2d2d6ac00e8b7e9"
    "e1ff6a01ba010000008bcee8f9cfe1ff6a01ba010000008bcee80bd0e1ff8b4c2430e832cde1ff8b4c2434a2d9d6ac00"
    "e824cde1ff68d8d6ac00ba020000008bcea2dad6ac00e86ee9e1ff6a01ba020000008bcee8b0cfe1ff6a01ba02000000"
    "8bcee8c2cfe1ff8b4c242ce8e9cce1ff8b4c2438a2e1d6ac00e8dbcce1ff68e0d6ac00ba030000008bcea2e2d6ac00e8"
    "25e9e1ff6a01ba030000008bcee867cfe1ff6a01ba030000008bcee879cfe1ff8b4c240c46e89fcce1ffa2e9d6ac0068"
    "e8d6ac0033d28bcee8ece8e1ff6a0133d28bcee831cfe1ff6a0033d28bcee846cfe1ff8b4c2410e86dcce1ff68f0d6ac"
    "00ba010000008bcea2f1d6ac00e8b7e8e1ff6a01ba010000008bcee8f9cee1ff6a00ba010000008bcee80bcfe1ff8b4c"
    "2424e832cce1ff68f8d6ac00ba020000008bcea2f9d6ac00e87ce8e1ff6a01ba020000008bcee8becee1ff6a00ba0200"
    "00008bcee8d0cee1ff8b4c2428e8f7cbe1ff6800d7ac00ba030000008bcea201d7ac00e841e8e1ff6a01ba030000008b"
    "cee883cee1ff6a00ba030000008bcee895cee1ff466808d7ac0033d28bcee816e8e1ff6a0033d28bcee85bcee1ff6a00"
    "33d28bcee870cee1ff6810d7ac00ba010000008bcee8efe7e1ff6a00ba010000008bcee831cee1ff6a00ba010000008b"
    "cee843cee1ff466818d7ac0033d28bcee8c4e7e1ff6a0033d28bcee809cee1ff6a0033d28bcee81ecee1ff"
)
RETAIL_CAVE = bytes.fromhex(
    "558bec83e4f081ec0c01000056e8def0ffff8d4c24108bf0e8930ad2ff33d28d4c2410e8c80cd2ffba010000008d4c24"
    "10e85a0bd2ffbac0c0c0ff8d4c2410e89c0cd2ff33c9e89599dcff8bd08d4c2410e8ea0ad2ff680000a041680000aa43"
    "6800007f438d4c241ce8920bd2ffba010000008d4c2410e8140bd2ffbadc3cea008d4c2410e876bddcff85f6745c6800"
    "00a041680000aa43680080cf438d4c241ce85a0bd2ffba020000008d4c2410e8dc0ad2ff8bcee8b571ffffd95c240c8d"
    "44240c5068f03cea00ba400000008d8c2498000000e8c644d2ff8d9424900000008d4c2410e816bddcff680000a04168"
    "0000aa43680080d9438d4c241ce8fe0ad2ffba010000008d4c2410e8800ad2ffbafc3cea008d4c2410e8e2bcdcff85f6"
    "745c680000a041680000aa436800c014448d4c241ce8c60ad2ffba020000008d4c2410e8480ad2ff8bcee85172ffffd9"
    "5c240c8d4c240c5168f03cea00ba400000008d8c2498000000e83244d2ff8d9424900000008d4c2410e882bcdcff6800"
    "00a041680080b6436800007f438d4c241ce86a0ad2ffba010000008d4c2410e8ec09d2ffba103dea008d4c2410e84ebc"
    "dcff85f6745c680000a041680080b643680080cf438d4c241ce8320ad2ffba020000008d4c2410e8b409d2ff8bcee8bd"
    "70ffff8d54240c5268203dea00ba400000008d8c249800000089442414e89e43d2ff8d9424900000008d4c2410e8eebb"
    "dcff680000a041680080b643680080d9438d4c241ce8d609d2ffba010000008d4c2410e85809d2ffba283dea008d4c24"
    "10e8babbdcff85f6745c680000a041680080b6436800c014448d4c241ce89e09d2ffba020000008d4c2410e82009d2ff"
    "8bcee8e971ffffd95c240c8d44240c5068343dea00ba400000008d8c2498000000e80a43d2ff8d9424900000008d4c24"
    "10e85abbdcff680000a041680000c3436800007f438d4c241ce84209d2ffba010000008d4c2410e8c408d2ffba403dea"
    "008d4c2410e826bbdcff85f6745c680000a041680000c343680080cf438d4c241ce80a09d2ffba020000008d4c2410e8"
    "8c08d2ff8bcee80570ffffd95c240c8d4c240c5168343dea00ba400000008d8c2498000000e87642d2ff8d9424900000"
    "008d4c2410e8c6badcff680000a041680000c343680080d9438d4c241ce8ae08d2ffba010000008d4c2410e83008d2ff"
    "ba4c3dea008d4c2410e892badcff85f6745c680000a041680000c3436800c014448d4c241ce87608d2ffba020000008d"
    "4c2410e8f807d2ff8bcee83170ffff8d54240c5268203dea00ba400000008d8c249800000089442414e8e241d2ff8d94"
    "24900000008d4c2410e832badcff5e8be55dc3"
)
RETAIL_CLINCH_CHAIN = bytes.fromhex(
    "396c2424be06000000750233f6396c24287505be01000000396c242c7505be02000000396c24307505be03000000396c"
    "24347505be04000000396c24387505be05000000"
)
RETAIL_ELIM_CHAIN = bytes.fromhex(
    "395c2428be06000000750233f6395c242c7505be01000000395c24307505be02000000395c24347505be03000000395c"
    "24387505be04000000395c243c7505be05000000"
)
RETAIL_DISPATCH_HEAD = bytes.fromhex("e84bfdffff")        # FUN_00247690: call FUN_002473e0
RETAIL_IN_BRACKET_HEAD = bytes.fromhex("568bf133d2")      # FUN_002476c0: push esi; mov esi,ecx; xor edx,edx


# --- the site table ---------------------------------------------------------------------------------

def sites(calendar: Sequence[tuple[int, int, int, int]] = CALENDAR_2026_14) -> tuple[Site, ...]:
    labels = cave_labels()
    return (
        Site("seed_seven", SEED_FN_VA, RETAIL_SEED_FN, seed_fn_bytes(),
             "FUN_002a7d60 rewritten: out[0..5] as retail, the seventh seed in [0xE57924]"),
        Site("bracket_builder", BUILDER_VA, RETAIL_BUILDER, builder_bytes(calendar),
             "FUN_002a7e50 0x2A7E57..0x2A8152: 14 seeds, 6 wild-card games, #1 seeds at home in the "
             "divisional round, own 13 kickoff records, rejoins the retail tail"),
        Site("advance_cave", CAVE_VA, RETAIL_CAVE, cave_bytes(),
             "dead FUN_00325e70: advance14 (reseeded divisional/conference/Super Bowl fill), seed_of, "
             "in_bracket14"),
        Site("advance_hook", DISPATCH_VA, RETAIL_DISPATCH_HEAD, _jmp_to(DISPATCH_VA, labels["advance"]),
             "FUN_00247690 -> jmp advance14 (the seven retail fillers become dead code)"),
        Site("in_bracket_hook", IN_BRACKET_VA, RETAIL_IN_BRACKET_HEAD, _jmp_to(IN_BRACKET_VA, labels["in_bracket"]),
             "FUN_002476c0 -> jmp in_bracket14 (six wild-card games, four divisional hosts)"),
        Site("clinch_chain", CLINCH_CHAIN_VA, RETAIL_CLINCH_CHAIN, chain_bytes(CLINCH_CHAIN_VA, "6c", "24", "2d"),
             "FUN_00132ed0: seed lookup loop over seeds 1..6 plus the seventh; 7 = not in"),
        Site("clinch_mode_mask", CLINCH_MODE_MASK_VA, bytes.fromhex("83e306"), bytes.fromhex("83e307"),
             "FUN_00132ed0: and ebx,6 -> 7 (the 'not in' sentinel for the best-case scan)"),
        Site("clinch_sentinel_a", CLINCH_SENTINEL_A_VA, bytes.fromhex("83fe06"), bytes.fromhex("83fe07"),
             "FUN_00132ed0: cmp esi,6 -> 7"),
        Site("clinch_sentinel_b", CLINCH_SENTINEL_B_VA, bytes.fromhex("83fe06"), bytes.fromhex("83fe07"),
             "FUN_00132ed0: cmp esi,6 -> 7"),
        Site("clinch_bye_level", CLINCH_BYE_LEVEL_VA, bytes.fromhex("83fb02"), bytes.fromhex("83fb01"),
             "FUN_00132ed0: only the #1 seed returns level 4; seeds 2-4 -> 2 (division), 5-7 -> 1 (berth)"),
        Site("elim_chain", ELIM_CHAIN_VA, RETAIL_ELIM_CHAIN, chain_bytes(ELIM_CHAIN_VA, "5c", "28", "1d"),
             "FUN_00133cf0: seed lookup loop plus the seventh seed"),
        Site("elim_sentinel", ELIM_SENTINEL_VA, bytes.fromhex("83fe06"), bytes.fromhex("83fe07"),
             "FUN_00133cf0: cmp esi,6 -> 7"),
        Site("picture_final_field", PICTURE_FINAL_COUNT_VA, bytes.fromhex("b802000000"), bytes.fromhex("b803000000"),
             "cb_00368395: the Playoff Picture lists seven teams per conference after the regular season"),
    )


def site_table(calendar: Sequence[tuple[int, int, int, int]] = CALENDAR_2026_14) -> list[dict[str, object]]:
    rows = []
    for site in sites(calendar):
        rows.append({"group": "playoffs_14", "label": site.label, "va": f"0x{site.va:08x}", "size": site.size,
                     "retail": site.retail.hex() if site.size <= 8 else f"<{site.size} retail bytes>",
                     "patched": site.patched.hex() if site.size <= 8 else f"<{site.size} bytes>", "note": site.note})
    return rows


def code_report(calendar: Sequence[tuple[int, int, int, int]] = CALENDAR_2026_14) -> dict[str, object]:
    labels = cave_labels()
    return {"seed_fn_bytes": len(seed_fn_bytes().rstrip(b"\xcc")), "seed_fn_capacity": SEED_FN_SIZE,
            "builder_bytes": len(builder_bytes(calendar).rstrip(b"\xcc")), "builder_capacity": BUILDER_SIZE,
            "cave_bytes": labels["end"] - CAVE_VA, "cave_capacity": CAVE_SIZE,
            "cave_labels": {k: f"0x{v:x}" for k, v in labels.items()},
            "seeds_per_conference": SEEDS_PER_CONFERENCE, "wild_card_games": WILD_CARD_GAMES,
            "postseason_games": POSTSEASON_GAMES_14, "runtime_verified": False}


__all__ = ["CALENDAR_2026_14", "CALENDAR_RETAIL_14", "CAVE_SIZE", "CAVE_VA", "GAME_TABLE", "LAST7_VA",
           "POSTSEASON_GAMES_14", "POSTSEASON_LABELS_14", "SEEDS_PER_CONFERENCE", "STAGE_SEASON_WEEKS_VA",
           "Playoffs14Error", "Site", "WILD_CARD_GAMES", "builder_bytes", "cave_bytes", "cave_labels",
           "chain_bytes", "code_report", "date_table_14", "game_table_bytes", "seed_fn_bytes", "site_table",
           "sites"]

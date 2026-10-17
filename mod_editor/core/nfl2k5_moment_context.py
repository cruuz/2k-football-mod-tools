"""ESPN 25th Anniversary moment context: the Super Bowl flag and the real game's stats so far. EXPERIMENTAL / UNWITNESSED.

Noah, 2026-10-17: "The commentary should be aware that these specific moments are the Super Bowl", and "When you
finish a moment, it'll have the stats and highlights not as if you just started the game; it should have the
historical stats baked in to the situation."

Super Bowl context (static RE, b775 job mo2)
--------------------------------------------
* 0x65D30 is the game's one game-type classifier: 0 for game mode 8 (the 25th Anniversary and the Situation mode),
  1 for mode 3, 2 for ordinary games and the preseason, and in season modes 3 (regular week), 4 wild card,
  5 divisional, 6/7 AFC/NFC championship, 8 Super Bowl (season stage 9, week row 0x14) and 9 Pro Bowl. It is also
  DRCT global variable 429 (the script variable table at 0xA8D850 lists it): expression 107 of the in-game
  director (outer 4), expression 1 of the intro director (outer 1194) and expression 8 of the halftime director
  (outer 1195) read it. Code callers: the stadium music playlist (0xA5526, 0xA57AA), the pregame big-helmet scene
  (0x125884, 0x1258FD) and the postgame scene cleanup (0x125BD6, 0x125C10). The pregame scene (0x125700) runs only
  in modes 4 to 7, so a moment never shows a pregame show either way.
* 0xF4650 names the game ("Situation", "Exhibition", "Super Bowl", "Week %d" ...) for the in-game header.
* 0x133A30 (stage 9 and week row 0x14) is the franchise's own Super Bowl test; it feeds franchise records only
  (coach and team Super Bowl counts, postgame franchise events), so it is NOT touched: a moment is not a franchise
  game and nothing may be written into a franchise.
This owner makes 0x65D30 return 8 and 0xF4650 return "Super Bowl" when, and only when, game mode is 8, the
situation flag 0xE6014C is 0 (an Anniversary moment, not the Situation mode, which stores 1) and the selected
physical row (0xBF1858) is one of the 17 Super Bowl moments. Everything else reads exactly as retail. Score,
clock, possession and the moment's rules come from SITU and are untouched. No field art is involved: retail draws
the "playoff_logo" field node only in game mode 6 and the AFC/NFC shields from the franchise week (0x9C6C4,
0x9C731), so Super Bowl field and wall art stays with the venue owners.

Historical stats (static RE)
----------------------------
Every live game number the box score, the player cards, the stat overlays and the post-game screens show goes
through two readers: 0xCB240 (player record, stat id, bank) and 0xCB2D0 (team record, stat id, bank). Bank 0 is
the current game; banks 0..7 reach 0xCA470 (player) / 0xCB080 (team) through the call sites 0xCB295 / 0xCB31F.
Derived ids (>= 0xB7: total yards, completion %, yards per carry, QB rating, total sacks, 3rd-down %, ...) are
formulas (table 0xA8B918) over the same readers, so they follow. The live players are the 84-byte records at
0xB30C4C (home, 65) and 0xB321A0 (away, 65), copied at kickoff by 0xC3C60 in the order of the moment team's player
list; the live teams are 0xB30864 (home) and 0xB30A58 (away).

This owner adds a per-moment baseline at those two call sites for bank 0 only: player keys 0..64 (home live index)
and 65..129 (away), team keys 0xFE (home) and 0xFF (away). Season, career and history banks, the save path and the
franchise merge never see it. The baselines are built from data/nfl2k5_moment_stats.json (sourced play-by-play cut
at the moment's first play) and the moment rosters on the disc being built (player names mapped to the team file's
own slot order, the order 0xC3C60 copies). They travel in SITU right after the moment-coach block ("MST1" after
"MCO1" behind each objective text). At selection (0x20CC05, inside the select handler, SITU alive) the selected
row's block is copied into one 2 KiB block taken once from the game's main heap (0x48700 on 0xB04E24) and kept for
the session; the 16-byte state remembers that block and which row it belongs to. A reader adds a baseline only in
game mode 8 with situation flag 0 and the armed row equal to the selected row.

XBE space: the allocator is full (b77), so the code lives in a retail function pair with no reference anywhere in the
image (0x33F2A0..0x33F42F, two unreferenced block-cipher routines; the bytewise rel/abs scans find only a false hit
inside an LEA at 0x33F25B), pinned by its retail sha256 like the dynamic kickoff and overtime caves. The state is a
16-byte late RW owner in the legacy RW page tail.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import struct
import unicodedata

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_moment_context"
DATA_SIZE = 16
REQUESTS = ((OWNER, "data", DATA_SIZE, 16),)
ROOT = Path(__file__).resolve().parents[2]
STATS_JSON = ROOT / "data/nfl2k5_moment_stats.json"

CAVE_VA = 0x33F2A0
CAVE_SIZE = 0x190
RETAIL_CAVE_SHA256 = "a3ba1124042203c94896a75de6c11968a8229170628ec1b483de9ec95e880c10"

MODE, SITUATION_FLAG, MOMENT = 0xE5FF80, 0xE6014C, 0xBF1858
LIVE_TEAMS = (0xB30864, 0xB30A58)
LIVE_PLAYERS, PLAYER_SIZE, LIVE_SLOTS = 0xB30C4C, 0x54, 130
MAIN_HEAP, HEAP_ALLOC = 0xB04E24, 0x48700
PLAYER_LIVE, TEAM_LIVE = 0xCA470, 0xCB080
GAME_TYPE_BACK = 0x65D3D          # retail continues here for modes other than 8 (eax = mode)
TITLE_BACK = 0xF4660              # pop ecx; ret
SELECT_BACK = 0x20CC0B
SITUATION_TEXT, SUPER_BOWL_TEXT = 0xE6BC24, 0xE6BC64   # L"Situation", L"Super Bowl" in .string_
BUFFER_SIZE = 2048
MAX_ENTRIES = (BUFFER_SIZE - 4) // 4
COACH_MAGIC, COACH_SIZE = b"MCO1", 4 + 2 * 84
MAGIC = b"MST1"
HOME_TEAM_KEY, AWAY_TEAM_KEY = 0xFE, 0xFF

# (label, va, retail bytes)
HOOKS = (
    ("game_type", 0x65D30, bytes.fromhex("a180ffe500")),
    ("title", 0xF465B, bytes.fromhex("b824bce600")),
    ("select", 0x20CC05, bytes.fromhex("8b461083f8ff")),
    ("player_stat", 0xCB295, bytes.fromhex("e8d6f1ffff")),
    ("team_stat", 0xCB31F, bytes.fromhex("e85cfdffff")),
)
SUPER_BOWL_ROWS = (14, 15, 21, 22, 23, 27, 28, 29, 30, 34, 35, 40, 42, 45, 46, 48, 50)
SUPER_BOWL_TITLES = {14: "SUPER BOWL XXIII", 15: "WIDE RIGHT", 21: "SUPER BOWL XXXII", 22: "A YARD TOO SHORT",
                     23: "VINATIERI STRIKES AGAIN", 27: "SUPER BOWL XLII: TYREE", 28: "SUPER BOWL XLIII: HOLMES",
                     29: "SUPER BOWL XLVI: SIDELINE", 30: "SUPER BOWL LI: 28-3", 34: "SUPER BOWL XXXVIII: FINALE",
                     35: "SUPER BOWL XLIV: AMBUSH", 40: "SUPER BOWL XLVII: HOLD ON", 42: "SUPER BOWL XLIX: BUTLER",
                     45: "SUPER BOWL LII: PHILLY", 46: "SUPER BOWL LIV: WASP", 48: "SUPER BOWL LVI: DONALD",
                     50: "SUPER BOWL LVIII: OVERTIME"}
UI_TEXT = ("EXPERIMENTAL / UNWITNESSED. With the more moments: the 17 Super Bowl moments are played as the Super Bowl "
           "(the booth's and the presentation's game type), and 35 moments start with the real game's stats up to "
           "that point (sourced play-by-play) in the box score and player stats.")


class MomentContextError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise MomentContextError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def super_bowl_mask():
    mask = 0
    for row in SUPER_BOWL_ROWS:
        mask |= 1 << (row - 1)
    return mask


# ------------------------------------------------------------------------------------------------ assembly
class _Asm:
    """Tiny x86 emitter: raw hex, labels, rel8/rel32 branches to labels or absolute targets."""

    def __init__(self, base):
        self.base, self.items, self.labels = base, [], {}

    def b(self, hexs):
        self.items.append(bytes.fromhex(hexs.replace(" ", "")))

    def u32(self, value):
        self.items.append(struct.pack("<I", value & 0xFFFFFFFF))

    def label(self, name):
        self.items.append(("label", name))

    def j8(self, op, target):
        self.items.append(("j8", bytes.fromhex(op), target))

    def j32(self, op, target):
        self.items.append(("j32", bytes.fromhex(op), target))

    def _size(self, it):
        if isinstance(it, bytes):
            return len(it)
        return 0 if it[0] == "label" else 2 if it[0] == "j8" else len(it[1]) + 4

    def assemble(self):
        pos = 0
        for it in self.items:
            if isinstance(it, tuple) and it[0] == "label":
                self.labels[it[1]] = pos
            pos += self._size(it)
        out = bytearray()
        for it in self.items:
            if isinstance(it, bytes):
                out += it
                continue
            if it[0] == "label":
                continue
            target = it[2]
            dest = self.labels[target] + self.base if isinstance(target, str) else target
            here = self.base + len(out)
            if it[0] == "j8":
                rel = dest - (here + 2)
                require(-128 <= rel <= 127, f"rel8 out of range to {target}")
                out += it[1] + struct.pack("<b", rel)
            else:
                out += it[1] + struct.pack("<i", dest - (here + len(it[1]) + 4))
        return bytes(out), {k: v + self.base for k, v in self.labels.items()}


def _imm(v):
    return struct.pack("<I", v & 0xFFFFFFFF).hex()


def code_for(cave, state):
    """The whole owner in the cave. state: +0 heap block, +4 armed physical row index (or -1)."""
    a = _Asm(cave)
    # --- 0x65D30: game type. Modes other than 8 continue retail at 0x65D3D with EAX = mode.
    a.label("game_type")
    a.b("a1" + _imm(MODE))                      # mov eax,[mode]
    a.b("83f808")                               # cmp eax,8
    a.j32("0f85", GAME_TYPE_BACK)               # jne retail
    a.j32("e9", "super_bowl")                   # tail: eax = 8 or 0, ret to the caller of 0x65D30
    # --- 0xF465B: the mode-8 title. ECX was pushed by 0xF4650; 0xF4660 pops it and returns.
    a.label("title")
    a.j32("e8", "super_bowl")
    a.b("85c0")                                 # test eax,eax
    a.b("b8" + _imm(SITUATION_TEXT))
    a.j8("74", "title_done")
    a.b("b8" + _imm(SUPER_BOWL_TEXT))
    a.label("title_done")
    a.j32("e9", TITLE_BACK)
    # --- predicate: EAX = 8 for a Super Bowl moment, else 0. Called only in mode 8. Keeps every other register.
    a.label("super_bowl")
    a.b("33c0")                                 # xor eax,eax
    a.b("3905" + _imm(SITUATION_FLAG))          # cmp [flag],eax
    a.j8("75", "sb_out")
    a.b("51")                                   # push ecx
    a.b("8b0d" + _imm(MOMENT))                  # mov ecx,[moment]
    a.b("83f940")                               # cmp ecx,64
    a.j8("73", "sb_pop")
    a.items.append(("bt",))                     # placeholder replaced below
    a.j8("73", "sb_pop")                        # jnc
    a.b("b008")                                 # mov al,8
    a.label("sb_pop")
    a.b("59")                                   # pop ecx
    a.label("sb_out")
    a.b("c3")
    # --- 0x20CC05 (select handler; ESI = the selected SITU record, still loaded): copy this row's baselines.
    # A row without a block leaves the state alone: the armed row then differs from the selected one.
    a.label("select")
    a.b("60")                                   # pushad (the displaced cmp rebuilds the flags)
    a.b("8b7e08")                               # mov edi,[esi+8]   the objective text
    a.b("85ff")
    a.j8("74", "sel_done")
    a.b("fc33c0b900020000f266af")               # cld; xor eax,eax; mov ecx,512; repne scasw (EDI past the NUL)
    a.j8("75", "sel_done")
    a.b("813f" + COACH_MAGIC.hex())             # cmp dword [edi],'MCO1'
    a.j8("75", "sel_nocoach")
    a.b("81c7" + _imm(COACH_SIZE))              # skip the coach block
    a.label("sel_nocoach")
    a.b("813f" + MAGIC.hex())                   # cmp dword [edi],'MST1'
    a.j8("75", "sel_done")
    a.b("0fb74f04")                             # movzx ecx,word [edi+4]  (entry count)
    a.b("f6c5fe")                               # test ch,0xFE: refuse 512 entries or more
    a.j8("75", "sel_done")
    a.b("8d7704")                               # lea esi,[edi+4]   count, reserved, entries
    a.b("a1" + _imm(state))                     # mov eax,[state]   the session block
    a.b("85c0")
    a.j8("75", "sel_have")
    a.b("51")                                   # push ecx
    a.b("b9" + _imm(MAIN_HEAP))                 # ecx = main heap
    a.b("ba" + _imm(BUFFER_SIZE))               # edx = size
    a.j32("e8", HEAP_ALLOC)                     # keeps ESI and EDI
    a.b("59")                                   # pop ecx
    a.b("85c0")
    a.j8("74", "sel_done")
    a.b("a3" + _imm(state))
    a.label("sel_have")
    a.b("8bf8")                                 # mov edi,eax
    a.b("8d0c8d04000000")                       # lea ecx,[ecx*4+4]
    a.b("f3a4")                                 # rep movsb
    a.b("a1" + _imm(MOMENT))
    a.b("a3" + _imm(state + 4))                 # arm with the selected row
    a.label("sel_done")
    a.b("61")                                   # popad
    a.b("8b461083f8ff")                         # the two displaced instructions
    a.j32("e9", SELECT_BACK)
    # --- 0xCB295: player live value (EAX = stat, ECX = bank, [esp+4] = player); ret 4 like 0xCA470.
    # EBX and EDI are free: 0xCB29A pops both before returning.
    a.label("player_stat")
    a.b("51" "50" "ff74240c")                   # push bank; push stat; push the player argument
    a.j32("e8", PLAYER_LIVE)                    # st0 = live value (ret 4)
    a.b("5b59")                                 # pop ebx (stat); pop ecx (bank)
    a.b("85c9")
    a.j8("75", "ps_out")                        # bank 0 (this game) only
    a.b("8b442404")                             # mov eax,[esp+4]
    a.b("2d" + _imm(LIVE_PLAYERS))              # sub eax,first live record
    a.b("3d" + _imm(LIVE_SLOTS * PLAYER_SIZE))
    a.j8("73", "ps_out")
    a.b("33d2" "b9" + _imm(PLAYER_SIZE) + "f7f1")   # eax = live index, edx = remainder
    a.b("85d2")
    a.j8("75", "ps_out")                        # not a record start
    a.b("8bc8" "8bd3")                          # ecx = key, edx = stat
    a.j32("e8", "look")
    a.label("ps_out")
    a.b("c20400")
    # --- 0xCB31F: team live value (EAX = stat, ECX = bank, [esp+4] = team); ret 4 like 0xCB080.
    a.label("team_stat")
    a.b("51" "50" "ff74240c")
    a.j32("e8", TEAM_LIVE)
    a.b("5a59" "85c9")                          # pop edx (stat); pop ecx (bank)
    a.j8("75", "ts_out")
    a.b("8b442404")                             # mov eax,[esp+4]
    a.b("b1" + "%02x" % HOME_TEAM_KEY)          # mov cl,0xFE
    a.b("3d" + _imm(LIVE_TEAMS[0]))
    a.j8("74", "ts_go")
    a.b("fec1")                                 # inc cl -> 0xFF
    a.b("3d" + _imm(LIVE_TEAMS[1]))
    a.j8("75", "ts_out")
    a.label("ts_go")
    a.j32("e8", "look")
    a.label("ts_out")
    a.b("c20400")
    # --- look: CL = key, DL = stat; ST0 += i16 baseline. Saves EAX, ESI and EDI.
    a.label("look")
    a.b("505657")                               # push eax; push esi; push edi (callers do not read flags)
    a.b("833d" + _imm(MODE) + "08")
    a.j8("75", "lk_out")
    a.b("833d" + _imm(SITUATION_FLAG) + "00")
    a.j8("75", "lk_out")
    a.b("a1" + _imm(state + 4))
    a.b("3b05" + _imm(MOMENT))
    a.j8("75", "lk_out")
    a.b("8b35" + _imm(state))                   # mov esi,[state]
    a.b("85f6")
    a.j8("74", "lk_out")
    a.b("0fb73e")                               # movzx edi,word [esi]
    a.b("83c604")
    a.label("lk_loop")
    a.b("85ff")
    a.j8("74", "lk_out")
    a.b("380e")                                 # cmp [esi],cl
    a.j8("75", "lk_next")
    a.b("385601")                               # cmp [esi+1],dl
    a.j8("75", "lk_next")
    a.b("de4602")                               # fiadd word [esi+2]
    a.j8("eb", "lk_out")
    a.label("lk_next")
    a.b("83c6044f")                             # add esi,4; dec edi
    a.j8("eb", "lk_loop")
    a.label("lk_out")
    a.b("5f5e58" "c3")                          # pop edi; pop esi; pop eax; ret
    a.label("mask")
    a.items.append(struct.pack("<Q", super_bowl_mask()))
    # bt dword [mask],ecx needs the mask's absolute address: place the mask first, then emit the instruction
    a.items = [("btmask",) if it == ("bt",) else it for it in a.items]
    pos, mask_at = 0, None
    for it in a.items:
        if isinstance(it, tuple) and it[0] == "label" and it[1] == "mask":
            mask_at = pos
        pos += 7 if it == ("btmask",) else a._size(it)
    a.items = [bytes.fromhex("0fa30d") + struct.pack("<I", cave + mask_at) if it == ("btmask",) else it
               for it in a.items]
    code, labels = a.assemble()
    require(len(code) <= CAVE_SIZE, f"moment context code {len(code)} exceeds the {CAVE_SIZE}-byte cave")
    return code.ljust(CAVE_SIZE, b"\xcc"), labels


def hook_bytes(label, labels):
    va, before = next((v, b) for n, v, b in HOOKS if n == label)
    target = labels[label]
    op = b"\xe8" if label in ("player_stat", "team_stat") else b"\xe9"
    return (op + struct.pack("<i", target - va - 5)).ljust(len(before), b"\x90")


# ------------------------------------------------------------------------------------------------ install
def allocation(payload):
    found = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not found:
        return None
    require(len(found) == 1 and (found[0]["kind"], found[0]["size"]) == ("data", DATA_SIZE),
            "foreign moment context allocation")
    return found[0]


def _views(payload):
    """(label, va, retail, installed) for every site, using the installed state's addresses."""
    owned = allocation(payload)
    labels = code_for(CAVE_VA, owned["va"] if owned else 0)[1]
    return [(n, va, before, hook_bytes(n, labels)) for n, va, before in HOOKS]


def status(payload):
    try:
        image = XbeImage(payload)
        cave = image.read(CAVE_VA, CAVE_SIZE)
        hooks = [image.read(va, len(before)) for _n, va, before in HOOKS]
        if sha(cave) == RETAIL_CAVE_SHA256:
            require(all(h == before for h, (_n, _v, before) in zip(hooks, HOOKS)), "foreign moment context hook")
            return "retail"
        owned = allocation(payload)
        require(owned is not None, "moment context code without its state")
        require(cave == code_for(CAVE_VA, owned["va"])[0], "foreign moment context cave")
        require(image.read(owned["va"], DATA_SIZE) == bytes(DATA_SIZE), "foreign initial moment context state")
        require(all(h == after for h, (_n, _v, _b, after) in zip(hooks, _views(payload))),
                "mixed moment context hooks")
        return "applied"
    except (MomentContextError, ValueError, KeyError, struct.error, StopIteration):
        return "foreign"


def view_edits(payload):
    """For owners that hash a span containing one of these sites: [(label, va, retail, installed)] once applied."""
    if status(payload) != "applied":
        return []
    return _views(payload)


def underlying(payload, labels=("select", "player_stat")):
    """A copy with the named installed hooks put back to retail (for the guards of the moments and MyCareer)."""
    state = status(payload)
    require(state != "foreign", "foreign moment context")
    if state == "retail":
        return payload
    out, image = bytearray(payload), XbeImage(payload)
    for name, va, before, _after in _views(payload):
        if name in labels:
            at = image.offset(va, len(before))
            out[at:at + len(before)] = before
    return seal(out)


def seal(out):
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    return bytes(out)


def apply(payload):
    initial = status(payload)
    require(initial != "foreign", "foreign moment context installation; rebuild from base")
    if initial == "applied":
        return payload, dict(status="already_applied", changed_bytes=0)
    before = payload
    if allocation(payload) is None:
        payload, _ = space.extend_scaleout(payload, REQUESTS)
    owned = allocation(payload)
    code, labels = code_for(CAVE_VA, owned["va"])
    out, image = bytearray(payload), XbeImage(payload)
    at = image.offset(CAVE_VA, CAVE_SIZE)
    out[at:at + CAVE_SIZE] = code
    for name, va, retail in HOOKS:
        at = image.offset(va, len(retail))
        require(bytes(out[at:at + len(retail)]) == retail, f"{name}: hook site is not retail")
        out[at:at + len(retail)] = hook_bytes(name, labels)
    result = seal(out)
    require(status(result) == "applied" and space.status(result) == "applied", "moment context readback")
    require(len(result) == len(before), "moment context grew the XBE")
    return result, dict(status="applied", changed_bytes=sum(x != y for x, y in zip(before, result)),
                        state_va=owned["va"], cave_va=CAVE_VA, code_bytes=len(code.rstrip(b"\xcc")),
                        super_bowl_rows=list(SUPER_BOWL_ROWS), labels={k: hex(v) for k, v in labels.items()})


def image_plan(target):
    """[(offset, bytes)] that install this owner in the disc image's default.xbe (only the differing runs)."""
    from .nfl2k5_music_archive import Disc
    with Disc(target, descriptors=()) as disc:
        e = disc.entries["default.xbe"]
        before = disc.read(e.size, e.byte_offset)
        after, receipt = apply(before)
        writes, i = [], 0
        while i < len(before):
            if before[i] == after[i]:
                i += 1
                continue
            start = i
            while i < len(before) and before[i] != after[i]:
                i += 1
            writes.append((e.byte_offset + start, after[start:i]))
    receipt["writes"] = [dict(offset=at, size=len(raw), sha256=sha(raw)) for at, raw in writes]
    return writes, receipt


def apply_to_image(target):
    """Install on a built copy; every write is read back and the replay must be empty."""
    from .nfl2k5_music_archive import write_all
    from . import platform_compat as io
    writes, receipt = image_plan(target)
    with Path(target).open("r+b") as f:
        for at, raw in writes:
            write_all(f.fileno(), raw, at)
            require(io.pread(f.fileno(), len(raw), at) == raw, "moment context image readback")
        os.fsync(f.fileno())
    replay, _ = image_plan(target)
    require(not replay, "moment context image replay must be empty")
    receipt["bytes_written"] = sum(len(raw) for _, raw in writes)
    return receipt


def image_status(target):
    from .nfl2k5_music_archive import Disc
    with Disc(target, descriptors=()) as disc:
        e = disc.entries["default.xbe"]
        return status(disc.read(e.size, e.byte_offset))


# ------------------------------------------------------------------------------------------------ baselines
def stats_doc():
    doc = json.loads(STATS_JSON.read_text(encoding="utf-8"))
    require(doc.get("schema") == "nfl2k5_moment_stats/v1" and len(doc["moments"]) == 51, "foreign moment stats")
    return doc


_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def name_key(first, last):
    text = unicodedata.normalize("NFKD", f"{first} {last}").encode("ascii", "ignore").decode().lower()
    text = _SUFFIX.sub("", re.sub(r"[^a-z ]", "", text.replace("-", " ")))
    return " ".join(text.split())


def last_key(last):
    return name_key("", last)


def map_players(source_players, roster):
    """source players of one side -> {source index: roster slot}; roster: [(first, last)] in slot order.

    Candidate names are the source's display name and its legal first/last (nflverse lists Antonio Romo as
    'Tony Romo'); the display name is tried first. An exact full name wins; otherwise a unique surname with the same
    first initial, where a roster surname cut with a period ('Rodgers-C.') matches its full form. Anything else stays
    in the team totals only."""
    full = {}
    for slot, (first, last) in enumerate(roster):
        full.setdefault(name_key(first, last), []).append(slot)
    out, notes = {}, []
    for i, p in enumerate(source_players):
        cands = []
        parts = (p.get("name") or "").split()
        if len(parts) >= 2:
            cands.append((parts[0], " ".join(parts[1:])))
        if p.get("first") and p.get("last"):
            cands.append((p["first"], p["last"]))
        exact = next((hits for f, l in cands if len(hits := full.get(name_key(f, l), [])) == 1), None)
        if exact:
            out[i] = exact[0]
            continue
        loose = {s for f, l in cands for s, (rf, rl) in enumerate(roster)
                 if rf[:1].lower() == f[:1].lower() and (last_key(rl) == last_key(l) or (
                     rl.endswith(".") and len(rl) > 3 and last_key(l).startswith(last_key(rl[:-1]))))}
        if len(loose) == 1:
            slot = loose.pop()
            out[i] = slot
            notes.append(f"{p['name']} -> {roster[slot][0]} {roster[slot][1]} (surname and initial)")
    return out, notes


def block_for(moment, rosters):
    """SITU trailer for one physical row: MST1, u16 count, u16 0, then (key, stat, i16 value) entries.

    rosters: {'home': [(first, last)], 'away': [(first, last)]} in the moment team files' slot order."""
    ids = stats_doc()["stat_ids"]
    entries, receipt = [], {"row": moment["row"], "mapped": 0, "team_only": [], "notes": []}
    for side, key in (("home", HOME_TEAM_KEY), ("away", AWAY_TEAM_KEY)):
        for stat, value in sorted(moment["team"].get(side, {}).get("stats", {}).items()):
            entries.append((key, ids[stat], value))
    for side, base in (("home", 0), ("away", 65)):
        mine = [p for p in moment["players"] if p["side"] == side]
        mapping, notes = map_players(mine, rosters[side])
        receipt["notes"] += notes
        for i, p in enumerate(mine):
            slot = mapping.get(i)
            if slot is None or slot >= 65:
                receipt["team_only"].append(f"{side}: {p['name']}")
                continue
            receipt["mapped"] += 1
            for stat, value in sorted(p["stats"].items()):
                entries.append((base + slot, ids[stat], value))
    require(len(entries) <= MAX_ENTRIES, f"row {moment['row']}: {len(entries)} baselines exceed {MAX_ENTRIES}")
    out = bytearray(MAGIC + struct.pack("<HH", len(entries), 0))
    for key, stat, value in entries:
        require(0 <= stat < 0xB7 and -32768 <= value <= 32767, "baseline outside the native reader's range")
        out += struct.pack("<BBh", key, stat, value)
    receipt["entries"] = len(entries)
    return bytes(out), receipt


def parse_block(raw, at=0):
    require(raw[at:at + 4] == MAGIC, "no moment stats block")
    count = struct.unpack_from("<H", raw, at + 4)[0]
    return [struct.unpack_from("<BBh", raw, at + 8 + 4 * i) for i in range(count)]


def trailer_after_coaches(text_tail):
    """Bytes of an existing MST1 trailer that follows a coach block (for the coach SITU writer to keep)."""
    if text_tail[:4] != COACH_MAGIC:
        return b""
    t = text_tail[COACH_SIZE:]
    if t[:4] != MAGIC:
        return b""
    count = struct.unpack_from("<H", t, 4)[0]
    return bytes(t[:8 + 4 * count])


def moment_team_files(main_rost, situ, data):
    """{physical row: {'away': file name, 'home': file name}}, resolved the way 20BD80 and the moments table do."""
    from . import nfl2k5_espn25_more_moments as mm
    from . import nfl2k5_espn25_scenarios as sc
    retail = {(d["selector"].lower(), d["year"]): d["filename"] for d in mm._retail_descriptors(main_rost)}
    new = {}
    for key, filename, _entry, selector, _ident in mm.table_entries(data):
        new[(selector.lower(), data.teams[key]["season"])] = filename
    body = situ[32:32 + struct.unpack_from("<I", situ, 4)[0]]
    count = struct.unpack_from("<I", situ, 8)[0]
    out = {}
    for i in range(count):
        at = sc.RECORDS + i * sc.STRIDE
        sides = {}
        for side, name_field, year_field in (("away", 0x14, 0x1C), ("home", 0x18, 0x20)):
            name = sc.utf16(body, sc.rel(body, at + name_field)).lower()
            year = struct.unpack_from("<I", body, at + year_field)[0]
            hit = new.get((name, year)) if i >= mm.RETAIL_COUNT else None
            sides[side] = hit or retail.get((name, year))
            require(sides[side] is not None, f"row {i + 1}: no team file for {name} {year}")
        out[i + 1] = sides
    return out


def roster_names(team_file_raw):
    from . import nfl2k5_roster_records as rr
    doc = rr.RosterDocument(team_file_raw[32:])
    return [(p.first, p.last) for p in doc.team_players(0)]


def stat_blocks(disc):
    """{physical row: SITU trailer} for every seeded moment on an open archive.Disc, plus a mapping receipt."""
    from . import nfl2k5_espn25_more_moments as mm
    data = mm.Data.load()
    entries = disc.archive_entries
    main = disc.read_entry_range(entries[5], 0, entries[5].size)
    situ_e = entries[22]
    situ = disc.read_entry_range(situ_e, 0, situ_e.size)
    files = moment_team_files(main, situ, data)
    by_id = {e.name_id: e for e in entries}
    cache = {}

    def names(filename):
        if filename not in cache:
            e = by_id[mm.name_id(filename)]
            cache[filename] = roster_names(disc.read_entry_range(e, 0, e.size))
        return cache[filename]

    blocks, receipts = {}, []
    for moment in stats_doc()["moments"]:
        if moment["status"] != "seeded":
            receipts.append({"row": moment["row"], "entries": 0, "reason": moment["status"]})
            continue
        sides = files[moment["row"]]
        raw, receipt = block_for(moment, {s: names(sides[s]) for s in ("home", "away")})
        receipt["files"] = sides
        blocks[moment["row"]] = raw
        receipts.append(receipt)
    return blocks, receipts


__all__ = ["OWNER", "REQUESTS", "HOOKS", "CAVE_VA", "CAVE_SIZE", "SUPER_BOWL_ROWS", "UI_TEXT", "apply", "status",
           "underlying", "view_edits", "code_for", "block_for", "stat_blocks", "parse_block", "trailer_after_coaches",
           "moment_team_files", "map_players", "super_bowl_mask", "image_plan", "apply_to_image", "image_status"]

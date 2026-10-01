"""Beta 76 research (job s13): where a Franchise game's team records come from, for the sprite scorebug.

Retail 2K5 keeps no per-team W-L-T table. Every record it shows is recomputed from the schedule grid
(0xE57C40, 22 rows x 17 slots x 8 bytes: type, home index, away index, month, day, year, hour, minute)
and the quarter scores (0xE587F0, five home bytes then five away bytes per game) by the season summers
FUN_000c7720 / 7750 / 7780. They take a LEAGUE team record pointer (``[0xE5786C + index * 4]`` in a
Franchise), never the in-game copies at 0xB30864 / 0xB30A58.

These tests pin every retail span the research relies on by SHA-256 (no retail bytes live here) and run
the retail code under Unicorn on a synthetic season:

* the summers equal a Python mirror of the grid, ties included, with a played postseason game counted
  and unplayed fixtures ignored; with no games played every team reads 0-0;
* the fixture getters FUN_000c4e00 / 4e20 return the league pointers of grid byte 1 (home) and byte 2
  (away);
* the fixture game start FUN_000c73b0 stages byte 1 into ``[0xE5FE68]`` (HOME) and byte 2 into
  ``[0xE5FE6C]`` (AWAY) and sets the game-mode word 0xE5FF80 to 7 (preseason and regular season),
  6 (postseason) or 5 (tournament);
* FUN_000617e0 copies ``[0xE5FE68]`` to the home context 0xB30864 and ``[0xE5FE6C]`` to the away
  context 0xB30A58, and the summers read such a copy as 0-0-0;
* the retail wide formatter 0x4A400 with the format pair at 0xE68C28 / 0xE68C34 writes UTF-16 "W-L",
  or "W-L-T" when there are ties;
* FUN_000c6b70 / 6c30 are the standings' HOME and AWAY split columns (home games only, road games
  only), so they are not the scorebug record; FUN_00341e20 always prints three fields;
* the in-game ESPN ticker line FUN_00100850 shows the entering record while a game is live and the
  post-game record once it is final, the same convention the 2026 MNF bar follows.

Nothing here is an in-game result. The retail-backed classes skip without the pinned USA XBE or
Unicorn.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_practice_reserves as reserves  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None

# (va, size, sha256): every retail span the record research executes or cites.
PINS = {
    "mode getter": (0x0C4B80, 0x006, "ea571d62a509b72a0a8afeb1ce87e10afb9b23fe864a4f34521e3a467052a60a"),
    "stage getter": (0x0C4BB0, 0x006, "712452f8e0b8c23621623a511c8e9688c1a61e199a1a75329dd87f51b658661d"),
    "team at index and its mode table": (0x0C4C50, 0x050, "bf4afd3d901ae05431add7119322ba12f7d246f0322e194cdd9c47ace0faca0c"),
    "fixture home team": (0x0C4E00, 0x012, "85b4401e850c9a15ab8d953502a50a19a5c5cf14e909987422b9a78157dea3b0"),
    "fixture away team": (0x0C4E20, 0x012, "9a29fc4c3b49d2b68d0f2b3af8b4c25ae6a766d69331ee91f204e2d07dc424d9"),
    "fixture record address": (0x0C4F10, 0x00D, "d5ad895b67c726ab60b8eb71af00988b5ed29297e8a4e8e93e69143a1f98cc62"),
    "fixture game type and its table": (0x0C4FD0, 0x080, "4cdd040f4cff4da8422c1b68b4c098eaa496c795cb151b35547affee6df93ef5"),
    "home final score": (0x0C5110, 0x036, "7602534cb462964558267d05bb6b12bb885f271c9a5a5510525f958f9383773d"),
    "away final score": (0x0C5150, 0x036, "062a264af2bf7428751275cdebc248618869ad7153369f80ea69f2f19d0249c7"),
    "week wins": (0x0C75A0, 0x078, "84ee24973e3c972c872af215bdee40de4c2d07f58913277badbe5027f15ee6ea"),
    "week losses": (0x0C7620, 0x078, "aaa24e98b77c6d3358b256f7eaf350220f78cf201e8f93a16c9c38ea8faadc21"),
    "week ties": (0x0C76A0, 0x078, "8d0254f6665821da999619ef9a9f67bf99ff2902904372f0def03b1972b6b7c1"),
    "season wins": (0x0C7720, 0x027, "231bd0125da47da67063dbdf0c7d6c8c726b2428d3ba494e6fea35ea507e450b"),
    "season losses": (0x0C7750, 0x027, "e5e2d524abc5445e58c6b464e2879147d68295059683bbe708f79ca801fb6e0e"),
    "season ties": (0x0C7780, 0x027, "12940076668bb6a493438fb23b8e386fd73e10e922843a74086f671ab8719b2c"),
    "home-games record string": (0x0C6B70, 0x0B5, "dfd038a35eb10e6d5a71803bc919a191eab4f4484598fbd76e8df6c088199d36"),
    "road-games record string": (0x0C6C30, 0x0B5, "1eac0aaafcd2082f520f18cbb8c0c2c6259f12cf27fe0630d7ecca5996a62834"),
    "wide formatter wrapper": (0x04A3E0, 0x013, "fab550722cc1f390ddc67943a8f9ba43650405ed6bb2a2c8f050a409b84f008e"),
    "wide formatter thunk": (0x04A400, 0x005, "1112e6f999beb333c0875ac9d54ad149a6691db37eba764d560e1c928d058b1a"),
    "overall record string": (0x341E20, 0x043, "96fdfa9c7c43af10443b79511150cbe92f4686938d13cb33011fd13a8763b86c"),
    "team copy": (0x061730, 0x0AB, "019b3b03a0b9d58f4ccc6cd8f980cdce29a433d2b93b2bac37d3ce0219765778"),
    "team staging head": (0x0617E0, 0x018, "03059b83f43fdae040d456f37e6085afe8a4468504bd386ea3225dab71cd9a3d"),
    "staged team setters and getters": (0x077AD0, 0x076, "915fe977b99f6a99c6b8896bc5a1b47bfbf19aba5b5fcaf52f62203bd65a9156"),
    "fixture game start": (0x0C73B0, 0x08F, "53f4b897fcd5f20ec3580f65cdc2dd95d294e933cc17b8d2512a8326be251653"),
    "ticker record lines": (0x100850, 0x1BA, "beb156155d045968dc570112253ffee9fe1b1718ecbb43cfe39e930070908129"),
    "format W-L": (0xE68C28, 0x00C, "4d5815d36d034ed873a14a3d1f1965f00cedd49ca804f92b418bf6f8c7c675bd"),
    "format W-L-T": (0xE68C34, 0x012, "d2d526f305eaa98c46fc91b33e94dff00caabcefb6d00f1815a6cbd98e95f2cc"),
    "format three unsigned fields": (0xEAB748, 0x012, "52513b3919c552d2c4049221692279e8ba7332b509ab227d1749f848614f16ba"),
    "ticker format W-L": (0xE6CD80, 0x01C, "86601d3e47880ed77df4709571d54b2857fc10407227dd23ce6314ba2564a55f"),
    "ticker format W-L-T": (0xE6CD9C, 0x01C, "a3823b212fb85b6c63361eef0e28c629855bd837ece77a8f176bc44b960b06f0"),
}

MODE, STAGE, WEEK, SLOT, GAME_MODE = 0xE576A0, 0xE576A4, 0xE576B4, 0xE576BC, 0xE5FF80
LEAGUE_TEAMS, GRID, SCORES = 0xE5786C, 0xE57C40, 0xE587F0
STAGED_HOME, STAGED_AWAY = 0xE5FE68, 0xE5FE6C
HOME_CONTEXT, AWAY_CONTEXT = 0xB30864, 0xB30A58
SUMMERS = (0xC7720, 0xC7750, 0xC7780)            # wins, losses, ties; each ECX = league team pointer
FORMAT_WL, FORMAT_WLT = 0xE68C28, 0xE68C34
TICKER_AWAY_LINE, TICKER_HOME_LINE = 0xBA3810, 0xBA3850


def record_text(w: int, l: int, t: int) -> str:
    """The broadcast and retail convention: ties appear only when there are some."""
    return f"{w}-{l}-{t}" if t else f"{w}-{l}"


def mirror(fixtures, team: int) -> tuple[int, int, int]:
    """Python mirror of the retail summers over played fixtures (home, away, home score, away score)."""
    w = l = t = 0
    for home, away, hs, as_ in fixtures:
        if team == home:
            w += hs > as_
            l += hs < as_
            t += hs == as_
        elif team == away:
            w += as_ > hs
            l += as_ < hs
            t += as_ == hs
    return w, l, t


class TeamCopyPinTests(unittest.TestCase):
    """Runs everywhere: the staging copy the research cites is the one the practice reserves patch replaces."""

    def test_team_copy_pin_is_the_practice_reserves_retail_stage(self):
        va, size, digest = PINS["team copy"]
        self.assertEqual((va, size), (reserves.STAGE_VA, reserves.STAGE_SIZE))
        self.assertEqual(len(reserves.RETAIL_STAGE), size)
        self.assertEqual(hashlib.sha256(reserves.RETAIL_STAGE).hexdigest(), digest)
        self.assertEqual(reserves.TEAM_COPIES, (HOME_CONTEXT, AWAY_CONTEXT))

    def test_the_three_summers_are_evenly_spaced(self):
        # A reader may call them as 0xC7720 + k * 0x30; the pins below keep their bytes fixed.
        self.assertEqual([PINS[n][0] for n in ("season wins", "season losses", "season ties")],
                         [0xC7720 + k * 0x30 for k in range(3)])
        self.assertEqual(SUMMERS, (0xC7720, 0xC7750, 0xC7780))

    def test_record_text_matches_the_broadcast_convention(self):
        self.assertEqual(record_text(1, 0, 0), "1-0")
        self.assertEqual(record_text(0, 0, 0), "0-0")
        self.assertEqual(record_text(8, 7, 1), "8-7-1")


def _retail() -> bytes | None:
    if not XBE.is_file() or XBE.stat().st_size > 16 * 1024 ** 2:
        return None
    data = XBE.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == RETAIL_SHA256 else None


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class RetailSpanTests(unittest.TestCase):
    def test_every_relied_on_span_matches_its_pin(self):
        data = _retail()
        if data is None:
            self.skipTest("retail XBE pin differs")
        image = XbeImage(data)
        for name, (va, size, digest) in PINS.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest)


class _Season:
    """The retail image mapped section by section, plus a synthetic 34-team league and heap."""

    HEAP, STACK, STOP = 0x3000000, 0x4000000, 0x5000000
    SP = STACK + 0x8000
    TEAMS = HEAP + 0x1000            # 34 league team records, stride 0x1F4
    NAMES = HEAP + 0x20000           # UTF-16 nicknames, 32 bytes each
    ARGS, TEXT = HEAP + 0x30100, HEAP + 0x30000

    def __init__(self, payload: bytes):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        image = XbeImage(payload)
        pages = {}
        for s in image.sections:
            for page in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096):
                pages[page] = pages.get(page, u.UC_PROT_READ) | (u.UC_PROT_WRITE if s.writable else 0) \
                    | (u.UC_PROT_EXEC if s.executable else 0)
        regions = []
        for page, flags in sorted(pages.items()):
            if regions and regions[-1][1] == page and regions[-1][2] == flags:
                regions[-1][1] += 4096
            else:
                regions.append([page, page + 4096, flags])
        for start, end, _flags in regions:
            self.uc.mem_map(start, end - start)
        for s in image.sections:
            self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for start, end, flags in regions:
            self.uc.mem_protect(start, end - start, flags)
        for va, size in ((self.HEAP, 0x40000), (self.STACK, 0x10000), (self.STOP, 4096)):
            self.uc.mem_map(va, size)
        self.hooks = []

    def team(self, index: int) -> int:
        return self.TEAMS + index * 0x1F4

    def put(self, va: int, value: int) -> None:
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va: int) -> int:
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def reg(self, name: str, value: int | None = None) -> int:
        register = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xFFFFFFFF)
        return value

    def wide(self, va: int, limit: int = 40) -> str:
        return bytes(self.uc.mem_read(va, limit * 2)).decode("utf-16le").split("\0")[0]

    def stub_return(self, va: int) -> None:
        """Return to the caller the moment execution reaches ``va`` (a call or tail-jump target)."""
        def leave(_uc, _at, _size, _data):
            sp = self.reg("ESP")
            self.reg("EIP", self.get(sp))
            self.reg("ESP", sp + 4)
        self.hooks.append(self.uc.hook_add(self.u.UC_HOOK_CODE, leave, begin=va, end=va))
        self.uc.ctl_remove_cache(va, va + 1)   # a block translated before the hook would bypass it

    def clear_stubs(self) -> None:
        for hook in self.hooks:
            self.uc.hook_del(hook)
        self.hooks = []

    def call(self, entry: int, *, ecx: int = 0, edx: int = 0, eax: int = 0, args=(), stop: int | None = None,
             budget: int = 2_000_000) -> int:
        target = self.STOP if stop is None else stop
        self.put(self.SP, self.STOP)
        for i, value in enumerate(args, 1):
            self.put(self.SP + 4 * i, value)
        for name, value in (("EAX", eax), ("ECX", ecx), ("EDX", edx), ("ESP", self.SP), ("EBX", 0x11111111),
                            ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444), ("EFLAGS", 0x202)):
            self.reg(name, value)
        self.uc.emu_start(entry, target, count=budget)
        if self.reg("EIP") != target:
            raise AssertionError(f"{entry:#x}: stopped at {self.reg('EIP'):#x}, expected {target:#x}")
        return self.reg("EAX")

    def season(self, weeks_played: int, *, seed: int = 26, stage: int = 8):
        """A synthetic 18-week Franchise: rows before ``weeks_played`` are played (type 3), later rows are
        scheduled (type 1); unused cells are empty (type 7). Returns the played fixtures."""
        rnd = random.Random(seed)
        for va, value in ((MODE, 2), (STAGE, stage), (WEEK, weeks_played), (SLOT, 0)):
            self.put(va, value)
        for i in range(34):
            self.uc.mem_write(self.team(i), bytes(0x1F4))
            self.uc.mem_write(self.NAMES + i * 32, f"Team{i:02d}\0".encode("utf-16le"))
            self.put(self.team(i) + 0x104, self.NAMES + i * 32)
            self.put(LEAGUE_TEAMS + 4 * i, self.team(i))
        grid, scores, fixtures = bytearray(bytes((7, 0, 0, 0, 0, 0, 0, 0)) * (22 * 17)), bytearray(22 * 17 * 10), []
        for week in range(18):
            order = list(range(32))
            rnd.shuffle(order)
            for slot in range(16):
                home, away, cell = order[2 * slot], order[2 * slot + 1], week * 17 + slot
                played = week < weeks_played
                grid[cell * 8:cell * 8 + 8] = bytes((3 if played else 1, home, away, 9, 13, 26, 1, 0))
                if played:
                    hq = [rnd.choice((0, 3, 7, 7, 10)) for _ in range(4)] + [0]
                    aq = list(hq) if rnd.random() < 0.1 else [rnd.choice((0, 3, 7, 7, 10)) for _ in range(4)] + [0]
                    scores[cell * 10:cell * 10 + 10] = bytes(hq + aq)
                    fixtures.append((home, away, sum(hq), sum(aq)))
        self.uc.mem_write(GRID, bytes(grid))
        self.uc.mem_write(SCORES, bytes(scores))
        return fixtures

    def play(self, week: int, slot: int, home: int, away: int, home_score: int, away_score: int) -> None:
        cell = week * 17 + slot
        self.uc.mem_write(GRID + cell * 8, bytes((3, home, away, 1, 9, 27, 4, 30)))
        self.uc.mem_write(SCORES + cell * 10, bytes((home_score, 0, 0, 0, 0, away_score, 0, 0, 0, 0)))

    def record(self, pointer: int) -> tuple[int, int, int]:
        return tuple(self.call(fn, ecx=pointer) for fn in SUMMERS)

    def format(self, w: int, l: int, t: int) -> str:
        self.uc.mem_write(self.ARGS, struct.pack("<3I", w, l, t))
        self.uc.mem_write(self.TEXT, bytes(64))
        self.call(0x4A400, ecx=self.TEXT, edx=FORMAT_WLT if t else FORMAT_WL, args=(self.ARGS,))
        if self.reg("ESP") != self.SP + 8:
            raise AssertionError("the wide formatter must pop its one stack argument")
        return self.wide(self.TEXT)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE and Unicorn required")
class SeasonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = _retail()
        if data is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.m = _Season(data)

    def setUp(self):
        self.m.clear_stubs()

    def test_summers_equal_the_grid_mirror_with_ties_and_a_played_postseason_game(self):
        m = self.m
        fixtures = m.season(10)
        self.assertTrue(any(hs == as_ for _h, _a, hs, as_ in fixtures), "the fixture must exercise ties")
        # A played Wild Card game (row 18 of the 18-week grid) counts; a scheduled one does not.
        m.play(18, 0, 4, 9, 24, 17)
        fixtures.append((4, 9, 24, 17))
        m.uc.mem_write(GRID + (18 * 17 + 1) * 8, bytes((1, 5, 6, 1, 10, 27, 1, 0)))
        for team in range(32):
            with self.subTest(team=team):
                self.assertEqual(m.record(m.team(team)), mirror(fixtures, team))

    def test_no_games_played_reads_zero_zero(self):
        m = self.m
        m.season(0)
        for team in (0, 13, 31):
            self.assertEqual(m.record(m.team(team)), (0, 0, 0))
        self.assertEqual(m.format(0, 0, 0), "0-0")

    def test_summers_take_league_pointers_not_the_in_game_copies(self):
        m = self.m
        fixtures = m.season(6)
        team = next(t for t in range(32) if sum(mirror(fixtures, t)))
        m.uc.mem_write(HOME_CONTEXT, bytes(m.uc.mem_read(m.team(team), 0x1F4)))
        self.assertEqual(m.record(HOME_CONTEXT), (0, 0, 0))
        self.assertEqual(m.record(m.team(team)), mirror(fixtures, team))

    def test_fixture_getters_return_the_league_pointers_of_bytes_one_and_two(self):
        m = self.m
        m.season(9)
        for week, slot in ((0, 0), (9, 4), (17, 15)):
            raw = bytes(m.uc.mem_read(GRID + (week * 17 + slot) * 8, 8))
            self.assertEqual(m.call(0xC4E00, ecx=week, edx=slot), m.team(raw[1]))
            self.assertEqual(m.call(0xC4E20, ecx=week, edx=slot), m.team(raw[2]))

    def test_fixture_game_start_stages_home_and_away_and_sets_the_game_mode_word(self):
        m = self.m
        m.season(9)
        # External side effects of the start routine are stubbed; staging and the mode word run natively.
        for va in (0x64B80, 0x77600, 0x77730):
            m.stub_return(va)
        raw = bytes(m.uc.mem_read(GRID + (9 * 17 + 4) * 8, 8))
        for mode, stage, word in ((2, 7, 7), (2, 8, 7), (2, 9, 6), (1, 8, 5)):
            with self.subTest(mode=mode, stage=stage):
                for va, value in ((MODE, mode), (STAGE, stage), (WEEK, 9), (SLOT, 4), (GAME_MODE, 0),
                                  (STAGED_HOME, 0), (STAGED_AWAY, 0)):
                    m.put(va, value)
                m.call(0xC73B0, args=(0,), stop=0xC743F)
                self.assertEqual(m.get(STAGED_HOME), m.team(raw[1]))
                self.assertEqual(m.get(STAGED_AWAY), m.team(raw[2]))
                self.assertEqual(m.get(GAME_MODE), word)

    def test_staging_copies_home_to_0xb30864_and_away_to_0xb30a58(self):
        m = self.m
        m.season(3)
        m.put(STAGED_HOME, m.team(12))
        m.put(STAGED_AWAY, m.team(8))
        m.call(0x617E0, stop=0x617F8)
        self.assertEqual(bytes(m.uc.mem_read(HOME_CONTEXT, 0x1F4)), bytes(m.uc.mem_read(m.team(12), 0x1F4)))
        self.assertEqual(bytes(m.uc.mem_read(AWAY_CONTEXT, 0x1F4)), bytes(m.uc.mem_read(m.team(8), 0x1F4)))

    def test_retail_formatter_writes_utf16_w_l_and_w_l_t(self):
        m = self.m
        for w, l, t in ((1, 0, 0), (0, 1, 0), (12, 5, 0), (8, 7, 1), (10, 10, 1)):
            with self.subTest(record=(w, l, t)):
                text = m.format(w, l, t)
                self.assertEqual(text, record_text(w, l, t))
                raw = bytes(m.uc.mem_read(m.TEXT, 2 * len(text) + 2))
                self.assertEqual(raw, (text + "\0").encode("utf-16le"))

    def test_home_and_road_strings_are_split_columns_not_the_season_record(self):
        m = self.m
        fixtures = m.season(12)
        team = next(t for t in range(32) if any(f[0] == t for f in fixtures) and any(f[1] == t for f in fixtures))
        home_games = mirror([f for f in fixtures if f[0] == team], team)
        road_games = mirror([f for f in fixtures if f[1] == team], team)
        overall = mirror(fixtures, team)
        m.call(0xC6B70, ecx=m.team(team))
        self.assertEqual(m.wide(0xB72A10), record_text(*home_games))
        m.call(0xC6C30, ecx=m.team(team))
        self.assertEqual(m.wide(0xB72A30), record_text(*road_games))
        self.assertNotIn(record_text(*overall), (record_text(*home_games), record_text(*road_games)))

    def test_overall_string_always_prints_three_fields(self):
        m = self.m
        fixtures = m.season(8)
        team = next(t for t in range(32) if mirror(fixtures, t)[2] == 0)
        w, l, t = mirror(fixtures, team)
        pointer = m.call(0x341E20, ecx=m.team(team))
        self.assertEqual(m.wide(pointer), f"{w}-{l}-{t}")
        self.assertTrue(m.wide(pointer).endswith("-0"))

    def test_ticker_line_is_the_entering_record_live_and_post_game_when_final(self):
        m = self.m
        fixtures = m.season(9)
        week, slot = 8, 3
        m.put(WEEK, week)
        raw = bytes(m.uc.mem_read(GRID + (week * 17 + slot) * 8, 8))
        home, away = raw[1], raw[2]
        index = week * 16 + slot                 # season() appends 16 played games per week, slot order
        self.assertEqual(fixtures[index][:2], (home, away))
        before = fixtures[:index] + fixtures[index + 1:]

        def line(team, record):
            w, l, t = record
            name = f"Team{team:02d}"
            return f"{name} ({w}-{l}-{t})" if t else f"{name} ({w}-{l})   "

        for status, pool in ((6, fixtures), (2, before)):
            with self.subTest(status=status):
                # FUN_00100850: EAX = slot, one stack argument = the ticker status (6 = final); stop once
                # both record lines are formatted.
                m.call(0x100850, eax=slot, args=(status,), stop=0x100A0A)
                self.assertEqual(m.wide(TICKER_AWAY_LINE), line(away, mirror(pool, away)))
                self.assertEqual(m.wide(TICKER_HOME_LINE), line(home, mirror(pool, home)))


if __name__ == "__main__":
    unittest.main()

"""The 14-team playoff patch: pattern-driven sites, assembled code that decodes and links, and (when
the retail executable and the unicorn emulator are available) the bracket logic run for real.

Layers:
* static -- site shapes, no overlap with the season-length sites, the game table's invariants;
* capstone (optional) -- every blob decodes completely, calls hit the intended routines, jumps land on
  instruction starts;
* retail smoke (needs the private default.xbe) -- every site is retail, apply repins the digests;
* unicorn (needs the retail default.xbe + the unicorn package) -- the rewritten season-start
  routine, the advance cave, ``seed_of`` and ``in_bracket14`` are executed against a mocked league
  (32 teams, fixed strengths, the retail grid/flag/score arrays, the retail helper routines running
  natively) and compared with a Python model of the 2020+ format.
"""

from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_playoffs14 as p14  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season  # noqa: E402
from tests.nfl2k5_season_length_test import RETAIL_XBE, build_synthetic_xbe  # noqa: E402

HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None


class StaticTests(unittest.TestCase):
    def test_sites_are_well_formed_and_disjoint_from_the_season_length_group(self) -> None:
        spans = []
        for site in p14.sites():
            self.assertEqual(len(site.retail), len(site.patched), site.label)
            self.assertNotEqual(site.retail, site.patched, site.label)
            spans.append((site.va, site.va + site.size, site.label))
        for group in ("year", "calendar", "season_length"):
            for site in season.group_sites(group):
                spans.append((site.va, site.va + site.size, f"{group}:{site.label}"))
        spans.sort()
        for (a0, a1, la), (b0, _b1, lb) in zip(spans, spans[1:]):
            self.assertLessEqual(a1, b0, f"{la} overlaps {lb}")
        self.assertEqual(len(p14.sites()), 13)

    def test_code_fits_its_regions(self) -> None:
        report = p14.code_report()
        self.assertLessEqual(report["seed_fn_bytes"], report["seed_fn_capacity"])
        self.assertLessEqual(report["builder_bytes"], report["builder_capacity"])
        self.assertLessEqual(report["cave_bytes"], report["cave_capacity"])
        self.assertEqual(len(p14.seed_fn_bytes()), p14.SEED_FN_SIZE)
        self.assertEqual(len(p14.builder_bytes()), p14.BUILDER_SIZE)
        self.assertEqual(len(p14.cave_bytes()), p14.CAVE_SIZE)
        self.assertEqual(p14.CAVE_VA + p14.CAVE_SIZE, 0x326243)
        self.assertFalse(report["runtime_verified"])

    def test_game_table_is_the_2020_format(self) -> None:
        wc = [g for g in p14.GAME_TABLE if g[0] == 0]
        self.assertEqual(len(wc), 6)
        pairs = sorted((h, a) for _r, _s, h, a, _fa, _fb in wc)
        self.assertEqual(pairs, [(1, 6), (2, 5), (3, 4), (8, 13), (9, 12), (10, 11)])   # 2v7 3v6 4v5 per conference
        div = [g for g in p14.GAME_TABLE if g[0] == 1]
        self.assertEqual([(g[2], g[3], g[4], g[5]) for g in div],
                         [(0, p14.NONE, 1, 0), (p14.NONE, p14.NONE, 0, 0), (7, p14.NONE, 1, 0), (p14.NONE, p14.NONE, 0, 0)])
        self.assertEqual([(g[0], g[1]) for g in p14.GAME_TABLE[10:]], [(2, 0), (2, 1), (3, 0)])
        self.assertEqual(len(p14.game_table_bytes()), 13 * 8)
        seeds_used = sorted(h for g in wc for h in (g[2], g[3]))
        self.assertEqual(seeds_used, [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13])   # the #1 seeds (0, 7) rest

    def test_calendar_matches_the_twelve_record_preset(self) -> None:
        # divisional / conference / Super Bowl dates agree with the season-length module's calendar
        self.assertEqual(p14.CALENDAR_2026_14[6:], season.CALENDAR_2026[4:11])
        table = p14.date_table_14(p14.CALENDAR_2026_14)
        self.assertEqual(len(table), 13 * 8)
        self.assertEqual(table[:8], bytes([0, 0, 0, 1, 16, 0, 4, 30]))
        self.assertEqual(table[5 * 8: 6 * 8], bytes([0, 0, 0, 1, 18, 0, 8, 15]))       # Monday wild card
        self.assertEqual(table[-8:], bytes([0, 0, 0, 2, 14, 0, 6, 30]))                # Super Bowl LXI
        self.assertEqual(len(p14.CALENDAR_RETAIL_14), 13)
        with self.assertRaises(p14.Playoffs14Error):
            p14.date_table_14(p14.CALENDAR_2026_14[:12])

    def test_chain_bytes(self) -> None:
        clinch = p14.chain_bytes(p14.CLINCH_CHAIN_VA, "6c", "24", "2d")
        elim = p14.chain_bytes(p14.ELIM_CHAIN_VA, "5c", "28", "1d")
        self.assertEqual(len(clinch), 0x44)
        self.assertEqual(len(elim), 0x44)
        self.assertIn(struct.pack("<I", p14.LAST7_VA), clinch)
        self.assertIn(struct.pack("<I", p14.LAST7_VA), elim)
        self.assertTrue(clinch.startswith(bytes.fromhex("33c0be07000000396c8424")))
        self.assertTrue(elim.startswith(bytes.fromhex("33c0be07000000395c8428")))


class SyntheticApplyTests(unittest.TestCase):
    def test_playoffs_group_round_trip_on_the_synthetic_xbe(self) -> None:
        payload = build_synthetic_xbe()
        self.assertEqual(season.group_status(payload, "playoffs_14"), "retail")
        patched, receipt = season.apply(payload, groups=("playoffs_14",))
        self.assertEqual(season.group_status(patched, "playoffs_14"), "applied")
        self.assertEqual(season.status(patched)["playoff_teams"], 14)
        self.assertEqual(season.status(patched)["season_length"], "retail")
        self.assertEqual(receipt["playoff_teams"], 14)
        self.assertEqual(receipt["sections_repinned"], [0])          # code only: .text
        self.assertEqual(len(receipt["edits"]), 13)
        with self.assertRaises(season.SeasonLengthError):
            season.apply(patched, groups=("playoffs_14",))
        # a foreign byte inside the cave is refused
        buf = bytearray(payload)
        off = season._offset(payload, p14.CAVE_VA + 100)
        buf[off] ^= 0xFF
        self.assertEqual(season.group_status(bytes(buf), "playoffs_14"), "foreign")

    def test_calendar14_parameter_changes_the_builder_only(self) -> None:
        payload = build_synthetic_xbe()
        alt = list(p14.CALENDAR_2026_14)
        alt[0] = (1, 16, 1, 0)
        patched, _ = season.apply(payload, groups=("playoffs_14",), calendar14=alt)
        self.assertEqual(season.group_status(patched, "playoffs_14", calendar14=alt), "applied")
        self.assertEqual(season.group_status(patched, "playoffs_14"), "foreign")


@unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
class CapstoneTests(unittest.TestCase):
    def _check(self, name: str, base: int, code: bytes, exits=()):
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        insns = list(md.disasm(code, base))
        self.assertEqual(sum(i.size for i in insns), len(code), f"{name}: undecodable bytes")
        starts = {i.address for i in insns}
        known = {v for k, v in vars(p14).items() if k.startswith("FN_")}
        labels = p14.cave_labels()
        known |= {labels["advance"], labels["seed_of"], labels["in_bracket"], p14.SEED_FN_VA}
        for i in insns:
            if i.mnemonic == "call":
                self.assertIn(int(i.op_str, 16), known, f"{name}: call {i.op_str} at {i.address:#x}")
            elif i.mnemonic.startswith("j"):
                target = int(i.op_str, 16)
                if target not in exits:
                    self.assertIn(target, starts, f"{name}: jump {i.op_str} at {i.address:#x}")
        return insns

    def test_blobs_decode_and_link(self) -> None:
        self._check("seed7", p14.SEED_FN_VA, p14.seed_fn_bytes().rstrip(b"\xcc"))
        builder = p14.builder_bytes()
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        end = next(i for i in md.disasm(builder, p14.BUILDER_VA)
                   if i.mnemonic == "jmp" and int(i.op_str, 16) == p14.BUILDER_END_VA)
        code_len = end.address + end.size - p14.BUILDER_VA
        self._check("builder", p14.BUILDER_VA, builder[:code_len], exits=(p14.BUILDER_END_VA,))
        labels = p14.cave_labels()
        self._check("cave", p14.CAVE_VA, p14.cave_bytes()[: labels["end"] - p14.CAVE_VA])
        self._check("clinch", p14.CLINCH_CHAIN_VA, p14.chain_bytes(p14.CLINCH_CHAIN_VA, "6c", "24", "2d"))
        self._check("elim", p14.ELIM_CHAIN_VA, p14.chain_bytes(p14.ELIM_CHAIN_VA, "5c", "28", "1d"))


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail default.xbe not present")
class RetailSmokeTests(unittest.TestCase):
    def test_every_site_is_retail_and_apply_repins(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(season.group_status(payload, "playoffs_14"), "retail")
        patched, receipt = season.apply(payload, groups=("playoffs_14",))
        self.assertEqual(season.group_status(patched, "playoffs_14"), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])
        for section in strength._sections(patched):
            if section.index == 0:
                self.assertEqual(strength.section_digest(patched, section), section.stored_digest)
        # the cave really is unreferenced: no rel32 call/jmp and no absolute pointer to it anywhere
        target = p14.CAVE_VA
        for section in strength._sections(payload):
            raw = payload[section.raw_offset: section.raw_offset + section.raw_size]
            self.assertEqual(raw.find(struct.pack("<I", target)), -1, f"pointer to the cave in section {section.index}")
        text = next(s for s in strength._sections(payload) if s.index == 0)
        code = payload[text.raw_offset: text.raw_offset + text.raw_size]
        for i in range(len(code) - 5):
            if code[i] in (0xE8, 0xE9):
                rel = struct.unpack_from("<i", code, i + 1)[0]
                self.assertNotEqual(text.virtual_address + i + 5 + rel, target, f"call/jmp to the cave at {text.virtual_address + i:#x}")


# --- emulation ---------------------------------------------------------------------------------------

GRID_VA = season.GRID_VA
FLAGS_VA = 0x00E57954
SCORES_VA = 0x00E587F0
SEED_TABLE_VA = 0x00E578F4
DIVISION_TABLE_VA = 0x00E576D4
STAGE_WEEKS_GLOBAL_VA = 0x00E576B0
SEASON_INDEX_VA = 0x00E576B8
TEAMS_VA = 0x00D00000
TEAM_STRIDE = 500
STACK_VA = 0x07F00000
SENTINEL = 0x00ABCD00
CONF_OF_DIVISION = (1, 1, 1, 1, 0, 0, 0, 0)   # .rdata 0x4F0FE0: divisions 0-3 NFC, 4-7 AFC


class League:
    """32 teams, team i in division i // 4 (0-3 NFC, 4-7 AFC), distinct fixed strengths."""

    def __init__(self, seed: int = 7) -> None:
        import random
        rng = random.Random(seed)
        order = list(range(32))
        rng.shuffle(order)
        self.strength = {team: 100 - rank for rank, team in enumerate(order)}
        self.division = {team: team // 4 for team in range(32)}

    def conf(self, team: int) -> int:
        return CONF_OF_DIVISION[self.division[team]]

    def ptr(self, team: int) -> int:
        return TEAMS_VA + team * TEAM_STRIDE

    def team(self, ptr: int) -> int:
        return (ptr - TEAMS_VA) // TEAM_STRIDE

    def seeds(self, conf: int) -> list[int]:
        winners = []
        for div in range(8):
            if CONF_OF_DIVISION[div] == conf:
                winners.append(max((t for t in range(32) if self.division[t] == div), key=self.strength.get))
        winners.sort(key=self.strength.get, reverse=True)
        rest = sorted((t for t in range(32) if self.conf(t) == conf and t not in winners),
                      key=self.strength.get, reverse=True)
        return winners + rest[:3]


@unittest.skipUnless(RETAIL_XBE.is_file() and HAVE_UNICORN, "retail default.xbe and unicorn needed")
class EmulationTests(unittest.TestCase):
    """Runs the patched routines on the real code with the league mocked at five hook points."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()

    def _boot(self, groups, wc_row: int, season_index: int, league: League, user_team: int | None = None):
        from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, Uc
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP

        patched, _ = season.apply(self.retail, groups=groups)
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0, 0x1000000)
        uc.mem_map(STACK_VA, 0x100000)
        for section in strength._sections(patched):
            if section.raw_size:
                uc.mem_write(section.virtual_address, patched[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_write(SENTINEL, b"\xc3")
        # league globals
        uc.mem_write(STAGE_WEEKS_GLOBAL_VA, struct.pack("<I", wc_row))
        uc.mem_write(SEASON_INDEX_VA, struct.pack("<I", season_index))
        uc.mem_write(DIVISION_TABLE_VA, b"".join(struct.pack("<I", league.division[t]) for t in range(32)))
        uc.mem_write(GRID_VA, bytes([7, 0, 0, 0, 0, 0, 0, 0]) * (22 * 17))
        uc.mem_write(FLAGS_VA, bytes(22 * 17 * 2))
        uc.mem_write(SCORES_VA, bytes(22 * 17 * 10))
        uc.mem_write(SEED_TABLE_VA, bytes(12 * 4))
        uc.mem_write(TEAMS_VA, bytes(32 * TEAM_STRIDE))

        def ret(pops: int = 0) -> None:
            esp = uc.reg_read(UC_X86_REG_ESP)
            target = struct.unpack("<I", uc.mem_read(esp, 4))[0]
            uc.reg_write(UC_X86_REG_ESP, esp + 4 + pops)
            uc.reg_write(UC_X86_REG_EIP, target)

        def team_count(uc_, *_):
            uc.reg_write(UC_X86_REG_EAX, 32)
            ret()

        def team_at(uc_, *_):
            idx = uc.reg_read(UC_X86_REG_ECX)
            uc.reg_write(UC_X86_REG_EAX, league.ptr(idx) if idx < 32 else 0)
            ret()

        def seed_division(uc_, *_):
            div = uc.reg_read(UC_X86_REG_ECX)
            best = max((t for t in range(32) if league.division[t] == div), key=league.strength.get)
            uc.reg_write(UC_X86_REG_EAX, league.ptr(best))
            ret()

        def sort_teams(uc_, *_):
            arr, count = uc.reg_read(UC_X86_REG_ECX), uc.reg_read(UC_X86_REG_EDX)
            ptrs = list(struct.unpack("<%dI" % count, uc.mem_read(arr, count * 4)))
            ptrs.sort(key=lambda ptr: league.strength[league.team(ptr)], reverse=True)
            uc.mem_write(arr, struct.pack("<%dI" % count, *ptrs))
            ret()

        def user(uc_, *_):
            uc.reg_write(UC_X86_REG_EAX, league.ptr(user_team) if user_team is not None else 0)
            ret()

        hooks = {p14.FN_TEAM_COUNT: team_count, p14.FN_TEAM_AT: team_at, p14.FN_SEED_DIVISION: seed_division,
                 p14.FN_SORT_TEAMS: sort_teams, p14.FN_USER_TEAM: user}

        def on_code(uc_, address, size, _user):
            fn = hooks.get(address)
            if fn is not None:
                fn(uc_)

        uc.hook_add(UC_HOOK_CODE, on_code)
        return uc

    @staticmethod
    def _call(uc, entry: int, ecx: int = 0, edx: int = 0, until: int = SENTINEL) -> int:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP

        esp = STACK_VA + 0x80000
        uc.mem_write(esp, struct.pack("<I", SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_ECX, ecx)
        uc.reg_write(UC_X86_REG_EDX, edx)
        uc.emu_start(entry, until, count=2_000_000)
        return uc.reg_read(UC_X86_REG_EAX)

    @staticmethod
    def _record(uc, row: int, slot: int) -> bytes:
        return bytes(uc.mem_read(GRID_VA + (row * 17 + slot) * 8, 8))

    @staticmethod
    def _flags(uc, row: int, slot: int) -> tuple[int, int]:
        return tuple(uc.mem_read(FLAGS_VA + (row * 17 + slot) * 2, 2))

    @staticmethod
    def _play(uc, row: int, slot: int, home_wins: bool) -> None:
        base = GRID_VA + (row * 17 + slot) * 8
        rec = bytearray(uc.mem_read(base, 8))
        rec[0] = 3
        uc.mem_write(base, bytes(rec))
        home, away = (7, 3) if home_wins else (3, 7)
        uc.mem_write(SCORES_VA + (row * 17 + slot) * 10, bytes([home, 0, 0, 0, 0, away, 0, 0, 0, 0]))

    def _bracket_scenario(self, groups, wc_row: int, season_index: int, wc_home_wins, div_home_wins, conf_home_wins):
        from unicorn.x86_const import UC_X86_REG_ESI

        league = League()
        uc = self._boot(groups, wc_row, season_index, league)
        labels = p14.cave_labels()
        a, b = league.seeds(0), league.seeds(1)
        # ---- season start: FUN_002a7e50 from its entry until the retail tail --------------------------
        self._call(uc, 0x002A7E50, ecx=0, until=p14.BUILDER_END_VA)
        self.assertEqual(uc.reg_read(UC_X86_REG_ESI), wc_row + 3)                  # the tail wants the SB row
        seeds14 = a + b
        expected_wc = [(1, 6), (2, 5), (3, 4), (8, 13), (9, 12), (10, 11)]
        for slot, (h, aw) in enumerate(expected_wc):
            rec = self._record(uc, wc_row, slot)
            self.assertEqual(rec[0], 0, f"wild card {slot} type")
            self.assertEqual((rec[1], rec[2]), (seeds14[h], seeds14[aw]), f"wild card {slot} teams")
            self.assertEqual(self._flags(uc, wc_row, slot), (1, 1))
            self.assertEqual(rec[3:], p14.date_table_14(p14.CALENDAR_2026_14)[slot * 8 + 3: slot * 8 + 8])
        self.assertEqual(self._record(uc, wc_row, 6)[0], 7)                        # slot 6 stays empty
        for slot, home in ((0, a[0]), (2, b[0])):
            rec = self._record(uc, wc_row + 1, slot)
            self.assertEqual(rec[1], home)
            self.assertEqual(self._flags(uc, wc_row + 1, slot), (1, 0))
        for slot in (1, 3):
            self.assertEqual(self._flags(uc, wc_row + 1, slot), (0, 0))
        for row, slots in ((wc_row + 2, (0, 1)), (wc_row + 3, (0,))):
            for slot in slots:
                self.assertEqual(self._record(uc, row, slot)[0], 0)
                self.assertEqual(self._flags(uc, row, slot), (0, 0))
        table = struct.unpack("<12I", uc.mem_read(SEED_TABLE_VA, 48))
        self.assertEqual([league.team(p) for p in table], a[:6] + b[:6])         # the saved 12-seed table
        self.assertEqual(league.team(struct.unpack("<I", uc.mem_read(p14.LAST7_VA, 4))[0]), b[6])
        # ---- seed_of / in_bracket ------------------------------------------------------------------------
        for conf, seeds in ((0, a), (1, b)):
            for n, team in enumerate(seeds, start=1):
                self.assertEqual(self._call(uc, labels["seed_of"], ecx=league.ptr(team), edx=conf), n)
        for team in range(32):
            self.assertEqual(self._call(uc, labels["in_bracket"], ecx=league.ptr(team)), int(team in seeds14),
                             f"in_bracket({team})")
        # ---- wild-card round -> divisional reseed ----------------------------------------------------------
        self._call(uc, labels["advance"])                                        # nothing played: no change
        self.assertEqual(self._flags(uc, wc_row + 1, 0), (1, 0))
        for slot, home_wins in enumerate(wc_home_wins):
            self._play(uc, wc_row, slot, home_wins)
        self._call(uc, labels["advance"])
        for conf, seeds, base_slot in ((0, a, 0), (1, b, 3)):
            winners = []
            for k in range(3):
                h, aw = expected_wc[base_slot + k]
                winners.append((seeds14[h] if wc_home_wins[base_slot + k] else seeds14[aw]))
            seed_no = {t: seeds.index(t) + 1 for t in seeds}
            lowest = max(winners, key=seed_no.get)
            others = sorted((t for t in winners if t != lowest), key=seed_no.get)
            rec0 = self._record(uc, wc_row + 1, 2 * conf)
            self.assertEqual((rec0[1], rec0[2]), (seeds[0], lowest), f"divisional {conf} game 0")
            self.assertEqual(self._flags(uc, wc_row + 1, 2 * conf), (1, 1))
            rec1 = self._record(uc, wc_row + 1, 2 * conf + 1)
            self.assertEqual((rec1[1], rec1[2]), (others[0], others[1]), f"divisional {conf} game 1")
            self.assertEqual(self._flags(uc, wc_row + 1, 2 * conf + 1), (1, 1))
        # ---- divisional -> conference ------------------------------------------------------------------------
        for slot, home_wins in enumerate(div_home_wins):
            self._play(uc, wc_row + 1, slot, home_wins)
        self._call(uc, labels["advance"])
        champs = []
        for conf, seeds in ((0, a), (1, b)):
            seed_no = {t: seeds.index(t) + 1 for t in seeds}
            winners = []
            for slot in (2 * conf, 2 * conf + 1):
                rec = self._record(uc, wc_row + 1, slot)
                winners.append(rec[1] if div_home_wins[slot] else rec[2])
            winners.sort(key=seed_no.get)
            rec = self._record(uc, wc_row + 2, conf)
            self.assertEqual((rec[1], rec[2]), (winners[0], winners[1]), f"conference {conf}")
            self.assertEqual(self._flags(uc, wc_row + 2, conf), (1, 1))
            champs.append(rec[1] if conf_home_wins[conf] else rec[2])
        # ---- conference -> Super Bowl ---------------------------------------------------------------------
        for slot, home_wins in enumerate(conf_home_wins):
            self._play(uc, wc_row + 2, slot, home_wins)
        self._call(uc, labels["advance"])
        rec = self._record(uc, wc_row + 3, 0)
        afc, nfc = champs
        self.assertEqual((rec[1], rec[2]), (afc, nfc) if season_index & 1 else (nfc, afc))
        self.assertEqual(self._flags(uc, wc_row + 3, 0), (1, 1))
        return uc, league

    def test_bracket_retail_rows_chalk(self) -> None:
        self._bracket_scenario(("playoffs_14",), 17, 0, [True] * 6, [True] * 4, [True, True])

    def test_bracket_eighteen_week_rows_with_upsets(self) -> None:
        self._bracket_scenario(("year", "calendar", "season_length", "playoffs_14"), 18, 1,
                               [False, True, False, True, False, False], [False, True, True, False], [False, True])

    def test_user_team_is_forced_in_as_the_seventh_seed(self) -> None:
        league = League()
        a, b = league.seeds(0), league.seeds(1)
        outsider = next(t for t in range(32) if league.conf(t) == 0 and t not in a)
        uc = self._boot(("playoffs_14",), 17, 0, league, user_team=outsider)
        self._call(uc, 0x002A7E50, ecx=1, until=p14.BUILDER_END_VA)
        rec = self._record(uc, 17, 0)                                            # AFC 2v7: the 7 is the user
        self.assertEqual((rec[1], rec[2]), (a[1], outsider))
        rec = self._record(uc, 17, 3)
        self.assertEqual((rec[1], rec[2]), (b[1], b[6]))
        # an already-seeded user team is left alone
        uc = self._boot(("playoffs_14",), 17, 0, league, user_team=a[3])
        self._call(uc, 0x002A7E50, ecx=1, until=p14.BUILDER_END_VA)
        self.assertEqual(self._record(uc, 17, 0)[2], a[6])


if __name__ == "__main__":
    unittest.main()

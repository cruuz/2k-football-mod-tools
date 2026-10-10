"""Beta 77 (job F4): letter grades in Franchise, Noah's 2K Player Grade System.

``mod_editor/core/nfl2k5_letter_grades.py`` shows a player's overall and a team's offense, defense and overall as
A+ ... F- (95+ A+, 90-94 A, 85-89 B+, 80-84 B, 75-79 C+, 70-74 C, 65-69 D+, 60-64 D, 55-59 F+, 50-54 F, 0-49 F-)
instead of numbers. These tests pin the scale, the band table, the owner's allocation and sites, the Studio wiring and
the native repair, and run the *real* retail code under Unicorn: the game's own swprintf with the new ``%R``
conversion, the spreadsheet cell formatter with its new kind 9, every patched text site from a real roster player
(or a real team rating) to the text on screen, and the six spreadsheet cell wrappers over the real column
descriptors. Nothing is witnessed in game. No retail bytes are stored here: the native tests skip without the
private USA executable (``NFL2K5_RETAIL_EXTRACTION``), and the v0.5 tests without the shipped v0.5 disc
(``NFL2K5_V05_DISC``).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
for entry in (REPO, REPO / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_letter_grades as lg  # noqa: E402
from mod_editor.core import nfl2k5_letter_grades_code as template  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
HAVE_CS = importlib.util.find_spec("capstone") is not None
V05_DISC = Path(os.environ.get("NFL2K5_V05_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso"))
V05_DISC_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"

# Noah's scale (b77_session/reports/F4_2K_PLAYER_GRADE_SYSTEM_noah.png): (lowest rating, highest rating, grade)
NOAH_SCALE = ((95, 999, "A+"), (90, 94, "A"), (85, 89, "B+"), (80, 84, "B"), (75, 79, "C+"), (70, 74, "C"),
              (65, 69, "D+"), (60, 64, "D"), (55, 59, "F+"), (50, 54, "F"), (-999, 49, "F-"))


def noah_grade(rating: int) -> str:
    for low, high, grade in NOAH_SCALE:
        if low <= rating <= high:
            return grade
    raise AssertionError(rating)


def _wstr(machine, address: int, size: int = 96) -> str:
    return bytes(machine.uc.mem_read(address, size)).decode("utf-16le", errors="replace").split("\0")[0]


def _fbits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


# ---------------------------------------------------------------------------------------------------------
class ScaleTests(unittest.TestCase):
    def test_the_default_bands_are_noahs_scale_exactly(self) -> None:
        self.assertEqual(lg.DEFAULT_BANDS, ((95, "A+"), (90, "A"), (85, "B+"), (80, "B"), (75, "C+"), (70, "C"),
                                            (65, "D+"), (60, "D"), (55, "F+"), (50, "F"), (None, "F-")))
        self.assertEqual(len({label for _m, label in lg.DEFAULT_BANDS}), 11)
        self.assertFalse({label for _m, label in lg.DEFAULT_BANDS} & {"A-", "B-", "C-", "D-"})

    def test_every_rating_gets_the_grade_on_the_image(self) -> None:
        for rating in range(-20, 140):
            self.assertEqual(lg.grade_for(rating), noah_grade(rating), rating)
        for low, high, grade in NOAH_SCALE:
            for rating in (max(low, -5), min(high, 120)):
                self.assertEqual(lg.grade_for(rating), grade)
        # both sides of every boundary
        for boundary, above, below in ((95, "A+", "A"), (90, "A", "B+"), (85, "B+", "B"), (80, "B", "C+"),
                                       (75, "C+", "C"), (70, "C", "D+"), (65, "D+", "D"), (60, "D", "F+"),
                                       (55, "F+", "F"), (50, "F", "F-")):
            self.assertEqual((lg.grade_for(boundary), lg.grade_for(boundary - 1)), (above, below))

    def test_band_tables_are_validated(self) -> None:
        good = ((90, "A"), (70, "B"), (None, "F"))
        self.assertEqual(lg.normalize_bands(good), good)
        for bad in (
            (), [(None, "F")] * 12,                                 # no rows, too many rows
            ((90, "A"), (90, "B"), (None, "F")),                    # not descending
            ((70, "A"), (90, "B"), (None, "F")),
            ((90, "A"), (70, "B")),                                  # last row not open
            ((90, "A"), (None, "")), ((90, "ABCD"), (None, "F")),   # label length
            ((90, "A%"), (None, "F")), ((90, "A n"), (None, "F")),  # label characters
            ((True, "A"), (None, "F")), ((9.5, "A"), (None, "F")), (("90", "A"), (None, "F")),
            ((90, "A"), (None, "F"), (None, "G")),                   # open row not last
        ):
            with self.assertRaises(lg.LetterGradesError, msg=repr(bad)):
                lg.normalize_bands(bad)

    def test_table_bytes_round_trip(self) -> None:
        table = lg.band_table_bytes()
        self.assertEqual(len(table), 132)
        self.assertEqual(lg.decode_band_table(table), lg.DEFAULT_BANDS)
        short = ((80, "G"), (None, "R"))
        self.assertEqual(lg.decode_band_table(lg.band_table_bytes(short)), short)
        self.assertEqual(struct.unpack_from("<i", lg.band_table_bytes(), 120)[0], -(1 << 31))
        with self.assertRaises(lg.LetterGradesError):
            lg.decode_band_table(table[:-1])
        broken = bytearray(table)
        broken[4:6] = b"%\0"
        with self.assertRaises(lg.LetterGradesError):
            lg.decode_band_table(bytes(broken))

    def test_trade_guideline_labels(self) -> None:
        self.assertEqual([lg.guideline_label(t) for t in lg.GUIDELINE_THRESHOLDS],
                         ["A or better", "B or better", "C or better", "D or better", "F or better",
                          "F- (40+)", "F- (30+)"])
        for threshold in lg.GUIDELINE_THRESHOLDS:
            slot = lg.guideline_slot_bytes(threshold)
            self.assertEqual(len(slot), 28)
            self.assertEqual(len(lg.retail_guideline_slot(threshold)), 28)
        self.assertEqual(lg.guideline_label(60, ((90, "A"), (None, "F"))), "F (60+)")


# ---------------------------------------------------------------------------------------------------------
class TemplateTests(unittest.TestCase):
    def test_the_generated_template_is_current_and_fits(self) -> None:
        self.assertLessEqual(len(template.CODE), lg.CODE_SIZE)
        self.assertLessEqual(len(template.RODATA), lg.RO_SIZE)
        self.assertEqual(lg.F4_REQUESTS, ((lg.OWNER, "code", 160, 16), (lg.OWNER, "read_only", 240, 16)))
        tool = REPO / "tools" / "nfl2k5_letter_grades_assemble.py"
        try:
            version = subprocess.run(["as", "--version"], capture_output=True, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("GNU as is not installed")
        if "GNU" not in version or not sys.platform.startswith("linux"):
            self.skipTest("needs GNU as emitting ELF32 objects (Linux binutils); macOS and Windows runners lack it")
        result = subprocess.run([sys.executable, str(tool), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_relocations_cover_exactly_the_absolute_and_external_references(self) -> None:
        kinds = sorted((symbol, kind) for _o, kind, symbol, _v in template.RELOCATIONS)
        self.assertEqual(kinds, [("fn_overall", 2), ("fn_swprintf", 2), ("nan_default", 2), ("ro", 1), ("ro", 1)])
        code, ro = lg.code_for(0x14EB150, 0x1509D60)
        self.assertEqual((len(code), len(ro)), (160, 240))
        # the band table is the first read-only item and holds the default bands
        self.assertEqual(lg.decode_band_table(ro[:132]), lg.DEFAULT_BANDS)
        # the two literals the sites use
        labels = lg.labels(0x14EB150, 0x1509D60)
        self.assertEqual(ro[labels["fmt_grade"] - 0x1509D60:][:6], "%R".encode("utf-16le") + b"\0\0")
        self.assertEqual(ro[labels["fmt_overall"] - 0x1509D60:][:22], "Overall:%R".encode("utf-16le") + b"\0\0")
        self.assertTrue(ro[labels["fmt_rating_sentence"] - 0x1509D60:].startswith(
            "A %s with rating %R or better.".encode("utf-16le")))

    @unittest.skipUnless(HAVE_CS, "capstone required")
    def test_the_code_decodes_cleanly_and_ends_each_function_with_a_return(self) -> None:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        code, _ro = lg.code_for(0x14EB150, 0x1509D60)
        va = 0x14EB150
        end = len(template.CODE)
        decoded = list(md.disasm(code[:end], va))
        self.assertEqual(sum(i.size for i in decoded), end)
        rets = [i.address - va for i in decoded if i.mnemonic == "ret"]
        # grade_text ends with a one-byte ret; the other three end with "ret imm16" (three bytes)
        self.assertEqual(rets, [template.LABELS["convert_R"] - 1, template.LABELS["cell_kind9"] - 3,
                                template.LABELS["matchup_overall"] - 3, end - 3])
        self.assertTrue(all(b == 0xCC for b in code[end:]))
        # no instruction writes outside what it should: the only stores are the output buffer and the argument cursor
        stores = [f"{i.mnemonic} {i.op_str}" for i in decoded if i.mnemonic in ("mov", "movzx") and i.op_str.startswith(("word ptr", "dword ptr"))]
        self.assertEqual(stores, ["mov dword ptr [ebx + 4], esi", "mov word ptr [ecx + ebx*2], ax",
                                  "mov word ptr [ecx], ax", "mov dword ptr [esp + 8], eax"])


# ---------------------------------------------------------------------------------------------------------
class AllocatorTests(unittest.TestCase):
    def test_the_owner_fits_the_complete_dormant_union_and_moves_nobody(self) -> None:
        union = tuple(space.dormant_union())
        # b77-f4b: F4 plus the progression row; i1: and every late owner ordered after them (v1b's period goalposts),
        # which the native repairs append after F4 and so never exist without it
        later = space.LATE_OWNERS[space.LATE_OWNERS.index(lg.OWNER):]
        without = tuple(r for r in union if r[0] not in later)
        self.assertEqual(len(union) - len(without), 7)   # b77-f5b: + the honors owner's code and data rows (late owner, last)
        plan_with, plan_without = space.plan(union), space.plan(without)
        key = lambda a: (a["owner"], a["kind"])           # noqa: E731
        old = {key(a): a for a in space._scale_allocations(without)}
        new = {key(a): a for a in space._scale_allocations(union)}
        for k, row in old.items():
            self.assertEqual(new[k], row, f"{k} moved")
        added = sorted(k for k in new if k not in old)
        self.assertEqual(added, sorted([(lg.OWNER, "code"), (lg.OWNER, "read_only"), (lg.PROGRESS_OWNER, "code"),
                                        ("nfl2k5_period_goalposts", "code"), ("nfl2k5_period_goalposts", "read_only"),
                                        ("nfl2k5_honors", "code"), ("nfl2k5_honors", "data")]))
        # after K128 in its region, contiguous with it
        k128, mine = new[("nfl2k5_k128", "code")], new[(lg.OWNER, "code")]
        self.assertEqual(mine["va"], k128["va"] + k128["size"])
        self.assertGreaterEqual(plan_with["capacity"]["code"]["available_bytes"], 0)
        self.assertGreater(plan_without["capacity"]["code"]["available_bytes"],
                           plan_with["capacity"]["code"]["available_bytes"])

    def test_late_owner_order_is_k128_then_letter_grades_then_progression(self) -> None:
        self.assertEqual(space.LATE_OWNERS[:3], ("nfl2k5_k128", "nfl2k5_letter_grades", "nfl2k5_letter_grades_progress"))
        solo = space._scale_allocations(tuple(lg.REQUESTS))
        self.assertTrue(all(a["owner"] in (lg.OWNER, lg.PROGRESS_OWNER, "nfl2k5_boot_logo", space.DIRECTORY_OWNER) for a in solo))

    def test_the_registry_the_plan_and_the_gui_know_the_option(self) -> None:
        import json
        registry = json.loads((REPO / "mod_editor/capabilities/registry.v1.json").read_text(encoding="utf-8"))
        rows = [c for c in registry["capabilities"] if c["id"] == "nfl2k5.gameplay.letter_grades"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["selectors"]["fields"][0]["name"], "letter_grades")
        self.assertIn("letter_grades", tt.R62_RUNTIME_KEYS)
        self.assertIn("letter_grades", tt.R62_SPACE_KEYS)
        from mod_editor.gui import beta62_options
        self.assertIn("letter_grades", beta62_options.KEYS)
        row = [r for r in beta62_options.OPTIONS if r[0] == "letter_grades"][0]
        self.assertEqual(row[1], "Letter grades in Franchise")
        self.assertIn("95+ A+", row[2])
        self.assertIn("letter_grades", __import__("mod_editor.core.nfl2k5_build_settings", fromlist=["x"]).FEATURE_KEYS)


class PlanTests(unittest.TestCase):
    def test_presets_basic_numbers_modern_and_experimental_grades(self) -> None:
        self.assertIs(mod_build.BuildPlan.__dataclass_fields__["letter_grades"].default, False)
        self.assertEqual({k: v["letter_grades"] for k, v in mod_build.PRESETS.items()},
                         {"softdrink_basic": False, "softdrink_advanced": True, "softdrink_experimental": True})
        for name, expected in (("softdrink_basic", False), ("softdrink_advanced", True), ("softdrink_experimental", True)):
            plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), name)
            self.assertIs(plan.letter_grades, expected)

    def test_the_option_alone_wants_an_executable_patch_and_validates(self) -> None:
        plan = mod_build.BuildPlan(source="s", target="t", letter_grades=True)
        self.assertTrue(plan.wants_xbe_patch())
        tt._validate_r62_options(letter_grades=True)
        with self.assertRaises(ValueError):
            tt._validate_r62_options(letter_grades="yes")
        requests = tt._selected_space_requests(letter_grades=True)
        self.assertEqual(tuple(r for r in requests if r[0] in (lg.OWNER, lg.PROGRESS_OWNER)), lg.REQUESTS)   # b77-f4b: plus the progression row
        self.assertEqual(tt._selected_space_requests(), ())
        availability = mod_build.availability()
        self.assertTrue(availability["letter_grades"])


# ---------------------------------------------------------------------------------------------------------
class SiteTests(unittest.TestCase):
    def test_the_site_list(self) -> None:
        sites = lg.sites(0x14EB150, 0x1509D60)
        self.assertEqual(len(sites), 28)
        spans = sorted((va, va + len(before)) for _l, va, before, _after in sites)
        for (a, b), (c, d) in zip(spans, spans[1:]):
            self.assertLessEqual(b, c, "sites overlap")
        for label, va, before, after in sites:
            self.assertEqual(len(before), len(after), label)
            self.assertNotEqual(before, after, label)
        names = [s[0] for s in sites]
        self.assertEqual(len(set(names)), 28)
        by = {s[0]: s for s in sites}
        # the %n row becomes %R and points at the owner's handler
        _l, va, before, after = by["printf_conversion_R"]
        self.assertEqual((va, before), (0x4E69B8, bytes.fromhex("6e000000009b0400")))
        self.assertEqual(struct.unpack("<II", after), (ord("R"), 0x14EB150 + template.LABELS["convert_R"]))
        # descriptor flags: kind byte 9 and nothing else
        for label, va in lg.PLAYER_COLUMNS + lg.TEAM_COLUMNS:
            self.assertEqual(by[label][2:], (bytes.fromhex("05000000"), bytes.fromhex("05090000")))
        # the unknown-kind branch: rel32 of the retail ja, retargeted to the kind 9 stub
        _l, va, before, after = by["sheet_cell_kind9"]
        self.assertEqual(va + 4 + struct.unpack("<i", before)[0], 0x1732CA)
        self.assertEqual(va + 4 + struct.unpack("<i", after)[0], 0x14EB150 + template.LABELS["cell_kind9"])
        # the weekly prep overall: jmp + two NOPs
        _l, va, before, after = by["weekly_prep_overall"]
        self.assertEqual((after[0], after[5:]), (0xE9, b"\x90\x90"))
        self.assertEqual(va + 5 + struct.unpack("<i", after[1:5])[0], 0x14EB150 + template.LABELS["matchup_overall"])
        # the Player Card glyph drawer: the colon test and glyph become minus, the apostrophe and quote tests and glyph plus
        self.assertEqual([by[l][1] for l in ("card_drawer_minus_test", "card_drawer_minus_glyph", "card_drawer_plus_test",
                                             "card_drawer_quote_test", "card_drawer_plus_glyph")],
                         [0xF200B, 0xF201D, 0xF2025, 0xF202B, 0xF2052])
        self.assertEqual([by[l][3] for l in ("card_drawer_minus_test", "card_drawer_plus_test", "card_drawer_quote_test")],
                         [struct.pack("<H", ord("-")), struct.pack("<H", ord("+")), struct.pack("<H", ord("+"))])
        self.assertEqual([struct.unpack("<I", by[l][3])[0] for l in ("card_drawer_minus_glyph", "card_drawer_plus_glyph")],
                         [38, 39])
        # the literal swaps point into the owner's read-only page
        for label in ("team_select_numbers", "player_card_overall", "depth_chart_overall", "matchups_overall"):
            self.assertEqual(struct.unpack("<I", by[label][3])[0], 0x1509D60 + template.RO_LABELS["fmt_grade"])
        self.assertEqual(struct.unpack("<I", by["contract_panel_overall"][3])[0], 0x1509D60 + template.RO_LABELS["fmt_overall"])
        self.assertEqual(struct.unpack("<I", by["trade_block_sentence"][3])[0], 0x1509D60 + template.RO_LABELS["fmt_rating_sentence"])

    def test_attributes_and_the_in_game_substitution_list_are_not_sites(self) -> None:
        touched = [(va, va + len(before)) for _l, va, before, _a in lg.sites(0x14EB150, 0x1509D60)]
        def hit(address: int) -> bool:
            return any(a <= address < b for a, b in touched)
        # the player card attribute bars (the '%d' of the ten bars, 0x32057E), the depth chart attribute value
        # (0x243641), the weekly prep attribute formats (0x2B0A5B, 0x2B0A7E) and the Matchups panel's non-overall
        # branch (0x2AF287) keep their literals
        for address in (0x32057E, 0x243641, 0x2B0A5B, 0x2B0A7E, 0x2AF287):
            self.assertFalse(hit(address), hex(address))
        # the Substitution list's RTG column (getter 0x26B840) and every attribute column descriptor
        self.assertFalse(hit(0x515928))
        self.assertEqual(len(lg.PLAYER_COLUMNS), 4)
        self.assertEqual(len(lg.TEAM_COLUMNS), 3)


# ---------------------------------------------------------------------------------------------------------
def _retail():
    from tests.nfl2k5_supersim_draft_fixture import retail_bytes
    return retail_bytes()


@unittest.skipUnless(HAVE_UC, "unicorn required")
class RetailNativeTests(unittest.TestCase):
    """The owner on the pinned retail executable (a single-owner allocation), then the real code under Unicorn."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.retail = _retail()
        except unittest.SkipTest as exc:
            raise unittest.SkipTest(str(exc))
        cls.patched, cls.receipt = lg.apply(cls.retail)

    def test_status_apply_and_replay(self) -> None:
        self.assertEqual(lg.status(self.retail), "retail")
        self.assertEqual(lg.status(self.patched), "applied")
        self.assertEqual(lg.read_settings(self.patched)["bands"][0], {"minimum": 95, "label": "A+"})
        again, receipt = lg.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(len(self.receipt["sites"]), 28)
        self.assertEqual(self.receipt["owner_bytes"], 400)
        with self.assertRaises(lg.LetterGradesError):
            lg.apply(self.patched, bands=((90, "A"), (None, "F")))

    def test_foreign_and_mixed_installations_are_refused(self) -> None:
        for label, va, before, after in lg.sites(0x14DA000, 0x1507000):
            off = rdata.offset_of(self.patched, va)
            broken = bytearray(self.patched)
            broken[off] ^= 0x01
            self.assertEqual(lg.status(bytes(broken)), "foreign", label)
            with self.assertRaises(ValueError):
                lg.apply(bytes(broken))
        # a retail executable with one site already patched is mixed, not retail
        off = rdata.offset_of(self.retail, 0x31F71E)
        mixed = bytearray(self.retail)
        mixed[off:off + 4] = struct.pack("<I", 0x1507000)
        self.assertEqual(lg.status(bytes(mixed)), "foreign")
        # a changed owner byte
        code = lg.allocations(self.patched)["code"]
        broken = bytearray(self.patched)
        broken[code["raw"] + 3] ^= 0xFF
        self.assertEqual(lg.status(bytes(broken)), "foreign")

    def test_a_custom_band_table_installs_and_reads_back(self) -> None:
        bands = ((90, "G"), (70, "OK"), (None, "X"))
        patched, _ = lg.apply(self.retail, bands=bands)
        self.assertEqual(lg.status(patched), "applied")
        self.assertEqual(lg.normalize_bands([(r["minimum"], r["label"]) for r in lg.read_settings(patched)["bands"]]), bands)

    def test_a_late_owner_is_appended_to_an_installed_image_without_moving_anyone(self) -> None:
        from mod_editor.core import nfl2k5_k128 as k128
        base, _ = space.apply(self.retail, k128.REQUESTS, scaleout=True)
        before = space.layout(base)["allocations"]
        grown, receipt = space.extend_scaleout(base, lg.REQUESTS)
        self.assertEqual(space.status(grown), "applied")
        self.assertTrue(receipt["existing_allocations_unchanged"])
        after = space.layout(grown)["allocations"]
        for row in before:
            self.assertIn(row, after)
        self.assertEqual(sorted((r["owner"], r["kind"]) for r in after if r["owner"] == lg.OWNER),
                         [(lg.OWNER, "code"), (lg.OWNER, "read_only")])
        # the new owner then installs, and the result equals a build that asked for both owners at once
        installed, _ = lg.apply(grown)
        direct, _ = lg.apply(space.apply(self.retail, k128.REQUESTS + lg.REQUESTS, scaleout=True)[0])
        self.assertEqual(installed, direct)
        # refusals: an owner that is not late, a second append, a legacy (not sealed) image
        with self.assertRaises(ValueError):
            space.extend_scaleout(base, (("nfl2k5_coin_defer", "code", 384, 16),))
        with self.assertRaises(ValueError):
            space.extend_scaleout(grown, lg.REQUESTS)
        with self.assertRaises(ValueError):
            space.extend_scaleout(self.retail, lg.REQUESTS)
        with self.assertRaises(ValueError):
            space.extend_scaleout(base[:-1], lg.REQUESTS)

    def test_the_owner_installs_in_either_order_with_k128(self) -> None:
        from mod_editor.core import nfl2k5_k128 as k128
        union, _ = space.apply(self.retail, k128.REQUESTS + lg.REQUESTS, scaleout=True)
        a, _ = lg.apply(k128.apply(union)[0])
        b, _ = k128.apply(lg.apply(union)[0])
        self.assertEqual(a, b)
        self.assertEqual((lg.status(a), k128.status(a)), ("applied", "applied"))
        # K128 alone, then the late append on its installed image, ends the same as the union build
        only, _ = k128.apply(self.retail)
        appended, _ = lg.apply(only)
        self.assertEqual(appended, a)


@unittest.skipUnless(HAVE_UC, "unicorn required")
class PrintfAndFormatterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            cls.retail = _retail()
        except unittest.SkipTest as exc:
            raise unittest.SkipTest(str(exc))
        cls.patched, _ = lg.apply(cls.retail)
        from tests.nfl2k5_supersim_draft_fixture import Machine
        cls.m = Machine(cls.patched, trace_writes=False)
        cls.m0 = Machine(cls.retail, trace_writes=False)

    def test_the_games_own_swprintf_writes_the_grade_for_percent_r(self) -> None:
        m = self.m
        fmt, dest, arg = m.ARENA + 0x1000, m.ARENA + 0x2000, m.ARENA + 0x3000
        m.uc.mem_write(fmt, "%R".encode("utf-16le") + b"\0\0")
        for rating in range(-5, 125):
            m.uc.mem_write(dest, b"\xee" * 64)
            m.uc.mem_write(arg, struct.pack("<i", rating))
            count = m.call(0x4A400, ecx=dest, edx=fmt, args=(arg,), budget=200000)
            self.assertEqual(_wstr(m, dest), noah_grade(rating), rating)
            self.assertEqual(count, len(noah_grade(rating)))
        # mixed formats keep the argument cursor right, and %d / %s are untouched
        m.uc.mem_write(fmt, "Overall:%R/%d/%s".encode("utf-16le") + b"\0\0")
        m.uc.mem_write(arg + 0x100, "ok".encode("utf-16le") + b"\0\0")
        m.uc.mem_write(arg, struct.pack("<iiI", 87, 87, arg + 0x100))
        m.call(0x4A400, ecx=dest, edx=fmt, args=(arg,), budget=200000)
        self.assertEqual(_wstr(m, dest), "Overall:B+/87/ok")
        # the bounded form (0x4A410) honours its size and never writes past it
        m.uc.mem_write(fmt, "%R".encode("utf-16le") + b"\0\0")
        m.uc.mem_write(dest, b"\xee" * 64)
        m.uc.mem_write(arg, struct.pack("<i", 97))
        m.call(0x4A410, ecx=dest, edx=2, args=(fmt, arg), budget=200000)
        self.assertEqual(bytes(m.uc.mem_read(dest, 4)), "A".encode("utf-16le") + b"\0\0")
        self.assertEqual(bytes(m.uc.mem_read(dest + 4, 2)), b"\xee\xee")

    def test_every_other_conversion_is_untouched(self) -> None:
        m, m0 = self.m, self.m0
        fmt, dest, arg = m.ARENA + 0x1000, m.ARENA + 0x2000, m.ARENA + 0x3000
        for text, args in (("%d", struct.pack("<i", -42)), ("%u", struct.pack("<I", 7)), ("%x", struct.pack("<I", 255)),
                           ("%s", struct.pack("<I", arg + 0x100)), ("%.1f", struct.pack("<d", 3.25)), ("%5d|", struct.pack("<i", 9)),
                           ("%c", struct.pack("<I", 65))):
            outs = []
            for machine in (m, m0):
                machine.uc.mem_write(fmt, text.encode("utf-16le") + b"\0\0")
                machine.uc.mem_write(arg + 0x100, "str".encode("utf-16le") + b"\0\0")
                machine.uc.mem_write(arg, args)
                machine.uc.mem_write(dest, b"\xee" * 64)
                machine.call(0x4A400, ecx=dest, edx=fmt, args=(arg,), budget=200000)
                outs.append(bytes(machine.uc.mem_read(dest, 64)))
            self.assertEqual(outs[0], outs[1], text)

    def test_spreadsheet_kind_9_writes_the_grade_and_every_other_kind_is_unchanged(self) -> None:
        m, m0 = self.m, self.m0
        dest = m.ARENA + 0x2000
        for rating in range(-3, 121):
            m.uc.mem_write(dest, b"\xee" * 64)
            m.call(0x173120, eax=9, ecx=dest, args=(_fbits(float(rating)),), budget=200000)
            self.assertEqual(_wstr(m, dest), noah_grade(rating), rating)
        for kind, value in ((0, 87.0), (1, 0.875), (2, 0.875), (3, 12.0), (4, 3.25), (5, 1234.0), (6, 3.5), (7, 3.14159),
                            (8, 2.5), (10, 1.0), (99, 1.0), (0xFFFFFFFF, 1.0)):
            outs = []
            for machine in (m, m0):
                machine.uc.mem_write(dest, b"\xee" * 64)
                machine.call(0x173120, eax=kind, ecx=dest, args=(_fbits(value),), budget=200000)
                outs.append(bytes(machine.uc.mem_read(dest, 64)))
            self.assertEqual(outs[0], outs[1], kind)
        m.uc.mem_write(dest, b"\xee" * 64)
        m.call(0x173120, eax=10, ecx=dest, args=(_fbits(1.0),), budget=200000)
        self.assertEqual(_wstr(m, dest), "**NAN**")


# ---------------------------------------------------------------------------------------------------------
@unittest.skipUnless(HAVE_UC, "unicorn required")
class StudioBuildTests(unittest.TestCase):
    """Studio's own build on a small image that carries the retail executable: the option installs the owner."""

    def test_the_build_installs_exactly_what_the_module_installs(self) -> None:
        from unittest import mock
        from nfl2k5_commentary_swap_test import _dir_node
        retail = _retail()
        size = len(retail)
        directory = _dir_node([(64, size, 0x80, "default.xbe"),
                               ((64 * 2048 + size + 2047) // 2048, 40 * 4096, 0x80, "textures.bin")])
        image = bytearray(64 * 2048 + size + (-size) % 2048 + 40 * 4096)
        magic = b"MICROSOFT*XBOX*MEDIA"
        image[0x10000:0x10014] = magic
        struct.pack_into("<II", image, 0x10014, 33, len(directory))
        image[0x107EC:0x10800] = magic
        image[33 * 2048:33 * 2048 + len(directory)] = directory
        image[64 * 2048:64 * 2048 + size] = retail
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / "tiny.iso", Path(temp) / "out.iso"
            source.write_bytes(image)
            plan = mod_build.BuildPlan(str(source), str(target), letter_grades=True, throw=False, catch_slider=False,
                                       draft_ai=False, returner_fix=False, realistic_flight=False)
            with mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
                receipt = mod_build.build(plan)
            self.assertIn("xbe_space", [step.get("step") for step in receipt["steps"]])
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                offset, length = tt.image_xbe_extent(fd, os.fstat(fd).st_size)
                built = os.pread(fd, length, offset)
            finally:
                os.close(fd)
        self.assertEqual(lg.status(built), "applied")
        self.assertEqual(built, lg.apply(retail)[0])
        # off leaves the executable retail
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / "tiny.iso", Path(temp) / "out.iso"
            source.write_bytes(image)
            plan = mod_build.BuildPlan(str(source), str(target), letter_grades=False, throw=False, catch_slider=False,
                                       draft_ai=False, returner_fix=False, realistic_flight=False)
            with mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
                mod_build.build(plan)
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                offset, length = tt.image_xbe_extent(fd, os.fstat(fd).st_size)
                plain = os.pread(fd, length, offset)
            finally:
                os.close(fd)
        self.assertEqual(plain, retail)
        self.assertEqual(lg.status(plain), "retail")


def _v05_xbe():
    if not V05_DISC.is_file():
        raise unittest.SkipTest("the shipped SOFTDRINK 2K28 v0.5 disc is absent")
    sys.path.insert(0, str(REPO / "tools"))
    import nfl_uniform_color_xiso_direct_patch as xc
    fd = os.open(V05_DISC, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(fd).st_size
        entries, _ = xc.parse_xdvdfs(fd, size)
        entry = next(e for e in entries.values() if e.path.strip("/") == "default.xbe")
        data = os.pread(fd, entry.size, entry.base_offset + entry.sector * 0x800)
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != V05_XBE_SHA256:
        raise unittest.SkipTest("the disc's default.xbe is not the shipped v0.5 executable")
    return data


def _v05_roster():
    from mod_editor.core import nfl2k5_roster_records as rr
    try:
        return rr.load_image(V05_DISC)
    except Exception as exc:                      # noqa: BLE001 - the roster is optional evidence
        raise unittest.SkipTest(f"v0.5 roster unreadable: {exc}")


@unittest.skipUnless(HAVE_UC, "unicorn required")
class V05NativeTests(unittest.TestCase):
    """The repair and every patched display path on the shipped v0.5 executable and roster (real players, real teams)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.v05 = _v05_xbe()
        sys.path.insert(0, str(REPO / "tools" / "b77"))
        import f4_repair
        cls.repair = f4_repair
        cls.patched, cls.receipt = f4_repair.repair_xbe(cls.v05)
        cls.roster = _v05_roster()
        from tests.nfl2k5_supersim_draft_fixture import Machine
        cls.mp = Machine(cls.patched, trace_writes=False)
        cls.m0 = Machine(cls.v05, trace_writes=False)

    # --- the repair ------------------------------------------------------------------------------------
    def test_the_repair_is_scoped_deterministic_and_idempotent(self) -> None:
        self.assertEqual(hashlib.sha256(self.patched).hexdigest(), self.repair.FIXED_V05_SHA256)
        self.assertEqual(self.receipt["status"], "applied")
        self.assertTrue(self.receipt["outside_scope_identical"])
        self.assertTrue(self.receipt["existing_allocations_unchanged"])
        self.assertEqual(self.receipt["changed_bytes"], 1194)
        changed = [s["label"] for s in self.receipt["scopes"] if s["changed"]]
        self.assertEqual(len(changed), 37)
        self.assertIn("owned RX code (160 bytes)", changed)
        again, receipt = self.repair.repair_xbe(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["status"], "already_applied")
        self.assertEqual(receipt["changed_bytes"], 0)
        # no byte outside the declared scopes: restoring the scopes from the input reproduces the input
        restored = bytearray(self.patched)
        for start, end, _label in self.repair.declared_scopes(self.v05, self.patched):
            restored[start:end] = self.v05[start:end]
        self.assertEqual(bytes(restored), self.v05)
        self.assertEqual(len(self.patched), len(self.v05))
        self.assertEqual(lg.status(self.v05), "retail")
        self.assertEqual(lg.status(self.patched), "applied")

    def test_every_existing_owner_keeps_its_bytes_and_address(self) -> None:
        old = space.layout(self.v05)["allocations"]
        new = space.layout(self.patched)["allocations"]
        for row in old:
            self.assertIn(row, new)
        mine = [row for row in new if row["owner"] == lg.OWNER]
        self.assertEqual([(r["kind"], r["size"]) for r in mine], [("code", 160), ("read_only", 240)])
        k128 = [row for row in new if row["owner"] == "nfl2k5_k128"][0]
        self.assertEqual(mine[0]["va"], k128["va"] + k128["size"])
        # every other owner's installed bytes are untouched
        for row in old:
            if row["owner"] == space.DIRECTORY_OWNER:
                continue
            self.assertEqual(self.v05[row["raw"]:row["raw"] + row["size"]],
                             self.patched[row["raw"]:row["raw"] + row["size"]], row["owner"])

    def test_the_repair_refuses_foreign_input(self) -> None:
        with self.assertRaises(ValueError):
            self.repair.repair_xbe(self.v05[:-1])
        broken = bytearray(self.v05)
        off = rdata.offset_of(self.v05, 0x31F71E)
        broken[off] ^= 1
        with self.assertRaises(ValueError):
            self.repair.repair_xbe(bytes(broken))

    # --- the descriptors and the sort-key code --------------------------------------------------------
    def test_columns_get_kind_9_and_keep_every_getter_byte(self) -> None:
        for label, va in lg.PLAYER_COLUMNS + lg.TEAM_COLUMNS:
            before = bytes(self.m0.uc.mem_read(va, 0xB0))
            after = bytes(self.mp.uc.mem_read(va, 0xB0))
            self.assertEqual(before[:4], bytes.fromhex("05000000"), label)
            self.assertEqual(after[:4], bytes.fromhex("05090000"), label)
            self.assertEqual(before[4:], after[4:], label)             # sub kind, getter, cookie, widths, headers
        # the getters the columns call: 0xE6660 for players, 0x34BB60/80/A0 for the team columns
        self.assertEqual(self.mp.get(0x540BB0), 0xE6660)
        self.assertEqual([self.mp.get(va + 8) for _l, va in lg.TEAM_COLUMNS], [0x34BB60, 0x34BB80, 0x34BBA0])

    def test_the_code_that_reads_the_number_for_sorting_is_byte_identical(self) -> None:
        """Lists sort on the number: every consumer of the overall and the team rating other than the five panel
        formatters (the sort keys, the AI and the sim) is untouched, and none of them reaches the grade code."""
        ranges = ((0x27E580, 0x27E5F2), (0x27E600, 0x27E903), (0x27E910, 0x27EAE3), (0x31E0F0, 0x31E203),
                  (0x34A7E0, 0x34A836), (0x36EDD0, 0x36EE6C), (0x36F0A0, 0x36F146), (0x360A10, 0x360A7D),
                  (0x2BDB00, 0x2BDCE3), (0x2BB390, 0x2BB4CE), (0x10C540, 0x10C5CB), (0x365B20, 0x365C6B),
                  (0x2AFF70, 0x2B00D3), (0x2AEC80, 0x2AECF4), (0x115ED0, 0x115FA0), (0x246A80, 0x246BFA),
                  (0x246C00, 0x246D52), (0x246D60, 0x246D8A), (0x246D90, 0x246DE0), (0x0E6660, 0x0E6670),
                  (0x0C4830, 0x0C4890), (0x0C48A0, 0x0C48D0), (0x34BB60, 0x34BBB5))
        for lo, hi in ranges:
            self.assertEqual(bytes(self.mp.uc.mem_read(lo, hi - lo)), bytes(self.m0.uc.mem_read(lo, hi - lo)),
                             f"{lo:#x}..{hi:#x}")
        # the delegate dispatch the spreadsheet getters run through
        for lo, hi in ((0x172930, 0x1729A5), (0x1728A0, 0x172915), (0x16F620, 0x16F624)):
            self.assertEqual(bytes(self.mp.uc.mem_read(lo, hi - lo)), bytes(self.m0.uc.mem_read(lo, hi - lo)))
        # the only edits are the 28 sites (and the owned pages): nothing else in the executable changed
        found = lg.allocations(self.patched)
        handler = lg.labels(found["code"]["va"], found["read_only"]["va"])["convert_R"]
        self.assertEqual(self.mp.get(0x4E69BC), handler)

    # --- real players and teams ------------------------------------------------------------------------
    def _overall(self, machine, record: bytes) -> int:
        address = machine.ARENA + 0x40000
        machine.uc.mem_write(address, record)
        return machine.call(0xE6660, ecx=address, budget=200000)

    def _players(self, step: int = 7):
        return self.roster.players[::step]

    def test_the_overall_the_game_computes_matches_the_python_native_overall(self) -> None:
        from mod_editor.core import nfl2k5_my_career_prospects as prospects
        for player in self.roster.players[::5]:
            self.assertEqual(self._overall(self.mp, player.record.encode()),
                             prospects.native_overall(player.record, lineman=True), player.display)

    def _site(self, machine, name: str, record: bytes) -> str:
        player = machine.ARENA + 0x40000
        dest = machine.ARENA + 0x60000
        machine.uc.mem_write(player, record)
        machine.uc.mem_write(dest, b"\xee" * 64)
        if name == "card":
            machine.put(0xC90248, player)
            seen = {}

            def hook(uc, address, size, user):
                seen["ecx"] = machine.reg("ECX")
            handle = machine.uc.hook_add(machine.u.UC_HOOK_CODE, hook, begin=0x3206CD, end=0x3206CD)
            machine.call(0x320640, stop=0x3206D2, budget=100000)
            machine.uc.hook_del(handle)
            return _wstr(machine, seen["ecx"])
        if name == "depth":
            handle = machine.leaf(0x242AE0, lambda: machine.ret(player, pop=0xC),
                                  reason="the depth chart slot resolver returns the one real player under test")
            machine.call(0x2434C0, edx=0x75, args=(dest, 0, 0), budget=200000)
        elif name == "weekly_prep":
            handle = machine.leaf(0x2AFF70, lambda: machine.ret(player, pop=4),
                                  reason="the weekly prep slot resolver returns the one real player under test")
            machine.call(0x2B0940, edx=36, args=(dest, 0, 0), budget=200000)
        elif name == "matchups":
            # the Matchups callback resolves its row through weekly prep state; its overall branch (0x2AF25C onward) is
            # entered here with the frame it has at that point: esi = the output buffer, ecx = the matchup's player
            uc, esp = machine.uc, machine.STACK
            uc.mem_write(esp, struct.pack("<8I", 0, 0, 0, 0, machine.STOP, dest, 0, 0))
            for reg, value in (("ESP", esp), ("ECX", player), ("ESI", dest), ("EDX", 0), ("EAX", 0), ("EBX", 0x11111111),
                               ("EDI", 0x33333333), ("EBP", 0x44444444), ("EFLAGS", 0x202)):
                machine.reg(reg, value)
            uc.emu_start(0x2AF25C, machine.STOP, count=200000)
            handle = None
        elif name == "contract":
            state = machine.ARENA + 0x70000
            machine.uc.mem_write(state, struct.pack("<I", player) + bytes(0x40))
            machine.put(0xCB8C34, state)
            handle = None
            machine.call(0x3473C0, edx=1, args=(dest, 0, 0), budget=300000)
        else:
            raise AssertionError(name)
        if handle is not None:
            machine.uc.hook_del(handle)
        return _wstr(machine, dest)

    def test_four_panel_sites_show_the_grade_of_the_real_players_overall(self) -> None:
        checked = 0
        for player in self._players():
            record = player.record.encode()
            overall = self._overall(self.mp, record)
            grade = noah_grade(overall)
            for site, want_patched, want_before in (("card", grade, str(overall)),
                                                    ("depth", grade, str(overall)),
                                                    ("weekly_prep", grade, str(overall)),
                                                    ("matchups", grade, str(overall)),
                                                    ("contract", "Overall:" + grade, "Overall:" + str(overall))):
                self.assertEqual(self._site(self.mp, site, record), want_patched, (site, player.display, overall))
                self.assertEqual(self._site(self.m0, site, record), want_before, (site, player.display, overall))
            checked += 1
        self.assertGreater(checked, 300)

    def _card_glyphs(self, machine, record: bytes) -> list[tuple[int, float]]:
        """Run the real Player Card function through the real glyph drawer; -> [(glyph index, x)] per drawn glyph.

        Only the team lookup and the team colour table (game state the drawer merely receives) are substituted; the
        string comes from the real swprintf, the centring from the real width routine, the glyphs from the real drawer.
        With the glyph meshes not loaded (static image) the real glyph routine returns just the advance width."""
        player = machine.ARENA + 0x40000
        machine.uc.mem_write(player, record)
        machine.put(0xC90248, player)
        seen: list[tuple[int, float]] = []

        def on_glyph(uc, address, size, user):
            seen.append((machine.reg("EAX"), machine.f32(machine.reg("ESP") + 4)))
        handles = [machine.uc.hook_add(machine.u.UC_HOOK_CODE, on_glyph, begin=0xEF420, end=0xEF420),
                   machine.leaf(0x69E70, lambda: machine.ret(0x1234),
                                reason="the current team lookup is game state; the drawer is only handed a colour"),
                   machine.leaf(0x68D70, lambda: machine.ret(0xFF204080),
                                reason="the team colour table is game state; the drawer is only handed a colour")]
        try:
            machine.call(0x320640, stop=0x3206FB, budget=600000)
        finally:
            for handle in handles:
                machine.uc.hook_del(handle)
        return seen

    def test_player_card_drawer_draws_the_sign_glyphs(self) -> None:
        """Retail draws digits only; with %R the patched drawer must draw the letter AND the plus or minus mesh."""
        def glyph(char: str) -> int:
            if char.isalpha():
                return ord(char.upper()) - ord("A")
            if char.isdigit():
                return 26 + int(char)                       # number_0 is glyph 26 (0x30 - 0x16)
            return {"-": 38, "+": 39}[char]
        centres, checked, signed = set(), 0, 0
        for player in self.roster.players[::11]:
            record = player.record.encode()
            overall = self._overall(self.mp, record)
            label = noah_grade(overall)
            after = self._card_glyphs(self.mp, record)
            before = self._card_glyphs(self.m0, record)
            self.assertEqual([g for g, _x in after], [glyph(c) for c in label], (overall, label))
            self.assertEqual([g for g, _x in before], [glyph(c) for c in str(overall)], overall)
            for run in (after, before):
                widths = [self.mp.f32(0xA90F18 + 12 * g) for g, _x in run]
                for (g0, x0), (g1, x1), w in zip(run, run[1:], widths):
                    self.assertAlmostEqual(x1 - x0, w, places=3)          # each glyph advances by its table width
                centres.add(round(run[0][1] + sum(widths) / 2, 2))        # centred on one fixed x: the width routine agrees
            signed += len(label) > 1
            checked += 1
        self.assertEqual(len(centres), 1, centres)
        self.assertGreater(signed, 100)
        self.assertGreater(checked, 200)

    def test_trade_block_sentence_and_guideline_labels(self) -> None:
        machine = self.mp
        labels = [_wstr(machine, 0xEAD4F8 + 0x1C * i) for i in range(7)]
        self.assertEqual(labels, ["A or better", "B or better", "C or better", "D or better", "F or better",
                                  "F- (40+)", "F- (30+)"])
        self.assertEqual(_wstr(machine, 0xEAD5BC), "any rating")
        for machine, patched in ((self.mp, True), (self.m0, False)):
            for rating in (95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 49, 40, 30, 1):
                machine.uc.mem_write(0xCB8C61, b"\x00")
                machine.uc.mem_write(0xE3C27C + 0x36, bytes([0]))
                machine.uc.mem_write(0xE3C27C + 0x39, bytes([rating]))
                text = _wstr(machine, machine.call(0x349CA0, ecx=0, budget=300000))
                shown = noah_grade(rating) if patched else str(rating)
                self.assertEqual(text, f"A QB with rating {shown} or better.", (patched, rating))

    @classmethod
    def _load_roster(cls, machine) -> None:
        body = cls.roster.original if hasattr(cls.roster, "original") else None
        machine.uc.mem_write(machine.ARENA + 0x300, bytes(body))
        machine.fixup_roster(machine.ARENA + 0x340)

    def _float_call(self, machine, fn: int, team: int) -> float:
        stub, team_a, fn_a, out = machine.STOP + 0x100, machine.ARENA + 0x1F0010, machine.ARENA + 0x1F0014, machine.ARENA + 0x1F0020
        if not getattr(machine, "_f4_stub", False):
            code = (b"\x8b\x0d" + struct.pack("<I", team_a) + b"\xff\x15" + struct.pack("<I", fn_a)
                    + b"\xd9\x1d" + struct.pack("<I", out) + b"\xc3")
            machine.uc.mem_write(stub, code)
            machine._f4_stub = True
        machine.put(team_a, team)
        machine.put(fn_a, fn)
        machine.call(stub, budget=3000000)
        return struct.unpack("<f", bytes(machine.uc.mem_read(out, 4)))[0]

    def test_team_select_shows_the_grade_of_each_real_team_rating(self) -> None:
        for machine in (self.mp, self.m0):
            self._load_roster(machine)
        teams = [self.mp.get(0xE5786C + 4 * t) for t in range(32)]
        seen = 0
        for team in teams:
            for fn in (0xC4830, 0xC4860, 0xC48A0):
                rating = self._float_call(self.mp, fn, team)
                self.assertEqual(rating, self._float_call(self.m0, fn, team))
                shown = int(min(100.0, rating * 100.0))          # the game: x100, clamp to 100, truncate
                for machine, want in ((self.mp, noah_grade(shown)), (self.m0, str(shown))):
                    scratch = machine.ARENA + 0x80000
                    machine.uc.mem_write(scratch, bytes(0x100))
                    esi = scratch + 0x40
                    machine.uc.mem_write(esi - 0x20, struct.pack("<f", rating))
                    machine.uc.mem_write(esi - 0x1C, struct.pack("<f", 0.5))
                    machine.call(0x31F6C2, esi=esi, stop=0x31F73A, budget=300000)
                    self.assertEqual(_wstr(machine, machine.reg("EDX")), want, (hex(fn), rating))
                seen += 1
        self.assertEqual(seen, 96)

    WRAPPERS = ((0x173300, 0x17331A, False), (0x173360, 0x173386, False), (0x1733E0, 0x1733FD, False),
                (0x173470, 0x173492, True), (0x173500, 0x17352E, True), (0x173580, 0x1735A5, True))

    def _cell(self, machine, wrapper, descriptor: int, value: int):
        entry, call_at, is_int = wrapper
        cell = machine.ARENA + 0x90000
        machine.uc.mem_write(cell, bytes(0x40))
        machine.put(cell, descriptor)
        machine.uc.mem_write(cell + 0xC, struct.pack("<i", value) if is_int else struct.pack("<f", float(value)))
        seen = {}

        def hook(uc, address, size, user):
            seen["ecx"], seen["eax"] = machine.reg("ECX"), machine.reg("EAX")
        handle = machine.uc.hook_add(machine.u.UC_HOOK_CODE, hook, begin=call_at, end=call_at)
        machine.call(entry, ecx=machine.ARENA + 0xA0000, edx=cell, stop=call_at + 5, budget=200000)
        machine.uc.hook_del(handle)
        return _wstr(machine, seen["ecx"]), seen["eax"]

    def test_spreadsheet_player_columns_show_grades_through_all_six_cell_wrappers(self) -> None:
        for player in self.roster.players[::9]:
            overall = self._overall(self.mp, player.record.encode())
            for label, descriptor in lg.PLAYER_COLUMNS:
                for wrapper in self.WRAPPERS:
                    text, kind = self._cell(self.mp, wrapper, descriptor, overall)
                    before, kind0 = self._cell(self.m0, wrapper, descriptor, overall)
                    self.assertEqual((text, kind, before, kind0), (noah_grade(overall), 9, str(overall), 0),
                                     (label, hex(wrapper[0]), overall))

    def test_spreadsheet_team_columns_show_grades_for_all_32_teams(self) -> None:
        self._load_roster(self.mp)
        teams = [self.mp.get(0xE5786C + 4 * t) for t in range(32)]
        checked = 0
        for team in teams:
            for (label, descriptor), getter in zip(lg.TEAM_COLUMNS, (0x34BB60, 0x34BB80, 0x34BBA0)):
                value = self.mp.call(getter, ecx=team, budget=3000000)
                for wrapper in self.WRAPPERS:
                    text, kind = self._cell(self.mp, wrapper, descriptor, value)
                    before, _ = self._cell(self.m0, wrapper, descriptor, value)
                    self.assertEqual((text, kind, before), (noah_grade(value), 9, str(value)), (label, value))
                checked += 1
        self.assertEqual(checked, 96)

    def test_attribute_columns_and_the_substitution_rating_stay_numbers(self) -> None:
        """Descriptors that are not in the site list keep kind 0, and their cell wrappers print the number."""
        speed = [va for va in range(0x4E3AE0, 0xA69980 - 16, 4)
                 if self.mp.get(va + 8) == 0x2B9030 and self.mp.get(va) == 5 and self.mp.get(va + 4) == 3]
        self.assertGreaterEqual(len(speed), 2)                 # SPD on two Franchise sheets
        for descriptor in speed + [0x515928]:                  # the attribute columns and the Substitution RTG
            self.assertEqual(self.mp.get(descriptor), 5)
            text, kind = self._cell(self.mp, self.WRAPPERS[3], descriptor, 87)
            self.assertEqual((text, kind), ("87", 0))

    def test_the_grade_distribution_of_the_v05_roster(self) -> None:
        counts: dict[str, int] = {}
        for player in self.roster.players:
            grade = noah_grade(self._overall(self.mp, player.record.encode()))
            counts[grade] = counts.get(grade, 0) + 1
        self.assertEqual(sum(counts.values()), len(self.roster.players))
        self.assertEqual(set(counts), {g for _l, _h, g in NOAH_SCALE})


if __name__ == "__main__":
    unittest.main()

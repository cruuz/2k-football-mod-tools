"""Beta 75: the1wam's lineman rating adjustment.

the1wam (#nfl2k28-softdrink-edition-mod, 2026-09-21/22) reported that the game's OVERALL
moves with a player's height and weight while he builds rosters, and asked for the effect to
be capped for offensive linemen: 326 lb and up calculated as 294 lb, 325 lb and down as
317 lb, "only make it affect the overall rating not gameplay".

The research is in ``mod_editor/core/nfl2k5_lineman_rating.py``. These tests pin the two
retail spans, prove apply and revert are exact on a synthetic executable, execute the cave
natively and compare it against the retail routine it wraps, and keep the Build wiring
honest. The retail-only class re-derives the formula, the profile tables and the dead cave
from the executable itself; it carries digests, never retail bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
for entry in (REPO, REPO / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_lineman_rating as lineman  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe as _plain_synthetic_xbe  # noqa: E402

try:
    import capstone
except ImportError:                                     # pragma: no cover - environment probe
    capstone = None
try:
    import unicorn
    from unicorn import x86_const
except ImportError:                                     # pragma: no cover - environment probe
    unicorn = None
    x86_const = None


def _build_synthetic_xbe(*args, **kwargs):
    """The shared synthetic image with the overall dispatch and the cave written in (opt-in
    there so the frozen beta 60/61 pack receipts, which hash the plain image, keep their hash)."""

    kwargs.setdefault("lineman", True)
    return _plain_synthetic_xbe(*args, **kwargs)


XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"

# The decoded per-position profiles and the two attribute descriptors an offensive line uses,
# hashed instead of quoted so no retail bytes live in the repository.
PROFILE_DIGEST = "b8b31bdb16e653b4b5f90d40ee089ce68a9fa00b51752c897d3d42e18cd7464d"


class RuleTests(unittest.TestCase):
    def test_the_rule_is_the1wams_two_branches_on_the_offensive_line_only(self) -> None:
        for code in lineman.LINE_POSITION_CODES:
            self.assertEqual(lineman.substituted_weight(code, 326), 294)
            self.assertEqual(lineman.substituted_weight(code, 325), 317)
            self.assertEqual(lineman.substituted_weight(code, 405), 294)
            self.assertEqual(lineman.substituted_weight(code, 150), 317)
            # the whole legal weight range lands on exactly one of the two values
            self.assertEqual({lineman.substituted_weight(code, w) for w in range(150, 406)},
                             {294, 317})

    def test_the_offensive_line_codes_are_center_guard_and_tackle(self) -> None:
        self.assertEqual(lineman.LINE_POSITION_CODES, (12, 13, 14))
        self.assertEqual([rr.POSITIONS[code] for code in lineman.LINE_POSITION_CODES],
                         ["C", "G", "T"])
        self.assertEqual(rr.SCHEME_GROUP_CODES["retail"]["OL"], lineman.LINE_POSITION_CODES)

    def test_no_other_position_is_touched(self) -> None:
        for code, name in enumerate(rr.POSITIONS):
            if code in lineman.LINE_POSITION_CODES:
                continue
            for weight in (150, 294, 317, 325, 326, 405):
                self.assertEqual(lineman.substituted_weight(code, weight), weight, name)

    def test_the_stored_byte_form_is_the_same_rule_minus_one_hundred_and_fifty(self) -> None:
        self.assertEqual(lineman.WEIGHT_BIAS, 150)
        self.assertEqual(rr.FIELD_BY_NAME["weight_raw"].offset, lineman.WEIGHT_FIELD)
        self.assertEqual(rr.FIELD_BY_NAME["position"].offset, lineman.POSITION_FIELD)
        for weight in range(150, 406):
            self.assertEqual(lineman.substituted_weight_raw(13, weight - 150),
                             lineman.substituted_weight(13, weight) - 150)


class ShapeTests(unittest.TestCase):
    def test_the_two_spans_are_the_documented_sites_and_keep_their_lengths(self) -> None:
        sites = lineman.sites()
        self.assertEqual([label for label, _va, _b, _a in sites],
                         ["overall_dispatch", "lineman_weight_cave"])
        self.assertEqual([va for _l, va, _b, _a in sites], [0x246D60, 0x1D2400])
        for label, _va, before, after in sites:
            self.assertEqual(len(before), len(after), label)
            self.assertNotEqual(before, after, label)

    def test_only_the_call_target_moves_at_the_dispatch(self) -> None:
        retail, patched = lineman.RETAIL_HOOK, lineman.PATCHED_HOOK
        at = lineman.HOOK_CALL_OFFSET
        self.assertEqual(retail[at], 0xE8)
        self.assertEqual(retail[:at + 1], patched[:at + 1])
        self.assertEqual(retail[at + 5:], patched[at + 5:])
        self.assertEqual(sum(x != y for x, y in zip(retail, patched)), 2)
        end = lineman.HOOK_VA + at + 5
        self.assertEqual(end + struct.unpack_from("<i", retail, at + 1)[0], lineman.OVERALL_BLEND_VA)
        self.assertEqual(end + struct.unpack_from("<i", patched, at + 1)[0], lineman.CAVE_VA)

    def test_the_cave_fits_with_room_to_spare_and_is_padded_with_int3(self) -> None:
        code = lineman.cave_code()
        self.assertEqual(len(code), lineman.CODE_BYTES)
        self.assertLessEqual(len(code), lineman.CAVE_SIZE)
        self.assertEqual(lineman.PATCHED_CAVE[:len(code)], code)
        self.assertEqual(lineman.PATCHED_CAVE[len(code):],
                         b"\xcc" * (lineman.CAVE_SIZE - len(code)))

    def test_the_cave_carries_the_two_substitution_constants_and_the_threshold(self) -> None:
        code = lineman.cave_code()
        self.assertIn(bytes((0xB2, lineman.LIGHT_READS_RAW)), code)     # mov dl, 167  (317 lb)
        self.assertIn(bytes((0xB2, lineman.HEAVY_READS_RAW)), code)     # mov dl, 144  (294 lb)
        self.assertIn(bytes((0x3C, lineman.HEAVY_FROM_RAW)), code)      # cmp al, 176  (326 lb)
        self.assertEqual((lineman.HEAVY_FROM_RAW, lineman.HEAVY_READS_RAW, lineman.LIGHT_READS_RAW),
                         (176, 144, 167))

    def test_revert_is_the_exact_inverse_of_apply(self) -> None:
        forward = lineman.sites()
        self.assertEqual([(label, va, after, before) for label, va, before, after in forward],
                         lineman.revert_sites())

    @unittest.skipUnless(capstone is not None, "capstone is required to read the cave back")
    def test_the_cave_disassembles_to_the_documented_wrapper(self) -> None:
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        rows = [(i.mnemonic, i.op_str) for i in md.disasm(lineman.cave_code(), lineman.CAVE_VA)]
        self.assertEqual(rows, [
            ("sub", "edx, 0xc"), ("cmp", "edx, 2"), ("ja", hex(lineman.CAVE_VA + 0x2A)),
            ("push", "ecx"), ("mov", "al, byte ptr [ecx + 0x2a]"), ("push", "eax"),
            ("mov", "dl, 0xa7"), ("cmp", "al, 0xb0"), ("jb", hex(lineman.CAVE_VA + 0x15)),
            ("mov", "dl, 0x90"), ("mov", "byte ptr [ecx + 0x2a], dl"),
            ("push", "dword ptr [esp + 0x10]"), ("push", "ecx"),
            ("call", hex(lineman.OVERALL_BLEND_VA)),
            ("pop", "eax"), ("pop", "ecx"), ("mov", "byte ptr [ecx + 0x2a], al"),
            ("ret", "8"), ("jmp", hex(lineman.OVERALL_BLEND_VA))])

    @unittest.skipUnless(capstone is not None, "capstone is required to read the cave back")
    def test_the_retail_cave_is_four_dead_accessor_stubs(self) -> None:
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        rows = [(i.address, i.mnemonic, i.op_str)
                for i in md.disasm(lineman.RETAIL_CAVE, lineman.CAVE_VA)
                if i.mnemonic != "nop"]
        self.assertEqual([row[0] - lineman.CAVE_VA for row in rows],
                         [0x00, 0x03, 0x10, 0x13, 0x20, 0x23, 0x30, 0x33])
        self.assertEqual({row[1] for row in rows}, {"mov", "ret"})


class SyntheticPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_the_default_synthetic_image_does_not_carry_the_window(self) -> None:
        self.assertEqual(lineman.status(_plain_synthetic_xbe()), "foreign")

    def test_status_is_retail_then_applied_and_revert_is_byte_exact(self) -> None:
        self.assertEqual(lineman.status(self.payload), "retail")
        patched, receipt = lineman.apply(self.payload)
        self.assertEqual(lineman.status(patched), "applied")
        self.assertTrue(receipt["experimental"])
        self.assertFalse(receipt["witnessed"])
        self.assertEqual(receipt["label"], lineman.UI_LABEL)
        self.assertEqual([edit["label"] for edit in receipt["edits"]],
                         ["overall_dispatch", "lineman_weight_cave"])
        reverted, _ = lineman.revert(patched)
        self.assertEqual(reverted, self.payload)

    def test_apply_is_idempotent_and_revert_of_retail_is_a_no_op(self) -> None:
        patched, _ = lineman.apply(self.payload)
        again, receipt = lineman.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(receipt["already_applied"])
        same, receipt = lineman.revert(self.payload)
        self.assertEqual(same, self.payload)
        self.assertTrue(receipt["already_applied"])

    def test_a_foreign_executable_is_refused(self) -> None:
        payload = bytearray(self.payload)
        off = rdata.offset_of(bytes(payload), lineman.HOOK_VA)
        payload[off + 4] ^= 0xFF
        self.assertEqual(lineman.status(bytes(payload)), "foreign")
        with self.assertRaises(lineman.LinemanRatingError):
            lineman.apply(bytes(payload))

    def test_nothing_outside_the_two_spans_and_the_section_digest_moves(self) -> None:
        patched, _ = lineman.apply(self.payload)
        spans = []
        for _label, va, retail, _p in lineman.sites():
            off = rdata.offset_of(self.payload, va)
            spans.append((off, off + len(retail)))
        digest_slots = [(h + 36, h + 56) for h in self._section_headers(self.payload)]
        for index, (a, b) in enumerate(zip(self.payload, patched)):
            if a == b:
                continue
            self.assertTrue(any(lo <= index < hi for lo, hi in spans + digest_slots),
                            f"byte 0x{index:x} changed outside the patched spans")

    @staticmethod
    def _section_headers(payload: bytes) -> list[int]:
        count, table = struct.unpack_from("<II", payload, 0x11C)
        base = struct.unpack_from("<I", payload, 0x104)[0]
        return [table - base + i * 56 for i in range(count)]


@unittest.skipUnless(unicorn is not None, "unicorn is required for the native cave proof")
class NativeWrapperTests(unittest.TestCase):
    """Run the patched dispatch and the retail dispatch and compare what the blend sees.

    Not a game witness: the blend itself is replaced by a stub that records its arguments,
    the profile pointer and the weight byte the player carried at that moment.
    """

    CODE_BASE, CODE_SIZE = 0x001D0000, 0x00090000       # covers the cave and the dispatch
    DATA_BASE, DATA_SIZE = 0x00AC0000, 0x00010000       # the profile table and the record
    STACK_BASE, STACK_SIZE = 0x00300000, 0x00010000
    PLAYER = 0x00AC8000
    SCRATCH = 0x00AC9000
    PROFILE = 0x00AC9800
    DONE = 0x00246F00

    def _stub(self) -> bytes:
        """`ret 8` after recording (weight byte, ebx, arg0, arg1, esp) into SCRATCH."""

        out = bytearray()
        out += bytes.fromhex("8b442404")                                # mov eax,[esp+4]
        out += bytes((0x8A, 0x40, lineman.WEIGHT_FIELD))                # mov al,[eax+0x2a]
        out += b"\xa2" + struct.pack("<I", self.SCRATCH)                # mov [SCRATCH], al
        out += b"\x89\x1d" + struct.pack("<I", self.SCRATCH + 4)        # mov [SCRATCH+4], ebx
        out += bytes.fromhex("8b442404")                                # mov eax,[esp+4]
        out += b"\xa3" + struct.pack("<I", self.SCRATCH + 8)            # mov [SCRATCH+8], eax
        out += bytes.fromhex("8b442408")                                # mov eax,[esp+8]
        out += b"\xa3" + struct.pack("<I", self.SCRATCH + 12)           # mov [SCRATCH+12], eax
        out += b"\x89\x25" + struct.pack("<I", self.SCRATCH + 16)       # mov [SCRATCH+16], esp
        out += bytes.fromhex("c20800")                                  # ret 8
        return bytes(out)

    def _run(self, hook: bytes, cave: bytes | None, position: int, weight_raw: int) -> dict:
        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        uc.mem_map(self.CODE_BASE, self.CODE_SIZE)
        uc.mem_map(self.DATA_BASE, self.DATA_SIZE)
        uc.mem_map(self.STACK_BASE, self.STACK_SIZE)
        uc.mem_write(lineman.HOOK_VA, hook)
        if cave is not None:
            uc.mem_write(lineman.CAVE_VA, cave)
        uc.mem_write(lineman.OVERALL_BLEND_VA, self._stub())
        uc.mem_write(self.DONE, b"\xc3")
        record = bytearray(0x54)
        record[lineman.WEIGHT_FIELD] = weight_raw
        record[lineman.POSITION_FIELD] = position
        uc.mem_write(self.PLAYER, bytes(record))
        uc.mem_write(lineman.POSITION_PROFILE_TABLE_VA + position * 4, struct.pack("<I", self.PROFILE))
        top = self.STACK_BASE + self.STACK_SIZE - 0x100
        uc.reg_write(x86_const.UC_X86_REG_ESP, top - 8)
        uc.mem_write(top - 4, struct.pack("<I", 0x11112222))            # the routine's own argument
        uc.mem_write(top - 8, struct.pack("<I", self.DONE))             # the return address
        uc.reg_write(x86_const.UC_X86_REG_ECX, self.PLAYER)
        uc.reg_write(x86_const.UC_X86_REG_EDX, position)
        uc.reg_write(x86_const.UC_X86_REG_EBX, 0xDEADBEEF)
        uc.emu_start(lineman.HOOK_VA, self.DONE)
        seen = uc.mem_read(self.SCRATCH, 20)
        return {"weight_seen": seen[0],
                "profile_seen": struct.unpack_from("<I", seen, 4)[0],
                "player_arg": struct.unpack_from("<I", seen, 8)[0],
                "mode_arg": struct.unpack_from("<I", seen, 12)[0],
                "blend_esp": struct.unpack_from("<I", seen, 16)[0],
                "record_after": bytes(uc.mem_read(self.PLAYER, 0x54)),
                "esp_after": uc.reg_read(x86_const.UC_X86_REG_ESP),
                "stack_top": top}

    def test_the_blend_sees_the_substituted_weight_for_every_line_position(self) -> None:
        for code in lineman.LINE_POSITION_CODES:
            for weight in (150, 293, 294, 317, 325, 326, 327, 405):
                raw = weight - lineman.WEIGHT_BIAS
                got = self._run(lineman.PATCHED_HOOK, lineman.PATCHED_CAVE, code, raw)
                self.assertEqual(got["weight_seen"] + lineman.WEIGHT_BIAS,
                                 lineman.substituted_weight(code, weight),
                                 f"{rr.POSITIONS[code]} at {weight} lb")
                self.assertEqual(got["record_after"][lineman.WEIGHT_FIELD], raw,
                                 "the real weight byte must be back before the routine returns")

    def test_every_other_position_reaches_the_blend_with_its_own_weight_untouched(self) -> None:
        for code in range(len(rr.POSITIONS)):
            if code in lineman.LINE_POSITION_CODES:
                continue
            for weight in (294, 326, 405):
                raw = weight - lineman.WEIGHT_BIAS
                got = self._run(lineman.PATCHED_HOOK, lineman.PATCHED_CAVE, code, raw)
                self.assertEqual(got["weight_seen"], raw, rr.POSITIONS[code])
                self.assertEqual(got["record_after"][lineman.WEIGHT_FIELD], raw)

    def test_the_patched_dispatch_matches_retail_in_every_respect_but_the_weight(self) -> None:
        for code in list(lineman.LINE_POSITION_CODES) + [0, 3, 9, 15, 16]:
            for weight in (280, 326):
                raw = weight - lineman.WEIGHT_BIAS
                plain = self._run(lineman.RETAIL_HOOK, None, code, raw)
                patched = self._run(lineman.PATCHED_HOOK, lineman.PATCHED_CAVE, code, raw)
                for key in ("profile_seen", "player_arg", "mode_arg", "esp_after"):
                    self.assertEqual(plain[key], patched[key], f"{key} at {rr.POSITIONS[code]}")
                self.assertEqual(plain["record_after"], patched["record_after"])
                self.assertEqual(patched["esp_after"], patched["stack_top"])
                self.assertEqual(patched["profile_seen"], self.PROFILE)
                self.assertEqual(patched["player_arg"], self.PLAYER)
                self.assertEqual(patched["mode_arg"], 0x11112222)
                if code in lineman.LINE_POSITION_CODES:
                    self.assertNotEqual(plain["weight_seen"], patched["weight_seen"])
                    # the wrapper's own frame: the saved player, the saved weight, the two
                    # re-pushed arguments and its return address, and nothing else
                    self.assertEqual(plain["blend_esp"] - patched["blend_esp"], 20)
                else:
                    self.assertEqual(plain["weight_seen"], patched["weight_seen"])
                    # a non-lineman tail-jumps: the blend runs on the retail frame exactly
                    self.assertEqual(plain["blend_esp"], patched["blend_esp"])


class BuildWiringTests(unittest.TestCase):
    @staticmethod
    def _plan(**kwargs) -> mod_build.BuildPlan:
        return mod_build.BuildPlan(source=Path("default.xbe"), target=Path("out.xbe"), **kwargs)

    def test_the_option_is_off_by_default_and_asks_for_an_xbe_patch_when_on(self) -> None:
        self.assertFalse(self._plan().the1wam_lineman_rating)
        self.assertFalse(self._plan().wants_xbe_patch())
        self.assertTrue(self._plan(the1wam_lineman_rating=True).wants_xbe_patch())

    def test_no_preset_turns_it_on(self) -> None:
        for name in mod_build.PRESETS:
            self.assertFalse(mod_build.apply_preset(self._plan(), name).the1wam_lineman_rating, name)

    def test_the_option_is_a_saved_build_setting(self) -> None:
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("the1wam_lineman_rating", settings.FEATURE_KEYS)

    def test_the_patch_lands_through_the_build_dispatcher_in_any_order(self) -> None:
        image = _build_synthetic_xbe()
        alone, _receipt = tt._apply_all(image, None, catch_slider=False, the1wam_lineman_rating=True)
        self.assertEqual(lineman.status(alone), "applied")
        with_others, _a = tt._apply_all(image, None, catch_slider=False,
                                        the1wam_lineman_rating=True, team_column=True)
        others_first, _b = tt._apply_all(image, None, catch_slider=False,
                                         team_column=True, the1wam_lineman_rating=True)
        self.assertEqual(with_others, others_first)
        self.assertEqual(lineman.status(with_others), "applied")

    def test_off_leaves_the_dispatch_alone(self) -> None:
        image = _build_synthetic_xbe()
        untouched, _receipt = tt._apply_all(image, None, catch_slider=False, team_column=True)
        self.assertEqual(lineman.status(untouched), "retail")

    def test_the_inspector_reports_the_row(self) -> None:
        import tempfile
        image = _build_synthetic_xbe()
        patched, _receipt = lineman.apply(image)
        with tempfile.TemporaryDirectory() as room:
            for payload, expected in ((image, "retail"), (patched, "applied")):
                path = Path(room) / "default.xbe"
                path.write_bytes(payload)
                self.assertEqual(tt.read_xbe(path)["the1wam_lineman_rating"], expected)

    def test_the_release_lists_carry_the_module(self) -> None:
        allowlist = (REPO / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split("\n")
        self.assertIn("mod_editor/core/nfl2k5_lineman_rating.py", allowlist)
        runtime = (REPO / "packaging" / "check_2k5_mod_studio_runtime.py").read_text(encoding="utf-8")
        self.assertIn("mod_editor.core.nfl2k5_lineman_rating", runtime)

    def test_the_capability_report_lists_the_module(self) -> None:
        self.assertTrue(mod_build.availability()["the1wam_lineman_rating"])

    def test_the_ui_strings_are_the1wams_words_and_carry_no_em_dash(self) -> None:
        for text in (lineman.UI_LABEL, lineman.HELP_TEXT, lineman.BUILD_CAPTION,
                     lineman.__doc__ or ""):
            self.assertNotIn(chr(0x2014), text)
        self.assertEqual(lineman.UI_LABEL, "the1wam lineman rating adjustment")
        self.assertIn("EXPERIMENTAL", lineman.HELP_TEXT)
        for number in ("326", "294", "325", "317"):
            self.assertIn(number, lineman.HELP_TEXT)


@unittest.skipUnless(XBE.is_file(), "the private USA default.xbe is not on this machine")
class RetailTests(unittest.TestCase):
    """Re-derive the overall computation from the executable; digests only, no retail bytes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = XBE.read_bytes()
        cls.text = next(s for s in _sections(cls.payload) if s.virtual_address == 0x11000)
        cls.text_bytes = cls.payload[cls.text.raw_offset: cls.text.raw_offset + cls.text.raw_size]
        cls.call_targets = _rel32_targets(cls.text_bytes, 0x11000)

    def _u32(self, va: int) -> int:
        return struct.unpack_from("<I", self.payload, rdata.offset_of(self.payload, va))[0]

    def _f32(self, va: int) -> float:
        return struct.unpack_from("<f", self.payload, rdata.offset_of(self.payload, va))[0]

    def _read(self, va: int, size: int) -> bytes:
        off = rdata.offset_of(self.payload, va)
        return self.payload[off: off + size]

    def test_the_pinned_spans_are_the_retail_bytes(self) -> None:
        for label, va, retail, _patched in lineman.sites():
            self.assertEqual(self._read(va, len(retail)), retail, label)
        self.assertEqual(lineman.status(self.payload), "retail")

    def test_the_blend_has_exactly_one_caller_and_it_is_the_patched_dispatch(self) -> None:
        callers = self.call_targets[lineman.OVERALL_BLEND_VA]
        self.assertEqual(callers, [lineman.HOOK_VA + lineman.HOOK_CALL_OFFSET])

    def test_the_cave_is_dead_everywhere_in_the_image(self) -> None:
        span = range(lineman.CAVE_VA, lineman.CAVE_VA + lineman.CAVE_SIZE)
        for va in span:
            self.assertEqual(self.call_targets.get(va, []), [], f"rel32 reaches 0x{va:x}")
            self.assertEqual(self.payload.find(struct.pack("<I", va)), -1,
                             f"a dword in the image equals 0x{va:x}")

    def test_the_weight_and_height_reads_are_where_the_research_says(self) -> None:
        # movzx edx, byte ptr [ebx+0x2a] ; ... ; add edx, 0x96   (the +150 bias)
        self.assertEqual(self._read(lineman.WEIGHT_READ_VA, 4),
                         bytes((0x0F, 0xB6, 0x53, lineman.WEIGHT_FIELD)))
        self.assertEqual(self._read(lineman.WEIGHT_READ_VA + 10, 6),
                         b"\x81\xc2" + struct.pack("<I", lineman.WEIGHT_BIAS))
        # movzx eax, byte ptr [ebx+0x2b]
        self.assertEqual(self._read(lineman.HEIGHT_READ_VA, 4), bytes((0x0F, 0xB6, 0x43, 0x2B)))

    def test_the_height_and_weight_coefficients_are_the_documented_constants(self) -> None:
        self.assertAlmostEqual(self._f32(lineman.HEIGHT_COEFFICIENT_VA),
                               lineman.HEIGHT_COEFFICIENT, places=7)
        self.assertAlmostEqual(self._f32(lineman.WEIGHT_COEFFICIENT_VA),
                               lineman.WEIGHT_COEFFICIENT, places=7)

    def test_the_line_profiles_use_only_the_two_blocking_attributes(self) -> None:
        for code in lineman.LINE_POSITION_CODES:
            profile = self._u32(lineman.POSITION_PROFILE_TABLE_VA + code * 4)
            count = self._u32(profile + 8)
            rows = self._read(self._u32(profile + 0x0C), count * 4)
            self.assertEqual(count, 2, rr.POSITIONS[code])
            self.assertEqual(sorted(rows[3::4]), [0, 1], rr.POSITIONS[code])
            self.assertEqual(sum(rows[0::4]), 100, "the profile weights are percentages")

    def test_height_is_dead_and_weight_is_live_for_the_offensive_line(self) -> None:
        for attribute, href, wref in lineman.LINE_ATTRIBUTE_REFERENCES:
            descriptor = self._u32(lineman.ATTRIBUTE_TABLE_VA + attribute * 8 + 4)
            self.assertAlmostEqual(self._f32(descriptor + 0x10), href, places=3)
            self.assertAlmostEqual(self._f32(descriptor + 0x18), wref, places=3)
            # 1000 inches is past every legal height, so max(0, height - Href) is always zero
            self.assertGreater(href, max(rr.NUMERIC_LIMITS["height"]))
            self.assertLess(wref, max(rr.NUMERIC_LIMITS["weight"]))

    def test_the_decoded_tables_match_their_pinned_digest(self) -> None:
        decoded = {"positions": {}, "attributes": {}}
        for code in range(len(rr.POSITIONS)):
            profile = self._u32(lineman.POSITION_PROFILE_TABLE_VA + code * 4)
            count = self._u32(profile + 8)
            rows = self._read(self._u32(profile + 0x0C), count * 4)
            decoded["positions"][rr.POSITIONS[code]] = {
                "base": round(self._f32(profile), 6), "span": round(self._f32(profile + 4), 6),
                "rows": [list(rows[i * 4: i * 4 + 4]) for i in range(count)]}
        for attribute in range(15):
            slots = self._u32(lineman.ATTRIBUTE_TABLE_VA + attribute * 8)
            descriptor = self._u32(lineman.ATTRIBUTE_TABLE_VA + attribute * 8 + 4)
            decoded["attributes"][attribute] = {
                "boost": round(self._f32(descriptor), 6),
                "gate_scale": round(self._f32(descriptor + 8), 6),
                "height_reference": round(self._f32(descriptor + 0x10), 6),
                "weight_reference": round(self._f32(descriptor + 0x18), 6),
                "terms": [[round(self._f32(descriptor + slot * 8), 6),
                           hex(self._u32(descriptor + slot * 8 + 4))] for slot in range(4, slots)]}
        blob = json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), PROFILE_DIGEST)

    def test_apply_and_revert_are_exact_on_the_real_executable(self) -> None:
        patched, receipt = lineman.apply(self.payload)
        self.assertEqual(lineman.status(patched), "applied")
        self.assertEqual(len(patched), len(self.payload))
        self.assertEqual(receipt["sections_repinned"], [0])
        reverted, _ = lineman.revert(patched)
        self.assertEqual(reverted, self.payload)


def _sections(payload: bytes):
    from mod_editor.core.nfl2k5_bump_strength import _sections as sections
    return sections(payload)


def _rel32_targets(blob: bytes, base: int) -> dict[int, list[int]]:
    """Every ``E8``/``E9`` rel32 in the blob, target -> the addresses that reach it."""

    out: dict[int, list[int]] = {}
    for index in range(len(blob) - 5):
        if blob[index] in (0xE8, 0xE9):
            target = (base + index + 5 + struct.unpack_from("<i", blob, index + 1)[0]) & 0xFFFFFFFF
            out.setdefault(target, []).append(base + index)
    return out


if __name__ == "__main__":       # pragma: no cover - CI runs this file directly too
    unittest.main()

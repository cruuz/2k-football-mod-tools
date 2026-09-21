"""Beta 75: the game's own Edit Player cycles all sixteen elbow pads.

X_Ray (#2k5-ideas, 2026-09-20) reported that High and Turf elbow pads cannot be selected
on the game's Edit Player screen, and that stepping off one a player already wears loses
it. Beta 74 fixed the Studio's list; the game's gate is a pair of constants in the two
elbow row handlers (``cmp dl, 9`` forward, a wrap that writes 9 backward), not a
per-player allowed set: every other equipment row on the same page already reaches its
whole list.

These tests pin the four retail spans, prove apply and revert are exact on a synthetic
executable, and keep the Build wiring honest. The retail-only class runs when the private
extraction is present and re-derives the gate from the executable itself.
"""

from __future__ import annotations

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
from mod_editor.core import nfl2k5_elbow_options as elbow  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe as _plain_synthetic_xbe  # noqa: E402


def _build_synthetic_xbe(*args, **kwargs):
    """The shared synthetic image with the Edit Player elbow window added (opt-in there so the
    frozen beta 60/61 pack receipts, which hash the plain image, keep their base hash)."""
    kwargs.setdefault("elbow", True)
    return _plain_synthetic_xbe(*args, **kwargs)

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"

# The four sites, as the report names them.
SITE_VAS = (0x34521F, 0x34525F, 0x3452CF, 0x34530F)


class ShapeTests(unittest.TestCase):
    def test_the_four_spans_are_the_documented_sites_and_keep_their_lengths(self) -> None:
        sites = elbow.sites()
        self.assertEqual(tuple(va for _label, va, _b, _a in sites), SITE_VAS)
        self.assertEqual([label for label, _va, _b, _a in sites],
                         ["left_elbow_next", "left_elbow_prev", "right_elbow_next", "right_elbow_prev"])
        for label, _va, before, after in sites:
            self.assertEqual(len(before), len(after), label)
            self.assertNotEqual(before, after, label)

    def test_only_the_cap_and_the_wrap_target_move_and_it_is_eight_bytes(self) -> None:
        changed = sum(sum(x != y for x, y in zip(before, after))
                      for _label, _va, before, after in elbow.sites())
        self.assertEqual(changed, 8)
        # forward: cmp dl, 9 -> cmp dl, 15
        for retail, patched in ((elbow.LEFT_NEXT_RETAIL, elbow.LEFT_NEXT_PATCHED),
                                (elbow.RIGHT_NEXT_RETAIL, elbow.RIGHT_NEXT_PATCHED)):
            self.assertEqual(retail[0x0B:0x0D], b"\x80\xfa")          # cmp dl, imm8
            self.assertEqual(retail[0x0D], elbow.RETAIL_LAST_INDEX)
            self.assertEqual(patched[0x0D], elbow.PATCHED_LAST_INDEX)
            self.assertEqual(retail[:0x0D], patched[:0x0D])
            self.assertEqual(retail[0x0E:], patched[0x0E:])
        # backward: the and/or pair writes 9 in retail and 15 after the patch
        for retail, patched, mask in ((elbow.LEFT_PREV_RETAIL, elbow.LEFT_PREV_PATCHED, elbow.LEFT_FIELD_MASK),
                                      (elbow.RIGHT_PREV_RETAIL, elbow.RIGHT_PREV_PATCHED, elbow.RIGHT_FIELD_MASK)):
            self.assertEqual(elbow.wrap_target(retail, mask), elbow.RETAIL_LAST_INDEX)
            self.assertEqual(elbow.wrap_target(patched, mask), elbow.PATCHED_LAST_INDEX)

    def test_the_two_fields_are_four_bits_each_and_do_not_overlap(self) -> None:
        for mask in (elbow.LEFT_FIELD_MASK, elbow.RIGHT_FIELD_MASK):
            self.assertEqual(bin(mask).count("1"), 4)
        self.assertEqual(elbow.LEFT_FIELD_MASK & elbow.RIGHT_FIELD_MASK, 0)
        # the patched range has to fit the field the handlers write
        self.assertEqual(elbow.PATCHED_LAST_INDEX, 0xF)
        self.assertEqual(elbow.OPTION_COUNT, len(rr.ELBOWS))

    def test_revert_is_the_exact_inverse_of_apply(self) -> None:
        forward = elbow.sites()
        backward = elbow.revert_sites()
        self.assertEqual([(label, va, after, before) for label, va, before, after in forward], backward)

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(elbow.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(rdata.RdataSiteError):
            rdata.offset_of(b"XBEH" + b"\0" * 0x200, elbow.LEFT_NEXT_VA)


class SyntheticTests(unittest.TestCase):
    """No game bytes beyond the four pinned spans: a fabricated 22-section image."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.image = _build_synthetic_xbe()

    def test_status_apply_revert_round_trip(self) -> None:
        self.assertEqual(elbow.status(self.image), "retail")
        patched, receipt = elbow.apply(self.image)
        self.assertEqual(elbow.status(patched), "applied")
        self.assertTrue(receipt["experimental"])
        self.assertFalse(receipt["witnessed"])
        self.assertEqual(receipt["option_count"], 16)
        self.assertEqual([edit["label"] for edit in receipt["edits"]],
                         ["left_elbow_next", "left_elbow_prev", "right_elbow_next", "right_elbow_prev"])
        again, second = elbow.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(second["already_applied"])
        reverted, revert_receipt = elbow.revert(patched)
        self.assertEqual(reverted, self.image)
        self.assertTrue(revert_receipt["reverted"])
        self.assertEqual(elbow.revert(self.image)[0], self.image)

    def test_the_touched_section_digest_is_recomputed(self) -> None:
        patched, _receipt = elbow.apply(self.image)
        seeded = [s for s in _sections(patched) if s.raw_size]
        self.assertTrue(seeded)
        for section in seeded:
            offset = section.header_offset + 36
            self.assertEqual(patched[offset: offset + 20], section_digest(patched, section), section.index)

    def test_a_tampered_site_is_foreign_and_apply_refuses_it(self) -> None:
        for _label, va, _before, _after in elbow.sites():
            tampered = bytearray(self.image)
            tampered[rdata.offset_of(self.image, va)] ^= 0x01
            self.assertEqual(elbow.status(bytes(tampered)), "foreign")
            with self.assertRaises(elbow.ElbowOptionsError):
                elbow.apply(bytes(tampered))

    def test_the_patch_lands_through_the_build_dispatcher_in_any_order(self) -> None:
        alone, _receipt = tt._apply_all(self.image, None, catch_slider=False, elbow_options=True)
        self.assertEqual(elbow.status(alone), "applied")
        with_others, _a = tt._apply_all(self.image, None, catch_slider=False,
                                        elbow_options=True, team_column=True)
        others_first, _b = tt._apply_all(self.image, None, catch_slider=False,
                                         team_column=True, elbow_options=True)
        self.assertEqual(with_others, others_first)
        self.assertEqual(elbow.status(with_others), "applied")

    def test_off_leaves_the_handlers_alone(self) -> None:
        untouched, _receipt = tt._apply_all(self.image, None, catch_slider=False, team_column=True)
        self.assertEqual(elbow.status(untouched), "retail")


class WiringTests(unittest.TestCase):
    @staticmethod
    def _plan(**kwargs) -> mod_build.BuildPlan:
        return mod_build.BuildPlan(source=Path("default.xbe"), target=Path("out.xbe"), **kwargs)

    def test_the_option_is_off_by_default_and_asks_for_an_xbe_patch_when_on(self) -> None:
        self.assertFalse(self._plan().elbow_options)
        self.assertFalse(self._plan().wants_xbe_patch())
        self.assertTrue(self._plan(elbow_options=True).wants_xbe_patch())

    def test_no_preset_turns_it_on(self) -> None:
        for name in mod_build.PRESETS:
            self.assertFalse(mod_build.apply_preset(self._plan(), name).elbow_options, name)

    def test_the_release_lists_carry_the_module(self) -> None:
        allowlist = (REPO / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split("\n")
        self.assertIn("mod_editor/core/nfl2k5_elbow_options.py", allowlist)
        runtime = (REPO / "packaging" / "check_2k5_mod_studio_runtime.py").read_text(encoding="utf-8")
        self.assertIn("mod_editor.core.nfl2k5_elbow_options", runtime)

    def test_the_inspector_reports_the_site_state(self) -> None:
        image = _build_synthetic_xbe()
        patched, _receipt = elbow.apply(image)
        for payload, expected in ((image, "retail"), (patched, "applied")):
            self.assertEqual(elbow.status(payload), expected)

    def test_the_help_text_says_experimental_and_names_the_missing_pads(self) -> None:
        self.assertIn("EXPERIMENTAL", elbow.HELP_TEXT)
        for pad in ("White Turf", "Black Turf", "Taped", "High White", "High Black", "High Team"):
            self.assertIn(pad, elbow.HELP_TEXT)
            self.assertIn(pad, rr.ELBOWS)


@unittest.skipUnless(XBE.is_file(), "private retail executable unavailable")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()

    def _u32(self, va: int) -> int:
        return struct.unpack_from("<I", self.retail, rdata.offset_of(self.retail, va))[0]

    def test_the_executable_carries_the_retail_handlers(self) -> None:
        self.assertEqual(elbow.status(self.retail), "retail")

    def test_apply_then_revert_is_byte_identical(self) -> None:
        patched, receipt = elbow.apply(self.retail)
        self.assertEqual(elbow.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0])       # .text only
        self.assertEqual(elbow.revert(patched)[0], self.retail)

    def test_both_edit_player_descriptors_own_the_patched_handlers(self) -> None:
        for descriptor, getter, next_fn, prev_fn in (
                (elbow.LEFT_DESCRIPTOR_VA, 0x3451F0, 0x345210, 0x345250),
                (elbow.RIGHT_DESCRIPTOR_VA, 0x3452A0, 0x3452C0, 0x345300)):
            self.assertEqual(self._u32(descriptor + 0x08), getter)
            self.assertEqual(self._u32(descriptor + 0x20), next_fn)
            self.assertEqual(self._u32(descriptor + 0x38), prev_fn)
            # every patched span sits inside the handler the descriptor names
            for _label, va, before, _after in elbow.sites():
                if next_fn <= va < next_fn + 0x40 or prev_fn <= va < prev_fn + 0x40:
                    off = rdata.offset_of(self.retail, va)
                    self.assertEqual(self.retail[off: off + len(before)], before)

    def test_all_three_row_lists_share_the_two_descriptors(self) -> None:
        for list_va in elbow.ROW_LIST_VAS:
            words = {self._u32(list_va + i * 4) for i in range(0x18)}
            self.assertIn(elbow.LEFT_DESCRIPTOR_VA, words, hex(list_va))
            self.assertIn(elbow.RIGHT_DESCRIPTOR_VA, words, hex(list_va))

    def test_the_option_list_has_sixteen_labels_in_the_studio_order(self) -> None:
        def label(va: int) -> str:
            off = rdata.offset_of(self.retail, va)
            end = off
            while True:
                end = self.retail.find(b"\0\0", end)
                if (end - off) % 2 == 0:
                    break
                end += 1
            return self.retail[off:end].decode("utf-16le")

        names = tuple(label(self._u32(elbow.OPTION_LIST_VA + i * 4)) for i in range(16))
        self.assertEqual(names, rr.ELBOWS)

    def test_elbow_pads_are_the_only_slot_the_game_cannot_cycle_fully(self) -> None:
        # (next handler, cap immediate offset inside it, list length): every other row's
        # cap is already len(list) - 1, which is why this patch is elbows only.
        slots = {"left_glove": (0x345E20, len(rr.GLOVES)), "right_glove": (0x345ED0, len(rr.GLOVES)),
                 "left_wrist": (0x3450B0, len(rr.WRISTS)), "right_wrist": (0x345160, len(rr.WRISTS)),
                 "sleeves": (0x345F80, len(rr.SLEEVES)), "turtleneck": (0x3460B0, len(rr.TURTLENECKS)),
                 "neck_roll": (0x346010, len(rr.NECK_ROLLS)), "face_shield": (0x345B80, len(rr.FACE_SHIELDS)),
                 "face_mask": (0x345AD0, len(rr.FACE_MASKS))}
        for name, (handler, count) in slots.items():
            off = rdata.offset_of(self.retail, handler)
            body = self.retail[off: off + 0x40]
            index = body.find(b"\x80\xfa")                # cmp dl, imm8
            self.assertGreater(index, 0, name)
            self.assertEqual(body[index + 2], count - 1, name)
        for handler in (0x345210, 0x3452C0):
            off = rdata.offset_of(self.retail, handler)
            body = self.retail[off: off + 0x40]
            index = body.find(b"\x80\xfa")
            self.assertEqual(body[index + 2], elbow.RETAIL_LAST_INDEX)
            self.assertLess(body[index + 2], len(rr.ELBOWS) - 1)

    def test_the_patched_handlers_reach_every_index_and_nothing_else_moves(self) -> None:
        patched, _receipt = elbow.apply(self.retail)
        differing = [i for i, (a, b) in enumerate(zip(self.retail, patched)) if a != b]
        text_edits = [i for i in differing if any(rdata.offset_of(self.retail, va) <= i
                                                  < rdata.offset_of(self.retail, va) + len(before)
                                                  for _l, va, before, _a in elbow.sites())]
        self.assertEqual(len(text_edits), 8)
        self.assertEqual(len(differing), 8 + 20)          # the eight bytes plus one section digest
        for handler in (0x345210, 0x3452C0):
            off = rdata.offset_of(patched, handler)
            body = patched[off: off + 0x40]
            self.assertEqual(body[body.find(b"\x80\xfa") + 2], elbow.PATCHED_LAST_INDEX)


if __name__ == "__main__":
    unittest.main()

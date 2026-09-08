"""7-on-7 v2: huddle geometry, exact replay, rollback and every owner pair.

Standalone unittest. Reads only the pinned 12 MB USA XBE and 78,768-byte
practice resource. No disc copy, whole archive read, or game boot is needed.
"""
from __future__ import annotations

import hashlib
import itertools
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_seven_on_seven as seven
from mod_editor.core import nfl2k5_seven_on_seven_book as book
from mod_editor.core import nfl2k5_depth_roles as roles
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_throw_tuning as tuning
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests import nfl2k5_allocator_stack as stack
from tests.mod_editor import test_nfl2k5_owner_pairwise_composition as pairs
from tests.mod_editor import test_nfl2k5_seven_on_seven as original


def repin(payload, va, content):
    buf = bytearray(payload)
    at = XbeImage(payload).offset(va, len(content))
    buf[at:at + len(content)] = content
    for section in _sections(buf):
        at = section.header_offset + 36
        buf[at:at + 20] = section_digest(buf, section)
    return bytes(buf)


class ExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = pairs.retail_xbe()
        cls.patched, _ = seven.apply(cls.retail)

    def test_every_site_refuses_partial_install_and_foreign_byte_before_repin(self):
        for label, va, before, after in seven.sites():
            for payload, replacement in ((self.retail, after), (self.patched, before),
                                         (self.patched, bytes([after[0] ^ 1]) + after[1:])):
                with self.subTest(site=label, installed=payload is self.patched):
                    bad = bytearray(repin(payload, va, replacement))
                    saved = bytes(bad)
                    self.assertEqual(seven.status(bad), "foreign")
                    # No section rewrite or repin may happen on a refusal.
                    with mock.patch.object(seven, "_section_for_offset", side_effect=AssertionError("mutation")):
                        with self.assertRaises(seven.SevenOnSevenError):
                            seven.apply(bad)
                    self.assertEqual(bytes(bad), saved)

    def test_stale_section_digest_and_v1_rush_hooks_refuse(self):
        bad = bytearray(self.patched)
        bad[_sections(bad)[0].header_offset + 36] ^= 1
        self.assertEqual(seven.status(bad), "foreign")
        for va, before in seven.RETAIL_RUSH_READS:
            self.assertEqual(XbeImage(self.patched).read(va, len(before)), before)
            bad = repin(self.patched, va, b"\xe8" + bytes(len(before) - 1))
            self.assertEqual(seven.status(bad), "foreign")
            with self.assertRaises(seven.SevenOnSevenError):
                seven.apply(bad)

    def test_existing_reservations_and_zero_new_budget(self):
        self.assertEqual(seven.REQUESTS, ())
        self.assertEqual(seven.CAVE_VA + seven.CAVE_SIZE, 0x1AC260)
        self.assertEqual(XbeImage(self.patched).read(0x1AC260, 64),
                         XbeImage(self.retail).read(0x1AC260, 64))
        self.assertTrue(XbeImage(self.patched).runtime_writable(seven.FLAG_VA, 1))
        self.assertFalse(XbeImage(self.patched).runtime_writable(seven.CAVE_VA, seven.CAVE_SIZE))

    def test_allocator_before_and_after_are_identical(self):
        for requests in ((), stack.LEGACY_REQUESTS, stack.REQUESTS):
            with self.subTest(requests=len(requests)):
                a = stack.space.apply(self.patched, requests)[0]
                b = seven.apply(stack.space.apply(self.retail, requests)[0])[0]
                self.assertEqual(a, b)
                self.assertEqual(seven.apply(a)[0], a)
                self.assertEqual(stack.space.apply(a, requests)[0], a)

    def test_native_hash_constants_and_old_out_of_bounds_regression(self):
        image = XbeImage(self.retail)
        left, right = (struct.unpack("<f", image.read(va, 4))[0] for va in (0x4F0F40, 0x4F0F3C))
        self.assertAlmostEqual(left, -281.94, places=3)
        self.assertAlmostEqual(right, 281.94, places=3)
        self.assertGreater(2300 + right, 2438.4)
        self.assertLess(-2300 + left, -2438.4)
        for name, _, _, positions, _ in book.FORMATIONS:
            for ball_x, direction, (x, z) in itertools.product((left, 0, right), (-1, 1), positions):
                with self.subTest(formation=name, ball_x=ball_x, direction=direction, x=x, z=z):
                    self.assertLess(abs(ball_x + direction * x), 2438.4)


class EveryOwnerPairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = pairs.retail_xbe()
        cls.legacy_seed = pairs.prerequisites(retail)
        seed = stack.policy.apply(cls.legacy_seed, music_unlock=True, music_userlist=True)[0]
        cls.seed = stack.space.apply(seed, stack.REQUESTS, scaleout=True)[0]

    def check_pair(self, owner, kwargs, *, legacy=False):
        seed = self.legacy_seed if legacy else self.seed
        if owner in (tuning.position_pools_patch, tuning.depth_chart_rows_patch):
            seed = tuning.scheme_labels_patch.apply(seed)[0]
        if owner is tuning.depth_chart_rows_patch:
            seed = tuning.position_pools_patch.apply(seed)[0]
        a = owner.apply(seven.apply(seed)[0], **kwargs)[0]
        b = seven.apply(owner.apply(seed, **kwargs)[0])[0]
        self.assertEqual(a, b, getattr(owner, "OWNER", owner.__name__))
        self.assertEqual(seven.status(a), "applied")
        self.assertEqual(seven.apply(a)[0], a)
        self.assertEqual(owner.status(a), "applied")
        # Several legacy owners deliberately reject direct apply on replay;
        # the dispatcher handles their already-applied result by status.
        if not legacy:
            self.assertEqual(owner.apply(a, **kwargs)[0], a)


def grown_pair(owner, kwargs):
    def test(self):
        self.check_pair(owner, kwargs)
    return test


for _owner, _kwargs in stack.owner_calls(read_option_diagnostic=True):
    if _owner is not seven:
        setattr(EveryOwnerPairTests, "test_" + _owner.OWNER, grown_pair(_owner, _kwargs))

# Legacy dispatcher owners also run individually against 7-on-7. Keep the
# prerequisites required by the already shipped practice/row owners.
for _name in ("catch_slider_patch", "accel_ramp_patch", "draft_ai_patch", "returner_fix_patch",
              "progression_patch", "scheme_labels_patch", "widescreen_patch", "modern_naming_patch",
              "overtime_patch", "team_column_patch", "position_row_patch", "probowl_order_patch",
              "edge_rename_patch", "kick_rules_patch", "dynamic_kickoff_patch", "uniform_choice_patch",
              "flatter_flight_patch", "position_pools_patch", "practice_reserves_patch", "depth_chart_rows_patch",
              "kick_laces_patch", "franchise_practice_patch", "player_star_patch",
              "practice_squad_patch", "depth_locks_patch", "season_cap_patch"):
    _module = getattr(tuning, _name)
    def _test(self, owner=_module):
        self.check_pair(owner, {}, legacy=True)
    setattr(EveryOwnerPairTests, "test_legacy_" + _name, _test)


class BookRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import nfl2k5_playbook_position_recode as recode
        packs = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/vc_53450030"
        if not (packs / "0").is_file():
            raise unittest.SkipTest("private extracted USA archive index is absent")
        with recode.OuterImage(packs) as archive:
            cls.entry = archive.entries[book.PRACTICE_OUTER_INDEX]
            cls.retail = archive.read_entry(book.PRACTICE_OUTER_INDEX)
        if hashlib.sha256(cls.retail).hexdigest() != book.RETAIL_RESOURCE_SHA256:
            raise unittest.SkipTest("practice resource differs from the USA evidence pin")
        cls.built = book.build_replacement(cls.retail)[0]
        cls.recode = recode

    def pool(self, raw):
        parsed = self.recode.parse_book("PRACTICE", self.entry, raw)
        table, _ = self.recode.recoded_table(parsed)
        at = 32 + self.recode.CATEGORY_BASE
        return raw[:at] + table + raw[at + len(table):]

    def test_all_six_writer_orders_and_all_four_exact_replays(self):
        ops = {"seven": lambda raw: book.build_replacement(raw)[0], "pools": self.pool,
               "roles": lambda raw: roles.normalise(raw).replacement}
        results = set()
        for order in itertools.permutations(ops):
            raw = self.retail
            for key in order:
                raw = ops[key](raw)
            with self.subTest(order=order):
                self.assertEqual(book.resource_status(raw), "applied")
                self.assertEqual(book.build_replacement(raw)[0], raw)
                results.add(hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(results), 1)
        for pooling, depth in itertools.product((False, True), repeat=2):
            raw = self.pool(self.retail) if pooling else self.retail
            raw = roles.normalise(raw).replacement if depth else raw
            self.assertIn(hashlib.sha256(raw).hexdigest(), book.KNOWN_SOURCE_STATES)
            built, receipt = book.build_replacement(raw)
            self.assertIn(hashlib.sha256(built).hexdigest(), book.APPLIED_RESOURCE_STATES)
            self.assertEqual(book.build_replacement(built)[1]["changed_byte_count"], 0)
            self.assertEqual(receipt["changed_byte_count"], sum(a != b for a, b in zip(raw, built)))

    def test_foreign_padding_header_route_and_link_refuse_before_writing(self):
        # These formerly passed structural verify despite changing valid bytes.
        for at in (0x14, len(self.built) - 1, 32 + book.PLAY_BASE + 27 * book.PLAY_SIZE + 5,
                   32 + book.FORMATION_AUX_BASE + 23 * book.FORMATION_AUX_SIZE):
            with self.subTest(offset=hex(at)):
                changed = bytearray(self.built)
                changed[at] ^= 1
                saved = bytes(changed)
                self.assertEqual(book.resource_status(saved), "foreign")
                with self.assertRaises(ValueError):
                    book.build_replacement(saved)
                original._FakeArchive.store = changed
                with mock.patch.object(book, "_outer_image", return_value=original._FakeArchive), \
                     mock.patch.object(original._FakeArchive, "write", side_effect=AssertionError("write before refusal")):
                    with self.assertRaises(book.SevenOnSevenBookError):
                        book.apply("fake.iso")
                self.assertEqual(bytes(changed), saved)

    def test_original_drill_assignments_and_formation_geometry_survive(self):
        before, after = self.retail[32:], self.built[32:]
        for index in range(book.RETAIL_PLAYS):
            original_flags, original_chains = lib.play_chains(before, index)
            flags, chains = lib.play_chains(after, index)
            self.assertEqual(flags, original_flags | book.AI_EXCLUDED)
            self.assertEqual(chains, original_chains, index)
        for index in range(book.RETAIL_FORMATIONS):
            self.assertEqual(lib.formation_record(after, index), lib.formation_record(before, index))

    def test_failed_write_and_readback_restore_the_complete_resource(self):
        for failure in ("short", "readback", "raise"):
            with self.subTest(failure=failure):
                class FailingArchive(original._FakeArchive):
                    writes = 0
                    def write(self, offset, data):
                        self.writes += 1
                        if self.writes == 1:
                            if failure == "short":
                                return super().write(offset, data[:13])
                            super().write(offset, data)
                            if failure == "raise":
                                raise OSError("injected write failure")
                            self.store[0x14] ^= 1
                            return len(data)
                        return super().write(offset, data)
                FailingArchive.store = bytearray(self.retail)
                with mock.patch.object(book, "_outer_image", return_value=FailingArchive):
                    with self.assertRaises((book.SevenOnSevenBookError, OSError)):
                        book.apply("fake.iso")
                self.assertEqual(bytes(FailingArchive.store), self.retail)


if __name__ == "__main__":
    unittest.main()

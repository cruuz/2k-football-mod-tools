"""Standalone pair matrix and strict screen-guard composition regressions.

Only the bounded USA default.xbe is read. Each pair starts with the complete
gate request union reserved and the legacy Practice Squad prerequisites; no
other matrix owner is installed. Both orders must retain both statuses and
exact replay, and produce the same bytes. No console or disc build is used.
"""
from pathlib import Path
import hashlib
import itertools
import os
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests import nfl2k5_allocator_stack as stack
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_music_playlist as playlist
from mod_editor.core import nfl2k5_practice_squad_screen as screen
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_franchise_practice as fp
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
# The ten integration owners requested in the brief, plus both screen partners.
# QB spy includes the landed man/rush hooks; Read option v5 retains its existing reservation.
OWNERS = (
    ("playbook_pair", stack.playbook_pair),
    ("helmet_finish", stack.helmet_finish),
    ("accelerated_clock_on_20", stack.AcceleratedClockOn),
    ("seven_on_seven_v2", stack.seven),
    ("camera_v5", stack.camera),
    ("abilities_v2", stack.abilities),
    ("momentum", stack.momentum),
    ("screen_hooks", stack.screen_hooks),
    ("read_option_v5", stack.read_option),
    ("qb_spy_man_rush", stack.qb_spy),
    ("franchise_2026", stack.franchise_2026),
    ("senior_bowl", stack.senior_bowl),
    ("animation_xbe", stack.animation_xbe),
    ("guardian_overlay", stack.guardian),
    ("my_career", career),
    ("crib_reclaim", stack.crib_reclaim),
    ("calendar", stack.calendar),
    ("music_playlist", playlist),
    ("practice_squad_screen", screen),
    ("my_career_generic", stack.my_career),
    ("franchise_autosave", stack.autosave),
    ("coverage_trail", stack.coverage_trail),
    ("deep_zone", stack.deep_zone),
    ("zone_drop", stack.zone_drop),
    ("scorebug_runtime", stack.runtime),
    ("static_scorebar_v3", stack.StaticScorebar),
    ("cpu_money_downs", stack.money_downs),
    ("franchise_edit_player", stack.edit_player),
)


def retail_xbe():
    if not XBE.is_file():
        raise unittest.SkipTest("pinned USA retail default.xbe is absent")
    if XBE.stat().st_size > 16 * 1024**2:
        raise AssertionError("expected a bounded XBE, not a disc or archive pack")
    with XBE.open("rb") as stream:
        payload = stream.read(16 * 1024**2 + 1)
    if hashlib.sha256(payload).hexdigest() != RETAIL_SHA256:
        raise unittest.SkipTest("retail XBE does not match the USA evidence pin")
    return payload


def prerequisites(payload):
    for owner in (ps, fp, pr):
        payload, _ = owner.apply(payload)
    return payload


def repin_edit(payload, va, content):
    """Corrupt native bytes while keeping section digests valid."""
    result = bytearray(payload)
    offset = XbeImage(payload).offset(va, len(content))
    result[offset:offset + len(content)] = content
    for section in _sections(result):
        result[section.header_offset + 36:section.header_offset + 56] = section_digest(result, section)
    return bytes(result)


class PairwiseCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed, _ = space.apply(prerequisites(retail_xbe()), stack.REQUESTS, scaleout=True)

    def check_pair(self, left, right):
        digests = []
        for order in ((left, right), (right, left)):
            with self.subTest(order=" -> ".join(owner.OWNER for owner in order)):
                result = self.seed
                for owner in order:
                    result, _ = owner.apply(result)
                for owner in (left, right):
                    self.assertEqual(owner.status(result), "applied", owner.OWNER)
                    replay, receipt = owner.apply(result)
                    self.assertEqual(replay, result, owner.OWNER)
                    if owner is stack.StaticScorebar:
                        self.assertEqual(receipt["state_before"], "applied", owner.OWNER)
                    else:
                        self.assertEqual(receipt["changed_bytes"], 0, owner.OWNER)
                self.assertEqual(space.apply(result, stack.REQUESTS, scaleout=True)[0], result)
                digests.append(hashlib.sha256(result).digest())
        if len(digests) == 2:
            self.assertEqual(digests[0], digests[1], "installation order changed the pair output")


def pair_test(left, right):
    def test(self):
        self.check_pair(left, right)
    return test


for (left_name, left), (right_name, right) in itertools.combinations(OWNERS, 2):
    if left.OWNER == right.OWNER:  # mutually exclusive legacy/generic formats
        continue
    setattr(PairwiseCompositionTests, f"test_{left_name}__{right_name}", pair_test(left, right))


class RefusalAssertions(unittest.TestCase):
    def assert_refused(self, payload, owners=(playlist, screen)):
        before = hashlib.sha256(payload).digest()
        for owner in owners:
            with self.subTest(owner=owner.__name__):
                self.assertEqual(owner.status(payload), "foreign")
                # Rejection must happen before either allocator install writer.
                with mock.patch.object(space, "install_code", side_effect=AssertionError("write before refusal")), \
                     mock.patch.object(space, "install_read_only", side_effect=AssertionError("write before refusal")):
                    with self.assertRaises(ValueError):
                        owner.apply(payload)
        self.assertEqual(hashlib.sha256(payload).digest(), before)


class MyCareerScreenGuardTests(RefusalAssertions):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.requests = career.REQUESTS + playlist.REQUESTS + screen.REQUESTS
        cls.seed, _ = space.apply(prerequisites(cls.retail), cls.requests, scaleout=True)
        # Exercise a nonzero, validated MyPlayer setup and nondefault playlist.
        from tests.nfl2k5_my_career_fixture import prepared
        cls.setup = prepared()[1]
        cls.selection = playlist.Selection((("femusic", 2), ("cribmusic", 4)), (1,))
        cls.patched = cls.seed
        for owner, options in ((career, dict(setup=cls.setup)),
                               (playlist, dict(selection=cls.selection)), (screen, {})):
            cls.patched, _ = owner.apply(cls.patched, **options)

    def test_actual_overlap_is_playlist_push_guard_only(self):
        edits = career.sites(0, 0)

        def overlaps(guards):
            return [(name, va) for va, size, *_ in guards for name, hook, before, _ in edits
                    if hook < va + size and va < hook + len(before)]

        self.assertEqual(overlaps(playlist.GUARDS), [("screen_dispatch", 0x6E390)])
        self.assertEqual(overlaps(screen.GUARDS), [])
        self.assertEqual(overlaps(screen.TEMPLATES.values()), [])
        self.assertEqual(overlaps((va, len(before)) for va, before in fp.PINS),
                         [("screen_dispatch", 0x6E390)])
        # No shared hook writes in either direction: PUSH and EVENT are distinct.
        self.assertEqual(overlaps((va, len(before)) for va, before in playlist.HOOKS.values()), [])

    def test_all_six_orders_replay_configured_owners_at_another_union_address(self):
        options = {career: dict(setup=self.setup), playlist: dict(selection=self.selection), screen: {}}
        expected = hashlib.sha256(self.patched).digest()
        for order in itertools.permutations((career, playlist, screen)):
            with self.subTest(order=" -> ".join(owner.OWNER for owner in order)):
                result = self.seed
                for owner in order:
                    result, _ = owner.apply(result, **options[owner])
                for owner in (career, playlist, screen, ps, fp, pr):
                    self.assertEqual(owner.status(result), "applied", owner.__name__)
                    self.assertEqual(owner.apply(result, **options.get(owner, {}))[0], result)
                self.assertEqual(self.selection.status(result), "applied")
                self.assertEqual(career.installed_setup(result), career.read_setup(self.setup))
                self.assertEqual(hashlib.sha256(result).digest(), expected)
        full_layout = space.plan(stack.REQUESTS, scaleout=True)
        full_code = next(a for a in full_layout["allocations"]
                         if a["owner"] == career.OWNER and a["kind"] == "code")
        self.assertNotEqual(career.allocations(self.patched)[0]["va"], full_code["va"])

    def test_every_partner_hook_byte_and_guard_tail_remain_pinned(self):
        image = XbeImage(self.patched)
        for va in (*range(0x6E390, 0x6E39A), 0x6E39A, 0x6E3F2):
            with self.subTest(va=hex(va)):
                bad = repin_edit(self.patched, va, bytes([image.read(va, 1)[0] ^ 1]))
                self.assertEqual(space.status(bad), "applied")
                self.assert_refused(bad)

    def test_exact_jump_without_complete_partner_installation_refuses(self):
        code, data = career.allocations(self.seed)
        _, labels = career.code_for(code["va"], data["va"])
        hook = career.branch(0x6E390, labels["screen_dispatch"], 10)
        # Correct destination and NOPs, but the owner allocation is empty.
        bad = repin_edit(self.seed, 0x6E390, hook)
        self.assertEqual(space.status(bad), "applied")
        self.assert_refused(bad, (career, playlist))
        # Exact PUSH remains, but another MyCareer hook has been reverted.
        _, va, original, _ = career.sites(code["va"], data["va"])[0]
        self.assert_refused(repin_edit(self.patched, va, original), (career, playlist, screen))

    def test_partner_code_setup_and_state_cannot_be_blessed_by_resealing(self):
        code, data = career.allocations(self.patched)
        original = XbeImage(self.patched).read(code["va"], code["size"])
        partner_base = screen.apply(playlist.apply(self.seed, selection=self.selection)[0])[0]
        for offset in (0, len(career.assembly.CODE), code["size"] - 1):
            with self.subTest(code_offset=offset):
                content = bytearray(original)
                content[offset] ^= 1
                # Fill a fresh allocation so both its SHA-256 seal and section
                # digests certify these bytes, then install the exact detours.
                bad, _ = space.install_code(partner_base, career.OWNER, bytes(content))
                bad, _ = career.rdata.apply(bad, career.sites(code["va"], data["va"]), career.OWNER)
                self.assertEqual(space.status(bad), "applied")
                self.assert_refused(bad, (career, playlist, screen))
        bad = repin_edit(self.patched, data["va"], b"\x01")
        self.assertEqual(space.status(bad), "foreign")  # allocator also requires zero initial RW
        self.assert_refused(bad, (career, playlist, screen))

    def test_practice_squad_still_pins_its_own_native_tail_and_templates(self):
        for va in (0x6E4E5, *(va for va, _ in screen.TEMPLATES.values())):
            with self.subTest(va=hex(va)):
                original = XbeImage(self.patched).read(va, 1)
                self.assert_refused(repin_edit(self.patched, va, bytes([original[0] ^ 1])), (screen,))

    def test_franchise_practice_accepts_push_in_both_orders(self):
        seed = ps.apply(self.retail)[0]
        results = []
        for order in ((career, fp), (fp, career)):
            with self.subTest(order=" -> ".join(owner.__name__ for owner in order)):
                result = seed
                for owner in order:
                    result, _ = owner.apply(result)
                for owner in order:
                    self.assertEqual(owner.status(result), "applied")
                    self.assertEqual(owner.apply(result)[0], result)
                results.append(hashlib.sha256(result).digest())
        self.assertEqual(results[0], results[1])
        for va in (0x6E391, 0x6E399, 0x6E39A, 0x6E3F2):
            value = XbeImage(self.patched).read(va, 1)[0] ^ 1
            self.assert_refused(repin_edit(self.patched, va, bytes([value])), (fp,))


class QbInitializerGuardTests(RefusalAssertions):
    @classmethod
    def setUpClass(cls):
        cls.owners = (stack.screen_hooks, stack.read_option)
        cls.seed, _ = space.apply(retail_xbe(), sum((owner.REQUESTS for owner in cls.owners), ()), scaleout=True)
        cls.patched = cls.seed
        for owner in cls.owners:
            cls.patched, _ = owner.apply(cls.patched)

    def test_every_shared_routine_hook_byte_and_native_tail_remain_pinned(self):
        image = XbeImage(self.patched)
        for va in (*range(0x19C7E9, 0x19C7F0), *range(0x19C849, 0x19C84F), 0x19C7F0, 0x19C84F):
            with self.subTest(va=hex(va)):
                bad = repin_edit(self.patched, va, bytes([image.read(va, 1)[0] ^ 1]))
                self.assertEqual(space.status(bad), "applied")
                self.assert_refused(bad, self.owners)

    def test_complete_partner_context_is_checked_without_recursion(self):
        # Nonshared dependencies must also be checked by the delegating owner.
        for va in (0x23E550, 0xF97F0):
            value = XbeImage(self.patched).read(va, 1)[0] ^ 1
            self.assert_refused(repin_edit(self.patched, va, bytes([value])), self.owners)

    def test_exact_hooks_without_partner_code_or_with_another_hook_reverted_refuse(self):
        image = XbeImage(self.patched)
        for owner, name in ((stack.screen_hooks, "qb"), (stack.read_option, "pass_init")):
            va, before = owner.HOOKS[name]
            bad = repin_edit(self.seed, va, image.read(va, len(before)))
            self.assertEqual(space.status(bad), "applied")
            self.assert_refused(bad, self.owners)
        for owner, name in ((stack.screen_hooks, "block"), (stack.read_option, "tick")):
            va, before = owner.HOOKS[name]
            self.assert_refused(repin_edit(self.patched, va, before), self.owners)

    def test_resealed_partner_code_and_state_refuse(self):
        image = XbeImage(self.patched)
        for owner, other in (self.owners, tuple(reversed(self.owners))):
            code = next(a for a in space.layout(self.seed)["allocations"]
                        if a["owner"] == owner.OWNER and a["kind"] == "code")
            content = bytearray(image.read(code["va"], code["size"]))
            content[0] ^= 1
            bad, _ = other.apply(self.seed)
            bad, _ = space.install_code(bad, owner.OWNER, bytes(content))
            if owner is stack.read_option:
                ro = stack.read_option.allocations(bad)["read_only"]
                bad, _ = space.install_read_only(bad, owner.OWNER, image.read(ro["va"], ro["size"]))
            for va, before in owner.HOOKS.values():
                bad = repin_edit(bad, va, image.read(va, len(before)))
            self.assertEqual(space.status(bad), "applied")
            self.assert_refused(bad, self.owners)
        data = stack.read_option.allocations(self.patched)["data"]
        self.assert_refused(repin_edit(self.patched, data["va"], b"\x01"), self.owners)


if __name__ == "__main__":
    unittest.main()

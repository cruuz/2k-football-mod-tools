"""Exact two-owner composition/refusal and bounded native initializer proofs.

The complete request union exercises relocated addresses. The existing two
XBE gates additionally install and replay every owner through stack.compose.
No disc/pack is read wholesale and no game or display is started.
"""
from __future__ import annotations

from contextlib import ExitStack
import gc
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch as mock_patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_read_option_runtime as read
from mod_editor.core import nfl2k5_screen_hooks as screen
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_screen_hooks import retail_xbe, repin
from tests.nfl2k5_allocator_stack import REQUESTS

PAIR = (read, screen)


def install_pair(base, order=PAIR, table=None):
    for owner in order:
        base, _ = owner.apply(base, **({"intent_table": table} if owner is read else {}))
    return base


def change(payload, edits, *, reseal=False):
    """Adversarial bytes with valid digests (and optional forged owner seals)."""
    image = XbeImage(payload)
    bad = bytearray(payload)
    for va, content in edits:
        offset = image.offset(va, len(content))
        bad[offset:offset + len(content)] = content
    if reseal:
        # A valid directory seal alone must never authorize foreign code/RO.
        _, _, requests = space._validate(payload)
        space._seal_scaleout(bad, requests)
    return repin(bad)


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.base, _ = space.apply(cls.retail, REQUESTS, scaleout=True)
        cls.composed = install_pair(cls.base)

    def assert_refused(self, owner, payload):
        with ExitStack() as context:
            for name in ("apply", "install_code", "install_read_only"):
                context.enter_context(mock_patch.object(space, name, side_effect=AssertionError("mutation before refusal")))
            self.assertEqual(owner.status(payload), "foreign")
            self.assertIsNone(owner.read_settings(payload))
            with self.assertRaises(ValueError):
                owner.apply(payload)

    def test_apply_both_orders_replay_and_settings_at_pair_and_union_addresses(self):
        pair_base, _ = space.apply(self.retail, read.REQUESTS + screen.REQUESTS, scaleout=True)
        self.assertNotEqual(read.allocations(pair_base)["code"]["va"], read.allocations(self.base)["code"]["va"])
        self.assertNotEqual(screen.allocation(pair_base)["va"], screen.allocation(self.base)["va"])
        for base in (pair_base, self.base):
            forward = install_pair(base)
            reverse = install_pair(base, tuple(reversed(PAIR)))
            self.assertEqual(forward, reverse)
            for owner in PAIR:
                with self.subTest(owner=owner.OWNER, code=screen.allocation(base)["va"]):
                    self.assertEqual(owner.status(base), "retail")
                    self.assertEqual(owner.status(forward), "applied")
                    replay, receipt = owner.apply(forward)
                    self.assertIs(replay, forward)
                    self.assertEqual((receipt["status"], receipt["changed_bytes"], receipt["edits"]),
                                     ("already_applied", 0, []))
                    self.assertFalse(owner.read_settings(forward)["runtime_witnessed"])
            self.assertEqual(read.read_settings(forward)["model_version"], 2)

    def test_partner_only_and_reserved_uninstalled_partner_are_supported(self):
        for owner, partner in (PAIR, tuple(reversed(PAIR))):
            partner_only = partner.apply(self.retail)[0]
            self.assertEqual(owner.status(partner_only), "retail")
            first = partner.apply(self.base)[0]
            self.assertEqual(owner.status(first), "retail")
            self.assertIs(partner.apply(first)[0], first)
            self.assertEqual(owner.apply(first)[0], self.composed)

    def test_exact_shared_routine_normalization_preserves_every_other_byte(self):
        original, composed = XbeImage(self.retail), XbeImage(self.composed)
        routine = bytearray(composed.read(0x19C740, 275))
        for owner, name in ((read, "pass_init"), (screen, "qb")):
            va, before = owner.HOOKS[name]
            routine[va - 0x19C740:va - 0x19C740 + len(before)] = before
        self.assertEqual(routine, original.read(0x19C740, 275))
        self.assertEqual(space.layout(self.base), space.layout(self.composed))

    def test_foreign_jump_opcode_displacement_padding_and_adjacent_bytes_refuse(self):
        for owner, partner, name in ((read, screen, "qb"), (screen, read, "pass_init")):
            va, before = partner.HOOKS[name]
            for source in (partner.apply(self.base)[0], self.composed):
                image = XbeImage(source)
                # Includes both sides of each exact whole-instruction span.
                for address in (va - 1, *range(va, va + len(before)), va + len(before), 0x19C740):
                    with self.subTest(owner=owner.OWNER, address=hex(address), installed=source is self.composed):
                        bad = change(source, [(address, bytes([image.read(address, 1)[0] ^ 1]))])
                        self.assertEqual(space.status(bad), "applied")
                        self.assert_refused(owner, bad)

    def test_detour_requires_named_allocation_complete_code_and_all_partner_hooks(self):
        for owner, partner, name in ((read, screen, "qb"), (screen, read, "pass_init")):
            partner_va = read.allocations(self.base)["code"]["va"] if partner is read else screen.allocation(self.base)["va"]
            hooks = partner.sites(partner_va)
            shared = next(row for row in hooks if row[0] == name)
            for base in (self.retail, self.base):
                self.assert_refused(owner, change(base, [(shared[1], shared[3])]))
            for hook_name, va, before, _after in hooks:
                if hook_name != name:
                    with self.subTest(owner=owner.OWNER, missing=hook_name):
                        self.assert_refused(owner, change(self.composed, [(va, before)]))
            # Correct shared jump but another allocator placement's destination.
            wrong_jump = b"\xe9" + struct.pack("<i", partner_va + 16 - shared[1] - 5) + b"\x90" * (len(shared[2]) - 5)
            self.assert_refused(owner, change(self.composed, [(shared[1], wrong_jump)]))

    def test_foreign_partner_code_state_table_prompt_and_dependencies_refuse_even_when_sealed(self):
        places = read.allocations(self.composed)
        checks = ((read, [screen.allocation(self.composed)["va"], screen.allocation(self.composed)["va"] + screen.CODE_SIZE - 1, 0x23BE30]),
                  (screen, [places["code"]["va"], places["code"]["va"] + read.CODE_SIZE - 1,
                            places["data"]["va"], places["read_only"]["va"], places["read_only"]["va"] + read.TABLE_SIZE, 0x120960]))
        image = XbeImage(self.composed)
        for owner, addresses in checks:
            for va in addresses:
                with self.subTest(owner=owner.OWNER, address=hex(va)):
                    bad = change(self.composed, [(va, bytes([image.read(va, 1)[0] ^ 1]))], reseal=True)
                    # The allocator separately requires initial RW zeros.
                    expected = "foreign" if va == places["data"]["va"] else "applied"
                    self.assertEqual(space.status(bad), expected)
                    self.assert_refused(owner, bad)

    def test_qb_spy_lifecycle_validation_composes_without_recursive_status(self):
        from mod_editor.core import nfl2k5_qb_spy_runtime as spy
        for order in ((spy, read, screen), (screen, read, spy)):
            result = install_pair(self.base, order)
            for owner in (spy, read, screen):
                self.assertEqual(owner.status(result), "applied")
                self.assertIs(owner.apply(result)[0], result)


class NativeInitializerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_nfl2k5_read_option_controls import uc
        if uc is None:
            raise unittest.SkipTest("Unicorn absent; bounded native initializer proof unavailable")
        cls.base, _ = space.apply(retail_xbe(), REQUESTS, scaleout=True)

    def test_screen_timer_and_ordinary_callback_survive_both_hooks(self):
        from tests.mod_editor.test_nfl2k5_screen_hooks_unicorn import Machine, atl_resource
        resource = atl_resource()
        for order in (PAIR, tuple(reversed(PAIR))):
            payload = install_pair(self.base, order)
            code = read.allocations(payload)["code"]["va"]
            for pi, expected in ((178, .6), (177, 1.0)):
                gc.collect()
                m = Machine(payload, resource, slot=0, pi=pi)
                m.boundary("qb", timer=1, stop_at=0x19C7F0)
                self.assertAlmostEqual(m.readf(m.task + 0x60), expected, places=6)
                m.run(0x19C849, stop_at=0x19C84F, esi=m.task)
                self.assertIn(code + read.assembly.LABELS["pass_init"], m.hits)
                self.assertEqual(m.get(m.task), 0x19BB60)
                self.assertAlmostEqual(m.readf(m.task + 0x60), expected, places=6)

    def test_authored_rpo_runs_both_hooks_through_full_native_initializer(self):
        from tests.mod_editor.test_nfl2k5_read_option_controls import ControlsMachine, shotgun_reads
        _, compiled = shotgun_reads()
        table = read.compile_intent_table([(compiled.replacement, compiled.report)])[0]
        for order in (PAIR, tuple(reversed(PAIR))):
            payload = install_pair(self.base, order, table)
            self.assertIs(read.apply(payload)[0], payload)
            with self.assertRaisesRegex(ValueError, "Different Read option intent"):
                read.apply(payload, intent_table=read.compile_intent_table()[0])
            for ready in (True, False):
                gc.collect()
                m = ControlsMachine(payload, compiled.replacement, controller=0, rpo=True, play_index=31)
                m.frames(1, throw=True)
                m.finish()
                m.ready(ready)
                m.pass_initializer()
                for owner, label, code in ((read, "pass_init", read.allocations(payload)["code"]["va"]),
                                           (screen, "qb", screen.allocation(payload)["va"])):
                    self.assertIn(code + owner.assembly.LABELS[label], m.hits)
                self.assertEqual(m.get(m.task), 0x19BAE0 if ready else 0x19BB60)
                self.assertEqual(m.get(m.state_va + 32), 0)
                if ready:
                    self.assertEqual(m.get(m.task + 0x40), m.OTHER)
                    m.uc.mem_write(0xBDFCD0 + 7 * 2, b"\x01")
                    m.boundaries = {0x198C20: (4, "float")}
                    m.run(m.get(m.task), ecx=m.QB)
                    self.assertEqual(m.get(m.QB + 0x100 + 0x1C), 0x42)


if __name__ == "__main__":
    unittest.main()

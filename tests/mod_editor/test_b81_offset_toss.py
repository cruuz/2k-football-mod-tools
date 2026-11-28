"""Controller dispatch and native exchange placement for Jacksonville's offset pitch."""
import dataclasses
from pathlib import Path
import unittest

from mod_editor.core import nfl2k5_offset_toss as toss, nfl2k5_playbook_lint as lint, nfl2k5_playbook_pack as packs
from tests.nfl2k5_supersim_draft_fixture import XBE, retail_bytes
from tools.b77.p13_handoff_probe import HandoffMachine, snap_time_for
from tools.nfl2k5_back_throws_replay import uc_module, x86

BOOK = Path(__file__).resolve().parents[2] / "data" / "playbooks" / "softdrink_jax_modern.2k5book"


class MenuMachine(HandoffMachine):
    """Retain the registered button handlers and offense dispatcher. Supply the open HUD and capture its queued event."""

    def __init__(self, payload):
        super().__init__(payload)
        self.events = []
        for address in (0xFF120, 0xFEE40, 0x18EB50, 0xA2740):
            self.uc.hook_add(uc_module.UC_HOOK_CODE, self._menu_state, begin=address, end=address)

    def _menu_state(self, uc, address, size, data):
        sp = uc.reg_read(x86.UC_X86_REG_ESP)
        self.uc.reg_write(x86.UC_X86_REG_EAX, 0)
        if address == 0xA2740:
            self.events.append(uc.reg_read(x86.UC_X86_REG_EDX))
        uc.reg_write(x86.UC_X86_REG_EIP, self.get(sp))
        uc.reg_write(x86.UC_X86_REG_ESP, sp + (12 if address == 0xA2740 else 4))

    def button(self, view, address):
        self.build(view)
        self.events.clear()
        controller = self.TEAM + 0x3000
        self.put(controller + 0x38, self.TEAM)
        self.put(controller + 0xC, self.TEAM + 0x3200)
        self.put(0xE5FF80, 4)
        self.put(0xE60284, 0)
        self.call(address, ecx=controller)
        return self.events[0] if self.events else None

    def set_node(self, slot, index):
        super().set_node(slot, index)
        node = self.nodes[slot][index]
        if node.op == 0x16:
            # Execute the stock Take Handoff operand decoder. It mirrors nonzero holes on bit 1 of its orientation.
            scratch = self.OUT + 0x400
            packed = int.from_bytes(node.to_bytes()[4:], "little")
            self.call(0x2B6620, (self.orientation,), ecx=scratch, edx=packed)
            state = self.get(self.actor(slot) + 0x20)
            self.f(state + 0x438, self.rf(scratch + 0x1c))

    def exchange(self, view, event):
        # A route flip keeps the formation. A full flip places all actors in its mirrored alignment.
        if event == 0x13:
            view = dataclasses.replace(view, positions=[(-x, y) for x, y in view.positions])
        self.build(view)
        self.orientation = 2 if event else 0
        self.put(self.TEAM + 0x1000 + 0x24, 0x1000 if event else 0)
        self.put(0xBDFC10, int(bool(event)))
        giver, back, _kind, _hole = lint.handoff_pairs(view)[0]
        self._start(giver, back, snap_time_for(view, giver))
        self._give(giver)
        return round(self.position(back)[0]), round(self.rf(self.task(back) + 0x20))


class BookTests(unittest.TestCase):
    def test_older_books_keep_stock_controls_and_accuracy_of_modern_motion_guidance(self):
        import json
        row = json.loads(BOOK.read_text())
        self.assertTrue(packs.loads_pack(json.dumps(row)).book.offset_toss_flip)
        self.assertIn("Manual pre-snap motion", row["book"]["notes"])
        del row["book"]["offset_toss_flip"]
        original = packs.loads_pack(json.dumps(row))
        self.assertFalse(original.book.offset_toss_flip)
        self.assertNotIn("offset_toss_flip", original.book.to_json())


@unittest.skipUnless(uc_module is not None and XBE.is_file(), "private US game executable and Unicorn required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = retail_bytes()
        patched, _ = toss.apply(cls.raw)
        cls.original, cls.current = MenuMachine(cls.raw), MenuMachine(patched)
        cls.plays = list(lint.pack_views(packs.load_pack(BOOK)))
        cls.crack = next(v for v in cls.plays if (v.formation, v.play) == (16, 164))
        cls.pistol = next(v for v in cls.plays if (v.formation, v.play) == (2, 145))
        cls.patch = patched

    def test_exact_install_and_foreign_hook(self):
        self.assertEqual((toss.status(self.raw), toss.status(self.patch)), ("retail", "applied"))
        self.assertEqual(toss.apply(self.patch)[0], self.patch)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        edited = bytearray(self.patch)
        edited[XbeImage(self.patch).offset(toss.SITE, 5) + 1] ^= 5
        self.assertEqual(toss.status(bytes(edited)), "foreign")

    def test_gun_spread_outside_pitch_keeps_the_carrier_with_the_exchange(self):
        before, after = self.original, self.current
        r3, black = 0x18FA60, 0x18FAB0
        self.assertEqual(before.button(self.crack, r3), 0x12)
        self.assertEqual(after.button(self.crack, r3), 0x13)
        self.assertEqual((before.button(self.crack, black), after.button(self.crack, black)), (0x13, 0x13))
        self.assertEqual(before.exchange(self.crack, 0x12), (-229, 533))
        self.assertEqual(after.exchange(self.crack, after.button(self.crack, r3)), (229, 533))
        self.assertEqual(after.exchange(self.crack, None), before.exchange(self.crack, None))
        self.assertEqual(after.exchange(self.crack, 0x13), before.exchange(self.crack, 0x13))

    def test_centered_pistol_toss_passes_interior_runs_and_route_flip_lock_are_unchanged(self):
        r3, black = 0x18FA60, 0x18FAB0
        controls = [self.pistol, next(v for v in self.plays if v.formation == 16 and lint.is_pass(v)),
                    next(v for v in self.plays if v.formation == 16 and "Zone" in v.play_name and lint.handoff_pairs(v)),
                    dataclasses.replace(self.crack, play_flags=self.crack.play_flags | 0x1000)]
        for v in controls:
            for button in (r3, black):
                with self.subTest(play=v.play_name, flags=v.play_flags, button=button):
                    self.assertEqual(self.current.button(v, button), self.original.button(v, button))
        self.assertEqual(self.current.button(self.pistol, r3), 0x12)
        for event in (None, 0x12, 0x13):
            self.assertEqual(self.current.exchange(self.pistol, event), self.original.exchange(self.pistol, event))


if __name__ == "__main__":
    unittest.main()

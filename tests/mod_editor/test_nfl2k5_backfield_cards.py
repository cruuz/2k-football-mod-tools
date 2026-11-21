"""Starting backfield cards, their native calling convention and Studio authoring paths."""
import itertools
from pathlib import Path
import hashlib
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build as build, modpack, modpack_sources
from mod_editor.core import nfl2k5_backfield_cards as cards, nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_console_memory as memory, nfl2k5_memory_budget as budget
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn as uc
    from unicorn import x86_const as reg
except ImportError:
    uc = None


class SettingsTests(unittest.TestCase):
    def test_gadget_slots_precede_cards_even_when_another_feature_spills_to_the_pool(self):
        expected = {("nfl2k5_gadget_proof", "code"): (0x151F680, 2048),
                    ("nfl2k5_gadget_proof", "read_only"): (0x151FE80, 12800),
                    ("nfl2k5_backfield_cards", "code"): (0x1523080, 176)}
        self.assertLess(space.LATE_OWNERS.index("nfl2k5_gadget_proof"), space.LATE_OWNERS.index(cards.OWNER))
        for size in (0, 0x2000, 0x13500, 0x17800, 0x30000):
            with self.subTest(extra_resident_bytes=size):
                extra = (("test_large_table", "read_only", size, 256),) if size else ()
                rows = space.plan(extra + cards.REQUESTS)["allocations"]
                found = {(r["owner"], r["kind"]): (r["va"], r["size"]) for r in rows
                         if (r["owner"], r["kind"]) in expected}
                self.assertEqual(found, expected)
                intervals = sorted((r["va"], r["va"] + r["size"]) for r in rows)
                self.assertTrue(all(end <= start for (_, end), (start, _) in zip(intervals, intervals[1:])))
        for partial in space.GADGET_REQUESTS:
            with self.subTest(incomplete=partial), self.assertRaisesRegex(ValueError, "gadget allocation"):
                space.plan((partial, space.BACKFIELD_REQUEST))

    def test_foreign_format_refuses(self):
        self.assertEqual(cards.status(b"XEX2" + bytes(512)), "foreign")
        with self.assertRaises(ValueError):
            cards.apply(b"XEX2" + bytes(512))

    def test_optional_switch_and_recipe_round_trip(self):
        default = build.BuildPlan("source", "target")
        self.assertFalse(default.backfield_cards)
        selected = build.BuildPlan("source", "target", backfield_cards=True)
        self.assertTrue(selected.wants_xbe_patch())
        self.assertTrue(settings.to_plan(settings.from_plan(selected), "source", "target").backfield_cards)
        self.assertTrue(selected.to_recipe()["backfield_cards"])
        self.assertEqual(modpack.describe_operation({"op": "backfield_cards"}),
                         "Show the starting backfield on Coach Matchup")

    def test_preset_and_extracted_source_recipe_respect_console_target(self):
        for name in build.PRESETS:
            for mb in (64, 128):
                with self.subTest(preset=name, console_memory=mb):
                    plan = build.apply_preset(build.BuildPlan("in", "out", console_memory=mb), name)
                    self.assertEqual(plan.backfield_cards, mb == 128)
                    old = modpack_sources.build_plan({"preset": name, "overrides": {"console_memory": mb}})
                    self.assertEqual(old.backfield_cards, mb == 128)
                    frozen = {"console_memory": mb, "backfield_cards": plan.backfield_cards}
                    self.assertEqual(modpack_sources.build_plan({"preset": name, "overrides": frozen}).backfield_cards,
                                     plan.backfield_cards)
        disabled = {"preset": "softdrink_basic", "overrides": {"backfield_cards": False}}
        self.assertFalse(modpack_sources.build_plan(disabled).backfield_cards)
        message = memory.requires_128()["backfield_cards"]
        self.assertIn("available in the standard preset", message)
        self.assertIn("compact preset keeps the original display", message)
        self.assertEqual(budget.BUILD_OWNER_BYTES["backfield_cards"][0], cards.CODE_SIZE)

    def test_studio_checkbox_project_restore_and_console_switch(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel
        app = QApplication.instance() or QApplication([])
        panel = BuildPanel()
        try:
            box = panel._boxes()["backfield_cards"]
            box.setEnabled(True)
            box.setChecked(True)
            self.assertTrue(panel.plan().backfield_cards)
            saved = panel.project_build_settings()
            box.setChecked(False)
            panel.restore_project_build_settings(saved)
            self.assertTrue(panel.plan().backfield_cards)
            panel.set_console_memory(64)
            self.assertFalse(box.isEnabled())
            self.assertFalse(panel.plan().backfield_cards)
            panel.set_console_memory(128)
            self.assertTrue(panel.plan().backfield_cards)
        finally:
            panel.deleteLater()
            app.processEvents()


@unittest.skipUnless(uc is not None, "Unicorn is needed to execute the card handler")
class HandlerTests(unittest.TestCase):
    """Execute the shipped handler. The four stock helper interfaces have independent test doubles."""
    CODE = 0x1800000
    STACK = 0x1904000
    STOP = 0x34C770
    CLUBS = (0x200000, 0x210000)
    MODE = 0xAE7C58

    def setUp(self):
        self.vm = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for page in (0xE7000, 0xE8000, 0x34B000, 0x34C000, 0xAE7000, self.CODE):
            self.vm.mem_map(page, 0x1000)
        self.vm.mem_map(self.STACK - 0x2000, 0x3000)
        self.vm.mem_write(self.CODE, cards.code_for(self.CODE))
        self.vm.mem_write(cards.RETURN, bytes.fromhex("5e5dc20400"))  # The stock pop esi/pop ebp/ret 4.
        self.vm.hook_add(uc.UC_HOOK_CODE, self.step)
        self.calls = []
        self.rows = bytearray(160)

    def word(self, address):
        return struct.unpack("<I", self.vm.mem_read(address, 4))[0]

    def arguments(self, count):
        sp = self.vm.reg_read(reg.UC_X86_REG_ESP)
        return tuple(self.word(sp + 4 + 4 * i) for i in range(count))

    def finish_call(self, nargs, value):
        sp = self.vm.reg_read(reg.UC_X86_REG_ESP)
        self.vm.reg_write(reg.UC_X86_REG_EIP, self.word(sp))
        self.vm.reg_write(reg.UC_X86_REG_ESP, sp + 4 + nargs * 4)
        # The new caller cannot depend on a prior helper retaining volatile registers or flags.
        self.vm.reg_write(reg.UC_X86_REG_ECX, 0xBAD10)
        self.vm.reg_write(reg.UC_X86_REG_EDX, 0xBAD20)
        self.vm.reg_write(reg.UC_X86_REG_EFLAGS, 0x46)
        self.vm.reg_write(reg.UC_X86_REG_EAX, value)

    def step(self, vm, address, size, user):
        eax, ecx, edx = (vm.reg_read(r) for r in (reg.UC_X86_REG_EAX, reg.UC_X86_REG_ECX, reg.UC_X86_REG_EDX))
        if address == cards.ORIGINAL_HANDLER:
            self.calls.append("original")
            vm.emu_stop()
        elif address == 0xE80D0:
            self.assertEqual(ecx, self.CLUBS[self.side])
            self.assertEqual(self.arguments(2), (0, 0))
            self.context = edx
            self.assertGreaterEqual(self.context, self.STACK - 0x400)
            self.assertLessEqual(self.context + cards.ROSTER_CONTEXT_SIZE, self.STACK)
            vm.mem_write(self.context, bytes([0x69]) * cards.ROSTER_CONTEXT_SIZE)
            self.calls.append("rank")
            self.finish_call(2, self.context)
        elif address == 0xE75A0:
            self.assertEqual(edx, self.context)
            self.finish_call(0, len(self.lists[ecx]))
        elif address == 0xE7810:
            ctx, ordinal = self.arguments(2)
            self.assertEqual((ecx, ctx), (0, self.context))
            self.assertLess(ordinal, len(self.lists[eax]))
            self.finish_call(2, self.lists[eax][ordinal])
        elif address == 0x34B7C0:
            club, = self.arguments(1)
            self.assertEqual((ecx, club), (self.side, self.CLUBS[self.side]))
            self.assertEqual(eax, self.calls.count("emit"))
            struct.pack_into("<5I", self.rows, (self.side + 2 * eax) * 20, 1, 1, 0, edx, club)
            self.calls.append("emit")
            self.finish_call(1, eax + 1)

    def prepare(self, side, lists, mode):
        self.side, self.lists = side, lists
        self.calls.clear()
        self.rows[:] = bytes(len(self.rows))
        initial = {
            reg.UC_X86_REG_EAX: 1, reg.UC_X86_REG_EBX: self.CLUBS[side], reg.UC_X86_REG_ECX: 0x187,
            reg.UC_X86_REG_EDX: 0xBA0, reg.UC_X86_REG_ESI: 0xAA, reg.UC_X86_REG_EDI: 0x895,
            reg.UC_X86_REG_EBP: side, reg.UC_X86_REG_ESP: self.STACK, reg.UC_X86_REG_EFLAGS: 0x247,
        }
        self.vm.mem_write(self.MODE, struct.pack("<I", mode))
        self.vm.mem_write(self.STACK, struct.pack("<5I", 0x51A4, 0x99E, self.STOP, side, 0x7842))
        for key, val in initial.items():
            self.vm.reg_write(key, val)
        return initial

    def test_full_outputs_registers_and_bounded_ordinals_on_both_sides(self):
        for counts in itertools.product(range(4), repeat=3):
            lists = [[(role + 1) * 0x1000 + rank * 84 for rank in range(n)] for role, n in enumerate(counts)]
            expected = [group[0] for group in lists if group]
            expected.extend(group[1] for group in lists[1:] if len(group) > 1)
            expected = expected[:3]
            for side, club in enumerate(self.CLUBS):
                with self.subTest(counts=counts, side=side):
                    registers = self.prepare(side, lists, 0)
                    self.vm.emu_start(self.CODE, self.STOP, count=1000)
                    self.assertEqual(self.vm.reg_read(reg.UC_X86_REG_EIP), self.STOP)
                    expected_rows = bytearray(160)
                    for i, player in enumerate(expected):
                        struct.pack_into("<5I", expected_rows, (side + 2 * i) * 20, 1, 1, 0, player, club)
                    self.assertEqual(self.rows, expected_rows)
                    self.assertEqual(self.calls, ["rank"] + ["emit"] * len(expected))
                    registers.update({reg.UC_X86_REG_EAX: len(expected), reg.UC_X86_REG_ESI: 0x51A4,
                                      reg.UC_X86_REG_EBP: 0x99E, reg.UC_X86_REG_ESP: self.STACK + 16})
                    for key, value in registers.items():
                        self.assertEqual(self.vm.reg_read(key), value)
                    self.assertEqual(self.word(self.STACK + 16), 0x7842)

    def test_special_modes_delegate_to_retail_with_original_stack_flags_and_registers(self):
        for mode in (1, 2, 0xFFFFFFFF):
            for side in (0, 1):
                expected = self.prepare(side, [], mode)
                stack = bytes(self.vm.mem_read(self.STACK, 20))
                self.vm.emu_start(self.CODE, self.STOP, count=100)
                self.assertEqual(self.calls, ["original"])
                self.assertEqual(bytes(self.vm.mem_read(self.STACK, 20)), stack)
                self.assertEqual(self.rows, bytes(160))
                for key, value in expected.items():
                    self.assertEqual(self.vm.reg_read(key), value)


class PrivateWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = retail_xbe()
        cls.patched, cls.receipt = cards.apply(cls.base)

    @unittest.skipUnless(uc is not None, "Unicorn is needed for the signed franchise")
    def test_signed_franchise_promoted_quarterback_on_both_sides_of_backfield(self):
        from mod_editor.core import nfl2k5_roster_records as records, nfl2k5_senior_bowl as bowl
        from tests.nfl2k5_supersim_draft_fixture import Machine, signed_save

        def roster_order(game, team, position):
            count = game.uc.mem_read(team + 0x11C, 1)[0]
            players = [game.get(team + 4 * i) for i in range(count)]
            return [p for p in players if game.uc.mem_read(p + 0x35, 1)[0] == position]

        original = Machine(self.base, trace_writes=False)
        body = bytearray(signed_save())
        original.load_franchise(bytes(body))
        quarterbacks = roster_order(original, original.get(0xE5786C), 0)
        first, promoted = quarterbacks[:2]
        self.assertEqual([(original.get(p + 0x28) >> 10) & 7 for p in (first, promoted)], [0, 1])
        for player, rank in ((first, 1), (promoted, 0)):
            offset = player - original.ARENA + 0x28
            word, = struct.unpack_from("<I", body, offset)
            struct.pack_into("<I", body, offset, (word & ~(7 << 10)) | (rank << 10))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SAVEGAME.DAT"
            path.write_bytes(body)
            path.with_name("EXTRA").write_bytes(records.sign_save(bytes(body)))
            document, _ = bowl.read_franchise(path)
            payload = bytes(document.body)
            self.assertEqual(payload, body)

        positions = (0, 7, 8)  # QB, halfback and fullback in the signed f0 franchise.
        for label, image in (("retail", self.base), ("patched", self.patched)):
            game = Machine(image, trace_writes=False)
            game.load_franchise(payload)
            clubs = [game.get(0xE5786C + 4 * i) for i in range(2)]
            for home, away in (clubs, clubs[::-1]):
                with self.subTest(handler=label, promoted_club_home=home == clubs[0]):
                    game.call(0x77AE0, ecx=home)
                    game.call(0x77B20, ecx=away)
                    game.call(0x34BC10, budget=2_000_000)
                    expected = bytearray(160)
                    for side, (team, copy) in enumerate(((away, 0xAE7FC0), (home, 0xAE7DCC))):
                        self.assertEqual(game.uc.mem_read(copy, 500), game.uc.mem_read(team, 500))
                        context = game.ARENA + 0x150000
                        game.call(0xE80D0, ecx=team, edx=context, args=(0, 0), budget=2_000_000)
                        for role, position in enumerate(positions):
                            raw_first = roster_order(game, team, position)[0]
                            self.assertGreater(game.call(0xE75A0, ecx=role, edx=context), 0)
                            starter = game.call(0xE7810, eax=role, args=(context, 0))
                            self.assertEqual(game.uc.mem_read(starter + 0x35, 1)[0], position)
                            if team == clubs[0] and position == 0:
                                self.assertEqual((raw_first, starter), (first, promoted))
                            player = raw_first if label == "retail" else starter
                            struct.pack_into("<5I", expected, (side + 2 * role) * 20, 1, 1, 0, player, copy)
                    game.put(0xAE7C54, 1)  # Backfield tab
                    game.put(0xAE7C58, 0)  # Player Lineup
                    game.call(0x34C9B0, budget=2_000_000)  # The screen refresh populates both sides.
                    self.assertEqual(bytes(game.uc.mem_read(0xAE7C8C, 160)), bytes(expected))

    def test_guarded_writer_preallocated_and_idempotent(self):
        self.assertEqual(cards.status(self.base), "retail")
        self.assertEqual(cards.status(self.patched), "applied")
        preallocated, _ = space.apply(self.base, cards.REQUESTS, scaleout=True)
        self.assertEqual(cards.status(preallocated), "retail")
        self.assertEqual(cards.apply(preallocated)[0], self.patched)
        again, receipt = cards.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["changed_bytes"], 0)
        before, after = XbeImage(self.base), XbeImage(self.patched)
        offset = cards.SITE - cards.DISPATCH
        region = bytearray(before.read(cards.DISPATCH, cards.DISPATCH_BYTES))
        region[offset:offset + 4] = struct.pack("<I", int(self.receipt["code_va"], 16))
        self.assertEqual(after.read(cards.DISPATCH, cards.DISPATCH_BYTES), region)

    def test_foreign_word_shared_continuation_helpers_and_owner_bytes_refuse(self):
        for original, va in [(self.base, cards.SITE), (self.base, 0x34C2F6), (self.patched, 0x135000),
                             *((self.base, va) for va, _, _ in cards.GUARDS),
                             (self.patched, int(self.receipt["code_va"], 16))]:
            with self.subTest(address=hex(va)):
                changed = bytearray(original)
                changed[XbeImage(original).offset(va)] ^= 1
                self.assertEqual(cards.status(bytes(changed)), "foreign")
                with self.assertRaises(ValueError):
                    cards.apply(bytes(changed))

    def test_upgrade_reserves_both_gadget_slots_without_enabling_the_rule(self):
        sources = (("NFL2K5_V08_XBE", "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"),
                   ("NFL2K5_B780_RC_XBE", "1a476d94ee64acf5bb287736cc06fea8f8f8181f3ee98e2b9586006c5659c9da"),
                   ("NFL2K5_V09_XISO", "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866"))
        for key, expected in sources:
            with self.subTest(source=key):
                path = Path(os.environ.get(key, ""))
                if not path.is_file():
                    self.skipTest(f"{key} requires a private SOFTDRINK source")
                source = build._xbe_bytes(path)
                self.assertEqual(hashlib.sha256(source).hexdigest(), expected)
                patched, receipt = cards.apply(source)
                self.assertEqual(receipt["code_va"], "0x1523080")
                before, after = XbeImage(source), XbeImage(patched)
                final_rows = space.layout(patched)["allocations"]
                for old in space.layout(source)["allocations"]:
                    if old["owner"] != space.DIRECTORY_OWNER:
                        self.assertIn(old, final_rows)
                        self.assertEqual(after.read(old["va"], old["size"]), before.read(old["va"], old["size"]))
                self.assertEqual(after.read(0x151F680, 2048), b"\xcc" * 2048)
                self.assertEqual(after.read(0x151FE80, 12800), bytes(12800))
                for va, size in ((0x18A641, 5), (0xE7760, 6)):
                    self.assertEqual(after.read(va, size), before.read(va, size))

    def test_populated_gadget_reservation_can_gain_cards_in_place(self):
        reserved, _ = space.apply(self.base, space.GADGET_REQUESTS, scaleout=True)
        existing_code = bytes([0x90]) * 2047 + b"\xc3"
        occupied, _ = space.install_code(reserved, space.GADGET_OWNER, existing_code)
        result, receipt = cards.apply(occupied)
        self.assertEqual(receipt["code_va"], "0x1523080")
        self.assertEqual(XbeImage(result).read(0x151F680, 2048), existing_code)

    def test_source_export_freezes_the_actual_disc_option(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project.json"
            project.write_text(json.dumps({"edits": [], "options": {}}))
            recipe = root / "frozen.json"
            recipe.write_text(json.dumps({"preset": "softdrink_basic", "overrides": {},
                                          "freeze": {"project": {"path": str(project)}}}))
            for name, payload, enabled in (("old", self.base, False), ("fixed", self.patched, True)):
                with self.subTest(name=name):
                    game = root / (name + ".xbe")
                    game.write_bytes(payload)
                    portable, _ = modpack_sources.prepare(recipe, root / name, patched_image=game)
                    self.assertEqual(portable["overrides"]["backfield_cards"], enabled)
                    self.assertEqual(modpack_sources.build_plan(portable).backfield_cards, enabled)

    def test_build_raw_source_and_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "default.xbe"
            output = Path(directory) / "out.xbe"
            source.write_bytes(self.base)
            receipt = build.build(build.BuildPlan(source, output, backfield_cards=True))
            self.assertEqual(receipt["result"]["backfield_cards"], "applied")
            self.assertEqual(output.read_bytes(), self.patched)
            self.assertEqual(source.read_bytes(), self.base)
            self.assertEqual(build.inspect(output)["backfield_cards"], "applied")


if __name__ == "__main__":
    unittest.main()

"""Bounded installed x86 proofs. Xbox I/O and rendered play remain unwitnessed."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career as c
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, Machine, prepared


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn or pinned USA retail default.xbe is absent")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("USA retail XBE evidence pin differs")
        cls.save, setup, _ = prepared()
        cls.seed = c.read_setup(setup)
        cls.payload = c.apply(retail, setup=setup)[0]

    def machine(self):
        return Machine(self.payload, self.save, self.seed)

    def test_inject_once_relocated_pointer_identity_and_native_draft_entry(self):
        m = self.machine()
        before = bytes(m.uc.mem_read(m.player, 84))
        m.uc.mem_write(m.player + 0x36, b"\x01")
        m.call(0x325B90, stop=0x325B96)
        self.assertEqual(m.get(m.state + 24), c.PROSPECT)
        self.assertEqual(bytes(m.uc.mem_read(m.player, 84)), before)
        self.assertEqual(m.reg("ESP"), m.STACK - 0x110)
        self.assertEqual(m.get(m.player + 16) - m.root, m.get(m.state + 88))
        m.uc.mem_write(m.player + 0x36, b"\x51")
        m.call("inject")
        self.assertEqual(m.uc.mem_read(m.player + 0x36, 1), b"\x51")
        m.stub(0x2BE6F0, lambda: m.ret())
        m.call("overwrite_guard", ecx=m.player)
        self.assertEqual(m.get(m.state + 24), c.LOST)
        self.assertEqual(m.call("primary"), 0)

    def test_final_generator_boundary_waits_for_draft_and_does_not_reassign_club(self):
        m = self.machine()
        generated = []
        m.stub(0x2BE900, lambda: (generated.append(True), m.ret()))
        m.put(0xE576A4, 4)
        m.call(0x2BE946)
        self.assertEqual(m.get(m.state + 24), c.PENDING)
        m.put(0xE576A4, 5)
        m.call(0x2BE946)
        self.assertEqual(m.get(m.state + 24), c.PROSPECT)
        self.assertEqual(m.get(m.state + 56), 0xFFFFFFFF)
        self.assertEqual(len(generated), 2)
        self.assertEqual(m.uc.mem_read(m.team + 0x11C, 1), b"\x03")

    def test_attach_and_each_control_survival_hook_keeps_only_myplayer(self):
        m = self.machine()
        m.activate()
        body = m.bodies()
        self.assertEqual(m.get(m.state + 2564), 0xB30C4C + 3 * 84)
        for hook, args in ((0x156640, ()), (0x156870, (0,)), (0x1A7970, ()),
                           (0x1A77A0, ()), (0x1A85E0, ()), (0x1A70E0, (body, body + 0x100, 0))):
            # Model a native catch/turnover selection attempting to hand input to another body.
            m.put(0xBD8210 + 36, 0)
            m.put(0xBD8210 + 36 + 0x10, 0xABCD)
            m.call(hook, ecx=body, args=args)
            ids = [m.get(0xBD8210 + i * 36) for i in range(22)]
            self.assertEqual(ids, [0] + [0xFFFFFFFF] * 21, hex(hook))
            self.assertEqual(m.get(0xBD8210 + 36 + 0x10), 0)
            self.assertEqual(m.get(m.state + 2568), body)
            for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
                self.assertEqual(m.reg(name), value, (hex(hook), name))
        m.put(0xBD8210 + 0x10, 0x12345678)
        m.call("rebind")
        self.assertEqual(m.get(0xBD8210 + 0x10), 0x12345678)

    def test_bench_injury_duplicate_and_cycle_detach_without_guessing(self):
        for failure in ("bench", "identity", "duplicate", "cycle"):
            m = self.machine()
            m.activate()
            body = m.bodies()
            if failure == "bench":
                m.put(body + 0x48, 1)
            elif failure == "identity":
                m.put(m.player + 16, m.get(m.player + 16) + 2)
            elif failure == "duplicate":
                m.put(body + 0x100 + 0x3C, m.get(body + 0x3C))
            else:
                m.put(body + 21 * 0x100 + 0x30, body)
            m.call("rebind", budget=200000)
            self.assertEqual(m.get(m.state + 2568), 0, failure)
            self.assertEqual(m.get(0xBE4D60), 0, failure)
            self.assertTrue(all(m.get(0xBD8210 + i * 36) == 0xFFFFFFFF for i in range(22)), failure)

    def test_selected_port_and_ordinary_franchise_transfer_fallback(self):
        m = self.machine()
        m.activate()
        m.put(m.state + 32, 7)
        body = m.bodies()
        self.assertEqual(m.get(0xBD8210), 7)
        self.assertEqual(m.get(0xBE4D60 + 7 * 24), body)
        self.assertTrue(m.input_modes)
        polled = []
        m.stub(0x120730, lambda: (polled.append(m.reg("ECX")), m.ret()))
        for index in range(22):
            m.call(0x1561A0, ecx=0xBD8210 + index * 36)
        self.assertEqual(polled, [7])
        m.put(m.state, 0)
        m.call(0x1A70E0, args=(123, 456, 789), stop=0x1A70E8)
        self.assertEqual(m.reg("ESP"), m.STACK)
        self.assertEqual((m.reg("EAX"), m.reg("ECX")), (123, 456))

    def test_cpu_team_ownership_trade_unsigned_and_reserves(self):
        m = self.machine()
        m.activate()
        self.assertEqual(m.get(m.state + 24), c.ACTIVE)
        self.assertEqual(m.get(m.state + 56), 0)
        self.assertEqual(m.call(0xC4D50, ecx=m.team), 0)
        # Exercise the actual return-address exception used by native game launch.
        self.assertEqual(m.call(0xC4D50, ecx=m.team, stop=0xC7462, return_to=0xC7462), 1)
        m.uc.mem_write(m.team + 0x11C, b"\x03")
        m.call("resolve_team")
        self.assertEqual(m.get(m.state + 24), c.UNSIGNED)
        other = m.team + 500
        m.put(other + 3 * 4, m.player)
        m.uc.mem_write(other + 0x11C, b"\x04")
        m.call("resolve_team")
        self.assertEqual(m.get(m.state + 56), 1)
        m.uc.mem_write(other + 0x11C, b"\x03")
        m.uc.mem_write(other + 0x19B, b"\x01")
        m.uc.mem_write(other + 0x1F2, b"\x01\xa5")
        m.call("resolve_team")
        self.assertEqual(m.get(m.state + 24), c.RESERVE)
        self.assertEqual(m.get(m.state + 60), 0)

    def test_gm_dispatchers_refuse_and_other_screens_replay_native_entry(self):
        m = self.machine()
        m.activate()
        for va in (0x142910, 0x142950):
            self.assertEqual(m.call(va), 0)
            self.assertEqual(m.get(m.state + 2576), 6)
        for descriptor in (0x52533C, 0x503D6C, 0x555098, m.code["va"] + 4096):
            self.assertEqual(m.call(0x6E390, edx=descriptor), 0)
        m.call(0x6E390, ecx=m.BODIES, edx=0x508DF0, stop=0x6E39A)
        self.assertEqual(m.reg("ESI"), m.BODIES)
        m.call(0x6E390, ecx=m.BODIES, edx=0x500DC8, stop=0x6E39A)
        self.assertEqual(m.get(m.state), 0)
        self.assertEqual(m.get(m.state + 2580), 0)
        m.put(0xE576A0, 0)
        m.call(0x142910, stop=0x142916)
        self.assertEqual(m.reg("ESP"), m.STACK - 12)

    def test_career_game_sim_is_blocked_other_game_reaches_native_whole_game(self):
        m = self.machine()
        m.activate()
        self.assertEqual(m.call(0xC6D10, ecx=0, edx=0), 1)
        self.assertEqual(m.call(0xC7A20, ecx=0, edx=0, args=(0,)), 0)
        m.uc.mem_write(0xE57C48, bytes([0, 1, 2, 9, 12, 4, 1, 0]))
        self.assertEqual(m.call(0xC6D10, ecx=0, edx=1), 0)
        m.call(0xC7A20, ecx=0, edx=1, args=(0,), stop=0xC7A26)
        self.assertEqual(m.reg("ESP"), m.STACK - 0x110)
        self.assertEqual((m.reg("ECX"), m.reg("EDX")), (0, 1))
        self.assertEqual(m.call("career_fixture", ecx=22, edx=0), 0)
        m.put(m.state + 24, c.LOST)
        self.assertEqual(m.call(0xC7A20, ecx=0, edx=1, args=(0,)), 0)

    def test_native_whole_game_dispatch_commits_other_fixture_and_replay_skips_engine(self):
        m = self.machine()
        m.activate()
        m.uc.mem_write(0xE57C48, bytes([0, 1, 2, 9, 12, 4, 1, 0]))
        engine = []
        # Art, progress dialog and the full statistics simulation are outside
        # this bounded proof. Native routing, row/slot setup and commit run.
        for va, pop in ((0x24C380, 0), (0x4A410, 8), (0x134D20, 0), (0x177990, 4),
                        (0x14EC60, 0), (0x77AE0, 0), (0x77B20, 0), (0x24AD80, 0)):
            m.stub(va, lambda pop=pop: m.ret(pop=pop))
        m.stub(0xC5220, lambda: m.ret(123, pop=20))
        m.stub(0x10B9C0, lambda: (engine.append((m.reg("ECX"), m.reg("EDX"))), m.ret(1, pop=4)))
        self.assertEqual(m.call(0xC7A20, ecx=0, edx=1, args=(0,)), 1)
        self.assertEqual(len(engine), 1)
        self.assertEqual(m.uc.mem_read(0xE57C48, 1), b"\x03")
        self.assertEqual(m.uc.mem_read(0xE57C40, 1), b"\x00")
        self.assertEqual(m.call(0xC7A20, ecx=0, edx=1, args=(0,)), 1)
        self.assertEqual(len(engine), 1)

    def test_standard_far_camera_focus_uses_myplayer_transform(self):
        m = self.machine()
        m.activate()
        body = m.bodies()
        for camera in (0, 1):
            m.put(m.state + 36, camera)
            m.put(0xB665F0, 7)
            m.call(0xA5490)
            self.assertEqual(m.get(0xB665F0), camera)
            self.assertEqual(m.get(0xB665F4), 1)
        m.put(body + 0x18, m.BODIES + 0x8000)
        captured = []
        def camera():
            captured.append([m.get(m.reg("ESP") + i * 4) for i in range(1, 7)])
            m.ret(pop=24)
        m.stub(0x5F760, camera)
        m.call("camera_focus", ecx=1, args=(0x3F800000, 123, 456, 0, 0, 0))
        self.assertEqual(captured[0], [0x3F800000, m.BODIES + 0x8030, 456, 0, 0, 0])

    def test_committed_week_xp_survives_week_navigation_and_replay(self):
        m = self.machine()
        m.activate()
        m.bodies()
        m.uc.mem_write(0xE57C40, b"\x03")
        m.put(0xE576B4, 1)
        m.call("settle")
        self.assertEqual(m.get(m.state + 64), 25)
        self.assertEqual(m.get(m.state + 76), 1)
        expected, _ = c.award_week(c.seal_state(bytes(m.uc.mem_read(m.state, 1280))[:64] + bytes(16) + bytes(m.uc.mem_read(m.state + 80, 1200))),
                                  year=7, stage=8, week=0, fixture=0, committed=True, appeared=True)
        self.assertEqual(m.get(m.state + 68), struct.unpack_from("<I", expected, 68)[0])
        m.call("settle")
        self.assertEqual(m.get(m.state + 64), 25)

    def test_native_checkpoint_roundtrip_pairs_full_save_and_closes_handles(self):
        m = self.machine()
        m.activate()
        self._journal(m)
        m.call("checkpoint_write", esi=self.IO, budget=12000000)
        self.assertEqual(len(self.files), 1)
        raw = next(iter(self.files.values()))
        c.validate_state(raw, self.save)
        self.assertEqual(len(raw), 1280)
        m.uc.mem_write(m.state, bytes(1280))
        m.call("checkpoint_read", esi=self.IO, budget=12000000)
        self.assertEqual(m.get(m.state + 24), c.LOST)
        self.assertEqual(m.call("primary"), 0)
        m.call("confirm_load")
        self.assertEqual(bytes(m.uc.mem_read(m.state, 1280)), raw)
        self.assertEqual(self.handles, {})
        # Seed bootstrap has the same exact pairing, independent of RAM address.
        self.files.clear()
        m.call("checkpoint_read", esi=self.IO, budget=12000000)
        m.call("confirm_load")
        self.assertEqual(bytes(m.uc.mem_read(m.state, 1280)), self.seed)
        m.put(m.state + 2580, 1)
        m.uc.mem_write(self.IO + 16, b"\x7a")
        m.call("checkpoint_read", esi=self.IO, budget=12000000)
        self.assertEqual(m.get(m.state + 24), c.LOST)
        self.assertEqual(m.get(m.state + 2576), 7)

    def test_installed_file_wrappers_forward_results_and_require_mycareer_entry(self):
        m = self.machine()
        m.activate()
        self._journal(m)
        self.files["game"] = self.save
        self.handles[99] = "game"
        count = self.IO + 0xE0000
        m.put(m.state, 0)
        self.assertEqual(m.call(0x1D8D2, args=(99, self.IO, len(self.save), count, 0)), 1)
        self.assertEqual(m.get(m.state), 0)
        m.put(m.state + 2580, 1)
        self.assertEqual(m.call(0x1D8D2, args=(99, self.IO, len(self.save), count, 0), budget=12000000), 1)
        self.assertEqual(m.get(m.state + 24), c.LOST)
        m.call("confirm_load")
        self.assertEqual(bytes(m.uc.mem_read(m.state, 1280)), self.seed)
        self.assertEqual(m.call(0x1D9BF, args=(99, self.IO, len(self.save), count, 0), budget=12000000), 1)
        journal = [raw for name, raw in self.files.items() if name.startswith("U:")]
        self.assertEqual(len(journal), 1)
        c.validate_state(journal[0], self.save)
        self.assertEqual(self.handles, {99: "game"})

    # Game Modes row route. The retail list dispatcher 0x150020 reads the screen
    # stack (ECX): [+0x100] depth, slot [depth*8] = top descriptor, slot +4 =
    # cursor, [+0x10C] = list state; each state entry is 0x2C bytes with the
    # row pointer at +0x14 and hidden/disabled words at +0x18/+0x1C. Row kind
    # 9 maps to case 3 through the byte table at 0x15024C and calls [row+0x28].
    MENU_STACK, MENU_STATE = Machine.BODIES + 0x10000, Machine.BODIES + 0x12000

    def _menu(self, m, row=1, pressed=0x100):
        S, M = self.MENU_STACK, self.MENU_STATE
        m.put(S + 0x100, 2)                       # Main Menu, then Game Modes on top
        m.put(S + 2 * 8, 0x5015CC)                # Game Modes descriptor: screen ID byte 0x11
        m.put(S + 2 * 8 + 4, row)                 # cursor on the chosen row
        m.put(S + 0x10C, M)
        m.put(M + 8, 6)                           # six rows before the kind-3 terminator
        for i in range(6):
            m.put(M + i * 0x2C + 0x14, 0x501460 + i * 0x34)
        m.put(M + 0xA7C, 2)
        m.put(0xBD8050, 1)
        m.stub(0x2498A0, lambda: m.ret(0))                         # no modal transition pending
        m.stub(0x709B0, lambda: m.ret(1))                          # every port connected
        m.stub(0xF3780, lambda: m.ret(0, pop=4))                   # no repeat/dpad input
        m.stub(0xF3750, lambda: m.ret(pressed if m.reg("EDX") == 0 else 0, pop=4))
        m.stub(0x2C8880, lambda: m.ret())                          # dispatcher tail
        m.stub(0x6E4E0, lambda: m.ret(0, pop=4))                   # descriptor event send
        m.stub(0xF3180, lambda: m.ret())
        m.stub(0xF3680, lambda: m.ret())
        dialogs = []

        def dialog():                                              # modal retail message box
            sp = m.reg("ESP")
            dialogs.append((m.reg("ECX"), m.reg("EDX"), [m.get(sp + 4 * i) for i in range(1, 7)]))
            m.ret(0xFFFFFFFF, pop=24)
        m.stub(0x14E440, dialog)
        return S, M, dialogs

    def test_game_modes_row_dispatches_to_entry_dialog_and_load_save(self):
        m = self.machine()
        S, M, dialogs = self._menu(m)
        im = XbeImage(self.payload)
        self.assertEqual(struct.unpack("<I", im.read(0x501494, 4))[0], 9)
        self.assertEqual(struct.unpack("<I", im.read(0x5014BC, 4))[0], m.labels["entry"])
        m.call(0x150020, ecx=S, budget=400000)
        # Case 3 reached entry: the sealed setup seeds the live state and entry is requested.
        self.assertEqual(m.get(M + 0x594), 0)
        self.assertEqual(m.get(m.state + 2580), 1)
        self.assertEqual(bytes(m.uc.mem_read(m.state, 1280)), bytes(self.seed[:24]) + struct.pack("<I", c.LOST) + bytes(self.seed[28:56]) + b"\xff" * 4 + bytes(self.seed[60:]))
        self.assertEqual(m.get(m.state + 2576), 7)
        self.assertEqual(len(dialogs), 1)
        ecx, edx, args = dialogs[0]
        self.assertEqual((ecx, edx), (0xE3C040, m.labels["title_text"]))
        self.assertEqual(args, [0x5042FC, 0, m.labels["entry_help"], 0, 0xFFFFFFFF, 0])
        self.assertEqual(bytes(m.uc.mem_read(edx, 18)).decode("utf-16le"), "MyCareer\0")
        # Native 0x6E390 then pushed Load / Save onto the same screen stack.
        self.assertEqual(m.get(S + 0x100), 3)
        self.assertEqual(m.get(S + 3 * 8), 0x508DF0)
        self.assertEqual(m.get(S + 0x108), 1)
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
            self.assertEqual(m.reg(name), value, name)

    def test_retail_row_bytes_push_team_select_and_neighbours_keep_their_targets(self):
        m = self.machine()
        S, M, dialogs = self._menu(m)
        # The retail First Person Football row: kind 0, its label, Team Select, no action.
        for va, value in ((0x501494, 0), (0x501498, 0xE7D5C4), (0x50149C, 0x526948), (0x5014BC, 0)):
            m.put(va, value)
        m.call(0x150020, ecx=S, budget=400000)
        self.assertEqual(dialogs, [])
        self.assertEqual((m.get(S + 0x100), m.get(S + 3 * 8)), (3, 0x526948))
        self.assertEqual(m.get(m.state + 2580), 0)
        for row, target in ((0, 0x500DC8), (2, 0x529AE0), (3, 0x529344), (4, 0x501298), (5, 0x501434)):
            with self.subTest(row=row):
                other = self.machine()
                S2, _, d2 = self._menu(other, row=row)
                other.call(0x150020, ecx=S2, budget=400000)
                self.assertEqual((d2, other.get(S2 + 0x100), other.get(S2 + 3 * 8)), ([], 3, target))
                self.assertEqual(other.get(other.state + 2580), 0)

    def test_unconfigured_build_explains_itself_and_pushes_nothing(self):
        payload = c.apply(XBE.read_bytes())[0]
        m = Machine(payload)
        S, M, dialogs = self._menu(m)
        m.call(0x150020, ecx=S, budget=400000)
        self.assertEqual(len(dialogs), 1)
        self.assertEqual(dialogs[0][1], m.labels["title_text"])
        self.assertEqual(dialogs[0][2][2], m.labels["no_setup_help"])
        self.assertEqual(m.get(S + 0x100), 2)
        self.assertEqual(m.get(m.state + 2580), 0)
        self.assertEqual(bytes(m.uc.mem_read(m.state, 1280)), bytes(1280))
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333), ("EBP", 0x44444444)):
            self.assertEqual(m.reg(name), value, name)

    def test_identity_follows_the_recipe_position_for_a_wide_receiver(self):
        save, setup, _ = prepared("WR")
        payload = c.apply(XBE.read_bytes(), setup=setup)[0]
        m = Machine(payload, save, c.read_setup(setup))
        self.assertEqual(m.uc.mem_read(m.player + 0x35, 1), b"\x03")
        self.assertEqual(m.call("primary"), m.player)
        m.activate()
        self.assertEqual(m.get(m.state + 24), c.ACTIVE)
        body = m.bodies()
        self.assertEqual(m.get(m.state + 2568), body)
        self.assertEqual(m.get(0xBD8210), 0)
        m.uc.mem_write(m.player + 0x35, b"\x00")
        self.assertEqual(m.call("primary"), 0)
        self.assertEqual(m.get(m.state + 24), c.LOST)

    def test_starter_lock_writes_depth_row_one_and_rank_bit_once(self):
        m = self.machine()
        m.activate()
        self.assertEqual(m.get(m.state + 24), c.ACTIVE)
        self.assertEqual(struct.unpack("<H", m.uc.mem_read(m.player + 0x28, 2))[0] & 0x1C00, 0)
        self.assertEqual(m.uc.mem_read(m.player + 0x52, 1), b"\x01")
        self.assertEqual(m.get(m.state + c.STARTER_DONE_OFFSET), 1)
        m.uc.mem_write(m.player + 0x28, struct.pack("<H", 0x0800))
        m.call("resolve_team")
        self.assertEqual(struct.unpack("<H", m.uc.mem_read(m.player + 0x28, 2))[0], 0x0800)
        save, setup, _ = prepared(starter_lock=False)
        quiet = Machine(c.apply(XBE.read_bytes(), setup=setup)[0], save, c.read_setup(setup))
        quiet.activate()
        self.assertEqual(quiet.get(quiet.state + 24), c.ACTIVE)
        self.assertEqual(struct.unpack("<H", quiet.uc.mem_read(quiet.player + 0x28, 2))[0] & 0x1C00, 0x0C00)
        self.assertEqual(quiet.uc.mem_read(quiet.player + 0x52, 1), b"\x00")
        self.assertEqual(quiet.get(quiet.state + c.STARTER_DONE_OFFSET), 0)

    def _journal(self, m):
        self.IO = 0x2400000
        m.uc.mem_map(self.IO, 0x100000)
        m.uc.mem_write(self.IO, self.save)
        self.files, self.handles = {}, {}
        def create():
            sp = m.reg("ESP")
            name = bytes(m.uc.mem_read(m.get(sp + 4), 18)).split(b"\0")[0].decode("ascii")
            disposition = m.get(sp + 20)
            if disposition == 3 and name not in self.files:
                return m.ret(0xFFFFFFFF, pop=28)
            self.handles[17] = name
            m.ret(17, pop=28)
        def io(writing):
            sp = m.reg("ESP")
            handle, buffer, n, count = [m.get(sp + i * 4) for i in range(1, 5)]
            if writing:
                self.files[self.handles[handle]] = bytes(m.uc.mem_read(buffer, n))
            else:
                raw = self.files[self.handles[handle]][:n]
                m.uc.mem_write(buffer, raw)
                n = len(raw)
            m.put(count, n)
            m.ret(1, pop=20)
        def close():
            del self.handles[m.get(m.reg("ESP") + 4)]
            m.ret(1, pop=4)
        m.stub(0x1E336, create)
        m.stub("read_original", lambda: io(False))
        m.stub("write_original", lambda: io(True))
        m.stub(0x1A69F, close)


if __name__ == "__main__":
    unittest.main()

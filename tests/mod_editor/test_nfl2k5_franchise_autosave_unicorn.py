"""Execute installed hooks and native menu/save routing with bounded services.

No emulator boot, OS write, signed container claim or graphical witness. The
storage, rendering and unrelated state service boundaries are in the fixture.
"""
import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_autosave as a
from mod_editor.core import nfl2k5_franchise_practice as practice
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_franchise_autosave_fixture import Machine, XBE, HAVE_UC


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "requires Unicorn and pinned USA retail default.xbe")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail USA XBE evidence pin differs")
        cls.payload = a.apply(cls.retail)[0]
        cls.practice_payload = practice.apply(cls.payload)[0]

    def test_actual_rows_share_off_on_display_and_never_activate_fpf(self):
        with Machine(self.payload) as m:
            for row in a.ROW_VAS:
                self.assertEqual(m.string(m.get(row+4)), "Auto Save")
                self.assertEqual(m.call(m.get(row+20)), 0)
                self.assertEqual(m.string(m.call(m.get(row+32))), "Off")
                self.assertEqual(m.call(m.get(row+24)), 1)
                self.assertEqual(m.call(m.get(row+20)), 1)
                self.assertEqual(m.string(m.call(m.get(row+32))), "On")
                self.assertEqual(m.get(0xE5FFE4), 0)
                m.call(m.get(row+28))

    def test_real_settings_copy_persists_only_original_word_and_load_consumes_it(self):
        with Machine(self.payload) as m:
            original = bytes(m.uc.mem_read(0xE5FF80, 0x2E0))
            m.call("toggle")
            m.call("serialize", ecx=m.BUFFER)
            expected = bytearray(original)
            struct.pack_into("<I", expected, 0x64, 1)
            self.assertEqual(bytes(m.uc.mem_read(m.BUFFER, 0x2E0)), expected)
            self.assertEqual(bytes(m.uc.mem_read(0xE5FF80, 0x2E0)), original)
            m.call("toggle")
            m.uc.mem_write(0xE5FF80, bytes(expected))
            self.assertEqual(m.call("load_settings", ebp=0), m.call(0xA5460))
            self.assertEqual(m.call("getter"), 1)
            self.assertEqual(m.get(0xE5FFE4), 0)
            for word in (0, 2, 0xFFFFFFFF):
                m.put(0xE5FFE4, word)
                m.call("load_settings", ebp=0)
                self.assertEqual(m.get(m.state), 0)
                self.assertEqual(m.get(0xE5FFE4), 0)
            m.put(0xE576A0, 1)
            m.put(0xE5FFE4, 7)
            m.call("serialize", ecx=m.BUFFER)
            self.assertEqual(m.get(m.BUFFER+0x64), 7)
            m.put(0xBDC1D4, 8)
            m.call("load_settings", ebp=0)
            self.assertEqual(m.get(0xE5FFE4), 7)

    def test_real_played_commit_retains_stats_dirty_flag_and_only_marks_franchise(self):
        for mode in (0, 1, 2):
            for game_state in (0, 1, 2):
                with self.subTest(mode=mode, game_state=game_state), Machine(self.payload) as m:
                    m.call("toggle")
                    m.put(0xE576A0, mode)
                    m.put(0xA83A18, game_state)
                    m.put(0xE576B4, 0)
                    m.put(0xE576BC, 0)
                    for va in (0x1356C0, 0x134140):
                        m.stub(va, lambda va=va: (m.events.append(va), m.ret()))
                    m.call(0xC5D60)
                    self.assertEqual(m.get(m.state+4), int(mode == 2 and game_state == 2))
                    self.assertEqual(m.events, [0x1356C0, 0x134140] if game_state == 2 else [])
                    if game_state == 2:
                        self.assertEqual(m.get(0xE576A8), 1)
                        self.assertEqual(m.uc.mem_read(0xE57C40, 1)[0] & 3, 3)

    def test_native_teardown_excludes_practice_modes(self):
        for settings_mode in (0, 1, 2, 5, 6, 7):
            with self.subTest(settings_mode=settings_mode), Machine(self.payload) as m:
                m.call("toggle")
                m.put(0xE5FF80, settings_mode)
                m.put(0xA83A18, 2)
                m.put(0xE576B4, 0)
                m.put(0xE576BC, 0)
                for va in (0x834F0, 0x61950, 0xF6030, 0xF72A0, 0xF5C70, 0xF5170,
                           0xF61E0, 0x432D0, 0xF6230, 0xF6510, 0x1356C0, 0x134140):
                    m.stub(va, lambda: m.ret())
                m.call(0x645D0)
                self.assertEqual(m.get(m.state+4), int(settings_mode in (5, 6, 7)))

    def test_simulation_post_result_native_call_marks_without_saving(self):
        with Machine(self.payload) as m:
            m.call("toggle")
            m.stub(0xC5220, lambda: m.ret(0x2207000, pop=20))
            def simulate():
                self.assertEqual(m.get(m.state+4), 0)
                m.events.append("simulated")
                m.ret(1, pop=4)
            m.stub(0x10B9C0, simulate)
            m.call(0xC7B25, stop=0xC7B66, ebx=0xE57C40, ebp=0x2208000, esi=0, edi=0)
            self.assertEqual(m.events, ["simulated"])
            self.assertEqual(m.get(m.state+4), 1)
            self.assertEqual(m.uc.mem_read(0xE57C40, 1)[0] & 3, 3)

    def test_live_desk_event_and_native_update_save_after_two_quiet_ticks(self):
        for payload in (self.payload, self.practice_payload):
            with Machine(payload) as m:
                m.native_save_services()
                m.native_desk_services()
                m.ready()
                m.event_tick()
                self.assertEqual(m.events, [])
                m.event_tick()
                self.assertEqual(m.events, ["discover", ("select", 0), "delete", "create", "write",
                                            "commit", ("select", 0), "free", "close"])
                self.assertEqual(m.get(m.state+24), 1)
                self.assertEqual(m.get(m.state+4), 0)
                self.assertEqual(m.get(m.state+8), 0)
                self.assertEqual(m.dialogs, [0x16A7A0]*4)
                self.assertEqual(struct.unpack_from("<I", m.saved, 0x64)[0], 1)
                count = len(m.events)
                for _ in range(5):
                    m.event_tick()
                self.assertEqual(len(m.events), count)

    def test_manual_save_keeps_native_prompts_and_establishes_current_slot(self):
        with Machine(self.payload) as m:
            m.native_save_services()
            m.call("toggle")
            m.put(0xBDBDA4, m.MANAGER)
            m.call(0x16E3F0, ecx=0)
            self.assertEqual(m.dialogs, [0x16BA70]+[0x16A7A0]*4+[0x16BAB0])
            self.assertEqual(m.get(m.state+12), 1)
            self.assertEqual(m.string(m.state+32), "Franchise1")
            m.put(m.state+4, 1)
            m.tick()
            m.tick()
            self.assertEqual(m.get(m.state+24), 2)
            self.assertEqual(m.get(0xBDBDA4), m.MANAGER)

    def test_io_failures_show_native_failure_release_state_and_do_not_repeat(self):
        for failure in ("delete", "create", "write", "commit", "allocation"):
            with self.subTest(failure=failure), Machine(self.payload) as m:
                m.native_save_services(fail=failure)
                m.ready()
                m.tick()
                m.tick()
                self.assertEqual(m.get(m.state+24), 0)
                self.assertEqual(m.get(m.state+8), 0)
                self.assertEqual(m.get(m.state+4), 0)
                self.assertEqual(m.events[-1], "close")
                self.assertEqual(m.get(0xBDBDA4), 0)
                if failure == "allocation":
                    self.assertIn(("notice", "Auto Save failed. Save Franchise manually."), m.events)
                else:
                    self.assertEqual(m.events.count("native_failure"), 1)
                    self.assertEqual(m.dialogs[-1], 0x16BAB0)
                    self.assertEqual(m.get(0xBDBDA0), 0)
                count = len(m.events)
                for _ in range(3):
                    m.tick()
                self.assertEqual(len(m.events), count)

    def test_off_nonfranchise_active_load_and_incomplete_desk_never_start_io(self):
        cases = [("enabled", 0), ("active", 1), (0xE576A0, 1), (0xA83A10, 123),
                 (0xAA2408, 0x524FA0), (0xAA2140, 0), (Machine.SCENE+4, 0x3F800000),
                 (Machine.SCENE+4, 0x7FC00000), (Machine.SCENE+4, 0xBF800000),
                 (Machine.MANAGER, 0x507EC8), (Machine.MANAGER+0x100, 32),
                 (0xBDBDB0, 0)] + [(0xBDBDA0, state) for state in (1, 2, 3, 4, 5, 6, 9, 42)]
        for address, value in cases:
            with self.subTest(address=address, value=value), Machine(self.payload) as m:
                m.ready()
                m.put({"enabled": m.state, "active": m.state+8}.get(address, address), value)
                m.tick()
                m.tick()
                self.assertEqual(m.events, [])

    def test_missing_slot_or_device_or_name_never_guesses_an_overwrite(self):
        for missing in ("slot", "device", "name", "count", "unavailable"):
            with self.subTest(missing=missing), Machine(self.payload) as m:
                m.ready()
                if missing == "slot":
                    m.put(m.state+12, 0)
                elif missing == "device":
                    m.put(m.DEVICES, m.DEVICE+100)
                elif missing == "count":
                    m.put(m.DEVICES+0x1C, 257)
                elif missing == "unavailable":
                    m.put(m.DEVICES+8, 0)
                else:
                    m.uc.mem_write(m.NAME, "Different\0".encode("utf-16le"))
                m.tick()
                m.tick()
                self.assertEqual(sum(isinstance(e, tuple) and e[0] == "notice" for e in m.events), 1)
                self.assertEqual(m.get(m.state+8), 0)
                self.assertNotIn("write", m.events)

    def test_reenumeration_selects_same_name_type_and_device_in_last_native_slot(self):
        with Machine(self.payload) as m:
            m.ready()
            # The former ordinal now names another file. Native device discovery
            # has also moved the original device to record 8 of 9.
            m.put(m.DEVICES, m.DEVICE+128)
            m.put(m.DEVICES+8*0x34, m.DEVICE)
            m.put(m.DEVICES+8*0x34+8, 1)
            m.put(m.DEVICES+8*0x34+0x1C, 2)
            m.put(0xBDC1D4, 8)
            m.put(0xBDC1D0+24, m.NAME)
            m.put(0xBDC1D4+24, 9)
            m.stub(0x16E3F0, lambda: (m.events.append(("save", m.reg("ECX"))), m.ret()))
            m.tick()
            m.tick()
            self.assertEqual(m.events, ["discover", ("select", 8), ("save", 1), "close"])

    def test_new_load_or_league_selection_invalidates_old_slot(self):
        with Machine(self.payload) as m:
            m.ready()
            m.call(0x16E540, stop=0x16E548)
            self.assertEqual([m.get(m.state+i) for i in (4, 12)], [0, 0])
            m.call("load_slot", ebp=0)
            self.assertEqual(m.get(m.state+12), 1)
            m.put(0xE5FFE4, 1)
            m.call(0xC7570, ecx=2)
            self.assertEqual(m.get(m.state+12), 0)
            self.assertEqual(m.get(0xE5FFE4), 0)

    def test_saved_buffer_reloads_through_native_type_dispatch_and_settings_copy(self):
        with Machine(self.payload) as source:
            source.native_save_services()
            source.ready()
            source.tick()
            source.tick()
            saved = source.saved
        for success in (False, True):
            with self.subTest(success=success), Machine(self.payload) as m:
                m.native_save_services()
                m.put(m.state+12, 1)  # A failed attempt must invalidate this.
                m.put(0xE576A0, 0)
                m.uc.mem_write(m.BUFFER, saved)
                m.stub(0x16C880, lambda: m.ret(int(success), pop=12))
                m.stub(0x16A3D0, lambda: m.ret(1, pop=4))
                m.stub(0xC5800, lambda: (m.events.append("season_loaded"), m.put(0xE576A0, 2), m.ret()))
                m.stub(0x2D0CE0, lambda: (m.events.append("front_office_loaded"), m.ret()))
                m.call(0x16E540, ecx=0, edx=0)
                self.assertEqual(m.get(m.state), int(success))
                self.assertEqual(m.get(m.state+12), int(success))
                self.assertEqual(m.get(m.state+4), 0)
                self.assertEqual(m.get(0xE5FFE4), 0)
                self.assertEqual(m.events, ["season_loaded", "front_office_loaded", "free"] if success else ["free"])
                if success:
                    self.assertIn(m.get(0xBDBDA0), (7, 8))

    def test_overlong_load_name_is_rejected_and_second_quiet_tick_resets(self):
        with Machine(self.payload) as m:
            m.uc.mem_write(m.NAME, ("X"*17+"\0").encode("utf-16le"))
            m.ready()
            self.assertEqual(m.get(m.state+12), 0)
            m.tick()
            self.assertEqual(m.get(m.state+20), 1)
            m.put(0xAA2408, 1)
            m.tick()
            self.assertEqual(m.get(m.state+20), 0)
            m.put(0xAA2408, 0)
            m.tick()
            self.assertEqual(m.events, [])

    def test_wrapped_native_registers_flags_and_stack_are_preserved(self):
        with Machine(self.payload) as m:
            m.call("toggle")
            for entry, callee in (("played", 0xC4BC0), ("simulated", 0x1C1C80), ("desk", 0x142DD0)):
                def native():
                    m.reg("ECX", 0x76543210)
                    m.reg("EDX", 0x12345678)
                    m.reg("EFLAGS", 0x247)
                    m.ret(0x123)
                m.stub(callee, native)
                self.assertEqual(m.call(entry, ecx=m.MANAGER), 0x123)
                for name, expected in (("EBX", 0x11111111), ("ESI", 0x22222222),
                                       ("EDI", 0x33333333), ("EBP", 0x44444444),
                                       ("ECX", 0x76543210), ("EDX", 0x12345678), ("EFLAGS", 0x247)):
                    self.assertEqual(m.reg(name), expected, (entry, name))


if __name__ == "__main__":
    unittest.main()

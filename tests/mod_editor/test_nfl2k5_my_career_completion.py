"""Shared completion integrity and Apartment save ABI, with native service seams.

These tests execute the commit dispatcher and save transaction. Stat providers,
rendering and storage completion are explicit fixture services, so this suite
alone does not prove a completed football match or a physical signed save.
"""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as career
from mod_editor.core import nfl2k5_franchise_autosave as autosave
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.nfl2k5_franchise_autosave_fixture import Machine, XBE, HAVE_UC


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class CompletionIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("expected bounded retail executable")
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail USA XBE evidence pin differs")
        cls.seed = space.apply(cls.retail, career.REQUESTS + autosave.REQUESTS, scaleout=True)[0]
        cls.payload = autosave.apply(career.apply(cls.seed)[0])[0]

    def test_two_orders_exact_replay_and_actual_changed_byte_receipts(self):
        reverse = career.apply(autosave.apply(self.seed)[0])[0]
        self.assertEqual(reverse, self.payload)
        for owner in (career, autosave):
            self.assertEqual(owner.status(self.payload), "applied")
            replay, receipt = owner.apply(self.payload)
            self.assertEqual(replay, self.payload)
            self.assertEqual(receipt["changed_bytes"], 0)
            before = (autosave if owner is career else career).apply(self.seed)[0]
            after, receipt = owner.apply(before)
            self.assertEqual(after, self.payload)
            self.assertEqual(receipt["changed_bytes"], sum(a != b for a, b in zip(before, after)))

    def test_complete_native_franchise_code_prefix_is_byte_identical(self):
        # The appended Apartment entry shares existing tails. Preserve the
        # witnessed Franchise implementation, including every relative branch.
        self.assertEqual(hashlib.sha256(autosave.assembly.CODE[:1027]).hexdigest(),
                         "754b944e37c1ed0f5fb9975bb98c4bc67583cd7f3cd47de981b7962c77c0f262")
        self.assertEqual(autosave.assembly.LABELS["career_complete"], 1027)
        relocations = sorted(r for r in autosave.assembly.RELOCATIONS if r[0] < 1027)
        self.assertEqual(hashlib.sha256(json.dumps(relocations).encode()).hexdigest(),
                         "49efae083f1dfff2258d3614d4c7649c57fd46764d411d6cc235cde78a395ba7")
        self.assertLessEqual(len(autosave.assembly.CODE), autosave.CODE_SIZE)
        self.assertLessEqual(career.code_for(0, 0)[1]["content_end"], career.TAG_OFFSET)

    def test_resealed_foreign_companion_and_native_contexts_refuse_before_writers(self):
        c, d = career.legacy.allocations(self.payload)
        a = autosave.allocations(self.payload)
        addresses = [0xC5D9E, 0xC5DA3, 0xC5DA9, 0xC5DAE, 0x16E4A9, 0x16E50D,
                     0x16E540, 0x16E5CE, 0x16E7C5, 0x16E815, 0x16E81A,
                     c["va"], c["va"] + career.TAG_OFFSET, d["va"],
                     a["code"]["va"] + 1027, a["data"]["va"], a["read_only"]["va"]]
        requests = space._validate(self.payload)[2]
        for va in addresses:
            with self.subTest(va=hex(va)):
                bad = bytearray(self.payload)
                bad[XbeImage(bad).offset(va, 1)] ^= 1
                space._seal_scaleout(bad, requests)
                for section in _sections(bad):
                    bad[section.header_offset+36:section.header_offset+56] = section_digest(bad, section)
                bad = bytes(bad)
                # The allocator independently requires initially zero RW;
                # content resealing cannot authorize initialized runtime data.
                self.assertEqual(space.status(bad),
                                 "foreign" if va in (d["va"], a["data"]["va"]) else "applied")
                for owner in (career, autosave):
                    self.assertEqual(owner.status(bad), "foreign", owner.OWNER)
                    with patch.object(space, "apply", side_effect=AssertionError("allocation before refusal")), \
                         patch.object(space, "install_code", side_effect=AssertionError("write before refusal")):
                        with self.assertRaises(ValueError):
                            owner.apply(bad)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "requires Unicorn and pinned USA retail default.xbe")
class ApartmentAutosaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CompletionIntegrityTests.setUpClass()
        cls.payload = CompletionIntegrityTests.payload

    def prepare(self, m):
        code, data = career.legacy.allocations(self.payload)
        labels = career.code_for(code["va"], data["va"])[1]
        m.call(labels["init_menus"])
        m.put(data["va"] + 2672, m.MANAGER)
        m.put(m.MANAGER, labels["apartment"])
        m.put(0xAA2140, 0)  # An Apartment does not own a Coach's Desk scene.
        m.stub(0xF3E90, lambda: m.ret(1))
        m.native_save_services()
        m.ready()
        return labels

    def event(self, m):
        return m.call(0x6E4E0, args=(6,), ecx=m.MANAGER, edx=0)

    def test_commit_settle_pending_then_topmost_apartment_two_quiet_updates(self):
        with Machine(self.payload) as m:
            labels = self.prepare(m)
            m.put(m.state + 4, 0)
            m.put(0xA83A18, 2)
            m.put(0xE576B4, 0)
            m.put(0xE576BC, 0)
            trace = []
            for va in (0x1356C0, 0x134140):
                m.stub(va, lambda va=va: (trace.append(va), m.ret()))
            for va in (labels["settle"], 0xC4BC0):
                m.stub(va, lambda va=va: trace.append(va))
            m.call(0xC5D60)
            self.assertEqual(trace, [0x1356C0, 0x134140, labels["settle"], 0xC4BC0])
            self.assertEqual(m.get(m.state + 4), 1)
            self.assertEqual(m.events, [])
            self.event(m)
            self.assertNotIn("write", m.events)
            self.event(m)
            self.assertEqual(m.events.count("write"), 1)
            self.assertEqual(m.get(m.state + 24), 1)
            for _ in range(3):
                self.event(m)
            self.assertEqual(m.events.count("write"), 1)

    def test_apartment_missing_slot_and_failure_are_once_only_and_release_busy(self):
        for failure in ("slot", "allocation", "delete", "create", "write", "commit"):
            with self.subTest(failure=failure), Machine(self.payload) as m:
                self.prepare(m)
                if failure == "slot":
                    m.put(m.state + 12, 0)
                else:
                    m.native_save_services(fail=failure)
                for _ in range(2):
                    self.event(m)
                self.assertEqual(m.get(m.state + 24), 0)
                self.assertEqual(m.get(m.state + 8), 0)
                self.assertEqual(m.get(m.state + 4), 0)
                count = len(m.events)
                for _ in range(3):
                    self.event(m)
                self.assertEqual(len(m.events), count)

    def test_live_scene_child_and_io_busy_defer_then_require_two_fresh_updates(self):
        for address, value in ((0xA83A10, 1), (0xBDBDB0, 0), (0xBDBDA0, 3),
                               (Machine.MANAGER, 0x507EC8)):
            with self.subTest(address=hex(address)), Machine(self.payload) as m:
                self.prepare(m)
                original = m.get(address)
                self.event(m)
                m.put(address, value)
                # Direct callback checks its own top descriptor, even when the
                # caller has not dispatched through the Apartment event record.
                m.call("career_complete", ecx=m.MANAGER,
                       edx=career.code_for(*[r["va"] for r in career.legacy.allocations(self.payload)])[1]["apartment"])
                self.assertEqual(m.events, [])
                m.put(address, original)
                self.event(m)
                self.assertEqual(m.events, [])
                self.event(m)
                self.assertEqual(m.events.count("write"), 1)


if __name__ == "__main__":
    unittest.main()

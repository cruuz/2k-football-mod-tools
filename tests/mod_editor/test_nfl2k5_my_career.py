"""Standalone MyCareer writer, fixed save, ledger and composition contracts."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career as c, nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, draft_save, prepared


class SetupTests(unittest.TestCase):
    def test_fixed_prospect_replacement_and_cpu_draft(self):
        before = draft_save()
        result, setup, receipt = prepared()
        self.assertEqual(len(result), len(before))
        self.assertEqual(c.validate_state(c.read_setup(setup), result), c.read_setup(setup))
        self.assertEqual(receipt["class_count_before"], receipt["class_count_after"])
        doc = rr.RosterDocument(result, base=rr.find_block_base(result))
        self.assertEqual(doc.players[-1].display, "My Player")
        self.assertFalse(doc.players[-1].teams)
        self.assertNotIn(doc.players[-1].offset, doc.free_agents)
        self.assertEqual(doc.players[-1].record.get("years_pro"), 0)
        at = fs.SEASON_BLOCK + fs.S_USER_CONTROL
        self.assertEqual(result[at:at+136], bytes(136))
        self.assertEqual(result[fs.FRONT_OFFICE_BLOCK:], before[fs.FRONT_OFFICE_BLOCK:])
        self.assertFalse(receipt["runtime_witnessed"])

    def test_stage_identity_and_state_refusals(self):
        p = bytearray(draft_save())
        for stage in (0, 4, 6, 8):
            p[fs.SEASON_BLOCK + fs.S_STAGE] = stage
            with self.assertRaisesRegex(c.MyCareerError, "NFL Draft"):
                c.prepare(bytes(p), first="My", last="Player")
        _, setup, _ = prepared()
        state = bytearray(c.read_setup(setup))
        for offset, value in ((28, 4096), (32, 8), (36, 2), (60, 0x2012345), (72, 64), (76, 65), (88, 0x91000)):
            bad = bytearray(state)
            struct.pack_into("<I", bad, offset, value)
            with self.assertRaises(c.MyCareerError):
                c.validate_state(c.seal_state(bad))
        state[50] ^= 1
        with self.assertRaisesRegex(c.MyCareerError, "damaged"):
            c.validate_state(bytes(state))

    def test_weekly_ring_replay_watermark_and_zero_weeks(self):
        state = bytearray(c.read_setup(prepared()[1]))
        struct.pack_into("<I", state, 24, c.ACTIVE)
        state = c.seal_state(state)
        first = None
        for year in range(8):
            for week in range(18):
                state, receipt = c.award_week(state, year=year, stage=8, week=week, fixture=0,
                                              committed=True, appeared=week % 2 == 0)
                self.assertEqual(receipt["awarded"], 25 if week % 2 == 0 else 0)
                first = first or state
        self.assertEqual(struct.unpack_from("<I", state, 76)[0], 64)
        self.assertEqual(struct.unpack_from("<I", state, 64)[0], 8 * 9 * 25)
        replay, _ = c.award_week(state, year=0, stage=8, week=0, fixture=0, committed=True, appeared=True)
        self.assertEqual(replay, state)
        pending, _ = c.award_week(state, year=9, stage=8, week=0, fixture=0, committed=False, appeared=True)
        self.assertEqual(pending, state)

    def test_signed_output_atomic_no_source_changes_or_partial_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / "save.zip"
            payload = draft_save()
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("53450030/0001/SAVEGAME.DAT", payload)
                z.writestr("53450030/0001/EXTRA", rr.sign_save(payload))
                z.writestr("53450030/0001/SaveImage.xbx", b"unchanged thumbnail")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            result = c.prepare_save(source, root / "out", first="My", last="Player")
            out = rr.SaveContainer.load(root / "out/MyCareer.zip")
            self.assertTrue(out.verified)
            self.assertTrue(result["signed"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
            self.assertEqual(c.read_setup(root / "out/MyCareer.json"), c.read_setup(json.loads((root / "out/MyCareer.json").read_text())))
            with self.assertRaises(ValueError):
                c.prepare_save(source, root / "bad", first="", last="Player")
            self.assertFalse((root / "bad").exists())
            self.assertFalse(list(root.glob(".mycareer-*")))


class AnyPositionTests(unittest.TestCase):
    def test_every_retail_position_prepares_with_its_template_rule(self):
        for code in range(c.POSITION_COUNT):
            name = rr.position_name(code)
            choices = c.templates_for(code)
            with self.subTest(position=name):
                result, setup, receipt = prepared(code)
                doc = rr.RosterDocument(result, base=rr.find_block_base(result))
                player = doc.players[-1]
                self.assertEqual(player.record.get("position"), code)
                self.assertEqual(player.display, "My Player")
                self.assertEqual(player.record.get("years_pro"), 0)
                self.assertTrue(player.record.get("player_type") & 0x10)
                self.assertFalse(player.teams)
                state = c.read_setup(setup)
                self.assertEqual(c.position_of(state), code)
                self.assertEqual(setup["position"], name)
                self.assertTrue(c.starter_lock_of(state))
                self.assertEqual(struct.unpack_from("<I", state, c.STARTER_DONE_OFFSET)[0], 0)
                self.assertEqual(receipt["position_group"], c.position_group(code))
                self.assertIn(receipt["position_group"], c.POSITION_CONTRACT)
                self.assertEqual(len(result), len(draft_save(code)))
                if choices:
                    self.assertEqual(receipt["template"], choices[0].label)
                    self.assertEqual(choices[0].position_code, code)
                    self.assertEqual(len(choices), 3)
                else:
                    self.assertIsNone(receipt["template"])
                    self.assertIn("generated", receipt["ratings"])
                    self.assertIn(name, ("C", "G", "T", "DT", "DE"))

    def test_generated_ratings_are_kept_when_no_template_is_chosen(self):
        before = draft_save("WR")
        doc = rr.RosterDocument(before, base=rr.find_block_base(before))
        ratings = {k: doc.players[-1].record.get(k) for k in rr.RATING_BYTE_ORDER}
        result, _, receipt = prepared("WR", template=None)
        after = rr.RosterDocument(result, base=rr.find_block_base(result)).players[-1]
        self.assertEqual({k: after.record.get(k) for k in rr.RATING_BYTE_ORDER}, ratings)
        self.assertIsNone(receipt["template"])
        result, _, receipt = prepared("WR", template=2)
        after = rr.RosterDocument(result, base=rr.find_block_base(result)).players[-1]
        self.assertEqual(after.record.get("speed"), 80)
        self.assertEqual(receipt["template"], "Balanced WR")

    def test_template_position_and_starter_refusals(self):
        with self.assertRaisesRegex(c.MyCareerError, "3 retail templates"):
            prepared("DE", template=3)
        with self.assertRaisesRegex(c.MyCareerError, "3 retail templates"):
            prepared("QB", template=3)
        with self.assertRaises(rr.RosterRecordError):
            prepared("XX")
        with self.assertRaisesRegex(c.MyCareerError, "no unassigned eligible WR prospect"):
            c.prepare(draft_save("QB"), first="My", last="Player", position="WR", template=0)
        with self.assertRaisesRegex(c.MyCareerError, "starter lock"):
            prepared("QB", starter_lock=1)
        _, setup, _ = prepared("QB", starter_lock=False)
        self.assertFalse(c.starter_lock_of(c.read_setup(setup)))

    def test_state_bounds_cover_position_and_starter_flags(self):
        state = bytearray(c.read_setup(prepared("HB")[1]))
        bad = bytearray(state)
        bad[c.POSITION_OFFSET] = 17
        with self.assertRaisesRegex(c.MyCareerError, "17 retail"):
            c.validate_state(c.seal_state(bad))
        for offset in (c.STARTER_LOCK_OFFSET, c.STARTER_DONE_OFFSET):
            bad = bytearray(state)
            struct.pack_into("<I", bad, offset, 2)
            with self.assertRaisesRegex(c.MyCareerError, "starter lock"):
                c.validate_state(c.seal_state(bad))

    def test_v1_setup_is_refused_and_v2_label_must_match(self):
        _, setup, _ = prepared("CB")
        old = dict(setup)
        old["schema"] = "nfl2k5_my_career/v1"
        del old["position"]
        with self.assertRaisesRegex(c.MyCareerError, "predates position choice"):
            c.read_setup(old)
        wrong = dict(setup)
        wrong["position"] = "QB"
        with self.assertRaisesRegex(c.MyCareerError, "disagrees"):
            c.read_setup(wrong)
        described = c.describe_setup(c.read_setup(setup))
        self.assertEqual((described["position"], described["group"], described["starter_lock"]), ("CB", "DB", True))
        self.assertTrue(described["proved"].startswith("proved"))
        self.assertTrue(described["hypothesis"].startswith("hypothesis"))

    def test_menu_and_title_labels_equal_the_naming_owner_contract(self):
        from mod_editor.core import nfl2k5_modern_naming as naming
        for label, role in (("mode_text", "menu_row"), ("title_text", "screen_title")):
            at = c.assembly.LABELS[label]
            self.assertEqual(c.assembly.CODE[at:at + 20], naming.career_text(role, 20), label)
        self.assertLessEqual(len(c.assembly.CODE) + c.STATE_SIZE, c.CODE_SIZE)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE does not match the USA evidence pin")
        cls.patched, cls.receipt = c.apply(cls.retail, setup=prepared()[1])

    def test_status_replay_budget_and_menu_action(self):
        self.assertEqual(c.status(self.retail), "retail")
        self.assertEqual(c.status(self.patched), "applied")
        self.assertEqual(c.apply(self.patched)[0], self.patched)
        code, data = c.allocations(self.patched)
        self.assertLessEqual(self.receipt["content_bytes"], 8192)
        self.assertEqual(XbeImage(self.patched).read(data["va"], 4096), bytes(4096))
        im = XbeImage(self.patched)
        self.assertEqual(struct.unpack("<I", im.read(0x501494, 4))[0], 9)
        ptr = struct.unpack("<I", im.read(0x501498, 4))[0]
        self.assertEqual(im.read(ptr, 18).decode("utf-16le"), "MyCareer\0")
        self.assertTrue(code["va"] >= 0x14BA000)

    def test_mixed_hooks_context_and_changed_recipe_refuse(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for va in (0x156246, 0x15624C, 0xC73C4, c.allocations(self.patched)[0]["va"]):
            bad = bytearray(self.patched)
            at = c.rdata.offset_of(bad, va)
            bad[at] ^= 1
            for s in _sections(bad):
                bad[s.header_offset + 0x24:s.header_offset + 0x38] = section_digest(bad, s)
            self.assertEqual(c.status(bytes(bad)), "foreign", hex(va))
            with self.assertRaises(c.MyCareerError):
                c.apply(bytes(bad))
        _, other, _ = c.prepare(draft_save(), first="Other", last="QB")
        with self.assertRaisesRegex(c.MyCareerError, "setup changed"):
            c.apply(self.patched, setup=other)

    def test_shared_helper_only_accepts_verified_delegation(self):
        from mod_editor.core import nfl2k5_practice_squad as ps, nfl2k5_franchise_practice as fp
        from mod_editor.core import nfl2k5_practice_reserves as pr
        before = pr.apply(fp.apply(ps.apply(self.retail)[0])[0])[0]
        after = c.apply(before)[0]
        self.assertEqual(pr.status(after), "applied")
        self.assertEqual(pr.apply(after)[0], after)


if __name__ == "__main__":
    unittest.main()

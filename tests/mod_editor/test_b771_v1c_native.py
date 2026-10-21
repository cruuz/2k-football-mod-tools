"""Real v0.6 Anniversary regression proofs. No game or emulator is launched."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]
from tools.b77 import v1c_repair as repair
from mod_editor.core import nfl2k5_espn25_more_moments as moments
from mod_editor.core import nfl2k5_era_rules as era
from mod_editor.core import nfl2k5_espn25_rosters as rosters
from mod_editor.core import nfl2k5_roster_records as rr

DISC = Path(os.environ.get("B771_V06_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6 (2026-10-09).xiso.iso"))
RETAIL = Path("/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso")
# Independently read from each objective, rather than copied from user_side.
USER_TEAMS = ("packers raiders dolphins steelers raiders cowboys 49ers chargers 49ers redskins "
              "broncos 49ers cardinals 49ers bills broncos broncos bills chiefs bills broncos titans "
              "patriots 49ers eagles falcons giants steelers giants patriots vikings titans patriots "
              "patriots saints eagles seahawks 49ers ravens ravens cowboys patriots packers vikings "
              "eagles chiefs chiefs rams vikings chiefs bengals").split()


def decode(raw):
    body = raw[32:32 + struct.unpack_from("<I", raw, 4)[0]]
    out = []
    for i in range(struct.unpack_from("<I", body, 64)[0]):
        at = 0x44 + i * 0x6C
        text = lambda off: moments.sc.utf16(body, moments.sc.rel(body, at + off))
        u32 = lambda off: struct.unpack_from("<I", body, at + off)[0]
        out.append(dict(row=i + 1, title=text(0), goal=text(8), away=text(20), home=text(24),
                        user_side=u32(0x24), possession=u32(0x28)))
    return out


@unittest.skipUnless(DISC.is_file(), "shipped v0.6 disc fixture required (B771_V06_DISC)")
class NativeRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before_xbe = rosters.read_xbe(DISC)
        with rr._outer_image()(DISC) as image:
            cls.before_situ = image.read_entry(22)
        assert repair.sha(cls.before_xbe) == repair.V06_HASHES["default.xbe"]
        assert repair.sha(cls.before_situ) == repair.V06_HASHES["situation.iff"]
        cls.after_xbe, cls.xbe_receipt = repair.repair_xbe(cls.before_xbe)
        cls.after_situ, cls.situ_receipt = repair.repair_situation(cls.before_situ)

    def test_all_51_control_the_objective_team(self):
        before, after = decode(self.before_situ), decode(self.after_situ)
        self.assertEqual(len(after), len(USER_TEAMS))
        self.assertEqual([r["row"] for r, team in zip(before, USER_TEAMS)
                          if r["home" if r["user_side"] else "away"] != team], [34])
        for row, team in zip(after, USER_TEAMS):
            self.assertEqual(row["home" if row["user_side"] else "away"], team, row["title"])
        source = moments.Data.load()
        for row, authored in zip(after[25:], source.moments):
            self.assertEqual(row["user_side"], int(authored["user_side"] == "home"))

    def test_brady_start_matches_source_and_native_scalar_fields(self):
        authored = next(m for m in moments.Data.load().moments if m["id"] == "super_bowl_shootout")
        self.assertEqual((authored["user_side"], authored["possession"], authored["ball_on"], authored["clock"]),
                         ("home", "home", "NE 40", "1:08"))
        self.assertEqual(authored["score_now"], dict(away=29, home=29))
        self.assertEqual(authored["timeouts"], dict(away=2, home=3))
        for off, fmt, _before, value, label in repair.SITU_FIELDS:
            self.assertEqual(struct.unpack_from("<" + fmt, self.after_situ, repair.ROW34 + off)[0], value, label)

    def test_scoped_repairs_are_idempotent_and_preserve_stacked_bytes(self):
        self.assertTrue(self.xbe_receipt["outside_scope_identical"])
        self.assertTrue(self.situ_receipt["outside_scope_identical"])
        self.assertEqual(repair.repair_xbe(self.after_xbe)[0], self.after_xbe)
        self.assertEqual(repair.repair_situation(self.after_situ)[0], self.after_situ)
        stacked_xbe = bytearray(self.before_xbe)
        stacked_xbe[4] ^= 1  # an unowned byte in the XBE signature header
        fixed_xbe, receipt = repair.repair_xbe(bytes(stacked_xbe))
        self.assertEqual(fixed_xbe[4], stacked_xbe[4])
        self.assertTrue(receipt["outside_scope_identical"])
        stacked = bytearray(self.before_situ)
        stacked[32 + 0x44 + 0x68] ^= 1  # another moment's temperature
        fixed, _ = repair.repair_situation(bytes(stacked))
        self.assertEqual(fixed[32 + 0x44 + 0x68], stacked[32 + 0x44 + 0x68])
        mixed = bytearray(self.before_situ)
        struct.pack_into("<I", mixed, repair.ROW34 + 0x24, 1)
        with self.assertRaisesRegex(ValueError, "mixed or foreign"):
            repair.repair_situation(bytes(mixed))

    def test_foreign_new_site_is_refused_even_with_a_resealed_image(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        bad = bytearray(self.before_xbe)
        bad[XbeImage(self.before_xbe).offset(0x22DFF0, 7)] ^= 1
        with self.assertRaises(ValueError):
            repair.repair_xbe(era._seal(bad))

    def test_all_51_menu_selections_load_the_correct_user_side(self):
        if not RETAIL.is_file():
            self.skipTest("private retail disc required for native menu fixture")
        import nfl2k5_b77_menu_native as menu
        from nfl2k5_espn25_more_moments_native import FastMomentsCPU
        data = moments.Data.load()
        resources, context, identities, _situ, files, retail_situ = menu.disc_inputs(DISC, RETAIL, data)
        cpu = FastMomentsCPU(self.after_xbe, resources, context, identities,
            situ_chunk=self.after_situ[:32 + struct.unpack_from("<I", self.after_situ, 4)[0]], extra_files=files)
        rows = []
        for display in range(51):
            cpu.events.clear()
            cpu.select(display)
            physical = cpu.r(0xBF1858)
            record = cpu.run(0x20C6F0)
            opened = menu.record_fields(cpu, record)
            selected = opened["home" if opened["user_side"] else "away"][0]
            self.assertEqual(selected, USER_TEAMS[physical], opened["title"])
            rows.append(dict(display=display + 1, physical=physical + 1,
                             title=opened["title"], controlled_team=selected, user_side=opened["user_side"]))
            cpu.run(0x20C3C0)
        evidence = os.environ.get("B771_EVIDENCE")
        if evidence:
            (Path(evidence) / "native-moment-sides.json").write_text(json.dumps(rows, indent=2) + "\n", newline="\n")

    def test_drive_live_score_and_native_history_agree_at_the_event_root(self):
        from tests.mod_editor.test_nfl2k5_defensive_try import Machine, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESI, UC_X86_REG_EDX
        results = []
        for payload in (self.before_xbe, self.after_xbe):
            m = Machine(payload)
            m.stub(0xA1BC0)  # audio/notification callback, not scoring/history
            m.set(0xE5FF80, 8)
            m.set(0xBF1858, 10)  # physical The Drive
            m.set(m.get(m.TEAM[0] + 8), 19)  # 13 + touchdown
            m.run(0x22DFF0, registers={UC_X86_REG_EAX: m.RECORD, UC_X86_REG_ECX: m.PLAYER[0]})
            event = m.get(m.RECORD + 0x74)
            m.run(0x22E2D0, registers={UC_X86_REG_ESI: m.RECORD})
            live = m.get(m.get(m.TEAM[0] + 8))
            index = 127
            ring = 0xE57474 + index * 4
            m.set(0xE53800, index)
            m.set(ring, 1 << 26)  # touchdown drive, home scorer
            m.set(m.SNAPSHOT, 3)
            m.set(m.SNAPSHOT + 0x354, event)
            m.set(m.SNAPSHOT + 0x358, m.TEAM[0])
            m.set(m.SNAPSHOT + 0x35C, m.PLAYER[0])
            m.run(0xCD88A, registers={UC_X86_REG_EAX: ring, UC_X86_REG_ESI: m.SNAPSHOT}, stop=0xCD909)
            subtype = m.get(m.DRIVE + 0x1C)
            total = m.run(0x250360, registers={UC_X86_REG_ECX: 0, UC_X86_REG_EDX: 255})
            results.append(dict(event=event, live=live, subtype=subtype, points=total))
        self.assertEqual((results[0]["event"], results[0]["live"], results[0]["subtype"]), (5, 20, 2))
        self.assertEqual((results[1]["event"], results[1]["live"], results[1]["subtype"]), (4, 20, 1))
        self.assertEqual(results[0]["points"] + 13, 21)
        self.assertEqual(results[1]["points"] + 13, results[1]["live"])
        evidence = os.environ.get("B771_EVIDENCE")
        if evidence:
            (Path(evidence) / "drive-scoring.json").write_text(json.dumps(results, indent=2) + "\n", newline="\n")

    def test_consecutive_native_try_classification_all_eras_and_reentry(self):
        from tests.mod_editor.test_nfl2k5_defensive_try import Machine, UC_X86_REG_EAX, UC_X86_REG_ECX
        m = Machine(self.after_xbe)
        profiles = json.loads((ROOT / "data/nfl2k5_era_rules.json").read_text())["mappings"]
        # One machine, no FPU reset or reseeding between calls.
        cases = [(8, i, 5 if row["two_point_try"] else 4) for i, row in enumerate(profiles)]
        cases += [(4, 10, 5), (7, 10, 5), (8, 51, 5), (8, 0xFFFFFFFF, 5), (8, 10, 4)]
        for mode, ordinal, expected in cases * 2:
            m.set(0xE5FF80, mode)
            m.set(0xBF1858, ordinal)
            m.run(0x22DFF0, registers={UC_X86_REG_EAX: m.RECORD, UC_X86_REG_ECX: m.PLAYER[0]})
            self.assertEqual(m.get(m.RECORD + 0x74), expected, (mode, ordinal))
            self.assertEqual(m.get(m.RECORD + 0x78), m.PLAYER[0])
            self.assertEqual(m.get(m.RECORD + 0x7C), m.TEAM[0])
            self.assertEqual(m.get(m.RECORD), 2)

    def test_modern2_actual_try_selector_respects_the_era(self):
        if not RETAIL.is_file():
            self.skipTest("private retail playbook required")
        from tools.b77.p9_harness import Fixture
        from pb.verify_league import BOOK_ENTRIES
        from mod_editor.core import nfl2k5_play_scoring as scoring
        with rr._outer_image()(RETAIL) as image:
            book = image.read_entry(BOOK_ENTRIES["ARZ"])
        fixture = Fixture(self.after_xbe)
        fixture.load_book(book)
        native_call = fixture.call
        def persistent_call(pc, *, args=(), **registers):
            # The older harness resets x87 on every call. Pass its actual
            # persistent state instead, so consecutive calls expose leaks.
            fp = {name: fixture.m.reg_read(getattr(fixture.r, "UC_X86_REG_" + name))
                  for name in ("FPCW", "FPTAG", "FPSW")}
            fp.update(registers)
            return native_call(pc, args=args, **fp)
        fixture.call = persistent_call
        fixture.seed(0.5, 1)
        profiles = json.loads((ROOT / "data/nfl2k5_era_rules.json").read_text())["mappings"]
        rows = []
        for ordinal, profile in enumerate(profiles):
            fixture.state(phase=3, margin=-2, quarter=4, seconds=60, mode=8)
            fixture.put(0xBF1858, ordinal)
            top = fixture.m.reg_read(fixture.r.UC_X86_REG_FPSW) & 0x3800
            pointer = fixture.call(0x20B2E0, ecx=scoring.TEAM, edi=0)
            category = fixture.m.mem_read(pointer + 4, 1)[0] & 0x3F
            self.assertEqual(fixture.m.reg_read(fixture.r.UC_X86_REG_FPSW) & 0x3800, top)
            if not profile["two_point_try"]:
                self.assertEqual(category, 0x13, (ordinal + 1, profile["season"]))
            else:
                self.assertLessEqual(category, 10, (ordinal + 1, profile["season"]))
            rows.append(dict(row=ordinal + 1, season=profile["season"], two_point_try=profile["two_point_try"],
                             category=category))
        # The same actual selector goes for two after leaving Anniversary mode.
        fixture.state(phase=3, margin=-2, quarter=4, seconds=60, mode=7)
        pointer = fixture.call(0x20B2E0, ecx=scoring.TEAM, edi=0)
        self.assertLessEqual(fixture.m.mem_read(pointer + 4, 1)[0] & 0x3F, 10)
        evidence = os.environ.get("B771_EVIDENCE")
        if evidence:
            (Path(evidence) / "native-cpu-try-rules.json").write_text(json.dumps(rows, indent=2) + "\n", newline="\n")


if __name__ == "__main__":
    unittest.main()

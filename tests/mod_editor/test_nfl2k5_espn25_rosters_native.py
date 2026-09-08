"""All 25 retail moment selections with the patched 35-resource roster set.

Bounded native x86 only: archive I/O, controller, weather and presentation are
substituted, as documented in the source scenario trace. Not a played game.
"""
import gc
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "tools", ROOT / "tests"):
    sys.path.insert(0, str(directory))
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
from tests.mod_editor.test_nfl2k5_espn25_rosters import RETAIL
try:
    from nfl2k5_espn25_rosters_native import CPU, XBE_SHA256
    NATIVE_ERROR = None
except ImportError as exc:
    NATIVE_ERROR = str(exc)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NATIVE_ERROR:
            raise unittest.SkipTest("Unicorn unavailable: " + NATIVE_ERROR)
        for path in (RETAIL / "default.xbe", RETAIL / "vc_53450030/0"):
            if not path.is_file():
                raise unittest.SkipTest("user-owned retail evidence absent: " + str(path))
        if e.sha(e.read_bounded(RETAIL / "default.xbe", 16 * 1024**2)) != XBE_SHA256:
            raise unittest.SkipTest("retail USA XBE evidence pin differs")
        cls.manifest, cls.sheets = e.dataset()
        before = e.read_resources(RETAIL)
        if e.status(before) != "retail":
            raise unittest.SkipTest("retail USA ROST evidence pins differ")
        cls.resources, cls.receipt = e.apply(before)
        with rr._outer_image()(RETAIL) as archive:
            for i in (5, 22):
                entry = archive.entries[i]
                e.require(entry.size <= e.MAX_RESOURCE, "native context read exceeds bound")
                cls.resources[i] = archive.read_entry(i)
            cls.context = e.describe_context(cls.resources[5], cls.resources[22], archive.entries)

    def test_all_25_moments_load_106_correctly_encoded_players_and_keep_scalar_setup(self):
        results = []
        main_roster = rr.RosterDocument(self.resources[5][32:])
        for moment in self.manifest["moments"]:
            index = moment["moment"]
            with self.subTest(moment=index, title=moment["title"]):
                cpu = CPU(RETAIL / "default.xbe", self.resources, self.context["descriptors"])
                cpu.select(index)
                expected = [moment["sides"][side]["outer"] for side in ("home", "away")]
                self.assertEqual([event["outer"] for event in cpu.events], expected)
                self.assertEqual(cpu.read(0xBF185C, 108), cpu.read(cpu.SITU + e.RECORDS + index * e.STRIDE, 108))
                teams, player_count = [], 0
                for side, callback in (("home", 0x77B00), ("away", 0x77B40)):
                    outer = moment["sides"][side]["outer"]
                    document = rr.RosterDocument(self.resources[outer][32:])
                    team = cpu.run(callback)
                    teams.append(team)
                    self.assertEqual(cpu.read(team + rr.TEAM_PLAYER_COUNT, 1), b"\x35")
                    pointers = [cpu.r(team + i * 4) for i in range(53)]
                    self.assertEqual(len(set(pointers)), 53)
                    for pointer, source in zip(pointers, document.team_players(0)):
                        record = rr.PlayerRecord.decode(cpu.read(pointer, 84))
                        self.assertEqual((cpu.text(cpu.r(pointer + 16)), cpu.text(cpu.r(pointer + 20))),
                                         (source.first, source.last))
                        self.assertEqual((record.values["position"], record.values["jersey"]),
                                         (source.record.values["position"], source.record.values["jersey"]))
                        self.assertEqual(record.ratings(), {k: min(100, value) for k, value in source.record.ratings().items()})
                        for field in ("height", "weight_encoded", "face", "helmet", "face_mask", "body", "depth_rank", "depth_side"):
                            if field in source.record.values:
                                self.assertEqual(record.values[field], source.record.values[field], field)
                        self.assertEqual(record.skin, source.record.skin)
                        college_index = source.record.values["college_pointer"]
                        self.assertLess(college_index, len(main_roster.college_offsets))
                        self.assertEqual(cpu.r(pointer), cpu.MAIN + main_roster.college_offsets[college_index])
                        player_count += 1
                self.assertNotEqual(*teams)
                result = cpu.setup()
                b = self.resources[22][32:]
                at = e.RECORDS + index * e.STRIDE
                import struct
                self.assertEqual((result["away_score"], result["home_score"]), (e.u32(b, at + 0x2C), e.u32(b, at + 0x34)))
                self.assertEqual(result["quarter"], e.u32(b, at + 0x3C) + 1)
                self.assertEqual(result["clock_seconds"], struct.unpack_from("<f", b, at + 0x4C)[0])
                self.assertEqual(result["down"], e.u32(b, at + 0x48))
                self.assertEqual((result["away_timeouts"], result["home_timeouts"]), (e.u32(b, at + 0x50), e.u32(b, at + 0x54)))
                results.append({"moment": index, "title": moment["title"], "loaded": True,
                                "imported_players_checked": player_count, "archive_requests": cpu.events, "setup": result})
                del cpu
                gc.collect()
        self.assertEqual(len(results), 25)
        # Optional bounded proof receipt; CI has no checkout mutation by default.
        receipt = os.environ.get("ESPN25_NATIVE_RECEIPT")
        if receipt:
            Path(receipt).write_text(json.dumps({"evidence": e.EVIDENCE, "xbe_sha256": XBE_SHA256,
                "dataset_sha256": e.DATASET_SHA256, "instruction_budget_per_call": 2000000,
                "moments": results, "gameplay_witnessed": False}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

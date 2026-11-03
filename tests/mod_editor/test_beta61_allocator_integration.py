"""Integrated allocator, selection and UI contracts. No runtime gameplay claim."""
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build as build, nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_music_storage as music_storage
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_allocator_stack import LEGACY_REQUESTS, REQUESTS, compose

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
OPTIONS = dict(xbe_space=True, kickoff_relocated=True, scorebug_runtime=True, momentum=100,
               momentum_contact=True, defensive_try=True, zone_drop_cap=True,
               music_policy="jukebox_menus", music_unlock=True)


class SelectionTests(unittest.TestCase):
    def test_presets_clear_every_new_opt_in_and_recipe_keeps_integer_level(self):
        for name in build.PRESETS:
            plan = build.apply_preset(build.BuildPlan("source", "target", momentum=100,
                momentum_contact=True, defensive_try=True, zone_drop_cap=True), name)
            self.assertEqual((plan.momentum, plan.momentum_contact, plan.defensive_try, plan.zone_drop_cap),
                             (0, False, False, False))
            self.assertIs(type(plan.to_recipe()["momentum"]), int)
        for key, value in (("momentum", 25), ("defensive_try", True), ("zone_drop_cap", True)):
            self.assertTrue(build.BuildPlan("s", "t", **{key: value}).wants_xbe_patch())
            self.assertTrue(build.availability()[key])

    def test_invalid_options_refuse_before_reading_foreign_bytes(self):
        for options in (dict(momentum=True), dict(momentum=-1), dict(momentum=101),
                        dict(momentum_contact=True), dict(defensive_try=1), dict(zone_drop_cap="yes")):
            with self.subTest(options=options), self.assertRaises(ValueError):
                tt._apply_all(b"not a game", None, False, **options)

    def test_build_and_gameplay_level_controls_and_preset_reset(self):
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.build_panel_qt import BuildPanel
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel, PATCHES
        self.app = app = QApplication.instance() or QApplication([])
        for cls in (BuildPanel, GameplayPatchesPanel):
            panel = cls()
            self.addCleanup(panel.close)
            state = {key: "retail" for key, _label, _help in PATCHES}
            state.update(path="/tmp/source.iso", container="xiso", status="retail")
            panel.apply_state(state)
            panel.momentum_level.setCurrentIndex(3)
            boxes = panel._boxes() if isinstance(panel, BuildPanel) else panel.checks
            boxes["momentum_contact"].setChecked(True)
            self.assertEqual((panel.plan().momentum, panel.plan().momentum_contact), (100, True))
            boxes["momentum"].setChecked(False)
            self.assertEqual((panel.plan().momentum, panel.plan().momentum_contact), (0, False))
            boxes["momentum"].setChecked(True)
            self.assertEqual(panel.plan().momentum, 100)
            panel.momentum_level.setCurrentIndex(0)
            self.assertEqual(panel.plan().momentum, 0)
            self.assertFalse(boxes["accel_ramp"].isChecked())
            if isinstance(panel, BuildPanel):
                for name in build.PRESETS:
                    panel.apply_preset(name)
                    self.assertEqual(panel.plan().momentum, 0)
                    self.assertFalse(panel.plan().momentum_contact)
                    self.assertFalse(panel.plan().defensive_try)
                    self.assertFalse(panel.plan().zone_drop_cap)
                for key in ("momentum", "momentum_contact", "defensive_try", "zone_drop_cap"):
                    self.assertLessEqual(len(boxes[key].text()), 60)
        app.processEvents()


@unittest.skipUnless(RETAIL.is_file(), "private USA executable absent")
class CompleteOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.full, _ = compose(cls.retail)

    def test_capacity_permissions_metadata_and_stable_existing_addresses(self):
        layout = space.layout(self.full)
        regions = layout["regions"]
        self.assertEqual([r["size"] for r in regions if r["kind"] == "code"], [4096, 4096, 24 * 4096])
        # Beta 76: era rules add 2048 RX, stock books 1536 RX, and moment
        # venue labels 2304 RX to the previous 91879-byte union.
        self.assertEqual(sum(a["size"] for a in layout["allocations"] if a["kind"] == "code"), 116071)  # b780 p2-playcall: + 544 sprite scorebug code (5,376 -> 5,920: the ball spot and page boxes) = 116,071; b778 ai8: + 192 cpu_third_down (the pin was stale on the beta-78 base: 109,031); b779: + 352 camera code (512 -> 864, cm2 grew the camera code owner), + 512 K128 (1,024 -> 1,536, km1), + 5,632 champions code (hn1) = 115,527. Earlier history: b773 i4: + 3,040 = 512 moment coaches code (mo1) and the four named directory code spills (tap burst 512, draft picks 544, H-back 1024, team ratings 448); b772-vt1: + 5,120 coach AI code; b77-f4: + the 160 RX bytes of the letter grades owner; b77-f4b: + 16 for the progression row; b77-v1b: + 176 period goalposts (legacy RX tail); b77-f5: + 2,560 honors code (MyCareer footprint gap)
        # Era rules also add one 16-byte state allocation.
        self.assertEqual(sum(a["size"] for a in layout["allocations"] if a["kind"] == "data"), 85218)  # b775 mo2: + the 16-byte moment context state (legacy RW tail); b773 mo1: + the 512-byte moment coaches state; b772-vt1: + 128 coach AI state; b77-f5: + the 16-byte honors state block (legacy RW tail)
        image = XbeImage(self.full)
        for a in layout["allocations"]:
            section = image.section(a["va"], a["size"])
            self.assertNotEqual(section.name, ".text")
            if a["va"] >= space.POOL_VA:
                # b778-xs1 (shipped in beta-78, reached by this union since b779 km1/hn1 moved K128 and champions
                # whole into the pool): the v4 pool is ONE preloaded writable + executable section (flags 0x07,
                # like retail .data), so every row in it, of any kind, is writable and executable. It is the only
                # section where that holds; every row in the v3 runs keeps the strict rule below.
                self.assertEqual(section.flags, space.POOL_FLAGS)
                self.assertTrue(section.writable and section.executable)
                self.assertEqual(section.start, space.POOL_VA)
            else:
                self.assertEqual(section.writable, a["kind"] == "data")
                if a["kind"] == "read_only":
                    # b773 sp2/ro1/tr1: the named code spills in the allocator directory page make the shared general
                    # read-only section executable; the music storage section stays plain read-only. Never writable.
                    self.assertFalse(section.writable)
                else:
                    self.assertEqual(section.executable, a["kind"] == "code")
            if a["kind"] == "data":
                self.assertEqual(image.read(a["va"], a["size"]), bytes(a["size"]))
        self.assertEqual(image.section(music_storage.VA).raw, music_storage.RAW)
        self.assertEqual(self.full[space.LIB_COPY:space.LIB_COPY + space.LIB_END-space.LIB_START],
                         self.retail[space.LIB_START:space.LIB_END])
        for index, original in enumerate(XbeImage(self.retail).sections):
            self.assertEqual(image.sections[index].header, original.header)
            self.assertEqual(image.sections[index].start, original.start)
            self.assertEqual(image.sections[index].raw, original.raw)
        legacy_requests = tt.kickoff_relocated_patch.REQUESTS + tt.scorebug_runtime_patch.REQUESTS
        legacy = space.apply(self.retail, legacy_requests)[0]
        # Beta 71: the two-owner layout alone needs the scale region for the 4,096-byte sprite owner, so its file
        # is one page-aligned region longer than the beta-61 size; the full union still fits FILE_SIZE (asserted above).
        # Beta 76 s15: the 4,608-byte sprite owner no longer fits the 4 KiB code page at CODE_VA+126976, so the
        # two-owner layout opens the 24-page code region and its file is exactly as long as the full union's.
        self.assertEqual(len(legacy) - space.FILE_SIZE, 270336)
        # b778-xs1/b779 km1+hn1: the full union is a v4 image. K128 (1,536 B) and champions (5,632 B) sit whole in the
        # pool behind its directory page: 4,096 + 1,536 + 5,632 = 11,264 bytes = 3 pages appended to the v3 file.
        pool_bytes = space.plan(REQUESTS)["file_size"] - len(legacy)
        self.assertEqual(pool_bytes, 3 * space.PAGE)
        self.assertEqual(len(self.full), len(legacy) + pool_bytes)
        # Beta 71: the sprite scorebug owner's 4,096-byte code no longer fits the first cave after the kickoff
        # owner (it was 1,408 at CODE_VA+2656 through beta 70) and is allocated in the scale region after the union.
        # Beta 76 s15: at 4,608 bytes it starts the 24-page code region, and the region directory follows the union.
        self.assertEqual([a["va"] for a in space.layout(legacy)["allocations"]],
                         [space.CODE_VA, space.CODE_VA+704, space.DATA_VA, space.DATA_VA+16,
                          space.CODE_VA+131072, space.DATA_VA+307200])
        # the v3 rows only: the v4 pool holds a second allocator directory row (its document page) at POOL_VA
        full_sites = {(a["owner"], a["kind"]): a for a in layout["allocations"] if a["va"] < space.POOL_VA}
        for a in space.layout(legacy)["allocations"]:
            if a["owner"] == tt.scorebug_runtime_patch.OWNER and a["kind"] == "code":
                continue   # beta 71: the grown sprite owner sits after the union; the gates and the manifest pin it
            if a["owner"] == space.DIRECTORY_OWNER:
                # b773 sp2/ro1/tr1: the allocator's own directory page gives its tail to the named code spills, so its
                # reservation may shrink; where it starts never moves and no feature allocation moves.
                full_row = full_sites[a["owner"], a["kind"]]
                self.assertEqual({k: v for k, v in a.items() if k != "size"},
                                 {k: v for k, v in full_row.items() if k != "size"})
                self.assertLessEqual(full_row["size"], a["size"])
                continue
            self.assertEqual(a, full_sites[a["owner"], a["kind"]])
        self.assertEqual(compose(self.retail, reverse=True)[0], self.full)

    def test_extension_corruption_and_reconfiguration_fail_closed(self):
        for offset in (space.LIB_COPY, 0x164, space.CODE2_NAME, space.CODE2_REFS,
                       space.META_START+112, space.DIRECTORY+12, space.CODE2_RAW,
                       music_storage.RAW, space.DATA_RAW):
            bad = bytearray(self.full); bad[offset] ^= 1
            with self.subTest(offset=hex(offset)):
                self.assertEqual(space.status(bad), "foreign")
                with self.assertRaises(ValueError):
                    space.apply(bad, REQUESTS)
        with self.assertRaisesRegex(ValueError, "differ"):
            space.apply(self.full, tt.momentum_patch.REQUESTS)
        # The era and stock-book owners consume 3584 of the previous 3776
        # spare RX bytes. Venue labels occupy legacy tails. Pin the remaining
        # boundary, including alignment and the final late owners.
        # b779 (km1/hn1): K128 (1,536 B) and champions (5,632 B) no longer fit the v3 code run and live whole in the
        # v4 pool, so the run's last page holds letter_grades 160 (0x14F1CA0), its progression row 16, and cpu_third_down
        # 192, ending 0x14F1E10: 496 bytes of the run (end 0x14F2000) remain.
        overflow, _ = space.apply(self.retail, REQUESTS + (("extra", "code", 16, 16),))
        self.assertTrue(space.is_scaleout(overflow))
        self.assertEqual(space.status(overflow), "applied")
        # b778-xs1: what the v3 runs cannot hold goes whole to the v4 pool; every row still in v3 stays where it was
        # ("extra" is an ordinary owner: like any new ordinary owner in v3 it packs ahead of later owners.)
        v3 = space.plan(REQUESTS)
        self.assertEqual(v3["version"], 4)      # the complete union is itself a v4 image since ai8/km1/hn1
        run = space._scale_regions()[3]
        run_end = run["va"] + run["size"]

        def pooled(report):
            return [a["owner"] for a in sorted(report["allocations"], key=lambda a: a["va"])
                    if a["va"] >= space.POOL_VA and a["owner"] != space.DIRECTORY_OWNER]

        free = run_end - max(a["va"] + a["size"] for a in v3["allocations"]
                             if a["kind"] == "code" and run["va"] <= a["va"] < run_end)
        self.assertEqual(free, 144)  # b780 p2-playcall: the sprite scorebug grew 544 bytes and the third-down owner moved to the pool (496 -> 144)
        self.assertEqual(pooled(v3), ["nfl2k5_k128", "nfl2k5_champions", "nfl2k5_cpu_third_down"])  # b780 p2: third down falls to the pool
        self.assertEqual(pooled(space.plan(REQUESTS + (("extra", "code", 32, 16),))), pooled(v3))
        self.assertEqual(pooled(space.plan(REQUESTS + (("extra", "code", free, 16),))), pooled(v3))    # fills the run exactly
        # one aligned step more pushes the last late code owner of the run whole into the pool (b780 p2: third down is
        # already there, so the next one is letter_grades_progress)
        self.assertEqual(pooled(space.plan(REQUESTS + (("extra", "code", free + 16, 16),))),
                         ["nfl2k5_k128", "nfl2k5_letter_grades_progress", "nfl2k5_champions", "nfl2k5_cpu_third_down"])
        v4 = space.plan(REQUESTS + (("extra", "code", 98305, 16),))
        extra = next(a for a in v4["allocations"] if a["owner"] == "extra")
        self.assertEqual((v4["version"], extra["va"], extra["size"]), (4, space.POOL_VA + space.PAGE, 98305))
        # An ordinary owner is placed before the late ones, so it takes the pool's first slot and the pool's late
        # owners (k128, champions) follow it: they keep their allocation (owner, kind, size, align) and only their
        # pool address moves. Every v3 row keeps its complete record.
        self.assertTrue(all(a in v4["allocations"] for a in v3["allocations"]
                            if a["owner"] != space.DIRECTORY_OWNER and a["va"] < space.POOL_VA))
        self.assertEqual(pooled(v4), ["extra", "nfl2k5_k128", "nfl2k5_champions"])
        for old_row in (a for a in v3["allocations"] if a["va"] >= space.POOL_VA and a["owner"] != space.DIRECTORY_OWNER):
            moved = next(a for a in v4["allocations"] if (a["owner"], a["kind"]) == (old_row["owner"], old_row["kind"]))
            self.assertEqual({k: v for k, v in moved.items() if k not in ("va", "raw")},
                             {k: v for k, v in old_row.items() if k not in ("va", "raw")})
            self.assertGreater(moved["va"], extra["va"] + extra["size"] - 1)
        with self.assertRaisesRegex(ValueError, "capacity"):
            space.plan(REQUESTS + (("extra", "code", space.MAX_REQUEST_BYTES + 1, 16),))

    def test_dispatcher_and_raw_writer_status_roundtrip(self):
        patched, receipt = tt._apply_all(self.retail, None, False, accel_ramp=True, **OPTIONS)
        self.assertTrue(receipt["legacy_accel_ramp_disabled_by_momentum_profile"])
        self.assertEqual(tt.accel_ramp_patch.status(patched), "retail")
        self.assertEqual(tt._apply_all(patched, None, False, **OPTIONS)[0], patched)
        with self.assertRaisesRegex(ValueError, "different Momentum"):
            tt._apply_all(patched, None, False, **{**OPTIONS, "momentum": 50})
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/"source.xbe", Path(folder)/"target.xbe"
            source.write_bytes(self.retail)
            report = tt.write_xbe_copy(source, target, **OPTIONS)
            read = tt.read_xbe(target)
            for key in ("momentum", "momentum_contact", "defensive_try", "zone_drop_cap"):
                self.assertEqual(report[key], "applied")
                self.assertEqual(read[key], "applied")
            self.assertEqual(read["momentum_settings"]["momentum"], 100)
            self.assertEqual(source.read_bytes(), self.retail)

    def test_image_writer_and_reader_roundtrip_with_all_new_owners(self):
        from tests.mod_editor.test_nfl2k5_xbe_space import image_with_xbe
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/"source.iso", Path(folder)/"target.iso"
            original = image_with_xbe(self.retail)
            source.write_bytes(original)
            report = tt.write_image_copy(source, target, **{**OPTIONS, "scorebug_runtime": False})
            read = tt.read_image(target)
            for key in ("momentum", "momentum_contact", "defensive_try", "zone_drop_cap"):
                self.assertEqual(report[key], "applied")
                self.assertEqual(read[key], "applied")
            self.assertEqual(read["momentum_settings"]["momentum"], 100)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

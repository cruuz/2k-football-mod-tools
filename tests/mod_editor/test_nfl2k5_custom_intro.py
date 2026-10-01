"""Custom intro video: settings, archive injection (shrink, grow, restore), refusals and Build wiring."""
from dataclasses import replace
from pathlib import Path
import hashlib
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_custom_intro as custom, nfl2k5_intro_videos as boot  # noqa: E402
from mod_editor.core import nfl2k5_music_archive as archive, nfl2k5_sofdec as sofdec  # noqa: E402
from mod_editor.core import platform_compat as io  # noqa: E402
from mod_editor.core import mod_build, nfl2k5_build_settings as settings  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256  # noqa: E402
from tests.nfl2k5_my_career_fixture import XBE  # noqa: E402
from tests.nfl2k5_sofdec_fixture import synthetic_movie  # noqa: E402
from tests.nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_off_by_default_in_no_preset_and_saved_with_the_project(self):
        self.assertEqual(mod_build.BuildPlan("", "").custom_intro, "")
        for key in mod_build.PRESETS:
            chosen = mod_build.BuildPlan("", "", custom_intro="C:/movies/intro.mov")
            self.assertEqual(mod_build.apply_preset(chosen, key).custom_intro, "", key)
            self.assertEqual(mod_build.apply_preset(mod_build.BuildPlan("", ""), key).custom_intro, "", key)
        plan = mod_build.BuildPlan("source.iso", "output.iso", custom_intro="C:/movies/intro.mov")
        restored = settings.to_plan(settings.from_plan(plan), "new.iso", "out.iso")
        self.assertEqual(restored.custom_intro, "C:/movies/intro.mov")
        with self.assertRaises(ValueError):
            settings.build_settings({"custom_intro": 1})
        self.assertIn("custom_intro", mod_build.availability())
        self.assertFalse(plan.wants_xbe_patch())

    def test_refuses_the_trim_before_any_copy_and_takes_the_crib_cut(self):
        base = mod_build.BuildPlan("source.iso", "output.iso", custom_intro="intro.mov")
        self.assertEqual(mod_build.validate_plan(base), [])
        self.assertIn("Trim intro videos", mod_build.validate_plan(replace(base, trim_intro_videos=True))[0])
        self.assertEqual(mod_build.validate_plan(replace(base, crib_reclaim=True)), [])       # b76-f2
        self.assertIn("Trim intro videos", mod_build.validate_plan(
            replace(base, crib_reclaim=True, trim_intro_videos=True))[0])
        self.assertIn("Works with the Crib movie cut", custom.HELP_TEXT)

    def test_movie_file_must_obey_the_retail_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good, _ = synthetic_movie(3)
            (root / "good.mov").write_bytes(good)
            self.assertEqual(custom.read_movie(root / "good.mov"), good)
            crib, _ = synthetic_movie(2, width=256, height=144)
            (root / "crib.mov").write_bytes(crib)
            (root / "noise.mov").write_bytes(os.urandom(20480))
            (root / "empty.mov").write_bytes(b"")
            for name in ("crib.mov", "noise.mov", "empty.mov", "missing.mov"):
                with self.subTest(name), self.assertRaises(ValueError):
                    custom.read_movie(root / name)


class PackSizesTests(unittest.TestCase):
    """The shared writer's pack rule: F absorbs; a spill takes the rest from E, then D (b76-f2)."""

    RETAIL = (193710080, 299999232, 309252096, 315508736, 313178112, 307972096, 458231808, 319197184,
              929370112, 634941440, 310294528, 458248192, 315131904, 309135360, 301813760, 451733504)

    def test_retail_numbers_crib_cut_then_intro(self):
        end = sum(self.RETAIL)
        self.assertEqual(end, 6227718144)
        crib_end = end - 417122304
        cut = archive.pack_sizes(self.RETAIL, crib_end)
        self.assertEqual(cut, list(self.RETAIL[:-1]) + [34611200])
        both_end = crib_end - (50241536 - 9056256)
        with self.assertRaisesRegex(ValueError, "pack F"):
            archive.pack_sizes(cut, both_end)                               # the old refusal
        both = archive.pack_sizes(cut, both_end, spill=True)
        self.assertEqual(both[-1], 2048)
        self.assertEqual(both[-2], 301813760 - 6574080 - 2048)
        self.assertEqual(both[:-2], list(self.RETAIL[:-2]))
        self.assertEqual(sum(both), both_end)
        # a restore grows E back to the retail size and F takes the rest: the Crib-cut sizes
        self.assertEqual(archive.pack_sizes(both, crib_end, spill=True, reference=self.RETAIL), cut)
        self.assertEqual(archive.pack_sizes(both, crib_end, spill=True), list(both[:-1]) + [2048 + 41185280])

    def test_spill_walks_back_and_keeps_a_sector_per_pack(self):
        sizes = [8192] * 4
        self.assertEqual(archive.pack_sizes(sizes, 32768 - 6144), [8192, 8192, 8192, 2048])
        self.assertEqual(archive.pack_sizes(sizes, 32768 - 8192, spill=True), [8192, 8192, 6144, 2048])
        self.assertEqual(archive.pack_sizes(sizes, 12288, spill=True), [6144, 2048, 2048, 2048])
        with self.assertRaisesRegex(ValueError, "exceeds every pack"):
            archive.pack_sizes(sizes, 6144, spill=True)
        with self.assertRaisesRegex(ValueError, "pack F"):
            archive.pack_sizes(sizes, 32768 - 8192)
        with self.assertRaisesRegex(ValueError, "pack F"):
            archive.pack_sizes(sizes, 32768 + 2**31, spill=True)

    def test_reference_regrows_only_smaller_packs(self):
        grown = [12288, 8192, 2048, 2048]                      # pack 0 grew (a sprite scorebug disc)
        reference = [8192, 8192, 8192, 8192]
        self.assertEqual(archive.pack_sizes(grown, 12288 + 8192 + 8192 + 4096, reference=reference),
                         [12288, 8192, 8192, 4096])
        self.assertEqual(archive.pack_sizes(grown, 12288 + 8192 + 4096, spill=True, reference=reference),
                         [12288, 8192, 2048, 2048])
        with self.assertRaisesRegex(ValueError, "count"):
            archive.pack_sizes(grown, 32768, reference=reference[:3])

    def test_writer_rewrites_unchanged_outers_in_a_pack_whose_start_moved(self):
        from mod_editor.core import nfl2k5_music_banks as banks
        from tests.mod_editor.test_nfl2k5_music_archive_raw_layout import sixteen_pack_image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sixteen_pack_image(root)                         # 16 packs of 8 KiB, 8 outers
            source, output = root / "fixture.xiso.iso", root / "out.iso"
            output.write_bytes(source.read_bytes())
            replacement = b"\xab" * 16384
            with archive.Disc(source, descriptors=()) as disc:
                last = len(disc.archive_entries) - 1
                geometry = archive.layout(disc, {last: len(replacement)}, spill=True)
                self.assertEqual([p["size"] for p in geometry["packs"]], [2048] * 16)   # every pack spilled
                fd = os.open(output, os.O_RDWR | getattr(os, "O_BINARY", 0))
                try:
                    banks._write_archive(fd, disc, geometry, {last: replacement}, {}, lambda *_: None)
                finally:
                    os.close(fd)
                with archive.Disc(output, descriptors=()) as result:
                    for index in range(last):                  # same virtual offset, new pack and place
                        old, new = disc.archive_entries[index], result.archive_entries[index]
                        self.assertEqual(new.virtual_offset, old.virtual_offset)
                        self.assertNotEqual(result.entry_spans(new, 0, new.size),
                                            disc.entry_spans(old, 0, old.size))
                        self.assertEqual(result.outer_hash(index), disc.outer_hash(index))
                    entry = result.archive_entries[last]
                    self.assertEqual(result.read_entry_range(entry, 0, entry.size), replacement)


def boot_pins(big_intro):
    """Synthetic boot movies at 4293..4296 standing in for the retail pins."""
    rows = []
    for index, name, *_ in boot.MOVIES:
        raw = bytes([index % 251]) * (big_intro if index == custom.OUTER else 6144)
        rows.append((index, name, raw))
    return rows


class Fixture:
    """A 16-pack synthetic XISO; pack F is the last extent unless the XBE is appended after it."""

    def __init__(self, test, *, big_intro=6144, xbe=None):
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        entries = [(i, bytes([i % 251]) * 2048) for i in range(4323)]
        movies = []
        for index, name, raw in boot_pins(big_intro):
            entries[index] = (zlib.crc32(name.upper().encode("utf-16le")), raw)
            movies.append((index, name, len(raw), hashlib.sha256(raw).hexdigest()))
        patch = mock.patch.object(boot, "MOVIES", tuple(movies))
        patch.start()
        test.addCleanup(patch.stop)
        fx = SyntheticXiso(self.root, entries, pack_sizes=(0x90000,) * 16,
                           pack_sectors=tuple(64 + i * (0x90000 // 2048 + 1) for i in range(16)))
        self.source = fx.path
        # retail fills the bytes after the outer table with 0x9F; the writer must keep them
        end = archive.HEADER_SIZE + archive.ENTRY_SIZE * len(entries)
        with self.source.open("r+b") as f:
            f.seek(fx.pack_extent("0") + end)
            f.write(b"\x9f" * (archive.align_up(end) - end))
        if xbe is not None:
            fd = os.open(self.source, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                archive.write_named(fd, lambda n, at: io.pread(fd, n, at), 0, "default.xbe",
                                    lambda n, at: xbe[at:at + n], len(xbe))
            finally:
                os.close(fd)
        self.original = archive.file_hash(self.source)

    def movie(self, gops=3, name="custom.mov", **options):
        data, _ = synthetic_movie(gops, **options)
        path = self.root / name
        path.write_bytes(data)
        return path, data


class InjectionTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(boot, "status", return_value="retail")   # synthetic XBE stands in
        patch.start()
        self.addCleanup(patch.stop)

    def test_shrink_publishes_a_verified_copy_and_restore_is_byte_exact(self):
        fx = Fixture(self, big_intro=320 * 1024)
        path, movie = fx.movie(3)
        self.assertLess(len(movie), 320 * 1024)
        self.assertEqual(custom.image_status(fx.source), "retail")
        planned = custom.plan(fx.source, movie)
        self.assertEqual(planned["source_state"], "retail")
        self.assertEqual(planned["after"], dict(size=len(movie), sha256=hashlib.sha256(movie).hexdigest()))
        self.assertLess(planned["archive_delta_bytes"], 0)
        self.assertFalse(planned["pack_f_relocated"])
        output = fx.root / "custom.iso"
        receipt = custom.rebuild(fx.source, output, movie, expected_plan=planned)
        self.assertEqual(archive.file_hash(fx.source), fx.original)
        self.assertEqual(custom.image_status(output), "custom")
        check = receipt["verification"]
        self.assertEqual(check["outer_count"], 4322)
        self.assertTrue(check["all_retained_outer_hashes_verified"])
        self.assertEqual(check["header_stage"], dict(reads=[list(r) for r in sofdec.HEADER_STAGE_READS],
                                                     width=640, height=480))
        shrink = fx.source.stat().st_size - output.stat().st_size
        self.assertEqual(output.stat().st_size, planned["output_bytes"])
        self.assertEqual(shrink % 2048, 0)
        self.assertGreater(shrink, 0)
        with archive.Disc(output, descriptors=()) as disc:
            entry = disc.archive_entries[custom.OUTER]
            self.assertEqual(disc.read_entry_range(entry, 0, entry.size), movie)
        restored = fx.root / "restored.iso"
        back = custom.restore(output, restored, fx.source)
        self.assertEqual(back["plan"]["source_state"], "custom")
        self.assertEqual(archive.file_hash(restored), fx.original)      # the identical image
        self.assertFalse(list(fx.root.glob(".archive-*")))

    def test_growth_resizes_the_last_pack_in_place_and_restore_is_byte_exact(self):
        fx = Fixture(self)
        _, movie = fx.movie(4)
        output = fx.root / "grown.iso"
        receipt = custom.rebuild(fx.source, output, movie)
        planned = receipt["plan"]
        self.assertGreater(planned["archive_delta_bytes"], 0)
        self.assertFalse(planned["pack_f_relocated"])
        self.assertEqual(output.stat().st_size - fx.source.stat().st_size,
                         archive.align_up(len(movie)) - archive.align_up(6144))
        self.assertEqual(custom.image_status(output), "custom")
        again = fx.root / "again.iso"
        _, other = fx.movie(2, name="other.mov", slice_bytes=(2000, 900, 300))
        second = custom.rebuild(output, again, other)
        self.assertEqual(second["plan"]["source_state"], "custom")
        same = custom.rebuild(again, fx.root / "same.iso", other)
        self.assertTrue(same["plan"]["already_applied"])
        self.assertEqual(archive.file_hash(fx.root / "same.iso"), archive.file_hash(again))
        custom.restore(again, fx.root / "restored.iso", fx.source)
        self.assertEqual(archive.file_hash(fx.root / "restored.iso"), fx.original)

    def test_growth_relocates_the_last_pack_when_something_follows_it(self):
        fx = Fixture(self, xbe=b"XBEH" + bytes(40000))      # appended after pack F
        _, movie = fx.movie(3)
        receipt = custom.rebuild(fx.source, fx.root / "moved.iso", movie)
        self.assertTrue(receipt["plan"]["pack_f_relocated"])
        self.assertEqual(custom.image_status(fx.root / "moved.iso"), "custom")
        self.assertTrue(receipt["verification"]["all_retained_outer_hashes_verified"])

    def test_foreign_states_and_stale_plans_refuse(self):
        fx = Fixture(self)
        _, movie = fx.movie(3)
        planned = custom.plan(fx.source, movie)
        with self.assertRaisesRegex(ValueError, "stale"):
            custom.rebuild(fx.source, fx.root / "out.iso", movie, expected_plan={**planned, "source_bytes": 1})
        with mock.patch.object(boot, "status", return_value="applied"):
            with self.assertRaisesRegex(ValueError, "boot movie loop is not retail"):
                custom.plan(fx.source, movie)
            self.assertEqual(custom.image_status(fx.source), "foreign")
        with archive.Disc(fx.source, descriptors=()) as disc:
            other = disc.entry_spans(disc.archive_entries[4294], 0, 1)[0].xiso_offset
            intro = disc.entry_spans(disc.archive_entries[custom.OUTER], 0, 1)[0].xiso_offset
        changed = fx.root / "changed.iso"
        changed.write_bytes(fx.source.read_bytes())
        with changed.open("r+b") as f:
            f.seek(other)
            f.write(b"!")
        with self.assertRaisesRegex(ValueError, "vc.mov is not retail"):
            custom.plan(changed, movie)
        foreign = fx.root / "foreign.iso"
        foreign.write_bytes(fx.source.read_bytes())
        with foreign.open("r+b") as f:
            f.seek(intro)
            f.write(b"!")
        self.assertEqual(custom.image_status(foreign), "foreign")
        with self.assertRaisesRegex(ValueError, "foreign intro movie payload"):
            custom.rebuild(foreign, fx.root / "out.iso", movie)
        self.assertFalse((fx.root / "out.iso").exists())
        with self.assertRaisesRegex(ValueError, "not the pinned retail"):
            custom.retail_intro(foreign)

    def test_verification_failure_keeps_the_destination_and_nonposix_publication_matches(self):
        from tests.mod_editor.test_shipped_tools_posix_only import simulated_non_posix
        fx = Fixture(self)
        _, movie = fx.movie(3)
        dest = fx.root / "out.iso"
        dest.write_bytes(b"keep")
        with mock.patch.object(custom, "verify", side_effect=ValueError("forced verification failure")):
            with self.assertRaisesRegex(ValueError, "forced"):
                custom.rebuild(fx.source, dest, movie, overwrite=True)
        self.assertEqual(dest.read_bytes(), b"keep")
        with self.assertRaises(ValueError):
            custom.rebuild(fx.source, fx.source, movie, overwrite=True)
        with simulated_non_posix():
            custom.rebuild(fx.source, fx.root / "windows.iso", movie)
        custom.rebuild(fx.source, fx.root / "posix.iso", movie)
        self.assertEqual(archive.file_hash(fx.root / "windows.iso"), archive.file_hash(fx.root / "posix.iso"))
        self.assertEqual(archive.file_hash(fx.source), fx.original)
        self.assertFalse(list(fx.root.glob(".archive-*")))

    def test_build_writes_the_movie_last_and_off_never_runs(self):
        fx = Fixture(self)
        path, movie = fx.movie(3)
        plan = mod_build.BuildPlan(str(fx.source), str(fx.root / "built.iso"), custom_intro=str(path),
                                   camera=False, catch_slider=False, accel_ramp=False)
        with mock.patch.object(mod_build, "inspect", return_value={"container": "xiso"}), \
             mock.patch.object(mod_build.tt, "_check_installed_runtime_settings"), \
             mock.patch.object(mod_build.tt, "_naming_source_preflight"), \
             mock.patch.object(mod_build.tt, "_grown_status_fields", return_value={}), \
             mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
            receipt = mod_build.build(plan)
            self.assertEqual(receipt["result"]["custom_intro"], "applied")
            self.assertEqual(receipt["custom_intro_after"]["sha256"], hashlib.sha256(movie).hexdigest())
            self.assertEqual(receipt["custom_intro_before"]["size"], 6144)
            step = next(s for s in receipt["steps"] if s["step"] == "custom_intro")
            self.assertNotIn("layout", step["plan"])
            self.assertEqual(custom.image_status(fx.root / "built.iso"), "custom")
            with mock.patch.object(custom, "finish_output", side_effect=AssertionError("off must not write")):
                off = mod_build.build(replace(plan, target=str(fx.root / "off.iso"), custom_intro=""))
            self.assertNotIn("custom_intro_after", off)
            (fx.root / "bad.mov").write_bytes(b"not a movie" * 400)
            with self.assertRaisesRegex(ValueError, "retail Sofdec rule"):
                mod_build.build(replace(plan, target=str(fx.root / "bad.iso"), custom_intro=str(fx.root / "bad.mov")))
            self.assertFalse((fx.root / "bad.iso").exists())
        self.assertFalse(list(fx.root.glob(".studio-build-*")))


class PanelTests(unittest.TestCase):
    """The Build page row: off, carries the movie only when ticked, saved with the project."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PyQt5 is absent")
        cls.app = QApplication.instance() or QApplication([])

    def test_custom_intro_row(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        panel = BuildPanel()
        try:
            self.assertEqual(panel.custom_intro_check.text(), custom.BUILD_CAPTION)
            self.assertEqual(panel.plan().custom_intro, "")
            with tempfile.TemporaryDirectory() as temp:
                movie, _ = synthetic_movie(3)
                good = Path(temp) / "intro.mov"
                good.write_bytes(movie)
                for widget in (panel.custom_intro_check, panel.custom_intro_field, panel.custom_intro_button):
                    widget.setEnabled(True)
                panel.custom_intro_field.setText(str(good))
                self.assertEqual(panel.plan().custom_intro, "")          # typed but not ticked: off
                panel.set_custom_intro(str(good))
                self.assertEqual(panel.plan().custom_intro, str(good))
                self.assertTrue(panel.has_work())
                self.assertIn(custom.BUILD_CAPTION, panel.selected_labels())
                self.assertEqual(panel._custom_intro_problem(), "")
                saved = panel.project_build_settings()
                self.assertEqual(saved["custom_intro"], str(good))
                panel.custom_intro_check.setChecked(False)
                panel.custom_intro_field.setText("")
                panel.restore_project_build_settings(saved)
                self.assertEqual(panel.plan().custom_intro, str(good))
                panel.custom_intro_field.setText(str(Path(temp) / "missing.mov"))
                self.assertIn("not found", panel._custom_intro_problem())
                noise = Path(temp) / "noise.mov"
                noise.write_bytes(b"x" * 20480)
                panel.custom_intro_field.setText(str(noise))
                self.assertIn("cannot be used", panel._custom_intro_problem())
        finally:
            panel.deleteLater()


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class RetailTests(unittest.TestCase):
    """With the real executable: its boot loop must be retail, and it is never changed."""

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE differs from the USA evidence pin")

    def test_real_executable_boot_loop_gate(self):
        fx = Fixture(self, xbe=self.retail)
        _, movie = fx.movie(3)
        receipt = custom.rebuild(fx.source, fx.root / "custom.iso", movie)
        self.assertEqual(custom.image_status(fx.root / "custom.iso"), "custom")
        self.assertTrue(receipt["plan"]["pack_f_relocated"])                  # the XBE follows pack F here
        trimmed = Fixture(self, xbe=boot.apply(self.retail)[0])
        self.assertEqual(custom.image_status(trimmed.source), "foreign")
        with self.assertRaisesRegex(ValueError, "boot movie loop is not retail"):
            custom.plan(trimmed.source, movie)


class CribFixture:
    """A 16-pack synthetic XISO in the retail order: the real XBE, then the packs back to back, then a
    2 KiB tail after pack F (retail has 14 KiB).  The 23 Crib movies (24 KiB each) and the four boot
    movies (the intro 320 KiB) sit at their retail indices, standing in for the pinned ones.  The
    Crib cut alone fits in pack F (655,360 -> 137,216 bytes); a 110,592-byte intro after it frees
    217,088 more, so the shrink spills 81,920 bytes into pack E (b76-f2).  ``xbe_last`` appends the
    XBE after pack F instead, so E and F are not the disc's last extents."""

    PACK = 0xA0000
    CRIB_MOVIE = 24576

    def __init__(self, test, xbe, *, xbe_last=False):
        from mod_editor.core import nfl2k5_crib_reclaim as crib
        from mod_editor.core.nfl2k5_depth_chart_storage import image_file_node
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        entries = [(i, bytes([i % 251]) * 2048) for i in range(4323)]
        pins = {}
        for module, rows in ((boot, boot_pins(320 * 1024)),
                             (crib, [(i, name, bytes([i % 251]) * self.CRIB_MOVIE) for i, name, *_ in crib.MOVIES])):
            pins[module] = []
            for index, name, raw in rows:
                entries[index] = (zlib.crc32(name.upper().encode("utf-16le")), raw)
                pins[module].append((index, name, len(raw), hashlib.sha256(raw).hexdigest()))
            patch = mock.patch.object(module, "MOVIES", tuple(pins[module]))
            patch.start()
            test.addCleanup(patch.stop)
        first = 64 if xbe_last else 35 + -(-len(xbe) // 2048)
        fx = SyntheticXiso(self.root, entries, pack_sizes=(self.PACK,) * 16,
                           pack_sectors=tuple(first + i * (self.PACK // 2048) for i in range(16)))
        self.source = fx.path
        end = archive.HEADER_SIZE + archive.ENTRY_SIZE * len(entries)
        fd = os.open(self.source, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            io.pwrite(fd, b"\x9f" * (archive.align_up(end) - end), fx.pack_extent("0") + end)
            read = lambda n, at: io.pread(fd, n, at)
            if xbe_last:
                archive.write_named(fd, read, 0, "default.xbe", lambda n, at: xbe[at:at + n], len(xbe))
            else:   # in its own slot before the packs, as on retail
                node, _, _ = image_file_node(read, 0, os.fstat(fd).st_size, "default.xbe")
                archive.write_all(fd, xbe, 35 * 2048)
                archive.write_all(fd, struct.pack("<II", 35, len(xbe)), node)
        finally:
            os.close(fd)
        self.original = archive.file_hash(self.source)

    def movie(self, gops=3):
        data, _ = synthetic_movie(gops)
        return data


def pack_extents(path):
    with archive.Disc(path, descriptors=()) as disc:
        return {p.name: (disc.pack_extents[p.name].byte_offset, p.size, p.virtual_start) for p in disc.packs}


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class CribCutTests(unittest.TestCase):
    """b76-f2: the Crib movie cut and the custom intro on one disc, in either order, with an exact restore."""

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE differs from the USA evidence pin")

    def test_cut_then_intro_spills_into_pack_e_restores_exactly_and_order_does_not_matter(self):
        from mod_editor.core import nfl2k5_crib_reclaim as crib
        fx = CribFixture(self, self.retail)
        movie = fx.movie(3)
        cut = fx.root / "cut.iso"
        crib.rebuild(fx.source, cut)
        before = pack_extents(cut)
        self.assertEqual(before["F"][1], fx.PACK - 23 * (fx.CRIB_MOVIE - 2048))
        self.assertEqual(before["E"][1], fx.PACK)
        self.assertEqual(before["E"][0] + before["E"][1], before["F"][0])
        self.assertEqual(cut.stat().st_size, before["F"][0] + before["F"][1])     # the cut drops the tail

        planned = custom.plan(cut, movie)
        shrink = 320 * 1024 - len(movie)
        self.assertGreater(shrink, before["F"][1])                             # more than F holds
        spilled = shrink - before["F"][1] + 2048
        self.assertEqual(planned["packs_resized"], {"E": dict(before=fx.PACK, after=fx.PACK - spilled),
                                                    "F": dict(before=before["F"][1], after=2048)})
        self.assertEqual(planned["layout"]["resized_packs"], ["E"])
        both = fx.root / "both.iso"
        receipt = custom.rebuild(cut, both, movie, expected_plan=planned)
        after = pack_extents(both)
        self.assertEqual(after["E"][:2], (before["E"][0], fx.PACK - spilled))  # resized where it is
        self.assertEqual(after["F"][:2], (before["E"][0] + fx.PACK - spilled, 2048))
        self.assertEqual(after["F"][2], after["E"][2] + after["E"][1])
        self.assertEqual({k: v for k, v in after.items() if k not in "EF"},
                         {k: v for k, v in before.items() if k not in "EF"})
        self.assertEqual(both.stat().st_size, cut.stat().st_size - shrink)
        self.assertEqual(receipt["verification"]["outer_count"], 4322)
        self.assertEqual(custom.image_status(both), "custom")
        self.assertTrue(crib.plan(both)["already_applied"])
        with archive.Disc(both, descriptors=()) as disc:
            entry = disc.archive_entries[custom.OUTER]
            self.assertEqual(disc.read_entry_range(entry, 0, entry.size), movie)

        back = custom.restore(both, fx.root / "restored.iso", fx.source)
        self.assertEqual(back["plan"]["reference_pack_sizes"], [fx.PACK] * 16)
        self.assertEqual(archive.file_hash(fx.root / "restored.iso"), archive.file_hash(cut))   # the Crib-cut disc

        # the other order: the intro on the source (F in place, the tail kept), then the cut spills
        custom.rebuild(fx.source, fx.root / "intro.iso", movie)
        second = crib.plan(fx.root / "intro.iso")
        self.assertEqual(second["layout"]["resized_packs"], ["E"])
        crib.rebuild(fx.root / "intro.iso", fx.root / "intro_cut.iso")
        self.assertEqual(archive.file_hash(fx.root / "intro_cut.iso"), archive.file_hash(both))
        self.assertEqual(archive.file_hash(fx.source), fx.original)
        self.assertFalse(list(fx.root.glob(".archive-*")))

    def test_spill_in_place_when_e_and_f_are_not_the_last_extents(self):
        from mod_editor.core import nfl2k5_crib_reclaim as crib
        fx = CribFixture(self, self.retail, xbe_last=True)
        movie = fx.movie(3)
        cut = fx.root / "cut.iso"
        crib.rebuild(fx.source, cut)
        before = pack_extents(cut)
        both = fx.root / "both.iso"
        receipt = custom.rebuild(cut, both, movie)
        self.assertNotIn("tail", receipt["plan"]["layout"])                      # the XBE follows F
        after = pack_extents(both)
        self.assertEqual((after["E"][0], after["F"][0]), (before["E"][0], before["F"][0]))   # shrunk in place
        self.assertEqual(after["F"][1], 2048)
        self.assertEqual(both.stat().st_size, cut.stat().st_size)
        restored = fx.root / "restored.iso"
        back = custom.restore(both, restored, fx.source)
        self.assertEqual(back["verification"]["state"], "retail")
        grown = pack_extents(restored)
        self.assertEqual({k: v[1:] for k, v in grown.items()}, {k: v[1:] for k, v in before.items()})
        self.assertGreater(grown["E"][0], before["F"][0])                       # grown packs relocate
        self.assertEqual(custom.image_status(restored), "retail")
        self.assertTrue(crib.plan(restored)["already_applied"])

    def test_build_takes_both_options(self):
        fx = CribFixture(self, self.retail)
        movie = fx.movie(3)
        path = fx.root / "custom.mov"
        path.write_bytes(movie)
        plan = mod_build.BuildPlan(str(fx.source), str(fx.root / "built.iso"), custom_intro=str(path),
                                   crib_reclaim=True, camera=False, catch_slider=False, accel_ramp=False)
        with mock.patch.object(mod_build, "inspect", return_value={"container": "xiso"}), \
             mock.patch.object(mod_build.tt, "_check_installed_runtime_settings"), \
             mock.patch.object(mod_build.tt, "_naming_source_preflight"), \
             mock.patch.object(mod_build.tt, "_grown_status_fields", return_value={}), \
             mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True}):
            receipt = mod_build.build(plan)
        steps = [s["step"] for s in receipt["steps"]]
        self.assertLess(steps.index("crib_reclaim"), steps.index("custom_intro"))
        self.assertEqual(receipt["result"]["custom_intro"], "applied")
        intro = next(s for s in receipt["steps"] if s["step"] == "custom_intro")
        self.assertEqual(intro["plan"]["packs_resized"]["F"]["after"], 2048)
        from mod_editor.core import nfl2k5_crib_reclaim as crib
        self.assertEqual(custom.image_status(fx.root / "built.iso"), "custom")
        self.assertTrue(crib.plan(fx.root / "built.iso")["already_applied"])
        self.assertFalse(list(fx.root.glob(".studio-build-*")))


if __name__ == "__main__":
    unittest.main()

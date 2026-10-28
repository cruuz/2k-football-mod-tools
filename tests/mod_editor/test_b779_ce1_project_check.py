"""b779-ce1: "Check my project" (mod_editor.core.nfl2k5_project_check). Small synthetic projects; no game data."""
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_project_check as pc  # noqa: E402
from mod_editor.core.nfl2k5_uniform_equipment_writer import load_targets  # noqa: E402


def sock_id(selector, chunk=4, reference=0, name="socks00"):
    for target in load_targets()[0].values():
        if target.set_selector == selector and target.chunk_index == chunk and target.reference_index == reference:
            return target.asset_id
    raise AssertionError(selector)


class ReportText(unittest.TestCase):
    def test_a_clean_report_says_nothing_has_to_change(self):
        report = pc.Report(steps=["Build options"], seconds=3)
        self.assertTrue(report.ok)
        self.assertIn("nothing has to be changed or unticked", report.text())

    def test_a_stop_is_numbered_and_says_what_to_do(self):
        report = pc.Report(findings=[pc.Finding(pc.STOP, "Stadium boards", "Boards conflict with your stadium edits.",
                                                "Dolphins", "Turn off Modern stadium boards."),
                                     pc.Finding(pc.NOTE, "Kits", "Kit K1 reads an edited kit.", "18A0 chunk 4.")],
                           steps=["a", "b"], seconds=1)
        text = report.text()
        self.assertFalse(report.ok)
        self.assertIn("1. Boards conflict with your stadium edits.", text)
        self.assertIn("What to do: Turn off Modern stadium boards.", text)
        self.assertIn("What Build will do with your work (no action needed):", text)
        self.assertEqual(report.as_dict()["ok"], False)
        self.assertEqual(report.as_dict()["findings"][0]["severity"], "stop")
        self.assertNotIn("—", text)


class Checks(unittest.TestCase):
    def plan(self, **kw):
        return mod_build.BuildPlan("/never/read.iso", "/never/written.iso", **kw)

    def test_incompatible_options_are_a_stop_that_names_them(self):
        plan = self.plan(custom_intro="movie.mp4", trim_intro_videos=True)
        report = pc.check(plan, run_preflight=False)
        self.assertEqual([f.area for f in report.stops], ["Build options"])
        self.assertIn("Custom intro video or Trim intro videos", report.stops[0].title)
        self.assertTrue(report.stops[0].fix)

    def test_a_stadium_edit_with_the_boards_is_a_stop_that_says_what_to_untick(self):
        from mod_editor.core import nfl2k5_board_kit as boards
        venue = boards.pinned_venues()[0]
        outer = next(iter(boards._venue_pins(venue).values()))["outer"]
        document = {"edits": [{"kind": "stadium_texture", "target": f"nfl2k5.stadium.o{outer}.x"}]}
        report = pc.check(self.plan(modern_board_kit=True), document=document, run_preflight=False)
        self.assertEqual([f.area for f in report.stops], ["Stadium boards"])
        self.assertIn("Turn off Modern stadium boards", report.stops[0].fix)
        self.assertTrue(pc.check(self.plan(modern_board_kit=False), document=document, run_preflight=False).ok)

    def test_equipment_that_needs_a_refit_is_a_note_because_build_refits_it(self):
        rows = [dict(asset_id="tset:3613:4:0:socks00", fit_status="needs refit"),
                dict(asset_id="tset:3613:4:1:socks00_mud", fit_status="fits")]
        report = pc.check(self.plan(), fit_rows=rows, run_preflight=False)
        self.assertTrue(report.ok)
        self.assertEqual(len(report.notes), 1)
        self.assertIn("tset:3613:4:0:socks00", report.notes[0].detail)
        self.assertNotIn("tset:3613:4:1", report.notes[0].detail)

    def test_the_source_preflight_refusal_is_a_stop_with_the_whole_sentence(self):
        message = "Modern stadium boards need a disc image. Choose your unmodified USA retail image."
        with mock.patch.object(mod_build, "preflight_plan", side_effect=ValueError(message)):
            report = pc.check(self.plan())
        self.assertEqual([f.area for f in report.stops], ["Disc and options"])
        self.assertEqual(report.stops[0].title, message)

    def test_the_source_preflight_is_skipped_on_request(self):
        with mock.patch.object(mod_build, "preflight_plan", side_effect=AssertionError("must not run")):
            self.assertTrue(pc.check(self.plan(), run_preflight=False).ok)


class KitMap(unittest.TestCase):
    def test_edited_kit_chunks_map_sock_edits_to_their_package_and_chunk(self):
        ids = [sock_id("14H8"), sock_id("14H8", reference=1), "tset:999999:4:0:socks00",
               "nfl2k5.uniform.14h9.pants", "nfl2k5.stadium.o1.x"]
        chunks, packages = pc.edited_kit_chunks(ids)
        self.assertEqual(sorted(chunks), [("14H8", 4)])
        self.assertEqual(len(chunks[("14H8", 4)]), 2)
        self.assertEqual(packages, {"14H8", "14H9"})

    def test_a_new_kit_that_reads_an_edited_chunk_gets_a_note_naming_both(self):
        doc = {"kits": [
            {"id": "K1", "team": "NYG", "code": "18", "style": 9,
             "sides": {"H": {"base": "18H8"}, "A": {"base": "18A8", "chunks": {"4": "18A0", "13-14": "18A0"}}}},
            {"id": "K2", "team": "DAL", "code": "07", "style": 10, "sides": {"H": {"base": "07H0"}, "A": {"base": "07A0"}}}]}
        notes = pc.moment_kit_notes([("Anniversary moment kits", doc)], {("18A0", 4): ["x"], ("18A0", 20): ["y"]})
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].severity, pc.NOTE)
        self.assertIn("K1", notes[0].title)
        self.assertIn("18A0 chunk 4", notes[0].detail)
        self.assertNotIn("chunk 20", notes[0].detail)         # chunk 20 is not read from 18A0 by K1
        self.assertEqual(pc.moment_kit_notes([("x", doc)], {}), [])

    def test_a_base_kit_chunk_counts_as_read(self):
        doc = {"kits": [{"id": "K1", "team": "NYG", "code": "18", "style": 9,
                         "sides": {"H": {"base": "18H8"}, "A": {"base": "18A8"}}}]}
        notes = pc.moment_kit_notes([("x", doc)], {("18A8", 8): ["tset:1:8:0:shoes01"]})
        self.assertIn("18A8 chunk 8", notes[0].detail)

    def test_the_shipped_documents_produce_notes_only_for_edited_donors(self):
        from mod_editor.core import nfl2k5_moment_kits as kits
        notes = pc.moment_kit_notes([("Anniversary moment kits", kits.document())], {("18A0", 4): ["x"]})
        self.assertEqual(len(notes), 1)
        self.assertIn("K1", notes[0].title)


class Archive(unittest.TestCase):
    def archive(self, folder, settings=None):
        path = Path(folder) / "p.2k5mod"
        manifest = {"schema": "2k5_mod_studio_project/v1", "game": "espn_nfl_2k5_xbox",
                    "payload_policy": "user-replacements-only", "build_settings": settings or {},
                    "edits": [{"asset_id": sock_id("14H8"), "file": "replacements/a.png", "png_sha256": "0" * 64,
                               "rgba_sha256": "0" * 64},
                              {"asset_id": "nfl2k5.stadium.o3138.scene", "file": "replacements/b.png",
                               "png_sha256": "0" * 64, "rgba_sha256": "0" * 64}],
                    "fit_receipts": {"0" * 64: [{"asset_id": sock_id("14H8"), "fit_status": "needs refit"}]},
                    "uniform_colors": []}
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("project.json", json.dumps(manifest))
        return path

    def test_read_archive_returns_ids_document_and_fit_rows_without_extracting(self):
        with tempfile.TemporaryDirectory() as folder:
            data = pc.read_archive(self.archive(folder))
            self.assertEqual(len(data["asset_ids"]), 2)
            self.assertEqual([e["kind"] for e in data["document"]["edits"]], ["texture", "stadium_texture"])
            self.assertEqual(data["fit_rows"][0]["fit_status"], "needs refit")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["p.2k5mod"])

    def test_command_line_exit_code_follows_the_stops_and_writes_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.archive(folder)
            out = Path(folder) / "report.json"
            argv = [str(path), "--source", str(Path(folder) / "retail.iso"), "--json", str(out), "--no-source-preflight"]
            with mock.patch("builtins.print"):
                self.assertEqual(pc.main(argv), 0)
            self.assertTrue(json.loads(out.read_text(encoding="utf-8"))["ok"])
            bad = self.archive(folder, {"custom_intro": "m.mp4", "trim_intro_videos": True})
            with mock.patch("builtins.print"):
                self.assertEqual(pc.main([str(bad), "--source", str(Path(folder) / "r.iso"), "--no-source-preflight"]), 1)


class DryRun(unittest.TestCase):
    """The user's edited chunks are compiled into the donors, then the new kits are composed from them."""

    SPAN = 10

    @staticmethod
    def span(video=100, flag=0, kind=b"T"):
        import struct
        return kind + struct.pack("<II", video, 7) + bytes([flag])

    def package(self, **chunks):
        return b"".join(chunks.get(f"c{i}", self.span(kind=b"U" if i == 0 else b"T")) for i in range(53))

    @staticmethod
    def parse(raw, allow_trailing=False):
        import struct
        rows = []
        for index in range(len(raw) // 10):
            kind = {b"U": "Unif", b"T": "TSET"}[raw[index * 10:index * 10 + 1]]
            video, system = struct.unpack_from("<II", raw, index * 10 + 1)
            rows.append(types.SimpleNamespace(index=index, kind=kind, offset=index * 10, end_offset=index * 10 + 10,
                                              video_bytes=video, system_bytes=system))
        return rows

    def setUp(self):
        import nfl_txtr
        from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
        from mod_editor.core import nfl2k5_moment_kits as kits
        self.kits = kits
        self.retail = {"18A0": self.package(), "18A8": self.package()}
        for patch in (mock.patch.object(nfl_txtr, "parse_chunks", self.parse),
                      mock.patch.object(kits, "MAX_VIDEO_BYTES", 53 * 100),
                      mock.patch.object(kits, "MAX_SYSTEM_BYTES", 53 * 7),
                      mock.patch.object(kits.RetailPackages, "__missing__", self.missing, create=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.doc = {"kits": [{"id": "K1", "team": "NYG", "code": "18", "style": 9,
                              "sides": {"H": {"base": "18A8"}, "A": {"base": "18A8", "chunks": {"4": "18A0"}}}}]}

    def missing(self, selector):
        raise KeyError(selector)

    def test_the_edited_chunk_is_compiled_into_the_retail_donor_and_the_overflow_is_named(self):
        grown = self.span(video=100 + 400, flag=0)

        def compile_group(index, edits, **kwargs):
            self.assertTrue(kwargs["preflight_only"])
            return types.SimpleNamespace(rebuilt_span=grown, video_end=500)

        retail = self.kits.RetailPackages("unused")
        retail.update(self.retail)
        with mock.patch.object(pc, "_feature_documents", return_value=[("Anniversary moment kits", self.doc)]), \
                mock.patch("mod_editor.core.nfl2k5_uniform_equipment_writer.build_unified_uniform_equipment_imports",
                           compile_group), \
                mock.patch.object(self.kits, "RetailPackages", return_value=retail):
            findings = pc.kit_dry_run(
                types.SimpleNamespace(source="retail.iso"), {("18A0", 4): ["tset:1:4:0:socks00"]},
                {"tset:1:4:0:socks00": Path("a.png")}, "index", "retail.iso")
        self.assertEqual(len(findings), 1)            # only the A side reads the edited chunk from 18A0
        self.assertEqual(findings[0].severity, pc.NOTE)
        self.assertIn("K1 (NYG, away)", findings[0].title)
        self.assertIn("18A0", findings[0].title)
        self.assertIn("chunk 4", findings[0].title)
        self.assertIn("socks", findings[0].title)

    def test_nothing_to_do_without_features_or_edits(self):
        plan = types.SimpleNamespace(source="x", espn25_more_moments=False, classic_teams=False)
        self.assertEqual(pc.kit_dry_run(plan, {("18A0", 4): ["x"]}, {}, "i", "r"), [])
        with mock.patch.object(pc, "_feature_documents", return_value=[("f", self.doc)]):
            self.assertEqual(pc.kit_dry_run(plan, {}, {}, "i", "r"), [])

    def test_a_dry_run_that_cannot_compile_leaves_the_static_notes_and_says_so(self):
        plan = mod_build.BuildPlan("/never/read.iso", "/never/written.iso", espn25_more_moments=True)
        ids = [sock_id("18A0")]
        with mock.patch.object(pc, "kit_dry_run", side_effect=ValueError("no cache")):
            report = pc.check(plan, asset_ids=ids, asset_paths={ids[0]: Path("a.png")}, source_index="i",
                              run_preflight=False)
        self.assertTrue(report.ok)
        titles = [f.title for f in report.notes]
        self.assertIn("The new kits could not be tried on your edited kits.", titles)
        self.assertTrue(any("K1" in t for t in titles))            # the static map still names the kit


class BuildGate(unittest.TestCase):
    """The long build runs the same quick check first and stops with its list."""

    def session(self):
        edit = types.SimpleNamespace(asset_id=sock_id("14H8"), replacement_path="/never/a.png")
        return types.SimpleNamespace(iter_project_png_edits=lambda: [edit])

    def service(self, document):
        return types.SimpleNamespace(preflight_project=lambda session: document)

    def test_a_stop_ends_the_build_before_any_work(self):
        plan = mod_build.BuildPlan("/never/read.iso", "/never/written.iso", custom_intro="m.mp4", trim_intro_videos=True)
        built = []
        with mock.patch.object(mod_build, "build", side_effect=lambda *a, **k: built.append(1)), \
                mock.patch("mod_editor.core.nfl2k5_model_project.validate_build_plan"):
            with self.assertRaises(ValueError) as caught:
                mod_build.build_with_project(plan, self.service({"edits": [{"kind": "texture", "target": "a"}]}),
                                             None, self.session())
        self.assertEqual(built, [])
        self.assertIn("What to do:", str(caught.exception))
        self.assertIn("Custom intro video or Trim intro videos", str(caught.exception))

    def test_a_passing_check_goes_on_to_the_build(self):
        plan = mod_build.BuildPlan("/never/read.iso", "/never/written.iso")
        seen = []
        with mock.patch("mod_editor.core.nfl2k5_model_project.validate_build_plan"), \
                mock.patch("mod_editor.core.nfl2k5_model_project.plan_rows", return_value=[]), \
                mock.patch.object(mod_build, "build", return_value={"steps": []}) as build:
            receipt = mod_build.build_with_project(
                plan, self.service({"edits": [{"kind": "texture", "target": "a"}]}), None, self.session(),
                lambda *a: seen.append(a[0]))
        build.assert_called_once()
        self.assertTrue(any(str(m).startswith("Project check passed") for m in seen))
        self.assertEqual(receipt["steps"], [])


if __name__ == "__main__":
    unittest.main()

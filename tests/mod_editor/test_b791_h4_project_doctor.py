"""b791 h4: the project doctor (Check my project v2), the stadium dry run and the edit-survival audit.

Synthetic projects and bundles only (no game data): the stadium writers' per-bundle functions are replaced by small
fakes in this process (one worker, so the fakes are seen), which proves the chain, the order, the failure and kept
records, the report shapes and the command line. The real refits on the retail disc are proved by the deep dive on
Coach Edwards' project (b77_session/reports/b791_h4-doctor_REPORT.md)."""
import io
import json
import os
import struct
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
from mod_editor.core import nfl2k5_edit_survival as survival  # noqa: E402
from mod_editor.core import nfl2k5_project_check as pc  # noqa: E402
from mod_editor.core import nfl2k5_stadium_dry_run as dry  # noqa: E402


def png(width=8, height=8, colour=(200, 30, 30, 255), *, box=None, box_colour=(255, 255, 255, 255), extra=b""):
    from PIL import Image
    image = Image.new("RGBA", (width, height), colour)
    if box:
        for x in range(box[0], box[2]):
            for y in range(box[1], box[3]):
                image.putpixel((x, y), box_colour)
    out = io.BytesIO()
    image.save(out, "PNG")
    data = out.getvalue()
    if extra:   # a private ancillary chunk before IEND (how the equipment import choice travels)
        import zlib
        chunk = b"npTC" + extra
        data = data[:-12] + struct.pack(">I", len(extra)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF) + data[-12:]
    return data


def sock_id(selector, chunk=4, reference=0):
    from mod_editor.core.nfl2k5_uniform_equipment_writer import load_targets
    for target in load_targets()[0].values():
        if target.set_selector == selector and target.chunk_index == chunk and target.reference_index == reference:
            return target.asset_id
    raise AssertionError(selector)


def archive(folder, settings=None, edits=None, name="p.2k5mod"):
    """A tiny .2k5mod: manifest + PNG members (untrusted data the doctor only parses)."""
    path = Path(folder) / name
    edits = edits or {sock_id("14H8"): png(), "nfl2k5.uniform.14h8.sleeve": png(16, 16)}
    rows, members = [], {}
    for number, (asset_id, data) in enumerate(sorted(edits.items())):
        member = f"replacements/{number:04d}.png"
        members[member] = data
        rows.append({"asset_id": asset_id, "file": member, "png_sha256": "0" * 64, "rgba_sha256": "0" * 64})
    manifest = {"schema": "2k5_mod_studio_project/v1", "game": "espn_nfl_2k5_xbox",
                "payload_policy": "user-replacements-only", "build_settings": settings or {}, "edits": rows,
                "fit_receipts": {"0" * 64: [{"asset_id": rows[0]["asset_id"], "fit_status": "fits"}]},
                "uniform_colors": []}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("project.json", json.dumps(manifest))
        for member, data in members.items():
            z.writestr(member, data)
    return path


# ----------------------------------------------------------------------------------------------- stadium dry run

class FakeArchive:
    """colour._outer_image()(source): entries by outer index and reads by offset."""

    def __init__(self, bundles):
        self.blobs = []
        self.entries = []
        offset = 0
        for outer, data in sorted(bundles.items()):
            while len(self.entries) <= outer:
                self.entries.append(types.SimpleNamespace(virtual_offset=0, size=0))
            self.entries[outer] = types.SimpleNamespace(virtual_offset=offset, size=len(data))
            self.blobs.append((offset, data))
            offset += len(data)

    def read(self, offset, size):
        for start, data in self.blobs:
            if start == offset and len(data) == size:
                return data
        raise AssertionError((offset, size))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class StadiumDryRun(unittest.TestCase):
    """The chain on synthetic bundles: Modern colour, the owning writer, surfaces, greens, in Build's order."""

    BUNDLES = {"s13ad.iff": (10, b"KC" * 20), "s00dd.iff": (11, b"AZ" * 20), "s41dd.iff": (12, b"SB" * 20)}

    def setUp(self):
        from mod_editor.core import nfl2k5_modern_color as colour
        self.colour = colour
        pins = [dict(name=n, outer=o, retail_sha256=dry.sha(d), applied_sha256="", sites=[], size=len(d))
                for n, (o, d) in self.BUNDLES.items()]
        self.archive = FakeArchive({o: d for o, d in self.BUNDLES.values()})
        self.calls = []
        for patch in (mock.patch.object(colour, "_pins", return_value={"bundles": pins}),
                      mock.patch.object(colour, "_outer_image", return_value=lambda *_a, **_k: self.archive),
                      mock.patch.object(colour, "bundle_plan", return_value=[("field", 0, 4), ("tint", 4, 4)]),
                      mock.patch.object(colour, "_refit_fields", return_value={}),
                      mock.patch("mod_editor.core.nfl2k5_modern_surfaces.indoor_flags", return_value={}),
                      mock.patch.object(dry, "_greens_families", return_value={"s13": "grass", "s00": "grass",
                                                                               "s41": "synthetic"}),
                      mock.patch.object(dry, "venue_names", return_value={"s13": "Arrowhead Stadium (KC)"})):
            patch.start()
            self.addCleanup(patch.stop)

    def plan(self, **kw):
        return mod_build.BuildPlan("/never/read.iso", "/never/written.iso", **kw)

    def fake_colour(self, unfit=()):
        def modern_bundle(data, outer_index=0, field_cache=None, settings=None):
            self.calls.append(("colour", outer_index))
            edits = [dict(kind="field", refit=True), dict(kind="tint")]
            if outer_index in unfit:
                edits[0] = dict(kind="field", refit=False, unfit="cannot keep the retail scratch word: greedy: 9 bytes "
                                "exceeds 8")
            return b"c" + data[1:], edits
        return modern_bundle

    def test_steps_follow_the_plan_in_build_order(self):
        plan = self.plan(modern_color=True, modern_arrowhead=True, modern_sofi=True, modern_practice_field=True,
                         modern_surfaces=True)
        self.assertEqual(dry.selected_steps(plan), ["colour", "arrowhead", "nfl2k5_sofi_model", "practice", "surfaces",
                                                    "greens"])
        self.assertEqual(dry.selected_steps(self.plan()), [])
        labels = [label for label, _why in dry.not_covered(plan)]
        self.assertIn("the modern stadium buildings", labels)
        self.assertIn("Stadium shadows", labels)
        self.assertNotIn("the modern stadium buildings", [l for l, _w in dry.not_covered(plan, stadium_models=True)])

    def test_a_refit_that_fails_with_an_empty_reason_is_named_and_the_bundle_goes_on(self):
        from mod_editor.core import nfl2k5_modern_arrowhead as ah
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_broadcast_greens as gr
        import nfl_txtr as tx

        def combined(retail, graded, outer_index=0, settings=None):
            self.calls.append(("arrowhead", outer_index))
            raise tx.TxtrError("cannot keep the retail scratch word: ")

        def surface(job):
            name, data = job[0], job[1]
            self.calls.append(("surfaces", name, data[:1]))
            return name, data, dict(edits=[dict(kind="divots")], field=dict(palette_cap=256), normal="full")

        def greens(job):
            self.calls.append(("greens", job[0], job[1]))
            return job[0], job[2], dict(edits=[dict(scene="field")])

        plan = self.plan(modern_color=True, modern_arrowhead=True, modern_surfaces=True)
        with mock.patch.object(self.colour, "modern_bundle", self.fake_colour()), \
                mock.patch.object(ah, "combined_bundle", combined), mock.patch.object(ms, "_job", surface), \
                mock.patch.object(gr, "_bundle_job", greens):
            result = dry.run(plan, "/never/read.iso", workers=1)
        self.assertEqual(result.bundles, 3)
        failed = result.failed
        self.assertEqual([(r["bundle"], r["step"]) for r in failed], [("s13ad.iff", "arrowhead")])
        self.assertIn("no candidate was recorded", failed[0]["reason"])
        self.assertIn("Arrowhead Stadium (KC)", dry.describe(failed[0]))
        self.assertIn("afternoon, dry", dry.describe(failed[0]))
        # Build's order for the Kansas City bundle: colour, Arrowhead, then surfaces on the graded bytes it kept
        kc = [c for c in self.calls if (len(c) > 1 and c[1] in (10, "s13ad.iff"))]
        self.assertEqual([c[0] for c in kc], ["colour", "arrowhead", "surfaces", "greens"])
        self.assertEqual(kc[2][2], b"c")
        # s41 is not a home venue: no surfaces, but greens with its own family
        self.assertNotIn(("surfaces", "s41dd.iff", b"c"), self.calls)
        self.assertIn(("greens", "s41dd.iff", "synthetic"), self.calls)
        counts = result.counts()
        self.assertEqual(counts[("colour", "refit")], 3)
        self.assertEqual(counts[("surfaces", "unchanged")], 2)       # the fake surface returns its input
        doc = result.as_dict()
        self.assertEqual(doc["schema"], dry.SCHEMA)
        blob = json.dumps(doc)
        self.assertNotIn("KCKCKC", blob)   # never bundle bytes, only names, statuses and digests

    def test_kept_spans_are_notes_from_colour_and_from_the_keep_keys(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        from mod_editor.core import nfl2k5_broadcast_greens as gr

        def surface(job):
            name, data = job[0], job[1]
            receipt = dict(edits=[], field=dict(palette_cap=64), normal="full")
            if name == "s00dd.iff":
                receipt["edits"] = [dict(kind="divots", kept="the divot layer keeps its bytes: no room")]
            return name, data, receipt

        plan = self.plan(modern_color=True, modern_surfaces=True)
        with mock.patch.object(self.colour, "modern_bundle", self.fake_colour(unfit={11})), \
                mock.patch.object(ms, "_job", surface), \
                mock.patch.object(gr, "_bundle_job", lambda job: (job[0], job[2], dict(edits=[]))):
            result = dry.run(plan, "/never/read.iso", workers=1)
        kept = {(r["bundle"], r["step"]) for r in result.kept}
        self.assertEqual(kept, {("s00dd.iff", "colour"), ("s00dd.iff", "surfaces")})
        self.assertFalse(result.failed)
        row = next(r for r in result.kept if r["step"] == "colour")
        self.assertIn("keeps its field as it was", dry.describe(row))

    def test_a_bundle_that_is_not_retail_is_skipped_and_named(self):
        self.archive.blobs[0] = (self.archive.blobs[0][0], b"XX" * 20)   # s13 (outer 10) differs from its pin
        with mock.patch.object(self.colour, "modern_bundle", self.fake_colour()):
            result = dry.run(self.plan(modern_color=True), "/never/read.iso", workers=1)
        self.assertIn("s13ad.iff", result.skipped_bundles)
        self.assertEqual(result.bundles, 2)

    def test_the_classic_field_bundles_are_left_out_of_the_dry_run(self):
        with mock.patch.object(self.colour, "modern_bundle", self.fake_colour()), \
                mock.patch("mod_editor.core.nfl2k5_classic_field.BUNDLES", ("s41dd.iff",)):
            result = dry.run(self.plan(modern_color=True, classic_teams=True, historic_teams_quick_game=True),
                             "/never/read.iso", workers=1)
        self.assertIn("s41dd.iff", result.skipped_bundles)
        self.assertNotIn("s41dd.iff", {r["bundle"] for r in result.rows})

    def test_the_model_field_is_placed_where_the_compose_worker_places_it(self):
        """The field-only path writes the stadium model's field at the same offset as its real _compose worker."""
        from mod_editor.core import nfl2k5_highmark_model as hm
        retail, current = bytes(range(64)), bytes(64)
        chunk = types.SimpleNamespace(offset=8)
        with mock.patch.object(hm, "field_span", return_value=(b"F" * 8, {"palette_cap": 256})), \
                mock.patch.object(dry, "_field_offset", return_value=chunk), \
                mock.patch("mod_editor.core.nfl2k5_modern_metlife.bundle_scenes", return_value={"field": chunk}), \
                mock.patch.object(hm, "model_bundle", return_value=(retail, {})), \
                mock.patch.object(hm, "stretch", return_value=(40, 48)), \
                mock.patch.object(hm, "build", return_value=None), mock.patch.object(hm, "highmark_shots", return_value=()):
            mine, _info = dry._model_field(hm, dict(name="s03dd.iff", retail=retail, settings=None, outer=1,
                                                    writer=("nfl2k5_highmark_model", "nfl2k5_highmark_model")), current)
            _n, theirs, _i = hm._compose(("s03dd.iff", retail, current, None, 1, None, retail))
        self.assertEqual(mine[:40], theirs[:40])      # the same field placement; the stretch (40-48) is geometry
        self.assertEqual(mine[8:16], b"F" * 8)

    def test_the_keep_records_of_the_b791_fixes_become_one_row_per_kept_span(self):
        receipt = {"edits": [], "kept": [{"site": "divots", "reason": "cannot keep the retail scratch word: ...",
                                          "user_note": "Modern surfaces: Arrowhead Stadium (s13ad.iff) keeps its divot "
                                                       "layer as it was"}]}
        self.assertEqual(dry._kept_items(receipt),
                         [("divots", "Modern surfaces: Arrowhead Stadium (s13ad.iff) keeps its divot layer as it was")])
        self.assertEqual(dry._kept_items({"kept": "whole bundle kept"}), [(None, "whole bundle kept")])

    def test_reasons_are_plain_and_bounded(self):
        self.assertIn("no candidate was recorded", dry._reason(ValueError("cannot keep the retail scratch word:")))
        self.assertEqual(dry._reason(ValueError("")), "ValueError with no message")
        self.assertLessEqual(len(dry._reason("x" * 5000)), 900)
        self.assertCountEqual(dry._kept_notes({"a": [{"unfit": "no room"}], "user_notes": ["kept one"]}),
                              ["no room", "kept one"])
        self.assertEqual(dry._kept_notes({"edits": [{"kind": "field", "refit": True}]}), [])
        self.assertEqual(dry.bundle_words("s29nr.iff"), "night, rain")


# ----------------------------------------------------------------------------------------------- the doctor

class DoctorReportShape(unittest.TestCase):
    def report(self):
        report = pc.DoctorReport(findings=[pc.Finding(pc.STOP, "Stadiums and colour", "Surfaces cannot refit 1 bundle.",
                                                      "First reason: x.", "Untick Modern playing surfaces.", code="s"),
                                           pc.Finding(pc.NOTE, "Kits", "K2 uses retail shoes.")],
                                 steps=["Options"], seconds=75,
                                 sections=[pc.Section("stadiums", "Stadium and colour dry run", summary="1 failed.",
                                                      data={"lines": ["Modern playing surfaces: 0 refit"]})],
                                 project=dict(name="p.2k5mod", edits=2), source=dict(name="retail.iso", identity="ok"),
                                 studio=dict(version="2K5 Mod Studio test", platform="test"))
        return report

    def test_text_summary_and_json_say_the_same_thing_in_plain_words(self):
        report = self.report()
        self.assertFalse(report.ok)
        text, summary, doc = report.text(), report.summary(), report.as_dict()
        self.assertIn("Change or untick 1 thing before Build", summary)
        self.assertIn("What to do: Untick Modern playing surfaces.", summary)
        self.assertIn("Stadium and colour dry run: 1 failed.", summary)
        self.assertIn("== Stadium and colour dry run", text)
        self.assertIn("Modern playing surfaces: 0 refit", text)
        self.assertIn("1 min 15 s", text)
        self.assertEqual(doc["schema"], pc.DOCTOR_SCHEMA)
        self.assertEqual((doc["stops"], doc["notes"]), (1, 1))
        self.assertEqual(doc["sections"][0]["key"], "stadiums")
        self.assertEqual(doc["findings"][0]["code"], "s")
        for words in (text, summary):
            self.assertNotIn("—", words)                  # no em dashes in what people read

    def test_write_makes_three_files_with_unix_newlines_in_any_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "My Reports" / "Coach Edwards"
            written = self.report().write(target)
            self.assertEqual(sorted(written), ["json", "summary", "text"])
            self.assertEqual(sorted(p.name for p in target.iterdir()),
                             ["project-check-summary.txt", "project-check.json", "project-check.txt"])
            for path in written.values():
                raw = Path(path).read_bytes()
                self.assertNotIn(b"\r\n", raw)
                raw.decode("utf-8")
            self.assertEqual(json.loads(Path(written["json"]).read_text(encoding="utf-8"))["schema"], pc.DOCTOR_SCHEMA)


class Scrub(unittest.TestCase):
    def test_written_reports_hide_the_home_folder_in_every_spelling(self):
        from pathlib import PureWindowsPath
        line = ('File "C:\\Users\\glenwood.edwards\\Desktop\\x.py" '
                + json.dumps("C:\\Users\\glenwood.edwards\\y") + " C:/Users/glenwood.edwards/z")
        with mock.patch.object(pc.Path, "home", return_value=PureWindowsPath("C:/Users/glenwood.edwards")):
            text = pc.scrub(line)
        self.assertNotIn("glenwood", text)
        self.assertEqual(text.count("~"), 3)


class Doctor(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_an_options_only_project_without_a_disc_still_gets_every_section(self):
        path = archive(self.folder, {"modern_arrowhead": True})
        report = pc.doctor(path, self.folder / "missing.iso", checks=pc.QUICK_CHECKS)
        keys = [s.key for s in report.sections]
        self.assertEqual(keys, ["options", "kits", "untested", "inventory"])
        self.assertTrue(report.ok, report.text())
        self.assertEqual(report.project["edits"], 2)
        self.assertFalse(report.source["present"])
        untested = report.section("untested").data
        self.assertIn("modern_arrowhead", [i["option"] for i in untested["options"]])
        inventory = report.section("inventory").data
        self.assertEqual(inventory["edits"], 2)
        self.assertEqual(inventory["families"], {"equipment": 1, "uniform": 1})

    def test_an_unreadable_project_is_a_stop_and_the_options_are_still_checked(self):
        bad = self.folder / "broken.2k5mod"
        bad.write_bytes(b"this is not a zip file")
        report = pc.doctor(bad, self.folder / "missing.iso", {"modern_arrowhead": True}, checks=pc.QUICK_CHECKS)
        self.assertFalse(report.ok)
        self.assertEqual(report.stops[0].code, "project.unreadable")
        self.assertIn("could not be read", report.stops[0].title)
        self.assertIn("modern_arrowhead", [i["option"] for i in report.section("untested").data["options"]])

    def test_the_report_never_carries_the_users_textures(self):
        marker = bytes(range(97, 123)) * 3          # an unmistakable run inside the user's PNG
        art = png(extra=marker)
        path = archive(self.folder, {}, {sock_id("14H8"): art})
        report = pc.doctor(path, self.folder / "missing.iso", checks=pc.QUICK_CHECKS)
        with tempfile.TemporaryDirectory() as out:
            written = report.write(out)
            blobs = b"".join(Path(p).read_bytes() for p in written.values())
        self.assertNotIn(marker, blobs)
        self.assertNotIn(marker.hex().encode(), blobs)
        import base64
        self.assertNotIn(base64.b64encode(art)[:40], blobs)

    def test_a_check_that_raises_is_a_failed_section_not_a_failed_doctor(self):
        path = archive(self.folder)
        with mock.patch.object(pc, "inventory", side_effect=RuntimeError("disk on fire")):
            report = pc.doctor(path, self.folder / "missing.iso", checks=pc.QUICK_CHECKS)
        section = report.section("inventory")
        self.assertEqual(section.status, "failed")
        self.assertIn("disk on fire", section.summary)
        self.assertIn("RuntimeError", section.data["error"])
        self.assertEqual(report.section("untested").status, "ran")

    def test_cancelling_stops_the_doctor(self):
        from mod_editor.core.nfl2k5_project_fit import BuildCancelled
        path = archive(self.folder)

        def progress(*_a):
            raise BuildCancelled("cancelled")
        with mock.patch.object(pc, "check", side_effect=BuildCancelled("cancelled")):
            with self.assertRaises(BuildCancelled):
                pc.doctor(path, self.folder / "missing.iso", checks=pc.QUICK_CHECKS, progress=progress)

    def test_settings_can_be_a_plan_a_saved_dict_or_the_projects_own(self):
        path = archive(self.folder, {"modern_metlife": True})
        own = pc._doctor_plan(None, pc.project_inputs(path), self.folder / "r.iso")
        self.assertTrue(own.modern_metlife)
        given = pc._doctor_plan({"modern_sofi": True}, pc.project_inputs(path), self.folder / "r.iso")
        self.assertTrue(given.modern_sofi)
        self.assertFalse(given.modern_metlife)
        plan = mod_build.BuildPlan("elsewhere.iso", "out.iso", modern_lambeau=True)
        from_plan = pc._doctor_plan(plan, pc.project_inputs(None), self.folder / "r.iso")
        self.assertTrue(from_plan.modern_lambeau)
        self.assertEqual(Path(from_plan.source).name, "r.iso")
        self.assertNotEqual(Path(from_plan.target).name, "out.iso")      # the doctor never names a real output

    def dry_result(self):
        rows = [dict(bundle="s13ad.iff", step="surfaces", status="failed", part="bundle", venue="Arrowhead Stadium (KC)",
                     label="Modern playing surfaces",
                     reason="cannot keep the retail scratch word: (no candidate was recorded: ...)"),
                dict(bundle="s00dd.iff", step="colour", status="kept", part="normal", venue="State Farm Stadium (ARI)",
                     label="Modern colour and lighting", reason="no room"),
                dict(bundle="s00dd.iff", step="surfaces", status="refit", part="field", venue="State Farm Stadium (ARI)",
                     label="Modern playing surfaces", reason="")]
        return dry.DryRun(rows=rows, steps=["colour", "surfaces", "greens"], bundles=2, workers=1, seconds=3,
                          not_covered=[("Stadium shadows", "geometry")])

    def test_stadium_failures_are_stops_and_kept_spans_are_notes(self):
        path = archive(self.folder, {"modern_color": True, "modern_surfaces": True})
        source = self.folder / "retail.iso"
        source.write_bytes(b"not a real disc")
        with mock.patch.object(dry, "run", return_value=self.dry_result()) as run:
            report = pc.doctor(path, source, checks=["stadiums"])
        run.assert_called_once()
        stops = [f for f in report.stops if f.area == "Stadiums and colour"]
        self.assertEqual(len(stops), 1)
        self.assertIn("Modern playing surfaces cannot refit 1 stadium bundle", stops[0].title)
        self.assertIn("Arrowhead Stadium (KC) (s13ad.iff)", stops[0].title)
        self.assertIn("Studio beta 79 stopped the whole build", stops[0].detail)
        self.assertIn("Untick Modern playing surfaces", stops[0].fix)
        notes = [f for f in report.notes if f.area == "Stadiums and colour"]
        self.assertEqual(len(notes), 1)
        self.assertIn("keeps 1 bump map as they are", notes[0].title)
        section = report.section("stadiums")
        self.assertIn("1 failed", section.summary)
        self.assertTrue(any(line.startswith("FAILS: ") for line in section.data["lines"]))
        self.assertTrue(any("Not tried here: Stadium shadows" in line for line in section.data["lines"]))

    def test_a_step_build_leaves_out_instead_of_stopping_is_a_note(self):
        path = archive(self.folder, {"modern_color": True, "modern_surfaces": True})
        source = self.folder / "retail.iso"
        source.write_bytes(b"not a real disc")
        with mock.patch.object(dry, "run", return_value=self.dry_result()), \
                mock.patch.object(mod_build, "OPTIONAL_STEPS", frozenset({"modern_surfaces"}), create=True):
            report = pc.doctor(path, source, checks=["stadiums"])
        self.assertTrue(report.ok, report.text())
        left = [f for f in report.notes if "cannot refit" in f.title]
        self.assertEqual(len(left), 1)
        self.assertIn("leaves that step out of your disc", left[0].detail)

    def test_a_session_is_read_through_its_edits(self):
        staged = self.folder / "a.png"
        staged.write_bytes(png())
        edit = types.SimpleNamespace(asset_id=sock_id("14H8"), replacement_path=str(staged))
        session = types.SimpleNamespace(iter_project_png_edits=lambda: [edit], name="open")
        inputs = pc.project_inputs(session, fit_rows=[])
        self.assertEqual(inputs.asset_ids, [edit.asset_id])
        self.assertEqual(inputs.png(edit.asset_id), staged.read_bytes())


class CommandLine(unittest.TestCase):
    def test_json_flag_prints_json_and_report_writes_the_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            path = archive(folder)
            out = io.StringIO()
            with mock.patch("sys.stdout", out), mock.patch("sys.stderr", io.StringIO()):
                code = pc.main([str(path), "--source", str(Path(folder) / "missing.iso"), "--quick", "--json",
                                "--report", str(Path(folder) / "report")])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out.getvalue())["schema"], pc.DOCTOR_SCHEMA)
            self.assertTrue((Path(folder) / "report" / "project-check.txt").is_file())

    def test_json_path_and_exit_code_follow_the_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = archive(folder, {"custom_intro": "m.mp4", "trim_intro_videos": True})
            target = Path(folder) / "r.json"
            with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(pc.main([str(bad), "--source", str(Path(folder) / "r.iso"), "--quick",
                                          "--json", str(target)]), 1)
            doc = json.loads(target.read_text(encoding="utf-8"))
            self.assertFalse(doc["ok"])
            self.assertEqual(doc["findings"][0]["severity"], "stop")


# ----------------------------------------------------------------------------------------------- the checks

class Untested(unittest.TestCase):
    def test_the_release_gate_list_loads_and_names_its_builds(self):
        gates = pc.release_gates()
        self.assertEqual([g["id"] for g in gates], ["basic", "advanced", "experimental", "softdrink"])
        softdrink = next(g for g in gates if g["id"] == "softdrink")
        self.assertTrue(softdrink["options"]["modern_color"])
        self.assertFalse(softdrink["options"]["modern_arrowhead"])
        self.assertEqual(softdrink["options"]["modern_venues_2026"], {"given": True})

    def test_arrowhead_and_custom_colour_are_named_with_the_levers(self):
        from mod_editor.core import nfl2k5_modern_color as colour
        settings = colour.default_settings()
        settings["values"]["master.strength"] = 0.61
        plan = mod_build.BuildPlan("r.iso", "o.iso", modern_color=True, modern_surfaces=True, modern_arrowhead=True,
                                   modern_color_settings=settings)
        found = pc.untested_options(plan, platform="win32")
        items = {i["option"]: i for i in found["options"]}
        self.assertIn("modern_arrowhead", items)
        self.assertIn("modern_color_settings", items)
        self.assertEqual(items["modern_color_settings"]["levers"][0]["lever"], "master.strength")
        self.assertTrue(any("your own Modern colour values" in p["labels"] for p in found["pairs"]))
        self.assertIn("Windows Python", found["platform"])
        self.assertIsNone(pc.untested_options(plan, platform="linux")["platform"])

    def test_options_every_release_build_has_are_not_listed(self):
        plan = mod_build.apply_preset(mod_build.BuildPlan("r.iso", "o.iso"), "softdrink_experimental")
        found = pc.untested_options(plan, platform="linux")
        self.assertEqual(found["options"], [])


class Inventory(unittest.TestCase):
    def test_families_pieces_choices_and_limits(self):
        from mod_editor.studio import project_archive as pa
        from mod_editor.core.nfl2k5_equipment_import_intent import OWN_TEXTURE, SCHEMA
        import hashlib
        from PIL import Image
        plain = png()
        with Image.open(io.BytesIO(plain)) as image:
            rgba = image.convert("RGBA").tobytes()
        sock = sock_id("14H8")
        choice = json.dumps({"schema": SCHEMA, "asset_id": sock, "mode": OWN_TEXTURE,
                             "rgba_sha256": hashlib.sha256(rgba).hexdigest(), "scale": 1},
                            separators=(",", ":")).encode()
        own = png(extra=choice)
        with tempfile.TemporaryDirectory() as folder:
            path = archive(folder, {}, {sock: own, sock_id("14H8", reference=1): plain,
                                        "nfl2k5.uniform.14h8.torso": png(), "nfl2k5.stadium.o3138.scene": png()})
            inputs = pc.project_inputs(path)
            with mock.patch.object(pa, "MAX_PROJECT_EDITS", 5):
                data = pc.inventory(inputs, mod_build.BuildPlan("r.iso", "o.iso"))
        self.assertEqual(data["edits"], 4)
        self.assertEqual(data["equipment_choices"], {"automatic": 1, "own texture": 1})
        self.assertEqual(data["equipment_parts"], {"socks": 2})
        self.assertEqual(data["uniform_parts"], {"torso": 1})
        self.assertEqual(data["stadium_edits"], 1)
        edits = next(row for row in data["limits"] if row["name"] == "project edits")
        self.assertEqual(edits["state"], "close")
        self.assertTrue(pc._inventory_lines(data))

    def test_uniform_parts_map_to_their_kit_file_pieces(self):
        self.assertEqual(pc.uniform_chunk("nfl2k5.uniform.18a0.sleeve"), ("18A0", 3))
        self.assertEqual(pc.uniform_chunk("nfl2k5.uniform.01h12.digit.arm.7"), ("01H12", 40))
        self.assertEqual(pc.uniform_chunk("nfl2k5.uniform.02a3.helmet.helmet02"), ("02A3", 12))
        self.assertIsNone(pc.uniform_chunk("nfl2k5.uniform.02a3.team-select.unif.256"))
        self.assertEqual(pc.KIT_PIECES[3], "sleeves")

    def test_stadium_edits_in_rebuilt_bundles_are_a_stop(self):
        from mod_editor.core import nfl2k5_modern_color as colour
        pin = colour._pins()["bundles"][0]
        plan = mod_build.BuildPlan("r.iso", "o.iso", modern_color=True)
        found = pc.stadium_edit_conflicts([f"nfl2k5.stadium.o{pin['outer']}.field", "nfl2k5.stadium.o1.x"], plan)
        self.assertEqual([c["bundle"] for c in found], [pin["name"]])
        self.assertEqual(pc.stadium_edit_conflicts([f"nfl2k5.stadium.o{pin['outer']}.field"],
                                                   mod_build.BuildPlan("r.iso", "o.iso")), [])


class Kits(unittest.TestCase):
    ART = {"chunk": 3, "kind": "tset", "texture": "sleeve00", "size": [16, 16, 1],
           "ops": [{"op": "poly", "color": "#FFFFFF", "points": [[2, 2], [6, 2], [6, 6], [2, 6]]}]}

    def test_kit_allocation_sums_the_chunks_like_the_largest_kit_rule(self):
        rows = [types.SimpleNamespace(system_bytes=7, video_bytes=100), types.SimpleNamespace(system_bytes=3, video_bytes=50)]
        with mock.patch("nfl_txtr.parse_chunks", return_value=rows):
            self.assertEqual(pc.kit_allocation(b"x"), (10, 150))

    def test_solid_paint_on_the_users_art_is_judged_from_the_png(self):
        self.assertTrue(pc._poly_paint_changes(png(16, 16), self.ART))
        self.assertFalse(pc._poly_paint_changes(png(16, 16, box=(0, 0, 9, 9)), self.ART))
        self.assertIsNone(pc._poly_paint_changes(png(16, 16), dict(self.ART, ops=[{"op": "recolor"}])))
        self.assertIsNone(pc._poly_paint_changes(b"not a png", self.ART))
        # a 32x32 PNG for a 16x16 texture is judged in the texture's own coordinates
        self.assertFalse(pc._poly_paint_changes(png(32, 32, box=(0, 0, 18, 18)), self.ART))

    def test_a_left_out_kit_that_a_classic_default_needs_is_an_orphan(self):
        doc = {"kits": [{"id": "K1", "team": "NYG", "code": "18", "style": 9, "label": [2007, 2011],
                         "sides": {"A": {"base": "18A8", "chunks": {"3": "18A0"}, "art": [self.ART]}}}],
               "selections": [{"row": 27, "side": "away", "file": "h-18-2007-giants-9.iff", "before": 8, "style": 9,
                               "kit": "K1"}],
               "classic_defaults": [{"file": "h-18-2007-giants-9.iff", "style": 9, "before": 8}]}
        from mod_editor.core import nfl2k5_moment_kits as kits

        def compose(document, packages, retail=None, report=None, skipped=None, *rest, **kw):
            skipped["K1"] = "2026 kit fixes: the art changed no texel"
            return {}
        retail = kits.RetailPackages("unused")
        retail.update({"18A0": b"a", "18A8": b"b"})
        plan = types.SimpleNamespace(espn25_more_moments=True, classic_teams=False, historic_teams_quick_game=False)
        with mock.patch.object(pc, "_feature_documents", return_value=[("Anniversary moment kits", doc)]), \
                mock.patch.object(pc, "donors_with_edits", return_value={"18A0": b"a", "18A8": b"b"}), \
                mock.patch.object(kits, "RetailPackages", return_value=retail), \
                mock.patch.object(kits, "compose", compose), mock.patch.object(pc, "_repairs_change", return_value=False):
            found = pc.kit_dependencies(plan, "retail.iso", None)
            self.assertEqual(found["left_out"], {"K1": "2026 kit fixes: the art changed no texel"})
            self.assertEqual([(o["file"], o["sure"]) for o in found["orphans"]], [("h-18-2007-giants-9.iff", True)])
            # the same kit on a project whose own Giants sleeve the art paints over: Build composes it from that art
            inputs = pc.ProjectInputs(asset_ids=["nfl2k5.uniform.18a0.sleeve"])
            inputs.png = lambda asset_id: png(16, 16)
            mine = pc.kit_dependencies(plan, "retail.iso", inputs)
            self.assertEqual(mine["left_out"], {})
            self.assertIn("K1", mine["uncertain"])
            self.assertEqual([r["changes"] for r in mine["paints_your_art"]], [True])
            self.assertEqual([o["sure"] for o in mine["orphans"]], [False])


# ----------------------------------------------------------------------------------------------- edit survival

class EditSurvival(unittest.TestCase):
    def test_pieces_map_equipment_uniform_stadium_and_other(self):
        pieces = survival.edited_pieces([sock_id("14H8"), "nfl2k5.uniform.14h8.torso", "nfl2k5.stadium.o3138.scene",
                                         "nfl2k5.uniform.14h8.team-select.unif.256", "nfl2k5.portrait.x"])
        self.assertEqual(sorted(pieces["kits"]["14H8"]), [1, 4])
        self.assertEqual(sorted(pieces["stadiums"]), [3138])
        self.assertEqual(len(pieces["other"]), 2)

    def snapshot(self):
        pieces = dict(kits={"21A9": {1: ["nfl2k5.uniform.21a9.torso"], 4: [sock_id("14H8")]}}, stadiums={}, other=["x"])
        return dict(schema=survival.SCHEMA, pieces=pieces, seconds=1.0,
                    stage=dict(kits={"21A9": ["h0", "MINE1", "r2", "r3", "MINE4"]}, stadiums={}),
                    source=dict(kits={"21A9": ["h0", "r1", "r2", "r3", "r4"]}, stadiums={}))

    def test_every_changed_piece_is_kept_lost_or_rewritten_by_name(self):
        snap = self.snapshot()
        final = dict(kits={"21A9": ["h0", "MINE1", "zz", "r3", "r4"]}, stadiums={})
        with mock.patch.object(survival, "_read", return_value=final):
            result = survival.audit(snap, "final.iso")
        self.assertEqual(result["kept"], 1)
        self.assertEqual([(r["chunk"], r["state"]) for r in result["lost"]], [(4, "back to the original")])
        notes = survival.user_notes(result)
        self.assertIn("1 of 2 edited pieces did not survive", notes[0])
        self.assertIn("21A9 socks (back to the original)", notes[0])
        self.assertIn("were not checked", notes[1])
        step = None
        with mock.patch.object(survival, "_read", return_value=final):
            step = survival.audit_step(snap, "final.iso")
        self.assertEqual((step["step"], step["state"], step["lost_count"]), ("edit_survival", "lost_edits", 1))

    def test_a_rewritten_or_missing_kit_is_named_and_all_kept_is_said(self):
        snap = self.snapshot()
        with mock.patch.object(survival, "_read", return_value=dict(kits={"21A9": ["h0", "THEIRS", "r2", "r3", "MINE4"]},
                                                                    stadiums={})):
            result = survival.audit(snap, "final.iso")
        self.assertEqual([(r["chunk"], r["state"]) for r in result["lost"]], [(1, "changed by a later build step")])
        with mock.patch.object(survival, "_read", return_value=dict(kits={"21A9": None}, stadiums={})):
            result = survival.audit(snap, "final.iso")
        self.assertEqual({r["state"] for r in result["lost"]}, {"missing"})
        with mock.patch.object(survival, "_read", return_value=dict(kits={"21A9": ["h0", "MINE1", "r2", "r3", "MINE4"]},
                                                                    stadiums={})):
            result = survival.audit(snap, "final.iso")
        self.assertEqual(result["lost"], [])
        self.assertIn("all 2 edited kit and stadium pieces are on the finished disc", survival.user_notes(result)[0])

    def test_the_audit_never_fails_a_finished_build(self):
        with mock.patch.object(survival, "_read", side_effect=OSError("gone")):
            step = survival.audit_step(self.snapshot(), "final.iso")
        self.assertEqual(step["state"], "not_checked")
        self.assertIn("could not run", step["user_notes"][0])
        self.assertEqual(survival.audit_step(None, "x")["state"], "not_checked")

    def test_build_with_project_snapshots_after_the_texture_stage_and_audits_the_finished_disc(self):
        edit = types.SimpleNamespace(asset_id=sock_id("14H8"), replacement_path="/never/a.png")
        session = types.SimpleNamespace(iter_project_png_edits=lambda: [edit])
        service = types.SimpleNamespace(preflight_project=lambda s: {"edits": [{"kind": "texture", "target": "a"}]},
                                        build=lambda cache, s, output, progress: "stage-result")
        plan = mod_build.BuildPlan("/never/read.iso", "/never/written.iso")
        calls = []

        def fake_build(plan, progress, _project_builder=None, require_change=False):
            self.assertEqual(_project_builder("/stage/source.iso"), "stage-result")
            return {"steps": [], "target": "/final.iso"}
        with mock.patch.object(mod_build, "build", fake_build), \
                mock.patch("mod_editor.core.nfl2k5_model_project.validate_build_plan"), \
                mock.patch("mod_editor.core.nfl2k5_model_project.plan_rows", return_value=[]), \
                mock.patch.object(survival, "snapshot", side_effect=lambda out, ids, source=None, progress=None:
                                  calls.append(("snapshot", out, tuple(ids), source)) or {"pieces": {}}), \
                mock.patch.object(survival, "audit_step", side_effect=lambda snap, final, progress=None:
                                  calls.append(("audit", final)) or {"step": "edit_survival", "user_notes": ["ok"]}):
            receipt = mod_build.build_with_project(plan, service, None, session, lambda *a: None)
        self.assertEqual(calls, [("snapshot", "/stage/source.iso", (edit.asset_id,), "/never/read.iso"),
                                 ("audit", "/final.iso")])
        self.assertEqual(receipt["steps"][-1]["step"], "edit_survival")
        from mod_editor.core.build_feedback import completion
        self.assertIn("ok", completion(dict(receipt, outcome={"status": "changed", "message": "m"}))[1])

    def test_a_snapshot_that_fails_does_not_fail_the_build_but_cancel_still_cancels(self):
        from mod_editor.core.nfl2k5_project_fit import BuildCancelled
        edit = types.SimpleNamespace(asset_id=sock_id("14H8"), replacement_path="/never/a.png")
        session = types.SimpleNamespace(iter_project_png_edits=lambda: [edit])
        with mock.patch.object(survival, "snapshot", side_effect=OSError("no disc")):
            self.assertIsNone(mod_build._edit_survival_snapshot("/s.iso", session, types.SimpleNamespace(source="r"),
                                                                lambda *a: None))
        with mock.patch.object(survival, "snapshot", side_effect=BuildCancelled("stop")):
            with self.assertRaises(BuildCancelled):
                mod_build._edit_survival_snapshot("/s.iso", session, types.SimpleNamespace(source="r"), lambda *a: None)


# ----------------------------------------------------------------------------------------------- the Build tab

class BuildTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        for entry in (ROOT / "tests", ROOT / "tests" / "mod_editor"):
            if str(entry) not in sys.path:
                sys.path.insert(0, str(entry))
        from test_mod_build_performance import synthetic_disc
        from mod_editor.gui.build_panel_qt import BuildPanel
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "ESPN NFL 2K5 (USA).xiso.iso"
        synthetic_disc(self.source)
        self.panel = BuildPanel()
        self.addCleanup(self.panel.deleteLater)

        class Immediate:
            def start(self, task):
                task.run()
        self.panel._pool = Immediate()
        self.panel.begin_reading(self.source)
        self.panel.apply_state(mod_build.inspect(self.source))
        for attribute in ("catch_check", "accel_check", "draft_check", "returner_check", "edge_check", "throw_check"):
            box = getattr(self.panel, attribute)
            if box.isEnabled():
                box.setChecked(True)
                break
        self.panel.target_field.setText(str(Path(self.temp.name) / "never.iso"))

    def report(self):
        return pc.DoctorReport(findings=[pc.Finding(pc.STOP, "Stadiums and colour", "Surfaces cannot refit 1 bundle.", "",
                                                    "Untick Modern playing surfaces.")],
                               steps=["x"], seconds=2, sections=[pc.Section("stadiums", "Stadium and colour dry run",
                                                                           summary="1 failed.")])

    def test_the_button_runs_the_doctor_and_shows_the_summary_with_save_report(self):
        from PyQt5.QtWidgets import QMessageBox
        shown = []

        def exec_(box):
            shown.append((box.text(), [b.text() for b in box.buttons()], box.detailedText()))
            return 0
        before = sorted(p.name for p in Path(self.temp.name).iterdir())
        with mock.patch.object(pc, "doctor", return_value=self.report()) as doctor, \
                mock.patch.object(QMessageBox, "exec_", exec_):
            self.panel._check_project()
        doctor.assert_called_once()
        args, kwargs = doctor.call_args
        self.assertEqual(Path(args[1]), self.source)
        self.assertIn("labels", kwargs)
        self.assertEqual(len(shown), 1)
        text, buttons, details = shown[0]
        self.assertIn("What to do: Untick Modern playing surfaces.", text)
        self.assertIn("Save report…", buttons)
        self.assertIn("== Stadium and colour dry run", details)
        self.assertIn("Change or untick 1 thing", self.panel.status_label.text())
        self.assertIn("Check my project", self.panel._last_build_summary)
        self.assertIsNone(self.panel._task)
        self.assertEqual(sorted(p.name for p in Path(self.temp.name).iterdir()), before)

    def test_save_report_writes_the_three_files_where_asked(self):
        folder = Path(self.temp.name) / "saved here"
        written = self.panel._save_check_report(self.report(), str(folder))
        self.assertEqual(sorted(Path(p).name for p in written),
                         ["project-check-summary.txt", "project-check.json", "project-check.txt"])
        self.assertIn("report saved", self.panel.status_label.text())
        self.assertEqual(self.panel._save_check_report(self.report(), ""), [])

    def test_a_cancelled_check_says_so(self):
        from PyQt5.QtWidgets import QMessageBox
        from mod_editor.core.nfl2k5_project_fit import BuildCancelled
        shown = []
        with mock.patch.object(pc, "doctor", side_effect=BuildCancelled("Build cancelled; no output was published.")), \
                mock.patch.object(QMessageBox, "exec_", lambda box: shown.append(box.text()) or 0):
            self.panel._check_project()
        self.assertIn("cancelled", self.panel.status_label.text().lower())
        self.assertNotIn("make the disc", self.panel.status_label.text().lower())


if __name__ == "__main__":
    unittest.main()

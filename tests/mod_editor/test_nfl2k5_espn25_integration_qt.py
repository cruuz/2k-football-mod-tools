"""Protected-surface integration of the ESPN Anniversary editor: Rosters host, Build plan, panels.

Offscreen and synthetic: the fixture is the same invented 25-moment / 75-roster catalog the
standalone suites use, packed into a relocated synthetic XDVDFS image under 4 MiB. No game,
console, emulator, display or retail resource is used.
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from espn25_fixture import fixtures  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as saved  # noqa: E402
from mod_editor.core import nfl2k5_espn25_scenarios as espn  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402

try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.build_panel_qt import BuildPanel
    from mod_editor.gui.gameplay_patches_panel_qt import INFORMATIONAL, NEEDS_IMAGE, PATCHES, GameplayPatchesPanel
    from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
    from mod_editor.gui.text_rosters_panel import ESPN_25TH_COMING_SOON_NOTE, SITU_BANK_PREFIX
    QT_ERROR = None
except ImportError as exc:  # pragma: no cover - precise skip on headless CI without PyQt5
    QT_ERROR = str(exc)

ROSTER_EDIT = {"moment": 0, "side": "away", "shared_resource": True,
               "csv": "pool,index,jersey,speed\nprimary,0,12,91\n"}


def _wait(app, condition, seconds=20.0):
    import time
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return condition()


class _Fixture:
    """A synthetic image whose layout pins are the fixture's own (MANIFEST patched for the test).

    The fixture image carries a 16-byte stub ``default.xbe`` (its packs sit at sector 512, so a
    retail-size executable would not fit the sub-4 MiB image).  The executable-dependent seams of
    ``mod_build`` are therefore answered from the throw-tuning synthetic XBE: ``tt.read_any`` (the
    inspection report, tagged as an image), ``_xbe_bytes`` (the OLB final pass reads pool sites),
    the naming preflight/preview and the outcome measure.  The copy, the Anniversary preflight and
    final pass over the real synthetic XDVDFS archive, and the publication run unchanged."""

    def __init__(self, testcase):
        self.temporary = tempfile.TemporaryDirectory(prefix="espn25-integration-")
        testcase.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.catalog = fixtures()
        manifest = self.directory / "layout.json"
        espn.write_json(manifest, self.catalog.manifest)
        xbe = self.directory / "default.xbe"
        xbe.write_bytes(_build_synthetic_xbe())
        report = {**mod_build.tt.read_xbe(xbe), "container": "xiso"}
        from mod_editor.core import build_feedback
        for patch in (mock.patch.object(espn, "MANIFEST", manifest),
                      mock.patch.object(mod_build.tt, "read_any", side_effect=lambda _path: dict(report)),
                      mock.patch.object(mod_build.tt.modern_naming_patch, "image_status", return_value="retail"),
                      mock.patch.object(mod_build.tt.modern_naming_patch, "image_preview", return_value={}),
                      mock.patch.object(mod_build, "_xbe_bytes", side_effect=lambda _path: xbe.read_bytes()),
                      mock.patch.object(mod_build.tt, "_naming_source_preflight", return_value=None),
                      mock.patch.object(build_feedback, "measure", return_value={"message": "measured"})):
            patch.start()
            testcase.addCleanup(patch.stop)
        entries = [self.catalog.resources.get(i, (0xA0000000 + i, bytes(32))) for i in range(189)]
        self.image = SyntheticXiso(self.directory, entries, pack_sizes=(2 * 1024 * 1024,), pack_sectors=(512,)).path

    def foreign_image(self):
        """A copy whose SITU bytes are not the pinned layout: inspect must say foreign, never guess."""

        foreign = self.directory / "foreign.iso"
        foreign.write_bytes(self.image.read_bytes())
        with espn.rr._outer_image()(foreign, writable=True) as archive:
            entry = archive.entries[22]
            archive.write(entry.virtual_offset + 40, b"\xff" * 8)
        return foreign

    def plan_file(self, name="plan.json", **edits):
        plan = self.catalog.prepare({"schema": espn.SCHEMA, "moments": [{"moment": 0, "setup": {"home_score": 14}}],
                                     "rosters": [ROSTER_EDIT], **edits})
        path = self.directory / name
        espn.write_json(path, plan)
        return path, plan


class BuildPlanTests(unittest.TestCase):
    """BuildPlan field, presets, availability, inspection and the validation refusals."""

    def test_field_presets_availability_and_persistence(self):
        self.assertEqual(mod_build.BuildPlan("", "").espn25_plan, "")
        for name, preset in mod_build.PRESETS.items():
            self.assertEqual(preset.get("espn25_plan"), "", name)
            self.assertEqual(mod_build.apply_preset(mod_build.BuildPlan("a", "b", espn25_plan="x"), name).espn25_plan, "")
        self.assertTrue(mod_build.availability()["espn25_plan"])
        self.assertIn("espn25_plan", saved.FEATURE_KEYS)
        state = saved.from_plan(mod_build.BuildPlan("a", "b", espn25_plan="/tmp/plan.json"))
        self.assertEqual(state["espn25_plan"], "/tmp/plan.json")
        self.assertEqual(saved.to_plan(state, "s", "t").espn25_plan, "/tmp/plan.json")
        with self.assertRaisesRegex(ValueError, "espn25_plan must be text"):
            saved.build_settings({"espn25_plan": True})

    def test_bare_xbe_inspection_and_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            xbe = Path(tmp) / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            self.assertEqual(mod_build.inspect(xbe)["espn25_plan"], "requires image")
            plan = Path(tmp) / "plan.json"
            plan.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "need a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(Path(tmp) / "out.xbe"), espn25_plan=str(plan)))
            with self.assertRaisesRegex(ValueError, "espn25_plan must be text"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(Path(tmp) / "out.xbe"), espn25_plan=True))

    def test_image_inspection_conflicts_and_stale_plan_refuse_before_copying(self):
        fixture = _Fixture(self)
        self.assertEqual(mod_build.inspect(fixture.image)["espn25_plan"], "available")
        self.assertEqual(mod_build.inspect(fixture.foreign_image())["espn25_plan"], "foreign")
        path, _plan = fixture.plan_file()
        target = fixture.directory / "out.iso"
        copies = mock.patch.object(mod_build.shutil, "copyfile", side_effect=AssertionError("copied before validation"))
        with copies:
            for kwargs, message in (({"reserves_16": True}, "roster arena growth"),
                                    ({"created_teams_extra": 2}, "roster arena growth"),
                                    ({"position_pools": True}, "merged position pools")):
                with self.assertRaisesRegex(ValueError, message):
                    mod_build.build(mod_build.BuildPlan(str(fixture.image), str(target), espn25_plan=str(path), **kwargs))
            missing = mod_build.BuildPlan(str(fixture.image), str(target), espn25_plan=str(fixture.directory / "absent.json"))
            with self.assertRaisesRegex(ValueError, "plan is missing"):
                mod_build.build(missing)
            # a plan made against other bytes is refused before any copy
            stale = json.loads(path.read_text(encoding="utf-8"))
            stale["resources"][0]["before_sha256"] = "0" * 64
            stale_path = fixture.directory / "stale.json"
            stale_path.write_text(json.dumps(stale), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ESPN Anniversary plan refused"):
                mod_build.build(mod_build.BuildPlan(str(fixture.image), str(target), espn25_plan=str(stale_path)))
        self.assertFalse(target.exists())

    def test_final_pass_applies_after_copy_and_publishes_only_a_complete_result(self):
        fixture = _Fixture(self)
        path, plan = fixture.plan_file()
        target = fixture.directory / "built.iso"
        messages = []
        receipt = mod_build.build(mod_build.BuildPlan(str(fixture.image), str(target), espn25_plan=str(path)),
                                  lambda message, *_: messages.append(message))
        step = next(row for row in receipt["steps"] if row["step"] == "espn25_plan")
        self.assertEqual(receipt["steps"][-1]["step"], "espn25_plan", "the plan is the last pass")
        self.assertFalse(step["already_applied"])
        self.assertEqual(receipt["result"]["espn25_plan"], "applied")
        self.assertEqual(receipt["plan"]["espn25_plan"], str(path))
        self.assertIn("Applying ESPN Anniversary edits", messages)
        self.assertEqual(espn.status(target, plan), "applied")
        self.assertEqual(espn.status(fixture.image, plan), "ready", "the source is never written")
        self.assertEqual(mod_build.inspect(target)["espn25_plan"], "available")
        # a failing final pass discards the disposable output instead of publishing it
        second = fixture.directory / "second.iso"
        with mock.patch.object(espn, "apply_to_image", side_effect=espn.Espn25Error("injected")):
            with self.assertRaisesRegex(ValueError, "injected"):
                mod_build.build(mod_build.BuildPlan(str(fixture.image), str(second), espn25_plan=str(path)))
        self.assertFalse(second.exists())
        self.assertEqual(sorted(p.name for p in fixture.directory.iterdir() if p.name.startswith(".studio-build-")), [])


@unittest.skipIf(QT_ERROR, f"PyQt5 unavailable offscreen: {QT_ERROR}")
class RostersHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.fixture = _Fixture(self)
        self.panel = RosterEditorPanel()
        self.addCleanup(self.panel.deleteLater)
        self.addCleanup(self.panel.close)

    def _load(self, path=None):
        source = path or self.fixture.image
        # the fixture image has no main disc roster the live editor can parse; adopt a document directly
        document = self.fixture.catalog.roster_document(0, "away")
        self.panel.load_document(document, source=source, kind="disc")
        return _wait(self.app, lambda: self.panel.espn25_ready() or "unavailable" in self.panel.status_label.text())

    def test_subtab_is_disabled_until_a_supported_source_loads_then_enabled(self):
        panel = self.panel
        index = panel._espn25_index
        self.assertEqual(panel.pages.tabText(index), "ESPN Anniversary")
        self.assertFalse(panel.pages.isTabEnabled(index))
        self.assertTrue(panel.pages.tabBar().isVisibleTo(panel), "the Anniversary tab keeps the tab bar visible")
        # a save (no scenarios) keeps it disabled; the live roster editor is untouched
        panel.load_document(self.fixture.catalog.roster_document(0, "away"), kind="save")
        self.assertFalse(panel.pages.isTabEnabled(index))
        self.assertIn("need a game disc", panel.pages.tabToolTip(index))
        self.assertTrue(self._load())
        self.assertTrue(panel.espn25_ready())
        self.assertTrue(panel.pages.isTabEnabled(index))
        self.assertEqual(panel.espn25_panel.moments.count(), 25)
        self.assertEqual(panel.espn25_panel.table.rowCount(), 53)
        self.assertFalse(panel.is_dirty())
        panel.show_espn25()
        self.assertEqual(panel.pages.currentIndex(), index)

    def test_layout_refusal_uses_the_status_line_and_keeps_the_tab_disabled(self):
        panel = self.panel
        foreign = self.fixture.directory / "foreign.iso"
        foreign.write_bytes(b"not an image" * 64)
        self.assertTrue(self._load(foreign))
        self.assertFalse(panel.espn25_ready())
        self.assertFalse(panel.pages.isTabEnabled(panel._espn25_index))
        self.assertIn("ESPN Anniversary is unavailable for this disc", panel.status_label.text())
        self.assertIn("unavailable", panel.pages.tabToolTip(panel._espn25_index))

    def test_pending_edits_make_the_host_dirty_until_a_plan_is_saved(self):
        panel = self.panel
        self.assertTrue(self._load())
        page = panel.espn25_panel
        page.shared.setChecked(True)
        page.import_csv_text(ROSTER_EDIT["csv"])
        self.assertTrue(panel.espn25_dirty())
        self.assertTrue(panel.is_dirty(), "unsaved Anniversary edits survive the shell's routine refresh guard")
        received = []
        panel.espn25_plan_changed.connect(received.append)
        path = self.fixture.directory / "saved-plan.json"
        page.save_plan(path)
        self.assertEqual(received, [str(path)])
        self.assertEqual(panel.espn25_plan_path, str(path))
        self.assertFalse(panel.espn25_dirty(), "a saved plan is not lost by a reload")
        self.assertIn("Use saved ESPN Anniversary edits", panel.status_label.text())
        self.assertEqual(espn.read_json(path)["schema"], espn.PLAN_SCHEMA)
        # editing again after the save is dirty again
        page.import_csv_text("pool,index,speed\nprimary,1,77\n")
        self.assertTrue(panel.espn25_dirty())

    def test_recovery_snapshot_restores_only_against_the_matching_catalog(self):
        panel = self.panel
        self.assertTrue(self._load())
        page = panel.espn25_panel
        self.assertIsNone(panel.espn25_recovery_snapshot())
        page.shared.setChecked(True)
        page.import_csv_text(ROSTER_EDIT["csv"])
        page.scenario_json.setPlainText('{"schema": "%s", "moments": []}' % espn.SCHEMA)
        snapshot = panel.espn25_recovery_snapshot()
        self.assertEqual(snapshot["schema"], RosterEditorPanel.ESPN25_RECOVERY_SCHEMA)
        self.assertEqual(json.loads(json.dumps(snapshot)), snapshot, "JSON-safe")
        self.assertEqual([outer for outer, _row in snapshot["pending"]], [113])
        # a fresh host restores after its matching catalog has loaded
        other = RosterEditorPanel()
        self.addCleanup(other.deleteLater)
        self.assertFalse(other.restore_espn25_recovery(snapshot), "queued until the catalog loads")
        other.load_document(self.fixture.catalog.roster_document(0, "away"), source=self.fixture.image, kind="disc")
        self.assertTrue(_wait(self.app, lambda: other.espn25_ready()))
        self.assertEqual(set(other.espn25_panel.pending), {113})
        self.assertEqual(other.espn25_panel.table.item(0, espn.CSV_COLUMNS.index("jersey")).text(), "12")
        self.assertTrue(other.espn25_panel.shared.isChecked())
        self.assertIn("moments", other.espn25_panel.scenario_json.toPlainText())
        self.assertTrue(other.espn25_dirty())
        # a snapshot from other bytes is refused, never applied
        third = RosterEditorPanel()
        self.addCleanup(third.deleteLater)
        third.load_document(self.fixture.catalog.roster_document(0, "away"), source=self.fixture.image, kind="disc")
        self.assertTrue(_wait(self.app, lambda: third.espn25_ready()))
        foreign = json.loads(json.dumps(snapshot))
        foreign["identity"]["situ_sha256"] = "0" * 64
        self.assertFalse(third.restore_espn25_recovery(foreign))
        self.assertEqual(third.espn25_panel.pending, {})
        self.assertIn("not restored", third.status_label.text())
        with self.assertRaises(ValueError):
            third.restore_espn25_recovery({"schema": "other"})

    def test_explicit_reload_replaces_the_catalog_and_the_replace_prompt_names_the_edits(self):
        panel = self.panel
        self.assertTrue(self._load())
        panel.espn25_panel.shared.setChecked(True)
        panel.espn25_panel.import_csv_text(ROSTER_EDIT["csv"])
        self.assertTrue(panel.is_dirty())
        with mock.patch("mod_editor.gui.roster_editor_panel_qt.QMessageBox") as box_class:
            box = box_class.return_value
            box.clickedButton.return_value = box.addButton.return_value   # "Keep editing"
            self.assertFalse(panel._confirm_replace())
            self.assertIn("ESPN Anniversary", box.setText.call_args[0][0])
        self.assertTrue(self._load())
        self.assertEqual(panel.espn25_panel.pending, {})
        self.assertFalse(panel.is_dirty())


@unittest.skipIf(QT_ERROR, f"PyQt5 unavailable offscreen: {QT_ERROR}")
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_text_note_and_conflict_helper_surface(self):
        self.assertEqual(ESPN_25TH_COMING_SOON_NOTE,
                         "Edit Anniversary setup and shared historic rosters in Rosters > ESPN Anniversary. "
                         "Experimental and unwitnessed. Extra moments can be validated for research; "
                         "installation is unavailable.")
        self.assertEqual(SITU_BANK_PREFIX, "nfl2k5.text-bank.situ.")

    def test_gameplay_row_is_informational_image_only_and_opens_rosters(self):
        keys = [key for key, _l, _e in PATCHES]
        self.assertIn("espn25_plan", keys)
        self.assertEqual(INFORMATIONAL, {"espn25_plan"})
        self.assertIn("espn25_plan", NEEDS_IMAGE)
        text = dict((key, explanation) for key, _l, explanation in PATCHES)["espn25_plan"]
        self.assertEqual(text, "Retail uses 25 moments and shared historic teams. Patch applies your saved Anniversary "
                               "setup and roster edits. Extra moments remain unavailable. Experimental and unwitnessed.")
        with tempfile.TemporaryDirectory() as tmp:
            xbe = Path(tmp) / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            panel = GameplayPatchesPanel()
            try:
                opened = []
                panel.open_anniversary.connect(lambda: opened.append(True))
                panel.apply_state(mod_build.inspect(xbe))
                self.assertNotIn("espn25_plan", panel.checks, "never a Boolean plan field")
                self.assertEqual(panel.badges["espn25_plan"].text(), "Full disc required")
                panel.anniversary_button.click()
                self.assertEqual(opened, [True])
                panel.target_field.setText(str(Path(tmp) / "out.xbe"))
                panel.checks["draft_ai"].setChecked(True)
                self.assertEqual(panel.plan().espn25_plan, "")
                panel.apply_state({**mod_build.inspect(xbe), "container": "xiso", "espn25_plan": "foreign"})
                self.assertEqual(panel.badges["espn25_plan"].text(), "Unrecognized source data")
            finally:
                panel.deleteLater()
                self.app.processEvents()

    def test_build_option_plan_picker_blocker_and_presets(self):
        panel = BuildPanel()
        try:
            self.assertEqual(panel.espn25_plan_check.text(), "Use saved ESPN Anniversary edits")
            self.assertEqual(len("Use saved ESPN Anniversary edits"), 32)   # the WIRING caption verbatim (its "31" count is off by one)
            self.assertIn("espn25_plan", panel._boxes())
            self.assertIn("espn25_plan", {f.name for f in dataclasses.fields(mod_build.BuildPlan)})
            # a bare executable first (before the fixture answers every path as an image)
            with tempfile.TemporaryDirectory() as tmp:
                xbe = Path(tmp) / "default.xbe"
                xbe.write_bytes(_build_synthetic_xbe())
                panel.apply_state(mod_build.inspect(xbe))
                self.assertFalse(panel.espn25_plan_check.isEnabled())
                self.assertEqual(panel._badges["espn25_plan"].text(), "Full disc required")
            fixture = _Fixture(self)
            path, _plan = fixture.plan_file()
            panel.apply_state(mod_build.inspect(fixture.foreign_image()))
            self.assertFalse(panel.espn25_plan_check.isEnabled())
            self.assertEqual(panel._badges["espn25_plan"].text(), "Unrecognized source data")
            panel.apply_state(mod_build.inspect(fixture.image))
            self.assertTrue(panel.espn25_plan_check.isEnabled())
            self.assertFalse(panel.espn25_plan_check.isChecked())
            for name in mod_build.PRESETS:
                panel.apply_preset(name)
                self.assertFalse(panel.espn25_plan_check.isChecked(), f"{name} must not enable user content")
            panel.target_field.setText(str(fixture.directory / "out.iso"))
            panel.espn25_plan_check.setChecked(True)
            self.assertTrue(panel.espn25_row.isVisibleTo(panel))
            self.assertEqual(panel.blocker(), "Save build edits on ★ Rosters > ESPN Anniversary or choose a plan JSON file.")
            bad = fixture.directory / "bad.json"
            bad.write_text('{"schema": "other"}', encoding="utf-8")
            panel.set_espn25_plan(str(bad))
            self.assertFalse(panel.espn25_plan_check.isChecked(), "checking requires a validated plan")
            self.assertIn("cannot be used", panel.espn25_plan_status.text())
            panel.set_espn25_plan(str(path))
            self.assertTrue(panel.espn25_plan_check.isChecked())
            self.assertEqual(panel.blocker(), "")
            self.assertEqual(panel.plan().espn25_plan, str(path))
            self.assertIn("Use saved ESPN Anniversary edits", panel.selected_labels())
            self.assertIn(f"ESPN Anniversary plan: {path.name}", panel.confirmation_text(panel.plan()))
            state = panel.project_build_settings()
            self.assertEqual(state["espn25_plan"], str(path))
            panel.espn25_plan_check.setChecked(False)
            self.assertEqual(panel.plan().espn25_plan, "", "unchecking clears the plan")
            panel.restore_project_build_settings(state)
            self.assertTrue(panel.espn25_plan_check.isChecked())
            self.assertEqual(panel.espn25_plan_field.text(), str(path))
        finally:
            panel.deleteLater()
            self.app.processEvents()


@unittest.skipIf(QT_ERROR, f"PyQt5 unavailable offscreen: {QT_ERROR}")
class TextConflictTests(unittest.TestCase):
    """The four-string editor and the Anniversary plan share SITU: the shell asks which strings are pending."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_anniversary_pending_edits_lists_only_changed_situ_strings(self):
        from mod_editor.core.nfl2k5_text_catalog import Nfl2k5TextCatalog, TextBank
        from mod_editor.gui.text_rosters_panel import TextRosterPanel
        from test_text_rosters_panel import FakeHost, catalog_fixture, text_asset
        base = catalog_fixture()
        bank = TextBank(SITU_BANK_PREFIX + "22.0", "SITU", "ESPN 25th Anniversary moments", 22, 0, True, "mixed", 2, "")
        title = text_asset("nfl2k5.text.situ.moment.0.title", bank.bank_id, "Retail title", outer=22,
                           owner_kind="situ_moment", owner_index=0, field="title")
        date = text_asset("nfl2k5.text.situ.moment.0.date", bank.bank_id, "Retail date", outer=22,
                          owner_kind="situ_moment", owner_index=0, field="date")
        catalog = Nfl2k5TextCatalog(base.banks + (bank,), base.assets + (title, date), base.teams, base.players,
                                    base.number_assets)
        host = FakeHost(catalog)
        panel = TextRosterPanel(host, view="text")
        try:
            self.assertEqual(panel.anniversary_pending_edits(), (), "nothing before the catalog loads")
            panel.reload()
            self.assertEqual(panel.anniversary_pending_edits(), ())
            host.text["nfl2k5.text.situ.moment.0.title"] = "Edited title"
            host.text["text.5.primary_players.0.first"] = "Other"       # a roster string is no Anniversary conflict
            self.assertEqual(panel.anniversary_pending_edits(), ("nfl2k5.text.situ.moment.0.title",))
            host.text.pop("nfl2k5.text.situ.moment.0.title")
            self.assertEqual(panel.anniversary_pending_edits(), ())
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()

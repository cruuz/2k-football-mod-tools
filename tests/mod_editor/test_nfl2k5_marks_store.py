"""Saved SOFTDRINK logos: synthetic files only, with real pack and pin checks."""
import contextlib
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(Path(__file__).parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from mod_editor.core import modpack as m, nfl2k5_official_marks as marks, nfl2k5_marks_store as store
from official_marks_fixture import softdrink_pack


class StoreFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack, pins = softdrink_pack(self.root / "input")
        self.state = self.root / "state"
        for patcher in (mock.patch.object(store, "state_root", return_value=self.state),
                        mock.patch.dict(os.environ, {marks.ENVIRONMENT: ""}),
                        mock.patch.dict(marks.ASSETS, pins, clear=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        from mod_editor.core import nfl2k5_espn_marks, nfl2k5_espn_wipes_boards
        for module in (nfl2k5_espn_marks, nfl2k5_espn_wipes_boards):
            document = dict(module._pins(), art=module.art_pins(self.pack.parent / "marks"))
            patcher = mock.patch.object(module, "_pins", return_value=document)
            patcher.start()
            self.addCleanup(patcher.stop)

    def rewrite(self, change):
        with zipfile.ZipFile(self.pack) as z:
            entries = {n: z.read(n) for n in z.namelist()}
        change(entries)
        with zipfile.ZipFile(self.pack, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in entries.items():
                z.writestr(name, data)


class StoreTests(StoreFixture, unittest.TestCase):
    def test_registration_retains_only_marks_and_provenance_and_checks_all_ten_features(self):
        source = store.register_pack(self.pack)
        folder = Path(source["folder"])
        self.assertEqual(store.registered_source(), source)
        self.assertEqual(source["name"], "SOFTDRINK 2K28")
        self.assertEqual(source["version"], m.load(self.pack).manifest.version)
        self.assertEqual(source["sha256"], m.hash_file(self.pack))
        self.assertRegex(source["saved_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual({p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()},
                         set(marks.ASSETS) | {"manifest.json", "source.json"})
        features = {r["feature"] for r in marks.CATALOG.values()}
        self.assertEqual(len(features), 10)
        for feature in features:
            marks.validate_feature(feature)
        for name in marks.ASSETS:
            marks.asset_path(name)
        self.assertFalse(list(self.state.glob(".saving-*")))

    def test_precedence_and_frozen_build_scope_receipt(self):
        source = store.register_pack(self.pack)
        self.assertEqual(marks.selected_root(), source["folder"])
        with mock.patch.dict(os.environ, {marks.ENVIRONMENT: "environment"}):
            self.assertEqual(marks.selected_root(), "environment")
            with marks.using_pack("recipe"):
                self.assertEqual(marks.selected_root(), "recipe")
                self.assertEqual(marks.selected_root("field"), "field")
            self.assertEqual(marks.selected_root(), "environment")
        @marks.build_scope
        def fake_build(plan):
            # A changed default cannot redirect an in-progress build.
            with mock.patch.object(store, "registered_root", return_value="different"):
                self.assertEqual(marks.selected_root(), source["folder"])
            return {"plan": {"official_marks_pack": plan.official_marks_pack}}
        receipt = fake_build(SimpleNamespace(official_marks_pack="", modern_sofi=True))
        self.assertEqual(receipt["official_marks_pack"], source["folder"])

    def test_no_marks_leaves_saved_copy_and_date_unchanged(self):
        old = store.register_pack(self.pack)
        pack = m.load(self.pack)
        pack.manifest = replace(pack.manifest, recipe={})
        self.assertIsNone(store.register_pack(pack))
        self.assertEqual(store.registered_source(), old)

    def test_no_marks_creates_no_state(self):
        pack = m.load(self.pack)
        pack.manifest = replace(pack.manifest, recipe={})
        self.assertIsNone(store.register_pack(pack))
        self.assertFalse(self.state.exists())

    def test_long_unicode_storage_without_resolve(self):
        root = store.f._path(self.root / ("données " + "a" * 75) / ("logos " + "b" * 75) / ("été " + "c" * 75))
        with mock.patch.object(store, "state_root", return_value=root), \
             mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
            source = store.register_pack(self.pack)
            self.assertEqual(store.registered_root(), source["folder"])
            for name in marks.ASSETS:
                marks.asset_path(name)

    def test_tampered_tree_preserves_valid_copy(self):
        old = store.register_pack(self.pack)
        self.rewrite(lambda e: e.__setitem__("assets/trees/logos/nfl_chiclet.png", b"tampered"))
        with self.assertRaises((ValueError, OSError)):
            store.register_pack(self.pack)
        self.assertEqual(store.registered_source(), old)
        marks.asset_path("nfl_chiclet.png")

    def test_unreviewed_pin_is_refused_even_with_valid_pack_hash(self):
        old = store.register_pack(self.pack)
        def corrupt(entries):
            name = "assets/trees/logos/nfl_chiclet.png"
            entries[name] += b"tamper"
            doc = json.loads(entries["manifest.json"])
            row = next(a for a in doc["assets"] if a["member"] == name)
            row.update(length=len(entries[name]), sha256=hashlib.sha256(entries[name]).hexdigest())
            entries["manifest.json"] = json.dumps(doc).encode()
        self.rewrite(corrupt)
        with self.assertRaisesRegex(ValueError, "PNG differs"):
            store.register_pack(self.pack)
        self.assertEqual(store.registered_source(), old)

    def test_escaping_tree_or_manifest_is_refused(self):
        pack = m.load(self.pack)
        for token in ("@pack/assets/trees/../../escape", "@pack/assets/trees/C:/escape", "/outside"):
            pack.manifest = replace(pack.manifest, recipe={"overrides": {"official_marks_pack": token}})
            with self.subTest(token=token), self.assertRaises(ValueError):
                store.register_pack(pack)
        self.assertFalse(self.state.exists())
        def escape(entries):
            name = "assets/trees/logos/manifest.json"
            doc = json.loads(entries[name])
            doc["marks"]["nfl_chiclet.png"]["file"] = "../escape.png"
            entries[name] = json.dumps(doc).encode()
            manifest = json.loads(entries["manifest.json"])
            row = next(a for a in manifest["assets"] if a["member"] == name)
            row.update(length=len(entries[name]), sha256=hashlib.sha256(entries[name]).hexdigest())
            entries["manifest.json"] = json.dumps(manifest).encode()
        self.rewrite(escape)
        with self.assertRaisesRegex(ValueError, "path escapes"):
            store.register_pack(self.pack)
        self.assertIsNone(store.registered_source())

    def test_failed_pointer_publish_keeps_previous_copy(self):
        old = store.register_pack(self.pack)
        original = store.f._transaction
        def transaction(path, *args, **kwargs):
            if Path(path).name == "current.json":
                raise OSError("synthetic publish failure")
            return original(path, *args, **kwargs)
        with mock.patch.object(store.f, "_transaction", side_effect=transaction), self.assertRaises(OSError):
            store.register_pack(self.pack)
        self.assertEqual(store.registered_source(), old)
        self.assertEqual(len(list(self.state.glob("logos-*"))), 1)

    def test_install_failure_to_save_does_not_hide_disc_success(self):
        with mock.patch.object(store, "register_pack", side_effect=OSError("disk full")):
            receipt = store.after_install(m.load(self.pack), {"target": {"path": "ready.iso"}})
        self.assertIn("disk full", receipt["official_marks_error"])
        self.assertEqual(receipt["target"]["path"], "ready.iso")

    def test_cli_apply_saves_logos_tip_and_json_stays_json(self):
        from tools import nfl2k5_modpack as cli
        for memory, json_mode in ((True, False), (False, False), (True, True)):
            pack = m.load(self.pack)
            pack.manifest.recipe["overrides"]["k128_memory"] = memory
            stdout, stderr = io.StringIO(), io.StringIO()
            output = self.root / f"cli-{memory}-{json_mode}.iso"
            with mock.patch.object(m, "load", return_value=pack), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = cli.main(["apply", str(self.pack), "--source", str(self.pack.parent / "base.iso"),
                                   "--out", str(output)] + (["--json"] if json_mode else []))
            self.assertEqual(result, 0, stderr.getvalue())
            self.assertEqual(output.read_bytes(), (self.pack.parent / "built.iso").read_bytes())
            text = stdout.getvalue()
            if json_mode:
                doc = json.loads(text)
                self.assertEqual(doc["memory_tip"], store.MEMORY_TIP)
                self.assertIn("SOFTDRINK logos saved", stderr.getvalue())
            else:
                self.assertIn("SOFTDRINK logos saved", text)
                self.assertEqual(store.MEMORY_TIP in text.splitlines()[-1], memory)


class StateRootTests(unittest.TestCase):
    def test_windows_macos_linux_state_paths(self):
        with mock.patch.object(store.platform_compat, "user_private_root", return_value=Path("/users/noah")), \
             mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/xdg-data"}):
            for windows, system, suffix in ((True, "win32", "users/noah"),
                                            (False, "darwin", "users/noah/Library/Application Support"),
                                            (False, "linux", "xdg-data")):
                with mock.patch.object(store.platform_compat, "IS_WINDOWS", windows), mock.patch.object(store.sys, "platform", system):
                    self.assertTrue(str(store.state_root()).replace("\\", "/").endswith(suffix + "/2k5-mod-studio/official-marks"))


class GuiTests(StoreFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def wait(self, predicate):
        until = time.monotonic() + 30
        while predicate() and time.monotonic() < until:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(predicate())

    def test_build_import_button_all_ten_gates_and_source_label(self):
        from mod_editor.gui.build_panel_qt import BuildPanel, QFileDialog
        panel = BuildPanel()
        warning = mock.patch("mod_editor.gui.build_panel_qt.QMessageBox.warning")
        warning.start()
        self.addCleanup(warning.stop)
        try:
            features = {r["feature"] for r in marks.CATALOG.values()}
            panel._state = {"container": "xiso", **{key: "retail" for key in features}}
            panel._official_marks_pack_changed()
            for key in features:
                self.assertFalse(panel._boxes()[key].isEnabled(), key)
            self.assertIn("Install SOFTDRINK 2K28", panel.official_marks_status.text())
            self.assertEqual(panel.official_marks_import_button.text(), "From a SOFTDRINK pack...")
            self.assertNotIn("release does not include", panel.official_marks_pack_field.toolTip())
            with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.pack), "")), \
                 mock.patch.object(m, "apply", side_effect=AssertionError("No installation for logo import")):
                panel.official_marks_import_button.click()
                self.wait(lambda: panel._marks_task is not None)
            self.assertIn("SOFTDRINK 2K28 logos, saved on", panel.official_marks_status.text())
            for key in features:
                self.assertTrue(panel._boxes()[key].isEnabled(), key)
            panel.official_marks_pack_field.setText(str(self.root / "missing"))
            self.assertIn("Chosen logo folder", panel.official_marks_status.text())
            for key in features:
                self.assertFalse(panel._boxes()[key].isEnabled(), key)
            panel.official_marks_pack_field.clear()
            self.assertTrue(all(panel._boxes()[key].isEnabled() for key in features))
            panel._state["modern_sofi"] = "foreign"
            panel._official_marks_pack_changed()
            self.assertFalse(panel.modern_sofi_check.isEnabled())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_share_install_saves_and_disc_ready_tip_is_conditional(self):
        from mod_editor.gui.share_panel_qt import SharePanel
        from mod_editor.gui.ux_text import XEMU_LINE
        panel = SharePanel()
        notices = []
        panel._notify = lambda *args: notices.append(args)
        try:
            for memory in (True, False):
                panel.load_pack(self.pack)
                panel._pack.manifest.recipe["overrides"]["k128_memory"] = memory
                panel.source_field.setText(str(self.pack.parent / "base.iso"))
                panel.target_field.setText(str(self.root / f"share-{memory}.iso"))
                panel.start_file_install()
                self.wait(lambda: panel.busy)
                self.assertIsNotNone(store.registered_source())
                self.assertEqual(notices[-1][1], "Disc ready", notices)
                self.assertIn(XEMU_LINE, notices[-1][2])
                self.assertEqual(store.MEMORY_TIP in notices[-1][2], memory)
                self.assertEqual(store.MEMORY_TIP in panel.apply_status.text(), memory)
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_customize_saves_logos_before_emitting_recipe(self):
        from mod_editor.gui.share_panel_qt import SharePanel, QFileDialog
        panel = SharePanel()
        panel._notify = lambda *args: None
        recipes = []
        panel.customization_ready.connect(recipes.append)
        try:
            with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.pack), "")), \
                 mock.patch.object(QFileDialog, "getExistingDirectory", return_value=str(self.root / "custom")):
                panel.customize_softdrink()
                self.wait(lambda: panel.busy)
            self.assertEqual(len(recipes), 1)
            self.assertIsNotNone(store.registered_source())
            self.assertTrue(Path(recipes[0]["overrides"]["official_marks_pack"]).is_dir())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_customize_still_finishes_when_the_logo_save_fails(self):
        # main 76.1: the extracted sources carry their own logos, so a failed save only reports.
        from mod_editor.gui.share_panel_qt import SharePanel, QFileDialog
        panel = SharePanel()
        panel._notify = lambda *args: None
        recipes = []
        panel.customization_ready.connect(recipes.append)
        try:
            with mock.patch.object(store, "register_pack", side_effect=OSError("read-only state folder")), \
                 mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.pack), "")), \
                 mock.patch.object(QFileDialog, "getExistingDirectory", return_value=str(self.root / "custom2")):
                panel.customize_softdrink()
                self.wait(lambda: panel.busy)
            self.assertEqual(len(recipes), 1)
            self.assertIsNone(store.registered_source())
            self.assertTrue(Path(recipes[0]["overrides"]["official_marks_pack"]).is_dir())
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_try_register_reports_instead_of_raising(self):
        with mock.patch.object(store, "register_pack", side_effect=OSError("disk full")):
            saved, error = store.try_register(m.load(self.pack))
        self.assertIsNone(saved)
        self.assertIn("disk full", error)


if __name__ == "__main__":
    unittest.main()

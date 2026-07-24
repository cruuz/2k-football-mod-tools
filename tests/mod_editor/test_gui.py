"""Display-free regression tests for Tkinter control-state orchestration."""

from __future__ import annotations

import queue
from pathlib import Path
import unittest
from unittest import mock

from mod_editor.core.apf_export import ApfJerseyExportResult
from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.controller import ModEditorController
from mod_editor.core.errors import ModEditorError
from mod_editor.core.model import GameId
from mod_editor.gui.tkinter_app import ModEditorApp


SCOREBUG_CAPABILITY_ID = "nfl2k5.scorebug_presentation.inventory"
APF_CAPABILITY_ID = "apf2k8.uniforms.jersey_00_23"
APF_PANTS_CAPABILITY_ID = "apf2k8.uniforms.pants_color_00_23"
APF_HELMET_CAPABILITY_ID = "apf2k8.uniforms.helmet_color_00_23"
APF_SHOULDER_CAPABILITY_ID = "apf2k8.uniforms.shoulder_color_00_23"
APF_DIGITAL_FONT_CAPABILITY_ID = "apf2k8.scorebug_presentation.digital_font"
NFL_SLIDER_CAPABILITY_ID = "nfl2k5.gameplay_tuning_sliders.rating_view"
APF_MENU_CAPABILITY_ID = "apf2k8.menus.layouts"
APF_SCOREBUG_CAPABILITY_ID = "apf2k8.scorebug_presentation.inventory"
APF_UNIFORM_CATALOG_CAPABILITY_ID = "apf2k8.uniforms.catalog"
NFL_SAVE_CAPABILITY_ID = "nfl2k5.saves.dashboard"


class _Widget:
    def __init__(self) -> None:
        self.state: str | None = None

    def config(self, **values) -> None:
        if "state" in values:
            self.state = values["state"]


class _CapabilityTree(_Widget):
    def __init__(self, row: str) -> None:
        super().__init__()
        self.row = row

    def selection(self) -> tuple[str, ...]:
        return (self.row,)


class _Status:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _Root:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []

    def after(self, delay: int, callback) -> None:
        self.after_calls.append((delay, callback))


def _app_with_selected(capability_id: str) -> ModEditorApp:
    registry = CapabilityRegistryLoader().load(
        allow_sample_fallback=False, check_files=False
    )
    controller = ModEditorController(registry)
    game = GameId.APF2K8 if capability_id.startswith("apf2k8.") else GameId.NFL2K5
    controller.create_project("GUI state test", game)

    app = ModEditorApp.__new__(ModEditorApp)
    app.controller = controller
    app._jobs = queue.Queue()
    app._busy = True
    app.root = _Root()
    app.status_var = _Status()
    row = "selected-capability-row"
    app.capability_tree = _CapabilityTree(row)
    app._capability_by_row = {row: registry.get(capability_id)}
    app.add_button = _Widget()
    app.provider_import_button = _Widget()
    app.provider_recipe_button = _Widget()
    app.apf_export_button = _Widget()
    app.mapped_inspect_button = _Widget()
    app.remove_button = _Widget()
    app.provider_validate_button = _Widget()
    app.provider_build_button = _Widget()
    app._project_widgets = [app.capability_tree]
    app._set_detail = lambda _text: None
    app._refresh_project_label = lambda: None
    app._refresh_log = lambda: None
    return app


class GuiControlStateTests(unittest.TestCase):
    def test_selected_actions_restore_after_success_and_error(self) -> None:
        for capability_id, export_state, inspect_state in (
            (SCOREBUG_CAPABILITY_ID, "disabled", "disabled"),
            (APF_CAPABILITY_ID, "normal", "normal"),
            (APF_PANTS_CAPABILITY_ID, "disabled", "normal"),
            (APF_HELMET_CAPABILITY_ID, "disabled", "normal"),
            (APF_SHOULDER_CAPABILITY_ID, "disabled", "normal"),
            (APF_DIGITAL_FONT_CAPABILITY_ID, "disabled", "normal"),
        ):
            for kind in ("success", "error"):
                with self.subTest(capability=capability_id, kind=kind):
                    app = _app_with_selected(capability_id)
                    callbacks: list[object] = []
                    errors: list[BaseException] = []
                    app._show_error = errors.append
                    payload: object = (
                        object()
                        if kind == "success"
                        else ModEditorError("synthetic failure")
                    )
                    callback = callbacks.append if kind == "success" else None
                    app._jobs.put((kind, payload, callback))

                    app._poll_jobs()

                    self.assertFalse(app._busy)
                    self.assertEqual(app.add_button.state, "disabled")
                    self.assertEqual(app.provider_import_button.state, "normal")
                    self.assertEqual(app.provider_recipe_button.state, "normal")
                    self.assertEqual(app.apf_export_button.state, export_state)
                    self.assertEqual(app.mapped_inspect_button.state, inspect_state)
                    self.assertEqual(app.remove_button.state, "normal")
                    self.assertEqual(app.provider_validate_button.state, "disabled")
                    self.assertEqual(app.provider_build_button.state, "disabled")
                    self.assertEqual(
                        app.status_var.value,
                        "Ready" if kind == "success" else "Operation failed",
                    )
                    self.assertEqual(
                        callbacks, [payload] if kind == "success" else []
                    )
                    self.assertEqual(errors, [payload] if kind == "error" else [])
                    self.assertEqual(len(app.root.after_calls), 1)

    def test_apf_export_collects_only_safe_inputs_and_defers_work(self) -> None:
        app = _app_with_selected(APF_CAPABILITY_ID)
        app._busy = False
        started: list[tuple[str, object, object]] = []
        app._start_job = lambda label, function, success: started.append(
            (label, function, success)
        )
        result = ApfJerseyExportResult(
            Path("/new/export"), Path("/new/export/provenance.json"), 23, 11
        )
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.askopenfilename",
                return_value="/owned/0A",
            ),
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=23
            ) as choose_asset,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.asksaveasfilename",
                return_value="/new/export",
            ),
            mock.patch(
                "mod_editor.gui.tkinter_app.export_apf_jersey", return_value=result
            ) as backend,
        ):
            app._export_apf_jersey()
            backend.assert_not_called()
            self.assertEqual(len(started), 1)
            label, function, success = started[0]
            self.assertIn("asset 23", label)
            self.assertEqual(function(), result)
            backend.assert_called_once_with(
                source_0a=Path("/owned/0A"),
                asset_index=23,
                output_dir=Path("/new/export"),
            )
            self.assertEqual(choose_asset.call_args.kwargs["minvalue"], 0)
            self.assertEqual(choose_asset.call_args.kwargs["maxvalue"], 23)
            with mock.patch(
                "mod_editor.gui.tkinter_app.messagebox.showinfo"
            ) as showinfo:
                success(result)
            report = showinfo.call_args.args[1]
            self.assertIn("/new/export/provenance.json", report)
            self.assertIn("no archive bytes were written", report)
            self.assertIn("bank 0 and bank 1", report)

    def test_pants_recipe_creator_collects_bounded_opaque_png_inputs_and_imports(self) -> None:
        app = _app_with_selected(APF_PANTS_CAPABILITY_ID)
        app._refresh_queue = lambda: None
        app._refresh_project_label = lambda: None
        created = Path("/new/apf2k8-pants-13.json")
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=13
            ) as choose,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.askopenfilename",
                return_value="/art/pants.png",
            ) as choose_png,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.asksaveasfilename",
                return_value=str(created),
            ) as choose_recipe,
            mock.patch(
                "mod_editor.gui.tkinter_app.create_apf_pants_recipe",
                return_value=created,
            ) as creator,
            mock.patch.object(
                app.controller, "import_provider_project"
            ) as importer,
            mock.patch("mod_editor.gui.tkinter_app.messagebox.showinfo") as showinfo,
        ):
            app._create_provider_recipe()
        creator.assert_called_once_with(
            output=created, asset_index=13, png=Path("/art/pants.png")
        )
        importer.assert_called_once_with(APF_PANTS_CAPABILITY_ID, created)
        self.assertEqual(choose.call_args.kwargs["minvalue"], 0)
        self.assertEqual(choose.call_args.kwargs["maxvalue"], 23)
        self.assertIn("opaque 512x512", choose_png.call_args.kwargs["title"])
        self.assertEqual(
            choose_recipe.call_args.kwargs["initialfile"], "apf2k8-pants-13.json"
        )
        self.assertIn(str(created), showinfo.call_args.args[1])

    def test_helmet_recipe_creator_names_raw_rg_contract_and_imports(self) -> None:
        app = _app_with_selected(APF_HELMET_CAPABILITY_ID)
        app._refresh_queue = lambda: None
        app._refresh_project_label = lambda: None
        created = Path("/new/apf2k8-helmet-16.json")
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=16
            ) as choose,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.askopenfilename",
                return_value="/art/helmet-rg.png",
            ) as choose_png,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.asksaveasfilename",
                return_value=str(created),
            ) as choose_recipe,
            mock.patch(
                "mod_editor.gui.tkinter_app.create_apf_helmet_recipe",
                return_value=created,
            ) as creator,
            mock.patch.object(
                app.controller, "import_provider_project"
            ) as importer,
            mock.patch("mod_editor.gui.tkinter_app.messagebox.showinfo"),
        ):
            app._create_provider_recipe()
        creator.assert_called_once_with(
            output=created, asset_index=16, png=Path("/art/helmet-rg.png")
        )
        importer.assert_called_once_with(APF_HELMET_CAPABILITY_ID, created)
        self.assertEqual(choose.call_args.kwargs["minvalue"], 0)
        self.assertEqual(choose.call_args.kwargs["maxvalue"], 23)
        self.assertIn("R/G data, B=0, A=255", choose_png.call_args.kwargs["title"])
        self.assertEqual(
            choose_recipe.call_args.kwargs["initialfile"], "apf2k8-helmet-16.json"
        )

    def test_shoulder_recipe_creator_collects_bounded_rgba_png_and_imports(self) -> None:
        app = _app_with_selected(APF_SHOULDER_CAPABILITY_ID)
        app._refresh_queue = lambda: None
        app._refresh_project_label = lambda: None
        created = Path("/new/apf2k8-shoulder-08.json")
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=8
            ) as choose,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.askopenfilename",
                return_value="/art/shoulder.png",
            ) as choose_png,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.asksaveasfilename",
                return_value=str(created),
            ) as choose_recipe,
            mock.patch(
                "mod_editor.gui.tkinter_app.create_apf_shoulder_recipe",
                return_value=created,
            ) as creator,
            mock.patch.object(app.controller, "import_provider_project") as importer,
            mock.patch("mod_editor.gui.tkinter_app.messagebox.showinfo"),
        ):
            app._create_provider_recipe()
        creator.assert_called_once_with(
            output=created, asset_index=8, png=Path("/art/shoulder.png")
        )
        importer.assert_called_once_with(APF_SHOULDER_CAPABILITY_ID, created)
        self.assertEqual(choose.call_args.kwargs["minvalue"], 0)
        self.assertEqual(choose.call_args.kwargs["maxvalue"], 23)
        self.assertIn("1024x1024 RGBA shoulder-color", choose_png.call_args.kwargs["title"])
        self.assertEqual(
            choose_recipe.call_args.kwargs["initialfile"], "apf2k8-shoulder-08.json"
        )

    def test_apf_digital_font_creator_requires_global_warning_and_white_rgb_alpha_png(self) -> None:
        app = _app_with_selected(APF_DIGITAL_FONT_CAPABILITY_ID)
        app._refresh_queue = lambda: None
        app._refresh_project_label = lambda: None
        created = Path("/new/apf2k8-digital-font.json")
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.messagebox.askyesno", return_value=True
            ) as warning,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.askopenfilename",
                return_value="/art/digital-font-alpha.png",
            ) as choose_png,
            mock.patch(
                "mod_editor.gui.tkinter_app.filedialog.asksaveasfilename",
                return_value=str(created),
            ) as choose_recipe,
            mock.patch(
                "mod_editor.gui.tkinter_app.create_apf_digital_font_recipe",
                return_value=created,
            ) as creator,
            mock.patch.object(app.controller, "import_provider_project") as importer,
            mock.patch("mod_editor.gui.tkinter_app.messagebox.showinfo"),
        ):
            app._create_provider_recipe()

        creator.assert_called_once_with(
            output=created, png=Path("/art/digital-font-alpha.png")
        )
        importer.assert_called_once_with(APF_DIGITAL_FONT_CAPABILITY_ID, created)
        warning_text = warning.call_args.args[1]
        self.assertIn("shared global UI alpha texture", warning_text)
        self.assertIn("runtime visibility are not proved", warning_text)
        self.assertIn("not a production perceptual encoder", warning_text)
        self.assertIn("RGB solid white; alpha stored", choose_png.call_args.kwargs["title"])
        self.assertEqual(
            choose_recipe.call_args.kwargs["initialfile"], "apf2k8-digital-font.json"
        )

    def test_mapped_inspector_dispatches_named_slider_and_menu_queries(self) -> None:
        cases = (
            (
                NFL_SLIDER_CAPABILITY_ID,
                "mod_editor.gui.tkinter_app.inspect_gameplay_sliders",
                "nfl2k5",
            ),
            (
                APF_MENU_CAPABILITY_ID,
                "mod_editor.gui.tkinter_app.inspect_main_menu",
                "apf2k8",
            ),
        )
        for capability_id, backend_name, argument in cases:
            with self.subTest(capability=capability_id):
                app = _app_with_selected(capability_id)
                shown: list[tuple[str, object]] = []
                errors: list[BaseException] = []
                app._show_inspection_result = lambda title, result: shown.append(
                    (title, result)
                )
                app._show_error = errors.append
                expected = {"schema": "synthetic/read-only", "writes": False}
                with mock.patch(backend_name, return_value=expected) as backend:
                    app._inspect_mapped_data()
                backend.assert_called_once_with(argument)
                self.assertEqual(len(shown), 1)
                self.assertEqual(shown[0][1], expected)
                self.assertEqual(errors, [])

    def test_uniform_sharing_inspector_uses_named_selector_not_raw_offset(self) -> None:
        app = _app_with_selected(APF_CAPABILITY_ID)
        shown: list[tuple[str, object]] = []
        app._show_inspection_result = lambda title, result: shown.append((title, result))
        app._show_error = self.fail
        expected = {"schema": "synthetic/apf-sharing", "writes": False}
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=23
            ) as choose,
            mock.patch(
                "mod_editor.gui.tkinter_app.inspect_apf_jersey_sharing",
                return_value=expected,
            ) as backend,
        ):
            app._inspect_mapped_data()
        backend.assert_called_once_with(23)
        self.assertEqual(choose.call_args.kwargs["minvalue"], 0)
        self.assertEqual(choose.call_args.kwargs["maxvalue"], 23)
        self.assertEqual(shown[0][1], expected)

    def test_save_inspector_dispatches_sanitized_report_without_prompt(self) -> None:
        app = _app_with_selected(NFL_SAVE_CAPABILITY_ID)
        shown: list[tuple[str, object]] = []
        app._show_inspection_result = lambda title, result: shown.append((title, result))
        app._show_error = self.fail
        expected = {"schema": "synthetic/save-inventory", "writes": False}
        with mock.patch(
            "mod_editor.gui.tkinter_app.inspect_nfl_save_inventory",
            return_value=expected,
        ) as backend:
            app._inspect_mapped_data()
        backend.assert_called_once_with()
        self.assertEqual(shown[0][1], expected)

    def test_apf_scorebug_inspector_dispatches_sanitized_named_report(self) -> None:
        app = _app_with_selected(APF_SCOREBUG_CAPABILITY_ID)
        shown: list[tuple[str, object]] = []
        app._show_inspection_result = lambda title, result: shown.append((title, result))
        app._show_error = self.fail
        expected = {"schema": "synthetic/apf-scorebug", "writes": False}
        with mock.patch(
            "mod_editor.gui.tkinter_app.inspect_apf_scorebug_presentation",
            return_value=expected,
        ) as backend:
            app._inspect_mapped_data()
        backend.assert_called_once_with()
        self.assertEqual(shown[0][1], expected)

    def test_pants_sharing_inspector_uses_bounded_asset_index(self) -> None:
        app = _app_with_selected(APF_PANTS_CAPABILITY_ID)
        shown: list[tuple[str, object]] = []
        app._show_inspection_result = lambda title, result: shown.append((title, result))
        app._show_error = self.fail
        expected = {"schema": "synthetic/apf-pants-sharing", "writes": False}
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=13
            ) as choose,
            mock.patch(
                "mod_editor.gui.tkinter_app.inspect_apf_pants_sharing",
                return_value=expected,
            ) as backend,
        ):
            app._inspect_mapped_data()
        backend.assert_called_once_with(13)
        self.assertEqual(choose.call_args.kwargs["minvalue"], 0)
        self.assertEqual(choose.call_args.kwargs["maxvalue"], 23)
        self.assertEqual(shown[0][1], expected)

    def test_shoulder_writer_inspector_uses_bounded_asset_index(self) -> None:
        app = _app_with_selected(APF_SHOULDER_CAPABILITY_ID)
        shown: list[tuple[str, object]] = []
        app._show_inspection_result = lambda title, result: shown.append((title, result))
        app._show_error = self.fail
        expected = {"schema": "synthetic/apf-shoulder-sharing", "writes": False}
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=8
            ) as choose,
            mock.patch(
                "mod_editor.gui.tkinter_app.inspect_apf_shoulder_sharing",
                return_value=expected,
            ) as backend,
        ):
            app._inspect_mapped_data()
        backend.assert_called_once_with(8)
        self.assertEqual(choose.call_args.kwargs["minvalue"], 0)
        self.assertEqual(choose.call_args.kwargs["maxvalue"], 23)
        self.assertEqual(shown[0][1], expected)

    def test_uniform_catalog_can_inspect_helmet_sharing_as_raw_channels(self) -> None:
        app = _app_with_selected(APF_UNIFORM_CATALOG_CAPABILITY_ID)
        shown: list[tuple[str, object]] = []
        app._show_inspection_result = lambda title, result: shown.append((title, result))
        app._show_error = self.fail
        expected = {"schema": "synthetic/apf-helmet-sharing", "writes": False}
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askstring", return_value="helmet"
            ) as choose_family,
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=16
            ) as choose_asset,
            mock.patch(
                "mod_editor.gui.tkinter_app.inspect_apf_helmet_sharing",
                return_value=expected,
            ) as backend,
        ):
            app._inspect_mapped_data()
        backend.assert_called_once_with(16)
        self.assertIn("pants, helmet, or shoulder", choose_family.call_args.args[1])
        self.assertEqual(choose_asset.call_args.kwargs["minvalue"], 0)
        self.assertEqual(choose_asset.call_args.kwargs["maxvalue"], 23)
        self.assertEqual(shown[0][1], expected)

    def test_uniform_catalog_can_inspect_shoulder_sharing(self) -> None:
        app = _app_with_selected(APF_UNIFORM_CATALOG_CAPABILITY_ID)
        shown: list[tuple[str, object]] = []
        app._show_inspection_result = lambda title, result: shown.append((title, result))
        app._show_error = self.fail
        expected = {"schema": "synthetic/apf-shoulder-sharing", "writes": False}
        with (
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askstring",
                return_value="shoulder",
            ),
            mock.patch(
                "mod_editor.gui.tkinter_app.simpledialog.askinteger", return_value=8
            ),
            mock.patch(
                "mod_editor.gui.tkinter_app.inspect_apf_shoulder_sharing",
                return_value=expected,
            ) as backend,
        ):
            app._inspect_mapped_data()
        backend.assert_called_once_with(8)
        self.assertEqual(shown[0][1], expected)


if __name__ == "__main__":
    unittest.main()

"""Headless product tests for the APF team-logo build (package + logo cache).

One "Team Logo" action must drive both offline-proved writers so the edit lands
in the ``uniform_logo_01`` package and in the prebuilt ``uniform_logocache``
aggregate, inside a single copied volume.  These tests pin the dispatch and the
fail-closed behaviour; they never claim any in-game/runtime visibility, which
remains a Xenia step.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio import gui  # noqa: E402
from mod_editor.apf_studio.gui import ApfTeamLogoPanel  # noqa: E402


def _write_png(path: Path, width: int, height: int) -> Path:
    image = QImage(width, height, QImage.Format_RGBA8888)
    image.fill(0x00000000)
    for y_value in range(height // 4, 3 * height // 4):
        for x_value in range(width // 4, 3 * width // 4):
            image.setPixel(x_value, y_value, 0xFFFF0000)
    if not image.save(str(path), "PNG"):
        raise AssertionError(f"could not write test PNG at {path}")
    return path


DECLARED_SIBLINGS = ("0B", "1A", "1B")


def _fake_game(root: Path) -> Path:
    """A stand-in volume layout: an index pack plus the siblings it declares."""

    game = root / "game"
    game.mkdir(parents=True)
    for name in ("0A",) + DECLARED_SIBLINGS:
        (game / name).write_bytes(b"\0" * 16)
    return game / "0A"


class _Source:
    def __init__(self, index_0a: str = "/nonexistent/APF/0A") -> None:
        self.index_0a = index_0a


class _Facade:
    def __init__(self, *, ready: bool = True, index_0a: str | None = None) -> None:
        self.source_ready = ready
        self.source = _Source(index_0a) if ready and index_0a else (
            _Source() if ready else None
        )
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.authoring_master_calls: list[dict[str, object]] = []

    def save_helmet_crest_authoring_master(self, **kwargs: object) -> Path:
        self.authoring_master_calls.append(dict(kwargs))
        progress = kwargs["progress"]
        progress("Saved synthetic authoring master", 1, 1)  # type: ignore[operator]
        return Path(kwargs["destination"])  # type: ignore[arg-type]


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object, bool]] = []

    def __call__(
        self,
        label: str,
        operation: object,
        on_success: object = None,
        blocking: bool = True,
    ) -> bool:
        self.calls.append((label, operation, on_success, blocking))
        return True

    def operation_for(self, prefix: str) -> object:
        for label, operation, _on_success, _blocking in reversed(self.calls):
            if label.startswith(prefix):
                return operation
        raise AssertionError(f"no task was started with label prefix {prefix!r}")


class _CompletedProcess:
    def __init__(self, returncode: int, stderr: str = "", stdout: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


def _value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def _appearance(slot: int, crest_asset: int):
    bank = gui.apf_custom_team_appearance_patch.AppearanceBank(
        palette=(0,) * 10,
        helmet_selector=b"\0" * 8,
        logo_selector=bytes((crest_asset,)) + b"\0" * 7,
    )
    return gui.apf_custom_team_appearance_patch.CustomTeamAppearance(
        slot=slot, home=bank, away=bank
    )


class ApfTeamLogoGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def _panel(
        self,
        *,
        ready: bool = True,
        runner: _RecordingRunner | None = None,
        index_0a: str | None = None,
    ) -> tuple[ApfTeamLogoPanel, _RecordingRunner]:
        recorder = runner or _RecordingRunner()
        panel = ApfTeamLogoPanel(
            _Facade(ready=ready, index_0a=index_0a), recorder  # type: ignore[arg-type]
        )
        panel.set_context()
        self.application.processEvents()
        return panel, recorder

    def _staged_panel(
        self, root: Path
    ) -> tuple[ApfTeamLogoPanel, _RecordingRunner, Path, Path]:
        index = _fake_game(root)
        panel, recorder = self._panel(index_0a=str(index))
        staged = _write_png(root / "crest.png", panel._WIDTH, panel._HEIGHT)
        panel._stage_path(staged)
        self.application.processEvents()
        return panel, recorder, staged, index

    def test_build_is_read_only_safe_until_a_game_and_a_png_are_present(self) -> None:
        panel, _runner = self._panel(ready=False)
        try:
            self.assertFalse(panel.build_button.isEnabled())
            self.assertFalse(panel.replace_button.isEnabled())
        finally:
            panel.deleteLater()
            self.application.processEvents()

        panel, _runner = self._panel()
        try:
            self.assertTrue(panel.replace_button.isEnabled())
            # A loaded game alone is not enough: nothing is staged yet.
            self.assertFalse(panel.build_button.isEnabled())
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_panel_names_linked_frontend_cache_and_separate_wordmark_owner(self) -> None:
        panel, _runner = self._panel()
        try:
            americans_index = next(
                index
                for index in range(panel.slot.count())
                if panel.slot.itemData(index).asset_index == 30
            )
            panel.slot.setCurrentIndex(americans_index)
            self.application.processEvents()

            ownership = panel.ownership_note.text().casefold()
            self.assertIn("linked crest index 30 (selector slot 5)", ownership)
            self.assertIn("uniform_logo_30.iff", ownership)
            self.assertIn("30_logo_l0/30_logo_l1", ownership)
            self.assertIn("frontend/team select cache", ownership)
            self.assertIn("selector slot 6", ownership)
            self.assertIn("uniform_textlogo_00..205", ownership)
            self.assertIn("not resized or changed here", ownership)
            self.assertIn("runtime consumption remains unproved", ownership)
            self.assertIn(
                "co-writes crest + team select cache",
                panel.crest_cache_pill.text().casefold(),
            )
            self.assertIn("selector slot 5", panel.slot_label.text().casefold())
            self.assertIn("selector slot 6", panel.slot.toolTip().casefold())
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_external_import_enables_non_overwriting_high_resolution_master_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "nonsquare-eagles-source.png"
            _write_png(source, 1000, 400)
            original_bytes = source.read_bytes()
            panel, runner = self._panel(index_0a=str(_fake_game(root)))
            try:
                with mock.patch.object(
                    gui, "confirm_prepared_slot_image", return_value=True
                ), mock.patch.object(gui.QMessageBox, "information"):
                    panel._stage_path(source)
                self.assertTrue(panel.master_button.isEnabled())
                draft = panel._texture_master_draft
                self.assertIsNotNone(draft)
                assert draft is not None
                self.assertEqual(draft.source_image.read_bytes(), original_bytes)
                self.assertEqual(draft.transform.width, 512.0)
                self.assertEqual(draft.transform.height, 205.0)
                output = root / "eagles.2ktexmaster"
                with mock.patch.object(
                    gui.QInputDialog,
                    "getItem",
                    return_value=("4× (recommended)", True),
                ), mock.patch.object(
                    gui.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(output), ""),
                ):
                    panel._save_authoring_master()
                operation = runner.operation_for(
                    "Saving high-resolution helmet-logo authoring master"
                )
                result = operation(lambda *_args: None)
                self.assertEqual(result, output)
                facade = panel.facade
                call = facade.authoring_master_calls[-1]  # type: ignore[attr-defined]
                self.assertEqual(call["source_image"], draft.source_image)
                self.assertEqual(call["high_resolution_scale"], 4)
                self.assertEqual(
                    call["editor_transform"]["operation"],  # type: ignore[index]
                    "apf-retail-crest-contain",
                )
                self.assertEqual(source.read_bytes(), original_bytes)
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_built_in_edit_keeps_master_and_records_native_raster_layer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "large-crest.png"
            _write_png(source, 1000, 400)
            original_bytes = source.read_bytes()
            panel, _runner = self._panel(index_0a=str(_fake_game(root)))
            try:
                with mock.patch.object(
                    gui, "confirm_prepared_slot_image", return_value=True
                ), mock.patch.object(gui.QMessageBox, "information"):
                    panel._stage_path(source)
                before = panel._texture_master_draft
                self.assertIsNotNone(before)
                assert before is not None
                self.assertIsNotNone(before.native_baseline_png)
                from mod_editor.core.image_fit import fit_image

                rgba = bytearray(
                    fit_image(
                        panel._staged_png, panel._WIDTH, panel._HEIGHT
                    ).rgba
                )
                rgba[0:4] = b"\x11\x22\x33\xff"
                result = SimpleNamespace(
                    width=panel._WIDTH,
                    height=panel._HEIGHT,
                    rgba=bytes(rgba),
                )
                with mock.patch(
                    "mod_editor.gui.texture_editor.edit_texture",
                    return_value=result,
                ):
                    panel._edit_in_place()

                after = panel._texture_master_draft
                self.assertIsNotNone(after)
                assert after is not None
                self.assertEqual(after.source_image.read_bytes(), original_bytes)
                self.assertEqual(
                    after.native_baseline_png, before.native_baseline_png
                )
                self.assertTrue(after.native_canvas_edited)
                self.assertEqual(
                    after.editor_transform["native_canvas_edit"]["operation"],
                    "native-canvas-raster-edit-after-import",
                )
                self.assertTrue(panel.master_button.isEnabled())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_retail_import_shows_the_exact_prepared_pixels_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "previewed-crest.png"
            _write_png(source, 900, 640)
            panel, _runner = self._panel(index_0a=str(_fake_game(root)))
            try:
                seen: list[Path] = []

                def _record_preview(_panel, image_path, **kwargs):
                    seen.append(Path(image_path))
                    return True

                with mock.patch.object(
                    gui, "confirm_prepared_slot_image",
                    side_effect=_record_preview,
                ), mock.patch.object(gui.QMessageBox, "information"):
                    panel._stage_path(source)
                self.assertEqual(len(seen), 1)
                previewed = seen[0]
                self.assertEqual(previewed, panel._staged_png)
                with open(previewed, "rb") as handle:
                    header = handle.read(8)
                self.assertEqual(header, b"\x89PNG\r\n\x1a\n")
                from PIL import Image

                with Image.open(previewed) as prepared:
                    self.assertEqual(prepared.size, (512, 512))
                    self.assertEqual(prepared.mode, "RGBA")
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_retail_import_declined_from_the_preview_stages_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "declined-crest.png"
            _write_png(source, 900, 640)
            panel, _runner = self._panel(index_0a=str(_fake_game(root)))
            try:
                with mock.patch.object(
                    gui, "confirm_prepared_slot_image", return_value=False
                ), mock.patch.object(gui.QMessageBox, "information"):
                    panel._stage_path(source)
                self.assertIsNone(panel._staged_png)
                self.assertFalse(panel.build_button.isEnabled())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_switching_coverage_requires_reimport_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            panel, runner, _staged, _index = self._staged_panel(Path(directory))
            try:
                self.assertTrue(panel.build_button.isEnabled())
                panel.coverage.setCurrentIndex(
                    panel.coverage.findData(gui.FULL_SHELL_CREST_PROFILE)
                )
                self.assertFalse(panel.build_button.isEnabled())
                self.assertIn("Import or drop", panel.path_note.text())
                with mock.patch.object(gui.QMessageBox, "information") as message:
                    panel._build_copied_volume()
                self.assertIn("other helmet coverage", message.call_args.args[2])
                self.assertFalse(
                    any(label.startswith("Building copied 0A") for label, *_ in runner.calls)
                )
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_one_action_writes_both_the_package_and_the_logo_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel, runner, staged, index = self._staged_panel(root)
            try:
                self.assertTrue(panel.build_button.isEnabled())
                out_volume = root / "out" / "0A"

                with mock.patch.object(
                    gui.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(out_volume), ""),
                ), mock.patch.object(
                    gui.QMessageBox, "question", return_value=gui.QMessageBox.Yes
                ):
                    panel._build_copied_volume()

                staging_layout: list[str] = []

                def _record(argv, **_kwargs):
                    if not staging_layout:
                        workspace = Path(_value_after(argv, "--output-volume")).parent
                        staging_layout.extend(
                            sorted(entry.name for entry in workspace.iterdir())
                        )
                    return _CompletedProcess(0)

                operation = runner.operation_for("Building copied 0A")
                with mock.patch.object(
                    gui.ApfTeamLogoPanel,
                    "_declared_sibling_packs",
                    return_value=DECLARED_SIBLINGS,
                ), mock.patch("subprocess.run", side_effect=_record) as run:
                    report = operation(lambda *_args: None)

                self.assertEqual(run.call_count, 3)
                package_argv = run.call_args_list[0].args[0]
                cache_argv = run.call_args_list[1].args[0]
                verify_argv = run.call_args_list[2].args[0]

                # 1) the package writer, from the user's read-only source.
                self.assertTrue(package_argv[1].endswith("apf_logo_patch.py"))
                self.assertEqual(_value_after(package_argv, "--index"), str(index))
                self.assertEqual(_value_after(package_argv, "--png"), str(staged))
                self.assertEqual(_value_after(package_argv, "--png-l1"), str(staged))
                intermediate = _value_after(package_argv, "--output-volume")

                # The intermediate is staged under the index's own pack name with
                # every declared sibling linked beside it, which is the only shape
                # an APF index parses -- the cache writer must re-parse it.
                self.assertEqual(Path(intermediate).name, index.name)
                self.assertEqual(
                    staging_layout, sorted(DECLARED_SIBLINGS)
                )

                # 2) the cache writer, chained onto the package writer's output so
                #    the single delivered volume carries both edits.
                self.assertTrue(cache_argv[1].endswith("apf_logocache_patch.py"))
                self.assertEqual(_value_after(cache_argv, "--index"), intermediate)
                self.assertEqual(_value_after(cache_argv, "--catalog-index"), "1")
                self.assertEqual(_value_after(cache_argv, "--png"), str(staged))
                self.assertEqual(_value_after(cache_argv, "--png-l1"), str(staged))
                self.assertEqual(
                    _value_after(cache_argv, "--output-volume"), str(out_volume)
                )

                # 3) the independent cache verifier compares the intermediate
                #    package copy to the final combined volume while both exist.
                self.assertTrue(verify_argv[1].endswith("apf_logocache_verify.py"))
                self.assertEqual(_value_after(verify_argv, "--source"), intermediate)
                self.assertEqual(_value_after(verify_argv, "--output"), str(out_volume))
                self.assertEqual(_value_after(verify_argv, "--catalog-index"), "1")
                self.assertIn("--expect-l1", verify_argv)
                self.assertEqual(
                    Path(_value_after(verify_argv, "--manifest")).name,
                    "0A.team_logo_cache.verify.json",
                )

                # The delivered artefact is the volume the author chose.
                self.assertEqual(report["volume"], out_volume)
                self.assertEqual(
                    Path(str(report["cache_manifest"])).name,
                    f"{out_volume.name}.team_logo_cache.json",
                )
                # The intermediate copy never survives the build.
                self.assertFalse(Path(intermediate).exists())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_full_shell_profile_writes_carrier_without_a_xenia_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel, runner, _staged, _index = self._staged_panel(root)
            try:
                panel.coverage.setCurrentIndex(
                    panel.coverage.findData(gui.FULL_SHELL_CREST_PROFILE)
                )
                # This test exercises the specialized build dispatch, not the
                # import wizard. Re-stage the already-semantic fixture under
                # the selected profile so the profile-mismatch guard is closed.
                self.assertTrue(panel._commit_design(_staged, remember_source=False))
                out_volume = root / "out" / "0A"
                with mock.patch.object(
                    gui.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(out_volume), ""),
                ), mock.patch.object(
                    gui.QMessageBox, "question", return_value=gui.QMessageBox.Yes
                ):
                    panel._build_copied_volume()

                operation = runner.operation_for("Building copied 0A")
                with mock.patch.object(
                    gui.ApfTeamLogoPanel,
                    "_declared_sibling_packs",
                    return_value=DECLARED_SIBLINGS,
                ), mock.patch.object(
                    gui,
                    "_build_full_shell_team_logo_volume",
                    return_value={
                        "volume": out_volume,
                        "crest_profile": gui.FULL_SHELL_CREST_PROFILE,
                        "crest_wrap_manifest": (
                            out_volume.parent
                            / f"{out_volume.name}.helmet_crest_wrap.json"
                        ),
                        "crest_patch": None,
                    },
                ) as full_shell_build:
                    report = operation(lambda *_args: None)

                full_shell_build.assert_called_once()
                self.assertEqual(full_shell_build.call_args.args[0], _index)
                self.assertEqual(full_shell_build.call_args.args[1], _staged)
                self.assertEqual(full_shell_build.call_args.args[2], out_volume)
                self.assertEqual(
                    full_shell_build.call_args.kwargs["cache_catalog_index"], 1
                )
                self.assertEqual(
                    full_shell_build.call_args.kwargs["outer_entry_index"], 36
                )
                self.assertEqual(
                    full_shell_build.call_args.kwargs["siblings"], DECLARED_SIBLINGS
                )
                self.assertEqual(
                    report["crest_profile"], gui.FULL_SHELL_CREST_PROFILE
                )
                crest_receipt = Path(str(report["crest_wrap_manifest"]))
                self.assertEqual(crest_receipt.parent, out_volume.parent)
                self.assertIsNone(report["crest_patch"])
                self.assertFalse(
                    (out_volume.parent / gui.apf_crest_box_patch.PATCH_BASENAME).exists()
                )
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_staged_appearance_runs_between_package_and_cache_and_is_reverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = _fake_game(root)
            staged_png = _write_png(root / "crest.png", 512, 512)
            output = root / "out" / "0A"
            package_manifest = root / "out" / "0A.team_logo_package.json"
            cache_manifest = root / "out" / "0A.team_logo_cache.json"
            appearance_manifest = root / "out" / "0A.custom_team_appearance.json"
            events: list[str] = []

            def _run(argv, **_kwargs):
                script = Path(argv[1]).name
                if script == "apf_logo_patch.py":
                    events.append("package")
                    Path(_value_after(argv, "--output-volume")).write_bytes(b"stage")
                    Path(_value_after(argv, "--manifest")).write_text(
                        '{"copied_volume":{"source_volume_sha256_before":"'
                        + "a" * 64
                        + '"}}'
                    )
                elif script == "apf_logocache_patch.py":
                    events.append("cache")
                    Path(_value_after(argv, "--output-volume")).write_bytes(b"final")
                    Path(_value_after(argv, "--manifest")).write_text(
                        '{"copied_volume":{"output_volume_sha256":"'
                        + "b" * 64
                        + '"}}'
                    )
                else:
                    events.append("cache_verify")
                    Path(_value_after(argv, "--manifest")).write_text("{}")
                return _CompletedProcess(0)

            def _stage(*_args, **_kwargs):
                events.append("appearance")
                return {"schema": "synthetic-stage"}

            def _verify(*_args, **_kwargs):
                events.append("appearance_verify")
                return {"verified_slots": (32,)}

            with mock.patch("subprocess.run", side_effect=_run), mock.patch.object(
                gui.apf_custom_team_appearance_patch,
                "patch_private_staged_volume",
                side_effect=_stage,
            ), mock.patch.object(
                gui.apf_custom_team_appearance_patch,
                "verify_output_appearances",
                side_effect=_verify,
            ):
                report = gui.build_team_logo_copied_volume(
                    index,
                    staged_png,
                    output,
                    package_manifest,
                    cache_manifest,
                    lambda *_args: None,
                    cache_catalog_index=30,
                    siblings=DECLARED_SIBLINGS,
                    appearance_replacements={32: _appearance(32, 30)},
                    appearance_manifest=appearance_manifest,
                )
            self.assertEqual(
                events,
                [
                    "package",
                    "appearance",
                    "cache",
                    "cache_verify",
                    "appearance_verify",
                ],
            )
            self.assertTrue(appearance_manifest.is_file())
            self.assertEqual(report["appearance_manifest"], appearance_manifest)

    def test_appearance_crest_selectors_must_match_selected_team_logo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = _fake_game(root)
            staged_png = _write_png(root / "crest.png", 512, 512)
            output = root / "out" / "0A"
            with mock.patch("subprocess.run") as run, self.assertRaisesRegex(
                RuntimeError, "HOME selects crest asset 29.*selected asset 30"
            ):
                gui.build_team_logo_copied_volume(
                    index,
                    staged_png,
                    output,
                    root / "out" / "package.json",
                    root / "out" / "cache.json",
                    lambda *_args: None,
                    cache_catalog_index=30,
                    siblings=DECLARED_SIBLINGS,
                    appearance_replacements={32: _appearance(32, 29)},
                    appearance_manifest=root / "out" / "appearance.json",
                )
            run.assert_not_called()
            self.assertFalse(output.exists())

    def test_full_shell_final_name_appears_only_after_complete_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_parent = root / "out"
            output_parent.mkdir()
            index = _fake_game(root)
            staged_png = _write_png(root / "crest.png", 512, 512)
            output = output_parent / "0A"
            package_manifest = output_parent / "package.json"
            cache_manifest = output_parent / "cache.json"
            cache_verify_manifest = output_parent / "cache.verify.json"
            crest_manifest = output_parent / "crest.json"
            compilation = mock.Mock(
                entries={1: b"compiled"},
                report={"catalog_slot_count": 118},
                cache_manifest={"schema": "cache/v1"},
                cache_structure_verification={"verified": True},
                carrier_manifest={"schema": "shell/v24"},
                carrier_verification={"verified": True},
            )
            observed_stage: list[Path] = []

            def publish(_source, private_stage, _entries, *, progress):
                del progress
                private_stage = Path(private_stage)
                self.assertFalse(output.exists())
                self.assertNotEqual(private_stage, output)
                self.assertEqual(private_stage.parent.parent, output.parent)
                private_stage.write_bytes(b"complete-verified-volume")
                observed_stage.append(private_stage)
                return {"schema": "synthetic-publication"}

            with mock.patch.object(
                gui, "compile_full_shell_crest_entries", return_value=compilation
            ), mock.patch.object(
                gui, "publish_compiled_outer_entries", side_effect=publish
            ):
                report = gui._build_full_shell_team_logo_volume(
                    index,
                    staged_png,
                    output,
                    package_manifest,
                    cache_manifest,
                    cache_verify_manifest,
                    crest_manifest,
                    lambda *_args: None,
                    cache_catalog_index=30,
                    outer_entry_index=1133,
                    siblings=DECLARED_SIBLINGS,
                    appearance_replacements=None,
                    appearance_manifest=None,
                )

            self.assertEqual(output.read_bytes(), b"complete-verified-volume")
            self.assertEqual(report["volume"], output)
            self.assertTrue(package_manifest.is_file())
            self.assertTrue(cache_manifest.is_file())
            self.assertTrue(cache_verify_manifest.is_file())
            self.assertTrue(crest_manifest.is_file())
            self.assertFalse(observed_stage[0].exists())
            self.assertFalse(observed_stage[0].parent.exists())

    def test_full_shell_appearance_stage_sees_declared_sibling_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_parent = root / "out"
            output_parent.mkdir()
            index = _fake_game(root)
            staged_png = _write_png(root / "crest.png", 512, 512)
            output = output_parent / "0A"
            compilation = mock.Mock(
                entries={1: b"compiled"},
                report={"catalog_slot_count": 118},
                cache_manifest={"schema": "cache/v1"},
                cache_structure_verification={"verified": True},
                carrier_manifest={"schema": "shell/v24"},
                carrier_verification={"verified": True},
            )
            observed_stage_parent: list[Path] = []

            def publish(_source, private_stage, _entries, *, progress):
                del progress
                Path(private_stage).write_bytes(b"complete-verified-volume")
                return {"schema": "synthetic-publication"}

            def patch(private_stage, _replacements):
                stage_parent = Path(private_stage).parent
                observed_stage_parent.append(stage_parent)
                for pack in DECLARED_SIBLINGS:
                    linked = stage_parent / pack
                    self.assertTrue(linked.exists())
                    self.assertEqual(linked.read_bytes(), (index.parent / pack).read_bytes())
                return {"schema": "synthetic-stage"}

            with mock.patch.object(
                gui, "compile_full_shell_crest_entries", return_value=compilation
            ), mock.patch.object(
                gui, "publish_compiled_outer_entries", side_effect=publish
            ), mock.patch.object(
                gui.apf_custom_team_appearance_patch,
                "patch_private_staged_volume",
                side_effect=patch,
            ), mock.patch.object(
                gui.apf_custom_team_appearance_patch,
                "verify_output_appearances",
                return_value={"verified_slots": (32,)},
            ):
                gui._build_full_shell_team_logo_volume(
                    index,
                    staged_png,
                    output,
                    output_parent / "package.json",
                    output_parent / "cache.json",
                    output_parent / "cache.verify.json",
                    output_parent / "crest.json",
                    lambda *_args: None,
                    cache_catalog_index=30,
                    outer_entry_index=1133,
                    siblings=DECLARED_SIBLINGS,
                    appearance_replacements={32: _appearance(32, 30)},
                    appearance_manifest=output_parent / "appearance.json",
                )

            self.assertTrue(output.is_file())
            self.assertFalse(observed_stage_parent[0].exists())

    def test_coverage_picker_defaults_to_the_non_surprising_retail_box(self) -> None:
        panel, _runner = self._panel()
        try:
            self.assertEqual(
                [panel.coverage.itemData(index) for index in range(panel.coverage.count())],
                [gui.RETAIL_CREST_PROFILE, gui.FULL_SHELL_CREST_PROFILE],
            )
            self.assertEqual(panel.coverage.currentData(), gui.RETAIL_CREST_PROFILE)
            self.assertIn("every team", panel.coverage.toolTip())
            self.assertEqual(
                panel._coverage_text(247 / 512) + " → " + panel._coverage_text(1.0),
                "48.2% → 100%",
            )
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_a_cache_writer_refusal_fails_the_whole_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel, runner, _staged, _index = self._staged_panel(root)
            try:
                with mock.patch.object(
                    gui.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(root / "out" / "0A"), ""),
                ), mock.patch.object(
                    gui.QMessageBox, "question", return_value=gui.QMessageBox.Yes
                ):
                    panel._build_copied_volume()

                operation = runner.operation_for("Building copied 0A")
                with mock.patch.object(
                    gui.ApfTeamLogoPanel,
                    "_declared_sibling_packs",
                    return_value=DECLARED_SIBLINGS,
                ), mock.patch("subprocess.run") as run:
                    run.side_effect = [
                        _CompletedProcess(0),
                        _CompletedProcess(
                            1,
                            stderr="error: logo cache payload hash is not the "
                            "pinned retail data; refusing",
                        ),
                    ]
                    with self.assertRaises(RuntimeError) as raised:
                        operation(lambda *_args: None)
                self.assertIn("pinned retail data", str(raised.exception))
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_a_package_writer_refusal_never_reaches_the_cache_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel, runner, _staged, _index = self._staged_panel(root)
            try:
                with mock.patch.object(
                    gui.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(root / "out" / "0A"), ""),
                ), mock.patch.object(
                    gui.QMessageBox, "question", return_value=gui.QMessageBox.Yes
                ):
                    panel._build_copied_volume()

                operation = runner.operation_for("Building copied 0A")
                with mock.patch.object(
                    gui.ApfTeamLogoPanel,
                    "_declared_sibling_packs",
                    return_value=DECLARED_SIBLINGS,
                ), mock.patch("subprocess.run") as run:
                    run.return_value = _CompletedProcess(
                        1,
                        stderr="error: source entry hash is not the pinned retail "
                        "uniform_logo_01; refusing",
                    )
                    with self.assertRaises(RuntimeError) as raised:
                        operation(lambda *_args: None)
                self.assertEqual(run.call_count, 1)
                self.assertIn("uniform_logo_01", str(raised.exception))
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_labels_never_claim_in_game_visibility(self) -> None:
        panel, _runner = self._panel()
        try:
            surfaces = " ".join(
                (
                    panel.build_button.toolTip(),
                    panel.slot.toolTip(),
                    panel.ownership_note.text(),
                    panel.crest_cache_pill.toolTip(),
                    ApfTeamLogoPanel.__doc__ or "",
                )
            ).casefold()
            for overclaim in (
                "updates the scorebug",
                "visible in game",
                "in-game proved",
                "proved in game",
            ):
                self.assertNotIn(overclaim, surfaces)
        finally:
            panel.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()

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
    image.fill(0xFF7F1020)
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

                self.assertEqual(run.call_count, 2)
                package_argv = run.call_args_list[0].args[0]
                cache_argv = run.call_args_list[1].args[0]

                # 1) the package writer, from the user's read-only source.
                self.assertTrue(package_argv[1].endswith("apf_logo_patch.py"))
                self.assertEqual(_value_after(package_argv, "--index"), str(index))
                self.assertEqual(_value_after(package_argv, "--png"), str(staged))
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
                self.assertEqual(
                    _value_after(cache_argv, "--output-volume"), str(out_volume)
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

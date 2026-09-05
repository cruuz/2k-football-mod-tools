"""The preflight has to be *reached*, not merely to exist.

Five releases in one day were the same defect: a mechanism was built and then
not wired to the thing that needed it. ``PAYLOAD_SCHEMA`` never reached a
project; the membership panel never reached a refresh; the extended catalog
never reached a session; ``quantize_levels_to_vc_lz_bound`` never reached four
importers. Each one looked finished and did nothing.

``nfl2k5_import_preflight`` shipped in exactly that state -- a complete module
with no caller. So these tests pin the whole path a user's click takes: button
-> handler -> facade -> session -> predictor, plus the two things a modder
actually sees, which are the result dialog and the reason the button is off.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.core import nfl2k5_import_preflight as preflight  # noqa: E402
from mod_editor.gui import studio_qt  # noqa: E402
from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
_STUDIO = ROOT / "mod_editor" / "gui" / "studio_qt.py"
_FACADE = ROOT / "mod_editor" / "studio" / "facade.py"
_SESSION = ROOT / "mod_editor" / "studio" / "session.py"
_JERSEY_REPORT = ROOT / "reports/assets/nfl2k5_jersey_tset_compatibility.json"


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} is no longer defined in {path.name}")


def _calls(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            target = inner.func
            if isinstance(target, ast.Attribute):
                names.add(target.attr)
            elif isinstance(target, ast.Name):
                names.add(target.id)
    return names


class WiringTests(unittest.TestCase):
    """Grep for each helper's own name, exactly as the handoff demands."""

    def test_the_button_is_connected_to_the_handler(self) -> None:
        source = _STUDIO.read_text(encoding="utf-8")
        self.assertIn("self.check_images_button = QPushButton(", source)
        self.assertIn(
            "self.check_images_button.clicked.connect(self._check_staged_images)",
            source,
        )

    def test_the_handler_reaches_the_facade(self) -> None:
        handler = _function(_STUDIO, "_check_staged_images")
        self.assertIn("preflight_visual_edits", _calls(handler))
        self.assertIn("_start_task", _calls(handler))

    def test_the_facade_reaches_the_session_and_the_predictor(self) -> None:
        method = _function(_FACADE, "preflight_visual_edits")
        called = _calls(method)
        self.assertIn("staged_preflight_inputs", called)
        self.assertIn("predict_edits", called)

    def test_the_session_reaches_the_real_catalog_and_allocations(self) -> None:
        method = _function(_SESSION, "staged_preflight_inputs")
        called = _calls(method)
        # Resolving through _visual_asset is what lets an extended-catalog row
        # (equipment, portrait, field art) be staged and still be named.
        self.assertIn("_visual_asset", called)
        self.assertIn("edits_for_assets", called)

    def test_the_slow_work_does_not_run_under_the_facade_lock(self) -> None:
        # The ladder runs for seconds per slot. Holding the lock across it would
        # freeze every status field the window polls, so the snapshot is taken
        # under the lock and the prediction is not.
        method = _function(_FACADE, "preflight_visual_edits")
        with_blocks = [n for n in ast.walk(method) if isinstance(n, ast.With)]
        self.assertTrue(with_blocks, "the session snapshot must be taken under the lock")
        inside = set()
        for block in with_blocks:
            for inner in ast.walk(block):
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                    inside.add(inner.func.attr)
        self.assertIn("staged_preflight_inputs", inside)
        self.assertNotIn("predict_edits", inside)


class AllocationTests(unittest.TestCase):
    """A bound has to come from the target report, never from a guess."""

    def setUp(self) -> None:
        if not _JERSEY_REPORT.is_file():
            self.skipTest("compatibility reports are gitignored derived data")
        packages = json.loads(_JERSEY_REPORT.read_text())["packages"]
        self.selector = packages[0]["selector"]

    def test_every_modelled_family_resolves_a_real_bound(self) -> None:
        for kind in ("torso", "sleeve", "pants"):
            with self.subTest(kind=kind):
                bound = preflight.slot_allocation_bytes(
                    kind, self.selector["asset_code"], self.selector["side"],
                    int(self.selector["variant"]),
                )
                self.assertIsInstance(bound, int)
                self.assertGreater(bound, 0)

    def test_the_two_helmet_meshes_have_separate_spans(self) -> None:
        bounds = {
            family: preflight.slot_allocation_bytes(
                "live_helmet", self.selector["asset_code"], self.selector["side"],
                int(self.selector["variant"]), family,
            )
            for family in ("helmet00", "helmet02")
        }
        self.assertTrue(all(isinstance(v, int) for v in bounds.values()))
        # Sharing one bound between the two meshes would silently predict the
        # wrong slot for one of them.
        self.assertNotEqual(bounds["helmet00"], bounds["helmet02"])

    def test_a_helmet_without_a_family_is_not_guessed(self) -> None:
        self.assertIsNone(preflight.slot_allocation_bytes(
            "live_helmet", self.selector["asset_code"], self.selector["side"],
            int(self.selector["variant"]), None,
        ))

    def test_an_unmodelled_kind_returns_no_bound(self) -> None:
        self.assertIsNone(
            preflight.slot_allocation_bytes("p8_texture", "00", "H", 0)
        )

    def test_an_absent_package_is_reported_not_invented(self) -> None:
        self.assertIsNone(
            preflight.slot_allocation_bytes("torso", "ZZ", "H", 99)
        )


class EditRowTests(unittest.TestCase):
    def test_rows_carry_the_asset_id_label_kind_path_and_bound(self) -> None:
        asset = SimpleNamespace(
            asset_id="u:1", label="Torso / Jersey", kind="p8_texture",
            asset_code="00", side_code="H", variant=0, family=None,
        )
        rows = preflight.edits_for_assets([(asset, Path("/tmp/x.png"))])
        self.assertEqual(len(rows), 1)
        asset_id, label, kind, png, allocation = rows[0]
        self.assertEqual((asset_id, label, kind), ("u:1", "Torso / Jersey", "p8_texture"))
        self.assertEqual(png, Path("/tmp/x.png"))
        self.assertIsNone(allocation)

    def test_an_asset_without_a_selector_is_unmodelled_not_a_crash(self) -> None:
        # Extended-catalog rows reach this the same way uniform components do,
        # and most of them carry no asset_code/side at all.
        asset = SimpleNamespace(asset_id="p8:9", label="Some texture", kind="torso")
        rows = preflight.edits_for_assets([(asset, Path("/tmp/x.png"))])
        self.assertIsNone(rows[0][4])
        predicted = preflight.predict_edits(rows)
        self.assertEqual(predicted[0].outcome, preflight.UNMODELLED)
        self.assertIn("decided at build time", predicted[0].detail)


class _CheckFacade(BrowseOnlyFacade):
    """The catalog-only fallback, taught to answer just the check.

    Subclassing it rather than hand-rolling a stub keeps the window's own
    start-up path on the code it was written against; every method this test
    does not care about keeps the fallback's honest refusal.
    """

    def __init__(self, rows: tuple[object, ...]) -> None:
        self.rows = rows
        self.calls = 0

    def preflight_visual_edits(self, progress) -> tuple[object, ...]:
        self.calls += 1
        progress("Checking staged images", 0, len(self.rows))
        return self.rows


def _row(outcome: str, label: str, **kwargs: object) -> preflight.SlotPrediction:
    return preflight.SlotPrediction(
        asset_id=label, label=label, kind="torso", outcome=outcome, **kwargs
    )


class DialogTests(unittest.TestCase):
    """What a modder actually sees when they press the button."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _window(self, rows: tuple[object, ...]) -> tuple[StudioMainWindow, _CheckFacade]:
        facade = _CheckFacade(rows)
        window = StudioMainWindow(facade=facade, offer_recovery=False)
        # Previews decode off-thread; leaving them running past teardown makes
        # Qt tear down a deleted QLabel from a worker callback.
        window._load_preview = lambda _asset: None  # type: ignore[method-assign]
        window._load_visual_preview = (  # type: ignore[method-assign]
            lambda _asset, _preview: None
        )
        self.addCleanup(window.close)
        # Run the operation inline: this test is about what reaches the dialog,
        # not about Qt's thread pool.
        def start(operation, on_success, **_kwargs) -> None:
            on_success(operation(lambda *_a: None))
        window._start_task = start  # type: ignore[method-assign]
        self.shown: list[QMessageBox] = []
        return window, facade

    def _capture(self) -> None:
        """Intercept both dialog routes.

        ``QMessageBox.information`` is a static convenience that spins its own
        modal event loop; under the offscreen platform nothing ever presses its
        button, so leaving it unpatched hangs the run rather than failing it.
        """

        shown = self.shown
        self.informed: list[tuple[str, str]] = []
        informed = self.informed

        def exec_(self_box: QMessageBox) -> int:
            shown.append(self_box)
            return 0

        def information(_parent, title, text, *_args, **_kwargs) -> int:
            informed.append((title, text))
            return QMessageBox.Ok

        patched_exec = QMessageBox.exec_
        patched_information = QMessageBox.information
        QMessageBox.exec_ = exec_  # type: ignore[assignment]
        QMessageBox.information = staticmethod(information)  # type: ignore[assignment]

        def restore() -> None:
            QMessageBox.exec_ = patched_exec  # type: ignore[assignment]
            QMessageBox.information = patched_information  # type: ignore[assignment]

        self.addCleanup(restore)

    def test_a_clean_set_says_nothing_will_be_changed(self) -> None:
        window, facade = self._window((
            _row(preflight.FULL, "Torso", palette_entries=255),
            _row(preflight.FULL, "Pants", palette_entries=200),
        ))
        self._capture()
        window._check_staged_images()
        self.assertEqual(facade.calls, 1)
        self.assertEqual(len(self.shown), 1)
        box = self.shown[0]
        self.assertIn("All 2 fit as authored", box.text())
        self.assertEqual(box.icon(), QMessageBox.Information)

    def test_a_reduction_leads_with_the_count_and_explains_the_cause(self) -> None:
        window, _ = self._window((
            _row(preflight.FULL, "Torso", palette_entries=255),
            _row(preflight.REDUCED, "Pants", palette_entries=16,
                 source_colours=4000, allocation_bytes=75_472),
        ))
        self._capture()
        window._check_staged_images()
        box = self.shown[0]
        self.assertIn("1 of 2", box.text())
        self.assertIn("lose colours", box.text())
        # The advice a user needs, because shrinking the source does nothing.
        self.assertIn("distinct shades", box.informativeText())
        self.assertIn("not its resolution", box.informativeText())
        self.assertIn("reduced to 16 colours", box.detailedText())

    def test_a_refusal_is_a_warning_and_leads_the_summary(self) -> None:
        window, _ = self._window((
            _row(preflight.REDUCED, "Pants", palette_entries=16,
                 source_colours=4000, allocation_bytes=75_472),
            _row(preflight.REFUSED, "Torso", detail="Nothing fits."),
        ))
        self._capture()
        window._check_staged_images()
        box = self.shown[0]
        self.assertEqual(box.icon(), QMessageBox.Warning)
        self.assertIn("will not fit", box.text())
        self.assertIn("stop the build", box.text())

    def test_unmodelled_rows_are_never_counted_as_fitting(self) -> None:
        # "All 3 fit as authored" when two of them were never checked is a claim
        # the preflight cannot support, and it is the exact shape of overclaim
        # this project has had to withdraw before.
        window, _ = self._window((
            _row(preflight.FULL, "Torso", palette_entries=255),
            _row(preflight.UNMODELLED, "Sock", detail="no fixed-span prediction yet."),
            _row(preflight.UNMODELLED, "Portrait", detail="no fixed-span prediction yet."),
        ))
        self._capture()
        window._check_staged_images()
        text = self.shown[0].text()
        self.assertIn("1 of 3 fit as authored", text)
        self.assertIn("2 could not be checked", text)
        self.assertNotIn("All 3", text)

    def test_an_all_unmodelled_set_claims_nothing(self) -> None:
        window, _ = self._window((
            _row(preflight.UNMODELLED, "Sock", detail="no fixed-span prediction yet."),
        ))
        self._capture()
        window._check_staged_images()
        text = self.shown[0].text()
        self.assertIn("None of these 1", text)
        self.assertIn("checked here", text)
        self.assertNotIn("fit as authored", text)

    def test_an_empty_set_says_so_instead_of_showing_an_empty_dialog(self) -> None:
        window, _ = self._window(())
        self._capture()
        window._check_staged_images()
        self.assertEqual(len(self.shown), 0)  # information(), not a built box
        self.assertEqual(len(self.informed), 1)
        title, text = self.informed[0]
        self.assertEqual(title, "Nothing to check")
        self.assertIn("Replace at least one image", text)
        self.assertIn("nothing to check", window.operation_status.text().casefold())


class BlockerTests(unittest.TestCase):
    """Never silent-gray: a disabled button has to name its own blocker."""

    def test_every_disabled_state_names_a_reason(self) -> None:
        source = _STUDIO.read_text(encoding="utf-8")
        self.assertIn('self.check_images_button.setProperty("disableReason"', source)
        self.assertIn("Open your game disc first.", source)
        self.assertIn("Replace at least one image first", source)

    def test_the_advice_names_shade_count_and_denies_resolution(self) -> None:
        advice = studio_qt.CHECK_IMAGES_ADVICE
        self.assertIn("distinct shades", advice)
        self.assertIn("not its resolution", advice)
        self.assertIn("gradients", advice)

    def test_the_tooltip_promises_no_build_and_no_change(self) -> None:
        message = studio_qt.CHECK_IMAGES_MESSAGE
        self.assertIn("Nothing is changed", message)
        self.assertIn("no build is started", message)


if __name__ == "__main__":
    unittest.main()

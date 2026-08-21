"""Noob-language audit: refusals say what happened AND how to fix it.

The fail-closed behaviour never changes -- the same bytes are still refused --
but every user-facing refusal in the GUI layer must carry a plain next step.
These tests pin the fix-hint wording and the converted-instead-of-refused
routes so a future edit cannot quietly bring the dead ends back.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.apf_studio import gui  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APF_GUI = _REPO_ROOT / "mod_editor" / "apf_studio" / "gui.py"
_STUDIO_QT = _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"
_CRIB_QT = _REPO_ROOT / "mod_editor" / "gui" / "crib_panel_qt.py"


class FixHintTests(unittest.TestCase):
    """The central error gloss pairs known refusals with plain fixes."""

    REFUSALS = (
        "Expected an exact 128x128 RGBA PNG; received 64x64 RGB.",
        "Pants PNG alpha must be 255 (fully opaque) everywhere",
        "Wordmark PNG alpha must be 255 everywhere; use the importer",
        "digital_font RGB must be solid white; draw only in alpha",
        "Helmet PNG blue must be 0; only the R/G mask channels are stored",
        "That image is 200×300; it must stay 512×512.",
        "DXT1 stadium textures require opaque artwork; flatten transparency first",
        "notes.txt could not be read as an image: cannot identify image file",
        "FFmpeg was not found to convert it.",
    )

    def test_every_known_refusal_gets_a_plain_fix_hint(self) -> None:
        for message in self.REFUSALS:
            with self.subTest(message=message):
                hint = gui.friendly_fix_hint(message)
                self.assertIsNotNone(hint, "refusal has no fix hint")
                assert hint is not None
                self.assertIn("Fix:", hint)

    def test_exact_size_refusals_point_back_to_the_editor(self) -> None:
        hint = gui.friendly_fix_hint(self.REFUSALS[0])
        assert hint is not None
        self.assertIn("resizes it for you", hint)

    def test_unknown_messages_get_no_hint(self) -> None:
        self.assertIsNone(gui.friendly_fix_hint("Something unrelated happened."))

    def test_the_error_dialog_shows_the_hint(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        start = source.index("    def _show_error(self, message: str")
        block = source[start:start + 800]
        self.assertIn("friendly_fix_hint(message)", block)


class NoDeadEndCopyTests(unittest.TestCase):
    """Stale 'refused / rejects' copy must not survive in the GUI layer."""

    def test_apf_gui_never_claims_wrong_sizes_are_refused(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        self.assertNotIn("Wrong PNG size", source)
        self.assertNotIn("any other size is refused", source)
        self.assertNotIn("refused before anything is staged", source)

    def test_2k5_uniform_help_no_longer_threatens_rejection(self) -> None:
        source = _STUDIO_QT.read_text(encoding="utf-8")
        self.assertNotIn("rejects the wrong dimensions", source)

    def test_crib_chooser_and_drop_accept_every_ordinary_format(self) -> None:
        source = _CRIB_QT.read_text(encoding="utf-8")
        self.assertIn("CRIB_IMAGE_FILTER", source)
        self.assertIn("resized to the exact", source)
        # The old PNG-only gate is gone from the drop target.
        self.assertNotIn('endswith(".png")', source)

    def test_stadium_chooser_accepts_every_ordinary_format(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        start = source.index("    def _replace_embedded_texture(self) -> None:")
        # Window must cover never-gray disableReason preamble + getOpenFileName.
        block = source[start:start + 1400]
        self.assertIn("IMAGE_IMPORT_FILTER", block)
        self.assertIn("resized to", block)

    def test_crest_pill_promises_conversion_instead_of_refusal(self) -> None:
        source = _APF_GUI.read_text(encoding="utf-8")
        # The tooltip is split across source string literals, so collapse
        # whitespace and quotes before matching the user-visible phrase.
        collapsed = source.replace('"', "").replace("'", "")
        collapsed = "".join(collapsed.split())
        self.assertIn("resizedandconvertedforyou", collapsed)


class DigitalFontConversionTests(unittest.TestCase):
    """The score-digit slot converts any image instead of refusing it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def test_an_opaque_jpeg_becomes_a_white_alpha_mask(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "digits.jpg"
            image = Image.new("RGB", (300, 100), (0, 0, 0))
            # A bright bar stands in for the digit strokes.
            for x in range(100, 200):
                for y in range(20, 80):
                    image.putpixel((x, y), (255, 255, 255))
            image.save(source, "JPEG")
            destination = Path(directory) / "mask.png"

            with mock.patch.object(
                gui.QMessageBox, "question", return_value=QMessageBox.Yes
            ) as question, mock.patch.object(gui.QMessageBox, "information"):
                prepared = gui._prepare_digital_font_mask(
                    None, source, destination
                )
            self.assertEqual(prepared, destination)
            # The offer explains the mask conversion in plain words.
            body = question.call_args.args[2]
            self.assertIn("alpha channel", body)
            self.assertIn("solid white", body)
            self.assertIn("not modified", body)

            with Image.open(destination) as mask:
                self.assertEqual(mask.size, (128, 128))
                self.assertEqual(mask.mode, "RGBA")
                red = mask.getchannel("R").getextrema()
                green = mask.getchannel("G").getextrema()
                blue = mask.getchannel("B").getextrema()
                alpha_min, alpha_max = mask.getchannel("A").getextrema()
            # The writer contract: RGB solid white, digits drawn in alpha.
            self.assertEqual(red, (255, 255))
            self.assertEqual(green, (255, 255))
            self.assertEqual(blue, (255, 255))
            self.assertEqual(alpha_min, 0)
            self.assertGreater(alpha_max, 200)

    def test_declining_the_conversion_stages_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "digits.png"
            Image.new("RGBA", (200, 200), (10, 10, 10, 255)).save(source)
            destination = Path(directory) / "mask.png"
            with mock.patch.object(
                gui.QMessageBox, "question", return_value=QMessageBox.Cancel
            ), mock.patch.object(gui.QMessageBox, "information"):
                prepared = gui._prepare_digital_font_mask(
                    None, source, destination
                )
            self.assertIsNone(prepared)
            self.assertFalse(destination.exists())

    def test_unreadable_files_are_refused_with_a_fix_not_jargon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            junk = Path(directory) / "junk.png"
            junk.write_bytes(b"this is not an image")
            with mock.patch.object(
                gui.QMessageBox, "information"
            ) as information:
                prepared = gui._prepare_digital_font_mask(
                    None, junk, Path(directory) / "mask.png"
                )
            self.assertIsNone(prepared)
            title, body = information.call_args.args[1], \
                information.call_args.args[2]
            self.assertIn("could not be read as an image", title.casefold())
            self.assertIn("Fix:", body)
            self.assertIn("resizes it for you", body)


class AppleDoubleRefusalTests(unittest.TestCase):
    """macOS ``._name`` resource forks are refused with a plain next step."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    class _UrlEvent:
        """Just enough of a QDropEvent for the panels' handlers."""

        def __init__(self, urls):
            self._urls = urls
            self.accepted = False
            self.ignored = False

        def mimeData(self):
            return self

        def hasUrls(self):
            return bool(self._urls)

        def urls(self):
            return self._urls

        def acceptProposedAction(self):
            self.accepted = True

        def ignore(self):
            self.ignored = True

    def test_apf_drop_refuses_a_resource_fork_twin(self) -> None:
        from PyQt5.QtCore import QUrl

        label = gui.ImageDropLabel()
        try:
            twin = Path(tempfile.gettempdir()) / "._player_face.png"
            event = self._UrlEvent([QUrl.fromLocalFile(str(twin))])
            with mock.patch.object(gui.QMessageBox, "information") as information:
                label.dropEvent(event)
            self.assertTrue(event.ignored)
            self.assertFalse(event.accepted)
            body = information.call_args.args[2]
            self.assertIn("macOS resource-fork file", body)
            self.assertIn("Drop the visible PNG instead", body)
        finally:
            label.deleteLater()
            self.application.processEvents()

    def test_apf_image_fit_refuses_a_resource_fork_twin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            twin = Path(directory) / "._player_face.png"
            twin.write_bytes(b"not the image")
            with mock.patch.object(gui.QMessageBox, "information") as information:
                prepared = gui.fit_slot_image(
                    None,
                    twin,
                    512,
                    512,
                    "The number_1_color jersey digit",
                    mode="contain",
                    staged_destination=Path(directory) / "fitted.png",
                )
            self.assertIsNone(prepared)
            body = information.call_args.args[2]
            self.assertIn("macOS resource-fork file", body)

    def test_2k5_studio_drop_refuses_a_resource_fork_twin(self) -> None:
        from PyQt5.QtCore import QUrl

        from mod_editor.gui import studio_qt

        preview = studio_qt._PngDropPreview()
        try:
            twin = Path(tempfile.gettempdir()) / "._portrait_2k5.png"
            event = AppleDoubleRefusalTests._UrlEvent(
                [QUrl.fromLocalFile(str(twin))]
            )
            with mock.patch.object(
                studio_qt.QMessageBox, "information"
            ) as information:
                preview.dropEvent(event)
            self.assertTrue(event.ignored)
            body = information.call_args.args[2]
            self.assertIn("macOS resource-fork file", body)
            self.assertIn("Drop the visible PNG instead", body)
        finally:
            preview.deleteLater()
            self.application.processEvents()

    def test_2k5_visual_drop_route_refuses_before_any_state(self) -> None:
        from mod_editor.gui import studio_qt

        seen: list[str] = []

        class _Stub:
            def _show_error(self, message: str) -> None:
                seen.append(message)

        # The guard fires before any selection/source state is consulted.
        studio_qt.StudioMainWindow._replace_visual_from_drop(
            _Stub(),  # type: ignore[arg-type]
            None,
            Path("/somewhere/._portrait_2k5.png"),
        )
        self.assertEqual(len(seen), 1)
        self.assertIn("macOS resource-fork file", seen[0])


class _RefusalFacade:
    """Enough catalog for a browser to answer refusals, with no archive."""

    def __init__(self, assets, number_budget=None):
        from mod_editor.apf_studio.catalog import ApfCatalog

        self.assets = tuple(assets)
        self._number_budget = number_budget
        self.catalog = ApfCatalog(
            source_sha256="f" * 64,
            outer_count=len(self.assets),
            iff_count=len(self.assets),
            non_iff_count=0,
            inner_count=len(self.assets),
            assets=self.assets,
            uniform_assets=(),
            capabilities=(),
            audio_selection_manifest=Path("synthetic-inner-selection.json"),
        )
        self.source_ready = True
        self.modified_asset_ids: frozenset[str] = frozenset()

    def require_catalog(self):
        return self.catalog

    def uniform_assets(self, family=None):
        return ()

    def browse_assets(self, **kwargs):
        return self.catalog.browse(**kwargs)

    def capability_cards(self, _category=None):
        return ()

    def preview_asset(self, *_args, **_kwargs):
        # The refusal tests never assert on preview pixels.
        return Path("/nonexistent/preview.png")

    def number_package_budget(self, entry_index, *_args, **_kwargs):
        if self._number_budget is None:
            raise RuntimeError("no budget model in this stub")
        return dict(self._number_budget)


_ROSTER_INNER_INDEXES: dict[str, int] = {}


def _roster_asset(name: str, *, category=None) -> object:
    from mod_editor.apf_studio.models import (
        ApfAsset,
        ApfCategory,
        ApfStatus,
    )

    inner = _ROSTER_INNER_INDEXES.setdefault(
        name, len(_ROSTER_INNER_INDEXES)
    )
    return ApfAsset(
        asset_id=f"apf:outer:1500:inner:{inner}",
        outer_index=1500,
        inner_index=inner,
        name=name,
        type_name="TXTR",
        asset_class="texture",
        category=category if category is not None else ApfCategory.ROSTERS,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=65_600,
        outer_size=12_288,
        part_count=2,
    )


def _digit_asset() -> object:
    from mod_editor.apf_studio import number_targets
    from mod_editor.apf_studio.models import (
        ApfAsset,
        ApfCategory,
        ApfStatus,
    )

    row = next(
        item
        for item in number_targets.load_targets()
        if str(item["name"]) == "number_1_color"
        and int(item["entry_index"]) == 862
    )
    asset_id = f"apf:outer:{row['entry_index']}:inner:{row['file_index']}"
    binding = number_targets.action_binding(
        asset_id,
        int(row["entry_index"]),
        int(row["file_index"]),
        str(row["name"]),
        "TXTR",
    )
    assert binding is not None
    return ApfAsset(
        asset_id=asset_id,
        outer_index=int(row["entry_index"]),
        inner_index=int(row["file_index"]),
        name=str(row["name"]),
        type_name="TXTR",
        asset_class="texture",
        category=ApfCategory.UNIFORMS,
        status=ApfStatus.EDITABLE,
        decoded_size=1_048_576,
        outer_size=int(row["entry_size"]),
        part_count=2,
        # The real catalog ships the binding's own notes on the asset.
        notes=binding.notes,
    )


def _run_task_inline(_label, operation, complete, *_flags):
    complete(operation(lambda *_a, **_k: None))


class FaceScanRefusalTests(unittest.TestCase):
    """APF 2K8 face/head rows state the export-only boundary up front."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _browser(self, assets, number_budget=None):
        from mod_editor.apf_studio.gui import AssetBrowser
        from mod_editor.apf_studio.models import ApfCategory

        facade = _RefusalFacade(assets, number_budget=number_budget)
        browser = AssetBrowser(
            facade,  # type: ignore[arg-type]
            ApfCategory.ALL_ASSETS,
            _run_task_inline,
        )
        browser.refresh()
        self.application.processEvents()
        return browser

    def _select(self, browser, name: str):
        for row in range(browser.table.rowCount()):
            if browser.table.item(row, 1).text() == name:
                browser.table.selectRow(row)
                self.application.processEvents()
                browser._selection_changed()
                return browser._selected_asset()
        raise AssertionError(f"no row named {name}")

    def test_face_row_refusal_names_the_boundary_and_the_2k5_route(self) -> None:
        browser = self._browser([_roster_asset("player_head_scan_07")])
        try:
            self._select(browser, "player_head_scan_07")
            reason = str(browser.replace_button.property("disableReason") or "")
            self.assertIn("no proved writer", reason)
            self.assertIn("hi_head", reason)
            self.assertIn("2K5 Mod Studio", reason)
            self.assertIn("Portraits & Faces", reason)
            self.assertNotIn("editing unlocks when an exact writer exists", reason)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_face_row_dialogs_use_the_dedicated_title(self) -> None:
        browser = self._browser([_roster_asset("portrait_team_03")])
        try:
            self._select(browser, "portrait_team_03")
            with mock.patch.object(gui.QMessageBox, "information") as information:
                browser._replace_selected()
            self.assertEqual(
                information.call_args.args[1], gui.FACE_SCAN_REFUSAL_TITLE
            )
            self.assertIn("hi_head", information.call_args.args[2])
            self.assertIn("2K5 Mod Studio", information.call_args.args[2])

            with mock.patch.object(gui.QMessageBox, "information") as dropped:
                browser._replace_from_drop(Path("/tmp/face.png"))
            self.assertEqual(dropped.call_args.args[1], gui.FACE_SCAN_REFUSAL_TITLE)
            self.assertIn("Portraits & Faces", dropped.call_args.args[2])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_non_face_roster_rows_keep_the_generic_refusal(self) -> None:
        browser = self._browser([_roster_asset("roster_team_table")])
        try:
            self._select(browser, "roster_team_table")
            reason = str(browser.replace_button.property("disableReason") or "")
            self.assertIn("No proved writer owns", reason)
            self.assertNotIn("Face scans", reason)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_face_named_rows_outside_rosters_keep_the_generic_refusal(self) -> None:
        from mod_editor.apf_studio.models import ApfCategory

        browser = self._browser(
            [_roster_asset("stadium_head_tower", category=ApfCategory.STADIUMS)]
        )
        try:
            self._select(browser, "stadium_head_tower")
            reason = str(browser.replace_button.property("disableReason") or "")
            self.assertIn("No proved writer owns", reason)
            self.assertNotIn("Face scans", reason)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_browse_locked_face_rows_use_the_same_boundary(self) -> None:
        from mod_editor.apf_studio.gui import AssetBrowser
        from mod_editor.apf_studio.models import ApfCategory

        facade = _RefusalFacade([_roster_asset("player_face_scan_12")])
        browser = AssetBrowser(
            facade,  # type: ignore[arg-type]
            ApfCategory.ALL_ASSETS,
            _run_task_inline,
            browse_export_only=True,
            action_lock_reason="This browse surface is export-only.",
        )
        browser.refresh()
        self.application.processEvents()
        try:
            self._select(browser, "player_face_scan_12")
            lock = str(browser.replace_button.property("disableReason") or "")
            self.assertIn("hi_head", lock)
            self.assertIn("2K5 Mod Studio", lock)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_digit_rows_show_the_package_budget_before_authoring(self) -> None:
        browser = self._browser(
            [_digit_asset()],
            number_budget={
                "outer_index": 862,
                "free_bytes": 917,
                "retail_bytes": 1_650_077,
                "budget_bytes": 1_650_994,
            },
        )
        try:
            asset = self._select(browser, "number_1_color")
            self.assertEqual(asset.outer_index, 862)
            notes = browser.detail_notes.text()
            self.assertIn("Free in this package: 917 bytes", notes)
            self.assertIn("Band: tight", notes)
            self.assertIn("overflow check", notes)
            # The honesty line from the family panel travels with the row.
            self.assertIn("usually fits", notes)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_digit_rows_with_room_name_the_solid_only_band(self) -> None:
        browser = self._browser(
            [_digit_asset()],
            number_budget={
                "outer_index": 862,
                "free_bytes": 2_044,
                "retail_bytes": 1_000_000,
                "budget_bytes": 1_002_044,
            },
        )
        try:
            self._select(browser, "number_1_color")
            notes = browser.detail_notes.text()
            self.assertIn("Free in this package: 2,044 bytes", notes)
            self.assertIn("Band: loose", notes)
            self.assertNotIn("no_custom_digit_fits", notes)
        finally:
            browser.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()

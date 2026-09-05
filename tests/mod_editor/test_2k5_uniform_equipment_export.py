"""Package-local 2K5 equipment must be findable and safely editable.

The editor previously called its 39 writable surfaces a "Complete Team Kit"
while hiding 45 embedded equipment references per uniform package. This suite
pins the bounded writer: all 28,530 reviewed socks/elbow-pad/glove/long-sleeve/
shoe/wristband references are swizzled P8 palette imports. Each selected palette
changes inside one fixed TSET span while shared indices and siblings stay exact.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PyQt5.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PyQt5.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.core.product_catalog import ProductCategory  # noqa: E402
from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_ROOT, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))
_CATALOG_PATH = (
    _ROOT / "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json"
)
_PACK0 = _ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
_INVENTORY = _ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
_XISO = _ROOT / "ESPN NFL 2K5 (USA).xiso.iso"


class CompactCatalogTests(unittest.TestCase):
    def test_catalog_identity_count_and_contract_are_pinned(self) -> None:
        from mod_editor.core.nfl2k5_extended_visual_catalog import (
            UNIFORM_EQUIPMENT_CATALOG_SHA256,
            UNIFORM_EQUIPMENT_CATALOG_SIZE,
        )

        payload = _CATALOG_PATH.read_bytes()
        document = json.loads(payload)
        self.assertEqual(len(payload), UNIFORM_EQUIPMENT_CATALOG_SIZE)
        self.assertEqual(hashlib.sha256(payload).hexdigest(),
                         UNIFORM_EQUIPMENT_CATALOG_SHA256)
        self.assertEqual(document["summary"], {
            "package_count": 634,
            "target_count": 28_530,
            "targets_per_package": 45,
        })
        self.assertEqual(document["contract"]["access"],
                         "preview-export-and-palette-import")
        self.assertEqual(document["contract"]["import_mode"],
                         "fixed-shared-index-palette")
        self.assertTrue(document["contract"]["import_supported"])
        self.assertFalse(document["contract"]["retail_payload_bytes"])

    def test_every_package_has_the_exact_45_reference_shape(self) -> None:
        document = json.loads(_CATALOG_PATH.read_bytes())
        columns = document["columns"]
        by_package: dict[int, Counter[int]] = {}
        selectors: set[tuple[int, int, int]] = set()
        for raw in document["rows"]:
            row = dict(zip(columns, raw))
            key = (
                row["outer_index"], row["tset_chunk_index"],
                row["reference_index"],
            )
            self.assertNotIn(key, selectors)
            selectors.add(key)
            by_package.setdefault(row["outer_index"], Counter())[
                row["tset_chunk_index"]
            ] += 1
        self.assertEqual(len(by_package), 634)
        expected = Counter({4: 2, 5: 14, 6: 8, 7: 6, 8: 6, 9: 6, 10: 3})
        self.assertTrue(all(counts == expected for counts in by_package.values()))

    def test_shipped_catalog_exactly_rebuilds_from_the_reviewed_inventory(self) -> None:
        from tools.build_nfl2k5_uniform_equipment_export_catalog import (
            build,
            serialize,
        )

        rebuilt = build(
            _ROOT / "reports/assets/nfl2k5_uniform_tset_textures.tsv"
        )
        shipped = _CATALOG_PATH.read_bytes()
        expected = json.loads(shipped)
        self.assertEqual(rebuilt, expected)
        self.assertEqual(serialize(rebuilt), shipped)
        self.assertLessEqual(max(map(len, shipped.splitlines())), 4_096)


class ProductInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.nfl2k5_extended_visual_catalog import (
            load_nfl2k5_extended_visual_catalog,
        )

        cls.catalog = load_nfl2k5_extended_visual_catalog()
        cls.assets = cls.catalog.assets_for_kind("uniform_equipment_texture")

    def test_all_six_missing_equipment_families_are_findable(self) -> None:
        self.assertEqual(len(self.assets), 28_530)
        counts = Counter(
            asset.equipment_descriptor.chunk_index for asset in self.assets
            if asset.equipment_descriptor is not None
        )
        self.assertEqual(counts, {
            4: 1_268,
            5: 8_876,
            6: 5_072,
            7: 3_804,
            8: 3_804,
            9: 3_804,
            10: 1_902,
        })
        for term in ("socks00", "elbowpad01", "glove01", "longsleeve01",
                     "shoes01", "wristband01"):
            with self.subTest(term=term):
                self.assertTrue(any(asset.texture == term for asset in self.assets))

    def test_titans_socks_are_editable_through_the_typed_project_route(self) -> None:
        from mod_editor.core.nfl2k5_extended_visual_catalog import VisualWriterRoute

        asset = next(
            row for row in self.assets
            if "28H0" in row.search_terms and row.texture == "socks00"
        )
        self.assertEqual(
            asset.label,
            "Socks 00 — Tennessee Titans Home",
        )
        self.assertEqual(asset.dimensions, (64, 64))
        self.assertTrue(asset.editable)
        self.assertIs(asset.writer_route, VisualWriterRoute.UNIFIED_VISUAL)
        self.assertEqual(asset.provider_edit("socks.png"), {
            "asset_id": asset.asset_id,
            "kind": "uniform_equipment_texture",
            "png": "socks.png",
        })

    def test_every_equipment_id_and_physical_selector_is_unique(self) -> None:
        self.assertEqual(len({asset.asset_id for asset in self.assets}), 28_530)
        self.assertEqual(len({
            (
                asset.equipment_descriptor.outer_index,
                asset.equipment_descriptor.chunk_index,
                asset.equipment_descriptor.reference_index,
            )
            for asset in self.assets
            if asset.equipment_descriptor is not None
        }), 28_530)


class StudioTruthfulEquipmentBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (_ROOT / "mod_editor/gui/studio_qt.py").read_text()
        tree = ast.parse(cls.source)
        cls.string_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }

    def test_all_textures_includes_package_local_equipment(self) -> None:
        self.assertIn(
            '"p8_texture", "uniform_equipment_texture"', self.source
        )

    def test_team_kit_name_and_equipment_scope_note_are_exact_and_honest(self) -> None:
        self.assertIn(
            "Whole kit (39 parts per uniform)", self.string_literals
        )
        self.assertIn(
            "All 45 socks, elbow pads, gloves, long sleeves, shoes and wristbands of the "
            "selected uniform use the same project and Make disc from project path.",
            self.string_literals,
        )
        self.assertIn(
            "39 editable parts · 45 equipment textures",
            self.string_literals,
        )
        self.assertIn("Equipment (socks, gloves, shoes…)", self.string_literals)

    def test_unsupported_formats_still_have_an_explicit_export_only_state(self) -> None:
        self.assertIn(
            "if asset.writer_route is VisualWriterRoute.EXPORT_ONLY", self.source
        )
        self.assertIn("\"view only (export)\"", self.source)
        # Never silent-gray: export/edit/replace stay clickable with disableReason.
        self.assertIn("state.export_button.setEnabled(True)", self.source)
        self.assertIn('setProperty("disableReason"', self.source)
        self.assertIn("edit_ok = bool(", self.source)
        self.assertIn("edit_block", self.source)
        self.assertIn("state.preview.set_replacement_enabled(edit_ok)", self.source)
        self.assertIn(
            'state.status_pill.set_status("Export only", "#91a0b5")',
            self.source,
        )

    def test_visual_dialog_and_drop_still_share_the_proved_resize_path(self) -> None:
        def calls(name: str) -> set[str]:
            tree = ast.parse(self.source)
            node = next(
                item for item in ast.walk(tree)
                if isinstance(item, ast.FunctionDef) and item.name == name
            )
            return {
                inner.func.attr
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
            }

        self.assertIn("_replace_visual_asset", calls("_choose_visual_replacement"))
        self.assertIn("_replace_visual_asset", calls("_replace_visual_from_drop"))
        self.assertIn("_fit_for_slot", calls("_replace_visual_asset"))


class _EquipmentResizeFacade(BrowseOnlyFacade):
    def __init__(self) -> None:
        self.source_ready = False
        self.source_display_name = "Synthetic NFL 2K5"
        self.source_path = Path("/private/NFL2K5.iso")
        self.source_sha256 = "b" * 64
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.modified_count = 0
        self.can_undo = False
        self.can_launch_xemu = False
        self.received: list[tuple[str, Path, tuple[int, int]]] = []

    def replace_asset(self, asset: object, path: Path, progress: object) -> object:
        progress("Checking fitted equipment PNG", 1, 1)  # type: ignore[operator]
        with Image.open(path) as image:
            size = image.size
        self.received.append((asset.asset_id, Path(path), size))  # type: ignore[attr-defined]
        return SimpleNamespace(message="Equipment palette is ready to build.")


class EquipmentResizeOffscreenTests(unittest.TestCase):
    """Actual All Textures dialog/drop events must reach the shared fitter."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="2k5-equipment-qt-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "oversize-socks.png"
        Image.new("RGBA", (128, 128), (18, 140, 80, 255)).save(self.source)
        self.original = self.source.read_bytes()
        self.facade = _EquipmentResizeFacade()
        self.window = StudioMainWindow(
            facade=self.facade,
            offer_recovery=False,
        )
        self.window._fit_dir = self.root / "fitted"
        self.window._fit_dir.mkdir()
        self.errors: list[str] = []
        self.window._show_error = self.errors.append  # type: ignore[method-assign]
        self.window._mark_workspace_changed = (  # type: ignore[method-assign]
            lambda **_kwargs: None
        )
        self.window._filter_visual_assets = (  # type: ignore[method-assign]
            lambda _category: None
        )
        self.window._load_visual_preview = (  # type: ignore[method-assign]
            lambda _asset, _preview: None
        )

        def immediate(operation: object, success: object, **_kwargs: object) -> None:
            result = operation(lambda *_args: None)  # type: ignore[operator]
            success(result)  # type: ignore[operator]

        self.window._start_task = immediate  # type: ignore[method-assign]
        self.facade.source_ready = True
        self.asset = next(
            row for row in self.window.extended_visual_catalog.assets_for_kind(
                "uniform_equipment_texture"
            )
            if "28H0" in row.search_terms and row.texture == "socks00"
        )
        self.state = self.window._visual_browsers[ProductCategory.TEXTURES]
        self.state.selected_asset_id = self.asset.asset_id
        self.window._selected_asset = self.asset
        # Never-silent-gray paths check disableReason before opening the dialog.
        self.state.replace_button.setEnabled(True)
        self.state.replace_button.setProperty("disableReason", "")
        self.state.replace_button.setToolTip("Replace this equipment texture.")
        self.state.preview.set_replacement_enabled(True)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.window._allow_close = True
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
        self.temporary.cleanup()

    def _assert_resized(self) -> None:
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.facade.received), 1)
        asset_id, fitted, size = self.facade.received[0]
        self.assertEqual(asset_id, self.asset.asset_id)
        self.assertNotEqual(fitted, self.source)
        self.assertEqual(size, (64, 64))
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_file_dialog_resizes_equipment_before_session_replace(self) -> None:
        with (
            patch(
                "mod_editor.gui.studio_qt.QFileDialog.getOpenFileName",
                return_value=(str(self.source), "PNG image (*.png)"),
            ),
            patch(
                "mod_editor.gui.studio_qt.QInputDialog.getItem",
                return_value=(
                    "Cover — fill the slot, crop overflow",
                    True,
                ),
            ) as chooser,
        ):
            QTest.mouseClick(self.state.replace_button, Qt.LeftButton)
            self.application.processEvents()
        chooser.assert_called_once()
        self._assert_resized()

    def test_drag_drop_resizes_equipment_before_session_replace(self) -> None:
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.source))])
        enter = QDragEnterEvent(
            QPoint(6, 6), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        dropped = QDropEvent(
            QPointF(6, 6), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier
        )
        with patch(
            "mod_editor.gui.studio_qt.QInputDialog.getItem",
            return_value=(
                "Cover — fill the slot, crop overflow",
                True,
            ),
        ) as chooser:
            QApplication.sendEvent(self.state.preview, enter)
            QApplication.sendEvent(self.state.preview, dropped)
            self.application.processEvents()
        self.assertTrue(enter.isAccepted())
        self.assertTrue(dropped.isAccepted())
        chooser.assert_called_once()
        self._assert_resized()


@unittest.skipUnless(_PACK0.is_file(), "private extracted NFL 2K5 fixture absent")
class RealSourceDecodeTests(unittest.TestCase):
    def setUp(self) -> None:
        from mod_editor.core.nfl2k5_extended_visual_catalog import (
            load_nfl2k5_extended_visual_catalog,
        )

        catalog = load_nfl2k5_extended_visual_catalog()
        self.asset = next(
            row for row in catalog.assets_for_kind("uniform_equipment_texture")
            if "28H0" in row.search_terms and row.texture == "socks00"
        )

    def test_titans_socks_preview_and_export_from_reviewed_source_hashes(self) -> None:
        from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ExtendedVisualIO
        import nfl_tset_png_import as png_codec

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = SimpleNamespace(
                originals=root / "originals",
                pack0=_PACK0,
                source=SimpleNamespace(sha256="retail-fixture"),
            )
            cache.originals.mkdir()
            io = Nfl2k5ExtendedVisualIO(cache)
            original = io.ensure_original(self.asset)
            width, height, rgba = png_codec.decode_rgba_png(
                original.read_bytes(), self.asset.dimensions
            )
            self.assertEqual((width, height), (64, 64))
            self.assertEqual(len(rgba), 64 * 64 * 4)
            exported = io.export_original(self.asset, root / "titans-socks.png")
            self.assertEqual(exported.read_bytes(), original.read_bytes())

    def test_source_hash_drift_is_refused(self) -> None:
        from mod_editor.core.errors import ValidationError
        from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ExtendedVisualIO

        with tempfile.TemporaryDirectory() as directory:
            cache = SimpleNamespace(
                originals=Path(directory),
                pack0=_PACK0,
                source=SimpleNamespace(sha256="retail-fixture"),
            )
            assert self.asset.equipment_descriptor is not None
            changed = replace(
                self.asset,
                equipment_descriptor=replace(
                    self.asset.equipment_descriptor,
                    base_pixel_sha256="0" * 64,
                ),
            )
            with self.assertRaisesRegex(ValidationError, "reviewed source hashes"):
                Nfl2k5ExtendedVisualIO(cache).ensure_original(changed)

    def test_every_equipment_family_round_trips_inside_one_fixed_tset_span(
        self,
    ) -> None:
        """One real target per physical layout, including both shoe TSETs."""

        from mod_editor.core.nfl2k5_extended_visual_catalog import (
            load_nfl2k5_extended_visual_catalog,
        )
        from mod_editor.core.nfl2k5_uniform_equipment_writer import (
            build_unified_uniform_equipment_imports,
        )
        from nfl_outer import parse_archive, read_entry_bytes
        from nfl_txtr import decode_chunk, encode_rgba_png, parse_chunks

        catalog = load_nfl2k5_extended_visual_catalog()
        assets = catalog.assets_for_kind("uniform_equipment_texture")
        selected = [
            next(
                row for row in assets
                if "28H0" in row.search_terms and row.texture == texture
            )
            for texture in (
                "socks00",
                "elbowpad01",
                "glove01",
                "longsleeve01",
                "shoes01",
                "shoes02",
                "wristband01",
            )
        ]
        archive = parse_archive(_PACK0)
        pack_hashes: dict[str, str] = {}
        with tempfile.TemporaryDirectory(prefix="2k5-equipment-roundtrip-") as name:
            root = Path(name)
            for asset in selected:
                with self.subTest(texture=asset.texture):
                    assert asset.equipment_descriptor is not None
                    descriptor = asset.equipment_descriptor
                    rgba = b"".join(
                        bytes((
                            24 + (x // 8) * 19 % 220,
                            32 + (y // 8) * 17 % 210,
                            210 if (x // 16 + y // 16) & 1 else 42,
                            255,
                        ))
                        for y in range(asset.height)
                        for x in range(asset.width)
                    )
                    png = root / f"{asset.texture}.png"
                    png.write_bytes(encode_rgba_png(
                        asset.width, asset.height, rgba
                    ))
                    replacement, previews, report, selector, target = \
                        build_unified_uniform_equipment_imports(
                            _PACK0,
                            [(asset.asset_id, png)],
                            pack_hashes=pack_hashes,
                        )

                    entry = archive.entries[descriptor.outer_index]
                    package = read_entry_bytes(archive, entry)
                    chunk = next(
                        row for row in parse_chunks(package, allow_trailing=True)
                        if row.index == descriptor.chunk_index
                    )
                    retail_span = package[chunk.offset:chunk.end_offset]
                    anchored = replace(chunk, offset=0)
                    retail_decoded, retail_info = decode_chunk(
                        retail_span, anchored
                    )
                    rebuilt_decoded, rebuilt_info = decode_chunk(
                        replacement, anchored
                    )
                    start = chunk.system_bytes + descriptor.palette_offset
                    end = start + 1_024
                    self.assertEqual(len(replacement), len(retail_span))
                    self.assertNotEqual(replacement, retail_span)
                    self.assertEqual(retail_decoded[:start], rebuilt_decoded[:start])
                    self.assertEqual(retail_decoded[end:], rebuilt_decoded[end:])
                    self.assertIsNotNone(retail_info)
                    self.assertIsNotNone(rebuilt_info)
                    self.assertLessEqual(
                        rebuilt_info.consumed_bytes, chunk.stored_size
                    )
                    self.assertEqual(len(previews), 1)
                    self.assertEqual(report["target"], target)
                    self.assertEqual(
                        report["bounded_palette_fit"]["attempts"][-1]["result"],
                        "fit",
                    )
                    self.assertEqual(
                        selector,
                        f"uniform-equipment-tset:"
                        f"{descriptor.outer_index}:{descriptor.chunk_index}",
                    )


@unittest.skipUnless(
    _PACK0.is_file() and _INVENTORY.is_file() and _XISO.is_file(),
    "private retail NFL 2K5 composer fixtures absent",
)
class RealComposedEquipmentProjectTests(unittest.TestCase):
    def test_two_socks_palettes_compose_as_one_span_and_reopen(self) -> None:
        """The public logical route groups overlapping clean/mud palette edits."""

        import nfl2k5_visual_mod_project as project_builder
        from nfl_txtr import decode_chunk, encode_rgba_png, parse_chunks

        with tempfile.TemporaryDirectory(prefix="2k5-equipment-project-") as name:
            root = Path(name)
            edits = []
            for reference, texture, colors in (
                (0, "socks00", ((10, 80, 55, 255), (235, 245, 230, 255))),
                (1, "socks00_mud", ((45, 24, 12, 255), (155, 112, 70, 255))),
            ):
                png = root / f"{texture}.png"
                rgba = b"".join(
                    bytes(colors[(x // 8 + y // 8) & 1])
                    for y in range(64) for x in range(64)
                )
                png.write_bytes(encode_rgba_png(64, 64, rgba))
                edits.append({
                    "asset_id": f"tset:3850:4:{reference}:{texture}",
                    "kind": "uniform_equipment_texture",
                    "png": png.name,
                })
            project_path = root / "equipment.2k5-project.json"
            project_path.write_bytes(project_builder.canonical_json({
                "schema": project_builder.SCHEMA,
                "purpose": "Package-local equipment fixed-span regression",
                "edits": edits,
            }))

            project = project_builder.read_project(project_path)
            index_pin = project_builder.ownership.pin_large_file(
                _PACK0,
                "canonical extracted pack 0",
                project_builder.INDEX_SIZE,
                project_builder.INDEX_SHA256,
            )
            inventory_pin = None
            source_fd = None
            prepared = None
            try:
                inventory_pin = project_builder.ownership.pin_large_file(
                    _INVENTORY,
                    "canonical chunk inventory",
                    project_builder.INVENTORY_SIZE,
                    project_builder.INVENTORY_SHA256,
                )
                source_fd = os.open(_XISO, os.O_RDONLY)
                entries, _directory = project_builder.common.parse_xdvdfs(
                    source_fd, os.fstat(source_fd).st_size
                )
                prepared = project_builder.prepare_project(
                    project,
                    index_pin,
                    inventory_pin,
                    {},
                    root,
                    source_fd,
                    entries,
                )
                self.assertEqual(len(prepared.edits), 1)
                edit = prepared.edits[0]
                self.assertEqual(edit.kind, "uniform_equipment_texture")
                self.assertEqual(edit.selector, "uniform-equipment-tset:3850:4")
                self.assertEqual(len(edit.project_edit["edits"]), 2)
                project_builder.bind_prepared_to_source(
                    prepared, source_fd, entries
                )
                project_builder.verify_prepared_pins(
                    project, prepared, index_pin, inventory_pin
                )
                self.assertTrue(edit.relative_runs)

                guard = 4_096
                source_window = project_builder.common.read_exact(
                    source_fd,
                    edit.absolute - guard,
                    guard + edit.replacement_size + guard,
                )
                candidate = root / "composed-equipment-window.bin"
                candidate.write_bytes(source_window)
                candidate_fd = os.open(candidate, os.O_RDWR)
                try:
                    project_builder.write_all(
                        candidate_fd, guard, edit.replacement_path.read_bytes()
                    )
                    os.fsync(candidate_fd)
                finally:
                    os.close(candidate_fd)
                _resolved, reopened, _identity = \
                    project_builder.read_regular_bounded(
                        candidate,
                        len(source_window),
                        "composed equipment XISO window",
                    )
                self.assertEqual(reopened[:guard], source_window[:guard])
                self.assertEqual(
                    reopened[guard + edit.replacement_size:],
                    source_window[guard + edit.replacement_size:],
                )
                chunks = parse_chunks(
                    reopened[guard:guard + edit.replacement_size]
                )
                self.assertEqual(len(chunks), 1)
                decoded, info = decode_chunk(
                    reopened[guard:guard + edit.replacement_size], chunks[0]
                )
                self.assertEqual(
                    len(decoded), chunks[0].system_bytes + chunks[0].video_bytes
                )
                self.assertIsNotNone(info)
                self.assertLessEqual(info.consumed_bytes, chunks[0].stored_size)
            finally:
                if source_fd is not None:
                    os.close(source_fd)
                if inventory_pin is not None:
                    os.close(inventory_pin.descriptor)
                os.close(index_pin.descriptor)
                if prepared is not None:
                    leftovers = project_builder.ownership.cleanup_owned(
                        prepared.temp_files, [prepared.temp_root]
                    )
                    self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()

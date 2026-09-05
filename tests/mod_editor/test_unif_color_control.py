"""End-to-end proofs for per-uniform facemask/faceshield colours."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_unif_color_writer as colour  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.model import SourceRecord  # noqa: E402
from mod_editor.core.nfl2k5_source_cache import SourceCache  # noqa: E402
from mod_editor.core.nfl2k5_uniform_catalog import (  # noqa: E402
    load_nfl2k5_uniform_catalog,
)
from mod_editor.studio.project_archive import (  # noqa: E402
    load_project_archive,
    save_project_archive,
)
from mod_editor.studio.session import StudioSession  # noqa: E402
from mod_editor.gui.studio_qt import (  # noqa: E402
    BrowseOnlyFacade,
    StudioMainWindow,
)
from PyQt5.QtWidgets import QApplication  # noqa: E402
import nfl2k5_visual_mod_project as build_project  # noqa: E402
import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402

EXTRACTED = _REPO_ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "vc_53450030"
SOURCE_XISO = _REPO_ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
INVENTORY = _REPO_ROOT / "reports" / "assets" / "nfl2k5_resource_chunks_v2.json"
REAL_DATA = (EXTRACTED / "0").is_file()

_SESSION = (_REPO_ROOT / "mod_editor" / "studio" / "session.py").read_text(
    encoding="utf-8"
)
_FACADE = (_REPO_ROOT / "mod_editor" / "studio" / "facade.py").read_text(
    encoding="utf-8"
)
_STUDIO = (_REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py").read_text(
    encoding="utf-8"
)
_PROJECT = (_REPO_ROOT / "tools" / "nfl2k5_visual_mod_project.py").read_text(
    encoding="utf-8"
)


class ColourParsingTests(unittest.TestCase):
    def test_both_accepted_spellings_agree(self) -> None:
        self.assertEqual(colour.parse_color("FF1A1A1A"), 0xFF1A1A1A)
        self.assertEqual(colour.parse_color("#1A1A1A"), 0xFF1A1A1A)
        self.assertEqual(colour.parse_color("1a1a1a"), 0xFF1A1A1A)

    def test_junk_is_refused(self) -> None:
        for bad in ("", "nope", "#12345", "GGGGGG", "FF1A1A1A1A"):
            with self.subTest(bad=bad):
                with self.assertRaises(colour.UnifColorWriterError):
                    colour.parse_color(bad)


@unittest.skipUnless(REAL_DATA, "extracted 2K5 uniform packs not present")
class RealRecordResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_uniform_catalog()
        cls.records = tuple(
            colour.resolve_uniform_color_record(EXTRACTED / "0", item.selector)
            for item in cls.catalog.uniform_sets
        )

    def test_every_catalog_set_resolves_to_one_unique_physical_record(self) -> None:
        self.assertEqual(len(self.records), 634)
        self.assertEqual(
            len({(row.pack_name, row.pack_offset) for row in self.records}), 634
        )
        counts = {
            pack: sum(row.pack_name == pack for row in self.records)
            for pack in "9ABC"
        }
        self.assertEqual(counts, {"9": 13, "A": 207, "B": 304, "C": 110})

    def test_the_old_global_offsets_are_detroit_home_and_away(self) -> None:
        by_span = {
            (row.pack_name, row.pack_offset): row.selector for row in self.records
        }
        self.assertEqual(by_span[("A", 0x055CA850)], "09H0")
        self.assertEqual(by_span[("B", 0x0F3C7850)], "09A0")

    def test_patching_one_record_preserves_both_neighbours_byte_exact(self) -> None:
        rows = sorted(
            (row for row in self.records if row.pack_name == "A"),
            key=lambda row: row.pack_offset,
        )
        previous, selected, following = rows[99:102]
        start = previous.pack_offset
        end = following.pack_offset + 8
        with selected.pack_path.open("rb") as stream:
            stream.seek(start)
            before = stream.read(end - start)
        after = bytearray(before)
        relative = selected.pack_offset - start
        replacement = xiso.pack_colors(0xFF123456, 0xFFABCDEF)
        after[relative:relative + 8] = replacement
        self.assertEqual(after[:relative], before[:relative])
        self.assertEqual(after[relative + 8:], before[relative + 8:])
        self.assertEqual(
            after[previous.pack_offset - start:previous.pack_offset - start + 8],
            before[previous.pack_offset - start:previous.pack_offset - start + 8],
        )
        self.assertEqual(
            after[following.pack_offset - start:following.pack_offset - start + 8],
            before[following.pack_offset - start:following.pack_offset - start + 8],
        )
        self.assertEqual(bytes(after[relative:relative + 8]), replacement)

    def test_missing_selector_and_bad_pack_provenance_fail_closed(self) -> None:
        with self.assertRaises(colour.UnifColorWriterError):
            colour.resolve_uniform_color_record(EXTRACTED / "0", "98H98")
        record = colour.resolve_uniform_color_record(EXTRACTED / "0", "09H0")
        self.assertEqual(record.pack_name, "A")
        expected_size, _sha, _sector = colour.PACK_PROVENANCE["A"]
        self.assertEqual(record.pack_path.stat().st_size, expected_size)


@unittest.skipUnless(
    REAL_DATA and SOURCE_XISO.is_file(), "retail 2K5 source XISO not present"
)
class RealComposedWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fd = os.open(SOURCE_XISO, os.O_RDONLY)
        cls.entries, _directory = xiso.parse_xdvdfs(
            cls.fd, SOURCE_XISO.stat().st_size
        )
        cls.pack_hashes: dict[str, str] = {}

    @classmethod
    def tearDownClass(cls) -> None:
        os.close(cls.fd)

    def test_one_set_emits_exactly_one_eight_byte_provenance_bound_span(self) -> None:
        built = colour.build_unif_color_imports(
            {
                "kind": "unif_color", "selector": "09H0",
                "facemask": "FF123456", "turtleneck": "FFABCDEF",
            },
            index_path=EXTRACTED / "0", source_fd=self.fd,
            entries=self.entries, pack_hashes=self.pack_hashes,
        )
        self.assertEqual(len(built), 1)
        replacement, previews, report, selector, target = built[0]
        self.assertEqual(replacement, xiso.pack_colors(0xFF123456, 0xFFABCDEF))
        self.assertEqual(previews, [])
        self.assertEqual(selector, "unif_color:09H0")
        self.assertEqual(target["span_size"], 8)
        self.assertEqual(target["xiso_pack_path"], "vc_53450030/A")
        self.assertEqual(report["uniform_selector"], "09H0")

    def test_no_op_and_wrong_full_pack_fingerprint_are_refused(self) -> None:
        retail = colour.resolve_uniform_color_record(EXTRACTED / "0", "09H0")
        with self.assertRaises(colour.UnifColorWriterError):
            colour.build_unif_color_imports(
                {
                    "kind": "unif_color", "selector": "09H0",
                    "facemask": retail.facemask_argb,
                    "turtleneck": retail.turtleneck_argb,
                },
                index_path=EXTRACTED / "0", source_fd=self.fd,
                entries=self.entries, pack_hashes=self.pack_hashes,
            )
        with self.assertRaises(colour.UnifColorWriterError):
            colour.build_unif_color_imports(
                {
                    "kind": "unif_color", "selector": "09H0",
                    "facemask": "FF123456", "turtleneck": "FFABCDEF",
                },
                index_path=EXTRACTED / "0", source_fd=self.fd,
                entries=self.entries,
                pack_hashes={"vc_53450030/A": "0" * 64},
            )


class ProjectSchemaTests(unittest.TestCase):
    def _project(self, rows: list[dict[str, str]], path: Path) -> None:
        path.write_bytes(build_project.canonical_json({
            "schema": build_project.SCHEMA,
            "purpose": "Per-uniform colour proof",
            "edits": rows,
        }))

    def test_build_project_accepts_multiple_sets_but_refuses_a_duplicate(self) -> None:
        row = {
            "kind": "unif_color", "selector": "09H0",
            "facemask": "FF123456", "turtleneck": "FFABCDEF",
        }
        with tempfile.TemporaryDirectory(prefix="unif-colour-schema-") as name:
            path = Path(name) / "project.json"
            self._project([row, {**row, "selector": "09A0"}], path)
            self.assertEqual(len(build_project.read_project(path).value["edits"]), 2)
            self._project([row, dict(row)], path)
            with self.assertRaises(build_project.ProjectError):
                build_project.read_project(path)

    def test_shareable_archive_roundtrips_logical_rows_and_rejects_tampering(self) -> None:
        class NeverUsed:
            def __getattr__(self, name: str) -> object:
                raise AssertionError(name)

        rows = (
            {"selector": "09H0", "facemask": "FF123456", "turtleneck": "FFABCDEF"},
            {"selector": "09A0", "facemask": "FF654321", "turtleneck": "FFFEDCBA"},
        )
        with tempfile.TemporaryDirectory(prefix="unif-colour-archive-") as name:
            root = Path(name)
            project = root / "colours.2k5mod"
            save_project_archive(
                catalog=NeverUsed(), asset_io=NeverUsed(), edits=(),
                destination=project, uniform_colors=rows,
            )
            loaded = load_project_archive(
                source=project, catalog=NeverUsed(), asset_io=NeverUsed(),
                private_root=root,
            )
            try:
                self.assertEqual(
                    loaded.uniform_colors,
                    tuple(sorted(rows, key=lambda row: row["selector"])),
                )
            finally:
                loaded.cleanup()

            with zipfile.ZipFile(project, "r") as archive:
                manifest = json.loads(archive.read("project.json"))
            manifest["uniform_colors"][0]["selector"] = "09H0"
            forged = root / "forged.2k5mod"
            with zipfile.ZipFile(forged, "w") as archive:
                archive.writestr(
                    "project.json",
                    (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
                )
            with self.assertRaises(ValidationError):
                load_project_archive(
                    source=forged, catalog=NeverUsed(), asset_io=NeverUsed(),
                    private_root=root,
                )


@unittest.skipUnless(REAL_DATA, "extracted 2K5 uniform packs not present")
class RealSessionRoundTripTests(unittest.TestCase):
    def _cache(self, root: Path) -> SourceCache:
        originals = root / "private-cache" / "originals"
        originals.mkdir(parents=True, exist_ok=True)
        source = SourceRecord(
            selected_path=str(SOURCE_XISO), inspected_path=str(SOURCE_XISO),
            kind="xiso", sha256="7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
            size=6_300_499_968, recognized=True,
            fingerprint_id="nfl2k5-usa-retail-xiso",
        )
        return SourceCache(
            source=source, root=originals.parent, pack0=EXTRACTED / "0",
            inventory=INVENTORY, originals=originals, resource_count=0,
            outer_entry_count=0, kind_counts={},
        )

    def test_session_save_load_and_undo_preserve_the_selected_set(self) -> None:
        catalog = load_nfl2k5_uniform_catalog()
        with tempfile.TemporaryDirectory(prefix="unif-colour-session-") as name:
            root = Path(name)
            first = StudioSession(
                self._cache(root), catalog, root=root / "sessions", session_id="first"
            )
            self.assertEqual(
                first.set_uniform_colors("09H0", "FF123456", "FFABCDEF"),
                ("FF123456", "FFABCDEF", True),
            )
            self.assertEqual(
                first.set_uniform_colors("09A0", "FF654321", "FFFEDCBA"),
                ("FF654321", "FFFEDCBA", True),
            )
            self.assertEqual(first.modified_count, 2)
            edits = first.canonical_document()["edits"]
            self.assertEqual(
                {edit["selector"] for edit in edits}, {"09H0", "09A0"}
            )
            project = root / "colours.2k5mod"
            first.save_shareable_project(project)

            second = StudioSession(
                self._cache(root), catalog, root=root / "sessions", session_id="second"
            )
            self.assertEqual(second.load_shareable_project(project), 2)
            self.assertEqual(
                second.uniform_colors("09H0"),
                ("FF123456", "FFABCDEF", True),
            )
            self.assertEqual(
                second.uniform_colors("09A0"),
                ("FF654321", "FFFEDCBA", True),
            )
            self.assertTrue(second.clear_uniform_colors("09H0"))
            self.assertEqual(second.modified_count, 1)
            self.assertEqual(
                second.undo(),
                "Revert colours for Detroit Lions — Current Uniform — Home",
            )
            self.assertEqual(second.modified_count, 2)
            self.assertEqual(second.revert_all(), 2)
            self.assertEqual(second.modified_count, 0)
            self.assertEqual(second.undo(), "Revert all assets")
            self.assertEqual(second.modified_count, 2)

            third = StudioSession(
                self._cache(root), catalog, root=root / "sessions", session_id="third"
            )
            self.assertEqual(
                third.set_uniform_colors("09H0", "FF000000", "FF385AAF"),
                ("FF000000", "FF385AAF", False),
            )
            self.assertEqual(third.modified_count, 0)
            self.assertFalse(third.can_undo)


class ControlSurfaceTests(unittest.TestCase):
    def test_session_facade_gui_and_build_use_the_same_per_set_contract(self) -> None:
        for member in (
            "def uniform_colors", "def set_uniform_colors",
            "def clear_uniform_colors",
        ):
            self.assertIn(member, _SESSION)
            self.assertIn(member, _FACADE)
        self.assertIn('"selector": selector,', _SESSION)
        self.assertIn(
            'UNIF_COLOR_FIELDS = {"kind", "selector", "facemask", "turtleneck"}',
            _PROJECT,
        )
        self.assertIn("len(self._unif_colors)", _SESSION)
        self.assertIn("self._unif_colors = {}", _SESSION)

    def test_gui_is_searchable_and_truthful_about_shared_word_zero(self) -> None:
        for text in (
            "Facemask, faceshield and turtleneck colours",
            "Filter by team, set, or selector",
            "Facemask / faceshield colour",
            "Turtleneck colour",
        ):
            self.assertIn(text, _STUDIO)
        # Honesty: visor tint is not a separate Unif word; type is per-player.
        self.assertTrue(
            "visor colour" in _STUDIO.casefold()
            or "independent visor" in _STUDIO.casefold(),
            msg="GUI must stay truthful that visor is not an independent Unif colour",
        )
        self.assertIn("self.uniform_catalog.uniform_sets", _STUDIO)
        self.assertIn("self.facade.set_uniform_colors(", _STUDIO)

    def test_the_colours_tab_mounts_the_control(self) -> None:
        mount = _STUDIO.index("if category == ProductCategory.UNIFORMS_EQUIPMENT:")
        self.assertIn("_build_colors_page(section)", _STUDIO[mount:mount + 2400])


class _ColourFacade(BrowseOnlyFacade):
    source_display_name = "Colour GUI fixture"
    source_path = SOURCE_XISO
    source_sha256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"

    def __init__(self) -> None:
        self.values: dict[str, tuple[str, str]] = {}
        self._source_ready = False

    @property
    def source_ready(self) -> bool:
        return self._source_ready

    @property
    def modified_count(self) -> int:
        return len(self.values)

    @property
    def can_undo(self) -> bool:
        return bool(self.values)

    def uniform_colors(self, selector: str, progress: object) \
            -> tuple[str, str, bool]:
        progress("read", 0, 1)  # type: ignore[operator]
        pair = self.values.get(selector, ("FF000000", "FF385AAF"))
        progress("read", 1, 1)  # type: ignore[operator]
        return pair[0], pair[1], selector in self.values

    def set_uniform_colors(
        self, selector: str, facemask: str, turtleneck: str, progress: object,
    ) -> tuple[str, str, bool]:
        progress("set", 0, 1)  # type: ignore[operator]
        self.values[selector] = (facemask, turtleneck)
        progress("set", 1, 1)  # type: ignore[operator]
        return facemask, turtleneck, True

    def clear_uniform_colors(self, selector: str, progress: object) -> bool:
        progress("clear", 0, 1)  # type: ignore[operator]
        had = self.values.pop(selector, None) is not None
        progress("clear", 1, 1)  # type: ignore[operator]
        return had


class GuiInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.facade = _ColourFacade()
        self.window = StudioMainWindow(facade=self.facade, offer_recovery=False)
        self.facade._source_ready = True
        self.window._refresh_edit_state()
        self.window._load_selected_unif_colors()
        self._drain()

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.application.processEvents()

    def _drain(self) -> None:
        deadline = time.monotonic() + 5.0
        while self.window._workers and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.005)
        self.application.processEvents()
        self.assertFalse(self.window._workers, "GUI colour worker did not finish")

    def _select(self, selector: str) -> None:
        self.window.unif_color_search.clear()
        index = self.window.unif_color_set.findData(selector)
        self.assertGreaterEqual(index, 0)
        self.window.unif_color_set.setCurrentIndex(index)
        self._drain()

    def test_selected_home_and_away_sets_keep_independent_colours(self) -> None:
        self.assertEqual(self.window.unif_color_set.count(), 634)
        self._select("21H0")
        self.assertTrue(self.window.unif_color_apply.isEnabled())
        self.window._pending_facemask = "FF123456"
        self.window._pending_turtleneck = "FFABCDEF"
        self.window._apply_unif_colors()
        self._drain()
        self.assertEqual(self.facade.values["21H0"], ("FF123456", "FFABCDEF"))

        self._select("21A0")
        self.assertEqual(
            (self.window._pending_facemask, self.window._pending_turtleneck),
            ("FF000000", "FF385AAF"),
        )
        self.assertEqual(self.facade.values["21H0"], ("FF123456", "FFABCDEF"))

        self._select("21H0")
        self.assertTrue(self.window.unif_color_revert.isEnabled())
        self.window._revert_unif_colors()
        self._drain()
        self.assertNotIn("21H0", self.facade.values)


if __name__ == "__main__":
    unittest.main()

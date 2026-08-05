from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from mod_editor.apf_studio.build import ApfBuildService, BuildError
from mod_editor.apf_studio.catalog import _status_for, build_capability_cards
from mod_editor.apf_studio.models import (
    DRAFT_LOGO_CATALOG_ID,
    DRAFT_LOGO_EDIT_ID,
    DRAFT_LOGO_INNER_INDEX,
    DRAFT_LOGO_OUTER_INDEX,
    ApfAsset,
    ApfCategory,
    ApfSource,
    ApfStatus,
    Modification,
)
from mod_editor.apf_studio.project import ProjectError, load_project, save_project
from mod_editor.apf_studio.session import ApfSession


def _source(root: Path) -> ApfSource:
    return ApfSource(
        selected_path=root,
        game_root=root,
        index_0a=root / "0A",
        source_sha256="d" * 64,
        source_size=0,
        xex_sha256="e" * 64,
        display_name="APF draft logo fixture",
    )


def _draft_asset() -> ApfAsset:
    return ApfAsset(
        asset_id=DRAFT_LOGO_CATALOG_ID,
        outer_index=DRAFT_LOGO_OUTER_INDEX,
        inner_index=DRAFT_LOGO_INNER_INDEX,
        name="draft_logo",
        type_name="TXTR",
        asset_class="texture",
        category=ApfCategory.LOGOS,
        status=ApfStatus.EDITABLE,
        decoded_size=16_384,
        outer_size=1,
        part_count=2,
    )


def _png(path: Path) -> tuple[bytes, str]:
    Image.new("RGBA", (128, 128), (12, 34, 56, 200)).save(path, format="PNG")
    data = path.read_bytes()
    return data, hashlib.sha256(data).hexdigest()


def _metadata() -> dict[str, object]:
    return {
        "width": 128,
        "height": 128,
        "outer_index": DRAFT_LOGO_OUTER_INDEX,
        "inner_index": DRAFT_LOGO_INNER_INDEX,
        "format": "BC3",
        "mip_levels": 1,
    }


class DraftLogoCatalogTests(unittest.TestCase):
    def test_exact_draft_logo_is_editable_without_unlocking_other_textures(self) -> None:
        self.assertIs(
            _status_for(
                DRAFT_LOGO_OUTER_INDEX,
                DRAFT_LOGO_INNER_INDEX,
                "TXTR",
                "draft_logo",
            ),
            ApfStatus.EDITABLE,
        )
        self.assertIs(
            _status_for(
                DRAFT_LOGO_OUTER_INDEX,
                DRAFT_LOGO_INNER_INDEX + 1,
                "TXTR",
                "draft_logo",
            ),
            ApfStatus.EXPORT_ONLY,
        )
        self.assertEqual(_draft_asset().export_label, "Editable PNG")

    def test_selector_capabilities_render_under_team_identity(self) -> None:
        cards = build_capability_cards()
        selector_cards = tuple(
            card for card in cards if card.capability_id.startswith("apf2k8.colors.")
        )
        self.assertEqual(len(selector_cards), 4)
        appearance_card = next(
            card
            for card in selector_cards
            if card.capability_id
            == "apf2k8.colors.uniform_selector_appearance_custom_team"
        )
        self.assertIs(appearance_card.category, ApfCategory.UNIFORMS)
        self.assertTrue(
            all(
                card.category is ApfCategory.TEAM_IDENTITY
                for card in selector_cards
                if card is not appearance_card
            )
        )

    def test_ui_does_not_hide_capability_cards_and_names_raw_exports(self) -> None:
        from mod_editor.apf_studio import gui

        source = inspect.getsource(gui.CapabilityPanel.set_cards)
        self.assertNotIn("cards[:6]", source)
        self.assertEqual(gui._asset_status_text(_draft_asset()), "✓ Editable PNG")
        raw = ApfAsset(
            asset_id="apf:outer:1:inner:2",
            outer_index=1,
            inner_index=2,
            name="fixture_scene",
            type_name="SCNE",
            asset_class="scene",
            category=ApfCategory.STADIUMS,
            status=ApfStatus.EXPORT_ONLY,
            decoded_size=10,
            outer_size=20,
            part_count=2,
        )
        self.assertEqual(
            gui._asset_status_text(raw), "↓ Raw parts ZIP only"
        )
        self.assertIsNone(gui.QApplication.instance())


class DraftLogoSessionAndProjectTests(unittest.TestCase):
    def test_replace_revert_and_project_roundtrip_are_typed_and_retail_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supplied = root / "draft.png"
            data, digest = _png(supplied)
            catalog = SimpleNamespace(
                get=lambda asset_id: _draft_asset()
                if asset_id == DRAFT_LOGO_CATALOG_ID
                else None
            )
            session = ApfSession(
                _source(root), catalog, cache_root=root / "private-cache"
            )
            try:
                with patch.object(
                    session.asset_io,
                    "preview_texture",
                    return_value=root / "private-original.png",
                ) as preview:
                    modification = session.replace_draft_logo(supplied)
                preview.assert_called_once()
                self.assertEqual(modification.asset_id, DRAFT_LOGO_EDIT_ID)
                self.assertEqual(modification.kind, "draft_logo")
                self.assertEqual(modification.replacement_sha256, digest)
                self.assertEqual(modification.metadata, _metadata())
                self.assertEqual(modification.replacement_path.read_bytes(), data)

                project = session.save_project(root / "draft.apf2k8mod")
                manifest, loaded, _annotations = load_project(
                    project,
                    expected_source_sha256="d" * 64,
                    destination_dir=root / "loaded",
                )
                self.assertEqual(manifest["replacement_count"], 1)
                self.assertFalse(
                    manifest["distribution"]["contains_original_game_bytes"]
                )
                self.assertEqual(loaded[0].asset_id, DRAFT_LOGO_EDIT_ID)
                self.assertEqual(loaded[0].metadata, _metadata())
                self.assertEqual(loaded[0].replacement_path.read_bytes(), data)

                imported_session = ApfSession(
                    _source(root), catalog, cache_root=root / "import-cache"
                )
                try:
                    with patch.object(
                        imported_session.asset_io,
                        "preview_texture",
                        return_value=root / "private-import-original.png",
                    ) as imported_preview:
                        self.assertEqual(imported_session.load_project(project), 1)
                    imported_preview.assert_called_once()
                    imported = imported_session.modification(DRAFT_LOGO_EDIT_ID)
                    self.assertIsNotNone(imported)
                    assert imported is not None
                    self.assertEqual(imported.replacement_sha256, digest)
                    self.assertEqual(imported.metadata, _metadata())
                finally:
                    imported_session.close()

                self.assertTrue(session.revert(DRAFT_LOGO_EDIT_ID))
                self.assertNotIn(DRAFT_LOGO_EDIT_ID, session.modified_asset_ids)
            finally:
                session.close()

    def test_project_rejects_changed_draft_logo_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "draft.png"
            _data, digest = _png(png)
            modification = Modification(
                asset_id=DRAFT_LOGO_EDIT_ID,
                kind="draft_logo",
                replacement_path=png,
                replacement_sha256=digest,
                metadata={**_metadata(), "inner_index": 118},
            )
            with self.assertRaisesRegex(ProjectError, "target metadata changed"):
                save_project(
                    root / "bad.apf2k8mod",
                    source_sha256="d" * 64,
                    modifications=(modification,),
                )


class DraftLogoBuildDispatchTests(unittest.TestCase):
    def test_compile_dispatches_only_the_pinned_writer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "draft.png"
            _data, digest = _png(png)
            modification = Modification(
                asset_id=DRAFT_LOGO_EDIT_ID,
                kind="draft_logo",
                replacement_path=png,
                replacement_sha256=digest,
                metadata=_metadata(),
            )
            writer_result = SimpleNamespace(
                entry_bytes=b"rebuilt fixed allocation",
                manifest={
                    "schema": "apf_texture_patch/v1",
                    "source": {
                        "outer_entry_index": DRAFT_LOGO_OUTER_INDEX,
                        "inner_file_index": DRAFT_LOGO_INNER_INDEX,
                    },
                    "target": {"name": "draft_logo", "type": "TXTR"},
                },
            )
            service = ApfBuildService(_source(root))
            with patch(
                "mod_editor.apf_studio.build.apf_texture_patch.build_patch",
                return_value=writer_result,
            ) as writer:
                outer, entry, schema = service._compile(modification)
            writer.assert_called_once_with(
                root / "0A",
                png,
                DRAFT_LOGO_OUTER_INDEX,
                DRAFT_LOGO_INNER_INDEX,
            )
            self.assertEqual((outer, entry, schema), (810, writer_result.entry_bytes, "apf_texture_patch/v1"))

    def test_compile_refuses_untyped_or_moved_draft_logo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "draft.png"
            _data, digest = _png(png)
            moved = Modification(
                asset_id=DRAFT_LOGO_EDIT_ID,
                kind="draft_logo",
                replacement_path=png,
                replacement_sha256=digest,
                metadata={**_metadata(), "outer_index": 811},
            )
            with self.assertRaisesRegex(BuildError, "target metadata changed"):
                ApfBuildService(_source(root))._compile(moved)


if __name__ == "__main__":
    unittest.main()

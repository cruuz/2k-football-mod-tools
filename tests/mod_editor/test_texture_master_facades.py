"""Editor facades bind authoring masters to the exact staged game PNG."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.helmet_crest_design import HELMET_CREST_DESIGN_EDIT_ID
from mod_editor.core.texture_master import AuthoringTransform
from mod_editor.studio.facade import Nfl2k5StudioFacade


class TextureMasterFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transform = AuthoringTransform(
            center_x=256.0,
            center_y=256.0,
            width=480.0,
            height=208.0,
            rotation_degrees=-7.5,
        )
        self.editor_transform = {
            "operation": "test-placement",
            "width": 480.0,
            "height": 208.0,
        }

    def test_apf_uses_the_current_staged_semantic_mask(self) -> None:
        staged_native = Path("/private/session/apf-staged-native.png")
        modification = SimpleNamespace(replacement_path=staged_native)
        session = SimpleNamespace(
            modification=lambda asset_id: (
                modification if asset_id == HELMET_CREST_DESIGN_EDIT_ID else None
            )
        )
        facade = object.__new__(ApfStudioFacade)
        facade._session_lock = threading.RLock()
        facade.session = session
        destination = Path("/exports/helmet.2ktexmaster")
        source = Path("/private/session/original.source")
        baseline = Path("/private/session/apf-native-before-edit.png")
        digest = "a" * 64

        with patch(
            "mod_editor.apf_studio.facade.save_texture_master_bundle",
            return_value=destination,
        ) as save:
            result = facade.save_helmet_crest_authoring_master(
                source_image=source,
                source_sha256=digest,
                destination=destination,
                transform=self.transform,
                editor_transform=self.editor_transform,
                high_resolution_scale=4,
                native_baseline_png=baseline,
            )

        self.assertEqual(result, destination)
        save.assert_called_once_with(
            source_image=source,
            destination=destination,
            asset_id=HELMET_CREST_DESIGN_EDIT_ID,
            editor_target="apf2k8_xbox360-helmet-crest",
            native_width=512,
            native_height=512,
            transform=self.transform,
            high_resolution_scale=4,
            compiled_native_png=staged_native,
            compiled_native_baseline_png=baseline,
            expected_source_sha256=digest,
            editor_transform=self.editor_transform,
        )

    def test_2k5_uses_the_current_session_png_for_the_selected_asset(self) -> None:
        staged_native = Path("/private/session/2k5-staged-native.png")
        session = SimpleNamespace(current_path=lambda _asset: staged_native)
        facade = object.__new__(Nfl2k5StudioFacade)
        facade._lock = threading.RLock()
        facade._session = session
        asset = SimpleNamespace(
            asset_id="nfl2k5.portrait.0000",
            label="Player portrait 0000",
            width=128,
            height=128,
        )
        destination = Path("/exports/portrait.2ktexmaster")
        source = Path("/private/session/original.source")
        baseline = Path("/private/session/2k5-native-before-edit.png")
        digest = "b" * 64

        with patch(
            "mod_editor.studio.facade.save_texture_master_bundle",
            return_value=destination,
        ) as save:
            result = facade.save_texture_authoring_master(
                asset,
                source_image=source,
                source_sha256=digest,
                destination=destination,
                transform=self.transform,
                editor_transform=self.editor_transform,
                high_resolution_scale=2,
                native_baseline_png=baseline,
            )

        self.assertEqual(result, destination)
        save.assert_called_once_with(
            source_image=source,
            destination=destination,
            asset_id=asset.asset_id,
            editor_target="nfl2k5_xbox",
            native_width=asset.width,
            native_height=asset.height,
            transform=self.transform,
            high_resolution_scale=2,
            compiled_native_png=staged_native,
            compiled_native_baseline_png=baseline,
            expected_source_sha256=digest,
            editor_transform=self.editor_transform,
        )


if __name__ == "__main__":
    unittest.main()

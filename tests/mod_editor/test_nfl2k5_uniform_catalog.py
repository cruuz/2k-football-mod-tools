"""Focused tests for the metadata-only NFL 2K5 uniform catalog."""

from __future__ import annotations

from pathlib import Path
import unittest

from mod_editor.core.nfl2k5_uniform_catalog import (
    ASSETS_PER_SET,
    EXPECTED_SET_COUNT,
    UniformCatalogError,
    load_nfl2k5_uniform_catalog,
)


class Nfl2k5UniformCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_uniform_catalog()

    def test_all_sets_and_39_component_surfaces_are_unique(self) -> None:
        self.assertEqual(len(self.catalog.uniform_sets), EXPECTED_SET_COUNT)
        self.assertEqual(
            len(self.catalog.assets), EXPECTED_SET_COUNT * ASSETS_PER_SET
        )
        self.assertEqual(
            len({uniform_set.selector for uniform_set in self.catalog.uniform_sets}),
            EXPECTED_SET_COUNT,
        )
        self.assertEqual(
            len({asset.asset_id for asset in self.catalog.assets}),
            EXPECTED_SET_COUNT * ASSETS_PER_SET,
        )
        for uniform_set in self.catalog.uniform_sets:
            self.assertEqual(len(self.catalog.assets_for_set(uniform_set.selector)), 39)

    def test_giants_home_metadata_groups_dimensions_and_stable_ids(self) -> None:
        uniform_set = self.catalog.uniform_set_for("18", "home", 0)
        self.assertEqual(uniform_set.selector, "18H0")
        self.assertEqual(uniform_set.team_names, ("New York Giants",))
        self.assertEqual(uniform_set.team_abbreviations, ("NYG",))
        self.assertEqual(uniform_set.style_label, "Current Uniform")
        self.assertEqual(uniform_set.uniform_package, "18H0.IFF")
        assets = self.catalog.assets_for_set("18h0")
        self.assertEqual(
            {asset.group: sum(item.group == asset.group for item in assets)
             for asset in assets},
            {
                "Live Uniform": 3,
                "Live Helmets": 2,
                "Jersey Digits": 10,
                "Helmet Digits": 10,
                "Arm / Shoulder Digits": 10,
                "Nameplate": 1,
                "Team Select Cards": 3,
            },
        )
        torso = self.catalog.get_asset("nfl2k5.uniform.18h0.torso")
        self.assertEqual(torso.dimensions, (512, 256))
        self.assertEqual(torso.set_selector, "18H0")
        self.assertEqual((torso.side_code, torso.side_name), ("H", "HOME"))
        nameplate = self.catalog.get_asset("nfl2k5.uniform.18h0.nameplate")
        # 1024x32: a horizontal character strip. The transposed value was
        # the descriptor bug that made the Nameplate Atlas export as
        # confetti; decoded correctly it reads "` - A B C D E F G H ...".
        self.assertEqual(nameplate.dimensions, (1024, 32))
        small_card = self.catalog.get_asset(
            "nfl2k5.uniform.18h0.team-select.helm.128"
        )
        self.assertEqual(small_card.dimensions, (128, 128))
        self.assertEqual(uniform_set.thumbnail_asset_id,
                         "nfl2k5.uniform.18h0.team-select.unif.256")

    def test_each_component_emits_the_exact_unified_provider_edit_shape(self) -> None:
        png = Path("replacements/giants.png")
        torso = self.catalog.get_asset("nfl2k5.uniform.18a0.torso")
        self.assertEqual(torso.provider_edit(png), {
            "asset_code": "18",
            "clean_png": "replacements/giants.png",
            "kind": "torso",
            "mud_mode": "darken_60",
            "mud_png": None,
            "side": "A",
            "variant": 0,
        })
        helmet = self.catalog.get_asset("nfl2k5.uniform.18a0.helmet.helmet02")
        self.assertEqual(helmet.provider_edit(png), {
            "asset_code": "18",
            "family": "helmet02",
            "kind": "live_helmet",
            "png": "replacements/giants.png",
            "side": "A",
            "variant": 0,
        })
        digit = self.catalog.get_asset("nfl2k5.uniform.18a0.digit.arm.7")
        self.assertEqual(digit.provider_edit(png), {
            "asset_code": "18",
            "digit": 7,
            "family": "arm",
            "kind": "live_number_nameplate",
            "png": "replacements/giants.png",
            "side": "A",
            "variant": 0,
        })
        nameplate = self.catalog.get_asset("nfl2k5.uniform.18a0.nameplate")
        self.assertIsNone(nameplate.provider_edit(png)["digit"])
        self.assertEqual(nameplate.provider_edit(png)["family"], "nameplate")
        card = self.catalog.get_asset(
            "nfl2k5.uniform.18a0.team-select.helm.256"
        )
        self.assertEqual(card.provider_edit(png), {
            "asset_code": "18",
            "family": "helm",
            "kind": "team_select",
            "png": "replacements/giants.png",
            "resolution": 256,
            "side": "away",
            "style": 0,
        })

    def test_every_generated_edit_has_only_a_named_selector_and_png_path(self) -> None:
        expected_keys = {
            "torso": {"asset_code", "clean_png", "kind", "mud_mode", "mud_png",
                      "side", "variant"},
            "sleeve": {"asset_code", "clean_png", "kind", "mud_mode", "mud_png",
                       "side", "variant"},
            "pants": {"asset_code", "clean_png", "kind", "mud_mode", "mud_png",
                      "side", "variant"},
            "live_helmet": {"asset_code", "family", "kind", "png", "side", "variant"},
            "live_number_nameplate": {
                "asset_code", "digit", "family", "kind", "png", "side", "variant",
            },
            "team_select": {
                "asset_code", "family", "kind", "png", "resolution", "side", "style",
            },
        }
        for asset in self.catalog.assets:
            edit = asset.provider_edit("replacement.png")
            self.assertEqual(set(edit), expected_keys[asset.kind])
            self.assertNotIn("offset", str(edit).lower())

    def test_unknown_ids_selectors_and_empty_paths_are_human_readable_errors(self) -> None:
        with self.assertRaisesRegex(UniformCatalogError, "Unknown uniform asset ID"):
            self.catalog.get_asset("nfl2k5.uniform.missing")
        with self.assertRaisesRegex(UniformCatalogError, "Unknown uniform set selector"):
            self.catalog.assets_for_set("18H99")
        with self.assertRaisesRegex(UniformCatalogError, "cannot be empty"):
            self.catalog.get_asset("nfl2k5.uniform.18h0.torso").provider_edit("")


if __name__ == "__main__":
    unittest.main()

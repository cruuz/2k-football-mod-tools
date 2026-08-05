"""Regression gates for APF's distinct crest, frontend-cache, and wordmark owners."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "reports" / "assets" / "apf_uniform_inventory.json"
REGISTRY = ROOT / "mod_editor" / "capabilities" / "registry.v1.json"


class ApfLogoSurfaceOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.capabilities = {row["id"]: row for row in registry["capabilities"]}

    def test_all_three_logo_domains_remain_distinct(self) -> None:
        families = {
            row["family"]: row for row in self.inventory["family_specs"]
        }
        self.assertEqual(families["logo"]["catalog_count"], 118)
        self.assertEqual(families["logo"]["selector_slot"], 5)
        self.assertEqual(
            families["logo"]["expected_inner_signature"],
            [
                {"name": "logo_l0", "type": "TXTR"},
                {"name": "logo_l1", "type": "TXTR"},
            ],
        )
        self.assertEqual(families["textlogo"]["catalog_count"], 206)
        self.assertEqual(families["textlogo"]["selector_slot"], 6)
        self.assertEqual(
            families["textlogo"]["expected_inner_signature"],
            [{"name": "textlogo_color", "type": "TXTR"}],
        )
        cache = self.inventory["logo_cache"]
        self.assertEqual(cache["outer_table_index"], 171)
        self.assertEqual(cache["file_count"], 236)
        self.assertEqual(cache["internal_cache_name"], "uniform_logocache.cdf")

    def test_americans_crest_cache_and_wordmark_slots_are_exact(self) -> None:
        americans = self.inventory["team_selector_graph"]["teams"][0]
        self.assertEqual(
            (americans["team_index"], americans["display_name"], americans["abbreviation"]),
            (0, "Americans", "PHI"),
        )
        for bank in americans["banks"]:
            selected = {
                family: selector["asset_index_byte_0"]
                for selector in bank["selectors"]
                for family in selector["families"]
                if family in {"logo", "textlogo"}
            }
            self.assertEqual(selected, {"logo": 30, "textlogo": 8})

        packages = {
            (row["family"], row["asset_index"]): row
            for row in self.inventory["packages"]
        }
        crest = packages[("logo", 30)]
        self.assertEqual(
            (crest["outer_name"], crest["outer_table_index"]),
            ("uniform_logo_30.iff", 1133),
        )
        self.assertEqual(
            [(row["name"], row["inner_index"]) for row in crest["files"]],
            [("logo_l1", 0), ("logo_l0", 1)],
        )
        wordmark = packages[("textlogo", 8)]
        self.assertEqual(
            (wordmark["outer_name"], wordmark["outer_table_index"]),
            ("uniform_textlogo_08.iff", 906),
        )
        descriptor = wordmark["files"][0]["txtr"]
        self.assertEqual(
            (
                wordmark["files"][0]["name"],
                descriptor["width"],
                descriptor["height"],
                descriptor["format_name"],
                descriptor["vc_base_data_length"],
                descriptor["vc_mip_data_length"],
            ),
            ("textlogo_color", 512, 128, "DXT1", 32768, 32768),
        )

        cache_rows = {
            row["cache_name"]: row
            for row in self.inventory["logo_cache"]["entries"]
            if row["catalog_index"] == 30
        }
        self.assertEqual(set(cache_rows), {"30_logo_l0", "30_logo_l1"})
        self.assertEqual(
            (
                cache_rows["30_logo_l0"]["cache_entry_index"],
                cache_rows["30_logo_l0"]["aggregate_slot"],
                cache_rows["30_logo_l1"]["cache_entry_index"],
                cache_rows["30_logo_l1"]["aggregate_slot"],
            ),
            (171, 96, 178, 97),
        )

    def test_product_contract_routes_crests_wordmarks_and_menu_cards_separately(
        self,
    ) -> None:
        cache = self.capabilities["apf2k8.logos_cards.team_logo_cache"]
        self.assertIn("outer 171", cache["source_container"]["resource"])
        self.assertIn("outer 213", cache["source_container"]["resource"])
        self.assertIn("one Team Logo action couples", cache["selectors"]["notes"])

        catalog = self.capabilities["apf2k8.logos_cards.uniform_catalog"]
        self.assertEqual(catalog["classification"], "extract-only")
        joined = " ".join(catalog["input_constraints"]).casefold()
        self.assertIn("use team logo for uniform_logo indices 0..117", joined)
        self.assertIn("wordmarks for uniform_textlogo indices 0..205", joined)
        self.assertIn("neither authorizes menu-card import", joined)
        self.assertIn("separate owners", catalog["selectors"]["notes"].casefold())

    def test_registry_names_static_team_select_mapping_without_runtime_overclaim(self) -> None:
        package = self.capabilities["apf2k8.logos_cards.team_logo"]
        cache = self.capabilities["apf2k8.logos_cards.team_logo_cache"]
        wordmark = self.capabilities["apf2k8.logos_cards.textlogo_wordmarks"]
        claims = " ".join(
            (
                package["summary"],
                package["gui"]["reason"],
                package["runtime"]["scope"],
                cache["summary"],
                cache["gui"]["reason"],
                cache["runtime"]["scope"],
                wordmark["summary"],
                wordmark["gui"]["reason"],
            )
        ).casefold()
        for marker in (
            "selector slot 5",
            "selector slot 6",
            "frontend",
            "team select",
            "uniform_logo",
            "uniform_textlogo",
            "changed-logo runtime consumption",
            "unproved",
        ):
            self.assertIn(marker, claims)
        self.assertNotIn("team select runtime-proved", claims)


if __name__ == "__main__":
    unittest.main()

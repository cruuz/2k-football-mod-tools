from __future__ import annotations

import unittest

from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
from mod_editor.core.product_catalog import (
    PRODUCT_CATEGORY_ORDER,
    ProductCategory,
    ProductStatus,
    build_nfl2k5_product_catalog,
)
from mod_editor.gui.crib_panel_qt import CribPanelHost
from mod_editor.gui.gameplay_panel_qt import GameplayPanelHost
from mod_editor.gui.menus_panel_qt import MenusPanelHost
from mod_editor.gui.playbooks_panel_qt import PlaybooksPanelHost
from mod_editor.gui.studio_qt import (
    BrowseOnlyFacade,
    UniformFilter,
    capability_findings,
    category_display_title,
    filter_uniform_sets,
    sidebar_category_titles,
    specialized_panel_for_category,
    uniform_search_text,
)
from mod_editor.gui.text_rosters_panel import TextRosterPanelHost


class StudioQtViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.uniforms = load_nfl2k5_uniform_catalog()
        cls.product = build_nfl2k5_product_catalog(
            CapabilityRegistryLoader().load(
                allow_sample_fallback=False, check_files=False
            )
        )

    def test_sidebar_includes_scope_expansion_in_exact_category_order(self) -> None:
        self.assertEqual(
            sidebar_category_titles(self.product),
            tuple(
                category_display_title(self.product, category)
                for category in PRODUCT_CATEGORY_ORDER
            ),
        )
        self.assertEqual(len(sidebar_category_titles(self.product)), 11)
        self.assertEqual(
            category_display_title(self.product, ProductCategory.TEAM_IDENTITY),
            "Text & Team Identity",
        )

    def test_specialized_pages_are_bound_to_their_product_categories(self) -> None:
        self.assertEqual(
            specialized_panel_for_category(ProductCategory.ROSTERS_PLAYERS),
            "rosters_players",
        )
        self.assertEqual(
            specialized_panel_for_category(ProductCategory.TEAM_IDENTITY),
            "text_rosters",
        )
        self.assertEqual(
            specialized_panel_for_category(ProductCategory.CRIB), "crib"
        )
        self.assertEqual(
            specialized_panel_for_category(ProductCategory.AUDIO), "audio"
        )
        self.assertEqual(
            specialized_panel_for_category(ProductCategory.PLAYBOOKS_PLAYS),
            "playbooks",
        )
        self.assertEqual(
            specialized_panel_for_category(ProductCategory.MENUS_UI), "menus"
        )
        self.assertEqual(
            specialized_panel_for_category(ProductCategory.SLIDERS_GAMEPLAY),
            "gameplay",
        )
        self.assertIsNone(
            specialized_panel_for_category(ProductCategory.UNIFORMS_EQUIPMENT)
        )

    def test_pre_source_fallback_satisfies_embedded_panel_contracts(self) -> None:
        fallback = BrowseOnlyFacade()
        self.assertIsInstance(fallback, TextRosterPanelHost)
        self.assertIsInstance(fallback, CribPanelHost)
        self.assertIsInstance(fallback, PlaybooksPanelHost)
        self.assertIsInstance(fallback, GameplayPanelHost)
        self.assertIsInstance(fallback, MenusPanelHost)
        self.assertEqual(fallback.list_crib_assets(), ())

    def test_empty_filter_keeps_every_metadata_set(self) -> None:
        rows = filter_uniform_sets(self.uniforms.uniform_sets, UniformFilter())
        self.assertEqual(len(rows), 634)

    def test_side_filter_splits_the_catalog_evenly(self) -> None:
        home = filter_uniform_sets(
            self.uniforms.uniform_sets, UniformFilter(side="home")
        )
        away = filter_uniform_sets(
            self.uniforms.uniform_sets, UniformFilter(side="away")
        )
        self.assertEqual(len(home), 317)
        self.assertEqual(len(away), 317)
        self.assertTrue(all(item.side_code == "H" for item in home))
        self.assertTrue(all(item.side_code == "A" for item in away))

    def test_search_matches_all_words_across_team_metadata(self) -> None:
        rows = filter_uniform_sets(
            self.uniforms.uniform_sets,
            UniformFilter(query="Giants New York away"),
        )
        self.assertTrue(rows)
        self.assertTrue(all("new york giants" in uniform_search_text(row) for row in rows))
        self.assertTrue(all(row.side_code == "A" for row in rows))

    def test_owner_and_side_filters_compose(self) -> None:
        owner = next(
            name
            for item in self.uniforms.uniform_sets
            for name in item.team_names
            if name == "New York Giants"
        )
        rows = filter_uniform_sets(
            self.uniforms.uniform_sets,
            UniformFilter(owner=owner, side="home"),
        )
        self.assertTrue(rows)
        self.assertTrue(all(owner in row.team_names for row in rows))
        self.assertTrue(all(row.side_code == "H" for row in rows))

    def test_unassigned_filter_does_not_hide_owned_sets_in_other_filters(self) -> None:
        rows = filter_uniform_sets(
            self.uniforms.uniform_sets,
            UniformFilter(owner="__unassigned__"),
        )
        self.assertTrue(rows)
        self.assertTrue(all(not row.team_names for row in rows))

    def test_every_coming_soon_card_can_surface_a_findings_note(self) -> None:
        coming_soon = [
            binding
            for binding in self.product.capabilities
            if binding.status == ProductStatus.COMING_SOON
        ]
        self.assertTrue(coming_soon)
        for binding in coming_soon:
            # Some reviewed registry rows intentionally have no porting list,
            # but this helper must remain deterministic and string-only.
            self.assertIsInstance(capability_findings(binding), tuple)
            self.assertTrue(
                all(isinstance(note, str) and note.strip()
                    for note in capability_findings(binding))
            )


if __name__ == "__main__":
    unittest.main()

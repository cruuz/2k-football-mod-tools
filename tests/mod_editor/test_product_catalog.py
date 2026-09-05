"""Focused tests for the registry-driven 2K5 Mod Studio navigation model."""

from __future__ import annotations

import unittest

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.product_catalog import (
    PRODUCT_CATEGORY_ORDER,
    FindingsContext,
    ProductCatalogError,
    ProductCategory,
    ProductStatus,
    build_nfl2k5_product_catalog,
    product_status,
)


class ProductCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = CapabilityRegistryLoader().load(
            allow_sample_fallback=False, check_files=False
        )

    def test_complete_sidebar_is_present_in_mandated_order(self) -> None:
        catalog = build_nfl2k5_product_catalog(self.registry)

        self.assertEqual(
            tuple(section.category for section in catalog.sections),
            PRODUCT_CATEGORY_ORDER,
        )
        self.assertEqual(
            tuple(section.title for section in catalog.sections),
            (
                "Uniforms & Equipment",
                "Rosters & Players",
                "Team Identity",
                "Field Art & Create-Team Art",
                "Stadiums",
                "Presentation",
                "Menus & UI",
                "The Crib",
                "Audio",
                "Gameplay",
                "Playbooks & Plays",
                "All Textures",
            ),
        )

    def test_every_nfl_capability_is_assigned_exactly_once(self) -> None:
        first = build_nfl2k5_product_catalog(self.registry)
        second = build_nfl2k5_product_catalog(self.registry)
        expected = {
            "nfl2k5.animations.inspect_export",
            "nfl2k5.audio.audo_wav",
            "nfl2k5.audio.ausb_fixed_range_wav",
            "nfl2k5.audio.fixed_audo_wav",
            "nfl2k5.audio.menu_back_wav",
            "nfl2k5.catching_drops.behavior",
            "nfl2k5.colors.unif_words",
            "nfl2k5.cpu_ai_draft.logic",
            "nfl2k5.crib.assets",
            "nfl2k5.cross_title_model_conversion.to_apf",
            "nfl2k5.franchise_restoration_cross_title.port",
            "nfl2k5.gameplay.kickoff_relocated",
            "nfl2k5.gameplay.xbe_space",
            "nfl2k5.gameplay_tuning_sliders.rating_view",
            "nfl2k5.logos.team_select_cards",
            "nfl2k5.menus.layouts",
            "nfl2k5.mode_state_routing.state_graph",
            "nfl2k5.models.guardian_cap_c_trial",
            "nfl2k5.models.scne_gltf",
            "nfl2k5.models.scne_same_count_position",
            "nfl2k5.models.scne_same_footprint_geometry",
            "nfl2k5.models.scne_upper_deck_source_subset",
            "nfl2k5.players.disc_roster",
            "nfl2k5.portraits_faces.live_textures",
            "nfl2k5.portraits_faces.roster_portraits",
            "nfl2k5.saves.dashboard",
            "nfl2k5.schedules_franchise.database",
            "nfl2k5.schedules_franchise.season_cap",
            "nfl2k5.scorebug_presentation.inventory",
            "nfl2k5.scorebug_presentation.score_buga_runtime",
            "nfl2k5.scorebug_presentation.shield_espn_runtime",
            "nfl2k5.screens.timing",
            "nfl2k5.scripts.director_playbook",
            "nfl2k5.stadiums.create_team_field_art",
            "nfl2k5.stadiums.geometry",
            "nfl2k5.textures.all_p8",
            "nfl2k5.uniforms.all_visual",
            "nfl2k5.uniforms.detroit_away_runtime",
        }
        first_ids = [binding.capability_id for binding in first.capabilities]
        second_ids = [binding.capability_id for binding in second.capabilities]

        self.assertEqual(len(first_ids), 38)
        self.assertEqual(len(first_ids), len(set(first_ids)))
        self.assertEqual(set(first_ids), expected)
        self.assertEqual(first_ids, second_ids)

    def test_classification_maps_to_product_language(self) -> None:
        self.assertEqual(
            product_status(Classification.RUNTIME_PROVED),
            ProductStatus.EDITABLE,
        )
        self.assertEqual(
            product_status(Classification.OFFLINE_WRITER_PROVED),
            ProductStatus.EDITABLE,
        )
        self.assertEqual(
            product_status(Classification.READ_ONLY_MAPPED),
            ProductStatus.PREVIEW,
        )
        self.assertEqual(
            product_status(Classification.EXTRACT_ONLY),
            ProductStatus.EXPORT_ONLY,
        )
        self.assertEqual(
            product_status(Classification.UNKNOWN),
            ProductStatus.COMING_SOON,
        )
        self.assertEqual(
            product_status(Classification.UNSAFE_DEFERRED),
            ProductStatus.COMING_SOON,
        )

    def test_category_and_global_counts_match_the_registry(self) -> None:
        catalog = build_nfl2k5_product_catalog(self.registry)
        expected = {
            ProductCategory.UNIFORMS_EQUIPMENT: (4, 3, 0, 0, 0, 1, 0),
            ProductCategory.ROSTERS_PLAYERS: (3, 3, 0, 0, 0, 0, 0),
            ProductCategory.TEAM_IDENTITY: (0, 0, 0, 0, 0, 0, 0),
            ProductCategory.FIELD_ART_CREATE_TEAM: (1, 1, 0, 0, 0, 0, 0),
            ProductCategory.STADIUMS: (8, 3, 1, 1, 0, 3, 0),
            ProductCategory.SCOREBUG_PRESENTATION: (3, 1, 0, 0, 0, 2, 0),
            ProductCategory.MENUS_UI: (2, 0, 2, 0, 0, 0, 0),
            ProductCategory.CRIB: (1, 1, 0, 0, 0, 0, 0),
            ProductCategory.AUDIO: (4, 3, 0, 1, 0, 0, 0),
            ProductCategory.SLIDERS_GAMEPLAY: (8, 2, 4, 0, 0, 0, 2),
            ProductCategory.PLAYBOOKS_PLAYS: (3, 3, 0, 0, 0, 0, 0),
            ProductCategory.TEXTURES: (1, 1, 0, 0, 0, 0, 0),
        }
        for category, values in expected.items():
            with self.subTest(category=category.value):
                counts = catalog.section(category).counts
                self.assertEqual(
                    (
                        counts.total,
                        counts.editable,
                        counts.preview,
                        counts.export_only,
                        counts.coming_soon,
                        counts.evidence,
                        counts.research,
                    ),
                    values,
                )
        self.assertEqual(
            (
                catalog.counts.total,
                catalog.counts.editable,
                catalog.counts.preview,
                catalog.counts.export_only,
                catalog.counts.coming_soon,
                catalog.counts.evidence,
                catalog.counts.research,
            ),
            (38, 21, 7, 2, 0, 6, 2),
        )

    def test_ambiguous_stadium_surface_and_team_identity_are_explicit(self) -> None:
        catalog = build_nfl2k5_product_catalog(self.registry)
        field_art = catalog.binding("nfl2k5.stadiums.create_team_field_art")
        geometry = catalog.binding("nfl2k5.stadiums.geometry")
        team_identity = catalog.section(ProductCategory.TEAM_IDENTITY)

        self.assertEqual(
            field_art.category, ProductCategory.FIELD_ART_CREATE_TEAM
        )
        self.assertEqual(geometry.category, ProductCategory.STADIUMS)
        self.assertEqual(team_identity.counts.total, 0)
        self.assertEqual(
            team_identity.related_capability_ids,
            ("nfl2k5.uniforms.all_visual",),
        )
        self.assertIn("team_identity", team_identity.findings_notes[0])

    def test_crib_capability_is_owned_only_by_the_crib(self) -> None:
        catalog = build_nfl2k5_product_catalog(self.registry)
        crib = catalog.binding("nfl2k5.crib.assets")
        roster_ids = {
            binding.capability_id
            for binding in catalog.section(
                ProductCategory.ROSTERS_PLAYERS
            ).capabilities
        }

        self.assertEqual(crib.category, ProductCategory.CRIB)
        self.assertEqual(crib.status, ProductStatus.EDITABLE)
        self.assertNotIn(crib.capability_id, roster_ids)

    def test_findings_hooks_add_normalized_deduplicated_notes_only(self) -> None:
        seen: list[FindingsContext] = []

        def first(context: FindingsContext):
            seen.append(context)
            if context.capability.capability_id == "nfl2k5.audio.audo_wav":
                return "  850   AUDO records mapped  "
            return None

        def second(context: FindingsContext):
            if context.capability.capability_id == "nfl2k5.audio.audo_wav":
                return ("850 AUDO records mapped", "Export stays local")
            return ()

        catalog = build_nfl2k5_product_catalog(
            self.registry, findings_note_hooks=(first, second)
        )
        binding = catalog.binding("nfl2k5.audio.audo_wav")

        self.assertEqual(len(seen), 32)
        self.assertEqual(
            binding.findings_notes,
            ("850 AUDO records mapped", "Export stays local"),
        )
        self.assertEqual(binding.status, ProductStatus.EXPORT_ONLY)

    def test_findings_hooks_reject_non_string_notes(self) -> None:
        def invalid(_context: FindingsContext):
            return ("valid", 7)

        with self.assertRaisesRegex(ProductCatalogError, "must return strings"):
            build_nfl2k5_product_catalog(
                self.registry,
                findings_note_hooks=(invalid,),
            )

    def test_streaming_audio_blocker_preserves_complete_research_boundary(self) -> None:
        required = (
            "Recover external music/commentary cue identities and directories, "
            "loop points, gain, pan, priority, and runtime routing before semantic "
            "presets or any whole-bank repacker."
        )
        stale = (
            "Recover external music/commentary bank codecs, cue directories, "
            "loop points, gain, pan, priority, and rebuild rules before any bank "
            "writer."
        )
        menu_back = self.registry.get("nfl2k5.audio.menu_back_wav")
        all_portme = tuple(
            note
            for capability in self.registry.capabilities
            for note in capability.raw["portme"]
        )

        self.assertIn(required, menu_back.raw["portme"])
        self.assertEqual(all_portme.count(required), 1)
        self.assertNotIn(stale, all_portme)


if __name__ == "__main__":
    unittest.main()

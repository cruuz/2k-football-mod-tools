"""Retail-free parity checks for APF capability cards and desktop actions."""

from __future__ import annotations

import unittest

from mod_editor.apf_studio.catalog import _status_for, build_capability_cards
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.models import (
    ASSET_ACTION_BINDINGS,
    CAPABILITY_ACTION_BINDINGS,
    DIGITAL_FONT_CATALOG_ID,
    DIGITAL_FONT_INNER_INDEX,
    DIGITAL_FONT_OUTER_INDEX,
    DRAFT_LOGO_CATALOG_ID,
    DRAFT_LOGO_INNER_INDEX,
    DRAFT_LOGO_OUTER_INDEX,
    ApfAsset,
    ApfCategory,
    ApfProductAction,
    ApfStatus,
    asset_action_binding,
    capability_action_binding,
)
from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId


class CapabilityActionParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = CapabilityRegistryLoader().load(
            allow_sample_fallback=False, check_files=False
        )
        cls.capabilities = {
            item.capability_id: item
            for item in cls.registry.for_game(GameId.APF2K8)
        }
        cls.cards = {
            item.capability_id: item for item in build_capability_cards()
        }

    def test_registry_cards_and_action_bindings_are_one_to_one(self) -> None:
        self.assertEqual(set(self.cards), set(self.capabilities))
        self.assertLessEqual(
            set(CAPABILITY_ACTION_BINDINGS), set(self.capabilities)
        )
        for capability_id, card in self.cards.items():
            binding = capability_action_binding(capability_id)
            with self.subTest(capability=capability_id):
                if card.status is ApfStatus.COMING_SOON:
                    continue
                self.assertIsNotNone(binding)
                assert binding is not None
                self.assertTrue(binding.handler_id)
                self.assertTrue(binding.actions)

    def test_every_editable_card_has_real_replace_and_revert_methods(self) -> None:
        editable_count = 0
        for capability_id, card in self.cards.items():
            if card.status is not ApfStatus.EDITABLE:
                continue
            editable_count += 1
            binding = capability_action_binding(capability_id)
            self.assertIsNotNone(binding)
            assert binding is not None
            with self.subTest(capability=capability_id):
                self.assertTrue(binding.has_complete_editor)
                self.assertIn(ApfProductAction.REPLACE, binding.actions)
                self.assertIn(ApfProductAction.REVERT, binding.actions)
                self.assertTrue(
                    hasattr(ApfStudioFacade, str(binding.replace_method))
                )
                self.assertTrue(
                    hasattr(ApfStudioFacade, str(binding.revert_method))
                )
                for method in binding.additional_replace_methods:
                    self.assertTrue(hasattr(ApfStudioFacade, method))
                capability = self.capabilities[capability_id]
                self.assertIn(
                    capability.classification,
                    {
                        Classification.RUNTIME_PROVED,
                        Classification.OFFLINE_WRITER_PROVED,
                    },
                )
                self.assertEqual(
                    capability.raw.get("backend", {}).get("operation"), "write"
                )
        self.assertGreater(editable_count, 0)

    def test_in_place_text_editor_is_editable_without_fake_file_input(self) -> None:
        capability_id = "apf2k8.menus.layouts"
        capability = self.capabilities[capability_id]
        self.assertEqual(capability.accepted_extensions, ())
        self.assertFalse(capability.can_queue_replacement)
        self.assertIs(self.cards[capability_id].status, ApfStatus.EDITABLE)
        self.assertTrue(
            CAPABILITY_ACTION_BINDINGS[capability_id].has_complete_editor
        )

    def test_roster_capability_names_all_bounded_editors_and_keeps_boundaries(self) -> None:
        capability_id = "apf2k8.players.roster"
        binding = CAPABILITY_ACTION_BINDINGS[capability_id]
        capability = self.capabilities[capability_id]
        card = self.cards[capability_id]
        self.assertIs(card.status, ApfStatus.EDITABLE)
        self.assertEqual(
            binding.handler_id,
            "roster.player_team_name_and_base_rating_editor",
        )
        self.assertEqual(
            binding.additional_replace_methods,
            ("replace_player_base_rating", "replace_player_position"),
        )
        self.assertIn("28 independent native base ratings", binding.product_note)
        self.assertIn("native 100", binding.product_note)
        self.assertIn("player first/last-name", binding.product_note)
        self.assertIn("Dan CODEX", binding.product_note)
        self.assertIn("zero-capacity names", binding.product_note)
        self.assertIn("paired semantic +0x34", binding.product_note)
        self.assertIn("desktop dropdown", binding.product_note)
        self.assertIn("spot check", binding.product_note)
        self.assertIn("exact native 0–99", capability.summary)
        self.assertIn("nonempty player first/last names", capability.summary)
        self.assertIn("disclose shared-allocation owners", capability.summary)
        self.assertIn("source native 100", capability.summary)
        self.assertIn("exact 0–16 player positions", capability.summary)
        self.assertIn("Dan CODEX", capability.raw["runtime"]["scope"])
        self.assertIn("abbreviations", capability.raw["runtime"]["scope"])
        self.assertIn(
            "no numeric rating readout",
            capability.raw["runtime"]["scope"],
        )
        findings = " ".join(card.findings)
        self.assertIn("+0x120..+0x126", findings)
        self.assertIn("Safe extension storage is unresolved", findings)
        self.assertIn("ordinary no-input boot did not enter the exact consumer", findings)
        self.assertIn("path_not_reached", findings)
        self.assertIn("membership", capability.raw["gui"]["reason"])
        self.assertIn("depth charts", capability.raw["gui"]["reason"])
        self.assertIn("+0x34", capability.raw["gui"]["reason"])
        self.assertIn("17-choice semantic dropdown", capability.raw["gui"]["reason"])
        self.assertIn("spot check remains pending", capability.raw["gui"]["reason"])

    def test_unbound_semantic_promises_are_downgraded(self) -> None:
        unbound = {
            "apf2k8.cross_title_model_conversion.nfl_to_apf",
            "apf2k8.logos_cards.uniform_catalog",
            "apf2k8.mode_state_routing.state_graph",
            "apf2k8.models.scne_gltf",
            "apf2k8.portraits_faces.hi_head",
            "apf2k8.schedules_franchise.retained",
        }
        for capability_id in unbound:
            with self.subTest(capability=capability_id):
                self.assertIsNone(capability_action_binding(capability_id))
                self.assertIs(
                    self.cards[capability_id].status, ApfStatus.COMING_SOON
                )
                self.assertIn(
                    "No dedicated Mod Studio semantic handler",
                    self.cards[capability_id].findings[0],
                )

    def test_draft_logo_registry_and_exact_asset_route_are_complete(self) -> None:
        capability_id = "apf2k8.logos_cards.draft_logo"
        capability = self.capabilities[capability_id]
        card = self.cards[capability_id]
        binding = asset_action_binding(
            DRAFT_LOGO_CATALOG_ID,
            DRAFT_LOGO_OUTER_INDEX,
            DRAFT_LOGO_INNER_INDEX,
            "draft_logo",
            "TXTR",
        )
        self.assertTrue(capability.can_queue_replacement)
        self.assertIs(card.category, ApfCategory.LOGOS)
        self.assertIs(card.status, ApfStatus.EDITABLE)
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.capability_id, capability_id)
        self.assertEqual(
            binding.handler_id,
            CAPABILITY_ACTION_BINDINGS[capability_id].handler_id,
        )
        self.assertIsNone(
            asset_action_binding(
                DRAFT_LOGO_CATALOG_ID,
                DRAFT_LOGO_OUTER_INDEX,
                DRAFT_LOGO_INNER_INDEX + 1,
                "draft_logo",
                "TXTR",
            )
        )

    def test_every_exact_asset_editor_resolves_to_its_capability_handler(self) -> None:
        for asset in ASSET_ACTION_BINDINGS:
            with self.subTest(asset=asset.asset_id):
                capability = CAPABILITY_ACTION_BINDINGS[asset.capability_id]
                self.assertEqual(asset.handler_id, capability.handler_id)
                self.assertEqual(asset.replace_method, capability.replace_method)
                for method in (
                    asset.preview_method,
                    asset.export_method,
                    asset.replace_method,
                ):
                    self.assertTrue(hasattr(ApfStudioFacade, method))

    def test_stadium_gltf_is_specialized_while_universal_scne_is_raw(self) -> None:
        stadium = capability_action_binding("apf2k8.stadiums.geometry")
        self.assertIsNotNone(stadium)
        assert stadium is not None
        self.assertEqual(stadium.handler_id, "stadium.gltf_viewer")
        self.assertIs(
            self.cards["apf2k8.stadiums.geometry"].status,
            ApfStatus.EXPORT_ONLY,
        )
        self.assertIsNone(capability_action_binding("apf2k8.models.scne_gltf"))
        raw_scene = ApfAsset(
            asset_id="apf:outer:2:inner:3",
            outer_index=2,
            inner_index=3,
            name="fixture_scene",
            type_name="SCNE",
            asset_class="scene",
            category=ApfCategory.STADIUMS,
            status=_status_for(2, 3, "SCNE", "fixture_scene"),
            decoded_size=1,
            outer_size=1,
            part_count=2,
        )
        self.assertIs(raw_scene.status, ApfStatus.EXPORT_ONLY)
        self.assertEqual(raw_scene.export_label, "Raw parts ZIP only")

    def test_only_exact_product_assets_receive_editable_catalog_status(self) -> None:
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
                DIGITAL_FONT_OUTER_INDEX,
                DIGITAL_FONT_INNER_INDEX,
                "TXTR",
                "digital_font",
            ),
            ApfStatus.EDITABLE,
        )
        self.assertEqual(
            DIGITAL_FONT_CATALOG_ID,
            f"apf:outer:{DIGITAL_FONT_OUTER_INDEX}:inner:{DIGITAL_FONT_INNER_INDEX}",
        )
        self.assertIs(
            _status_for(
                DIGITAL_FONT_OUTER_INDEX,
                DIGITAL_FONT_INNER_INDEX + 1,
                "TXTR",
                "digital_font",
            ),
            ApfStatus.EXPORT_ONLY,
        )


if __name__ == "__main__":
    unittest.main()

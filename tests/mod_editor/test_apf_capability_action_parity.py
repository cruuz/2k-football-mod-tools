"""Retail-free parity checks for APF capability cards and desktop actions."""

from __future__ import annotations

import importlib
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
from mod_editor.core.audio_conform import SUPPORTED_SUFFIXES


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
                if card.status in {
                    ApfStatus.COMING_SOON,
                    ApfStatus.EVIDENCE,
                    ApfStatus.RESEARCH,
                }:
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
                self.assertTrue(
                    binding.has_complete_editor
                    or binding.has_verified_one_shot_writer
                )
                if binding.has_verified_one_shot_writer:
                    self.assertIn(ApfProductAction.BUILD_COPY, binding.actions)
                    module_name, separator, function_name = str(
                        binding.one_shot_target
                    ).partition(":")
                    self.assertEqual(separator, ":")
                    self.assertTrue(function_name)
                    self.assertTrue(
                        hasattr(importlib.import_module(module_name), function_name)
                    )
                    self.assertIn("copied", binding.output_kind)
                else:
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

    def test_audio_cards_match_the_common_file_conformer(self) -> None:
        self.assertTrue(
            {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
            <= set(SUPPORTED_SUFFIXES)
        )
        for capability_id in (
            "apf2k8.audio.ausb_xma_export",
            "apf2k8.audio.xma_export",
        ):
            capability = self.capabilities[capability_id]
            card = self.cards[capability_id]
            copy = " ".join(
                (
                    capability.summary,
                    str(capability.raw["gui"]["reason"]),
                    *card.findings,
                )
            )
            portme = " ".join(capability.raw["portme"])
            with self.subTest(capability=capability_id):
                for name in ("WAV", "MP3", "FLAC", "OGG", "M4A"):
                    self.assertIn(name, copy)
                self.assertNotIn("FLAC/MP3 and batch PCM input remain unsupported", copy)
                self.assertIn("external XMA1 encoder", copy)
                self.assertIn("selected ordinary WAV/MP3/FLAC/OGG/M4A", portme)
                self.assertIn("folder/ZIP packs", portme)
                self.assertIn("mixed-format ordinary-audio packs remain unsupported", portme)

    def test_logo_cards_disclose_linked_cache_and_independent_wordmark_ownership(self) -> None:
        team_logo = CAPABILITY_ACTION_BINDINGS[
            "apf2k8.logos_cards.team_logo"
        ].product_note.casefold()
        cache = CAPABILITY_ACTION_BINDINGS[
            "apf2k8.logos_cards.team_logo_cache"
        ].product_note.casefold()
        wordmark = CAPABILITY_ACTION_BINDINGS[
            "apf2k8.logos_cards.textlogo_wordmarks"
        ].product_note.casefold()

        for claims in (team_logo, cache):
            self.assertIn("selector-slot-5", claims)
            self.assertIn("frontend", claims)
            self.assertIn("team select", claims)
            self.assertIn("selector-slot-6", claims)
            self.assertIn("uniform_textlogo", claims)
            self.assertIn("unproved", claims)
        self.assertIn("selector-slot-6", wordmark)
        self.assertIn("selector-slot-5", wordmark)
        self.assertIn("frontend/team select", wordmark)
        self.assertIn("never squeezes", wordmark)

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
        self.assertIn("31 independent native base ratings", binding.product_note)
        self.assertIn("native 100", binding.product_note)
        self.assertIn("player first/last-name", binding.product_note)
        self.assertIn("Dan CODEX", binding.product_note)
        self.assertIn("zero-capacity names", binding.product_note)
        self.assertIn("paired semantic +0x34", binding.product_note)
        self.assertIn("desktop dropdown", binding.product_note)
        self.assertIn("spot check", binding.product_note)
        self.assertIn("bounded on-disc team/player names", capability.summary)
        self.assertIn("31 native base ratings", capability.summary)
        self.assertIn("exact mirrored positions", capability.summary)
        self.assertIn("149 proved raw-save", capability.summary)
        self.assertIn("15 bounded text fields", capability.summary)
        self.assertIn("count-preserving populated memberships", capability.summary)
        self.assertIn("source native rating 100", capability.summary)
        self.assertIn("Dan CODEX", capability.raw["runtime"]["scope"])
        self.assertIn("abbreviations", capability.raw["runtime"]["scope"])
        self.assertIn(
            "without a numeric readout",
            capability.raw["runtime"]["scope"],
        )
        portme = " ".join(capability.raw["portme"])
        constraints = " ".join(capability.raw["input_constraints"])
        self.assertIn("+0x120..+0x126", constraints)
        self.assertIn("path_not_reached", portme)
        self.assertIn("membership", capability.raw["gui"]["reason"])
        self.assertIn("depth", capability.raw["gui"]["reason"])
        self.assertIn("+0x34", capability.raw["gui"]["reason"])
        self.assertIn("exact 0–16 positions", capability.raw["gui"]["reason"])
        self.assertIn("spot check remains pending", capability.raw["gui"]["reason"])
        self.assertIn("Save Players", capability.raw["gui"]["reason"])
        self.assertIn("signed-container reinjection", capability.raw["gui"]["reason"])

    def test_inspectors_exports_and_internal_evidence_are_not_fake_promises(self) -> None:
        expected = {
            "apf2k8.cross_title_model_conversion.nfl_to_apf": ApfStatus.PREVIEW,
            "apf2k8.mode_state_routing.state_graph": ApfStatus.PREVIEW,
            "apf2k8.portraits_faces.hi_head": ApfStatus.EXPORT_ONLY,
            "apf2k8.schedules_franchise.retained": ApfStatus.PREVIEW,
        }
        for capability_id, status in expected.items():
            with self.subTest(capability=capability_id):
                self.assertIsNotNone(capability_action_binding(capability_id))
                self.assertIs(self.cards[capability_id].status, status)

        hidden = {
            capability_id: card.status
            for capability_id, card in self.cards.items()
            if self.capabilities[capability_id].raw["gui"].get("expose") is False
        }
        self.assertTrue(hidden)
        self.assertLessEqual(
            set(hidden.values()),
            {ApfStatus.EVIDENCE, ApfStatus.RESEARCH},
        )
        self.assertNotIn(ApfStatus.COMING_SOON, hidden.values())
        self.assertNotIn(
            ApfStatus.COMING_SOON,
            {card.status for card in self.cards.values()},
        )

        logo_catalog = "apf2k8.logos_cards.uniform_catalog"
        self.assertIsNotNone(capability_action_binding(logo_catalog))
        self.assertIs(self.cards[logo_catalog].status, ApfStatus.EXPORT_ONLY)

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
        texture = capability_action_binding("apf2k8.stadiums.textures")
        self.assertIsNotNone(texture)
        assert texture is not None
        self.assertEqual(texture.handler_id, "stadium.embedded_texture_editor")
        self.assertTrue(texture.has_complete_editor)
        self.assertIs(
            self.cards["apf2k8.stadiums.textures"].status,
            ApfStatus.EDITABLE,
        )
        model = capability_action_binding("apf2k8.models.scne_gltf")
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.handler_id, "uniforms.model_position_roundtrip")
        self.assertEqual(
            model.actions,
            frozenset(
                {
                    ApfProductAction.PREVIEW,
                    ApfProductAction.EXPORT,
                    ApfProductAction.BUILD_COPY,
                }
            ),
        )
        self.assertTrue(model.has_verified_one_shot_writer)
        self.assertIs(
            self.cards["apf2k8.models.scne_gltf"].status,
            ApfStatus.EDITABLE,
        )
        # Release-gap audit (2026-08-04): the helmet/player round trip lives in
        # the Uniforms & Equipment workspace, so its capability card must render
        # there too -- not under Stadiums via the models_shap_scne surface
        # default. The stadium mesh round trip stays in Stadium Studio.
        self.assertIs(
            self.cards["apf2k8.models.scne_gltf"].category,
            ApfCategory.UNIFORMS,
        )
        stadium_model = capability_action_binding(
            "apf2k8.models.scne_same_count_position"
        )
        self.assertIsNotNone(stadium_model)
        assert stadium_model is not None
        self.assertTrue(stadium_model.has_verified_one_shot_writer)
        self.assertEqual(stadium_model.output_kind, "verified copied 1A")
        self.assertIs(
            self.cards["apf2k8.models.scne_same_count_position"].status,
            ApfStatus.EDITABLE,
        )
        self.assertIs(
            self.cards["apf2k8.models.scne_same_count_position"].category,
            ApfCategory.STADIUMS,
        )
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

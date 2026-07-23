"""Headless tests for the public mod-editor safety boundary."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mod_editor.core.capabilities import (
    Capability,
    CapabilityRegistry,
    CapabilityRegistryLoader,
    Classification,
)
from mod_editor.core.controller import ModEditorController
from mod_editor.core.errors import (
    ActionNotImplementedError,
    OutputRefusedError,
    RegistryError,
    ValidationError,
)
from mod_editor.core.model import GameId
from mod_editor.core.persistence import load_project
from mod_editor.core.sources import KnownFingerprint, SourceInspector


def _test_registry() -> CapabilityRegistry:
    safe_raw = {
        "backend": {
            "operation": "write",
            "module": "tools/reviewed_writer.py",
            "command": "python3 tools/reviewed_writer.py",
        },
        "gui": {"expose": True, "mode": "edit"},
        "input_constraints": ["PNG only"],
        "source_container": {
            "format": "XISO",
            "retail_file": "user source",
            "resource": "named asset",
            "hash_pins": [],
        },
        "selectors": {"fields": [], "notes": "Use a team/style name"},
        "runtime": {"status": "not-tested", "scope": "offline only", "evidence": []},
        "portme": ["Runtime visibility remains unproved"],
        "public_distribution": {"rule": "Never distribute retail game data"},
        "validation_command": "python3 tools/reviewed_validator.py",
    }
    safe = Capability(
        "nfl2k5.uniform.test",
        GameId.NFL2K5,
        "uniforms",
        Classification.OFFLINE_WRITER_PROVED,
        "Uniform test writer",
        "Uniforms",
        "Test-only capability",
        (".png",),
        safe_raw,
    )
    read_only_raw = dict(safe_raw)
    read_only_raw["backend"] = {
        "operation": "inspect",
        "module": "tools/inspect.py",
        "command": "python3 tools/inspect.py",
    }
    read_only_raw["gui"] = {"expose": True, "mode": "view"}
    read_only = Capability(
        "nfl2k5.models.inspect",
        GameId.NFL2K5,
        "models_shap_scne",
        Classification.READ_ONLY_MAPPED,
        "Model map",
        "Models",
        "Read-only",
        (".gltf",),
        read_only_raw,
    )
    return CapabilityRegistry((safe, read_only), None, False)


class CoreTests(unittest.TestCase):
    def test_product_registry_mode_skips_development_evidence_files(self) -> None:
        from mod_editor.capabilities import validate_registry

        with mock.patch.object(
            validate_registry,
            "load_and_validate",
            wraps=validate_registry.load_and_validate,
        ) as loader:
            registry = CapabilityRegistryLoader().load(
                allow_sample_fallback=False, check_files=False
            )
        self.assertFalse(registry.used_sample_fallback)
        self.assertFalse(loader.call_args.kwargs["check_files"])

    def test_missing_registry_has_explicit_sample_or_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            loader = CapabilityRegistryLoader(Path(temporary) / "missing.json")
            fallback = loader.load()
            self.assertTrue(fallback.used_sample_fallback)
            with self.assertRaises(RegistryError):
                loader.load(allow_sample_fallback=False)

    def test_read_only_hash_recognition_does_not_change_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "owned.xiso.iso"
            payload = (b"user-owned-test-disc\0" * 4096) + b"end"
            source.write_bytes(payload)
            before = source.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            fingerprint = KnownFingerprint(
                "test-disc", GameId.NFL2K5, "xiso", digest, "Synthetic test"
            )
            record = SourceInspector((fingerprint,)).inspect(source, GameId.NFL2K5)
            self.assertTrue(record.recognized)
            self.assertEqual(record.fingerprint_id, "test-disc")
            self.assertEqual(source.read_bytes(), before)

    def test_project_roundtrip_and_unknown_field_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "example.vcmod.json"
            controller = ModEditorController(_test_registry())
            original = controller.create_project("Example", GameId.NFL2K5)
            controller.save_project(path)
            loaded = load_project(path)
            self.assertEqual(loaded.project_id, original.project_id)
            self.assertEqual(loaded.game, GameId.NFL2K5)
            document = json.loads(path.read_text(encoding="utf-8"))
            document["raw_offset"] = "0x1234"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_project(path)

    def test_queue_requires_proved_writer_named_target_and_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            replacement = Path(temporary) / "logo.png"
            replacement.write_bytes(b"not-decoded-in-model-test")
            controller = ModEditorController(_test_registry())
            controller.create_project("Queue", GameId.NFL2K5)
            item = controller.enqueue_replacement(
                "nfl2k5.uniform.test", replacement, "detroit/away/style0"
            )
            self.assertEqual(item.target_id, "detroit/away/style0")
            with self.assertRaises(ValidationError):
                controller.enqueue_replacement(
                    "nfl2k5.models.inspect", replacement, "detroit"
                )
            with self.assertRaises(ValidationError):
                controller.enqueue_replacement(
                    "nfl2k5.uniform.test", replacement, "0x1234"
                )
            wrong = Path(temporary) / "logo.dds"
            wrong.write_bytes(b"dds")
            with self.assertRaises(ValidationError):
                controller.enqueue_replacement(
                    "nfl2k5.uniform.test", wrong, "detroit"
                )

    def test_copy_is_identical_exclusive_and_does_not_apply_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.iso"
            output = root / "output.iso"
            replacement = root / "uniform.png"
            source.write_bytes(os.urandom(128 * 1024))
            replacement.write_bytes(b"replacement")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            inspector = SourceInspector(
                (KnownFingerprint("test-disc", GameId.NFL2K5, "xiso", digest, "test"),)
            )
            controller = ModEditorController(_test_registry(), inspector)
            controller.create_project("Copy", GameId.NFL2K5)
            controller.select_source(source)
            controller.set_output_path(output)
            controller.enqueue_replacement(
                "nfl2k5.uniform.test", replacement, "detroit/away"
            )
            result = controller.create_staging_copy()
            self.assertTrue(result.verified_identical)
            self.assertEqual(result.replacements_applied, 0)
            self.assertEqual(source.read_bytes(), output.read_bytes())
            with self.assertRaises((OutputRefusedError, ValidationError)):
                controller.create_staging_copy()
            with self.assertRaises(ActionNotImplementedError):
                controller.apply_queued_replacements()

    def test_broken_output_symlink_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.iso"
            source.write_bytes(b"source")
            link = root / "output.iso"
            link.symlink_to(root / "missing-target.iso")
            digest = hashlib.sha256(b"source").hexdigest()
            inspector = SourceInspector(
                (KnownFingerprint("test", GameId.NFL2K5, "xiso", digest, "test"),)
            )
            controller = ModEditorController(_test_registry(), inspector)
            controller.create_project("Link", GameId.NFL2K5)
            controller.select_source(source)
            controller.set_output_path(link)
            with self.assertRaises(ValidationError):
                controller.create_staging_copy()
            self.assertTrue(link.is_symlink())

    def test_extracted_directory_copy_is_manifest_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "owned_apf_files"
            source.mkdir()
            executable = source / "default.xex"
            executable.write_bytes(b"synthetic xex")
            (source / "media").mkdir()
            (source / "media" / "asset.bin").write_bytes(b"asset" * 200)
            digest = hashlib.sha256(executable.read_bytes()).hexdigest()
            inspector = SourceInspector(
                (KnownFingerprint("test-apf", GameId.APF2K8, "xex2", digest, "test"),)
            )
            controller = ModEditorController(_test_registry(), inspector)
            controller.create_project("Directory", GameId.APF2K8)
            controller.select_source(source)
            output = root / "copied_apf_files"
            controller.set_output_path(output)
            result = controller.create_staging_copy()
            self.assertTrue(result.verified_identical)
            self.assertEqual((output / "default.xex").read_bytes(), b"synthetic xex")
            self.assertEqual(
                (output / "media" / "asset.bin").read_bytes(), b"asset" * 200
            )

    def test_canonical_registry_drives_badges_and_action_gates(self) -> None:
        registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
        self.assertFalse(registry.used_sample_fallback)
        self.assertGreaterEqual(len(registry.capabilities), 38)
        self.assertTrue(registry.for_game(GameId.NFL2K5))
        self.assertTrue(registry.for_game(GameId.APF2K8))
        self.assertEqual(
            registry.get("apf2k8.uniforms.jersey_00_23").badge, "PROVED"
        )
        self.assertTrue(
            registry.get("nfl2k5.uniforms.all_visual").can_queue_replacement
        )
        scorebug = registry.get("nfl2k5.scorebug_presentation.inventory")
        self.assertTrue(scorebug.can_queue_replacement)
        self.assertFalse(scorebug.is_experimental)
        self.assertTrue(
            registry.get("apf2k8.scorebug_presentation.inventory").is_experimental
        )
        self.assertFalse(
            registry.get("nfl2k5.cpu_ai_draft.logic").can_queue_replacement
        )
        apf_topology = registry.get(
            "apf2k8.models.scne_same_footprint_topology"
        )
        self.assertEqual(apf_topology.badge, "PROVED")
        self.assertFalse(apf_topology.can_queue_replacement)
        self.assertFalse(apf_topology.raw["gui"]["expose"])
        self.assertFalse(apf_topology.raw["gui"]["default_enabled"])
        self.assertEqual(apf_topology.raw["runtime"]["status"], "not-tested")
        nfl_geometry = registry.get(
            "nfl2k5.models.scne_same_footprint_geometry"
        )
        self.assertEqual(nfl_geometry.badge, "PROVED")
        self.assertFalse(nfl_geometry.can_queue_replacement)
        self.assertFalse(nfl_geometry.raw["gui"]["expose"])
        self.assertFalse(nfl_geometry.raw["gui"]["default_enabled"])
        self.assertEqual(nfl_geometry.raw["classification"], "runtime-proved")
        self.assertEqual(nfl_geometry.raw["runtime"]["status"], "visible-proved")
        self.assertEqual(
            nfl_geometry.raw["public_distribution"]["mod_payload"],
            "none-until-safe",
        )
        self.assertIn(
            "reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json",
            nfl_geometry.raw["runtime"]["evidence"],
        )
        self.assertIn(
            "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json",
            nfl_geometry.raw["evidence"],
        )
        for capability in registry.capabilities:
            if not capability.can_queue_replacement:
                continue
            self.assertEqual(capability.raw["backend"]["operation"], "write")
            self.assertTrue(capability.raw["gui"]["expose"])
            self.assertEqual(capability.raw["gui"]["mode"], "edit")
            self.assertTrue(capability.accepted_extensions)

    def test_requested_advanced_surfaces_are_present_and_not_accidentally_writable(self) -> None:
        registry = CapabilityRegistryLoader().load(allow_sample_fallback=False)
        requested = {
            "catching_drops",
            "cpu_ai_draft",
            "cross_title_model_conversion",
            "franchise_restoration_cross_title",
            "gameplay_tuning_sliders",
            "mode_state_routing",
            "scorebug_presentation",
        }
        present = {capability.surface for capability in registry.capabilities}
        self.assertTrue(requested.issubset(present))
        for capability in registry.capabilities:
            if capability.surface in requested and capability.badge == "PORTME":
                self.assertFalse(capability.can_queue_replacement)


if __name__ == "__main__":
    unittest.main()

"""Tiny provider/orchestrator tests; no retail image or emulator is used."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.core.capabilities import Classification
from mod_editor.core.controller import ModEditorController
from mod_editor.core.errors import OutputRefusedError
from mod_editor.core.model import GameId, SourceRecord
from mod_editor.core.providers import (
    Apf2k8HelmetColorProvider,
    Apf2k8JerseyColorProvider,
    Apf2k8PantsColorProvider,
    Apf2k8ShoulderColorProvider,
    Nfl2k5ScorebugProvider,
    Nfl2k5UnifiedVisualProvider,
    ProviderCommandResult,
    ProviderError,
    ProviderEvent,
    ProviderOrchestrator,
    ProviderRequest,
    ProviderStage,
    SubprocessCommandRunner,
    derived_provider_outputs,
)


CAPABILITY_ID = "nfl2k5.uniforms.all_visual"
CRIB_CAPABILITY_ID = "nfl2k5.crib.assets"
PINNED_SOURCE_SHA = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
APF_CAPABILITY_ID = "apf2k8.uniforms.jersey_00_23"
APF_PANTS_CAPABILITY_ID = "apf2k8.uniforms.pants_color_00_23"
APF_HELMET_CAPABILITY_ID = "apf2k8.uniforms.helmet_color_00_23"
APF_SHOULDER_CAPABILITY_ID = "apf2k8.uniforms.shoulder_color_00_23"
APF_DIGITAL_FONT_CAPABILITY_ID = "apf2k8.scorebug_presentation.digital_font"
APF_SOURCE_SHA = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
SCOREBUG_CAPABILITY_ID = "nfl2k5.scorebug_presentation.inventory"
NFL_AUDIO_CAPABILITY_ID = "nfl2k5.audio.menu_back_wav"


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def backend_project(path: Path) -> Path:
    value = {
        "schema": "nfl2k5_visual_mod_project/v1",
        "purpose": "Tiny provider-layer test recipe; never built as a game image.",
        "edits": [
            {
                "kind": "team_identity",
                "team_index": 0,
                "city": "Test City",
                "nickname": "Test Team",
                "abbreviation": "TST",
                "city_abbreviation": "TC",
            }
        ],
    }
    path.write_bytes(canonical_json(value))
    return path


def source_record(path: Path) -> SourceRecord:
    return SourceRecord(
        selected_path=str(path),
        inspected_path=str(path),
        kind="xiso",
        sha256=PINNED_SOURCE_SHA,
        size=path.stat().st_size,
        recognized=True,
        fingerprint_id="nfl2k5-usa-retail-xiso",
        detected_game=GameId.NFL2K5.value,
        note="Synthetic path with injected hash probe for provider tests only",
    )


def request(root: Path) -> ProviderRequest:
    source = root / "tiny-source.iso"
    source.write_bytes(b"tiny source; provider tests never copy it")
    project = backend_project(root / "backend-project.json")
    output = root / "new-output.xiso.iso"
    manifest, artifacts = derived_provider_outputs(output)
    return ProviderRequest(
        CAPABILITY_ID,
        GameId.NFL2K5,
        project,
        source_record(source),
        output,
        manifest,
        artifacts,
    )


def apf_recipe(path: Path, png: Path, asset_index: int = 6) -> Path:
    path.write_bytes(
        canonical_json(
            {
                "schema": "apf2k8_jersey_color_recipe/v1",
                "asset_index": asset_index,
                "png": str(png),
            }
        )
    )
    return path


def apf_source_record(path: Path) -> SourceRecord:
    return SourceRecord(
        selected_path=str(path),
        inspected_path=str(path),
        kind="apf-volume-0a",
        sha256=APF_SOURCE_SHA,
        size=path.stat().st_size,
        recognized=True,
        fingerprint_id="apf2k8-usa-volume-0a",
        detected_game=GameId.APF2K8.value,
        note="Tiny provider test path with an injected read-only hash result",
    )


def apf_request(root: Path, asset_index: int = 6) -> ProviderRequest:
    from PIL import Image

    source = root / "tiny-0A"
    source.write_bytes(b"tiny APF source; provider tests never copy it")
    png = root / "jersey.png"
    Image.new("RGBA", (1024, 1024), (12, 34, 56, 255)).save(png)
    recipe = apf_recipe(root / "apf-recipe.json", png, asset_index)
    output = root / "new-0A"
    manifest, artifacts = derived_provider_outputs(output)
    return ProviderRequest(
        APF_CAPABILITY_ID,
        GameId.APF2K8,
        recipe,
        apf_source_record(source),
        output,
        manifest,
        artifacts,
    )


def apf_pants_request(root: Path, asset_index: int = 13) -> ProviderRequest:
    from PIL import Image

    source = root / "tiny-pants-0A"
    source.write_bytes(b"tiny APF source; pants provider tests never copy it")
    png = root / "pants.png"
    Image.new("RGBA", (512, 512), (12, 34, 56, 255)).save(png)
    recipe = root / "apf-pants-recipe.json"
    recipe.write_bytes(canonical_json({
        "schema": "apf2k8_pants_color_recipe/v1",
        "asset_index": asset_index,
        "png": str(png),
    }))
    output = root / "new-pants-0A"
    manifest, artifacts = derived_provider_outputs(output)
    return ProviderRequest(
        APF_PANTS_CAPABILITY_ID,
        GameId.APF2K8,
        recipe,
        apf_source_record(source),
        output,
        manifest,
        artifacts,
    )


def apf_helmet_request(root: Path, asset_index: int = 16) -> ProviderRequest:
    from PIL import Image

    source = root / "tiny-helmet-0A"
    source.write_bytes(b"tiny APF source; helmet provider tests never copy it")
    png = root / "helmet.png"
    Image.new("RGBA", (256, 1024), (12, 34, 0, 255)).save(png)
    recipe = root / "apf-helmet-recipe.json"
    recipe.write_bytes(canonical_json({
        "schema": "apf2k8_helmet_color_recipe/v1",
        "asset_index": asset_index,
        "png": str(png),
    }))
    output = root / "new-helmet-0A"
    manifest, artifacts = derived_provider_outputs(output)
    return ProviderRequest(
        APF_HELMET_CAPABILITY_ID,
        GameId.APF2K8,
        recipe,
        apf_source_record(source),
        output,
        manifest,
        artifacts,
    )


def apf_shoulder_request(root: Path, asset_index: int = 8) -> ProviderRequest:
    from PIL import Image

    source = root / "tiny-shoulder-0A"
    source.write_bytes(b"tiny APF source; shoulder provider tests never copy it")
    png = root / "shoulder.png"
    Image.new("RGBA", (1024, 1024), (12, 34, 56, 211)).save(png)
    recipe = root / "apf-shoulder-recipe.json"
    recipe.write_bytes(canonical_json({
        "schema": "apf2k8_shoulder_color_recipe/v1",
        "asset_index": asset_index,
        "png": str(png),
    }))
    output = root / "new-shoulder-0A"
    manifest, artifacts = derived_provider_outputs(output)
    return ProviderRequest(
        APF_SHOULDER_CAPABILITY_ID,
        GameId.APF2K8,
        recipe,
        apf_source_record(source),
        output,
        manifest,
        artifacts,
    )


def scorebug_project(path: Path, targets: tuple[str, ...] = ("score_buga", "shield_espn")) -> Path:
    from PIL import Image

    edits = []
    for index, target in enumerate(targets):
        width, height = Nfl2k5ScorebugProvider.target_dimensions[target]
        png = path.parent / f"{target}.png"
        Image.new(
            "RGBA",
            (width, height),
            ((index + 1) * 30, (index + 1) * 40, (index + 1) * 50, 255),
        ).save(png)
        payload = png.read_bytes()
        edits.append(
            {
                "png": png.name,
                "png_sha256": hashlib.sha256(payload).hexdigest(),
                "png_size": len(payload),
                "target": target,
            }
        )
    path.write_bytes(
        canonical_json(
            {
                "edits": edits,
                "purpose": "Tiny scorebug provider test recipe; never built as a game image.",
                "schema": Nfl2k5ScorebugProvider.backend_schema,
                "source": dict(Nfl2k5ScorebugProvider.source_pin),
            }
        )
    )
    return path


def scorebug_source_record(path: Path) -> SourceRecord:
    return SourceRecord(
        selected_path=str(path),
        inspected_path=str(path),
        kind="xiso",
        sha256=PINNED_SOURCE_SHA,
        size=Nfl2k5ScorebugProvider.source_size,
        recognized=True,
        fingerprint_id="nfl2k5-usa-retail-xiso",
        detected_game=GameId.NFL2K5.value,
        note="Tiny provider path with an injected exact retail hash/size result",
    )


def scorebug_request(root: Path) -> ProviderRequest:
    source = root / "tiny-scorebug-source.iso"
    source.write_bytes(b"tiny scorebug source; provider tests never copy it")
    project = scorebug_project(root / "scorebug-project.json")
    output = root / "new-scorebug-output.xiso.iso"
    manifest, artifacts = derived_provider_outputs(output)
    return ProviderRequest(
        SCOREBUG_CAPABILITY_ID,
        GameId.NFL2K5,
        project,
        scorebug_source_record(source),
        output,
        manifest,
        artifacts,
    )


class FakeProvider:
    provider_id = "fake-nfl-provider"
    capability_ids = frozenset({CAPABILITY_ID})

    def __init__(self, fail_build: bool = False):
        self.calls: list[str] = []
        self.fail_build = fail_build

    def preflight(self, request, capability, emit):
        self.calls.append("preflight")
        emit(ProviderEvent(ProviderStage.PREFLIGHT, "INFO", "fake preflight"))

    def validate(self, request, capability, emit):
        self.calls.append("validate")
        emit(ProviderEvent(ProviderStage.VALIDATE, "INFO", "fake validate"))
        return ProviderCommandResult(("fake", "validate"), 0, "ok", "")

    def build(self, request, capability, emit):
        self.calls.append("build")
        if self.fail_build:
            raise ProviderError("synthetic build failure")
        emit(ProviderEvent(ProviderStage.BUILD, "INFO", "fake build"))
        return ProviderCommandResult(("fake", "build"), 0, "ok", "")

    def verify(self, request, capability, emit):
        self.calls.append("verify")
        emit(ProviderEvent(ProviderStage.VERIFY, "INFO", "fake verify"))
        return ProviderCommandResult(("fake", "verify"), 0, "ok", "")


class FakeApfProvider(FakeProvider):
    provider_id = "fake-apf-provider"
    capability_ids = frozenset({APF_CAPABILITY_ID})


class RecordingRunner:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], Path, ProviderStage]] = []

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(argv)
        self.calls.append((fixed, cwd, stage))
        command = fixed[2]
        if command == "validate":
            stdout = json.dumps(
                {
                    "schema": "nfl2k5_visual_mod_project/v1",
                    "schema_and_png_pins_valid": True,
                }
            )
        elif command == "build":
            stdout = "NFL2K5_VISUAL_MOD_BUILD_PASS edits=1 changed=1 runtime=false\n"
        else:
            stdout = "NFL2K5_VISUAL_MOD_VERIFY_PASS edits=1 changed=1 runtime=false\n"
        emit(ProviderEvent(stage, "INFO", stdout.strip()))
        return ProviderCommandResult(fixed, 0, stdout, "")


class ApfRecordingRunner:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], Path, ProviderStage]] = []

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(argv)
        self.calls.append((fixed, cwd, stage))
        if stage == ProviderStage.VALIDATE:
            stdout = json.dumps(
                {
                    "schema": "apf2k8_jersey_color_recipe/v1",
                    "recipe_valid": True,
                    "asset_index": 6,
                    "png_dimensions": [1024, 1024],
                    "png_mode": "RGBA",
                }
            )
        elif stage == ProviderStage.BUILD:
            stdout = "APF_JERSEY_FAMILY_PATCH_PASS mode=patched asset=6 entry=875\n"
        else:
            stdout = (
                "APF_JERSEY_FAMILY_VERIFY_PASS asset=6 levels=9 "
                "outside_span=true source_unchanged=true\n"
            )
        emit(ProviderEvent(stage, "INFO", stdout.strip()))
        return ProviderCommandResult(fixed, 0, stdout, "")


class ApfPantsRecordingRunner:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], Path, ProviderStage]] = []

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(argv)
        self.calls.append((fixed, cwd, stage))
        if stage == ProviderStage.VALIDATE:
            stdout = json.dumps({
                "schema": "apf2k8_pants_color_recipe/v1",
                "recipe_valid": True,
                "asset_index": 13,
                "png_dimensions": [512, 512],
                "png_mode": "RGBA",
                "png_fully_opaque": True,
            })
        elif stage == ProviderStage.BUILD:
            stdout = "APF_PANTS_FAMILY_PATCH_PASS mode=patched asset=13 entry=882\n"
        else:
            stdout = (
                "APF_PANTS_FAMILY_VERIFY_PASS asset=13 levels=8 normals=3 "
                "outside_target=exact runtime_visibility=false\n"
            )
        emit(ProviderEvent(stage, "INFO", stdout.strip()))
        return ProviderCommandResult(fixed, 0, stdout, "")


class ApfHelmetRecordingRunner:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], Path, ProviderStage]] = []

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(argv)
        self.calls.append((fixed, cwd, stage))
        if stage == ProviderStage.VALIDATE:
            stdout = json.dumps({
                "schema": "apf2k8_helmet_color_recipe/v1",
                "recipe_valid": True,
                "asset_index": 16,
                "png_dimensions": [256, 1024],
                "png_mode": "RGBA",
                "png_fully_opaque": True,
                "png_blue_zero": True,
                "png_alpha_255": True,
                "channel_semantics_named": False,
            })
        elif stage == ProviderStage.BUILD:
            stdout = "APF_HELMET_FAMILY_PATCH_PASS mode=patched asset=16 entry=900\n"
        else:
            stdout = (
                "APF_HELMET_FAMILY_VERIFY_PASS asset=16 levels=7 normal=1 "
                "channels=raw-rg outside_target=exact runtime_visibility=false\n"
            )
        emit(ProviderEvent(stage, "INFO", stdout.strip()))
        return ProviderCommandResult(fixed, 0, stdout, "")


class ApfShoulderRecordingRunner:
    def __init__(self):
        self.calls: list[tuple[tuple[str, ...], Path, ProviderStage]] = []

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(argv)
        self.calls.append((fixed, cwd, stage))
        if stage == ProviderStage.VALIDATE:
            stdout = json.dumps({
                "schema": "apf2k8_shoulder_color_recipe/v1",
                "recipe_valid": True,
                "asset_index": 8,
                "png_dimensions": [1024, 1024],
                "png_mode": "RGBA",
            })
        elif stage == ProviderStage.BUILD:
            stdout = "APF_SHOULDER_FAMILY_PATCH_PASS mode=patched asset=8 entry=910\n"
        else:
            stdout = (
                "APF_SHOULDER_FAMILY_VERIFY_PASS asset=8 levels=9 siblings=3 "
                "paired_normal=true outside_target=exact runtime_visibility=false\n"
            )
        emit(ProviderEvent(stage, "INFO", stdout.strip()))
        return ProviderCommandResult(fixed, 0, stdout, "")


class ScorebugRecordingRunner:
    def __init__(
        self,
        *,
        invalid_validation: bool = False,
        missing_marker: ProviderStage | None = None,
    ):
        self.calls: list[tuple[tuple[str, ...], Path, ProviderStage]] = []
        self.invalid_validation = invalid_validation
        self.missing_marker = missing_marker

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(argv)
        self.calls.append((fixed, cwd, stage))
        project_path = Path(fixed[fixed.index("--project") + 1]).resolve(strict=True)
        project = json.loads(project_path.read_bytes())
        targets = [edit["target"] for edit in project["edits"]]
        if stage == ProviderStage.VALIDATE:
            if self.invalid_validation:
                stdout = json.dumps({"schema": Nfl2k5ScorebugProvider.backend_schema})
            else:
                stdout = json.dumps(
                    {
                        "edit_count": len(targets),
                        "project_path": str(project_path),
                        "project_sha256": hashlib.sha256(project_path.read_bytes()).hexdigest(),
                        "schema": Nfl2k5ScorebugProvider.backend_schema,
                        "source_pins_valid": True,
                        "strict_importers_passed": True,
                        "target_dimensions": {
                            target: {
                                "height": Nfl2k5ScorebugProvider.target_dimensions[target][1],
                                "width": Nfl2k5ScorebugProvider.target_dimensions[target][0],
                            }
                            for target in targets
                        },
                        "targets": targets,
                    }
                )
        elif stage == ProviderStage.BUILD:
            stdout = (
                "scorebug build completed without marker\n"
                if self.missing_marker == stage
                else "NFL2K5_SCOREBUG_MOD_BUILD_PASS targets=2 changed=42 runtime=false\n"
            )
        else:
            stdout = (
                "scorebug verification completed without marker\n"
                if self.missing_marker == stage
                else "NFL2K5_SCOREBUG_MOD_VERIFY_PASS targets=2 changed=42 runtime=false\n"
            )
        emit(ProviderEvent(stage, "INFO", stdout.strip()))
        return ProviderCommandResult(fixed, 0, stdout, "")


class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = CapabilityRegistryLoader().load(
            allow_sample_fallback=False, check_files=False
        )

    def test_orchestrator_orders_preflight_validate_build_verify(self) -> None:
        fake = FakeProvider()
        orchestrator = ProviderOrchestrator(self.registry, (fake,))
        events: list[ProviderEvent] = []
        with tempfile.TemporaryDirectory() as temporary:
            result = orchestrator.build_and_verify(request(Path(temporary)), events.append)
        self.assertEqual(fake.calls, ["preflight", "validate", "build", "verify"])
        self.assertTrue(result.validated)
        self.assertTrue(result.built)
        self.assertTrue(result.independently_verified)
        self.assertEqual(events[-1].stage, ProviderStage.COMPLETE)

    def test_validate_only_never_calls_build_or_verify(self) -> None:
        fake = FakeProvider()
        orchestrator = ProviderOrchestrator(self.registry, (fake,))
        with tempfile.TemporaryDirectory() as temporary:
            result = orchestrator.validate(request(Path(temporary)))
        self.assertEqual(fake.calls, ["preflight", "validate"])
        self.assertTrue(result.validated)
        self.assertFalse(result.built)
        self.assertFalse(result.independently_verified)

    def test_failed_build_never_calls_verify(self) -> None:
        fake = FakeProvider(fail_build=True)
        orchestrator = ProviderOrchestrator(self.registry, (fake,))
        events: list[ProviderEvent] = []
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ProviderError):
                orchestrator.build_and_verify(request(Path(temporary)), events.append)
        self.assertEqual(fake.calls, ["preflight", "validate", "build"])
        self.assertTrue(
            any(
                event.stage == ProviderStage.BUILD and event.level == "ERROR"
                for event in events
            )
        )

    def test_unmapped_capability_is_refused(self) -> None:
        orchestrator = ProviderOrchestrator(self.registry, (FakeProvider(),))
        with self.assertRaises(ProviderError):
            orchestrator.provider_id("nfl2k5.cpu_ai_draft.logic")

    def test_default_provider_map_contains_all_nine_typed_routes(self) -> None:
        orchestrator = ProviderOrchestrator(self.registry)
        self.assertEqual(
            orchestrator.provider_id(CAPABILITY_ID), "nfl2k5-unified-visual-v1"
        )
        self.assertEqual(
            orchestrator.provider_id(CRIB_CAPABILITY_ID),
            "nfl2k5-unified-visual-v1",
        )
        self.assertEqual(
            orchestrator.provider_id(SCOREBUG_CAPABILITY_ID), "nfl2k5-scorebug-v1"
        )
        self.assertEqual(
            orchestrator.provider_id(NFL_AUDIO_CAPABILITY_ID),
            "nfl2k5-menu-back-audio-v1",
        )
        self.assertEqual(
            orchestrator.provider_id(APF_CAPABILITY_ID), "apf2k8-jersey-color-v1"
        )
        self.assertEqual(
            orchestrator.provider_id(APF_PANTS_CAPABILITY_ID),
            "apf2k8-pants-color-v1",
        )
        self.assertEqual(
            orchestrator.provider_id(APF_HELMET_CAPABILITY_ID),
            "apf2k8-helmet-color-v1",
        )
        self.assertEqual(
            orchestrator.provider_id(APF_SHOULDER_CAPABILITY_ID),
            "apf2k8-shoulder-color-v1",
        )
        self.assertEqual(
            orchestrator.provider_id(APF_DIGITAL_FONT_CAPABILITY_ID),
            "apf2k8-digital-font-v1",
        )
        self.assertFalse(
            orchestrator.supports("apf2k8.models.scne_same_footprint_topology")
        )
        self.assertFalse(
            orchestrator.supports("nfl2k5.models.scne_same_footprint_geometry")
        )

    def test_real_provider_constructs_fixed_argv_and_three_stages(self) -> None:
        runner = RecordingRunner()
        provider = Nfl2k5UnifiedVisualProvider(
            runner=runner,
            source_hasher=lambda path, progress: (PINNED_SOURCE_SHA, path.stat().st_size),
        )
        orchestrator = ProviderOrchestrator(self.registry, (provider,))
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            result = orchestrator.build_and_verify(job)
        self.assertTrue(result.independently_verified)
        self.assertEqual([call[0][2] for call in runner.calls], ["validate", "build", "verify"])
        self.assertEqual(runner.calls[0][0][3:], ("--project", str(job.backend_project)))
        expected_tail = (
            "--project",
            str(job.backend_project),
            "--source-xiso",
            job.source.selected_path,
            "--output-xiso",
            str(job.output_xiso),
            "--manifest",
            str(job.manifest),
            "--artifact-dir",
            str(job.artifact_dir),
        )
        self.assertEqual(runner.calls[1][0][3:], expected_tail)
        registry_template = self.registry.get(CAPABILITY_ID).raw["backend"]["command"]
        self.assertNotIn(registry_template, runner.calls[1][0])

    def test_real_preflight_refuses_existing_output_and_noncanonical_project(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider(
            runner=RecordingRunner(),
            source_hasher=lambda path, progress: (PINNED_SOURCE_SHA, path.stat().st_size),
        )
        capability = self.registry.get(CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            job.output_xiso.write_bytes(b"must survive refusal")
            with self.assertRaises(OutputRefusedError):
                provider.preflight(job, capability, lambda event: None)
            self.assertEqual(job.output_xiso.read_bytes(), b"must survive refusal")
            job.output_xiso.unlink()
            value = json.loads(job.backend_project.read_text(encoding="utf-8"))
            job.backend_project.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ProviderError):
                provider.preflight(job, capability, lambda event: None)

    def test_scorebug_provider_constructs_fixed_argv_and_three_stages(self) -> None:
        runner = ScorebugRecordingRunner()
        provider = Nfl2k5ScorebugProvider(
            runner=runner,
            source_hasher=lambda path, progress: (
                PINNED_SOURCE_SHA,
                Nfl2k5ScorebugProvider.source_size,
            ),
        )
        orchestrator = ProviderOrchestrator(self.registry, (provider,))
        with tempfile.TemporaryDirectory() as temporary:
            job = scorebug_request(Path(temporary))
            result = orchestrator.build_and_verify(job)
        self.assertTrue(result.independently_verified)
        self.assertEqual(
            [call[2] for call in runner.calls],
            [ProviderStage.VALIDATE, ProviderStage.BUILD, ProviderStage.VERIFY],
        )
        self.assertEqual(
            runner.calls[0][0][2:],
            ("validate", "--project", str(job.backend_project)),
        )
        expected_tail = (
            "--project",
            str(job.backend_project),
            "--source-xiso",
            job.source.selected_path,
            "--output-xiso",
            str(job.output_xiso),
            "--manifest",
            str(job.manifest),
            "--artifact-dir",
            str(job.artifact_dir),
        )
        self.assertEqual(runner.calls[1][0][3:], expected_tail)
        for argv, cwd, _stage in runner.calls:
            self.assertTrue(argv[1].endswith("tools/nfl2k5_scorebug_mod_project.py"))
            self.assertEqual(cwd, Path(__file__).resolve().parents[2])
            self.assertNotIn(
                self.registry.get(SCOREBUG_CAPABILITY_ID).raw["backend"]["command"],
                argv,
            )

    def test_scorebug_preflight_rejects_project_png_source_and_output_forgery(self) -> None:
        provider = Nfl2k5ScorebugProvider(
            runner=ScorebugRecordingRunner(),
            source_hasher=lambda path, progress: (
                PINNED_SOURCE_SHA,
                Nfl2k5ScorebugProvider.source_size,
            ),
        )
        capability = self.registry.get(SCOREBUG_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = scorebug_request(root)
            value = json.loads(job.backend_project.read_bytes())

            value["edits"][0]["offset"] = 1234
            job.backend_project.write_bytes(canonical_json(value))
            with self.assertRaisesRegex(ProviderError, "invalid edit"):
                provider.preflight(job, capability, lambda event: None)

            job = scorebug_request(root)
            value = json.loads(job.backend_project.read_bytes())
            value["source"]["xiso_size"] -= 1
            job.backend_project.write_bytes(canonical_json(value))
            with self.assertRaisesRegex(ProviderError, "canonical typed"):
                provider.preflight(job, capability, lambda event: None)

            job = scorebug_request(root)
            value = json.loads(job.backend_project.read_bytes())
            value["edits"][1]["target"] = value["edits"][0]["target"]
            job.backend_project.write_bytes(canonical_json(value))
            with self.assertRaisesRegex(ProviderError, "at most once"):
                provider.preflight(job, capability, lambda event: None)

            job = scorebug_request(root)
            value = json.loads(job.backend_project.read_bytes())
            job.backend_project.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ProviderError, "canonical typed"):
                provider.preflight(job, capability, lambda event: None)

            job = scorebug_request(root)
            (root / "score_buga.png").write_bytes(b"forged")
            with self.assertRaisesRegex(ProviderError, "size differs"):
                provider.preflight(job, capability, lambda event: None)

            job = scorebug_request(root)
            wrong_source = replace(job.source, size=1)
            with self.assertRaisesRegex(ProviderError, "pinned retail XISO"):
                provider.preflight(
                    replace(job, source=wrong_source), capability, lambda event: None
                )

            job = scorebug_request(root)
            job.output_xiso.write_bytes(b"sentinel")
            with self.assertRaises(OutputRefusedError):
                provider.preflight(job, capability, lambda event: None)
            self.assertEqual(job.output_xiso.read_bytes(), b"sentinel")
            job.output_xiso.unlink()

            with self.assertRaisesRegex(OutputRefusedError, "distinct"):
                provider.preflight(
                    replace(job, manifest=job.output_xiso),
                    capability,
                    lambda event: None,
                )

            protected_png = root / "score_buga.png"
            with self.assertRaisesRegex(OutputRefusedError, "already exists"):
                provider.preflight(
                    replace(job, output_xiso=protected_png),
                    capability,
                    lambda event: None,
                )

    def test_scorebug_provider_pins_registry_contract_backend_hash_and_source_hash(self) -> None:
        provider = Nfl2k5ScorebugProvider(
            runner=ScorebugRecordingRunner(),
            source_hasher=lambda path, progress: (
                PINNED_SOURCE_SHA,
                Nfl2k5ScorebugProvider.source_size,
            ),
        )
        capability = self.registry.get(SCOREBUG_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            job = scorebug_request(Path(temporary))
            provider._validate_capability(job, capability)

            module_raw = copy.deepcopy(capability.raw)
            module_raw["backend"]["module"] = "tools/nfl_scorebug_xiso_workflow.py"
            with self.assertRaisesRegex(ProviderError, "does not exactly authorize"):
                provider._validate_capability(job, replace(capability, raw=module_raw))

            pin_raw = copy.deepcopy(capability.raw)
            pin_raw["source_container"]["hash_pins"].append("0" * 64)
            with self.assertRaisesRegex(ProviderError, "does not exactly authorize"):
                provider._validate_capability(job, replace(capability, raw=pin_raw))

            selector_raw = copy.deepcopy(capability.raw)
            selector_raw["selectors"]["fields"][0]["allowed"] += ", raw_offset"
            with self.assertRaisesRegex(ProviderError, "does not exactly authorize"):
                provider._validate_capability(job, replace(capability, raw=selector_raw))

            with self.assertRaisesRegex(ProviderError, "does not exactly authorize"):
                provider._validate_capability(
                    job,
                    replace(capability, classification=Classification.RUNTIME_PROVED),
                )

            with mock.patch.object(provider, "backend_module_sha256", "0" * 64):
                with self.assertRaisesRegex(ProviderError, "backend hash changed"):
                    provider._validate_capability(job, capability)

            wrong_hash_provider = Nfl2k5ScorebugProvider(
                runner=ScorebugRecordingRunner(),
                source_hasher=lambda path, progress: (
                    "0" * 64,
                    Nfl2k5ScorebugProvider.source_size,
                ),
            )
            with self.assertRaisesRegex(ProviderError, "source changed"):
                wrong_hash_provider.preflight(job, capability, lambda event: None)

    def test_scorebug_provider_rejects_unproved_reports_and_missing_markers(self) -> None:
        def orchestrator(runner: ScorebugRecordingRunner) -> ProviderOrchestrator:
            provider = Nfl2k5ScorebugProvider(
                runner=runner,
                source_hasher=lambda path, progress: (
                    PINNED_SOURCE_SHA,
                    Nfl2k5ScorebugProvider.source_size,
                ),
            )
            return ProviderOrchestrator(self.registry, (provider,))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ProviderError, "did not prove"):
                orchestrator(ScorebugRecordingRunner(invalid_validation=True)).validate(
                    scorebug_request(root)
                )

            with self.assertRaisesRegex(ProviderError, "build success marker"):
                orchestrator(
                    ScorebugRecordingRunner(missing_marker=ProviderStage.BUILD)
                ).build_and_verify(scorebug_request(root))

            runner = ScorebugRecordingRunner(missing_marker=ProviderStage.VERIFY)
            with self.assertRaisesRegex(ProviderError, "verifier exited"):
                orchestrator(runner).build_and_verify(scorebug_request(root))
            self.assertEqual(
                [call[2] for call in runner.calls],
                [ProviderStage.VALIDATE, ProviderStage.BUILD, ProviderStage.VERIFY],
            )

    def test_apf_provider_constructs_fixed_argv_for_recipe_build_and_verifier(self) -> None:
        runner = ApfRecordingRunner()
        provider = Apf2k8JerseyColorProvider(
            runner=runner,
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        orchestrator = ProviderOrchestrator(self.registry, (provider,))
        with tempfile.TemporaryDirectory() as temporary:
            # Canonicalise the temp dir so the exact-argv assertions below are not
            # defeated by a symlinked (macOS /private/var) or short-name (Windows)
            # temp location: the providers realpath their inputs, so every path in
            # the recorded argv is already canonical.
            temporary = str(Path(temporary).resolve())
            job = apf_request(Path(temporary))
            result = orchestrator.build_and_verify(job)
        self.assertTrue(result.independently_verified)
        self.assertEqual(
            [call[2] for call in runner.calls],
            [ProviderStage.VALIDATE, ProviderStage.BUILD, ProviderStage.VERIFY],
        )
        self.assertEqual(
            runner.calls[0][0][2:],
            ("validate-recipe", "--recipe", str(job.backend_project)),
        )
        self.assertTrue(runner.calls[0][0][1].endswith("apf_jersey_family_verify.py"))
        self.assertEqual(
            runner.calls[1][0][2:],
            (
                "--index", job.source.selected_path,
                "--asset-index", "6",
                "--png", str(Path(temporary) / "jersey.png"),
                "--output-volume", str(job.output_xiso),
                "--manifest", str(job.manifest),
            ),
        )
        self.assertTrue(runner.calls[1][0][1].endswith("apf_jersey_family_patch.py"))
        self.assertEqual(
            runner.calls[2][0][2:],
            (
                "verify", "--recipe", str(job.backend_project),
                "--source-0a", job.source.selected_path,
                "--output-0a", str(job.output_xiso),
                "--manifest", str(job.manifest),
                "--artifact-dir", str(job.artifact_dir),
            ),
        )
        self.assertNotIn(
            self.registry.get(APF_CAPABILITY_ID).raw["backend"]["command"],
            runner.calls[1][0],
        )

    def test_apf_preflight_refuses_noncanonical_selector_png_and_outputs(self) -> None:
        provider = Apf2k8JerseyColorProvider(
            runner=ApfRecordingRunner(),
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        capability = self.registry.get(APF_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = apf_request(root)
            value = json.loads(job.backend_project.read_text(encoding="utf-8"))
            value["asset_index"] = 24
            job.backend_project.write_bytes(canonical_json(value))
            with self.assertRaisesRegex(ProviderError, "canonical typed"):
                provider.preflight(job, capability, lambda event: None)

            value["asset_index"] = 6
            value["raw_offset"] = "0x1234"
            job.backend_project.write_bytes(canonical_json(value))
            with self.assertRaisesRegex(ProviderError, "canonical typed"):
                provider.preflight(job, capability, lambda event: None)

            value.pop("raw_offset")
            job.backend_project.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ProviderError, "canonical typed"):
                provider.preflight(job, capability, lambda event: None)

            png = root / "jersey.png"
            link = root / "linked.png"
            link.symlink_to(png)
            apf_recipe(job.backend_project, link)
            with self.assertRaisesRegex(ProviderError, "non-symlink"):
                provider.preflight(job, capability, lambda event: None)

            from PIL import Image

            wrong = root / "wrong.png"
            Image.new("RGBA", (512, 512), (0, 0, 0, 255)).save(wrong)
            apf_recipe(job.backend_project, wrong)
            with self.assertRaisesRegex(ProviderError, "1024x1024"):
                provider.preflight(job, capability, lambda event: None)

            apf_recipe(job.backend_project, png)
            job.output_xiso.write_bytes(b"sentinel")
            with self.assertRaises(OutputRefusedError):
                provider.preflight(job, capability, lambda event: None)
            self.assertEqual(job.output_xiso.read_bytes(), b"sentinel")
            job.output_xiso.unlink()
            aliased = replace(job, manifest=job.output_xiso)
            with self.assertRaisesRegex(OutputRefusedError, "distinct"):
                provider.preflight(aliased, capability, lambda event: None)

    def test_apf_provider_requires_exact_registry_module_classification_and_hash_pin(self) -> None:
        provider = Apf2k8JerseyColorProvider(
            runner=ApfRecordingRunner(),
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        capability = self.registry.get(APF_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            job = apf_request(Path(temporary))
            module_raw = copy.deepcopy(capability.raw)
            module_raw["backend"]["module"] = "tools/apf_uniform_mip_patch.py"
            with self.assertRaises(ProviderError):
                provider._validate_capability(job, replace(capability, raw=module_raw))

            with self.assertRaises(ProviderError):
                provider._validate_capability(
                    job,
                    replace(capability, classification=Classification.RUNTIME_PROVED),
                )

            pin_raw = copy.deepcopy(capability.raw)
            pin_raw["source_container"]["hash_pins"].append("0" * 64)
            with self.assertRaises(ProviderError):
                provider._validate_capability(job, replace(capability, raw=pin_raw))

    def test_apf_pants_provider_uses_fixed_recipe_build_and_verify_argv(self) -> None:
        runner = ApfPantsRecordingRunner()
        provider = Apf2k8PantsColorProvider(
            runner=runner,
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        orchestrator = ProviderOrchestrator(self.registry, (provider,))
        with tempfile.TemporaryDirectory() as temporary:
            # Canonicalise the temp dir (see the jersey test) so the exact-argv
            # comparison holds under macOS /private/var and Windows short names.
            temporary = str(Path(temporary).resolve())
            job = apf_pants_request(Path(temporary))
            result = orchestrator.build_and_verify(job)
        self.assertTrue(result.independently_verified)
        self.assertEqual(
            [call[2] for call in runner.calls],
            [ProviderStage.VALIDATE, ProviderStage.BUILD, ProviderStage.VERIFY],
        )
        self.assertEqual(
            runner.calls[0][0][2:],
            ("validate-recipe", "--recipe", str(job.backend_project)),
        )
        self.assertTrue(runner.calls[0][0][1].endswith("apf_pants_family_verify.py"))
        self.assertEqual(
            runner.calls[1][0][2:],
            (
                "--index", job.source.selected_path,
                "--asset-index", "13",
                "--png", str(Path(temporary) / "pants.png"),
                "--output-volume", str(job.output_xiso),
                "--manifest", str(job.manifest),
            ),
        )
        self.assertTrue(runner.calls[1][0][1].endswith("apf_pants_family_patch.py"))
        self.assertEqual(
            runner.calls[2][0][2:],
            (
                "verify", "--recipe", str(job.backend_project),
                "--source-0a", job.source.selected_path,
                "--output-0a", str(job.output_xiso),
                "--manifest", str(job.manifest),
                "--artifact-dir", str(job.artifact_dir),
            ),
        )
        self.assertNotIn(
            self.registry.get(APF_PANTS_CAPABILITY_ID).raw["backend"]["command"],
            runner.calls[1][0],
        )

    def test_apf_pants_preflight_rejects_transparency_and_wrong_schema(self) -> None:
        from PIL import Image

        provider = Apf2k8PantsColorProvider(
            runner=ApfPantsRecordingRunner(),
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        capability = self.registry.get(APF_PANTS_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = apf_pants_request(root)
            Image.new("RGBA", (512, 512), (1, 2, 3, 254)).save(root / "pants.png")
            with self.assertRaisesRegex(ProviderError, "fully opaque"):
                provider.preflight(job, capability, lambda event: None)

            Image.new("RGBA", (512, 512), (1, 2, 3, 255)).save(root / "pants.png")
            value = json.loads(job.backend_project.read_bytes())
            value["schema"] = "apf2k8_jersey_color_recipe/v1"
            job.backend_project.write_bytes(canonical_json(value))
            with self.assertRaisesRegex(ProviderError, "canonical typed"):
                provider.preflight(job, capability, lambda event: None)

    def test_apf_pants_provider_pins_writer_verifier_schema_and_registry(self) -> None:
        provider = Apf2k8PantsColorProvider(
            runner=ApfPantsRecordingRunner(),
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        for relative, expected in (
            (provider.backend_module, provider.backend_module_sha256),
            (provider.verifier_module, provider.verifier_module_sha256),
            (provider.recipe_schema_file, provider.recipe_schema_file_sha256),
        ):
            self.assertEqual(
                hashlib.sha256(Path(relative).read_bytes()).hexdigest(), expected
            )
        capability = self.registry.get(APF_PANTS_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            job = apf_pants_request(Path(temporary))
            provider._validate_capability(job, capability)
            forged = copy.deepcopy(capability.raw)
            forged["selectors"]["fields"][0]["allowed"] = "raw offset"
            with self.assertRaises(ProviderError):
                provider._validate_capability(job, replace(capability, raw=forged))

    def test_apf_helmet_provider_uses_fixed_strict_recipe_build_and_verify_argv(self) -> None:
        runner = ApfHelmetRecordingRunner()
        provider = Apf2k8HelmetColorProvider(
            runner=runner,
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        capability = self.registry.get(APF_HELMET_CAPABILITY_ID)
        exposed_raw = copy.deepcopy(capability.raw)
        exposed_raw["gui"]["expose"] = True
        exposed_raw["gui"]["default_enabled"] = True
        exposed = replace(capability, raw=exposed_raw)
        registry = replace(
            self.registry,
            capabilities=tuple(
                exposed if item.capability_id == APF_HELMET_CAPABILITY_ID else item
                for item in self.registry.capabilities
            ),
        )
        orchestrator = ProviderOrchestrator(registry, (provider,))
        with tempfile.TemporaryDirectory() as temporary:
            # Canonicalise the temp dir (see the jersey test) so the exact-argv
            # comparison holds under macOS /private/var and Windows short names.
            temporary = str(Path(temporary).resolve())
            job = apf_helmet_request(Path(temporary))
            result = orchestrator.build_and_verify(job)
        self.assertTrue(result.independently_verified)
        self.assertEqual(
            [call[2] for call in runner.calls],
            [ProviderStage.VALIDATE, ProviderStage.BUILD, ProviderStage.VERIFY],
        )
        self.assertEqual(
            runner.calls[0][0][2:],
            ("validate-recipe", "--recipe", str(job.backend_project)),
        )
        self.assertTrue(runner.calls[0][0][1].endswith("apf_helmet_family_verify.py"))
        self.assertEqual(
            runner.calls[1][0][2:],
            (
                "--index", job.source.selected_path,
                "--asset-index", "16",
                "--png", str(Path(temporary) / "helmet.png"),
                "--output-volume", str(job.output_xiso),
                "--manifest", str(job.manifest),
            ),
        )
        self.assertTrue(runner.calls[1][0][1].endswith("apf_helmet_family_patch.py"))
        self.assertEqual(
            runner.calls[2][0][2:],
            (
                "verify", "--recipe", str(job.backend_project),
                "--source-0a", job.source.selected_path,
                "--output-0a", str(job.output_xiso),
                "--manifest", str(job.manifest),
                "--artifact-dir", str(job.artifact_dir),
            ),
        )
        self.assertNotIn(
            capability.raw["backend"]["command"], runner.calls[1][0]
        )

    def test_apf_helmet_preflight_rejects_blue_alpha_and_semantics_claims(self) -> None:
        from PIL import Image

        provider = Apf2k8HelmetColorProvider(
            runner=ApfHelmetRecordingRunner(),
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        capability = self.registry.get(APF_HELMET_CAPABILITY_ID)
        raw = copy.deepcopy(capability.raw)
        raw["gui"]["expose"] = True
        capability = replace(capability, raw=raw)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = apf_helmet_request(root)
            Image.new("RGBA", (256, 1024), (1, 2, 3, 255)).save(root / "helmet.png")
            with self.assertRaisesRegex(ProviderError, "B channel"):
                provider.preflight(job, capability, lambda event: None)
            Image.new("RGBA", (256, 1024), (1, 2, 0, 254)).save(root / "helmet.png")
            with self.assertRaisesRegex(ProviderError, "fully opaque"):
                provider.preflight(job, capability, lambda event: None)

            valid_runner = ApfHelmetRecordingRunner()
            provider.runner = valid_runner
            Image.new("RGBA", (256, 1024), (1, 2, 0, 255)).save(root / "helmet.png")
            valid_runner.run = lambda argv, cwd, stage, emit: ProviderCommandResult(
                tuple(argv), 0, json.dumps({
                    "schema": provider.recipe_schema,
                    "recipe_valid": True,
                    "asset_index": 16,
                    "png_dimensions": [256, 1024],
                    "png_mode": "RGBA",
                    "png_fully_opaque": True,
                    "png_blue_zero": True,
                    "png_alpha_255": True,
                    "channel_semantics_named": True,
                }), ""
            )
            with self.assertRaisesRegex(ProviderError, "typed recipe/PNG contract"):
                provider.validate(job, capability, lambda event: None)

    def test_apf_helmet_provider_pins_writer_verifier_and_schema(self) -> None:
        provider = Apf2k8HelmetColorProvider()
        for relative, expected in (
            (provider.backend_module, provider.backend_module_sha256),
            (provider.verifier_module, provider.verifier_module_sha256),
            (provider.recipe_schema_file, provider.recipe_schema_file_sha256),
        ):
            self.assertEqual(
                hashlib.sha256(Path(relative).read_bytes()).hexdigest(), expected
            )
        self.assertEqual(provider.png_dimensions, (256, 1024))
        self.assertTrue(provider.png_fully_opaque)
        self.assertTrue(provider.png_blue_zero)
        self.assertFalse(provider.channels_semantics_named)

    def test_apf_shoulder_provider_uses_fixed_recipe_build_and_verify_argv(self) -> None:
        runner = ApfShoulderRecordingRunner()
        provider = Apf2k8ShoulderColorProvider(
            runner=runner,
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        orchestrator = ProviderOrchestrator(self.registry, (provider,))
        with tempfile.TemporaryDirectory() as temporary:
            # Canonicalise the temp dir (see the jersey test) so the exact-argv
            # comparison holds under macOS /private/var and Windows short names.
            temporary = str(Path(temporary).resolve())
            job = apf_shoulder_request(Path(temporary))
            result = orchestrator.build_and_verify(job)
        self.assertTrue(result.independently_verified)
        self.assertEqual(
            [call[2] for call in runner.calls],
            [ProviderStage.VALIDATE, ProviderStage.BUILD, ProviderStage.VERIFY],
        )
        self.assertEqual(
            runner.calls[0][0][2:],
            ("validate-recipe", "--recipe", str(job.backend_project)),
        )
        self.assertTrue(runner.calls[0][0][1].endswith("apf_shoulder_family_verify.py"))
        self.assertEqual(
            runner.calls[1][0][2:],
            (
                "--index", job.source.selected_path,
                "--asset-index", "8",
                "--png", str(Path(temporary) / "shoulder.png"),
                "--output-volume", str(job.output_xiso),
                "--manifest", str(job.manifest),
            ),
        )
        self.assertTrue(runner.calls[1][0][1].endswith("apf_shoulder_family_patch.py"))
        self.assertEqual(
            runner.calls[2][0][2:],
            (
                "verify", "--recipe", str(job.backend_project),
                "--source-0a", job.source.selected_path,
                "--output-0a", str(job.output_xiso),
                "--manifest", str(job.manifest),
                "--artifact-dir", str(job.artifact_dir),
            ),
        )
        self.assertNotIn(
            self.registry.get(APF_SHOULDER_CAPABILITY_ID).raw["backend"]["command"],
            runner.calls[1][0],
        )

    def test_apf_shoulder_provider_pins_contract_and_rejects_wrong_dimensions(self) -> None:
        from PIL import Image

        provider = Apf2k8ShoulderColorProvider(
            runner=ApfShoulderRecordingRunner(),
            source_hasher=lambda path, progress: (APF_SOURCE_SHA, path.stat().st_size),
        )
        for relative, expected in (
            (provider.backend_module, provider.backend_module_sha256),
            (provider.verifier_module, provider.verifier_module_sha256),
            (provider.recipe_schema_file, provider.recipe_schema_file_sha256),
        ):
            self.assertEqual(
                hashlib.sha256(Path(relative).read_bytes()).hexdigest(), expected
            )
        capability = self.registry.get(APF_SHOULDER_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = apf_shoulder_request(root)
            provider._validate_capability(job, capability)
            Image.new("RGBA", (512, 512), (1, 2, 3, 4)).save(root / "shoulder.png")
            with self.assertRaisesRegex(ProviderError, "1024x1024"):
                provider.preflight(job, capability, lambda event: None)

    def test_provider_tracks_corrected_registry_kind_allowlist_and_rejects_unknown(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider(
            runner=RecordingRunner(),
            source_hasher=lambda path, progress: (PINNED_SOURCE_SHA, path.stat().st_size),
        )
        capability = self.registry.get(CAPABILITY_ID)
        self.assertEqual(
            provider._registry_authorized_kinds(capability), provider.backend_known_kinds
        )
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            value = json.loads(job.backend_project.read_text(encoding="utf-8"))
            value["edits"] = [
                {"kind": "player_portrait", "portrait_id": "0001", "png": "portrait.png"}
            ]
            job.backend_project.write_bytes(canonical_json(value))
            provider.preflight(job, capability, lambda event: None)
            value["edits"] = [{"kind": "arbitrary_offset_patch", "offset": "0x1234"}]
            job.backend_project.write_bytes(canonical_json(value))
            with self.assertRaisesRegex(ProviderError, "not authorized"):
                provider.preflight(job, capability, lambda event: None)

    def test_unified_ausb_preflight_requires_and_forwards_private_audio_inputs(self) -> None:
        runner = RecordingRunner()
        provider = Nfl2k5UnifiedVisualProvider(
            runner=runner,
            source_hasher=lambda path, progress: (
                PINNED_SOURCE_SHA, path.stat().st_size
            ),
        )
        capability_id = "nfl2k5.audio.ausb_fixed_range_wav"
        capability = self.registry.get(capability_id)
        with tempfile.TemporaryDirectory() as temporary:
            # Canonicalise the temp dir so the forwarded private-input paths, which
            # the provider realpaths, compare equal under macOS /private/var and
            # Windows short names.
            root = Path(temporary).resolve()
            job = replace(request(root), capability_id=capability_id)
            wav = root / "replacement.wav"
            wav.write_bytes(b"synthetic user WAV; preflight does not decode it")
            job.backend_project.write_bytes(canonical_json({
                "schema": "nfl2k5_visual_mod_project/v1",
                "purpose": "Synthetic AUSB provider safety-input routing test.",
                "edits": [{
                    "kind": "ausb_audio",
                    "asset_id": "nfl2k5.audio.ausb.o0000.c0000.r00000",
                    "wav": str(wav),
                }],
            }))

            with self.assertRaisesRegex(
                ProviderError, "three private safety inputs"
            ):
                provider.preflight(job, capability, lambda event: None)

            cache = root / "private-cache"
            derived = cache / "derived"
            derived.mkdir(parents=True)
            exact = derived / "audio-source-pcm-fingerprints-v1.json"
            containment = derived / "audio-source-pcm-containment-v2.json"
            exact.write_bytes(b"synthetic private exact inventory")
            containment.write_bytes(b"synthetic private containment inventory")
            bound = replace(
                job,
                source_cache_root=cache,
                audio_exact_inventory=exact,
                audio_containment_inventory=containment,
            )
            provider.preflight(bound, capability, lambda event: None)
            provider.build(bound, capability, lambda event: None)
            argv = runner.calls[-1][0]
            self.assertEqual(
                argv[argv.index("--source-cache-root") + 1], str(cache)
            )
            self.assertEqual(
                argv[argv.index("--audio-exact-inventory") + 1], str(exact)
            )
            self.assertEqual(
                argv[argv.index("--audio-containment-inventory") + 1],
                str(containment),
            )

    def test_unified_visual_build_does_not_receive_private_audio_paths(self) -> None:
        runner = RecordingRunner()
        provider = Nfl2k5UnifiedVisualProvider(runner=runner)
        capability = self.registry.get(CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            job = request(Path(temporary))
            provider.build(job, capability, lambda event: None)
        argv = runner.calls[-1][0]
        self.assertNotIn("--source-cache-root", argv)
        self.assertNotIn("--audio-exact-inventory", argv)
        self.assertNotIn("--audio-containment-inventory", argv)

    def test_unified_provider_pins_and_composes_exact_stadium_texture_kind(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider()
        capability = self.registry.get(CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = request(root)
            png = root / "cement01.png"
            png.write_bytes(b"synthetic user PNG; validate does not decode it")
            wav = root / "menu-back.wav"
            wav.write_bytes(b"synthetic user WAV; validate does not decode it")
            job.backend_project.write_bytes(canonical_json({
                "schema": "nfl2k5_visual_mod_project/v1",
                "purpose": "Exact Stadium texture mixed-provider closure test.",
                "edits": [
                    {
                        "kind": "stadium_texture",
                        "target": (
                            "nfl2k5.stadium.o3280.c0005.scene2648.texture0002"
                        ),
                        "png": str(png),
                    },
                    {"kind": "menu_back_audio", "wav": str(wav)},
                ],
            }))
            provider._validate_capability(job, capability)
            result = provider.validate(job, capability, lambda event: None)
            report = json.loads(result.stdout)
            self.assertEqual(
                report["kind_counts"],
                {"menu_back_audio": 1, "stadium_texture": 1},
            )
            self.assertTrue(report["schema_and_png_pins_valid"])

    def test_crib_capability_authorizes_canonical_team_photo_project(self) -> None:
        provider = Nfl2k5UnifiedVisualProvider(
            runner=RecordingRunner(),
            source_hasher=lambda path, progress: (
                PINNED_SOURCE_SHA, path.stat().st_size
            ),
        )
        capability = self.registry.get(CRIB_CAPABILITY_ID)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = replace(request(root), capability_id=CRIB_CAPABILITY_ID)
            job.backend_project.write_bytes(canonical_json({
                "schema": "nfl2k5_visual_mod_project/v1",
                "purpose": "Crib provider preflight contract test.",
                "edits": [{
                    "kind": "crib_team_photo",
                    "selector": "crib_team_photo:00_photo_00",
                    "png": "user-photo.png",
                }],
            }))

            provider._validate_capability(job, capability)
            provider.preflight(job, capability, lambda event: None)

    def test_controller_persists_provider_binding_without_project_schema_change(self) -> None:
        fake = FakeProvider()
        orchestrator = ProviderOrchestrator(self.registry, (fake,))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = request(root)
            controller = ModEditorController(
                self.registry, provider_orchestrator=orchestrator
            )
            controller.create_project("Typed provider", GameId.NFL2K5)
            assert controller.project is not None
            controller.project.source = job.source
            controller.set_output_path(job.output_xiso)
            item = controller.import_provider_project(CAPABILITY_ID, job.backend_project)
            self.assertEqual(item.target_id, "provider:fake-nfl-provider")
            result = controller.build_typed_provider()
            self.assertTrue(result.independently_verified)
            saved = root / "typed.vcmod.json"
            controller.save_project(saved)
            document = json.loads(saved.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], "vc_mod_project/v1")
            reopened = ModEditorController(
                self.registry, provider_orchestrator=orchestrator
            )
            reopened.open_project(saved)
            self.assertEqual(
                reopened.typed_provider_binding().target_id,
                "provider:fake-nfl-provider",
            )

    def test_importing_a_new_typed_recipe_replaces_the_previous_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unified = root / "unified.json"
            scorebug = root / "scorebug.json"
            unified.write_text("{}\n", encoding="utf-8")
            scorebug.write_text("{}\n", encoding="utf-8")
            controller = ModEditorController(self.registry)
            controller.create_project("Replace binding", GameId.NFL2K5)
            controller.import_provider_project(CAPABILITY_ID, unified)
            replacement = controller.import_provider_project(
                SCOREBUG_CAPABILITY_ID, scorebug
            )
            assert controller.project is not None
            bindings = [
                row
                for row in controller.project.replacements
                if row.target_id.startswith("provider:")
            ]
            self.assertEqual(bindings, [replacement])
            self.assertEqual(
                replacement.target_id,
                "provider:nfl2k5-scorebug-v1",
            )

    def test_controller_import_and_build_is_game_generic_for_apf_recipe(self) -> None:
        fake = FakeApfProvider()
        orchestrator = ProviderOrchestrator(self.registry, (fake,))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = apf_request(root)
            controller = ModEditorController(
                self.registry, provider_orchestrator=orchestrator
            )
            controller.create_project("Typed APF recipe", GameId.APF2K8)
            assert controller.project is not None
            controller.project.source = job.source
            controller.set_output_path(job.output_xiso)
            item = controller.import_provider_project(
                APF_CAPABILITY_ID, job.backend_project
            )
            self.assertEqual(item.target_id, "provider:fake-apf-provider")
            result = controller.build_typed_provider()
            self.assertTrue(result.independently_verified)
            self.assertEqual(fake.calls, ["preflight", "validate", "build", "verify"])

    def test_subprocess_runner_forces_argv_mode_closed_stdin_and_no_shell(self) -> None:
        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("provider output\n")
                self.stderr = io.StringIO("")

            def wait(self):
                return 0

        captured = {}

        def fake_popen(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return FakeProcess()

        runner = SubprocessCommandRunner()
        events: list[ProviderEvent] = []
        hostile_environment = {
            "LD_PRELOAD": "/tmp/forged.so",
            "LD_AUDIT": "/tmp/audit.so",
            "GCONV_PATH": "/tmp/forged-gconv",
            "PYTHONPATH": "/tmp/forged-python",
            "AWS_SECRET_ACCESS_KEY": "do-not-inherit",
        }
        with mock.patch.dict("mod_editor.core.providers.os.environ", hostile_environment), \
             mock.patch("mod_editor.core.providers.subprocess.Popen", fake_popen):
            result = runner.run(
                ("python3", "fixed-provider.py", "validate"),
                Path.cwd(),
                ProviderStage.VALIDATE,
                events.append,
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(captured["argv"], ("python3", "fixed-provider.py", "validate"))
        self.assertIs(captured["kwargs"]["stdin"], __import__("subprocess").DEVNULL)
        self.assertIs(captured["kwargs"]["shell"], False)
        self.assertEqual(captured["kwargs"]["env"], {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": __import__("os").defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        })
        self.assertTrue(any(event.message == "provider output" for event in events))


if __name__ == "__main__":
    unittest.main()

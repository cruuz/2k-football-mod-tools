"""Recipe, provider, and independent-verifier tests for APF digital_font."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from mod_editor.__main__ import main as editor_main
from mod_editor.core import apf_digital_font as font_recipe
from mod_editor.core.apf_digital_font import (
    APF_DIGITAL_FONT_RECIPE_SCHEMA,
    APF_DIGITAL_FONT_SCOPE,
    APF_DIGITAL_FONT_STORED_CHANNEL,
    APF_DIGITAL_FONT_TARGET,
    ApfDigitalFontRecipeError,
    canonical_apf_digital_font_recipe_json,
    create_apf_digital_font_recipe,
    load_apf_digital_font_recipe,
)
from mod_editor.core.apf_digital_font_provider import Apf2k8DigitalFontProvider
from mod_editor.core.capabilities import Capability, Classification
from mod_editor.core.errors import OutputRefusedError
from mod_editor.core.model import GameId, SourceRecord
from mod_editor.core.providers import (
    ProviderCommandResult,
    ProviderError,
    ProviderRequest,
    ProviderStage,
    SubprocessCommandRunner,
)


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import apf_digital_font_verify as font_verify  # noqa: E402
import apf_texture_patch as archive_patch  # noqa: E402


def make_font_png(path: Path, *, size=(128, 128), mode="RGBA", colored=False) -> Path:
    if mode == "RGBA":
        image = Image.new("RGBA", size, (254 if colored else 255, 255, 255, 0))
        if size == (128, 128) and not colored:
            alpha = Image.new("L", size)
            alpha.putdata([
                (x * 17 + y * 29) & 0xFF
                for y in range(128)
                for x in range(128)
            ])
            image.putalpha(alpha)
    else:
        image = Image.new(mode, size, 255)
    image.save(path)
    return path


def font_capability() -> Capability:
    provider = Apf2k8DigitalFontProvider
    raw = {
        "backend": {
            "command": "python3 tools/apf_digital_font_patch.py --index <0A> --png <png> --output-volume <new-0A> --manifest <manifest>",
            "module": provider.backend_module,
            "operation": "write",
        },
        "gui": {
            "default_enabled": True,
            "expose": True,
            "mode": "edit",
            "reason": "fixed alpha-only shared global provider",
        },
        "selectors": {
            "fields": [{
                "allowed": "digital_font only",
                "name": "target",
                "required": True,
            }],
            "notes": "fixed shared target",
        },
        "source_container": {"hash_pins": [provider.source_sha256]},
    }
    return Capability(
        capability_id="apf2k8.scorebug_presentation.digital_font",
        game=GameId.APF2K8,
        surface="scorebug_presentation",
        classification=Classification.OFFLINE_WRITER_PROVED,
        title="APF shared digital font",
        category="Scorebug / presentation",
        summary="fixed shared alpha texture",
        accepted_extensions=(".png", ".json"),
        raw=raw,
    )


def font_request(root: Path) -> ProviderRequest:
    png = make_font_png(root / "digital-font.png")
    recipe = root / "digital-font.recipe.json"
    create_apf_digital_font_recipe(output=recipe, png=png)
    source = root / "retail-0A"
    source.write_bytes(b"tiny fixture; provider hash callback supplies the retail identity")
    record = SourceRecord(
        selected_path=str(source),
        inspected_path=str(source),
        kind="apf-volume-0a",
        sha256=Apf2k8DigitalFontProvider.source_sha256,
        size=Apf2k8DigitalFontProvider.source_size,
        recognized=True,
        fingerprint_id="apf2k8-usa-volume-0a",
        detected_game=GameId.APF2K8.value,
    )
    return ProviderRequest(
        capability_id="apf2k8.scorebug_presentation.digital_font",
        game=GameId.APF2K8,
        backend_project=recipe,
        source=record,
        output_xiso=root / "new-0A",
        manifest=root / "digital-font.manifest.json",
        artifact_dir=root / "digital-font.artifacts",
    )


class FakeFontRunner:
    def __init__(self, request: ProviderRequest):
        self.request = request
        self.calls: list[tuple[tuple[str, ...], ProviderStage]] = []
        self.staged_scripts: list[Path] = []
        self.staged_hashes: list[dict[str, str]] = []

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(os.fspath(item) for item in argv)
        self.calls.append((fixed, stage))
        script = Path(fixed[1])
        self.staged_scripts.append(script)
        self.staged_hashes.append({
            f"tools/{path.name}": hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(script.parent.glob("*.py"))
        })
        if stage == ProviderStage.VALIDATE:
            stdout = json.dumps({
                "alpha_sha256": "a" * 64,
                "field_scorebug_only_proved": False,
                "png_dimensions": [128, 128],
                "png_mode": "RGBA",
                "png_rgb_solid_white": True,
                "png_sha256": "b" * 64,
                "png_size": 100,
                "production_dxt5a_encoder_ready": False,
                "recipe_valid": True,
                "runtime_visibility_proved": False,
                "schema": APF_DIGITAL_FONT_RECIPE_SCHEMA,
                "scope": APF_DIGITAL_FONT_SCOPE,
                "stored_channel": APF_DIGITAL_FONT_STORED_CHANNEL,
                "target": APF_DIGITAL_FONT_TARGET,
            }) + "\n"
        elif stage == ProviderStage.BUILD:
            self.request.manifest.write_text(json.dumps({
                "copied_volume": {
                    "output_volume": str(self.request.output_xiso),
                },
                "family_target": {
                    "field_scorebug_only_proved": False,
                    "inner_index": 246,
                    "outer_index": 1310,
                    "runtime_visibility_proved": False,
                    "shared_global_ui_texture": True,
                },
                "mode": "patched",
                "schema": Apf2k8DigitalFontProvider.backend_schema,
            }), encoding="utf-8")
            stdout = "APF_DIGITAL_FONT_PATCH_PASS outer=1310 inner=246 runtime=false\n"
        else:
            stdout = "APF_DIGITAL_FONT_VERIFY_PASS global=true runtime=false\n"
        return ProviderCommandResult(fixed, 0, stdout, "")


class ApfDigitalFontTests(unittest.TestCase):
    def test_shared_texture_compressor_default_contract_remains_byte_exact(self) -> None:
        historical_vectors = (
            (
                b"APF2K8",
                10,
                "298139512256b1f4c747811f7b7e6c2cd44f7d8c80067acfddad470279c116d7",
            ),
            (
                b"A" * 4097,
                10,
                "cc0ac53772e3fdf01bea95801a74dc1efc3f493ccc878002aa32500d53dc04ba",
            ),
            (
                b"ABC" * 3000,
                11,
                "d0e3dc17ce4b19dc186f39849b40161f26eeaae691ec0e3fe183bab4045dba39",
            ),
        )
        for decoded, shift, expected_sha256 in historical_vectors:
            encoded = archive_patch.compress_h7a(decoded, shift)
            self.assertEqual(hashlib.sha256(encoded).hexdigest(), expected_sha256)
            self.assertEqual(
                encoded,
                archive_patch.compress_h7a(
                    decoded,
                    shift,
                    candidate_limit=archive_patch.MAX_H7A_CANDIDATES,
                ),
            )
        with self.assertRaisesRegex(archive_patch.PatchError, "must be positive"):
            archive_patch.compress_h7a(b"ABC", 10, candidate_limit=0)

    def test_headless_cli_creates_fixed_global_alpha_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = make_font_png(root / "font.png")
            output = root / "font.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = editor_main([
                    "--create-apf-digital-font-recipe",
                    str(output),
                    "--apf-digital-font-png",
                    str(png),
                ])
            self.assertEqual(status, 0)
            self.assertIn("MOD_EDITOR_APF_DIGITAL_FONT_RECIPE_CREATED", stdout.getvalue())
            self.assertEqual(load_apf_digital_font_recipe(output).png_path, png.resolve())

    def test_create_and_load_canonical_alpha_only_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = make_font_png(root / "font.png")
            output = root / "font.recipe.json"
            png_payload = png.read_bytes()
            with Image.open(png) as image:
                alpha = image.getchannel("A").tobytes()

            created = create_apf_digital_font_recipe(output=output, png=png)

            self.assertEqual(created, output.resolve())
            value = json.loads(output.read_bytes())
            self.assertEqual(value, {
                "alpha_sha256": hashlib.sha256(alpha).hexdigest(),
                "png": "font.png",
                "png_sha256": hashlib.sha256(png_payload).hexdigest(),
                "png_size": len(png_payload),
                "schema": APF_DIGITAL_FONT_RECIPE_SCHEMA,
                "scope": APF_DIGITAL_FONT_SCOPE,
                "stored_channel": APF_DIGITAL_FONT_STORED_CHANNEL,
                "target": APF_DIGITAL_FONT_TARGET,
            })
            self.assertEqual(
                output.read_bytes(), canonical_apf_digital_font_recipe_json(value)
            )
            loaded = load_apf_digital_font_recipe(output)
            self.assertEqual(loaded.recipe_path, output.resolve())
            self.assertEqual(loaded.png_path, png.resolve())
            self.assertEqual(loaded.alpha_sha256, hashlib.sha256(alpha).hexdigest())
            serialized = output.read_text(encoding="utf-8")
            for forbidden in ("outer_index", "inner_index", "offset", "payload", "retail"):
                self.assertNotIn(forbidden, serialized)

    def test_recipe_rejects_dimensions_mode_nonwhite_rgb_suffix_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = make_font_png(root / "valid.png")
            linked = root / "linked.png"
            linked.symlink_to(valid)
            wrong_suffix = root / "valid.bin"
            wrong_suffix.write_bytes(valid.read_bytes())
            cases = [
                ("dimensions", make_font_png(root / "dimensions.png", size=(127, 128))),
                ("mode", make_font_png(root / "mode.png", mode="RGB")),
                ("colored", make_font_png(root / "colored.png", colored=True)),
                ("suffix", wrong_suffix),
                ("symlink", linked),
            ]
            for name, png in cases:
                output = root / f"reject-{name}.json"
                with self.subTest(name=name), self.assertRaises(ApfDigitalFontRecipeError):
                    create_apf_digital_font_recipe(output=output, png=png)
                self.assertFalse(os.path.lexists(output))

    def test_recipe_loader_rejects_scope_fields_pins_duplicates_and_png_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = make_font_png(root / "font.png")
            original = root / "original.json"
            create_apf_digital_font_recipe(output=original, png=png)
            base = json.loads(original.read_bytes())

            mutations = {
                "scope": {**base, "scope": "field-scorebug-only"},
                "target": {**base, "target": "scorebug"},
                "channel": {**base, "stored_channel": "rgba"},
                "alpha": {**base, "alpha_sha256": "0" * 64},
                "size-bool": {**base, "png_size": True},
                "extra": {**base, "raw_offset": 123},
            }
            for name, value in mutations.items():
                path = root / f"reject-{name}.json"
                path.write_bytes(canonical_apf_digital_font_recipe_json(value))
                with self.subTest(name=name), self.assertRaises(ApfDigitalFontRecipeError):
                    load_apf_digital_font_recipe(path)

            noncanonical = root / "noncanonical.json"
            noncanonical.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaises(ApfDigitalFontRecipeError):
                load_apf_digital_font_recipe(noncanonical)

            duplicate = root / "duplicate.json"
            duplicate.write_text('{"schema":"x","schema":"y"}\n', encoding="utf-8")
            with self.assertRaisesRegex(ApfDigitalFontRecipeError, "duplicate"):
                load_apf_digital_font_recipe(duplicate)

            make_font_png(png, colored=True)
            with self.assertRaises(ApfDigitalFontRecipeError):
                load_apf_digital_font_recipe(original)

    def test_recipe_output_is_exclusive_and_owned_partial_is_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = make_font_png(root / "font.png")
            existing = root / "existing.json"
            existing.write_text("mine", encoding="utf-8")
            with self.assertRaises(OutputRefusedError):
                create_apf_digital_font_recipe(output=existing, png=png)
            self.assertEqual(existing.read_text(encoding="utf-8"), "mine")

            broken = root / "broken.json"
            broken.symlink_to(root / "missing")
            with self.assertRaises(OutputRefusedError):
                create_apf_digital_font_recipe(output=broken, png=png)
            self.assertTrue(broken.is_symlink())

            interrupted = root / "interrupted.json"
            with patch.object(font_recipe.os, "write", side_effect=OSError("injected")):
                with self.assertRaises(ApfDigitalFontRecipeError):
                    create_apf_digital_font_recipe(output=interrupted, png=png)
            self.assertFalse(os.path.lexists(interrupted))

    def test_schema_freezes_fixed_global_alpha_contract(self) -> None:
        schema = json.loads(
            (ROOT / "mod_editor/apf_digital_font_recipe.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema"]["const"], APF_DIGITAL_FONT_RECIPE_SCHEMA)
        self.assertEqual(schema["properties"]["target"]["const"], APF_DIGITAL_FONT_TARGET)
        self.assertEqual(schema["properties"]["scope"]["const"], APF_DIGITAL_FONT_SCOPE)
        self.assertEqual(schema["properties"]["stored_channel"]["const"], "alpha")
        self.assertEqual(set(schema["required"]), {
            "alpha_sha256", "png", "png_sha256", "png_size", "schema",
            "scope", "stored_channel", "target",
        })

    def test_independent_validator_and_exclusive_metadata_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = make_font_png(root / "font.png")
            recipe = root / "font.json"
            create_apf_digital_font_recipe(output=recipe, png=png)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = font_verify.main(["validate-recipe", "--recipe", str(recipe)])
            self.assertEqual(status, 0)
            report = json.loads(stdout.getvalue())
            self.assertTrue(report["recipe_valid"])
            self.assertTrue(report["png_rgb_solid_white"])
            self.assertEqual(report["stored_channel"], "alpha")
            self.assertFalse(report["field_scorebug_only_proved"])
            self.assertFalse(report["runtime_visibility_proved"])

            artifact = root / "artifacts"
            receipt = font_verify.write_artifact_dir(artifact, {
                "recipe": {"alpha_sha256": report["alpha_sha256"]},
                "scope_boundary": {
                    "shared_global_ui_texture": True,
                    "runtime_visibility_proved": False,
                },
                "verification": {"contains_game_or_replacement_bytes": False},
            })
            raw = receipt.read_bytes()
            self.assertEqual(raw, canonical_apf_digital_font_recipe_json(json.loads(raw)))
            for forbidden in ("replacement_base64", "png_base64", "retail_bytes"):
                self.assertNotIn(forbidden, raw.decode("utf-8"))
            with self.assertRaises(font_verify.VerifyError):
                font_verify.write_artifact_dir(artifact, {})

    def test_provider_uses_fixed_argv_and_emits_global_runtime_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = font_request(root)
            runner = FakeFontRunner(request)
            provider = Apf2k8DigitalFontProvider(
                runner=runner,
                source_hasher=lambda _path, _progress: (
                    Apf2k8DigitalFontProvider.source_sha256,
                    Apf2k8DigitalFontProvider.source_size,
                ),
                workspace=ROOT,
            )
            events = []
            provider.preflight(request, font_capability(), events.append)
            validation = provider.validate(request, font_capability(), events.append)
            build = provider.build(request, font_capability(), events.append)
            verify = provider.verify(request, font_capability(), events.append)

            self.assertTrue(json.loads(validation.stdout)["recipe_valid"])
            self.assertEqual(build.returncode, verify.returncode, 0)
            self.assertEqual([stage for _, stage in runner.calls], [
                ProviderStage.VALIDATE,
                ProviderStage.BUILD,
                ProviderStage.VERIFY,
            ])
            validate_argv, build_argv, verify_argv = [argv for argv, _ in runner.calls]
            self.assertEqual(validate_argv[2:4], ("validate-recipe", "--recipe"))
            self.assertIn(str(request.output_xiso), build_argv)
            self.assertNotIn(str(request.backend_project), build_argv)
            self.assertIn(str(request.backend_project), verify_argv)
            self.assertIn(str(request.artifact_dir), verify_argv)
            for argv in (validate_argv, build_argv, verify_argv):
                for forbidden in ("--offset", "--outer", "--inner", "--file-index"):
                    self.assertNotIn(forbidden, argv)
                self.assertFalse(Path(argv[1]).is_relative_to(ROOT))
            expected_code = {
                relative: digest
                for relative, digest in Apf2k8DigitalFontProvider.module_pins.items()
                if relative.startswith("tools/") and relative.endswith(".py")
            }
            self.assertEqual(runner.staged_hashes, [expected_code] * 3)
            self.assertTrue(all(not path.exists() for path in runner.staged_scripts))
            warnings = " ".join(event.message for event in events if event.level == "WARNING")
            self.assertIn("shared global UI", warnings)
            self.assertIn("Runtime visibility is unproved", warnings)
            self.assertIn("not production-quality", warnings)

    def test_provider_pins_all_owning_modules_source_and_registry_contract(self) -> None:
        expected = {
            "tools/apf_inner.py",
            "tools/apf_outer.py",
            "tools/apf_texture_patch.py",
            "tools/apf_xenos_dxt5a.py",
            "tools/apf_digital_font_layout.py",
            "tools/apf_digital_font_transport.py",
            "tools/apf_digital_font_patch.py",
            "tools/apf_digital_font_verify.py",
            "mod_editor/apf_digital_font_recipe.schema.json",
            "reports/specs/apf_digital_font_asset_format.v1.json",
        }
        self.assertEqual(set(Apf2k8DigitalFontProvider.module_pins), expected)
        for relative, digest in Apf2k8DigitalFontProvider.module_pins.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = font_request(root)
            provider = Apf2k8DigitalFontProvider(
                source_hasher=lambda _path, _progress: (
                    Apf2k8DigitalFontProvider.source_sha256,
                    Apf2k8DigitalFontProvider.source_size,
                ),
                workspace=ROOT,
            )
            capability = font_capability()
            capability.raw["selectors"]["fields"][0]["allowed"] = "any font"
            with self.assertRaises(ProviderError):
                provider.preflight(request, capability, lambda _event: None)

            provider.module_pins = {
                **Apf2k8DigitalFontProvider.module_pins,
                Apf2k8DigitalFontProvider.backend_module: "0" * 64,
            }
            with self.assertRaisesRegex(ProviderError, "hash changed"):
                provider.preflight(request, font_capability(), lambda _event: None)

    def test_provider_rejects_hardlinked_pins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            owner = tools / "owner.py"
            owner.write_text("VALUE = 1\n", encoding="utf-8")
            pinned = tools / "pinned.py"
            os.link(owner, pinned)
            digest = hashlib.sha256(pinned.read_bytes()).hexdigest()
            provider = Apf2k8DigitalFontProvider(workspace=workspace)
            with self.assertRaisesRegex(ProviderError, "single-link"):
                provider._read_pinned("tools/pinned.py", digest)

    def test_provider_rejects_escaping_symlink_parent_and_oversized_pins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            outside = Path(temporary) / "outside"
            outside.mkdir()
            payload = outside / "pinned.py"
            payload.write_text("VALUE = 1\n", encoding="utf-8")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            (workspace / "linked-tools").symlink_to(outside, target_is_directory=True)
            provider = Apf2k8DigitalFontProvider(workspace=workspace)

            with self.assertRaisesRegex(ProviderError, "workspace-relative"):
                provider._read_pinned("../outside/pinned.py", digest)
            with self.assertRaisesRegex(ProviderError, "non-symlink directory"):
                provider._read_pinned("linked-tools/pinned.py", digest)

            tools = workspace / "tools"
            tools.mkdir()
            bounded = tools / "bounded.py"
            bounded.write_bytes(b"12345")
            provider.max_pinned_file_bytes = 4
            with self.assertRaisesRegex(ProviderError, "bounded single-link"):
                provider._read_pinned(
                    "tools/bounded.py", hashlib.sha256(b"12345").hexdigest()
                )

    def test_staged_execution_does_not_import_mutated_repo_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            tools = workspace / "tools"
            tools.mkdir()
            main = tools / "main.py"
            helper = tools / "helper.py"
            main.write_text("import helper\nprint(helper.VALUE)\n", encoding="utf-8")
            helper.write_text("VALUE = 'staged'\n", encoding="utf-8")

            class MutatingRunner:
                def run(self, argv, cwd, stage, emit):
                    helper.write_text("VALUE = 'mutated-repo'\n", encoding="utf-8")
                    return SubprocessCommandRunner().run(argv, cwd, stage, emit)

            provider = Apf2k8DigitalFontProvider(
                runner=MutatingRunner(), workspace=workspace
            )
            provider.module_pins = {
                "tools/helper.py": hashlib.sha256(helper.read_bytes()).hexdigest(),
                "tools/main.py": hashlib.sha256(main.read_bytes()).hexdigest(),
            }
            result = provider._run_pinned_module(
                "tools/main.py", (), ProviderStage.VALIDATE, lambda _event: None
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "staged")
            self.assertIn("mutated-repo", helper.read_text(encoding="utf-8"))

    def test_verifier_remains_independent_of_writer_and_recipe_modules(self) -> None:
        source = (ROOT / "tools/apf_digital_font_verify.py").read_text(encoding="utf-8")
        for forbidden in (
            "import apf_digital_font_patch",
            "import apf_digital_font_transport",
            "import apf_digital_font_layout",
            "import apf_xenos_dxt5a",
            "import mod_editor",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

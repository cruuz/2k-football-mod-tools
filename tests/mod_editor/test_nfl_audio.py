"""Focused tests for the fixed NFL 2K5 menu-back audio recipe."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

from mod_editor.__main__ import main as editor_main
# Kernel write-seals are read through platform_compat, never through a
# module-scope ``import fcntl``: that import does not exist on Windows and made
# this whole file unimportable there, which is the exact portability bug
# platform_compat was added to remove.  read_seals()/write_seal_mask() are the
# same two fcntl calls on POSIX -- byte for byte -- and fail closed elsewhere.
from mod_editor.core.platform_compat import (
    read_seals,
    supports_sealed_memfd,
    write_seal_mask,
)
from mod_editor.core.errors import OutputRefusedError
from mod_editor.core.capabilities import Capability, Classification
from mod_editor.core.model import GameId, SourceRecord
from mod_editor.core.nfl_audio import (
    NFL_MENU_BACK_AUDIO_FRAME_COUNT,
    NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA,
    NFL_MENU_BACK_AUDIO_TARGET,
    NflAudioRecipeError,
    canonical_nfl_audio_recipe_json,
    create_nfl_menu_back_audio_recipe,
    load_nfl_menu_back_audio_recipe,
)
from mod_editor.core.nfl_audio_provider import Nfl2k5MenuBackAudioProvider
from mod_editor.core.providers import (
    ProviderCommandResult,
    ProviderError,
    ProviderRequest,
    ProviderStage,
)
from tests.mod_editor.test_gui import _app_with_selected

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import nfl_audo_wav_xiso_verify as audio_verify  # noqa: E402


def make_wav(
    path: Path,
    *,
    channels: int = 1,
    sample_rate: int = 16_000,
    sample_width: int = 2,
    frame_count: int = NFL_MENU_BACK_AUDIO_FRAME_COUNT,
) -> Path:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(sample_width)
        stream.setframerate(sample_rate)
        frame = b"\0" * (channels * sample_width)
        stream.writeframes(frame * frame_count)
    return path


def audio_capability() -> Capability:
    provider = Nfl2k5MenuBackAudioProvider
    raw = {
        "classification": Classification.OFFLINE_WRITER_PROVED.value,
        "backend": {
            "command": provider.backend_command,
            "module": provider.backend_module,
            "operation": "write",
        },
        "gui": {
            "default_enabled": True,
            "expose": True,
            "mode": "edit",
            "reason": "fixed writer",
        },
        "selectors": {
            "fields": [
                {"allowed": NFL_MENU_BACK_AUDIO_TARGET, "name": "target", "required": True}
            ],
            "notes": "fixed target",
        },
        "source_container": {"hash_pins": [provider.source_sha256]},
    }
    return Capability(
        capability_id="nfl2k5.audio.menu_back_wav",
        game=GameId.NFL2K5,
        surface="audio",
        classification=Classification.OFFLINE_WRITER_PROVED,
        title="NFL 2K5 fixed menu-back WAV writer",
        category="Audio",
        summary="fixed slot",
        accepted_extensions=(".wav",),
        raw=raw,
    )


class FakeAudioRunner:
    def __init__(self, output: Path):
        self.output = output
        self.calls: list[tuple[tuple[str, ...], Path, ProviderStage]] = []
        self.archives: dict[ProviderStage, dict[str, bytes]] = {}
        self.archive_seals: dict[ProviderStage, int] = {}

    def run(self, argv, cwd, stage, emit):
        fixed = tuple(os.fspath(value) for value in argv)
        self.calls.append((fixed, Path(cwd), stage))
        archive_path = Path(fixed[4])
        with zipfile.ZipFile(archive_path) as archive:
            self.archives[stage] = {
                name: archive.read(name) for name in sorted(archive.namelist())
            }
        # The provider only applies memfd write-seals on Linux; on a host without
        # them it stages the snapshot as a verified read-only file (no seals to
        # read). Recording seals there would call the Linux-only F_GET_SEALS.
        if supports_sealed_memfd():
            descriptor = os.open(archive_path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
            try:
                self.archive_seals[stage] = read_seals(descriptor)
            finally:
                os.close(descriptor)
        else:
            self.archive_seals[stage] = 0
        if stage == ProviderStage.BUILD:
            stdout = json.dumps({
                "changed_bytes": 3000,
                "output": str(self.output.resolve()),
                "runtime": False,
                "schema": Nfl2k5MenuBackAudioProvider.backend_schema,
                "sha256": "a" * 64,
            }) + "\n"
        else:
            stdout = "NFL2K5_AUDO_WAV_XISO_VERIFY_PASS changed_bytes=3000 runtime=false\n"
        return ProviderCommandResult(fixed, 0, stdout, "")


def make_provider_request(root: Path) -> tuple[ProviderRequest, Path]:
    wav = make_wav(root / "menu-back.wav")
    recipe = root / "recipe.json"
    create_nfl_menu_back_audio_recipe(
        output=recipe, purpose="typed provider test", wav=wav
    )
    source_path = root / "retail.xiso.iso"
    source_path.write_bytes(b"fixture")
    source = SourceRecord(
        selected_path=str(source_path),
        inspected_path=str(source_path),
        kind="xiso",
        sha256=Nfl2k5MenuBackAudioProvider.source_sha256,
        size=Nfl2k5MenuBackAudioProvider.source_size,
        recognized=True,
        fingerprint_id="nfl2k5-usa-retail-xiso",
        detected_game=GameId.NFL2K5.value,
    )
    return (
        ProviderRequest(
            capability_id="nfl2k5.audio.menu_back_wav",
            game=GameId.NFL2K5,
            backend_project=recipe,
            source=source,
            output_xiso=root / "output.xiso.iso",
            manifest=root / "output.manifest.json",
            artifact_dir=root / "output.artifacts",
        ),
        wav,
    )


def copy_provider_pins(destination: Path) -> None:
    provider = Nfl2k5MenuBackAudioProvider(workspace=ROOT)
    relatives = {
        member[0]
        for closure in (provider._writer_members(), provider._verifier_members())
        for member in closure
    }
    relatives.add(provider.recipe_schema_file)
    for relative in sorted(relatives):
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, output)


class NflAudioRecipeTests(unittest.TestCase):
    def test_headless_cli_creates_fixed_audio_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = make_wav(root / "menu-back.wav")
            output = root / "menu-back.recipe.json"
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                status = editor_main(
                    [
                        "--create-nfl-menu-back-audio-recipe",
                        str(output),
                        "--purpose",
                        "CLI fixed menu-back test",
                        "--audio-wav",
                        str(wav),
                    ]
                )

            self.assertEqual(status, 0)
            self.assertIn(
                "MOD_EDITOR_NFL_MENU_BACK_AUDIO_RECIPE_CREATED", stdout.getvalue()
            )
            loaded = load_nfl_menu_back_audio_recipe(output)
            self.assertEqual(loaded.purpose, "CLI fixed menu-back test")
            self.assertEqual(loaded.wav_path, wav.resolve())

    def test_gui_recipe_creator_collects_only_purpose_and_fixed_wav(self) -> None:
        app = _app_with_selected("nfl2k5.audio.menu_back_wav")
        app._refresh_queue = lambda: None
        app._refresh_project_label = lambda: None
        created = Path("/new/nfl2k5-menu-back-audio.json")
        with (
            patch(
                "mod_editor.gui.tkinter_app.simpledialog.askstring",
                return_value="GUI fixed menu-back test",
            ) as choose_purpose,
            patch(
                "mod_editor.gui.tkinter_app.filedialog.askopenfilename",
                return_value="/art/menu-back.wav",
            ) as choose_wav,
            patch(
                "mod_editor.gui.tkinter_app.filedialog.asksaveasfilename",
                return_value=str(created),
            ) as choose_recipe,
            patch(
                "mod_editor.gui.tkinter_app.create_nfl_menu_back_audio_recipe",
                return_value=created,
            ) as creator,
            patch.object(app.controller, "import_provider_project") as importer,
            patch("mod_editor.gui.tkinter_app.messagebox.showinfo"),
        ):
            app._create_provider_recipe()

        creator.assert_called_once_with(
            output=created,
            purpose="GUI fixed menu-back test",
            wav=Path("/art/menu-back.wav"),
        )
        importer.assert_called_once_with("nfl2k5.audio.menu_back_wav", created)
        self.assertIn("fixed menu-back_01", choose_purpose.call_args.args[1])
        self.assertIn("mono PCM16LE 16000 Hz", choose_wav.call_args.kwargs["title"])
        self.assertEqual(
            choose_recipe.call_args.kwargs["initialfile"],
            "nfl2k5-menu-back-audio.json",
        )

    def test_create_and_load_canonical_recipe_with_content_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = make_wav(root / "menu-back.wav")
            output = root / "menu-back.recipe.json"
            before = hashlib.sha256(wav.read_bytes()).hexdigest()

            result = create_nfl_menu_back_audio_recipe(
                output=output,
                purpose="Replace the fixed menu-back cue",
                wav=wav,
            )

            self.assertEqual(result, output.resolve())
            value = json.loads(output.read_bytes())
            self.assertEqual(
                value,
                {
                    "purpose": "Replace the fixed menu-back cue",
                    "schema": NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA,
                    "target": NFL_MENU_BACK_AUDIO_TARGET,
                    "wav": "menu-back.wav",
                    "wav_sha256": before,
                    "wav_size": len(wav.read_bytes()),
                },
            )
            self.assertEqual(output.read_bytes(), canonical_nfl_audio_recipe_json(value))
            loaded = load_nfl_menu_back_audio_recipe(output)
            self.assertEqual(loaded.recipe_path, output.resolve())
            self.assertEqual(loaded.wav_path, wav.resolve())
            self.assertEqual(loaded.wav_sha256, before)
            self.assertEqual(hashlib.sha256(wav.read_bytes()).hexdigest(), before)
            serialized = output.read_text(encoding="utf-8")
            for forbidden in ("offset", "outer_index", "chunk_index", "payload", "retail"):
                self.assertNotIn(forbidden, serialized)

    def test_create_rejects_non_pcm_shape_metadata_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid = make_wav(root / "valid.wav")
            cases: list[tuple[str, Path]] = [
                ("stereo", make_wav(root / "stereo.wav", channels=2)),
                ("rate", make_wav(root / "rate.wav", sample_rate=22_050)),
                ("width", make_wav(root / "width.wav", sample_width=1)),
                ("frames", make_wav(root / "frames.wav", frame_count=100)),
            ]
            metadata = root / "metadata.wav"
            payload = valid.read_bytes()
            extra = b"LIST" + struct.pack("<I", 4) + b"test"
            metadata.write_bytes(payload[:4] + struct.pack("<I", len(payload) + len(extra) - 8)
                                 + payload[8:] + extra)
            cases.append(("metadata", metadata))
            linked = root / "linked.wav"
            linked.symlink_to(valid)
            cases.append(("symlink", linked))
            wrong_suffix = root / "valid.bin"
            wrong_suffix.write_bytes(valid.read_bytes())
            cases.append(("suffix", wrong_suffix))

            for name, wav in cases:
                output = root / f"reject-{name}.json"
                with self.subTest(name=name), self.assertRaises(NflAudioRecipeError):
                    create_nfl_menu_back_audio_recipe(
                        output=output, purpose="invalid input", wav=wav
                    )
                self.assertFalse(os.path.lexists(output))

    def test_loader_rejects_tampering_noncanonical_fields_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = make_wav(root / "valid.wav")
            original = root / "original.json"
            create_nfl_menu_back_audio_recipe(output=original, purpose="test", wav=wav)
            base = json.loads(original.read_bytes())

            mutated = dict(base)
            mutated["target"] = "menu-forward_01"
            wrong_target = root / "wrong-target.json"
            wrong_target.write_bytes(canonical_nfl_audio_recipe_json(mutated))
            with self.assertRaises(NflAudioRecipeError):
                load_nfl_menu_back_audio_recipe(wrong_target)

            mutated = dict(base)
            mutated["raw_offset"] = 123
            extra = root / "extra.json"
            extra.write_bytes(canonical_nfl_audio_recipe_json(mutated))
            with self.assertRaises(NflAudioRecipeError):
                load_nfl_menu_back_audio_recipe(extra)

            noncanonical = root / "noncanonical.json"
            noncanonical.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaises(NflAudioRecipeError):
                load_nfl_menu_back_audio_recipe(noncanonical)

            mutated = dict(base)
            mutated["wav_size"] = True
            bool_size = root / "bool-size.json"
            bool_size.write_bytes(canonical_nfl_audio_recipe_json(mutated))
            with self.assertRaises(NflAudioRecipeError):
                load_nfl_menu_back_audio_recipe(bool_size)

            wav.write_bytes(wav.read_bytes()[:-2] + b"\x01\x02")
            with self.assertRaisesRegex(NflAudioRecipeError, "SHA-256"):
                load_nfl_menu_back_audio_recipe(original)

    def test_output_is_exclusive_and_failure_cleans_only_owned_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wav = make_wav(root / "valid.wav")
            existing = root / "existing.json"
            existing.write_text("mine", encoding="utf-8")
            with self.assertRaises(OutputRefusedError):
                create_nfl_menu_back_audio_recipe(output=existing, purpose="test", wav=wav)
            self.assertEqual(existing.read_text(encoding="utf-8"), "mine")

            broken = root / "broken.json"
            broken.symlink_to(root / "missing-target")
            with self.assertRaises(OutputRefusedError):
                create_nfl_menu_back_audio_recipe(output=broken, purpose="test", wav=wav)
            self.assertTrue(broken.is_symlink())

            absent_parent = root / "missing" / "recipe.json"
            with self.assertRaises(OutputRefusedError):
                create_nfl_menu_back_audio_recipe(
                    output=absent_parent, purpose="test", wav=wav
                )

            interrupted = root / "interrupted.json"
            with patch("mod_editor.core.nfl_audio.os.write", side_effect=OSError("injected")):
                with self.assertRaises(NflAudioRecipeError):
                    create_nfl_menu_back_audio_recipe(
                        output=interrupted, purpose="test", wav=wav
                    )
            self.assertFalse(os.path.lexists(interrupted))

    def test_schema_matches_fixed_named_contract(self) -> None:
        schema_path = Path(__file__).resolve().parents[2] / "mod_editor" / (
            "nfl_menu_back_audio_recipe.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema"]["const"], NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA)
        self.assertEqual(schema["properties"]["target"]["const"], NFL_MENU_BACK_AUDIO_TARGET)
        self.assertEqual(
            set(schema["required"]),
            {"schema", "purpose", "target", "wav", "wav_size", "wav_sha256"},
        )

    def test_independent_verifier_receipt_is_metadata_only_and_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact_dir = root / "verification"
            result = {
                "changed_bytes": 3000,
                "decoded_pcm_sha256": "1" * 64,
                "output_sha256": "2" * 64,
                "replacement_payload_sha256": "3" * 64,
                "rmse": 12.5,
            }

            report = audio_verify.write_artifact_dir(artifact_dir, result)

            self.assertEqual(report, artifact_dir / "verification.json")
            raw = report.read_bytes()
            value = json.loads(raw)
            self.assertEqual(raw, canonical_nfl_audio_recipe_json(value))
            self.assertEqual(value["schema"], audio_verify.ARTIFACT_SCHEMA)
            self.assertEqual(value["target"], {
                "chunk_index": 101,
                "name": "menu-back_01",
                "outer_index": 3,
            })
            self.assertTrue(value["result"]["independent_verifier"])
            self.assertFalse(value["result"]["runtime_visibility_proved"])
            serialized = raw.decode("utf-8")
            for forbidden in ("xiso bytes", "pcm bytes", "retail payload"):
                self.assertNotIn(forbidden, serialized.lower())
            with self.assertRaises(audio_verify.AudioVerifyError):
                audio_verify.write_artifact_dir(artifact_dir, result)

    def test_verifier_receipt_failure_removes_only_owned_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = {"changed_bytes": 1}
            broken = root / "broken"
            broken.symlink_to(root / "absent")
            with self.assertRaises(audio_verify.AudioVerifyError):
                audio_verify.write_artifact_dir(broken, result)
            self.assertTrue(broken.is_symlink())

            interrupted = root / "interrupted"
            with patch.object(audio_verify.os, "write", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    audio_verify.write_artifact_dir(interrupted, result)
            self.assertFalse(os.path.lexists(interrupted))

    def test_typed_provider_uses_fixed_writer_and_independent_verifier_argv(self) -> None:
        if not supports_sealed_memfd():
            self.skipTest(
                "this asserts the kernel write-seals on the provider's staged "
                "zipapp; memfd seals are a Linux primitive with no equivalent "
                "on macOS or Windows"
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, wav = make_provider_request(root)
            runner = FakeAudioRunner(request.output_xiso)
            provider = Nfl2k5MenuBackAudioProvider(
                runner=runner,
                source_hasher=lambda _path, _progress: (
                    Nfl2k5MenuBackAudioProvider.source_sha256,
                    Nfl2k5MenuBackAudioProvider.source_size,
                ),
                workspace=ROOT,
            )

            provider.preflight(request, audio_capability(), lambda _event: None)
            validation = provider.validate(request, audio_capability(), lambda _event: None)
            build = provider.build(request, audio_capability(), lambda _event: None)
            verify = provider.verify(request, audio_capability(), lambda _event: None)

            self.assertTrue(json.loads(validation.stdout)["recipe_valid"])
            self.assertEqual(build.returncode, verify.returncode, 0)
            self.assertEqual([stage for _, _, stage in runner.calls], [
                ProviderStage.BUILD,
                ProviderStage.VERIFY,
            ])
            build_argv, verify_argv = [call[0] for call in runner.calls]
            self.assertIn(str(wav.resolve()), build_argv)
            self.assertIn(str(request.artifact_dir.resolve()), verify_argv)
            self.assertEqual(build_argv[1:4], ("-I", "-B", "-S"))
            self.assertEqual(verify_argv[1:4], ("-I", "-B", "-S"))
            for argv in (build_argv, verify_argv):
                self.assertRegex(argv[4], rf"^/proc/{os.getpid()}/fd/[0-9]+$")
                self.assertNotIn("--offset", argv)
                self.assertNotIn("--outer", argv)
                self.assertNotIn("--chunk", argv)
                self.assertNotIn(os.fspath(ROOT), argv[4])
            self.assertEqual([cwd for _, cwd, _ in runner.calls], [Path("/"), Path("/")])
            # The write-seal assertion only applies where the provider actually
            # seals (Linux memfd); elsewhere it stages a verified read-only file,
            # already asserted by the rest of this test.
            if supports_sealed_memfd():
                required_seals = write_seal_mask()
                self.assertTrue(
                    all(value & required_seals == required_seals
                        for value in runner.archive_seals.values())
                )
            self.assertEqual(
                set(runner.archives[ProviderStage.BUILD]),
                {"__main__.py", "nfl_uniform_color_xiso_direct_patch.py"},
            )
            self.assertEqual(
                set(runner.archives[ProviderStage.VERIFY]),
                {"__main__.py", "nfl_team_identity_xiso_verify.py"},
            )
            self.assertEqual(
                hashlib.sha256(
                    runner.archives[ProviderStage.BUILD][
                        "nfl_uniform_color_xiso_direct_patch.py"
                    ]
                ).hexdigest(),
                provider.writer_dependency_module_sha256,
            )
            self.assertEqual(
                hashlib.sha256(
                    runner.archives[ProviderStage.VERIFY][
                        "nfl_team_identity_xiso_verify.py"
                    ]
                ).hexdigest(),
                provider.verifier_dependency_module_sha256,
            )

    def test_typed_provider_fails_closed_on_registry_or_module_pin_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request, _wav = make_provider_request(root)
            hasher = lambda _path, _progress: (
                Nfl2k5MenuBackAudioProvider.source_sha256,
                Nfl2k5MenuBackAudioProvider.source_size,
            )
            provider = Nfl2k5MenuBackAudioProvider(source_hasher=hasher, workspace=ROOT)
            bad = audio_capability()
            bad.raw["selectors"]["fields"][0]["allowed"] = "any AUDO"
            with self.assertRaises(ProviderError):
                provider.preflight(request, bad, lambda _event: None)

            altered_capabilities = []
            for mutate in (
                lambda raw: raw["backend"].__setitem__("command", "python3 forged.py"),
                lambda raw: raw["backend"].__setitem__("extra", True),
                lambda raw: raw.__setitem__(
                    "classification", Classification.RUNTIME_PROVED.value
                ),
            ):
                altered = audio_capability()
                mutate(altered.raw)
                altered_capabilities.append(altered)
            altered_capabilities.extend((
                replace(
                    audio_capability(),
                    classification=Classification.RUNTIME_PROVED,
                ),
                replace(audio_capability(), accepted_extensions=(".wav", ".bin")),
            ))
            for altered in altered_capabilities:
                with self.subTest(altered=altered):
                    with self.assertRaisesRegex(ProviderError, "does not authorize"):
                        provider.preflight(request, altered, lambda _event: None)

            for attribute in (
                "backend_module_sha256",
                "writer_dependency_module_sha256",
                "verifier_module_sha256",
                "verifier_dependency_module_sha256",
                "recipe_schema_file_sha256",
            ):
                with self.subTest(attribute=attribute):
                    provider = Nfl2k5MenuBackAudioProvider(
                        source_hasher=hasher, workspace=ROOT
                    )
                    setattr(provider, attribute, "0" * 64)
                    with self.assertRaisesRegex(ProviderError, "hash changed"):
                        provider.preflight(
                            request, audio_capability(), lambda _event: None
                        )

    def test_every_code_and_schema_pin_rejects_hardlinks(self) -> None:
        provider_type = Nfl2k5MenuBackAudioProvider
        pins = (
            provider_type.backend_module,
            provider_type.writer_dependency_module,
            provider_type.verifier_module,
            provider_type.verifier_dependency_module,
            provider_type.recipe_schema_file,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_root = root / "request"
            request_root.mkdir()
            request, _wav = make_provider_request(request_root)
            workspace = root / "workspace"
            workspace.mkdir()
            copy_provider_pins(workspace)
            hasher = lambda _path, _progress: (
                provider_type.source_sha256,
                provider_type.source_size,
            )

            for index, relative in enumerate(pins):
                with self.subTest(relative=relative):
                    alias = root / f"hardlink-{index}"
                    os.link(workspace / relative, alias)
                    try:
                        provider = provider_type(
                            source_hasher=hasher, workspace=workspace
                        )
                        with self.assertRaisesRegex(ProviderError, "single-link"):
                            provider.preflight(
                                request, audio_capability(), lambda _event: None
                            )
                    finally:
                        alias.unlink()

    def test_sealed_writer_and_verifier_closures_are_complete_and_importable(self) -> None:
        if not supports_sealed_memfd():
            self.skipTest(
                "kernel memfd write-seals are a Linux primitive; this provider "
                "seals its zipapp with them and has no equivalent elsewhere"
            )
        provider = Nfl2k5MenuBackAudioProvider(workspace=ROOT)
        required_seals = write_seal_mask()
        cases = (
            (
                "writer",
                provider._writer_members(),
                {
                    "__main__.py": provider.backend_module_sha256,
                    "nfl_uniform_color_xiso_direct_patch.py": (
                        provider.writer_dependency_module_sha256
                    ),
                },
            ),
            (
                "verifier",
                provider._verifier_members(),
                {
                    "__main__.py": provider.verifier_module_sha256,
                    "nfl_team_identity_xiso_verify.py": (
                        provider.verifier_dependency_module_sha256
                    ),
                },
            ),
        )
        for label, members, expected in cases:
            with self.subTest(label=label):
                with provider._sealed_zipapp(members, label) as module:
                    archive_path = module.path
                    # The memfd path's re-verify is a no-op but must stay callable.
                    module.reverify_before_exec()
                    self.assertRegex(
                        os.fspath(archive_path),
                        rf"^/proc/{os.getpid()}/fd/[0-9]+$",
                    )
                    descriptor = os.open(archive_path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                    try:
                        self.assertEqual(
                            read_seals(descriptor) & required_seals,
                            required_seals,
                        )
                    finally:
                        os.close(descriptor)
                    with self.assertRaises(OSError):
                        os.open(archive_path, os.O_WRONLY | getattr(os, "O_BINARY", 0))
                    with zipfile.ZipFile(archive_path) as archive:
                        self.assertEqual(archive.namelist(), list(expected))
                        for name, expected_hash in expected.items():
                            self.assertEqual(
                                hashlib.sha256(archive.read(name)).hexdigest(),
                                expected_hash,
                            )
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-B",
                            "-S",
                            os.fspath(archive_path),
                            "--help",
                        ],
                        cwd="/",
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        shell=False,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertIn("usage:", completed.stdout)
                self.assertFalse(os.path.exists(archive_path))

    def test_hash_update_cannot_hide_an_unpinned_external_import(self) -> None:
        provider_type = Nfl2k5MenuBackAudioProvider
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_root = root / "request"
            request_root.mkdir()
            request, _wav = make_provider_request(request_root)
            workspace = root / "workspace"
            workspace.mkdir()
            copy_provider_pins(workspace)
            writer = workspace / provider_type.backend_module
            writer.write_bytes(writer.read_bytes() + b"\nimport unpinned_audio_owner\n")
            provider = provider_type(
                source_hasher=lambda _path, _progress: (
                    provider_type.source_sha256,
                    provider_type.source_size,
                ),
                workspace=workspace,
            )
            provider.backend_module_sha256 = hashlib.sha256(writer.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ProviderError, "external import closure changed"):
                provider.preflight(request, audio_capability(), lambda _event: None)

    def test_hash_update_cannot_enable_dynamic_import_or_code_loading(self) -> None:
        provider_type = Nfl2k5MenuBackAudioProvider
        injections = (
            b"\nfrom importlib import import_module\nimport_module('unowned')\n",
            b"\nexec(compile('VALUE = 1', '<dynamic>', 'exec'))\n",
        )
        for index, injection in enumerate(injections):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace = root / "workspace"
                workspace.mkdir()
                copy_provider_pins(workspace)
                writer = workspace / provider_type.backend_module
                writer.write_bytes(writer.read_bytes() + injection)
                provider = provider_type(workspace=workspace)
                provider.backend_module_sha256 = hashlib.sha256(
                    writer.read_bytes()
                ).hexdigest()
                with self.assertRaisesRegex(
                    ProviderError, "dynamic (?:import/code loader|loader module)"
                ):
                    provider._load_closure(provider._writer_members())

    def test_build_rechecks_live_pins_then_executes_only_sealed_snapshot(self) -> None:
        provider_type = Nfl2k5MenuBackAudioProvider
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_root = root / "request"
            request_root.mkdir()
            request, _wav = make_provider_request(request_root)
            workspace = root / "workspace"
            workspace.mkdir()
            copy_provider_pins(workspace)
            hasher = lambda _path, _progress: (
                provider_type.source_sha256,
                provider_type.source_size,
            )
            rejected_runner = FakeAudioRunner(request.output_xiso)
            provider = provider_type(
                runner=rejected_runner, source_hasher=hasher, workspace=workspace
            )
            provider.preflight(request, audio_capability(), lambda _event: None)
            dependency = workspace / provider.writer_dependency_module
            dependency.write_bytes(dependency.read_bytes() + b"\n# changed before build\n")
            with self.assertRaisesRegex(ProviderError, "hash changed"):
                provider.build(request, audio_capability(), lambda _event: None)
            self.assertEqual(rejected_runner.calls, [])

        class MutatingRunner(FakeAudioRunner):
            def __init__(self, output: Path, mutable_writer: Path):
                super().__init__(output)
                self.mutable_writer = mutable_writer

            def run(self, argv, cwd, stage, emit):
                if stage == ProviderStage.BUILD:
                    self.mutable_writer.write_text(
                        "raise RuntimeError('mutable repository path executed')\n",
                        encoding="utf-8",
                    )
                return super().run(argv, cwd, stage, emit)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_root = root / "request"
            request_root.mkdir()
            request, _wav = make_provider_request(request_root)
            workspace = root / "workspace"
            workspace.mkdir()
            copy_provider_pins(workspace)
            writer = workspace / provider_type.backend_module
            runner = MutatingRunner(request.output_xiso, writer)
            provider = provider_type(
                runner=runner,
                source_hasher=lambda _path, _progress: (
                    provider_type.source_sha256,
                    provider_type.source_size,
                ),
                workspace=workspace,
            )
            provider.preflight(request, audio_capability(), lambda _event: None)
            result = provider.build(request, audio_capability(), lambda _event: None)
            self.assertEqual(result.returncode, 0)
            self.assertNotEqual(
                hashlib.sha256(writer.read_bytes()).hexdigest(),
                provider.backend_module_sha256,
            )
            self.assertEqual(
                hashlib.sha256(
                    runner.archives[ProviderStage.BUILD]["__main__.py"]
                ).hexdigest(),
                provider.backend_module_sha256,
            )
            self.assertNotIn(os.fspath(workspace), result.argv[4])


if __name__ == "__main__":
    unittest.main()

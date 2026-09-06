from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
INSTALLER_PATH = ROOT / "packaging/apf2k8_mod_studio_installer.py"
SPEC = importlib.util.spec_from_file_location("_apf2k8_installer_tested", INSTALLER_PATH)
assert SPEC is not None and SPEC.loader is not None
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)


def _release_entries() -> tuple[str, ...]:
    values: list[str] = []
    for raw in (ROOT / "packaging/apf2k8-release-allowlist.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            values.append(line)
    return tuple(values)


def _stage_release(destination: Path) -> None:
    for relative in _release_entries():
        parts = PurePosixPath(relative).parts
        source = ROOT.joinpath(*parts)
        target = destination.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target, follow_symlinks=False)
        source_mode = source.stat(follow_symlinks=False).st_mode
        target.chmod(0o755 if source_mode & stat.S_IXUSR else 0o644)


def _launcher_python() -> str:
    """Return the interpreter the shipped Linux launcher actually uses.

    Pytest is often installed in an isolated virtual environment that does not
    inherit distro packages such as PyQt5.  The product launcher deliberately
    executes the system ``python3`` after checking those distro dependencies,
    so using ``sys.executable`` here would test the runner rather than the
    installed application.  Windows has a separate bundled-runtime installer.
    """

    if os.name != "nt":
        executable = shutil.which("python3")
        if executable is not None:
            return executable
    return sys.executable


@unittest.skipIf(
    os.name == "nt",
    "the per-user XDG installer is POSIX-only; Windows ships the NSIS installer",
)
class ReleaseClosureTests(unittest.TestCase):
    def test_literal_local_import_gate_catches_a_lazy_missing_module(self) -> None:
        gate_path = ROOT / "packaging/check_apf2k8_mod_studio_runtime.py"
        spec = importlib.util.spec_from_file_location(
            "_apf_runtime_import_closure_test", gate_path
        )
        assert spec is not None and spec.loader is not None
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        with tempfile.TemporaryDirectory(prefix="apf-lazy-import-closure-") as temporary:
            stage = Path(temporary)
            feature = stage / "mod_editor/apf_studio/feature.py"
            feature.parent.mkdir(parents=True)
            feature.write_text(
                "def on_click():\n"
                "    from mod_editor.core.shipped_only_in_source import value\n"
                "    return value\n",
                encoding="utf-8",
            )
            original_root = gate.ROOT
            gate.ROOT = stage
            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "feature.py:2 imports missing local module "
                    "mod_editor.core.shipped_only_in_source",
                ):
                    gate._check_literal_product_import_closure()
            finally:
                gate.ROOT = original_root

    def test_apf_stage_has_no_dependency_on_the_mixed_2k5_research_module(self) -> None:
        entries = set(_release_entries())
        self.assertNotIn(
            "mod_editor/core/playbook_package_rule_spike.py",
            entries,
        )
        for relative in (
            "mod_editor/apf_studio/facade.py",
            "mod_editor/apf_studio/playbook_membership_qt.py",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("playbook_package_rule_spike", text)

    def test_external_xma1_bridge_is_in_the_retail_free_runtime_closure(self) -> None:
        entries = set(_release_entries())
        self.assertTrue(
            {
                "docs/mod_editor/apf2k8_external_xma1_encoder.md",
                "mod_editor/apf_studio/audio_encoding.py",
            }.issubset(entries)
        )
        runtime = (
            ROOT / "packaging/check_apf2k8_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        for marker in (
            '"mod_editor.apf_studio.audio_encoding"',
            "_exercise_external_xma1_bridge(modules)",
            '"apf2k8_audio_pcm16_template/v1"',
            '"encoded_pending_exact_slot_validation"',
            '"bridge_reads_loaded_game"',
            '"bridge_passes_loaded_game_path"',
            '"encoder_input_is_user_selected_pcm"',
            '"synthetic PCM copy was mistaken for encoder-compatible XMA1"',
            '"replace_audio_from_pcm"',
        ):
            self.assertIn(marker, runtime)

    def test_audio_replacement_pack_is_in_the_retail_free_runtime_closure(self) -> None:
        entries = set(_release_entries())
        self.assertIn(
            "mod_editor/apf_studio/audio_replacement_pack.py",
            entries,
        )
        runtime = (
            ROOT / "packaging/check_apf2k8_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        for marker in (
            '"mod_editor.apf_studio.audio_replacement_pack"',
            '== "apf2k8_mod_studio_audio_replacement_pack/v1"',
            '== "apf2k8_mod_studio_audio_target_baseline/v1"',
            "audio_replacement_pack.MAX_PACK_ENTRIES == 47_775",
            "audio_replacement_pack.TEMPLATE_PAYLOADS_INCLUDED is False",
            '"wav_flac_input_supported": False',
            '"validated_count", "was_cancelled"',
            '"baseline_sha256"',
            '"active_modifications"',
            '"root_identity", "payload_directory_identity"',
            '"file_identity"',
            '"content_sha256"',
            '"read_audio_replacement_payload"',
            '"progress", "cancel_requested"',
            '"_cancel_running_audio_import"',
            "AudioReplacementPreviewReceipt",
            '"confirmation_token"',
            '"preview_audio_replacement_pack"',
            "fully_validated_read_only_preview_then_explicit_apply",
            "audio_replacement_confirmation=fully_validated_read_only_preview_then_explicit_apply",
            "audio_replacement_token=exact_member_result_source_session_project_revision",
            "audio_replacement_noop=cancel_unchanged",
            "audio_replacement_lifecycle=worker_drained_before_confirmation",
            "run_when_idle=self._run_when_idle",
            "self._idle_callbacks.append(callback)",
        ):
            self.assertIn(marker, runtime)

    def test_audio_gui_lifecycle_fences_are_in_the_runtime_closure(self) -> None:
        runtime = (
            ROOT / "packaging/check_apf2k8_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        for marker in (
            "_applied_audio_query_token",
            "_audio_query_controls_match_applied",
            "_cleared_audio_shortlist",
            "_audio_preview_request_is_current",
            "audio_query_lifecycle=applied_token_debounce_guarded",
            "audio_shortlist_clear=one_level_ordered_restore",
            "audio_preview_lifecycle=request_owned_success_failure",
            "audio_preview_cancellation=request_owned_process_group_cancel",
            "audio_waveform_cancellation=request_owned_process_group_cancel",
            "audio_add_all_matching=applied_query_atomic_256",
            "audio_session_teardown=cancel_drain_before_close_source",
            "shortlist_matching_button",
            "_matching_audio_cache_key",
            "_matching_audio_shortlist_additions",
            "_add_matching_audio_to_shortlist",
            "cancel_pending_audio_reads",
            "_cancel_transient_audio_reads",
            "_defer_source_load_until_idle",
            "_resume_pending_source_load",
            "_close_when_workers_finish",
            "run_cancellable_subprocess",
            "start_new_session=True",
        ):
            self.assertIn(marker, runtime)

    def test_token_preserving_roster_and_rating_editor_slice_is_declared(self) -> None:
        entries = set(_release_entries())
        self.assertTrue(
            {
                "docs/product/APF_PLAYER_RATINGS_TOKEN_PRESERVING_RUNTIME.md",
                "docs/product/APF_ROSTER_IDENTITY_TOKEN_PRESERVING_RUNTIME.md",
                "docs/product/APF_TRUE_099_PLAYER_RATINGS.md",
                "mod_editor/apf_studio/player_ratings.py",
                "mod_editor/apf_studio/player_positions.py",
                "mod_editor/data/apf2k8_player_ratings.v1.json",
                "mod_editor/data/apf2k8_player_positions.v1.json",
                "tools/apf_player_rating_patch.py",
                "tools/apf_player_position_patch.py",
                "tools/apf_roster_composite_patch.py",
                "tools/apf_roster_identity_patch.py",
            }.issubset(entries)
        )
        runtime = (
            ROOT / "packaging/check_apf2k8_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"mod_editor.apf_studio.player_ratings"', runtime)
        self.assertIn('"mod_editor.apf_studio.player_positions"', runtime)
        self.assertIn('"apf_player_rating_patch"', runtime)
        self.assertIn('"apf_player_position_patch"', runtime)
        self.assertIn("len(rating_schema.fields) == 31", runtime)
        self.assertIn(
            'rating_schema.runtime_status == "token_preserving_runtime_loaded"',
            runtime,
        )
        self.assertIn('"replace_roster_identity_text"', runtime)
        self.assertIn('"replace_player_base_rating"', runtime)
        self.assertIn('"replace_player_position"', runtime)
        self.assertIn('"player first/last names"', runtime)
        self.assertIn('"team abbreviations"', runtime)
        self.assertIn('"raw-save jersey"', runtime)
        self.assertIn('"membership"', runtime)
        self.assertIn("project.MAX_PROJECT_FILES == 131_072", runtime)
        self.assertIn(
            "project.MAX_PROJECT_MANIFEST_BYTES == 128 * 1024 * 1024",
            runtime,
        )
        self.assertIn(
            "project.MAX_REPLACEMENT_BYTES == 24 * 1024 * 1024",
            runtime,
        )
        self.assertIn(
            "project.MAX_PROJECT_ARCHIVE_BYTES == 2 * 1024 * 1024 * 1024",
            runtime,
        )
        self.assertIn(
            "project.MAX_PROJECT_EXPANDED_BYTES == 2 * 1024 * 1024 * 1024",
            runtime,
        )

    def test_alpha23_roster_planner_and_ausb_writer_closure_is_declared(self) -> None:
        entries = set(_release_entries())
        self.assertTrue(
            {
                "docs/product/APF_AUSB_EXACT_SLOT_FEASIBILITY.md",
                "mod_editor/apf_studio/roster_workspace.py",
                "mod_editor/apf_studio/roster_workspace_qt.py",
                "tools/apf_ausb_exact_slot.py",
            }.issubset(entries)
        )
        runtime = (
            ROOT / "packaging/check_apf2k8_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        for marker in (
            '"mod_editor.apf_studio.roster_workspace"',
            '"mod_editor.apf_studio.roster_workspace_qt"',
            '"apf_ausb_exact_slot"',
            "_check_ausb_feasibility_doc()",
            "_check_audio_packet_reuse_release_boundary(modules)",
            "ausb_exact_slot.EXPECTED_OWNER_ROW_COUNT == 45_514",
            "ausb_exact_slot.EXPECTED_CANONICAL_RANGE_COUNT == 45_513",
            "ausb_exact_slot.EXPECTED_UNIQUE_SOURCE_PAYLOAD_HASH_COUNT == 40_316",
            '"AUDO same-domain source packet"',
            '"AUDO cross-domain AUSB source packet"',
            '"AUSB same-domain source packet"',
            '"AUSB cross-domain AUDO source packet"',
            '"reuses a complete 0x800-byte audio packet"',
            "build_service._reject_any_source_audio_reuse(payload)",
            '"public build boundary accepted an exact',
            'ausb_binding.handler_id == "audio.ausb_exact_slot_editor"',
            "roster_workspace.MASTER_ROSTER_SLOTS == 53",
            'roster_workspace.FILE_EXTENSION == ".apf2k8roster"',
        ):
            self.assertIn(marker, runtime)

    def test_clean_allowlist_stage_passes_the_alpha32_runtime_gate(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="apf-alpha32-runtime-stage-"
        ) as temporary_name:
            stage = Path(temporary_name) / "release"
            stage.mkdir()
            _stage_release(stage)
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                    "QT_QPA_PLATFORM": "offscreen",
                }
            )
            result = subprocess.run(
                [
                    _launcher_python(),
                    str(stage / "packaging/check_apf2k8_mod_studio_runtime.py"),
                ],
                cwd=stage,
                env=environment,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("APF2K8_MOD_STUDIO_RUNTIME_PASS", result.stdout)

    def test_stadium_studio_source_closure_is_declared_without_derived_media(self) -> None:
        entries = set(_release_entries())
        self.assertTrue(
            {
                "mod_editor/apf_studio/stadium.py",
                "mod_editor/apf_studio/stadium_material_findings.py",
                "mod_editor/gui/stadium_viewer.py",
                "mod_editor/data/apf2k8_stadium_material_findings.v1.json",
                "tools/apf_scene.py",
            }.issubset(entries)
        )
        self.assertFalse(
            any(
                PurePosixPath(entry).suffix.casefold()
                in {".bin", ".glb", ".gltf", ".zip"}
                for entry in entries
            )
        )

    def test_stadium_material_findings_are_fail_closed_in_packaged_runtime(self) -> None:
        runtime = (
            ROOT / "packaging/check_apf2k8_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"mod_editor.apf_studio.stadium_material_findings"',
            runtime,
        )
        self.assertIn("load_stadium_material_findings()", runtime)
        self.assertIn(
            'material_findings.outcome == "embedded_texture_ownership_proved"',
            runtime,
        )
        self.assertIn(
            'material_findings.proof["texture_writer_safe_to_expose"] is True',
            runtime,
        )
        self.assertIn("STADIUM_MATERIAL_FINDINGS_SHA256", runtime)
        self.assertIn("len(registry.capabilities) == 149", runtime)


@unittest.skipIf(
    os.name == "nt",
    "the per-user XDG installer is POSIX-only; Windows ships the NSIS installer",
)
class PerUserPathTests(unittest.TestCase):
    def test_launcher_hands_its_exact_private_state_root_to_the_app(self) -> None:
        launcher = (
            ROOT / "tools/launch_apf2k8_mod_studio.sh"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'export APF2K8_MOD_STUDIO_STATE_DIR="$studio_state_dir"',
            launcher,
        )

    def test_paths_are_scoped_to_the_user(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-installer-paths-") as temporary_name:
            # Resolve the temp root so resolve_install_paths' canonical outputs
            # compare equal to ours under a symlinked (macOS /private/var) or
            # short-name (Windows) temp location.
            home = Path(temporary_name).resolve() / "home"
            home.mkdir()
            paths = installer.resolve_install_paths(
                {
                    "HOME": str(home),
                    "XDG_DATA_HOME": str(home / "custom data"),
                }
            )
            self.assertEqual(paths.app_dir, home / "custom data/apf2k8-mod-studio/app")
            self.assertEqual(paths.wrapper, home / ".local/bin/apf2k8-mod-studio")
            self.assertEqual(
                paths.desktop,
                home / "custom data/applications/apf2k8-mod-studio.desktop",
            )

    def test_system_xdg_destination_is_refused(self) -> None:
        with self.assertRaisesRegex(installer.InstallError, "system location"):
            installer.resolve_install_paths(
                {"HOME": "/home/synthetic-user", "XDG_DATA_HOME": "/usr/local/share"}
            )

    def test_desktop_exec_quotes_spaces_and_special_characters(self) -> None:
        template = (ROOT / "packaging/apf2k8-mod-studio.desktop").read_bytes()
        rendered = installer._render_desktop(
            template,
            Path('/home/test user/.local/bin/apf$2k8"studio'),
            "12345678-1234-1234-1234-123456789abc",
        ).decode("utf-8")
        self.assertIn('Exec="/home/test user/.local/bin/apf\\$2k8\\"studio"', rendered)
        self.assertIn("X-APF2K8-Mod-Studio-Managed=true", rendered)


@unittest.skipIf(
    os.name == "nt",
    "the per-user XDG installer is POSIX-only; Windows ships the NSIS installer",
)
class PerUserLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-installer-lifecycle-")
        self.root = Path(self.temporary.name)
        self.release = self.root / "release"
        self.release.mkdir()
        _stage_release(self.release)
        self.home = self.root / "home"
        self.home.mkdir()
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.home / "data"),
                "XDG_STATE_HOME": str(self.home / "state"),
            }
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_install_update_and_authenticated_uninstall(self) -> None:
        first = installer.install(self.release, environment=self.environment)
        self.assertEqual(first.action, "installed")
        paths = first.paths
        self.assertTrue(paths.app_dir.is_dir())
        self.assertTrue(paths.wrapper.is_file())
        self.assertTrue(paths.wrapper.stat().st_mode & stat.S_IXUSR)
        self.assertTrue(paths.desktop.is_file())
        self.assertTrue(paths.icon.is_file())
        for relative in (
            "docs/product/APF_AUSB_EXACT_SLOT_FEASIBILITY.md",
            "mod_editor/apf_studio/roster_workspace.py",
            "mod_editor/apf_studio/roster_workspace_qt.py",
            "tools/apf_ausb_exact_slot.py",
        ):
            self.assertTrue((paths.app_dir / relative).is_file(), relative)
        record = json.loads(paths.record.read_text(encoding="utf-8"))
        self.assertFalse(record["contains_retail_game_data"])
        self.assertTrue(record["preserves_user_data_on_uninstall"])
        self.assertIn(str(paths.app_dir / "tools/launch_apf2k8_mod_studio.sh"), paths.wrapper.read_text())
        self.assertIn(f'Exec="{paths.wrapper}"', paths.desktop.read_text(encoding="utf-8"))

        runtime_environment = self.environment.copy()
        runtime_environment.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONPATH": str(paths.app_dir),
                "QT_QPA_PLATFORM": "offscreen",
            }
        )
        installed_probe = (
            "import importlib,importlib.util,pathlib,sys;"
            "path=pathlib.Path('packaging/check_apf2k8_mod_studio_runtime.py').resolve();"
            "spec=importlib.util.spec_from_file_location('installed_apf_runtime_gate',path);"
            "gate=importlib.util.module_from_spec(spec);"
            "sys.modules[spec.name]=gate;"
            "spec.loader.exec_module(gate);"
            "modules={name:importlib.import_module(name) for name in gate.PRODUCT_MODULES};"
            "gate._check_audio_packet_reuse_release_boundary(modules);"
            "print('APF_AUDIO_PACKET_GATE_PASS')"
        )
        runtime_result = subprocess.run(
            [_launcher_python(), "-c", installed_probe],
            cwd=paths.app_dir,
            env=runtime_environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(runtime_result.returncode, 0, runtime_result.stderr)
        self.assertIn(
            "APF_AUDIO_PACKET_GATE_PASS",
            runtime_result.stdout,
        )

        second = installer.install(self.release, environment=self.environment)
        self.assertEqual(second.action, "updated")
        second_record = json.loads(paths.record.read_text(encoding="utf-8"))
        self.assertNotEqual(record["install_id"], second_record["install_id"])

        sentinels = (
            self.home / ".cache/apf2k8-mod-studio/user-preview",
            self.home / ".config/apf2k8-mod-studio/settings.json",
            self.home / "state/apf2k8-mod-studio/user-state",
            self.home / "Documents/my-project.apf2k8mod",
        )
        for sentinel in sentinels:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("preserve me\n", encoding="utf-8")

        paths.desktop.write_text(
            paths.desktop.read_text(encoding="utf-8") + "# user changed this shortcut\n",
            encoding="utf-8",
        )
        result = installer.uninstall(environment=self.environment)
        self.assertEqual(result.action, "uninstalled")
        self.assertTrue(any("Preserved changed desktop" in row for row in result.warnings))
        self.assertTrue(paths.desktop.exists())
        self.assertFalse(paths.app_dir.exists())
        self.assertFalse(paths.wrapper.exists())
        self.assertFalse(paths.icon.exists())
        self.assertFalse(paths.record.exists())
        self.assertTrue(all(path.exists() for path in sentinels))

    def test_unowned_command_collision_is_preserved(self) -> None:
        paths = installer.resolve_install_paths(self.environment)
        paths.wrapper.parent.mkdir(parents=True)
        paths.wrapper.write_text("unrelated user command\n", encoding="utf-8")
        with self.assertRaisesRegex(installer.InstallError, "unowned file"):
            installer.install(self.release, environment=self.environment)
        self.assertEqual(paths.wrapper.read_text(encoding="utf-8"), "unrelated user command\n")
        self.assertFalse(paths.app_dir.exists())


if __name__ == "__main__":
    unittest.main()

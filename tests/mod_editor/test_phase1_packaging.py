"""Focused tests for the retail-free 2K5 Mod Studio release-stage gate."""

from __future__ import annotations

import importlib.util
import hashlib
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "packaging/check_2k5_mod_studio_release.py"
SPEC = importlib.util.spec_from_file_location("release_gate", CHECKER)
assert SPEC is not None and SPEC.loader is not None
release_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_gate)


@unittest.skipIf(
    os.name == "nt",
    "POSIX inode/link-count release audit runs in the dedicated Linux gate",
)
class ModStudioPackagingTests(unittest.TestCase):
    def test_source_version_and_visible_product_label_are_pinned(self) -> None:
        package_source = (ROOT / "mod_editor/__init__.py").read_text(
            encoding="utf-8"
        )
        studio_source = (ROOT / "mod_editor/gui/studio_qt.py").read_text(
            encoding="utf-8"
        )
        version_assignments = [
            line for line in package_source.splitlines()
            if line.startswith("__version__ = ")
        ]
        self.assertEqual(version_assignments, ['__version__ = "1.0.0rc75"'])
        self.assertIn(
            'release_candidate = __version__.rsplit("rc", 1)[-1]',
            studio_source,
        )
        self.assertIn(
            'QLabel(f"v1.0 RC{release_candidate} • Xbox Edition")',
            studio_source,
        )
        getting_started = (
            ROOT / "docs/mod_editor/2k5_mod_studio_getting_started.md"
        ).read_text(encoding="utf-8")
        changelog = (
            ROOT / "docs/mod_editor/2k5_mod_studio_changelog.md"
        ).read_text(encoding="utf-8")
        packaging_readme = (ROOT / "packaging/README.md").read_text(
            encoding="utf-8"
        )
        status = (ROOT / "STATUS.md").read_text(encoding="utf-8")
        self.assertTrue(getting_started.startswith(
            "# 2K5 Mod Studio v1.0 RC75 — Getting Started"
        ))
        self.assertIn(
            "## v1.0 RC48 Audio Converter, Stadium Model Export, Update Check", changelog
        )
        self.assertIn("## v1.0 RC50", changelog)
        self.assertIn("## v1.0 RC69", changelog)
        self.assertIn("## v1.0 RC67", changelog)
        self.assertIn(
            "fully_validated_read_only_preview_then_explicit_apply",
            packaging_readme,
        )
        self.assertIn("registry has 70 cross-title rows", getting_started)
        self.assertIn("complete 12-tab sidebar", getting_started)
        self.assertIn("twelve-section desktop launch signature", packaging_readme)
        self.assertTrue(status.startswith(
            "# 2K5 Mod Studio — v1.0 RC75 Release Status"
        ))

    def _fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="2k5-release-gate-test-")
        root = Path(temporary.name) / "release"
        (root / "app").mkdir(parents=True)
        (root / "app/main.py").write_text("print('safe product code')\n", encoding="utf-8")
        allowlist = Path(temporary.name) / "allowlist.txt"
        allowlist.write_text("app/\napp/main.py\n", encoding="utf-8")
        return temporary, root, allowlist

    def test_accepts_declared_text_only_stage(self) -> None:
        temporary, root, allowlist = self._fixture()
        with temporary:
            report = release_gate.audit_release(root, allowlist)
        self.assertEqual(report["file_count"], 1)
        self.assertFalse(report["retail_payloads_included"])

    def test_refuses_known_private_host_paths_in_staged_text(self) -> None:
        for private_path in (
            "/home/noah/private-release-artifact",
            "/media/noah/Storage/private-game-dump",
        ):
            with self.subTest(private_path=private_path):
                temporary, root, allowlist = self._fixture()
                with temporary:
                    (root / "app/main.py").write_text(
                        f"LOCAL_PATH = {private_path!r}\n", encoding="utf-8"
                    )
                    with self.assertRaisesRegex(
                        release_gate.ReleaseCheckError, "private host path"
                    ):
                        release_gate.audit_release(root, allowlist)

    def test_allows_unrelated_portable_absolute_path_examples(self) -> None:
        temporary, root, allowlist = self._fixture()
        with temporary:
            (root / "app/main.py").write_text(
                "EXAMPLE_INSTALL = '/opt/2k5-mod-studio'\n", encoding="utf-8"
            )
            report = release_gate.audit_release(root, allowlist)
        self.assertEqual(report["file_count"], 1)

    def test_refuses_container_even_when_prefix_is_allowlisted(self) -> None:
        temporary, root, allowlist = self._fixture()
        with temporary:
            (root / "app/game.xiso").write_bytes(b"synthetic")
            with self.assertRaisesRegex(release_gate.ReleaseCheckError, "suffix is forbidden"):
                release_gate.audit_release(root, allowlist)

    def test_refuses_generated_stadium_gltf_even_when_allowlisted(self) -> None:
        temporary, root, allowlist = self._fixture()
        with temporary:
            (root / "app/stadium.gltf").write_text(
                '{"asset":{"version":"2.0"}}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(
                release_gate.ReleaseCheckError, "suffix is forbidden"
            ):
                release_gate.audit_release(root, allowlist)

    def test_refuses_extracted_tree_even_when_allowlisted(self) -> None:
        temporary, root, _allowlist = self._fixture()
        with temporary:
            (root / "extracted").mkdir()
            (root / "extracted/index.py").write_text("x = 1\n", encoding="utf-8")
            allowlist = Path(temporary.name) / "all.txt"
            allowlist.write_text("app/\napp/main.py\nextracted/\n", encoding="utf-8")
            with self.assertRaisesRegex(release_gate.ReleaseCheckError, "forbidden extracted"):
                release_gate.audit_release(root, allowlist)

    def test_refuses_undeclared_and_disguised_binary_files(self) -> None:
        temporary, root, allowlist = self._fixture()
        with temporary:
            (root / "app/extra.py").write_text("x = 1\n", encoding="utf-8")
            # app/ permits descendants, so the safe extra is accepted; an
            # unrelated directory is still outside the allowlist.
            (root / "other").mkdir()
            (root / "other/payload.json").write_bytes(b"XBEH\0retail-like")
            with self.assertRaisesRegex(release_gate.ReleaseCheckError, "undeclared release directory"):
                release_gate.audit_release(root, allowlist)

    def test_refuses_symlinks(self) -> None:
        temporary, root, allowlist = self._fixture()
        with temporary:
            (root / "app/link.py").symlink_to(root / "app/main.py")
            with self.assertRaisesRegex(release_gate.ReleaseCheckError, "symlinks are forbidden"):
                release_gate.audit_release(root, allowlist)

    def test_launcher_and_packaging_docs_require_pyqt5_not_tk(self) -> None:
        launcher = (ROOT / "tools/launch_2k5_mod_studio.sh").read_text(encoding="utf-8")
        readme = (ROOT / "packaging/README.md").read_text(encoding="utf-8")
        combined = launcher + "\n" + readme
        self.assertIn("from PyQt5 import QtWidgets; import PIL; import mod_editor", launcher)
        self.assertIn("python3 -m mod_editor --studio", combined)
        self.assertIn("python3-pyqt5", readme)
        self.assertNotIn("tkinter", combined.casefold())
        self.assertNotIn("python3-tk", combined.casefold())
        self.assertNotIn("python/tk/pillow", combined.casefold())
        self.assertNotRegex(combined, r"(?i)\btk(?:inter)?\b")

    def test_only_exact_reviewed_metadata_can_cross_reports_boundary(self) -> None:
        for relative in release_gate.REVIEWED_METADATA:
            self.assertIsNone(
                release_gate._forbidden_path(release_gate.PurePosixPath(relative))
            )
        arbitrary = release_gate.PurePosixPath("reports/assets/extra.json")
        self.assertEqual(release_gate._forbidden_path(arbitrary), "reports")
        private = release_gate.PurePosixPath(release_gate.PRIVATE_INVENTORY_PATH)
        self.assertEqual(release_gate._forbidden_path(private), "reports")

    def test_arbitrary_report_is_refused_even_when_manifest_names_it(self) -> None:
        temporary, root, _allowlist = self._fixture()
        with temporary:
            report = root / "reports/assets/unreviewed.json"
            report.parent.mkdir(parents=True)
            report.write_text('{"schema":"made-up/v1"}\n', encoding="utf-8")
            allowlist = Path(temporary.name) / "allowlist-with-report.txt"
            allowlist.write_text(
                "app/main.py\nreports/assets/unreviewed.json\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                release_gate.ReleaseCheckError,
                "forbidden extracted/build/local-data path component 'reports'",
            ):
                release_gate.audit_release(root, allowlist)

    def test_private_audio_origin_inventory_is_refused_by_name_or_schema(self) -> None:
        cases = (
            (
                "app/audio-source-pcm-fingerprints-v1.json",
                '{"schema":"safe-looking/v1"}\n',
                "inventory path",
            ),
            (
                "app/renamed-values.json",
                '{"schema":"2k5_mod_studio_audio_source_pcm_fingerprints/v1"}\n',
                "inventory schema",
            ),
            (
                "app/renamed-window-values.json",
                '{"schema":"2k5_mod_studio_audio_pcm_containment/v1"}\n',
                "inventory schema",
            ),
            (
                "app/renamed-quarter-window-values.json",
                '{"schema":"2k5_mod_studio_audio_pcm_containment/v2"}\n',
                "inventory schema",
            ),
        )
        for relative, payload, message in cases:
            with self.subTest(relative=relative):
                temporary, root, allowlist = self._fixture()
                with temporary:
                    path = root / relative
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaisesRegex(
                        release_gate.ReleaseCheckError, message
                    ):
                        release_gate.audit_release(root, allowlist)

    def test_private_derived_cache_tree_is_refused_under_allowed_prefix(self) -> None:
        temporary, root, allowlist = self._fixture()
        with temporary:
            derived = root / "app/derived"
            derived.mkdir()
            (derived / "inventory.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                release_gate.ReleaseCheckError,
                "forbidden extracted/build/local-data path component 'derived'",
            ):
                release_gate.audit_release(root, allowlist)

    def test_reviewed_metadata_files_match_exact_contract_and_have_no_payload(self) -> None:
        self.assertEqual(len(release_gate.REVIEWED_METADATA), 22)
        self.assertEqual(
            sum(path.startswith("reports/assets/")
                for path in release_gate.REVIEWED_METADATA),
            16,
        )
        for relative, (size, expected_sha, schema) in release_gate.REVIEWED_METADATA.items():
            path = ROOT / relative
            payload = path.read_bytes()
            self.assertEqual(len(payload), size)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected_sha)
            text = payload.decode("utf-8")
            document = release_gate.json.loads(text)
            self.assertEqual(document["schema"], schema)
            self.assertFalse(release_gate._metadata_contains_payload(document))

    def test_release_allowlist_has_scanner_and_metadata_but_not_private_inventory(self) -> None:
        allowlist_text = (ROOT / "packaging/release-allowlist.txt").read_text(
            encoding="utf-8"
        )
        entries = {
            line.strip() for line in allowlist_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertIn("tools/nfl_resource_scan.py", entries)
        self.assertIn("packaging/check_2k5_mod_studio_runtime.py", entries)
        self.assertIn("mod_editor/gui/studio_qt.py", entries)
        self.assertIn("mod_editor/gui/audio_waveform_qt.py", entries)
        self.assertIn("mod_editor/studio/facade.py", entries)
        self.assertIn("mod_editor/studio/audio_replacement_pack.py", entries)
        self.assertIn("mod_editor/studio/uniform_bundle.py", entries)
        self.assertIn("mod_editor/studio/workspace_state.py", entries)
        self.assertIn("mod_editor/core/apf_digital_font_provider.py", entries)
        self.assertIn("mod_editor/core/nfl2k5_stadium_cache.py", entries)
        self.assertIn("mod_editor/core/nfl2k5_stadium_texture_writer.py", entries)
        self.assertIn("mod_editor/core/nfl2k5_crib_geometry_writer.py", entries)
        self.assertIn(
            "mod_editor/core/nfl2k5_crib_standalone_texture_writer.py", entries
        )
        self.assertIn("mod_editor/core/nfl2k5_playbook_route_writer.py", entries)
        self.assertIn("mod_editor/core/nfl2k5_safe_text_banks.py", entries)
        self.assertIn("mod_editor/core/nfl2k5_audo_fixed_slots.py", entries)
        self.assertIn(
            "mod_editor/core/nfl2k5_audio_containment_fingerprints.py", entries
        )
        self.assertIn(
            "mod_editor/core/nfl2k5_audio_origin_authorization.py", entries
        )
        self.assertIn(
            "mod_editor/core/nfl2k5_audio_origin_preparation.py", entries
        )
        self.assertIn(
            "mod_editor/core/nfl2k5_audio_source_containment.py", entries
        )
        self.assertIn(
            "mod_editor/core/nfl2k5_audio_source_fingerprints.py", entries
        )
        self.assertIn(
            "mod_editor/core/nfl2k5_audio_source_scan.py", entries
        )
        self.assertIn("mod_editor/core/nfl2k5_ausb_build_adapter.py", entries)
        self.assertIn("mod_editor/core/nfl2k5_ausb_fixed_slots.py", entries)
        self.assertIn("mod_editor/core/nfl2k5_playbook_inspector.py", entries)
        self.assertIn("mod_editor/gui/gameplay_panel_qt.py", entries)
        self.assertIn("mod_editor/gui/menus_panel_qt.py", entries)
        self.assertIn("mod_editor/gui/playbooks_panel_qt.py", entries)
        self.assertIn("tools/nfl_stadium_studio_cache.py", entries)
        self.assertIn("tools/nfl_crib_bar_monitor_png_xiso.py", entries)
        self.assertIn("tools/string_table_inventory.py", entries)
        self.assertIn("tools/apf_inner.py", entries)
        self.assertIn("tools/apf_outer.py", entries)
        self.assertIn("mod_editor/data/nfl2k5_crib_catalog.v1.json", entries)
        self.assertIn(
            "mod_editor/data/nfl2k5_gameplay_inspection.v1.json", entries
        )
        self.assertIn(
            "mod_editor/data/nfl2k5_main_menu_inspection.v1.json", entries
        )
        self.assertIn("docs/mod_editor/2k5_mod_studio_getting_started.md", entries)
        self.assertIn("docs/mod_editor/2k5_mod_studio_changelog.md", entries)
        self.assertTrue(set(release_gate.REVIEWED_METADATA) <= entries)
        self.assertNotIn(release_gate.PRIVATE_INVENTORY_PATH, entries)
        self.assertNotIn("mod_editor/", entries)
        self.assertNotIn("tools/", entries)
        self.assertFalse(any(entry.endswith("/") for entry in entries))

    def test_clean_runtime_probe_uses_product_registry_mode(self) -> None:
        runtime_probe = (
            ROOT / "packaging/check_2k5_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn("allow_sample_fallback=False", runtime_probe)
        self.assertIn("check_files=False", runtime_probe)
        self.assertIn("sys.dont_write_bytecode = True", runtime_probe)
        self.assertIn("os.chdir(ROOT)", runtime_probe)
        self.assertIn("build_nfl2k5_product_catalog", runtime_probe)
        self.assertIn("extended_visual_catalog: object", runtime_probe)
        self.assertIn('"mod_editor.studio.workspace_state"', runtime_probe)
        self.assertIn('"mod_editor.studio.audio_replacement_pack"', runtime_probe)
        self.assertIn("_exercise_audio_replacement_pack_v2", runtime_probe)
        self.assertIn("AUDIO_REPLACEMENT_PACK_V2_SCHEMA", runtime_probe)
        self.assertIn(
            "audio_replacement_pack_v2=selected_mixed", runtime_probe
        )
        self.assertIn("_exercise_audio_replacement_pack_v3", runtime_probe)
        self.assertIn("AUDIO_REPLACEMENT_PACK_V3_SCHEMA", runtime_probe)
        self.assertIn(
            "audio_replacement_pack_v3=all_standalone_850", runtime_probe
        )
        self.assertIn("AUDIO_REPLACEMENT_PACK_V4_SCHEMA", runtime_probe)
        self.assertIn("AUDIO_CUE_MAP_SCHEMA", runtime_probe)
        self.assertIn(
            "audio_replacement_pack_v4=all_standalone_850_mapped",
            runtime_probe,
        )
        self.assertIn(
            "AUDIO_REPLACEMENT_PREFLIGHT_CONTRACT", runtime_probe
        )
        self.assertIn(
            "fully_validated_read_only_preview_then_explicit_apply",
            runtime_probe,
        )
        self.assertIn(
            "_exercise_audio_replacement_preflight_contract", runtime_probe
        )
        self.assertIn("RC29_AUDIO_ANNOTATION_RUNTIME_PINS", runtime_probe)
        for relative in (
            "mod_editor/gui/audio_panel_qt.py",
            "mod_editor/gui/studio_qt.py",
            "mod_editor/studio/audio_annotations.py",
            "mod_editor/studio/audio_replacement_pack.py",
            "mod_editor/studio/facade.py",
            "mod_editor/studio/project_archive.py",
            "mod_editor/studio/session.py",
        ):
            self.assertIn(relative, runtime_probe)
        self.assertIn(
            "audio_pack_import=validated_preview_token_apply", runtime_probe
        )
        self.assertIn("mutation_revision", runtime_probe)
        self.assertIn("confirmation_token=token", runtime_probe)
        self.assertIn("audio_pack_path_lookup=canonical_850", runtime_probe)
        self.assertIn("audio_meaning_confidence=1_152_697", runtime_probe)
        self.assertIn("audio_add_all_matching=bounded_256", runtime_probe)
        self.assertIn("_exercise_playable_audio_catalog", runtime_probe)
        self.assertIn("EXPECTED_PLAYABLE_AUDIO_COUNT == 54_421", runtime_probe)
        self.assertIn('PLAYABLE_AUDIO_SCOPE_ID == "playable"', runtime_probe)
        self.assertIn("PLAYABLE_AUDIO_FAMILIES == (", runtime_probe)
        self.assertIn(
            "AUDIO_PLAYABLE_DEFAULT_SCOPE_CONTRACT", runtime_probe
        )
        self.assertIn(
            "default_mixed_54421_standalone_then_streaming_ranges",
            runtime_probe,
        )
        self.assertIn(
            "audio_default_scope=playable_54421_standalone_then_ranges",
            runtime_probe,
        )
        self.assertIn(
            "audio_detail_layout=scrollable_pinned_actions", runtime_probe
        )
        self.assertIn("audio_toolbar_layout=two_row_930", runtime_probe)
        self.assertIn(
            "audio_preview_lifecycle=selection_source_epoch_owned_process",
            runtime_probe,
        )
        self.assertIn(
            "audio_query_lifecycle=applied_token_debounce_guarded", runtime_probe
        )
        self.assertIn(
            "audio_shortlist_clear=one_level_ordered_restore", runtime_probe
        )
        self.assertIn(
            "audio_source_failure=transactional_old_catalog_restore", runtime_probe
        )
        self.assertIn(
            "audio_waveform=explicit_read_only_session_wav", runtime_probe
        )
        self.assertIn(
            "audio_media_invalidation=selection_source_content_owned",
            runtime_probe,
        )
        self.assertIn(
            "embedded_audio_task=global_action_guarded_until_drain",
            runtime_probe,
        )
        self.assertIn(
            "embedded_operation_task=audio_crib_mutually_exclusive_until_drain",
            runtime_probe,
        )
        self.assertIn("_exercise_audio_waveform", runtime_probe)
        self.assertIn('"mod_editor.gui.audio_waveform_qt"', runtime_probe)
        self.assertIn(
            "audio_bundle_modified_range=user_wav", runtime_probe
        )
        self.assertIn(
            'content_origin="user_replacement"', runtime_probe
        )
        self.assertIn(
            'expected in str(exc), "streaming collection refusal changed"',
            runtime_probe,
        )
        self.assertIn('"mod_editor.studio.uniform_bundle"', runtime_probe)
        self.assertIn("_exercise_team_kit", runtime_probe)
        self.assertIn("_exercise_workspace_recovery", runtime_probe)
        self.assertIn("registry=70 sections=12 nfl2k5_capabilities=32", runtime_probe)
        self.assertIn("stadium_textures_editable=23838", runtime_probe)
        self.assertIn("audio=850 audio_editable=850 audio_export_only=0", runtime_probe)
        self.assertIn("audio_streaming_ranges=53571", runtime_probe)
        self.assertIn("crib=498 crib_editable=498", runtime_probe)
        self.assertIn("playbooks=37 formations=1533 plays=9251", runtime_probe)
        self.assertIn("_exercise_product_inspections", runtime_probe)
        self.assertIn("_exercise_default_provider_controller", runtime_probe)
        self.assertIn("ModEditorController(registry)", runtime_probe)
        self.assertIn(
            '"apf2k8.scorebug_presentation.digital_font"', runtime_probe
        )
        self.assertIn("reports=16 reviewed_metadata=22", runtime_probe)
        self.assertIn("Nfl2k5StadiumCacheCoordinator", runtime_probe)
        self.assertIn("build_scorebug_texture_import", runtime_probe)


if __name__ == "__main__":
    unittest.main()

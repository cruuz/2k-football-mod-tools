"""Retail-free product tests for the fixed APF full-shell crest profile."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from PIL import Image

from mod_editor.apf_studio.build import (
    HELMET_CREST_COMPOSITE_SCHEMA,
    ApfBuildService,
    BuildError,
    _CompiledBuildSpan,
)
from mod_editor.apf_studio.helmet_crest_design import (
    FULL_SHELL_CREST_PROFILE,
    GLOBAL_COVERAGE_SCOPE,
    HELMET_CREST_DESIGN_EDIT_ID,
    HELMET_CREST_DESIGN_KIND,
    RETAIL_CREST_PROFILE,
    HelmetCrestDesignError,
    metadata,
    validate_metadata,
)
from mod_editor.apf_studio.models import ApfSource, Modification
from mod_editor.apf_studio.project import load_project, save_project
from mod_editor.apf_studio.session import ApfSession, SessionError


def _source(root: Path) -> ApfSource:
    game = root / "game"
    game.mkdir()
    index = game / "0A"
    index.write_bytes(b"fixture")
    return ApfSource(
        selected_path=game,
        game_root=game,
        index_0a=index,
        source_sha256="a" * 64,
        source_size=len(b"fixture"),
        xex_sha256="b" * 64,
        display_name="fixture",
    )


def _mask(path: Path, *, transparent: bool = False) -> Path:
    image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    if not transparent:
        pixels = image.load()
        for y_value in range(201, 310):
            for x_value in range(132, 379):
                pixels[x_value, y_value] = (255, 0, 0, 255)
    image.save(path, "PNG")
    return path


class MetadataTests(unittest.TestCase):
    def test_only_two_fixed_profiles_and_global_full_shell_scope(self) -> None:
        full = metadata(
            profile=FULL_SHELL_CREST_PROFILE,
            crest_asset_index=30,
            crest_outer_entry_index=1133,
            fit_visible_mask=True,
            source_horizontal_coverage=247 / 512,
            output_horizontal_coverage=1.0,
        )
        self.assertEqual(full["coverage_scope"], GLOBAL_COVERAGE_SCOPE)
        self.assertFalse(full["creates_xenia_patch"])
        self.assertFalse(full["edits_default_xex"])
        with self.assertRaises(HelmetCrestDesignError):
            metadata(
                profile="1.40x_slider",
                crest_asset_index=30,
                crest_outer_entry_index=1133,
                fit_visible_mask=False,
                source_horizontal_coverage=1.0,
                output_horizontal_coverage=1.0,
            )

    def test_fit_is_not_accepted_for_the_retail_profile(self) -> None:
        with self.assertRaisesRegex(
            HelmetCrestDesignError, "only for the full-shell"
        ):
            metadata(
                profile=RETAIL_CREST_PROFILE,
                crest_asset_index=1,
                crest_outer_entry_index=36,
                fit_visible_mask=True,
                source_horizontal_coverage=0.5,
                output_horizontal_coverage=1.0,
            )


class SessionAndProjectTests(unittest.TestCase):
    def test_fit_stages_48_2_to_100_percent_and_roundtrips_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source(root)
            session = ApfSession(
                source, mock.Mock(), cache_root=root / "cache"
            )
            try:
                with mock.patch(
                    "mod_editor.apf_studio.session.apf_team_crests.crest_slots",
                    return_value=(
                        SimpleNamespace(asset_index=30, outer_entry_index=1133),
                    ),
                ):
                    result = session.replace_helmet_crest_design(
                        _mask(root / "wing.png"),
                        profile=FULL_SHELL_CREST_PROFILE,
                        crest_asset_index=30,
                        crest_outer_entry_index=1133,
                        fit_visible_mask=True,
                    )
                self.assertEqual(result.asset_id, HELMET_CREST_DESIGN_EDIT_ID)
                self.assertEqual(result.kind, HELMET_CREST_DESIGN_KIND)
                self.assertAlmostEqual(
                    float(result.metadata["source_horizontal_coverage"]),
                    247 / 512,
                )
                self.assertEqual(
                    result.metadata["output_horizontal_coverage"], 1.0
                )
                with Image.open(result.replacement_path) as fitted:
                    fitted.load()
                    rgba = fitted.tobytes()
                active_x = {
                    (offset // 4) % 512
                    for offset in range(0, len(rgba), 4)
                    if rgba[offset] or rgba[offset + 1] or rgba[offset + 2]
                }
                self.assertEqual((min(active_x), max(active_x)), (0, 511))

                project = root / "crest.apf2k8mod"
                save_project(
                    project,
                    source_sha256=source.source_sha256,
                    modifications=(result,),
                )
                _manifest, loaded, _annotations = load_project(
                    project,
                    expected_source_sha256=source.source_sha256,
                    destination_dir=root / "loaded",
                )
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].metadata, result.metadata)
                self.assertEqual(
                    loaded[0].replacement_sha256, result.replacement_sha256
                )
            finally:
                session.close()

    def test_detail_layer_stages_saves_and_roundtrips_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source(root)
            session = ApfSession(
                source, mock.Mock(), cache_root=root / "cache"
            )
            try:
                detail = Image.new("RGBA", (512, 512), (0, 0, 255, 255))
                detail.save(root / "detail.png", "PNG")
                with mock.patch(
                    "mod_editor.apf_studio.session.apf_team_crests.crest_slots",
                    return_value=(
                        SimpleNamespace(asset_index=1, outer_entry_index=36),
                    ),
                ):
                    result = session.replace_helmet_crest_design(
                        _mask(root / "wing.png"),
                        profile=RETAIL_CREST_PROFILE,
                        crest_asset_index=1,
                        crest_outer_entry_index=36,
                        detail_png=root / "detail.png",
                    )
                detail_digest = str(result.metadata["detail_sha256"])
                self.assertEqual(len(detail_digest), 64)
                stored_detail = result.replacement_path.parent / (
                    f"{detail_digest}.png"
                )
                self.assertTrue(stored_detail.is_file())

                project = root / "crest_two_layer.apf2k8mod"
                save_project(
                    project,
                    source_sha256=source.source_sha256,
                    modifications=(result,),
                )
                _manifest, loaded, _annotations = load_project(
                    project,
                    expected_source_sha256=source.source_sha256,
                    destination_dir=root / "loaded",
                )
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].metadata, result.metadata)
                loaded_detail = loaded[0].replacement_path.parent / (
                    f"{detail_digest}.png"
                )
                self.assertTrue(loaded_detail.is_file())
                self.assertEqual(
                    hashlib.sha256(loaded_detail.read_bytes()).hexdigest(),
                    detail_digest,
                )
            finally:
                session.close()

    def test_full_shell_profile_refuses_a_staged_detail_layer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source(root)
            session = ApfSession(
                source, mock.Mock(), cache_root=root / "cache"
            )
            try:
                detail = Image.new("RGBA", (512, 512), (0, 0, 255, 255))
                detail.save(root / "detail.png", "PNG")
                with mock.patch(
                    "mod_editor.apf_studio.session.apf_team_crests.crest_slots",
                    return_value=(
                        SimpleNamespace(asset_index=30, outer_entry_index=1133),
                    ),
                ):
                    with self.assertRaisesRegex(
                        SessionError, "retail side-decal"
                    ):
                        session.replace_helmet_crest_design(
                            _mask(root / "wing.png"),
                            profile=FULL_SHELL_CREST_PROFILE,
                            crest_asset_index=30,
                            crest_outer_entry_index=1133,
                            detail_png=root / "detail.png",
                        )
            finally:
                session.close()

    def test_transparent_and_symlink_inputs_fail_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = ApfSession(
                _source(root), mock.Mock(), cache_root=root / "cache"
            )
            try:
                with self.assertRaisesRegex(SessionError, "fully transparent"):
                    session.replace_helmet_crest_design(
                        _mask(root / "transparent.png", transparent=True),
                        profile=RETAIL_CREST_PROFILE,
                        crest_asset_index=1,
                        crest_outer_entry_index=36,
                    )
                real = _mask(root / "real.png")
                linked = root / "linked.png"
                linked.symlink_to(real)
                with self.assertRaisesRegex(SessionError, "non-symlink"):
                    session.replace_helmet_crest_design(
                        linked,
                        profile=RETAIL_CREST_PROFILE,
                        crest_asset_index=1,
                        crest_outer_entry_index=36,
                    )
                self.assertNotIn(
                    HELMET_CREST_DESIGN_EDIT_ID, session.modified_asset_ids
                )
            finally:
                session.close()

    def test_headless_full_shell_api_rejects_literal_rgb_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            painted = root / "painted-yellow.png"
            Image.new("RGBA", (512, 512), (255, 209, 0, 255)).save(painted)
            session = ApfSession(
                _source(root), mock.Mock(), cache_root=root / "cache"
            )
            try:
                with self.assertRaisesRegex(
                    SessionError, "semantic APF region masks"
                ):
                    session.replace_helmet_crest_design(
                        painted,
                        profile=FULL_SHELL_CREST_PROFILE,
                        crest_asset_index=30,
                        crest_outer_entry_index=1133,
                    )
                self.assertNotIn(
                    HELMET_CREST_DESIGN_EDIT_ID, session.modified_asset_ids
                )
            finally:
                session.close()


class BuildCompilerTests(unittest.TestCase):
    def test_runtime_closure_prunes_superseded_guard_band_tools(self) -> None:
        runtime_gate = (
            Path(__file__).resolve().parents[2]
            / "packaging/check_apf2k8_mod_studio_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"apf_helmet_crest_guard_band"', runtime_gate)
        self.assertNotIn('"apf_helmet_crest_guard_band_verify"', runtime_gate)
        self.assertIn('"apf_helmet_crest_wrap_patch"', runtime_gate)
        self.assertIn('"apf_helmet_crest_wrap_verify"', runtime_gate)

    def _modification(self, root: Path, profile: str) -> Modification:
        payload = _mask(root / f"{profile}.png").read_bytes()
        target = metadata(
            profile=profile,
            crest_asset_index=30,
            crest_outer_entry_index=1133,
            fit_visible_mask=False,
            source_horizontal_coverage=247 / 512,
            output_horizontal_coverage=247 / 512,
        )
        import hashlib

        return Modification(
            HELMET_CREST_DESIGN_EDIT_ID,
            HELMET_CREST_DESIGN_KIND,
            root / f"{profile}.png",
            hashlib.sha256(payload).hexdigest(),
            target,
        )

    def test_full_profile_compiles_package_cache_pair_and_outer_1310(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = ApfBuildService(_source(root))
            compiled = SimpleNamespace(
                entries={
                    1133: b"selected-package",
                    1134: b"migrated-package",
                    171: b"cache-directory",
                    213: b"cache-payload",
                    1310: b"shell-route",
                },
                report={
                    "catalog_slot_count": 118,
                    "component_writer_schemas": {
                        "package": "package/v1",
                        "cache": "cache/v1",
                        "shell": "shell/v24",
                        "shell_verify": "shell-verify/v24",
                    },
                },
                carrier_manifest={"schema": "shell/v24"},
                carrier_verification={"verified": True},
            )
            with mock.patch(
                "mod_editor.apf_studio.build.apf_team_crests.crest_slots",
                return_value=(
                    SimpleNamespace(asset_index=30, outer_entry_index=1133),
                ),
            ), mock.patch(
                "mod_editor.apf_studio.build.compile_full_shell_crest_entries",
                return_value=compiled,
            ) as compiler:
                progress = mock.Mock()
                entries, row = service._compile_helmet_crest_design(
                    self._modification(root, FULL_SHELL_CREST_PROFILE), progress
                )
            self.assertEqual(
                set(entries),
                {1133, 1134, 171, 213, 1310},
            )
            self.assertEqual(row["profile"], FULL_SHELL_CREST_PROFILE)
            self.assertEqual(row["kind"], HELMET_CREST_DESIGN_KIND)
            self.assertEqual(
                row["writer_schema"], HELMET_CREST_COMPOSITE_SCHEMA
            )
            self.assertFalse(row["creates_xenia_patch"])
            self.assertFalse(row["edits_default_xex"])
            compiler.assert_called_once_with(
                service.source.index_0a,
                root / f"{FULL_SHELL_CREST_PROFILE}.png",
                selected_asset_index=30,
                selected_outer_index=1133,
                progress=progress,
            )
            self.assertEqual(row["shell_atlas_compilation"]["catalog_slot_count"], 118)
            self.assertNotIn("guard_band", row)
            self.assertEqual(row["carrier_verification"], {"verified": True})

    def test_composed_cache_pair_uses_raw_structure_verifier_not_vc_iff(self) -> None:
        import apf_logocache_verify

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = ApfBuildService(_source(root))
            output = root / "output"
            output.mkdir()
            (output / "0A").write_bytes(b"synthetic")

            def entry(index: int) -> SimpleNamespace:
                return SimpleNamespace(
                    table_index=index,
                    name_id=index,
                    offset_blocks=index,
                    size_blocks=1,
                    size=0x800,
                    segments=(SimpleNamespace(
                        pack_name="0A", pack_offset=index * 0x800, size=0x800,
                    ),),
                )

            entries = [entry(index) for index in range(214)]
            cache_data = {
                apf_logocache_verify.DIR_TABLE_INDEX: b"D" * apf_logocache_verify.DIR_SIZE,
                apf_logocache_verify.PAYLOAD_TABLE_INDEX: (
                    b"P" * apf_logocache_verify.PAYLOAD_SIZE
                ),
            }
            for index, name_id, offset, size in (
                (
                    apf_logocache_verify.DIR_TABLE_INDEX,
                    apf_logocache_verify.DIR_NAME_ID,
                    apf_logocache_verify.DIR_PACK_OFFSET,
                    apf_logocache_verify.DIR_SIZE,
                ),
                (
                    apf_logocache_verify.PAYLOAD_TABLE_INDEX,
                    apf_logocache_verify.PAYLOAD_NAME_ID,
                    apf_logocache_verify.PAYLOAD_PACK_OFFSET,
                    apf_logocache_verify.PAYLOAD_SIZE,
                ),
            ):
                entries[index] = SimpleNamespace(
                    table_index=index,
                    name_id=name_id,
                    offset_blocks=offset // 0x800,
                    size_blocks=size // 0x800,
                    size=size,
                    segments=(SimpleNamespace(
                        pack_name="0A", pack_offset=offset, size=size,
                    ),),
                )
            archive = SimpleNamespace(alignment=0x800, entries=tuple(entries))
            spans = [
                _CompiledBuildSpan(
                    pack_name="0A",
                    offset=entries[index].segments[0].pack_offset,
                    data=cache_data[index],
                    outer_index=index,
                    asset_ids=(HELMET_CREST_DESIGN_EDIT_ID,),
                    kind=HELMET_CREST_DESIGN_KIND,
                    writer_schema=HELMET_CREST_COMPOSITE_SCHEMA,
                    reparse_owner=True,
                )
                for index in sorted(cache_data)
            ]
            with mock.patch(
                "mod_editor.apf_studio.build.EXPECTED_TREE",
                {"0A": (len(b"synthetic"), "0" * 64)},
            ), mock.patch.object(
                service, "_verify_changed_pack", return_value="1" * 64
            ), mock.patch(
                "mod_editor.apf_studio.build.apf_outer.parse_archive",
                return_value=archive,
            ), mock.patch(
                "mod_editor.apf_studio.build.apf_inner.parse_iff"
            ) as parse_iff, mock.patch(
                "mod_editor.apf_studio.build.apf_logocache_verify.verify_cache_structure",
                return_value={"verified": True},
            ) as verify_cache:
                self.assertEqual(
                    service._verify_composed(output, spans, lambda *_args: None),
                    "1" * 64,
                )
            parse_iff.assert_not_called()
            verify_cache.assert_called_once_with(
                cache_data[apf_logocache_verify.DIR_TABLE_INDEX],
                cache_data[apf_logocache_verify.PAYLOAD_TABLE_INDEX],
            )

            with mock.patch(
                "mod_editor.apf_studio.build.EXPECTED_TREE",
                {"0A": (len(b"synthetic"), "0" * 64)},
            ), mock.patch.object(
                service, "_verify_changed_pack", return_value="1" * 64
            ), mock.patch(
                "mod_editor.apf_studio.build.apf_outer.parse_archive",
                return_value=archive,
            ), mock.patch(
                "mod_editor.apf_studio.build.apf_logocache_verify.verify_cache_structure",
                side_effect=apf_logocache_verify.VerifyError("bad raw cache"),
            ), self.assertRaisesRegex(
                BuildError, "raw uniform_logocache structure is invalid"
            ):
                service._verify_composed(output, spans, lambda *_args: None)

    def test_retail_profile_does_not_touch_outer_1310(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = ApfBuildService(_source(root))
            package = SimpleNamespace(
                entry_bytes=b"package", manifest={"schema": "package/v1"}
            )
            cache = SimpleNamespace(
                directory_bytes=b"directory",
                payload_bytes=b"payload",
                manifest={"schema": "cache/v1"},
            )
            with mock.patch(
                "mod_editor.apf_studio.build.apf_team_crests.crest_slots",
                return_value=(
                    SimpleNamespace(asset_index=30, outer_entry_index=1133),
                ),
            ), mock.patch(
                "mod_editor.apf_studio.build.apf_logo_patch.build_patch",
                return_value=package,
            ), mock.patch(
                "mod_editor.apf_studio.build.apf_logocache_patch.build_cache_patch",
                return_value=cache,
            ), mock.patch(
                "mod_editor.apf_studio.build.apf_helmet_crest_wrap_patch.build_patch"
            ) as wrap:
                entries, row = service._compile_helmet_crest_design(
                    self._modification(root, RETAIL_CREST_PROFILE)
                )
            self.assertEqual(set(entries), {1133, 171, 213})
            self.assertEqual(row["profile"], RETAIL_CREST_PROFILE)
            wrap.assert_not_called()

    def test_full_shell_verifier_refusal_aborts_the_compile(self) -> None:
        import apf_helmet_crest_wrap_verify

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = ApfBuildService(_source(root))
            with mock.patch(
                "mod_editor.apf_studio.build.apf_team_crests.crest_slots",
                return_value=(
                    SimpleNamespace(asset_index=30, outer_entry_index=1133),
                ),
            ), mock.patch(
                "mod_editor.apf_studio.build.compile_full_shell_crest_entries",
                side_effect=apf_helmet_crest_wrap_verify.VerifyError(
                    "tampered carrier"
                ),
            ), self.assertRaisesRegex(BuildError, "tampered carrier"):
                service._compile_helmet_crest_design(
                    self._modification(root, FULL_SHELL_CREST_PROFILE)
                )

    def test_digital_font_collision_names_outer_and_composite_fix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _source(root)
            crest = self._modification(root, FULL_SHELL_CREST_PROFILE)
            digital = Modification(
                "apf:presentation:digital_font",
                "digital_font",
                root / "missing.png",
                "0" * 64,
                {},
            )
            with mock.patch(
                "mod_editor.apf_studio.build._require_build_space"
            ), mock.patch(
                "mod_editor.apf_studio.build.sha256_file",
                return_value="dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
            ):
                with self.assertRaisesRegex(
                    BuildError, "outer 1310.*composite compiler"
                ):
                    ApfBuildService(source).build(
                        (crest, digital), root / "output"
                    )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.core import platform_compat
from mod_editor.core.model import SourceRecord
from mod_editor.core.nfl2k5_source_cache import SOURCE_SHA256, SourceCache
from mod_editor.core.nfl2k5_stadium_cache import (
    EXPECTED_STADIUM_SCENES,
    Nfl2k5StadiumCacheCoordinator,
    StadiumCacheError,
    StadiumCacheFindingsError,
    WorkerCommandResult,
)
from mod_editor.core.nfl2k5_stadium_studio import Nfl2k5StadiumStudio
from tests.mod_editor.test_platform_compat import simulated_windows_filesystem


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_stadium_studio_cache as stadium_worker  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SyntheticSuccessfulRunner:
    def __init__(self, *, unsafe_path: str | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.unsafe_path = unsafe_path
        self.saw_resume_sentinel = False

    @staticmethod
    def _argument(argv: tuple[str, ...], name: str) -> str:
        return argv[argv.index(name) + 1]

    def run(self, argv: object, cwd: Path, progress: object) -> WorkerCommandResult:
        command = tuple(str(value) for value in argv)  # type: ignore[arg-type]
        self.calls.append(command)
        output = Path(self._argument(command, "--output"))
        source_sha256 = self._argument(command, "--source-sha256")
        self.saw_resume_sentinel = (output / "scene_records" / "resume.ok").is_file()
        models = output / "models"
        textures = output / "textures"
        models.mkdir(parents=True, exist_ok=True)
        textures.mkdir(parents=True, exist_ok=True)
        gltf_manifest = models / "manifest.json"
        texture_manifest = textures / "manifest.json"
        gltf_manifest.write_text(
            json.dumps(
                {
                    "schema": "nfl2k5_static_gltf_manifest/v2",
                    "summary": {"stadium_only": True},
                    "exports": [],
                }
            ),
            encoding="utf-8",
        )
        texture_manifest.write_text(
            json.dumps(
                {
                    "schema": "nfl2k5_scne_embedded_texture_png/v1",
                    "summary": {"stadium_only": True},
                    "pngs": [],
                    "occurrences": [],
                    "materials": [],
                }
            ),
            encoding="utf-8",
        )
        gltf_path = self.unsafe_path or "models/manifest.json"
        marker = {
            "schema": "2k5_mod_studio_stadium_cache_result/v1",
            "source_sha256": source_sha256,
            "private_user_cache": True,
            "shareable": False,
            "paths": {
                "gltf_manifest": gltf_path,
                "texture_manifest": "textures/manifest.json",
                "texture_root": "textures",
            },
            "hashes": {
                "gltf_manifest_sha256": _sha256(gltf_manifest),
                "texture_manifest_sha256": _sha256(texture_manifest),
            },
            "summary": {
                "stadium_scene_count": EXPECTED_STADIUM_SCENES,
                "exported_scene_count": EXPECTED_STADIUM_SCENES,
                "texture_occurrence_count": 0,
                "unique_png_count": 0,
            },
            "derived_payload_bytes": sum(
                path.stat().st_size for path in (gltf_manifest, texture_manifest)
            ),
            "resumed_scene_count": int(self.saw_resume_sentinel),
        }
        (output / "result.json").write_text(json.dumps(marker), encoding="utf-8")
        return WorkerCommandResult(0, ("synthetic success",))


class SyntheticFailedRunner:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, argv: object, cwd: Path, progress: object) -> WorkerCommandResult:
        self.calls += 1
        return WorkerCommandResult(
            1,
            (
                'STADIUM_CACHE_FINDINGS {"code":"bounded_private_derivation_failed",'
                '"message":"synthetic SCNE semantic boundary"}',
            ),
        )


class StadiumCacheCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # Resolve the temp root so paths the coordinator canonicalises compare
        # equal to ours under a symlinked (macOS /private/var) or short-name
        # (Windows) temp location.
        self.root = Path(self.temporary.name).resolve() / "private-source-cache"
        self.root.mkdir()
        self.pack0 = self.root / "extracted" / "game" / "0"
        self.pack0.parent.mkdir(parents=True)
        self.pack0.write_bytes(b"synthetic private pack zero")
        self.inventory = self.root / "indexes" / "inventory.json"
        self.inventory.parent.mkdir()
        self.inventory.write_text('{"synthetic":true}\n', encoding="utf-8")
        self.originals = self.root / "originals"
        self.originals.mkdir()
        source = SourceRecord(
            selected_path="/private/user/NFL2K5.iso",
            inspected_path="/private/user/NFL2K5.iso",
            kind="xiso",
            sha256=SOURCE_SHA256,
            size=6_300_499_968,
            recognized=True,
            fingerprint_id="nfl2k5-usa-retail-xiso",
            detected_game="nfl2k5",
        )
        self.cache = SourceCache(
            source=source,
            root=self.root,
            pack0=self.pack0,
            inventory=self.inventory,
            originals=self.originals,
            resource_count=1,
            outer_entry_count=1,
            kind_counts={"SCNE": 1},
        )
        self.pack0_before = self.pack0.read_bytes()
        self.inventory_before = self.inventory.read_bytes()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_atomic_private_publication_and_completed_cache_reuse(self) -> None:
        runner = SyntheticSuccessfulRunner()
        progress: list[tuple[str, int, int]] = []
        coordinator = Nfl2k5StadiumCacheCoordinator(
            runner=runner,
            free_space_reserve=0,
        )

        first = coordinator.ensure(self.cache, lambda *event: progress.append(event))
        second = coordinator.ensure(self.cache)

        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(first, second)
        self.assertTrue(first.private)
        self.assertFalse(first.shareable)
        self.assertEqual(first.scene_count, EXPECTED_STADIUM_SCENES)
        self.assertEqual(first.root.name, "stadium-studio-v1")
        self.assertEqual(first.root.parent, self.root / "derived")
        self.assertFalse((self.root / "derived" / ".stadium-studio-v1.staging").exists())
        self.assertEqual(self.pack0.read_bytes(), self.pack0_before)
        self.assertEqual(self.inventory.read_bytes(), self.inventory_before)
        self.assertEqual(progress[-1], ("Stadium Studio private assets ready", 1, 1))

        command = runner.calls[0]
        supplied_paths = {
            command[command.index("--cache-root") + 1],
            command[command.index("--pack0") + 1],
            command[command.index("--inventory") + 1],
            command[command.index("--output") + 1],
        }
        for raw in supplied_paths:
            Path(raw).resolve().relative_to(self.root.resolve())

    def test_existing_staging_checkpoints_are_preserved_for_worker_resume(self) -> None:
        staging = self.root / "derived" / ".stadium-studio-v1.staging"
        checkpoint = staging / "scene_records" / "resume.ok"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text("synthetic checkpoint", encoding="utf-8")
        runner = SyntheticSuccessfulRunner()

        result = Nfl2k5StadiumCacheCoordinator(
            runner=runner, free_space_reserve=0
        ).ensure(self.cache)

        self.assertTrue(runner.saw_resume_sentinel)
        self.assertEqual(result.resumed_scene_count, 1)
        self.assertTrue((result.root / "scene_records" / "resume.ok").is_file())

    def test_failed_worker_keeps_private_staging_and_never_publishes(self) -> None:
        runner = SyntheticFailedRunner()
        coordinator = Nfl2k5StadiumCacheCoordinator(
            runner=runner, free_space_reserve=0
        )

        with self.assertRaisesRegex(
            StadiumCacheFindingsError, "synthetic SCNE semantic boundary"
        ):
            coordinator.ensure(self.cache)

        self.assertEqual(runner.calls, 1)
        self.assertTrue(
            (self.root / "derived" / ".stadium-studio-v1.staging").is_dir()
        )
        self.assertFalse((self.root / "derived" / "stadium-studio-v1").exists())
        self.assertEqual(self.pack0.read_bytes(), self.pack0_before)
        self.assertEqual(self.inventory.read_bytes(), self.inventory_before)

    def test_forged_worker_path_is_rejected_before_publication(self) -> None:
        runner = SyntheticSuccessfulRunner(unsafe_path="../outside/manifest.json")
        coordinator = Nfl2k5StadiumCacheCoordinator(
            runner=runner, free_space_reserve=0
        )

        with self.assertRaisesRegex(StadiumCacheError, "path is unsafe"):
            coordinator.ensure(self.cache)

        self.assertFalse((self.root / "derived" / "stadium-studio-v1").exists())
        self.assertTrue(
            (self.root / "derived" / ".stadium-studio-v1.staging").is_dir()
        )

    def test_private_derived_cache_is_owner_only_on_posix(self) -> None:
        # The POSIX confidentiality contract, asserted exactly as before the
        # port: 0o700 directories and a 0o600 lock file, re-verified by the
        # coordinator itself after it creates them.
        if platform_compat.IS_WINDOWS:
            self.skipTest("POSIX mode privacy does not exist on Windows")
        Nfl2k5StadiumCacheCoordinator(
            runner=SyntheticSuccessfulRunner(), free_space_reserve=0
        ).ensure(self.cache)

        derived = self.root / "derived"
        self.assertEqual(stat.S_IMODE(derived.stat().st_mode), 0o700)
        self.assertEqual(
            stat.S_IMODE((derived / ".stadium-studio-v1.lock").stat().st_mode), 0o600
        )
        self.assertEqual(platform_compat.private_directory_mode(), 0o700)
        self.assertEqual(platform_compat.private_file_mode(), 0o600)

    def test_private_derived_cache_takes_the_windows_branch_and_still_verifies(
        self,
    ) -> None:
        # Forced Windows semantics on this host: the derived cache directory
        # reports 0o777 and the lock file 0o666, because Windows implements
        # neither.  The coordinator must accept exactly those values -- the
        # honest expectation for that platform -- and still refuse anything its
        # own OS *can* police.  msvcrt is genuinely absent here, so only the
        # advisory-lock primitive is stubbed; every privacy decision is real.
        with simulated_windows_filesystem():
            with (
                patch(
                    "mod_editor.core.nfl2k5_stadium_cache.exclusive_nonblocking_lock"
                ),
                patch("mod_editor.core.nfl2k5_stadium_cache.release_lock"),
            ):
                result = Nfl2k5StadiumCacheCoordinator(
                    runner=SyntheticSuccessfulRunner(), free_space_reserve=0
                ).ensure(self.cache)

            derived = self.root / "derived"
            self.assertEqual(stat.S_IMODE(derived.stat().st_mode), 0o777)
            self.assertEqual(
                stat.S_IMODE((derived / ".stadium-studio-v1.lock").stat().st_mode),
                0o666,
            )
            self.assertEqual(platform_compat.private_directory_mode(), 0o777)
            self.assertEqual(platform_compat.private_file_mode(), 0o666)
            self.assertFalse(platform_compat.privacy_guarantee().posix_mode_privacy)
            self.assertEqual(result.root.name, "stadium-studio-v1")
            self.assertTrue(result.private)
            self.assertFalse(result.shareable)

    def test_windows_branch_still_refuses_a_symlinked_lock_file(self) -> None:
        # Windows has no O_NOFOLLOW, so the lock file's open() *does* follow a
        # symlink there.  The privacy re-verification is what closes that gap:
        # it lstats the name, compares it against the descriptor it was handed,
        # and refuses the substitution.  Weaker platform, same guarantee.
        derived = self.root / "derived"
        derived.mkdir(mode=0o700)
        planted = self.root / "planted.lock"
        planted.write_bytes(b"")
        lock_path = derived / ".stadium-studio-v1.lock"
        try:
            lock_path.symlink_to(planted)
        except (OSError, NotImplementedError):
            self.skipTest("this platform/account cannot create symlinks")
        with simulated_windows_filesystem():
            with (
                patch(
                    "mod_editor.core.nfl2k5_stadium_cache.exclusive_nonblocking_lock"
                ),
                patch("mod_editor.core.nfl2k5_stadium_cache.release_lock"),
            ):
                with self.assertRaisesRegex(StadiumCacheError, "is a symlink"):
                    Nfl2k5StadiumCacheCoordinator(
                        runner=SyntheticSuccessfulRunner(), free_space_reserve=0
                    ).ensure(self.cache)

    def test_runtime_sources_do_not_depend_on_research_outputs(self) -> None:
        for relative in (
            Path("mod_editor/core/nfl2k5_stadium_cache.py"),
            Path("tools/nfl_stadium_studio_cache.py"),
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertNotIn("assets/intermediate", source)
            self.assertNotIn("reports/", source)
            self.assertNotIn("mod_editor.__main__", source)


class StadiumWorkerAggregationTests(unittest.TestCase):
    def test_worker_refuses_archive_pack_symlink_outside_private_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cache"
            packs = root / "packs"
            packs.mkdir(parents=True)
            outside = Path(temporary) / "outside-pack"
            outside.write_bytes(b"outside")
            for name in stadium_worker.EXPECTED_PACK_NAMES:
                (packs / name).write_bytes(name.encode("ascii"))
            (packs / "F").unlink()
            (packs / "F").symlink_to(outside)

            with self.assertRaisesRegex(
                stadium_worker.StadiumWorkerError, "regular, non-link"
            ):
                stadium_worker._validate_archive_pack_set(root, packs / "0")

    def test_synthetic_scene_records_make_product_compatible_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            # Resolve the temp root so the worker's canonical manifest paths
            # compare equal to ours under a symlinked (macOS /private/var) or
            # short-name (Windows) temp location.
            output = Path(temporary).resolve() / "private-staging"
            models = output / "models"
            textures_root = output / "textures"
            models.mkdir(parents=True)
            rgba = bytes((10, 20, 30, 255))
            rgba_sha256 = hashlib.sha256(rgba).hexdigest()
            png_payload = stadium_worker.encode_rgba_png(1, 1, rgba)
            png_relative = (
                Path("by_rgba_sha256")
                / rgba_sha256[:2]
                / f"{rgba_sha256}.png"
            )
            png_path = textures_root / png_relative
            png_path.parent.mkdir(parents=True)
            png_path.write_bytes(png_payload)
            binary = b"synthetic non-retail glTF buffer"
            document = {
                "asset": {"version": "2.0"},
                "buffers": [{"byteLength": len(binary), "uri": "scene.bin"}],
                "nodes": [
                    {
                        "name": "synthetic_surface",
                        "mesh": 0,
                        "extras": {"source_shape_index": 0},
                    }
                ],
                "meshes": [
                    {
                        "name": "synthetic_surface",
                        "primitives": [
                            {
                                "extras": {
                                    "source_material_index": 0,
                                    "source_material_name": "synthetic_material",
                                    "source_submesh_index": 0,
                                }
                            }
                        ],
                    }
                ],
            }
            gltf_payload = (
                json.dumps(document, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            (models / "scene.gltf").write_bytes(gltf_payload)
            (models / "scene.bin").write_bytes(binary)
            record = {
                "schema": stadium_worker.SCENE_RECORD_SCHEMA,
                "source": {"scene_index": 7},
                "export": {
                    "scene_index": 7,
                    "outer_index": 9,
                    "chunk_index": 2,
                    "scene_name": "stadium",
                    "decoded_sha256": "1" * 64,
                    "source_shape_count": 1,
                    "eligible_shape_indices": [0],
                    "withheld_shapes": [],
                    "status": "exported",
                    "gltf": "scene.gltf",
                    "bin": "scene.bin",
                    "gltf_sha256": hashlib.sha256(gltf_payload).hexdigest(),
                    "bin_sha256": hashlib.sha256(binary).hexdigest(),
                    "binary_bytes": len(binary),
                    "mesh_count": 1,
                    "primitive_count": 1,
                    "vertex_count": 1,
                    "raw_index_count": 1,
                    "gltf_index_count": 1,
                    "float3_shape_count": 1,
                    "normshort3_shape_count": 0,
                },
                "occurrences": [
                    {
                        "scene_index": 7,
                        "outer_index": 9,
                        "chunk_index": 2,
                        "texture_index": 0,
                        "scene_name": "stadium",
                        "width": 1,
                        "height": 1,
                        "format_name": "P8",
                        "rgba_sha256": rgba_sha256,
                        "png_sha256": hashlib.sha256(png_payload).hexdigest(),
                        "png_path": png_relative.as_posix(),
                        "mapped_material_names": "synthetic_material",
                        "mapped_material_count": 1,
                    }
                ],
                "materials": [
                    {
                        "scene_index": 7,
                        "outer_index": 9,
                        "chunk_index": 2,
                        "material_index": 0,
                        "material_name": "synthetic_material",
                        "scene_name": "stadium",
                        "mapping_status": "mapped_embedded_texture",
                        "texture_index": 0,
                    }
                ],
                "pngs": [
                    {
                        "rgba_sha256": rgba_sha256,
                        "width": 1,
                        "height": 1,
                        "png_path": png_relative.as_posix(),
                        "png_sha256": hashlib.sha256(png_payload).hexdigest(),
                        "png_size": len(png_payload),
                        "occurrence_count": 1,
                        "mapped_material_count": 1,
                        "representative_scene_index": 7,
                        "representative_outer_index": 9,
                        "representative_chunk_index": 2,
                        "representative_texture_index": 0,
                        "representative_descriptor_offset": 32,
                    }
                ],
            }

            result = stadium_worker.finalize_records(
                output_root=output,
                records=[record],
                source_sha256=SOURCE_SHA256,
                inventory_sha256="4" * 64,
                pack0_relative="extracted/game/0",
                inventory_relative="indexes/inventory.json",
                resumed_scene_count=0,
            )

            gltf = json.loads((output / "models" / "manifest.json").read_text())
            textures = json.loads(
                (output / "textures" / "manifest.json").read_text()
            )
            marker = json.loads((output / "result.json").read_text())
            self.assertEqual(gltf["schema"], "nfl2k5_static_gltf_manifest/v2")
            self.assertEqual(
                textures["schema"], "nfl2k5_scne_embedded_texture_png/v1"
            )
            self.assertEqual(textures["summary"]["png_count"], 1)
            self.assertEqual(marker, result)
            self.assertTrue(marker["private_user_cache"])
            self.assertFalse(marker["shareable"])
            self.assertEqual(marker["summary"]["stadium_scene_count"], 1)
            studio = Nfl2k5StadiumStudio(
                output / "models" / "manifest.json",
                output / "textures" / "manifest.json",
                output / "textures",
                geometry_catalog=None,
            )
            self.assertEqual(studio.scene_count, 1)
            scene = studio.list_scenes()[0]
            details = studio.scene_details(scene)
            self.assertEqual(len(details.textures), 1)
            self.assertEqual(
                studio.texture_for_surface(scene.scene_id, 0, 0),
                details.textures[0],
            )
            self.assertEqual(
                studio.preview_texture(details.textures[0].texture_id), png_path
            )


if __name__ == "__main__":
    unittest.main()

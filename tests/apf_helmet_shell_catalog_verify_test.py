from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apf_helmet_shell_catalog_verify",
    ROOT / "tools/apf_helmet_shell_catalog_verify.py",
)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


PRIVATE_SOURCE = Path(
    "/media/noah/Storage/for codex 1.0/extracted/"
    "All-Pro Football 2K8 (USA)/0A"
)


class HelmetShellCatalogVerifyTest(unittest.TestCase):
    def semantic_mask(self) -> bytes:
        pixels = np.zeros((verify.WIDTH * verify.HEIGHT, 4), dtype=np.uint8)
        pixels[:, 3] = 136
        pixels[123, :] = (170, 68, 0, 136)
        return pixels.tobytes()

    def test_triangle_strip_expansion_respects_restart_parity(self) -> None:
        self.assertEqual(
            verify.expand_strip([0, 1, 2, 3, 0xFFFF, 4, 5, 6]),
            [(0, 1, 2), (2, 1, 3), (4, 5, 6)],
        )
        self.assertEqual(verify.expand_strip([9] * 30), [])

    def test_semantic_mask_contract_rejects_invalid_channels(self) -> None:
        valid = self.semantic_mask()
        report = verify.validate_semantic_mask(valid, "valid")
        self.assertEqual(report["active_texel_count"], 1)

        invalid = bytearray(valid)
        invalid[2] = 17
        with self.assertRaisesRegex(verify.VerifyError, "uses blue"):
            verify.validate_semantic_mask(bytes(invalid), "blue")

        invalid = bytearray(valid)
        invalid[0] = 1
        with self.assertRaisesRegex(verify.VerifyError, "four-bit lattice"):
            verify.validate_semantic_mask(bytes(invalid), "lattice")

        invalid = bytearray(valid)
        invalid[0:4] = bytes((255, 17, 0, 136))
        with self.assertRaisesRegex(verify.VerifyError, "one red/green unit"):
            verify.validate_semantic_mask(bytes(invalid), "overweight")

    def test_retail_migration_uses_background_and_exact_sample_indices(self) -> None:
        pixels = np.zeros((verify.WIDTH * verify.HEIGHT, 4), dtype=np.uint8)
        pixels[0] = (17, 34, 0, 136)
        pixels[42] = (170, 68, 0, 136)
        sample_map = np.full(verify.WIDTH * verify.HEIGHT, -2, dtype=np.int32)
        sample_map[3] = -1
        sample_map[7] = 42
        migrated = np.frombuffer(
            verify.migrate_retail_rgba(pixels.tobytes(), sample_map), dtype=np.uint8,
        ).reshape((-1, 4))
        self.assertEqual(migrated[0].tolist(), [17, 34, 0, 136])
        self.assertEqual(migrated[3].tolist(), [17, 34, 0, 136])
        self.assertEqual(migrated[7].tolist(), [170, 68, 0, 136])
        self.assertTrue(verify.palette_is_subset(migrated.tobytes(), pixels.tobytes()))
        introduced = migrated.copy()
        introduced[9] = (34, 51, 0, 136)
        self.assertFalse(verify.palette_is_subset(introduced.tobytes(), pixels.tobytes()))

    def test_exact_source_catalog_cache_and_physical_map_are_pinned(self) -> None:
        if not PRIVATE_SOURCE.is_file():
            self.skipTest("exact private APF source is unavailable")
        archive = verify.apf_outer.parse_archive(PRIVATE_SOURCE)
        catalog = verify.resolve_catalog(archive)
        self.assertEqual(len(catalog), 118)
        self.assertEqual(catalog[30], 1133)

        rebound, rebound_catalog = verify.open_standalone_output_catalog(
            PRIVATE_SOURCE, archive,
        )
        self.assertEqual(rebound.index_path, PRIVATE_SOURCE)
        self.assertEqual(rebound_catalog, catalog)
        self.assertEqual(rebound.packs[0].path, PRIVATE_SOURCE)
        self.assertEqual(
            [pack.path for pack in rebound.packs[1:]],
            [pack.path for pack in archive.packs[1:]],
        )

        with verify.apf_inner.ArchiveReader(archive) as reader:
            package = verify._decode_package(archive, reader, 30, catalog[30])
            directory_raw = verify._read_outer_raw(
                archive, reader, verify.CACHE_DIRECTORY_INDEX,
                verify.CACHE_DIRECTORY_SIZE,
            )
        self.assertEqual(set(package.layers), {"logo_l0", "logo_l1"})
        self.assertTrue(all(
            len(layer.rgba) == verify.RGBA_LENGTH
            and layer.mip_length == verify.MIP_LENGTH
            and len(layer.dram) == verify.DRAM_LENGTH
            for layer in package.layers.values()
        ))

        directory = verify._cache_directory(directory_raw)
        self.assertEqual(len(directory.entries), 236)
        self.assertEqual(len({(row.catalog, row.level) for row in directory.entries}), 236)
        self.assertLessEqual(directory.total_stream_length, verify.CACHE_PAYLOAD_SIZE)

        system = verify._read_helmet_system(archive)
        sample_map, report = verify.build_retail_migration_map(system)
        self.assertEqual(sample_map.shape, (512 * 512,))
        self.assertEqual(
            report["combined_map_sha256"],
            "63545ad88e2ebac8098cddbc4991d32cdf13c9fff2abb48bb86b4466ca7002e8",
        )
        self.assertEqual(report["low_lod_only_texel_count"], 6686)
        self.assertEqual(
            [row["map_sha256"] for row in report["lods"]],
            [
                "df52ef5f0b7cff8649495fa1ef34e1a4f85fa8994b4301197a4a8e47e911343a",
                "6f65191a504eb4002f9b1fc68bf4ba00b64cfff28a2bb75d1f61e89799c2387d",
            ],
        )
        self.assertEqual(
            [row["covered_shell_atlas_texels"] for row in report["lods"]],
            [95001, 99966],
        )
        self.assertEqual(
            [row["mapped_retail_texels"] for row in report["lods"]],
            [{"left": 10178, "right": 10175}, {"left": 12684, "right": 12688}],
        )

    def test_contract_is_independent_headless_and_receipt_hashes_are_unambiguous(self) -> None:
        source = (ROOT / "tools/apf_helmet_shell_catalog_verify.py").read_text(
            encoding="utf-8",
        )
        self.assertIn("independent_headless_file_level_catalog_verification", source)
        self.assertIn("all_nonselected_layers_exact_independent_physical_migration", source)
        self.assertIn("nonselected_stored_h7a_subblocks_byte_exact", source)
        self.assertNotIn("import apf_logo_patch", source)
        self.assertNotIn("import apf_helmet_crest_wrap_patch", source)
        self.assertNotIn("import apf_helmet_crest_wrap_verify", source)
        self.assertNotIn("subprocess", source)

        inventory = {str(index): f"{index:064x}"[-64:] for index in range(118)}
        self.assertEqual(
            verify._find_package_hashes({"nested": {"package_entry_sha256_by_asset_index": inventory}}),
            [inventory],
        )


if __name__ == "__main__":
    unittest.main()

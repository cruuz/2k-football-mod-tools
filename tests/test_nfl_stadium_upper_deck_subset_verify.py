from __future__ import annotations

import ast
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import nfl_stadium_upper_deck_subset_patch as writer  # noqa: E402
import nfl_stadium_upper_deck_subset_verify as verifier  # noqa: E402


INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
SOURCE_PACK = INDEX.parent / "9"
CATALOG = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
BOUNDARY = ROOT / "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json"
RECIPE_SCHEMA = ROOT / "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json"
PREFIX8 = (
    ROOT
    / "reports/asset_samples/nfl_scne/"
      "stadium_upper_deck_prefix8_source_subset_recipe.v1.json"
)
NONIDENTITY4 = (
    ROOT
    / "reports/asset_samples/nfl_scne/"
      "stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json"
)
VERIFIER_SOURCE = TOOLS / "nfl_stadium_upper_deck_subset_verify.py"
RETAIL_AVAILABLE = all(
    path.is_file()
    for path in (
        INDEX,
        SOURCE_PACK,
        CATALOG,
        BOUNDARY,
        RECIPE_SCHEMA,
        PREFIX8,
        NONIDENTITY4,
    )
)


def contains_private_payload(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in {
                "positions",
                "replacement_bytes",
                "retail_records",
                "source_vertex_ids",
            }
            or contains_private_payload(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_private_payload(item) for item in value)
    return isinstance(value, (bytes, bytearray))


class VerifierSourcePolicyTests(unittest.TestCase):
    """Tests that do not require any user-owned retail data."""

    def test_verifier_has_only_the_audited_standard_library_imports(self) -> None:
        source = VERIFIER_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(VERIFIER_SOURCE))
        imported_roots: set[str] = set()
        relative_imports: list[tuple[str | None, int]] = []
        forbidden_dynamic_calls: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative_imports.append((node.module, node.lineno))
                elif node.module is not None:
                    imported_roots.add(node.module.split(".", 1)[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"__import__", "compile", "eval", "exec"}:
                    forbidden_dynamic_calls.append((node.func.id, node.lineno))

        self.assertEqual(relative_imports, [])
        self.assertEqual(forbidden_dynamic_calls, [])
        self.assertEqual(
            imported_roots,
            {
                "__future__",
                "argparse",
                "contextlib",
                "hashlib",
                "json",
                "math",
                "os",
                "pathlib",
                "stat",
                "struct",
                "typing",
            },
            "a verifier import changed without an explicit independence audit",
        )

    def test_bound_file_rejects_content_preserving_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "authority.json"
            displaced = root / "authority.pinned"
            payload = b"same-content-different-inode\n"
            path.write_bytes(payload)
            with verifier.BoundFile(path, "test authority") as bound:
                original_identity = bound.identity
                path.rename(displaced)
                path.write_bytes(payload)
                self.assertNotEqual(
                    original_identity,
                    (path.stat().st_dev, path.stat().st_ino),
                )
                self.assertEqual(bound.read(0, len(payload)), payload)
                with self.assertRaisesRegex(
                    verifier.UpperDeckSubsetVerifyError,
                    "pathname|pinned inode",
                ):
                    bound.assert_stable()


@unittest.skipUnless(RETAIL_AVAILABLE, "pinned user-owned NFL 2K5 extraction is unavailable")
class VerifierRetailEndToEndTests(unittest.TestCase):
    """Strict copied-volume checks against temporary, writer-produced artifacts."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        scratch_root = ROOT / ".codex-tmp"
        scratch_root.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(
            prefix=".upper-deck-verifier-tests-", dir=scratch_root
        )
        cls.root = Path(cls.temporary.name)
        cls.outputs = {
            "identity_noop": cls.root / "identity",
            "count_only_prefix": cls.root / "prefix8",
            "source_subset_remap": cls.root / "nonidentity4",
        }
        writer.patch(
            INDEX,
            None,
            True,
            cls.outputs["identity_noop"],
            CATALOG,
            BOUNDARY,
            RECIPE_SCHEMA,
        )
        writer.patch(
            INDEX,
            PREFIX8,
            False,
            cls.outputs["count_only_prefix"],
            CATALOG,
            BOUNDARY,
            RECIPE_SCHEMA,
        )
        writer.patch(
            INDEX,
            NONIDENTITY4,
            False,
            cls.outputs["source_subset_remap"],
            CATALOG,
            BOUNDARY,
            RECIPE_SCHEMA,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()
        super().tearDownClass()

    def verify_output(
        self,
        output: Path,
        recipe: Path | None,
        *,
        identity_noop: bool = False,
    ) -> dict[str, object]:
        return verifier.verify(
            INDEX,
            BOUNDARY,
            CATALOG,
            RECIPE_SCHEMA,
            output,
            recipe,
            identity_noop=identity_noop,
        )

    @contextmanager
    def changed_byte(self, path: Path, offset: int):
        with path.open("r+b", buffering=0) as stream:
            stream.seek(offset)
            original = stream.read(1)
            self.assertEqual(len(original), 1)
            replacement = bytes([original[0] ^ 1])
            stream.seek(offset)
            stream.write(replacement)
            os.fsync(stream.fileno())
        try:
            yield original
        finally:
            with path.open("r+b", buffering=0) as stream:
                stream.seek(offset)
                stream.write(original)
                os.fsync(stream.fileno())

    def test_all_three_modes_verify_end_to_end(self) -> None:
        cases = (
            (
                "identity_noop",
                None,
                True,
                12,
                writer.base.PACK_SHA256,
                writer.base.DECODED_SHA256,
                0,
            ),
            (
                "count_only_prefix",
                PREFIX8,
                False,
                8,
                None,
                "dffa0cc9aa4599c94fe436ec8599c8b9597eacb0d377865c6454a733cf56f272",
                2,
            ),
            (
                "source_subset_remap",
                NONIDENTITY4,
                False,
                4,
                "65f3775e804db6c93a9f560737c6879d2fa8fb81e21559f33e755c5f8173d290",
                "5503271598c6f55edb0f4d19b5232cadd55a9869029bf343287cb2157c4b9f93",
                64,
            ),
        )
        for mode, recipe, identity, count, pack_hash, decoded_hash, changed in cases:
            with self.subTest(mode=mode):
                report = self.verify_output(
                    self.outputs[mode], recipe, identity_noop=identity
                )
                self.assertEqual(report["mode"], mode)
                self.assertEqual(report["request"]["new_vertex_count"], count)
                if pack_hash is not None:
                    self.assertEqual(report["output"]["volume_sha256"], pack_hash)
                self.assertEqual(report["decoded"]["output_sha256"], decoded_hash)
                self.assertEqual(report["decoded"]["decoded_changed_byte_count"], changed)
                self.assertFalse(report["claims"]["runtime_proved"])
                self.assertFalse(report["claims"]["production_ready"])
                self.assertFalse(contains_private_payload(report))

    def test_manifest_overclaim_is_rejected(self) -> None:
        output = self.outputs["source_subset_remap"]
        manifest_path = output / "manifest.json"
        original = manifest_path.read_bytes()
        manifest = json.loads(original.decode("utf-8"))
        manifest["claims"]["runtime_visibility_proved"] = True
        manifest_path.write_bytes(verifier.canonical_json(manifest))
        try:
            with self.assertRaisesRegex(
                verifier.UpperDeckSubsetVerifyError,
                "manifest differs from the independent complete reconstruction",
            ):
                self.verify_output(output, NONIDENTITY4)
        finally:
            manifest_path.write_bytes(original)

    def test_wrapper_scratch_mutation_is_rejected(self) -> None:
        output = self.outputs["count_only_prefix"]
        offset = verifier.CHUNK_START + 0x14
        with self.changed_byte(output / "9", offset):
            with self.assertRaisesRegex(
                verifier.UpperDeckSubsetVerifyError,
                "scratch differs from independently derived bounded value",
            ):
                self.verify_output(output, PREFIX8)

    def test_nonzero_consumed_cap_gap_is_rejected(self) -> None:
        output = self.outputs["count_only_prefix"]
        consumed = 908_863
        self.assertLess(consumed, verifier.RETAIL_CONSUMED)
        offset = verifier.CHUNK_START + 32 + consumed
        with self.changed_byte(output / "9", offset):
            with self.assertRaisesRegex(
                verifier.UpperDeckSubsetVerifyError,
                "fixed gap is nonzero",
            ):
                self.verify_output(output, PREFIX8)

    def test_fixed_final_tail_mutation_is_rejected(self) -> None:
        output = self.outputs["count_only_prefix"]
        offset = verifier.CHUNK_START + 32 + verifier.RETAIL_CONSUMED
        with self.changed_byte(output / "9", offset):
            with self.assertRaisesRegex(
                verifier.UpperDeckSubsetVerifyError,
                "fixed final tail changed",
            ):
                self.verify_output(output, PREFIX8)

    def test_outside_target_mutation_is_rejected(self) -> None:
        output = self.outputs["count_only_prefix"]
        with self.changed_byte(output / "9", 0):
            with self.assertRaisesRegex(
                verifier.UpperDeckSubsetVerifyError,
                "changed before target chunk|outside-target-chunk hash changed",
            ):
                self.verify_output(output, PREFIX8)

    def test_report_inside_output_is_rejected_before_verification(self) -> None:
        output = self.outputs["identity_noop"]
        report_path = output / "verification.json"
        with (
            mock.patch.object(
                verifier,
                "_verify_bound",
                side_effect=AssertionError("bound verification called before report preflight"),
            ) as bound_verify_mock,
            self.assertRaisesRegex(
                verifier.UpperDeckSubsetVerifyError,
                "report.*output|output.*report",
            ),
        ):
            verifier.verify(
                INDEX,
                BOUNDARY,
                CATALOG,
                RECIPE_SCHEMA,
                output,
                None,
                identity_noop=True,
                report_path=report_path,
            )
        bound_verify_mock.assert_not_called()
        self.assertFalse(report_path.exists())

    def test_content_preserving_manifest_path_swap_is_rejected(self) -> None:
        output = self.outputs["count_only_prefix"]
        manifest_path = output / "manifest.json"
        displaced = self.root / "manifest.pinned"
        payload = manifest_path.read_bytes()
        original_inspect = verifier.inspect_target
        raced = False

        def inspect_with_race(decoded: bytes, new_count: int) -> dict[str, object]:
            nonlocal raced
            if not raced:
                raced = True
                manifest_path.rename(displaced)
                manifest_path.write_bytes(payload)
                self.assertNotEqual(
                    (manifest_path.stat().st_dev, manifest_path.stat().st_ino),
                    (displaced.stat().st_dev, displaced.stat().st_ino),
                )
            return original_inspect(decoded, new_count)

        try:
            with (
                mock.patch.object(verifier, "inspect_target", side_effect=inspect_with_race),
                self.assertRaisesRegex(
                    verifier.UpperDeckSubsetVerifyError,
                    "pinned|inode|pathname no longer",
                ),
            ):
                self.verify_output(output, PREFIX8)
            self.assertTrue(raced)
        finally:
            if raced:
                if manifest_path.exists():
                    manifest_path.unlink()
                if displaced.exists():
                    displaced.rename(manifest_path)


if __name__ == "__main__":
    unittest.main()

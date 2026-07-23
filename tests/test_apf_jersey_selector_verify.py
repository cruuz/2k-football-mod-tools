from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_jersey_selector_patch as writer  # noqa: E402
import apf_jersey_selector_verify as verify  # noqa: E402


SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
RECIPES = ROOT / "reports/asset_samples/apf_roster"

# The complete-volume hashes are exercised by the slow validator.  Unit tests
# synthesize only the fixed ROST span, or a sparse temporary volume shell.
CASES = (
    {
        "name": "identity",
        "recipe": "jersey_wasps_identity.v1.json",
        "output": "identity-0A",
        "volume_sha256": verify.SOURCE_VOLUME_SHA256,
        "entry_sha256": verify.OUTER_SHA256,
        "decoded_sha256": verify.DECODED_SHA256,
        "manifest_sha256": "d9a41a9f919a78974746df4b90464a9c88872116537ff20fe1efabdc3878c3a3",
        "recipe_sha256": "b0ac83eeca1b662a7c4f78710ec9b6a65c2a307ba5bf4cf40420179a2aa96bec",
        "mode": "no_op",
        "assignment_count": 1,
        "changed_bytes": 0,
        "payload_size": 435_225,
    },
    {
        "name": "wasps-targeted",
        "recipe": "jersey_wasps_4_to_21_targeted.v1.json",
        "output": "wasps-targeted-0A",
        "volume_sha256": "07d88e0820eff142e27049c9b167055a02527674a89b4cf15deaab662bc5b07c",
        "entry_sha256": "ac5b93fd6f60a751b4bb085666dc91fa1f24ca1b497dfa82fcaaa5a31d946583",
        "decoded_sha256": "7222f3df1beb94928b649b0b664894baf0f0934fabee30e88519da2ee835b376",
        "manifest_sha256": "38a66b2966b64bba0c3fe79f5e7a6cb3a5028f450946a7c61768cad9c0027373",
        "recipe_sha256": "c98584b027325a021fc3554766dcf11d5d6f1ab66824198132bfbe71c0b35147",
        "mode": "changed",
        "assignment_count": 1,
        "changed_bytes": 2,
        "payload_size": 435_231,
    },
    {
        "name": "full-unique",
        "recipe": "jersey_all_24_built_in_unique.v1.json",
        "output": "full-unique-0A",
        "volume_sha256": "7679491d4d8ca3378011e61a21de7a7e9c945ba16a1c9eefa91e16c3a604de77",
        "entry_sha256": "0bc194aca869c3acee359e6c7fa906c02e0ced328a1f95e13cd1e092a640a627",
        "decoded_sha256": "13997341f21a8ead74fc7526c28d7f2dfe8ff886abc64acd243ff96448db0cd2",
        "manifest_sha256": "283fb6a82e4b30d0d7bf98b7139ffdc85e916db76f653b8644575cb77dfc080e",
        "recipe_sha256": "0f4a93b1c446db5fd5a341cc11f2b997b47ca0ef68f1883e5596f0956b2e0de1",
        "mode": "changed",
        "assignment_count": 24,
        "changed_bytes": 30,
        "payload_size": 435_262,
    },
)


class APFJerseySelectorVerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = [SOURCE] + [
            RECIPES / str(case["recipe"])
            for case in CASES
        ]
        missing = [path for path in required if not path.is_file()]
        if missing:
            raise AssertionError(
                f"required APF jersey-selector authority is missing: {missing[0]}"
            )

        with verify.BoundFile(SOURCE, "retail source 0A") as source:
            cls.source_outer = verify.parse_outer_directory(source)
            cls.source_directory = source.read(0, writer.ARCHIVE_DIRECTORY_SIZE)
            cls.source_entry = source.read(
                cls.source_outer.pack_offset, cls.source_outer.size
            )
        cls.source_iff = verify.parse_iff(cls.source_entry)
        (
            cls.source_decoded,
            cls.source_tokens,
            cls.source_consumed,
        ) = verify.decode_h7a(cls.source_iff.payload)
        cls.source_tables = verify.parse_root(cls.source_decoded)
        cls.source_layout = verify.derive_selector_layout(cls.source_decoded)

        writer_entry = writer._target_entry()
        writer_reader = writer.BytesReader(cls.source_entry)
        writer_record = writer.apf_inner.parse_iff(writer_reader, writer_entry)
        writer_stored = cls.source_entry[
            writer_record.blocks[0].start_offset:
            writer_record.blocks[0].start_offset + writer_record.blocks[0].stored_length
        ]
        writer_layout = writer.derive_selector_layout(cls.source_decoded)
        writer_source = (
            None,
            writer_entry,
            writer_record,
            cls.source_entry,
            writer_stored,
            cls.source_decoded,
            writer_layout,
        )
        cls.writer_results: dict[str, writer.BuildResult] = {}
        with mock.patch.object(writer, "_validate_source", return_value=writer_source):
            for case in CASES:
                cls.writer_results[str(case["name"])] = writer.build_patch(
                    SOURCE, RECIPES / str(case["recipe"])
                )

    @staticmethod
    def _load_canonical(path: Path, label: str) -> tuple[dict[str, object], bytes]:
        with verify.BoundFile(path, label) as bound:
            return verify.load_canonical_json(bound, verify.MAX_MANIFEST_BYTES, label)

    def _case_material(
        self, case: dict[str, object]
    ) -> tuple[dict[str, object], bytes, list[tuple[int, int, int]], bytes, dict[str, object], bytes]:
        recipe, recipe_raw = self._load_canonical(
            RECIPES / str(case["recipe"]), "assignment recipe"
        )
        assignments = verify.validate_recipe(recipe)
        result = self.writer_results[str(case["name"])]
        manifest = copy.deepcopy(result.manifest)
        manifest["result"]["copied_volume"] = {
            "name": case["output"],
            "outside_outer_entry_prefix_sha256": verify.SOURCE_PREFIX_SHA256,
            "outside_outer_entry_suffix_sha256": verify.SOURCE_SUFFIX_SHA256,
            "sha256": case["volume_sha256"],
            "size_bytes": verify.SOURCE_VOLUME_SIZE,
        }
        manifest_raw = verify.canonical_json_bytes(manifest)
        return recipe, recipe_raw, assignments, result.entry, manifest, manifest_raw

    def _write_sparse_output(self, root: Path, name: str, entry: bytes) -> Path:
        path = root / name
        with path.open("xb") as stream:
            stream.write(self.source_directory)
            stream.seek(verify.OUTER_OFFSET)
            stream.write(entry)
            stream.truncate(verify.SOURCE_VOLUME_SIZE)
        return path

    def _rebuild_decoded(self, decoded: bytes) -> bytes:
        payload, _ = verify.encode_preserving_h7a(
            self.source_tokens,
            len(self.source_iff.payload) - self.source_consumed,
            decoded,
        )
        self.assertLessEqual(len(payload), verify.MAX_H7A_PAYLOAD_SIZE)
        stored = struct.pack(
            ">5I",
            verify.H7A_MAGIC,
            verify.DECODED_SIZE,
            verify.H7A_HEADER_SIZE + len(payload),
            verify.H7A_UNKNOWN,
            verify.H7A_SHIFT,
        ) + payload
        header = bytearray(self.source_entry[:verify.IFF_HEADER_SIZE])
        struct.pack_into(
            ">8I",
            header,
            verify.IFF_BLOCK_TABLE_OFFSET,
            verify.IFF_BLOCK_HASH,
            verify.IFF_BLOCK_HASH,
            0x20,
            verify.DECODED_SIZE,
            verify.H7A_UNKNOWN,
            verify.IFF_HEADER_SIZE,
            len(stored),
            0,
        )
        file_length = verify.IFF_HEADER_SIZE + len(stored)
        struct.pack_into(">I", header, 0x08, file_length)
        active = bytes(header) + stored + self.source_iff.footer
        self.assertLessEqual(len(active), verify.OUTER_SIZE)
        rebuilt = active + bytes(verify.OUTER_SIZE - len(active))
        parsed = verify.parse_iff(rebuilt)
        round_trip, _, _ = verify.decode_h7a(parsed.payload)
        self.assertEqual(round_trip, decoded)
        return rebuilt

    def _assert_sparse_verify_rejects(
        self,
        case: dict[str, object],
        entry: bytes,
        manifest: dict[str, object],
        message: str,
    ) -> None:
        changed_inside = sum(
            before != after for before, after in zip(self.source_entry, entry)
        )
        volume_facts = {
            "output_sha256": case["volume_sha256"],
            "changed_bytes_inside_outer_entry": changed_inside,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self._write_sparse_output(root, str(case["output"]), entry)
            manifest_path = root / "manifest.json"
            manifest_path.write_bytes(verify.canonical_json_bytes(manifest))
            with mock.patch.object(
                verify, "compare_complete_volumes", return_value=volume_facts
            ):
                with self.assertRaisesRegex(verify.VerifyError, message):
                    verify.verify(
                        SOURCE,
                        RECIPES / str(case["recipe"]),
                        output,
                        manifest_path,
                    )

    def test_verifier_imports_are_standard_library_allowlisted(self) -> None:
        source = (ROOT / "tools/apf_jersey_selector_verify.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "verifier must not use relative imports")
                self.assertIsNotNone(node.module)
                imported.add(str(node.module).split(".", 1)[0])
        self.assertEqual(imported, {
            "__future__", "argparse", "contextlib", "dataclasses", "hashlib",
            "json", "os", "pathlib", "stat", "struct", "sys", "typing", "zlib",
        })

    def test_source_outer_iff_h7a_root_and_selector_pointers_are_derived(self) -> None:
        self.assertEqual(self.source_outer, verify.OuterEntry(
            verify.OUTER_NAME_ID,
            verify.OUTER_OFFSET,
            verify.OUTER_SIZE,
            "0A",
            verify.OUTER_OFFSET,
        ))
        self.assertEqual(verify.sha256_bytes(self.source_entry), verify.OUTER_SHA256)
        self.assertEqual(
            (
                self.source_iff.file_length,
                len(self.source_iff.stored),
                len(self.source_iff.payload),
                len(self.source_iff.footer),
                len(self.source_iff.tail),
            ),
            (435_329, 435_245, 435_225, 96, 799),
        )
        self.assertEqual(verify.sha256_bytes(self.source_iff.footer), verify.FOOTER_SHA256)
        self.assertEqual(verify.sha256_bytes(self.source_decoded), verify.DECODED_SHA256)
        self.assertEqual(
            (len(self.source_decoded), len(self.source_tokens), self.source_consumed),
            (2_294_304, 284_015, 435_225),
        )
        self.assertEqual(self.source_consumed, len(self.source_iff.payload))
        self.assertEqual(
            self.source_tables[verify.TEAM_TABLE],
            verify.RootTable(4, 40, 753_780, 0x180),
        )
        self.assertEqual(
            self.source_tables[verify.SELECTOR_TABLE],
            verify.RootTable(17, 3724, 1_966_632, 8),
        )
        self.assertEqual(
            self.source_tables[verify.CONFIG_TABLE],
            verify.RootTable(19, 40, 1_997_756, 0x98),
        )
        self.assertEqual(self.source_layout.assets[:24], verify.RETAIL_BUILT_IN_ASSETS)
        self.assertEqual(self.source_layout.offsets[7], (0x1E09B8, 0x1E0948))
        self.assertEqual(self.source_layout.record_indices[7], (242, 228))
        self.assertEqual(self.source_layout.offsets[22], (0x1E02B8, 0x1E0248))
        self.assertEqual(self.source_layout.record_indices[22], (18, 4))

    def test_identity_targeted_and_full_outputs_reconstruct_exactly(self) -> None:
        claims = {
            "all_bytes_outside_outer_entry_bit_exact": True,
            "complete_manifest_reconstructed": True,
            "emulator_runtime_visibility_proved": False,
            "original_xbox_360_hardware_proved": False,
            "production_gui_exposed": False,
            "selector_byte_0_only": True,
            "selector_bytes_1_through_7_bit_exact": True,
        }
        for case in CASES:
            with self.subTest(case=case["name"]):
                (
                    recipe,
                    recipe_raw,
                    assignments,
                    output_entry,
                    manifest,
                    manifest_raw,
                ) = self._case_material(case)
                self.assertEqual(
                    manifest_raw,
                    verify.canonical_json_bytes(manifest),
                )
                expected_entry, wanted, expected_manifest, differences = (
                    verify.build_expected(
                        self.source_entry,
                        self.source_iff,
                        self.source_decoded,
                        self.source_tokens,
                        self.source_consumed,
                        self.source_layout,
                        recipe,
                        recipe_raw,
                        assignments,
                        str(case["output"]),
                        str(case["volume_sha256"]),
                    )
                )
                self.assertEqual(output_entry, expected_entry)
                self.assertEqual(manifest, expected_manifest)
                self.assertEqual(verify.sha256_bytes(manifest_raw), case["manifest_sha256"])
                output_iff = verify.parse_iff(output_entry)
                output_decoded, _, _ = verify.decode_h7a(output_iff.payload)
                self.assertEqual(output_decoded, wanted)
                self.assertEqual(verify.sha256_bytes(output_entry), case["entry_sha256"])
                self.assertEqual(verify.sha256_bytes(wanted), case["decoded_sha256"])
                self.assertEqual(len(output_iff.payload), case["payload_size"])
                self.assertEqual(len(differences), case["changed_bytes"])
                reconstructed_report = {
                    "assignment_count": len(assignments),
                    "claims": claims,
                    "decoded_changed_byte_count": len(differences),
                    "decoded_output_sha256": verify.sha256_bytes(wanted),
                    "manifest_sha256": verify.sha256_bytes(manifest_raw),
                    "mode": expected_manifest["mode"],
                    "outer_entry_sha256": verify.sha256_bytes(output_entry),
                    "output_volume_sha256": case["volume_sha256"],
                    "payload_size_after": len(output_iff.payload),
                    "recipe_sha256": verify.sha256_bytes(recipe_raw),
                    "schema": verify.VERIFY_SCHEMA,
                }
                self.assertEqual(reconstructed_report["mode"], case["mode"])
                self.assertEqual(
                    reconstructed_report["assignment_count"],
                    case["assignment_count"],
                )
                self.assertEqual(
                    reconstructed_report["decoded_changed_byte_count"],
                    case["changed_bytes"],
                )
                self.assertEqual(
                    reconstructed_report["output_volume_sha256"],
                    case["volume_sha256"],
                )
                self.assertEqual(
                    reconstructed_report["recipe_sha256"], case["recipe_sha256"]
                )
                self.assertEqual(reconstructed_report["claims"], claims)

    def test_recipe_loader_rejects_noncanonical_and_duplicate_keys(self) -> None:
        recipe, _ = self._load_canonical(
            RECIPES / "jersey_wasps_identity.v1.json", "assignment recipe"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            noncanonical = root / "noncanonical.json"
            noncanonical.write_bytes(json.dumps(recipe).encode("utf-8"))
            with verify.BoundFile(noncanonical, "assignment recipe") as bound:
                with self.assertRaisesRegex(verify.VerifyError, "not canonical"):
                    verify.load_canonical_json(
                        bound, verify.MAX_RECIPE_BYTES, "assignment recipe"
                    )

            duplicate = root / "duplicate.json"
            duplicate.write_bytes(b'{"schema":"first","schema":"second"}\n')
            with verify.BoundFile(duplicate, "assignment recipe") as bound:
                with self.assertRaisesRegex(verify.VerifyError, "duplicate key 'schema'"):
                    verify.load_canonical_json(
                        bound, verify.MAX_RECIPE_BYTES, "assignment recipe"
                    )

    def test_recipe_rejects_wrong_claims(self) -> None:
        recipe, _ = self._load_canonical(
            RECIPES / "jersey_wasps_identity.v1.json", "assignment recipe"
        )
        wrong = copy.deepcopy(recipe)
        wrong["claim_flags"]["emulator_runtime_visibility_proved"] = True
        with self.assertRaisesRegex(verify.VerifyError, "claim flags differ"):
            verify.validate_recipe(wrong)

    def test_full_recipe_rejects_duplicate_asset_allocation(self) -> None:
        recipe, _ = self._load_canonical(
            RECIPES / "jersey_all_24_built_in_unique.v1.json", "assignment recipe"
        )
        duplicate = copy.deepcopy(recipe)
        duplicate["assignments"][23]["replacement_asset_index"] = 21
        with self.assertRaisesRegex(verify.VerifyError, "not a permutation"):
            verify.validate_recipe(duplicate)

    def test_iff_rejects_header_footer_and_fixed_tail_mutations(self) -> None:
        first_tail_byte = self.source_iff.file_length + len(self.source_iff.footer)
        mutations = (
            ("header", 0, "fixed header differs"),
            ("footer", self.source_iff.file_length, "footer header differs"),
            ("tail", first_tail_byte, "tail is nonzero"),
        )
        for name, offset, message in mutations:
            with self.subTest(mutation=name):
                corrupted = bytearray(self.source_entry)
                corrupted[offset] ^= 1
                with self.assertRaisesRegex(verify.VerifyError, message):
                    verify.parse_iff(bytes(corrupted))

    def test_h7a_rejects_invalid_match(self) -> None:
        with self.assertRaisesRegex(verify.VerifyError, "lookback bounds"):
            verify.decode_h7a(b"\x01\x00\x00")

    def test_complete_volume_compare_rejects_outside_target_bytes(self) -> None:
        source_bytes = bytes(range(64))
        outer_offset = 16
        outer_size = 8
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source"
            source_path.write_bytes(source_bytes)
            for name, offset, message in (
                ("prefix", outer_offset - 1, "differs before"),
                ("suffix", outer_offset + outer_size, "differs after"),
            ):
                with self.subTest(mutation=name):
                    output_bytes = bytearray(source_bytes)
                    output_bytes[offset] ^= 1
                    output_path = root / f"output-{name}"
                    output_path.write_bytes(output_bytes)
                    with mock.patch.multiple(
                        verify,
                        SOURCE_VOLUME_SIZE=len(source_bytes),
                        OUTER_OFFSET=outer_offset,
                        OUTER_SIZE=outer_size,
                        SOURCE_VOLUME_SHA256=verify.sha256_bytes(source_bytes),
                        SOURCE_PREFIX_SHA256=verify.sha256_bytes(
                            source_bytes[:outer_offset]
                        ),
                        SOURCE_SUFFIX_SHA256=verify.sha256_bytes(
                            source_bytes[outer_offset + outer_size:]
                        ),
                    ):
                        with verify.BoundFile(source_path, "source") as source:
                            with verify.BoundFile(output_path, "output") as output:
                                with self.assertRaisesRegex(verify.VerifyError, message):
                                    verify.compare_complete_volumes(source, output)

    def test_verify_rejects_one_bank_opaque_and_unrelated_decoded_mutations(self) -> None:
        case = CASES[1]
        _, _, _, expected_entry, manifest, _ = self._case_material(case)
        expected_iff = verify.parse_iff(expected_entry)
        expected_decoded, _, _ = verify.decode_h7a(expected_iff.payload)

        bank_zero, _bank_one = self.source_layout.offsets[22]
        one_bank = bytearray(self.source_decoded)
        one_bank[bank_zero] = 21
        with self.assertRaisesRegex(verify.VerifyError, "jersey selector assets differ"):
            verify.derive_selector_layout(bytes(one_bank))

        opaque = bytearray(expected_decoded)
        opaque[bank_zero + 1] ^= 1
        self.assertEqual(
            verify.derive_selector_layout(bytes(opaque)).assets[22], 21
        )

        unrelated = bytearray(expected_decoded)
        unrelated[-1] ^= 1
        self.assertEqual(
            verify.derive_selector_layout(bytes(unrelated)).assets[22], 21
        )

        for name, decoded in (
            ("one-bank", bytes(one_bank)),
            ("opaque-selector-byte", bytes(opaque)),
            ("unrelated-decoded-byte", bytes(unrelated)),
        ):
            with self.subTest(mutation=name):
                mutated_entry = self._rebuild_decoded(decoded)
                self.assertNotEqual(mutated_entry, expected_entry)
                self._assert_sparse_verify_rejects(
                    case,
                    mutated_entry,
                    manifest,
                    "output ROST outer entry differs from independent reconstruction",
                )

    def test_expected_reconstruction_rejects_h7a_allocation_overflow(self) -> None:
        case = CASES[1]
        recipe, recipe_raw, assignments, _, _, _ = self._case_material(case)
        with mock.patch.object(
            verify,
            "encode_preserving_h7a",
            return_value=(bytes(verify.MAX_H7A_PAYLOAD_SIZE + 1), {}),
        ):
            with self.assertRaisesRegex(
                verify.VerifyError, "H7A payload exceeds fixed allocation"
            ):
                verify.build_expected(
                    self.source_entry,
                    self.source_iff,
                    self.source_decoded,
                    self.source_tokens,
                    self.source_consumed,
                    self.source_layout,
                    recipe,
                    recipe_raw,
                    assignments,
                    str(case["output"]),
                    str(case["volume_sha256"]),
                )

    def test_bound_file_rejects_final_and_parent_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_parent = root / "real"
            real_parent.mkdir()
            authority = real_parent / "authority.json"
            authority.write_bytes(b"{}\n")
            final_link = root / "final-link.json"
            final_link.symlink_to(authority)
            with self.assertRaisesRegex(verify.VerifyError, "regular non-symlink"):
                verify.BoundFile(final_link, "authority")

            parent_link = root / "parent-link"
            parent_link.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(verify.VerifyError, "symlink component"):
                verify.BoundFile(parent_link / authority.name, "authority")

    def test_report_reservation_rejects_symlink_parent_and_final_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_parent = root / "real"
            real_parent.mkdir()
            authority = root / "authority.json"
            authority.write_bytes(b"{}\n")
            with verify.BoundFile(authority, "authority") as bound:
                parent_link = root / "parent-link"
                parent_link.symlink_to(real_parent, target_is_directory=True)
                with self.assertRaisesRegex(verify.VerifyError, "symlink component"):
                    verify.ReportReservation(parent_link / "report.json", [bound])

                unrelated = root / "unrelated.json"
                unrelated.write_bytes(b"{}\n")
                final_link = real_parent / "report.json"
                final_link.symlink_to(unrelated)
                with self.assertRaisesRegex(verify.VerifyError, "already exists"):
                    verify.ReportReservation(final_link, [bound])

    def test_verify_rejects_hardlink_alias_before_parsing_or_scanning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "0A"
            output = root / "output-0A"
            recipe = root / "recipe.json"
            manifest = root / "manifest.json"
            source.write_bytes(b"source")
            output.write_bytes(b"output")
            recipe.write_bytes(b"{}\n")
            os.link(recipe, manifest)
            with self.assertRaisesRegex(verify.VerifyError, "aliases the same inode"):
                verify.verify(source, recipe, output, manifest)

    def test_verify_rejects_manifest_overclaim_without_full_volume_rescan(self) -> None:
        case = CASES[1]
        _, _, _, output_entry, manifest, _ = self._case_material(case)
        overclaim = copy.deepcopy(manifest)
        overclaim["claim_flags"]["emulator_runtime_visibility_proved"] = True
        self._assert_sparse_verify_rejects(
            case,
            output_entry,
            overclaim,
            "manifest differs from complete independent reconstruction",
        )


if __name__ == "__main__":
    unittest.main()

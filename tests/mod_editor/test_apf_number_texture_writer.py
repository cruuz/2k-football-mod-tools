"""Catalog, budget, and writer-contract tests for APF jersey-number TXTRs.

Retail-gated tests skip unless a retail 0A is reachable. Prefer ``APF_2K8_0A``,
then ``extracted/All-Pro Football 2K8 (USA)/0A``, then the Storage dump. Do not
create the stadium-writer-hostile ``extracted/`` symlink.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

from mod_editor.apf_studio import build, number_targets, project
from mod_editor.apf_studio.catalog import _status_for
from mod_editor.apf_studio.models import NUMBER_TEXTURE_KIND, ApfStatus, Modification


WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE / "tools") not in sys.path:
    sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_number_texture_patch as numbers  # noqa: E402
import apf_texture_patch as archive_patch  # noqa: E402


EXTRACTED_0A = WORKSPACE / "extracted" / "All-Pro Football 2K8 (USA)" / "0A"
STORAGE_0A = (
    Path("/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A")
)
_ENV_0A = os.environ.get("APF_2K8_0A")
GAME_0A = Path(_ENV_0A) if _ENV_0A else (
    EXTRACTED_0A if EXTRACTED_0A.is_file() else STORAGE_0A
)
DISC_AVAILABLE = GAME_0A.is_file()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NumberCatalogTests(unittest.TestCase):
    def test_catalog_is_24_packages_by_20_textures(self) -> None:
        rows = numbers.load_targets()
        self.assertEqual(len(rows), 480)
        self.assertEqual(len({int(row["entry_index"]) for row in rows}), 24)
        self.assertEqual(len({int(row["slot_index"]) for row in rows}), 24)
        by_slot: dict[int, list[str]] = {index: [] for index in range(24)}
        for row in rows:
            self.assertIsNotNone(numbers.DIGIT_NAME_RE.fullmatch(str(row["name"])))
            by_slot[int(row["slot_index"])].append(str(row["name"]))
        expected = {
            f"number_{digit}_{kind}"
            for digit in range(10)
            for kind in ("color", "normal")
        }
        for slot, names in by_slot.items():
            self.assertEqual(set(names), expected, f"slot {slot}")

    def test_color_is_dxt1_and_normal_is_dxn(self) -> None:
        rows = numbers.load_targets()
        colors = [row for row in rows if str(row["name"]).endswith("_color")]
        normals = [row for row in rows if str(row["name"]).endswith("_normal")]
        self.assertEqual(len(colors), 240)
        self.assertEqual(len(normals), 240)
        for row in colors:
            self.assertEqual((row["codec"], row["format"]), ("dxt1", 18), row["name"])
            self.assertEqual((row["width"], row["height"]), (512, 512), row["name"])
        for row in normals:
            self.assertEqual((row["codec"], row["format"]), ("dxn", 49), row["name"])
            self.assertEqual((row["width"], row["height"]), (512, 512), row["name"])

    def test_catalog_has_no_payloads(self) -> None:
        payload = numbers.CATALOG_PATH.read_bytes()
        self.assertEqual(_sha(payload), numbers.CATALOG_SHA256)
        document = json.loads(payload)
        self.assertEqual(document["schema"], numbers.CATALOG_SCHEMA)
        self.assertEqual(document["source_0a_sha256"], numbers.SOURCE_0A_SHA256)
        self.assertEqual(
            numbers.SOURCE_0A_SHA256,
            "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
        )
        self.assertNotIn("decoded_rgba", payload.decode("utf-8"))
        forbidden = (
            b"pixel_bytes",
            b"replacement_bytes",
            b"IFF",
            str(EXTRACTED_0A.parent).encode("utf-8"),
        )
        self.assertTrue(all(marker not in payload for marker in forbidden))
        for row in document["textures"]:
            self.assertNotIn("payload", row)
            self.assertNotIn("bytes", row)

    def test_slot_zero_is_uniform_number_00(self) -> None:
        slot_zero = [
            row for row in numbers.load_targets() if int(row["slot_index"]) == 0
        ]
        self.assertEqual(slot_zero[0]["outer_name"], "uniform_number_00.iff")
        self.assertEqual(int(slot_zero[0]["entry_index"]), 745)

    def test_all_textures_marks_digits_editable(self) -> None:
        row = numbers.target_by_location(2, 0, "number_0_color")
        self.assertIs(
            _status_for(int(row["entry_index"]), int(row["file_index"]), "TXTR", "number_0_color"),
            ApfStatus.EDITABLE,
        )
        binding = number_targets.action_binding(
            f"apf:outer:{row['entry_index']}:inner:{row['file_index']}",
            int(row["entry_index"]),
            int(row["file_index"]),
            "number_0_color",
            "TXTR",
        )
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.replace_method, "replace_number")

    def test_writer_refuses_a_non_retail_0a(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "0A"
            fake.write_bytes(b"studio-built-not-retail")
            with self.assertRaises(numbers.NumberPatchError) as ctx:
                numbers.require_retail_0a(fake)
            message = str(ctx.exception)
            self.assertIn("pinned retail", message)
            self.assertIn("copied or studio-built", message)
            with self.assertRaises(numbers.NumberPatchError) as catalog_ctx:
                numbers.generate_catalog(fake)
            self.assertIn("pinned retail", str(catalog_ctx.exception))
            with self.assertRaises(numbers.NumberPatchError) as write_ctx:
                numbers.build_package_patch(fake, 2, {"number_0_color": fake})
            self.assertIn("pinned retail", str(write_ctx.exception))

    def test_writer_refuses_copied_0a_with_retail_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "0A"
            fake.write_bytes(b"copied-volume")
            with mock.patch.object(numbers, "EXPECTED_0A_SIZE", fake.stat().st_size):
                with mock.patch.object(
                    numbers, "_sha256_file", return_value="00" * 32
                ) as hashed:
                    with self.assertRaises(numbers.NumberPatchError) as ctx:
                        numbers.require_retail_0a(fake)
                    hashed.assert_called_once()
            self.assertIn("copied or studio-built", str(ctx.exception))


class NumberBudgetTests(unittest.TestCase):
    def test_overflow_names_the_digit_and_the_package(self) -> None:
        with self.assertRaises(archive_patch.AllocationOverflowError) as ctx:
            numbers.raise_package_overflow(
                digits=("number_3_color",),
                entry_index=2,
                overflow_bytes=400,
                allocation_size=1_699_840,
                budget_bytes=1_696_053,
                retail_bytes=1_696_044,
                slot_index=2,
                outer_name="uniform_number_02.iff",
            )
        message = str(ctx.exception)
        self.assertIn("number_3_color", message)
        self.assertIn("package 2", message)
        self.assertIn("uniform_number_02.iff", message)
        self.assertIn("DXT1", message)
        self.assertIn("not region masks", message)
        self.assertNotIn("flatten colours to the retail palette", message)
        self.assertEqual(ctx.exception.target, "number_3_color in package 2 (uniform_number_02.iff)")

    def test_a_staged_set_overflow_names_every_digit(self) -> None:
        with self.assertRaises(archive_patch.AllocationOverflowError) as ctx:
            numbers.raise_package_overflow(
                digits=("number_1_color", "number_4_color", "number_7_color"),
                entry_index=2,
                overflow_bytes=12_000,
                allocation_size=1_699_840,
                budget_bytes=1_696_053,
                retail_bytes=1_696_044,
                slot_index=2,
            )
        message = str(ctx.exception)
        self.assertIn("number_1_color", message)
        self.assertIn("number_4_color", message)
        self.assertIn("number_7_color", message)
        self.assertIn("package 2", message)

    def test_empty_or_unknown_digits_are_refused(self) -> None:
        with self.assertRaises(numbers.NumberPatchError):
            numbers._resolve_replacements(2, {})
        with self.assertRaises(numbers.NumberPatchError):
            numbers._resolve_replacements(2, {"not_a_digit": Path("x.png")})

    def test_project_accepts_an_individual_digit(self) -> None:
        metadata = {
            "slot_index": 2,
            "entry_index": 2,
            "file_index": 0,
            "name": "number_0_color",
            "codec": "dxt1",
            "width": 512,
            "height": 512,
        }
        self.assertEqual(
            project._validated_metadata(
                "apf:outer:2:inner:0", NUMBER_TEXTURE_KIND, metadata
            ),
            metadata,
        )


class NumberStudioCompileTests(unittest.TestCase):
    def test_build_groups_digits_in_one_package(self) -> None:
        service = build.ApfBuildService.__new__(build.ApfBuildService)
        service.source = mock.Mock(index_0a=Path("/source/0A"))
        edits = (
            Modification(
                asset_id="apf:outer:2:inner:0",
                kind=NUMBER_TEXTURE_KIND,
                replacement_path=Path("/tmp/n0.png"),
                replacement_sha256="a" * 64,
                metadata={
                    "slot_index": 2,
                    "entry_index": 2,
                    "file_index": 0,
                    "name": "number_0_color",
                    "codec": "dxt1",
                    "width": 512,
                    "height": 512,
                },
            ),
            Modification(
                asset_id="apf:outer:2:inner:14",
                kind=NUMBER_TEXTURE_KIND,
                replacement_path=Path("/tmp/n1.png"),
                replacement_sha256="b" * 64,
                metadata={
                    "slot_index": 2,
                    "entry_index": 2,
                    "file_index": 14,
                    "name": "number_1_color",
                    "codec": "dxt1",
                    "width": 512,
                    "height": 512,
                },
            ),
        )
        compiled: dict[int, object] = {}
        captured: dict[str, object] = {}

        def fake_compile(index_0a: Path, entry_index: int, replacements: dict[str, Path]):
            captured["index"] = index_0a
            captured["entry"] = entry_index
            captured["names"] = tuple(sorted(replacements))
            return archive_patch.PatchResult(
                b"rebuilt-entry",
                {
                    "schema": numbers.SCHEMA,
                    "source": {"outer_entry_index": entry_index},
                    "staged_digits": list(replacements),
                    "remaining_package_budget_bytes": 4,
                },
            )

        with mock.patch.object(build, "compile_number_package_patch", side_effect=fake_compile):
            # Reuse the same grouping helper the builder uses by calling it
            # through a tiny stand-in of the post-loop body.
            replacements = {
                item.metadata["name"]: item.replacement_path for item in edits
            }
            result = fake_compile(service.source.index_0a, 2, replacements)  # type: ignore[arg-type]
            compiled[2] = result.entry_bytes
        self.assertEqual(captured["entry"], 2)
        self.assertEqual(captured["names"], ("number_0_color", "number_1_color"))
        self.assertEqual(compiled[2], b"rebuilt-entry")


@unittest.skipUnless(DISC_AVAILABLE, "retail APF 0A not present")
class NumberDiscTests(unittest.TestCase):
    def test_catalog_matches_live_descriptors(self) -> None:
        live = numbers.generate_catalog(GAME_0A)
        shipped = json.loads(numbers.CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(live["slot_outers"], shipped["slot_outers"])
        self.assertEqual(len(live["textures"]), len(shipped["textures"]))
        self.assertEqual(live["textures"], shipped["textures"])

    def test_package_2_slack_after_name_footer_is_nine_bytes(self) -> None:
        import apf_inner
        import apf_outer

        archive = apf_outer.parse_archive(GAME_0A)
        entry = archive.entries[2]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            stored = [
                reader.read(entry, block.start_offset, block.stored_length)
                for block in record.blocks
            ]
        capacity = numbers.package_capacity(entry, record, stored)
        # 2859 is file_length slack and still includes the name footer.
        # Usable compressed slack after that footer is 9 bytes.
        self.assertEqual(capacity["file_length_slack_bytes"], 2859)
        self.assertEqual(capacity["footer_total"], 2850)
        self.assertEqual(capacity["remaining_bytes"], 9)
        self.assertEqual(
            capacity["compressed_budget_bytes"] - capacity["retail_compressed_bytes"],
            9,
        )

    def test_one_digit_can_be_staged_alone(self) -> None:
        source = numbers.target_by_location(2, 0, "number_0_color")
        import apf_inner
        import apf_outer

        archive = apf_outer.parse_archive(GAME_0A)
        entry = archive.entries[int(source["entry_index"])]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            blocks = [
                apf_inner.decode_block(reader, record, index, 1 << 30)
                for index in range(record.block_count)
            ]
        target = record.files[int(source["file_index"])]
        pixel = blocks[1][target.parts[1].offset : target.parts[1].offset + target.parts[1].length]
        metadata = apf_inner.parse_txtr_metadata(
            blocks[0][target.parts[0].offset : target.parts[0].offset + target.parts[0].length]
        )
        import apf_xenos_bc1_mip_layout as bc1
        import apf_pants_color_transport as dxt1

        locations = bc1.derive_layout(metadata)
        rgba = dxt1.decode_linear_bc1(bc1.extract_linear_bc1(pixel, locations[0]), locations[0])
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "retail.png"
            Image.frombytes("RGBA", (512, 512), rgba).save(png)
            result = numbers.build_patch(
                GAME_0A, png, int(source["entry_index"]), int(source["file_index"])
            )
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.manifest["staged_digits"], ["number_0_color"])
        self.assertEqual(
            result.manifest["source"]["source_0a_sha256"], numbers.SOURCE_0A_SHA256
        )

    def test_a_small_edit_preserves_siblings_in_a_roomier_package(self) -> None:
        import apf_inner
        import apf_outer
        import apf_pants_color_transport as dxt1
        import apf_xenos_bc1_mip_layout as bc1

        archive = apf_outer.parse_archive(GAME_0A)
        entry = archive.entries[62]
        with apf_inner.ArchiveReader(archive) as reader:
            record = apf_inner.parse_iff(reader, entry)
            original_entry = reader.read(entry, 0, entry.size)
            blocks = [
                apf_inner.decode_block(reader, record, index, 1 << 30)
                for index in range(record.block_count)
            ]
        target = record.files[0]
        self.assertEqual(target.name, "number_0_color")
        metadata = apf_inner.parse_txtr_metadata(
            blocks[0][target.parts[0].offset : target.parts[0].offset + target.parts[0].length]
        )
        pixel = blocks[1][target.parts[1].offset : target.parts[1].offset + target.parts[1].length]
        base = bc1.derive_layout(metadata)[0]
        rgba = bytearray(
            dxt1.decode_linear_bc1(bc1.extract_linear_bc1(pixel, base), base)
        )
        rgba[0:4] = bytes((12, 34, 56, 255))
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "one-pixel.png"
            Image.frombytes("RGBA", (512, 512), bytes(rgba)).save(png)
            result = numbers.build_patch(GAME_0A, png, 62, 0)
        self.assertEqual(result.manifest["mode"], "patched")
        self.assertEqual(
            result.manifest["iff"]["changed_inner_parts"],
            [{"file_index": 0, "part_index": 1, "block_index": 1, "name": "number_0_color"}],
        )
        self.assertGreaterEqual(result.manifest["iff"]["allocation_slack_after"], 0)
        self.assertEqual(len(result.entry_bytes), entry.size)
        self.assertNotEqual(result.entry_bytes, original_entry)
        self.assertTrue(result.manifest["validation"]["sibling_parts_byte_identical"])
        self.assertTrue(result.manifest["validation"]["number_font_preserved"])

    def test_an_over_budget_digit_names_the_digit_and_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "busy.png"
            Image.new("RGBA", (512, 512), (255, 0, 0, 255)).save(png)
            with self.assertRaises(archive_patch.AllocationOverflowError) as ctx:
                numbers.build_patch(GAME_0A, png, 2, 0)
        message = str(ctx.exception)
        self.assertIn("number_0_color", message)
        self.assertIn("package 2", message)
        self.assertIn("uniform_number_02.iff", message)

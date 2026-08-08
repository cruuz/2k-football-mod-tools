"""Product gates for the 206-slot APF rectangular wordmark writer."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw

from mod_editor.apf_studio import build, project
from mod_editor.apf_studio.models import Modification
from mod_editor.apf_studio.textlogo_authoring import (
    WORDMARK_FIT_MODES,
    prepare_wordmark_png,
)


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in os.sys.path:
    os.sys.path.insert(0, str(TOOLS))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_pants_color_transport as bc1_transport  # noqa: E402
import apf_textlogo_patch as writer  # noqa: E402
import apf_textlogo_verify as verifier  # noqa: E402
import apf_xenos_bc1_mip_layout as bc1_mips  # noqa: E402


SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
SOURCE_AVAILABLE = SOURCE.is_file()


def _changed_wordmark(path: Path) -> Path:
    image = Image.new("RGBA", (512, 128), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (18, 14, 493, 113),
        radius=18,
        fill=(255, 0, 0, 255),
        outline=(255, 255, 255, 255),
        width=8,
    )
    draw.rectangle((48, 39, 464, 89), fill=(0, 0, 0, 255))
    draw.text((205, 54), "APF", fill=(255, 255, 255, 255), anchor="mm")
    image.save(path)
    return path


class ApfTextLogoCatalogTests(unittest.TestCase):
    def test_catalog_is_exact_retail_free_and_distinct_from_crests(self) -> None:
        rows = writer.load_targets()
        self.assertEqual(len(rows), 206)
        self.assertEqual([row["asset_index"] for row in rows], list(range(206)))
        self.assertEqual(len({row["outer_table_index"] for row in rows}), 206)
        self.assertEqual(len({row["outer_name_id"] for row in rows}), 206)
        self.assertEqual(rows[8]["outer_name"], "uniform_textlogo_08.iff")
        self.assertEqual(rows[8]["outer_table_index"], 906)
        self.assertNotIn("uniform_logo_", json.dumps(rows))
        payload = writer.CATALOG_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), writer.CATALOG_SHA256)
        forbidden = (
            b"decoded_rgba",
            b"pixel_bytes",
            b"replacement_bytes",
            str(SOURCE.parent).encode("utf-8"),
        )
        self.assertTrue(all(marker not in payload for marker in forbidden))

    def test_authoring_contains_or_covers_and_always_flattens_alpha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "transparent-tall.png"
            image = Image.new("RGBA", (100, 400), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle(
                (20, 20, 80, 380), fill=(25, 120, 240, 128)
            )
            image.save(source)
            contained = prepare_wordmark_png(
                source, root / "contain.png", fit_mode="contain"
            )
            covered = prepare_wordmark_png(
                source, root / "cover.png", fit_mode="cover"
            )
            self.assertEqual(contained.fit_action, "padded")
            self.assertEqual(covered.fit_action, "cropped")
            for result in (contained, covered):
                with Image.open(result.output_path) as prepared:
                    prepared.load()
                    self.assertEqual(prepared.size, (512, 128))
                    self.assertEqual(prepared.mode, "RGBA")
                    self.assertEqual(prepared.getchannel("A").getextrema(), (255, 255))
            with Image.open(contained.output_path) as prepared:
                self.assertEqual(prepared.getpixel((0, 0)), (0, 0, 0, 255))
            self.assertGreater(contained.transparent_source_pixels, 0)

    def test_stretch_mode_is_accepted_by_prepare_wordmark_png(self) -> None:
        """GUI combo data=stretch must reach the shipped authoring path."""
        self.assertIn("stretch", WORDMARK_FIT_MODES)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "wide.png"
            Image.new("RGBA", (900, 100), (200, 40, 40, 200)).save(source)
            prepared = prepare_wordmark_png(
                source, root / "stretch.png", fit_mode="stretch"
            )
            self.assertEqual(prepared.fit_mode, "stretch")
            self.assertEqual(prepared.fit_action, "stretched")
            self.assertEqual(
                (prepared.source_width, prepared.source_height), (900, 100)
            )
            with Image.open(prepared.output_path) as image:
                image.load()
                self.assertEqual(image.size, (512, 128))
                self.assertEqual(image.mode, "RGBA")
                # Flattened retail black background — full alpha
                self.assertEqual(image.getchannel("A").getextrema(), (255, 255))

    def test_gui_wordmark_fit_combo_data_matches_wordmark_fit_modes(self) -> None:
        """Combo items must not offer a mode prepare_wordmark_png rejects."""
        gui = (ROOT / "mod_editor" / "apf_studio" / "gui.py").read_text(
            encoding="utf-8"
        )
        # Extract the Wordmark panel's addItem data values for fit_mode.
        start = gui.index('self.fit_mode.addItem("Contain')
        block = gui[start : start + 500]
        for mode in WORDMARK_FIT_MODES:
            self.assertIn(f'"{mode}"', block, f"GUI missing fit mode {mode}")

    def test_project_and_build_accept_typed_index_205(self) -> None:
        metadata = {
            "family": "textlogo",
            "asset_index": 205,
            "width": 512,
            "height": 128,
            "outer_index": 1285,
            "inner_index": 0,
        }
        self.assertEqual(
            project._validated_metadata("apf:uniform:textlogo:205", "uniform", metadata),
            metadata,
        )
        service = build.ApfBuildService.__new__(build.ApfBuildService)
        service.source = mock.Mock(index_0a=Path("/source/0A"))
        replacement = Path("/replacement.png")
        modification = Modification(
            asset_id="apf:uniform:textlogo:205",
            kind="uniform",
            replacement_path=replacement,
            replacement_sha256="a" * 64,
            metadata=metadata,
        )
        result = mock.Mock(
            entry_bytes=b"rebuilt",
            manifest={
                "schema": writer.SCHEMA,
                "family_target": {
                    "asset_index": 205,
                    "outer_table_index": 1285,
                },
            },
        )
        with mock.patch.object(build, "compile_uniform_patch", return_value=result) as compile_:
            outer, payload, schema = service._compile(modification)
        self.assertEqual((outer, payload, schema), (1285, b"rebuilt", writer.SCHEMA))
        compile_.assert_called_once_with(
            Path("/source/0A"), replacement, "textlogo", 205
        )


@unittest.skipUnless(SOURCE_AVAILABLE, "extracted APF 0A not present")
class ApfTextLogoRealSourceTests(unittest.TestCase):
    def _source_png(self, asset_index: int, destination: Path) -> Path:
        row = writer.target_record(asset_index)
        *_, metadata, texture = writer._read_source(SOURCE, row)
        location = bc1_mips.derive_layout(metadata)[0]
        rgba = bc1_transport.decode_linear_bc1(
            bc1_mips.extract_linear_bc1(texture, location), location
        )
        Image.frombytes("RGBA", (512, 128), rgba).save(destination)
        return destination

    def test_all_206_source_derived_noops_are_package_bit_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "source.png"
            for asset_index, row in enumerate(writer.load_targets()):
                self._source_png(asset_index, png)
                result = writer.build_patch(SOURCE, png, asset_index)
                self.assertEqual(result.manifest["mode"], "no_op")
                self.assertEqual(
                    hashlib.sha256(result.entry_bytes).hexdigest(),
                    row["outer_allocation"]["sha256"],
                )

    def test_changed_minimum_headroom_slot_reopens_with_exact_write_mask(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = _changed_wordmark(Path(directory) / "changed.png")
            result = writer.build_patch(SOURCE, png, 151)
        self.assertEqual(result.manifest["mode"], "patched")
        self.assertGreaterEqual(result.manifest["iff"]["allocation_slack_after"], 0)
        self.assertEqual(
            result.manifest["iff"]["changed_inner_parts"],
            [{"file_index": 0, "part_index": 1, "block_index": 1}],
        )
        self.assertTrue(result.manifest["validation"]["all_six_levels_regenerated"])
        row = writer.target_record(151)
        archive = apf_outer.parse_archive(SOURCE)
        entry = archive.entries[row["outer_table_index"]]
        memory = writer.archive_patch.BytesReader(result.entry_bytes)
        record = apf_inner.parse_iff(memory, entry)
        self.assertEqual(record.file_count, 1)
        blocks = [
            apf_inner.decode_block(memory, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        metadata = apf_inner.parse_txtr_metadata(blocks[0][: writer.DRAM_LENGTH])
        locations = bc1_mips.derive_layout(metadata)
        self.assertEqual(len(locations), 6)
        self.assertEqual(
            bc1_mips.transport_roundtrip(blocks[1], locations), blocks[1]
        )

    def test_independent_whole_volume_verifier_accepts_only_target_range(self) -> None:
        source_root = SOURCE.parent.resolve()
        with tempfile.TemporaryDirectory(prefix="apf-textlogo-volume-") as directory:
            root = Path(directory)
            for name in ("0B", "1A", "1B"):
                (root / name).symlink_to(source_root / name)
            png = _changed_wordmark(root / "changed.png")
            result = writer.build_patch(SOURCE, png, 151)
            row = writer.target_record(151)
            archive = apf_outer.parse_archive(SOURCE)
            output = root / "0A"
            writer.archive_patch._write_copied_volume(
                SOURCE,
                output,
                archive.entries[row["outer_table_index"]],
                result.entry_bytes,
            )
            receipt = verifier.verify_copied_volume(
                SOURCE, output, 151, patch_manifest=result.manifest
            )
            self.assertEqual(receipt["changed_inner_parts"], [[0, 1]])
            self.assertTrue(receipt["outside_target"]["source_and_output_match"])
            self.assertTrue(receipt["all_six_mips_reopened"])


if __name__ == "__main__":
    unittest.main()

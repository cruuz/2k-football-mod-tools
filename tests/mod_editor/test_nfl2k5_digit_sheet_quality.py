"""Offline digit quality, real Team Kit/session/writer, bounded disc windows."""
from __future__ import annotations

from collections import Counter
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/fixtures")]

from PIL import Image
from number_sheet_quality_cases import CASES, FILL, OUTLINE, author_sheet, digit_image
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips, quantize_digit_levels, resize_cell
from mod_editor.core.nfl2k5_digit_preview import _filtered_level, decode_digit_texture, preview_digit_sheet, render_digit_sample
from nfl_tset_png_import import MipLevel, quantize_levels_to_vc_lz_bound
import nfl_live_numbers_nameplate_png_import as writer
import nfl_live_numbers_nameplate_targets as targets


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assets(size=64):
    return tuple(SimpleNamespace(digit=d, family="jersey", set_selector="26H0",
                                 width=size, height=size, asset_id=f"digit:{d}") for d in range(10))


def legacy_build(*args):
    """Replay the retained pre-fix filter and shared quantizer in the same writer.

    The TXTR wrapper, swizzler, fixed-span compressor and validators are the
    production path. Only the two changed quality policies are substituted.
    """
    def old_bound(levels, build_decoded, **kwargs):
        kwargs.pop("quantizer", None)
        kwargs.pop("minimum_palette_limit", None)
        return quantize_levels_to_vc_lz_bound(levels, build_decoded, **kwargs)
    with patch("mod_editor.core.nfl2k5_digit_texture.make_digit_mips", writer.make_mips), \
         patch.object(writer, "quantize_levels_to_vc_lz_bound", old_bound):
        return writer.build_import(*args)


def describe(texture):
    return {"span_sha256": texture.span_sha256, "format": texture.format_name,
            "packed_format": hex(texture.packed_format), "alpha_bits": texture.alpha_bits,
            "palette_sha256": sha(bytes(ch for c in texture.palette for ch in c)),
            "palette_rgba": texture.palette,
            "mips": [{"level": m.level, "size": [m.width, m.height], "rgba_sha256": sha(m.rgba),
                      "alpha_values": sorted(set(m.rgba[3::4])),
                      "partial_alpha_pixels": sum(0 < a < 255 for a in m.rgba[3::4]),
                      "alpha_sum": sum(m.rgba[3::4]),
                      "render32_sha256": sha(render_digit_sample(texture, height=32, level=m.level).tobytes())}
                     for m in texture.levels]}


class DigitQualityTests(unittest.TestCase):
    def test_majority_loses_coverage_and_rare_outline_wins_ties(self):
        transparent = bytes((250, 0, 200, 0))
        source = bytes(OUTLINE) + transparent * 3
        old = writer.make_mips(source, 2, 2, 2)[1].rgba
        new = make_digit_mips(source, 2, 2, 2)[1].rgba
        self.assertEqual(old[3], 0)
        self.assertEqual(new, bytes((*OUTLINE[:3], 64)))
        # Two colour ties favor globally rare green even when it only covers
        # half of the footprint; three white footprints establish rarity.
        rgba = b"".join(bytes(OUTLINE if x < 2 and y == 0 else FILL)
                        for y in range(4) for x in range(4))
        self.assertEqual(writer.make_mips(rgba, 4, 4, 2)[1].rgba[:4], bytes(OUTLINE))
        averaged = make_digit_mips(rgba, 4, 4, 2)[1].rgba[:4]
        self.assertEqual(averaged, bytes((140, 228, 148, 255)))

    def test_area_is_from_base_and_alpha_stays_eight_bits(self):
        rgba = bytes((240, 30, 70, 5)) + bytes((255, 0, 0, 0)) * 15
        result = make_digit_mips(rgba, 4, 4, 3)
        self.assertEqual(result[1].rgba[:4], bytes((240, 30, 70, 1)))
        self.assertEqual(result[2].rgba, bytes(4))
        rgba = bytes((240, 30, 70, 17)) + bytes(4) * 15
        self.assertEqual(make_digit_mips(rgba, 4, 4, 3)[2].rgba, bytes((240, 30, 70, 1)))
        with self.assertRaises(ValidationError):
            make_digit_mips(bytes(3 * 3 * 4), 3, 3, 2)

    def test_hidden_rgb_cannot_bleed_in_cell_resize_or_mips(self):
        image = Image.new("RGBA", (64, 64), (255, 0, 255, 0))
        image.paste((255, 255, 255, 255), (16, 16, 48, 48))
        resized = resize_cell(image, (32, 32))
        for r, g, b, a in resized.getdata():
            if a: self.assertEqual((r, g, b), (255, 255, 255))
        for level in make_digit_mips(image.tobytes(), 64, 64, 4):
            for i in range(0, len(level.rgba), 4):
                r, g, b, a = level.rgba[i:i+4]
                if a: self.assertEqual((r, g, b), (255, 255, 255))

    def test_float_cell_resize_avoids_eight_bit_premultiplication_colour_loss(self):
        image = Image.new("RGBA", (62, 62), (45, 210, 40, 1))
        old = image.resize((64, 64), Image.Resampling.LANCZOS)
        new = resize_cell(image, (64, 64))
        self.assertNotEqual(old.getpixel((32, 32)), (45, 210, 40, 1))
        self.assertEqual(new.getpixel((32, 32)), (45, 210, 40, 1))

    def test_before_after_mip_hashes_and_images_match_recorded_fixture(self):
        pins = json.loads((ROOT / "tests/fixtures/number_sheet_quality_mip_hashes.json").read_text())
        source = digit_image(3).tobytes()
        for label, levels in (("before", writer.make_mips(source, 64, 64, 4)),
                              ("after", make_digit_mips(source, 64, 64, 4))):
            self.assertEqual([sha(m.rgba) for m in levels], pins[label])
            for mip in levels:
                image = Image.frombytes("RGBA", (mip.width, mip.height), mip.rgba)
                stream = BytesIO(); image.save(stream, "PNG")
                with Image.open(BytesIO(stream.getvalue())) as decoded:
                    self.assertEqual(sha(decoded.tobytes()), pins[label][mip.level])

    def test_palette_protects_rare_opaque_outline_and_partial_alpha(self):
        rgba = b"".join(bytes((x % 256, (x * 11) % 256, 200, 1 + x % 254)) for x in range(4094))
        rgba += bytes(OUTLINE) + bytes(FILL)
        levels = make_digit_mips(rgba, 64, 64, 4)
        palette, indices, receipt = quantize_digit_levels(levels, 32)
        self.assertIn(OUTLINE, palette)
        self.assertIn(FILL, palette)
        self.assertEqual(receipt["protected_opaque_colours"], 2)
        self.assertEqual(receipt["alpha_bits"], 8)
        for source, mapped in zip(levels, indices):
            for a, index in zip(source.rgba[3::4], mapped):
                self.assertEqual((a == 0, a == 255), (palette[index][3] == 0, palette[index][3] == 255))
        self.assertEqual(quantize_digit_levels(levels, 32), (palette, indices, receipt))

    def test_quality_floor_refuses_instead_of_dropping_outline(self):
        from nfl_txtr import TxtrError
        levels = make_digit_mips(digit_image(8).tobytes(), 64, 64, 4)
        with self.assertRaisesRegex(TxtrError, "32-colour quality budget"):
            quantize_levels_to_vc_lz_bound(levels, lambda p, i: bytes(range(256)) * 4,
                stream_tag=1, offset_bits=12, max_encoded_size=32,
                quantizer=quantize_digit_levels, minimum_palette_limit=32)

    def test_exact_large_palette_does_not_report_solid_colour_approximation(self):
        rgba = b"".join(bytes((i * 4, 20, 30, 255)) for i in range(64))
        palette, _, receipt = quantize_digit_levels([MipLevel(0, 8, 8, rgba)])
        self.assertEqual(len(palette), 64)
        self.assertEqual(receipt["approximated_opaque_colours"], 0)

    def test_all_synthetic_sheets_layouts_sizes_palette_and_alpha_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for case in CASES:
                for layout in ("horizontal", "vertical", "grid_5x2", "grid_2x5"):
                    with self.subTest(case=case, layout=layout):
                        source = author_sheet(root / "source.png", case, layout=layout)
                        before = source.read_bytes()
                        outputs = split_digit_sheet(source, assets(), orientation=layout)
                        self.assertEqual(source.read_bytes(), before)
                        self.assertEqual([o.digit for o in outputs], list(range(10)))
                        for output in outputs:
                            self.assertEqual(output.layout, layout)
                            with Image.open(BytesIO(output.png)) as image:
                                self.assertEqual(image.size, (64, 64))
                                rgba = image.tobytes()
                            chain = make_digit_mips(rgba, 64, 64, 4)
                            self.assertTrue(any(0 < a < 255 for a in chain[2].rgba[3::4]))
                            if case.startswith("cell_"):
                                self.assertIn("will be resized", " ".join(output.warnings))
                        if case in ("crisp", "palette_png", "premultiplied_looking") and layout == "horizontal":
                            with Image.open(source) as original, Image.open(BytesIO(outputs[3].png)) as split:
                                self.assertEqual(split.tobytes(), original.convert("RGBA").crop((192, 0, 256, 64)).tobytes())

    def test_bad_cell_mapping_reports_layout_size_and_consequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sheet.png"
            Image.new("RGBA", (641, 64)).save(path)
            with self.assertRaisesRegex(ValidationError, r"horizontal.*64.1x64.*divisible"):
                split_digit_sheet(path, assets(), orientation="horizontal")
            Image.new("RGBA", (640, 32)).save(path)
            outputs = split_digit_sheet(path, assets(), orientation="horizontal")
            self.assertIn("64x32 cell", outputs[0].mapping_note)
            self.assertIn("stretch", " ".join(outputs[0].warnings))

    def test_encoded_decoder_and_renderer_refuse_invalid_inputs(self):
        with self.assertRaises(ValidationError): decode_digit_texture(b"short")
        with self.assertRaises(ValidationError):
            render_digit_sample(SimpleNamespace(levels=[]), height=0)

    def test_preview_bilinear_uses_two_texels_without_extra_downscale_blur(self):
        pixels = bytes((255, 255, 255, 255)) + bytes((0, 0, 0, 255)) * 7
        level = MipLevel(0, 8, 1, pixels)
        self.assertEqual(_filtered_level(level, (2, 1)).tobytes(), bytes((0, 0, 0, 255)) * 2)
        self.assertEqual(_filtered_level(level, (8, 1)).tobytes(), pixels)

    def test_grid_alignment_changes_old_filter_coverage_despite_same_cell_size(self):
        # An aligned solid region survives majority mips; a one-pixel shift
        # of that same art loses half-covered edges. Native dimensions alone
        # cannot distinguish the clean and blocky cases.
        errors = []
        for offset in (0, 1):
            image = Image.new("RGBA", (64, 64))
            image.paste(FILL, (16 + offset, 16 + offset, 48 + offset, 48 + offset))
            before = writer.make_mips(image.tobytes(), 64, 64, 4)
            reference = make_digit_mips(image.tobytes(), 64, 64, 4)
            errors.append(sum((a - b) ** 2 for old, new in zip(before[1:], reference[1:])
                              for a, b in zip(old.rgba[3::4], new.rgba[3::4])))
        self.assertEqual(errors[0], 0)
        self.assertGreater(errors[1], 0)


class RetailDigitQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = Path(os.environ.get("NFL2K5_TEST_INDEX", str(ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")))
        cls.inventory = Path(os.environ.get("NFL2K5_TEST_INVENTORY", str(ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json")))
        cls.xiso = Path(os.environ.get("NFL2K5_TEST_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
        needed = [cls.index, cls.inventory, cls.xiso, targets.DEFAULT_REPORT,
                  ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"]
        for name in ("jersey_tset", "sleeve_tset", "pants_tset", "live_helmet_txtr"):
            needed.append(ROOT / f"reports/assets/nfl2k5_{name}_compatibility.json")
        missing = [str(p) for p in needed if not p.is_file()]
        if missing: raise unittest.SkipTest("Private retail digit evidence absent: " + ", ".join(missing))
        from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
        cls.catalog = load_nfl2k5_uniform_catalog()
        cls.archive = writer.parse_archive(cls.index)

    def test_retail_format_mips_palette_and_alpha(self):
        evidence = []
        for code in ("05", "26"):
            for family in ("jersey", "helmet", "arm"):
                for digit in (1, 3, 5, 8):
                    _, _, target = targets.select_target(family, code, "H", 0, digit)
                    span = writer.read_entry_range(self.archive, self.archive.entries[target.outer_index], target.chunk_offset, target.span_size)
                    writer.validate_template(span, target)
                    decoded = decode_digit_texture(span)
                    self.assertEqual(decoded.alpha_bits, 8)
                    self.assertEqual(len(decoded.levels), target.mip_levels)
                    self.assertTrue(any(0 < a < 255 for m in decoded.levels[1:] for a in m.rgba[3::4]))
                    evidence.append({"selector": target.selector, **describe(decoded)})
        output = os.environ.get("NUMBER_SHEET_QUALITY_ARTIFACTS")
        if output:
            root = Path(output); root.mkdir(parents=True, exist_ok=True)
            (root / "retail.json").write_text(json.dumps(evidence, indent=2) + "\n")

    def test_all_cases_through_real_session_team_kit_writer_and_disc_windows(self):
        from mod_editor.core.nfl2k5_source_cache import SourceCache, SOURCE_SHA256
        from mod_editor.studio.session import StudioSession
        from mod_editor.studio.uniform_bundle import TeamKitBundleService, TEAM_KIT_MANIFEST
        import nfl_uniform_color_xiso_direct_patch as xiso
        import nfl2k5_visual_mod_project as composer

        evidence = []
        artifact_root = Path(os.environ["NUMBER_SHEET_QUALITY_ARTIFACTS"]) if os.environ.get("NUMBER_SHEET_QUALITY_ARTIFACTS") else None
        with tempfile.TemporaryDirectory(prefix="digit-quality-retail-") as temporary, self.xiso.open("rb") as disc:
            root = Path(temporary).resolve()
            cache = SourceCache(SimpleNamespace(sha256=SOURCE_SHA256), root / "cache", self.index,
                                self.inventory, root / "originals", 0, 0, {})
            # The complete matrix uses Ravens style 3; Seattle's much tighter
            # zero slot is exercised separately as a precise quality refusal.
            digit_targets = tuple(a for a in self.catalog.assets_for_set("02H3") if a.family == "jersey" and a.digit is not None)
            entries, _ = xiso.parse_xdvdfs(disc.fileno(), os.fstat(disc.fileno()).st_size)
            for case in CASES:
                with self.subTest(case=case):
                    session = StudioSession(cache, self.catalog, root=root / "sessions")
                    session.visual_catalog = self.catalog
                    service = TeamKitBundleService(self.catalog, session)
                    source = author_sheet(root / "sheet.png", case)
                    outputs = split_digit_sheet(source, digit_targets, orientation="horizontal")
                    kit = root / case
                    service.export(("02H3",), kit)
                    paths = {r["asset_id"]: kit / r["path"] for r in json.loads((kit / TEAM_KIT_MANIFEST).read_text())["assets"]}
                    for output in outputs: paths[output.asset_id].write_bytes(output.png)
                    imported = service.import_edited(kit, expected_set_selectors=("02H3",))
                    self.assertEqual(imported.changed_count, 10)
                    before_rows, after_rows = [], []
                    for asset in digit_targets:
                        args = (self.index, targets.DEFAULT_REPORT, "jersey", "02", "H", 3, asset.digit, session.current_path(asset))
                        old, _, old_receipt = legacy_build(*args)
                        new, _, receipt = writer.build_import(*args)
                        _, _, target = targets.select_target("jersey", "02", "H", 3, asset.digit)
                        absolute = entries[target.xiso_pack_path.casefold()].byte_offset + target.pack_offset
                        disc.seek(absolute - 64)
                        original_window = disc.read(target.span_size + 128)
                        self.assertEqual(sha(original_window[64:-64]), target.span_sha256)
                        path = root / "written-window.bin"
                        path.write_bytes(original_window)
                        with path.open("r+b") as stream:
                            composer.write_all(stream.fileno(), 64, new)
                            stream.flush()
                        reopened = path.read_bytes()
                        self.assertEqual((reopened[:64], reopened[-64:]), (original_window[:64], original_window[-64:]))
                        actual = decode_digit_texture(reopened[64:-64])
                        before = decode_digit_texture(old)
                        self.assertEqual([sha(m.rgba) for m in actual.levels], receipt["mips"]["decoded_rgba_sha256"])
                        self.assertEqual(len(new), target.span_size)
                        if not case.startswith("cell_"):
                            self.assertIn(OUTLINE, actual.palette)
                            self.assertIn(FILL, actual.palette)
                        else:
                            # Resizing may change the author's exact RGB. Both
                            # distinct solid colour regions must still survive.
                            for colour in (OUTLINE, FILL):
                                self.assertLess(min(max(abs(c[i] - colour[i]) for i in range(3))
                                                    for c in actual.palette if c[3] == 255), 24)
                        self.assertTrue(any(0 < a < 255 for a in actual.levels[2].rgba[3::4]))
                        with Image.open(session.current_path(asset)) as png:
                            ideal = make_digit_mips(png.convert("RGBA").tobytes(), asset.width, asset.height, target.mip_levels)
                        errors = {name: [sum((a - b) ** 2 for a, b in zip(m.rgba[3::4], reference.rgba[3::4]))
                                         for m, reference in zip(tex.levels, ideal)]
                                  for name, tex in (("before", before), ("after", actual))}
                        self.assertLess(sum(errors["after"][1:]), sum(errors["before"][1:]))
                        disc.seek(absolute - 64)
                        self.assertEqual(disc.read(len(original_window)), original_window)
                        before_rows.append((asset.digit, before)); after_rows.append((asset.digit, actual))
                        evidence.append({"case": case, "selector": target.selector, "stored_bytes": target.stored_size,
                                         "before": describe(before), "after": describe(actual),
                                         "fit": receipt.get("bounded_palette_fit"),
                                         "squared_alpha_error": errors,
                                         "quantization": receipt["quantization"]})
                        if artifact_root:
                            artifact_root.mkdir(parents=True, exist_ok=True)
                            for label, texture in (("before", before), ("after", actual)):
                                for mip in texture.levels:
                                    image = Image.frombytes("RGBA", (mip.width, mip.height), mip.rgba)
                                    image.save(artifact_root / f"{case}_{asset.digit}_{label}_mip{mip.level}.png")
                    if artifact_root:
                        from mod_editor.core.nfl2k5_digit_preview import render_digit_sheet_preview
                        for label, rows in (("before", before_rows), ("after", after_rows)):
                            (artifact_root / f"{case}_{label}.png").write_bytes(render_digit_sheet_preview(rows))
                    session.undo()
                    self.assertEqual(session.modified_count, 0)
            if artifact_root:
                (artifact_root / "synthetic.json").write_text(json.dumps(evidence, indent=2) + "\n")

    def test_real_preview_uses_identical_writer_spans_and_reports_unfit_sheet(self):
        selected = tuple(a for a in self.catalog.assets_for_set("26H0") if a.family == "jersey" and a.digit is not None)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = author_sheet(root / "sheet.png", "crisp")
            outputs = split_digit_sheet(source, selected)
            preview = preview_digit_sheet(self.index, selected, outputs)
            self.assertEqual(len(preview.receipts), 10)
            self.assertIn("8-bit alpha", preview.details)
            with Image.open(BytesIO(preview.png)) as image:
                self.assertEqual(image.size, (730, 850))
            for output, receipt in zip(outputs, preview.receipts):
                path = root / "digit.png"; path.write_bytes(output.png)
                span, _, _ = writer.build_import(self.index, targets.DEFAULT_REPORT, "jersey", "26", "H", 0, output.digit, path)
                self.assertEqual(sha(span), receipt["replacement"]["span_sha256"])
            # Deliberately double-filtered artwork still cannot fit Seattle 0
            # above the quality floor. Refuse before a GUI Team Kit transaction.
            source = author_sheet(root / "sheet.png", "double_resampled62")
            outputs = split_digit_sheet(source, selected)
            with self.assertRaisesRegex(ValidationError, "Digit 0:.*1488-byte.*16-colour"):
                preview_digit_sheet(self.index, selected, outputs)


if __name__ == "__main__":
    unittest.main()

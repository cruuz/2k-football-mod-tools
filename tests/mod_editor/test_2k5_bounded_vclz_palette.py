"""Regression coverage for the reported 1,568-byte number-art build failure.

The supported digit textures are P8, but their retail VC-LZ bodies are fixed in
place.  Ninety-four targets have only 1,568 bytes.  A high-colour replacement is
valid P8 art yet cannot fit if the importer always insists on a 256-entry
palette.  The product now tries deterministic palette tiers until the complete
stream fits, preserving the richest tier that passed.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
import sys
import tempfile
import unittest


_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT, _ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from nfl_live_numbers_nameplate_png_import import make_mips  # noqa: E402
from nfl_tset_png_import import (  # noqa: E402
    palette_bytes,
    quantize_levels_to_vc_lz_bound,
)
from nfl_txtr import (  # noqa: E402
    TxtrError,
    compress_vc_lz,
    decode_chunk,
    decompress_vc_lz,
    encode_rgba_png,
    parse_chunks,
    parse_texture,
    swizzle_2d,
)


_REAL_INDEX = _ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
_REAL_INVENTORY = _ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
_REAL_REPORT = (
    _ROOT / "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json"
)
_REAL_XISO = _ROOT / "ESPN NFL 2K5 (USA).xiso.iso"
_HAVE_REAL_COMPOSER_INPUTS = all(
    path.is_file()
    for path in (_REAL_INDEX, _REAL_INVENTORY, _REAL_REPORT, _REAL_XISO)
)


class Exact1568BytePaletteFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rng = random.Random(0x2C05)
        rgba = bytes(rng.randrange(256) for _ in range(64 * 64 * 4))
        cls.levels = make_mips(rgba, 64, 64, 4)
        cls.fit = quantize_levels_to_vc_lz_bound(
            cls.levels,
            cls._decoded,
            stream_tag=1,
            offset_bits=12,
            max_encoded_size=1_568,
        )

    @staticmethod
    def _decoded(palette, index_levels) -> bytes:
        chain = b"".join(
            swizzle_2d(indices, level.width, level.height, 1)
            for indices, level in zip(index_levels, Exact1568BytePaletteFitTests.levels)
        )
        # Exact live jersey/arm digit allocation: 128 system bytes, 5,440
        # index bytes and one 1,024-byte P8 palette.
        assert len(chain) == 5_440
        return bytes(128) + chain + palette_bytes(palette)

    def test_high_entropy_digit_fits_the_exact_reported_bound(self) -> None:
        fit = self.fit

        self.assertEqual(fit.attempts[0]["palette_entries"], 256)
        self.assertEqual(fit.attempts[0]["result"], "vc_lz_overflow")
        self.assertEqual(fit.attempts[-1]["result"], "fit")
        self.assertLessEqual(len(fit.compressed), 1_568)
        decoded, info = decompress_vc_lz(fit.compressed, len(fit.decoded))
        self.assertEqual(decoded, fit.decoded)
        self.assertEqual(info.consumed_bytes, len(fit.compressed))
        self.assertTrue(fit.compression.verified_roundtrip)

    def test_bound_is_inclusive_and_one_byte_short_still_fails(self) -> None:
        fit = self.fit
        exact, _ = compress_vc_lz(
            fit.decoded,
            stream_tag=1,
            offset_bits=12,
            max_encoded_size=len(fit.compressed),
        )
        self.assertEqual(exact, fit.compressed)
        with self.assertRaisesRegex(TxtrError, "VC-LZ stream needs more than"):
            compress_vc_lz(
                fit.decoded,
                stream_tag=1,
                offset_bits=12,
                max_encoded_size=len(fit.compressed) - 1,
            )

    def test_compressible_art_keeps_its_complete_palette(self) -> None:
        colors = (
            (0, 0, 0, 0), (255, 255, 255, 255),
            (20, 60, 140, 255), (210, 30, 40, 255),
        )
        rgba = b"".join(
            bytes(colors[((x // 8) ^ (y // 8)) & 3])
            for y in range(64) for x in range(64)
        )
        levels = make_mips(rgba, 64, 64, 4)

        def decoded(palette, index_levels) -> bytes:
            chain = b"".join(
                swizzle_2d(indices, level.width, level.height, 1)
                for indices, level in zip(index_levels, levels)
            )
            return bytes(128) + chain + palette_bytes(palette)

        fit = quantize_levels_to_vc_lz_bound(
            levels, decoded, stream_tag=1, offset_bits=12,
            max_encoded_size=1_568,
        )
        self.assertEqual(len(fit.palette), 4)
        self.assertEqual(len(fit.attempts), 1)
        self.assertEqual(fit.attempts[0]["result"], "fit")

    def test_number_and_sleeve_importers_use_the_same_bounded_path(self) -> None:
        for relative in (
            "tools/nfl_live_numbers_nameplate_png_import.py",
            "tools/nfl_sleeve_tset_png_import.py",
        ):
            with self.subTest(importer=relative):
                source = (_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("quantize_levels_to_vc_lz_bound(", source)


@unittest.skipUnless(
    _HAVE_REAL_COMPOSER_INPUTS,
    "private retail XISO/index inputs are unavailable",
)
class Real1568ByteComposedBuildTests(unittest.TestCase):
    """Exercise the public project route without storing a second 6.3 GB XISO.

    ``07H7:jersey_digit:1`` is a real 64x64 retail target whose complete VC-LZ
    body is capped at exactly 1,568 bytes.  The compositor binds the logical
    project edit to that target in the read-only XISO.  We then apply the
    prepared replacement to an actual source window with guards on both sides,
    close it, reopen it independently, and reparse the TXTR.  This is the same
    selected-span operation used by the full copier, without wasting six
    gigabytes on a redundant test artifact.
    """

    def test_hostile_number_art_falls_back_and_reopens_from_composed_xiso_window(
        self,
    ) -> None:
        import nfl2k5_visual_mod_project as project_builder
        import nfl_live_numbers_nameplate_png_import as live_import

        with tempfile.TemporaryDirectory(prefix="nfl-vclz-1568-composed-") as name:
            root = Path(name)
            hostile = root / "hostile-number.png"
            rng = random.Random(0x15682C05)
            hostile_rgba = bytes(
                rng.randrange(256) for _ in range(64 * 64 * 4)
            )
            hostile.write_bytes(encode_rgba_png(64, 64, hostile_rgba))
            project_path = root / "number.2k5-project.json"
            project_path.write_bytes(project_builder.canonical_json({
                "schema": project_builder.SCHEMA,
                "purpose": "Regression for the reported 1,568-byte number build",
                "edits": [{
                    "kind": "live_number_nameplate",
                    "asset_code": "07",
                    "side": "H",
                    "variant": 7,
                    "family": "jersey",
                    "digit": 1,
                    "png": hostile.name,
                }],
            }))

            project = project_builder.read_project(project_path)
            index_pin = project_builder.ownership.pin_large_file(
                _REAL_INDEX,
                "canonical extracted pack 0",
                project_builder.INDEX_SIZE,
                project_builder.INDEX_SHA256,
            )
            inventory_pin = None
            source_fd = None
            prepared = None
            try:
                inventory_pin = project_builder.ownership.pin_large_file(
                    _REAL_INVENTORY,
                    "canonical chunk inventory",
                    project_builder.INVENTORY_SIZE,
                    project_builder.INVENTORY_SHA256,
                )
                reports = project_builder.pin_reports({
                    "live_number_nameplate"
                })
                source_fd = os.open(
                    _REAL_XISO,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_BINARY", 0),
                )
                source_size = os.fstat(source_fd).st_size
                entries, _directory = project_builder.common.parse_xdvdfs(
                    source_fd, source_size
                )
                prepared = project_builder.prepare_project(
                    project,
                    index_pin,
                    inventory_pin,
                    reports,
                    root,
                    source_fd,
                    entries,
                )
                project_builder.ownership.assert_owned_tree(
                    prepared.temp_root, prepared.temp_files, []
                )
                project_builder.bind_prepared_to_source(
                    prepared, source_fd, entries
                )
                project_builder.verify_prepared_pins(
                    project, prepared, index_pin, inventory_pin
                )

                self.assertEqual(len(prepared.edits), 1)
                edit = prepared.edits[0]
                self.assertEqual(edit.kind, "live_number_nameplate")
                self.assertEqual(edit.selector, "07H7:jersey_digit:1")
                self.assertEqual(edit.target["stored_size"], 1_568)
                self.assertEqual(edit.replacement_size, 1_600)
                self.assertEqual(
                    edit.absolute,
                    entries[edit.pack_path.casefold()].byte_offset
                    + edit.pack_offset,
                )
                self.assertTrue(edit.relative_runs)

                import_report = json.loads(
                    edit.import_report_path.read_text(encoding="utf-8")
                )
                fit = import_report["bounded_palette_fit"]
                self.assertEqual(fit["stored_size_bound"], 1_568)
                self.assertEqual(fit["attempts"][0]["palette_entries"], 256)
                self.assertEqual(fit["attempts"][0]["result"], "vc_lz_overflow")
                self.assertEqual(fit["attempts"][-1]["result"], "fit")
                self.assertLess(fit["selected_palette_entries"], 256)
                self.assertLessEqual(fit["selected_encoded_bytes"], 1_568)

                guard = 4_096
                window_start = edit.absolute - guard
                source_window = project_builder.common.read_exact(
                    source_fd,
                    window_start,
                    guard + edit.replacement_size + guard,
                )
                replacement = edit.replacement_path.read_bytes()
                candidate_path = root / "composed-xiso-window.bin"
                candidate_path.write_bytes(source_window)
                candidate_fd = os.open(
                    candidate_path,
                    os.O_RDWR
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_BINARY", 0),
                )
                try:
                    # Exercise the same exact-offset writer as the public full
                    # XISO composer, but against only the bound source window.
                    project_builder.write_all(candidate_fd, guard, replacement)
                    os.fsync(candidate_fd)
                    self.assertEqual(
                        project_builder.common.read_exact(
                            candidate_fd, guard, edit.replacement_size
                        ),
                        replacement,
                    )
                finally:
                    os.close(candidate_fd)

                _resolved, reopened, _identity = (
                    project_builder.read_regular_bounded(
                        candidate_path,
                        len(source_window),
                        "composed XISO target window",
                    )
                )
                self.assertEqual(reopened[:guard], source_window[:guard])
                self.assertEqual(
                    reopened[guard + edit.replacement_size:],
                    source_window[guard + edit.replacement_size:],
                )
                reopened_span = reopened[guard:guard + edit.replacement_size]
                self.assertEqual(reopened_span, replacement)
                self.assertEqual(
                    project_builder.common.read_exact(
                        source_fd, window_start, len(source_window)
                    ),
                    source_window,
                    "the source XISO window changed during composition",
                )

                chunks = parse_chunks(reopened_span)
                self.assertEqual(len(chunks), 1)
                chunk = chunks[0]
                decoded, decode_info = decode_chunk(reopened_span, chunk)
                texture = parse_texture(decoded, chunk)
                levels = live_import.decode_levels(decoded, chunk, texture)
                self.assertIsNotNone(decode_info)
                self.assertLessEqual(decode_info.consumed_bytes, 1_568)
                preview_path = prepared.edits[0].preview_paths[0][1]
                preview = live_import.decode_rgba_png(
                    preview_path.read_bytes(), (64, 64)
                )
                self.assertEqual(preview[2], levels[0].rgba)
            finally:
                if source_fd is not None:
                    os.close(source_fd)
                if inventory_pin is not None:
                    os.close(inventory_pin.descriptor)
                os.close(index_pin.descriptor)
                if prepared is not None:
                    leftovers = project_builder.ownership.cleanup_owned(
                        prepared.temp_files, [prepared.temp_root]
                    )
                    self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "apf_helmet_crest_guard_band", TOOLS / "apf_helmet_crest_guard_band.py"
)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)


class HelmetCrestGuardBandTest(unittest.TestCase):
    def test_palette_and_safe_interval_are_exact(self) -> None:
        background = bytes((0, 0, 0, 136))
        rgba = bytearray(background * (512 * 512))
        for y in range(120, 392):
            for x in range(512):
                offset = (y * 512 + x) * 4
                rgba[offset : offset + 4] = bytes((255, (x % 16) * 17, 0, 136))
        result = guard.add_horizontal_guard(bytes(rgba))
        self.assertEqual(result.source_active_bbox, (0, 120, 511, 391))
        self.assertEqual(result.output_active_bbox, (64, 120, 447, 391))
        self.assertEqual(result.carrier_u_offset, 0.125)
        self.assertEqual(result.carrier_u_scale, 0.75)
        self.assertTrue(result.palette_values_preserved)
        for y in range(512):
            self.assertEqual(result.output_rgba[(y * 512) * 4 : (y * 512 + 64) * 4], background * 64)
            self.assertEqual(result.output_rgba[(y * 512 + 448) * 4 : (y + 1) * 512 * 4], background * 64)

    def test_empty_mask_is_rejected(self) -> None:
        with self.assertRaisesRegex(guard.GuardBandError, "no nonblack"):
            guard.add_horizontal_guard(bytes((0, 0, 0, 136)) * (512 * 512))

    def test_prepare_png_keeps_semantic_design_and_encodes_guard_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "design.png"
            image = Image.new("RGBA", (512, 512), (0, 0, 0, 136))
            for y in range(122, 390):
                for x in range(512):
                    image.putpixel((x, y), (255, 0, 0, 136))
            image.save(source, "PNG")
            prepared = guard.prepare_png(source)
            self.assertEqual(prepared.design_rgba, image.tobytes())
            self.assertEqual(prepared.guard.output_active_bbox, (64, 122, 447, 389))
            with Image.open(io.BytesIO(prepared.guarded_png)) as guarded:
                guarded.load()
                self.assertEqual(guarded.size, (512, 512))
                self.assertEqual(guarded.convert("RGBA").tobytes(), prepared.guard.output_rgba)


if __name__ == "__main__":
    unittest.main()

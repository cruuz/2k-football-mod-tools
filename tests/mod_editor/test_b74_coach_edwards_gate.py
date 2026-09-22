"""Beta 74 release gate: Coach Edwards' workflow, end to end, on the retail disc.

Every one of his six reports lived in the same chain: import equipment art,
build, read the build back. Each earlier beta fixed the symptom in front of
us and a new one surfaced behind it, because nothing ran that chain whole on
real data before a release. This does, through the same facade the Studio
window uses and with no Qt:

1. index the retail XISO (a fresh cache when none exists);
2. import a near-white independent sock into the Cardinals home set, the exact
   art that beta 73 refused with "Simplify the artwork" and that Build fits
   at 16 x 16, and expect it staged for Build instead of refused;
3. import a normal shoe texture (shared palette) into the same set and expect it
   fitted at full size;
4. run Build's own fit and refit over the uniform set 11H0 shoe span he
   reported for beta 74/74.1, where two own-texture shoe imports fill FOUR
   references of one 54,480-byte span because each shoe stages its mud twin,
   and expect one shared appended chain and a fitting refit rather than
   "Build tried every Refit equipment choice and none fits". That import
   stages 402 packages through the Studio, which no release gate can build,
   so it runs on the real retail span through the real compile path;
5. save the project and load it back, as he does to share it;
6. build a real disc through the real child builder and verifier, and read
   the receipts back: the sock refit is reported, the shoe fit is listed,
   the disc is the size of the source, no stage is left behind.

Opt in with ``NFL2K5_COACH_EDWARDS_GATE=1``: it hashes the source, writes a
6 GB disc beside the scratch folder and deletes it again, and takes minutes.
Run it niced through ``tools/coach_edwards_gate.sh`` before every release.
Nothing here claims an in-game result; Noah witnesses that.
"""
import io
import os
from pathlib import Path
import random
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO",
                           "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
SCRATCH = Path(os.environ.get("NFL2K5_GATE_SCRATCH", ROOT / ".scratch/coach-edwards-gate"))
SOCK = "tset:3621:4:0:socks00"
SHOE = "tset:3621:8:0:shoes01"
# Uniform set 11H0, the span in his beta 74/74.1 refusal: two shoe imports,
# four references, one 54,480-byte span with 9 bytes of retail slack.
SHARED_SPAN_SHOES = ("tset:3702:8:0:shoes01", "tset:3702:8:1:shoes01_mud",
                     "tset:3702:8:2:shoes04", "tset:3702:8:3:shoes04_mud")


def _near_white_sock_png():
    """64x64, mostly white with faint variation: fits at 16x16, not at 64x64 independent."""
    from PIL import Image
    rng = random.Random(3)
    image = Image.new("RGBA", (64, 64), (255, 255, 255, 255))
    pixels = image.load()
    for i in range(64 * 64):
        if rng.random() < 0.5:
            value = rng.randrange(200, 256)
            pixels[i % 64, i // 64] = (value, value, rng.randrange(200, 256), 255)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _striped_png(width, height):
    """A plain three-colour stripe, the kind of shoe art that fits at full size."""
    from PIL import Image
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    for y in range(height):
        colour = ((20, 60, 140, 255), (240, 245, 250, 255), (170, 35, 55, 255))[(y // 7) % 3]
        for x in range(width):
            pixels[x, y] = colour
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _plain_shoe_png(width, height):
    """Plain art: a white shoe with one dark sole band, the kind he imports."""
    from PIL import Image
    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    pixels = image.load()
    for y in range(height * 25 // 32, height):
        for x in range(width):
            pixels[x, y] = (30, 30, 34, 255)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class _Progress:
    """The facade's progress sink; prints a line at most every 15 seconds."""

    def __init__(self):
        self.last = 0.0
        self.cancelled = None

    def __call__(self, stage, completed, total):
        now = time.monotonic()
        if now - self.last > 15:
            print(f"  {stage}: {completed}/{total}", flush=True)
            self.last = now


@unittest.skipUnless(os.environ.get("NFL2K5_COACH_EDWARDS_GATE") == "1" and XISO.is_file(),
                     "set NFL2K5_COACH_EDWARDS_GATE=1 with the retail XISO present")
class CoachEdwardsWorkflowGate(unittest.TestCase):
    def test_import_save_load_build_and_readback_on_the_retail_disc(self):
        from mod_editor.studio.facade import Nfl2k5StudioFacade
        SCRATCH.mkdir(parents=True, exist_ok=True)
        progress = _Progress()
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="gate-", dir=SCRATCH) as temp:
            folder = Path(temp).resolve()
            facade = Nfl2k5StudioFacade()
            print("indexing the retail disc", flush=True)
            facade.load_source(XISO, progress)
            print(f"  indexed in {time.monotonic() - started:.0f}s", flush=True)
            catalog = facade.visual_catalog
            sock = catalog.get_asset(SOCK)
            shoe = catalog.get_asset(SHOE)
            self.assertEqual((sock.width, sock.height), (64, 64))

            sock_png = folder / "cardinals-sock.png"
            sock_png.write_bytes(_near_white_sock_png())
            shoe_png = folder / "cardinals-shoe.png"
            shoe_png.write_bytes(_striped_png(shoe.width, shoe.height))

            # 2. The sock beta 73 refused: staged for Build, not refused.
            staged = facade.replace_equipment_texture(
                sock, sock_png, progress, independent=True, scale=1, scope=None)
            self.assertFalse(isinstance(staged, Exception), staged)
            self.assertIn("Build refits it automatically", staged.message)
            # 3. A normal shoe on the shared palette: fitted at import at full size.
            fitted = facade.replace_equipment_texture(
                shoe, shoe_png, progress, independent=False, scale=1, scope=None)
            self.assertFalse(isinstance(fitted, Exception), fitted)
            self.assertIn("fitted at", fitted.message)

            # 4. The 11H0 shared shoe span: Build's own fit and refit, on the
            # real retail bytes, for the four references his import fills.
            from mod_editor.core import nfl2k5_uniform_equipment_writer as equipment
            from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
            from nfl_tset_png_import import decode_rgba_png

            shoes = catalog.get_asset(SHARED_SPAN_SHOES[0])
            plain = _plain_shoe_png(shoes.width, shoes.height)
            rgba = decode_rgba_png(plain, (shoes.width, shoes.height))[2]
            shoe_edits = []
            for asset_id in SHARED_SPAN_SHOES:
                path = folder / (asset_id.replace(":", "_") + ".png")
                path.write_bytes(with_import_mode(plain, asset_id, rgba, independent=True, scale=1))
                shoe_edits.append((asset_id, path))
            refit_folder = folder / "shared-span-refits"
            refit_folder.mkdir()
            print("fitting the 11H0 shoe span", flush=True)
            span_at = time.monotonic()
            # The private index the Studio session uses for this indexed disc.
            pack0 = facade._cache.pack0
            fitted_rows, substitutes, refitted = equipment.auto_refit_group(
                pack0, shoe_edits, refit_folder, heartbeat=lambda note: None)
            print(f"  fitted in {time.monotonic() - span_at:.0f}s", flush=True)
            self.assertEqual([row["fit_status"] for row in fitted_rows], ["fits"] * 4)
            self.assertEqual(len({row["pixel_offset"] for row in fitted_rows}), 1)
            self.assertEqual(sorted(record["asset_id"] for record in refitted),
                             sorted(SHARED_SPAN_SHOES))
            for record in refitted:
                self.assertIn("fitted at", record["fit_summary"])
            for asset_id, path in shoe_edits:
                path.write_bytes(substitutes[asset_id])
            compiled = equipment.build_unified_uniform_equipment_imports(
                pack0, shoe_edits, preflight_only=True, suggest_fit=False)
            self.assertEqual(compiled.rebuild_info.stored_size, 54_480)
            self.assertLessEqual(compiled.rebuild_info.recompressed_bytes, 54_480)
            self.assertTrue(compiled.rebuild_info.loader_in_place_end_guard)
            self.assertTrue(compiled.rebuild_info.loader_in_place_alias_guard)
            self.assertEqual(compiled.rebuild_info.rebuilt_overlap_scratch_bytes,
                             compiled.rebuild_info.original_overlap_scratch_bytes)
            print("  " + "; ".join(f"{record['asset_id']} {record['fit_summary']}"
                                   for record in refitted), flush=True)

            # 5. Save and reload the project, as he does to share it.
            project = folder / "cardinals.2k5mod"
            facade.save_project(project, progress)
            self.assertTrue(project.is_file())
            loaded = facade.load_project(project, progress)
            self.assertIn("Equipment needs refit", loaded.message)
            self.assertIn(SOCK, loaded.message)

            # 6. A real build through the real child, and the readback.
            output = folder / "Cardinals test disc.xiso.iso"
            print("building the disc", flush=True)
            built_at = time.monotonic()
            result = facade.build_iso(output, progress)
            print(f"  built in {time.monotonic() - built_at:.0f}s", flush=True)
            self.assertTrue(output.is_file())
            self.assertEqual(output.stat().st_size, XISO.stat().st_size)
            refits = "\n".join(result.refitted)
            self.assertIn("socks00", refits)
            self.assertIn("16 x 16", refits)
            summary = "\n".join(result.texture_summary)
            self.assertIn("shoes01", summary)
            self.assertIn("fitted at", summary)
            live = [p for p in folder.glob(f".{output.name}.2k5mod-*")]
            self.assertEqual(live, [])
            output.unlink()
            print("\n".join(result.refitted + result.texture_summary), flush=True)
        print(f"gate passed in {time.monotonic() - started:.0f}s", flush=True)


if __name__ == "__main__":
    unittest.main()

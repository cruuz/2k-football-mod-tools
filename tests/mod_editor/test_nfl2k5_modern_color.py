"""Modern colour and lighting: pure transforms, light-rig receipts, and retail-gated bundle proofs."""
from __future__ import annotations

import colorsys
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_modern_color as mc  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_INDEX", "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
GAME = mc._game_folder(RETAIL) if RETAIL.exists() else None
XBE = GAME / "default.xbe" if GAME else None


def _hsv(b, g, r):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return h * 360, s, v


class PaletteTransformTests(unittest.TestCase):
    def test_green_entries_move_toward_target_and_desaturate(self):
        pal = bytearray(1024)
        pal[0:4] = bytes((66, 125, 100, 255))   # retail Arrowhead colour-map median, B,G,R,A
        pal[4:8] = bytes((10, 10, 200, 255))    # red: untouched
        pal[8:12] = bytes((240, 240, 240, 255))  # white line: untouched
        out = mc.regrade_palette(bytes(pal))
        h0, s0, v0 = _hsv(*pal[0:3]); h1, s1, v1 = _hsv(*out[0:3])
        self.assertLess(abs(h1 - mc.HUE_TARGET), abs(h0 - mc.HUE_TARGET), "hue pulled toward the target")
        self.assertLess(s1, s0); self.assertGreaterEqual(v1, v0 - 0.01)
        far = bytes((30, 120, 120, 255)) * 256  # a yellow-green at 60 degrees moves up toward 82
        fh0 = _hsv(*far[0:3])[0]; fh1 = _hsv(*mc.regrade_palette(far)[0:3])[0]
        self.assertGreater(fh1, fh0); self.assertLess(fh1, mc.HUE_TARGET)
        self.assertEqual(out[4:12], bytes(pal[4:12]))
        self.assertEqual(out[3], 255)
        self.assertEqual(len(out), 1024)
        self.assertEqual(mc.regrade_palette(out), mc.regrade_palette(out), "deterministic")

    def test_material_colour_word_regrade_keeps_alpha_and_non_greens(self):
        self.assertNotEqual(mc.regrade_colour_word(0xFF37683B), 0xFF37683B)
        self.assertEqual(mc.regrade_colour_word(0xFF37683B) >> 24, 0xFF)
        self.assertEqual(mc.regrade_colour_word(0xFFFFFFFF), 0xFFFFFFFF)
        self.assertEqual(mc.regrade_colour_word(0xFF6C7933) >> 24, 0xFF)

    def test_normal_flatten_raises_z_and_leaves_non_normal_palettes(self):
        pal = bytearray()
        for i in range(256):
            x, y = (i % 16) / 8 - 1, (i // 16) / 8 - 1
            z = (max(0.0, 1 - x * x - y * y)) ** 0.5
            enc = lambda c: min(255, max(0, round((c + 1) * 127.5)))
            pal += bytes((enc(z), enc(y), enc(x), 255))
        out = mc.flatten_normal_palette(bytes(pal))
        self.assertTrue(mc.looks_like_normal_palette(bytes(pal)))
        zs_before = sum(pal[i * 4] for i in range(256)); zs_after = sum(out[i * 4] for i in range(256))
        self.assertGreater(zs_after, zs_before)
        self.assertEqual(out[3], 255)
        plain = bytes(range(256)) * 4
        self.assertEqual(mc.flatten_normal_palette(plain), plain)

    def test_tints(self):
        self.assertEqual(mc.TINTS[0xFFFFEECD], 0xFFFFF5E6)
        self.assertEqual(mc.TINTS[0xFFF2FFFF], 0xFFF8FCFF)
        for before, after in mc.VERTEX_TINTS.items():
            self.assertEqual(after[3], 255)
            self.assertLess(max(after[:3]) - min(after[:3]), max(before[:3]) - min(before[:3]), "tint moves toward neutral")
        for before, after in mc.TINTS.items():
            spread = lambda w: max((w >> 16) & 255, (w >> 8) & 255, w & 255) - min((w >> 16) & 255, (w >> 8) & 255, w & 255)
            self.assertLess(spread(after), spread(before)); self.assertEqual(after >> 24, 0xFF)


class LightRigTests(unittest.TestCase):
    def test_rig_definitions_match_retail_light_counts(self):
        counts = {"day": 2, "night_indoor": 3, "alt_day": 3, "alt_dynamic": 3, "rain": 3, "snow": 3, "afternoon": 3}
        for name, rig in mc.MODERN_RIGS.items():
            self.assertEqual(len(rig["lights"]), counts[name], name)
            for channel in rig["ambient"]:
                self.assertTrue(0.5 <= channel <= 1.0)
            self.assertTrue(0.3 <= rig["ambient_intensity"] <= 0.6)
            for colour, intensity in rig["lights"]:
                self.assertTrue(all(0.5 <= c <= 1.0 for c in colour))
                self.assertTrue(0.15 <= intensity <= 1.2, name)
            # A neutral rig: no channel darker than 0.84 of the brightest on the key light.
            key = rig["lights"][0][0]
            self.assertGreaterEqual(min(key) / max(key), 0.84, name)

    @unittest.skipUnless(XBE and XBE.is_file(), "retail executable not available")
    def test_retail_tables_apply_replay_restore_and_foreign(self):
        payload = XBE.read_bytes()
        self.assertEqual(mc.xbe_status(payload), "retail")
        patched, receipt = mc.apply(payload)
        self.assertEqual(mc.xbe_status(patched), "applied")
        self.assertEqual(receipt["state"], "applied")
        self.assertEqual(len(receipt["edits"]), len(mc.LIGHT_TABLES))
        self.assertEqual(receipt["changed_bytes"], sum(a != b for a, b in zip(payload, patched)))
        again, again_receipt = mc.apply(patched)
        self.assertEqual(again, patched); self.assertEqual(again_receipt["edits"], [])
        restored, _ = mc.apply(patched, enabled=False)
        self.assertEqual(restored, payload)
        image = mc.XbeImage(payload)
        for name, va, _digest in mc.LIGHT_TABLES:
            before = image.read(va, mc.TABLE_SIZE); after = mc.XbeImage(patched).read(va, mc.TABLE_SIZE)
            self.assertEqual(before[0x14:0x18], after[0x14:0x18], "light count")
            self.assertEqual(before[0x100:0x120], after[0x100:0x120], "shadow value and tail")
            count = struct.unpack_from("<I", before, 0x14)[0]
            for i in range(count):
                base = 0x20 + i * 0x40
                self.assertEqual(before[base + 0x10:base + 0x20], after[base + 0x10:base + 0x20], "direction")
        broken = bytearray(patched); at = image.offset(mc.LIGHT_TABLES[0][1], 4); broken[at] ^= 1
        self.assertEqual(mc.xbe_status(bytes(broken)), "foreign")
        with self.assertRaises(ValueError):
            mc.apply(bytes(broken))
        self.assertEqual(len(mc.reservations(patched)), len(mc.LIGHT_TABLES))
        mc.verify(patched); mc.verify(payload, enabled=False)


class BundleStateTests(unittest.TestCase):
    def test_sites_the_option_leaves_alone_do_not_make_a_bundle_mixed(self):
        class Entry:
            name_id, size, virtual_offset = 7, 64, 0

        class Archive:
            entries = {3: Entry()}

            def __init__(self, blob):
                self.blob = blob

            def read(self, at, size):
                return self.blob[at:at + size]
        retail = bytes(range(64)); after = bytearray(retail); after[0] ^= 1; after = bytes(after)
        pin = dict(name="x", outer=3, name_id=7, size=64, sites=[
            dict(kind="field", offset=0, size=8, retail=hashlib.sha256(retail[:8]).hexdigest(), applied=hashlib.sha256(after[:8]).hexdigest()),
            dict(kind="tint", offset=8, size=4, retail=hashlib.sha256(retail[8:12]).hexdigest(), applied=hashlib.sha256(retail[8:12]).hexdigest())])
        self.assertEqual(mc._bundle_state(Archive(retail), pin), "retail")
        self.assertEqual(mc._bundle_state(Archive(after), pin), "applied")
        broken = bytearray(after); broken[9] ^= 1
        self.assertEqual(mc._bundle_state(Archive(bytes(broken)), pin), "foreign")
        untouched = dict(pin, sites=[pin["sites"][1]])
        self.assertEqual(mc._bundle_state(Archive(retail), untouched), "applied")


class BundleTests(unittest.TestCase):
    @unittest.skipUnless(GAME and (GAME / "vc_53450030").is_dir(), "retail extraction not available")
    def test_arrowhead_night_bundle_transform_matches_pins(self):
        pins = mc._pins()
        row = next(r for r in pins["bundles"] if r["name"] == "s13nd.iff")
        with mc._outer_image()(GAME / "vc_53450030") as archive:
            entry = archive.entries[row["outer"]]
            data = archive.read(entry.virtual_offset, entry.size)
        self.assertEqual(hashlib.sha256(data).hexdigest(), row["retail_sha256"])
        after, edits = mc.modern_bundle(data, outer_index=row["outer"])
        self.assertEqual(len(after), len(data))
        self.assertEqual(hashlib.sha256(after).hexdigest(), row["applied_sha256"])
        kinds = [e["kind"] for e in edits]
        self.assertEqual(kinds, ["field", "normal", "tint"])
        field = edits[0]
        self.assertTrue(field["refit"]); self.assertEqual(len(field["palettes"]), 2)
        tint = edits[2]
        self.assertNotEqual(tint["before_sha256"], tint["after_sha256"], "night tint softened")
        # Decoded colour map moved toward the broadcast turf: less yellow, less saturated.
        tx, inv, ResourceRecord, HEADER = mc._tools()
        for payload in (data, after):
            chunk = tx.parse_chunks(payload, allow_trailing=True)[0]
            rec, out, record = mc._scene(payload, chunk, row["outer"])
            texture = next(t for t in rec["embedded_textures"] if t.get("mapped_material_names") == ["color_premipped"])
            info = inv.texture_info(out, texture["descriptor_offset"], rec["name"], texture["index"])
            rgba = tx.texture_to_rgba(out, record.as_chunk(), info)
            pixels = [rgba[i:i + 3] for i in range(0, len(rgba), 4)]
            mean = [sum(p[c] for p in pixels) / len(pixels) for c in range(3)]
            h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in mean))
            if payload is data:
                retail_hsv = (h * 360, s, v)
            else:
                self.assertLess(s, retail_hsv[1], "less saturated"); self.assertGreater(v, retail_hsv[2] - 0.005, "not darker")
                self.assertLessEqual(abs(h * 360 - mc.HUE_TARGET), abs(retail_hsv[0] - mc.HUE_TARGET) + 0.5, "hue at or toward the target")

    @unittest.skipUnless(GAME and (GAME / "vc_53450030").is_dir(), "retail extraction not available")
    def test_pins_cover_every_bundle_and_statuses(self):
        pins = mc._pins()
        self.assertEqual(len(pins["bundles"]), 477)
        self.assertEqual(len(pins["light_tables"]), len(mc.LIGHT_TABLES))
        self.assertEqual(mc.image_status(GAME / "vc_53450030"), "retail")


if __name__ == "__main__":
    unittest.main(verbosity=2)

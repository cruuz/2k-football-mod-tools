"""W1: wet-uniform repair (rain rig ambient head, rain fog start/end, 210 kit mud spans) and its Studio counterparts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
import w1_repair as w1  # noqa: E402
from mod_editor.core import nfl2k5_modern_color as mc  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_INDEX",
                                 "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")).parents[1] / "default.xbe"
DISC = Path("/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso")


def v05_like(retail: bytes) -> bytes:
    """Retail default.xbe with the two owned ranges set to the v0.5 bytes and the section digests refreshed."""
    image, out = XbeImage(retail), bytearray(retail)
    # v0.5 already carries the Studio's rain lights (colour and intensity); only the head (ambient) differs from the new table
    rain = mc.modern_table(image.read(0x4e7830, mc.TABLE_SIZE))
    at = image.offset(0x4e7830, mc.TABLE_SIZE)
    out[at:at + mc.TABLE_SIZE] = rain
    for _label, va, before, _after in w1.XBE_SITES:
        at = image.offset(va, len(before))
        out[at:at + len(before)] = before
    for section in _sections(out):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(out, section)
    return bytes(out)


class MudRuleTests(unittest.TestCase):
    def test_wet_rule_matches_the_studio_mode_and_retail_range(self):
        import nfl_tset_png_import as legacy
        palette = [(252, 252, 252, 255), (0, 0, 0, 255), (10, 200, 90, 128)]
        self.assertEqual([tuple(w1.wet(c) for c in p[:3]) + (p[3],) for p in palette], legacy.derive_mud_palette(palette, "wet_93"))
        self.assertEqual(w1.wet(252), 234)          # retail white away jersey 252 -> 236 (0.936)
        self.assertTrue(0.92 <= w1.wet(252) / 252 <= 0.94)
        self.assertEqual(w1.dark(252), 151)         # what v0.5 shipped: grey
        for value in range(256):
            self.assertLessEqual(w1.wet(value), value)

    def test_kit_manifest_is_complete_and_pinned_to_the_shipped_sets(self):
        manifest = json.loads(w1.KIT_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], w1.KIT_MANIFEST_SCHEMA)
        spans = manifest["spans"]
        self.assertEqual(len(spans), 210)
        self.assertEqual({s["selector"] for s in spans}, set(w1.kit_selectors()))
        self.assertEqual({s["chunk"] for s in spans}, {1, 2, 3})
        for selector in w1.kit_selectors():
            self.assertEqual(sorted(s["chunk"] for s in spans if s["selector"] == selector), [1, 2, 3])
        self.assertTrue(all(s["before_sha256"] != s["after_sha256"] and s["changed_entries"] > 0 for s in spans))
        ends = sorted((s["pack"], s["pack_offset"], s["pack_offset"] + s["length"]) for s in spans)
        for a, b in zip(ends, ends[1:]):
            self.assertTrue(a[0] != b[0] or a[2] <= b[1], "spans do not overlap")


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail executable not available")
class XbeRepairTests(unittest.TestCase):
    def setUp(self):
        self.retail = RETAIL_XBE.read_bytes()
        self.payload = v05_like(self.retail)

    def test_new_bytes_are_exactly_what_the_studio_writes(self):
        image = XbeImage(self.retail)
        rig = mc.modern_table(image.read(0x4e7830, mc.TABLE_SIZE))
        fog = mc.modern_fog()
        (_, _, _, rig_after), (_, _, _, fog_after) = w1.XBE_SITES
        self.assertEqual(rig[:20], rig_after)
        self.assertEqual(fog[8:16], fog_after)
        # the owned head is the only part of the rain rig that differs from the v0.5 rig the old Studio default wrote
        self.assertEqual(rig[20:], mc.modern_table(image.read(0x4e7830, mc.TABLE_SIZE))[20:])

    def test_repair_is_scoped_idempotent_and_matches_the_studio_result(self):
        digest = hashlib.sha256(self.payload).hexdigest()
        fixed, receipt = w1.repair_xbe(self.payload, expected_input_sha256=digest)
        again, again_receipt = w1.repair_xbe(fixed, expected_input_sha256=hashlib.sha256(fixed).hexdigest())
        self.assertEqual(fixed, again)
        self.assertTrue(again_receipt["already_applied"] and not receipt["already_applied"])
        self.assertTrue(receipt["outside_scope_identical"])
        labels = {r["label"] for r in receipt["ranges"]}
        self.assertEqual(labels, {"rain_rig_ambient_head", "rain_fog_start_end", "section_12_sha1", "section_13_sha1"})
        self.assertEqual(receipt["changed_bytes"], sum(a != b for a, b in zip(self.payload, fixed)))
        studio, _ = mc.apply(self.retail)
        a, b = XbeImage(fixed), XbeImage(studio)
        self.assertEqual(a.read(0x4e7830, mc.TABLE_SIZE), b.read(0x4e7830, mc.TABLE_SIZE))
        self.assertEqual(a.read(0xA86804, 20), b.read(0xA86804, 20))
        for section in _sections(fixed):
            self.assertEqual(section.stored_digest, section_digest(fixed, section), "section digests are refreshed")

    def test_foreign_bytes_are_refused(self):
        image = XbeImage(self.payload)
        broken = bytearray(self.payload)
        broken[image.offset(0x4e7830, 4)] ^= 0x40
        with self.assertRaisesRegex(ValueError, "unexpected bytes"):
            w1.repair_xbe(bytes(broken), expected_input_sha256=hashlib.sha256(bytes(broken)).hexdigest())
        with self.assertRaisesRegex(ValueError, "unexpected bytes"):
            w1.repair_xbe(self.retail, expected_input_sha256=hashlib.sha256(self.retail).hexdigest())


@unittest.skipUnless(DISC.is_file(), "v0.5 disc is not available")
class KitSpanTests(unittest.TestCase):
    def test_first_kit_chunk_rebuilds_to_its_pinned_span_in_the_same_size(self):
        from mod_editor.core import nfl2k5_bump_texture_writer as bump
        row = json.loads(w1.KIT_MANIFEST.read_text(encoding="utf-8"))["spans"][0]
        with bump._Image.open(DISC, writable=False) as image:
            span = image.read_pack(row["pack"], row["pack_offset"], row["length"])
        self.assertEqual(hashlib.sha256(span).hexdigest(), row["before_sha256"])
        new, receipt = w1.rewrite_chunk(span)
        self.assertEqual(len(new), len(span))
        self.assertEqual(hashlib.sha256(new).hexdigest(), row["after_sha256"])
        self.assertEqual(receipt["changed_entries"], row["changed_entries"])
        again, again_receipt = w1.rewrite_chunk(new)
        self.assertIs(again, new)
        self.assertEqual(again_receipt["changed_entries"], 0)


if __name__ == "__main__":
    unittest.main()

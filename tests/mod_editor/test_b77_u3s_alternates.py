"""Job u3s (beta 77): the derive-recipe alternate pipeline and its native repair.

Model tests build tiny synthetic exports; nothing reads a disc. The repair's span logic runs on synthetic packs."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

import u3s_alternates as ua  # noqa: E402
import u3s_repair as ur  # noqa: E402

ORANGE, WHITE, BLACK, RED = (255, 80, 20), (255, 255, 255), (0, 0, 0), (200, 16, 46)


def rgba(colours: list[tuple[int, int, int]]) -> np.ndarray:
    a = np.ones((1, len(colours), 4), np.float32)
    a[0, :, :3] = np.array(colours, np.float32) / 255.0
    return a


class RemixTests(unittest.TestCase):
    rule = {"from": ["#FF5014", "#FFFFFF", "#000000"], "to": ["#FFFFFF", "#FFFFFF", "#000000"], "tolerance": 0.1}

    def test_blends_of_the_shell_colour_are_rebuilt_and_other_colours_stay(self) -> None:
        half_black = tuple(int(round(c * 0.5)) for c in ORANGE)
        half_white = tuple(int(round((o + 255) / 2)) for o in ORANGE)
        src = rgba([ORANGE, BLACK, WHITE, half_black, half_white, RED, (128, 128, 128)])
        out, changed = ua.recolour(src, self.rule)
        got = (out[0, :, :3] * 255 + 0.5).astype(int)
        np.testing.assert_allclose(got[0], WHITE, atol=2)        # the shell
        np.testing.assert_allclose(got[1], BLACK, atol=1)        # a stripe stays black
        np.testing.assert_allclose(got[2], WHITE, atol=1)
        np.testing.assert_allclose(got[3], (128, 128, 128), atol=3)   # an anti-aliased stripe edge
        np.testing.assert_allclose(got[4], WHITE, atol=3)        # a shell-to-white edge leaves no orange fringe
        np.testing.assert_array_equal(got[5], RED)               # the flag and shield are not blends
        np.testing.assert_array_equal(got[6], (128, 128, 128))   # grey hardware holds no shell colour
        self.assertEqual(changed, 3)

    def test_regions_and_exclusions_limit_the_rule(self) -> None:
        src = np.ones((4, 4, 4), np.float32)
        src[..., :3] = np.array(ORANGE, np.float32) / 255.0
        out, changed = ua.recolour(src, dict(self.rule, exclude=[[0, 0, 2, 4]]))
        self.assertEqual(changed, 8)
        np.testing.assert_allclose(out[:, :2, :3], src[:, :2, :3])
        out, changed = ua.recolour(src, dict(self.rule, region="box"), {"box": (1, 1, 3, 3)})
        self.assertEqual(changed, 4)


class UnifRecordTests(unittest.TestCase):
    def test_the_colour_words_are_read_from_a_checked_header(self) -> None:
        package = bytearray(0x60)
        package[:5] = b"UnifP"
        package[0x2C:0x30] = b"Unif"
        package[0x40:0x50] = "uniform\0".encode("utf-16le")
        struct.pack_into("<II", package, 0x50, 0xFF9598A2, 0xFF171DA1)
        self.assertEqual(ua.unif_words(bytes(package)), {"facemask": "FF9598A2", "turtleneck": "FF171DA1"})
        package[0x2C] = 0
        with self.assertRaises(SystemExit):
            ua.unif_words(bytes(package))


class EditMappingTests(unittest.TestCase):
    def test_every_component_maps_to_the_studios_edit_kind(self) -> None:
        png = Path("x.png")
        cases = {
            ("torso.png", "TSET", 1, 0): ("torso", None),
            ("pants.png", "TSET", 2, 0): ("pants", None),
            ("sleeve.png", "TSET", 3, 0): ("sleeve", None),
            ("socks00.png", "TSET", 4, 0): ("uniform_equipment_texture", "tset:3665:4:0:socks00"),
            ("socks00_mud.png", "TSET", 4, 1): ("uniform_equipment_texture", "tset:3665:4:1:socks00_mud"),
            ("helmet_helmet02.png", "TXTR", 12, 0): ("live_helmet", "helmet02"),
            ("digit_jersey_7.png", "TXTR", 20, 0): ("live_number_nameplate", "jersey_digit"),
            ("digit_helmet_0.png", "TXTR", 23, 0): ("live_number_nameplate", "helmet_digit"),
            ("digit_arm_9.png", "TXTR", 42, 0): ("live_number_nameplate", "arm_digit"),
            ("names.png", "TXTR", 43, 0): ("live_number_nameplate", "nameplate"),
            ("splayer.png", "TXTR", 51, 0): ("p8_texture", "p8:3665:splayer"),
            ("flipchip.png", "TXTR", 52, 0): ("p8_texture", "p8:3665:flipchip"),
        }
        for (file, kind, chunk, index), (edit_kind, detail) in cases.items():
            asset = {"file": file, "kind": kind, "chunk": chunk, "tset_index": index}
            (edit,) = ua.edit_for("06H5", asset, 3665, png)
            self.assertEqual(edit["kind"], edit_kind, file)
            if edit_kind in ("torso", "pants", "sleeve"):
                self.assertEqual((edit["asset_code"], edit["side"], edit["variant"], edit["mud_mode"]),
                                 ("06", "H", 5, "darken_60"))
            elif edit_kind in ("uniform_equipment_texture", "p8_texture"):
                self.assertEqual(edit["asset_id"], detail)
            else:
                self.assertEqual(edit["family"], detail)
        self.assertEqual(ua.edit_for("06A5", {"file": "digit_jersey_7.png", "kind": "TXTR", "chunk": 20,
                                              "tset_index": 0}, 3982, png)[0]["digit"], 7)
        with self.assertRaises(SystemExit):
            ua.edit_for("06H5", {"file": "bump_jersey.png", "kind": "TXTR", "chunk": 45, "tset_index": 0}, 3665, png)


def save(path: Path, colour, size=(8, 8), alpha=255) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, tuple(colour) + (alpha,)).save(path)


class AuthorTests(unittest.TestCase):
    def test_a_derive_recipe_on_a_synthetic_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "export"
            assets = [("torso.png", "TSET", 1, 0, (8, 8)), ("helmet_helmet02.png", "TXTR", 12, 0, (8, 8)),
                      ("socks00.png", "TSET", 4, 0, (8, 8)), ("digit_helmet_0.png", "TXTR", 23, 0, (8, 8)),
                      ("glove01.png", "TSET", 6, 0, (8, 8)), ("bump_jersey.png", "TXTR", 45, 0, (8, 8))]
            doc = {"kits": {}}
            for sel in ("06A0", "06H5", "06A5"):
                unif = {"facemask": "FF000000", "turtleneck": "FFDB3E06" if sel == "06A0" else "FF0C254D"}
                doc["kits"][sel] = {"outer_index": {"06A0": 3977, "06H5": 3665, "06A5": 3982}[sel], "unif": unif,
                                    "assets": [
                    {"file": f, "name": f[:-4], "kind": k, "chunk": c, "tset_index": i, "size": list(s)}
                    for f, k, c, i, s in assets]}
            for f, *_ in assets:
                save(exp / "uniforms/06A0" / f, WHITE if f == "torso.png" else ORANGE if "helmet" in f else BLACK)
                for sel in ("06H5", "06A5"):
                    save(exp / "uniforms" / sel / f, BLACK if f == "glove01.png" else (90, 90, 90))
            (exp / "export.json").write_text(json.dumps(doc))
            recipe = {"team": "CIN", "code": "06", "style": 5, "set": "White Bengal", "build_type": "derive",
                      "kits": {"H": {"donor": "06A0"}, "A": {"donor": "06A0"}},
                      "recolour": [{"components": ["helmet_helmet02"], "from": ["#FF5014", "#FFFFFF", "#000000"],
                                    "to": ["#FFFFFF", "#FFFFFF", "#000000"], "tolerance": 0.1}],
                      "blank": ["digit_helmet_*"], "socks": {"colour": "#FFFFFF"}}
            out = ua.author(recipe, exp, root / "art")
            files = [e for e in out["edits"] if e["kind"] != "unif_color"]
            kinds = sorted((e["kind"], Path(e.get("png") or e.get("clean_png")).name) for e in files
                           if Path(e.get("png") or e.get("clean_png")).parent.name == "06H5")
            # the glove equals the slot's own texture (no edit); the relief map is never written
            self.assertEqual(kinds, [("live_helmet", "helmet_helmet02.png"),
                                     ("live_number_nameplate", "digit_helmet_0.png"),
                                     ("torso", "torso.png"), ("uniform_equipment_texture", "socks00.png")])
            helmet = np.asarray(Image.open(root / "art/06H5/helmet_helmet02.png"))
            self.assertTrue((helmet[..., :3] >= 253).all())
            self.assertEqual(int(np.asarray(Image.open(root / "art/06H5/digit_helmet_0.png"))[..., 3].max()), 0)
            socks = np.asarray(Image.open(root / "art/06A5/socks00.png")).astype(int)
            self.assertTrue((socks[..., :3] >= 215).all())
            colour = [e for e in out["edits"] if e["kind"] == "unif_color"]
            self.assertEqual(sorted(e["selector"] for e in colour), ["06A5", "06H5"])    # the donor's turtleneck word
            self.assertEqual(colour[0]["turtleneck"], "FFDB3E06")
            self.assertEqual(len(out["edits"]), 10)


def patch(offset: int, before: bytes, after: bytes, label: str = "span") -> dict:
    import hashlib
    return {"offset": offset, "length": len(after), "label": label, "resource": "06H5.IFF",
            "resource_offset": offset, "before_sha256": hashlib.sha256(before).hexdigest(),
            "after_sha256": hashlib.sha256(after).hexdigest(), "data": after}


class RepairSpanTests(unittest.TestCase):
    def test_spans_apply_once_and_prove_the_rest_identical(self) -> None:
        original = bytes(range(256)) * 4
        patches = [patch(16, original[16:20], b"ABCD"), patch(100, original[100:102], b"xy")]
        data, receipt = ur.apply_patches(original, patches)
        self.assertEqual(data[16:20], b"ABCD")
        self.assertTrue(receipt["outside_scope_identical"])
        self.assertEqual(sum(a != b for a, b in zip(original, data)), 6)
        again, second = ur.apply_patches(data, patches)
        self.assertEqual(again, data)
        self.assertTrue(all(s["already_applied"] for s in second["spans"]))

    def test_unexpected_input_and_overlaps_are_refused(self) -> None:
        original = bytes(64)
        with self.assertRaises(ValueError):
            ur.apply_patches(original, [patch(8, b"\x01\x01\x01\x01", b"ABCD")])
        with self.assertRaises(ValueError):
            ur.apply_patches(original, [patch(8, bytes(4), b"ABCD"), patch(10, bytes(4), b"EFGH")])
        with self.assertRaises(ValueError):
            ur.apply_patches(original, [patch(62, bytes(4), b"ABCD")])

    def test_a_manifest_may_name_only_its_own_slot(self) -> None:
        recipes = {"alternates": {"CIN:5": {"code": "06", "style": 5, "kits": {"H": {}, "A": {}}}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            for resources, ok in (({"06H5.IFF": [], "06A5.IFF": [], "outer:3102": []}, True),
                                  ({"16H0.IFF": []}, False), ({"outer:5": []}, False)):
                path.write_text(json.dumps({"schema": ur.MANIFEST_SCHEMA, "key": "CIN:5", "resources": resources}))
                if ok:
                    self.assertEqual(len(ur.load_manifests([path], recipes, ["CIN:5"])), 1)
                else:
                    with self.assertRaises(ValueError):
                        ur.load_manifests([path], recipes, ["CIN:5"])
            path.write_text(json.dumps({"schema": ur.MANIFEST_SCHEMA, "key": "CIN:4", "resources": {}}))
            with self.assertRaises(ValueError):
                ur.load_manifests([path], recipes, ["CIN:5"])


RETAIL_PACKS = Path(__import__("os").environ.get("NFL2K5_RETAIL_EXTRACTION",
                                                 "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "vc_53450030"


@unittest.skipUnless((RETAIL_PACKS / "0").is_file(), "the retail extraction is not present")
class RosterPairTests(unittest.TestCase):
    """The 4-byte label edit on the retail main roster: found by asset code, checked, idempotent."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_historic_styles as hs
        with hs.Source(RETAIL_PACKS) as src:
            cls.roster = src.get(identity=ur.ROSTER_ID)

    def test_the_bengals_style_5_pair(self) -> None:
        p = ur.roster_patch(self.roster, "06", 5, (2004, 2), (2026, 1))
        self.assertEqual(struct.unpack_from("<HH", self.roster, p["offset"]), (2004, 2))
        data, receipt = ur.apply_patches(self.roster, [dict(p, resource="ROST", resource_offset=p["offset"])])
        self.assertEqual(sum(a != b for a, b in zip(self.roster, data)), 2)       # 2004 -> 2026 and 2 -> 1, low bytes
        again = ur.roster_patch(data, "06", 5, (2004, 2), (2026, 1))
        self.assertEqual(again["offset"], p["offset"])
        with self.assertRaises(ValueError):
            ur.roster_patch(self.roster, "06", 5, (2004, 1), (2026, 1))          # the wrong retail pair
        with self.assertRaises(ValueError):
            ur.roster_patch(self.roster, "99", 5, (2004, 2), (2026, 1))          # no such franchise


if __name__ == "__main__":
    unittest.main()

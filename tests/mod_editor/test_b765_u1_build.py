import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[2] / "tools/b765/u1_build.py"
SPEC = importlib.util.spec_from_file_location("u1_build_test", PATH)
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)
SCHEMA = "nfl2k5_visual_mod_project/v1"


def project(edits):
    return dict(schema=SCHEMA, edits=edits)


def torso(path="new.png"):
    return dict(kind="torso", asset_code="16", side="H", variant=0, clean_png=path)


class ProjectOverlay(unittest.TestCase):
    def test_giants_mip_overlay_preserves_other_helmets_and_prior_edits(self):
        original = dict(kind="live_helmet", asset_code="18", side="H", variant=0,
                        family="helmet00", png="keep.png")
        changed = dict(original, family="helmet02", png="protected.png")
        base = project([original, torso()])
        out, receipt = build.overlay(base, [project([changed])])
        self.assertEqual(out["edits"], [original, torso(), changed])
        self.assertEqual(receipt["preserved_edit_count"], 2)
        self.assertEqual(build.overlay(out, [project([changed])])[0], out)

    def test_unreviewed_live_helmet_target_refused(self):
        edit = dict(kind="live_helmet", asset_code="18", side="H", variant=0,
                    family="helmet02", png="protected.png")
        for change in ({"asset_code": "16"}, {"side": "X"}, {"variant": 1},
                       {"family": "helmet00"}):
            with self.assertRaisesRegex(ValueError, "unowned live helmet"):
                build.overlay(project([]), [project([dict(edit, **change)])])

    def test_eight_font_corrections_own_jersey_and_arm_targets_only(self):
        codes = {"00", "06", "08", "09", "14", "15", "28", "37"}
        jersey = [dict(kind="live_number_nameplate", asset_code=code, side=side,
                       variant=0, digit=digit, family="jersey_digit", png="new.png")
                  for code in sorted(codes) for side in ("H", "A") for digit in range(10)]
        original = dict(kind="live_number_nameplate", asset_code="15", side="H",
                        variant=0, digit=1, family="helmet_digit", png="unchanged.png")
        out, receipt = build.overlay(project([original]), [project(jersey)])
        self.assertEqual(out["edits"][0], original)
        self.assertEqual(len(receipt["targets"]), 160)
        self.assertEqual(receipt["preserved_edit_count"], 1)
        for code in codes:
            arms, arm_receipt = build.overlay(project([original]), [project([dict(original, asset_code=code, family="arm_digit")])])
            self.assertEqual(arms["edits"][0], original)
            self.assertEqual(len(arm_receipt["targets"]), 1)
            for family in ("helmet_digit", "nameplate"):
                with self.assertRaisesRegex(ValueError, "unowned number"):
                    build.overlay(project([]), [project([dict(original, asset_code=code, family=family)])])

    def test_preserves_unrelated_edits_and_base_metadata(self):
        other = dict(kind="stadium", asset_id="s1", path="keep.bin")
        base = dict(project([other, torso("old.png")]), purpose="pack")
        out, receipt = build.overlay(base, [project([torso()])])
        self.assertEqual(out["edits"], [other, torso()])
        self.assertEqual(out["purpose"], "pack")
        self.assertEqual(receipt["preserved_edit_count"], 1)
        self.assertTrue(receipt["unrelated_edits_identical"])

    def test_overlay_idempotent(self):
        once, _ = build.overlay(project([torso("old.png")]), [project([torso()])])
        twice, _ = build.overlay(once, [project([torso()])])
        self.assertEqual(once, twice)

    def test_duplicate_and_unowned_corrections_refused(self):
        for edits in ([torso(), torso()], [dict(torso(), asset_code="18")],
                      [dict(kind="stadium", asset_id="s1")], [dict(torso(), side="HA")]):
            with self.assertRaises(ValueError):
                build.overlay(project([]), [project(edits)])

    def test_native_merge_refuses_overlap_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.span").write_bytes(b"abcd")
            patch = dict(offset=0, length=4, before_sha256=build.sha(b"old!"),
                         after_sha256=build.sha(b"abcd"), replacement="one.span")
            manifest = dict(schema="b765/u1/texture-repair/v1", resources={"16H0.IFF": [patch, patch]})
            path = root / "input.json"
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                build.merge_native([path], root / "out/native.json")
            self.assertFalse((root / "out").exists())

    def test_native_merge_pins_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.span").write_bytes(b"abcd")
            patch = dict(offset=0, length=4, before_sha256=build.sha(b"old!"),
                         after_sha256=build.sha(b"abcd"), replacement="one.span")
            path = root / "input.json"
            path.write_text(json.dumps(dict(schema="b765/u1/texture-repair/v1", resources={"16H0.IFF": [patch]})))
            doc = build.merge_native([path], root / "out/native.json")
            result = doc["resources"]["16H0.IFF"][0]
            self.assertEqual((root / "out" / result["replacement"]).read_bytes(), b"abcd")

    def test_native_merge_refuses_symlinked_replacement_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.span").write_bytes(b"abcd")
            try:
                (root / "linked").symlink_to(root, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            patch = dict(offset=0, length=4, before_sha256=build.sha(b"old!"),
                         after_sha256=build.sha(b"abcd"), replacement="linked/one.span")
            path = root / "input.json"
            path.write_text(json.dumps(dict(schema="b765/u1/texture-repair/v1", resources={"16H0.IFF": [patch]})))
            with self.assertRaisesRegex(ValueError, "symlink"):
                build.merge_native([path], root / "out/native.json")
            self.assertFalse((root / "out").exists())

    def test_native_merge_preserves_existing_manifest_without_partial_binaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.span").write_bytes(b"abcd")
            patch = dict(offset=0, length=4, before_sha256=build.sha(b"old!"),
                         after_sha256=build.sha(b"abcd"), replacement="one.span")
            path = root / "input.json"
            path.write_text(json.dumps(dict(schema="b765/u1/texture-repair/v1", resources={"16H0.IFF": [patch]})))
            output = root / "out"
            output.mkdir()
            (output / "native.json").write_bytes(b"other job")
            with self.assertRaisesRegex(ValueError, "existing output differs"):
                build.merge_native([path], output / "native.json")
            self.assertEqual([p.name for p in output.iterdir()], ["native.json"])
            self.assertEqual((output / "native.json").read_bytes(), b"other job")

    def test_native_merge_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.span").write_bytes(b"abcd")
            patch = dict(offset=0, length=4, before_sha256=build.sha(b"old!"),
                         after_sha256=build.sha(b"abcd"), replacement="one.span")
            path = root / "input.json"
            path.write_text(json.dumps(dict(schema="b765/u1/texture-repair/v1", resources={"16H0.IFF": [patch]})))
            output = root / "out/native.json"
            first = build.merge_native([path], output)
            second = build.merge_native([path], output)
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

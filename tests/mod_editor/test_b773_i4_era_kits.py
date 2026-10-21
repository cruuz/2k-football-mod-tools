"""b773-i4: the five Anniversary era kits as a Studio stage, and the late uniform pin chain.

The 10/16 Studio build of Noah's disc stopped after 2 h 55 min at the Unc Bowl finish: the Studio never composed the
a5k era kits (only the v0.6 native repair did), so PIT 22A4 was still the retail 1961-62 kit the Unc Bowl pins do
not know. The native tests rebuild the ten kits from retail and v0.6 inputs, check them against the pins and the
v0.6 bytes, and run the Unc Bowl finish on the result; the chain test replays every late step against the build's
verified project manifest (private inputs, skipped when absent).
"""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
from mod_editor.core import nfl2k5_era_kits as era  # noqa: E402
from mod_editor.core import nfl2k5_unc_bowl_uniforms as unc  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
V06 = Path(os.environ.get("B771_V06_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6 (2026-10-09).xiso.iso"))
V061 = Path(os.environ.get("NFL2K5_IC1_BASE",
                           "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6.1 fixes (2026-10-13).xiso.iso"))
MANIFEST = Path(os.environ.get("B773_I4_PROJECT_MANIFEST",
                               "/home/noah/2k-worktrees/.b77-scratch/i4/studio-builds/onuser-verified-project-manifest.json"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Wiring(unittest.TestCase):
    def test_runs_after_labels_spares_and_moments_and_before_the_unc_bowl_finish(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        at = source.index("era_kits.apply_to_image(target")
        self.assertGreater(at, source.index("styles_receipt = styles.apply_to_image(target, retail)"))
        self.assertGreater(at, source.index("espn_receipt = espn.apply_to_image(target, loaded_espn25_plan)"))
        self.assertLess(at, source.index("uniforms_receipt = uniforms.apply_to_image(target)"))

    def test_pins_cover_the_ten_target_slots_and_their_exact_inputs(self):
        document = era.pins()
        expected = {}
        for recipe in era.recipes():
            for side, selector in era.targets(recipe).items():
                donor, parts = era.inputs_of(recipe, side)
                expected[selector] = {donor, *parts.values()}
        self.assertEqual(set(document["kits"]), set(expected))
        for selector, inputs in expected.items():
            self.assertEqual(set(document["kits"][selector]["inputs"]), inputs, selector)
        # The Unc Bowl finish starts from exactly the composed G4 away kit.
        unc_pins = __import__("json").loads(unc.PINS.read_text())["resources"]["22A4.IFF"]
        self.assertEqual(unc_pins["size"], document["kits"]["22A4"]["size"])

    def test_needed_packages_read_retail_only_for_retail_parts(self):
        copy, retail = era.needed_packages()
        self.assertEqual(retail, ["17A1.IFF"])
        self.assertIn("22H0.IFF", copy)
        self.assertIn("16H12.IFF", copy)     # NE's historic spare (retail 2004 look) is the G1 donor
        self.assertEqual(len([n for n in copy if n[:-4] in era.pins()["kits"]]), 10)


class Decisions(unittest.TestCase):
    """plan() decides per slot without compiling anything in these cases."""

    def document(self, **overrides):
        document = era.pins()
        kits = {s: dict(p, **overrides) for s, p in document["kits"].items()}
        return dict(document, kits=kits)

    def kits(self, payload=b"retail kit"):
        copy, _retail = era.needed_packages()
        return {name: payload for name in copy}

    def labels(self):
        return {(r["code"], r["style"]): tuple(r["label"]) for r in era.recipes()}

    def states(self, rows):
        return {selector: row["state"] for selector, _data, row in rows}

    def test_without_the_era_labels_every_slot_keeps_its_retail_kit(self):
        rows = era.plan(self.kits(), {}, document=self.document())
        self.assertEqual(set(self.states(rows).values()), {"retail_label"})
        self.assertTrue(all(data is None for _s, data, _r in rows))

    def test_composed_kits_are_left_alone_and_user_art_in_the_slot_is_kept(self):
        rows = era.plan(self.kits(), self.labels(), document=self.document(after_sha256=sha(b"retail kit")))
        self.assertEqual(set(self.states(rows).values()), {"applied"})
        rows = era.plan(self.kits(b"user kit"), self.labels(), document=self.document())
        self.assertEqual(set(self.states(rows).values()), {"other_uniform"})

    def test_a_missing_target_or_donor_is_reported_not_raised(self):
        kits = self.kits()
        del kits["22A4.IFF"]
        del kits["16H12.IFF"]
        document = self.document()
        for selector in ("16H11", "16A11"):
            document["kits"][selector] = dict(document["kits"][selector], before_sha256=sha(b"retail kit"))
        rows = {s: r for s, _d, r in era.plan(kits, self.labels(), document=document)}
        self.assertEqual(rows["22A4"]["state"], "absent")
        self.assertEqual(rows["16H11"]["state"], "donor_absent")
        self.assertEqual(rows["16H11"]["missing"], ["16H12"])

    def test_an_image_the_studio_cannot_open_is_another_image(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "copy.iso"
            path.write_bytes(b"\0" * 4096)
            self.assertEqual(era.apply_to_image(path, lambda: self.fail("retail read"))["state"], "other_image")


@unittest.skipUnless(RETAIL.is_file() and V06.is_file(), "retail ISO or the v0.6 disc absent")
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_bump_texture_writer as bump

        def read(path, names):
            with bump._Image.open(path, writable=False) as image:
                index = bump._parsed_index(image)
                entries = {bump.logical_name_for(e.name_id): e for e in index.entries}
                return {n: image.read_segments(index.sub_extents(entries[n], 0, entries[n].size))
                        for n in names if n in entries}
        copy, retail_names = era.needed_packages()
        targets = {s + ".IFF" for s in era.pins()["kits"]}
        cls.retail = read(RETAIL, sorted(set(copy) | set(retail_names) |
                                         {"06H5.IFF", "16H0.IFF", "16A0.IFF", "02H0.IFF", "02A0.IFF"}))
        cls.v06 = read(V06, sorted(set(copy) | {"06H5.IFF"}))
        # Studio-stage inputs: era targets are retail (no project edit touches them); the donors equal v0.6 (the
        # project spans of 22H0, 21H0, 17H0, 17A0 and 02H3 are byte-identical to v0.6; the spares are retail copies).
        cls.stage = {n: (cls.retail[n] if n in targets else cls.v06[n]) for n in copy}
        cls.rows = era.plan(cls.stage, {(r["code"], r["style"]): tuple(r["label"]) for r in era.recipes()},
                            {n: cls.retail[n] for n in retail_names})

    def test_historic_spare_donors_are_the_retail_style_zero_kits(self):
        for spare, retail in (("16H12", "16H0"), ("16A12", "16A0"), ("02H4", "02H0"), ("02A4", "02A0")):
            self.assertEqual(self.v06[spare + ".IFF"], self.retail[retail + ".IFF"], spare)

    def test_all_ten_era_kits_compose_to_the_v06_bytes(self):
        for selector, data, row in self.rows:
            self.assertEqual(row["state"], "composed", selector)
            self.assertTrue(row["pinned_inputs"], selector)
            self.assertEqual(data, self.v06[selector + ".IFF"], selector)

    def test_replay_on_the_composed_kits_is_a_no_op(self):
        kits = dict(self.stage, **{s + ".IFF": d for s, d, _r in self.rows})
        labels = {(r["code"], r["style"]): tuple(r["label"]) for r in era.recipes()}
        self.assertEqual({r["state"] for _s, _d, r in era.plan(kits, labels)}, {"applied"})

    def test_the_unc_bowl_finish_accepts_the_composed_away_kit(self):
        composed = {s: d for s, d, _r in self.rows}
        specs = {"06H5.IFF": unc.validate_owned("06H5.IFF", self.v06["06H5.IFF"]),
                 "22A4.IFF": unc.validate_owned("22A4.IFF", composed["22A4"])}
        fixed = {"06H5.IFF": unc.finish_cincinnati(self.v06["06H5.IFF"]),
                 "22A4.IFF": unc.finish_pittsburgh(composed["22A4"], self.stage["22H0.IFF"])}
        for name, data in fixed.items():
            for p in specs[name]["spans"]:
                self.assertEqual(sha(data[p["offset"]:p["offset"] + p["length"]]), p["after_sha256"], p["label"])
        with self.assertRaises(ValueError):
            unc.validate_owned("22A4.IFF", self.retail["22A4.IFF"])     # the 10/16 failure


@unittest.skipUnless(RETAIL.is_file() and V06.is_file() and V061.is_file() and MANIFEST.is_file(),
                     "private build manifest or discs absent")
class ProjectChain(unittest.TestCase):
    def test_unc_bowl_kits_pass_every_late_step_against_the_project_manifest(self):
        import kit_pin_chain_check as check
        out = io.StringIO()
        with redirect_stdout(out):
            status = check.main(["--manifest", str(MANIFEST), "--retail", str(RETAIL), "--reference", str(V06),
                                 "--reference", str(V061), "--only", "06H5", "22A4", "22H4", "22H0"])
        self.assertEqual(status, 0, out.getvalue()[-3000:])


if __name__ == "__main__":
    unittest.main()

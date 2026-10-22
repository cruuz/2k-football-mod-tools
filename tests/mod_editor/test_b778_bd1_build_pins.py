"""b778-bd1: two Studio builds that stopped on a pin after a long run (beta-77.1 reports, 10/21).

1. Modern MetLife on its own (no Modern colour) refused every Giants (s18) bundle: "the refit bundle differs from the
   applied pin". The pins were recorded before the b777 ar1 midfield re-centre was added to the field refit, so the
   compile no longer reproduced them. The pins are re-recorded; the retail-gated test recompiles all eighteen bundles.
2. The Unc Bowl finish refused any build whose 06H5 / 22A4 kit was not the pinned v0.6 span set ("foreign or partially
   repaired Unc Bowl uniform spans") after about three hours. A kit that is still retail, or that something else changed, is
   now left alone and named in the receipt; a source disc that carries a foreign kit is refused before anything is written.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_unc_bowl_uniforms as unc  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
MARKS = Path(os.environ.get("NFL2K5_MARKS_PACK", "/home/noah/.local/share/2k5-mod-studio/official-marks/"
                            "logos-7d37460c5f364263b81642d322f553f1"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(RETAIL.is_file() and MARKS.is_dir(), "needs the retail disc and the official art pack")
class MetLifePinsReproduceTests(unittest.TestCase):
    def test_every_bundle_compiles_to_its_pin(self):
        os.environ["NFL2K5_MARKS_PACK"] = str(MARKS)
        from mod_editor.core import nfl2k5_modern_metlife as ml
        pins = {p["name"]: p for p in ml._pins()["bundles"]}
        with ml._outer_image()(str(RETAIL)) as archive:
            def read(name):
                entry = archive.entries[pins[name]["outer"]]
                return archive.read(entry.virtual_offset, entry.size)
            compiled = ml._compile_all(read, workers=8)
        wrong = [name for name, (data, after, _edits) in compiled.items()
                 if sha(after) != pins[name]["applied_sha256"]
                 or any(sha(after[s["offset"]:s["offset"] + s["size"]]) != s["applied"] for s in pins[name]["sites"])]
        self.assertEqual(wrong, [])


class FakeIndex:
    def __init__(self, names):
        self.entries = [mock.Mock(name_id=0xDEAD0000 + i, size=4) for i in range(22)] + [mock.Mock(name_id=0x3F407CF4, size=4)] + \
            [mock.Mock(name_id=n, size=4) for n in names]

    def sub_extents(self, entry, start, size):
        return (id(entry), size)


class FakeImage:
    def __init__(self, files, situ=b"SITU"):
        self.files, self.situ, self.writes = files, situ, []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read_segments(self, extents):
        key, _size = extents
        return self.situ if key == self.situ_key else self.by_id[key]

    def write_segments(self, extents, data):
        self.writes.append(self.names_by_id[extents[0]])
        self.by_id[extents[0]] = data


def make_pins(raws):
    """A synthetic pin document: two spans per kit, a retail hash, before and after bytes."""
    doc = {"schema": "nfl2k5_unc_bowl_uniforms/v1", "source": "synthetic", "resources": {}}
    for name, raw in raws["before"].items():
        spans = []
        for at in (0, 16):
            spans.append(dict(offset=at, length=16, label="s", before_sha256=sha(raw[at:at + 16]),
                              after_sha256=sha(raws["after"][name][at:at + 16])))
        doc["resources"][name] = dict(size=len(raw), retail_sha256=sha(raws["retail"][name]), spans=spans)
    return doc


def synthetic():
    out = {"retail": {}, "before": {}, "after": {}, "foreign": {}}
    for name, seed in (("06H5.IFF", 1), ("22A4.IFF", 2)):
        for state, offset in (("retail", 0), ("before", 10), ("after", 20), ("foreign", 30)):
            out[state][name] = bytes((seed * 7 + offset + i) & 255 for i in range(48))
    return out


class UncBowlKitStateTests(unittest.TestCase):
    def setUp(self):
        self.raws = synthetic()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        pins = Path(self.tmp.name) / "pins.json"
        pins.write_text(json.dumps(make_pins(self.raws)), encoding="utf-8", newline="\n")
        patcher = mock.patch.object(unc, "PINS", pins)
        patcher.start()
        self.addCleanup(patcher.stop)

    def image_for(self, states, uses_slots=True):
        """Patch the image layer so ``states`` ({file: state}) are what the 'disc' holds."""
        files = {name: self.raws[state][name] for name, state in states.items()}
        files["22H0.IFF"] = b"donor"
        ids = {name: 0x1000 + i for i, name in enumerate(files)}
        index = FakeIndex(ids.values())
        by_entry = {id(e): files[n] for n, e in zip(files, index.entries[23:])}
        image = FakeImage(files)
        image.by_id = by_entry
        image.names_by_id = {id(e): n for n, e in zip(files, index.entries[23:])}
        image.situ_key = id(index.entries[22])
        logical = {v: k for k, v in ids.items()}
        stack = [mock.patch.object(unc.bump._Image, "open", lambda *a, **k: image),
                 mock.patch.object(unc.bump, "_parsed_index", lambda _image: index),
                 mock.patch.object(unc.bump, "logical_name_for", lambda ident: logical.get(ident)),
                 mock.patch.object(unc, "unc_bowl_uses_slots", lambda _situ: uses_slots),
                 mock.patch.object(unc, "finish_cincinnati", lambda raw: self.raws["after"]["06H5.IFF"]),
                 mock.patch.object(unc, "finish_pittsburgh", lambda raw, donor: self.raws["after"]["22A4.IFF"])]
        for patcher in stack:
            patcher.start()
            self.addCleanup(patcher.stop)
        return image

    def test_classify_names_all_four_states(self):
        for state in ("retail", "before", "after", "foreign"):
            self.assertEqual(unc.classify("06H5.IFF", self.raws[state]["06H5.IFF"]), state)
        mixed = bytearray(self.raws["before"]["22A4.IFF"])
        mixed[16:32] = self.raws["after"]["22A4.IFF"][16:32]
        self.assertEqual(unc.classify("22A4.IFF", bytes(mixed)), "foreign")
        self.assertEqual(unc.classify("22A4.IFF", self.raws["retail"]["22A4.IFF"] + b"x"), "foreign")

    def test_a_retail_kit_no_longer_stops_the_build(self):
        image = self.image_for({"06H5.IFF": "retail", "22A4.IFF": "retail"})
        receipt = unc.apply_to_image("disc.iso")
        self.assertEqual(receipt["state"], "kits_not_repaired")
        self.assertEqual(image.writes, [])
        self.assertEqual(len(receipt["user_notes"]), 2)
        self.assertIn("06H5.IFF", receipt["user_notes"][0])

    def test_a_kit_the_user_changed_is_left_alone_and_named(self):
        image = self.image_for({"06H5.IFF": "before", "22A4.IFF": "foreign"})
        receipt = unc.apply_to_image("disc.iso")
        self.assertEqual(receipt["state"], "partly_applied")
        self.assertEqual(image.writes, ["06H5.IFF"])
        self.assertEqual(image.by_id[next(k for k, n in image.names_by_id.items() if n == "22A4.IFF")],
                         self.raws["foreign"]["22A4.IFF"])
        self.assertEqual(len(receipt["user_notes"]), 1)
        self.assertIn("22A4.IFF", receipt["user_notes"][0])

    def test_both_pinned_kits_still_finish(self):
        image = self.image_for({"06H5.IFF": "before", "22A4.IFF": "before"})
        receipt = unc.apply_to_image("disc.iso")
        self.assertEqual(receipt["state"], "applied")
        self.assertEqual(sorted(image.writes), ["06H5.IFF", "22A4.IFF"])
        self.assertNotIn("user_notes", receipt)

    def test_other_moment_slots_are_not_this_modules_business(self):
        image = self.image_for({"06H5.IFF": "foreign", "22A4.IFF": "foreign"}, uses_slots=False)
        self.assertEqual(unc.apply_to_image("disc.iso"), dict(state="other_moment_slots", changed=False))
        self.assertEqual(image.writes, [])

    def test_a_foreign_source_is_refused_up_front_naming_the_file(self):
        self.image_for({"06H5.IFF": "retail", "22A4.IFF": "foreign"})
        with self.assertRaises(ValueError) as caught:
            unc.preflight_source("disc.iso")
        message = str(caught.exception)
        self.assertIn("22A4.IFF", message)
        self.assertNotIn("06H5.IFF", message)
        self.assertIn("retail", message)
        self.assertIn("Nothing was written", message)

    def test_retail_and_softdrink_sources_pass_the_start_check(self):
        for states in ({"06H5.IFF": "retail", "22A4.IFF": "retail"}, {"06H5.IFF": "before", "22A4.IFF": "after"}):
            self.image_for(states)
            self.assertEqual({k: v for k, v in unc.preflight_source("disc.iso").items() if k in unc.OWNED}, states)


class WiringTests(unittest.TestCase):
    def test_the_source_check_runs_before_the_first_copy_and_notes_reach_the_receipt(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        check = text.index("unc.preflight_source(")
        self.assertLess(check, text.index('receipt["steps"].append({"step": "copy"})'))
        self.assertLess(check, text.index("progress(\"Applying ESPN Anniversary edits\", 0, 0)"))
        self.assertIn("uniforms_receipt.get(\"user_notes\"", text)


if __name__ == "__main__":
    unittest.main()

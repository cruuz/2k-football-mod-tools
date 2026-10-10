"""Job u3r (beta 77): striped socks through the fixed equipment writer, the stacking repair and the restack tool.

Model tests use synthetic bytes. The one test that compiles through the real equipment writer needs the retail index
(the same optional input as test_nfl2k5_equipment_banded_roundtrip) and is skipped without it."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools"), str(REPO / "tools/b77"), str(REPO / "tools/b765")]

import u3r_repair as rep  # noqa: E402
import u3r_restack as rs  # noqa: E402
import u3r_socks as socks  # noqa: E402

SPEC = json.loads((REPO / "data/nfl2k5_sock_redo_2026_u3r.json").read_text())
INDEX = Path(os.environ.get("NFL2K5_RETAIL_INDEX",
                            "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class SpecTests(unittest.TestCase):
    def test_every_entry_names_a_kit_and_has_evidence(self) -> None:
        self.assertEqual(SPEC["schema"], socks.SPEC_SCHEMA)
        seen = set()
        for key, entry in SPEC["sets"].items():
            self.assertRegex(entry["selector"], r"^[0-9]{2}[HA][0-9]{1,2}$", key)
            self.assertNotIn(entry["selector"], seen)
            seen.add(entry["selector"])
            self.assertTrue(entry.get("evidence"), key)
            if entry.get("bands") is not None:
                self.assertRegex(entry["base"], r"^#[0-9A-Fa-f]{6}$")
                for band in entry["bands"]:
                    self.assertTrue(0 <= band["y"] and band["y"] + band["height"] <= 64, key)
        # both kits of every redone alternate are listed together
        for team, style in (("CHI", 4), ("CLE", 4), ("SF", 7), ("TEN", 7)):
            self.assertIn(f"{team}:{style}:H", SPEC["sets"])
            self.assertIn(f"{team}:{style}:A", SPEC["sets"])

    def test_the_frozen_project_socks_and_the_photographed_sets_are_present(self) -> None:
        for key in ("CHI:0:H", "CHI:0:A", "CLE:0:H", "CLE:0:A", "WAS:0:A"):
            self.assertIn(key, SPEC["sets"])
        was = SPEC["sets"]["WAS:0:A"]
        self.assertEqual([b["y"] for b in was["bands"]], [33, 37])           # burgundy over gold, u2d's photo fit
        self.assertEqual(was["bands"][0]["colour"].upper(), "#5E1519")
        self.assertEqual(was["bands"][1]["colour"].upper(), "#FFB612")


class PaintTests(unittest.TestCase):
    def test_bands_land_on_their_rows_and_nowhere_else(self) -> None:
        arr = socks.paint_bands("#FFFFFF", [{"y": 33, "height": 4, "colour": "#5E1519"},
                                            {"y": 37, "height": 6, "colour": "#FFB612"}])
        self.assertEqual(arr.shape, (64, 64, 4))
        self.assertEqual(tuple(arr[32, 5, :3]), (255, 255, 255))
        self.assertEqual(tuple(arr[33, 5, :3]), (0x5E, 0x15, 0x19))
        self.assertEqual(tuple(arr[36, 63, :3]), (0x5E, 0x15, 0x19))
        self.assertEqual(tuple(arr[37, 0, :3]), (0xFF, 0xB6, 0x12))
        self.assertEqual(tuple(arr[42, 0, :3]), (0xFF, 0xB6, 0x12))
        self.assertEqual(tuple(arr[43, 0, :3]), (255, 255, 255))
        self.assertTrue((arr[..., 3] == 255).all())
        with self.assertRaises(ValueError):
            socks.paint_bands("#FFFFFF", [{"y": 60, "height": 8, "colour": "#000000"}])

    def test_mud_twin_is_the_retail_darken_60(self) -> None:
        clean = socks.paint_bands("#FFFFFF", [])
        mud = socks.mud_twin(clean)
        self.assertEqual(tuple(mud[0, 0, :3]), (153, 153, 153))
        self.assertTrue((mud[..., 3] == 255).all())

    def test_snap_removes_speckle_and_keeps_structure(self) -> None:
        arr = np.full((64, 64, 4), 255, np.uint8)
        arr[10, :, :3] = (200, 30, 30)                      # a band
        arr[20, 5, :3] = (252, 253, 254)                    # speckle within 4 of the row median
        arr[30, 8:20, :3] = (10, 10, 10)                    # a real notch: kept
        out = socks.snap_rows(arr)
        self.assertEqual(tuple(out[20, 5, :3]), (255, 255, 255))
        self.assertEqual(tuple(out[10, 40, :3]), (200, 30, 30))
        self.assertEqual(tuple(out[30, 10, :3]), (10, 10, 10))
        self.assertTrue(np.array_equal(out[..., 3], arr[..., 3]))


def patch(name: str, offset: int, before: bytes, after: bytes, also=()):
    return {"offset": offset, "length": len(after), "label": "t", "resource": name, "resource_offset": offset,
            "before_sha256": sha(before), "also_before_sha256": [sha(x) for x in also], "after_sha256": sha(after),
            "data": after}


class RepairTests(unittest.TestCase):
    def test_accepts_v05_earlier_job_and_own_output_and_proves_scope(self) -> None:
        pack = bytes(range(256)) * 4
        v05, earlier, new = pack[100:116], b"E" * 16, b"N" * 16
        for state in (v05, earlier, new):
            original = pack[:100] + state + pack[116:]
            data, receipt = rep.apply_patches(original, [patch("05H4.IFF", 100, v05, new, also=[earlier])])
            self.assertEqual(data[100:116], new)
            self.assertEqual(data[:100], pack[:100])
            self.assertEqual(data[116:], pack[116:])
            self.assertTrue(receipt["outside_scope_identical"])
            again, second = rep.apply_patches(data, [patch("05H4.IFF", 100, v05, new, also=[earlier])])
            self.assertEqual(again, data)
            self.assertEqual(second["spans"][0]["input_state"], "already_applied")

    def test_refuses_unexpected_bytes_and_overlaps(self) -> None:
        pack = bytes(range(256)) * 4
        with self.assertRaises(ValueError):
            rep.apply_patches(pack, [patch("x", 100, b"A" * 16, b"N" * 16)])
        v05 = pack[100:116]
        with self.assertRaises(ValueError):
            rep.apply_patches(pack, [patch("x", 100, v05, b"N" * 16), patch("x", 108, pack[108:124], b"M" * 16)])
        bad = patch("x", 100, v05, b"N" * 16)
        bad["data"] = b"Z" * 16
        with self.assertRaises(ValueError):
            rep.apply_patches(pack, [bad])


class RestackTests(unittest.TestCase):
    def manifest(self, folder: Path, spans: dict) -> dict:
        folder.mkdir(parents=True, exist_ok=True)
        resources = {}
        for resource, rows in spans.items():
            for offset, length, before, after in rows:
                name = f"{sha(after)}.span"
                (folder / name).write_bytes(after)
                resources.setdefault(resource, []).append({
                    "offset": offset, "length": length, "label": "t", "before_sha256": sha(before),
                    "after_sha256": sha(after), "replacement": name})
        return {"schema": "b77/u3s/texture-repair/v1", "key": "k", "set": "s", "resources": resources}

    def test_keeps_only_changed_spans_and_records_the_earlier_after(self) -> None:
        v05 = b"v" * 8
        job_a, job_b = b"a" * 8, b"b" * 8
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prior = self.manifest(root / "prior", {"10H5.IFF": [(0, 8, v05, job_a), (16, 8, v05, job_a)]})
            new = self.manifest(root / "new", {"10H5.IFF": [(0, 8, v05, job_a), (16, 8, v05, job_b)]})
            out = rs.restack(new, root / "new", [(prior, root / "prior")], root / "out")
            spans = out["resources"]["10H5.IFF"]
            self.assertEqual([p["offset"] for p in spans], [16])
            self.assertEqual(spans[0]["also_before_sha256"], [sha(job_a)])
            self.assertEqual(out["restack"], {"kept": 1, "dropped_unchanged": 1})
            self.assertTrue((root / "out" / spans[0]["replacement"]).exists())

    def test_partial_overlap_with_an_earlier_span_is_a_conflict(self) -> None:
        v05 = b"v" * 8
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prior = self.manifest(root / "prior", {"10H5.IFF": [(0, 8, v05, b"a" * 8)]})
            new = self.manifest(root / "new", {"10H5.IFF": [(4, 8, v05, b"b" * 8)]})
            with self.assertRaises(ValueError):
                rs.restack(new, root / "new", [(prior, root / "prior")], root / "out")


@unittest.skipUnless(INDEX.is_file(), "retail index not available")
class WriterRoundTripTests(unittest.TestCase):
    def test_a_banded_sock_compiles_at_full_size_and_reads_back_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            clean, mud = socks.author(SPEC["sets"]["WAS:0:A"], {}, "WAS:0:A", root)
            done = socks.compile_pair(INDEX, 4176, clean, mud)
            for asset, t in done["textures"].items():
                self.assertEqual((t["width"], t["height"]), (64, 64), asset)
                self.assertLess(t["mad_vs_input"], 0.5, asset)
                rb = t["readback"]
                self.assertEqual(rb[34, 10, 3], 255)
            clean_rb = done["textures"]["tset:4176:4:0:socks00"]["readback"]
            self.assertGreater(int(clean_rb[34, 10, 0]) - int(clean_rb[34, 10, 2]), 20)       # burgundy band survived (red > blue)
            self.assertGreater(int(clean_rb[40, 10, 0]) - int(clean_rb[40, 10, 2]), 100)      # gold band survived


if __name__ == "__main__":
    unittest.main()

"""Integration: formation/play clone via pack-0 builder on real cache.

Offline (needs private cache at ~/.cache/2k5-mod-studio); proves the
Studio → canonical → backend pack-0 path without needing a full XISO or xemu.
"""
import pathlib
import unittest

from mod_editor.core import nfl2k5_formation_play_writer as w


INDEX = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
INVENTORY = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/indexes/nfl2k5_resource_chunks_v2.json")


def _has_cache() -> bool:
    return INDEX.exists() and INVENTORY.exists()


@unittest.skipUnless(_has_cache(), "private 2K5 cache missing")
class FormationPlayPackIntegrationTests(unittest.TestCase):
    def test_atl_clone_one_formation_one_play(self):
        asset_id = "nfl2k5.resource.o0308.c0000.k504c4159"  # ATL-like 39/254
        repl, _, report, sel, tgt = w.build_unified_formation_play_import(
            INDEX, INVENTORY, asset_id,
            formation_requests=[{"asset_id": asset_id, "donor_formation_index": 0}],
            play_requests=[{"asset_id": asset_id, "donor_play_index": 0}],
        )
        self.assertEqual(report["old_formation_count"], 39)
        self.assertEqual(report["new_formation_count"], 40)
        self.assertEqual(report["old_play_count"], 254)
        self.assertEqual(report["new_play_count"], 255)
        self.assertEqual(len(repl), 0x20 + 0x13390)
        self.assertGreater(len(report["changed_ranges"]), 0)
        self.assertEqual(tgt["pack_offset"], 106803200)

    def test_arz_at_capacity_refused(self):
        asset_id = "nfl2k5.resource.o0307.c0000.k504c4159"  # ARZ 270-cap
        with self.assertRaisesRegex(Exception, "capacity is 270"):
            w.build_unified_formation_play_import(
                INDEX, INVENTORY, asset_id,
                formation_requests=[],
                play_requests=[{"asset_id": asset_id, "donor_play_index": 0}],
            )

    def test_provider_edit_roundtrip(self):
        f = w.FormationCreateRequest(asset_id="nfl2k5.resource.o0308.c0000.k504c4159", donor_formation_index=2)
        p = w.PlayCreateRequest(asset_id="nfl2k5.resource.o0308.c0000.k504c4159", donor_play_index=5)
        self.assertEqual(f.provider_edit()["kind"], "play_formation_create")
        self.assertEqual(p.provider_edit()["kind"], "play_create")
        # from mapping
        f2 = w.formation_request_from_mapping({"asset_id": f.asset_id, "donor_formation_index": 2})
        p2 = w.play_request_from_mapping({"asset_id": p.asset_id, "donor_play_index": 5})
        self.assertEqual(f, f2)
        self.assertEqual(p, p2)

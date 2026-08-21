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
        l = w.FormationLinkRequest(asset_id="nfl2k5.resource.o0308.c0000.k504c4159", formation_index=0, play_index=1)
        self.assertEqual(f.provider_edit()["kind"], "play_formation_create")
        self.assertEqual(p.provider_edit()["kind"], "play_create")
        self.assertEqual(l.provider_edit()["kind"], "play_formation_link")
        # from mapping
        f2 = w.formation_request_from_mapping({"asset_id": f.asset_id, "donor_formation_index": 2})
        p2 = w.play_request_from_mapping({"asset_id": p.asset_id, "donor_play_index": 5})
        l2 = w.link_request_from_mapping(
            {"asset_id": l.asset_id, "formation_index": 0, "play_index": 1}
        )
        self.assertEqual(f, f2)
        self.assertEqual(p, p2)
        self.assertEqual(l, l2)

    def test_custom_name_appends_to_pool_and_updates_count_word(self):
        import struct
        asset_id = "nfl2k5.resource.o0308.c0000.k504c4159"
        repl, _, report, _, _ = w.build_unified_formation_play_import(
            INDEX, INVENTORY, asset_id,
            formation_requests=[
                {"asset_id": asset_id, "donor_formation_index": 0,
                 "custom_name": "ZZ TEST ACE"}
            ],
        )
        self.assertEqual(report["custom_names"], ("ZZ TEST ACE",))
        body = repl[0x20:]
        # pool count word grew by exactly the appended u16 count
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource
        src_span = _read_atl_span()
        old_body = src_span[0x20:]
        old_end = w._pool_end(old_body, 39, 254, len(parse_playbook_resource(src_span, asset_id=asset_id).categories))
        new_end = old_end + (len("ZZ TEST ACE") + 1) * 2
        self.assertEqual(
            struct.unpack_from("<I", body, w.POOL_COUNT_WORD)[0],
            (new_end - w.STRING_BASE) // 2,
        )
        # appended name decodes back through the new formation's name pointer
        parsed = parse_playbook_resource(repl, asset_id=asset_id)
        self.assertEqual(parsed.formations[39].name, "ZZ TEST ACE")
        # tail after the appended string stays zero
        self.assertFalse(any(body[new_end:]))

    def test_overlong_custom_name_refused(self):
        asset_id = "nfl2k5.resource.o0308.c0000.k504c4159"
        with self.assertRaisesRegex(Exception, "1 through 40"):
            w.build_unified_formation_play_import(
                INDEX, INVENTORY, asset_id,
                formation_requests=[
                    {"asset_id": asset_id, "donor_formation_index": 0,
                     "custom_name": "X" * 41}
                ],
            )

    def test_create_play_then_link_it_into_created_formation(self):
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource
        asset_id = "nfl2k5.resource.o0308.c0000.k504c4159"
        source = parse_playbook_resource(_read_atl_span(), asset_id=asset_id)
        donor = next(
            f.index for f in source.formations if len(f.play_links) < 36
        )
        repl, _, report, _, _ = w.build_unified_formation_play_import(
            INDEX, INVENTORY, asset_id,
            formation_requests=[{"asset_id": asset_id, "donor_formation_index": donor}],
            play_requests=[{"asset_id": asset_id, "donor_play_index": 0}],
            link_requests=[{"asset_id": asset_id, "formation_index": 39, "play_index": 254}],
        )
        self.assertEqual(report["links"], ((39, 254, report["links"][0][2], report["links"][0][3]),))
        from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource
        parsed = parse_playbook_resource(repl, asset_id=asset_id)
        linked = parsed.formations[39].play_links
        self.assertTrue(
            any(lk.play_index == 254 for lk in linked),
            "created play not listed in created formation",
        )

    def test_link_group_bounds_enforced(self):
        asset_id = "nfl2k5.resource.o0308.c0000.k504c4159"
        with self.assertRaisesRegex(Exception, "0 through 3"):
            w.build_unified_formation_play_import(
                INDEX, INVENTORY, asset_id,
                link_requests=[
                    {"asset_id": asset_id, "formation_index": 0, "play_index": 0, "group": 4}
                ],
            )

    def test_link_out_of_range_play_refused(self):
        asset_id = "nfl2k5.resource.o0308.c0000.k504c4159"
        with self.assertRaisesRegex(Exception, "outside this PLAY book"):
            w.build_unified_formation_play_import(
                INDEX, INVENTORY, asset_id,
                link_requests=[
                    {"asset_id": asset_id, "formation_index": 0, "play_index": 9000}
                ],
            )


def _read_atl_span() -> bytes:
    from mod_editor.core.nfl2k5_universal_asset_index import Nfl2k5UniversalAssetIndex
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "tools"))
    from nfl_outer import read_entry_range
    sidecar = INVENTORY.parent.parent / "universal-assets-v1.sqlite3"
    index = Nfl2k5UniversalAssetIndex(INVENTORY, INDEX, sidecar)
    record = index.get("nfl2k5.resource.o0308.c0000.k504c4159")
    entry = index.archive.entries[record.outer_index]
    return read_entry_range(index.archive, entry, record.chunk_offset, record.raw_size)

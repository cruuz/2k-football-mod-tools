"""Authoring: formation geometry + node-chain plays through the pack-0 writer.

Offline (needs the private cache at ~/.cache/2k5-mod-studio).  Proves that an
authored formation (Pistol from Ace) and an authored play (rewritten receiver
routes and a shotgun QB chain) compile, reparse, keep byte ownership, and pass
the ported retail play validator.
"""
import pathlib
import struct
import unittest

from mod_editor.core import nfl2k5_formation_play_writer as w
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as insp

INDEX = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
INVENTORY = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/indexes/nfl2k5_resource_chunks_v2.json")
ATL = "nfl2k5.resource.o0308.c0000.k504c4159"
ACE = 10
TE_Y_OUTS = 141
YD = codec.YD_CM


def _has_cache() -> bool:
    return INDEX.exists() and INVENTORY.exists()


def pistol_positions():
    return [
        (0, int(-4 * YD)),            # QB 4 yards deep
        (304, 0), (-304, 0), (0, 0), (152, 0), (-152, 0),
        (-457, 0), (-1371, -219), (1371, -219), (457, 0),
        (0, int(-7 * YD)),            # HB directly behind the QB
    ]


def slant_route(depth_yd: float):
    return (
        (0x01, (1, 3, 0, 0.0, 0.0, 0.0)),
        (0x12, (0, 0, 3 * YD, 15)),
        (0x12, (2, 0, depth_yd * YD, 15)),
    )


def shotgun_qb():
    return (
        (0x01, (1, 4, 0, 0.0, 0.0, 0.0)),
        (0x03, (0,)),
        (0x04, (0, 0.0, -1 * YD, 0)),
        (0x06, (0, 1, 4, 2, 3, 0.0)),
    )


class CodecUnitTests(unittest.TestCase):
    def test_route_segment_round_trip(self):
        node = codec.Node(0x12, 0, [2, 0, 10 * YD, 15])
        raw = node.to_bytes()
        again = codec.Node.from_bytes(raw)
        self.assertEqual(again.op, 0x12)
        self.assertEqual(again.operands[0], 2)
        self.assertAlmostEqual(again.operands[2], 10 * YD, places=1)

    def test_flags_follow_retail_convention(self):
        nodes = [codec.Node(op, 0, list(vals)) for op, vals in slant_route(10)]
        codec.assign_node_flags(nodes)
        self.assertEqual([n.flags for n in nodes], [0x00, 0x04, 0x02])
        qb = [codec.Node(0x01, 0, [1, 4, 0, 0, 0, 0]), codec.Node(0x03, 0, [0]), codec.Node(0x13, 0, [10, 0])]
        codec.assign_node_flags(qb)
        self.assertEqual([n.flags for n in qb], [0x10, 0x10, 0x16])

    def test_formation_record_round_trip(self):
        raw = bytes(range(0xB4))
        rec = codec.FormationRecord.from_bytes(raw)
        self.assertEqual(rec.to_bytes(), raw)


class LibraryUnitTests(unittest.TestCase):
    def test_position_kinds_match_stock_groups(self):
        # "Ace" fields two tight ends on the line (kind 8) and "5 Wide" five wideouts (kind 9).
        self.assertEqual(codec.POSITION_KINDS[8], "TE")
        self.assertEqual(codec.POSITION_KINDS[9], "WR")
        self.assertEqual((lib.TE, lib.WR), (8, 9))

    def test_ranked_codes_assign_depth_chart_ranks_left_to_right(self):
        kinds = [lib.QB, lib.T, lib.T, lib.C, lib.G, lib.G, lib.WR, lib.WR, lib.TE, lib.HB, lib.HB]
        xs = [0, 3, -3, 0, 1.7, -1.7, -15, 15, 5, -2, 2]
        codes = lib.ranked_codes(kinds, xs)
        self.assertEqual([codec.position_label(c) for c in codes],
                         ["QB", "T", "T2", "C", "G", "G2", "WR", "WR2", "TE", "HB", "HB2"])
        self.assertTrue(lib.is_offense_category(codes))
        self.assertEqual(lib.back_count(codes), 2)

    def test_drawn_route_quantizes_to_game_segments(self):
        def line(*pts):
            return [(x * YD, z * YD) for x, z in pts]
        chain, words = lib.quantize_drawn_route(line((12, 0), (12, 10), (6, 16)), 1)
        self.assertEqual([op for op, _ in chain], [0x01, 0x12])
        self.assertEqual(chain[1][1][0], 2, "10 up then 45° inside is a post")
        self.assertIn("post", words)
        chain, _ = lib.quantize_drawn_route(line((12, 0), (12, 8), (20, 8)), 1)
        self.assertEqual([(op, vals[0]) for op, vals in chain[1:]], [(0x12, 0), (0x12, 5)], "stem then out")
        chain, _ = lib.quantize_drawn_route(line((-12, 0), (-12, 2), (6, 3)), -1)
        self.assertEqual([(op, vals[0]) for op, vals in chain[1:]], [(0x12, 0), (0x12, 4)], "drag from the left goes in")
        chain, words = lib.quantize_drawn_route(line((12, 0), (12, 3), (12, 8), (13, 12), (11, 16), (12, 20), (18, 22), (12, 24)), 1)
        self.assertLessEqual(len(chain) - 1, lib.ROUTE_MAX_NODES)
        with self.assertRaises(ValueError):
            lib.quantize_drawn_route([(0, 0)], 1)

    def test_drawn_run_path(self):
        lane, path, words = lib.drawn_run_path([(0, -7 * YD), (0, -2 * YD), (0, 4 * YD)], 1)
        self.assertEqual(path[0], 0)
        self.assertAlmostEqual(path[2], 11.0)
        self.assertIn("straight ahead", words)


@unittest.skipUnless(_has_cache(), "private 2K5 cache missing")
class PlayAuthorIntegrationTests(unittest.TestCase):
    def test_personnel_group_written_for_a_two_back_gun_set(self):
        # HB + HB2 (RB2 instead of the FB): no stock group fields it, so the mix is written
        # into the unused "Jacks" group and the formation points at that group.
        kinds = [lib.QB, lib.T, lib.T, lib.C, lib.G, lib.G, lib.TE, lib.WR, lib.WR, lib.HB, lib.HB]
        positions = [(0, int(-5 * YD)), (304, 0), (-304, 0), (0, 0), (152, 0), (-152, 0),
                     (457, 0), (-1371, -100), (1371, -100), (-320, int(-5 * YD)), (320, int(-5 * YD))]
        codes = lib.ranked_codes(kinds, [x for x, _ in positions])
        repl, _, report, _sel, _tgt = w.build_unified_formation_play_import(
            INDEX, INVENTORY, ATL,
            formation_requests=[{"asset_id": ATL, "donor_formation_index": 0, "custom_name": "Gun Two Back",
                                 "slot_positions": positions, "category_index": 0, "category_positions": codes}],
            play_requests=[], link_requests=[],
        )
        body = repl[0x20:]
        cat = body[insp.CATEGORY_BASE + 5: insp.CATEGORY_BASE + 16]
        self.assertEqual(list(cat), codes)
        self.assertEqual(report["authored_formations"][0]["position_codes"], codes)
        self.assertEqual(report["authored_formations"][0]["category_index"], 0)
        book = insp.parse_playbook_resource(repl, asset_id=ATL)
        self.assertEqual(book.formations[39].name, "Gun Two Back")
        self.assertEqual([codec.position_label(c) for c in lib.category_positions(body, 0)][6:],
                         ["TE", "WR", "WR2", "HB", "HB2"])
        with self.assertRaises(Exception):
            w.formation_request_from_mapping({"asset_id": ATL, "donor_formation_index": 0, "category_positions": codes})

    def test_pistol_formation_and_slant_play(self):
        assignments = [None] * 11
        assignments[0] = shotgun_qb()
        assignments[6] = slant_route(8)
        assignments[9] = slant_route(12)
        repl, _, report, _sel, tgt = w.build_unified_formation_play_import(
            INDEX, INVENTORY, ATL,
            formation_requests=[{"asset_id": ATL, "donor_formation_index": ACE,
                                 "custom_name": "Pistol Ace", "slot_positions": pistol_positions()}],
            play_requests=[{"asset_id": ATL, "donor_play_index": TE_Y_OUTS,
                            "custom_name": "Pistol Slants", "assignments": assignments}],
            link_requests=[{"asset_id": ATL, "formation_index": 39, "play_index": 254}],
        )
        self.assertEqual(report["new_formation_count"], 40)
        self.assertEqual(report["new_play_count"], 255)
        self.assertEqual(report["new_node_count"], report["old_node_count"] + 4 + 3 + 3)
        self.assertTrue(report["claims"]["authored_plays_pass_ported_game_validator"])
        book = insp.parse_playbook_resource(repl, asset_id=ATL)
        formation = book.formations[39]
        self.assertEqual(formation.name, "Pistol Ace")
        body = repl[0x20:]
        rec = codec.FormationRecord.from_bytes(
            body[insp.FORMATION_BASE + 39 * insp.FORMATION_SIZE: insp.FORMATION_BASE + 40 * insp.FORMATION_SIZE])
        self.assertEqual((rec.slots[0].x[0], rec.slots[0].z[0]), (0, -365))
        self.assertEqual((rec.slots[10].x[0], rec.slots[10].z[0]), (0, -640))
        self.assertEqual(rec.slots[1].mirror_partner, 2)
        self.assertEqual(rec.slots[0].mirror_partner, 0)
        self.assertEqual(rec.qb_alignment, 2, "a 4-yard QB must be flagged shotgun (bit 19)")
        donor = codec.FormationRecord.from_bytes(
            body[insp.FORMATION_BASE + ACE * insp.FORMATION_SIZE: insp.FORMATION_BASE + (ACE + 1) * insp.FORMATION_SIZE])
        self.assertEqual(donor.qb_alignment, 1)
        play = book.plays[254]
        self.assertEqual(play.name, "Pistol Slants")
        chain = book.chain(play.assignments[6].chain_start_index)
        self.assertEqual([n.opcode for n in chain.nodes], [0x01, 0x12, 0x12])
        self.assertTrue(any(l.play_index == 254 for l in formation.play_links))
        # descriptor for the authored WR slot matches what the game computes for a 3-node route chain
        self.assertEqual(play.assignments[6].descriptor_word & 0x00FFFFFF, 0xB11013)

    def test_reference_play_carries_the_class_the_game_plays(self):
        """A pass staged under a run-class header (bits 12-15 = 0x8000) is played as a run:
        icons vanish at the snap and the QB cannot throw.  The wizard must take its donor and
        header flags from a stock play of the same shape."""
        raw = pathlib.Path(INDEX).open("rb")
        raw.seek(106803200)
        book = insp.parse_playbook_resource(raw.read(0x20 + insp.BODY_SIZE), asset_id=ATL)
        body = w_body = None
        raw.seek(106803200 + 0x20)
        body = raw.read(insp.BODY_SIZE)
        first_offense = next(p.index for p in book.plays if p.family_id == 0)
        self.assertEqual(lib.play_class_label(lib.play_chains(body, first_offense)[0]), "run",
                         "ATL's first offensive play is a run — that is the old donor bug")
        donor, flags = lib.reference_play_for(book, body, "pass")
        self.assertEqual(lib.play_class_label(flags), "pass")
        self.assertEqual(flags & lib.PLAY_CLASS_MASK, lib.PLAY_CLASS_PASS)
        self.assertFalse(flags & (lib.PLAY_FLAG_PLAY_ACTION | lib.PLAY_FLAG_QUICK | lib.PLAY_FLAG_SPECIAL))
        self.assertEqual(lib.qb_signature(lib.play_chains(body, donor)[1][0][1]), "pass")
        donor, flags = lib.reference_play_for(book, body, "pa_pass")
        self.assertTrue(flags & lib.PLAY_FLAG_PLAY_ACTION)
        self.assertEqual(lib.play_class_label(flags), "pass")
        self.assertEqual(lib.qb_signature(lib.play_chains(body, donor)[1][0][1]), "pa_pass")
        donor, flags = lib.reference_play_for(book, body, "run")
        self.assertEqual(lib.play_class_label(flags), "run")
        self.assertEqual(lib.qb_signature(lib.play_chains(body, donor)[1][0][1]), "run")
        donor, flags = lib.reference_play_for(book, body, "run", "Draw")
        self.assertEqual(lib.qb_signature(lib.play_chains(body, donor)[1][0][1]), "draw")
        for kind in ("sneak", "keeper"):
            donor, flags = lib.reference_play_for(book, body, kind)
            self.assertEqual(lib.play_class_label(flags), "run")
            self.assertEqual(lib.qb_signature(lib.play_chains(body, donor)[1][0][1]), "qb_run")
        # the generated wizard chains classify the way the stock corpus does
        self.assertEqual(lib.qb_signature(lib.qb_pass_chain(True)), "pass")
        self.assertEqual(lib.qb_signature(lib.qb_fake_then_pass(10, False)), "pa_pass")
        self.assertEqual(lib.qb_signature(lib.qb_handoff_chain(10, 0)), "run")
        self.assertEqual(lib.qb_signature(lib.qb_handoff_chain(10, 4, draw=True)), "draw")
        self.assertEqual(lib.qb_signature(lib.qb_sneak_chain()), "qb_run")
        # forcing: a run header asked to carry a pass gets the pass class and nothing else changes below bit 9
        forced = lib.class_flags_for("pass", 0x800e)
        self.assertEqual(forced & lib.PLAY_CLASS_MASK, lib.PLAY_CLASS_PASS)
        self.assertEqual(forced & 0x1FF, 0x800e & 0x1FF)

    def test_play_flags_are_written_and_verified(self):
        assignments = [None] * 11
        assignments[0] = shotgun_qb()
        donor_flags = lib.play_chains(pathlib.Path(INDEX).read_bytes()[106803200 + 0x20:106803200 + 0x20 + insp.BODY_SIZE], TE_Y_OUTS)[0]
        self.assertEqual(donor_flags, 0x640e)
        repl, _, _report, _sel, _tgt = w.build_unified_formation_play_import(
            INDEX, INVENTORY, ATL,
            play_requests=[{"asset_id": ATL, "donor_play_index": TE_Y_OUTS, "custom_name": "Gun Pass",
                            "assignments": assignments, "play_flags": 0x620e}],
        )
        book = insp.parse_playbook_resource(repl, asset_id=ATL)
        self.assertEqual(book.plays[254].flags_or_id, 0x620e)
        self.assertEqual(lib.play_class_label(book.plays[254].flags_or_id), "pass")
        with self.assertRaisesRegex(Exception, "family and type code"):
            w.build_unified_formation_play_import(
                INDEX, INVENTORY, ATL,
                play_requests=[{"asset_id": ATL, "donor_play_index": TE_Y_OUTS, "assignments": assignments,
                                "play_flags": 0x6201}],
            )
        req = w.play_request_from_mapping({"asset_id": ATL, "donor_play_index": TE_Y_OUTS, "play_flags": 0x620e})
        self.assertEqual(req.provider_edit()["play_flags"], 0x620e)
        self.assertNotEqual(req.selector, w.play_request_from_mapping({"asset_id": ATL, "donor_play_index": TE_Y_OUTS}).selector)

    def test_invalid_play_is_refused_with_game_reason(self):
        assignments = [None] * 11
        assignments[0] = ((0x01, (1, 4, 0, 0, 0, 0)), (0x03, (0,)), (0x13, (10, 0)))  # handoff without taker
        with self.assertRaisesRegex(Exception, "Handoff To must be matched"):
            w.build_unified_formation_play_import(
                INDEX, INVENTORY, ATL,
                play_requests=[{"asset_id": ATL, "donor_play_index": TE_Y_OUTS, "assignments": assignments}],
            )

    def test_bad_slot_position_count_refused(self):
        with self.assertRaisesRegex(Exception, "eleven"):
            w.formation_request_from_mapping({"asset_id": ATL, "donor_formation_index": ACE, "slot_positions": [[0, 0]]})


if __name__ == "__main__":
    unittest.main()

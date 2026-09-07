"""Standalone draft reservation, copy-injection and native-route proofs."""
from dataclasses import replace
from pathlib import Path
import json
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_draft_start as draft
from mod_editor.core import nfl2k5_senior_bowl as bowl
from mod_editor.core import nfl2k5_roster_records as rr
from tests.nfl2k5_senior_bowl_fixture import prospects
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes, signed_save
from tools import nfl2k5_supersim_draft_probe as probe

IDENTITY = b"draft-start-test"
RECEIPT = Path(__file__).resolve().parents[2] / "docs/nfl2k5_supersim_draft_receipts.json"
PRIOR_YEAR = RECEIPT.with_name("nfl2k5_draft_start_prior_year.json")


class ReservationTests(unittest.TestCase):
    def test_all_positions_both_sides_and_supported_schemes(self):
        for scheme in bowl.SCHEMES:
            rows = prospects(scheme)
            for position, quota in enumerate(bowl.quotas(scheme)):
                if not quota:
                    continue
                for side in (0, 1):
                    reservation = draft.reserve(rows, year=1, franchise_id=IDENTITY,
                                                position=position, side=side, scheme=scheme)
                    squads = draft.squads_for(rows, reservation)
                    self.assertEqual(tuple(map(len, squads)), (53, 53))
                    self.assertIn(reservation.index, squads[side])
                    # The existing event validator accepts precisely this
                    # selection. Its legacy kit fields are not used to launch.
                    event = bowl.prepare_event(rows, year=1, franchise_id=IDENTITY,
                                                settings=bowl.Settings(scheme=scheme))
                    self.assertEqual(tuple(r.index for r in event.lines if r.side == side), squads[side])

    def test_stale_class_owned_short_and_late_entries_refuse(self):
        rows = prospects()
        reservation = draft.reserve(rows, year=1, franchise_id=IDENTITY, position=0)
        for changed in (rows[:-1], tuple(replace(p, owned=True) if p.index == reservation.index else p for p in rows),
                        tuple(replace(p, identity=b"new class") for p in rows)):
            with self.assertRaises(draft.DraftStartError):
                draft.squads_for(changed, reservation)
        for kwargs in ({"stage": 5}, {"days": 3}, {"untouched_hours": False}):
            with self.assertRaises(draft.DraftStartError):
                draft.reserve(rows, year=1, franchise_id=IDENTITY, position=0, **kwargs)
        with self.assertRaises(bowl.SeniorBowlError):
            draft.reserve(rows[:3], year=1, franchise_id=IDENTITY, position=0)

    def test_v1_uses_generic_nfl_and_no_stock_or_runtime_claim(self):
        self.assertEqual(draft.GENERIC_NFL_KITS, ("31A0.IFF", "31H0.IFF"))
        self.assertEqual(draft.NATIVE_TO_EVENT_SIDES, (1, 0))
        self.assertEqual(draft.SCOUTING_STOCK_DELTA, 0)
        self.assertEqual(draft.REQUESTS, ())
        self.assertFalse(draft.RUNTIME_READY)
        self.assertFalse(hasattr(draft, "apply"))
        self.assertIn("simulate_year_0", draft.route(draft.START_CHOICES[0]))
        self.assertEqual(draft.route(draft.START_CHOICES[1])[-1], "rookie_year_0")
        with self.assertRaises(draft.DraftStartError):
            draft.route("force a random team")
        # Existing Senior Bowl v1 intentionally refuses generic bank 31. The
        # integration must change that owner/codec before making a launch offer.
        with self.assertRaises(bowl.SeniorBowlError):
            bowl.Kit(31, "H").validate()

    def test_bounded_native_team_projection_preserves_generic_template(self):
        template = bytearray(500)
        struct.pack_into("<H", template, 0x118, 31)
        template[0x104:0x108] = b"NAME"
        before = bytes(template)
        result = draft.project_native_team(before, tuple(range(53)), primary_base=0x2000000, primary_count=106)
        self.assertEqual(before, bytes(template))
        self.assertEqual(result[0x11C], 53)
        self.assertEqual(result[0x104:0x108], b"NAME")
        self.assertEqual(struct.unpack_from("<I", result, 52*4)[0], 0x2000000+52*84)
        self.assertEqual(result[53*4:65*4], bytes(48))
        for indices in (tuple(range(52)), (0,)*53, tuple(range(54, 107))):
            with self.assertRaises(draft.DraftStartError):
                draft.project_native_team(before, indices, primary_base=0x2000000, primary_count=106)
        template[0x118] = 50
        with self.assertRaises(draft.DraftStartError):
            draft.project_native_team(bytes(template), tuple(range(53)), primary_base=0x2000000, primary_count=106)


class PrivateInjectionTests(unittest.TestCase):
    def setUp(self):
        self.payload = signed_save()
        self.document = rr.RosterDocument(self.payload, base=rr.SAVE_BLOCK_OFFSET)
        self.players = bowl.prospects_from_document(self.document)
        self.reservation = draft.reserve(self.players, year=0, franchise_id=IDENTITY, position=0)
        self.creation = draft.Creation("Noah", "Rookie", 0, 1, (("pass_accuracy", 79),))

    def test_copy_injection_preserves_all_other_players_and_membership(self):
        candidate, updated, receipt = draft.inject(self.document, self.reservation, self.creation,
                                                    year=0, franchise_id=IDENTITY)
        self.assertEqual(self.document.to_body(), self.payload)
        self.assertTrue(receipt["changed"])
        for old, new in zip(self.document.players, candidate.players):
            if old.pool == "primary" and old.index == updated.index:
                self.assertEqual((new.first, new.last, new.college_index), ("Noah", "Rookie", 1))
                self.assertEqual(new.record.get("pass_accuracy"), 79)
                self.assertTrue(bowl.prospects_from_document(candidate)[new.index].eligible)
            else:
                self.assertEqual(old.record.encode(), new.record.encode())
        for old, new in zip(self.document.teams, candidate.teams):
            self.assertEqual(self.payload[old.offset:old.offset+500], candidate.to_body()[new.offset:new.offset+500])
        original_squads = draft.squads_for(self.players, self.reservation)
        self.assertEqual(original_squads, draft.squads_for(bowl.prospects_from_document(candidate), updated))
        repeated, same, second = draft.inject(candidate, updated, self.creation, year=0, franchise_id=IDENTITY)
        self.assertEqual(repeated.to_body(), candidate.to_body())
        self.assertEqual(same, updated)
        self.assertFalse(second["changed"])

    def test_foreign_recipe_year_identity_and_source_refuse_without_mutation(self):
        candidate, updated, _ = draft.inject(self.document, self.reservation, self.creation,
                                              year=0, franchise_id=IDENTITY)
        for creation, options in ((replace(self.creation, position=1), {}),
                                   (replace(self.creation, college=999), {}),
                                   (self.creation, {"year": 1}),
                                   (self.creation, {"franchise_id": b"wrong-save-id---"})):
            with self.assertRaises(draft.DraftStartError):
                draft.inject(self.document, self.reservation, creation,
                             **({"year": 0, "franchise_id": IDENTITY} | options))
            self.assertEqual(self.document.to_body(), self.payload)
        with self.assertRaises(draft.DraftStartError):
            draft.inject(candidate, self.reservation, self.creation, year=0, franchise_id=IDENTITY)
        with self.assertRaises(draft.DraftStartError):
            draft.inject(candidate, updated, replace(self.creation, first="Alex"), year=0, franchise_id=IDENTITY)


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; native x86 probes require it")
class NativeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = retail_bytes()

    def test_pinned_pause_row_and_all_research_spans(self):
        audit = probe.audit(self.payload)
        self.assertEqual(audit["pause_row"], {"kind": 9, "text": "0xe626c4", "action": "0x6efe0"})
        self.assertEqual(audit["pause_text"], "Simulate To End")
        self.assertEqual(len(audit["callback_table"]), 19)
        if not RECEIPT.is_file():
            self.fail("committed derived research receipt is missing")
        self.assertEqual(audit, json.loads(RECEIPT.read_text())["audit"])
        long_record = json.loads(PRIOR_YEAR.read_text())
        self.assertEqual(audit, long_record["audit"])
        prior = long_record["prior_year"]
        self.assertEqual(prior["native_calls"], {"0xc7a20": 268, "0x1356d0": 268, "0x247b40": 1})
        self.assertEqual((prior["transitions"][-1]["year"], prior["transitions"][-1]["stage"]), (1, 5))
        self.assertEqual(prior["class_count"], 380)
        self.assertTrue(prior["class_stable_at_draft_entry"])
        self.assertEqual(prior["squad_sizes"], [53, 53])
        with self.assertRaises(ValueError):
            probe.audit(self.payload[:-1]+b"X")

    def test_native_prospect_clone_personnel_kits_and_stat_isolation(self):
        result = probe.projection_proof(self.payload)
        self.assertEqual(result["cloned_records"], 106)
        self.assertEqual(result["initial_history_aliases"], 106)
        self.assertEqual(result["stat_pointer_rebindings"], 106)
        self.assertEqual(result["all_33_personnel_from_each_squad"], [True, True])
        self.assertEqual(result["kits"], ["31h0.iff", "31a0.iff"])
        self.assertEqual(result["source_arena_sha256_before"], result["source_arena_sha256_after"])
        self.assertTrue(result["source_arena_read_only"])
        self.assertEqual(result["stop"]["reason"], "target")
        self.assertEqual(result["stop"]["final"]["quarter"], 2)
        self.assertEqual(result["finish"]["reason"], "game_end")
        self.assertEqual(result["leaves"], [])

    def test_real_draft_ai_rng_and_native_signing(self):
        result = probe.draft_proof(self.payload)
        self.assertGreater(result["distinct_candidates"], 1)
        sign = result["native_sign"]
        self.assertEqual(sign["count_after"], sign["count_before"]+1)
        self.assertFalse(sign["flags"] & 0x10)
        self.assertNotEqual(sign["contract_word"], "0x0")

    def test_fresh_start_and_whole_fixture_commit(self):
        result = probe.fresh_start_proof(self.payload)
        self.assertEqual(tuple(result[k] for k in ("stage", "stage_weeks", "week", "year", "class_count")),
                         (8, 17, 0, 0, 380))
        self.assertEqual(result["leaves"], [])
        fixture = result["first_fixture"]
        self.assertEqual((fixture["return"], fixture["native_commits"]), (1, 1))
        self.assertGreater(fixture["native_ticks"], 100)
        self.assertEqual(bytes.fromhex(fixture["fixture_hex"])[0] & 7, 3)

    def test_full_native_draft_and_undrafted_cleanup_replay(self):
        recorded = json.loads(RECEIPT.read_text())["full_drafts"]
        # Replay a drafted and an undrafted seed through all 224 picks and
        # native FA cleanup. The full eight-seed command records the other six.
        actual = probe.full_draft_proof(self.payload, seeds=(1, 2))
        self.assertEqual(json.loads(json.dumps(actual)), recorded[:2])
        self.assertEqual(actual[0]["free_agent_occurrences"], 1)
        self.assertIsNotNone(actual[1]["landing"])


if __name__ == "__main__":
    unittest.main()

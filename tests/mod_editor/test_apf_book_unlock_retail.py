"""Optional fast, read-only retail proof; no retail fixture is distributed."""
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core import apf2k8_scheme_presets as presets
from tools import apf_book_resolution_probe as probe


def local_input(variable):
    value = os.environ.get(variable)
    if not value or not Path(value).is_file():
        raise unittest.SkipTest(f"Set {variable} to an existing user-owned input; no retail bytes are bundled")
    return Path(value)


class RetailProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = local_input("APF_BOOK_RETAIL_INDEX")

    def test_five_clones_make_twelve_cpu_offensive_resources(self):
        requests = clone.requests_from_json((Path(__file__).resolve().parents[2] /
                                            "data/apf2k8/book_clone_example.json").read_bytes())
        plan = clone.compile_unlock(self.index, requests)
        self.assertEqual(len(plan.clones), 5)
        self.assertEqual(plan.report["directory"]["append_bytes"], 10240)
        rows = plan.report["book_identity"]["assignments"]
        real_cpu = {x["resolved_book"] for x in rows if x["side"] == "offense" and
                    x["resolved_book"] not in (None, "USER-o", "global-o")}
        self.assertEqual(len(real_cpu), 12)
        selected = {x.team_index for x in requests}
        self.assertTrue(all(not x["shared"] for x in rows if x["side"] == "offense" and
                            x["team_index"] in selected))
        for item in plan.clones:
            donor = identity.read_resource(self.index, identity.filename_id(item.donor_type), "spb", "SPLB")[3]
            self.assertTrue(clone.verify_clone_body(donor, item.body, item.name)["identical_except_name"])

    def test_preset_is_starting_content_on_an_independent_copy(self):
        request = clone.CloneRequest(5, 5, "O-ZoneBlock")
        plan = clone.compile_unlock(self.index, [request], preset_ids=("wide-zone",))
        prepared = presets.compile_preset(self.index, presets.load_preset("wide-zone"))
        self.assertEqual(len(plan.clones), 1)
        item = plan.clones[0]
        self.assertTrue(clone.verify_clone_body(prepared.replacement, item.body, item.name)["identical_except_name"])
        self.assertEqual(plan.report["preset_ids"], ["wide-zone"])
        self.assertEqual(plan.report["clones"][0]["transport"]["h7a_overlapping_matches"], 0)

    def test_three_authored_presets_fit_and_repeat(self):
        counts = {"wide-zone": 13, "spread-to-run": 21, "pro-power": 20}
        for slug, count in counts.items():
            with self.subTest(slug=slug):
                result = presets.compile_preset(self.index, presets.load_preset(slug))
                self.assertEqual(len(result.report["verification"]["changed_records"]), count)
                self.assertEqual(result.report["transport"]["h7a_overlapping_matches"], 0)
                self.assertGreater(result.report["transport"]["remaining_bytes"], 0)
                self.assertTrue(result.report["idempotent_reapply"])

    def test_all_fifteen_resource_names_match_filename_hashes(self):
        report, _bodies = probe.archive_evidence(self.index)
        self.assertEqual(len(report["books"]), 15)
        self.assertEqual(sum(x["populated_records"] for x in report["books"]), 209)
        self.assertEqual(sum(x["h7a_overlaps"] for x in report["books"]), 0)
        self.assertEqual(report["unaccounted_payload_boundaries"], [])
        self.assertTrue(report["sorted_unique_ids"])
        self.assertTrue(report["tail_covered"])

    def test_base_executable_and_crc_table_are_pinned(self):
        report = probe.executable_evidence(local_input("APF_BOOK_FLAT_PE"))
        self.assertEqual(report["sha256"], probe.PE_SHA256)
        self.assertEqual(report["crc_table"]["entries"], 256)

    def test_raw_save_contains_eight_combined_template_slots(self):
        path = local_input("APF_BOOK_RAW_SAVE")
        bodies = {name: identity.read_resource(self.index, identity.filename_id(name), "spb", "SPLB")[3]
                  for name in ("USER-o", "USER-d")}
        report = probe.save_evidence(path, bodies)
        self.assertEqual(report["serialized_slots"], 8)
        self.assertEqual(report["bank_start"], 0x258004)
        self.assertTrue(all(x["matches_20_USER_o_records"] and x["matches_6_USER_d_records"]
                            and x["mask_is_template_OR"] for x in report["slots"]))


if __name__ == "__main__":
    unittest.main()

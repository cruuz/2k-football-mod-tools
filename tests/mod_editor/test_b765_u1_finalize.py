"""A follow-up font cannot be marked closed without complete native scope proof."""
import copy
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b765.u1_finalize import check_font_receipt, check_helmet_receipt


class FontAuditScope(unittest.TestCase):
    def setUp(self):
        self.make_case("MIN", "15", {"H", "A"})

    def make_case(self, team, code, arm_sides):
        self.before, self.after = {}, {}
        resources, measurements = {}, []
        for selector in (code + "H0", code + "A0"):
            owned = set(range(13, 23)) | (set(range(33, 43)) if selector[2] in arm_sides else set())
            assets = [dict(chunk_index=i, offset=i*128, length=64, span_sha256=f"before-{i}")
                      for i in range(1, 73)]
            updated = [dict(a, span_sha256=f"after-{a['chunk_index']}")
                       if a["chunk_index"] in owned else dict(a) for a in assets]
            self.before[selector] = dict(resource_sha256="resource-before", assets=assets)
            self.after[selector] = dict(resource_sha256="resource-after", assets=updated)
            resources[selector] = dict(outside_scope_identical=True, idempotent=True,
                before_sha256="resource-before", after_sha256="resource-after",
                spans=[dict(offset=i*128, length=64, before_sha256=f"before-{i}", after_sha256=f"after-{i}")
                       for i in sorted(owned)])
            measurements += [dict(selector=selector, digit=i, family="jersey_digit") for i in range(10)]
            if selector[2] in arm_sides:
                measurements += [dict(selector=selector, digit=i, family="arm_digit") for i in range(10)]
        self.doc = dict(schema="b765/u1/fonts/v1", team=team, families=["jersey_digit", "arm_digit"],
                        resources=resources, digits=measurements)

    def test_complete_native_scope_accepts(self):
        self.assertIs(check_font_receipt(self.doc, self.before, self.after), self.doc)

    def test_incomplete_or_duplicate_digits_refused(self):
        for digits in (self.doc["digits"][:-1], self.doc["digits"][:-1] + [self.doc["digits"][0]]):
            with self.assertRaisesRegex(ValueError, "every jersey"):
                check_font_receipt(dict(self.doc, digits=digits), self.before, self.after)

    def test_unowned_family_side_or_team_refused(self):
        for doc in (dict(self.doc, families=["jersey_digit", "helmet_digit"]),
                    dict(self.doc, team="NYG"),
                    dict(self.doc, resources={"15H0": self.doc["resources"]["15H0"]})):
            with self.assertRaises(ValueError):
                check_font_receipt(doc, self.before, self.after)

    def test_false_scope_or_idempotence_refused(self):
        for flag in ("outside_scope_identical", "idempotent"):
            doc = copy.deepcopy(self.doc)
            doc["resources"]["15H0"][flag] = False
            with self.assertRaisesRegex(ValueError, "native resource"):
                check_font_receipt(doc, self.before, self.after)

    def test_resource_hash_mismatch_refused(self):
        after = copy.deepcopy(self.after)
        after["15H0"]["resource_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "native resource"):
            check_font_receipt(self.doc, self.before, after)

    def test_unowned_helmet_or_nameplate_component_change_refused(self):
        for chunk in (23, 43):
            after = copy.deepcopy(self.after)
            after["15H0"]["assets"][chunk-1]["span_sha256"] = "changed"
            with self.assertRaisesRegex(ValueError, "unowned native"):
                check_font_receipt(self.doc, self.before, after)

    def test_jersey_span_pin_or_offset_mismatch_refused(self):
        for field, value in (("offset", 0), ("length", 32), ("before_sha256", "bad"), ("after_sha256", "bad")):
            doc = copy.deepcopy(self.doc)
            doc["resources"]["15H0"]["spans"][0][field] = value
            with self.assertRaisesRegex(ValueError, "number font span"):
                check_font_receipt(doc, self.before, self.after)

    def test_extra_or_duplicate_span_refused(self):
        for count in (19, 21):
            doc = copy.deepcopy(self.doc)
            spans = doc["resources"]["15H0"]["spans"]
            spans[:] = spans[:count] if count == 19 else spans + [spans[0]]
            with self.assertRaisesRegex(ValueError, "exactly its"):
                check_font_receipt(doc, self.before, self.after)

    def test_existing_blank_arm_family_must_remain_byte_identical(self):
        self.make_case("ARI", "00", {"H"})
        check_font_receipt(self.doc, self.before, self.after)
        self.after["00A0"]["assets"][32]["span_sha256"] = "changed"
        with self.assertRaisesRegex(ValueError, "unowned native"):
            check_font_receipt(self.doc, self.before, self.after)


class HelmetAuditScope(unittest.TestCase):
    def setUp(self):
        self.before, self.after, resources = {}, {}, {}
        for selector in ("18H0", "18A0"):
            assets = [dict(chunk_index=i, offset=i * 128, length=64,
                           span_sha256=f"before-{i}") for i in range(1, 73)]
            updated = [dict(a, span_sha256="after-12") if a["chunk_index"] == 12
                       else dict(a) for a in assets]
            self.before[selector] = dict(resource_sha256="before", assets=assets)
            self.after[selector] = dict(resource_sha256="after", assets=updated)
            pixel = dict(family="helmet02", mip_levels=[1], protected_changed_texels=0,
                         system_identical=True, descriptor_identical=True, allocation_identical=True,
                         levels=[dict(level=i, dimensions=[256 >> i] * 2,
                                      protected_changed_texels=0, protected_before_sha256="same",
                                      protected_after_sha256="same", changed_texels=3 if i == 1 else 0)
                                 for i in range(6)])
            resources[selector] = dict(before_sha256="before", after_sha256="after",
                    outside_scope_identical=True, idempotent=True,
                    spans=[dict(offset=12 * 128, length=64, before_sha256="before-12",
                                after_sha256="after-12", helmet_pixel_scope=pixel)])
        self.doc = dict(schema="b765/u1/nyg-logo-mips-receipt/v1", resources=resources,
                        geometry_edited=False)

    def test_complete_protected_mip_receipt_accepts(self):
        self.assertIs(check_helmet_receipt(self.doc, self.before, self.after), self.doc)

    def test_unowned_component_change_refused(self):
        for chunk in (11, 13, 33):
            after = copy.deepcopy(self.after)
            after["18H0"]["assets"][chunk - 1]["span_sha256"] = "changed"
            with self.assertRaisesRegex(ValueError, "unowned component"):
                check_helmet_receipt(self.doc, self.before, after)

    def test_missing_side_or_geometry_change_refused(self):
        for change in (dict(geometry_edited=True), dict(resources={"18H0": self.doc["resources"]["18H0"]})):
            with self.assertRaises(ValueError):
                check_helmet_receipt(dict(self.doc, **change), self.before, self.after)

    def test_base_or_coarse_mip_setback_refused(self):
        for level in (0, 3, 4, 5):
            doc = copy.deepcopy(self.doc)
            doc["resources"]["18H0"]["spans"][0]["helmet_pixel_scope"]["levels"][level]["changed_texels"] = 1
            with self.assertRaisesRegex(ValueError, "protected mip"):
                check_helmet_receipt(doc, self.before, self.after)

    def test_protected_pixel_and_descriptor_claims_refused(self):
        for field, value in (("protected_changed_texels", 1), ("descriptor_identical", False),
                             ("system_identical", False), ("mip_levels", [1, 2]),
                             ("mip_levels", [1, 2, 3])):
            doc = copy.deepcopy(self.doc)
            doc["resources"]["18H0"]["spans"][0]["helmet_pixel_scope"][field] = value
            with self.assertRaisesRegex(ValueError, "pixel protection"):
                check_helmet_receipt(doc, self.before, self.after)


if __name__ == "__main__":
    unittest.main()

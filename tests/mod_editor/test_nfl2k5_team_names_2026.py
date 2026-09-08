"""Bounded resource/image tests; only synthetic images are written."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "tests", ROOT / "tools"):
    sys.path.insert(0, str(p))
from mod_editor.core import nfl2k5_team_names_2026 as names
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_ages as ages
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_text_catalog import encode_fixed_utf16le, Nfl2k5TextCatalog, load_roster_resources
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, RETAIL_EXTRACTION
from nfl2k5_xiso_fixture import SyntheticXiso


def synthetic_resource():
    data = names.manifest()
    body = bytearray(synthetic_body())
    body[:64] = bytes.fromhex(data["body_prefix_hex"])
    for pin in data["structure_pins"]:
        value = bytes.fromhex(pin["hex"])
        body[pin["offset"]:pin["offset"] + len(value)] = value
    for cell in data["cells"]:
        off, size, field = cell["body_offset"], cell["allocation_bytes"], cell["pointer_offset"]
        body[off:off + size] = encode_fixed_utf16le(cell["retail"], size, cell["field"])
        struct.pack_into("<i", body, field, off - field + 1)
    return bytes.fromhex(data["resource_header_hex"]) + bytes(body)


class NamesTests(unittest.TestCase):
    def setUp(self):
        self.before = synthetic_resource()

    def test_manifest_enumerates_32_teams_and_every_difference_and_fallback(self):
        data = names.manifest()
        self.assertEqual([t["index"] for t in data["teams"]], list(range(32)))
        self.assertEqual([t["index"] for t in data["teams"] if t["retail"] != t["desired"]], [7, 8, 22, 23, 25])
        for t in data["teams"]:
            self.assertEqual(t["retail"]["asset_code"], t["written"]["asset_code"])
        for cell in data["cells"]:
            self.assertEqual(cell["allocation_bytes"], 2 * (len(cell["retail"]) + 1))
            encode_fixed_utf16le(cell["written"], cell["allocation_bytes"], cell["field"])
            if cell["written"] != cell["desired"]:
                with self.assertRaises(ValidationError):
                    encode_fixed_utf16le(cell["desired"], cell["allocation_bytes"], cell["field"])

    def test_exact_spans_idempotence_and_unchanged_pointers(self):
        after, receipt = names.apply(self.before)
        self.assertEqual(names.status(self.before), "retail")
        self.assertEqual(names.status(after), "applied")
        self.assertEqual(receipt["changed_spans"], 17)
        self.assertEqual(receipt["growth_bytes"], 0)
        allowed = {i for cell in receipt["writes"] for i in range(cell["resource_offset"],
                   cell["resource_offset"] + cell["allocation_bytes"])}
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(self.before, after)) if a != b))
        self.assertEqual(len(after), len(self.before))
        again, repeated = names.apply(after)
        self.assertEqual(again, after)
        self.assertEqual(repeated["changed_spans"], 0)
        for cell in receipt["writes"]:
            off = cell["pointer_offset"] + 32
            self.assertEqual(after[off:off + 4], self.before[off:off + 4])

    def test_each_partial_write_and_foreign_byte_refuses(self):
        after, receipt = names.apply(self.before)
        for cell in receipt["writes"]:
            start, size = cell["resource_offset"], cell["allocation_bytes"]
            for src, dst in ((self.before, after), (after, self.before)):
                mixed = bytearray(src)
                mixed[start:start + size] = dst[start:start + size]
                self.assertEqual(names.status(mixed), "foreign")
                with self.assertRaises(names.TeamNamesError):
                    names.apply(mixed)
        for off in (0, 32 + 0x10, 32 + 0x58, receipt["writes"][-1]["resource_offset"]):
            foreign = bytearray(self.before)
            foreign[off] ^= 0x01
            snapshot = bytes(foreign)
            with self.assertRaises(names.TeamNamesError):
                names.apply(foreign)
            self.assertEqual(foreign, snapshot)
        self.assertEqual(names.status(self.before[:-1]), "foreign")

    def test_foreign_pointer_and_player_alias_refuse(self):
        cell = names.manifest()["cells"][0]
        for field, target in ((cell["pointer_offset"], cell["body_offset"] + 2),
                              (0xAFA8 + 0x10, cell["body_offset"]),
                              (0xAFA8 + 0x10, cell["body_offset"] + 2)):
            body = bytearray(self.before)
            struct.pack_into("<i", body, 32 + field, target - field + 1)
            self.assertEqual(names.status(body), "foreign")

    def test_shared_catalog_uses_actual_short_forms_and_rejects_manual_conflicts(self):
        assets = [SimpleNamespace(asset_id=f"nfl2k5.text.rost.5.{c['domain']}.{c['team_index']}.{c['field']}",
                                  value=c["retail"], label=c["field"]) for c in names.manifest()["cells"]]
        catalog = SimpleNamespace(assets=assets)
        self.assertEqual(names.catalog_overrides(catalog), {})
        values = names.catalog_overrides(catalog, enabled=True)
        self.assertEqual(values["nfl2k5.text.rost.5.team.25.nickname"], "Cmdrs")
        self.assertEqual(values["nfl2k5.text.rost.5.team_label.25.nickname"], "Cmdrs")
        self.assertEqual(values["nfl2k5.text.rost.5.team.8.abbreviation"], "LA")
        assets[-1].value = "CUSTOM"
        with self.assertRaisesRegex(names.TeamNamesError, "manual edit"):
            names.catalog_overrides(catalog, enabled=True)

    def test_real_archive_adapter_relocated_pack_copy_noop_refusal_and_closed_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            fixture = SyntheticXiso(root, [(100 + i, b"DUMY" + bytes(256)) for i in range(5)] +
                                    [(5, self.before), (200, b"TAIL" + bytes(256))],
                                    pack_sizes=(0xA0000,), pack_sectors=(96,))
            original = fixture.path.read_bytes()  # capped < 1 MB synthetic image only
            self.assertEqual(names.image_status(fixture.path), "retail")
            with rr._outer_image()(fixture.path) as archive:
                entry = archive.entries[5]
                offset = archive.packs[0].image_offset + entry.virtual_offset
            receipt = names.apply_to_image(fixture.path)
            expected = bytearray(original)
            expected[offset:offset + len(self.before)] = names.apply(self.before)[0]
            self.assertEqual(fixture.path.read_bytes(), expected)
            self.assertEqual(receipt["status"], "applied")
            with patch.object(rr._outer_image(), "write", side_effect=AssertionError("idempotent write")):
                self.assertTrue(names.apply_to_image(fixture.path)["already_applied"])
            fixture.path.write_bytes(original)
            with patch.object(rr._outer_image(), "write", return_value=1):
                with self.assertRaisesRegex(names.TeamNamesError, "short"):
                    names.apply_to_image(fixture.path)
            os.replace(fixture.path, root / "closed.iso")


class RetailNamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RETAIL_EXTRACTION / "vc_53450030/0").is_file():
            raise unittest.SkipTest("private retail extraction is absent")
        with rr._outer_image()(RETAIL_EXTRACTION) as archive:
            cls.entry = archive.entries[5]
            cls.before = archive.read(cls.entry.virtual_offset, cls.entry.size)

    def test_retail_names_and_both_orders_with_ages_and_roster_edits(self):
        named, _ = names.apply(self.before)
        actual = names.read_team_identities(named)
        self.assertEqual(actual[25]["display"], "Washington Cmdrs")
        self.assertEqual(actual[22]["display"], "L Vegas Raiders")
        self.assertEqual(actual[8]["abbreviation"], "LA")
        self.assertEqual(actual[23]["abbreviation"], "LAR")
        self.assertEqual(names.read_team_identities(self.before, enabled=True), actual)
        def change(resource):
            doc = rr.RosterDocument(resource[32:])
            doc.players[0].record.set("scramble", 97)
            ages.apply(doc, ages.preview(doc, 2004, 2026))
            return resource[:32] + doc.to_body()
        self.assertEqual(names.apply(change(self.before))[0], change(named))

    def test_existing_team_identity_catalog_points_at_same_fields(self):
        header = struct.unpack_from("<4s7I", self.before)
        row = dict(kind="ROST", outer_index=5, outer_id=hex(self.entry.name_id), outer_size=self.entry.size,
                   chunk_index=0, chunk_offset=0, stored_size=header[1], word_08=header[2], word_0c=header[3],
                   word_10=header[4], word_14=header[5])
        inventory = {"schema": "nfl2k5_resource_chunk_inventory/v1", "chunks": [row]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "inventory.json"
            path.write_text(json.dumps(inventory))
            views = load_roster_resources(RETAIL_EXTRACTION / "vc_53450030/0", path, [5])
        catalog = Nfl2k5TextCatalog.from_parsed(inventory, views)
        overrides = names.catalog_overrides(catalog, enabled=True)
        for team in catalog.teams[:32]:
            fields = dict(team.text_asset_ids)
            for name in ("city", "nickname", "abbreviation"):
                asset = next(a for a in catalog.assets if a.asset_id == fields[name])
                value = overrides.get(asset.asset_id, asset.value)
                self.assertEqual(value, names.manifest()["teams"][team.team_index]["written"][name])

    def test_composes_with_history_prospect_names_and_position_pools_in_both_orders(self):
        from mod_editor.core import nfl2k5_team_history as history, nfl2k5_prospect_names as prospects
        import nfl2k5_roster_reclassify as reclassify
        history_rows = history.read_csv(history.SHIPPED_CSV.read_text())
        prospect_rows = prospects.read_csv(prospects.SHIPPED_CSV.read_text())
        def other_passes(resource):
            parsed = reclassify.parse_resource(5, 0, resource)
            moves, _schemes = reclassify.plan_resource(parsed, {})
            body = bytearray(parsed.body)
            reclassify.apply_moves(body, moves)
            body, _ = history.apply_body(bytes(body), history_rows)
            body, _ = prospects.apply_body(body, prospect_rows)
            return resource[:32] + body
        self.assertEqual(names.apply(other_passes(self.before))[0],
                         other_passes(names.apply(self.before)[0]))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import struct
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_text_catalog import (
    Nfl2k5TextCatalog,
    Nfl2k5TextEdits,
    RosterResourceView,
    TextAccess,
    encode_fixed_utf16le,
)


def _put(body: bytearray, offset: int, value: str) -> None:
    payload = (value + "\0").encode("utf-16le")
    body[offset:offset + len(payload)] = payload


def _fixture(*, shared_player_name: bool = False) -> tuple[dict, RosterResourceView]:
    body = bytearray(0x900)
    _put(body, 0x20, "historic")
    strings = {
        "nickname": (0x300, "Comets '80"),
        "abbreviation": (0x318, "COM80"),
        "asset_code": (0x324, "42"),
        "city": (0x32A, "Orbit City"),
        "city_abbreviation": (0x340, "ORB"),
        "first_name": (0x348, "Alex"),
        "last_name": (0x352, "Smith"),
    }
    if shared_player_name:
        strings["last_name"] = strings["first_name"]
    for offset, value in strings.values():
        _put(body, offset, value)

    raw = bytearray(0x54)
    struct.pack_into("<H", raw, 0x06, 1234)
    struct.pack_into("<I", raw, 0x20, (12 << 3) | 0x80000)
    raw[0x35] = 3
    parsed = {
        "label": "historic",
        "teams": [{
            "index": 0,
            "nickname": strings["nickname"][1],
            "nickname_offset": strings["nickname"][0],
            "abbreviation": strings["abbreviation"][1],
            "abbreviation_offset": strings["abbreviation"][0],
            "asset_code": strings["asset_code"][1],
            "asset_code_offset": strings["asset_code"][0],
            "city": strings["city"][1],
            "city_offset": strings["city"][0],
            "city_abbreviation": strings["city_abbreviation"][1],
            "city_abbreviation_offset": strings["city_abbreviation"][0],
        }],
        "players": [{
            "pool": "primary_players",
            "index": 0,
            "first_name": strings["first_name"][1],
            "first_name_offset": strings["first_name"][0],
            "last_name": strings["last_name"][1],
            "last_name_offset": strings["last_name"][0],
            "raw_hex": raw.hex(),
        }],
        "stadiums": [], "coaches": [], "colleges": [],
        "historic_descriptors": [], "team_labels": [], "generated_names": [],
    }
    view = RosterResourceView(113, "0x12345678", 0x920, 0x1800, bytes(body), parsed)
    inventory = {
        "schema": "nfl2k5_resource_chunk_inventory/v1",
        "chunks": [
            {"kind": "ROST", "outer_index": 113, "chunk_index": 0,
             "outer_id": "0x12345678"},
            {"kind": "SITU", "outer_index": 900, "chunk_index": 0,
             "outer_id": "0x87654321"},
        ],
    }
    return inventory, view


class Nfl2k5TextCatalogTests(unittest.TestCase):
    def test_fixed_utf16_contract_accepts_shorter_and_zero_pads(self) -> None:
        payload = encode_fixed_utf16le("NY", 10, "City")
        self.assertEqual(payload, "NY".encode("utf-16le") + bytes(6))
        self.assertEqual(len(payload), 10)
        with self.assertRaisesRegex(ValidationError, "allows 4"):
            encode_fixed_utf16le("ABCDE", 10, "City")
        with self.assertRaisesRegex(ValidationError, "NUL"):
            encode_fixed_utf16le("A\0B", 10, "City")
        with self.assertRaisesRegex(ValidationError, "UTF-16 units"):
            encode_fixed_utf16le("😀😀😀", 10, "City")

    def test_catalog_surfaces_historical_identity_names_numbers_and_limits(self) -> None:
        inventory, view = _fixture()
        catalog = Nfl2k5TextCatalog.from_parsed(inventory, {113: view})
        self.assertEqual(len(catalog.banks), 2)
        unresolved = catalog.get_bank("nfl2k5.text-bank.situ.900.0")
        self.assertFalse(unresolved.decoded)
        self.assertEqual(unresolved.access, "read_only")
        self.assertTrue(catalog.teams[0].historical)
        self.assertTrue(catalog.teams[0].editable)
        self.assertTrue(catalog.players[0].historical)
        self.assertTrue(catalog.players[0].editable)

        nickname = catalog.get_asset(catalog.teams[0].asset_id_for("nickname"))
        self.assertIs(nickname.access, TextAccess.EDITABLE)
        self.assertEqual(
            nickname.allocation_bytes, len(("Comets '80\0").encode("utf-16le"))
        )
        self.assertEqual(nickname.character_limit, len("Comets '80"))
        asset_code = catalog.get_asset(catalog.teams[0].asset_id_for("asset_code"))
        self.assertIs(asset_code.access, TextAccess.READ_ONLY)
        self.assertIn("uniforms/art", asset_code.reason)
        found = catalog.search("alex first", editable=True)
        self.assertEqual([item.field for item in found], ["first_name"])
        self.assertEqual(catalog.export_payload(found[0].asset_id), b"Alex\n")
        number = catalog.get_number_asset(catalog.players[0].jersey_number_asset_id)
        self.assertEqual(number.value, 12)
        self.assertTrue(number.editable)

    def test_staged_edits_are_sparse_reversible_and_retail_free(self) -> None:
        inventory, view = _fixture()
        catalog = Nfl2k5TextCatalog.from_parsed(inventory, {113: view})
        session = Nfl2k5TextEdits(catalog)
        team, player = catalog.teams[0], catalog.players[0]
        nickname = team.asset_id_for("nickname")
        session.set_text(nickname, "Comets")
        session.set_text(player.first_name_asset_id, "Al")
        session.set_number(player.jersey_number_asset_id, 88)
        self.assertEqual(session.modified_count, 3)
        self.assertEqual(session.provider_edits(), (
            {"kind": "roster_player_text", "resource_outer_index": 113,
             "primary_player_index": 0,
             "changes": {"first_name": "Al", "jersey_number": 88}},
            {"kind": "roster_team_text", "resource_outer_index": 113,
             "team_index": 0, "changes": {"nickname": "Comets"}},
        ))
        document = session.replacement_document()
        encoded = session.canonical_replacement_bytes()
        self.assertEqual(document["schema"], "2k5_mod_studio_text_replacements/v1")
        self.assertNotIn(b"Orbit City", encoded)
        self.assertNotIn(b"Smith", encoded)
        self.assertNotIn(b"Comets '80", encoded)

        session.revert(nickname)
        self.assertEqual(session.value(nickname), "Comets '80")
        self.assertTrue(session.undo())
        self.assertEqual(session.value(nickname), "Comets")
        clone = Nfl2k5TextEdits(catalog)
        clone.load_replacement_document(document)
        self.assertEqual(clone.provider_edits(), session.provider_edits())
        clone.revert_all()
        self.assertEqual(clone.modified_count, 0)

    def test_shared_name_allocations_fail_closed_as_read_only(self) -> None:
        inventory, view = _fixture(shared_player_name=True)
        catalog = Nfl2k5TextCatalog.from_parsed(inventory, {113: view})
        player = catalog.players[0]
        first = catalog.get_asset(player.first_name_asset_id)
        last = catalog.get_asset(player.last_name_asset_id)
        self.assertEqual(first.reference_count, 2)
        self.assertEqual(last.reference_count, 2)
        self.assertIs(first.access, TextAccess.READ_ONLY)
        self.assertIs(last.access, TextAccess.READ_ONLY)
        self.assertFalse(player.editable)
        with self.assertRaisesRegex(ValidationError, "shared"):
            Nfl2k5TextEdits(catalog).set_text(first.asset_id, "A")

    def test_replacement_document_rejects_read_only_and_duplicates(self) -> None:
        inventory, view = _fixture()
        catalog = Nfl2k5TextCatalog.from_parsed(inventory, {113: view})
        session = Nfl2k5TextEdits(catalog)
        asset_code = catalog.teams[0].asset_id_for("asset_code")
        with self.assertRaisesRegex(ValidationError, "outside"):
            session.load_replacement_document({
                "schema": "2k5_mod_studio_text_replacements/v1",
                "edits": [{"asset_id": asset_code, "kind": "text", "value": "99"}],
            })
        first = catalog.players[0].first_name_asset_id
        with self.assertRaisesRegex(ValidationError, "repeats"):
            session.load_replacement_document({
                "schema": "2k5_mod_studio_text_replacements/v1",
                "edits": [
                    {"asset_id": first, "kind": "text", "value": "Al"},
                    {"asset_id": first, "kind": "text", "value": "A"},
                ],
            })

    def test_private_cache_merges_safe_banks_without_duplicate_strg(self) -> None:
        source_sha = (
            "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
        )
        root = Path.home() / ".cache" / "2k5-mod-studio" / source_sha
        pack0 = root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
        inventory = root / "indexes/nfl2k5_resource_chunks_v2.json"
        if not pack0.is_file() or not inventory.is_file():
            self.skipTest("recognized private NFL 2K5 cache is not present")

        catalog = Nfl2k5TextCatalog.from_paths(pack0, inventory)
        self.assertEqual(len(catalog.banks), 716)
        self.assertEqual(len(catalog.assets), 23_346)
        self.assertEqual(catalog.editable_count, 20_074)
        self.assertEqual(catalog.read_only_count, 3_272)
        strg = [asset for asset in catalog.assets if asset.owner_kind == "strg_text"]
        self.assertEqual(len(strg), 1_115)
        self.assertEqual(len({asset.asset_id for asset in strg}), 1_115)

        situ = catalog.get_asset("nfl2k5.text.situ.moment.0.title")
        self.assertTrue(situ.editable)
        edits = Nfl2k5TextEdits(catalog)
        edits.set_text(situ.asset_id, "MOD")
        self.assertEqual(edits.provider_edits(), ({
            "kind": "universal_fixed_text",
            "selector": "situ:moment:0:title",
            "text": "MOD",
        },))
        shareable = edits.replacement_document()
        self.assertEqual(shareable["edits"], [{
            "asset_id": situ.asset_id,
            "kind": "text",
            "value": "MOD",
        }])
        encoded = json.dumps(shareable, sort_keys=True)
        for forbidden in ("selector", "offset", "preimage", "pack_name"):
            self.assertNotIn(forbidden, encoded)

        selector = catalog.get_asset(
            "nfl2k5.text.situ.moment.0.away_team_asset_code"
        )
        self.assertFalse(selector.editable)
        self.assertIn("team-resource selector", selector.reason)
        situation_bank = catalog.get_bank(selector.bank_id)
        self.assertIn("Coming Soon", situation_bank.reason)
        name_bank = next(bank for bank in catalog.banks if bank.kind == "NAME")
        self.assertIn("glyph metrics", name_bank.label)


if __name__ == "__main__":
    unittest.main()

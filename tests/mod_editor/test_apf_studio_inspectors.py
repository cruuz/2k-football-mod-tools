from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.apf_studio.inspectors import (
    ApfInspectorService,
    ExportIdentity,
    InspectorError,
    PagedModel,
    _jukebox_presentation,
    _row,
    classify_audo_role,
    classify_ausb_role,
    discover_external_audio_banks,
    export_semantic_rows,
    inspect_audio,
    inspect_localization,
    inspect_playbooks_directors,
    inspect_roster,
    inspect_uniform_selectors,
)
from mod_editor.apf_studio.models import (
    ApfSource,
    ExternalAudioBankIdentity,
)
from mod_editor.apf_studio.player_ratings import load_player_rating_schema


PLAYER_RATING_SCHEMA = load_player_rating_schema()


def _source() -> ApfSource:
    path = Path("/not-retail/0A")
    return ApfSource(
        selected_path=path,
        game_root=path.parent,
        index_0a=path,
        source_sha256="fixture",
        source_size=0,
        xex_sha256="fixture",
        display_name="APF unit fixture",
    )


def _roster_report() -> dict[str, object]:
    stadiums = [
        {
            "stadium_index": index,
            "display_name": f"Stadium {index}",
            "asset_key": f"stadium_{index}",
            "capacity": 50_000 + index,
            "description": f"Fixture stadium {index}",
        }
        for index in range(31)
    ]
    teams = [
        {
            "team_index": index,
            "display_name": "Needle Team" if index == 0 else f"Team {index}",
            "abbreviation": f"T{index:02d}",
            "secondary_abbreviation": f"X{index:02d}",
            "numeric_string_code": str(index),
            "derived_slot_kind": "built_in_team" if index < 32 else "user_slot",
            "roster_count": 34 if index < 24 else 33 if index < 40 else 0,
            "stadium_index": index % 31,
            "stadium_name": stadiums[index % 31]["display_name"],
        }
        for index in range(40)
    ]
    players = [
        {
            "player_index": index,
            "first_name": "Needle" if index == 0 else f"First{index}",
            "last_name": f"Last{index}",
            "position_code": index % 17,
            "position_abbreviation": "QB" if index % 17 == 0 else "WR",
            "position_name": "Quarterback" if index % 17 == 0 else "Wide Receiver",
            "base_ratings": {
                field.field_id: (
                    100
                    if index == 0 and field.field_id == "unknown_rating_d4"
                    else (index + field.display_order) % 100
                )
                for field in PLAYER_RATING_SCHEMA.fields
            },
            "team_memberships": [],
            "strings": {"biography": f"Bio {index}"},
            "hall_of_fame_induction_year_at_0x112": 0,
            "championship_count_at_0x114": 0,
            "championship_game_appearance_count_at_0x115": 0,
            "all_pro_game_count_at_0x116": 0,
        }
        for index in range(2_254)
    ]
    memberships = []
    for index in range(1_344):
        team_index = index % 40
        membership = {
            "team_index": team_index,
            "roster_slot": index // 40,
            "player_index": index,
        }
        memberships.append(membership)
        players[index]["team_memberships"].append(
            {
                "team_index": team_index,
                "team_name": teams[team_index]["display_name"],
                "roster_slot": index // 40,
            }
        )
    return {
        "players": players,
        "teams": teams,
        "stadiums": stadiums,
        "team_roster_memberships": memberships,
    }


def _roster_identity_fixture() -> tuple[object, ...]:
    rows: list[object] = []
    ordinal = 0
    for entity_kind, count, fields in (
        ("player", 2_254, ("first_name", "last_name")),
        (
            "team",
            40,
            ("display_name", "abbreviation", "secondary_abbreviation"),
        ),
    ):
        for entity_index in range(count):
            for field in fields:
                owner = SimpleNamespace(
                    owner_id=f"{entity_kind}:{entity_index}:{field}",
                    entity_kind=entity_kind,
                    entity_index=entity_index,
                    field=field,
                )
                rows.append(
                    SimpleNamespace(
                        asset_id=f"apf:roster-name:{ordinal}",
                        maximum_utf16_units=16,
                        editable=True,
                        known_owner_count=1,
                        known_owners=(owner,),
                        note="Fixture fixed allocation.",
                    )
                )
                ordinal += 1
    return tuple(rows)


def _localization_tables() -> list[dict[str, object]]:
    table_specs = ((10, 0, "credits_English", 747, 640), (11, 0, "English", 825, 639))
    tables: list[dict[str, object]] = []
    global_pool = 0
    for outer, inner, name, record_count, pool_count in table_specs:
        pool = []
        for pool_index in range(pool_count):
            text = "Needle localization" if global_pool == 0 else f"Pool text {global_pool}"
            pool.append({"pool_index": pool_index, "offset": pool_index * 2, "text": text})
            global_pool += 1
        records = []
        for index in range(record_count):
            control = name == "English" and index == record_count - 1
            pool_index = None if control else index % pool_count
            records.append(
                {
                    "outer_index": outer,
                    "inner_index": inner,
                    "table_name": name,
                    "record_index": index,
                    "text_id": f"0x{index:08x}",
                    "is_control_record": control,
                    "pool_index": pool_index,
                    "text": None if control else pool[pool_index]["text"],
                }
            )
        tables.append(
            {
                "outer_index": outer,
                "inner_index": inner,
                "inner_name": name,
                "records": records,
                "pool": pool,
                "unreferenced_pool_indices": [0],
                "byte_identical_rebuild": True,
            }
        )
    return tables


def _named_records(kind: str, count: int, size: int) -> list[dict[str, object]]:
    return [
        {
            "index": index,
            "name": "Needle Play" if kind == "play" and index == 0 else f"{kind} {index}",
            "offset": index * size,
            "size": size,
            **(
                {
                    "flags_or_id_04": "0x00000000",
                    "unknown_word_08": "0x00000000",
                    "slots": [
                        {"route_node_index": (index * 11 + slot) % 4_948}
                        for slot in range(11)
                    ],
                }
                if kind == "play"
                else {}
            ),
        }
        for index in range(count)
    ]


def _playbook_fixture() -> list[dict[str, object]]:
    return [
        {
            "outer_index": 180,
            "inner_index": 0,
            "inner_name": "mpb",
            "book_name": "MASTER",
            "root_counts": {
                "formation_count": 163,
                "play_count": 586,
                "category_count": 28,
                "route_node_count": 4_948,
            },
            "formations": _named_records("formation", 163, 0xB8),
            "plays": _named_records("play", 586, 0x64),
            "categories": _named_records("category", 28, 0x10),
            "route_node_blob_hex": (b"\x01\x02\x03\x04\x05\x06\x07\x08" * 4_948).hex(),
        }
    ]


def _director_fixture() -> list[dict[str, object]]:
    roles = (
        ("ingame", 112, 1015, 7),
        ("wrapup", 20, 96, 0),
        ("tutorial", 1, 3, 101),
        ("halftime", 1, 116, 12),
        ("intro", 3, 393, 0),
    )
    result = []
    for outer, (role, fixed_count, instruction_count, string_count) in enumerate(roles, 200):
        fixed = [
            {
                "slot_index": index,
                "ordinal": index,
                "offset": index * 32,
                "package_size": 32,
                "child_count": index % 3,
                "unknown_u16_04": 0,
                "unknown_u16_06": 0,
            }
            for index in range(fixed_count)
        ]
        instructions = [
            {
                "index": index,
                "offset": index * 4,
                "size": 4,
                "first_byte": index & 0xFF,
                "head_hex": "00000000",
            }
            for index in range(instruction_count)
        ]
        strings = [
            {
                "index": index,
                "offset": index * 8,
                "size": 8,
                "text": "Needle director" if role == "tutorial" and index == 0 else f"String {index}",
            }
            for index in range(string_count)
        ]
        result.append(
            {
                "outer_index": outer,
                "inner_index": 0,
                "outer_name": f"{role}.iff",
                "role": role,
                "graph": {
                    "nonnull_fixed_record_count": fixed_count,
                    "instruction_count": instruction_count,
                    "string_count": string_count,
                    "fixed_records": fixed,
                    "instructions": instructions,
                    "strings": strings,
                },
            }
        )
    return result


def _selector_fixture() -> tuple[dict[str, object], list[dict[str, object]]]:
    teams = []
    selector_record = 0
    for team_index in range(40):
        banks = []
        for bank_index in range(2):
            selectors = []
            for slot in range(14):
                selectors.append(
                    {
                        "slot": slot,
                        "families": ["jersey"] if slot == 4 else [],
                        "asset_index_byte_0": team_index % 24,
                        "selector_record_index": selector_record,
                        "raw_record_hex": "0100000000000000",
                        "opaque_bytes_1_7_hex": "00000000000000",
                        "semantic_status": "fixture",
                    }
                )
                selector_record += 1
            banks.append({"bank": bank_index, "selectors": selectors})
        teams.append(
            {
                "team_index": team_index,
                "display_name": "Needle Team" if team_index == 0 else f"Team {team_index}",
                "abbreviation": f"T{team_index:02d}",
                "slot_kind": "built_in_team",
                "config_record_index": team_index,
                "banks": banks,
            }
        )
    return {"team_count": 40}, teams


class _Reader:
    def __init__(self, _archive: object):
        pass

    def __enter__(self) -> "_Reader":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _audio_fixture() -> tuple[object, object, list[int]]:
    audo = [
        SimpleNamespace(
            index=index,
            name="Needle AUDO" if index == 0 else f"audo_{index}",
            type_name="AUDO",
            parts=(
                SimpleNamespace(block_index=0, length=44, role="metadata"),
                SimpleNamespace(block_index=1, length=2_048, role="payload"),
            ),
        )
        for index in range(2_261)
    ]
    ausb_counts = [2_276] * 19 + [2_270]
    ausb = [
        SimpleNamespace(
            index=2_261 + index,
            name="Needle AUSB" if index == 0 else f"ausb_{index}",
            type_name="AUSB",
            parts=(SimpleNamespace(block_index=0, bank_index=index),),
        )
        for index in range(20)
    ]
    iff_entry = SimpleNamespace(
        table_index=5,
        name_id=5,
        head_hex="ff3bef94",
        size=1,
    )
    external = [
        SimpleNamespace(
            table_index=100 + index,
            name_id=1_000 + index,
            head_hex="08000000",
            size=10 * 1024 * 1024,
        )
        for index in range(19)
    ]
    archive = SimpleNamespace(entries=[iff_entry, *external])
    record = SimpleNamespace(files=[*audo, *ausb])
    return archive, record, ausb_counts


class ApfStudioInspectorTests(unittest.TestCase):
    def test_paging_search_and_kind_filters_are_headless(self) -> None:
        model = PagedModel(
            tuple(
                _row(f"row:{index}", "even" if index % 2 == 0 else "odd", f"Title {index}", "", {"index": index})
                for index in range(12)
            )
        )
        page = model.page(kinds="even", search="title", offset=2, limit=3)
        self.assertEqual(page.total, 6)
        self.assertEqual([row.row_id for row in page.items], ["row:4", "row:6", "row:8"])
        self.assertEqual(page.previous_offset, 0)
        self.assertEqual(page.next_offset, 5)
        self.assertEqual(model.kind_counts, {"even": 6, "odd": 6})
        with self.assertRaises(InspectorError):
            model.page(limit=0)

    def test_audio_role_filter_and_conservative_taxonomy(self) -> None:
        model = PagedModel(
            (
                _row("a", "audo", "menu_back", "", {"role_id": "ui_menu_sfx"}),
                _row("b", "audo", "mystery", "", {"role_id": "general_sfx"}),
            )
        )
        self.assertEqual(model.page(roles="ui_menu_sfx").total, 1)
        self.assertEqual(model.role_counts, {"general_sfx": 1, "ui_menu_sfx": 1})
        self.assertEqual(classify_audo_role("menu_back")[0], "ui_menu_sfx")
        self.assertEqual(classify_audo_role("unowned_thing")[0], "general_sfx")
        self.assertEqual(classify_ausb_role("jukeboxmusic")[0], "soundtrack_music")
        self.assertEqual(classify_ausb_role("unknown_bank")[0], "general_sfx")
        title, fields = _jukebox_presentation("jukebox22", 0)
        self.assertEqual(title, "Soundtrack Track 01 · Mono companion")
        self.assertIn("not guessed", str(fields["track_title_status"]))

    def test_audio_source_filter_keeps_duplicate_bank_names_coordinate_distinct(self) -> None:
        rows = (
            _row(
                "audo:1",
                "audo",
                "menu_back",
                "",
                {
                    "role_id": "ui_menu_sfx",
                    "audio_source_id": "audo:standalone",
                    "audio_source_label": "Standalone AUDO",
                },
                export_identity=ExportIdentity("audo", 5, 1, None, "menu-back"),
            ),
            _row(
                "bank:8:2",
                "ausb_bank",
                "cwdloop",
                "",
                {
                    "role_id": "diagnostic_ambient",
                    "audio_source_id": "ausb:8:2",
                    "audio_source_label": "cwdloop · O8/I2",
                },
            ),
            _row(
                "bank:8:2:0",
                "ausb_substream",
                "cwdloop 0",
                "",
                {
                    "role_id": "diagnostic_ambient",
                    "audio_source_id": "ausb:8:2",
                    "audio_source_label": "cwdloop · O8/I2",
                },
                export_identity=ExportIdentity(
                    "ausb_substream", 8, 2, 0, "cwdloop-0"
                ),
            ),
            _row(
                "bank:9:3:0",
                "ausb_substream",
                "cwdloop 0",
                "",
                {
                    "role_id": "diagnostic_ambient",
                    "audio_source_id": "ausb:9:3",
                    "audio_source_label": "cwdloop · O9/I3",
                },
                export_identity=ExportIdentity(
                    "ausb_substream", 9, 3, 0, "cwdloop-0"
                ),
            ),
        )
        model = PagedModel(rows)
        selected = model.page(sources="ausb:8:2")
        self.assertEqual(
            [row.row_id for row in selected.items],
            ["bank:8:2", "bank:8:2:0"],
        )
        self.assertEqual(selected.sources, ("ausb:8:2",))
        self.assertEqual(
            model.page(
                sources="ausb:8:2", roles="diagnostic_ambient", kinds="ausb_substream"
            ).total,
            1,
        )
        self.assertEqual(
            model.audio_sources,
            (
                ("audo:standalone", "Standalone AUDO", 1),
                ("ausb:8:2", "cwdloop · O8/I2", 1),
                ("ausb:9:3", "cwdloop · O9/I3", 1),
            ),
        )

        with tempfile.TemporaryDirectory() as directory:
            destination = export_semantic_rows(
                model,
                Path(directory) / "bank.json",
                sources="ausb:9:3",
            )
            document = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(document["filter"]["sources"], ["ausb:9:3"])
            self.assertEqual(document["record_count"], 1)
            self.assertEqual(document["records"][0]["row_id"], "bank:9:3:0")

    def test_filtered_semantic_rows_export_as_json_and_csv(self) -> None:
        model = PagedModel(
            (
                _row("player:0", "player", "Needle Player", "Team 1", {"index": 0, "name": "Needle"}),
                _row("team:1", "team", "Other Team", "Team 1", {"index": 1, "name": "Other"}),
            ),
            ("Read-only decoded fixture.",),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = export_semantic_rows(
                model,
                root / "players.json",
                search="Needle",
                kinds="player",
            )
            document = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], "apf2k8_mod_studio_semantic_export/v1")
            self.assertEqual(document["record_count"], 1)
            self.assertEqual(document["records"][0]["row_id"], "player:0")
            self.assertEqual(document["records"][0]["fields"]["name"], "Needle")

            csv_path = export_semantic_rows(model, root / "all.csv")
            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([row["row_id"] for row in rows], ["player:0", "team:1"])
            self.assertEqual(json.loads(rows[0]["fields_json"])["index"], 0)

            existing = root / "existing.json"
            existing.write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_semantic_rows(model, existing)
            self.assertEqual(existing.read_text(encoding="utf-8"), "preserve")

    def test_roster_snapshot_has_complete_live_shape_and_search(self) -> None:
        with patch("mod_editor.apf_studio.inspectors.apf_roster.load_roster", return_value=(b"fixture", {})), patch(
            "mod_editor.apf_studio.inspectors.apf_roster.build_report", return_value=_roster_report()
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_roster_identity_patch.inventory_from_decoded",
            return_value=_roster_identity_fixture(),
        ):
            snapshot = inspect_roster(_source())
        self.assertEqual(snapshot.summary, {"players": 2254, "teams": 40, "stadiums": 31, "memberships": 1344})
        self.assertEqual(snapshot.model.kind_counts, {"membership": 1344, "player": 2254, "stadium": 31, "team": 40})
        self.assertGreater(snapshot.model.page(search="Needle", limit=20).total, 0)
        player = snapshot.model.page(kinds="player", limit=1).items[0]
        ratings = player.fields["base_ratings"]
        self.assertEqual(len(ratings), len(PLAYER_RATING_SCHEMA.fields))
        self.assertEqual(ratings[0]["label"], "Speed")
        self.assertEqual(ratings[0]["value"], 0)
        self.assertEqual(ratings[25]["label"], "Unknown Rating (0xD4)")
        native_100 = next(
            row for row in ratings if row["id"] == "unknown_rating_d4"
        )
        self.assertEqual(native_100["value"], 100)
        self.assertEqual(native_100["relative_offset_hex"], "0xD4")
        self.assertEqual(player.fields["base_rating_scale"]["native_maximum"], 100)
        first_name_editor = player.fields["identity_editor"]["first_name"]
        self.assertTrue(first_name_editor["runtime_editable"])
        self.assertEqual(first_name_editor["runtime_edit_scope"], "player_name")
        self.assertEqual(
            first_name_editor["known_alias_owners"],
            (
                {
                    "entity_kind": "player",
                    "entity_index": 0,
                    "field": "first_name",
                    "label": "Player 0 · first name",
                },
            ),
        )
        team = snapshot.model.page(kinds="team", limit=1).items[0]
        self.assertTrue(
            team.fields["identity_editor"]["display_name"]["runtime_editable"]
        )
        self.assertFalse(
            team.fields["identity_editor"]["abbreviation"]["runtime_editable"]
        )
        self.assertFalse(
            team.fields["identity_editor"]["secondary_abbreviation"][
                "runtime_editable"
            ]
        )
        self.assertEqual(
            snapshot.model.page(
                search="Pass Arm Strength", kinds="player", limit=20
            ).total,
            2_254,
        )
        self.assertTrue(
            any(
                value.startswith("Editable:") and "source 100" in value
                for value in snapshot.model.findings
            )
        )

    def test_localization_has_1572_records_and_1279_distinct_pool_strings(self) -> None:
        with patch(
            "mod_editor.apf_studio.inspectors.apf_txt_loc.parse_archive",
            return_value=_localization_tables(),
        ):
            snapshot = inspect_localization(_source())
        self.assertEqual(snapshot.summary["records"], 1_572)
        self.assertEqual(snapshot.summary["distinct_texts"], 1_279)
        self.assertEqual(snapshot.summary["control_records"], 1)
        self.assertEqual(snapshot.records.page(search="Needle localization").total, 2)
        self.assertEqual(snapshot.pool.page(search="Needle localization").total, 1)

    def test_playbook_and_director_structures_are_fully_pageable(self) -> None:
        with patch(
            "mod_editor.apf_studio.inspectors.playbook_inventory.parse_apf",
            return_value=_playbook_fixture(),
        ), patch(
            "mod_editor.apf_studio.inspectors.director_inventory.parse_apf",
            return_value=_director_fixture(),
        ):
            snapshot = inspect_playbooks_directors(_source())
        self.assertEqual(snapshot.playbook_summary, {"books": 1, "formations": 163, "plays": 586, "categories": 28, "route_nodes": 4948, "slot_references": 6446})
        self.assertEqual(snapshot.director_summary, {"resources": 5, "fixed_records": 137, "instructions": 1623, "primary_strings": 120})
        self.assertEqual(snapshot.playbooks.kind_counts["route_node"], 4_948)
        self.assertEqual(snapshot.playbooks.page(kinds="play", search="Needle").total, 1)
        self.assertEqual(snapshot.directors.page(kinds="director_string", search="Needle").total, 1)

    def test_selector_banks_use_current_home_away_proof_labels(self) -> None:
        with patch(
            "mod_editor.apf_studio.inspectors.apf_uniform_inventory._load_team_selectors",
            return_value=_selector_fixture(),
        ):
            snapshot = inspect_uniform_selectors(_source())
        self.assertEqual(snapshot.summary, {"teams": 40, "banks": 80, "selectors": 1120})
        home = snapshot.model.get("apf:selector:team:0:bank:0")
        away = snapshot.model.get("apf:selector:team:0:bank:1")
        self.assertEqual((home.fields["proved_label"], home.fields["config_index_start"], home.fields["selector_mode"]), ("HOME", 0, 1))
        self.assertEqual((away.fields["proved_label"], away.fields["config_index_start"], away.fields["selector_mode"]), ("AWAY", 14, 0))
        self.assertEqual(snapshot.model.page(kinds="selector", search="Needle Team HOME").total, 14)

    def test_audio_catalog_addresses_every_audo_and_ausb_substream(self) -> None:
        archive, record, counts = _audio_fixture()

        def parse_ausb(payload: bytes) -> dict[str, object]:
            bank = payload[0]
            count = counts[bank]
            external = bank if bank < 19 else 0
            entries = [
                {"packet_offset": index * 2_048, "value_float": 0.25}
                for index in range(count)
            ]
            return {
                "external_filename": f"bank_{external}.bin",
                "external_filename_crc32_upper_ascii": f"0x{1_000 + external:08x}",
                "entry_count": count,
                "entries": entries,
                "terminal_boundary": {"packet_offset": count * 2_048, "value_float": 0.25},
                "sample_rate": 32_000,
                "channel_layout_code": 2,
                "derived_channel_count": 1,
            }

        with patch(
            "mod_editor.apf_studio.inspectors.apf_outer.parse_archive", return_value=archive
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_inner.ArchiveReader", _Reader
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_inner.parse_iff", return_value=record
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_audio._identify_parts",
            side_effect=lambda _record, item: item.parts,
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_audio._read_part",
            side_effect=lambda _reader, _record, part, _cache, _maximum: (
                b"\x00" * 44
                if getattr(part, "role", "") == "metadata"
                else bytes([part.bank_index])
            ),
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_audio.parse_metadata",
            return_value={
                "encoded_size": 2_048,
                "sample_rate": 32_000,
                "declared_sample_count": 32_000,
                "derived_channel_count": 1,
            },
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_audio.parse_ausb", side_effect=parse_ausb
        ):
            snapshot = inspect_audio(_source())

        self.assertEqual(snapshot.summary, {"audo": 2261, "ausb_banks": 20, "ausb_substreams": 45514, "external_bins": 19})
        self.assertEqual(len(snapshot.external_banks.rows), 19)
        shared_external = snapshot.external_banks.get("apf:audio:external:100")
        self.assertEqual(shared_external.title, "bank_0.bin")
        self.assertEqual(shared_external.kind, "external_bank")
        self.assertIsNone(shared_external.export_identity)
        self.assertIsInstance(
            shared_external.external_bank_identity,
            ExternalAudioBankIdentity,
        )
        self.assertEqual(
            tuple(owner.coordinates for owner in shared_external.external_bank_identity.owners),
            ((5, 2261), (5, 2280)),
        )
        self.assertEqual(
            shared_external.fields["linked_audio_source_ids"],
            ("ausb:5:2261", "ausb:5:2280"),
        )
        self.assertEqual(
            snapshot.external_banks.page(sources="ausb:5:2280").total,
            1,
        )
        self.assertEqual(
            snapshot.external_banks.page(roles="general_sfx").total,
            19,
        )
        self.assertEqual(snapshot.audo.page(search="Needle AUDO").total, 1)
        self.assertEqual(snapshot.ausb_substreams.page(search="Needle AUSB", limit=10).total, counts[0])
        audo_identity = snapshot.audo.rows[0].export_identity
        ausb_identity = snapshot.ausb_substreams.rows[0].export_identity
        self.assertEqual(audo_identity, ExportIdentity("audo", 5, 0, None, "Needle-AUDO"))
        self.assertEqual(ausb_identity, ExportIdentity("ausb_substream", 5, 2261, 0, "Needle-AUSB-00000"))
        self.assertEqual(audo_identity.exporter, "apf_audio.export_selected")
        self.assertEqual(ausb_identity.exporter, "apf_ausb_audio.export_substream")
        self.assertEqual(ausb_identity.coordinates, (5, 2_261, 0))
        self.assertEqual(snapshot.audo.rows[0].fields["audio_format"], "XMA1")
        self.assertEqual(snapshot.audo.rows[0].fields["duration_seconds"], 1.0)
        self.assertEqual(
            snapshot.audo.rows[0].fields["audio_source_id"],
            "audo:standalone",
        )
        self.assertEqual(
            snapshot.ausb_substreams.rows[0].fields["audio_source_id"],
            "ausb:5:2261",
        )

    def test_cached_selection_discovers_exact_external_bank_ownership(self) -> None:
        archive, record, counts = _audio_fixture()
        selection = [
            {
                "table_index": 5,
                "files": [
                    {
                        "index": 2_261 + index,
                        "name": "Needle AUSB" if index == 0 else f"ausb_{index}",
                        "type_name": "AUSB",
                    }
                    for index in range(20)
                ],
            }
        ]

        def parse_ausb(payload: bytes) -> dict[str, object]:
            bank = payload[0]
            external = bank if bank < 19 else 0
            return {
                "external_filename": f"bank_{external}.bin",
                "external_filename_crc32_upper_ascii": f"0x{1_000 + external:08x}",
                "entry_count": counts[bank],
                "sample_rate": 32_000,
                "derived_channel_count": 1,
            }

        with patch(
            "mod_editor.apf_studio.inspectors.apf_outer.parse_archive",
            return_value=archive,
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_inner.ArchiveReader", _Reader
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_inner.parse_iff",
            return_value=record,
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_audio._read_part",
            side_effect=lambda _reader, _record, part, _cache, _maximum: bytes(
                [part.bank_index]
            ),
        ), patch(
            "mod_editor.apf_studio.inspectors.apf_audio.parse_ausb",
            side_effect=parse_ausb,
        ):
            identities = discover_external_audio_banks(_source().index_0a, selection)

        self.assertEqual(len(identities), 19)
        self.assertEqual(sum(len(identity.owners) for identity in identities), 20)
        self.assertEqual(identities[0].external_filename, "bank_0.bin")
        self.assertEqual(
            tuple(owner.coordinates for owner in identities[0].owners),
            ((5, 2261), (5, 2280)),
        )

    def test_service_caches_each_expensive_snapshot(self) -> None:
        service = ApfInspectorService(_source())
        marker = object()
        with patch("mod_editor.apf_studio.inspectors.inspect_roster", return_value=marker) as mocked:
            self.assertIs(service.roster(), marker)
            self.assertIs(service.roster(), marker)
        mocked.assert_called_once_with(service.source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_text_catalog import (
    Nfl2k5TextCatalog,
    Nfl2k5TextEdits,
    RosterNumberAsset,
    RosterPlayer,
    RosterTeam,
    TextAccess,
    TextAsset,
    TextBank,
)
from mod_editor.gui.text_rosters_panel import (
    ESPN_25TH_COMING_SOON_NOTE,
    STATUS_EDITABLE,
    STATUS_MODIFIED,
    STATUS_READ_ONLY,
    TextFilter,
    TextRosterPanel,
    TextRosterPanelHost,
    current_roster_players,
    filter_current_players,
    filter_historical_players,
    filter_text_assets,
    historical_resources,
    roster_number_coverage,
    text_catalog_summary,
    text_usage,
)


def text_asset(
    asset_id: str,
    bank_id: str,
    value: str,
    *,
    outer: int,
    owner_kind: str,
    owner_index: int,
    field: str,
    editable: bool = True,
    group: str | None = None,
) -> TextAsset:
    allocation = len((value + "\0").encode("utf-16le"))
    return TextAsset(
        asset_id=asset_id,
        bank_id=bank_id,
        label=f"{owner_kind} {owner_index} {field}",
        value=value,
        encoding="utf-16le",
        allocation_bytes=allocation,
        character_limit=allocation // 2 - 1,
        used_utf16_code_units=len(value.encode("utf-16le")) // 2,
        access=TextAccess.EDITABLE if editable else TextAccess.READ_ONLY,
        reason="Fixed allocation" if editable else "Mapped but writeback is unproved",
        outer_index=outer,
        chunk_index=0,
        owner_kind=owner_kind,
        owner_index=owner_index,
        field=field,
        reference_count=1,
        provider_kind="roster_player_text" if editable else None,
        provider_group_id=group if editable else None,
    )


def catalog_fixture() -> Nfl2k5TextCatalog:
    banks = (
        TextBank("bank.5", "ROST", "Current roster", 5, 0, False, "mixed", 4, ""),
        TextBank("bank.113", "ROST", "Historic 113", 113, 0, True, "mixed", 7, ""),
        TextBank("bank.114", "ROST", "Historic 114", 114, 0, True, "mixed", 7, ""),
        TextBank(
            "bank.strg", "STRG", "Menu messages", 300, 0, True,
            TextAccess.READ_ONLY.value, 1, "Pool ownership is unproved",
        ),
    )
    assets: list[TextAsset] = []
    teams: list[RosterTeam] = []
    players: list[RosterPlayer] = []
    numbers: list[RosterNumberAsset] = []
    for resource, city, nickname, first, last, jersey in (
        (113, "New York", "Giants", "Ada", "Lovelace", 12),
        (114, "Boston", "Minutemen", "Grace", "Hopper", 34),
    ):
        bank_id = f"bank.{resource}"
        team_group = f"team.{resource}"
        pairs: list[tuple[str, str]] = []
        for field, value in (
            ("city", city),
            ("nickname", nickname),
            ("abbreviation", nickname[:3].upper()),
            ("city_abbreviation", city[:3].upper()),
        ):
            asset_id = f"text.{resource}.team.{field}"
            assets.append(text_asset(
                asset_id, bank_id, value, outer=resource, owner_kind="team",
                owner_index=0, field=field, group=team_group,
            ))
            pairs.append((field, asset_id))
        teams.append(RosterTeam(
            team_group, resource, "historic", True, 0,
            f"{city} {nickname}", f"H{resource}", tuple(pairs), True,
            "Fixed-allocation identity fields",
        ))

        player_group = f"player.{resource}.0"
        first_id = f"text.{resource}.player.first"
        last_id = f"text.{resource}.player.last"
        number_id = f"number.{resource}.player"
        shield_id = f"face-shield.{resource}.player"
        assets.extend((
            text_asset(
                first_id, bank_id, first, outer=resource,
                owner_kind="primary_players", owner_index=0,
                field="first_name", group=player_group,
            ),
            text_asset(
                last_id, bank_id, last, outer=resource,
                owner_kind="primary_players", owner_index=0,
                field="last_name", group=player_group,
            ),
        ))
        numbers.append(RosterNumberAsset(
            number_id, f"Player {resource} jersey", jersey, 0, 99,
            TextAccess.EDITABLE, "Masked jersey field", resource, 0,
            player_group,
        ))
        numbers.append(RosterNumberAsset(
            shield_id, f"Player {resource} face shield", 0, 0, 2,
            TextAccess.EDITABLE,
            "Per-player type; not a HOME/AWAY tint", resource, 0,
            player_group, field="face_shield",
            choices=((0, "None"), (1, "Clear"), (2, "Dark")),
        ))
        players.append(RosterPlayer(
            player_group, resource, "historic", True, "primary_players", 0,
            f"{first} {last}", 5, resource - 100, first_id, last_id,
            number_id, True, "Primary historical player", shield_id,
        ))
    for pool, index, first, last, jersey, editable in (
        ("primary_players", 0, "Current", "Starter", 55, True),
        ("secondary_players", 0, "Reserve", "Player", 77, False),
    ):
        player_group = f"player.5.{pool}.{index}"
        first_id = f"text.5.{pool}.{index}.first"
        last_id = f"text.5.{pool}.{index}.last"
        number_id = f"number.5.{pool}.{index}"
        shield_id = f"face-shield.5.{pool}.{index}"
        assets.extend((
            text_asset(
                first_id, "bank.5", first, outer=5,
                owner_kind=pool, owner_index=index,
                field="first_name", group=player_group, editable=editable,
            ),
            text_asset(
                last_id, "bank.5", last, outer=5,
                owner_kind=pool, owner_index=index,
                field="last_name", group=player_group, editable=editable,
            ),
        ))
        numbers.append(RosterNumberAsset(
            number_id, f"Current {pool} jersey", jersey, 0, 99,
            TextAccess.EDITABLE, "Masked jersey field for either player pool",
            5, index, player_group,
        ))
        numbers.append(RosterNumberAsset(
            shield_id, f"Current {pool} face shield", 0, 0, 2,
            TextAccess.EDITABLE,
            "Per-player type; loaded saves can override the disc seed",
            5, index, player_group, field="face_shield",
            choices=((0, "None"), (1, "Clear"), (2, "Dark")),
        ))
        players.append(RosterPlayer(
            player_group, 5, "current", False, pool, index,
            f"{first} {last}", 3, index, first_id, last_id,
            number_id, editable,
            "Primary current player" if editable else "Secondary writer unproved",
            shield_id,
        ))
    assets.append(text_asset(
        "text.strg.welcome", "bank.strg", "Welcome", outer=300,
        owner_kind="strg_pool", owner_index=0, field="text", editable=False,
    ))
    return Nfl2k5TextCatalog(banks, assets, teams, players, numbers)


class FakeHost:
    def __init__(self, catalog: Nfl2k5TextCatalog) -> None:
        self.catalog = catalog
        self.text: dict[str, str] = {}
        self.numbers: dict[str, int] = {}

    def text_catalog_snapshot(self, progress) -> Nfl2k5TextCatalog:
        progress("Text ready", 1, 1)
        return self.catalog

    def text_value(self, asset_id: str) -> str:
        return self.text.get(asset_id, self.catalog.get_asset(asset_id).value)

    def number_value(self, asset_id: str) -> int:
        return self.numbers.get(
            asset_id, self.catalog.get_number_asset(asset_id).value
        )

    def replace_text(self, asset_id: str, value: str, progress) -> object:
        self.text[asset_id] = value
        progress("Text replacement ready", 1, 1)
        return None

    def replace_number(self, asset_id: str, value: int, progress) -> object:
        self.numbers[asset_id] = value
        progress("Jersey number ready", 1, 1)
        return None

    def revert_text(self, asset_id: str, progress) -> object:
        self.text.pop(asset_id, None)
        self.numbers.pop(asset_id, None)
        progress("Text reverted", 1, 1)
        return None

    # write_bytes mirrors the product writer (StudioFacade._publish_new_export
    # opens the export with O_BINARY and "wb"). write_text would translate "\n"
    # into "\r\n" on Windows, so the double would publish bytes the shipped
    # exporter never produces.
    def export_text(self, asset_id: str, destination: Path, progress) -> Path:
        destination.write_bytes((self.text_value(asset_id) + "\n").encode("utf-8"))
        progress("Text exported", 1, 1)
        return destination

    def export_number(self, asset_id: str, destination: Path, progress) -> Path:
        destination.write_bytes(
            (str(self.number_value(asset_id)) + "\n").encode("utf-8")
        )
        progress("Jersey number exported", 1, 1)
        return destination


class TextRosterPanelViewModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = catalog_fixture()
        self.host = FakeHost(self.catalog)

    def test_protocol_and_fixed_allocation_usage_are_headless(self) -> None:
        self.assertIsInstance(self.host, TextRosterPanelHost)
        asset = self.catalog.get_asset("text.113.player.first")
        self.assertTrue(text_usage(asset, "Al").valid)
        self.assertFalse(text_usage(asset, "").valid)
        self.assertFalse(text_usage(asset, "LongerThanAda").valid)
        self.assertEqual(text_usage(asset, "😀").used_utf16_units, 2)

    def test_product_summary_and_25th_note_explain_access_plainly(self) -> None:
        self.assertEqual(
            text_catalog_summary(self.catalog),
            "17 strings total · 14 Editable · 3 Preview/Export-only",
        )
        self.assertIn("ESPN 25th Anniversary", ESPN_25TH_COMING_SOON_NOTE)
        self.assertIn("Team selectors", ESPN_25TH_COMING_SOON_NOTE)
        self.assertIn("ownership is not proved", ESPN_25TH_COMING_SOON_NOTE)

    def test_universal_filter_searches_current_values_bank_and_status(self) -> None:
        changed = "text.113.team.nickname"
        self.host.text[changed] = "Comets"
        rows = filter_text_assets(
            self.catalog, TextFilter(query="comets", bank_id="bank.113"),
            self.host.text_value,
        )
        self.assertEqual([row.asset_id for row in rows], [changed])
        modified = filter_text_assets(
            self.catalog, TextFilter(status=STATUS_MODIFIED), self.host.text_value
        )
        self.assertEqual([row.asset_id for row in modified], [changed])
        read_only = filter_text_assets(
            self.catalog, TextFilter(status=STATUS_READ_ONLY), self.host.text_value
        )
        self.assertEqual(
            [row.asset_id for row in read_only],
            [
                "text.5.secondary_players.0.first",
                "text.5.secondary_players.0.last",
                "text.strg.welcome",
            ],
        )

    def test_filter_rejects_unknown_status_and_bank(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            filter_text_assets(self.catalog, TextFilter(status="unsafe"))
        with self.assertRaises(KeyError):
            filter_text_assets(self.catalog, TextFilter(bank_id="missing"))

    def test_historical_resources_and_search_cover_team_name_and_number(self) -> None:
        resources = historical_resources(self.catalog)
        self.assertEqual([row.outer_index for row in resources], [113, 114])
        self.assertEqual([len(row.players) for row in resources], [1, 1])
        self.host.text["text.114.player.first"] = "Amazing"
        self.host.numbers["number.114.player"] = 88
        by_name = filter_historical_players(
            self.catalog, resources, query="amazing boston",
            text_value=self.host.text_value, number_value=self.host.number_value,
        )
        self.assertEqual([row.player.group_id for row in by_name], ["player.114.0"])
        by_number = filter_historical_players(
            self.catalog, resources, query="88", outer_index=114,
            text_value=self.host.text_value, number_value=self.host.number_value,
        )
        self.assertEqual([row.player.group_id for row in by_number], ["player.114.0"])
        self.host.text["text.113.team.nickname"] = "Comets"
        by_current_team = filter_historical_players(
            self.catalog, resources, query="new york comets",
            text_value=self.host.text_value, number_value=self.host.number_value,
        )
        self.assertEqual(
            [row.player.group_id for row in by_current_team], ["player.113.0"]
        )

    def test_current_roster_search_status_and_read_only_coverage(self) -> None:
        rows = current_roster_players(self.catalog)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [row.player.pool for row in rows],
            ["primary_players", "secondary_players"],
        )
        self.host.text["text.5.primary_players.0.first"] = "Edited"
        self.host.numbers["number.5.primary_players.0"] = 88
        modified = filter_current_players(
            self.catalog, rows, query="edited 88 primary", status=STATUS_MODIFIED,
            text_value=self.host.text_value, number_value=self.host.number_value,
        )
        self.assertEqual(
            [row.player.group_id for row in modified],
            ["player.5.primary_players.0"],
        )
        read_only = filter_current_players(
            self.catalog, rows, status=STATUS_READ_ONLY,
            text_value=self.host.text_value, number_value=self.host.number_value,
        )
        self.assertEqual(read_only, ())
        editable = filter_current_players(
            self.catalog, rows, status=STATUS_EDITABLE,
            text_value=self.host.text_value, number_value=self.host.number_value,
        )
        self.assertEqual(
            [row.player.group_id for row in editable],
            ["player.5.secondary_players.0"],
        )

    def test_fixture_number_coverage_is_one_to_one_across_both_views(self) -> None:
        coverage = roster_number_coverage(self.catalog)
        self.assertEqual(coverage.total, 4)
        self.assertEqual(coverage.current, 2)
        self.assertEqual(coverage.historical, 2)
        self.assertEqual(coverage.editable, 4)
        self.assertEqual(coverage.current_editable, 2)
        self.assertEqual(coverage.historical_editable, 2)

    def test_exact_6522_number_scope_and_access_counts(self) -> None:
        players: list[RosterPlayer] = []
        numbers: list[RosterNumberAsset] = []
        for index in range(6522):
            historical = index < 3975
            current_index = index - 3975
            player_editable = historical or current_index < 2479
            pool = "primary_players" if player_editable else "secondary_players"
            outer = 100 + index // 53 if historical else 5
            group_id = f"synthetic.player.{index}"
            number_id = f"synthetic.number.{index}"
            players.append(RosterPlayer(
                group_id, outer, "historic" if historical else "current",
                historical, pool, index, f"Player {index}", 0, 0,
                f"first.{index}", f"last.{index}", number_id,
                player_editable, "Synthetic coverage row",
            ))
            numbers.append(RosterNumberAsset(
                number_id, f"Jersey {index}", index % 100, 0, 99,
                TextAccess.EDITABLE,
                "Synthetic coverage row", outer, index, group_id,
            ))
        catalog = Nfl2k5TextCatalog((), (), (), players, numbers)
        coverage = roster_number_coverage(catalog)
        self.assertEqual(
            coverage,
            type(coverage)(6522, 2547, 3975, 6522, 2547, 3975),
        )
        self.assertEqual(len(current_roster_players(catalog)), 2547)
        self.assertEqual(
            sum(len(resource.players) for resource in historical_resources(catalog)),
            3975,
        )

    def test_host_export_contract_writes_only_selected_current_text(self) -> None:
        self.host.text["text.113.player.first"] = "Al"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "name.txt"
            result = self.host.export_text(
                "text.113.player.first", destination, lambda *_args: None
            )
            self.assertEqual(result, destination)
            # read_bytes, not read_text: a text-mode read on Windows strips the
            # "\r" back out and would hide a CRLF-contaminated export.
            self.assertEqual(destination.read_bytes(), "Al\n".encode("utf-8"))

    def test_number_edit_export_and_revert_path_uses_staged_value(self) -> None:
        asset_id = "number.5.primary_players.0"
        self.host.replace_number(asset_id, 88, lambda *_args: None)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "number.txt"
            result = self.host.export_number(
                asset_id, destination, lambda *_args: None
            )
            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"88\n")
        self.host.revert_text(asset_id, lambda *_args: None)
        self.assertEqual(self.host.number_value(asset_id), 55)

    def test_secondary_number_project_reopens_with_pool_aware_provider_edit(self) -> None:
        asset_id = "number.5.secondary_players.0"
        edits = Nfl2k5TextEdits(self.catalog)
        edits.set_number(asset_id, 66)
        self.assertEqual(edits.provider_edits(), ({
            "kind": "roster_player_text",
            "resource_outer_index": 5,
            "player_pool": "secondary_players",
            "player_index": 0,
            "changes": {"jersey_number": 66},
        },))
        reopened = Nfl2k5TextEdits(self.catalog)
        reopened.load_replacement_document(edits.replacement_document())
        self.assertEqual(reopened.number(asset_id), 66)
        self.assertEqual(reopened.provider_edits(), edits.provider_edits())

    def test_face_shield_project_reopens_and_stays_per_player(self) -> None:
        asset_id = "face-shield.5.secondary_players.0"
        edits = Nfl2k5TextEdits(self.catalog)
        edits.set_number(asset_id, 2)
        self.assertEqual(edits.provider_edits(), ({
            "kind": "roster_player_text",
            "resource_outer_index": 5,
            "player_pool": "secondary_players",
            "player_index": 0,
            "changes": {"face_shield": 2},
        },))
        reopened = Nfl2k5TextEdits(self.catalog)
        reopened.load_replacement_document(edits.replacement_document())
        self.assertEqual(reopened.number(asset_id), 2)
        with self.assertRaisesRegex(ValidationError, "0 through 2"):
            reopened.set_number(asset_id, 3)


class TextRosterPanelOffscreenTests(unittest.TestCase):
    def test_scoped_views_put_text_and_rosters_in_their_own_workspaces(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        catalog = catalog_fixture()
        host = FakeHost(catalog)
        text_panel = TextRosterPanel(host, view="text")
        roster_panel = TextRosterPanel(host, view="rosters")
        application.processEvents()

        self.assertEqual(
            [text_panel.tabs.tabText(index) for index in range(text_panel.tabs.count())],
            ["All Text"],
        )
        self.assertEqual(
            [
                roster_panel.tabs.tabText(index)
                for index in range(roster_panel.tabs.count())
            ],
            ["Current Roster Players", "Historical Teams & Players"],
        )
        self.assertEqual(roster_panel.current_model.rowCount(), 2)
        self.assertEqual(roster_panel.historical_model.rowCount(), 2)
        self.assertFalse(hasattr(text_panel, "current_model"))
        self.assertFalse(hasattr(text_panel, "historical_model"))
        self.assertFalse(hasattr(roster_panel, "text_model"))

        text_panel.status_filter.setCurrentIndex(
            text_panel.status_filter.findData(STATUS_EDITABLE)
        )
        text_panel.text_table.selectRow(0)
        application.processEvents()
        self.assertIsNotNone(text_panel.selected_asset)
        selected_asset = text_panel.selected_asset
        assert selected_asset is not None
        text_panel.current_text.setPlainText("X")
        text_panel._apply_selected_text()
        self.assertEqual(host.text_value(selected_asset.asset_id), "X")

        roster_panel.current_table.selectRow(0)
        application.processEvents()
        roster_panel.current_number.setText("88")
        roster_panel.current_face_shield.setCurrentIndex(
            roster_panel.current_face_shield.findData(2)
        )
        roster_panel._apply_current_player()
        self.assertEqual(host.number_value("number.5.primary_players.0"), 88)
        self.assertEqual(host.number_value("face-shield.5.primary_players.0"), 2)

        text_panel.deleteLater()
        roster_panel.deleteLater()
        application.processEvents()

    def test_complete_current_and_historical_views_are_clickable_headlessly(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

        application = QApplication.instance() or QApplication([])
        catalog = catalog_fixture()
        host = FakeHost(catalog)
        statuses: list[str] = []
        panel = TextRosterPanel(host, on_status=statuses.append)
        application.processEvents()

        coverage = roster_number_coverage(catalog)
        expected_status = (
            f"Text & rosters ready • {len(catalog.assets):,} strings • "
            f"{coverage.total:,} jersey numbers"
        )
        self.assertEqual(panel.status_label.text(), expected_status)
        self.assertEqual(statuses[-1], expected_status)
        self.assertIn("across 4 banks", panel.status_label.toolTip())
        self.assertIn("current and", panel.status_label.toolTip())

        self.assertEqual(
            [panel.tabs.tabText(index) for index in range(panel.tabs.count())],
            [
                "All Text",
                "Current Roster Players",
                "Historical Teams & Players",
            ],
        )
        self.assertEqual(panel.current_model.rowCount(), 2)
        self.assertEqual(panel.historical_model.rowCount(), 2)

        panel.current_table.selectRow(0)
        application.processEvents()
        # Never silent-gray: Apply stays clickable; disableReason teaches "no change".
        self.assertTrue(panel.apply_current_button.isEnabled())
        self.assertTrue(
            str(panel.apply_current_button.property("disableReason") or "").strip()
        )
        self.assertTrue(panel.export_current_number_button.isEnabled())
        self.assertEqual(panel.current_face_shield.currentText(), "None")
        self.assertIn("not a HOME/AWAY tint", panel.current_note.text())
        panel.current_number.setText("88")
        panel.current_face_shield.setCurrentIndex(
            panel.current_face_shield.findData(1)
        )
        self.assertTrue(panel.apply_current_button.isEnabled())
        self.assertFalse(
            str(panel.apply_current_button.property("disableReason") or "").strip()
        )
        panel._apply_current_player()
        self.assertEqual(host.number_value("number.5.primary_players.0"), 88)
        self.assertEqual(host.number_value("face-shield.5.primary_players.0"), 1)

        panel.current_table.selectRow(1)
        application.processEvents()
        self.assertFalse(panel.current_first.isEnabled())
        self.assertFalse(panel.current_last.isEnabled())
        self.assertTrue(panel.current_number.isEnabled())
        self.assertTrue(panel.current_face_shield.isEnabled())
        self.assertTrue(panel.apply_current_button.isEnabled())
        self.assertTrue(
            str(panel.apply_current_button.property("disableReason") or "").strip()
        )
        self.assertTrue(panel.export_current_number_button.isEnabled())
        panel.current_number.setText("66")
        panel.current_face_shield.setCurrentIndex(
            panel.current_face_shield.findData(2)
        )
        self.assertTrue(panel.apply_current_button.isEnabled())
        self.assertFalse(
            str(panel.apply_current_button.property("disableReason") or "").strip()
        )
        panel._apply_current_player()
        self.assertEqual(
            host.number_value("number.5.secondary_players.0"), 66
        )
        self.assertEqual(
            host.number_value("face-shield.5.secondary_players.0"), 2
        )

        panel.historical_table.selectRow(0)
        application.processEvents()
        self.assertTrue(panel.export_historical_number_button.isEnabled())
        self.assertEqual(panel.player_face_shield.currentText(), "None")
        panel.deleteLater()
        application.processEvents()


if __name__ == "__main__":
    unittest.main()

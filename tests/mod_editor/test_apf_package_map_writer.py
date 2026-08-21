"""Who-lines-up package-map writer: bytes only, no 3rd-and-long claim."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest

from mod_editor.core.apf2k8_package_map_writer import (
    APF_FORMATION_BASE,
    APF_FORMATION_COUNT_OFFSET,
    APF_FORMATION_SIZE,
    APF_MASTER_BODY_SIZE,
    APF_PACKAGE_MAP_OFFSET_IN_FORMATION,
    APF_PACKAGE_MAP_ROLE_TE,
    APF_PACKAGE_MAP_ROLE_WR3,
    HONESTY,
    PackageMapChange,
    change_from_mapping,
    compile_master_play_edits,
    compile_master_play_edits_detailed,
    compile_package_maps,
    decode_package_map_payload,
    encode_package_map_payload,
    list_apf_formations,
    put_role_in_slot,
    read_apf_formation_package_map,
    role_label,
    slot_summary,
    swap_map_slots,
    swap_te_and_wr,
)
from mod_editor.core.errors import ValidationError

IDENTITY_MAP = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
ACE_MAP = (0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7)


def _synthetic_apf_master() -> bytes:
    body = bytearray(APF_MASTER_BODY_SIZE)
    struct.pack_into(">I", body, APF_FORMATION_COUNT_OFFSET, 3)
    names = ("Ace", "Ace Empty", "I Spread")
    maps = (
        (0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7),
        (0, 10, 8, 9, 1, 4, 3, 5, 2, 7, 6),
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
    )
    pool = 0x22384
    for index, (name, package_map) in enumerate(zip(names, maps, strict=True)):
        record = APF_FORMATION_BASE + index * APF_FORMATION_SIZE
        encoded = name.encode("utf-16be") + b"\0\0"
        body[pool : pool + len(encoded)] = encoded
        struct.pack_into(">i", body, record, (pool - record) + 1)
        offset = record + APF_PACKAGE_MAP_OFFSET_IN_FORMATION
        body[offset : offset + 11] = bytes(package_map)
        pool += len(encoded)
    return bytes(body)


class PackageMapWriterTests(unittest.TestCase):
    def test_swap_te_and_wr_exchanges_roles_only(self) -> None:
        source = (0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7)
        swapped = swap_te_and_wr(source)
        self.assertEqual(swapped[2], APF_PACKAGE_MAP_ROLE_WR3)
        self.assertEqual(swapped[3], APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(
            [value for index, value in enumerate(swapped) if index not in {2, 3}],
            [value for index, value in enumerate(source) if index not in {2, 3}],
        )

    def test_put_te_in_wr_slot_is_a_slot_swap(self) -> None:
        source = (0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7)
        updated = put_role_in_slot(source, 3, APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(updated, swap_map_slots(source, 2, 3))

    def test_compile_touches_only_named_maps(self) -> None:
        body = _synthetic_apf_master()
        ace = read_apf_formation_package_map(body, 0)
        change = PackageMapChange(0, swap_te_and_wr(ace))
        patched = compile_package_maps(body, (change,))
        self.assertEqual(read_apf_formation_package_map(patched, 0), change.new_map)
        self.assertEqual(
            read_apf_formation_package_map(patched, 1),
            read_apf_formation_package_map(body, 1),
        )
        self.assertEqual(
            read_apf_formation_package_map(patched, 2),
            read_apf_formation_package_map(body, 2),
        )
        changed = sum(1 for left, right in zip(body, patched, strict=True) if left != right)
        self.assertEqual(changed, 2)

    def test_payload_round_trip(self) -> None:
        change = PackageMapChange(2, (10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0))
        raw = encode_package_map_payload(change)
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(payload["schema"], "apf2k8_formation_package_map_replacement/v1")
        self.assertEqual(decode_package_map_payload(raw, change.selector), change)

    def test_rejects_non_permutation(self) -> None:
        with self.assertRaises(ValidationError):
            PackageMapChange(0, (8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8))

    def test_honesty_does_not_claim_third_and_long(self) -> None:
        self.assertIn("does not change which formation the CPU picks", HONESTY)
        self.assertNotIn("3rd-and-long fix", HONESTY.casefold())
        self.assertIn("TE", role_label(8))
        self.assertIn("WR", role_label(9))
        self.assertIn("role 3", role_label(3))
        self.assertIn("TE is stored in map slot 3", slot_summary((0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7)))

    def test_list_formations_reads_names(self) -> None:
        rows = list_apf_formations(_synthetic_apf_master())
        self.assertEqual([name for _index, name, _map in rows], ["Ace", "Ace Empty", "I Spread"])


class SessionPackageMapTests(unittest.TestCase):
    def test_session_stages_and_reverts_a_map(self) -> None:
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch

        from mod_editor.apf_studio.models import ApfSource
        from mod_editor.apf_studio.session import ApfSession

        body = _synthetic_apf_master()
        ace = read_apf_formation_package_map(body, 0)
        change = PackageMapChange(0, swap_te_and_wr(ace))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = ApfSource(
                selected_path=root / "0A",
                game_root=root,
                index_0a=root / "0A",
                source_sha256="a" * 64,
                source_size=1,
                xex_sha256="b" * 64,
                display_name="Synthetic APF",
            )
            session = ApfSession(source, SimpleNamespace(), cache_root=root / "cache")
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                count = session.apply_package_map_batch((change,))
                self.assertEqual(count, 1)
                staged = session.staged_package_maps()
                self.assertEqual(len(staged), 1)
                self.assertEqual(staged[0].new_map, change.new_map)
                self.assertTrue(session.revert(change.selector))
                self.assertEqual(session.staged_package_maps(), ())


class PackageMapUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_panel_explains_the_boundary_without_hex_essays(self) -> None:
        from unittest.mock import MagicMock

        from PyQt5.QtWidgets import QLabel

        from mod_editor.apf_studio.playbook_package_map_qt import ApfPackageMapPanel

        facade = MagicMock()
        facade.source_ready = False
        facade.source = None
        panel = ApfPackageMapPanel(facade, lambda *_a, **_k: None)
        try:
            titles = [
                widget.text()
                for widget in panel.findChildren(QLabel)
                if widget.objectName() == "panelTitle"
            ]
            self.assertEqual(titles, ["Who lines up"])
            self.assertIn("does not change which formation", HONESTY)
            self.assertNotIn("0x84", HONESTY)
        finally:
            panel.deleteLater()
            self.app.processEvents()


class StrictPayloadTests(unittest.TestCase):
    def test_change_from_mapping_rejects_malformed_formation_index(self) -> None:
        for bad in ("abc", None, 1.5, True, [0]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    change_from_mapping(
                        {"formation_index": bad, "new_map": list(IDENTITY_MAP)}
                    )

    def test_change_from_mapping_rejects_missing_or_wrong_map(self) -> None:
        with self.assertRaises(ValidationError):
            change_from_mapping({"formation_index": 0, "new_map": None})
        with self.assertRaises(ValidationError):
            change_from_mapping({"formation_index": 0, "new_map": {"a": 1}})
        with self.assertRaises(ValidationError):
            change_from_mapping({"formation_index": 0})
        with self.assertRaises(ValidationError):
            change_from_mapping(
                {"formation_index": 0, "new_map": ["0", 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
            )

    def test_change_rejects_boolean_and_float_roles(self) -> None:
        with self.assertRaises(ValidationError):
            PackageMapChange(0, (True, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10))
        with self.assertRaises(ValidationError):
            PackageMapChange(0, (0.0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10))

    def test_decode_payload_rejects_corruption_with_validation_errors(self) -> None:
        change = PackageMapChange(2, IDENTITY_MAP)
        selector = change.selector
        with self.assertRaises(ValidationError):
            decode_package_map_payload(b"not json{", selector)
        missing = json.loads(encode_package_map_payload(change).decode("utf-8"))
        del missing["new_map"]
        with self.assertRaises(ValidationError):
            decode_package_map_payload(
                json.dumps(missing).encode("utf-8"), selector
            )
        duplicated = encode_package_map_payload(change).decode("utf-8").replace(
            '"formation_index": 2,', '"formation_index": 2, "formation_index": 2,'
        )
        with self.assertRaises(ValidationError):
            decode_package_map_payload(duplicated.encode("utf-8"), selector)
        string_index = json.loads(encode_package_map_payload(change).decode("utf-8"))
        string_index["formation_index"] = "2"
        with self.assertRaises(ValidationError):
            decode_package_map_payload(
                json.dumps(string_index).encode("utf-8"), selector
            )

    def test_decode_payload_rejects_deeply_nested_json(self) -> None:
        # A recursion bomb must fail closed with a ValidationError, not a bare
        # RecursionError that escapes every caller's except-clause.
        deep = b"[" * 100_000 + b"]" * 100_000
        with self.assertRaises(ValidationError):
            decode_package_map_payload(deep, "apf:pkgmap:any:f0")


class NoOpCompileGuardTests(unittest.TestCase):
    def test_compile_package_maps_rejects_a_batch_that_changes_nothing(self) -> None:
        body = _synthetic_apf_master()
        same = PackageMapChange(1, read_apf_formation_package_map(body, 1))
        with self.assertRaises(ValidationError):
            compile_package_maps(body, (same,))
        with self.assertRaises(ValidationError):
            compile_master_play_edits(body, package_maps=(same,))

    def test_detailed_compile_reports_only_effective_maps_and_ranges(self) -> None:
        body = _synthetic_apf_master()
        same = PackageMapChange(1, read_apf_formation_package_map(body, 1))
        effective = PackageMapChange(0, swap_te_and_wr(ACE_MAP))
        patched, ranges, effective_maps = compile_master_play_edits_detailed(
            body, package_maps=(same, effective)
        )
        self.assertEqual(effective_maps, (effective,))
        expected_offset = APF_FORMATION_BASE + APF_PACKAGE_MAP_OFFSET_IN_FORMATION
        self.assertEqual(list(ranges), [(expected_offset, expected_offset + 11)])
        self.assertEqual(
            read_apf_formation_package_map(patched, 0), effective.new_map
        )
        self.assertEqual(
            read_apf_formation_package_map(patched, 1),
            read_apf_formation_package_map(body, 1),
        )

    def test_empty_master_play_selection_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            compile_master_play_edits(_synthetic_apf_master())

    def test_duplicate_formation_caught_even_when_one_entry_is_a_noop(self) -> None:
        # The no-op pre-filter must not hide a repeated formation index.
        body = _synthetic_apf_master()
        stock = read_apf_formation_package_map(body, 1)
        changed = swap_te_and_wr(ACE_MAP)
        same = PackageMapChange(1, stock)
        other = PackageMapChange(1, changed)
        with self.assertRaises(ValidationError):
            compile_master_play_edits(body, package_maps=(same, other))
        with self.assertRaises(ValidationError):
            compile_master_play_edits(body, package_maps=(other, same))


def _make_session_fixture(temporary: str, cache_name: str = "cache"):
    from pathlib import Path
    from types import SimpleNamespace

    from mod_editor.apf_studio.models import ApfSource
    from mod_editor.apf_studio.session import ApfSession

    root = Path(temporary)
    source = ApfSource(
        selected_path=root / "0A",
        game_root=root,
        index_0a=root / "0A",
        source_sha256="a" * 64,
        source_size=1,
        xex_sha256="b" * 64,
        display_name="Synthetic APF",
    )
    session = ApfSession(source, SimpleNamespace(), cache_root=root / cache_name)
    return root, session


class SessionBatchSemanticsTests(unittest.TestCase):
    def test_batch_replaces_the_entire_staged_set(self) -> None:
        from unittest.mock import patch

        from mod_editor.apf_studio.session import SessionError

        body = _synthetic_apf_master()
        change_a = PackageMapChange(0, swap_te_and_wr(ACE_MAP))
        change_b = PackageMapChange(2, IDENTITY_MAP[::-1])
        change_c = PackageMapChange(1, swap_te_and_wr(ACE_MAP))
        with tempfile.TemporaryDirectory() as temporary:
            _root, session = _make_session_fixture(temporary)
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                session.apply_package_map_batch((change_a, change_b))
                self.assertEqual(
                    [item.formation_index for item in session.staged_package_maps()],
                    [0, 2],
                )
                session.apply_package_map_batch((change_c,))
                self.assertEqual(
                    [item.formation_index for item in session.staged_package_maps()],
                    [1],
                )
                with self.assertRaises(SessionError):
                    session.apply_package_map_batch((change_c, change_c))
                with self.assertRaises(SessionError):
                    session.apply_package_map_batch(
                        (
                            PackageMapChange(
                                1, read_apf_formation_package_map(body, 1)
                            ),
                        )
                    )

    def test_empty_batch_clears_staged_maps_and_is_undoable(self) -> None:
        from unittest.mock import patch

        body = _synthetic_apf_master()
        change_a = PackageMapChange(0, swap_te_and_wr(ACE_MAP))
        with tempfile.TemporaryDirectory() as temporary:
            _root, session = _make_session_fixture(temporary)
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                self.assertEqual(session.apply_package_map_batch((change_a,)), 1)
                removed = session.apply_package_map_batch(())
                self.assertEqual(removed, 1)
                self.assertEqual(session.staged_package_maps(), ())
                self.assertTrue(session.undo())
                self.assertEqual(
                    [item.new_map for item in session.staged_package_maps()],
                    [change_a.new_map],
                )

    def test_project_round_trip_keeps_only_logical_bytes(self) -> None:
        from unittest.mock import patch

        from mod_editor.apf_studio.project import load_project

        body = _synthetic_apf_master()
        change = PackageMapChange(0, swap_te_and_wr(ACE_MAP))
        with tempfile.TemporaryDirectory() as temporary:
            root, session = _make_session_fixture(temporary)
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                session.apply_package_map_batch((change,))
                project_path = root / "who-lines-up.apf2k8mod"
                session.save_project(project_path)
            _manifest, loaded, _annotations = load_project(
                project_path,
                expected_source_sha256="a" * 64,
                destination_dir=root / "unpacked",
            )
            self.assertEqual(len(loaded), 1)
            item = loaded[0]
            self.assertEqual(item.replacement_path.suffix, ".json")
            self.assertEqual(
                decode_package_map_payload(
                    item.replacement_path.read_bytes(), item.asset_id
                ),
                change,
            )
            self.assertNotIn(
                bytes(ACE_MAP), item.replacement_path.read_bytes()
            )
            with patch(
                "mod_editor.apf_studio.session.read_master_play_body",
                return_value=body,
            ):
                _imported_root, imported = _make_session_fixture(
                    temporary, cache_name="cache-import"
                )
                self.assertEqual(imported.load_project(project_path), 1)
                self.assertEqual(
                    [item.new_map for item in imported.staged_package_maps()],
                    [change.new_map],
                )


class PackagingTests(unittest.TestCase):
    def test_allowlist_ships_the_writer_and_panel(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        lines = {
            line.strip()
            for line in (root / "packaging/apf2k8-release-allowlist.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertTrue(
            {
                "mod_editor/core/apf2k8_package_map_writer.py",
                "mod_editor/apf_studio/playbook_package_map_qt.py",
            }
            <= lines
        )


class _FakePackageMapFacade:
    def __init__(self, source_path) -> None:
        from types import SimpleNamespace

        self.source_ready = True
        self.source = SimpleNamespace(index_0a=source_path)
        self._staged: list[PackageMapChange] = []
        self.apply_calls: list[tuple[PackageMapChange, ...]] = []
        self._broken_reads = False

    def staged_package_maps(self):
        if self._broken_reads:
            raise RuntimeError("staged payload cache is corrupt")
        return tuple(self._staged)

    def apply_package_maps(self, changes, progress=None):
        changes = tuple(changes)
        self.apply_calls.append(changes)
        self._staged = list(changes)
        return len(changes)


class PackageMapPanelActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _make_panel(self, facade):
        from unittest.mock import patch

        from mod_editor.apf_studio.playbook_package_map_qt import (
            ApfPackageMapPanel,
        )

        def run_sync(label, work, done, *args, **kwargs):
            done(work(None))

        patcher = patch(
            "mod_editor.apf_studio.playbook_package_map_qt.read_master_play_body",
            return_value=_synthetic_apf_master(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        panel = ApfPackageMapPanel(facade, run_sync)
        self.addCleanup(panel.deleteLater)
        panel.set_context()
        return panel

    def test_put_swap_and_copy_actions_edit_the_draft(self) -> None:
        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade)
        expected_put = put_role_in_slot(ACE_MAP, 3, APF_PACKAGE_MAP_ROLE_TE)
        panel.table.setCurrentCell(3, 0)
        panel._put_role(APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(panel._draft.get(0), expected_put)
        panel._swap_te_wr()
        # Swapping again restores the stock map, so the draft entry drops out.
        self.assertEqual(panel._current_map(0), ACE_MAP)
        self.assertNotIn(0, panel._draft)
        panel.copy_from.setCurrentIndex(2)
        panel._copy_from()
        self.assertEqual(panel._draft.get(0), IDENTITY_MAP)
        panel._stage()
        self.assertEqual(len(facade.apply_calls), 1)
        staged = facade.apply_calls[-1]
        self.assertEqual([change.formation_index for change in staged], [0])
        self.assertEqual(staged[0].new_map, IDENTITY_MAP)
        self.assertNotIn(
            bytes(ACE_MAP),
            encode_package_map_payload(staged[0]),
        )

    def test_table_cells_use_readable_colors(self) -> None:
        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade)
        self.assertGreater(panel.table.rowCount(), 0)
        for column in range(3):
            item = panel.table.item(0, column)
            self.assertIsNotNone(item)
            self.assertEqual(item.foreground().color().name(), "#dce8f5")
            self.assertEqual(item.background().color().name(), "#0c1421")

    def test_stage_with_an_empty_draft_stages_nothing(self) -> None:
        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade)
        panel._stage()
        self.assertEqual(facade.apply_calls, [])
        self.assertIn("Nothing to stage yet", panel.status.text())

    def test_revert_all_asks_first_and_clears_every_map(self) -> None:
        from unittest.mock import patch

        from PyQt5.QtWidgets import QMessageBox

        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade)
        panel.table.setCurrentCell(3, 0)
        panel._put_role(APF_PACKAGE_MAP_ROLE_TE)
        panel._stage()
        self.assertEqual(len(facade.apply_calls), 1)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.No
        ):
            panel._revert_all()
        self.assertEqual(len(facade.apply_calls), 1)
        self.assertEqual(len(facade.staged_package_maps()), 1)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.Yes
        ):
            panel._revert_all()
        self.assertEqual(len(facade.apply_calls), 2)
        self.assertEqual(facade.apply_calls[-1], ())
        self.assertEqual(facade.staged_package_maps(), ())

    def test_broken_staged_reads_lock_commit_paths_without_wiping_draft(self) -> None:
        from unittest.mock import patch

        from PyQt5.QtWidgets import QMessageBox

        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade)
        panel.table.setCurrentCell(3, 0)
        panel._put_role(APF_PACKAGE_MAP_ROLE_TE)
        panel._stage()
        self.assertEqual(len(facade.apply_calls), 1)
        kept_draft = dict(panel._draft)
        facade._broken_reads = True
        panel.set_context()
        self.assertFalse(panel.stage_button.isEnabled())
        self.assertFalse(panel.revert_button.isEnabled())
        self.assertFalse(panel.revert_all_button.isEnabled())
        self.assertIn("Could not read the staged who-lines-up edits", panel.status.text())
        self.assertEqual(panel._draft, kept_draft)
        with patch.object(QMessageBox, "information"):
            panel._stage()
            panel._revert_all()
            panel._revert_one()
        self.assertEqual(len(facade.apply_calls), 1)


if __name__ == "__main__":
    unittest.main()

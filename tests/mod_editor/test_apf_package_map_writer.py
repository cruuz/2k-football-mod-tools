"""Who-lines-up package-map writer: bytes only, no 3rd-and-long claim."""

from __future__ import annotations

import json
import os
from pathlib import Path
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

WORKSPACE = Path(__file__).resolve().parents[2]
EXTRACTED_0A = WORKSPACE / "extracted" / "All-Pro Football 2K8 (USA)" / "0A"
STORAGE_0A = Path(
    "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"
)
_ENV_0A = os.environ.get("APF_2K8_0A")
GAME_0A = Path(_ENV_0A) if _ENV_0A else (
    EXTRACTED_0A if EXTRACTED_0A.is_file() else STORAGE_0A
)
DISC_AVAILABLE = GAME_0A.is_file()

# The five ids that move together through every offensive formation.
OL_BLOCK = (1, 4, 3, 5, 2)


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
        self.assertIn(
            "role 8 (TE) is at map position 3",
            slot_summary((0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7)),
        )

    def test_summary_does_not_call_a_map_position_a_field_slot(self) -> None:
        """A football reader took "map slot 2 = TE" as "the TE lines up
        second". The five ids that behave like the line never sit at map
        positions 2..6, so the copy must not invite that reading."""

        summary = slot_summary((0, 10, 8, 9, 1, 4, 3, 5, 2, 6, 7))
        self.assertIn("map position", summary)
        self.assertNotIn("map slot", summary)
        self.assertIn("not the play's route slots", summary)
        folded = HONESTY.casefold()
        self.assertIn("once each", folded)
        self.assertIn("default.xex", folded)
        self.assertNotIn("runtime proved", folded)

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
        applied = len(facade.apply_calls)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.No
        ):
            panel._revert_all()
        self.assertEqual(len(facade.apply_calls), applied)
        self.assertEqual(len(facade.staged_package_maps()), 1)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.Yes
        ):
            panel._revert_all()
        self.assertEqual(len(facade.apply_calls), applied + 1)
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
        applied = len(facade.apply_calls)
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
        self.assertEqual(len(facade.apply_calls), applied)


class UnstagedDraftRegressionTests(unittest.TestCase):
    """Urianus, 2026-08-24: "Who Lines Up always says 'applied 0 edits'".

    The panel marked a formation edited, the status line said "ready to stage
    or already staged", and Build -- which only ever reads the session -- wrote
    a plain copy and reported nothing applied."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def _make_panel(self, facade, run_task=None):
        from unittest.mock import patch

        from mod_editor.apf_studio.playbook_package_map_qt import (
            ApfPackageMapPanel,
        )

        def run_sync(label, work, done, *args, **kwargs):
            done(work(None))
            return True

        patcher = patch(
            "mod_editor.apf_studio.playbook_package_map_qt.read_master_play_body",
            return_value=_synthetic_apf_master(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        panel = ApfPackageMapPanel(facade, run_task or run_sync)
        self.addCleanup(panel.deleteLater)
        panel.set_context()
        return panel

    def test_editing_a_map_reaches_the_session_without_a_stage_click(self) -> None:
        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade)
        panel.table.setCurrentCell(3, 0)
        panel._put_role(APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(len(facade.apply_calls), 1)
        self.assertEqual(
            [change.formation_index for change in facade.staged_package_maps()], [0]
        )
        self.assertEqual(panel.unstaged_maps(), ())

    def test_status_never_conflates_staged_with_merely_drafted(self) -> None:
        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade)
        panel.table.setCurrentCell(3, 0)
        panel._put_role(APF_PACKAGE_MAP_ROLE_TE)
        self.assertIn("staged", panel.status.text())
        self.assertNotIn("ready to stage or already staged", panel.status.text())

    def test_a_refused_stage_keeps_the_draft_and_says_it_is_not_staged(self) -> None:
        """The window refuses a second blocking task and returns False. The
        panel used to drop that click silently."""

        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade, run_task=lambda *_a, **_k: False)
        panel.table.setCurrentCell(3, 0)
        panel._put_role(APF_PACKAGE_MAP_ROLE_TE)
        self.assertEqual(facade.apply_calls, [])
        self.assertIn(0, panel._draft)
        self.assertEqual(panel.unstaged_maps(), (0,))
        self.assertIn("NOT staged", panel.status.text())

    def test_a_plain_refresh_does_not_discard_an_unstaged_map(self) -> None:
        facade = _FakePackageMapFacade("synthetic-0A")
        panel = self._make_panel(facade, run_task=lambda *_a, **_k: False)
        panel.table.setCurrentCell(3, 0)
        panel._put_role(APF_PACKAGE_MAP_ROLE_TE)
        kept = dict(panel._draft)
        panel.refresh()
        self.assertEqual(panel._draft, kept)
        self.assertEqual(panel.unstaged_maps(), (0,))

    def test_build_refuses_while_a_who_lines_up_map_is_unstaged(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        from mod_editor.apf_studio import gui as apf_gui
        from mod_editor.apf_studio.models import ApfCategory

        window = SimpleNamespace(
            facade=SimpleNamespace(source_ready=True),
            _unstaged_who_lines_up=lambda: apf_gui.ApfStudioMainWindow.
            _unstaged_who_lines_up(window),
            _pages={
                ApfCategory.PLAYBOOKS: SimpleNamespace(
                    playbook_package_maps=SimpleNamespace(
                        unstaged_maps=lambda: (0, 4)
                    )
                )
            },
        )
        shown: list[tuple[str, str]] = []
        with patch.object(
            apf_gui.QMessageBox,
            "information",
            staticmethod(lambda _p, title, text, *a, **k: shown.append((title, text))),
        ), patch.object(
            apf_gui.QFileDialog,
            "getExistingDirectory",
            staticmethod(lambda *a, **k: self.fail("Build must not start")),
        ):
            apf_gui.ApfStudioMainWindow._build_game(window)
        self.assertEqual(len(shown), 1)
        self.assertIn("not staged", shown[0][1])
        self.assertIn("Stage this map", shown[0][1])

    def test_zero_edit_build_message_explains_itself(self) -> None:
        from types import SimpleNamespace

        from mod_editor.apf_studio.gui import ApfStudioMainWindow

        empty = SimpleNamespace(modified_assets=(), manifest="/nonexistent")
        text = ApfStudioMainWindow._build_edit_detail(empty)
        self.assertIn("Applied 0 edits", text)
        self.assertIn("nothing was staged", text)
        self.assertIn("plain copy", text)

    def test_build_message_reports_the_changed_regions(self) -> None:
        import json as _json
        from pathlib import Path as _Path
        from types import SimpleNamespace

        from mod_editor.apf_studio.gui import ApfStudioMainWindow

        with tempfile.TemporaryDirectory() as temporary:
            manifest = _Path(temporary) / "manifest.json"
            manifest.write_text(
                _json.dumps(
                    {
                        "edits": [
                            {
                                "kind": "formation_package_map_batch",
                                "changed_byte_count": 2,
                                "changed_ranges": [[597, 608]],
                                "package_maps": [{"formation_index": 0}],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            receipt = SimpleNamespace(
                modified_assets=("apf:pkgmap:apf:playbook:180:0:f0",),
                manifest=manifest,
            )
            text = ApfStudioMainWindow._build_edit_detail(receipt)
        self.assertIn("Applied 1 edit.", text)
        self.assertIn("1 who-lines-up formation map written", text)
        self.assertIn("1 byte region changed (2 bytes)", text)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class RetailVocabularyTests(unittest.TestCase):
    """What the eleven bytes are, read off the user's own game.

    Urianus, 2026-08-25: "the WRs/TEs are 100% NOT on slots 2-6 (OL on every
    play I've edited in Assignment Routes) ... QB in slot 1 and OL in 2-6 ...
    are set in stone". He is right about the play's route slots, and these
    tests pin why that does not describe this map."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.apf2k8_playbook_route_writer import (
            read_master_play_body,
        )

        cls.body = read_master_play_body(GAME_0A)
        cls.rows = list_apf_formations(cls.body)

    def test_every_retail_formation_map_is_a_permutation_of_0_to_10(self) -> None:
        """So a byte cannot be a headcount: no set can hold two receivers."""

        self.assertEqual(len(self.rows), 163)
        for index, name, package_map in self.rows:
            self.assertEqual(
                sorted(package_map), list(range(11)), f"{index} {name}"
            )

    def test_defences_and_special_teams_carry_the_same_eleven_numbers(self) -> None:
        """A legend that reads 8 as TE and 9 as WR puts both in a 4-3."""

        named = {name: package_map for _index, name, package_map in self.rows}
        for name in ("4-3", "Nickel", "Dime", "3-4", "Prevent", "Kickoff", "Punt"):
            self.assertIn(name, named)
            self.assertIn(APF_PACKAGE_MAP_ROLE_TE, named[name], name)
            self.assertIn(APF_PACKAGE_MAP_ROLE_WR3, named[name], name)

    def test_the_line_block_never_sits_at_map_positions_two_to_six(self) -> None:
        """The play's slots 2..6 are the offensive line on every play. The
        five ids that travel as a block here start at map position 3, 4, 5 or
        6 (1-based) depending on the formation, never at 2, so the block never
        fills positions 2..6. Map position is not the play's route slot."""

        starts: dict[int, int] = {}
        for index, name, package_map in self.rows[:141]:
            found = [
                start
                for start in range(len(package_map) - 4)
                if tuple(package_map[start : start + 5]) == OL_BLOCK
            ]
            self.assertEqual(len(found), 1, f"{index} {name} {list(package_map)}")
            starts[found[0]] = starts.get(found[0], 0) + 1
        self.assertNotIn(1, starts)
        self.assertEqual(sum(starts.values()), 141)
        # Zero-based starts. 1 would be the only one that puts the block on
        # map positions 2..6, and no retail formation does that.
        self.assertEqual(sorted(starts), [2, 3, 4, 5])

    def test_pinned_maps_still_match_the_disc(self) -> None:
        named = {name: package_map for _index, name, package_map in self.rows}
        self.assertEqual(named["I Pro"], (0, 9, 10, 8, 1, 4, 3, 5, 2, 6, 7))
        self.assertEqual(named["Ace"], ACE_MAP)
        self.assertEqual(named["Ace Empty"], (0, 10, 8, 9, 1, 4, 3, 5, 2, 7, 6))
        self.assertEqual(named["4-3"], (0, 2, 3, 1, 4, 5, 6, 9, 7, 8, 10))


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class RetailBuildRegionTests(unittest.TestCase):
    """A staged map changes exactly its own eleven-byte region in outer 180."""

    def test_one_edit_changes_only_that_formations_region(self) -> None:
        from mod_editor.core.apf2k8_package_map_writer import (
            apf_formation_package_map_offset,
            build_master_play_edits,
            compile_master_play_edits,
        )
        from mod_editor.core.apf2k8_playbook_route_writer import (
            read_master_play_body,
        )

        original = read_master_play_body(GAME_0A)
        stock = read_apf_formation_package_map(original, 0)
        change = PackageMapChange(0, put_role_in_slot(stock, 0, APF_PACKAGE_MAP_ROLE_WR3))
        built = compile_master_play_edits(original, package_maps=(change,))
        offset = apf_formation_package_map_offset(0)
        self.assertEqual(
            offset,
            APF_FORMATION_BASE + 0 * APF_FORMATION_SIZE
            + APF_PACKAGE_MAP_OFFSET_IN_FORMATION,
        )
        self.assertEqual(offset, 0x0255)
        differing = [
            index
            for index, (left, right) in enumerate(zip(original, built, strict=True))
            if left != right
        ]
        self.assertTrue(differing)
        self.assertTrue(
            all(offset <= index < offset + 11 for index in differing), differing
        )
        self.assertEqual(read_apf_formation_package_map(built, 0), change.new_map)

        outer_index, _entry_bytes, report = build_master_play_edits(
            GAME_0A, package_maps=(change,)
        )
        self.assertEqual(outer_index, 180)
        self.assertEqual(report["changed_ranges"], [[offset, offset + 11]])
        self.assertEqual(report["package_maps_already_matching"], 0)
        self.assertEqual(report["package_maps"][0]["formation_name"], "I Pro")
        self.assertEqual(report["package_maps"][0]["resource_offset"], offset)
        self.assertFalse(report["claims"]["runtime_proved"])
        self.assertFalse(report["claims"]["third_and_long_director_changed"])


if __name__ == "__main__":
    unittest.main()

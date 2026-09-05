"""View-model and dialog tests for the PS2 replacement-pack export window.

Everything here is synthetic: hand-built PNGs, a hand-built mapping manifest in
a tempdir, a hand-built ``.2k5mod``.  No disc, no game data and -- deliberately
-- not the shipped manifest either, which a given build may not carry yet.  A
test that needed retail bytes could not be committed, and one that needed the
shipped map would fail on every branch where it has not landed.

The dialog's Qt-free view model is tested without a display; the dialog itself
is exercised against an offscreen QApplication and skipped where PyQt5 is
absent, following the disc-inventory tests.

The test that matters most is
``DialogTests.test_the_receipt_carries_the_emulator_settings``: a pack shown
without ``ClassicTextureNames`` and ``LoadTextureReplacements`` looks like it
worked and then silently draws the retail art.

Close behind it is the emulator-target group.  The pack is the same bytes for
every answer, so nothing else here would catch a window that stopped asking, or
tooltips that stopped explaining why it asks.  Those tests check the hover text
against ``TARGET_EXPLANATION_REQUIRED_FACTS`` rather than against sentences of
their own, so the wording -- including the measured numbers -- can be corrected
in one place and still cannot quietly disappear.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
import zipfile
import zlib

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_ROOT, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import ps2_export_service as svc  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402

try:
    import mod_editor.gui.ps2_export_dialog_qt as dialog_module
except ImportError:  # PyQt5 is not installed here
    dialog_module = None


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def png_bytes(width: int, height: int, value: int = 0x40) -> bytes:
    """A real, minimal, valid RGBA PNG built from scratch."""

    raw = b"".join(
        b"\x00" + bytes([value, value, value, 0xFF]) * width for _ in range(height)
    )
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def props(width_log2: int, height_log2: int, psm: int = 0x29) -> str:
    """The trailing ``%08x``: ``PSM | TW << 6 | TH << 10 | TCC << 14``."""

    return "%08x" % (psm | (width_log2 << 6) | (height_log2 << 10) | (1 << 14))


WIDE = props(9, 8)  # 512x256

MAPPED = "p8:5:one"
FANOUT = "tset:7:4:2:socks01"
UNMAPPED = "p8:404:nowhere"
LOGICAL = "nfl2k5.uniform.01h0.torso"

NAME_ONE = "1111-2222-" + WIDE + ".png"
NAME_FAN_A = "3333-4444-" + WIDE + ".png"
NAME_FAN_B = "3333-4444-" + WIDE + "-mip1.png"

#: The provenance a shipped manifest carries, plus the ``requires_setting``
#: block whose two values decide whether the emulator draws the pack at all.
PROVENANCE = {
    "counts": {"entries": 3},
    "disc": {
        "serial": "SLUS-20919",
        "boot_sha256": "0" * 64,
        "content_sha256": "1" * 64,
    },
    "emulator": {
        "name": "PenguinScreen2",
        "commit": "0123456789abcdef",
        "hash_convention": "classic-tcc-bit14",
        "requires_setting": {
            "ClassicTextureNames": True,
            "LoadTextureReplacements": True,
        },
    },
    "generated": "2026-01-01T00:00:00Z",
    "method": "hop1/v5",
}


def manifest_document() -> dict:
    """A 1:1 row and a 1:2 fan-out row. ``UNMAPPED`` is deliberately absent."""

    document = dict(PROVENANCE)
    document["schema"] = svc.MAPPING_SCHEMA
    document["entries"] = [
        {"pcsx2_png": NAME_ONE, "xbox_asset_id": MAPPED},
        {"pcsx2_png": NAME_FAN_A, "xbox_asset_id": FANOUT},
        {"pcsx2_png": NAME_FAN_B, "xbox_asset_id": FANOUT},
    ]
    return document


def write_manifest(directory: Path) -> Path:
    path = directory / svc.MAPPING_MANIFEST
    path.write_bytes(
        (json.dumps(manifest_document(), indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return path


def write_project(directory: Path, name: str = "kit.2k5mod") -> Path:
    """A ``.2k5mod`` with two mappable edits and two the map cannot name.

    512x256 art matches the manifest's geometry exactly, so no export in this
    suite resamples and none of it needs Pillow.
    """

    path = directory / name
    payload = png_bytes(512, 256)
    rows = []
    with zipfile.ZipFile(path, "w") as archive:
        for index, asset in enumerate((MAPPED, FANOUT, UNMAPPED, LOGICAL)):
            member = f"replacements/{index}.png"
            archive.writestr(member, payload)
            rows.append({"asset_id": asset, "file": member})
        archive.writestr("manifest.json", json.dumps({
            "schema": "2k5_mod_studio_project/v1",
            "game": "espn_nfl_2k5_xbox",
            "payload_policy": "user-replacements-only",
            "edits": rows,
        }, indent=2, sort_keys=True))
    return path


@unittest.skipIf(dialog_module is None, "PyQt5 is not installed")
class ViewModelTests(unittest.TestCase):
    def test_nothing_is_offered_without_a_plan(self) -> None:
        state = dialog_module.ps2_export_action_state(
            plan_ready=False, busy=False, mapped_count=3, exported=False,
            target_chosen=True,
        )
        self.assertTrue(state.can_choose_project)
        self.assertFalse(state.can_export)
        self.assertFalse(state.can_verify)

    def test_a_busy_dialog_offers_nothing(self) -> None:
        state = dialog_module.ps2_export_action_state(
            plan_ready=True, busy=True, mapped_count=3, exported=True,
            target_chosen=True,
        )
        self.assertEqual(
            (state.can_choose_project, state.can_export, state.can_verify),
            (False, False, False),
        )

    def test_exporting_needs_at_least_one_mapped_target(self) -> None:
        none_mapped = dialog_module.ps2_export_action_state(
            plan_ready=True, busy=False, mapped_count=0, exported=False,
            target_chosen=True,
        )
        some = dialog_module.ps2_export_action_state(
            plan_ready=True, busy=False, mapped_count=1, exported=False,
            target_chosen=True,
        )
        self.assertFalse(none_mapped.can_export)
        self.assertTrue(some.can_export)

    def test_exporting_waits_for_the_emulator_answer(self) -> None:
        """No default, so an unanswered window cannot write a pack."""

        unanswered = dialog_module.ps2_export_action_state(
            plan_ready=True, busy=False, mapped_count=2, exported=False,
            target_chosen=False,
        )
        answered = dialog_module.ps2_export_action_state(
            plan_ready=True, busy=False, mapped_count=2, exported=False,
            target_chosen=True,
        )
        self.assertFalse(unanswered.can_export)
        self.assertTrue(answered.can_export)
        # The question gates writing, not reading.
        self.assertTrue(unanswered.can_choose_project)

    def test_verifying_needs_a_pack_to_have_been_written(self) -> None:
        before = dialog_module.ps2_export_action_state(
            plan_ready=True, busy=False, mapped_count=1, exported=False,
            target_chosen=True,
        )
        after = dialog_module.ps2_export_action_state(
            plan_ready=True, busy=False, mapped_count=1, exported=True,
            target_chosen=True,
        )
        self.assertFalse(before.can_verify)
        self.assertTrue(after.can_verify)

    def test_status_labels_and_refusals(self) -> None:
        self.assertEqual(dialog_module.status_label(svc.STATUS_MAPPED), "Will export")
        self.assertIn("not in the map",
                      dialog_module.status_label(svc.STATUS_UNMAPPED))
        self.assertIn("ambiguous",
                      dialog_module.status_label(svc.STATUS_AMBIGUOUS))
        with self.assertRaises(ValidationError):
            dialog_module.status_label("probably")

    def test_the_suggested_folder_name_derives_from_the_project(self) -> None:
        self.assertEqual(dialog_module.suggested_pack_name("Lions Away.2k5mod"),
                         "Lions Away-pcsx2-pack")
        self.assertEqual(dialog_module.suggested_pack_name(""),
                         "nfl2k5-ps2-pcsx2-pack")

    def test_the_summary_says_when_nothing_is_mappable(self) -> None:
        self.assertIn("no edited texture targets",
                      dialog_module.plan_summary_text(0, 0, 0))
        none_mapped = dialog_module.plan_summary_text(0, 3, 0)
        self.assertIn("None of the 3", none_mapped)
        self.assertIn("nothing to export", none_mapped)
        self.assertEqual(dialog_module.plan_summary_text(2, 1, 3),
                         "2 of 3 edited targets will write 3 PCSX2 files.")

    def test_required_settings_come_from_the_manifest_provenance(self) -> None:
        self.assertEqual(
            dialog_module.required_settings(PROVENANCE),
            ("ClassicTextureNames=true", "LoadTextureReplacements=true"),
        )

    def test_required_settings_are_found_at_the_top_level_too(self) -> None:
        top = {"requires_setting": ["ClassicTextureNames=true",
                                    "LoadTextureReplacements=true"]}
        self.assertEqual(
            dialog_module.required_settings(top),
            ("ClassicTextureNames=true", "LoadTextureReplacements=true"),
        )

    def test_a_manifest_without_the_key_still_names_both_settings(self) -> None:
        # A manifest predating ``requires_setting`` must not produce a receipt
        # that quietly omits the two settings the emulator needs.
        without = {"emulator": {"name": "PenguinScreen2"}}
        self.assertEqual(dialog_module.required_settings(without),
                         dialog_module.DEFAULT_REQUIRED_SETTINGS)
        self.assertEqual(dialog_module.required_settings(None),
                         dialog_module.DEFAULT_REQUIRED_SETTINGS)

    def test_the_three_targets_match_the_service(self) -> None:
        self.assertEqual(dialog_module.EMULATOR_TARGET_VALUES,
                         svc.EMULATOR_TARGETS)
        with self.assertRaises(ValidationError):
            dialog_module.target_choice("dolphin")

    def test_the_explanation_still_states_every_required_fact(self) -> None:
        """The contract in docs/product/PS2_M1_PLAN.md, checked against itself.

        The facts live in one constant so the wording -- and the measured
        numbers in it -- can be corrected in one place; this asserts the hover
        text has not drifted away from them.
        """

        self.assertEqual(dialog_module.target_explanation_gaps(), ())
        text = dialog_module.target_explanation_text()
        for fact in dialog_module.TARGET_EXPLANATION_REQUIRED_FACTS:
            self.assertIn(fact, text)

    def test_every_choice_carries_a_label_an_audience_and_an_explanation(self) -> None:
        self.assertEqual(len(dialog_module.EMULATOR_TARGET_CHOICES), 3)
        for choice in dialog_module.EMULATOR_TARGET_CHOICES:
            with self.subTest(choice=choice.value):
                self.assertTrue(choice.label.strip())
                self.assertTrue(choice.audience.strip())
                # Long enough to be an explanation rather than a restatement
                # of the label.
                self.assertGreater(len(choice.tooltip), 80)
        self.assertIn("the files are the same",
                      dialog_module.TARGET_GROUP_TOOLTIP.lower())

    def test_the_instructions_follow_the_target(self) -> None:
        """Each answer names the settings that emulator actually has."""

        classic = dialog_module.penguinscreen2_instructions(
            Path("/tmp/pack"), PROVENANCE, svc.TARGET_PENGUINSCREEN2_CLASSIC)
        modern = dialog_module.penguinscreen2_instructions(
            Path("/tmp/pack"), PROVENANCE, svc.TARGET_PCSX2_MODERN)
        legacy = dialog_module.penguinscreen2_instructions(
            Path("/tmp/pack"), PROVENANCE, svc.TARGET_PCSX2_LEGACY)
        self.assertIn("ClassicTextureNames=true", classic)
        self.assertIn("LoadTextureReplacements=true", classic)
        # A stock PCSX2 has no such setting; naming it sends the user hunting.
        self.assertNotIn("ClassicTextureNames=true", modern)
        self.assertNotIn("ClassicTextureNames=true", legacy)
        self.assertIn("1.7.4034", modern)
        self.assertIn("584", modern)
        self.assertIn("1.7.4034", legacy)
        for text in (classic, modern, legacy):
            self.assertIn("LoadTextureReplacements=true", text)
            self.assertIn("retail art", text)
            self.assertIn(str(Path("/tmp/pack")), text)

    def test_the_instructions_carry_both_settings_and_the_path(self) -> None:
        text = dialog_module.penguinscreen2_instructions(
            Path("/tmp/pack"), PROVENANCE
        )
        self.assertIn("ClassicTextureNames=true", text)
        self.assertIn("LoadTextureReplacements=true", text)
        self.assertIn(str(Path("/tmp/pack")), text)
        self.assertIn("textures/SLUS-20919/replacements", text)
        self.assertIn("retail art", text)

    def test_the_receipt_summary_counts_resamples_and_skips(self) -> None:
        class Row:
            def __init__(self, target, resampled=None):
                self.source_target = target
                self.resampled_from = resampled

        class Receipt:
            files = (Row("a"), Row("a", [64, 64]), Row("b"))
            skipped = ({"target": "c"},)

        text = dialog_module.receipt_summary_text(Receipt())
        self.assertIn("Wrote 3 PCSX2 files from 2 edited targets.", text)
        self.assertIn("1 were resampled", text)
        self.assertIn("1 target skipped", text)

    def test_the_verdict_line_reports_a_downgrade(self) -> None:
        self.assertIn("PASS", dialog_module.verdict_text(
            {"result": "PASS", "files_checked": 3}))
        downgraded = dialog_module.verdict_text({
            "result": "INCOMPLETE", "files_checked": 3,
            "downgrade_reason": "no project was supplied",
        })
        self.assertIn("INCOMPLETE", downgraded)
        self.assertIn("no project was supplied", downgraded)

    def test_a_live_session_with_edits_is_explained_not_denied(self) -> None:
        class Session:
            modified_asset_ids = frozenset({"p8:1:a", "p8:2:b"})

        hint = dialog_module.live_session_hint(Session(), 0)
        self.assertIn("2 edited items", hint)
        self.assertIn(".2k5mod", hint)
        # A session that planned something, and a plain path, say nothing.
        self.assertEqual(dialog_module.live_session_hint(Session(), 2), "")
        self.assertEqual(dialog_module.live_session_hint(Path("a.2k5mod"), 0), "")
        self.assertEqual(dialog_module.live_session_hint(None, 0), "")


def _qt_application():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception:
        return None
    return QApplication.instance() or QApplication([])


@unittest.skipIf(dialog_module is None, "PyQt5 is not installed")
class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _qt_application()
        if cls.app is None:  # pragma: no cover - environment guard
            raise unittest.SkipTest("no QApplication is available")

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-export-dialog-")
        self.root = Path(self._temp.name)
        self.manifest = write_manifest(self.root)
        self.project = write_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _settle(self, dialog, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while dialog._busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(dialog._busy, "the background operation never finished")

    #: ``None`` is a meaningful project (open with no project), so the
    #: "use the suite's default" case needs a sentinel of its own.
    _DEFAULT = object()

    def _dialog(self, project=_DEFAULT, manifest=_DEFAULT,
                target=svc.TARGET_PENGUINSCREEN2_CLASSIC):
        """A window, with the emulator already answered unless a test wants none.

        The window opens with nothing selected on purpose, so a test about the
        export path has to answer that question first, exactly as a user does.
        ``target=None`` leaves it unanswered.
        """

        dialog = dialog_module.Ps2ExportDialog(
            self.project if project is self._DEFAULT else project,
            manifest=self.manifest if manifest is self._DEFAULT else manifest,
        )
        if target is not None:
            dialog._target_radios[target].setChecked(True)
        return dialog

    def _export_to(self, dialog, destination: Path) -> None:
        """Drive the export, standing in for the folder chooser and the prompt."""

        from PyQt5.QtWidgets import QFileDialog, QMessageBox

        real_save = QFileDialog.getSaveFileName
        real_question = QMessageBox.question
        QFileDialog.getSaveFileName = staticmethod(
            lambda *args, **kwargs: (str(destination), "")
        )
        QMessageBox.question = staticmethod(
            lambda *args, **kwargs: QMessageBox.No
        )
        try:
            dialog._export()
            self._settle(dialog)
        finally:
            QFileDialog.getSaveFileName = real_save
            QMessageBox.question = real_question

    def test_the_dialog_is_a_qt_dialog(self) -> None:
        from PyQt5.QtWidgets import QDialog

        self.assertTrue(dialog_module.PYQT5_AVAILABLE)
        self.assertTrue(issubclass(dialog_module.Ps2ExportDialog, QDialog))

    def test_a_project_is_planned_into_the_table_on_open(self) -> None:
        dialog = self._dialog()
        try:
            self.assertEqual(dialog.table.rowCount(), 4)
            targets = [dialog.table.item(row, 0).text()
                       for row in range(dialog.table.rowCount())]
            self.assertEqual(sorted(targets), sorted([MAPPED, FANOUT, UNMAPPED, LOGICAL]))
            by_target = {dialog.table.item(row, 0).text():
                         (dialog.table.item(row, 1).text(),
                          dialog.table.item(row, 2).text(),
                          dialog.table.item(row, 3).text())
                         for row in range(dialog.table.rowCount())}
            self.assertEqual(by_target[MAPPED][0], "Will export")
            self.assertEqual(by_target[MAPPED][2], "1")
            # The fan-out row writes both of its PCSX2 names.
            self.assertEqual(by_target[FANOUT][2], "2")
            self.assertIn("no manifest row", by_target[UNMAPPED][1])
            self.assertEqual(by_target[UNMAPPED][2], "0")
            # A logical uniform id is reported with its own reason, not guessed.
            self.assertIn("logical uniform provider", by_target[LOGICAL][1])
            self.assertIn("2 of 4 edited targets", dialog.info_label.text())
            self.assertTrue(dialog.export_button.isEnabled())
            self.assertFalse(dialog.verify_button.isEnabled())
        finally:
            dialog.done(0)

    def test_nothing_is_answered_when_the_window_opens(self) -> None:
        """No default, because the right answer depends on the user's emulator.

        A default would be a guess made silently, and the way they would find
        out it was wrong is by following instructions for a setting their build
        does not have.
        """

        dialog = self._dialog(target=None)
        try:
            self.assertIsNone(dialog.selected_target())
            for radio in dialog._target_radios.values():
                self.assertFalse(radio.isChecked())
            self.assertFalse(dialog.export_button.isEnabled())
            self.assertIn("no default", dialog.info_label.text())
            # Answering is all it takes.
            dialog._target_radios[svc.TARGET_PCSX2_MODERN].setChecked(True)
            self.assertEqual(dialog.selected_target(), svc.TARGET_PCSX2_MODERN)
            self.assertTrue(dialog.export_button.isEnabled())
        finally:
            dialog.done(0)

    def test_every_choice_explains_itself_on_hover(self) -> None:
        """Tooltip and accessible description, both from the one constant.

        A screen-reader user is told exactly what a mouse user is told, and the
        required facts are checked against
        ``TARGET_EXPLANATION_REQUIRED_FACTS`` rather than sentences written
        here, so correcting the wording is one edit in one place.
        """

        dialog = self._dialog(target=None)
        try:
            self.assertEqual(len(dialog._target_radios),
                             len(dialog_module.EMULATOR_TARGET_CHOICES))
            hovers = [dialog.target_group.toolTip()]
            for choice in dialog_module.EMULATOR_TARGET_CHOICES:
                radio = dialog._target_radios[choice.value]
                with self.subTest(choice=choice.value):
                    self.assertEqual(radio.text(), choice.label)
                    self.assertEqual(radio.toolTip(), choice.tooltip)
                    self.assertEqual(radio.accessibleDescription(),
                                     choice.tooltip)
                    self.assertTrue(radio.toolTip().strip())
                hovers.append(radio.toolTip())
                hovers.append(radio.text())
            # The group explains the question itself, not just the answers.
            self.assertTrue(dialog.target_group.toolTip().strip())
            self.assertEqual(dialog.target_group.toolTip(),
                             dialog.target_group.accessibleDescription())
            whole = "\n".join(hovers)
            for fact in dialog_module.TARGET_EXPLANATION_REQUIRED_FACTS:
                self.assertIn(fact, whole,
                              f"the hover text no longer says {fact}")
        finally:
            dialog.done(0)

    def test_each_answer_reaches_the_receipt_and_the_instructions(self) -> None:
        """Same files every time; a different receipt and different steps."""

        digests = {}
        for target in svc.EMULATOR_TARGETS:
            with self.subTest(target=target):
                destination = self.root / ("pack-" + target)
                dialog = self._dialog(target=target)
                try:
                    self._export_to(dialog, destination)
                    receipt = json.loads(
                        (destination / svc.RECEIPT_NAME).read_text("utf-8"))
                    self.assertEqual(receipt["emulator_target"], target)
                    digests[target] = sorted(
                        (row["pcsx2_png"], row["sha256"])
                        for row in receipt["files"]
                    )
                    shown = dialog.receipt_label.text()
                    self.assertIn(
                        dialog_module.target_choice(target).audience, shown)
                    for setting in receipt["instructions"]["settings"]:
                        self.assertIn(setting, shown)
                finally:
                    dialog.done(0)
        first = digests[svc.EMULATOR_TARGETS[0]]
        for target, rows in digests.items():
            self.assertEqual(rows, first, target)

    def test_the_validators_own_explanation_check_passes_here(self) -> None:
        """The step ``validate_nfl2k5_ps2_replacement_pack.sh`` runs.

        Running it in CI as well as in the validator means a change that
        empties the hover text fails on the machine that made it, not later on
        somebody's release box.
        """

        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = dialog_module.check_target_explanation()
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("NFL2K5_PS2_EXPORT_TARGET_EXPLANATION_PASS",
                      buffer.getvalue())
        self.assertIn("default=none", buffer.getvalue())

    def test_export_is_refused_when_nothing_maps(self) -> None:
        # A project whose only edit the manifest cannot name must not offer an
        # export that would publish a folder holding just a receipt.
        path = self.root / "nothing.2k5mod"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("replacements/0.png", png_bytes(64, 64))
            archive.writestr("manifest.json", json.dumps({
                "edits": [{"asset_id": UNMAPPED, "file": "replacements/0.png"}],
            }))
        dialog = self._dialog(project=path)
        try:
            self.assertEqual(dialog.table.rowCount(), 1)
            self.assertFalse(dialog.export_button.isEnabled())
            self.assertIn("nothing to export", dialog.info_label.text())
        finally:
            dialog.done(0)

    def test_a_missing_manifest_is_reported_not_raised(self) -> None:
        absent = self.root / "not-shipped" / svc.MAPPING_MANIFEST
        dialog = self._dialog(manifest=absent)
        try:
            self.assertEqual(dialog.table.rowCount(), 0)
            self.assertIn("not shipped in this build", dialog.info_label.text())
            self.assertFalse(dialog.export_button.isEnabled())
            self.assertFalse(dialog.verify_button.isEnabled())
            self.assertTrue(dialog.project_button.isEnabled())
        finally:
            dialog.done(0)

    def test_the_shipped_manifest_path_never_crashes_the_window(self) -> None:
        """``manifest=None`` is what the studio and ``--ps2-export`` pass.

        The map is produced by a separate work package and may or may not be in
        a given build, so this asserts the invariant that holds either way: the
        window opens, and Export is offered exactly when a plan exists.
        """

        dialog = self._dialog(manifest=None)
        try:
            shipped = svc.DEFAULT_MANIFEST_PATH.is_file()
            if shipped:
                self.assertIsNotNone(dialog._plan)
            else:
                self.assertIsNone(dialog._plan)
                self.assertIn("not shipped in this build", dialog.info_label.text())
            self.assertEqual(dialog.export_button.isEnabled(),
                             dialog._plan is not None
                             and bool(dialog._plan.mapped))
            self.assertTrue(dialog.project_button.isEnabled())
        finally:
            dialog.done(0)

    def test_a_project_that_is_not_there_is_reported_not_raised(self) -> None:
        """``--ps2-export <typo>`` must open a window, not a traceback.

        ``project_from_archive`` stats the path before its own try block, so a
        missing project surfaces as a bare FileNotFoundError rather than the
        service's Ps2ExportError. Construction has to survive it -- and name the
        file, which "[Errno 2] No such file or directory" does not.
        """

        missing = self.root / "gone.2k5mod"
        dialog = self._dialog(project=missing)
        try:
            self.assertIsNone(dialog._plan)
            self.assertEqual(dialog.table.rowCount(), 0)
            self.assertIn(str(missing), dialog.info_label.text())
            self.assertIn(str(missing), dialog.status_label.text())
            self.assertFalse(dialog.export_button.isEnabled())
            # Recoverable: choosing a real project from here still works.
            dialog.set_project(self.project)
            self.assertEqual(dialog.table.rowCount(), 4)
        finally:
            dialog.done(0)

    def test_a_project_that_is_not_a_zip_is_reported_not_raised(self) -> None:
        junk = self.root / "junk.2k5mod"
        junk.write_bytes(b"this is not a zip archive")
        dialog = self._dialog(project=junk)
        try:
            self.assertIsNone(dialog._plan)
            self.assertIn("could not be planned", dialog.info_label.text())
            self.assertFalse(dialog.export_button.isEnabled())
        finally:
            dialog.done(0)

    def test_no_project_leaves_the_chooser_as_the_only_action(self) -> None:
        dialog = self._dialog(project=None)
        try:
            self.assertEqual(dialog.table.rowCount(), 0)
            self.assertFalse(dialog.export_button.isEnabled())
            self.assertTrue(dialog.project_button.isEnabled())
            self.assertIn("No project is open", dialog.status_label.text())
            dialog.set_project(self.project)
            self.assertEqual(dialog.table.rowCount(), 4)
            self.assertTrue(dialog.export_button.isEnabled())
        finally:
            dialog.done(0)

    def test_exporting_off_thread_writes_the_pack_and_the_receipt(self) -> None:
        destination = self.root / "pack"
        dialog = self._dialog()
        try:
            self._export_to(dialog, destination)
            self.assertIsNotNone(dialog._receipt)
            replacements = destination.joinpath(*svc.REPLACEMENTS_DIR)
            written = sorted(p.name for p in replacements.iterdir())
            self.assertEqual(written, sorted([NAME_ONE, NAME_FAN_A, NAME_FAN_B]))
            self.assertTrue((destination / svc.RECEIPT_NAME).is_file())
            self.assertTrue((destination / svc.MAPPING_MANIFEST).is_file())
            # Only the mapped targets; the unmapped and logical ones wrote
            # nothing at all.
            receipt = json.loads((destination / svc.RECEIPT_NAME).read_text("utf-8"))
            self.assertEqual(
                sorted({row["source_target"] for row in receipt["files"]}),
                sorted([MAPPED, FANOUT]),
            )
            self.assertTrue(dialog.verify_button.isEnabled())
        finally:
            dialog.done(0)

    def test_the_receipt_carries_the_emulator_settings(self) -> None:
        destination = self.root / "pack-settings"
        dialog = self._dialog()
        try:
            self._export_to(dialog, destination)
            shown = dialog.receipt_label.text()
            self.assertFalse(dialog.receipt_label.isHidden())
            self.assertIn("ClassicTextureNames=true", shown)
            self.assertIn("LoadTextureReplacements=true", shown)
            self.assertIn("Wrote 3 PCSX2 files", shown)
            self.assertIn(str(destination), shown)
        finally:
            dialog.done(0)

    def test_an_existing_destination_shows_the_services_own_refusal(self) -> None:
        from PyQt5.QtWidgets import QMessageBox

        destination = self.root / "already-there"
        destination.mkdir()
        dialog = self._dialog()
        warnings: list[str] = []
        real_warning = QMessageBox.warning
        QMessageBox.warning = staticmethod(
            lambda *args, **kwargs: warnings.append(str(args[2]))
        )
        try:
            self._export_to(dialog, destination)
            self.assertEqual(len(warnings), 1)
            self.assertIn("already exists there", warnings[0])
            self.assertIn("already exists there", dialog.status_label.text())
            self.assertIsNone(dialog._receipt)
            # The folder that was already there is untouched.
            self.assertEqual(list(destination.iterdir()), [])
            self.assertTrue(dialog.export_button.isEnabled())
        finally:
            QMessageBox.warning = real_warning
            dialog.done(0)

    def test_the_independent_verifier_passes_the_exported_pack(self) -> None:
        destination = self.root / "pack-verify"
        dialog = self._dialog()
        try:
            self._export_to(dialog, destination)
            dialog._verify()
            self._settle(dialog)
            self.assertIn("PASS", dialog.status_label.text())
            self.assertIn("3 file(s) re-checked", dialog.status_label.text())
        finally:
            dialog.done(0)

    def test_accepting_the_offer_verifies_without_stranding_the_window(self) -> None:
        """Answering "yes" starts a second task from inside the first's handler.

        That reentrancy is the part worth pinning: if the busy flag were cleared
        in the wrong order the window would be left unclosable, or the second
        task would never start.
        """

        from PyQt5.QtWidgets import QFileDialog, QMessageBox

        destination = self.root / "pack-offered"
        dialog = self._dialog()
        real_save = QFileDialog.getSaveFileName
        real_question = QMessageBox.question
        QFileDialog.getSaveFileName = staticmethod(
            lambda *args, **kwargs: (str(destination), "")
        )
        QMessageBox.question = staticmethod(lambda *args, **kwargs: QMessageBox.Yes)
        try:
            dialog._export()
            self._settle(dialog)
            self.assertIn("PASS", dialog.status_label.text())
            self.assertFalse(dialog._busy)
            self.assertTrue(dialog.export_button.isEnabled())
        finally:
            QFileDialog.getSaveFileName = real_save
            QMessageBox.question = real_question
            dialog.done(0)

    def test_a_tampered_pack_fails_verification_and_says_so(self) -> None:
        from PyQt5.QtWidgets import QMessageBox

        destination = self.root / "pack-tampered"
        dialog = self._dialog()
        warnings: list[str] = []
        real_warning = QMessageBox.warning
        QMessageBox.warning = staticmethod(
            lambda *args, **kwargs: warnings.append(str(args[2]))
        )
        try:
            self._export_to(dialog, destination)
            victim = destination.joinpath(*svc.REPLACEMENTS_DIR, NAME_ONE)
            victim.write_bytes(png_bytes(512, 256, value=0x7F))
            dialog._verify()
            self._settle(dialog)
            self.assertEqual(len(warnings), 1)
            self.assertIn(NAME_ONE, warnings[0])
            # The refusal must not claim the pack was rolled back; it is still
            # on disk exactly as written.
            self.assertIn("still on disk", warnings[0])
            self.assertTrue(victim.is_file())
        finally:
            QMessageBox.warning = real_warning
            dialog.done(0)

    def test_a_live_session_without_staged_bytes_is_explained(self) -> None:
        class Session:
            modified_asset_ids = frozenset({"p8:5:one", "p8:6:two"})
            session_id = "live"

        dialog = self._dialog(project=Session())
        try:
            self.assertEqual(dialog.table.rowCount(), 0)
            self.assertIn("2 edited items", dialog.info_label.text())
            self.assertIn(".2k5mod", dialog.info_label.text())
            self.assertFalse(dialog.export_button.isEnabled())
        finally:
            dialog.done(0)

    def test_closing_is_refused_while_an_operation_runs(self) -> None:
        dialog = self._dialog()
        try:
            dialog._busy = True
            dialog._busy_verb = "Writing the replacement pack"
            dialog.reject()
            self.assertIn("still running", dialog.status_label.text())
            self.assertEqual(dialog.result(), 0)
        finally:
            dialog._busy = False
            dialog.done(0)

    def test_no_retail_path_or_disc_handle_is_reachable_from_the_window(self) -> None:
        # The window must own presentation only: the plan it renders is the
        # sole source of what gets written, and it carries the user's own PNGs.
        dialog = self._dialog()
        try:
            self.assertTrue(hasattr(dialog, "_plan"))
            for planned in dialog._plan.files:
                self.assertIn(planned.source_target, {MAPPED, FANOUT})
                self.assertTrue(planned.payload.startswith(PNG_SIGNATURE))
        finally:
            dialog.done(0)


@unittest.skipIf(dialog_module is None, "PyQt5 is not installed")
class EntryPointTests(unittest.TestCase):
    """``--ps2-export`` and the studio's File-menu entry reach this window.

    Both are wiring, so both are tested by standing in for the parts that would
    open a window or run an event loop.  Without this, a renamed handler or a
    dropped branch would only be found by launching the app by hand.
    """

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-export-entry-")
        self.root = Path(self._temp.name)
        self.project = write_project(self.root)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _run_main(self, argv):
        """Call ``mod_editor.__main__.main`` with the window and loop stubbed."""

        from PyQt5.QtWidgets import QApplication

        import mod_editor.__main__ as entry

        built = []

        class FakeDialog:
            def __init__(self, project=None, **kwargs):
                built.append(project)

            def show(self):
                pass

        real_exec = QApplication.exec_
        QApplication.exec_ = lambda self: 0
        sys.modules["mod_editor.gui.ps2_export_dialog_qt"].Ps2ExportDialog, real_dialog = (
            FakeDialog,
            sys.modules["mod_editor.gui.ps2_export_dialog_qt"].Ps2ExportDialog,
        )
        try:
            code = entry.main(argv)
        finally:
            QApplication.exec_ = real_exec
            sys.modules["mod_editor.gui.ps2_export_dialog_qt"].Ps2ExportDialog = real_dialog
        return code, built

    def test_the_flag_opens_the_window_on_the_given_project(self) -> None:
        code, built = self._run_main(["--ps2-export", str(self.project)])
        self.assertEqual(code, 0)
        self.assertEqual(built, [self.project])

    def test_the_flag_without_a_path_opens_the_chooser(self) -> None:
        # "--ps2-export with no path" must stay distinguishable from the flag
        # being absent, or the studio would open instead.
        code, built = self._run_main(["--ps2-export"])
        self.assertEqual(code, 0)
        self.assertEqual(built, [None])

    def test_the_studio_offers_the_entry_and_a_handler_for_it(self) -> None:
        from mod_editor.gui import studio_qt

        window = studio_qt.StudioMainWindow
        self.assertTrue(callable(getattr(window, "_open_ps2_export", None)))
        source = Path(studio_qt.__file__).read_text(encoding="utf-8")
        self.assertIn('"Export PS2 replacement pack…"', source)
        self.assertIn("self._ps2_export_action.triggered.connect", source)
        self.assertIn("from .ps2_export_dialog_qt import Ps2ExportDialog", source)


if __name__ == "__main__":
    unittest.main()

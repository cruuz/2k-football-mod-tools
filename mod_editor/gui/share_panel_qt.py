"""Share tab: create a ``.2k5patch`` from a patched copy, or apply one to your own disc.

Sits next to the ESPN Scorebug & Ticker tab.  A patch file carries only the bytes that
differ from the base disc image (each run pinned to the hash of the bytes it replaces),
the creator's source assets and a recipe of the studio operations -- never the disc.
Applying copies the reader's own disc image and splices the runs into the copy after
verifying every run; a wrong base is refused before anything is written.  All disc work
runs in the background so the studio stays responsive.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mod_editor.core import mod_build, modpack
from mod_editor.gui.ux_text import XEMU_LINE, Details
from mod_editor.gui.task_delivery import bound

IMAGE_FILTER = "Disc images (*.iso *.xiso);;All files (*)"
PACK_FILTER = f"2K5 disc patches (*{modpack.EXTENSION});;All files (*)"
PROJECT_FILTER = f"2K5 Mod Studio projects (*{modpack.PROJECT_EXTENSION});;All files (*)"
ASSET_FILTER = "Source files (*.png *.wav *.json *.txt *.csv);;All files (*)"


def _human(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{count} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{count} B"


class _Signals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)


class _Task(QRunnable):
    def __init__(self, operation: Callable[[modpack.ProgressSink], object]) -> None:
        super().__init__()
        self.signals = _Signals()
        self._operation = operation

    def run(self) -> None:
        try:
            self.signals.finished.emit(self._operation(self.signals.progress.emit))
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


class SharePanel(QWidget):
    """Create and apply ``.2k5patch`` files (disc images only, always on copies)."""

    disc_written = pyqtSignal(str)   # a disc copy Apply wrote and verified (Play latest can start it)

    def __init__(self, facade: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._task: _Task | None = None
        self.busy = False
        self._pack: modpack.Pack | None = None
        self._check_state: str | None = None
        self._asset_paths: list[Path] = []
        self.last_export: dict | None = None
        self.last_check: dict | None = None
        self.last_apply: dict | None = None
        self._build_pair_owned = False     # a finished Build owns base/patched; the open disc must not replace them
        self._followed_source = ""         # the last open disc the install form followed
        self._build()

    # ------------------------------------------------------------------ the open-disc hook
    def follow_source(self, source: Path | str) -> None:
        """Fill the export "Starting disc" (only while no build owns the pair) and the install "Your disc".

        The install source follows the open disc when it is empty or still holds the previous
        open disc; a disc the user chose by hand stays.  A changed install source invalidates the
        old check report.
        """

        text = str(source)
        if not self._build_pair_owned and not self.base_field.text().strip():
            self.base_field.setText(text)
        current = self.source_field.text().strip()
        if not current or current == self._followed_source:
            if current != text:
                self.source_field.setText(text)
                self._check_state = None
                self.check_status.setText("")
                self.describe_source()
        self._followed_source = text
        self._refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Export a mod file (.2k5patch) for someone with a compatible copy of the game. "
            "It contains changes rather than a full disc."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        intro_details = Details("How a mod file works")
        intro_details.add_text(
            "A mod file holds the bytes that differ from the disc you started from, each pinned to the "
            "bytes it replaces, plus any source files you choose to include and a description of the "
            "studio changes it recognises. Someone with their own copy of the game applies it to a COPY "
            "of their disc; a disc that is not the same starting disc is refused before anything is written.")
        layout.addWidget(intro_details)

        # ---- the easy way: the copy the Build tab just wrote
        quick = QGroupBox("Export mod file")
        quick_layout = QVBoxLayout(quick)
        self.quick_hint = QLabel("Make a disc on the Build tab, then export a .2k5patch to share yourself.")
        self.quick_hint.setWordWrap(True)
        quick_layout.addWidget(self.quick_hint)
        self.quick_target_label = QLabel("")
        self.quick_target_label.setWordWrap(True)
        self.quick_target_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.quick_target_label.hide()
        quick_layout.addWidget(self.quick_target_label)
        quick_row = QHBoxLayout()
        self.quick_export_button = QPushButton("Export mod file…")
        self.quick_export_button.setObjectName("primaryButton")
        self.quick_export_button.setEnabled(False)
        self.quick_export_button.setToolTip("Make a disc on the Build tab first.")
        self.quick_export_button.clicked.connect(self.start_export)
        quick_row.addWidget(self.quick_export_button)
        self.quick_reason = QLabel("Make a disc on the Build tab first.")
        self.quick_reason.setObjectName("throwMuted")
        quick_row.addWidget(self.quick_reason, 1)
        quick_layout.addLayout(quick_row)
        # ---- the same export from any two disc files (collapsed; every field stays reachable)
        self.export_details = Details("Export from existing disc files")
        create_layout = self.export_details.content
        self.base_field, self.base_button = self._path_row(create_layout, "Starting disc", self._choose_base)
        self.patched_field, self.patched_button = self._path_row(create_layout, "Modified disc", self._choose_patched)
        # A patch built on a working copy still applies to retail when every run's expected bytes
        # are the retail bytes. Point this at a retail dump and the pack says so, instead of
        # warning everyone who opens it about a "custom base" that never affected them.
        self.retail_field, self.retail_button = self._path_row(
            create_layout, "Unmodified reference disc (optional)", self._choose_retail)
        form = QFormLayout()
        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText("What this mod does, e.g. ESPN scorebug + 80-yard bombs")
        self.name_field.textChanged.connect(self._refresh)
        form.addRow("Name", self.name_field)
        self.author_field = QLineEdit()
        form.addRow("Author", self.author_field)
        self.version_field = QLineEdit()
        self.version_field.setPlaceholderText("1")
        form.addRow("Version", self.version_field)
        self.description_field = QPlainTextEdit()
        self.description_field.setPlaceholderText("Optional notes for the people who install it")
        self.description_field.setMaximumHeight(64)
        form.addRow("Description", self.description_field)
        create_layout.addLayout(form)

        assets_box = QGroupBox("Your source files (optional)")
        assets_layout = QVBoxLayout(assets_box)
        self.assets_list = QListWidget()
        self.assets_list.setMaximumHeight(90)
        assets_layout.addWidget(self.assets_list)
        assets_buttons = QHBoxLayout()
        self.add_assets_button = QPushButton("Add source files…")
        self.add_assets_button.clicked.connect(self._choose_assets)
        assets_buttons.addWidget(self.add_assets_button)
        self.remove_asset_button = QPushButton("Remove selected")
        self.remove_asset_button.clicked.connect(self._remove_selected_assets)
        assets_buttons.addWidget(self.remove_asset_button)
        assets_buttons.addStretch(1)
        assets_layout.addLayout(assets_buttons)
        self.project_field, self.project_button = self._path_row(assets_layout, "Project file (.2k5mod, optional)", self._choose_project)
        assets_note = QLabel("Recognized changes are described automatically. Optional files help others edit your work.")
        assets_note.setWordWrap(True)
        assets_layout.addWidget(assets_note)
        create_layout.addWidget(assets_box)

        self.out_field, self.out_button = self._path_row(create_layout, "Save mod file as", self._choose_out)
        create_actions = QHBoxLayout()
        self.export_button = QPushButton("Export mod file")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.start_export)
        create_actions.addWidget(self.export_button)
        create_actions.addStretch(1)
        create_layout.addLayout(create_actions)
        self.export_status = QLabel("")
        self.export_status.setWordWrap(True)
        create_layout.addWidget(self.export_status)
        quick_layout.addWidget(self.export_details)
        layout.addWidget(quick)

        apply_box = QGroupBox("Install a friend's mod")
        apply_layout = QVBoxLayout(apply_box)
        self.pack_field, self.pack_button = self._path_row(apply_layout, "Mod file (.2k5patch)", self._choose_pack)
        self.pack_summary = QLabel("Choose a .2k5patch file to see what it does.")
        self.pack_summary.setWordWrap(True)
        self.pack_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        apply_layout.addWidget(self.pack_summary)
        self.source_field, self.source_button = self._path_row(apply_layout, "Your disc (.iso, never modified)", self._choose_source)
        # Which disc this is decides whether a byte-run patch can ever apply, so say it as soon
        # as the path is known rather than after a check has counted 2,802 mismatching runs.
        self.source_identity = QLabel("")
        self.source_identity.setWordWrap(True)
        self.source_identity.setTextInteractionFlags(Qt.TextSelectableByMouse)
        apply_layout.addWidget(self.source_identity)
        self.check_status = QLabel("")
        self.check_status.setWordWrap(True)
        apply_layout.addWidget(self.check_status)
        self.target_field, self.target_button = self._path_row(apply_layout, "Save disc copy as", self._choose_target)
        apply_actions = QHBoxLayout()
        self.check_button = QPushButton("Check it fits my disc")
        self.check_button.setEnabled(False)
        self.check_button.clicked.connect(self.start_check)
        apply_actions.addWidget(self.check_button)
        self.apply_button = QPushButton("Make disc with this mod")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.start_apply)
        apply_actions.addWidget(self.apply_button)
        apply_actions.addStretch(1)
        apply_layout.addLayout(apply_actions)
        self.apply_status = QLabel("")
        self.apply_status.setWordWrap(True)
        apply_layout.addWidget(self.apply_status)
        layout.addWidget(apply_box)

        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)
        layout.addStretch(1)

    def _path_row(self, parent: QVBoxLayout, label: str, chooser: Callable[[], None]) -> tuple[QLineEdit, QPushButton]:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        field = QLineEdit()
        field.textChanged.connect(self._refresh)
        row.addWidget(field, 1)
        button = QPushButton("Choose…")
        button.clicked.connect(chooser)
        row.addWidget(button)
        parent.addLayout(row)
        return field, button

    # ------------------------------------------------------------------ hooks (overridable in tests)
    def _confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text, QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        return answer == QMessageBox.Ok

    def _notify(self, kind: str, title: str, text: str) -> None:
        if kind == "error":
            QMessageBox.critical(self, title, text)
        else:
            QMessageBox.information(self, title, text)

    # ------------------------------------------------------------------ state
    def _refresh(self) -> None:
        if self.busy:
            for button in (self.export_button, self.check_button, self.apply_button):
                button.setEnabled(False)
            return
        self.export_button.setEnabled(bool(self.base_field.text() and self.patched_field.text()
                                           and self.out_field.text() and self.name_field.text().strip()))
        have_pack = self._pack is not None
        self.check_button.setEnabled(have_pack and bool(self.source_field.text()))
        self.apply_button.setEnabled(have_pack and self._check_state == "ready" and bool(self.target_field.text()))

    def prefill_from_build(self, receipt: dict) -> None:
        """Fill the export form from a Build-tab receipt so one click exports a .2k5patch beside the copy."""
        source, target = Path(str(receipt.get("source", ""))), Path(str(receipt.get("target", "")))
        if not source.name or not target.name:
            return
        self.base_field.setText(str(source))
        self.patched_field.setText(str(target))
        self._build_pair_owned = True
        self.out_field.setText(str(target.with_name(target.name.split(".xiso")[0] + modpack.EXTENSION)))
        plan = receipt.get("plan") if isinstance(receipt.get("plan"), dict) else {}
        if not self.name_field.text().strip():
            self.name_field.setText(str(plan.get("name") or "My NFL 2K5 patch"))
        if not self.version_field.text().strip():
            self.version_field.setText("1")
        self.quick_export_button.setEnabled(True)
        self.quick_export_button.setToolTip("Writes the mod file named below, next to the disc you just made.")
        self.quick_reason.hide()
        self.quick_target_label.setText(f"From {source.name} to {target.name}.\nMod file: {self.out_field.text()}")
        self.quick_target_label.show()
        self.export_status.setText("Ready: press Export mod file to write the mod file next to your copy.")
        self._refresh()

    def set_assets(self, paths: list[Path]) -> None:
        self._asset_paths = [Path(path) for path in paths]
        self.assets_list.clear()
        for path in self._asset_paths:
            self.assets_list.addItem(str(path))
        self._refresh()

    def load_pack(self, path: Path) -> None:
        """Read a patch file's manifest (fast; no disc access) and show its summary."""

        self.pack_field.blockSignals(True)
        self.pack_field.setText(str(path))
        self.pack_field.blockSignals(False)
        self._check_state = None
        self.check_status.setText("")
        try:
            self._pack = modpack.load(path)
        except modpack.ModpackError as exc:
            self._pack = None
            self.pack_summary.setText(f"Couldn't open this mod file: {exc}")
            self._refresh()
            return
        self.pack_summary.setText(self.summarize(modpack.inspect(self._pack)))
        self._refresh()

    @staticmethod
    def summarize(info: dict) -> str:
        base = info["base"]
        lines = [f"{info['name']}  v{info['version'] or '-'}  by {info['author'] or 'unknown'}"]
        if info["description"]:
            lines.append(info["description"])
        lines.append(f"{info['runs']} run(s), {_human(info['bytes'])} changed; patch file {_human(info['pack_bytes'])}; "
                     f"created {info['created'] or '?'} with {info['tool'].get('name') or '?'} {info['tool'].get('version') or ''}")
        if info.get("patch_operations"):
            labels = {"byte_runs": "Byte changes", "xbe_grow": "SPECIAL executable growth",
                      "file_replace": "Named file replacement", "file_grow": "Named file growth", "file_shrink": "Named file shrink"}
            lines.append("Disc operations: " + ", ".join(labels.get(op["name"], op["name"]) for op in info["patch_operations"]))
        if info.get("result", {}).get("size", base["size"]) != base["size"]:
            lines.append(f"Disc size: {_human(base['size'])} → {_human(info['result']['size'])}.")
        if base["is_retail"]:
            lines.append("Base: the retail disc image.")
        elif base.get("is_retail_equivalent"):
            lines.append("Base: retail-equivalent. The author built on a working copy, but every byte this "
                         "patch changes was proved against the retail disc image, so a retail dump takes it.")
        else:
            lines.append(f"Base: NOT the retail disc image ({base['label'] or 'custom'}); your copy must match that base.")
        if info["regions"]:
            lines.append("Touches: " + ", ".join(f"{region['name']} ({region['runs']} run(s), {_human(region['bytes'])})"
                                                 for region in info["regions"]))
        if info["recipe_lines"]:
            lines.append("Recipe: " + "; ".join(info["recipe_lines"]))
        if info["assets"]:
            lines.append(f"Assets ({len(info['assets'])}, {_human(info['assets_bytes'])}): "
                         + ", ".join(asset["path"].split("/", 1)[1] for asset in info["assets"]))
        else:
            lines.append("Assets: none bundled")
        return "\n".join(lines)

    def apply_check_report(self, report: dict) -> None:
        """Populate from a check report (also used by tests)."""

        self.last_check = report
        self._check_state = report["state"]
        word = {"ready": "Ready to apply", "applied": "Already installed",
                "mismatch": "Doesn't match this mod's required starting disc"}.get(
            str(report["state"]), str(report["state"]).replace("_", " ").capitalize())
        self.check_status.setText(f"{word} — {report['explanation']}")
        self._refresh()

    # ------------------------------------------------------------------ choosers
    def _choose_file(self, field: QLineEdit, title: str, filters: str) -> Path | None:
        chosen, _f = QFileDialog.getOpenFileName(self, title, str(Path.home()), filters)
        if not chosen:
            return None
        field.setText(chosen)
        return Path(chosen)

    def _choose_base(self) -> None:
        self._choose_file(self.base_field, "Choose the base disc image", IMAGE_FILTER)

    def _choose_patched(self) -> None:
        self._choose_file(self.patched_field, "Choose the patched copy", IMAGE_FILTER)

    def _choose_retail(self) -> None:
        self._choose_file(self.retail_field, "Choose a retail disc image to prove the patch against", IMAGE_FILTER)

    def _choose_project(self) -> None:
        self._choose_file(self.project_field, "Choose a studio project to embed", PROJECT_FILTER)

    def _choose_assets(self) -> None:
        chosen, _f = QFileDialog.getOpenFileNames(self, "Choose source files to bundle", str(Path.home()), ASSET_FILTER)
        if chosen:
            self.set_assets(self._asset_paths + [Path(item) for item in chosen])

    def _remove_selected_assets(self) -> None:
        rows = sorted({index.row() for index in self.assets_list.selectedIndexes()}, reverse=True)
        for row in rows:
            del self._asset_paths[row]
        self.set_assets(self._asset_paths)

    def _choose_out(self) -> None:
        suggested = (self.name_field.text().strip() or "my-edits").replace("/", "-") + modpack.EXTENSION
        chosen, _f = QFileDialog.getSaveFileName(self, "Save the mod file as", suggested, PACK_FILTER)
        if chosen:
            if not chosen.casefold().endswith(modpack.EXTENSION):
                chosen += modpack.EXTENSION
            self.out_field.setText(chosen)

    def _choose_pack(self) -> None:
        path = self._choose_file(self.pack_field, "Choose a mod file (.2k5patch)", PACK_FILTER)
        if path is not None:
            self.load_pack(path)

    def _choose_source(self) -> None:
        if self._choose_file(self.source_field, "Choose your game disc (.iso)", IMAGE_FILTER) is not None:
            self._check_state = None
            self.check_status.setText("")
            self.describe_source()
            self._refresh()
            if self._pack is not None:
                self.start_check()

    def describe_source(self) -> str:
        """Name the disc image in the source field (also used by tests)."""

        path = self.source_field.text().strip()
        text = ""
        if path:
            try:
                from mod_editor.core import nfl2k5_disc_identity as identity
                found = identity.identify(path)
            except Exception:  # noqa: BLE001 -- naming the disc must never break the panel
                found = None
            if found is not None:
                text = ("Your image: " + found.line()
                        + ("" if found.can_take_a_byte_run_patch
                           else " Use the Build tab to make this mod yourself instead."))
        self.source_identity.setText(text)
        return text

    def _choose_target(self) -> None:
        chosen, _f = QFileDialog.getSaveFileName(self, "Where should the new disc go?",
                                                 "ESPN NFL 2K5 (patched).xiso.iso", IMAGE_FILTER)
        if chosen:
            self.target_field.setText(mod_build.image_target_path(chosen))

    # ------------------------------------------------------------------ background work
    def _start(self, operation: Callable[[modpack.ProgressSink], object], done: Callable[[object], None], failed: Callable[[str], None]) -> None:
        if self.busy:
            return
        self.busy = True
        self._refresh()
        task = _Task(operation)
        task.signals.progress.connect(self._on_progress)

        def finish(result: object) -> None:
            self.busy = False
            self._task = None
            self.progress_label.setText("")
            done(result)
            self._refresh()

        def fail(message: str) -> None:
            self.busy = False
            self._task = None
            self.progress_label.setText("")
            failed(message)
            self._refresh()

        task.signals.finished.connect(bound(self, finish))
        task.signals.failed.connect(bound(self, fail))
        self._task = task
        self._pool.start(task)

    def _on_progress(self, stage: str, done: int, total: int) -> None:
        if total:
            self.progress_label.setText(f"{stage}: {done * 100 // total}%")
        else:
            self.progress_label.setText(f"{stage}…")

    def start_export(self) -> None:
        base = Path(self.base_field.text())
        patched = Path(self.patched_field.text())
        out = Path(self.out_field.text())
        if out.suffix.casefold() != modpack.EXTENSION:
            out = out.with_name(out.name + modpack.EXTENSION)
            self.out_field.setText(str(out))
        meta = {
            "name": self.name_field.text(),
            "author": self.author_field.text(),
            "version": self.version_field.text(),
            "description": self.description_field.toPlainText(),
            "assets": list(self._asset_paths),
            "project": self.project_field.text().strip() or None,
            "retail_image": self.retail_field.text().strip() or None,
        }
        overwrite = False
        if out.exists():
            if not self._confirm("Replace the mod file?", f"{out} already exists. Replace it?"):
                return
            overwrite = True
        self.export_status.setText("Comparing the two images…")

        def operation(progress: modpack.ProgressSink) -> object:
            return modpack.export(base, patched, out, meta, overwrite=overwrite, progress=progress)

        self._start(operation, self._export_done, self._export_failed)

    def _export_done(self, receipt: object) -> None:
        assert isinstance(receipt, dict)
        self.last_export = receipt
        base = receipt["base"]
        text = (f"Wrote {Path(receipt['pack']).name} ({_human(receipt['pack_bytes'])}): {receipt['runs']} run(s), "
                f"{_human(receipt['bytes'])} changed, {len(receipt['assets'])} asset(s), in {receipt['elapsed_seconds']} s. "
                + ("Base is the retail disc image." if base["is_retail"]
                   else "Base is retail-equivalent: every changed byte was proved against the retail disc image."
                   if base.get("is_retail_equivalent")
                   else "Base is NOT the retail disc image: only people with the same base can apply this."))
        if receipt["recipe_lines"]:
            text += " Recipe: " + "; ".join(receipt["recipe_lines"]) + "."
        self.export_status.setText(text)
        self._notify("info", "Mod file written", f"{receipt['pack']}\n\nShare this file, never the disc.")

    def _export_failed(self, message: str) -> None:
        self.export_status.setText(f"Couldn't export the mod file: {message}")
        self._notify("error", "Couldn't export the mod file", message)

    def start_check(self) -> None:
        if self._pack is None or not self.source_field.text():
            return
        pack = self._pack
        source = Path(self.source_field.text())
        self.check_status.setText("Checking every run against your disc image…")

        def operation(progress: modpack.ProgressSink) -> object:
            return modpack.check(pack, source, progress=progress)

        self._start(operation, self._check_done, self._check_failed)

    def _check_done(self, report: object) -> None:
        assert isinstance(report, dict)
        self.apply_check_report(report)

    def _check_failed(self, message: str) -> None:
        self._check_state = None
        self.check_status.setText(f"Couldn't check this mod: {message}")
        self._refresh()

    def start_apply(self) -> None:
        if self._pack is None or self._check_state != "ready":
            return
        pack = self._pack
        source = Path(self.source_field.text())
        target = Path(self.target_field.text())
        if target.exists() and target.resolve() == source.resolve():
            self._notify("error", "Same file", "Source and output are the same file. Fix: choose a different output file.")
            return
        overwrite = target.exists()
        if not self._confirm(
            "Make disc with this mod?",
            f"Mod: {pack.manifest.name}\nSource (unchanged): {source}\n"
            + (f"Replace existing disc copy: {target}" if overwrite else f"New disc: {target}")
            + f"\n\nThis copies the whole disc and writes {len(pack.manifest.patch_operations) or len(pack.manifest.runs)} verified change(s) "
              f"({_human(pack.manifest.total_bytes)}) into the copy.\n\n" + XEMU_LINE,
        ):
            return
        self.apply_status.setText("Copying your disc image and applying the patch…")

        def operation(progress: modpack.ProgressSink) -> object:
            return modpack.apply(pack, source, target, overwrite=overwrite, progress=progress)

        self._start(operation, self._apply_done, self._apply_failed)

    def _apply_done(self, receipt: object) -> None:
        assert isinstance(receipt, dict)
        self.last_apply = receipt
        target = receipt["target"]
        result = ("byte-identical to the author's patched image" if target["matches_author_result"]
                  else "every run verified; the rest of the file is your own base"
                  if target["matches_author_result"] is False else "every run verified")
        self.apply_status.setText(f"Disc ready: {Path(target['path']).name} in {receipt['elapsed_seconds']} s; {result}.")
        self._check_state = None
        self.disc_written.emit(str(target["path"]))
        self._notify("info", "Disc ready", f"{target['path']}\n\nOpen it in xemu. " + XEMU_LINE)

    def _apply_failed(self, message: str) -> None:
        self.apply_status.setText(f"Couldn't make the disc: {message}")
        self._notify("error", "Couldn't make the disc with this mod", message)


__all__ = ["SharePanel"]

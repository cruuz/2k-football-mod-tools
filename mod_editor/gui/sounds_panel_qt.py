"""Sounds tab: put your own WAV into a rotating SFX bank slot or a standalone cue of a copied disc.

Sits next to Audio Cues in the Audio workspace.  It reads the three rotating
sound banks (``sfx_game`` hits/pads/ball/snap, ``sfx_safe`` whistles and crowd
reactions, ``QB_at_line`` cadence) straight out of any NFL 2K5 disc image plus
the audited catalog of the 850 standalone ``AUDO`` cues (chants, PA, menu/UI,
music stings), lists them with their allocations, exports any of them to WAV,
previews how a replacement WAV fits (padded with silence or fade-trimmed to
every sub-bank's exact allocation) and writes it into a COPY of the disc.  The
source image is never modified.  Everything the tab does is the same as
``tools/nfl2k5_soundbank_swap.py`` and ``tools/nfl2k5_audo_swap.py``.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mod_editor.gui.ux_text import XEMU_LINE, Details, plain_failure, show_operation_error, suggest_copy_name
from mod_editor.gui.task_delivery import bound

IMAGE_FILTER = "Disc images (*.iso *.xiso);;All files (*)"
WAV_FILTER = "WAV audio (*.wav);;All files (*)"
STANDALONE = "audo"
STANDALONE_LABEL = "Standalone cues"
DEFAULT_CONTAINERS = ("sfx_game", "sfx_safe", "QB_at_line")
CONTAINER_HINTS = {
    "sfx_game": "in-game SFX: hits, pads, helmets, grunts, ball, snap, kick (rotates every play)",
    "sfx_safe": "whistles, crowd cheer/aww front+rear layers, play-call menu (rotates at play end)",
    "QB_at_line": "QB cadence: down / set / colour / hut / audible (0-19 home voice, 20-39 away)",
    STANDALONE: "850 standalone AUDO cues: chants, PA, menu/UI clicks, music stings, crib, huddle claps",
}
DEFAULT_FADE_MS = 10.0
DEFAULT_RETAIL_PACKS = (Path(os.environ["NFL2K5_RETAIL_PACKS"]) if os.environ.get("NFL2K5_RETAIL_PACKS") else None)   # extracted retail packs, developer machines only


class SoundsError(ValueError):
    """Anything the panel must refuse before it touches a disc."""


def soundbank_module():
    tools = Path(__file__).resolve().parents[2] / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module("nfl2k5_soundbank_swap")


def audo_module():
    soundbank_module()
    return importlib.import_module("nfl2k5_audo_swap")


# ------------------------------------------------------------------ catalog model
@dataclass(frozen=True)
class Allocation:
    """One recording's exact shape: a sub-bank of a bank slot, or one standalone record."""

    label: str
    channels: int
    sample_rate: int
    frame_count: int

    @property
    def seconds(self) -> float:
        return self.frame_count / self.sample_rate


@dataclass(frozen=True)
class SoundRow:
    """One replaceable sound: a bank slot (all its sub-banks) or one standalone AUDO record."""

    container: str
    key: str
    name: str
    allocations: tuple[Allocation, ...]
    package: str = ""
    duplicate_names: int = 1

    @property
    def is_standalone(self) -> bool:
        return self.container == STANDALONE

    @property
    def variants(self) -> int:
        return len(self.allocations)

    @property
    def channels(self) -> int:
        return self.allocations[0].channels

    @property
    def sample_rates(self) -> tuple[int, ...]:
        return tuple(sorted({allocation.sample_rate for allocation in self.allocations}))

    @property
    def seconds_min(self) -> float:
        return min(allocation.seconds for allocation in self.allocations)

    @property
    def seconds_max(self) -> float:
        return max(allocation.seconds for allocation in self.allocations)

    @property
    def unit(self) -> str:
        return "record" if self.is_standalone else "sub-bank"

    def label(self) -> str:
        channels = "mono" if self.channels == 1 else "stereo"
        rates = "/".join(str(rate) for rate in self.sample_rates)
        if self.seconds_min == self.seconds_max:
            seconds = f"{self.seconds_min:.3f} s"
        else:
            seconds = f"{self.seconds_min:.3f}..{self.seconds_max:.3f} s"
        if self.is_standalone:
            dup = f"   ×{self.duplicate_names} same-name records" if self.duplicate_names > 1 else ""
            return f"{self.name:<26} {self.package:<48} {channels} {rates} Hz   {seconds}{dup}"
        return f"{self.name:<26} {self.variants:>3} sub-banks   {channels} {rates} Hz   {seconds}"

    def matches(self, query: str) -> bool:
        query = query.strip().casefold()
        if not query:
            return True
        haystack = " ".join((self.name, self.key, self.package, self.container)).casefold()
        return all(word in haystack for word in query.split())


@dataclass(frozen=True)
class SoundCatalog:
    """Everything the tab can list for one source disc (cached per source path)."""

    source: Path
    banks: dict[str, tuple[SoundRow, ...]]
    bank_facts: dict[str, dict[str, object]]
    standalone: tuple[SoundRow, ...]
    standalone_error: str = ""

    def containers(self) -> list[str]:
        return list(self.banks) + [STANDALONE]

    def rows(self, container: str) -> tuple[SoundRow, ...]:
        if container == STANDALONE:
            return self.standalone
        return self.banks.get(container, ())

    def row(self, container: str, key: str) -> SoundRow | None:
        for row in self.rows(container):
            if row.key == key:
                return row
        return None

    @property
    def total(self) -> int:
        return sum(len(rows) for rows in self.banks.values()) + len(self.standalone)


def read_catalog(source: Path, *, banks=None, audo_records=None) -> SoundCatalog:
    """Bank slots from the disc (via the tools' parser) plus the standalone AUDO catalog."""

    sb = soundbank_module()
    au = audo_module()
    source = Path(source)
    pins = sb.PINNED_BANKS if banks is None else tuple(banks)
    bank_rows: dict[str, tuple[SoundRow, ...]] = {}
    facts: dict[str, dict[str, object]] = {}
    with sb.SoundBanks(source, banks=pins) as disc:
        for key, bank in disc.banks.items():
            rows: list[SoundRow] = []
            for slot in bank.slots:
                allocations = []
                for subbank in range(bank.subbank_count):
                    payload = bank.payload(slot.index, subbank)
                    allocations.append(Allocation(f"sb{subbank:02d}", payload.channels, payload.sample_rate,
                                                  payload.frame_count))
                rows.append(SoundRow(key, slot.name, slot.name, tuple(allocations)))
            bank_rows[key] = tuple(rows)
            facts[key] = bank.describe()
    standalone: tuple[SoundRow, ...] = ()
    error = ""
    try:
        records = au.load_catalog() if audo_records is None else tuple(audo_records)
        standalone = tuple(
            SoundRow(STANDALONE, record.key, record.name,
                     (Allocation(record.key, record.channels, record.sample_rate, record.frame_count),),
                     record.package, record.duplicate_name_count)
            for record in records
        )
    except Exception as exc:  # noqa: BLE001 - the banks are still usable without the catalog
        error = f"{type(exc).__name__}: {exc}"
    return SoundCatalog(source, bank_rows, facts, standalone, error)


# ------------------------------------------------------------------ fit preview
@dataclass(frozen=True)
class FitPreview:
    clip_channels: int
    clip_rate: int
    clip_frames: int
    rows: tuple[tuple[Allocation, int, int], ...]   # (allocation, padded frames, trimmed frames)

    @property
    def clip_seconds(self) -> float:
        return self.clip_frames / self.clip_rate

    @property
    def padded(self) -> list[tuple[Allocation, int]]:
        return [(allocation, pad) for allocation, pad, _trim in self.rows if pad > 0]

    @property
    def trimmed(self) -> list[tuple[Allocation, int]]:
        return [(allocation, trim) for allocation, _pad, trim in self.rows if trim > 0]

    @property
    def exact(self) -> int:
        return sum(1 for _allocation, pad, trim in self.rows if pad == 0 and trim == 0)


def preview_fit(row: SoundRow, clip_channels: int, clip_rate: int, clip_frames: int) -> FitPreview:
    """Per allocation: how many frames of silence are padded, or trimmed, exactly as the tools fit."""

    if clip_frames <= 0 or clip_rate <= 0:
        raise SoundsError("the clip is empty")
    rows: list[tuple[Allocation, int, int]] = []
    for allocation in row.allocations:
        if allocation.sample_rate == clip_rate:
            shaped = clip_frames
        else:
            shaped = max(1, int(round(clip_frames * allocation.sample_rate / clip_rate)))
        rows.append((allocation, max(0, allocation.frame_count - shaped), max(0, shaped - allocation.frame_count)))
    return FitPreview(clip_channels, clip_rate, clip_frames, tuple(rows))


def _span(values: list[float]) -> str:
    low, high = min(values), max(values)
    return f"{low:.3f} s" if abs(high - low) < 0.0005 else f"{low:.3f}..{high:.3f} s"


def fit_summary(row: SoundRow, preview: FitPreview, *, fade_ms: float = DEFAULT_FADE_MS) -> str:
    """One line: clip duration vs the slot seconds of every sub-bank, pad / trim / exact."""

    channels = "mono" if preview.clip_channels == 1 else "stereo"
    total = row.variants
    unit = row.unit
    plural = f"{unit}s"
    head = (f"Clip {preview.clip_seconds:.3f} s ({channels}, {preview.clip_rate} Hz) → {row.name} "
            f"holds {_span([a.seconds for a in row.allocations])}")
    parts: list[str] = []
    padded, trimmed = preview.padded, preview.trimmed
    if padded:
        where = f" in {len(padded)} of {total} {plural}" if total > 1 else ""
        parts.append(f"pad {_span([pad / a.sample_rate for a, pad in padded])} of silence{where}")
    if trimmed:
        where = f" in {len(trimmed)} of {total} {plural}" if total > 1 else ""
        parts.append(f"trim {_span([trim / a.sample_rate for a, trim in trimmed])} "
                     f"({fade_ms:g} ms fade-out){where}")
    if preview.exact:
        parts.append(f"exact fit in {preview.exact} of {total} {plural}" if total > 1 else "exact fit")
    conversions: list[str] = []
    slot_rates = row.sample_rates
    if any(rate != preview.clip_rate for rate in slot_rates):
        conversions.append(f"resampled {preview.clip_rate} → {'/'.join(str(r) for r in slot_rates)} Hz")
    if row.channels != preview.clip_channels:
        conversions.append("mono → stereo" if row.channels == 2 else "stereo → mono")
    text = f"{head}: {'; '.join(parts)}."
    if conversions:
        text += f" Converted: {', '.join(conversions)}."
    return text


def read_clip(path: Path) -> tuple[int, int, int]:
    """(channels, sample rate, frames) of a PCM16 WAV through the tool's reader."""

    sb = soundbank_module()
    channels, rate, pcm = sb.read_wav(Path(path))
    return channels, rate, len(pcm) // (channels * 2)


# ------------------------------------------------------------------ operations
def _standalone_selection(au, records, key: str, all_matches: bool):
    selected = au.select_records(records, keys=[key])
    if all_matches:
        selected = au.select_records(records, names=[selected[0].name])
    return selected


def _same_file(source: Path, target: Path) -> bool:
    if target.exists():
        try:
            return os.path.samefile(source, target)
        except OSError:
            return False
    return source.resolve() == target.resolve()


def _pins(sb, banks):
    return sb.PINNED_BANKS if banks is None else tuple(banks)


def perform_export(source: Path, container: str, key: str, out_dir: Path, *, subbanks=None,
                   all_matches: bool = False, banks=None, audo_records=None) -> list[dict[str, object]]:
    """Decode the selected sound (one sub-bank, every sub-bank, or record(s)) to WAV files."""

    sb = soundbank_module()
    out_dir = Path(out_dir)
    if container == STANDALONE:
        au = audo_module()
        records = au.load_catalog() if audo_records is None else tuple(audo_records)
        selected = _standalone_selection(au, records, key, all_matches)
        with au.AudoDisc(Path(source), records=records) as disc:
            return au.export_records(disc, selected, out_dir)
    with sb.SoundBanks(Path(source), banks=_pins(sb, banks)) as disc:
        payloads = disc.payloads_for(container, [key], subbanks)
        return sb.export_samples(disc, payloads, out_dir)


def receipt_path_for(target: Path) -> Path:
    name = Path(target).name
    for suffix in (".iso", ".xiso"):
        if name.lower().endswith(suffix):
            name = name[:-len(suffix)]
    return Path(target).with_name(f"{name}.sounds-receipt.json")


def perform_write(source: Path, target: Path, container: str, key: str, wav: Path,
                  retail_packs: Path | None, *, subbanks=None, all_matches: bool = False,
                  allow_trim: bool = True, strict: bool = False, banks=None, audo_records=None,
                  receipt_path: Path | None = None) -> dict[str, object]:
    """Copy the disc, then let the tool gate and write the payload(s) in the copy; save the receipt."""

    source, target, wav = Path(source), Path(target), Path(wav)
    if _same_file(source, target):
        raise SoundsError("The copy must not be the source.")
    if not source.is_file():
        raise SoundsError(f"source is not a file: {source}")
    packs = Path(retail_packs) if retail_packs and Path(retail_packs).is_dir() else None
    sb = soundbank_module()
    shutil.copyfile(source, target)
    if container == STANDALONE:
        au = audo_module()
        records = au.load_catalog() if audo_records is None else tuple(audo_records)
        selected = _standalone_selection(au, records, key, all_matches)
        # The catalog hashes gate every record (wrapper, system area, tail AND
        # payload must be retail); the packs are a second, optional comparison.
        receipt = au.replace_records(target, selected, wav, retail_packs=packs, force=False,
                                     guards=[source], allow_trim=allow_trim, fade_ms=DEFAULT_FADE_MS,
                                     strict=strict, catalog=records)
    else:
        # The banks have no catalog hashes: the extracted retail packs are the
        # only proof that the spans are still retail.  Without them the tool
        # refuses unless forced (same rule as the Commentary tab); the receipt
        # records which gate applied per payload.
        receipt = sb.replace_samples(target, container, [key], wav, subbanks=subbanks, retail_packs=packs,
                                     force=packs is None, guards=[source], allow_trim=allow_trim,
                                     fade_ms=DEFAULT_FADE_MS, strict=strict, banks=_pins(sb, banks))
    receipt["source"] = str(source)
    receipt["target"] = str(target)
    receipt["container"] = container
    receipt["selection"] = key
    path = Path(receipt_path) if receipt_path is not None else receipt_path_for(target)
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    receipt["receipt_path"] = str(path)
    return receipt


def perform_verify(target: Path, container: str, key: str, wav: Path, *, subbanks=None,
                   all_matches: bool = False, allow_trim: bool = True, banks=None, audo_records=None,
                   decoded_dir: Path | None = None) -> dict[str, object]:
    """Re-read the copy and compare every payload with the encoded WAV (the tools' ``verify``)."""

    sb = soundbank_module()
    if container == STANDALONE:
        au = audo_module()
        records = au.load_catalog() if audo_records is None else tuple(audo_records)
        selected = _standalone_selection(au, records, key, all_matches)
        return au.verify_records(Path(target), selected, Path(wav), decoded_dir=decoded_dir,
                                 allow_trim=allow_trim, fade_ms=DEFAULT_FADE_MS, catalog=records)
    return sb.verify_samples(Path(target), container, [key], Path(wav), subbanks=subbanks,
                             decoded_dir=decoded_dir, allow_trim=allow_trim, fade_ms=DEFAULT_FADE_MS,
                             banks=_pins(sb, banks))


# ------------------------------------------------------------------ background task
class _Signals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class _Task(QRunnable):
    def __init__(self, operation: Callable[[], object]) -> None:
        super().__init__()
        self.signals = _Signals()
        self._operation = operation

    def run(self) -> None:
        try:
            self.signals.finished.emit(self._operation())
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ panel
class SoundsPanel(QWidget):
    """One WAV into a rotating bank slot (every sub-bank by default) or a standalone cue, in a copy."""

    def wait_idle(self, timeout_ms: int = 30_000) -> bool:
        """Block until the background task (source load / export / write) has finished; True when idle."""
        return bool(self._pool.waitForDone(timeout_ms))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.wait_idle()
        super().closeEvent(event)

    def __init__(self, facade: object | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._facade = facade
        self._pool = QThreadPool(self)
        self._task: _Task | None = None
        self._pool.setMaxThreadCount(1)
        self._busy = False
        self._catalog: SoundCatalog | None = None
        self._catalog_cache: dict[Path, SoundCatalog] = {}
        self._clip: tuple[int, int, int] | None = None
        self._clip_error = ""
        # Tests and fixtures pin a different bank list / AUDO catalog; None = the retail pins.
        self.bank_pins = None
        self.audo_records = None
        self._target_generated = False
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Replace hits, whistles, crowd sounds, menu clicks or QB cadence with your WAV, then make a "
            "disc copy. Every sound keeps its length: a longer clip is trimmed, a shorter one is padded "
            "with silence. These selections apply to the copy made on this page. " + XEMU_LINE
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        intro_details = Details("Details")
        intro_details.add_text(
            "Three rotating SFX banks (sfx_game: hits, pads, ball, snap; sfx_safe: whistles and crowd "
            "reactions; QB_at_line: the QB cadence) and the 850 standalone cues (crowd chants, PA, menu "
            "clicks, music stings). A rotating sound is replaced in every sub-bank by default so the game "
            "cannot rotate back to the old recording. The source disc is never touched.")
        layout.addWidget(intro_details)

        source_box = QGroupBox("1. Game disc (.iso)")
        source_layout = QHBoxLayout(source_box)
        self.source_field = QLineEdit()
        self.source_field.setReadOnly(True)
        self.source_field.setPlaceholderText("Filled in when you open a disc (top right), or choose one here")
        self.source_button = QPushButton("Choose…")
        self.source_button.clicked.connect(self._choose_source)
        source_layout.addWidget(self.source_field, 1)
        source_layout.addWidget(self.source_button)
        layout.addWidget(source_box)

        pick_box = QGroupBox("2. Sound to replace")
        pick_layout = QVBoxLayout(pick_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Group"))
        self.container_combo = QComboBox()
        self.container_combo.setAccessibleName("Sound group")
        self._fill_containers(list(DEFAULT_CONTAINERS))
        self.container_combo.currentIndexChanged.connect(lambda _index: self._refill_list())
        row.addWidget(self.container_combo)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sounds by name, package or key")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search sounds")
        self.search.setToolTip("Filter the list. Press Ctrl+F to focus search from anywhere.")
        self.search.setAccessibleDescription(self.search.toolTip())
        self.search.setProperty("studioSearch", True)
        self.search.textChanged.connect(lambda _text: self._refill_list())
        row.addWidget(self.search, 1)
        pick_layout.addLayout(row)
        self.sound_list = QListWidget()
        self.sound_list.setAccessibleName("Sounds")
        # Column-shaped rows (name, sub-banks, shape, seconds) line up in a fixed-pitch
        # face, the family the shell's own monospace rule uses.  Set per item: the
        # shell stylesheet's font rule overrides a widget-level setFont.
        self._mono = QFont("DejaVu Sans Mono")
        self._mono.setStyleHint(QFont.Monospace)
        self._mono.setFixedPitch(True)
        self.sound_list.setMaximumHeight(190)
        self.sound_list.itemSelectionChanged.connect(self._sound_picked)
        pick_layout.addWidget(self.sound_list)
        row = QHBoxLayout()
        row.addWidget(QLabel("Replace in"))
        self.scope_combo = QComboBox()
        self.scope_combo.setAccessibleName("Replacement scope")
        self.scope_combo.setToolTip("Every sub-bank (default, the game rotates them each play) or one sub-bank; "
                                    "for standalone cues, this record only or every record with the same name.")
        self.scope_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        row.addWidget(self.scope_combo, 1)
        self.export_button = QPushButton("Export selected to WAV…")
        self.export_button.setToolTip("Decode the selected sound from the disc into PCM WAV files "
                                      "(one sub-bank, or every variant into a folder).")
        self.export_button.clicked.connect(self._export)
        row.addWidget(self.export_button)
        pick_layout.addLayout(row)
        self.detail_label = QLabel("Pick a sound to see its allocation.")
        self.detail_label.setWordWrap(True)
        pick_layout.addWidget(self.detail_label)
        layout.addWidget(pick_box)

        clip_box = QGroupBox("3. Your WAV")
        clip_layout = QVBoxLayout(clip_box)
        row = QHBoxLayout()
        self.audio_field = QLineEdit()
        self.audio_field.setPlaceholderText("A .wav file, mono or stereo, any rate (converted to fit the slot)")
        self.audio_field.textChanged.connect(self._clip_changed)
        row.addWidget(self.audio_field, 1)
        self.audio_button = QPushButton("Choose WAV…")
        self.audio_button.clicked.connect(self._choose_audio)
        row.addWidget(self.audio_button)
        clip_layout.addLayout(row)
        self.fit_label = QLabel("Choose a sound and a WAV to preview the fit.")
        self.fit_label.setWordWrap(True)
        self.fit_label.setAccessibleName("Fit summary")
        clip_layout.addWidget(self.fit_label)
        layout.addWidget(clip_box)

        target_box = QGroupBox("4. Save disc copy as")
        target_layout = QVBoxLayout(target_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("File"))
        self.target_field = QLineEdit()
        self.target_field.setPlaceholderText("Where the new disc goes (never the source)")
        self.target_field.textChanged.connect(self._refresh)
        self.target_field.textEdited.connect(lambda _t: setattr(self, "_target_generated", False))
        target_button = QPushButton("Choose…")
        target_button.clicked.connect(self._choose_target)
        row.addWidget(self.target_field, 1)
        row.addWidget(target_button)
        target_layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Original game files folder (checks the slot first; optional for standalone sounds)"))
        self.retail_field = QLineEdit(str(DEFAULT_RETAIL_PACKS) if DEFAULT_RETAIL_PACKS is not None and DEFAULT_RETAIL_PACKS.is_dir() else "")
        self.retail_field.setToolTip("An extracted original vc_53450030 folder. Bank sounds can only be checked against "
                                     "the original through it; standalone sounds are always checked by the catalog hashes.")
        row.addWidget(self.retail_field, 1)
        target_layout.addLayout(row)
        layout.addWidget(target_box)

        row = QHBoxLayout()
        self.write_button = QPushButton("Make disc with this sound")
        self.write_button.clicked.connect(self._write)
        row.addWidget(self.write_button)
        self.verify_button = QPushButton("Check the disc")
        self.verify_button.setToolTip("Re-read the copy and check every payload holds exactly the encoded WAV.")
        self.verify_button.clicked.connect(self._verify)
        row.addWidget(self.verify_button)
        self.status_label = QLabel("Open your game disc (top right), or choose one above, to begin.")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Sounds status")
        row.addWidget(self.status_label, 1)
        layout.addLayout(row)
        layout.addStretch(1)
        self._refresh()

    def _fill_containers(self, keys: list[str]) -> None:
        self.container_combo.blockSignals(True)
        self.container_combo.clear()
        names = {"sfx_game": "In-game effects (sfx_game)", "sfx_safe": "Whistles & crowd (sfx_safe)",
                 "QB_at_line": "QB cadence (QB_at_line)"}
        for key in keys:
            self.container_combo.addItem(names.get(key, key), key)
            self.container_combo.setItemData(self.container_combo.count() - 1,
                                             CONTAINER_HINTS.get(key, ""), Qt.ToolTipRole)
        self.container_combo.addItem(STANDALONE_LABEL, STANDALONE)
        self.container_combo.setItemData(self.container_combo.count() - 1,
                                         CONTAINER_HINTS[STANDALONE], Qt.ToolTipRole)
        self.container_combo.blockSignals(False)

    # ------------------------------------------------------------------ state
    @property
    def source_loaded(self) -> bool:
        return self._catalog is not None

    def current_container(self) -> str:
        return str(self.container_combo.currentData() or "")

    def apply_catalog(self, path: Path, catalog: SoundCatalog) -> None:
        """Populate from a catalog (also used by tests and the screenshot tool)."""

        self._catalog = catalog
        self._catalog_cache[Path(path)] = catalog
        self.source_field.setText(str(path))
        if not self.target_field.text().strip() or self._target_generated:
            self.target_field.setText(suggest_copy_name(path, suffix="sounds"))
            self._target_generated = True
        current = self.current_container()
        self._fill_containers(list(catalog.banks))
        index = self.container_combo.findData(current)
        self.container_combo.setCurrentIndex(index if index >= 0 else 0)
        banks = ", ".join(f"{key} ({len(rows)} slots × {catalog.bank_facts[key].get('subbank_count')} sub-banks)"
                          for key, rows in catalog.banks.items())
        standalone = (f"{len(catalog.standalone)} standalone cues" if catalog.standalone
                      else f"standalone catalog unavailable ({catalog.standalone_error})")
        self.status_label.setText(f"Read {banks}; {standalone}. Pick a sound.")
        self._refill_list()

    def apply_failure(self, path: Path, message: str) -> None:
        self._catalog = None
        self.source_field.setText(str(path))
        self.sound_list.clear()
        self.status_label.setText(f"Not an NFL 2K5 disc image (no sound banks found): {message}")
        self._refresh()

    def load_source(self, path: Path) -> None:
        """Read the catalog in the background (cached per source path)."""

        path = Path(path)
        cached = self._catalog_cache.get(path)
        if cached is not None:
            self.apply_catalog(path, cached)
            return
        self.status_label.setText("Reading the sound banks and the cue catalog…")
        pins, records = self.bank_pins, self.audo_records

        def operation() -> object:
            return read_catalog(path, banks=pins, audo_records=records)

        def done(result: object) -> None:
            assert isinstance(result, SoundCatalog)
            self.apply_catalog(path, result)

        def failed(message: str) -> None:
            self.apply_failure(path, message)

        self._run(operation, done, failed)

    def visible_rows(self) -> list[SoundRow]:
        return [self.sound_list.item(index).data(Qt.UserRole) for index in range(self.sound_list.count())]

    def current_row(self) -> SoundRow | None:
        items = self.sound_list.selectedItems()
        if not items:
            return None
        row = items[0].data(Qt.UserRole)
        return row if isinstance(row, SoundRow) else None

    def select_sound(self, container: str, key: str) -> bool:
        index = self.container_combo.findData(container)
        if index < 0:
            return False
        self.container_combo.setCurrentIndex(index)
        for position in range(self.sound_list.count()):
            row = self.sound_list.item(position).data(Qt.UserRole)
            if isinstance(row, SoundRow) and row.key == key:
                self.sound_list.setCurrentRow(position)
                return True
        return False

    def scope(self) -> tuple[list[int] | None, bool]:
        """(sub-banks to write or None for all, every same-name standalone record?)."""

        row = self.current_row()
        index = self.scope_combo.currentIndex()
        if row is None or index <= 0:
            return None, False
        if row.is_standalone:
            return None, True
        return [index - 1], False

    def set_replacement(self, path: Path) -> None:
        self.audio_field.setText(str(path))

    def _refill_list(self) -> None:
        self.sound_list.clear()
        if self._catalog is None:
            self._refresh()
            return
        query = self.search.text()
        for row in self._catalog.rows(self.current_container()):
            if not row.matches(query):
                continue
            item = QListWidgetItem(row.label())
            item.setFont(self._mono)
            item.setData(Qt.UserRole, row)
            item.setToolTip(f"{row.container} · {row.key}")
            self.sound_list.addItem(item)
        self._sound_picked()

    def _sound_picked(self) -> None:
        row = self.current_row()
        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        if row is None:
            self.detail_label.setText("Pick a sound to see its allocation.")
        elif row.is_standalone:
            self.scope_combo.addItem("This record only")
            if row.duplicate_names > 1:
                self.scope_combo.addItem(f"Every record named {row.name} ({row.duplicate_names})")
            allocation = row.allocations[0]
            self.detail_label.setText(
                f"{row.name} · {row.package} · {row.key}: {'mono' if row.channels == 1 else 'stereo'} "
                f"{allocation.sample_rate} Hz, {allocation.frame_count:,} frames = {allocation.seconds:.3f} s. "
                "The wrapper, name and descriptor stay; only the payload bytes are replaced."
            )
        else:
            self.scope_combo.addItem(f"All {row.variants} sub-banks (the game rotates them every play)")
            for allocation in row.allocations:
                self.scope_combo.addItem(f"Sub-bank {allocation.label[2:]} only ({allocation.seconds:.3f} s)")
            self.detail_label.setText(
                f"{row.name} in {row.container}: {row.variants} rotating recordings, "
                f"{'mono' if row.channels == 1 else 'stereo'} {'/'.join(str(r) for r in row.sample_rates)} Hz, "
                f"{row.seconds_min:.3f}..{row.seconds_max:.3f} s per sub-bank. Replacing writes all "
                f"{row.variants} unless one sub-bank is chosen below."
            )
        self.scope_combo.blockSignals(False)
        self._update_fit()
        self._refresh()

    def _clip_changed(self, text: str) -> None:
        self._clip = None
        self._clip_error = ""
        path = Path(text.strip()) if text.strip() else None
        if path is not None and path.is_file():
            try:
                self._clip = read_clip(path)
            except Exception as exc:  # noqa: BLE001 - shown in the fit line
                self._clip_error = f"{type(exc).__name__}: {exc}"
        self._update_fit()
        self._refresh()

    def _update_fit(self) -> None:
        row = self.current_row()
        if self._clip_error:
            self.fit_label.setText(f"Cannot read the WAV: {self._clip_error}")
            return
        if row is None or self._clip is None:
            self.fit_label.setText("Choose a sound and a WAV to preview the fit.")
            return
        channels, rate, frames = self._clip
        try:
            self.fit_label.setText(fit_summary(row, preview_fit(row, channels, rate, frames)))
        except SoundsError as exc:
            self.fit_label.setText(f"Cannot fit the clip: {exc}")

    def ready(self) -> bool:
        target = self.target_field.text().strip()
        source = self.source_field.text().strip()
        return (self.source_loaded and self.current_row() is not None and self._clip is not None
                and bool(target) and Path(target) != Path(source))

    def _refresh(self) -> None:
        target = self.target_field.text().strip()
        source = self.source_field.text().strip()
        different = bool(target) and bool(source) and Path(target) != Path(source)
        self.write_button.setEnabled(self.ready() and not self._busy)
        self.verify_button.setEnabled(not self._busy and self.current_row() is not None and self._clip is not None
                                      and different and Path(target).is_file())
        self.export_button.setEnabled(not self._busy and self.source_loaded and self.current_row() is not None)
        self.source_button.setEnabled(not self._busy)
        self.audio_button.setEnabled(not self._busy)

    # ------------------------------------------------------------------ actions
    def _choose_source(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose your game disc (.iso)", str(Path.home()), IMAGE_FILTER)
        if chosen:
            self.load_source(Path(chosen))

    def _choose_audio(self) -> None:
        chosen, _f = QFileDialog.getOpenFileName(self, "Choose the replacement WAV", str(Path.home()), WAV_FILTER)
        if chosen:
            self.audio_field.setText(chosen)

    def _choose_target(self) -> None:
        chosen, _f = QFileDialog.getSaveFileName(self, "Where should the new disc go?",
                                                 "ESPN NFL 2K5 (sounds).xiso.iso", IMAGE_FILTER)
        if chosen:
            self.target_field.setText(chosen)
            self._target_generated = False

    def _export(self) -> None:
        row = self.current_row()
        if row is None or self._catalog is None:
            return
        chosen = QFileDialog.getExistingDirectory(self, "Folder for the exported WAV files", str(Path.home()))
        if not chosen:
            return
        source = self._catalog.source
        subbanks, all_matches = self.scope()
        pins, records = self.bank_pins, self.audo_records
        out = Path(chosen)
        self.status_label.setText(f"Exporting {row.name}…")

        def operation() -> object:
            return perform_export(source, row.container, row.key, out, subbanks=subbanks,
                                  all_matches=all_matches, banks=pins, audo_records=records)

        def done(result: object) -> None:
            assert isinstance(result, list)
            self.status_label.setText(f"Exported {len(result)} WAV file(s) of {row.name} to {out} (manifest.json alongside).")
            self._refresh()

        self._run(operation, done, self._failed)

    def _write(self) -> None:
        row = self.current_row()
        if row is None or self._catalog is None or self._clip is None:
            return
        source = self._catalog.source
        target = Path(self.target_field.text().strip())
        if _same_file(source, target):
            QMessageBox.warning(self, "Same file", "Source and output are the same file. Fix: choose a different output file.")
            return
        wav = Path(self.audio_field.text().strip())
        retail = Path(self.retail_field.text().strip()) if self.retail_field.text().strip() else None
        packs_ok = retail is not None and retail.is_dir()
        subbanks, all_matches = self.scope()
        if row.is_standalone:
            what = (f"every record named {row.name} ({row.duplicate_names})" if all_matches
                    else f"{row.name} ({row.package})")
            gate = ("catalog hashes" + (" + retail packs" if packs_ok else "")
                    + ": wrapper, name, descriptor and payload must still be retail")
        else:
            what = (f"{row.name} in {row.container}, sub-bank {subbanks[0]}" if subbanks
                    else f"{row.name} in {row.container}, all {row.variants} sub-banks")
            gate = ("retail packs: every span is compared with the retail bytes first" if packs_ok
                    else "NO retail packs folder: the bank spans are written without a retail check")
        answer = QMessageBox.question(
            self, "Make disc with this sound?",
            f"Source (unchanged): {source}\n"
            + (f"Replace existing disc copy: {target}" if target.exists() else f"New disc: {target}")
            + f"\n\n{what} will be replaced with {wav.name}.\n{self.fit_label.text()}\n\nCheck before writing — {gate}."
              "\n\n" + XEMU_LINE,
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Ok:
            return
        pins, records = self.bank_pins, self.audo_records

        def operation() -> object:
            return perform_write(source, target, row.container, row.key, wav, retail, subbanks=subbanks,
                                 all_matches=all_matches, banks=pins, audo_records=records)

        self.status_label.setText("Copying the disc image and writing the sound…")
        self._run(operation, self._done, self._failed)

    def _verify(self) -> None:
        row = self.current_row()
        if row is None or self._clip is None:
            return
        target = Path(self.target_field.text().strip())
        wav = Path(self.audio_field.text().strip())
        subbanks, all_matches = self.scope()
        pins, records = self.bank_pins, self.audo_records
        self.status_label.setText(f"Verifying {row.name} in {target.name}…")

        def operation() -> object:
            return perform_verify(target, row.container, row.key, wav, subbanks=subbanks,
                                  all_matches=all_matches, banks=pins, audo_records=records)

        def done(result: object) -> None:
            assert isinstance(result, dict)
            count = result.get("payload_count", result.get("record_count"))
            if result.get("all_match"):
                self.status_label.setText(f"Verified: all {count} payload(s) of {row.name} in {target.name} "
                                          f"hold exactly the encoded {wav.name}.")
            else:
                bad = [r.get("payload", r.get("key")) for r in result.get("payloads", [])
                       if not r.get("matches_encoded_clip")]
                self.status_label.setText(f"Mismatch: {len(bad)} of {count} payload(s) in {target.name} do not hold "
                                          f"{wav.name}: {', '.join(str(b) for b in bad[:6])}")
            self._refresh()

        self._run(operation, done, self._failed)

    def _run(self, operation: Callable[[], object], done: Callable[[object], None],
             failed: Callable[[str], None]) -> None:
        task = _Task(operation)

        def finish_done(result: object) -> None:
            self._busy = False
            done(result)

        def finish_failed(message: str) -> None:
            self._busy = False
            failed(message)

        task.signals.finished.connect(bound(self, finish_done))
        task.signals.failed.connect(bound(self, finish_failed))
        self._task = task
        self._busy = True
        self._refresh()
        self._pool.start(task)

    def _done(self, receipt: object) -> None:
        assert isinstance(receipt, dict)
        target = Path(str(receipt.get("target")))
        rows = receipt.get("payloads") or []
        gates = sorted({str(r.get("retail_gate")) for r in rows})
        padded = sum(1 for r in rows if r.get("padded_silence_frames"))
        trimmed = sum(1 for r in rows if r.get("trimmed_frames"))
        snr = [r.get("encode_snr_db") for r in rows if isinstance(r.get("encode_snr_db"), (int, float))]
        self.status_label.setText(
            f"Written: {target.name}. {len(rows)} payload(s) of {receipt.get('selection')} replaced "
            f"({padded} padded, {trimmed} trimmed), gate={'/'.join(gates)}, "
            f"SNR {min(snr):.1f}..{max(snr):.1f} dB. Read-back verified. Receipt: "
            f"{Path(str(receipt.get('receipt_path'))).name}"
            if snr else
            f"Written: {target.name}. {len(rows)} payload(s) replaced. Receipt: "
            f"{Path(str(receipt.get('receipt_path'))).name}"
        )
        QMessageBox.information(self, "Disc ready",
                                f"{target}\n\nOpen it in xemu. " + XEMU_LINE)
        self._refresh()

    def _failed(self, message: str) -> None:
        self.status_label.setText(plain_failure("finish that", message))
        show_operation_error(self, "finish that", message)
        self._refresh()


__all__ = [
    "Allocation",
    "FitPreview",
    "STANDALONE",
    "SoundCatalog",
    "SoundRow",
    "SoundsError",
    "SoundsPanel",
    "fit_summary",
    "perform_export",
    "perform_verify",
    "perform_write",
    "preview_fit",
    "read_catalog",
    "read_clip",
    "receipt_path_for",
]

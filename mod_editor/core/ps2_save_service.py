"""Qt-free service backing the PS2 Save Editor.

The GUI never talks to the command-line tools directly.  This module is the
seam between them: it owns an open save, exposes it as plain rows a table can
render, validates edits the way the writer does, and performs the write plus
its independent verification in one call.  Everything here is standard
library, so the whole thing is unit-testable without a display.

Capacities are reported in **characters** rather than bytes.  A name slot
stores UTF-16LE text plus a two-byte terminator, so a slot of ``n`` bytes
holds ``(n - 2) // 2`` characters -- that is the number a person editing a
roster actually needs, and doing the conversion here keeps it out of the
widget layer.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import errno
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable
import sys

from .errors import ValidationError
from .platform_compat import publish_no_replace

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_save as save_lib  # noqa: E402
import nfl2k5_ps2_save_verify as verify_lib  # noqa: E402


@dataclass(frozen=True)
class SaveSummary:
    """What the editor shows about the currently open save."""

    directory: str
    kind: str
    payload_bytes: int
    checksum_valid: bool
    player_count: int

    @property
    def headline(self) -> str:
        state = "checksum OK" if self.checksum_valid else "checksum MISMATCH"
        return (
            f"{self.directory} — {self.kind} · "
            f"{self.player_count:,} players · {state}"
        )


@dataclass(frozen=True)
class PlayerRow:
    """One editable player, as the table displays it."""

    index: int
    first: str
    last: str
    first_capacity: int   # characters, not bytes
    last_capacity: int

    def capacity_for(self, field: str) -> int:
        return self.first_capacity if field == "first" else self.last_capacity

    def value_for(self, field: str) -> str:
        return self.first if field == "first" else self.last


@dataclass(frozen=True)
class WriteResult:
    """Outcome of writing a save and independently verifying it."""

    output: Path
    verified: bool
    changed_bytes: int
    edits: int
    detail: str


def _characters(capacity_bytes: int) -> int:
    """UTF-16LE slot capacity in characters, excluding the terminator."""
    return max(0, (capacity_bytes - 2) // 2)


class Ps2SaveService:
    """Open, edit, and write one PS2 save.

    The service keeps the *original* save alongside the working copy so a
    write can be verified against a clean baseline, and so the editor can
    discard changes without touching the user's file.
    """

    #: Accepted inputs, for the GUI's file dialog.
    OPEN_FILTER = (
        "PS2 saves (*.psu *.ps2);;"
        "PSU save (*.psu);;Memory card image (*.ps2);;All files (*)"
    )
    SAVE_FILTER = "PSU save (*.psu)"
    #: Offered instead when the save came from a card, so the edit can go
    #: straight back into a copy of it.
    SAVE_FILTER_CARD = "Memory card image (*.ps2);;PSU save (*.psu)"

    def __init__(self) -> None:
        self._source: Path | None = None
        self._original: save_lib.Ps2Save | None = None
        self._working: save_lib.Ps2Save | None = None
        self._edits: dict[tuple[int, str], dict] = {}

    # -- state ---------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._working is not None

    @property
    def source_path(self) -> Path | None:
        return self._source

    @property
    def dirty(self) -> bool:
        return bool(self._edits)

    @property
    def edit_count(self) -> int:
        return len(self._edits)

    # -- opening -------------------------------------------------------

    def open(self, path: Path, directory: str | None = None) -> SaveSummary:
        """Load a save from a .psu, an extracted folder, or a card image."""
        try:
            original = save_lib.load_save(Path(path), directory)
            report = save_lib.inspect(original)
        except save_lib.SaveError as exc:
            raise ValidationError(str(exc)) from exc
        self._working = deepcopy(original)
        self._original = original
        self._source = Path(path)
        self._edits.clear()
        return self._summary(original, report)

    @staticmethod
    def card_directories(path: Path) -> tuple[str, ...]:
        return tuple(save.directory for save in save_lib.read_memcard(path))

    def close(self) -> None:
        self._source = None
        self._original = None
        self._working = None
        self._edits.clear()

    def _require_open(self) -> save_lib.Ps2Save:
        if self._working is None:
            raise ValidationError("No PS2 save is open.")
        return self._working

    # -- reading -------------------------------------------------------

    def summary(self) -> SaveSummary:
        save = self._require_open()
        return self._summary(save, save_lib.inspect(save))

    @staticmethod
    def _summary(save, report) -> SaveSummary:
        roster = report.get("roster") or {}
        tables = roster.get("tables") or {}
        return SaveSummary(
            directory=save.directory,
            kind=str(report.get("type_name") or "Unknown"),
            payload_bytes=int(report.get("payload_bytes") or 0),
            checksum_valid=bool(report.get("crc_valid")),
            player_count=int(tables.get("primary_players") or 0),
        )

    def players(self) -> list[PlayerRow]:
        """Every primary player as one row, pairing first and last names."""
        save = self._require_open()
        try:
            slots = save_lib.player_name_slots(save)
        except save_lib.SaveError as exc:
            raise ValidationError(str(exc)) from exc

        merged: dict[int, dict[str, tuple[str, int]]] = {}
        for slot in slots:
            index = int(slot["player"])
            merged.setdefault(index, {})[str(slot["field"])] = (
                str(slot["value"]),
                _characters(int(slot["capacity_bytes"])),
            )
        rows: list[PlayerRow] = []
        for index in sorted(merged):
            first, first_cap = merged[index].get("first", ("", 0))
            last, last_cap = merged[index].get("last", ("", 0))
            rows.append(PlayerRow(index, first, last, first_cap, last_cap))
        return rows

    # -- editing -------------------------------------------------------

    def validate_name(self, index: int, field: str, value: str) -> str | None:
        """Return a message explaining why a name is rejected, else None.

        The GUI calls this while the user types so a too-long name is refused
        before anything is written, rather than failing at save time.
        """
        if field not in ("first", "last"):
            return f"Unknown name field {field!r}."
        if "\x00" in value:
            return "A name cannot contain a null character."
        slots = save_lib.player_name_slots(self._require_open())
        slot = next((slot for slot in slots if slot["player"] == index and slot["field"] == field), None)
        if slot is None:
            return f"Player {index} has no editable {field} name in this save."
        if slot.get("shared") and value != slot["value"]:
            return "This name shares storage with another name. Changing it would rename both."
        capacity = _characters(int(slot["capacity_bytes"]))
        if capacity <= 0:
            return "This player has no editable slot for that name."
        try:
            units = len(value.encode("utf-16le")) // 2
        except UnicodeEncodeError:
            return "This name contains an incomplete Unicode character."
        if units > capacity:
            return (
                f"That name needs {units} UTF-16 units; this slot holds "
                f"{capacity}. PS2 saves are fixed size, so a replacement has "
                "to fit the space the old name used."
            )
        return None

    def set_name(self, index: int, field: str, value: str) -> None:
        """Apply one name edit to the working copy."""
        problem = self.validate_name(index, field, value)
        if problem:
            raise ValidationError(problem)
        save = self._require_open()
        try:
            change = save_lib.set_player_name(save, index, field, value)
        except save_lib.SaveError as exc:
            raise ValidationError(str(exc)) from exc
        key = (index, field)
        baseline = self._edits.get(key, change)["previous"]
        if value == baseline:
            self._edits.pop(key, None)
        else:
            self._edits[key] = dict(change, previous=baseline)

    def revert(self) -> SaveSummary:
        """Discard every edit by reloading from the source file."""
        if self._source is None:
            raise ValidationError("No PS2 save is open.")
        return self.open(self._source, self._require_open().directory)

    # -- writing -------------------------------------------------------

    @property
    def opened_from_card(self) -> bool:
        """True when the open save came out of a .ps2 memory-card image."""
        return bool(self._source and self._source.suffix.lower() == ".ps2")

    def write(
        self, output: Path, progress: Callable[[str], None] | None = None
    ) -> WriteResult:
        """Reseal and independently verify a staged save, then publish the copy.

        A ``.psu`` destination produces a standalone save file; a ``.ps2``
        destination produces a copy of the memory card this save came from
        with the edit written into it, which is why writing to a card is only
        offered when the save was opened from one.

        Verification is not optional: the editor reports what an independent
        check found, so a write is never presented as successful on the
        writer's own say-so. For a card that check also re-reads the whole
        image, confirms every page's ECC, and confirms the other saves on the
        card are byte-identical.

        ``progress`` is called with the name of each stage as it starts. A card
        write takes seconds, and the caller may be a GUI that has to say which
        of the two long steps is running.
        """
        announce = progress if progress is not None else (lambda _stage: None)
        save = self._require_open()
        if self._original is None:  # pragma: no cover - guarded by _require_open
            raise ValidationError("No baseline is available to verify against.")
        if not self._edits:
            raise ValidationError("There are no changes to save yet.")

        output = Path(output)
        declared = list(self._edits.values())
        to_card = output.suffix.lower() == ".ps2"
        if to_card and not self.opened_from_card:
            raise ValidationError(
                "Writing a memory-card image needs a save that was opened from "
                "one. Open a .ps2 card first, or save as .psu instead."
            )

        if output.exists() or output.is_symlink():
            raise ValidationError(f"Refusing to overwrite an existing file: {output}. Choose a new filename.")
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".studio-ps2-", dir=output.parent) as folder:
                staged = Path(folder) / output.name
                result = self._write_and_verify(staged, save, declared, to_card, announce)
                if result.verified:
                    try:
                        publish_no_replace(staged, output)
                    except OSError as exc:
                        # macOS gives ENOTSUP (45), not EOPNOTSUPP (102), for link() on exFAT, FAT and SMB.
                        if exc.errno not in {errno.ENOSYS, errno.EOPNOTSUPP, errno.EPERM,
                                             getattr(errno, "ENOTSUP", errno.EOPNOTSUPP)}:
                            raise
                        # Some removable filesystems have no exclusive rename or hard links.
                        # Use the writer's exclusive, flushed output path for the verified bytes.
                        save_lib._write_reserved(output, staged.read_bytes(), (self._source,))
                return replace(result, output=output)
        except FileExistsError as exc:
            raise ValidationError(f"The output appeared during verification. Choose a new filename: {output}.") from exc
        except (OSError, save_lib.SaveError) as exc:
            raise ValidationError(f"Could not write {output}: {exc}") from exc

    def _write_and_verify(
        self, output: Path, save: save_lib.Ps2Save, declared: list[dict], to_card: bool,
        announce: Callable[[str], None],
    ) -> WriteResult:
        save.reseal()
        if to_card:
            announce("Writing the memory-card image…")
            save_lib.write_into_memcard(self._source, save, output, save.directory)
        else:
            announce("Writing the save file…")
            save_lib.write_psu(save, output)

        try:
            if to_card:
                announce("Verifying the card: every page's ECC and the other saves…")
                card = verify_lib.verify_memcard_write(
                    self._source, output, save.directory, declared
                )
                report = card["save"]
                extra = (
                    f" Card checked: {card['ecc']['pages_checked']:,} pages of ECC, "
                    f"{len(card['other_saves_untouched'])} other save(s) untouched."
                )
            else:
                announce("Verifying the file that was written…")
                # Re-read what actually landed on disk. Verifying the
                # in-memory save would only prove the editor agrees with
                # itself, and would miss a serialization bug or a short write.
                report = verify_lib.verify(
                    verify_lib.decode_save(self._source, save.directory),
                    verify_lib.decode_psu(output),
                    declared,
                )
                extra = ""
        except verify_lib.VerifyError as exc:
            return WriteResult(output, False, 0, len(declared),
                               f"Save verification failed: {exc}")

        changed = int(report.get("changed_bytes") or 0)
        return WriteResult(
            output,
            True,
            changed,
            len(declared),
            f"Saved and verified — {len(declared)} change(s), "
            f"{changed} bytes, roster tables intact.{extra}",
        )

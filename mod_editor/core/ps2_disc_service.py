"""Qt-free service backing the PS2 Disc Inventory window.

The GUI never talks to the command-line tool directly.  This module is the
seam between them: it runs ``tools/nfl2k5_ps2_disc_inventory.py`` over the
user's own ISO, keeps the ~550,000 resulting rows in a private SQLite sidecar
so a table can page through them without holding them all in Python objects,
answers filtered counts and windows for a virtualized model, joins an Xbox
resource-name inventory by name, and exports rows or the report.  Everything
here is standard library, so the whole thing is unit-testable without a
display.

Two boundaries are deliberate.  The disc is opened for reading only and its
size and mtime are re-checked after the walk; nothing here can write to it.
And only the metadata half of each resource chunk is ever decoded: the
inventory tool never reads pixel or audio payload, so nothing this service
holds or exports can carry retail data -- names, types, sizes, offsets,
dimensions and digests only.

Threading: :meth:`open`, :meth:`load_xbox_inventory` and :meth:`export_csv`
are slow (a full disc takes a minute or two) and are meant to run off the Qt
thread; each uses its own SQLite connection.  :meth:`count`, :meth:`rows` and
:meth:`distinct` are fast and are meant for the thread that owns the view.
The dialog serialises them: it never queries while an operation is running.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Callable, Iterable, Optional

from .errors import ValidationError

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_disc_inventory as inventory_lib  # noqa: E402
import ps2_iso9660 as iso_lib  # noqa: E402

PRESENCE_ANY = ""
PRESENCE_BOTH = "both"
PRESENCE_PS2_ONLY = "ps2_only"
#: Stored on every named row until an Xbox inventory is loaded.
PRESENCE_UNKNOWN = "unknown"
PRESENCES = (PRESENCE_ANY, PRESENCE_BOTH, PRESENCE_PS2_ONLY, PRESENCE_UNKNOWN)

FILTER_COLUMNS = ("fourcc", "role", "pack")

#: Columns of an exported rows CSV, in order.
EXPORT_COLUMNS = (
    "pack", "entry_index", "name", "name_key", "fourcc", "role", "size",
    "width", "height", "format", "xbox_presence", "extra",
)

_INSERT_BATCH = 4096
_COMMIT_TIMEOUT = 30.0


@dataclass(frozen=True)
class DiscIdentity:
    """What the window shows about the open image before any row."""

    name: str
    size_bytes: int
    serial: Optional[str]
    boot_file: Optional[str]
    boot_sha256: Optional[str]
    serial_matches: bool
    retail_boot_elf: bool
    image_sha256: Optional[str]
    retail_image: Optional[bool]

    @property
    def headline(self) -> str:
        if self.serial is None:
            serial = "no SYSTEM.CNF boot serial"
        elif self.serial_matches:
            serial = self.serial
        else:
            serial = f"{self.serial} (expected {inventory_lib.SERIAL})"
        boot = "retail boot ELF" if self.retail_boot_elf else "boot ELF differs from retail"
        return f"{self.name} — {serial} · {boot} · {self.size_bytes:,} bytes"


@dataclass(frozen=True)
class InventorySummary:
    """Counts the window shows once the walk has finished."""

    entries: int
    rows: int
    named_rows: int
    textures: int
    name_keys: int
    errors: int
    xbox_name_keys: Optional[int]
    shared: Optional[int]
    ps2_only: Optional[int]
    xbox_only: Optional[int]

    @property
    def xbox_loaded(self) -> bool:
        return self.xbox_name_keys is not None

    @property
    def headline(self) -> str:
        text = (
            f"{self.entries:,} entries · {self.rows:,} rows · "
            f"{self.textures:,} textures · {self.name_keys:,} distinct names"
        )
        if self.errors:
            text += f" · {self.errors} decode error(s)"
        if self.xbox_loaded:
            text += (
                f" · Xbox: {self.shared:,} shared names, {self.ps2_only:,} PS2-only, "
                f"{self.xbox_only:,} Xbox-only"
            )
        return text


@dataclass(frozen=True)
class ResourceRow:
    """One inventory row as the table displays it."""

    pack: str
    entry_index: int
    name: str
    name_key: str
    fourcc: str
    role: str
    size: str
    width: str
    height: str
    format: str
    xbox: str
    extra: str

    @property
    def dimensions(self) -> str:
        return f"{self.width}x{self.height}" if self.width and self.height else ""


@dataclass(frozen=True)
class RowFilter:
    """The table's current narrowing; empty strings mean "any"."""

    search: str = ""
    fourcc: str = ""
    role: str = ""
    pack: str = ""
    presence: str = PRESENCE_ANY

    def validate(self) -> None:
        if self.presence not in PRESENCES:
            raise ValidationError(
                "An Xbox presence filter must be blank, both, ps2_only or unknown."
            )

    def where(self) -> tuple[str, list]:
        """SQL ``WHERE`` text (or empty) plus its parameters."""

        self.validate()
        clauses: list[str] = []
        params: list = []
        needle = self.search.strip()
        if needle:
            if needle.isdigit():
                clauses.append("(instr(name_key, ?) > 0 OR entry_index = ?)")
                params.extend([needle.upper(), int(needle)])
            else:
                clauses.append("instr(name_key, ?) > 0")
                params.append(needle.upper())
        for column, value in (
            ("fourcc", self.fourcc), ("role", self.role),
            ("pack", self.pack), ("xbox", self.presence),
        ):
            if value:
                clauses.append(f"{column} = ?")
                params.append(value)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _role_of(extra: str) -> str:
    for piece in extra.split(";"):
        if piece.startswith("role="):
            return piece[5:]
    return ""


def _exclusive_output(output: Path) -> None:
    if os.path.lexists(output):
        raise ValidationError(
            f"Refusing to overwrite {output.name}; choose a name that does not exist yet."
        )


class Ps2DiscService:
    """Open one PS2 disc image read-only and serve its resource inventory."""

    #: Accepted inputs, for the GUI's file dialogs.
    OPEN_FILTER = "PS2 disc images (*.iso *.bin *.img);;All files (*)"
    XBOX_FILTER = (
        "Resource-name inventories (*.csv *.tsv *.csv.gz *.tsv.gz);;All files (*)"
    )

    def __init__(self, *, jobs: Optional[int] = None) -> None:
        self._source: Optional[Path] = None
        self._workspace: Optional[Path] = None
        self._database: Optional[Path] = None
        self._connection: Optional[sqlite3.Connection] = None
        self._report: Optional[dict] = None
        self._side: Optional[inventory_lib.NameSide] = None
        self._join: Optional[dict] = None
        self._jobs = jobs if jobs is not None else max(1, min(4, os.cpu_count() or 1))

    # -- state ---------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._connection is not None

    @property
    def source_path(self) -> Optional[Path]:
        return self._source

    @property
    def xbox_loaded(self) -> bool:
        return self._join is not None

    def _require_open(self) -> sqlite3.Connection:
        if self._connection is None or self._report is None:
            raise ValidationError("No disc image is open.")
        return self._connection

    # -- opening -------------------------------------------------------

    def open(self, path: Path, progress: Optional[Callable[[str], None]] = None) -> DiscIdentity:
        """Inventory ``path`` into a fresh private sidecar.  Slow; run off the UI thread."""

        path = Path(path)
        if not path.is_file():
            raise ValidationError(f"{path} is not a file.")
        self.close()
        workspace = Path(tempfile.mkdtemp(prefix="nfl2k5-ps2-disc-"))
        database = workspace / "inventory.sqlite"
        build = sqlite3.connect(str(database), timeout=_COMMIT_TIMEOUT)
        batch: list = []

        def flush() -> None:
            if batch:
                build.executemany(
                    "INSERT INTO rows(pack, entry_index, name, name_key, fourcc, role, "
                    "size, width, height, format, xbox, extra) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    batch,
                )
                del batch[:]

        def sink(row: dict) -> None:
            batch.append((
                str(row["pack"]), int(row["entry_index"]), row["name"], row["name_key"],
                row["fourcc"], _role_of(row["extra"]), str(row["size"]),
                str(row["width"]), str(row["height"]), row["format"],
                PRESENCE_UNKNOWN if row["name_key"] else "", row["extra"],
            ))
            if len(batch) >= _INSERT_BATCH:
                flush()

        try:
            build.execute("PRAGMA journal_mode = OFF")
            build.execute("PRAGMA synchronous = OFF")
            build.execute(
                "CREATE TABLE rows (id INTEGER PRIMARY KEY, pack TEXT, entry_index INTEGER, "
                "name TEXT, name_key TEXT, fourcc TEXT, role TEXT, size TEXT, width TEXT, "
                "height TEXT, format TEXT, xbox TEXT, extra TEXT)"
            )
            if progress is not None:
                progress("Reading the disc identity and pack table…")
            report, side = inventory_lib.inventory(
                str(path), csv_path=None, jobs=self._jobs, progress=progress,
                row_sink=sink,
            )
            flush()
            if progress is not None:
                progress("Indexing rows…")
            for column in ("name_key", "fourcc", "role", "pack", "xbox"):
                build.execute(f"CREATE INDEX idx_{column} ON rows({column})")
            build.commit()
        except (inventory_lib.InventoryError, iso_lib.Iso9660Error, OSError) as exc:
            build.close()
            shutil.rmtree(workspace, ignore_errors=True)
            raise ValidationError(str(exc).strip() or exc.__class__.__name__) from exc
        except BaseException:
            build.close()
            shutil.rmtree(workspace, ignore_errors=True)
            raise
        build.close()

        self._source = path
        self._workspace = workspace
        self._database = database
        self._connection = sqlite3.connect(
            str(database), timeout=_COMMIT_TIMEOUT, check_same_thread=False
        )
        self._report = report
        self._side = side
        self._join = None
        return self.identity()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
        if self._workspace is not None:
            shutil.rmtree(self._workspace, ignore_errors=True)
        self._source = None
        self._workspace = None
        self._database = None
        self._connection = None
        self._report = None
        self._side = None
        self._join = None

    # -- what is open --------------------------------------------------

    def identity(self) -> DiscIdentity:
        self._require_open()
        image = self._report["image"]
        who = image["identity"]
        return DiscIdentity(
            name=image["name"],
            size_bytes=image["size_bytes"],
            serial=who["serial"],
            boot_file=who["boot_file"],
            boot_sha256=who["boot_sha256"],
            serial_matches=bool(who["serial_matches"]),
            retail_boot_elf=bool(who["retail_boot_elf"]),
            image_sha256=who["image_sha256"],
            retail_image=who["retail_image"],
        )

    def summary(self) -> InventorySummary:
        self._require_open()
        resources = self._report["resources"]
        join = self._join or {}
        return InventorySummary(
            entries=self._report["outer"]["entries_scanned"],
            rows=resources["row_count"],
            named_rows=resources["named_rows"],
            textures=resources["txtr_rows"],
            name_keys=resources["distinct_name_keys"],
            errors=self._report["error_count"],
            xbox_name_keys=join.get("xbox_name_keys"),
            shared=join.get("shared"),
            ps2_only=join.get("ps2_only"),
            xbox_only=join.get("xbox_only"),
        )

    def report(self) -> dict:
        """The tool's JSON report for the open disc (a copy)."""
        self._require_open()
        return dict(self._report)

    # -- the Xbox side -------------------------------------------------

    def load_xbox_inventory(
        self, path: Path, progress: Optional[Callable[[str], None]] = None
    ) -> InventorySummary:
        """Join an Xbox resource-name inventory by name; stamps every row's presence."""

        self._require_open()
        path = Path(path)
        if progress is not None:
            progress(f"Reading {path.name}…")
        try:
            side, provenance = inventory_lib.load_name_side(str(path))
        except (inventory_lib.InventoryError, OSError, UnicodeDecodeError, csv.Error) as exc:
            raise ValidationError(str(exc).strip() or exc.__class__.__name__) from exc
        _rows, join = inventory_lib.name_join(self._side, side)
        if progress is not None:
            progress("Marking each PS2 name's Xbox counterpart…")
        connection = sqlite3.connect(str(self._database), timeout=_COMMIT_TIMEOUT)
        try:
            connection.execute("CREATE TEMP TABLE xbox_keys (k TEXT PRIMARY KEY)")
            connection.executemany(
                "INSERT OR IGNORE INTO xbox_keys(k) VALUES (?)",
                ((key,) for key in side.keys),
            )
            connection.execute(
                "UPDATE rows SET xbox = CASE WHEN name_key = '' THEN '' "
                "WHEN name_key IN (SELECT k FROM xbox_keys) THEN ? ELSE ? END",
                (PRESENCE_BOTH, PRESENCE_PS2_ONLY),
            )
            connection.commit()
        finally:
            connection.close()
        self._join = dict(join, xbox_inventory=provenance)
        self._report["name_join"] = dict(self._join)
        return self.summary()

    # -- reading rows --------------------------------------------------

    def count(self, flt: RowFilter = RowFilter()) -> int:
        connection = self._require_open()
        where, params = flt.where()
        (total,) = connection.execute(f"SELECT COUNT(*) FROM rows{where}", params).fetchone()
        return int(total)

    def rows(self, flt: RowFilter, offset: int, limit: int) -> list[ResourceRow]:
        connection = self._require_open()
        if offset < 0 or limit <= 0:
            raise ValidationError("A row window needs a non-negative offset and a positive size.")
        where, params = flt.where()
        cursor = connection.execute(
            "SELECT pack, entry_index, name, name_key, fourcc, role, size, width, height, "
            f"format, xbox, extra FROM rows{where} ORDER BY id LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        return [ResourceRow(*record) for record in cursor.fetchall()]

    def distinct(self, column: str) -> list[str]:
        """Values a filter combo can offer, in sorted order."""
        connection = self._require_open()
        if column not in FILTER_COLUMNS:
            raise ValidationError(f"Cannot list distinct values of {column!r}.")
        cursor = connection.execute(
            f"SELECT DISTINCT {column} FROM rows WHERE {column} != '' ORDER BY {column}"
        )
        return [str(value) for (value,) in cursor.fetchall()]

    # -- exporting -----------------------------------------------------

    def export_csv(
        self, output: Path, flt: RowFilter = RowFilter(),
        progress: Optional[Callable[[str], None]] = None,
    ) -> int:
        """Write the rows the filter selects.  Returns the row count; never overwrites."""

        self._require_open()
        output = Path(output)
        _exclusive_output(output)
        where, params = flt.where()
        connection = sqlite3.connect(str(self._database), timeout=_COMMIT_TIMEOUT)
        written = 0
        try:
            cursor = connection.execute(
                "SELECT pack, entry_index, name, name_key, fourcc, role, size, width, "
                f"height, format, xbox, extra FROM rows{where} ORDER BY id",
                params,
            )
            with open(output, "x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(EXPORT_COLUMNS)
                while True:
                    block = cursor.fetchmany(_INSERT_BATCH)
                    if not block:
                        break
                    writer.writerows(block)
                    written += len(block)
                    if progress is not None:
                        progress(f"Exported {written:,} rows…")
        finally:
            connection.close()
        return written

    def export_report(self, output: Path) -> Path:
        """Write the tool's JSON report (identity, censuses, join).  Never overwrites."""

        self._require_open()
        output = Path(output)
        _exclusive_output(output)
        inventory_lib.write_json(str(output), self._report)
        return output


__all__ = [
    "DiscIdentity",
    "EXPORT_COLUMNS",
    "FILTER_COLUMNS",
    "InventorySummary",
    "PRESENCES",
    "PRESENCE_ANY",
    "PRESENCE_BOTH",
    "PRESENCE_PS2_ONLY",
    "PRESENCE_UNKNOWN",
    "Ps2DiscService",
    "ResourceRow",
    "RowFilter",
]

"""Lazy universal browser/export adapter for NFL 2K5 resource chunks.

The private source cache contains 86,882 indexed resource wrappers.  Keeping
the 55 MiB JSON document resident would make a desktop asset browser needlessly
heavy, so this adapter streams it once into a private SQLite sidecar.  Browser
queries are paged and raw export copies one bounded block at a time.

The sidecar and exported resources are derived from the user's own dump.  No
row or payload is part of the public application package.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import struct
import sys
from typing import Iterator
from uuid import uuid4

from .errors import ValidationError
from .json_stream import (
    file_contains_bytes,
    iter_top_level_array,
    require_regular_file,
)
from .nfl2k5_source_cache import (
    INVENTORY_SHA256,
    SourceCache,
)


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_outer import FormatError, parse_archive, read_entry_range  # noqa: E402


INDEX_SCHEMA = "2k5_mod_studio_universal_asset_index/v1"
SOURCE_SCHEMA = "nfl2k5_resource_chunk_inventory/v1"
RESOURCE_HEADER_SIZE = 0x20
COPY_BLOCK = 1024 * 1024
DEFAULT_PAGE_SIZE = 250
MAX_PAGE_SIZE = 2000


@dataclass(frozen=True)
class UniversalAssetRecord:
    """One indexed resource wrapper; the payload itself remains on disk."""

    asset_id: str
    outer_index: int
    outer_id: str
    outer_head: str
    outer_size: int
    chunk_index: int
    chunk_offset: int
    zero_padding_before: int
    kind: str
    stored_size: int
    end_offset: int
    word_08: int
    word_0c: int
    word_10: str
    word_14: int

    @property
    def raw_size(self) -> int:
        """Size of the 0x20-byte wrapper plus its stored body."""

        return self.end_offset - self.chunk_offset

    @property
    def suggested_filename(self) -> str:
        printable = "".join(
            character if character.isalnum() else "_" for character in self.kind
        ).strip("_")
        suffix = printable or self.kind.encode("ascii").hex()
        return f"{self.outer_index:04d}_{self.chunk_index:04d}_{suffix}.bin"


def _asset_id(outer_index: int, chunk_index: int, kind: str) -> str:
    return (
        f"nfl2k5.resource.o{outer_index:04d}.c{chunk_index:04d}."
        f"k{kind.encode('ascii').hex()}"
    )


def _integer(row: dict[str, object], key: str, *, minimum: int = 0) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"Private game index has an invalid {key!r} value")
    return value


def _text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise ValidationError(f"Private game index has an invalid {key!r} value")
    return value


def _normalize_row(row: object) -> UniversalAssetRecord:
    if not isinstance(row, dict):
        raise ValidationError("Private game index contains a non-object resource row")
    outer_index = _integer(row, "outer_index")
    chunk_index = _integer(row, "chunk_index")
    outer_id = _text(row, "outer_id")
    outer_head = _text(row, "outer_head")
    kind = _text(row, "kind")
    if len(kind) != 4 or any(not 0x20 <= ord(value) <= 0x7E for value in kind):
        raise ValidationError("Private game index contains an invalid resource FourCC")
    if len(outer_id) != 10 or not outer_id.startswith("0x"):
        raise ValidationError("Private game index contains an invalid outer entry ID")
    try:
        int(outer_id[2:], 16)
    except ValueError as exc:
        raise ValidationError("Private game index contains an invalid outer entry ID") from exc
    chunk_offset = _integer(row, "chunk_offset")
    stored_size = _integer(row, "stored_size", minimum=1)
    end_offset = _integer(row, "end_offset")
    outer_size = _integer(row, "outer_size", minimum=1)
    if end_offset != chunk_offset + RESOURCE_HEADER_SIZE + stored_size:
        raise ValidationError("Private game index has an inconsistent resource extent")
    if end_offset > outer_size:
        raise ValidationError("Private game index has a resource outside its outer entry")
    word_10 = _text(row, "word_10")
    if len(word_10) != 10 or not word_10.startswith("0x"):
        raise ValidationError("Private game index has an invalid word_10 value")
    try:
        int(word_10[2:], 16)
    except ValueError as exc:
        raise ValidationError("Private game index has an invalid word_10 value") from exc
    return UniversalAssetRecord(
        asset_id=_asset_id(outer_index, chunk_index, kind),
        outer_index=outer_index,
        outer_id=outer_id,
        outer_head=outer_head,
        outer_size=outer_size,
        chunk_index=chunk_index,
        chunk_offset=chunk_offset,
        zero_padding_before=_integer(row, "zero_padding_before"),
        kind=kind,
        stored_size=stored_size,
        end_offset=end_offset,
        word_08=_integer(row, "word_08"),
        word_0c=_integer(row, "word_0c"),
        word_10=word_10,
        word_14=_integer(row, "word_14"),
    )


def _database_row(record: UniversalAssetRecord) -> tuple[object, ...]:
    return (
        record.asset_id,
        record.outer_index,
        record.outer_id,
        record.outer_head,
        record.outer_size,
        record.chunk_index,
        record.chunk_offset,
        record.zero_padding_before,
        record.kind,
        record.stored_size,
        record.end_offset,
        record.word_08,
        record.word_0c,
        record.word_10,
        record.word_14,
    )


def _record_from_sql(row: tuple[object, ...]) -> UniversalAssetRecord:
    return UniversalAssetRecord(
        asset_id=str(row[0]),
        outer_index=int(row[1]),
        outer_id=str(row[2]),
        outer_head=str(row[3]),
        outer_size=int(row[4]),
        chunk_index=int(row[5]),
        chunk_offset=int(row[6]),
        zero_padding_before=int(row[7]),
        kind=str(row[8]),
        stored_size=int(row[9]),
        end_offset=int(row[10]),
        word_08=int(row[11]),
        word_0c=int(row[12]),
        word_10=str(row[13]),
        word_14=int(row[14]),
    )


class Nfl2k5UniversalAssetIndex:
    """Paged metadata browser and bounded raw-resource exporter."""

    def __init__(
        self,
        inventory_path: Path,
        pack0: Path,
        database_path: Path,
        *,
        inventory_fingerprint: str | None = None,
        expected_count: int | None = None,
    ) -> None:
        self.inventory_path = inventory_path.expanduser()
        self.pack0 = pack0.expanduser()
        self.database_path = database_path.expanduser()
        self.expected_count = expected_count
        require_regular_file(self.inventory_path, "private NFL 2K5 asset index")
        require_regular_file(self.pack0, "private NFL 2K5 archive index")
        if not file_contains_bytes(
            self.inventory_path,
            f'"schema": "{SOURCE_SCHEMA}"'.encode("ascii"),
            label="private NFL 2K5 asset index",
        ):
            raise ValidationError("The private game index has an unsupported format")
        self.inventory_fingerprint = inventory_fingerprint or self._hash_inventory()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if self.database_path.is_symlink():
            raise ValidationError("The universal asset sidecar cannot be a symbolic link")
        if not self._database_is_current():
            self._build_database()
        try:
            self.archive = parse_archive(self.pack0)
        except (OSError, FormatError) as exc:
            raise ValidationError(f"Could not open the private game archive: {exc}") from exc

    @classmethod
    def from_cache(cls, cache: SourceCache) -> "Nfl2k5UniversalAssetIndex":
        return cls(
            cache.inventory,
            cache.pack0,
            cache.root / "indexes" / "universal-assets-v1.sqlite3",
            inventory_fingerprint=INVENTORY_SHA256,
            expected_count=cache.resource_count,
        )

    @property
    def asset_count(self) -> int:
        with self._connect_read_only() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

    def kinds(self) -> tuple[tuple[str, int], ...]:
        with self._connect_read_only() as connection:
            rows = connection.execute(
                "SELECT kind, COUNT(*) FROM assets GROUP BY kind ORDER BY kind"
            ).fetchall()
        return tuple((str(kind), int(count)) for kind, count in rows)

    def get(self, asset_id: str) -> UniversalAssetRecord:
        with self._connect_read_only() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
        if row is None:
            raise ValidationError(f"Unknown indexed asset: {asset_id}")
        return _record_from_sql(row)

    def query(
        self,
        *,
        search: str = "",
        kind: str | None = None,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[UniversalAssetRecord, ...]:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValidationError("Asset page offset must be zero or greater")
        if isinstance(limit, bool) or not isinstance(limit, int) \
                or not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValidationError(
                f"Asset page size must be between 1 and {MAX_PAGE_SIZE}"
            )
        clauses: list[str] = []
        arguments: list[object] = []
        if kind is not None:
            if len(kind) != 4:
                raise ValidationError("Resource kind filters must be four characters")
            clauses.append("kind = ?")
            arguments.append(kind)
        if search:
            escaped = (
                search.replace("\\", "\\\\").replace("%", "\\%")
                .replace("_", "\\_")
            )
            clauses.append(
                "(asset_id LIKE ? ESCAPE '\\' OR outer_id LIKE ? ESCAPE '\\' "
                "OR outer_head LIKE ? ESCAPE '\\' OR kind LIKE ? ESCAPE '\\')"
            )
            pattern = f"%{escaped}%"
            arguments.extend((pattern, pattern, pattern, pattern))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        arguments.extend((limit, offset))
        with self._connect_read_only() as connection:
            rows = connection.execute(
                "SELECT * FROM assets" + where +
                " ORDER BY outer_index, chunk_index LIMIT ? OFFSET ?",
                tuple(arguments),
            ).fetchall()
        return tuple(_record_from_sql(row) for row in rows)

    def iter_all(self, *, page_size: int = DEFAULT_PAGE_SIZE) \
            -> Iterator[UniversalAssetRecord]:
        offset = 0
        while True:
            page = self.query(offset=offset, limit=page_size)
            if not page:
                return
            yield from page
            offset += len(page)

    def export_raw(self, asset_or_id: UniversalAssetRecord | str,
                   destination: Path) -> Path:
        """Atomically export one exact wrapper/body without loading it whole."""

        record = (
            self.get(asset_or_id) if isinstance(asset_or_id, str) else asset_or_id
        )
        canonical = self.get(record.asset_id)
        if canonical != record:
            raise ValidationError("That asset record does not match the private index")
        if not 0 <= record.outer_index < len(self.archive.entries):
            raise ValidationError("Indexed asset names an unknown outer archive entry")
        entry = self.archive.entries[record.outer_index]
        if (
            entry.size != record.outer_size
            or f"0x{entry.name_id:08x}" != record.outer_id
            or entry.head_ascii != record.outer_head
        ):
            raise ValidationError("The private archive no longer matches its asset index")
        try:
            header = read_entry_range(
                self.archive, entry, record.chunk_offset, RESOURCE_HEADER_SIZE
            )
        except (OSError, FormatError) as exc:
            raise ValidationError(f"Could not read that resource: {exc}") from exc
        if (
            header[:4] != record.kind.encode("ascii")
            or struct.unpack_from("<I", header, 4)[0] != record.stored_size
            or struct.unpack_from("<I", header, 8)[0] != record.word_08
            or struct.unpack_from("<I", header, 0x0C)[0] != record.word_0c
            or f"0x{struct.unpack_from('<I', header, 0x10)[0]:08x}" != record.word_10
            or struct.unpack_from("<I", header, 0x14)[0] != record.word_14
        ):
            raise ValidationError("That resource header no longer matches the game index")

        target = destination.expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(target):
            raise ValidationError(f"A file already exists there: {target}")
        temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid4().hex}.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            written = 0
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                while written < record.raw_size:
                    size = min(COPY_BLOCK, record.raw_size - written)
                    try:
                        block = read_entry_range(
                            self.archive,
                            entry,
                            record.chunk_offset + written,
                            size,
                        )
                    except (OSError, FormatError) as exc:
                        raise ValidationError(f"Could not export that resource: {exc}") from exc
                    stream.write(block)
                    written += len(block)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError as exc:
                raise ValidationError(f"A file appeared at the export destination: {target}") from exc
        finally:
            temporary.unlink(missing_ok=True)
        return target.resolve(strict=True)

    def _hash_inventory(self) -> str:
        digest = hashlib.sha256()
        with self.inventory_path.open("rb") as stream:
            for block in iter(lambda: stream.read(COPY_BLOCK), b""):
                digest.update(block)
        return digest.hexdigest()

    def _database_is_current(self) -> bool:
        if not self.database_path.exists():
            return False
        try:
            info = self.database_path.lstat()
            if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                return False
            with sqlite3.connect(self.database_path) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
                count = int(connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return False
        return (
            metadata.get("schema") == INDEX_SCHEMA
            and metadata.get("inventory_fingerprint") == self.inventory_fingerprint
            and (
                self.expected_count is None
                or count == self.expected_count
            )
            and metadata.get("asset_count") == str(count)
        )

    def _build_database(self) -> None:
        temporary = self.database_path.with_name(
            f".{self.database_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        if os.path.lexists(temporary):
            raise ValidationError("Could not reserve the universal asset index")
        connection = sqlite3.connect(temporary)
        count = 0
        try:
            connection.executescript(
                """
                PRAGMA journal_mode = OFF;
                PRAGMA synchronous = FULL;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE assets (
                    asset_id TEXT PRIMARY KEY,
                    outer_index INTEGER NOT NULL,
                    outer_id TEXT NOT NULL,
                    outer_head TEXT NOT NULL,
                    outer_size INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_offset INTEGER NOT NULL,
                    zero_padding_before INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    stored_size INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    word_08 INTEGER NOT NULL,
                    word_0c INTEGER NOT NULL,
                    word_10 TEXT NOT NULL,
                    word_14 INTEGER NOT NULL
                );
                """
            )
            insert = "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            batch: list[tuple[object, ...]] = []
            previous: tuple[int, int] | None = None
            for raw in iter_top_level_array(
                self.inventory_path,
                "chunks",
                label="private NFL 2K5 asset index",
            ):
                record = _normalize_row(raw)
                order = (record.outer_index, record.chunk_index)
                if previous is not None and order <= previous:
                    raise ValidationError("Private game index resource order is invalid")
                previous = order
                batch.append(_database_row(record))
                count += 1
                if len(batch) == 1000:
                    connection.executemany(insert, batch)
                    batch.clear()
            if batch:
                connection.executemany(insert, batch)
            if self.expected_count is not None and count != self.expected_count:
                raise ValidationError(
                    f"Private game index lists {count:,} resources; "
                    f"{self.expected_count:,} were expected"
                )
            connection.execute(
                "INSERT INTO metadata VALUES (?, ?)", ("schema", INDEX_SCHEMA)
            )
            connection.execute(
                "INSERT INTO metadata VALUES (?, ?)",
                ("inventory_fingerprint", self.inventory_fingerprint),
            )
            connection.execute(
                "INSERT INTO metadata VALUES (?, ?)", ("asset_count", str(count))
            )
            connection.executescript(
                """
                CREATE INDEX assets_kind_order ON assets(kind, outer_index, chunk_index);
                CREATE INDEX assets_outer_order ON assets(outer_index, chunk_index);
                """
            )
            connection.commit()
        except BaseException:
            connection.close()
            temporary.unlink(missing_ok=True)
            raise
        connection.close()
        try:
            os.replace(temporary, self.database_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _connect_read_only(self) -> sqlite3.Connection:
        uri = f"file:{self.database_path.resolve(strict=True).as_posix()}?mode=ro"
        return sqlite3.connect(uri, uri=True)


__all__ = ["Nfl2k5UniversalAssetIndex", "UniversalAssetRecord"]

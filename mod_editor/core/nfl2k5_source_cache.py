"""Private, user-XISO-derived cache for 2K5 Mod Studio.

Nothing in this cache is a release payload.  It is rebuilt from the user's
recognized XISO, lives below the user's cache directory, and is deliberately
separate from shareable projects (which contain user-authored replacements
only).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Callable

from .errors import ValidationError
from .model import GameId, SourceRecord
from .sources import SourceInspector


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402


SOURCE_SIZE = 6_300_499_968
SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
PACK_FOLDER = Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030")
PACK0_SIZE = 193_710_080
PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INVENTORY_SIZE = 55_746_414
INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
INVENTORY_RELATIVE = Path("indexes/nfl2k5_resource_chunks_v2.json")
CACHE_SCHEMA = "2k5_mod_studio_source_cache/v1"
COPY_BLOCK = 16 * 1024 * 1024


IndexProgress = Callable[[str, int, int], None]


@dataclass(frozen=True)
class SourceCache:
    source: SourceRecord
    root: Path
    pack0: Path
    inventory: Path
    originals: Path
    resource_count: int
    outer_entry_count: int
    kind_counts: dict[str, int]


def default_cache_root() -> Path:
    return Path.home() / ".cache" / "2k5-mod-studio"


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BLOCK), b""):
            result.update(block)
    return result.hexdigest()


def _emit(progress: IndexProgress | None, stage: str, completed: int, total: int) -> None:
    if progress is not None:
        progress(stage, completed, total)


def _regular_non_symlink(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValidationError(f"{label} must be a regular file: {path}")
    return info


class Nfl2k5SourceCache:
    """Recognize an XISO and materialize its archive packs atomically."""

    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = (cache_root or default_cache_root()).expanduser()
        self.inspector = SourceInspector()

    def index(self, source_xiso: Path,
              progress: IndexProgress | None = None) -> SourceCache:
        selected = source_xiso.expanduser().resolve(strict=True)
        info = _regular_non_symlink(selected, "NFL 2K5 XISO")
        if info.st_size != SOURCE_SIZE:
            raise ValidationError(
                "That file is not the supported NFL 2K5 Xbox XISO "
                f"({info.st_size:,} bytes found; {SOURCE_SIZE:,} expected)."
            )

        def hash_progress(completed: int, total: int) -> None:
            _emit(progress, "Checking your XISO", completed, total)

        source = self.inspector.inspect(selected, GameId.NFL2K5, hash_progress)
        if (
            not source.recognized
            or source.fingerprint_id != "nfl2k5-usa-retail-xiso"
            or source.sha256 != SOURCE_SHA256
            or source.kind != "xiso"
        ):
            raise ValidationError(
                "2K5 Mod Studio currently supports the USA retail Xbox XISO. "
                "This file did not match that dump; it was not modified."
            )

        self.cache_root.mkdir(parents=True, exist_ok=True)
        final = self.cache_root / SOURCE_SHA256
        cached = self._load_existing(final, source)
        if cached is not None:
            _emit(progress, "Game index ready", 1, 1)
            return cached

        temporary = Path(tempfile.mkdtemp(
            prefix=f".{SOURCE_SHA256[:12]}.indexing-", dir=self.cache_root))
        try:
            self._extract_packs(selected, temporary, progress)
            inventory = self._build_inventory(temporary, progress)
            pack0 = temporary / PACK_FOLDER / "0"
            if pack0.stat().st_size != PACK0_SIZE or _digest(pack0) != PACK0_SHA256:
                raise ValidationError("The private archive cache did not match your XISO")
            if inventory.stat().st_size != INVENTORY_SIZE or \
                    _digest(inventory) != INVENTORY_SHA256:
                raise ValidationError("The generated game index did not match NFL 2K5")
            summary = json.loads(inventory.read_text(encoding="utf-8"))["summary"]
            marker = {
                "inventory": {
                    "path": INVENTORY_RELATIVE.as_posix(),
                    "sha256": INVENTORY_SHA256,
                    "size": INVENTORY_SIZE,
                },
                "packs": self._pack_ledger(temporary / PACK_FOLDER),
                "schema": CACHE_SCHEMA,
                "source": {
                    "sha256": SOURCE_SHA256,
                    "size": SOURCE_SIZE,
                },
                "summary": summary,
            }
            self._atomic_write_json(temporary / "cache.json", marker)
            (temporary / "originals").mkdir()
            try:
                os.replace(temporary, final)
            except FileExistsError:
                existing = self._load_existing(final, source)
                if existing is None:
                    raise ValidationError("Another indexing process published an invalid cache")
                shutil.rmtree(temporary)
                return existing
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        result = self._load_existing(final, source)
        if result is None:
            raise ValidationError("Game index publication failed")
        _emit(progress, "Game index ready", 1, 1)
        return result

    def _load_existing(self, root: Path, source: SourceRecord) -> SourceCache | None:
        marker_path = root / "cache.json"
        if not marker_path.is_file() or marker_path.is_symlink():
            return None
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (
            marker.get("schema") != CACHE_SCHEMA
            or marker.get("source") != {"sha256": SOURCE_SHA256, "size": SOURCE_SIZE}
        ):
            return None
        pack_folder = root / PACK_FOLDER
        pack_rows = marker.get("packs")
        if not isinstance(pack_rows, list) or not pack_rows:
            return None
        for row in pack_rows:
            path = pack_folder / str(row.get("name", ""))
            try:
                info = _regular_non_symlink(path, "cached archive pack")
            except ValidationError:
                return None
            if info.st_size != row.get("size"):
                return None
        pack0 = pack_folder / "0"
        inventory = root / INVENTORY_RELATIVE
        if (
            not inventory.is_file()
            or inventory.is_symlink()
            or inventory.stat().st_size != INVENTORY_SIZE
            or pack0.stat().st_size != PACK0_SIZE
        ):
            return None
        summary = marker.get("summary", {})
        counts = summary.get("resource_kind_counts", {})
        if not isinstance(counts, dict):
            return None
        originals = root / "originals"
        originals.mkdir(exist_ok=True)
        return SourceCache(
            source=source,
            root=root,
            pack0=pack0,
            inventory=inventory,
            originals=originals,
            resource_count=int(summary.get("resource_chunk_count", 0)),
            outer_entry_count=int(summary.get("outer_entry_count", 0)),
            kind_counts={str(key): int(value) for key, value in counts.items()},
        )

    def _extract_packs(self, source: Path, root: Path,
                       progress: IndexProgress | None) -> None:
        pack_folder = root / PACK_FOLDER
        pack_folder.mkdir(parents=True)
        descriptor = os.open(
            source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_CLOEXEC", 0))
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_size != SOURCE_SIZE:
                raise ValidationError("The XISO changed before indexing")
            entries, _ = xiso.parse_xdvdfs(descriptor, opened.st_size)
            packs = sorted(
                (entry for key, entry in entries.items()
                 if key.startswith("vc_53450030/") and not entry.attributes & 0x10),
                key=lambda entry: entry.path,
            )
            if [entry.path.rsplit("/", 1)[-1] for entry in packs] != list("0123456789ABCDEF"):
                raise ValidationError("The supported NFL 2K5 archive pack set is incomplete")
            total = sum(entry.size for entry in packs)
            completed = 0
            for entry in packs:
                name = entry.path.rsplit("/", 1)[-1]
                output = pack_folder / name
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | \
                    getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
                target_fd = os.open(output, flags, 0o600)
                try:
                    position = entry.byte_offset
                    remaining = entry.size
                    while remaining:
                        block = os.pread(descriptor, min(COPY_BLOCK, remaining), position)
                        if not block:
                            raise ValidationError(f"Short XISO read while indexing pack {name}")
                        view = memoryview(block)
                        while view:
                            written = os.write(target_fd, view)
                            if written <= 0:
                                raise ValidationError(f"Short cache write for pack {name}")
                            view = view[written:]
                        position += len(block)
                        remaining -= len(block)
                        completed += len(block)
                        _emit(progress, f"Indexing game files ({name})", completed, total)
                    os.fsync(target_fd)
                finally:
                    os.close(target_fd)
                if output.stat().st_size != entry.size:
                    raise ValidationError(f"Private cache size mismatch for pack {name}")
            current = os.fstat(descriptor)
            if (current.st_dev, current.st_ino, current.st_size) != \
                    (opened.st_dev, opened.st_ino, opened.st_size):
                raise ValidationError("The XISO changed during indexing")
        finally:
            os.close(descriptor)

    def _build_inventory(self, root: Path,
                         progress: IndexProgress | None) -> Path:
        inventory = root / INVENTORY_RELATIVE
        inventory.parent.mkdir(parents=True)
        _emit(progress, "Cataloging assets", 0, 1)
        command = [
            sys.executable,
            str(TOOLS / "nfl_resource_scan.py"),
            PACK_FOLDER.joinpath("0").as_posix(),
            "--json",
            str(inventory),
        ]
        result = subprocess.run(
            command,
            cwd=root,
            env={
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": os.defpath,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip().splitlines()
            raise ValidationError(
                "Could not catalog the game files: " +
                (message[-1] if message else "unknown scanner error")
            )
        _emit(progress, "Cataloging assets", 1, 1)
        return inventory

    @staticmethod
    def _pack_ledger(pack_folder: Path) -> list[dict[str, object]]:
        return [
            {"name": name, "size": (pack_folder / name).stat().st_size}
            for name in "0123456789ABCDEF"
        ]

    @staticmethod
    def _atomic_write_json(path: Path, value: object) -> None:
        payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temporary = path.with_name(f".{path.name}.tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        os.replace(temporary, path)

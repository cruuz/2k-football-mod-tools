"""Read-only APF source recognition and private ISO extraction."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Callable

from mod_editor.core import platform_compat

from .backend import PRODUCT_ROOT
from .models import ApfSource


Progress = Callable[[str, int, int], None]


def _xdvdfs_module():
    """The XDVDFS reader, imported the way the rest of the tree imports tools/."""
    tools = str(Path(__file__).resolve().parents[2] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import nfl_uniform_color_xiso_direct_patch as module
    except ImportError:  # pragma: no cover - lean checkouts without tools/
        return None
    return module

EXPECTED_0A_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_0A_SIZE = 1_140_850_688
EXPECTED_XEX_SHA256 = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
EXPECTED_ISO_SHA256 = "c45aab61de93773dfe25adbae5749ad5adb3f3369a6c0106b2159ad603b6fe53"
EXPECTED_GAME_FILES: dict[str, int] = {
    "0A": EXPECTED_0A_SIZE,
    "0B": 1_073_838_080,
    "1A": 1_140_850_688,
    "1B": 517_971_968,
    "default.xex": 38_408_192,
    "$SystemUpdate/su20076000_00000000": 7_299_072,
}
EXPECTED_GAME_HASHES: dict[str, str] = {
    "0A": EXPECTED_0A_SHA256,
    "0B": "775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53",
    "1A": "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb",
    "1B": "04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084",
    "default.xex": EXPECTED_XEX_SHA256,
    "$SystemUpdate/su20076000_00000000": "39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8",
}


class SourceError(ValueError):
    """Raised when a selected source is not the supported APF USA revision."""


def _noop_progress(_stage: str, _completed: int, _total: int) -> None:
    return None


def sha256_file(
    path: Path,
    progress: Progress = _noop_progress,
    *,
    stage: str = "Checking source",
) -> str:
    """Hash one stable regular file opened read-only and without following links."""

    supplied = path.lstat()
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise SourceError(f"{path.name} must be a regular, non-symlink file")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        # Windows CRT text mode collapses CRLF and treats 0x1A as a soft EOF, so
        # a binary source (every XISO/PNG) would hash short/wrong there and the
        # "changed after it was loaded" check would fire spuriously. O_BINARY is
        # 0 on POSIX, so Linux/macOS are byte-identical.
        | getattr(os, "O_BINARY", 0),
    )
    digest = hashlib.sha256()
    completed = 0
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            supplied.st_dev,
            supplied.st_ino,
            supplied.st_size,
        ):
            raise SourceError(f"{path.name} changed while it was being opened")
        total = opened.st_size
        while True:
            block = os.read(descriptor, 8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            completed += len(block)
            progress(stage, completed, total)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise SourceError(f"{path.name} changed while it was being read")
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def bundled_extract_xiso() -> Path:
    """The vendored extractor for the running OS.

    Both binaries are built from the same vendored extract-xiso 2.7.1 source and
    ship side by side: the ELF for Linux, and ``extract-xiso.exe`` -- a PE32+
    x86-64 console build -- for Windows.  Picking by platform is what lets a
    Windows user hand the app a ``.iso`` directly instead of having to extract it
    themselves or supply their own build of the extractor.

    macOS is deliberately not covered.  Neither bundled binary can run there and
    shipping one would mean vendoring a third architecture we cannot test, so a
    macOS user still points the app at an already-extracted game folder or sets
    ``extract_xiso`` to their own build.  The path is returned regardless; the
    caller reports a missing or non-executable extractor rather than this
    function guessing.
    """

    build = PRODUCT_ROOT / "tools" / "vendor" / "extract-xiso" / "build"
    if platform_compat.IS_WINDOWS:
        return build / "extract-xiso.exe"
    return build / "extract-xiso"


@dataclass
class SourceManager:
    cache_root: Path | None = None
    extract_xiso: Path | None = None

    def __post_init__(self) -> None:
        if self.cache_root is None:
            self.cache_root = Path.home() / ".cache" / "apf2k8-mod-studio"
        if self.extract_xiso is None:
            self.extract_xiso = bundled_extract_xiso()

    def resolve(
        self,
        selected: Path,
        progress: Progress = _noop_progress,
    ) -> ApfSource:
        selected = selected.expanduser().resolve(strict=True)
        extracted_from_iso = False
        source_iso_sha256: str | None = None
        if selected.is_dir():
            root = selected
        elif selected.name in EXPECTED_GAME_FILES:
            root = selected.parent
        elif selected.suffix.lower() in {".iso", ".xiso"} or selected.name.lower().endswith(
            ".xiso.iso"
        ):
            source_iso_sha256 = sha256_file(
                selected, progress, stage="Checking APF disc image"
            )
            # The container hash is recorded and used as the extraction-cache
            # key, but it is NOT a gate. Xbox 360 dumps vary at least as much as
            # original-Xbox ones, and the real identity check already happens
            # after extraction, against the per-file ledger (0A/0B/1A/1B and
            # default.xex, by exact size and hash). Gating on the wrapper here
            # refused legal dumps before that stronger check could ever run --
            # the same defect the 2K5 side was fixed for.
            root = self._extract_iso(selected, source_iso_sha256, progress)
            extracted_from_iso = True
        else:
            raise SourceError(
                "Choose the APF game folder, its 0A file, or the original APF ISO."
            )
        return self._validate_root(
            selected,
            root,
            progress,
            extracted_from_iso=extracted_from_iso,
            source_iso_sha256=source_iso_sha256,
        )

    def _validate_root(
        self,
        selected: Path,
        root: Path,
        progress: Progress,
        *,
        extracted_from_iso: bool,
        source_iso_sha256: str | None,
    ) -> ApfSource:
        root = root.resolve(strict=True)
        for name, expected_size in EXPECTED_GAME_FILES.items():
            path = root / name
            try:
                item = path.lstat()
            except FileNotFoundError as exc:
                raise SourceError(f"The selected game is missing {name}.") from exc
            if not stat.S_ISREG(item.st_mode) or stat.S_ISLNK(item.st_mode):
                raise SourceError(f"{name} must be a regular, non-symlink file")
            if item.st_size != expected_size:
                raise SourceError(
                    f"{name} has the wrong size for the supported APF USA revision."
                )
        index = root / "0A"
        digest = sha256_file(index, progress, stage="Recognizing APF game data")
        if digest != EXPECTED_0A_SHA256:
            raise SourceError(
                "0A does not match the supported untouched APF USA revision. "
                "Load the original extracted game, not a previously modified copy."
            )
        hashes = self._validate_complete_ledger(root, digest, progress)
        xex_digest = hashes["default.xex"]
        return ApfSource(
            selected_path=selected,
            game_root=root,
            index_0a=index,
            source_sha256=digest,
            source_size=EXPECTED_0A_SIZE,
            xex_sha256=xex_digest,
            display_name="All-Pro Football 2K8 (USA)",
            extracted_from_iso=extracted_from_iso,
            source_iso_sha256=source_iso_sha256,
        )

    def _validate_complete_ledger(
        self, root: Path, digest_0a: str, progress: Progress
    ) -> dict[str, str]:
        """Hash every boot payload once, then reuse a stat-bound private receipt."""

        assert self.cache_root is not None
        receipt_path = self.cache_root / "source-ledgers" / f"{digest_0a}.json"
        current_stats: dict[str, dict[str, int]] = {}
        for relative in EXPECTED_GAME_FILES:
            value = (root / relative).stat()
            current_stats[relative] = {
                "device": value.st_dev,
                "inode": value.st_ino,
                "size": value.st_size,
                "mtime_ns": value.st_mtime_ns,
            }
        if receipt_path.is_file():
            try:
                import json

                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                if (
                    receipt.get("schema") == "apf2k8_mod_studio_source_ledger/v1"
                    and receipt.get("files") == current_stats
                    and receipt.get("hashes") == EXPECTED_GAME_HASHES
                ):
                    return dict(EXPECTED_GAME_HASHES)
            except (OSError, ValueError, TypeError):
                pass
        hashes = {"0A": digest_0a}
        remaining = [name for name in EXPECTED_GAME_FILES if name != "0A"]
        for index, relative in enumerate(remaining, start=1):
            progress("Verifying every APF game file", index - 1, len(remaining))
            hashes[relative] = sha256_file(
                root / relative, stage=f"Checking {relative}"
            )
            if hashes[relative] != EXPECTED_GAME_HASHES[relative]:
                raise SourceError(
                    f"{relative} does not match the supported APF USA revision"
                )
        progress("Verifying every APF game file", len(remaining), len(remaining))
        if hashes != EXPECTED_GAME_HASHES:
            raise SourceError("The APF source ledger is incomplete")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{receipt_path.name}.",
            suffix=".tmp",
            dir=receipt_path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(
                    (
                        json.dumps(
                            {
                                "schema": "apf2k8_mod_studio_source_ledger/v1",
                                "files": current_stats,
                                "hashes": hashes,
                                "retail_bytes_cached": False,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, receipt_path)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise
        return hashes

    def _extract_native(
        self, source_iso: Path, staging: Path, progress: Progress
    ) -> tuple[str, bool] | None:
        """Copy the six files the editor reads straight out of the image.

        Returns ``None`` on success, or a human-readable reason it could not be
        done, in which case the caller falls back to the bundled extractor.

        The bundled ``extract-xiso`` probes exactly four partition offsets --
        0, 0x0FD90000, 0x02080000, 0x18300000 -- and calls anything else "not a
        valid xbox iso image".  That is the same defect the 2K5 source lane was
        fixed for: a layout measured on one machine treated as the only legal
        layout.  A dump is not one canonical file, and a list of four guesses is
        still guessing.  Our reader *searches* sector-aligned positions for the
        XDVDFS magic and confirms a candidate by requiring it at both ends of
        the header sector plus a root directory that fits inside the image, so
        it accepts a strict superset of what the bundled tool accepts.

        It is also much cheaper: the editor reads six files, and unpacking the
        whole disc to get them costs several gigabytes of disk and minutes of
        wall clock that this path does not spend.
        """
        xiso = _xdvdfs_module()
        if xiso is None:  # pragma: no cover - lean checkouts without tools/
            return ("the XDVDFS reader is not installed", False)
        try:
            descriptor = os.open(
                source_iso, os.O_RDONLY | getattr(os, "O_BINARY", 0)
            )
        except OSError as exc:
            return (f"the disc image could not be opened ({exc.strerror})", False)
        try:
            image_size = os.fstat(descriptor).st_size
            base = xiso.locate_xdvdfs_base(
                descriptor, image_size, require_entry="default.xex"
            )
            entries, _ = xiso.parse_xdvdfs(descriptor, image_size, base)
            by_name = {name.lower(): entry for name, entry in entries.items()}
            wanted: list[tuple[str, object, int]] = []
            for name, expected_size in EXPECTED_GAME_FILES.items():
                entry = by_name.get(name.lower())
                if entry is None:
                    return (f"the image does not contain {name}", False)
                if entry.size != expected_size:
                    return (f"{name} has the wrong size for the supported APF USA revision", False)
                wanted.append((name, entry, expected_size))
            total = sum(size for _, _, size in wanted)
            done = 0
            for name, entry, expected_size in wanted:
                target = staging.joinpath(*name.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                offset = entry.byte_offset
                remaining = expected_size
                with open(target, "wb") as handle:
                    while remaining:
                        count = min(4 << 20, remaining)
                        handle.write(xiso.pread(descriptor, count, offset))
                        offset += count
                        remaining -= count
                        done += count
                        progress("Extracting APF ISO into a private cache", done, total)
        except (OSError, ValueError) as exc:
            # A positively identified non-Xbox container is a final answer.
            # Running the bundled extractor after it can only append a second,
            # vaguer failure that buries the one sentence the user needs.
            identified = False
            try:
                identified = (
                    xiso.identify_non_xdvdfs_image(descriptor, image_size) is not None
                )
            except Exception:  # pragma: no cover - identification is advisory
                identified = False
            return (str(exc), identified)
        finally:
            os.close(descriptor)
        return None

    def _extract_with_bundled_tool(
        self,
        source_iso: Path,
        staging: Path,
        progress: Progress,
        native_error: str,
    ) -> None:
        """Last resort: unpack the whole disc with the bundled extract-xiso."""
        for leftover in sorted(staging.iterdir(), reverse=True):
            if leftover.is_dir() and not leftover.is_symlink():
                shutil.rmtree(leftover, ignore_errors=True)
            else:
                leftover.unlink()
        if self.extract_xiso is None:
            raise SourceError(f"APF ISO extraction failed: {native_error}")
        try:
            tool = self.extract_xiso.resolve(strict=True)
        except OSError as exc:
            raise SourceError(
                f"APF ISO extraction failed: {native_error}"
            ) from exc
        tool_mode = tool.lstat().st_mode
        if not stat.S_ISREG(tool_mode) or stat.S_ISLNK(tool_mode) or not os.access(tool, os.X_OK):
            raise SourceError("The bundled APF ISO extractor is unavailable")
        result = subprocess.run(
            [str(tool), "-q", "-d", str(staging), str(source_iso)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            # Report BOTH attempts. "does not appear to be a valid xbox iso
            # image" on its own sends people off to re-dump a disc that is
            # usually fine, when what actually happened is that neither reader
            # could find a filesystem where it looked.
            raise SourceError(
                "APF ISO extraction failed: "
                + native_error
                + (f"; the bundled extractor also failed: {detail[-300:]}" if detail else "")
            )

    def _extract_iso(
        self,
        source_iso: Path,
        source_iso_sha256: str,
        progress: Progress,
    ) -> Path:
        assert self.cache_root is not None
        sources = self.cache_root / "sources"
        destination = sources / source_iso_sha256 / "game"
        cache_complete = all(
            (destination / relative).is_file()
            and (destination / relative).stat().st_size == expected_size
            for relative, expected_size in EXPECTED_GAME_FILES.items()
        )
        if cache_complete:
            return destination
        if destination.exists() or destination.is_symlink():
            # Only this private, content-addressed extraction cache is removed.
            # Recover automatically from a prior interrupted/invalid extraction.
            if destination.is_symlink():
                destination.unlink()
            else:
                shutil.rmtree(destination)
        sources.mkdir(parents=True, exist_ok=True)
        parent = destination.parent
        parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="extracting-", dir=parent))
        progress("Extracting APF ISO into a private cache", 0, 0)
        try:
            native = self._extract_native(source_iso, staging, progress)
            if native is not None:
                native_error, definitive = native
                if definitive:
                    raise SourceError(f"APF ISO extraction failed: {native_error}")
                self._extract_with_bundled_tool(
                    source_iso, staging, progress, native_error
                )
            candidate = staging
            if not (candidate / "0A").is_file():
                matches = list(staging.rglob("0A"))
                matches = [item for item in matches if item.parent.is_dir()]
                if len(matches) != 1:
                    raise SourceError("The extracted ISO did not contain one recognizable APF game")
                candidate = matches[0].parent
            if destination.exists():
                if (destination / "0A").is_file():
                    return destination
                raise SourceError("The private APF extraction cache is incomplete")
            # Windows MoveFileEx cannot rename onto an existing directory, so
            # publish through the platform layer rather than os.replace here.
            if candidate == staging:
                platform_compat.publish_no_replace(
                    staging, destination, is_directory=True, require_atomic=False
                )
            else:
                platform_compat.publish_no_replace(
                    candidate, destination, is_directory=True, require_atomic=False
                )
                shutil.rmtree(staging, ignore_errors=True)
            progress("APF ISO extraction complete", 1, 1)
            return destination
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

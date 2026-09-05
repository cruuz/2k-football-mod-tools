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
import stat
import subprocess
import sys
import tempfile
from typing import Callable

from .errors import ValidationError
from .model import GameId, SourceRecord
from . import platform_compat
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
# Where pack 0 sat in the pinned retail rip (sector 796,479 of an extracted .xiso).  Recorded in
# prepared-edit targets as provenance ONLY: the build (nfl2k5_visual_mod_project.bind_prepared_to_source)
# derives every absolute offset from the pack's position in the image actually being written,
# because a raw dump or a rebuilt image puts the same pack elsewhere.
PACK0_RETAIL_SECTOR = 796_479
PACK0_RETAIL_BYTE_OFFSET = PACK0_RETAIL_SECTOR * 2048
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
    """Where the private, XISO-derived cache lives, per platform.

    POSIX keeps the historical ``~/.cache/2k5-mod-studio``; its confidentiality
    comes from the ``0o700`` mode bits on the directories inside it.

    Windows has no mode bits to rely on, so the location is where the guarantee
    is expected to come from -- and it is verified rather than assumed, by
    ``platform_compat.verify_private_root_placement``, which reads the root's
    DACL and refuses one that does not restrict access.  The location alone
    would not be enough: the
    cache goes under ``%LOCALAPPDATA%`` (``platform_compat.user_private_root``),
    the per-user application-data root whose ACL is expected to exclude other
    accounts and to be inherited by everything created beneath it -- an
    expectation that ``platform_compat.verify_private_root_placement`` actually
    verifies by reading the DACL, rather than one this choice of location
    assumes on its own.  ``~/.cache`` on Windows would be
    an ordinary folder under the profile with no such intent, and on a machine
    with a roaming profile it would also sync the user's game-derived cache to a
    file server.  Both platforms therefore satisfy
    :func:`~mod_editor.core.platform_compat.is_within_user_private_root`.
    """

    if platform_compat.IS_WINDOWS:
        return platform_compat.user_private_root() / "2k5-mod-studio" / "cache"
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


def _is_reparse_point(info: os.stat_result) -> bool:
    """Whether an ``lstat`` result denotes a Windows reparse point (junction).

    A directory *junction* -- and every other reparse point except a symlink --
    is NOT reported by ``lstat``/``S_ISLNK`` as a link, so a junction planted in
    place of a private cache path slips past a symlink-only guard and can
    redirect game-derived bytes into a shared or attacker-controlled tree.  On
    Windows ``os.lstat`` sets ``st_reparse_tag`` to a non-zero tag for any
    reparse point (mount-point junction, symlink, ...); on POSIX the attribute is
    absent, so this is ``False`` and the symlink-only behaviour is byte-for-byte
    unchanged there.  Mirrors the ``FILE_ATTRIBUTE_REPARSE_POINT`` refusal the
    Windows ``DirHandle`` already applies in ``platform_compat`` (which is the
    intended shared home for this predicate once it exposes one).
    """

    return getattr(info, "st_reparse_tag", 0) != 0


def _regular_non_symlink(path: Path, label: str) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} is missing: {path}") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or _is_reparse_point(info)
    ):
        raise ValidationError(f"{label} must be a regular, non-link file: {path}")
    return info


class Nfl2k5SourceCache:
    """Recognize an XISO and materialize its archive packs atomically."""

    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = (cache_root or default_cache_root()).expanduser()
        self.inspector = SourceInspector()

    def _ensure_private_cache_root(self) -> None:
        """Create (or accept) the private cache root through the DACL-applying
        creator, then verify its *real* confidentiality -- never a bare ``mkdir``.

        POSIX: :func:`platform_compat.create_private_directory` is ``mkdir`` mode
        ``0o700``.  The per-XISO subdirectories carry the historical owner-only
        guarantee, so the placement re-check below is a deliberate no-op here and
        Linux behaviour is unchanged apart from the root now being created
        owner-only rather than umask-default.

        Windows: the same call applies a current-user/administrators-only ACL to
        a freshly created root (Python 3.13+ translates ``mode=0o700`` into that
        DACL), and :func:`platform_compat.verify_private_root_placement` then
        QUERIES the directory's actual DACL and fails closed if any
        Everyone/Users/other-account ACE grants access, or the ACL cannot be
        read.  That DACL query -- not mere realpath containment under
        ``%LOCALAPPDATA%`` -- is what closes the two Windows escapes: a
        pre-existing world-readable ``%LOCALAPPDATA%``/``%TEMP%`` cache dir with
        an inherited Users/Everyone ACE, and a hostile ``LOCALAPPDATA`` that
        points the profile root *at the cache root itself* so ``candidate ==
        trusted-root`` would otherwise pass unconditionally.  Because the
        guarantee is the DACL of this exact directory, the candidate can never be
        trusted merely for being its own configured root.
        """

        platform_compat.create_private_directory(
            self.cache_root, parents=True, exist_ok=True
        )
        platform_compat.verify_private_root_placement(
            self.cache_root, "The private NFL 2K5 source cache root"
        )

    def index(self, source_xiso: Path,
              progress: IndexProgress | None = None) -> SourceCache:
        selected = source_xiso.expanduser().resolve(strict=True)
        _regular_non_symlink(selected, "NFL 2K5 XISO")

        def hash_progress(completed: int, total: int) -> None:
            _emit(progress, "Checking your XISO", completed, total)

        # Deliberately no whole-file size or SHA-256 gate here any more. Dumps of
        # one disc legitimately differ -- where the game partition starts, how
        # much padding survives, how the ripper closed the image -- and pinning
        # the container turned every one of those into "this is not the USA
        # version" for people holding a perfectly legal copy. Identity now comes
        # from the executable inside the image, and the guarantee that actually
        # protects the writers is unchanged and enforced below: every archive
        # pack extracted from this image must hash to its pinned value, and the
        # generated inventory must hash to its pinned value, or nothing is
        # published. Those checks are strictly stronger than a container hash,
        # because they cover the bytes the writers really touch.
        source = self.inspector.inspect(selected, GameId.NFL2K5, hash_progress)
        if (
            not source.recognized
            or source.fingerprint_id != "nfl2k5-usa-retail-xiso"
            or source.kind != "xiso"
        ):
            raise ValidationError(
                "This file does not contain the USA retail NFL 2K5 Xbox game. "
                "2K5 Mod Studio reads the game's default.xbe out of the image to "
                "identify it, so any layout of a USA retail dump is accepted -- an "
                "extracted .xiso or a raw disc read, padded or trimmed. Nothing "
                "here was modified."
            )

        self._ensure_private_cache_root()
        final = self.cache_root / SOURCE_SHA256
        cached = self._load_existing(final, source)
        if cached is not None:
            _emit(progress, "Game index ready", 1, 1)
            return cached

        temporary = Path(tempfile.mkdtemp(
            prefix=f".{SOURCE_SHA256[:12]}.indexing-", dir=self.cache_root))
        try:
            # ``mkdtemp`` creates 0o700 on POSIX and an ordinary directory on
            # Windows, which has no directory modes; re-verify whichever of
            # those this platform actually promises before any game bytes land
            # in it.  Inside the try so a refusal still removes the staging tree.
            self._require_private_directory(
                temporary, "The private NFL 2K5 indexing staging directory"
            )
            self._extract_packs(selected, temporary, progress, source.size)
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
                platform_compat.remove_private_tree(temporary)
                return existing
        except BaseException:
            if temporary.exists():
                # Not ``shutil.rmtree``: the staging tree holds files this
                # product deliberately makes read-only, which Windows refuses to
                # delete at all.  The helper clears that attribute first there
                # and is exactly ``shutil.rmtree`` on POSIX.
                platform_compat.remove_private_tree(temporary)
            raise
        result = self._load_existing(final, source)
        if result is None:
            raise ValidationError("Game index publication failed")
        _emit(progress, "Game index ready", 1, 1)
        return result

    @staticmethod
    def _require_private_directory(path: Path, label: str) -> None:
        """Re-verify a private staging directory in this platform's own terms.

        POSIX: the unchanged owner-only ``0o700`` assertion.  Windows:
        directories carry no mode there, so the check is that this is a real,
        non-reparse-point directory inheriting the cache root's ACL -- the
        strongest guarantee that platform offers, named by
        :func:`~mod_editor.core.platform_compat.privacy_guarantee` rather than
        quietly skipped.
        """

        try:
            platform_compat.verify_private_directory(path, label)
        except platform_compat.PrivatePathError as exc:
            raise ValidationError(str(exc)) from exc

    @staticmethod
    def _require_private_file(path: Path, label: str, *, fd: int | None = None) -> None:
        """Re-verify a private staging file in this platform's own terms.

        ``0o600`` on POSIX.  On Windows the same file reads back ``0o666``,
        because the only permission bit there is owner-write; that honest value
        is asserted instead, and it confers no privacy -- the cache root's ACL
        does (see :func:`default_cache_root`).
        """

        try:
            platform_compat.verify_private_file(path, label, fd=fd)
        except platform_compat.PrivatePathError as exc:
            raise ValidationError(str(exc)) from exc

    def _load_existing(self, root: Path, source: SourceRecord) -> SourceCache | None:
        # A pre-existing cache root is attacker-reachable: refuse to read one
        # that is a symlink or a Windows junction/reparse point (which S_ISLNK
        # would miss) before trusting anything inside it.  A missing root is
        # simply "no cache yet".
        try:
            root_info = os.lstat(root)
        except OSError:
            return None
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or stat.S_ISLNK(root_info.st_mode)
            or _is_reparse_point(root_info)
        ):
            return None
        marker_path = root / "cache.json"
        if (
            not marker_path.is_file()
            or marker_path.is_symlink()
            or _is_reparse_point(os.lstat(marker_path))
        ):
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
            or _is_reparse_point(os.lstat(inventory))
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
                       progress: IndexProgress | None,
                       expected_size: int) -> None:
        pack_folder = root / PACK_FOLDER
        pack_folder.mkdir(parents=True)
        descriptor = os.open(
            source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
            getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
        try:
            opened = os.fstat(descriptor)
            # Only that this is still a regular file of the size we inspected.
            # Comparing against SOURCE_SIZE would reject every dump whose
            # container differs from the project's own copy, which is the whole
            # defect being fixed; what the packs must be is enforced by hash
            # after extraction, and the re-stat below catches a swap mid-read.
            if not stat.S_ISREG(opened.st_mode) or opened.st_size != expected_size:
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
                target_fd = os.open(output, flags | getattr(os, "O_BINARY", 0), 0o600)
                try:
                    position = entry.byte_offset
                    remaining = entry.size
                    while remaining:
                        block = platform_compat.pread(descriptor, min(COPY_BLOCK, remaining), position)
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
                # The 0o600 creation mode above is still filtered through umask
                # on POSIX and reduced to "not read-only" on Windows, so harden
                # the pack and re-verify it against what this platform can
                # actually promise before it is published.
                platform_compat.harden_private_file(output)
                self._require_private_file(
                    output, f"The private NFL 2K5 archive pack {name}"
                )
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
        temporary = platform_compat.temporary_sibling(path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags | getattr(os, "O_BINARY", 0), 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        # Same reasoning as the archive packs: the creation mode is advisory on
        # both platforms, so the staged marker is hardened and re-verified in
        # this platform's own terms before it becomes the published cache.json.
        platform_compat.harden_private_file(temporary)
        Nfl2k5SourceCache._require_private_file(
            temporary, "The private NFL 2K5 cache marker"
        )
        os.replace(temporary, path)

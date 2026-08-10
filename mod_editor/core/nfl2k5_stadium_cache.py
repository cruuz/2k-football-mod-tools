"""Private, resumable Stadium Studio derivation from one :class:`SourceCache`.

The desktop product must not depend on the repository's research ``assets`` or
``reports`` trees.  This coordinator therefore invokes a fixed, shipped worker
with only the private pack-0 archive and resource inventory already derived
from the user's recognized XISO.  The worker writes beneath that same private
cache; no caller-selected export path and no shareable-project path exists in
this API.

Publication is a same-filesystem directory rename.  A failed or interrupted
worker leaves only a versioned staging directory, which the worker can resume
scene-by-scene on the next call.  A completed directory is accepted only after
its result marker and both product manifests are independently checked.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
from typing import Callable, Protocol, Sequence

from . import platform_compat
from .errors import ValidationError
from .nfl2k5_build_service import (
    WINDOWS_CREATE_SUSPENDED,
    WindowsProcessGroup,
    adopt_process_group,
    stop_windows_process_group,
    use_suspended_launch,
)
from .nfl2k5_source_cache import SOURCE_SHA256, SourceCache
from .platform_compat import (
    PrivatePathError,
    create_private_directory,
    exclusive_nonblocking_lock,
    fsync_directory,
    harden_private_directory,
    harden_private_file,
    privacy_guarantee,
    release_lock,
    verify_private_directory,
    verify_private_file,
)


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "tools/nfl_stadium_studio_cache.py"
RESULT_SCHEMA = "2k5_mod_studio_stadium_cache_result/v1"
GLTF_MANIFEST_SCHEMA = "nfl2k5_static_gltf_manifest/v2"
TEXTURE_MANIFEST_SCHEMA = "nfl2k5_scne_embedded_texture_png/v1"
PRIVATE_PARENT = "derived"
FINAL_NAME = "stadium-studio-v1"
STAGING_NAME = ".stadium-studio-v1.staging"
LOCK_NAME = ".stadium-studio-v1.lock"
EXPECTED_STADIUM_SCENES = 477
ESTIMATED_PRIVATE_BYTES = 750 * 1024**2
DEFAULT_FREE_SPACE_RESERVE = 1024**3
ESTIMATED_SECONDS_LOW = 10 * 60
ESTIMATED_SECONDS_HIGH = 30 * 60
COPY_BLOCK = 1024 * 1024


ProgressSink = Callable[[str, int, int], None]


class StadiumCacheError(ValidationError):
    """A private cache could not be generated or safely accepted."""


class StadiumCacheFindingsError(StadiumCacheError):
    """The bounded worker reached an honest decoder or ownership boundary."""


class StadiumCacheStaleError(StadiumCacheError):
    """A previously derived private cache no longer matches this build.

    Kept distinct from every other cache error because the correct response
    differs.  A safety failure -- a symlink, a reparse point, a path outside
    the private root -- must refuse and stay refused.  Staleness must not: this
    cache is derived from the user's own game and is fully reproducible, so the
    only right answer is to discard it and derive again.

    This class exists because it did not.  Beta 30 rebound derived stadium
    assets to the canonical game-content identity instead of a container hash,
    which was the correct fix, and left every cache written before that change
    failing its own marker check with no way back.  Anyone who had already
    opened Stadium Studio then met "result marker is incompatible or
    incomplete" on every launch, on a game that used to work, with the only
    remedy being to delete a private directory nobody had told them about.
    """


@dataclass(frozen=True)
class WorkerCommandResult:
    returncode: int
    output: tuple[str, ...]


class StadiumCacheWorkerRunner(Protocol):
    """Injectable process boundary used by synthetic product tests."""

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        progress: ProgressSink,
    ) -> WorkerCommandResult: ...


@dataclass(frozen=True)
class StadiumCacheResult:
    """Validated paths to retail-derived files that stay under SourceCache.root."""

    root: Path
    gltf_manifest: Path
    texture_manifest: Path
    texture_root: Path
    scene_count: int
    exported_scene_count: int
    texture_occurrence_count: int
    unique_png_count: int
    derived_payload_bytes: int
    resumed_scene_count: int
    private: bool = True
    shareable: bool = False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(COPY_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_reparse_point(info: os.stat_result) -> bool:
    """Whether an ``lstat`` result denotes a Windows reparse point (junction).

    A directory *junction* -- and every other reparse point except a symlink --
    is NOT reported by ``lstat``/``S_ISLNK`` as a link, so a junction planted in
    place of a private cache directory slips past a symlink-only guard and
    redirects derived bytes and lock files into a shared or attacker-controlled
    tree.  On Windows ``os.lstat`` sets ``st_reparse_tag`` to a non-zero tag for
    any reparse point; on POSIX the attribute is absent, so this is ``False`` and
    the symlink-only behaviour is byte-for-byte unchanged.  Mirrors the
    ``FILE_ATTRIBUTE_REPARSE_POINT`` refusal the Windows ``DirHandle`` already
    applies in ``platform_compat`` (the intended shared home for this predicate).
    """

    return getattr(info, "st_reparse_tag", 0) != 0


def _regular_file(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise StadiumCacheError(f"{label} is missing: {path}") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or _is_reparse_point(info)
    ):
        raise StadiumCacheError(f"{label} must be a regular, non-link file: {path}")
    return path.resolve(strict=True)


def _confined_file(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise StadiumCacheError(f"Private Stadium Studio result has no {label} path")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise StadiumCacheError(f"Private Stadium Studio {label} path is unsafe")
    resolved_root = root.resolve(strict=True)
    path = _regular_file(resolved_root / part, label)
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise StadiumCacheError(f"Private Stadium Studio {label} escapes its cache") from exc
    return path


def _confined_directory(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise StadiumCacheError(f"Private Stadium Studio result has no {label} path")
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise StadiumCacheError(f"Private Stadium Studio {label} path is unsafe")
    resolved_root = root.resolve(strict=True)
    candidate = resolved_root / part
    try:
        info = candidate.lstat()
    except FileNotFoundError as exc:
        raise StadiumCacheError(f"{label} directory is missing: {candidate}") from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or _is_reparse_point(info)
    ):
        raise StadiumCacheError(f"{label} must be a private, non-link directory")
    path = candidate.resolve(strict=True)
    try:
        path.relative_to(resolved_root)
    except ValueError as exc:
        raise StadiumCacheError(f"Private Stadium Studio {label} escapes its cache") from exc
    return path


def _read_json(path: Path, label: str) -> dict[str, object]:
    _regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StadiumCacheError(f"Could not read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise StadiumCacheError(f"{label} is not a JSON object")
    return value


def _positive_int(value: object, label: str, *, allow_zero: bool = True) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise StadiumCacheError(f"Private Stadium Studio result has an invalid {label}")
    return value


def _worker_findings(output: tuple[str, ...]) -> str:
    prefix = "STADIUM_CACHE_FINDINGS "
    for line in reversed(output):
        if not line.startswith(prefix):
            continue
        payload = line[len(prefix):]
        try:
            document = json.loads(payload)
        except json.JSONDecodeError:
            return payload
        if isinstance(document, dict):
            message = document.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return payload
    return output[-1] if output else "worker stopped without details"


class SubprocessStadiumCacheWorkerRunner:
    """Run the fixed worker without a shell and forward structured progress."""

    _environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        progress: ProgressSink,
    ) -> WorkerCommandResult:
        fixed = tuple(os.fspath(value) for value in argv)
        suspended = use_suspended_launch()
        try:
            process = subprocess.Popen(
                fixed,
                cwd=cwd,
                env=self._environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,
                # POSIX only; silently ignored on Windows, where the job object
                # adopted below supplies the same reach.
                start_new_session=True,
                # Windows only (``0`` -- the default -- everywhere else, so the
                # POSIX launch is byte-for-byte the one it always was): freeze
                # the child so it is sealed into the job before it can spawn a
                # descendant; ``adopt_process_group`` resumes it.
                creationflags=WINDOWS_CREATE_SUSPENDED if suspended else 0,
                bufsize=1,
            )
        except OSError as exc:
            raise StadiumCacheFindingsError(
                "Stadium Studio could not start its private asset generator. "
                f"The shipped worker may be missing or unreadable ({exc})."
            ) from exc
        group = adopt_process_group(process, was_suspended=suspended)
        lines: list[str] = []
        try:
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip("\r\n")
                if line:
                    lines.append(line)
                    if len(lines) > 160:
                        del lines[:40]
                prefix = "STADIUM_CACHE_PROGRESS "
                if line.startswith(prefix):
                    try:
                        event = json.loads(line[len(prefix):])
                        stage = str(event["stage"])
                        completed = int(event["completed"])
                        total = int(event["total"])
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
                    progress(stage, completed, total)
            returncode = process.wait()
        except BaseException:
            # The worker owns only paths below the private cache's staging
            # directory.  Stop its whole process group before control returns
            # to the coordinator, which may remove or resume that directory.
            self._stop_process_group(process, group)
            raise
        # The worker has exited.  POSIX leaves the group alone on this path and
        # always has; Windows has one extra thing to do -- release the job
        # handle it would otherwise leak.
        if group is not None:
            group.close()
        return WorkerCommandResult(returncode, tuple(lines))

    @staticmethod
    def _stop_process_group(
        process: subprocess.Popen[str],
        group: WindowsProcessGroup | None = None,
    ) -> None:
        """Stop the worker and every descendant it started, on both models.

        POSIX signals the session-owned process group exactly as it always has.
        Windows has neither ``os.killpg`` nor ``signal.SIGKILL`` -- reaching for
        either raised ``AttributeError`` out of this teardown, so it stopped
        nothing and a runaway worker kept writing into the private cache -- and
        instead terminates and drains the job object the worker was adopted
        into; see the note above
        :class:`~mod_editor.core.nfl2k5_build_service.WindowsProcessGroup`.
        """

        if platform_compat.IS_WINDOWS:
            # Deliberately ahead of the "direct child already exited" shortcut
            # below: on Windows the job can still hold descendants the exited
            # worker started, and those are what would keep writing into the
            # private cache the coordinator is about to publish or clean up.
            if not stop_windows_process_group(process, group):
                raise StadiumCacheError(
                    "Stadium Studio could not stop its private asset generator; "
                    "a background process may still be writing into the private "
                    "cache. Sign out or restart Windows before trying again."
                )
            return
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()


class Nfl2k5StadiumCacheCoordinator:
    """Generate or reuse the versioned private Stadium Studio cache."""

    def __init__(
        self,
        *,
        runner: StadiumCacheWorkerRunner | None = None,
        worker: Path = WORKER,
        free_space_reserve: int = DEFAULT_FREE_SPACE_RESERVE,
    ) -> None:
        if isinstance(free_space_reserve, bool) or not isinstance(
            free_space_reserve, int
        ) or free_space_reserve < 0:
            raise ValueError("free_space_reserve must be zero or greater")
        self.runner = runner or SubprocessStadiumCacheWorkerRunner()
        self.worker = worker
        self.free_space_reserve = free_space_reserve

    def load_existing(self, cache: SourceCache) -> StadiumCacheResult | None:
        """Return a completed cache without starting derivation."""

        root, _pack0, _inventory = self._validate_source_cache(cache)
        final = root / PRIVATE_PARENT / FINAL_NAME
        if not final.exists():
            return None
        # Every admitted container is reduced to the same independently pinned
        # pack/inventory cache.  Bind derived assets to that canonical content,
        # not to padding/layout bytes in whichever legal XISO was selected.
        try:
            return self._validate_result(final, SOURCE_SHA256)
        except StadiumCacheStaleError:
            # This accessor promises "already built", and a cache this build
            # cannot read is not built. Reporting "nothing yet" sends the caller
            # to ensure(), which rebuilds it; raising here would make every
            # read-only probe fail on a game that only needs re-deriving.
            return None

    def ensure(
        self,
        cache: SourceCache,
        progress: ProgressSink | None = None,
    ) -> StadiumCacheResult:
        """Build once, resume after interruption, then publish atomically."""

        sink = progress or (lambda _stage, _completed, _total: None)
        root, pack0, inventory = self._validate_source_cache(cache)
        parent = root / PRIVATE_PARENT
        create_private_directory(parent, parents=True, exist_ok=True)
        # A symlink OR a Windows junction/reparse point here would redirect the
        # whole private derived cache -- and its single-writer lock -- into an
        # attacker tree; S_ISLNK alone misses a junction, so refuse any reparse
        # point too.  os.lstat carries st_reparse_tag on Windows and nothing on
        # POSIX, keeping the Linux path byte-identical.
        parent_info = os.lstat(parent)
        if stat.S_ISLNK(parent_info.st_mode) or _is_reparse_point(parent_info):
            raise StadiumCacheError(
                "Private derived-cache directory cannot be a symlink or reparse "
                "point (junction)"
            )
        harden_private_directory(parent)
        self._require_private_directory(parent, "The private derived-cache directory")
        lock_path = parent / LOCK_NAME
        lock_fd = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            # The creation mode above is subject to umask on POSIX and decides
            # only the read-only attribute on Windows, so the lock file is
            # hardened and then re-verified against whatever this platform can
            # actually promise.  Done before the lock is taken so a failure
            # cannot leave an unlocked descriptor to release.
            harden_private_file(lock_path)
            self._require_private_file(
                lock_path,
                "The Stadium Studio single-writer lock file",
                fd=lock_fd,
            )
        except BaseException:
            os.close(lock_fd)
            raise
        try:
            try:
                exclusive_nonblocking_lock(lock_fd)
            except BlockingIOError as exc:
                raise StadiumCacheError(
                    "Stadium Studio assets are already being prepared by another "
                    "2K5 Mod Studio window. Let that operation finish and try again."
                ) from exc
            final = parent / FINAL_NAME
            if final.exists():
                try:
                    result = self._validate_result(final, SOURCE_SHA256)
                except StadiumCacheStaleError:
                    # Derived from the user's own game and reproducible, so a
                    # cache this build cannot read is a rebuild, not a wall.
                    # Only staleness reaches here; a safety refusal from
                    # _validate_result is a different class and still propagates.
                    sink("Rebuilding out-of-date private Stadium Studio assets", 0, 1)
                    self._discard_stale_final(final)
                else:
                    sink("Stadium Studio private assets ready", 1, 1)
                    return result
            staging = parent / STAGING_NAME
            if staging.exists():
                info = staging.lstat()
                if (
                    not stat.S_ISDIR(info.st_mode)
                    or stat.S_ISLNK(info.st_mode)
                    or _is_reparse_point(info)
                ):
                    raise StadiumCacheError(
                        "The resumable Stadium Studio staging path is not a private directory"
                    )
            else:
                create_private_directory(staging)
            harden_private_directory(staging)
            self._require_private_directory(
                staging, "The resumable Stadium Studio staging directory"
            )
            worker = _regular_file(self.worker, "Stadium Studio worker")
            sink("Preparing private Stadium Studio assets", 0, EXPECTED_STADIUM_SCENES)
            argv = (
                sys.executable,
                str(worker),
                "--cache-root", str(root),
                "--pack0", str(pack0),
                "--inventory", str(inventory),
                "--output", str(staging),
                "--source-sha256", SOURCE_SHA256,
                "--expected-scenes", str(EXPECTED_STADIUM_SCENES),
                "--minimum-free-bytes", str(self.free_space_reserve),
            )
            outcome = self.runner.run(argv, ROOT, sink)
            if outcome.returncode != 0:
                detail = _worker_findings(outcome.output)
                raise StadiumCacheFindingsError(
                    "Stadium Studio could not finish its bounded private derivation. "
                    f"{detail} The source XISO and shareable projects were untouched; "
                    "completed scene checkpoints remain in the private cache for retry."
                )
            self._validate_result(staging, SOURCE_SHA256)
            if final.exists():
                raise StadiumCacheError(
                    "Another process published Stadium Studio assets unexpectedly"
                )
            os.replace(staging, final)
            # Commit the rename's directory entry where the platform can; on
            # Windows there is no directory-flush primitive and the helper says
            # so rather than pretending the entry was committed.
            fsync_directory(parent)
            sink("Stadium Studio private assets ready", 1, 1)
            # Re-resolve every path after the directory rename.
            return self._validate_result(final, SOURCE_SHA256)
        finally:
            try:
                release_lock(lock_fd)
            finally:
                os.close(lock_fd)

    def _discard_stale_final(self, final: Path) -> None:
        """Remove a published cache this build cannot read, safely.

        Deleting a directory tree is the one destructive act in this module, so
        it is fenced twice: the target must be the exact published name under
        the private parent, and it must be a real directory rather than a
        symlink or reparse point -- the same conditions the publisher itself
        required. Anything else is left untouched and reported, because a cache
        that fails those checks is a safety question, not a stale one.
        """

        if final.name != FINAL_NAME or final.parent.name != PRIVATE_PARENT:
            raise StadiumCacheError(
                "Refusing to remove an unexpected Stadium Studio cache path"
            )
        info = final.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or _is_reparse_point(info)
        ):
            raise StadiumCacheError(
                "The published Stadium Studio cache is not a plain private "
                "directory, so it will not be removed automatically"
            )
        # Renamed aside first: publication is a rename onto this exact name, so
        # a crash mid-delete must not leave a half-erased tree wearing it.
        discarded = final.with_name(f".{FINAL_NAME}.stale")
        if discarded.exists():
            shutil.rmtree(discarded, ignore_errors=True)
        os.replace(final, discarded)
        shutil.rmtree(discarded, ignore_errors=True)
        fsync_directory(final.parent)

    @staticmethod
    def _require_private_directory(path: Path, label: str) -> None:
        """Re-verify one private cache directory, in this platform's terms.

        On POSIX that is the unchanged owner-only ``0o700`` assertion.  On
        Windows, where a directory carries no mode at all, it is the strongest
        check that platform supports -- a real, non-reparse-point directory
        inheriting the private cache root's ACL.  The difference is stated by
        :func:`~mod_editor.core.platform_compat.privacy_guarantee`, never
        silently skipped, and a failure is fatal here: this directory is about
        to hold bytes derived from the user's own game image.
        """

        try:
            verify_private_directory(path, label)
        except PrivatePathError as exc:
            raise StadiumCacheError(
                f"{exc} ({privacy_guarantee().mechanism} privacy is in force here)"
            ) from exc

    @staticmethod
    def _require_private_file(path: Path, label: str, *, fd: int | None = None) -> None:
        """Re-verify one private cache file, in this platform's terms.

        ``0o600`` on POSIX; on Windows the same file necessarily reads back
        ``0o666`` -- writable, no privacy from the mode -- and that honest
        expectation is what gets asserted there instead of the POSIX number.
        """

        try:
            verify_private_file(path, label, fd=fd)
        except PrivatePathError as exc:
            raise StadiumCacheError(
                f"{exc} ({privacy_guarantee().mechanism} privacy is in force here)"
            ) from exc

    @staticmethod
    def _validate_source_cache(cache: SourceCache) -> tuple[Path, Path, Path]:
        # Identity, not container equality. The sha256 term used to require the
        # user's whole image to equal the project's own dump, which refused
        # every other legal rip of the same disc; the fingerprint already says
        # this cache came from recognized USA retail NFL 2K5, and every artefact
        # inside the cache is pinned individually.
        if (
            not cache.source.recognized
            or cache.source.fingerprint_id != "nfl2k5-usa-retail-xiso"
            or cache.source.kind != "xiso"
        ):
            raise StadiumCacheError(
                "Stadium Studio requires the recognized USA NFL 2K5 SourceCache"
            )
        try:
            root_info = cache.root.lstat()
        except FileNotFoundError as exc:
            raise StadiumCacheError("The private NFL 2K5 source cache is missing") from exc
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or stat.S_ISLNK(root_info.st_mode)
            or _is_reparse_point(root_info)
        ):
            raise StadiumCacheError("The private NFL 2K5 source cache is not a safe directory")
        root = cache.root.resolve(strict=True)
        if root.name != SOURCE_SHA256:
            raise StadiumCacheError(
                "The private NFL 2K5 source cache is not the canonical game cache"
            )
        pack0 = _regular_file(cache.pack0, "private archive pack 0")
        inventory = _regular_file(cache.inventory, "private resource inventory")
        for path, label in ((pack0, "pack 0"), (inventory, "resource inventory")):
            try:
                path.relative_to(root)
            except ValueError as exc:
                raise StadiumCacheError(
                    f"Private {label} is outside the recognized SourceCache"
                ) from exc
        return root, pack0, inventory

    @staticmethod
    def _validate_result(root: Path, source_sha256: str) -> StadiumCacheResult:
        try:
            info = root.lstat()
        except FileNotFoundError as exc:
            raise StadiumCacheError("Private Stadium Studio cache is missing") from exc
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or _is_reparse_point(info)
        ):
            raise StadiumCacheError("Private Stadium Studio cache is not a safe directory")
        root = root.resolve(strict=True)
        marker_path = root / "result.json"
        marker = _read_json(marker_path, "private Stadium Studio result marker")
        if (
            marker.get("schema") != RESULT_SCHEMA
            or marker.get("source_sha256") != source_sha256
            or marker.get("private_user_cache") is not True
            or marker.get("shareable") is not False
        ):
            raise StadiumCacheStaleError(
                "Private Stadium Studio result marker is incompatible or incomplete"
            )
        paths = marker.get("paths")
        hashes = marker.get("hashes")
        summary = marker.get("summary")
        if not isinstance(paths, dict) or not isinstance(hashes, dict) \
                or not isinstance(summary, dict):
            raise StadiumCacheStaleError("Private Stadium Studio result marker is incomplete")
        gltf_manifest = _confined_file(
            root, paths.get("gltf_manifest"), "stadium glTF manifest"
        )
        texture_manifest = _confined_file(
            root, paths.get("texture_manifest"), "stadium texture manifest"
        )
        texture_root = _confined_directory(
            root, paths.get("texture_root"), "stadium texture root"
        )
        if _sha256(gltf_manifest) != hashes.get("gltf_manifest_sha256"):
            raise StadiumCacheStaleError("Private stadium glTF manifest hash changed")
        if _sha256(texture_manifest) != hashes.get("texture_manifest_sha256"):
            raise StadiumCacheStaleError("Private stadium texture manifest hash changed")
        gltf = _read_json(gltf_manifest, "stadium glTF manifest")
        texture = _read_json(texture_manifest, "stadium texture manifest")
        if gltf.get("schema") != GLTF_MANIFEST_SCHEMA:
            raise StadiumCacheStaleError("Private stadium glTF manifest schema changed")
        if texture.get("schema") != TEXTURE_MANIFEST_SCHEMA:
            raise StadiumCacheStaleError("Private stadium texture manifest schema changed")
        scene_count = _positive_int(summary.get("stadium_scene_count"), "scene count")
        exported = _positive_int(
            summary.get("exported_scene_count"), "exported scene count"
        )
        if scene_count != EXPECTED_STADIUM_SCENES or exported > scene_count:
            raise StadiumCacheStaleError("Private Stadium Studio scene coverage is incomplete")
        return StadiumCacheResult(
            root=root,
            gltf_manifest=gltf_manifest,
            texture_manifest=texture_manifest,
            texture_root=texture_root,
            scene_count=scene_count,
            exported_scene_count=exported,
            texture_occurrence_count=_positive_int(
                summary.get("texture_occurrence_count"),
                "texture occurrence count",
            ),
            unique_png_count=_positive_int(
                summary.get("unique_png_count"), "unique PNG count"
            ),
            derived_payload_bytes=_positive_int(
                marker.get("derived_payload_bytes"), "derived payload size"
            ),
            resumed_scene_count=_positive_int(
                marker.get("resumed_scene_count", 0), "resumed scene count"
            ),
        )


__all__ = [
    "DEFAULT_FREE_SPACE_RESERVE",
    "ESTIMATED_PRIVATE_BYTES",
    "ESTIMATED_SECONDS_HIGH",
    "ESTIMATED_SECONDS_LOW",
    "EXPECTED_STADIUM_SCENES",
    "Nfl2k5StadiumCacheCoordinator",
    "StadiumCacheError",
    "StadiumCacheFindingsError",
    "StadiumCacheResult",
    "StadiumCacheStaleError",
    "StadiumCacheWorkerRunner",
    "SubprocessStadiumCacheWorkerRunner",
    "WorkerCommandResult",
]

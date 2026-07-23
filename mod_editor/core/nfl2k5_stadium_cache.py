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
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
from typing import Callable, Protocol, Sequence

from .errors import ValidationError
from .nfl2k5_source_cache import SOURCE_SHA256, SourceCache


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


def _regular_file(path: Path, label: str) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise StadiumCacheError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
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
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
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
                start_new_session=True,
                bufsize=1,
            )
        except OSError as exc:
            raise StadiumCacheFindingsError(
                "Stadium Studio could not start its private asset generator. "
                f"The shipped worker may be missing or unreadable ({exc})."
            ) from exc
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
            raise
        return WorkerCommandResult(returncode, tuple(lines))


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
        return self._validate_result(final, cache.source.sha256)

    def ensure(
        self,
        cache: SourceCache,
        progress: ProgressSink | None = None,
    ) -> StadiumCacheResult:
        """Build once, resume after interruption, then publish atomically."""

        sink = progress or (lambda _stage, _completed, _total: None)
        root, pack0, inventory = self._validate_source_cache(cache)
        parent = root / PRIVATE_PARENT
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if parent.is_symlink():
            raise StadiumCacheError("Private derived-cache directory cannot be a symlink")
        os.chmod(parent, 0o700)
        lock_path = parent / LOCK_NAME
        lock_fd = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise StadiumCacheError(
                    "Stadium Studio assets are already being prepared by another "
                    "2K5 Mod Studio window. Let that operation finish and try again."
                ) from exc
            final = parent / FINAL_NAME
            if final.exists():
                sink("Stadium Studio private assets ready", 1, 1)
                return self._validate_result(final, cache.source.sha256)
            staging = parent / STAGING_NAME
            if staging.exists():
                info = staging.lstat()
                if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
                    raise StadiumCacheError(
                        "The resumable Stadium Studio staging path is not a private directory"
                    )
            else:
                staging.mkdir(mode=0o700)
            os.chmod(staging, 0o700)
            worker = _regular_file(self.worker, "Stadium Studio worker")
            sink("Preparing private Stadium Studio assets", 0, EXPECTED_STADIUM_SCENES)
            argv = (
                sys.executable,
                str(worker),
                "--cache-root", str(root),
                "--pack0", str(pack0),
                "--inventory", str(inventory),
                "--output", str(staging),
                "--source-sha256", cache.source.sha256,
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
            self._validate_result(staging, cache.source.sha256)
            if final.exists():
                raise StadiumCacheError(
                    "Another process published Stadium Studio assets unexpectedly"
                )
            os.replace(staging, final)
            directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            sink("Stadium Studio private assets ready", 1, 1)
            # Re-resolve every path after the directory rename.
            return self._validate_result(final, cache.source.sha256)
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)

    @staticmethod
    def _validate_source_cache(cache: SourceCache) -> tuple[Path, Path, Path]:
        if (
            not cache.source.recognized
            or cache.source.fingerprint_id != "nfl2k5-usa-retail-xiso"
            or cache.source.sha256 != SOURCE_SHA256
            or cache.source.kind != "xiso"
        ):
            raise StadiumCacheError(
                "Stadium Studio requires the recognized USA NFL 2K5 SourceCache"
            )
        try:
            root_info = cache.root.lstat()
        except FileNotFoundError as exc:
            raise StadiumCacheError("The private NFL 2K5 source cache is missing") from exc
        if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
            raise StadiumCacheError("The private NFL 2K5 source cache is not a safe directory")
        root = cache.root.resolve(strict=True)
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
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
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
            raise StadiumCacheError(
                "Private Stadium Studio result marker is incompatible or incomplete"
            )
        paths = marker.get("paths")
        hashes = marker.get("hashes")
        summary = marker.get("summary")
        if not isinstance(paths, dict) or not isinstance(hashes, dict) \
                or not isinstance(summary, dict):
            raise StadiumCacheError("Private Stadium Studio result marker is incomplete")
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
            raise StadiumCacheError("Private stadium glTF manifest hash changed")
        if _sha256(texture_manifest) != hashes.get("texture_manifest_sha256"):
            raise StadiumCacheError("Private stadium texture manifest hash changed")
        gltf = _read_json(gltf_manifest, "stadium glTF manifest")
        texture = _read_json(texture_manifest, "stadium texture manifest")
        if gltf.get("schema") != GLTF_MANIFEST_SCHEMA:
            raise StadiumCacheError("Private stadium glTF manifest schema changed")
        if texture.get("schema") != TEXTURE_MANIFEST_SCHEMA:
            raise StadiumCacheError("Private stadium texture manifest schema changed")
        scene_count = _positive_int(summary.get("stadium_scene_count"), "scene count")
        exported = _positive_int(
            summary.get("exported_scene_count"), "exported scene count"
        )
        if scene_count != EXPECTED_STADIUM_SCENES or exported > scene_count:
            raise StadiumCacheError("Private Stadium Studio scene coverage is incomplete")
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
    "StadiumCacheWorkerRunner",
    "SubprocessStadiumCacheWorkerRunner",
    "WorkerCommandResult",
]

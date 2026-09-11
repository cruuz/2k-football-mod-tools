"""Typed, allowlisted backend providers.

Registry command strings are descriptive evidence only.  Providers build their
own fixed argument vectors and never use a shell or accept arbitrary flags.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from typing import Callable, Iterator, Mapping, Protocol, Sequence

from . import platform_compat
from .capabilities import Capability, CapabilityRegistry, Classification
from .errors import ModEditorError, OutputRefusedError, ValidationError
from .model import GameId, SourceRecord


class ProviderError(ModEditorError):
    """A typed provider gate, command, build, or verification failed."""


class ProviderStage(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    VALIDATE = "VALIDATE"
    BUILD = "BUILD"
    VERIFY = "VERIFY"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True)
class ProviderEvent:
    stage: ProviderStage
    level: str
    message: str


ProviderEventCallback = Callable[[ProviderEvent], None]


@dataclass(frozen=True)
class ProviderRequest:
    capability_id: str
    game: GameId
    backend_project: Path
    source: SourceRecord
    output_xiso: Path
    manifest: Path
    artifact_dir: Path
    source_cache_root: Path | None = None
    audio_exact_inventory: Path | None = None
    audio_containment_inventory: Path | None = None


@dataclass(frozen=True)
class ProviderCommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ProviderRunResult:
    provider_id: str
    validated: bool
    built: bool
    independently_verified: bool
    validation: ProviderCommandResult | None
    build: ProviderCommandResult | None
    verification: ProviderCommandResult | None


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult: ...


class SubprocessCommandRunner:
    """Run fixed argv with no shell, stdin, or inherited injection environment."""

    def run(
        self,
        argv: Sequence[str],
        cwd: Path,
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        fixed = tuple(os.fspath(value) for value in argv)
        # Provider modules are an integrity boundary.  An inherited LD_PRELOAD,
        # LD_AUDIT, GCONV_PATH, Python startup option, or tool-specific variable
        # could otherwise alter execution before the pinned Python bytes run.
        # These providers need no ambient credentials or user configuration.
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        try:
            process = subprocess.Popen(
                fixed,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=False,
            )
        except OSError as exc:
            raise ProviderError(f"Could not start typed provider: {exc}") from exc
        assert process.stdout is not None and process.stderr is not None
        messages: queue.Queue[tuple[str, str | None]] = queue.Queue()

        def pump(name: str, stream) -> None:
            try:
                for line in iter(stream.readline, ""):
                    messages.put((name, line))
            finally:
                stream.close()
                messages.put((name, None))

        threads = [
            threading.Thread(target=pump, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=pump, args=("stderr", process.stderr), daemon=True),
        ]
        for thread in threads:
            thread.start()
        completed_streams = 0
        stdout: list[str] = []
        stderr: list[str] = []
        while completed_streams < 2:
            name, line = messages.get()
            if line is None:
                completed_streams += 1
                continue
            if name == "stdout":
                stdout.append(line)
                emit(ProviderEvent(stage, "INFO", line.rstrip()))
            else:
                stderr.append(line)
                emit(ProviderEvent(stage, "WARNING", line.rstrip()))
        returncode = process.wait()
        for thread in threads:
            thread.join()
        return ProviderCommandResult(
            fixed, returncode, "".join(stdout), "".join(stderr)
        )


class TypedProvider(Protocol):
    provider_id: str
    capability_ids: frozenset[str]

    def preflight(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> None: ...

    def validate(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult: ...

    def build(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult: ...

    def verify(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult: ...


SourceHasher = Callable[[Path, Callable[[int, int], None] | None], tuple[str, int]]
ContainedSourceValidator = Callable[[Path], bool]


def _is_supported_nfl2k5_container(path: Path) -> bool:
    """Recheck the game inside a non-canonical NFL 2K5 disc container.

    Legal dumps of one Xbox disc can have different whole-file hashes and
    sizes.  The executable inside them cannot: :func:`contained_identity`
    hashes ``default.xbe`` and returns a match only for the reviewed USA retail
    revision.  Backends still bind every edited pack/span independently.
    """

    from .sources import contained_identity

    identity = contained_identity(path)
    return bool(
        identity is not None
        and identity.fingerprint_id == "nfl2k5-usa-retail-xiso"
        and identity.game == GameId.NFL2K5
        and identity.kind == "xiso"
    )


@dataclass(frozen=True)
class _PinnedPayload:
    relative: str
    payload: bytes
    identity: tuple[int, int]


def _read_pinned_payload(
    workspace: Path,
    relative: str,
    expected_sha256: str,
    label: str,
) -> _PinnedPayload:
    """Read one allowlisted file through a stable descriptor.

    Provider pins are an execution boundary, not merely a release checksum.  A
    multiply-linked file can be changed through an unseen alias, so it is
    rejected along with symlinks.  The descriptor and pathname identities are
    compared before and after the complete bounded read.
    """

    relative_path = Path(relative)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or any(part in {"", ".", ".."} for part in relative_path.parts)
    ):
        raise ProviderError(f"Allowlisted {label} path is not a safe relative path")
    root = workspace.resolve(strict=True)
    parent = root
    for component in relative_path.parts[:-1]:
        parent /= component
        try:
            parent_info = parent.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(f"Allowlisted {label} parent is missing: {parent}") from exc
        if not stat.S_ISDIR(parent_info.st_mode) or stat.S_ISLNK(parent_info.st_mode):
            raise ProviderError(f"Allowlisted {label} parent must be a non-symlink directory")
    path = root / relative_path
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ProviderError(f"Allowlisted {label} is missing: {relative}") from exc
    if (
        not stat.S_ISREG(supplied.st_mode)
        or stat.S_ISLNK(supplied.st_mode)
        or supplied.st_nlink != 1
        or not 0 < supplied.st_size <= 16 * 1024 * 1024
    ):
        raise ProviderError(
            f"Allowlisted {label} must be a bounded, singly-linked regular file"
        )
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or identity != (supplied.st_dev, supplied.st_ino)
            or opened.st_size != supplied.st_size
        ):
            raise ProviderError(f"Allowlisted {label} changed before its pinned read")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise ProviderError(f"Allowlisted {label} shortened during its pinned read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ProviderError(f"Allowlisted {label} grew during its pinned read")
        current = path.lstat()
        if (
            not stat.S_ISREG(current.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or current.st_nlink != 1
            or (current.st_dev, current.st_ino, current.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
        ):
            raise ProviderError(f"Allowlisted {label} pathname changed during its pinned read")
        payload = b"".join(chunks)
    finally:
        os.close(descriptor)
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ProviderError(f"Allowlisted {label} hash changed")
    return _PinnedPayload(relative, payload, identity)


def _validate_pin_set(
    workspace: Path,
    pins: Mapping[str, str],
    label: str,
) -> None:
    if not pins:
        raise ProviderError(f"Allowlisted {label} pin set is empty")
    for relative, expected in pins.items():
        _read_pinned_payload(workspace, relative, expected, f"{label} file {relative}")


def _write_staged_payload(path: Path, payload: bytes) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        0o400,
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ProviderError("Pinned execution bundle created a non-regular file")
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            if written <= 0:
                raise ProviderError("Short write while staging a pinned execution bundle")
            cursor += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    current = path.lstat()
    if (
        not stat.S_ISREG(current.st_mode)
        or stat.S_ISLNK(current.st_mode)
        or current.st_nlink != 1
        or (current.st_dev, current.st_ino, current.st_size)
        != (identity[0], identity[1], len(payload))
    ):
        raise ProviderError("Pinned execution bundle pathname changed during staging")
    return identity


def _verify_staged_payload(
    path: Path,
    identity: tuple[int, int],
    expected_sha256: str,
    label: str,
) -> None:
    try:
        supplied = path.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
    except OSError as exc:
        raise ProviderError(f"Pinned {label} execution bundle changed while running") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
            or opened.st_nlink != 1
            or (supplied.st_dev, supplied.st_ino) != identity
            or (opened.st_dev, opened.st_ino) != identity
        ):
            raise ProviderError(f"Pinned {label} execution bundle changed while running")
        digest = hashlib.sha256()
        completed = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            completed += len(block)
            if completed > 16 * 1024 * 1024:
                raise ProviderError(f"Pinned {label} execution bundle changed while running")
            digest.update(block)
        current = path.lstat()
        if (
            current.st_nlink != 1
            or (current.st_dev, current.st_ino, current.st_size)
            != (opened.st_dev, opened.st_ino, completed)
            or digest.hexdigest() != expected_sha256
        ):
            raise ProviderError(f"Pinned {label} execution bundle changed while running")
    finally:
        os.close(descriptor)


def _materialize_readonly_tree(source: Path, destination: Path, label: str) -> None:
    """Expose read-only evidence without requiring symlink privileges."""

    if source.is_symlink():
        raise ProviderError(
            f"Pinned {label} evidence root must be a non-symlink directory"
        )
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir() or destination.is_symlink():
        raise ProviderError(
            f"Pinned {label} evidence destination has an invalid type"
        )
    for child in source.iterdir():
        child_info = child.lstat()
        if stat.S_ISLNK(child_info.st_mode):
            raise ProviderError(
                f"Pinned {label} evidence child must not be a symlink"
            )
        child_destination = destination / child.name
        if child.is_dir():
            _materialize_readonly_tree(child, child_destination, label)
            continue
        if not child.is_file():
            raise ProviderError(
                f"Pinned {label} evidence child is not a regular file"
            )
        if child_destination.exists():
            continue
        try:
            os.link(child, child_destination)
        except (OSError, NotImplementedError, AttributeError):
            shutil.copyfile(child, child_destination)
        if child_destination.stat().st_size != child_info.st_size:
            child_destination.unlink(missing_ok=True)
            raise ProviderError(
                f"Pinned {label} evidence copy has the wrong size: {child}"
            )


@contextmanager
def _pinned_execution_bundle(
    workspace: Path,
    pins: Mapping[str, str],
    entry_module: str,
    label: str,
) -> Iterator[Path]:
    """Yield an executable copy made only from freshly verified module bytes.

    Every local import in a provider's reviewed closure is copied into a private
    temporary tree. The backend therefore executes the bytes that were hashed,
    even if an original workspace pathname changes after pinning. Read-only
    evidence roots are materialized as hard-linked files when possible and
    copied when the source and temporary directory are on different
    filesystems; neither route needs Windows administrator rights.
    """

    if entry_module not in pins:
        raise ProviderError(f"Pinned {label} entry module is absent from its closure")
    payloads = {
        relative: _read_pinned_payload(
            workspace, relative, expected, f"{label} file {relative}"
        )
        for relative, expected in pins.items()
    }
    with tempfile.TemporaryDirectory(prefix="vc-provider-") as temporary:
        bundle_root = Path(temporary)
        staged: dict[Path, tuple[tuple[int, int], str]] = {}
        for relative, pin in payloads.items():
            destination = bundle_root / relative
            identity = _write_staged_payload(destination, pin.payload)
            staged[destination] = (identity, hashlib.sha256(pin.payload).hexdigest())
        canonical_workspace = workspace.resolve(strict=True)
        for evidence_root in ("reports", "extracted"):
            source = canonical_workspace / evidence_root
            destination = bundle_root / evidence_root
            try:
                evidence_info = source.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(evidence_info.st_mode) or stat.S_ISLNK(
                evidence_info.st_mode
            ):
                raise ProviderError(
                    f"Pinned {label} evidence root must be a non-symlink directory"
                )
            _materialize_readonly_tree(source, destination, label)
        entry = bundle_root / entry_module
        try:
            yield entry
        finally:
            for path, (identity, expected) in staged.items():
                _verify_staged_payload(path, identity, expected, label)


class Nfl2k5UnifiedVisualProvider:
    provider_id = "nfl2k5-unified-visual-v1"
    capability_ids = frozenset({
        "nfl2k5.audio.fixed_audo_wav",
        "nfl2k5.audio.ausb_fixed_range_wav",
        "nfl2k5.crib.assets",
        "nfl2k5.uniforms.all_visual",
    })
    backend_module = "tools/nfl2k5_visual_mod_project.py"
    backend_command = (
        "python3 tools/nfl2k5_visual_mod_project.py build --project <project.json> "
        "--source-xiso <retail.xiso.iso> --output-xiso <new.xiso.iso> "
        "--manifest <manifest.json> --artifact-dir <artifact-dir>"
    )
    backend_module_sha256 = "a268a924760d3d7439d19fca389b95ee7309bf80761eb62e3b7617a36f70e929"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/audio_conform.py": "db40b6f28dedf1deea7fad6306fe0afebf842a5ee113d5067f6b5b7721686c0f",
        "mod_editor/core/build_feedback.py": "56c078f5cecf5a2d37349b15b964a6f5350341db3f55f6808a60fc3b205abf76",
        "mod_editor/core/build_io.py": "bb5bf2cf27bea644fa7f7ef694ff5a9368a076a04d59379fcdb568ace6167744",
        "mod_editor/core/equipment_palette.py": "0272af0ed054919fd21624a4a2adbeec97959f78036dd5932de3ef5211b8f844",
        "mod_editor/core/errors.py": "4624e80f063f1e7db69ec6c20d2703f01eec49728b02c88792ccb309bd742de0",
        "mod_editor/core/image_use.py": "78794c08fcf52debcb24d54cf62c8b1936463aedbe74929cdb5037f117b9c14d",
        "mod_editor/core/json_stream.py": "5933752561dd8b519a301c18ec1d14f13a457f58e6ae337984f543ab2b0838b0",
        "mod_editor/core/metadata_cache.py": "49874cc7f12cc0d36d15b9355dbca64ffe95590ba7582b460738b05aabcd9024",
        "mod_editor/core/mod_build.py": "71463608ba01afee4eca17528c42562c1d8d5e64274ef0f7b0a7fcc759b3a4fd",
        "mod_editor/core/model.py": "292f0c5444e32f5cea000fd3cabd6963d7d805a5434dcbc364a36ca2c0f0d228",
        "mod_editor/core/modpack.py": "7524c5de4d03c23997f88355c6888f1e013e5d5e62a995d07e8b963d1be9fd2a",
        "mod_editor/core/modpack_ops.py": "897f364a0cfe42bb8fbd33f8bc97166ea25520a379a612431f00d8aefca8e5c5",
        "mod_editor/core/nfl2k5_abilities_runtime.py": "9a4de702d6daf475df990f47f787c7b554451e11648f14d3082ab84aa954f41a",
        "mod_editor/core/nfl2k5_abilities_runtime_code.py": "30da3adf1c622a8a650e090e0380e4cf23e725b8215d0e79dd2acf03270d370f",
        "mod_editor/core/nfl2k5_accel_ramp.py": "95014c753d46faed2e75e545d992794bb62965a9bbe6407057d3626395c6e862",
        "mod_editor/core/nfl2k5_accelerated_clock.py": "079ce771155f78b33591000e3f622671dd947a5357e14df165f245331c3bbdb1",
        "mod_editor/core/nfl2k5_accelerated_clock_code.py": "4ff06a448a9777ad24389f490169fa2de981f7e865aabf74e8d5f9b79857c317",
        "mod_editor/core/nfl2k5_animation.py": "2ae98a97fb78b06050a5bfc9ab8a838b30ea36d7a9514132893debe4441b44b6",
        "mod_editor/core/nfl2k5_animation_bones.py": "b82275d45fd4f0b34aaa4613e0ea266724f14270c9069650b5aded3a3f929eb8",
        "mod_editor/core/nfl2k5_animation_import.py": "a1bf3c0b4c15835c946e0373fb2185dbaf748bae0d508a0698f6f4db92d5c50f",
        "mod_editor/core/nfl2k5_animation_math.py": "2b0c8cd4f700a6426e6fc83d605f4db8d14488f2825acd540da0a79586a4ed7e",
        "mod_editor/core/nfl2k5_animation_xbe.py": "3a384b0e5c731e4ec4d11f78ad74223990b0130f99914d1bc5385d1d1da186ad",
        "mod_editor/core/nfl2k5_asset_io.py": "412918547d100b6458a34f5ebacfd0f5149cc38dabc4a45aa7180fd274e00395",
        "mod_editor/core/nfl2k5_audio_catalog.py": "be1dbafb7077a4aab9c8ce5ff9ba9f0c5da9dd54c86464b4d97304aaf44a4efc",
        "mod_editor/core/nfl2k5_audio_containment_fingerprints.py": "da564ae30a18e9bfc7a3006b2422bceef0d0078d3cb9a919671ade23eda5f146",
        "mod_editor/core/nfl2k5_audio_origin_authorization.py": "664e43a7d2bb7dfcccf328b622b5fe7be3f5510d03919c56fa85149d7d3ffb8d",
        "mod_editor/core/nfl2k5_audio_origin_preparation.py": "eb874cc84d5cc5752cbf46aa8150c8304b9a0ddbe58e28cb5b22c856c3326af5",
        "mod_editor/core/nfl2k5_audio_source_containment.py": "7d6770b74555c8febfc437306686a05fb8b5fb5cd87d2c1ae5c1ed98efeed063",
        "mod_editor/core/nfl2k5_audio_source_fingerprints.py": "b0531c08751258833a2d134b79409e46db3b6da1862e1520a03c303144cff1ca",
        "mod_editor/core/nfl2k5_audio_source_scan.py": "b8bb4eef4d6a94a072b5e1e5c87fc0a113e8269118ba4e5857cb89c9560950e8",
        "mod_editor/core/nfl2k5_audo_family_labels.py": "b4d699da1a1d58b32a1bbd0e49b62d69c9ae89a2c24d450a26d7b8831e49cef8",
        "mod_editor/core/nfl2k5_audo_fixed_slots.py": "7b63203e40b1410f04e0866bbe3ad91044fc06700f21a164b65cf8872638c32c",
        "mod_editor/core/nfl2k5_ausb_build_adapter.py": "138eccfa097da8005dca74d43c0a10808558c4a4f1702c31e8f009cc49a7ecc7",
        "mod_editor/core/nfl2k5_ausb_fixed_slots.py": "56a39ad842d3552dd26e2089d3c859cba8b59fd61701e63f2f9265db20422d4a",
        "mod_editor/core/nfl2k5_boot_logo.py": "c767db7cdcc7dcf363a3a78547bcc251004980bc696300b3a8a3d283482fbdaa",
        "mod_editor/core/nfl2k5_build_service.py": "336ef393db878db8d22586af839716c9d5ec53ffeef189cc77b0e86edb651287",
        "mod_editor/core/nfl2k5_build_settings.py": "aa50ce8b583ad074f689033cfc4b7b68e5a68455f805950289bd110de484abcc",
        "mod_editor/core/nfl2k5_bump_strength.py": "79f9264fbe0813db9be66f22e35f8944e35b92ae415132d819eda50920e41bb0",
        "mod_editor/core/nfl2k5_calendar_engine.py": "796246b2248eddda3a0e57ed791b53cc1446fe3a3128ad39397ababe873ab841",
        "mod_editor/core/nfl2k5_calendar_engine_code.py": "9b43e835f1df76f85ecb13e7ef593d2eee884a1fa82fe41ea3d813186445ca22",
        "mod_editor/core/nfl2k5_camera.py": "ad21c4d301ab26ed5786383f0b3aa76aace895c2c673b38289e41b225ee593be",
        "mod_editor/core/nfl2k5_catch_slider.py": "0ea12e1f558463538a154f50c38036389a8c0432c7ba55ac2862cd706b85498f",
        "mod_editor/core/nfl2k5_cave_oracle.py": "8be24dd71d7503dba209061747bb74c439833970978a045a96f740cedafb940e",
        "mod_editor/core/nfl2k5_college_check.py": "b4752a4a015c2b39a19e9887ef67ffdcc2b2b9ac044642a45201a2fae500709d",
        "mod_editor/core/nfl2k5_coverage_slider.py": "e63025985e5e2a1f9e18fbc8f7375b16689f2b81bdb61766d86f8d8ee515fc0b",
        "mod_editor/core/nfl2k5_coverage_trail.py": "68b6548fc60cf8cbed4a912403b6323c44818eeba358cdc28fa8090642a3e969",
        "mod_editor/core/nfl2k5_coverage_trail_code.py": "746874dbef2fbf16355affd2b373840fb96e235fc0f2592c9c2858c826080e66",
        "mod_editor/core/nfl2k5_cpu_money_downs.py": "eabd2616b276cbc2a44406e4b6c3dcd87578c9afb293ed968abcb3fafcdec720",
        "mod_editor/core/nfl2k5_cpu_money_downs_code.py": "b720d4fa432fbc6ae366a8e2018aefde8cbe9531aef5007392c352b895e3b31a",
        "mod_editor/core/nfl2k5_crib.py": "01f98c38f1dcf6a6175e017b68794fc16011b437763eb42d8d3810430760fb8c",
        "mod_editor/core/nfl2k5_crib_electronics_targets.py": "6d474769ee594d792d11f112fb3e39da8bd2ae8117bae92231956b4305112e2b",
        "mod_editor/core/nfl2k5_crib_geometry_writer.py": "d1cb53a2e801cfd14c469dc58cf8e433a8045e93e724ed502073a1cb2b8d0d78",
        "mod_editor/core/nfl2k5_crib_reclaim.py": "93f87645b362bc23778c23f5b770eeedb3ef12666fc2262c0d5cee390ec1636b",
        "mod_editor/core/nfl2k5_crib_scene_texture_writer.py": "4f72f59fab6f116c164a2acafb110829a46eb18dc5abcc5cd2c05978a0f0cdbd",
        "mod_editor/core/nfl2k5_crib_standalone_texture_writer.py": "95cab3bb2d666fa4f4dfddfb25816c443b17a51bb97abbe90d9532a5f117bae6",
        "mod_editor/core/nfl2k5_deep_zone.py": "59fb0d2b1f5be90d90692d7f143d00d8091ceac2d9ba1ee9bd40c0f9f626cbf7",
        "mod_editor/core/nfl2k5_deep_zone_code.py": "421d08aa91966fb43667cdcc44813ff8cd2d898b8c47191bfa9050930e9667cc",
        "mod_editor/core/nfl2k5_defensive_try.py": "7ed9559148794d2c9ba60c688165d79d777dced3903b56347acc6c14fce27ac2",
        "mod_editor/core/nfl2k5_depth_chart_rows.py": "b2b8dd171f20837d321a8e762f0a01d87f93e0987875e34fa27f218131090568",
        "mod_editor/core/nfl2k5_depth_chart_storage.py": "acb37c1fbb13e327880574df1142d6cb1262e97b307bfd182a167647d0892a1e",
        "mod_editor/core/nfl2k5_depth_locks.py": "39a0948c3fc26721f15495acd66a3a48c8db1cb6bcda6e4911b07d353bffd61c",
        "mod_editor/core/nfl2k5_depth_roles.py": "92a11e038973a1c421fe7f3162064bb62a9fd8cefd6bfb4bd9cc5765d3f3a19d",
        "mod_editor/core/nfl2k5_equipment_import_intent.py": "ef50b20ff389b0067046c53eb62fc254a3c1319eedd7eb1a8d1aaba8f2cfb8c4",
        "mod_editor/core/nfl2k5_equipment_lz.py": "c09e5a518177c4b473f71ca0f14a2562d8c0ca1e322f2bab0c32a5cf46350571",
        "mod_editor/core/nfl2k5_digit_art.py": "607220b6b173e25bd69e0d625828aa21a9c60f246de2ae00738513b52600d4cc",
        "mod_editor/core/nfl2k5_digit_texture.py": "38112506a194aae7b0e229cdb0d40d0fbbba52bf7ac5e3e81c7a67743352e79c",
        "mod_editor/core/nfl2k5_disc_identity.py": "000ec3164d1da4a9e0fb4a4bd48deb55e4241cff90d7ee4762dd1caa446eff3e",
        "mod_editor/core/nfl2k5_draft_ai.py": "b90f8e84cd6e30c03758158a917773cdb44f3089f5f0aa2413503f39fb4a9a16",
        "mod_editor/core/nfl2k5_dynamic_kickoff.py": "0f2a618ce8ad2443a472145fa69a7d06e0f78af1e9f7ce211ed9b35b00e6a6e7",
        "mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py": "211063695451178000aa7088245ddef8c31973f08fad490341a378bf6e8a6b4f",
        "mod_editor/core/nfl2k5_edge_rename.py": "8d07169164719fff6121c36b07f90ac8af0d350ea39cb2dcaee83a3ab4e3fc0d",
        "mod_editor/core/nfl2k5_espn25_rosters.py": "3cfe17df38d5d6d42bf31972848644ed32b7a0462f979b0380ad5c69e384c036",
        "mod_editor/core/nfl2k5_extended_visual_catalog.py": "6576fc522bec39f163b851471ab9105db5080a5085681f3f27e626c6e50011f3",
        "mod_editor/core/nfl2k5_extended_visual_io.py": "f949128412f01ea2be68e8be397466765c336fd02c900dc7b928d0d7bd3e9bcf",
        "mod_editor/core/nfl2k5_formation_play_writer.py": "fb09bdd724874d0a03488e12a046d8107221e99b52c77df21c04a7181d3508bf",
        "mod_editor/core/nfl2k5_franchise_2026.py": "1951dd3a20b35cec58814fcda757f2cda7a3220054615c9412a92f58faf6a79d",
        "mod_editor/core/nfl2k5_franchise_2026_code.py": "3aaa62bc4282a7605823b30d20936d388916d2f5c51a4a4774f85c0af67efcfa",
        "mod_editor/core/nfl2k5_franchise_autosave.py": "39fefc51d2b95fb56730ff1359c3fa9b73e0a4aa9302f38a32905efea791e3d3",
        "mod_editor/core/nfl2k5_franchise_autosave_code.py": "bf06126a790642048aae92d57d3815d445560bc012ed02df5917648bcceec183",
        "mod_editor/core/nfl2k5_franchise_edit_player.py": "6bb34cacc88fc4e6ff2a12510cb33eda8c66460c2728439f10dd1b77c1793ec9",
        "mod_editor/core/nfl2k5_franchise_practice.py": "a02412be59a08a5997c1c2936265377520abb4e3ecf7108e24d9546b7a8592f0",
        "mod_editor/core/nfl2k5_franchise_save.py": "5687f7444ed04ff006cc5ccbaf94cc51fe3deef6891c78b91869c550bc2a2029",
        "mod_editor/core/nfl2k5_gameplay_lever.py": "fb69f15c8a070d40458f0997cdcb8dd1beb164afafa9db3fa7a3e7f47977857b",
        "mod_editor/core/nfl2k5_guardian_cap.py": "10d04364c41bd7522f74109a3031df05a5cd9ef3ea80193daaf93a455943b5a8",
        "mod_editor/core/nfl2k5_guardian_overlay.py": "510149cf1ebd9954fb19b56bb6f15313cee365e19e609d4c3d323646872fad3f",
        "mod_editor/core/nfl2k5_guardian_overlay_code.py": "019075c8fa333bd5be8d240c86038a3ab89527af11921ddfd6935b06eab08cf6",
        "mod_editor/core/nfl2k5_guardian_resources.py": "5343af8c538dd5382488fb84876096968f3386f9e7b16518bde4d65e4324eefe",
        "mod_editor/core/nfl2k5_hires_budget.py": "e36cffa4aa56b51a9549126a0fa7c04998a2771f9b5d2f78fdd158a41ed51ba6",
        "mod_editor/core/nfl2k5_hires_catalog.py": "4d1c67add6cfed68018d4341e6171b005a1568b60eebf199507afc39eba3ae1f",
        "mod_editor/core/nfl2k5_hires_evidence.py": "4309e402356c9266efb2ab498b99056412dd5613e61615db2b3ecadb11e943da",
        "mod_editor/core/nfl2k5_hires_layouts.py": "e9c5fde8390e6f0a5a35f91fcd7b2e39196a13cf0389be5a6cc6d035367710ce",
        "mod_editor/core/nfl2k5_hires_pack.py": "f1d6c5405bcdbdec43da7e6b44ce26d3da6d8dadc94756e8cb8200a2a9dd1d51",
        "mod_editor/core/nfl2k5_hires_texture.py": "cab5e3e72cfbf8eb3d4601ecd55782f6a0e78cfa2bb17440c61622348fb446c2",
        "mod_editor/core/nfl2k5_hud_layout.py": "9953e899093daf2517adc74d101a4160353377e36e273eba5fdec7f82bbb8da3",
        "mod_editor/core/nfl2k5_import_preflight.py": "7f7cbcac329171f70e4931d818af806edcf851c46ac04d5e8ebef95ed7db6454",
        "mod_editor/core/nfl2k5_kick_laces.py": "a495864f35b60f335855b17f8a12ec304f78ecf3c363a597bb0e519e64790754",
        "mod_editor/core/nfl2k5_kick_rules.py": "09023a7bf09146877c2bc7ba3ea7c7f9e5037e0090a70394262537192519c8d5",
        "mod_editor/core/nfl2k5_match_coverage.py": "d9c1a93508a25a17d389b1dfa628ab8d0ac2da25d99bcc64a347b98f4447cfa2",
        "mod_editor/core/nfl2k5_models.py": "e17207d02e8267b11cb822a13e50e5c20db4b5411c89400090125d198f66df23",
        "mod_editor/core/nfl2k5_modern_naming.py": "517f44b88799817d5c036605cbd3cf1a4baa06cbfa50ed4ee706c0a38b80701f",
        "mod_editor/core/nfl2k5_modern_positions.py": "f2bbb8ca3dcc78c6a16e1f70b3cb4858e95383daf817333dc2d37ac3d624c8e5",
        "mod_editor/core/nfl2k5_momentum.py": "2746d12c7950c96cd0400bb59c33a413294b5ac3d4563874727cc32378981cce",
        "mod_editor/core/nfl2k5_momentum_code.py": "a56830bdfaf46ac987b0699f926745c177be183754baa422bbe192fc9e305b08",
        "mod_editor/core/nfl2k5_music_archive.py": "a86456b894128d773c61c972c3eb535614f476941c5781737f6ebaef8d11da8a",
        "mod_editor/core/nfl2k5_music_banks.py": "9be63fa3ff7733c651d10812138235d425c97a0cc9ca91f60622df723fb2ddd8",
        "mod_editor/core/nfl2k5_music_build.py": "7818eaebd1849ee7f969efeae549addd375ced1aa38aac557d37efc16a6c0a7c",
        "mod_editor/core/nfl2k5_music_catalog.py": "e54417c33f0ff7c7dfa19dbad57f61f578b3e819d17ff7e2b3693b8ecee61e48",
        "mod_editor/core/nfl2k5_helmet_finish.py": "667f06ddbba78b7ee3416265ab6f67ab43edf1444569b1e407e7b3c6d92b1f3d",
        "mod_editor/core/nfl2k5_jukebox_list.py": "3752a85731a7190cda9e429ed26a6c8810be35b45b31db1710e31e82f4408eb7",
        "mod_editor/core/nfl2k5_music_collections.py": "75e9145cc396c633a5f99a07f0d8a4c9bdcf87dd6e29c6726e98a792dd9752da",
        "mod_editor/core/nfl2k5_music_metadata.py": "e3ee47bc222794312b1b0119a96c046edf6f53a071db00ff0208f106abdedf48",
        "mod_editor/core/nfl2k5_music_playlist.py": "1a0900178e647b3c3d1071fb8056b81eaf3e18d9fa5748443115bd1b6c15e35a",
        "mod_editor/core/nfl2k5_music_playlist_code.py": "d77324785e5aeacf3b6540619d0c8116e05da313c1f048a2e270cd002edc07ac",
        "mod_editor/core/nfl2k5_music_policy.py": "f1f21c182fa9f86844c6dcc0019f0463ef841799fd24a717131b4d762c8a99ec",
        "mod_editor/core/nfl2k5_music_storage.py": "db13a224f6e04e2ebbe0f7639946e2e6c9626500939614a44f2539a25137904b",
        "mod_editor/core/nfl2k5_my_career.py": "f625215f21b280e68ecc3e5e9c6dbb53470389b00639e6bec601a46d304102a9",
        "mod_editor/core/nfl2k5_my_career_code.py": "0ce8c85ca30bbc188356e612ca1d95e01e94ceb7dfe2cabcea222672f07e3c2b",
        "mod_editor/core/nfl2k5_my_career_mode.py": "2d5cdd8dc549ac6f793e40b5191b316bc29612b0d2e5eb35e28f70403e224e3e",
        "mod_editor/core/nfl2k5_my_career_mode_code.py": "c365793e340929d103e5dedb42bdcc8327443d74b7bb3e2546ff3a1b702301de",
        "mod_editor/core/nfl2k5_my_career_progression.py": "77ee4d665dccc60862e162195e85d3cb3d39e6ad04ce9eee9cc87a99754d9cf5",
        "mod_editor/core/nfl2k5_my_career_save.py": "f229b968fc4bea9d9cf1e5c858684056b66deeccb3f3944450fad836f053b812",
        "mod_editor/core/nfl2k5_overtime.py": "9621106101e1ce6d0bccb35ab5a2051cc8d68e9ed2fcdf2af87a13342855bbd5",
        "mod_editor/core/nfl2k5_p8_texture_writer.py": "4a519adf657eeb5ecbf8be6a8cba99411cbd0e5843bf55d7bd7e142723498485",
        "mod_editor/core/nfl2k5_penalties.py": "f4d3b4e703136aea3c49d224c93b08960083403d4a0c4dc6df85f37536151a3e",
        "mod_editor/core/nfl2k5_play_codec.py": "c45262cf6b50c57678f0839702a60a34de4d782df9930715a4ab649cef354234",
        "mod_editor/core/nfl2k5_play_intents.py": "197960e5c8ed647982a3b739856297dbd06346425611c486fe321e387ae2f21b",
        "mod_editor/core/nfl2k5_play_library.py": "4acd4872eed43f3efa44edc5cc26690b20e47c49461f3f6db5b39484688500df",
        "mod_editor/core/nfl2k5_playbook_inspector.py": "70e294c4e892487e38875a40178914b9d95e8ff494fd6441563272df43921f8d",
        "mod_editor/core/nfl2k5_playbook_pack.py": "49b1fe33d985ea5c2b52fb8174da1994fbecff42cea4a5407dbb019bb19d5125",
        "mod_editor/core/nfl2k5_playbook_pair.py": "2e1207d5ef86f13ab1b020d250d1bf4409fa09ac40aa449d31d006a5e1f2e7bb",
        "mod_editor/core/nfl2k5_playbook_pair_code.py": "78e97a0ce01e49af9a22c59d540ea8121097ae26c31f6650983baa7a945969ae",
        "mod_editor/core/nfl2k5_playbook_route_writer.py": "87ac9ab729e15c665774223c406a248931b77a05ca2fa258b04e1f0cd06674c5",
        "mod_editor/core/nfl2k5_player_star.py": "66784f4905a50d6acab67a62b952b3d3d8f8b90ec4d470e650276d29e4d97a7d",
        "mod_editor/core/nfl2k5_player_tags.py": "ab981d447202a4840398034aa6c2e11320aa55d0ea901cf0698eed10f7d12d91",
        "mod_editor/core/nfl2k5_playoff_picture.py": "cc851bca3cd4ac77fdcea03be41db1536c51e3699503cfb227f60f1619b2c441",
        "mod_editor/core/nfl2k5_playoffs14.py": "d8c490d6d37d118355db80de95c924db52f03ba897b4fbd85432d1840a14051d",
        "mod_editor/core/nfl2k5_position_pools.py": "a959ecbc63257955f7681c95aa8e96790f896f1c1bd209d8514d4f516c7fbfdd",
        "mod_editor/core/nfl2k5_position_row.py": "0df78f0d7e3af61be8738afe5373925f48ef8a309a35bfcb31ab62008b6be85b",
        "mod_editor/core/nfl2k5_practice_reserves.py": "3728a1d8195819c72f814ac5110755a06598aeb1400f6a53702821a7b275a8b6",
        "mod_editor/core/nfl2k5_practice_squad.py": "c061f558eeb05dee8040881c81ca22c88a40365bf45615eb633da54481c836d2",
        "mod_editor/core/nfl2k5_practice_squad_runtime.py": "33041313a6ae071fd48cf28d79b2ad8c11281d9afe2310a5189ec03735da8ccb",
        "mod_editor/core/nfl2k5_practice_squad_screen.py": "dd7f089fa01c6138a940147de61ebfa09fc2c2e66d5d0ab3e88d47f3cf72d92a",
        "mod_editor/core/nfl2k5_practice_squad_screen_code.py": "d23c1575d824c0fef3486fe067b3e445a926f431a8fb57478aaf539aa2e641ef",
        "mod_editor/core/nfl2k5_preseason.py": "5e18c2bba83005798237cc3c85b0e10ee9f7dd8f4e179f52a430f46ed02c951b",
        "mod_editor/core/nfl2k5_probowl_order.py": "6e61b983f57f7e01695c7626b51854aea2242e1c7879049f8bb3a85a44b3cf9f",
        "mod_editor/core/nfl2k5_progression.py": "a4e978a251fb9a747819c09c3563540229a41afca92458990496915f772d6b94",
        "mod_editor/core/nfl2k5_prospect_names.py": "e92464afcc1b82581551b3092f2aedf8e5bca7d4a1e26f28fa4bdeefd44bf5da",
        "mod_editor/core/nfl2k5_qb_spy_runtime.py": "d0c0f0f216c3f845a7fc233c608766b09e2d74a4e979b937480f788e8c00c2bc",
        "mod_editor/core/nfl2k5_qb_spy_runtime_code.py": "759ee92ee3bac1d79d80ac6d6ae539ea6f0e3cef658dc945548a8c7db35c468f",
        "mod_editor/core/nfl2k5_rdata_sites.py": "cb422ad49c38a233a8d0e855beae0a9748b1dfef809472bdae84c459865762af",
        "mod_editor/core/nfl2k5_read_option_runtime.py": "f4b3c0126f270dc6ed4aae33d75ab0d6ab25dbe389d803002045cede1f7363dd",
        "mod_editor/core/nfl2k5_read_option_runtime_code.py": "2f58745ddc7ad4cf28adf3223d3a85661ca79d0252a7bb7d27a7a19e90bcc69a",
        "mod_editor/core/nfl2k5_resource_growth.py": "d33b9b3a6571852e13297050efd5364ab411f10efbaee32b6b087f01e41725fa",
        "mod_editor/core/nfl2k5_returner_fix.py": "a59cd96b4d639ee4f2d7fa7460e1b8bd61559ca060e7cd5c1a8d65990a3c7dc2",
        "mod_editor/core/nfl2k5_roster_ages.py": "f38aff19e3bb9ab503d5a7b85d191ff8c15703e101a5580ea02d0d85c6290daa",
        "mod_editor/core/nfl2k5_roster_arena.py": "a80f32af8ed30d86c45edb761405fa1c3a9e3ad7ca9c0cc609814b9e8e352b9d",
        "mod_editor/core/nfl2k5_roster_arena_code.py": "23a661e5f3bf87d23d1769d5866f6e464d6dfb092afdc34c57b8cd5b8a07ef1d",
        "mod_editor/core/nfl2k5_roster_arena_growth.py": "b8c291abe201e1296f21626fae29bea47bb4571aeb6cb60dd0eacd972fbe839d",
        "mod_editor/core/nfl2k5_roster_arena_image.py": "3d3344b53d40c017d921c91fbf3d8579f12f5cbee6ec9e112bd68b7d18345b7d",
        "mod_editor/core/nfl2k5_roster_records.py": "dcbbf5da41d8cae027ec89669a87f70703069fba3753e9ce8848b0e1029b9340",
        "mod_editor/core/nfl2k5_roster_storage.py": "b2bed5fb92dedd9d1c4312a7e9344ca1558225d9ed12977e4fe69f4ca9d85bb6",
        "mod_editor/core/nfl2k5_safe_text_banks.py": "c7ea4288611615204f53c40f5da06728bd9e5511eec5ae06711145e509461d48",
        "mod_editor/core/nfl2k5_save_rost.py": "2440e0796000f08bff319e5967675fc0b4df09ad7534733562fbbb22d8fbdac2",
        "mod_editor/core/nfl2k5_save_writer.py": "5a883cd1e449e8c796dc9453e6e9245390715d081979c024ac1182ef2c483bc4",
        "mod_editor/core/nfl2k5_scorebar_v3.py": "406ed027b583e9d49dee9a671eab085af171c2d2b50ab5bc115e487ff45d5d91",
        "mod_editor/core/nfl2k5_scorebug_exact.py": "3cd8455f641247979ed1b0bc2fc12342dfbecb81d3d2e9ff34400cc25a8c6b03",
        "mod_editor/core/nfl2k5_scorebug_fonts.py": "b292f93b7bc25b64a379069b77c9172c1b92cf79553bfe4a7be835d1ad7119e9",
        "mod_editor/core/nfl2k5_scorebug_ingame.py": "8ac07aee28a23c23bacf5b65a0d2529fb43be2028fcc3ed83a9e61f9cf017e30",
        "mod_editor/core/nfl2k5_scorebug_resources.py": "8e4addf4db21d0b23f5209ab15f336031a9e90961613cf05ebbf5cb9bcdafd9b",
        "mod_editor/core/nfl2k5_scorebug_runtime.py": "df0cf28bcf094b390f01baaa80ac39c0371f9bead62c5c6b6c7cad1a04bbb1c7",
        "mod_editor/core/nfl2k5_scorebug_source_art.py": "a3617552d90389df8e7ce4d78faa8fd64a1995c91e4e8ef93219007761ac27fd",
        "mod_editor/core/nfl2k5_scorebug_template.py": "409f7324352b88a6b4387b1f1a8ee1231c56f9674d7762ece24a8142fd2d2060",
        "mod_editor/core/nfl2k5_scorebug_unified_adapter.py": "3307d3b1777fcb51f112dea2c6c5290dd969c3037d5bc21112f9740b7cef9bfd",
        "mod_editor/core/nfl2k5_scramble_tuning.py": "f9e85191b7d93849a92a749385bdd746609465238e776ea0e7f072ac29bf2e92",
        "mod_editor/core/nfl2k5_screen_hooks.py": "4e2d53a15e47e45ba76ec4a6c7d34d96bc100160aaab507c8c0a1f2b04eae27b",
        "mod_editor/core/nfl2k5_screen_hooks_code.py": "bcab9155aceb1e62e2cb1e5a7b98231ec7cf101ae3623a8e0b2397dd4ab27b33",
        "mod_editor/core/nfl2k5_screen_timing.py": "0627fa31055f019d64d0cc3edd5f550734e59696a196c62882b0c81056c65a88",
        "mod_editor/core/nfl2k5_season_cap.py": "dda1e4d3a11bfe798d837ab8629bfa1d4e90fc233417e39de1974ac1c5b959c6",
        "mod_editor/core/nfl2k5_season_length.py": "1346dd254f3bddccefe67ee54f9f29cce894f9e89cb279530d995fed86c910bc",
        "mod_editor/core/nfl2k5_senior_bowl.py": "e415ac02f3170f74c23137ba4f487d4dc4b4f10c1db4565d753d0558b846647c",
        "mod_editor/core/nfl2k5_senior_bowl_code.py": "000abee8fc9bf5d382d4c8934a0509c32de7976805eadabb5c4aed3ccb0812da",
        "mod_editor/core/nfl2k5_seven_on_seven.py": "2c2874feedf4b1818ef7cd35bcce9229fd27848f831de732cb11a217ab575c84",
        "mod_editor/core/nfl2k5_seven_on_seven_book.py": "d681b30dfec2cb8d438dd4d67ea6585aaf4244c888ae7ef3e632df0d4ee7ee59",
        "mod_editor/core/nfl2k5_source_cache.py": "91ba6711fbe675a7a23d296a8989d6e985e6a262c89cb320ee5a06742876fac7",
        "mod_editor/core/nfl2k5_special_roles.py": "5c51ee9bcaae8e6a9c520430a9d6ad5c711b08043d2332d5161420022438d967",
        "mod_editor/core/nfl2k5_stadium_cache.py": "af3f8983f4312f755f27456684e6e27505d41eda07539ebcd813b90c81a88762",
        "mod_editor/core/nfl2k5_stadium_studio.py": "7ec5b2b65b3e6be605e91ae772dd15c3eb71ac46398e2ecab0a1c181cf4fef7d",
        "mod_editor/core/nfl2k5_stadium_texture_writer.py": "dc1bf06c20c86411ff4c91e09003c9f561f3c7aada142ed522ca237d7d0d18f5",
        "mod_editor/core/nfl2k5_team_column.py": "465ae89093c76404e71653004c3bb1a0cd60ef9c1ebec4df7b639f4fe94e6337",
        "mod_editor/core/nfl2k5_team_history.py": "e8620bb41a4e76b7b84e10f1f8f4abce4052061507089a97503339e3b4b1b5ae",
        "mod_editor/core/nfl2k5_text_catalog.py": "514706a38b28a4c7189f49e7601813cd55e16f1b9e81c9c8aa3e92c072e962c9",
        "mod_editor/core/nfl2k5_throw_arc.py": "0fbf33d12fe27a0f940fb7e13f375390b88701c4ccb7e89a1de895d8f66b9c3c",
        "mod_editor/core/nfl2k5_throw_tuning.py": "ffdc3859c0b9892ade179679d9b943a46d86b1bf284cfebbeedf54b05b2153cd",
        "mod_editor/core/nfl2k5_unif_color_writer.py": "5e950cc404e25c1fbeff7ee5aa2a3fad235115aeddd743e95be6862677a88324",
        "mod_editor/core/nfl2k5_uniform_catalog.py": "342964f000624ce7dcbc552fce01810a93704dca6bc62559cc7a73b89f8c59a1",
        "mod_editor/core/nfl2k5_uniform_choice.py": "485a0b64855836d03573381281b079a9cdab814996fa83b894046d8b29f93d6a",
        "mod_editor/core/nfl2k5_uniform_equipment_writer.py": "89959c31762e5e758d7abf25dca533c71a0436db768da2c8c5df52f4c81b3b55",
        "mod_editor/core/nfl2k5_universal_asset_index.py": "9df3c0a754abcb60fa4db3afd0f9b8af364f60551014d259e2713f5387491421",
        "mod_editor/core/nfl2k5_weekly_prep.py": "5b3b9847f24246b33be5d63d141908f7241ea3da7a62a8d9736c0964b0bff933",
        "mod_editor/core/nfl2k5_weekly_prep_code.py": "554fb7018dd0d2d5c59bd230cffd64d3be1cbc910df6410e40920cd3c08e97f8",
        "mod_editor/core/nfl2k5_weekly_prep_save.py": "aedb0576c3a19a3a6574362729f83d3dfac5bc4aae7eb203388403c721a83720",
        "mod_editor/core/nfl2k5_widescreen.py": "e3c24be27e02098ef981349aa9a1008b26d022bf655c0c0c6e4e70557c0f0f43",
        "mod_editor/core/nfl2k5_xbe_space.py": "cba5f40d4dd7940032fb90b5554e1605f3f773c94b42871dbd119a9ede49e74b",
        "mod_editor/core/nfl2k5_zone_drop.py": "96b915ac40cfbcb61b9bfa88a584a18841635e061947a7e1644ea193f83a94f0",
        "mod_editor/core/nfl_audio.py": "31193529647bd5fc35a2c25d38bccb83d20b16d46358169c26ced120c6c8e05c",
        "mod_editor/core/platform_compat.py": "cbcf52e782c474b91dbb2c36f35547e88e8062d4f3e0434baa8314e695a1e811",
        "mod_editor/core/recipes.py": "10d518fc5bf0dab89cc9d1b0b055dda880ad0f24e2e7aee8dbe9d74fda2d97d8",
        "mod_editor/core/sources.py": "d47ef48a21d0cb4bb47e2b0f5ace029e68c3dc8906caa7d48e19e6dea4341375",
        "mod_editor/core/texture_master.py": "2597b4d177703f8c81e3c10eb9ded655390ccfa47f36bfab8d06fab1b0e79098",
        "mod_editor/studio/audio_annotations.py": "c45c94b011d703a24d063138f82477814495705c3b0055a9a867dbab453ba923",
        "mod_editor/studio/audio_bundle.py": "fafc659024246d1cff782ab07f6c744c97a563f64fedca8a288f3126fbeb4604",
        "mod_editor/studio/music_service.py": "594e9e51859e1387c887da8f5f7a2299bd3657ef44443936d23b4e80d1838a04",
        "mod_editor/studio/project_archive.py": "3556062a7cf178ef416706543e71270783d04439494420810fb7a10ca7f01479",
        "mod_editor/studio/session.py": "665ab4888cfdf5999eb7aeeb50ef870bfbed759c7d42f945a9fe054404779715",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/game_audio_convert.py": "3ba3f1f4c2aa452198a12e65d8e93e8d690988d0a6a88c80d7c5de91c1e5a983",
        "tools/nfl2k5_commentary_swap.py": "d12b0a4595155acf97545b01fa82791b43357e5a07a1569a58b1135e9faa965d",
        "tools/nfl2k5_jersey_png_workflow.py": "e7af6773a07085da33745e62bfccc59c2f013e833f2aa1ae9009c965938f5832",
        "tools/nfl2k5_playbook_position_recode.py": "326ea888c7e4c7281d231ea02b495ee8af6289770cf122ba6299f0518126adc9",
        "tools/nfl2k5_scorebug_espn_art.py": "4bd1e9fb9166ddfbe1423f3e2c41ed2424841a0ae476270c2117de2a9e006780",
        "tools/nfl2k5_scorebug_layout.py": "63ee159943a6494de331339e7460cb674955698c1d0d6a3aa8057e024967dcc5",
        "tools/nfl2k5_scorebug_position_patch.py": "eb2b913bd4d0620dcefc4f280db1f6d73e4a5c348b0483a246bbf587506cdbff",
        "tools/nfl2k5_scorebug_reference.py": "32ef741eb84bdf022de8cae357895eea891e6265c025e57afd4d49a37a6f4444",
        "tools/nfl2k5_visual_mod_project.py": "a268a924760d3d7439d19fca389b95ee7309bf80761eb62e3b7617a36f70e929",
        "tools/nfl_all_texture_xiso_workflow.py": "61d0574ae5320cb7b12b96f1be0b34dcf1fdef363091b00de0fd0fac7130bd91",
        "tools/nfl_audo_wav_xiso_workflow.py": "d684cbe7b30f77caf808bcef3d0219777b333336ae5bee4837d10f69cc1d13c6",
        "tools/nfl_create_team_field_art_inventory.py": "da59018f1417871516b75769ea53a351a1d2b03ed855f985c1f88ac333b42489",
        "tools/nfl_create_team_field_art_png_import.py": "f4dff7694bb11f758e78773ff7e23b96500499f198e10efffd7e680765780b08",
        "tools/nfl_crib_bar_monitor_png_xiso.py": "d0ff8f4ebfb20e443dd12892e531a6ac1736831c182c35a19edb94a8f4cc8c11",
        "tools/nfl_crib_team_photo_png_import.py": "00c05c92fe9ee194b2c1c96830efc09aa99f5023687f29b5a08c16f3dbdf9539",
        "tools/nfl_crib_team_photo_targets.py": "e0ec8925ae179ce0955e32c681f7bc866ccd8807d5489791d8f9210bb955b357",
        "tools/nfl_dxt1.py": "bce75aca68acbfaa5112927e228672d4d77c58fc27cd3ce047751d8875dcb9a2",
        "tools/nfl_jersey_tset_png_import.py": "78300a96baa39ec48bab1c84e0f9aaf61674e829c271785427e623a120e7eead",
        "tools/nfl_jersey_tset_targets.py": "6835fbeef8f34aaa137b582a386d630860eccb1bf17cc626232d3ff36bda02e0",
        "tools/nfl_live_face_texture_png_import.py": "e0f7398cbdb87a79593b5a8a61ec12b2ed3b03bb1966d4fb14f581543c2c7864",
        "tools/nfl_live_face_texture_targets.py": "c9748ee6cbb0441fded6c961ef25ec913e3294218c7892eacb731456c315f8d4",
        "tools/nfl_live_helmet_txtr_png_import.py": "0ab06a1d199e434f73d1b012cf4f2429a0c1890132903b6af815c688c327b9fe",
        "tools/nfl_live_helmet_txtr_targets.py": "26b18b9aa8f0afd71e0b137eef52f2cbfd0f2108cb63546979883446bc93325f",
        "tools/nfl_live_numbers_nameplate_png_import.py": "d8451ab1b1fb83963a7dd972b35172c99daa79ecdd70b7c7a47e88086b67df1c",
        "tools/nfl_live_numbers_nameplate_targets.py": "e122e41055e4d3b02ab35041db2e3cbd828fcf90c1b8f258abeb8718c20fc6a4",
        "tools/nfl_outer.py": "0f27ac4157f13704e4303dbf2e146427cc56d1d910a3e242fac4081a04d9ee6d",
        "tools/nfl_pants_tset_png_import.py": "414c4d37ff8421574ab7a5fc40fb0a411dd348a126425b90f9718e5d2ddc114d",
        "tools/nfl_pants_tset_targets.py": "8d5f39d1ee9d62cf6b79600fde31adb61eb77914d49a4efb91e1da10266e3eee",
        "tools/nfl_player_portrait_png_import.py": "d5c9b0b869a02daa48892abf75f2efa43b7b6fa5d961b9bdb446d88327183f94",
        "tools/nfl_player_portrait_targets.py": "0121d71588ad717ca68f4b2c67dbf32f8d0d36eb47b7b1e28bc4d39ce093c3ba",
        "tools/nfl_roster.py": "d81cd9c95e792c3e8df827e9058323ee95b33a9b7833f6f06549355e77528b9b",
        "tools/nfl_scene_probe.py": "851841d8474dbd2e8be098a9c84537057fcc9ced9d4d74669e2b808e00d71450",
        "tools/nfl_scne_gltf.py": "afeb666595742e2a96075fb9d0edb4d8ac913b9e1c2ebfa6ed3ba04496a57207",
        "tools/nfl_scne_inventory.py": "0f58222812df6b380588f8b0a2592101136a863cd0dd170b0f32df726de2fc6b",
        "tools/nfl_scorebug_png_import.py": "0dbef5f87476633d91ebea19aeb86451dd5ac434743ef80a5a694cf4e3975440",
        "tools/nfl_sleeve_tset_png_import.py": "becf2d323f576737ea63380f60a416c7deda95421619b9dc9bdadd2b7458c0b5",
        "tools/nfl_sleeve_tset_targets.py": "41cd48b6dc9f4779bca4d9e9ecf6e32246dfbc34034385c40b8ecf3ee933953d",
        "tools/nfl_static_gltf.py": "5249732b635374eb33bcb39f162224bccd2163cf1cfd01b1dfc8db42ac40bea3",
        "tools/nfl_team_select_card_png_import.py": "7012a7d75a4203016b532e301f9727ebf5d58f9f88dc1271087c5461e493af1d",
        "tools/nfl_team_select_card_targets.py": "125361ee0aefbcbb46da8d466a1d850c91c3d9f33ea0eced3f2240f4563d5766",
        "tools/nfl_tset_fixed_span_verify.py": "d9a60349538962cb7c3ea8e3d2461b118fbbc10d05e9b68f0fe010f8cc1c2eb1",
        "tools/nfl_tset_png_import.py": "70516de8445f00834cc9f5fc2b41132690a74f4ae449033d1031901b626166cd",
        "tools/nfl_tset_png_import_dynamic_validate.py": "da20c1dff0145780c0d485970a527a0f172ab8a8653977784deae5e7c7ce6a03",
        "tools/nfl_tset_png_import_verify.py": "777ca0ed729e54c41f7b522c4b121f577a573f5b010a851ab36218fff472076b",
        "tools/nfl_tset_png_import_xiso_generic_patch.py": "a84699a55b7e34ff49a28913a7b892ce673fac4b78d427929683c2afc0c68cc2",
        "tools/nfl_txtr.py": "0896e3f409f38116602d37a8902f1403e8afe6ad9e17e9ee9d36244ae97a5107",
        "tools/nfl_uniform_color_xiso_direct_patch.py": "bbd4f5147d19afe3ad3ff0079c5bc0693108b58956bed74444c659718aef4ceb",
        "tools/nfl_uniform_inventory.py": "f2fc4ee3fad2c7eff0e2ca669c7f2642cea38a8c4d5cafb6d17a9c0b6e042740",
        "mod_editor/core/responsive_json.py": "7fb0241f333733941dab16032bbcd1310fa85a46f850a7d774273ff68dccb18c",
        "tools/nfl_vc_lz_fill.py": "7779b1eee05582f1219c70c8a5f19eb6e6b1b7a651c56f51e44feb21684d73af",
        "tools/string_table_inventory.py": "8f69e9b8fe016509739cfbf10594d25e34288ca062b13463d18e9cc9611caefd",
        "tools/xbe_info.py": "c7843c317a7ec022bc22ee6266b96d856b57233af2d6baa71ec071a94212e0ef",
        "tools/xbox_ima_encoder.py": "2f6c7209674d93c542f4c67fdab2ebfa4aaa8a6a21d6b4a08d07a9996bf79d76"
    }
    data_pins: Mapping[str, str] = {
        "mod_editor/data/nfl2k5_crib_catalog.v1.json":
            "c78801144df2f070e003ba458c5affa15a52cc00221cc1a3d9983f1fbf172cd8",
        "mod_editor/data/nfl2k5_equipment_chain_pins.v1.json": "32ab51a7a70aea4e5bec1cff6b3f6542fb7a3f198b494939b8864313bc099628",
        "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json":
            "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173",
        "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json":
            "f44472856044a5d8a50d18476a4c7af18ef98bcc3f7cf1d567db2b33d5336bfa",
        "reports/specs/nfl2k5_crib_static_position_targets.v1.json":
            "90f955166c8582f7041bd0d936bacbef1f44b3869487f71535acec1caeb44b4f",
    }
    backend_schema = "nfl2k5_visual_mod_project/v1"
    source_sha256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
    max_project_bytes = 64 * 1024 * 1024
    backend_audio_kinds = frozenset({
        "menu_back_audio",
        "audo_audio",
        "ausb_audio",
    })
    audio_exact_inventory_relative = Path(
        "derived/audio-source-pcm-fingerprints-v1.json"
    )
    audio_containment_inventory_relative = Path(
        "derived/audio-source-pcm-containment-v2.json"
    )
    backend_kind_order = (
        "torso",
        "sleeve",
        "pants",
        "live_helmet",
        "live_number_nameplate",
        "team_select",
        "live_face",
        "create_team_field_art",
        "team_identity",
        "player_roster",
        "player_portrait",
        "crib_team_photo",
        "crib_standalone_texture",
        "crib_scene_texture",
        "crib_scene_geometry",
        "play_assignment_route",
        "play_formation_create",
        "play_create",
        "play_formation_link",
        "scorebug_texture",
        "stadium_texture",
        "stadium_geometry",
        "p8_texture",
        "uniform_equipment_texture",
        "unif_color",
        "roster_team_text",
        "roster_player_text",
        "universal_fixed_text",
        "menu_back_audio",
        "audo_audio",
        "ausb_audio",
    )
    backend_known_kinds = frozenset(backend_kind_order)
    selector_fields = [
        {
            "allowed": ", ".join(backend_kind_order),
            "name": "kind",
            "required": True,
        },
        {
            "allowed": "kind-specific canonical selector fields",
            "name": "target",
            "required": True,
        },
    ]

    def __init__(
        self,
        runner: CommandRunner | None = None,
        source_hasher: SourceHasher | None = None,
        workspace: Path | None = None,
        contained_source_validator: ContainedSourceValidator | None = None,
    ):
        self.runner = runner or SubprocessCommandRunner()
        self.workspace = workspace or Path(__file__).resolve().parents[2]
        self.source_hasher = source_hasher or self._hash_source
        self.contained_source_validator = (
            contained_source_validator or _is_supported_nfl2k5_container
        )

    def preflight(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> None:
        emit(ProviderEvent(ProviderStage.PREFLIGHT, "INFO", "Checking typed provider contract"))
        self._validate_capability(request, capability)
        project = self._read_project_header(request.backend_project)
        authorized_kinds = self._registry_authorized_kinds(capability)
        project_kinds = {
            edit.get("kind")
            for edit in project["edits"]
            if isinstance(edit, dict) and isinstance(edit.get("kind"), str)
        }
        if len(project_kinds) == 0 or any(
            not isinstance(edit, dict) or not isinstance(edit.get("kind"), str)
            for edit in project["edits"]
        ):
            raise ProviderError("Unified project edits need string kind fields")
        unauthorized = project_kinds - authorized_kinds
        if unauthorized:
            raise ProviderError(
                "Unified project uses backend kinds not authorized by the capability registry: "
                + ", ".join(sorted(unauthorized))
            )
        if project_kinds & self.backend_audio_kinds:
            self._private_audio_argv(request)
        emit(
            ProviderEvent(
                ProviderStage.PREFLIGHT,
                "INFO",
                f"Canonical unified project has {len(project['edits'])} edit(s)",
            )
        )
        source_path = self._regular_non_symlink(Path(request.source.selected_path), "source XISO")
        if (
            not request.source.recognized
            or request.source.detected_game != GameId.NFL2K5.value
            or request.source.fingerprint_id != "nfl2k5-usa-retail-xiso"
            or request.source.kind != "xiso"
        ):
            raise ProviderError(
                "Typed build requires the recognized NFL 2K5 USA retail XISO"
            )
        try:
            inspected_path = Path(request.source.inspected_path).resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise ProviderError("Recognized source inspection path is no longer available") from exc
        if inspected_path != source_path:
            raise ProviderError("Source inspection path does not match the selected XISO")
        self._validate_outputs(request)
        progress_bucket = -1

        def hash_progress(completed: int, total: int) -> None:
            nonlocal progress_bucket
            bucket = 10 if total == 0 else min(10, (completed * 10) // total)
            if bucket != progress_bucket:
                progress_bucket = bucket
                emit(
                    ProviderEvent(
                        ProviderStage.PREFLIGHT,
                        "INFO",
                        f"Read-only source recheck {bucket * 10}%",
                    )
                )

        digest, size = self.source_hasher(source_path, hash_progress)
        if digest != request.source.sha256:
            raise ProviderError("Source XISO changed after editor recognition")
        if size != request.source.size:
            raise ProviderError("Source XISO size changed after editor recognition")
        if (
            digest != self.source_sha256
            and not self.contained_source_validator(source_path)
        ):
            raise ProviderError(
                "Source XISO no longer contains the reviewed NFL 2K5 USA default.xbe"
            )
        emit(ProviderEvent(ProviderStage.PREFLIGHT, "INFO", "Preflight gates passed"))

    def validate(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        result = self._run("validate", request, ProviderStage.VALIDATE, emit)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("Typed validator did not return its canonical JSON report") from exc
        if (
            report.get("schema") != self.backend_schema
            or report.get("schema_and_png_pins_valid") is not True
        ):
            raise ProviderError("Typed validator report did not prove schema and input pins")
        return result

    def build(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        result = self._run("build", request, ProviderStage.BUILD, emit)
        if "NFL2K5_VISUAL_MOD_BUILD_PASS" not in result.stdout:
            raise ProviderError("Typed backend exited without its build success marker")
        return result

    def verify(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        result = self._run("verify", request, ProviderStage.VERIFY, emit)
        if "NFL2K5_VISUAL_MOD_VERIFY_PASS" not in result.stdout:
            raise ProviderError("Independent verifier exited without its success marker")
        return result

    def _run(
        self,
        command: str,
        request: ProviderRequest,
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        with _pinned_execution_bundle(
            self.workspace,
            {**self.module_pins, **self.data_pins},
            self.backend_module,
            "NFL unified visual backend",
        ) as module:
            argv = [
                sys.executable,
                os.fspath(module),
                command,
                "--project",
                os.fspath(request.backend_project),
            ]
            if command != "validate":
                argv.extend(
                    [
                        "--source-xiso",
                        os.fspath(request.source.selected_path),
                        "--output-xiso",
                        os.fspath(request.output_xiso),
                        "--manifest",
                        os.fspath(request.manifest),
                        "--artifact-dir",
                        os.fspath(request.artifact_dir),
                    ]
                )
                project = self._read_project_header(request.backend_project)
                project_kinds = {
                    edit["kind"] for edit in project["edits"]
                    if isinstance(edit, dict) and isinstance(edit.get("kind"), str)
                }
                if project_kinds & self.backend_audio_kinds:
                    argv.extend(self._private_audio_argv(request))
            emit(ProviderEvent(stage, "INFO", f"Starting typed {command} provider"))
            result = self.runner.run(argv, self.workspace, stage, emit)
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip().splitlines()
            tail = " | ".join(details[-5:]) if details else "no diagnostic output"
            raise ProviderError(f"Typed {command} failed with exit {result.returncode}: {tail}")
        return result

    def _validate_capability(self, request: ProviderRequest, capability: Capability) -> None:
        backend = capability.raw.get("backend", {})
        gui = capability.raw.get("gui", {})
        pins = capability.raw.get("source_container", {}).get("hash_pins", [])
        fields = capability.raw.get("selectors", {}).get("fields", [])
        if (
            request.capability_id not in self.capability_ids
            or capability.capability_id != request.capability_id
            or request.game != GameId.NFL2K5
            or capability.game != GameId.NFL2K5
            or capability.classification != Classification.OFFLINE_WRITER_PROVED
            or capability.raw.get("classification")
            != Classification.OFFLINE_WRITER_PROVED.value
            or backend
            != {
                "command": self.backend_command,
                "module": self.backend_module,
                "operation": "write",
            }
            or gui.get("expose") is not True
            or gui.get("mode") != "edit"
            or pins != [self.source_sha256]
            or fields != self.selector_fields
        ):
            raise ProviderError("Capability registry does not authorize this typed provider")
        if self.module_pins.get(self.backend_module) != self.backend_module_sha256:
            raise ProviderError("Allowlisted unified backend hash pin is inconsistent")
        _validate_pin_set(self.workspace, self.module_pins, "NFL unified visual backend")
        _validate_pin_set(self.workspace, self.data_pins, "NFL unified visual data")

    def _read_project_header(self, path: Path) -> dict:
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(f"unified backend project does not exist: {path}") from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
        ):
            raise ProviderError(
                "unified backend project must be a singly-linked, non-symlink regular file"
            )
        resolved = path.resolve(strict=True)
        size = supplied.st_size
        if not 0 < size <= self.max_project_bytes:
            raise ProviderError("Unified backend project size is outside the allowed range")
        descriptor = os.open(
            resolved,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            identity = (opened.st_dev, opened.st_ino)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or identity != (supplied.st_dev, supplied.st_ino)
                or opened.st_size != size
            ):
                raise ProviderError("Unified backend project changed before preflight read")
            chunks: list[bytes] = []
            remaining = size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise ProviderError("Unified backend project shortened during preflight")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ProviderError("Unified backend project grew during preflight")
            current = resolved.stat(follow_symlinks=False)
            if (
                current.st_nlink != 1
                or (current.st_dev, current.st_ino, current.st_size) != (*identity, size)
            ):
                raise ProviderError("Unified backend project pathname changed during preflight")
            payload = b"".join(chunks)
        finally:
            os.close(descriptor)
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ProviderError("Unified backend project is invalid JSON") from exc
        canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if (
            payload != canonical
            or not isinstance(value, dict)
            or set(value) != {"schema", "purpose", "edits"}
            or value.get("schema") != self.backend_schema
            or not isinstance(value.get("purpose"), str)
            or not value["purpose"]
            or not isinstance(value.get("edits"), list)
            or not value["edits"]
        ):
            raise ProviderError("Unified backend project header/schema is not canonical v1")
        return value

    def _registry_authorized_kinds(self, capability: Capability) -> frozenset[str]:
        fields = capability.raw.get("selectors", {}).get("fields", [])
        if fields != self.selector_fields:
            raise ProviderError("Unified capability has no exact registry kind allowlist")
        return self.backend_known_kinds

    def _private_audio_argv(self, request: ProviderRequest) -> tuple[str, ...]:
        """Return backend-owned private safety inputs for one audio build.

        These paths are never accepted from the shareable project document.
        The caller must bind all three from its already-indexed private source
        cache; the backend then reopens and independently authenticates them.
        """

        supplied = (
            request.source_cache_root,
            request.audio_exact_inventory,
            request.audio_containment_inventory,
        )
        if any(value is None for value in supplied):
            raise ProviderError(
                "Audio projects need the indexed game's three private safety "
                "inputs (source cache, exact-origin inventory, and containment "
                "inventory). Reopen the game in 2K5 Mod Studio, let Audio "
                "preparation finish, and build again."
            )
        root_value, exact_value, containment_value = supplied
        if not all(isinstance(value, Path) for value in supplied):
            raise ProviderError("Private audio safety inputs must be local paths")
        assert isinstance(root_value, Path)
        assert isinstance(exact_value, Path)
        assert isinstance(containment_value, Path)

        requested_root = root_value.expanduser()
        try:
            root_info = requested_root.lstat()
            root = requested_root.resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise ProviderError(
                "The private audio source cache is missing; reopen the game in "
                "2K5 Mod Studio and let Audio preparation finish."
            ) from exc
        if (
            not platform_compat.is_canonical_absolute_path(requested_root, root)
            or not stat.S_ISDIR(root_info.st_mode)
            or stat.S_ISLNK(root_info.st_mode)
        ):
            raise ProviderError(
                "The private audio source-cache path is not a canonical local directory"
            )

        expected_exact = root / self.audio_exact_inventory_relative
        expected_containment = root / self.audio_containment_inventory_relative
        resolved: list[Path] = []
        for supplied_path, expected_path, label in (
            (exact_value, expected_exact, "exact-origin inventory"),
            (containment_value, expected_containment, "containment inventory"),
        ):
            candidate = supplied_path.expanduser()
            if not platform_compat.is_canonical_absolute_path(candidate, expected_path):
                raise ProviderError(
                    f"Private audio {label} is not the canonical file in this source cache"
                )
            actual = self._regular_non_symlink(candidate, f"private audio {label}")
            if actual != expected_path:
                raise ProviderError(
                    f"Private audio {label} escapes its canonical source cache"
                )
            resolved.append(actual)

        return (
            "--source-cache-root",
            os.fspath(root),
            "--audio-exact-inventory",
            os.fspath(resolved[0]),
            "--audio-containment-inventory",
            os.fspath(resolved[1]),
        )

    def _validate_outputs(self, request: ProviderRequest) -> None:
        paths = (request.output_xiso, request.manifest, request.artifact_dir)
        canonical: list[Path] = []
        for path in paths:
            requested = path.expanduser()
            if not requested.is_absolute():
                requested = Path.cwd() / requested
            if os.path.lexists(requested):
                raise OutputRefusedError(f"Typed provider output already exists: {requested}")
            parent = requested.parent
            try:
                parent_stat = parent.lstat()
            except FileNotFoundError as exc:
                raise OutputRefusedError(f"Typed provider output parent is missing: {parent}") from exc
            if not stat.S_ISDIR(parent_stat.st_mode) or stat.S_ISLNK(parent_stat.st_mode):
                raise OutputRefusedError("Typed provider output parent must be a non-symlink directory")
            canonical.append(requested.resolve(strict=False))
        if len(set(canonical)) != 3:
            raise OutputRefusedError("Typed provider output, manifest, and artifacts must be distinct")
        protected = {
            Path(request.source.selected_path).resolve(strict=True),
            request.backend_project.resolve(strict=True),
        }
        if any(path in protected for path in canonical):
            raise OutputRefusedError("Typed provider outputs cannot replace source or project inputs")

    @staticmethod
    def _regular_non_symlink(path: Path, label: str) -> Path:
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(f"{label} does not exist: {path}") from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
        ):
            raise ProviderError(f"{label} must be a singly-linked, non-symlink regular file")
        return path.resolve(strict=True)

    @staticmethod
    def _hash_source(
        path: Path, progress: Callable[[int, int], None] | None
    ) -> tuple[str, int]:
        supplied = path.lstat()
        total = supplied.st_size
        completed = 0
        digest = hashlib.sha256()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            identity = (opened.st_dev, opened.st_ino)
            if (
                not stat.S_ISREG(opened.st_mode)
                or stat.S_ISLNK(supplied.st_mode)
                or supplied.st_nlink != 1
                or opened.st_nlink != 1
                or opened.st_size != total
                or identity != (supplied.st_dev, supplied.st_ino)
            ):
                raise ProviderError("Source XISO changed before read-only recheck")
            while True:
                block = os.read(descriptor, 16 * 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                completed += len(block)
                if progress:
                    progress(completed, total)
            current = os.fstat(descriptor)
            pathname = path.lstat()
            if (
                current.st_size != total
                or current.st_nlink != 1
                or completed != total
                or (current.st_dev, current.st_ino) != identity
                or (pathname.st_dev, pathname.st_ino, pathname.st_size)
                != (opened.st_dev, opened.st_ino, total)
                or pathname.st_nlink != 1
            ):
                raise ProviderError("Source XISO changed during read-only recheck")
        finally:
            os.close(descriptor)
        return digest.hexdigest(), total


class Nfl2k5ScorebugProvider:
    """Typed scorebug recipe -> copied XISO -> independent verifier."""

    provider_id = "nfl2k5-scorebug-v1"
    capability_ids = frozenset({"nfl2k5.scorebug_presentation.inventory"})
    backend_module = "tools/nfl2k5_scorebug_mod_project.py"
    backend_module_sha256 = "98b3b656d9101afbed60b42f4390dcb50536e1202632553b8c099088e077f60a"
    module_pins: Mapping[str, str] = {
        backend_module: backend_module_sha256,
        "tools/nfl_outer.py": "0f27ac4157f13704e4303dbf2e146427cc56d1d910a3e242fac4081a04d9ee6d",
        "tools/nfl_scene_probe.py": "851841d8474dbd2e8be098a9c84537057fcc9ced9d4d74669e2b808e00d71450",
        "tools/nfl_scorebug_png_import.py": "0dbef5f87476633d91ebea19aeb86451dd5ac434743ef80a5a694cf4e3975440",
        "tools/nfl_tset_png_import.py": "70516de8445f00834cc9f5fc2b41132690a74f4ae449033d1031901b626166cd",
        "tools/nfl_txtr.py": "0896e3f409f38116602d37a8902f1403e8afe6ad9e17e9ee9d36244ae97a5107",
        "tools/nfl_uniform_color_xiso_direct_patch.py": "bbd4f5147d19afe3ad3ff0079c5bc0693108b58956bed74444c659718aef4ceb",
        "tools/nfl_uniform_inventory.py": "f2fc4ee3fad2c7eff0e2ca669c7f2642cea38a8c4d5cafb6d17a9c0b6e042740",
        "mod_editor/core/responsive_json.py": "7fb0241f333733941dab16032bbcd1310fa85a46f850a7d774273ff68dccb18c",
        "tools/xbe_info.py": "c7843c317a7ec022bc22ee6266b96d856b57233af2d6baa71ec071a94212e0ef",
    }
    recipe_schema_file = "mod_editor/data/nfl2k5_scorebug_mod_project.schema.json"
    recipe_schema_file_sha256 = "2e213dc7448f34f40da2f9ab4cc2a1ccd9b4412390939411c12f231d11d81277"
    backend_schema = "nfl2k5_scorebug_mod_project/v1"
    source_sha256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
    source_size = 6_300_499_968
    max_project_bytes = 64 * 1024
    max_png_bytes = 32 * 1024 * 1024
    target_names = ("score_buga", "shield_espn", "digital_font")
    target_dimensions = {
        "score_buga": (64, 64),
        "shield_espn": (128, 64),
        "digital_font": (128, 128),
    }
    source_pin = {
        "canonical_index_sha256": "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
        "canonical_index_size": 193_710_080,
        "default_xbe_sha256": "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
        "default_xbe_size": 11_948_032,
        "scorebug_audit_sha256": "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1",
        "scorebug_audit_size": 46_512,
        "xiso_sha256": source_sha256,
        "xiso_size": source_size,
    }
    _sha256_re = re.compile(r"^[0-9a-f]{64}$")

    def __init__(
        self,
        runner: CommandRunner | None = None,
        source_hasher: SourceHasher | None = None,
        workspace: Path | None = None,
        contained_source_validator: ContainedSourceValidator | None = None,
    ):
        self.runner = runner or SubprocessCommandRunner()
        self.workspace = workspace or Path(__file__).resolve().parents[2]
        self.source_hasher = source_hasher or Nfl2k5UnifiedVisualProvider._hash_source
        self.contained_source_validator = (
            contained_source_validator or _is_supported_nfl2k5_container
        )

    def preflight(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> None:
        emit(ProviderEvent(ProviderStage.PREFLIGHT, "INFO", "Checking typed scorebug contract"))
        self._validate_capability(request, capability)
        project = self._read_project(request.backend_project)
        pngs = self._pin_project_pngs(project)
        source = self._source_xiso(request)
        self._validate_outputs(request, source, project["path"], pngs)
        progress_bucket = -1

        def progress(completed: int, total: int) -> None:
            nonlocal progress_bucket
            bucket = 10 if total == 0 else min(10, (completed * 10) // total)
            if bucket != progress_bucket:
                progress_bucket = bucket
                emit(
                    ProviderEvent(
                        ProviderStage.PREFLIGHT,
                        "INFO",
                        f"Read-only scorebug source recheck {bucket * 10}%",
                    )
                )

        digest, size = self.source_hasher(source, progress)
        if digest != request.source.sha256 or size != request.source.size:
            raise ProviderError("Scorebug source changed after editor recognition")
        if (
            digest != self.source_sha256
            and not self.contained_source_validator(source)
        ):
            raise ProviderError(
                "Scorebug source no longer contains the reviewed NFL 2K5 USA default.xbe"
            )
        emit(
            ProviderEvent(
                ProviderStage.PREFLIGHT,
                "INFO",
                f"Canonical scorebug project has {len(project['value']['edits'])} edit(s)",
            )
        )

    def validate(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        project = self._read_project(request.backend_project)
        result = self._run("validate", request, ProviderStage.VALIDATE, emit)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("Scorebug validator did not return its canonical JSON report") from exc
        edits = project["value"]["edits"]
        targets = [edit["target"] for edit in edits]
        expected_dimensions = {
            target: {
                "width": self.target_dimensions[target][0],
                "height": self.target_dimensions[target][1],
            }
            for target in targets
        }
        expected_keys = {
            "edit_count",
            "project_path",
            "project_sha256",
            "schema",
            "source_pins_valid",
            "strict_importers_passed",
            "targets",
            "target_dimensions",
        }
        if (
            not isinstance(report, dict)
            or set(report) != expected_keys
            or report.get("schema") != self.backend_schema
            or type(report.get("edit_count")) is not int
            or report["edit_count"] != len(edits)
            or report.get("project_path") != os.fspath(project["path"])
            or report.get("project_sha256") != hashlib.sha256(project["payload"]).hexdigest()
            or report.get("source_pins_valid") is not True
            or report.get("strict_importers_passed") is not True
            or report.get("targets") != targets
            or report.get("target_dimensions") != expected_dimensions
        ):
            raise ProviderError("Scorebug validator report did not prove the canonical recipe and pins")
        return result

    def build(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        result = self._run("build", request, ProviderStage.BUILD, emit)
        if "NFL2K5_SCOREBUG_MOD_BUILD_PASS" not in result.stdout:
            raise ProviderError("Scorebug writer exited without its build success marker")
        return result

    def verify(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        result = self._run("verify", request, ProviderStage.VERIFY, emit)
        if "NFL2K5_SCOREBUG_MOD_VERIFY_PASS" not in result.stdout:
            raise ProviderError("Independent scorebug verifier exited without its success marker")
        return result

    def _run(
        self,
        command: str,
        request: ProviderRequest,
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        with _pinned_execution_bundle(
            self.workspace,
            self.module_pins,
            self.backend_module,
            "NFL scorebug backend",
        ) as module:
            argv = [
                sys.executable,
                os.fspath(module),
                command,
                "--project",
                os.fspath(request.backend_project),
            ]
            if command != "validate":
                argv.extend(
                    [
                        "--source-xiso",
                        os.fspath(request.source.selected_path),
                        "--output-xiso",
                        os.fspath(request.output_xiso),
                        "--manifest",
                        os.fspath(request.manifest),
                        "--artifact-dir",
                        os.fspath(request.artifact_dir),
                    ]
                )
            emit(ProviderEvent(stage, "INFO", f"Starting typed scorebug {command} provider"))
            result = self.runner.run(argv, self.workspace, stage, emit)
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip().splitlines()
            tail = " | ".join(details[-5:]) if details else "no diagnostic output"
            raise ProviderError(
                f"Typed scorebug {command} failed with exit {result.returncode}: {tail}"
            )
        return result

    def _validate_capability(self, request: ProviderRequest, capability: Capability) -> None:
        backend = capability.raw.get("backend", {})
        gui = capability.raw.get("gui", {})
        pins = capability.raw.get("source_container", {}).get("hash_pins", [])
        fields = capability.raw.get("selectors", {}).get("fields", [])
        if (
            request.capability_id not in self.capability_ids
            or capability.capability_id != request.capability_id
            or request.game != GameId.NFL2K5
            or capability.game != GameId.NFL2K5
            or capability.classification != Classification.OFFLINE_WRITER_PROVED
            or backend.get("operation") != "write"
            or backend.get("module") != self.backend_module
            or gui.get("expose") is not True
            or gui.get("mode") != "edit"
            or pins != [self.source_sha256]
            or fields
            != [
                {
                    "allowed": ", ".join(self.target_names),
                    "name": "target",
                    "required": True,
                }
            ]
            or capability.accepted_extensions != (".png",)
        ):
            raise ProviderError("Capability registry does not exactly authorize the scorebug provider")
        if self.module_pins.get(self.backend_module) != self.backend_module_sha256:
            raise ProviderError("Allowlisted scorebug backend hash changed")
        _validate_pin_set(self.workspace, self.module_pins, "NFL scorebug backend")
        _read_pinned_payload(
            self.workspace,
            self.recipe_schema_file,
            self.recipe_schema_file_sha256,
            "NFL scorebug recipe schema",
        )

    def _pinned_backend(self) -> Path:
        _read_pinned_payload(
            self.workspace,
            self.backend_module,
            self.backend_module_sha256,
            "scorebug backend",
        )
        return (self.workspace / self.backend_module).resolve(strict=True)

    def _read_project(self, path: Path) -> dict[str, object]:
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(f"Scorebug project does not exist: {path}") from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
            or not 0 < supplied.st_size <= self.max_project_bytes
        ):
            raise ProviderError(
                "Scorebug project must be a small, singly-linked, non-symlink regular file"
            )
        resolved = path.resolve(strict=True)
        descriptor = os.open(
            resolved,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            identity = (opened.st_dev, opened.st_ino)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or identity != (supplied.st_dev, supplied.st_ino)
                or opened.st_size != supplied.st_size
            ):
                raise ProviderError("Scorebug project changed before preflight read")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    raise ProviderError("Scorebug project shortened during preflight")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ProviderError("Scorebug project grew during preflight")
            current = resolved.stat(follow_symlinks=False)
            if (
                current.st_nlink != 1
                or (current.st_dev, current.st_ino, current.st_size)
                != (*identity, opened.st_size)
            ):
                raise ProviderError("Scorebug project pathname changed during preflight")
            payload = b"".join(chunks)
        finally:
            os.close(descriptor)
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("Scorebug project is invalid UTF-8 JSON") from exc
        canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if (
            payload != canonical
            or not isinstance(value, dict)
            or set(value) != {"schema", "purpose", "source", "edits"}
            or value.get("schema") != self.backend_schema
            or not isinstance(value.get("purpose"), str)
            or not 0 < len(value["purpose"]) <= 4096
            or "\0" in value["purpose"]
            or value.get("source") != self.source_pin
            or not isinstance(value.get("edits"), list)
            or not 1 <= len(value["edits"]) <= len(self.target_names)
        ):
            raise ProviderError("Scorebug project is not canonical typed v1 JSON")
        names: list[str] = []
        for edit in value["edits"]:
            if (
                not isinstance(edit, dict)
                or set(edit) != {"target", "png", "png_size", "png_sha256"}
                or not isinstance(edit.get("target"), str)
                or edit["target"] not in self.target_names
                or not isinstance(edit.get("png"), str)
                or not edit["png"]
                or "\0" in edit["png"]
                or type(edit.get("png_size")) is not int
                or not 0 < edit["png_size"] <= self.max_png_bytes
                or not isinstance(edit.get("png_sha256"), str)
                or self._sha256_re.fullmatch(edit["png_sha256"]) is None
            ):
                raise ProviderError("Scorebug project has an invalid edit record")
            names.append(edit["target"])
        if len(names) != len(set(names)):
            raise ProviderError("Each scorebug target may appear at most once")
        return {"path": resolved, "payload": payload, "value": value}

    def _pin_project_pngs(self, project: dict[str, object]) -> tuple[Path, ...]:
        value = project["value"]
        project_path = project["path"]
        assert isinstance(value, dict) and isinstance(project_path, Path)
        result: list[Path] = []
        for edit in value["edits"]:
            png = Path(edit["png"])
            if not png.is_absolute():
                png = project_path.parent / png
            try:
                supplied = png.lstat()
            except FileNotFoundError as exc:
                raise ProviderError(f"Scorebug PNG does not exist: {png}") from exc
            if (
                not stat.S_ISREG(supplied.st_mode)
                or stat.S_ISLNK(supplied.st_mode)
                or supplied.st_nlink != 1
                or supplied.st_size != edit["png_size"]
                or not 0 < supplied.st_size <= self.max_png_bytes
            ):
                raise ProviderError("Scorebug PNG type or size differs from its project pin")
            resolved = png.resolve(strict=True)
            descriptor = os.open(
                resolved,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            )
            try:
                opened = os.fstat(descriptor)
                identity = (opened.st_dev, opened.st_ino)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or identity != (supplied.st_dev, supplied.st_ino)
                    or opened.st_size != supplied.st_size
                ):
                    raise ProviderError("Scorebug PNG changed before preflight read")
                digest = hashlib.sha256()
                remaining = opened.st_size
                while remaining:
                    block = os.read(descriptor, min(1024 * 1024, remaining))
                    if not block:
                        raise ProviderError("Scorebug PNG shortened during preflight")
                    digest.update(block)
                    remaining -= len(block)
                if os.read(descriptor, 1):
                    raise ProviderError("Scorebug PNG grew during preflight")
                current = resolved.stat(follow_symlinks=False)
                if (
                    current.st_nlink != 1
                    or (current.st_dev, current.st_ino, current.st_size)
                    != (*identity, opened.st_size)
                ):
                    raise ProviderError("Scorebug PNG pathname changed during preflight")
            finally:
                os.close(descriptor)
            if digest.hexdigest() != edit["png_sha256"]:
                raise ProviderError("Scorebug PNG SHA-256 differs from its project pin")
            result.append(resolved)
        if len(result) != len(set(result)) or project_path in result:
            raise ProviderError("Scorebug project PNG inputs must be distinct regular files")
        return tuple(result)

    def _source_xiso(self, request: ProviderRequest) -> Path:
        source = Path(request.source.selected_path)
        if (
            not request.source.recognized
            or request.source.detected_game != GameId.NFL2K5.value
            or request.source.fingerprint_id != "nfl2k5-usa-retail-xiso"
            or request.source.kind != "xiso"
        ):
            raise ProviderError(
                "Typed scorebug build requires the recognized NFL 2K5 USA retail XISO"
            )
        resolved = Nfl2k5UnifiedVisualProvider._regular_non_symlink(source, "source XISO")
        if Path(request.source.inspected_path).resolve(strict=True) != resolved:
            raise ProviderError("Scorebug source inspection path does not match the selected XISO")
        return resolved

    def _validate_outputs(
        self,
        request: ProviderRequest,
        source: Path,
        project: Path,
        pngs: tuple[Path, ...],
    ) -> None:
        paths = (request.output_xiso, request.manifest, request.artifact_dir)
        canonical: list[Path] = []
        for path in paths:
            requested = path.expanduser()
            if not requested.is_absolute():
                requested = Path.cwd() / requested
            if os.path.lexists(requested):
                raise OutputRefusedError(f"Typed scorebug provider output already exists: {requested}")
            try:
                parent = requested.parent.lstat()
            except FileNotFoundError as exc:
                raise OutputRefusedError(
                    f"Typed scorebug provider output parent is missing: {requested.parent}"
                ) from exc
            if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
                raise OutputRefusedError(
                    "Typed scorebug output parent must be a non-symlink directory"
                )
            canonical.append(requested.resolve(strict=False))
        if len(set(canonical)) != 3:
            raise OutputRefusedError(
                "Scorebug output XISO, manifest, and artifact directory must be distinct"
            )
        protected = {source.resolve(strict=True), project.resolve(strict=True), *pngs}
        if any(path in protected for path in canonical):
            raise OutputRefusedError(
                "Scorebug provider outputs cannot replace source, project, or PNG inputs"
            )


class Apf2k8JerseyColorProvider:
    """Typed APF asset-index recipe -> copied 0A -> independent verifier."""

    provider_id = "apf2k8-jersey-color-v1"
    capability_ids = frozenset({"apf2k8.uniforms.jersey_00_23"})
    backend_module = "tools/apf_jersey_family_patch.py"
    backend_module_sha256 = "4af9b5258406c2151e033aab475ef6216e081daa26b1cde18130bcd68ef593b9"
    verifier_module = "tools/apf_jersey_family_verify.py"
    verifier_module_sha256 = "3509315eb7c5b95e892eab150453c7881235bd62adc00c626ea54f1451006f5d"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "cbcf52e782c474b91dbb2c36f35547e88e8062d4f3e0434baa8314e695a1e811",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_texture_patch.py": "301cbea24825ddc914498d99befa4db633cb4cd4a47119dec698942f3cd40f18",
        "tools/apf_uniform_mip_patch.py": "c93c95c8441ab074eedc83776fda88204a9c68c40ea0455fc619d162825c20f9",
        "tools/apf_xenos_mip_layout.py": "ec07ea62ad67b3fff7e92fb8779c0cf85f65bc9f196c39b374dd19455619f9d7",
    }
    recipe_schema_file = "mod_editor/apf_jersey_recipe.schema.json"
    recipe_schema_file_sha256 = "d883af2ba6f0afe1b27e98911864a8bab6208f83085908518d4b7dfba578d36e"
    recipe_schema = "apf2k8_jersey_color_recipe/v1"
    source_sha256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
    max_recipe_bytes = 64 * 1024
    max_png_bytes = 64 * 1024 * 1024
    asset_label = "jersey"
    png_dimensions = (1024, 1024)
    png_fully_opaque = False
    png_blue_zero = False
    channels_semantics_named = True
    build_success_marker = "APF_JERSEY_FAMILY_PATCH_PASS"
    verify_success_marker = "APF_JERSEY_FAMILY_VERIFY_PASS"

    def __init__(
        self,
        runner: CommandRunner | None = None,
        source_hasher: SourceHasher | None = None,
        workspace: Path | None = None,
    ):
        self.runner = runner or SubprocessCommandRunner()
        self.workspace = workspace or Path(__file__).resolve().parents[2]
        self.source_hasher = source_hasher or Nfl2k5UnifiedVisualProvider._hash_source

    def preflight(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> None:
        emit(ProviderEvent(
            ProviderStage.PREFLIGHT,
            "INFO",
            f"Checking typed APF {self.asset_label} contract",
        ))
        self._validate_capability(request, capability)
        recipe = self._read_recipe(request.backend_project)
        self._validate_png(recipe["png"])
        source = self._source_0a(request)
        self._validate_outputs(request, source, recipe["png"])
        progress_bucket = -1

        def progress(completed: int, total: int) -> None:
            nonlocal progress_bucket
            bucket = 10 if total == 0 else min(10, (completed * 10) // total)
            if bucket != progress_bucket:
                progress_bucket = bucket
                emit(
                    ProviderEvent(
                        ProviderStage.PREFLIGHT,
                        "INFO",
                        f"Read-only APF 0A recheck {bucket * 10}%",
                    )
                )

        digest, size = self.source_hasher(source, progress)
        if digest != self.source_sha256 or digest != request.source.sha256:
            raise ProviderError("APF 0A changed or does not match the pinned retail SHA-256")
        if size != request.source.size:
            raise ProviderError("APF 0A size changed after editor recognition")
        emit(
            ProviderEvent(
                ProviderStage.PREFLIGHT,
                "INFO",
                f"APF {self.asset_label} asset {recipe['asset_index']} and "
                f"{self.png_dimensions[0]}x{self.png_dimensions[1]} RGBA PNG passed preflight",
            )
        )

    def validate(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        module = self.workspace / self.verifier_module
        argv = (
            sys.executable,
            os.fspath(module),
            "validate-recipe",
            "--recipe",
            os.fspath(request.backend_project),
        )
        result = self._run(argv, ProviderStage.VALIDATE, emit)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"APF {self.asset_label} recipe validator did not return canonical JSON"
            ) from exc
        if (
            report.get("schema") != self.recipe_schema
            or report.get("recipe_valid") is not True
            or report.get("png_dimensions") != list(self.png_dimensions)
            or report.get("png_mode") != "RGBA"
            or (
                self.png_fully_opaque
                and report.get("png_fully_opaque") is not True
            )
            or (
                self.png_blue_zero
                and report.get("png_blue_zero") is not True
            )
            or (
                self.png_blue_zero
                and report.get("png_alpha_255") is not True
            )
            or (
                not self.channels_semantics_named
                and report.get("channel_semantics_named") is not False
            )
            or type(report.get("asset_index")) is not int
            or not 0 <= report["asset_index"] <= 23
        ):
            raise ProviderError(
                f"APF {self.asset_label} recipe validator did not prove the typed recipe/PNG contract"
            )
        return result

    def build(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        recipe = self._read_recipe(request.backend_project)
        source = self._source_0a(request)
        module = self.workspace / self.backend_module
        argv = (
            sys.executable,
            os.fspath(module),
            "--index",
            os.fspath(source),
            "--asset-index",
            str(recipe["asset_index"]),
            "--png",
            os.fspath(recipe["png"]),
            "--output-volume",
            os.fspath(request.output_xiso),
            "--manifest",
            os.fspath(request.manifest),
        )
        result = self._run(argv, ProviderStage.BUILD, emit)
        if self.build_success_marker not in result.stdout:
            raise ProviderError(
                f"APF {self.asset_label} writer exited without its build success marker"
            )
        return result

    def verify(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        source = self._source_0a(request)
        module = self.workspace / self.verifier_module
        argv = (
            sys.executable,
            os.fspath(module),
            "verify",
            "--recipe",
            os.fspath(request.backend_project),
            "--source-0a",
            os.fspath(source),
            "--output-0a",
            os.fspath(request.output_xiso),
            "--manifest",
            os.fspath(request.manifest),
            "--artifact-dir",
            os.fspath(request.artifact_dir),
        )
        result = self._run(argv, ProviderStage.VERIFY, emit)
        if self.verify_success_marker not in result.stdout:
            raise ProviderError(
                f"Independent APF {self.asset_label} verifier exited without its success marker"
            )
        return result

    def _run(
        self,
        argv: Sequence[str],
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        if len(argv) < 2:
            raise ProviderError("Typed APF provider argv has no allowlisted entry module")
        try:
            relative = (
                Path(argv[1])
                .resolve(strict=False)
                .relative_to(self.workspace.resolve(strict=True))
                .as_posix()
            )
        except (OSError, ValueError) as exc:
            raise ProviderError("Typed APF provider entry module is outside the workspace") from exc
        if relative not in {self.backend_module, self.verifier_module}:
            raise ProviderError("Typed APF provider entry module is not allowlisted for this route")
        with _pinned_execution_bundle(
            self.workspace,
            self.module_pins,
            relative,
            f"APF {self.asset_label} backend",
        ) as module:
            fixed = (os.fspath(argv[0]), os.fspath(module), *map(os.fspath, argv[2:]))
            emit(
                ProviderEvent(
                    stage,
                    "INFO",
                    f"Starting typed APF {stage.value.lower()} provider",
                )
            )
            result = self.runner.run(fixed, self.workspace, stage, emit)
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip().splitlines()
            tail = " | ".join(details[-5:]) if details else "no diagnostic output"
            raise ProviderError(
                f"Typed APF {stage.value.lower()} failed with exit {result.returncode}: {tail}"
            )
        return result

    def _validate_capability(self, request: ProviderRequest, capability: Capability) -> None:
        backend = capability.raw.get("backend", {})
        gui = capability.raw.get("gui", {})
        pins = capability.raw.get("source_container", {}).get("hash_pins", [])
        fields = capability.raw.get("selectors", {}).get("fields", [])
        if (
            request.capability_id not in self.capability_ids
            or capability.capability_id != request.capability_id
            or request.game != GameId.APF2K8
            or capability.game != GameId.APF2K8
            or capability.classification != Classification.OFFLINE_WRITER_PROVED
            or backend.get("operation") != "write"
            or backend.get("module") != self.backend_module
            or gui.get("expose") is not True
            or gui.get("mode") != "edit"
            or pins != [self.source_sha256]
            or fields != [{"allowed": "0..23", "name": "asset_index", "required": True}]
        ):
            raise ProviderError(
                f"Capability registry does not exactly authorize the APF {self.asset_label} provider"
            )
        if (
            self.module_pins.get(self.backend_module) != self.backend_module_sha256
            or self.module_pins.get(self.verifier_module) != self.verifier_module_sha256
        ):
            raise ProviderError(
                f"Allowlisted APF {self.asset_label} writer/verifier hash pin is inconsistent"
            )
        _validate_pin_set(
            self.workspace,
            self.module_pins,
            f"APF {self.asset_label} backend",
        )
        self._pinned_module(
            self.recipe_schema_file,
            self.recipe_schema_file_sha256,
            f"APF {self.asset_label} recipe schema",
        )

    def _pinned_module(self, relative: str, expected: str, label: str) -> Path:
        _read_pinned_payload(self.workspace, relative, expected, label)
        return (self.workspace / relative).resolve(strict=True)

    def _read_recipe(self, path: Path) -> dict[str, object]:
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(
                f"APF {self.asset_label} recipe does not exist: {path}"
            ) from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
            or not 0 < supplied.st_size <= self.max_recipe_bytes
        ):
            raise ProviderError(
                f"APF {self.asset_label} recipe must be a small, singly-linked, "
                "non-symlink regular file"
            )
        resolved = path.resolve(strict=True)
        descriptor = os.open(
            resolved,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            identity = (opened.st_dev, opened.st_ino)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or identity != (supplied.st_dev, supplied.st_ino)
                or opened.st_size != supplied.st_size
            ):
                raise ProviderError(
                    f"APF {self.asset_label} recipe changed before preflight read"
                )
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    raise ProviderError(
                        f"APF {self.asset_label} recipe shortened during preflight"
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ProviderError(
                    f"APF {self.asset_label} recipe grew during preflight"
                )
            current = resolved.stat(follow_symlinks=False)
            if (
                current.st_nlink != 1
                or (current.st_dev, current.st_ino, current.st_size)
                != (*identity, opened.st_size)
            ):
                raise ProviderError(
                    f"APF {self.asset_label} recipe pathname changed during preflight"
                )
            payload = b"".join(chunks)
        finally:
            os.close(descriptor)

        seen: set[str] = set()

        def pairs(rows):
            result = {}
            for key, value in rows:
                if key in seen:
                    raise ProviderError(
                        f"APF {self.asset_label} recipe has duplicate key: {key}"
                    )
                seen.add(key)
                result[key] = value
            return result

        try:
            value = json.loads(payload, object_pairs_hook=pairs)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError(
                f"APF {self.asset_label} recipe is invalid UTF-8 JSON"
            ) from exc
        canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if (
            payload != canonical
            or not isinstance(value, dict)
            or set(value) != {"schema", "asset_index", "png"}
            or value.get("schema") != self.recipe_schema
            or type(value.get("asset_index")) is not int
            or not 0 <= value["asset_index"] <= 23
            or not isinstance(value.get("png"), str)
            or not value["png"]
            or "\0" in value["png"]
        ):
            raise ProviderError(
                f"APF {self.asset_label} recipe is not canonical typed v1 JSON"
            )
        png = Path(value["png"]).expanduser()
        if not png.is_absolute():
            png = resolved.parent / png
        try:
            png_supplied = png.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(
                f"APF {self.asset_label} PNG does not exist: {png}"
            ) from exc
        if (
            not stat.S_ISREG(png_supplied.st_mode)
            or stat.S_ISLNK(png_supplied.st_mode)
            or png_supplied.st_nlink != 1
        ):
            raise ProviderError(
                f"APF {self.asset_label} PNG path must be a singly-linked, "
                "non-symlink regular file"
            )
        png = png.resolve(strict=True)
        if png == resolved or png.suffix.lower() != ".png":
            raise ProviderError(
                f"APF {self.asset_label} recipe must name a distinct .png file"
            )
        return {"asset_index": value["asset_index"], "png": png, "path": resolved}

    def _validate_png(self, path: Path) -> None:
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(
                f"APF {self.asset_label} PNG does not exist: {path}"
            ) from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
            or not 0 < supplied.st_size <= self.max_png_bytes
        ):
            raise ProviderError(
                f"APF {self.asset_label} PNG must be a bounded, singly-linked, "
                "non-symlink regular file"
            )
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if (
                opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (supplied.st_dev, supplied.st_ino, supplied.st_size)
            ):
                raise ProviderError(
                    f"APF {self.asset_label} PNG changed before preflight decode"
                )
            payload = bytearray()
            while len(payload) < opened.st_size:
                chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - len(payload)))
                if not chunk:
                    raise ProviderError(
                        f"APF {self.asset_label} PNG shortened during preflight"
                    )
                payload.extend(chunk)
            if os.read(descriptor, 1):
                raise ProviderError(
                    f"APF {self.asset_label} PNG grew during preflight"
                )
            current = path.lstat()
            if (
                current.st_nlink != 1
                or (current.st_dev, current.st_ino, current.st_size)
                != (opened.st_dev, opened.st_ino, opened.st_size)
            ):
                raise ProviderError(
                    f"APF {self.asset_label} PNG pathname changed during preflight"
                )
        finally:
            os.close(descriptor)
        try:
            from PIL import Image, UnidentifiedImageError

            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                if (
                    image.format != "PNG"
                    or image.size != self.png_dimensions
                    or image.mode != "RGBA"
                ):
                    raise ProviderError(
                        f"APF {self.asset_label} PNG must decode as exact "
                        f"{self.png_dimensions[0]}x{self.png_dimensions[1]} RGBA"
                    )
                if (
                    self.png_fully_opaque
                    and image.getchannel("A").getextrema() != (255, 255)
                ):
                    raise ProviderError(
                        f"APF {self.asset_label} PNG must be fully opaque"
                    )
                if (
                    self.png_blue_zero
                    and image.getchannel("B").getextrema() != (0, 0)
                ):
                    raise ProviderError(
                        f"APF {self.asset_label} PNG B channel must be exactly zero"
                    )
        except (UnidentifiedImageError, OSError) as exc:
            raise ProviderError(
                f"APF {self.asset_label} PNG decode failed: {exc}"
            ) from exc

    def _source_0a(self, request: ProviderRequest) -> Path:
        source = Path(request.source.selected_path)
        if (
            not request.source.recognized
            or request.source.detected_game != GameId.APF2K8.value
            or request.source.fingerprint_id != "apf2k8-usa-volume-0a"
            or request.source.kind != "apf-volume-0a"
            or request.source.sha256 != self.source_sha256
            or Path(request.source.inspected_path).resolve(strict=True)
            != source.resolve(strict=True)
        ):
            raise ProviderError(
                f"Typed APF {self.asset_label} build requires the recognized pinned retail 0A file"
            )
        return Nfl2k5UnifiedVisualProvider._regular_non_symlink(source, "source APF 0A")

    def _validate_outputs(
        self, request: ProviderRequest, source: Path, png: Path
    ) -> None:
        paths = (request.output_xiso, request.manifest, request.artifact_dir)
        canonical: list[Path] = []
        for path in paths:
            requested = path.expanduser()
            if not requested.is_absolute():
                requested = Path.cwd() / requested
            if os.path.lexists(requested):
                raise OutputRefusedError(f"Typed APF provider output already exists: {requested}")
            try:
                parent = requested.parent.lstat()
            except FileNotFoundError as exc:
                raise OutputRefusedError(
                    f"Typed APF provider output parent is missing: {requested.parent}"
                ) from exc
            if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
                raise OutputRefusedError("Typed APF output parent must be a non-symlink directory")
            canonical.append(requested.resolve(strict=False))
        if len(set(canonical)) != 3:
            raise OutputRefusedError("APF output 0A, manifest, and artifacts must be distinct")
        protected = {
            source.resolve(strict=True),
            png.resolve(strict=True),
            request.backend_project.resolve(strict=True),
        }
        if any(path in protected for path in canonical):
            raise OutputRefusedError("APF provider outputs cannot replace source, recipe, or PNG")


class Apf2k8PantsColorProvider(Apf2k8JerseyColorProvider):
    """Typed opaque pants recipe -> copied 0A -> independent verifier."""

    provider_id = "apf2k8-pants-color-v1"
    capability_ids = frozenset({"apf2k8.uniforms.pants_color_00_23"})
    backend_module = "tools/apf_pants_family_patch.py"
    backend_module_sha256 = "19fc4fc7ae02f1983ad2b0d1a9ef893cccb19fb92009d959acd0cff993ae2112"
    verifier_module = "tools/apf_pants_family_verify.py"
    verifier_module_sha256 = "4a253a09389c62919e921eb6a9771acf319dc0486ac9b22e0c2c5a4bfe8325a8"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "cbcf52e782c474b91dbb2c36f35547e88e8062d4f3e0434baa8314e695a1e811",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_pants_color_transport.py": "658a124fef839e5252dc89dc6fcd4736698cd2b6a6b053c6f9935bbc75e12871",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_texture_patch.py": "301cbea24825ddc914498d99befa4db633cb4cd4a47119dec698942f3cd40f18",
        "tools/apf_xenos_bc1_mip_layout.py": "02b4198299b7a97e3474460c6bb07763c1aac10518b6fe7c2bd16d473927f07c",
        "tools/nfl_dxt1.py": "bce75aca68acbfaa5112927e228672d4d77c58fc27cd3ce047751d8875dcb9a2",
    }
    recipe_schema_file = "mod_editor/apf_pants_recipe.schema.json"
    recipe_schema_file_sha256 = "c666dda528ef5f9b7ce7597137ee398a6e5bd97db72b236d6688528ae7defc4e"
    recipe_schema = "apf2k8_pants_color_recipe/v1"
    asset_label = "pants"
    png_dimensions = (512, 512)
    png_fully_opaque = True
    build_success_marker = "APF_PANTS_FAMILY_PATCH_PASS"
    verify_success_marker = "APF_PANTS_FAMILY_VERIFY_PASS"


class Apf2k8HelmetColorProvider(Apf2k8JerseyColorProvider):
    """Typed raw R/G helmet recipe -> copied 0A -> independent verifier."""

    provider_id = "apf2k8-helmet-color-v1"
    capability_ids = frozenset({"apf2k8.uniforms.helmet_color_00_23"})
    backend_module = "tools/apf_helmet_family_patch.py"
    backend_module_sha256 = "8f7260bd9005dc451698068c3f84176a8d3b356425943c3b218c638f2b353ca4"
    verifier_module = "tools/apf_helmet_family_verify.py"
    verifier_module_sha256 = "a1c07511ddcaacda083a4970555ee3c61c88c188227b853689dd299cb7841a18"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "cbcf52e782c474b91dbb2c36f35547e88e8062d4f3e0434baa8314e695a1e811",
        "tools/apf_helmet_color_transport.py": "86d4fbf1b43b2dfb02b6d3e35c4829ccaf3b0818edf5bab60903595269a933cb",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_texture_patch.py": "301cbea24825ddc914498d99befa4db633cb4cd4a47119dec698942f3cd40f18",
        "tools/apf_xenos_dxn_mip_layout.py": "85eba338384d518b111dab153120dc937ed45a898d348f4d1548d5f8d8672431",
    }
    recipe_schema_file = "mod_editor/apf_helmet_recipe.schema.json"
    recipe_schema_file_sha256 = "dcc0c90cd0a17d0790490d9595bfb6d831940ca804770e2fda1659add6fbfef0"
    recipe_schema = "apf2k8_helmet_color_recipe/v1"
    asset_label = "helmet two-channel"
    png_dimensions = (256, 1024)
    png_fully_opaque = True
    png_blue_zero = True
    channels_semantics_named = False
    build_success_marker = "APF_HELMET_FAMILY_PATCH_PASS"
    verify_success_marker = "APF_HELMET_FAMILY_VERIFY_PASS"


class Apf2k8ShoulderColorProvider(Apf2k8JerseyColorProvider):
    """Typed shoulder-color recipe -> copied 0A -> independent verifier."""

    provider_id = "apf2k8-shoulder-color-v1"
    capability_ids = frozenset({"apf2k8.uniforms.shoulder_color_00_23"})
    backend_module = "tools/apf_shoulder_family_patch.py"
    backend_module_sha256 = "eef8adb6679337019226621426c1998ffe401bfdea8b7593bbdb30dc212527a8"
    verifier_module = "tools/apf_shoulder_family_verify.py"
    verifier_module_sha256 = "9481262b3bcaa112bcb83c74f596bc09c98b6081a5d3c78162ad35599ae2fbd9"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "cbcf52e782c474b91dbb2c36f35547e88e8062d4f3e0434baa8314e695a1e811",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_shoulder_color_transport.py": "ba654154c990fad1b45760cfd325b352def357e5f1030915323591128e0a9b46",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_texture_patch.py": "301cbea24825ddc914498d99befa4db633cb4cd4a47119dec698942f3cd40f18",
        "tools/apf_uniform_mip_patch.py": "c93c95c8441ab074eedc83776fda88204a9c68c40ea0455fc619d162825c20f9",
        "tools/apf_xenos_mip_layout.py": "ec07ea62ad67b3fff7e92fb8779c0cf85f65bc9f196c39b374dd19455619f9d7",
    }
    recipe_schema_file = "mod_editor/apf_shoulder_recipe.schema.json"
    recipe_schema_file_sha256 = "404c15940d623f4578811406eaf52de5d0fbad6a48b5534402d6f28129d331dc"
    recipe_schema = "apf2k8_shoulder_color_recipe/v1"
    asset_label = "shoulder color"
    png_dimensions = (1024, 1024)
    build_success_marker = "APF_SHOULDER_FAMILY_PATCH_PASS"
    verify_success_marker = "APF_SHOULDER_FAMILY_VERIFY_PASS"


class ProviderOrchestrator:
    """Resolve a capability through an explicit provider map and sequence stages."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        providers: Sequence[TypedProvider] | None = None,
    ):
        self.registry = registry
        if providers is None:
            # Imported only after this module has finished defining the shared
            # provider protocol, avoiding a module-level dependency cycle.
            from .apf_digital_font_provider import Apf2k8DigitalFontProvider
            from .nfl_audio_provider import Nfl2k5MenuBackAudioProvider

            selected: tuple[TypedProvider, ...] = (
                Nfl2k5UnifiedVisualProvider(),
                Nfl2k5ScorebugProvider(),
                Nfl2k5MenuBackAudioProvider(),
                Apf2k8JerseyColorProvider(),
                Apf2k8PantsColorProvider(),
                Apf2k8HelmetColorProvider(),
                Apf2k8ShoulderColorProvider(),
                Apf2k8DigitalFontProvider(),
            )
        else:
            selected = tuple(providers)
        mapping: dict[str, TypedProvider] = {}
        for provider in selected:
            for capability_id in provider.capability_ids:
                if capability_id in mapping:
                    raise ValidationError(f"Duplicate typed provider mapping: {capability_id}")
                mapping[capability_id] = provider
        self._providers: Mapping[str, TypedProvider] = mapping

    def supports(self, capability_id: str) -> bool:
        return capability_id in self._providers

    def provider_id(self, capability_id: str) -> str:
        return self._resolve(capability_id).provider_id

    def validate(
        self, request: ProviderRequest, emit: ProviderEventCallback | None = None
    ) -> ProviderRunResult:
        callback = emit or (lambda _event: None)
        provider, capability = self._begin(request, callback)
        validation = self._stage_call(
            ProviderStage.VALIDATE,
            callback,
            lambda: provider.validate(request, capability, callback),
        )
        callback(ProviderEvent(ProviderStage.COMPLETE, "INFO", "Typed project validation passed"))
        return ProviderRunResult(provider.provider_id, True, False, False, validation, None, None)

    def build_and_verify(
        self, request: ProviderRequest, emit: ProviderEventCallback | None = None
    ) -> ProviderRunResult:
        callback = emit or (lambda _event: None)
        provider, capability = self._begin(request, callback)
        validation = self._stage_call(
            ProviderStage.VALIDATE,
            callback,
            lambda: provider.validate(request, capability, callback),
        )
        build = self._stage_call(
            ProviderStage.BUILD,
            callback,
            lambda: provider.build(request, capability, callback),
        )
        verification = self._stage_call(
            ProviderStage.VERIFY,
            callback,
            lambda: provider.verify(request, capability, callback),
        )
        callback(
            ProviderEvent(
                ProviderStage.COMPLETE,
                "INFO",
                "Build completed and independent reconstruction verified the output",
            )
        )
        return ProviderRunResult(
            provider.provider_id, True, True, True, validation, build, verification
        )

    def _begin(
        self, request: ProviderRequest, emit: ProviderEventCallback
    ) -> tuple[TypedProvider, Capability]:
        provider = self._resolve(request.capability_id)
        capability = self.registry.get(request.capability_id)
        try:
            provider.preflight(request, capability, emit)
        except Exception as exc:
            emit(ProviderEvent(ProviderStage.PREFLIGHT, "ERROR", str(exc)))
            raise
        return provider, capability

    def _resolve(self, capability_id: str) -> TypedProvider:
        try:
            return self._providers[capability_id]
        except KeyError as exc:
            raise ProviderError(
                f"No typed provider is allowlisted for capability: {capability_id}"
            ) from exc

    @staticmethod
    def _stage_call(stage: ProviderStage, emit: ProviderEventCallback, function):
        try:
            return function()
        except Exception as exc:
            emit(ProviderEvent(stage, "ERROR", str(exc)))
            raise


def derived_provider_outputs(output_xiso: Path) -> tuple[Path, Path]:
    requested = output_xiso.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    base = Path(os.path.abspath(os.fspath(requested)))
    return (
        base.with_name(base.name + ".vcmod-manifest.json"),
        base.with_name(base.name + ".vcmod-artifacts"),
    )

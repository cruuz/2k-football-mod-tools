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
    backend_module_sha256 = "de7fe94cea4695f950ab7a2b2cb2f440de9a061b738e0369bdebb557614c0bc7"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/nfl2k5_defense_lint.py": "11863cffaf5250b3c150432b1f74d9f6115e6603fcc6d7a3e6127b9ebb6e2756",
        "mod_editor/core/nfl2k5_espn25_fields.py": "c6d78cdfca03089dece69ddb9ca9f97051d8f6f8fc4c937e7fef4979c23e38eb",
        "mod_editor/core/nfl2k5_super_bowl_walls.py": "59bdad180507344e939d6292677cbce4c810c8938796e82b0e507886adf8ac0d",
        "mod_editor/core/nfl2k5_super_bowl_fields.py": "e78875a6ce29bcd72a3126edc1aca3e48375947b8c69ea6ab525c74a1bf4d2bf",
        "mod_editor/core/nfl2k5_super_bowl_hosts.py": "2048bb3aa21ff53150288bf6d4484405ffffadddeebac258789b60f42564f31f",
        "mod_editor/core/nfl2k5_era_ball.py": "f67735c2fcad8a495c3f47674f22786742bb7da1531639047f15f6504b528e7b",
        "mod_editor/core/nfl2k5_midfield_centre.py": "3cfa613178d15b291e1586c6f1d05da875d4e99438aa06fe3b5f0c02288c5ed2",
        "mod_editor/core/exact_math.py": "31b977deeda09cbb68dcde7561ea54c9ebfad2cb4ff74f6601d681e3f4d68564",
        "mod_editor/core/nfl2k5_allegiant_model.py": "3444c0eca6d678977645ffe83a955bcd23f14da4a00a7642a907edeeeca12f6e",
        "mod_editor/core/nfl2k5_allegiant_venue.py": "adf75beb901280fa9ddb2e5a0e88364fa178437bd39345598f02793b7b0ae4c1",
        "mod_editor/core/nfl2k5_att_model.py": "b6e460856e148855803c52afb9461d442644e9d3546ae74f0f6ca4fc48a03071",
        "mod_editor/core/nfl2k5_att_venue.py": "8b2ffc6f8bcf7459dc74047a055086073db5f53764a511df4621cbbb4e0460b7",
        "mod_editor/core/nfl2k5_board_kit.py": "b5e93761e277fb52385c261ee918a6d80ab0d66f5601dc4ebf15d2d72d5975e0",
        "mod_editor/core/nfl2k5_everbank_model.py": "bd276b34b476e433f351a456b8d53a8a0d155ee040551c72869cf588e61b8a24",
        "mod_editor/core/nfl2k5_everbank_venue.py": "c9800b21db596449d88efb36e3308db953ad8c8a840090e15ccfef4f98451a8c",
        "mod_editor/core/nfl2k5_gillette_model.py": "45d7b5188dfb3cd62e759d210c3acba5f7a8c4f45a458ab5beb863ec1a08426b",
        "mod_editor/core/nfl2k5_gillette_venue.py": "a2fc078b343140004d17875f06849d9484b9155f6d6d033380112f73f8a88ba4",
        "mod_editor/core/nfl2k5_hard_rock_model.py": "7effe8fbf43110f6ed54cfc9afd806d8eec2576beb3948498ffef3be3f7d9123",
        "mod_editor/core/nfl2k5_hard_rock_venue.py": "c94f5e0986ce307ace72f74272da8647bee54296964daa63679932ee66cc47ee",
        "mod_editor/core/nfl2k5_highmark_model.py": "f1acfbf79a888b6542b1d193390234dc6baddf73a12bd6caee528e299cfd0b02",
        "mod_editor/core/nfl2k5_highmark_venue.py": "caf65f301a9f0c1e97bbc76736fd88188c236b98a002157d5998d40392dce46f",
        "mod_editor/core/nfl2k5_lambeau_model.py": "3aad96173fbf2b9f5caf10eb80b7e7cc0b2a1b3552be33f1024cff8cb324e217",
        "mod_editor/core/nfl2k5_lambeau_venue.py": "6e66f5f4872438c13d3d77df0980e5b3b76c7851601b449a093d546482b39af8",
        "mod_editor/core/nfl2k5_levis_model.py": "3dd23633da15f61de03cd903d8522c4551f6259947ccfac40ace9138261e96b5",
        "mod_editor/core/nfl2k5_levis_venue.py": "6f6e2c5ce5d2d38a13e3a73c1f7e827829b921813671e155a7d8f1d26354ad87",
        "mod_editor/core/nfl2k5_lucas_oil_model.py": "049d676aa1c0bd32545089eea2b30380bd71c8652d1ac65e2a4ce26062ceabc3",
        "mod_editor/core/nfl2k5_lucas_oil_venue.py": "106be9ee3376742f2ca9caddf6467f5ccd88f74955010936666047e0c54e1bac",
        "mod_editor/core/nfl2k5_mercedes_benz_model.py": "823f3c7ef417f090b0f8b10d4f799bf5b92a06d5381ae84f5af9edc41ce64cf6",
        "mod_editor/core/nfl2k5_mercedes_benz_venue.py": "a35ced58f2c17e3eb0a088a79ddbcfbbd47a8d40b59d79af84a83051f39b2d21",
        "mod_editor/core/nfl2k5_metlife_crowd.py": "ff42efdd0aace6a5622119e9a265329a4865f7365d74c54d1d70a7989e3d1be9",
        "mod_editor/core/nfl2k5_metlife_model.py": "19db233bd7035e3da5382c2f73fc6870a457d85d531a8542965f560287e4c8ec",
        "mod_editor/core/nfl2k5_model_fan_art.py": "5d1ae475fc1be8d5d987a04d8906a3cb2c84cc1ba21fb3b5e7cf0f3b0abc805f",
        "mod_editor/core/nfl2k5_modern_metlife.py": "66ab7312df3d0e62881935a744cb9661c948b326302790063694dc44c5102fc2",
        "mod_editor/core/nfl2k5_modern_surfaces.py": "09885beed3b0341854fd9d9ab6be10d0ae1ef444bcf88cd43501a61700c89535",
        "mod_editor/core/nfl2k5_broadcast_greens.py": "1819a3085508cfc6493241ee87b6f53fed1a1b8ed6aaa64eaada77603eee7802",
        "mod_editor/core/nfl2k5_modern_venues_2026.py": "59572c748df5ac7317a47e543639a82764c90c2755452fe49f976c07ebc8f918",
        "mod_editor/core/nfl2k5_scne_builder.py": "28357fe693ded37f4f48808ad264d3378a6e923c5d27604b1b9a952020d404d7",
        "mod_editor/core/nfl2k5_sofi_crowd.py": "a3d8c12bf3da19bc35ab115c7e04220b5fd5e36e8ba272c91c9ac2b156c106dc",
        "mod_editor/core/nfl2k5_sofi_model.py": "22e0287a77065f87c7b1f6e02cf8ab4721e6fc8194cf9751ea9c8beafab53b23",
        "mod_editor/core/nfl2k5_sofi_venue.py": "754b26053df033fd0f8265490eab5c8c780bac266142cc41f5695a4113eadb9b",
        "mod_editor/core/nfl2k5_stadium_environment.py": "a7d447b2e8146b260aa113d08e8a8f36c118b7d6741ab58dc99ffb153b780e38",
        "mod_editor/core/nfl2k5_stadium_shadow.py": "ad5cea85c20ac80caa4c00bcb237e6701096254a9c5c3717e3fab3c05a39b87b",
        "mod_editor/core/nfl2k5_stadium_shared_art.py": "9d7e4ecad06d863a9cad8b3dd7c35422fd490f0690e351fe4217fd0149237e36",
        "mod_editor/core/nfl2k5_state_farm_model.py": "4d8fa0bbd4399dea02fc86fa37a4b8198ac3c7251738e1850d0f8657c70cf0fc",
        "mod_editor/core/nfl2k5_state_farm_venue.py": "05a3163dae06970f52263dda7994f798879843f915c5cba42b541584d26548c7",
        "mod_editor/core/nfl2k5_usbank_model.py": "dd3ea4f79880242f9489723b44d45602304fc52f216e6e57029351e2d7269d7c",
        "mod_editor/core/nfl2k5_usbank_venue.py": "388044c9675a4d76ac615772e6772b52f4107f3b93c76a9cc6f342e2a30901a0",
        "mod_editor/core/nfl2k5_anniversary_pack.py": "3e88ec99b02064d65fe511ee8dcb4ee2099371b05472bd81adbb25ed1bfcc75c",
        "mod_editor/core/nfl2k5_marks_store.py": "911a8b18e8bc3b058a71448b0f1bb73803323cf2c9cf1c654c4640087de8d3d6",
        "mod_editor/core/xdvdfs_compact.py": "10397d4b4923f79b6753f54a173ecc9cc352032b27906055ba47469f42d12d67",
        "mod_editor/core/nfl2k5_moment_venues.py": "fa578e8ae40c539c3167f5d3816ac7744a40e77f34c76ce6c7be48f57371213d",
        "mod_editor/core/nfl2k5_historic_styles.py": "3ef49ccca45b672ac4ae090612c8d517b5c57a62f41b21325ad69ec207c06ef6",
        "mod_editor/core/nfl2k5_uniform_slots.py": "6430c34ee1ff62489b049a83d379a420615f8ed1f490a8fa91541077f4f9d3a1",
        "mod_editor/core/nfl2k5_menu_icon_orientation.py": "c65452ffabcb8c234f1be76f313dd0274b88a1e047f2232d624190938af71dad",
        "mod_editor/core/nfl2k5_menu_icon_uf3.py": "63df869c5b997b67a6a39bbcd37d5638658f9b610cf0d3af69ab954c06797580",
        "mod_editor/core/nfl2k5_pants_hem_2026.py": "ae9e1b88f56788ae2e3ec819f535461aa6872047102de1a7d24e9243c596f22d",
        "mod_editor/core/nfl2k5_glyph_fixes_2026.py": "5b509cd0835f26814df5b798e556c763933dda6c8c60d5baca1f4c042a336ac6",
        "mod_editor/core/nfl2k5_menu_chiefs_2026.py": "c60f4b3f79672c299fa19515ece7477de1d15b3bfcc38911e35590682f612f77",
        "mod_editor/core/nfl2k5_menu_helmet_w2026.py": "a01a8edc75729b354b56a32718c20e1059393b3fa6f69bbaa067c340b5480e71",
        "mod_editor/core/nfl2k5_era_rules_code.py": "a493d389359ac7f360b92a03b6713a2ffa8f41a31b1032e3f9824bf8f332499b",
        "mod_editor/core/nfl2k5_era_rules.py": "34c783344c274c09b55265ae81051e900ee33fe3cfc17fb01d5db9631ca4e370",
        "mod_editor/core/nfl2k5_stock_books.py": "d8def627bbe667d5fb8f9e00fbd5bed5f436e30f64ac53571f6a59452a150a6c",
        "mod_editor/core/nfl2k5_moment_gun_weight.py": "ab0fa2a22641666208f5aecdb21d30a99b85c8d23ffeea87c5de37ebd5e29cb9",
        "mod_editor/core/nfl2k5_project_fit.py": "a0184fba0e2b544861fb127ee50f7492c29f9d0667963a492d5cda60fa8ea5fc",
        "mod_editor/core/nfl2k5_my_career_prospects.py": "7c326fbfdaf090c6bf3394af99d266c8f069be8e8a49919f7503e14db9b09c45",
        "mod_editor/core/nfl2k5_rules_patch.py": "07589de43b12b8110ccf8895d9500c3abd4d5b5c14acde7b30f4469c2cc8db6b",
        "mod_editor/core/nfl2k5_coin_defer.py": "c2708dfc02f138d16d8688777cb3b4221dfbbacf1e7317f7865d01ec22de00cd",
        "mod_editor/core/nfl2k5_inbox_standings.py": "4f8d3d31e878a1584d8a0c21a9860a2dd746fdf0f50db383f4bf7ce53b28b19e",
        "mod_editor/core/nfl2k5_coin_defer_code.py": "7b7110e944011df70b67e8b7e7f937da044304a530ee1b0c4dc471ee83585195",
        "mod_editor/core/nfl2k5_coin_defer_code_b779.py": "fbbd7deef5b1d357a3a82d20c3685530b11585f9fa7e66c8c2a336ef4ac41821",  # b780 modes2: frozen beta-69 .. v0.9 RC revision
        "mod_editor/core/nfl2k5_decided_clock.py": "9fdbf3ec93f04366946b8c05b48e312106c8e1273b5d661cb394d4278af9dfec",
        "mod_editor/core/nfl2k5_decided_clock_code.py": "26d142750b0a14c479bf63ae9a17144b91debb561b8827618785392d70e667a8",
        "mod_editor/core/nfl2k5_decided_clock_code_b779.py": "519d35265dadabde1345dfcb876a0b3d81ab0b9bddc564bc48514e6ff65cb361",  # b780 modes2: frozen beta-69 .. v0.9 RC revision
        "mod_editor/core/nfl2k5_cpu_scrambles.py": "b12cd71f227453045fb257f7c681db804a180a01fff7379d2c349593787db78a",
        "mod_editor/core/nfl2k5_cpu_scrambles_code.py": "6f86fc560391fa8e890e1360610357f1f2695da5007eae05a8390efc597fdc66",
        "mod_editor/core/audio_conform.py": "b71528aa23b6dca49bbe023477920661da77cd7c34610dc8f6962be3a0cc9156",
        "mod_editor/core/build_feedback.py": "510fc80b8b080761c54efa891383c10fbf8e84f274c8f787ec8194ac8ba36193",
        "mod_editor/core/build_io.py": "7e1e04876981fb08280560a03c19d61f2aa37fdac4a10c8db65e3fb5025d7887",
        "mod_editor/core/equipment_palette.py": "2886a97ef4dd0d2a2feedd2698dcd521ae64d8992e36d9f2e0fa121b37be6876",
        "mod_editor/core/equipment_reporting.py": "790bf6896f8f50caedf6ed5409b1aa0d759d0129886c8ba6c1000e7528496e6e",
        "mod_editor/core/equipment_staging.py": "75b8417df9e8c6ac638367faad38030c46a903af7c451ceacb8646693601b0c6",
        "mod_editor/core/errors.py": "b5ef4de5c7b67a323cd1dfc6f56ecb62b53a220bdcfd3603500b8fcb0807e086",
        "mod_editor/core/image_use.py": "22a50b66cece72046d84de5ed34f3d04c71c6ac921dba125cf9b08505e71efac",
        "mod_editor/core/json_stream.py": "5933752561dd8b519a301c18ec1d14f13a457f58e6ae337984f543ab2b0838b0",
        "mod_editor/core/metadata_cache.py": "49874cc7f12cc0d36d15b9355dbca64ffe95590ba7582b460738b05aabcd9024",
        "mod_editor/core/build_steps.py": "a3faea414e5a26b8bd77522edae2ece7812679d64fe795b2f07b0bdc4abaa400",  # b791-h3: step context and optional steps
        "mod_editor/core/mod_build.py": "56dd5a5479ad7eeb9e302e57e6d0dfee459e50995a2c8f4617e300fd8fff3083",
        "mod_editor/core/nfl2k5_console_memory.py": "23f83dee0f768a7d3319bb86a64b99b2cd6eb26fef05737ae94f308a46d76538",  # b780-m64b: the 128 MB / 64 MB target (validate_plan)
        "mod_editor/core/studio_inspection.py": "bbe1e2e9b3de63b13e8908d2b37f114ee79b6fb2fc88d26670a6eb1e6e341e1e",  # b780 studio1: mod_build.inspect runs inside its validation memo
        "mod_editor/core/nfl2k5_disc_check.py": "fd57273cf397d47ce5d23d2deaadc7dbf631992e38a70fd13be6dadff098942c",  # b780 studio1: the disc identity names a released SOFTDRINK disc from its list
        "mod_editor/core/model.py": "292f0c5444e32f5cea000fd3cabd6963d7d805a5434dcbc364a36ca2c0f0d228",
        "mod_editor/core/modpack.py": "9358104a7fc4678c6b1292d77adc06627f898a55d4b91492612962d68a3cb3f9",
        "mod_editor/core/modpack_files.py": "62d7cf1f6d7a6e9d6bc4899d2820213c6cfa848776e05d36e50b533af32125ce",
        "mod_editor/core/modpack_ops.py": "a9d0528670ed13904f040a7408f43355d100be7a41939f3c4fdde6e63db48f0e",
        "mod_editor/core/nfl2k5_abilities_runtime.py": "97092be1e9c457950822e7ee734a90a52341cf20412ac610712d0f03f5886e1d",
        "mod_editor/core/nfl2k5_tap_burst.py": "7dcbe2bcf02e19cdf18c2f58ec8974829c2b71333f94059171c5781fcc4e40b6",
        "mod_editor/core/nfl2k5_human_tap_burst.py": "b327e461bba86bab8443aa8a6502e1ae60c65af82978049f1a8616b87879ab67",
        "mod_editor/core/nfl2k5_abilities_runtime_code.py": "efb55d5e000379eea7ab1e48f5810256a18d0534125de20f9884c723aa4f554b",
        "mod_editor/core/nfl2k5_accel_ramp.py": "95014c753d46faed2e75e545d992794bb62965a9bbe6407057d3626395c6e862",
        "mod_editor/core/nfl2k5_accelerated_clock.py": "079ce771155f78b33591000e3f622671dd947a5357e14df165f245331c3bbdb1",
        "mod_editor/core/nfl2k5_accelerated_clock_code.py": "fc301bece04715466d2ee6d23b7b401bb146261f40b00f113a49a669297ed956",
        "mod_editor/core/nfl2k5_animation.py": "2ae98a97fb78b06050a5bfc9ab8a838b30ea36d7a9514132893debe4441b44b6",
        "mod_editor/core/nfl2k5_animation_bones.py": "b82275d45fd4f0b34aaa4613e0ea266724f14270c9069650b5aded3a3f929eb8",
        "mod_editor/core/nfl2k5_animation_import.py": "a1bf3c0b4c15835c946e0373fb2185dbaf748bae0d508a0698f6f4db92d5c50f",
        "mod_editor/core/nfl2k5_animation_math.py": "2b0c8cd4f700a6426e6fc83d605f4db8d14488f2825acd540da0a79586a4ed7e",
        "mod_editor/core/nfl2k5_animation_xbe.py": "3a384b0e5c731e4ec4d11f78ad74223990b0130f99914d1bc5385d1d1da186ad",
        "mod_editor/core/nfl2k5_anniversary_kickoff.py": "dec2efcb8209787e101cfcf0a6513e44a495ec3990ba6a145e91dfb39895cc76",
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
        "mod_editor/core/nfl2k5_boot_logo.py": "9ee25b1fb49859951ba4780ec2b4a3d71773f7199d5a308338acf51f84bdb257",
        "mod_editor/core/nfl2k5_build_service.py": "cdff75f2ceb2da2ad18d38b7c8f1915193f91075ac2275cb204474765d27dcc7",
        "mod_editor/core/nfl2k5_build_settings.py": "a072fa1d2adf05ad0f7b3943a5492ed80d9de728a638e984d613dff4637eb10b",
        "mod_editor/core/nfl2k5_build_service.py": "cdff75f2ceb2da2ad18d38b7c8f1915193f91075ac2275cb204474765d27dcc7",
        "mod_editor/core/nfl2k5_midfield_art.py": "da5ff3541f2d7a7674cd3fc715c831379ecbe17c307951ce547ecaf8d3b4ab89",
        "mod_editor/core/nfl2k5_split_endzone_art.py": "c135625db5663efa13f3f446f98e7cfe8d071148f7b892ea378d18a05d845957",
        "mod_editor/core/exact_math.py": "31b977deeda09cbb68dcde7561ea54c9ebfad2cb4ff74f6601d681e3f4d68564",
        "mod_editor/core/nfl2k5_allegiant_model.py": "3444c0eca6d678977645ffe83a955bcd23f14da4a00a7642a907edeeeca12f6e",
        "mod_editor/core/nfl2k5_allegiant_venue.py": "adf75beb901280fa9ddb2e5a0e88364fa178437bd39345598f02793b7b0ae4c1",
        "mod_editor/core/nfl2k5_att_model.py": "b6e460856e148855803c52afb9461d442644e9d3546ae74f0f6ca4fc48a03071",
        "mod_editor/core/nfl2k5_att_venue.py": "8b2ffc6f8bcf7459dc74047a055086073db5f53764a511df4621cbbb4e0460b7",
        "mod_editor/core/nfl2k5_board_kit.py": "b5e93761e277fb52385c261ee918a6d80ab0d66f5601dc4ebf15d2d72d5975e0",
        "mod_editor/core/nfl2k5_everbank_model.py": "bd276b34b476e433f351a456b8d53a8a0d155ee040551c72869cf588e61b8a24",
        "mod_editor/core/nfl2k5_everbank_venue.py": "c9800b21db596449d88efb36e3308db953ad8c8a840090e15ccfef4f98451a8c",
        "mod_editor/core/nfl2k5_gillette_model.py": "45d7b5188dfb3cd62e759d210c3acba5f7a8c4f45a458ab5beb863ec1a08426b",
        "mod_editor/core/nfl2k5_gillette_venue.py": "a2fc078b343140004d17875f06849d9484b9155f6d6d033380112f73f8a88ba4",
        "mod_editor/core/nfl2k5_hard_rock_model.py": "7effe8fbf43110f6ed54cfc9afd806d8eec2576beb3948498ffef3be3f7d9123",
        "mod_editor/core/nfl2k5_hard_rock_venue.py": "c94f5e0986ce307ace72f74272da8647bee54296964daa63679932ee66cc47ee",
        "mod_editor/core/nfl2k5_highmark_model.py": "f1acfbf79a888b6542b1d193390234dc6baddf73a12bd6caee528e299cfd0b02",
        "mod_editor/core/nfl2k5_highmark_venue.py": "caf65f301a9f0c1e97bbc76736fd88188c236b98a002157d5998d40392dce46f",
        "mod_editor/core/nfl2k5_lambeau_model.py": "3aad96173fbf2b9f5caf10eb80b7e7cc0b2a1b3552be33f1024cff8cb324e217",
        "mod_editor/core/nfl2k5_lambeau_venue.py": "6e66f5f4872438c13d3d77df0980e5b3b76c7851601b449a093d546482b39af8",
        "mod_editor/core/nfl2k5_levis_model.py": "3dd23633da15f61de03cd903d8522c4551f6259947ccfac40ace9138261e96b5",
        "mod_editor/core/nfl2k5_levis_venue.py": "6f6e2c5ce5d2d38a13e3a73c1f7e827829b921813671e155a7d8f1d26354ad87",
        "mod_editor/core/nfl2k5_lucas_oil_model.py": "049d676aa1c0bd32545089eea2b30380bd71c8652d1ac65e2a4ce26062ceabc3",
        "mod_editor/core/nfl2k5_lucas_oil_venue.py": "106be9ee3376742f2ca9caddf6467f5ccd88f74955010936666047e0c54e1bac",
        "mod_editor/core/nfl2k5_mercedes_benz_model.py": "823f3c7ef417f090b0f8b10d4f799bf5b92a06d5381ae84f5af9edc41ce64cf6",
        "mod_editor/core/nfl2k5_mercedes_benz_venue.py": "a35ced58f2c17e3eb0a088a79ddbcfbbd47a8d40b59d79af84a83051f39b2d21",
        "mod_editor/core/nfl2k5_metlife_crowd.py": "ff42efdd0aace6a5622119e9a265329a4865f7365d74c54d1d70a7989e3d1be9",
        "mod_editor/core/nfl2k5_metlife_model.py": "19db233bd7035e3da5382c2f73fc6870a457d85d531a8542965f560287e4c8ec",
        "mod_editor/core/nfl2k5_model_fan_art.py": "5d1ae475fc1be8d5d987a04d8906a3cb2c84cc1ba21fb3b5e7cf0f3b0abc805f",
        "mod_editor/core/nfl2k5_modern_metlife.py": "66ab7312df3d0e62881935a744cb9661c948b326302790063694dc44c5102fc2",
        "mod_editor/core/nfl2k5_modern_surfaces.py": "09885beed3b0341854fd9d9ab6be10d0ae1ef444bcf88cd43501a61700c89535",
        "mod_editor/core/nfl2k5_broadcast_greens.py": "1819a3085508cfc6493241ee87b6f53fed1a1b8ed6aaa64eaada77603eee7802",
        "mod_editor/core/nfl2k5_modern_venues_2026.py": "59572c748df5ac7317a47e543639a82764c90c2755452fe49f976c07ebc8f918",
        "mod_editor/core/nfl2k5_scne_builder.py": "28357fe693ded37f4f48808ad264d3378a6e923c5d27604b1b9a952020d404d7",
        "mod_editor/core/nfl2k5_sofi_crowd.py": "a3d8c12bf3da19bc35ab115c7e04220b5fd5e36e8ba272c91c9ac2b156c106dc",
        "mod_editor/core/nfl2k5_sofi_model.py": "22e0287a77065f87c7b1f6e02cf8ab4721e6fc8194cf9751ea9c8beafab53b23",
        "mod_editor/core/nfl2k5_sofi_venue.py": "754b26053df033fd0f8265490eab5c8c780bac266142cc41f5695a4113eadb9b",
        "mod_editor/core/nfl2k5_stadium_environment.py": "a7d447b2e8146b260aa113d08e8a8f36c118b7d6741ab58dc99ffb153b780e38",
        "mod_editor/core/nfl2k5_stadium_shadow.py": "ad5cea85c20ac80caa4c00bcb237e6701096254a9c5c3717e3fab3c05a39b87b",
        "mod_editor/core/nfl2k5_stadium_shared_art.py": "9d7e4ecad06d863a9cad8b3dd7c35422fd490f0690e351fe4217fd0149237e36",
        "mod_editor/core/nfl2k5_state_farm_model.py": "4d8fa0bbd4399dea02fc86fa37a4b8198ac3c7251738e1850d0f8657c70cf0fc",
        "mod_editor/core/nfl2k5_state_farm_venue.py": "05a3163dae06970f52263dda7994f798879843f915c5cba42b541584d26548c7",
        "mod_editor/core/nfl2k5_usbank_model.py": "dd3ea4f79880242f9489723b44d45602304fc52f216e6e57029351e2d7269d7c",
        "mod_editor/core/nfl2k5_usbank_venue.py": "388044c9675a4d76ac615772e6772b52f4107f3b93c76a9cc6f342e2a30901a0",
        "mod_editor/core/nfl2k5_modern_arrowhead.py": "0bd6686db5572940b95b0c75211a89ddfb1c8d30aeb278a5ccf6921fca524b17",
        "mod_editor/core/nfl2k5_modern_color.py": "07ba4a7667d28c989cb59d12da91e0e0e8189c68e8c1a971d39289ee0d03617e",
        "mod_editor/core/nfl2k5_bump_strength.py": "79f9264fbe0813db9be66f22e35f8944e35b92ae415132d819eda50920e41bb0",
        "mod_editor/core/nfl2k5_calendar_engine.py": "24dc9c152a79c81d75232b556f82ebc3ab6892a662c3d8071a4da85a6cd45644",
        "mod_editor/core/nfl2k5_calendar_engine_code.py": "9b43e835f1df76f85ecb13e7ef593d2eee884a1fa82fe41ea3d813186445ca22",
        "mod_editor/core/nfl2k5_later_schedule.py": "3bcf96d22a24338d02c7f930151d27c1d812612036a38fadfc0797f2a0e446ef",  # b780-season1
        "mod_editor/core/nfl2k5_camera.py": "c2b85ae199f5cd6b334b6b3dfa193caf782671488ce852eba8cb28fd50c34cfb",
        "mod_editor/core/nfl2k5_catch_slider.py": "b5bca296e1a76f078aeb4932e7078fe0b80aa2a7440461afae57f57c49cec5eb",
        "mod_editor/core/nfl2k5_cave_oracle.py": "8be24dd71d7503dba209061747bb74c439833970978a045a96f740cedafb940e",
        "mod_editor/core/nfl2k5_college_check.py": "f63ebec10d10a7e868f8f83d1c32001b8780b1edb3514ef60bf2f3de25556f86",
        "mod_editor/core/nfl2k5_compile_cache.py": "6e30bc377ab6b894b8d5b634cc2ed2426f143795d937a2ab423eece80876b40e",
        "mod_editor/core/nfl2k5_stage_cache.py": "4e78b766d57fc320d2448cd7b2ade0ff4ad08a37f45e74f41cbfe9868c6df72a",
        "mod_editor/core/nfl2k5_late_steps.py": "b2ac23b707cfd2173211f921aceec6cc98a7673ee52d959fd7e679475a56ac4c",
        "mod_editor/core/nfl2k5_coverage_slider.py": "e63025985e5e2a1f9e18fbc8f7375b16689f2b81bdb61766d86f8d8ee515fc0b",
        "mod_editor/core/nfl2k5_coverage_trail.py": "2307dfcfc5419eec9e5b1286cb056d577939028a7a14ff532bfc0a67a24fa902",
        "mod_editor/core/nfl2k5_coverage_trail_code.py": "3c2cfd81b9210f4843bf4eb548987794991161c7ccf5f21ab197d83ac8b0943f",
        "mod_editor/core/nfl2k5_coverage_hitch_code.py": "a7be9dcd4cb6c66222e92cb1f3b49f2d82342cad43507c716f074300c026681b",
        "mod_editor/core/nfl2k5_cpu_money_downs.py": "f4f6eedc9a2dfbd58cfcb0fb82cdc42f0a697d90f231b2ae6241976826018ac1",
        "mod_editor/core/nfl2k5_cpu_money_downs_code.py": "75006f464c59eb82522931b1d7763dcbedc69c726196eb4a11e4ce7424413199",
        "mod_editor/core/nfl2k5_cpu_third_down.py": "e4cf6e7a6cbedf651dff6b797018fdd23959cf2d2ed045482611c56a5aa76ee8",
        "mod_editor/core/nfl2k5_cpu_qb_reads.py": "d23312a9a21ac0ba3114b740be4a2ca315d0f9567b11d0f6a99891fc7f64e005",
        "mod_editor/core/nfl2k5_cpu_qb_reads_code.py": "a20b09e6bf4b98a02f481562717630c633bbf84d206921f2f9c7548707a6738c",
        "mod_editor/core/nfl2k5_db_ball_play.py": "1da99c1ded8ec24816fc6c188675d1f4429c651b29a4be291862eeb1b0f6205d",
        "mod_editor/core/nfl2k5_db_ball_play_code.py": "4e380523a17918720ad3c229f1a7d3ca5682dc12ebc70df63ef022b3449db3b6",
        "mod_editor/core/nfl2k5_dive_window.py": "d57c3c4f1ac961aa448504633c20ed900b1cd375fa1a3bd0f5fbaeb0e03fd220",
        "mod_editor/core/nfl2k5_dive_window_code.py": "9997f24066be72f40f7edc41278ef336240c572d7d1df180343a16863aa0d826",
        "mod_editor/core/nfl2k5_qb_accuracy.py": "155b1fd4b21567b39e7dcd136764657d33ce13fda7142af3e060d6c37ae05a64",
        "mod_editor/core/nfl2k5_qb_accuracy_code.py": "2e7c79ac4f1014580b784901fd78bd14d19d2e1fbced21c767f9c0bbca75c7b6",
        "mod_editor/core/nfl2k5_crib.py": "01f98c38f1dcf6a6175e017b68794fc16011b437763eb42d8d3810430760fb8c",
        "mod_editor/core/nfl2k5_crib_electronics_targets.py": "6d474769ee594d792d11f112fb3e39da8bd2ae8117bae92231956b4305112e2b",
        "mod_editor/core/nfl2k5_crib_geometry_writer.py": "d1cb53a2e801cfd14c469dc58cf8e433a8045e93e724ed502073a1cb2b8d0d78",
        "mod_editor/core/nfl2k5_crib_reclaim.py": "9acb8197fcf6449f3e09f5f04b90b84db89b963320ac9db25a3144f7c975b582",
        "mod_editor/core/nfl2k5_crib_scene_texture_writer.py": "4f72f59fab6f116c164a2acafb110829a46eb18dc5abcc5cd2c05978a0f0cdbd",
        "mod_editor/core/nfl2k5_crib_standalone_texture_writer.py": "95cab3bb2d666fa4f4dfddfb25816c443b17a51bb97abbe90d9532a5f117bae6",
        "mod_editor/core/nfl2k5_deep_zone.py": "59fb0d2b1f5be90d90692d7f143d00d8091ceac2d9ba1ee9bd40c0f9f626cbf7",
        "mod_editor/core/nfl2k5_deep_zone_code.py": "421d08aa91966fb43667cdcc44813ff8cd2d898b8c47191bfa9050930e9667cc",
        "mod_editor/core/nfl2k5_defensive_try.py": "230382d2e3b59076d1ae496a7585ac7505e2a2099b3ebb471a905759405b3f66",
        "mod_editor/core/nfl2k5_depth_chart_rows.py": "1254f317a88563888660f6ff125d1cee25904fdfb260832747fc73e22acdcd76",
        "mod_editor/core/nfl2k5_depth_chart_storage.py": "c401fdcae11af49b17245bf6b430f2c078ad33cc4f1452f18d648b88d8c3d52a",
        "mod_editor/core/nfl2k5_depth_locks.py": "e4be02224f8d575cbf49d6f593ee3ad37d8c46c0143b1da1f191620b4147a13b",
        "mod_editor/core/nfl2k5_depth_roles.py": "92a11e038973a1c421fe7f3162064bb62a9fd8cefd6bfb4bd9cc5765d3f3a19d",
        "mod_editor/core/nfl2k5_equipment_import_intent.py": "d1d5839e46be4dbc53f3709bc053830e4320fff1cc4a5f87a7391baf0355da68",
        "mod_editor/core/nfl2k5_equipment_import.py": "d061bc77992dcc1b12d11f3051de25024ac48574fc41ff24f45cab46ae79097f",
        "mod_editor/core/nfl2k5_equipment_lz.py": "2804d1828097e90fc5038ea7dbed0b081a84073e5018145628079fee032e1796",
        "mod_editor/core/nfl2k5_digit_art.py": "87f0e80eb9312be8ea3491e843a42bd94f4ba4ac94bc2aaace508c1dd90c2806",
        "mod_editor/core/nfl2k5_digit_texture.py": "9b31dfbaf0ab7d2cb3d7b0a534d9ca5cb8b58ceb0b941aababfc43001c80b20a",
        "mod_editor/core/nfl2k5_disc_identity.py": "ccfbd9a2209f4d2ce3f28ea85ac3e21577ac0816364a09c858648dc45772ef83",
        "mod_editor/core/nfl2k5_display_list_stability.py": "34649b364e65566cc798df8e0ad60410609f7178973358e95ee3691b2f6e6031",
        "mod_editor/core/nfl2k5_draft_ai.py": "dbad1bea26e6e6e911bc633c559e5e5de85553c378c4b8b3ddc50514b9ddc9d3",
        "mod_editor/core/nfl2k5_draft_class.py": "01c112faec0bc4f3c10142bc8e84ae1c23d156daa553f76fbb8b0f847c4d3307",  # b780 b1-draft: imported by throw_tuning (the draft fixes)
        "mod_editor/core/nfl2k5_dynamic_kickoff.py": "5ed5a2914bd857d734f285f68af3b2b4b41712939e9d8aa42cf88103b11f6b16",
        "mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py": "65965dcc61ca1ebe85b4532be99a6ae64e504bad13f0d438223c9e5193d6261e",
        "mod_editor/core/nfl2k5_edge_rename.py": "8d07169164719fff6121c36b07f90ac8af0d350ea39cb2dcaee83a3ab4e3fc0d",
        "mod_editor/core/nfl2k5_elbow_options.py": "cd6921f1d7b2942f81c1415fab45eb18f3c4487e3e0aac1fda3a9dbd82760a1f",
        "mod_editor/core/nfl2k5_espn25_scenarios.py": "6a6d2c000f0f78a4e1330186250e80c030751338e0b568d63bc12042bc4e8e79",
        "mod_editor/core/nfl2k5_modern_coaches.py": "6611224f1c7f4853826d7d1530e2debd0f1bb03647e775a1a7e77014716dab27",
        "mod_editor/core/nfl2k5_moment_coaches.py": "13dc10ed4283be7dee3092c0012d26bd77a47bff649edb688532f3e71c464405",
        "mod_editor/core/nfl2k5_moment_context.py": "53c004fe1e5e12edc23e624bb2a117322c663f7683cfaabe9a14bb01184249e5",
        "mod_editor/core/nfl2k5_espn25_more_moments.py": "4c7c0edd68cf1035d2187a3b87b2604c1eba2c8781ebf2e5661783371f7a4987",
        "mod_editor/core/nfl2k5_espn25_more_moments_code.py": "661c05f766df80e30c11f1975d0a3af797bf5a26ceadf0f0dc56a86e7b99fcdc",
        "mod_editor/core/nfl2k5_espn25_rosters.py": "c918fb073517e188734cd529820642686b74ce7bd4c5359e1657c2561c1feb82",
        "mod_editor/core/nfl2k5_extended_visual_catalog.py": "6576fc522bec39f163b851471ab9105db5080a5085681f3f27e626c6e50011f3",
        "mod_editor/core/nfl2k5_extended_visual_io.py": "928a8367c3faf4f37adeb9fa11164529457d79a9bb03fb0f0ecaa0082863975b",
        "mod_editor/core/nfl2k5_formation_play_writer.py": "746974969f0e1b64f5954c24c6fd3d22e9e647f295f58c4cec03d24a3c48bffd",
        "mod_editor/core/nfl2k5_franchise_2026.py": "20a58ac47e48d96d5cfe338e6ebe45d7a52bfe7f880dc6b1b6cff29940ca77e2",
        "mod_editor/core/nfl2k5_franchise_2026_code.py": "3aaa62bc4282a7605823b30d20936d388916d2f5c51a4a4774f85c0af67efcfa",
        "mod_editor/core/nfl2k5_franchise_autosave.py": "237af86d5e1adc6726d4e6d75152c07f2365d0ca54048a55335cbb275e361ca2",
        "mod_editor/core/nfl2k5_franchise_autosave_code.py": "bf06126a790642048aae92d57d3815d445560bc012ed02df5917648bcceec183",
        "mod_editor/core/nfl2k5_franchise_edit_player.py": "54e99267d7c0eaa7edbd55311271905271246b255392e27555f58df42313206e",
        "mod_editor/core/nfl2k5_franchise_practice.py": "941f16e83b5205c36bba517b6fd20f0079e435f8c50b6a52d2b119ee58025c84",
        "mod_editor/core/nfl2k5_franchise_save.py": "97a9eca8375c675d9442f8290c9e22c5de6404adcabc03ab2af5e4ca279dcc5e",
        "mod_editor/core/nfl2k5_gameplay_lever.py": "21fbc88ec891fed1798905f26932d812906c5ce62485bffc1e3b47c9aa9b31f3",
        "mod_editor/core/nfl2k5_guardian_cap.py": "10d04364c41bd7522f74109a3031df05a5cd9ef3ea80193daaf93a455943b5a8",
        "mod_editor/core/nfl2k5_guardian_overlay.py": "c84e20e32f60a0f955c6a5f6bc059ce4abeb5276b7e7e90ba845f8f658990461",
        "mod_editor/core/nfl2k5_guardian_overlay_code.py": "019075c8fa333bd5be8d240c86038a3ab89527af11921ddfd6935b06eab08cf6",
        "mod_editor/core/nfl2k5_guardian_resources.py": "ae273e73f488527655d6650b9651ce2c78420f5a19e9b3caa7024379ef96deb9",
        "mod_editor/core/nfl2k5_historic_rosters.py": "36b4c4810afa1b1c7622a07e2ebd162a42eac21a541fc093daceb689bea85e26",
        "mod_editor/core/nfl2k5_historic_styles.py": "3ef49ccca45b672ac4ae090612c8d517b5c57a62f41b21325ad69ec207c06ef6",
        "mod_editor/core/nfl2k5_uniform_slots.py": "6430c34ee1ff62489b049a83d379a420615f8ed1f490a8fa91541077f4f9d3a1",
        "mod_editor/core/nfl2k5_menu_icon_orientation.py": "c65452ffabcb8c234f1be76f313dd0274b88a1e047f2232d624190938af71dad",
        "mod_editor/core/nfl2k5_menu_icon_uf3.py": "63df869c5b997b67a6a39bbcd37d5638658f9b610cf0d3af69ab954c06797580",
        "mod_editor/core/nfl2k5_pants_hem_2026.py": "ae9e1b88f56788ae2e3ec819f535461aa6872047102de1a7d24e9243c596f22d",
        "mod_editor/core/nfl2k5_glyph_fixes_2026.py": "5b509cd0835f26814df5b798e556c763933dda6c8c60d5baca1f4c042a336ac6",
        "mod_editor/core/nfl2k5_nameplate_fixes_2026.py": "00b710b798240ff4041040237076c35fd1b350ff56cff98c178d83a8eaefb2c4",
        "mod_editor/core/nfl2k5_menu_chiefs_2026.py": "c60f4b3f79672c299fa19515ece7477de1d15b3bfcc38911e35590682f612f77",
        "mod_editor/core/nfl2k5_menu_helmet_w2026.py": "a01a8edc75729b354b56a32718c20e1059393b3fa6f69bbaa067c340b5480e71",
        "mod_editor/core/nfl2k5_historic_teams_quick_game.py": "ae5ec8f54426e7faebfec7506baad623ed5950b944146e8bcc7a5080a8614a38",
        "mod_editor/core/nfl2k5_historic_teams_quick_game_code.py": "de1f93902ea8d78c7484344a19118a7e2c23163ee6beac59e76a3d061b09b10c",
        "mod_editor/core/nfl2k5_historic_teams_quick_game_code_b778.py": "3476183ffa3faf91db310ea64fb095dc21437fd20cd77f28e4b0ae23985f5cb5",  # b780 modes2: frozen beta-78 .. v0.9 RC revision
        "mod_editor/core/nfl2k5_classic_teams.py": "c2cf55498ba87fbaf613737776c60cbcb546b3227effc9db43f7e523d797ce2a",
        "mod_editor/core/nfl2k5_classic_art.py": "7f5682d76b185c090e85b436d87127565b95cc0c19fab3c1d416274ba67eb155",
        "mod_editor/core/nfl2k5_classic_kit_art.py": "8095764ce78cf7f08dbed5244cdccb4a2090a4edaca6508c7f67b7d1ce84ded7",
        "mod_editor/core/nfl2k5_classic_face.py": "3e220a1b888036bf9d53b90e9e318b1033a60b66a6b39e4eab3a8061d41548b9",
        "mod_editor/core/nfl2k5_classic_field.py": "7d179fd7afe40dd0283bcdf12fb7426a35880abbf7aaef894da5a4877dc6ad37",
        "mod_editor/core/nfl2k5_front_schemes.py": "a03ff7d5636feb259c3cb9dddd4ac2c00875748f14525fb9024a7634e4894e91",
        "mod_editor/core/nfl2k5_hires_budget.py": "e36cffa4aa56b51a9549126a0fa7c04998a2771f9b5d2f78fdd158a41ed51ba6",
        "mod_editor/core/nfl2k5_hires_catalog.py": "4d1c67add6cfed68018d4341e6171b005a1568b60eebf199507afc39eba3ae1f",
        "mod_editor/core/nfl2k5_hires_evidence.py": "4309e402356c9266efb2ab498b99056412dd5613e61615db2b3ecadb11e943da",
        "mod_editor/core/nfl2k5_hires_layouts.py": "e9c5fde8390e6f0a5a35f91fcd7b2e39196a13cf0389be5a6cc6d035367710ce",
        "mod_editor/core/nfl2k5_hires_pack.py": "1f9aaa68e5d40ac5c5097e495771faa2d49536b030ae7f25b1911ac93f59b0fe",
        "mod_editor/core/nfl2k5_hires_texture.py": "cab5e3e72cfbf8eb3d4601ecd55782f6a0e78cfa2bb17440c61622348fb446c2",
        "mod_editor/core/nfl2k5_hud_layout.py": "9953e899093daf2517adc74d101a4160353377e36e273eba5fdec7f82bbb8da3",
        "mod_editor/core/nfl2k5_import_preflight.py": "e2abd1a89ae56ee44af112d153d5c87e4e9924deeee94086d32a15b4347b4e81",
        "mod_editor/core/nfl2k5_period_goalposts.py": "bbde38118d849361ea1a57b2fb64d00040c5b19d21d37e849d0616fbc5fa1967",
        "mod_editor/core/nfl2k5_k128.py": "778c6b1835fe22ba87972d81098d7bffb3ef927205bf56627370ab163af821b5",
        "mod_editor/core/nfl2k5_kick_laces.py": "a495864f35b60f335855b17f8a12ec304f78ecf3c363a597bb0e519e64790754",
        "mod_editor/core/nfl2k5_punter_holder.py": "1b2a19862b6996f8fc9b60f90f9d968d263ad3d5f96d12a8770d1c5af4341dfa",
        "mod_editor/core/nfl2k5_kick_rules.py": "885525ea94351521fc5e22c1c40c17ef3f374d665862e5920c4d9a644cd53be2",
        "mod_editor/core/nfl2k5_kickoff_blocking.py": "310ef53a004045f4daaedf8502100f60b050f0ae76a005eac0807b20e0090707",
        "mod_editor/core/nfl2k5_kickoff_returns.py": "d1f30bac8fd709f64be20e060027649a43fc04b82c7bd09b48082e8e66e5220f",
        "mod_editor/core/nfl2k5_letter_grades.py": "fddc1cff6490c4695dd9d9016521744dec2d077346a740508a682434cd0e9e8b",
        "mod_editor/core/nfl2k5_letter_grades_attributes.py": "0fb3e43e4bd366b542bea98770f75d20ed0a46642bf25f38e261971d44b3e28a",
        "mod_editor/core/nfl2k5_letter_grades_code.py": "b01bcdb0e8a0e8c6a41f606500afeffd41034f2615c776dda6a9b24be6548dbd",
        "mod_editor/core/nfl2k5_letter_grades_progress.py": "5088c0b6a545b95efae98f906b5c4c2e030774b22f87a35fd08a2c1c80b31a90",
        "mod_editor/core/nfl2k5_honors.py": "775745cb1de0c259a7edebdb7981e05d2ca46d2f7eaabf103fb63190a1d22abd",
        "mod_editor/core/nfl2k5_honors_code.py": "5f74c634876b93f5a6fb37073b742d2248f7118f6074651473459791caccef59",
        "mod_editor/core/nfl2k5_champions.py": "cc677f15b8704080071a034b65ff953e2b12df194b64ef550aa17943373fb8b7",
        "mod_editor/core/nfl2k5_champions_code.py": "d0b7c4b07d849a24fda938e120cf7c6d4f15f0b589ac20183ecde61fb7fa463a",
        "mod_editor/core/nfl2k5_champions_code_b779.py": "c9a7e5bffface03b6ad23a030c652ef4398f8ac2ed26c249b8e815c2056c4407",  # b780 n6: frozen beta-79 runtime
        "mod_editor/core/nfl2k5_champions_code_b780.py": "c4f68380fa68902511e4502340d6b0e55228e04e6756dd3fde1eaef40db8ae7d",
        "mod_editor/core/nfl2k5_hair_styles.py": "e0de5a96cd3c87264fb99d6e278b881fd784c0e6fb6604b118aef61377139414",
        "mod_editor/core/nfl2k5_play_art_routes.py": "b2e652809e1a030608fcd3811bce6346903b3af3f06b5e737250d091b98681cf",
        "mod_editor/core/nfl2k5_team_number_scale.py": "1be5d406dfa34e809488f9c5efbcbdc23e012c697c118fa7ac665c8a4cc49269",
        "mod_editor/core/nfl2k5_run_blocking.py": "96251a09e80032838fc0cf9fa8ca187063fc2d7a60c823b7b4a3daca41e54d7f",
        "mod_editor/core/nfl2k5_run_blocking_code.py": "622c8683badbb73ad0997e96d68a9d116317c5916d92a70be2758b05914e244b",
        "mod_editor/core/nfl2k5_pass_protection.py": "47927d1bec09e75e536093564d8874d9c236237840758750d0bd291cc58b0508",
        "mod_editor/core/nfl2k5_pass_protection_code.py": "a9d8e2bfb43cab4c95d2e5c909a47a5d84fbf3b927ce51f97da619728b49e8de",
        "mod_editor/core/nfl2k5_pass_rush_stats.py": "bf6db89e8e248bdda1cf7051932cb1a87699ef93be6d4f67d9d7c6b8ed139e37",
        "mod_editor/core/nfl2k5_pass_rush_stats_b779.py": "aa5d0ca54ff78cce5e95e1cecd3c1848484792218465602afc6b91f2064f8281",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_pass_rush_stats_b780.py": "ef2efea90ac371bc1fbe89fd52e897f1b767b580e00513dd8a8ec3d922bcb2d3",
        "mod_editor/core/nfl2k5_pass_rush_stats_code.py": "7ae1f6b16903831cc76db878ac0447386e99e40b0df94c7c93c45eee0f86adbb",
        "mod_editor/core/nfl2k5_pass_rush_stats_code_b779.py": "1aaa9727867ef483c1bc53696ab98efefe1440381cdb1771cba1d05f31413c9d",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_pass_rush_stats_code_b780.py": "1f15e31239b14696c9167851dea4f907b720c07c5d0dce3ca3b0ce4329a0d5fc",
        "mod_editor/core/nfl2k5_cpu_passer_iq.py": "b20345c8645b637e4fa619d811e50786bca501259ba16a6fa7a5b7c48b195b27",  # b780 a-passer
        "mod_editor/core/nfl2k5_cpu_passer_iq_code.py": "8f9e07127306df30acb5e5f65cb2c299da1cc8b0fb06e29f1459e3b7d9d209bc",  # b780 a-passer
        "mod_editor/core/nfl2k5_cpu_clock2.py": "335e32d1e0358c602b6c7bab378cbbd0ebdebc7f93b779892f2b4b026b9a16ee",  # b780 b-clock
        "mod_editor/core/nfl2k5_backfield_cards.py": "6eba11828f0bc8f3681e28c1d4ca3113173766ea4e006eb81451f11413abf4a5",
        "mod_editor/core/nfl2k5_offset_toss.py": "eda42210555d6925b1a9ee85d3e98016b9be5e9592cd97a580eda4be6904985f",
        "mod_editor/core/nfl2k5_cpu_clock2_code.py": "5e738afcc2f8091b47f89e0ec72bce416e5c56f5986e9eaf070ad3ffbd16fd0f",  # b780 b-clock
        "mod_editor/core/nfl2k5_protection_calls.py": "3b22fb81f3d641e51fa849156910d39190d4a34a8f1ac36297c4e8c849fa5730",  # b780 p1-slide
        "mod_editor/core/nfl2k5_protection_calls_code.py": "2b7d47b62cca789dea4a8da518eeeff36f337b267e1dd2f97eefcd1a6d8509b1",  # b780 p1-slide
        "mod_editor/core/nfl2k5_lineman_rating.py": "e1c08c86e0a31c58fd86d5a155c56ad200cf5ef237771c95b39bfe29215261c1",
        "mod_editor/core/nfl2k5_match_coverage.py": "d9c1a93508a25a17d389b1dfa628ab8d0ac2da25d99bcc64a347b98f4447cfa2",
        "mod_editor/core/nfl2k5_model_project.py": "04371be3e1e86a9a6b3d2499dc0db203d6d5d9241c104c78879a2a414aa05488",
        "mod_editor/core/nfl2k5_model_skeleton.py": "feaff8bb682d51d6b62c23cb955ccaf5b9a149f9e2948d7ee4f219200cd7f0ee",
        "mod_editor/core/nfl2k5_models.py": "8b2e86bd0e6f2ba8d192bcdb452bc8e45fc38a4a0af8a95350a0e2f816bc6176",
        "mod_editor/core/nfl2k5_modern_helmets.py": "61f3c09f70d54f5a926963f310d87382a53b003a6b99a807b9dd1944ae67ff08",
        "mod_editor/core/nfl2k5_modern_naming.py": "517f44b88799817d5c036605cbd3cf1a4baa06cbfa50ed4ee706c0a38b80701f",
        "mod_editor/core/nfl2k5_modern_positions.py": "f2bbb8ca3dcc78c6a16e1f70b3cb4858e95383daf817333dc2d37ac3d624c8e5",
        "mod_editor/core/nfl2k5_momentum.py": "2746d12c7950c96cd0400bb59c33a413294b5ac3d4563874727cc32378981cce",
        "mod_editor/core/nfl2k5_momentum_code.py": "a56830bdfaf46ac987b0699f926745c177be183754baa422bbe192fc9e305b08",
        "mod_editor/core/nfl2k5_music_archive.py": "080413560947097ca76c441e8e92007c643f635b86f1206deced2f62b3278445",
        "mod_editor/core/nfl2k5_music_banks.py": "cfef1645768dc4cff160f997325389b70f7f226d4f2ba0f885d95a2465f59b59",
        "mod_editor/core/nfl2k5_music_conform.py": "ce8326cdac35fd693b6bb8066591b7de0c9cec1bb79e14eab4492179c5ffe89f",
        "mod_editor/core/nfl2k5_music_build.py": "af411acb0bc3ca3a3a168cbf16b235c476fe44d36b2516a2afffab94339b78bc",
        "mod_editor/core/nfl2k5_music_catalog.py": "e54417c33f0ff7c7dfa19dbad57f61f578b3e819d17ff7e2b3693b8ecee61e48",
        "mod_editor/core/nfl2k5_helmet_finish.py": "667f06ddbba78b7ee3416265ab6f67ab43edf1444569b1e407e7b3c6d92b1f3d",
        "mod_editor/core/nfl2k5_jukebox_list.py": "3752a85731a7190cda9e429ed26a6c8810be35b45b31db1710e31e82f4408eb7",
        "mod_editor/core/nfl2k5_music_collections.py": "75e9145cc396c633a5f99a07f0d8a4c9bdcf87dd6e29c6726e98a792dd9752da",
        "mod_editor/core/nfl2k5_music_metadata.py": "e3ee47bc222794312b1b0119a96c046edf6f53a071db00ff0208f106abdedf48",
        "mod_editor/core/nfl2k5_music_playlist.py": "c3436b59502a094fac88b32ad0fe61f0164c86f0553b21ba1d344e931d0cbccf",
        "mod_editor/core/nfl2k5_music_playlist_code.py": "565d8ad8b8e6435190dda20a137e7b8128c5716d72935ab30be5189efab48546",
        "mod_editor/core/nfl2k5_music_policy.py": "f1f21c182fa9f86844c6dcc0019f0463ef841799fd24a717131b4d762c8a99ec",
        "mod_editor/core/nfl2k5_music_storage.py": "a934b271e63c06da003936ddcca4175474e15b7a2ee00f7d09ddf0cb1daebbfc",
        "mod_editor/core/nfl2k5_my_career.py": "586de7e35df4da30e07fc013a93fae38063fc70628ded966ede0719e446651a8",
        "mod_editor/core/nfl2k5_my_career_advisory.py": "893e01173254d112593d5c8ad3cd3aaad5dd9edb3f6482357f2ad1bc534c21ac",
        "mod_editor/core/nfl2k5_my_career_code.py": "0ce8c85ca30bbc188356e612ca1d95e01e94ceb7dfe2cabcea222672f07e3c2b",
        "mod_editor/core/nfl2k5_my_career_events.py": "228a0b59d43b9b9c52e10ac93cc72072e772e694cc864c8e2e037c5d7c772460",
        "mod_editor/core/nfl2k5_my_career_mode.py": "6bc271bc88b0d59bcd459bfcc4b149439ef02c0ab75448ec32620f1d4bc10411",
        "mod_editor/core/nfl2k5_rookie_faces.py": "3b7461fe711d72ada7c2009f04e2736783157612d03c351843fadbce9576b3f9",  # b780-int (gen1mc): MyCareer's draft-signing context reads its draft-number byte
        "mod_editor/core/nfl2k5_my_career_mode_code.py": "dbf9330b042795f057e5dfd92df680f6c004a97eae9f5218a3cd66cd13b5d489",
        "mod_editor/core/nfl2k5_my_career_home.py": "852747c8b6ae3b94bc61a3f0d8b7a3060bde155901667e71021a8346c291a0ab",
        "mod_editor/core/nfl2k5_my_career_mode_code_b779.py": "9774a72e254da1609e82a53d2d5b74701e1d2acec484b6588256fc9b256c0355",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_my_career_mode_code_b780.py": "e29173a94e1dd4cea73149f9f0ebfe945c7fb6ebef386e2f3ddf89ec77932ee6",
        "mod_editor/core/nfl2k5_my_career_home_code.py": "c23c0177432f74ec2d8c51b99400bd47c9160fc6e563b8aca05eebd12d7ac485",
        "mod_editor/core/nfl2k5_my_career_progression.py": "77ee4d665dccc60862e162195e85d3cb3d39e6ad04ce9eee9cc87a99754d9cf5",
        "mod_editor/core/nfl2k5_my_career_save.py": "2f8b4c9e7fe6114539f20f069ae0c428bac63d2004b6f620909aed5b6f412361",
        "mod_editor/core/nfl2k5_overtime.py": "8882534bf80e5acc734c383367306d837c67dca0ec950ac93c019979fa64e406",
        "mod_editor/core/nfl2k5_p8_texture_writer.py": "4a519adf657eeb5ecbf8be6a8cba99411cbd0e5843bf55d7bd7e142723498485",
        "mod_editor/core/nfl2k5_penalties.py": "f74e61d6404d30b54811442b1bbb58fa6d233d55f57856043a6cc6e8730c1ed8",
        "mod_editor/core/nfl2k5_play_codec.py": "3f01db64ac7230102fb8c37c3baa2ad60932803a576a8f7404dc3c0d347b268e",
        "mod_editor/core/nfl2k5_presentation_standalone.py": "c420f31fca02c60c0176eb36f571794d91e9de0ce57ac2cc009a9aa756701ca6",
        "mod_editor/core/nfl2k5_play_intents.py": "4d4f08fdeece4f45e8b23aaa5cccda971463b8cc8cfd10e52e8fcaa03508f64d",
        "mod_editor/core/nfl2k5_play_library.py": "f6e8113f4ecdcd8ab2cd1da8266bbf5dcddd84ec73f6af67316af21c1a94c0a9",
        "mod_editor/core/nfl2k5_offense_concepts.py": "ea86417d940806a40839982c92b7485e5e35ac0a89ec4eb02a3e5cf13e7b055a",
        "mod_editor/core/nfl2k5_offense_modern.py": "855c2564f5eb58b8167e595a8bcd85b5dbbd6a9b1727e48029bbe94c80ac647c",
        "mod_editor/core/nfl2k5_complete_offense.py": "ef4853d2ae382574268cd925120af55ee89d1e780ae1f416473832cfdcf9db07",
        "mod_editor/core/nfl2k5_playbook_lint.py": "7c1c09bee0f94eba9b07ad26ee19913bae09be2b1ac80172fa4bc38169e67af3",
        "mod_editor/core/nfl2k5_play_scoring.py": "8776325303e695d34543c462a276747dfa7d1a74ec14245027c53965d952bdfa",
        "mod_editor/core/nfl2k5_screen_authored_pins.py": "e7e31ff271875cd322ba6b9c143a344000f7c4fde584ccdd9fdf266faca7325e",
        "mod_editor/core/nfl2k5_playbook_inspector.py": "296b94fe2565486665c6e820658fd149d22b3ddaeec42cc87b606325f5f7167f",
        "mod_editor/core/nfl2k5_playbook_pack.py": "1eccc42943c9c4653258373a853bf7a1138957bdbfece911ea8321921cac6d27",
        "mod_editor/core/nfl2k5_coach_ai.py": "bf3b35376abbf92567a10c62e6bc46a0a4375fa9acf5e3da6dd4de0f1a69b93f",
        "mod_editor/core/nfl2k5_coach_ai_code.py": "2b284172bc2cae180eea7ef3ae11ce69fff3363399bc305a4504cef4fbf7cfdc",
        "mod_editor/core/nfl2k5_coach_staff.py": "4ddd9bf4541b5a68276168d8eae634ad493c189e7eb9069224696172a5d2f15a",
        "mod_editor/core/nfl2k5_vip.py": "7760c4c3c07a00b081db7f742c314fb23ba02d97568ec39e1106f0d8e9af3b51",
        "mod_editor/core/nfl2k5_coach_diversity.py": "a56f23767967090df58f4da16ebc9d5d66d713f12628da5da241a1f36104aa53",
        "mod_editor/core/nfl2k5_defense_calls.py": "24101801896efc6667c7be3b787fa1fe9044a0679dda85a5f1d72ae6b56e9302",
        "mod_editor/core/nfl2k5_defense_rings.py": "07f33943226aa848a299c47a9284ece043d768787b5234aadb82fc6c4394ce0d",
        "mod_editor/core/nfl2k5_playbook_pair.py": "4965a39ce7e651b05896d76567c1cf9662ef8ef8f9ced30d0c41e3f0b930888d",
        "mod_editor/core/nfl2k5_playbook_pair_code.py": "78e97a0ce01e49af9a22c59d540ea8121097ae26c31f6650983baa7a945969ae",
        "mod_editor/core/nfl2k5_playbook_route_writer.py": "87ac9ab729e15c665774223c406a248931b77a05ca2fa258b04e1f0cd06674c5",
        "mod_editor/core/nfl2k5_player_star.py": "6907c77e277b88dbbfc068370a62bdcf3be96ec0f4c776b57ac72c9e34778d03",
        "mod_editor/core/nfl2k5_player_tags.py": "19f01e1be1a41ebefadbd1801aba0d83da8954d7a9f19d5fa8d43984c64df45b",
        "mod_editor/core/nfl2k5_playoff_picture.py": "69bc099bd9a75d9132cc2a38723c0c6803a676f53828377bd9161dbfbee9fcfb",
        "mod_editor/core/nfl2k5_playoffs14.py": "d8c490d6d37d118355db80de95c924db52f03ba897b4fbd85432d1840a14051d",
        "mod_editor/core/nfl2k5_lineup_iterator.py": "b8b0c21ca736d411fb1288a6f4cddd5c84929b1c57962c455756e51f1eae7c0c",
        "mod_editor/core/nfl2k5_disc_extents.py": "2a1c1fe06a67139bcac469fd2cbc3cced1f523bac96b226094a296793bce3625",
        "mod_editor/core/nfl2k5_position_pools.py": "78bd3ec83675d8f9e1f3aa307621ab2367157c3855b6bdb3924c640ce9fd7bd0",
        "mod_editor/core/nfl2k5_bump_texture_writer.py": "a6044fe22a734e44f9e4e997e7f8032806efdf0aea28bae12ca525768755efb9",
        "mod_editor/core/nfl2k5_era_kits.py": "a4110a2f05a6f02b6bbc6e443b67ccc7e5cdfcd11c6634ea8c5cad79dcce832a",
        "mod_editor/core/nfl2k5_moment_kits.py": "b57a3ba64cebe7ec5bd6be8741dff8480bc2154318f036fb6e445750afcbcf96",
        "mod_editor/core/nfl2k5_project_check.py": "c1ed769e2ef9cfd639fc0329d50bb7ea53483d82e49c3acaf4262cac997c69c1",
        "mod_editor/core/nfl2k5_stadium_dry_run.py": "2e5ceddd5a0b7236ba6185a3e4f0a91352ff3598677cc63430de02623f913087",
        "mod_editor/core/nfl2k5_edit_survival.py": "3fe60b03fa633bd967c529a6e25141cc1dfaadbf15203ddc2755055a43eed3ad",
        "mod_editor/core/nfl2k5_practice_field_model.py": "3b4ebdf0e9cfda0ea832e5544c50bd249faeb01a4ed9cf00860f0b773491772e",
        "mod_editor/core/nfl2k5_moment_scans.py": "99445768a0d0ff24576aab37c5cae3d9ffcb2816034f447cd93d3092d18c616c",
        "mod_editor/core/nfl2k5_unc_bowl_uniforms.py": "639af055c4943c2578955885f4ccc9a7d65f0bd4c632487f56934bdcb1968e1c",
        "mod_editor/core/nfl2k5_nyg_numbers.py": "812f042c6293db1e66567d940228af53acf0955ab9eeec0ff936f64bc243587b",
        "mod_editor/core/nfl2k5_kit_fixes_2026.py": "6abf1c9f59db063646c4c6ecb651f26ae314ec1e959d0b18d30d3e8a707b39be",
        "mod_editor/core/nfl2k5_kit_rule_emblem.py": "5950b7fabb434f2aeaa59c7495db380593c600a1aa0d2c89af319a2903f268c8",
        "mod_editor/core/nfl2k5_kit_rule_fill.py": "cc53076d5a2f8015bf0503ba39b995226eac848a95afbc334a523827b40ffe5a",
        "mod_editor/core/nfl2k5_kit_rule_recolour.py": "c2209ac28148ca3eaee4104163d98b35bdc365d8917dd92e5c987f4a000a3913",
        "mod_editor/core/nfl2k5_relief_2026.py": "9ff0d3c8de77521365869dc24fe3934ae235a00b61da510b83c5a79188260bda",
        "mod_editor/core/nfl2k5_position_row.py": "0df78f0d7e3af61be8738afe5373925f48ef8a309a35bfcb31ab62008b6be85b",
        "mod_editor/core/nfl2k5_practice_reserves.py": "787e84ba5d4e1316e3bef58a82305366bf8e3d5f084cb0fe242fb68f77ecbbb6",
        "mod_editor/core/nfl2k5_practice_squad.py": "2631acdf806d7859f2ac40c0efc71b6315c647cfc5949ab568653ccbf5265ebe",
        "mod_editor/core/nfl2k5_practice_squad_runtime.py": "f010e75098d57ef59fc2ea88927b44402c976fd65de23a82422381d95fc3d900",
        "mod_editor/core/nfl2k5_practice_squad_screen.py": "165de73201100b6d64fe7cb75e041db9205fd97ccabb81528924e23160f9137c",
        "mod_editor/core/nfl2k5_practice_squad_screen_code.py": "d649e11edae0627de6e17aed0c4c60abea6104fb49fc904135276abef1e23b0e",
        "mod_editor/core/nfl2k5_preseason.py": "5e18c2bba83005798237cc3c85b0e10ee9f7dd8f4e179f52a430f46ed02c951b",
        "mod_editor/core/nfl2k5_probowl_order.py": "6e61b983f57f7e01695c7626b51854aea2242e1c7879049f8bb3a85a44b3cf9f",
        "mod_editor/core/nfl2k5_roster_fill_composition.py": "96547bdc1c66889f68f44deb147bd5f6095ee169d343d53aaa4f532d12ee53e8",
        "mod_editor/core/nfl2k5_franchise_economy.py": "db9d6a995233af83a516b805201125649525c02ca01f5df629f7223c0e84a970",
        "mod_editor/core/nfl2k5_franchise_economy_code.py": "9a7b580e27009b2cdb3b01db9cda210e40214e5d911e80ce7feea31ce4dd61b2",
        "mod_editor/core/nfl2k5_progression.py": "5ff9ab5b8b5a9b38e6acba0526464838abee667c957596368673f26ff88eaf50",
        "mod_editor/core/nfl2k5_prospect_names.py": "6f48b67a3b00b72b8bc51ca35527037ceca27c4137b9bb0e1d4542f27c39e7ac",
        "mod_editor/core/nfl2k5_qb_spy_runtime.py": "094e1ed86847a0b78e9ead41b44aea476f6f2f313ff6c986b1db722940553a2c",
        "mod_editor/core/nfl2k5_qb_spy_runtime_code.py": "759ee92ee3bac1d79d80ac6d6ae539ea6f0e3cef658dc945548a8c7db35c468f",
        "mod_editor/core/nfl2k5_rdata_sites.py": "cb422ad49c38a233a8d0e855beae0a9748b1dfef809472bdae84c459865762af",
        "mod_editor/core/nfl2k5_read_option_runtime.py": "f4b3c0126f270dc6ed4aae33d75ab0d6ab25dbe389d803002045cede1f7363dd",
        "mod_editor/core/nfl2k5_read_option_runtime_code.py": "2f58745ddc7ad4cf28adf3223d3a85661ca79d0252a7bb7d27a7a19e90bcc69a",
        "mod_editor/core/nfl2k5_resource_growth.py": "d33b9b3a6571852e13297050efd5364ab411f10efbaee32b6b087f01e41725fa",
        "mod_editor/core/nfl2k5_returner_fix.py": "9d60b36b199d55c3e49bb402b6c147dc478e83396554ca7874c0756d957f0eae",
        "mod_editor/core/nfl2k5_roster_ages.py": "cac19da10b8c93c3d1f0bb1b18a03abf95c5b7d5644299080ac3216560b9cc1a",
        "mod_editor/core/nfl2k5_roster_arena.py": "b0e4e1aa7b55eb1070b59bb145c6c92df4d3ab512f43fe6919482aa0df29b589",
        "mod_editor/core/nfl2k5_roster_arena_code.py": "ff38a3ca7cc5d59e28c0807ef70c552ff08307a4870a75d5a4b1761021fd77da",
        "mod_editor/core/nfl2k5_roster_arena_code_b78.py": "d09e15c483d8cf67ea33716929efe4712d8e75a21b7bb99670c9944efa5ff1fc",
        "mod_editor/core/nfl2k5_roster_arena_growth.py": "4a10b2d35fce686360b1a50481eead0343fa53aa03ae149e40be2ee5040c77c6",
        "mod_editor/core/nfl2k5_roster_arena_image.py": "bc438e13c6aed320ee3cbc45682210f7db36ab657d921dd2c79d6bb603ed9814",
        "mod_editor/core/nfl2k5_draft_picks.py": "3a2d018fa44df1100b512b01db97b2306ddc5d9ac585a596569b9a525268bdd5",
        "mod_editor/core/nfl2k5_hback.py": "7d82d304cfb2f39d4a435d522e9b536974a40ba7cb6b7a1ede57a2c1a7efb94d",
        "mod_editor/core/nfl2k5_roster_refresh.py": "4a33bc3f3dbb577facf675cdfc77e965a38e43ae1c5828504a5ab80ed87f5276",
        "mod_editor/core/nfl2k5_third_down_back.py": "316d3681d1b9952fa6851c4c31b091cb36f026b8b4ed572ab9735cba3b9befbd",
        "mod_editor/core/nfl2k5_equipment_fit.py": "245cc3ff765426fdad097475b5f181b1a6fed023528f950b362ff4a4c037ee11",
        "mod_editor/core/nfl2k5_created_appearance.py": "39ba94915df17b5cf869b005f6a772328cd59c69154a538665770db9049a30aa",
        "mod_editor/core/nfl2k5_team_ratings.py": "e05796dc1523a76c74fd074b576b4aa0ad18c378e16237328ca2970afe2aafd0",
        "mod_editor/core/nfl2k5_spare_capacity.py": "537a21876bc58ff3450dbc76adb965f616e0a40f19abff56ff8233b4b41825af",
        "mod_editor/core/nfl2k5_free_agents.py": "371487df33405965c0e0d926a36a49f2a516710e32280f4a2fc402e15edae0e1",
        "mod_editor/core/nfl2k5_roster_appearance_transfer.py": "b8264599eaa0ccbfac1412d4f9d96af796b1d00eb4abb2dd68d6ba95f9480704",
        "mod_editor/core/nfl2k5_roster_records.py": "07dcaba1d9ea617451f57b539e8ceaf9ff888fcbe867a25bb16af58df971530d",
        "mod_editor/core/nfl2k5_qb_throw_power.py": "f33b5bb5e7d4494c37b73ac5b373e3781103bc229d794b03769e4ca3226e8190",
        "mod_editor/core/nfl2k5_roster_snapshot.py": "c6832cc65d54213e03f7100080b99311f89ccdfd7502d91c1425df2ce4a14496",
        "mod_editor/core/nfl2k5_roster_save_to_disc.py": "53bfc70379662c2465ec6bd1bc896331b0429856cba54adcb055143a8099eaa2",
        "mod_editor/core/nfl2k5_created_history.py": "e8ee0b2754030e78383f6e97e3954c5437007c37e0d4424b8398987f789a3298",
        "mod_editor/core/nfl2k5_franchise_history.py": "72b4004d4ee11cf37ae461d040f9d3f9dc6a76a55fe96a6e4a8de45e1749ffab",
        "mod_editor/core/nfl2k5_career_stats.py": "d511269dfc1e4d4519045dec73bfc5fc1cae9b6b3c965f9de27e0f9a511db003",
        "mod_editor/core/nfl2k5_official_marks.py": "9f0e67322ba4b266693d0805d8cc80ed668b6b91ac90b301627a90b2cc2a90a2",
        "mod_editor/core/nfl2k5_college_refs.py": "2f49e35ed8904f376d7c4edc2d590d1bd48d593803f22ea7bc3399b2980fcfb7",
        "mod_editor/core/nfl2k5_resource_load_guard.py": "b679bb7dea16b1ea9bcc04b599760012d350acffb6ebd5a37ebfe857d726c9dc",
        "mod_editor/core/nfl2k5_rb_rename.py": "97ea6e6fe04cce65c48889c02a0337352f11563ea579cf996f93dc7a83d86166",
        "mod_editor/core/nfl2k5_trophy_room.py": "568a4d3291f3b5378f1785531f04873f420c2a7cdb73a5338b3af91787d7795a",
        "mod_editor/core/nfl2k5_loader_wakeup.py": "5472678b2d69adf05cafde4df80ae24fbba5d67397367f4195ec241e099aad6a",
        "mod_editor/core/nfl2k5_formation_art_spacing.py": "288fa57184b01a1980d706e66d099b8c7e95c77753d1c2d93d05b061f9571e99",
        "mod_editor/core/nfl2k5_force_out.py": "9498bc3bc5ecb8dc7bc40ddb0a821b1402b9162efb167a1d020a4fb9dc9ed574",
        "mod_editor/core/nfl2k5_star_retention.py": "f94dc1bbf8ec74dd3f41507575e4ffe772fce7880340b5c56fc926c400f10bd4",  # b778-fa1
        "mod_editor/core/nfl2k5_practice_injuries.py": "8b411bcd88201f1155319b140c7c6a9555e9bcf8751921c7264dd28f8955c518",  # b778-pi1
        "mod_editor/core/nfl2k5_ball_carrier_ai.py": "ddcb45a9a6cbea475fd44b0b040ba5bc9262f9732ff33747b0498cbe4f10ebd5",  # b778-ai5
        "mod_editor/core/nfl2k5_runner_vision.py": "f783174fb1c30ab04c6420432269b1457c270846ac375bcfb5c11fcb2da4f18d",  # b780 cv2-runner
        "mod_editor/core/nfl2k5_return_coverage.py": "3be0439c2f122ea0c7a5b53f50b89b0b31c8455ce13baa9ce8728ba9d2470db0",  # b778-kr1
        "mod_editor/core/nfl2k5_catch_snap_limit.py": "949c360348a42ef86f14ea338a7fe5493ad3061deeccd7068febff351cee711b",  # b780-cv4
        "mod_editor/core/nfl2k5_speed_threshold.py": "73f076c6af05daebe5f54a661fc5cb4fc2daf4bdbc627e797a42851872f1b08b",  # b780-cv5
        "mod_editor/core/nfl2k5_speed_threshold_code.py": "7578a910fadc5852901edaeca84d983f1a20e2e90ab227f00a678a08554d3e90",  # b780-cv5
        "mod_editor/core/nfl2k5_star_career.py": "9190271ff9fe7a641a0eee544876b92e7f756950ccb9a498727245d5622d7616",  # b778-st2
        "mod_editor/core/nfl2k5_star_career_code.py": "47b34490a21113803ba97a985378dcec237c39d53fed8fd6e9f498b82ec39098",  # b778-st2
        "mod_editor/core/nfl2k5_sportscenter_lineup.py": "d7901a39e3d80149441eb2b88ce71d49b5cdf6a47a27397ae3947d40f7c29023",  # b778-sc2
        "mod_editor/core/nfl2k5_draft_clock.py": "306e873a85e3c2aaf63815b424faa092a454a15cfd7a6fd334947686262cf4c6",  # b778-dr1
        "mod_editor/core/nfl2k5_weekly_progression.py": "7a5591e33c51891dae37cf5332fb3d6c46983285feaaaa8eade3e93ccafb61fb",  # b778-pg1
        "mod_editor/core/nfl2k5_player_progress_screen.py": "72730dea7dc942cc301fe89b05717913885897a484ed05f9e5a67e63c40fbbad",  # b778-pg2
        "mod_editor/core/nfl2k5_player_progression.py": "83b48e765dbce3139edfe7c2cf7b16d84d81d9cea4b60956bf455e85ef1998c2",  # b778-pg2
        "mod_editor/core/nfl2k5_franchise_extension.py": "f7ec35994cbbd7f48015a4e478167796db88788d77370fb46ae465e800c9663a",  # b780 j23
        "mod_editor/core/nfl2k5_franchise_footer.py": "b54b07f6c30a9a581820cdae216096fd6ddc41b0b556a51f1cd52bdb3e4f7b3a",  # b780 j23
        "mod_editor/core/nfl2k5_player_progress_screen_b779.py": "176720be40abf0887b496a4b056581c2cc65d31e93c58821137692c50cc2197f",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_franchise_footer_code.py": "af47806e13bb5e64eb3d6bc2feee0cc1369304f060f32f24c12b655c19a8c787",  # b780 j23
        "mod_editor/core/nfl2k5_history_screen.py": "c913c8360f97220e651171ee2c4f2c9bea6172bf9e0ffe633b483ae97234a9ad",  # b780-int: j4, now reserved by the first space pass (imported by throw_tuning)
        "mod_editor/core/nfl2k5_history_screen_code.py": "f0832a12bad7ced75dc5128a079949063dccb44b51665ad30637ecdfab8320d1",  # b780-int: its generated runtime
        "mod_editor/core/nfl2k5_history_screen_code_b780.py": "fb6dc3c7a66c1d7b60887780b3ffeeb8240086d4267af50446a6eb49fba4aa0f",
        "mod_editor/core/nfl2k5_history.py": "31629561cefcd12f0badcc3c85201f110c7c8924c7d3267b500eb4ff0421534f",  # b780 j23
        "mod_editor/core/nfl2k5_hof_rules.py": "6d9f044659f19a8c6af2502963a98322716713235fe3544ebe703a50b5921ce5",  # b780-int: j6's Hall of Fame rule, imported by the j23 history capture and footer format
        "mod_editor/core/nfl2k5_champions_history.py": "276ac2e36390dd3fb77af6a03481197308ba0a650d29af249d21faf4c47b4d53",  # b780-int: the champions history the j23 footer format and champions owner now import
        "mod_editor/core/nfl2k5_history_code.py": "7677da0a95a58b89dd5e5b46c6bd74f8d69fd11b73678daa74c4d55d7464c0a5",  # b780 j23
        "mod_editor/core/nfl2k5_contract_college_guard.py": "4bf8deeb95c3718380e8dc248ec2a2f0c81116f304d1a93723e277cc4bd32fe6",  # b778-cr1
        "mod_editor/core/nfl2k5_coach_career_fix.py": "7dea3f42075289b257c8b81e9591d35d6d19530d450ecb5469764925e6bd90ba",  # b780 c1 (wired at b780-int)
        "mod_editor/core/nfl2k5_history_pool.py": "2ab343c67a32c1bb69162defbb63c47bdc8d53adc5372bd17b5c3ef5eb072d8f",  # b780 hist1
        "mod_editor/core/nfl2k5_history_pool_code.py": "a4b2a9e08453619b58e3fec5ec9fb0f9bc0446bb224ef5cc057aefaa06d02eab",  # b780 hist1: its generated runtime
        "mod_editor/core/nfl2k5_load_user_team_guard.py": "70b3e0d9196a55d093870651173d83e305545f15118acd6224a9fb9f02ca7e86",  # b780 mc1
        "mod_editor/core/nfl2k5_save_list_type_guard.py": "64fcd510de0aa6b3595bfeb94e5f1555e96fb723595cc9d0390f9bf969368f40",  # b780 mc1
        "mod_editor/core/nfl2k5_show_block_guard.py": "ecdd50d675c1257780b91cf38d98f41cea62973b4bb060aacfaf21aede68ad40",  # b81 ot-crash
        "mod_editor/core/nfl2k5_edition_save_notes.py": "d321ef80273c081bdfc4871c11fa52d3733a604f3b7968149be9b4ab84268d05",  # beta 81 review M1
        "mod_editor/core/nfl2k5_sim_cb_tackles_b779.py": "09d6272b93b5e356cbc8b1147b6bac8c5184fcfbc37f4aee8729df723473eedd",  # b780-int: frozen beta-79 tail for the previous state
        "mod_editor/core/nfl2k5_sim_cb_tackles.py": "0b5655021e33a2c28bff7523399321f588aa4f925cf84823b9603c474c94f7a7",  # b778-cb1
        "mod_editor/core/nfl2k5_sim_rb_injuries.py": "777a337e2ba22559c0b77ae5bc22b3df94a1392da07217a76d7a3a02063ebed0",  # b779-sim2
        "mod_editor/core/nfl2k5_sim_rb_injuries_b779.py": "87b8403aaba06c2fe1879de873188e465383abc636f7cd9f69ed51f8a6100a00",  # b780 hunt1: frozen beta-79 roll for the previous state
        "mod_editor/core/nfl2k5_sim_qb_injuries.py": "95eba337fa04320f01e4a2c9d4146189ce3b3074993600bc97d54882bd78a071",
        "mod_editor/core/nfl2k5_sim_qb_injuries_code.py": "d0c34226fe9ed023c88ee57ec105d76d00c349e86166244b430893d7338e2284",
        "mod_editor/core/nfl2k5_sim_qb_injuries_code_b81_slice1.py": "bb25da81abf8bd62c615d1cc676401a5050f4ab0f982fff243dea14af53cdfd0",  # b81 slice 2: frozen slice 1 bank, read to reverse a QBMEDv1 install
        "mod_editor/core/nfl2k5_sim_qb_injuries_code_b81_slice2.py": "a893ed713c2a16ec9a4fbf33d8e3cdc330d6f80578cd3d3eefe04dd9ee211873",  # b81 slice 3: frozen slice 2 bank, read to reverse a QBMEDv2 install
        "mod_editor/core/nfl2k5_sim_qb_injuries_code_b81_slice3.py": "ec6737ce9bab5695714c7956c932272af6fe33a63b8f4411cbe1f8de6497aff3",  # b81 stability: frozen slice 3 bank, read to reverse a QBMEDv3 install
        "mod_editor/core/nfl2k5_qb_room.py": "c54f14cb6c6b7617b20a2512750910a29fc5f231b73961c8aa6405f98d0d8af6",  # b81 qb34: mod_build loads it by name
        "mod_editor/core/nfl2k5_qb_room_code.py": "f4beb936955b748d938bbd24700ce62c7dbd9d5335f268c037f6314afb5762b7",  # b81 qb34: its generated page template
        "mod_editor/core/nfl2k5_qb_room_code_b81_floor.py": "fca60cc8cb3b41a8dbb6756110d33ee0ef1ef70581420b7ecf73dbb0c91cbca4",  # b81 qb34: frozen floor handover template ("previous")
        "mod_editor/core/nfl2k5_qb_room_code_b81_3a.py": "892a6ba85e94f55151423b4842825d521b85e54c9dcf7162d41b9344bee513f8",  # b81 qb34: frozen stage 0 + 3a template ("previous")
        "mod_editor/core/nfl2k5_qb_room_code_b81_d1d2.py": "f01e39ac2a6fbf29595a28d7092d7dcc8fa7060081430f88d6295e9c5ac2ef32",  # b81 qb34: frozen D1 + D2 template ("previous")
        "mod_editor/core/nfl2k5_qb_room_code_b81_floor_review.py": "1c95004a4f47f2fd83d3235644c061a336a7ffec5d662604b47c31e1996be8f0",  # b81 qb34: frozen floor review template ("previous")
        "mod_editor/core/nfl2k5_qb_room_code_b81_handover.py": "8c1df5fc0d2eadd433f3558c334c07275284f43a1ec283842d3901eab4e8162a",  # b81 qb34: frozen floor + D1 + D2 hand-over template (b2672e398; "previous" since C21)
        "mod_editor/core/nfl2k5_qb_trades.py": "00f1b6fd4aceb6c647d7b490a4079b9ac998721d81174b3a379233116b76f6ff",  # b81 qb34 4b (C20): the room owner loads it with bit 16
        "mod_editor/core/nfl2k5_qb_trades_code.py": "03a3b7fe4d829e132d782f62fb180567b7bc5bfc581940c7ff8a3ae7eed7ea68",  # b81 qb34 4b: its generated page template
        "mod_editor/core/nfl2k5_helmet_side_numbers.py": "c10876d8ef2c26740f3559706d8678de673730a7e260285ddc35eaafec9e6069",  # b81 helmet-sides: mod_build loads it by name (route 5 = set E)
        "mod_editor/core/nfl2k5_number_kerning.py": "48405334b32b7495399f204a898825531423ed6025e848b51ac0c86891df6902",  # b81 helmet-sides: the owner reads Number kerning's state (same cell addressing)
        "mod_editor/core/nfl2k5_sim_realism.py": "81d981f096486cc13f7033e87b014694eacbbee82afeb96412784cb85ff7d77a",  # b779-sim2 r6
        "mod_editor/core/nfl2k5_sim_scoring.py": "7c3681cef1f94638ab0137d966f08d80fcde3dfc335874ae24c5fd9491815f96",  # b81 scoring: in-place simulated kicking, installed by the QB option
        "mod_editor/core/nfl2k5_cpu_kick_aim.py": "cc41567cdd80d6149af319cb2502b62f8d8ff32ea9263b1cdeee388bb9463f99",  # b81 scoring: CPU place-kick aim (imported by throw_tuning)
        "mod_editor/core/nfl2k5_sim_realism_b779.py": "687a35375780ce07948ba555a8c189167586393c5de6f48d954c2902a71010ad",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_standings_records.py": "175712ff8aff730b035aab671bf2208322ba52ec1fef758afad7d24263485c1c",  # b780-j1
        "mod_editor/core/nfl2k5_standings_records_code.py": "b5fa55b20ca61daf797ba9433ec4a950c14efccd71a0ec90a132a03102aa1e5e",  # b780-j1
        "mod_editor/core/nfl2k5_scramble_blocking.py": "f3116c50b1c01913aab22fc3cc497d843afffee4ee47161e11ac5dc0bc3556f1",  # b780-cv7
        "mod_editor/core/nfl2k5_scramble_blocking_code.py": "658ec167085e6fc083ec3acde723db330280091624a413401c09fc3e73643611",  # b780-cv7
        "mod_editor/core/nfl2k5_audible_legend.py": "a441d13947fd09d7dcd82f79f80f66642e29148484b40fdab8525aee14161b20",  # b780-p3: imported by throw_tuning for the build union
        "mod_editor/core/nfl2k5_lineup_roles.py": "084f75f1f872ebab56b930bd47d8eb72a68dfea2cfe8796e0a6c9835e950de26",  # b780 sub1: the SPECIAL third-down back + FB fallback (late owner)
        "mod_editor/core/nfl2k5_intro_autoskip.py": "a836a0f77a6cdf1402a1d4ec0c66ebe0ac0b5d973c36dcc007b6434dce0b6d95",  # b780-mem1: imported by throw_tuning for the build union
        "mod_editor/core/nfl2k5_injured_reserve.py": "e463fba60efaf9ccf9cebc1612c1ecf5bd6694e41f84403120e05ff07f88c453",  # b780 IR1: modern injured reserve (late owner, imported by throw_tuning)
        "mod_editor/core/nfl2k5_injured_reserve_code.py": "6cdccc14900bccbb41d9e1ac00fd776bf964a36faca63c91fafb42b2be70ddb9",  # b780 IR1: its generated runtime template
        "mod_editor/core/nfl2k5_franchise_ownership.py": "f8eabe44463a07f90c2286023562e5809156a6054f6fb8520018360f7352c370",
        "mod_editor/core/nfl2k5_franchise_ownership_code.py": "f407221db98c311cbef6f9626ca2b37f5f4ecbdcc2d5638bead3a57a4bfa93b5",
        "mod_editor/core/nfl2k5_injured_reserve_code_b81_pre_ownership.py": "1e1f421ecfdc6dd9d40de2696d9fa9f146858b0488e46fe31f83d28ef5c4f387",
        "mod_editor/core/nfl2k5_injured_reserve_code_b780.py": "0435e068e930f74a937e075f0f235fc61d951ba7b12873ac2b6fdcfc17f3b78a",
        "mod_editor/core/nfl2k5_injured_reserve_save.py": "cf9111798edbe0fcedfae7cf9894f288223da9f47a315c0f31bfcbfe79d1e6b2",  # b780 IR1: the save extension codec (imported by nfl2k5_franchise_save)
        "mod_editor/core/nfl2k5_preseason_warning.py": "44647523c32291820e98b2dad0a9c44af27fe6bca13626104551dc3647bcc6f2",  # b779-int1: imported by throw_tuning for the build union (693fe63a0)
        "mod_editor/core/nfl2k5_coach_carousel.py": "aa132ec652edafbaf86c86180e409eaa465039cca76ab6eee17aa8fd707685fd",  # b780-c6: the coaching carousel (late owner, imported by throw_tuning)
        "mod_editor/core/nfl2k5_coach_carousel_code.py": "86cd01c57d294d3c34551f0aa7f6949764350a7343e80ef3ef596f52bbae36e9",  # b780-c6: its generated runtime template
        "mod_editor/core/nfl2k5_coach_owners.py": "97094f12b5bad7def37132988614efbd2f727a12470b98712f8725ff406c4029",  # b780-int: c5's owner patience model, imported by the carousel at module level
        "mod_editor/core/nfl2k5_sim_stats.py": "52680d840b0bd4e01919d0a9160ece5f69eac6d45d68ed7d478464f304615ff3",  # b778-sim1
        "mod_editor/core/nfl2k5_option_defaults.py": "74c27b923397fc9ced78505caf95d4d9aacef221905ace82f1ce3230ffb0ad5d",  # b779-df1
        "mod_editor/core/nfl2k5_quick_long_release.py": "007dcffb32ccd61421ab69a2248e9f837298d3851e58e7de5bac2191c71ef898",  # b780-c-release
        "mod_editor/core/nfl2k5_clock_led.py": "ab030b1fbed873b96e0ba6055fcc38ef53193c31f2df496128e2de581e7b01c2",  # b778-sd4
        "mod_editor/core/nfl2k5_module_loader.py": "5a1422a3a348053a3f49bd16caa7c51f954894c8595b179f2f92dddc63e8b639",
        "mod_editor/core/nfl2k5_crib_trophy_room.py": "1ca109c95177e63990645a7c00c44b707cc750b5c6957b6d8e744f676d8dc0ee",
        "mod_editor/core/nfl2k5_name_keyboard.py": "f1ffd4fa4d820cde1834c14d9ee6853f2f2c54598029b1e08807dce4a32ace04",
        "mod_editor/core/nfl2k5_roster_storage.py": "b2bed5fb92dedd9d1c4312a7e9344ca1558225d9ed12977e4fe69f4ca9d85bb6",
        "mod_editor/core/nfl2k5_safe_text_banks.py": "c7ea4288611615204f53c40f5da06728bd9e5511eec5ae06711145e509461d48",
        "mod_editor/core/nfl2k5_save_rost.py": "df775f99aaa41a7e5ad099f0d8d7dcfe54321ec8651bd673b2accb36fd3dade3",
        "mod_editor/core/nfl2k5_save_writer.py": "48c281b51ae9e9acfd4874cb818ca7a891d2fb54d4159612160ac9cb7af49815",
        "mod_editor/core/nfl2k5_scorebar_v3.py": "4e3d58f8fdc71d6da202d1367826fec5e32350470dd88089ecfcb7d272ba67bf",
        "mod_editor/core/runtime_dependencies.py": "326c47fbd24a2cbd5e360b32fd8754434a8433d21bea7efda23bebbc0e9343ac",
        "mod_editor/core/nfl2k5_scorebug_assets.py": "9d7036c1a426faee7671337e976d6ef21ae8a7d4e01b03b9f1791651b75f6293",
        "mod_editor/core/nfl2k5_scorebug_exact.py": "2d6f954868d78bb08c179ea3fb092f1de19f75c4087dd2ea58f75f4923c50a09",
        "mod_editor/core/nfl2k5_scorebug_fonts.py": "b292f93b7bc25b64a379069b77c9172c1b92cf79553bfe4a7be835d1ad7119e9",
        "mod_editor/core/nfl2k5_indicator_names.py": "6d55f821ae030d506a20b0c863bf060b9bc2285ba063535ac9a49dbbfed809ec",
        "mod_editor/core/nfl2k5_scorebug_ingame.py": "092394682baf2c803e64d350a0fb85834a0b19b12ef0b60c14260839403fba34",
        "mod_editor/core/nfl2k5_team_names_2026.py": "dbc2b15d73e7750fb4cf1f184690f976942695d4e5f555ce63f12ca8ac6a07be",
        "mod_editor/core/nfl2k5_scorebug_mnf_font.py": "4aab9c01ea57c255671d7c3dde9e473173cf1b28fdd0004a4e2c053330415709",
        "mod_editor/core/nfl2k5_scorebug_resources.py": "3db02edd29ead0daa459229e1e5b2178a2fd2a8e61c95178184b524855b09658",
        'mod_editor/core/nfl2k5_scorebug_sprite.py': '368602f697209075621ae0b8419bbfdbc89c922aea0aeb277bcd8a4375695920',
        'mod_editor/core/nfl2k5_scorebug_teams.py': '95f27e3a4320488b98bc5dc6236b70b881299ee91813a588e7ff62ddedd1c09f',
        'tools/scorebug_sprite/xemu_model.py': '1b97da7ecdf4e0fe19d6a1d7ea41ff3110810f14777da88f3ca94e18e1f110b3',
        'mod_editor/core/nfl2k5_scorebug_sprite_code.py': '75f1ec71a015dfc026c2335f6c3b79c7b1d86b29c671048e8cc264c466feee85',
        'tools/nfl2k5_scorebug_exact.py': '8be2b18d28575b451d39bb15dab192546ee82dd0fa2be42bc649aa966ddb38dc',
        'tools/nfl2k5_scorebug_projection.py': '1e06472e086a0c67abe19d2be10c03df456f67f2ed13efec3ed6ed31a2666734',
        'tools/nfl2k5_scorebug_template_proof.py': '6f21bd9fc54d472db03ad5e84d8344cfdb358c7e2e6c950134d80e5cf345bcc2',
        'tools/nfl_main_menu_font.py': '64ae881a6ccaede10d15dc3d68277d061c5ccb9f94ccdee5208095ca31316d60',
        'tools/nfl_normshort3_positions.py': '925147094fdf03d91ee0e0487b0dee3b632438c333fbb9f2b8ecb54a15cf19e3',
        "mod_editor/core/nfl2k5_scorebug_runtime.py": "4b74a4e7e74a0eab7ab25bd7f9bdc9c74e06fb527401a83a3e7cc9e240311411",
        "mod_editor/core/nfl2k5_scorebug_runtime_b779.py": "11e77fcd5105353eeb89132f1fcbe73528cb503b46c4be13f7e9b45d8a7b29a5",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_scorebug_sprite_code_b779.py": "9bbfcb2bd87febab32a6545413f679d422d423b484958ec969150bdbf4c3aa9f",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_scorebug_sprite_code_r16.py": "a5f78258fdf74a8558d7cf38f049492b9b06f6ba202a890bf3694b33f3577af2",  # b780 pres2: frozen owner revision 16 engine (b780 gc1), recognition only
        "mod_editor/core/nfl2k5_scorebug_sprite_code_r15.py": "9dc1a847fa95ed628a9b0566c63bb218324828131ccd8b507413f58584c1ae36",  # b780 pres2: frozen owner revision 15 engine (b780 p2), recognition only
        "mod_editor/core/nfl2k5_playcall_layout.py": "10a12aebd99cd40ebcabb085e940734607c28e3c265902eac76580ce4cd9a077",
        "mod_editor/core/nfl2k5_playcall_layout_b779.py": "6f417b453783a751845d45e7d0c7987e2414cb86d03fd531e966533f4f8cd863",  # b780 n6: frozen beta-79 revision
        "mod_editor/core/nfl2k5_scorebug_source_art.py": "2ccce5d54172944a142786425de5b2a9ee4336c329086e7b92db170c94f98d13",
        "mod_editor/core/nfl2k5_scorebug_template.py": "409f7324352b88a6b4387b1f1a8ee1231c56f9674d7762ece24a8142fd2d2060",
        "mod_editor/core/nfl2k5_scorebug_unified_adapter.py": "3307d3b1777fcb51f112dea2c6c5290dd969c3037d5bc21112f9740b7cef9bfd",
        "mod_editor/core/nfl2k5_scramble_tuning.py": "f9e85191b7d93849a92a749385bdd746609465238e776ea0e7f072ac29bf2e92",
        "mod_editor/core/nfl2k5_screen_hooks.py": "6663e8b6d4e023335ad1e676881e70293144a5e8fc078c2374fa828080b37627",
        "mod_editor/core/nfl2k5_screen_hooks_code.py": "bcab9155aceb1e62e2cb1e5a7b98231ec7cf101ae3623a8e0b2397dd4ab27b33",
        "mod_editor/core/nfl2k5_screen_timing.py": "8c7245f79a2c79df3974545b30db4de45c6b1b8071ff5d7a4bc396b2a9903894",
        "mod_editor/core/nfl2k5_season_cap.py": "dda1e4d3a11bfe798d837ab8629bfa1d4e90fc233417e39de1974ac1c5b959c6",
        "mod_editor/core/nfl2k5_season_length.py": "259d80385ea6e657ea2732d87f1711c90f5f9165134eb5d62b55ecb4fb5cca97",
        "mod_editor/core/nfl2k5_senior_bowl.py": "ce39c8aef6d9f5438a98c67360c1392d1e5063d7f5b9094b615dfdae141c255c",
        "mod_editor/core/nfl2k5_senior_bowl_code.py": "000abee8fc9bf5d382d4c8934a0509c32de7976805eadabb5c4aed3ccb0812da",
        "mod_editor/core/nfl2k5_seven_on_seven.py": "8d0da9680a0481ee861c45b0dc8f9e785015bd43e472796a3b6e781597244269",
        "mod_editor/core/nfl2k5_seven_on_seven_book.py": "4cb148bd14f33bc67eab092220156206565dbbde9f75a217712fdf98ece3a80a",
        "mod_editor/core/nfl2k5_source_cache.py": "04c9f2189947546d6bc124da57d02b7d3d22df7b39c292a0dae8662637bc594a",
        "mod_editor/core/nfl2k5_special_roles.py": "ebaec1af405b5ede1f931a0f825b5702d4e44b0e79cd7067ed51d631969aa943",
        "mod_editor/core/nfl2k5_stadium_cache.py": "af3f8983f4312f755f27456684e6e27505d41eda07539ebcd813b90c81a88762",
        "mod_editor/core/nfl2k5_stadium_studio.py": "6b4456f70acaa620f36a2496b2e2af75948cd83f93dae49e3c189b0e3edb8988",
        "mod_editor/core/nfl2k5_stadium_texture_writer.py": "bf456928ad0565095805f9c39e270d50f49ee24f2aec1a8206937659f61cdc92",
        "mod_editor/core/nfl2k5_team_column.py": "beb4ef328d010fb4f22238ffe80a7e52afeb247cc55df37f5bafdfbd44931883",
        "mod_editor/core/nfl2k5_team_history.py": "1cb61895afa12bedd10879f2394dc83d7b12d261d5e9fcf6c96a6017d054eb25",
        "mod_editor/core/nfl2k5_team_logo_swap.py": "d4e46ff301b3449fc78a145548be2bcbc6104caad80563e1d940ef564fd73c12",
        "mod_editor/core/nfl2k5_text_catalog.py": "514706a38b28a4c7189f49e7601813cd55e16f1b9e81c9c8aa3e92c072e962c9",
        "mod_editor/core/nfl2k5_throw_arc.py": "0fbf33d12fe27a0f940fb7e13f375390b88701c4ccb7e89a1de895d8f66b9c3c",
        "mod_editor/core/nfl2k5_throw_tuning.py": "f3b9cce3242d11faa8643f4e3293da76b3899ed41c0a69e2aae33e84fb21454a",
        "mod_editor/core/nfl2k5_trade_deadline.py": "6d06124670e0c360c9c9600ee7010d8afd239df7cd6352e18dd3762fc72297f4",
        "mod_editor/core/nfl2k5_unif_color_writer.py": "5e950cc404e25c1fbeff7ee5aa2a3fad235115aeddd743e95be6862677a88324",
        "mod_editor/core/nfl2k5_uniform_catalog.py": "e297a2431241c8cc5b0fa38b42ae6ee77771094fafda28f44c98ad47dafe10b5",
        "mod_editor/core/nfl2k5_uniform_choice.py": "d618e2d8ebeae1443b0e9846e4f26d53cbc8d74314253798b860ddf8e9c312d9",
        "mod_editor/core/nfl2k5_uniform_equipment_writer.py": "0a81203ec407acd35c9685d158d75ba2fb56872f4f52cc58dd7d841b5d6dfb11",
        "mod_editor/core/nfl2k5_universal_asset_index.py": "9df3c0a754abcb60fa4db3afd0f9b8af364f60551014d259e2713f5387491421",
        "mod_editor/core/nfl2k5_weekly_prep.py": "7987f113bca8fc358fe197ce791b6f1114323b1468c27f6589df6bb76ea90292",
        "mod_editor/core/nfl2k5_weekly_prep_code.py": "b44155d9f5ceb529d6e9534e9d23f211c569cd4e602e28683479ad187bfb40cd",
        "mod_editor/core/nfl2k5_weekly_prep_code_b779.py": "aa5ca8cc6a4427c8c5a487d03a9b5cbdf858a8d44b178c0ca1c31eb21813aba4",  # b780 modes2: frozen beta-63 .. v0.9 RC revision
        "mod_editor/core/nfl2k5_weekly_prep_save.py": "aedb0576c3a19a3a6574362729f83d3dfac5bc4aae7eb203388403c721a83720",
        "mod_editor/core/nfl2k5_widescreen.py": "98e3fd35f5c45a35143e678055872fe405447a735b211cd2897119d3ed801b4c",
        "mod_editor/core/nfl2k5_widescreen_menus.py": "a72a4d2387e023c0552c9bfb6c5b3330a689bbe00ed5619853260a7c13012701",
        "mod_editor/core/nfl2k5_xbe_space.py": "86f3b1c7237b548265d5ff2d95de06fad18e9694c0c0f7d9a409ccbc22d61f9f",
        "mod_editor/core/nfl2k5_zone_drop.py": "96b915ac40cfbcb61b9bfa88a584a18841635e061947a7e1644ea193f83a94f0",
        "mod_editor/core/nfl_audio.py": "31193529647bd5fc35a2c25d38bccb83d20b16d46358169c26ced120c6c8e05c",
        "mod_editor/core/platform_compat.py": "b63521c9b17119b87558aff36a5a914d0c3fdd42e96240cf7de20065ead644d7",
        "mod_editor/core/recipes.py": "10d518fc5bf0dab89cc9d1b0b055dda880ad0f24e2e7aee8dbe9d74fda2d97d8",
        "mod_editor/core/sources.py": "d47ef48a21d0cb4bb47e2b0f5ace029e68c3dc8906caa7d48e19e6dea4341375",
        "mod_editor/core/texture_master.py": "2597b4d177703f8c81e3c10eb9ded655390ccfa47f36bfab8d06fab1b0e79098",
        "mod_editor/studio/audio_annotations.py": "c45c94b011d703a24d063138f82477814495705c3b0055a9a867dbab453ba923",
        "mod_editor/studio/audio_bundle.py": "fafc659024246d1cff782ab07f6c744c97a563f64fedca8a288f3126fbeb4604",
        "mod_editor/studio/music_service.py": "2f2126c1055d75b71597bf60d2583861eceb790499e2636e51ccb1e3428393d5",
        "mod_editor/studio/project_archive.py": "07ee0383db64aac79cd2846903da63756b45b09c05118de4fd6fec612701c8bb",
        "mod_editor/studio/project_manifest.py": "9ba0fd3d5ce51c800959489ee1e5116a68ec123351cae66b7833da1a6f0aebd0",
        "mod_editor/studio/session.py": "04f02116d8e8904288cf21953ef5002a9b63bcb14a594d4999b63beb9ea186f5",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/game_audio_convert.py": "3ba3f1f4c2aa452198a12e65d8e93e8d690988d0a6a88c80d7c5de91c1e5a983",
        "tools/nfl2k5_commentary_swap.py": "d12b0a4595155acf97545b01fa82791b43357e5a07a1569a58b1135e9faa965d",
        "tools/nfl2k5_jersey_png_workflow.py": "d5042236dc3800e52325a163ad43efd1769ac71f38c05a4d1b8d3532f364184f",
        "tools/nfl2k5_kickoff_alignment.py": "31218fc1e553adf4ab0f7fa59857459da16b828a5bb3679aba3c27d419cfe82b",
        "tools/nfl2k5_playbook_position_recode.py": "95d8555d9c548fb61edd7d027d2d95249e6e2b6a27bd5891545939404c39e22e",
        "tools/nfl2k5_scorebug_espn_art.py": "2f6d15ca6fa67565781ac284141b68ccee1d4c8f2b9c9c87132026842f06313b",
        "tools/nfl2k5_scorebug_layout.py": "63ee159943a6494de331339e7460cb674955698c1d0d6a3aa8057e024967dcc5",
        "tools/nfl2k5_scorebug_position_patch.py": "eb2b913bd4d0620dcefc4f280db1f6d73e4a5c348b0483a246bbf587506cdbff",
        "tools/nfl2k5_scorebug_reference.py": "5186fbbbc75619518cdad41763d4fcb9d438bb2bf37ee98bc74b265c6446b435",
        "tools/nfl2k5_roster_reclassify.py": "0f4800d1558de2c5b0f9f2722b5f3f5d7a4797a58f454f0a7db9179175af8831",
        "tools/nfl2k5_visual_mod_project.py": "de7fe94cea4695f950ab7a2b2cb2f440de9a061b738e0369bdebb557614c0bc7",
        "tools/nfl_all_texture_xiso_workflow.py": "61d0574ae5320cb7b12b96f1be0b34dcf1fdef363091b00de0fd0fac7130bd91",
        "tools/nfl_audo_wav_xiso_workflow.py": "d684cbe7b30f77caf808bcef3d0219777b333336ae5bee4837d10f69cc1d13c6",
        "tools/nfl_create_team_field_art_inventory.py": "da59018f1417871516b75769ea53a351a1d2b03ed855f985c1f88ac333b42489",
        "tools/nfl_create_team_field_art_png_import.py": "f4dff7694bb11f758e78773ff7e23b96500499f198e10efffd7e680765780b08",
        "tools/nfl_crib_bar_monitor_png_xiso.py": "d0ff8f4ebfb20e443dd12892e531a6ac1736831c182c35a19edb94a8f4cc8c11",
        "tools/nfl_crib_team_photo_png_import.py": "00c05c92fe9ee194b2c1c96830efc09aa99f5023687f29b5a08c16f3dbdf9539",
        "tools/nfl_crib_team_photo_targets.py": "e0ec8925ae179ce0955e32c681f7bc866ccd8807d5489791d8f9210bb955b357",
        "tools/nfl_dxt1.py": "bce75aca68acbfaa5112927e228672d4d77c58fc27cd3ce047751d8875dcb9a2",
        "tools/nfl_jersey_tset_png_import.py": "af030703a499adbd9c2f3097ede4762ebfe4482b5f5222325efbafecd994155b",
        "tools/nfl_jersey_tset_targets.py": "6835fbeef8f34aaa137b582a386d630860eccb1bf17cc626232d3ff36bda02e0",
        "tools/nfl_live_face_texture_png_import.py": "e0f7398cbdb87a79593b5a8a61ec12b2ed3b03bb1966d4fb14f581543c2c7864",
        "tools/nfl_live_face_texture_targets.py": "c9748ee6cbb0441fded6c961ef25ec913e3294218c7892eacb731456c315f8d4",
        "tools/nfl_live_helmet_txtr_png_import.py": "14996e8675d80cf559668079993610bfe8de627d834f1b3242f55ba2952c6af1",
        "tools/nfl_live_helmet_txtr_targets.py": "26b18b9aa8f0afd71e0b137eef52f2cbfd0f2108cb63546979883446bc93325f",
        "tools/nfl_live_numbers_nameplate_png_import.py": "86a4796e44fcb286b8fd9450fc5242f4ddc22fb83a4fa32ffdab3ecbdd2d3449",
        "tools/nfl_live_numbers_nameplate_targets.py": "e122e41055e4d3b02ab35041db2e3cbd828fcf90c1b8f258abeb8718c20fc6a4",
        "tools/nfl_outer.py": "0f27ac4157f13704e4303dbf2e146427cc56d1d910a3e242fac4081a04d9ee6d",
        "tools/nfl_pants_tset_png_import.py": "63f0f7c0e47b785a712169076aaee8a08d3c5e4891ea3951661bc5587609c2c6",
        "tools/nfl_pants_tset_targets.py": "8d5f39d1ee9d62cf6b79600fde31adb61eb77914d49a4efb91e1da10266e3eee",
        "tools/nfl_player_portrait_png_import.py": "d5c9b0b869a02daa48892abf75f2efa43b7b6fa5d961b9bdb446d88327183f94",
        "tools/nfl_player_portrait_targets.py": "0121d71588ad717ca68f4b2c67dbf32f8d0d36eb47b7b1e28bc4d39ce093c3ba",
        "tools/nfl_roster.py": "d81cd9c95e792c3e8df827e9058323ee95b33a9b7833f6f06549355e77528b9b",
        "tools/nfl_scene_probe.py": "851841d8474dbd2e8be098a9c84537057fcc9ced9d4d74669e2b808e00d71450",
        "tools/nfl_scne_gltf.py": "afeb666595742e2a96075fb9d0edb4d8ac913b9e1c2ebfa6ed3ba04496a57207",
        "tools/nfl_scne_inventory.py": "0f58222812df6b380588f8b0a2592101136a863cd0dd170b0f32df726de2fc6b",
        "tools/nfl_scorebug_png_import.py": "0dbef5f87476633d91ebea19aeb86451dd5ac434743ef80a5a694cf4e3975440",
        "tools/nfl_sleeve_tset_png_import.py": "635e9a49707fcad189c490a988f6d7a9117ac27fcaf0ee2b5fc394cd20fb1c80",
        "tools/nfl_sleeve_tset_targets.py": "41cd48b6dc9f4779bca4d9e9ecf6e32246dfbc34034385c40b8ecf3ee933953d",
        "tools/nfl_static_gltf.py": "5249732b635374eb33bcb39f162224bccd2163cf1cfd01b1dfc8db42ac40bea3",
        "tools/nfl_team_select_card_png_import.py": "7012a7d75a4203016b532e301f9727ebf5d58f9f88dc1271087c5461e493af1d",
        "tools/nfl_team_select_card_targets.py": "125361ee0aefbcbb46da8d466a1d850c91c3d9f33ea0eced3f2240f4563d5766",
        "tools/nfl_tset_fixed_span_verify.py": "d9a60349538962cb7c3ea8e3d2461b118fbbc10d05e9b68f0fe010f8cc1c2eb1",
        "tools/nfl_tset_png_import.py": "5554b629aeaa5f2733a8dc493801d9680546617de676779ea4944e1210e1f0b6",
        "tools/nfl_tset_png_import_dynamic_validate.py": "c54e1991cc9771e03b7f23dbf35cb6858ae48c269c607594c85aff191a124a42",
        "tools/nfl_tset_png_import_verify.py": "777ca0ed729e54c41f7b522c4b121f577a573f5b010a851ab36218fff472076b",
        "tools/nfl_tset_png_import_xiso_generic_patch.py": "a84699a55b7e34ff49a28913a7b892ce673fac4b78d427929683c2afc0c68cc2",
        "tools/nfl_txtr.py": "1c8b7bb31f47c9735d73c1d871f2a43964f011aa2e983980c1274a73390dd5db",
        "tools/nfl_uniform_color_xiso_direct_patch.py": "bbd4f5147d19afe3ad3ff0079c5bc0693108b58956bed74444c659718aef4ceb",
        "tools/nfl_uniform_inventory.py": "f2fc4ee3fad2c7eff0e2ca669c7f2642cea38a8c4d5cafb6d17a9c0b6e042740",
        "mod_editor/core/responsive_json.py": "7fb0241f333733941dab16032bbcd1310fa85a46f850a7d774273ff68dccb18c",
        "tools/nfl_vc_lz_fill.py": "7b9323911f3f7ccf4bcd9e247d516f2776720ca44bb73218133088fefd715606",
        "tools/string_table_inventory.py": "8f69e9b8fe016509739cfbf10594d25e34288ca062b13463d18e9cc9611caefd",
        "tools/xbe_info.py": "c7843c317a7ec022bc22ee6266b96d856b57233af2d6baa71ec071a94212e0ef",
        "tools/xbox_ima_encoder.py": "2f6c7209674d93c542f4c67fdab2ebfa4aaa8a6a21d6b4a08d07a9996bf79d76"
    }
    data_pins: Mapping[str, str] = {
        "data/vip/coach_sources_2026.json": "54fac5e396a2d76c574d63b94217261c58ef2dbfa4f1906fbbade6e7951c9b63",
        "data/vip/coach_portraits_2026.json": "aa398aa7b0e695c73b4a809ba5886bb7df95d1c4173adb00f542d6fd0ccfebe1",
        "data/vip/defense_identity_2026.json": "12e2bcc1b7ede02dcac2d2f43351c7985e88ab4a62ad908d900168b4009a55e7",
        "data/vip/coaches/ARI.json": "f05194553bd87ea58fd07e8c32a0f6c127ab72c84b337ce23fb28e88adf6bb25",
        "data/vip/coaches/ATL.json": "47b81905bbcf74fd0fb3e70098e81191d17a47f0c332a2a2f7f9fc2f41f81713",
        "data/vip/coaches/BAL.json": "3fb8a696df304884656d0c291ef07cc0ec3d29779433e2b2678cf2a2868db404",
        "data/vip/coaches/BUF.json": "da4cb5baaf325761e3348c56bcdbe5bac43c32eb1be0e9ebe6eb0b7faf18c6dc",
        "data/vip/coaches/CAR.json": "798f94047b3b14bf8125b101cfa82f334605551d3160f98fb30bdc66a1c4ee28",
        "data/vip/coaches/CHI.json": "40fa7f7a9ec3365928daa61aa100a106ec424b66031fe8f0c73e795b0c9d8cbb",
        "data/vip/coaches/CIN.json": "b30981f746a96d80bdd123887a1b02eff23ae2448a9f365956edeaf286bd4eaa",
        "data/vip/coaches/CLE.json": "721689ead13c3fc10548fc5f81340ba60038729ee65a165103ed15c53317c845",
        "data/vip/coaches/DAL.json": "fe6d1cefe369f4c8bfd527a2103dba4f38681a68607b69bb75654b4a9ac4d2ad",
        "data/vip/coaches/DEN.json": "2153ab654d1e5225e7ec0028c7516d55e4fc8450931a8ea5900d8e418a3863a4",
        "data/vip/coaches/DET.json": "bc91c0d3925209919b5b42c7a8f8d636827cdcefbbbf1a7fe724deab523b6474",
        "data/vip/coaches/GB.json": "489428faad98e0b90a29d7c79acc63a44a29f68669d758bb7862bfb9797d4ada",
        "data/vip/coaches/HOU.json": "d30d7c17a2f54c709e65150a3c1f5f7b3787813bdbee8cea87896a55bf4e5bfd",
        "data/vip/coaches/IND.json": "232fa74ecb56dd02aed9968f35fae349aba6d8081d4e559eb5370bcabde10932",
        "data/vip/coaches/JAX.json": "5d2d5c5393247cf1fa81ee0acb99e0da9b752d59a8ffa7d6edc819af01ac3a68",
        "data/vip/coaches/KC.json": "f82aad77da6c424bdf2e2909be3b1d2cd9c5841eefa537792ae7c51227b2d6ed",
        "data/vip/coaches/LAC.json": "6418953333be5652fc32da4ba72e09e46d4ba2a047b584880c6aece21361f8da",
        "data/vip/coaches/LAR.json": "396d16b9fbaaf205e1a3b30754e99df50f4c3eb4dbfb4394ef5fb4dc1acdf2b4",
        "data/vip/coaches/LV.json": "06ccb5edb5fc048201726149e73ca35ef0f4c2bd461a5a243f0f8997252af6ca",
        "data/vip/coaches/MIA.json": "ca1eaa093d0931f7cb0dcac699ea3d2e06236cd5a5eddd073aa48e7d92c2e1de",
        "data/vip/coaches/MIN.json": "0679b1718eec1327711876aa8213c89bdf0f159dff77013252f8d9d55a4e3dcc",
        "data/vip/coaches/NE.json": "24d671a0e130aae21edd1d2b8fc35c3c6928d49123c73701dccb254b0820f4dc",
        "data/vip/coaches/NO.json": "85f8a3f98d5b3f2e556d626937fdaf76814e157c3e4de1fd4a8935d639e4fce3",
        "data/vip/coaches/NYG.json": "aa2fc658e75f65c20c26f07794289d31571ecd84397e0be3c307b816eecbbb0d",
        "data/vip/coaches/NYJ.json": "b3f0c507de82070779956a1fce4e767dd0214deb4e529a4d9744e6531d2185f8",
        "data/vip/coaches/PHI.json": "881f09f1b31df26633889bbc3e20fe53bb0356bf72f66f1209da602e24ee3890",
        "data/vip/coaches/PIT.json": "1d0e71ad1a9b9a34adf91062b62acb739a24758c09408680a1eb835420d87c05",
        "data/vip/coaches/SEA.json": "5e131b080819369335d3edef136e1d509154af25ae15c7519c8863ef8861e578",
        "data/vip/coaches/SF.json": "002e71db711aef0896f4219f80fa578f23cd59c304da3e2ccd2b1bb41225c34b",
        "data/vip/coaches/TB.json": "2f1626c3a8047afff41f6fa7a7cad359e9db96c92356a83ed8bc38368057057b",
        "data/vip/coaches/TEN.json": "34a02ba96970f7b88597cd0a129394e908317f92154e0cb20332a85af831419f",
        "data/vip/coaches/WAS.json": "a3975b14cc02719a2152b8f6764d80d091ad4c3a987ee6fb6ff6a157f6544b28",
        "data/nfl2k5_moment_era_kits.json": "6f7095e05cc31ece037aa40cf2d5b315c45566482f7b4a1a6a855067d087ac76",
        "data/nfl2k5_era_kits_pins.json": "de18bdf5f1b32067b286c72c275641a6e3498791f852b6bbe48ea2c80ad0db90",
        "data/nfl2k5_moment_kits.json": "e2fcbb93f376f266f6973626a48e2244521df1f529f3fbe67ec28cfdc7565c18",
        "data/nfl2k5_moment_kits_pins.json": "514dd6891d97b7102d7c3f85bf355840faaeefe13e7a296edaa34a0ef176a342",
        "data/nfl2k5_release_gates.json": "12b1146cdedd09e72fc532b712b4726cf744ee9f1bfa360c4e6ffd13b1209285",
        "data/nfl2k5_unc_bowl_uniforms_pins.json": "84dc131eebe5188fbfc18eee5187abc8ac5aba572b3796a35d2cd905a2769fe0",
        "data/nfl2k5_nyg_numbers_pins.json": "e1d34f4a340820f6569f362a91e7a1a5f5f96fd74c3a46644d656500a392f2da",
        "data/nfl2k5_kit_fixes_2026.json": "d33818434feb3f30e5d2515eaae1b186f97bfc6344bd477298550885bce96156",
        "data/nfl2k5_kit_fixes_2026_alts.json": "8a15681861c8abbe4c66c25e27fae776e3d37495f8e0ecf68fa4ffc6660ed7f5",
        "data/nfl2k5_kit_fixes_2026_uf3.json": "f4a2cbc1368de99d800498ea969041d29bb0e195fe6ae6d32f2213c4174c71fa",
        "data/nfl2k5_kit_fixes_2026_sea1.json": "a313792e54018305ee69026e06e1227f4998e7bfe33b95d2a55d27821fd4da62",
        "data/nfl2k5_kit_fixes_2026_ov1.json": "506d9592290de13e4aeb17a23a0febf147e4392b985646ef9c0df5e15765c9c4",
        "data/nfl2k5_pants_hem_2026.json": "c85ecadefb53337ab7b97996b36b9c36d2119e4745f64e1bab34e321162aa9ca",
        "data/nfl2k5_glyph_fixes_2026.json": "a709d39b5fb5ab4a6f6793e6626d36771197c6a196c410b8057e58f899148387",
        "data/nfl2k5_nameplate_fixes_2026.json": "535f690f05dfb40a53239ca007fef42bdc4eaaa9611fcf4b74b1496b62980200",
        "data/nfl2k5_glyph_fixes_2026/TEN_28A0_digit_arm_7.png": "01252bae05b33caa13780327eafd8add37303d54bc27d46429cef61230a292d5",
        "data/nfl2k5_glyph_fixes_2026/TEN_28A0_digit_jersey_7.png": "5da1a357b81632f469e23f506155ff43af10b2fad036a3de285145e7b694c713",
        "data/nfl2k5_glyph_fixes_2026/TEN_28H0_digit_arm_7.png": "078b28a7a0ae54e18d08b4580155ba6fa49fe566932305c7decd795a96f6d17b",
        "data/nfl2k5_glyph_fixes_2026/TEN_28H0_digit_jersey_7.png": "25727ec3a92a703131e11766c4da6a781a63855be44d10a0a961e451cad02de6",
        "data/nfl2k5_kit_fixes_2026_ku1.json": "2811ee1e688df9b388544d335106df651eedef26e4bedf69c0e3b914a8d08c97",
        "data/nfl2k5_kit_fixes_2026_sw1.json": "857e2cc360d95f830840bf2db620dfb5499e92eb4e12e0c319fcff205102f459",
        "data/nfl2k5_kit_fixes_2026_names.json": "cb354c62aa6b6e8de0ff01e9f25937f0a2e54169bfc37932bd689599529693fb",
        "data/nfl2k5_glyph_fixes_2026_b81u.json": "dfa1bf243713de29770e08d39dea4df0666591d4aa5565c9edc133a7369e452b",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_0.png": "26d9a687f3d5b42b484cee12564b93815034384654dcc5e137e69957f89e20c9",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_1.png": "6388edb77bb69daddeebda1b96d96b2cf0532b7314a02492ea5f78290cff195c",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_2.png": "5dc0b5217b5df5da541acb6e87b9a9bbe4d953d7c505db3753f09124901b9ca8",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_3.png": "06b923bbc3f0ef44f2e3a87e2d0c69bd5a33d8f9e5a63fd6fb2812224827118f",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_4.png": "ec60757a89eec56eb4cb51296d1279dcb48165d981a8e4390712dd65490d971e",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_5.png": "0007ea69c17c4aa5f5ea826527de17280ca9e0716855d2161d01f5262857b3ed",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_6.png": "0c8ebbb3b2fdde5db4d21ef558cb1f44c8137a3acafcbcc3b6a91e8281f115c8",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_7.png": "aea9b035bc6002a1fc8edacbd90bf92efbbe7d45f89a78431abdf2dc1cfa14ac",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_8.png": "af14b2106f6660fa732d7f81db9f527a9cd9391bdd13b76b2ef3dbc26887b88d",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_digit_jersey_9.png": "1ae468d59da7633fb677373729d2df4a2f31cb5701d5799893e8cf4dd20e38a8",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00A0_names.png": "3e9ebb153c98e87789d4af4fe38536fd0f63cb951ecd496e37113066d9e156f8",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_0.png": "09f227a1463e3d3e07c0b8ed96383c16e40c575f7772d452643eeebc6acd2acd",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_1.png": "c08191d18d99abe876117a12253c73623b5fd9f30688e6c2f1db9523cf5842ee",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_2.png": "322d2a8d0cfa36059ccb5cc40e429d44dc1efe0926b1903640ae9512ce4ad208",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_3.png": "033230579b3a60ff8f05a0a8bbd28e2e99280935d3156feaf29763e815a814c5",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_4.png": "080799f8c2149dff351d098c735dbcd420aaeb49e5cbe61c75ca4d17f3ac4162",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_5.png": "8ca26204d08dea440b6df16e9c799a4bad70a9be9130bc6fbb8a1cedf2c1a4ef",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_6.png": "3c4724ac12b20e524f19d6a85479c88bf1537b7f56602a4f7869283b49eb1300",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_7.png": "fa0712421aaac076cdd7e2b118c02e4e072a9473226b657de435889c0670251f",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_8.png": "02644868de5a98b9cfbfc0664ed438f933acc44fe514900a0af51fa5a78fa12e",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_arm_9.png": "14692c0b48a2dd55dfab879ec17e4a77da77a324996e2fcd35d9e4a289f88126",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_0.png": "a6d6bda51977a867ec996d373a2cfcb87a3e580062acda7652ac63ab3cf6d695",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_1.png": "9584deda3afb984cade02e04c98498d48b74d1896afd788a5b8bf4113227eaba",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_2.png": "1f39c157d2b84aa27315a1764f102bfa4bda9e134f1289183b2d8159a97087b6",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_3.png": "aa67380b3dbb2f7c8fb4ca650329725b455cc867d01b9a6da0282530d77d026b",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_4.png": "ee8e48efc1c022b6a39f6044f66fc497e8d17813301790d33651640719c21db5",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_5.png": "3d58a4e266b667414390fb816e4224ad68e840d4083c9b8cfcbdc8851eb06537",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_6.png": "5e283dc43f81aae07001535dc0a9f378c11f60207d36080055bc62020adef510",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_7.png": "169bcb26af7ee1616ca306329781145a2fc8ea8e7c878bd9ebd271a1aec7e745",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_8.png": "cad9475458bb6594dad79becfac37dbb71f80bcf58c5ec38f879802d4da4622a",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_digit_jersey_9.png": "2111dbed90563a3c2b5743ecdae254795d0c6ad223d726a8198a718803b48400",
        "data/nfl2k5_glyph_fixes_2026_b81u/ARI_00H0_names.png": "4a9dfcfbb5130175d671d38ea92c314a079d4c4b88d0eb90ed620971f9dc8084",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_0.png": "7c3fb48feb6e6480fbf744c5c0bfc154bbf3fafda84c8263ecaf2f04bf9c4149",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_1.png": "e4640a7373c0ba2e62aeda635f1258360f6e26a29b652c8aaead0d9332df704c",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_2.png": "337b9eb1b206df48964a422d0944ade9632b7e4826c46b76daad880bed58ba59",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_3.png": "2fa0be382626d61438abbf7a32d77da01f86b28fda222c814598e68da98b44e2",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_4.png": "8019ebbfda672c4aac4426bf7ff6a65369f77c93f38578814fe07b5de16dc160",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_5.png": "1a8180d458fe91bcbffc600c7f1578e6b8a55051fe33bec018225413b4180c39",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_6.png": "a326e1603b276057083eaadc51d3b4bf41db807c823d90a4e19ee35e92f611f9",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_7.png": "075fd2507cd18438075e3799478bc848f8f38712bb6efb58e559426a7daf0fa4",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_8.png": "ff7f83e7d21c9f0aaa66a1dee9a0ce79dbb370e7b505f710ec7276a55a6cb672",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_arm_9.png": "68f46d4905f9b311419f3916228814a33a9bfe18cde2385ff457169e4b1565be",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_0.png": "bcb2adf17bba979cfec68040598a5985731b08ad24573ba6edbda2ebbd30cfc6",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_1.png": "5376522be2fa0f22877b8c184cf95621aeece6e76b5cc550c82d1088540593be",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_2.png": "3b8e9edf21fd3134626b7ee4be228537f1336c0cd68f2ae2096f9cc1af5c5d82",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_3.png": "4525f5054b0e75bc28bf9ca04578926b6a4d902351945079921e93549b5efb5d",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_4.png": "9cab4abb576a0cfd1a46971bff686aff15be32bd834e53f0513ca6e709797628",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_5.png": "2ae9d765544da06f84f908a3bf56f79252136e05fdfdce3bc9a70024a7aba15f",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_6.png": "88b31457034133ebb817bba8ead4c97d335c0c1351e91f15f0140cd87e4d0478",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_7.png": "990242dfcf1d6ae005529b552395b517397e73edbc4937585a47867ebfa7e4d3",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_8.png": "995ac7a99ff340d7d68979de8e16a547d4c56a0985ced838bba00f885cf180ec",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A0_digit_jersey_9.png": "736123f280f441d770e9616396c1fba73934f3fc92598e7cb2fa61a25cfee22b",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01A9_names.png": "ef7150b4981adffaa52ab28979e503446a460778c46cad619a375aaacf347773",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_0.png": "388d52adab164b1405dabcf2dcc5166bc75b7d8a463df58a6d1b4b139bced813",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_1.png": "7e9f50520338a94e98614fab5001344ac6a9cf66f557e751e9c3c91e10e031c5",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_2.png": "5ba6685c3519cf82cc0192b30c9503e5e8b002519eab0728d96eaeeb812f3b44",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_3.png": "5fdb6ee0ad5419ac5bbc5a9d0ba8a76480075dd644e69072d18663646724bd1e",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_4.png": "2fb1a3053b8aeb6ae64f1124afd28b9b32e118201ed9bec80b65c0b4f82f5bd7",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_5.png": "dda26ea19fdb40fe6cccf600d656f552be351b68b91ab9ffad8c8637a802d02d",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_6.png": "0deae7e063d4ef545e67f0202ec85a0365c337779f08b90b49e68329ef1767ad",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_7.png": "04f77779d69a79335747553074c9ef4f753a60e8079467b06a0f650ee2565496",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_8.png": "68fd036a98ec42cdec9d9f2e93867dfd5b5c64d0bc1dbf5ac25f7c19cc8cfe1b",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_arm_9.png": "3adc476de43dca022c0b3b4ac150581cb879d5948e531e117fb4344453320a16",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_0.png": "5400c59dd8179d7bbb0e198c43e3574939291f778f565915edbcec23c243d2ca",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_1.png": "9a9ba2888d66e365e201cc9d6c28ca3573b783c381f7cdcb6b0ba85883abc410",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_2.png": "389ddfd589b89c6f279cb6c68c5227e98762f7fb3af92241b7592151ddd70be7",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_3.png": "3659e3d034a0c1c5a8352da04c3e5d3106f5be6f301bf0cd375bf5b5dd275c31",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_4.png": "c44edb53e9829308b888978cf6165fd21bee79e01c50db837364e1882d8240e9",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_5.png": "8cb249662869e69e8cbacf23b511ce6a512aa0dca8be6d5b95f89488fb338e2f",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_6.png": "b2ddbc80df58e583e43f3497bb990116b77872cc44d645dc6a148893475d33fc",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_7.png": "518e2fb3a422522d8988469d80035130206e00c5e607c6d51ac3132be55f3af8",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_8.png": "0c907841ea5e07af4572d54541e51123c8a0037bf3fcedc9801248861e49bdc7",
        "data/nfl2k5_glyph_fixes_2026_b81u/ATL_01H0_digit_jersey_9.png": "22bb6b31501e2efc6b83c6f5d937a94843740ba2f34dc0110bfdb162f3dff130",
        "data/nfl2k5_glyph_fixes_2026_b81u/BAL_02H0_names.png": "7c92873ffa51961497ad79519d9f2da8928d379ca944c358d77cd4167e24dfef",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_0.png": "61e9da3ab8ce47fd9a890cc4d52a2c908f2879cb4e27d95c2354177c4dc4d85f",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_1.png": "0a8c6bc62019b01b4305aca62a58172d79f0e709653002851432f35e06e5a605",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_2.png": "507e919d33fcc7bca5a4c2f4219e7514d9ed1a6d80c5ec76bb908b790b4e7716",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_3.png": "93f2b2e0f069307bdfaeacde7aa57388132e4220b487e2861aad99b321dd4a07",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_4.png": "8d9e91694ea2669c851c6535d20be2bc2487ac4c7e5388bdf90a79e6d4d60b82",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_5.png": "2215d3a226d052e06af9edc28a50bcc37ae802100c9d7f35157a7365dc1c1003",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_6.png": "96c1c3442ecaf830eb8604e0eccda36adcd065c1a06f4be91c6d98fb72144ed7",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_7.png": "4e37e04eca4f20c1954807109455ab6ae73b72ed6733237a62367ca2db986566",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_8.png": "e8cfeb929dd6f7a02f5735caa2175384c4bad21e488cf72eb6e4bd907d7e73b3",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A0_digit_jersey_9.png": "53a00b7580e29273056eee83c9c80c57ea9de64aaef02ae01d9bcd8dc2d82d4a",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_0.png": "b5718082f98c797a7fa898206ba16d9cdebc90f7ded9882d95f83b68f7afba08",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_1.png": "274d448e230b332b23dd28a75e52c236d434232685f5a10641e2678188b2e1f7",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_2.png": "187a49149dc9258f8c7f561fea586c49c36649b35dddae7cd2ac0f2a767a225a",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_3.png": "e7fc4a827f9eb992ba0adb82a8ec6b1eed1bc3bf3cfc9dc165ba69e25423b805",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_4.png": "4570e803f941f61a5600791d73d6e2348b2eb1cf03c6e1f8b03c8d4b6e4a8072",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_5.png": "eb2ff73767c8178138119c077cd5b99d18684962b051e221672bb4434fd50e36",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_6.png": "c3988982ab65b2d64e9a5100f8c2a72a8802f5de4f2b727b5283ef0a927d2fed",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_7.png": "689be4f67880e1a0daac08742b14769dc19e89b154439316609e4a7fa6c438fb",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_8.png": "90d4382bddfcd3bf1abe18873f6055e10e94f8d68630d53f2b9af460a7aeb482",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06A6_digit_jersey_9.png": "bd30d6dc0aa9809b541a02cead224ba1c1be27512a6a6ca10dd498d01e45cca0",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_0.png": "d597388ea3e36cd969f07f5bf840061b807ba009300eb46ff96d834488b30bc0",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_1.png": "475d73a0255c53cd55db99932baeb9ab5d53f3e4d320e609eefe2f57a5116001",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_2.png": "e1c030b881a7a2567b3863d30d06240ea0c7a52274d9fc2f3c491c6184bf417d",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_3.png": "1c40d008a39c9bc4b4d8ac18776cba77073401264a35593dfcf4d8ed5b40e9dc",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_4.png": "c73e7f3f79f83cc3fe0636e1a0d73e9219ecfb377e88a8505e6062dc81fc8d95",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_5.png": "4d33a106f7b343d1c269ca9ed4242c174dbb2421db7d9a30056df8c4f284d8c4",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_6.png": "5323f273946798c07752e0ca5b2330bc602643a3ca983f84e1f7cf9669d7faa8",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_7.png": "1045f20f28d463c3d552b7cd8d5bc21921690c79f1c444046fbdd943b14a3436",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_8.png": "ab28eb6c42358ed32e908c22fd4f0832766f3c805199418069b23092d8da3a17",
        "data/nfl2k5_glyph_fixes_2026_b81u/CIN_06H0_digit_jersey_9.png": "805172b0bcb36e9292d0eda74161876aed5293ac60e5fda5d779c5711015109d",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_0.png": "d811b99e7142b289afe3ccc716ab39cc45ff81802019bba0b070d3e626bac629",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_1.png": "56df0f23cd6c171234730064ab81f2a51f9b46a7f684b5fa586120857c36dd8b",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_2.png": "464b3d5149ee34811e960f861af3848160453ba1e4575a12181d09d0247349f2",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_3.png": "ee55079d34dc6f48a2ac4b8c726941086d5c2f2bc8731c7b357492d059e0f708",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_4.png": "9bf40974431fee251f7091f25c5e96cdd493b0a9dbef528315f8ce7d18c9a314",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_5.png": "3f497bb274ca86f326109fc2129dcadaec79794ce1f744fc07d6c7754750f163",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_6.png": "c609bd48401e1aff62ceb934304a489dd6652087ec0accc3b497e5b6cbd6d6f3",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_7.png": "aa2fcc19f8cfe609de4440ee5e13391add769c4dcca3114504ef6fb660c69dba",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_8.png": "7d91d55792680c7991909973c766fe6cc11b6cfdfb9235d1391bd756e26c6c82",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_arm_9.png": "455aef8aeffb140a30134d22128ba93aab6432ee5387e8dd8d18788c49f35e33",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_digit_jersey_7.png": "81e47ed856f18a73ba4b44be7259e2c901397de65bc45b54ec061455b1bec086",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A0_names.png": "984e38cefdb74e6f2d3f2813bcc53f1c60ac682cb7b98a9fb0b262da4c6b80a4",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_0.png": "450db341a94e8228d430c07c699fa40225766ee58f7c2bdf0565c4bf30ce7a47",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_1.png": "4e24ceda5cc3b9cb94bc0d81e87edeab333034b8985172e525ed12b3d0746193",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_2.png": "7b306efe73ec733023f96a7ef9af5a410f43fca3c832e66b8c039beb48efc789",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_3.png": "6ce7667b12d9c9dce3a868232c5acf21fc7d27182c995b1f8dda580a2b02f106",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_4.png": "b58dc3aa7e3ee202f96f9992140ae687ac57be4f58d69c0aaf5c5519686823c9",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_5.png": "6fb0291e349cf454e8f88c30ba35f8c0645e9595e39ad0babe02e083500a0dfd",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_6.png": "bfb24f6ee20b705ce1d1c68768cdac8bfb40bb297dc084edb25810d2266a803a",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_7.png": "361f245dda513ec2e3d6bcf0ce56875c1ea2c3982c882e0e5de8911e178df671",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_8.png": "260ffbe835f6da1a225a862f5da61b0beda69d36069171abd6b8ebe6750c32f0",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A3_digit_arm_9.png": "7466584d3eb5e12b14da1661a95e78e7de2d390f748e3431d62ffc1752ce2b38",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30A4_names.png": "878203c70a53f773abe4d498d902aeb29c656506af095ef2c4e82d5c55957a3d",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_0.png": "a416d97958375a8d58174841ce26ac0788ee220ca938583ee46bc309d3f4c7cc",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_1.png": "1c31c3ed12ddcfb4131015e1427a2e01fd9041846a76ae61073933e583924279",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_2.png": "0d5139910d02c57d15a79d3de473295160d5ceb5b3c8f168a5c451da700e4d2e",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_3.png": "cbcc2a9307dd7bfc0002c60f75795b28138aa168bf62b3b829fe36487b1f3429",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_4.png": "a2617d53698860bf182316c98d3c827543fb5c45506fbc788b61c2341dd5b48a",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_5.png": "4be3802af88352c775ceeb3e05085022bddbc75c5f4a8fd7e36bdad15689e3e9",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_6.png": "68d2b9b76c47997ab2c6f8c95b09cb157add5ca6c49fa0815f01f0b3796ec6ff",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_7.png": "5d22200ac32961d1285576cdc46a507964ef5a6113fe5b7558407b9b6ea26b18",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_8.png": "8dd716f8547bacc55120b43e96dbcda118128897406dc6fdc773ae1f761bb01c",
        "data/nfl2k5_glyph_fixes_2026_b81u/CLE_30H0_digit_arm_9.png": "659c919ac0fe52f2d304c6199cfc288fe031a938fced3ac84e6fffa5770d941c",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_0.png": "087aafa95d4db334554c0278e1187c4bee8a9fb2c636aa62760467ff83b37d3c",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_1.png": "37614986b15c6728c5acce734fa965a0574d6b96122f02819b9e1c6b4047588c",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_2.png": "09b743810d97190e3b9b1f4f4f19485d9155f1e5bc6c2313bd65daf98518a7e3",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_3.png": "163d36e0f77a90e5a423767033dca1240fc9dbeb346fd262d00d71bc6bbaccef",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_4.png": "d9436b69d4b45ec3054fb09731d402ce40aba39d5eaf30d968e687d2e7abd91c",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_5.png": "61a56ec85ad07babb6d44edcf8f76cac74d5d30ce1371c5925d2be6688d043ed",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_6.png": "bf54b933cc35f87b6bcfdd1f0319b3b2f98918eb711bd0c09b1925565e4f064f",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_7.png": "efd37e6217f22d7bed9bff84440535010c156a4be7e772a50f2b4b7dc3e38ae2",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_8.png": "a603b160589c21a94b618c9367254ecdc8cf317f8f00113e120503b2c67a8ebb",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A0_digit_jersey_9.png": "87a8d19328352ba9988abc02247cfede3cee6d996dfc835d940ffa8a220dc213",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_0.png": "c159415c33b7b7d3d253e2aaa2b98825e6d9f4ca273cadd577c71b5cf97d7e41",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_1.png": "279a544b62f7df432f9dee042712b38b42400959b4d86889c2bd0169e5ab6251",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_2.png": "d138edc910eaa61115619e88fb84f30368633481bb2e980f7fc3349f7dad452b",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_3.png": "a15d7b1f29aa1fa87b5781de155629546b5d6242fcfb2c1896e799770e4b1140",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_4.png": "ca2395a59f2f36b93ea4ca365b586dbefc9eb9b3b344449424b260884911e992",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_5.png": "c0501aac463c1c3a73cb2320d537a12a33f56463ef729b1370be855602e6c52a",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_6.png": "2e81428478a173719d899dd2ee4bcc25c28fe3b4c685dc1f8f1f9ecf7926b79e",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_7.png": "128938dd3bc9717e41d13afc2c6ef23d7429e8a7d2ba8f1df89087e196d48c57",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_8.png": "ceee47ec4b11018a0a317794c7e1ab92a2a787acb9b5f0c826825ab22d46c616",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08A6_digit_jersey_9.png": "6ea4adbc3e5ea452b9ea24c7dedb4dde4d4c66525c5a6368eee70a2f84d128ed",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_0.png": "fc8c60726c927611deded784d6123f8f62e36d33b2e62c3cb600b02f638b0e8b",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_1.png": "2d8e36693d7263353d7ff8181409892f1afba809e47f6182b84714055f384484",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_2.png": "86615891f7f645e58758272cbcb86bd3c16344cd600ee53cdae9d04e9a6dd63e",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_3.png": "093eb921054c2d33bd8fd7937344bb3e6d6a0573f6564b90a7afcb6fb6c7c77f",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_4.png": "211d6f8726a27dc0ccaf59e7d83206ffdf377e4680096d30cc6046cc4ace527f",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_5.png": "df224577f908039be787545213c2cda549210846e99c02b417f58f5128cdbc4c",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_6.png": "699c970c8891be4f8a1fcd6b8f2bd375d4d25dc364de3695ae27d714408835a3",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_7.png": "ff5a7e7fa99d9111b4bf0dcc342d862575dfe8dbdc87a8afbe0a876efe2527bd",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_8.png": "8f1a65c76f9fa3c2e8fca5beeb5c07067f46f63a71aaf10faa271656f952b45e",
        "data/nfl2k5_glyph_fixes_2026_b81u/DEN_08H0_digit_jersey_9.png": "8c0988c9eeefb4d69e876c7706bad9c88ed51f6877ee49d94950b492f0f63bb3",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_0.png": "f90a52f074f8eabc78d24ef2fcc908358c1761d938783afa6d2e82a29b22728c",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_1.png": "22e360031f7b86a7d062e4211a3888e60e28cef6f89d114cae6743a92add0c50",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_2.png": "8982eba2316206eb3646bd92072ef4527fd35848e42df2c58c5ea514e3d9c309",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_3.png": "45977a8720abbfcc031582e0e974435bdc8ff72223ae03d4987ce409948c80c7",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_4.png": "83f897256eac0ee6224cdf76a9552e0d6cda1ccf4dca407cacb80a74fd1d29fa",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_5.png": "5464f2adfd2c239573c8baa4450c421b99c08d1b03834c3bb173f3513578b5e3",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_6.png": "4fcae551d99890b51b29ed6c759984af84819ca11da473c37e94550e998d1bb9",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_7.png": "e92b3c715797cf18b7103a4292f33af0c3ca3ccd53416628d368899a4d935de2",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_8.png": "d6b344c48be9fdab22c0ef42c677125b77a75b9edead0a35a52c4cd8db823ca3",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_arm_9.png": "fe2b01056596363b0d94903b61c50106b42833144a6e4b81f261b1d53c29edc9",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_0.png": "cb41b4bc2dee5bcbe3b99ea1b1baf358fd5675a17ce78cd59a850fdd67a29e8d",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_1.png": "5f90d02ee52de8451e7e533ed1cf79b3a5ae7f20a788854432e9a99b3ec65b21",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_2.png": "e280eb6b4732a86fbb0f85627b8f3e5be235f75400fa887c131a4605942c3fff",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_3.png": "fb9c1737a110128637bc11c9fb1db5ffd5832cda669d9eed417587c7889144d5",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_4.png": "b3d647bedfa451c1e30d9cfd5c942e59f63be452f21624591f6fbadcf9578eb4",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_5.png": "94315f0e8891a0524772e63324560b572ffcaa3be691baf2095e1b58ea101f78",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_6.png": "a333d402986396a7e87c94de6d40211343445d62026c7f065675c34e0f6913af",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_7.png": "6328121511c2e0cd5dcf890771b09c8d0efd95ae6d5e1e974bfe4649b57ebf99",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_8.png": "ed6227aec8297228d3aefba71fb064ccbbcde1f49797e4a7fb3e6159f364b48e",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A2_digit_jersey_9.png": "eca7b850edd4756b0806f69cee7e2f972bac1cd915aec37f38b40cda564eb830",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_0.png": "efa81f56a2e92cf563a3630e6d064533c4af84971474f54f8f6ca160789ff265",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_1.png": "aa0c44cc91698e05aa5b008e9f7e0e3dd6d1637a0c7bf94975f06952588d5789",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_2.png": "a62ff5c5fe04f8af05fb210a2db44beb91622d086e6b78a77543f5495fd99d74",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_3.png": "75f684ca4ff90e14c5c38dd44df87d4ec3fe6a5a34843cff79d7c8d70f57f33a",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_4.png": "1b52f6529fa25e26c8cfe50e890249db3c8e88064961da80e7a62a635dabc91e",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_5.png": "c1d6b4750b1f72185291aef4695a4398cb318f4c3fcce7c4462039465828935c",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_6.png": "8bd786a68260915a67236a8ca2500583b0317f12234bbee49c5bfaca9ccf7033",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_7.png": "3b403075cd67327b5f6e25aa0bce3e7a858ae0fd360efaae1bb8c27d71900bbb",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_8.png": "98d841237d395c4248b555fc57910452d034da9f43a66ce71e5a4ef892a77094",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09A9_digit_jersey_9.png": "455b8d996d1b7e555857c69c23c04c466668acbf4d55d0d60686e31cc8387839",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09H2_digit_arm_7.png": "e8aa701b948e5668cab133fce6dfd4566ebaeb77ad7d5e9d480e16363d7dcde8",
        "data/nfl2k5_glyph_fixes_2026_b81u/DET_09H2_digit_jersey_7.png": "a772a53be2788b16a985c59a95f68ad1f7f6c4d849dafa3f4462c9d0241bca18",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_0.png": "6f0f017ed10b02f39a8d3e2f00f506554b157b3f15fb2d837313047dce29cecc",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_1.png": "398afa1b21343d7b0180e7e050d298e2caccd3b356e636b96090c92eb5d875cc",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_2.png": "43b6f5e4a09e0e942290a67c768027daf2844882c93c7bab33d98a8fb044922b",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_3.png": "5a02d4159dc9e270d28adb164bd68625b35be538194146c841cb84f1686d4657",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_4.png": "c43db61ccd315cd4af7283fdf10231f5eebb03f1bcd232109f22d257b18b92f7",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_5.png": "797ba17c0e68f7ee3351f5735a0655d06b80d595bdf4271776ccef24361d4077",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_6.png": "b732288575d6ea488874bfb0695fbfbdbff7830989187c96d6eafd3604fb1ce0",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_7.png": "00f98a0b1543acda87258f45c8ee5aa49e70a6551b32191ac09124aa4752a75f",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_8.png": "487d7b0bd5631166e67a3393ca8d5175dbc5b3ebdbd6402642a9c232659abcb6",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A0_digit_jersey_9.png": "48d35cddad6dcf680a645a811d60f30a3fed300496d44282b0616602fde956a2",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_0.png": "427e465484f7f12fb4eb807a588b75cf1d8cc46679360e6a5588daddc0b23cab",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_1.png": "d0e72f7a06048799301019e025e25df5da9e586451a37419b9c1154bffd8264e",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_2.png": "8377e116db9adcef776b69465ab0d086117927333443a43242baadb854a94ef0",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_3.png": "e210ce7bedb46aa93cad556180370badef70ab0e943077dd5001b98b589996ca",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_4.png": "63b7269bafddf7cea2d5162c0bff515d8e5d2fc327cd8e247b240ea8cb523d9b",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_5.png": "12448842ec326ed63d94988e611f38f2c70085bbcfd860bec4ff31b8950c6509",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_6.png": "07b1be4e5ce446bcbc8250ceeef1abbf542ed287c9062c5357972cfe5d0aa94d",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_7.png": "2aad01d948d273ff2a60d48d75e4ccb26a7b04472888c57af46c29c228302e6e",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_8.png": "a71c12a0bd27758aa7e9a27efe687aab431c9a1ba0262ad7d614d91a3078eed4",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37A2_digit_jersey_9.png": "709d31acaecd6d25719201b361b1adeea9265aced2382ce9acc16f8872c97915",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_0.png": "356707bf751f14b5562ee63c609786b0dbd4a6e30ad2d730056eb611f61fc183",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_1.png": "9ca3b703130062fb82ed362f5c59883960f1870cf5c7279bb01845a87bea84e2",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_2.png": "58986bfe4953a90518ded7624a1cfe31cd5775c1d5e965571dd5e62c8956747c",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_3.png": "ededef44e83b31ab7a45373f782b3199ad7e797c36829a8a1dd2340f6fcc825e",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_4.png": "1e2c0eda0df750cdfe81cc94c081052d42570f3cfdd8c26797e7f75ff42a4e66",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_5.png": "2d8bb1543358c2233442e3ae01ed56b70a20c410073bd1dd82c2347c4cf868c5",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_6.png": "756a48146b244ab9d8c1e41454356babb338ab33fea0add0238ce97354348ed9",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_7.png": "e994f3f01511cdb6a43dc561894675f47b0faa274f472b0b4b145746583c9793",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_8.png": "0d7a07e20a2a72642aef817e8d987a390f6fa6a257dc1d526ae5c1fad52b9a9a",
        "data/nfl2k5_glyph_fixes_2026_b81u/HOU_37H0_digit_arm_9.png": "f3adf550497bf40962291275edc4fd05a1db57b77e256756d560c07fb1266f35",
        "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A0_names.png": "067984292236ef1c3ac36e33977586e874f4bb5f0ad8b940d613d1e7a91c9708",
        "data/nfl2k5_glyph_fixes_2026_b81u/IND_11A3_names.png": "18d1ebe9316a8d88bdbf5f55c1fcc6f673a8c3c02ba23ff5e3ce117cf81a1260",
        "data/nfl2k5_glyph_fixes_2026_b81u/JAX_12H0_names.png": "d143fe34ceca0e3cd387b6fd8774bcbb217947738d448566a4a7ae1360d85bcf",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_0.png": "c7e9c2ad6f6627e218ac20b7a48eda7e399024f0bf69503eadffaf26313c377d",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_1.png": "f0bc47f43dfd489a4cc395949d54b22649da075b0252ccd1c63007ad36eb1430",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_2.png": "e3c85317a9e7b68ed1dd23f3550a4f9e37dcbf83ee5fe25e7a792dee31657894",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_3.png": "ba1ef3c3f52b55b54442f7c21624bbe022643588b0ff33ec426284bb85595505",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_4.png": "3a8073698f9386db6ed665bd10c48992b8a4b0ed5675370032e54f2d26328307",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_5.png": "640f61c426a28285f80a4e461e125a30bd861df3030419e36bc9ed63d87da9d2",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_6.png": "df2f8e75d7fd710b6549fa71616337bfcb3ea40c73c83bb76a70592d94c0fecc",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_7.png": "174da3383a812e8863bf3af06a2624c580fe08b8ccbd0789bb8c2889d060a096",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_8.png": "816cd56c016040df21b91d0672a9aade28267ed5bc9487b6934993f8c318b122",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A0_digit_jersey_9.png": "e49547aa7122169d2279cb5d1851029c78d4fbf9c5e2888a38b6d748c21f44cd",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_0.png": "30e5f82f6f66acb8a2750217bdf0d892d55e004e87146dde2976d97d8643d57d",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_1.png": "4e857a7bc4e95fab93de87f7eeaa5dc2f6781ff02c65647b74410a7ba32ecb66",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_2.png": "e970b7c8dc23dd2fff48ba660d11a76097a21b280bb1f89183abec45023e2ecc",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_3.png": "d7489b7fb45398bce4e291762fe3a5eda324aac67e4005e8e25956cd2ea93131",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_4.png": "8b4bceb268da3adac44458fd8a8084091f0bf5e0f1ba99975fb4f636857c4c65",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_5.png": "440b380bf807c9305404816725a73473b825eafebd6c75aab67fb09d807dd9b4",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_6.png": "aa31841208f13c29a35cd814a8e6c0111305c08fd36d60ff0978072228ea13f0",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_7.png": "3ef47d4cddf8711ace37a71e0f9e7e2496b159f325962ddc6ca3a0f6fe2591a2",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_8.png": "8ae02d7d511e1d947a54fdd50067d3f12b500043351db6afba84514a5fb855b0",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A11_digit_jersey_9.png": "a025cdc1426d68e0f3111dec784c9a0071131711c4776046a4eeea27e9e388dd",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_0.png": "04d33386eba32921c5128dc22ab7d092809f8d20d3368e34cc07c85e7745a865",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_1.png": "ba003fc0d1211593809df3ee979bb383b6ad7919e0895a9329ab03ba074c6cc9",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_2.png": "e0c718124b172600aaf604ee69d88953899acbdc278a1f0a191d3f189a7374f8",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_3.png": "040b2ca0f6dabfa1c16b4fc887b55eb36a6a651d05281b9304ed5f0d57f9dc59",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_4.png": "81b9cc4a49734b3a3e9ac404f2babf263119835f4a3e3bf1203ae7bcddb76736",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_5.png": "5db922ee79541c352726fb1fac961281f2b46fc6bb249d2455e657497e46d0fe",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_6.png": "688d76dfc90cd8e495bc476394c427cef2159e5f041ec816dc5c05799ea1e635",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_7.png": "ca1da35bbf9f4c504f93eae4a63f0f50a3c1e4cef660039fe823d28fc0afeb5f",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_8.png": "7470db6e31a5d7bf0a4646f1d7a6aa3ff81b48ef5d9545ce8b562a1d9d318fe9",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAC_24A9_digit_jersey_9.png": "0076e6280cdaffc7aa2bd3847312c9a498f4447af36f089e7b5f9aca9e90d0a4",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_0.png": "b745bf3e187db7a8ee0218394c169c6f47fee649444ab91b056d6ffed25a85f1",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_1.png": "b6d9485d036b614e1f8e5bc647d5acb3cc51fea843bbd393574357e8390a8ad5",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_2.png": "0f4b4a17970cb683f02ec44024ae0336ce021f8758173ac4e7280b3e197b7c7c",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_3.png": "244396e1ceae798f82719b280abafe606ca94e4c2d43483b5aa7dd3f4af8960e",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_4.png": "41a351809a1e58feb3c1628dac78054f2d8bd016dd9aa76add548754de10dd9b",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_5.png": "878e06f4cbe30d9e0068dc5c03eae3a81ebe38e6560cc2cd9edc7d582dad7466",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_6.png": "2a114c64ce213d6335eb025c426503fa52e386fd0fb279fd65e2349389b29ea3",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_7.png": "f0bce44ad4f7c2dd835cc00a2fb7745292695baa37a18c926b572c47865ad37b",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_8.png": "ee61670689d5a6ab91cc54c81951b4e991edada28e22f9662670d24abd9fdc5a",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23A0_digit_jersey_9.png": "eacd48b39ff514c6cc36ad47fbec8c6f15d68bf17166ac8c81b75ee262760ff1",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_0.png": "f6dfc0659b04bf1321d5349d450351d4a703d2eb2bc94db4a0b06bb5d9cdc06c",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_1.png": "9878e2094173792e57936a6c07d2bd0a094e1c674be1bf495e2540074629c8d9",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_2.png": "005011530c34aab6a99d125c1a4cd2d0203e092bdcedefe61ff45d0e6182d781",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_3.png": "8f8049059f43fd7440fbf5cb0cfeaa073791c56e2b6fe9efbfe5b0927922823d",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_4.png": "aa1b5e9ca147ceb36a8d779499ee2a6d9bfe5f8a693a845ed2a7295b58c6b9a5",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_5.png": "ed09c31bc5420d2d5589bdd12e89681fc0988668245ad5aeb58e4bb81b7627d9",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_6.png": "f411b5b6edff08c8ef0ca57fa0bbee4d99eeac2131e5994ba9a02b63b258591f",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_7.png": "1a65c061bfe4d2a8d162d4f2b95a44fa364bc050a2023d707b8aa04de611c477",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_8.png": "2ec43fa6f2154312e867c07b3da30b6b016ad3d3f00a3594cb236a1c4dc6234c",
        "data/nfl2k5_glyph_fixes_2026_b81u/LAR_23H0_digit_jersey_9.png": "328646455fb499e693005c36654b9ba0f850525a97465f1c01084d99ac8cb9ff",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_0.png": "df30c08289246a6e105082d0ff92dd64296dc942b2839dde9ac85347ac55f0b3",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_1.png": "582fda688af42947136b2f28c736557372a225db64317ae07d1413d7e1765f4a",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_2.png": "676940567e5f2966d1d0963f6e57b26e961acd6c0b6ea80ebd49cad5de9b0b62",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_3.png": "72850693bccdf09040724524cde133f7a85f06b4368fa47fa33e8e326a1f60d5",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_4.png": "65f7f8b602fa538acd678b524d717aa4042c54f6b60418e8af9adcc0c33c3a52",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_5.png": "052710e271f82e248fd40534423de2550dcabf2e142d8b425a0b2c7a1d40e416",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_6.png": "529f4a9b0671ed57defe64db2f9c1222df73b7bdbcf3a0795a8a4ce39508dcc7",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_7.png": "c33c20fc31071d7adb4deb92d9bae973926dc48d47ed3de5e04193eb3d2224ec",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_8.png": "99159e9f8692cec8c14d20b242f36a163633bec6666802db9cfe47e765088889",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A0_digit_arm_9.png": "05bace00b1bf59690dfd09266a03c2b0b81f8df15cc81edb2da2f0cf4e606942",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_0.png": "79c27fcac02295e0d9b6e12c64084d8aa96834fc29cc73f4a8571ef7d270a741",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_1.png": "d33f93cd409003d5491a201b71805571bc0e119c65e94885a53ff50c366bef5b",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_2.png": "c36498e49d7325c7d8287f1e4ce7c11fd431920b2bf7f7e3b429077f3ca7b825",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_3.png": "6d738c37655dd9687ac92d1e6417215a1bd7a9e5e9108bebd3b4c0d93e07e540",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_4.png": "528b34b0ddeeb3f63177294b8147f30a01dc03f9655feaf6363bf818e6b962d6",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_5.png": "f3b2932a9cb8bc49e2ddb2fbdfeffbe2d5f18594921da7c5b9f1c34f5979fe9d",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_6.png": "870c3fbd0e8ae2fc77e4b4737957152a17f0d2aa250d10f07712e606a2a1e1f6",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_7.png": "3f6d2536d47e67e58e13dbec013b9a6b09fae12ce467747abe58325aaea399bd",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_8.png": "e180371cf9055760753377f678f4e7e3f6064fb982c85843825803c3959f92a2",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_arm_9.png": "209ecd834a389f6affe39069fcc6dcc0ba535681c19435b120f2a84285f72739",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_0.png": "798047099ea9567df15357d59ea49b170f2a6d10416226905ddb58b92dc22593",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_1.png": "7b2afd39c1c5001ff380de7f919dbe33854a9fdc39b1ef91a79008138b01d144",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_2.png": "fb0993ae0f4fdb2a3a970208156dfcc89bc2353a94cebe356735567e6ec3ac6f",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_3.png": "727f18bc633ad1c4e5a00c6487375eb98640eb93bfa58ee6eca34d3eb5da7741",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_4.png": "78f30b94836db615dbe4ec0177959db094b651e71be0342921feaaa0297e41c1",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_5.png": "9993b755f53a1ac61960721c0bd9474bdf39882b397b487ef61dd8539e70b38f",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_6.png": "583faedd0ac7b6279427c94c56045404812986ab2cebdc81ad68c1869ed40875",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_7.png": "30f2f2f5a6bc77ef5caab74b5891effcb5e7681b08899e0feb2086889b4ee8fc",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_8.png": "01c9f06ea6e706d6a7360464fd3871d727e9f2829b58fd91742c41767ab36d99",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14A10_digit_jersey_9.png": "1f4a7e4f109abdbd4b9f6e3f75431ed4961512937c80b49ac95dd1f7a948674d",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_0.png": "99cfa85fa74913c9f36306e1479cb7058d16c5cc188102c5105250b8a3ef66c4",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_1.png": "1caf83398bf8e49574792a3ef76b1a03b2144a8bbbfcd1550caeed5a47a22b87",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_2.png": "b455dc62952803db1df4a401ddb00bb2fb7bd5ffa7ca2e65742c4c336e721be2",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_3.png": "ff4ccfe390b84081a52a690187c4438654c5614116f45004dddba3bf1c0b7cdf",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_4.png": "f42b979abd993139887fac033415ba94e46d151c6ae136d068802e7603e255b5",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_5.png": "b0c26390b23dd258dfacb58ac012f067ed9a0268021c3e9e307b4095db7cf38d",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_6.png": "e4c468be954bccf283227858c37455e1f9ae4aded723c54a4f2075e907809c20",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_7.png": "754f8ee1b7fa4ce4ca1fc74a26d9ca7b0919472dee584a538608551ebf8bf653",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_8.png": "0996e6a6174a93a955a6b53fa55bbfcf3a7438b052557b82abf7dce235b4bb31",
        "data/nfl2k5_glyph_fixes_2026_b81u/MIA_14H0_digit_arm_9.png": "d3bae739e0900d2174aa75a1815f75c9ae85fbfab7b18e6e0cda049fdc2a91c4",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_0.png": "14d7bc9ce2ea84c8274f883b9bf3df7dce7d0dfca44c65c1c11edb81b5ad3de0",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_1.png": "84c16129ffa3dd301bb4a68ef1f05929d68366e2cbc6ea354ad58e9346203827",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_2.png": "6a63705c0dcc114305620b11b55cc28a1d617a68826c986f7588adb4306cf35e",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_3.png": "28af6973adb17015e752a575428959703d01d1afdda7dcec3d9940067f3da860",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_4.png": "749b78896bff567c55b52ae43ba4b926795bb379e5077c54756c6352b76b4f50",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_5.png": "07a45a13455ba19e7d663eacbdd87ce9fafe74261e883a2a55362589c804a3bb",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_6.png": "cd505b51852c91e35cdb71778b65330c3037ddb64a429723515d1a4ffaf66639",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_7.png": "34f8248e262c4ea3d8874fcdeb9f7d71762e39f899ef9c5b03983578a650bedf",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_8.png": "07e3e0203bbf73b75875ed36daef65ad62ceb272f3551d74e5cf225c3a77bb3d",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16A0_digit_jersey_9.png": "e4850068561851c9d088231c9dcabe4b1e1500a38321256a0a052bfca4002ed8",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_0.png": "9221970ed7e83c00c7421d0114de9ed4fe70c3b4db51cd2fc63c1dd0c9dce112",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_1.png": "6169a54d73b6b63a555cb50b48dd668b2e8469cd12903f44f75b52750809df03",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_2.png": "7814d5955592bac35b85edb8c962a469e500bd24bde2917e0d3fda5a851142bf",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_3.png": "6e36e970cefe6520cc8e8932627e0314ddd13c30e6354ae03cb5a3a0a2dc4b53",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_4.png": "38c6f937ed0194d60fb47a73632b206b6de3bb66ebf9464936b03eba620f2346",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_5.png": "5d863be30d5ac25da79ccce5525a8f6a6f1f6b640acbb9ec9f94c8eab9c3414b",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_6.png": "cb9899775442c027c9b93d7e93cfb94a828d9d4284f72d537d2a2fbeae1156eb",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_7.png": "8e536f6829a6a0d526df94191c8d45886932685fbf8ef19215df19e26a6918e7",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_8.png": "8eafecc103bccdc8eae30914dcbd2407b05211f718f41dcccf8a22f48630cfff",
        "data/nfl2k5_glyph_fixes_2026_b81u/NE_16H0_digit_jersey_9.png": "e75452eb6951aae52b7bc894efdee112bf105534f98a42d9b4a22a03d8e35887",
        "data/nfl2k5_glyph_fixes_2026_b81u/NO_17A1_names.png": "b654602b173cb9cfbd30c29abcf77e7382e1d071f19073b7f2204a0b25bd8010",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYG_18A7_names.png": "abaf4243785a5f6f0b715323e91f713c118120c79dee39f9afe325f5a568c2a6",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_arm_2.png": "d0fed3bb15c042590817430138497a70df7ace7c56163d32044afcf503ad2fef",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_digit_jersey_2.png": "8e472e5e68e0aefbff4aff04c3e75cb3439d9e40af6a8ae3e7ba797308954ff5",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A0_names.png": "a076b14e9f2a5c4c80124083477c1b176c58e6168d77a95e4bbc766586b86986",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A2_digit_arm_2.png": "30b5d5c522f0c98bd5a08fc32e77f1b6fd73597bdcb9ad22523b03ce4debac3d",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19A7_digit_arm_2.png": "4f028b55a539218e791db196e5e96b89f183f24a1336f83e220f2db61f0da4c5",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_arm_2.png": "bd2db48b4fee62302330357d048cedb586a12d8b647ccfd8d140bf93c9884f2f",
        "data/nfl2k5_glyph_fixes_2026_b81u/NYJ_19H0_digit_jersey_2.png": "65bbaf358df77e73d73665ff23c3783a74af3d57c0b7c868265cf7245de5402f",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_0.png": "d8052fc3c0cf0843fb217986b0aa8a279a7dae73161079bf6441c48efe8bcec0",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_1.png": "8f6ed15ccb5471d732cb41fc07cc18db05d10c56d3bcee3e4b5e66d8b78a93a7",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_2.png": "f724bca72f4fbd1793b56131570540e86d64a80e8957aa25f9ab877ae6a957c7",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_3.png": "26898b22a69f5a620b5d1e54cd5c48525255395acdbddfa4b0a07936ef6096e3",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_4.png": "8308fb922965d82261c3b1621b56307be3dd1e6ccf75982ad55345fbc8f90e7d",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_5.png": "bc9c451d71b966df65cd766d2c621ee1e7a383e05fb301464e4b208303819d6a",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_6.png": "46512c10e320ae191b0eaadea422e856e9b84456acfc738f9a4c4b9e3ccf52df",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_7.png": "198610b383d437df4217486df069d35bc53b98ad67ecb28445a03172e636b7d4",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_8.png": "905fc164624b7f43d88ab5fca9b332e5fe58e5c2fe5475a0b4c8e17518695cd9",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_arm_9.png": "7c6e79163b93f9a98d13bd88d5d3307ef5a8647d3bb242e19b403091e0fc5351",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26A4_digit_jersey_2.png": "83ceb532e12991ffa1dcf5f4a18514a3f28bb9c8bf85c7dae45c9ff2c6372c1a",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_0.png": "5522da470f2f4dccc70ddc2d25c3caa1149cbdfc628cca43f385fde77f846046",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_1.png": "2858a2994c4b1913722aa54eba83c439d5b066d68d1ad4e3071759a22461b454",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_2.png": "e3755591b979848e81213048475056bde74659218ef9c42c9c4e1df77eb7295f",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_3.png": "e81fed2a5ee6e8dfeaac10efc0e98bfed082888101ae2d38060fbb5022426a24",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_4.png": "784dcd24db3181bc389f155b598122c8a2e18155a29359dd322ec1b83b35c03f",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_5.png": "1c3c86a7ee9fda8ed58f184446db0b43bf1b82ff897207e4b725dad1512dd23a",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_6.png": "ac2de5f689909a731cc6f3d857f95df3e35ea3d0339f13227052b544f3e45432",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_7.png": "a809e73126f928a52c2fd38da40e97a2b23707c6f88dc3d6f8ec100a2cc1ae3e",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_8.png": "697e998527e61adac578b5e307902e403e2703bb8fe6a7a9b0f8e578568c6fb8",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_arm_9.png": "ce5afdb2cd5487bba8a50b46136573987e6e7eca50fec522d2b26d5f93490aa2",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_0.png": "083c88a07c7e3dc3bac301d6832b83a54834ad4cd1600a6e8007a2a483eb03ee",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_1.png": "ce37992056399981e2592c3f63a400360d23ded3dda420dd76055489764c1b35",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_2.png": "d8529485d373855b105f693bdb295e98f8d86f256ea87e242371305c89155879",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_3.png": "425f789068362904e8dd5aebbba7d6bb63dc76b104ca3f18eea703b8667dc187",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_4.png": "c104c1bf9cd5b1d83650e1a7805817c97289d63cb4d737158aff8a0eea5127e7",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_5.png": "817ea382ab901864c9110fffd4b97784d01d2e2009774b98d902205d936ef1a8",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_6.png": "55fc9f0b1c3f5352171c52c073ba320a1aa528681e1d5b1da4ee1607298bb4e5",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_7.png": "59744929167340b0595a2a14b97f9c63232170a7d10e8e15b6e63defdb64acdb",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_8.png": "70fa0e77275476d2e70c4e03020d57cb1b5d2ea23b15d4de8f08ab41b4c5c7c1",
        "data/nfl2k5_glyph_fixes_2026_b81u/SEA_26H4_digit_jersey_9.png": "9223e1b060917d1157298f098815af7d63feee1ce589a2b2330044e1c49c3473",
        "data/nfl2k5_glyph_fixes_2026_b81u/TB_27A0_names.png": "3865b3c9a807267820d78b99a297046baaf10581e0d64e1cfdfa5f821aafc139",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_0.png": "6aa01acc5a56e677cdbcdc72da1b28ea516c97e1a9ced5d245702016edf8ebb7",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_1.png": "64fd06af6bb93bc40b7df2bb5fd1054b9944e7c0ae25be42f1eadab0d8ad94d1",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_2.png": "94af7fef0df5af8927e649ff0cad3cdeb9eed269fe668c1d32f9203cad2f6bc2",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_3.png": "c8c0247de22449de33370d03979984b72bf14633ce771b6824d29dd4c8476135",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_4.png": "6940c97d59e6afbc359cb3b5160450884d9f5b473ccf522a76b2ef9dbd80bcad",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_5.png": "1714febcf1e12de93c7deb92f2c1314077d41e46a12a0325261b6b45033317ad",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_6.png": "3c24484eaee1593bd3816fb7b3b6b92d84ac5a06c12bd705d7881dd934f41c1b",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_7.png": "05f6edd7aa8ac85aa00a958f4103eac28cfe7e04871cd7c9ffbe07e11eabde83",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_8.png": "82a45cb22b7d7da34afeacc1497ee048ce170325b878ceb3f89d9e18a7e24c5a",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_arm_9.png": "7ada4d852ee5b84106294425387973457f13cc02311802e0a2a05478798353d3",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_0.png": "a2d641093d145247f216de24083b7d1438dc871ed27dd577e9181c042c043914",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_1.png": "83a530465269c88986635f3e7ee0713332148ad16094628d299b952f9f70f9b4",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_2.png": "e1aad4fad0034f4e42c14d16add8f09b5626bf9a47b49b489456ee5ef45cc4dd",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_3.png": "8742d99fb28cdb9a73be8c26a46175d95572c5ef08a2ff75874f94cc8036422e",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_4.png": "1d1fa9e4d5bc779add22fdb6730a570787ba54ce29e8a9efe025920a891aea63",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_5.png": "ab86fb70d41064d0c01a74a491b4116def644e5d65bbef6593ab0dbde424afde",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_6.png": "c13bf9cddb161ab75bdbfa1375969d55b8ea0acc370b34db63c40eaa4da01ed4",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_7.png": "34fc69d02c88c01d0d63d01821885e4e8ce5387e44378169ff72166c596dc87f",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_8.png": "5c1385b458f26e11bc5d04bf9884ca1936f74fbe42144c0a0f7a03c4fdeb93ec",
        "data/nfl2k5_glyph_fixes_2026_b81u/TEN_28A7_digit_jersey_9.png": "c75073a37930a06be156832835ba4c8bf6821a5cb4342f3514b288d40c316add",
        "data/nfl2k5_kit_fixes_2026_b81.json": "d2a9e3239050947bc69a4ade58491b3578e3859d841831749dfd163ef24d2da7",
        "data/nfl2k5_kit_fixes_2026_b81u.json": "1e803b7ebfeacba800301482c105a4a50354f20bd63e10606efca1a4f349930e",
        "data/nfl2k5_sideline_2026_b81u.json": "99467fc250d25538123b89f2cc9280d7c2b9589d612eeaea1ca92463d7c7e9b3",
        "data/nfl2k5_relief_2026_b81u.json": "e7bf44e4360bb5a34a198937abb9b3df74d2dc1bb478bc65e966bc39384b6372",
        "data/nfl2k5_relief_2026_b81u/difference_jersey.png": "f4d24e2c69457b2b08c9ffb9fd9e3c023bea9d41e342842907b8286323f28387",
        "data/nfl2k5_relief_2026_b81u/difference_sleeve.png": "31bb10e5979ee53b022816f1311b4d53d949c606d888186ac85103104b1a7983",
        "data/nfl2k5_relief_2026_b81u/jersey_08692d8525216e39.png": "83de69541844bb9855916ae0c42cd42c006832a7df90d14a94b29a9e4c9fd8a4",
        "data/nfl2k5_relief_2026_b81u/jersey_0ba7a3e6d1c29068.png": "fd95bef1d517f2ba2050407639c5f27c37cac2293f55044a43ee2af9d6a3355f",
        "data/nfl2k5_relief_2026_b81u/jersey_0d21204f5c3849c3.png": "059ac18032b4ed3ab18afc57be8c554e0125c18ad61a16c4e0c6ea53eb455532",
        "data/nfl2k5_relief_2026_b81u/jersey_0eb216a3513e479a.png": "2c8157e254fde93a00e603391267515589d655989961f008c1e0a61c55566cbd",
        "data/nfl2k5_relief_2026_b81u/jersey_12de006ac81dc5c6.png": "77446def5f08837e66fd46ed189c761971eca60ed9da018fd359b385eb57c2b6",
        "data/nfl2k5_relief_2026_b81u/jersey_131b6886dc0f5f18.png": "1ebdc48fc64cb73c7acb8bd40df15133a02248e2ee3d95e59ce92db247ccedf8",
        "data/nfl2k5_relief_2026_b81u/jersey_140fb7b1f9f97f4d.png": "cf9671b82ab24153d1e39e5f25d6b721790f8ad22326142e7936236c7daa7c07",
        "data/nfl2k5_relief_2026_b81u/jersey_14e5040f10a441ef.png": "be07a96ee806e048cec7663b6078c7d18c41504579041b7eda7ef8d2182f5e32",
        "data/nfl2k5_relief_2026_b81u/jersey_1678f894fb8eee04.png": "1fd33565a5cebb7b3c417f7a89e225136454d6fdc57045c23dd081e54b944e9b",
        "data/nfl2k5_relief_2026_b81u/jersey_16826bc7e52e00a4.png": "4ca77721612f2103e2ddf4183f5b63c16a1e80c2168c8a8357605c7e60580d22",
        "data/nfl2k5_relief_2026_b81u/jersey_18516cd4b1a96ca6.png": "2089b8550fa77fe11a7e44c5969924e99a368052a13f371eebb73578f74460dd",
        "data/nfl2k5_relief_2026_b81u/jersey_18989c0dacb5150c.png": "b56d09a20b7512d91aa8af2d67535e31635e0c9b37a4f03651d8d316730c27ce",
        "data/nfl2k5_relief_2026_b81u/jersey_19b9ed41c01633f8.png": "fefb8748276e57e2dcf56197a26dad1d7888bd650d0e8e716e2818c0bfd8a3ff",
        "data/nfl2k5_relief_2026_b81u/jersey_1ef55d30f6acf6d9.png": "74acaaf643fadf7702f967c636cb10824b8e193fb1fbd3a0fd29a02e2956ada4",
        "data/nfl2k5_relief_2026_b81u/jersey_22b824c01d021eab.png": "0f71596d2c4225c48476e1e89a47e55901436c39bb4db9327cfc7ba9bb5097f7",
        "data/nfl2k5_relief_2026_b81u/jersey_244f0201ac6384be.png": "351249e2cc40ad7f432e314a09122f4497d7ec5c281b0c1ca5a3cb615a6ab3c6",
        "data/nfl2k5_relief_2026_b81u/jersey_2d8277456186c227.png": "7d26087b034f775dd9489c9a83ecef50361bdd38d02f1d16e00a5f10712ee243",
        "data/nfl2k5_relief_2026_b81u/jersey_320adf1f2d864ca9.png": "ae0c58584b531f3f00fe8a5235664a02319614a5f52933f506a9d88f24d365e2",
        "data/nfl2k5_relief_2026_b81u/jersey_35bd82ac1b9b62a0.png": "a89e443e79900a70b6ea27eba6a4ae01bedffe2356d17a00aaa0f1829738f99d",
        "data/nfl2k5_relief_2026_b81u/jersey_384e4b887440dff4.png": "a01809417fe1942df7ce76a9587d3b462ef4c02ab4d9e04e2da6bafe316788ed",
        "data/nfl2k5_relief_2026_b81u/jersey_3948f848caecb780.png": "3d575cdfa6c145cd8b48ae15bc45c7e6f2b126eec2421025353d18616104803c",
        "data/nfl2k5_relief_2026_b81u/jersey_3e22a07846126ecd.png": "16344fd6160801b49cb4e24f29d4984175242b6824b531205c8c816a82ce3fc8",
        "data/nfl2k5_relief_2026_b81u/jersey_3e713ba1b55e838d.png": "6e6cbdc2dbc0374c877b473de87d13a8f5b0cba2eca6dddc2f6ce0b3cd34474a",
        "data/nfl2k5_relief_2026_b81u/jersey_461ac369e3dcb21c.png": "53500bb36fa3e4abc2fa09465e86fef8434f8a0519b2c07c5c5dc65c327795cd",
        "data/nfl2k5_relief_2026_b81u/jersey_4726bbd20e019079.png": "8520f633dbc33e55e42ad1177eee8f6ac13f00c74ecf3dbe32f93126e01e0182",
        "data/nfl2k5_relief_2026_b81u/jersey_4c6cd8beee2e6267.png": "05238b3d5542e2601ec9207fb3ca1544e4be7aa0e1b322120a3aeafabc134ead",
        "data/nfl2k5_relief_2026_b81u/jersey_4dce2a9c3ecb966d.png": "f8817b1e8401ac750d35f1970d26b426fea597fb34a5e279c9117048a48e315e",
        "data/nfl2k5_relief_2026_b81u/jersey_5082c749b41055eb.png": "77874c83d059678ccad5c5aedd3c6b668c3ddcce76b3e411d72d8621ff62cced",
        "data/nfl2k5_relief_2026_b81u/jersey_595e1efe763da2ca.png": "829f12e137102e83ce4b50755b89797c7ddbd03dab1a22205ad1acb367419496",
        "data/nfl2k5_relief_2026_b81u/jersey_5e48e191aea80550.png": "b4737607b7e543e476fa79c1113463a83af2e8f016030ab980f4ee35ee71409d",
        "data/nfl2k5_relief_2026_b81u/jersey_6ca7bb7f91efbbb8.png": "5522d3f54f7ea5ae7eff696f4f15158eb9aed1486c486262c9c355d171f31c2b",
        "data/nfl2k5_relief_2026_b81u/jersey_6d0cdd7cec29664f.png": "e6c6659617d28f0b0fd8c93c29eabbcbace996b3752cbdab3b634250e59a473f",
        "data/nfl2k5_relief_2026_b81u/jersey_736cc9431ce86755.png": "b2492704215af0af65266a34670f2a89e0b93b07169d495977a054bc213630a3",
        "data/nfl2k5_relief_2026_b81u/jersey_77e4974464b42d48.png": "2d3cfff639cf4d93e381338d65d001eabc3acc3d3720d503c054730226f36448",
        "data/nfl2k5_relief_2026_b81u/jersey_7b41ddd869297400.png": "a760fec25172752548bce8e802b3b47d51f198fbb0ff9a697abc94fbd7464ac3",
        "data/nfl2k5_relief_2026_b81u/jersey_82a495e1861f6c8a.png": "547c1c7db0047dc90a1bdcbb48c60cc98e120b8c2cd542562abbed4abc7ff3b2",
        "data/nfl2k5_relief_2026_b81u/jersey_8c564671b7b541b8.png": "7c1dd45aa94b4fde006a06d9b082242cc10aaa28b3af522e694dd1248184ae61",
        "data/nfl2k5_relief_2026_b81u/jersey_92d27871d7a6867f.png": "ec83d1bd95dcdd1fe22d85de030d7e9283b0b15fbc076672473ef3be2e7e7513",
        "data/nfl2k5_relief_2026_b81u/jersey_9790a6c43112c18d.png": "9e928b1ecdad1affa3dd6f7d10688515ca855a3c108dde0afff6de48b09f4a90",
        "data/nfl2k5_relief_2026_b81u/jersey_9dcaf7ebd3674e85.png": "95318cf2429790141183eb45e63a6147b1cbf5347a1e2a312bb4571bd0f9c203",
        "data/nfl2k5_relief_2026_b81u/jersey_9ee009193f88bcc6.png": "3c14fce3c86c40c3e41741b0a4587afef08906ab50f1aa2f4cb723ed65b74bb8",
        "data/nfl2k5_relief_2026_b81u/jersey_a561ebc9412ab5c1.png": "ff46ef835507321526696244236511123ac9a51ab753098267f1463c6676a260",
        "data/nfl2k5_relief_2026_b81u/jersey_a8fb9eeecb09fdb5.png": "6a1c2b59b0ef51b7fdc18066e95240745e03f95f0d2df618ff2f1b1f0d7a4858",
        "data/nfl2k5_relief_2026_b81u/jersey_ab25a27ee05818f1.png": "0aa67a0e142389c8caa227966e283dd29cccf9dd80fd440eef24c41f9026eae9",
        "data/nfl2k5_relief_2026_b81u/jersey_ad5fb03606e3394d.png": "e4e6b213d386b8779c1f8e2da64c37e6775363644ad9f3a2d7845323ed0e9b00",
        "data/nfl2k5_relief_2026_b81u/jersey_ad9fc377a2f57258.png": "fe3ce300bd2761325b6986fdfbba32a1f3a6d0d298023707e887d76bde6b5f6b",
        "data/nfl2k5_relief_2026_b81u/jersey_af59448ec91c9f16.png": "35dc1a939225bdb5690c12eb986e5f894eac481b6229b43c1b43ca20750c4768",
        "data/nfl2k5_relief_2026_b81u/jersey_b042398fa43cb6a2.png": "7dd5eb9a90c6e1240c6c0c6fdbfb8be2a7cf8ca21ff2845735fe56dea96f0593",
        "data/nfl2k5_relief_2026_b81u/jersey_b053e944ef9dd7af.png": "e6f9b5599564821ae38cd991b5585fb8a41712528145074a23bd4b444fe54432",
        "data/nfl2k5_relief_2026_b81u/jersey_b9c3cc83469e54c3.png": "dec1279b3e1755ce13218ac94351b79c33cb2e065a9e5032b417b6bb3788d616",
        "data/nfl2k5_relief_2026_b81u/jersey_bf5eea286cc8b60f.png": "2d5c7942a50c0230b793a80b3cef82dfdc227e900d7ff23d672431d12fec3123",
        "data/nfl2k5_relief_2026_b81u/jersey_bf95f005f2aae3fa.png": "ec93099d2ac9918237b7b31cd500586dea6baabaa1c440746aac6a4d5bb73d78",
        "data/nfl2k5_relief_2026_b81u/jersey_c3b21bf558b898b7.png": "8416e71b9c8535249cc759da50208439aa7057fc5bed759b2d4fcaee9cfde094",
        "data/nfl2k5_relief_2026_b81u/jersey_c3bf78e3a90dcf07.png": "89183644624e5cef53628c26d0e4373b813fe377684973e312caca443d483098",
        "data/nfl2k5_relief_2026_b81u/jersey_cab3c2d38af44be7.png": "649fade05c6ada8926273c39b766c11de91f0ced09dff53c7ca3188c448e8e7d",
        "data/nfl2k5_relief_2026_b81u/jersey_cda2033cea659c2d.png": "5ddf74cf733b2a3dc6c171094997797ff5e0763c6f0614aa18dbba4f26b0e3ee",
        "data/nfl2k5_relief_2026_b81u/jersey_ce2801115170ec67.png": "55d49c4e1d9daacc723109137cac0fd31052e4ccf656a64efe10da64ee262a3f",
        "data/nfl2k5_relief_2026_b81u/jersey_cedc13e8672f341c.png": "a416a2f54d0861a25323e275d517888cb0fab32f36d3c2238c61bcf103239b23",
        "data/nfl2k5_relief_2026_b81u/jersey_d6bd4fcd200880b9.png": "9aea6a2fd005871d7a3ccbd7bca1f8a434e6576f8482ec7fb35635a72c91c8bf",
        "data/nfl2k5_relief_2026_b81u/jersey_d7892f3ec43f37ae.png": "5c7bbe83e05c839b08acf114ef17d8aa1458e53da907973adda8ecbabebd3258",
        "data/nfl2k5_relief_2026_b81u/jersey_da9e396ab9e4aab2.png": "9b66f4fdb0e72ba66c9ee6d8fa2a744fd8d1b6d0bed85b7409e48ac5ced7e2ad",
        "data/nfl2k5_relief_2026_b81u/jersey_dabc0ecf69e73826.png": "902046f7975b9bebcaff78ba0b77059c91b36cec27c41f7a0430a674689fa1ed",
        "data/nfl2k5_relief_2026_b81u/jersey_df00cf5771c47901.png": "33f3d263e9305eadcc18cabc567e0e7fc7d66fb5dcbfa2bdb87267ebe5ef13d2",
        "data/nfl2k5_relief_2026_b81u/jersey_df32c3595bcf208a.png": "293a2a097c63fba292ae4dbf211d20c46d7e296f9c5e716337db835d6e36e938",
        "data/nfl2k5_relief_2026_b81u/jersey_e195a0de3ece9c53.png": "2489e1807deae1c3fcef1f32e5edccef800968e3a24cbdf6fcf6e0a0daecb4c0",
        "data/nfl2k5_relief_2026_b81u/jersey_e52aceef5be0387e.png": "425ccbd3f53f5da90bc74b718686e8e444b42f34a41c518e53730f2889211729",
        "data/nfl2k5_relief_2026_b81u/jersey_ec4fb0e9601298c4.png": "536aea9b59b71cf190511cf153ba1166aee43849edf2735f7a7d4448876298a0",
        "data/nfl2k5_relief_2026_b81u/jersey_f5f0e580bbefbd3f.png": "174f32f987814f7f648d6b0c085f98124eb890ea2aad3cd3702c81aba5b6572b",
        "data/nfl2k5_relief_2026_b81u/jersey_fe829803ff5ecba8.png": "6f9498d9f3b61b8b26b222ecf7d4663ac84deef4c74235f2ab0fe6afaf47db86",
        "data/nfl2k5_relief_2026_b81u/pants_1411994e5bb854ab.png": "4edc24bad262bcc187f52aff21b6e293734396ce7532652e462977857bb3d286",
        "data/nfl2k5_relief_2026_b81u/pants_1555626dd3db073a.png": "14f903d96d3536f5fa261972f771ec1160d79cf01d4e3f1c61a58b41c43519ac",
        "data/nfl2k5_relief_2026_b81u/pants_1ef2c1a114131279.png": "898f5a24c0ca1bb58741c5163bcdf1769ae6a79736a957e056313dd7919cc4b6",
        "data/nfl2k5_relief_2026_b81u/pants_2dcb91c3595d2845.png": "e26ba83403bdbd76cdc929bfa4d04005b6a391ab921ecaa563824d0ef5085128",
        "data/nfl2k5_relief_2026_b81u/pants_30e2233a0551b7c9.png": "8f140260a106ca8e8f4b15178610f7b631e9283d773581d060b68e77164df0e1",
        "data/nfl2k5_relief_2026_b81u/pants_322f9f8e9370e3fe.png": "361b2876826eeb2c7d28aefa9ec1acd38dd9908cf0efa048847c2b3a409efe00",
        "data/nfl2k5_relief_2026_b81u/pants_3cdf334575f2f3e4.png": "9f43da6d77dd86674b4d2691636f995a58aa8592b35e2a491d78583e18e6d5d0",
        "data/nfl2k5_relief_2026_b81u/pants_4b7536c685a24068.png": "bb074af332d5097b9c0161a908ccc3246cd4c3f38544f37b66ebbc6dea35f787",
        "data/nfl2k5_relief_2026_b81u/pants_4ba635e1366c75e3.png": "02471ff26e88ec3b6b53fd231808a5cf32a1c7a146852243548eac5666b8b104",
        "data/nfl2k5_relief_2026_b81u/pants_6de22667d7875b69.png": "14d9ad6e3562569a9e4301b61aaf963a969aaf54b17385cde1f42a3093f13f94",
        "data/nfl2k5_relief_2026_b81u/pants_7578ba4e3ec1a879.png": "265b69c2b22dec6dcb307a4846cead2df2f0282974e597c95f345f16a514dd5d",
        "data/nfl2k5_relief_2026_b81u/pants_75847d3c3f0471b6.png": "a439456941fc4fa9e6149561d91da2bd4ebfafc04865c8e57ae188c0cdd8679e",
        "data/nfl2k5_relief_2026_b81u/pants_8daa16090c56086a.png": "a0632bcc9d71a5dab06955ac87f2f84e98c2842b304648eeb33b77d7f794490c",
        "data/nfl2k5_relief_2026_b81u/pants_8e504d76ee1e5bc8.png": "57c8e518fb5a1e275771000920b41d45ff76ed3ba979818263afb2f5e7a0e5fe",
        "data/nfl2k5_relief_2026_b81u/pants_9ab60e414e773e37.png": "1e39171df921f20abd69b92bd7ad6b73aa0eb1eff9456dc2d466381df8d7b8b5",
        "data/nfl2k5_relief_2026_b81u/pants_b2e21f26231984e8.png": "63cf6bfa7295966cb032e24cf2570bcaf7d32df8236e331705dc810e87ccb76d",
        "data/nfl2k5_relief_2026_b81u/pants_b5aeecfdf31c47aa.png": "0eca9baa66d6126f8afbad78ea414d5f9bdc060201a0f0b547118d06e5c6acaf",
        "data/nfl2k5_relief_2026_b81u/pants_c3d724c12f92c711.png": "bb5070622c73a161eb03f6e61e3eb55708c73589c5b945b5c93f613963f5612c",
        "data/nfl2k5_relief_2026_b81u/pants_c9af6728914a8540.png": "108568b5e45ae068b78ffd78f6fa2efbfd3177d2cf16178a5a943fd804cbad91",
        "data/nfl2k5_relief_2026_b81u/pants_cf6f939940d9ea82.png": "42577622dc0a9ac719feef112d87e8f570112fe121a09dc46dac6ae72b3ed0aa",
        "data/nfl2k5_relief_2026_b81u/pants_d5af3eb466a3449c.png": "86f3f7f88c38cd5f81661125b7df988a9bc77ed8c16912bdcd40e91d584fa3f7",
        "data/nfl2k5_relief_2026_b81u/pants_e53d20841b96af46.png": "ca314ad7679a9facd251c47dc16d249fafb1475820f80d96318987ac75aa8012",
        "data/nfl2k5_relief_2026_b81u/pants_e59208c8e19ce490.png": "c1b644abdaf63a50bb41f841b20e3ff6579c40c2ec9df88d89adec9aff73810e",
        "data/nfl2k5_relief_2026_b81u/pants_e5ee9c2b46eb8b5f.png": "b87a79f444aa8f72682f5c064d15f9ef498feb7faf546c4a09ed128d89e7adf4",
        "data/nfl2k5_relief_2026_b81u/pants_e99b20458c7d11c1.png": "58e145d937021a174139fca407be147be0321786529abd0f617d296e945de6db",
        "data/nfl2k5_relief_2026_b81u/pants_edbd8e96194309ff.png": "1cac0f863bc703b46553157ee05a76d94d03da0cada27f345bb80a5c170f801d",
        "data/nfl2k5_relief_2026_b81u/pants_ee4e23ee718e55b2.png": "82be4befd5611d799c2910f4c883149ab849ee7f2cbfe9c53d056ad46170cbaf",
        "data/nfl2k5_relief_2026_b81u/pants_f13e4152edb77a81.png": "01ec9cbfe6a44063739ed5195ad20d266f6c749e6f2a68c182a0fcefebd6b9e2",
        "data/nfl2k5_relief_2026_b81u/pants_f7c5c027a600889c.png": "0c03f1c01e24c185b151e8640d25ac7e6dd0b22233e006e81ef2f4b34fce9972",
        "data/nfl2k5_relief_2026_b81u/pants_fc27aaf9d3d32732.png": "d88f83bc34e39bf68fd7c1cee098a47b1da28f29bbe6a71e69cea0cc1131f6b5",
        "data/nfl2k5_relief_2026_b81u/pants_fd2661399a5a3975.png": "3da5c7fe008508fdf14075acf716eb001acf0669be3dd622659d289dd8eeba76",
        "data/nfl2k5_relief_2026_b81u/sleeve_0374b17fa6b479b5.png": "ce0a86ddd2e2f385996001b90b9d8ec8c2083dd81db7eeb12c43df9d503d7794",
        "data/nfl2k5_relief_2026_b81u/sleeve_03fc94aa1c403d7a.png": "e268d4618479976b57858fad20666084a038156c312eeed92a613c74c67b8678",
        "data/nfl2k5_relief_2026_b81u/sleeve_07eadc1c75d1d45f.png": "dea2e4d2bf8b0485fb7e5c68a71da5951c05632d095fbfb2b7c03d1474d93c4b",
        "data/nfl2k5_relief_2026_b81u/sleeve_09fb74a53cbd2d0d.png": "0e88dfcf5dee0aea72e1d62cf31a4ea88cee279403004ba9a4a977b18c356ea5",
        "data/nfl2k5_relief_2026_b81u/sleeve_13bb28b56671dc09.png": "cb542d623ffececf719659e0fef298904732b81628c5788a16f86c5c40892a07",
        "data/nfl2k5_relief_2026_b81u/sleeve_158b9c53ecf6741d.png": "ae282445e42a4c2d45e808f0ffbce48b22dbe39e2055b4b04a562b7f44174ec3",
        "data/nfl2k5_relief_2026_b81u/sleeve_2914c1be6dd62322.png": "69cf4e7380af726829012c01612bb86c4edf702ae8074cbe9f4bf417dff09cfa",
        "data/nfl2k5_relief_2026_b81u/sleeve_2c0fc7efce985e6b.png": "231ba0c0b8d0430cb433e67702beaeea1029463e2e27f9d5781db97fbb5f506f",
        "data/nfl2k5_relief_2026_b81u/sleeve_30d2990df11270fa.png": "cbe0c47d2b9bfc866dfc7dddf2d1215f81f1fbaab9b2ec8622089663c0e64365",
        "data/nfl2k5_relief_2026_b81u/sleeve_3c3b7fd4b1255738.png": "34c9b2b5358e11237d37437d3a973599338b79dd8e44bbfc5261738404e60dd9",
        "data/nfl2k5_relief_2026_b81u/sleeve_3e005454b26a78ff.png": "657f5a3118644cc188f44bf5a5282e0e0040b315bbf9584f7dbd6558f8cea280",
        "data/nfl2k5_relief_2026_b81u/sleeve_3f36ff5c03516dc4.png": "3a063b5479af773f770f6cd5c873bdd4f55fe5d2f5ccd66a0f0e15363737118c",
        "data/nfl2k5_relief_2026_b81u/sleeve_4075d7efeecb3e61.png": "3bc448c9dabd45f1c892338d116904a50b16f87497ecd84f693c0a7816f67c25",
        "data/nfl2k5_relief_2026_b81u/sleeve_4829cd928f65b3dc.png": "6ca118e9bc4706c9f2a6184ae71d7529ba5035beb71b174f950030621bfe45ce",
        "data/nfl2k5_relief_2026_b81u/sleeve_493e471a7250cb4e.png": "44be105d43c6c2ece83afc0a15ee1a595bd8bf732c4412f4a804cba30c162ba7",
        "data/nfl2k5_relief_2026_b81u/sleeve_49ca4cdfe5bff8c0.png": "9e48cae7ac7b2178c82e0fbacffa421eb2936ceb7bc2c618ad84522b86b34632",
        "data/nfl2k5_relief_2026_b81u/sleeve_4a3d4696df40b40d.png": "61db59b9e17f25ea3d5b00c29a1384068df68b096d6b3bd7fee8771df43ff263",
        "data/nfl2k5_relief_2026_b81u/sleeve_4fdc1bc7bd244070.png": "845ff92d0d6e65c37392087876073e680a05fd86a087cadcd822cdfe2792cd9b",
        "data/nfl2k5_relief_2026_b81u/sleeve_527792b0e073c74e.png": "051ea8006f6f95cb1e3fa97a9a6338ca301e0ec26f2d16d8782d20cfe7cb41a4",
        "data/nfl2k5_relief_2026_b81u/sleeve_5963b98385b838d0.png": "597cafaf34cb7f696eadb49121494bd90d273244b7926d99a04c4da7f92ed503",
        "data/nfl2k5_relief_2026_b81u/sleeve_5e0037b0863cc875.png": "a247a96a0313fbbb13ab27025e6b43ea40172a3392288dafb71c8ee4a2bf36b1",
        "data/nfl2k5_relief_2026_b81u/sleeve_5f445f0ce96c35aa.png": "0c8795a0c2408c376f79851d6e39c9c271fdbb9d82ab491bb4256874981546d1",
        "data/nfl2k5_relief_2026_b81u/sleeve_65a655ca657c8695.png": "a21d8548837bd8805390ddc0740c5078c1d8e2c0c00f7ef29733cf5dc03a7702",
        "data/nfl2k5_relief_2026_b81u/sleeve_65ea0ccb1356d723.png": "e0742322e9adf26c1c8875da685b5843905288cbef48c5aeabd6c33a60634622",
        "data/nfl2k5_relief_2026_b81u/sleeve_69d8b4f0b06e300c.png": "7f629fa1669b5f0d6463ac683f241621a4076ff175842b70603da1f2cca845e5",
        "data/nfl2k5_relief_2026_b81u/sleeve_7fc74e56d5840fb1.png": "8ad14b8158c43144f50008d1571ee552e32f45fa23dcc1697b01a7fac2b4a8ec",
        "data/nfl2k5_relief_2026_b81u/sleeve_854cf38dbbbc33fc.png": "7410d142c7dc5a78e1256afb1c0de0680e3e8ea23ca273ae6efdc45c51e3a1f1",
        "data/nfl2k5_relief_2026_b81u/sleeve_8992fc8a8940e640.png": "dac5284faa0212f7b98af5dcc3c2219fc92e66ede219785a6f6d0ddc7613bde6",
        "data/nfl2k5_relief_2026_b81u/sleeve_95bd7da6e3342283.png": "2716dfbb2156f61a31df73fd39c9519f8f0eac6761f6f9113301db65d8b626c7",
        "data/nfl2k5_relief_2026_b81u/sleeve_9763a09bac19428c.png": "31e69fbbbd0fc3b34102833a8f4fba16f9320c4f3eeee8c85a2c9a8662b7a18b",
        "data/nfl2k5_relief_2026_b81u/sleeve_9d56584a6e003663.png": "184ce8b94aca17a9c91d5ff432606fa1b532232ff009b7a1edb96fb654ffd002",
        "data/nfl2k5_relief_2026_b81u/sleeve_aa995d8bad5a175a.png": "a6135c5eab1f88321e6deba93ed8a7e7fbbf8cf211954f5201caac881ffd18e5",
        "data/nfl2k5_relief_2026_b81u/sleeve_c103284c58897bba.png": "19d03d2bd16497d93ea2e60f8da86afa85d56cce2b621d2862d8f7772400fd4c",
        "data/nfl2k5_relief_2026_b81u/sleeve_c2526fa7bfd55e99.png": "3a0bac8087d2339e1fb6b752838f7015de772cd9e25db028338e4ca4896529ab",
        "data/nfl2k5_relief_2026_b81u/sleeve_d2fe5151099cfcbf.png": "85654412476ae96f1e024811807a4c7f2c4eba52a66dade26851f7f5706440a8",
        "data/nfl2k5_relief_2026_b81u/sleeve_d490ad9edd64e09a.png": "22785bbe474caa6d02f3625234fa99f287619872a1fdb11e76a6c38269ddab35",
        "data/nfl2k5_relief_2026_b81u/sleeve_da452b5f9f2393d0.png": "aeffbf140326923f7fc09cbf43003e8870195c460fee7b994fec39dc10e996cf",
        "data/nfl2k5_relief_2026_b81u/sleeve_e32d6e79dad95f92.png": "e297ab64800a437b045f3d157d6c64c061dfd39e32a8403cdf03b8dbf1ceed20",
        "data/nfl2k5_relief_2026_b81u/sleeve_e473d30c9c2785ec.png": "bebd90bbc4873276ae0263a568c49f6756c0a5d7083de72317e82fa9c397cd0d",
        "data/nfl2k5_relief_2026_b81u/sleeve_e662bc0e2a5f5d0e.png": "8574c54468ae8173e342febf3f5c5279585188297aef66f43c1f028662b70d80",
        "data/nfl2k5_relief_2026_b81u/sleeve_e9642e24fde03ca5.png": "706d68b3caca15a953d178535169a151af441aeffa7ff1f91092a2d366289d67",
        "data/nfl2k5_relief_2026_b81u/sleeve_eae5c711e253e301.png": "878f8d84705101af177d13278c67433552991642c619272729ea023b74bf13a1",
        "data/nfl2k5_relief_2026_b81u/sleeve_eb08218b66c6e7f1.png": "4ab2631364ba4891311a873e8707f8a50f47584ac2450798f63de986060c97ca",
        "data/nfl2k5_relief_2026_b81u/sleeve_f12d3e250fe3c759.png": "d46bb449dafdd821aaffcfb587ffae3d092f1bbefbc6bc26f4b29c590819edcb",
        "data/nfl2k5_menu_chiefs_2026.json": "8b4a86d2bb6893d6e23546ebddc3ff1626e029fcf3b8ed4a14fbee6fd1748eb2",
        "data/nfl2k5_menu_helmet_w2026.json": "ae19a9a2d032d25312fea3114ae530b137a0f437629f56c5ff484f08ac5626b6",
        "data/nfl2k5_indicator_names/atlas.png": "2693d6044962f9f59f4390b3e578d3575d9d3f0c081ae668510c83399c3197f7",
        "data/nfl2k5_indicator_names/metrics.json": "2bebe47d2fb50e36a5c3a736d95677c06c780addf88463c2b5b266111af4a129",
        "mod_editor/data/nfl2k5_free_agents_2026.v1.json": "39cf9602756dcf8742e90654a43fecf10c86f24db61a915074ccef094a6f7ad8",
        "mod_editor/data/nfl2k5_refresh_appearance_2026.v1.json": "867624f428dad0d32eba16b6e05d4d2f104266c5fe37c3c0d9ab43ce7797e204",
        "data/nfl2k5_ratings_forty_sources.json": "39cc65634bfafab8b37817129be309e85f73f35ef7eb5f1f0b2472e5632d5817",
        "data/nfl2k5_espn25_more_teams/teams.json": "0484cc4ea617f4d250571ac3551f820368a15456c444326203d31c98eebd8cd3",
        "data/nfl2k5_espn25_more_teams/manifest.json": "1aefb229e40d438e32210669eb62459bb71aa056bfe23c460dcc86eb0fbc95ba",
        "data/nfl2k5_espn25_more_moments_appearance.json": "d129d17eb71eac0f2bb5a5c3bbcec3a82ff256437dc06a104f14e60afae7232c",
        "data/nfl2k5_moment_scans.json": "c95a90c155fe170d6a312acdf659b3bffd04c028b3d930ab1fdc13d6a8971627",
        "data/nfl2k5_espn25_moment_rosters/appearance.json": "2349e073097edced764fe790d449ef8223f444363711494cfe9996a19678296c",
        "data/nfl2k5_classic_teams/teams.json": "bbe46a3c6d87a9c7a8d2e1c95a63cece0495a7c069a132fd5253cd9ecca668ca",
        "data/nfl2k5_classic_teams/manifest.json": "93e82081f2036b2196ae78ba9a71df138c205bae8e9269b596a60e2ea588de35",
        "data/nfl2k5_classic_teams/appearance.json": "8b2607c2ceb4e70682991b0980736b3be9726fbdb1fbe440d812a48ef30b711c",
        "data/nfl2k5_classic_teams/classic.json": "defcc410cb3ca1bec867f0a05fe8ecd599d727e9107426cfa2fa709473cf4b69",
        "data/nfl2k5_classic_teams/honours.json": "9430c474ede71ea59077476a01c051fc2675a032e864e84cf77312d25d52d184",
        "data/nfl2k5_espn25_more_moments.json": "53b5667960d0720ab75d127804f152d9513d681648525b958228db16bf12bafd",
        "data/nfl2k5_espn25_fields/source/nfl_2008.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/source/nfl_2008_source.png": "6b8162747a0a58998b342a3a351ba5efbe70cb6ce1350889db9656e74514b119",
        "data/nfl2k5_espn25_fields/source/manifest.json": "8b1addd0e0b8c392519b40cf661e3a65cfcaa4e3267c1c4a326ff316bfec6588",
        "data/nfl2k5_espn25_fields/source/den_wordmark_1968_1996.png": "45249c2c87f229cd89d513a5e009d0a0a967dbb15f076637e8a1343257ad833c",
        "data/nfl2k5_espn25_fields/source/den_1968_1996.png": "4e8cd3f37ee15539b086f157a6835b9986e648f8124fac4a8368579a11777030",
        "data/nfl2k5_espn25_fields/row51/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row51/endzone_S.png": "7d3eb92c5b89ea2c4ba0df1b9fc6031742110f4c84ad9fff4dfeb57a1b2baec1",
        "data/nfl2k5_espn25_fields/row51/endzone_N.png": "7d3eb92c5b89ea2c4ba0df1b9fc6031742110f4c84ad9fff4dfeb57a1b2baec1",
        "data/nfl2k5_espn25_fields/row51/center_logo.png": "faa151e8d922c6dfbb37394b0b6d5b556dccbf02002cd11e57fadc6b0caed840",
        "data/nfl2k5_espn25_fields/row50/playoff_logo.png": "035321f7b260488a6ecaba93cc54814649ac7f1bfa7d3d53dd090de233aab1a4",
        "data/nfl2k5_espn25_fields/row50/endzone_S.png": "ad3ebe4d1bd9682f34dfba8a75f9072021fcdc3122daee16cf9242e4ac6ecae9",
        "data/nfl2k5_espn25_fields/row50/endzone_N.png": "b4e3b58d35b03ac6699a2c1240682348eb44869af21def2a4ced00daa2d18706",
        "data/nfl2k5_espn25_fields/row50/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row49/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row49/endzone_S.png": "fd330f882c387324a911944fbdcd79b3b79b4d25c11e7b555045f06e99aec912",
        "data/nfl2k5_espn25_fields/row49/endzone_N.png": "fd330f882c387324a911944fbdcd79b3b79b4d25c11e7b555045f06e99aec912",
        "data/nfl2k5_espn25_fields/row49/center_logo.png": "7b0b9bfd168c22f023133e6def7c0140d335a6c45ed099d00586235b78ee0d32",
        "data/nfl2k5_espn25_fields/row48/playoff_logo.png": "571c2e2fbad7c51f10bf7807afce6f0ce929d6461b2c339cd100507296b1b8cb",
        "data/nfl2k5_espn25_fields/row48/endzone_S.png": "d3a999474e89240e6bdc96ad77a5a0a87a0820c97ab4b50c7e7c7106ee928bd9",
        "data/nfl2k5_espn25_fields/row48/endzone_N.png": "956e4ef615779c0fccba65d6983ac709130820732e06325f1299852a5b4b9499",
        "data/nfl2k5_espn25_fields/row48/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row47/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row47/endzone_S.png": "c6852cd5f76a924924875a1e0f1d026d753cf3b4fe033317d4fc8d0382bdb328",
        "data/nfl2k5_espn25_fields/row47/endzone_N.png": "618858132efada63436afbf3f10bd8af2df65e128fcd1deaaa26b6da790d5596",
        "data/nfl2k5_espn25_fields/row47/center_logo.png": "4d4f617af92995f9d93102a1f572419d6738763ac0376070f08ebceb17da8e0b",
        "data/nfl2k5_espn25_fields/row46/playoff_logo.png": "d2135e57222ad2f0df936dc9a748994f41b74e3011abe5efaf27878ff1484b03",
        "data/nfl2k5_espn25_fields/row46/endzone_S.png": "50a719f19e985acb0f5e6ffae446d989278567577bca634d53f8479da584aa1a",
        "data/nfl2k5_espn25_fields/row46/endzone_N.png": "06ba6c33051b188c72229cad481880f532c92406c8ab0d21983a2a4c73e97844",
        "data/nfl2k5_espn25_fields/row46/center_logo.png": "22c0a79706a3642e580d5a36bd5ce3c20301aefbe64c50dca2561f566d07811f",
        "data/nfl2k5_espn25_fields/row45/playoff_logo.png": "be22410453acbbeff81e09de8b548c943e4d35a8a3cc8f586f6eca8f0a706df3",
        "data/nfl2k5_espn25_fields/row45/endzone_S.png": "af98b4fcf27929e1b59c9b849d0fdeb7ca2a5c6e2efd3e1bc7eb14a5f29011e3",
        "data/nfl2k5_espn25_fields/row45/endzone_N.png": "7c573abe809a76663b89b03ca24f81f091e3bb4e516b9f62a38bb86176fc29c2",
        "data/nfl2k5_espn25_fields/row45/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row44/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row44/endzone_S.png": "3e89cce2a482a9b8e2b014f03d080680ad7cc0dccf2efbf8c203345a1880d3e5",
        "data/nfl2k5_espn25_fields/row44/endzone_N.png": "c78b63e95e668741132f8887afe25970ac2290abe56d93bf08bc7e1e68660f21",
        "data/nfl2k5_espn25_fields/row44/center_logo.png": "7b0b9bfd168c22f023133e6def7c0140d335a6c45ed099d00586235b78ee0d32",
        "data/nfl2k5_espn25_fields/row43/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row43/endzone_S.png": "ecd56f8f93af9a056156797b7c97ad2dba9185b918e5529d99d26a2cb645bbce",
        "data/nfl2k5_espn25_fields/row43/endzone_N.png": "ecd56f8f93af9a056156797b7c97ad2dba9185b918e5529d99d26a2cb645bbce",
        "data/nfl2k5_espn25_fields/row43/center_logo.png": "659161efd63caad98b98095c58c0feda8ba9d99ddf99b0f061704240d245c2e2",
        "data/nfl2k5_espn25_fields/row42/playoff_logo.png": "bd8d10d6bd2ee0ed7a6206f3ca84941e93915cc854218a9bddd9f36ed8d3f729",
        "data/nfl2k5_espn25_fields/row42/endzone_S.png": "b464c1af50b1fac10dda0ccd7eef841e505ea81c0947ba9a83189f04f4564b0f",
        "data/nfl2k5_espn25_fields/row42/endzone_N.png": "9892b7209497c580ea413484c0c567e1b7bc87f40062a93bd29360b6cdae3f15",
        "data/nfl2k5_espn25_fields/row42/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row41/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row41/endzone_S.png": "8f308c45ae9bb0e2de5ced49400ac7c3293994d6299bbfab9c615c9f40796a73",
        "data/nfl2k5_espn25_fields/row41/endzone_N.png": "42d424e1ad75b5196a60e8aa6bb7a1fcab4c1e0e3af289a2838f65cbaa669364",
        "data/nfl2k5_espn25_fields/row41/center_logo.png": "e708e2111962c122369974fa58ea20d2016011419753354dbef917917c33ef39",
        "data/nfl2k5_espn25_fields/row40/playoff_logo.png": "09d50edbcb46ed497c9a5797779e88ab7f43dc0880a51e1d58a8fd68a2091eeb",
        "data/nfl2k5_espn25_fields/row40/endzone_S.png": "0ef7eb9986c436918e67a7a86c4a090db7395e2fa48cdcaa93f45f9b536b27d5",
        "data/nfl2k5_espn25_fields/row40/endzone_N.png": "0e45d24a19d3e0ed0293e66055d37f1e7f3e247a8a6730f043d9339a78cdd65b",
        "data/nfl2k5_espn25_fields/row40/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row39/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row39/endzone_S.png": "a01e17bec7bebb0acdc3686f7cd489743ffafb17b5f0c318ddc60712731d1d94",
        "data/nfl2k5_espn25_fields/row39/endzone_N.png": "7d3e884df42ebaf738328c8be1d2b2256277d51ab7f75d89eaf372c21c15330f",
        "data/nfl2k5_espn25_fields/row39/center_logo.png": "1a9a1b499ada786b67122e7e54b1d71cacc1e11693f2848d9e652c389877fc77",
        "data/nfl2k5_espn25_fields/row38/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row38/endzone_S.png": "75d87dd14b8f824f34f246ea0ba2b0057e3c2a6614cbc6f6fb70003abe40019c",
        "data/nfl2k5_espn25_fields/row38/endzone_N.png": "d18dd00877c7be5f2097b1c56b8b599192e38942069a807ba80d7a5b7d96ad0d",
        "data/nfl2k5_espn25_fields/row38/center_logo.png": "6d6c95a7a16b664da3797b20985352ea06a7e1ffe10dbb35b7a74b0cfcd8ca02",
        "data/nfl2k5_espn25_fields/row37/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row37/endzone_S.png": "51911f4f533b030699729faec5ae1bab4939876415510f529b1302e393c576f9",
        "data/nfl2k5_espn25_fields/row37/endzone_N.png": "51911f4f533b030699729faec5ae1bab4939876415510f529b1302e393c576f9",
        "data/nfl2k5_espn25_fields/row37/center_logo.png": "03bf5a691e88e919520a1ecc40b975cf3196437764a69c0742fb9a90fafe78a5",
        "data/nfl2k5_espn25_fields/row36/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row36/endzone_S.png": "1fee175614c51ff839de63d583d4d9c91c621ade4d2eca88dd2116b003ff9ba6",
        "data/nfl2k5_espn25_fields/row36/endzone_N.png": "1fee175614c51ff839de63d583d4d9c91c621ade4d2eca88dd2116b003ff9ba6",
        "data/nfl2k5_espn25_fields/row36/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row35/playoff_logo.png": "57ec2ba76d21f89f36baac87d28f7cffa92fa25a8e660045a666e115e5ce79c3",
        "data/nfl2k5_espn25_fields/row35/endzone_S.png": "f76c0a982017212d7ca5a5c387dac5c22f700712b51035b5263eac82c08110f3",
        "data/nfl2k5_espn25_fields/row35/endzone_N.png": "a3b5117e5d22b0a75eac01d9440069179e8ba99dd4f8a50e277f76177e9fa6a0",
        "data/nfl2k5_espn25_fields/row35/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row34/playoff_logo.png": "8f9999e96b5bc292baa8569b362878be17092ccde7600d23d04fb3f0520ba10b",
        "data/nfl2k5_espn25_fields/row34/endzone_S.png": "9977ce085702a660d2179b351f47c1f769b0f10fb774a2adb4b3cad19352e77e",
        "data/nfl2k5_espn25_fields/row34/endzone_N.png": "bc09b4b44e39f100a94621b4daa1fe09e44ed4a93e020c2da631602646570af1",
        "data/nfl2k5_espn25_fields/row34/center_logo.png": "8795cf7d2e2314e41389ec6f9c19518d907e641da3c4c581c96a6db44f2e34e7",
        "data/nfl2k5_espn25_fields/row33/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row33/endzone_S.png": "9ce33fb27005df9209e329d4858c64043777cc93e64c0a67a213c6e4c5d0ab96",
        "data/nfl2k5_espn25_fields/row33/endzone_N.png": "4c55fcad6beed6e7e41edebb4c7a8ad0e4d30583e69c4c5d7bd67fa916f988cc",
        "data/nfl2k5_espn25_fields/row33/center_logo.png": "ee725a47f32d9127a24b7bfd8414a20aabe0ace5ead9f266d2b5330fe2c76bc2",
        "data/nfl2k5_espn25_fields/row32/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row32/endzone_S.png": "e5e59b90790ad84dc90ecff2aa02c5f94dd66bbcf746081936b8f9f52ff7149b",
        "data/nfl2k5_espn25_fields/row32/endzone_N.png": "116659760ce5ecc7bf8367125ca48510bb8db428e7e59db2dc7f0c44cfb24db1",
        "data/nfl2k5_espn25_fields/row32/center_logo.png": "5632834fda06dc6e611e64d1ab914ba9bdd28b19173f9d91fa03cccdaefffd31",
        "data/nfl2k5_espn25_fields/row31/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row31/endzone_S.png": "3cbc6957f97a3e8895a7e68e6df6c4af77ae1321f65d5e79c253b726acb811dc",
        "data/nfl2k5_espn25_fields/row31/endzone_N.png": "3cbc6957f97a3e8895a7e68e6df6c4af77ae1321f65d5e79c253b726acb811dc",
        "data/nfl2k5_espn25_fields/row31/center_logo.png": "4cc83cb4a3d044a48cd48693936d119c2a94c606a7d677c8663d54b66f565678",
        "data/nfl2k5_espn25_fields/row30/playoff_logo.png": "2d08eb5dc662bcfbb7d821039125d31cab6ff9527b8f4716cf325944251940fb",
        "data/nfl2k5_espn25_fields/row30/endzone_S.png": "b603e57c8870a9c2f63b4bd6d60b991e4b36399cf2144e111e8598fbd0b0f530",
        "data/nfl2k5_espn25_fields/row30/endzone_N.png": "0fd248e8435ae24caa00cb5db803991e42ac44e57274c8cf92b40b4fb3d9efd9",
        "data/nfl2k5_espn25_fields/row30/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row29/playoff_logo.png": "a8a872758f2f970c21fd7ec606002715613406a1e8fa15b0bcbbea2514e58bb8",
        "data/nfl2k5_espn25_fields/row29/endzone_S.png": "d496174600b16f8090aaebb3d4bb7493d11596f8c7a011df9b5fd52304d6805a",
        "data/nfl2k5_espn25_fields/row29/endzone_N.png": "0e102f9f9787490dcbe7ca69f53adcddce99243af94e5647e72cd753d8771ac2",
        "data/nfl2k5_espn25_fields/row29/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row28/playoff_logo.png": "8745e73577c0ffcf315ea4a73d38b44745e8ccf39b2d8ffa2f5f8cf70d42e935",
        "data/nfl2k5_espn25_fields/row28/endzone_S.png": "c939a90032ad4d4471531e6331827d61809633060f3a7a9a624f133dadc0f53a",
        "data/nfl2k5_espn25_fields/row28/endzone_N.png": "68b9b03fccd9513c4c017cbf849621c21a48e39d5f88390dbd6f54c957a57cbd",
        "data/nfl2k5_espn25_fields/row28/center_logo.png": "1d0e8fe7f52a9ba3549e415e14c82bc70221a3ff9bfe6d934b4304be100eaec6",
        "data/nfl2k5_espn25_fields/row27/playoff_logo.png": "6e894eb32b38230931a622e992aa03a06f7f40590ca44a0371189bc590a7cfe5",
        "data/nfl2k5_espn25_fields/row27/endzone_S.png": "190a4c9c61361b2b4fbaea07eb76984afda78d16401b7e2311c3c22addc8ae10",
        "data/nfl2k5_espn25_fields/row27/endzone_N.png": "efeca1f6d55386370276893f7125282228ed5fb622f60ca84b6047a5c3876ab5",
        "data/nfl2k5_espn25_fields/row27/center_logo.png": "8795cf7d2e2314e41389ec6f9c19518d907e641da3c4c581c96a6db44f2e34e7",
        "data/nfl2k5_espn25_fields/row26/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row26/endzone_S.png": "f79d84a6b1af61d9ba4120918b2d8bd3bf3cdc0645cd455f93a896c0c91724e2",
        "data/nfl2k5_espn25_fields/row26/endzone_N.png": "19c06c07cd3d065350404b7290a983205e6010408f34ffaa5672463dab3be630",
        "data/nfl2k5_espn25_fields/row26/center_logo.png": "3a313ff9757e05cccffc4c35f864df76480d8431a4d3419f353cd570f86adf33",
        "data/nfl2k5_espn25_fields/row25/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row25/endzone_S.png": "688d7a50a6b99c9571c069213579148d43d85fd44bf1cc48cad642a04ece99a6",
        "data/nfl2k5_espn25_fields/row25/endzone_N.png": "688d7a50a6b99c9571c069213579148d43d85fd44bf1cc48cad642a04ece99a6",
        "data/nfl2k5_espn25_fields/row25/center_logo.png": "4305f33bb9eb01e314d944a0a9fdb6f45a9109bd2c3ae1f983d69b6b664e1b62",
        "data/nfl2k5_espn25_fields/row24/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row24/endzone_S.png": "98bdeb7e258ff0fedbd32a41969bd1a68d1452042ffdb92ce52f9a554307d5ac",
        "data/nfl2k5_espn25_fields/row24/endzone_N.png": "98bdeb7e258ff0fedbd32a41969bd1a68d1452042ffdb92ce52f9a554307d5ac",
        "data/nfl2k5_espn25_fields/row24/center_logo.png": "6d6c95a7a16b664da3797b20985352ea06a7e1ffe10dbb35b7a74b0cfcd8ca02",
        "data/nfl2k5_espn25_fields/row23/playoff_logo.png": "53e7d8a3488bec7ddb88e8fbcdd618d3c1e3b918b2ed3fbef45bbaf65ec10b5f",
        "data/nfl2k5_espn25_fields/row23/endzone_S.png": "cd55dd7948c3ddebee8b96b27ba183a114f35f57c757e319e1bdb6787739e2a0",
        "data/nfl2k5_espn25_fields/row23/endzone_N.png": "e828bcc77f166efd379ff7c3b9244b4505595d64c6322cf018855f6fa4172214",
        "data/nfl2k5_espn25_fields/row23/center_logo.png": "4041219e07916001f1fa1f1276ca8995c021e53057dee6579c1373a18c607947",
        "data/nfl2k5_espn25_fields/row22/playoff_logo.png": "59bd9acecf82110a85ea42a836745822c3b8fe187260ed9f6cec7120e264d7fc",
        "data/nfl2k5_espn25_fields/row22/endzone_S.png": "aa8c70cc1824f59330e6b9d12802be50e0492a2451ebd85ff91df0af6b1e8fe9",
        "data/nfl2k5_espn25_fields/row22/endzone_N.png": "52a759c5f8bc972085e8fc673f50b6e913dcbb97214bdc47e9ef872d699b2426",
        "data/nfl2k5_espn25_fields/row22/center_logo.png": "7b53b041f70897eb02b6d6830cc1be105b39ec32b54a587ea456a7e0c2b33769",
        "data/nfl2k5_espn25_fields/row21/playoff_logo.png": "1458018501bc5d4967ec5442b0d6510eb1481047d055d18abf89d000b282b5de",
        "data/nfl2k5_espn25_fields/row21/endzone_S.png": "cfd689926a1df35948c10b4d08ee5e8b77f496444e44694da2638f53d93b2035",
        "data/nfl2k5_espn25_fields/row21/endzone_N.png": "29be3b298b4e221f85a5d81ba3387d7ebdcfe59a2e369b80ebb3a8d9f0df9a23",
        "data/nfl2k5_espn25_fields/row21/center_logo.png": "92cb3644b95a4e52eb713f16fff8cd6b0f3b505a9c0d2a07f234262d1106b141",
        "data/nfl2k5_espn25_fields/row20/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row20/endzone_S.png": "c0b088ff52d722f4cb261dec97fe776acdba87a76dbfe6c3f4eaf28985da7f07",
        "data/nfl2k5_espn25_fields/row20/endzone_N.png": "ed526e17094387b211bf42973922b926902597c0c0d194940e909b4b46591873",
        "data/nfl2k5_espn25_fields/row20/center_logo.png": "2c096e8848378b195ae33e86efbac90cc45d77148205680e429d7fa3940b5397",
        "data/nfl2k5_espn25_fields/row19/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row19/endzone_S.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
        "data/nfl2k5_espn25_fields/row19/endzone_N.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
        "data/nfl2k5_espn25_fields/row19/center_logo.png": "c956057054db08e1bb6f64ba376df5c04d2b6b5b1647e22bf40157235e9583cd",
        "data/nfl2k5_espn25_fields/row18/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row18/endzone_S.png": "c0b088ff52d722f4cb261dec97fe776acdba87a76dbfe6c3f4eaf28985da7f07",
        "data/nfl2k5_espn25_fields/row18/endzone_N.png": "ed526e17094387b211bf42973922b926902597c0c0d194940e909b4b46591873",
        "data/nfl2k5_espn25_fields/row18/center_logo.png": "2c096e8848378b195ae33e86efbac90cc45d77148205680e429d7fa3940b5397",
        "data/nfl2k5_espn25_fields/row17/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row17/endzone_S.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
        "data/nfl2k5_espn25_fields/row17/endzone_N.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
        "data/nfl2k5_espn25_fields/row17/center_logo.png": "c956057054db08e1bb6f64ba376df5c04d2b6b5b1647e22bf40157235e9583cd",
        "data/nfl2k5_espn25_fields/row16/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row16/endzone_S.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
        "data/nfl2k5_espn25_fields/row16/endzone_N.png": "0dac8b822183cd16186d406db078aa907c623f0dc152872efa4e34cae704509e",
        "data/nfl2k5_espn25_fields/row16/center_logo.png": "c956057054db08e1bb6f64ba376df5c04d2b6b5b1647e22bf40157235e9583cd",
        "data/nfl2k5_espn25_fields/row15/playoff_logo.png": "bd1f3db9f201822293f52dc0929d6e2fd62d6c06b391789f4b122b58f82ab42d",
        "data/nfl2k5_espn25_fields/row15/endzone_S.png": "26004ccd163f9e20014fb68cf094bfa1449c9869989ac43b3e9fb6750b81caa5",
        "data/nfl2k5_espn25_fields/row15/endzone_N.png": "7ed33ab918ee2275f84d7fb57cba68bcf3de5515d9c391f03ee1fbdf7e36c60f",
        "data/nfl2k5_espn25_fields/row15/center_logo.png": "609b9479ef1033e4c361df7edb28272c789fb45c0a7a8b7f429bd9be1a7d5122",
        "data/nfl2k5_espn25_fields/row14/playoff_logo.png": "73067442898187e2fe0e01bd154266897b1b7b48bd71177dfc0f1bb33851ad74",
        "data/nfl2k5_espn25_fields/row14/endzone_S.png": "88959788326a55e07943abc9b10f206402078e4fd7e110c35a71af3d3ee70304",
        "data/nfl2k5_espn25_fields/row14/endzone_N.png": "26f2900788884f66ab13ecd7f3638e6ab6a3baee99c28e14a3049b6c295bbb86",
        "data/nfl2k5_espn25_fields/row14/center_logo.png": "8795cf7d2e2314e41389ec6f9c19518d907e641da3c4c581c96a6db44f2e34e7",
        "data/nfl2k5_espn25_fields/row13/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row13/endzone_S.png": "94f9d868b85b78746e176b47fbc476422df63f0a05be559629f46d3bd91d33b6",
        "data/nfl2k5_espn25_fields/row13/endzone_N.png": "94f9d868b85b78746e176b47fbc476422df63f0a05be559629f46d3bd91d33b6",
        "data/nfl2k5_espn25_fields/row13/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row12/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row12/endzone_S.png": "14a115bdaa4d5957b4c5ffeefb17733de3ecdfa67e845e8f6db753379d58b844",
        "data/nfl2k5_espn25_fields/row12/endzone_N.png": "14a115bdaa4d5957b4c5ffeefb17733de3ecdfa67e845e8f6db753379d58b844",
        "data/nfl2k5_espn25_fields/row12/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row11/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row11/endzone_S.png": "2b1aab048e8775d954ecf404bda54da9289a0de4427fcd2340a05cb0fdd1f292",
        "data/nfl2k5_espn25_fields/row11/endzone_N.png": "322eefd24e0fa8f201ec3f4ff0d7f6b339d52383d81508cc108109473337b24a",
        "data/nfl2k5_espn25_fields/row11/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row10/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row10/lettering.png": "7baf59cda0fde5793f976ff484008341da764cc8dfac96c26e875c44d2d731e2",
        "data/nfl2k5_espn25_fields/row10/endzone_S.png": "ef01cb09f101c5d36b67d907721827958eabfe107604525d991dc50bbf48c199",
        "data/nfl2k5_espn25_fields/row10/endzone_N.png": "ef01cb09f101c5d36b67d907721827958eabfe107604525d991dc50bbf48c199",
        "data/nfl2k5_espn25_fields/row10/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row09/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row09/endzone_S.png": "cb3be6e910723f61f98b590d7aa776e45de85a6cb923393190e21ef517af84f2",
        "data/nfl2k5_espn25_fields/row09/endzone_N.png": "3e2898d4d793483906ae8b7a88552137f2097d3b9641377855ed4795ceafa439",
        "data/nfl2k5_espn25_fields/row09/center_logo.png": "4124084c42bd24cc6af2919b80b1c77e4d4bf62b8fc3c9b9bf3f07e18b1135a5",
        "data/nfl2k5_espn25_fields/row08/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row08/endzone_S.png": "c03c94821d6c561b6a636d92fce0de6d81a42c02139d365d52559b8af9245577",
        "data/nfl2k5_espn25_fields/row08/endzone_N.png": "c03c94821d6c561b6a636d92fce0de6d81a42c02139d365d52559b8af9245577",
        "data/nfl2k5_espn25_fields/row08/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row07/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row07/endzone_S.png": "26954570a83d7df4bf3631cecc53877b191aac991f3d6ea5d13a067ad87c2425",
        "data/nfl2k5_espn25_fields/row07/endzone_N.png": "26954570a83d7df4bf3631cecc53877b191aac991f3d6ea5d13a067ad87c2425",
        "data/nfl2k5_espn25_fields/row07/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row06/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row06/endzone_S.png": "8708e20aaef8baf8aad45b38839290da0e660da8c495fd055f30ed4143f2643d",
        "data/nfl2k5_espn25_fields/row06/endzone_N.png": "487d4f827ca5bed40fd332e10cd1d93a80a503da03453f28cede8ee0bd441ff8",
        "data/nfl2k5_espn25_fields/row06/center_logo.png": "1427e0e1a617bf3e0d2ab0804dc8697bc60e1601d0248e9e31407fa4c9df1aa8",
        "data/nfl2k5_espn25_fields/row05/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row05/lettering.png": "0aac0ba56ad51c2107386e06a8fc727527be93eff31e5662505834d89a6d28ed",
        "data/nfl2k5_espn25_fields/row05/endzone_S.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
        "data/nfl2k5_espn25_fields/row05/endzone_N.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
        "data/nfl2k5_espn25_fields/row05/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row04/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row04/endzone_S.png": "d663ac7e95f6f10900421707723971b839539de9593b1771610d43262324138e",
        "data/nfl2k5_espn25_fields/row04/endzone_N.png": "3bc7d4419a3e7f2c5b80e04e4cbfd07300a706cc174fdc4d09b23a1f2f5766a5",
        "data/nfl2k5_espn25_fields/row04/center_logo.png": "912db95cd096b6199ac3c21500cc5b3fd3554ff241c729bd71fc8f89a0a572b9",
        "data/nfl2k5_espn25_fields/row03/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row03/endzone_S.png": "a8d9521e6aaee5eb8024e8323850bb3547e580cac29818445293ddded6b78f1c",
        "data/nfl2k5_espn25_fields/row03/endzone_N.png": "ebebbe97f639a91083adc740cc6dcac2d95606813fb09933e5e84662ce1ce071",
        "data/nfl2k5_espn25_fields/row03/center_logo.png": "f9559b5717fe3aaa4d4a8374c548ef12a33b5016bef5de7f5a2c5eabdb165732",
        "data/nfl2k5_espn25_fields/row02/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row02/lettering.png": "0aac0ba56ad51c2107386e06a8fc727527be93eff31e5662505834d89a6d28ed",
        "data/nfl2k5_espn25_fields/row02/endzone_S.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
        "data/nfl2k5_espn25_fields/row02/endzone_N.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
        "data/nfl2k5_espn25_fields/row02/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row01/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row01/endzone_S.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
        "data/nfl2k5_espn25_fields/row01/endzone_N.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
        "data/nfl2k5_espn25_fields/row01/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/manifest.json": "9f7e0cfc607f9068b143eeb7d44f68209b7a324ef3fe4857fa9dda676a588006",
        "data/nfl2k5_espn25_fields/source/nfl100.png": "e5492f431984e885ba5e927e747a6716f39755ae3f078e3ac3714ca84b3dd41b",
        "data/nfl2k5_espn25_fields/source/row03_center.png": "add4deaffc840b722d98c7bd91cb6286a165a8de922d160c601823e556f6f53e",
        "data/nfl2k5_espn25_fields/source/row03_endzone_N.png": "f3c15f0bb902d97950f48de236c30a911012d60a5fbb03f0ef9ce09a0107fe14",
        "data/nfl2k5_espn25_fields/source/row03_endzone_S.png": "aec7eafc5c01bc99a389e3b59c3098f0b045f3fb51d58ac61ddf3808e08a9e96",
        "data/nfl2k5_espn25_fields/source/row04_center.png": "b86a10f3569bd9f91f0ceed8c3a1a4ded49e5e3323ab25a19037d482b9cd4d3b",
        "data/nfl2k5_espn25_fields/source/row04_endzone_N.png": "e109b337b8364015b9edc9410787e4a0a5fdb2fc19e20afb129a967dbe9087ca",
        "data/nfl2k5_espn25_fields/source/row04_endzone_S.png": "a178d41eb5db399f9846447708569a7f87c442fbcd7b7cf42757a6f860d02ca9",
        "data/nfl2k5_espn25_fields/source/row06_endzone_N.png": "a4de783fddd78f91073a7436abada3ba7051a02020c8e05912ef165b755ecf2d",
        "data/nfl2k5_espn25_fields/source/row06_endzone_S.png": "2acc161b38279f97e1f04218ecc94a575ed9ce633e72563a6ae5afeabe133b2a",
        "data/nfl2k5_espn25_fields/source/row09_center.png": "0dcf00e16a79fdac977df59358af2a6b4dbca194a4bb969694f84e419ee42fe4",
        "data/nfl2k5_espn25_fields/source/row09_endzone_N.png": "778c702aaf18b98fd3663cdba1568d48f241db9d560da834eae1bd2a75440672",
        "data/nfl2k5_espn25_fields/source/row09_endzone_S.png": "20dae6541e87e3d80a7cd3e8829a1608a16667dd6fd4a302fb97c83ee7dd2361",
        "data/nfl2k5_espn25_fields/source/row11_endzone_N.png": "c9fa1f2b428414637d6215dca913a5db6d2ca80f7e5f49536e3241a02c57ae38",
        "data/nfl2k5_espn25_fields/source/row11_endzone_S.png": "ba9ef9f3aca98914aed5cbe829a0808405ea646412c28854132399a42c204113",
        "data/nfl2k5_espn25_fields/source/row14_endzone_N.png": "887a4dff5d12f3573c79f8b62f791fe838bc650f7306712340715a2002f6fe0e",
        "data/nfl2k5_espn25_fields/source/row14_endzone_S.png": "dd69cc073bec1f05027b508c8cbf9c6af937f3c33f35b78a3430ddc40e148f97",
        "data/nfl2k5_espn25_fields/source/row15_endzone_N.png": "a7e2700cd933518560624b003da064559db86b688be21c1fa8a768440f965f86",
        "data/nfl2k5_espn25_fields/source/row15_endzone_S.png": "dc0f4c49783ffa62b5bfb43999a78b618af6b9c0b3734d401ea6383a3b738dc0",
        "data/nfl2k5_espn25_fields/source/row18_center.png": "834a0e19d205eee21a07031c0c4b91243f362972fdc5ec06aeebf18da330c148",
        "data/nfl2k5_espn25_fields/source/row18_endzone_N.png": "c112679090ba3c8341ff7da3e1e2fb7e62e65a3302b1cd4f29c30d27fb53851e",
        "data/nfl2k5_espn25_fields/source/row18_endzone_S.png": "634fbdfab33c53caee73ba232812c4e9ca743d11c872b544789a94c57406f703",
        "data/nfl2k5_espn25_fields/source/row20_center.png": "834a0e19d205eee21a07031c0c4b91243f362972fdc5ec06aeebf18da330c148",
        "data/nfl2k5_espn25_fields/source/row20_endzone_N.png": "c112679090ba3c8341ff7da3e1e2fb7e62e65a3302b1cd4f29c30d27fb53851e",
        "data/nfl2k5_espn25_fields/source/row20_endzone_S.png": "634fbdfab33c53caee73ba232812c4e9ca743d11c872b544789a94c57406f703",
        "data/nfl2k5_espn25_fields/source/row21_endzone_N.png": "21822f04efc28392230ee99ab305747bd3e5f09a45860c5f21a3bed9c331ee21",
        "data/nfl2k5_espn25_fields/source/row21_endzone_S.png": "84da5c9e01dad05dcb7083ee951aae63ed160c1e6c48526e11edd7fe3fa750bb",
        "data/nfl2k5_espn25_fields/source/row22_endzone_N.png": "4eb6c71c40a82a1f8f5d5210322217bf02ab6d8ff6c2bb90045596c24816ee37",
        "data/nfl2k5_espn25_fields/source/row22_endzone_S.png": "79bb6f7a6f7e16e5823e383f874ba8dc3544baba4ea539f8a012f30da4d0f0fd",
        "data/nfl2k5_espn25_fields/source/row23_endzone_N.png": "355ccf53e403c233f397e94a49c000216f476fc28875c865ac5ddf291e38dbb6",
        "data/nfl2k5_espn25_fields/source/row23_endzone_S.png": "e40eb7d509c65bb693583eda0b341634e05ed7b38513c3d5f3ed43dbac95c375",
        "data/nfl2k5_espn25_fields/source/row26_center.png": "f2c0011ee24b63ff23aaa1460852f890a6c08dccac9f2408f8c9975dba329add",
        "data/nfl2k5_espn25_fields/source/row26_endzone_N.png": "65b0034bea84b28fe6f94d4b166015e7320249f1442992160fff12ad686c0402",
        "data/nfl2k5_espn25_fields/source/row26_endzone_S.png": "f51c54e5ca7a15fccbb0ec1c3b69dfa5397787246c6413ddb2bbc465daa5aeec",
        "data/nfl2k5_espn25_fields/source/row27_endzone_N.png": "a200be78183df8f5aa9e6c17df604e18106af3e5887d5d4cf5209a652c1fea6c",
        "data/nfl2k5_espn25_fields/source/row27_endzone_S.png": "25c5d80fb696442ebe0b1eb115310a757498a650d50e0289bae602f09ef7715b",
        "data/nfl2k5_espn25_fields/source/row28_endzone_N.png": "24a23f2cd6f329346803a7df853d189b714cf493b4c7e219cf9dd44bbb381b2a",
        "data/nfl2k5_espn25_fields/source/row28_endzone_S.png": "55c4045010eb808020dbff51edea7b6deae3fe2e7f69d9141579a1013db5dc0a",
        "data/nfl2k5_espn25_fields/source/row29_endzone_N.png": "01014a66dfa53906922f29425d29919ae1c1ad616a15733059f49f48f0d62e7f",
        "data/nfl2k5_espn25_fields/source/row29_endzone_S.png": "3373f4fd5ec434312fb8f77eff46c98421947283bb873afceeefb6cbc86cbe16",
        "data/nfl2k5_espn25_fields/source/row30_endzone_N.png": "8405405495d3995a5c44ac12f75ce5bc0ea77477f248fa89f76a2848650171e7",
        "data/nfl2k5_espn25_fields/source/row30_endzone_S.png": "73e68031a0ca11ed0239e4d25bb6f983718ecaf5511f861c2312e766bda78b4b",
        "data/nfl2k5_espn25_fields/source/row32_endzone_N.png": "61a42d28f0e377978fcc7ce7c82d06ef70b067745494374fa70ce95a05f896d4",
        "data/nfl2k5_espn25_fields/source/row32_endzone_S.png": "380e0e013a4f24e46a0dc560175b9f425f146073f7d09e557c21bc104795145b",
        "data/nfl2k5_espn25_fields/source/row33_endzone_N.png": "30fe1ae29857d9e2995fed755ad70567d004765240f5e1c8dd1b51198cbab870",
        "data/nfl2k5_espn25_fields/source/row33_endzone_S.png": "93c8fd44276757b1369f9b68ff8addbfcd658ac2658917b6b884fd43e12f0f1a",
        "data/nfl2k5_espn25_fields/source/row34_endzone_N.png": "b14bb4d9937ee223cbe74eb4bd1c5970a7a183bb68c4f0a0880a91a7399e5999",
        "data/nfl2k5_espn25_fields/source/row34_endzone_S.png": "4093e5d072c13de93b9452aa7217b834ee79f2808eab7084bad63d372de1bceb",
        "data/nfl2k5_espn25_fields/source/row35_endzone_N.png": "cb0c520d40447e951262695d4de67fc20cba5d96c3abea47634c859f27a7ccb7",
        "data/nfl2k5_espn25_fields/source/row35_endzone_S.png": "3581dc024173ed9158a1ce5048bf27d449e0c989535d60151588aca8bfa82186",
        "data/nfl2k5_espn25_fields/source/row38_endzone_N.png": "289845b1611c0a13e0cd11550da291da61e7282686fba0671cb8de16c15522d7",
        "data/nfl2k5_espn25_fields/source/row38_endzone_S.png": "c3573dc69e8079e9bd927f8aec5ef5440ccc93c2dfc396b29b1b0e76f2768969",
        "data/nfl2k5_espn25_fields/source/row39_endzone_N.png": "f58582f43246e201bac463959c9e77d65037a7bcea07e01bcb223f8aafb3ed64",
        "data/nfl2k5_espn25_fields/source/row39_endzone_S.png": "ea4eb7e856afb8c7f04c340f25d97094caf318737dcc3deb12a8b91c7124edc7",
        "data/nfl2k5_espn25_fields/source/row40_endzone_N.png": "a651c098b6b7af3d8d0db5a002ba2a3f9b934cb321657125ca3017c51e155c6d",
        "data/nfl2k5_espn25_fields/source/row40_endzone_S.png": "8a614473dc7da4b2e809c6c301612d1ca0214132b22f628b7fd21029896cd049",
        "data/nfl2k5_espn25_fields/source/row41_endzone_N.png": "4c8792f87a516667c2354b8e9ef1bcf4f926d19532c9ffc80d08e52915fc5579",
        "data/nfl2k5_espn25_fields/source/row41_endzone_S.png": "43fb0c5cff08a9b7456b5e4f6b17958e6936773692e67e7f430846bce01ed029",
        "data/nfl2k5_espn25_fields/source/row42_endzone_N.png": "098412ad8aa221c03fa2d17feba8a6efb17cf57feff85ad1439fa4ea72b9a56b",
        "data/nfl2k5_espn25_fields/source/row42_endzone_S.png": "bea9dc2c556e35af2d313e9d072b797dc683d18084c70e83f87d6bcc62202930",
        "data/nfl2k5_espn25_fields/source/row44_endzone_N.png": "c92cdf18a8a21b3de202e3b89f32cd488dfb88708ed2adc55636cbbb413616af",
        "data/nfl2k5_espn25_fields/source/row44_endzone_S.png": "1b293c6b04937cc4636d5cec77a6d07305ecd14454d0824463da771dfa9fc3c2",
        "data/nfl2k5_espn25_fields/source/row45_endzone_N.png": "627fae2596925204839560e340a51f554ebd51e67c3aaee94df0a9165004f903",
        "data/nfl2k5_espn25_fields/source/row45_endzone_S.png": "e993ec613694f9e76b4dc2bd7410d344e663639b301d62220fa581a67f81d7dd",
        "data/nfl2k5_espn25_fields/source/row46_endzone_N.png": "da1222e48ac1ae391c83c26ca863edfe9229b4dcf60da785d0920fb163b77283",
        "data/nfl2k5_espn25_fields/source/row46_endzone_S.png": "14b19a35816552db46fe53291fbf8ac12b7c9ca04b4b0cb01a6f7176ccd341f9",
        "data/nfl2k5_espn25_fields/source/row47_endzone_N.png": "6813b905e67e920dc0b4d145fb9dc30f5af786ca5cd6a7669f265ee2e567b4de",
        "data/nfl2k5_espn25_fields/source/row47_endzone_S.png": "dba4ff0420a954a2b6c22f133ef8830f2f72d9ae389f15ef18658d40b12380aa",
        "data/nfl2k5_espn25_fields/source/row48_endzone_N.png": "2c8d077c83bd3363a8daee06565fe409024fd0412bc3fd77afc58cd28cab4a16",
        "data/nfl2k5_espn25_fields/source/row48_endzone_S.png": "ba7f05ccb064912713b70ca999210eb0e7f9e8be360a79e5515073de8eab8ad2",
        "data/nfl2k5_espn25_fields/source/row50_endzone_N.png": "911e23977aee3d90823857449ccd7238850cab4771c26b84ef53a0289c686048",
        "data/nfl2k5_espn25_fields/source/row50_endzone_S.png": "a947362a380a50c70925e07f7041ce6e594fe1010703cbdd38e2e5ce2db25725",
        "data/nfl2k5_espn25_fields/source/sb25.png": "19e1ded7316192392eeb993a8ce0f74a0801cc50d1d4ed433b3d9f9c3cf4d130",
        "data/nfl2k5_espn25_fields/source/sb25.svg": "da93e4a9d1bd685d8b1aab9fc7a90150e9e9e8a3c9fe2f4413338f78c7ba3442",
        "data/nfl2k5_espn25_fields/source/sb32.png": "5e25faaf1d4cb612ca3c21aaa6081c56baa98d25d2bcfb5b9036697d5bf83280",
        "data/nfl2k5_espn25_fields/source/sb34.png": "9aeea8a326ed302273d9c5d97cb5024a6ea2b73dd5b9a146a58440ed888ccfee",
        "data/nfl2k5_espn25_fields/source/sb36.png": "3f861a3253574e4d0f447365ee34c487fc1e493a74e08abd95330599a8c798e0",
        "data/nfl2k5_espn25_more_teams/steelers_2025.csv": "518c1cdb418ce402f6cab0e4c42532c0dfa55c991d4eef9724649fe6a7e2521a",
        "data/nfl2k5_espn25_more_teams/bengals_2025.csv": "23211f988adc97ea41c377f8c3c7bc2fe5f3f12e9d92ce42352dfdce0960a5db",
        "data/nfl2k5_espn25_v04_profile.json": "3f1f60561c14a2a09fd23dae09d0fad6dbc5f2b49cf14cc171c4cb1a3ad5351d",
        "data/nfl2k5_espn25_unc_bowl.json": "4a632282beb8cde62ffaa5e896ea22bc89eb67b54ba49a2e19a694c02abb9b18",
        "data/nfl2k5_espn25_fields.json": "da73bb1f1a838fe642d8537596565600bd6febb1771b0829eb6e977bc056da4f",
        "data/nfl2k5_moment_goalposts.json": "256d15573650a24a24b83953d627d0bede614aff6587c16c3eb060ad48329acf",
        "data/nfl2k5_moment_venues.json": "960f1f61f5395ce65117b32840f38f28dcb31fbbc1e793eda9dc39c7853b5fb0",
        "data/espn25_previews_2026.json": "8ae83e55f9ad9cc5a9fa1f5ed0efe4c0802522b7332c5ef3e3b594ca472e287c",
        "data/nfl2k5_era_rules.json": "fab269783f2f4524b01e031a15de8156629a6728d86249b9402822594778d1e4",
        "data/nfl2k5_stock_books.json": "87d779bb2be3c4b20b901c4afa0a620bb4b0aae29ef833bc4440a38c396417fd",
        "data/nfl2k5_front_schemes.json": "1026ff34b0de28362b25f1019c5ef2ccd8b706bbee41f6ce77b26b6efc07a626",
        "data/nfl2k5_moment_coaches.json": "3b38c524f4a861ac100e96f847939f8d12ffe62c6eef3aba93e7f33144e9148b",
        "data/nfl2k5_moment_stats.json": "1aea510df6cd581b7d992b640f3c0be0b07a89308592f691cda6c87dde052cc2",
        "data/nfl2k5_moment_playbook_eras.json": "756d99acac597ceb86026264c23e67ab038fd765de19692ccfdbdc65f3ca61c9",
        "data/nfl2k5_modern_venues_2026/numbers/manifest.json": "fa9ca79e6175b4b50fb624841b4cb6aea47f9a9f910e891723de1fdf9cfed089",
        "data/nfl2k5_modern_venues_2026/numbers/block.png": "1a6e2517c6f5f745a0a98712c4f19870ae964c8f81563d99351f2a1948d56718",
        "data/nfl2k5_super_bowl_logos/manifest.json": "66193ac79c75a1da67f44948392f4a3885f31733e255448905f410409d1a28a8",
        "data/nfl2k5_super_bowl_logos/brands/abc.png": "40089deda13e1be30afd5c0c7d07dccc5c9918507541497c6575f2d67c71896a",
        "data/nfl2k5_super_bowl_logos/brands/cbs.png": "7b7b3482fcfbe90b783800457d85404949d717a6ff8ba1534576015609193ccc",
        "data/nfl2k5_super_bowl_logos/brands/espn.png": "89dc92e83232b12e19e0efcac3d44e2ed61c3a38b4f06d82384a8802cb430679",
        "data/nfl2k5_super_bowl_logos/brands/fox.png": "845daec20b134a879a8e9e1662c4e909277271d0814810907e788e3ae928ac6b",
        "data/nfl2k5_super_bowl_logos/brands/nbc.png": "79763cd0c5f72ea741875e3c6e353b79dc67e5a4f8a05f90e7caff08a7afaba4",
        "data/nfl2k5_super_bowl_logos/super_bowl/LI.png": "35d9ceb588c55bcdb5b01a1e8d86e0b1c82df1d5d765299a11833b628a772cda",
        "data/nfl2k5_super_bowl_logos/super_bowl/LII.png": "4d29dc721ef89c2557c5fd5d6827d6daca27ec9197bd50fe67cba496f31e7f33",
        "data/nfl2k5_super_bowl_logos/super_bowl/LIV.png": "5fd1a4ea668e38570f7659a6ab2944b9234d227728c0b90180cef39e113a5a82",
        "data/nfl2k5_super_bowl_logos/super_bowl/LVI.png": "97fc8e02cc63059aaeac49deab4281da5bc96a8eba9fa506e250323fd67fa28d",
        "data/nfl2k5_super_bowl_logos/super_bowl/LVIII.png": "0e581e17c81fff5aca3d796155e6bf51ba485a9bd3806c1d33f89c1577b6f46a",
        "data/nfl2k5_super_bowl_logos/super_bowl/XLII.png": "16f8f8a31110b95ff134e38b850246fe234e96fc2df9a63ae004ad31d9acd4a8",
        "data/nfl2k5_super_bowl_logos/super_bowl/XLIII.png": "7dd945a696a03d435f48ba52f6731c938ffc55f5d891eae31af104d73ace7e94",
        "data/nfl2k5_super_bowl_logos/super_bowl/XLIV.png": "260a7d63a99f1aab41a29a90918afd37a2d64843a579a11ea47771c5b0056c82",
        "data/nfl2k5_super_bowl_logos/super_bowl/XLIX.png": "b19dfb80f755903da9f2eef5fb21eb13628364b0e98849d41de7e515659eca9c",
        "data/nfl2k5_super_bowl_logos/super_bowl/XLVI.png": "04c1f3e83de84cd8710ae35eb9d1feec0bd77c2089c2c2e4ae0fe5fc7b7f0ffe",
        "data/nfl2k5_super_bowl_logos/super_bowl/XLVII.png": "2d54985087ffe8ebb8133db8760ab1daab8762eddc20ec6ae20b2d66dab4fac5",
        "data/nfl2k5_super_bowl_logos/super_bowl/XXIII.png": "130f5e2405c2c23789e1810f7650dec47b7a31e2b64eb01d88365d9aa87c16f3",
        "data/nfl2k5_super_bowl_logos/super_bowl/XXV.png": "85f2451c355d842f98eaace1a02d708856a644e620b40e0481c6de78baff1c88",
        "data/nfl2k5_super_bowl_logos/super_bowl/XXXII.png": "bc42798dfc53c7373bbbe8b0dad65216fbb248c260a256782116c2e69ce939ac",
        "data/nfl2k5_super_bowl_logos/super_bowl/XXXIV.png": "de5bb748d5dd335625baff3bf887aeac6df85f5a31dcea19fd359d798d0ed327",
        "data/nfl2k5_super_bowl_logos/super_bowl/XXXVI.png": "8915b4f6a5b523cea6020e47614ea969b53ca9926029b52052e24a71b7916819",
        "data/nfl2k5_super_bowl_logos/teams/CIN_1988.png": "6d382e567a2188ae78de7520b1dcccd14e4a858af27f085bb91064a41216c636",
        "data/nfl2k5_super_bowl_logos/teams/NYG_1990.png": "a43168ac74d9a9cf8e04f739a331086f3797aeeeafe2652b2cd2d4373d9ee0e2",
        "data/nfl2k5_super_bowl_logos/teams/STL_1999.png": "ed4fbc293ede71dc5f39fa7f9db6c4928c117e8abd1faaeb7cba19b2cacd566a",
        "data/nfl2k5_super_bowl_logos/teams/STL_2001.png": "8bfd3de6c9c804ccfca5b356359e7125475b4040d0730b53da4f47e21ffad1dd",
        "data/nfl2k5_modern_color_pins.json": "670a9f1df1abe67c12d373318e4bca0c388e9e7a3c54d42e44ad37f52981719d",
        "data/nfl2k5_modern_helmets/geometry.json": "3bd4a970dd27a614040c307fcca3f66e4a83fef6d008a8efa1384e4b76ef0c7a",
        "data/nfl2k5_modern_helmets/pins.json": "6f4c8816369aec0087b52df23b2ae62a2fe1312817a118eeaade5ab52bd51a28",
        "data/nfl2k5_presentation_standalone.json": "69e6589ffbdda17fc3a5f3b9201ffc206bd0c347e54596b38a88cfeb1d454f36",
        "data/nfl2k5_official_marks_catalog.json": "36f83b0ef43441c834c7abc17834d70b426e704d4cc8c9b77044d2b685698cf3",
        "mod_editor/data/nfl2k5_crib_catalog.v1.json":
            "c78801144df2f070e003ba458c5affa15a52cc00221cc1a3d9983f1fbf172cd8",
        "mod_editor/data/nfl2k5_equipment_chain_pins.v1.json": "1057ef17a6680edf64d83ce563f168e5c6850c63c7b212423d70486838591295",
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
        "tools/nfl_tset_png_import.py": "5554b629aeaa5f2733a8dc493801d9680546617de676779ea4944e1210e1f0b6",
        "tools/nfl_txtr.py": "1c8b7bb31f47c9735d73c1d871f2a43964f011aa2e983980c1274a73390dd5db",
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
        "mod_editor/core/platform_compat.py": "b63521c9b17119b87558aff36a5a914d0c3fdd42e96240cf7de20065ead644d7",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_texture_patch.py": "4f8f69133a527c5792b01afb59d3b2a577f2ed28ee5e6f94154b274f530c28a2",
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
        "mod_editor/core/platform_compat.py": "b63521c9b17119b87558aff36a5a914d0c3fdd42e96240cf7de20065ead644d7",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_pants_color_transport.py": "658a124fef839e5252dc89dc6fcd4736698cd2b6a6b053c6f9935bbc75e12871",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_texture_patch.py": "4f8f69133a527c5792b01afb59d3b2a577f2ed28ee5e6f94154b274f530c28a2",
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
        "mod_editor/core/platform_compat.py": "b63521c9b17119b87558aff36a5a914d0c3fdd42e96240cf7de20065ead644d7",
        "tools/apf_helmet_color_transport.py": "86d4fbf1b43b2dfb02b6d3e35c4829ccaf3b0818edf5bab60903595269a933cb",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_texture_patch.py": "4f8f69133a527c5792b01afb59d3b2a577f2ed28ee5e6f94154b274f530c28a2",
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
        "mod_editor/core/platform_compat.py": "b63521c9b17119b87558aff36a5a914d0c3fdd42e96240cf7de20065ead644d7",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/apf_shoulder_color_transport.py": "ba654154c990fad1b45760cfd325b352def357e5f1030915323591128e0a9b46",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_texture_patch.py": "4f8f69133a527c5792b01afb59d3b2a577f2ed28ee5e6f94154b274f530c28a2",
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

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
    backend_module_sha256 = "569d69aa2135d6c5c1c722edc40805d54dc17571ad835406252c7cc55ff4fac7"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/nfl2k5_espn25_fields.py": "337b3f2125434cbbe97c3d4fe689304da22a3e7d678bdaa46b57122a8f306ca3",
        "mod_editor/core/exact_math.py": "31b977deeda09cbb68dcde7561ea54c9ebfad2cb4ff74f6601d681e3f4d68564",
        "mod_editor/core/nfl2k5_allegiant_model.py": "9db239e9a75dced1ffc00bcef598974e2097b7dd8fdb16342fff3a4efa6bdf02",
        "mod_editor/core/nfl2k5_allegiant_venue.py": "adf75beb901280fa9ddb2e5a0e88364fa178437bd39345598f02793b7b0ae4c1",
        "mod_editor/core/nfl2k5_att_model.py": "717c1a98b55355507a3143563fd30e020de5e992589c868e544faa3e9ea8e7b1",
        "mod_editor/core/nfl2k5_att_venue.py": "8b2ffc6f8bcf7459dc74047a055086073db5f53764a511df4621cbbb4e0460b7",
        "mod_editor/core/nfl2k5_board_kit.py": "227c1b9b04be942f49741d3fcd50fb42e10a9c94cd910030039ea07aa7b4070f",
        "mod_editor/core/nfl2k5_everbank_model.py": "8b4af825bc0f7c1f692b8be365de6f6cc6e3d577b5923075470e4f34abf23d4f",
        "mod_editor/core/nfl2k5_everbank_venue.py": "c9800b21db596449d88efb36e3308db953ad8c8a840090e15ccfef4f98451a8c",
        "mod_editor/core/nfl2k5_gillette_model.py": "054bf85432de4e9d7342e9216d7e2db1346b7ab0ad8cc5aa3172e125f8383186",
        "mod_editor/core/nfl2k5_gillette_venue.py": "a2fc078b343140004d17875f06849d9484b9155f6d6d033380112f73f8a88ba4",
        "mod_editor/core/nfl2k5_hard_rock_model.py": "6886b12c64f7d707090d5e607b723452b67041979b062e797c3da6a98eb0f7c0",
        "mod_editor/core/nfl2k5_hard_rock_venue.py": "c94f5e0986ce307ace72f74272da8647bee54296964daa63679932ee66cc47ee",
        "mod_editor/core/nfl2k5_highmark_model.py": "6cd06ba78c23b5ea577f8d69ede22c85e5c82935ac3853588bdef1179cf765dc",
        "mod_editor/core/nfl2k5_highmark_venue.py": "caf65f301a9f0c1e97bbc76736fd88188c236b98a002157d5998d40392dce46f",
        "mod_editor/core/nfl2k5_lambeau_model.py": "05b918132361ac82541ce80c24ed426e6e6a5838a740bcd1a15e76a17ed65dce",
        "mod_editor/core/nfl2k5_lambeau_venue.py": "6e66f5f4872438c13d3d77df0980e5b3b76c7851601b449a093d546482b39af8",
        "mod_editor/core/nfl2k5_levis_model.py": "c1df7a5761e8a6795282f296ef117f06ef1bf84456ea049e32a8ae79e2b7d215",
        "mod_editor/core/nfl2k5_levis_venue.py": "6f6e2c5ce5d2d38a13e3a73c1f7e827829b921813671e155a7d8f1d26354ad87",
        "mod_editor/core/nfl2k5_lucas_oil_model.py": "3aa1b7f3ec376c645ed5556f7c5896a5fe8278a75e187a5e4b79ffca7d3f53fb",
        "mod_editor/core/nfl2k5_lucas_oil_venue.py": "106be9ee3376742f2ca9caddf6467f5ccd88f74955010936666047e0c54e1bac",
        "mod_editor/core/nfl2k5_mercedes_benz_model.py": "6e7a26b12a24b0a9fe49840eb5a4cb8ad5d9c5e9d5a910c091982ace6390c953",
        "mod_editor/core/nfl2k5_mercedes_benz_venue.py": "a35ced58f2c17e3eb0a088a79ddbcfbbd47a8d40b59d79af84a83051f39b2d21",
        "mod_editor/core/nfl2k5_metlife_crowd.py": "ff42efdd0aace6a5622119e9a265329a4865f7365d74c54d1d70a7989e3d1be9",
        "mod_editor/core/nfl2k5_metlife_model.py": "1b4338cb0eb990ff92445e324560a8174cae9bd8e214c8181550bdfc52d1152e",
        "mod_editor/core/nfl2k5_model_fan_art.py": "78d13e31cabe730a20f0f14124f2693b03b7de00ad89ecea51432e1bb45bc259",
        "mod_editor/core/nfl2k5_modern_metlife.py": "02ba1b8c5815e756ba003c2e9c44d7156f8b88a36e486f2531bc4afb8fe66abe",
        "mod_editor/core/nfl2k5_modern_surfaces.py": "217ad394f0d4f32367c27e6dc8257232150f582df1e0382e2002eeeab40210c3",
        "mod_editor/core/nfl2k5_modern_venues_2026.py": "99299473ee8493ba3aed353d7999ff481ed33731961e4806dae231c648dfc336",
        "mod_editor/core/nfl2k5_scne_builder.py": "02472ce2bbdab214a89b6d6afefe0d506974d50833cb9763ef4548870934d80d",
        "mod_editor/core/nfl2k5_sofi_crowd.py": "a3d8c12bf3da19bc35ab115c7e04220b5fd5e36e8ba272c91c9ac2b156c106dc",
        "mod_editor/core/nfl2k5_sofi_model.py": "acc7ea7629f2a47f3853d766f81f9ce50213bd85bb6432b384d2d8ebc8acf051",
        "mod_editor/core/nfl2k5_sofi_venue.py": "754b26053df033fd0f8265490eab5c8c780bac266142cc41f5695a4113eadb9b",
        "mod_editor/core/nfl2k5_stadium_environment.py": "a7d447b2e8146b260aa113d08e8a8f36c118b7d6741ab58dc99ffb153b780e38",
        "mod_editor/core/nfl2k5_stadium_shared_art.py": "9d7e4ecad06d863a9cad8b3dd7c35422fd490f0690e351fe4217fd0149237e36",
        "mod_editor/core/nfl2k5_state_farm_model.py": "b7d37693a08d6001f1baab744a5bcf14eaf8f1633f02848b4c0bb2421f956d3f",
        "mod_editor/core/nfl2k5_state_farm_venue.py": "05a3163dae06970f52263dda7994f798879843f915c5cba42b541584d26548c7",
        "mod_editor/core/nfl2k5_usbank_model.py": "9d250d6af1411ddb289a113323a3fbcbdba79cce211b13623f014459e621aeb8",
        "mod_editor/core/nfl2k5_usbank_venue.py": "388044c9675a4d76ac615772e6772b52f4107f3b93c76a9cc6f342e2a30901a0",
        "mod_editor/core/nfl2k5_anniversary_pack.py": "ce18514a50889f3bb2180b07890fab142de49fe416f83470a1ef3f0a33c86acc",
        "mod_editor/core/nfl2k5_marks_store.py": "cc0049a7b10fdd31ed43c183e29470d920e0bf8af6b24b704e989095c0dc0659",
        "mod_editor/core/xdvdfs_compact.py": "915f970f10d9bda7cee08652bceba9117b075433e0c88406e6749be08194f8e1",
        "mod_editor/core/nfl2k5_moment_venues.py": "7b3f92ee60c1ed050290a6958fb1a4d01c12d25d71f4d4411985b5f78a7122dc",
        "mod_editor/core/nfl2k5_historic_styles.py": "27de168580d3299d71b62c0e5fbc8ff949323c2aeac27f7ac8f2b721a57665b4",
        "mod_editor/core/nfl2k5_era_rules_code.py": "31a59de504f1d3c80db7823240bc1854324a544e48c572f5cb3518c0a1da6402",
        "mod_editor/core/nfl2k5_era_rules.py": "2bba6bab5470da6827fad55ee2cfa1cb70056ccab5fd289de13dceeff87a5bd7",
        "mod_editor/core/nfl2k5_stock_books.py": "b4ea9ee618973180eaae3f6a82fe8d3988e71ebe2d67b0b936029d7eab029806",
        "mod_editor/core/nfl2k5_project_fit.py": "ca9551a8f1d89e6435acba870daa3902ede49a84a2a9e5d1adf5b5eb53eeeb7a",
        "mod_editor/core/nfl2k5_my_career_prospects.py": "7c326fbfdaf090c6bf3394af99d266c8f069be8e8a49919f7503e14db9b09c45",
        "mod_editor/core/nfl2k5_rules_patch.py": "b1f5fe57fc2ec7b71479493014955db4455c9837ebde6e06e145969fba76a798",
        "mod_editor/core/nfl2k5_coin_defer.py": "403dddd1c40718d1284f008ac52222a0e2cbf0b9109941d8f16949739f6be5e0",
        "mod_editor/core/nfl2k5_coin_defer_code.py": "9eefd8074b0fec01375cd266339ca0810e660af91dffbe275acaf0e5b927b0a2",
        "mod_editor/core/nfl2k5_decided_clock.py": "cf27be38419bf9443c50fbed9de5c5deb08c620613af84869e60683f1b135a5b",
        "mod_editor/core/nfl2k5_decided_clock_code.py": "83d7961b291a0fe08d3ac1518ec7b97ab4489f830c20c04bdd99626344d53c58",
        "mod_editor/core/nfl2k5_cpu_scrambles.py": "6a5b913f4c6407b64548e979ff59e1f66b2688f9ddccc20c4ed887e3209d5576",
        "mod_editor/core/nfl2k5_cpu_scrambles_code.py": "6519b049d4f570dc92c58ede831a521ebface07ce23fb8406eb42318bbf52a92",
        "mod_editor/core/audio_conform.py": "b71528aa23b6dca49bbe023477920661da77cd7c34610dc8f6962be3a0cc9156",
        "mod_editor/core/build_feedback.py": "bb9ee63c389bf19024c88929c5947bb18e98c608397dab1052b8c7aaf8079572",
        "mod_editor/core/build_io.py": "7e1e04876981fb08280560a03c19d61f2aa37fdac4a10c8db65e3fb5025d7887",
        "mod_editor/core/equipment_palette.py": "2886a97ef4dd0d2a2feedd2698dcd521ae64d8992e36d9f2e0fa121b37be6876",
        "mod_editor/core/equipment_reporting.py": "790bf6896f8f50caedf6ed5409b1aa0d759d0129886c8ba6c1000e7528496e6e",
        "mod_editor/core/equipment_staging.py": "75b8417df9e8c6ac638367faad38030c46a903af7c451ceacb8646693601b0c6",
        "mod_editor/core/errors.py": "4624e80f063f1e7db69ec6c20d2703f01eec49728b02c88792ccb309bd742de0",
        "mod_editor/core/image_use.py": "17022719327a2c98e5b49837044bf31d652e68a74a145ac162cd4bdfad3b07a2",
        "mod_editor/core/json_stream.py": "5933752561dd8b519a301c18ec1d14f13a457f58e6ae337984f543ab2b0838b0",
        "mod_editor/core/metadata_cache.py": "49874cc7f12cc0d36d15b9355dbca64ffe95590ba7582b460738b05aabcd9024",
        "mod_editor/core/mod_build.py": "8c8af3b5ada40b52dae9965906e237762082d7063d46aa43cfe873c12863fab3",
        "mod_editor/core/mod_build.py": "8c8af3b5ada40b52dae9965906e237762082d7063d46aa43cfe873c12863fab3",
        "mod_editor/core/model.py": "292f0c5444e32f5cea000fd3cabd6963d7d805a5434dcbc364a36ca2c0f0d228",
        "mod_editor/core/modpack.py": "158926f7b25e66143b13318bd0767491c2cabd8ebdedadf3927cd720d23820c6",
        "mod_editor/core/modpack_files.py": "f9fdb22d460b1d03477c1dc6b6608c5d09b8d4fe1b68d290f9cd96c712f21546",
        "mod_editor/core/modpack_ops.py": "485d2d8e3caa9c5096de406768918cde1bd8d8b15ddba15a299e0bd0e8099f4b",
        "mod_editor/core/nfl2k5_abilities_runtime.py": "5d801a96d1c50b87d67cda5bd4b85ad007376669d430f84f31a857fb922b367e",
        "mod_editor/core/nfl2k5_abilities_runtime_code.py": "30da3adf1c622a8a650e090e0380e4cf23e725b8215d0e79dd2acf03270d370f",
        "mod_editor/core/nfl2k5_accel_ramp.py": "95014c753d46faed2e75e545d992794bb62965a9bbe6407057d3626395c6e862",
        "mod_editor/core/nfl2k5_accelerated_clock.py": "079ce771155f78b33591000e3f622671dd947a5357e14df165f245331c3bbdb1",
        "mod_editor/core/nfl2k5_accelerated_clock_code.py": "4ff06a448a9777ad24389f490169fa2de981f7e865aabf74e8d5f9b79857c317",
        "mod_editor/core/nfl2k5_animation.py": "2ae98a97fb78b06050a5bfc9ab8a838b30ea36d7a9514132893debe4441b44b6",
        "mod_editor/core/nfl2k5_animation_bones.py": "b82275d45fd4f0b34aaa4613e0ea266724f14270c9069650b5aded3a3f929eb8",
        "mod_editor/core/nfl2k5_animation_import.py": "a1bf3c0b4c15835c946e0373fb2185dbaf748bae0d508a0698f6f4db92d5c50f",
        "mod_editor/core/nfl2k5_animation_math.py": "2b0c8cd4f700a6426e6fc83d605f4db8d14488f2825acd540da0a79586a4ed7e",
        "mod_editor/core/nfl2k5_animation_xbe.py": "3a384b0e5c731e4ec4d11f78ad74223990b0130f99914d1bc5385d1d1da186ad",
        "mod_editor/core/nfl2k5_anniversary_kickoff.py": "597684aa0ab7e27a03462483d24cd2bdfcf19cd191335511b9c8dd24c19b34b4",
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
        "mod_editor/core/nfl2k5_build_service.py": "e22d670a851ddc493d913d741818a9cc567f5bc827ef3c44da12d48b12439438",
        "mod_editor/core/nfl2k5_build_settings.py": "80c3c7a18e4e72d092aa11bd4984adf46250894a75b42c13124fb2e6169be83d",
        "mod_editor/core/nfl2k5_build_service.py": "e22d670a851ddc493d913d741818a9cc567f5bc827ef3c44da12d48b12439438",
        "mod_editor/core/nfl2k5_build_settings.py": "80c3c7a18e4e72d092aa11bd4984adf46250894a75b42c13124fb2e6169be83d",
        "mod_editor/core/nfl2k5_midfield_art.py": "96fe077342c387121ed3901b517b8b588326c3203ab30adad3e7f88d6b728e73",
        "mod_editor/core/nfl2k5_split_endzone_art.py": "0f49082fe468e6a0ae2371a4a26a3c5eeb9938afcedf77d6e10141eaa4a8616a",
        "mod_editor/core/exact_math.py": "31b977deeda09cbb68dcde7561ea54c9ebfad2cb4ff74f6601d681e3f4d68564",
        "mod_editor/core/nfl2k5_allegiant_model.py": "9db239e9a75dced1ffc00bcef598974e2097b7dd8fdb16342fff3a4efa6bdf02",
        "mod_editor/core/nfl2k5_allegiant_venue.py": "adf75beb901280fa9ddb2e5a0e88364fa178437bd39345598f02793b7b0ae4c1",
        "mod_editor/core/nfl2k5_att_model.py": "717c1a98b55355507a3143563fd30e020de5e992589c868e544faa3e9ea8e7b1",
        "mod_editor/core/nfl2k5_att_venue.py": "8b2ffc6f8bcf7459dc74047a055086073db5f53764a511df4621cbbb4e0460b7",
        "mod_editor/core/nfl2k5_board_kit.py": "227c1b9b04be942f49741d3fcd50fb42e10a9c94cd910030039ea07aa7b4070f",
        "mod_editor/core/nfl2k5_everbank_model.py": "8b4af825bc0f7c1f692b8be365de6f6cc6e3d577b5923075470e4f34abf23d4f",
        "mod_editor/core/nfl2k5_everbank_venue.py": "c9800b21db596449d88efb36e3308db953ad8c8a840090e15ccfef4f98451a8c",
        "mod_editor/core/nfl2k5_gillette_model.py": "054bf85432de4e9d7342e9216d7e2db1346b7ab0ad8cc5aa3172e125f8383186",
        "mod_editor/core/nfl2k5_gillette_venue.py": "a2fc078b343140004d17875f06849d9484b9155f6d6d033380112f73f8a88ba4",
        "mod_editor/core/nfl2k5_hard_rock_model.py": "6886b12c64f7d707090d5e607b723452b67041979b062e797c3da6a98eb0f7c0",
        "mod_editor/core/nfl2k5_hard_rock_venue.py": "c94f5e0986ce307ace72f74272da8647bee54296964daa63679932ee66cc47ee",
        "mod_editor/core/nfl2k5_highmark_model.py": "6cd06ba78c23b5ea577f8d69ede22c85e5c82935ac3853588bdef1179cf765dc",
        "mod_editor/core/nfl2k5_highmark_venue.py": "caf65f301a9f0c1e97bbc76736fd88188c236b98a002157d5998d40392dce46f",
        "mod_editor/core/nfl2k5_lambeau_model.py": "05b918132361ac82541ce80c24ed426e6e6a5838a740bcd1a15e76a17ed65dce",
        "mod_editor/core/nfl2k5_lambeau_venue.py": "6e66f5f4872438c13d3d77df0980e5b3b76c7851601b449a093d546482b39af8",
        "mod_editor/core/nfl2k5_levis_model.py": "c1df7a5761e8a6795282f296ef117f06ef1bf84456ea049e32a8ae79e2b7d215",
        "mod_editor/core/nfl2k5_levis_venue.py": "6f6e2c5ce5d2d38a13e3a73c1f7e827829b921813671e155a7d8f1d26354ad87",
        "mod_editor/core/nfl2k5_lucas_oil_model.py": "3aa1b7f3ec376c645ed5556f7c5896a5fe8278a75e187a5e4b79ffca7d3f53fb",
        "mod_editor/core/nfl2k5_lucas_oil_venue.py": "106be9ee3376742f2ca9caddf6467f5ccd88f74955010936666047e0c54e1bac",
        "mod_editor/core/nfl2k5_mercedes_benz_model.py": "6e7a26b12a24b0a9fe49840eb5a4cb8ad5d9c5e9d5a910c091982ace6390c953",
        "mod_editor/core/nfl2k5_mercedes_benz_venue.py": "a35ced58f2c17e3eb0a088a79ddbcfbbd47a8d40b59d79af84a83051f39b2d21",
        "mod_editor/core/nfl2k5_metlife_crowd.py": "ff42efdd0aace6a5622119e9a265329a4865f7365d74c54d1d70a7989e3d1be9",
        "mod_editor/core/nfl2k5_metlife_model.py": "1b4338cb0eb990ff92445e324560a8174cae9bd8e214c8181550bdfc52d1152e",
        "mod_editor/core/nfl2k5_model_fan_art.py": "78d13e31cabe730a20f0f14124f2693b03b7de00ad89ecea51432e1bb45bc259",
        "mod_editor/core/nfl2k5_modern_metlife.py": "02ba1b8c5815e756ba003c2e9c44d7156f8b88a36e486f2531bc4afb8fe66abe",
        "mod_editor/core/nfl2k5_modern_surfaces.py": "217ad394f0d4f32367c27e6dc8257232150f582df1e0382e2002eeeab40210c3",
        "mod_editor/core/nfl2k5_modern_venues_2026.py": "99299473ee8493ba3aed353d7999ff481ed33731961e4806dae231c648dfc336",
        "mod_editor/core/nfl2k5_scne_builder.py": "02472ce2bbdab214a89b6d6afefe0d506974d50833cb9763ef4548870934d80d",
        "mod_editor/core/nfl2k5_sofi_crowd.py": "a3d8c12bf3da19bc35ab115c7e04220b5fd5e36e8ba272c91c9ac2b156c106dc",
        "mod_editor/core/nfl2k5_sofi_model.py": "acc7ea7629f2a47f3853d766f81f9ce50213bd85bb6432b384d2d8ebc8acf051",
        "mod_editor/core/nfl2k5_sofi_venue.py": "754b26053df033fd0f8265490eab5c8c780bac266142cc41f5695a4113eadb9b",
        "mod_editor/core/nfl2k5_stadium_environment.py": "a7d447b2e8146b260aa113d08e8a8f36c118b7d6741ab58dc99ffb153b780e38",
        "mod_editor/core/nfl2k5_stadium_shared_art.py": "9d7e4ecad06d863a9cad8b3dd7c35422fd490f0690e351fe4217fd0149237e36",
        "mod_editor/core/nfl2k5_state_farm_model.py": "b7d37693a08d6001f1baab744a5bcf14eaf8f1633f02848b4c0bb2421f956d3f",
        "mod_editor/core/nfl2k5_state_farm_venue.py": "05a3163dae06970f52263dda7994f798879843f915c5cba42b541584d26548c7",
        "mod_editor/core/nfl2k5_usbank_model.py": "9d250d6af1411ddb289a113323a3fbcbdba79cce211b13623f014459e621aeb8",
        "mod_editor/core/nfl2k5_usbank_venue.py": "388044c9675a4d76ac615772e6772b52f4107f3b93c76a9cc6f342e2a30901a0",
        "mod_editor/core/nfl2k5_modern_arrowhead.py": "afbe211c6996e401b7625a006e01cff4b2f9e38b65339cd7d727ebbb5cff5177",
        "mod_editor/core/nfl2k5_modern_color.py": "46ec57de1dd69359253d623d0961d88d923294539e7979f3407a28325e3ef558",
        "mod_editor/core/nfl2k5_bump_strength.py": "79f9264fbe0813db9be66f22e35f8944e35b92ae415132d819eda50920e41bb0",
        "mod_editor/core/nfl2k5_calendar_engine.py": "24dc9c152a79c81d75232b556f82ebc3ab6892a662c3d8071a4da85a6cd45644",
        "mod_editor/core/nfl2k5_calendar_engine_code.py": "9b43e835f1df76f85ecb13e7ef593d2eee884a1fa82fe41ea3d813186445ca22",
        "mod_editor/core/nfl2k5_camera.py": "ad21c4d301ab26ed5786383f0b3aa76aace895c2c673b38289e41b225ee593be",
        "mod_editor/core/nfl2k5_catch_slider.py": "0ea12e1f558463538a154f50c38036389a8c0432c7ba55ac2862cd706b85498f",
        "mod_editor/core/nfl2k5_cave_oracle.py": "8be24dd71d7503dba209061747bb74c439833970978a045a96f740cedafb940e",
        "mod_editor/core/nfl2k5_college_check.py": "b4752a4a015c2b39a19e9887ef67ffdcc2b2b9ac044642a45201a2fae500709d",
        "mod_editor/core/nfl2k5_compile_cache.py": "0ef3f49e681793ba7b251f5c5e887910e87a4c6ffbd58b5d4146a056b3123480",
        "mod_editor/core/nfl2k5_coverage_slider.py": "e63025985e5e2a1f9e18fbc8f7375b16689f2b81bdb61766d86f8d8ee515fc0b",
        "mod_editor/core/nfl2k5_coverage_trail.py": "68b6548fc60cf8cbed4a912403b6323c44818eeba358cdc28fa8090642a3e969",
        "mod_editor/core/nfl2k5_coverage_trail_code.py": "746874dbef2fbf16355affd2b373840fb96e235fc0f2592c9c2858c826080e66",
        "mod_editor/core/nfl2k5_cpu_money_downs.py": "dc79309b430782d1271976fefb2be42f0a45d6fb89e6bfdc85775e776a9418ee",
        "mod_editor/core/nfl2k5_cpu_money_downs_code.py": "b720d4fa432fbc6ae366a8e2018aefde8cbe9531aef5007392c352b895e3b31a",
        "mod_editor/core/nfl2k5_crib.py": "01f98c38f1dcf6a6175e017b68794fc16011b437763eb42d8d3810430760fb8c",
        "mod_editor/core/nfl2k5_crib_electronics_targets.py": "6d474769ee594d792d11f112fb3e39da8bd2ae8117bae92231956b4305112e2b",
        "mod_editor/core/nfl2k5_crib_geometry_writer.py": "d1cb53a2e801cfd14c469dc58cf8e433a8045e93e724ed502073a1cb2b8d0d78",
        "mod_editor/core/nfl2k5_crib_reclaim.py": "36071e997a738af905d30dde90efc3eaa59ddb9368debf1fdcea425d0aad064a",
        "mod_editor/core/nfl2k5_crib_scene_texture_writer.py": "4f72f59fab6f116c164a2acafb110829a46eb18dc5abcc5cd2c05978a0f0cdbd",
        "mod_editor/core/nfl2k5_crib_standalone_texture_writer.py": "95cab3bb2d666fa4f4dfddfb25816c443b17a51bb97abbe90d9532a5f117bae6",
        "mod_editor/core/nfl2k5_deep_zone.py": "59fb0d2b1f5be90d90692d7f143d00d8091ceac2d9ba1ee9bd40c0f9f626cbf7",
        "mod_editor/core/nfl2k5_deep_zone_code.py": "421d08aa91966fb43667cdcc44813ff8cd2d898b8c47191bfa9050930e9667cc",
        "mod_editor/core/nfl2k5_defensive_try.py": "a0b4cfb8500a46151878bb12a6f2379108c01e1be07b4f83eb5317c3e7e0f87c",
        "mod_editor/core/nfl2k5_depth_chart_rows.py": "49c3170fc78fe1b2e3927290a748287a5728208e2c255d5abf81fdd5b89e45e3",
        "mod_editor/core/nfl2k5_depth_chart_storage.py": "acb37c1fbb13e327880574df1142d6cb1262e97b307bfd182a167647d0892a1e",
        "mod_editor/core/nfl2k5_depth_locks.py": "9ffccf562eb4a3d739f29d6d90939597685217a7a3acd37a1e8c6962f2ef658a",
        "mod_editor/core/nfl2k5_depth_roles.py": "92a11e038973a1c421fe7f3162064bb62a9fd8cefd6bfb4bd9cc5765d3f3a19d",
        "mod_editor/core/nfl2k5_equipment_import_intent.py": "eae62374a69c2f5c52e0f77f5851ebd3d62c89bb29981be4225eda5082036892",
        "mod_editor/core/nfl2k5_equipment_import.py": "d061bc77992dcc1b12d11f3051de25024ac48574fc41ff24f45cab46ae79097f",
        "mod_editor/core/nfl2k5_equipment_lz.py": "2804d1828097e90fc5038ea7dbed0b081a84073e5018145628079fee032e1796",
        "mod_editor/core/nfl2k5_digit_art.py": "149bfb44290b2a93494778dc0eab577ac347581beae858601cb41f3079975716",
        "mod_editor/core/nfl2k5_digit_texture.py": "38112506a194aae7b0e229cdb0d40d0fbbba52bf7ac5e3e81c7a67743352e79c",
        "mod_editor/core/nfl2k5_disc_identity.py": "000ec3164d1da4a9e0fb4a4bd48deb55e4241cff90d7ee4762dd1caa446eff3e",
        "mod_editor/core/nfl2k5_display_list_stability.py": "34649b364e65566cc798df8e0ad60410609f7178973358e95ee3691b2f6e6031",
        "mod_editor/core/nfl2k5_draft_ai.py": "b90f8e84cd6e30c03758158a917773cdb44f3089f5f0aa2413503f39fb4a9a16",
        "mod_editor/core/nfl2k5_dynamic_kickoff.py": "5ed5a2914bd857d734f285f68af3b2b4b41712939e9d8aa42cf88103b11f6b16",
        "mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py": "65965dcc61ca1ebe85b4532be99a6ae64e504bad13f0d438223c9e5193d6261e",
        "mod_editor/core/nfl2k5_edge_rename.py": "8d07169164719fff6121c36b07f90ac8af0d350ea39cb2dcaee83a3ab4e3fc0d",
        "mod_editor/core/nfl2k5_elbow_options.py": "cd6921f1d7b2942f81c1415fab45eb18f3c4487e3e0aac1fda3a9dbd82760a1f",
        "mod_editor/core/nfl2k5_espn25_more_moments.py": "a914bbff9494d1211fb43a59858d7bff96fc671fe645e8640bea5d5f3f45c41a",
        "mod_editor/core/nfl2k5_espn25_more_moments_code.py": "661c05f766df80e30c11f1975d0a3af797bf5a26ceadf0f0dc56a86e7b99fcdc",
        "mod_editor/core/nfl2k5_espn25_rosters.py": "9f00a0cd2cd7237fb3ce5ebe8fc9b278cb19f74c3fa9501d6edc8c7c4ad4f604",
        "mod_editor/core/nfl2k5_extended_visual_catalog.py": "6576fc522bec39f163b851471ab9105db5080a5085681f3f27e626c6e50011f3",
        "mod_editor/core/nfl2k5_extended_visual_io.py": "928a8367c3faf4f37adeb9fa11164529457d79a9bb03fb0f0ecaa0082863975b",
        "mod_editor/core/nfl2k5_formation_play_writer.py": "9ae1968d2e877bfa826d6537617fadc409d4761aa03a4e840ae38199e8a3ad0f",
        "mod_editor/core/nfl2k5_franchise_2026.py": "e72fe54827d646a2d15107abaf4069b3460a6194898ca93239ccde989f2131b9",
        "mod_editor/core/nfl2k5_franchise_2026_code.py": "3aaa62bc4282a7605823b30d20936d388916d2f5c51a4a4774f85c0af67efcfa",
        "mod_editor/core/nfl2k5_franchise_autosave.py": "39fefc51d2b95fb56730ff1359c3fa9b73e0a4aa9302f38a32905efea791e3d3",
        "mod_editor/core/nfl2k5_franchise_autosave_code.py": "bf06126a790642048aae92d57d3815d445560bc012ed02df5917648bcceec183",
        "mod_editor/core/nfl2k5_franchise_edit_player.py": "aff7a39db971c0929363fbafa0771571b766fe041cc7e22a569f17f955da9b39",
        "mod_editor/core/nfl2k5_franchise_practice.py": "a02412be59a08a5997c1c2936265377520abb4e3ecf7108e24d9546b7a8592f0",
        "mod_editor/core/nfl2k5_franchise_save.py": "5687f7444ed04ff006cc5ccbaf94cc51fe3deef6891c78b91869c550bc2a2029",
        "mod_editor/core/nfl2k5_gameplay_lever.py": "21fbc88ec891fed1798905f26932d812906c5ce62485bffc1e3b47c9aa9b31f3",
        "mod_editor/core/nfl2k5_guardian_cap.py": "10d04364c41bd7522f74109a3031df05a5cd9ef3ea80193daaf93a455943b5a8",
        "mod_editor/core/nfl2k5_guardian_overlay.py": "c84e20e32f60a0f955c6a5f6bc059ce4abeb5276b7e7e90ba845f8f658990461",
        "mod_editor/core/nfl2k5_guardian_overlay_code.py": "019075c8fa333bd5be8d240c86038a3ab89527af11921ddfd6935b06eab08cf6",
        "mod_editor/core/nfl2k5_guardian_resources.py": "ae273e73f488527655d6650b9651ce2c78420f5a19e9b3caa7024379ef96deb9",
        "mod_editor/core/nfl2k5_historic_rosters.py": "36b4c4810afa1b1c7622a07e2ebd162a42eac21a541fc093daceb689bea85e26",
        "mod_editor/core/nfl2k5_historic_styles.py": "27de168580d3299d71b62c0e5fbc8ff949323c2aeac27f7ac8f2b721a57665b4",
        "mod_editor/core/nfl2k5_historic_teams_quick_game.py": "83526a04e065c41f1bb6fab175e17799de3a512ce98521a5857773c6274792e7",
        "mod_editor/core/nfl2k5_historic_teams_quick_game_code.py": "29197741a8157e9562edab4892106f649c9d3e00bbfcbf9377a2ecd4a7433361",
        "mod_editor/core/nfl2k5_hires_budget.py": "e36cffa4aa56b51a9549126a0fa7c04998a2771f9b5d2f78fdd158a41ed51ba6",
        "mod_editor/core/nfl2k5_hires_catalog.py": "4d1c67add6cfed68018d4341e6171b005a1568b60eebf199507afc39eba3ae1f",
        "mod_editor/core/nfl2k5_hires_evidence.py": "4309e402356c9266efb2ab498b99056412dd5613e61615db2b3ecadb11e943da",
        "mod_editor/core/nfl2k5_hires_layouts.py": "e9c5fde8390e6f0a5a35f91fcd7b2e39196a13cf0389be5a6cc6d035367710ce",
        "mod_editor/core/nfl2k5_hires_pack.py": "1f9aaa68e5d40ac5c5097e495771faa2d49536b030ae7f25b1911ac93f59b0fe",
        "mod_editor/core/nfl2k5_hires_texture.py": "cab5e3e72cfbf8eb3d4601ecd55782f6a0e78cfa2bb17440c61622348fb446c2",
        "mod_editor/core/nfl2k5_hud_layout.py": "9953e899093daf2517adc74d101a4160353377e36e273eba5fdec7f82bbb8da3",
        "mod_editor/core/nfl2k5_import_preflight.py": "7f7cbcac329171f70e4931d818af806edcf851c46ac04d5e8ebef95ed7db6454",
        "mod_editor/core/nfl2k5_k128.py": "90492ab22afe76e3f0f64875e99081d22fc42f21942e362342ac51a5ee297859",
        "mod_editor/core/nfl2k5_kick_laces.py": "a495864f35b60f335855b17f8a12ec304f78ecf3c363a597bb0e519e64790754",
        "mod_editor/core/nfl2k5_kick_rules.py": "885525ea94351521fc5e22c1c40c17ef3f374d665862e5920c4d9a644cd53be2",
        "mod_editor/core/nfl2k5_kickoff_blocking.py": "310ef53a004045f4daaedf8502100f60b050f0ae76a005eac0807b20e0090707",
        "mod_editor/core/nfl2k5_kickoff_returns.py": "d1f30bac8fd709f64be20e060027649a43fc04b82c7bd09b48082e8e66e5220f",
        "mod_editor/core/nfl2k5_lineman_rating.py": "e1c08c86e0a31c58fd86d5a155c56ad200cf5ef237771c95b39bfe29215261c1",
        "mod_editor/core/nfl2k5_match_coverage.py": "d9c1a93508a25a17d389b1dfa628ab8d0ac2da25d99bcc64a347b98f4447cfa2",
        "mod_editor/core/nfl2k5_model_project.py": "04371be3e1e86a9a6b3d2499dc0db203d6d5d9241c104c78879a2a414aa05488",
        "mod_editor/core/nfl2k5_model_skeleton.py": "feaff8bb682d51d6b62c23cb955ccaf5b9a149f9e2948d7ee4f219200cd7f0ee",
        "mod_editor/core/nfl2k5_models.py": "8b2e86bd0e6f2ba8d192bcdb452bc8e45fc38a4a0af8a95350a0e2f816bc6176",
        "mod_editor/core/nfl2k5_modern_helmets.py": "4b292d9cc399dbaafb084fdeb87df747c37bffba1a0a49c034416936a46f7e6c",
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
        "mod_editor/core/nfl2k5_music_playlist.py": "29c9b2fdc7449e482504d824bb9dd8c562389bef2c198361ef29583befaaf243",
        "mod_editor/core/nfl2k5_music_playlist_code.py": "565d8ad8b8e6435190dda20a137e7b8128c5716d72935ab30be5189efab48546",
        "mod_editor/core/nfl2k5_music_policy.py": "f1f21c182fa9f86844c6dcc0019f0463ef841799fd24a717131b4d762c8a99ec",
        "mod_editor/core/nfl2k5_music_storage.py": "db13a224f6e04e2ebbe0f7639946e2e6c9626500939614a44f2539a25137904b",
        "mod_editor/core/nfl2k5_my_career.py": "b30477d18aa7aba3c669d4a06e4215f3a5924af8367d2327e411307f18611196",
        "mod_editor/core/nfl2k5_my_career_advisory.py": "14aa17b6d3dc4aba6303de17eaa999c7599856110ee89ae14ccd522f0eaf00ba",
        "mod_editor/core/nfl2k5_my_career_code.py": "0ce8c85ca30bbc188356e612ca1d95e01e94ceb7dfe2cabcea222672f07e3c2b",
        "mod_editor/core/nfl2k5_my_career_events.py": "228a0b59d43b9b9c52e10ac93cc72072e772e694cc864c8e2e037c5d7c772460",
        "mod_editor/core/nfl2k5_my_career_mode.py": "96434e5fe8e686bfa72a475b30cd6aa213e4eb3c9bdfef477f645c29017528a9",
        "mod_editor/core/nfl2k5_my_career_mode_code.py": "bf8ae27ef695ee73997a5129fbb324c87a6af47a7bc7e08411cb85e9162fb319",
        "mod_editor/core/nfl2k5_my_career_progression.py": "77ee4d665dccc60862e162195e85d3cb3d39e6ad04ce9eee9cc87a99754d9cf5",
        "mod_editor/core/nfl2k5_my_career_save.py": "c9c833f499212722b260eaa465d8e0445c53281fc832a03c21814bd1b94886ea",
        "mod_editor/core/nfl2k5_overtime.py": "3ff6cb4883cf9c6846029564a777c3cf26b891b10afc3a1a06c8baee72c02e4b",
        "mod_editor/core/nfl2k5_p8_texture_writer.py": "4a519adf657eeb5ecbf8be6a8cba99411cbd0e5843bf55d7bd7e142723498485",
        "mod_editor/core/nfl2k5_penalties.py": "f74e61d6404d30b54811442b1bbb58fa6d233d55f57856043a6cc6e8730c1ed8",
        "mod_editor/core/nfl2k5_play_codec.py": "3f01db64ac7230102fb8c37c3baa2ad60932803a576a8f7404dc3c0d347b268e",
        "mod_editor/core/nfl2k5_presentation_standalone.py": "c420f31fca02c60c0176eb36f571794d91e9de0ce57ac2cc009a9aa756701ca6",
        "mod_editor/core/nfl2k5_play_intents.py": "4d4f08fdeece4f45e8b23aaa5cccda971463b8cc8cfd10e52e8fcaa03508f64d",
        "mod_editor/core/nfl2k5_play_library.py": "259191d8cf7f8e145dbb3498b5142eead050a5383b095e1d7d53c80283488abc",
        "mod_editor/core/nfl2k5_complete_offense.py": "80bb63e19545be710e23cc56e60c846813c12737091d3913e457ba0a2f2f431f",
        "mod_editor/core/nfl2k5_play_scoring.py": "5cf6b50416682cf54527befb2954c26e367df316e0bd8536955517e451d1d107",
        "mod_editor/core/nfl2k5_screen_authored_pins.py": "5a4dd7d846224e39c932281ea53d052172e46675d977d8f1e628c0adaf90a39d",
        "mod_editor/core/nfl2k5_playbook_inspector.py": "2a690d189ad0e97d0c908daa2d6bc83d716a20b593666230a3dc88b91fae0ab8",
        "mod_editor/core/nfl2k5_playbook_pack.py": "d5acf4c197daed9452d7d4bb3a0ae3f992b68ecd9baa3016914ecc97b1d56bab",
        "mod_editor/core/nfl2k5_playbook_pair.py": "9d9a72b7cd5c1b8dea7b59d97520717595b9699a24e1f85f6c8884bc445579d0",
        "mod_editor/core/nfl2k5_playbook_pair_code.py": "78e97a0ce01e49af9a22c59d540ea8121097ae26c31f6650983baa7a945969ae",
        "mod_editor/core/nfl2k5_playbook_route_writer.py": "87ac9ab729e15c665774223c406a248931b77a05ca2fa258b04e1f0cd06674c5",
        "mod_editor/core/nfl2k5_player_star.py": "6907c77e277b88dbbfc068370a62bdcf3be96ec0f4c776b57ac72c9e34778d03",
        "mod_editor/core/nfl2k5_player_tags.py": "19f01e1be1a41ebefadbd1801aba0d83da8954d7a9f19d5fa8d43984c64df45b",
        "mod_editor/core/nfl2k5_playoff_picture.py": "cc851bca3cd4ac77fdcea03be41db1536c51e3699503cfb227f60f1619b2c441",
        "mod_editor/core/nfl2k5_playoffs14.py": "d8c490d6d37d118355db80de95c924db52f03ba897b4fbd85432d1840a14051d",
        "mod_editor/core/nfl2k5_lineup_iterator.py": "b8b0c21ca736d411fb1288a6f4cddd5c84929b1c57962c455756e51f1eae7c0c",
        "mod_editor/core/nfl2k5_disc_extents.py": "2a1c1fe06a67139bcac469fd2cbc3cced1f523bac96b226094a296793bce3625",
        "mod_editor/core/nfl2k5_position_pools.py": "548f24698c4e4ae50b090b9bdec7366661e1833dd7a55f29e03260f6b78ff2aa",
        "mod_editor/core/nfl2k5_position_row.py": "0df78f0d7e3af61be8738afe5373925f48ef8a309a35bfcb31ab62008b6be85b",
        "mod_editor/core/nfl2k5_practice_reserves.py": "3728a1d8195819c72f814ac5110755a06598aeb1400f6a53702821a7b275a8b6",
        "mod_editor/core/nfl2k5_practice_squad.py": "c98cf2edff83719ae8948346eec8875f81c234b4f0142a690c30dbfae377d7a4",
        "mod_editor/core/nfl2k5_practice_squad_runtime.py": "bcb9823807ce4ccc20c709e79099c37ef61b678eb319f25981e15ba3e8d9d682",
        "mod_editor/core/nfl2k5_practice_squad_screen.py": "e9207a6e53488711319ca06b5a2b3df68b459ad37f461657da0d1c520b1c7e23",
        "mod_editor/core/nfl2k5_practice_squad_screen_code.py": "d649e11edae0627de6e17aed0c4c60abea6104fb49fc904135276abef1e23b0e",
        "mod_editor/core/nfl2k5_preseason.py": "5e18c2bba83005798237cc3c85b0e10ee9f7dd8f4e179f52a430f46ed02c951b",
        "mod_editor/core/nfl2k5_probowl_order.py": "6e61b983f57f7e01695c7626b51854aea2242e1c7879049f8bb3a85a44b3cf9f",
        "mod_editor/core/nfl2k5_roster_fill_composition.py": "d68a4388ef964734602ef270aa53f2103cef3d1dd1437349167c324739fcba0b",
        "mod_editor/core/nfl2k5_franchise_economy.py": "3de240d43af25e13f0f92fd7ec6bb5b80a223b4653f36dbed2c5d82b6c18a2d1",
        "mod_editor/core/nfl2k5_franchise_economy_code.py": "0fbd627f1b7aa64b2dab6e72a1d01a8d44db32bf9b08d58c76bc44c717873a45",
        "mod_editor/core/nfl2k5_progression.py": "a4e978a251fb9a747819c09c3563540229a41afca92458990496915f772d6b94",
        "mod_editor/core/nfl2k5_prospect_names.py": "51112f0fd3794e748678f1e7f9537d0177f37f388945cf3bd8aed3e2c8c05f47",
        "mod_editor/core/nfl2k5_qb_spy_runtime.py": "d0c0f0f216c3f845a7fc233c608766b09e2d74a4e979b937480f788e8c00c2bc",
        "mod_editor/core/nfl2k5_qb_spy_runtime_code.py": "759ee92ee3bac1d79d80ac6d6ae539ea6f0e3cef658dc945548a8c7db35c468f",
        "mod_editor/core/nfl2k5_rdata_sites.py": "cb422ad49c38a233a8d0e855beae0a9748b1dfef809472bdae84c459865762af",
        "mod_editor/core/nfl2k5_read_option_runtime.py": "f4b3c0126f270dc6ed4aae33d75ab0d6ab25dbe389d803002045cede1f7363dd",
        "mod_editor/core/nfl2k5_read_option_runtime_code.py": "2f58745ddc7ad4cf28adf3223d3a85661ca79d0252a7bb7d27a7a19e90bcc69a",
        "mod_editor/core/nfl2k5_resource_growth.py": "d33b9b3a6571852e13297050efd5364ab411f10efbaee32b6b087f01e41725fa",
        "mod_editor/core/nfl2k5_returner_fix.py": "a59cd96b4d639ee4f2d7fa7460e1b8bd61559ca060e7cd5c1a8d65990a3c7dc2",
        "mod_editor/core/nfl2k5_roster_ages.py": "f38aff19e3bb9ab503d5a7b85d191ff8c15703e101a5580ea02d0d85c6290daa",
        "mod_editor/core/nfl2k5_roster_arena.py": "f4af5a0adee42963796c3ec2d61a5f113586da9694f04510a1227025c9b35ffc",
        "mod_editor/core/nfl2k5_roster_arena_code.py": "7317e0d071edead50066e03a2bd36fadc4cc81f9554f45afef555c2fd1d3365b",
        "mod_editor/core/nfl2k5_roster_arena_growth.py": "9ca3f5aed36a19c943123cfc2b93a976a0c37929700283d6551a30cadd2c5d7a",
        "mod_editor/core/nfl2k5_roster_arena_image.py": "3d3344b53d40c017d921c91fbf3d8579f12f5cbee6ec9e112bd68b7d18345b7d",
        "mod_editor/core/nfl2k5_spare_capacity.py": "1afd56aa33857731820ad0d3eab25967f4f4ee4552f3d21be8bc567c2a136134",
        "mod_editor/core/nfl2k5_free_agents.py": "bfc8652d3f69819f91a0bc813e256cdf9ea144a9d6210dce5d60e00e05067555",
        "mod_editor/core/nfl2k5_roster_appearance_transfer.py": "b8264599eaa0ccbfac1412d4f9d96af796b1d00eb4abb2dd68d6ba95f9480704",
        "mod_editor/core/nfl2k5_roster_records.py": "1374b3b9dbd893962d0984c4405159f6e0f39eaf240ba7477f2cb0a43fb402c2",
        "mod_editor/core/nfl2k5_roster_snapshot.py": "9b38f3a53cb2529f2226950a7f453b588c61daa9ac47acff4d9ad823abed7baa",
        "mod_editor/core/nfl2k5_roster_save_to_disc.py": "70fae49ace3c573adb8fdff3fb8b81073d6348e24055dac592ab5eb07caf69ac",
        "mod_editor/core/nfl2k5_franchise_history.py": "307bcb10d4351f284cdff3db988d3b5051d10905625cb358156fdba20f6c8508",
        "mod_editor/core/nfl2k5_career_stats.py": "6b12f7bcebef7f4b58cd7a72bc758b7fcd7709b46bfd17da443c6ff5aeca97a2",
        "mod_editor/core/nfl2k5_official_marks.py": "9f0e67322ba4b266693d0805d8cc80ed668b6b91ac90b301627a90b2cc2a90a2",
        "mod_editor/core/nfl2k5_college_refs.py": "2f49e35ed8904f376d7c4edc2d590d1bd48d593803f22ea7bc3399b2980fcfb7",
        "mod_editor/core/nfl2k5_resource_load_guard.py": "b679bb7dea16b1ea9bcc04b599760012d350acffb6ebd5a37ebfe857d726c9dc",
        "mod_editor/core/nfl2k5_roster_storage.py": "b2bed5fb92dedd9d1c4312a7e9344ca1558225d9ed12977e4fe69f4ca9d85bb6",
        "mod_editor/core/nfl2k5_safe_text_banks.py": "c7ea4288611615204f53c40f5da06728bd9e5511eec5ae06711145e509461d48",
        "mod_editor/core/nfl2k5_save_rost.py": "2440e0796000f08bff319e5967675fc0b4df09ad7534733562fbbb22d8fbdac2",
        "mod_editor/core/nfl2k5_save_writer.py": "5a883cd1e449e8c796dc9453e6e9245390715d081979c024ac1182ef2c483bc4",
        "mod_editor/core/nfl2k5_scorebar_v3.py": "4e3d58f8fdc71d6da202d1367826fec5e32350470dd88089ecfcb7d272ba67bf",
        "mod_editor/core/runtime_dependencies.py": "326c47fbd24a2cbd5e360b32fd8754434a8433d21bea7efda23bebbc0e9343ac",
        "mod_editor/core/nfl2k5_scorebug_assets.py": "9d7036c1a426faee7671337e976d6ef21ae8a7d4e01b03b9f1791651b75f6293",
        "mod_editor/core/nfl2k5_scorebug_exact.py": "3023cf9000891373aacf8782157ceb86d131ed63ebb81816501664df8ebd7c23",
        "mod_editor/core/nfl2k5_scorebug_fonts.py": "b292f93b7bc25b64a379069b77c9172c1b92cf79553bfe4a7be835d1ad7119e9",
        "mod_editor/core/nfl2k5_scorebug_ingame.py": "24c572ff8b109ed77a80e10193754683398b70d71a0529f4d3c24e5c44237d39",
        "mod_editor/core/nfl2k5_team_names_2026.py": "4a91c6293533a5124ed225687d93495a052dd3ea4ab05e64422081528416a909",
        "mod_editor/core/nfl2k5_scorebug_mnf_font.py": "4aab9c01ea57c255671d7c3dde9e473173cf1b28fdd0004a4e2c053330415709",
        "mod_editor/core/nfl2k5_scorebug_resources.py": "d050a1130e66274e40fcfdaf5e764efa446cc3c09c2f540c241c1b5cc86a127b",
        'mod_editor/core/nfl2k5_scorebug_sprite.py': 'b0c1924ac66570e1fbe7859e9f5fd483785b645f82019ba4a348e8b6ce77b588',
        'mod_editor/core/nfl2k5_scorebug_teams.py': '95f27e3a4320488b98bc5dc6236b70b881299ee91813a588e7ff62ddedd1c09f',
        'tools/scorebug_sprite/xemu_model.py': '1b97da7ecdf4e0fe19d6a1d7ea41ff3110810f14777da88f3ca94e18e1f110b3',
        'mod_editor/core/nfl2k5_scorebug_sprite_code.py': '621c64a9d8a9469140e8196faed22e0432f8a2bcd4c793f11f25ceb90e1f8f64',
        'tools/nfl2k5_scorebug_exact.py': '8be2b18d28575b451d39bb15dab192546ee82dd0fa2be42bc649aa966ddb38dc',
        'tools/nfl2k5_scorebug_projection.py': 'e55fde9d1101ac24822431169953b487621f94145ea49e737edb46d9eb203d18',
        'tools/nfl2k5_scorebug_template_proof.py': '6f21bd9fc54d472db03ad5e84d8344cfdb358c7e2e6c950134d80e5cf345bcc2',
        'tools/nfl_main_menu_font.py': '64ae881a6ccaede10d15dc3d68277d061c5ccb9f94ccdee5208095ca31316d60',
        'tools/nfl_normshort3_positions.py': '925147094fdf03d91ee0e0487b0dee3b632438c333fbb9f2b8ecb54a15cf19e3',
        "mod_editor/core/nfl2k5_scorebug_runtime.py": "c8f066632e84fe23b75870664819cbda5beeaf622cb48f066dfb72546eab9307",
        "mod_editor/core/nfl2k5_playcall_layout.py": "4020bc30aae2ebbe718791794a93fda358c91f24ad8274ed6dc56be1834afa98",
        "mod_editor/core/nfl2k5_scorebug_source_art.py": "a3617552d90389df8e7ce4d78faa8fd64a1995c91e4e8ef93219007761ac27fd",
        "mod_editor/core/nfl2k5_scorebug_template.py": "409f7324352b88a6b4387b1f1a8ee1231c56f9674d7762ece24a8142fd2d2060",
        "mod_editor/core/nfl2k5_scorebug_unified_adapter.py": "3307d3b1777fcb51f112dea2c6c5290dd969c3037d5bc21112f9740b7cef9bfd",
        "mod_editor/core/nfl2k5_scramble_tuning.py": "f9e85191b7d93849a92a749385bdd746609465238e776ea0e7f072ac29bf2e92",
        "mod_editor/core/nfl2k5_screen_hooks.py": "4e2d53a15e47e45ba76ec4a6c7d34d96bc100160aaab507c8c0a1f2b04eae27b",
        "mod_editor/core/nfl2k5_screen_hooks_code.py": "bcab9155aceb1e62e2cb1e5a7b98231ec7cf101ae3623a8e0b2397dd4ab27b33",
        "mod_editor/core/nfl2k5_screen_timing.py": "8c7245f79a2c79df3974545b30db4de45c6b1b8071ff5d7a4bc396b2a9903894",
        "mod_editor/core/nfl2k5_season_cap.py": "dda1e4d3a11bfe798d837ab8629bfa1d4e90fc233417e39de1974ac1c5b959c6",
        "mod_editor/core/nfl2k5_season_length.py": "669fca7096e00602758cd46fc58776be5289600b6cb0c9b75d6a2822dffde1d4",
        "mod_editor/core/nfl2k5_senior_bowl.py": "e415ac02f3170f74c23137ba4f487d4dc4b4f10c1db4565d753d0558b846647c",
        "mod_editor/core/nfl2k5_senior_bowl_code.py": "000abee8fc9bf5d382d4c8934a0509c32de7976805eadabb5c4aed3ccb0812da",
        "mod_editor/core/nfl2k5_seven_on_seven.py": "2c2874feedf4b1818ef7cd35bcce9229fd27848f831de732cb11a217ab575c84",
        "mod_editor/core/nfl2k5_seven_on_seven_book.py": "5c9e244426613eb5bd484e328f5ce3424832f4f6717313c39b9ef8e96963fbed",
        "mod_editor/core/nfl2k5_source_cache.py": "91ba6711fbe675a7a23d296a8989d6e985e6a262c89cb320ee5a06742876fac7",
        "mod_editor/core/nfl2k5_special_roles.py": "16861404565bfcb3c87de7ed80d616b1c2a6d1dcac0e1e5ad8d1a30259b1f59f",
        "mod_editor/core/nfl2k5_stadium_cache.py": "af3f8983f4312f755f27456684e6e27505d41eda07539ebcd813b90c81a88762",
        "mod_editor/core/nfl2k5_stadium_studio.py": "2b08e3e3c8b6e005b4772bfb1ff2ddd79604c8af36557af8e316ab0612fbe94f",
        "mod_editor/core/nfl2k5_stadium_texture_writer.py": "885811a5d03322f6d4027aaa22550e672afc6103ac84fad832f78ef752fce102",
        "mod_editor/core/nfl2k5_team_column.py": "465ae89093c76404e71653004c3bb1a0cd60ef9c1ebec4df7b639f4fe94e6337",
        "mod_editor/core/nfl2k5_team_history.py": "8e360ec57bada84bd505c399ee6fa5e7a05d50a316548f3bb8c6e45b7c9c4e5e",
        "mod_editor/core/nfl2k5_team_logo_swap.py": "d4e46ff301b3449fc78a145548be2bcbc6104caad80563e1d940ef564fd73c12",
        "mod_editor/core/nfl2k5_text_catalog.py": "514706a38b28a4c7189f49e7601813cd55e16f1b9e81c9c8aa3e92c072e962c9",
        "mod_editor/core/nfl2k5_throw_arc.py": "0fbf33d12fe27a0f940fb7e13f375390b88701c4ccb7e89a1de895d8f66b9c3c",
        "mod_editor/core/nfl2k5_throw_tuning.py": "a4dfc43c74dc226a42cc9bc3fbc5124237f9e5102fb4ef28a1f1272362f9ccab",
        "mod_editor/core/nfl2k5_unif_color_writer.py": "5e950cc404e25c1fbeff7ee5aa2a3fad235115aeddd743e95be6862677a88324",
        "mod_editor/core/nfl2k5_uniform_catalog.py": "342964f000624ce7dcbc552fce01810a93704dca6bc62559cc7a73b89f8c59a1",
        "mod_editor/core/nfl2k5_uniform_choice.py": "d618e2d8ebeae1443b0e9846e4f26d53cbc8d74314253798b860ddf8e9c312d9",
        "mod_editor/core/nfl2k5_uniform_equipment_writer.py": "3ea124f438c66e62851b482b711188f7a0c064460d30c86fa85559f1fa4f58da",
        "mod_editor/core/nfl2k5_universal_asset_index.py": "9df3c0a754abcb60fa4db3afd0f9b8af364f60551014d259e2713f5387491421",
        "mod_editor/core/nfl2k5_weekly_prep.py": "5b3b9847f24246b33be5d63d141908f7241ea3da7a62a8d9736c0964b0bff933",
        "mod_editor/core/nfl2k5_weekly_prep_code.py": "554fb7018dd0d2d5c59bd230cffd64d3be1cbc910df6410e40920cd3c08e97f8",
        "mod_editor/core/nfl2k5_weekly_prep_save.py": "aedb0576c3a19a3a6574362729f83d3dfac5bc4aae7eb203388403c721a83720",
        "mod_editor/core/nfl2k5_widescreen.py": "98e3fd35f5c45a35143e678055872fe405447a735b211cd2897119d3ed801b4c",
        "mod_editor/core/nfl2k5_widescreen_menus.py": "a72a4d2387e023c0552c9bfb6c5b3330a689bbe00ed5619853260a7c13012701",
        "mod_editor/core/nfl2k5_xbe_space.py": "0551886a5a285b64d9d7175e66bc35ad764bce7f0edaa7a1bb51b1bb2c6ae0bb",
        "mod_editor/core/nfl2k5_zone_drop.py": "96b915ac40cfbcb61b9bfa88a584a18841635e061947a7e1644ea193f83a94f0",
        "mod_editor/core/nfl_audio.py": "31193529647bd5fc35a2c25d38bccb83d20b16d46358169c26ced120c6c8e05c",
        "mod_editor/core/platform_compat.py": "cbd205e1fb1d9387f77b63d6f919604bd80f1820f630c45a81ce9e07d9677e67",
        "mod_editor/core/recipes.py": "10d518fc5bf0dab89cc9d1b0b055dda880ad0f24e2e7aee8dbe9d74fda2d97d8",
        "mod_editor/core/sources.py": "d47ef48a21d0cb4bb47e2b0f5ace029e68c3dc8906caa7d48e19e6dea4341375",
        "mod_editor/core/texture_master.py": "2597b4d177703f8c81e3c10eb9ded655390ccfa47f36bfab8d06fab1b0e79098",
        "mod_editor/studio/audio_annotations.py": "c45c94b011d703a24d063138f82477814495705c3b0055a9a867dbab453ba923",
        "mod_editor/studio/audio_bundle.py": "fafc659024246d1cff782ab07f6c744c97a563f64fedca8a288f3126fbeb4604",
        "mod_editor/studio/music_service.py": "2f2126c1055d75b71597bf60d2583861eceb790499e2636e51ccb1e3428393d5",
        "mod_editor/studio/project_archive.py": "07ee0383db64aac79cd2846903da63756b45b09c05118de4fd6fec612701c8bb",
        "mod_editor/studio/project_manifest.py": "9ba0fd3d5ce51c800959489ee1e5116a68ec123351cae66b7833da1a6f0aebd0",
        "mod_editor/studio/session.py": "2b16918c62d59be53d5382eb8bc552176e5e028d77d302516b7a14ce500f4c13",
        "tools/apf_inner.py": "4175688c9df2cb8d8253f5b4d08570a3a3486cb9856d000a4146e5a952982847",
        "tools/apf_outer.py": "e9ce600393f9c9f6b372bb385e9486a655167bf6cc9ef256cc96c8439957cd31",
        "tools/game_audio_convert.py": "3ba3f1f4c2aa452198a12e65d8e93e8d690988d0a6a88c80d7c5de91c1e5a983",
        "tools/nfl2k5_commentary_swap.py": "d12b0a4595155acf97545b01fa82791b43357e5a07a1569a58b1135e9faa965d",
        "tools/nfl2k5_jersey_png_workflow.py": "e7af6773a07085da33745e62bfccc59c2f013e833f2aa1ae9009c965938f5832",
        "tools/nfl2k5_kickoff_alignment.py": "31218fc1e553adf4ab0f7fa59857459da16b828a5bb3679aba3c27d419cfe82b",
        "tools/nfl2k5_playbook_position_recode.py": "326ea888c7e4c7281d231ea02b495ee8af6289770cf122ba6299f0518126adc9",
        "tools/nfl2k5_scorebug_espn_art.py": "4bd1e9fb9166ddfbe1423f3e2c41ed2424841a0ae476270c2117de2a9e006780",
        "tools/nfl2k5_scorebug_layout.py": "63ee159943a6494de331339e7460cb674955698c1d0d6a3aa8057e024967dcc5",
        "tools/nfl2k5_scorebug_position_patch.py": "eb2b913bd4d0620dcefc4f280db1f6d73e4a5c348b0483a246bbf587506cdbff",
        "tools/nfl2k5_scorebug_reference.py": "5186fbbbc75619518cdad41763d4fcb9d438bb2bf37ee98bc74b265c6446b435",
        "tools/nfl2k5_roster_reclassify.py": "569bd7021f7fa8259a6ffd9c4473e8c1d08e22d9e383593c288f747d2e2fd867",
        "tools/nfl2k5_visual_mod_project.py": "569d69aa2135d6c5c1c722edc40805d54dc17571ad835406252c7cc55ff4fac7",
        "tools/nfl_all_texture_xiso_workflow.py": "61d0574ae5320cb7b12b96f1be0b34dcf1fdef363091b00de0fd0fac7130bd91",
        "tools/nfl_audo_wav_xiso_workflow.py": "d684cbe7b30f77caf808bcef3d0219777b333336ae5bee4837d10f69cc1d13c6",
        "tools/nfl_create_team_field_art_inventory.py": "da59018f1417871516b75769ea53a351a1d2b03ed855f985c1f88ac333b42489",
        "tools/nfl_create_team_field_art_png_import.py": "f4dff7694bb11f758e78773ff7e23b96500499f198e10efffd7e680765780b08",
        "tools/nfl_crib_bar_monitor_png_xiso.py": "d0ff8f4ebfb20e443dd12892e531a6ac1736831c182c35a19edb94a8f4cc8c11",
        "tools/nfl_crib_team_photo_png_import.py": "00c05c92fe9ee194b2c1c96830efc09aa99f5023687f29b5a08c16f3dbdf9539",
        "tools/nfl_crib_team_photo_targets.py": "e0ec8925ae179ce0955e32c681f7bc866ccd8807d5489791d8f9210bb955b357",
        "tools/nfl_dxt1.py": "bce75aca68acbfaa5112927e228672d4d77c58fc27cd3ce047751d8875dcb9a2",
        "tools/nfl_jersey_tset_png_import.py": "4aa2dc64dc060b91f4a1d7c95ca2472726cd15afdcbeff27dd368b645149db25",
        "tools/nfl_jersey_tset_targets.py": "6835fbeef8f34aaa137b582a386d630860eccb1bf17cc626232d3ff36bda02e0",
        "tools/nfl_live_face_texture_png_import.py": "e0f7398cbdb87a79593b5a8a61ec12b2ed3b03bb1966d4fb14f581543c2c7864",
        "tools/nfl_live_face_texture_targets.py": "c9748ee6cbb0441fded6c961ef25ec913e3294218c7892eacb731456c315f8d4",
        "tools/nfl_live_helmet_txtr_png_import.py": "38555a95f7fe50abfbf9b47ab86945ffba2bfd92d78eae6b828532f865abaabe",
        "tools/nfl_live_helmet_txtr_targets.py": "26b18b9aa8f0afd71e0b137eef52f2cbfd0f2108cb63546979883446bc93325f",
        "tools/nfl_live_numbers_nameplate_png_import.py": "86a4796e44fcb286b8fd9450fc5242f4ddc22fb83a4fa32ffdab3ecbdd2d3449",
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
        "tools/nfl_tset_png_import.py": "a37b26b62b0b2a18b7db9de6d605ed0906642214f2a044e31da891f0995dda56",
        "tools/nfl_tset_png_import_dynamic_validate.py": "da20c1dff0145780c0d485970a527a0f172ab8a8653977784deae5e7c7ce6a03",
        "tools/nfl_tset_png_import_verify.py": "777ca0ed729e54c41f7b522c4b121f577a573f5b010a851ab36218fff472076b",
        "tools/nfl_tset_png_import_xiso_generic_patch.py": "a84699a55b7e34ff49a28913a7b892ce673fac4b78d427929683c2afc0c68cc2",
        "tools/nfl_txtr.py": "a75395d736266fd42e59995844d8001d0c333ca5d6f29f8228bbe14ff73974f4",
        "tools/nfl_uniform_color_xiso_direct_patch.py": "bbd4f5147d19afe3ad3ff0079c5bc0693108b58956bed74444c659718aef4ceb",
        "tools/nfl_uniform_inventory.py": "f2fc4ee3fad2c7eff0e2ca669c7f2642cea38a8c4d5cafb6d17a9c0b6e042740",
        "mod_editor/core/responsive_json.py": "7fb0241f333733941dab16032bbcd1310fa85a46f850a7d774273ff68dccb18c",
        "tools/nfl_vc_lz_fill.py": "12c466df4bf896d884a816a02bb9f23af1d8a95ae96b0a486e241d6a9f30d3b2",
        "tools/string_table_inventory.py": "8f69e9b8fe016509739cfbf10594d25e34288ca062b13463d18e9cc9611caefd",
        "tools/xbe_info.py": "c7843c317a7ec022bc22ee6266b96d856b57233af2d6baa71ec071a94212e0ef",
        "tools/xbox_ima_encoder.py": "2f6c7209674d93c542f4c67fdab2ebfa4aaa8a6a21d6b4a08d07a9996bf79d76"
    }
    data_pins: Mapping[str, str] = {
        "mod_editor/data/nfl2k5_free_agents_2026.v1.json": "c89b19a91e01677c250f0827034c19129251b04cdd30cf84c3524f1aac92c443",
        "data/nfl2k5_ratings_forty_sources.json": "39cc65634bfafab8b37817129be309e85f73f35ef7eb5f1f0b2472e5632d5817",
        "data/nfl2k5_espn25_more_teams/teams.json": "0484cc4ea617f4d250571ac3551f820368a15456c444326203d31c98eebd8cd3",
        "data/nfl2k5_espn25_more_teams/manifest.json": "e95e94e6e0a6b4cb23ceaefe565911ef313c0b817d55fc7da6ea4795403c05f9",
        "data/nfl2k5_espn25_more_moments_appearance.json": "2397399d6681a1c05f7e1287d3e4e83ff710e4fdc40b759621593a296643e3f3",
        "data/nfl2k5_espn25_more_moments.json": "3bc2a20c68cbc262b105b0bde11c6c8d1c39e6d21bed84cba9514af00c689870",
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
        "data/nfl2k5_espn25_fields/row02/endzone_S.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
        "data/nfl2k5_espn25_fields/row02/endzone_N.png": "cb09f5b9a788b61412dec608a36bb97ce997455fcd30b803ee218d92cc6d2c8d",
        "data/nfl2k5_espn25_fields/row02/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/row01/playoff_logo.png": "e1cabc0d8e1e6da0ae3da0f7505ad25fa945baae636baeb0bd3465bf7c5a60dc",
        "data/nfl2k5_espn25_fields/row01/endzone_S.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
        "data/nfl2k5_espn25_fields/row01/endzone_N.png": "bbc041dff4441c99eb2323161cca7eb2a5c4bb103036e7d0b382b71928790d2d",
        "data/nfl2k5_espn25_fields/row01/center_logo.png": "3c6c50f94ab35e9f96c772731fe6b7950048179bc81b8ab0396cc1edbde89163",
        "data/nfl2k5_espn25_fields/manifest.json": "f0702f9f6b9758a632a308e86310b1ad0b853d8a64752c77753a46233ad8b141",
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
        "data/nfl2k5_espn25_more_teams/steelers_2025.csv": "0a5abc4ca06f2765e0ff95f6e8dfae9d5f8d761d9831eac0923b82fef7cb3b0c",
        "data/nfl2k5_espn25_more_teams/bengals_2025.csv": "9cd4f343905739c468c980cf384bafd63e22cb8605418980f2ebc9954f4702ac",
        "data/nfl2k5_espn25_v04_profile.json": "3f1f60561c14a2a09fd23dae09d0fad6dbc5f2b49cf14cc171c4cb1a3ad5351d",
        "data/nfl2k5_espn25_unc_bowl.json": "2ad8c32bed29352ae2407350c1301646634914baa2e841cc4e9e1a96cba041e5",
        "data/nfl2k5_espn25_fields.json": "4d17dc285178ca60f5b0e8281790f0de601578f4aabcb79b53346c453db08834",
        "data/nfl2k5_moment_venues.json": "960f1f61f5395ce65117b32840f38f28dcb31fbbc1e793eda9dc39c7853b5fb0",
        "data/espn25_previews_2026.json": "8ae83e55f9ad9cc5a9fa1f5ed0efe4c0802522b7332c5ef3e3b594ca472e287c",
        "data/nfl2k5_era_rules.json": "fab269783f2f4524b01e031a15de8156629a6728d86249b9402822594778d1e4",
        "data/nfl2k5_stock_books.json": "87d779bb2be3c4b20b901c4afa0a620bb4b0aae29ef833bc4440a38c396417fd",
        "data/nfl2k5_modern_color_pins.json": "cf61e48211eba21152501bee6b20666f24663b0d18cfc0d2b2975dd8c45afacf",
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
        "tools/nfl_tset_png_import.py": "a37b26b62b0b2a18b7db9de6d605ed0906642214f2a044e31da891f0995dda56",
        "tools/nfl_txtr.py": "a75395d736266fd42e59995844d8001d0c333ca5d6f29f8228bbe14ff73974f4",
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
        "mod_editor/core/platform_compat.py": "cbd205e1fb1d9387f77b63d6f919604bd80f1820f630c45a81ce9e07d9677e67",
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
        "mod_editor/core/platform_compat.py": "cbd205e1fb1d9387f77b63d6f919604bd80f1820f630c45a81ce9e07d9677e67",
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
        "mod_editor/core/platform_compat.py": "cbd205e1fb1d9387f77b63d6f919604bd80f1820f630c45a81ce9e07d9677e67",
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
        "mod_editor/core/platform_compat.py": "cbd205e1fb1d9387f77b63d6f919604bd80f1820f630c45a81ce9e07d9677e67",
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

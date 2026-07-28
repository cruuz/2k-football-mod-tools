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


@contextmanager
def _pinned_execution_bundle(
    workspace: Path,
    pins: Mapping[str, str],
    entry_module: str,
    label: str,
) -> Iterator[Path]:
    """Yield an executable copy made only from freshly verified module bytes.

    Every local import in a provider's reviewed closure is copied into a private
    temporary tree.  The backend therefore executes the bytes that were hashed,
    even if an original workspace pathname changes after pinning.  Read-only
    evidence roots are linked into the mirror because the backends independently
    hash those inputs; no executable file is linked.
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
            destination.symlink_to(source.resolve(strict=True), target_is_directory=True)
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
    backend_module_sha256 = "cd365cf2c868f01578d262037231d98590d1bbe7c7f0ecb0be45581e240d8ee1"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/errors.py": "4624e80f063f1e7db69ec6c20d2703f01eec49728b02c88792ccb309bd742de0",
        "mod_editor/core/json_stream.py": "5933752561dd8b519a301c18ec1d14f13a457f58e6ae337984f543ab2b0838b0",
        "mod_editor/core/model.py": "292f0c5444e32f5cea000fd3cabd6963d7d805a5434dcbc364a36ca2c0f0d228",
        "mod_editor/core/nfl2k5_audio_catalog.py": "7b938b1fa47f9c86d05868015ba0cd2d764df08b8040ca0f8c7499b49fae4005",
        "mod_editor/core/nfl2k5_audio_containment_fingerprints.py": "da564ae30a18e9bfc7a3006b2422bceef0d0078d3cb9a919671ade23eda5f146",
        "mod_editor/core/nfl2k5_audio_origin_authorization.py": "664e43a7d2bb7dfcccf328b622b5fe7be3f5510d03919c56fa85149d7d3ffb8d",
        "mod_editor/core/nfl2k5_audio_source_containment.py": "2f1f9700922ac20042a6ffc4e4bd93202e1be05d26e99d4a5e019f41530238c6",
        "mod_editor/core/nfl2k5_audio_source_fingerprints.py": "81724f6e68b95457356d78286619ffe3c9f109e5f7dc6c78410f671e0bd92cd3",
        "mod_editor/core/nfl2k5_audio_source_scan.py": "b8bb4eef4d6a94a072b5e1e5c87fc0a113e8269118ba4e5857cb89c9560950e8",
        "mod_editor/core/nfl2k5_audo_fixed_slots.py": "bd92ac9d727b7516c8e99ee13a30e56153088d49259db606b86b8bbcb2db974f",
        "mod_editor/core/nfl2k5_ausb_build_adapter.py": "138eccfa097da8005dca74d43c0a10808558c4a4f1702c31e8f009cc49a7ecc7",
        "mod_editor/core/nfl2k5_ausb_fixed_slots.py": "49c4391884b2e3ed5a3928ab7b85316c2194213cae2892cae769ea807a2e1259",
        "mod_editor/core/nfl2k5_safe_text_banks.py": "c7ea4288611615204f53c40f5da06728bd9e5511eec5ae06711145e509461d48",
        "mod_editor/core/nfl2k5_scorebug_unified_adapter.py": "3307d3b1777fcb51f112dea2c6c5290dd969c3037d5bc21112f9740b7cef9bfd",
        "mod_editor/core/nfl2k5_source_cache.py": "662f1a9c0be6c73b647ba3850396f1016e10ef1c5227e01a4474d6d679c36731",
        "mod_editor/core/nfl2k5_unif_color_writer.py": "80cbea2665321b19bb1876730faf593856701ec44bf1f56d077518dc2d816552",
        "mod_editor/core/nfl2k5_p8_texture_writer.py": "94aa984f9dad9666b79b091071a81c194fa1cd4880a1af8d9ed0c68a26de9731",
        "mod_editor/core/nfl2k5_stadium_texture_writer.py": "c270d03fe92985baeb867182370207d2b4a224524fcaf3a6759438860d1601f9",
        "mod_editor/core/nfl_audio.py": "31193529647bd5fc35a2c25d38bccb83d20b16d46358169c26ced120c6c8e05c",
        "mod_editor/core/platform_compat.py": "5e205827d9fcec50ef9999cd508469481a718816947ecb42c346182325c5ed6b",
        "mod_editor/core/sources.py": "3d63ce6305fbd0a44e990045fbf9c7331c657971ff90af44090b2e05a90b6878",
        "tools/apf_inner.py": "4f6fb5ca21f48f96d498f976350f88c1f060569abc52d44a3742d2071e2f41cc",
        "tools/apf_outer.py": "7e86c0e5fb6338e14d7dab5d45f408655d456beeb9d10c6f28f5bc5c1bb088ac",
        "tools/nfl2k5_jersey_png_workflow.py": "e7af6773a07085da33745e62bfccc59c2f013e833f2aa1ae9009c965938f5832",
        backend_module: backend_module_sha256,
        "tools/nfl_all_texture_xiso_workflow.py": "a07a08b292e94a1a2a4e4925d5a6383a3fa2cf7806184948d88feaf06e700b53",
        "tools/nfl_audo_wav_xiso_workflow.py": "d684cbe7b30f77caf808bcef3d0219777b333336ae5bee4837d10f69cc1d13c6",
        "tools/nfl_create_team_field_art_inventory.py": "42358fb588bdc9b25f75640781bf16ed873913385e53e43c41f6bccf12d11bb3",
        "tools/nfl_create_team_field_art_png_import.py": "4f550de59e2827c0f3784ca1609ff499d01d94ee0b6b4b36c6c1fbb24a28482f",
        "tools/nfl_crib_bar_monitor_png_xiso.py": "d0ff8f4ebfb20e443dd12892e531a6ac1736831c182c35a19edb94a8f4cc8c11",
        "tools/nfl_crib_team_photo_png_import.py": "00c05c92fe9ee194b2c1c96830efc09aa99f5023687f29b5a08c16f3dbdf9539",
        "tools/nfl_crib_team_photo_targets.py": "5b4e72c65d5e169810033d4a9f7a0bc1c8ae318a400749e2652eaa02ed2f53a1",
        "tools/nfl_dxt1.py": "bce75aca68acbfaa5112927e228672d4d77c58fc27cd3ce047751d8875dcb9a2",
        "tools/nfl_jersey_tset_png_import.py": "a2c7c641ae37dbdd2459ecb2541961b27f48e3c5db96a83b590ef8e1e2a3f7bb",
        "tools/nfl_jersey_tset_targets.py": "73f55ae819ff4cfb0d5a7314a783a0247535be4d0055ed0563bfad65f4a5872a",
        "tools/nfl_live_face_texture_png_import.py": "fecbf035225dea5975b1078c80dcd00bbd00bec8d4b38321f33d7a240da459d7",
        "tools/nfl_live_face_texture_targets.py": "c9748ee6cbb0441fded6c961ef25ec913e3294218c7892eacb731456c315f8d4",
        "tools/nfl_live_helmet_txtr_png_import.py": "ddaf7c2621b8cb4db139bd5ab4698b2076b18f6d91eb029b52dde8fadaeb29f8",
        "tools/nfl_live_helmet_txtr_targets.py": "26b18b9aa8f0afd71e0b137eef52f2cbfd0f2108cb63546979883446bc93325f",
        "tools/nfl_live_numbers_nameplate_png_import.py": "9deb7255ba757d23875b0ff8037718b91e085934a98de1960c5bfbfebcaa9c2c",
        "tools/nfl_live_numbers_nameplate_targets.py": "4c66e8fb98f731bad2c5d1957ed3f682ed3f755ab6bb1811f6c51deaa85652dd",
        "tools/nfl_outer.py": "affbb92ea9fcce81b5d3502b2946fc0cf275b660c1ea93492730267110d49b46",
        "tools/nfl_roster.py": "8b5268787b072888d24be13952732b302ce41d648f7c59a1dd1a89a3aad56511",
        "tools/nfl_pants_tset_png_import.py": "7ceff6c3956c0e4993e20c710d5ff08d671c8474864c63a31d3e532c1bd54ed6",
        "tools/nfl_pants_tset_targets.py": "f53b13492b3ec9a197fdff5adfb1e06e56c40db8e85265aa25d0fc7879779f2b",
        "tools/nfl_player_portrait_png_import.py": "555c0d81e633033053b2427883be9bff8ebbe8b7844c81fdb0c329445485932e",
        "tools/nfl_player_portrait_targets.py": "0121d71588ad717ca68f4b2c67dbf32f8d0d36eb47b7b1e28bc4d39ce093c3ba",
        "tools/nfl_scene_probe.py": "31b17ded825d4379b517affece54fc5cd96abea49330017296a10a029216fc26",
        "tools/nfl_scne_inventory.py": "0f58222812df6b380588f8b0a2592101136a863cd0dd170b0f32df726de2fc6b",
        "tools/nfl_scorebug_png_import.py": "99bdfb9fbcab09790686e18972532c98f6d6096e92b8a6575dd271bd43a6285f",
        "tools/nfl_sleeve_tset_png_import.py": "7e8f6f43d74c1eee79e94f9a27c609d904747eac63691e7a5936dc56aed9d334",
        "tools/nfl_sleeve_tset_targets.py": "75ad68a32188fdefb883397b7406539c6a5ec50b1ab8f99ddf266f4c58d0bfe4",
        "tools/nfl_team_select_card_png_import.py": "7012a7d75a4203016b532e301f9727ebf5d58f9f88dc1271087c5461e493af1d",
        "tools/nfl_team_select_card_targets.py": "125361ee0aefbcbb46da8d466a1d850c91c3d9f33ea0eced3f2240f4563d5766",
        "tools/nfl_tset_fixed_span_verify.py": "d9a60349538962cb7c3ea8e3d2461b118fbbc10d05e9b68f0fe010f8cc1c2eb1",
        "tools/nfl_tset_png_import.py": "b92f6fb28155b3adfd86d8a687ce1d9f777634cc9547e860171f4bac406685cd",
        "tools/nfl_tset_png_import_dynamic_validate.py": "da20c1dff0145780c0d485970a527a0f172ab8a8653977784deae5e7c7ce6a03",
        "tools/nfl_tset_png_import_verify.py": "777ca0ed729e54c41f7b522c4b121f577a573f5b010a851ab36218fff472076b",
        "tools/nfl_tset_png_import_xiso_generic_patch.py": "a84699a55b7e34ff49a28913a7b892ce673fac4b78d427929683c2afc0c68cc2",
        "tools/nfl_txtr.py": "0896e3f409f38116602d37a8902f1403e8afe6ad9e17e9ee9d36244ae97a5107",
        "tools/nfl_uniform_color_xiso_direct_patch.py": "7b86c201d4dee4e6744297533fbb4e369be32970915982a40fc69f35e58d50b0",
        "tools/nfl_uniform_inventory.py": "c8593288ab737609d1f8ce4787af2a76a0e80d96a3d09cd686695c1e408b17c3",
        "tools/string_table_inventory.py": "88877c5c83d75382a7b349390b2babbe724da88927f53c916056eb88622d1ea4",
        "tools/xbe_info.py": "c7843c317a7ec022bc22ee6266b96d856b57233af2d6baa71ec071a94212e0ef",
    }
    data_pins: Mapping[str, str] = {
        "mod_editor/data/nfl2k5_crib_catalog.v1.json":
            "2f862fc6602bb23d433f0599c519839be9cd43ca6cd42bc22aeb7b94d56d305a",
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
        "crib_scene_texture",
        "scorebug_texture",
        "stadium_texture",
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
    ):
        self.runner = runner or SubprocessCommandRunner()
        self.workspace = workspace or Path(__file__).resolve().parents[2]
        self.source_hasher = source_hasher or self._hash_source

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
            or request.source.sha256 != self.source_sha256
        ):
            raise ProviderError("Typed build requires the recognized pinned NFL 2K5 retail XISO")
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
        if digest != self.source_sha256 or digest != request.source.sha256:
            raise ProviderError("Source XISO changed or does not match the pinned retail SHA-256")
        if size != request.source.size:
            raise ProviderError("Source XISO size changed after editor recognition")
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
        "tools/nfl_outer.py": "affbb92ea9fcce81b5d3502b2946fc0cf275b660c1ea93492730267110d49b46",
        "tools/nfl_scene_probe.py": "31b17ded825d4379b517affece54fc5cd96abea49330017296a10a029216fc26",
        "tools/nfl_scorebug_png_import.py": "99bdfb9fbcab09790686e18972532c98f6d6096e92b8a6575dd271bd43a6285f",
        "tools/nfl_tset_png_import.py": "b92f6fb28155b3adfd86d8a687ce1d9f777634cc9547e860171f4bac406685cd",
        "tools/nfl_txtr.py": "0896e3f409f38116602d37a8902f1403e8afe6ad9e17e9ee9d36244ae97a5107",
        "tools/nfl_uniform_color_xiso_direct_patch.py": "7b86c201d4dee4e6744297533fbb4e369be32970915982a40fc69f35e58d50b0",
        "tools/nfl_uniform_inventory.py": "c8593288ab737609d1f8ce4787af2a76a0e80d96a3d09cd686695c1e408b17c3",
        "tools/xbe_info.py": "c7843c317a7ec022bc22ee6266b96d856b57233af2d6baa71ec071a94212e0ef",
    }
    recipe_schema_file = "reports/assets/nfl2k5_scorebug_mod_project.schema.json"
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
    ):
        self.runner = runner or SubprocessCommandRunner()
        self.workspace = workspace or Path(__file__).resolve().parents[2]
        self.source_hasher = source_hasher or Nfl2k5UnifiedVisualProvider._hash_source

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
        if digest != self.source_sha256 or size != self.source_size:
            raise ProviderError("Scorebug source changed or does not match the pinned retail XISO")
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
            or request.source.sha256 != self.source_sha256
            or request.source.size != self.source_size
        ):
            raise ProviderError("Typed scorebug build requires the recognized pinned retail XISO")
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
    backend_module_sha256 = "0eace20481a94c439d789bee30ef457ede08bcf321b490a59cffe5eb58cd7435"
    verifier_module = "tools/apf_jersey_family_verify.py"
    verifier_module_sha256 = "588f8ba9a556092d3307535867b3760ca06b062847991f8bcfd95a49623cd249"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "5e205827d9fcec50ef9999cd508469481a718816947ecb42c346182325c5ed6b",
        "tools/apf_inner.py": "4f6fb5ca21f48f96d498f976350f88c1f060569abc52d44a3742d2071e2f41cc",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_outer.py": "7e86c0e5fb6338e14d7dab5d45f408655d456beeb9d10c6f28f5bc5c1bb088ac",
        "tools/apf_texture_patch.py": "d29532405a2e719fb78de13636bf0cbcb43348da68e7b14130b9502dad3488fa",
        "tools/apf_uniform_mip_patch.py": "26ee8964c84f8aa2676e00d9b05af99582fddc4c2e7b040304d44a0aa75c9881",
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
            relative = os.fspath(
                Path(argv[1]).resolve(strict=False).relative_to(
                    self.workspace.resolve(strict=True)
                )
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
    backend_module_sha256 = "f4fe8a9bdc1579fa4447963a07aa268d2a773785a4dce9c17fd2e703f49026ed"
    verifier_module = "tools/apf_pants_family_verify.py"
    verifier_module_sha256 = "8647749896c53f6333181391dbbec50fbd837e2f442c89257fff6b6a17dcac3e"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "5e205827d9fcec50ef9999cd508469481a718816947ecb42c346182325c5ed6b",
        "tools/apf_inner.py": "4f6fb5ca21f48f96d498f976350f88c1f060569abc52d44a3742d2071e2f41cc",
        "tools/apf_outer.py": "7e86c0e5fb6338e14d7dab5d45f408655d456beeb9d10c6f28f5bc5c1bb088ac",
        "tools/apf_pants_color_transport.py": "a3f33a0fc5b860f78a0686f3e559db4c3d22a05cdfb7793019599ef67cd05615",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_texture_patch.py": "d29532405a2e719fb78de13636bf0cbcb43348da68e7b14130b9502dad3488fa",
        "tools/apf_xenos_bc1_mip_layout.py": "56f53603e73e563ff66305430956373468160fb0af9380fe0257c5a5edde9234",
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
    backend_module_sha256 = "c43408e28acf8e953905115835cac38c66c7120de48c845e14e6490c47aca8c3"
    verifier_module = "tools/apf_helmet_family_verify.py"
    verifier_module_sha256 = "7240193adb4fc02e0971abb93e1390ddf93e7f54b114b95d7be86ed9bad50d48"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "5e205827d9fcec50ef9999cd508469481a718816947ecb42c346182325c5ed6b",
        "tools/apf_helmet_color_transport.py": "3c75f6744ca5d85a1222622c440a4d038a55412e16d1d1dab4e1e421a879cd7e",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_inner.py": "4f6fb5ca21f48f96d498f976350f88c1f060569abc52d44a3742d2071e2f41cc",
        "tools/apf_outer.py": "7e86c0e5fb6338e14d7dab5d45f408655d456beeb9d10c6f28f5bc5c1bb088ac",
        "tools/apf_texture_patch.py": "d29532405a2e719fb78de13636bf0cbcb43348da68e7b14130b9502dad3488fa",
        "tools/apf_xenos_dxn_mip_layout.py": "eed0f39a027c06ec4e4f46a55eab80dad07bd675801b78cdda079c29ff4839d5",
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
    backend_module_sha256 = "ac5d8571a87293d28b8889550f1a37879eeb0bc5c37bdb341719725cbda42515"
    verifier_module = "tools/apf_shoulder_family_verify.py"
    verifier_module_sha256 = "e84f0f4714cf55bb52be040ab17faeda9854dea80e91ca55052064ce637183bf"
    module_pins: Mapping[str, str] = {
        "mod_editor/core/platform_compat.py": "5e205827d9fcec50ef9999cd508469481a718816947ecb42c346182325c5ed6b",
        "tools/apf_inner.py": "4f6fb5ca21f48f96d498f976350f88c1f060569abc52d44a3742d2071e2f41cc",
        "tools/apf_outer.py": "7e86c0e5fb6338e14d7dab5d45f408655d456beeb9d10c6f28f5bc5c1bb088ac",
        "tools/apf_shoulder_color_transport.py": "aa77e667a91bc1b5c33f1d744cab6f5e89b872b2a693d417aeb6a981eda1e96c",
        backend_module: backend_module_sha256,
        verifier_module: verifier_module_sha256,
        "tools/apf_texture_patch.py": "d29532405a2e719fb78de13636bf0cbcb43348da68e7b14130b9502dad3488fa",
        "tools/apf_uniform_mip_patch.py": "26ee8964c84f8aa2676e00d9b05af99582fddc4c2e7b040304d44a0aa75c9881",
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

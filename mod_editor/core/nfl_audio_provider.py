"""Typed provider for NFL 2K5's fixed ``menu-back_01`` WAV writer."""

from __future__ import annotations

import ast
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from typing import Callable, Iterator
import zipfile

from . import platform_compat
from .capabilities import Capability, Classification
from .errors import OutputRefusedError
from .platform_compat import (
    SealIntegrityError,
    pread,
    seal_readonly,
    supports_sealed_memfd,
)
from .model import GameId
from .nfl_audio import (
    NFL_MENU_BACK_AUDIO_FRAME_COUNT,
    NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA,
    NFL_MENU_BACK_AUDIO_SAMPLE_RATE,
    NFL_MENU_BACK_AUDIO_TARGET,
    NflMenuBackAudioRecipe,
    load_nfl_menu_back_audio_recipe,
)
from .providers import (
    CommandRunner,
    Nfl2k5UnifiedVisualProvider,
    ProviderCommandResult,
    ProviderError,
    ProviderEvent,
    ProviderEventCallback,
    ProviderRequest,
    ProviderStage,
    SourceHasher,
    SubprocessCommandRunner,
)


def _is_reparse_point(info: os.stat_result) -> bool:
    """Whether an ``lstat`` result denotes a Windows reparse point (junction).

    A directory *junction* -- and every other reparse point except a symlink --
    is NOT reported by ``lstat``/``S_ISLNK`` as a link, so a junction planted as
    a validated directory (the provider workspace, an allowlisted parent, or the
    private sealed-closure staging directory) slips past a symlink-only guard.
    On Windows ``os.lstat`` sets ``st_reparse_tag`` to a non-zero tag for any
    reparse point; on POSIX the attribute is absent, so this is ``False`` and the
    symlink-only behaviour is byte-for-byte unchanged.  Mirrors the
    ``FILE_ATTRIBUTE_REPARSE_POINT`` refusal the Windows ``DirHandle`` applies in
    ``platform_compat`` (the intended shared home for this predicate).
    """

    return getattr(info, "st_reparse_tag", 0) != 0


# Names for the exec-pin mechanism this provider ends up with.  The two below are
# the paths platform_compat has no say in: the Linux ``memfd`` staging (kernel
# write-seals plus a ``/proc/self/fd`` name for a descriptor this process holds)
# and the untouched non-memfd POSIX fallback for a kernel with no ``memfd`` at all.
# Every other case reports the mechanism string platform_compat itself returned
# (``SEALED_EXEC_WINDOWS_SHARE_PIN`` / ``SEALED_EXEC_REVERIFIED_PATH`` / ...), so
# the name in an event or a test assertion is always the one actually enforced.
_EXEC_PIN_LINUX_MEMFD = "linux-memfd-write-seals-procfs-fd"
_EXEC_PIN_REHASHED_PATH = "rehashed-path-residual-window"


@dataclass(frozen=True)
class _PinnedExec:
    """A staged closure pinned for exactly as long as its pin is held open.

    ``path`` is the value to place on the child's ``argv``; it is valid only
    inside the ``pin_for_exec`` context that produced it.  ``inode_pinned`` is the
    load-bearing honesty field -- ``True`` means the bytes re-verified at pin time
    are provably the bytes the child gets (a descriptor this process holds, named
    through ``/proc``, which no directory entry can redirect), ``False`` means
    the re-hash ran
    immediately before the launch but the child still opens a *name* another
    same-user process could swap in between.  ``mechanism`` names which case is in
    force so an event, a caller or a test can assert the real guarantee instead of
    assuming the strongest one.
    """

    path: Path
    inode_pinned: bool
    mechanism: str


@dataclass(frozen=True)
class _StagedModule:
    """A staged closure ready to hand to the writer/verifier subprocess.

    ``path`` is where the closure is staged.  ``pin_for_exec`` is the pre-exec
    gate: the caller MUST enter it before building ``argv``, put the
    :class:`_PinnedExec` it yields on the child's ``argv``, and stay inside it
    until :meth:`CommandRunner.run` has created the subprocess, because the pin is
    released on exit.  What that pin enforces differs by platform, and it says
    which:

    * Linux memfd path -- ``sealed=True`` -- the bytes are kernel-write-sealed
      (immutable even to this process) and the child receives them through
      ``/proc/self/fd``, an fd this process holds that no name lookup can swap.
      The pin is the memfd itself, already held for the whole staging context, so
      entering the context does nothing new: ``inode_pinned=True``.

    * Windows -- :func:`platform_compat.reverify_sealed_before_exec` re-opens the
      staged file, re-hashes it against the seal-time digest, fails closed on any
      change, and *keeps* a ``CreateFileW`` handle whose share mode withholds
      ``FILE_SHARE_WRITE`` and ``FILE_SHARE_DELETE``.  While that handle lives
      nothing can rewrite, truncate or delete those BYTES.  It does not lock the
      NAME: ``SetFileInformationByHandle(FileRenameInfoEx)`` with
      ``POSIX_SEMANTICS | REPLACE_IF_EXISTS`` rebinds a name whose file has open
      handles -- the handles keep the old file, later opens get the replacement
      -- and the child opens by name.  So the window is narrowed, not closed,
      and Windows reports ``inode_pinned=False`` with the same WARNING macOS
      emits.  An earlier revision of this docstring claimed the window was
      closed here; an independent audit showed it was not.

    * macOS -- the same helper re-hashes and holds a descriptor, but macOS has
      neither a cross-process fd path nor a mandatory share lock, so the child
      re-opens by *name* and a same-user rename/unlink swap between the re-hash
      and that open remains possible.  The window is narrowed to the launch
      itself, not closed, and that is reported rather than hidden:
      ``inode_pinned=False``, mechanism ``SEALED_EXEC_REVERIFIED_PATH``.

    ``reverify_before_exec`` is the older, weaker check kept for callers (and
    tests) that only want the re-hash: on the non-memfd path it re-opens the exact
    staged file, proves it is still the same inode (no symlink/junction/rename
    swap), re-hashes it against the seal-time digest and fails closed on any
    change -- but it then *closes* its descriptor, so on its own it proves only
    that the bytes were intact at that instant and leaves the check-to-use window
    open.  It is a no-op on the kernel-sealed memfd path.  ``pin_for_exec``, not
    this, is what the build and verify stages run.
    """

    path: Path
    reverify_before_exec: Callable[[], None]
    pin_for_exec: Callable[
        [ProviderStage, ProviderEventCallback], AbstractContextManager[_PinnedExec]
    ]


class Nfl2k5MenuBackAudioProvider:
    """Fixed recipe -> copied XISO -> independent full-image verifier."""

    provider_id = "nfl2k5-menu-back-audio-v1"
    capability_ids = frozenset({"nfl2k5.audio.menu_back_wav"})
    backend_module = "tools/nfl_audo_wav_xiso_workflow.py"
    backend_command = (
        "python3 tools/nfl_audo_wav_xiso_workflow.py --source-xiso "
        "<retail.xiso.iso> --input-wav <menu-back.wav> --output-xiso "
        "<new.xiso.iso> --manifest <manifest.json>"
    )
    backend_module_sha256 = "71046985927dea1fb70863056fb4f2705e24328bcb6d631916709a42a2fb6c04"
    verifier_module = "tools/nfl_audo_wav_xiso_verify.py"
    verifier_module_sha256 = "2b6d159334a00fa18fc0276eb1f400bd49069a68e6e478be2c7a9b50e1371d00"
    writer_dependency_module = "tools/nfl_uniform_color_xiso_direct_patch.py"
    writer_dependency_module_sha256 = (
        "a9a3b987767d477a588957fddc37991cab5e2c1c53ebd5736ee1f303a6965924"
    )
    verifier_dependency_module = "tools/nfl_team_identity_xiso_verify.py"
    verifier_dependency_module_sha256 = (
        "dcbe2001f3f2f292bad88ae85657f28a5564496f37b561b33548eecf1e9d8f8a"
    )
    recipe_schema_file = "mod_editor/nfl_menu_back_audio_recipe.schema.json"
    recipe_schema_file_sha256 = "3548ea8b9614c2d6de1251000661fd512f7605675ef02ad34bb1a35e36c850d9"
    source_sha256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
    source_size = 6_300_499_968
    backend_schema = "nfl2k5_audo_wav_xiso_workflow/v1"
    _sha256_re = re.compile(r"^[0-9a-f]{64}$")
    _max_pinned_module_bytes = 4 * 1024 * 1024
    _execution_cwd = Path("/")
    _python_flags = ("-I", "-B", "-S")
    _dynamic_import_modules = frozenset({"importlib", "pkgutil", "runpy", "zipimport"})
    _dynamic_import_calls = frozenset({
        "__import__",
        "compile",
        "eval",
        "exec",
        "exec_module",
        "import_module",
        "module_from_spec",
        "run_module",
        "run_path",
        "spec_from_file_location",
    })

    def __init__(
        self,
        runner: CommandRunner | None = None,
        source_hasher: SourceHasher | None = None,
        workspace: Path | None = None,
    ):
        self.runner = runner or SubprocessCommandRunner()
        self.workspace = workspace or Path(__file__).resolve().parents[2]
        self.source_hasher = source_hasher or Nfl2k5UnifiedVisualProvider._hash_source

    def _writer_members(
        self,
    ) -> tuple[tuple[str, str, str, str, frozenset[str]], ...]:
        return (
            (
                self.backend_module,
                self.backend_module_sha256,
                "NFL audio writer",
                "__main__.py",
                frozenset({"nfl_uniform_color_xiso_direct_patch"}),
            ),
            (
                self.writer_dependency_module,
                self.writer_dependency_module_sha256,
                "NFL audio writer dependency",
                "nfl_uniform_color_xiso_direct_patch.py",
                frozenset(),
            ),
        )

    def _verifier_members(
        self,
    ) -> tuple[tuple[str, str, str, str, frozenset[str]], ...]:
        return (
            (
                self.verifier_module,
                self.verifier_module_sha256,
                "NFL audio verifier",
                "__main__.py",
                frozenset({"nfl_team_identity_xiso_verify"}),
            ),
            (
                self.verifier_dependency_module,
                self.verifier_dependency_module_sha256,
                "NFL audio verifier dependency",
                "nfl_team_identity_xiso_verify.py",
                frozenset(),
            ),
        )

    def preflight(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> None:
        emit(ProviderEvent(ProviderStage.PREFLIGHT, "INFO", "Checking fixed NFL audio contract"))
        self._validate_capability(request, capability)
        recipe = load_nfl_menu_back_audio_recipe(request.backend_project)
        source = self._source_xiso(request)
        self._validate_outputs(request, source, recipe)
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
                        f"Read-only NFL XISO recheck {bucket * 10}%",
                    )
                )

        digest, size = self.source_hasher(source, progress)
        if digest != self.source_sha256 or digest != request.source.sha256:
            raise ProviderError("NFL XISO changed or does not match the pinned retail SHA-256")
        if size != self.source_size or size != request.source.size:
            raise ProviderError("NFL XISO size changed after editor recognition")
        emit(
            ProviderEvent(
                ProviderStage.PREFLIGHT,
                "INFO",
                f"Fixed {NFL_MENU_BACK_AUDIO_TARGET} WAV passed recipe and source preflight",
            )
        )

    def validate(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        emit(ProviderEvent(ProviderStage.VALIDATE, "INFO", "Validating pinned NFL audio recipe"))
        recipe = load_nfl_menu_back_audio_recipe(request.backend_project)
        report = {
            "frame_count": NFL_MENU_BACK_AUDIO_FRAME_COUNT,
            "recipe_valid": True,
            "sample_rate": NFL_MENU_BACK_AUDIO_SAMPLE_RATE,
            "schema": NFL_MENU_BACK_AUDIO_RECIPE_SCHEMA,
            "target": NFL_MENU_BACK_AUDIO_TARGET,
            "wav_sha256": recipe.wav_sha256,
            "wav_size": recipe.wav_size,
        }
        stdout = json.dumps(report, sort_keys=True) + "\n"
        return ProviderCommandResult(
            ("internal:nfl2k5-menu-back-audio-recipe",), 0, stdout, ""
        )

    def build(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        recipe = load_nfl_menu_back_audio_recipe(request.backend_project)
        source = self._source_xiso(request)
        with self._sealed_zipapp(self._writer_members(), "writer") as module:
            # Re-verify the sealed snapshot against its digest AND hold the pin
            # across the launch: the context stays open until runner.run has
            # created the child, so where the platform can pin an inode the bytes
            # verified here are the bytes executed.  Where it cannot, the pin
            # reports that instead of claiming it (no-op on the kernel-sealed
            # Linux memfd path, which is already executing from a held fd).
            with module.pin_for_exec(ProviderStage.BUILD, emit) as pinned:
                argv = (
                    sys.executable,
                    *self._python_flags,
                    os.fspath(pinned.path),
                    "--source-xiso",
                    os.fspath(source),
                    "--input-wav",
                    os.fspath(recipe.wav_path),
                    "--output-xiso",
                    os.fspath(self._absolute(request.output_xiso)),
                    "--manifest",
                    os.fspath(self._absolute(request.manifest)),
                )
                result = self._run(argv, ProviderStage.BUILD, emit)
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError("NFL audio writer did not return its JSON success report") from exc
        if (
            not isinstance(report, dict)
            or set(report) != {"changed_bytes", "output", "runtime", "schema", "sha256"}
            or report.get("schema") != self.backend_schema
            or Path(str(report.get("output"))).resolve() != request.output_xiso.resolve()
            or type(report.get("changed_bytes")) is not int
            or not 0 < report["changed_bytes"] <= 3_204
            or type(report.get("sha256")) is not str
            or self._sha256_re.fullmatch(report["sha256"]) is None
            or report.get("runtime") is not False
        ):
            raise ProviderError("NFL audio writer success report did not prove the fixed contract")
        return result

    def verify(
        self, request: ProviderRequest, capability: Capability, emit: ProviderEventCallback
    ) -> ProviderCommandResult:
        recipe = load_nfl_menu_back_audio_recipe(request.backend_project)
        source = self._source_xiso(request)
        with self._sealed_zipapp(self._verifier_members(), "verifier") as module:
            # Same pre-exec pin as the writer: the independent verifier is exactly
            # the module an attacker would want to substitute after it was checked,
            # so its pin is held open until the child has been created too.
            with module.pin_for_exec(ProviderStage.VERIFY, emit) as pinned:
                argv = (
                    sys.executable,
                    *self._python_flags,
                    os.fspath(pinned.path),
                    "--source-xiso",
                    os.fspath(source),
                    "--output-xiso",
                    os.fspath(self._absolute(request.output_xiso)),
                    "--input-wav",
                    os.fspath(recipe.wav_path),
                    "--manifest",
                    os.fspath(self._absolute(request.manifest)),
                    "--artifact-dir",
                    os.fspath(self._absolute(request.artifact_dir)),
                )
                result = self._run(argv, ProviderStage.VERIFY, emit)
        if "NFL2K5_AUDO_WAV_XISO_VERIFY_PASS" not in result.stdout:
            raise ProviderError("Independent NFL audio verifier omitted its success marker")
        return result

    def _run(
        self,
        argv: tuple[str, ...],
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        emit(ProviderEvent(stage, "INFO", f"Starting fixed NFL audio {stage.value.lower()}"))
        result = self.runner.run(argv, self._execution_cwd, stage, emit)
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip().splitlines()
            tail = " | ".join(details[-5:]) if details else "no diagnostic output"
            raise ProviderError(
                f"Fixed NFL audio {stage.value.lower()} failed with exit "
                f"{result.returncode}: {tail}"
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
            or fields
            != [{"allowed": NFL_MENU_BACK_AUDIO_TARGET, "name": "target", "required": True}]
            or capability.accepted_extensions != (".wav",)
        ):
            raise ProviderError("Capability registry does not authorize the fixed NFL audio provider")
        self._load_closure(self._writer_members())
        self._load_closure(self._verifier_members())
        self._pinned_payload(
            self.recipe_schema_file,
            self.recipe_schema_file_sha256,
            "NFL audio recipe schema",
        )

    def _pinned_payload(self, relative: str, expected: str, label: str) -> bytes:
        if self._sha256_re.fullmatch(expected) is None:
            raise ProviderError(f"Allowlisted {label} SHA-256 pin is malformed")
        relative_path = Path(relative)
        if (
            not relative_path.parts
            or relative_path == Path(".")
            or relative_path.is_absolute()
            or ".." in relative_path.parts
        ):
            raise ProviderError(f"Allowlisted {label} path is not workspace-relative")
        workspace = self.workspace.expanduser()
        try:
            workspace_info = workspace.lstat()
        except FileNotFoundError as exc:
            raise ProviderError("NFL audio provider workspace is missing") from exc
        if (
            not stat.S_ISDIR(workspace_info.st_mode)
            or stat.S_ISLNK(workspace_info.st_mode)
            or _is_reparse_point(workspace_info)
        ):
            raise ProviderError("NFL audio provider workspace must be a non-symlink directory")
        workspace = workspace.resolve(strict=True)
        path = workspace / relative_path
        parent = path.parent
        while parent != workspace:
            try:
                parent_info = parent.lstat()
            except FileNotFoundError as exc:
                raise ProviderError(f"Allowlisted {label} parent is missing") from exc
            if (
                not stat.S_ISDIR(parent_info.st_mode)
                or stat.S_ISLNK(parent_info.st_mode)
                or _is_reparse_point(parent_info)
            ):
                raise ProviderError(f"Allowlisted {label} parent must be a non-symlink directory")
            parent = parent.parent
        if path == workspace or workspace not in path.parents:
            raise ProviderError(f"Allowlisted {label} escapes the provider workspace")
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(f"Allowlisted {label} is missing") from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or _is_reparse_point(supplied)
            or supplied.st_nlink != 1
            or not 0 < supplied.st_size <= self._max_pinned_module_bytes
        ):
            raise ProviderError(
                f"Allowlisted {label} must be a bounded, single-link, non-symlink regular file"
            )
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (supplied.st_dev, supplied.st_ino, supplied.st_size)
            ):
                raise ProviderError(f"Allowlisted {label} changed before its pinned read")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    raise ProviderError(f"Allowlisted {label} shortened during its pinned read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ProviderError(f"Allowlisted {label} grew during its pinned read")
            payload = b"".join(chunks)
            current = path.stat(follow_symlinks=False)
            if (
                current.st_nlink != 1
                or (current.st_dev, current.st_ino, current.st_size)
                != (opened.st_dev, opened.st_ino, opened.st_size)
            ):
                raise ProviderError(f"Allowlisted {label} pathname changed during its pinned read")
        finally:
            os.close(descriptor)
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ProviderError(f"Allowlisted {label} hash changed")
        return payload

    def _load_closure(
        self,
        members: tuple[tuple[str, str, str, str, frozenset[str]], ...],
    ) -> dict[str, bytes]:
        payloads: dict[str, bytes] = {}
        archived_modules = {
            Path(archive_name).stem
            for _relative, _expected, _label, archive_name, _imports in members
            if archive_name != "__main__.py"
        }
        for relative, expected, label, archive_name, expected_imports in members:
            if archive_name in payloads:
                raise ProviderError("NFL audio staged closure has a duplicate archive member")
            payload = self._pinned_payload(relative, expected, label)
            try:
                tree = ast.parse(payload, filename=relative)
            except (SyntaxError, UnicodeDecodeError) as exc:
                raise ProviderError(f"Allowlisted {label} is not valid Python source") from exc
            external: set[str] = set()
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level != 0:
                        raise ProviderError(f"Allowlisted {label} uses a relative import")
                    if node.module is not None:
                        names = [node.module]
                if isinstance(node, ast.Call):
                    function = node.func
                    if (
                        isinstance(function, ast.Name)
                        and function.id in self._dynamic_import_calls
                    ) or (
                        isinstance(function, ast.Attribute)
                        and function.attr in self._dynamic_import_calls
                    ):
                        raise ProviderError(
                            f"Allowlisted {label} uses a dynamic import/code loader"
                        )
                for name in names:
                    top = name.split(".", 1)[0]
                    if top in self._dynamic_import_modules:
                        raise ProviderError(
                            f"Allowlisted {label} imports a dynamic loader module"
                        )
                    if top not in sys.stdlib_module_names:
                        external.add(top)
            if external != set(expected_imports):
                raise ProviderError(f"Allowlisted {label} external import closure changed")
            if not external <= archived_modules:
                raise ProviderError(f"Allowlisted {label} import is absent from the staged closure")
            payloads[archive_name] = payload
        if "__main__.py" not in payloads:
            raise ProviderError("NFL audio staged closure has no fixed entry point")
        return payloads

    @contextmanager
    def _sealed_zipapp(
        self,
        members: tuple[tuple[str, str, str, str, frozenset[str]], ...],
        label: str,
    ) -> Iterator[_StagedModule]:
        payloads = self._load_closure(members)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as stream:
            for name in sorted(payloads, key=lambda value: (value != "__main__.py", value)):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat.S_IFREG | 0o444) << 16
                stream.writestr(info, payloads[name])
        raw = archive.getvalue()
        if supports_sealed_memfd():
            with self._sealed_memfd_module(raw, label) as module:
                yield module
        else:
            with self._read_only_file_module(raw, label) as module:
                yield module

    @contextmanager
    def _sealed_memfd_module(self, raw: bytes, label: str) -> Iterator[_StagedModule]:
        """Linux path: an anonymous, kernel-write-sealed ``memfd`` closure.

        The staged bytes cannot be modified afterwards even by this process, and
        the executable is handed to the subprocess through ``/proc/self/fd`` --
        never a lookup-able pathname an attacker could swap.  The staged module's
        ``reverify_before_exec`` is therefore a no-op: there is no swappable name
        and no writable descriptor to guard against.  ``pin_for_exec`` is a no-op
        for the same reason -- the descriptor is already held open for this whole
        context, which *is* the pin, so entering it performs no syscall and yields
        the identical ``/proc`` path this path has always executed.
        """

        descriptor = os.memfd_create(
            f"nfl2k5-audio-{label}", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
        )
        try:
            cursor = 0
            while cursor < len(raw):
                written = os.write(descriptor, raw[cursor:])
                if written <= 0:
                    raise ProviderError("NFL audio staged closure write was incomplete")
                cursor += written
            try:
                seal_readonly(descriptor, None)
            except SealIntegrityError as exc:
                raise ProviderError(
                    "NFL audio staged closure did not acquire every write seal"
                ) from exc
            opened = os.fstat(descriptor)
            staged = pread(descriptor, opened.st_size, 0)
            if (
                opened.st_size != len(raw)
                or len(staged) != opened.st_size
                or hashlib.sha256(staged).digest() != hashlib.sha256(raw).digest()
            ):
                raise ProviderError("NFL audio sealed closure bytes changed")
            proc_path = Path(f"/proc/{os.getpid()}/fd/{descriptor}")
            try:
                visible = proc_path.stat()
            except FileNotFoundError as exc:
                raise ProviderError("NFL audio sealed closure is unavailable through procfs") from exc
            if not stat.S_ISREG(visible.st_mode) or visible.st_size != len(raw):
                raise ProviderError("NFL audio sealed closure procfs identity differs")

            def _reverify_sealed_memfd() -> None:
                # Kernel write-seals make these bytes immutable even to us, and
                # the child opens them through the /proc/self/fd we hold, so no
                # name lookup can swap the executable: nothing to re-check.
                return

            @contextmanager
            def _pin_sealed_memfd_for_exec(
                _stage: ProviderStage, _emit: ProviderEventCallback
            ) -> Iterator[_PinnedExec]:
                # The pin already exists: `descriptor` stays open for the whole
                # enclosing context and `proc_path` names precisely its inode, so
                # this holds nothing further and emits nothing.  Byte for byte the
                # instructions this path has always run.
                _reverify_sealed_memfd()
                yield _PinnedExec(proc_path, True, _EXEC_PIN_LINUX_MEMFD)

            yield _StagedModule(
                proc_path, _reverify_sealed_memfd, _pin_sealed_memfd_for_exec
            )
        finally:
            os.close(descriptor)

    @contextmanager
    def _read_only_file_module(self, raw: bytes, label: str) -> Iterator[_StagedModule]:
        """Non-Linux path: a private, read-only, hash-verified file closure.

        Without ``memfd`` write-seals there is no kernel guarantee of
        immutability, so integrity is proved instead by making the file
        read-only inside a fresh private directory and re-verifying that its
        bytes still hash to the closure we intended to stage.  The file is
        removed when the context exits.

        Read-only is not a seal: an owner (or another same-user process) can
        clear the attribute and rewrite the bytes.  So the file is re-verified
        immediately before the child is launched, through the staged module's
        ``pin_for_exec`` -- and, unlike a bare re-hash, that context *keeps the
        verified object open* across ``runner.run``.  What that holds shut
        differs by platform, and on none of the platforms this fallback runs on
        does it close the check-to-use window:

        * Windows: :func:`platform_compat.reverify_sealed_before_exec` re-hashes
          the staged file and keeps a ``CreateFileW`` handle sharing READ only,
          so while the child is starting no same-user process can rewrite,
          truncate or delete those BYTES.  It does not hold the NAME the child
          opens: ``SetFileInformationByHandle(FileRenameInfoEx)`` with
          ``POSIX_SEMANTICS | REPLACE_IF_EXISTS`` rebinds a name whose file has
          open handles -- the existing handles keep the old file, every later
          open resolves to the replacement -- and the child opens by name.  So
          the window is narrowed, NOT closed, and Windows reports it exactly as
          macOS does: ``inode_pinned=False``, mechanism
          :data:`~mod_editor.core.platform_compat.SEALED_EXEC_WINDOWS_SHARE_PIN`,
          and a WARNING event on the stage.  An earlier revision of this
          docstring claimed the window was closed here; an independent audit
          showed it was not.

        * macOS: the same helper re-hashes through a descriptor it then holds, but
          macOS offers neither a cross-process fd path (no ``/proc``) nor a
          mandatory share lock, so the child opens the *name*.  A same-user
          rename/unlink swap in that instant would still be executed: the window
          is narrowed to the launch, NOT closed.  That is reported honestly --
          ``inode_pinned=False``, mechanism
          :data:`~mod_editor.core.platform_compat.SEALED_EXEC_REVERIFIED_PATH`,
          and a WARNING event on the stage -- rather than claimed away.  Closing
          it needs a macOS exec-from-held-descriptor primitive, which is
          platform_compat's job, not this provider's.

        * Any other kernel without ``memfd`` seals (an exotic Linux): unchanged
          from what it has always done -- the re-hash below runs and the staged
          pathname is executed, with the same residual, named the same way
          (``inode_pinned=False``).  Linux's real path is the sealed memfd above.

        ``reverify_before_exec`` remains available for callers that want only the
        re-hash; it drops its descriptor immediately, so it does not by itself
        close anything.  The file lives in a private, per-user staging directory
        this process just created and is removed when the context exits.
        """

        workdir = Path(tempfile.mkdtemp(prefix=f"nfl2k5-audio-{label}-"))
        module_path = workdir / "sealed-closure.zip"
        try:
            descriptor = os.open(
                module_path,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
                0o600,
            )
            try:
                cursor = 0
                while cursor < len(raw):
                    written = os.write(descriptor, raw[cursor:])
                    if written <= 0:
                        raise ProviderError("NFL audio staged closure write was incomplete")
                    cursor += written
                seal = seal_readonly(descriptor, os.fspath(module_path))
                opened = os.fstat(descriptor)
                staged = pread(descriptor, opened.st_size, 0)
                if (
                    seal.sealed
                    or not seal.read_only
                    or opened.st_size != len(raw)
                    or len(staged) != opened.st_size
                    or seal.sha256 != hashlib.sha256(raw).hexdigest()
                    or hashlib.sha256(staged).digest() != hashlib.sha256(raw).digest()
                ):
                    raise ProviderError("NFL audio sealed closure bytes changed")
            finally:
                os.close(descriptor)
            visible = module_path.lstat()
            if (
                not stat.S_ISREG(visible.st_mode)
                or stat.S_ISLNK(visible.st_mode)
                or _is_reparse_point(visible)
                or visible.st_size != len(raw)
            ):
                raise ProviderError("NFL audio sealed closure identity differs")

            expected_sha = hashlib.sha256(raw).hexdigest()
            expected_size = len(raw)

            def _reverify_sealed_file() -> None:
                # Re-open the exact staged file (no symlink/junction follow),
                # prove it is still the same inode we sealed and re-hash it
                # against the digest captured above.  A cleared read-only bit +
                # byte replacement, a rename swap, or a junction/symlink planted
                # over the name are all caught here, immediately before the
                # child opens the path.
                fd = os.open(
                    module_path,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_BINARY", 0),
                )
                try:
                    reopened = os.fstat(fd)
                    named = os.lstat(module_path)
                    if (
                        not stat.S_ISREG(reopened.st_mode)
                        or stat.S_ISLNK(named.st_mode)
                        or _is_reparse_point(named)
                        or (named.st_dev, named.st_ino)
                        != (reopened.st_dev, reopened.st_ino)
                        or reopened.st_size != expected_size
                    ):
                        raise ProviderError(
                            "NFL audio sealed closure was swapped before execution"
                        )
                    digest = hashlib.sha256()
                    remaining = expected_size
                    while remaining:
                        chunk = pread(
                            fd, min(1 << 20, remaining), expected_size - remaining
                        )
                        if not chunk:
                            raise ProviderError(
                                "NFL audio sealed closure shortened before execution"
                            )
                        digest.update(chunk)
                        remaining -= len(chunk)
                    if digest.hexdigest() != expected_sha:
                        raise ProviderError(
                            "NFL audio sealed closure bytes changed before execution"
                        )
                finally:
                    os.close(fd)

            @contextmanager
            def _pin_sealed_file_for_exec(
                stage: ProviderStage, emit: ProviderEventCallback
            ) -> Iterator[_PinnedExec]:
                if not (platform_compat.IS_WINDOWS or platform_compat.IS_MACOS):
                    # No memfd seals and not one of the ported platforms: run the
                    # exact instructions this branch has always run -- re-hash the
                    # staged snapshot, then execute the staged pathname -- and
                    # report the residual that leaves rather than a pin we do not
                    # hold.
                    _reverify_sealed_file()
                    yield _PinnedExec(module_path, False, _EXEC_PIN_REHASHED_PATH)
                    return
                # Windows/macOS: re-verify through platform_compat and KEEP what
                # it hands back open across runner.run, so the verified object --
                # not merely a verified snapshot of it -- is what the child gets
                # ON LINUX, whose /proc fd path names the descriptor itself.
                # macOS and Windows hand the child a NAME, so there the pin
                # narrows the window rather than closing it; inode_pinned says
                # which case applies and the WARNING below fires when it is the
                # weaker one.
                try:
                    handle = platform_compat.reverify_sealed_before_exec(
                        module_path, expected_sha, expected_size=expected_size
                    )
                except SealIntegrityError as exc:
                    raise ProviderError(
                        "NFL audio sealed closure was swapped or rewritten before "
                        "execution"
                    ) from exc
                except (platform_compat.DirectoryTransactionUnavailable, OSError) as exc:
                    # The platform could not give us the pin it promises (no
                    # kernel32, an unreadable staging file).  Refuse to launch
                    # rather than execute an unpinned module.
                    raise ProviderError(
                        "NFL audio sealed closure could not be pinned for execution"
                    ) from exc
                try:
                    if handle.sha256 != expected_sha:
                        raise ProviderError(
                            "NFL audio sealed closure bytes changed before execution"
                        )
                    if handle.inode_pinned:
                        emit(ProviderEvent(
                            stage,
                            "INFO",
                            "Sealed NFL audio closure held pinned across launch "
                            f"({handle.mechanism}): it cannot be replaced while "
                            "the child starts",
                        ))
                    else:
                        emit(ProviderEvent(
                            stage,
                            "WARNING",
                            "Sealed NFL audio closure re-verified but NOT pinned "
                            f"across launch ({handle.mechanism}): this platform "
                            "cannot stop a same-user rename swap between the "
                            "check and the child opening the module",
                        ))
                    yield _PinnedExec(
                        Path(handle.exec_path), handle.inode_pinned, handle.mechanism
                    )
                finally:
                    handle.close()

            yield _StagedModule(
                module_path, _reverify_sealed_file, _pin_sealed_file_for_exec
            )
        finally:
            try:
                module_path.chmod(stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
            shutil.rmtree(workdir, ignore_errors=True)

    @staticmethod
    def _absolute(path: Path) -> Path:
        requested = path.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        return requested.resolve(strict=False)

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
            raise ProviderError("Fixed NFL audio build requires the recognized retail XISO")
        resolved = Nfl2k5UnifiedVisualProvider._regular_non_symlink(source, "source XISO")
        if Path(request.source.inspected_path).resolve(strict=True) != resolved:
            raise ProviderError("NFL audio source inspection path does not match the selected XISO")
        return resolved

    @staticmethod
    def _validate_outputs(
        request: ProviderRequest, source: Path, recipe: NflMenuBackAudioRecipe
    ) -> None:
        paths = (request.output_xiso, request.manifest, request.artifact_dir)
        canonical: list[Path] = []
        for path in paths:
            requested = path.expanduser()
            if not requested.is_absolute():
                requested = Path.cwd() / requested
            if os.path.lexists(requested):
                raise OutputRefusedError(f"Fixed NFL audio output already exists: {requested}")
            try:
                parent = requested.parent.lstat()
            except FileNotFoundError as exc:
                raise OutputRefusedError(
                    f"Fixed NFL audio output parent is missing: {requested.parent}"
                ) from exc
            if (
                not stat.S_ISDIR(parent.st_mode)
                or stat.S_ISLNK(parent.st_mode)
                or _is_reparse_point(parent)
            ):
                raise OutputRefusedError(
                    "Fixed NFL audio output parent must be a non-symlink directory"
                )
            canonical.append(requested.resolve(strict=False))
        if len(set(canonical)) != 3:
            raise OutputRefusedError("NFL audio XISO, manifest, and artifacts must be distinct")
        protected = {
            source.resolve(strict=True),
            recipe.recipe_path.resolve(strict=True),
            recipe.wav_path.resolve(strict=True),
        }
        if any(path in protected for path in canonical):
            raise OutputRefusedError("NFL audio outputs cannot replace source, recipe, or WAV")


__all__ = ["Nfl2k5MenuBackAudioProvider"]

"""Typed provider for APF 2K8's shared alpha-only ``digital_font``."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Iterator, Mapping

from . import platform_compat
from .platform_compat import SealIntegrityError
from .apf_digital_font import (
    APF_DIGITAL_FONT_DIMENSIONS,
    APF_DIGITAL_FONT_RECIPE_SCHEMA,
    APF_DIGITAL_FONT_SCOPE,
    APF_DIGITAL_FONT_STORED_CHANNEL,
    APF_DIGITAL_FONT_TARGET,
    ApfDigitalFontRecipe,
    load_apf_digital_font_recipe,
)
from .capabilities import Capability, Classification
from .errors import OutputRefusedError
from .model import GameId
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


class Apf2k8DigitalFontProvider:
    """Fixed global-alpha recipe -> copied 0A -> independent verifier."""

    provider_id = "apf2k8-digital-font-v1"
    capability_ids = frozenset({"apf2k8.scorebug_presentation.digital_font"})
    backend_module = "tools/apf_digital_font_patch.py"
    verifier_module = "tools/apf_digital_font_verify.py"
    recipe_schema_file = "mod_editor/apf_digital_font_recipe.schema.json"
    format_spec_file = "reports/specs/apf_digital_font_asset_format.v1.json"
    source_sha256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
    source_size = 1_140_850_688
    backend_schema = "apf_digital_font_patch/v1"
    verify_schema = "apf_digital_font_verify/v1"
    max_manifest_bytes = 8 * 1024 * 1024
    max_pinned_file_bytes = 16 * 1024 * 1024
    module_pins: Mapping[str, str] = {
        "tools/apf_inner.py": "7eb66ba962e5bfb976da6f7b47b58bb88c1d755bc1fec4611c8b9e68a4e66f86",
        "tools/apf_outer.py": "7e86c0e5fb6338e14d7dab5d45f408655d456beeb9d10c6f28f5bc5c1bb088ac",
        "tools/apf_texture_patch.py": "194d37682ac28fef1853e4c27c8a0327b75ef52218afcf1fbc6f4fa169e1b7b9",
        "tools/apf_xenos_dxt5a.py": "063c4d564748019198b54898c3676f541a85319606f3ae9bd733d9340c7d66f6",
        "tools/apf_digital_font_layout.py": "df7ef3f9f5a664a0b5edce4e1dc15ccbca6fd9e3eb3579377f12abb0b392fcb4",
        "tools/apf_digital_font_transport.py": "4ed563c17df79df3f0bef6190546c5fbe82314ed71fc3bf7a965c845130a0bf8",
        backend_module: "e72f91b746f44f1729b5e36d39a1cd0944ffab0194ab7e2cb36d5f3c1185ccd7",
        verifier_module: "7846a5ecc91763296bea5e2b2f722de3c1b2137b769ceaa9406a64999042baf8",
        recipe_schema_file: "265edf051e513cdb9174b6c2d0109e892ca2e64e281ee07711c1665bfbc9cb93",
        format_spec_file: "0a53dbcfa291a7a3f4d1714f78d23ccaeef0e82cb1547171fdc7b86a07f6b678",
    }

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
        self,
        request: ProviderRequest,
        capability: Capability,
        emit: ProviderEventCallback,
    ) -> None:
        emit(ProviderEvent(
            ProviderStage.PREFLIGHT,
            "INFO",
            "Checking fixed APF digital_font alpha-only contract",
        ))
        self._validate_capability(request, capability)
        recipe = load_apf_digital_font_recipe(request.backend_project)
        source = self._source_0a(request)
        self._validate_outputs(request, source, recipe)
        emit(ProviderEvent(
            ProviderStage.PREFLIGHT,
            "WARNING",
            "digital_font is a shared global UI texture; field-scorebug-only side effects are not proved",
        ))
        emit(ProviderEvent(
            ProviderStage.PREFLIGHT,
            "WARNING",
            "Runtime visibility is unproved and the bounded DXT5A encoder is not production-quality",
        ))
        progress_bucket = -1

        def progress(completed: int, total: int) -> None:
            nonlocal progress_bucket
            bucket = 10 if total == 0 else min(10, (completed * 10) // total)
            if bucket != progress_bucket:
                progress_bucket = bucket
                emit(ProviderEvent(
                    ProviderStage.PREFLIGHT,
                    "INFO",
                    f"Read-only APF 0A recheck {bucket * 10}%",
                ))

        digest, size = self.source_hasher(source, progress)
        if digest != self.source_sha256 or digest != request.source.sha256:
            raise ProviderError("APF 0A changed or does not match the pinned retail SHA-256")
        if size != self.source_size or size != request.source.size:
            raise ProviderError("APF 0A size changed after editor recognition")
        emit(ProviderEvent(
            ProviderStage.PREFLIGHT,
            "INFO",
            "Fixed shared digital_font recipe, white RGB, and stored alpha plane passed preflight",
        ))

    def validate(
        self,
        request: ProviderRequest,
        capability: Capability,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        arguments = (
            "validate-recipe",
            "--recipe",
            os.fspath(request.backend_project),
        )
        result = self._run_pinned_module(
            self.verifier_module, arguments, ProviderStage.VALIDATE, emit
        )
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "APF digital_font independent recipe validator returned invalid JSON"
            ) from exc
        if (
            not isinstance(report, dict)
            or report.get("schema") != APF_DIGITAL_FONT_RECIPE_SCHEMA
            or report.get("recipe_valid") is not True
            or report.get("target") != APF_DIGITAL_FONT_TARGET
            or report.get("scope") != APF_DIGITAL_FONT_SCOPE
            or report.get("stored_channel") != APF_DIGITAL_FONT_STORED_CHANNEL
            or report.get("png_dimensions") != list(APF_DIGITAL_FONT_DIMENSIONS)
            or report.get("png_mode") != "RGBA"
            or report.get("png_rgb_solid_white") is not True
            or report.get("field_scorebug_only_proved") is not False
            or report.get("runtime_visibility_proved") is not False
            or report.get("production_dxt5a_encoder_ready") is not False
        ):
            raise ProviderError(
                "APF digital_font validator did not prove the alpha-only global boundary"
            )
        return result

    def build(
        self,
        request: ProviderRequest,
        capability: Capability,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        recipe = load_apf_digital_font_recipe(request.backend_project)
        source = self._source_0a(request)
        arguments = (
            "--index",
            os.fspath(source),
            "--png",
            os.fspath(recipe.png_path),
            "--output-volume",
            os.fspath(request.output_xiso),
            "--manifest",
            os.fspath(request.manifest),
        )
        result = self._run_pinned_module(
            self.backend_module, arguments, ProviderStage.BUILD, emit
        )
        if "APF_DIGITAL_FONT_PATCH_PASS" not in result.stdout:
            raise ProviderError("APF digital_font writer omitted its success marker")
        manifest = self._read_manifest(request.manifest)
        family = manifest.get("family_target", {})
        copied = manifest.get("copied_volume", {})
        if (
            manifest.get("schema") != self.backend_schema
            or manifest.get("mode") != "patched"
            or not isinstance(family, dict)
            or family.get("outer_index") != 1310
            or family.get("inner_index") != 246
            or family.get("shared_global_ui_texture") is not True
            or family.get("field_scorebug_only_proved") is not False
            or family.get("runtime_visibility_proved") is not False
            or not isinstance(copied, dict)
            or Path(str(copied.get("output_volume"))).resolve()
            != request.output_xiso.resolve()
        ):
            raise ProviderError("APF digital_font writer manifest changed its fixed boundary")
        return result

    def verify(
        self,
        request: ProviderRequest,
        capability: Capability,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        source = self._source_0a(request)
        arguments = (
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
        result = self._run_pinned_module(
            self.verifier_module, arguments, ProviderStage.VERIFY, emit
        )
        if "APF_DIGITAL_FONT_VERIFY_PASS" not in result.stdout:
            raise ProviderError("Independent APF digital_font verifier omitted its marker")
        return result

    def _run(
        self,
        argv: tuple[str, ...],
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        emit(ProviderEvent(
            stage,
            "INFO",
            f"Starting fixed APF digital_font {stage.value.lower()}",
        ))
        result = self.runner.run(argv, self.workspace, stage, emit)
        if result.returncode != 0:
            details = (result.stderr or result.stdout).strip().splitlines()
            tail = " | ".join(details[-5:]) if details else "no diagnostic output"
            raise ProviderError(
                f"APF digital_font {stage.value.lower()} failed with exit "
                f"{result.returncode}: {tail}"
            )
        return result

    def _run_pinned_module(
        self,
        relative: str,
        arguments: tuple[str, ...],
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> ProviderCommandResult:
        """Run an exact private copy of the complete external Python closure.

        Every allowlisted module is re-read from the workspace, hash-checked
        against its pin and written into a fresh private directory, so the child
        imports the copy and never the repository tree that could be rewritten
        under it.  Staging alone does not decide *what the child executes*: the
        child is handed a pathname and opens it itself, so between the last write
        here and that open a same-user process can clear the read-only bit and
        replace a staged module -- exactly the writer/verifier substitution the
        staged copy exists to prevent.

        On the ported platforms that window is narrowed across the launch, and on
        neither of them is it closed.  :meth:`_pinned_closure` re-verifies every
        staged module through
        :func:`platform_compat.reverify_sealed_before_exec` and keeps what that
        returns open until the subprocess has been created:

        * Windows -- a deny-write/deny-delete share pin per module, so while the
          child starts no same-user process can rewrite, truncate or delete the
          BYTES any of those pins hold.  A pin does not hold the NAME the child
          opens: ``SetFileInformationByHandle(FileRenameInfoEx)`` with
          ``POSIX_SEMANTICS | REPLACE_IF_EXISTS`` rebinds a name whose file has
          open handles -- the existing handles keep the old file, every later
          open resolves to the replacement -- and the child opens each module by
          name.  So the check-to-use window is narrowed, NOT closed, and Windows
          reports that the same way macOS does (a WARNING event, ``inode_pinned``
          ``False``).  An earlier revision of this docstring claimed the window
          was closed here; an independent audit showed it was not.
        * macOS -- no lock of any kind exists: the modules are re-hashed immediately
          before the launch and their descriptors held, but the child re-opens by
          name, so a same-user rename swap in that instant would still be
          executed.  The window is narrowed, NOT closed, and that is reported (a
          WARNING event, ``inode_pinned`` ``False``) rather than claimed away.
        * Any other platform (Linux) -- unchanged: the staged copy is executed by
          pathname, exactly the instructions it runs today, with the residual that
          has always applied.

        The argv path is always the staged pathname: the closure's sibling modules
        are imported from the entry point's own directory, so an exec path that
        named the same inode from somewhere else (a POSIX ``/proc`` fd path) would
        break those imports.  Because the child therefore opens every module by
        name, only a pin that holds the *name* counts as closing the window; one
        that pins an inode elsewhere is reported as the residual it really leaves.
        """

        if relative not in self.module_pins or not relative.startswith("tools/"):
            raise ProviderError("APF digital_font execution module is not allowlisted")
        with tempfile.TemporaryDirectory(prefix="mod-editor-apf-font-provider-") as raw:
            bundle = Path(raw)
            staged_modules: dict[str, Path] = {}
            staged_pins: dict[str, tuple[Path, str, int]] = {}
            for module_relative, expected in self.module_pins.items():
                module_path = Path(module_relative)
                if module_path.parts[0] != "tools" or module_path.suffix != ".py":
                    continue
                payload = self._read_pinned(module_relative, expected)
                target = bundle / module_path
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(
                    target,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
                    0o400,
                )
                try:
                    cursor = 0
                    while cursor < len(payload):
                        written = os.write(descriptor, payload[cursor:])
                        if written <= 0:
                            raise ProviderError(
                                "Could not stage the pinned APF digital_font closure"
                            )
                        cursor += written
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                staged_modules[module_relative] = target
                staged_pins[module_relative] = (target, expected, len(payload))
            staged = staged_modules.get(relative)
            if staged is None:
                raise ProviderError("APF digital_font staged execution module is missing")
            if not (platform_compat.IS_WINDOWS or platform_compat.IS_MACOS):
                return self._run(
                    (sys.executable, os.fspath(staged), *arguments), stage, emit
                )
            # Ported platforms only: hold the whole staged closure pinned until the
            # child exists.  That makes the checked module the module that runs
            # only where the handle names the exec path (Linux /proc); this
            # closure always executes a staged PATHNAME so its sibling imports
            # resolve, so on macOS and Windows a same-user rename can still
            # rebind that name -- counted and warned about below, not claimed
            # away.
            with self._pinned_closure(staged_pins, relative, stage, emit) as exec_path:
                return self._run(
                    (sys.executable, os.fspath(exec_path), *arguments), stage, emit
                )

    @contextmanager
    def _pinned_closure(
        self,
        staged: Mapping[str, tuple[Path, str, int]],
        entry: str,
        stage: ProviderStage,
        emit: ProviderEventCallback,
    ) -> Iterator[Path]:
        """Hold every staged module re-verified and pinned across the launch.

        The child imports the entry point's siblings out of the same directory, so
        pinning only the entry point would leave every helper module swappable
        after its check; all of them are re-verified and held.  What "held" buys
        differs by platform and is reported, never assumed:
        :attr:`platform_compat.SealedExecHandle.inode_pinned` is ``True`` only
        where opening the ``exec_path`` it hands back is guaranteed to yield the
        bytes just verified -- today only the Linux ``/proc/<pid>/fd`` inode pin,
        which this closure cannot execute from because the child has to open the
        staged pathname for its sibling imports to resolve.  On both platforms
        this method runs on the pin therefore leaves a name-swap window open:
        the Windows share pin holds the BYTES it opened but not the NAME (a
        ``POSIX_SEMANTICS`` ``FileRenameInfoEx`` rebinds a name whose file has
        open handles, and later opens get the replacement), and macOS holds only
        a descriptor no other process can name.  Those modules are counted and
        the residual is emitted as a WARNING on this stage; the INFO branch is
        reached only if platform_compat ever hands back a pin on the very name
        the child opens.  Any mismatch, or any failure to obtain the pin the
        platform promises, refuses the launch instead of running an unverified
        closure.
        """

        with ExitStack() as pins:
            handles: dict[str, platform_compat.SealedExecHandle] = {}
            for module_relative in sorted(staged):
                path, expected, size = staged[module_relative]
                try:
                    handle = platform_compat.reverify_sealed_before_exec(
                        path, expected, expected_size=size
                    )
                except SealIntegrityError as exc:
                    raise ProviderError(
                        "APF digital_font staged closure module was replaced "
                        f"before execution: {module_relative}"
                    ) from exc
                except (
                    platform_compat.DirectoryTransactionUnavailable,
                    OSError,
                ) as exc:
                    raise ProviderError(
                        "APF digital_font staged closure module could not be "
                        f"pinned for execution: {module_relative}"
                    ) from exc
                pins.enter_context(handle)
                if handle.sha256 != expected:
                    raise ProviderError(
                        "APF digital_font staged closure module hash changed "
                        f"before execution: {module_relative}"
                    )
                handles[module_relative] = handle
            # The child opens every module of this closure BY NAME -- the entry
            # point from argv, its siblings from that same directory through
            # ``import`` -- so the guarantee is only as strong as the pin's hold on
            # the *names*.  A handle that pins an inode under some other name (a
            # POSIX ``/proc`` fd path) cannot be executed here without breaking
            # those imports, so it does not count as covering the name and is
            # reported as the residual it leaves rather than as a pin.
            name_pinned = {
                module_relative: (
                    handle.inode_pinned
                    and Path(handle.exec_path) == staged[module_relative][0]
                )
                for module_relative, handle in handles.items()
            }
            entry_handle = handles[entry]
            mechanism = (
                entry_handle.mechanism
                if name_pinned[entry]
                else platform_compat.SEALED_EXEC_REVERIFIED_PATH
            )
            unpinned = sorted(
                module_relative
                for module_relative, is_name_pinned in name_pinned.items()
                if not is_name_pinned
            )
            if unpinned:
                emit(ProviderEvent(
                    stage,
                    "WARNING",
                    "Staged APF digital_font closure re-verified but NOT pinned "
                    f"across launch ({mechanism}): this platform cannot stop a "
                    f"same-user rename swap of {len(unpinned)} of its "
                    f"{len(handles)} modules between the check and the child "
                    "opening them",
                ))
            else:
                emit(ProviderEvent(
                    stage,
                    "INFO",
                    "Staged APF digital_font closure held pinned across launch "
                    f"({mechanism}): none of its {len(handles)} modules can be "
                    "replaced while the child starts",
                ))
            yield staged[entry][0]

    def _validate_capability(
        self, request: ProviderRequest, capability: Capability
    ) -> None:
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
            or fields != [{
                "allowed": "digital_font only",
                "name": "target",
                "required": True,
            }]
        ):
            raise ProviderError(
                "Capability registry does not authorize the APF digital_font provider"
            )
        for relative, expected in self.module_pins.items():
            self._pinned_file(relative, expected)

    def _pinned_file(self, relative: str, expected: str) -> Path:
        self._read_pinned(relative, expected)
        return (self.workspace / relative).resolve(strict=True)

    def _read_pinned(self, relative: str, expected: str) -> bytes:
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or not relative_path.parts
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        ):
            raise ProviderError(
                "Allowlisted APF digital_font path must be safely workspace-relative"
            )
        workspace = self.workspace.expanduser()
        try:
            workspace_info = workspace.lstat()
        except FileNotFoundError as exc:
            raise ProviderError("APF digital_font provider workspace is missing") from exc
        if not stat.S_ISDIR(workspace_info.st_mode) or stat.S_ISLNK(
            workspace_info.st_mode
        ):
            raise ProviderError(
                "APF digital_font provider workspace must be a non-symlink directory"
            )
        workspace = workspace.resolve(strict=True)
        parent = workspace
        for component in relative_path.parts[:-1]:
            parent /= component
            try:
                parent_info = parent.lstat()
            except FileNotFoundError as exc:
                raise ProviderError(
                    f"Allowlisted APF digital_font parent is missing: {relative}"
                ) from exc
            if not stat.S_ISDIR(parent_info.st_mode) or stat.S_ISLNK(
                parent_info.st_mode
            ):
                raise ProviderError(
                    "Allowlisted APF digital_font parent must be a non-symlink directory"
                )
        path = workspace / relative_path
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError(f"Allowlisted APF digital_font file is missing: {relative}") from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or supplied.st_nlink != 1
            or not 0 < supplied.st_size <= self.max_pinned_file_bytes
        ):
            raise ProviderError(
                "Allowlisted APF digital_font file must be a bounded single-link "
                f"regular file: {relative}"
            )
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
            )
        except OSError as exc:
            raise ProviderError(
                f"Allowlisted APF digital_font file could not be opened safely: {relative}"
            ) from exc
        try:
            opened = os.fstat(descriptor)
            identity = (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
                opened.st_nlink,
            )
            if identity != (
                supplied.st_dev,
                supplied.st_ino,
                supplied.st_size,
                supplied.st_mtime_ns,
                supplied.st_nlink,
            ):
                raise ProviderError(
                    f"Allowlisted APF digital_font file changed before open: {relative}"
                )
            payload = bytearray()
            while len(payload) < opened.st_size:
                chunk = os.read(descriptor, min(1024 * 1024, opened.st_size - len(payload)))
                if not chunk:
                    raise ProviderError(
                        f"Allowlisted APF digital_font file shortened: {relative}"
                    )
                payload.extend(chunk)
            if os.read(descriptor, 1):
                raise ProviderError(
                    f"Allowlisted APF digital_font file grew: {relative}"
                )
            current = path.lstat()
            if (
                current.st_dev,
                current.st_ino,
                current.st_size,
                current.st_mtime_ns,
                current.st_nlink,
            ) != identity:
                raise ProviderError(
                    f"Allowlisted APF digital_font file changed while reading: {relative}"
                )
            result = bytes(payload)
            if hashlib.sha256(result).hexdigest() != expected:
                raise ProviderError(
                    f"Allowlisted APF digital_font file hash changed: {relative}"
                )
            return result
        finally:
            os.close(descriptor)

    def _source_0a(self, request: ProviderRequest) -> Path:
        source = Path(request.source.selected_path)
        try:
            selected = source.resolve(strict=True)
            inspected = Path(request.source.inspected_path).resolve(strict=True)
        except OSError as exc:
            raise ProviderError("Pinned APF 0A source path is unavailable") from exc
        if (
            not request.source.recognized
            or request.source.detected_game != GameId.APF2K8.value
            or request.source.fingerprint_id != "apf2k8-usa-volume-0a"
            or request.source.kind != "apf-volume-0a"
            or request.source.sha256 != self.source_sha256
            or request.source.size != self.source_size
            or inspected != selected
        ):
            raise ProviderError(
                "Typed APF digital_font build requires the recognized pinned retail 0A"
            )
        return Nfl2k5UnifiedVisualProvider._regular_non_symlink(
            selected, "source APF 0A"
        )

    def _validate_outputs(
        self,
        request: ProviderRequest,
        source: Path,
        recipe: ApfDigitalFontRecipe,
    ) -> None:
        requested_paths = (
            request.output_xiso,
            request.manifest,
            request.artifact_dir,
        )
        canonical: list[Path] = []
        for path in requested_paths:
            requested = path.expanduser()
            if not requested.is_absolute():
                requested = Path.cwd() / requested
            if os.path.lexists(requested):
                raise OutputRefusedError(
                    f"Typed APF digital_font output already exists: {requested}"
                )
            try:
                parent = requested.parent.lstat()
            except FileNotFoundError as exc:
                raise OutputRefusedError(
                    f"Typed APF digital_font output parent is missing: {requested.parent}"
                ) from exc
            if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
                raise OutputRefusedError(
                    "Typed APF digital_font output parent must be a non-symlink directory"
                )
            canonical.append(requested.resolve(strict=False))
        if len(set(canonical)) != 3:
            raise OutputRefusedError(
                "APF digital_font output 0A, manifest, and artifacts must be distinct"
            )
        protected = {
            source.resolve(strict=True),
            recipe.recipe_path.resolve(strict=True),
            recipe.png_path.resolve(strict=True),
        }
        if any(path in protected for path in canonical):
            raise OutputRefusedError(
                "APF digital_font outputs cannot replace source, recipe, or PNG"
            )

    def _read_manifest(self, path: Path) -> dict[str, object]:
        try:
            supplied = path.lstat()
        except FileNotFoundError as exc:
            raise ProviderError("APF digital_font writer did not create its manifest") from exc
        if (
            not stat.S_ISREG(supplied.st_mode)
            or stat.S_ISLNK(supplied.st_mode)
            or not 0 < supplied.st_size <= self.max_manifest_bytes
        ):
            raise ProviderError("APF digital_font manifest is not a bounded regular file")
        try:
            value = json.loads(path.read_bytes())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProviderError("APF digital_font manifest is invalid JSON") from exc
        if not isinstance(value, dict):
            raise ProviderError("APF digital_font manifest root is not an object")
        return value


__all__ = ["Apf2k8DigitalFontProvider"]

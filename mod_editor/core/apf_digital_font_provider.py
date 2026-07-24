"""Typed provider for APF 2K8's shared alpha-only ``digital_font``."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Mapping

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
        "tools/apf_inner.py": "75a74b34524b3861785b916e3470862bccfe278825a63aa2dccb924849ae9606",
        "tools/apf_outer.py": "eb89734ed3ad0205ff7d8732b2f7f93368eff861ccbc5e1473d4e21f25e8a62e",
        "tools/apf_texture_patch.py": "ee4ba6a6594db45c1416cf8a3fa96b3541f5883c5ed317f1e2af099593eaf97c",
        "tools/apf_xenos_dxt5a.py": "c95e556e55de81b8576da2e3bd3311018137cb449167c74121be3d5010ff5443",
        "tools/apf_digital_font_layout.py": "c4b8b724f125d9a29970f06a5edc4dd92c4cf074eb7ce8f6f879be2b32ebd7b1",
        "tools/apf_digital_font_transport.py": "a4b08c3ad31d195aa1b3e312a54690b42faba83de93369b732669264d959d481",
        backend_module: "e72f91b746f44f1729b5e36d39a1cd0944ffab0194ab7e2cb36d5f3c1185ccd7",
        verifier_module: "7ba6cd2172d9ae4f9a1a2d4cd9d485e0d644ba7a31baecbcca7da1fe1cd3b531",
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
        """Run an exact private copy of the complete external Python closure."""

        if relative not in self.module_pins or not relative.startswith("tools/"):
            raise ProviderError("APF digital_font execution module is not allowlisted")
        with tempfile.TemporaryDirectory(prefix="mod-editor-apf-font-provider-") as raw:
            bundle = Path(raw)
            staged_modules: dict[str, Path] = {}
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
                    | getattr(os, "O_CLOEXEC", 0),
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
            staged = staged_modules.get(relative)
            if staged is None:
                raise ProviderError("APF digital_font staged execution module is missing")
            return self._run(
                (sys.executable, os.fspath(staged), *arguments), stage, emit
            )

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
                | getattr(os, "O_CLOEXEC", 0),
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

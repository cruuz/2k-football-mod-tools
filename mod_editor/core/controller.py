"""UI-neutral controller and explicit boundary around future patch backends."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
from typing import Callable

from .capabilities import Capability, CapabilityRegistry, CapabilityRegistryLoader
from .errors import ActionNotImplementedError, ValidationError
from .model import GameId, LogEntry, ModProject, ReplacementItem
from .output import CopyResult, create_source_copy, validate_copy_destination
from .persistence import load_project, save_project
from .providers import (
    ProviderEvent,
    ProviderOrchestrator,
    ProviderRequest,
    ProviderRunResult,
    derived_provider_outputs,
)
from .sources import HashProgress, SourceInspector


class IssueLevel(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class ValidationIssue:
    level: IssueLevel
    message: str


LogListener = Callable[[LogEntry], None]


class ModEditorController:
    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        inspector: SourceInspector | None = None,
        log_listener: LogListener | None = None,
        provider_orchestrator: ProviderOrchestrator | None = None,
    ):
        self.registry = registry or CapabilityRegistryLoader().load(check_files=False)
        self.inspector = inspector or SourceInspector()
        self.project: ModProject | None = None
        self.log_listener = log_listener
        self.providers = provider_orchestrator or ProviderOrchestrator(self.registry)

    def create_project(self, name: str, game: GameId) -> ModProject:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("Project name cannot be empty")
        self.project = ModProject(cleaned, game)
        self._log("INFO", f"Created {game.display_name} project: {cleaned}")
        if self.registry.used_sample_fallback:
            self._log("WARNING", self.registry.warning)
        return self.project

    def open_project(self, path: Path) -> ModProject:
        self.project = load_project(path)
        self._log("INFO", f"Opened project: {path}")
        return self.project

    def save_project(self, path: Path | None = None) -> Path:
        project = self._require_project()
        destination = path or (Path(project.project_path) if project.project_path else None)
        if destination is None:
            raise ValidationError("Choose a project file before saving")
        self._log("INFO", f"Saving project: {destination}")
        return save_project(project, destination)

    def select_source(
        self, path: Path, progress: HashProgress | None = None
    ):
        project = self._require_project()
        self._log("INFO", f"Hashing source read-only: {path}")
        record = self.inspector.inspect(path, project.game, progress)
        project.source = record
        project.dirty = True
        if record.recognized and record.detected_game == project.game.value:
            self._log("INFO", f"Recognized source: {record.fingerprint_id} ({record.sha256})")
        elif record.recognized:
            self._log("ERROR", record.note)
        else:
            self._log("WARNING", f"Unrecognized source hash: {record.sha256}")
        return record

    def set_output_path(self, path: Path) -> None:
        project = self._require_project()
        requested = path.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        project.output_path = os.path.abspath(os.fspath(requested))
        project.dirty = True
        self._log("INFO", f"Output selected (overwrite disabled): {project.output_path}")

    def capabilities_for_project(self) -> tuple[Capability, ...]:
        project = self._require_project()
        return self.registry.for_game(project.game)

    def enqueue_replacement(
        self, capability_id: str, replacement_path: Path, target_id: str
    ) -> ReplacementItem:
        project = self._require_project()
        capability = self.registry.get(capability_id)
        if capability.game != project.game:
            raise ValidationError("Capability belongs to the other game")
        if not capability.can_queue_replacement:
            raise ValidationError(
                f"{capability.title} is {capability.badge}; replacement is not enabled"
            )
        replacement = replacement_path.expanduser().resolve(strict=True)
        if not replacement.is_file():
            raise ValidationError(f"Replacement is not a regular file: {replacement}")
        if replacement.suffix.lower() not in capability.accepted_extensions:
            allowed = ", ".join(capability.accepted_extensions)
            raise ValidationError(f"Replacement must use one of: {allowed}")
        item = ReplacementItem.create(capability_id, str(replacement), target_id)
        project.replacements.append(item)
        project.dirty = True
        self._log("INFO", f"Queued {capability.title} for named target {item.target_id}")
        return item

    def import_provider_project(
        self, capability_id: str, backend_project_path: Path
    ) -> ReplacementItem:
        project = self._require_project()
        if not self.providers.supports(capability_id):
            raise ValidationError(
                f"No typed provider is allowlisted for capability: {capability_id}"
            )
        capability = self.registry.get(capability_id)
        if capability.game != project.game:
            raise ValidationError("Typed provider capability belongs to the other game")
        supplied = backend_project_path.expanduser()
        try:
            supplied.lstat()
        except FileNotFoundError as exc:
            raise ValidationError(f"Provider project does not exist: {supplied}") from exc
        if not supplied.is_file() or supplied.is_symlink():
            raise ValidationError("Provider project must be a non-symlink regular JSON file")
        if supplied.suffix.lower() != ".json":
            raise ValidationError("Typed provider recipe/project must use a .json filename")
        provider_id = self.providers.provider_id(capability_id)
        marker = f"provider:{provider_id}"
        # Typed builds intentionally bind exactly one provider recipe. Importing
        # another typed recipe replaces the previous binding instead of leaving
        # a saved project in an invalid two-provider state.
        existing = [
            row for row in project.replacements if row.target_id.startswith("provider:")
        ]
        for row in existing:
            project.replacements.remove(row)
        item = ReplacementItem.create(capability_id, str(supplied.resolve(strict=True)), marker)
        project.replacements.append(item)
        project.dirty = True
        self._log(
            "INFO",
            f"Imported typed provider project for {capability.title}; validation has not run yet",
        )
        return item

    def provider_supported(self, capability_id: str) -> bool:
        return self.providers.supports(capability_id)

    def typed_provider_binding(self) -> ReplacementItem | None:
        project = self._require_project()
        bindings = [row for row in project.replacements if row.target_id.startswith("provider:")]
        if len(bindings) > 1:
            raise ValidationError("Project contains more than one typed provider binding")
        return bindings[0] if bindings else None

    def typed_provider_request(self) -> ProviderRequest:
        project = self._require_project()
        binding = self.typed_provider_binding()
        if binding is None:
            raise ValidationError("Import a canonical typed recipe/project JSON first")
        if not self.providers.supports(binding.capability_id):
            raise ValidationError("Saved provider binding is no longer allowlisted")
        expected_marker = f"provider:{self.providers.provider_id(binding.capability_id)}"
        if binding.target_id != expected_marker:
            raise ValidationError("Saved provider binding marker does not match the allowlist")
        unrelated = [row for row in project.replacements if row.item_id != binding.item_id]
        if unrelated:
            raise ValidationError(
                "Typed builds currently accept one imported recipe/project only; remove other queue rows"
            )
        if project.source is None:
            raise ValidationError("Select and recognize the retail source before typed validation")
        if not project.output_path:
            raise ValidationError("Choose a new copied-output path before typed validation")
        output = Path(project.output_path)
        manifest, artifacts = derived_provider_outputs(output)
        return ProviderRequest(
            capability_id=binding.capability_id,
            game=project.game,
            backend_project=Path(binding.replacement_path),
            source=project.source,
            output_xiso=output,
            manifest=manifest,
            artifact_dir=artifacts,
        )

    def validate_typed_provider(
        self, event_listener: Callable[[ProviderEvent], None] | None = None
    ) -> ProviderRunResult:
        request = self.typed_provider_request()
        return self.providers.validate(
            request, lambda event: self._handle_provider_event(event, event_listener)
        )

    def build_typed_provider(
        self, event_listener: Callable[[ProviderEvent], None] | None = None
    ) -> ProviderRunResult:
        request = self.typed_provider_request()
        return self.providers.build_and_verify(
            request, lambda event: self._handle_provider_event(event, event_listener)
        )

    def remove_replacement(self, item_id: str) -> None:
        project = self._require_project()
        original_count = len(project.replacements)
        project.replacements = [row for row in project.replacements if row.item_id != item_id]
        if len(project.replacements) == original_count:
            raise ValidationError(f"Queue item not found: {item_id}")
        project.dirty = True
        self._log("INFO", f"Removed replacement queue item: {item_id}")

    def validate_project(self) -> tuple[ValidationIssue, ...]:
        project = self._require_project()
        issues: list[ValidationIssue] = []
        if project.source is None:
            issues.append(ValidationIssue(IssueLevel.ERROR, "Select and inspect a source first"))
        else:
            source = Path(project.source.selected_path)
            if not source.exists():
                issues.append(ValidationIssue(IssueLevel.ERROR, "Selected source no longer exists"))
            if (
                project.source.detected_game is not None
                and project.source.detected_game != project.game.value
            ):
                issues.append(ValidationIssue(IssueLevel.ERROR, "Source belongs to the other game"))
            elif not project.source.recognized:
                issues.append(
                    ValidationIssue(
                        IssueLevel.WARNING,
                        "Source hash is not recognized; future writers must refuse it unless their "
                        "format-specific verifier succeeds",
                    )
                )
        if not project.output_path:
            issues.append(ValidationIssue(IssueLevel.ERROR, "Choose a copy-only output path"))
        elif project.source is not None:
            try:
                validate_copy_destination(
                    Path(project.source.selected_path), Path(project.output_path)
                )
            except Exception as exc:
                issues.append(ValidationIssue(IssueLevel.ERROR, str(exc)))
        for item in project.replacements:
            try:
                capability = self.registry.get(item.capability_id)
            except ValidationError as exc:
                issues.append(ValidationIssue(IssueLevel.ERROR, str(exc)))
                continue
            path = Path(item.replacement_path)
            if not path.is_file():
                issues.append(
                    ValidationIssue(IssueLevel.ERROR, f"Replacement is missing: {path}")
                )
            if not capability.can_queue_replacement:
                issues.append(
                    ValidationIssue(
                        IssueLevel.ERROR,
                        f"Queued capability is no longer writable: {capability.title}",
                    )
                )
        provider_rows = [
            row for row in project.replacements if row.target_id.startswith("provider:")
        ]
        ordinary_rows = [row for row in project.replacements if row not in provider_rows]
        if provider_rows:
            issues.append(
                ValidationIssue(
                    IssueLevel.INFO,
                    "Typed provider project is imported; use Typed Validate before Build + Verify",
                )
            )
        if ordinary_rows:
            issues.append(
                ValidationIssue(
                    IssueLevel.INFO,
                    "Queue is valid, but applying queued replacements is PORTME in this first UI slice",
                )
            )
        if not issues:
            issues.append(ValidationIssue(IssueLevel.INFO, "Project is ready for a source-only staging copy"))
        errors = sum(item.level == IssueLevel.ERROR for item in issues)
        warnings = sum(item.level == IssueLevel.WARNING for item in issues)
        self._log("INFO", f"Validation finished: {errors} error(s), {warnings} warning(s)")
        for issue in issues:
            if issue.level != IssueLevel.INFO:
                self._log(issue.level.value, issue.message)
        return tuple(issues)

    def create_staging_copy(self, progress=None) -> CopyResult:
        project = self._require_project()
        issues = self.validate_project()
        errors = [item for item in issues if item.level == IssueLevel.ERROR]
        if errors:
            raise ValidationError("Staging copy refused: fix validation errors first")
        if project.source is None:
            raise ValidationError("Source is not selected")
        self._log(
            "WARNING",
            "Creating an unmodified source copy only; queued assets will not be applied",
        )
        result = create_source_copy(project.source, Path(project.output_path), progress)
        self._log("INFO", f"Verified source-only copy: {result.bytes_copied} bytes")
        return result

    def apply_queued_replacements(self) -> None:
        self._log(
            "PORTME",
            "Queued replacement dispatch is intentionally unimplemented; no writer was executed",
        )
        raise ActionNotImplementedError(
            "PORTME: connect each reviewed registry capability to a fixed, typed backend adapter. "
            "Arbitrary commands and raw offsets will not be accepted."
        )

    def _require_project(self) -> ModProject:
        if self.project is None:
            raise ValidationError("Create or open a project first")
        return self.project

    def _log(self, level: str, message: str) -> None:
        if self.project is None:
            return
        entry = self.project.add_log(level, message)
        if self.log_listener:
            self.log_listener(entry)

    def _handle_provider_event(
        self,
        event: ProviderEvent,
        listener: Callable[[ProviderEvent], None] | None,
    ) -> None:
        self._log(event.level, f"{event.stage.value}: {event.message}")
        if listener:
            listener(event)

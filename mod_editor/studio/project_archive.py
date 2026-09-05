"""Retail-free, shareable 2K5 Mod Studio project archives.

A ``.2k5mod`` file contains one small JSON manifest plus only the user's
replacement assets and user-authored metadata.  It never contains private
originals, extracted archives, an XISO path, or build output.  Loading
validates the complete archive before the caller replaces its active working
session.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Iterable, Mapping
from uuid import uuid4
import zipfile

from mod_editor.core import platform_compat
from mod_editor.core.errors import ValidationError
from mod_editor.core.json_stream import read_bounded_regular_file
from mod_editor.core.nfl2k5_audio_origin_authorization import (
    AuthorizedPcm16Wav,
    require_authorized_pcm16_wav,
)
from mod_editor.core.nfl2k5_playbook_route_writer import (
    PROVIDER_KIND as PLAY_ROUTE_KIND,
    request_from_mapping as play_route_request_from_mapping,
)
from mod_editor.core.nfl2k5_formation_play_writer import (
    PROVIDER_KIND_FORMATION as FORMATION_CREATE_KIND,
    PROVIDER_KIND_LINK as FORMATION_LINK_KIND,
    PROVIDER_KIND_PLAY as PLAY_CREATE_KIND,
    formation_request_from_mapping,
    link_request_from_mapping,
    play_request_from_mapping,
)
from mod_editor.studio.audio_annotations import (
    AudioCueAnnotation,
    MAX_AUDIO_ANNOTATIONS,
    annotation_document,
    parse_audio_annotation_document,
    validate_audio_cue_annotations,
)


PROJECT_SCHEMA = "2k5_mod_studio_project/v1"
PROJECT_GAME = "espn_nfl_2k5_xbox"
PROJECT_EXTENSION = ".2k5mod"
MAX_PROJECT_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_TEXT_REPLACEMENTS_BYTES = 32 * 1024 * 1024
MAX_AUDIO_ANNOTATIONS_BYTES = 32 * 1024 * 1024
MAX_REPLACEMENT_BYTES = 64 * 1024 * 1024 + 44
MAX_PROJECT_EDITS = 25_000
MAX_PROJECT_REPLACEMENT_BYTES = 1024 * 1024 * 1024
MAX_PROJECT_EXPANDED_BYTES = (
    MAX_PROJECT_REPLACEMENT_BYTES
    + MAX_MANIFEST_BYTES
    + MAX_TEXT_REPLACEMENTS_BYTES
    + MAX_AUDIO_ANNOTATIONS_BYTES
)
MAX_PROJECT_MEMBERS = MAX_PROJECT_EDITS + 3
MAX_UNIFORM_COLOR_EDITS = 634
UNIFORM_SELECTOR_RE = re.compile(
    r"^[0-9]{2}[HA](?:[0-9]|[1-9][0-9])$", re.ASCII
)
ARGB_RE = re.compile(r"^[0-9A-F]{8}$", re.ASCII)


def _asset_key(asset_id: str) -> str:
    return hashlib.sha256(asset_id.encode("utf-8")).hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _canonical_audio_annotations_json(value: object) -> bytes:
    """Serialize validated user text without ``ensure_ascii`` size inflation."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _reject_duplicate_json_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    """Reject ambiguous duplicate keys at every untrusted JSON object depth."""

    accepted: dict[str, object] = {}
    for key, value in pairs:
        if key in accepted:
            raise ValidationError(
                f"Project JSON contains a duplicate object key: {key!r}."
            )
        accepted[key] = value
    return accepted


def _prepare_audio_annotations(
    supplied: Mapping[str, object] | Iterable[AudioCueAnnotation],
) -> tuple[tuple[AudioCueAnnotation, ...], bytes | None]:
    """Normalize either records or a recovery document at the save boundary."""

    if isinstance(supplied, Mapping):
        annotations = parse_audio_annotation_document(supplied)
    else:
        annotations = validate_audio_cue_annotations(supplied)
    if not annotations:
        return (), None
    payload = _canonical_audio_annotations_json(annotation_document(annotations))
    if len(payload) > MAX_AUDIO_ANNOTATIONS_BYTES:
        raise ValidationError(
            "Audio annotations exceed the 32 MiB project metadata limit."
        )
    return annotations, payload


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100600 << 16
    info.create_system = 3
    return info


def _destination(path: Path) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = Path(os.path.abspath(os.fspath(requested)))
    if requested.suffix.casefold() != PROJECT_EXTENSION:
        raise ValidationError(
            f"Mod Studio projects must use the {PROJECT_EXTENSION} extension."
        )
    requested.parent.mkdir(parents=True, exist_ok=True)
    if requested.parent.is_symlink():
        raise ValidationError("Choose a project folder that is not a symbolic link.")
    return requested


def _publish_archive(
    temporary: Path,
    destination: Path,
    *,
    replace: bool,
    expected_target: ProjectTargetIdentity | None = None,
) -> None:
    if expected_target is not None:
        if not replace:
            raise ValidationError(
                "Fast-save target protection requires an atomic replacement."
            )
        current = project_target_identity(destination)
        if current != expected_target:
            raise ValidationError(
                "The active project changed outside Mod Studio. It was not "
                "overwritten; use Save Project As or reopen it first."
            )
    if os.path.lexists(destination):
        current = destination.lstat()
        if not replace:
            raise ValidationError(f"A file already exists there: {destination}")
        if not stat.S_ISREG(current.st_mode) or stat.S_ISLNK(current.st_mode):
            raise ValidationError("Project destination must be a regular file, not a link.")
        os.replace(temporary, destination)
        return
    try:
        platform_compat.publish_no_replace(temporary, destination)
    except FileExistsError as exc:
        raise ValidationError(f"A file appeared at the project destination: {destination}") from exc


@dataclass(frozen=True)
class LoadedProjectEdit:
    asset: Any
    staged_path: Path
    png_sha256: str
    rgba_sha256: str


@dataclass(frozen=True)
class LoadedProjectAudioEdit:
    asset_id: str
    staged_path: Path
    wav_sha256: str
    wav_bytes: bytes = b""


@dataclass(frozen=True)
class AuthorizedProjectAudioEdit:
    """Ephemeral, non-serializable hand-off for one shareable audio member."""

    asset_id: str
    authorized_wav: AuthorizedPcm16Wav


@dataclass(frozen=True)
class LoadedProject:
    staging_root: Path
    edits: tuple[LoadedProjectEdit, ...]
    text_replacements: Mapping[str, Any] | None = None
    audio_edits: tuple[LoadedProjectAudioEdit, ...] = ()
    audio_annotations: tuple[AudioCueAnnotation, ...] = ()
    uniform_colors: tuple[Mapping[str, str], ...] = ()
    play_route_edits: tuple[Mapping[str, object], ...] = ()
    formation_creates: tuple[Mapping[str, object], ...] = ()
    play_creates: tuple[Mapping[str, object], ...] = ()
    formation_links: tuple[Mapping[str, object], ...] = ()

    def cleanup(self) -> None:
        shutil.rmtree(self.staging_root, ignore_errors=True)


@dataclass(frozen=True)
class ProjectTargetIdentity:
    """Private in-memory fingerprint for one named project file.

    This is deliberately filesystem metadata, not project content.  It lets a
    document-style fast save prove that the path still names the exact regular
    file the user opened or last saved before replacing it atomically.
    """

    path: Path
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


def project_target_identity(path: Path) -> ProjectTargetIdentity:
    """Capture a fail-closed identity for a named ``.2k5mod`` target."""

    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = Path(os.path.abspath(os.fspath(requested)))
    if requested.suffix.casefold() != PROJECT_EXTENSION:
        raise ValidationError(
            f"The active project must use the {PROJECT_EXTENSION} extension. "
            "Use Save Project As to choose another file."
        )
    try:
        before = requested.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(
            "The active project file is missing. Use Save Project As to choose "
            "a new destination."
        ) from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ValidationError(
            "The active project target is no longer a regular, non-linked file. "
            "Use Save Project As to choose a safe destination."
        )
    try:
        descriptor = os.open(
            requested,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
        )
    except FileNotFoundError as exc:
        raise ValidationError(
            "The active project file disappeared. Use Save Project As to choose "
            "a new destination."
        ) from exc
    except OSError as exc:
        raise ValidationError(
            "The active project target could not be opened safely. Use Save "
            "Project As to choose a new destination."
        ) from exc
    try:
        opened = os.fstat(descriptor)
        try:
            resolved = requested.resolve(strict=True)
            after = requested.lstat()
        except FileNotFoundError as exc:
            raise ValidationError(
                "The active project file changed while Mod Studio checked it. "
                "Use Save Project As or reopen it."
            ) from exc
        # ``opened`` is an fd stat and ``after`` a path stat of the same file, so
        # the change time is compared only where the two calls agree on it (see
        # platform_compat.supports_change_time_identity).
        opened_key = (
            opened.st_dev, opened.st_ino, opened.st_size,
            opened.st_mtime_ns, *platform_compat.change_time_identity(opened),
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or stat.S_ISLNK(after.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or after.st_nlink != 1
            or opened_key != (
                after.st_dev, after.st_ino, after.st_size,
                after.st_mtime_ns, *platform_compat.change_time_identity(after),
            )
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ValidationError(
                "The active project changed while Mod Studio checked it. Use "
                "Save Project As or reopen it."
            )
        # The recorded fingerprint keeps every field, including the raw change
        # time: both sides of the later ProjectTargetIdentity comparison come
        # from this same fd stat, so that field stays a usable signal on every
        # platform and is not dropped here.
        return ProjectTargetIdentity(
            resolved, opened.st_dev, opened.st_ino, opened.st_size,
            opened.st_mtime_ns, opened.st_ctime_ns,
        )
    finally:
        os.close(descriptor)


def save_project_archive(
    *,
    catalog: Any,
    asset_io: Any,
    edits: Iterable[Any],
    destination: Path,
    replace: bool = False,
    expected_target: ProjectTargetIdentity | None = None,
    allow_empty: bool = False,
    text_replacements: Mapping[str, Any] | None = None,
    audio_edits: Iterable[Any] = (),
    audio_annotations: Mapping[str, object] | Iterable[AudioCueAnnotation] = (),
    uniform_colors: Iterable[Mapping[str, str]] = (),
    play_route_edits: Iterable[Mapping[str, object]] = (),
    formation_creates: Iterable[Mapping[str, object]] = (),
    play_creates: Iterable[Mapping[str, object]] = (),
    formation_links: Iterable[Mapping[str, object]] = (),
) -> Path:
    """Atomically save only user-authored replacements and annotation metadata."""

    output = _destination(destination)
    if expected_target is not None:
        try:
            current_path = output.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValidationError(
                "The active project file is missing. Use Save Project As to "
                "choose a new destination."
            ) from exc
        if current_path != expected_target.path:
            raise ValidationError(
                "The fast-save target no longer matches the active project. "
                "Use Save Project As to choose a destination."
            )
    visual_edits = tuple(edits)
    supplied_audio_edits = tuple(audio_edits)
    supplied_play_route_edits = tuple(play_route_edits)
    supplied_formation_creates = tuple(formation_creates)
    supplied_play_creates = tuple(play_creates)
    supplied_formation_links = tuple(formation_links)
    if (
        len(visual_edits) + len(supplied_audio_edits)
        + len(supplied_play_route_edits)
        + len(supplied_formation_creates) + len(supplied_play_creates)
        + len(supplied_formation_links) > MAX_PROJECT_EDITS
    ):
        raise ValidationError(
            f"A project can contain at most {MAX_PROJECT_EDITS:,} combined "
            "visual and audio edits."
        )
    rows: list[tuple[dict[str, str], bytes]] = []
    seen: set[str] = set()
    for edit in visual_edits:
        asset_id = edit.asset_id
        if asset_id in seen:
            raise ValidationError(f"Duplicate project asset: {asset_id}")
        seen.add(asset_id)
        asset = catalog.get_asset(asset_id)
        payload, rgba = asset_io.validate_replacement(asset, edit.replacement_path)
        original = asset_io.ensure_original(asset)
        _original_payload, original_rgba = asset_io.validate_replacement(asset, original)
        if rgba == original_rgba:
            raise ValidationError(
                f"{asset.label} matches the retail original and was excluded. Revert it first."
            )
        png_sha256 = _sha256(payload)
        rgba_sha256 = _sha256(rgba)
        if png_sha256 != edit.replacement_sha256 or rgba_sha256 != edit.rgba_sha256:
            raise ValidationError(
                f"{asset.label} changed outside Mod Studio. Replace it again before saving."
            )
        entry = f"replacements/{_asset_key(asset_id)}.png"
        row = {
            "asset_id": asset_id,
            "file": entry,
            "png_sha256": png_sha256,
            "rgba_sha256": rgba_sha256,
        }
        if asset_id.startswith("nfl2k5.crib."):
            selector = getattr(asset, "selector", None)
            if not isinstance(selector, str) or not selector:
                raise ValidationError(f"Crib selector is missing for {asset_id}.")
            row["selector"] = selector
        rows.append((row, payload))
    text_payload: bytes | None = None
    if text_replacements is not None:
        if not isinstance(text_replacements, Mapping):
            raise ValidationError("Text replacements must be a JSON object.")
        text_payload = _canonical_json(dict(text_replacements))
        if not 0 < len(text_payload) <= MAX_TEXT_REPLACEMENTS_BYTES:
            raise ValidationError("Text replacements are empty or unexpectedly large.")
    audio_rows: list[tuple[dict[str, str], bytes]] = []
    audio_seen: set[str] = set()
    for edit in supplied_audio_edits:
        asset_id = edit.asset_id
        if not isinstance(asset_id, str) or not asset_id or asset_id in audio_seen:
            raise ValidationError("Audio project assets must have unique stable IDs.")
        audio_seen.add(asset_id)
        authorized = getattr(edit, "authorized_wav", None)
        if authorized is not None:
            try:
                issued = require_authorized_pcm16_wav(authorized)
            except ValidationError as exc:
                raise ValidationError(
                    f"Audio replacement lacks a valid in-memory origin authorization: "
                    f"{asset_id}. {exc}"
                ) from exc
            payload = issued.wav_bytes
        else:
            # Compatibility for non-product test doubles and older internal
            # callers. StudioSession's real NFL 2K5 service always supplies the
            # sealed in-memory branch above, so its save never reopens a path
            # after the origin verdict.
            try:
                _source, payload = read_bounded_regular_file(
                    Path(edit.replacement_path),
                    f"Audio replacement for {asset_id}",
                    maximum=MAX_REPLACEMENT_BYTES,
                )
            except ValidationError as exc:
                raise ValidationError(
                    f"Audio replacement is unsafe or too large: {asset_id}. {exc}"
                ) from exc
        wav_sha256 = _sha256(payload)
        expected_sha256 = getattr(edit, "replacement_sha256", wav_sha256)
        if wav_sha256 != expected_sha256:
            raise ValidationError(
                f"Audio replacement changed outside Mod Studio: {asset_id}"
            )
        entry = f"audio/{_asset_key(asset_id)}.wav"
        audio_rows.append(({
            "asset_id": asset_id,
            "file": entry,
            "wav_sha256": wav_sha256,
        }, payload))
    audio_rows.sort(key=lambda value: value[0]["asset_id"])
    annotations, annotations_payload = _prepare_audio_annotations(audio_annotations)
    uniform_rows: list[dict[str, str]] = []
    uniform_seen: set[str] = set()
    for number, supplied in enumerate(uniform_colors, 1):
        row = dict(supplied) if isinstance(supplied, Mapping) else {}
        if set(row) != {"selector", "facemask", "turtleneck"}:
            raise ValidationError(
                f"Uniform colour row {number} has unsupported fields."
            )
        selector = row.get("selector")
        facemask = row.get("facemask")
        turtleneck = row.get("turtleneck")
        if (
            not isinstance(selector, str)
            or UNIFORM_SELECTOR_RE.fullmatch(selector) is None
            or selector in uniform_seen
            or not isinstance(facemask, str)
            or ARGB_RE.fullmatch(facemask) is None
            or not isinstance(turtleneck, str)
            or ARGB_RE.fullmatch(turtleneck) is None
        ):
            raise ValidationError(
                f"Uniform colour row {number} has an invalid selector or ARGB value."
            )
        uniform_seen.add(selector)
        uniform_rows.append({
            "selector": selector,
            "facemask": facemask,
            "turtleneck": turtleneck,
        })
    if len(uniform_rows) > MAX_UNIFORM_COLOR_EDITS:
        raise ValidationError("A project cannot edit more than 634 uniform colour records.")
    uniform_rows.sort(key=lambda row: row["selector"])
    play_route_rows: list[dict[str, object]] = []
    play_route_seen: set[tuple[str, int, int]] = set()
    for number, supplied in enumerate(supplied_play_route_edits, 1):
        row = dict(supplied) if isinstance(supplied, Mapping) else {}
        if row.get("kind") != PLAY_ROUTE_KIND:
            raise ValidationError(
                f"PLAY route row {number} has an invalid provider kind."
            )
        request = play_route_request_from_mapping({
            key: value for key, value in row.items() if key != "kind"
        })
        target = (
            request.asset_id, request.target_play_index,
            request.target_slot_index,
        )
        if target in play_route_seen:
            raise ValidationError("Project repeats one PLAY assignment-route target.")
        play_route_seen.add(target)
        play_route_rows.append(request.provider_edit())
    play_route_rows.sort(key=lambda row: (
        str(row["asset_id"]), int(row["target_play_index"]),
        int(row["target_slot_index"]),
    ))
    create_rows: list[dict[str, object]] = []
    for number, supplied in enumerate(supplied_formation_creates, 1):
        request = formation_request_from_mapping(supplied)
        create_rows.append(request.provider_edit())
    for number, supplied in enumerate(supplied_play_creates, 1):
        request = play_request_from_mapping(supplied)
        create_rows.append(request.provider_edit())
    link_rows: list[dict[str, object]] = []
    for number, supplied in enumerate(supplied_formation_links, 1):
        request = link_request_from_mapping(supplied)
        link_rows.append(request.provider_edit())
    create_rows.sort(key=lambda row: (
        str(row["asset_id"]), str(row["kind"]),
        json.dumps(row, sort_keys=True),
    ))
    link_rows.sort(key=lambda row: (
        str(row["asset_id"]), int(row["formation_index"]), int(row["play_index"]),
    ))
    empty_project = (
        not rows
        and text_payload is None
        and not audio_rows
        and annotations_payload is None
        and not uniform_rows
        and not play_route_rows
        and not create_rows
        and not link_rows
    )
    if empty_project and not allow_empty:
        raise ValidationError(
            "Make at least one edit or audio annotation before saving a project."
        )
    rows.sort(key=lambda value: value[0]["asset_id"])
    manifest = {
        "edits": [row for row, _payload in rows],
        "game": PROJECT_GAME,
        "payload_policy": "user-replacements-only",
        "schema": PROJECT_SCHEMA,
    }
    if empty_project:
        # This explicit marker distinguishes an intentional, canonical empty
        # document (for Save-after-Revert and recovery) from a malformed archive
        # that merely omitted every declared payload.
        manifest["empty_project"] = True
    if text_payload is not None:
        manifest["text_replacements"] = {
            "file": "text-replacements.json",
            "sha256": _sha256(text_payload),
        }
    if audio_rows:
        manifest["audio_edits"] = [row for row, _payload in audio_rows]
    if annotations_payload is not None:
        manifest["audio_annotations"] = {
            "count": len(annotations),
            "file": "audio-annotations.json",
            "sha256": _sha256(annotations_payload),
            "size": len(annotations_payload),
        }
    if uniform_rows:
        manifest["uniform_colors"] = uniform_rows
    if play_route_rows:
        manifest["play_route_edits"] = play_route_rows
    if create_rows:
        manifest["playbook_creates"] = create_rows
    if link_rows:
        manifest["playbook_links"] = link_rows
    manifest_payload = _canonical_json(manifest)
    replacement_bytes = sum(len(payload) for _row, payload in rows) + sum(
        len(payload) for _row, payload in audio_rows
    )
    expanded_bytes = replacement_bytes + len(manifest_payload) + (
        len(text_payload) if text_payload is not None else 0
    ) + (
        len(annotations_payload) if annotations_payload is not None else 0
    )
    if replacement_bytes > MAX_PROJECT_REPLACEMENT_BYTES \
            or expanded_bytes > MAX_PROJECT_EXPANDED_BYTES:
        raise ValidationError(
            "Project replacements exceed the 1 GiB combined payload limit. "
            "Split the work into smaller shareable projects."
        )
    if shutil.disk_usage(output.parent).free < expanded_bytes:
        raise ValidationError(
            "There is not enough free space to save this project safely."
        )
    temporary = platform_compat.temporary_sibling(output)
    descriptor = os.open(
        temporary,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w+b", closefd=True) as stream:
            with zipfile.ZipFile(
                stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
            ) as archive:
                archive.writestr(_zip_info("project.json"), manifest_payload)
                if text_payload is not None:
                    archive.writestr(
                        _zip_info("text-replacements.json"), text_payload
                    )
                if annotations_payload is not None:
                    archive.writestr(
                        _zip_info("audio-annotations.json"), annotations_payload
                    )
                for row, payload in audio_rows:
                    archive.writestr(_zip_info(row["file"]), payload)
                for row, payload in rows:
                    archive.writestr(_zip_info(row["file"]), payload)
            stream.flush()
            os.fsync(stream.fileno())
        if not 0 < temporary.stat().st_size <= MAX_PROJECT_BYTES:
            raise ValidationError(
                "The saved project exceeds the 2 GiB archive limit. "
                "Split the work into smaller shareable projects."
            )
        _publish_archive(
            temporary,
            output,
            replace=replace,
            expected_target=expected_target,
        )
        return output.resolve(strict=True)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValidationError(f"Could not save the Mod Studio project: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def load_project_archive(
    *, source: Path, catalog: Any, asset_io: Any, private_root: Path,
) -> LoadedProject:
    """Validate every archive member and stage replacements in private storage."""

    requested = source.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"Project does not exist: {requested}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError("Choose a regular .2k5mod file, not a folder or link.")
    if requested.suffix.casefold() != PROJECT_EXTENSION:
        raise ValidationError(f"Choose a {PROJECT_EXTENSION} Mod Studio project.")
    if not 0 < supplied.st_size <= MAX_PROJECT_BYTES:
        raise ValidationError("That project is empty or exceeds the 2 GiB project limit.")
    source_path = requested.resolve(strict=True)
    stage = private_root / f"project-import-{uuid4().hex}"
    stage.mkdir(parents=True, mode=0o700)
    loaded: list[LoadedProjectEdit] = []
    try:
        with zipfile.ZipFile(source_path, "r") as archive:
            infos = archive.infolist()
            if not 1 <= len(infos) <= MAX_PROJECT_MEMBERS:
                raise ValidationError(
                    f"Project archive member count exceeds the {MAX_PROJECT_MEMBERS:,} "
                    "file limit."
                )
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ValidationError("Project contains duplicate archive members.")
            if any(
                info.is_dir()
                or info.flag_bits & 1
                or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                for info in infos
            ):
                raise ValidationError("Project contains an unsupported or encrypted member.")
            expanded_bytes = sum(info.file_size for info in infos)
            if expanded_bytes > MAX_PROJECT_EXPANDED_BYTES:
                raise ValidationError(
                    "Project expands beyond the safe 1 GiB replacement limit. "
                    "Ask the author to split it into smaller projects."
                )
            if shutil.disk_usage(stage.parent).free < expanded_bytes:
                raise ValidationError(
                    "There is not enough free space to open this project safely."
                )
            by_name = {info.filename: info for info in infos}
            manifest_info = by_name.get("project.json")
            if manifest_info is None or manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise ValidationError("Project manifest is missing or too large.")
            try:
                document = json.loads(
                    archive.read(manifest_info).decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_pairs,
                )
            except (UnicodeError, json.JSONDecodeError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ValidationError(f"Project manifest is not valid JSON: {exc}") from exc
            base_fields = {"edits", "game", "payload_policy", "schema"}
            optional_fields = {
                "text_replacements", "audio_edits", "audio_annotations",
                "uniform_colors", "empty_project",
                "play_route_edits", "playbook_creates", "playbook_links",
            }
            if not isinstance(document, dict) or not (
                base_fields <= set(document) <= base_fields | optional_fields
            ):
                raise ValidationError("Project manifest has unsupported fields.")
            if (
                document.get("schema") != PROJECT_SCHEMA
                or document.get("game") != PROJECT_GAME
                or document.get("payload_policy") != "user-replacements-only"
            ):
                raise ValidationError("Project was not created for NFL 2K5 Mod Studio.")
            empty_marker_present = "empty_project" in document
            empty_marker = document.get("empty_project")
            if empty_marker_present and empty_marker is not True:
                raise ValidationError("Project empty-document marker is malformed.")
            rows = document.get("edits")
            if not isinstance(rows, list) or not 0 <= len(rows) <= MAX_PROJECT_EDITS:
                raise ValidationError("Project edit count is outside the supported range.")
            expected_members = {"project.json"}
            loaded_audio: list[LoadedProjectAudioEdit] = []
            text_document: Mapping[str, Any] | None = None
            loaded_annotations: tuple[AudioCueAnnotation, ...] = ()
            loaded_uniform_colors: list[Mapping[str, str]] = []
            loaded_play_routes: list[Mapping[str, object]] = []
            text_meta = document.get("text_replacements")
            if text_meta is not None:
                if not isinstance(text_meta, dict) or set(text_meta) != {
                    "file", "sha256",
                } or text_meta.get("file") != "text-replacements.json":
                    raise ValidationError("Project text metadata is malformed.")
                text_info = by_name.get("text-replacements.json")
                if text_info is None or not 0 < text_info.file_size \
                        <= MAX_TEXT_REPLACEMENTS_BYTES:
                    raise ValidationError("Project text replacements are missing or too large.")
                try:
                    text_payload = archive.read(text_info)
                    parsed_text = json.loads(
                        text_payload.decode("utf-8"),
                        object_pairs_hook=_reject_duplicate_json_pairs,
                    )
                except (UnicodeError, json.JSONDecodeError, RuntimeError,
                        zipfile.BadZipFile) as exc:
                    raise ValidationError(
                        f"Project text replacements are not valid JSON: {exc}"
                    ) from exc
                if _sha256(text_payload) != text_meta.get("sha256"):
                    raise ValidationError("Project text replacement checksum failed.")
                if not isinstance(parsed_text, dict):
                    raise ValidationError("Project text replacements must be an object.")
                text_document = parsed_text
                expected_members.add("text-replacements.json")
            annotation_meta = document.get("audio_annotations")
            if annotation_meta is not None:
                annotation_fields = {"count", "file", "sha256", "size"}
                if (
                    not isinstance(annotation_meta, dict)
                    or set(annotation_meta) != annotation_fields
                    or annotation_meta.get("file") != "audio-annotations.json"
                ):
                    raise ValidationError("Project audio annotation metadata is malformed.")
                annotation_count = annotation_meta.get("count")
                annotation_size = annotation_meta.get("size")
                if (
                    type(annotation_count) is not int
                    or not 1 <= annotation_count <= MAX_AUDIO_ANNOTATIONS
                    or type(annotation_size) is not int
                    or not 0 < annotation_size <= MAX_AUDIO_ANNOTATIONS_BYTES
                ):
                    raise ValidationError(
                        "Project audio annotation count or size is outside the limit."
                    )
                annotation_info = by_name.get("audio-annotations.json")
                if (
                    annotation_info is None
                    or annotation_info.file_size != annotation_size
                ):
                    raise ValidationError(
                        "Project audio annotations are missing or have the wrong size."
                    )
                try:
                    annotation_payload = archive.read(annotation_info)
                except (RuntimeError, zipfile.BadZipFile) as exc:
                    raise ValidationError(
                        f"Could not read project audio annotations: {exc}"
                    ) from exc
                if _sha256(annotation_payload) != annotation_meta.get("sha256"):
                    raise ValidationError(
                        "Project audio annotation checksum failed."
                    )
                try:
                    annotation_document_value = json.loads(
                        annotation_payload.decode("utf-8"),
                        object_pairs_hook=_reject_duplicate_json_pairs,
                    )
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise ValidationError(
                        f"Project audio annotations are not valid JSON: {exc}"
                    ) from exc
                loaded_annotations = parse_audio_annotation_document(
                    annotation_document_value
                )
                if len(loaded_annotations) != annotation_count:
                    raise ValidationError(
                        "Project audio annotation count does not match its metadata."
                    )
                expected_members.add("audio-annotations.json")
            audio_rows = document.get("audio_edits", [])
            if not isinstance(audio_rows, list) or len(audio_rows) > MAX_PROJECT_EDITS:
                raise ValidationError("Project audio edit count is outside the limit.")
            if len(rows) + len(audio_rows) > MAX_PROJECT_EDITS:
                raise ValidationError(
                    f"Project exceeds the {MAX_PROJECT_EDITS:,} combined visual "
                    "and audio edit limit."
                )
            uniform_rows = document.get("uniform_colors", [])
            if not isinstance(uniform_rows, list) or len(uniform_rows) \
                    > MAX_UNIFORM_COLOR_EDITS:
                raise ValidationError("Project uniform colour edit count is outside the limit.")
            uniform_seen: set[str] = set()
            for number, row in enumerate(uniform_rows, 1):
                if not isinstance(row, dict) or set(row) != {
                    "selector", "facemask", "turtleneck",
                }:
                    raise ValidationError(
                        f"Project uniform colour row {number} has unsupported fields."
                    )
                selector = row.get("selector")
                facemask = row.get("facemask")
                turtleneck = row.get("turtleneck")
                if (
                    not isinstance(selector, str)
                    or UNIFORM_SELECTOR_RE.fullmatch(selector) is None
                    or selector in uniform_seen
                    or not isinstance(facemask, str)
                    or ARGB_RE.fullmatch(facemask) is None
                    or not isinstance(turtleneck, str)
                    or ARGB_RE.fullmatch(turtleneck) is None
                ):
                    raise ValidationError(
                        f"Project uniform colour row {number} has an invalid selector or ARGB value."
                    )
                uniform_seen.add(selector)
                loaded_uniform_colors.append({
                    "selector": selector,
                    "facemask": facemask,
                    "turtleneck": turtleneck,
                })
            play_route_rows = document.get("play_route_edits", [])
            if not isinstance(play_route_rows, list) or len(play_route_rows) \
                    > MAX_PROJECT_EDITS:
                raise ValidationError("Project PLAY route edit count is outside the limit.")
            play_route_seen: set[tuple[str, int, int]] = set()
            for number, raw_route in enumerate(play_route_rows, 1):
                if not isinstance(raw_route, dict) or raw_route.get("kind") \
                        != PLAY_ROUTE_KIND:
                    raise ValidationError(
                        f"Project PLAY route row {number} has unsupported fields."
                    )
                request = play_route_request_from_mapping({
                    key: value for key, value in raw_route.items() if key != "kind"
                })
                target_key = (
                    request.asset_id, request.target_play_index,
                    request.target_slot_index,
                )
                if target_key in play_route_seen:
                    raise ValidationError(
                        "Project repeats one PLAY assignment-route target."
                    )
                play_route_seen.add(target_key)
                loaded_play_routes.append(request.provider_edit())
            create_rows = document.get("playbook_creates", [])
            if not isinstance(create_rows, list) or len(create_rows) \
                    > MAX_PROJECT_EDITS:
                raise ValidationError(
                    "Project playbook create count is outside the limit."
                )
            loaded_creates: list[Mapping[str, object]] = []
            create_seen: set[tuple[str, str, int, str]] = set()
            for number, raw_create in enumerate(create_rows, 1):
                if not isinstance(raw_create, dict) or raw_create.get("kind") \
                    not in (FORMATION_CREATE_KIND, PLAY_CREATE_KIND):
                    raise ValidationError(
                        f"Project playbook create row {number} has an invalid kind."
                    )
                mapper = (
                    formation_request_from_mapping
                    if raw_create["kind"] == FORMATION_CREATE_KIND
                    else play_request_from_mapping
                )
                request = mapper({
                    key: value for key, value in raw_create.items() if key != "kind"
                })
                donor = (
                    request.donor_formation_index
                    if raw_create["kind"] == FORMATION_CREATE_KIND
                    else request.donor_play_index
                )
                key = (
                    request.asset_id, str(raw_create["kind"]), donor,
                    json.dumps(request.provider_edit(), sort_keys=True, default=list),
                )
                if key in create_seen:
                    raise ValidationError("Project repeats one playbook create.")
                create_seen.add(key)
                loaded_creates.append(request.provider_edit())
            link_rows = document.get("playbook_links", [])
            if not isinstance(link_rows, list) or len(link_rows) \
                    > MAX_PROJECT_EDITS:
                raise ValidationError(
                    "Project playbook link count is outside the limit."
                )
            loaded_links: list[Mapping[str, object]] = []
            link_seen: set[tuple[str, int, int]] = set()
            for number, raw_link in enumerate(link_rows, 1):
                if not isinstance(raw_link, dict) or raw_link.get("kind") \
                        != FORMATION_LINK_KIND:
                    raise ValidationError(
                        f"Project playbook link row {number} has an invalid kind."
                    )
                request = link_request_from_mapping({
                    key: value for key, value in raw_link.items() if key != "kind"
                })
                key = (request.asset_id, request.formation_index, request.play_index)
                if key in link_seen:
                    raise ValidationError("Project repeats one playbook link.")
                link_seen.add(key)
                loaded_links.append(request.provider_edit())
            if (
                len(rows) + len(audio_rows) + len(play_route_rows)
                + len(loaded_creates) + len(loaded_links) > MAX_PROJECT_EDITS
            ):
                raise ValidationError(
                    f"Project exceeds the {MAX_PROJECT_EDITS:,} combined edit limit."
                )
            seen_audio: set[str] = set()
            for row in audio_rows:
                if not isinstance(row, dict) or set(row) != {
                    "asset_id", "file", "wav_sha256",
                }:
                    raise ValidationError("Project audio metadata has unsupported fields.")
                asset_id = row.get("asset_id")
                if not isinstance(asset_id, str) or not asset_id or asset_id in seen_audio:
                    raise ValidationError("Project contains duplicate audio assets.")
                seen_audio.add(asset_id)
                entry = f"audio/{_asset_key(asset_id)}.wav"
                if row.get("file") != entry:
                    raise ValidationError(f"Project audio path is not canonical for {asset_id}.")
                info = by_name.get(entry)
                if info is None or not 0 < info.file_size <= MAX_REPLACEMENT_BYTES:
                    raise ValidationError(f"Audio replacement is missing or too large: {asset_id}")
                try:
                    payload = archive.read(info)
                except (RuntimeError, zipfile.BadZipFile) as exc:
                    raise ValidationError(
                        f"Could not read audio replacement for {asset_id}: {exc}"
                    ) from exc
                if _sha256(payload) != row.get("wav_sha256"):
                    raise ValidationError(f"Audio replacement checksum failed: {asset_id}")
                staged = stage / f"{_asset_key(asset_id)}.wav"
                descriptor = os.open(
                    staged,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                    getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                with os.fdopen(descriptor, "wb", closefd=True) as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                loaded_audio.append(LoadedProjectAudioEdit(
                    asset_id, staged, row["wav_sha256"], payload
                ))
                expected_members.add(entry)
            if (
                not rows
                and text_document is None
                and not loaded_audio
                and not loaded_annotations
                and not loaded_uniform_colors
                and not loaded_play_routes
            ):
                if empty_marker is not True:
                    raise ValidationError(
                        "Project does not contain any edits or audio annotations."
                    )
            elif empty_marker_present:
                raise ValidationError(
                    "Project empty-document marker conflicts with authored content."
                )
            seen_assets: set[str] = set()
            for row in rows:
                base_edit_fields = {
                    "asset_id", "file", "png_sha256", "rgba_sha256",
                }
                if not isinstance(row, dict) or set(row) not in {
                    frozenset(base_edit_fields),
                    frozenset(base_edit_fields | {"selector"}),
                }:
                    raise ValidationError("Project edit metadata has unsupported fields.")
                asset_id = row.get("asset_id")
                if not isinstance(asset_id, str) or not asset_id or asset_id in seen_assets:
                    raise ValidationError("Project contains an empty or duplicate asset ID.")
                seen_assets.add(asset_id)
                expected_entry = f"replacements/{_asset_key(asset_id)}.png"
                if row.get("file") != expected_entry:
                    raise ValidationError(f"Project path is not canonical for {asset_id}.")
                info = by_name.get(expected_entry)
                if info is None or not 0 < info.file_size <= MAX_REPLACEMENT_BYTES:
                    raise ValidationError(f"Replacement is missing or too large for {asset_id}.")
                expected_members.add(expected_entry)
                try:
                    payload = archive.read(info)
                except (RuntimeError, zipfile.BadZipFile) as exc:
                    raise ValidationError(f"Could not read replacement for {asset_id}: {exc}") from exc
                if _sha256(payload) != row.get("png_sha256"):
                    raise ValidationError(f"Replacement checksum failed for {asset_id}.")
                asset = catalog.get_asset(asset_id)
                selector = row.get("selector")
                if asset_id.startswith("nfl2k5.crib."):
                    # v1 projects saved before the scene writer did not carry
                    # this redundant logical selector. New saves always do;
                    # keep the old Team Photo archives loadable.
                    if selector is not None and selector != getattr(
                        asset, "selector", None
                    ):
                        raise ValidationError(
                            f"Crib selector does not match the asset: {asset_id}."
                        )
                elif selector is not None:
                    raise ValidationError(
                        f"Only Crib replacements may carry a selector: {asset_id}."
                    )
                staged = stage / f"{_asset_key(asset_id)}.png"
                descriptor = os.open(
                    staged,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
                    0o600,
                )
                with os.fdopen(descriptor, "wb", closefd=True) as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                checked_payload, rgba = asset_io.validate_replacement(asset, staged)
                if checked_payload != payload or _sha256(rgba) != row.get("rgba_sha256"):
                    raise ValidationError(f"Replacement pixels failed validation for {asset_id}.")
                original = asset_io.ensure_original(asset)
                _original_payload, original_rgba = asset_io.validate_replacement(asset, original)
                if rgba == original_rgba:
                    raise ValidationError(
                        f"{asset.label} matches the retail original; the project is not replacement-only."
                    )
                loaded.append(LoadedProjectEdit(
                    asset, staged, row["png_sha256"], row["rgba_sha256"],
                ))
            if set(by_name) != expected_members:
                raise ValidationError("Project contains undeclared files.")
    except (OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(stage, ignore_errors=True)
        raise ValidationError(f"Could not open the Mod Studio project: {exc}") from exc
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return LoadedProject(
        stage,
        tuple(loaded),
        text_document,
        tuple(loaded_audio),
        loaded_annotations,
        tuple(loaded_uniform_colors),
        tuple(loaded_play_routes),
        formation_creates=tuple(
            row for row in loaded_creates if row["kind"] == FORMATION_CREATE_KIND
        ),
        play_creates=tuple(
            row for row in loaded_creates if row["kind"] == PLAY_CREATE_KIND
        ),
        formation_links=tuple(loaded_links),
    )


__all__ = [
    "AuthorizedProjectAudioEdit",
    "LoadedProject",
    "LoadedProjectEdit",
    "LoadedProjectAudioEdit",
    "MAX_AUDIO_ANNOTATIONS_BYTES",
    "MAX_PROJECT_EDITS",
    "MAX_PROJECT_EXPANDED_BYTES",
    "MAX_PROJECT_MEMBERS",
    "MAX_PROJECT_REPLACEMENT_BYTES",
    "MAX_UNIFORM_COLOR_EDITS",
    "PROJECT_EXTENSION",
    "PROJECT_GAME",
    "PROJECT_SCHEMA",
    "ProjectTargetIdentity",
    "load_project_archive",
    "project_target_identity",
    "save_project_archive",
]

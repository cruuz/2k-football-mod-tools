"""Retail-free labels and notes for stable NFL 2K5 audio cue IDs.

Annotations are project metadata.  They describe logical catalog rows but do
not contain, replace, or otherwise authorize any game audio bytes.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import unicodedata

from mod_editor.core.errors import ValidationError


AUDIO_ANNOTATIONS_SCHEMA = "2k5_mod_studio_audio_annotations/v1"
MAX_AUDIO_ANNOTATIONS = 54_421
MAX_CUE_ID_CHARS = 512
MAX_TITLE_CHARS = 120
MAX_NOTE_CHARS = 2_000
MAX_TOTAL_UTF8_BYTES = 16 * 1024 * 1024


def _text(
    value: object,
    label: str,
    *,
    maximum_chars: int,
    trim: bool,
    allow_lf: bool = False,
) -> str:
    if type(value) is not str:
        raise ValidationError(f"Audio annotation {label} must be text.")
    if allow_lf:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = value.strip() if trim else value
    if not trim and value != value.strip():
        raise ValidationError(
            f"Audio annotation {label} cannot start or end with whitespace."
        )
    if len(normalized) > maximum_chars:
        raise ValidationError(
            f"Audio annotation {label} is too long "
            f"({len(normalized):,}/{maximum_chars:,} characters)."
        )
    if any(
        (
            unicodedata.category(character) in {"Cc", "Cf", "Cs"}
            and not (allow_lf and character == "\n")
        )
        for character in normalized
    ):
        raise ValidationError(
            f"Audio annotation {label} contains a control or bidirectional "
            "formatting character."
        )
    return normalized


@dataclass(frozen=True, slots=True)
class AudioCueAnnotation:
    """One immutable user-authored annotation keyed by a logical cue ID."""

    cue_id: str
    title: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        cue_id = validate_audio_cue_id(self.cue_id)
        title = _text(
            self.title,
            "title",
            maximum_chars=MAX_TITLE_CHARS,
            trim=True,
        )
        note = _text(
            self.note,
            "note",
            maximum_chars=MAX_NOTE_CHARS,
            trim=True,
            allow_lf=True,
        )
        if not title and not note:
            raise ValidationError(
                "Enter a custom audio title or note before saving the annotation."
            )
        object.__setattr__(self, "cue_id", cue_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "note", note)


def validate_audio_cue_id(value: object) -> str:
    """Validate one stable logical cue identifier without catalog access."""

    cue_id = _text(
        value,
        "cue ID",
        maximum_chars=MAX_CUE_ID_CHARS,
        trim=False,
    )
    if not cue_id:
        raise ValidationError("Audio annotation cue ID cannot be empty.")
    return cue_id


def validate_audio_cue_annotation(
    cue_id: object,
    title: object = "",
    note: object = "",
) -> AudioCueAnnotation:
    """Validate and normalize one annotation from an untrusted boundary."""

    return AudioCueAnnotation(cue_id, title, note)  # type: ignore[arg-type]


def validate_audio_cue_annotations(
    annotations: Iterable[AudioCueAnnotation],
) -> tuple[AudioCueAnnotation, ...]:
    """Validate a bounded collection and return deterministic cue-ID order."""

    accepted: dict[str, AudioCueAnnotation] = {}
    total_utf8_bytes = 0
    try:
        iterator = iter(annotations)
    except TypeError as exc:
        raise ValidationError("Audio annotations must be a collection.") from exc

    for index, candidate in enumerate(iterator, start=1):
        if index > MAX_AUDIO_ANNOTATIONS:
            raise ValidationError(
                f"A project can contain at most {MAX_AUDIO_ANNOTATIONS:,} "
                "audio annotations."
            )
        if not isinstance(candidate, AudioCueAnnotation):
            raise ValidationError(
                f"Audio annotation row {index:,} has an invalid record type."
            )
        # Reconstructing applies the same validation even if a caller supplied
        # a forged/subclassed instance around the frozen record boundary.
        annotation = AudioCueAnnotation(
            candidate.cue_id, candidate.title, candidate.note
        )
        if annotation.cue_id in accepted:
            raise ValidationError(
                f"Audio cue {annotation.cue_id} is annotated more than once."
            )
        total_utf8_bytes += sum(
            len(value.encode("utf-8"))
            for value in (annotation.cue_id, annotation.title, annotation.note)
        )
        if total_utf8_bytes > MAX_TOTAL_UTF8_BYTES:
            raise ValidationError(
                "Audio annotation text exceeds the 16 MiB project limit."
            )
        accepted[annotation.cue_id] = annotation
    return tuple(accepted[cue_id] for cue_id in sorted(accepted))


def annotation_document(
    annotations: Iterable[AudioCueAnnotation],
) -> dict[str, object]:
    """Return the canonical retail-free project document for annotations."""

    checked = validate_audio_cue_annotations(annotations)
    return {
        "annotations": [
            {
                "cue_id": annotation.cue_id,
                "note": annotation.note,
                "title": annotation.title,
            }
            for annotation in checked
        ],
        "schema": AUDIO_ANNOTATIONS_SCHEMA,
    }


def parse_audio_annotation_document(
    document: object,
) -> tuple[AudioCueAnnotation, ...]:
    """Strictly parse an untrusted annotation JSON document."""

    if not isinstance(document, Mapping) or set(document) != {"annotations", "schema"}:
        raise ValidationError("Audio annotation document fields are invalid.")
    if document.get("schema") != AUDIO_ANNOTATIONS_SCHEMA:
        raise ValidationError("Audio annotation document schema is unsupported.")
    rows = document.get("annotations")
    if type(rows) is not list:
        raise ValidationError("Audio annotation rows must be a list.")
    if len(rows) > MAX_AUDIO_ANNOTATIONS:
        raise ValidationError(
            f"A project can contain at most {MAX_AUDIO_ANNOTATIONS:,} "
            "audio annotations."
        )
    parsed: list[AudioCueAnnotation] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping) or set(row) != {"cue_id", "note", "title"}:
            raise ValidationError(
                f"Audio annotation row {index:,} fields are invalid."
            )
        try:
            parsed.append(validate_audio_cue_annotation(
                row["cue_id"], row["title"], row["note"]
            ))
        except ValidationError as exc:
            raise ValidationError(
                f"Audio annotation row {index:,} is invalid: {exc}"
            ) from exc
    return validate_audio_cue_annotations(parsed)


__all__ = [
    "AUDIO_ANNOTATIONS_SCHEMA",
    "AudioCueAnnotation",
    "MAX_AUDIO_ANNOTATIONS",
    "MAX_CUE_ID_CHARS",
    "MAX_NOTE_CHARS",
    "MAX_TITLE_CHARS",
    "MAX_TOTAL_UTF8_BYTES",
    "annotation_document",
    "parse_audio_annotation_document",
    "validate_audio_cue_annotation",
    "validate_audio_cue_annotations",
    "validate_audio_cue_id",
]

"""Retail-free labels and notes for stable APF 2K8 audio cue IDs.

Annotations are user-authored project metadata.  They describe logical AUDO
or AUSB cue rows but never contain, replace, or authorize any game audio.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
import unicodedata


AUDIO_ANNOTATIONS_SCHEMA = "apf2k8_audio_annotations/v1"
MAX_AUDIO_ANNOTATIONS = 47_775
MAX_CUE_ID_CHARS = 128
MAX_TITLE_CHARS = 120
MAX_NOTE_CHARS = 2_000
MAX_TOTAL_UTF8_BYTES = 16 * 1024 * 1024

_PLAYABLE_CUE_ID = re.compile(
    r"(?:apf:audio:audo:[0-9]+:[0-9]+|"
    r"apf:audio:ausb:[0-9]+:[0-9]+:[0-9]+)\Z"
)


class AudioAnnotationError(ValueError):
    """Untrusted cue annotation metadata violates the bounded contract."""


def _text(
    value: object,
    label: str,
    *,
    maximum_chars: int,
    trim: bool,
    allow_lf: bool = False,
) -> str:
    if type(value) is not str:
        raise AudioAnnotationError(f"Audio annotation {label} must be text")
    if allow_lf:
        value = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = value.strip() if trim else value
    if not trim and value != value.strip():
        raise AudioAnnotationError(
            f"Audio annotation {label} cannot start or end with whitespace"
        )
    if len(normalized) > maximum_chars:
        raise AudioAnnotationError(
            f"Audio annotation {label} is too long "
            f"({len(normalized):,}/{maximum_chars:,} characters)"
        )
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        and not (allow_lf and character == "\n")
        for character in normalized
    ):
        raise AudioAnnotationError(
            f"Audio annotation {label} contains a control or formatting character"
        )
    return normalized


def validate_audio_cue_id(value: object) -> str:
    """Validate one APF playable semantic cue ID without reading retail data."""

    cue_id = _text(
        value,
        "cue ID",
        maximum_chars=MAX_CUE_ID_CHARS,
        trim=False,
    )
    if not _PLAYABLE_CUE_ID.fullmatch(cue_id):
        raise AudioAnnotationError(
            "Audio annotations require one standalone AUDO or individual "
            "AUSB-substream cue ID"
        )
    return cue_id


@dataclass(frozen=True, slots=True)
class AudioCueAnnotation:
    """One immutable user-authored annotation keyed by a semantic cue ID."""

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
            raise AudioAnnotationError(
                "Enter a custom audio title or note before saving the annotation"
            )
        object.__setattr__(self, "cue_id", cue_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "note", note)


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
        raise AudioAnnotationError("Audio annotations must be a collection") from exc
    for index, candidate in enumerate(iterator, start=1):
        if index > MAX_AUDIO_ANNOTATIONS:
            raise AudioAnnotationError(
                f"A project can contain at most {MAX_AUDIO_ANNOTATIONS:,} "
                "audio annotations"
            )
        if not isinstance(candidate, AudioCueAnnotation):
            raise AudioAnnotationError(
                f"Audio annotation row {index:,} has an invalid record type"
            )
        annotation = AudioCueAnnotation(
            candidate.cue_id, candidate.title, candidate.note
        )
        if annotation.cue_id in accepted:
            raise AudioAnnotationError(
                f"Audio cue {annotation.cue_id} is annotated more than once"
            )
        total_utf8_bytes += sum(
            len(value.encode("utf-8"))
            for value in (annotation.cue_id, annotation.title, annotation.note)
        )
        if total_utf8_bytes > MAX_TOTAL_UTF8_BYTES:
            raise AudioAnnotationError(
                "Audio annotation text exceeds the 16 MiB project limit"
            )
        accepted[annotation.cue_id] = annotation
    return tuple(accepted[cue_id] for cue_id in sorted(accepted))


def annotation_document(
    annotations: Iterable[AudioCueAnnotation],
) -> dict[str, object]:
    """Return the canonical retail-free document for user cue metadata."""

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

    if not isinstance(document, Mapping) or set(document) != {
        "annotations", "schema",
    }:
        raise AudioAnnotationError("Audio annotation document fields are invalid")
    if document.get("schema") != AUDIO_ANNOTATIONS_SCHEMA:
        raise AudioAnnotationError("Audio annotation document schema is unsupported")
    rows = document.get("annotations")
    if type(rows) is not list:
        raise AudioAnnotationError("Audio annotation rows must be a list")
    if len(rows) > MAX_AUDIO_ANNOTATIONS:
        raise AudioAnnotationError(
            f"A project can contain at most {MAX_AUDIO_ANNOTATIONS:,} "
            "audio annotations"
        )
    parsed: list[AudioCueAnnotation] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping) or set(row) != {
            "cue_id", "note", "title",
        }:
            raise AudioAnnotationError(
                f"Audio annotation row {index:,} fields are invalid"
            )
        try:
            parsed.append(
                validate_audio_cue_annotation(
                    row["cue_id"], row["title"], row["note"]
                )
            )
        except AudioAnnotationError as exc:
            raise AudioAnnotationError(
                f"Audio annotation row {index:,} is invalid: {exc}"
            ) from exc
    return validate_audio_cue_annotations(parsed)


__all__ = [
    "AUDIO_ANNOTATIONS_SCHEMA",
    "AudioAnnotationError",
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

"""Family-reviewed label promotions for the 850 standalone AUDO cues.

The pinned import-capacity audit partitions the standalone cues into
equal-decoded-content and equal-resource-span groups, and the deterministic
labeling pass in ``tools/nfl2k5_audo_family_labels.py`` promotes a
provisional cue to ``family-reviewed`` confidence only when its group carries
a representative whose label is already reviewed (one of the 152 reviewed
labels or the proved Menu Back writer route).  This module is the editor's
read side for that pass.

The shipped promotion report is pinned by schema, size, and SHA-256, and it
embeds the SHA-256 of the exact audit it was computed from.  Loading is
fail-closed: a missing report, a stale hash, a schema mismatch, or any
malformed row returns an empty promotion map, so every label stays
provisional.  Reviewed labels and the Menu Back proof are never relabeled:
applying the map is the catalog's job, and it skips every reviewed row.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .errors import ValidationError
from .json_stream import read_bounded_regular_file, require_regular_file


ROOT = Path(__file__).resolve().parents[2]

FAMILY_LABEL_REPORT = ROOT / "reports/assets/nfl2k5_audo_family_labels.json"
FAMILY_LABEL_REPORT_SCHEMA = "nfl2k5_audo_family_labels/v2"
FAMILY_LABEL_REPORT_SHA256 = (
    "ea66da8ea539114563de5694599a6046bde78661556846a34f8addeb31d544dd"
)
MAX_FAMILY_LABEL_REPORT_BYTES = 1024 * 1024
# The promotion report binds to the pinned audit; reuse the audit's own
# product size limit when re-reading it for that binding.
MAX_BOUND_AUDIT_BYTES = 16 * 1024 * 1024

FAMILY_LABEL_PREFIX = "family: "
FAMILY_REVIEWED_CONFIDENCE = "family-reviewed"
FAMILY_LABEL_GROUP_KINDS = ("equal_decoded_content", "equal_resource_span")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_RE = re.compile(r"^outer_(\d{4})_chunk_(\d{4})$")
_MAX_LABEL_BYTES = 200
_MAX_NAME_BYTES = 96
_MAX_GROUP_ID_BYTES = 96


class Nfl2k5AudoFamilyLabelError(ValidationError):
    """The family-label promotion report failed closed."""


@dataclass(frozen=True, slots=True)
class AudoFamilyLabelPromotion:
    """One provisional cue's disclosed family inference and its provenance."""

    key: str
    label: str
    group_id: str
    group_kind: str
    representative_key: str
    representative_name: str
    confidence: str
    evidence_sha256: str
    member_count: int

    @property
    def selector(self) -> tuple[int, int]:
        matched = _KEY_RE.fullmatch(self.key)
        assert matched is not None
        return int(matched.group(1)), int(matched.group(2))


def _text(value: object, field: str, *, maximum: int) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise Nfl2k5AudoFamilyLabelError(
            f"Family-label promotion has an invalid {field}"
        )
    return value


def _normalize_promotion(raw: object) -> AudoFamilyLabelPromotion:
    if not isinstance(raw, dict):
        raise Nfl2k5AudoFamilyLabelError("Family-label promotion row is not a record")
    key = _text(raw.get("key"), "key", maximum=32)
    if _KEY_RE.fullmatch(key) is None:
        raise Nfl2k5AudoFamilyLabelError(
            f"Family-label promotion has an invalid cue key: {key}"
        )
    label = _text(raw.get("label"), "label", maximum=_MAX_LABEL_BYTES)
    if not label.startswith(FAMILY_LABEL_PREFIX) or label == FAMILY_LABEL_PREFIX:
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion must disclose the family inference prefix"
        )
    group_kind = _text(raw.get("group_kind"), "group kind", maximum=32)
    if group_kind not in FAMILY_LABEL_GROUP_KINDS:
        raise Nfl2k5AudoFamilyLabelError(
            f"Family-label promotion has an unknown group kind: {group_kind}"
        )
    confidence = _text(raw.get("confidence"), "confidence", maximum=32)
    if confidence != FAMILY_REVIEWED_CONFIDENCE:
        raise Nfl2k5AudoFamilyLabelError(
            f"Family-label promotion has an unknown confidence: {confidence}"
        )
    evidence = _text(raw.get("evidence_sha256"), "evidence hash", maximum=64)
    if _SHA256_RE.fullmatch(evidence) is None:
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion has an invalid evidence hash"
        )
    member_count = raw.get("member_count")
    if type(member_count) is not int or member_count < 2:
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion has an invalid member count"
        )
    representative_key = _text(
        raw.get("representative_key"), "representative key", maximum=32
    )
    if (
        _KEY_RE.fullmatch(representative_key) is None
        or representative_key == key
    ):
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion has an invalid representative cue"
        )
    return AudoFamilyLabelPromotion(
        key=key,
        label=label,
        group_id=_text(raw.get("group_id"), "group id", maximum=_MAX_GROUP_ID_BYTES),
        group_kind=group_kind,
        representative_key=representative_key,
        representative_name=_text(
            raw.get("representative_name"),
            "representative name",
            maximum=_MAX_NAME_BYTES,
        ),
        confidence=confidence,
        evidence_sha256=evidence,
        member_count=member_count,
    )


def load_family_label_promotions(
    capacity_report: Path,
    *,
    report: Path = FAMILY_LABEL_REPORT,
    expected_sha256: str | None = FAMILY_LABEL_REPORT_SHA256,
) -> dict[str, AudoFamilyLabelPromotion]:
    """Return the per-cue family-label promotions, fail-closed.

    Any missing, stale, or malformed input leaves every label provisional by
    returning an empty map; this function never raises.
    """

    try:
        return _load_family_label_promotions(
            capacity_report, report=report, expected_sha256=expected_sha256
        )
    except (
        AssertionError,
        KeyError,
        Nfl2k5AudoFamilyLabelError,
        OSError,
        TypeError,
        ValidationError,
        ValueError,
    ):
        return {}


def _load_family_label_promotions(
    capacity_report: Path,
    *,
    report: Path,
    expected_sha256: str | None,
) -> dict[str, AudoFamilyLabelPromotion]:
    report_info = require_regular_file(report, "family-label promotion metadata")
    if not 0 < report_info.st_size <= MAX_FAMILY_LABEL_REPORT_BYTES:
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion metadata is outside the product size limit"
        )
    payload = read_bounded_regular_file(
        report,
        "family-label promotion metadata",
        maximum=MAX_FAMILY_LABEL_REPORT_BYTES,
        error_type=Nfl2k5AudoFamilyLabelError,
    )[1]
    if expected_sha256 is not None:
        if (
            _SHA256_RE.fullmatch(expected_sha256) is None
            or hashlib.sha256(payload).hexdigest() != expected_sha256
        ):
            raise Nfl2k5AudoFamilyLabelError(
                "Family-label promotion metadata changed from the shipped "
                "product version"
            )
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion metadata is not a record"
        )
    if document.get("schema") != FAMILY_LABEL_REPORT_SCHEMA:
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion metadata schema is unsupported"
        )
    source_audit_sha256 = document.get("source_audit_sha256")
    if (
        not isinstance(source_audit_sha256, str)
        or _SHA256_RE.fullmatch(source_audit_sha256) is None
    ):
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion metadata is missing its source audit hash"
        )
    audit_payload = read_bounded_regular_file(
        capacity_report,
        "audio ownership metadata",
        maximum=MAX_BOUND_AUDIT_BYTES,
        error_type=Nfl2k5AudoFamilyLabelError,
    )[1]
    if hashlib.sha256(audit_payload).hexdigest() != source_audit_sha256:
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion metadata was computed from a different "
            "audio ownership audit"
        )
    raw_promotions = document.get("promotions")
    if not isinstance(raw_promotions, list):
        raise Nfl2k5AudoFamilyLabelError(
            "Family-label promotion metadata is missing its promotion rows"
        )
    promotions: dict[str, AudoFamilyLabelPromotion] = {}
    for raw in raw_promotions:
        promotion = _normalize_promotion(raw)
        if promotion.key in promotions:
            raise Nfl2k5AudoFamilyLabelError(
                f"Family-label promotion duplicates cue {promotion.key}"
            )
        promotions[promotion.key] = promotion
    return promotions


__all__ = [
    "AudoFamilyLabelPromotion",
    "FAMILY_LABEL_GROUP_KINDS",
    "FAMILY_LABEL_PREFIX",
    "FAMILY_LABEL_REPORT",
    "FAMILY_LABEL_REPORT_SCHEMA",
    "FAMILY_LABEL_REPORT_SHA256",
    "FAMILY_REVIEWED_CONFIDENCE",
    "MAX_FAMILY_LABEL_REPORT_BYTES",
    "Nfl2k5AudoFamilyLabelError",
    "load_family_label_promotions",
]

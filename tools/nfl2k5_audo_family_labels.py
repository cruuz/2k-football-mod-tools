#!/usr/bin/env python3
"""Group NFL 2K5 standalone AUDO cues into audible-equivalence families.

The pinned import-capacity audit already partitions the 850 standalone sounds
into ``equal_decoded_content_groups`` and ``equal_resource_span_groups`` --
cues whose decoded PCM16 (or whole stored resource span) is byte-identical and
therefore *sounds identical*.  This tool turns that partition into the
deterministic labeling pass for the 697 alias-related cues whose in-game
meaning is otherwise unproved:

* a provisional cue is promoted to ``family-reviewed`` confidence only when it
  belongs to an equal-content or equal-span group whose representative carries
  an already reviewed label (one of the 152 reviewed labels or the proved
  Menu Back writer route);
* the promoted label text always carries the ``family: `` prefix so the
  family inference is disclosed wherever it is displayed;
* every promotion records per-cue provenance (group id, group kind,
  representative cue, confidence, evidence hash);
* reviewed labels and the Menu Back proof are never relabeled;
* a provisional cue with no reviewed representative stays provisional.

This is a headless *labeling aid*, not a runtime-ownership proof: equal PCM
proves equal sound, not equal trigger.  Families without a reviewed
representative (the 340-member ``oclapaa_01`` crowd-chant family among them)
stay provisional until xemu instrumentation assigns per-cue runtime owners.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

SCHEMA = "nfl2k5_audo_family_labels/v2"
AUDIT_SCHEMA = "nfl2k5_audo_import_capacity/v1"
DEFAULT_AUDIT = Path("reports/assets/nfl2k5_audo_import_capacity.json")

REVIEWED_CLASSIFICATION = "structurally-encodable-owner-runtime-unproved"
CANDIDATE_CLASSIFICATION = "candidate-for-separately-authorized-fixed-slot-writer"
PROVISIONAL_CLASSIFICATION = "export-only"
PROVED_WRITER_AUTHORIZATION = "public-offline-writer-proved"
FAMILY_LABEL_PREFIX = "family: "
FAMILY_REVIEWED_CONFIDENCE = "family-reviewed"

# Equal decoded content is the stronger audible-equivalence claim, so it wins
# whenever a cue sits in both kinds of promotable group.
GROUP_KINDS = (
    ("equal_decoded_content", "equal_decoded_content_groups", "decoded_pcm_sha256"),
    ("equal_resource_span", "equal_resource_span_groups", "resource_span_sha256"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_audit(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw)
    require(value.get("schema") == AUDIT_SCHEMA, "audit schema mismatch")
    return value


def reviewed_keys(audit: dict[str, object]) -> tuple[set[str], set[str]]:
    """Return the reviewed label sets.

    The first set is the structurally reviewed labels; the second is any
    separately authorized fixed slot whose writer route is proved (the Menu
    Back proof).  Their union is every cue whose label may anchor a family
    promotion, and which is itself never relabeled.
    """

    structural: set[str] = set()
    proved_fixed: set[str] = set()
    for rec in audit["records"]:
        classification = rec.get("classification")
        if classification == REVIEWED_CLASSIFICATION:
            structural.add(rec["key"])
        elif (
            classification == CANDIDATE_CLASSIFICATION
            and rec.get("ownership", {}).get("fixed_slot_authorization")
            == PROVED_WRITER_AUTHORIZATION
        ):
            proved_fixed.add(rec["key"])
    return structural, proved_fixed


def build_promotions(
    audit: dict[str, object], reviewed: set[str]
) -> list[dict[str, object]]:
    """Deterministically promote provisional cues with reviewed representatives."""

    records = {rec["key"]: rec for rec in audit["records"]}
    groups = audit["groups"]
    promoted: dict[str, dict[str, object]] = {}
    for kind, group_list_key, evidence_key in GROUP_KINDS:
        for group in sorted(groups[group_list_key], key=lambda g: g["group_id"]):
            members = sorted(group["members"])
            representatives = sorted(key for key in members if key in reviewed)
            if not representatives:
                continue
            representative = representatives[0]
            for key in members:
                if key in reviewed or key in promoted:
                    continue
                record = records[key]
                if record.get("classification") != PROVISIONAL_CLASSIFICATION:
                    continue
                promoted[key] = {
                    "key": key,
                    "name": record.get("name"),
                    "label": FAMILY_LABEL_PREFIX + records[representative]["name"],
                    "confidence": FAMILY_REVIEWED_CONFIDENCE,
                    "group_id": group["group_id"],
                    "group_kind": kind,
                    "representative_key": representative,
                    "representative_name": records[representative]["name"],
                    "evidence_sha256": group[evidence_key],
                    "member_count": len(members),
                }
    return [promoted[key] for key in sorted(promoted)]


def build_families(
    audit: dict[str, object], *, source_audit_sha256: str
) -> dict[str, object]:
    records = {rec["key"]: rec for rec in audit["records"]}
    structural_reviewed, proved_fixed = reviewed_keys(audit)
    reviewed = structural_reviewed | proved_fixed
    groups = audit["groups"]["equal_decoded_content_groups"]

    families = []
    for group in sorted(groups, key=lambda g: g["group_id"]):
        members = group["members"]
        member_records = [records[key] for key in members]
        names = sorted({rec.get("name") or "" for rec in member_records})
        reviewed_members = sorted(
            rec["key"] for rec in member_records if rec["key"] in reviewed
        )
        export_only_members = sorted(
            rec["key"] for rec in member_records
            if rec.get("classification") == PROVISIONAL_CLASSIFICATION
        )
        # A family carries a confident audible label only when it contains at
        # least one reviewed member; a shared name alone proves nothing about
        # meaning (the 340 oclapaa_01 cues share a name, not a meaning).
        confident_label = (
            records[reviewed_members[0]].get("name") if reviewed_members else None
        )
        families.append({
            "group_id": group["group_id"],
            "decoded_pcm_sha256": group["decoded_pcm_sha256"],
            "channels": group.get("channels"),
            "sample_rate": group.get("sample_rate"),
            "member_count": len(members),
            "members": members,
            "distinct_names": names,
            "reviewed_members": reviewed_members,
            "export_only_members": export_only_members,
            "confident_audible_label": confident_label,
            "label_basis": (
                "reviewed-representative" if reviewed_members else "none"
            ),
        })

    families.sort(key=lambda f: (-f["member_count"], f["group_id"]))
    promotions = build_promotions(audit, reviewed)
    provisional_count = sum(
        1 for rec in records.values()
        if rec.get("classification") == PROVISIONAL_CLASSIFICATION
    )
    return {
        "schema": SCHEMA,
        "source_audit_sha256": source_audit_sha256,
        "summary": {
            "record_count": len(records),
            "reviewed_label_count": len(structural_reviewed),
            "proved_fixed_slot_count": len(proved_fixed),
            "provisional_record_count": provisional_count,
            "equal_content_family_count": len(families),
            "equal_span_group_count": len(
                audit["groups"]["equal_resource_span_groups"]),
            "promoted_cue_count": len(promotions),
            "provisional_remaining_count": provisional_count - len(promotions),
            "largest_family_member_count": (
                families[0]["member_count"] if families else 0),
        },
        "claims": {
            "equal_pcm_means_equal_sound": True,
            "equal_pcm_means_equal_runtime_trigger": False,
            "family_label_is_inference_not_runtime_proof": True,
            "reviewed_labels_overwritten": False,
            "runtime_ownership_proved": False,
            "portme": (
                "Families without a reviewed representative still need runtime "
                "instrumentation to assign per-cue owners; instrument one "
                "deterministic action logging outer/chunk/name/game-state."
            ),
        },
        "promotions": promotions,
        "families": families,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require(not args.output.exists(), "output already exists")
        audit = load_audit(args.audit)
        result = build_families(
            audit,
            source_audit_sha256=hashlib.sha256(args.audit.read_bytes()).hexdigest(),
        )
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"nfl2k5_audo_family_labels: {exc}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    summary = result["summary"]
    print(
        "NFL2K5_AUDO_FAMILY_LABELS_OK "
        f"families={summary['equal_content_family_count']} "
        f"reviewed={summary['reviewed_label_count']} "
        f"promoted={summary['promoted_cue_count']} "
        f"provisional_remaining={summary['provisional_remaining_count']} "
        f"largest={summary['largest_family_member_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

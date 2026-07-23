#!/usr/bin/env python3
"""Group NFL 2K5 standalone AUDO cues into audible-equivalence families.

The pinned import-capacity audit already partitions the 850 standalone sounds
into ``equal_decoded_content_groups`` — cues whose decoded PCM16 is
byte-identical and therefore *sound identical*.  This tool turns that partition
into a labeling aid for the 697 alias-related cues whose in-game meaning is
otherwise unproved:

* every member of a multi-member equal-content family is audibly equivalent to
  the others, so a human-readable label confirmed for any one member applies
  audibly to all of them;
* a family whose members share a single non-empty name carries a confident
  audible label without any runtime work;
* a family that contains at least one runtime-reviewed cue inherits that cue's
  confirmed meaning for every sibling.

This is a headless *labeling aid*, not a runtime-ownership proof: equal PCM
proves equal sound, not equal trigger.  The output is a deterministic report a
mod author can use to label crowds/ambience confidently while the remaining
duplicate-name/different-content cues still await runtime instrumentation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

SCHEMA = "nfl2k5_audo_family_labels/v1"
AUDIT_SCHEMA = "nfl2k5_audo_import_capacity/v1"
DEFAULT_AUDIT = Path("reports/assets/nfl2k5_audo_import_capacity.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_audit(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw)
    require(value.get("schema") == AUDIT_SCHEMA, "audit schema mismatch")
    return value


def build_families(audit: dict[str, object]) -> dict[str, object]:
    records = {rec["key"]: rec for rec in audit["records"]}
    reviewed_keys = {
        rec["key"] for rec in audit["records"]
        if rec.get("classification") == "structurally-encodable-owner-runtime-unproved"
    }
    groups = audit["groups"]["equal_decoded_content_groups"]

    families = []
    export_only_in_multimember = 0
    export_only_with_confident_label = 0
    for group in groups:
        members = group["members"]
        member_records = [records[key] for key in members]
        names = sorted({rec.get("name") or "" for rec in member_records})
        non_empty_names = [name for name in names if name]
        consistent_name = (
            non_empty_names[0] if len(non_empty_names) == 1 and
            all(rec.get("name") == non_empty_names[0] for rec in member_records)
            else None
        )
        reviewed_members = [
            rec["key"] for rec in member_records if rec["key"] in reviewed_keys
        ]
        export_only_members = [
            rec["key"] for rec in member_records
            if rec.get("classification") == "export-only"
        ]
        # A confident audible label exists when the family is name-consistent or
        # carries at least one reviewed member.
        confident_label = consistent_name or (
            records[reviewed_members[0]].get("name") if reviewed_members else None
        )
        if len(members) > 1:
            export_only_in_multimember += len(export_only_members)
            if confident_label:
                export_only_with_confident_label += len(export_only_members)
        families.append({
            "group_id": group["group_id"],
            "decoded_pcm_sha256": group["decoded_pcm_sha256"],
            "channels": group.get("channels"),
            "sample_rate": group.get("sample_rate"),
            "member_count": len(members),
            "members": members,
            "distinct_names": names,
            "consistent_name": consistent_name,
            "reviewed_members": reviewed_members,
            "export_only_members": export_only_members,
            "confident_audible_label": confident_label,
            "label_basis": (
                "consistent-name" if consistent_name
                else "reviewed-sibling" if reviewed_members
                else "none"
            ),
        })

    families.sort(key=lambda f: (-f["member_count"], f["group_id"]))
    multimember = [f for f in families if f["member_count"] > 1]
    return {
        "schema": SCHEMA,
        "source_audit_sha256": hashlib.sha256(
            DEFAULT_AUDIT.read_bytes()).hexdigest()
        if DEFAULT_AUDIT.exists() else None,
        "summary": {
            "record_count": len(records),
            "equal_content_family_count": len(families),
            "multimember_family_count": len(multimember),
            "singleton_family_count": len(families) - len(multimember),
            "export_only_record_count": sum(
                1 for rec in records.values()
                if rec.get("classification") == "export-only"),
            "export_only_in_multimember_family": export_only_in_multimember,
            "export_only_with_confident_audible_label":
                export_only_with_confident_label,
            "largest_family_member_count": (
                multimember[0]["member_count"] if multimember else 0),
        },
        "claims": {
            "equal_pcm_means_equal_sound": True,
            "equal_pcm_means_equal_runtime_trigger": False,
            "runtime_ownership_proved": False,
            "portme": (
                "Families labeled 'none' (duplicate name, different content) still "
                "need runtime instrumentation to assign per-cue owners; instrument "
                "one deterministic action logging outer/chunk/name/game-state."
            ),
        },
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
        result = build_families(audit)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"nfl2k5_audo_family_labels: {exc}", file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    summary = result["summary"]
    print(
        "NFL2K5_AUDO_FAMILY_LABELS_OK "
        f"families={summary['equal_content_family_count']} "
        f"multimember={summary['multimember_family_count']} "
        f"export_only={summary['export_only_record_count']} "
        f"export_only_confident={summary['export_only_with_confident_audible_label']} "
        f"largest={summary['largest_family_member_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

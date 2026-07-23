#!/usr/bin/env python3
"""Validate the APF roster identity writer without publishing game bytes."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import apf_roster_identity_patch as writer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def main() -> int:
    try:
        writer._self_test()  # type: ignore[attr-defined]
        if not SOURCE.is_file():
            print(
                "APF_ROSTER_IDENTITY_VALIDATION_PASS "
                "private_source=false self_test=true retail_bytes=0 offsets=0"
            )
            return 0
        allocations = writer.inventory(SOURCE)
        selected = next(item for item in allocations if item.editable)
        replacement = "X" if selected.text != "X" else "Y"
        result = writer.build_patch(
            SOURCE, {selected.pool_index: replacement}
        )
        manifest_text = json.dumps(result.manifest, sort_keys=True)
        if (
            result.manifest.get("mode") != "patched"
            or len(result.entry_bytes) <= 0
            or replacement in manifest_text
            or "pack_offset" in manifest_text
            or "byte_offset" in manifest_text
            or result.manifest.get("validation", {}).get(
                "fixed_outer_allocation_preserved"
            )
            is not True
        ):
            raise writer.RosterIdentityError(
                "Changed-path validation did not satisfy the retail-free contract"
            )
        print(
            "APF_ROSTER_IDENTITY_VALIDATION_PASS "
            f"private_source=true allocations={len(allocations)} "
            f"editable={sum(item.editable for item in allocations)} "
            f"owners={sum(item.known_owner_count for item in allocations)} "
            f"changed={result.manifest['output']['decoded_changed_byte_count']} "
            "numbers=read_only_unmapped retail_bytes=0 offsets=0"
        )
        return 0
    except (writer.RosterIdentityError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

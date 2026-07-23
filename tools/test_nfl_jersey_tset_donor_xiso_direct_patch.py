#!/usr/bin/env python3
"""Focused fail-closed tests for the jersey TSET donor writer."""

from __future__ import annotations

from pathlib import Path
import tempfile

import nfl_jersey_tset_donor_xiso_direct_patch as writer
from nfl_outer import parse_archive
from nfl_scene_probe import read_entry_range
import nfl_uniform_color_xiso_direct_patch as common


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"


def expect_patch_error(callback, label: str) -> None:
    try:
        callback()
    except (common.PatchError, OSError):
        return
    raise AssertionError(f"{label} did not fail closed")


def main() -> int:
    archive = parse_archive(INDEX)
    target = read_entry_range(
        archive, archive.entries[writer.TARGET_OUTER_INDEX],
        writer.TSET_CHUNK_OFFSET, writer.TSET_SPAN_SIZE,
    )
    donor = read_entry_range(
        archive, archive.entries[writer.DONOR_OUTER_INDEX],
        writer.TSET_CHUNK_OFFSET, writer.TSET_SPAN_SIZE,
    )
    offsets, runs = writer.validate_span_pair(target, donor)
    assert len(offsets) == writer.RELATIVE_DIFF_COUNT
    assert len(runs) == writer.RELATIVE_RUN_COUNT
    assert writer.offset_digest(offsets) == writer.RELATIVE_DIFF_U32LE_SHA256
    assert writer.run_digest(runs) == writer.RELATIVE_RUN_U32LE_SHA256
    assert offsets == sorted(set(offsets))
    assert sum(end - start + 1 for start, end in runs) == len(offsets)

    damaged_target = bytearray(target)
    damaged_target[0x20] ^= 1
    expect_patch_error(
        lambda: writer.validate_span_pair(bytes(damaged_target), donor),
        "damaged target stream",
    )
    damaged_donor = bytearray(donor)
    damaged_donor[-1] ^= 1
    expect_patch_error(
        lambda: writer.validate_span_pair(target, bytes(damaged_donor)),
        "damaged donor stream",
    )
    expect_patch_error(
        lambda: writer.validate_span_pair(target[:-1], donor),
        "short target span",
    )

    assert writer.difference_runs([1, 2, 3, 7, 9, 10]) == [
        (1, 3), (7, 7), (9, 10)
    ]
    with tempfile.TemporaryDirectory(prefix="nfl-tset-writer-test-") as temp:
        root = Path(temp)
        canonical = writer.canonical_new_path(root / "new.xiso.iso")
        assert canonical == root.resolve() / "new.xiso.iso"
        expect_patch_error(
            lambda: writer.canonical_new_path(root / "missing" / "new.iso"),
            "missing output parent",
        )

    print(
        "NFL_JERSEY_TSET_DONOR_WRITER_TESTS_PASS "
        f"relative_diffs={len(offsets)} runs={len(runs)} fail_closed=3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Focused constants/fail-closed tests for the PNG-import XISO writer."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

from nfl_outer import parse_archive
from nfl_scene_probe import read_entry_range
import nfl_tset_png_import_xiso_direct_patch as writer
import nfl_uniform_color_xiso_direct_patch as common


ROOT = Path(__file__).resolve().parents[1]


def expect_failure(callback, label: str) -> None:
    try:
        callback()
    except (OSError, common.PatchError):
        return
    raise AssertionError(f"{label} did not fail closed")


def main() -> int:
    archive = parse_archive(ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    source = read_entry_range(
        archive, archive.entries[writer.TARGET_OUTER_INDEX],
        writer.TARGET_CHUNK_OFFSET, writer.SPAN_SIZE,
    )
    replacement = (
        ROOT / "reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.tset.bin"
    ).read_bytes()
    offsets = [
        index for index, (before, after) in enumerate(zip(source, replacement))
        if before != after
    ]
    runs = writer.difference_runs(offsets)
    assert len(offsets) == writer.RELATIVE_DIFF_COUNT
    assert writer.digest_offsets(offsets, "<I") == writer.RELATIVE_DIFF_U32LE_SHA256
    assert len(runs) == writer.RELATIVE_RUN_COUNT
    assert writer.run_digest(runs) == writer.RELATIVE_RUN_U32LE_SHA256
    absolute = [writer.TARGET_SPAN_ABSOLUTE + value for value in offsets]
    assert writer.digest_offsets(absolute, "<Q") == writer.ABSOLUTE_DIFF_U64LE_SHA256
    assert source[:0x20] == replacement[:0x20]

    manifest = json.loads(
        (ROOT / "reports/assets/nfl2k5_lions_09H0_diagnostic_png_import_xiso_direct.json")
        .read_text(encoding="utf-8")
    )
    assert manifest["output"]["sha256"] == \
        "b9f47fcec3e284a12ea30f390035dd29f97fa62507330ba3ff30391cf4e10ae6"
    assert manifest["patch"]["actual_changed_byte_count"] == len(offsets)
    assert manifest["claims"]["runtime_visibility_proved"] is False
    assert manifest["claims"]["xemu_started"] is False

    damaged = bytearray(replacement)
    damaged[-1] ^= 1
    assert writer.sha256_bytes(bytes(damaged)) != writer.REPLACEMENT_SPAN_SHA256
    with tempfile.TemporaryDirectory(prefix="nfl-png-xiso-writer-test-") as temp:
        root = Path(temp)
        assert writer.canonical_new_path(root / "new.iso") == root.resolve() / "new.iso"
        expect_failure(
            lambda: writer.canonical_new_path(root / "absent" / "new.iso"),
            "absent output parent",
        )

    print(
        "NFL_TSET_PNG_IMPORT_XISO_WRITER_TESTS_PASS "
        f"changed_bytes={len(offsets)} runs={len(runs)} wrapper_preserved=true "
        "runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

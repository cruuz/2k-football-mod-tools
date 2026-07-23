#!/usr/bin/env python3
"""Deterministic safety/unit tests for the bounded NFL uniform color writer."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import sys


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import nfl_uniform_color_patch as patch  # noqa: E402
from nfl_outer import Archive, Pack  # noqa: E402


SENTINEL_REPLACEMENT = b"replacement path must survive\n"


def cross_pack_mapping_case(root: Path) -> None:
    packs = (
        Pack(0, "0", 1, 0x800, 0x000, root / "0"),
        Pack(1, "1", 1, 0x800, 0x800, root / "1"),
        Pack(2, "2", 1, 0x800, 0x1000, root / "2"),
    )
    archive = Archive(root / "0", 0, 3, packs, ())
    slices = patch.map_virtual_write(archive, 0x7FE, b"abcdef")
    assert [(item.pack_name, item.pack_offset, item.data) for item in slices] == [
        ("0", 0x7FE, b"ab"),
        ("1", 0x000, b"cdef"),
    ]


def owned_inode_swap_case(root: Path) -> None:
    destination = root / "owned"
    displaced = root / "displaced"
    owned = patch.reserve_file(destination)
    try:
        destination.rename(displaced)
        destination.write_bytes(SENTINEL_REPLACEMENT)
        try:
            patch.pwrite_owned(owned, 0, b"x")
        except patch.PatchError as exc:
            assert "inode changed" in str(exc)
        else:
            raise AssertionError("post-reservation inode swap was accepted")
        patch.unlink_if_owned(owned)
        assert destination.read_bytes() == SENTINEL_REPLACEMENT
        assert displaced.read_bytes() == b""
    finally:
        os.close(owned.descriptor)


def exclusive_destination_case(root: Path) -> None:
    destination = root / "existing"
    destination.write_bytes(b"do not replace")
    try:
        patch.reserve_file(destination)
    except patch.PatchError:
        pass
    else:
        raise AssertionError("existing output destination was accepted")
    assert destination.read_bytes() == b"do not replace"


def clone_breaks_writable_links_case(root: Path) -> None:
    source = root / "source"
    output = root / "output"
    (source / "vc_53450030").mkdir(parents=True)
    (source / "vc_53450030/A").write_bytes(b"A" * 4096)
    (source / "vc_53450030/B").write_bytes(b"B" * 4096)
    (source / "default.xbe").write_bytes(b"unrelated")
    relative = [Path("vc_53450030/A"), Path("vc_53450030/B"), Path("default.xbe")]
    original_hashes = dict(patch.EXPECTED_PACK_SHA256)
    patch.EXPECTED_PACK_SHA256.update(
        {
            "A": patch.sha256_file(source / "vc_53450030/A"),
            "B": patch.sha256_file(source / "vc_53450030/B"),
        }
    )
    owned: dict[str, patch.OwnedFile] = {}
    try:
        stats, owned, _ = patch.clone_tree(source, output, relative)
        assert stats == {"hardlinked_files": 1, "copied_files": 2}
        assert (source / "default.xbe").stat().st_ino == (output / "default.xbe").stat().st_ino
        for name in ("A", "B"):
            assert (source / f"vc_53450030/{name}").stat().st_ino != (
                output / f"vc_53450030/{name}"
            ).stat().st_ino
            assert patch.owned_path_matches(owned[name])
    finally:
        patch.EXPECTED_PACK_SHA256.clear()
        patch.EXPECTED_PACK_SHA256.update(original_hashes)
        for item in owned.values():
            os.close(item.descriptor)


def exact_diff_case(root: Path) -> None:
    source = root / "diff-source"
    output = root / "diff-output"
    source.write_bytes(bytes(range(64)))
    owned = patch.reserve_file(output)
    try:
        source_fd = os.open(source, os.O_RDONLY)
        try:
            patch._copy_fd(source_fd, owned.descriptor, 64)  # type: ignore[attr-defined]
        finally:
            os.close(source_fd)
        patch.pwrite_owned(owned, 20, b"\xff\xfe\xfd\xfc")
        changed = patch.changed_offsets(source, owned, set(range(20, 24)))
        assert changed == [20, 21, 22, 23]
        try:
            patch.changed_offsets(source, owned, {20, 21, 22})
        except patch.PatchError as exc:
            assert "unintended byte change" in str(exc)
        else:
            raise AssertionError("out-of-policy byte difference was accepted")
    finally:
        os.close(owned.descriptor)


def source_nesting_case(root: Path) -> None:
    source = root / "retail"
    source.mkdir()
    manifest = root / "manifest.json"
    try:
        patch.preflight_paths(source, source / "patched", manifest)
    except patch.PatchError as exc:
        assert "inside source" in str(exc)
    else:
        raise AssertionError("output nested within source was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="nfl-uniform-color-writer-") as temporary:
        root = Path(temporary)
        cases = [
            ("cross_pack_virtual_mapping", cross_pack_mapping_case),
            ("owned_inode_swap", owned_inode_swap_case),
            ("exclusive_destination", exclusive_destination_case),
            ("clone_breaks_writable_links", clone_breaks_writable_links_case),
            ("exact_diff_policy", exact_diff_case),
            ("source_output_nesting", source_nesting_case),
        ]
        for index, (_, case) in enumerate(cases):
            case_root = root / f"case-{index}"
            case_root.mkdir()
            case(case_root)

    report = {
        "schema": "nfl2k5_uniform_color_patch_tests/v1",
        "case_count": len(cases),
        "cases": [name for name, _ in cases],
        "proved_invariants": {
            "virtual_writes_split_at_pack_boundaries": True,
            "post_reservation_path_swap_rejected": True,
            "replacement_path_not_deleted_by_cleanup": True,
            "existing_output_not_replaced": True,
            "target_packs_copied_to_independent_inodes": True,
            "unrelated_files_hardlinked": True,
            "diff_scanner_rejects_changes_outside_allowed_offsets": True,
            "output_tree_inside_source_rejected": True,
        },
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"NFL_UNIFORM_COLOR_PATCH_TEST_PASS cases={len(cases)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

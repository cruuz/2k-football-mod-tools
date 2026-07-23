#!/usr/bin/env python3
"""Verify and document the NFL 2K5 Lions color-patch XISO round trip."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import nfl_uniform_color_patch as color_patch
from nfl_outer import parse_archive, read_entry_range


SCHEMA = "nfl2k5_uniform_color_xiso_proof/v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise color_patch.PatchError(message)


def file_inventory(root: Path) -> list[Path]:
    result = [path.relative_to(root) for path in root.rglob("*") if path.is_file()]
    require(not any(path.is_symlink() for path in root.rglob("*")), f"symlink in extracted tree: {root}")
    return sorted(result)


def git_commit_for(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path.parent.parent), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def extract_xiso_version(path: Path) -> str:
    result = subprocess.run([str(path), "-v"], check=True, capture_output=True, text=True)
    return (result.stdout + result.stderr).strip()


def verify_listing(tool: Path, xiso: Path, expected: dict[str, int]) -> dict[str, object]:
    result = subprocess.run(
        [str(tool), "-l", str(xiso)], check=True, capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    for relative, size in expected.items():
        require(f"/{relative} ({size} bytes)" in output, f"XISO list is missing {relative}")
    require("19 files in" in output, "XISO listing did not report 19 files")
    return {
        "command": [str(tool), "-l", str(xiso)],
        "listed_file_count": 19,
        "all_expected_paths_and_sizes_present": True,
        "saved_listing": "reports/assets/nfl2k5_lions_magenta_xiso_listing.txt",
    }


def verify_patched_fields(root: Path) -> list[dict[str, object]]:
    archive = parse_archive(root / color_patch.TESTED_INDEX_REL)
    result: list[dict[str, object]] = []
    for target in color_patch.TARGETS:
        entry = archive.entries[target.outer_index]
        require(entry.name_id == target.name_id, f"{root}: target ID mismatch")
        raw = read_entry_range(
            archive, entry, color_patch.COLOR_PAIR_ENTRY_OFFSET, len(color_patch.MAGENTA_PAIR)
        )
        require(raw == color_patch.MAGENTA_PAIR, f"{root}: {target.logical_name} is not magenta")
        result.append(
            {
                "outer_index": target.outer_index,
                "logical_name": target.logical_name,
                "raw_hex": raw.hex(),
                "colors": [f"0x{color_patch.MAGENTA_ARGB:08x}"] * 2,
            }
        )
    return result


def generate(
    source_iso: Path,
    source_root: Path,
    patched_root: Path,
    xiso: Path,
    reextracted_root: Path,
    extract_xiso: Path,
    patch_manifest_path: Path,
) -> dict[str, object]:
    for path in (source_iso, xiso, extract_xiso, patch_manifest_path):
        require(path.is_file(), f"missing input: {path}")
    for path in (source_root, patched_root, reextracted_root):
        require(path.is_dir(), f"missing tree: {path}")

    patch_manifest = json.loads(patch_manifest_path.read_text(encoding="utf-8"))
    require(patch_manifest["schema"] == color_patch.SCHEMA, "patch manifest schema mismatch")
    require(Path(patch_manifest["source"]["game_root"]) == source_root, "patch source root mismatch")
    require(Path(patch_manifest["output"]["game_root"]) == patched_root, "patch output root mismatch")

    source_files = file_inventory(source_root)
    patched_files = file_inventory(patched_root)
    reextracted_files = file_inventory(reextracted_root)
    require(source_files == patched_files == reextracted_files, "tree file lists differ")
    require(len(source_files) == color_patch.EXPECTED_FILE_COUNT, "unexpected game file count")

    source_iso_sha = color_patch.sha256_file(source_iso)
    require(source_iso_sha == color_patch.EXPECTED_ISO_SHA256, "original ISO SHA-256 mismatch")
    xiso_sha = color_patch.sha256_file(xiso)

    patched_pack_hashes = {record["pack"]: record["patched_sha256"] for record in patch_manifest["packs"]}
    files: list[dict[str, object]] = []
    expected_listing: dict[str, int] = {}
    for relative in source_files:
        source_path = source_root / relative
        patched_path = patched_root / relative
        reextracted_path = reextracted_root / relative
        source_info = source_path.stat(follow_symlinks=False)
        patched_info = patched_path.stat(follow_symlinks=False)
        reextracted_info = reextracted_path.stat(follow_symlinks=False)
        require(source_info.st_size == patched_info.st_size == reextracted_info.st_size, f"size mismatch: {relative}")
        source_hash = color_patch.sha256_file(source_path)
        reextracted_hash = color_patch.sha256_file(reextracted_path)
        is_target = relative in color_patch.TARGET_PACK_RELS
        if is_target:
            pack_name = relative.name
            patched_hash = color_patch.sha256_file(patched_path)
            require(source_hash == color_patch.EXPECTED_PACK_SHA256[pack_name], f"source pack changed: {pack_name}")
            require(patched_hash == patched_pack_hashes[pack_name], f"patched pack hash mismatch: {pack_name}")
            require(reextracted_hash == patched_hash, f"XISO round trip lost patch in pack {pack_name}")
            require((source_info.st_dev, source_info.st_ino) != (patched_info.st_dev, patched_info.st_ino), f"target pack still aliases source: {pack_name}")
            relation = "independent_patched_copy"
        else:
            require((source_info.st_dev, source_info.st_ino) == (patched_info.st_dev, patched_info.st_ino), f"unrelated clone file is not unchanged hardlink: {relative}")
            patched_hash = source_hash
            require(reextracted_hash == source_hash, f"unrelated file changed through XISO: {relative}")
            relation = "unchanged_hardlink_then_byte_exact_reextract"
        files.append(
            {
                "path": str(relative),
                "size": source_info.st_size,
                "source_sha256": source_hash,
                "patched_tree_sha256": patched_hash,
                "reextracted_sha256": reextracted_hash,
                "relation": relation,
            }
        )
        expected_listing[str(relative)] = source_info.st_size

    by_path = {record["path"]: record for record in files}
    require(by_path["default.xbe"]["source_sha256"] == color_patch.EXPECTED_XBE_SHA256, "source XBE changed")
    require(by_path["default.xbe"]["reextracted_sha256"] == color_patch.EXPECTED_XBE_SHA256, "-m XBE preservation failed")
    require(by_path[str(color_patch.TESTED_INDEX_REL)]["source_sha256"] == color_patch.EXPECTED_INDEX_SHA256, "source archive index changed")
    require(by_path[str(color_patch.TESTED_INDEX_REL)]["reextracted_sha256"] == color_patch.EXPECTED_INDEX_SHA256, "reextracted archive index changed")

    # Strict original parser validation is repeated after all write/repack work.
    source_archive = parse_archive(source_root / color_patch.TESTED_INDEX_REL)
    for target in color_patch.TARGETS:
        color_patch.validate_target(source_archive, target)
    patched_fields = verify_patched_fields(patched_root)
    reextracted_fields = verify_patched_fields(reextracted_root)
    listing = verify_listing(extract_xiso, xiso, expected_listing)

    tool_commit = git_commit_for(extract_xiso)
    require(tool_commit == "b72e5b60d598ec6df80534cda19cdcd4361aa18c", "extract-xiso commit mismatch")
    return {
        "schema": SCHEMA,
        "scope": {
            "claim": "copy-only raw Unif color edit survived XISO create/list/extract",
            "title": "ESPN NFL 2K5 (USA)",
            "team": "Detroit Lions",
            "packages": ["09H0.IFF", "09A0.IFF"],
            "texture_or_model_replacement_proved": False,
            "runtime_visibility_proved": False,
        },
        "artifacts": {
            "source_iso": str(source_iso),
            "source_iso_size": source_iso.stat().st_size,
            "source_iso_sha256": source_iso_sha,
            "patched_game_tree": str(patched_root),
            "patched_xiso": str(xiso),
            "patched_xiso_size": xiso.stat().st_size,
            "patched_xiso_sha256": xiso_sha,
            "reextracted_game_tree": str(reextracted_root),
            "patch_manifest": str(patch_manifest_path),
        },
        "extract_xiso": {
            "path": str(extract_xiso),
            "sha256": color_patch.sha256_file(extract_xiso),
            "version": extract_xiso_version(extract_xiso),
            "git_commit": tool_commit,
            "create_command": [
                str(extract_xiso),
                "-m",
                "-c",
                str(patched_root),
                str(xiso),
            ],
            "media_patch_disabled_with_m": True,
            "listing": listing,
            "extract_command": [
                str(extract_xiso),
                "-x",
                "-d",
                str(reextracted_root),
                str(xiso),
            ],
        },
        "patched_tree_fields": patched_fields,
        "reextracted_fields": reextracted_fields,
        "files": files,
        "validation": {
            "source_iso_pin_unchanged": True,
            "source_xbe_pin_unchanged": True,
            "source_archive_index_pin_unchanged": True,
            "source_target_packs_pin_unchanged": True,
            "xiso_created_with_media_patch_disabled": True,
            "xiso_listed_all_19_files_with_expected_sizes": True,
            "xiso_reextracted_successfully": True,
            "all_17_unrelated_files_byte_exact_after_reextract": True,
            "both_2_target_packs_match_patched_tree_after_reextract": True,
            "both_4_patched_color_words_parse_as_opaque_magenta_after_reextract": True,
            "default_xbe_byte_exact_after_create_and_reextract": True,
        },
        "portme": [
            "PORTME: emulator runtime visibility is not established by an XISO byte round trip.",
            "PORTME: these raw color words are not PNG-backed textures; texture/model import remains separate work.",
            "PORTME: extract-xiso rebuilds filesystem layout, so the patched XISO need not match the retail ISO byte-for-byte or in total image size.",
            "PORTME: only fixed-size writes to the two proved Unif fields are supported by the current writer.",
        ],
        "phase_summary": {
            "worked": [
                "A pinned extract-xiso build created the image with -m, listed all files, and re-extracted it.",
                "All 17 unrelated game files survived byte-exact; packs A/B exactly match their patched copies.",
                "The four Lions color fields reparsed as 0xffff00ff from the re-extracted XISO.",
                "The retail ISO, XBE, archive index, and source packs remained at their pinned hashes.",
            ],
            "failed": [
                "No runtime emulator screenshot was captured by this static round-trip proof."
            ],
            "blocking": [
                "Runtime navigation to a Lions uniform preview is still needed to prove the visible material effect.",
                "PNG textures and model repacking require separate serializers and are not implied by this proof.",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-iso", type=Path, required=True)
    parser.add_argument("--source-game-root", type=Path, required=True)
    parser.add_argument("--patched-game-root", type=Path, required=True)
    parser.add_argument("--xiso", type=Path, required=True)
    parser.add_argument("--reextracted-game-root", type=Path, required=True)
    parser.add_argument("--extract-xiso", type=Path, required=True)
    parser.add_argument("--patch-manifest", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)

    owned: color_patch.OwnedFile | None = None
    try:
        output = args.manifest.parent.resolve(strict=True) / args.manifest.name
        owned = color_patch.reserve_file(output)
        report = generate(
            args.source_iso.resolve(strict=True),
            args.source_game_root.resolve(strict=True),
            args.patched_game_root.resolve(strict=True),
            args.xiso.resolve(strict=True),
            args.reextracted_game_root.resolve(strict=True),
            args.extract_xiso.resolve(strict=True),
            args.patch_manifest.resolve(strict=True),
        )
        color_patch.write_owned_json(owned, report)
        print(
            "NFL_UNIFORM_COLOR_XISO_PROOF_PASS files=19 unrelated=17 "
            "patched_packs=2 patched_words=4 media_patch_disabled=true"
        )
        return 0
    except (OSError, subprocess.SubprocessError, color_patch.PatchError, ValueError) as exc:
        if owned is not None:
            try:
                color_patch.unlink_if_owned(owned)
            except OSError:
                pass
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if owned is not None:
            os.close(owned.descriptor)


if __name__ == "__main__":
    raise SystemExit(main())

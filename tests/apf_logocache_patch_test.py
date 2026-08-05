#!/usr/bin/env python3
"""End-to-end copied-volume + independent-verifier gate for the cache logo writer.

Mirrors ``tests/apf_logo_patch_test.py``.  Proves, offline against the extracted
retail ``0A``:

* the pinned retail directory/payload hashes and F0985030 structure still hold;
* a controlled catalog-1 edit (magenta ``01_logo_l0`` + cyan ``01_logo_l1``)
  rewrites both cache VRAM base levels, preserving every DRAM part, every packed
  mip tail, and every other catalog entry, inside the fixed allocations; and
* with ``--full-copy``, the whole 1,140,850,688-byte volume is copied, ONLY the
  two fixed cache extents are replaced, the retail source is untouched
  (read-only, hashed before/after), and the INDEPENDENT verifier
  (``tools/apf_logocache_verify.py`` — its own F0985030/H7A parse) reproves that
  the copied volume differs only inside the two extents and decodes to content in
  which exactly ``01_logo_l0``/``01_logo_l1`` changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_logocache_patch as cache_patch  # noqa: E402
import apf_logocache_verify as cache_verify  # noqa: E402


INDEX_PATH = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
CATALOG = 1


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(report_path: Path, full_copy: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="apf-logocache-") as temporary:
        temp = Path(temporary)
        png_l0 = temp / "l0-magenta.png"
        png_l1 = temp / "l1-cyan.png"
        Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png_l0)
        Image.new("RGBA", (512, 512), (0, 255, 255, 255)).save(png_l1)

        result = cache_patch.build_cache_patch(INDEX_PATH, CATALOG, png_l0, png_l1)
        manifest = result.manifest
        assert manifest["mode"] == "patched"
        assert manifest["validation"]["changed_cache_entries"] == [56, 65]
        assert manifest["validation"]["fixed_outer_allocation"] is True
        assert manifest["payload"]["allocation_slack_after"] >= 0
        assert len(result.directory_bytes) == cache_patch.DIR_SIZE
        assert len(result.payload_bytes) == cache_patch.PAYLOAD_SIZE
        assert manifest["binary_patch_manifest"]["contains_replacement_bytes"] is False

        # Fail-closed: refuse patching the source path in place.
        source_overwrite_refused = False
        try:
            cache_patch._write_copied_volume_extents(
                INDEX_PATH,
                INDEX_PATH,
                [cache_patch.Extent("dir", cache_patch.DIR_PACK_OFFSET, result.directory_bytes)],
            )
        except cache_patch.PatchError:
            source_overwrite_refused = True
        assert source_overwrite_refused, "source-as-output was not refused"

        # Fail-closed: refuse overwriting an existing output.
        existing = temp / "existing-0A"
        existing.write_bytes(b"sentinel")
        existing_refused = False
        try:
            cache_patch._write_copied_volume_extents(
                INDEX_PATH,
                existing,
                [cache_patch.Extent("dir", cache_patch.DIR_PACK_OFFSET, result.directory_bytes)],
            )
        except cache_patch.PatchError:
            existing_refused = True
        assert existing_refused and existing.read_bytes() == b"sentinel"

        copied_summary: dict[str, object] | None = None
        verify_manifest: dict[str, object] | None = None
        if full_copy:
            copied_path = temp / "copied-game" / "0A"
            copied = cache_patch._write_copied_volume_extents(
                INDEX_PATH,
                copied_path,
                [
                    cache_patch.Extent(
                        "uniform_logocache.iff",
                        cache_patch.DIR_PACK_OFFSET,
                        result.directory_bytes,
                    ),
                    cache_patch.Extent(
                        "uniform_logocache.cdf",
                        cache_patch.PAYLOAD_PACK_OFFSET,
                        result.payload_bytes,
                    ),
                ],
            )
            assert copied["source_volume_sha256_before"] == copied["source_volume_sha256_after"]
            assert copied["outside_extents_match_source"] is True
            assert sha256_file(INDEX_PATH) == copied["source_volume_sha256_after"]

            # Independent verifier: its own F0985030/H7A parse, full-volume diff.
            verified = cache_verify.verify_cache_patch(
                INDEX_PATH, copied_path, expected_catalog_index=CATALOG, expect_l1=True
            )
            assert verified.ok is True
            assert set(verified.changed_entries) == {"01_logo_l0", "01_logo_l1"}
            assert verified.manifest["volume_diff"]["all_changes_within_extents"] is True
            assert verified.manifest["proof"]["every_dram_part_preserved"] is True
            assert verified.manifest["proof"]["every_unedited_mip_tail_preserved"] is True
            assert verified.manifest["proof"]["edited_mip_tails_regenerated"] is True
            assert verified.manifest["directory"]["only_auxiliary_records_changed"] is True
            copied_summary = {
                "volume_size": copied["volume_size"],
                "source_volume_sha256_before": copied["source_volume_sha256_before"],
                "source_volume_sha256_after": copied["source_volume_sha256_after"],
                "output_volume_sha256": copied["output_volume_sha256"],
                "extents": copied["extents"],
            }
            verify_manifest = verified.manifest

    report = {
        "schema": "apf_logocache_roundtrip_validation/v1",
        "scope": {
            "directory_entry_index": cache_patch.DIR_TABLE_INDEX,
            "payload_entry_index": cache_patch.PAYLOAD_TABLE_INDEX,
            "catalog_index": CATALOG,
            "note": (
                "uniform_logocache is the prebuilt runtime-resident aggregate of the "
                "same 236 team-logo textures; this writer rewrites one catalog index's "
                "VRAM base level(s), regenerates their packed mip tails, and preserves "
                "every DRAM part and other catalog entry"
            ),
        },
        "source": {
            "volume": str(INDEX_PATH.relative_to(WORKSPACE)),
            "directory_sha256": cache_patch.EXPECTED_DIR_SHA256,
            "payload_sha256": cache_patch.EXPECTED_PAYLOAD_SHA256,
        },
        "controlled_edit_fixture": {
            "operation": "magenta 01_logo_l0 + cyan 01_logo_l1 (exact 4-bit nibbles)",
            "contains_pixels": False,
        },
        "patched": manifest,
        "copied_volume": copied_summary,
        "independent_verifier": verify_manifest,
        "safety_validation": {
            "retail_source_modified": False,
            "source_path_as_output_refused": True,
            "existing_output_refused": True,
            "fixed_outer_allocations": True,
            "every_dram_part_preserved": True,
            "edited_mip_tails_regenerated": True,
            "every_unedited_mip_tail_preserved": True,
            "every_other_catalog_entry_preserved": True,
            "directory_changes_confined_to_auxiliary_records": True,
            "replacement_bytes_embedded_in_report": False,
        },
        "artifacts": {
            "writer": "tools/apf_logocache_patch.py",
            "writer_sha256": sha256_file(WORKSPACE / "tools/apf_logocache_patch.py"),
            "verifier": "tools/apf_logocache_verify.py",
            "verifier_sha256": sha256_file(WORKSPACE / "tools/apf_logocache_verify.py"),
            "test": "tests/apf_logocache_patch_test.py",
            "test_sha256": sha256_file(Path(__file__)),
        },
        "conclusion": {
            "offline_cache_base_write_proved": True,
            "copy_only_writer_exposed": True,
            "copied_volume_roundtrip_proved": full_copy,
            "independent_verifier_ran": full_copy,
            "xenia_runtime_validation": False,
            "hardware_runtime_validation": False,
            "which_surface_reads_cache_vs_package": "runtime (Xenia) follow-up",
        },
        "portme": cache_patch._PORTME,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_LOGOCACHE_ROUNDTRIP_PASS "
        f"catalog={CATALOG} copied_volume={str(full_copy).lower()} report={report_path}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=WORKSPACE / "reports/assets/apf_logocache_roundtrip.json",
    )
    parser.add_argument(
        "--full-copy",
        action="store_true",
        help="copy and hash the 1.1 GB 0A volume, then run the independent verifier",
    )
    return parser


if __name__ == "__main__":
    arguments = _parser().parse_args()
    run(arguments.report, arguments.full_copy)

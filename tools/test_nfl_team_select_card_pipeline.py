#!/usr/bin/env python3
"""Bounded tests for standalone NFL 2K5 Team Select card imports."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tempfile

from nfl_outer import parse_archive, read_entry_range
from nfl_team_select_card_fixture import fixture
from nfl_team_select_card_import_verify import verify
from nfl_team_select_card_png_import import (
    build_import,
    canonical_json,
    read_png,
    validate_rebuilt,
)
from nfl_team_select_card_targets import (
    REPORT_SHA256,
    TargetError,
    normalize,
    select_target,
)
from nfl_team_select_card_xiso_workflow import read_plan
from nfl_txtr import HEADER, encode_rgba_png


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
COMPATIBILITY = ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
FIXTURES = ROOT / "reports/assets/nfl2k5_team_select_card_fixtures"
BUNDLES = ROOT / "reports/assets"


def expect_failure(callback, exceptions: tuple[type[BaseException], ...],
                   label: str) -> None:
    try:
        callback()
    except exceptions:
        return
    raise AssertionError(f"{label} did not fail closed")


def source_span(archive, target) -> bytes:
    entry = archive.entries[target.outer_index]
    assert entry.name_id == target.outer_id and entry.size == target.outer_size
    return read_entry_range(archive, entry, target.chunk_offset, target.span_size)


def assert_preserved(archive, target, replacement: bytes) -> None:
    source = source_span(archive, target)
    fixed_prefix = HEADER.size + target.system_bytes
    assert len(source) == len(replacement) == target.span_size
    assert replacement[:fixed_prefix] == source[:fixed_prefix]
    assert replacement != source
    changes = [index for index, pair in enumerate(zip(source, replacement))
               if pair[0] != pair[1]]
    assert changes and min(changes) >= fixed_prefix and max(changes) < len(source)
    padding = read_entry_range(
        archive, archive.entries[target.outer_index],
        target.chunk_offset + target.span_size,
        target.slot_size - target.span_size,
    )
    assert padding == bytes(96)
    validate_rebuilt(
        replacement, target, source[:HEADER.size],
        source[HEADER.size:fixed_prefix],
    )


def audit_inventory() -> dict:
    payload = COMPATIBILITY.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == REPORT_SHA256
    report = json.loads(payload)
    assert report["schema"] == "nfl2k5_team_select_card_inventory/v1"
    assert report["summary"] == {
        "concrete_resource_count": 1902,
        "helm_128_count": 634,
        "helm_256_count": 634,
        "layout_class_counts": {
            "raw_p8_128x128_base1": 634,
            "raw_p8_256x256_base1": 1268,
        },
        "name_multiplicity_counts": {"1": 634, "2": 634},
        "rgba_multiplicity_counts": {
            "1": 944, "2": 174, "3": 62, "4": 28, "5": 16,
            "6": 8, "7": 12, "8": 8, "9": 4,
        },
        "selector_key_count": 634,
        "target_pack_counts": {"3": 1787, "4": 115},
        "unif_256_count": 634,
        "unique_rgba_count": 1256,
    }
    targets = report["targets"]
    assert len(targets) == len({row["selector"] for row in targets}) == 1902
    assert Counter(row["outer_index"] for row in targets) == {
        3102: 1268, 3105: 634,
    }
    assert Counter(Path(row["pack_path"]).name for row in targets) == {
        "3": 1787, "4": 115,
    }

    name_counts = Counter(row["name"] for row in targets)
    assert Counter(name_counts.values()) == {1: 634, 2: 634}
    assert all(count == (1 if name.startswith("unif_") else 2)
               for name, count in name_counts.items())

    logical = defaultdict(list)
    for row in targets:
        logical[(row["asset_code"], row["side_context"], row["style"])].append(row)
        assert row["compressed"] is False
        assert row["compression_magic"] == "0x00000000"
        assert row["overlap_scratch_bytes"] == 0
        assert row["vc_lz_stream_tag"] is None
        assert row["vc_lz_alias_constraint"] == "not_applicable_raw_resource"
        assert row["format_name"] == "P8" and row["mip_levels"] == 1
        assert row["depth"] == 1 and row["palette_entries"] == 256
        assert row["post_span_padding_all_zero"] is True
        assert row["post_span_padding_bytes"] == 96
        assert row["chunk_offset"] == row["chunk_index"] * row["slot_size"]
        assert row["span_size"] == row["stored_size"] + HEADER.size
        assert row["slot_size"] == row["span_size"] + 96
        assert row["video_bytes"] == row["width"] * row["height"] + 1024
        assert row["palette_offset"] == row["width"] * row["height"]
        assert 0 <= row["span_pack_offset"] and \
            row["span_pack_offset"] + row["span_size"] <= row["pack_size"]
    assert len(logical) == 634
    for rows in logical.values():
        assert {(row["family"], row["width"]) for row in rows} == {
            ("unif", 256), ("helm", 256), ("helm", 128),
        }
        helmets = [row for row in rows if row["family"] == "helm"]
        assert len(helmets) == 2 and helmets[0]["name"] == helmets[1]["name"]
    return report


def main() -> int:
    report = audit_inventory()
    assert normalize("unif", "09", "away", 0, 256) == \
        "unif:09:away:0:256"
    assert normalize("helm", "09", "away", 0, 128) == \
        "helm:09:away:0:128"
    invalid = (
        ("card", "09", "away", 0, 256),
        ("unif", "9", "away", 0, 256),
        ("unif", "09", "A", 0, 256),
        ("unif", "09", "away", -1, 256),
        ("unif", "09", "away", 100, 256),
        ("unif", "09", "away", True, 256),
        ("unif", "09", "away", 0, 128),
        ("helm", "09", "away", 0, 64),
    )
    for selector in invalid:
        expect_failure(
            lambda selector=selector: normalize(*selector),
            (TargetError,), f"invalid selector {selector}",
        )
    expect_failure(
        lambda: select_target("helm", "99", "home", 99, 256, COMPATIBILITY),
        (TargetError,), "absent selector",
    )

    archive = parse_archive(INDEX)
    canonical_cases = (
        (
            "unif", "detroit_away_style0_unif_nonretail.png",
            "nfl2k5_team_select_card_import_unif_a09_0",
            "5f11da8f27d45f71f86d4c6f93c15832a38fe2606fbf7705e1de5dc302ee0cec",
            66232,
        ),
        (
            "helm", "detroit_away_style0_helm_nonretail.png",
            "nfl2k5_team_select_card_import_helm_a09_0",
            "cd13e69f6d899ae9041326b29486f11c92664f21d4d7d34d62db1ea6da39da5c",
            65584,
        ),
    )
    verified = []
    selected = {}
    for family, png_name, bundle_name, expected_sha, expected_changes in canonical_cases:
        bundle = BUNDLES / bundle_name
        result = verify(
            INDEX, COMPATIBILITY, family, "09", "away", 0, 256,
            FIXTURES / png_name,
            bundle / "replacement.txtr.bin",
            bundle / "preview.png",
            bundle / "import.json",
        )
        assert result["replacement_sha256"] == expected_sha
        assert result["changed_bytes"] == expected_changes
        assert result["independently_reconstructed"] is True
        assert result["runtime_visibility_proved"] is False
        _, _, target = select_target(
            family, "09", "away", 0, 256, COMPATIBILITY)
        replacement = (bundle / "replacement.txtr.bin").read_bytes()
        assert hashlib.sha256(replacement).hexdigest() == expected_sha
        assert_preserved(archive, target, replacement)
        selected[family] = (target, replacement, bundle, png_name)
        verified.append(result["selector"])

    fixture_report = json.loads((FIXTURES / "fixtures.json").read_bytes())
    assert fixture_report["retail_artwork_included"] is False
    assert all(row["non_retail"] is True for row in fixture_report["fixtures"])

    # All adversarial files live under the project and are removed on exit.
    with tempfile.TemporaryDirectory(
            prefix=".nfl-team-select-card-test-", dir=ROOT) as name:
        temporary = Path(name)

        wrong_dimensions = temporary / "wrong_dimensions.png"
        wrong_dimensions.write_bytes(
            encode_rgba_png(128, 128, fixture("unif", 128, 128)))
        expect_failure(
            lambda: read_png(wrong_dimensions, (256, 256)),
            (ValueError,), "wrong PNG dimensions",
        )
        symlink = temporary / "fixture_link.png"
        symlink.symlink_to(wrong_dimensions.name)
        expect_failure(
            lambda: read_png(symlink, (128, 128)),
            (ValueError,), "symlink PNG",
        )

        compatibility_link = temporary / "compatibility_link.json"
        compatibility_link.symlink_to(COMPATIBILITY)
        expect_failure(
            lambda: select_target(
                "unif", "09", "away", 0, 256, compatibility_link),
            (TargetError,), "symlink compatibility report",
        )
        forged_compatibility = temporary / "forged_compatibility.json"
        forged_payload = bytearray(COMPATIBILITY.read_bytes())
        forged_payload[-2] = 0x20 if forged_payload[-2] != 0x20 else 0x09
        forged_compatibility.write_bytes(forged_payload)
        expect_failure(
            lambda: select_target(
                "unif", "09", "away", 0, 256, forged_compatibility),
            (TargetError,), "forged compatibility report",
        )
        index_link = temporary / "index_link"
        index_link.symlink_to(INDEX)
        expect_failure(
            lambda: build_import(
                index_link, COMPATIBILITY, "unif", "09", "away", 0, 256,
                FIXTURES / "detroit_away_style0_unif_nonretail.png"),
            (ValueError,), "symlink canonical index",
        )
        bool_plan = temporary / "bool_plan.json"
        bool_plan.write_bytes(canonical_json({
            "schema": "nfl2k5_team_select_card_plan/v1",
            "purpose": "invalid bool-as-int control",
            "edits": [{
                "family": "unif", "asset_code": "09", "side": "away",
                "style": True, "resolution": 256,
                "png": str(FIXTURES /
                           "detroit_away_style0_unif_nonretail.png"),
            }],
        }))
        expect_failure(
            lambda: read_plan(bool_plan),
            (ValueError,), "bool-as-int workflow plan",
        )

        # The canonical verifier must reject a changed P8/palette span even
        # when the original manifest and preview are retained.
        _, original, bundle, png_name = selected["unif"]
        tampered_dir = temporary / "tampered-bundle"
        tampered_dir.mkdir()
        tampered = bytearray(original)
        tampered[-1] ^= 0x01
        (tampered_dir / "replacement.txtr.bin").write_bytes(tampered)
        (tampered_dir / "preview.png").write_bytes(
            (bundle / "preview.png").read_bytes())
        (tampered_dir / "import.json").write_bytes(
            (bundle / "import.json").read_bytes())
        expect_failure(
            lambda: verify(
                INDEX, COMPATIBILITY, "unif", "09", "away", 0, 256,
                FIXTURES / png_name,
                tampered_dir / "replacement.txtr.bin",
                tampered_dir / "preview.png",
                tampered_dir / "import.json",
            ),
            (ValueError,), "tampered canonical replacement",
        )

        # A system-byte alteration is refused by the structural rebuilder,
        # independently of the canonical bundle comparison above.
        unif_target, unif_replacement, _, _ = selected["unif"]
        unif_source = source_span(archive, unif_target)
        system_tamper = bytearray(unif_replacement)
        system_tamper[HEADER.size + unif_target.system_bytes - 1] ^= 0x01
        expect_failure(
            lambda: validate_rebuilt(
                bytes(system_tamper), unif_target,
                unif_source[:HEADER.size],
                unif_source[HEADER.size:HEADER.size + unif_target.system_bytes],
            ),
            (ValueError,), "tampered system allocation",
        )

        # Exercise the second proved allocation class with deterministic,
        # non-retail 128x128 helmet art.
        helmet_128_png = temporary / "helm_128_nonretail.png"
        helmet_128_png.write_bytes(
            encode_rgba_png(128, 128, fixture("helm", 128, 128)))
        rebuilt_128, preview_128, manifest_128 = build_import(
            INDEX, COMPATIBILITY, "helm", "09", "away", 0, 128,
            helmet_128_png,
        )
        assert manifest_128["target"]["selector"] == "helm:09:away:0:128"
        assert manifest_128["target"]["name"] == "helm_a09_0"
        assert manifest_128["target"]["outer_index"] == 3105
        assert manifest_128["target"]["layout_class"] == \
            "raw_p8_128x128_base1"
        assert len(rebuilt_128) == 17568
        assert manifest_128["replacement"]["span_size"] == 17568
        assert manifest_128["template"]["compressed"] is False
        assert manifest_128["template"]["vc_lz_stream_tag"] is None
        assert manifest_128["claims"]["runtime_visibility_proved"] is False
        assert preview_128
        _, _, helmet_128_target = select_target(
            "helm", "09", "away", 0, 128, COMPATIBILITY)
        assert_preserved(archive, helmet_128_target, rebuilt_128)

    assert report["claims"]["runtime_visibility_proved_by_this_report"] is False
    print(
        "NFL_TEAM_SELECT_CARD_PIPELINE_TESTS_PASS "
        "resources=1902 selector_keys=634 layouts=2 "
        f"canonical={','.join(verified)} tamper_refused=true "
        "dimensions_refused=true symlink_refused=true system_preserved=true "
        "forged_refused=true plan_types_refused=true helm128=true "
        "xiso_opened=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

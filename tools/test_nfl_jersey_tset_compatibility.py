#!/usr/bin/env python3
"""Multi-target and fail-closed tests for compatible jersey PNG imports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile

from nfl_outer import parse_archive
from nfl_scene_probe import read_entry_range
import nfl2k5_uniform_jersey_png_workflow as workflow
import nfl2k5_uniform_jersey_png_workflow_verify as workflow_verify
from nfl_jersey_tset_dynamic_validate import DynamicValidationError, validate_dynamic_import
import nfl_jersey_tset_png_import as importer
from nfl_jersey_tset_targets import (
    TargetError,
    load_report,
    normalize_selector,
    select_target,
    target_from_row,
)
from nfl_txtr import HEADER, TxtrError
import nfl_tset_png_import_xiso_generic_patch as pinning
from test_nfl_tset_png_import_dynamic_workflow import noise_fixture, user_fixture
import nfl_uniform_color_xiso_direct_patch as common


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
COMPATIBILITY = ROOT / "reports/assets/nfl2k5_jersey_tset_compatibility.json"


def expect_failure(callback, exceptions: tuple[type[BaseException], ...], label: str) -> None:
    try:
        callback()
    except exceptions:
        return
    raise AssertionError(f"{label} did not fail closed")


def main() -> int:
    _, report, _ = load_report(COMPATIBILITY)
    assert report["summary"] == {
        "package_count": 634,
        "pair_count": 317,
        "home_count": 317,
        "away_count": 317,
        "layout_class_count": 1,
        "allocation_class_count": 346,
        "compatible_package_count": 634,
        "incompatible_package_count": 0,
        "compatible_home_count": 317,
        "compatible_away_count": 317,
        "pack_counts": {"9": 13, "A": 207, "B": 304, "C": 110},
        "stored_size_minimum": 31872,
        "stored_size_maximum": 126704,
        "all_spans_single_pack_segment": True,
        "all_source_xiso_spans_match": True,
    }
    targets = [target_from_row(report, row) for row in report["packages"]]
    assert len({target.selector for target in targets}) == 634
    assert sum(target.side == "H" for target in targets) == 317
    assert sum(target.side == "A" for target in targets) == 317
    assert min(target.stored_size for target in targets) == 31872
    assert max(target.stored_size for target in targets) == 126704
    assert {target.pack_name for target in targets} == {"9", "A", "B", "C"}
    assert normalize_selector("09", "home", 0) == ("09", "H", 0)
    assert normalize_selector("27", "away", 0) == ("27", "A", 0)
    for args in (("9", "H", 0), ("09", "X", 0), ("09", "H", -1)):
        expect_failure(
            lambda args=args: normalize_selector(*args),
            (TargetError,), f"invalid selector {args}",
        )
    expect_failure(
        lambda: select_target("98", "H", 99, COMPATIBILITY),
        (TargetError,), "absent selector",
    )

    archive = parse_archive(INDEX)
    fixture_payload = user_fixture()
    with tempfile.TemporaryDirectory(prefix="nfl-compatible-jersey-test-") as name:
        temporary = Path(name)
        clean = temporary / "multi_team_user.png"
        clean.write_bytes(fixture_payload)
        strict_mud = temporary / "strict_identity_mud.png"
        strict_mud.write_bytes(fixture_payload)
        cases = (
            ("00", "H", 0, None, "darken_60", "arizona_home"),
            ("27", "A", 0, strict_mud, "identity", "tampa_away"),
        )
        validated_rows = []
        for code, side, variant, mud, mode, stem in cases:
            *_, target = select_target(code, side, variant, COMPATIBILITY)
            span = temporary / f"{stem}.bin"
            manifest = temporary / f"{stem}.json"
            previews = temporary / f"{stem}-previews"
            result = importer.run(
                INDEX, INVENTORY, COMPATIBILITY, target,
                clean, mud, mode, span, manifest, previews,
            )
            source_span = read_entry_range(
                archive, archive.entries[target.outer_index],
                target.chunk_offset, target.span_size,
            )
            assert HEADER.unpack_from(source_span) == target.complete_header
            expected_header = list(target.complete_header)
            expected_header[5] = result["rebuild"]["rebuilt_overlap_scratch_bytes"]
            assert HEADER.unpack_from(span.read_bytes()) == tuple(expected_header)
            validated, evidence = validate_dynamic_import(
                target=target,
                compatibility_path=COMPATIBILITY,
                source_span=source_span,
                replacement_span=span.read_bytes(),
                import_manifest_payload=manifest.read_bytes(),
                clean_png_name=clean.name,
                clean_png_payload=clean.read_bytes(),
                mud_png_name=mud.name if mud else None,
                mud_png_payload=mud.read_bytes() if mud else None,
                preview_payloads={
                    child.name: child.read_bytes() for child in previews.iterdir()
                },
                replacement_span_name=span.name,
                import_manifest_name=manifest.name,
                preview_directory_name=previews.name,
            )
            assert validated.selector == target.selector
            assert validated.stored_size == target.stored_size
            assert validated.span_sha256 == result["rebuild"]["complete_span_sha256"]
            assert evidence["validated"]["preview_count"] == 12
            assert span.read_bytes()[:20] == source_span[:20]
            assert span.read_bytes()[24:HEADER.size] == source_span[24:HEADER.size]
            assert validated.loader_in_place_end_guard is True
            assert validated.loader_in_place_alias_guard is True
            validated_rows.append(validated)

            # The read-only verifier must continue to authenticate preserved
            # v2 artifacts without making the current writer or v3 dynamic
            # validator accept the old loader-overlap wrapper semantics.
            if target.selector == "00H0":
                legacy_span = source_span[:HEADER.size] + span.read_bytes()[HEADER.size:]
                legacy_span_sha = hashlib.sha256(legacy_span).hexdigest()
                legacy_manifest = json.loads(manifest.read_bytes())
                legacy_manifest["schema"] = workflow_verify.LEGACY_IMPORT_SCHEMA
                legacy_manifest["target"] = workflow_verify.legacy_import_target(target)
                legacy_rebuild = {
                    key: result["rebuild"][key]
                    for key in workflow_verify.LEGACY_REBUILD_INFO_FIELDS
                }
                legacy_rebuild["rebuilt_span_sha256"] = legacy_span_sha
                legacy_rebuild.update({
                    "decoded_roundtrip_sha256":
                        result["rebuild"]["decoded_roundtrip_sha256"],
                    "complete_span_sha256": legacy_span_sha,
                    "complete_span_size": target.span_size,
                    "fixed_span_fit": True,
                    "zero_padding_verified": True,
                })
                legacy_manifest["rebuild"] = legacy_rebuild
                legacy_manifest["claims"] = workflow_verify.legacy_import_claims()
                legacy_payload = (
                    json.dumps(legacy_manifest, indent=2, sort_keys=True) + "\n"
                ).encode()
                preview_payloads = {
                    child.name: child.read_bytes() for child in previews.iterdir()
                }
                legacy_validated, legacy_evidence = \
                    workflow_verify.validate_legacy_dynamic_import(
                        target=target,
                        compatibility_path=COMPATIBILITY,
                        source_span=source_span,
                        replacement_span=legacy_span,
                        import_manifest_payload=legacy_payload,
                        clean_png_name=clean.name,
                        clean_png_payload=clean.read_bytes(),
                        mud_png_name=mud.name if mud else None,
                        mud_png_payload=mud.read_bytes() if mud else None,
                        preview_payloads=preview_payloads,
                        replacement_span_name=span.name,
                        import_manifest_name=manifest.name,
                        preview_directory_name=previews.name,
                    )
                assert legacy_validated.span_sha256 == legacy_span_sha
                assert legacy_validated.loader_in_place_end_guard is False
                assert legacy_validated.loader_in_place_alias_guard is False
                assert set(legacy_evidence["validated"]) == set(
                    workflow_verify.LEGACY_VALIDATED_FIELDS
                )

                expect_failure(
                    lambda: validate_dynamic_import(
                        target=target,
                        compatibility_path=COMPATIBILITY,
                        source_span=source_span,
                        replacement_span=legacy_span,
                        import_manifest_payload=legacy_payload,
                        clean_png_name=clean.name,
                        clean_png_payload=clean.read_bytes(),
                        mud_png_name=mud.name if mud else None,
                        mud_png_payload=mud.read_bytes() if mud else None,
                        preview_payloads=preview_payloads,
                    ),
                    (DynamicValidationError,),
                    "v2 import through strict v3 validator",
                )
                forged_legacy = json.loads(legacy_payload)
                forged_legacy["claims"][
                    "target_specific_wrapper_and_allocation_preserved"
                ] = False
                forged_legacy_payload = (
                    json.dumps(forged_legacy, indent=2, sort_keys=True) + "\n"
                ).encode()
                expect_failure(
                    lambda: workflow_verify.validate_legacy_dynamic_import(
                        target=target,
                        compatibility_path=COMPATIBILITY,
                        source_span=source_span,
                        replacement_span=legacy_span,
                        import_manifest_payload=forged_legacy_payload,
                        clean_png_name=clean.name,
                        clean_png_payload=clean.read_bytes(),
                        mud_png_name=mud.name if mud else None,
                        mud_png_payload=mud.read_bytes() if mud else None,
                        preview_payloads=preview_payloads,
                    ),
                    (ValueError,),
                    "forged legacy v2 claims",
                )

            forged = json.loads(manifest.read_bytes())
            forged["target"]["outer_index"] += 1
            forged_payload = (json.dumps(forged, indent=2, sort_keys=True) + "\n").encode()
            expect_failure(
                lambda target=target, source_span=source_span, span=span,
                       forged_payload=forged_payload, mud=mud, previews=previews:
                    validate_dynamic_import(
                        target=target,
                        compatibility_path=COMPATIBILITY,
                        source_span=source_span,
                        replacement_span=span.read_bytes(),
                        import_manifest_payload=forged_payload,
                        clean_png_name=clean.name,
                        clean_png_payload=clean.read_bytes(),
                        mud_png_name=mud.name if mud else None,
                        mud_png_payload=mud.read_bytes() if mud else None,
                        preview_payloads={
                            child.name: child.read_bytes() for child in previews.iterdir()
                        },
                    ),
                (DynamicValidationError,), f"forged target manifest {target.selector}",
            )

        assert validated_rows[0].selector == "00H0"
        assert validated_rows[1].selector == "27A0"
        assert validated_rows[0].mud_source_kind == "derived_palette"
        assert validated_rows[1].mud_source_kind == "second_png_exact_shared_indices"
        assert validated_rows[0].stored_size != validated_rows[1].stored_size

        # The smallest allocation accepts compressible artwork while retaining
        # its distinct offset-bit/header profile, then refuses deterministic
        # high-entropy artwork before committing any outputs.
        *_, smallest = select_target("30", "H", 2, COMPATIBILITY)
        small_span = temporary / "smallest.bin"
        small_manifest = temporary / "smallest.json"
        small_previews = temporary / "smallest-previews"
        small_result = importer.run(
            INDEX, INVENTORY, COMPATIBILITY, smallest,
            clean, None, "darken_60", small_span, small_manifest, small_previews,
        )
        assert smallest.stored_size == 31872 and smallest.offset_bits == 10
        assert small_result["compression"]["encoded_bytes"] == 10397
        noise = temporary / "incompressible.png"
        noise.write_bytes(noise_fixture())
        oversize_span = temporary / "oversize.bin"
        oversize_manifest = temporary / "oversize.json"
        oversize_previews = temporary / "oversize-previews"
        expect_failure(
            lambda: importer.run(
                INDEX, INVENTORY, COMPATIBILITY, smallest,
                noise, None, "identity",
                oversize_span, oversize_manifest, oversize_previews,
            ),
            (TxtrError, importer.ImportError), "smallest allocation overflow",
        )
        assert not oversize_span.exists() and not oversize_manifest.exists() and \
            not oversize_previews.exists()

        # Three outer packages cross pack boundaries, but their early jersey
        # spans remain wholly inside the first segment and are selectable.
        for code, side, variant in (("01", "H", 11), ("25", "H", 3), ("24", "A", 10)):
            *_, boundary = select_target(code, side, variant, COMPATIBILITY)
            row = next(item for item in report["packages"]
                       if item["outer_index"] == boundary.outer_index)
            assert len(row["archive_segments"]) == 2 and len(row["span_segments"]) == 1

        symlink_report = temporary / "compatibility-link.json"
        symlink_report.symlink_to(COMPATIBILITY)
        expect_failure(
            lambda: select_target("00", "H", 0, symlink_report),
            (TargetError,), "symlink compatibility inventory",
        )
        forged_report = temporary / "forged-compatibility.json"
        damaged = bytearray(COMPATIBILITY.read_bytes())
        damaged[-2] ^= 1
        forged_report.write_bytes(damaged)
        expect_failure(
            lambda: select_target("00", "H", 0, forged_report),
            (TargetError,), "forged compatibility inventory",
        )

        sentinel = temporary / "existing-output.iso"
        sentinel.write_bytes(b"DO NOT OVERWRITE")
        before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        *_, arizona = select_target("00", "H", 0, COMPATIBILITY)
        expect_failure(
            lambda: workflow.run(
                source_xiso=temporary / "not-needed.iso",
                compatibility_path=COMPATIBILITY,
                target=arizona,
                clean_png=clean,
                mud_png=None,
                mud_mode="identity",
                output_xiso=sentinel,
                manifest_path=temporary / "unused.json",
                preview_dir=temporary / "unused-previews",
            ),
            (common.PatchError,), "generalized workflow O_EXCL preflight",
        )
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == before

        swap = temporary / "swap.bin"
        swap.write_bytes(b"first")
        pin = pinning.pin_small_file(swap, "swap fixture")
        swap.rename(temporary / "swap-old.bin")
        swap.write_bytes(b"second")
        expect_failure(
            lambda: pinning.verify_pin(pin, "swap fixture"),
            (common.PatchError,), "generalized path swap",
        )

    print(
        "NFL_JERSEY_TSET_COMPATIBILITY_TESTS_PASS packages=634 pairs=317 "
        "layouts=1 allocations=346 compatible=634 home=317 away=317 packs=4 "
        "fixtures=00H0,27A0 smallest=30H2 strict_mud=true forged_rejected=true "
        "oversize_refused=true boundaries=3 symlink_refused=true path_swap_refused=true "
        "o_excl=true legacy_v2_readonly=true v3_loader_alias_guard=true runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

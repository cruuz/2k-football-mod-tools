#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

artifact_dir=/media/noah/Storage/.codex-tmp/nfl2k5-actual-jersey-binding-away-loader-safe-20260711
run_dir=/media/noah/Storage/.codex-tmp/nfl2k5-away-cacheclear-xemu-20260711
historical_xiso="$artifact_dir/ESPN-NFL-2K5-Detroit-AWAY-CODEX-MOD-loader-safe.xiso.iso"
chain_spec="$root/reports/specs/nfl2k5_historical_xemu_hdd_chain.v1.json"
chain_spec_sha=9f017bda0ffb99dd5d9859b2a92fb7e82b30d901a684635449b37bcfe91cfe90
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

python3 -m py_compile \
  tools/nfl_away_loader_safe_virtual_xiso_verify.py \
  tools/nfl2k5_uniform_jersey_png_workflow_verify.py \
  tools/nfl_tset_loader_alias_audit.py \
  tools/nfl_qcow2_historical_chain_verify.py

python3 tests/test_nfl_away_loader_safe_virtual_xiso_verify.py
python3 -m unittest tests.test_nfl_qcow2_historical_chain_verify

workflow_mode=virtual
import_inputs_staged=private
if [[ -f "$historical_xiso" && ! -L "$historical_xiso" ]]; then
  workflow_mode=materialized
  import_inputs_staged=not_applicable
  PYTHONPATH=tools python3 tools/nfl2k5_uniform_jersey_png_workflow_verify.py \
    --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
    --output-xiso "$historical_xiso" \
    --manifest "$artifact_dir/workflow_manifest.json" \
    --target-code 09 \
    --target-side A \
    --target-variant 0 \
    --clean-png reports/assets/nfl2k5_lions_diagnostic_codex_mod.png \
    --previews "$artifact_dir/previews" \
    >"$tmp/workflow-verify.json"
else
  [[ ! -e "$historical_xiso" && ! -L "$historical_xiso" ]] || {
    echo "historical AWAY XISO path is not an absent or regular file" >&2
    exit 1
  }
  PYTHONPATH=tools python3 tools/nfl_away_loader_safe_virtual_xiso_verify.py \
    --source "$root/ESPN NFL 2K5 (USA).xiso.iso" \
    --historical-output "$historical_xiso" \
    --index "$root/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0" \
    --inventory "$root/reports/assets/nfl2k5_resource_chunks_v2.json" \
    --compatibility "$root/reports/assets/nfl2k5_jersey_tset_compatibility.json" \
    --clean-png "$root/reports/assets/nfl2k5_lions_diagnostic_codex_mod.png" \
    --historical-previews "$artifact_dir/previews" \
    >"$tmp/workflow-verify.json"
fi

python3 tools/nfl_qcow2_historical_chain_verify.py \
  --root "$root" \
  --spec "$chain_spec" \
  --spec-sha256 "$chain_spec_sha" \
  --leaf away_cacheclear \
  >"$tmp/qcow-chain.json"

PYTHONPATH=tools python3 - \
  "$root" "$tmp/workflow-verify.json" "$tmp/qcow-chain.json" "$tmp" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image
from nfl_away_loader_safe_virtual_xiso_verify import PinnedCopySession


root = Path(sys.argv[1])
evidence = PinnedCopySession(
    "away-runtime-evidence-", parent=Path(sys.argv[4])
)
workflow_path = evidence.add(
    Path(sys.argv[2]), "workflow-verify.json", expected_nlink=1
)
qcow_chain_path = evidence.add(
    Path(sys.argv[3]), "qcow-chain.json", expected_nlink=1
)
report_path = evidence.add(root / (
    "reports/assets/"
    "nfl2k5_actual_jersey_binding_away_loader_safe_xemu_runtime.json"
), "runtime-report.json", expected_size=39_977, expected_sha256=(
    "124acf5b6e718a114e2ee1c5e8b528393b91427cfbcc7ac506363223e21eecb7"
), expected_nlink=1)
doc_path = evidence.add(root / (
    "docs/research/"
    "nfl_actual_jersey_binding_away_loader_safe_xemu_runtime.md"
), "runtime-doc.md", expected_size=9_014, expected_sha256=(
    "8259a15b369535841043ee4ee63e7db0e5002100e5206d8047c99005820e4507"
), expected_nlink=1)
asset_sequence = 0


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def resolved(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def pinned(record: dict[str, object], expected: str | None = None) -> Path:
    global asset_sequence
    path = resolved(str(record["path"]))
    assert record["opened_read_only"] is True
    expected_hash = str(record["sha256"])
    if expected is not None:
        assert expected_hash == expected, path
    asset_sequence += 1
    return evidence.add(
        path,
        f"asset-{asset_sequence:02d}-{path.name}",
        expected_size=int(record["size"]),
        expected_sha256=expected_hash,
        expected_nlink=1,
    )


def image_record(record: dict[str, object], expected: str,
                 dimensions: list[int]) -> Path:
    path = pinned(record, expected)
    with Image.open(path) as image:
        assert image.format == "PNG", path
        assert list(image.size) == record["dimensions"] == dimensions, path
    return path


def color_audit(path: Path, crop: tuple[int, int, int, int]) \
        -> dict[str, object]:
    predicates = {
        "magenta": lambda r, g, b: r >= 180 and g <= 100 and b >= 150,
        "cyan": lambda r, g, b: r <= 100 and g >= 140 and b >= 140,
        "green": lambda r, g, b: r <= 100 and g >= 120 and b <= 100,
    }
    with Image.open(path) as source:
        image = source.convert("RGB")
        sample = image.crop(crop)
        raw_sha = hashlib.sha256(sample.tobytes()).hexdigest()
        x0, y0, x1, y1 = crop
        points = {name: [] for name in predicates}
        for y in range(y0, y1):
            for x in range(x0, x1):
                pixel = image.getpixel((x, y))
                for name, predicate in predicates.items():
                    if predicate(*pixel):
                        points[name].append((x, y))
    boxes = {
        name: None if not values else [
            min(x for x, _y in values),
            min(y for _x, y in values),
            max(x for x, _y in values) + 1,
            max(y for _x, y in values) + 1,
        ]
        for name, values in points.items()
    }
    return {
        "crop": list(crop),
        "crop_pixels": (crop[2] - crop[0]) * (crop[3] - crop[1]),
        "crop_rgb_sha256": raw_sha,
        "counts": {name: len(values) for name, values in points.items()},
        "bounding_boxes": boxes,
    }


def ocr(path: Path) -> str:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", "6"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return " ".join(result.stdout.decode("utf-8", "replace").upper().split())


assert digest(report_path) == (
    "124acf5b6e718a114e2ee1c5e8b528393b91427cfbcc7ac506363223e21eecb7"
)
assert digest(doc_path) == (
    "8259a15b369535841043ee4ee63e7db0e5002100e5206d8047c99005820e4507"
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_away_loader_safe_xemu_runtime/v1"
assert report["captured_at"] == "2026-07-11"
assert report["scope"] == {
    "title": "ESPN NFL 2K5",
    "platform": "original Xbox",
    "emulator": "xemu",
    "emulator_version": "0.8.135",
    "target": "09A0.IFF chunk 1 jersey00/jersey00_mud",
    "target_team": "Detroit Lions",
    "target_side": "AWAY",
    "uniform_selector": "Current Uniform",
    "hardware_validation": False,
    "legacy_negative_reports_modified": False,
}

artifact = report["artifact_under_test"]
assert artifact["xiso"]["sha256"] == (
    "5e8cf7c36c511878e5d5073fe96d757c1e21de08a360a5ca15f5ec7584242f2d"
)
assert artifact["xiso"]["size"] == 6_300_499_968
assert artifact["retail_source"]["sha256"] == (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
assert artifact["workflow_manifest"]["sha256"] == (
    "8113352fe422132d690f78a8de8ebb08a2947755861a5b0d60de558e7f364c42"
)
assert artifact["workflow_schema"] == "nfl2k5_uniform_jersey_png_workflow/v3"
assert artifact["target"] == {
    "logical_name": "09A0.IFF",
    "outer_index": 4002,
    "chunk_index": 1,
    "absolute_span_offset": 4_718_884_976,
    "span_size": 79_120,
    "stored_size": 79_088,
    "template_overlap_scratch_bytes": 16,
    "rebuilt_overlap_scratch_bytes": 56_816,
    "replacement_span_sha256": (
        "12b4ffd5f6926a3c404190262e0a8c19d6c3335cd046b9dfff79797a05016766"
    ),
}
assert artifact["patch"] == {
    "changed_bytes": 74_705,
    "changed_runs": 3_605,
    "all_other_xiso_bytes_identical": True,
    "xdvdfs_tree_and_extents_preserved": True,
}
assert artifact["loader_alias_revalidation"] == {
    "decoded_sha256": (
        "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e"
    ),
    "encoded_bytes": 22_285,
    "exact_minimum_scratch_bytes": 56_792,
    "wrapper_scratch_bytes": 56_816,
    "scratch_margin_bytes": 24,
    "source_start": 154_752,
    "matches_reference_decode": True,
    "first_unread_source_collision": None,
    "first_invalid_match": None,
}
assert artifact["unchanged_since_manifest_hash"] is True

isolation = report["isolation"]
overlay = isolation["hdd_overlay"]
assert overlay["sha256"] == (
    "43b6cea37aa0c5a02b50a822211842fe761da64cc2aaf75ecaad2fbdfe582ab4"
)
assert overlay["size"] == 983_040
assert overlay["format"] == "qcow2"
assert overlay["virtual_size"] == 8_589_934_592
assert overlay["cluster_size"] == 65_536
assert overlay["dirty"] is False
assert overlay["snapshot_count"] == 0
assert overlay["fresh_for_this_run"] is True
assert overlay["backing"]["sha256"] == (
    "96bf4b69a2b1b2f71ca9ceb7a989b40c23fde8b979ff686b8155a218bd1846e5"
)
cache = isolation["cache_partition_preparation"]
assert cache["backing_image_modified"] is False
expected_cache = {
    "X": (0x00080000, "still_zero_after_run", "00000000000000000000000000000000"),
    "Y": (0x2EE80000, "still_zero_after_run", "00000000000000000000000000000000"),
    "Z": (0x5DC80000, "reinitialized_during_run_with_new_serial",
          "46415458c0306e442000000001000000"),
}
assert len(cache["partitions"]) == 3
for row in cache["partitions"]:
    offset, state, prefix = expected_cache[row["partition"]]
    assert row["offset"] == offset
    assert row["postrun_state"] == state
    assert row["postrun_header_16_hex"] == prefix
    assert row["prelaunch_action"] == "zeroed_first_4096_bytes_in_fresh_overlay"

asset_hashes = {
    "coin-toss-live-diagnostic.png": "e9cf835d8693ce5f1a203bbeccfb9fc4f3e6cb2df425520b2016f2c4b07fff75",
    "lions-away-loader-safe-team-select-00.png": "5f83cbd1caf7bdab2d776ab697bfa9aef5096eaad7d2d644c462297594800927",
    "lions-away-loader-safe-team-select-01.png": "f7ffcd3f3d0117047428f5c6b0af07fcb2d5162d713dc27ab0eec2f812575a60",
    "lions-away-loader-safe-team-select-02.png": "c313f93b4358679b6c01c1b81ecee44c7cf3e6f9a721d638cc7212123a02190e",
    "lions-away-loader-safe-team-select-03.png": "3817d4bc8109e599c5ebec80621ad00b7d1c8c149d2ebaf36b2eb5162d09137a",
    "lions-away-loader-safe-team-select-04.png": "e63c60d74bb9feb94dd59fb938c5b1bc26b5c760dcbf4542fabf30cbac61dbc5",
    "lions-away-loader-safe-team-select-05.png": "b113ba3988cdfc29d83182276f861121404e108ad8af1c66aa04a5b66abc4f42",
    "lions-away-loader-safe-team-select-06.png": "05e9339d465e0c6ff751326cd0e18374436b5175ef6092e9e6dd9a6bb46b9d3a",
    "lions-away-loader-safe-team-select-07.png": "377272822ea880a7fb337fc7412d789ddc195ac436fb90224085b03ef05917bd",
    "lions-away-loader-safe-team-select-08.png": "5ea4b31ee260fb75da7e702ec459497275ed012e0922bb76bcee1f2fdac8a38d",
    "lions-away-loader-safe-team-select-09.png": "dad185935d1a9755e942ad55f7f4d9c1765d18b58d0584889b06464016c887e2",
    "lions-away-loader-safe-team-select-10.png": "f836f98b11c16bd3edda98848c96960d477c0cd9debba1a29e0b24a2c939af0b",
    "lions-away-loader-safe-team-select-11.png": "b9626ab50aba517304dd0ea94c439bf8bf8513ae0c4192a886b2f4be082e4889",
    "lions-away-loader-safe-team-select-12.png": "3497ac1ace195d587c2548292790b76f538ea3fc2c6ac5f59ab737161685dc10",
    "stadium-load-20s.png": "4f09a80030106663d7d26ccbbf600df4c82818e2b19a6ee7ebf41abb94bbdcc9",
    "team-select-contact.png": "c083555b624fc97c01510a9f7f0712ef2f606a8c2c7851012a98b2eea564bc48",
}
assert set(report["canonical_assets"]) == set(asset_hashes)
asset_paths = {}
for name, expected_hash in asset_hashes.items():
    dimensions = [1720, 912] if name == "team-select-contact.png" else [1280, 672]
    asset_paths[name] = image_record(
        report["canonical_assets"][name], expected_hash, dimensions
    )

coin = report["observations"]["coin_toss"]
detroit = color_audit(asset_paths["coin-toss-live-diagnostic.png"],
                      (810, 90, 1088, 350))
giants = color_audit(asset_paths["coin-toss-live-diagnostic.png"],
                     (210, 60, 600, 350))
assert detroit == coin["detroit_player_crop"]
assert detroit["crop_rgb_sha256"] == (
    "269b55591c6cca1941fa0f18c31452b0573367c1e802a99fa60deb509fb0063f"
)
assert detroit["counts"] == {"magenta": 630, "cyan": 564, "green": 26}
assert detroit["bounding_boxes"] == {
    "magenta": [855, 105, 1088, 315],
    "cyan": [841, 105, 1088, 309],
    "green": [906, 146, 988, 317],
}
assert giants == coin["giants_player_control_crop"]
assert giants["crop_rgb_sha256"] == (
    "9f9f91df0ab72cc5e0e7a2e51b46fc161024d5d37c6fb85b39c200010ba16d71"
)
assert giants["counts"] == {"magenta": 0, "cyan": 0, "green": 13}
coin_text = ocr(asset_paths["coin-toss-live-diagnostic.png"])
assert "COIN TOSS" in coin_text and "LIONS CALL IT" in coin_text
assert coin["diagnostic_visible_on_detroit_players"] is True
assert coin["live_player_rendering_visibility_proved"] is True

team = report["observations"]["team_select"]
assert team["frame_count"] == 13
assert team["all_frames_retail_looking"] is True
assert team["diagnostic_visible"] is False
assert team["interpretation"] == "separate or baked preview path"
expected_team_counts = [
    {"magenta": 0, "cyan": 2, "green": 0},
    {"magenta": 0, "cyan": 3, "green": 0},
    {"magenta": 0, "cyan": 0, "green": 0},
    {"magenta": 0, "cyan": 0, "green": 0},
    {"magenta": 0, "cyan": 1, "green": 0},
    {"magenta": 0, "cyan": 17, "green": 0},
    {"magenta": 0, "cyan": 10, "green": 0},
    {"magenta": 0, "cyan": 1, "green": 0},
    {"magenta": 0, "cyan": 1, "green": 0},
    {"magenta": 0, "cyan": 11, "green": 0},
    {"magenta": 0, "cyan": 20, "green": 0},
    {"magenta": 0, "cyan": 2, "green": 0},
    {"magenta": 0, "cyan": 0, "green": 0},
]
expected_team_crop_hashes = [
    "9124142cd78c225627fbbcf7b7d0675f1a86ff475946c391aa1870bc3ed360cd",
    "e6bd88ce35ea717cb601185e932f663e706ff3c9d1be1cd37bf073444def60ee",
    "b00e9268f9dfb5310856c16a93b742a421029994a0d8c9067dc9a85b34bf4cc8",
    "15548475c66780344651ee263f45f8bf0e4fc344d391c9bd2fe6f8b8c1658159",
    "f664fdc95c6c24d0e0727fcab57586cf85120f65864a7239b2e3b8ffbd3029e1",
    "a38f29a7856ceac4837415c6b12856858c2845ff7b9d3e65fa068a11651cddbd",
    "c3dcd67764e8fa566be5ab35845608d5280c49c29183c890fa5b6b8008003468",
    "e39c0351ed629d92166515bc6108c644efdb965c49251feea6a4d84fd0239058",
    "8fcc1bcbb6c2418af554bd76b152db50c2642705075e82e6ce12cee45c3fa7c3",
    "7cfdf2f6de1a3ec36c45e12c86c3f78f480f724d4ec2d60d189043c20038dcc4",
    "822a2197dcfc5a2cfd2da4b0e08bc4fd9bcd1e36ead068af7500dc083ba72e54",
    "9abc65a93b99f024163efd17914d76de2e125574db041436fb0a3f7d28d80f9d",
    "7bdd61d51ea99baa39760e1293fe181ed2894e90bd32a60dcc5469f48a854f35",
]
assert len(team["frames"]) == len(expected_team_counts) == 13
for index, row in enumerate(team["frames"]):
    name = f"lions-away-loader-safe-team-select-{index:02d}.png"
    measured = color_audit(asset_paths[name], (250, 155, 570, 440))
    assert row["index"] == index
    assert measured == row["lions_preview_crop"]
    assert measured["counts"] == expected_team_counts[index]
    assert measured["crop_rgb_sha256"] == expected_team_crop_hashes[index]
    assert row["diagnostic_visible"] is False
assert "TEAMSELECT" in ocr(asset_paths[
    "lions-away-loader-safe-team-select-00.png"
])

outcome = report["outcome"]
assert outcome["classification"] == (
    "positive_live_player_jersey_visibility_team_select_preview_separate"
)
assert outcome["modified_xiso_runtime_accepted"] is True
assert outcome["patched_09A0_chunk1_controls_live_detroit_away_jersey"] is True
assert outcome["team_select_uses_separate_or_baked_preview_path"] is True
assert outcome["diagnostic_visible_on_live_coin_toss_players"] is True
assert outcome["gameplay_after_coin_toss_captured"] is False
assert outcome["gameplay_visibility_claimed"] is False
assert outcome["hardware_validation"] is False
assert outcome["retail_source_modified"] is False
assert outcome["backing_hdd_modified"] is False
assert report["boundary"] == (
    "The nested display/session ended after the positive coin-toss capture. "
    "No gameplay frame after coin toss was captured, so this report makes no "
    "gameplay-visibility claim."
)

workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
common_workflow = {
    "changed_bytes": 74_705,
    "changed_runs": 3_605,
    "encoded_bytes": 22_285,
    "files": 19,
    "mips": 6,
    "outer_index": 4002,
    "pack": "B",
    "previews": 12,
    "replacement_span_sha256": (
        "12b4ffd5f6926a3c404190262e0a8c19d6c3335cd046b9dfff79797a05016766"
    ),
    "source_sha256": (
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
    ),
    "stored_size": 79_088,
    "target": "09A0",
    "zero_padding_bytes": 56_803,
}
if workflow["schema"] == "nfl2k5_uniform_jersey_png_workflow/v3":
    assert workflow == {
        **common_workflow,
        "output_sha256": (
            "5e8cf7c36c511878e5d5073fe96d757c1e21de08a360a5ca15f5ec7584242f2d"
        ),
        "runtime_visibility_proved": False,
        "schema": "nfl2k5_uniform_jersey_png_workflow/v3",
    }
else:
    assert workflow == {
        **common_workflow,
        "all_other_image_bytes_identical": True,
        "historical_output_path": (
            "/media/noah/Storage/.codex-tmp/"
            "nfl2k5-actual-jersey-binding-away-loader-safe-20260711/"
            "ESPN-NFL-2K5-Detroit-AWAY-CODEX-MOD-loader-safe.xiso.iso"
        ),
        "historical_runtime_reexecuted": False,
        "import_manifest_sha256": (
            "7ecc117d2b1fbaeecc5f6c94c5ee8faab80e94679bcdd1db85a509b3eb7c54a2"
        ),
        "output_materialized": False,
        "runtime_visibility_proved_by_reconstruction": False,
        "schema": "nfl2k5_away_loader_safe_virtual_xiso_verify/v1",
        "virtual_output_sha256": (
            "5e8cf7c36c511878e5d5073fe96d757c1e21de08a360a5ca15f5ec7584242f2d"
        ),
        "xdvdfs_tree_and_extents_preserved": True,
    }

chain = json.loads(qcow_chain_path.read_text(encoding="utf-8"))
assert chain["schema"] == "nfl2k5_historical_xemu_hdd_chain_verify/v1"
assert chain["leaf"] == "away_cacheclear"
assert chain["base_status"] == "missing"
assert chain["chain_complete"] is False
assert chain["guest_content_replayable"] is False
assert chain["historical_runtime_reexecuted"] is False
assert chain["missing_base_reconstructed"] is False
assert chain["substitution_allowed"] is False
assert [row["id"] for row in chain["layers"]] == [
    "away_cacheclear", "jersey_tset_controller_base"
]
assert chain["layers"][0]["pin"]["sha256"] == (
    "43b6cea37aa0c5a02b50a822211842fe761da64cc2aaf75ecaad2fbdfe582ab4"
)
assert chain["layers"][0]["header"]["backing_path"] == (
    "/media/noah/Storage/.codex-tmp/"
    "nfl2k5-xemu-jersey-tset-controller-20260711/xbox_hdd.qcow2"
)
assert chain["layers"][1]["pin"] is None

# The positive package supplements, rather than mutates, the preserved negative.
legacy_json = evidence.add(root / (
    "reports/assets/nfl2k5_actual_jersey_binding_away_xemu_runtime.json"
), "legacy-negative-report.json", expected_size=14_755, expected_sha256=(
    "5c798656eb6983d8a23d0dc8ff2736c931c089953f14acbeaaa9c052294c5ef1"
), expected_nlink=1)
legacy_doc = evidence.add(
    root / "docs/research/nfl_actual_jersey_binding_away_xemu_runtime.md",
    "legacy-negative-doc.md", expected_size=7_691, expected_sha256=(
        "0238721a9884065d3e3de75098fe9d7108d7aa83d6ad6210ac2ede0366f5070c"
    ), expected_nlink=1,
)
assert digest(legacy_json) == (
    "5c798656eb6983d8a23d0dc8ff2736c931c089953f14acbeaaa9c052294c5ef1"
)
assert digest(legacy_doc) == (
    "0238721a9884065d3e3de75098fe9d7108d7aa83d6ad6210ac2ede0366f5070c"
)

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "positive for live player rendering at the coin toss",
    "There is no post-coin-toss gameplay frame",
    "this report makes no gameplay-visibility claim",
    "Team Select formats and loads standalone 256×256 P8 cards",
    "wrapper scratch at `+0x14`: 56,816 bytes",
    "PORTME(gameplay)",
):
    assert phrase in doc, phrase
evidence.validate()
evidence.close()
PY

printf '%s\n' \
  "NFL_AWAY_LOADER_SAFE_XEMU_RUNTIME_VALIDATION_PASS scratch=56816 workflow_mode=$workflow_mode xiso_materialized=$([[ \"$workflow_mode\" == materialized ]] && echo true || echo false) import_inputs_staged=$import_inputs_staged previews_dirfd=closed evidence_copies=private team_frames=13 team_preview=retail historical_live_coin_toss=yes magenta=630 cyan=564 green=26 gameplay=no cache_overlay_layer=retained chain_complete=false guest_content_replayable=false historical_runtime_reexecuted=false originals_unchanged=yes legacy_untouched=yes"

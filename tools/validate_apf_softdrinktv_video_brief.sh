#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIEF="$ROOT/docs/research/apf_softdrinktv_video_brief.md"

# Publication-only gate: local reads and hashes. This deliberately does not
# decrypt/decompress an executable, launch an emulator, or write game data.
python3 - "$ROOT" "$BRIEF" <<'PY'
from __future__ import annotations

import csv
import hashlib
import json
import re
import struct
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1]).resolve()
brief = Path(sys.argv[2]).resolve()
if not brief.is_file():
    raise SystemExit(f"missing brief: {brief}")
text = brief.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load_json(rel: str):
    return json.loads((root / rel).read_text(encoding="utf-8"))


required_sections = (
    "## The publishable answer",
    "## Title and thumbnail",
    "## Evidence hierarchy",
    "## Claim ledger",
    "## 10-minute outline and exact narration",
    "## Exact visual and data handoff",
    "## Evidence files pinned for publication",
    "## Statements to avoid",
    "## Fact-check gate",
)
for section in required_sections:
    require(section in text, f"missing brief section: {section}")

# Every local Markdown citation must exist and remain inside the project.
local_targets: set[Path] = set()
for raw in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
    target = raw.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if target.startswith(("http://", "https://", "#")):
        continue
    target = target.split("#", 1)[0]
    path = (brief.parent / target).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"citation escapes project root: {raw}") from exc
    require(path.exists(), f"missing cited file: {raw} -> {path}")
    local_targets.add(path)
require(len(local_targets) >= 23, f"too few distinct local citations: {len(local_targets)}")

# Claim IDs and publication grades are an editorial contract.
expected_grades = {
    "C1": "A_PROVEN",
    "C2": "A_PROVEN",
    "C3": "A_PROVEN",
    "C4": "BOUNDARY_PROVEN",
    "C5": "A_PROVEN",
    "C6": "BOUNDARY_PROVEN",
    "C7": "A_PROVEN",
    "C8": "A_PROVEN",
    "C9": "A_PROVEN",
    "C10": "B_HISTORICAL_INFERENCE",
    "C11": "UNKNOWN",
}
found_grades: dict[str, str] = {}
for line in text.splitlines():
    match = re.match(r"^\| (C\d+) \| `([^`]+)` \|", line)
    if not match:
        continue
    claim_id, grade = match.groups()
    require(claim_id not in found_grades, f"duplicate claim ID: {claim_id}")
    found_grades[claim_id] = grade
require(found_grades == expected_grades, f"claim-grade drift: {found_grades!r}")

story_rows = sum(
    bool(re.match(r"^\| \d+:\d{2}–\d+:\d{2} \|", line))
    for line in text.splitlines()
)
require(story_rows == 11, f"outline row count drift: {story_rows} != 11")
for phrase in (
    "Keep the question mark",
    "statically orphaned retail content",
    "static-orphan candidate",
    "consecutive five-package SportsCenter wrapup run",
    "`fr.iff` → `franchise.iff`",
    "519 distinct `2K6`-tagged animation identifiers",
    "does **not** prove",
    "No recovered artifact says `NFL 2K6` as a product/build identity",
    "does not launch an emulator, execute game code, or modify game files",
):
    require(phrase in text, f"required publication boundary missing: {phrase!r}")

# Pin every report and selected image named in the publication hash tables.
expected_hashes = {
    "reports/cut_content/apf_nfl_lineage/lineage.json":
        "b263564991725d81ecd892727242f6821a2ce29d734eecdf7431a09f2984285b",
    "reports/cut_content/apf_nfl_lineage/manual_remnants.json":
        "9a27535464d4c08c7f580036e1950b31c61fec30797e1704513c7172daa6ddb2",
    "reports/cut_content/apf_nfl_lineage/reference_remnants.json":
        "7a79b04815a356787cd80814818d15a181f0633f6a24d7fe38b362fa63f97312",
    "reports/cut_content/apf_nfl_lineage/reference_runtime_owner.json":
        "e866c195da8d11521e9c5f6016f82a697b705cf7a43ac8c54d3e54a6647929c5",
    "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants.json":
        "66f4467e7b91bbc43e5c8b6648bc4d0ffd6e13f4153031eaee789a3cabe86dd6",
    "reports/cut_content/apf_nfl_lineage/pregameanims_static_ownership.json":
        "c3b43cdb4a0373ae81f751768bb98cea8baf1628c1209a190634d3d81a367546",
    "reports/cut_content/apf_nfl_lineage/wrapup_followup.json":
        "fa05d0ce2048d17512e65b6c13844576ae18813a9056f2a4f122acfd086e34ed",
    "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_lineage.json":
        "f2e348386dc4c042252f766f5cf4046760ff6723e101ac9ab84b27bee9a33f4d",
    "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime.json":
        "3861da491a2f033ef5fe2d9cb6d8c663b5a0c0c55fd16585a533f228700b918c",
    "reports/cut_content/apf_nfl_lineage/apf_xex_identity_card.png":
        "247d8431696bb91e3d6b9781a93b252df2378028e5bb16956cc5ca7ba28724f5",
    "reports/cut_content/apf_nfl_lineage/reference_remnants/apf_reference_nfl_shield.png":
        "52a551831eeeb95e4f8ebbf8ad871304185592948ff2d7fdbd22c3b198aeca60",
    "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants/pregame_conference_textures_nfl_vs_apf.png":
        "08f2ea42969704b3eaf6c150d7882dbabc723efb18538e3358a8080d564a1d6f",
    "reports/cut_content/apf_nfl_lineage/sc_logo_2k5_vs_apf.png":
        "11d6823fa1043481aac311dd85266ee2daae63a0caacd07cda147d1448eab147",
    "reports/cut_content/apf_nfl_lineage/berman_2k5_vs_apf.png":
        "af12e6968c11a7c24ebb1ea8e0ced360877bb9da8a901681b58f2770552aa3b5",
    "reports/cut_content/apf_nfl_lineage/apf_franchise_texture_contact_sheet.png":
        "06be6b667fe11f6e1c0982d2fde672f3ca1283d921095eea545abf341e324e2d",
    "reports/cut_content/apf_nfl_lineage/draft_logo_2k5_vs_apf.png":
        "6c24dd17325c95f7d73d7c30a47a239db365d2a2789f2fe54ddb85198ae0cf3f",
    "reports/cut_content/apf_nfl_lineage/apf_franchise_runtime_identity_card.png":
        "bf3ca33f2113172d490a3718a55fcc0db4d0c4a3a0144146a081d4426157c5ef",
    "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_identity_card.png":
        "e48c0bc42de1ae3e91015bd5ee0677a31e235e535bef2b32540b246b3b9aa357",
}
for rel, expected in expected_hashes.items():
    path = root / rel
    require(path.is_file(), f"missing pinned artifact: {rel}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    require(actual == expected, f"hash drift for {rel}: {actual} != {expected}")
    require(expected in text, f"pinned hash absent from brief: {rel}")

expected_png_dimensions = {
    "reports/cut_content/apf_nfl_lineage/apf_xex_identity_card.png": (1920, 1080),
    "reports/cut_content/apf_nfl_lineage/reference_remnants/apf_reference_nfl_shield.png": (128, 128),
    "reports/cut_content/apf_nfl_lineage/pregame_conference_remnants/pregame_conference_textures_nfl_vs_apf.png": (1024, 512),
    "reports/cut_content/apf_nfl_lineage/sc_logo_2k5_vs_apf.png": (1984, 642),
    "reports/cut_content/apf_nfl_lineage/berman_2k5_vs_apf.png": (1984, 634),
    "reports/cut_content/apf_nfl_lineage/apf_franchise_texture_contact_sheet.png": (1272, 848),
    "reports/cut_content/apf_nfl_lineage/draft_logo_2k5_vs_apf.png": (1104, 603),
    "reports/cut_content/apf_nfl_lineage/apf_franchise_runtime_identity_card.png": (1920, 1080),
    "reports/cut_content/apf_nfl_lineage/apf_2k6_animation_identity_card.png": (1920, 1080),
}
for rel, expected in expected_png_dimensions.items():
    data = (root / rel).read_bytes()
    require(data[:8] == b"\x89PNG\r\n\x1a\n", f"not PNG: {rel}")
    require(data[12:16] == b"IHDR", f"missing PNG IHDR: {rel}")
    actual = struct.unpack(">II", data[16:24])
    require(actual == expected, f"PNG dimension drift for {rel}: {actual} != {expected}")

# Quantitative claim audit against the pinned machine reports.
lineage = load_json("reports/cut_content/apf_nfl_lineage/lineage.json")
summary = lineage["summary"]
identity = lineage["apf_executable_identity"]
require(identity["original_pe_name"] == "nfl_clean_opt_submission_ready.xex", "C1 PE name drift")
require(identity["pdb_path"].endswith(r"XENON\NFL\CLEAN_OPT\default.xex.pdb"), "C1 PDB path drift")
require(identity["embedded_vcsports_nfl_code_path_count"] == 24, "C1 source-path count drift")
for key, expected in {
    "franchise_direct_shared_name_type_count": 77,
    "franchise_exact_whole_layout_sequence_count": 21,
    "franchise_exact_ordered_string_record_count": 1492,
    "franchise_exact_string_pool_entry_count": 1106,
    "runtime_reachability_proved": False,
    "nfl_2k6_identity_proved": False,
}.items():
    require(summary.get(key) == expected, f"lineage fact drift: {key}")

manual = load_json("reports/cut_content/apf_nfl_lineage/manual_remnants.json")
ml = manual["manual_lineage"]
require(ml["apf_string_slot_count"] == ml["nfl_string_slot_count"] == 1553, "C2 manual slot drift")
require(ml["markup_normalized_exact_ordered_string_matches"] == 1544, "C2 normalized match drift")
require(ml["authored_difference_string_count"] == 9, "C2 authored edit drift")
require(ml["authored_difference_class_counts"]["weekly_prep_hours_60_to_40"] == 3, "C2 Weekly Prep drift")
me = manual["executable_evidence"]
require(me["compiled_page_table_count"] == 15, "C2 compiled page-table drift")
require(me["compiled_page_table_exactly_names_xenon_1_through_15"] is True, "C2 xenon table drift")
require(me["retail_frontend_route_to_initializer_proved"] is False, "C2 route boundary drift")

reference = load_json("reports/cut_content/apf_nfl_lineage/reference_remnants.json")
rt = reference["cross_title_text_lineage"]
require(reference["cross_title_shield_art"]["dimensions"] == [128, 128], "C3 shield dimension drift")
require(rt["apf_printable_utf16_string_occurrences"] == 988, "C3 APF string count drift")
require(rt["exact_ordered_string_occurrence_matches"] == 987, "C3 ordered match drift")
require(rt["removed_nfl_glossary_entry_count"] == 13, "C3 glossary removal drift")
require(rt["selectively_modified_pair_count"] == 1, "C3 edited-pair drift")

reference_owner = load_json("reports/cut_content/apf_nfl_lineage/reference_runtime_owner.json")
apf_reference = reference_owner["apf"]
require(apf_reference["classification"] == "statically_orphaned_retail_content", "C4 classification drift")
require(apf_reference["generic_refr_handler"]["registered_during_normal_boot"] is True, "C4 generic boot registration drift")
require(apf_reference["reference_owner_code"]["loader_static_incoming_refs"] == 0, "C4 loader-owner drift")
require(apf_reference["serialized_assets"]["pack_count"] == 4, "C4 pack-scan drift")

pregame = load_json("reports/cut_content/apf_nfl_lineage/pregame_conference_remnants.json")
require(pregame["filename_identity"]["uppercase_name"] == "PREGAMEANIMS.IFF", "C5 filename drift")
textures = pregame["conference_texture_lineage"]
require(len(textures) == 4, "C5 texture count drift")
require(min(row["minimum_channel_correlation"] for row in textures) > 0.9726, "C5 texture correlation drift")
require(len(pregame["conference_geometry_lineage"]) == 3, "C5 geometry count drift")
require(pregame["mrks_lineage"]["selected_exact_identifier_count"] == 13, "C5 MRKS identifier drift")

pregame_owner = load_json("reports/cut_content/apf_nfl_lineage/pregameanims_static_ownership.json")
pc = pregame_owner["conclusion"]
require(pc["apf_classification"] == "static_orphan_candidate_with_generic_mrks_support", "C6 classification drift")
require(pc["nfl_classification"] == "compiled_pregame_package_lifecycle_owner", "C6 NFL lifecycle drift")
require(pc["runtime_reachability_disproved_in_apf"] is False, "C6 overclaim boundary drift")
require(pc["runtime_reachability_proved_in_apf"] is False, "C6 reachability boundary drift")

wrapup = load_json("reports/cut_content/apf_nfl_lineage/wrapup_followup.json")
cluster = wrapup["wrapup_cluster"]
require(cluster["nfl_outer_indices_are_consecutive_17_through_21"] is True, "C7 consecutive cluster drift")
require(cluster["all_five_have_exact_cross_platform_filename_hash_pairs"] is True, "C7 package-pair drift")
require([row["role"] for row in cluster["packages"]] == ["awards", "show", "director", "intro", "outro"], "C7 role list drift")
require(cluster["awards_package"]["runtime_owner_proved"] is False, "C7 runtime boundary drift")
fr = wrapup["franchise_filename_resolution"]
require(fr["nfl_filename"] == "fr.iff", "C8 NFL filename drift")
require(fr["apf_descendant_filename"] == "franchise.iff", "C8 APF filename drift")
require(fr["nfl_xbe_utf16le_literal_count"] == 1, "C8 XBE literal drift")

anim_lineage = load_json("reports/cut_content/apf_nfl_lineage/apf_2k6_animation_lineage.json")["result"]
for key, expected in {
    "apf_2k6_unique_identifier_count": 519,
    "apf_2k6_pointer_reference_total": 597,
    "apf_2k6_unique_animation_filename_count": 225,
    "formal_nfl_2k6_product_identity_proved": False,
    "runtime_consumption_of_every_identifier_proved": False,
}.items():
    require(anim_lineage.get(key) == expected, f"C9 lineage drift: {key}")
anim_runtime = load_json("reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime.json")["result"]
for key, expected in {
    "all_two_k6_mappings_have_concrete_motion_roots": True,
    "two_k6_unique_single_mocap_root_count": 597,
    "two_k6_selector_linked_identifier_count": 149,
    "two_k6_selector_target_group_count": 49,
    "runtime_execution_observed": False,
    "worked_movement_config_reached_by_recovered_direct_lookup_calls": False,
}.items():
    require(anim_runtime.get(key) == expected, f"C9 runtime drift: {key}")

# Upstream claim ledgers must keep their own grades and explicit boundaries.
expected_ledger_grades = {
    "reports/cut_content/apf_nfl_lineage/manual_remnants_video_claims.tsv":
        ["A_proven", "A_proven", "boundary"],
    "reports/cut_content/apf_nfl_lineage/reference_remnants_video_claims.tsv":
        ["A_proven", "A_proven", "boundary"],
    "reports/cut_content/apf_nfl_lineage/pregame_conference_video_claims.tsv":
        ["A_proven", "A_proven", "boundary"],
    "reports/cut_content/apf_nfl_lineage/pregameanims_static_ownership_claims.tsv":
        ["A_proven", "A_proven", "A_proven", "boundary"],
    "reports/cut_content/apf_nfl_lineage/wrapup_followup_video_claims.tsv":
        ["A_PROVEN", "A_PROVEN", "A_PROVEN", "B_STRUCTURAL_LINEAGE", "BOUNDARY_PROVEN"],
}
for rel, expected in expected_ledger_grades.items():
    with (root / rel).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    grades = [row["grade"] for row in rows]
    require(grades == expected, f"upstream claim-grade drift for {rel}: {grades!r}")
    require(all(row.get("boundary", "").strip() for row in rows), f"missing claim boundary in {rel}")

# README should expose exactly one canonical brief link, without copying the
# research into a second document.
readme = (root / "README.md").read_text(encoding="utf-8")
require(readme.count("docs/research/apf_softdrinktv_video_brief.md") == 1, "README brief-link count must be one")
require(readme.count("validate_apf_softdrinktv_video_brief.sh") == 1, "README validator-command count must be one")

print(
    "APF_SOFTDRINKTV_VIDEO_BRIEF_VALIDATION_PASS "
    f"claims={len(found_grades)} outline_rows={story_rows} "
    f"citations={len(local_targets)} pinned={len(expected_hashes)} "
    f"visuals={len(expected_png_dimensions)} local_read_only=true"
)
PY

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$ROOT" <<'PY'
import csv
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])

def require(condition, message):
    if not condition:
        raise SystemExit(f"NFL_UNIF_COLOR_OWNERSHIP_VALIDATION_FAIL: {message}")

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

expected_sources = {
    root / "ESPN NFL 2K5 (USA).xiso.iso":
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
    root / "extracted/ESPN NFL 2K5 (USA)/default.xbe":
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9",
    root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0":
        "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
    root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/A":
        "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
    root / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/B":
        "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
}
for path, expected in expected_sources.items():
    require(path.is_file(), f"missing source {path}")
    require(sha256(path) == expected, f"source hash mismatch {path}")

report_path = root / "reports/assets/nfl2k5_unif_color_ownership.json"
report = json.loads(report_path.read_text())
require(report["schema"] == "nfl2k5_unif_color_ownership_v1", "schema mismatch")
require(report["scope"]["binary_modified"] is False, "scope must remain read-only")
require(report["scope"]["emulator_or_controller_touched"] is False,
        "scope must not claim emulator/controller use")
require(report["existing_runtime_context"]["three_byte_donor_xiso_sha256"] ==
        "2f0ce4d4ac26c864a274c47f7147c45df1ecbf22d05d169f3940706eb64f3702",
        "existing donor context mismatch")
require("not a jersey-color change" in
        report["existing_runtime_context"]["bounded_result"],
        "existing runtime claim is not bounded")

for key in ("script", "trace", "pseudo_c"):
    item = report["ghidra_evidence"][key]
    path = root / item["path"]
    require(path.is_file(), f"missing Ghidra evidence {path}")
    require(sha256(path) == item["sha256"], f"Ghidra evidence hash mismatch {key}")

trace = (root / report["ghidra_evidence"]["trace"]["path"]).read_text()
for needle in (
    "0x0008E850 owner=0x0008E850:FUN_0008e850 refs=0x0008EACD",
    "0x0008E860 owner=0x0008E860:FUN_0008e860 refs=0x0008F667",
    "index=23 slot=0x004EEEC4 pointer=0x00E64C98 text=HI_turtleneck",
    "index=24 slot=0x004EEEC8 pointer=0x00E64CB4 text=UNIF_jersey",
    "0x004EDB54=0x3F2AC083 float=0.667",
    "0x00E632D8 text=facemask",
    "0x00E6334C text=HOME",
    "0x00E63368 text=AWAY",
    "0x0008EB05 CALL 0x0008e470",
    "0x0008EB2B CALL 0x0008e470",
    "0x0008F696 CALL 0x0008e470",
):
    require(needle in trace, f"trace missing {needle}")

with (root / "reports/assets/nfl2k5_uniform_packages.tsv").open(newline="") as handle:
    rows = {row["logical_name"]: row for row in csv.DictReader(handle, delimiter="\t")
            if row["logical_name"] in {"09H0.IFF", "25H0.IFF"}}
require(set(rows) == {"09H0.IFF", "25H0.IFF"}, "probe rows missing")
target = rows["09H0.IFF"]
donor = rows["25H0.IFF"]
require((target["color_word_0"], target["color_word_1"]) ==
        ("0xff000000", "0xff385aaf"), "Detroit pair mismatch")
require((donor["color_word_0"], donor["color_word_1"]) ==
        ("0xff9c1622", "0xff88172d"), "49ers pair mismatch")
for field in ("side_context", "style_display", "selector_08", "selector_0c",
              "scale_10", "flag_14"):
    require(target[field] == donor[field], f"donor shape mismatch at {field}")

target_body = bytes.fromhex(target["unif_raw_hex"])
donor_body = bytes.fromhex(donor["unif_raw_hex"])
require(len(target_body) == len(donor_body) == 0x50, "Unif body size mismatch")
diffs = [index for index, pair in enumerate(zip(target_body, donor_body))
         if pair[0] != pair[1]]
require(diffs == [0x30, 0x31, 0x32, 0x34, 0x35, 0x36],
        f"unexpected donor diff offsets {diffs}")
require(hashlib.sha256(donor_body).hexdigest() ==
        "8d176356012bcb041035fa0b6eb992d67b701e2fab3a7e88d6547e3da195b74a",
        "donor body hash mismatch")

with (root / "ESPN NFL 2K5 (USA).xiso.iso").open("rb") as handle:
    handle.seek(0x12AB4F850)
    retail_pair = handle.read(8)
require(retail_pair.hex() == "000000ffaf5a38ff", "direct XISO retail pair mismatch")
expected_changed = [
    (5011470416, 0x00, 0x22),
    (5011470417, 0x00, 0x16),
    (5011470418, 0x00, 0x9C),
    (5011470420, 0xAF, 0x2D),
    (5011470421, 0x5A, 0x17),
    (5011470422, 0x38, 0x88),
]
reported_changed = report["retail_probe"]["result"]["direct_xiso_changed_bytes"]
require([(row["offset_decimal"], int(row["before"], 16), int(row["after"], 16))
         for row in reported_changed] == expected_changed, "reported byte diff mismatch")
require(report["retail_probe"]["result"]["resulting_target_body_byte_identical_to_donor"]
        is True, "donor identity not asserted")
require(report["color_word_0"]["semantic_owner"] ==
        "facemask/faceshield packed tint", "word 0 ownership mismatch")
require(report["color_word_1"]["material_name"] == "HI_turtleneck",
        "word 1 ownership mismatch")
require(report["jersey_diffuse_conclusion"]["color_word_0_reaches_UNIF_jersey"]
        is False, "word 0 jersey claim mismatch")
require(report["jersey_diffuse_conclusion"]["color_word_1_reaches_UNIF_jersey"]
        is False, "word 1 jersey claim mismatch")
require(len(report["portme"]) >= 5 and all(item.startswith("PORTME:")
        for item in report["portme"]), "PORTME ledger incomplete")

doc = (root / "docs/research/nfl_unif_color_ownership.md").read_text()
for needle in ("`color_word_0` is the facemask", "`HI_turtleneck`",
               "0x12AB4F850", "Remaining `PORTME`s"):
    require(needle in doc, f"documentation missing {needle}")

print("NFL_UNIF_COLOR_OWNERSHIP_VALIDATION_PASS "
      "word0=facemask word1=HI_turtleneck probe=49ers_current_home "
      "changed_bytes=6 donor_body_exact=true originals_unchanged=true title_executed=false")
PY

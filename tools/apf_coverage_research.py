#!/usr/bin/env python3
"""Reproduce the derived APF coverage evidence; never emit retail byte arrays.

Inputs are pinned decompressed flat images, a generated function comparison,
and the user's read-only 0A/0B archive. Outputs are numeric tables, hashes,
addresses, authored labels, and static evidence grades.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.apf_coverage_function_diff import Image, Function, sha
from tools.apf_coverage_tu_extract import TU_PE_SHA256
from mod_editor.core import apf2k8_coverage_tuning as coverage

BASE_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"

# Zero size means use validated .pdata; nonzero sizes are manually checked
# leaf spans ending at their return, rather than the preceding .pdata record.
SITES = (
    (0x84A87958, 40, "opcode_codec_row", "A_PROVEN"),
    (0x84A87980, 0, "descriptor_chain_length_loop", "A_PROVEN"),
    (0x84A94030, 20, "lane_cm_lookup", "A_PROVEN"),
    (0x84A94048, 32, "mirrored_lane_lookup", "A_PROVEN"),
    (0x84A94068, 12, "codec_table_address", "A_PROVEN"),
    (0x84A94098, 0, "generic_node_decode", "A_PROVEN"),
    (0x84A940F0, 0, "decoded_operand_lookup", "A_PROVEN"),
    (0x84A92148, 360, "zone_decode", "A_PROVEN"),
    (0x84A922B0, 344, "zone_encode", "A_PROVEN"),
    (0x84A92410, 316, "man_decode", "A_PROVEN"),
    (0x8482DB10, 0, "assignment_opcode_search", "A_PROVEN"),
    (0x8482DC00, 0, "assignment_float_operand", "A_PROVEN"),
    (0x8482DCA0, 0, "assignment_integer_operand", "A_PROVEN"),
    (0x8482DFA8, 0, "decode_current_assignment", "A_PROVEN"),
    (0x8482E180, 144, "assignment_position_transform", "A_PROVEN"),
    (0x847D0278, 272, "formation_alignment_cm", "A_PROVEN"),
    (0x847F0A08, 0, "construct_zone_records", "A_PROVEN"),
    (0x847F5CB8, 0, "initialize_zone_state", "A_PROVEN"),
    (0x847F4ED8, 0, "initial_zone_update", "A_PROVEN"),
    (0x847F43C8, 0, "steady_zone_update", "A_PROVEN"),
    (0x847EA128, 56, "time_gated_zone_padding", "A_PROVEN"),
    (0x847EA7F8, 268, "lateral_landmark_shift_and_clamp", "A_PROVEN"),
    (0x847EA7A0, 0, "slider_seven_curve", "A_PROVEN"),
    (0x847ECD48, 0, "directional_radius", "A_PROVEN"),
    (0x847ECE78, 0, "limit_displacement_to_radius", "A_PROVEN"),
    (0x847EB628, 328, "deep_no_outside_threat_adjustment", "A_PROVEN"),
    (0x847EE0C0, 0, "select_two_zone_threats", "A_PROVEN"),
    (0x847EE8C8, 0, "assign_receivers_with_man_opcode_test", "A_PROVEN"),
    (0x847EED38, 0, "coverage_assignment_orchestration", "B_INFERENCE"),
    (0x847EC170, 0, "coverage_rating_dependent_delay", "A_PROVEN"),
    (0x847EC4E0, 0, "threat_response_geometry", "B_INFERENCE"),
    (0x847C0DB0, 12, "coverage_rating_index_twenty", "A_PROVEN"),
    (0x847CBED8, 0, "roster_coverage_byte_getter", "A_PROVEN"),
    (0x847C1590, 0, "refresh_cached_effective_rating", "A_PROVEN"),
    (0x847CCC28, 0, "effective_rating_and_slider_adjustment", "A_PROVEN"),
    (0x847CCE48, 0, "populate_effective_rating_rows", "A_PROVEN"),
    (0x847CDD50, 0, "shared_ratings_contest_changed_in_tu", "A_PROVEN"),
    (0x847CE048, 0, "ratings_contest_caller_changed_in_tu", "A_PROVEN"),
    (0x848B9738, 0, "strength_break_tackle_tackle_contest", "B_INFERENCE"),
    (0x848F1CD8, 0, "composure_pass_rush_proximity_sum", "A_PROVEN"),
    (0x847F6430, 12, "tackle_rating_index_seventeen", "A_PROVEN"),
    (0x847F6440, 12, "run_coverage_rating_index_nineteen", "A_PROVEN"),
)


def direct_calls(im, f):
    result = set()
    for a in range(f.start, f.start + f.size, 4):
        w = im.word(a)
        if w >> 26 == 18:
            d = w & 0x3FFFFFC
            if d & 0x2000000:
                d -= 0x4000000
            target = (d if w & 2 else a + d) & 0xFFFFFFFF
            if not f.start <= target < f.start + f.size:
                result.add(target)
    return sorted(result)


def build_evidence(base, tu, diff, body):
    if sha(base.data) != BASE_PE_SHA256 or sha(tu.data) != TU_PE_SHA256:
        raise ValueError("unsupported flat PE pin")
    if diff["base"]["sha256"] != sha(base.data) or diff["tu"]["sha256"] != sha(tu.data):
        raise ValueError("function diff does not belong to these images")
    fs = base.functions()
    starts = [f.start for f in fs]
    fmap = {f.start: f for f in fs}
    pairs = {int(r["base_va"], 16): r for r in diff["functions"]}
    sites = []
    for address, size, label, grade in SITES:
        if size == 0:
            if address not in fmap:
                raise ValueError(f"site {address:#x} needs manually verified leaf bounds")
            f = fmap[address]
            row = dict(pairs[address])
        else:
            f = Function(address, size, "manually_checked_leaf")
            predecessor = fs[bisect_right(starts, address) - 1]
            prior = pairs[predecessor.start]
            target = int(prior["tu_va"], 16) + prior["tu_size"] + address - predecessor.start - predecessor.size
            g = Function(target, size, f.source)
            if base.normalized(f) != tu.normalized(g):
                raise ValueError(f"manual leaf {address:#x} does not retain its shape at {target:#x}")
            a, b = base.read(address, size), tu.read(target, size)
            row = {"base_va": f"0x{address:08x}", "tu_va": f"0x{target:08x}",
                   "base_size": size, "tu_size": size, "base_file_offset": address - base.base,
                   "tu_file_offset": target - tu.base, "base_sha256": sha(a), "tu_sha256": sha(b),
                   "comparison": "identical" if a == b else "normalized_equal",
                   "alignment": "manually_checked_leaf_between_pdata_anchors", "alignment_grade": "B_INFERENCE"}
        row.update(label=label, evidence_grade=grade, bounds_source=f.source, runtime_witnessed=False)
        row.pop("classification", None)
        row["base_direct_branch_targets"] = direct_calls(base, f)
        sites.append(row)

    # Tables are dumped as typed derived numbers, never raw byte strings.
    def floats(im, address, count, kind="f"):
        return list(struct.unpack(f">{count}{kind}", im.read(address, count * (8 if kind == "d" else 4))))
    def table(label, a, count, kind="f", delta=32):
        v, w = floats(base, a, count, kind), floats(tu, a + delta, count, kind)
        return {"label": label, "base_va": a, "tu_va": a + delta, "values": v, "tu_values": w,
                "equal_values": v == w, "scalar_type": kind, "grade": "A_PROVEN"}
    tables = [table("lane_centimeters", 0x820FBF80, 17),
              table("zone_mode_identity", 0x820B7C68, 16, "I"),
              table("zone_padding_after_time_gate_cm", 0x820B7CC0, 1, "d"),
              table("lateral_clamp_reciprocal", 0x820B7CD8, 1),
              table("positive_lateral_clamp_cm_float", 0x820B7CDC, 1),
              table("negative_lateral_clamp_cm_float", 0x820B7CE0, 1),
              table("positive_lateral_clamp_cm_double", 0x820B7CE8, 1, "d"),
              table("negative_lateral_clamp_cm_double", 0x820B7CF0, 1, "d"),
              table("nondeep_absolute_depth_clamp_cm", 0x820B7DB8, 1)]
    for label, address in [("initial_deep_drop_depth_curve", 0x820B7CA8),
                           ("initial_deep_drop_lateral_curve", 0x820C8C58),
                           ("slider_seven_curve", 0x820C9440)]:
        count = base.word(address)
        if not 0 < count <= 16 or tu.word(address + 32) != count:
            raise ValueError("curve count changed")
        row = table(label, address + 4, count * 2)
        row.update(base_count_va=address, tu_count_va=address + 32, knot_count=count)
        tables.append(row)
    tables.extend([table("contest_base_array_A", 0x820B748C, 3, delta=16),
                   table("contest_base_array_B_retained_for_sentinel", 0x820B7498, 3, delta=28)])
    tables.append({"label": "tu_contest_added_non_sentinel_array", "base_va": None,
                   "tu_va": 0x820B74A8, "tu_values": floats(tu, 0x820B74A8, 3), "scalar_type": "f",
                   "grade": "A_PROVEN", "consumer_tu_va": 0x847CEBB0})
    for label, address in [("contest_input_curve", 0x820B74A4), ("contest_angle_curve", 0x820B74D8),
                           ("contest_rating_curve", 0x820B7504)]:
        count = base.word(address)
        row = table(label, address + 4, 2*count, delta=28)
        row.update(base_count_va=address, tu_count_va=address+28, knot_count=count)
        tables.append(row)
    opcodes = []
    for i in range(29):
        a = 0x820FBFC8 + i * 16
        opcodes.append({"opcode": i, "base_flags": base.word(0x820FBE68 + i*4),
                        "tu_flags": tu.word(0x820FBE88 + i*4),
                        "base_codec_functions": list(struct.unpack(">4I", base.read(a, 16))),
                        "tu_codec_functions": list(struct.unpack(">4I", tu.read(a + 32, 16)))})

    book, zones = coverage._parsed(body)
    coverage.inspect_zones(body)  # independent pin gate before derived output
    selected = [301, 302, 317, 319, 344, 345, 386, 458, 459, 460, 478, 491]
    assignments = []
    for index in selected:
        row = {"play_index": index, "slots": []}
        for slot in range(11):
            desc = 0x80C4 + index * 100 + 12 + slot * 8
            length = coverage._word(body, desc) >> 28
            node = (coverage.inventory.relative(body, desc + 4, ">", "chain") - 0x17AC4) // 8
            chain = []
            for j in range(node, node + length):
                off = 0x17AC4 + j * 8
                op, w = body[off], coverage._word(body, off + 4)
                n = {"node_index": j, "opcode": op}
                if op == 13:
                    n.update({k: v for k, v in zones[j].items() if k not in ("uses", "body_offset")})
                if op == 14:
                    n["decoded_man_operands"] = {"flag": w & 1, "depth_feet": ((w >> 4) & 255)-64,
                                                  "a": (w >> 12) & 15, "b": (w >> 16) & 15,
                                                  "side": (w >> 20) & 15, "c": (w >> 24) & 15,
                                                  "d": (w >> 1) & 7, "e": (w >> 28) & 1}
                chain.append(n)
            row["slots"].append({"slot_index": slot, "node_count": length, "chain": chain})
        assignments.append(row)
    formations = []
    for index in (0, 141, 147):
        off = 0x244 + index * 184
        formations.append({"formation_index": index, "slot_base": off + 30,
                           "slots": [{"slot_index": i,
                                      "x_cm_columns": list(struct.unpack_from(">3h", body, off+32+i*14)),
                                      "z_cm_columns": list(struct.unpack_from(">3h", body, off+38+i*14))}
                                     for i in range(11)]})

    # Descriptor index/labels are the already-proved player_ratings contract.
    rating_labels = {0: "speed", 1: "agility", 2: "strength", 19: "run_coverage", 20: "coverage",
                     13: "pass_read_coverage", 18: "pass_rush", 17: "tackle"}
    ratings = []
    for i in range(28):
        address = 0x84DB5470 + i * 32
        ratings.append({"index": i, "label": rating_labels.get(i, "other_descriptor"), "va_both": address,
                        "base_getter_va": base.word(address), "tu_getter_va": tu.word(address),
                        "base_setter_va": base.word(address+4), "tu_setter_va": tu.word(address+4),
                        "base_control_word": base.word(address+8), "tu_control_word": tu.word(address+8),
                        "base_coefficients": floats(base, address+12, 5), "tu_coefficients": floats(tu, address+12, 5)})

    zone_targets = {a for a, _, _, _ in SITES if 0x847E9000 <= a < 0x847F6400}
    rating_targets = {0x847CCC28, 0x847C0DB0, 0x847CBED8, 0x847C1590, 0x847CCE48,
                      0x847CDD50, 0x847CE048, 0x847F6430, 0x847F6440}
    changed = []
    for row in diff["functions"]:
        if row["comparison"] != "normalized_different":
            continue
        r = dict(row)
        address = int(r["base_va"], 16)
        calls = set(direct_calls(base, fmap[address]))
        tags = []
        if calls & zone_targets or address in zone_targets:
            tags.append("coverage")
        if calls & rating_targets or address in rating_targets:
            tags.append("ratings")
        r["classification"] = tags or ["other"]
        r["classification_grade"] = "B_INFERENCE" if tags else "UNKNOWN"
        r["classification_reason"] = "direct branch to mapped routine or mapped routine itself" if tags else "no mapped direct coverage/ratings branch; semantic domain unresolved"
        r["mapped_direct_targets"] = sorted(calls & (zone_targets | rating_targets))
        r["semantic_change_proved"] = address in (0x847CDD50, 0x847CE048, 0x848F1CD8)
        if r["base_size"] != r["tu_size"]:
            r["residual_kind"] = "size_changed"
        else:
            f = fmap[address]
            g = Function(int(r["tu_va"], 16), r["tu_size"])
            bn, tn = base.normalized(f), tu.normalized(g)
            indices = [i for i, (a, b) in enumerate(zip(bn, tn)) if a != b]
            candidate = all(base.word(f.start+i*4) >> 26 in (14, 15, 32, 34, 36, 38, 40, 42, 44, 48, 50, 52, 54)
                            and base.word(f.start+i*4) & 0xFFFF0000 == tu.word(g.start+i*4) & 0xFFFF0000
                            for i in indices)
            r["residual_kind"] = "address_operand_candidate" if candidate else "other_instruction_shape_difference"
        changed.append(r)

    stats = {k: v for k, v in diff.items() if k not in ("functions", "gap_differences")}
    stats["classification_counts"] = dict(Counter(tag for r in changed for tag in r["classification"]))
    stats["residual_kind_counts"] = dict(Counter(r["residual_kind"] for r in changed))
    stats["classification_note"] = "Pursuit-specific changed code not proved; other is unresolved, not an exclusion of coverage or pursuit."
    return {
        "address_map.json": {"schema": "apf_coverage_address_map/v1", "runtime_witnessed": False, "functions": sites,
                             "unresolved": [
                                 {"claim": "reported_corner_route_failure_cause", "grade": "UNKNOWN",
                                  "base_investigation_vas": [0x847EE0C0, 0x847EB628, 0x847EA7F8]},
                                 {"claim": "MOD_Palms_China_predicate", "grade": "UNKNOWN",
                                  "base_investigation_vas": [0x847EE8C8, 0x847EED38, 0x847F6018]},
                                 {"claim": "awareness_or_star_tier_changes_receiver_ordering", "grade": "UNKNOWN",
                                  "base_investigation_vas": [0x847CCC28, 0x847EE0C0]},
                                 {"claim": "pursuit_specific_TU_rework", "grade": "UNKNOWN",
                                  "base_investigation_vas": []}]},
        "data_tables.json": {"schema": "apf_coverage_data/v1", "runtime_witnessed": False, "tables": tables,
                             "opcode_rows": opcodes, "rating_descriptors": ratings,
                             "base_codec_table_va": 0x820FBFC8, "tu_codec_table_va": 0x820FBFE8,
                             "base_flags_va": 0x820FBE68, "tu_flags_va": 0x820FBE88},
        "zone_nodes.json": {"schema": "apf_zone_nodes/v1", "master_sha256": sha(body),
                             "masked_master_sha256": coverage.MASKED_MASTER_SHA256, "zone_count": len(zones),
                             "nodes": list(zones.values())},
        "stock_assignments.json": {"schema": "apf_coverage_assignments/v1", "runtime_witnessed": False,
                                    "plays": assignments, "formation_alignments": formations},
        "tu_summary.json": stats,
        "tu_changed_functions.json": {"schema": "apf_tu_changed_function_candidates/v1", "functions": changed},
        "tu_gap_differences.json": {"schema": "apf_tu_anchored_gaps/v1", "gaps": diff["gap_differences"]},
        "tu_function_index.json": {"schema": "apf_tu_function_index/v1", "alignment_grade": "B_INFERENCE",
                                    "columns": ["base_va", "tu_va", "base_size", "tu_size", "comparison"],
                                    "rows": [[r[k] for k in ("base_va", "tu_va", "base_size", "tu_size", "comparison")]
                                             for r in diff["functions"]]},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-pe", required=True, type=Path)
    p.add_argument("--tu-pe", required=True, type=Path)
    p.add_argument("--function-diff", required=True, type=Path)
    p.add_argument("--master-index", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    base, tu = Image(a.base_pe.read_bytes()), Image(a.tu_pe.read_bytes())
    reports = build_evidence(base, tu, json.loads(a.function_diff.read_text(encoding="utf-8")),
                             coverage.read_master_play_body(a.master_index))
    a.out.mkdir(parents=True, exist_ok=True)
    for name, report in reports.items():
        # One complete row per line keeps the large inventories diffable.
        row_key = "rows" if name == "tu_function_index.json" else "gaps" if name == "tu_gap_differences.json" else None
        if row_key:
            metadata = {k: v for k, v in report.items() if k != row_key}
            text = (json.dumps(metadata, allow_nan=False)[:-1] + f', "{row_key}": [\n'
                    + ",\n".join("  " + json.dumps(r, allow_nan=False) for r in report[row_key]) + "\n]}")
        else:
            text = json.dumps(report, indent=2, allow_nan=False)
        (a.out / name).write_text(text + "\n", encoding="utf-8")
    lines = ["# TU 1.1 function-difference candidates", "",
             "Generated numeric inventory. All cross-image alignments are B_INFERENCE. A changed signature is not by itself a proved gameplay change. All runtime behavior is UNWITNESSED. Flat offsets are VA minus 0x82000000.", "",
             "| Base VA | TU VA | Bytes base → TU | Residual | Touch classification / grade |",
             "|---|---|---:|---|---|"]
    for r in reports["tu_changed_functions.json"]["functions"]:
        lines.append(f"| `{r['base_va']}` | `{r['tu_va']}` | {r['base_size']} → {r['tu_size']} | {r['residual_kind']} | {', '.join(r['classification'])} / {r['classification_grade']} |")
    for kind in ("unmatched_base", "unmatched_tu"):
        lines += ["", f"**{kind} (UNKNOWN; not automatically added/deleted)**", "", "| VA | Bytes |", "|---|---:|"]
        lines.extend(f"| `{r['va']}` | {r['size']} |" for r in reports["tu_summary.json"][kind])
    (a.out / "tu_changed_functions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"reports": len(reports), "mapped_functions": len(reports["address_map.json"]["functions"]),
                      "zones": reports["zone_nodes.json"]["zone_count"], "tu_counts": reports["tu_summary.json"]["counts"]}))


if __name__ == "__main__":
    main()

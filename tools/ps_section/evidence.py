#!/usr/bin/env python3
"""Read-only USA XBE evidence ledger. Emits hashes/addresses, never a patched XBE.

Optional Ghidra exports contribute function metadata and source hashes only.
An optional oracle JSON contributes its actual budgets and verdicts, without
turning unknown bytes into an allocation. Path binary reads work on Windows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_practice as fp
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage

SPANS = {
    "coach_descriptor": (0x522190, 0x30), "coach_rows": (0x521F20, 12 * 0x34),
    "roster_descriptor": (0x555098, 0x30), "roster_frame": (0x555070, 0x28),
    "roster_sheet": (0x554C70, 0x140), "all_positions_page": (0x554B58, 0x118),
    "selected_player": (0x2B83F0, 0x37), "roster_count": (0x2B8D90, 0x90),
    "roster_getter": (0x2B8E20, 0x100), "staging": (0x61730, 0xAB),
    "copy_players": (0xC3C60, 0x45), "position_count_gate": (0xE7CA3, 0xA),
    "position_init": (0xE80D0, 0x37), "lineup": (0x18A5D0, 0x62E),
    "fa_tick": (0x324600, 0x15), "cpu_sign": (0x322BB0, 0x241),
    "draft_sign": (0x325B50, 0x3D), "season_cuts": (0x2BFAA0, 0x42),
}
FUNCTIONS = (0x61730, 0x617E0, 0xC3C60, 0xE7C50, 0xE80D0, 0x18A5D0,
             0x189360, 0xE81D0, 0xE8410, 0x13EC80, 0x174140, 0x174C70,
             0x324600, 0x3242C0, 0x322BB0, 0x323B30, 0x2BFAA0, 0x325B50)


def collect(payload: bytes) -> dict:
    if hashlib.sha256(payload).hexdigest() != ps.RETAIL_SHA256:
        raise ValueError("requires the pinned USA retail XBE")
    image = XbeImage(payload)
    manifest = ReservationManifest.load(DEFAULT_MANIFEST, image)
    drift = [path for path, expected in manifest.document["source_sha256"].items()
             if not (ROOT / path).is_file() or hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected]
    patched, receipt = pr.apply(fp.apply(ps.apply(payload)[0])[0])
    def word(va):
        return hex(struct.unpack("<I", image.read(va, 4))[0])
    ledger = {
        "schema": "astra.ps_section.evidence.v1", "retail_sha256": ps.RETAIL_SHA256,
        "image_size": len(payload), "spans": {},
        "menu_retail": fp.read_rows(payload), "menu_built": fp.read_rows(patched),
        "practice_receipt": receipt, "screen_implemented": False,
        "screen_bindings": {hex(a): word(a) for a in (
            0x55509C, 0x5550A0, 0x5550AC, 0x555070,
            0x554B88, 0x554BA0, 0x554D34, 0x542520, 0x5408F0)},
        "practice_squad_runtime_abi": {
            "ps_promote": {"va": hex(ps.SYMBOLS["ps_promote"]), "team": "ECX", "player": "EDX"},
            "ps_demote": {"va": hex(ps.SYMBOLS["ps_demote"]), "team": "ECX", "player": "EDX"},
            "reserve_count": {"va": hex(ps.SYMBOLS["reserve_count"]), "team": "EAX",
                              "scope": "private optimized helper; entire runtime pinned"}},
        "screen_plan_bytes": {"descriptor": 48, "frame": 40, "sheet": 320,
                              "two_pages": 560, "additional_menu_bytes": 0},
        "manifest": {"sha256": hashlib.sha256(DEFAULT_MANIFEST.read_bytes()).hexdigest(),
                     "source_drift": drift, "new_caves": [], "new_runtime_flags": [],
                     "staging_prior_owners": manifest.overlaps(pr.STAGE_VA, pr.STAGE_VA + pr.STAGE_SIZE)},
    }
    for name, (va, size) in SPANS.items():
        ledger["spans"][name] = {"va": hex(va), "size": size,
                                   "sha256": hashlib.sha256(image.read(va, size)).hexdigest()}
    # Every byte alignment, including callback-table and immediate interiors.
    interior = []
    lo, hi = pr.STAGE_VA + 1, pr.STAGE_VA + pr.STAGE_SIZE
    for section in image.sections:
        data = image.read(section.start, section.raw_size)
        # The target interval is within one 256-byte page. Filter by its upper
        # three bytes before decoding; this remains an all-alignment scan.
        suffix = struct.pack("<I", lo)[1:]
        start = 1
        while (start := data.find(suffix, start)) != -1:
            at = start - 1
            value = struct.unpack_from("<I", data, at)[0]
            if lo <= value < hi:
                interior.append({"source": hex(section.start + at), "target": hex(value)})
            start += 1
    ledger["staging_interior_absolute_candidates"] = interior
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, default=Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
        "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe")
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--oracle-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = [args.xbe, DEFAULT_MANIFEST]
    if args.oracle_report:
        inputs.append(args.oracle_report)
    if args.output.suffix != ".json" or any(
            args.output.resolve() == p.resolve() or (args.output.exists() and args.output.samefile(p))
            for p in inputs):
        parser.error("output must be a separate JSON file")
    result = collect(args.xbe.read_bytes())
    if args.corpus:
        csv.field_size_limit(10**8)
        with (args.corpus / "functions.tsv").open(newline="", encoding="utf-8") as handle:
            rows = {int(row["address"], 16): row for row in csv.DictReader(handle, delimiter="\t")
                    if row["address"].startswith("0x")}
        result["ghidra"] = {}
        for address in FUNCTIONS:
            row = rows[address]
            result["ghidra"][hex(address)] = {
                "body_ranges": row["body_ranges"], "source": row["pseudo_c_file"],
                "source_sha256": hashlib.sha256((args.corpus / row["pseudo_c_file"]).read_bytes()).hexdigest()}
    if args.oracle_report:
        scan = json.loads(args.oracle_report.read_text(encoding="utf-8"))
        if scan["xbe_sha256"] != ps.RETAIL_SHA256:
            parser.error("oracle report is for a different executable")
        result["oracle_scan"] = {key: scan[key] for key in (
            "xbe_sha256", "reservation_model", "budgets", "budget_exhausted", "instruction_count",
            "reference_count", "unresolved_count", "unresolved_by_kind", "sections", "queries")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}; sources unchanged; management screen deferred.")


if __name__ == "__main__":
    main()

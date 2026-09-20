#!/usr/bin/env python3
"""Read-only fixture import and crest-build timing; emit metadata, never art."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.apf_studio import ps3_texture_bundle as api
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.session import ApfSession
import apf_logo_patch as writer
import apf_ps3_speed_benchmark as profiling


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"python": sys.version, "platform": platform.platform(), "cpu_count": os.cpu_count(),
              "bundle": str(args.bundle), "bundle_sha256": hashlib.sha256(args.bundle.read_bytes()).hexdigest(),
              "index": str(args.index), "encoder_policy": writer.encoder_policy(), "phases": {}}

    def phase(name, operation):
        start = time.perf_counter()
        result = operation()
        report["phases"][name] = time.perf_counter() - start
        print(f"{name}: {report['phases'][name]:.4f}s", flush=True)
        return result

    profiling.instrument()
    writer.ordered_crest_map = profiling.profiled_map
    bundle = phase("read_bundle_cold", lambda: api.read_bundle(args.bundle))
    phase("read_bundle_warm", lambda: api.read_bundle(args.bundle))
    slots = phase("destination_slots", lambda: api.destination_slots(args.index))
    logos = api.TextureBundle(bundle.source, tuple(p for p in bundle.pairs if p.kind == "logo"), ())
    report["logo_pairs"] = len(logos.pairs)
    report["rejected_pairs"] = len(bundle.rejected_pairs)
    sizes = phase("measure_all_cold", lambda: api.measure_bundle_logos(logos, slots, args.index,
        lambda msg, *_: print(msg, flush=True) if msg.startswith("Measured") else None))
    phase("measure_all_warm", lambda: api.measure_bundle_logos(logos, slots, args.index))
    # The screenshot identifies slot 96 but not its input art. Use the Raiders
    # pair visible in the supplied matchup, and record this choice explicitly.
    pair = next(p for p in logos.pairs if p.team == "Los Angeles Raiders")
    slot = next(s for s in slots if s.crest_asset_index == 96)
    report["scenario"] = {"team": pair.team, "pair_id": pair.pair_id, "slot": slot.slot_id,
                          "crest_asset_index": 96, "compressed_art_budget": slot.compressed_art_budget,
                          "screenshot_art_identity_known": False}
    plan = phase("plan_slot96", lambda: api.build_plan(logos, slots,
        [api.Assignment(pair.pair_id, slot.slot_id)], measurements=sizes))
    source = ApfSource(args.index.parent, args.index.parent, args.index, "a" * 64,
                       args.index.stat().st_size, "b" * 64, "read-only timing fixture")
    with tempfile.TemporaryDirectory(prefix="apf-b72-logo-") as directory:
        session = ApfSession(source, Mock(), cache_root=Path(directory) / "cache")
        try:
            phase("stage_slot96", lambda: api.stage_plan(session, plan))
        finally:
            session.close()
    request = ((slot.outer_index, *(layer.image.tobytes() for layer in pair.layers), True),)
    cold = phase("compile_slot96", lambda: writer.build_crest_packages(args.index, request))
    warm = phase("compile_slot96_warm", lambda: writer.build_crest_packages(args.index, request))
    assert cold[slot.outer_index].entry_bytes == warm[slot.outer_index].entry_bytes
    result = cold[slot.outer_index]
    report["package"] = {"sha256": hashlib.sha256(result.entry_bytes).hexdigest(),
                         "size": len(result.entry_bytes), "fit": result.manifest.get("fit"),
                         "warm_bytes_identical": True}
    report["stages_exclusive_seconds"] = dict(profiling.STATS)
    report["calls"] = dict(profiling.CALLS)
    report["limitations"] = ["Linux timing, native helper enabled if available",
        "No full game-folder copy, linked logo-cache build, or emulator run",
        "Local fixture ZIP is not the missing September 11 attachment; screenshot's exact art is unknown"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("xb") as stream:
        stream.write((json.dumps(report, indent=2, sort_keys=True) + "\n").encode())


if __name__ == "__main__":
    main()

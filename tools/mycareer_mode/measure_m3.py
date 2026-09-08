"""Compile an M3 purchase-core lower bound without installing it.

The normal owner still enforces its exact 8192-byte reservation. This probe
does not enlarge the owner or produce an executable. The omitted M3 UI,
calendar, transactions, draft and texture binding require additional space.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from tools.mycareer_mode import build_runtime


def measure():
    source = build_runtime.SOURCE
    c = (source / "runtime.c").read_text(encoding="utf-8")
    extra = (source / "upgrade_candidate.c").read_text(encoding="utf-8")
    base = mode.assembly
    if build_runtime.generate() != build_runtime.TARGET.read_text(encoding="utf-8"):
        raise ValueError("baseline generated runtime differs")
    _, labels = mode.code_for(0, 0)
    with tempfile.TemporaryDirectory(prefix="mycareer-m3-budget-") as folder:
        d = Path(folder).resolve()
        (d / "runtime.c").write_text(c + "\n" + extra, encoding="utf-8")
        (d / "runtime.S").write_bytes((source / "runtime.S").read_bytes())
        compiled = {}
        # Only the locally generated Python byte/relocation literals execute.
        exec(compile(build_runtime.generate(d), "<generated-m3-capacity>", "exec"), compiled)
        smaller = {}
        exec(compile(build_runtime.generate(d, optimize="-Oz"), "<generated-m3-oz-capacity>", "exec"), smaller)
    mode.assembly = SimpleNamespace(**compiled)
    try:
        try:
            candidate, candidate_labels = mode.code_for(0, 0)
        except mode.legacy.MyCareerError as exc:
            error = str(exc)
            match = re.fullmatch(r"generic MyCareer needs (\d+) bytes; exceeds its 8192-byte budget by (\d+) bytes", error)
            if match is None:
                raise
            required, shortfall = map(int, match.groups())
            refused = True
        else:
            required = candidate_labels["content_end"] + len(mode.TAG)
            shortfall, refused, error = 0, False, ""
            del candidate
    finally:
        mode.assembly = base
    mode.assembly = SimpleNamespace(**smaller)
    try:
        try:
            mode.code_for(0, 0)
        except mode.legacy.MyCareerError as exc:
            match = re.fullmatch(r"generic MyCareer needs (\d+) bytes; exceeds its 8192-byte budget by (\d+) bytes", str(exc))
            if match is None:
                raise
            oz_required, oz_shortfall = map(int, match.groups())
        else:
            raise ValueError("the Oz design now fits; revise the capacity conclusion")
    finally:
        mode.assembly = base
    return {
        "schema": "nfl2k5.mycareer.m3-capacity.v1", "experimental": True,
        "runtime_witnessed": False, "runtime_installed": False,
        "compiler_flags": "build_runtime.py: gcc -m32 -Os -fomit-frame-pointer",
        "reservation_rx": mode.CODE_SIZE, "reservation_rw": mode.DATA_SIZE,
        "format_tag_bytes": len(mode.TAG),
        "baseline_machine_bytes": len(base.CODE),
        "baseline_content_bytes": labels["content_end"],
        "baseline_remaining_bytes": mode.TAG_OFFSET - labels["content_end"],
        "candidate_machine_bytes": len(compiled["CODE"]),
        "candidate_machine_delta": len(compiled["CODE"]) - len(base.CODE),
        "candidate_required_rx_bytes": required, "candidate_shortfall_bytes": shortfall,
        "normal_owner_refused": refused, "refusal": error,
        "baseline_menu_rw_bytes": labels["menu_bytes"],
        "nine_row_hub_menu_rw_bytes": labels["menu_bytes"] + 4 * 52,
        "current_menu_rw_capacity": 1024,
        "candidate_quote_rw_range": [3328, 3368],
        "candidate_source_sha256": hashlib.sha256(extra.encode()).hexdigest(),
        "candidate_machine_sha256": hashlib.sha256(compiled["CODE"]).hexdigest(),
        "uninstalled_oz_alternative": {
            "candidate_machine_bytes": len(smaller["CODE"]),
            "candidate_required_rx_bytes": oz_required,
            "candidate_shortfall_bytes": oz_shortfall,
            "candidate_machine_sha256": hashlib.sha256(smaller["CODE"]).hexdigest(),
            "claim": "Additional compiler compaction still exceeds the owner; no runtime or UI acceptance claimed.",
        },
        "included": ["existing M2 runtime and menus", "rating quote, tier cost and atomic debit",
                     "identity/token/value/balance revalidation, cancel and replay refusal"],
        "excluded": ["purchase UI and confirmation wiring", "nine-row hub RX tables",
                     "calendar", "Team/depth UI", "trade/release execution and native logs",
                     "draft and played Senior Bowl", "art registration and drawing"],
        "claim": "Measured lower bound for this design, not an exact size of all M3 or a proof that every possible refactor exceeds the reservation.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(measure(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")

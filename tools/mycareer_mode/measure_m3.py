"""Measure the installed M3 runtime and unchanged peer allocations.

The historical pre-M3 lower bound remains in docs/nfl2k5_my_career_m3_budget.json.
This tool builds only the bounded runtime object; it creates no XBE or disc.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_xbe_space as space
from tools.mycareer_mode import build_runtime


def measure():
    if build_runtime.generate() != build_runtime.TARGET.read_text(encoding="utf-8"):
        raise ValueError("generated M3 runtime differs")
    requests = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
    previous = [(o, k, 8192 if (o, k) == (mode.OWNER, "code") else n, a)
                for o, k, n, a in requests if o != mode.EXTRA_OWNER]
    before, after = space.plan(previous), space.plan(requests)
    old = {(r["owner"], r["kind"]): r for r in before["allocations"]}
    current = {(r["owner"], r["kind"]): r for r in after["allocations"]}
    peers = [r for key, r in old.items() if key != (mode.OWNER, "code")]
    if not all(current[r["owner"], r["kind"]] == r for r in peers):
        raise ValueError("M3 changed another allocation")
    code, data = current[mode.OWNER, "code"], current[mode.OWNER, "data"]
    blob, labels = mode.code_for(code["va"], data["va"])
    return {
        "schema": "nfl2k5.mycareer.m3-installed-budget.v1",
        "experimental": True, "runtime_witnessed": False,
        "requests": mode.REQUESTS,
        "machine_code_bytes": len(mode.assembly.CODE),
        "content_bytes": labels["content_end"]-code["va"],
        "format_tag_bytes": len(mode.TAG),
        "spare_rx_bytes": mode.TAG_OFFSET-(labels["content_end"]-code["va"]),
        "immutable_code_sha256_at_budget_address": hashlib.sha256(blob).hexdigest(),
        "before": before, "after": after,
        "unchanged_peer_allocations": peers,
        "same_file_size": before["file_size"] == after["file_size"],
        "historical_measurement": "docs/nfl2k5_my_career_m3_budget.json",
        "senior_bowl_playable": False,
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

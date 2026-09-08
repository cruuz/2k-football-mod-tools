"""Measure an uninstalled fast-forward lower bound; no executable is written."""
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
    base = mode.assembly
    extra = (source / "fastforward_candidate.c").read_text(encoding="utf-8")
    if build_runtime.generate() != build_runtime.TARGET.read_text(encoding="utf-8"):
        raise ValueError("generated baseline differs")
    with tempfile.TemporaryDirectory(prefix="mycareer-m4-capacity-") as folder:
        d = Path(folder).resolve()
        (d / "runtime.c").write_text((source / "runtime.c").read_text(encoding="utf-8")
                                     + "\n" + extra, encoding="utf-8")
        (d / "runtime.S").write_bytes((source / "runtime.S").read_bytes())
        compiled = {}
        exec(compile(build_runtime.generate(d), "<generated-mode4-capacity>", "exec"), compiled)
    union = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
    layouts = []
    for name, requests in (("minimal", mode.REQUESTS), ("budget_union", union)):
        allocations = mode.space.plan(requests, scaleout=True)["allocations"]
        own = {a["kind"]: a for a in allocations if a["owner"] == mode.OWNER}
        code, data = own["code"]["va"], own["data"]["va"]
        _, labels = mode.code_for(code, data)
        mode.assembly = SimpleNamespace(**compiled)
        try:
            try:
                mode.code_for(code, data)
            except mode.legacy.MyCareerError as exc:
                match = re.fullmatch(r"generic MyCareer needs (\d+) bytes; exceeds its 8192-byte budget by (\d+) bytes", str(exc))
                if match is None:
                    raise
                required, shortfall = map(int, match.groups())
            else:
                raise ValueError("candidate fits; revise the capacity conclusion")
        finally:
            mode.assembly = base
        layouts.append(dict(name=name, code_va=hex(code), data_va=hex(data),
                            content_bytes=labels["content_end"] - code,
                            remaining_bytes=mode.TAG_OFFSET - labels["content_end"] + code,
                            candidate_required_rx=required, candidate_shortfall=shortfall,
                            normal_owner_refused=True))
    return dict(schema="nfl2k5.mycareer.mode4-capacity.v1", experimental=True,
                runtime_witnessed=False, candidate_installed=False, candidate_executed=False,
                compiler_flags="build_runtime.py: gcc -m32 -Oz -fomit-frame-pointer",
                reservation_rx=mode.CODE_SIZE, reservation_rw=mode.DATA_SIZE,
                format_tag_bytes=len(mode.TAG), baseline_machine_bytes=len(base.CODE),
                candidate_machine_bytes=len(compiled["CODE"]),
                candidate_machine_delta=len(compiled["CODE"]) - len(base.CODE),
                candidate_source_sha256=hashlib.sha256(extra.encode()).hexdigest(),
                layouts=layouts,
                included=["existing complete mode", "admission, presence/end checks and bounded native-frame loop"],
                excluded=["UI, pause and interruption", "timestep, scene, audio and animation handling",
                          "safe live resume", "stop-to-Apartment lifecycle"],
                claim="Lower bound for this incomplete design, not a universal minimum or a working Supersim.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(measure(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")

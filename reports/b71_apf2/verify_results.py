"""Aggregate the latest standalone result for every requested suite."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).parent
expected = sorted(p.relative_to(root).as_posix() for p in (root / "tests/mod_editor").glob("test_apf*.py"))
expected += ["tests/mod_editor/" + name for name in (
    "test_b69_a1_playcalling.py", "test_provider_integrity.py", "test_product_catalog.py",
    "test_phase1_packaging.py", "test_capability_registry_module_commands.py")]
records = [json.loads(line) for line in (folder / "commands.jsonl").read_text().splitlines()]
latest = {}
for record in sorted(records, key=lambda row: row["started_utc"]):
    command = record["command"]
    if len(command) >= 2 and Path(command[-2]).name.startswith("python") and command[-1] in expected:
        latest[command[-1]] = record
results = []
for path in expected:
    record = latest.get(path)
    if record is None:
        results.append({"suite": path, "missing": True})
        continue
    output = (root / record["log"]).read_text()
    counts = re.findall(r'Ran (\d+) tests? in', output)
    skipped = re.findall(r'OK \(skipped=(\d+)\)', output)
    results.append({"suite": path, "exit_code": record["exit_code"], "log": record["log"],
                    "tests_run": int(counts[-1]) if counts else None,
                    "skipped": int(skipped[-1]) if skipped else 0,
                    "elapsed_seconds": record["elapsed_seconds"], "started_utc": record["started_utc"]})
failed = [r for r in results if r.get("missing") or r["exit_code"]]
summary = {"expected_standalone_suites": len(expected), "passed_suite_files": len(results) - len(failed),
           "tests_reported_run": sum(r.get("tests_run") or 0 for r in results),
           "skips_reported": sum(r.get("skipped", 0) for r in results),
           "failed_or_missing": failed, "suites": results}
(folder / "suite_results.json").write_bytes((json.dumps(summary, indent=2) + "\n").encode())
print(json.dumps({key: value for key, value in summary.items() if key != "suites"}, indent=2))
print("Files with optional skips:")
for row in results:
    if row.get("skipped"):
        print(row["suite"], "skipped", row["skipped"], "log", row["log"])
raise SystemExit(bool(failed))

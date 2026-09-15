"""Run each requested suite standalone, with independent processes and per-file locks."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
files = sorted((root / "tests/mod_editor").glob("test_apf*.py"))
files += [root / "tests/mod_editor" / name for name in (
    "test_b69_a1_playcalling.py", "test_provider_integrity.py", "test_product_catalog.py",
    "test_phase1_packaging.py", "test_capability_registry_module_commands.py")]
if "--remaining" in sys.argv:
    import json
    completed = {Path(json.loads(line)["log"]).stem
                 for line in Path(__file__).with_name("commands.jsonl").read_text().splitlines()}
    # These two bounded native matrices are already running in the first
    # coordinator. Let another pair of workers drain the shorter checks.
    busy = {"test_apf_b67_model_native", "test_apf_b69_native"}
    busy.update(p.name for p in (root / ".scratch/check-locks").iterdir())
    files = [p for p in files if p.stem not in completed | busy]

def run(path):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("run.py")),
                             path.stem, sys.executable, str(path.relative_to(root))],
                            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return path.name, result.returncode, result.stdout

failed = []
workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 2
with ThreadPoolExecutor(max_workers=workers) as pool:
    tasks = [pool.submit(run, path) for path in files]
    for task in as_completed(tasks):
        name, code, output = task.result()
        print(f"{'PASS' if code == 0 else 'FAIL'} {name} exit={code}", flush=True)
        if code:
            failed.append(name)
            print(output[-3000:], flush=True)
print(f"Completed {len(files)} standalone suites; failures: {failed}", flush=True)
sys.exit(bool(failed))

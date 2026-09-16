"""Commit the reviewed explicit paths and write the private bundle receipt."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

root = Path(__file__).resolve().parents[2]
receipt_path = root / ".scratch/astra-b71-apf2-delivery.json"
bundle = root / ".scratch/astra-b71-apf2.bundle"
base = "e2f5c6e61a0aa5772b0b7d858cb3fb3d35896174"
git = ["git", "--git-dir=.scratch/git", "--work-tree=."]
receipt = {"base": base, "branch": "astra/b71-apf2-situations", "commands": [],
           "gameplay": "UNWITNESSED", "push": False}

def save():
    receipt_path.write_bytes((json.dumps(receipt, indent=2) + "\n").encode())

def run(command):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    begin = time.monotonic()
    result = subprocess.run(command, cwd=root, env=dict(os.environ, PYTHONPATH=str(root), QT_QPA_PLATFORM="offscreen"),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    receipt["commands"].append({"command": command, "started_utc": started,
                                "elapsed_seconds": round(time.monotonic() - begin, 3),
                                "exit_code": result.returncode, "output": result.stdout})
    save()
    if result.returncode:
        raise SystemExit(result.returncode)
    return result.stdout.strip()

paths = json.loads(Path(__file__).with_name("delivery_paths.json").read_text())
assert paths and all(not p.startswith("/") and ".." not in Path(p).parts and (root / p).is_file() for p in paths)
assert all(p in ("ASTRA_REPORT.md", "ASTRA_LAST_MESSAGE.md") or p.startswith("reports/b71_apf2/") for p in paths)
run([*git, "add", "-f", "--", *paths])
run(["python3", "reports/b71_apf2/audit_delivery.py"])
# Verbatim test output keeps its original blank lines and whitespace.
run([*git, "diff", "--cached", "--check", "--", ".", ":(exclude)reports/b71_apf2/*.log"])
run(["python3", "packaging/repin.py", "--apply"])
run([*git, "commit", "-m", "APF: record situation evidence, regression gates and unfinished runtime scope", "--", *paths])
receipt["head"] = run([*git, "rev-parse", "HEAD"])
receipt["commits"] = run([*git, "log", "--oneline", base + "..HEAD"])
run([*git, "bundle", "create", str(bundle.relative_to(root)), base + "..astra/b71-apf2-situations"])
run([*git, "bundle", "verify", str(bundle.relative_to(root))])
run([*git, "bundle", "list-heads", str(bundle.relative_to(root))])
run([*git, "diff", "--exit-code"])
run([*git, "diff", "--cached", "--exit-code"])
receipt["bundle"] = {"path": str(bundle.relative_to(root)), "bytes": bundle.stat().st_size,
                     "sha256": hashlib.sha256(bundle.read_bytes()).hexdigest()}
stage = root / ".scratch/apf-release"
if stage.exists():
    shutil.rmtree(stage)
test_python = root / ".scratch/test-python"
if test_python.exists():
    shutil.rmtree(test_python)
locks = root / ".scratch/check-locks"
if locks.exists():
    assert not list(locks.iterdir()), "A standalone check is still running"
    locks.rmdir()
receipt["temporary_stage_removed"] = not stage.exists()
receipt["temporary_python_removed"] = not test_python.exists()
save()
print(json.dumps(receipt, indent=2))

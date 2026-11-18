"""Run the three hosted OS matrices with a fresh interpreter and on-disk output per file."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from local_windows_ci import EVIDENCE, ISOLATED, plan, skip_reason, test_count


def run_file(path, repo, environment, stream, timer, seconds):
    command = [sys.executable, str(path)]
    if os.name != "nt":
        command = [timer, "-k", "30", str(seconds), *command] if timer else command
        return subprocess.run(command, cwd=repo, env=environment,
                              stdout=stream, stderr=subprocess.STDOUT).returncode
    # The native Win32 wait uses no helper process on success. On timeout,
    # taskkill /T follows the child PID tree, including nested installers.
    with subprocess.Popen(command, cwd=repo, env=environment,
                          stdout=stream, stderr=subprocess.STDOUT) as child:
        try:
            return child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            taskkill = Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"
            try:
                subprocess.run([str(taskkill), "/PID", str(child.pid), "/T", "/F"],
                               stdout=stream, stderr=subprocess.STDOUT, timeout=30)
            except (OSError, subprocess.TimeoutExpired) as error:
                stream.write(f"\nCould not stop the timed-out child process tree: {error}\n".encode())
            finally:
                child.kill()
            return 124


def run_suite(repo: Path, timer: str, *, seconds: int = 420) -> int:
    files = plan(repo, [])
    if not files:
        print("no test files found under tests/mod_editor/test_*.py", flush=True)
        return 2
    lean = not (repo / EVIDENCE).is_file()
    environment = {**os.environ, "PYTHONPATH": str(repo), "QT_QPA_PLATFORM": "offscreen"}
    isolated = environment.copy()
    del isolated["PYTHONPATH"]
    passed = skipped = tests = 0
    failures = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as logs:
        for path in files:
            reason = skip_reason(lean, path.name)
            if reason:
                print(f"SKIP  {path.name}  ({reason})", flush=True)
                skipped += 1
                continue
            started = time.monotonic()
            output = Path(logs) / path.name
            # A descendant inheriting a stdout pipe can keep communicate() open
            # after the child exits. A distinct regular file also prevents an
            # orphan from writing into the next test's captured output.
            with output.open("wb") as stream:
                try:
                    rc = run_file(path, repo, isolated if path.name == ISOLATED else environment,
                                  stream, timer, seconds)
                except OSError as error:
                    stream.write(f"Could not launch {path.name}: {error}\n".encode())
                    rc = 1
            log = output.read_text(encoding="utf-8", errors="replace")
            count = test_count(log)
            elapsed = time.monotonic() - started
            if count is not None:
                tests += count
            if rc == 0 and count is not None:
                passed += 1
                print(f"PASS  {path.name}  ({count} tests)  [{elapsed:.3f}s]", flush=True)
                continue
            failures.append(path.name)
            if rc in (124, 137):
                log += f"\nTIMED OUT after {seconds}s (killed by CI per-file timeout)"
            elif rc == 0:
                rc = 1
                log += "\nNo test runner summary. Run this test file directly and check its entry point."
            print(f"FAIL  {path.name}  (rc={rc})  [{elapsed:.3f}s]", flush=True)
            print("\n".join(log.splitlines()[-40:]), flush=True)
    print(f"SUMMARY: files={len(files)} passed={passed} failed={len(failures)} skipped={skipped} tests={tests}", flush=True)
    if failures:
        print("FAILED FILES:", *failures, flush=True)
        return 1
    print("ALL TEST FILES PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_suite(Path(__file__).resolve().parents[2], sys.argv[1]))

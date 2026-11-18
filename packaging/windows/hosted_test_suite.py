"""Run the three hosted OS matrices with a fresh interpreter and on-disk output per file."""
from __future__ import annotations

import ast
import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from local_windows_ci import EVIDENCE, ISOLATED, plan, skip_reason, test_count


PRIVATE_INPUTS = json.loads(Path(__file__).with_name("hosted_private_test_inputs.json").read_text(encoding="utf-8"))


def skip_details(output: str):
    """Separate unittest class/module skips (uncounted) from skipped test cases."""
    fixtures = {}
    reasons = set()
    for line in output.splitlines():
        if " ... skipped " not in line:
            continue
        label, value = line.rsplit(" ... skipped ", 1)
        try:
            reason = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(reason, str):
            reasons.add(reason)
            if re.fullmatch(r"(?:setUp|tearDown)(?:Class|Module) \([^)]+\)", label):
                fixtures[label] = reason
    unittest_results = re.findall(r"^(?:OK|FAILED|NO TESTS RAN)(?: \(([^)\n]*)\))?$", output, re.M)
    if unittest_results:
        skipped = re.search(r"\bskipped=(\d+)\b", unittest_results[-1])
        # A skipped subtest also appears in unittest's outcome total while its
        # enclosing test remains one executed case.
        subtests = len(re.findall(r"^  \S.* \.\.\. skipped (?:'|\")", output, re.M))
        count = int(skipped[1]) if skipped else 0
        return max(0, count - len(fixtures) - subtests), fixtures, reasons, count
    for line in reversed(output.splitlines()):
        if re.search(r"\bin [0-9]+(?:\.[0-9]+)?s\b", line):
            skipped = re.search(r"\b(\d+) skipped\b", line)
            if skipped:
                return int(skipped[1]), fixtures, reasons, 0
    return 0, fixtures, reasons, 0


def missing_private_inputs(name, fixtures, skipped_count):
    expected = PRIVATE_INPUTS["files"].get(name)
    if not expected or len(fixtures) != len(expected) or len(fixtures) != skipped_count:
        return None
    labels = set()
    for cls, key in expected.items():
        reason = fixtures.get(f"setUpClass (__main__.{cls})", "").replace("\\", "/")
        requirement = PRIVATE_INPUTS["requirements"][key]
        if not any(fnmatch.fnmatchcase(reason, pattern) for pattern in requirement["messages"]):
            return None
        labels.add(requirement["description"])
    return ", ".join(sorted(labels))


def write_job_summary(totals, groups):
    lines = [f"### Test coverage on {sys.platform}, Python {sys.version.split()[0]}", "", totals]
    for label, files in groups:
        lines.extend(["", f"**{label} ({len(files)})**", ""])
        for name, reason in files.items():
            lines.append(f"- `{name}` — {reason}")
    summary = "\n".join(lines) + "\n"
    print(summary, flush=True)
    if destination := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(destination).open("a", encoding="utf-8") as stream:
            stream.write(summary)


def run_file(path, repo, environment, stream, timer, seconds):
    command = [sys.executable, str(path), "-v"]
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
    # Nested runner tests produce their own summaries in temporary files.
    environment.pop("GITHUB_STEP_SUMMARY", None)
    isolated = environment.copy()
    del isolated["PYTHONPATH"]
    passed = tests = case_skips = 0
    failures = []
    preset_skips, private_skips, all_case_skips, unexpected_zero = {}, {}, {}, {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as logs:
        for path in files:
            reason = skip_reason(lean, path.name)
            if reason:
                print(f"SKIP  {path.name}  ({reason})", flush=True)
                preset_skips[path.name] = reason
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
            skipped_cases, fixtures, reasons, skipped_outcomes = skip_details(log)
            if count is not None:
                tests += count
                case_skips += min(count, skipped_cases)
            if rc == 0 and count == 0:
                private = missing_private_inputs(path.name, fixtures, skipped_outcomes)
                if private:
                    private_skips[path.name] = private
                    print(f"SKIP  {path.name}  (0 cases, private input required: {private})", flush=True)
                    continue
            if rc == 0 and count and skipped_cases >= count:
                explanation = ", ".join(sorted(reasons)) or f"framework reported {skipped_cases} skipped cases"
                all_case_skips[path.name] = explanation
                print(f"SKIP  {path.name}  (all {count} collected cases skipped: {explanation})", flush=True)
                continue
            if rc == 0 and count:
                passed += 1
                print(f"PASS  {path.name}  ({count} tests)  [{elapsed:.3f}s]", flush=True)
                for fixture, reason in fixtures.items():
                    print(f"      {fixture} skipped: {reason}", flush=True)
                continue
            failures.append(path.name)
            if count == 0:
                unexpected_zero[path.name] = "No matching private class and input declaration"
                log += "\nZero tests ran without the declared private fixture skips. Check test discovery and the setup reason."
            if rc in (124, 137):
                log += f"\nTIMED OUT after {seconds}s (killed by CI per-file timeout)"
            elif rc == 0:
                rc = 1
                if count is None:
                    unexpected_zero[path.name] = "No test runner summary"
                    log += "\nNo test runner summary. Run this test file directly and check its entry point."
            print(f"FAIL  {path.name}  (rc={rc})  [{elapsed:.3f}s]", flush=True)
            print("\n".join(log.splitlines()[-40:]), flush=True)
    skipped = len(preset_skips) + len(private_skips) + len(all_case_skips)
    totals = (f"SUMMARY: files={len(files)} passed={passed} failed={len(failures)} skipped={skipped} tests={tests} "
              f"executed_cases={tests - case_skips} skipped_cases={case_skips}")
    write_job_summary(totals, (("Zero-case files requiring private inputs", private_skips),
                               ("Files with every collected case explicitly skipped", all_case_skips),
                               ("Files skipped before collection", preset_skips),
                               ("Unexpected zero or missing test runner summary", unexpected_zero)))
    if failures:
        print("FAILED FILES:", *failures, flush=True)
        return 1
    print("ALL TEST FILES PASSED", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_suite(Path(__file__).resolve().parents[2], sys.argv[1]))

"""Partition every discovered matrix case into plain standalone Python runs.

No assertions, owners, fixtures or test selection rules are changed. Each
partition uses the test file's own unittest entry point; the receipt records
all case names, exit statuses and output hashes. No third-party runner needed.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.mod_editor import test_nfl2k5_owner_pairwise_composition as matrix


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield '.'.join(item.id().split('.')[-2:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=4)
    parser.add_argument('--log-dir', type=Path, required=True)
    args = parser.parse_args()
    args.log_dir.mkdir(parents=True, exist_ok=True)
    names = sorted(cases(unittest.defaultTestLoader.loadTestsFromModule(matrix)))
    if not names or len(names) != len(set(names)):
        raise RuntimeError('Missing or duplicated discovered matrix cases')
    groups = [names[index::args.workers] for index in range(args.workers)]
    script = ROOT / 'tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py'
    start = time.monotonic()

    def run(index):
        command = [sys.executable, str(script), *groups[index]]
        log = args.log_dir / f'pairwise-{index + 1}.log'
        with log.open('wb') as output:
            result = subprocess.run(command, cwd=ROOT,
                env={**os.environ, 'PYTHONPATH': str(ROOT)},
                stdout=output, stderr=subprocess.STDOUT)
        raw = log.read_bytes()
        summaries = re.findall(rb'Ran (\d+) tests? in ([0-9.]+)s', raw)
        count = int(summaries[-1][0]) if summaries else 0
        skips = re.findall(rb'OK \(skipped=(\d+)\)', raw)
        complete = result.returncode == 0 and count == len(groups[index])
        record = dict(partition=index + 1, command=command, cases=groups[index],
            exit=result.returncode, tests=count, skipped=int(skips[-1]) if skips else 0,
            complete=complete,
            output_sha256=hashlib.sha256(raw).hexdigest())
        print(json.dumps({k: record[k] for k in ('partition', 'exit', 'tests', 'complete')}), flush=True)
        return record

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(run, range(args.workers)))
    complete = all(row['complete'] for row in rows)
    receipt = dict(discovered=len(names), executed=sum(row['tests'] for row in rows),
        skipped=sum(row['skipped'] for row in rows), complete=complete, partitions=rows)
    (args.log_dir / 'pairwise-receipt.json').write_bytes(
        (json.dumps(receipt, indent=2) + '\n').encode('utf-8'))
    print(f'Ran {receipt["executed"]} tests in {time.monotonic() - start:.3f}s')
    print(('OK' + (f' (skipped={receipt["skipped"]})' if receipt['skipped'] else ''))
          if complete else 'FAILED: inspect partition logs')
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())

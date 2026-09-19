"""Write the handoff only after every requested standalone file and gate passes."""
from pathlib import Path
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent
subprocess.run([sys.executable, str(folder / 'summarize.py')], check=True)
suites = json.loads((folder / 'final-tests.json').read_text())
gates = json.loads((folder / 'gates.json').read_text())
assert suites['all_passed'] and len(gates) == 11 and all(r['exit_code'] == 0 for r in gates)
body = (folder / 'report_body.md').read_text()
body = body.replace('Code commits are `a07c6569` and `1a6eb013`, followed by the evidence handoff',
                    'Code commits are `a07c6569`, `1a6eb013` and `a006e736`, followed by the evidence handoff')
body += '\n## Final validation ledger\n\n'
body += f"**{suites['files']} standalone suite files, {suites['tests']} tests, all passed.** The new native suite executed all five cases on both owned profiles.\n\n"
body += 'Each file below ran as plain `python3 <file>` with `PYTHONPATH=<worktree>` and `QT_QPA_PLATFORM=offscreen`. Exact interpreter paths, elapsed times, complete logs and log hashes are in [final-tests.json](reports/b72_a1/final-tests.json).\n\n'
body += '| Standalone file | Tests | Result | Log |\n| --- | ---: | --- | --- |\n'
for row in suites['results']:
    body += f"| `{row['command'][1]}` | {row['tests']} | PASS | [{row['log']}](reports/b72_a1/{row['log']}) |\n"
body += '\nAll requested APF gates and supporting checks pass. The registry, provider integrity, catalog, packaging, installer, action parity and visual gates are unchanged. The clean staged release/runtime gates use the local dependency environment described above.\n\n'
body += '| Check | Result | Full output |\n| --- | --- | --- |\n'
for row in gates:
    body += f"| {row['name']} | PASS | [{row['name']}.log](reports/b72_a1/{row['name']}.log) |\n"
body += '\nExact gate commands are in [gates.json](reports/b72_a1/gates.json). Reproduce with `python3 reports/b72_a1/prepare_test_python.py`, then the resulting environment interpreter running `reports/b72_a1/run_gates.py`.\n\n'
body += 'The release contains 292 files with no private, retail, symlink or undeclared payload. Runtime closure checks 161 modules and 73 APF capabilities. [stage-audit.json](reports/b72_a1/stage-audit.json) confirms zero byte differences between staged files and the delivery source. [v2-receipts.json](reports/b72_a1/v2-receipts.json) records both exact generated code and data hashes.\n'
(root / 'ASTRA_REPORT.md').write_bytes(body.encode())
lines = [
    'Job b72-a1 is implemented on bundle branch b72-a1 from base 088e3f41.',
    'The delivery bundle is .scratch/astra-b72-a1.bundle.',
    'Shared Git metadata was read-only; commits use .scratch/b72-a1.git.',
    'Version 2 carries per-book, per-bucket personnel comparison rows.',
    'Policies follow resolved SPLB book names, not roster labels.',
    'Local rows range from 0 to 10; Retail row removes an override.',
    'The shared switch stays off by default in every preset.',
    'The matching v2 situation patch must be installed and enabled.',
    'Inline status distinguishes missing, matching and stale installed patches.',
    'The preview shows curve, ratings mean, product, rank and retail/effective rows.',
    'No new weight slider or lever beyond the local row was added.',
    'The native hook preserves retail arithmetic and RNG consumption.',
    'Absent, unmatched and unknown-version policies preserve retail output bytes.',
    'Both profiles fit the original data and executable reservations.',
    'All 12 buckets match native weights for both profiles and run/pass arms.',
    'Queens at rating 7 remains callable as the sole allowed formation.',
    f"All {suites['files']} standalone files and {suites['tests']} tests pass; APF gates pass.",
    'The fixture correction is Queens row 7: curve 0.5 at request 10, not 0.05.',
    'Gameplay is UNWITNESSED: test O-ManBlock 3rd-and-8, Queens / Pro: Strong.',
    'ASTRA_REPORT.md has the exact scenario and evidence; WIRING.md has registry metadata.',
]
assert len(lines) == 20
(root / 'ASTRA_LAST_MESSAGE.md').write_bytes(('\n'.join(lines)+'\nASTRA_DONE\n').encode())
print('Wrote final report and exactly 20 summary lines plus ASTRA_DONE')

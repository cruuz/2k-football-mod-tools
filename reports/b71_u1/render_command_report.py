"""Append the measured command ledger to the job report without inventing times."""
from pathlib import Path
import json

folder = Path(__file__).resolve().parent
report = folder.parents[1] / 'ASTRA_REPORT.md'
marker = '\n<!-- U1 COMMAND LEDGER -->\n'
text = report.read_text().split(marker)[0]
text += marker + '\n## Command receipts\n\n'
text += ('All shell commands after initial discovery run through `reports/b71_u1/run.py`. '
         'The JSONL ledger carries the exact command, UTC start, elapsed seconds, and exit status; '
         'each linked log contains the complete captured output. Reproduction and release-gate '
         'logs also record their child commands and statuses. Tool file edits are represented by '
         'the explicit-path commits. Initial read-only discovery receipts are transcribed from '
         'tool results below; one truncated timing is honestly unavailable.\n\n')
rows = [json.loads(line) for line in (folder/'commands.jsonl').read_text().splitlines()]
text += '| Command / output | UTC start | Seconds | Exit |\n| --- | --- | ---: | ---: |\n'
for row in rows:
    label = row['label']
    text += f"| [{label}](reports/b71_u1/{label}.log) | {row['start_utc']} | {row['seconds']} | {row['exit_code']} |\n"
text += '\n### Exact commands\n\n'
for row in rows:
    text += f"<details><summary>{row['label']}: exit {row['exit_code']}, {row['seconds']} seconds</summary>\n\n```bash\n{row['command']}\n```\n\n</details>\n\n"
text += '### Initial discovery (before the journal)\n\n'
for row in json.loads((folder/'bootstrap_commands.json').read_text()):
    duration = str(row['seconds']) + ' seconds' if row['seconds'] is not None else 'time UNWITNESSED'
    text += f"<details><summary>Exit {row['exit_code']}; {duration}</summary>\n\n```bash\n{row['command']}\n```\n\n{row.get('note','')}\n\n</details>\n\n"
report.write_text(text.rstrip() + '\n')
print(f'Rendered {len(rows)} journal entries and 12 discovery commands')

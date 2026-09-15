"""Render exact validation command records into the report appendix."""
import json
from pathlib import Path
import shlex

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).parent
records = [json.loads(line) for line in (folder / "commands.jsonl").read_text().splitlines()]
report = root / "ASTRA_REPORT.md"
prefix = report.read_text().split("<!-- COMMAND_RESULTS -->")[0]
lines = ["<!-- COMMAND_RESULTS -->", "", "| UTC start | Seconds | Exit | Command | Output |",
         "| --- | ---: | ---: | --- | --- |"]
for row in sorted(records, key=lambda item: item["started_utc"]):
    command = shlex.join(row["command"]).replace("\n", "\\n").replace("|", "\\|").replace("`", "&#96;")
    lines.append(f'| {row["started_utc"]} | {row["elapsed_seconds"]:.3f} | {row["exit_code"]} | `{command}` | [{Path(row["log"]).stem}]({row["log"]}) |')
report.write_bytes((prefix + "\n".join(lines) + "\n").encode())
print(f"Rendered {len(records)} command records; post-report delivery commands have their separate receipt.")

"""Check proposed protected wiring without hiding baseline strict failures."""
import json
from pathlib import Path
from mod_editor.capabilities.validate_registry import validate_data, _local_path

root = Path(__file__).resolve().parents[2]
document = json.loads((root / "mod_editor/capabilities/registry.v1.json").read_text())
updates = json.loads((root / "docs/research/apf_b71_situations_registry.json").read_text())
by_id = {row["id"]: row for row in document["capabilities"]}
assert len(by_id) == 174 and len(updates) == 5
assert all(row["id"] in by_id for row in updates)
by_id.update({row["id"]: row for row in updates})
document["capabilities"] = sorted(by_id.values(), key=lambda row: row["id"])
validate_data(document, check_files=False)
for row in updates:
    for path in row["evidence"]:
        _local_path(path, row["id"])
print("Proposed schema and all replacement-row evidence paths pass: 5 replacements, 0 additions, 174 total.")
print("This is not strict registry validation. Missing baseline evidence remains a separate failed gate.")

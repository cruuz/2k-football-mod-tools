# APF-2 protected registry integration

Only `mod_editor/capabilities/registry.v1.json` needs protected wiring.
All APF application changes and the APF release allowlist change are implemented
in the worktree. No protected GUI, build owner, release check, installer test,
registry file or unrelated game writer was edited.

## Replace five existing rows, add zero rows

At the root `capabilities` array, replace rows by their exact `id` using
[`docs/research/apf_b71_situations_registry.json`](docs/research/apf_b71_situations_registry.json).
This file contains the complete replacement objects. The five IDs are:

- `apf2k8.playbooks.cpu_playcalling`
- `apf2k8.playbooks.identity`
- `apf2k8.playbooks.offensive_schemes`
- `apf2k8.playbooks.scheme_presets`
- `apf2k8.playbooks.scheme_spreadsheet`

The scheme rows remain available to legacy recipes and scripts but stop claiming
visible controls in the integrated editor. The CPU row explicitly says shared
membership edits affect every situation and independent per-situation whitelists
are not implemented. Runtime status remains not-tested / UNWITNESSED.

Exact merge code, from the repository root:

```python
import json
from pathlib import Path
path = Path("mod_editor/capabilities/registry.v1.json")
document = json.loads(path.read_text(encoding="utf-8"))
updates = json.loads(Path("docs/research/apf_b71_situations_registry.json").read_text(encoding="utf-8"))
by_id = {row["id"]: row for row in document["capabilities"]}
assert len(by_id) == 174
assert len(updates) == 5
assert all(row["id"] in by_id for row in updates)
by_id.update({row["id"]: row for row in updates})
document["capabilities"] = sorted(by_id.values(), key=lambda row: row["id"])
assert len(document["capabilities"]) == 174
path.write_bytes((json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"))
```

The registry count remains **174**; change no count pins. Re-run
`python3 packaging/repin.py --apply` and strict
`python3 -m mod_editor.capabilities.validate_registry` after integration.
The input worktree's missing baseline evidence is recorded in `ASTRA_REPORT.md`;
the proposed schema/new-evidence check does not replace that strict gate.

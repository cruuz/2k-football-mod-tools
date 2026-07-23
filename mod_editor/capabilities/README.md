# Capability registry

This directory is the fail-closed contract between reverse-engineering
evidence and the public mod-editor GUI.

- [`registry.v1.json`](registry.v1.json) is the canonical capability data.
- [`registry.schema.json`](registry.schema.json) is the JSON Schema contract.
- [`validate_registry.py`](validate_registry.py) performs stricter semantic,
  local-file, coverage, GUI-safety, and canonical-encoding checks using only
  the Python standard library.
- [`test_registry.py`](test_registry.py) covers negative/tamper cases.
- [`ROADMAP.md`](ROADMAP.md) translates the registry into a public release
  sequence and explains the boundary between data mods, executable patches,
  emulator-only work, and a native port.

Validate before loading the registry in the GUI:

```bash
bash mod_editor/capabilities/validate.sh
```

The schema id is `vc_mod_capability_registry/v1`. A consumer must fail closed
on any other version rather than guessing compatibility.

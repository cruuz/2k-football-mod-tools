# Beta 72 a1 integration

The product implementation is complete in unprotected APF files. No new
capability row is required. Extend the existing CPU Play Calling capability;
shared and APF registry counts remain unchanged.

Protected file: `mod_editor/capabilities/registry.v1.json`.
Insertion point: capability `apf2k8.playbooks.cpu_playcalling`.
Apply this exact update to that row during integration:

```python
row['gui']['reason'] = (
    'Named-book preview, exclusions and per-book/per-bucket personnel comparison rows '
    'use explicit undoable project edits. No preset enables these policies. '
    'Install the matching v2 situation patch separately; the page checks whether '
    'the installed patch matches the project. Gameplay UNWITNESSED.'
)
row['evidence'] += [
    'docs/research/apf_b72_personnel_rows.md',
    'tests/mod_editor/test_apf_b72_personnel_rows.py',
    'tests/mod_editor/test_apf_b72_personnel_rows_native.py',
]
row['input_constraints'] += [
    'Local comparison rows 0..10 are keyed by resolved book name, one of twelve '
    'live buckets and ordinary personnel category. Unknown or absent overrides '
    'retain retail behavior. No SPLB or MASTER bytes change for local row edits.',
    'Version 2 retains the existing fixed allocation and up to 48 named books; '
    'sparse row capacity depends on book count. Full data is refused before staging.',
    'Preview exposes curve term, ratings mean, product, rank, retail weight and '
    'effective row. These are read-only factors, not independent weight sliders.',
]
```

The requested job branch is in `.scratch/b72-a1.git`, because the worktree's
shared Git metadata is read-only. Fetch the verified bundle's `b72-a1`
branch. The worktree remains attached to its original launcher branch;
no shared Git refs or other worktrees were changed.

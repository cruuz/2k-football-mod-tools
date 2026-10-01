#!/usr/bin/env python3
"""Conservative source audit of shipped Build data; no imports or disc access.

Walk every shipped Python module (a superset of registry Build backends), resolve
literal data paths and unique path components, and expand directories to cover
computed filenames. Report the registry/backend and BuildPlan coverage alongside
all readers. This is a static closure, not a proof of arbitrary Python execution.
Reviewed non-runtime files stay explicit; new directory contents fail closed.
"""
from __future__ import annotations
import argparse
import ast
from collections import defaultdict
import json
from pathlib import Path

# These belong to development-only branches, not the installed Build route.
EXCLUDED = {
    "data/nfl2k5_modern_helmets/geometry_speedflex.json": "Research SpeedFlex geometry; released apply uses the other pinned profile.",
    "data/nfl2k5_modern_helmets/pins_speedflex.json": "Research SpeedFlex pins; not the released profile.",
    "data/nfl2k5_scorebug_assets/atlas_2026_preview.png": "Development preview, never read by Build.",
    "data/nfl2k5_scorebug_assets/espn_glyphs.json": "Legacy _sources font authoring helper; Build uses the shipped MNF/template fonts.",
    "data/nfl2k5_scorebug_assets/espn_glyphs.png": "Legacy _sources font authoring helper; not Build input.",
    "data/nfl2k5_scorebug_assets/espn_wordmark.png": "Legacy atlas_2026 authoring helper; not Build input or a release mark.",
}
# Exact legacy atlas roster, not a wildcard that could hide a new runtime file.
for stem in 'ari atl bal buf car chi cin cle dal den det gb hou ind jax kc lac lar lv mia min ne no nyg nyj phi pit sea sf tb ten wsh'.split():
    EXCLUDED[f'data/nfl2k5_scorebug_assets/logos/{stem}.png'] = 'Legacy atlas_2026 authoring helper; Build uses reviewed template artwork.'


def audit(root: Path, allowlist: Path) -> dict:
    entries = {s.strip() for s in allowlist.read_text().splitlines() if s.strip() and not s.startswith('#')}
    def allowed(path):
        return path in entries or any(path.startswith(p) for p in entries if p.endswith('/'))
    sources = sorted(p for base in ('mod_editor', 'tools') for p in (root/base).rglob('*.py')
                     if allowed(p.relative_to(root).as_posix()))
    by_name = defaultdict(list)
    for base in ('data', 'mod_editor/data'):
        for p in (root/base).rglob('*'):
            by_name[p.name].append(p)
    readers = defaultdict(set)
    for source in sources:
        tree = ast.parse(source.read_text())
        parents = {id(child): node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            parent = parents.get(id(node))
            if isinstance(parent, ast.Expr):  # docstrings are not data reads
                continue
            candidates = []
            if value.startswith(('data/', 'mod_editor/data/')):
                candidates = [root/value]
            elif isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div) and len(by_name[value]) == 1:
                candidates = by_name[value]
            for path in candidates:
                files = sorted(path.rglob('*')) if path.is_dir() else [path]
                for file in files:
                    if file.is_dir() or '__pycache__' in file.parts:
                        continue
                    readers[file.relative_to(root).as_posix()].add(source.relative_to(root).as_posix())
    registry = json.loads((root/'mod_editor/capabilities/registry.v1.json').read_text())['capabilities']
    backends = {c['id']: c.get('backend', {}).get('module') for c in registry
                if allowed(c.get('backend', {}).get('module') or '')}
    plan_tree = ast.parse((root/'mod_editor/core/mod_build.py').read_text())
    plan = next(n for n in plan_tree.body if isinstance(n, ast.ClassDef) and n.name == 'BuildPlan')
    fields = [n.target.id for n in plan.body if isinstance(n, ast.AnnAssign)]
    # The file chooser passes pack paths into BuildPlan, so the reader has no
    # literal directory to discover. Audit the shipped library for that field.
    dynamic_inputs = {'playbook_packs': 'data/playbooks'}
    for field, directory in dynamic_inputs.items():
        if field in fields and allowed('mod_editor/core/mod_build.py'):
            for file in sorted((root/directory).rglob('*')):
                if file.is_file():
                    readers[file.relative_to(root).as_posix()].add('mod_editor/core/mod_build.py')
    missing = {p: sorted(modules) for p, modules in sorted(readers.items()) if p not in EXCLUDED and (not allowed(p) or not (root/p).is_file())}
    return dict(schema=1, scope='All shipped Python sources, including registry backends and BuildPlan readers; literal paths and directory expansion.',
                buildplan_fields=fields, dynamic_input_libraries=dynamic_inputs, registry_shipped_backends=backends, modules_scanned=len(sources),
                data_files_checked=len(readers), missing=missing,
                exclusions={p: reason for p, reason in EXCLUDED.items() if p in readers},
                readers={p: sorted(v) for p, v in sorted(readers.items())})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--allowlist', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    report = audit(args.root.resolve(), args.allowlist or args.root/'packaging/release-allowlist.txt')
    if args.json:
        args.json.write_text(json.dumps(report, indent=2)+'\n', newline="\n")
    print(f"BUILD_DATA_ALLOWLIST modules={report['modules_scanned']} registry_backends={len(report['registry_shipped_backends'])} build_fields={len(report['buildplan_fields'])} data_files={report['data_files_checked']} exclusions={len(report['exclusions'])} missing={len(report['missing'])}")
    for path, readers in report['missing'].items():
        print(path + ': ' + ', '.join(readers))
    return bool(report['missing'])

if __name__ == '__main__':
    raise SystemExit(main())

"""Narrow-diff, palette, native budget, inventory and policy scans."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import fit as F


def old(path):
    return subprocess.check_output(['git', 'show', F.BASE+':'+path], cwd=F.ROOT)


def main():
    unchanged = {}
    names = ['data/nfl2k5_scorebug_sprite/template.png',
        'data/nfl2k5_scorebug_sprite/team_colors_official_2026.json',
        'data/nfl2k5_cave_reservations.json', 'tools/scorebug_sprite/runtime.c',
        'mod_editor/core/nfl2k5_scorebug_sprite_code.py',
        'mod_editor/core/nfl2k5_scorebug_runtime.py', 'mod_editor/core/nfl2k5_scorebug_sprite.py',
        'mod_editor/core/nfl2k5_scorebug_exact.py', 'mod_editor/core/nfl2k5_scorebug_resources.py',
        'mod_editor/core/nfl2k5_scorebug_teams.py', 'mod_editor/core/providers.py',
        'packaging/release-allowlist.txt', 'packaging/apf2k8-release-allowlist.txt',
        'packaging/check_2k5_mod_studio_release.py', 'packaging/nfl2k5_scorebug_template_pngs.json',
        'tests/mod_editor/test_provider_integrity.py']
    for path in names:
        data = (F.ROOT/path).read_bytes()
        assert data == old(path), path
        unchanged[path] = hashlib.sha256(data).hexdigest()
    for name in ('layout.json', 'team_accents.json'):
        path = 'data/nfl2k5_scorebug_sprite/'+name
        before, after = json.loads(old(path)), json.loads((F.ROOT/path).read_text())
        if name == 'layout.json':
            before.pop('logo_fit'); after.pop('logo_fit')
        else:
            for data in (before, after):
                for team in data['teams'].values():
                    team.pop('logo_fit', None)
        assert before == after, 'Non-logo mutation: '+path
    allowed = set((F.ROOT/'packaging/release-allowlist.txt').read_text().splitlines())
    shipping = ['data/nfl2k5_scorebug_sprite/layout.json', 'data/nfl2k5_scorebug_sprite/team_accents.json',
        'packaging/scorebug_replication_pins.py', 'docs/mod_editor/2k5_mod_studio_changelog.md']
    assert all(path in allowed for path in shipping)
    diff = subprocess.check_output(['git', 'diff', F.BASE, '--'], cwd=F.ROOT, text=True)
    added = '\n'.join(line[1:] for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))
    assert '\u2014' not in added
    patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                r'\bgh[pousr]_[A-Za-z0-9]{30,}', r'\bsk-[A-Za-z0-9_-]{30,}']
    hits = []
    for path in list(F.OUT.rglob('*'))+[F.ROOT/'ASTRA_REPORT.md', F.ROOT/'ASTRA_LAST_MESSAGE.md', F.ROOT/'WIRING.md']:
        if path.is_file() and path.suffix in ('.py', '.md', '.json', '.jsonl', '.log', '.txt') and path.name != 'scan.py':
            data = path.read_text(encoding='utf-8')
            assert '\u2014' not in data, path
            for pattern in patterns:
                if re.search(pattern, data):
                    hits.append(path.relative_to(F.ROOT).as_posix())
    assert not hits, hits
    F.write('scans.json', dict(base=F.BASE, unchanged_sha256=unchanged,
        only_logo_fit_changes=True, palette_fields_unchanged=True, existing_allowlist_paths=shipping,
        new_inventory_entries=0, new_provider_modules=0, secret_pattern_hits=hits, new_em_dashes=0,
        retail_policy='No retail resources retained; product closure runs its retained-byte policy audit.'))
    print('PASS: only logo fits changed; palettes, template, native owners, inventories and provider sources unchanged.')


if __name__ == '__main__':
    main()

"""Index every APF protected-file handoff against the integrated source tree."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
p = ROOT / 'reports/b71_a6/wiring-locations.json'
rows = json.loads(p.read_text())
seen = {(r['path'], r['anchor']) for r in rows}
extra = {
    'mod_editor/capabilities/registry.v1.json': [
        '"id": "apf2k8.playbooks.' + name + '"'
        for name in ('identity', 'offensive_schemes', 'scheme_presets', 'scheme_spreadsheet')
    ],
    'packaging/apf2k8-release-allowlist.txt': [
        'mod_editor/apf_studio/situation_masks.py',
        'mod_editor/apf_studio/situation_mask_qt.py',
        'docs/research/apf_b71_apf3.md',
        'docs/research/apf_b71_apf4.md',
        'mod_editor/apf_studio/fourth_down_qt.py',
        'docs/mod_editor/apf2k8_fourth_down_and_xenia.md',
        'docs/research/apf_b71_fourth_down.md',
    ],
    'data/apf2k8/patch_reservations.json': [
        '"end_inclusive": "0x84D0E2FF"',
        '"owner": "apf2k8_situation_mask_data"',
        '"owner": "apf2k8_situation_mask_code"',
        '"owner": "apf2k8_situation_mask_receipts"',
    ],
    'packaging/check_apf2k8_mod_studio_runtime.py': [
        '"mod_editor.core.apf2k8_fourth_down"',
        '"mod_editor.apf_studio.fourth_down_qt"',
        "'mod_editor.core.apf2k8_situation_mask'",
        "'mod_editor.apf_studio.situation_masks'",
        "'mod_editor.apf_studio.situation_mask_qt'",
        'expected = {"apf2k8_situation_mask_data"',
        'mask.verify_code(profile,code)',
        'Situation canonical export changed',
        'Situation masks must start off',
    ],
    'mod_editor/apf_studio/models.py': [
        'one_shot_target="mod_editor.core.apf2k8_fourth_down:write_patch"',
    ],
    'mod_editor/apf_studio/gui.py': [
        'self.fourth_down_action =', 'def _fourth_down_triggers', 'def _configure_xenia',
    ],
    'mod_editor/apf_studio/launcher.py': [
        '"edge": "xenia-edge.config.toml"', 'def write_controller_config', 'def _sdl_config',
    ],
    'mod_editor/core/apf2k8_xex.py': [
        'def xenia_content_roots', 'for name in ("xenia-edge.config.toml"',
    ],
}
for path, anchors in extra.items():
    lines = (ROOT / path).read_text().splitlines()
    for anchor in anchors:
        numbers = [i for i, line in enumerate(lines, 1) if anchor in line]
        assert numbers, (path, anchor)
        if (path, anchor) not in seen:
            rows.append(dict(path=path, anchor=anchor, lines=numbers))
for row in rows:
    lines = (ROOT / row['path']).read_text().splitlines()
    assert row['lines'] == [i for i, line in enumerate(lines, 1) if row['anchor'] in line], row
p.write_text(json.dumps(rows, indent=2) + '\n')
print('Wiring anchors:', len(rows), '; all current line references verified')

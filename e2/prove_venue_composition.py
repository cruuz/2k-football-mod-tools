"""PROVED OFFLINE: compare disabled executable output with e7d7aca5, no disc build."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_moment_venues as venues
from mod_editor.core import nfl2k5_espn25_more_moments as moments


def main():
    source = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')
    payload = source.read_bytes()
    old = types.ModuleType('mod_editor.core._e2p3_baseline')
    old.__file__, old.__package__ = tt.__file__, 'mod_editor.core'
    sys.modules[old.__name__] = old
    code = subprocess.check_output(['git', 'show', 'e7d7aca5:mod_editor/core/nfl2k5_throw_tuning.py'], cwd=ROOT)
    exec(compile(code, old.__file__, 'exec'), old.__dict__)
    options = dict(catch_slider=False, scheme_labels=True, practice_squad=True, franchise_practice=True,
                   depth_locks=True, espn25_more_moments=True, historic_stock_books=True,
                   historic_teams_quick_game=True)
    before, _ = old._apply_all(payload, None, **options)
    off, _ = tt._apply_all(payload, None, espn25_named_previews=False, **options)
    assert before == off
    on, _ = tt._apply_all(payload, None, espn25_named_previews=True, **options)
    assert venues.status(on) == moments.status(on) == 'applied'
    report = dict(classification='PROVED OFFLINE', base='e7d7aca5', off_byte_identical=True,
                  off_sha256=hashlib.sha256(off).hexdigest(), on_sha256=hashlib.sha256(on).hexdigest(),
                  on_status=venues.status(on), options=options, allocation=venues.allocation(on))
    (ROOT / 'e2/evidence/e2p3/option-composition.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()

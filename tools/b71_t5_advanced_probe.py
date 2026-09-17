"""Real Advanced preflight and first XBE pass, entirely in memory.

No source bytes, executable or disc copy are written to the worktree.
The later archive passes and complete playable disc remain unwitnessed.
"""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build as build


class FirstPassComplete(Exception):
    pass


def run():
    source = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
    plan = build.apply_preset(build.BuildPlan(str(source), str(ROOT/'.scratch/not-written.iso')),
                              'softdrink_advanced')
    started = time.monotonic()
    preflight = build.preflight_plan(plan)
    result = dict(preflight_seconds=time.monotonic()-started, preset='softdrink_advanced')
    original = build._xbe_bytes(source)
    def first_pass(source, target, **kwargs):
        options = {k:v for k,v in kwargs.items() if k in inspect.signature(build.tt._apply_all).parameters}
        settings = kwargs.get('settings')
        options['wanted'] = build.tt._resolve_wanted(settings, None) if settings is not None else None
        options['arc_table'] = bool(settings is not None and settings.arc_by_distance)
        options['_defer_runtime_settings'] = True
        started = time.monotonic()
        after, receipt = build.tt._apply_all(original, **options)
        result.update(first_pass_seconds=time.monotonic()-started,
                      before_sha256=hashlib.sha256(original).hexdigest(),
                      after_sha256=hashlib.sha256(after).hexdigest(),
                      changed_bytes=sum(a!=b for a,b in zip(original,after)),
                      output_written=False, later_disc_passes='UNWITNESSED')
        raise FirstPassComplete()
    with patch.object(build.tt, 'write_copy', side_effect=first_pass):
        try:
            build._build(plan)
        except FirstPassComplete:
            pass
    assert not Path(plan.target).exists()
    assert result['changed_bytes'] > 0
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__':
    run()

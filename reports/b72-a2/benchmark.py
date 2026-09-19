"""Offline repeated-validation benchmark against the local O-ManBlock fixture."""
import json
from pathlib import Path
import statistics
import sys
import tempfile
import subprocess
import types
import time
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio.session import ApfSession
from mod_editor.apf_studio.models import ApfSource
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_package_map_writer import PackageMapChange, list_apf_formations, swap_te_and_wr
from mod_editor.core.apf2k8_playbook_route_writer import RouteCloneRequest

if '--baseline' in sys.argv:
    name = 'mod_editor.apf_studio._b72_baseline_session'
    baseline = types.ModuleType(name)
    baseline.__package__ = 'mod_editor.apf_studio'
    sys.modules[name] = baseline
    source_text = subprocess.check_output(['git', 'show', '088e3f41:mod_editor/apf_studio/session.py'], text=True)
    exec(compile(source_text, '<baseline-session>', 'exec'), baseline.__dict__)
    ApfSession = baseline.ApfSession
index = Path('extracted/All-Pro Football 2K8 (USA)/0A').resolve()
source = ApfSource(index, index.parent, index, 'a'*64, index.stat().st_size, 'b'*64, 'Offline fixture')
with tempfile.TemporaryDirectory() as temp:
    session = ApfSession(source, SimpleNamespace(), cache_root=Path(temp))
    book = splb.read_book(index, 130)
    record = book.records[0]
    holder = next(e.play_index for e in record.entries if e.y == 1)
    move = splb.TagMove(130, 0, holder, record.entries[0].play_index)
    body = session._master_play_body()
    forms = list_apf_formations(body)
    session.apply_package_map_batch((PackageMapChange(0, swap_te_and_wr(forms[0][2])),))
    # A two-way swap preserves all chain starts.
    session.swap_play_assignment_routes(0, 0, 1, 0)
    actions = {'Fine-tune Plays': lambda: session._compile_splb_groups((move,)),
               'Who lines up': session._compile_master_play,
               'Assignment Routes': lambda: session.relay_play_assignment_route_candidates(0, 1, 1, 1)}
    results = {}
    for label, action in actions.items():
        action()
        samples = []
        for _ in range(5):
            start = time.perf_counter()
            action()
            samples.append((time.perf_counter()-start)*1000)
        results[label] = {'median_ms': statistics.median(samples), 'max_ms': max(samples), 'samples_ms': samples}
    print(json.dumps({'book': book.name, 'outer':130, 'iterations':5, 'timings':results}, indent=2))

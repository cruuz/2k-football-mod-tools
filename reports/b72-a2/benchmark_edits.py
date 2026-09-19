"""Ten real O-ManBlock membership edits, using the old and new Qt panels."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
from types import SimpleNamespace as NS
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio import session as current_session
from mod_editor.apf_studio import playbook_membership_qt as current_panel
from mod_editor.apf_studio.models import ApfSource
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body, _parse


def baseline(name):
    path = 'mod_editor/apf_studio/' + name + '.py'
    module = types.ModuleType('mod_editor.apf_studio._b72_before_' + name)
    module.__package__ = 'mod_editor.apf_studio'
    sys.modules[module.__name__] = module
    source = subprocess.check_output(['git', 'show', '088e3f41:' + path], text=True)
    exec(compile(source, '<before-' + name + '>', 'exec'), module.__dict__)
    return module


app = QApplication.instance() or QApplication([])
index = ROOT/'extracted/All-Pro Football 2K8 (USA)/0A'
source = ApfSource(index, index.parent, index, 'a'*64, index.stat().st_size, 'b'*64, 'Offline fixture')
book = splb.read_book(index, 130)
inventory = _parse(read_master_play_body(index))
record = book.records[0]
existing = {entry.play_index for entry in record.entries}
additions = [i for i in range(586) if i not in existing][:10]
assert len(record.entries)+len(additions) <= splb.ENTRY_CAPACITY
out = {}
for version, session_module, panel_module in [('before', baseline('session'), baseline('playbook_membership_qt')),
                                              ('after', current_session, current_panel)]:
    with tempfile.TemporaryDirectory() as temp:
        session = session_module.ApfSession(source, NS(), cache_root=Path(temp))
        facade = NS(session=session, source_ready=True, source=source, book_choices={130: 'O-ManBlock'},
                    staged_splb_changes=session.staged_splb_changes, staged_splb_outers=session.staged_splb_outers,
                    stage_splb_membership=session.apply_splb_membership_batch)
        if version == 'after':
            facade.compiled_splb_book = session.compiled_splb_book
            session._splb_books[130] = book
        panel = panel_module.ApfPlaybookMembershipPanel(facade, lambda *_: None)
        panel._book, panel._loaded_index = book, index
        panel._plays = [p['name'] for p in inventory['plays']]
        panel._formations = {f['index']: f['name'] for f in inventory['formations']}
        panel._refresh_formations()
        if version == 'after':
            panel.queue_edits.setChecked(True)
        app.processEvents()
        samples = []
        with patch.object(splb.apf_inner, 'encode_h7a_preserving_tokens', side_effect=AssertionError('staging must not encode')):
            for play in additions:
                start = time.perf_counter()
                panel.stage_membership(0, play, True)
                panel.set_context()
                samples.append((time.perf_counter()-start)*1000)
        changes = panel.staged_changes()
        confirm_start = time.perf_counter()
        if version == 'after':
            session.apply_splb_membership_batch(changes, replace_outer=130)
        confirm_ms = (time.perf_counter()-confirm_start)*1000
        compiled = splb.compile_book(book, changes)
        out[version] = {'book': book.name, 'edits': len(additions), 'edit_ms': samples,
                        'total_edit_ms': sum(samples), 'confirm_ms': confirm_ms,
                        'replacement_sha256': hashlib.sha256(compiled.replacement).hexdigest()}
        panel.deleteLater()
assert out['before']['replacement_sha256'] == out['after']['replacement_sha256']
print(json.dumps(out, indent=2))

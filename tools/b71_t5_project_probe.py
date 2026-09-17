"""600 authored replacements, historical loaders, real codecs, synthetic packs.

Archive/catalog I/O uses a bounded synthetic three-reference TSET in 200 sets.
No retail bytes. Each normal/mud/sock item has distinct authored colours.
"""
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from b70_equipment_fixture import SizedFixture
from b71_t4_equipment_probe import historical
from mod_editor.core import nfl2k5_uniform_equipment_writer as current_writer
from mod_editor.core import nfl2k5_equipment_lz as current_lz
from mod_editor.studio import session as current_session
from mod_editor.studio import project_archive as current_archive
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
from nfl_txtr import encode_rgba_png
from nfl_tset_png_import import decode_rgba_png


class Corpus:
    def __init__(self, root, count=600):
        self.root = root
        self.fixture = SizedFixture(root, width=32, family=4, margin=1200,
                                   names=('socks00', 'socks00_mud', 'shoes09'))
        self.rows = tuple(replace(row, outer_index=n, set_selector=f'{n%32:02}H{n//32}')
                          for n in range((count+2)//3) for row in self.fixture.rows)[:count]
        self.targets = {row.asset_id: row for row in self.rows}
        self.groups = {}
        for row in self.rows:
            self.groups.setdefault((row.outer_index, row.chunk_index), []).append(row)
        self.assets = {row.asset_id: SimpleNamespace(asset_id=row.asset_id,
            dimensions=(32, 32), width=32, height=32, kind='uniform_equipment_texture',
            label=f'{row.set_selector} / {row.name}', editable=True) for row in self.rows}
        self.catalog = SimpleNamespace(get_asset=lambda key: self.assets[key])
        self.cache = SimpleNamespace(pack0=root/'0', root=root/'cache', source=SimpleNamespace(sha256='a'*64))
        self.original = root/'original.png'
        self.original.write_bytes(encode_rgba_png(32,32,bytes((0,0,0,255))*1024))
        corpus = self
        class IO:
            def __init__(self, cache=None):
                pass
            def validate_replacement(self, asset, path):
                data = Path(path).read_bytes()
                return data, decode_rgba_png(data, asset.dimensions)[2]
            def ensure_original(self, asset):
                return corpus.original
        self.io = IO
        self.edits = []
        for n, row in enumerate(self.rows):
            rgba = b''.join(bytes(((n*13+x*3)%251, (n*7+y*11)%251, (n+y//4)%251, 255))
                            for y in range(32) for x in range(32))
            path = root/f'art-{n}.png'
            path.write_bytes(with_import_mode(encode_rgba_png(32,32,rgba), row.asset_id, rgba,
                                             independent=row.reference_index < 2))
            self.edits.append(SimpleNamespace(asset_id=row.asset_id, replacement_path=path,
                replacement_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                rgba_sha256=hashlib.sha256(rgba).hexdigest()))
        self.project = root/'many.2k5mod'
        current_archive.save_project_archive(catalog=self.catalog,asset_io=IO(),edits=self.edits,destination=self.project)

    def context(self, writer=current_writer):
        stack = ExitStack()
        f = self.fixture
        segment = SimpleNamespace(pack_ordinal=0,pack_offset=128,size=len(f.span))
        archive = SimpleNamespace(entries=[SimpleNamespace(size=len(f.span),segments=[segment]) for _ in self.groups],
            packs=[SimpleNamespace(name='pack',path=f.pack,size=len(f.span))])
        for name, value in [('load_targets',lambda *args: (self.targets,{k:tuple(v) for k,v in self.groups.items()})),
                            ('parse_archive',lambda *args: archive),('read_entry_bytes',lambda *args:f.span),
                            ('_chain_pins',lambda:{k:hashlib.sha256(f.span).hexdigest() for k in self.groups})]:
            stack.enter_context(patch.object(writer,name,side_effect=value))
        parse = writer.parse_chunks
        stack.enter_context(patch.object(writer,'parse_chunks',side_effect=lambda data,**kw:
            [f.chunk] if kw.get('allow_trailing') else parse(data,**kw)))
        return stack

    def session(self, module=current_session, name='opened'):
        with patch.object(module, 'Nfl2k5ProductVisualIO', self.io):
            session = module.StudioSession(self.cache,self.catalog,root=self.root/'sessions',session_id=name)
        session.attach_visual_catalog(self.catalog)
        return session


def run(revision, count=600):
    with tempfile.TemporaryDirectory(prefix='b71-t5-probe-') as folder, ExitStack() as stack:
        corpus = Corpus(Path(folder),count)
        if revision == 'after':
            writer, session = current_writer, current_session
        else:
            writer = historical(revision,'mod_editor/core/nfl2k5_uniform_equipment_writer.py','t5_writer')
            lz = historical(revision,'mod_editor/core/nfl2k5_equipment_lz.py','t5_lz')
            session = historical(revision,'mod_editor/studio/session.py','mod_editor.studio.t5_session')
            archive = historical(revision,'mod_editor/studio/project_archive.py','mod_editor.studio.t5_archive')
            stack.enter_context(patch.object(session,'load_project_archive',archive.load_project_archive))
            stack.enter_context(patch.object(current_writer,'preflight_project_equipment',writer.preflight_project_equipment))
            stack.enter_context(patch.object(current_lz,'compress_equipment_optimal',lz.compress_equipment_optimal))
        stack.enter_context(corpus.context(writer))
        if writer is not current_writer:
            stack.enter_context(corpus.context())
        phase = {}
        for owner, name in [(session,'load_project_archive'),
                            (writer,'_compile_group'),(writer,'compress_vc_lz'),(current_lz,'compress_equipment_optimal'),
                            (writer,'_quantize_art'),(writer,'_read_png'),(writer,'_stage_compiler_key')]:
            if not hasattr(owner, name):
                continue
            original = getattr(owner,name)
            def measured(*a,_fn=original,_name=name,**kw):
                start=time.monotonic()
                row=phase.setdefault(_name,dict(calls=0,seconds=0))
                row['calls']+=1
                try:return _fn(*a,**kw)
                finally:row['seconds']+=time.monotonic()-start
            stack.enter_context(patch.object(owner,name,side_effect=measured))
        opened = corpus.session(session)
        before=hashlib.sha256(corpus.project.read_bytes()).hexdigest()
        start=time.monotonic()
        try:
            outcome=dict(count=opened.load_shareable_project(corpus.project),outcome='opened')
        except Exception as exc:
            outcome=dict(outcome='refused',error=str(exc))
        outcome.update(revision=revision,seconds=time.monotonic()-start,phases=phase,
            source_unchanged=before==hashlib.sha256(corpus.project.read_bytes()).hexdigest(),
            replacements=count,fixture='synthetic TSETs, real PNGs/codecs/loader; no retail package I/O')
        print(json.dumps(outcome,indent=2),flush=True)
        return outcome

if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv)>1 else 'after',int(sys.argv[2]) if len(sys.argv)>2 else 600)

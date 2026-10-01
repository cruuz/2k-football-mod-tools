"""Synthetic N1/N2 against the exact job base, never a disc build."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tests/mod_editor')]
from test_b76_ed1_large_projects import Corpus, measurements, fit
from test_b76_ed1_large_projects import SizedFixture, visual, reporting, palette
import test_nfl2k5_equipment_texture_chain as fixture_module

BASE = '6bd9b3d66d239a267f8d4f66e083b8a6eb320671'


def historical(path, name):
    source = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
    module = types.ModuleType(name)
    module.__file__ = str(ROOT/path)
    sys.modules[name] = module
    exec(compile(source, str(ROOT/path), 'exec'), module.__dict__)
    return module


archive = historical('mod_editor/studio/project_archive.py', 'mod_editor.studio.ed1_old_archive')
models = historical('mod_editor/core/nfl2k5_model_project_session.py', 'mod_editor.core.ed1_old_models')
models.archive = archive
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    corpus = Corpus(root, 600)
    rows = measurements(corpus)
    receipts = {fit.digest([generation, n]): rows[n:n+3]
                for generation in range(100) for n in range(0, len(rows), 3)}
    path = root/'beta75-writer.2k5mod'
    archive.save_project_archive(catalog=corpus.catalog, asset_io=corpus.io(),
        edits=corpus.edits, destination=path, fit_receipts=receipts,
        uniform_colors=[dict(selector=f'{n%32:02}H{n//32}', facemask='FF112233',
                             turtleneck='FF445566') for n in range(200)])
    with zipfile.ZipFile(path) as zipped:
        size = zipped.getinfo('project.json').file_size
    assert size > 16 * 1024**2, size
    print(f'PROVED OFFLINE: baseline save succeeded, project.json={size} bytes, '
          '600 textures, 200 colour records, 100 fit generations.', flush=True)
    for name, operation in (
        ('Models precheck', lambda: models._read_models(path)),
        ('Base loader', lambda: archive.load_project_archive(source=path,
            catalog=corpus.catalog, asset_io=corpus.io(), private_root=root/'private')),
    ):
        try:
            operation()
        except archive.ValidationError as exc:
            assert 'too large' in str(exc), str(exc)
            print(f'PROVED OFFLINE: {name} rejected its own saved file: {exc}', flush=True)
        else:
            raise AssertionError(f'{name} unexpectedly opened the baseline archive')

old_palette = historical('mod_editor/core/equipment_palette.py', 'mod_editor.core.ed1_old_palette')
old_writer = historical('mod_editor/core/nfl2k5_uniform_equipment_writer.py', 'mod_editor.core.ed1_old_writer')
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    rgba = b''.join(bytes((x, y, (x+y) % 256, 255)) for y in range(256) for x in range(256))
    (root/'old').mkdir()
    fixture = SizedFixture(root/'old', width=256, margin=4000)
    edits = [fixture.png(n, rgba=rgba, independent=False) for n in range(3)]
    with patch.object(fixture_module, 'writer', old_writer), patch.object(palette, 'quality', old_palette.quality):
        span, previews, report, _, _ = fixture.build(edits)
    old_span = hashlib.sha256(span).hexdigest()
    old_previews = [hashlib.sha256(data).hexdigest() for _, data in previews]
    metrics = [{k: v for k, v in row['palette_quality'].items() if k != 'merged_colours'} for row in report['edits']]
    payload = visual.canonical_json(visual.normalized_import_report(report,
        dict(edits=[dict(target=key, png=str(path)) for key, path in edits]), 'uniform_equipment_texture'))
    path = root/'05162_import.json'
    path.write_bytes(payload)
    print(f'PROVED OFFLINE: baseline receipt={len(payload)} bytes; '
          f'colour-change rows={[len(r["palette_quality"]["merged_colours"]) for r in report["edits"]]}.', flush=True)
    try:
        reporting._read_receipt(path)
    except archive.ValidationError as exc:
        assert 'outside 1..33554432' in str(exc)
        print(f'PROVED OFFLINE: baseline parent readback failed: {exc}', flush=True)
    else:
        raise AssertionError('Baseline receipt unexpectedly fit')
    del report, payload
    (root/'fixed').mkdir()
    fixture = SizedFixture(root/'fixed', width=256, margin=4000)
    edits = [fixture.png(n, rgba=rgba, independent=False) for n in range(3)]
    span, previews, report, _, _ = fixture.build(edits)
    assert hashlib.sha256(span).hexdigest() == old_span
    assert [hashlib.sha256(data).hexdigest() for _, data in previews] == old_previews
    for row, previous in zip(report['edits'], metrics):
        assert all(row['palette_quality'][k] == v for k, v in previous.items())
    print(f'PROVED OFFLINE: fixed replacement span SHA-256={old_span}; '
          'all three previews and aggregate quality metrics equal the baseline.', flush=True)

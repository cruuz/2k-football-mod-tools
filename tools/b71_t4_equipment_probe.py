"""Reproduce the 22H2 one-byte boundary using authored art and read-only retail.

Only authored PNGs, a replacement-only project and measurements are written.
No decoded game data or rebuilt retail spans are persisted.
"""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core import nfl2k5_equipment_lz as lz
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips
from mod_editor.core.equipment_palette import quantize
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
from mod_editor.studio.project_archive import (
    save_project_archive, load_project_archive,
)
from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import parse_chunks, decode_chunk, compress_vc_lz, encode_rgba_png
from nfl_tset_png_import import decode_rgba_png


def artwork(seed=71, speckles=34):
    rng = random.Random(seed)
    colours = ((244, 242, 232, 255), (16, 24, 32, 255), (170, 30, 40, 255))
    pixels = [colours[(y // 5) % 3] if y < 24 else colours[0]
              for y in range(64) for x in range(64)]
    for index in rng.sample(range(4096), speckles):
        pixels[index] = colours[rng.randrange(3)]
    return b''.join(bytes(c) for c in pixels)


def historical(revision, path, name):
    source = subprocess.run(['git', 'show', f'{revision}:{path}'], cwd=ROOT,
                            check=True, capture_output=True).stdout
    module = ModuleType(name)
    module.__file__ = str(ROOT / path)
    sys.modules[name] = module
    exec(compile(source, f'{revision}:{path}', 'exec'), module.__dict__)
    return module


def retail_context(index):
    by_id, groups = writer.load_targets()
    target = next(t for t in by_id.values() if t.set_selector == '22H2' and t.name == 'socks00')
    archive = parse_archive(index)
    package = read_entry_bytes(archive, archive.entries[target.outer_index])
    chunk = parse_chunks(package, allow_trailing=True)[target.chunk_index]
    span = package[chunk.offset:chunk.end_offset]
    decoded, info = decode_chunk(span, parse_chunks(span)[0])
    return target, groups[target.outer_index, target.chunk_index], chunk, span, decoded, info


def authored(target, rgba):
    levels = make_digit_mips(rgba, 64, 64, target.mip_levels)
    levels[0] = writer.replace(levels[0], rgba=rgba)
    payload = with_import_mode(encode_rgba_png(64, 64, rgba), target.asset_id, rgba, independent=True)
    return {target.reference_index: (target, payload, rgba, levels)}


def run(index, output):
    output.mkdir(parents=True, exist_ok=True)
    target, rows, chunk, span, decoded, info = retail_context(index)
    assert chunk.stored_size == 6784
    rgba = artwork()
    inputs = authored(target, rgba)
    old = historical('f7d6fc07', 'mod_editor/core/nfl2k5_uniform_equipment_writer.py', 'b71_probe_b69')
    old_lz = historical('f7d6fc07', 'mod_editor/core/nfl2k5_equipment_lz.py', 'b71_probe_b69_lz')
    beta70 = historical('3c98d433', 'mod_editor/core/nfl2k5_uniform_equipment_writer.py', 'b71_probe_b70')
    measurements = {}
    candidates = []
    old_rebuild = old._rebuild_fixed_span
    def capture(template, candidate, **kwargs):
        candidates.append(candidate)
        return old_rebuild(template, candidate, **kwargs)
    with patch.object(old, '_rebuild_fixed_span', side_effect=capture), \
         patch.object(lz, 'compress_equipment_optimal', old_lz.compress_equipment_optimal):
        accepted = old._compile_group(span, chunk, decoded, info, rows, dict(inputs), {0}, suggest_fit=False)
    candidate = candidates[-1]
    greedy, _ = compress_vc_lz(candidate, stream_tag=info.stream_tag, offset_bits=10)
    with patch.object(lz.subprocess, 'run', wraps=lz.subprocess.run) as native:
        writer._PARSE_CACHE.clear()
        optimal, strategy = writer._cached_parse(candidate, info.stream_tag, 10, chunk.stored_size)
    assert len(greedy) == 6785 and len(optimal) == 6764
    assert strategy == 'optimal_token_parse'
    assert len(accepted.rebuilt_span) == len(span) and accepted.rebuilt_span[20:24] == span[20:24]
    measurements.update(asset_id=target.asset_id, set_selector=target.set_selector,
        seed=71, speckles=34, authored_rgba_sha256=hashlib.sha256(rgba).hexdigest(),
        budget=chunk.stored_size, greedy_bytes=len(greedy), optimal_bytes=len(optimal),
        strategy=strategy,
        helper=str(lz._optimal_helper()), native_calls=native.call_count,
        beta69_filled_bytes=accepted.rebuild_info.recompressed_bytes,
        beta69_palette_limit=accepted.attempts[-1]['maximum_palette_entries'],
        span_bytes=len(span), wrapper_14_preserved=True)
    for name, context in (
        ('beta70', ExitStack()),
        ('beta70_without_stripe_floor', patch.object(beta70, '_striped_art', return_value=False)),
        ('beta70_old_quantizer_only', patch.object(beta70, '_quantize_art', quantize)),
    ):
        with context:
            try:
                fit = beta70._compile_group(span, chunk, decoded, info, rows, dict(inputs), {0}, suggest_fit=False)
            except beta70.EquipmentFitError as error:
                measurements[name] = dict(error=str(error), attempts=error.attempts)
            else:
                measurements[name] = dict(filled_bytes=fit.rebuild_info.recompressed_bytes,
                    palette_limit=fit.attempts[-1]['maximum_palette_entries'])
    assert 'error' in measurements['beta70']
    # This archive contains only the authored PNG; no original needs exporting.
    png = output / 'sock.png'
    png.write_bytes(inputs[0][1])
    asset = SimpleNamespace(asset_id=target.asset_id, label='22H2 socks00',
                            kind='uniform_equipment_texture', dimensions=(64, 64))
    catalog = SimpleNamespace(get_asset=lambda asset_id: asset)
    class ArtIO:
        def validate_replacement(self, asset, path):
            payload = Path(path).read_bytes()
            return payload, decode_rgba_png(payload, asset.dimensions)[2]
        def ensure_original(self, asset):
            # A synthetic comparison PNG is used only by save's no-op gate.
            return comparison
    with tempfile.TemporaryDirectory(prefix='b71-t4-project-') as temporary:
        comparison = Path(temporary) / 'comparison.png'
        comparison.write_bytes(encode_rgba_png(64, 64, bytes((0, 0, 0, 255)) * 4096))
        project = output / 'one-byte.2k5mod'
        save_project_archive(catalog=catalog, asset_io=ArtIO(),
            edits=[SimpleNamespace(asset_id=target.asset_id, replacement_path=png,
                replacement_sha256=hashlib.sha256(png.read_bytes()).hexdigest(),
                rgba_sha256=hashlib.sha256(rgba).hexdigest())], destination=project,
            replace=project.exists())
        loaded = load_project_archive(source=project, catalog=catalog,
                                       asset_io=ArtIO(), private_root=Path(temporary))
        try:
            assert len(loaded.edits) == 1
            assert loaded.edits[0].staged_path.read_bytes() == png.read_bytes()
        finally:
            loaded.cleanup()
    measurements['project'] = project.name
    measurements['in_game_outcome'] = 'UNWITNESSED'
    (output / 'measurements.json').write_text(json.dumps(measurements, indent=2) + '\n')
    return measurements


if __name__ == '__main__':
    index = ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
    result = run(index, ROOT / 'reports/b71_t4/reproduction')
    print(json.dumps({k: v for k, v in result.items() if not isinstance(v, dict)}, indent=2))

"""Byte identity, one ladder, proven capacity, and project reuse regressions."""
from pathlib import Path
import os
import random
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
import pytest
from b72_quantizer_oracle import quantize_art as old_quantize
from b72_lz_oracle import compress_vc_lz as old_compress
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips
from mod_editor.core import equipment_palette as palette
from tools.bench.b72.b72_speed_bench import photo, sheet, stripes
from b70_equipment_fixture import CASES, stage_case
from nfl_txtr import compress_vc_lz, TxtrError


@pytest.mark.parametrize('rgba,width', [
    (photo(32), 32), (sheet(32), 32), (stripes(32), 32),
    (random.Random(72).randbytes(32 * 32 * 4), 32),
    (bytes((0, 0, 0, 0, 255, 255, 255, 0)) * 512, 32),
    (b''.join(bytes((i % 256, (i * 17) % 256, (i * 31) % 256, 255)) for i in range(1024)), 32),
])
def test_quantizer_bit_exact_six_fixtures(rgba, width):
    levels = make_digit_mips(rgba, width, width, 3)
    for limit in writer.PALETTE_LIMITS:
        assert writer._quantize_art(levels, limit) == old_quantize(levels, limit)


def test_integer_distance_ties_and_overflow():
    colors = [(0, 0, 0, 0), (255, 255, 255, 255), (10, 20, 30, 0), (40, 80, 120, 128)]
    for color, selected in zip(colors, palette.nearest(colors, colors)):
        assert selected == min(range(len(colors)), key=lambda i: (palette.distance(color, colors[i]), i))
    assert palette.distance(colors[0], colors[1]) > 2**32


def test_normal_mud_share_quantization_and_one_group_ladder():
    writer._QUANTIZED_CACHE.clear()
    levels = make_digit_mips(photo(32), 32, 32, 3)
    with patch.object(palette, 'medoids', wraps=palette.medoids) as count:
        writer._quantize_art(levels, 64)
        writer._quantize_art(list(levels), 64)
        assert count.call_count == 1
    with patch.object(writer, '_fit_candidates', wraps=writer._fit_candidates) as count:
        stage_case(CASES[3])
        assert count.call_count == 1


@pytest.mark.parametrize('bits', (10, 11, 12, 13))
def test_greedy_codec_bytes_statistics_and_limits(bits):
    for data in (bytes(8192), bytes(range(256)) * 32, b'abcxyz123' * 1000,
                 random.Random(72).randbytes(8192), b'a', b'ab'):
        assert compress_vc_lz(data, stream_tag=72, offset_bits=bits) == old_compress(data, stream_tag=72, offset_bits=bits)
        for bound in (1, 2, 16, 64, 128):
            outcomes = []
            for codec in (old_compress, compress_vc_lz):
                try:
                    outcomes.append(codec(data, stream_tag=72, offset_bits=bits, max_candidate_comparisons=bound))
                except TxtrError as exc:
                    outcomes.append(str(exc))
            assert outcomes[0] == outcomes[1]


def test_capacity_bound_is_below_real_encoding_after_arbitrary_changes():
    rng = random.Random(721)
    source = rng.randbytes(8192)
    regions = ((100, 4100), (4400, 8192))
    for tail in (bytes(4096), rng.randbytes(4096)):
        changed = bytearray(source)
        changed[:100] = rng.randbytes(100)
        changed[4100:4400] = rng.randbytes(300)
        candidate = bytes(changed) + tail
        bounds = writer._capacity_bounds(source, regions, len(candidate), (10, 11, 12, 13))
        for bits, bound in zip((10, 11, 12, 13), bounds):
            encoded, _ = compress_vc_lz(candidate, stream_tag=1, offset_bits=bits)
            assert bound <= len(encoded)


def test_incremental_groups_and_remember_do_not_reread_unchanged_pngs():
    from b71_t5_project_probe import Corpus
    from mod_editor.core import equipment_staging as staging
    from mod_editor.core import nfl2k5_project_fit as receipts
    from mod_editor.core import json_stream
    from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
    with tempfile.TemporaryDirectory() as folder:
        corpus = Corpus(Path(folder), 24)
        session = corpus.session()
        with corpus.context():
            session.load_shareable_project(corpus.project)
            counts = []
            original = writer.preflight_project_equipment
            def count(index, edits, **kwargs):
                edits = list(edits)
                counts.append(len(edits))
                return original(index, edits, **kwargs)
            with patch.object(writer, 'preflight_project_equipment', side_effect=count):
                rows = staging.equipment_fit_rows(session)
                assert counts == [24]
                with patch.object(json_stream, 'read_bounded_regular_file', side_effect=AssertionError('unchanged PNG reread')):
                    assert staging.equipment_fit_rows(session) == rows
                    receipts.remember(session, rows)
                assert counts == [24]
                target = corpus.rows[0]
                rgba = bytes((100, 20, 50, 255)) * 1024
                png = Path(folder) / 'new.png'
                png.write_bytes(with_import_mode(writer.encode_rgba_png(32, 32, rgba), target.asset_id, rgba, independent=True))
                session.replace_batch(((corpus.assets[target.asset_id], png),))
                staging.equipment_fit_rows(session)
                assert counts == [24, 3]
                # Rewriting the same path, including a restored mtime, must not
                # reuse a stale digest or fit. ctime/identity still invalidates.
                edit = next(iter(session.iter_edits()))
                edit.replacement_path.write_bytes(b'changed outside the editor')
                from mod_editor.core.errors import ValidationError
                with pytest.raises(ValidationError, match='changed outside'):
                    staging.equipment_fit_rows(session)


def test_cache_is_sized_by_project_bytes_and_lru():
    cache = writer.EquipmentCompileCache(project_items=2681)
    assert cache.maximum_bytes == 512 * 1024 * 1024
    for i in range(2681):
        cache.compiled[i] = bytes(128)
        cache.artwork[i] = bytes(128)
    assert len(cache.compiled) == len(cache.artwork) == 2681
    assert cache.statistics(detailed=True)['retained_bytes'] < cache.maximum_bytes
    lru = writer._ByteLRU(1800)
    for key in range(3):
        lru[key] = bytes(300)
    lru.get(0)
    lru[3] = bytes(700)
    assert 0 in lru and 1 not in lru and 3 in lru
    assert lru.retained_bytes <= lru.maximum_bytes


def test_serial_reuses_evicted_preflight_from_build_owned_storage():
    from b70_equipment_fixture import SizedFixture
    with tempfile.TemporaryDirectory() as folder:
        fixture = SizedFixture(Path(folder), width=32, family=8, margin=2048)
        asset_id, png = fixture.png(rgba=photo(32))
        # Deliberately smaller than a single compiled receipt.
        cache = writer.EquipmentCompileCache(maximum_bytes=4096)
        cache.enable_handoff()
        with fixture.context(), patch.object(writer, '_stage_disk_cache', side_effect=OSError('disabled')):
            first = writer.build_unified_uniform_equipment_imports(Path(folder) / '0', [(asset_id, png)],
                compile_cache=cache, preflight_only=True)
            cache.preflight_keys.update(cache.used_keys)
            assert not cache.compiled
            with patch.object(writer, '_compile_group', side_effect=AssertionError('serial pass recompiled')):
                second = writer.build_unified_uniform_equipment_imports(Path(folder) / '0', [(asset_id, png)],
                    compile_cache=cache, preflight_only=True)
            assert second.rebuilt_span == first.rebuilt_span
            assert cache.serial_recompiles == 0
        cache._handoff_directory.cleanup()


def test_refit_preflights_24_item_project_once():
    from tools.bench.b72.b72_refit_bench import run
    result = run(False)
    assert result['outcome'] == 'fit'
    assert result['full_project_preflights'] == 1
    assert result['preflight_rows'] == [24, 3]


def test_retail_capacity_skips_full_size_ladder_and_reports_checked_size():
    from tools.bench.b72.b72_retail_equipment_bench import photo as retail_photo
    index = Path(os.environ.get('NFL2K5_RETAIL_INDEX',
        ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
    if not index.is_file():
        pytest.skip('private retail fixture unavailable')
    from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
    targets, _ = writer.load_targets()
    target = next(t for t in targets.values() if t.name == 'shoes01')
    rgba = retail_photo(target.width, target.height)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'shoe.png'
        path.write_bytes(with_import_mode(writer.encode_rgba_png(target.width, target.height, rgba),
            target.asset_id, rgba, independent=True))
        sizes = []
        quantize = writer._quantize_art
        def measured(levels, maximum, **kwargs):
            sizes.append((levels[0].width, maximum))
            return quantize(levels, maximum, **kwargs)
        writer._STAGED_CACHE.clear()
        writer._PARSE_CACHE.clear()
        with patch.object(writer, '_stage_disk_cache', side_effect=OSError('disabled')), \
             patch.object(writer, '_quantize_art', side_effect=measured):
            with pytest.raises(writer.EquipmentFitError) as caught:
                writer.build_unified_uniform_equipment_imports(index, [(target.asset_id, path)], preflight_only=True)
        assert caught.value.required > caught.value.budget
        assert caught.value.required_is_lower_bound
        assert caught.value.suggestion['width'] == 64
        assert caught.value.suggestion['encoded_bytes'] <= caught.value.budget
        assert sizes == [(64, 2)]


def test_span_filler_preserves_every_trial_decision():
    from b72_fill_oracle import fill_stream as old_fill
    from nfl_vc_lz_fill import fill_stream
    for data in (bytes(2048), b'abc123' * 400, random.Random(72).randbytes(2048)):
        stream, _ = compress_vc_lz(data, stream_tag=1, offset_bits=10)
        for growth in (0, 1, 7, 32, 128, 1024):
            for slack in (0, 4, 16):
                assert fill_stream(stream, data, len(stream) + growth, slack=slack) == old_fill(
                    stream, data, len(stream) + growth, slack=slack)


def test_identical_art_reuses_mips_across_target_specific_png_intents():
    from b70_equipment_fixture import SizedFixture
    from mod_editor.core import nfl2k5_digit_texture as digit
    with tempfile.TemporaryDirectory() as folder:
        fixture = SizedFixture(Path(folder), width=32, family=8, margin=2048)
        _, normal = fixture.png(0, rgba=photo(32))
        _, sibling = fixture.png(1, rgba=photo(32))
        cache = writer.EquipmentCompileCache()
        with patch.object(digit, 'make_digit_mips', wraps=digit.make_digit_mips) as measured:
            first = writer._read_png(normal, fixture.rows[0], cache)
            second = writer._read_png(sibling, fixture.rows[1], cache)
        assert first[0] != second[0]  # each intent still names its own target
        assert first[1:] == second[1:]
        assert measured.call_count == 1

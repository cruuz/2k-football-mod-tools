"""Byte identity, one ladder, proven capacity, and project reuse regressions."""
from pathlib import Path
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
    writer._quantize_pixels.cache_clear()
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

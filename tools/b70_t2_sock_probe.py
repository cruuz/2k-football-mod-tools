"""Measure authored stripe preservation inside a real, read-only sock span."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_uniform_equipment_writer as w
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips
from mod_editor.core.equipment_palette import quantize, quality
from nfl_outer import parse_archive, read_entry_range, read_entry_bytes
from nfl_txtr import encode_rgba_png, parse_chunks, decode_chunk


def art(patterned=False):
    colours = ((240, 239, 221, 255), (211, 57, 13, 255), (50, 18, 11, 255))
    out = bytearray()
    for y in range(64):
        for x in range(64):
            c = colours[(y // 5) % 3] if y < 24 else colours[0]
            if patterned and y >= 24:
                # Reconstructed white designer sock with dark vertical motifs,
                # ribbing and coloured bands, not the reporter's absent source PNG.
                c = colours[2] if x % 13 in (1, 2) and y % 11 < 7 else c
                shade = (x % 4) * 3
                c = tuple(max(0, v-shade) for v in c[:3]) + (255,)
            out.extend(c)
    return bytes(out)


def main():
    index = Path(os.environ.get('NFL2K5_RETAIL_INDEX', ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
    byid, _ = w.load_targets()
    target = next(t for t in byid.values() if t.set_selector == '30H0' and t.name == 'socks00')
    archive = parse_archive(index)
    results = []
    for name, rgba in (('three_colour_bands', art()), ('designer_sock_reconstruction', art(True))):
        levels = make_digit_mips(rgba, 64, 64, 4)
        comparison = []
        for limit in (16, 8, 4, 2):
            old_p, old_i, _ = quantize(levels, limit)
            new_p, new_i, _ = w._quantize_art(levels, limit)
            comparison.append(dict(limit=limit,
                previous=quality(rgba, b''.join(bytes(old_p[i]) for i in old_i[0])),
                current=quality(rgba, b''.join(bytes(new_p[i]) for i in new_i[0]))))
        with tempfile.TemporaryDirectory(prefix='b70-sock-') as directory:
            png = Path(directory) / 'sock.png'
            png.write_bytes(with_import_mode(encode_rgba_png(64,64,rgba), target.asset_id, rgba, independent=True))
            refusal = None
            try:
                compiled = w.build_unified_uniform_equipment_imports(index, [(target.asset_id, png)])
            except w.EquipmentFitError as exc:
                assert exc.suggestion
                refusal = dict(message=str(exc), attempts=exc.attempts, suggestion=exc.suggestion)
                png.write_bytes(with_import_mode(encode_rgba_png(64,64,rgba), target.asset_id, rgba,
                                                independent=True, scale=exc.suggestion['scale']))
                compiled = w.build_unified_uniform_equipment_imports(index, [(target.asset_id, png)])
            span, _, receipt, _, metadata = compiled
            chunk = parse_chunks(span)[0]
            decoded, _ = decode_chunk(span, chunk)
            # Production compile already checks sibling bytes and all authored mips.
            before = read_entry_range(archive, archive.entries[target.outer_index], parse_chunks(read_entry_bytes(archive, archive.entries[target.outer_index]), allow_trailing=True)[target.chunk_index].offset, len(span))
            assert len(before) == len(span) and before[20:24] == span[20:24]
            row = receipt['edits'][0]
            results.append(dict(art=name, authored_rgba_sha256=hashlib.sha256(rgba).hexdigest(),
                stripe_detector=w._striped_art(rgba,64,64), fit=row,
                original_span_bytes=len(before), final_span_bytes=len(span),
                wrapper_14_unchanged=True, decoded_bytes=len(decoded), comparison=comparison,
                refusal_and_explicit_retry=refusal, encoded_bytes=receipt['compression']['recompressed_bytes']))
            print(name, row['fit_summary'], len(span), flush=True)
    (ROOT/'reports/b70_t2/sock-quality.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__ == '__main__':
    main()

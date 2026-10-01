"""Serial incremental event-art proof on retail bundles in RAM; no game output."""
import importlib.util
import json
import re
import resource
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from mod_editor.core import nfl2k5_stadium_shared_art as shared

OUT = ROOT / "ev"
SN = Path('/media/noah/Storage/.b76-research/sn/audit_stadium_names.py')
spec = importlib.util.spec_from_file_location('sn_ocr', SN)
sn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sn)
ocr = sn.Tesseract()
checks, texts, seen, pictures = [], [], {}, []
design = json.loads(shared.EVENT_PATH.read_text())


def save():
    doc = dict(evidence='PROVED OFFLINE', checks=checks, unique_ocr=len(texts),
               peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               ocr_implementation=str(SN), ocr_sha256=mv.sha(SN.read_bytes()))
    (OUT / 'evidence/field_proof.json').write_text(json.dumps(doc, indent=2)+'\n')
    (OUT / 'evidence/ocr.json').write_text(json.dumps(texts, indent=2)+'\n')


with mv._outer_image()(ROOT / 'extracted/ESPN NFL 2K5 (USA)', writable=False) as archive:
    for row in design['textures']:
        prefix, key = row['venue'], row['material']
        pins = mv.venues()[prefix]['bundles']
        day = next(p for p in pins if p['name'] == prefix+'dd.iff')
        entry = mv._entry(archive, day)
        raw_day = archive.read(entry.virtual_offset, entry.size)
        plan = mv.plan_venue(prefix, None, {day['name']: raw_day})
        # Increment over fb2: sponsors already belong to the predecessor. Their
        # writer is unchanged; restrict this delta to the newly added field item.
        plan['items'] = [i for i in plan['items'] if i.get('kind') == 'field-logo']
        assert len(plan['items']) == 1
        for pin in pins:
            name, code = pin['name'], mv.code_of(pin['name'])
            e = mv._entry(archive, pin)
            before = archive.read(e.virtual_offset, e.size)
            assert mv.sha(before) == pin['retail_sha256'], name
            after, edits = mv.modern_bundle(before, name, plan, plan['base'])
            assert len(edits) == 1 and edits[0]['kind'] == 'field'
            chunk = mv.bundle_scenes(before)['field']
            rec, old = mv._mm()._scene(before, chunk)
            newrec, new = mv._mm()._scene(after, chunk)
            assert len(old) == len(new) and rec['system_bytes'] == newrec['system_bytes']
            assert old[:int(rec['system_bytes'])] == new[:int(rec['system_bytes'])]
            index = mv.variant_index(plan['items'][0], code, rec)
            tex = mv.p8_rows(rec)[index]
            lo = int(rec['system_bytes']) + tex['pixel_offset']
            hi = int(rec['system_bytes']) + tex['palette_offset'] + 1024
            assert old[:lo] == new[:lo] and old[hi:] == new[hi:]
            assert old[lo:hi] != new[lo:hi]
            span = mv._mm().scene_span(before, chunk)
            end = chunk.offset + len(span)
            assert before[:chunk.offset+32] == after[:chunk.offset+32]
            assert before[end:] == after[end:]
            # Exercise the production status reader with real bytes and receipt.
            memory_entry = SimpleNamespace(index=pin['outer'], name_id=pin['name_id'], size=len(after), virtual_offset=0)
            entries = [None] * (pin['outer']+1)
            entries[pin['outer']] = memory_entry
            memory = SimpleNamespace(entries=entries, read=lambda offset, size: after[offset:offset+size])
            receipt = dict(bundles={name: dict(applied_sha256=mv.sha(after))})
            assert mv.bundle_state(memory, pin, receipt, {}) == 'venues'
            assert mv.bundle_state(memory, pin, {}, {}) == 'foreign'
            bad = bytearray(after); bad[chunk.offset+40] ^= 1
            memory.read = lambda offset, size: bytes(bad[offset:offset+size])
            assert mv.bundle_state(memory, pin, receipt, {}) == 'foreign'
            rgba = mv.read_texture(new, newrec, tex)
            rgba_hash = mv.sha(rgba.tobytes())
            image = Image.fromarray(rgba)
            if rgba_hash not in seen:
                # The sn API converts RGBA to RGB. Composite first so transparent
                # white antialias pixels cannot become white on white in OCR.
                canvas = Image.new('RGBA', image.size, '#244b32')
                canvas.alpha_composite(image)
                runs = [ocr.read(canvas, scale, psm) for scale in (2, 4) for psm in (11, 6)]
                combined = ' '.join(r['text'].upper() for r in runs)
                forbidden = re.findall(r"\b(?:HAWAII|MIAMI|200[5-9]|05|XL|XLI|XLII|XLIII)\b", combined)
                assert not forbidden, (name, combined)
                assert all(word in combined for word in row['lines'][0].split()), (name, combined)
                assert row['lines'][1] in combined, (name, combined)
                seen[rgba_hash] = len(texts)
                texts.append(dict(first_bundle=name, rgba_sha256=rgba_hash, runs=runs, forbidden_hits=[]))
                image.save(OUT / 'review' / (name+'_event.png'))
            if code == 'dd':
                pictures.append((prefix, Image.fromarray(mv.read_texture(old, rec, tex)), image))
            checks.append(dict(bundle=name, before_sha256=mv.sha(before), after_sha256=mv.sha(after),
                               material=key, format=tex['format_name'], size=[tex['width'], tex['height']],
                               texture=index, allocation=[lo, hi], allocation_sha256=mv.sha(new[lo:hi]),
                               other_decoded_bytes_unchanged=len(old)-(hi-lo), geometry_unchanged=True,
                               other_bundle_bytes_and_wrapper_unchanged=True, compressed_readback=True,
                               status='venues', tamper_status='foreign', ocr_index=seen[rgba_hash], edits=edits))
            save()
            print('PROVED OFFLINE', name, key, 'read-back / byte mask / status / OCR', flush=True)
ocr.close()
sheet = Image.new('RGB', (1080, len(pictures)*300), '#244b32')
pen = ImageDraw.Draw(sheet)
for j, (prefix, a, b) in enumerate(pictures):
    y = j*300
    pen.text((5,y+3), 'PROVED OFFLINE '+prefix+' retail / new P8, native / new P8 2x crop', fill='white')
    for x, im in [(5,a),(280,b)]:
        sheet.paste(im,(x,y+28),im)
    crop = b.crop((0,72,256,184)).resize((512,224), Image.Resampling.NEAREST)
    sheet.paste(crop,(560,y+45),crop)
sheet.save(OUT / 'review/event_fields.png')
save()
print('DONE',len(checks),'bundles',len(texts),'unique OCR textures',flush=True)

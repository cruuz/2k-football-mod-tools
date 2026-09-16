"""Native collection reader proof for a larger same-name score_bug SCNE."""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests/mod_editor'), str(ROOT/'tools')]
from test_nfl2k5_scorebug_assets import NativeOuterLoad, PACK, XBE
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_resources as art

def main():
    with PACK.open('rb') as stream:
        record = art.RESOURCES['score_bug']
        stream.seek(record['pack_offset']); retail = stream.read(record['span_size'])
    chunk, decoded, _ = scene.decode(retail)
    print('retail', chunk, flush=True)
    grown = bytearray(decoded + bytes(8192))
    grown[-16:] = b'SPRITE-SCNE-S5\0\0'
    appended = struct.pack('<4s7I', b'SCNE', len(grown), len(grown), 0, 0, 0, 0, 0) + grown
    blob = retail + appended
    c = NativeOuterLoad(owner.apply(XBE.read_bytes())[0], blob, 0, len(blob))
    m = c.m
    # Register the real SCNE handler in the fixture's resource-handler list.
    handler = m.alloc(16)
    m.put(handler, m.get(0xb0957c)); m.put(handler+8, int.from_bytes(b'SCNE','little'))
    m.put(handler+12, 0x45a90); m.put(0xb0957c, handler)
    m.uc.mem_write(0x2f010, bytes.fromhex('c20400'))  # startup animation/GPU boundary
    result = c.run()
    obj = c.lookup('SCNE','score_bug')
    print('lookup', hex(obj), result, flush=True)
    assert obj and bytes(m.uc.mem_read(obj-256+len(grown)-16,16)) == b'SPRITE-SCNE-S5\0\0'
    result.update(retail_decoded_bytes=len(decoded), appended_decoded_bytes=len(grown),
                  lookup_object=hex(obj), newest_scene_wins=True,
                  native_reader='0x43A20', native_handler='0x45A90', lookup='0x449E0',
                  boundary='OS I/O completions and startup animation; no emulator or GPU')
    (ROOT/'reports/b71_s5/scene-route.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)

if __name__=='__main__': main()

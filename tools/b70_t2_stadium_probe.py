"""Read-only retail banner census and bounded SCNE material relocation.

No game, GPU, disc copy or retail payload output. Requires the user's existing
private resource inventory and Stadium Studio cache. Receipts are metadata.
"""
from pathlib import Path
import hashlib
import json
import os
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_stadium_texture_writer as writer
from mod_editor.core import nfl2k5_weather as weather
from tools.nfl2k5_weather_native_probe import Machine
import test_nfl2k5_equipment_texture_native as native

RETAIL = Path(os.environ.get('NFL2K5_RETAIL_ROOT', ROOT / 'extracted/ESPN NFL 2K5 (USA)'))
CACHE = Path(os.environ.get('NFL2K5_PRIVATE_CACHE', Path.home() / '.cache/2k5-mod-studio' / writer.SOURCE_SHA256))


def native_binding(source, decoded=None):
    """Run SCNE registration through all texture/material relocations, no doubles.

    Stop before mesh registration at 0x2F20A. Decompression is independently
    replayed by the source resolver. This does not execute the package manager.
    """
    native.NativeEquipmentTests.setUpClass()
    t = native.NativeEquipmentTests()
    t.setUp()
    from unicorn.x86_const import UC_X86_REG_FPCW, UC_X86_REG_FPTAG
    base = 0x4000020
    payload = source.decoded if decoded is None else decoded
    t.uc.mem_map(0x4000000, (len(payload) + 0x2000) & ~4095)
    t.uc.mem_write(base - 32, source.span[:32])
    t.uc.mem_write(base, payload)
    t.uc.reg_write(native.UC_X86_REG_ECX, base - 32)
    t.uc.reg_write(native.UC_X86_REG_ESP, 0x3010000)
    t.uc.reg_write(UC_X86_REG_FPCW, 0x37f)
    t.uc.reg_write(UC_X86_REG_FPTAG, 0xffff)
    t.put(0x3010000, t.stop)
    t.uc.emu_start(0x45bc0, 0x2f20a, timeout=1_000_000, count=200_000)
    assert t.uc.reg_read(native.UC_X86_REG_EIP) == 0x2f20a
    c = source.contract
    descriptor = base + c.descriptor_offset
    scene, *_ = writer.parse_scene(c.scene_index, source.resource, payload, {})
    offsets = [m['record_offset'] for m in scene['materials'] if m['texture_index'] == c.texture_index]
    for offset in offsets:
        assert t.words(base + offset + 0x30)[0] == descriptor
    assert t.words(descriptor + 4, 2) == (base + c.system_bytes + c.pixel_offset,
                                         base + c.system_bytes + c.palette_offset)
    return dict(start='0x45BC0', stop='0x2F20A', instruction_cap=200000,
                timeout_microseconds=1000000, external_doubles=[],
                material_offsets=offsets, descriptor_offset=c.descriptor_offset,
                material_to_descriptor_exact=True, pixel_palette_pointers_exact=True)


def main():
    inventory = CACHE / 'indexes/nfl2k5_resource_chunks_v2.json'
    manifest = CACHE / 'derived/stadium-studio-v1/textures/manifest.json'
    resolver = writer._DynamicStadiumResolver(RETAIL / 'vc_53450030/0', inventory)
    doc = json.loads(manifest.read_text())
    names = {zlib.crc32(f's{i:02d}{tod}{wet}.iff'.upper().encode('utf-16le')):
             f's{i:02d}{tod}{wet}.iff' for i in range(100) for tod in 'dan' for wet in 'drs'}
    census = []
    for row in doc['occurrences']:
        if 'banner_corp' not in row['mapped_material_names'].split('|'):
            continue
        entry = resolver.archive.entries[row['outer_index']]
        assert int(row['outer_id'], 16) == entry.name_id
        census.append(dict(bundle=names.get(entry.name_id),
            selector=f"nfl2k5.stadium.o{row['outer_index']:04d}.c{row['chunk_index']:04d}.scene{row['scene_index']:04d}.texture{row['texture_index']:04d}",
            outer_index=row['outer_index'], chunk_index=row['chunk_index'], scene_index=row['scene_index'],
            texture_index=row['texture_index'], material_names=row['mapped_material_names'].split('|'),
            width=row['width'], height=row['height'], rgba_sha256=row['rgba_sha256']))
    resource = weather.load_resource(RETAIL)
    venues = weather.inspect_resource(resource)['rows']
    traced = []
    for index in (5, 6):
        venue = venues[index]
        m = Machine((RETAIL / 'default.xbe').read_bytes(), resource[venue['offset']:venue['offset']+128])
        for tod in range(3):
            for temp, rain in ((70, 0), (70, .5), (20, .5)):
                m.conditions(temperature=temp, precipitation=rain, tod=tod)
                suffix = ''.join(m.suffixes())
                bundle = venue['asset_code'] + suffix + '.iff'
                rows = [r for r in census if r['bundle'] == bundle]
                assert rows
                # The inventory lists every SCNE in this IFF, including non-stadium objects.
                outer = rows[0]['outer_index']
                scenes = [dict(scene_index=i, chunk_index=r.chunk_index)
                          for i, r in enumerate(resolver.scne_resources) if r.outer_index == outer]
                from nfl_scene_probe import named_inner
                for scene_info in scenes:
                    resource_row = resolver.scne_resources[scene_info['scene_index']]
                    data = writer.read_entry_range(resolver.archive, resolver.archive.entries[outer],
                                                   resource_row.chunk_offset, 32+resource_row.stored_size)
                    decoded, _ = writer.decode_resource(data, resource_row)
                    scene_info['name'] = named_inner(decoded, 'SCNE')[0]
                    scene_info['contains_banner_corp_name'] = 'banner_corp'.encode('utf-16le') in decoded
                    scene_info['source_span_sha256'] = hashlib.sha256(data).hexdigest()
                assert {s['chunk_index'] for s in scenes if s['contains_banner_corp_name']} == {r['chunk_index'] for r in rows}
                for row in rows:
                    source = resolver.resolve(row['selector'])
                    native_result = native_binding(source)
                    traced.append(dict(venue=venue['stadium'], bundle=bundle, all_scne_in_package=scenes,
                                       occurrence=row, source_span_sha256=source.contract.source_span_sha256,
                                       native=native_result))
                print(bundle, 'banner occurrences', len(rows), 'SCNEs', len(scenes), flush=True)
    output = dict(schema='b70_t2_banner_evidence/v1', in_game_outcome='UNWITNESSED',
                  census_source='Existing private manifest; archive identities rechecked. Selected 18 packages reparsed from retail.',
                  census=census, traced=traced)
    (ROOT / 'reports/b70_t2/stadium-banners.json').write_text(json.dumps(output, indent=2)+'\n')


if __name__ == '__main__':
    main()

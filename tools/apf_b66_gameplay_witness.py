#!/usr/bin/env python3
"""Read-only beta-66 gameplay/data census. Emits hashes/metadata, never retail bytes.

Supply the extracted retail 0A and, optionally, decrypted PS3 USERDATA (or ZIP),
Xbox Roster.ROS, and decompressed flat base/TU PE images. No emulator is used.
"""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
from mod_editor.core import apf2k8_splb_writer as splb, apf2k8_play_codec as codec
from mod_editor.core import apf_field_material_writer as field
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from mod_editor.core.errors import ValidationError
from mod_editor.apf_studio import ps3_roster_convert as roster
import apf_textlogo_patch as textlogo
import apf_scene
from apf_coverage_function_diff import Image

BASE_SHA = 'cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
TU_SHA = '65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def personnel(index):
    master = codec.Book.from_bytes(read_master_play_body(index))
    census = splb.retail_formation_packages(index)
    counts = Counter()
    exceptions = []
    replay = []
    for outer in splb.STOCK_BOOKS:
        book = splb.read_book(index, outer)
        for row in book.records:
            if not row.populated:
                continue
            counts['retail_records'] += 1
            b = int.from_bytes(row.trailer[4:], 'big')
            counts['multiple_word_b_bits'] += b.bit_count() > 1
            if row.category_index != master.formations[row.formation_index].category_index:
                counts['primary_differs_from_master'] += 1
                exceptions.append({'outer': outer, 'record': row.record_index,
                                   'formation': row.formation_index, 'category': row.category_index,
                                   'master_category': master.formations[row.formation_index].category_index})
            destination = 69 if row.formation_index != 69 else 9
            change = splb.TrailerReplace(outer, row.record_index, destination, row.category_index)
            try:
                result = splb.compile_book(book, [change])
            except ValidationError as exc:
                if 'bounded ladder would have no formation' not in str(exc):
                    raise
                counts['unsafe_ladder_refusals'] += 1
                continue
            splb.verify_book(book.body, result.replacement, [change])
            after = splb.parse_book(result.replacement, outer).records[row.record_index]
            assert after.category_index in splb.FORMATION_PERSONNEL_CATEGORIES[destination]
            assert int.from_bytes(after.trailer[4:], 'big') == 1 << after.category_index
            counts['moves_reparsed'] += 1
            replay.append({'outer': outer, **result.report['records_trailer_replaced'][0]})
    for fi, formation in enumerate(master.formations):
        expected = tuple(c for c, count in census[fi]) if fi in census else (formation.category_index,)
        assert splb.FORMATION_PERSONNEL_CATEGORIES[fi] == expected
    return {'status': 'PROVED bytes; runtime UNWITNESSED', 'book_count': len(splb.STOCK_BOOKS),
            'formation_count': len(census), 'counts': dict(counts),
            'formation_is_single_category_function': all(len(c) == 1 for c in census.values()),
            'multiple_primary_categories': {str(f): cats for f, cats in census.items() if len(cats) > 1},
            'primary_master_exceptions': exceptions, 'moves': replay}


def appearance(ps3, xbox, member):
    source = roster.read_source(ps3, member)
    baseline = xbox.read_bytes() if xbox else None
    output, receipt = roster.convert(source, xbox_appearance=baseline)
    source_graph, output_graph = roster.team_appearance(source), roster.team_appearance(output)
    selectors = lambda graph: [[s['record_hex'] for b in t['banks'] for s in b['selectors']] for t in graph]
    assert selectors(source_graph) == selectors(output_graph)
    structure = roster.inspect_structure(source)
    layout = {str(i): asdict(structure.tables[i]) for i in (4, 15, 16, 17, 19)}
    result = {'status': 'PROVED graph and byte transport; runtime UNWITNESSED',
              'ps3_sha256': sha(source), 'converted_sha256': sha(output), 'layout': layout,
              'appearance': receipt['team_appearance']}
    if baseline is not None:
        xbox_structure = roster.inspect_structure(baseline)
        xbox_layout = {str(i): asdict(xbox_structure.tables[i]) for i in (4, 15, 16, 17, 19)}
        assert layout == xbox_layout
        retained, retention = roster.convert(source, apply_team_appearance=False, xbox_appearance=baseline)
        assert selectors(roster.team_appearance(retained)) == selectors(roster.team_appearance(baseline))
        result.update(xbox_sha256=sha(baseline), layout_matches_xbox=True,
                      retention_reparsed=retention['team_appearance']['selectors_reparsed'])
    return result


def wordmarks(index):
    kinds = Counter()
    for target in textlogo.load_targets():
        _, _, record, _, _, _, metadata, _ = textlogo._read_source(index, target)
        assert record.file_count == 1 and record.files[0].name == 'textlogo_color'
        kinds[(metadata['width'], metadata['height'], record.file_count)] += 1
    return {'status': 'PROVED pinned texture ownership; palette mapping HYPOTHESIS',
            'catalog_sha256': textlogo.CATALOG_SHA256, 'targets_reparsed': sum(kinds.values()),
            'shape_counts': [{'width': k[0], 'height': k[1], 'textures': k[2], 'count': v} for k, v in kinds.items()],
            'format': 'opaque BC1/DXT1 RGB, six mips, single textlogo_color',
            'second_mask_present': False, 'six_independent_regions_proved': False,
            'team_palette_slot_binding_proved': False,
            'bounded_alternative': 'Permute existing R/G/B; paired crest layers support six-region crest art.'}


def material_nodes(index):
    """Bounded SCNE node/draw reparse; emit indices and names only."""
    archive = field.apf_outer.parse_archive(index)
    result = {}
    for outer in field.ENTRY_NAME_IDS:
        entry = archive.entries[outer]
        with field.apf_inner.ArchiveReader(archive) as reader:
            source = reader.read(entry, 0, entry.size)
        _, part, block = field._parse_entry(entry, source)
        body = block[part.offset:part.offset+part.length]
        scene = apf_scene.parse_scene_system_part(body, outer_index=outer, inner_index=1)
        groups = {}
        for node in scene['nodes']:
            start, count = node['draw_record_offset'], node['draw_record_count']
            groups[node['name']] = [struct.unpack_from('>I', body, start+i*0x30+0x20)[0]
                                    for i in range(count)]
        assert groups['A_grass_color'] == [1, 0]
        assert groups['B_ticks'] == [2] and groups['C_chalk_lines'] == [3, 2, 3]
        assert groups['D_graphic_overlays'] == [4, 5, 6, 7, 8, 9]
        assert groups['E_Outside_grass'] == [10, 11]
        result[str(outer)] = groups
    return {'draw_record_stride': 0x30, 'material_index_word': 0x20,
            'node_material_indices': result}


def materials(index):
    result = []
    for outer in field.ENTRY_NAME_IDS:
        _, receipt = field.build_patch(index, outer, {key: 0.25 for key in field.OVERLAYS})
        result.append(receipt)
    return {'status': 'PROVED scene/H7A bytes; rendering UNWITNESSED', 'receipts': result,
            'draw_relationships': material_nodes(index)}


def abilities(base_path, tu_path):
    data = base_path.read_bytes()
    if sha(data) != BASE_SHA:
        raise ValueError('Base flat PE differs from the researched pin')
    base = Image(data)
    tu = None
    if tu_path:
        data = tu_path.read_bytes()
        if sha(data) != TU_SHA:
            raise ValueError('TU flat PE differs from the researched pin')
        tu = Image(data)
    assert base.word(0x820FF0D8) == 0x84744C50
    assert base.word(0x820FF0C8) == 0x84745490
    assert struct.unpack('>f', base.read(0x82003740, 4))[0] == struct.unpack('>f', struct.pack('>f', 0.05))[0]
    functions = {f.start: f for f in base.functions()}
    sites = []
    for address, size, load, meaning in (
        (0x847ECF20, 0x424, 0x847ED318, 'When r27 is nonzero and DT is set, add 0.05 to f1.'),
        (0x84873580, 0xFFC, 0x848742D0, 'When DT is set, state at r27+0x40 is 4, and signed separation exceeds f22, add 0.05 to f31.'),
    ):
        f = functions[address]
        assert f.size == size
        assert base.word(load) & 0xFC00FFFF == 0x80000018  # lwz ...,0x18(...)
        assert base.word(load+4) & 0xFC0007FE == 0x54000420  # rlwinm ...,0,16,16
        row = {'function': hex(address), 'size': size, 'dt_word_load': hex(load),
               'function_sha256': sha(base.read(address, size)), 'static_effect': meaning}
        if tu:
            matches = [g for g in tu.functions() if g.size == size and tu.normalized(g) == base.normalized(f)]
            assert len(matches) == 1
            row.update(tu_function=hex(matches[0].start), tu_dt_word_load=hex(matches[0].start+load-address),
                       tu_match='unique normalized instruction-shape match; referenced data equivalence not proved')
        sites.append(row)
    return {'status': 'PROVED ability getters/scoring consumers; release animation cause HYPOTHESIS',
            'base_sha256': BASE_SHA, 'tu_sha256': TU_SHA if tu else None,
            'dispatch_table': '0x820fefc8 + ability_id * 16',
            'deep_threat': {'id': 17, 'packed_byte': 26, 'bit': 7, 'getter': '0x84744c50'},
            'possession': {'id': 16, 'packed_byte': 41, 'bit': 2, 'getter': '0x84745490'},
            'consumers': sites, 'glitch_causal_site_proved': False, 'patch_exported': False,
            'reason': 'The identified branches change evaluation scores. No bounded animation-only fix is proved; disabling DT would remove intended effects.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--ps3', type=Path)
    parser.add_argument('--member')
    parser.add_argument('--xbox-roster', type=Path)
    parser.add_argument('--base-pe', type=Path)
    parser.add_argument('--tu-pe', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or args.report.is_symlink():
        parser.error('report must be a new file')
    source_hash = file_sha(args.index)
    if source_hash != textlogo.SOURCE_0A_SHA256:
        raise ValueError('Source 0A differs from pinned retail')
    result = {'schema': 'apf_b66_gameplay_witness/v1', 'runtime': 'UNWITNESSED; no emulator used',
              'source_0a_sha256': source_hash}
    for name, operation in [('26_personnel', lambda: personnel(args.index)),
                            ('28_wordmarks', lambda: wordmarks(args.index)),
                            ('29_field_materials', lambda: materials(args.index))]:
        result[name] = operation()
        print(name, 'reparsed', flush=True)
    if args.ps3:
        result['27_ps3_appearance'] = appearance(args.ps3, args.xbox_roster, args.member)
    if args.base_pe:
        result['31_deep_threat'] = abilities(args.base_pe, args.tu_pe)
    assert file_sha(args.index) == source_hash
    result['source_0a_hash_unchanged'] = True
    args.report.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also refuses symlinks or an accidental input alias.
    with args.report.open('xb') as stream:
        stream.write((json.dumps(result, indent=2, sort_keys=True)+'\n').encode())
    print(args.report)


if __name__ == '__main__':
    main()

"""Standalone bounded tests for mode naming. Never read a whole retail pack/disc."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tests', ROOT / 'tools'):
    sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_modern_naming as n
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_safe_text_banks import encode_fixed_utf16le
from nfl2k5_xiso_fixture import SyntheticXiso, dir_node, SECTOR
from nfl_scene_probe import ResourceRecord
from string_table_inventory import parse_nfl_body, rebuild_table

EXTRACTED = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
    '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)'
RETAIL_IMAGE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')


def synthetic_xbe():
    data = n.manifest(); pin = data['xbe_section']
    buf = bytearray(11_948_032)  # retail XBE length; only the string section is seeded
    buf[:4] = b'XBEH'
    struct.pack_into('<II', buf, 0x104, 0x10000, 0x1000)
    struct.pack_into('<II', buf, 0x11c, 22, 0x10200)
    buf[0x900:0x909] = b'.string_\0'
    struct.pack_into('<6I', buf, 0x200 + 14 * 56, pin['flags'], pin['virtual_address'],
                     pin['virtual_size'], pin['raw_offset'], pin['raw_size'], 0x10900)
    for c in n._rows(data, 'xbe'):
        off = c['retail_file_offset']
        buf[off:off+c['allocation_bytes']] = n._encoded(c, False)
    repin(buf)
    return bytes(buf)


def repin(buf):
    sec = _sections(buf)[14]
    off = sec.header_offset + 36
    buf[off:off+20] = section_digest(buf, sec)


def synthetic_strg():
    data = n.manifest(); pin = data['resource']
    buf = bytearray(pin['resource_size'])
    prefix = bytes.fromhex(pin['structure_hex'])
    buf[:len(prefix)] = prefix
    for c in pin['pool_allocations']:
        off, size = c['resource_offset'], c['allocation_bytes']
        if size > 2:
            buf[off:off+size] = encode_fixed_utf16le('X' * (size//2-1), size, 'fixture')
    for c in n._rows(data, 'strg'):
        off, size = c['resource_offset'], c['allocation_bytes']
        buf[off:off+size] = n._encoded(c, False)
    return bytes(buf)


def table(payload):
    r = n.manifest()['resource']
    rec = ResourceRecord(r['outer_index'], r['outer_id'], r['outer_size'], r['chunk_index'],
                         r['chunk_offset'], 'STRG', len(payload)-32, *struct.unpack_from('<4I',payload,8))
    return parse_nfl_body(payload[32:], rec)


def fixture_image(root, xbe, strg):
    r = n.manifest()['resource']
    outer = bytearray(r['outer_size'])
    outer[r['chunk_offset']:r['chunk_offset']+len(strg)] = strg
    entries = [(i, b'') for i in range(r['outer_index'])]
    entries += [(int(r['outer_id'], 0), bytes(outer)), (999, b'TAIL')]
    fixture = SyntheticXiso(root, entries, pack_sizes=(0x600000,), pack_sectors=(8192,))
    rootdir = dir_node([(40, len(xbe), 0x80, 'default.xbe'),
                        (34, 20, 0x10, 'vc_53450030')])
    with fixture.path.open('r+b') as f:
        f.seek(33 * SECTOR); f.write(rootdir)
        f.seek(0x10000 + 24); f.write(struct.pack('<I',len(rootdir)))
        f.seek(40 * SECTOR); f.write(xbe)
    return fixture


class NamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe = synthetic_xbe()
        cls.strg = synthetic_strg()

    def test_mapping_semantics_and_preset_fit_gate(self):
        data = n.manifest()
        self.assertEqual(len(data['cells']), 24)
        self.assertEqual(sum(c['domain']=='xbe' for c in data['cells']), 23)
        for c in data['cells']:
            self.assertEqual(n._choice(c), c['desired'])
            self.assertNotIn('Franchise', c['desired'])
            self.assertNotIn('MyTeam', c['desired'])
        self.assertFalse(n.preset_enabled('basic'))
        self.assertFalse(n.preset_enabled('advanced'))
        self.assertTrue(n.preset_enabled('experimental'))
        self.assertEqual(n.career_text('menu_row',18), 'MyCareer'.encode('utf-16le') + bytes(2))
        self.assertEqual(n.career_text('screen_title'), 'MyCareer'.encode('utf-16le') + bytes(4))
        with self.assertRaises(n.ModernNamingError): n.career_text('menu_row',16)
        with self.assertRaises(n.ModernNamingError): n.career_text('invalid')

    def test_exact_writes_read_every_string_idempotent_and_disable(self):
        data = n.manifest()
        for source in (self.xbe, self.strg):
            with self.subTest(domain=n._domain(source)):
                self.assertEqual(n.status(source), 'retail')
                out, receipt = n.apply(source)
                self.assertEqual(n.status(out), 'applied')
                self.assertEqual(receipt['changed_spans'], 23 if source is self.xbe else 1)
                allowed = {i for c in n._rows(data,n._domain(source))
                           for i in range(n._offset(source,c),n._offset(source,c)+c['allocation_bytes'])}
                if source is self.xbe:
                    off = _sections(source)[14].header_offset+36
                    allowed.update(range(off,off+20))
                self.assertEqual(len(out),len(source))
                self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(source,out)) if a != b))
                for cell in n._rows(data,n._domain(source)):
                    off=n._offset(out,cell)
                    raw=out[off:off+cell['allocation_bytes']]
                    self.assertEqual(raw.decode('utf-16le').split('\0')[0],cell['desired'])
                    self.assertEqual(raw,n._encoded(cell,True))
                again, replay=n.apply(out)
                self.assertEqual(again,out);self.assertEqual(replay['writes'],[])
                self.assertEqual(replay['changed_bytes'],0)
                restored, undo=n.apply(out,enabled=False,original=source)
                self.assertEqual(restored,source)
                self.assertEqual(undo['status'],'retail')
                self.assertEqual(n.apply(restored,enabled=False,original=source)[1]['writes'],[])
                with self.assertRaises(n.ModernNamingError):n.apply(out,enabled=False)
                with self.assertRaises(n.ModernNamingError):n.apply(out,enabled=False,original=out)
        before_table=table(self.strg);after_table=table(n.apply(self.strg)[0])
        self.assertEqual(rebuild_table(after_table),n.apply(self.strg)[0][32:])
        for before,after in zip(before_table.pool,after_table.pool):
            self.assertEqual((before.offset,before.end_offset),(after.offset,after.end_offset))
            wanted=n._rows(data,'strg')[0]['desired'] if before.index==3 else before.text
            self.assertEqual(after.text,wanted)
        self.assertEqual([(r.id_a,r.id_b,r.text_offset) for r in before_table.records],
                         [(r.id_a,r.id_b,r.text_offset) for r in after_table.records])

    def test_each_partial_or_foreign_xbe_cell_refuses_without_mutation(self):
        after,_=n.apply(self.xbe)
        for cell in n._rows(n.manifest(),'xbe'):
            off,size=cell['retail_file_offset'],cell['allocation_bytes']
            mixed=bytearray(self.xbe);mixed[off:off+size]=after[off:off+size];repin(mixed)
            snapshot=bytes(mixed)
            self.assertEqual(n.status(mixed),'foreign')
            with self.assertRaises(n.ModernNamingError):n.apply(mixed)
            self.assertEqual(mixed,snapshot)
            mixed=bytearray(self.xbe);mixed[off]^=1;repin(mixed)
            self.assertEqual(n.status(mixed),'foreign')
        for bad in (b'',b'XBEH',self.xbe[:-10],self.strg[:-1],b'NOPE'+self.strg[4:]):
            self.assertEqual(n.status(bad),'foreign')

    def test_foreign_structure_pointer_digest_and_tokens_refuse(self):
        for offset in (0,8,32+0x10,32+0x34,32+0x34+8):
            bad=bytearray(self.strg);bad[offset]^=1
            self.assertEqual(n.status(bad),'foreign')
        bad=bytearray(self.xbe);bad[0x200+14*56+36]^=1
        self.assertEqual(n.status(bad),'foreign')
        bad=bytearray(self.xbe);bad[0x200+14*56]^=1;repin(bad)
        self.assertEqual(n.status(bad),'foreign')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'names.json'
            for modify in ('locator','token','nul','bool','surrogate'):
                data=n.manifest();cell=data['cells'][5]
                if modify=='locator':cell['va']+=2
                if modify=='token':
                    cell=next(c for c in data['cells'] if '|LINK|' in c['retail']);cell['desired']=cell['desired'].replace('|LINK|','')
                if modify=='nul':cell['desired']='A\0B'
                if modify=='bool':cell['fallbacks']=[True]
                if modify=='surrogate':cell['desired']='\ud800'
                path.write_text(json.dumps(data))
                self.assertFalse(n.all_strings_fit(path))
                self.assertEqual(n.status(self.xbe,manifest_path=path),'foreign')

    def test_custom_fallback_utf16_counts_manifest_receipt_and_stale_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'names.json';data=n.manifest()
            cell=next(c for c in data['cells'] if c['retail']=='Quick Game')
            cell['desired']='An impossibly long Play Now label';cell['fallbacks']=['\U0001f3c8'*6,'Play']
            path.write_text(json.dumps(data))
            out,receipt=n.apply(self.xbe,manifest_path=path)
            changed=next(c for c in receipt['writes'] if c['asset_id']==cell['asset_id'])
            self.assertEqual(changed['after'],'Play');self.assertTrue(changed['fallback'])
            self.assertEqual(n.status(out),'foreign')
            self.assertEqual(n.apply(out,enabled=False,original=self.xbe,manifest_path=path)[0],self.xbe)
            cell['fallbacks']=[];path.write_text(json.dumps(data))
            self.assertFalse(n.preset_enabled('experimental',path))
            with self.assertRaises(n.ModernNamingError):n.apply(self.xbe,manifest_path=path)

    def test_manual_catalog_conflict_and_disabling_preview(self):
        cell=n._rows(n.manifest(),'strg')[0]
        asset=SimpleNamespace(asset_id=cell['asset_id'],editable=True,allocation_bytes=cell['allocation_bytes'],
                              value=cell['retail'],label='Milestones')
        catalog=SimpleNamespace(assets=[asset])
        self.assertEqual(n.catalog_overrides(catalog),{})
        self.assertEqual(n.catalog_overrides(catalog,enabled=True),{cell['asset_id']:cell['desired']})
        with self.assertRaisesRegex(n.ModernNamingError,'manual edit'):
            n.catalog_overrides(catalog,enabled=True,value_lookup=lambda a:'Custom')
        self.assertTrue(all(c['before']==c['after'] for c in n.preview_rows(enabled=False)))

    def test_restore_preserves_unrelated_text_edits(self):
        changed=bytearray(n.apply(self.xbe)[0]);changed[0xaef020:0xaef024]=b'T\0X\0';repin(changed)
        restored,_=n.apply(changed,enabled=False,original=self.xbe)
        expected=bytearray(self.xbe);expected[0xaef020:0xaef024]=b'T\0X\0';repin(expected)
        self.assertEqual(restored,expected)

    def test_real_image_adapter_relocated_pack_full_restore_and_closed_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();f=fixture_image(root,self.xbe,self.strg)
            source=root/'source.iso';source.write_bytes(f.path.read_bytes()) # synthetic <23 MiB only
            with patch.object(Path,'read_bytes',side_effect=AssertionError('whole pack read')):
                with n._outer_image()(f.retail_packs) as loose:
                    pin=n.manifest()['resource']
                    offset=loose.entries[pin['outer_index']].virtual_offset+pin['chunk_offset']
                    self.assertEqual(loose.read(offset,pin['resource_size']),self.strg)
            self.assertEqual(n.image_status(f.path),'retail')
            preview=n.image_preview(f.path)
            self.assertEqual(len(preview),24);self.assertTrue(all(r['source_verified'] for r in preview))
            receipt=n.apply_to_image(f.path)
            self.assertEqual(receipt['changed_spans'],24)
            self.assertEqual(n.image_status(f.path),'applied')
            with patch.object(n.io,'pwrite',side_effect=AssertionError('idempotent write')):
                self.assertEqual(n.apply_to_image(f.path)['changed_spans'],0)
            n.apply_to_image(f.path,enabled=False,original_source=source)
            self.assertEqual(f.path.read_bytes(),source.read_bytes())
            os.replace(f.path,root/'closed.iso')

    def test_image_preflight_and_io_failure_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();f=fixture_image(root,self.xbe,self.strg)
            original=f.path.read_bytes() # synthetic only
            real=n.io.pwrite;calls=[]
            def fail_once(fd,raw,off):
                calls.append(off)
                if len(calls)==1:
                    real(fd,raw[:4],off)
                    return 4
                return real(fd,raw,off)
            with patch.object(n.io,'pwrite',side_effect=fail_once):
                with self.assertRaisesRegex(n.ModernNamingError,'Short'):
                    n.apply_to_image(f.path)
            self.assertEqual(f.path.read_bytes(),original)
            # A prior XBE dispatcher pass is permitted only through the explicit data adapter.
            with f.path.open('r+b') as out:
                out.seek(40*SECTOR);out.write(n.apply(self.xbe)[0])
            self.assertEqual(n.image_status(f.path),'foreign')
            with self.assertRaisesRegex(n.ModernNamingError,'Mixed'):n.apply_to_image(f.path)
            n.apply_to_image(f.path,include_xbe=False)
            self.assertEqual(n.image_status(f.path),'applied')
            os.replace(f.path,root/'closed.iso')

    def test_directories_are_refused_before_loose_pack_constructor(self):
        with patch.object(n,'_outer_image',side_effect=AssertionError('must not load loose pack')):
            self.assertEqual(n.image_status(ROOT),'foreign')

    def test_capability_candidate_schema_and_its_own_command_file_closure(self):
        from mod_editor.capabilities.validate_registry import (
            DEFAULT_REGISTRY, validate_data, _local_path, _command_module)
        row=json.loads((ROOT/'docs/mod_editor/nfl2k5_modern_naming_capability.json').read_text())
        registry=json.loads(DEFAULT_REGISTRY.read_text())
        installed=[item for item in registry['capabilities'] if item['id']==row['id']]
        if installed:
            self.assertEqual(installed,[row])
        registry['capabilities']=[item for item in registry['capabilities'] if item['id']!=row['id']]
        registry['capabilities'].append(row)
        registry['capabilities'].sort(key=lambda item:item['id'])
        # Older registry rows refer to absent private research. Validate all
        # metadata and then enforce real file closure for every new reference.
        validate_data(registry,check_files=False)
        for path in row['evidence']:
            _local_path(path,'modern naming evidence')
        for command in (row['backend']['command'],row['validation_command']):
            self.assertEqual(_command_module(command,'modern naming command'),row['backend']['module'])
            _local_path(row['backend']['module'],'modern naming backend')

    def test_codec_preserves_aliases_and_rejects_nonzero_padding_and_overlap(self):
        from string_table_inventory import parse_pool, StringTableError
        raw=encode_fixed_utf16le('A',10,'first')+encode_fixed_utf16le('B',4,'second')
        refs={0:('A',4),10:('B',14)}
        pool,end,tail=parse_pool(raw,0,refs,'utf-16le','test',fixed_allocations=True)
        self.assertEqual([(p.offset,p.end_offset,p.text) for p in pool],[(0,10,'A'),(10,14,'B')])
        self.assertEqual((end,tail),(14,b''))
        with self.assertRaises(StringTableError):
            parse_pool(raw[:4]+b'Z'+raw[5:],0,refs,'utf-16le','test',fixed_allocations=True)
        with self.assertRaises(StringTableError):
            parse_pool(raw,0,{0:('A',12),10:('B',14)},'utf-16le','test',fixed_allocations=True)
        # APF retains the strict compact-pool default, not NFL padding policy.
        with self.assertRaises(StringTableError):parse_pool(raw,0,refs,'utf-16le','test')


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (EXTRACTED/'default.xbe').is_file() or not (EXTRACTED/'vc_53450030/0').is_file():
            raise unittest.SkipTest('Private USA retail default.xbe and extracted archive are absent')
        from nfl_outer import parse_archive,read_entry_range
        cls.xbe=(EXTRACTED/'default.xbe').read_bytes()
        data=n.manifest();pin=data['resource'];archive=parse_archive(EXTRACTED/'vc_53450030/0')
        cls.strg=read_entry_range(archive,archive.entries[pin['outer_index']],pin['chunk_offset'],pin['resource_size'])

    def test_retail_allocation_readback_and_full_reversal(self):
        for before in (self.xbe,self.strg):
            after,receipt=n.apply(before)
            self.assertEqual(n.apply(after)[1]['changed_spans'],0)
            self.assertEqual(n.apply(after,enabled=False,original=before)[0],before)
            self.assertEqual(n.status(after),'applied')
        before=table(self.strg);after=table(n.apply(self.strg)[0])
        for a,b in zip(before.pool,after.pool):
            self.assertEqual(b.text,n._rows(n.manifest(),'strg')[0]['desired'] if a.index==3 else a.text)
        self.assertEqual(rebuild_table(after),n.apply(self.strg)[0][32:])

    def test_real_image_read_only_matches_extraction(self):
        if not RETAIL_IMAGE.is_file():self.skipTest('Private USA retail XISO is absent')
        self.assertEqual(n.image_status(RETAIL_IMAGE),'retail')
        rows=n.image_preview(RETAIL_IMAGE)
        self.assertEqual(len(rows),24)
        self.assertTrue(all(r['source_verified'] for r in rows))


if __name__=='__main__':
    unittest.main()

"""One archive transaction: 48 clones plus independent asset allocations.

The synthetic crest and field payloads test transport/identity composition;
they do not substitute for the existing crest/field rendering-writer proofs.
"""
from pathlib import Path
import struct
import json
import tempfile
import unittest
import zlib

from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.core import apf2k8_book_identity as identity
from tests.mod_editor.test_apf_book_unlock import archive_fixture, iff
import apf_inner
import apf_outer


class CloneBatchTests(unittest.TestCase):
    def test_owned_48_book_plan_fits_real_directory_without_copying_game(self):
        from tests.mod_editor.test_apf_playcall_research_native import INDEX
        if not INDEX.is_file():
            self.skipTest('Owned retail index absent; set APF_RETAIL_INDEX for the real directory capacity check')
        rost = identity.read_disc_roster(INDEX)
        plans = clone.own_book_plan(INDEX, rost, 'offense') + clone.own_book_plan(INDEX, rost, 'defense')
        self.assertEqual(len(plans), 48)
        compiled = clone.compile_unlock(INDEX, (p.request() for p in plans))
        self.assertEqual(len(compiled.clones), 48)
        self.assertEqual(len({c.name_id for c in compiled.clones}), 48)
        assigned = identity.parse_roster_identity(compiled.roster_body)
        for plan in plans:
            self.assertEqual(assigned.labels[plan.label_id].kind, plan.clone_name)
        print('PROVED read-only retail compile: 48 clones fit the existing directory and ROST label strings', flush=True)

    def test_owned_donor_overlay_survives_preset_and_clone(self):
        from tests.mod_editor.test_apf_playcall_research_native import INDEX
        from mod_editor.core import apf2k8_splb_writer as splb
        if not INDEX.is_file():
            self.skipTest('Owned retail index absent; set APF_RETAIL_INDEX for donor/preset composition')
        source = identity.read_resource(INDEX, identity.filename_id('O-ZoneBlock'), 'spb', 'SPLB')
        book = splb.parse_book(source[3], source[1].table_index)
        form = book.records[0].formation_index
        edited = splb.set_formation_ratings(book.body, form, (7, 6, 5))
        packed, _ = clone.rebuild_resource(source, edited)
        plan = clone.compile_unlock(INDEX, [clone.CloneRequest(5, 5, 'O-ZoneBlock')],
                                    preset_ids=('wide-zone',), asset_replacements={source[1].name_id: packed})
        self.assertEqual(splb.formation_ratings(plan.clones[0].body, form), (7, 6, 5))

    def test_48_clones_assets_and_reopen_by_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = archive_fixture(root / 'source')
            archive = apf_outer.parse_archive(index)
            with apf_inner.ArchiveReader(archive) as reader:
                resources = [(e.name_id, reader.read(e, 0, e.size)) for e in archive.entries]
            crest_id, field_id = (zlib.crc32(n) for n in (b'CREST-PROOF.IFF', b'FIELD-PROOF.IFF'))
            resources += [(crest_id, iff(bytes(range(6)) * 256, 'crest', 'TXTR')),
                          (field_id, iff(b'field geometry and art' * 128, 'field', 'SCNE'))]
            resources.sort()
            whole = bytearray(2048)
            rows = []
            for name_id, payload in resources:
                rows.append((name_id, len(whole) // 2048, len(payload) // 2048))
                whole.extend(payload)
            split = len(whole) // 4096 * 2048
            struct.pack_into('>6I', whole, 0, apf_outer.MAGIC, 2048, 2, 0, len(rows), 0)
            for i, (name, size) in enumerate((('0A', split), ('1B', len(whole) - split))):
                struct.pack_into('>II8s', whole, 0x18 + i * 16, size // 2048, 0, name.encode('utf-16-be').ljust(8, b'\0'))
            for i, row in enumerate(rows):
                struct.pack_into('>III', whole, 0x38 + i * 12, *row)
            index.write_bytes(whole[:split])
            (index.parent / '1B').write_bytes(whole[split:])
            rost = identity.read_disc_roster(index)
            plans = clone.own_book_plan(index, rost, 'offense') + clone.own_book_plan(index, rost, 'defense')
            self.assertEqual(len(plans), 48)
            self.assertEqual(len({a.clone_name for a in plans}), 48)
            overlays = {crest_id: iff(bytes(reversed(range(6))) * 256, 'crest', 'TXTR'),
                        field_id: iff(b'painted field surface' * 128, 'field', 'SCNE')}
            source_archive = apf_outer.parse_archive(index)
            bindings = clone.asset_name_bindings(index, range(len(source_archive.entries)))
            project = root / 'asset-manifest.json'
            project.write_text(json.dumps({'asset_name_bindings': bindings}), newline='\n')
            compiled = clone.compile_unlock(index, (p.request() for p in plans), asset_replacements=overlays)
            self.assertEqual(len(compiled.clones), 48)
            receipt = clone.build_new_folder(compiled, root / 'built')
            self.assertEqual(receipt['verification']['clone_count_added'], 48)
            reopened = root / 'built' / '0A'
            saved = json.loads(project.read_text())
            restored = {int(k): v for k, v in saved['asset_name_bindings'].items()}
            self.assertEqual(restored, bindings)
            remapped = clone.resolve_asset_bindings(reopened, restored)
            after = apf_outer.parse_archive(reopened)
            self.assertTrue(any(old != new for old, new in remapped.items()))
            for old, new in remapped.items():
                self.assertEqual(after.entries[new].name_id, bindings[old])
            bound = identity.parse_roster_identity(identity.read_disc_roster(reopened))
            for assignment in plans:
                label = bound.labels[assignment.label_id]
                self.assertEqual(label.kind, assignment.clone_name)
                self.assertEqual(getattr(bound.teams[assignment.team_index], label.side), label.index)
                self.assertEqual(identity.read_resource(reopened, identity.filename_id(label.kind), 'spb', 'SPLB')[3][0x30:0x68].decode('utf-16-be').rstrip('\0'), label.kind)
            print('PROVED synthetic archive: 48 clones; crest/field allocations preserved; every original asset reopened by name hash; unrelated bytes compared', flush=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)

"""Standalone storage, instruction, ownership and signed-save proofs. No emulator."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_storage as storage
from mod_editor.core import nfl2k5_roster_records as records
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_franchise_save as franchise
from mod_editor.core import nfl2k5_practice_squad as reserves
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256, ReservationManifest, DEFAULT_MANIFEST
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HUB = Path(os.environ.get("NFL2K5_SAVE_FIXTURES", "/home/noah/Desktop/2K5-8 Editors/save_fixtures"))
HAVE_CS = importlib.util.find_spec("capstone") is not None


def repin(payload):
    buf = bytearray(payload)
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


def with_stadiums(payload, preamble=0):
    """Use vacant fixture storage; production has no arbitrary append writer."""
    buf = bytearray(payload)
    root = preamble + (0x20 if struct.unpack_from('<I', buf, preamble + 16)[0] == 0 else 0x40)
    table = root + 0x70
    struct.pack_into('<Ii', buf, root + 0x10, 82, table - root - 0x14 + 1)
    # Deliberately reverse IDs: the reader must not confuse index with ID.
    for i, asset_id in enumerate(reversed(storage.STADIUM_IDS)):
        buf[table + i * 128 + 124:table + i * 128 + 128] = bytes((asset_id, 0xAA, 0xBB, 0xCC))
    return bytes(buf), root, table


class CodecTests(unittest.TestCase):
    def test_all_82_stadiums_round_trip_in_both_versions(self):
        for version in (17, 0):
            base = 0 if version == 17 else 0x300
            original = synthetic_body() if version == 17 else synthetic_save_v0(synthetic_body())
            original, root, table = with_stadiums(original, base)
            team = root + 0x1C + struct.unpack_from('<i', original, root + 0x1C)[0] - 1
            for index in range(82):
                buf = bytearray(original)
                field = team + storage.TEAM_STADIUM
                struct.pack_into('<i', buf, field, table + index * 128 - field + 1)
                source = bytes(buf)
                with self.subTest(version=version, index=index):
                    doc = records.RosterDocument(source, base=base)
                    saved = codec.decode(source)
                    self.assertEqual(doc.teams[0].stadium_index, index)
                    self.assertEqual(saved.teams[0].stadium_index, index)
                    self.assertEqual(doc.stadiums[index].asset_id, storage.STADIUM_IDS[81 - index])
                    self.assertEqual(doc.to_body(), source)
                    self.assertEqual(saved.to_bytes(), source)
                    saved.edit_player('primary', 0, {'speed': 91})
                    out = saved.to_bytes()
                    self.assertEqual(out[field:field + 4], source[field:field + 4])
                    self.assertEqual(out[table:table + 82 * 128], source[table:table + 82 * 128])

    def test_franchise_reads_current_buffer_and_preserves_suffix(self):
        source, root, table = with_stadiums(synthetic_franchise(), 0x300)
        save = franchise.FranchiseSave(source)
        _ = save.roster  # prime cached document before simulating native selection
        field = save.team_offset(0) + storage.TEAM_STADIUM
        for index in range(82):
            struct.pack_into('<i', save.buffer, field, table + index * 128 - field + 1)
            self.assertEqual(save.team_stadium(0).index, index)
        output = save.to_bytes()
        self.assertEqual(output[franchise.ARENA_END:], source[franchise.ARENA_END:])
        self.assertEqual(len(output), franchise.FRANCHISE_SAVE_SIZE)
        self.assertEqual(franchise.FranchiseSave(output).roster.teams[0].stadium_index, 81)

    def test_corrupt_stadium_references_and_arena_escape_refuse(self):
        source, root, table = with_stadiums(synthetic_franchise(), 0x300)
        team = records.RosterDocument(source, base=0x300).teams[0].offset
        field = team + storage.TEAM_STADIUM
        for target in (table + 1, table + 82 * 128, root, franchise.ARENA_END):
            bad = bytearray(source)
            struct.pack_into('<i', bad, field, target - field + 1)
            with self.subTest(target=target):
                with self.assertRaises(codec.SaveRostError):
                    codec.decode(bad)
                with self.assertRaises(records.RosterRecordError):
                    records.RosterDocument(bad, base=0x300)
                with self.assertRaises(franchise.FranchiseSaveError):
                    franchise.FranchiseSave(bad).team_stadium(0)
        # A table may fit the whole franchise file and still escape its arena.
        bad = bytearray(source)
        struct.pack_into('<i', bad, root + 0x14, franchise.ARENA_END - root - 0x14 + 1)
        with self.assertRaises(records.RosterRecordError):
            records.RosterDocument(bad, base=0x300)
        with self.assertRaises(codec.SaveRostError):
            codec.decode(bad)

    def test_reserve_capacity_is_not_raised_by_stadium_support(self):
        raw = bytearray(500)
        raw[reserves.ACTIVE_COUNT] = 53
        for i in range(53):
            struct.pack_into('<i', raw, i * 4, 0x1000 + i * 84 - i * 4 + 1)
        original = bytes(raw)
        result = reserves.set_reserve_list(raw, range(53, 65), player_pool_offset=0x1000, player_count=70)
        self.assertEqual(len(reserves.reserve_list(result)), 12)
        for count in (13, 16, 17):
            with self.assertRaises(reserves.PracticeSquadError):
                reserves.set_reserve_list(raw, range(53, 53 + count), player_pool_offset=0x1000, player_count=70)
        self.assertEqual(bytes(raw), original)

    def test_foreign_executable_inputs(self):
        for payload in (b'', b'XBEH', b'bad', None):
            self.assertEqual(storage.status(payload), 'foreign')
            with self.assertRaises(ValueError):
                storage.apply(payload)


@unittest.skipUnless(XBE.is_file(), f'pinned USA default.xbe absent: {XBE}')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError('USA retail evidence hash differs')
        cls.base, _ = space.apply(cls.retail, storage.REQUESTS)
        cls.patched, cls.receipt = storage.apply(cls.base)

    def test_exact_edits_replay_receipt_and_digests(self):
        self.assertEqual(storage.status(self.retail), 'retail')
        self.assertEqual(storage.status(self.base), 'retail')
        self.assertEqual(storage.status(self.patched), 'applied')
        self.assertEqual(storage.apply(self.retail)[0], self.patched)
        replay, receipt = storage.apply(self.patched)
        self.assertEqual(replay, self.patched)
        self.assertEqual((receipt['changed_bytes'], receipt['edits']), (0, []))
        self.assertEqual(self.receipt['changed_bytes'], sum(a != b for a, b in zip(self.base, self.patched)))
        self.assertEqual(self.receipt['after_sha256'], hashlib.sha256(self.patched).hexdigest())
        self.assertEqual(self.receipt['reserve_limit'], 12)
        self.assertFalse(self.receipt['save_layout_changed'])
        self.assertFalse(self.receipt['runtime_witnessed'])
        a = storage.site(self.patched)
        image = XbeImage(self.patched)
        allowed = set(range(a['raw'], a['raw'] + a['size']))
        allowed.update(range(space.DIRECTORY, space.PAGE))
        for va, old, new in storage.sites(a['va']):
            self.assertEqual(image.read(va, len(old)), new)
            allowed.update(range(image.offset(va), image.offset(va) + len(old)))
        for section in _sections(self.patched):
            self.assertEqual(section_digest(self.patched, section), section.stored_digest)
            allowed.update(range(section.header_offset + 36, section.header_offset + 56))
        self.assertTrue(all(i in allowed for i, (x, y) in enumerate(zip(self.base, self.patched)) if x != y))
        self.assertEqual(image.read(storage.RETAIL_LIST_VA, 67), storage.RETAIL_IDS)

    def assert_refused(self, payload):
        before = bytes(payload)
        self.assertEqual(storage.status(payload), 'foreign')
        with self.assertRaises(ValueError):
            storage.apply(payload)
        self.assertEqual(bytes(payload), before)

    def test_partial_installs_corrupt_guards_and_sealed_foreign_list_refuse(self):
        image = XbeImage(self.patched)
        for va, old, _new in storage.sites(storage.site(self.patched)['va']):
            bad = bytearray(self.patched)
            bad[image.offset(va):image.offset(va) + len(old)] = old
            with self.subTest(va=hex(va)):
                self.assert_refused(repin(bad))
            bad = bytearray(self.patched)
            bad[image.offset(va)] ^= 1
            self.assert_refused(repin(bad))
        for va, size, _hash in storage.GUARDS:
            for offset in (0, size - 1):
                bad = bytearray(self.patched)
                bad[image.offset(va) + offset] ^= 1
                self.assert_refused(repin(bad))
        sealed, _ = space.install_code(self.base, storage.OWNER, bytes(82))
        self.assert_refused(sealed)
        sealed, _ = space.install_code(self.base, storage.OWNER, storage.STADIUM_IDS)
        self.assert_refused(sealed)  # list installed without its instructions
        foreign_union, _ = space.apply(self.retail)
        with self.assertRaisesRegex(ValueError, 'missing stadium allocation'):
            storage.apply(foreign_union)

    @unittest.skipUnless(HAVE_CS, 'capstone missing: independent instruction and operand audit')
    def test_every_list_reference_and_all_navigation_bounds(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        from capstone.x86 import X86_OP_IMM
        image = XbeImage(self.retail)
        refs = []
        for section in image.sections:
            raw = image.read(section.start, section.raw_size)
            start = 0
            while (at := raw.find(struct.pack('<I', storage.RETAIL_LIST_VA), start)) >= 0:
                refs.append(section.start + at)
                start = at + 1
        self.assertEqual(refs, [0x3191C4, 0x3192CB, 0x319343])
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        patched = XbeImage(self.patched)
        expected = {0x31926D:82, 0x319289:81, 0x31928D:82, 0x3192D7:82,
                    0x31934C:82, 0x31A9CE:81, 0x31A9FD:82}
        for va, scalar in expected.items():
            instruction = next(md.disasm(patched.read(va, 12), va))
            self.assertEqual(instruction.operands[-1].type, X86_OP_IMM)
            self.assertEqual(instruction.operands[-1].imm, scalar)
        self.assertEqual(len(set(storage.STADIUM_IDS)), 82)
        self.assertEqual(storage.STADIUM_IDS[:67], image.read(storage.RETAIL_LIST_VA, 67))
        # Native team +114 relocation and serialization remain byte-identical.
        # The code resolves field-relative refs on load and emits target-field+1
        # on save, independently of the selected stadium's ID/list position.
        for va, size in ((0x241977, 23), (0x241AD3, 21)):
            self.assertEqual(patched.read(va, size), image.read(va, size))

    def test_manifest_records_full_sites_and_owned_list(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        recorder.observe(space, 'apply', self.retail, self.base, {})
        recorder.observe(storage, 'apply', self.base, self.patched, self.receipt)
        spans = recorder.finish(self.patched)
        a = storage.site(self.patched)
        for va, old, _new in storage.sites(a['va']):
            self.assertTrue(any(s['owner'] == storage.OWNER and int(s['start'], 0) <= va
                                and va + len(old) <= int(s['end'], 0) for s in spans))
        self.assertTrue(any(s['owner'] == storage.OWNER and int(s['start'], 0) == a['va']
                            and s['size'] == 82 for s in spans))
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        for va, old, _new in storage.sites(a['va']):
            self.assertEqual(manifest.overlaps(va, va + len(old), exclude_owner=storage.OWNER), [])

    def test_complete_union_keeps_existing_allocations_and_both_orders(self):
        from tests.nfl2k5_allocator_stack import REQUESTS, compose
        previous = tuple(r for r in REQUESTS if r[0] != storage.OWNER)
        old = space._allocations(previous)
        new = space._allocations(REQUESTS)
        self.assertEqual([a for a in new if a['owner'] != storage.OWNER], old)
        forward, _ = compose(self.retail)
        backward, _ = compose(self.retail, reverse=True)
        self.assertEqual(forward, backward)
        self.assertEqual(storage.status(forward), 'applied')
        self.assertEqual(storage.apply(forward)[0], forward)


class EvidenceSaveTests(unittest.TestCase):
    def test_two_real_signed_saves_keep_all_added_choices(self):
        for name in ('f0', 'f1'):
            path = HUB / name / 'UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
            if not path.is_file():
                self.skipTest(f'private version-0 save absent: {path}')
            container = records.SaveContainer.load(path)
            source = container.savegame
            doc = codec.decode(source)
            self.assertEqual({s.asset_id for s in doc.stadiums}, set(storage.STADIUM_IDS))
            output = bytearray(source)
            added = [s for s in doc.stadiums if s.asset_id in storage.ADDED_IDS]
            for team, stadium in zip(doc.teams, added):
                field = team.offset + storage.TEAM_STADIUM
                struct.pack_into('<i', output, field, stadium.offset - field + 1)
            output = bytes(output)
            saved = codec.decode(output)
            roster = records.RosterDocument(output, base=0x300)
            career = franchise.FranchiseSave(output)
            for team, stadium in zip(saved.teams, added):
                self.assertEqual(team.stadium_index, stadium.index)
                self.assertEqual(roster.teams[team.index].stadium_index, stadium.index)
                self.assertEqual(career.team_stadium(team.index).asset_id, stadium.asset_id)
            self.assertEqual(roster.to_body(), output)
            self.assertEqual(saved.to_bytes(), output)
            self.assertEqual(career.to_bytes(), output)
            self.assertEqual(output[franchise.ARENA_END:], source[franchise.ARENA_END:])
            with tempfile.TemporaryDirectory(prefix='stadium-save-') as tmp:
                target = Path(tmp).resolve() / 'roundtrip.zip'
                container.write(target, output)
                reopened = records.SaveContainer.load(target)
                self.assertTrue(reopened.verified)
                self.assertEqual(reopened.savegame, output)
                for member, data in container.members.items():
                    if member not in (container.savegame_name, container.extra_name):
                        self.assertEqual(reopened.members[member], data)
            self.assertEqual(path.read_bytes(), source)


if __name__ == '__main__':
    unittest.main()

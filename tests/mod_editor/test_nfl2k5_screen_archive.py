"""Standalone transactional archive transport tests; all bytes are synthetic."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_screen_timing as timing
from mod_editor.core.errors import ValidationError


class MemoryArchive:
    def __init__(self, resources):
        self.entries = {}
        self.payload = bytearray()
        self.writes = 0
        self.fail_at = None
        self.rollback_failure = False
        self.readback_failure = False
        for index, raw in resources.items():
            self.entries[index] = SimpleNamespace(index=index, virtual_offset=len(self.payload), size=len(raw))
            self.payload.extend(raw)

    def entries_with_head(self, head):
        return [e for e in self.entries.values() if self.read(e.virtual_offset, len(head)) == head]

    def read_entry(self, index):
        e = self.entries[index]
        value = self.read(e.virtual_offset, e.size)
        if self.readback_failure and self.writes:
            self.readback_failure = False
            return value[:-1] + bytes([value[-1] ^ 1])
        return value

    def read(self, offset, size): return bytes(self.payload[offset:offset + size])

    def write(self, offset, raw):
        self.writes += 1
        if self.writes == self.fail_at:
            self.payload[offset:offset + max(1, len(raw) - 1)] = raw[:max(1, len(raw) - 1)]
            return len(raw) - 1
        if self.rollback_failure and self.fail_at and self.writes > self.fail_at:
            raise OSError('injected rollback failure')
        self.payload[offset:offset + len(raw)] = raw
        return len(raw)


def fixture():
    return {i: b'PLAY' + bytes([i - 307]) + bytes(7) for i in range(307, 344)}


def candidate(raw, level='D'):
    index = raw[4] + 307
    after = raw[:5] + b'\x01\x02' + raw[7:]
    return after, {'outer_index': index, 'book': str(index), 'changed_bytes': 2,
                   'changes': [{'offset': 5, 'before': '0000', 'after': '0102'}],
                   'already_applied': False, 'has_effect': True, 'capacity_ok': True}


class ScreenArchiveTransactionTests(unittest.TestCase):
    def test_transport_exact_receipt_addresses(self):
        archive = MemoryArchive(fixture())
        with patch.object(timing, 'apply', side_effect=candidate):
            receipt = timing.apply_to_archive(archive)
        self.assertEqual(receipt['changed_bytes'], 74)
        self.assertEqual(len(receipt['books']), 37)
        for index, raw in fixture().items():
            self.assertEqual(archive.read_entry(index), candidate(raw)[0])
        self.assertEqual(receipt['writes'][0]['virtual_offset'], 5)
        self.assertEqual(receipt['writes'][-1]['outer_index'], 343)

    def test_last_book_foreign_preflights_before_any_write(self):
        archive = MemoryArchive(fixture()); original = bytes(archive.payload)
        def apply(raw, level):
            if raw[4] == 36: raise ValidationError('foreign final book')
            return candidate(raw, level)
        with patch.object(timing, 'apply', side_effect=apply):
            with self.assertRaisesRegex(ValidationError, 'foreign final'):
                timing.apply_to_archive(archive)
        self.assertEqual(archive.writes, 0)
        self.assertEqual(archive.payload, original)

    def test_mixed_archive_and_misplaced_book_refuse(self):
        for mode in ('mixed', 'misplaced'):
            archive = MemoryArchive(fixture())
            def apply(raw, level):
                result, row = candidate(raw, level)
                if raw[4] == 36:
                    row['already_applied'] = mode == 'mixed'
                    if mode == 'misplaced': row['outer_index'] = 308
                return result, row
            with patch.object(timing, 'apply', side_effect=apply):
                with self.assertRaises(ValidationError): timing.apply_to_archive(archive)
            self.assertEqual(archive.writes, 0)

    def test_missing_book_refuses(self):
        resources = fixture(); resources.pop(343)
        archive = MemoryArchive(resources)
        with self.assertRaisesRegex(ValidationError, 'all 37'): timing.apply_to_archive(archive)
        self.assertEqual(timing.inspect_archive(archive)['status'], 'foreign')
        self.assertEqual(archive.writes, 0)

    def test_attempted_short_write_and_bad_readback_roll_back(self):
        for mode in ('short', 'readback'):
            archive = MemoryArchive(fixture()); original = bytes(archive.payload)
            if mode == 'short': archive.fail_at = 3
            else: archive.readback_failure = True
            with patch.object(timing, 'apply', side_effect=candidate):
                with self.assertRaisesRegex(ValidationError, 'short write|read-back differs'):
                    timing.apply_to_archive(archive)
            self.assertEqual(archive.payload, original)

    def test_rollback_failure_invalidates_output(self):
        archive = MemoryArchive(fixture()); archive.fail_at = 2; archive.rollback_failure = True
        with patch.object(timing, 'apply', side_effect=candidate):
            with self.assertRaisesRegex(ValidationError, 'discard this output copy'):
                timing.apply_to_archive(archive)

    def test_preimage_change_refuses_before_first_write(self):
        archive = MemoryArchive(fixture())
        def apply(raw, level):
            if raw[4] == 36: archive.payload[7] ^= 1
            return candidate(raw, level)
        with patch.object(timing, 'apply', side_effect=apply):
            with self.assertRaisesRegex(ValidationError, 'changed since'):
                timing.apply_to_archive(archive)
        self.assertEqual(archive.writes, 0)


if __name__ == '__main__': unittest.main()

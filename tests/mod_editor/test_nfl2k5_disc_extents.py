"""Wide XDVDFS bounds without allocating multi-gigabyte test files."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import tempfile
import unittest
from unittest.mock import patch

from mod_editor.core import nfl2k5_disc_extents as bounds
from tests.test_xdvdfs_robustness import _Image, _entry


class ExtentTests(unittest.TestCase):
    def test_wide_offsets_across_two_and_four_gib_and_last_sector(self):
        volume = 3912564  # candidate D
        for start in (1048575, 2097151, 3085555):
            self.assertEqual(bounds.check_extent(start, 4096, volume), start + 2)
        self.assertEqual(bounds.check_extent(volume - 1, 2048, volume), volume)
        with self.assertRaises(bounds.DiscExtentError):
            bounds.check_extent(volume - 1, 2049, volume)

    def test_file_cap_prevents_kernel_rounding_overflow(self):
        self.assertEqual(bounds.check_extent(1, 0xFFFFF800, 0x200000), 0x200000)
        for length in (0xFFFFF801, 0xFFFFFFFF, 0x100000000, -1):
            with self.assertRaises(bounds.DiscExtentError):
                bounds.check_extent(0, length, bounds.MAX_XEMU_SECTORS)

    def test_unrepresentable_fields_and_signed_lba_ceiling(self):
        for fields in ((-1, 0, 10), (1 << 32, 0, 10), (True, 0, 10),
                       (0, 0, 1 << 31), (0xFFFFFFFF, 2048, 0x7FFFFFFF)):
            with self.assertRaises(bounds.DiscExtentError):
                bounds.check_extent(*fields)
        self.assertEqual(bounds.check_extent(0x7FFFFFFE, 2048, 0x7FFFFFFF), 0x7FFFFFFF)

    def test_every_directory_and_file_checked_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = _Image()
            data, _ = image.add_directory([bytes(16)])
            child, child_size = image.add_directory([_entry(b'file', data, 16, 0x80)])
            root, root_size = image.add_directory([_entry(b'dir', child, child_size, 0x10),
                                                     _entry(b'empty', 0, 0, 0x10)])
            path = image.write(Path(tmp) / 'disc.iso', root, root_size)
            original = path.read_bytes()
            with patch.object(bounds, 'check_extent', wraps=bounds.check_extent) as check:
                result = bounds.validate_image(path)
            self.assertEqual(result['extents_checked'], 4)
            self.assertEqual({c.kwargs['name'] for c in check.call_args_list}, {'/', 'dir', 'dir/file', 'empty'})
            self.assertEqual(path.read_bytes(), original)
            path.write_bytes(original[:-1])
            with self.assertRaises(bounds.DiscExtentError):
                bounds.validate_image(path)


if __name__ == '__main__':
    unittest.main()

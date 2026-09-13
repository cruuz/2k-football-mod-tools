"""Exercise save-input boundaries missing from the integrated J8 snapshot."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from mod_editor.apf_studio import ps3_roster_convert as ps3
from tests.mod_editor.test_apf_ps3_roster_convert import Fixture
from tests.mod_editor.test_apf_stfs_roster_rehash import synthetic_stfs, reader, subject


class SaveInputBoundaryTests(unittest.TestCase):
    def test_root_userdata_zip_matches_the_raw_conversion_and_preserves_source(self):
        fixture = Fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "roster.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("USERDATA", fixture.ps3())
            before = source.read_bytes()
            output = root / "Roster.ROS"
            receipt = ps3.write_conversion(source, output)
            self.assertEqual(receipt.member, "USERDATA")
            self.assertEqual(output.read_bytes(), fixture.expected())
            self.assertEqual(source.read_bytes(), before)

    def test_single_copy_package_cannot_select_a_secondary_leaf(self):
        source = bytearray(synthetic_stfs(b"a" * 170 * 4096))
        top = 0xA000 + 0xAB * 4096
        source[top + 24 + 20] |= 0x40
        source[0x381:0x395] = hashlib.sha1(source[top:top + 4096]).digest()
        source[0x32C:0x340] = hashlib.sha1(source[0x344:0xA000]).digest()
        with self.assertRaises(reader.StfsRosterError):
            subject.rehash_roster(bytes(source), b"b" * 170 * 4096)


if __name__ == "__main__":
    unittest.main()

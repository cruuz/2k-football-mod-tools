"""Retail SPLB header, filename hash, and roster label agreement."""
import hashlib
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_book_identity as identity
from mod_editor.core import apf2k8_splb_writer as splb

INDEX=Path(os.environ.get('APF_RETAIL_0A','/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'))


@unittest.skipUnless(INDEX.is_file(),f'Retail APF 0A absent: {INDEX}')
class IdentityTests(unittest.TestCase):
    def test_four_headers_filename_ids_and_label_types(self):
        expected=[(293,'USER-d',0x2f551cf1,'83b3da4aa3fd412f50e242c130c6613d59aa27e0c7ddcf3943689dedb00d92e1'),
                  (656,'global-d',0x6c4ebf6f,'2740c33db3378ec9ffb8be222aed7cbd17c99f376c46b2ef240b28ca7e4e1408'),
                  (1037,'USER-o',0xad00822c,'e973cc4933d6678f3ff2493adf9a227a43d14c4ab89f8d50ae4d97fedbcd75a2'),
                  (1439,'global-o',0xee1b21b2,'e5ca4ff34db2eb19fd71869104ab8148f3bc34ea3a1a8f68d9156e851d9812f1')]
        for outer,name,name_id,digest in expected:
            _archive,entry,_record,body,_decoded,_stored=identity.read_resource(INDEX,identity.filename_id(name),'spb','SPLB')
            self.assertEqual((entry.table_index,entry.name_id),(outer,name_id))
            self.assertEqual(splb.parse_book(body,outer).name,name)
            self.assertEqual(hashlib.sha256(body).hexdigest(),digest)
        roster=identity.parse_roster_identity(identity.read_disc_roster(INDEX))
        self.assertEqual([r.index for r in roster.labels if r.kind=='USER-o'],list(range(25,32))+list(range(64,68)))
        self.assertEqual([r.index for r in roster.labels if r.kind=='USER-d'],list(range(56,64))+[68])
        self.assertFalse(any(r.kind.startswith('global-') for r in roster.labels))


if __name__=='__main__':
    unittest.main()

"""Noncompacting writer restrictions and exact toggle restoration."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_formation_calling as calling
from tests.mod_editor.test_apf_b69_schemes import fixture


class CallingTests(unittest.TestCase):
    def test_changes_only_B_all_duplicates_and_restores_exactly(self):
        book,_,_=fixture();out=bytearray(book)
        out[0x120:0x1D0]=out[0x70:0x120]
        out[0x1D0:0x280]=out[0x70:0x120]
        word=struct.unpack_from('>I',out,0x278)[0]
        struct.pack_into('>I',out,0x278,word|1<<24)
        book=splb._compact_normalize(bytes(out))
        masks=calling.membership_masks(book,0)
        changed=calling.set_never_call(book,0,True,masks)
        differences={i for i,(a,b) in enumerate(zip(book,changed)) if a!=b}
        self.assertEqual(differences,{0x11F,0x1CF})
        self.assertEqual(calling.membership_masks(changed,0),(0,0))
        self.assertEqual(calling.set_never_call(changed,0,False,masks),book)
        self.assertEqual(splb.row_coverage(book,fixture()[1]),splb.row_coverage(changed,fixture()[1]))

    def test_last_personnel_record_special_and_stale_masks_refused(self):
        book,_,_=fixture()
        with self.assertRaisesRegex(ValueError,'last formation'):
            calling.set_never_call(book,0,True,calling.membership_masks(book,0))
        with self.assertRaises(ValueError):calling.set_never_call(book,155,True,(1,))
        with self.assertRaisesRegex(ValueError,'membership changed'):
            calling.set_never_call(book,0,True,(1,))


if __name__=='__main__':unittest.main(verbosity=2)

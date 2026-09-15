"""Audit append/repoint arithmetic; deliberately does not claim a disc proof."""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/'tools')]
from tools.b70_t2_stadium_probe import RETAIL
from nfl_outer import parse_archive, read_entry_bytes, HEADER_SIZE, ENTRY_SIZE
from nfl_txtr import parse_chunks
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from capstone import Cs, CS_ARCH_X86, CS_MODE_32


def main():
    archive = parse_archive(RETAIL/'vc_53450030/0')
    entry = archive.entries[3734]
    chunks = parse_chunks(read_entry_bytes(archive,entry),allow_trailing=True)
    grown = json.loads((ROOT/'reports/b70_t2/grown-loader.json').read_text())
    extra = grown['grown_stored_bytes']-chunks[9].stored_size
    ordered = sorted(archive.entries,key=lambda e:e.virtual_offset)
    gaps = [b.virtual_offset-a.virtual_end for a,b in zip(ordered,ordered[1:])]
    size, append = entry.size+extra, archive.virtual_size
    record = struct.pack('<III',entry.name_id,size,append//2048)
    assert struct.unpack('<III',record) == (entry.name_id,size,append//2048)
    report = dict(package_outer=3734,package_bytes=entry.size,tset_chunk=9,chunk_offset=chunks[9].offset,
        original_body_bytes=chunks[9].stored_size,grown_body_bytes=grown['grown_stored_bytes'],
        whole_package_growth=extra,grown_package_bytes=size,
        entry_record_offset=HEADER_SIZE+ENTRY_SIZE*entry.table_index,
        candidate_append_virtual_offset=append,candidate_entry_sector=append//2048,
        candidate_final_volume=archive.packs[-1].name,candidate_added_volume_blocks=(size+2047)//2048,
        largest_inter_entry_gap=max(gaps),tail_free_bytes=archive.virtual_size-ordered[-1].virtual_end,
        index_fields_roundtrip=True,offline_disc_roundtrip=False,native_archive_lookup=False,
        growth_conclusion='UNPROVED. Serialization arithmetic and isolated TSET load do not establish archive/XDVDFS relocation.')
    image=XbeImage((RETAIL/'default.xbe').read_bytes())
    decoder=Cs(CS_ARCH_X86,CS_MODE_32)
    report['loader_instructions']=[dict(va=hex(i.address),instruction=i.mnemonic+' '+i.op_str)
        for i in decoder.disasm(image.read(0x451d0,0x8a),0x451d0)
        if i.address in (0x451d0,0x451da,0x451ec,0x451f5,0x45228,0x4522a,0x45235)]
    (ROOT/'reports/b70_t2/growth-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()

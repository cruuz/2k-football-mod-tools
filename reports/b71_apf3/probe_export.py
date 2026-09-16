"""Measure the Straight / three Queens edit without writing retail bytes."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from tests.mod_editor.test_apf_playcall_research_native import INDEX
from mod_editor.core import apf2k8_splb_writer as s, apf2k8_book_clone as clone
from mod_editor.core import apf2k8_book_identity as identity


def straight_book():
    original = s.read_book(INDEX, 130)
    donor = s.read_book(INDEX, 1411)
    record = next(r for r in donor.records if r.populated and r.formation_index == 133)
    slot = next(r.record_index for r in original.records if not r.populated)
    changes = [s.MembershipChange(130, slot, e.play_index, True) for e in record.entries]
    changes.append(s.TrailerReplace(130, slot, 133, record.category_index))
    compiled = s.compile_book(original, changes)
    s.verify_book(original.body, compiled.replacement, changes)
    body = compiled.replacement
    queens = [r.formation_index for r in original.records if r.populated and r.category_index == 6]
    assert queens == [2, 14, 24]
    steps = []
    source = identity.read_resource(INDEX, identity.filename_id(original.name), 'spb', 'SPLB')
    for form in [None, *queens]:
        if form is not None:
            body = s.remove_formation(body, form).book
        with patch.object(s.apf_texture_patch, '_optimal_binary', return_value=None):
            packed, transport = clone.rebuild_resource(source, body)
        record_iff, original_body, decoded, original_entry = source[2:]
        part, block = record_iff.files[0].parts[0], record_iff.blocks[0]
        reader = s.apf_texture_patch.BytesReader(packed)
        parsed = s.apf_inner.parse_iff(reader, source[1])
        wanted = decoded[:part.offset] + body + decoded[part.offset + part.length:]
        after = s.apf_inner.decode_block(reader, parsed, 0, 16*1024*1024)
        assert after == wanted
        assert after[part.offset:part.offset+part.length] == body
        assert parsed.files == record_iff.files
        assert len(packed) == source[1].size == 2048
        footer_size = 8 + record_iff.footer.payload_size
        assert packed[parsed.file_length:parsed.file_length+footer_size] == original_entry[record_iff.file_length:record_iff.file_length+footer_size]
        rows = [r for r in s.parse_book(body, 130).records if r.populated]
        steps.append({'removed': form, 'formations': [r.formation_index for r in rows],
                      'body_sha256': hashlib.sha256(body).hexdigest(),
                      'entry_sha256': hashlib.sha256(packed).hexdigest(),
                      'old_active_bytes': record_iff.header_size + 20 + footer_size + transport['transport']['token_preserving_bytes'],
                      **transport})
    assert s.read_book(INDEX, 130).body == original.body
    assert set(r.formation_index for r in rows) == ({r.formation_index for r in original.records if r.populated} - set(queens)) | {133}
    return original, s.parse_book(body, 130), steps


if __name__ == '__main__':
    _, _, steps = straight_book()
    result = {'status': 'PROVED offline exact decoded bytes; gameplay UNWITNESSED',
              'book': 'O-ManBlock', 'donor': 'O-Shotgun', 'added': 133,
              'removed': [2, 14, 24], 'steps': steps}
    Path(__file__).with_name('export.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))

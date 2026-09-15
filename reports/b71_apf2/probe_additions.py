"""Read-only allocation reproduction; print measurements, never retail bodies."""
from mod_editor.core import apf2k8_splb_writer as s
from tests.mod_editor.test_apf_playcall_research_native import INDEX

for outer in (767, 130, 369):
    book, donor = s.read_book(INDEX, outer), s.read_book(INDEX, 1411)
    forms = {r.formation_index for r in book.records if r.populated}
    changes = []
    first = next(r.record_index for r in book.records if not r.populated)
    additions = [r for r in donor.records if r.populated and r.formation_index not in forms]
    for number, record in enumerate(additions):
        changes.extend(s.MembershipChange(outer, first + number, e.play_index, True) for e in record.entries)
        changes.append(s.TrailerReplace(outer, first + number, record.formation_index, record.category_index))
        try:
            result = s.build_book_patch(INDEX, changes)
        except Exception as exc:
            print(book.name, number + 1, record.formation_index, type(exc).__name__, str(exc), flush=True)
            break
        print(book.name, number + 1, record.formation_index, len(result.entry_bytes), result.report['h7a_transport']['strategy'], flush=True)

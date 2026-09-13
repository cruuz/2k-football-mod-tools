"""Noncompacting exclusion from the ordinary CPU category/formation lottery.

Word B=0 excludes a record in 84A8B660/A330 and 848693F8. Primary category,
plays, ratings and order stay intact. Cached special calls bypass that gate;
this API deliberately refuses special formations. See the beta-69 native proof.
"""
import struct

from . import apf2k8_splb_writer as splb
from .apf2k8_playcall_model import PlaycallError, _int


def membership_masks(book, formation):
    records = splb._formation_records(book, formation)
    return tuple(int.from_bytes(r.trailer[4:], 'big') for r in records)


def set_never_call(book, formation, never, restore_masks):
    """Restore masks come from the reviewed, persisted enable event."""
    _int(formation, 0, 150, 'Ordinary formation')
    if type(never) is not bool:
        raise PlaycallError('Choose whether to exclude this formation from ordinary CPU calls')
    records = splb._formation_records(book, formation)
    if not isinstance(restore_masks, tuple) or len(restore_masks) != len(records):
        raise PlaycallError('The formation records changed; review Never call again')
    for mask in restore_masks:
        _int(mask, 1, (1 << 28)-1, 'Original personnel membership')
    current = membership_masks(book, formation)
    expected = restore_masks if never else (0,)*len(records)
    if current != expected:
        raise PlaycallError('The formation membership changed; undo the intervening edit and review again')
    parsed = splb.parse_book(book, 0)
    if never:
        # Retaining A retains its advertised category after normalization. Keep
        # another B member for every affected category, so no cached personnel
        # or independent lineup row points only to an excluded record.
        affected = 0
        for r, mask in zip(records, restore_masks):
            affected |= mask | (1 << r.category_index)
        surviving = 0
        for r in parsed.records:
            if r.populated and r.formation_index != formation:
                surviving |= int.from_bytes(r.trailer[4:], 'big')
        if affected & ~surviving:
            raise PlaycallError('This is the last formation for one of its personnel categories; keep another formation or use Remove formation and review coverage')
    output = bytearray(book)
    for r, mask in zip(records, restore_masks):
        struct.pack_into('>I', output, splb.RECORD_BASE+r.record_index*splb.RECORD_STRIDE+0xAC, 0 if never else mask)
    result = bytes(output)
    if membership_masks(result, formation) != ((0,)*len(records) if never else restore_masks):
        raise PlaycallError('Never call membership failed readback')
    return result

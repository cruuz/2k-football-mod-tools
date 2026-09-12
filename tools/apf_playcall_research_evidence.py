"""Sparse instruction/difference receipts; consumes images in memory only."""
from __future__ import annotations

import difflib
import hashlib
import struct

BASE = 0x82000000
# End addresses are exclusive. Broader spans include adjacent helper routines
# and embedded switch tables, so no instruction inside a span is omitted.
SPANS = (
    ('wrapper', 0x84815608, 0x84815674, 0xCA0),
    ('lineup_ladder', 0x84860730, 0x84860A00, 0xCA0),
    ('roulette', 0x84863388, 0x84863720, 0xCA0),
    ('situation', 0x84866258, 0x84867938, 0xCD0),
    ('cpu_selection', 0x84867BF8, 0x8486D0F4, 0xD00),
    ('team_tendency', 0x84928CF0, 0x8492A6E0, 0xEC8),
    ('tendency_install', 0x8492F188, 0x8492F270, 0xEC8),
    ('label_to_book_filename', 0x849D6200, 0x849D6500, 0xEC8),
    ('loaded_book_install_and_merge', 0x849D4050, 0x849D4228, 0xEC8),
    ('master_validation', 0x84A88BD8, 0x84A88F18, 0xFD0),
    ('book_access_and_normalization', 0x84A89B40, 0x84A8D150, 0xFD0),
    ('category_compatibility', 0x84A9BFD8, 0x84A9C1C8, 0xFD0),
    ('master_types', 0x84A94068, 0x84A940D0, 0xFD0),
)
VARIABLE_SPANS = (
    ('formation_to_category', 0x84864AB8, 0x84864B30, 0x84865758, 0x84865800),
    ('commit_supplied_call', 0x84867938, 0x84867AE8, 0x84868608, 0x848687E8),
)
CURVES = (
    ('requested_row', 0x820C8884),
    ('offense_row_distance', 0x820C88A8),
    ('defense_row_distance', 0x820C88D4),
    ('formation_rating', 0x820C88F0),
    ('category_rating', 0x820C891C),
    ('play_x_rating', 0x820C8990),
)
PINS = (
    0x84815638, 0x84815664, 0x8481566C,
    0x848607D0, 0x84860808, 0x84860888,
    0x848676A0, 0x84867738, 0x848677D4, 0x84867834,
    0x84868D04, 0x84868D2C, 0x84868EEC, 0x84868F10, 0x84868F2C,
    0x84868F58, 0x84869058, 0x84869138, 0x84869140,
    0x84869318, 0x848694B0, 0x848695A0, 0x848695C0, 0x848695F0,
    0x8486A1F8, 0x8486A2E8, 0x8486A478, 0x8486A4C8, 0x8486A778,
    0x8486A958, 0x8486A9A0, 0x8486AA18, 0x8486AC00, 0x8486AC08,
    0x8486AEB0, 0x8486B198, 0x8486B2D0, 0x8486B328, 0x8486B638,
    0x8486B690, 0x8486BC08, 0x8486BD90, 0x8486C958, 0x8486C95C,
    0x8486C974, 0x8486C9C8, 0x8486CA00, 0x8486CA80, 0x8486CAB8,
    0x8486CEC4, 0x8486CED4, 0x8486CF84, 0x8486D038, 0x8486D05C,
    0x8486D088, 0x8486D09C, 0x8486D0B8, 0x8486D0C4, 0x8486D0D0,
    0x84929AE4, 0x84929AE8, 0x84929B24, 0x84929B5C, 0x84929CE4,
    0x84929E08, 0x84929E10, 0x8492A2A8, 0x8492A440, 0x8492A450,
    0x8492A458, 0x8492A61C, 0x8492A640, 0x8492F1F8,
    0x84A8A258, 0x84A8A330, 0x84A8AAB4, 0x84A8B36C, 0x84A8C5C8,
    0x84A8C790, 0x84A8CAC0, 0x84A8CB6C, 0x84A8CBB0,
)


def evidence(base, updated):
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN
    decoder = Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN)

    def word(image, address):
        return struct.unpack_from('>I', image, address - BASE)[0]

    def assembly(image, address):
        value = word(image, address)
        # Embedded jump-table words are addresses, not lwzu instructions.
        if 0x84630000 <= value < 0x84D10000 and value % 4 == 0:
            return f'code_pointer 0x{value:08X}'
        decoded = list(decoder.disasm(image[address - BASE:address - BASE + 4], address))
        return f'{decoded[0].mnemonic} {decoded[0].op_str}'.rstrip() if decoded else f'Xenon/undecoded 0x{value:08X}'

    def region(image, start, end):
        return {'start': f'{start:08X}', 'end_exclusive': f'{end:08X}',
                'sha256': hashlib.sha256(image[start - BASE:end - BASE]).hexdigest()}

    spans = []
    for name, start, end, delta in SPANS:
        differences = []
        for address in range(start, end, 4):
            if word(base, address) != word(updated, address + delta):
                differences.append([f'{address:08X}', assembly(base, address),
                                    f'{address + delta:08X}', assembly(updated, address + delta)])
        spans.append({'name': name, 'base': region(base, start, end),
                      'tu': region(updated, start + delta, end + delta),
                      'differences': differences})
    for name, start, end, tu_start, tu_end in VARIABLE_SPANS:
        base_words = [word(base, a) for a in range(start, end, 4)]
        tu_words = [word(updated, a) for a in range(tu_start, tu_end, 4)]
        matcher = difflib.SequenceMatcher(None, base_words, tu_words, autojunk=False)
        differences = []
        for tag, i, j, k, l in matcher.get_opcodes():
            if tag == 'equal':
                continue
            differences.append({'operation': tag,
                                'base': [[f'{a:08X}', assembly(base, a)] for a in range(start + i * 4, start + j * 4, 4)],
                                'tu': [[f'{a:08X}', assembly(updated, a)] for a in range(tu_start + k * 4, tu_start + l * 4, 4)]})
        spans.append({'name': name, 'base': region(base, start, end),
                      'tu': region(updated, tu_start, tu_end), 'differences': differences})
    curves = []
    for name, address in CURVES:
        count = word(base, address)
        assert 0 < count <= 16
        size = 4 + 8 * count
        assert base[address - BASE:address - BASE + size] == updated[address + 0x20 - BASE:address + 0x20 - BASE + size]
        values = struct.unpack_from(f'>{count * 2}f', base, address + 4 - BASE)
        curves.append({'name': name, 'base': f'{address:08X}', 'tu': f'{address + 0x20:08X}',
                       'pairs': [list(values[i:i + 2]) for i in range(0, len(values), 2)]})
    return {'schema': 'apf_playcall_research_v1', 'grade': 'PROVED pinned images, static disassembly',
            'base_sha256': hashlib.sha256(base).hexdigest(), 'tu_sha256': hashlib.sha256(updated).hexdigest(),
            'difference_columns': ['base_address', 'base_instruction', 'tu_address', 'tu_instruction'],
            'scope': 'Every changed instruction word in the explicitly hashed spans; not an executable-wide diff.',
            'spans': spans, 'curves': curves,
            'pins': [[f'{a:08X}', assembly(base, a)] for a in PINS]}

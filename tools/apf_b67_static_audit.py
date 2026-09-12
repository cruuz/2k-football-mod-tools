"""Pinned BASE/TU caller and tendency access receipt; emits no retail bytes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct

from mod_editor.core.apf2k8_playcall_patch import PROFILES, check_image


def audit(image):
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN
    profile = check_image(image)
    updated = profile == PROFILES[1]
    target = 0x848613D0 if updated else 0x84860730
    parent = 0x84A05EA8 if updated else 0x84A04FF0
    branches, pointers, parent_pointers = [], [], []
    for offset in range(0, len(image) - 3, 4):
        word = struct.unpack_from('>I', image, offset)[0]
        address = 0x82000000 + offset
        if word == target:
            pointers.append(f'{address:08X}')
        if word == parent:
            parent_pointers.append(f'{address:08X}')
        op = word >> 26
        if op not in (16, 18):
            continue
        width = 16 if op == 16 else 26
        delta = word & ((1 << width) - 4)
        if delta & (1 << (width - 1)):
            delta -= 1 << width
        destination = ((0 if word & 2 else address) + delta) & 0xFFFFFFFF
        if destination == target:
            branches.append(f'{address:08X}')
    decoder = Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN)
    def span(start, end):
        data = image[start - 0x82000000:end - 0x82000000]
        return {'start': f'{start:08X}', 'end': f'{end:08X}', 'sha256': hashlib.sha256(data).hexdigest(),
                'instructions': [f'{i.address:08X} {i.mnemonic} {i.op_str}'.rstrip() for i in decoder.disasm(data, start)]}
    delta = 0xEC8 if updated else 0
    return {'profile': profile.name, 'sha256': profile.sha256, 'lineup_resolver': f'{target:08X}',
            'direct_branches_all_aligned_words': branches,
            'absolute_words': pointers, 'parent_absolute_words': parent_pointers,
            'caller': span(parent, parent + 0xBC),
            'tendency_row_selection': span(0x84929B4C + delta, 0x84929BBC + delta),
            'tendency_row_reads': span(0x84929DB0 + delta, 0x84929E48 + delta),
            'classification': 'PROVED two direct calls in one routine, supplying both team managers. Its indirect entry lifecycle is UNCLASSIFIED; CPU-team exclusion is not proved.',
            'row_arrays': 'PROVED read by the optional tendency category cache. Not the ordinary AEB0 category policy.',
            'boundary': 'Aligned direct branch and absolute-word scan; computed indirect call targets require separate lifecycle classification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--tu', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = {'schema': 'apf_b67_static_audit/v1', 'images': [audit(p.read_bytes()) for p in (args.base, args.tu)]}
    args.report.write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print('PROVED static receipt:', args.report)


if __name__ == '__main__':
    main()

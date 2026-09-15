"""Versioned per-book exclusions for twelve live down/distance buckets.

The native extension filters ordinary draws after retail enumeration. Empty
filtered draws retain the original candidates. Special phases bypass it.
Policy is immutable; only two last-draw receipts live in writable padding.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import struct
import tomllib

from .errors import ValidationError
from .apf2k8_playcall_patch import (
    IMAGE_BASE, PROFILES, _Assembler, _branch, _d, _x, _rl, check_image,
)

SCHEMA = 'apf2k8_situation_mask/v1'
CLASSIFICATION = 'EXPERIMENTAL'
DATA_START, DATA_LIMIT = 0x8462CA00, 0x84630000
CODE_START, CODE_LIMIT = 0x84D0E300, 0x84D0F000
RECEIPT_START, RECEIPT_LIMIT = 0x852D6500, 0x852D6540
MAX_BOOKS, KEY_COUNT, MASK_BYTES, ENTRY_SIZE = 48, 12, 20, 268
FRAME = 0x300
# Separate pinned sites; no general TU relocator.
HOOKS = {'base': (0x8486B198, 0x848696C0),
         'tu_1_1': (0x8486BE98, 0x8486A3C0)}
GAME = {'base': 0x851A2780, 'tu_1_1': 0x851A27B0}
KEY_LABELS = tuple(f'{down}{("st", "nd", "rd", "th")[down-1]} down: {label}'
                   for down in range(1, 5)
                   for label in ('up to 2 yards', 'over 2 through 7 yards', 'over 7 yards'))


def live_key(down, distance_units):
    """Absolute single-precision longitudinal target-minus-ball distance.

    Thresholds are f32(182.88) and f32(640.08) game units. This uses actual
    down, with no event/clock/score aliases or requested-row RNG in the key.
    """
    if type(down) is not int or not 1 <= down <= 4:
        raise ValidationError('The situation mask needs a scrimmage down from 1 to 4')
    distance = abs(struct.unpack('>f', struct.pack('>f', distance_units))[0])
    if not distance < float('inf'):
        raise ValidationError('The situation mask needs a finite distance')
    cuts = [struct.unpack('>f', struct.pack('>f', n))[0] for n in (182.88, 640.08)]
    return (down - 1) * 3 + sum(distance > cut for cut in cuts)


def situation_key(situation):
    from .apf2k8_playcall_model import _distance
    return live_key(situation.down, _distance(situation))


def canonical_policies(policies):
    if not isinstance(policies, dict) or len(policies) > MAX_BOOKS:
        raise ValidationError(f'Choose at most {MAX_BOOKS} named books for the situation patch')
    result = {}
    for name, rows in sorted(policies.items()):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 -]{0,26}', name):
            raise ValidationError('Situation masks need a book name of 1 to 27 ASCII letters, digits, spaces or hyphens')
        if not isinstance(rows, (list, tuple)) or len(rows) != KEY_COUNT:
            raise ValidationError('Supply all twelve live situation masks for each book')
        checked = []
        for values in rows:
            if not isinstance(values, (list, tuple)) or any(type(v) is not int or not 0 <= v < 151 for v in values):
                raise ValidationError('Exclude ordinary formations 0 through 150; special formations keep their native paths')
            if len(set(values)) != len(values):
                raise ValidationError('A situation repeats a formation exclusion')
            checked.append(sorted(values))
        if any(checked):
            result[name] = checked
    return result


def encode_data(policies):
    policies = canonical_policies(policies)
    data = bytearray(struct.pack('>4I', 0x41504634, 1, len(policies), ENTRY_SIZE))
    for name, rows in policies.items():
        data.extend(name.encode('ascii').ljust(28, b'\0'))
        for row in rows:
            words = [0] * 5
            for formation in row:
                words[formation // 32] |= 1 << (formation % 32)
            data.extend(struct.pack('>5I', *words))
    return bytes(data).ljust(DATA_LIMIT - DATA_START, b'\0')


def decode_data(data):
    if len(data) != DATA_LIMIT - DATA_START:
        raise ValidationError('Situation data allocation has the wrong size')
    magic, version, count, stride = struct.unpack_from('>4I', data)
    if (magic, version, stride) != (0x41504634, 1, ENTRY_SIZE) or count > MAX_BOOKS:
        raise ValidationError('Situation data header differs from version 1')
    result = {}
    try:
        for i in range(count):
            at = 16 + ENTRY_SIZE * i
            raw = data[at:at+28]
            name = raw.split(b'\0')[0].decode('ascii')
            if name in result:
                raise ValueError('Duplicate book name')
            rows = []
            for key in range(KEY_COUNT):
                words = struct.unpack_from('>5I', data, at + 28 + key * MASK_BYTES)
                rows.append([f for f in range(160) if words[f//32] & (1 << (f%32))])
            result[name] = rows
        if encode_data(result) != data:
            raise ValueError('Noncanonical names, order, masks or padding')
    except (UnicodeError, ValueError, struct.error) as exc:
        raise ValidationError(f'Invalid situation data: {exc}') from exc
    return result


class Assembler(_Assembler):
    def d(self, op, rt, ra, imm): self.emit(_d(op, rt, ra, imm))
    def li(self, r, n): self.d(14, r, 0, n)
    def addi(self, r, a, n): self.d(14, r, a, n)
    def lwz(self, r, a, n): self.d(32, r, a, n)
    def stw(self, r, a, n): self.d(36, r, a, n)
    def cmpi(self, r, n): self.d(10, 24, r, n)
    def cmp(self, a, b): self.emit(_x(24, a, b, 32))
    def mr(self, a, s): self.emit(_x(s, a, s, 444))
    def addr(self, r, address):
        self.d(15, r, 0, (address + 0x8000) >> 16)
        self.addi(r, r, address & 0xffff)
    def add(self, r, a, b): self.emit(_x(r, a, b, 266))
    def bits(self, source, dest, shift, mb, me): self.emit(_rl(source, dest, shift, mb, me))


def _leaf(start, hook, profile, category):
    a = Assembler(start)
    e = a.emit
    count, book_reg = (24, 28) if category else (27, 29)
    saved = (0, *range(3, 32))
    slots = {r: 8 + 8*i for i, r in enumerate(saved)}
    # Preserve Xenon's full-width ABI, including upper GPR halves and FPSCR.
    a.d(62, 1, 1, -FRAME | 1)
    for r, offset in slots.items(): a.d(62, r, 1, offset)
    e(_x(0, 0, 0, 19)); a.stw(0, 1, 0xF8)
    a.d(54, 0, 1, 0x100); a.d(54, 13, 1, 0x108)
    e(0xFDA0048E)  # mffs f13
    a.d(54, 13, 1, 0x118)
    a.mr(14, book_reg)
    a.cmpi(count, 1); a.jump('restore', 'lt')
    a.cmpi(count, 40); a.jump('restore', 'gt')
    if category:
        a.cmpi(26, 10); a.jump('restore', 'gt')
        a.cmpi(21, 0); a.jump('restore', 'ne')  # explicit formation path
    else:
        a.cmpi(28, 0); a.jump('restore', 'eq')
        a.cmpi(25, 0); a.jump('restore', 'ne')  # explicit play path
        a.d(34, 3, 28, 4); a.bits(3, 3, 0, 26, 31)
        a.cmpi(3, 10); a.jump('restore', 'gt')
    a.addr(3, GAME[profile.name]); a.lwz(4, 3, 0x34)
    a.cmpi(4, 4); a.jump('restore', 'ne')  # kick/try/pregame untouched
    a.lwz(3, 3, 0x6C); a.cmpi(3, 0); a.jump('restore', 'eq')
    a.lwz(4, 3, 4); a.cmpi(4, 1); a.jump('restore', 'lt')
    a.cmpi(4, 4); a.jump('restore', 'gt')
    a.addi(4, 4, -1); a.d(7, 17, 4, 3)
    a.d(48, 0, 3, 0x28); a.d(48, 13, 3, 0x18)
    e(0xEC006828)  # fsubs f0,f0,f13
    e(0xFC000210)  # fabs f0,f0
    a.d(52, 0, 1, 0x110); a.lwz(4, 1, 0x110)
    a.addr(3, 0x7F800000); a.cmp(4, 3); a.jump('restore', 'ge')
    for i, value in enumerate((182.88, 640.08)):
        a.addr(3, struct.unpack('>I', struct.pack('>f', value))[0])
        a.cmp(4, 3); a.jump(f'distance{i}', 'gt'); a.jump('distance_done')
        a.label(f'distance{i}'); a.addi(17, 17, 1)
    a.label('distance_done')
    a.cmpi(14, 0); a.jump('restore', 'eq')
    a.lwz(15, 14, 0x7E0C); a.cmpi(15, 0); a.jump('restore', 'eq')
    for offset, value in ((0x34, 163), (0x38, 586), (0x3C, 28)):
        a.lwz(3, 15, offset); a.cmpi(3, value); a.jump('restore', 'ne')
    a.addr(16, DATA_START)
    for offset, value in ((0, 0x41504634), (4, 1), (12, ENTRY_SIZE)):
        a.lwz(3, 16, offset); a.addr(4, value); a.cmp(3, 4); a.jump('restore', 'ne')
    a.lwz(18, 16, 8); a.cmpi(18, MAX_BOOKS); a.jump('restore', 'gt')
    a.cmpi(18, 0); a.jump('restore', 'eq')
    a.addi(16, 16, 16); a.li(19, 0)
    a.label('book')
    a.addi(3, 14, 0x30); a.mr(4, 16); a.li(5, 28)
    a.label('name')
    a.d(40, 6, 3, 0); a.d(34, 7, 4, 0); a.cmp(6, 7); a.jump('next_book', 'ne')
    a.cmpi(7, 0); a.jump('found', 'eq')
    a.addi(3, 3, 2); a.addi(4, 4, 1); a.addi(5, 5, -1)
    a.cmpi(5, 0); a.jump('name', 'ne'); a.jump('restore')
    a.label('next_book')
    a.addi(16, 16, ENTRY_SIZE); a.addi(19, 19, 1)
    a.cmp(19, 18); a.jump('book', 'lt'); a.jump('restore')
    a.label('found')
    a.d(7, 3, 17, MASK_BYTES); a.add(16, 16, 3); a.addi(16, 16, 28)
    a.li(3, 0)
    for offset in range(0, MASK_BYTES, 4):
        a.lwz(4, 16, offset); e(_x(3, 3, 4, 444))
    a.cmpi(3, 0); a.jump('restore', 'eq')
    # Save receipt context before using those registers for scans.
    a.stw(17, 1, 0x270); a.stw(19, 1, 0x274)
    a.lwz(18, 1, slots[count]+4)  # original count
    a.addi(20, 1, FRAME + (0x110 if category else 0xF0))
    a.addi(21, 1, FRAME + (0x70 if category else 0x50))
    a.li(22, 0); a.li(23, 0)
    a.label('candidate')
    a.bits(22, 3, 2, 0, 29); e(_x(24, 20, 3, 23))
    if category:
        # First determine the retail primary preference before applying masks.
        a.addi(3, 15, 0x44); e(_x(25, 3, 24, 40))
        a.cmpi(25, 28*16); a.jump('restore', 'ge')
        a.bits(25, 25, 28, 4, 31)
        a.li(26, 0)
        for pass_number in (0, 1):
            a.addi(27, 14, 0x70); a.li(28, 176)
            a.label(f'record{pass_number}')
            a.d(40, 3, 27, 0); a.bits(3, 3, 0, 22, 31)
            a.cmpi(3, 0x3FF); a.jump(f'end{pass_number}', 'eq')
            a.lwz(29, 27, 0xA8); a.bits(29, 30, 8, 24, 31)
            a.cmpi(30, 163); a.jump('restore', 'ge')
            a.d(7, 3, 30, 184); a.add(31, 15, 3); a.addi(31, 31, 0x244)
            # Primary scan and final candidates both skip cached specials.
            a.lwz(3, 1, slots[27]+4); a.lwz(3, 3, 0xC)
            for offset in (0x50, 0x58, 0x60):
                a.lwz(4, 3, offset); a.cmp(31, 4); a.jump(f'next{pass_number}', 'eq')
            a.bits(29, 3, 15, 25, 31)
            if pass_number == 0:
                a.cmp(3, 25); a.jump('next0', 'ne'); a.li(26, 1); a.jump('end0')
            else:
                a.cmpi(26, 0); a.jump('membership', 'eq')
                a.cmp(3, 25); a.jump('next1', 'ne')
                a.label('membership')
                a.lwz(3, 27, 0xAC); a.li(4, 1); e(_x(4, 4, 25, 24))
                e(_x(3, 3, 4, 28)); a.cmpi(3, 0); a.jump('next1', 'eq')
                a.lwz(3, 31, 8); a.bits(3, 3, 0, 31, 31)
                a.cmpi(3, 0); a.jump('next1', 'ne')
                # Any unexcluded structural member keeps the category. Native
                # formation enumeration remains the authority for play gates.
                a.cmpi(30, 151); a.jump('keep', 'ge')
                a.bits(30, 3, 29, 3, 29); e(_x(3, 16, 3, 23))
                a.bits(30, 4, 0, 27, 31); a.li(5, 1); e(_x(5, 5, 4, 24))
                e(_x(3, 3, 5, 28)); a.cmpi(3, 0); a.jump('keep', 'eq')
            a.label(f'next{pass_number}')
            a.addi(27, 27, 176); a.addi(28, 28, -1); a.cmpi(28, 0)
            a.jump(f'record{pass_number}', 'ne')
            a.label(f'end{pass_number}')
        a.jump('next_candidate')
    else:
        a.addi(3, 15, 0x244); e(_x(4, 3, 24, 40))
        a.li(5, 184); e(_x(30, 4, 5, 459))
        a.cmpi(30, 163); a.jump('restore', 'ge')
        a.d(7, 3, 30, 184); a.cmp(3, 4); a.jump('restore', 'ne')
        a.cmpi(30, 151); a.jump('keep', 'ge')
        a.bits(30, 3, 29, 3, 29); e(_x(3, 16, 3, 23))
        a.bits(30, 4, 0, 27, 31); a.li(5, 1); e(_x(5, 5, 4, 24))
        e(_x(3, 3, 5, 28)); a.cmpi(3, 0); a.jump('next_candidate', 'ne')
    a.label('keep')
    a.bits(22, 3, 2, 0, 29); e(_x(4, 21, 3, 23))
    a.bits(23, 3, 2, 0, 29); a.addi(5, 1, 0x120); e(_x(24, 5, 3, 151))
    a.addi(5, 1, 0x1C0); e(_x(4, 5, 3, 151)); a.addi(23, 23, 1)
    a.label('next_candidate')
    a.addi(22, 22, 1); a.cmp(22, 18); a.jump('candidate', 'lt')
    a.addr(3, RECEIPT_START + (0 if category else 24))
    a.lwz(4, 1, 0x270); a.stw(4, 3, 0)
    a.lwz(4, 1, 0x274); a.stw(4, 3, 4)
    a.stw(18, 3, 8); a.stw(23, 3, 12); a.li(4, 0); a.stw(4, 3, 16)
    a.cmpi(23, 0); a.jump('commit', 'ne')
    a.li(4, 1); a.stw(4, 3, 16); a.lwz(4, 3, 20); a.addi(4, 4, 1); a.stw(4, 3, 20)
    a.jump('restore')
    a.label('commit')
    a.cmp(23, 18); a.jump('restore', 'eq')
    # Update both halves of saved count: the native count is an unsigned int.
    a.li(3, 0); a.stw(3, 1, slots[count]); a.stw(23, 1, slots[count]+4)
    a.li(22, 0)
    a.label('copy')
    a.bits(22, 3, 2, 0, 29); a.addi(4, 1, 0x120); e(_x(5, 4, 3, 23)); e(_x(5, 20, 3, 151))
    a.addi(4, 1, 0x1C0); e(_x(5, 4, 3, 23)); e(_x(5, 21, 3, 151))
    a.addi(22, 22, 1); a.cmp(22, 23); a.jump('copy', 'lt')
    a.label('restore')
    a.d(50, 13, 1, 0x118); e(0xFDFE6D8E)  # mtfsf 255,f13
    a.d(50, 0, 1, 0x100); a.d(50, 13, 1, 0x108)
    a.lwz(0, 1, 0xF8); e(0x7C0FF120)
    for r, offset in slots.items(): a.d(58, r, 1, offset)
    a.d(58, 1, 1, 0)
    a.li(5, 3 if category else 1)
    e(_branch(start + len(a.words)*4, hook+4))
    return a.finish()


def assemble(profile):
    if profile not in PROFILES:
        raise ValidationError('Choose the pinned BASE or TU 1.1 profile')
    category_hook, formation_hook = HOOKS[profile.name]
    first = _leaf(CODE_START, category_hook, profile, True)
    second_start = CODE_START + len(first)
    second = _leaf(second_start, formation_hook, profile, False)
    code = first + second
    if len(code) > CODE_LIMIT - CODE_START:
        raise ValidationError('Situation hooks exceed their executable reservation')
    return code, ((category_hook, CODE_START), (formation_hook, second_start))


def verify_code(profile, code):
    from capstone import Cs, CS_ARCH_PPC, CS_MODE_64, CS_MODE_BIG_ENDIAN
    canonical, hooks = assemble(profile)
    if code != canonical:
        raise ValidationError('Situation code differs from the reviewed generator')
    instructions = list(Cs(CS_ARCH_PPC, CS_MODE_64 | CS_MODE_BIG_ENDIAN).disasm(code, CODE_START))
    if len(instructions)*4 != len(code):
        raise ValidationError('Situation code contains an undecodable instruction')
    leaves = ((hooks[0][1], hooks[1][1], hooks[0][0]), (hooks[1][1], CODE_START+len(code), hooks[1][0]))
    branches = 0
    for insn in instructions:
        word = int.from_bytes(insn.bytes, 'big'); op = word >> 26
        if op in (16, 18):
            if word & 3: raise ValidationError('Situation leaf must use relative non-linking branches')
            width = 26 if op == 18 else 16
            delta = word & ((1 << width)-4)
            if delta & (1 << (width-1)): delta -= 1 << width
            target = insn.address + delta
            lo, hi, hook = next(span for span in leaves if span[0] <= insn.address < span[1])
            if not (lo <= target < hi) and not (insn.address == hi-4 and target == hook+4):
                raise ValidationError('Situation branch leaves its owned leaf')
            branches += 1
        if insn.mnemonic in ('bctr', 'bctrl', 'blr', 'blrl', 'mtctr', 'mtlr'):
            raise ValidationError('Situation leaf changes indirect control flow')
    return {'instructions': len(instructions), 'branches': branches, 'sha256': hashlib.sha256(code).hexdigest()}


@dataclass(frozen=True)
class SituationPatch:
    profile: object
    data: bytes

    @property
    def words(self):
        decode_data(self.data)
        code, hooks = assemble(self.profile)
        verify_code(self.profile, code)
        writes = [(site, _branch(site, target)) for site, target in hooks]
        for start, payload in ((CODE_START, code), (DATA_START, self.data),
                               (RECEIPT_START, bytes(RECEIPT_LIMIT-RECEIPT_START))):
            writes.extend((start+i, int.from_bytes(payload[i:i+4], 'big')) for i in range(0, len(payload), 4))
        return tuple(writes)

    @property
    def receipt(self):
        code, hooks = assemble(self.profile)
        return {'schema': SCHEMA, 'classification': CLASSIFICATION, 'runtime_status': 'UNWITNESSED',
                'profile': self.profile.name, 'image_sha256': self.profile.sha256,
                'key': 'actual down 1..4 x absolute f32 longitudinal distance <=182.88 / <=640.08 / >640.08',
                'policies': decode_data(self.data), 'data_sha256': hashlib.sha256(self.data).hexdigest(),
                'hooks': hooks, 'code': verify_code(self.profile, code),
                'fallback': 'An empty filtered draw uses the original complete draw; last-draw receipts at 0x852D6500 and 0x852D6518',
                'limits': 'Ordinary automatic offense calls in scrimmage phase 4 only; cached specials, explicit play/formation paths and kick/try phases bypass the filter.'}

    def as_toml(self):
        lines = ['title_name = "All-Pro Football 2K8"', 'title_id = "54540807"',
                 f'hash = "{self.profile.module_hash}"', '', '[[patch]]',
                 '    name = "Per-book situation exclusions (unwitnessed)"',
                 '    desc = "Twelve live down/distance buckets; empty-draw fallback; EXPERIMENTAL."',
                 '    author = "2K Football Mod Tools"', '    is_enabled = true']
        for address, value in self.words:
            lines += ['', '    [[patch.be32]]', f'        address = 0x{address:08X}', f'        value = 0x{value:08X}']
        return '\n'.join(lines)+'\n'


def compile_patch(image, policies):
    profile = check_image(image)
    patch = SituationPatch(profile, encode_data(policies))
    for address, word in zip(HOOKS[profile.name], (0x38A00003, 0x38A00001)):
        if image[address-IMAGE_BASE:address-IMAGE_BASE+4] != struct.pack('>I', word):
            raise ValidationError('The situation hook instruction changed')
    for start, end in ((DATA_START, DATA_LIMIT), (CODE_START, CODE_LIMIT), (RECEIPT_START, RECEIPT_LIMIT)):
        if any(image[start-IMAGE_BASE:end-IMAGE_BASE]):
            raise ValidationError('The situation patch reservation is not zero-filled')
    patch.words
    return patch


def canonical_payload(payload):
    try:
        parsed = tomllib.loads(payload.decode('utf-8'))
        profile = next(p for p in PROFILES if p.module_hash == parsed['hash'])
        row, = parsed['patch']
        writes = row['be32']; mapped = {w['address']: w['value'] for w in writes}
        if len(mapped) != len(writes): raise ValueError('Duplicate writes')
        data = b''.join(struct.pack('>I', mapped[at]) for at in range(DATA_START, DATA_LIMIT, 4))
        expected = tomllib.loads(SituationPatch(profile, data).as_toml())
        enabled = row['is_enabled']
        if type(enabled) is not bool: raise ValueError('Enabled must be boolean')
        expected['patch'][0]['is_enabled'] = enabled
        if parsed != expected: raise ValueError('Unexpected patch content')
        return profile, enabled
    except (KeyError, ValueError, TypeError, StopIteration, struct.error, UnicodeError) as exc:
        raise ValidationError(f'Choose a canonical Studio situation mask patch: {exc}') from exc


def filter_categories(book, master, candidates, excluded):
    """Cold-preview equivalent of the conservative native category filter."""
    from .apf2k8_playcall_model import _records
    excluded = set(excluded)
    records = _records(book)
    result = []
    for category, weight in candidates:
        primary = any(r.category_index == category for r in records)
        members = [r for r in records if (not primary or r.category_index == category)
                   and int.from_bytes(r.trailer[4:], 'big') & (1 << category)
                   and not struct.unpack_from('>I', master, 0x24C + r.formation_index*184)[0] & 1]
        if any(r.formation_index not in excluded for r in members):
            result.append((category, weight))
    return (tuple(result) or candidates), bool(candidates and not result)


def filter_formations(candidates, excluded):
    result = tuple(pair for pair in candidates if pair[0] not in excluded)
    return (result or candidates), bool(candidates and not result)


def audit_reservations(image):
    """Pinned image, PE/XEX-mapped section padding and direct-reference audit.

    This checks aligned absolute pointers and relative branches. It does not
    claim to disprove arbitrary computed addresses. The reservations lie past
    the declared virtual data/string contents, and past executable contents.
    """
    profile = check_image(image)
    pe = struct.unpack_from('<I', image, 0x3C)[0]
    count = struct.unpack_from('<H', image, pe+6)[0]
    optional_size = struct.unpack_from('<H', image, pe+20)[0]
    sections = {}
    for i in range(count):
        at = pe+24+optional_size+40*i
        name = image[at:at+8].rstrip(b'\0').decode('ascii')
        virtual_size, rva, raw_size = struct.unpack_from('<3I', image, at+8)
        sections[name] = (IMAGE_BASE+rva, virtual_size, raw_size, struct.unpack_from('<I', image, at+36)[0])
    ranges = ((DATA_START, DATA_LIMIT, '.string_'), (CODE_START, CODE_LIMIT, '.text'),
              (RECEIPT_START, RECEIPT_LIMIT, '.data'))
    for lo, hi, name in ranges:
        start, virtual_size, raw_size, flags = sections[name]
        end = start+max(virtual_size,raw_size)
        if not end <= lo < hi <= (end+65535)&~65535:
            raise ValidationError('Situation reservation is not in the pinned section’s final mapped page padding')
        if any(image[lo-IMAGE_BASE:hi-IMAGE_BASE]):
            raise ValidationError('Situation reservation contains retail bytes')
        if name == '.data' and not flags&0x80000000:
            raise ValidationError('Draw receipt padding is not writable')
        if name == '.text' and not flags&0x20000000:
            raise ValidationError('Situation code padding is not executable')
    # An arbitrary word in .rdata includes compressed assets and floats. Only
    # PE relocation entries identify absolute pointer fields. Keep the raw
    # collisions in the receipt instead of calling asset words pointers.
    relocation_sites = set()
    types = set()
    reloc_start, reloc_size, _, _ = sections['.reloc']
    at, end = reloc_start-IMAGE_BASE, reloc_start-IMAGE_BASE+reloc_size
    while at < end:
        page, size = struct.unpack_from('<II', image, at)
        if size < 8 or size % 2 or at+size > end:
            raise ValidationError('The pinned PE relocation block is malformed')
        for cursor in range(at+8,at+size,2):
            value = struct.unpack_from('<H',image,cursor)[0]
            kind, offset = value >> 12, value & 0xFFF
            types.add(kind)
            if kind == 3: relocation_sites.add(IMAGE_BASE+page+offset)
            elif kind != 0: raise ValidationError(f'Unreviewed PE relocation type {kind}')
        at += size
    direct, collisions = [], []
    text_start,text_size,_,_=sections['.text']
    words = memoryview(image)
    for offset,(word,) in enumerate(struct.iter_unpack('>I',words)):
        pc=IMAGE_BASE+offset*4
        if any(lo<=word<hi for lo,hi,_ in ranges):
            if pc in relocation_sites:direct.append((pc,word,'relocated pointer'))
            else:collisions.append((pc,word))
        if text_start<=pc<text_start+text_size:
            if word>>26 in (16,18) and not word&2:
                width=26 if word>>26==18 else 16
                delta=word&((1<<width)-4)
                if delta&(1<<(width-1)):delta-=1<<width
                target=pc+delta
                if any(lo<=target<hi for lo,hi,_ in ranges):direct.append((pc,target,'branch'))
            if word>>26==15 and (word>>16)&31==0:
                register=(word>>21)&31
                high=(word&0xFFFF)<<16
                for step in range(1,9):
                    if pc+step*4>=text_start+text_size:break
                    following=struct.unpack_from('>I',image,offset*4+step*4)[0]
                    op,ra,rt=following>>26,(following>>16)&31,(following>>21)&31
                    imm=following&0xFFFF
                    if imm&0x8000:imm-=0x10000
                    if ra==register and op in (14,32,34,36,38,40,42,44,48,50,52,54):
                        target=(high+imm)&0xFFFFFFFF
                        if any(lo<=target<hi for lo,hi,_ in ranges):direct.append((pc,target,'lis/displacement'))
                    if op in (14,15,32,34,40,42) and rt==register:break
    if direct:raise ValidationError(f'Retail references reach situation storage: {direct[:8]}')
    return {'profile':profile.name,'sections':sections,'ranges':ranges,
            'relocated_absolute_references':0,'direct_branch_references':0,
            'lis_displacement_references':0,'relocation_sites_checked':len(relocation_sites),
            'relocation_types':sorted(types),'untyped_word_collisions':collisions,
            'computed_address_limit':'No claim about arbitrary computed addresses; owned ranges are mapped section padding beyond declared content.'}

"""Bounded beta-64 college inspection and candidate repair, with no file or GUI writes.

Input is a main disc ROST body/resource or a verified container's SAVEGAME.DAT
(roster or franchise). Both player pools use signed field-relative pointers to
eight-byte college records. Historical/exported single-team resources use a
different, index-based ABI and are deliberately refused when no local table exists.

Scanning does not require a successful full roster decode: that is precisely
what a broken college can prevent. Framing/table boundaries are checked first;
unrelated data is never followed to locate a player. Repair changes only player
+0x00 words on a copy, then requires the unchanged strict codec to accept it.
Callers still run their normal ownership/depth checks and signed-copy writer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import struct

from . import nfl2k5_roster_arena as arena
from . import nfl2k5_save_rost as codec


class CollegeCheckError(ValueError):
    """The layout or proposed repair cannot be established without guessing."""


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise CollegeCheckError(message)


def _u32(data: bytes, field: int) -> int:
    return struct.unpack_from('<I', data, field)[0]


def _rel(data: bytes, field: int) -> int | None:
    raw = struct.unpack_from('<i', data, field)[0]
    return None if raw == 0 else field + raw - 1


@dataclass(frozen=True)
class College:
    index: int
    offset: int
    raw: int
    name_offset: int | None
    name: str
    stored_id: int  # Metadata, NOT the array ordinal (retail IDs are noncontiguous).
    issue: str = ''


@dataclass(frozen=True)
class Finding:
    source: str
    pool: str
    index: int
    offset: int  # Absolute in the supplied bytes, also the college pointer field.
    player: str
    raw: int
    target: int | None
    college_index: int | None
    reason: str
    game_display: str  # Static inference, never an assertion of witnessed game output.


@dataclass(frozen=True)
class Scan:
    source: str
    sha256: str
    layout: codec.Layout
    player_count: int
    colleges: tuple[College, ...]
    findings: tuple[Finding, ...]
    table_issues: tuple[College, ...]


def _data_end(layout: codec.Layout) -> int:
    return layout.root + arena.BLOCK_OFFSET if layout.version in (1, 18) else layout.end


def _span(layout: codec.Layout, offset: int, size: int, label: str) -> None:
    _require(size >= 0 and layout.root + 0x70 <= offset
             and offset + size <= _data_end(layout), f'{label}: range outside ROST arena data')


def _tables(data: bytes, layout: codec.Layout) -> dict[str, codec.Table]:
    """Use the codec's table ABI without its player/string validation prerequisite."""
    try:
        arena.read(data, layout.root, layout.end, layout.version)
    except arena.ArenaError as exc:
        raise CollegeCheckError(str(exc)) from exc
    tables = {}
    occupied = []
    for name, count_field, pointer_field, stride, maximum in codec.TABLES:
        count = _u32(data, layout.root + count_field)
        _require(count <= maximum, f'{name}: implausible count {count}')
        target = _rel(data, layout.root + pointer_field)
        _require(count == 0 or target is not None, f'{name}: null table with nonzero count')
        if target is not None:
            _span(layout, target, count * stride, name)
        if count:
            occupied.append((target, target + count * stride, name))
        tables[name] = codec.Table(name, count, target, stride)
    _require(tables['primary'].count > 0 and tables['teams'].count > 0,
             'primary players and teams are required')
    occupied.sort()
    for left, right in zip(occupied, occupied[1:]):
        _require(left[1] <= right[0], f'overlapping {left[2]}/{right[2]} tables')
    _require(tables['colleges'].count > 0,
             'no local college table: missing table or unsupported single-team college indices')
    return tables


def _frame(data: bytes) -> tuple[codec.Layout, dict[str, codec.Table]]:
    """Same framing contract as decode(); college failures must not hide a frame."""
    _require(len(data) <= 32 * 1024 * 1024, 'payload exceeds 32 MiB codec limit')
    candidates, failures = [], []
    point = data.find(b'ROST', 0, min(len(data), 0x10000))
    while point >= 0:
        if point >= 12 and data[point + 0x2C:point + 0x30] != b'ROST':
            base = point - 12
            try:
                _require(base <= len(data) - 0x20, 'truncated ROST preamble')
                version = _u32(data, base + 16)
                _require(version in (0, 1, 17, 18), f'unsupported ROST version {version}')
                delta = 0x20 if version in (0, 1) else 0x40
                root = _rel(data, base + 0x14)
                _require(root == base + delta, f'version {version}: unexpected root offset')
                wrapper = base - 0x20 if base >= 0x20 and data[base - 0x20:base - 0x1C] == b'ROST' else None
                if wrapper is not None:
                    declared = _u32(data, wrapper + 4)
                    _require(delta + 0x70 <= declared <= 16 * 1024 * 1024, 'implausible resource length')
                    end = base + declared
                    _require(end <= len(data), 'truncated declared ROST resource')
                else:
                    expected = {0: 0x91020, 1: 0x92020, 17: 0x90F60, 18: 0x92040}[version]
                    _require(base == 0 and len(data) == expected, 'unframed ROST has unknown boundaries')
                    end = len(data)
                layout = codec.Layout(version, wrapper, base, root, end)
                candidates.append((layout, _tables(data, layout)))
            except CollegeCheckError as exc:
                failures.append(str(exc))
        point = data.find(b'ROST', point + 1, min(len(data), 0x10000))
    _require(len(candidates) == 1, 'ambiguous ROST resources' if len(candidates) > 1
             else 'no supported ROST: ' + ('; '.join(failures[:3]) or 'inner header not found'))
    return candidates[0]


def _string(data: bytes, layout: codec.Layout, field: int) -> str:
    target = _rel(data, field)
    if target is None:
        return ''
    _span(layout, target, 2, 'UTF-16 pointer')
    _require(target % 2 == 0, 'unaligned UTF-16 string')
    for end in range(target, min(_data_end(layout), target + 8192) - 1, 2):
        if data[end:end + 2] == b'\0\0':
            try:
                return data[target:end].decode('utf-16-le')
            except UnicodeDecodeError as exc:
                raise CollegeCheckError('invalid UTF-16 string') from exc
    raise CollegeCheckError('unterminated UTF-16 string')


def scan(payload: bytes | bytearray, *, source: str = '') -> Scan:
    """List invalid/missing player references and malformed college name records.

    Null player references are reported as missing (63.1 accepts them); valid
    pointers to a blank/None college are clean. A null college name pointer also
    represents blank in the existing codecs. No string contents are guessed from
    an off-table player target. A readable interior college-name string cannot be
    distinguished from intentional suffix sharing without an external source.
    """
    data = bytes(payload)
    layout, tables = _frame(data)
    colleges = []
    table = tables['colleges']
    for index in range(table.count):
        field = table.offset + index * table.stride
        name, issue = '', ''
        try:
            name = _string(data, layout, field)
        except CollegeCheckError as exc:
            issue = str(exc)
        colleges.append(College(index, field, _u32(data, field), _rel(data, field),
                                name, _u32(data, field + 4), issue))
    by_offset = {c.offset: c for c in colleges}
    findings = []
    for pool in ('primary', 'secondary'):
        table = tables[pool]
        for index in range(table.count):
            field = table.offset + index * table.stride
            target = _rel(data, field)
            college = by_offset.get(target)
            if college is not None and not college.issue:
                continue
            if target is None:
                reason = 'null_reference'
                display = 'Static player-card path: COLLEGE label with no value (null is checked at 0x145D90).'
            elif college is not None:
                reason = 'invalid_college_name'
                display = 'Unknown: college name cannot be read as bounded UTF-16.'
            elif not (layout.root + 0x70 <= target and target + 8 <= _data_end(layout)):
                reason = 'outside_arena'
                display = 'Unknown: college record lies outside the serialized arena.'
            else:
                reason = 'off_table'
                exported = (target - colleges[0].offset) // 8
                if not 0 <= exported < len(colleges):
                    exported = -1
                display = ('Unknown: player card follows a non-college record. '
                           f'Static native team export would use college index {exported}.')
            names = []
            for name_field in (field + 0x10, field + 0x14):
                try:
                    names.append(_string(data, layout, name_field))
                except CollegeCheckError:
                    names.append('[unreadable]')
            findings.append(Finding(source, pool, index, field, ' '.join(names).strip() or f'#{index}',
                                    _u32(data, field), target, college.index if college else None,
                                    reason, display))
    return Scan(source, hashlib.sha256(data).hexdigest(), layout,
                tables['primary'].count + tables['secondary'].count, tuple(colleges), tuple(findings),
                tuple(c for c in colleges if c.issue))


def repair(payload: bytes | bytearray, *, source: str = '', college_index: int | None = None,
           expected_sha256: str | None = None) -> tuple[bytes, dict]:
    """Repair all findings to one verified local college record, atomically in memory.

    Default: first case-insensitive None entry, else first blank entry, else entry
    zero. An explicit ordinal is allowed; address proximity is not evidence of
    the intended college. Broken table strings require separate research and are
    refused, even if unreferenced. Nothing signs, writes, or weakens a validator.
    """
    data = bytes(payload)
    digest = hashlib.sha256(data).hexdigest()
    _require(expected_sha256 is None or expected_sha256 == digest, 'stale college scan: payload changed')
    report = scan(data, source=source)
    _require(not report.table_issues, 'college table has unreadable names; player-only repair refused')
    if college_index is None:
        college_index = next((c.index for c in report.colleges if c.name.strip().casefold() == 'none'),
                             next((c.index for c in report.colleges if not c.name.strip()), 0))
    _require(type(college_index) is int and 0 <= college_index < len(report.colleges),
             'college index is outside this roster table')
    college = report.colleges[college_index]
    out = bytearray(data)
    repairs = []
    for finding in report.findings:
        raw = college.offset - finding.offset + 1
        _require(-(1 << 31) <= raw < (1 << 31) and raw != 0, 'college relative pointer is not encodable')
        struct.pack_into('<i', out, finding.offset, raw)
        repairs.append({**asdict(finding), 'new_raw': raw & 0xFFFFFFFF,
                        'new_target': college.offset, 'new_college_index': college.index,
                        'new_college': college.name})
    fixed = bytes(out)
    if repairs:
        from . import nfl2k5_my_career_save as career
        try:
            codec.decode(fixed, preamble=report.layout.preamble)
            # The inline footer repeats MyPlayer's college identity. It must
            # remain valid without changing any footer/checksum byte.
            if len(fixed) in career.SIZES and report.layout.preamble == 0x300:
                career.read(fixed)
        except (codec.SaveRostError, career.CareerSaveError) as exc:
            raise CollegeCheckError(f'candidate fails unchanged roster/identity validation: {exc}') from exc
        _require(not scan(fixed).findings, 'college repair read-back differs')
    return fixed, {'source': source, 'before_sha256': digest,
                   'after_sha256': hashlib.sha256(fixed).hexdigest(), 'changed': len(repairs),
                   'college_index': college.index, 'college': college.name,
                   'repairs': repairs, 'saved': False}

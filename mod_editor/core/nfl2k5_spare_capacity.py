"""Restore real import/create-player vacancies inside the existing main ROST.

The dated 377-FA roster uses 140 of the original 155 vacant records. This
copy-only writer inserts 140 blank primary records and reclaims the same number
of bytes from a proved unused player-name gap. Existing records, history,
ordinals, memberships, selected text, arena size and schema remain unchanged.
No executable allocation, reserve policy or whole-save format changes.
"""
from __future__ import annotations
import hashlib
import struct

OWNER = 'nfl2k5_spare_capacity'
BODY_SIZE = 0x90F60
PRIMARY_BEFORE = 2479
EXTRA_RECORDS = 140
PRIMARY_AFTER = PRIMARY_BEFORE + EXTRA_RECORDS
SECONDARY_COUNT = 68
INSERT_BYTES = EXTRA_RECORDS * 84
ARRAY_BEFORE = 0x72FB4
ARRAY_AFTER = ARRAY_BEFORE + INSERT_BYTES
RESOURCE_BEFORE_SHA256 = 'd09fc9cb9399b6c1d712847e179b2f50d6069ba16fee7c406508113a01187320'
RESOURCE_AFTER_SHA256 = 'b3dd88e2b51824b368e78f99f17d7aea7d64b26316c60fee5c0767f31261f501'
# Bare-body table offsets, read by native C0500/C0730. Only the insertion's
# later tables move; no other table count or schema is admitted by this owner.
NATIVE_TABLES = {
    'primary': (2479, 0xAFA8), 'secondary': (68, 0x3DD14),
    'stadiums': (82, 0xB0), 'teams': (52, 0x41C8),
    'colleges': (266, 0xA758), 'coaches': (35, 0x2AD0),
    'free_agents': (377, 0x3F364), 'team_labels': (36, 0x29B0),
    'generated_names': (485, ARRAY_BEFORE), 'historic_descriptors': (75, 0x73EDC),
}
PLAYER_NAME_START = 0x7B970
PLAYER_NAME_END = 0x8B7D0


class SpareCapacityError(ValueError):
    """The main roster cannot gain vacancies without changing owned identities."""

def require(ok, message):
    if not ok: raise SpareCapacityError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _wrapped(body):
    require(len(body) == BODY_SIZE, 'spare capacity requires the fixed native main ROST size')
    return b'ROST' + struct.pack('<7I', len(body), len(body), 0, 0, 0, 0, 0) + bytes(body)

def _decode(body):
    from . import nfl2k5_save_rost as saved
    document = saved.decode(_wrapped(body), reference_year=2026)
    require(document.layout.version == 17 and document.layout.root == 0x60,
            'spare capacity requires the native version-17 main ROST')
    require(document.tables['secondary'].count == SECONDARY_COUNT,
            'spare capacity requires the audited 68 secondary records')
    return document

def _table_layout(document, *, extended):
    point = NATIVE_TABLES['secondary'][1]
    for name, (count, offset) in NATIVE_TABLES.items():
        table = document.tables[name]
        expected_count = PRIMARY_AFTER if extended and name == 'primary' else count
        expected_offset = offset + (INSERT_BYTES if extended and offset >= point else 0)
        require(table.count == expected_count and table.offset == expected_offset + 32,
                'foreign native ' + name + ' table count/offset')
    return document


def extended_layout(body):
    """Seal the declared native table relocation; allow subsequent typed edits."""
    return _table_layout(_decode(body), extended=True)


def _initial_extension(body):
    """Stricter replay guard: all added vacancies have private native-width names."""
    from . import nfl2k5_roster_records as rr
    document = extended_layout(body)
    roster = rr.load_body(body, scheme='one_pool', reference_year=2026)
    extra = roster.by_pool('primary')[PRIMARY_BEFORE:PRIMARY_AFTER]
    require(len(extra) == EXTRA_RECORDS, 'extra spare record count differs')
    old_targets = set()
    new_targets = []
    for player in roster.players:
        for offset in (0x10, 0x14):
            target = roster.rel(player.offset + offset)
            if player.pool == 'primary' and player.index >= PRIMARY_BEFORE:
                require(target is not None and PLAYER_NAME_START + INSERT_BYTES <= target
                        and target + 34 <= PLAYER_NAME_END and target % 2 == 0,
                        'new spare name buffer lies outside the fixed player-name pool')
                require(bytes(body[target:target + 34]) == '****************'.encode('utf-16le') + b'\0\0',
                        'new spare name buffer is not native-width blank storage')
                new_targets.append(target)
            elif target is not None:
                old_targets.add(target)
    require(len(set(new_targets)) == 2 * EXTRA_RECORDS and not (set(new_targets) & old_targets),
            'new spare name buffers alias each other or an existing player')
    old_name_spans = [(target, target + rr.encoded_size(roster.names.text_at(target)))
                      for target in old_targets]
    require(not any(target < end and start < target + 34
            for target in new_targets for start, end in old_name_spans),
            'new spare name buffer overlaps an existing selected-name allocation')
    ordered = sorted(new_targets)
    require(all(left + 34 <= right for left, right in zip(ordered, ordered[1:])),
            'new spare name buffers overlap')
    require(all(player.record.get('player_type') == 1 and player.group == 'pool'
            and not player.teams and (player.pool, player.index) not in roster.reserve_owner
            and player.first == player.last == '****************' for player in extra),
            'extra spare records are occupied or have a foreign type')
    return document


def status(body):
    try:
        document = _decode(body)
        count = document.tables['primary'].count
        if count == PRIMARY_BEFORE: return 'retail'
        if count == PRIMARY_AFTER:
            _initial_extension(body)
            return 'applied'
        return 'foreign'
    except (ValueError, KeyError, TypeError, IndexError, struct.error, OverflowError):
        return 'foreign'

def apply_body(body):
    """Return an exact-size candidate; refuse before mutating caller bytes."""
    from . import nfl2k5_roster_arena as arena, nfl2k5_roster_records as rr
    before = bytes(body)
    document = _decode(before)
    primary = document.tables['primary']
    if primary.count == PRIMARY_AFTER:
        _initial_extension(before)
        return before, dict(owner=OWNER, already_applied=True, changed_bytes=0,
                            primary_count=PRIMARY_AFTER, secondary_count=SECONDARY_COUNT,
                            before_sha256=sha(before), after_sha256=sha(before),
                            arena_size_unchanged=True, roster_schema_unchanged=True)
    require(primary.count == PRIMARY_BEFORE and primary.offset is not None,
            'spare capacity requires the audited 2479 primary records')
    source = rr.load_body(before, scheme='one_pool', reference_year=2026)
    require(len(source.free_agents) == 377, 'apply dated free agents before restoring import capacity')
    require([p.index for p in source.group_players('draft_class')] == list(range(1944, 2324)),
            'spare capacity would alter the native 380-player draft window')
    unused = [p for p in source.by_pool('primary') if p.record.get('player_type') & 1]
    require(len(unused) == 15 and all(p.group == 'pool' and p.index >= 2464
            and p.first == p.last == '****************' for p in unused),
            'the dated source does not have its 15 vacant trailing records')
    _table_layout(document, extended=False)
    original = _wrapped(before)
    point = primary.offset + primary.count * 84
    require(all(t.offset is None or t.name == 'primary' or t.offset >= point
            or t.offset + t.count * t.stride <= primary.offset for t in document.tables.values()),
            'primary insertion crosses another table')
    gaps = [(size, offset + 32) for offset, size in source.names.free.items() if size >= INSERT_BYTES]
    require(gaps, 'unused player-name space cannot hold 140 real spare records')
    gap_capacity, gap = max(gaps)
    require(source.names.start + 32 <= gap and gap + INSERT_BYTES <= source.names.end + 32
            and point < gap, 'reclaimed player-name gap is outside its declared pool')
    fields = arena.pointer_fields(document)
    targets = {field: document.rel(field, label='spare capacity relocation') for field in fields}
    require(not any(gap <= field < gap + INSERT_BYTES for field in fields),
            'a relocation field occupies the proposed unused name gap')
    require(not any(target is not None and gap <= target < gap + INSERT_BYTES for target in targets.values()),
            'a live native pointer selects the proposed unused name gap')
    require(not any(gap < block.offset + 32 + block.capacity and block.offset + 32 < gap + INSERT_BYTES
            for block in source.names.blocks.values()), 'selected player text occupies the reclaimed gap')
    def moved(value):
        require(not gap <= value < gap + INSERT_BYTES, 'a live object occupies the reclaimed gap')
        return value + (INSERT_BYTES if point <= value < gap else 0)
    template = next(p for p in reversed(document.players) if p.pool == 'primary'
                    and p.index == unused[-1].index)
    out = bytearray(original[:point]) + bytearray(INSERT_BYTES) + bytearray(original[point:gap]) + bytearray(original[gap + INSERT_BYTES:])
    for field, target in targets.items():
        at = moved(field)
        struct.pack_into('<i', out, at, 0 if target is None else moved(target) - at + 1)
    struct.pack_into('<I', out, document.layout.root, PRIMARY_AFTER)
    for index in range(EXTRA_RECORDS):
        at = point + index * 84
        out[at:at + 84] = original[template.offset:template.offset + 84]
        for offset in arena.TABLE_POINTERS['primary']:
            target = targets[template.offset + offset]
            struct.pack_into('<i', out, at + offset, 0 if target is None else moved(target) - at - offset + 1)
    require(len(out) == len(original), 'spare capacity changed native resource geometry')
    # Native Create Player edits may write through these name pointers. Give
    # every new vacancy its own two original-width buffers, never template aliases.
    names = rr.load_body(bytes(out[32:]), scheme='one_pool').names
    free = dict(names.free)
    star = '****************'.encode('utf-16le') + b'\0\0'
    name_changes = []
    new_name_offsets = []
    for index in range(EXTRA_RECORDS):
        at = point + index * 84
        for field in (0x10, 0x14):
            fits = [(capacity, offset) for offset, capacity in free.items() if capacity >= len(star)]
            require(fits, 'unused player-name space cannot give each spare private name buffers')
            capacity, offset = min(fits)
            del free[offset]
            if capacity > len(star): free[offset + len(star)] = capacity - len(star)
            dest = offset + 32
            name_changes.append((dest, bytes(out[dest:dest + len(star)])))
            new_name_offsets.append(dest)
            out[dest:dest + len(star)] = star
            struct.pack_into('<i', out, at + field, dest - at - field + 1)
    require(len(set(new_name_offsets)) == 2 * EXTRA_RECORDS,
            'new spare-player name buffers alias')
    candidate = bytes(out)
    readback = _decode(candidate[32:])
    _initial_extension(candidate[32:])
    require(readback.layout == document.layout, 'spare capacity changed native schema/arena geometry')
    for name, table in document.tables.items():
        require(readback.tables[name].count == (PRIMARY_AFTER if name == 'primary' else table.count)
                and readback.tables[name].stride == table.stride, 'an unrelated native table changed')
    for field, target in targets.items():
        require(readback.rel(moved(field), label='relocation readback') == (None if target is None else moved(target)),
                'native relative pointer readback differs')
    inverse_input = bytearray(candidate)
    for dest, prior in name_changes: inverse_input[dest:dest + len(prior)] = prior
    inverse = bytearray(inverse_input[:point]) + bytearray(inverse_input[point + INSERT_BYTES:gap + INSERT_BYTES]) + bytearray(original[gap:gap + INSERT_BYTES]) + bytearray(inverse_input[gap + INSERT_BYTES:])
    for field in fields: inverse[field:field + 4] = original[field:field + 4]
    inverse[document.layout.root:document.layout.root + 4] = original[document.layout.root:document.layout.root + 4]
    require(bytes(inverse) == original, 'bytes outside the explicit insertion/reclaimed gap/pointers changed')
    old_by = {p.key: p for p in document.players}
    new_by = {p.key: p for p in readback.players}
    for key, player in old_by.items():
        other = new_by[key]
        require((player.first, player.last) == (other.first, other.last), 'an existing player name changed')
        a = bytearray(original[player.offset:player.offset + 84])
        b = bytearray(candidate[other.offset:other.offset + 84])
        for offset in arena.TABLE_POINTERS[player.pool]: a[offset:offset + 4] = b[offset:offset + 4] = bytes(4)
        require(a == b and document.history_words[key] == readback.history_words[key],
                'an existing record or its history changed')
    for old, new in zip(document.teams, readback.teams):
        require((old.index, old.asset_id, old.abbreviation, tuple(moved(p) for p in old.player_offsets))
                == (new.index, new.asset_id, new.abbreviation, new.player_offsets), 'a team or membership changed')
    output = candidate[32:]
    final = rr.load_body(output, scheme='one_pool', reference_year=2026)
    require([(source.by_offset[p].pool, source.by_offset[p].index) for p in source.free_agents]
            == [(final.by_offset[p].pool, final.by_offset[p].index) for p in final.free_agents],
            'free-agent identities or order changed')
    require(final.to_body(normalise_commentary=False) == output, 'new roster codec roundtrip differs')
    require(len([p for p in final.by_pool('primary') if p.record.get('player_type') & 1]) == 155,
            'native import/create-player vacancies were not restored')
    return output, dict(owner=OWNER, already_applied=False, changed_bytes=sum(a != b for a, b in zip(before, output)),
        before_sha256=sha(before), after_sha256=sha(output), primary_count=PRIMARY_AFTER,
        secondary_count=SECONDARY_COUNT, added_real_spare_records=EXTRA_RECORDS, spare_records=155,
        insert_body_offset=point - 32, insertion_bytes=INSERT_BYTES, reclaimed_name_body_offset=gap - 32,
        reclaimed_name_bytes=INSERT_BYTES, reclaimed_gap_capacity=gap_capacity,
        reclaimed_gap_before_sha256=sha(original[gap:gap + INSERT_BYTES]),
        reclaimed_gap_nonzero_bytes=sum(bool(v) for v in original[gap:gap + INSERT_BYTES]),
        native_relative_pointer_fields=len(fields), all_original_record_nonpointer_bytes_names_history_equal=True,
        all_team_and_fa_memberships_ordinals_and_order_equal=True, draft380_ordinals_and_records_preserved=True,
        all_bytes_outside_explicit_reclaimed_and_new_name_scopes_recover_exactly_by_inverse=True,
        new_blank_name_bytes=2 * EXTRA_RECORDS * len(star),
        new_blank_name_body_spans=[[dest - 32, dest - 32 + len(star)] for dest in new_name_offsets],
        each_new_blank_has_distinct_first_and_last_name_storage=True,
        no_live_pointer_or_selected_text_in_reclaimed_gap=True, arena_size_unchanged=True,
        roster_schema_unchanged=True, native_xbe_changes=False, remaining_free_name_bytes=final.names.free_bytes)

def repair_resource(resource, *, approved_input_sha256=()):
    """Hash-gated native owner; the complete fixed main ROST is its scope."""
    digest = sha(resource)
    require(digest in {RESOURCE_BEFORE_SHA256, RESOURCE_AFTER_SHA256, *approved_input_sha256},
            'unexpected main ROST SHA-256; input left untouched')
    require(len(resource) == BODY_SIZE + 32 and resource[:4] == b'ROST'
            and struct.unpack_from('<II', resource, 4) == (BODY_SIZE, BODY_SIZE),
            'native main ROST resource framing differs')
    body, receipt = apply_body(resource[32:])
    after = resource[:32] + body
    require(after[:32] == resource[:32] and len(after) == len(resource), 'native wrapper or size changed')
    receipt.update(before_resource_sha256=digest, after_resource_sha256=sha(after),
                   approved_composed_input=digest not in (RESOURCE_BEFORE_SHA256, RESOURCE_AFTER_SHA256),
                   declared_resource_scope=[0, len(resource)], outside_resource_identical_required=True)
    return after, receipt

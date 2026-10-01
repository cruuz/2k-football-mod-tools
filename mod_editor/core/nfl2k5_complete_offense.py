"""DESIGN: pinned complete-offense recipes using the existing authoring compiler.

PROVED OFFLINE: repack only referenced strings and byte-identical assignment
chains. Indices never move. Retained plays keep flags, descriptors and nodes.
Each new record first passes the existing writer against the original source,
so replacing a donor cannot affect another request. No executable is patched.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from . import nfl2k5_playbook_inspector as insp
from . import nfl2k5_formation_play_writer as writer

REPORT_SCHEMA = 'nfl2k5_complete_offense/v1'


def require(value, message):
    if not value:
        from .nfl2k5_playbook_pack import PlaybookPackError
        raise PlaybookPackError(message)


def validate_structure(pack):
    """PROVED OFFLINE: reject ambiguous menus and partial/conditional recipes."""
    from .nfl2k5_playbook_pack import TEAM_BOOKS
    require(pack.book.resolved_targets() == (pack.book.team,), 'Complete offense has exactly one team target')
    require(pack.book.team in TEAM_BOOKS, 'Complete offense needs a club book')
    fs, ps = pack.formations_by_id, {p.id: p for p in pack.plays}
    require(len(fs) == len(pack.formations) and len(ps) == len(pack.plays), 'Duplicate entry ID')
    require(len(set(fs) & set(ps)) == 0, 'Formation/play IDs overlap')
    require(len(dict(pack.menus)) == len(pack.menus) and set(dict(pack.menus)) == set(fs),
            'Complete offense needs exactly one menu per authored formation')
    for entries in (pack.formations, pack.plays):
        require(all(e.replace_index is not None for e in entries), 'Complete offense replaces existing indices only')
        require(len({e.replace_index for e in entries}) == len(entries), 'Duplicate replacement index')
        for entry in entries:
            require(writer._clean_custom_name(entry.custom_name) == entry.custom_name, 'Invalid custom name')
    used = set()
    for fid, menu in pack.menus:
        require(3 <= len(menu) <= insp.FORMATION_PLAY_LINKS, f'{fid}: menu needs 3..36 plays')
        require(len(menu) == len(set(menu)), f'{fid}: duplicate play in menu')
        require(set(menu) <= set(ps), f'{fid}: unknown play ID')
        used.update(menu)
    require(used == set(ps), 'Every authored play must appear in a menu')
    for p in pack.plays:
        require(p.link_formation is None and p.link_group is None, 'v4 uses complete menus, not appended links')
        require(p.play_type in ('run', 'pass', 'pa_pass'), 'Complete offense supports fixed run/pass/PA only')
        require(not p.option_intent and not p.spy_slots, 'No option/spy intent in complete offense')
        require(len(p.assignments) == 11 and all(p.assignments), 'Complete offense authors all eleven assignments')
        require(all(1 <= len(c) <= 15 and all(len(n) == 2 and n[0] != 0x1A for n in c)
                    for c in p.assignments), 'No conditional branches or invalid chains in complete offense')
        require(p.play_flags is not None and p.donor.flags is not None, 'Record donor and authored flags')
        require((p.play_flags & 0x1FF) == (p.donor.flags & 0x1FF), 'Donor family/type flags changed')
        require(lib.play_class_label(p.play_flags) == ('run' if p.play_type == 'run' else 'pass'),
                'Play class disagrees with declared type')


def ordinary_indices(book, body):
    """PROVED OFFLINE: special-flag offense, defense and special teams stay retail."""
    plays = {p.index for p in book.plays if p.family_id == 0 and not p.flags_or_id & lib.PLAY_FLAG_SPECIAL}
    forms = {f.index for f in book.formations if lib.formation_record(body, f.index).type_code < 4
             and any(l.play_index in plays for l in f.play_links)}
    return forms, plays


def repack(resource, names=None, chains=None):
    """PROVED OFFLINE: bounded pool rebuilding with exact chain interning."""
    book = insp.parse_playbook_resource(resource)
    old = resource[insp.RESOURCE_HEADER_SIZE:]
    body = bytearray(old)
    names = dict(names or {})
    chains = dict(chains or {})
    name_fields = [0x30] + [base + n * size for base, size, count in (
        (insp.FORMATION_BASE, insp.FORMATION_SIZE, len(book.formations)),
        (insp.PLAY_BASE, insp.PLAY_SIZE, len(book.plays)),
        (insp.CATEGORY_BASE, insp.CATEGORY_SIZE, len(book.categories))) for n in range(count)]
    for field in name_fields:
        if field not in names:
            start = field - 1 + struct.unpack_from('<i', old, field)[0]
            end = writer._string_end(old, field)
            names[field] = old[start:end]
    for p in book.plays:
        for slot, (desc, nodes) in enumerate(lib.play_chains(old, p.index)[1]):
            chains.setdefault((p.index, slot), (desc, nodes))
    body[insp.NODE_BASE:writer.POOL_COUNT_WORD] = bytes(writer.POOL_COUNT_WORD - insp.NODE_BASE)
    body[insp.STRING_BASE:] = bytes(insp.BODY_SIZE - insp.STRING_BASE)
    cursor, intern = insp.NODE_BASE, {}
    for (index, slot), (desc, nodes) in sorted(chains.items()):
        raw = b''.join(nodes)
        require(len(nodes) == (desc & 15) and all(len(n) == 8 for n in nodes), 'Invalid descriptor/node extent')
        if raw not in intern:
            require(cursor + len(raw) <= writer.POOL_COUNT_WORD, 'Complete offense node pool exceeds 3500')
            intern[raw] = cursor
            body[cursor:cursor + len(raw)] = raw
            cursor += len(raw)
        field = insp.PLAY_BASE + index * insp.PLAY_SIZE + 12 + slot * 8
        struct.pack_into('<Ii', body, field - 4, desc, intern[raw] - field + 1)
    struct.pack_into('<I', body, 0x40, (cursor - insp.NODE_BASE) // 8)
    cursor, intern = insp.STRING_BASE, {}
    for field in name_fields:
        raw = names[field]
        require(raw.endswith(b'\0\0') and len(raw) % 2 == 0, 'Invalid UTF-16 name')
        if raw not in intern:
            require(cursor + len(raw) <= insp.BODY_SIZE, 'Complete offense name pool overflow')
            intern[raw] = cursor
            body[cursor:cursor + len(raw)] = raw
            cursor += len(raw)
        struct.pack_into('<i', body, field, intern[raw] - field + 1)
    struct.pack_into('<I', body, writer.POOL_COUNT_WORD, (cursor - insp.STRING_BASE) // 2)
    result = resource[:insp.RESOURCE_HEADER_SIZE] + bytes(body)
    insp.parse_playbook_resource(result)
    return result


def compile_offense(resource, pack, *, asset_id):
    """PROVED OFFLINE: compile the whole replacement atomically in memory."""
    from . import nfl2k5_playbook_pack as packs
    validate_structure(pack)
    require(packs.book_fingerprint(resource) == pack.base.book_fingerprint,
            'Complete offense source fingerprint changed; regenerate and review')
    source = insp.parse_playbook_resource(resource, asset_id=asset_id)
    old = resource[32:]
    fs, ps = ordinary_indices(source, old)
    require({f.replace_index for f in pack.formations} == fs, 'Replace every ordinary offensive formation exactly once')
    require({p.replace_index for p in pack.plays} == ps, 'Replace every ordinary offensive play exactly once')
    # DESIGN: shared personnel categories remain intact, including package swaps.
    for f in pack.formations:
        require(f.donor.index in fs, 'Formation donor must be ordinary offense')
        ci = f.category_index
        require(ci is not None and 0 <= ci < len(source.categories), 'Formation needs a stock personnel category')
        require(tuple(lib.category_positions(old, ci)) == f.position_codes and f.category_positions is None,
                'Complete offense preserves stock personnel groups')
        slots = [codec.FormationSlot(0, codec.NO_MIRROR, 1, [x]*3, [z]*3) for x, z in f.slot_positions]
        require(not codec.formation_legality(slots, f.position_codes), f'{f.id}: illegal formation')
    # PROVED OFFLINE: per-record staging cannot exhaust the final pool simply
    # because replaced names/chains still occupied the original source.
    staging = repack(resource)
    result, names, assignments = bytearray(staging), {}, {}
    for f in pack.formations:
        req = f.request_mapping(asset_id)
        # Names are written once into the final compacted pool.
        req.pop('custom_name')
        compiled = writer.compile_formation_play_creations(staging, [req], allow_unchanged=True)
        off = insp.FORMATION_BASE + f.replace_index * insp.FORMATION_SIZE
        # Keep current name pointer valid until final repack.
        result[32 + off + 4:32 + off + insp.FORMATION_SIZE] = compiled.replacement[32 + off + 4:32 + off + insp.FORMATION_SIZE]
        aux = insp.FORMATION_AUX_BASE + f.replace_index * insp.FORMATION_AUX_SIZE
        result[32 + aux + 72:32 + aux + 80] = compiled.replacement[32 + aux + 72:32 + aux + 80]
        names[off] = f.custom_name.encode('utf-16le') + b'\0\0'
    for p in pack.plays:
        require(p.donor.index in ps, 'Play donor must be ordinary offense')
        donor_flags, donor_chains = lib.play_chains(old, p.donor.index)
        require(donor_flags == p.donor.flags and lib.qb_signature(donor_chains[0][1]) == p.donor.signature,
                f'{p.id}: donor metadata differs from source')
        require(lib.qb_signature(p.assignments[0]) == ('run' if p.play_type == 'run' else p.play_type),
                f'{p.id}: QB chain disagrees with play type')
        req = p.request_mapping(asset_id)
        req.pop('custom_name')
        compiled = writer.compile_formation_play_creations(staging, (), [req])
        flags, chains = lib.play_chains(compiled.replacement[32:], p.replace_index)
        off = insp.PLAY_BASE + p.replace_index * insp.PLAY_SIZE
        struct.pack_into('<I', result, 32 + off + 4, flags)
        names[off] = p.custom_name.encode('utf-16le') + b'\0\0'
        assignments.update({(p.replace_index, slot): chain for slot, chain in enumerate(chains)})
    play_ids = {p.id: p.replace_index for p in pack.plays}
    for fid, menu in pack.menus:
        fi = pack.formations_by_id[fid].replace_index
        aux = 32 + insp.FORMATION_AUX_BASE + fi * insp.FORMATION_AUX_SIZE
        words = [0x8000 | (min(slot, 3) << 9) | play_ids[pid] for slot, pid in enumerate(menu)]
        struct.pack_into('<36H', result, aux, *(words + [0x7FF] * (36-len(words))))
    # PROVED OFFLINE: preserve default audible formation indices; remap their
    # link byte to one of the first three valid entries in each new menu.
    for n in range(5):
        off = 32 + 0x4C + n*2
        fi = result[off]
        require(fi in fs, 'Unexpected special offense default audible')
        result[off+1] = min(n, 2)
    rebuilt = repack(bytes(result), names, assignments)
    final = insp.parse_playbook_resource(rebuilt, asset_id=asset_id)
    require(not insp.menu_link_problems(rebuilt), 'Final offense menus do not terminate')
    new = rebuilt[32:]
    require(len(final.formations) == len(source.formations) and len(final.plays) == len(source.plays), 'Counts changed')
    for p in source.plays:
        if p.index not in ps:
            require(lib.play_chains(old, p.index) == lib.play_chains(new, p.index), 'Retained play semantics changed')
            require(final.plays[p.index].name == p.name, 'Retained play renamed')
    for f in source.formations:
        if f.index not in fs:
            off = insp.FORMATION_BASE + f.index * insp.FORMATION_SIZE
            aux = insp.FORMATION_AUX_BASE + f.index * insp.FORMATION_AUX_SIZE
            require(new[off+4:off+insp.FORMATION_SIZE] == old[off+4:off+insp.FORMATION_SIZE]
                    and new[aux:aux+80] == old[aux:aux+80] and final.formations[f.index].name == f.name,
                    'Retained formation changed')
    for ci in range(len(source.categories)):
        off = insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE
        require(new[off+4:off+16] == old[off+4:off+16], 'Personnel changed')
    # PROVED OFFLINE: explicit ownership excludes header references, defensive
    # audibles, substitution rows, category payloads and every unused table slot.
    owned = set()
    def allow(a, b):
        owned.update(range(32+a, 32+b))
    for a,b in ((0x30,0x34),(0x40,0x44),(0x4C,0x56),(insp.NODE_BASE,insp.BODY_SIZE)):
        allow(a,b)
    for base,size,count,changed in ((insp.FORMATION_BASE,insp.FORMATION_SIZE,len(source.formations),fs),
                                    (insp.PLAY_BASE,insp.PLAY_SIZE,len(source.plays),ps),
                                    (insp.CATEGORY_BASE,insp.CATEGORY_SIZE,len(source.categories),set())):
        for i in range(count):
            off = base+i*size
            allow(off,off+(size if i in changed else 4))
            if base == insp.PLAY_BASE:
                for s in range(11): allow(off+12+s*8,off+16+s*8)
    for fi in fs:
        off = insp.FORMATION_AUX_BASE + fi*insp.FORMATION_AUX_SIZE
        allow(off,off+80)
    diffs = writer._difference_ranges(resource, rebuilt)
    require(all(i in owned for a,b in diffs for i in range(a,b)), 'Complete offense changed an unowned byte')
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    report = dict(schema=REPORT_SCHEMA, status='PROVED OFFLINE', asset_id=asset_id,
                  source_sha256=digest(resource), replacement_sha256=digest(rebuilt),
                  new_play_indices=sorted(ps),
                  spy_intent={'schema': lib.SPY_INTENT_SCHEMA, 'records': []},
                  option_intent={'schema': lib.OPTION_INTENT_SCHEMA, 'records': []},
                  new_formation_count=len(final.formations), new_play_count=len(final.plays),
                  new_node_count=final.node_count, replaced_formations=len(fs), replaced_plays=len(ps),
                  retained_plays=len(source.plays)-len(ps), menus=len(pack.menus),
                  name_pool_bytes=struct.unpack_from('<I', new, writer.POOL_COUNT_WORD)[0]*2,
                  pool_strategy='exact chain/string interning; stable indices', runtime_witness=False)
    return writer.CompiledFormationPlayResource(asset_id, 'complete-offense:'+asset_id, digest(resource), digest(rebuilt),
        sum(b-a for a,b in diffs), diffs, (), (), tuple(sorted(fs)), tuple(sorted(ps)), rebuilt, final, report)

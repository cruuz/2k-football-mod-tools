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
from . import nfl2k5_playbook_lint as lint
from . import nfl2k5_formation_play_writer as writer

REPORT_SCHEMA = 'nfl2k5_complete_offense/v1'
#: Declared play type -> QB chain signatures it may carry and the header class it needs.
#: b77 p48o: draws, QB runs, QB-direct reverses (end arounds) and the retail flea flicker.
PLAY_SIGNATURES = {
    'run': ({'run', 'draw'}, 'run'), 'sneak': ({'qb_run'}, 'run'), 'keeper': ({'qb_run'}, 'run'),
    'reverse': ({'run'}, 'run'), 'pass': ({'pass'}, 'pass'), 'pa_pass': ({'pa_pass'}, 'pass'),
    'flea': ({'flea'}, 'pass'),
    # b776 pb1: the centre snaps to a back (retail H Direct Snap); the QB chain is a decoy release.
    'direct_snap': ({'other'}, 'run'),
    # b776 pb1: a play appended into a retained special-teams formation (fake field goal); its donor
    # is that formation's own retail play and keeps the donor's class.
    'special': (None, None),
}
SPECIAL_FORMATION_TYPES = range(8, 14)   # punt .. field goal / kick formations (formation type code)


def is_special_addition(play) -> bool:
    """b776 pb1: a play linked into a retained (special-teams) formation by index: appended into a free record, or
    written over one ordinary offensive record when the book has no free record left."""
    return isinstance(play.link_formation, int) and play.play_type == 'special'


def snap_target(chains) -> int | None:
    """Slot the centre's Snap To node names, or None."""
    for chain in chains:
        for node in chain or ():
            if int(node[0]) == 0x02:
                return int(node[1][0])
    return None


def require(value, message):
    if not value:
        from .nfl2k5_playbook_pack import PlaybookPackError
        raise PlaybookPackError(message)


def validate_structure(pack):
    """PROVED OFFLINE: reject ambiguous menus and partial/conditional recipes.

    b776 pb1: formations and plays may also be appended (``replace_index`` None) into the book's free
    records; an appended ``special`` play is linked by index into a retained special-teams formation
    instead of a menu. Everything else must sit in exactly the pack's menus."""
    from .nfl2k5_playbook_pack import TEAM_BOOKS
    require(pack.book.resolved_targets() == (pack.book.team,), 'Complete offense has exactly one team target')
    require(pack.book.team in TEAM_BOOKS, 'Complete offense needs a club book')
    fs, ps = pack.formations_by_id, {p.id: p for p in pack.plays}
    require(len(fs) == len(pack.formations) and len(ps) == len(pack.plays), 'Duplicate entry ID')
    require(len(set(fs) & set(ps)) == 0, 'Formation/play IDs overlap')
    require(len(dict(pack.menus)) == len(pack.menus) and set(dict(pack.menus)) == set(fs),
            'Complete offense needs exactly one menu per authored formation')
    for entries in (pack.formations, pack.plays):
        replaced = [e.replace_index for e in entries if e.replace_index is not None]
        require(len(set(replaced)) == len(replaced), 'Duplicate replacement index')
        for entry in entries:
            require(writer._clean_custom_name(entry.custom_name) == entry.custom_name, 'Invalid custom name')
    used = set()
    for fid, menu in pack.menus:
        require(3 <= len(menu) <= insp.FORMATION_PLAY_LINKS, f'{fid}: menu needs 3..36 plays')
        require(len(menu) == len(set(menu)), f'{fid}: duplicate play in menu')
        require(set(menu) <= set(ps), f'{fid}: unknown play ID')
        used.update(menu)
    specials = {p.id for p in pack.plays if is_special_addition(p)}
    require(not (used & specials), 'A special-teams addition is linked by its formation index, not a menu')
    require(used | specials == set(ps), 'Every authored play must appear in a menu')
    for p in pack.plays:
        if p.id in specials:
            require(p.link_group is None or p.link_group == 3, 'A special addition takes an ordinary menu slot')
        else:
            require(p.link_formation is None and p.link_group is None, 'v4 uses complete menus, not appended links')
        require(p.play_type in PLAY_SIGNATURES, 'Complete offense supports run/pass/PA/QB run/reverse/flea/direct snap/special only')
        require(p.play_type != 'special' or p.id in specials, 'A special play must be appended into a special formation')
        require(not p.option_intent and not p.spy_slots, 'No option/spy intent in complete offense')
        require(len(p.assignments) == 11 and all(p.assignments), 'Complete offense authors all eleven assignments')
        require(all(1 <= len(c) <= 15 and all(len(n) == 2 and n[0] != 0x1A for n in c)
                    for c in p.assignments), 'No conditional branches or invalid chains in complete offense')
        require(p.play_flags is not None and p.donor.flags is not None, 'Record donor and authored flags')
        require((p.play_flags & 0x1FF) == (p.donor.flags & 0x1FF), 'Donor family/type flags changed')
        if p.play_type == 'special':
            require(p.play_flags == p.donor.flags, 'A special addition keeps its retail donor header')
        else:
            require(lib.play_class_label(p.play_flags) == PLAY_SIGNATURES[p.play_type][1],
                    'Play class disagrees with declared type')
        if p.play_type == 'direct_snap':
            target = snap_target(p.assignments)
            require(target is not None and target != 0 and
                    any(int(n[0]) == 0x15 for n in p.assignments[target]),
                    'A direct snap needs the centre to snap to a carrier with a run path')


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


def new_category_records(pack, source):
    """b776 pb1: personnel groups the pack appends after the book's last record, {index: (positions, code, name)}.

    A formation names a new group by an index at or past the source's category count and gives all three
    values; the indices must continue the table without a gap and stay within the 26 records."""
    count = len(source.categories)
    rows = {}
    for f in pack.formations:
        ci = f.category_index
        if ci is None or ci < count:
            continue
        values = (f.category_positions, f.category_code, f.category_name)
        require(all(v is not None for v in values), f'{f.id}: a new personnel group needs positions, code and name')
        require(rows.get(ci, values) == values, f'{f.id}: formations disagree about new personnel group {ci}')
        rows[ci] = (tuple(values[0]), int(values[1]), values[2])
    require(sorted(rows) == list(range(count, count + len(rows))), 'New personnel groups must continue the table')
    require(count + len(rows) <= insp.CATEGORY_CAPACITY, 'Personnel groups exceed the 26 the book holds')
    for ci, (positions, code, name) in rows.items():
        require(lib.is_offense_category(list(positions)), f'New personnel group {ci}: not an offensive group')
        require(0 <= code <= 10, f'New personnel group {ci}: lottery code outside 0..10')
        require(writer._clean_custom_name(name) == name and 0 < len(name) <= 20, f'New personnel group {ci}: invalid name')
    return rows


def append_category_records(resource, rows):
    """Write appended personnel-group records (name pointer parked on the book name until the final repack)."""
    if not rows:
        return resource
    raw = bytearray(resource)
    h = insp.RESOURCE_HEADER_SIZE
    count = struct.unpack_from('<I', raw, h + 0x3C)[0]
    book_name = 0x30 - 1 + struct.unpack_from('<i', raw, h + 0x30)[0]
    for ci in sorted(rows):
        require(ci == count, 'New personnel groups must continue the table')
        positions, code, _name = rows[ci]
        off = insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE
        raw[h + off:h + off + insp.CATEGORY_SIZE] = bytes(insp.CATEGORY_SIZE)
        struct.pack_into('<i', raw, h + off, book_name - off + 1)
        raw[h + off + 4] = code & 0x3F
        raw[h + off + 5:h + off + 16] = bytes(positions)
        count += 1
    struct.pack_into('<I', raw, h + 0x3C, count)
    return bytes(raw)


def category_edits(pack, source, body, fs):
    """b77 p6s: the personnel-group records the pack rewrites, {index: (positions|None, code|None, name|None)}.

    A group may be rewritten (eleven position codes, lottery code 0..10, label) only when no retained
    formation (Hail Mary, Clock, defense, special teams) owns it or lists it in its mask, and every
    pack formation that names the group agrees on each value. Groups no formation names stay stock."""
    edits = {}
    for f in pack.formations:
        if f.category_index is not None and f.category_index >= len(source.categories):
            continue                    # b776 pb1: appended groups (new_category_records)
        values = (f.category_positions, f.category_code, f.category_name)
        if all(v is None for v in values):
            continue
        ci = f.category_index
        require(ci is not None and 0 <= ci < len(source.categories), f'{f.id}: personnel group edit needs a group')
        cur = edits.setdefault(ci, [None, None, None])
        for k, v in enumerate(values):
            if v is None:
                continue
            require(cur[k] is None or cur[k] == v, f'{f.id}: formations disagree about personnel group {ci}')
            cur[k] = v
    if edits:
        for g in source.formations:
            if g.index in fs:
                continue
            aux = insp.FORMATION_AUX_BASE + g.index * insp.FORMATION_AUX_SIZE
            own, mask = struct.unpack_from('<II', body, aux + 0x48)
            for ci in edits:
                require((own & 0x3F) != ci and not mask >> ci & 1,
                        f'Personnel group {ci} is used by retained formation {g.index}; it cannot be rewritten')
    for ci, (positions, code, name) in edits.items():
        if positions is not None:
            require(lib.is_offense_category(list(positions)), f'Personnel group {ci}: not an offensive group')
        require(lib.is_offense_category(lib.category_positions(body, ci)),
                f'Personnel group {ci}: only offensive groups can be recoded')
        if name is not None:
            require(writer._clean_custom_name(name) == name and 0 < len(name) <= 20,
                    f'Personnel group {ci}: invalid name')
    return {ci: tuple(v) for ci, v in edits.items()}


def apply_category_edits(resource, edits):
    """Positions and lottery code bytes (names are written at the final repack)."""
    raw = bytearray(resource)
    for ci, (positions, code, _name) in edits.items():
        off = insp.RESOURCE_HEADER_SIZE + insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE
        if positions is not None:
            raw[off + 5:off + 16] = bytes(positions)
        if code is not None:
            raw[off + 4] = (raw[off + 4] & 0xC0) | code
    return bytes(raw)


def _grow(resource, app_forms, app_plays, asset_id):
    """b776 pb1: append clones of each appended entry's donor (donor names, chains and links) so every
    appended index exists before the per-record compile; the final repack replaces all of it."""
    if not app_forms and not app_plays:
        return resource
    compiled = writer.compile_formation_play_creations(
        resource,
        [dict(asset_id=asset_id, donor_formation_index=f.donor.index) for f in app_forms],
        [dict(asset_id=asset_id, donor_play_index=p.donor.index) for p in app_plays],
        allow_unchanged=True)
    return compiled.replacement


def compile_offense(resource, pack, *, asset_id):
    """PROVED OFFLINE: compile the whole replacement atomically in memory.

    b776 pb1: besides replacing every ordinary offensive record in place, a pack may append formations
    and plays into the book's free records (50 formations, 270 plays), append personnel groups (26
    records) and append special-teams additions linked into a retained formation's menu."""
    from dataclasses import replace as _replace
    from . import nfl2k5_playbook_pack as packs
    validate_structure(pack)
    require(packs.book_fingerprint(resource) == pack.base.book_fingerprint,
            'Complete offense source fingerprint changed; regenerate and review')
    source = insp.parse_playbook_resource(resource, asset_id=asset_id)
    original = resource
    old = resource[32:]
    fs, ps = ordinary_indices(source, old)
    nf0, np0, nc0 = len(source.formations), len(source.plays), len(source.categories)
    require({f.replace_index for f in pack.formations if f.replace_index is not None} == fs,
            'Replace every ordinary offensive formation exactly once')
    require({p.replace_index for p in pack.plays if p.replace_index is not None} == ps,
            'Replace every ordinary offensive play exactly once')
    app_forms = [f for f in pack.formations if f.replace_index is None]
    app_plays = [p for p in pack.plays if p.replace_index is None]
    require(nf0 + len(app_forms) <= insp.FORMATION_CAPACITY, 'Appended formations exceed the 50 the book holds')
    require(np0 + len(app_plays) <= insp.PLAY_CAPACITY, 'Appended plays exceed the 270 the book holds')
    special_links = {}
    for p in [q for q in pack.plays if q.replace_index is None or is_special_addition(q)]:
        require(p.donor.index < np0, f'{p.id}: donor outside the book')
        if is_special_addition(p):
            fi = p.link_formation
            require(0 <= fi < nf0 and fi not in fs, f'{p.id}: a special addition links into a retained formation')
            rec = lib.formation_record(old, fi)
            require(rec.type_code in SPECIAL_FORMATION_TYPES, f'{p.id}: target formation is not special teams')
            require(any(l.play_index == p.donor.index for l in source.formations[fi].play_links),
                    f'{p.id}: a special addition clones a play of its own formation')
            special_links.setdefault(fi, []).append(p.id)
        else:
            require(p.donor.index in ps, 'Play donor must be ordinary offense')
    for f in app_forms:
        require(f.donor.index in fs, 'Formation donor must be ordinary offense')
    # appended indices, in pack order (the writer appends in request order)
    pack = _replace(pack,
                    formations=tuple(f if f.replace_index is not None else _replace(f, replace_index=nf0 + app_forms.index(f))
                                     for f in pack.formations),
                    plays=tuple(p if p.replace_index is not None else _replace(p, replace_index=np0 + app_plays.index(p))
                                for p in pack.plays))
    special_ids = {p.id for p in pack.plays if is_special_addition(p)}
    new_f = {nf0 + k for k in range(len(app_forms))}
    new_p = {np0 + k for k in range(len(app_plays))}
    new_cats = new_category_records(pack, source)
    # b77 p6s: personnel groups may be rewritten (twins, lottery codes, labels) and formations may list
    # their group memberships; everything else about the groups stays stock.
    edits = category_edits(pack, source, old, fs)
    if edits:
        resource = apply_category_edits(resource, edits)
    resource = append_category_records(resource, new_cats)
    resource = _grow(resource, app_forms, app_plays, asset_id)
    grown = insp.parse_playbook_resource(resource, asset_id=asset_id)
    cats = resource[32:]
    all_fs, all_ps = fs | new_f, ps | new_p
    for f in pack.formations:
        require(f.donor.index in fs, 'Formation donor must be ordinary offense')
        ci = f.category_index
        require(ci is not None and 0 <= ci < len(grown.categories), 'Formation needs a stock personnel category')
        require(tuple(lib.category_positions(cats, ci)) == f.position_codes
                and (f.category_positions is None or tuple(f.category_positions) == f.position_codes),
                'Formation personnel disagrees with its personnel group')
        if f.category_mask is not None:
            require(ci in f.category_mask, f'{f.id}: the mask must include the owning group')
            donor_aux = insp.FORMATION_AUX_BASE + f.donor.index * insp.FORMATION_AUX_SIZE
            donor_own, donor_mask = struct.unpack_from('<II', old, donor_aux + 0x48)
            for c in f.category_mask:
                # same eleven players, or a stock cross-personnel membership the retail donor already had
                require(c < len(grown.categories)
                        and (sorted(lib.category_positions(cats, c)) == sorted(f.position_codes)
                             or (donor_mask >> c & 1 and (donor_own & 0x3F) == ci and c not in edits)),
                        f'{f.id}: a mask group must field the same eleven players')
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
        req.pop('situation', None)
        compiled = writer.compile_formation_play_creations(staging, [req], allow_unchanged=True)
        off = insp.FORMATION_BASE + f.replace_index * insp.FORMATION_SIZE
        # Keep current name pointer valid until final repack.
        result[32 + off + 4:32 + off + insp.FORMATION_SIZE] = compiled.replacement[32 + off + 4:32 + off + insp.FORMATION_SIZE]
        if f.situation is not None:
            # b77 p48o: explicit CPU situation ratings (short, medium, long) in flag bits 21-29,
            # read by the native formation scorer 0x207EF0; every other flag bit stays the donor's.
            word = struct.unpack_from('<I', result, 32 + off + 4)[0] & ~(0x1FF << 21)
            for shift, value in zip((21, 24, 27), f.situation):
                word |= (value & 7) << shift
            struct.pack_into('<I', result, 32 + off + 4, word)
        aux = insp.FORMATION_AUX_BASE + f.replace_index * insp.FORMATION_AUX_SIZE
        result[32 + aux + 72:32 + aux + 80] = compiled.replacement[32 + aux + 72:32 + aux + 80]
        if f.category_mask is not None:
            struct.pack_into('<I', result, 32 + aux + 0x4C, sum(1 << c for c in f.category_mask))
        names[off] = f.custom_name.encode('utf-16le') + b'\0\0'
    checkdown_routes = []
    execution_fixes = []
    play_formations = {p.id: [pack.formations_by_id[fid] for fid, menu in pack.menus if p.id in menu]
                       for p in pack.plays}
    for p in pack.plays:
        special = p.id in special_ids
        if not special:
            require(p.donor.index in ps, 'Play donor must be ordinary offense')
        donor_flags, donor_chains = lib.play_chains(old, p.donor.index)
        require(donor_flags == p.donor.flags and lib.qb_signature(donor_chains[0][1]) == p.donor.signature,
                f'{p.id}: donor metadata differs from source')
        wanted = PLAY_SIGNATURES[p.play_type][0]
        require(wanted is None or lib.qb_signature(p.assignments[0]) in wanted,
                f'{p.id}: QB chain disagrees with play type')
        if special:
            authored = [list(c) for c in p.assignments]
        else:
            # Old complete-offense files retain their original authored nodes.
            # Normalize their deep-back flats here so rebuilding those packs in
            # Studio receives the same geometry repair as new route authoring.
            variants = [lib.forward_back_flats(p.assignments, f.slot_positions, f.position_codes)
                        for f in play_formations[p.id]]
            require(all(v[0] == variants[0][0] for v in variants),
                    f'{p.id}: shared checkdown has conflicting formation depths')
            authored, repaired_slots = variants[0]
            # b77 p13: rebuild template plays whose geometry the runtime cannot
            # execute (far end-around runners, zero-margin RB screens, backs whose
            # routes finish level with the QB). Unrecognised plays pass unchanged.
            fixes = [lint.normalize_offense_play(f.slot_positions, f.position_codes, authored)
                     for f in play_formations[p.id]]
            require(all(fx[0] == fixes[0][0] for fx in fixes),
                    f'{p.id}: shared play has conflicting execution fixes')
            fixed, fix_receipts = fixes[0]
            if fixed is not None:
                authored = fixed
            if fix_receipts:
                execution_fixes.append(dict(play_id=p.id, play_index=p.replace_index,
                                            formations=[f.id for f in play_formations[p.id]],
                                            rules=fix_receipts))
            if repaired_slots:
                checkdown_routes.append(dict(play_id=p.id, play_index=p.replace_index,
                                             slots=repaired_slots,
                                             formations=[f.id for f in play_formations[p.id]]))
        req = p.request_mapping(asset_id)
        req['assignments'] = [codec.chain_json(chain) for chain in authored]
        req['replace_index'] = p.replace_index
        req.pop('custom_name')
        compiled = writer.compile_formation_play_creations(staging, (), [req])
        flags, chains = lib.play_chains(compiled.replacement[32:], p.replace_index)
        off = insp.PLAY_BASE + p.replace_index * insp.PLAY_SIZE
        struct.pack_into('<I', result, 32 + off + 4, flags)
        names[off] = p.custom_name.encode('utf-16le') + b'\0\0'
        assignments.update({(p.replace_index, slot): chain for slot, chain in enumerate(chains)})
    for ci, (_positions, _code, name) in edits.items():
        if name is not None:
            names[insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE] = name.encode('utf-16le') + b'\0\0'
    for ci, (_positions, _code, name) in new_cats.items():
        names[insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE] = name.encode('utf-16le') + b'\0\0'
    play_ids = {p.id: p.replace_index for p in pack.plays}
    for fid, menu in pack.menus:
        fi = pack.formations_by_id[fid].replace_index
        aux = 32 + insp.FORMATION_AUX_BASE + fi * insp.FORMATION_AUX_SIZE
        words = [0x8000 | (min(slot, 3) << 9) | play_ids[pid] for slot, pid in enumerate(menu)]
        struct.pack_into('<36H', result, aux, *(words + [0x7FF] * (36-len(words))))
    special_words = {}
    for fi, ids in special_links.items():
        aux = 32 + insp.FORMATION_AUX_BASE + fi * insp.FORMATION_AUX_SIZE
        words = list(struct.unpack_from('<36H', result, aux))
        for pid in ids:
            slot = next((k for k, w in enumerate(words) if (w & 0x1FF) == 0x1FF), None)
            require(slot is not None, f'{pid}: the special formation menu is full')
            words[slot] = 0x8000 | (3 << 9) | play_ids[pid]
            special_words.setdefault(fi, []).append(slot)
        struct.pack_into('<36H', result, aux, *words)
    # PROVED OFFLINE: preserve default audible formation indices; remap their
    # link byte to one of the first three valid entries in each new menu.
    for n in range(5):
        off = 32 + 0x4C + n*2
        fi = result[off]
        require(fi in fs, 'Unexpected special offense default audible')
        result[off+1] = min(n, 2)
    rebuilt = repack(bytes(result), names, assignments)
    final = insp.parse_playbook_resource(rebuilt, asset_id=asset_id)
    ui_problems = insp.playcall_ui_problems(rebuilt)
    require(not ui_problems, 'Final offense has unsafe play-call names or menus: ' + '; '.join(ui_problems[:3]))
    new = rebuilt[32:]
    require(len(final.formations) == nf0 + len(app_forms) and len(final.plays) == np0 + len(app_plays), 'Counts changed')
    require(len(final.categories) == nc0 + len(new_cats), 'Category count changed')
    for p in source.plays:
        if p.index not in ps:
            require(lib.play_chains(old, p.index) == lib.play_chains(new, p.index), 'Retained play semantics changed')
            require(final.plays[p.index].name == p.name, 'Retained play renamed')
    for f in source.formations:
        if f.index not in fs:
            off = insp.FORMATION_BASE + f.index * insp.FORMATION_SIZE
            aux = insp.FORMATION_AUX_BASE + f.index * insp.FORMATION_AUX_SIZE
            old_links = list(struct.unpack_from('<36H', old, aux))
            new_links = list(struct.unpack_from('<36H', new, aux))
            for slot in special_words.get(f.index, ()):
                require(old_links[slot] & 0x1FF == 0x1FF, 'Special addition overwrote a retained link')
                new_links[slot] = old_links[slot]
            require(new[off+4:off+insp.FORMATION_SIZE] == old[off+4:off+insp.FORMATION_SIZE]
                    and new_links == old_links and new[aux+72:aux+80] == old[aux+72:aux+80]
                    and final.formations[f.index].name == f.name,
                    'Retained formation changed')
    for ci in range(nc0):
        off = insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE
        require(new[off+4:off+16] == cats[off+4:off+16], 'Personnel changed')
        if ci in edits and edits[ci][2] is not None:
            require(final.categories[ci].name == edits[ci][2], 'Personnel group name not written')
    for ci, (positions, code, name) in new_cats.items():
        off = insp.CATEGORY_BASE + ci * insp.CATEGORY_SIZE
        require(new[off+4] & 0x3F == code and tuple(new[off+5:off+16]) == tuple(positions)
                and final.categories[ci].name == name, 'New personnel group not written')
    # PROVED OFFLINE: explicit ownership excludes header references, defensive
    # audibles, substitution rows, category payloads and every unused table slot.
    owned = set()
    def allow(a, b):
        owned.update(range(32+a, 32+b))
    for a,b in ((0x30,0x34),(0x40,0x44),(0x4C,0x56),(insp.NODE_BASE,insp.BODY_SIZE)):
        allow(a,b)
    if app_forms or app_plays or new_cats:
        allow(0x34, 0x40)
    for base,size,count,changed in ((insp.FORMATION_BASE,insp.FORMATION_SIZE,len(final.formations),all_fs),
                                    (insp.PLAY_BASE,insp.PLAY_SIZE,len(final.plays),all_ps),
                                    (insp.CATEGORY_BASE,insp.CATEGORY_SIZE,len(final.categories),
                                     set(edits) | set(new_cats))):
        for i in range(count):
            off = base+i*size
            allow(off,off+(size if i in changed else 4))
            if base == insp.PLAY_BASE:
                for s in range(11): allow(off+12+s*8,off+16+s*8)
    for fi in all_fs:
        off = insp.FORMATION_AUX_BASE + fi*insp.FORMATION_AUX_SIZE
        allow(off,off+80)
    for fi, slots in special_words.items():
        off = insp.FORMATION_AUX_BASE + fi*insp.FORMATION_AUX_SIZE
        for slot in slots:
            allow(off + 2 * slot, off + 2 * slot + 2)
    resource = original
    diffs = writer._difference_ranges(resource, rebuilt)
    require(all(i in owned for a,b in diffs for i in range(a,b)), 'Complete offense changed an unowned byte')
    rebuilt, category_menus = writer.compact_unused_categories(rebuilt, trim_name_tail=True)
    final = insp.parse_playbook_resource(rebuilt, asset_id=asset_id)
    new = rebuilt[32:]
    diffs = writer._difference_ranges(resource, rebuilt)
    digest = lambda raw: hashlib.sha256(raw).hexdigest()
    report = dict(schema=REPORT_SCHEMA, status='PROVED OFFLINE', asset_id=asset_id,
                  source_sha256=digest(resource), replacement_sha256=digest(rebuilt),
                  new_play_indices=sorted(all_ps | {play_ids[i] for i in special_ids}),
                  spy_intent={'schema': lib.SPY_INTENT_SCHEMA, 'records': []},
                  option_intent={'schema': lib.OPTION_INTENT_SCHEMA, 'records': []},
                  new_formation_count=len(final.formations), new_play_count=len(final.plays),
                  new_node_count=final.node_count, replaced_formations=len(fs), replaced_plays=len(ps),
                  appended_formations=len(app_forms), appended_plays=len([p for p in app_plays if p.id not in special_ids]),
                  special_additions=[dict(play_id=pid, play_index=play_ids[pid],
                                          formation=next(fi for fi, ids in special_links.items() if pid in ids))
                                     for pid in sorted(special_ids)],
                  appended_categories={str(ci): v[2] for ci, v in new_cats.items()},
                  retained_plays=len(source.plays)-len(ps), menus=len(pack.menus),
                  name_pool_bytes=struct.unpack_from('<I', new, writer.POOL_COUNT_WORD)[0]*2,
                  pool_strategy='exact chain/string interning; stable indices',
                  checkdown_routes=checkdown_routes,
                  execution_fixes=dict(schema=lint.FIX_SCHEMA, plays=execution_fixes),
                  category_menus=category_menus,
                  runtime_witness=False)
    return writer.CompiledFormationPlayResource(asset_id, 'complete-offense:'+asset_id, digest(resource), digest(rebuilt),
        sum(b-a for a,b in diffs), diffs, (), (), tuple(sorted(all_fs)), tuple(sorted(all_ps)), rebuilt, final, report)

#!/usr/bin/env python3
"""Beta 77 job p48d: put the SOFTDRINK defense v2 into a shipped team PLAY resource (PACK0 entries 307..342).

Bounded repair, a function of the bytes the defense owns:
  * the defensive formation records the v2 pack re-authors (geometry columns, situation bits 21-29, name pointer),
    their 0x50 menu entries, and an appended Nickel Mug formation where the pack has one;
  * the defensive play records the pack replaces or appends (header, eleven descriptors and chain pointers, name);
  * appended node chains and UTF-16 names in the input's verified zero tails, and the four count words.
Every chain and name is first looked up in the input's own pools (retail scripts are usually still there), so the
node budget grows only by what is new.  Category rows (position-pool recode, depth roles), kickoff/return records,
offense and special teams are untouched; a scope receipt proves every byte outside the declared ranges identical.

The target content is recompiled the way Build does: retail entry (read from the user's own XISO) -> the team's
offense pack -> the team's v2 defense pack, whose source pin must match.  The input's offense must decode exactly
like that compile (family 0 plays and offensive formations), so the defense is never put on a different offense.

Usage:
  p48d_repair.py SOURCE.play OUTPUT.play --entry-id 324 --receipt R.json [--retail-image ISO]
                 [--offense-pack P] [--defense-pack P] [--expected-input-sha256 HEX]
Known inputs are pinned in p48d_repair_manifest.json (v0.5 entry hashes and their exact outputs); a stacked input
(e.g. after job p48o's offense repair) needs --expected-input-sha256 and the matching offense/defense packs.
Output creation is exclusive; the input is never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / 'tools')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.dont_write_bytecode = True

from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402
from mod_editor.core import nfl2k5_defense_lint as dlint  # noqa: E402

SCHEMA = 'b77.p48d.defense-v2.v1'
MANIFEST = Path(__file__).with_name('p48d_repair_manifest.json')
RETAIL_IMAGE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
H = ip.RESOURCE_HEADER_SIZE
NODE_COUNT_WORD, FORMATION_COUNT_WORD, PLAY_COUNT_WORD, POOL_COUNT_WORD = 0x40, 0x34, 0x38, 0x1083C


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def team_of(entry_id: int) -> str:
    from nfl2k5_playbook_position_recode import BOOK_ENTRIES
    for team, entry in BOOK_ENTRIES.items():
        if entry == entry_id and team in pk.TEAM_BOOKS:
            return team
    raise ValueError(f'PACK0 entry {entry_id} is not one of the 32 team books')


def default_offense(team: str) -> Path:
    return ROOT / f"data/playbooks/softdrink_{'giants' if team == 'NYG' else team.lower()}_modern.2k5book"


def default_defense(team: str) -> Path:
    return ROOT / f'data/playbooks/softdrink_{team.lower()}_defense.2k5book'


def reference(team: str, entry_id: int, image: Path, offense: Path, defense: Path, xbe=None):
    """retail -> offense compile -> v2 defense, exactly like Build's playbook stage (in memory)."""
    from nfl2k5_playbook_position_recode import OuterImage
    from mod_editor.core.nfl2k5_complete_offense import compile_offense
    from mod_editor.core.nfl2k5_formation_play_writer import compile_formation_play_creations
    with OuterImage(image) as img:
        raw = img.read_entry(entry_id)
    source = compile_offense(raw, pk.load_pack(offense), asset_id=f'book:{team}').replacement
    pack = pk.load_pack(defense)
    if pack.base.book_fingerprint != pk.book_fingerprint(source[H:]):
        raise ValueError('The defense pack is pinned to a different offense compile; regenerate it (pb/v2/defense/build.py)')
    book = ip.parse_playbook_resource(source)
    for p in pack.plays:
        pk.validate_defense_pack_play(p, book, source[H:])
    rows = pk.pack_requests(pack, f'book:{team}', book)
    compiled = compile_formation_play_creations(source, *rows)
    return source, compiled.replacement, pack


# ---------------------------------------------------------------------------------------------------------------
# decoded views
# ---------------------------------------------------------------------------------------------------------------
def play_view(body: bytes, book, index: int):
    flags, chains = lib.play_chains(body, index)
    return (book.plays[index].name, flags, tuple((d, tuple(bytes(n) for n in nodes)) for d, nodes in chains))


def formation_view(body: bytes, book, index: int):
    rec = body[ip.FORMATION_BASE + index * ip.FORMATION_SIZE: ip.FORMATION_BASE + (index + 1) * ip.FORMATION_SIZE]
    aux = body[ip.FORMATION_AUX_BASE + index * ip.FORMATION_AUX_SIZE: ip.FORMATION_AUX_BASE + (index + 1) * ip.FORMATION_AUX_SIZE]
    return (book.formations[index].name, rec[4:], aux)


def owned(pack: pk.PlaybookPack, book_ref):
    """(play indices, formation indices) the defense pack writes in the reference compile."""
    n_plays_src = pack.base.donor_play_count
    n_forms_src = pack.base.donor_formation_count
    appended_p = [p for p in pack.plays if p.replace_index is None]
    plays = sorted({p.replace_index for p in pack.plays if p.replace_index is not None}
                   | {n_plays_src + k for k in range(len(appended_p))})
    appended_f = [f for f in pack.formations if f.replace_index is None]
    forms = sorted({f.replace_index for f in pack.formations if f.replace_index is not None}
                   | {n_forms_src + k for k in range(len(appended_f))})
    # formations whose menu gains links
    linked = set()
    for p in pack.plays:
        if p.link_formation is not None:
            t = pk._link_target_index(pack, p.link_formation, book_ref)
            if t is not None:
                linked.add(t)
    return plays, forms, sorted(linked)


def rel(field: int, target: int) -> int:
    return target - field + 1


def _name_raw(body: bytes, field: int) -> bytes:
    from mod_editor.core import nfl2k5_formation_play_writer as writer
    start = field - 1 + struct.unpack_from('<i', body, field)[0]
    return bytes(body[start: writer._string_end(body, field)])


# ---------------------------------------------------------------------------------------------------------------
# transformation
# ---------------------------------------------------------------------------------------------------------------
def transform(payload: bytes, source: bytes, ref: bytes, pack: pk.PlaybookPack):
    if len(payload) != H + ip.BODY_SIZE:
        raise ValueError('Expected one fixed-size PLAY resource')
    book_in = ip.parse_playbook_resource(payload)
    book_src = ip.parse_playbook_resource(source)
    book_ref = ip.parse_playbook_resource(ref)
    body_in, body_src, body_ref = payload[H:], source[H:], ref[H:]
    # 1. the input's offense is the offense the defense pack is pinned to
    for p in book_src.plays:
        if p.family_id == 0:
            if p.index >= len(book_in.plays) or play_view(body_in, book_in, p.index) != play_view(body_src, book_src, p.index):
                raise ValueError(f'Input offense play {p.index} differs from the pinned offense compile')
    for f in book_src.formations:
        if lib.formation_record(body_src, f.index).type_code < 4:
            if formation_view(body_in, book_in, f.index) != formation_view(body_src, book_src, f.index):
                raise ValueError(f'Input offensive formation {f.index} differs from the pinned offense compile')
    plays, forms, linked = owned(pack, book_src)
    n_forms_in, n_plays_in = len(book_in.formations), len(book_in.plays)
    # Everything defensive must end up exactly as a fresh Build makes it: records an earlier defense pack rewrote but
    # this one keeps native (a retained retail call or formation) are restored too.
    for p in book_ref.plays:
        if p.family_id == 1 and p.index < n_plays_in and p.index not in plays:
            if play_view(body_in, book_in, p.index) != play_view(body_ref, book_ref, p.index):
                plays = sorted(set(plays) | {p.index})
    for f in book_ref.formations:
        if 4 <= lib.formation_record(body_ref, f.index).type_code <= 7 and f.index < n_forms_in and f.index not in forms:
            if formation_view(body_in, book_in, f.index) != formation_view(body_ref, book_ref, f.index):
                forms = sorted(set(forms) | {f.index})
    expect_forms = len(book_ref.formations)
    expect_plays = len(book_ref.plays)
    already = n_forms_in == expect_forms and n_plays_in == expect_plays
    if not already and (n_forms_in != len(book_src.formations) or n_plays_in != len(book_src.plays)):
        raise ValueError('Input formation/play counts match neither the pinned source nor the repaired book')
    # 2. rebuild both pools from the decoded content: owned records take the reference compile's chains and names,
    #    every other record keeps its own.  Unreferenced chains and names of the replaced defense disappear, exactly
    #    as Build's offense repack does; pool layout and pointer fields are declared scopes, content is proved below.
    total_plays, total_forms = expect_plays, expect_forms
    chains = {}
    for i in range(total_plays):
        src_body = body_ref if i in plays else body_in
        _, slot_rows = lib.play_chains(src_body, i)
        chains[i] = [(d, b''.join(bytes(n) for n in nodes)) for d, nodes in slot_rows]
    names = {}
    names[0x30] = _name_raw(body_in, 0x30)
    for f in range(total_forms):
        field = ip.FORMATION_BASE + f * ip.FORMATION_SIZE
        names[field] = _name_raw(body_ref if f in forms else body_in, field)
    for i in range(total_plays):
        field = ip.PLAY_BASE + i * ip.PLAY_SIZE
        names[field] = _name_raw(body_ref if i in plays else body_in, field)
    for c in range(len(book_in.categories)):
        field = ip.CATEGORY_BASE + c * ip.CATEGORY_SIZE
        names[field] = _name_raw(body_in, field)
    body_b = bytearray(body_in)
    scopes = []
    for i in plays:
        rec = ip.PLAY_BASE + i * ip.PLAY_SIZE
        if i >= n_plays_in and any(body_b[rec: rec + ip.PLAY_SIZE]):
            raise ValueError(f'Play slot {i} beyond the input count is not empty')
        body_b[rec: rec + ip.PLAY_SIZE] = body_ref[rec: rec + ip.PLAY_SIZE]
        scopes.append((H + rec, H + rec + ip.PLAY_SIZE, f'play {i} record'))
    for f in forms:
        recoff = ip.FORMATION_BASE + f * ip.FORMATION_SIZE
        ref_rec = body_ref[recoff: recoff + ip.FORMATION_SIZE]
        if f >= n_forms_in and (any(body_b[recoff: recoff + ip.FORMATION_SIZE])
                                or any(body_b[ip.FORMATION_AUX_BASE + f * ip.FORMATION_AUX_SIZE:
                                              ip.FORMATION_AUX_BASE + (f + 1) * ip.FORMATION_AUX_SIZE])):
            raise ValueError(f'Formation slot {f} beyond the input count is not empty')
        same_donor = any(pf.replace_index == f and pf.donor.index == f for pf in pack.formations)
        if f < n_forms_in and not already and same_donor:
            mine = bytes(body_b[recoff: recoff + ip.FORMATION_SIZE])
            # same native donor: only flags (situation bits), geometry columns and the name may differ
            if mine[8:0x1A] != ref_rec[8:0x1A] or any(mine[0x1A + 14 * s: 0x1A + 14 * s + 2] != ref_rec[0x1A + 14 * s: 0x1A + 14 * s + 2]
                                                      for s in range(11)):
                raise ValueError(f'Formation {f}: personnel/stance bytes differ from the native donor')
        body_b[recoff: recoff + ip.FORMATION_SIZE] = ref_rec
        scopes.append((H + recoff, H + recoff + ip.FORMATION_SIZE, f'formation {f} record'))
    for f in sorted(set(forms) | set(linked)):
        aux = ip.FORMATION_AUX_BASE + f * ip.FORMATION_AUX_SIZE
        body_b[aux: aux + ip.FORMATION_AUX_SIZE] = body_ref[aux: aux + ip.FORMATION_AUX_SIZE]
        scopes.append((H + aux, H + aux + ip.FORMATION_AUX_SIZE, f'formation {f} menu'))
    old_nodes = struct.unpack_from('<I', body_in, NODE_COUNT_WORD)[0]
    # nodes
    body_b[ip.NODE_BASE: POOL_COUNT_WORD] = bytes(POOL_COUNT_WORD - ip.NODE_BASE)
    cursor, intern = ip.NODE_BASE, {}
    for i in range(total_plays):
        for slot, (desc, raw) in enumerate(chains[i]):
            if raw not in intern:
                if cursor + len(raw) > POOL_COUNT_WORD:
                    raise ValueError('Node pool capacity (3,500) exceeded')
                intern[raw] = cursor
                body_b[cursor: cursor + len(raw)] = raw
                cursor += len(raw)
            field = ip.PLAY_BASE + i * ip.PLAY_SIZE + 8 + slot * 8
            struct.pack_into('<Ii', body_b, field, desc, rel(field + 4, intern[raw]))
    new_nodes = (cursor - ip.NODE_BASE) // ip.NODE_SIZE
    struct.pack_into('<I', body_b, NODE_COUNT_WORD, new_nodes)
    # names
    body_b[ip.STRING_BASE:] = bytes(ip.BODY_SIZE - ip.STRING_BASE)
    cursor, intern = ip.STRING_BASE, {}
    for field, raw in names.items():
        if raw not in intern:
            if cursor + len(raw) > ip.BODY_SIZE:
                raise ValueError('Name pool capacity exceeded')
            intern[raw] = cursor
            body_b[cursor: cursor + len(raw)] = raw
            cursor += len(raw)
        struct.pack_into('<i', body_b, field, rel(field, intern[raw]))
    struct.pack_into('<I', body_b, POOL_COUNT_WORD, (cursor - ip.STRING_BASE) // 2)
    struct.pack_into('<I', body_b, FORMATION_COUNT_WORD, total_forms)
    struct.pack_into('<I', body_b, PLAY_COUNT_WORD, total_plays)
    scopes += [(H + ip.NODE_BASE, H + POOL_COUNT_WORD, 'node pool (rebuilt with exact interning)'),
               (H + POOL_COUNT_WORD, H + POOL_COUNT_WORD + 4, 'name pool count'),
               (H + ip.STRING_BASE, H + ip.BODY_SIZE, 'name pool (rebuilt with exact interning)'),
               (H + 0x30, H + 0x34, 'book name pointer'),
               (H + FORMATION_COUNT_WORD, H + FORMATION_COUNT_WORD + 4, 'formation count'),
               (H + PLAY_COUNT_WORD, H + PLAY_COUNT_WORD + 4, 'play count'),
               (H + NODE_COUNT_WORD, H + NODE_COUNT_WORD + 4, 'node count')]
    for i in range(total_plays):
        if i not in plays:
            rec = ip.PLAY_BASE + i * ip.PLAY_SIZE
            scopes.append((H + rec, H + rec + 4, f'play {i} name pointer'))
            scopes.append((H + rec + 8, H + rec + ip.PLAY_SIZE, f'play {i} chain descriptors and pointers'))
    for f in range(total_forms):
        if f not in forms:
            field = ip.FORMATION_BASE + f * ip.FORMATION_SIZE
            scopes.append((H + field, H + field + 4, f'formation {f} name pointer'))
    for c in range(len(book_in.categories)):
        field = ip.CATEGORY_BASE + c * ip.CATEGORY_SIZE
        scopes.append((H + field, H + field + 4, f'category {c} name pointer'))
    result = payload[:H] + bytes(body_b)
    # 4. decoded content: owned records equal the reference compile, everything else equals the input
    book_out = ip.parse_playbook_resource(result)
    body_out = result[H:]
    for p in book_out.plays:
        want = play_view(body_ref, book_ref, p.index) if p.index in plays else play_view(body_in, book_in, p.index)
        if p.family_id == 1 and play_view(body_out, book_out, p.index) != play_view(body_ref, book_ref, p.index):
            raise ValueError(f'Defensive play {p.index} differs from a fresh Build')
        if play_view(body_out, book_out, p.index) != want:
            raise ValueError(f'Play {p.index} did not decode as intended')
        if p.index in plays:
            error = codec.validate_play(p.flags_or_id, lib.play_chains(body_out, p.index)[1])
            if error:
                raise ValueError(f'Native validator rejects play {p.index}: {error}')
    for f in book_out.formations:
        src = (body_ref, book_ref) if (f.index in forms or f.index in linked) else (body_in, book_in)
        if formation_view(body_out, book_out, f.index) != formation_view(src[0], src[1], f.index):
            raise ValueError(f'Formation {f.index} did not decode as intended')
    for c in range(26):
        row = ip.CATEGORY_BASE + c * ip.CATEGORY_SIZE
        if body_out[row + 4: row + ip.CATEGORY_SIZE] != body_in[row + 4: row + ip.CATEGORY_SIZE]:
            raise ValueError(f'Category row {c} changed')
    if [c.name for c in book_out.categories] != [c.name for c in book_in.categories]:
        raise ValueError('Category names changed')
    if ip.menu_link_problems(result):
        raise ValueError('Menu link problems: ' + '; '.join(ip.menu_link_problems(result)))
    lint = [x.to_json() for x in dlint.lint_resource(result) if x.severity == 'error']
    if lint:
        raise ValueError('Defense linter: ' + json.dumps(lint)[:400])
    receipt_scopes, outside = ranges(payload, result, scopes)
    return result, dict(owned_plays=plays, owned_formations=forms, menus_written=sorted(set(forms) | set(linked)),
                        old_node_count=old_nodes, new_node_count=new_nodes,
                        old_name_units=struct.unpack_from('<I', body_in, POOL_COUNT_WORD)[0],
                        new_name_units=struct.unpack_from('<I', result[H:], POOL_COUNT_WORD)[0],
                        scopes=receipt_scopes, outside_scope_sha256=outside)


def ranges(before: bytes, after: bytes, scopes):
    merged = []
    for start, end, label in sorted(scopes):
        if merged and start < merged[-1][1]:
            if end <= merged[-1][1] and merged[-1][2] == label:
                continue
            raise ValueError(f'Overlapping repair scopes: {merged[-1]} and {(start, end, label)}')
        merged.append((start, end, label))
    old_out, new_out, cursor, rows = hashlib.sha256(), hashlib.sha256(), 0, []
    for start, end, label in merged:
        old_out.update(before[cursor:start])
        new_out.update(after[cursor:start])
        rows.append(dict(offset=hex(start), size=end - start, label=label,
                         before_sha256=sha(before[start:end]), after_sha256=sha(after[start:end])))
        cursor = end
    old_out.update(before[cursor:])
    new_out.update(after[cursor:])
    if len(before) != len(after) or old_out.digest() != new_out.digest():
        raise ValueError('Unexpected byte outside the declared defense scopes')
    return rows, old_out.hexdigest()


def repair_resource(payload: bytes, entry_id: int, *, image: Path = RETAIL_IMAGE, offense: Path | None = None,
                    defense: Path | None = None, expected_input_sha256: str | None = None):
    team = team_of(entry_id)
    offense = offense or default_offense(team)
    defense = defense or default_defense(team)
    off_sha, def_sha = sha(offense.read_bytes()), sha(defense.read_bytes())
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else dict(books={})
    stacks = [r for r in manifest['books'].get(str(entry_id), [])
              if r['offense_pack_sha256'] == off_sha and r['defense_pack_sha256'] == def_sha]
    before = sha(payload)
    accepted = {expected_input_sha256} if expected_input_sha256 else (
        {r['input_sha256'] for r in stacks} | {r['output_sha256'] for r in stacks})
    if before not in accepted:
        raise ValueError('Unexpected PLAY input SHA256 for these offense/defense packs '
                         '(pass --expected-input-sha256 for a new stacked input)')
    source, ref, pack = reference(team, entry_id, image, offense, defense)
    result, receipt = transform(payload, source, ref, pack)
    known = [r for r in stacks if before in (r['input_sha256'], r['output_sha256'])]
    if known and sha(result) != known[0]['output_sha256']:
        raise ValueError('Known PLAY repair output SHA256 mismatch')
    receipt.update(schema=SCHEMA, disc_file='media/pack0.bin', pack0_entry_id=entry_id, book=team, size=len(payload),
                   offense_pack=str(offense.relative_to(ROOT)) if offense.is_relative_to(ROOT) else str(offense),
                   offense_pack_sha256=off_sha,
                   defense_pack=str(defense.relative_to(ROOT)) if defense.is_relative_to(ROOT) else str(defense),
                   defense_pack_sha256=def_sha,
                   before_sha256=before, after_sha256=sha(result),
                   status='applied' if result != payload else 'already_applied',
                   changed_bytes=sum(a != b for a, b in zip(payload, result)), outside_scope_identical=True,
                   gameplay='unwitnessed')
    return result, receipt


def build_manifest(disc: Path, stack: str, *, image: Path = RETAIL_IMAGE, offense_dir: Path | None = None,
                   out_dir: Path | None = None) -> dict:
    """Run the repair on every team entry of a disc (read-only) and pin input/output hashes for these packs."""
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    import contextlib
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else dict(schema=SCHEMA + '.manifest', books={})
    # `disc` is a disc image (v0.5 or later) or a directory of <entry id>.play inputs (e.g. job p48o's repair output)
    context = contextlib.nullcontext(None) if disc.is_dir() else OuterImage(disc)
    with context as img:
        for team in pk.TEAM_BOOKS:
            entry = BOOK_ENTRIES[team]
            payload = (disc / f'{entry}.play').read_bytes() if img is None else img.read_entry(entry)
            offense = (offense_dir / default_offense(team).name) if offense_dir else default_offense(team)
            result, receipt = repair_resource(payload, entry, image=image, offense=offense,
                                              expected_input_sha256=sha(payload))
            again, _ = repair_resource(result, entry, image=image, offense=offense, expected_input_sha256=sha(result))
            if again != result:
                raise ValueError(f'{team}: repair is not idempotent')
            rows = [r for r in manifest['books'].get(str(entry), []) if r.get('stack') != stack]
            rows.append(dict(stack=stack, book=team, input_sha256=receipt['before_sha256'],
                             output_sha256=receipt['after_sha256'], offense_pack_sha256=receipt['offense_pack_sha256'],
                             defense_pack_sha256=receipt['defense_pack_sha256'], node_count=receipt['new_node_count'],
                             changed_bytes=receipt['changed_bytes'], scopes=len(receipt['scopes'])))
            manifest['books'][str(entry)] = rows
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f'{team}.play').write_bytes(result)
                (out_dir / f'{team}.receipt.json').write_text(json.dumps(receipt, indent=1) + '\n', newline='\n')
            print(team, receipt['status'], receipt['new_node_count'], receipt['changed_bytes'], flush=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1) + '\n', newline='\n')
    return manifest


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '--build-manifest':
        mp = argparse.ArgumentParser(prog='p48d_repair.py --build-manifest')
        mp.add_argument('--build-manifest', dest='disc', type=Path, required=True,
                        help='disc image, or a directory of <entry id>.play inputs')
        mp.add_argument('--stack', required=True)
        mp.add_argument('--retail-image', type=Path, default=RETAIL_IMAGE)
        mp.add_argument('--offense-dir', type=Path)
        mp.add_argument('--out-dir', type=Path)
        a = mp.parse_args(argv)
        build_manifest(a.disc, a.stack, image=a.retail_image, offense_dir=a.offense_dir, out_dir=a.out_dir)
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--entry-id', required=True, type=int)
    ap.add_argument('--receipt', required=True, type=Path)
    ap.add_argument('--retail-image', type=Path, default=RETAIL_IMAGE)
    ap.add_argument('--offense-pack', type=Path)
    ap.add_argument('--defense-pack', type=Path)
    ap.add_argument('--expected-input-sha256')
    args = ap.parse_args(argv)
    if args.source.is_symlink() or not args.source.is_file():
        ap.error('Source must be a regular non-symlink extracted PLAY resource')
    if (args.output.exists() or args.output.is_symlink() or args.receipt.exists() or args.receipt.is_symlink()
            or args.output.absolute() == args.receipt.absolute()):
        ap.error('Choose distinct new output and receipt paths')
    with args.source.open('rb') as stream:
        payload = stream.read(H + ip.BODY_SIZE + 1)
    try:
        result, receipt = repair_resource(payload, args.entry_id, image=args.retail_image, offense=args.offense_pack,
                                          defense=args.defense_pack, expected_input_sha256=args.expected_input_sha256)
    except (ValueError, KeyError) as exc:
        ap.error(str(exc))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(result)
    with args.receipt.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: receipt[k] for k in ('status', 'before_sha256', 'after_sha256', 'changed_bytes',
                                               'old_node_count', 'new_node_count')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())

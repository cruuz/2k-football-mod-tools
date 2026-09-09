"""Retail PLAY rule bundles and maintainable, offline editor reference.

Only selectors and research explanations ship with the library. Assignment
bytes are extracted from the user's loaded resource, with every flag retained.
No runtime patch, network access or whole-pack read is part of this module.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Sequence

from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from .errors import ValidationError
from .nfl2k5_playbook_inspector import BODY_SIZE, Nfl2k5Playbook

REFERENCE_PATH = Path(__file__).resolve().parents[2] / 'docs/mod_editor/play_rules.json'
EVIDENCE = 'EXPERIMENTAL / UNWITNESSED'
RUNTIME_NOTICE = ('Runtime target selection, double-team decisions, protection slides and '
                  'receiver pickup are not authorable as new rules here. Copied instructions '
                  'still use the game\'s existing AI. No gameplay result is proved.')


@lru_cache(maxsize=1)
def _reference() -> dict:
    data = json.loads(REFERENCE_PATH.read_text(encoding='utf-8'))
    if data.get('schema') != 'nfl2k5_play_rules/v1':
        raise ValidationError('Unsupported play rules reference version.')
    if [r['opcode'] for r in data['opcodes']] != list(range(codec.OPCODE_COUNT)):
        raise ValidationError('The play rules reference must cover all 29 opcodes.')
    return data


def reference() -> dict:
    """Fresh structured reference; parameter schemas follow the actual codec."""
    data = deepcopy(_reference())
    for row in data['opcodes']:
        op = row['opcode']
        row['name'] = codec.OPCODE_NAMES[op]
        row['parameters'] = [dict(key=s.key, kind=s.kind, bits=s.bits,
                                  label=s.label, choices=dict(s.choices or {}))
                             for s in codec.OPERAND_SCHEMAS[op]]
    return data


def describe_node(raw: bytes) -> str:
    node = codec.Node.from_bytes(raw)
    text = node.describe()
    if node.op == 0x11 and node.operands[0] == 9:
        # These two fields are table indices, not coordinates in centimetres.
        text = (f'Move to named spot: X table index {int(node.operands[5])}, '
                f'Y table index {int(node.operands[6])}; flags=0x{node.flags:02x}')
    meaning = _reference()['opcodes'][node.op]['meaning']
    return text + '. ' + meaning


@dataclass(frozen=True)
class RuleBundle:
    label: str
    source_asset_id: str
    source_body_sha256: str
    formation_index: int
    play_index: int
    play_flags: int
    position_codes: tuple[int, ...]
    slots: tuple[int, ...]
    raw_chains: tuple[tuple[bytes, ...], ...]

    def chains(self) -> list:
        return [[(n.op, list(n.operands), n.flags)
                 for n in map(codec.Node.from_bytes, chain)] for chain in self.raw_chains]


@dataclass
class RuleApplication:
    chains: list
    source_slots: tuple[int, ...]
    target_slots: tuple[int, ...]
    mapping: dict[int, int]
    play_flags: int
    donor_play_index: int
    label: str
    notes: tuple[str, ...]
    source_asset_id: str
    source_body_sha256: str
    source_formation_index: int
    source_play_index: int


def _indices(book: Nfl2k5Playbook, body: bytes, formation: int, play: int,
             *, require_link: bool = True) -> None:
    if len(body) != BODY_SIZE:
        raise ValidationError('Rules require one complete PLAY body, not an archive pack.')
    if type(formation) is not int or not 0 <= formation < len(book.formations):
        raise ValidationError('Choose a source formation in this book.')
    if type(play) is not int or not 0 <= play < len(book.plays):
        raise ValidationError('Choose a source play in this book.')
    if require_link and play not in {l.play_index for l in book.formations[formation].play_links}:
        raise ValidationError('The rule play must belong to its source formation.')
    flags, chains = lib.play_chains(body, play)
    if flags != book.plays[play].flags_or_id or any(
            desc != a.descriptor_word or raws != [bytes.fromhex(n.raw_hex)
                for n in book.assignment_chain(a).nodes]
            for (desc, raws), a in zip(chains, book.plays[play].assignments)):
        raise ValidationError('The loaded playbook and its source bytes do not match.')


def friendly_operand(op: int, values: Sequence) -> int | None:
    """Operand index in the friendly-slot namespace, never a receiver selector."""
    if op in (0x02, 0x13, 0x14):
        return 0
    if op in (0x15, 0x18) and values[0] == 2:
        return 5
    if op == 0x1A and values[5] == 0:
        return 3
    if op == 0x0E and (values[4] or values[6] or values[7]):
        return 5
    return None


def coupled_slots(chains: Sequence, slots: Sequence[int]) -> tuple[int, ...]:
    """Close both directions over transfers, exchanges and decision links.

    Snapping to a quarterback does not require copying his whole play. Other
    friendly dependencies retain their complete participating source chains.
    """
    chosen = set(slots)
    edges = []
    for slot, chain in enumerate(chains):
        for row in chain:
            op, values = row[:2]
            index = friendly_operand(op, values)
            if index is not None and op != 0x02:
                target = int(values[index])
                if not 0 <= target < 11:
                    raise ValidationError('Rule dependency names an invalid friendly slot.')
                edges.append({slot, target})
    while True:
        expanded = chosen | set().union(*(e for e in edges if e & chosen))
        if expanded == chosen:
            return tuple(sorted(chosen))
        chosen = expanded


def extract_bundle(book: Nfl2k5Playbook, body: bytes, formation: int, play: int,
                   *, scope: str = 'all', slots: Sequence[int] | None = None,
                   label: str | None = None) -> RuleBundle:
    _indices(book, body, formation, play)
    codes = tuple(lib.category_positions(body, lib.formation_category(body, formation)))
    try:
        chains = lib.exact_play_chains(body, play)
        flags, raw = lib.play_chains(body, play)
        error = codec.validate_play(flags, raw)
        codec.validate_sync(raw)
        if error:
            raise ValueError(error)
    except ValueError as exc:
        raise ValidationError(f'The source rules cannot be copied exactly: {exc}') from exc
    automatic = slots is None
    if automatic:
        if scope == 'all':
            slots = range(11)
        elif scope == 'line':
            slots = [s for s, c in enumerate(codes) if c & 31 in lib.OL_KINDS]
        elif scope == 'active' and book.plays[play].family_id == 1:
            slots = sorted(lib.defense_active(chains))
        else:
            raise ValidationError('Choose all assignments, offensive line, or active defense.')
    slots = tuple(slots)
    if (not slots or any(type(s) is not int or not 0 <= s < 11 for s in slots)
            or len(set(slots)) != len(slots)):
        raise ValidationError('Choose distinct assignment slots from 0 through 10.')
    closed = coupled_slots(chains, slots)
    if automatic:
        slots = closed
    elif set(slots) != set(closed):
        missing = ', '.join(str(s) for s in closed if s not in slots)
        raise ValidationError('Copy these linked players together; also select slots ' + missing + '.')
    return RuleBundle(label or book.plays[play].name, book.asset_id,
                      hashlib.sha256(body).hexdigest(), formation, play, flags,
                      codes, tuple(sorted(slots)), tuple(tuple(nodes) for _, nodes in raw))


def apply_bundle(bundle: RuleBundle, book: Nfl2k5Playbook, body: bytes,
                 formation: int, donor_play: int, *, chains: Sequence | None = None,
                 position_codes: Sequence[int] | None = None,
                 play_flags: int | None = None) -> RuleApplication:
    """Copy per-position chains onto a compatible formation and validate all 11.

    Names are no authority for remapping. Match exact native position/ordinal
    codes, preserve opponent selectors and refuse missing/ambiguous personnel.
    A partial defensive bundle must keep the donor's front/coverage component.
    """
    _indices(book, body, formation, donor_play, require_link=False)
    if (bundle.source_asset_id != book.asset_id or
            bundle.source_body_sha256 != hashlib.sha256(body).hexdigest()):
        raise ValidationError('Re-extract rules from the currently loaded book before applying them.')
    source_family = (bundle.play_flags >> 6) & 7
    donor_flags, donor = lib.play_chains(body, donor_play)
    flags = donor_flags if play_flags is None else play_flags
    if source_family != ((flags >> 6) & 7):
        raise ValidationError('Offense, defense and special teams need matching rule families.')
    formation_type = lib.formation_record(body, formation).type_code
    if ((source_family == 0 and formation_type >= 4) or
            (source_family == 1 and not 4 <= formation_type <= 7)):
        raise ValidationError('These rules need a formation in the same play family.')
    if source_family == 0 and ((flags ^ bundle.play_flags) &
                              (lib.PLAY_CLASS_MASK | lib.PLAY_FLAG_PLAY_ACTION)):
        raise ValidationError('Choose a donor with the same run, pass or play-action class as these rules.')
    target_codes = list(position_codes) if position_codes is not None else lib.category_positions(
        body, lib.formation_category(body, formation))
    if len(target_codes) != 11 or any(type(c) is not int or not 0 <= c <= 255 for c in target_codes):
        raise ValidationError('A target formation needs eleven native position codes.')
    source = bundle.chains()
    needed = set(bundle.slots)
    for s in bundle.slots:
        for op, values, _ in source[s]:
            index = friendly_operand(op, values)
            if index is not None:
                needed.add(int(values[index]))
    mapping = {}
    for slot in sorted(needed):
        matches = [s for s, code in enumerate(target_codes) if code == bundle.position_codes[slot]]
        if len(matches) != 1:
            raise ValidationError(f'Rules need one {codec.position_label(bundle.position_codes[slot])} '
                                  f'for source slot {slot}; this formation has {len(matches)}.')
        mapping[slot] = matches[0]
    if len(set(mapping.values())) != len(mapping):
        raise ValidationError('Ambiguous source personnel cannot be assigned to one target slot.')
    result = deepcopy(chains) if chains is not None else lib.exact_play_chains(body, donor_play)
    if len(result) != 11:
        raise ValidationError('The target play must have eleven assignments.')
    before_component = lib.defense_component(result) if source_family == 1 else None
    for s in bundle.slots:
        fresh = deepcopy(source[s])
        for op, values, _ in fresh:
            index = friendly_operand(op, values)
            if index is not None:
                values[index] = mapping[int(values[index])]
        result[mapping[s]] = fresh
    if source_family == 1 and lib.defense_component(result) != before_component:
        raise ValidationError('These rules change the front/coverage split. Choose the matching component.')
    # Reject an existing paired script being cut in half by a partial overwrite.
    base = chains if chains is not None else lib.exact_play_chains(body, donor_play)
    targets = tuple(sorted(mapping[s] for s in bundle.slots))
    if set(coupled_slots(base, targets)) != set(targets):
        raise ValidationError('These rules would split an existing linked assignment. Copy the whole pair.')
    try:
        error = lib.validate_chains(flags, donor, result)
        if error:
            raise ValueError(error)
    except (ValueError, TypeError, IndexError) as exc:
        raise ValidationError(f'The combined rules failed the play validator: {exc}') from exc
    return RuleApplication(result, bundle.slots, targets, mapping, flags, donor_play,
                           bundle.label, (EVIDENCE, RUNTIME_NOTICE,
                            'Position codes are matched exactly; formation geometry stays as authored.'),
                           bundle.source_asset_id, bundle.source_body_sha256,
                           bundle.formation_index, bundle.play_index)


def compile_application(raw_resource: bytes, book: Nfl2k5Playbook,
                        application: RuleApplication, *, custom_name: str | None = None,
                        replace_index: int | None = None):
    """Compile with ordinary PLAY guards, exact receipts and no-op support."""
    from . import nfl2k5_formation_play_writer as writer
    if (book.asset_id != application.source_asset_id or
            hashlib.sha256(raw_resource[32:]).hexdigest() != application.source_body_sha256):
        raise ValidationError('The rules source changed before compilation. Re-extract from the current book.')
    request = writer.rule_play_request(book.asset_id, raw_resource[32:],
        application.donor_play_index, application.chains, custom_name=custom_name,
        replace_index=replace_index, play_flags=application.play_flags)
    compiled = writer.compile_formation_play_creations(raw_resource, play_requests=(request,),
                                                       allow_unchanged=True)
    compiled.report['rules'] = dict(label=application.label,
        source_asset_id=application.source_asset_id,
        source_body_sha256=application.source_body_sha256,
        source_formation=application.source_formation_index, source_play=application.source_play_index,
        source_slots=list(application.source_slots), target_slots=list(application.target_slots),
        slot_mapping=dict(application.mapping), evidence=EVIDENCE, gameplay_witnessed=False,
        runtime_behavior_authored=False, reused_slots=[s for s, c in enumerate(request.assignments) if c is None])
    return compiled


def catalog(book: Nfl2k5Playbook, body: bytes) -> list[dict]:
    """Resolve named presets by exact retail names in the loaded book."""
    rows = []
    for preset in _reference()['presets']:
        matches = [p for p in book.plays if p.name in preset['names'] and p.family_id == preset['family']]
        for play in matches:
            for form in book.formations:
                if any(l.play_index == play.index for l in form.play_links):
                    rows.append(dict(preset=preset['id'], label=preset['label'],
                                     play=play.index, play_name=play.name,
                                     formation=form.index, formation_name=form.name,
                                     scope=preset['scope'], note=preset['note']))
    from .nfl2k5_match_coverage import rule_catalog
    rows.extend(rule_catalog(book, body))
    return rows


def inspect_play(book: Nfl2k5Playbook, body: bytes, play: int,
                 formation: int | None = None) -> dict:
    """Complete decoded chain viewer, including plays without a menu link."""
    if len(body) != BODY_SIZE:
        raise ValidationError('Inspect one PLAY body at a time.')
    rows = book.decoded_play(play)
    _indices(book, body, 0, play, require_link=False)
    codes = None
    if formation is not None:
        _indices(book, body, formation, play)
        codes = lib.category_positions(body, lib.formation_category(body, formation))
    for row in rows:
        row['position'] = codec.position_label(codes[row['slot']]) if codes else 'slot ' + str(row['slot'])
        for node in row['nodes']:
            raw = bytes.fromhex(node['raw'])
            node['description'] = describe_node(raw)
            node['operands'] = codec.Node.from_bytes(raw).operands
    return dict(book=book.book_name, play=play, name=book.plays[play].name,
                family=book.plays[play].family_label, formation=formation,
                body_sha256=hashlib.sha256(body).hexdigest(), evidence=EVIDENCE,
                runtime_note=RUNTIME_NOTICE, assignments=rows)


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('reference', 'catalog', 'inspect'))
    parser.add_argument('--image', type=Path, help='Read-only retail extracted tree or XISO')
    parser.add_argument('--book', default='ATL')
    parser.add_argument('--play', type=int)
    parser.add_argument('--formation', type=int)
    args = parser.parse_args(argv)
    if args.command == 'reference':
        result = reference()
    else:
        if args.image is None:
            parser.error('--image is required for retail rules')
        # This existing reader seeks only the selected 78,768-byte resource.
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        from .nfl2k5_playbook_inspector import parse_playbook_resource
        if args.book not in BOOK_ENTRIES:
            parser.error('Unknown retail book')
        with OuterImage(args.image) as archive:
            raw = archive.read_entry(BOOK_ENTRIES[args.book])
        book = parse_playbook_resource(raw, asset_id='book:' + args.book)
        if args.command == 'catalog':
            result = catalog(book, raw[32:])
        else:
            if args.play is None:
                parser.error('--play is required for inspect')
            result = inspect_play(book, raw[32:], args.play, args.formation)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

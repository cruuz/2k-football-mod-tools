"""Explicit fixed-span press alignment for a selected three-deep PLAY pair.

EXPERIMENTAL / UNWITNESSED. Runtime nfl2k5_deep_zone must also enable bail.
No names identify coverage. The existing formation/play compiler owns cloning,
relative pointers, shared-node isolation, fixed resource span and validation.
"""
from __future__ import annotations

import hashlib

from . import nfl2k5_play_codec as codec, nfl2k5_play_library as lib
from .nfl2k5_formation_play_writer import PlayCreateRequest, compile_formation_play_creations
from .nfl2k5_playbook_inspector import parse_playbook_resource
from .nfl2k5_playbook_pack import RESOURCE_SIZE


def apply(resource: bytes, *, formation_index: int, front_play_index: int,
          coverage_play_index: int, asset_id: str = "deep-zone-bail") -> tuple[bytes, dict]:
    """Replace only selected coverage CB chains; repeated application is exact.

The authoring candidate requires a complete native-personnel split-call pair,
three >=18-yard terminal zone assignments, two of them CBs, and no other deep
assignments. Runtime independently requires exactly three native bit-8 records.
The selected coverage row remains shared by its existing formation links.
"""
    if not isinstance(resource, bytes) or len(resource) != RESOURCE_SIZE:
        raise ValueError("Press bail requires one fixed-size PLAY resource")
    if any(type(v) is not int or v < 0 for v in (formation_index, front_play_index, coverage_play_index)):
        raise ValueError("Choose nonnegative formation, front and coverage indices")
    book = parse_playbook_resource(resource, asset_id=asset_id)
    body = resource[32:]
    if (front_play_index, coverage_play_index) not in lib.defense_pairs(book, body, formation_index):
        raise ValueError("Choose a complete native defensive front/coverage pair")
    personnel = lib.defense_personnel(book, body, formation_index)
    front = lib.exact_play_chains(body, front_play_index)
    coverage = lib.exact_play_chains(body, coverage_play_index)
    effective = lib.effective_defense(front, coverage)
    active = lib.defense_active(coverage)
    deep = [s for s, chain in enumerate(effective)
            if chain and chain[-1][0] == 0x0D and chain[-1][1][1] >= 18*codec.YD_CM-.001]
    shallow_deep = [s for s, chain in enumerate(effective)
                    if chain and chain[-1][0] == 0x0D and 15*codec.YD_CM-.001 <= chain[-1][1][1] < 18*codec.YD_CM-.001]
    corners = [s for s in deep if personnel["codes"][s] & 31 == 18]
    if len(deep) != 3 or len(corners) != 2 or shallow_deep or not set(corners) <= active:
        raise ValueError("Press bail requires exactly three deep zones with both coverage-row corners")
    formation = lib.formation_record(body, formation_index)
    users = [f.index for f in book.formations
             if any(p.index == coverage_play_index for p in book.plays_for_formation(f.index))]
    for fi in users:
        other = lib.formation_record(body, fi)
        if any(other.slots[slot].x[0] != formation.slots[slot].x[0] for slot in corners):
            raise ValueError("Coverage row has different formation lanes; clone the row before press authoring")
    authored, changes = [None]*11, []
    for slot in corners:
        chain = coverage[slot]
        if [n[0] for n in chain] != [0x1B, 0x0D]:
            raise ValueError("Press bail requires plain Defense Start then Zone corner chains")
        op, values, flags = chain[0]
        # Mode 1 anchors at the LOS, with retail 183F60 supplying its legal
        # player-scaled minimum. X stays in the formation's physical lane.
        values = list(values)
        values[0], values[2], values[3] = 1, formation.slots[slot].x[0], 0
        # The authored API encodes physical operands while preserving mirror
        # flags; normalize through its exact codec round trip before comparison.
        target = (op, values, flags)
        replacement = [target, chain[1]]
        packed = [n.to_bytes() for n in codec.encode_chain(replacement)]
        old = lib.play_chains(body, coverage_play_index)[1][slot][1]
        if packed != old:
            authored[slot] = tuple(replacement)
            changes.append(dict(slot=slot, before=[b.hex() for b in old],
                                after=[b.hex() for b in packed]))
    common = dict(owner="nfl2k5_deep_zone_bail", experimental=True, runtime_witnessed=False,
                  formation_index=formation_index, front_play_index=front_play_index,
                  coverage_play_index=coverage_play_index, affected_formations=users, corner_slots=corners, deep_slots=deep,
                  alignment="LOS anchored; native legal minimum; original formation lane",
                  requires_runtime_bail=True, source_sha256=hashlib.sha256(resource).hexdigest())
    if not changes:
        return resource, dict(status="already_applied", changed_bytes=0, edits=[], **common)
    request = PlayCreateRequest(asset_id, coverage_play_index,
                                assignments=tuple(authored), replace_index=coverage_play_index)
    compiled = compile_formation_play_creations(resource, play_requests=(request,))
    final = compiled.replacement
    if len(final) != len(resource):
        raise ValueError("Press bail compiler changed the fixed PLAY span")
    after = lib.play_chains(final[32:], coverage_play_index)[1]
    before = lib.play_chains(body, coverage_play_index)[1]
    for slot in range(11):
        if slot not in corners and before[slot] != after[slot]:
            raise ValueError("Press bail compiler changed an unselected assignment")
    return final, dict(status="applied", changed_bytes=compiled.changed_byte_count,
                       edits=changes, result_sha256=hashlib.sha256(final).hexdigest(),
                       compiler=compiled.report, **common)


def main(argv=None):
    """Bounded copy writer; explicit pair selection and a new output only."""
    import argparse
    import json
    from pathlib import Path
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('resource',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--formation',type=int,required=True)
    parser.add_argument('--front',type=int,required=True)
    parser.add_argument('--coverage',type=int,required=True)
    args=parser.parse_args(argv)
    try:
        with args.resource.open('rb') as stream:raw=stream.read(RESOURCE_SIZE+1)
        result,receipt=apply(raw,formation_index=args.formation,front_play_index=args.front,
                             coverage_play_index=args.coverage)
        created=False
        try:
            with args.output.open('xb') as stream:
                created=True
                stream.write(result)
        except BaseException:
            if created:args.output.unlink(missing_ok=True)
            raise
        print(json.dumps(receipt,indent=2))
        return 0
    except (ValueError,OSError) as exc:
        print(f'Press bail refused: {exc}',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())

# Play Editor timeboxed findings

Status: six-hour spike stopped early with a partial structural result; visual
route authoring remains Coming Soon  
Date: 2026-07-18

## Shipping decision

The v1.0 Playbooks & Plays tab ships as a viewer/inspector, not a route-drawing
editor. The spike materially improved the inspector model, but it did not
recover enough coordinate, opcode, slot-role, and write-back semantics to let a
user draw a route and save it safely.

This is a deliberate product boundary rather than a hidden unfinished feature.
Every `PLAY` resource remains browsable and exportable. The structured viewer
can show books, formations, play names, play families, eleven player slots,
complete raw node chains, and every still-unknown field. Replace/Import stays
disabled with the findings below visible in the tab.

## Newly recovered structure

The complete NFL corpus contains 37 fixed-size `PLAY` books, 1,533 formation
records, 9,251 play records, 835 category records, 91,833 eight-byte nodes, and
101,761 player-slot references.

### Complete stock node-chain segmentation

Taking the union of all eleven slot pointers in each book yields 32,502 unique
node-chain starts. In every book the first start is node zero. Sorting those
starts and using the next start as the candidate boundary partitions every one
of the 91,833 nodes exactly, with no uncovered node, overlap, or padding:

| Nodes in chain | Unique chains |
| ---: | ---: |
| 2 | 14,903 |
| 3 | 9,342 |
| 4 | 7,317 |
| 5 | 910 |
| 6 | 27 |
| 7 | 3 |
| **Total** | **32,502 chains / 91,833 nodes** |

All chain starts use only three first-byte opcodes:

- `0x01`: 18,467 chains;
- `0x1A`: 433 chains; and
- `0x1B`: 13,602 chains.

All first nodes have zero in the low three bits of byte one. Every candidate
last node has bit one set in byte one. Those invariants support the partition,
as does the exact whole-corpus coverage. They are sufficient for a read-only
chain inspector, but not yet sufficient to claim a general linked-list grammar
or a safe compiler.

The complete opcode census is `0x01` through `0x1B` with `0x05` and `0x07`
present only in the specialized field-goal/punt families. The first node,
intermediate node, and last node byte patterns are retained exactly in the
viewer. No opcode receives an invented football-action name.

### Exact play-family field

Executable consumers already isolate bits 6 through 8 of the play word at
`+0x04`. Exhaustive name grouping across all 9,251 records closes its eight
observed values:

| Value | Family | Play records | Corpus examples |
| ---: | --- | ---: | --- |
| 0 | Offense | 5,307 | `Strong Iso`, `50 Double Cross`, `QB Sneak` |
| 1 | Defense | 3,332 | `Cover 3`, `2 Man`, zone blitz families |
| 2 | Punt | 36 | `Punt` |
| 3 | Punt return/defense | 180 | `PR Left`, `PR Middle`, `Punt Block` |
| 4 | Field goal | 36 | `Field Goal` |
| 5 | Field-goal defense | 72 | `FG Block`, `FG Defend` |
| 6 | Kickoff | 144 | left/middle/right and onside kick |
| 7 | Kickoff return | 144 | left/middle/right and onside return |

These counts cover all 9,251 plays exactly. The viewer may safely use these
family names while continuing to expose the complete original word.

### Formation-to-play membership

Each active formation has a parallel `0x50`-byte auxiliary record. Executable
consumers prove that its first 36 little-endian `u16` entries are play slots.
The low nine bits select a play index; `0x1FF` is empty. Bits 9 and 10 form the
observed three-way grouping used by the selection code, with value 3 used as an
unassigned/fallback group. The last eight bytes and remaining high bits stay
raw because their narrower meanings are not proved.

This is enough to organize the inspector as book -> formation -> grouped play
slots -> play -> eleven player assignments -> node chain.

## Why visual authoring did not unlock

The prerequisite differential fixtures do not exist locally. The available
corpus contains stock disc playbooks, not multiple game-created custom plays
that differ by exactly one moved waypoint, route type, formation position, or
player assignment. Custom-play save ownership is also not established.

The following semantic gaps remain blocking:

- the eleven player roles/order for every offensive, defensive, and special-
  teams formation;
- formation-coordinate fields, sign, scale, axis orientation, origin, and
  relationship to the line of scrimmage;
- the meaning and operand layout of node opcodes `0x01..0x1B`;
- which node operands are coordinates, timing, route style, action type,
  branch conditions, blocking targets, coverage targets, motion, or flags;
- whether the corpus-derived next-start boundary is also the runtime grammar
  for newly authored chains;
- validation rules shared by the `0xB4` formation record, `0x50` auxiliary
  record, play descriptor bits, node chains, and the nonzero post-node region;
- ownership, integrity, precedence, and serialization of user-created plays in
  Xbox saves; and
- a format-preserving inverse compiler plus a runtime proof that an edited
  assignment executes as drawn.

Without those items, a field canvas would be decorative guesswork and a writer
could silently turn a route into a block, coverage assignment, invalid target,
or corrupt play. The safe v1.0 outcome is therefore the inspector.

## Best next spike

Create four controlled game-authored fixtures on an isolated headless xemu
profile: one receiver moved only along field X, the same receiver moved only
along field Y, one route waypoint added without moving the endpoints, and one
route type changed without moving any point. Preserve the clean profile and
diff the exact custom-play save/container after each edit.

Correlate changed records against the known descriptor and chain layouts, then
place runtime read watchpoints on those bytes while the selected play is drawn
in the play-call UI and executed on field. A field becomes authorable only when
both the orthogonal fixture diffs and the runtime consumer agree on its meaning.

## Retail-data boundary

The release contains parser code and schema/status metadata only. It does not
contain any stock playbook body, route node, formation record, play name, or
other decoded retail payload. A user's private cache supplies the viewer at
runtime. Shareable projects cannot contain raw stock `PLAY` resources.

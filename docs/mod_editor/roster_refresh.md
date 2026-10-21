# Dated roster refreshes

The optional `roster_refresh` key of a roster-edits document carries a
`nfl2k5.roster_refresh.v1` plan. It is specific to the 2619-primary-player,
modern-position disc roster. It does not migrate franchise saves.

The build defers this directive until after the original roster and history
imports, historic rosters, player tags and quarterback throw-power adjustment.
The standalone roster writer also accepts a refresh-only document. This lets
the repair tool use the same final writer on an already-built disc.

Existing players retain their primary indices, ratings, names, history pointers,
appearance, stars and abilities. Their permitted changes are jersey, position,
depth rank, depth side, membership and the five depth-preference bits. Number
commentary is repaired by the normal roster writer. All other roster bytes,
including coach and history tables, remain outside the refresh's ownership.
Two guarded initialization exceptions apply: unused CAP records need exclusive
adjacent name buffers, and unsigned records moved into NFL ownership need valid
native contract terms. Existing nonzero contracts are never replaced.

Plans identify existing records by index, first name, last name and date of
birth, and carry source identifiers and URLs. Membership includes all 32 clubs,
42 to 53 active players per club, up to 12 reserves, specialists, and a free-agent
list. New identities may use only vacant create slots starting at 2464 and must
provide model ratings. They start with zero history and ability state. Their
ratings must already include the pack's desired final adjustments because the
refresh runs after those adjustments. Replay changes only permitted roster
fields, preserving subsequent ratings and appearance work.
Every owned record needs a nonzero contract length because native IR payroll
divides by that length. A `contract_initializations` row may supply the five
contract fields for an otherwise empty unsigned record, with a source URL and
modeling rule. Replay preserves a nonzero contract. The dated October 14 H-back
stage uses the existing economy minimum model for these accounting placeholders;
they are explicitly distinguished from observed NFL contracts.

All active depth chains are locked. NFL clubs are checked for conflicting
locks; alumni teams alias the same player records and cannot have independent
rank locks. A player missing from a dated chart needs an explicit authoring
fallback. A generic portrait must be identified as such, never as a likeness.

## Offline repair

`tools/b77/ro1_repair.py --disc INPUT --plan refresh.json --receipt receipt.json
--virtual` reads the entire input and hashes a projected output without copying
or modifying a disc. Omit `--virtual` only when applying to an authorized copy.
The tool accepts the pinned October 13 base hash or a previous output hash with
`--prior-receipt`. It rejects a different plan on replay, uses fixed differing
runs inside ROST, checks Studio replay, and reports whole-image and outside-span
hashes. Actual writes also receive readback and whole-image verification.

Virtual proof does not demonstrate a live franchise, an actual write/replay, or
a complete retail-to-pack build. It proves the final roster stage on the pinned
installed baseline. A complete rebuild must still pass the identity guards.

## New-franchise future picks

The franchise initializer at `0x13EE10` initializes two banks of seven 32-byte
ownership arrays. Bank 0 is `0xE3C0B4..0xE3C193`; bank 1 is
`0xE3C194..0xE3C273`. Each byte starts as its original team index. The bank stride
is `0xE0`, and the round stride is `0x20`. Writing default executable data alone
cannot seed traded picks because initialization resets it.

The load routine expands the front-office save's fourteen 32-dword tables into
these byte arrays. At `0x31E430`, season transition copies bank 1 to bank 0 and
resets bank 1 to original ownership. `0x31E210` also reorders first-bank entries
with the draft-order permutation. No third future-year bank was established.

The optional `draft_pick_ownership` directive now installs an owned, guarded
hook immediately after the reset at `0x13EF89`. Its complete 448-row manifest
seeds the 2027 and 2028 drafts for a 2026 starting season. Conditional choices
must be explicitly frozen by the data author, with unconfirmed owners marked.
Native later trading and rollover stay intact. See
[draft_pick_ownership.md](draft_pick_ownership.md) for guards and native checks.
An existing-save upgrade could potentially write the front-office tables, but
would need to preserve user trades and the save's season and draft order. This
refresh does not implement an existing-save upgrade. Its `unrepresented`
manifest also records unsupported reserve status
and missing practice-squad identities; absence from active rosters does not
mean correctly seeded injured reserve.

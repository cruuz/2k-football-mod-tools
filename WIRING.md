# Beta-60 integration: experimental practice squads

These are the additions for Claude's protected files on the rebased beta-60
stack. They have deliberately not been applied here. The shipped behavior is
**53 active + up to 12 reserves**, with no native reserve screen. Do not label
this as 16 reserves or witnessed. BASIC/ADVANCED default off; EXPERIMENTAL on.
Off-season active capacity is `65 - reserve_count`; a full 53+12 roster must
release active players to add draft picks. Trades needing a temporary extra
slot are refused before changing ownership.

## Cave ownership after relocation

Dynamic kickoff retains `0x2890F0..0x289883` exclusively. Practice squads use
the following `(VA, capacity)` allocations (all executable code/constants):

```python
((0x374111, 651), (0x3BA610, 592), (0x3DCB20, 381), (0x3BABE0, 333),
 (0x3D1E20, 319), (0x3E1600, 225), (0x3E81B0, 158), (0x3EE0D0, 146),
 (0x2EAEE0, 143), (0x3D1610, 142), (0x2952B0, 140))
```

Reserve these complete capacities, including trailing NOP padding, when
regenerating `data/nfl2k5_cave_reservations.json` after integration. The supplied
manifest predates rebased source changes and omits kickoff; this branch leaves
it and the oracle's source-drift guard intact. The relocation audit uses
`ReservationManifest.load(..., source_root=None)` as permitted by the brief,
then checks existing reservations and the actual current stack bytes in the
cave gate. The oracle retains its `unknown` verdict for unresolved indirect
flow; no closed-world allocation proof is claimed. See
[AUDIT.md](tools/practice_squad/AUDIT.md) for exact evidence and limits.

Both XBE gates apply practice squads after `_apply_all(...,
dynamic_kickoff=True)`, `pools.apply(...)` and `rows.apply(...)`. The same
composition executes the bounded CPU season gate and save/reload. Preserve
that combination when wiring the option. Storage still uses 65 pointer fields
and only `+0x19B/+0x1F2/+0x1F3`; no save-format migration is required.

## `mod_editor/core/nfl2k5_throw_tuning.py`

Alongside the patch imports (near line 76), add:

```python
from . import nfl2k5_practice_squad as practice_squad_patch
```

Append this parameter to `_apply_all`, `write_xbe_copy`, and `write_image_copy`
(near lines 905, 1034, 1139), preserving existing positional parameter order:

```python
practice_squad: bool = False,
```

In both writers' `_require(wanted is not None or ...)` predicates, add
`or practice_squad`. In both calls to `_apply_all`, add
`practice_squad=practice_squad`. `write_copy` already forwards `**kwargs`.

Add this item to `_apply_all`'s `for flag, module, key, label in (...)` tuple
(near line 1000):

```python
(practice_squad, practice_squad_patch, "practice_squad_patch", "Practice squad"),
```

Add the following state entries beside `franchise_practice` in each dictionary;
the byte variable differs by function:

```python
# read_xbe and read_image (near lines 604 and 706)
"practice_squad": practice_squad_patch.status(payload),
# write_xbe_copy result (near line 1117)
"practice_squad": practice_squad_patch.status(result),
# write_image_copy result (near line 1283)
"practice_squad": practice_squad_patch.status(after),
```

The existing tuple loop already consumes `changed_bytes` and includes the
sub-receipt. No adapter is needed. Once integrated, both XBE gate tests can
pass `practice_squad=True` into `_apply_all` instead of the separate `ps.apply`
call added on this branch; retain coverage either way.

## `mod_editor/core/mod_build.py`

Add to `BuildPlan` beside `franchise_practice` (near line 154):

```python
# 53 active + up to 12 hidden reserves; zero reserve cap cost; unwitnessed.
practice_squad: bool = False
```

Add `or self.practice_squad` to `wants_xbe_patch`. The dataclass recipe
serialization needs no special handling. Add to the three preset dictionaries:

```python
# softdrink_basic
"practice_squad": False,
# softdrink_advanced
"practice_squad": False,
# softdrink_experimental
"practice_squad": True,
```

Add these dictionary entries at their existing counterparts:

```python
# available() (near line 274)
"practice_squad": _core_module("nfl2k5_practice_squad") is not None,
# inspect() (near line 323)
"practice_squad": report.get("practice_squad", "unknown"),
# build writer kwargs (near line 562)
"practice_squad": plan.practice_squad,
```

Add `"practice_squad"` to the XBE step receipt key tuple near line 568.

## GUI toggles

In `mod_editor/gui/gameplay_patches_panel_qt.py`, append to `PATCHES`:

```python
("practice_squad", "Practice squads: 53 active + up to 12 reserves (experimental)",
 "CPU season cuts keep up to 12 players as team-owned reserves. Reserves stay "
 "off the active roster and depth chart and do not affect the team rating. "
 "They survive saves and rollover, cost no salary cap space, and retain their "
 "existing contract terms. There is no in-game reserve screen or automatic "
 "promotion. Team import requires an empty destination. Unwitnessed in game."),
```

This is a boolean XBE toggle: no entry in `STRING_TOGGLES` or `NEEDS_IMAGE`.

In `mod_editor/gui/build_panel_qt.py`, beside the existing franchise practice
checkbox (near line 226), add:

```python
self.practice_squad_check = QCheckBox(
    "Practice squads: 53 active + up to 12 hidden reserves; zero reserve cap cost (experimental, unwitnessed)")
```

Add `self.practice_squad_check` to the checkbox layout tuple near line 229.
Add `("practice_squad", "practice squads")` to the inspected status-label
tuple near line 315. Add the following respective lines:

```python
# _refresh availability gates, beside franchise_practice (near line 369)
gate(self.practice_squad_check, "practice_squad")
# preset-to-widget dictionary (near line 399)
"practice_squad": self.practice_squad_check,
# BuildPlan construction (near line 461)
practice_squad=self.practice_squad_check.isChecked(),
```

Add `or p.practice_squad` to the plan-has-work predicate near line 473.

## Rosters API and count exposure

For the existing disc `RosterDocument`, add this import to
`mod_editor/gui/roster_editor_panel_qt.py`:

```python
from mod_editor.core import nfl2k5_practice_squad as ps
```

Inside `_populate_teams`, before the label assignment near line 927:

```python
reserve_count = len(ps.reserve_list(
    self.document.body[team.offset:team.offset + ps.TEAM_SIZE]))
```

Append `f" + {reserve_count} reserve"` to `label` when `reserve_count` is
nonzero. Catch `ps.PracticeSquadError` at the load boundary and display its
message; do not silently treat unknown metadata as an empty list.
Leave `team.slots` and `team.player_count` as the active list/count. The
existing `to_body()` preserves hidden slots when reordering active players.
Reserve identities should be a separate group if adding a selectable list.

For either a disc body or an entire version-0 save, these are complete API
examples with all coordinates in the same payload:

```python
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_practice_squad as ps

doc = codec.decode(payload)
team = doc.teams[team_index]
coords = dict(team_offset=team.offset,
              player_pool_offset=doc.tables["primary"].offset)
raw = payload[team.offset:team.offset + ps.TEAM_SIZE]
indices = ps.reserve_list(raw, **coords)
names = [doc.by_key["primary", i].first + " " +
         doc.by_key["primary", i].last for i in indices]

# Low-level storage writer, AFTER transferring active/FA/IR ownership:
replacement = ps.set_reserve_list(
    raw, new_reserve_indices, **coords,
    player_count=doc.tables["primary"].count)
candidate = bytearray(payload)
candidate[team.offset:team.offset + ps.TEAM_SIZE] = replacement
ps.validate_roster(bytes(candidate), ir_player_indices=ir_indices)
```

`reserve_list(raw)` without coordinates returns team-relative byte offsets,
not pool indices. Zero is a valid primary index; NULL pointer words are the
empty sentinel. `set_reserve_list` returns a copy and does not itself release,
sign, recalculate cap, or repair depth-chart indices. Do not implement a
promote/demote button by calling it alone. Runtime `ps_promote`/`ps_demote`
perform those transactions; their current fastcall entries are exported by
`nfl2k5_practice_squad_runtime.SYMBOLS` (ECX team, EDX player; EAX 1/0).

An external primary-pool reorder must update **all 65 pointer fields**. If
using an index map, `remap_reserve_list(raw, complete_old_to_new_map, **coords)`
refuses missing entries; `None` explicitly drops a retired identity. Preserve
the old coordinates until decoding old references, then encode against the
new pool/team positions. Never reinterpret an old index in the new pool.

For signed saves use `doc, container = codec.load_save(source)` and
`container.write(new_target, candidate)` after validation; this re-signs EXTRA
and retains the other members. IR is outside the ROST resource: supply its
indices from the franchise adapter for ownership-changing edits. No version
number substitution is valid. The copied codec is not a drop-in
`RosterDocument` GUI replacement; Claude's version-0 adapter must expose its
players/teams while preserving `doc.original` framing and suffix. Re-decode a
changed payload before further player edits so `to_bytes()` retains team edits.

No changes are required in `nfl2k5_position_pools.py` or
`nfl2k5_modern_positions.py`: active roster/depth-chart loops keep using
`+0x11C`. Do not expand those loops to include reserves.

## Packaging

Append these explicit paths to `packaging/release-allowlist.txt` (de-duplicate
the codec if Claude's version-0 work already added it):

```text
mod_editor/core/nfl2k5_practice_squad.py
mod_editor/core/nfl2k5_practice_squad_runtime.py
mod_editor/core/nfl2k5_save_rost.py
```

The generated Python payload is sufficient on Windows; GCC/binutils,
Unicorn, Capstone, private inputs, research tools and tests are development
dependencies, not runtime payload. Add the same three dotted module names to
the required-core import tuple in `packaging/check_2k5_mod_studio_runtime.py`
if extending that release check. Run the two XBE gates after integration,
then the normal release checks and repin. This branch changes no release tag,
update metadata, protected implementation or allowlist.

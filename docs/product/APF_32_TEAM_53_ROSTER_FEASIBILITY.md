# APF 2K8: 32-team and 53-player roster feasibility

Date: 2026-07-18  
Scope: US Xbox 360 retail APF 2K8, emulator-targeted modification, and APF 2K8 Mod Studio  
Status: product finding and staged implementation proposal; not a shipped roster-expansion capability

Product-boundary refresh: 2026-07-20

## Outcome

The two requested dimensions have very different difficulty levels:

| Target | Current classification | Practical meaning |
|---|---|---|
| 32 team identities in the roster database | **Structurally present** | The disc already has 40 team records and exactly 32 nonempty 42-player team rows. |
| 32 teams selectable in Play Now | **Plausible, runtime-unproved** | Rows 24-31 are populated online placeholders rather than ordinary built-in teams. Their list/category ownership must be mapped and patched before they can be claimed as eight additional offline teams. |
| 53 players represented for each of 32 teams | **Size-feasible; safe storage unresolved** | The player table is large enough, and a compact reserve representation fits the existing fixed ROST allocation. The original `team +0x120` placement is falsified because stock code owns its first seven bytes; stock APF also does not understand the representation. |
| 53 players simultaneously recognized by stock roster/depth-chart code | **Not possible as a data-only edit** | Every stock team record has only 42 contiguous membership pointers. True 53-player behavior requires version-pinned XEX changes to roster accessors and every direct consumer. |
| 32-team Play Now with 53-player master rosters and 42 active players | **Nearest achievable product** | Mod Studio can eventually retain 53 authored players per team and compile a selected 42-player active roster into the stock layout before launch. This avoids claiming that APF itself sees all 53 at once. |
| 32-team Season/franchise | **Major executable, schedule, UI, and save project** | Retained Season/franchise code contains 24-entry loops, while schedule tables, roster mutation, and save ownership remain incomplete. |

The defensible short answer is therefore:

> A 32-team APF conversion is plausible. A true 32-by-53 in-game roster system is also technically plausible on Xenia, but only as an engine patch with a new side-table contract. It is not a normal ROST edit and is not supported by the current product.

This note does not prove runtime success, authorize a public executable patch, or describe a working 32-team Season. It records the exact local evidence, a new bounded container-space experiment, and the smallest staged route that can falsify or advance the idea.

## 1. Exact proved ROST capacity

The pinned on-disc `roster_english.iff` resource contains one decoded `ROST` body of 2,294,304 bytes. Its proved major tables include:

| Structure | Count | Record stride |
|---|---:|---:|
| Player records | 2,254 | `0x14C` |
| Stadium records | 31 | `0x24` |
| Team records | 40 | `0x180` |
| Counted team memberships | 1,344 | One player pointer per membership |
| Players outside the counted-membership relationship | 910 | Existing player records, not newly allocated records |

The canonical inventory reports 32 teams with counted rosters, all containing 42 players:

- team indices `0..23`: 24 ordinary built-in teams;
- team indices `24..31`: eight `ONLN1` through `ONLN8` placeholder teams, each with 42 distinct player pointers; and
- team indices `32..39`: eight `USER1` through `USER8` placeholder teams, each with a zero roster count and 42 zero membership slots.

All 1,344 counted memberships are unique. No counted player belongs to two teams.

The total player-table arithmetic is favorable:

```text
32 teams * 53 players = 1,696 required player records
2,254 existing player records - 1,696 = 558 records remaining

additional memberships needed beyond stock:
32 teams * (53 - 42) = 352

existing unassigned player records:
910
```

The global player-record count is therefore not the limiting factor. The limiting factor is how a team record stores and exposes its membership.

The unassigned records occur in these exact index ranges:

```text
1008..1805  798 records
1848..1861   14 records
1904..1917   14 records
1960..1973   14 records
2016..2029   14 records
2072..2085   14 records
2128..2141   14 records
2184..2197   14 records
2240..2253   14 records
```

Those ranges sum to 910. The eight 14-record ranges immediately follow the eight populated online-placeholder rosters. This pattern is interesting capacity evidence, but it does not by itself prove that those records are intended as reserve slots.

Primary evidence:

- [ROST parser and structural invariants](../../tools/apf_roster.py)
- Private canonical roster inventory (research evidence; not distributed in the public tool)

## 2. Why stock team membership stops at 42

The proved subset of each `0x180` team record begins as follows:

```text
+0x000..+0x0A4  42 contiguous big-endian relative player pointers
+0x0A8          display-name pointer
+0x0AC          abbreviation pointer
+0x0B0          numeric-string-code pointer
+0x0B8          stadium pointer
+0x0BC          uniform-configuration pointer/fields begin
+0x0C5          counted-roster loop bound
+0x0D0          category code; exact enum meaning remains open
+0x0E8          secondary-abbreviation pointer
+0x108..+0x11C  six auxiliary player pointers; role unresolved
+0x120..+0x126  seven stock-accessed auxiliary roster bytes; exact roles partial
+0x127..+0x17F  89 bytes still unresolved
```

This is not merely a parser convention:

- XEX `0x84746F78` indexes teams at `team_base + index * 0x180` after checking the root team count.
- XEX `0x84AB9840` reads byte `+0xC5` as a loop bound, advances through the leading dword pointer array, and reads each referenced player's position byte.
- The current strict parser rejects a roster count above 42 because pointer slot 42 would overlap the display-name field.

Changing only `+0xC5` from 42 to 53 is therefore invalid. Unpatched code would treat the following eleven dwords as player pointers:

```text
slots 42 onward -> display name, abbreviations, team metadata, stadium data, and other non-player fields
```

A stock-data-only 53-player roster is ruled out by this layout. Any true 53-player route must either change the team-record schema and all consumers or add a separate membership representation understood by patched code.

## 3. The 32-team opportunity and its limits

### 3.1 What already exists

The low-level roster accessor is count-driven, and the ROST root exposes 40 team records. The first 32 are already populated. This makes 32 much more realistic than adding eight brand-new team records.

The placeholder categories differ:

| Team range | Current identity | Counted roster | Observed category code |
|---|---|---:|---:|
| `0..23` | Built-in teams | 42 | `0` |
| `24..31` | `ONLN1..ONLN8` | 42 | `3` |
| `32..39` | `USER1..USER8` | 0 | `2` |

The `online_slot` and `user_slot` names are derived from exact abbreviations. The category-code enum is not yet semantically proved. It is plausible that a team-list or mode filter uses this distinction, but changing category `3` to `0` is not yet an authorized writer or a proved way to expose the rows offline.

### 3.2 What must be runtime-proved

A 32-team Play Now claim requires all of the following:

1. Trace the owner that builds the selectable offline team list.
2. Determine whether it filters on team index, category code, abbreviation, a separate saved-team registry, or some combination.
3. Make exactly one bounded change that admits team 24.
4. Select team 24, load its roster, enter gameplay, and prove the same team identity persists.
5. Repeat the boundary test with team 31 so success is not limited to the first online slot.
6. Cold-reload with an isolated profile and determine whether a save shadows the disc row.

Until those checks pass, the exact statement is “32 populated records exist,” not “32 offline teams work.”

### 3.3 Visual-identity capacity

All 40 team rows have on-disc HOME/AWAY uniform-configuration records, but the physical asset catalogs do not all have 32 distinct entries:

| Uniform allocation family | Physical catalog count |
|---|---:|
| Glove | 3 |
| Helmet | 24 |
| Jersey | 24 |
| Logo | 118 |
| Text logo | 206 |
| Font | 11 |
| Number | 24 |
| Pants | 24 |
| Shoe | 11 |
| Shoulder plus normal | 24 |
| Sock | 24 |

Consequences:

- 32 teams can have distinct logo and text-logo selector identities inside existing catalog counts.
- Eight or more teams must share base helmet, jersey, number, pants, shoulder, and sock assets unless those catalogs are expanded.
- Shared pattern assets do not necessarily prevent visually distinct teams if material colors and logos are independently owned, but saved-team material/color semantics are not yet mapped.
- Existing selector write authority intentionally refuses online/user-slot authoring, and save overrides remain unproved.

This is a visual-authoring constraint, not a reason to reject the 32-team roster experiment.

## 4. Bounded container-space experiment for 53 players

### 4.1 Question

Can the existing fixed ROST allocation physically carry 352 additional team-to-player relationships without enlarging the decoded ROST body or its outer archive entry?

This experiment deliberately answers only that storage question. It does not claim that stock executable code consumes the proposed bytes.

### 4.2 Input and invariants

The read-only probe used the pinned retail ROST and the same checked token-preserving H7A encoder used by the selector-capacity work.

Exact fixed-allocation values:

```text
retail H7A payload:       435,225 bytes
fixed H7A payload limit:  436,024 bytes
retail payload headroom:      799 bytes
decoded ROST length:    2,294,304 bytes
H7A shift:                     10
```

The probe:

1. decoded the pinned ROST in memory;
2. selected 352 player indices outside the existing counted memberships;
3. assigned eleven proposed additional players to each of team rows `0..31`;
4. changed the proposed team count to 53 where applicable;
5. rebuilt the H7A payload in memory;
6. required the rebuilt payload to decompress exactly to the proposed decoded bytes; and
7. wrote no output volume or product file.

A fresh byte inspection found all 96 bytes at team `+0x120..+0x17F` equal to
zero for all 40 pinned team records. That was useful compression-capacity
evidence, but a later static consumer trace proved that the first seven bytes
are not unowned: stock accessors read and write `+0x120..+0x126`. An all-zero
retail state is therefore not spare-runtime-capacity proof. The remaining
`+0x127..+0x17F` bytes are unresolved, not available.

### 4.3 Results

| Representation for the additional eleven players | Bytes per team | Decoded bytes changed | H7A payload | Difference from limit | Result |
|---|---:|---:|---:|---:|---|
| Ordinary four-byte field-relative player pointers in the zero tail | 44 | 1,438 | 436,902 | 878 bytes over | **Does not fit** |
| Big-endian unsigned 16-bit player indices in the zero tail | 22 | 734 | 436,097 | 73 bytes over | **Does not fit** |
| Eleven packed unsigned 12-bit player indices plus four pad bits | 17 | 573 | 435,912 | 112 bytes under | **Fits** |

The 12-bit representation is sufficient because all valid player indices are `0..2253`, which is below the 12-bit ceiling of 4095.

For 32 teams:

```text
11 player IDs * 12 bits = 132 bits per team
132 bits rounded to bytes = 17 bytes per team
17 bytes * 32 teams = 544 decoded side-table bytes
```

The fitted payload grows by 687 bytes relative to retail:

```text
435,912 - 435,225 = 687 bytes
```

It remains 112 bytes below the existing fixed outer allocation. The token-preserving rebuild round-tripped exactly.

### 4.4 Exact caveat

The fitting result establishes only this:

> A compact 32-team-by-11 reserve-index representation can be recompressed
> inside the current fixed outer allocation for the tested deterministic
> assignment. This is a size result, not ownership of the tested location.

It does **not** establish any of the following:

- that any team-tail address is semantically free at runtime;
- that APF accepts a team count of 53;
- that a stock loop can read a packed 12-bit index;
- that roster screens, depth charts, gameplay, AI, injuries, substitutions, statistics, or saves handle player 43;
- that arbitrary player assignments always remain under the H7A ceiling;
- that an independent production writer or verifier exists; or
- that an executable patch is complete, safe, or releasable.

The direct-pointer experiment is also an important negative result. A natural “put eleven more normal pointers in the tail” design exceeds the current fixed payload by 878 bytes under the checked token-preserving route. It must not be presented as an already fitting alternative.

### 4.5 Follow-up static ownership result

The original `+0x120` placement is now **falsified**. In the pinned static
recompilation:

- XEX `0x84AB9990` reads and conditionally writes bytes `team +288..+293`
  (`+0x120..+0x125`) when replacing a stock membership slot;
- exact getter/setter functions at `0x84746270..0x847462D8` read and write
  `team +0x120..+0x126` individually;
- exact getters at `0x84AD9BC8..0x84AD9BF8` expose the same seven bytes; and
- downstream code at `0x84A18408` and `0x84ADA858..0x84ADA8A0` consumes these
  bytes as signed roster-slot/auxiliary selectors and grouped values.

Their complete meaning is not yet decoded, but ownership does not depend on a
final label: stock code reads and writes them. A reserve writer must not place
packed indices at `+0x120`. Bytes `+0x127..+0x17F` still need their own complete
consumer/serializer audit before use. The safer first runtime experiment uses
an emulator-owned mapping or a single hard-coded test player and writes no
team-tail byte.

## 5. Revised XEX-side-table architecture

The lowest-disruption true-53 design is a second membership segment, not an expanded `0x180` team stride.

### 5.1 Proposed data contract

For each of the first 32 teams:

```text
active membership 0..41:
    existing 42 field-relative dword pointers at team +0x000

extended membership 42..52:
    eleven packed 12-bit player indices in a separately owned extension table

proposed side-table footprint:
    17 bytes per team
```

The extension table may eventually live in an independently proved ROST region
or in emulator-allocated guest memory. It may not begin at `team +0x120`:
`+0x120..+0x126` are stock-owned, and the rest of the tail remains unproved.
A first one-player experiment needs no persistent table at all; it can resolve
one pinned player index conditionally inside one exact consumer hook.

An initial compatibility prototype should leave stock `+0xC5` at 42 and expose the extra eleven only through one patched experimental accessor. This prevents untouched stock loops from walking into metadata. Only after every direct membership consumer is inventoried and redirected should the runtime-visible count become 53.

### 5.2 Required executable behavior

A patched accessor would conceptually implement:

```text
get_team_roster_count(team):
    return 53 for admitted expanded teams

get_team_player(team, slot):
    if slot < 42:
        use the existing pointer array
    else if slot < 53:
        decode packed 12-bit index at side-table slot (slot - 42)
        resolve it through the proved player-table accessor
    else:
        reject
```

That helper is useful only if every relevant direct consumer is routed through it. At minimum the audit must cover:

- roster and depth-chart construction;
- lineup validation and auto-fill;
- offense, defense, and special-teams enumeration;
- substitution and injury replacement;
- AI roster evaluation;
- player/team statistics ownership;
- team creation and accepted-team reload;
- Season roster mutation, if Season is in scope;
- save/profile serialization and load precedence; and
- any network/online structures, which should remain out of scope initially.

XEX `0x84AB9840` is one known direct traversal, not proof that it is the only traversal.

### 5.3 Why expanding the team stride is worse

An alternative would enlarge each team record from `0x180` to at least `0x1AC`, move every field after the membership array, rebuild the team table, and patch every accessor and serializer offset.

That route is substantially riskier because it changes:

- team stride multiplication;
- display-name, abbreviation, stadium, category, selector, and auxiliary offsets;
- root table adjacency and following-table pointers;
- ROST relocation/serialization behavior;
- compressed allocation size; and
- every consumer compiled against the original layout.

A separately owned side table preserves the existing 42-pointer prefix, team
stride, and all named metadata offsets. It remains the preferred ambitious
route, but the original in-record `+0x120` placement is retired.

### 5.4 Other longshot storage candidates

Two additional areas remain evidence-bearing but weaker:

1. Root table 2 contains 1,001 dword slots: 427 valid player pointers and 574 zeros. The 574 zero slots exceed the 352 relationships needed, but the table's purpose is unresolved.
2. The ROST has a `0xFA0`-byte zero workspace between root pointers. Existing executable code treats it as custom-name capacity, so consuming it for membership risks colliding with saved-team name allocation.

Neither should be used before exact consumer ownership is recovered.

## 6. Current product boundary

APF 2K8 Mod Studio's current bounded on-disc roster writers cover:

- all 2,254 player records' first- and last-name references where the mapped
  UTF-16BE allocation has a supported pure-owner scope;
- all 40 team display-name allocations;
- player positions as exact native codes `0..16`, including the required
  `+0x34` / `+0x35` mirror update; and
- all 31 mapped base-rating bytes per player as exact native `0..99` values.

This is **63,112 independently editable rating cells** (`2,254 * 28`), not a
tier-to-number approximation. Existing native source value `100` remains
visible and revertible, while newly authored values deliberately stop at 99.
The token-preserving ROST transport has booted and loaded a player changed from
Speed 40 to 99; a controlled gameplay-effect A/B is still outstanding.

The identity writer preserves every pointer and requires authored UTF-16BE text
to fit the original allocation. Team abbreviations and secondary abbreviations
are mapped for browsing but remain runtime-locked; the product does not claim
write ownership of them. It also does not currently write:

- team membership or roster counts;
- jersey numbers;
- appearance, faces, or equipment fields in player records;
- auxiliary player references;
- category codes or offline team-list ownership;
- depth charts; or
- save/profile roster state.

Accordingly, 32 renamed database rows do not yet equal 32 complete modern NFL teams. The existing UI must keep membership and 53-player expansion labeled Coming Soon or experimental until their separate proofs land.

Primary product boundary:

- [Bounded APF roster identity writer](APF_ROSTER_IDENTITY_WRITER.md)
- [True native 0–99 base-rating result](APF_TRUE_099_PLAYER_RATINGS.md)
- [Rating writer runtime boundary](APF_PLAYER_RATINGS_TOKEN_PRESERVING_RUNTIME.md)
- [APF Mod Studio Getting Started](../mod_editor/apf2k8_mod_studio_getting_started.md)
- [Public capability registry](../../mod_editor/capabilities/registry.v1.json)

## 7. Save/profile boundary

The eight `USER` rows and first-run team construction make saved-team overlays likely, but the current evidence does not prove their complete container schema or exact capacity policy.

Known boundaries:

- A clean APF profile forces team construction with two gold, three silver, and six bronze players.
- The previous Coach's Desk experiment did not complete that onboarding, so it did not reach a controlled Season destination.
- No safe APF save/profile writer is exposed.
- Container integrity, profile binding, versioning, load precedence, and changed-save reload remain incomplete.
- Saved-team state may shadow disc team identities, selectors, colors, and roster data.

A disc-only Quick Game prototype should therefore use isolated storage and explicitly classify behavior before save support is attempted. A successful warm run is insufficient if a clean profile produces a different team list or overwrites the changed row.

Primary evidence:

- Season-to-Coach's-Desk Xenia experiment (private research evidence; not distributed)
- APF franchise runtime-ownership analysis (private research evidence; not distributed)
- [Public product status and capability boundary](../mod_editor/APF2K8_STATUS.md)

## 8. Why a 32-team Season is a separate project

The retained executable contains substantial APF-adapted Season/franchise code, but it is not a data-only league-size switch.

At least two focused initialization paths contain an exact 24-entry loop:

```text
loop bound: 0x18
decimal:    24
```

One occurs in the standalone retained franchise initializer; another clears a 24-dword Season-side array. These are strong 24-team management-state constraints, though they are not proof that every subsystem shares one universal hard-coded team count.

A real 32-team Season additionally requires:

- schedule table and generator ownership;
- standings and tiebreaker ownership;
- playoff qualification and bracket policy;
- team-select and scrolling-list capacity;
- simulation and GameCast team references;
- statistics and record-book cardinality;
- week progression and completion states;
- roster mutation and injury handling;
- new/load mode initialization;
- save schema, integrity, signatures, and reload proof; and
- return-path and resource-lifecycle testing.

The retained `playoff_tree` layout has 16 panel records, but panel count alone does not define a 32-team league or prove a compatible playoff format. Schedule tables and their runtime/save consumers remain explicitly unmapped.

Primary evidence:

- Franchise restoration feasibility analysis (private research evidence; not distributed)
- Focused franchise/Season pseudo-C (private analysis artifact; not distributed)
- Cross-title layout inventory (private analysis artifact; not distributed)
- [Public product status and capability boundary](../mod_editor/APF2K8_STATUS.md)

## 9. Staged implementation and falsification route

Each stage should end with a bounded result before the next begins.

### Stage A: prove the 32nd database team in Play Now

Goal: determine whether populated online rows can become ordinary offline teams.

1. Trace the exact team-list producer and category filter.
2. Create a copied-game experiment admitting only team 24.
3. Give team 24 a visibly diagnostic name through the existing identity writer.
4. Prove selection, matchup display, roster load, coin toss, and live gameplay persistence.
5. Repeat team 31 as the upper boundary.
6. Cold-reload under isolated storage and test save precedence.

Positive result: team 31 is selectable and reaches gameplay with its expected 42-player row.  
Falsifier: the list admits the row but gameplay resolves another team or a saved-team override. That would redirect work to the runtime team registry/save owner rather than justify broader category edits.

### Stage B: prove bounded membership mutation inside 42

Goal: establish that the on-disc counted-membership relationship is writable and consumed.

1. Replace one existing membership pointer with one unassigned player record.
2. Keep count 42 and preserve every other team/player pointer.
3. Independently reparse and verify referential integrity.
4. Prove the changed player appears in roster/depth-chart UI and gameplay.
5. Revert and prove the original player returns.

This stage is required even if 53 remains deferred. It unlocks authentic 42-player team construction and the practical master-roster alternative.

### Stage C: ship the practical 53-master/42-active workflow

Goal: let modders author 53 players per team without claiming unsupported runtime capacity.

1. Store only user-authored 53-player team definitions in the retail-free project.
2. Require the user to select or generate a 42-player active roster for each build.
3. Compile those 42 relationships into the stock membership array.
4. Preserve the eleven inactive/reserve definitions in project metadata only.
5. Make swaps reproducible per team and rebuildable before launch.

This is the nearest product-quality alternative and can coexist with later XEX work.

### Stage D: find separately owned extension storage

Result so far: the original `team +0x120` start failed static ownership review.
Stock code accesses `+0x120..+0x126`.

1. Trace all XEX reads/writes and serializer coverage of `+0x127..+0x17F`.
2. If any byte remains a candidate, run a no-op tag only in that bounded span.
3. Otherwise allocate a version-pinned emulator-owned guest side table.
4. Exercise team creation, Play Now, reload, and any stock Season path available.
5. Confirm no stock subsystem clears, hashes, copies, or rejects the chosen
   storage unexpectedly.

Falsifier: any stock consumer assigns another meaning to a candidate byte. Do
not shift the table blindly; use runtime-allocated storage or revisit root
table 2 rather than overwrite an owner.

### Stage E: runtime-prove player slot 43

Goal: cross the stock boundary once, causally.

1. Resolve one pinned unassigned player index for one team through a conditional
   emulator hook; write no team-tail byte.
2. Patch one exact roster accessor/consumer to expose slot 42, the 43rd player.
3. Keep every other team and extension slot unchanged.
4. Prove the player in roster UI, depth chart, and one live play/substitution route.
5. Capture logs and rollback.

Negative result is useful if it identifies a second direct consumer or downstream 42-player array.

### Stage F: one complete 53-player team

Goal: validate every game system needed for all eleven extra members.

Test:

- roster browsing;
- depth charts and special teams;
- auto-fill and lineup validation;
- substitutions;
- injuries;
- AI roster use;
- player and team statistics;
- game completion and return to menus; and
- cold reload.

Only after this passes should the extension be applied to all 32 rows.

### Stage G: all 32 teams, still Play Now first

Goal: combine the 32-team selector route with the 53-player accessor route.

1. Populate 352 extension relationships with uniqueness and bounds checks.
2. Build all 32 identities and active/reserve lists.
3. Sample the first, last, and several middle teams in gameplay.
4. Run cross-team integrity checks and verify no player is unintentionally shared.
5. Keep Season disabled unless its separate tests pass.

### Stage H: save and Season work

Goal: move from a disc-seeded Play Now conversion to persistent league state.

This stage begins only after controlled one-variable APF save/profile pairs exist. It must separately close schedule, standings, playoffs, roster mutations, serialization, signatures, and create-save-reload behavior.

## 10. Product presentation policy

Mod Studio should present these states honestly:

| Feature label | UI status until proved |
|---|---|
| Browse 40 team records | Available |
| Rename existing player/team allocations | Editable |
| Existing 42-player memberships | Preview/Export-only |
| 32-team Play Now mode | Coming Soon: populated rows found; selector/runtime proof pending |
| 53-player master roster with 42 active | Coming Soon until bounded membership writing lands |
| True 53-player XEX extension | Experimental, emulator-only |
| 32-team Season | Research/Coming Soon |

No public project or tool may contain retail roster bytes, modified XEX bytes, save/profile payloads, or preimages. A future XEX feature should distribute only version-pinned user-applied patch logic and authored metadata. Users must supply their own legally dumped game.

## 11. Final classification

### Proved

- 40 on-disc team records exist.
- The first 32 have counted 42-player rosters.
- 2,254 player records and 910 currently unassigned records exist.
- Thirty-two 53-player rosters need 1,696 player records and 352 additional relationships, so total player-record count is sufficient.
- The stock team record contains only 42 contiguous membership pointers.
- A direct count-to-53 edit is structurally invalid for stock consumers.
- A deterministic packed 12-bit reserve-index proposal fits the tested fixed ROST allocation with 112 bytes of H7A headroom.
- Stock code reads and writes `team +0x120..+0x126`; the original embedded
  side-table placement is falsified.

### Plausible but unproved

- Reclassifying/admitting `ONLN1..ONLN8` as eight additional offline Play Now teams.
- Finding a separately owned ROST region or emulator-allocated side table.
- Patching all roster consumers to merge 42 stock pointers with eleven packed reserve indices.
- Achieving a complete 32-by-53 Play Now conversion on Xenia.

### Major separate project

- 32-team Season/franchise scheduling, standings, playoffs, roster mutation, and persistence.
- Save/profile-compatible 53-player rosters.
- Original Xbox 360 hardware support.

### Best next experiment

Trace and admit team 24 in the offline team selector, then prove it from selection through live gameplay while leaving its existing 42-player roster untouched. That experiment isolates the 32-team question before any 53-player XEX work begins.

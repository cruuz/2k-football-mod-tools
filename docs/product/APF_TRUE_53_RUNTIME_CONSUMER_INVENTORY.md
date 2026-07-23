# APF 2K8 true-53 runtime consumer inventory

Date: 2026-07-19  
Scope: pinned US retail `default.xex`, emulator-target roster expansion  
Result: completed static experiment; no game or emulator process was started

## Outcome

True 53-player teams are still technically plausible as an emulator-only
feature, but they are **not** a one-byte or one-function patch. The static
experiment found four separate constraint layers:

1. the on-disc team record has only 42 contiguous membership pointers;
2. a central count/getter helper family traverses that 42-pointer prefix;
3. at least 25 roster-class routines read, write, copy, search, or clear the
   membership array directly; and
4. one post-load roster-layout routine allocates position buckets for exactly
   42 players, independently of the stored count.

The existing slot-43 Xenia experiment remains useful: it tests one carefully
isolated cornerback selection path without altering retail data. It cannot be
promoted into a general 53-player patch by merely removing its exact-caller
gate.

This is a mixed result:

- **Positive:** an emulator-owned side table plus version-pinned runtime hooks
  remains a viable architecture. Nothing found makes 53 inherently impossible.
- **Negative:** changing `team + 0xC5` to 53, or patching only
  `0x84AB9840`/`0x84AB9930`, is falsified as a complete solution.

The global roster arithmetic is favorable. APF already contains 2,254 player
records; 32 teams times 53 players requires 1,696, leaving 558 records beyond
that requirement. Team rows 0–31 are already populated (rows 24–31 are online
placeholders with 42 members), so player-record quantity is not the blocker.
Making rows 24–31 selectable offline is a separate selector/save-override
problem.

## Pinned evidence boundary

| Item | Pin |
|---|---|
| Game | All-Pro Football 2K8, Xbox 360, US retail |
| Title ID | `0x54540807` |
| Retail `default.xex` SHA-256 | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| Static-recompiler image | `build-static-recomp-apf/ppc/ppc_recomp.*.cpp` |
| Reviewed slot-43 Xenia commit | `d145430737f787f522e08e7d86d3e94bdde6d6a1` |
| Reviewed native Xenia SHA-256 | `e8d7fda95239d12c11a1d2b336bbed33b39d1da738a65dc2e757c16b8d215641` |

The experiment searched generated PowerPC functions and their original guest
instruction comments. It performed no source-game write, XEX write, ROST
write, save write, GUI launch, or emulator launch. Addresses and counts below
are metadata, not retail game bytes.

## 1. The existing 42-pointer record boundary

The team record has stride `0x180`:

```text
team +0x000..+0x0A4   42 player pointers (42 * 4 bytes)
team +0x0A8           display-name pointer; not player slot 43
team +0x0AC           abbreviation pointer
team +0x0B0           numeric-string pointer
team +0x0B8           stadium pointer
team +0x0C5           counted membership byte
team +0x0D0           category value
team +0x108..+0x11C   six auxiliary player pointers
team +0x120..+0x126   seven stock-owned roster selectors
```

Therefore, letting an unmodified loop run 53 iterations would interpret team
identity and stadium fields as player pointers. The stock `0x180` record cannot
hold 53 ordinary contiguous member pointers without moving every later field
and patching every team-record consumer.

The safer architecture continues to be:

```text
slots 0..41   -> original team record
slots 42..52  -> emulator-owned extension table of player indices/pointers
```

The retail count byte should remain 42 until each consumer is redirected.

### Team-stride and serialization consumers

Expanding the team record itself is even broader than extending membership:

| Entry | Static contract |
|---|---|
| `0x84746F60` | Returns the root team count |
| `0x84746F78` | Resolves `team_base + index * 0x180` |
| `0x84746FC0` | Reverse-resolves a team pointer by dividing by `0x180` |
| `0x84753508` | Team serializer size callback returns `0x180` |
| `0x847535A0` | Initializes/copies one exact 384-byte team record |
| `0x8474B828`, `0x8474B8A0`, `0x8474B9B8`, `0x8474BA20` | Global team-table walkers advance by `0x180` |
| `0x8474DEB8`, `0x8474ECE0` | Large load/copy paths contain repeated `+0xC5` and 384-byte record operations |

This reinforces the side-table decision. Enlarging `0x180` would require
changing index access, reverse access, serialization, global iteration, copy
code, root adjacency, and every later field offset before it could be tested.

## 2. Central helper family and its real call surface

Four neighboring functions directly traverse `team + 0xC5` and the member
pointer prefix:

| Entry | Observed behavior | 53-player implication |
|---|---|---|
| `0x84AB9840` | Count members matching a position (`17` means any position) | Must count both stock and extension segments |
| `0x84AB9888` | Count matching-position members after filtering a flag field | Must preserve the filter while visiting extension members |
| `0x84AB98E0` | Count matching-position members, capped at 20 | Extension-aware, but the semantic cap may remain 20 |
| `0x84AB9930` | Return the Nth member matching a position | Must resolve slots from both segments and reject out-of-range N |

The static recompile contains:

- 30 direct calls to `0x84AB9840` from 16 owner functions;
- 63 direct calls to `0x84AB9930` from 11 owner functions; and
- 19 distinct owner functions across the union.

That is 93 statically visible direct calls to the two primary helpers. The
other two helpers have no ordinary direct-call instruction in the recompile
and may be reached through function tables or indirect dispatch; they must not
be discarded as dead without runtime coverage.

The 19 direct owner functions are:

```text
0x846811E8  0x84681258  0x849E3360  0x849E3640  0x849E4F20
0x849E4F78  0x849E54A8  0x849EB650  0x849EBFC8  0x849F0B58
0x849F3368  0x84A16C30  0x84A16D10  0x84A19808  0x84A1A1A0
0x84A1A388  0x84A2FD20  0x84A31EC8  0x84ABA4D0
```

The current slot-43 prototype intentionally intercepts only return addresses
`0x84A16D34` and `0x84A16D50`, one count/get pair inside owner
`0x84A16D10`. It covers two of the 93 direct calls and only the CB branch. That
is the correct scope for a causal first experiment, not a coverage claim.

Owner `0x84A31EC8` alone contains 44 of the 63 getter calls. Static control
flow shows a large mode/scheme switch that repeatedly requests position/depth
members for lineup or personnel evaluation. It is a critical gameplay consumer:
success at the isolated `0x84A16D10` cornerback path cannot stand in for it.

## 3. Confirmed direct roster-class consumers

The following routines use `+0xC5` or the member array directly. They are a
confirmed lower bound, not an assertion that no other consumer exists.

| Entry | Static behavior relevant to 53 |
|---|---|
| `0x84AB8680` | Iterates every team member and aggregates a player field |
| `0x84AB86E0` | Iterates every member and aggregates a caller-selected player field |
| `0x84AB89F0` | Finds a player pointer in a team's counted membership array |
| `0x84AB9028` | Removes a slot, shifts later pointers left, decrements `+0xC5`, clears the vacated pointer, and repairs auxiliary slot selectors |
| `0x84AB93D0` | Rebuilds roster ordering/depth metadata; contains an independent fixed 42-player workspace described below |
| `0x84AB97E0` | Iterates members and copies one `0x14C` player record per member into a caller buffer |
| `0x84AB9840` | Position-count helper |
| `0x84AB9888` | Filtered position-count helper |
| `0x84AB98E0` | Capped position-count helper |
| `0x84AB9930` | Nth member by position helper |
| `0x84AB9A18` | Finds the Nth member of a position and branches to the bounded slot-replacement routine |
| `0x84AB9AB0` | Returns the first member when count is at least one |
| `0x84AB9AD0` | Finds the member following a supplied player pointer |
| `0x84AB9B28` | Searches for a member pointer and routes a found index into the removal routine |
| `0x84AB9B70` | Appends a player only when `count < 42`; increments `+0xC5` |
| `0x84AB9BA8` | Iterates a team's roster cyclically while consulting player metadata |
| `0x84AB9D10` | Boolean membership search |
| `0x84AB9D50` | Null-safe append, also explicitly rejects `count >= 42` |
| `0x84AB9D98` | Clears the roster count and the six auxiliary slot selectors |
| `0x84AB9E50` | Counts members with a player flag set |
| `0x84ABA1C0` | Iterates members and classifies a player subfield through indirect dispatch |
| `0x84ABA230` | Similar classified-member traversal returning a selected player/result |
| `0x84ABA2A8` | Finds the Nth member matching a player subtype |
| `0x84ABA348` | Resolves requested position/ordinal pairs and computes a six-value aggregate |
| `0x84ABA4D0` | Repeatedly calls the Nth-position getter and also performs direct full-roster traversal |

Two additional confirmed cross-subsystem consumers were found outside that
roster-method cluster:

- `0x84AB67B8` enumerates teams, then walks each counted roster while resetting
  or shifting a player-owned history/stat field.
- `0x84ABC830` obtains a current/global team pointer and walks its counted
  members during a player-selection/matching path.

Additional high-confidence direct consumers outside the local helper cluster
include `0x849D6E48`, `0x84A04980`, `0x84A24370`, `0x84A24430`,
`0x84A2FE00`, `0x84A2FEB8`, `0x84A30030`, and `0x84A4F6C0`.
They cover slot/head selection, current-team membership lookup, filtered
count/get operations, and append/replace/swap behavior. They must receive
their own exact hook or be proven to route through the future abstraction.

`0x84A2FD20` is particularly important: it uses helper-derived position
quotas, selects an over-quota player, then directly shifts the leading member
array left, clears the final pointer, and decrements `+0xC5`. A helper-only
patch would therefore still lose or ignore extension members during trimming.

## 4. The independent fixed-42 workspace

`0x84AB93D0` is the most important new blocker. It does not merely trust the
stored count. Its initialization proves an internal 17-position by 42-player
layout:

| Guest address | Instruction-level fact | Meaning |
|---|---|---|
| `0x84AB93E8` | load loop count 714 | Clears `17 * 42` dwords |
| `0x84AB941C` | set outer member count to 42 | Walks exactly 42 member pointers |
| `0x84AB94A4` | compare insertion index with 41 | Last legal index is 41 |
| `0x84AB94D0` | multiply position by 42 | Each position bucket has a 42-pointer stride |

The function uses a `0xC10`-byte stack frame (3,088 bytes). Its main local
array begins at stack `+0xB0` and consumes `714 * 4 = 2,856` bytes, leaving only
the existing small bookkeeping margin. A 17-by-53 pointer array would need
`901 * 4 = 3,604` bytes, 748 bytes more than the stock array.

Consequently, a true-53 patch must do one of the following:

1. replace this whole routine with an emulator-side implementation and owned
   temporary storage;
2. enlarge/rebase its stack frame and adjust every local offset; or
3. keep this routine stock-only and build extension-player ordering/depth
   metadata in a second pass whose downstream consumers are also patched.

Option 1 is the smallest and most reviewable emulator experiment. Patching
only the literal 42 values is unsafe because the existing frame cannot contain
the larger array.

The broader scan found other high-confidence functions with a hard-coded 42
in a team/membership path:

```text
0x8469D5F8  0x849E3348  0x849EF140  0x84A2FE00  0x84A2FEB8
0x84A30030  0x84A5CC58  0x84AB93D0  0x84AB9B70  0x84AB9D50
```

The last two are explicit append caps. The earlier functions require their
individual control-flow semantics to be preserved, but they are already
admitted to the patch audit as hard-cap witnesses.

`0x849E3348` is a pure `team + 0xC5 < 42` predicate used by a team-enumerating
roster transaction path. Its neighbor `0x849E32E8` can accept counts through
54 under an additional unresolved team condition. That neighbor is useful
evidence that some management mode may tolerate 53; it is not proof that the
ordinary team path or storage layout does.

`0x84A19808` contains two position-ordering passes with 42-entry local sort
arrays and explicit 41/42 bounds. A real NFL position group is far smaller
than 42, so this may not block a 53-player total by itself, but it must be
classified rather than globally widened. Created-player/list-management
candidates `0x84A51668`, `0x84A517A0`, and `0x84A0A0E8` also cap pointer lists
at 42; nearby delete/assigned-to-team strings suggest a UI/created-player
scope, which runtime tracing must confirm.

## 5. High-confidence candidates still needing exact dataflow closure

A focused query found 41 functions that both call a proved team-record
accessor (`0x84746F78` or wrapper `0x8467D658`) and contain at least one byte
read at displacement `+197`. This syntactic intersection is a useful coverage
queue, but large functions may operate on more than one structure, so it is
not promoted to confirmed consumer status without register-flow review.

```text
0x84680090 0x84680D58 0x846815A0 0x84681728 0x84681A88
0x846C19D8 0x847039C8 0x8470EA58 0x8470EF28 0x8471A410
0x8471B0D8 0x8471F920 0x8471F9B0 0x849DEFD8 0x849E1DA0
0x849E20E8 0x849E50A8 0x849E5268 0x849E6918 0x849E69E8
0x849EAEF8 0x849EB110 0x849EB290 0x849EBFC8 0x849EDA18
0x849F3368 0x849F42F0 0x849F4538 0x849F6448 0x84A4F320
0x84A4FFC0 0x84A51FD8 0x84A5C2D8 0x84A73180 0x84A75E28
0x84A778D0 0x84A7A500 0x84AB67B8 0x84AE7638 0x84B04A78
0x84B07A58
```

Runtime coverage should determine which of these execute during roster menus,
depth-chart setup, Play Now gameplay, injuries, substitutions, end-of-game
statistics, and return to the frontend.

For completeness, the widest syntactic scan saw 179 functions loading or
storing byte displacement 197. That is intentionally a low-confidence
envelope because unrelated structures may also own a byte at `+197`. Fifty-nine
functions had same-body team provenance and form the medium-confidence queue.
An independent Ghidra pseudo-C scan produced 36 `+0xC5` hits; two were clear
false positives (`0x84790490` range arithmetic and unrelated structure
`0x84C0D4E8`), leaving 34 high/medium roster candidates. The patch must begin
with the confirmed set while retaining the wider sets as coverage gates.

## 6. Practical implementation ladder

The implementation should remain version-pinned and emulator-only until all
steps pass:

1. **Observe the existing slot-43 path.** Run the reviewed log-only control.
   Do not enable modification until it reports `observe_path_proved`.
2. **Cross one helper path.** Run the confirmed one-player modified control and
   prove player 43 is returned only at the intended call pair.
3. **Generalize the helper abstraction.** Add an emulator-owned 11-slot side
   segment for one team, extend all four helper semantics, and log every helper
   owner/return address reached.
4. **Replace the fixed roster-layout builder.** Reimplement `0x84AB93D0` for a
   53-player input using owned temporary memory; do not enlarge its stock stack
   array in place.
5. **Patch roster mutation methods.** Redirect append, remove, replace, clear,
   contains, first/next, and copy operations so they understand both segments.
6. **Close the 41-function candidate queue.** Classify each by dataflow and
   runtime coverage. Any direct consumer must be redirected or deliberately
   kept stock-only with a documented consequence.
7. **Prove one complete team.** Roster browser, depth chart, substitutions,
   injury replacement, AI use, game completion, stats, frontend return, and
   cold reload.
8. **Scale to 32 teams.** Only after one team's complete path passes. Offline
   selector ownership for teams 25–32 remains a separate requirement.

Season/save persistence and online/network structures should remain outside
the first implementation. A first successful version may rebuild its
emulator-owned extension table from the retail-free Mod Studio project at each
launch.

The Season/franchise lane is not automatically solved by 32-team Play Now.
Existing evidence includes separate exact 24-entry Season loops; expanding
that mode additionally implicates schedules, standings, playoffs, statistics,
UI, roster mutation, and save schemas.

### Observe-only consumer census design

The next broad-coverage runtime experiment should collect metadata without
changing the game. On the pinned Xenia build:

1. invalidate the roster-root epoch at guest `0x84750EF8`;
2. validate and cache the loaded ROST root at `0x8474F950`;
3. retain the exact PPC source PC through `X64Emitter::MarkSourceOffset`;
4. observe x64 HIR `LOAD_OFFSET`, `STORE_OFFSET`, `LOAD`, `STORE`,
   `ATOMIC_COMPARE_EXCHANGE`, and `MEMSET`; and
5. aggregate only accesses intersecting each validated team's
   `+0x000..+0x0A7` member region or `+0xC5` count byte.

The receipt key should be:

```text
guest PC + LR + read/write + width + member/count region + relative slot + team index
```

It must not record guest values, player pointers, absolute roster addresses,
names, or other retail data. Validation must require 2,254 players, 40 team
rows, exact `0x14C` player and `0x180` team strides, stock 42/0 team counts,
and 1,344 unique valid memberships. Root reload, unsupported overlapping
memory operations, dropped events, overflow, malformed receipts, or source
mutation fail closed.

The census is complete only after the full boot/frontend/roster/depth/gameplay/
substitution/injury/stats/postgame/cold-reload matrix runs twice without adding
a new consumer key, and every static candidate is observed or explicitly
classified. Even then, it proves the inventory—not true-53 behavior.

## 7. Product status

- True independent `0..99` editing is already shipped for all 28 mapped base
  attributes across all 2,254 player records.
- Overall, player tier, abilities, position, equipment, membership, and depth
  chart are separate fields/systems; changing base ratings does not silently
  rewrite them.
- The 32-by-53 Mod Studio roster view remains an honest project planner: rows
  43–53 are preserved in a retail-free project and are not claimed as active
  in stock APF.
- True 53 remains **Coming Soon / emulator-only experiment** pending runtime
  proof and the multi-consumer patch above.
- No retail game bytes are contained in this note, the project plan, or the
  experiment runner.

## Completed experiment result

The bounded static inventory completed successfully. It found a much larger
consumer surface than the original one-helper hypothesis and identified the
fixed 17-by-42 layout builder as a concrete additional blocker. This is a
useful negative result for the simple-patch idea and a positive roadmap for a
coordinated emulator shim.

The first valid passive slot-43 observe control subsequently ran headlessly for
180 seconds with null graphics, audio, and input. It preserved the complete
source tree and `default.xex` and completed `path_not_reached`: ordinary
no-input boot did not exercise the exact defensive roster-builder path. That is
a completed negative for passive boot, not a hook failure. Modified mode stays
locked. The next runtime step is a fresh observe run deliberately navigated
into that path, using either a reviewed scripted virtual controller or the
isolated operator workflow.

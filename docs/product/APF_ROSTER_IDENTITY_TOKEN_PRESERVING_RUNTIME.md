# APF 2K8 token-preserving roster-identity runtime proofs

Dates: 2026-07-18 and 2026-07-19  
Classification: **Runtime-positive for built-in team and player-name edits**  
Scope: fixed-allocation `roster/ROST` identity replacements in Xenia

## Player-name result — 2026-07-19

A second token-preserving candidate changed Dan Marino's unaliased last-name
allocation from `Marino` to `CODEX`. The candidate booted through the title,
no-profile prompt, name entry, and first-run Team Create flow. In Gold-tier
quarterback selection, the list visibly rendered **Dan CODEX #13 QB**. Opening
the full Star Card rendered **QB #13 DAN CODEX — GOLD STAR** beside the stable
3D player, biography, career text, and three abilities. No corrupted text,
player-card failure, or old roster startup crash appeared.

| Property | Value |
| --- | --- |
| Stable target | `apf:roster-name:1977` |
| Semantic owner | Player 788, `last_name` only |
| Allocation | 14 decoded bytes / 6 authored characters maximum |
| Replacement | `Marino` → `CODEX` |
| Decoded bytes changed | 6, all inside the selected allocation |
| Source H7A tokens | 284,015 |
| Tokens preserved | 284,010 |
| Tokens repaired | 5 |
| Team fields changed | 0 of 120 |
| Base-rating cells changed | 0 of 63,112 |
| Candidate `0A` SHA-256 | `0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044` |

The private candidate receipt is SHA-256
`b7c23be3bfe2ab6aad590f28b18c49c7b64940b35d09424c3fdfc1419da79919`.
All six supported source files matched before construction and remained
unchanged after runtime. Xenia Canary `canary_experimental@6e5b8324f` ran only
on isolated `DISPLAY=:99`, reported a normal `Cheap-skate exit!`, and logged
neither guest PC `0x84AB1D40` nor an access violation.

| Private evidence basename | Bytes | SHA-256 |
| --- | ---: | --- |
| `apf-player-name-dan-codex-token-preserving-runtime-20260719.mp4` | 512,390 | `89f406ce59f6b1f2f5b83d2a3cfa3ea24d9b4e8c5d3db9a13ccab6f6f198acdd` |
| `apf-player-name-dan-codex-star-card-runtime-20260719.mp4` | 750,979 | `ef3ad1d5f7ee53016128be9a6275098eaa6afe32cde3dab6436f5d605cfe6a11` |

This proves the repaired transport and live consumer for one bounded,
unaliased player-name allocation. Alpha.21 now uses that same fixed-allocation
writer for 3,191 nonempty player first/last-name allocations serving 4,482
writable references, while preserving every exact character limit and clearly
disclosing every alias owner. Together with 40 team display names, the product
scope contains 3,231 editable name allocations. It does not prove team
abbreviations, jersey numbers, membership, depth charts, 53-player active
rosters, or arbitrary growth of the roster pool.

The alias boundary is part of the feature, not a footnote. Of the editable
player-name allocations, 429 are shared, the largest has 23 owners, and 61 are
used by both first- and last-name fields. One replacement changes every listed
owner together. The inspector keeps that complete owner list local to the
loaded game; a retail-free project persists only authored replacement text and
the existing offset-free limit/count/fingerprint target contract. The empty
zero-capacity allocation, mixed team/player ownership, unknown ownership, and
both abbreviation families fail closed.

## Team display-name result — 2026-07-18

## Result

A token-preserving `ROST` rebuild booted normally and the game visibly consumed
the injected team display name `CODEXTEAM`. The name rendered on Logo Selection,
rendered again on Team Summary, and remained present after reaching a stable
Team Select screen. The game did not reproduce the earlier startup access
violation and exited cleanly.

This is a positive runtime result for the bounded route that edits an existing
built-in team's display-name allocation without growing or moving it. The
separate player-name result above closes the repaired-route player-consumer
gap; team abbreviations, jersey numbers, membership, depth charts, and roster-
capacity expansion remain separate.

## Why this result differs from the earlier crash

The earlier writer changed only nine decoded name bytes, but then ran the whole
2.29 MB decoded roster through a generic greedy H7A compressor. That fresh parse
changed about 412,821 of the 434,269 comparable compressed bytes and shifted the
IFF footer 956 bytes. Clean, team-only, player-only, and combined controls proved
that every generic rebuilt `ROST` crashed at guest PC `0x84AB1D40`.

The replacement writer replays the retail H7A token stream and changes only the
tokens whose decoded spans intersect the authored bytes. For the same team-only
edit, it preserved 284,004 of 284,015 retail tokens and split or replaced only
11. The decoded roster graph and all relative pointers stayed bit-exact outside
the nine authored UTF-16BE character bytes.

| Property | Historical generic rebuild | Token-preserving rebuild |
| --- | ---: | ---: |
| Authored decoded bytes | 9 | 9 |
| Retail H7A tokens preserved by construction | No | 284,004 / 284,015 |
| Retail tokens split or replaced | Whole stream retokenized | 11 |
| H7A payload size | 434,269 bytes | 435,246 bytes |
| Delta from 435,225-byte retail payload | -956 bytes | +21 bytes |
| IFF file length | 434,373 bytes | 435,350 bytes |
| Fixed outer allocation | 436,224 bytes | 436,224 bytes |
| Xenia result | Startup crash | Booted and consumed `CODEXTEAM` |

The runtime A/B therefore isolates full-stream retokenization as the causal
difference that matters for this edit. The old static trace remains valid as a
description of how the generic build failed: the guest reached the ROST graph
fixup with an already-relocated table pointer and relocated it a second time.
It is no longer evidence that every fixed-allocation roster-name edit is
impossible.

## Controlled runtime path

The successful run used Xenia Canary `canary_experimental@6e5b8324f`, a fresh
persistent profile, and an isolated `DISPLAY=:99`. The operator's live desktop
was not touched. The only authored game-data change was built-in team 0's
display name, `Americans` → `CODEXTEAM`.

The observed path was:

1. normal game startup and demo presentation;
2. first-run profile creation;
3. first-run Team Create flow;
4. Logo Selection with `CODEXTEAM` rendered in the game UI;
5. Team Summary with `CODEXTEAM` rendered again;
6. a stable Team Select screen with `CODEXTEAM` still consumed; and
7. a clean emulator exit with no guest access-violation record.

Three five-second audit captures pin the visual observations. The videos are
private runtime evidence and are not distributed with Mod Studio.

| Evidence basename | SHA-256 |
| --- | --- |
| `apf-roster-token-preserving-team-name-consumption-20260718.mp4` | `f8b14cd8df3e17586297f758aeb19d7ada54b3876e7e8fdc047557c21ff81bf9` |
| `apf-roster-team-summary-codexteam-20260718.mp4` | `ec1cd8ee93d6cf0d8248cf35b199f1fc7b361dabf9080c41a43d5160a55d8c8b` |
| `apf-roster-team-select-codexteam-20260718.mp4` | `b8fa43e02396fd3d9e2363134ff63c26d8d3ab02b3478b9063fa1c95c0610e52` |

## Capability boundary

The proved capability is deliberately narrow:

- **Runtime-proved:** one built-in team display-name allocation and one
  unaliased player last-name allocation, edited in place and rebuilt with the
  retail-token-preserving H7A route.
- **Same bounded player-name product family:** Alpha.21 product-wires 3,191
  nonempty player first/last allocations / 4,482 writable references under
  their exact limits, with every shared-allocation alias owner disclosed.
- **Offline-proved but not yet runtime-proved through the repaired route:**
  team abbreviations, secondary abbreviations, and other mapped identity
  families.
- **Not unlocked by this experiment:** jersey numbers, ratings, positions,
  abilities, membership, depth charts, team-count changes, or roster-size
  changes.

The Alpha.21 product surface promotes team display-name and player
first/last-name editing because every admitted project load and Build is forced
through a centralized pure-scope check and this token-preserving compiler,
enforces the original UTF-16 allocation limit, and exposes alias ownership.
Abbreviations stay Preview until their own one-variable repaired-route spot
check visibly renders the new value.

## Safety and distribution

The user's source game remained read-only. The test build was an atomically
published, separate game directory; all bytes outside the one changed outer
entry matched the source, and all unchanged sibling assets were verified.

The Alpha.21 public-product smoke repeated the proof through only supported
product actions: load, replace Dan's last name with `CODEX`, Undo, replace,
individual Revert, replace, save a project, reopen it, Build a separate 3.7 GB
game, and reparse the output. The 989-byte project contains replacement JSON
only and has SHA-256
`45902ead474bfd868c88469220076e3cd23a47e7a58c3fa568129e1bb743694e`.
The built `0A` SHA-256 is
`0212b638c1cdfa348110e57dbef4af5e0048101ff340202f52fec2021cd54044`,
which exactly matches the prior runtime candidate. Only outer 1126 changed,
the ROST reparsed successfully, and the source remained unchanged. The private
`product-smoke.receipt.json` has SHA-256
`6e0c84222ba28ce89f96f79e6cccb482ef1d9aa771d7e59a06ad3fe865d88f70`;
its runtime-equivalence section records the matching candidate and prior video
hashes rather than merely asserting equivalence in prose.

Fresh isolated-display visual QA also passed after the UX fix. **Identity &
Names** defaulted visible with **Base Ratings (28)** adjacent. **Replace Player
Name**, **Revert Player Name**, and **View 23 affected fields…** were all visible
with the exact `4/4` limit and no clipping or scroll trap. A separate
retail-free product-code dialog check displayed all 23 owner rows at once with
high contrast. Neither check touched the user's live desktop or pointer.

A built game contains the user's retail data and must never be distributed.
The shareable project contract stores only user-authored replacement text and
non-content metadata—never the retail `ROST`, original strings, preimages, or
physical offsets. Alias-owner lists also stay local and do not enter a project.
Alpha.21's complete product regression passes `648/648` in `90.763s`, and it is
the current packaged checkpoint. Verify its archive with the authoritative
adjacent `.sha256` sidecar. The corrected `607,218`-byte archive has SHA-256
`35b7d23298ce69639ad7e2a09b24be4838de6066d22963abaf0f387dd3d4e232`;
its `119`-byte mode-`0444` sidecar verifies. Package-facing docs intentionally
avoid embedding their own circular archive hash; this source report and the
source `STATUS` were updated after sealing. An independent audit rejected and
deleted the first regenerable candidate for stale Alpha.20-current /
Alpha.21-pre-seal wording, and only the corrected rebuild was sealed. Alpha.20
is the preserved previous checkpoint at SHA-256
`f3f02cbefbbcd5f0890efb889948e2a34487a9f07f0a2900744d44b19da56ef8`.

## Best next proof

Run a bounded same-allocation XMA replacement feasibility experiment. If a
safe, distributable replacement route cannot ship, move directly to bulk roster
authoring instead of extending the audio loop. Later, run one-variable
abbreviation candidates through screens that visibly consume them. Do not infer
abbreviation or 53-active-roster support from the player-name result.

## Related documents

- [Bounded roster identity writer](APF_ROSTER_IDENTITY_WRITER.md)
- [Historical generic-transport negative](APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md)
- [Static trace of the historical crash](APF_ROSTER_CRASH_STATIC_TRACE.md)
- [32-team and 53-player feasibility](APF_32_TEAM_53_ROSTER_FEASIBILITY.md)

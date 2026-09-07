# MyCareer in-game mode milestone report

2026-09-07, branch `astra/r64-mycareer-mode`, starting commit `c450b2d`.
**EXPERIMENTAL / UNWITNESSED.** No game boot, played game, rendered menu,
console save, audio, GUI, network access or push occurred.

## Milestone status

| Milestone | Status |
| --- | --- |
| M1: complete mode design and native prerequisite evidence | Complete; bundle commit and DONE receipt accompany delivery |
| M2: in-game creation, placement, franchise, hub and game loop | Not complete; follow-up work below must not be presented as a mode |
| M3: calendar, card, depth, upgrades, requests, art and auto-save | Not complete |

M1 delivers `ASTRA_MYCAREER_MODE_DESIGN.md`, an explicit feature/native map,
save candidate and field layout with its ownership gate, game and Practice
return contracts, CPU/off-field decision, budgets, Fable asset requests and
milestone acceptance criteria. `WIRING.md` supplies every protected integration
surface and clearly distinguishes future changes from M1, which changes no
production hook, allocator request, capability or Build behavior.

`tools/nfl2k5_my_career_mode_audit.py` is a bounded read-only evidence command,
with nine literal native-function pins and twelve descriptor words, refusing
foreign/oversized evidence. It emits JSON describing the current owner and
explicitly refuses to call the proposed save bytes an allocated region.
`test_nfl2k5_my_career_mode_routes.py` adds actual native prerequisite execution;
it does not stub out creation and pretend a complete mode ran.

## PROVED and HYPOTHESIS

**PROVED:** current entry still requires a per-disc seed and a prepared draft
save. Existing persistence is an external `U:` journal, not bytes in the
franchise save. The current any-position binder, CPU ownership and once-only
ledger remain unchanged and pass their original tests.

**PROVED in new bounded execution:** the native creator selects a free created
PRIMARY record, initializes its existing name storage and college reference,
and pushes the actual player editor `0x56F050`, with no MyCareer seed. A full
pool does not push or mutate records. Selecting an existing created player
uses a distinct native branch; a new-career adapter must explicitly avoid
that branch. The probes execute `0x3461F0`, `0xBFF00/0xBFF50`, `0xC0A80`,
native string copying and PUSH; only RNG and descriptor rendering/event
delivery are external substitutes. This is not installed Game Modes entry.

**PROVED in new bounded execution:** native Franchise Options advance runs
its validation, calls `0x10EA10` then `0x13EE10`, and pushes `0x52ABE0` only
when accepted. Those two initializers are stubs in this specific call-order
test, so their internal work and a completed new franchise are HYPOTHESIS.
The design calls this out instead of calling a mocked initialization proved.

**PROVED in new bounded execution:** complete native season load `0xC5800`
and save `0xC5310`, including their stat serializers, round-trip the 128-byte
tail at file `0x9967C..0x996FB` for three patterns. Source bytes and output
canaries are checked. Empty substate 3 clears that region. Its normal
preservation is real evidence; its availability for MyCareer is **HYPOTHESIS**.
Only the two explicit tail constructions were found in a linear `.text`
operand census; computed-index access and lifecycle ownership need further
proof. No production save writer is authorized by that negative census.

**PROVED:** native coach-mode predicate does not implement a skip command.
**HYPOTHESIS:** CPU drives at normal speed, playable position-specific behavior,
human play-call gating, creation completion/placement, a distinct hub's game
return and stable save/load. No native possession-skip routine is identified.
The requested shared auto-save implementation is absent from this checkout;
the design proposes an adapter contract, not a fabricated address.

## M1 validation and receipts

All suites ran standalone, plain Python, no skips. Commands are relative to
this checkout; logs and `/usr/bin/time -v` receipts are in
`.scratch/mycareer-mode/` and are excluded from commits.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | 13 passed, 20.088 s |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | 18 passed, 11.754 s |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_routes.py -v` | 7 passed, 2.748 s |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_audit.py -v` | 2 passed, 0.044 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed, 306.119 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 95 passed, 391.941 s |
| `python3 tools/nfl2k5_my_career_assemble.py --check` | Template verified |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | PASS, 41 requests |
| `git diff --check` | PASS |

**214 passing tests.** Both gates use the complete owner union, forward and
reverse application, status checks and replay. They passed with the checked-in
manifest; no protected manifest replacement or freshness exemption was used.
Peak measured process RSS: **499,292 KiB**, below the 2 GiB test bound.

Read-only audit reproduction:

```sh
python3 tools/nfl2k5_my_career_mode_audit.py \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'
```

`M1-audit.json` pins retail
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
`M1-writer-receipt.json` records the unchanged existing owner's seedless
installation, exact edit receipt and zero-change identical replay; its XBE
hash is `d396fa02e54be144a4bf9c5210170fb97568aed4573f099b586fce6a7b64b842`.
That unconfigured old-owner XBE is NOT a playable new-mode recipe.

Root free space was 108,010,352,640 bytes at M1 verification. No disc or pack
copy was made; a 6.3 GB disposable image would consume the floor's headroom.
Only bounded executable/synthetic save reads were used. Scratch stays below
200 MB; no acceptance disc is left behind.

## Noah's witness list, all pending

1. Boot a generic patched disc with no MyCareer.json, no prepared draft save
   and no title-journal file. Choose MyCareer, create MyPlayer with name,
   college, position and attributes, choose a club, and reach the apartment.
   Cancel on every creation page and restart without consuming another slot.
2. Verify nine hub rows, long names, focus, controller footer and art at 4:3
   and widescreen. Back from every child, dialog and nested page reaches a
   usable hub. Explicit Quit alone leaves it. Repeat at root and above Main
   Menu, including Save and load errors.
3. Create separate QB, HB/FB, WR, TE, OL, DL, LB, DB, K and P careers. Play
   snaps at each position. Verify human play calling only for the correct unit
   while MyPlayer is present, CPU teammates and no control transfer after
   turnover, handoff, catch, fumble, substitution, injury or inactive status.
4. Watch off-field drives through possession changes, timeout, halftime and
   overtime. Verify no stuck snap or menu and honest off-field status text.
   Any Skip control must have a working proved action.
5. Launch/quit/cancel/resume/repeat franchise Practice, then a scheduled game,
   then Practice again. Every end returns to the apartment with valid menu
   state; Practice does not advance the calendar or award game XP.
6. Complete games, byes, final regular week, playoffs and season rollover.
   Verify native score/stats/injuries/progression, next opponent and once-only
   25-point participation award. Abandon a game and follow native result rules.
7. Open the correct MyPlayer card, season and career stats; edit the team's
   depth chart, select starter on the intended side, advance a week and check
   lock persistence and CPU roster management.
8. Buy attributes through every price tier and cap, cancel confirmation, and
   check exact balance/rating changes. Preserve all style, lock and ability
   fields. Test insufficient points and native progression between purchases.
9. Request a trade or demand release, save with the request pending, reload,
   advance a week, and verify a different legal club with correct old/new depth,
   salary and transaction history. Check cancel and unavailable-team handling.
10. Verify auto-save after each committed game, manual Save, cancelled Save,
    failed Save/retry and cold reload. Copy the ordinary signed career save
    to another patched disc with a different allocator layout and no journal.
    Load two different careers on the same disc and verify identity, balance,
    watermark, team and pending requests never cross between them.
11. Exit to ordinary Franchise and ordinary Create Player/Practice. Confirm
    their menus, rosters, settings, save/load and return routes remain native.

## Delivery discipline

The worktree's Git directory resolves outside writable roots, into
`/home/noah/2k-football-mod-tools/.git/worktrees/astra-r64-mycareer-mode`.
Use the requested bundle fallback with isolated Git metadata under `.scratch/`,
read-only access to existing objects, and explicit-path staging/commits. Keep
edits in this worktree. No original repository metadata, protected product
file, brief, scratch artifact or generated game payload is part of a commit.
Each completed milestone gets `.scratch/M<n>.bundle` and `.scratch/M<n>_DONE`.
Unfinished milestones do not get a misleading DONE marker. No push.

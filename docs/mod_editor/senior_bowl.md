# Senior Bowl: component contract and native implementation boundary

**EXPERIMENTAL / UNWITNESSED. The native simulation MVP is not complete.**
There is no live stage detour, game simulation, native save extension, native
screen or scouting-card hook in this revision. Do not use component tests or
`status == "applied"` to enable a game option. `simulate` refuses, the Studio
button is disabled, all presets remain off, and every installation receipt
contains `native_event_available: false`, `retail_hooks: 0`, `save_growth: 0`.

The delivered host workflow reads a signed franchise save, scans its current
primary pool and ownership, previews two balanced squads, configures four
verified kit donors, and saves independent preview projects. The native code
is dormant, reproducible groundwork. No Xbox save or disc is written by the
preview panel. The handoff in WIRING.md exposes preparation only.

## Current selection and identity contract

Scan every primary record, up to 4096. Require allocated flag `+8 & 4`, current
prospect `+8 & 0x10`, no drafted `+8 & 0x20`, and no active, reserve, free-agent,
injured-reserve or all-star-list ownership. Validate live list entries and
counts. Do not rely on the old first-year index window or cached display group.
Reject repeated primary indices, invalid positions and classes over 512.
The retained map contains all eligible prospects, including nonparticipants.

Each team gets the memo's 53-player quota. Position codes use the shipped
roster codec: QB 0, K 1, P 2, WR 3, CB 4, FS 5, SS 6, HB 7, FB 8, TE 9,
OLB 10, ILB 11, C 12, G 13, T 14, DT 15, DE/EDGE 16. One-pool combines
OLB/ILB at 11 (seven per side), leaves EDGE at 16 and refuses eligible OLBs
still carrying retired code 10. It never changes those records to fit.

Sort each position's eligible players by primary index. Rotate the first
selection by `((seed XOR (position * 0x9E3779B9)) & 0xffffffff) % count`,
then alternate sides, starting with `(seed XOR position) & 1`, until twice
the quota has been selected. This is a deterministic selection policy,
not a talent/rating ranking. A missing position refuses the whole selection;
no veteran or wrong-position substitute is inserted. The full class remains
visible when a squad cannot be completed.

Class SHA-256 includes scheme, sorted indices, position/flags, decoded name,
college and pointer-free record identity/attributes. Source pointers are
never serialized. A 16-byte nonzero franchise ID is supplied by the caller
and stored with the event. **Its native creation and save identity binding
remain unresolved.** Host helpers do not invent a stable native ID from the
mutable save-file hash. The preview itself does not need one.

Verified donors are 50A0.IFF, 50H0.IFF, 51A0.IFF and 51H0.IFF, defaulting to
50A0 versus 51H0. Bank 51 is an alternate donor, not retail USER2's bank;
USER1/USER2 IDs 90/91 are team IDs. Other banks/eras refuse until their
packages are verified. Configuration changes no shared uniform resource.

## SBN1 development event format

An event is exactly 16384 little-endian bytes. This is a proposed separate
event blob, **not an approved SAVEGAME.DAT trailer or Xbox save member**.
CRC-32 detects accidental corruption; it is not authentication or signing.

| Offset | Bytes | Content |
| --- | ---: | --- |
| 0 | 4 | `SBN1` |
| 4, 6 | 2 each | Version 1, header size 256 |
| 8, 12 | 4 each | Total size 16384, CRC-32 over bytes 16..16383 |
| 16, 20, 24, 28 | 4 each | State, season index 0..127, seed, scheme enum |
| 32 | 16 | Franchise identity |
| 48 | 32 | Class SHA-256 |
| 80, 82 | 2 each | Eligible class count, participant count (0 or 106) |
| 84, 87 | 3 each | Away/home bank, ASCII side A/H, era 0 |
| 90 | 10 | Reserved zero |
| 100 | 20 | Away five quarter scores then home five (u16, fifth is aggregate overtime) |
| 120 | 96 | Twelve signed i32 team totals per side, in TEAM_STATS order |
| 216 | 40 | Reserved zero |
| 256 | 2048 | Up to 512 class rows: u16 index, u8 position, u8 zero |
| 2304 | 8480 | 106 rows, 80 bytes each: u16 index, u8 position, u8 side, 36 i16 stats, four zero bytes |
| 10784 | 5600 | Reserved zero |

All unused class/participant entries are zero. State values are 1 pending,
2 running, 3 complete, 4 skipped. Zero allocator memory is uninitialized, not
a valid serialized event. Schemes are 0 retail, 1 edge, 2 one_pool.
`PLAYER_STATS` and `TEAM_STATS` in the module define exact field order. Sacks
are counted in half-sack units. Signed yard fields allow losses. The host
codec checks sorted unique membership, full positional quotas, exact selection
from seed, numeric bounds, counted-stat relationships, scores and team yards,
all reserved bytes, and expected franchise/class/year. It re-encodes to demand
canonical bytes. Running restores as pending with the same seed and no result.
Completed and skipped records remain terminal for their year after draft
flags/ownership change. Pending identity changes refuse. Stock ratings,
perceived draft stock and CPU scores are never edited.

`Event.scouting_line` returns only a separate result for an actual participant
in a complete supplied record. This is a host projection, not a native card.
Tests use explicitly synthetic result fixtures. No fake game result generator
or test simulator is shipped.

`save_event` and preview projects use bounded same-directory temporary files,
flush/fsync, close, then `os.replace`; failure before replacement preserves the
old target and removes the temporary file. Xbox save/signature/XBE filenames
are refused. Event files and projects never change franchise totals. This
does not establish Xbox file transport, power-loss behavior or OS signing.

## Native components and their exact proof boundary

Owner requests are 4096 RX (16 aligned) and 65536 RW (4096 aligned), inside
the assigned 16384/65536 budget. The remaining 12288 RX bytes from the estimate
are unrequested, not available by guessed address. Realized addresses come
only from the complete selected allocator union. No retail cave is used.

RW event is at +0, staging at +0x4000. Planned, **unused** workspace regions
reserve two 500-byte teams at +0x9000, 106 84-byte players at +0x9400, and
two 168-byte coaches at +0xB800. This revision does not construct runtime
team/player/coach clones or prove eleven-personnel lookup. All disk RW is zero.

The GNU .S source assembles to the checked-in Python template without runtime
compiler dependencies. The private cdecl component ABIs are:

| Routine | Arguments | Result / scope |
| --- | --- | --- |
| sb_gate | event, year, stage, days, untouched-hours | 1 hold Combine, 0 pass, -1 invalid; component policy only |
| sb_select | normalized 8-byte rows, count, seed, scheme, scratch event | class count, -1 malformed, -2 shortage; writes scratch only |
| sb_crc | bytes, count | Standard reflected CRC-32 |
| sb_check | event, length | Envelope/CRC/bounds only, **not full semantic validation** |
| sb_save | buffer, exact capacity | Copy valid owned event to external buffer, 1/0; no I/O |
| sb_load | buffer, exact length, expected identity48, year | Envelope/identity check and copy, running to pending; no I/O |
| sb_simulate | none | Always -6; no native simulator call or event mutation |

Normalized input rows are `<IBBBB`: index, position, original flag byte,
owned boolean, reserved zero. They must cover a validated primary snapshot
sorted by unique index; at most 4096. This is **not a native ROST scanner**.
The native selector is differentially tested against the host policy. The
codec's native semantic validator is intentionally incomplete and must not be
installed as a game load callback. Caller buffers must be mapped/disjoint;
copy routines additionally reject wrap and overlap with owned RW. Stack and
all nonvolatile GPRs/DF are checked. No x87/SSE instructions are introduced.

Unicorn maps the actual allocated component bytes RX and owned state RW;
it executes no retail simulator, Xbox kernel, GUI renderer or save transport.
Inputs and outputs are bounded. Tests stop at a supplied return address with
2.5 million instructions maximum per call (three for simulation refusal).
The static gates compose the dormant owner with all landed owners in both
orders and inspect full instruction writes/allocation ownership. Those are
component/placement proofs, not the requested native MVP acceptance.

## Required native MVP work, in dependency order

The read-only authority is the hub's SENIOR_BOWL_RESEARCH_2026-09-05.md §2-4.
Retail XBE SHA-256 is 73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9.
The following additional byte observations are PROVED; proposals remain
HYPOTHESIS until executed with meaningful caller/write-boundary checks.

1. **Persistence first.** Retail season serializer call is at 0x16E4F5 to
   0xC5310, size getter at 0x16E4FA to 0xC5300, front-office serializer at
   0x16E50D to 0x2D0790, final write at 0x16E524 to 0x16C2F0. Its complete
   save buffer was allocated at 0x16E4A9 (0x48700) with size in EBX. Restore
   calls 0xC5800 at 0x16E7F8, size at 0x16E7FD, front office 0x2D0CE0 at
   0x16E810. These callsites establish no optional member/trailer contract.
   Trace the franchise size getter (0x16AA10), metadata/type/version, file
   size acceptance, signature coverage, allocation, write completion and
   failed/short-write behavior before choosing an optional member or append.
   Preserve signed legacy length 720044 and the mode/stage/substate meanings.
   Never borrow opaque save padding, team tails or live substate 0xE576A8.
   A separate optional member requires a durable franchise key, its own seal,
   and a two-file atomicity/recovery protocol. A signed optional trailer
   requires size/version/read/sign checks on every caller, plus host save
   reader support; neither is implemented. Extend native sb_check to the
   host's complete semantic validation before exposing any load bridge.
2. **Runtime class and squads.** Build the normalized snapshot by bounded
   live root/primary/owner scans with no cached pointers across a save load.
   Stage 4 entry with four untouched days can create one record; legacy
   mid-combine or consumed hours marks skipped. Build cloned 500-byte teams,
   84-byte players and coaches into the named workspace, zero unused slots,
   redirect history +0x2C and sim scratch +0x30, configure depths and all
   special-team selectors on clones only. Validate installed PLAY/venue donors
   and every eleven-personnel/specialist lookup. Avoid the 0xFFFF result of
   reverse league lookup 0xC4CA0 for temporary nonleague teams.
3. **Simulator audit and isolation.** At 0x10B9DB the scheduled wrapper calls
   core 0x10B940, then 0x1356D0 at 0x10B9E0 commits franchise results. Core
   ABI is unusual: it consumes five stack words (`ret 0x14`) and also uses
   incoming EAX/ECX/EDX. Replay actual callers before defining the bridge.
   It initializes 0x10B280, ticks 0x10B250 until 5/-1, and finalizes 0x1053B0.
   Finalizer reaches 0x105060, which performs writes through `[player+0x30]`
   at 0x10507B and following instructions; a cloned +0x2C history pointer
   alone is insufficient. Audit the full reachable write set, including
   0x251880 reached through 0x1047B0. Capture native readers 0xCB240/0xCB2D0
   into the ledger before cleanup, retain seed/RNG/context, and never invoke
   scheduled wrapper 0xC7A20 or persistent commit 0x1356D0. Prove byte-equal
   persistent roster/history/contracts/injury/fatigue/progression, standings,
   schedules, awards/news and coach totals on success and every failure.
   Refusal tests in this revision are not this proof.
4. **Preamble and UI.** After persistence/sim proofs, intercept all Combine
   navigation and advancement, including automatic 0x2486F0, without consuming
   a week/day/hour twice. Do not renumber stages. Coordinate an additional
   Coach's Desk row with the shipped Practice Squad relocated table; do not
   overwrite its pointer or assume another free retail row. Clone roster,
   class and result descriptors with private count/get/sort/activation state.
   Resolve sorted rows to actual prospect identities, disable transactions,
   provide Simulate, Skip and Back, retain event results after other games,
   and bind the event-only line in scouting without affecting draft scores.
   Execute actual screen construction, callback expansion, rebuild and teardown
   before claiming native UI support. No descriptor or callback is installed here.

## Exact playable follow-up specification (deferred)

Prerequisites: every native MVP proof above green, followed by Noah's sim/save
witness. Reserve another 4096-8192 immutable bytes through an explicit revised
union, inside the owner's 16384 total ceiling if the final MVP leaves room;
otherwise request a new budget rather than use another owner's allocation.

Use scored exhibition-style mode 4, not Franchise Practice's mode 1. Trace the
team setters 0x77AE0/0x77B20, venue/settings 0x134040 and physical controller
assignment ABI. Retain an owned event flag and a snapshot of franchise stage,
substate/week/slot, teams/playbooks/venue, controller sides, menu return context
and all globals the launch path changes. Pending must survive settings cancel;
running must recover to pending after quit/interruption with the same seed.
Normal completion, overtime and abort must restore the surrounding context.
Gate the played result commit at 0xEC65A only for a validated active event;
ordinary games and Pro Bowl retain the original call exactly once. Capture
the same ledger before cleanup; a completed event cannot award or commit twice.
Compose the 0x6160F..0x61670 uniform rule with nfl2k5_uniform_choice, resetting
its flip/era settings on every completion/cancel/abort route. Exercise all
controller sides and special teams, then the next ordinary franchise game and
stock Pro Bowl, before exposing controller play. No playable implementation
or mode-4 return ABI is claimed.

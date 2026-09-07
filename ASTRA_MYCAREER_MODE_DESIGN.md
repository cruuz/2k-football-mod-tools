# MyCareer in-game mode design, milestone 1

2026-09-07, `astra/r64-mycareer-mode`, base `c450b2d`.
**EXPERIMENTAL / UNWITNESSED.** This is an implementation contract with
audited native prerequisites. It is not a claim that the mode exists yet.
PROVED means pinned bytes or the explicitly bounded instruction tests below.
HYPOTHESIS means an unproved connection, ownership assumption, or gameplay
behavior, with the necessary proof specified. Noah alone supplies played
witnesses. Design decisions are requirements, not observations.

The product contract is one patched disc for all careers, no Studio or external
save preparation, Create MyPlayer in the game, a distinct apartment hub, games
and practice with control of MyPlayer only, advancement and saving. The hub
also exposes the requested career management and information. Every child
returns to its parent inside MyCareer; unwinding the parent chain reaches the
hub. Only the explicit Quit to main menu action leaves the mode. Do not rename
Coach's Desk globally or present the existing developer setup as this mode.

## Starting point and corrections to the brief

**PROVED:** `FABLE_MYCAREER_REPORT.md`, `ASTRA_MY_CAREER_REPORT.md` (the actual
filename has an underscore), `ASTRA_MYCAREER_COMPOSE_REPORT.md`, the current
owner and assembly establish the existing entry, binder, identity, starter
lock, CPU ownership and checkpoint implementation. The assembled template at
this base is 4,900 bytes; its per-disc seed adds 1,280, totaling 6,180 of
8,192 RX bytes. RW capacity is 4,096 and the visited-controller array ends at
byte 3,312. No new allocator page is needed just to investigate the mode.

**PROVED correction:** the checkpoint is NOT stored inside the franchise
save. It is a separate 64-slot title-data journal, `U:\MyCareer00.dat` through
`U:\MyCareer3F.dat`, paired by two hashes of all 720,044 save bytes. The disc
also contains one player's recipe. The current entry with no seed refuses to
push any screen. The journal may lose an older snapshot through slot reuse.
None of these are acceptable persistence mechanisms for the new mode.

**PROVED correction:** Practice's current return fix recognizes the exact
stack `Coach's Desk -> cloned settings -> Team Select`, not any arbitrary
parent. `ASTRA_PRACTICE_EXIT_V2_REPORT.md` supersedes the earlier exit report.
The fixed native Main Menu unwind at launch must be handled when substituting
a new hub. Setting a late return flag is insufficient.

Also read for reuse: the PS native screen, depth locks, modern naming,
allocator scaleout, roster arena/storage, season cap, calendar, Franchise 2026,
Senior Bowl, Crib backend, scorebug/hires resource and latest integration
reports. The latter two franchise experiments contain dormant components;
their installed status does not certify a playable engine extension. The
RC85/RC86 changelog is historical scope, not stronger evidence than the
current owner and latest correction reports.

## Mode map and native boundaries

```text
Game Modes / MyCareer
  fresh entry -> Create MyPlayer -> Choose team -> Start franchise -> Apartment
  existing career -> native Load / Save -> validate saved identity -> Apartment

Apartment
  Play next game -> native schedule selection / pregame -> game -> Apartment
  Practice -> franchise practice settings -> Team Select -> rep -> Apartment
  Schedule -> calendar / fixture detail -> Apartment
  MyPlayer card -> season / career / ratings -> Apartment
  Team and depth chart -> native depth editor -> Apartment
  Requests -> request trade / demand release / cancel request -> Apartment
  Upgrade -> choose rating / confirm cost -> Apartment
  Save -> native signed save UI -> Apartment
  Quit to main menu -> save prompt -> native teardown -> Main Menu
```

Creation cancellation returns to a MyCareer entry hub with Create MyPlayer,
Load career and Quit. It must release the uncommitted created slot, clear all
transient callbacks and preserve the source roster. A cancelled creation must
not call the new-franchise initializer or install a half-valid identity.

| Requirement | Native evidence and proposed connection | Proof still required |
| --- | --- | --- |
| Entry | **PROVED:** Game Modes row `0x501494`, kind 9, action at `+0x28`, list dispatcher `0x150020`, PUSH `0x6E390`. Existing four-word owner edit already composes. | **HYPOTHESIS:** seedless entry selecting Create/Load and the cancellation hub. Execute installed dispatcher, creation and all cancellation paths with a disc containing no player bytes. |
| Create MyPlayer | **PROVED:** `0x525768 -> 0x56E9C4` is the created-player list. Accept record `0x56E7D8 -> 0x3461F0`. Editor `0x56F050`, Appearance `0x56ED80`, Equipment `0x56EBA0` use handler `0xF40F0`. | **HYPOTHESIS:** skip the general edit-existing-player list for fresh MyCareer. Explicitly allocate a new slot; do not accidentally edit the list's first existing player. See the new native tests for that distinction. |
| Record location | **PROVED:** allocator `0xBFF50` scans the PRIMARY pool `[root]`, `[root+4]`, stride 84, for `record+8 & 1` set and `&4` clear. `0xC0A80` initializes it preserving name storage pointers. `0xCB8B14` holds the editing pointer; `0xCB8B98` identifies a new slot. | **HYPOTHESIS:** capture its ordinal and immutable fingerprint only after the final successful commit. Never persist `0xCB8B14` or a native RAM pointer. Prove full-pool refusal and cancellation leave all other players untouched. |
| Name, college, attributes, position | **PROVED:** the existing native sheets and Rosters codec expose these fields. College cycles through `0x343CC0/0x343CE0`; record `+0x35` is position, `+0x36..+0x51` are 28 rating/style bytes. Three CAP templates per supported position at `0x5561B8`, applied by `0x343460`. | **HYPOTHESIS:** every desired choice is usable from the new entry across all 17 positions. OL/DL lack the 12-position CAP template table, so use explicit balanced starter ratings under codec rules, never an out-of-bounds template index. |
| Creation completion | **PROVED:** `0x346C50` normalizes the record, marks `+8 &4`, resolves club/FA ownership, appends an unowned player to `root+0x38` with `0x242560`, then POP-TO `0x56E9C4` at `0x346D40/0x346D77`. | **HYPOTHESIS:** intercept only a career-owned successful commit and replace that return with placement. Preserve ordinary CAP, equipment Back, cancel confirmation and all native destructors. |
| Placement | Decision: **choose one NFL team**, sign as an undrafted rookie before preseason. Do not call this a draft. Native helpers: FA removal `0x2425C0`, team removal `0xC3EB0`, append `0xC3EE0`, compactor `0x243790`, salary `0xC3F00`. Acquisition UI `0x2B8310` demonstrates their sequence. | **PROVED:** helper sequence and roster codec transactions. **HYPOTHESIS:** career-specific admission, contract and full-team handling. Validate source identity, no IR/reserve/FA duplicate, destination capacity and contract before any mutation; refuse unavailable teams visibly. |
| Franchise start | **PROVED:** options descriptor `0x500DC8`, advance `0x148CC0`: validate `0x148AB0`, initialize `0x10EA10`, then `0x13EE10`, PUSH Customize League `0x52ABE0`. `0x13EE10` initializes league, cap, orders, team salaries and draft generation using the current roster. Final `0x13F1B0` calls native setup and pushes Desk at `0x13F2D9`. | **HYPOTHESIS:** a defaults-only path may bypass Customize League, but must execute its initialization work. Trace the stage transition and finalizer before implementing that bypass. Do not merely set mode/stage/week globals or fabricate a preseason save. |
| Apartment hub | **PROVED:** generic native list family `0xF3E90`, descriptors of 44 bytes, rows of 52, type-3 terminator. PS proves owned clones plus immutable rows/strings and native lifecycle. | **HYPOTHESIS:** a new list descriptor, own hooks, own layout and RW state. Use generic menu lifecycle, not the Desk's 3D scene/update callbacks. Validate all nine rows, empty/no-player states and renderer resources. |
| Play next game | **PROVED:** schedule launcher `0x142880` fades and queues `0x522828` through `[0xAA2408]`; event-1 callback `0x327A00`; fixture grid `0xE57C40`, 22 rows of 17 eight-byte cells. Existing `career_fixture` and `sim` distinguish the career fixture. | **HYPOTHESIS:** preselect the earliest outstanding career-team fixture, run native pregame, refuse whole-game sim for it, and advance other fixtures through normal schedule logic. Bye/offseason uses an explicit Advance week action, not a nonexistent opponent. |
| Return from game | **PROVED:** game descriptor `0x4E7EC0`, ended update `0x650A0 -> 0x64CD0 -> 0x6E400`; teardown `0x64CA0 -> 0x649C0 -> 0x645D0`; franchise commit path `0xC5D60`. | **HYPOTHESIS:** the installed new hub remains a valid parent through launch, postgame and load. Execute the full stack chain and hub event-3 rebuild, including failed loading, not just an assertion that a callback returned its address. |
| Save | **PROVED:** native Load/Save descriptor `0x508DF0`; Save Franchise is represented at `0x508E24`; the existing game signs its standard container. Serializer/load boundaries below are explicit. | **HYPOTHESIS:** initialize the native save operation context from a hub action, handle overwrite/cancel/failure, and return to hub without bypassing signature generation. A WriteFile hook after signing cannot alter signed bytes safely. |
| Quit | **PROVED:** Desk's `0xC8190` confirmation, roster teardown `0xC0110`, season reset `0xC7570`, screen clear `0x6E480`, Main Menu `0x515660`. Pause Quit `0x6EBE0` first returns to the game and marks it ended. | **HYPOTHESIS:** only the hub's explicit exit uses full franchise teardown; child/pause exits preserve hub and identity. Save prompt Cancel stays in the hub. |

Draft version: create MyPlayer before the genuine Combine/Draft stage,
reserve a real generated prospect ordinal, inject after the final generator,
then allow native draft and signing. Existing `inject`/`overwrite_guard`
provide parts of that path. Starting a fresh rookie at a normal preseason
without simulating the preceding season requires a certified native initial
draft path; neither the Studio draft-save replacement nor a stage-word write
provides it. Draft presentation is outside v1.

## Player control, play calling and off-field progress

**PROVED:** retain the existing binder and its full set of attachment,
copy/reset, selection and transfer guards. Match record derives from
`0xC3C60`, not the possession team or player name. Per-frame `0x1563F0`
decodes bodies with a controller; the body's native context is restored by
`0x1565F0 -> 0x120880`. A missing, inactive, duplicate or cyclic body list
detaches the port. CPU teammates keep their callbacks. Camera focus uses
`0xA5947`; the current camera owner's session settings take precedence.

**HYPOTHESIS:** physical control of routes, blocking and pre-handoff mesh
behavior works for every position. Port attachment proves identity and input
delivery, not that every body behavior consumes every human command. Witness
QB, HB/FB, WR, TE, C/G/T, DT/DE, OLB/ILB, CB/FS/SS, K and P separately.

Play-call policy is an explicit new feature. Offense codes **0, 3, 7, 8, 9**
(QB, WR, HB, FB, TE) call offense only when MyPlayer is on the field on that
unit. Defense codes **4, 5, 6, 10, 11, 15, 16** call defense only when present.
K/P and C/G/T receive the CPU's call. A turnover does not temporarily give
control of the other unit. No selection hook may transfer input to another
player. The team's `+0x30` human field remains clear for CPU club management.

**HYPOTHESIS:** hook the native play-call eligibility consumer, separately
from controller ownership and CPU front-office getter `0xC4D50`. A global
human-team toggle would reenable unwanted CPU-management paths and is not the
design. Required proof: inventory the menu eligibility reads and their call
contexts, run QB/WR/defender/bench/special-teams cases into the actual native
play-call constructor, then verify snap/play selection/clock progression.
An on-field binder success alone must not mark this feature complete.

| Off-field candidate | Verdict and cost |
| --- | --- |
| Native sim to next possession/quarter | **HYPOTHESIS, not located.** No identified descriptor, callback or ABI supports a claim it exists. A text search failing is not proof of absence. Need live-match state, score/clock/injury/stat merge and a next-appearance stopping condition. |
| Whole-fixture sim `0xC7A20` | **PROVED** whole-fixture behavior and current exclusion of career-team games. Cannot splice it into a live drive. Keep it for other fixtures only. |
| Coach mode `0x63810`, setting `0xE6002C` | **PROVED** predicate: disabled for modes 0/3 or FPP, otherwise returns the setting. **HYPOTHESIS** for a speed/skip function; the predicate provides neither. Do not fast-forward by changing a frame delta, which changes physics. |
| CPU drive at normal speed, status cue | Chosen **v1 fallback**, conditional on stability proof. **PROVED** binder detaches and leaves CPU callbacks. **HYPOTHESIS** that all drives snap, select plays and finish without human input. Use plain `Watching the other unit` text. Do not display a functional Skip prompt until a proved skip action exists. Test turnovers, timeout, halftime, overtime and injured/benched careers. |

No off-field path earns appearance XP. If the normal-speed path requires a
human snap or gets stuck in play calling, v1 is not ready. A misleading skip
prompt would not satisfy the fallback in the brief.

## Calendar, MyPlayer card, depth and progression

Schedule v1 uses the real franchise schedule and its week/stage data, constrained
to the career club, with other fixtures available as read-only results. The
landed calendar owner supplies date arithmetic; it does not create a new
calendar view. **HYPOTHESIS:** a monthly calendar clone can sit above that
native schedule after the filtered fixture path is proved. No invented dates,
fake opponents or alternate source of standings.

**PROVED:** player `+0x2C` points into the season-history stream; root
`+0x40/+0x44` are used dwords/base. `nfl2k5_team_history` documents per-season
slots, fields, terminators and folded history. Native Player Card descriptors
include `0x535E70`, `0x5360D8`, `0x536340`, `0x5365A8`, `0x536810`,
`0x536A78`, `0x536CB8`; each references Player Card text `0xEA3588`.
**HYPOTHESIS:** resolve the position-specific opener and its selection/context
ABI from the live roster, then open the exact primary MyPlayer. Preserve native
season/career/stat tabs and the game's folded-history limits. XP is not a
replacement for performance statistics, and no new historical stat stream is
necessary. A card opened with an arbitrary pointer would not prove identity.

**PROVED:** depth rows `0x5140D8`, stride 0x48, position/chain at +0x40/+0x44;
getter `0x242AE0`, swap `0x242CA0`, native edit action `0x244303`, KR/PR
`0x244360/0x2443D4`. Rank/side are separate three-bit chains in `+0x28`.
Depth locks use player `+0x52` low five bits and preserve ability bits.
**HYPOTHESIS:** open the retail depth chart for only the career team through
its actual team/context initializer. Remove the existing blanket MyCareer
restriction for this exact child, retaining restrictions on unrelated GM
screens and foreign clones. All positions can elect starter; for right-side
paired positions honor side-chain selection instead of unconditionally
asserting rank 0 means the requested side.

The native progression and CPU depth sorting remain enabled. Weekly sort at
`0x247D5C` and `0x248075` surrounds weekly processing; the existing lock owner
protects a user-selected starter. Do not replace the progression engine.
Weekly upgrade policy for v1:

| Condition / rating before increase | Point policy |
| --- | --- |
| Committed career fixture with an appearance | 25 points, once, preserving the existing participation rule |
| Practice, bye, benched, injured, cancelled/abandoned fixture | 0 points; no practice farming |
| 0..69 | 10 points per +1 |
| 70..79 | 15 points per +1 |
| 80..89 | 25 points per +1 |
| 90..94 | 40 points per +1 |
| 95..98 | 60 points per +1 |
| 99 or a legacy value above 99 | No purchase |

Balance cap is 1,000,000, rating cap 99. Show current value, +1 value and exact
cost before confirmation. Preserve style channels `power_run_style`,
`kicking_style` and `scramble`, and every ability/lock bit; they are not purchasable numerical
attributes. Use the codec's rating field definitions/masks, never a blind
increment over 28 bytes. Revalidate identity, balance and current rating after
the dialog, then debit and write together. Cancel and stale changes write
nothing. The UI uses `Upgrade points`, not participation statistics.

**PROVED:** the existing monotonic fixture watermark prevents duplicate
awards after its ring is evicted. **HYPOTHESIS:** the new compact save stores
that watermark and balance, plus pending transaction week and flags. It must
settle the completed fixture before native navigation changes year/stage; the
last game of a season is a necessary test, not just adjacent regular weeks.

## Requests: next-week team change

Decision: Request trade and Demand release enqueue one request. They do not
mutate membership in the middle of the current week. Cancellation is available
until execution. At the next committed native weekly boundary, choose a
different NFL team with legal capacity and positional need; deterministic
tie-break by team ID. Trade is a move request, not a user-controlled GM trade
negotiation screen. Release removes the old membership and signs with the new
club in the same successful transition; no intentionally stranded FA week.

**PROVED:** native roster transaction helpers and host membership/cap rules
exist (placement row above; `nfl2k5_roster_records` transactions). **HYPOTHESIS:**
guaranteeing another club by next week needs a proved full-roster path. Never
silently cut another player or ignore cap/IR/reserves to manufacture success.
Preflight all destinations before permitting a request; if none qualify, show
`No team can sign you this week` and retain the current club. This is an
explicit exception to the requested guarantee and must be removed before
calling that guarantee complete. A guaranteed version needs native CPU roster
room-making, legal contract/cap handling and transaction-log proof.

Required tests: success, full destination, no legal team, injured player,
duplicate ownership, Save/Load with a pending request, repeated weekly callback,
season rollover, cancel, native log identity, salary and old/new depth repair.
No pointers or team-object addresses go in the request record.

## Persistence: exact candidate, ownership gate and save ABI

The container remains exactly **720,044 bytes (0xAFCAC)**. Existing ranges:
settings `[0,0x2E0)`, ROST `[0x2E0,0x91320)`, season
`[0x91320,0x996FC)`, front office `[0x996FC,0xAFCAC)`.
No player-specific executable seed, external checkpoint file or extra ZIP
member may be necessary to load a new-format career.

**PROVED candidate transport:** season tail `[0x9967C,0x996FC)`, 128 bytes,
corresponds to RAM `[0xE5FB80,0xE5FC00)`. Native serializer `0xC5310` calls
`0x1346A0`; its `0x134984 -> 0x31000` copies the tail to the save. Load
`0xC5800 -> 0x1349A0`, `0x134C4C -> 0x31000` copies it back. New tests
execute both COMPLETE season routines with zero, ascending and all-FF tails,
checking source and destination canaries. Substate 3 clears the entire block
and therefore the tail. A linear Capstone scan finds only the two explicit
tail-address constructions above, but cannot exclude computed indexing.

**HYPOTHESIS / NOT ALLOCATED:** absence of obvious references or zero sample
saves does not prove that these bytes are available. Before production use,
audit the encompassing stat object, variable-index readers/writers, resets,
season rollover, and all loaded/save states. Trace writes through native week,
offseason, stats and save/load tests with a canary. Check current owner union
for competing save metadata. Do not take player ability bits, VIP data, unused
FA slots, history capacity or arbitrary zero roster padding as fallback space.

Candidate compact schema, only after that ownership gate, relative to 0x9967C:

| Bytes | Meaning |
| --- | --- |
| 0..7 | New magic `MCPL0001` (distinct from old `MCQB0001`) |
| 8..11 | u16 version 1, u16 length 128 |
| 12..15 | Checksum of 16..127, corruption check only; native container signature still required |
| 16..31 | Creation token, nonzero, generated in-game |
| 32..35 | Primary pool ordinal, bounded by the actual pool count |
| 36..39 | Phase, controller port, camera preference, position (one byte each) |
| 40..43 | Current club ID or -1; membership is re-resolved, never trusted as a pointer |
| 44..55 | Root-relative college/first/last references, each bounded to the serialized roster arena |
| 56..63 | Record +4 identity word and masked birth identity from record +0x18 |
| 64..71 | Upgrade balance and monotonic committed-fixture watermark |
| 72..75 | Request kind, flags, target club or 0xFF, reserved zero |
| 76..79 | Request's due native week key |
| 80..83 | Starter preference, starter-applied flags and reserved zeros |
| 84..87 | Cumulative participation points earned, bounded |
| 88..127 | Reserved zero; reject unknown versions/nonzero reserved bytes |

All fields are little endian, pointer free. History remains in native streams;
the 64-entry diagnostic XP ring need not occupy save bytes if the monotonic
watermark is kept. A fresh load reconstructs runtime state in owned RW, checks
ordinal, immutable identity, roster membership, bounds, schema and checksum,
then enables control only after native signature/deserialization completion.
Foreign/missing/corrupt identity must detach input and show a usable recovery
screen, never control a lookalike or fall back to controlling the team.

If ownership of the tail cannot be established, M2 persistence is blocked;
there is no certified alternate byte allocation in this design. Prove a native
arena allocation with lifecycle and serialization or renegotiate the fixed
container contract in a later brief. Do not silently ship the old journal.

If certified, serialize through the tail-copy boundary before container
signing, preserving ordinary noncareer tail semantics. Keep runtime state in
the existing RW allocation; do not make the tail's retail RAM address a new
runtime cave. Retain legacy setup reading only as an explicit compatibility
path, never as the default creation workflow. New saves must reload on two
independently built patched XBEs with no seed and different allocation VAs.

## Hub lifecycle and auto-save contract

The new descriptor must have its own state and lifecycle, with no event that
destructs the hub on a child push. Retain the native stack and native child
destructors. Associate the actual manager/depth for the lifetime of this entry;
never follow a stale manager pointer from an earlier game. Reject full stacks
and repeated entry without duplicating resources. A root at depth 0 and a hub
above Main Menu must both work.

For Practice, extend the existing return-target helper's explicitly validated
parent recognition to the sealed MyCareer descriptor. Keep its cloned settings
and Team Select checks. A naked flag or accepting any grown address is unsafe.
Current MyCareer `screen_dispatch` refuses ALL grown descriptors and several
retail GM screens; replace that blanket grown-address refusal with exact
career-owned destinations and permitted read/edit children. This change must
compose with playlist, PS screen, Practice and both hook installation orders.

For scheduled games, prove the launch keeps the hub. Pause Quit preserves the
game parent; the ended-game lifecycle destroys the game and resumes the hub.
Whether an abandoned game counts as played follows native commit status;
do not award points or mark a schedule result simply because Quit was chosen.

Auto-save is owned by the parallel `astra/r63-franchise-autosave` session,
whose implementation is absent from this checkout. **HYPOTHESIS:** connect to
its eventual public routine; no numeric address or success return is invented.
Proposed adapter ABI is `request_after_game(manager, fixture_key)` returning
queued/saved/cancelled/failed, and a completion signal. This is a requested
interface, not an existing API. The shared owner must initialize the native
save context and use native signing, overwrite and error handling.

Order: native game result/stats commit -> settle XP once -> complete a due
weekly request if the native week advanced -> resume usable hub -> request
shared save once for that committed fixture -> reflect success or failure.
Do not save from a per-frame binder, before a finished result, or while the
game's resource teardown is running. Pending state and a last-saved fixture
watermark stop repeated hub-resume saves. Failure retains dirty state and an
explicit Retry save action; manual Save uses the same service. Practice and
cancelled matches do not trigger an after-game save. Cold reload must prove
result, ratings, points and pending requests agree in the same signed file.

## Allocation and resource budget

**PROVED current union:** `python3 tools/nfl2k5_xbe_space.py plan --requests
tests/fixtures/nfl2k5_allocator_beta62_requests.json`: 41 requests,
12,300,288-byte XBE; new-owner availability 54,800 RX, 4,096 RW, 8,616 RO.
Existing MyCareer requests remain `8192 RX / 4096 RW / 0 RO`, 16-byte aligned.
No new request, gate owner or page count is introduced in M1.

Proposed M2/M3 component ceilings, **HYPOTHESIS estimates, not measured code**:

| Component | RX ceiling | RW ceiling |
| --- | ---: | ---: |
| Reused binder, identity, camera, CPU guards, settlement | 3,328 | 1,280 |
| Creation, placement, franchise and return routes | 1,408 | 384 |
| Hub descriptor, rows, hooks and strings | 1,568 | 768 |
| Compact save encode/validate/load | 640 | 256 |
| Requests, rating purchases, play-call gating | 1,024 | 512 |
| Validated controller pointer list and scratch/alignment | 224 | 896 |
| Total | **8,192** | **4,096** |

These estimates require removing the old seed and external-journal machinery,
not placing a second owner beside it. All static tables are immutable owned RX
content; no writable code page. General RO cost is zero. If assembly exceeds
this, report actual size and request a revised union, never use an unreserved
address or silently consume the scarce spare RW page. The current exact union
remains the gate fixture until an implementation changes REQUESTS.

Art is an archive/texture allocation, not RX/RW memory. The proposed background
below consumes about 350,528 native index/palette bytes with seven mips, before
wrapper/system/scene data; measure actual resource and peak menu heap use.
Clone resources or author a new family with existing scene/texture writers;
do not replace shared Crib materials in place to change only the hub.

## ASSET REQUEST LIST for the Fable art agent

No art agent is invoked here. These are exact authoring requests and native
constraints for the integration handoff, with placement still **HYPOTHESIS**.
No existing Crib still was found or rendered in this headless session. Use an
authored apartment composition based on the existing Crib room's wall,
window, framed-shirt and television materials. Do not claim a 3D room texture
is already a usable fullscreen still.

**PROVED source selectors:** outer 4248, `crib_scene_texture:room:2`
(wall/ceiling, 256x256 P8, six mips), `room:22` (bar monitor, 128x128,
five), `room:31/32` (ESPN/Crib screens, 128x128, five), `room:37/38`
(paintings, 512x256, six), `crib_scene_texture:skybox_day:0` and
`skybox_night:0` (512x256, six). Original assets stay private to the user's
retail extraction; ship authored pixels and source-derived writer recipes.

| Deliverable | Exact authoring / native specification | Use |
| --- | --- | --- |
| `mycareer_apartment.png` | 512x512 non-interlaced RGBA PNG; compose for a centered 512x384 4:3 crop, with the core art safe inside a centered 512x288 wide crop. No baked UI text. Native P8, 256 BGRA palette entries maximum, mips 512,256,128,64,32,16,8, individually swizzled by existing writer. 349,504 index bytes + 1,024 palette bytes. | Hub-only background, warm wall/window/sofa, football gear, dark left menu area. Distinct from Coach's Desk. |
| `mycareer_panels.png` | 256x128 RGBA PNG, native P8, <=256 palette entries, mips 256x128 through 16x8 (five); 43,648 indices + 1,024 palette. | Opaque/translucent backing atlas for player summary, opponent and upgrade balance; padding between regions, no names baked in. |
| `mycareer_calendar.png` | 128x128 RGBA PNG, native P8, <=256 colors, five mips 128..8; 21,824 indices + 1,024 palette. | Atlas of played, upcoming, bye, practice and request icons. No color-only meaning; each icon has a distinct shape. |
| `mycareer_focus.png` | 128x32 RGBA PNG, native P8, <=256 colors, one mip unless the chosen native template requires more. 4,096 indices + 1,024 palette. | Focus row highlight with a clear edge and center fill. |
| Layout specification | Virtual 640x480; content inside x=36..604, y=28..452. Nine rows of 26px height, menu x=44..302, top 142; summary x=332..596. Controller footer y=432. Runtime strings, retail font, no new font atlas. | Shared 4:3/wide safe layout; wide layout adds side art without stretching characters. |

Use the source template's actual format, mip count, wrapper and fixed stored
span when compiling. The single-mip focus request is provisional until a
specific texture slot is assigned. If compressed content will not fit, use the
existing transactional archive growth owner and receipt; never truncate art
or guess offsets. All TXTR/SCNE IDs, descriptors and loaded layout token must
be assigned and validated together. Budget a single background and no animated
Crib scene for v1. A plain temporary native `options` layout is acceptable for
M2 only; it does not satisfy M3 hub-art completion.

## Acceptance and milestone exits

M1 exit: this complete map, explicit unresolved proofs, asset request, native
prerequisite tests, writer/native baseline, both XBE gates, replay and budget
receipts, report and protected wiring handoff. M1 is a design milestone;
HYPOTHESIS items are implementation work, not completed product features.

M2 exit requires ALL of: seedless entry -> native creation -> placement ->
genuine franchise -> minimal hub -> player-locked game -> usable hub; certified
inline identity/state; cold reload with two careers on the same disc and with
different allocator layouts; native Back/cancel/error route tests; both gates
in both orders, unchanged replay, foreign/mixed refusals and exact receipts.
The recipe for Claude must be a generic disc recipe with no setup file or
player name parameter. Do not write M2_DONE for a host codec, direct-entry
probe, mocked frontend state machine or code that still needs an external save.

M3 exit requires schedule/card/depth, real rating purchases and weekly awards,
next-week requests, hub art, shared after-game auto-save and the complete
stability matrix. Noah's witness list is in ASTRA_MYCAREER_MODE_REPORT.md.
Protected release integration remains in WIRING.md. All presets stay off until
the intended executable routes exist; nothing here is called witnessed.

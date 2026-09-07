# MyCareer mode-2 implementation and acceptance report

2026-09-07, `astra/r64-mycareer-mode-2`, base
`2f2a29c7a0f9ecd2527a1a1dfe784426cecb1021`.
**EXPERIMENTAL / UNWITNESSED. M2 and M3 are incomplete.**
This report replaces the historical M1/audit report, which remains in the base
commit. The binding continuation brief supersedes M1's fixed-length save
proposal: the occupied season tail is never used by this implementation.

The seedless creation, franchise initialization, apartment, inline persistence,
native load return, Practice lifecycle, abandoned-game return and generic disc
writer are implemented and tested. A continuous completed player-locked match,
off-field snap/clock progression and the M3 features are not certified. No
M2_DONE or M3_DONE marker is written. There was no game boot, Xbox emulator boot,
GUI display, audio, network access, played witness or push.

## What was built

`mod_editor/core/nfl2k5_my_career_mode.py` is the generic format of the existing
`nfl2k5_my_career` owner. It reuses exactly 8192 RX / 4096 RW bytes. It refuses
legacy/generic mixtures before mutation; old explicitly prepared-save builds
retain their compatibility implementation. Generic status validates every
hook, native context, allocation, complete generated template, format seal
and initially zero RW. The legacy status API delegates full validation when
it recognizes the new format.

The installed Game Modes action opens an owned entry list:

1. Enter the draft: native `Coming in the next update` notice.
2. Undrafted free agent: native new-player creation, followed by all 32 NFL clubs.
3. Load career: native Load/Save UI.
4. Quit to main menu: the explicit exit.

The new-player bridge enters the actual NEW branch at `0x34621C`, preserving
native date/name/appearance/equipment and completion logic. It snapshots the
unused 84-byte PRIMARY slot, two 34-byte name cells and unused FA tail cell.
Back/cancel restores the entire bounded source roster and clears transient CAP
callbacks. Full pools, full FA storage, aliased names, contradictory ownership
and full destinations refuse visibly. Native confirmation occurs before any
franchise or signing mutation. The five positions absent from the native CAP
rating-template table receive balanced numerical ratings under exact career
creation ownership; style bytes are preserved. Tests cover those record
values and cancellation, not rendered position-selector choices.

Placement executes complete native defaults and franchise initialization
`0x148C60 -> 0x10EA10 -> 0x13EE10`, native FA removal, contract, jersey,
team append/sort/salary operations, club association `0x13EC90`, then complete
finalization `0x13F1B0`. These initializers are not stubs in the creation test.
Weekly Preparation defaults off. CPU front-office management stays enabled.
The identity is captured from the new record, never selected by player name.
The native RNG supplies the creation token; deterministic entropy is a named
fixture seam, so the fixtures do not demonstrate hardware entropy quality.

The distinct Apartment uses owned native-list descriptors, not a renamed
Coach's Desk. Its five rows are Play next game, Practice, MyPlayer, Save and
Quit to main menu. Back on the root stays in the mode. Native schedule, player
card, Practice settings and Save children return correctly through Back.
Cold native Load executes the real completion operation, CLEAR and REPLACE
at `0x16DD30`, restores the club association and opens Apartment at depth zero.
An authenticated but invalid requested career clears identity and displays
`Career save could not be loaded.` without disabling the entry list.

Practice uses a private clone of native settings and native Team Select.
Native START, game descriptor, Pause, Quit confirmation, ended-game dispatch
and return to Apartment are executed with explicit engine/rendering service
seams. The game is not claimed played. For franchise launch, Schedule START
and Play reach native Team Select and Game. The postgame parent `0x4F19E8`
must remain on the stack: it calls `0xC74E0`, including `0xC5DF0` week processing
for completed games. A guarded callback replacement at `0x4F1994` runs that
native callback first, then returns from Schedule to Apartment. Abandoned-game
and scene-load-failure tests exercise this native chain and a usable child
after return. No XP is awarded and abandonment retains native fixture status.
The completed-game branch is not yet proved through a full match.

## Inline persistence

`nfl2k5_my_career_save.py` defines the versioned 128-byte `MCPL0001` footer
AFTER all four complete native streams, including front office:

| Native container | Career container | Footer offset |
| --- | --- | --- |
| 720044 bytes, ROST version 0 | 720172 bytes | 720044 (`0xAFCAC`) |
| 724140 bytes, ROST version 1 | 724268 bytes | 724140 (`0xB0CAC`) |

ROST versions remain owned by the arena-growth implementation. Career schema
version 1 is independent. The real Franchise1 season-tail occupancy recorded
by M1 remains a counterexample to using `0x9967C..0x996FB`; none of those bytes
is appropriated. Ordinary saves retain their native length.

The footer contains a creation token, PRIMARY ordinal, phase/port/camera/
position, club ordinal, root-relative college and name references, immutable
record/birth identity, upgrade balance, committed-fixture watermark, pending
request scalars, starter preference and cumulative points. Reserved bytes are
zero. No allocator address, live body pointer, executable recipe or external
journal is persisted. The FNV checksum detects corruption; native signing
provides authentication.

Seven pinned adapters cover native total-size calculation (`0x16AA26`),
metadata admission (`0x16ABB5`), serialization before signing (`0x16E50D`),
load-begin identity clearing (`0x16E5CE`), successful signed read before ANY
deserializer (`0x16E6D3`), source ROST extent (`0x16E7E5`) and completion after
all deserializers (`0x16E815`). Loading a smaller native roster into a larger
arena uses the SOURCE extent when locating later streams. Bad lengths,
wrappers, versions, reserved fields, identity references and ordinals refuse
before native decode. Failed reads do not leave an old player attached.

PROVED in bounded instruction execution: all four native serializers and all
four deserializers; both container sizes; independent careers on different
allocator layouts; native HMAC construction and EXTRA writer covering the
entire extended buffer, matching the existing host verifier; cancelled/failed
writes and malformed reads. Signing fixtures replace kernel SHA-1/OS services
and use the title certificate key derivation. No physical console save is
claimed. Reader/save-writer helpers recognize the footer without mistaking it
for extra roster growth or shifting the season year by 128 bytes.

## Control and off-field evidence

The retained binder revalidates primary identity and maps it through the native
match copy. It bounds the body list and controller array, rejects duplicate or
cyclic lists, detaches absent bodies, and leaves CPU teammates unassigned to
the human port. The inline variant corrects the away human field to `0xE5FC90`;
the historical assembler output remains byte-identical.

Consumer-specific play-call hooks leave both raw team `+0x30` human fields
clear. On-field QB/WR/HB/FB/TE may call offense; CB/FS/SS/OLB/ILB/DT/DE may call
defense. Linemen, special teams and absent bodies use CPU eligibility. Native
`0x1891B0` and native controller assignment run for all 17 positions on both
teams and across possession changes. This is a control-decision proof, not a
snap, drive or physical control witness. The CPU body callback `0x152B80` is
unchanged so teammates' CPU behavior is retained.

`mode_unit_present()` exports a bounded presence query for a future Supersim
stop condition. It returns a validated body or zero; the adapter must discover
its relocated label from the sealed owner. No guessed Supersim address is
installed. Normal-speed CPU play is the fallback, pending snap/clock proof.
The `0xC5D9E` wrapper settles the ledger after native stat commit and before
week advancement; autosave's separate `0xC5DA9` boundary is left to its owner.
The compact schema transports pending requests and earned points, but there
is no new M3 request or purchase UI.

## Exact builds, allocations and resource bounds

The committed `docs/mod_editor/nfl2k5_my_career_mode_receipt.json` contains
source hashes, both complete disc hashes, XBE hashes, exact patch edits,
allocator receipts, unchanged replay, cold-load results and deletion receipts.
It records M2/M3 complete as false. No game executable, save or disc is included.

| Layout used by independent disc build | MyCareer RX VA | MyCareer RW VA |
| --- | --- | --- |
| MyCareer requests only | `0x14DA000` | `0x14F2000` |
| Committed full budget union | `0x14DD670` | `0x14F3350` |

Both use the existing 8192/4096 budget, with no fictitious relocation owner.
The cold-load suites use these same two layouts. Full safety gates separately
INSTALL and replay the complete owner stack in both orders. The generic disc
recipe reserves the union but installs only allocator infrastructure and this
MyCareer format; other selected features still use their normal adapters.

Current measured content: **7870 RX bytes**, including **6996 machine-code
bytes**, strings and the compressed immutable menu template. A **17-byte seal**
is at the end of the allocation, leaving **305 bytes** before it. The expanded
menus occupy **996 RW bytes** at `state+256`; persistent binder fields, CAP
rollback, footer staging and the bounded visited-controller list all fit the
4096-byte state allocation. No mutable `.data`/`.bss` or runtime code-page
storage is linked. GCC `-Os` and GNU binutils regenerate the checked template.
A separate `-Oz` size experiment saved only 71 C-section bytes; it was not
adopted. The remaining space does not accommodate the unimplemented M3 design.
No owner budget or page was expanded to conceal that shortfall.

Two full 6300499968-byte source disc copies were built sequentially inside
TemporaryDirectory, each grown to 6312800256 bytes. Both were read back,
stream-hashed, used for cold native load of the QB/club-2 and CB/club-31 careers,
and deleted before writing the receipt. Lowest measured root free space while
an image existed: **102589693952 bytes**, above the 100 GB floor. Acceptance
process peak RSS: **253176 KiB**. Files are streamed in 4 MiB chunks; executable
reads are capped at 16 MiB. Scratch contains only bounded save hex, research
scripts, JSON and logs, below 200 MB. The synthetic XDVDFS test also proves a
neighbouring file survives executable relocation.

Generic recipe, run from this repository with new output paths:

```sh
python3 -m mod_editor.core.nfl2k5_my_career_mode apply \
  '/path/to/retail/default.xbe' '/path/to/output/default.xbe' \
  --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json \
  --receipt '/path/to/output/mycareer-xbe.json'

python3 -m tools.mycareer_mode.build_disc \
  '/path/to/retail.xiso.iso' '/path/to/output/MyCareer.xiso.iso' \
  --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json \
  --receipt '/path/to/output/mycareer-disc.json'
```

No setup file, player name or prepared Franchise is accepted by either recipe.
They refuse existing outputs, stream temporary staging and verify the result
before replacing the new output path. All stage handles close before replace.
The image/XBE and JSON receipt are separate publications; a receipt-write
failure can leave the successfully published output and is not an atomic
multi-file transaction. The production patch and generic recipe remain labelled
experimental. Protected Build and GUI integration is specified in WIRING.md.

## Validation

Every suite ran standalone with plain Python. Native evidence tests declare
precise skips when the pinned USA XBE, retail roster, Unicorn or Capstone is
absent. No skip was used to hide a failure in the new suites. Durations below
are the latest completed run for each named suite in this session.

| Command (`python3` prefix) | Result |
| --- | --- |
| `tests/mod_editor/test_nfl2k5_my_career_inline.py` | 8 passed, 11.193 s |
| `tests/mod_editor/test_nfl2k5_my_career_frontend.py` | 7 passed, 53.422 s |
| `tests/mod_editor/test_nfl2k5_my_career_control.py` | 2 passed, 15.092 s |
| `tests/mod_editor/test_nfl2k5_my_career_generic_build.py` | 5 passed, 7.496 s |
| `tests/mod_editor/test_nfl2k5_my_career.py` | 13 passed, 19.725 s |
| `tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | 18 passed, 12.208 s |
| `tests/mod_editor/test_nfl2k5_my_career_manifest.py` | 3 passed, 5.924 s |
| `tests/mod_editor/test_nfl2k5_my_career_mode_routes.py` | 7 passed, 3.037 s |
| `tests/mod_editor/test_nfl2k5_my_career_mode_audit.py` | 6 passed, 0.075 s |
| `tests/mod_editor/test_nfl2k5_my_career_creation_boundary.py` | 4 passed, 2.291 s |
| `tests/mod_editor/test_nfl2k5_franchise_save.py` | 13 passed, 1.582 s |
| `tests/mod_editor/test_nfl2k5_roster_records.py` | 108 tests, 1 skipped, 12.423 s |
| `tests/mod_editor/test_nfl2k5_save_writer.py` | 17 tests, 1 skipped, 0.039 s |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed, 363.931 s |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 95 passed, 454.913 s |
| `tools/mycareer_mode/build_runtime.py --check` | PASS |
| `tools/nfl2k5_my_career_assemble.py --check` | PASS; legacy template unchanged |
| `git diff --check` | PASS |

The two baseline skips are the absent shipped portrait catalogue and the old
save-writer smoke test's `/tmp/opencode/espn26/default.xbe` fixture. The new
native signing suite uses the actual pinned retail extraction and passes.

The capability fragment passes schema validation in the merged registry and
explicit checks of its own evidence/module/command paths. Baseline full-file
registry checking reports an unrelated missing `docs/research/apf_audio.md`;
no baseline file or validation exemption was committed. Initially the safety
gates refused Overtime/PAT companion edits inside audited play-call contexts.
The fix requires those owners' complete sealed status and normalizes only
those exact sites before checking the original native context hash.

## Remaining acceptance work and counterevidence

- **M2 completed played-game chain:** the engine-step/asset seams in the stack
  fixture do not execute football. A completion-boundary probe reaches a null
  player-stat callback because the fixture has not initialized the live engine's
  match-stat objects. It is recorded as a failed probe, not a completed match.
  A complete native finish, real stats, once-only award, final-season transition
  and return to a usable apartment remain required.
- **Off-field fallback:** real PLAY data plus native constructors select the
  expected CPU/human branch in a research probe. Full CPU choice reaches an
  uninitialized role/script pointer at `0x1A8E60`; the resource-validation seam
  does not establish a legal complete play-script set. No mid-function stub was
  added to turn this into a passing game. Snap, clock, turnover, timeout,
  halftime, overtime, injury and substitution progression are still unproved.
- **Schedule scope:** Play next game currently opens native Schedule. Explicit
  earliest-unplayed selection, bye/advance presentation and filtering unrelated
  game-card actions remain unfinished. Native START can simulate other fixtures
  before the career fixture. A 500-million-instruction research budget expired
  in native history insertion while completing those CPU fixtures; that bounded
  stop is not evidence of a production hang or a completed week.
- **M3:** calendar view, season/career stat tabs, depth chart, numerical purchase
  UI, weekly trade/release transaction, hub art and shared auto-save are not
  implemented. Scalar storage and the five-row hub do not satisfy M3. Fit the
  remaining design inside the existing budget before adding these features;
  this report makes no claim that 305 bytes is sufficient.
- **Rendered/physical behavior:** hardware/device/rendering boundaries remain
  explicit. Neither menu rendering nor a physical save/load or player position
  has been witnessed by Noah. All presets and public GUI exposure stay off.

Read-only dependency checks: `astra/r64-mycareer-supersim-draft` still exposes
`RUNTIME_READY=False`, `REQUESTS=()`. Its report proves native simulation/draft
steps but records loss of live state on resume; it is not an installable
Supersim adapter. Draft retains the requested next-update notice. The shared
`astra/r63-franchise-autosave` owner exists but its cached-slot/FPF-aware native
save callback recognizes Coach's Desk, not this apartment; the proposed
`request_after_game` ABI is not an actual callable contract. Fable's apartment,
panel, calendar and focus PNGs/recipes exist on `fable/r64-mycareer-art`, but no
hub-only native texture/scene family is assigned here. Those worktrees were
read only and no dependency files were copied or edited. WIRING.md details
all three integration boundaries and every protected dispatcher/Build/GUI/
allowlist/runtime-closure/capability change.

## Noah's witness list after the outstanding code gates

Create at least two careers on one generic disc, including different names,
positions and clubs. Check every CAP page, template, Back/cancel and full-team
refusal. Load both careers on another allocator layout and verify identity,
club, ratings, points and settings. Use native Save, overwrite, cancel, device
failure, retry and cold reload. Invalid career files must show an error and
never attach to another player.

For each position family, verify MyPlayer alone receives physical input through
substitutions, possession changes, kicking, penalties and camera changes. Test
benched/injured games and CPU snaps on the other unit. Complete regulation,
overtime, a bye and the season's last game; verify real stats and once-only
awards, then enter every apartment child after game return. Abandoned games
and Practice must award nothing. Test load failure and repeated launch/return
from both a root apartment and one above Main Menu. Quit cancellation must
stay in the mode; only explicit confirmed Quit leaves it. M3 needs its separate
purchase/request/calendar/art/auto-save witness matrix once implemented.

# Separate offensive and defensive playbooks

EXPERIMENTAL / UNWITNESSED. USA Xbox. Worktree `astra/r65-playbook-pair`, base
`be99b324f34d536c625efcba7e7ea5d4f104fd2b`. No game was played or displayed.

## What was built

`mod_editor/core/nfl2k5_playbook_pair.py` is an opt-in executable owner. Its
freestanding C kernel and x86 adapters add **HOME Defensive playbook** and
**AWAY Defensive playbook** immediately after the corresponding original book
rows in the two native pregame Options lists. The original captions become
**HOME Offensive playbook** and **AWAY Offensive playbook**. Options was chosen
because it already has native cycling/text callbacks and a terminator-delimited
row list; no unproved extra space in the Team Select artwork is assumed.

Each side defaults to **Same as offense**. The 34 alternatives are the 32 club
books, Generic and West Coast. Both human and CPU sides have the same controls.
A successful pair takes ordinary offense and all special teams from the first
book, and the entire ordinary defense, including fronts and coverages, from
the second. It creates one self-contained live PLAY body before the native
play-call initialization caches any pointers. It does not switch a side's root
at possession changes.

The pair is game-only. The first nondefault selection displays:

> Defensive playbooks last one game. This choice is not saved to Franchise.
> Paired sides do not use VIP learning or replay.

A changed team invalidates that side's choice. Game teardown clears both choices.
No second saved book index was proved or allocated, and no Franchise, profile,
or custom-book save byte is changed. This is the brief's explicit persistence
refusal, not a claim of Franchise team persistence. Play Now and Franchise
schedule games share the installed setup/load path. Mode values 4 through 7
are admitted; practice 0 through 3 and drill mode 8 are excluded. Native row
visibility writes the runtime row's hidden flag at +8 through EDX; it is not a
boolean-return callback. Rows are hidden once a paired game has started.

Both sides must use stock source choices. Native User A/User B sources are
refused before extra loads, with a plain notice. A missing resource, queue
failure, allocation failure, malformed graph or capacity overflow retains that
side's original complete book and displays a HOME/AWAY-specific notice. It
never publishes a partially merged body or silently drops plays. The other
side can still have a valid pair.

The owner, standalone patch/instruction tests, full gate union, manifest builder
lists, budget fixture and capability handoff are implemented. Protected product
wiring is specified in WIRING.md; the Studio toggle is not wired in this branch.
All presets should remain off. The explicit CLI can already install the owner
into a new XBE copy.

## PROVED: retail selection, ownership and enumeration

Evidence is the pinned retail executable SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`, its individual
PLAY/ROST archive resources, and the read-only Ghidra corpus. Function names
below are addresses, not recovered developer symbols. Tests do not need the
Ghidra installation.

| Path | Retail evidence and implication |
| --- | --- |
| Setup selection | HOME getter/setter `775F0/77600`, metadata pointer `E5FE78`; AWAY `77720/77730`, `E5FE7C`. A metadata entry is a display name and short resource code. Team setters `77AE0/77B20` seed the choice from team+110. |
| Native Options | Original lists `526A70` and `526D88`, each seven 52-byte rows plus a terminator. Descriptor pointers `526C20/526F38` are redirected to one owned immutable template. `2C1A95` and `27B49A` open these descriptors. Runtime rows are separate writable instances; `F2F90` hides an instance by matching its caption. Renaming the original book captions also avoids the old one-side book-hiding rules in Franchise/network setup. Network play is outside this feature's supported witness scope. |
| Modes | `77C6B` initializes exhibition to 4. `C73F2..C743E` chooses Season 5 and Franchise schedule 6/7 from league/phase. The early assumption that mode zero meant a normal game was rejected against these bytes; mode zero is practice. |
| Resource lookup | `628D0(1)` builds HOME filename at `B307D0`; `(0)` builds AWAY at `B30810`, using `%s-pb.iff`. Calls at `63095/630C3` queue the named `PLYBOOKHOME/PLYBOOKAWAY` resources through `43F50`. `61580` extracts PLAY/`plb` and calls the supplied root setter. |
| Loaded roots | HOME getter/setter `777D0/777E0`, root `E5FE80`; AWAY `777F0/77800`, `E5FE84`. The resource names and literal HOME/AWAY captions establish the side mapping; some earlier practice notes use different A/B terminology. |
| Team binding | `87160` writes HOME root to `E5FC20+20`, AWAY to `E5FC60+20`. Possession uses the current offense/defense team pointers `E60280/E60284`. There is one root per side, not a second defensive book field. |
| Tables | `E0660` reads root+44 plus formation index times 180; `E06E0` reads root+60 plus play index times 96. `E0830` bounds formation indices and reads root+48 plus index times 80. The native accessors execute successfully over every retained link in the merged KC/BAL book. |
| Unit classification | Formation type is `(flags >> 8) & 63`: ordinary offense 0..3, defense 4..7, special teams 8..13. Play family is `(flags >> 6) & 7`, with ordinary defense 1. The source parser, actual resource census and `204B40/204C80` agree. |
| Cached references | `64710` starts setup before `63330`, `11A540`, `188870` and `2075E0`. `11A540` binds teams; `188870` validates play records. `204C80` caches special-team play/formation/category pointers and `204B40` fills audible selectors. A late root swap leaves cached pointers from the old book. |
| Cleanup | `61950` unloads named resources through `432F0`; it handles pending cancellation as well as normal teardown. The owner restores original root pointers, frees its composites, cancels/unloads its two named defensive resources and clears state before retail teardown. |

The two additional queue identities are `PAIRDEFHOME` and `PAIRDEFAWAY`; their
request objects are distinct owned RW spans. Callback routing selects the side
explicitly, so reversed completion order cannot swap the books.

## PROVED: why a second root cannot simply be spliced in

A PLAY body is 0x13390 bytes (78,736; archive wrapper adds 32). Root+34/+38/+3C/+40
hold formation/play/category/node counts. The native fixed layout is:

| Data | Offset, extent and merge rule |
| --- | --- |
| Formations | +134, 50 records of 180 (0xB4) bytes. Copy each retained record, preserve player-slot, coordinate and mirror bytes; remap its name pointer. Same names never collapse different formations. |
| Formation auxiliaries | +245C, 50 records of 80 (0x50) bytes. Preserve the 36 link positions and high flag bits, replacing only each low-nine-bit play index; 1FF stays empty. |
| Category references | Aux+48 low six bits are the default category; +4C is the membership mask. Remap both. Categories merge only when the complete 12-byte role/code payload and UTF-16 name agree. |
| Plays | +33FC, 270 records of 96 (0x60) bytes. Preserve flags and all eleven descriptors. Copy declared chains using descriptor low nibble for length; maximum 15 nodes. Only exact byte-identical node spans are shared. |
| Categories | +993C, 26 records of 16 (0x10) bytes. Preserve all role/code bytes; remap names. |
| Nodes | +9ADC, 3500 records times eight. Preserve every opcode, operand and condition flag byte; rewrite assignment pointers to the output pool. |
| Names | +10840 through +1337F; +1083C stores character count. Bounded UTF-16 names of at most 40 characters, including a checked terminator and remaining-pool checks. |
| Default audibles | Root+4C..55 offense and +56..5F defense: five pairs of formation index and linked-play-slot byte. Remap formation indices; retain link slots and reject cross-unit or empty targets. |
| Substitutions | Root+6C has fifty words. `E0850` matches type bits 18..19 and index bits 20..29. Remap category type 1 and formation type 2; reject unknown nonzero types rather than guessing. Retail main ROST has zero source override rows at root+60. Synthetic live overrides are tested. |

This avoids *internal* formation, category, link and audible collisions. It
retains both front and coverage records. Player-local mirror and shift values
are preserved rather than reinterpreted as book-global indices. It does not
prove the visible hot-route, shift, substitution or audible behavior in a game;
those remain explicit witness items. No claim is made that every downstream
actor or animation path has been executed.

Two further collisions required active handling:

1. The normal PLAY loader `166610` calls `E99C0`, which cycles between the two
   fixed custom-book buffers `B75A40` and `B88DD0`. Four book loads would reuse
   those buffers. During a paired load only, the wrapper returns the native
   heap-selection value zero for *all* PLAY loads, independent of ordering.
   The existing allocator/destructor path then owns the source bodies. It is
   not enough to change the mode only around enqueueing, because loads complete
   later. The native `1665B0` destructor explicitly exempts only the two fixed
   buffers and frees heap-backed bodies.
2. VIP records contain formation and play numbers. `17DFC0`, for example,
   feeds recorded indices through the root accessors. Reordering a book can
   replay the wrong play and can pollute later profile learning. The `F71E0`
   wrapper supplies its native no-profile result for each successfully paired
   side only. Ordinary CPU selection remains available; its play distribution
   and all user expectations still need witnessing. Default and failed pairs
   keep the native VIP path.

The merge also relocates source records outside the two fixed buffers recognized
by the existing authored read-option/QB-spy identity lookups. Their custom
controls are **not supported on a paired side** in this implementation. Those
owners still compose byte-for-byte in the gates, and they are not modified here.
Protected Build wiring must refuse pairing together with authored intent
features until those owners gain an explicit paired-root contract. Ordinary
retail plays continue to carry their original assignment bytes.

## PROVED: bounds, requests and receipts

The 37 resources are the 32 clubs plus Editor, GEN, PRACTICE, reference and WCO.
The new selector offers 34 stock game books; it does not pretend that all 37
archive resources are selectable team books. Among the 1,156 ordered pairs of
these 34 choices, 290 exceed the formation or play caps; 866 pass only those
count checks. That count is not an approval of the remaining node, name,
category, audible and substitution constraints.

The requested example is buildable: KC has 159 ordinary offense plays and 17
special-team plays; BAL supplies 93 defense plays. The emitted code produces
269 plays, 42 formations and 23 categories. Every chosen play's flags,
descriptors and declared assignment bytes compare to its donor. CIN offense
with OAK defense requires 291 plays and is refused. No capacity is expanded.

Requests are **8192 RX / 512 RW / 4096 RO**, aligned to 16, all in named v3
allocator children. No retail cave or .text storage is used. The live workspace
is 140 bytes; extra RW is reserved and starts zero. The complete budget fixture
has 44,432 RX bytes, 4,096 RW bytes and 4,008 RO bytes available to subsequent
owners. The 512 RW bytes fit existing alignment slack before the Senior Bowl
allocation. The synthetic stress owner's RX request falls from 48 to 40 KiB so
it still fits beside every real owner; its multi-page tests remain intact.
The XBE remains 12,300,288 bytes.

Each successful composite uses 78,736 native heap bytes. With both sides paired,
up to four source bodies plus two composites require 472,416 bytes, excluding
resource-manager bookkeeping and allocator overhead. Actual Xbox heap pressure
is unwitnessed. Allocation failure has a tested fallback. The private merge
uses bounded stack maps; it never puts large mutable bodies in owned RX or RO.

`status` distinguishes retail/applied/foreign; `apply` recognizes all hooks,
immutable tables, zero initial RW and prerequisite pins before allocating or
editing. Mixed and foreign installs refuse. Code, tables and site receipts carry
exact addresses/sizes; all section digests are repinned. Reapplying a complete
owner returns identical bytes and an empty changed-byte receipt. The CLI writes
a new file exclusively and refuses replacing an existing source/output.

## The in-game custom-book verdict

**PROVED: 2K5 already has a bounded native custom playbook manager.** It is not
accurate to say that 2K5 has no writable custom book or no in-game existing-play
selection infrastructure. The Front Office entry at `503CA0` references manager
screen `519920`; another entry is at `555134`. Native text includes Manage
Playbooks, Add Plays, Manage Audibles, Manage Substitutions, Save Playbook and
Load Playbook. The two User A/User B buffers above are each a full writable PLAY.

`163180` clones a book; `162530` imports formations with a 50-record limit and
`162630` imports plays/nodes with 270/3500 limits. `1628F0` imports selected
formation/play links, and `162E18` processes selected UI rows. Native managers
`26B200` and `26B9D0` bind audible and substitution editing to a custom root.
`628D0` selects an active User A/B buffer directly for gameplay.

The bounded native save path is also present. `161A60` reports 0x13390 bytes;
`161A70` temporarily makes pointer fields relative, copies the full body, then
restores its live source pointers. The save call at `16D832` uses that serializer
and `16D845` calls the normal transaction with Playbook type 6. `161E30` copies
and relocates a selected User buffer; `16A480` is its load adapter. The standalone
instruction test executes the retail serializer and loader: KC serializes back
to the exact original body, leaves User A unchanged, and restores the equivalent
live book into User B. This is an in-memory proof, not a signed-device save or a
controller witness.

The Studio's Create a Play, `.2k5book` packs, Rules library and Info tab already
serve offline authoring. They do not by themselves establish an APF-style
profile save contract. The existing native manager is the bounded in-game
alternative to witness first; this branch does not duplicate it or advertise a
new persistent editor that was not built. The executable pair owner builds a
bounded composite book for a game, but does not save that composite.

A new 38th disc book is not a safe shortcut for this beta. It needs a new native
roster metadata entry/count, a matching named archive resource/directory entry,
selection and load lifetime handling, and a proved save reference. Fixed-span
PLAY writers and archive file growth alone do not establish all of those. The
existing two slots avoid the 38th-index problem, but writing an offline-authored
book into a user's signed profile still needs a proved profile attachment,
serialization/version/signature transaction and load/reload ownership. Native
standalone Playbook save type 6 is proved; automatic attachment to every profile
and independent per-Franchise-team two-book selection are not. The retail
importers also mutate incrementally and deduplicate by names in places, so they
cannot be treated as an atomic collision-safe cross-book API without further
work. No new profile field, slot index, archive directory or signature format is
guessed. These are the exact deferred portions of the requested editor.

## Tests and limits

Final commands/results are recorded below. Every suite runs
with plain Python/unittest. Private evidence and Unicorn/Capstone absence cause
specific skips. No whole disc or archive pack is loaded into RAM.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_playbook_pair.py` | 7 passed, 16.827 s. Pins, mixed/foreign refusal, zero-state ownership, receipts, replay, rows and capability schema. |
| `python3 tests/mod_editor/test_nfl2k5_playbook_pair_unicorn.py` | 20 passed, 10.780 s; peak RSS 76,132 KiB. Emitted merge/lifecycle code, native mode setup, native accessors and custom-book serializer/load roundtrip. |
| `python3 tools/nfl2k5_playbook_pair_assemble.py --check` | Passed; checked-in generated x86 matches C/S. |
| `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py` | 23 passed, 823.039 s; peak RSS 203,584 KiB. Includes the complete union in both orders and a temporary bounded synthetic image transport. |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 99 passed, 1,471.612 s; peak RSS 340,500 KiB. Every owner in forward/reverse orders and both allocator entry paths; writable targets and RO/RX separation. |
| `NFL2K5_PLAYBOOK_PAIR_MANIFEST="$PWD/.scratch/playbook-pair-manifest.json" python3 tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py` | 1 passed, 188.073 s; peak RSS 241,568 KiB. Observed 108 actual XBE transactions / 11,835 reservations, checked current source fingerprints, all section digests, exclusive attribution and allocation projection. |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | Passed; spare RX/RW/RO is 44,432 / 4,096 / 4,008 bytes. |

The following commands used
`NFL2K5_CAVE_MANIFEST="$PWD/.scratch/playbook-pair-manifest.json"`. The cave gate
was partitioned across four plain-Python invocations covering all five test
classes and all 111 tests; no gate test was omitted. Timed runs used
`/usr/bin/time -v`.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py CaveReferenceTests ScorebugReferenceReservations` | 28 passed, 213.935 s; peak RSS 236,072 KiB. |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py ReverseOwnerOrderTests` | 28 passed, 311.171 s; peak RSS 281,004 KiB. |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py ScaleoutOwnerTests` | 27 passed, 217.291 s; peak RSS 229,204 KiB. |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py ScaleoutReverseOwnerTests` | 28 passed, 311.608 s; peak RSS 266,644 KiB. |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 229.302 s; peak RSS 922,432 KiB. Fresh-source enforcement, full legacy-reference equivalence and negative cave checks remain intact. |

Total: **289 passing tests** in the final runs above. The final manifest's 278
source fingerprints match the current tree. Every new hook consists of complete
instructions, has no retail branch/pointer into its interior, and has exclusive
ownership; all three new allocator children are reserved under their named
owner. Per-process peak memory stayed below 1 GiB, within the 2 GiB limit.

The CLI was exercised with `python3 -m mod_editor.core.nfl2k5_playbook_pair
apply <retail.xbe> <temporary-output.xbe>`, followed by `status` and a repeat
write to the existing output. Apply/status passed, the existing output was
refused, and TemporaryDirectory removed it. Receipt:
`.scratch/pair-cli-receipt.json`. Python compilation and `git diff --check`
passed. All protected paths compare unchanged to the base commit.

Initial tests exposed two implementation assumptions that were corrected:
native exhibition is mode 4, and the visibility callback writes a runtime-row
flag through EDX. The final emitted-instruction suite covers both. The first
XBE-only manifest fixture also recorded nested generic writers as owners and
missed an adapter's captured function. The cave/oracle guards rejected that
incorrect attribution. The fixture now records the real outer owner and wraps
the adapter, with explicit exclusive-ownership and section-digest assertions;
no oracle or overlap guard was relaxed.

The disk preflight reported 93 GiB available on `/`, already below the brief's
100 GB free-space floor. No real disc/archive copy was made. Instead the
new manifest test observes the production XBE writers while executing the
complete gate composition, then validates every current source fingerprint.
Its scratch JSON is explicitly XBE-only, `new_disc_built=false`,
`release_manifest=false`. It neither refreshes stale historical pins by fiat nor
certifies the protected release disc manifest. That real rebuild remains a
protected integration step for Claude when disk space permits.

HYPOTHESIS / UNWITNESSED: native menu layout and controller interaction, real
asynchronous I/O and resource lifetime under all match exits, Xbox heap margin,
CPU play distributions, animation and player assignment behavior, and actual
signed custom-book saves. Structural/CPU tests do not turn these into gameplay
witnesses.

## Noah's witness list

1. Enable only the explicit pairing option. Check both pregame Options lists:
   each offensive choice followed by Defensive playbook; legible captions,
   values, scrolling and back navigation; Same as offense initially.
2. Play Now: Chiefs offense/Ravens defense on HOME, then AWAY. Repeat human vs
   CPU, CPU vs human and CPU vs CPU. Verify offense, defense and special-team
   menus across possession changes, punt/return, field goal/defense and kickoff.
3. Select ordinary fronts and coverages, all five default audibles, formation
   audibles, hot routes, flips, motion, defensive shifts and personnel packages.
   Check every player, including substitutions, then repeat on the next snap.
4. Pair both sides differently; retry the same book, change a team after
   selecting a defense, cancel during loading, quit a game and start another.
   Check that no old choice/book survives and User A/B books were not overwritten.
5. Choose CIN offense/OAK defense and confirm the HOME/AWAY fallback notice and
   complete original book. Also try a missing or deliberately invalid donor on
   a disposable install. Do not accept a partial menu or silent truncation.
6. Franchise: human and CPU teams, home/away, regular-season and playoff games.
   Select the pair before each game. Verify the explicit no-persistence notice;
   after save/quit/reload and next week it must again be Same as offense.
7. With a paired side, confirm ordinary CPU coaching works while VIP learning/
   replay is absent. With Same as offense and with a failed pair, confirm native
   VIP behavior. Do not combine authored read-option/spy controls with pairing.
8. Open the retail Playbook Manager, build a User A/B book from existing plays,
   edit its audibles/substitutions, save it through the native Playbook save
   command, quit/reload, select it for an ordinary unpaired game and verify its
   plays. Record whether and where a profile contains or references that save.
9. Run several full games and all exit paths to check heap/resource cleanup and
   absence of crashes or changed unrelated save state.

Delivery uses an explicit-path local commit on `astra/r65-playbook-pair`, with
the 18 feature/report/test paths only. No push. `ASTRA_BRIEF.md` and `.scratch/`
are excluded. The scratch receipts and logs remain available for continuation
or local review; they contain no full disc, archive pack or generated XBE.

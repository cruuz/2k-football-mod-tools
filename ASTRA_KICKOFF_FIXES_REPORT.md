# Kickoff fixes A-D

EXPERIMENTAL / UNWITNESSED. Base: `e997a8e889473cca5df7a01412c96da2aa1e6bbf`.
Work completed in the assigned r63 worktree, using read-only USA executable
and PLAY resources. No emulator, GUI, audio, network, disc build, archive
mutation, or push. Noah supplied the four observations below; the new build
has not been played.

The bounded changes add an in-field touchback eligibility guard, let held
players select and sample a neutral idle pose while keeping their position,
and replace normal-return blocking chains with local assignments. The world
art investigation does **not** justify a further widescreen x correction.
The exact visual cause of D remains open; this report does not claim it fixed.

## Evidence and decisions

| Witness | PROVED | Decision / HYPOTHESIS |
|---|---|---|
| A: touchback when ball looked fielded/downed around the receiving 1 | The dynamic classifier reads actual ball/contact z, signed in the kicking direction. The goal is 4572 cm, exactly 50 yards from midfield. The receiving 1 is 4480.56 cm, inside the landing zone. No one-yard boundary error exists. Retail `B6760` can return touchback eligibility from player-root position or descriptor `5103A0`, without checking ball position. | Guard `B6760` for a live, active normal dynamic kickoff, the actual receiving ball carrier, and a ball inside the landing zone. Return false; otherwise execute retail. This prevents the proved counterexample. Which eligibility branch caused Noah's event is HYPOTHESIS. |
| B: sideways/stale pose until release in kickoff practice | The previous owner returned from both `1CD5D0` planning and `218010` animation sampling, merely setting animation-updated. Its final position hook copied the old heading back too. | Keep planning held, clear running/turning input, face the opponent using retail `1A89E0`, enter the same idle/locomotion descriptor `50F4EC` used by initial placement at `155017`, and run the real sampler continuation. Keep position fixed while animation advances. Exact rendered idle clip is UNWITNESSED. |
| C: second returner blocks the deep kicker; front blockers run past coverage | All 36 normal-return books share the same chains. Front slots 2-6 have 21-30 yard rush legs before blocking. Slots 7-10 still share the deep-returner receive/follow chain, including the alternate release block. Those nodes also serve onside returns. | Allocate private validated chains. Slots 2-10 start an immediate drive block at their current position. Slots 0/1 preserve the entire normal receive branch, replacing only the alternate non-carrier block with a local lead block. Better target choice in Noah's crowded returns is HYPOTHESIS; no hard-coded kicker target was found. |
| D: on-field kickoff play/landing art misplaced with widescreen v3 | The traced on-field assignment renderer emits world-space vertices; it does not call CPU projection `2AB40`. Its diagram compression is disabled in the world pass. The active world projection is already widened by v3. | Do not apply HUD x-undo to this world route. The revised return chains also remove obsolete long assignment art. The precise landing-art variant and camera state in Noah's observation remain HYPOTHESIS/open. |

### A: coordinate and scoring trace

Dynamic classifier constants, unchanged:

* `4E72A0`: goal `4572.0` cm, inclusive end-zone boundary.
* `4F0F98`: landing-zone front edge `2743.199951` cm (receiving 20).
* `4EE8E0`: half width `2438.399902` cm.
* `4E72B8`: yard `91.440002` cm.

Ground contact uses the supplied collision position in EDX. Player/dead-ball
checks use the ball object's `+14` transform and z at `+8`, not the predicted
landing spot, player's feet, or a timer. The sign follows the kicking team's
direction, latched at launch. First-contact history remains separate from
current position.

Retail tackle/down path `B96B0 -> B6760 -> A1A20 -> B7780` can set the context
`+17C` touchback marker. `B6760` tests the player's root transform at
`player+18 -> +30/+38` against the team's end-zone rectangle and calls
`222F80`, which recognizes descriptor `5103A0` independently of ball position.
The ensuing impetus/ownership checks can return true. The dead-ball path
`B7BB0` also calls this eligibility function. Retail constants `4E72B0`
(-4572) and `4F0F9C` (-5486.3999) likewise do not encode a one-yard exception.

New hook `B6760..B6766` pins `83 ec 0c 8b 47 38` (two complete instructions).
It identifies the receiving team through the saved kicker at `CTX+1C4`, not
through mutable current possession. It leaves true end-zone balls and other
plays on the retail path. The normal phase/active/live guards remain; no
safety, onside, or scrimmage rule is replaced. The guard is specifically for
the landing zone, not a general rewrite of all football scoring.

The new bounded test reproduces retail eligibility=true at the receiving
1, half-yard and 0.01-yard points using descriptor `5103A0`; both installed
patch variants return false. Goal-line equality and 0.01 yard beyond it still
return true. Both field directions execute. This proves a counterexample and
its guard, not that this descriptor was present during Noah's play.

### B: stationary players, live animation

Hold eligibility stays on normal kickoff formation type 8, on-field slots
0-10, in ready state 13 and approach/live state 14 before first contact.
The ten coverage players and nine setup-zone blockers are held. Kicker slot
0 and receiving slots 0/1 retain their existing freedom to kick/field the
ball. State 12 still permits lineup. Consequently, a truly deep returner
already excluded from the hold would require another explanation of B;
Noah's apparent returner was not identified by slot in the observation.

The held motion wrapper zeros controller speed and its turning bit, sets
heading coherently through the native setter, saves the 48-byte transform
on the stack **before** entering the idle descriptor, and runs the retail
animation sampler. It restores the saved transform afterward, including
any root movement caused by clip entry. The final collision/position setter
restores only the 16-byte position vector from the frame snapshot, retaining
the new heading. No timer releases anyone. The existing contact latch does.

Unicorn executes `1A89E0`, `1CD550`, `2132A0`, `305920`, `305870`, `2FCAC0`,
and the `218010` continuation with bounded animation tables. Clip installation
`2D6B70` and animation rendering `31BEB0` are explicit doubles, as are
attribute updates and scene notifications. Tests seed a sideways heading,
running input, old clip, and deliberately moving sampler; three held frames
select the zero-speed clip, face the kick, and retain position, then release
planning on contact. Both old-cave and grown allocations execute with RX
protection. This is not a rendered-mesh or gameplay animation proof.

### C: fixed PLAY resources and local blocking

New core `nfl2k5_kickoff_returns.py` exposes resource `status` and idempotent
`apply`. The companion tool exposes streamed archive/image `status`/`apply`
and a CLI. It recognizes the three normal return plays by formation type 9,
menu/name/family, and complete retail-chain SHA-256 pins; mixed or foreign
chains are refused. All 36 books match these pins: 32 NFL teams plus GEN,
Editor, reference and WCO. PRACTICE has no corresponding normal kickoff pair.

The existing formation/play writer and rule validator append 78 nodes per
book and repoint the replaced assignments without changing resource size.
No shared original node is edited. All other plays, including onside and
safety plays, retain identical descriptors and chains. Normal receiving
branches for both deep slots are byte-identical. Total: 2,808 nodes appended,
19,217 byte differences across 36 resources, each still 0x133B0 bytes.
Minimum audited spare capacity before this change was 761 nodes; every
actual compilation and subsequent validation passed.

Setup blockers get Start then ACTION+terminal Block Leg type 0 (drive),
relative=1, offset=(0,0), turn=2 (no extra 45-degree bias). Deep non-carriers
get alternate-terminal Block Leg type 4 (lead), likewise relative to their
current position with zero offset. No returner is forced to be the carrier.

Unicorn decodes the actual packed block operands through `2B5D60`, reads the
engine operand cache through `1B8C40/1B8CA0`, and executes `2400B0` and
`23F450` up to the target selector `2FAFF0`. Type 0 selects mode 2; type 4
selects mode 3. Both pass the blocker's current world position, with zero
run-to offset, in both directions. Mode 3 also explicitly bases its scoring
origin on the player's current position (`2FAFF0`, switch case 3). Opponent
history/stance setup are doubles; the full opponent scoring contest is not
simulated. Whether nearby coverage is consistently preferred over the deep
kicker in traffic is still a gameplay witness, not a proved AI outcome.

All-resource planning precedes any archive write. A bounded archive fixture
proves exact writes, idempotence and mixed-book refusal before the first
write. No private archive was opened writable during this work. Protected
build/packaging integration is fully specified in `WIRING.md` and is still
required before the new data writer runs automatically in Studio.

### D: projection audit extension

The previous widescreen report left exact world-route variants open. The
additional trace is:

| Consumer | Pinned executable/corpus route | Result |
|---|---|---|
| On-field play art | `64E80 -> 11A8F0 -> 75D90 -> 1807F0`, world-mode argument 0 | `BDFBE4=0`; no diagram compression. |
| Player assignment origin | `75D90 -> 1840B0 -> 182480` | Current player/selected-play world coordinates; existing kickoff lineup exception remains active. |
| Diagram coordinate compressor | `182480 -> 180120` | Immediate return when `BDFBE4=0`. Type-9/13 compression belongs to the diagram pass. |
| Block/run assignment line | Opcode 17 draw callback `181CC0 -> 180410 -> 164AC0 -> 164880 -> 2D2A0/2CB50` | World endpoints become GPU vertices. No CPU `2AB40` HUD projection. |
| Dashed/follow path and caps | `165820 -> 164880`; caps `164DD0 -> 164AC0` | Same world geometry path. |
| Traced player/landing marker family | `F9320 -> F8880` | World marker geometry; active GPU projection, already covered by v3. Exact witnessed marker variant remains unidentified. |
| Play-call diagram/menu | `144BA0`, camera `BD7030` | Separate diagram camera, retained retail layout. Not the world pass. |

The new CPU proof executes `180120` in world mode and the real thick-line
geometry `164AC0` with and without widescreen. It captures all four world
vertices at final submission `164880`, checks the line remains centered on
its supplied world endpoints, and asserts no `2AB40` call. Vertices are
identical across both aspect settings. V3's separate 13-test polish suite
remains green. The five CPU-projected HUD wrapper sites (`7EC59`, `FA2A1`,
`FA31E`, `32C895`, `32C8AC`) are unchanged.

**Open D limitation:** neither the GPU rasterizer nor Noah's camera/marker
variant was reproduced. Wrong art due to stale old assignment endpoints is
a plausible partial explanation, not an established cause of the complete
widescreen observation. No speculative world x scaling was installed.

## Allocation, pins and receipts

Twelve hooks share the same compiler. Branch relaxation operates on symbolic
assembler items, shortening only local jumps with valid 8-bit displacements;
it does not search executable bytes or relocate opcodes heuristically.
Code uses 1,717 of the existing 1,939 bytes (222 spare). RW remains ten bytes;
new temporary transform storage is on the stack. No `.text` runtime state,
new cave, new owner, or allocator budget increase. Existing allocator union
and owner ordering remain intact.

The retail XBE SHA-256 is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Legacy cave SHA pin remains
`15d306fbdb8b915a5ebfbdbc92634553a644a409e50bfeec87b06d248f8f3d90`.
Hooks/caves/status refuse mixed, foreign and previous-revision streams before
mutation. Same-revision application is idempotent. Section digests are
repinned by existing helpers. Rebuild old experimental discs from retail.

[Committed exact receipts](docs/nfl2k5_kickoff_fixes_receipts.json) contain
input/output hashes, each XBE hook/cave offset and emitted bytes, before
hashes (or tiny hook bytes), and all 36 PLAY source/result hashes with exact
resource-relative and archive-virtual before/after edits. The grown receipt
uses the current full allocator request union: RX `14BA2C0`, RW `14BB000`.
It describes allocation plus this owner, not a fully composed final disc.
The gate tests separately compose every owner in both orders and both
allocator modes. No proprietary XBE, complete PLAY resource, pack or disc
is distributed in the receipts.

## Validation and delivery

Final commands/results are recorded below. No private test
was skipped. All suites run with plain `python3 file.py`; fixture absence
uses precise skips in portable tests. The archive resource tests use bounded
readers, and no process loads a full disc or archive pack.

| Command | Final result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_dynamic_kickoff.py` | 23 passed, 42.640 s |
| `python3 tests/mod_editor/test_nfl2k5_kickoff_fixes.py` | 9 passed, 7.868 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed, 299.045 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 91 passed, 383.692 s |
| `python3 tests/mod_editor/test_nfl2k5_widescreen_polish.py` | 13 passed, 6.492 s |
| `python3 tests/nfl2k5_kickoff_alignment_test.py` | 7 passed, 0.564 s |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | Passed; no request-row changes |
| `python3 -m tools.nfl2k5_kickoff_returns status <extracted>/vc_53450030` | Retail, 36 books; read-only |
| `git diff --check` | Passed |

The two gates include every existing owner in both orders and allocator
modes. Added assertions cover the new complete eligibility hook, the exact
grown instruction stream, and unchanged code/state allocations. The scoped
eligibility regression also checks safety, scrimmage, ready state, inactive
kickoff, loose/other-held ball, sideline and short-zone bypasses.

Intermediate regression runs exposed stale fixture assumptions: they expected
animation to remain skipped and all 48 transform bytes to be restored. Those
expectations were replaced with native descriptor/idle selection and separate
position/heading checks. A draft two-node blocking chain lacked ACTION on its
terminal node and was rejected by the existing validator; the final chain
uses flags `06`. No validator or protected gate was weakened. Final logs,
corpus excerpts and scratch receipts remain under `.scratch/`; no private
binary copy is retained there.

## Noah's witness list

1. **A, field versus goal:** human and CPU normal returns, both directions.
   Field/down the ball at the 1, inside the 1, on the goal line and just in the
   end zone. Inspect the ball as well as the player's root/feet. In-field
   downs should retain that spot, with no touchback announcement or jump to
   the 35. True direct end-zone touchbacks should use 35 (or selected 2024
   setting 30); landing-zone-first balls downed in the end zone should retain
   the existing 20-yard behavior. Return out and back into the end zone too.
2. **B, practice repetition:** kickoff practice and an ordinary game; repeat
   plays after a diving catch, tackle, turn and prior kick. Observe ready,
   kicker approach, flight, first touch, and the following frame. Held players
   should show a neutral idle stance facing the kick, without sliding or a
   sideways old pose, and release exactly on contact. Identify whether any
   remaining apparent returner is deep slot 0/1 or a setup blocker 2-10.
   Switch human control to a coverage player and repeat in both directions.
3. **C, three return calls:** Return Left, Middle and Right, each with either
   deep player fielding the ball, both directions, short and deep normal
   kicks. The other returner should lead/block locally instead of seeking
   the far kicker; front and rear setup blockers should engage nearby
   coverage without the obsolete long run past it. Check lane variety,
   immediate collisions, target switching, penalties and any idle blocker.
   Onside return and safety kick assignments should behave as before.
4. **D, identify the visual variant:** compare 4:3 and widescreen v3 for the
   same kickoff/camera. Check on-field assignment lines, terminal arrows,
   ball landing ring/zone, player ring and the separate play-call diagram
   against players, ball and painted yard lines. Include left/right edges,
   both end directions, practice, live-camera transition and replay. Record
   which element moves incorrectly and at what state; no current proof
   establishes that this observation has been eliminated.
5. **Build integration:** after Claude applies `WIRING.md`, build a disposable
   Experimental image from retail, verify the receipt contains the new
   `kickoff_returns` step for 36 books and the twelve-hook XBE revision, then
   perform the checks above. Basic/Advanced should retain their existing
   defaults. No previously patched kickoff disc is a supported upgrade base.

## Commit delivery

The requested explicit-path staging succeeded; no bundle fallback was needed.
The delivery commit contains the eleven explicit source, test, receipt and
report paths. `ASTRA_BRIEF.md`, `.scratch/` and all protected files are
excluded. Working research remains local in `.scratch/`. The final response
supplies the commit ID. No push was performed.

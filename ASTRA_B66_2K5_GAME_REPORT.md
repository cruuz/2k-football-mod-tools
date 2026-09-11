# Beta 66 D2: NFL 2K5 game-code research and fixes

Branch: `astra/b66-2k5-game`. Retail USA XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
All game behavior remains **UNWITNESSED**. Evidence here is pinned retail bytes,
Capstone disassembly and bounded native x86 or recovered-C execution. No console
emulator, game boot, GPU display, audio, network, retail disc build or signed-save edit
was used. The optional Ghidra project was located; the proof instruments used
were the pinned repository readers and executable harnesses.

Implemented: collection-list bounds, the paired-root/source-identity contract,
and a reversible helmet Matte writer. Boot/play-call attribution, playoff QB
attribution and unrestricted skeleton import remain unresolved at the specific
boundaries below. Protected integration is specified in the **Beta 66 D2**
section appended to `WIRING.md`; it has not been applied in this worktree.

## 4. Mud: added-song collection freeze

Mud: “I imported songs and the game still freezes after going to Incite #2
(that's where they go) but I can play them in the stadium music creator.”

| Status | Finding and evidence |
| --- | --- |
| PROVED | `0x32A0F0` is the Crib collection-list builder. Its retail `cmp edi,13` at `0x32A160` uses the HDD row capacity for disc collections too. |
| PROVED | UI label pointers start at `0xAE6128`. HDD starts at index 22 and has thirteen triples; disc starts at index 49 and has four triples. Both end at `0xAE621C`, where the navigation labels begin. |
| PROVED | A fifth disc row hashes navigation labels as song widgets. A sixth reaches the null label at `0xAE6228`; native `0x3865D: mov ax,[ebx]` dereferences zero. This happens with 59+2 songs, before preview audio is needed. |
| PROVED | Replacing the row-number bound with `cmp esi,0xAE621C; jae 0x32A255` and retargeting the loop back edge repairs the full native list build. It uses four disc rows or thirteen HDD rows, with the existing scrolling offset. |
| PROVED | The full builder runs for 59, 60, 61, 193 and 200 total songs, at every valid offset through the appended collection; the same list under collections 14 and 17 succeeds. |
| HYPOTHESIS | This is the precise failure Mud encountered on his build. His executable/save was not supplied. The native failure matches the collection-entry trigger, but no played confirmation is claimed. |

Consumer audit, using the retail instructions and metadata pointers:

| Consumer | Native site / storage | Result |
| --- | --- | --- |
| Collection/song tuple | `0x27FF20`, collection record at `0xAC9C98 + 32*c`, song root at `0xAC9C9C + 32*c` | Count/root refer to the grown song record array. |
| Title/checksum | `0x27F9A0`, record `+4`; `0x27F550` hashes collection name/title | Grown pointers are valid; the native builder executes these lookups. |
| Artist | `0x27F9F0`, record `+8` | Part of the grown record, no separate 59-element artist array found. |
| Duration/frames | `0x27FCE0`, record `+12`; `0x27FC80` / `0x27EFB0` convert the duration text | Installed bounded duration strings; native list formatting path executes. Raw bank frame counts remain owned by the music bank writer. |
| Preview stream | `0x27FA40` gets the record's stream ordinal; `0x27F740` and `0x27FF90` route preview | Uses the installed record plus music policy/playlist routing. Actual `cribmusic`/`crib22` decoding and Xbox audio are outside the list-build proof. |
| Purchase/unlock | `0x27F520`, collection `+0x14`, then `0x10E8F0` | Collection state, not a fixed per-song purchase table. No added-song overrun found here. |
| Album art/icon | `0x27F5D0`, collection `+4`; details screen resource binding near `0x32A8FF` / `0x32A90C` | Collection artwork pointer. No separate song-indexed image table found on this path. |
| Spoken outtake flag | Music catalogue metadata and stream choice | No separate retail per-song boolean consumer found in the inspected Crib routines. Decoder behavior is not claimed proved. |
| List widget identity | `0x32A185` through `0x32A241`, triple of pointers passed to `0x38650` | **The reproduced out-of-bounds consumer.** |

`nfl2k5_jukebox_list.py` owns only `0x32A159..0x32A169` and
`0x32A24F..0x32A255`. It pins the normalized complete 435-byte function
(SHA-256 `36a66f2a35336c845fc2713630d397947c8d96b9365bdf68860d5583dff22a80`),
rejects foreign/mixed states, seals the XBE digests and reparses after writing.
The native down-button arm at `0x32B450` already uses four disc rows / thirteen
HDD rows; its scrolling transition is also tested through the last added song.
No table allocation, executable scratch, collection-number test or I/O wait
is added. `nfl2k5_music_metadata.apply/status` now includes this repair.
Previously expanded executables missing the repair require a clean rebuild.

The cave gate initially treated the old internal back edge
`0x32A24F -> 0x32A160` as external to the first changed run. Its declaration
now groups the complete pinned function, as existing multi-site function
rewrites do. A fresh retail reference scan finds **no external interior
entry** into `0x32A0F0..0x32A2A3`; it still checks every such entry and does
not classify these live bytes as a free cave. Parent metadata recording
delegates only these exactly verified child spans to the jukebox owner.

**D1 coordination:** retain this automatic metadata dependency when moving the
songs into their own collection. The D1 collection number is not part of the
repair. The handoff in WIRING names the two metadata integration lines and the
collection-independent native fixture. No direct message to another job was sent.

**Noah's witness:** build a clean disc with two added tracks, then with the
maximum library. Enter the added-song collection, scroll from first to last
track and back, open details, preview both `cribmusic` and `crib22` material,
and return to the collection. Confirm title, artist, duration and art; test a
locked and unlocked profile. Repeat with D1's dedicated collection, and check
an Xbox HDD collection still shows thirteen rows and scrolls normally.

## 12 / 22. jrolling2003 SEGA stall and CER play-call freeze

jrolling2003: “had to turn some experimental settings off since I got stuck on
the sega screen.” CER's reported sequence is PAT, kickoff, a goal-post/stands
camera and KICK RETURN play call. Neither report supplies the exact failed
recipe plus an executable/save snapshot at the stall.

| Status | Finding |
| --- | --- |
| PROVED | The named bounded suites terminate on their defined fixtures. The music cold exclusion, profile stop override and player re-creation reach their native continuation/stub boundaries. |
| PROVED | Broadcast row 7 retains the retail kick/preview entries; its edited entries are states 1 and 8..19. The existing native menu, gameplay projection, coach-binding and generic-MyCareer camera tests pass. |
| HYPOTHESIS | An experimental owner causes either reported stall. No failing owner or shipping preset has been causally identified. |
| HYPOTHESIS | An entire cold boot or PAT -> kickoff -> KICK RETURN screen transition succeeds under arbitrary combinations. None of these bounded fixtures executes the complete device/event lifecycle. |

The table distinguishes a terminating hook from the unproved continuation.
A passing isolated fixture is not a proof that a device call returns on hardware.

| Owner / exact sites | PROVED boundary from this run | HYPOTHESIS / exact remaining boundary |
| --- | --- | --- |
| Music playlist `player_init 0xF63CA`, `profile_context 0xF64CD`, `mode 0xF6510`, screen event `0x6E4E0` | Cold exclusions, modes, generation reset, profile override and 24 named context routes terminate. Initialization has a bounded four-word copy; playlist bag count is bounded by the selection compiler. | `player_init` continues to retail `0x27F1B0`; mode/loading to `0xF5410`, game music to `0x1C4210`. Resource `0x449E0`, bank bind `0xCEF80`, packet queue `0xCF150` and callbacks are not real Xbox I/O in the harness. |
| Other playlist hooks `0x325E22`, `0x27F040`, `0x28016D`, `0xD90F0`, `0xD9350`, `0x2801A0`, `0x280450`, `0x27FF15`, `0x2806B2`, `0x27FEC0`, `0x27F6B0`, `0x27F6F0`, `0x27FF90`, `0x2804C0` | Existing playlist/context suites exercise enqueue, dispatch, frame, preview, suspend, pause/resume, halftime and native screen push/pop boundaries. | Asynchronous packet completion and native 3D/audio callbacks remain the same unproved frontier; no SEGA-loop attribution. |
| Screen timing and hooks `0x23ECD2`, `0x19C7E9` | Bounded screen blocking/QB timer execution; malformed grammar exits through tested bounds. Screen timing A/B/C/D edits PLAY nodes, not a boot polling routine. | Actual actor scheduling beyond the native timer continuations and `0x11A7C0` phase dispatch is not reconstructed from CER's state. |
| Widescreen v3 `0x2ACA1`, `0x66A52`, `0x9E1BC` | Native projection, pixel camera/scissor and sky lens paths tested. No owned wait loop or mutable executable data introduced. | Native draw/device completion after `0x28110` and the real scene/camera lifecycle. |
| Scorebar v3 / runtime `0xFCE56`, `0xFCFA2`, native visibility `0xFCA87` | All six scorebar states, transition/marker state, emitted draw and composition tests. | Rendering callbacks and GPU submission are fixture boundaries. A screen reaching its draw call is not a completed play-call frame. Other live sites are `0xFCFFC`, `0xFD07B`, `0xFD0EB`, `0xFD15E`, `0xFC9F6`, `0xFCEC7`, `0x9FEAB`, `0xFC6D5`, `0xFC010`, `0xFC030`, `0xFBE30`, `0xFC285`, `0xFC305`, `0xFC0A6` and the quarter table at `0xFC0F4..0xFC100`. |
| Calendar engine `0x1C1880`, `0x1C19F0`, `0x1C1940`, `0x8B0E7`, `0xD22AC`, `0xD2356`, `0x2BF5CA`, `0x2BF60E`, `0x2BF61C`, `0x2BF646`, `0x2BF661`, `0x2BF67C`, `0x2BF697`, `0x347714`, `0x3663E4` | The exhaustive 128-season native Gregorian/weekday/calendar suite terminates. Helpers operate on supplied date fields, with no I/O wait. | Caller-supplied date/context validity before a full title boot; downstream schedule/event consumers beyond these date helpers. |
| Practice squad screen, Coach's Desk pointer `0x5221A0`; native event dependency `0x6E4E0` | Native screen fixture covers descriptor, list, move/cancel transactions and composition. | It requires a valid franchise screen/context; native `0x14E440`, `0x174C70` and dialog/roster lifecycle have no complete boot witness. |
| Abilities `0x17B010`, `0x75CC8`, `0x15647D`, `0x18EC6D`, `0x1CD550`, `0x2D43F0`, `0x2D46D0`, `0x2D4740` | Bounded attribute/decode/dispatch/init/generate/AI/consume suite passes. Hooks apply bounded record/flag tests, not a boot wait. | Init tail `0x1CD555`, generation tail `0x2D43F5`, and real actor/account state at `0x1B3340`; no evidence tying these to SEGA. |
| Guardian `0x8F02E`, `0x8FB45`, `0xC16CD` | Native resource registration, material binder, refresh, clone and absent-resource guards terminate. | Runtime resource lookup `0x449E0` and actual texture/device lifetime; invalid render objects before retail caller initialization are not a valid fixture. |
| Seven-on-seven loader `0x62D0C`, mode switch `0xE33FF` | Native loader/switch and practice selection tests pass with bounded source/resource fixtures. Owned RW begins zero. | Actual load queue completion beyond the native loader boundary and live kickoff scheduling. |
| Position pools `0x242B07`, existing row lookup body `0x2BA840` | Pinned bounded row lookup/filter writer. This is a finite lookup, not a load-completion loop. | Actual roster/player pointers on the failing transition; no failing value captured. |
| MyCareer camera entry `0xA5490`, native screen push `0x6E390`; M3 hooks in `nfl2k5_my_career_mode.MODE_HOOKS/SAVE_HOOKS` | Existing MyCareer native suite and Broadcast composition pass. | Screen and actor objects supplied by fixtures, save I/O and full `0x11A7C0` phase scheduling are not boot/transition proofs. |
| Camera row 7: selectors `0x16D1D4`, `0x16E7B1`, `0x16E864`, `0xA55EB`; spectator choice `0xA54C3` | Native options/selection, all edited gameplay-state projections, both aspects, pass options, player binding and sampled stands clearance pass. | Game-entry continuation `0xA5490` and state transition dispatch beyond the camera selection are unproved for CER's recorded play. |

Additional M3 transition sites audited against the existing MODE_HOOKS:
`0x64D27` skip tick; `0x13856`/`0x112DD9` skip buttons; `0x8970B` camera pick;
`0x1212A5` art input; `0xC5D60`/`0xC5D69`/`0xC74E3`/`0xC74EC` result;
`0x11A8F5` visual dispatch; `0xC5D9E` stats commit; `0x6E390` screen dispatch;
`0x2C0E83` practice return; `0x16DDE0` loaded replacement. Save/load seams are
`0x16AA26`, `0x16ABB5`, `0x16E50D`, `0x16E5CE`, `0x16E6D3`, `0x16E7E5`,
`0x16E815`. The mode-audit suite checks pinned save ownership; the routes suite adds finite
route evidence;
actual save I/O and complete boot/transition state remain HYPOTHESIS.

The supplied video frames were inspected directly: `_03.png` shows the goal
post and stands with NE 7 / SEA 7, second quarter 2:32, Kickoff; `_05.png`
shows KICK RETURN entering over the players; `_07.png` shows all three return
choices, NE 35 and play clock :40. Thus this recording reaches a rendered
play-call screen. The frames alone do not establish a CPU spin, prove that
input responds, or show that Broadcast was selected.

Preset audit: the shipped Experimental preset enables calendar, widescreen,
static scorebar and screen timing D; merged position pools and camera are also
used by Advanced. Music shuffle, authored read controls, QB spy, pairing,
abilities, Guardian overlay, seven-on-seven and MyCareer are opt-in and false
in every preset. No preset was changed based on these hypotheses. Exact build
receipts must be compared before naming a particular option as the SEGA stall.

**Noah's witness:** retain the failed beta-63.1 build receipt and a copy of the
save/profile. Cold boot the same recipe three times, recording the last screen.
Compare the clean Basic baseline, then one changed option at a time. For CER,
select Broadcast before kickoff; reproduce PAT -> kickoff -> KICK RETURN,
including replay/skip and a possession change. Record camera choice, active
options, team, quarter, phase and the exact point input stops. If it stalls,
capture the PC and the `0xE602B4`/`0xE602B8` phase values. Do not infer a fix
from a camera angle changing alone.

## 14. BigTimeEmpire: playoff backup QB

BigTimeEmpire reports CPU teams starting the backup QB instead of the starter
in franchise playoff games.

| Status | Finding |
| --- | --- |
| PROVED | Native weekly auto-depth routine `0x2BDCF0` sorts by rating returned at `0x2BDD71..0x2BDD88`, swaps roster pointers via `0xC3D70`, then assigns rank bits and calls the native compactor `0x243790`. |
| PROVED | With explicitly supplied unequal QB ratings, native sorting/compaction preserves the higher-rated starter at stages 8/9 and weeks 16, 17, 18, 21, 22; reversing the ratings reverses the order. Stage/week alone did not reproduce the bug. Rating calculation is a declared stub in this test. |
| PROVED | `0x2BE020` runs its CPU injury path at stages 8 and 9. It tests injury bits `player+0x28 & 0x3E0`, bit 31 at `+0x20`, then compares the duration bits 22..29 with `22-week`. Native calls into the IR transaction occur exactly above that threshold. |
| HYPOTHESIS | A stale injury flag, the `22-week` threshold at `0x2BE0B0`, or an injury-adjusted rating at `0x246D80` demotes the intended starter. No affected player's pre/post record or live rating return is available. |
| HYPOTHESIS | A playoff-specific lineup rebuild overrides the weekly result after `0x248075`. This needs the actual game-entry/lineup state, not just a synthetic roster sort. |

Exact blocker: no causal input for either `0x2BE0B0: cmp edx,ecx` / branch
`0x2BE0B2`, or the rating comparison `0x2BDD8D`. The candidate IR transaction at
`0x246FF0` reaches roster removal `0x2BD900` and notification `0x2BFDF0`.
The threshold probe observes entry to that transaction and does not fabricate
its downstream effects. The native compactor reads rank bits at `0x2437E5`
and rewrites ranks at `0x24386F`; it contains no playoff-week branch.
No `nfl2k5_playoff_starters` writer and no BASIC-preset change is justified yet.

**Noah's witness:** preserve a CPU team's save before week 17 and before its
first playoff game. Record both QBs' ratings, depth order, fatigue, injury type,
duration, IR membership and start eligibility. Advance one week at a time;
compare simulate vs play, with all options off and with Basic. Break/log at
`0x2BDCF0`, `0x246D80`, `0x2BE0B0` and the first on-field lineup selection. A
fix needs the first instruction that changes the intended starter's eligibility
or ordering, together with the actual before/after player records.

## 1. Smuzz: separate books with authored read option / QB spy

| Status | Finding |
| --- | --- |
| PROVED | Pairing copies and renumbers source plays into a private body. Publishing only its root is insufficient for QB spy: a donor play carries a different original book hash and ordinal. |
| PROVED | The pair owner now publishes both teams' merged/offense/defense roots in its existing RW allocation, with bounded read-root and source-identity callbacks. |
| PROVED | Read option consults the publication and retains its existing actual-team-root fallback. That v5 fallback was already more general than the old report's two-buffer description. QB spy retains its two fixed-buffer fallback. |
| PROVED | A private 270-entry u16 map preserves original play ordinal and offense/donor side. Before borrowing donor intent, the callback compares the full descriptor and both native script nodes. A changed live script fails closed. |
| PROVED | Native pair loading/merge, both home and away identity lookups, read-option lookup with a deliberately stale team root, unpaired spy fallback, cleanup and installation-order equivalence pass. |
| HYPOTHESIS | Played controls, audibles, hot routes and resource teardown in all modes work. No played witness is claimed. |

Contract address is **fixed for each sealed build**, derived as
`nfl2k5_playbook_pair.contract_va(xbe) = owned_data.va + 160` and linked as an
absolute immediate in both runtime readers. It is zero when no pair allocation
exists; allocation alone leaves the publication all zero. A process-wide
hard-coded address independent of the selected allocator union would violate
that union's ownership. No new allocation or reservation size was introduced.
In the observed complete gate union, owned RW starts at `0x014F4390`, so the
publication is at `0x014F4430` within its existing 512-byte allocation.

| Byte offset from contract | Meaning |
| --- | --- |
| 0 / 4 | Fastcall read-root / spy-source callback; zero means inactive |
| 8 / 12 / 16 | Home merged / original offense / original defense root |
| 20 / 24 / 28 | Away merged / original offense / original defense root |

Callbacks are published only after a complete successful merge. Cleanup revokes
both callbacks before freeing anything and clears all roots. The ordinal map
is inside the pair-owned heap allocation after its `0x13390` PLAY body, adding
540 bytes to that allocation, never to the resource manager. Readers scan at
most two roots, validate descriptor bounds, and never wait for loading.

Read-option RX remains within its existing 2048-byte reservation (2028 normal,
1904 diagnostic). A local short-branch trampoline preserves the existing edge
loop's control flow to accommodate the publication check. The original intent
hash checks remain. QB spy uses EDX:EAX for original root:descriptor, then runs
its existing exact original-book/play/slot/script lookup.

Three core `nfl2k5_throw_tuning.py` refusal sites were removed. The protected
`mod_build.py` refusal must be removed by the WIRING handoff; until integration,
the protected GUI/build path still refuses the combination. The old message
constant is retained only for that intermediate protected caller. EXPERIMENTAL,
all presets unchanged and off.

**Noah's witness:** author a read option in the offensive book and a QB spy in
the defensive donor. Choose different offense/defense books for both teams.
Run give/keep/pass and spy engagement, then change sides and repeat. Test an
unpaired side, hot routes/audibles, cancellation/reload and a second game with
pairing off. Verify fallback plays still run when the exact authoring signature
is absent or changed. Retain the pair/import receipts.

## 8. maumau78: Matte helmets

xevan: “all helmets share the same reflection texture.”

| Status | Finding |
| --- | --- |
| PROVED | Helmet shells are in low-body SCNE `3/113` and high-head SCNE `3/115`, not high-body `3/114`. Parsed A/B/C material indices are 12/14/16 and 0/2/21 respectively. |
| PROVED | Native reflection binding uses material `+0x34` (`0x8E430`, store `0x8E462`). Refresh `0x8FAD0` recomputes material byte `+9` from uniform shininess and lighting, storing at `0x8FBAE`. A zero authored only in a scene is overwritten. |
| PROVED | Three conditional branches at `0x8FB43`, `0x8FB4E`, `0x8FB59` identify shell A/B/C and can target the existing zero clamp `0x8FB9E`, then the same native `+9` store. The fourth material comparison keeps its original path. |
| PROVED | Full native refresh with native context/uniform reads, FPU conversion, clamp and loop sets all three shell weights to zero in both LODs. Only the four expected material weight bytes may change, and the fourth retains nonzero retail lighting. Actual scene material names are reparsed. |
| PROVED | Matte -> Glossy restores the exact retail XBE, including digests; replay is identical, malformed/partial edits refuse. Both installation orders with Guardian retain both owners and restoring Glossy retains Guardian. |
| HYPOTHESIS | The resulting displayed finish is the desired matte appearance in every lighting/weather/replay mode. Actual GPU rendering remains unwitnessed. |

`nfl2k5_helmet_finish.py`: **ADVANCED**, default **Glossy (retail)** / Matte off
in every preset. It changes three branch displacements, with no cave, new
resource, new texture, runtime scratch or package refit. It pins the complete
263-byte refresh function and accepts only an exactly verified Guardian hook
as a neighboring composition. Guardian's dependency guard reciprocally
normalizes only a complete exact Matte triple. No broad hash exemption.

CLI (new output only):
`python3 -m mod_editor.core.nfl2k5_helmet_finish source.xbe matte.xbe --finish matte`.
Use `--finish glossy` on a Matte input to restore. Protected registry and
Gameplay/Uniforms wiring is supplied separately, so the new option is not yet
rendered by this worktree's GUI.

**Noah's witness:** compare identical Glossy and Matte builds at noon, night,
rain and snow. Check both selectable shell styles, close replay and distant
Broadcast, both teams, player editor and Guardian on/off. Verify shell decals,
face masks, visors and uniform shine retain their intended appearance; return
to Glossy and compare with retail. Do not call the feature witnessed based
only on the byte-level weight test.

## 9. maumau78: edited glTF skeleton import

| Status | Finding |
| --- | --- |
| PROVED | The Models exporter writes named SCNE bind transforms, not the SKEL axis array, into glTF joint translations and inverse binds. Player SCNE bind records have stride 112, absolute translation `+0x40`, local translation `+0x50`, name pointer `+0x60`, parent `+0x64`; low/high counts are 25/62. |
| PROVED | SKEL `3/116` has a 400-byte array of 25 normalized four-float axes (w=0), SHA-256 `c0892cd00a6819031c5cc6e7e4392548cc72e665e27f7dc14c928fc860feed3d`. These are not endpoint lengths or a named rest-pose table. |
| PROVED | Retail `0x9064D` loads SKEL; `0x90654` publishes it at `0xB65B78`. The high-pose routine loads that pointer at `0x9214F`, adds 0x10, and uses an axis through `0x92216: lea ecx,[edi+0x20]`, passed to `0x90250` at `0x92252`. Runtime-derived joints also use fixed constants around `0x4EF8E0`. |
| PROVED | The existing constrained left-forearm writer coordinates low/high bind translations, twist pivots, mesh and normals, keeps SKEL axes, and refits both compressed spans without changing the scratch wrapper. Its existing native/recovered-C numerical gates are included in validation below. |
| HYPOTHESIS | Arbitrary edited glTF bones can be uniquely converted into the native SKEL axes and all high derived-joint constants, attachment and morph behavior. That inverse mapping is not proved. |

Exact blocker is the **representation mismatch**, not an unknown SKEL byte
stride: arbitrary glTF bone edits supply rest transforms; `0x92252` consumes
an independently authored axis while constructing a derived high-body matrix.
The Models geometry importer at `nfl2k5_models.py:1439` uses the first joint's
world-times-inverse-bind transform to interpret vertices, then its writer
preserves the native bind records. Accepting edited joints there would silently
omit their native axis/derived-joint/LOD obligations. Extending only SKEL would
not write the exported lengths at all. The existing ±2% left-forearm operation
is not advertised as general Blender skeleton import. No general bone writer
or false Models UI promise was added.

**Noah's witness / next evidence:** export the full lo_body/hi_body/hi_head set.
Use the existing constrained forearm edit first and compare all LODs, body
sizes, idle/run/pass/catch/tackle poses, hand-held ball and helmet attachments.
For general import, supply one intended edited skeleton with unchanged topology
and record precisely which local axes/lengths changed. First derive and test
its effect at `0x92252` and the high-joint graph, plus low/high bind skinning and
attachment paths. A Blender preview alone is not the required proof.

## Validation

All commands use standalone `python3` with `PYTHONPATH=.`. Missing retail assets
cause precise SkipTest in the added tests; this run had the retail XBE and packs.
The resource inventory was generated read-only with
`python3 tools/nfl_resource_scan.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --json .scratch/resource_inventory.json`.
Only metadata was written; no retail resource payload is committed.
The existing animation suite uses disposable compact synthetic XISO transport
fixtures for bounded resource spans. It does not copy or build a retail disc.

The protected release manifest correctly refuses its stale source pin:
`OracleError: stale reservation source: mod_editor/core/nfl2k5_guardian_overlay.py; regenerate manifest`.
It was not overwritten or given copied-forward fingerprints. The standalone
pair-manifest fixture instead observed 128 actual XBE transactions and 12,340
reservations from the current sources, verified every section digest, and
wrote a separate test-only manifest with `image_steps=[]`, `xbe_only=true`,
`release_manifest=false`, and `runtime_witnessed=false`. Its oracle run leaves
the resource/disc-build evidence check explicitly skipped. Claude must still
regenerate the protected production manifest after applying WIRING and merging
D1; this XBE evidence is not a release-disc certificate.

Reproduce the current-source ownership checks with:

```sh
mkdir -p .scratch
PYTHONPATH=. NFL2K5_PLAYBOOK_PAIR_MANIFEST="$PWD/.scratch/d2-xbe-manifest.json" python3 tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py
PYTHONPATH=. NFL2K5_CAVE_MANIFEST="$PWD/.scratch/d2-xbe-manifest.json" python3 tests/mod_editor/test_xbe_patch_cave_references.py
PYTHONPATH=. NFL2K5_CAVE_MANIFEST="$PWD/.scratch/d2-xbe-manifest.json" python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
PYTHONPATH=. python3 tests/mod_editor/test_xbe_patch_memory_writes.py
PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py
```

The matrix can also run with
`PYTHONPATH=. python3 tests/run_nfl2k5_pairwise.py --workers 4 --log-dir .scratch/pairwise`.
That is the final matrix command used here: it discovers the complete suite,
partitions its 388 cases into four plain standalone invocations of the same
test file, checks the executed case counts and exit statuses, and records every
case name and output hash. There are 377 distinct owner pairs; the mutually
exclusive legacy/generic MyCareer formats share an owner and are not a pair.
No assertion, fixture or owner list is replaced by the runner.

Final result: **1,063 passed, two skipped**, across 35 standalone suites
(1,065 reported cases). The two skips are the optional pre-existing patched-disc
smoke fixture in throw tuning and the explicitly absent resource/disc-build
evidence in the XBE-only oracle manifest. There are no skipped matrix or new
native-repair cases.

Unless the environment/partition command above applies, the exact invocation
for each row is `PYTHONPATH=. python3 <test file>`. Results reproduce the
standalone unittest summaries. Full commands, output hashes, writer source
hashes and manifest scope are in
`docs/mod_editor/nfl2k5_beta66_d2_validation.json`.

The observed test manifest SHA-256 is
`f3e454367fd85f4918847abcad3ac0f17a12ffca17e6bd017b388bee8f16bb53`;
its fully composed XBE SHA-256 is
`4509b85406055b30c8da2675379a8c9b03e86499e4723518ab4f81b11f58e7e0`.
Neither artifact contains a console witness.

Both proposed distribution capability rows pass the registry schema after
the WIRING evidence-path substitution, and their backend/public evidence paths
exist. The canonical registry and protected UI/build files remain unchanged;
no staged release or UI integration result is claimed.

| Standalone test file | Tests | Result | Seconds |
| --- | ---: | --- | ---: |
| `tests/mod_editor/test_nfl2k5_jukebox_list.py` | 6 | OK | 43.001 |
| `tests/mod_editor/test_nfl2k5_playoff_starters_research.py` | 2 | OK | 7.104 |
| `tests/mod_editor/test_nfl2k5_playbook_pair_unicorn.py` | 20 | OK | 8.592 |
| `tests/mod_editor/test_nfl2k5_helmet_finish.py` | 4 | OK | 82.933 |
| `tests/mod_editor/test_nfl2k5_paired_intent.py` | 5 | OK | 37.996 |
| `tests/mod_editor/test_nfl2k5_playbook_pair.py` | 7 | OK | 12.915 |
| `tests/mod_editor/test_nfl2k5_my_career_mode_audit.py` | 6 | OK | 0.073 |
| `tests/mod_editor/test_nfl2k5_my_career_mode_routes.py` | 7 | OK | 3.530 |
| `tests/mod_editor/test_nfl2k5_screen_timing.py` | 13 | OK | 145.343 |
| `tests/mod_editor/test_nfl2k5_music_metadata.py` | 6 | OK | 16.439 |
| `tests/mod_editor/test_nfl2k5_music_playlist.py` | 15 | OK | 13.075 |
| `tests/mod_editor/test_nfl2k5_music_playlist_contexts.py` | 7 | OK | 10.378 |
| `tests/mod_editor/test_nfl2k5_abilities_unicorn.py` | 12 | OK | 7.893 |
| `tests/mod_editor/test_nfl2k5_calendar_engine_unicorn.py` | 10 | OK | 366.891 |
| `tests/mod_editor/test_nfl2k5_camera_broadcast.py` | 9 | OK | 28.420 |
| `tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | 18 | OK | 12.821 |
| `tests/mod_editor/test_nfl2k5_practice_squad_screen_unicorn.py` | 14 | OK | 6.855 |
| `tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 13 | OK | 340.485 |
| `tests/mod_editor/test_nfl2k5_qb_spy_unicorn.py` | 16 | OK | 6.583 |
| `tests/mod_editor/test_nfl2k5_read_option_runtime.py` | 13 | OK | 46.385 |
| `tests/mod_editor/test_nfl2k5_read_option_unicorn.py` | 6 | OK | 2.778 |
| `tests/mod_editor/test_nfl2k5_scorebar_v3.py` | 9 | OK | 63.346 |
| `tests/mod_editor/test_nfl2k5_screen_hooks_unicorn.py` | 10 | OK | 22.844 |
| `tests/mod_editor/test_nfl2k5_seven_on_seven_v2.py` | 69 | OK | 148.400 |
| `tests/mod_editor/test_nfl2k5_widescreen_polish.py` | 13 | OK | 6.948 |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 115 | OK | 1427.876 |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 388 | OK | 688.815 |
| `tests/mod_editor/test_nfl2k5_throw_tuning.py` | 45 | OK (skipped=1) | 11.559 |
| `tests/mod_editor/test_nfl2k5_guardian_overlay.py` | 6 | OK | 7.464 |
| `tests/mod_editor/test_nfl2k5_guardian_unicorn.py` | 7 | OK | 246.996 |
| `tests/mod_editor/test_nfl2k5_animation_import_retail.py` | 11 | OK | 44.507 |
| `tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py` | 1 | OK | 623.180 |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 127 | OK | 1470.974 |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 29 | OK (skipped=1) | 286.685 |
| `tests/nfl2k5_position_pools_test.py` | 26 | OK | 23.659 |

`python3 packaging/repin.py --apply`: `applied 0 pin update(s)` at final
verification; every pinned writer edit had already been repinned. `git diff
--check` passes. No protected product files or presets were edited. Integration
must still apply WIRING, regenerate the release manifest, run the protected
product checks, and obtain Noah's game witnesses before promoting any runtime
status.

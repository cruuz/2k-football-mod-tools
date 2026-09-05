# Read option / RPO build continuation, 2026-09-05

**EXPERIMENTAL / UNWITNESSED. Data tier only.** Continued the seven uncommitted
product-file edits and draft pack from the interrupted session on
`astra/r61b-read-option-build`, starting at `d0bf583`. Read the complete hub memo
`READ_OPTION_RESEARCH_2026-09-05.md`, including its evidence distinctions and
sections 1 and 3-9. No game boot, emulator, bounded CPU execution, GUI display,
audio, network, push, XBE write, or change to another worktree was performed.
All archive inputs were read only. Offscreen Qt widgets were exercised.

## What was built and verified

**PROVED by bytes and offline tests:**

- `nfl2k5_play_codec.py` accepts legacy `[opcode, operands]` nodes and explicit
  `[opcode, operands, flag_byte]` nodes. Conditional chains serialize every flag.
  The writer uses the donor flags for matching legacy graphs, and constructs
  supported forward forks for new legacy pairs. It never silently linearizes a
  conditional graph. Partial flag specification, malformed/nonfinite operands,
  wrapped condition selectors/coordinates, invalid normal/alternate terminals,
  stale synchronization references and dependency cycles refuse.
- Each supported chain has 1-15 nodes and one forward condition. Condition/cache
  indices are 0-7; alternate destinations are 1-7 and inside the same chain.
  The global pool is 3500 nodes. Capacity is checked cumulatively before writes.
- All five native recipes match all 30 node bytes per play exactly: MIN 24,
  NO 57, NO 66, PHI 175, TEN 144. QB flags remain `10 10 14 12 13`; back flags
  remain `10 14 02 11 03`. Four strong recipes are byte-identical; NO 66 has
  mirrored geometry and its distinct take animation. A decoder mirror alone
  does not change that animation.
- Acceptance covers each native donor's renamed clone (zero appended nodes),
  explicit and legacy reauthoring (30 nodes), mirror, swap of back slots 9/10,
  request serialization, `.2k5book` export/import and recompilation. Unchanged
  reauthored descriptors and assignment nodes are byte-identical to retail;
  new pool pointers/counts necessarily differ when chains are appended. Export
  and import of the same named request produce identical complete resources.
- Friendly slot remapping now includes condition kind 4 and respects operand 5
  for all condition kinds. Opponent slots are not remapped with offensive
  personnel; mode-6 argument 6 remains a source-node index. Pitch targets and
  the selected back move together. Mode-2 follow movement preserves its partner.
- The additional fork/synchronization guard accepts all **9251 retail plays in
  37 books**. A deliberately flattened native option still passes the ported
  retail validator, but the new authoring guard rejects it. This demonstrates
  why ordinary validator success alone is insufficient.
- `PlaybookNode.condition` and `.description` expose condition kind, coordinates,
  actor slot, alternate node, friendly/opponent namespace, argument/cache node,
  human-input enable and path/terminal flags. Designer operand labels distinguish
  the two node indices, preserve flags through edits, and show a branch diamond.
  The unowned inspector table still needs the small display hookup in WIRING.md.
- Create a Play offers `Speed option`, `Zone read (experimental)` and
  `RPO (experimental)` in an EXPERIMENTAL / UNWITNESSED box. It keeps the chosen
  native under-center I alignment/personnel, chooses strong/weak and back 9/10,
  and shows the actual opponent slot and expected defensive formation. RPO also
  chooses eligible receiver 6, 7 or 8. It shows actual node/byte cost, remaining
  cumulative capacity and branch-index limits. No replacement left means Add
  to project is disabled. Options use a separate design batch and inherit
  existing audible groups/menu links.
- The two read presets author both participants together: QB condition at node
  2, normal keep/pass at 3, alternate give at 4; back condition at 1 watches QB
  node 2, follows/releases normally, or takes at 3 and runs at 4. Mesh destination
  is one yard toward the run side and three back; keep destination is four yards
  opposite and three up; back runs two yards toward the run side and five up.
  RPO supplies an actual three-yard slant to its selected receiver, retail first
  read `receiver_slot - 5` with later zeros skipped, a nominal 0.3-second timer,
  and a pass-capable header. Supporting blocks use the native option recipe.
- Schema `nfl2k5_playbook_pack/v3` preserves explicit flags and
  `nfl2k5_option_intent/v1` across pack files, provider rows, actual saved project
  manifests and compiler receipts. Old schemas refuse explicit flags/intent.
  Receipt records identify final play index and intended fixture, with
  `runtime_target_check=false` and `gameplay_witnessed=false`, under the existing
  source/replacement SHA-256 and exact changed-range receipts.
- The shipped pack uses the existing CLI, staging and PLAY writer pipelines.
  The facade's real staging method was tested with an isolated session: eight
  play requests retain intent, with **zero duplicate menu-link requests**.
  Neither pack compilation nor facade staging needs a new XBE or facade flag.

## Shipped SOFTDRINK option pack

`data/playbooks/softdrink_option.2k5book` targets **retail MIN only**, formation 12
`I Jokers`. All indices below are zero based. It replaces existing records; all
other menus referencing those records also see the replacement. Their names
are listed so Noah can test the actual affected calls.

| New play | Replaces | Added nodes | Other affected formations |
| --- | --- | ---: | --- |
| SD MIN24 Speed EXPERIMENTAL | 156 Weak Stretch | 0 | Tight Triple |
| SD NO57 Speed EXPERIMENTAL | 160 50 Y/TE Zones | 0 | none |
| SD NO66 Speed EXPERIMENTAL | 25 Strong Toss | 24 | Tight Triple, Quads, Ace Bunch, I Spread, I Twins |
| SD PHI175 Speed EXPERIMENTAL | 158 90 X Lob Fade | 0 | I Jokers Pair |
| SD TEN144 Speed EXPERIMENTAL | 93 Weak Iso | 0 | I Spread |
| SD Speed Weak EXPERIMENTAL | 159 50 Y/TE Comebacks | 24 | Split Jokers |
| SD Zone Read EXPERIMENTAL | 155 Strong Counter Trap | 10 | I Jokers Pair |
| SD RPO EXPERIMENTAL | 157 90 X Speed Under | 13 | Split Jokers |

The first five calls carry the complete corresponding native assignment recipes
in MIN's existing menu. They are not five copied retail resources. Equal donor
chains are retained in place. The additional weak-speed preset pitches to slot
9; native recipes pitch to 10. Original MIN 24 remains available as a control.
The zone/RPO fixture is MIN formation 28 `4-3`, opponent slots 2 and 6 respectively;
RPO's intended receiver is friendly slot 7. The expected formation/personnel/
package/alignment signature is
`2754cde5a7300586be1c5038a14d0a76260255d0978f1a92e6c79041c6179e54`.

Totals: **46 formations, 266 plays, 2472 -> 2543 nodes**, 71 added nodes / 568 pool
bytes, 426 name-pool bytes budgeted, **807 changed bytes** in a fixed **78768-byte**
resource. No formation, personnel or menu-link bytes change. Source resource
SHA-256: `50673fd09d38f4a17057a4e79a87119ee861456dd4416b94191b1563aa60887e`.
Result SHA-256: `b54805a0f8d2013ff49907a81d41b9ca1ab517a610854ba06a73902d14fd1ccf`.
Rebuilding from the same source is deterministic. Reapplying to the compiled
output refuses its changed fingerprint instead of consuming the pool again.

Automatic cross-book or changed-source retargeting of an option pack refuses.
The interrupted draft regenerated any pack called SOFTDRINK option after only
checking its IDs, silently losing edits. That behavior was removed. Explicitly
call `option_pack(book, body, team)` for the intended intermediate source, then
review its replacements and fixed 4-3 fixture. The generator prefers I Jokers,
can use another compatible native I menu, and avoids any play linked to a gun
menu. It refuses missing 4-3 fixtures or fewer than eight usable replacements.

**PROVED composition:** actual Modern Gun Core -> modern defense -> regenerated
option packs pass for CHI (3267 -> 3462 nodes) and ARZ (3183 -> 3378 nodes), using
I Spread. ARZ remains at the full 270-play cap. Every gun-menu assignment and
defensive script remains byte-identical through the option pass. **Known refusal:**
that gun pack replaces MIN I Jokers, leaving insufficient independent compatible
calls. The two shipped MIN seeds must not be combined as-is. WIRING.md specifies
reservation/re-resolution and source-order requirements; no global guards were
weakened to conceal the conflict.

## HYPOTHESIS and limits

The research memo proves a retail position/velocity-dependent predicate, not a
modern football read. The UI prints: **“The read is position/velocity based; a
dependable modern read needs the later runtime tier.”**

The fixed opponent signature is verified at authoring/import/compile time only.
The game cannot verify it or dynamically find the backside EDGE or apex. Human
input remains enabled on the native speed option; the geometric read experiments
have it disabled. No physical controller-button claim is made. For the read
presets, true means give and false (including some missing-target cases) means
keep or enter pass. There is **no guaranteed default give** for an unavailable
RPO receiver. The ordinary pass continuation can choose another receiver or
scramble. A nominal timer does not establish an exchange or release frame.

Neither an unblocked read defender, a controlled mesh window, modern crash/stay
policy, one-way runtime commitment, late-input handling, route readiness,
penalty behavior, nor coordinated defensive dive/QB/pitch responsibilities has
been witnessed. These remain runtime-tier and play-test work. The first testing
formation is I Jokers; every other affected menu listed above needs its own
alignment/exchange witness. Serialized PLAY bytes do not contain external
fixture intent; preserve the v3 recipe/project metadata when sharing.

Protected Build/Share packaging, target-picker and inspector-table hookups are
specified in WIRING.md. The existing create-only `.2k5mod` loader bug still rejects
an otherwise valid project containing only creations. Saved manifest contents
and recompilation are proved; a full loader round trip remains covered by the
existing defense expected-failure test until its documented two-predicate fix.

## Exact verification

All following files ran **standalone** as
`QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python3 tests/mod_editor/FILE.py`.
The aggregate is **147 tests reported**, with no unexpected failure. One test
and one class are skipped for the missing private uniform catalog; one existing
defense test is an expected failure for the create-only loader issue above.
The new option tests require only the public modules and, for retail cases,
the read-only extraction; they use precise skips when the extraction/Qt is absent.

| FILE | Result |
| --- | --- |
| test_nfl2k5_read_option | 15, OK |
| test_nfl2k5_read_option_qt | 7, OK |
| test_nfl2k5_defense_play | 12, OK |
| test_nfl2k5_defense_play_qt | 4, OK, one existing expected failure |
| test_nfl2k5_screen_timing | 13, OK |
| test_nfl2k5_screen_archive | 7, OK |
| test_nfl2k5_screen_preset_qt | 4, OK |
| test_nfl2k5_formation_play_writer | 8, OK |
| test_nfl2k5_playbook_pack | 37, OK, one private-catalog skip |
| test_nfl2k5_playbook_pack_ui | 13, OK |
| test_nfl2k5_playbook_inspector | 6, OK |
| test_nfl2k5_play_author | 13, OK |
| test_nfl2k5_create_play_wizard_qt | class skipped: private uniform catalog missing |
| test_nfl2k5_play_designer_qt | 4, OK |
| test_nfl2k5_playbook_route_writer | 4, OK |

The Designer and route-writer tests previously lacked standalone import paths.
Those test setups were corrected. Designer now reads the extraction with a closed
archive context rather than opening a persistent cache database outside the worktree.
Initial acceptance-test failures (including name-pool expectations, descriptor
versus inferred extent checks, and MIN's composition conflict) were resolved or
turned into explicit refusal assertions before the final successful run.

The actual CLI also passed all seven stages, including source fingerprint,
budget, ported retail validation and fixed-span dry compilation:

```sh
python3 tools/nfl2k5_playbook_pack.py check data/playbooks/softdrink_option.2k5book \
  --image '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)' --team MIN
```

`git diff --check` passes. Logs are retained in `.scratch/` only. No XBE patch is
introduced, so runtime memory-write/cave-reference composition gates do not apply;
no emulator or Unicorn proof is claimed for this implementation.

## Noah's witness list: all pending

Use video plus trace where available. For each pair, record source/patch identity,
book/play/formation, controller mode, direction/hash, snap frame, QB/HB active
node/callback, branch bits, selected actor, decision-cache value, input request
frame, ball owner, transfer/throw frame, defender position/velocity and outcome.
Start with ten paired snaps per condition; that is not long-run CPU balance proof.

1. **Retail baseline:** MIN 24 (I Jokers), NO 57 (I Twins; Strong I Pro), NO 66
   (I Jokers; Weak I Twins; Weak I Spread), PHI 175 (I Spread; I Jokers Pair),
   TEN 144 (I Jokers; I Jokers Pair; Strong I Jokers). Test both directions and
   hashes, human keep/requested pitch and CPU QB/back. Establish the actual
   Xbox input and earliest/latest accepted frames. Pass requires a controlled
   keep and completed lateral to the intended back, not just a valid diagram.
2. **Interrupted exchange:** early/late/held/repeated input, QB hit at decision,
   back blocked or behind/ahead/outside, sidelines, missed pitch and loose ball.
   Compare ordinary toss and flea flicker controls. Fail duplicate balls, frozen
   exchanges, impossible forward laterals or ownership changes after a keep.
3. **Authoring fidelity:** original versus clone and explicit reauthor; mirror;
   slots 9/10 swapped; pack export/import and saved-project reload after wiring.
   Include the deliberately flattened negative control. Require matching partner,
   flags, callback changes and outcomes. Test all eight installed names and every
   additional affected menu in the replacement table, including MIN 24 control.
4. **Zone read:** fix the selected 4-3 opponent slot 2; manually create crash,
   stay/widen, scrape and late-slant pairs, then let AI control him. Confirm the
   actor is actually the intended backside edge and remains unblocked. Observe
   actual mesh, give/keep outcome and absence of a second decision. Repeat odd/
   even fronts and substitutions only after choosing their explicit new fixture.
5. **RPO:** fix 4-3 opponent slot 6 and receiver 7; compare coverage hold, run fit,
   ambiguous and late commitments. Check receiver eligibility/readiness, actual
   first read and release, unavailable receiver behavior, line movement/penalties,
   and no give after a throw request. Include human takeover, QB styles, motion
   and both directions. Default-give behavior is a future requirement, not a
   guarantee of this geometric scaffold; record failures explicitly.
6. **Defense:** contain, man, zone and blitz versus designed give, designed keep,
   native speed and authored reads. Track dive/QB/pitch responsibility before and
   after commitment, abandoned targets, pursuit timing and coverage leakage.
   A lucky tackle does not establish correct responsibility.
7. **Lifecycle/composition:** audible, no-huddle, next snap/dead ball, turnover,
   injuries/substitutions, custom personnel, controller switching, save/load and
   repeated import. Test with the then-current throw/gun/defense/depth-role/grown-
   section stack after resolving the documented source/menu conflicts. Require
   ordinary passes/runs to remain clean and no state carryover. Add a CPU-versus-
   CPU half for callability and continuity; larger samples assess selection bias.

## Commit delivery

The shared git metadata is read-only: normal `git add` cannot create its index
lock. Per the brief, all working files remain in place and the explicit-path
commit is delivered in `.scratch/r61b-read-option-build.bundle`, on the same
`astra/r61b-read-option-build` branch name in an isolated scratch repository.
The incremental bundle requires base commit `d0bf583d0bc5027c92dd7150aa6c4eed9a74ee70`.
`git bundle verify` checks the delivered bundle. No changes were staged in the
shared index, and no push was attempted. Neither ASTRA_BRIEF.md nor .scratch
contents are part of the commit.

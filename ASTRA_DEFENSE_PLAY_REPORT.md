# ASTRA defense play report

Branch: `astra/r61b-defense-play`. Brief: `ASTRA_BRIEF.md`; research: the two 2026-09-04 defense/Spy memos in the read-only hub. Work used local retail PLAY resources only. No emulator, display, audio, network, XBE mutation or push occurred. **No gameplay was witnessed.**

## Delivered

- Defense in Create a Play and the Play Designer, eleven selectable assignments, native donor/personnel selection, all-slot diagrams, mirror preview, original defensive mirror partners, and synchronized three-column coordinates. Native type/category/package/eligible fingerprints are pinned per book (48 distinct fingerprints across 37 books). Category row index and CPU category code are displayed separately. Changing personnel means choosing an appropriate native donor, not overwriting a shared category.
- Man target/cushion, zone landmark/depth, rush lane/delay, complete retail exchange scripts, and Spy authoring intent. Exchanging scripts replaces the complete paired donor so both friendly partner references survive; geometric opponent selectors are never treated as friendly slots.
- Cover 0, Cover 1, Cover 2 Man/Hard/Soft, Cover 3, four-deep spot quarters, Cover 6 split-field, five-rush replacement Fire 3, and four-rush replacement 3. Tampa MLB deep drop and a separate Double A formation/neutral-start look are explicitly EXPERIMENTAL. These are spot/retail-script recipes; match-quarters and Palms are not advertised.
- `data/playbooks/softdrink_modern_defense.2k5book`: schema v2, SOFTDRINK modern defense, ten core calls, default targets all 32 teams plus GEN/reference. CLI `modern-defense` regenerates against a native book; `check --all-books --retarget` validates all 37. Playbooks has a generate/export/install button. Existing Share/Build pack paths are reused.
- Spy emits a legal same-slot MLB `1B -> 0D` shallow donor at center/four yards (editable only within 3-5). Compiler checks the original descriptor, entire Start, flags and other zone operands, and refuses non-MLB linked menus. UI says exactly: **shallow middle zone; a true spy needs the runtime patch (not yet shipped)**. The versioned per-play `spy_intent` survives `.2k5book` reload and saved project rows; the receipt resolves it to play/slot indices. It is never inferred from PLAY bytes or encoded as a fake opcode/bit.
- Operand guards reject nonfinite/wrapping coordinates, unsupported defensive actions, bad lanes and invalid friendly partners. FS/SS labels and the missing seventeenth rush lane are repaired. Pools are displayed in nodes/bytes, cumulative archive targets are preflighted before the first write, and all affected defensive menus are reparsed and audited.

## PROVED in this worktree

**PROVED:** Every one of the 9,251 original plays passes the existing validator; all 3,332 defensive plays reproduce their descriptors and every defensive node re-encodes exactly. Every resulting play in each of the 37 compiled pack books passes the same validator. This establishes byte/ported-validator correctness, not independent native execution or gameplay quality.

**PROVED:** Each core pack clones 220 nodes / 1,760 node-pool bytes and appends 306 name bytes. The resource remains 78,768 bytes. Team/GEN/reference/WCO books replace ten coverage records with no formation/play-count growth. Editor and PRACTICE append ten calls to their 4-3 menu; their drill records remain unchanged. No category bytes change in any of the 37 books. All stock formation records remain byte-identical in the core pack. Their membership masks, package maps, FF eligibles, and existing menu links stay intact.

**PROVED:** The smallest stock node budget is CHI: 2,739 used, 761 free. Defense leaves 541 free. The actual Modern Gun Core plus defense composition passes for all 32 teams; CHI uses 3,267 nodes, leaving 233. A synthetic insufficient CHI tail refuses before any archive write. New names and cloned formations are separately capacity checked. Replacing a play does not reclaim its old nodes.

**PROVED:** Native front/partial-coverage pairing is preserved. Every permitted audited pair covers all eleven slots, with coverage taking precedence where it drops a front lineman. The intended preview fronts produce counts 6/0, 5/1, 4/2, 4/2, 4/2, 4/3, 4/4, 4/3, 5/3, 4/3 (rushers/deep defenders), respectively. CPU category membership is structural reachability, not a promised selection percentage. Retail validation sets the usable bit on load; donor header/tendency fields are preserved, not invented.

**PROVED category isolation:** **zero category rows are written**. Thus no shared row can change another formation's personnel. Replacing a shared coverage can intentionally change multiple formation menus; all those menus are enumerated below. Entries are `formation index:name [category row / CPU code]`. Codes 13 (base/Bear where linked), 14 (Nickel) and 15 (Dime) are inherited exactly; special utility rows, if present below, retain their own codes. No Goalline/Prevent categories are newly claimed.

| Book | Plays before/after | Nodes after | Affected formation categories |
|---|---:|---:|---|
| ARZ | 270/270 | 2875 | 24:4-3 [9/13]; 25:Nickel [10/14]; 26:Dime [11/15] |
| ATL | 254/254 | 2658 | 22:4-3 [10/13]; 23:Nickel [11/14]; 24:Dime [12/15] |
| BAL | 263/263 | 2716 | 25:3-4 [10/13]; 26:Nickel [11/14]; 27:Dime [12/15] |
| BUF | 270/270 | 2930 | 27:4-3 [10/13]; 28:Nickel [11/14]; 29:Dime [12/15] |
| CAR | 269/269 | 2879 | 28:4-3 [10/13]; 29:Nickel [11/14]; 30:Dime [12/15] |
| CHI | 266/266 | 2959 | 24:4-3 [10/13]; 25:Nickel [11/14]; 26:Dime [12/15] |
| CIN | 270/270 | 2914 | 27:4-3 [10/13]; 28:Nickel [11/14]; 29:Dime [12/15] |
| CLE | 269/269 | 2905 | 27:4-3 [9/13]; 28:Nickel [10/14]; 29:Dime [11/15] |
| DAL | 269/269 | 2894 | 23:4-3 [10/13]; 25:Nickel [11/14]; 26:Dime [12/15] |
| DEN | 263/263 | 2869 | 24:4-3 [10/13]; 25:Nickel [11/14]; 26:Dime [12/15] |
| DET | 255/255 | 2724 | 24:4-3 [9/13]; 25:Nickel [10/14]; 26:Dime [11/15] |
| GB | 264/264 | 2798 | 31:4-3 [10/13]; 32:Nickel [11/14]; 33:Dime [12/15] |
| HOU | 270/270 | 2945 | 23:3-4 [20/13]; 24:Nickel [9/14]; 25:Dime [10/15] |
| IND | 265/265 | 2866 | 28:4-3 [10/13]; 29:Nickel [11/14]; 30:Dime [12/15] |
| JAX | 270/270 | 2827 | 24:4-3 [10/13]; 25:Nickel [11/14]; 26:Dime [12/15] |
| KC | 261/261 | 2938 | 25:4-3 [10/13]; 26:Nickel [11/14]; 27:Dime [12/15] |
| MIA | 259/259 | 2942 | 26:4-3 [11/13]; 27:Nickel [12/14]; 28:Dime [13/15] |
| MIN | 266/266 | 2692 | 28:4-3 [11/13]; 29:Nickel [12/14]; 30:Dime [13/15] |
| NE | 250/250 | 2835 | 25:3-4 [9/13]; 26:Nickel [10/14]; 27:Dime [11/15] |
| NO | 264/264 | 2950 | 24:4-3 [8/13]; 25:Nickel [9/14]; 26:Dime [10/15] |
| NYG | 269/269 | 2829 | 26:4-3 [9/13]; 27:Nickel [10/14]; 28:Dime [11/15] |
| NYJ | 270/270 | 2842 | 23:4-3 [9/13]; 25:Nickel [10/14]; 26:Dime [11/15] |
| OAK | 270/270 | 2837 | 25:4-3 [10/13]; 27:Nickel [11/14]; 28:Dime [12/15] |
| PHI | 267/267 | 2773 | 24:4-3 [10/13]; 25:Nickel [11/14]; 26:Dime [12/15] |
| PIT | 263/263 | 2926 | 24:3-4 [21/13]; 25:Nickel [10/14]; 26:Dime [11/15] |
| SD | 270/270 | 2936 | 24:3-4 [20/13]; 25:Nickel [9/14]; 26:Dime [10/15] |
| SEA | 269/269 | 2852 | 26:4-3 [9/13]; 27:Nickel [10/14]; 28:Dime [11/15] |
| SF | 249/249 | 2623 | 22:4-3 [10/13]; 23:Nickel [11/14]; 24:Dime [12/15] |
| STL | 269/269 | 2925 | 28:4-3 [9/13]; 29:Nickel [10/14]; 30:Dime [11/15] |
| TB | 253/253 | 2615 | 32:4-3 [9/13]; 33:Nickel [10/14]; 34:Dime [11/15] |
| TEN | 264/264 | 2836 | 21:4-3 [10/13]; 22:Nickel [11/14]; 23:Dime [12/15] |
| WAS | 260/260 | 2865 | 25:4-3 [8/13]; 26:Nickel [9/14]; 27:Dime [10/15] |
| GEN | 218/218 | 2371 | 23:4-3 [9/13]; 25:Nickel [10/14]; 26:Dime [11/15] |
| reference | 263/263 | 2605 | 28:4-3 [12/13]; 29:Nickel [13/14]; 30:Dime [14/15] |
| WCO | 232/232 | 2449 | 27:4-3 [9/13]; 29:Nickel [10/14]; 30:Dime [11/15] |
| Editor | 51/61 | 1038 | 1:4-3 [8/13] |
| PRACTICE | 27/37 | 535 | 19:4-3 [8/13] |

## Noah's witness list (all pending)

Start with **ATL Nickel f23 + Base p0**. The pack also changes linked ATL 4-3 f22 and Dime f24 calls; inspect both. Then use BAL Nickel f26 + Base Odd (odd front), HOU/NE/PIT/SD Nickel (the other odd variants), and CLE Nickel f28 (two OLBs). CLE's slot 5 is not MLB, so Spy is deliberately unavailable there; use ATL Nickel slot 5 for the Spy witness. GEN/reference use their Nickel donors. Editor/PRACTICE use 4-3 and retain tutorials.

| ATL play (replacement index) | What Noah should look for |
|---|---|
| SD Zero Man (p32) | Six rushers, five man assignments; no deep help. |
| SD One High Man (p21) | Five rushers, five man assignments and one centered deep safety. |
| SD Two Man (p25) | Four rushers, five man assignments, two deep halves. |
| SD Two Hard (p10) | Two 18-yard halves; hard corners initially near the line. |
| SD Two Soft (p23) | Two 18-yard halves; underneath/soft corner landmarks at eight yards. |
| SD Three Deep (p8) | Four rushers and three deep zones; centered safety plus outside thirds. |
| SD Four Deep Spot (p27) | Four 18-yard deep landmarks. These are spot quarters. |
| SD Six Split Field (p29) | Right half at +12 yards; two left deep zones at -6/-18. Check side on both hashes. |
| SD Fire Replace Three (p26) | Five rushers after merging with Base; DT slot 2 drops and slots 4/6 replace him. |
| SD Replace Three (p35) | Four rushers after merging with Base; DT slot 2 drops and slot 5 replaces him. |

1. Run each call from both field directions and hashes. Check eleven correct players, readable art, depth-chart ordinals, substitutions/injuries, mirrored roles and snap behavior. Test each available stock front paired with the replaced coverage, not only Base.
2. Use verticals/seams, flood/smash, slants/flats, crossing routes, trips, bunch, motion and switch releases. Record which defender owns which receiver. A moving landmark is not proof of modern matching rules.
3. Create **SD Double A EXPERIMENTAL** from ATL Nickel; linebackers 4/5 should show at X -76/+76 cm, depth 91 cm. Check that the neutral starts do not walk them back before the snap. Create **Tampa 2 Drop EXPERIMENTAL**; MLB should start a middle deep drop. Vertical carry/release fidelity remains a hypothesis.
4. Create paired ATL Nickel Cover 3 calls with and without **Spy on MLB slot 5**. Test stationary QB, left/right rollouts, straight-ahead scramble, RB release, crossing receiver, handoff, play action and pass. The fallback still uses ordinary zone receiver pickup/release; no true QB priority or contain fix is claimed. Repeat after audible, mirror, substitution and next snap.
5. Confirm CPU use on early downs, third-and-short/long, red zone and late-game situations; record a CPU-vs-CPU half. Confirm front/coverage selection, no missing assignments, freezes or broken audibles. No test here proves selection frequency.

## HYPOTHESIS and integration limits

The football fidelity, CPU frequencies, behavior of newly combined selectors/masks, Tampa vertical carry and Double A presentation remain **HYPOTHESIS / UNWITNESSED**. The normal Spy zone can still follow receivers; dedicated runtime behavior is deferred as requested. Custom cross-book defense scripts refuse automatic retargeting; the ten built-in presets regenerate with each target's own donors. The wizard preserves native personnel/package choices rather than authoring arbitrary recoded depth pools.

`WIRING.md` identifies two real integration dependencies outside the owned files: the existing create-only `.2k5mod` loader's empty-content bug, and moving defense pack compilation before defensive position recoding in protected `mod_build.py`. The saved project contains intent correctly; create-only project reload has an explicit expected-failure regression until the loader fix is wired. Full builds combining pooled positions and defense require that ordering fix. Release allowlist/closure/capability edits are also handed off there. No runtime dispatcher flag or new XBE status entry is needed.

## Validation commands and results

Commands run from this worktree. New tests bootstrap their own import paths and Qt uses offscreen. Existing read-only suite commands below use `PYTHONPATH=.:tools` where those unchanged files require it.

| Command | Final result |
|---|---|
| `python3 tests/mod_editor/test_nfl2k5_defense_play.py` | 12 passed; 111.309 s. All 37 rebuilt books, 9,251 original plays, all final plays, actual gun/defense composition, native fingerprints, mirrored fields, Spy preservation and refusal paths. |
| `python3 tests/mod_editor/test_nfl2k5_defense_play_qt.py` | 3 passed, 1 expected failure (create-only loader integration); 2.983 s. Offscreen. |
| `python3 tests/mod_editor/test_nfl2k5_playbook_pack.py` | 37 passed; facade class skipped because the private uniform-catalog report is absent. |
| `python3 tests/mod_editor/test_nfl2k5_play_author.py` | 13 passed. Also repaired the test's leaked reader handle. |
| `python3 tests/mod_editor/test_nfl2k5_formation_play_writer.py` | 8 passed. Existing clone/link test now selects a play actually belonging to its donor formation. |
| `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_create_play_wizard_qt.py` | Facade class skipped: private uniform-catalog report absent. New defense wizard tests use the actual compiler with an isolated host and run successfully. |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_playbook_inspector.py` | 4 passed. |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_playbook_pack_ui.py` | 13 passed. |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_play_designer_qt.py` | 4 passed. |
| `QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_playbooks_panel_qt.py` | 7 passed, 1 skipped (relative extracted pack0 fixture absent). |
| `python3 tools/nfl2k5_playbook_pack.py modern-defense --book .scratch/ATL.PLAY --team ATL -o data/playbooks/softdrink_modern_defense.2k5book` | Pack generated; full check green. |
| `python3 tools/nfl2k5_playbook_pack.py check data/playbooks/softdrink_modern_defense.2k5book --image '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)' --all-books --retarget --json .scratch/defense-cli.json` | 37 of 37 books green. |
| `python3 -m py_compile` on the ten changed product modules; `git diff --check` | Passed. |

Private reproduction outputs: `.scratch/defense_evidence.py` / `.json` contain per-book source/replacement SHA-256, exact replacement/donor/front indices, affected categories and changed-byte counts. `.scratch/defense-cli.json` records the full CLI checks. Raw PLAY copies and logs remain only in `.scratch/`; none is committed. Standalone tests independently regenerate their evidence from the extracted retail archive and skip precisely when it is absent.

## Commit delivery

The required explicit-path `git add -- <owned paths>` was attempted and refused because this worktree's Git metadata is mounted read-only (`index.lock`: Read-only file system). Per the brief, the files remain in place and the commit is delivered in `.scratch/r61-defense-play.bundle`, based on this branch's original HEAD. The bundle's temporary Git metadata is inside `.scratch/`; it reads original Git objects through an alternate and never writes the main checkout or its metadata. The commit includes only the 19 explicitly named product/test/pack/report paths. `ASTRA_BRIEF.md` and `.scratch/` are excluded. No push was attempted.

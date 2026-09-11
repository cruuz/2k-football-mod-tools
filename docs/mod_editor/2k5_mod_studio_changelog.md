# 2K5 Mod Studio — Product Changelog

## v1.0 RC90, beta 66

- **Faster startup, disc builds and Add Songs (Smuzz, maumau78 and Mud, 2026-09-10).**
  In response to "the performance since 59 is now more sluggish" and "Why does it take so long to convert the songs?",
  workspaces load when opened, large texture lists create only visible row artwork, and versioned metadata caches
  avoid expanding the same catalogs on every launch. A project plus gameplay build uses one private disc copy,
  validates the plan before preparing textures, and publishes only after its checks pass. Independent uniform
  encodes use a bounded process pool, and PNG/palette conversion copies exact bytes in bulk; equipment keeps its
  existing grouped compile cache. Preparing 40 synthetic uniform edits against the retail source fell from
  123 seconds to 17 seconds. The offscreen window appeared in 0.52 seconds instead of 6.33 seconds. Both build paths show
  elapsed time and copy progress. The dependency-free song encoder keeps the same ADPCM bytes and audible preview
  while avoiding work on candidate states that cannot win; the four-minute synthetic stereo probe fell from
  1,189 seconds to 89 seconds. Disc-byte parity and source preservation are covered by synthetic build tests.
  In-game behavior and Windows responsiveness still require Noah's witness.

## v1.0 RC89, beta 65: accelerated clock, MyCareer supersim and positions, the Windows folder-publish fix (2026-09-10)

- **Fixed: "[WinError 5] Access is denied" while importing a number sheet on Windows (Coach Edwards, 2026-09-10).**
  The digit-sheet import exports a private Team Kit into its own temporary folder and publishes it with one
  `os.rename`. Windows refuses to rename a folder while another process holds a file inside it open, which is exactly
  what real-time antivirus and the search indexer do right after 39 fresh PNGs are written, so on a work laptop the
  import died at the publish step ("Your original game disc was not changed" was true). The publish now retries the
  no-clobber rename over about six seconds of backoff on the two transient Windows refusals and, when the caller
  allows a non-atomic publish, falls back to reserving the destination with an exclusive `mkdir` and copying the
  staged tree into it. An existing destination is still refused at once, nothing is ever overwritten, and the
  Windows branch is exercised on every CI platform by `tests/mod_editor/test_windows_folder_publish_retry.py`.

- **EDGE and LB are the only edge and linebacker choices when the position pools are on (Noah, MyCareer position
  picker, 2026-09-10).** With merged position pools, Create Player and Create MyPlayer cycle through EDGE and LB
  without an OLB entry, in both directions, with no blank row. EDGE has Power, Speed and Balanced templates drawn
  from the game's DE and OLB ratings; roster, draft, scouting, free-agency, contracts, trade-needs and the other
  native selectors skip the retired row; the 3-4 interior depth slots read DT. The seventh "Defensive End" consumer,
  the Create Player long-name table, now says Edge Rusher too. The completed build requires reclassified rosters:
  the old "Keep Outside Linebackers" compatibility profile is retired and an uncertified roster refuses the build.
  `ASTRA_B65_POSITIONS_REPORT.md`; unwitnessed in game.
- **MyCareer uses the game's own templates for linemen, and says what each position can really do.** MyCareer now
  uses the native Create Player templates for offensive and defensive linemen instead of substituting 65s. Its
  position descriptions distinguish proved input handling (every position's controller decode, port restore and
  switch guards were executed natively) from what is still unwitnessed: routes, mesh movement, catches and
  blocking under the stick. No speculative first-person control flag is enabled; Noah's QB play remains the only
  witness.
- **Selected players get a filled white star at their feet.** The existing Rosters star tags now draw a solid
  five-point star with a near-black edge, replacing the hollow outline at the same size and position. Builds
  upgrade recognized beta-58–64 star patches automatically when the star option is enabled. The same 22-player
  bound, HUD/coach/replay visibility rules and ordinary controller circles remain. No new style switch or preset
  change. Native CPU submissions, complete fill, material fields and legacy upgrades are proved offline;
  in-game appearance still needs Noah's witness. `ASTRA_REPORT.md`; preview `nfl2k5_player_star_filled.png`.

- **MyCareer Settings: first person, off-field play and MyPlayer's star.** Open Settings below Upgrades in the
  Apartment. First Person Football defaults Off and uses the same native toggle as Franchise Settings.
  Off-field play offers Spectate or Skip presentation, defaulting to Skip; both sides retain native AI at normal
  speed. MyPlayer star defaults On and changes only MyPlayer's star bit, preserving every other tag and player.
  All three choices now survive save/load, including migration of older careers. B returns from Settings;
  B during an eligible off-field presentation switches to Spectate. Native skips, menu dispatch, masked tags and
  saved choices are proved in bounded execution. Fast forward and a guaranteed pre-snap return remain unproved.
  The existing 16 KiB code and 8 KiB writable owners still fit, with at least 145 code bytes spare in the measured layouts; no other owner moves.
  Built by Astra; experimental, opt-in and unwitnessed. See `ASTRA_REPORT.md` for Noah's witness script.
- **Accelerated clock (Madden style), opt-in.** After a huddled play call, the human or CPU offense's play
  clock jumps to a chosen 25, 20, 15, 10 or 5 seconds. The game clock loses the same time only when its native
  running state permits it. Final-two-minute and no-huddle snaps keep their normal clocks; kickoffs and the
  first snap of a quarter are excluded, and a snap latch prevents repeated runoff after a re-spot. The writer,
  option read-back and bounded native proofs are complete. Build-time controls require the integration in
  `WIRING.md`; no in-game settings row is included. Off in every preset, 20-second minimum when enabled.
  Scorebug rendering, full-game play counts and actual console play remain UNWITNESSED; see `ASTRA_REPORT.md`.

## v1.0 RC88, the 2K8 beta: no 2K5 changes beyond the version and the release tag (2026-09-09)

- Beta 64 is the first All-Pro Football 2K8 beta (APF 2K8 Mod Studio 0.1.0-alpha.85, see
  `apf2k8_mod_studio_changelog.md`). The 2K5 studio is beta 63.1 unchanged: `1.0.0rc88` and release tag `beta-64`
  exist only so the in-app Update button offers the release and reports it correctly. The SOFTDRINK packs are the
  beta 63.1 files. The 2K5 runtime closure now pins the canonical registry at 139 rows (86 NFL 2K5, 52 APF, 1 PS2).

## Beta 63.1 hotfix (2026-09-09)

- **Build no longer refuses the whole disc over one jersey digit (Coach Edwards, #2k5-bugs 2026-09-09).** A Team
  Kit round trip through a colour-managed editor re-saved every digit with tiny per-channel differences, so all 30
  Ravens Away digits imported as "Modified", and the arm digit 1 (whose retail encoding leaves six bytes of slack in
  its 896-byte slot) could not be re-encoded within the 16-colour budget: "Digit artwork cannot fit its 896-byte
  texture slot" ended the build. Two fixes: a live digit within 3 per channel of its export baseline imports as the
  retail digit (torso, sleeves, pants and nameplate keep the exact rule; real edits still import), and a digit that
  cannot fit its slot keeps the RETAIL digit for that slot, records a "kept retail" row in the build receipt, the
  status bar and the "Modded XISO ready" dialog, and the build succeeds. A corrupt payload still fails closed.
  `HOTFIX63_DIGITS_REPORT.md`. Unplayed in game (the disc builds; the retail digit is what the game shows).
- **Build no longer fails with "outer 5: ROST preamble" after the Outside Linebackers scan (jrolling2003, #2k5-bugs
  2026-09-09).** The disc layout was never the problem: the 16-reserves / extra-created-teams arena growth rewrites
  the main roster as version 18, and the merged-positions scan that runs last accepted only version 17, so any image
  with position pools plus reserves/extra teams failed after the full build. The scan now reads version 18 when the
  arena is exactly the writer's grown shape. The refusal also carried "This image is: repacked disc ... Build & Share
  works", which sent the tester to repack a dump that was fine; a build refusal now names the disc only when the
  disc is the reason (a modified or unknown image). `HOTFIX63_REPACKED_SOURCE_REPORT.md`.
- **Franchise Schedule "Apply to this game" works on a real playoff save (BigTimeEmpire, #2k5-bugs 2026-09-08).**
  "Refused: no supported ROST: unsupported ROST version 593952; player college is not a college record": every
  franchise edit, including a kickoff-time change that only writes the season block, ran the strict roster codec
  over the whole save, and one player's college pointer that lands inside the arena but off the college table (the
  game itself never checks it; the player card and the roster page tolerate it) refused the ROST. The "version" was
  the outer wrapper's declared length (0x91020 = 593,952), tried as a header by the scanner. Now: an in-arena
  off-table college pointer is recorded instead of refused, refusals name the player record and offset, the wrapper
  magic is no longer tried as a header, and schedule / year / cap / control edits skip the roster codec (the ROST
  bytes and the injured-reserve table are unchanged by them); arena edits are validated exactly as before.
  `HOTFIX63_FRANCHISE_SCHEDULE_REPORT.md`. Unplayed on the tester's save (not available; four real saves round-trip).
- **Imported shoes (and gloves, elbow pads, sleeves, wristbands) reach the players in a game, not only Edit Player
  (maumau78, #2k5-bugs 2026-09-09).** The player texture binding table at 0x4EEAF8 marks shoe styles 1/2/4/5,
  gloves 1-4, elbow pads 1-4, long sleeves 1-2 and wristbands 1-2 as global rows: the game resolves them by name
  through the newest loaded uniform package, which is the away team's package in a game and the viewed team's own
  package on the Edit Player screen. The studio staged the texture into one package, which only the preview ever
  read. An equipment import now stages every package the game samples (the selected one plus all 317 away and 85
  home Current Uniform packages) as one undoable batch with a receipt naming every copy; shared spans compile once.
  Styles 3/6 were already correct. `HOTFIX63_SHOES_REPORT.md`. Unplayed.
- **Kick and punt returners are no longer scaled by the Interception slider (root cause candidate for "every
  kickoff and punt return is muffed", shanethepain, #2k5-general 2026-09-08).** The catch-slider cave (on in every
  preset since beta 62) classified a catcher whose team differs from the offense as a defender and returned
  rand / (2 x Interception) with no kick discriminator; a returner has that identity before possession changes, so
  Interception 0 failed every kick and punt catch (25 failed half). The cave now reads the ball kind at 0xE602C0
  (3 = kick or backward pass, 4 = forward pass, proved by instruction) and routes kicked balls through the
  catcher's own Catching slider; forward passes are byte-identical to beta 63. Twenty-two bytes in the unused tail
  of the same boot-logo bitmap; both XBE gates and the pairwise matrix green. `HOTFIX63_CATCH_SLIDER_KICKS_REPORT.md`
  and `HOTFIX63_KICKOFF_MUFFS_VERIFY_REPORT.md` (what the kickoff receipts do and do not prove). Unplayed.
- **A raw disc dump builds with every option ticked (Ju3tin, #2k5-general 2026-09-09).** "ValueError: overlapping
  disc file or metadata: root directory": the archive reader's overlap sweep started at partition+0x10800 and so
  assumed every directory sits past the volume descriptor, but a pressed-disc (redump) dump keeps its root directory
  at sector 30 and the `vc_53450030` directory at 31, below the descriptor at 32; the first span was reported as an
  overlap although nothing overlaps. Three lines in `nfl2k5_music_archive.py`; the all-options build from the raw
  dump reproduced the dialog verbatim before and completes after (regression tests on a synthetic raw layout and,
  retail-gated, on the dump). The "please insert disk" that followed is xemu, not the build: xemu 0.8.x boots only
  the game partition and does not accept redump-layout images (its documentation; its redump pull request #2915 was
  closed unmerged), and the studio keeps the source's layout, so the identity line for a raw dump now says so and
  gives the cut (`xdvdfs pack`, or `dd` past the first 0x18300000 bytes). `HOTFIX63_RAWDUMP_OVERLAP_REPORT.md`.
- **Rosters: Check my rosters, a college reference checker and repair (BigTimeEmpire, #2k5-bugs 2026-09-09).**
  "Certain roster and save files can't be edited if a player doesn't have a college or there are errors with their
  college." On 63.1 a blank or None college is accepted everywhere and an in-arena off-table pointer no longer refuses
  a franchise save; what still refuses a roster-save signed copy is a college pointer that leaves the roster arena,
  and a broken college table refuses a load. The Checks tab gains **Check my rosters…**: it scans the loaded document
  (or a chosen save or disc, read-only, even one whose roster did not parse) and lists every player whose college
  reference is null or invalid with the file, pool, record, byte offset, raw word, reason, what the game would show
  and the proposed college; table issues are listed even when unused. **Repair listed college references** points
  those records at a valid college (None by default, or a chosen one) changing only the four bytes of each affected
  player's college pointer, then runs the page's existing ownership and depth checks, installs the result with one
  undo entry, keeps an explicit repair journal in dirty state, carries the repair into Build & Share (as the college
  name, never a raw pointer) and into a saved signed copy, and refuses to guess when the college table itself is
  broken. Core `nfl2k5_college_check.py` (scan + atomic repair for the disc ROST, roster saves and franchise saves;
  retail scan: 0 findings). `HOTFIX63_COLLEGE_CHECK_REPORT.md`, `HOTFIX63_COLLEGE_CHECK_GUI_REPORT.md`. Unplayed;
  the tester's file was not supplied.
- **Music tab on a fresh rip: verified fixed in 63, regression tests added (Mud, #2k5-bugs 2026-09-09 on 62.1).**
  The stadium-music and jukebox paths share the readiness check that beta 63 stopped raising; new tests replay a
  mismatched-digest cache through the real window offscreen. `HOTFIX63_MUSIC_VERIFY_REPORT.md`. No product change.
- **Broadcast camera v5.3: the mount clears the near stands (existing `camera` option; no new switch, no preset
  change).** maumau78 on beta 63: "Broadcast CAM on the last release is fire!" then "only issue is that on right side
  will clip over crowd and stadium structure". Root cause: v5.2 used the retail TV template's press-box eye, 52.5 m
  toward the near sideline and 16.5 m up, and a type-2 mount follows the ball across the field as well as along it.
  Measured on the retail stadium scenes (all 53 models through the Stadium Studio's own glTF derivation), 16.5 m is
  the front-row height of the second level, whose front sits about 58 m from the field's centre line (Superdome
  58.2 m, Arizona 59.7 m): with the ball past the near hash the eye was already among the second-level seats and
  crowd, and in the end zones inside the loge corner trim. The mount moves to the front of the loge, 45 m out and
  14 m up, with the lens widened from 80 to 68: the same pitch (17.3 degrees, was 17.4) and the same framing at the
  ball (every sample point within 10 px of v5.2 through the native solver), 15% closer in perspective. Through the
  solver the eye now stays in front of the second level and below the corner trim for every ball from the far
  sideline to 9 m past the centre line toward the camera (the near hash is 2.8 m, the near numbers begin at 11 m),
  the whole field long including both end zones: 300 sampled ball positions per case, 156 cases, 0 violations (v5.2:
  95 per direction on the same grid). Over the 53 stadium models the frames with structure over the field between the
  numbers fall from 15% to 5% (between the hashes 8% to 2%); plays wider than that still carry a constant-offset
  mount into some stadiums' seats, and the complete fix (the native eye clamp box set by one owned setup callback)
  is described in `WIRING.md` for a later beta. Descriptor differs from the template in type, look-at, lens and the
  mount's x and y; the 80 owned RO bytes, 160 RX wrappers, hooks and requests are unchanged.
  `HOTFIX63_CAMERA_V53_REPORT.md`, proof JSON/PNG regenerated. Unplayed.

## v1.0 RC87, the last 2K5 beta before APF 2K8: read option v5, Franchise Edit Player, CPU fourth downs, weekly preparation, separate playbooks, match coverage, abilities rules v2 with move locks, close pursuit recovery, Broadcast camera, deep-zone tiers, 7-on-7 v2, MyCareer draft and the fresh-rip fix (2026-09-08)

Beta 63 was built by GPT-6 Astra under Claude's review in one wave of fourteen bounded sessions plus the four
correction sessions that followed beta 62's play tests, each landed on the stack by Claude with the protected
wiring (dispatcher, BuildPlan, presets, Gameplay Patches and Build rows, packaging, capability registry and count
pins) done by hand and every union merged three ways. Every executable owner passed the retail byte pins, both
executable safety gates composed with every owner in both installation orders, the pairwise composition matrix and
the reservation manifest regenerated once from the retail executable and disc after the last landing. Nothing in this
section has been played in xemu or on a console unless it says so: Noah's witnesses are listed first and everything
else is unwitnessed. Every new option is labelled experimental and defaults to off or retail in every preset unless
stated, and every entry names its Build option and its presets. This is Noah's ledger for the beta: it covers every
commit on the stack since beta 62, grouped by area, with a commit index at the end.

### Noah's witnesses (2026-09-08, xemu, discs bn and bo, beta 62 stack plus the first beta 63 fixes)

- **Read option v4 diagnostic (disc bo).** After the snap the top left of the screen showed `READ miss 48`, the
  quarterback no longer took off on his own, and there was still no handoff: the RPO played as a play-action pass.
  That single line settled two things. The hooks run on a real play (the diagnostic text is drawn by the patch), and
  the paired lookup was keyed by the wrong number: the authored plays were paired as resource 155 (Zone Read) and
  157 (RPO) while the live lookup produced 48. Read option v5 below is the answer.
- **ESPN 25th Anniversary rosters (disc bn).** The Ice Bowl put a number 14 at quarterback for the Packers instead
  of Bart Starr's 15; Wide Right showed two Cowboys teams; MyCareer menu rows appeared doubled; the RPOs played the
  same as before. The scorebug was solid and the kickoff was fine. The duplicate-Cowboys defect is root-caused and
  repaired below; the number 14 and the loading loop were not reproduced and the in-game option now refuses.
- **The DB circling bug.** Noah asked for it in this beta by name. The close pursuit recovery below is the reproduced
  orbit fixed on native code; his exact man-coverage circle is not confirmed to be the same defect.

### Noah's witnesses (2026-09-08 evening, xemu, disc bp: the beta 63 stack with every gameplay opt-in)

- **Read option v5:** "the zone read experiment sorta works, its not natural and its weird but if i wait long enough
  the qb gives it to the RB although it feels late. but the core is working." On an option play the quarterback rolled
  right with the back behind him and Black pitched. Verdict: good enough for this release as experimental; the give
  timing is the next thing to iron out.
- **The circling defender:** "DB circling appears to be gone, tested a few pass plays and no one circled."
- **Franchise Edit Player:** "changing positions and edit player in franchise work perfect. backs out perfect."
- **Broadcast camera:** "playable now but very very far away, should be far closer" (fixed below as v5.1, unplayed).
- **CPU fourth downs:** not tested; stays experimental. **Abilities rules v2:** "fine for now but don't make that part
  of any patch until we have given the top players stars", so it stays off in every preset.

### Gameplay

- **Read option v5: the paired play is found by the loaded book, not by a menu number (same "Read option mesh
  controls (experimental)" option, `read_option_runtime`, off in every preset, same 2,048 RX / 256 RW / 88 RO
  reservation and two-record table).** Noah's `READ miss 48` was the clue. On disc bo the gameplay loader keeps Zone
  Read at resource 155 and RPO at 157, and 48 is PA Z Slant, so the old number could not have been the selected play.
  Proved by executing the real gameplay loader `0xE0D90`, the native menu accessor `0xE13F0` (zero-based entries 6, 7
  and 10 of bo's I Jokers menu select 155, 157 and 48) and the assignment selector `0x1CEAC0`: none of them turns 155
  into 48. The v4 diagnostic itself was the weak link: its buffer-relative lookup stored its quotient into the
  displayed number before the caller checked the snapping quarterback, so a later lookup for another slot-zero actor
  could overwrite the field with 48 while the recorded quarterback was unchanged. v5 resolves the paired resource from
  the loaded team book's play pointer and fingerprints (`identity_model=loaded_team_book_fingerprints/v5`), refuses
  duplicate live fingerprints when compiling the table, and installs native give, keep, pitch and RPO controls:
  do nothing and the quarterback gives; Xbox Black pulls and pitches; release A after the snap and press A again to
  pull and keep; X or the named receiver pulls and passes on an RPO. Cancellation stays open until the native
  exchange event, including a delayed mesh past one second (the one-second interval Noah saw is the CPU read's
  fallback deadline). v5 waits through native snap reception before starting the give or take; the diagnostic variant
  shows `READ <resource> snap` during that interval and `pend` when the quarterback has the ball. The diagnostic
  defaults CPU reads to give; the normal variant keeps the CPU edge read. The recipe pack is 1.0.2. Old v1 to v4
  executables must be rebuilt from the supported base. 458 tests, both gates, the pairwise matrix. The exact runtime
  state that produced the live 48 is not recoverable from a screenshot and is documented as unproved. Witness list in
  `ASTRA_READ_OPTION_V5_REPORT.md`.
- **Close pursuit recovery, the circling defender (Build: "Close pursuit recovery (experimental)",
  `coverage_trail`; on in Advanced and Experimental after Noah's play test, off in Basic).** In the bounded native pursuit replay a defender at full throttle with a
  capped turn radius is carried past a close opponent again and again because the close-pursuit branch never brakes on
  arrival: he orbits. The owner is one six-byte hook at `0x2FC9F0` (pinned `8b510cd94210`, returning to `0x2FC9F6`)
  into a 520-byte routine in a 640-byte RX reservation, zero RW, zero RO. It removes the reproduced orbit and improves
  stationary arrival in the supplied man fixtures; the crossing fixture shows an early separation cost that the report
  documents rather than hides. A 5,760-frame numerical receipt, native and integrity suites, and a frame fixture on the
  kickoff skeleton harness. Noah played disc bp on 2026-09-08 and saw no circling on several pass plays ("DB circling
  appears to be gone"), so the option is on in Advanced and Experimental; the man-coverage cause is still not proved to
  be the same defect. `ASTRA_DEFENDER_CIRCLING_REPORT.md`.
- **CPU fourth downs and first downs (Build: "CPU fourth downs and first downs (experimental)", `cpu_money_downs`,
  Retail / Modern / Aggressive; retail in every preset).** Retail already reads distance to the marker: the category
  decision `0x20B180` asks the field-goal routine `0x20AF80` and the punt routine `0x209CA0` first, and the punt routine
  is conservative (own half punts, beyond midfield more than a yard commonly punts) with late, score, timeout and
  range exceptions. The patch adds a measured fourth-down policy for CPU offenses only in ordinary phase 4 and
  regulation quarters: own 20 to 40 goes on 1 yard (Aggressive 2), 40 to 60 on 2 (3), 60 to 80 on 3 (5), 80 to 100 on 2
  (3); below the own 20 retail decides; the final 30 seconds of the first half and the final two minutes of a
  one-score fourth quarter stay retail; late leads subtract a yard, late deficits add up to four; overtime and
  anything odd delegates to retail. When the policy accepts, the hook enters the native ordinary-offense category
  generator; when it declines, it replays the displaced instruction. Replays of the real decision instructions: own 50
  and 2 in the second quarter went from punt to offense, opponent 30 and 2 from field goal to offense, own 30 and 7
  stayed a punt, opponent 20 and 2 down three with 100 seconds stayed a field goal. The passing change intercepts the
  play's native score at `0x20980D` on CPU third and fourth downs and multiplies it by 1.5 (Modern) or 2 (Aggressive)
  only when the supported primary route reaches the marker, judged from the loaded PLAY buffers with a conservative
  classifier (explicit first read, one straight leg, at most one terminal break; screens and multi-break routes keep
  retail weights). On the ARI formation-8 sample with 256 seeds the primary reaching a 3-yard marker went from 47% to
  75% (Modern) and 88% (Aggressive), a 12-yard marker from 24% to 51% and 71%. 2,048 RX bytes, 17 hook bytes, no RO
  or RW. Build and Gameplay show a level combo beside the checkbox (checking selects Modern, unchecking returns to
  Retail); an executable with a different installed level refuses. `ASTRA_CPU_MONEY_DOWNS_REPORT.md`, replays in
  `docs/mod_editor/nfl2k5_cpu_money_downs_replays.json`.
- **Separate offensive and defensive playbooks (Build: "Separate offensive and defensive playbooks (experimental)",
  `playbook_pair`, off in every preset).** The expert's dual-playbook ask. Two rows, HOME Defensive playbook and AWAY
  Defensive playbook, join the two pregame Options lists right after the original book rows (which become HOME and AWAY
  Offensive playbook); both human and CPU sides get them; each defaults to Same as offense with the 32 club books,
  Generic and West Coast as alternatives. A pair takes ordinary offense and all special teams from the first book and
  the whole ordinary defense, fronts and coverages included, from the second, building one self-contained live PLAY
  body before the native play-call initialization caches pointers. The choice lasts one game and the first
  non-default selection says so on screen: it is not saved to Franchise, paired sides do not use VIP learning or
  replay, and no profile, save or 38th stock book byte changes. A missing resource, allocation failure or malformed
  graph keeps that side's original book and says which side failed; native User A/User B sources are refused before
  extra loads. 8,192 RX + 512 RW (in an existing alignment gap) + 4,096 RO. Limit: this build refuses the pair together
  with the read option or QB spy controls until those identity lookups support composite roots; the message is plain
  and shown before any output is written. The 2K8-style editor verdict is in the report: 2K5 already has a bounded
  native custom playbook manager (Manage Playbooks, Add Plays, Manage Audibles, Save and Load Playbook on two writable
  User buffers, serializer `0x161A70`, Playbook save type 6, all executed in a bounded proof); what is not proved is
  automatic attachment to every profile, a 38th disc book and independent per-Franchise-team two-book selection, so
  no such editor is advertised. `ASTRA_PLAYBOOK_PAIR_REPORT.md`.
- **Match coverage census and pack (no XBE owner; Build > Playbook packs > "Add match coverage experiments").** All 37
  books, 9,251 plays, 3,332 defensive plays and 91,833 pool nodes decoded and validated: 59 defensive play records carry
  explicit man/zone exchanges across 105 formation menus (Combo Inside Zone 28, Combo Strong Zone 12, Zone Double
  Steal 4, Weak Combo Strong Zone 4, Strong and Weak Bracket 1 3 each, Combo Weak Zone 3, Open Cover 5 1, Inside Zone
  Odd 1); 53 have reciprocal partners and six nonreciprocal ones are left exactly as found. Both man-to-zone and
  zone-to-man vocabulary exist as opposite sides of one native exchange. 105 retail formation diagrams and five
  authored-call diagrams are rendered under `docs/mod_editor/match_coverage` in the repository (the release payload
  carries the census and metadata, not the images) with the census (JSON, CSV, table), the
  native evidence pins, a compiler receipt and a guide; the Rules library gains structural match bundles and the Info
  panel reads the new `match_coverage` section. The optional pack `data/playbooks/softdrink_match_coverage.2k5book`
  adds five experimental calls built from those rules (122 nodes, 976 bytes, no formations; OAK, the reference book and
  TEN select 4-3 when Nickel lacks five free destinations). Full Rip/Liz, quarters-match and Palms receiver keys are
  not implemented and the pack does not claim them. `ASTRA_MATCH_COVERAGE_REPORT.md`.
- **Player abilities rules v2 with the editor locks Noah asked for (Build: "Player abilities rules v2 (experimental)",
  `abilities`, off in every preset; three lock checkboxes on the same option, all on by default).** The abilities
  owner grows to 1,344 RX bytes inside its 1,536-byte budget with one six-byte entry hook at `0x17B010` wrapping the
  common effective-attribute getter. Five bounded live effects attach to the existing permissions during live phase
  14 for tiered players, after native injury, condition, slider arithmetic and both clamps: Juke adds to Agility,
  Stiff-Arm to Strength, Hurdle to Jumping, Truck to Tackle Shed, Spin to Pass Rush, by 0.02 per tier (Star,
  Superstar, X-Factor), capped at 1, never reviving a zero, never writing a rating byte. Tiers are stored in the
  record's two spare bits with limits of 2, 4 and 7 abilities; tier 0 keeps legacy permissions. The locks: right-stick
  moves need the ability, each special move needs its own permission, Speedster is required for speed above 99; both
  move locks off restores the retail charge meter, either one on keeps the restricted charge policy. The Rosters
  Abilities page is new: tier and per-ability checks for the selected player, a reviewed full-league assignment
  (rank within the position scheme by the mean of the key ratings; rank 1 X-Factor, the next third Superstar, the
  rest Star; free agents, templates, historic-only players and prospects untouched), receipts you can save, and every
  transaction on the shared Rosters undo stack; lock settings flow from Rosters to Build and back. CLI:
  `python3 -m mod_editor.core.nfl2k5_abilities_editor --roster <disc> --top-n 10 --output <json>`. Six suggested
  independent abilities are refused in the report because no storage or complete native outcome proof exists in the
  budget. 599 tests. `ASTRA_ABILITIES_V2_REPORT.md`. Caught before release, on this branch only: every real disc
  reports rules v2's model version even at retail, and the Build page's refresh synced the three lock boxes
  through the public setter, which refreshes again: RecursionError on every real disc open, surfaced as the
  "unexpected error" dialog. Found by replaying the field reports through the real window offscreen (the
  synthetic-executable tests never saw it because their inspection reports "foreign"). Now the boxes follow the
  disc only when the rules are actually installed, silently; a retail disc leaves them to the user (before, the
  retail defaults also reverted every untick on the next refresh). Regression test with a retail-shaped inspection.
- **Deep-zone corner tiers (Build: "Deep-zone QB facing (experimental)" and "Press corner bail (experimental)",
  `deep_zone_facing` and `deep_zone_bail`, off in every preset; one owner, 2,048 RX + 256 RW).** The two rows the
  beta-62 audit deferred. Facing keeps CPU deep-zone corners oriented toward the quarterback on a slower directional
  drop until a pass, a run, or their selected receiver gets a yard past them. Press bail gives selected three-deep
  calls a press start within two yards and a directional bail; alone it ends at seven yards. Native target selection
  and player control keep their rules; native frame evidence is in `docs/mod_editor/nfl2k5_deep_zone_native_frames.json`.
  An executable whose installed tiers differ refuses (rebuild from base). The press-bail PLAY authoring staging
  (`deep_zone_bail_calls`) is carried on the plan but not wired in this build; the runtime bail serves already authored
  press calls. `ASTRA_DEEP_ZONE_TIERS_V2_REPORT.md`.
- **Throws to backs: research, no repair.** Astra's native probes execute the target solver `0x2DA8E0`, the launch
  routine `0x1CBDB0` and the ball predictor `0x1CC820` and pin fourteen native entry spans, but none of the four
  reported symptoms (pass behind a moving back, ball off the helmet, no catch attempt, needless dive with lost yards)
  was reproduced through a complete frame, and the moving-route lead is already shared by backs and receivers. No
  option, no preset change, 16 tests and the hold documented in `ASTRA_BACK_THROWS_REPORT.md`.
- **7-on-7 practice v2, released as an opt-in (Build: "7-on-7 practice (experimental)", `seven_on_seven`, off in
  every preset; `SEVEN_ON_SEVEN_RELEASED` is now True).** The beta-58 version parked the linemen on the sideline and
  the huddle stalled because those spots were out of bounds. v2 puts the tackles and guards at the retail I Pro line
  positions with the retail 50 All Go pass sets, keeps the centre's retail snap, gives the defensive line the retail
  4-3 positions with the tutorial idle assignment for three and the retail lane-11 rush for the right end with its
  delay raised to four seconds, and drops the two Power Pocket detours (turn Power Pocket off to test the delayed rush).
  Practice > Scrimmage > Practice Type gains 7-On-7; both teams use the practice book with Trips, Spread and Ace
  passing sets, nine pass plays and six coverages; eleven still appear on each side. The replay is idempotent and the
  book accepts retail, recoded and depth-role sources with identical final bytes. 533 tests. Huddle break and repeated
  snaps still need Noah's play test. `ASTRA_SEVEN_ON_SEVEN_V2_REPORT.md`.

### Franchise

- **Edit Player on Player Contracts (Build: "Franchise Edit Player (experimental)", `franchise_edit_player`; on in
  Advanced and Experimental after Noah's play test, off in Basic; implies the Position row).** X_Ray's ask. Player Contracts is descriptor `0x540650` on the native
  generic table screen; its popup table at `0x521340` has ten 60-byte records with fifteen dwords each (label, action
  id, eligibility and phase predicates). The owner appends Edit Player after Assign Jersey Number for the team you
  coach, keeping all ten existing conditional records and their order, and opens the game's own roster editor on the
  live selected player with the beta-58 Position row after Last Name; Contracts, Front Office and Coach's Desk stay
  beneath it and there is no new exit hook or runtime state, so changes take effect immediately, including on Back.
  704 RO bytes, no code. Native Contracts and Desk return proofs, 411 tests. Noah played it on disc bp on 2026-09-08:
  position changes and Edit Player "work perfect" and backing out to the Desk stays in Franchise (the main-menu return
  he flagged did not happen). `ASTRA_FRANCHISE_EDIT_PLAYER_REPORT.md`.
- **Weekly Preparation (Build: "Fix safety drills (experimental)", "CPU teams prepare too" and "Remember my weekly
  prep"; `weekly_prep`, `weekly_prep_cpu`, `weekly_prep_remember`; off in every preset; unchecking the first clears
  the other two, checking either of them checks the first).** The expert's TE and safety complaint, root-caused: retail
  DB drills test only CB position 4 and exclude FS 5 and SS 6, so safeties never got the DB drill effects; the TE row
  has a valid filter and drill rows matching HB and FB, so the reported TE deficit is not root-caused and no TE bonus
  was invented. The owner (649 bytes in a 1,536-byte RX reservation, zero RW and RO) fixes the safety filter,
  optionally runs the native prep routine for CPU clubs before their games with equal low full-drill time for starters
  and backups followed by two rest days, and optionally keeps a human club's valid activities and reapplies the saved
  plan before games until changed; these are the game's own temporary bonuses, not progression, and no save field is
  added. The native plan reader and writer (`nfl2k5_weekly_prep_save.py`) refuse applied state 2, unknown states, bad
  activities and out-of-pool targets before mutation; the decoded drill and attribute tables are in
  `docs/mod_editor/weekly_preparation.md`. Auto Save's prerequisite validator accepts the wrapped hook. 28 feature tests,
  202 gate tests. `ASTRA_WEEKLY_PREP_REPORT.md`.
- **Franchise 2026 rules stay unavailable.** The remaining blockers are proved on native code: the 2026 ledger is not
  persisted by the save, roster staging ignores elevations, and elevated copies resolve to the wrong permanent player.
  The inspector and self-check are updated and the Gameplay row keeps the disabled "2026 franchise rules (unavailable)"
  caption with the owner's own text. `ASTRA_FRANCHISE_2026_RUNTIME_REPORT.md`.

### Presentation and modes

- **Broadcast camera (existing "Standard, Far and Broadcast cameras (experimental)" option, `camera`, Basic off,
  Advanced on, Experimental on; no new switch).** Camera v5 adds Broadcast after Custom in the game's Camera options
  (engine index 7; First Person 6 stays skipped). It is a following adaptation of a proved retail sideline descriptor:
  the retail TV row mixes descriptor types, inherited eye positions and scripted shots, and exposing those pointers
  verbatim does not initialize a playable view, so the exact coach-mode television sequence is not reproduced and the
  report says so. Standard still starts every game and practice, Far keeps its v4 framing, the choice lasts the session,
  Coach Mode and player control are unchanged in the bounded fixtures, and both MyCareer implementations compose with
  it. Requests grow to 160 RX + 80 RO. 311 tests, both gates, 15 pairs. Noah played it on disc bp: "playable now but very
  very far away, should be far closer", so v5.1 moves the mount in from 57 to 39 yards off the ball at 13.7 yards up,
  narrows the lens from 24 to 30 (about 1.8 times closer on screen) and leads the focus by 13 yards downfield so the
  routes develop toward the open side of the frame; both flats, the backfield and receivers 25 yards deep stay inside
  4:3 in all 156 native projection cases, and a 40-yard post is off the open edge until the camera follows, as on
  television. Noah then played v5.1 on disc bq: "still too far away, make it look like tv from a broadcast from the
  nfl last year" and "it isn't centered, it has the offense at the left and the defense at middle, empty on right"
  (the 13-yard lead). v5.2 is the retail TV director's own wide line-of-scrimmage shot made to follow the ball: the
  template's press-box mount (52.5 m toward the near sideline, 16.5 m up, pitch 17.4 degrees), its wide lens word 80
  (the director's live shots use 120), about 1.85 times closer on screen than v5.1 and 3.3 times closer than v5, the
  look-at 2.5 m ahead of the ball instead of 12 and shifted 4 m toward the near sideline so the near wideout clears
  the scorebug. Through the native solver, 16:9 shows about 17 yards behind the ball to 22 ahead (4:3 about 13 to
  17), the ball within 64 px of centre, the far sideline in the top quarter and the near sideline below the frame;
  the focus, backfield, shotgun QB, both flats, both wideouts and a 15-yard receiver stay inside every aspect and
  above the scorebug in all 156 cases; receivers 25 and 40 yards deep are past the downfield edge until the camera
  follows the ball, as on television. Descriptor now differs from the retail template only in type, look-at and
  lens; the eye is the template's own. `ASTRA_CAMERA_V5_REPORT.md`, refreshed projection evidence (now eleven
  sample players) in `docs/mod_editor`. v5.2 is unplayed.
- **MyCareer mode 5 (existing "MyCareer: create MyPlayer in the game" option, `my_career`, off in every preset).**
  The four owned lists (MyCareer entry, Choose team and Sign, the scrolling 32-club picker, Apartment) use the retail
  navigation renderer with the selected row in yellow; signing puts the created record at depth 1 of its position and
  shifts the former starter to depth 2 with both native rank and side fields and the depth-lock bits set; Apartment
  gains a Start MyPlayer action between MyPlayer and Save; signing, Start MyPlayer, Practice and Play next game share
  the same bounded insertion. Hub art is still blocked. `ASTRA_MYCAREER_MODE_5_REPORT.md`.
- **MyCareer M3: the draft, Senior Bowl preparation and upgrades (existing option, renamed "MyCareer: draft and
  upgrades", `my_career`, off in every preset; the owner grows to 16,384 RX plus a second fixed 4,096-byte state page
  at `0x1505000`, the previously spare last RW page, moving no other owner).** Noah asked for the Senior Bowl and the
  draft inside MyCareer with upgrades. The generic Game Modes entry now prepares a native first draft, creates
  MyPlayer with the existing Create Player templates, places the record in the rookie class and opens Senior Bowl
  preparation (the default seed-1 selection in the Senior Bowl data tier includes MyPlayer; the Senior Bowl game
  itself is still unavailable). Continuing runs the existing draft AI (the generic MyCareer path now installs
  `draft_ai` before allocation to reuse its ratings and needs) and the native pick, signing and cleanup routines; the
  drafted player returns to the same Apartment. An undrafted player uses the existing club selection and native
  free-agent signing. Astra's final native run found a real blockage: native preseason leaves all 32 clubs at 54
  players with nowhere to sign, so an undrafted career now asks for an explicit confirmation to let the chosen club
  make room; after confirmation the pinned native cut routine takes the club to 53 and the signing routines add
  MyPlayer as its 54th, the released player enters the native free-agent list, and cancellation changes no roster.
  The Apartment adds Upgrades and the next fixture's week, date and time: purchases spend the existing 25 XP per
  played appearance at 10 / 15 / 25 / 40 / 60 XP per rating point by threshold, role skills cap at 99, physical and
  general skills at 90, unrelated specialist skills at 75, never lowering a native or template rating; quotes are
  re-validated at confirmation and stale or replayed quotes consume the quote without buying. Save and load reuse the
  existing 128-byte footer. Old 8 KiB MyCareer executables refuse and must be rebuilt from base. 569 tests, both gates,
  the pairwise matrix and a continuous season-to-creation native replay. Witness list in `ASTRA_MYCAREER_DRAFT_REPORT.md`.
- **ESPN 25th Anniversary in the game: the duplicate-Cowboys defect fixed, the option refuses until the rest is
  proved.** `0xC2300` clears the active count at team +0x11C but leaves released player pointers at +0 to +0x100, so
  Practice Squad's reserve count rejects the next `0xC1030` import while `0x20CB30` ignores the failure and publishes
  the last successful Cowboys team for both sides: that is Wide Right's two Cowboys teams, repaired with a 12-byte
  native fix proved on all 25 moments of the bn executable and resources. The Packers number 14 was not reproduced
  (bn's native depth builder and formation picker choose Bart Starr 15 and Don Meredith 17) and the loading loop was
  not located, so the in-game option refuses with a plain Wide Right message before copying anything. The exact
  lineups in the editor are unchanged. `ASTRA_ESPN25_IN_GAME_REPORT.md`.
- **Scorebug entry-stall repair v2 ("Scorebug effects (diagnostic only)", `scorebug_runtime`, off in every preset).**
  The reproduced stall: the runtime binding hook searched every resource collection, could evict an unrelated cached
  texture and then wait on its GPU fence before HUD initialization finished. The three private TXTR and FONT lookups
  now name the resident `GAMEDATA` collection through the native named-collection lookup and the HUD's typed resident
  list; a missing named HUD falls back to the hidden panel and native font instead of borrowing another collection.
  The two native call hooks (`0xFCE56` and `0xFCFA2`) are unchanged. This is a counterexample to the old binding's
  safety, not proof of the testers' freeze. `ASTRA_SCOREBUG_FREEZE_V2_REPORT.md`, trace and validation under
  `docs/scorebug_ingame/freeze_v2`.

### Studio

- **Fresh rips can open Stadium Studio again (also shipped as the beta 62 hotfix).** Two testers with a fresh ISO hit
  "The private NFL 2K5 source cache is not the canonical game cache". `_validate_source_cache` compared the cache
  folder name with the project's own rip digest while `SourceCache` names the folder after the opened disc's digest,
  so any legal dump whose bytes differ from the project rip was refused. It now accepts the opened disc's own digest or
  the canonical one and the message says "does not belong to the opened game disc". Regression test added. The same
  wall stood behind the Music tab: the audio fingerprint and containment stores compared the cache folder name with
  the project rip's digest too (their own comments claimed the folder was named for the canonical identity; it is
  named after the opened disc), so a fresh rip that loaded the private audio inventories was refused with "not the
  canonical cache key". Both stores accept the opened disc's folder now, with regression tests. Behind that wall stood
  a third: the audio preparation read `result.inventory_path` on the exact scan result, which has no such field (the
  containment result does), so the first audio preparation of any fresh cache crashed with AttributeError; the test's
  fake scanners had the wrong shape and hid it. Fixed, with the fakes corrected and a shape test. A real fresh rip
  (the retail image with a container byte changed) was then opened through the Studio, prepared for audio and built
  into the Basic and Advanced presets on this stack before release. A beta 62.1 tester's `errors.log` (five entries)
  then confirmed the Music-tab path exactly: `_music_changed` -> `audio_editing_ready` ->
  `Nfl2k5AudioOriginPreparation.is_ready` -> `store.inventory_path` -> "not the canonical cache key", on every music
  change and on every source load. That probe now answers False for any cache a store refuses instead of raising
  (`prepare()` repeats the validation and reports a refusal as a message), so a readiness check can never again put
  the "unexpected error" dialog on screen. Regression test mirrors the reported stack. Two more testers reported 62.1
  at disc open ("The first operation finished, but its next step could not start: ... not the canonical cache
  key"): the post-open continuation `refresh_loaded_source` resets the audio panel, which asks that same probe.
  The sequence (open, Start SOFTDRINK Basic, Music tab, re-open) was replayed through the real `StudioMainWindow`
  offscreen on a fresh rip with every `QMessageBox` and the crash hook captured: no dialog, no error.
- **Build and Gameplay rows for every new owner**, a level combo for CPU fourth downs, parent and child linking for
  weekly prep, the three abilities lock checkboxes restored from an installed v2 source, a new Rosters Abilities page
  inside a scroll host with the Guardian caps group, and the "Add match coverage experiments" button.
- **The allocator ownership proof matches the manifest builder.** `dormant_union` stopped at beta 62 and never listed
  the camera owner, so the retail-only manifest tests refused with "new pages overlap another manifest owner" on any
  stack with more owners; it now equals the gate union and the builder's request list (51 requests). Capacity pins
  reflect the whole beta 63 union (38,432 RX, 4,096 RW and 3,224 RO bytes free in the documented budget); the
  scale-out stress owner shrinks to 36 KiB so the synthetic union still fills the code pages exactly.
- **Counts.** Capability registry 124 rows, 86 for Xbox NFL 2K5; provider closure 257 pinned modules; release
  allowlist 797 files (the 110 match-coverage diagrams stay in the repository under docs; the release policy forbids media suffixes
  in the payload, and directory entries are forbidden by the packaging test); registry rows refreshed for the read option, abilities runtime, scorebug runtime and franchise 2026 objects.

### Not in this release

- Throws to backs (research only), Franchise 2026 rules enforcement, the exact coach-mode TV camera, full modern
  match coverage (Rip/Liz, quarters, Palms), a persistent 2K8-style in-game playbook editor, press-bail PLAY authoring
  staging, the ESPN 25th Anniversary in-game option, and any played witness of the new owners.

### Commit index (every commit since beta 62, newest first)

Everything below is beta 63; the paragraph each one belongs to is named in plain words. Manifest, release text and the
MyCareer draft commits are listed in the ship record when they land.

- Deep zone: 3d0e5f0 wiring (two options, tier-mismatch refusal, capacity pins); 466dedc facing and press bail tiers.
- Release pins: 247c246 version 1.0.0rc87 and tag beta-63.
- Scorebug and 7-on-7: 7c87033 wiring (help text, 7-on-7 released as an opt-in, idempotent replay key); b00b2e9 7-on-7
  v2 with retail line positions; 87a5e81 scorebug binding scoped to the resident HUD collection.
- Franchise 2026: a17bbef help text from the owner, report, registry row; 16dda1c the remaining runtime blockers proved.
- Read option: 838f67c registry row and pins; ce131da v5 identity and cancelable native handoff.
- Match coverage and abilities: fbcc08b wiring (pack button, seed check, Rosters Abilities page, lock sync, closure
  fix); b65b186 abilities v2 effects, tiers and locks; 1f081df match coverage census, rule bundles and pack.
- Playbooks: b94dab3 wiring (refuses with read option or QB spy, integrated capacity pins); 9bcf7e6 native playbook
  pairing and the editor verdict.
- Weekly preparation: e7071ea wiring (three options, parent and child linking); d419835 safety drills, CPU prep and
  remembered plans.
- CPU downs: 4f19151 wiring (level combo, installed-level refusal); 1b5e124 fourth-down policy and marker preference.
- Edit Player: b3aeb3b wiring (implies Position row); 4e3b9b9 Player Contracts editor.
- Camera: 3c2e1ac wiring (caption, explicit closure imports); aa2abbe Broadcast camera v5.
- Research: 0b8a880 throws to backs, held.
- Studio and allocator: 2df5e1f dormant_union equals the gate union; a67d7f8 fresh-rip cache check (the beta 62 hotfix).
- Circling: be99b32 wiring; bf3b68b close pursuit recovery owner.
- MyCareer M3: f659d81 draft, Senior Bowl preparation and upgrades (plus its wiring commit).
- Beta 62 corrections: ad6d239 ESPN 25 team reuse repair and the refusing option; a009a87 MyCareer mode 5;
  e3e4ec5 read option v4 diagnostic and the bm identity proof.

## v1.0 RC86, the biggest beta yet: kickoff v5 and the paired cameras witnessed, the ESPN scorebar v3 and Scorebar Studio, Franchise Auto Save, MyCareer at any position, ESPN Anniversary rosters, read option with modern controls, widescreen v3, the play rules library, 82 stadiums, roster arena growth, the scaled-out executable space and twenty more experimental owners (2026-09-07)

Beta 62 was built by GPT-6 Astra under Claude's review: one bounded session per feature, three integration sessions on
the stack, then a week of correction sessions driven by Noah's own play tests and the Discord ledger, and a pairwise
composition audit of every executable owner. Every patch passed the retail byte pins, both executable safety gates
composed with every owner in both orders, the reservation manifest (regenerated 24 times on this stack, the last time
alone from the retail executable and disc: 28 extra owners, 10,808 reservations from 125 observed writer calls, 144
pinned source files), a real image build of the experimental preset, a second real build with every opt-in switched on,
the local Windows tester and the full CI loop. Nothing in this section has been played in xemu or on a console unless it
says so: the witnesses are Noah's own and are listed first; everything else is unwitnessed. Every new option is
labelled experimental and defaults to off or retail in every preset unless stated, and every entry names its Build
option and the presets that turn it on. This section covers every commit on the stack since beta 60 that RC85 did not
(the beta-61 squash is RC85's), grouped by area, with a commit index at the end.

### Names

Following Noah's direction to use the modern 2K Sports naming system, the studio and the patched game now say **MyNFL** for Franchise, **MyPlayer** for Create Player, **Play Now** for Quick Game and **MyCareer** for the new mode, which sits on the Game Modes row where First Person Football was. The in-game text change is its own opt-in patch (below). Create a Team keeps its name.

### Noah's witnesses (2026-09-07, xemu, Experimental preset discs)

- **Noah's read option play-through (2026-09-08, xemu, disc bl, the paired build).** On the I Jokers RPO and zone read the quarterback ran forward at the snap whatever the snap button did; no mesh, no handoff, no read window. His words: "it should work like madden 27 or 26". The v3 correction below is the answer; the pairing itself held (the build reported two read plays paired).

- **Noah's MyCareer play-through (2026-09-08, xemu, disc bk).** The route is real: Game Modes, MyCareer, Undrafted free agent, the game's Create Player, Sign, and he was a 49er in a real game as the quarterback: coin toss, the CPU played while his unit was off the field, then he moved, passed and handed off without the camera following the back. What he could not see: the club list and the Apartment drew no rows (he chose a club and a row blind; the first entries were taken), no marker under MyPlayer, no play art or receiver icons for the quarterback, the pre-snap cut to the quarterback sat too high, and after he quit a game the next Play advanced the week instead of keeping the fixture. His verdict: nice start, not shippable yet. Those defects are the mode-4 correction in this beta; see the MyCareer entry.

- **What Noah saw, disc by disc.** MyNFL showed in the game on the first disc, so the modern names were the first beta-62 item seen running. Quitting Free Practice inside Franchise returned to the main menu on that disc; the second correction traced the live route and Noah then witnessed the return to the Coach's Desk, with a traded Mike Vick on the practice roster. Dynamic kickoff (shipped in beta 60) showed three things on the first disc: a touchback awarded on a ball that looked fielded at the 1, a returner frozen sideways from the previous play's animation, and the second return man blocking the kicker deep and running past defenders. After v2 he saw the compressed play art sit inside the play card but the held players still jittered before the kick; after v3 (disc bd) they were perfectly still after the kick and still jittered before it; after v4 (disc bf) the kicking team was still but the receiving team's legs still moved and the blocking was still poor; after v5 (disc bh) he called the kickoff good. One presentation defect carries to the next beta: a kick caught in the end zone was whistled dead with no visible kneel while the colour commentator called the returner off to the races. On disc bd he called the paired cameras perfect, kept the new Standard as the default and Far for the extra pull-back, the kickoff play art sat correctly in the card, and nothing hung on the Experimental preset. His three scorebar screenshots on bd showed the loop-773 bar as a solid base with four defects (quarter clipped to "st", game clock and play clock run together, "Ball on" drawn over the down pill, no team names); the v2 bar on bf was right before the snap and lost its whole middle during the play, and he asked for per-team panel colours; the v3 bar on bh he called good, with one cosmetic item left (the rim is red on the right and silver on the left, and should be all silver or team colours). Franchise Auto Save ran on bf: after one manual save and the switch set On, the game saved on his return to the Coach's Desk after a game. He saw the blank Outside Linebackers group in Team Rosters on the merged-position disc; the OLB fix below removes it and is itself unwitnessed. A disc with every opt-in switched on at once hangs at the SEGA screen while the preset alone boots; the opt-in responsible is being bisected, and two Discord testers describe what looks like the same hang (the crowd loads, the audio loops, back to the Berman intro), which the batch-2 verdicts below rank for that bisect. Everything not named in this paragraph is unwitnessed.

### Gameplay

- **Read option and RPO with modern controls (Build: "Read option mesh controls (experimental)", `read_option_runtime`, off in every preset).** This is the feature Noah asked for by name: hold the snap button to keep, let go in time to hand off, read the edge rusher. The runtime owner (`nfl2k5_read_option_runtime`, 2,048 code bytes, 256 writable, 88 read-only) hooks five pinned retail instructions: the conditional-branch update at `0x1AF191`, the HUD draw at `0x646A1`, the pass initializer at `0x19C849`, the snap at `0xB6FBD` and the new-play reset at `0x1AD9C3`. On an authored Zone read or RPO the human quarterback sees a read cue, the runtime picks the unblocked replacement EDGE at the snap from the eleven assignment records, opens a read window counted in simulation updates, and the give/keep decision follows the button: release in the window to give, hold to keep. The CPU makes the same read from the edge defender's position and velocity with hysteresis so it does not flicker. On RPO plays a receiver press during the mesh is carried into the native pass initializer; that is entry into the retail pass continuation after its readiness check, not a guaranteed instant throw, so it is not advertised as a finished three-way mesh. Reads are paired with the play through a small immutable table (at most two records) compiled from the pack's exact play bytes and compiler receipts, so a hand-edited resource without its receipt stays a plain option. The first core (960 code bytes) shipped in wave B and was grown to this v2 the same day; an executable holding v1 must be rebuilt from its base. The read-option runtime and the screen timing hooks used to refuse each other's detour at the shared pass initializer; each guard now validates ownership first and dependencies second. A Shotgun Zone read and RPO authoring helper produce Noah's requested witness plays. Unwitnessed.

- **The read option and QB spy now pair with the final playbooks (no new option).** Noah asked for the read option on a test disc and the build refused: the pack writer collected each authored play with its compiler report, then the merged-position recode and the depth-roles pass rewrote every book (12 bytes of depth roles and 22 bytes of pooled defensive personnel in the shipped MIN book), and the final check refused the stale pair. A new resolver (`nfl2k5_play_intents`) runs after the last book writer: it finds each retained play in the final book by slot and name, recompiles the report from the final bytes through the real compiler (a personnel view built from the retained native codes, accepted only when the pool and role writers reproduce the whole final resource exactly), and refuses with the team, play and changed slot when the eleven assignment descriptors or any node chain differ. On the retail image every descriptor and node of `SD Zone Read EXPERIMENTAL` and `SD RPO EXPERIMENTAL` (MIN, I Jokers, plays 155 and 157; the Shotgun recipes are Gun: Doubles Right, `SD Gun Zone Read` and `SD Gun RPO Slant`) is equal before and after the passes, so both tables compile from the final book: 8 plays, 1 book, 2 reads. The Build summary now says how many reads and spies paired. Runtime bytes, hooks and hashes are unchanged; both flags stay off in every preset. Built by Astra; the first full disc with the pairing is Noah's disc bl. Unwitnessed.

- **Read option v3: a real mesh (same `read_option_runtime` option).** Noah played the paired build and the quarterback ran forward at the snap whatever the snap button did: no mesh, no handoff. Root cause on native code: the paired records did engage, but v2's read hook sat after the native movement call inside the condition callback (the first sample arrived with the throttle already at 1.0), and the per-frame dispatcher let human stick priority win before the task callback, so nothing ever held the quarterback. v3 moves the tick hook ahead of the movement call and adds one six-byte hook at the dispatcher so the paired, live, ball-owning quarterback condition reaches its task first; while the read is pending the quarterback's throttle and command are cleared and only distinct game-clock samples read input, against a one-second deadline instead of an update count. Controls: hold the snap button through the window to keep (the quarterback pulls and you have him on the stick); release during the window, a quick tap, or no input hands off (a real native exchange, the back becomes the carrier, the quarterback carries out the fake); the left stick cannot cancel the mesh; on the RPO, hold snap and press the named receiver during the window to throw through the native pass path. The back is re-authored to wait half a yard beside the quarterback; the read cue now sits on the actual unblocked EDGE's native world marker instead of a fixed screen spot; CPU quarterbacks read the same way. The option pack is version 1.0.1 (same eight plays, two reads). Reservation unchanged (2,048 code, 256 writable, 88 read-only). Full-frame proofs for early release, in-window release, hold-through, no input and the RPO throw. Built by Astra; unwitnessed (Noah's disc bm).

- **Dynamic kickoff v2 and v3: the hold, close blocks, fitted play art, and the held-player freeze (existing "Dynamic kickoff" option, `dynamic_kickoff`, Experimental preset on, Basic and Advanced off; the same code moves with "Kickoff in extra space").** Noah's four observations from the first disc were each traced. A: the touchback classifier reads the actual ball and contact position in the kicking direction, the goal line is 4,572 cm and the receiving 1 is inside the landing zone, so no one-yard boundary error exists; an in-field eligibility guard was added anyway so a ball fielded in the field of play can never score a touchback. B: the previous owner returned from planning and animation sampling with a stale heading, so a player could sit sideways in the pose from the last play; v2 holds every coverage and setup player in a fixed native idle frame with zero speed and a normal opposing-team heading, and the kicker and both deep returners stay free. C: all 36 normal-return books shared blocking chains with 21 to 30 yard rush legs before any block, so the front men ran past everybody and the second returner took the kicker deep; released return blockers now select the nearest approaching coverage player as a local assignment, and the return-blocking writer runs in Build as its own step right after the alignment writer, with its own availability, inspection, patch text and caption. D: the on-field play art renderer draws in world space and is already widened by widescreen v3, so no further x correction was justified; instead the dynamic kickoff formation is compressed into the play-call card. After Noah still saw jitter before the kick, v3 replayed sixty complete native frames and found three writers outside the sampler that v2 had not covered: residual collision separation decaying into the transform, fresh pair-resolution impulses added directly at `1D8940`, and an integer turn spring integrated with the full frame delta even at zero animation time. The sixteenth hook stops fresh collision displacement at its producer for held players and clears the residual collision and spring state before the native late passes; all nineteen held roles then keep exactly the same watched bytes through sixty frames in both directions and both code placements, and first ground or player contact releases them on the next frame. The cave gate learned that the kickoff v2 hooks are also declared by the relocated variant of the same feature, and the shared allocator projection pins the separation hook only when a kickoff owner is installed. 1,939 code bytes, 10 state bytes, no new option or allocation. Witnessed on disc bd: still after the kick, still jittering before it, which v4 answers.

- **Dynamic kickoff v4: the hold starts when each player finishes his own lineup.** The proof v3 never made: the global play state stays 12 while each player's own state goes from 12 to 13 as he completes his lineup, and the global state only becomes 13 after both teams are accepted as ready. v3 armed its hold on the global state, so every player who had finished lining up was free to fidget while the other team was still arriving. v4 holds each of the nineteen coverage and setup players as soon as his own state reaches 13, preserves native team readiness through a new ready query after fixed idle replaces the ready animation, and adds a head-pose guard that samples the fixed clip instead of interpolating a late head-look request. The kicker and both deep returners stay free, first contact still releases everyone, the play art is untouched. Two more pinned instruction spans (ready at `1FF940`, head pose at `1DF430`), eighteen hooks, 1,935 of the 1,939 reserved bytes, still 10 state bytes, no new option or allocation. A full-frame replay from state 12 through the CPU delay, launch and first contact holds every eligible player in both directions. Witnessed on disc bf: the kicking team was still, the receiving team's legs still moved.

- **Dynamic kickoff v5: the receiving team's legs, and blocks that take the nearest coverage man.** The v4 fixture had left the game's locomotion callback as a stub. With the real callback installed, the hold's per-update stance call turned out to restart a locomotion lifecycle whose initializer swaps a completed player back to the ready path, and only the receiving side runs the ready stance's foot sampler, so the nine setup blockers shuffled while everyone else stood still. v5 keeps a completed player's selected stance without restarting that lifecycle. Blocking: the earlier target selector only ran after first contact, but the game can start a blocker's drive task before that with the kicker cached as the target, and the no-target fallback also chased the kicker, so setup blockers and the second deep man ran past coverage men toward the kicker. v5 adds one pinned six-byte hook at the drive callback that refreshes the nearest lane-weighted coverage target before pursuit and waits with zero throttle when nobody is there. A complete return replay runs all 27 native phases each frame with the nine setup blockers and the alternate deep man on real drive tasks. Nineteen hooks, 1,937 of 1,939 reserved bytes, 10 state bytes, no new allocation, all v2, v3 and v4 proofs kept. Witnessed on disc bh: Noah called the kickoff good, both teams still before the kick and the blocking accepted. Open for the next beta: on a kick caught in the end zone the returner did not kneel visually while commentary called him off to the races.

- **Dynamic kickoff v6: the returner kneels on an end-zone catch and the booth stays quiet (existing `dynamic_kickoff`).** Noah's last note on disc bh: the returner caught the kick in the end zone, the whistle blew and he jogged off without a knee while the colour man called him off to the races. Replayed on native code: v5's returner wrapper classified the held ball in the end zone and requested the finish itself on the catch frame, before the native post-catch selector's kneel task (`2EE090`, action 99, the two embedded 23-bone kneel clips) could run, so no kneel clip and no kneel event ever executed; and the per-frame catch producer that feeds the commentary ring kept running for a ball that never entered the field. v6 lets the native kneel task run to its own timed touchback event (1.008 s, native events 0x3A and 0x5B, then the state transition) and adds one pinned six-byte hook at the commentary producer that defers the catch and clear-lane lines while the ball is still in the receiving end zone under possession; the native next-play reset clears the pending contact. A fielded ball returned from the 3, a grounded kick in the end zone (touchback by rule at the contact callback) and a ball fielded at the 1 (never a touchback) replay unchanged. Twenty hooks, all 1,939 reserved bytes, the same 10 state bytes, no new option or allocation. Built by Astra; unwitnessed (Noah's three situations are the witness list).

- **Momentum collisions (Build: "Weight and speed in contact (experimental)", `momentum_collisions` and `momentum_collision_level`, off in every preset).** The beta-61 Momentum owner gains a bounded mass-times-approach-velocity term in the carrier's two native Break Tackle reads. Both horizontal velocities are read at the first call, weights decode as byte + 150 pounds like the native contact code, and the bonus is `0.06 * level/100 * clamp(p / (220 * v_ref), 0, 1)` added to the existing run-up bonus and capped at 0.08 before the native attribute is clamped to 1. A stationary, retreating or perpendicular carrier gets nothing; shoulder charges, jukes, dives and locked tackles fall back to retail; nothing adds impulses, conserves energy, changes animation or forces the Truck ability. The research memo's general collision solver stays deferred. Unwitnessed.

- **Defensive two-point try: the box-score row and saved stats (existing "Defensive two-point returns (experimental)", `defensive_try`, off in every preset).** Beta 61's owner scored the return but only tallied it in a diagnostic. It now writes the native defensive-conversion box-score row, the player-card season column, the saved season and career category used by completed franchise games, player points (twice the defensive count) and the event-banner strings, and repairs the offensive failed-attempt accounting when the defense scores. Stat ID `0x4000` is intercepted only in the native player and team readers at `0xCB240` and `0xCB2D0`; the owner's 1,040 writable bytes hold 256 player counts and 128 replacement drive records so a replayed drive removes its earlier credit, reassigning the scorer moves it, and reusing a ring slot no longer loses older totals (a 130-drive fixture proves 65 credits per team through the wrap). Field 59 of the saved stream is proved unused by all 183 native descriptors. Unwitnessed.

- **Screen pass timing hooks (Build: "Screen pass timing hooks (second experiment)", `screen_hooks`, off in every preset).** A second, independent screen experiment on top of beta 61's data tiers A to D: two scoped hooks (640 code bytes). At the block-completion check `0x23ECD2`, a current, non-terminal, expired finite screen hold in phase 14 keeps the native task active while the snap clock is below 0.8 s; at the pass-timer store `0x19C7E9`, a screen with an encoded default delay stores 0.6 s while every explicit PLAY delay survives. The guard never shortens a positive hold, forces a release, picks a defender or weakens coverage. The 0.8 and 0.6 come from the memo, not live calibration. Unwitnessed.

- **QB spy from man and rush assignments (existing "QB spy for zone, man and rush (experimental)", `qb_spy`, off in every preset).** Wave A's dedicated zone spy (five live detours, a four-yard shadow of the quarterback's predicted lateral position, pursuit latched on a forward or wide escape, an authored lookup of up to 31 records) now also enters from man and rush assignments sharing the same decision, snap identity and sealed table; native man and rush callbacks and their fallback targets stay valid. The paired intent table is compiled from the playbook pack writer's own resource and report pairs (the collector moved to the third playbook-pack call), and the command spies only when nothing is authored. The owner grows from 1,536 to 2,048 code bytes (768 writable, 512 read-only unchanged), so an executable holding the old set must be rebuilt from its base. Unwitnessed.

- **Deep-zone corner tiers: audited, not built.** Noah's list had two more tiers for corners in deep zones: keep eyes on the quarterback until the pass, and a press-corner bail. The controlling memo certifies only the initial-drop cap that shipped in beta 61 ("Initial deep-zone corner drop (experimental)", `zone_drop_cap`), calls sustained facing a later hypothesis needing event identity and hysteresis, and never proved a bail command or animation. Astra therefore built a read-only audit (`python3 -m mod_editor.core.nfl2k5_zone_facing --xbe`) that verifies the zone-drop, spy, coverage and catch owners and their native facing knots, plus bounded Unicorn proofs of the retail reaction routine, and added no patch. Both gates call the audit.

- **Player abilities rules v1 (Build: "Player abilities (experimental)", `abilities` with an optional off week 1 to 18, off in every preset), from wave A.** The seven roster flags at record +0x52 and +0x53 finally do something: Speedster permits movement speed above 99, each special move needs its stored permission, right-stick moves also need Right-Stick Moves, and the special-move charge meter works only for live ball carriers with an allowed move, CPU included. Zero-flag players lose the five special moves under this opt-in contract, so assign abilities in Rosters first; cosmetic stars grant nothing. An optional existing regular-season week turns the rules off for that week. Seven retail hook spans, disjoint from Momentum and the legacy ramp; every permutation of the three is byte-identical. Unwitnessed.

- **Gameplay levers (batch 1): Coverage slider, scramble acceleration, flatter deep flight, Chop Block ("Coverage slider response", "Slow-QB acceleration", "Flatter deep flight", "Repair Chop Block toggle", all experimental, `coverage_slider`, `scramble_tuning`, `flatter_deep_ball`, `chop_block_toggle`, off in every preset).** The Coverage slider is remapped directly through two pinned operand repoints (16 owned bytes); a native acceleration-curve selector helps slow quarterbacks as ball carriers (160 owned bytes, one pinned call); a flatter deep-flight speed table joins the Throw Distance & Arc panel as an exclusive choice with an 80-yard starting setting, the per-arm table and a grey/blue flight-curve preview that now also reads the relocated high-arc table when that mode is selected. The Chop Block repair gets a plain interface over the retail dead toggle. The 2026 team names ("2026 team names", `team_names_2026`, off in every preset) landed in the same batch. Unwitnessed.

- **Community gameplay reports, batch 2: verdicts, not patches.** Astra worked the gameplay side of the Discord ledger to a verdict each, with the witness that would close it, and changed no owner bytes: (B13) Smuzz's screen-edge artifact: widescreen v3 already fixed every proven projection consumer; what remains could be a far-sky seam, a render-to-texture camera or an unaudited effect quad, and a fixed screen edge belongs to the HUD layout while a line that follows the field belongs to assignment geometry, so no blanket widescreen patch is justified; compare retail 4:3, v3 alone and v3 plus one Hi-res family in the same scene with play art on and off. (B19) "blocking breaks with mods, hurry-up does not block": the abilities runtime's carrier-only charge policy (which clears non-carrier meters and denies nine unclassified direct consumers) is the strongest general-blocking suspect, Momentum changes ordinary locomotion for everyone, the screen timing hooks touch only the screen grammar, and no hurry-up defect is proved; test one owner per disc with the same play, huddle then hurry-up. (B20) Atomic's slower disc: the receipts put numbers on every growth (the grown executable is +352,256 bytes; the three-asset Hi-res pilot +536,448 video bytes; the six families +4,146,176 bytes in the modelled scene; a 200-track library up to 1.3 GB of streamed audio; the runtime scorebug 1,419,264 bytes of resident heap), Hi-res and the runtime scorebug are the real candidates, a bigger XISO is not loaded into RAM, and only paired frame-time measurements with the counter visible can justify a performance note. (B5) BigTimeEmpire's dynamic-looking play card with a traditional kickoff: the card is a preview and the Basic and Advanced presets leave dynamic kickoff off; the alignment writer repositions the existing Kickoff and Kick Return formations rather than adding a named one, so check the executable and book receipts together. (B6) muffs and blockers running past threats: the A to D, v2 and v3 corrections address alignment, the hold and return assignments; none is a catch or muff-rate change, and the returner fix only corrects who the CPU puts back there, so punts and catch rates need their own controlled comparison. (B8) the Berman loop against Noah's SEGA hang: the pinned native startup order (heap, then the roster arena allocation, then the legal page and SEGA logo, then the global, director and roster archives, then the frontend) ranks the opt-ins for the bisect: roster arena growth first (it allocates before the legal page), then the Crib movie cut, the Guardian overlay's grown global archive, the music banks and shuffle, and the Practice Squad screen; looping crowd audio does not identify the music owner, and the two native wait loops the scorebug fix report proved can both freeze with audio alive. The FAQ answers are in `docs/mod_editor/discord_bugs_2_faq.md`.

### Franchise, MyNFL and MyCareer

- **Franchise Practice returns to the Coach's Desk (existing "Free Practice inside Franchise", `franchise_practice`, Advanced and Experimental on). Witnessed.** Noah's bug: quitting practice in Franchise dropped to the main menu. The first correction never ran: it had mistaken a following event record for the settings screen's START handler. Retail's Scrimmage Settings START at `0x148B50` is a restart of an already loaded game (two pops, jump to `0x64B10`), which the beta-58 launcher had copied with one pop and the Coach's Desk underneath; the START stub now pops the settings screen once and pushes the retail game screen through the normal scene loader, so Quit finds a game screen to tear down. Noah still saw the main-menu exit on the first disc, so the second pass traced the live route and found the Coach's Desk discarded at Team Select launch (the launch arm unwinds to a fixed Main Menu target); a guarded 5-byte hook in that arm keeps the Desk only for the exact Franchise Practice stack, within the same 352-byte cave at `0x1D82D0` (the three stubs occupy 107 bytes of it), and the pause-menu Quit path was executed end to end under Unicorn through the Desk's row rebuild. No new allocation, flag or save field. Noah then quit a Franchise practice rep and landed on the Coach's Desk.

- **Franchise Auto Save (Build and Gameplay Patches: "Franchise Auto Save (experimental)", `franchise_autosave`, Advanced and Experimental on, Basic off). Witnessed.** Noah's ask: an optional auto save after each game, in the setting slot First Person Football used to occupy. The owner replaces the First Person Football rows in Franchise setup and in Coach's Desk, Options, Franchise Options with an Auto Save switch that keeps the native Off and On choices, the row size, order and count; both rows address one owned switch, and Generic Game Options was left alone because its nine rows have no proved spare. The installed switch starts Off. A successful manual Save Franchise or Load Franchise establishes the device and the full save name, so a new franchise needs one manual save. When a played or simulated game completes and the Coach's Desk is back on top for two quiet updates, the owner enumerates the storage again, finds that exact device, name and Franchise type, and calls the native Save action. It never keeps a stale menu ordinal, invents a name, selects an unrelated file or picks the first device; if the destination is unknown or gone, the game's own notice explains that a manual save is needed. Several simulated results before one return to the Desk produce one save of the latest state, there is one attempt per pending result with no repeated failure popup, overwrite and success confirmations are suppressed only for an automatic attempt, and Off clears pending work. The setting is restored from the original First Person Football word of a native franchise save, so saves keep their size, signing and container. The owner takes 1,536 code, 128 data and 512 read-only bytes from the allocator (the complete union grew to 49,943 code bytes) and rides the final grown pass with the other owners; its bounded x86 tests execute the native completion, Desk dispatch, manual save routing, progress and failure selection and settings reload with storage and drawing substituted. The historical kickoff v3 receipt is pinned to the allocator union of its own time so a new owner joining the union no longer moves the bytes it compares. Noah witnessed it on disc bf: after one manual save and the switch set On, the game saved on his return to the Coach's Desk. Long sessions and a lost destination remain untested.

- **The empty Outside Linebackers group is gone from the roster screens (Build: "Merge positions and remove the empty OLB group", `position_pools`, Advanced and Experimental on; new dependent switch "Keep Outside Linebackers for existing saves", `position_pools_keep_olb`, off in every preset).** Noah saw a blank Outside Linebackers group in Team Rosters on the merged-position disc. Beta 58's one-pool merge had left the retired OLB row alive under its retail name because dropping a record from the fifteen abutting position-filter arrays looked unsafe. The fix session corrected the model first: the arrays the earlier note pointed at were page name fields; the real selector is a NULL-terminated table of four-byte page pointers per screen, sixteen of them for fifteen screen families, and the Pro Bowl order patch already moves pointers in the same tables. Removing the row means dropping one pointer and shifting the rest four bytes, with the page descriptors, columns and callbacks untouched. The build now runs an early pass that keeps every row, then, after the last roster writer, scans every roster on the disc; only a complete scan proving no outside linebacker remains removes the row, any player still carrying the OLB position keeps his group, and the final pass runs only when the build selected the pools or the copied executable already reads as pooled (an executable that cannot be read keeps its rows). If you will load an older or custom save, tick the keep switch. Fullbacks and every other group are unchanged. Both gates, sixteen pinned table edits, a Gameplay Patches row, the position-pool status in every status dictionary and in inspection, registry row 112. Unwitnessed.

- **Native Practice Squad screen (Build: "Practice Squad screen (experimental)", `practice_squad_screen`, off in every preset), from wave A.** A real Coach's Desk destination for the practice squad: the desk table keeps its phase Schedule rows, Practice, then Practice Squad, Front Office, Gameplan, ESPN.com, Features, Options and Quit, replacing the Crib row (the main-menu Crib and Trophy Room route are untouched). The screen clones the Team Rosters descriptor, frame, sheet and All Positions page into Active and Reserves pages driven by the beta-60 transaction code. Enabling it selects practice squads, Free Practice and the allocator. Only the four-byte desk table pointer changes in a retail section. The roster arena owner installs its prerequisites only while they are still retail, because this screen replaces the Coach's Desk table. Unwitnessed.

- **Roster arena growth: 16 reserves and two more created teams (Build: "16 reserves (experimental)" and "Two extra created teams (experimental)", `reserves_16` and `created_teams_extra`, off in every preset).** The ROST arena grows from `0x91000` to `0x92000` (save ROST version 1, disc ROST version 18, a full franchise save of 724,140 bytes instead of 720,044) with five persisted 16-bit primary-player indices per NFL team, so ordinary migrated squads carry 16 reserves and a team with the eligibility bit 17, while active players stay bounded by 65 in the off-season and 53 in season (70 combined). Two optional created-team records take ordinals 52 and 53 (IDs 100 and 101). The team stride stays 500 bytes and the 65-pointer prefix stays put; the owner is 8,192 code bytes with no new writable page, and the native reserve consumers and the Practice Squad screen read the overflow. Unmigrated saves, non-NFL teams and a created-teams-only migration keep the 12-reserve format; the migration is an explicit signed-copy step on the Rosters page, and no team receives a seventeenth reserve on its own. The storage-growth research (below) explains why the pointer prefix was not widened in place. Unwitnessed. **Boot witness (2026-09-08):** a disc with the seven content opt-ins hung at the SEGA logo on 9/7; Noah then booted the Crib reclaim alone and the Practice Squad screen alone (both boot), and the arena growth alone hung at the SEGA logo. The arena growth is therefore the hang and stays off in every preset and off the test discs; the next beta bisects the 16-reserve overflow from the two created-team records. Its offline proofs stand.

- **Franchise playoff editor fixes (BigTimeEmpire's report).** Editing playoff games before the Super Bowl showed only some of the listed games and sometimes refused the date or kickoff. Two causes: the schedule codec's `set_game` ended every edit with an unconditional home-not-equal-away check, which refused the 14-team builder's placeholder games, and the view did not recognise the shipped 17 and 18 week layouts. The Franchise schedule now lists every existing postseason game with its round, opens on **All postseason** for postseason and completed saves, edits dates and kickoff times before participants qualify (they show **To be decided**), keeps each item's physical row and slot through filtering, undo and redo, and says **This game has been played** with the existing override instead of silently refusing. Dates and times never touch participants, qualification flags, scores or adjacent games. Two standalone regression suites.

- **128-season franchise calendar (existing "128-season franchise (experimental)", `season_cap`, Experimental on, Basic and Advanced off), from wave A.** Beta 60's 128-season cap only raised the gate; the calendar engine repairs dates, weekdays, live birth years and season labels through index 127 with the final postseason in the following year, coordinating the existing year, calendar, season-length, preseason and 14-team playoff groups. The harness now derives its base year from the executable and checks all 128 indices for both 2004 and 2026 against an independent fourth-Thursday oracle (2100 and 2104 leap transitions included; final postseasons in 2132 and 2154). The public option now normalises to the cap plus the calendar plus the 2026 regular and preseason ROST templates on the allocator, which an XBE-only apply cannot certify, so the Franchise tab carries the exact starting-year wording instead of the old 2053 warning. The ROST writer's receipt counted 2,089 changed bytes for inputs over 1 MiB; it is 2,085. Unwitnessed.

- **Franchise 2026 roster rules: host rules built, runtime not ready ("2026 franchise rules (unavailable)", `franchise_2026_rules`).** The memo's R1 to R5 (three regular-season standard elevations with the third being the last, postseason elevation after exhaustion, IR timing, a 47 or 48 man game-day selection from 53 plus two elevations covering every primary position and two quarterbacks) exist as validated host ownership transactions, an explicit counter companion and a bounded native kernel in 4,096 writable bytes. They are not enforced in a running game: `RUNTIME_READY` is false, the build preflight refuses, and the capability is inspection-only. The memo's full 60,872-byte ledger cannot live in spare save bits (only bits 5 to 7 of player byte +0x53 are free) and appending to retail files is not authorised, so the compact schema is a proof, not the feature.

- **Senior Bowl: preparation and dormant components, simulation not built ("Senior Bowl native event (not available)", `senior_bowl`).** A signed franchise reader, a complete primary-pool scan, a reproducible 53 plus 53 positional selection, four verified kit choices, a seed, a 16 KiB event codec, stage and recovery policy, a scouting-line projection and a preview page with saved projects are built; the Simulate button is disabled and says why. Native simulation, persistence, live team cloning, results screens and scouting-card hooks are specified in the report and WIRING, not implemented. The safe decision was to refuse native activation rather than write unowned save bytes. The owner reserves its writable heap so a later build does not move anyone. The MyCareer draft-start research below settled two more Senior Bowl facts: v1 will use the retail generic NFL uniform template (bank 31), and its scouting output has no draft-stock effect.

- **Create a Team can pick all 82 stadiums (Build: "All 82 Create a Team stadiums (experimental)", `all_stadiums`, off in every preset).** The 67-entry stadium list had three readers, two search bounds, two preview modulo bounds, a previous-preview offset and two controller wrap bounds; the memo had missed four of them. An owned immutable 82-byte ID list plus ten operand edits keeps the first 67 in order and appends the missing 15, with no mutable state, ROST growth or save version. Unwitnessed.

- **MyCareer without a prepared save: create MyPlayer in the game (experimental, default off, `my_career` with no setup file).** Noah's question was why MyCareer still needed a Franchise save carried to the Draft. The second MyCareer design (mode 2, mode 3) removes that: the Game Modes row that used to launch First Person Football opens an owned entry list with Enter the draft, Undrafted free agent, Load career and Quit to main menu. Undrafted free agent runs the game's own Create Player screen (the native creation branch, name, appearance and equipment preserved; the five positions without a native rating template get balanced ratings), then any of the 32 clubs, then the complete native franchise initialization, free-agent removal, contract, jersey and club association. The career lives in an Apartment with five rows: Play next game, Practice, MyPlayer, Save and Quit to main menu; Play selects your next unplayed fixture through the native schedule, the native postgame and week handling return to the Apartment, and the career saves inline in the ordinary franchise save (schema version 1 footer) so the native Load screen brings it back. Off the field the CPU plays at normal speed. With Franchise Auto Save installed and switched on, a completed result saves to the slot chosen by a manual Save or Load (the two owners validate each other's complete installation and compose in either order; that composition is what the first landing of this mode broke and the M2a repair fixed). The owner reuses the legacy allocation (8,192 code bytes, 4,096 writable; 8,118 used, 57 spare). What is not built: the draft entry shows `Draft entry is not ready.`, automatic CPU drives while MyPlayer is off the field are proved only at the frame, snap, turnover, timeout, halftime, overtime, injury and substitution boundaries (not a whole drive), and the M3 items (calendar, player card, depth editing, upgrades, requests, hub art) are measured and not installed: the upgrade core alone needs 251 more bytes than the reservation holds. A legacy MyCareer.json setup from a draft-stage save still works through the old route. Bounded native execution, four disc cold loads and both gates; never booted. Built by Astra (mode 2, M2a, mode 3, 2026-09-07 to 2026-09-08). Unwitnessed.

- **MyCareer mode 4: the lists you could not see, the marker, the icons and the quit rule (same `my_career` option).** Noah played the in-game creation twice tonight and reported a Choose team button that did nothing, a blank backdrop after Sign, no marker under MyPlayer, no play art or receiver icons for the quarterback, a too-high pre-snap cut, and a quit game that advanced the week. Root cause of the blank screens, proved on native code: the owned club list and Apartment descriptors carried rows and strings but no layout resource for the animated renderer and had the direct text mode disabled, so the native menu built its rows and took input while drawing nothing (that is why blind A presses ran Play); Choose team was a settings-kind row the A handler never routes to an action. Mode 4 adds an owned text pass after the native event with retail fonts, the selected-row styling and native glyph walking, so the Apartment title, five rows and a fixture footer ("Off field: CPU at normal speed") and a real 32-club picker draw; the confirmed club is the one that signs. MyPlayer's side satisfies the human-side reads the retail indicator, receiver icons and pre-snap play art key off; the first Play continues into your own fixture after the league processing; a quit game stays playable; Team Select defaults to the career club; the pre-lineup presentation camera takes the retail human branch while the gameplay camera is untouched. Supersim stays uninstalled: the fast-forward candidate measures 40 to 42 bytes over the tested layouts before any screen work, so the footer states the wait instead. Both gates and the 101-pair composition suite. Built by Astra; unwitnessed.

- **MyCareer at any position, on the Game Modes row (Build: "MyCareer (experimental)", `my_career`, off in every preset), and the Crib movie cut ("Crib movie cut (experimental)", `crib_reclaim`, off).** The mode that replaces First Person Football, in its second revision. The Game Modes row that launched First Person Football is the MyCareer action, and the route is proved by bounded execution, not only by bytes: the retail list dispatcher maps the row's kind through its case table and calls the owner's entry; a build with no sealed setup shows a native message and pushes nothing, a configured build shows the entry message and pushes the native Load and Save screen, and the five neighbouring rows keep their targets. First Person Football's exhibition entry is gone, and its Franchise Settings toggle still works. MyPlayer can be any of the 17 retail positions: from a signed Franchise save at the NFL Draft stage, the MyCareer page takes a name, a position, one of that position's three retail create-a-player templates where they exist (quarterbacks, backs, receivers, tight ends, linebackers, defensive backs, kickers and punters; linemen keep the generated prospect ratings), the controller and a Standard or Far camera, replaces the first eligible prospect at that position in the same 84-byte record and the same 720,044-byte save, and publishes a signed `MyCareer.zip`, its JSON (schema v2 with the position; a v1 setup is refused with a message to create MyPlayer again) and a receipt. The runtime identity compares the record's position with the sealed recipe, and a once-only starter lock places MyPlayer on depth row 1 with the depth-lock rank bit at the first active club. Control binding is position-agnostic because the frame input walk decodes input for any on-field body with a controller and each body applies its own command context; the report tabulates what is proved and what is a hypothesis per position group. Human route running, blocking and pre-handoff control are not retail non-first-person features and are not provided; the CPU calls plays, snaps and kicks. The owner's screen guards were fixed so it composes with the playlist, Free Practice and the Practice Squad screen in either order (its hook sat inside spans those owners pin whole), it now detects the camera owner by that owner's constant spectator hook instead of a byte the Far default happened to write, and the XBE gates apply the modern naming explicitly since the composition fix no longer carries it. The Crib movie cut is an independent patch on the movie consumer with a streamed plan and a transactional archive and disc shrink (23 movies, about 417 MB reclaimed; the Trophy Room, awards, profiles, shared room, games and furniture stay). Nothing here has been booted.

- **MyCareer as an in-game mode: designed, its native prerequisites proved, not built.** Noah's target is a mode you start from the game, not from a save prepared in the studio. Session M1 wrote the design (`ASTRA_MYCAREER_MODE_DESIGN.md`: the feature-to-native map, the save candidate and field layout with its ownership gate, the game and Practice return contracts, the CPU and off-field decision, budgets, the art requests and the milestone acceptance criteria) and a read-only audit command with nine pinned native functions, and proved by bounded execution that the native creator selects a free created record, initialises its name storage and college reference and pushes the real player editor, that Franchise Options advance runs its validation and pushes the next screen only when accepted, and that the season load and save round-trip a 128-byte tail of the save file. The follow-up audit then found a supplied year-7 franchise save with nonzero words in that tail, so the unconditional use of the tail is rejected and no save writer ships. The Supersim and draft-start research settled the start of the mode: retail has a real pause-menu Simulate To End and a visual simulator, native simulation can run ticks and stop at possession, quarter and half boundaries, but a correct return to live play is not proved, so no off-field skip patch is installed (`nfl2k5_supersim` is a bounded reader with `RUNTIME_READY` false); draft entry will use the real prior-season route with two start choices, "Enter the draft" and "Sign as an undrafted rookie", and one continuous bounded run proved the native data lifecycle from a fresh roster through all 268 fixture simulations, the year rollover, retirements and free agency, the Combine and draft entry (eight trials with the same created quarterback produced three clubs and five undrafted outcomes, so no draft selection is promised). The apartment hub art was authored to the design's constraints (a 512 by 512 backdrop, a panel atlas, a calendar icon atlas and a focus row) with a checker that verifies sizes, alpha, mips, palettes and banding; after Noah asked for a game asset instead of a drawn room, the backdrop became the Crib's own night skyline (`crib_scene_texture:skybox_night:0`), recomposed from the user's private source cache by a committed recipe because the repository carries no retail pixels. None of the hub art is installed in a disc; the Build caption "MyCareer: create MyPlayer in the game" is reserved in WIRING for the milestone that builds it. Nothing here changes a hook, an allocation, a preset or Build.

### Presentation

- **Modern 2K mode names in the game (Build: "Modern 2K mode names (MyNFL, MyPlayer, Play Now)", `modern_naming`, Experimental on only when every span fits). Witnessed: MyNFL.** Fixed-span text replacement in the executable's string bank: Franchise becomes MyNFL in the menu link, Options, Save, Settings, Status, milestones, trophies, the Celebrity Phone note and the completion messages; Quick Game becomes Play Now; Player Create and Create Player become MyPlayer. Every span is listed with its virtual address, UTF-16 limit and every static reference, with a complete preview in the Text page. Screen names inferred from descriptor context are hypotheses until witnessed; the MyCareer menu row and title get two 20-byte owned strings. Noah saw MyNFL in the game.

- **Cameras: paired Standard and Far, the new Standard starts every game and practice (Build and Gameplay Patches: "Start games with the new Standard camera (experimental)", `camera`, Advanced and Experimental on, Basic off). Witnessed.** Retail started new profiles on Standard and restored a saved choice. Noah first asked for Far every time because the raised, farther view leaves room above the scorebar; the first camera owner (64 owned code bytes, riding the final grown pass with the allocator) selected Far at game entry and raised Far's seven scrimmage descriptors. His next note was that the old Standard was now too close and the throw pulled back too far. Camera v2 pairs the two rows: Far keeps the raised, far framing; Standard takes retail Far's settled eye distance at the new raised pitch, so it is the closer of the two but no longer the retail close-up; both rows keep lens 28 through the pass states instead of widening to 24, and the native live growth stops at a much smaller height so throws pull back less. The earlier projection fixture had omitted part of the native eye position, which the report corrects with the actual `5F760` arithmetic. Noah then chose the new Standard as the default: v4's owned wrappers select row 0 at game and practice entry and after settings and franchise loads, the fresh-profile default site is left retail because retail already starts on Standard, Far stays one Options change away, and Options changes last for the session (nine hooks, 27 receipt edits; older camera installs refuse as foreign). Sixteen selection and geometry proofs run the real initializer, settings importers and game-entry path under Unicorn. Witnessed on disc bd: Noah called both cameras perfect, keeps the new Standard as the default and Far for the extra pull-back.

- **Widescreen v3 (existing "Widescreen 16:9 (experimental)", `widescreen`, Experimental on).** Noah reported artifacts and a general feeling that not everything fit. Astra audited every camera consumer in the executable (table in the report) and fixed the proven inconsistencies: the second interlaced field was still stretched (v2 corrected only the first), the projection-dependent screen plane was rebuilt before the projection changed and left stale, projected shadows were culled against the old frustum, the sky panorama and full-target tint were pillarboxed and used the old horizontal angle, projected billboards and the passing icons and foot and head markers went through a wide world projection and were then compressed again by the 4:3 HUD, player name labels were clamped to the inner window, replay markers took two active-camera projections, and a one-pixel camera scissor could round to zero. The regular HUD keeps its apparent size and the play-call diagram stays pillarboxed by design. Still open and honest: crowd and sideline pop-in, stadium and dome seams, LOD transitions and replay bars are asset-level hypotheses that a CPU proof cannot settle; they need Noah's eyes on a wide display. A byte receipt lists every corpus function and hook. Unwitnessed.

- **The static ESPN scorebar, from v8 to a repaintable template to the broadcast-measured bar (Build and Gameplay Patches: "Experimental ESPN scorebar", `scorebug`, Experimental on, Basic and Advanced off; "Scorebar artwork folder", `scorebug_folder`; "Scorebug effects (diagnostic only)", `scorebug_runtime`, off everywhere).** The community report said the beta-61 static bar was too big and clipped and the runtime build with logos hung on game entry. Two static defects were proved and fixed first: the preview omitted the game's native +16 vertical viewport translation, so the bar rendered 16 pixels lower than previewed, and text objects that initialise their font scale to 2.0 were approximated at 9 pixels; the installed scene and root now project to the frame bounds measured from the ESPN capture, [84, 381, 560, 429] at 640 by 480, and that measurement is a test, not a hand-typed target. A second audit settled the boundary: the static bar is native scene data the game already draws, while logos and live marks need the runtime owner. Noah then judged the v8 bar unreadable (a dark two-row box with unbound cells) and asked for the real ESPN bar. v9 rebuilt the bar as one wide dark frame with white text, the disc-derived ESPN mark moved into the left cell and the red down banner over a light clock strip, with the detached tab art and decorative timeout marks removed. v10 replaced hand-placed pixels with a lossless PNG-layer compiler: the bar is a folder (`layout.json` plus one image per layer at 1x and 2x, schema `nfl2k5_scorebug_template/v1`), the Build tab has a folder field so anyone can paint their own bar (183 files joined the release allowlist for it), and the shipped folder is newly authored art. Claude authored a broadcast ESPN template from Noah's SVG lineage (one 476 by 48 bar inside the HUD rails, 32 team block pairs, a 120-colour atlas) and the real reference frame is a Raiders at Texans broadcast capture. The exact revision measures the bar directly from that frame and installs broadcast-derived layers with a comparator that scores every region of the installed scene against the reference, and the static option installs that bar by default while an explicit folder still selects the byte-identical v10 contract. The loop then ran to iteration 773: private scorebug font resources bound through the native registry (so the digits, clock and quarter match the reference size and weight while FONT4, FONT8 and every global font slot stay retail), the thin rim with its measured silver and red reflections, the clock-cell reflections, corners and separators, matched score weight and quarter capitals, the Raiders and Texans logo contours fitted at atlas resolution, one native white possession chevron, and a compact font for three-digit scores in both native flip directions; the mean regional colour error against the broadcast crop fell from 42.8 to 25.3 and settled, the runtime owner uses 1,395 of its 1,408 code bytes, and no new request, option or preset was added. Before and after renders from the offline projection harness are in `docs/scorebug_ingame`. Witnessed on disc bd as the base with four defects, which v2 below repairs.

- **The v2 static bar: live team names, separated clocks and an event row (the in-game fix).** Noah's three screenshots on disc bd showed the loop-773 bar with the quarter clipped to "st", the game clock and play clock run together as "5:0022", "Ball on WAS 35" drawn over the down pill and no team identity on the neutral panels. The fix session first proved what the screenshots were made of: the typography is retail FONT4 and FONT8, not the private fonts, because those bind only with the runtime owner, and a calibrated native raster of the old bar reproduces the captures to zero pixels of edge error. The new default scene puts the live team abbreviations on the outer neutral panels in native FONT4 with the existing possession predicate choosing yellow or white, gives the quarter, game clock and play clock separate cells (1ST, 5:00 and a dark play-clock cell with white digits), widens the red pill from 86 to 104 units so "4th & Inches" fits, and restores a lower event row for ball-on, fumble, flag and field-goal labels, which retail can request in the same frame as the down. The executable edits are two tail jumps to the native uppercase routine, a 48-byte in-place quarter-case replacement and three immutable newline-to-space format strings; no cave, request or allocation is added, and the runtime emitter changes only a four-byte play-clock colour. Old exact-v1 discs are foreign to v2, so rebuild from a clean source. Witnessed on disc bf: right before the snap, and the whole middle vanished during the play.

- **The v3 static bar: the middle stays through the play, and the panels wear the teams' colours. Witnessed.** The vanishing middle is retail behaviour that v2 had inherited: the native visibility owner drops the down and clock elements during the live play. v3 rewrites that owner as one pinned 581-byte span so the red down box and the quarter, game clock and play clock cells stay requested and drawn at the same size in every state, with live values, and the play clock shows two dashes when the game has none. The panel colours use the callbacks that already fetch the live team abbreviations: they now read each team's retail primary colour and tint the two panel materials, so BAL sits on purple and JAX on teal, MIN on purple and NYJ on green, with no runtime owner, no game-entry hook and no cached team pointer, the mechanism a tester had tied to the runtime bar's hang. The session first reproduced Noah's three captures from the installed v2 scene to within one pixel, then rendered the v3 forecast for the same moments plus a live frame with the middle present. Static text stays on the retail fonts, an explicit artwork folder still selects the byte-identical v10 contract, and the runtime bar stays off. The shared help, the availability check, the allowlist and the registry wording follow v3. Witnessed on disc bh: Noah called the scorebar good; one cosmetic item carries to the next beta, the rim is red on the right and silver on the left (the reference broadcast's colours) and should be all silver or follow the team colours.

- **The scorebar rim follows the teams (v3 revision, no new option).** Noah's note on the final disc: the outline was red on the right and silver on the left, the reference broadcast's colours. The rim turned out to be painted into the generated atlas tile, not the template PNG layers, so the tile now carries a white mask and the two outline halves take a material tint from the same live team callbacks that colour the panels: each side uses the team's retail primary when it differs from the panel fill, otherwise the retail secondary, otherwise silver. The down box, clock cells, centre and decorative timeout marks stay neutral. Two three-byte visibility instructions change; no new owner, hook, cached pointer or resource lookup. The explicit artwork folder (v10 layout) is byte-identical, and Scorebar Studio round-trips unchanged. Forecasts for BAL at JAX, MIN at NYJ and LV at HOU ship with the report. Built by Astra; unwitnessed.

- **The runtime scorebug freeze: investigated again, still open, the next comparison reduced to two probes.** The runtime owner (logos, live timeout marks) hung on game entry for a tester. The first investigation this beta proved that the native reader, allocation, decompression, registration, lookup and event hooks all terminate in simulation and that two real native wait loops can freeze with audio alive if their completion is withheld; rather than ship a speculative hook change, a six-profile runtime diagnostic matrix (`scorebug_runtime_probe`) was exposed. The second investigation added the parent game initializer, the complete scorebug frame continuation, the native completion writers and both special lookup-context branches to the fixture, recorded bounded traces of every PC, poll and write, and found no first failing hook and no hook-starved completion in the supported CPU fixtures; a Discord tester's report that removing the custom team-binding hooks stops the hang is the strongest lead. The production owner is unchanged, no defer, reorder, timeout or forced completion is shipped, the next gameplay comparison is reduced to the `hooks` and `neutral` probes (the other four stay available), and the runtime option stays off in every preset.

- **Guardian cap overlay (Build: "Guardian caps (experimental)", `guardian_overlay`, off in every preset; the beta-61 route B "Guardian caps on helmet C" stays in Experimental).** Per-player caps over helmet A or C, optional caps for everyone in practice, B-shell geometry at both player LODs, one soft-shell texture (the neutral quilt writer repackaged as `helmet01`), a fresh resource lookup with a missing-texture fallback and a masked native clone hook (three pinned live hooks). Record byte +0x53 bit 5 is the cap; the star-tag writer now masks only its own bit. A reusable pack-0 collection growth writer streams and verifies in 1 MiB blocks. The GPU output is unwitnessed.

- **Hi-res texture families (Build: "Hi-res pack (experimental)", `hires_pack`, with six family boxes, off in every preset).** Wave A's pilot (scorebug frame, one created-team field logo, one helmet at 2x, from a `Hi-res` folder or `.2ktexmaster` masters) grows to a compiler over 2,524 pinned resources in six families: 64 helmet art, 1,920 uniform numbers, 64 paired clean and mud jerseys, 126 created-team midfield logos, 348 embedded stock midfield logos and the two scorebug pieces. What cannot be said: that they fit in 64 MiB with a proved headroom. The game builds a variable residual resource heap at runtime, so the compiler refuses a modelled overage, reports smaller selections as unproved and leaves headroom null; the 128 MiB target stays disabled because the game limits texture addresses to the first 64 MiB. The Build tab exposes the families with a budget preflight, the worker rejects stale replies after a folder or selection changes, the family check no longer dereferences an unavailable module, and the compiler is classified beside the writers that own their own compression. Unwitnessed.

- **Add your music, the simple way (Music tab).** Noah's ask after a tester's song came back sounding like an old console: make adding music seamless and readable. The Music tab now opens on a Songs page with one "Add songs..." button (MP3, M4A, FLAC, OGG or WAV, several at once, or drop the files anywhere on the page). Each file is decoded and resampled to the game's rate automatically, volume-matched to the game's own jukebox songs (gain capped at +12 dB, peaks at -1 dBFS), and appended to one list that shows the game's 66 songs and yours together, marked "yours", with editable title and artist, Remove, Move up and down, and a Play that plays the encoded result the game will decode rather than the source file. The line under the list says how many of your songs Build will add. Plain-words warnings, never refusals, for a file below 22,050 Hz, 8-bit sound, under 64 kbps, or so quiet that the volume match hits its cap ("This file is very quiet; the game will add hiss. Use a louder copy."); only songs over ten minutes or beyond the 200-song limit refuse, with the reason. Missing FFmpeg is one sentence naming the download. The Playlist page follows added, removed, renamed and reordered songs by identity. The old Recordings page sits behind "Advanced: edit existing recordings" with every earlier control intact, and a portable v2 Music project carries your prepared songs and choices without game audio. The getting-started Music section is a five-step walkthrough and the FAQ answers "my song sounds crushed or like an old console". For the record: the shipped encoder was measured tonight on a real MP3 at 35 dB signal-to-noise with no block-rate buzz, the same codec and rate as the stock songs. Built by Astra; unwitnessed in the game.

- **Shared music shuffle and the Playlist page (Build: "Shared music shuffle (experimental)", `music_shuffle`, off in every preset).** Fifteen live hooks (86 bytes) replace the background disc and HDD playlists with the Playlist page's selection (66 core songs by default, outtakes and ten background beds optional, at most 100 records, 200-song banks browsable); the shared menu, Crib and game background player shuffle it while loading screens and shows keep their timed music. Tier 4b adds native screen activation and the draft entry to the shared controller with bounded Unicorn coverage of all 24 named context contracts across 70 native screen tables, library verification against the installed executable and the rebuilt AUSB descriptors, and playlist documents that persist in projects. "All modes" is deliberately not claimed: individual screen routes and audible output are unwitnessed.

### Editor

- **Rosters: play styles in plain words, exact undo, 2026 names and ages (batch 1).** Power Run Style shows Finesse, Balanced and Power (1, 50, 99) beside the raw value, and undo of a bucket edit restores a non-canonical source value such as 38 exactly instead of quantising it. Scramble says "odd = scrambler" on the page, the parity card and the header; the Even/Odd toggle flips only bit zero. Kicking Style keeps its Punter, Default and Kicker presets with experimental wording; the old "signature release" claim is gone because that motion is unwitnessed. The 2026 name data and explicit age shifts complete the roster-data pass, and the Rosters page carries the abilities note and the portrait selectors (below).

- **ESPN 25th Anniversary: edit the rosters behind every moment, and author the moments themselves (Rosters, ESPN Anniversary subtab; Build: "Use saved ESPN Anniversary edits", `espn25_plan`, never part of a preset; Gameplay Patches shows an informational "ESPN Anniversary setup and rosters" row that opens the Rosters page).** Noah asked whether the 25 moments could get historically accurate rosters and whether the mode could hold more than 25. The research settled the first half: the moments do not use the live teams. Each side's selector names one of 35 shared historic roster files on the disc (75 exist, 53 players each; moment 0 loads the 1966 Packers file against the 1971 Cowboys file), matched by team name and year and imported through the game's own historic importer, and every field of the scenario record is now mapped: stadium index, human side, possession, scores, quarter, ball spot, distance, down, clock, timeouts, uniforms, weather. The Rosters tab gains an ESPN Anniversary subtab, enabled when a disc image is open (a save has no scenarios): pick a moment and a side, see the historic file it loads and every other moment that shares it, acknowledge the shared use, edit the 53 players or import a CSV in the Rosters format (export one to start), paste scenario edits as validated JSON, then Save build edits and tick the Build option with the saved plan. The plan is validated once against the source before any copy, refuses bare executables, the roster arena growth and the merged position pools, and is applied as the last pass on the disposable copy after every relocation; the studio reports a pending Game Text edit of the same strings as a conflict before a build starts and offers an identity-matched recovery snapshot. The edits are written into the shared historic files through the existing roster writers, so they also change that team wherever the game uses it, and independent rosters for two moments that share a file would need cloned resources, which this beta does not do. More than 25 stays research: the moment walker and accessor are count-driven and a 30-record table passes them, the menu count and reward loop are hard-coded constants that would change together, but completion is a 32-bit mask in the profile whose persistence past bit 24 is unproved, so installing an expanded table is refused until a profile save and reload is witnessed. Registry row 113, a 13-test integration suite. Unwitnessed.

- **Historic moment rosters: real players in the ESPN 25th Anniversary files (Build and Gameplay Patches: "Historic moments: real rosters", `espn25_rosters`, off in every preset).** Noah asked for the exact players on the field in each of the 25 moments. The 35 shared historic roster files now get 53 distinct real names each from the nflverse season rosters (CC-BY, 1960 to 2004, checked in as CSVs with a manifest of every row's source), keeping each retail slot's position, rating profile and appearance. What it is not: the exact game-day lineup. The source has no starts, depth order or awards, 105 slots had to be filled from neighbouring seasons, 1,173 jersey numbers are unknown for their year, and 12 moments share a file with another moment from a different season, so the file carries one season. Every approximation is listed per moment in the report and the manifest. The option needs a disc image, refuses the merged position pools (they recode the historic files) and cannot be combined with a saved Anniversary plan in the same build; it runs as a final data pass before the plan pass, and all 25 moments load in the native trace. Registry row 114. Unwitnessed.

- **Historic moment rosters, second pass: the exact starters and numbers from the box scores (same `espn25_rosters` option).** Noah: "we should be able to find the jersey numbers and starters from those games somewhere". They were found: the 25 box scores and the 50 team-season rosters were read through his own browser from Pro Football Reference (facts only; no page is shipped), and the dataset was regenerated. Every chosen side now carries its 22 box-score starters at starting depth (770 starters certified across the 35 files, 903 of the 1,100 starter names at starting depth across all 50 sides), the bench comes from that season's roster ordered by games started, and jersey numbers come from the season page: unknown numbers fall from 1,173 to 123 (all 123 belong to players absent from that season's page), other-season number guesses from 127 to zero, and 1,080 college cells are filled. The twelve moments that share a historic file with another season keep the chosen moment's lineup, and the fifteen losing sides list exactly which starters they lack; nothing is silently called exact. The generator refuses missing or ambiguous starter evidence. Built by Astra from tonight's pull; unwitnessed (open THE ICE BOWL, WIDE RIGHT and one more moment and check the pause-menu depth and the on-field names and numbers).

- **Team Kit bundles now import into any project, with a receipt, and big projects save fast again (Coach Edwards' report).** A tester exported a team's kit from a fresh project, painted it, and could not import it into his main project: "The working pixels changed after export for Torso / Jersey; export a fresh Team Kit bundle before importing." The importer compared every one of the 78 components against the bundle's export-time pixels and origin before deciding anything, so any earlier edit in the destination (another style's jersey, a number sheet's digits) refused the whole bundle. It now decides per component: a supplied PNG whose pixels equal the export baseline is skipped and never overwrites an edit in your project; a PNG that differs is imported in one transaction with one Undo; when your project already had a different edit there, the import goes through and the result names it ("your earlier edit") instead of refusing. Bad bundles (order, identity, duplicates, missing files, size, format, wrong team or style) still refuse before anything changes. The studio captures the selected team, style and side scope before the worker starts and forwards them as the expected sets, the Team Kit page shows the receipt under the private-export warning with imported, skipped and overwritten counts, the status line repeats it, the dialog's Details list every component by set, group and label, and only changed components mark the project dirty. Number sheets and kits work in either order. The same report said the editor slows past 300 edits: the save path was decoding every replacement PNG again on each save; a bounded cache of validated decodes takes a 351-edit save from 23.1 seconds to 0.09 seconds. The FAQ carries the interim workaround for older builds: export a fresh bundle from the main project, copy your edited PNGs over it, then import.

- **Use this save's roster on the disc (a tester's question).** A tester with a complete roster in an Xbox save asked how to apply it to the project. A save session could only write a re-signed copy of the save or export the edits made in the editor. The Rosters page now offers "Use this save's roster on the disc…" below the export row when a save is open, and the same action under Tools with a save picker when a disc is open. It compares the save's players with the current disc by identity and writes the ordinary roster edits file (names, numbers, positions, ratings, equipment, contracts, depth order, team membership including free agents and moves) with a receipt beside it: per-team counts and every skipped player with its reason (a name longer than its slot, no free slot for an added player, a disc on the merged position scheme). Build applies it through "Include exported Rosters edits". The FAQ carries both answers: play the roster by writing the save copy back to the HDD, or bake it into a disc with the new action and a build. Unwitnessed in game.

- **Number sheets: a layout chooser, and digits that stop coming out blocky (Coach Edwards' two reports).** Batch 2 first fixed the splitter: it chose the longer axis and rounded ten cut positions, so a five-column, two-row sheet was read as a horizontal strip and a width not divisible by ten was cut into unequal cells. The studio now asks for the layout after the digit family (one row, one column, five columns by two rows, or two columns by five rows, always 0 to 9 left to right then top to bottom), cells must divide the sheet exactly, an ambiguous sheet refuses instead of guessing, and `docs/mod_editor/number_sheets.md` explains equal transparent cells, padding, order and limits. His second report showed imported digits rendering with stair-stepped edges on one jersey and clean on another, and shrinking the source did nothing. The cause was in our encoder, not his art: the digit writer built each smaller mip by picking the most common colour in every 2 by 2 block, a region selector rather than a coverage filter, so a quarter-covered outline pixel became fully transparent, the error compounded down the chain, and the palette fitter then dropped colours to squeeze the result into the slot. Retail's own digit textures carry partial alpha in every smaller level. The cell resize is now a float, premultiplied filter, the mips are true coverage averages sharing one palette with the outline colours kept, and the new "Number sheet: encoded game preview" dialog shows every digit exactly as encoded, at jersey size on light and dark backgrounds, with the size notes, before anything is staged; "Import all ten digits" imports, Cancel stages nothing. Unwitnessed in game.

- **Gloves and cleats can get their own texture (a Discord question; experimental, per-variant choice).** maumau78 asked how shoe textures work and strayslastaccount explained he had to break the mip chain so a cleat read a single texture. Astra's census of all 634 uniform sets (1,902 glove and shoe spans) confirms the format: every named sock, glove and shoe variant in a chunk shares one swizzled index chain with its smaller distance images and owns only a 256-entry palette, so the shipped importer could recolour a shoe but never give one shoe a different stripe. Each variant also has its own texture descriptor, so the new choice, "Give this glove or shoe its own texture", points the selected variant at a separate image with a complete coverage mip chain (same palette order the game expects) and leaves the shared images for the other variants, including a separately named dirty version. Space is the limit: the whole recompressed resource must still fit its original slot, so the dialog offers the original, half or quarter size and refuses overflow instead of shrinking silently; the real-file proof fits a new 64 by 64 cleat design through all four levels. Ordinary imports stay palette-only. Team Kit's equipment browser and All Textures share the route. The dialog states what is lost and that nothing is witnessed at distance on the GPU. Built by Astra; unwitnessed.

- **Ten editor bugs from the Discord ledger (batch 1), each with a regression test and a FAQ answer.** The community feedback ledger Noah asked for turned up editor-side reports that never reached an issue tracker, and Astra worked through them from the reporters' own words; the protected diff shipped as a fixture patch and was applied unchanged. The updater compared the installed RC label against beta tags and so kept saying "Update available" after an update (X_Ray); both sides are normalised through the documented RC-to-beta aliases now, and a release without its digest sidecar is no longer offered for Update now. Selecting an option on Gameplay Patches and again on Build and Share never applied it twice (the build measures its output once), but Gameplay and Build did not stay in sync and a saved project lost its gameplay choices (Atomic and others); the two panels now mirror each other in both directions, the project file carries every Build choice, and old projects load with explicit defaults. A build whose output matched its input reported success while writing nothing; the receipt now measures the output against the source and the studio says "No changes written" or "Copy ready; changes not measured" instead of "Disc ready". Make disc and Check my images stayed grey for gameplay-only work; they route correctly now and explain their scope. A modded image reopened with a populated retail cache showed stock art; the cache refuses a changed archive instead. The three-letter first-name limit was the name pool refusing a longer donor, which is now explained and worked around. Portrait selectors are shown and confirmed in Rosters. Launching the wrong xemu binary from the studio (WinError 193) is refused with a clear message. Photoshop PNG variants are accepted and DDS is refused with the export advice. The Windows updater path, the in-game portrait witness and the reporters' own files remain on Noah's witness list; the answers are in `docs/mod_editor/discord_bugs_1_faq.md`.

- **Editor fixes from batch 2, and what the sweep found while wiring them.** Three of the four protected changes landed unchanged: the sheet layout question above, a destination check that runs before any expensive build work, and publication that refuses to replace an image another process holds open (the transactional image writer publishes the same way), so swapping emulators with a disc mounted can no longer clobber the output ("Did swapping emulators brick my XISO?" is answered: a crash or an open handle does not change bytes; compare hashes). The APF GUI change (panels reading staged art from the session) stays out because the fake facades in both APF GUI suites do not model it; it is handed back in WIRING with the failing suites named. Fixes found while verifying: the open-file probe now skips same-user processes whose descriptors are hidden (sandboxed browsers and flatpaks) instead of failing every build, and no longer calls a Unix-only user lookup, so it runs on Windows; the cached-source check looked up archive packs a to f in uppercase while the retail directory lists them in lowercase, which would have refused every retail disc once a cache existed; the layout lookup tolerates a label outside its table. The plan-level refusal of a Hi-res scorebug family combined with the scorebar runs before the image-parsing scorebar preflight again, so the cheap refusal comes first.

- **Build choices survive a disc inspection; a project restore resets only what it saved.** The inspection-completion path restored the project's Build settings after applying a pending preset, and with nothing saved that reset every choice to its default, wiping the preset you had just pressed. A freshly inspected source now keeps its current selections when no feature choice was saved (only the music part resets), while an explicit project open keeps the batch-1 contract: every saved choice is applied and absent ones return to their defaults. The APF crest master reads a modification's asset id with the design edit id as the fallback, so older modification objects still save.

- **Scorebar Studio: a scorebug editor and creator page (the Scorebar page, between MyCareer and Build & Share; registry row 110).** Noah asked for "a super easy to use scorebug editor/creator tool in the editor". Pick a preset (the reference v10 bar, the Fable ESPN template, a plain dark bar, or a retail-like approximation from colours alone, no retail pixels), then work part by part on the eight fixed cells with plain controls: fill colour, a two or three colour blend with a direction, corner rounding, a border, opacity, or your own picture fitted into the part (fit inside, fill and crop, or stretch), with undo and redo, merged slider drags and a dirty flag. The live preview composites the parts onto a drawn field at 4:3 or the 27/32 widescreen contraction in four sample states (1st & 10, 4th & 1, Timeouts, Two-minute), with stand-in text from the staged glyph sheet at the measured live-text positions and preview-only team colours, and an honest line under it for the colour count and the estimate of the game's 2,400-byte slot (blends are reduced to the colour limit jointly; exact pictures are never touched). Save writes a complete template folder (`layout.json`, `1x/` and `2x/` PNGs, your pictures, `scorebar_studio.json`) that the Build tab's scorebar folder field accepts and checks with the same compiler Build uses; Open reads any such folder back losslessly (the shipped reference round-trips byte for byte); Use in Build fills that field without ticking the option, which you still tick yourself. Limits, stated on the page: one bar for every team (team colours are preview only; live team art is the separate runtime option), no live fonts, cells or timeouts, and nothing here has been seen in a game yet. Twelve model tests, eleven offscreen page tests, a two-minute guide with ten rendered previews (`docs/mod_editor/scorebug_studio.md`), and the preset registry is one JSON row per preset. Unwitnessed.

- **Rules library and Info tab in Create a Play.** Noah's Discord question was whether the AI programming had been extracted. The assignments page now has Assignments, Rules library and Info tabs. The library pulls complete per-position rule bundles out of the loaded resource (Combo Inside Zone from ATL Nickel play 28 was the first), supports named selectors and search across every play, remaps friendly references, keeps explicit branch flags and validates the eleven combined assignments before staging through the existing writer, project and pack pipeline. Twelve sample plays (combo inside, outside zone, power, counter, draw, screen, cover 3, 2 man, pass sets, fire zone, speed option, inside zone) were decoded node by node and re-encoded with zero changed bytes across the 78,768-byte resource. The vocabulary is documented with its opcodes: combo exchanges as paired `0x1B -> 0x0D -> 0x0E` chains, zone runs as `0x11` type 8, pulls and traps as type 2, lead and release-then-block as types 4 and 3, pass sets as type 1 with the `0x1A` slide predicate, zone landmarks, man targets and cushions, fire zones as `0x1B -> 0x0B` with a replacement drop, screen hold and release, and reads as `0x1A` predicates (position and velocity, geometry, personnel). The Info tab is a read-only, searchable reference generated from structured JSON and the codec schemas, and an evidence manifest records every source hash without shipping retail scripts.

- **Bone and animation import (Animations page, experimental).** Exports now include `primary.gltf` and `primary.bin` for the native primary channel; a constrained glTF import verifies the canonical structure and the mandatory sidecar against the source bytes, keeps original words for unchanged keys, compares poses and samples, checks archive identity and split-pack placement, then streams, stages, verifies and publishes a new copy with a receipt (`check`, `import`, `limb-check`, `limb-import`, `variant`). Two complete `.rdata` motion spans are pinned by an executable owner that permits only their main rotation-word edits. A coordinated left-forearm length edit updates low and high SCNE and SKEL together, and the first authored referee gesture ships. The Animations page enables **Import to a new copy** only after preflight. MMCD and paired-root authoring still refuse. On Windows the import compares size and modification time instead of inode identity, and the streamed hash decides content.

- **Stadium editor: textured exports and Blender round trips.** Stadium glTF exports gain source-derived UVs using the proved per-shape scale and offset equation (no V flip), white base colour so the artwork is not darkened, and a 0.5 alpha cutout for transparent images; a Blender texture helper and atomic session imports round-trip edits with unchanged bytes preserved (changed UVs or geometry are not imported). Runtime ownership for new stadium geometry (F1) stays gated and its next steps are in the report.

- **Community Blender stadium add-ons: audited and withheld.** The community importer v0.11.1 and round-trip exporter v0.3.0 were reviewed in headless Blender 4.0.2 against a retail stadium. An untouched import and export changed 148,712 bytes of the mesh buffer because the exporter writes Blender's converted axes straight back, 8,885 rows still drift after correcting that, the Models import accepts the wrong geometry, and the exporter can overwrite its own template. The reproducible proof tool and audit tests ship so the author can fix and re-run; the add-ons themselves do not.

- **Disk-space preflights ask for the real bytes, not a 100 GiB floor.** The development brief's disk rule had been written into the Crib movie cut and the animation import preflights, so anyone with less than 100 GiB free was refused. Both now need the copy or scratch bytes plus a margin and say the exact numbers.

### Packaging, CI and verification

- **Owned executable space scaled out: 104 KiB of code pages, 84 KiB of writable pages and 16 KiB of read-only space (existing "Extra patch space (experimental, unwitnessed)", `xbe_space`, selected automatically by any owner that needs it).** Beta 61 grew the executable by two code pages, one writable page and a 64 KiB music section, and every wave-B feature needed more. `nfl2k5_xbe_space.py` now builds a fixed, page-granular map from the section-run table: three added sections with hard per-kind budgets, a 4 KiB read-only directory page, and the same named deterministic allocations per owner (a replay checks the same request set). Every beta-61 owner keeps its addresses and beta-62 owners sort together after the complete beta-61 union; no retail section moves. A pure `plan` API and CLI reject invalid, duplicate, misaligned or over-budget requests before a build; `install_read_only` writes exact immutable bytes; writable state starts zeroed and never lands in `.text`. The largest single request today is 96 KiB of code, 80 KiB of data or 16 KiB of read-only. The grown executable is 12,300,288 bytes. Any build that selects a beta-62 owner picks the scaled-out layout automatically.

- **Every owner installs in every order.** A pairwise composition suite installs each pair of the twelve wave-B executable owners in both orders and requires identical bytes, `applied` status on both, zero changed bytes on replay and an unchanged allocator; the final audit ran 66 pairs in 132 orders, all byte-identical. Two real conflicts fell out of it and were fixed: the read-option runtime and the screen timing hooks both pin the native pass initializer at `0x19C740` and used to refuse each other's detour; MyCareer's screen hook at `0x6E390` and the playlist's event-dispatcher hook at `0x6E4E0` sat inside spans that the playlist, Free Practice and the native Practice Squad screen pin whole. Each guard now validates ownership first and dependencies second, and accepts a partner's hook bytes only after that partner's complete owner validates, never arbitrary bytes.

- **Experimental export works again.** Beta 61 shipped without an experimental `.2k5patch` because the exporter refused a chained growth ("growth must append at the first sector after the image"). The cause was a retained intermediate allocation: the SPECIAL tab appended an executable, the scorebug appended pack 0, and the final owned-page executable superseded the first one, leaving 12,021,760 physical bytes unaccounted for. The mod-pack format now records each growth's append sector and offset, and a `file_grow` payload (version 2) carries the retained bytes before the replacement file in one streamed, hashed append. Before and after hashes stay mandatory, every byte of the projected result is compared against the author image, and a 32 MiB retained-prefix test proves the reader never exceeds its 16 MiB block. Ordinary contiguous chains keep payload version 1. Share also exports every grown named file.

- **The reservation manifest and the two executable gates, regenerated after every landing.** The cave manifest (`data/nfl2k5_cave_reservations.json`) was regenerated 26 times on this stack, once after each owner landed, and the provider and runtime-checker pins were refreshed with `packaging/repin.py` each time. Two recorder defects were fixed on the way: an owner's declared edit inside its own grown page is now published from the final layout instead of pinned from the dormant-owner probe (the probe had placed the camera owner at a different page offset, so both gates refused the regenerated manifest), and allocator reservations are consulted only when the observed image actually carries the applied allocator (the seven-on-seven owner is applied on retail space, and asking the allocator for it returned planned pages outside the mapping). The probe base is built without any allocator-selecting preset option now that the Experimental preset carries a v3 owner. Gate declarations followed the owners: the kickoff v2 hooks are also declared by the relocated kickoff variant, the practice-squad caves may carry the roster arena owner's declared import repoints, the wave-B owners belong to the complete union rather than the legacy request set, the franchise-2026 merge of the gate union helper was repaired, the memory-write gate got back the guardian and Senior Bowl methods the union resolver had trimmed, the XBE gates apply the modern naming explicitly, the scale-out tests size their synthetic owner from the shared LARGE constant, the practice-squad Unicorn fixture maps the allocator's grown pages before writing them, the allocator stack projection pins the kickoff separation hook only when a kickoff owner is installed, and the historical kickoff v3 receipt allocates under its own recorded union. One `dormant_union()` feeds the manifest and the allocation proof, with v3 routing for the dormant set.

- **CI on Windows and macOS, the local Windows tester, and the sweep fixes.** The eight-job CI loop learned to reproduce the assembler proofs only with a GNU x86 assembler that emits ELF32 (Apple's assembler and MinGW's COFF output skip them, and the Senior Bowl template reproduction shares that probe), the disc memory budget measures without a kernel ceiling on macOS (which rejects lowering RLIMIT_AS), eight shipped text writes and the candidate registry envelope pin LF, and the wiring of the second integration left seven CI failures that were fixed together (the modern names panel catches an unavailable backend instead of aborting a catalog-only build; the Build-only momentum level widget is guarded; a fresh Build selection counts feature toggles only, so the default-on caps-in-practice and hi-res family boxes no longer block Start SOFTDRINK basic; the Senior Bowl test tolerates its merged registry row; the shell tests expect the Modern mode names subtab). The audio integration test cleans its temp dir after tearDown so Windows can delete the loaded source (the WinError 32 flake in beta-61 CI). The local Windows tester (Wine 9.0, the installer's own runtime) ran the beta-62 changed set: 135 files, 122 passed, 7 failed on the first pass and 70 changed files later (55 passed, 11 Wine gaps), and every real failure was fixed on the stack: provider closure pins for the wave-A modules, Build-plan coverage exemptions for sub-setting fields, a cp1252 read in a maintainer-only export test, the hi-res compiler's VC-LZ classification, the Hi-res family check that dereferenced an unavailable module, and two stale beta-61 expectations (the runtime scorebug off in every preset, the music revalidate hook stubbed); the Wine gaps (audio inventory identity, the Job Object ceiling) are recorded. The full local sweep on the stack later found five more: the scorebar template compiler, its art tool and the kickoff returns tool let the platform pick a line ending (they pass `newline="\n"` now), two allocator tests and the APF installer test pinned figures the camera owner and the registry moved, the music all-modes wiring test faked a facade that accepted only the music keys, and the coverage test names the new Standard camera caption. The APF runtime gate follows the shared registry (108 rows at that point, 37 APF unchanged).

- **The three integration sessions and the five interrupted ones.** Integration 1 wired the batch-1 owners (82 stadiums, 2026 team names, the levers, the hi-res pilot) into BuildPlan, the presets, the dispatcher, the four status dictionaries, the panels, the allowlist, the runtime closure and the registry, and taught Share to export grown files. Integration 2 wired the wave-A owners (music shuffle with the Playlist document, the Practice Squad screen, abilities with the off week, QB spy with its paired intent table, the calendar under the public 128-season option) the same way, with the registry at 95 rows and 57 NFL 2K5 capabilities at that point. Integration 3 wired the wave-B owners across Build, the Studio and the release closure. Five Astra sessions (calendar engine, QB spy runtime, abilities runtime, Practice Squad screen, music playlist) were cut by the Codex usage limit on 9/5 and preserved as WIP snapshots, then completed; every one of them is a finished owner above.

- **The build-ordering test follows the OLB removal.** The explainable-build suite's ordering test stubs the one-pool writer and the roster reclassifier; after the final Outside Linebackers filter pass landed it needed the roster scan stub and now expects the `position_pool_filters` step after `depth_roles`. The local sweep on the ship candidate caught it (one error in 16 tests); the fix is test-only.

- **The CI test jobs get 45 minutes.** The suite reached 495 files with tonight's native frame replays (MyCareer mode 4, read option v3, kickoff v6); Linux finishes in 22 minutes and the Windows runners ran out of the old 30-minute job budget at 471 files with nothing failed, so the job budget is 45 minutes. The per-file 420-second budget is unchanged. With the budget raised, the Windows runners reached the release-check suites and found two rules that read Windows file stats as violations: a hard-link rule (Windows reports zero links) and a world-writable rule (Windows reports 0o666 on every file); both now count only on POSIX, where the staged release is actually built.

- **Known local-only test finding, carried to the next beta.** Two retail-only tests (the zone-drop and MyCareer manifest checks, which need the retail executable and so never run on GitHub) fail on this stack with "new pages overlap another manifest owner": the allocator's own dormant union (`nfl2k5_xbe_space.dormant_union`) lacks the camera owner and Franchise Auto Save, both of which the manifest builder and the gate union include, so the proof layout it derives is shifted against the real manifest. The shipped reservation manifest, both executable gates and the pairwise suite use the complete union and are green; the defect is in the proof helper, not in any shipped byte. It is the first fix on the next stack because it is a manifest-pinned source.

- **Counts.** The capability registry holds 116 rows (78 for NFL 2K5; 83 rows at beta 61), the release allowlist 749 exact files, the unified provider closure 243 pinned modules, the runtime closure 206 product modules and 34 tools, and the reservation manifest 28 extra owners, 10,808 reservations from 125 observed writer calls and 144 pinned source files (manifest 26, regenerated after the last landing on 2026-09-08). The Scorebar page joins the sidebar between MyCareer and Build & Share.

### What is honestly partial

Every one of these is labelled in the studio and in its report. None is hidden.

- **Senior Bowl:** data preparation, selection, kits and a preview page. No simulation, no results screen, no scouting hooks. The Simulate button is disabled and says so.
- **Franchise 2026 roster rules:** host-side rules and a dormant native kernel. Nothing is enforced in a running game; the build preflight refuses the option.
- **Scorebug runtime freeze:** not root-caused after two investigations. The static bar is v3 and witnessed; the runtime build stays off in every preset and ships the probe matrix, reduced to `hooks` and `neutral`, for Noah to run.
- **MyCareer in the game:** the Game Modes route, the any-position writer and the identity are proved and unbooted; the in-game creation mode is a design with native proofs and authored art, not a shipped option.
- **Deep-zone corner facing and bail:** not built. The memo does not certify them; a read-only audit and native proofs ship instead.
- **Hi-res families:** the compiler covers 2,524 resources, but a proved memory headroom cannot be stated from static evidence, so the studio refuses a modelled overage rather than pretend.
- **Read option:** the mesh, the read cue, the replacement EDGE and the hold-to-keep controls are built; the RPO receiver press enters the native pass continuation and is not a guaranteed instant throw.
- **Music shuffle:** the shared player, Crib and game background are proved by bounded execution; individual screen routes and audible output are unwitnessed, so "all modes" is not claimed.
- **Modern naming:** every span is byte-proved; MyNFL is witnessed; which other screen shows which string is a hypothesis until seen.
- **Widescreen v3:** every proven projection defect is fixed; asset-level seams, pop-in and LOD transitions need eyes on a wide display.
- **Dynamic kickoff:** v5 is witnessed as good; the end-zone catch presentation (no visible kneel) is the open item.
- **Scorebar:** v3 is witnessed as good; the rim colours are the open item; the paint-your-own folder path and Scorebar Studio are unwitnessed in game.
- **ESPN Anniversary:** rosters and setup per moment are editable and the real-roster data patch exists, both unwitnessed; more than 25 moments is refused until a profile save proves the completion bits.
- **Historic moment rosters:** real names per season, not game-day lineups; 105 cross-season fillers, 1,173 unknown numbers and 12 shared-season conflicts are listed per moment.
- **Franchise Auto Save:** witnessed once on one disc; long sessions and a lost destination are untested.
- **Guardian caps, abilities, QB spy, screen hooks, momentum collisions, arena growth, Practice Squad screen, calendar, OLB removal, Team Kit import, number sheets:** built and proved offline; never booted or never seen in a game.

### How it was verified

Every executable owner passes its own standalone suite, the two safety gates composed with every owner in both orders (79 memory-write tests and 95 cave-reference tests at the last count in the reports, in four installation variants), the reservation-manifest oracle, the pairwise composition matrix (run again after all wiring), the allocator scale-out and integration pins, and the feature suites listed in each report (818 tests in the third integration session's final loop, one historical-evidence skip; the MyCareer mode audit's 214; the scorebar v2 session's 351 with 11 evidence skips). The reservation manifest was regenerated alone from the retail executable and disc after the last source change. Packaging ran the release allowlist and runtime-closure checks on the staged tree, the local Windows tester on the changed set, a simulated non-POSIX real-disc build and apply, the release gate, the staged runtime gate, the updater end-to-end from RC85 and a Wine silent install of the Windows installer. The full local loop and the eight-job GitHub CI ran on the held ship commit (26b0d3d); the 75 commits after it each carry the suites named in their messages and two full local sweeps, and CI on the final commit is the release gate's job at tag time, not a claim of this text.

### Presets

Basic is unchanged from beta 61. Advanced adds the paired cameras with the new Standard default, Franchise Auto Save (installed; the in-game switch starts Off) and, through the existing merged-positions option, the removal of the empty Outside Linebackers group after the roster scan. Experimental adds all of those plus the modern 2K mode names (only when every text span fits), the full 128-season calendar under the existing 128-season option and the v3 static ESPN scorebar in place of the beta-61 bar, and it leaves the runtime scorebug (logos and live events) off until the freeze report is resolved. Every other new option in this beta is opt-in and off in all three presets.

### Research since beta 61, and what each concluded

The two beta-61 research tables listed what was buildable and what needed more work. Here is the verdict on each, in the order Noah gave them.

- **Momentum contact model (MOMENTUM_RESEARCH):** buildable as a bounded outcome-input term, and built (momentum collisions above). A general impulse solver remains deferred by the memo.
- **Defensive two-point try stats (DEFENSIVE_2PT_RESEARCH section 3):** buildable; the box-score row, saved category and player points are built. Field 59 of the saved stream is proved unused.
- **Widescreen consumers (WIDESCREEN night notes):** the blanket "active camera is correct" claim was wrong for the second field, shadows, sky and projected HUD markers; audited and fixed as v3.
- **Play AI extraction (Combo Inside Zone question):** the play scripts are data, not code: eleven per-slot node chains over 29 opcodes. The vocabulary is decoded and documented, the rules library extracts them, and the Info tab carries the reference.
- **Franchise practice exit:** the beta-58 launcher copied a restart, not an entry, and the launch arm discarded the Desk. Fixed and witnessed.
- **Deep-zone corner tiers (CB_DEEP_ZONE_RESEARCH sections 2 to 5):** facing and bail are not certified by the memo; audited, not built.
- **Scorebug (tester report and screenshot):** two static defects proved and fixed, the bar rebuilt four times to Noah's eye and witnessed as v3; the runtime freeze has two candidate native wait loops, no failing hook in any fixture, and a tester's binding-hook lead.
- **Read option (READ_OPTION research and the modern-controls ask):** buildable in stages; the runtime core and the v2 controls are built, the three-way RPO exchange is bounded by the native pass path.
- **Senior Bowl (SENIOR_BOWL_RESEARCH):** the data tier is buildable and built; the native simulation needs save ownership the memo does not grant.
- **Franchise 2026 rules (FRANCHISE_2026_RESEARCH R1 to R5):** the rules fit host transactions; a native ledger of 60,872 bytes has no home in the save, so the runtime is not ready.
- **128-season calendar (SEASON_CAP_RESEARCH):** buildable and built, proved for every index against an independent calendar.
- **Bone and animation import (BONE_ANIM_RESEARCH tiers 2 and 3):** buildable for the primary channel and embedded roots; built. Paired MMCD roots still refuse.
- **Stadium editor (STADIUM_EDITOR_RESEARCH and the UV finding):** textured exports and Blender round trips are buildable and built; new runtime geometry ownership is not yet.
- **Guardian caps (GUARDIAN_CAP_RESEARCH route A):** buildable and built on record bit +0x53 bit 5.
- **Screen passes (SCREEN_PASS_RESEARCH section 4):** the two scoped runtime hooks are buildable and built as an opt-in experiment; the values are the memo's, not calibrated.
- **QB spy (QB_SPY_RESEARCH section 4 and the man/rush follow-up):** buildable and built for zone, then man and rush, within a 2,048-byte owner.
- **Music in all modes (music tiers 4a and 4b):** the shared player is buildable and built; per-screen routing is bounded-proved, not witnessed.
- **MyCareer space (MYCAREER_SPACE) and abilities (ABILITIES_SYSTEM):** both buildable in a first version; both built and off by default. The in-game mode (M1) is designed with its native prerequisites proved; M2 and M3 are not built.
- **Modern 2K naming:** buildable as fixed-span text; built with a preview; MyNFL witnessed.
- **Hi-res textures (HIRES_TEXTURES_RESEARCH):** the compiler is buildable and built for six families; the 64 MiB headroom question cannot be answered statically.
- **Roster storage growth (STORAGE_GROWTH design):** widening the 65-pointer team prefix in place would shift every field from +0x104 and change every stride; the versioned reserve overflow in a grown arena was the right shape, and the arena growth above is that design built.
- **Playoff editor (Discord report):** two real defects, both fixed.
- **ESPN Anniversary (Noah's two questions):** the moments load shared historic roster files, not the live teams, so the rosters are editable through them; more than 25 moments is possible in the walker but refused until the profile's completion bits are witnessed.
- **APF 2K8 into 2K5 (Noah's question, researched at the end of the beta):** APF's 5,884 animation definitions share only 632 names with 2K5's catalogue, and the APF frontend rig (17 rotation and 6 translation channels on 21 joints) does not fit either pinned 2K5 embedded destination (23 rotation words), so no animation converter shipped. Plays are the strong path: 4,910 of 4,948 APF play nodes survive endian conversion and a 2K5 re-encode exactly (the 38 failures are one opcode that loses operand bits). Twenty-five ordinary rating fields transport exactly. Seven penalty curves and the 17 draft weights are byte-identical in both games, so there is nothing to gain there. Tackle, blocking and coverage systems are code and would need deliberate 2K5 re-implementations. Ranked next builds: selected APF play translation, an APF legends ratings preset, one celebration retarget, one recovered blocking rule as an executable owner, an APF camera framing preset. Memo: APF_TO_2K5_PORT_RESEARCH.md.
- **Community Blender stadium add-ons (importer v0.11.1, round-trip exporter v0.3.0):** reviewed and withheld, as above.

### Try first

If you play one thing from this beta, make it a game on the Experimental preset: the kickoff (v5, witnessed), the new Standard camera with Far one Options change away (witnessed), the v3 scorebar with the middle that stays and the team colours (witnessed), and Franchise Auto Save after one manual save (witnessed). Then the unwitnessed ones that need a report back: the read option with a Shotgun Zone read play, MyCareer at a position you never got to play (create MyPlayer on the MyCareer page, then Build with the setup), the empty-OLB removal on a Team Rosters screen, an ESPN Anniversary moment with an edited roster, a Team Kit imported into another project, a number sheet through the new preview, a bar painted in Scorebar Studio, the 82-stadium picker and the playoff editor. The scorebug probe matrix (`hooks` and `neutral`) is the one that needs a report back to close the freeze.

### Commit index (every commit since beta 60, newest first)

The beta-61 squash (cf349b7) is RC85's. Everything below is beta 62; the paragraph each one belongs to is named in plain words.

- Kickoff: 127cae5 v5 (receiving stance, nearest-coverage blocks); 10f8c7b v4 (hold from lineup completion); b167472 v3 (held collision and pose writers); eb3a1fc v2 (hold, nearest blocking, card fit); 4be60f7 fixes A to D (eligibility, ready animation, return assignments); 2a74112 return-blocking writer wired into Build; 33c2448 cave gate declares the v2 hooks for the relocated variant; b2948b8 allocator projection pins the separation hook only with a kickoff owner; ae99298 the historical v3 suite pinned to its recorded union.
- Cameras: cf24305 v4 (the new Standard starts games and practice, MyCareer detects the owner by its spectator hook); d5f75b3 camera v2 and MyCareer any-position wired (help text, registry, pins, manifest 13); 79fde2c v2 (paired Standard and Far, bounded pass pullback); de74ec0 the Far owner wired; e5007fc the Far owner (select Far at entry, raise framing above the scorebar); 75bbd8b manifest after the Far landing.
- Scorebar: 0599e4e v3 landed (help, availability, allowlist, registry, manifest 20); e202ce4 v3 (middle stays, team colours); d9e5cc4 v2 bar, kickoff v4 and the hub art landed (help, pins, evidence inventory, manifest 18); 9c5050e v2 (clocks, event overlap, live team identity); d458db2 the freeze investigation (native completion traces); 5639034 manifest 16 after the loop landing; cd9b291 provider closure pins the fonts module; 059b52a loop iteration 773; 970afa0 the exact default wired (allowlist, closure, help, pins, manifest 14); f966f49 the exact default with byte-identical v10 folder builds; 5f7d412 and 75be275 the recorder fix for grown-page declared edits and the manifest after it; 1749663 manifest after the template landing; 477443e provider closure with the template compiler; 80d055c the repaintable template wired (folder field, preflight, allowlist +183, registry 109); 31c0f93 v10 and the repaintable template; ddec83f the Raiders at Texans reference frame; 6bcb285 the Fable broadcast template; 9ffe939 manifest after v9; f263cd0 v9 help text; 315909d v9; 331e04d the native static rendering audit and the runtime boundary; b7bac4f the projection repair and the freeze probes.
- Scorebar Studio: 1606ec9 the page wired (navigation, handler, allowlist, PNG catalog, closure, registry 110); 16c672a the page and its model.
- Franchise Auto Save: 304e08b wired (dispatcher, Build plan, shared options, packaging, registry 111, manifest 17); e724eac the owner.
- Franchise Practice exit: 1e1b239 v2 (launch unwind keeps the Coach's Desk); 35decfc release text after the witness; b5301a7 v1 (exit through the retail game screen); d1eb0f5 manifest after v2, kickoff and the scorebar audit.
- MyCareer: 3fffba0 supersim and draft-start proofs; e38e5fe the hub backdrop from the Crib skyline; 766da45 the hub art, atlases and checker; 2f2a29c the occupied-save audit; 824cd2b the in-game mode design (M1); e3b76d0 the Game Modes route and any position; 305b172 screen guards and pairwise composition; 6e589d6 XBE gates apply the modern naming explicitly; bf09526 the first MyCareer (quarterback) and the Crib movie cut.
- OLB: f96e1da follow-ups (final pass guard, pins, manifest 22); 3cdb41c wired (build passes, keep switch, rows, status, registry 112); 5a200be the removal after a complete roster scan.
- ESPN Anniversary and historic rosters: 98d1c6a the real-roster option and the number-sheet fix wired (manifest 24, registry 114); 07dcc67 the real-roster data; b6f3ef3 follow-ups (pins, manifest 23); 927da9c the editor wired (Rosters subtab, Build pass, rows, registry 113); 0978719 the authoring backend and panel; 248d210 the research.
- Rosters save to disc: b5650f3 kickoff v5 follow-ups with manifest 25 and the save-to-disc wiring (registry 115 rows); ba5ef62 the Xbox save roster export for the current disc.
- Team Kit and number sheets: 76434d6 the import receipt wired; 12d2773 cross-project imports and the decode cache; e871d65 the coverage mips, shared palette and encoded preview.
- Discord bugs: e0aca65 batch 2 wired and the sweep finds; f315249 batch 2 (editor fixes and gameplay verdicts); 24899d1 batch 1 wired; e03137b batch 1 (ten editor fixes).
- Build choices: c450b2d an inspected source keeps its choices; 35ab69c the empty restore keeps them and the crest master tolerates legacy modifications.
- Sweeps and CI: 902a261 (no bare `os.getuid` in the open-file probe, the coverage test names the Standard caption); 3e41c7e provider closure count follows the destination pin; d6d848b manifest 15 after the bug batches, camera v4 and the sweep; f1695a0 the five sweep failures; 661b77e the practice-squad Unicorn fixture maps the grown pages; ffb4ce5 the recorder consults allocator reservations only on a grown image; eeff463 manifest after kickoff v2; e997a8e Windows CI (ELF32 probe, LF envelope); 945658b macOS memory-ceiling skip; ea2246b CI on Windows and macOS; daff30c the seven CI failures; 744319d the APF gate's registry count; 0f27157 manifest after the Hi-res check repair; 0abd21c the beta-61 integration test; 63d2587 the Hi-res family check; 46430e9 the VC-LZ classification; f371972 the Windows tester triage; 5f5b504 the audio test temp dir.
- Release text: 26b0d3d the held ship branch (first witnesses); d26e17e version 1.0.0rc86, tag beta-62, the first RC86 changelog, notes and status.
- Disk space: 394d058 the real scratch bytes plus a margin instead of the 100 GiB floor.
- Research: a6c3168 the Blender add-on audit; 839f1d2 the APF port research; c0346ad the deep-zone audit; 98ef185 the calendar delivery review.
- Wave-B owners: 7812a78 the roster arena growth; 314fc58 its prerequisites only while retail; fcbd19f read-option and screen-hooks composition; c809769 the hi-res families; c2748b9 the playoff editor; 9852858 read option v2 (mesh controls, native RPO handoff); 85ee5a8 modern naming; 6f6c134 music routes and playlist validation; 95dee5a QB spy man and rush; ff3931a screen hooks; 9f7bb57 the Guardian overlay; a1cd0d9 stadium texture round trips; d62f1e6 animation imports; 372c5ba Senior Bowl preparation; 0cb20ff franchise 2026 host rules; db6981f the read-option core; 288ba65 defensive try stats; 8a4db28 widescreen v3; cea907a the rules library and Info tab; de8972a momentum collisions.
- Batch-1 owners: 490b3c1 the scale-out; 6489f9f the hi-res pilot; 76eeb82 the levers; 7109aae roster styles, 2026 names and ages; f88d3ee the 82 stadiums; 3d931b6 chained modpack growth (the experimental export) and bounded disc test memory; 125a044 owner ordering; 26677cd provider repin.
- Integration: b7e5224 integration 3; 6336d22 integration 2; 5a0eac1 its follow-ups; de4e038 the QB spy pack collector; 8cdcf80 integration 1; 773a93c, 12a11830, 6b1939e, 12df680 and 051ded3 the five WIP snapshots.
- Gates, unions and pins: 7d46618, 1e1871d, 05d3ce9, 97d4c5d (gate declarations and union repairs); 8732c26 and 03ee723 (scale-out test sizing); 855e77c (one dormant union); bef5fb9 and c2e3e2c (wave-A reconciliation and fixups); 40ef8ab (probe base without a preset option); 91efa7c and 5fd05a7 (registry 95 pins); 0949287, 2efaa2d, ad25de3, 3e4a068, 04a398c, 45766f4, 21111a9, aba137d, 659290e, b83ef70 (manifest regenerations); 032a20d, ebb8b7e, 40f95f1, 57c9e30, 1b6f19c, 10be6df, 3aa217a (allocator and provider pins).

## v1.0 RC85 — defense Create a Play, the Music tab and 200-track banks, the Momentum option, Rosters locks / reserves / abilities, the reference scorebug with real logos, and the allocator that makes native features possible

Beta 61 was built almost entirely by GPT-6 Astra under Claude's review: research memo first, build session second, one
integration session per wave on the stack. Every patch passed the retail byte pins, both executable safety gates
(memory writes and cave references, now composed with every owner in both orders), a real image build of the
experimental preset, a second real build with every opt-in switched on, and the full standalone CI loop. Nothing in this
section has been played in xemu or on a console unless it says so; every new option is labelled experimental and
defaults to off or retail in every preset unless stated.

- **Owned executable space: two code pages and one writable page past the retail image, plus a 64 KiB read-only
  section (experimental, default off).** Every native feature people asked for this year stopped at the same wall: the
  free-space oracle certifies no unused code in the retail executable. Beta 60 grew the executable's final read-only
  section for the SPECIAL tab, and Noah witnessed that disc booting. This beta generalises the idea:
  `nfl2k5_xbe_space.py` appends new section descriptors (two executable, one writable, one read-only) beyond every retail
  section, hands out named, deterministic allocations per owner (a replay checks the same request set), records them in
  the reservation manifest, and the disc writer appends the grown executable and repoints its directory entry as before.
  The witness for the loader is `kickoff_relocated`: the complete 1,939-byte dynamic kickoff moved into the new pages
  with all eleven hooks retargeted, so if kickoffs still line up on a disc built with it, code in the new pages runs.
  Capacity after this beta: 6,501 bytes of owner code across the two code pages, 3,242 bytes of state in the writable
  page. Built by Astra; both allocator flags stay off in every preset.
- **Create a Play for DEFENSE, and a modern defense pack.** The Defense family joins the wizard and the Play Designer:
  native donor formations and personnel, eleven slot assignments with man, zone landmark, rush lane and exchange-script
  choices, mirror preview, capacity display and refusal at the smallest book budget. Presets build Cover 0, Cover 1,
  Cover 2 Man / Hard / Soft, Cover 3, four-deep spot quarters, Cover 6 split-field, a five-man replacement Fire 3 and a
  four-rush replacement 3 from retail building blocks; Tampa MLB drop and a Double A look are experiments. The
  `softdrink_modern_defense.2k5book` pack installs ten core calls into all 32 books plus GEN and reference (it replaces
  plays, never appends: eight books sit at the 270-play cap). A Spy assignment writes the legal shallow-middle-zone
  donor and records spy intent for a later runtime; the UI says plainly that a true spy is not here yet.
- **Read option and RPO.** Five stock plays (MIN 24, NO 57 and 66, PHI 175, TEN 144) are real conditional speed options,
  and retail has a generic branch on an opponent's position and velocity. The studio's play writer used to strip the
  branch flags on any rebuild, which quietly turned an option into a straight handoff; fixed, with all five options
  byte-exact through clone, mirror, retarget, pack and import. Conditional nodes now show honestly in the inspector and
  designer, and experimental Speed option, Zone read and RPO presets plus a small option pack ship with the same
  "position and velocity read, not a dependable modern read yet" label.
- **Screen passes: measured timing levels and a real screen preset.** Every stock screen that uses the retail hold,
  release and block grammar (64 of the 129 named screens) can take one of four timing levels: A holds the line 0.8 s
  instead of 0.5, B shortens the quarterback's nominal drop from 10 to 7 yards, C sets an explicit 0.6 s pass delay, D
  combines them (the experimental preset uses D). Only declared assignment lengths change; shared chains and node
  budgets are enforced per book. The Create a Play HB Screen generator, which gave all five linemen permanent pass
  protection, now authors the stock sequence with HB, WR and TE variants. No hook code; Noah's paired-snap witness
  decides whether that tier is needed.
- **★ Rosters: Locks, Reserves, Abilities.** A Locks column (Rank, Side, KR1, KR2, PR) uses the new depth-lock record
  bits so the weekly auto-depth keeps your tackles, guards and returners where you put them (LT/LG and RT/RG labels,
  conflicts diagnosed before saving, an Unlock action). Every NFL team gets a Reserves group with the same cards and
  filters; Promote and Demote are one atomic host transaction (53 active, 12 reserve, 65 total, salary recomputed by the
  ported integer helpers, journal replay, signed-copy write). An Abilities card edits the data-only flags (Speedster,
  Right-Stick Moves and the phase-two move bits) with the honest label that they have no gameplay effect until the
  runtime ships. The franchise view now builds from the composed save bytes and knows the configured starting year.
- **Depth-chart locks (executable, experimental preset).** Six in-place rewrites in the depth-chart routines: moving a
  player on the depth chart or confirming a returner locks that choice in his record and the weekly sort keeps it. No
  cave, no runtime variable. The module recognises both the retail rows and the shipped SPECIAL layout.
- **SPECIAL tab fixes (Noah's first look).** Third-column names were never drawn because thirteen rows at the retail
  pitch summoned both scrollbars and the sheet's frame lost two pixels; the row pitch is now 25 and the label column 57
  pixels, so all thirteen rows fit without scrolling and every column draws names. Rows are now `KR, PR, K, P, LS, LGUN,
  RGUN, NCB, DCB, SLWR, GAD, 3DRB, PWRB` in that order.
- **Practice squad in the game, part 1.** The Coach's Desk lists Schedule before Practice, and Free Practice in Franchise
  (modes 0 to 2) draws reserves into the disposable practice roster, so a practice-squad player can be practised. The
  reserve list, Promote and Demote inside the game wait for the native screen.
- **Franchise beyond 30 seasons (experimental).** One signed byte at `0x2480CD` (`1E` to `7F`) lets the franchise run
  to index 127, 128 seasons. Both save writers accept indices 0 to 127, the birth-year codec drops its fixed century, and
  the Franchise tab shows the raw index beside the ordinal. Dates and ages after 2099 are not repaired yet; the label says so.
- **Guardian caps, route B (experimental, opt-in).** Helmet C's low and high shells are sculpted into a cap inside their
  fixed spans with zero archive growth and identical wrappers; one test uniform (Detroit current away) gets a neutral
  quilt texture. Every C wearer shows the cap while it is on. Per-player caps are a later job.
- **Music.** Two tiers. First, a menu policy: a four-byte pointer swap plays the 59 jukebox songs in the menus, fourteen
  unlock-key fields make every collection available on a new profile without Crib purchases, and an optional UserList
  policy uses the same bank. Second, the Music tab: 66 core rows (7 menu recordings and 59 jukebox songs with their
  linked mono stadium twins) plus 20 presentation beds, drag a WAV, MP3, FLAC or OGG onto a slot or the list, automatic
  fit to the slot's exact length with RMS level matching and a 50 ms end fade, source and current playback, export, one-
  click Restore and shared undo. Third, any-count and any-length banks: a transactional rebuild of the outer archive
  with named XDVDFS pack writes (grow and shrink), a new format-2 `file_shrink` operation, a 64 KiB read-only section for
  the jukebox titles, artists and durations, and a synthetic 200-track menu bank proved on four real image builds. Twelve
  jukebox tracks are spoken outtakes and are named as such.
- **Scorebug: the reference bar, with real team logos and live events (experimental).** The bar is rebuilt from the SVG
  design to match the broadcast reference: rounded frame at the bottom centre, team panels, big white scores, timeout
  dashes, a red down-and-distance pill over a white quarter, clock and play-clock strip, and the literal ESPN NFL mark
  top right. A runtime owner in the new pages binds each panel to the current teams' logos (appended as ordinary native
  textures the game's own loader registers), dims timeout dashes from the real counts, flashes a score change, drives the
  native slide on a new down, and colours the play clock under five seconds. The scorebug option itself is now off in the
  advanced preset until witnessed, on in experimental.
- **Momentum (experimental, off in every preset).** Retail already has acceleration, an Agility-based turning limit,
  weight-based acceleration and velocity and weight in contact, which corrects the acceleration ramp's old "retail has
  no acceleration model" note (docstring fixed; behaviour unchanged). The option tightens fast cuts through the 44-byte
  turn record, adds consistent braking when the stick releases with the run animation still coupled, and, behind its
  own flag, a bounded run-up bonus to Break Tackle.
- **Defensive two-point returns on tries (experimental, opt-in).** After a defensive possession on a try the play
  continues; a return to the end zone scores two for the defense through the game's own two-point routine; kickoff
  ownership and the packed scoring history are corrected; a try safety scores one; play-by-play distinguishes the
  events; the CPU tries to return. Not implemented: the defensive-conversion box-score row (a diagnostic tally only).
- **Deep-zone corners stop turning their backs (experimental, opt-in).** The zone-drop initializer gives a defender
  aligned at five yards or less a throttle of 1.0, which selects the running animation, while seven yards gets 0.84 and a
  backpedal: the Cover 3 exploit the Discord described. An 80-byte owned wrapper caps the initial drop for deep-zone
  corners at the backpedal band. Ball reaction and interceptions are unchanged by design.
- **Animations workspace (experimental).** Catalogue of archive and embedded animation resources, native frame data,
  a skeleton scrubber, glTF export with the native sidecar that keeps every byte needed to reconstruct the clip, and a
  constrained existing-clip writer whose import stays disabled until its gates pass.
- **Windows path-length fix.** A Windows user's whole-kit import failed with "no such file" because the temporary file
  name during an atomic write pushed the path past Windows' 260-character limit. Every atomic writer now uses a short
  temporary name, the Windows-only writers go through the `\\?\` long-path prefix, and the message names the limit.
- **A local Windows tester.** `packaging/windows/local_windows_ci.py` runs the CI test matrix under Wine with the
  installer's own pinned Windows Python and Qt, so a Windows-only failure takes 35 seconds to reproduce instead of a
  30-minute GitHub round trip. It reproduced the beta-60 handle bug exactly. Two Wine facts learned on the way: Python
  cannot start when its stdout is a plain file (it needs a pipe), and Wine re-applies TEMP from its registry.
- **Under the hood.** The cave manifest records every owner including the grown pages; provider closures pin every new
  module; the release and runtime gates cover the new tabs; the Playbooks panel offers the defense and option packs; a
  standalone `validate_beta61_integrated_features.py` runs every new capability's checks.

## v1.0 RC84 — ★ Rosters does what Finn's did (real saves, Franchise tab, membership, templates), dynamic kickoff, slot / nickel / dime, practice squads, career stats, simpler words everywhere (2026-09-04)

- **Mod files are modular now (format 2): a `.2k5patch` can carry anything, including a change that resizes the disc.**
  The old patch format could only carry same-size, in-place byte edits, so the SPECIAL depth-chart tab (which grows the
  executable) could not travel in a shareable patch. The format is now an ordered list of typed, self-verifying operations
  (in-place byte runs, an executable-grow that replays the appended page and the one directory repoint, and named
  file-replace / file-grow), each with its own before-and-after hash, a reader-version stamp so an older Mod Studio refuses
  a newer pack with a clear message instead of misapplying it, and a copy-then-rename apply so a failed patch never leaves a
  half-written disc. Old packs keep working unchanged, and a new-format pack that only edits bytes produces exactly the same
  disc the old format would. The upshot: the SOFTDRINK Experimental patch now includes SPECIAL, and no future feature will
  hit "the patch can't carry this" again, it just adds an operation type. Built by GPT-6 Astra; verified applying to a retail
  disc byte-for-byte.- **The Playoff Picture, the Playoff Tree and SportsCenter's playoff previews now show the seven-seed format.** Noah's
  first look at the pre-release disc found the franchise's seeding preview and the recap segments still describing the
  retail six-seed picture while the bracket itself played the 2020+ format. Built by GPT-6 Astra and now part of the 2026
  season step: the Playoff Picture always lists the seven projected qualifiers with a visible 7, the Playoff Tree binds
  all thirteen postseason games (three wild-card boxes per conference, headed "AFC: 7 Seeds / Superbowl / NFC: 7 Seeds",
  no fixed connectors because the wild-card winners reseed), SportsCenter admits the seventh seed's status and compares
  the seventh team with the eighth on the bubble, only the #1 seed is ever labelled "#1 Seed / Bye" (an older save's
  stale second-bye flag is ignored), and the durable seventh seeds ride in the wild-card slots of the grid so save and
  reload keep them. 605 bytes, no new cave; proved by bounded execution of the presentation callbacks through complete
  wild-card rounds with upsets. The recorded narration was not touched. Unwitnessed on screen.
- **Fixed before release: the star under tagged players never drew.** Beta 58's star patch widened the controller-
  indicator gate so a tagged player was queued, but the game's indicator pass marks every CPU body and skips the whole
  drawing branch for them, so nothing appeared under anyone. The patch now runs its own pass after the game's: for every
  player on the field whose roster record carries the tag it draws a closed white five-point outline at his feet, hollow in
  the middle, whoever is controlling him, in games, practice and franchise, following the same HUD and coach-camera
  visibility as the ordinary circle. Proved by bounded execution of the real queue, decoder and model-selection routines
  and of the live-game roster copy (the tag byte survives the load). The tag bit is the same one the future ability gates
  will read. Noah's first look confirmed it draws; a second pass made it bold enough to read on a far receiver:
  radius 108 with a thick white band and a near-black border drawn underneath for contrast on turf and yard lines.
- **Fixed before release: the dynamic kickoff's coverage men lined up beside the kicker.** Noah's first play of the
  pre-release disc showed the ten coverage players standing at the kicking 35 with the kicker instead of on the receiving
  40. The playbook data was right; a retail pre-snap clamp (0x183F60, called from the selected-play target routine)
  replaced every coverage man's downfield target with the tee minus his stance clearance. A six-byte hook now bypasses
  that clamp for the ten on-field coverage slots of a normal kickoff only, and the hold starts at the engine's ready
  state rather than at the ball launch, so nobody drifts between line-up and the kick. Proved by bounded execution of
  the real coordinate readers against all 36 books in both directions; still unwitnessed in game until Noah's next play.
- **Simpler words everywhere.** A usability pass over every page for someone who has played 2K5 and maybe used
  Flying Finn's editor but never a mod studio: one set of names (Open game disc…, Open project… / Save project,
  Game disc (.iso) / Save disc copy as, Make my disc, Make disc from project, Make disc with these changes, Save disc
  copy… / Save Xbox save copy… on ★ Rosters, Set up xemu… / Play latest disc in xemu), short labels with the story
  under Details and a badge that says when a change needs the full disc, is already on the disc, or is not yet tested
  in-game, and the RSA sentence replaced by "For xemu; original Xbox support is not provided." Opening a disc now
  fills every page that has its own source field (Build, Game Fixes, Position names, Throw, ESPN bar, Commentary,
  Replace a Sound, Bump Maps, ★ Models, Share) through that page's own reader, suggests a distinct copy name beside
  the disc, and loads ★ Rosters on first entry without ever resetting an edited roster; Getting Started's Start
  SOFTDRINK Basic ticks the preset once the disc has been read. The Build tab puts the presets, the output name, a
  selection summary and Make my disc with a visible blocker ahead of the option list, fits a 1366-px window, and
  reaches every BuildPlan field (manual arc, commentary rows, playbook packs, mod name / author / notes were never
  on it; 7-on-7 stays reachable but disabled). Gameplay lands on Game Fixes with the research tables under
  Reference (read-only); Saves & Sliders moves there from Uniforms. Share reads Export mod file / Install a friend's
  mod with plain states. Tab titles no longer clip and lone ampersands no longer vanish. ★ Rosters keeps Finn's
  layout; it says Est. OVR, units, Position names, a readable contract line, and treats an exported roster-edits
  file as a snapshot that goes stale after the next edit. Nothing was removed and no writer changed; the record of
  the pass is `UX_EXECUTION_REPORT.md`.
- **Practice squads in franchise: 53 active plus up to 12 reserves (Experimental).** Built by GPT-6 Astra: when the
  CPU's season gate cuts a 65-man roster to 53, each team now keeps up to twelve of the players it cut as team-owned
  reserves, in the same 65-slot roster table the game already carries through the off-season (three spare bytes mark
  the list; every pointer keeps the game's own relative encoding, so saves, team exports and the season rollover carry
  them). Reserves stay off the active roster, the depth chart and the team rating, cost no cap space and keep their
  contract terms; a full 53 + 12 roster has to release players to draft. Promote and demote run as transactions in the
  executable (eight small caves, none on a live function; the first draft shared a cave with the dynamic kickoff and was
  moved). The requested sixteen-player tail was disproved: those bytes hold live cap and statistics data. No in-game
  reserve screen yet and no automatic promotion; only use reserve-bearing saves on a disc that carries the patch.
  Unwitnessed in game.
- **Franchise tab on ★ Rosters (Beta 60).** A franchise save now gets a second page beside the roster. Flying Finn's editor already turned into a franchise editor when you
  loaded a franchise save; this is the studio's version of that page, which it did not have before. Both pages write ONE re-signed copy, roster edits
  first. **Overview**: the season year (the game's `2004 + field` rule shown beside it), stage and week
  read-only, the user-controlled teams as a checkable list, the salary cap in $M with the raw $1000-unit value,
  and every team's salary against the cap. **Schedule**: the 22 × 17 grid week by week — away, home, date,
  kick-off, played, score — with Finn's Edit Game (team pickers, date, time) and Swap Home/Away; a played cell
  is refused with the reason unless you tick *Allow editing played games*; scores stay read-only because the
  quarter-score side order is a hypothesis. **Coaches**: one record per team — names and the three info lines
  (pooled strings, read-only), seasons, W / L / T, winning seasons, Super Bowls, playoff and Super Bowl W / L,
  photo and body ids, the run % playcalling split, the 23 ratings and the ten Back Field tendencies on the
  player cards' bars. **Injured Reserve**: the five slots per team, *Place on IR…* from the team's rostered
  players (Finn's move byte for byte: pointer list compacted, count byte down one, player marked, slot filled)
  and *Activate*, labelled unwitnessed; a free agent or a prospect is refused in Finn's words. **Checks**: the
  layout map by PROVED / HYPOTHESIS / OPAQUE, what the page may edit, every franchise edit since load in plain
  words and the byte ranges it touched. Undo / Redo per action, a dirty marker, and every write goes through
  the core module's writers — no offset lives in the page. Reproduces Finn's IR save byte for byte through the
  UI path; the year rule and the IR move are the witnessed parts, everything else is unwitnessed in game.
- **The SPECIAL tab: role depth charts, X / Z labels (Experimental).** Offence and both defences keep their eleven
  depth-chart rows, with LWR / RWR shown as X and Z, so nothing scrolls off the screen. The Special Teams tab is renamed
  SPECIAL and now carries thirteen rows: KR, PR, K, P, then SLOT, NICKEL CORNER, DIME CORNER, GADGET, left and right
  GUNNER, LONG SNAPPER, 3RD DOWN BACK and POWER BACK. These are views onto your existing receiver, corner, back and
  centre lists (so moving a player into a role can change another row; right gunner and dime corner share a list), and
  the same build's playbook pass lines those players up on the field: the slot man and the nickel / dime corners inside,
  the two punt gunners and the long snapper, the third-down back in shotgun and three-receiver sets and the power back in
  goal-line and short-yardage sets. It replaces the earlier thirteen-row layout that ran off the screen. Because it adds
  the extra rows without disturbing the retail table, the executable grows by 72 KB (a new read-only data page appended
  to it, the disc's directory repointed to the larger file); a real build writes and reads it back correctly, but whether
  the enlarged executable boots is the one thing still unwitnessed. Built by GPT-6 Astra.
- **Franchise saves, decoded.** The two signed saves on hand turned out to be franchise saves, and so is the one
  pulled out of the emulator's disk image, so the Rosters tab has been opening franchise saves all along; now the
  studio also reads the rest of the file. Beyond the roster arena a franchise save carries a season block (mode,
  stage, week, year, the 12 + 12 playoff seeds, divisions, which teams are user-controlled, the 22 × 17 schedule
  grid with quarter scores) and a front-office block (salary cap, the injured-reserve table, trades, free-agent
  bids, the transaction log and ledger), tiled with no gap and proved off the game's own save and restore
  routines. A read-only card under the Rosters source row now says what a franchise save is ("2011 season ·
  offseason stage 1, week 0/1 · user team(s) DET · coach Steve Mariucci (153-85-0) · salary cap $88.1M · 268/268
  grid games played · injured reserve: none"), and Flying Finn's injured-reserve move is reproduced byte for byte.
  The writers (year, cap, user control, schedule cell, coach fields, IR place / activate, re-signed write) live in
  the new core module for a Franchise tab. `tools/nfl2k5_xemu_saves.py` lists and extracts saves from a copy of
  xemu's `xbox_hdd.qcow2` (pure-Python qcow2 + FATX, read-only) and writes a catalogue. Unwitnessed edits: the
  in-game checklist is in the report.
- **Dynamic kickoff, the whole 2024/2025 rule (Build tab and Gameplay Patches, Experimental).** Beta 58 moved the
  kick spots and the line-up; this executable patch, built by GPT-6 Astra, adds the behaviour: the ten coverage men
  and nine setup blockers do not move until the ball touches the ground or a player (the kicker and the two returners
  are free), the first contact is remembered, a ball that lands in the landing zone and is then downed in the end zone
  comes out to the 20, a kick straight into the end zone is a touchback to the 35 (30 for the 2024 spot), a kick short
  of the landing zone or out of bounds goes to the 40, the CPU kicker aims for the landing zone 90 % of the time and the
  CPU returner takes the touchback 90 % of the time. Your own kicks and returns are untouched; onside and safety kicks
  and every scrimmage play bypass it. Ten hooks into a 1,939-byte hash-pinned cave at 0x2890F0 with ten runtime bytes in
  the unowned section gap; both executable gates, bounded execution of every hook in both field directions, idempotent.
  Ticking it switches on the modern kick spots and the line-up with it. Unwitnessed in game: the in-game checklist is
  in the build report.
- **X / Z / SLOT receivers and nickel / dime corners (Build tab, Advanced).** Retail 2K5 has no slot receiver:
  the inside man of a three-wide set is whichever ordinal the formation happens to name (the #1 receiver in 196 of
  the 466 three-wide formations, the #2 in 115, the #3 in 100), so the third receiver on your depth chart is inside
  only a fifth of the time. The new pass, built by GPT-6 Astra from the depth-chart research, rewrites the
  personnel groups of every playbook so the innermost receiver is the third receiver (SLOT) with X and Z outside,
  and nickel / dime sets use your third and fourth corners inside in all 71 and 38 of them. Twelve shared groups
  whose formations disagree about the inside spot by more than two yards, bunch sets and special teams keep their
  retail assignments and are listed in the build report; 456 bytes change on the disc and every play still passes
  the validator. Depth-chart rows named SLOT / NICKEL / DIME are the executable follow-up. Unwitnessed in game.
  The same delivery fixed the Create-a-Play writer's authored menu links, which were missing the populated-link bit.
- **★ Rosters: team membership — release, sign, move, swap.** Finn's core operations, as
  pointer-list edits plus the team's `+0x11C` count byte and the free-agent list's count, under the
  grid: **Release to free agency**, **Sign to ▾** a team (a free agent) or **Move to ▾** (a rostered
  player), and **Swap with…** another rostered player. Finn's own limits apply and refuse with his
  own words — a club must keep **42** players, may hold **54**, and the free-agent list is full at
  the game's own ceiling: its append helper at `0x242560` refuses at `cmp eax,0x9C4` (**2,500**) and
  never reallocates, so the list is a fixed 2,500-slot buffer whose tail past the count is junk
  (real saves carry stale absolute pointers there, which is why "the zero run after the list" is
  not the capacity). The **draft class cannot be moved** ("Invalid operation on a draft class"): two
  real saves show the game regenerates 380 prospects into a fixed record window (1937..2316 in
  retail, celebrity records included) at load and marks them itself with `+0x08` bit 4
  (`FUN_002BE6F0`), so a team pointer at a prospect would not take him out of the class. A player
  who joins a team is ranked at the bottom of his position's chain (the auto depth chart's own
  rank / side rule); a released player's record is not touched (retail free agents keep their old
  bits). Depth order is preserved, every operation undoes, the team list counts follow, **Show my
  changes** names moves as text (`IND (12 of 53) -> Free Agents`), the roster-edits document
  carries them with the destination slot and the depth bits pinned, Build's roster-edits step
  replays them as one checked transaction (a document that would break the rules on the target
  roster is skipped with the reason, the fields still land), and the CSV's `team` column now signs,
  moves and releases. Verified on the retail body (2,500-slot list, 53-man clubs, the AFC squad
  at 43, BRP at 54, alumni sides that share records with the clubs) and on the real franchise
  saves. Unwitnessed in game.
- **★ Rosters: Check & repair on load.** Finn's editor silently cleared the "headless" bit on load
  and told you afterwards. The page now plans every mechanical repair it can prove when a roster
  loads — the headless bit (`+0x0C` bit 7; the retail disc itself ships one, Carlos Joseph), a
  player on a position code the loaded scheme retired, a team count byte that overstates its
  pointer list, a duplicate entry in a team or free-agent list — lists them on the Checks tab,
  touches nothing until **Repair (N)** is pressed, then applies them with an itemised receipt and
  an undo.
- **★ Rosters: `.PlayerData` export and restore.** Finn's backup container (150-byte entries: the
  raw record, 16-byte first and last name, 32-byte college, `u16 7`) is read and written from the
  CSV menu, so community backups load. Restore matches by **name + play-by-play index** (a unique
  name still matches when the index differs, and says so; an ambiguous name is skipped, not
  guessed), never overwrites a name, brings the college back by name from the roster's own table,
  never moves a pointer and leaves the studio's star tag alone; whole record or attributes only.
- **★ Rosters: the game's own create-a-player templates, all 28 slots proved.** The 36-record
  table at `.rdata 0x5561B8` (three per position, QB..ILB; C, G, T, DT and DE have none) is read
  through its only apply routine, `FUN_00343460`, which fixes every slot to a rating byte. A `-1`
  slot is **not** "leave alone": the routine writes 75 (`mov bl,0x4B`) and clamps everything to
  0..100. **Template ▾** on the toolbar offers the player's three first — read from the loaded
  disc's executable when there is one, else the pinned retail table — and applies with undo.
- **★ Rosters: play-by-play and portrait pickers.** The two ids get a searchable list beside the
  spin box. Play-by-play: the ids the loaded roster itself uses (`Last, First`), the jersey-number
  call-outs 9000–9099, the 9100 "announce the number" fallback and the 485-name recorded surname
  bank at 9300+ — all proved in the executable; any other id can still be typed, and the wider
  audio-bank index Finn shipped from his install is not decoded. Portraits: the **4,303** portraits
  the disc carries, by id, with the roster records that select them, from the shipped portrait
  catalogue; when the catalogue is absent the spin box stays and the picker says why.
- **`docs/nfl2k5_ratings_and_styles.md`.** The ratings → animation study as a shareable document:
  the 28 rating bytes with their getters and retail distributions, the three style channels (Power
  Run Style's 33 / 66 thresholds, the Scramble parity bit at `0x002D92B1` and the mobile-QB test,
  Kicking Style as an unproved channel), Best Hand, the template slot map, and what the studio
  exposes — with every hypothesis labelled as one.

- **Career stats from your own CSV (Build tab, opt-in).** A new pass, built by GPT-6 Astra and wired here,
  imports real per-season counters for the roster's past seasons — passing, rushing, receiving, defence and
  kicking, 31 fields whose IDs were read off the game's own display-selector table (`0xA8A51C + 28·selector`);
  sacks keep their half units and field goals go by distance bucket, the way the game stores them. Export the
  roster's counters first with `tools/nfl2k5_career_stats.py` (the export carries the identity and raw-word
  pins the import demands: retail already holds 5,867 real player-seasons back to 1982, and a few keys are
  duplicated), edit values, import: nothing is invented, a season the CSV does not name is untouched, every
  written value is decoded back, and the pass refuses to grow past the stat pool. Runs right after the team
  history. The same delivery adds a lossless version-0 / version-17 ROST codec module used as the framing
  oracle for the save work above, stages release files as 0755 / 0644 (a group-writable checkout made the
  reviewed H7A encoder refuse itself silently), and says why when that encoder is refused.
- **★ Rosters opens real Xbox saves.** Every real `SAVEGAME.DAT` stores the roster the way the game keeps
  it in memory (a version-0 ROST arena with the object 0x20 bytes after its preamble, at file offset 0x320),
  not the way the disc resource is laid out (version 17, object at +0x40). RC83 only knew the disc layout and
  refused every genuine save with "no ROST block found" — the save editing it advertised had been proven on a
  synthetic save built like the disc. The document now reads both layouts through the same field-relative
  pointers, so a real save gets the whole editor (ratings, names, depth chart, CSV, global edits), round-trips
  byte-identically when nothing is changed, and re-signs to a copy exactly as before. Found by GPT-6 Astra's
  review of the two HMAC-verified saves on hand; both load with 2,547 players and 52 teams. Franchise-mode
  saves are expected to carry the same arena but none has been examined yet.
- **★ Rosters now reads a patched disc's own position scheme instead of the retail 17.** Two of
  the Build tab's patches change what a position *means*: the **EDGE rename** prints EDGE / Edge
  Rusher wherever the game said Defensive End, and the **one-pool** pass (`position_pools` plus the
  ROST reclassify) makes 16 = EDGE, 15 = the interior, 11 = LB and **retires 10** — no player on a
  reclassified roster carries OLB, and writing one back parks him in a filter row no team fills.
  The editor was showing `QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE` on all of them. It now
  detects the scheme — from the disc's own `edge_rename` / `scheme_labels` / `position_pools`
  states for an image, and from the records themselves for a save or a loose ROST body (an empty
  OLB code in the primary pool is the reclassify signature; retail ships 191 of them, and the 68
  class-generator templates are excluded because the pass deliberately leaves them keyed per enum)
  — and a **Position scheme** selector on the source row says what was found, why, and lets you
  override it. A save cannot show the EDGE rename at all, because that patch only rewrites text;
  the page says so rather than guessing.
- Everything that names a position follows the scheme: the grid, the header card, the position
  chips (one pool gains its own **EDGE** chip and "DL" becomes the interior), the Position picker,
  the Global Attribute Editor's position boxes, the validation checks and the CSV. Everything that
  *means* a position stays keyed by the **code**, the way the game keys its own per-position rating
  labels and getters: a one-pool LB is read on the linebacker card set and an EDGE on the
  defensive-end one, the jersey ranges follow the pool, and the depth chart is grouped per code so
  the edge rushers and the interior are separate chains. The header card names the card set a
  player is rated on.
- **A retired code is never written.** Under one pool the Position picker shows OLB greyed out and
  disabled, so the row cannot be picked and the picker cycles the live codes, and the card refuses
  the write anyway with a message naming the code that replaces it; a global edit aimed at a retired
  position is refused; a CSV that brings **OLB** rows onto a one-pool roster maps them to **LB (11)**
  and logs one line per row it moved; and a saved roster-edits document authored on a retail disc
  does the same when Build applies it to a disc built with the pools, so the edit lands on a
  position the game actually fills. CSV import accepts every scheme's names whichever roster it is
  reading into, so a sheet exported from a retail disc loads onto a one-pool disc and back. A player
  already parked on the retired code is still shown, and the Checks tab now says he is on a position
  no screen fills.

## v1.0 RC83 — ★ Rosters (the Flying Finn-parity roster editor), playbook packs, scorebug on every machine, disc identity, body sets, one LB group, TEAM column filled (2026-09-04)

- **Fixed: a refusal now says which disc image you handed it.** One report carried two failures
  on one file: Build & Share -> Advanced died with `pack-0 schedule template is foreign: ROST
  stored size is not retail`, and Apply refused with `2802 run(s) hold bytes that are neither
  the expected base nor the patched bytes`. Both sentences were true and neither was actionable,
  because both are the same sentence for four different images. A new identifier
  (`mod_editor/core/nfl2k5_disc_identity.py`) finds `default.xbe` and `vc_53450030/0` through the
  disc directory, hashes them, compares their positions with the retail layout, and names the
  image: **retail dump (xiso)**, **retail dump (raw/redump with video partition)**, **repacked
  disc**, **modified disc**, or **unknown image**, each with a sentence saying what to do. The
  Build tab's source line and the Apply panel show it the moment you choose a file, and every
  Build refusal, the schedule step's refusal and the Apply MISMATCH text quote it.
- **A repacked disc builds.** Retail file bytes rebuilt at other sectors are a legal image for
  Build & Share, which resolves every file through the disc directory, and the schedule step now
  finds the ROST roster resource by **searching the pack for it** rather than trusting pack
  offset 0x392800, so a rearranged pack is read where the resource really is instead of being
  called foreign because one u32 was somewhere else. What a repack cannot do is take a
  `.2k5patch`, since a patch addresses bytes by their position in the game partition; Apply now
  says exactly that and points at the Build tab.
- **Published patches stop calling themselves a "custom base".** A patch exported from a working
  copy still applies to a retail dump when every run's expected bytes are the retail bytes.
  `modpack.export` takes a retail image (`--retail-image`, or the new optional field on the
  Share page), proves every run against it, and records `is_retail_equivalent` in the manifest;
  Apply then reads "Base: retail-equivalent" instead of warning about a base that never affected
  the person reading it. Without that proof nothing is claimed.

- **Fixed: "made the patch and didn't get the new scorebug at the bottom."** The ESPN scorebug
  was the one Build step that could only run on the machine it was written on. Its inputs are
  the retail score_bug scene and three retail P8 atlases, plus our repaints of those atlases —
  and a repaint that keeps the retail alpha silhouette, the retail letter mask and one retail
  glyph cell is retail-derived, so none of it could ship under the retail-free release rule.
  The Build tab therefore showed "Not available in this build" and **Advanced silently skipped
  the scorebug**; only the published `.2k5patch` files carried those bytes. Nothing has to ship:
  every input is now read out of **your own disc image** at build time. The scene span and the
  three atlas spans are read at pinned pack-relative offsets — the pack resolved through your
  image's own file table — and checked against the audited retail SHA-256 first; the
  retail atlases are decoded to PNGs and the modern art is regenerated from them by the
  generator that has always shipped (`tools/nfl2k5_scorebug_espn_art.py`), then cached beside
  the model index in the private, disc-derived cache so a second build does no work. The result
  is byte-for-byte what this workstation builds: on the retail image, the re-laid mesh span, the
  `score_buga`, `shield_espn` and `digital_font` spans and the whole patched `default.xbe` are
  identical to a build made with the developer files present
  (`tests/mod_editor/test_nfl2k5_scorebug_source_art.py`, including a full write over a real
  disc copy).
  `availability()["scorebug"]` is now about what this build can DO, not about files on one
  person's disk, and the Presentation tab draws its planned-look mockup from your disc instead
  of saying "mockup not shipped in this build".
  - The shared **digit sheet** (`digital_font`) is drawn with DejaVu Sans Bold. Where that face
    is not installed the sheet is skipped and named in the receipt rather than silently redrawn
    in a fallback font; the bar itself never depends on it.
  - The **ticker-band atlas** (`NAVTEXTURE`, the Bottom Line strip under the bar) was hand
    painted and has no generator, so it stays out of a release build and your ticker keeps its
    retail art. The receipt says so. The published `SOFTDRINK patch advanced` `.2k5patch` still
    carries it — Share → Apply.
  - Every receipt now records where each PNG came from (`art_origin`), whether it matched the
    reference art the published patches were built with (`art_reference_match`), and anything
    that was skipped and why (`art_skipped`).
- The scorebug's texture writer and the field-pack texture writer no longer need an extracted
  copy of `vc_53450030/0` (a developer artefact that was never in a release, and whose absence
  made the step fail even here unless `NFL2K5_RETAIL_INDEX` happened to be set). Both read the
  retail template out of the image they are writing, at a pinned offset with a pinned digest, and
  fall back to the extracted archive only to tell "already imported" from "foreign bytes".
- The scorebug mockup's triangle strips are decoded from the retail scene's own command blocks
  instead of an intermediate glTF research export; the export is no longer needed anywhere.
- **★ Models: a whole player body in one operation.** A player is three scenes -- `hi_body`
  (drawn close up), `lo_body` (swapped in at distance) and `hi_head` -- so a body edit made on one
  of them alone changes shape when the camera pulls back; a modder who exported all three had no
  way to apply more than one of them. Selecting any of the three now arms a **Player body set**
  box: **Export the body set** writes all three (plus a set README) into the export folder, and
  **Check the folder** fits every edited file in one go and writes them into **ONE** copy of the
  disc. It is all-or-nothing twice over: a member that no longer fits its space on the disc
  refuses the whole set *before* the disc is copied, and every member's place on the disc is
  located and checked before the first byte moves. A set is "the three SCNE of one pack entry
  named hi_body / lo_body / hi_head" -- on the retail disc, outer 3 chunks 114 / 113 / 115, and
  no other pack entry carries any of those names. A file you did not touch is skipped and named in
  the report (exporting the set writes all three, so editing only the head is normal); a folder
  where nothing changed is refused. Measured on the real cache: a 120-vertex nudge on both bodies
  repacks to 202,224 of `hi_body`'s 202,240 stored bytes and 135,792 of `lo_body`'s 135,808 with
  the wrapper byte-identical, while a scattered edit (every tenth vertex) needs 623 bytes more than
  `hi_body` has and refuses the whole set - so body edits want to be smooth and local. Single-model
  export and import are unchanged. (`nfl2k5_models.body_sets` / `export_body_set` /
  `compile_body_set_import` / `write_import_set_copy`, new `UnchangedModelError`, `models_panel_qt`.)
- **Fixed: the roster screens listed "Linebackers" twice in a row** with the one-pool positions
  patch on (a user, 2026-09-04). The home screen's Team Rosters, the draft, free agency, the trade
  block and scouting each own a fixed position-filter list with one row per roster code -- fifteen
  arrays of 17-19 records (`0xB0`/`0xC8`/`0x110`/`0x118`/`0x120`/`0x128` bytes, name pointer at
  `+0x00`, roster enum at `+0x18`; the count handler is `FUN_0031AB20` -> `FUN_000C3CB0(team,
  position)`), and the `Outside Linebackers` record is always the one immediately before
  `Inside Linebackers` (0x539520/0x5395E8, 0x53A1F8/0x53A2A8, 0x53AF90/0x53B058, 0x53DEF0/0x53E008,
  0x53FBF0/0x53FD18, 0x5498E8/0x549998, 0x550F68/0x551078, 0x552798/0x5528B0, 0x5545E8/0x554700,
  0x559450/0x559578, 0x55EFB0/0x55F078, 0x570D30/0x570E50, 0x57FD70/0x57FE90, 0x582658/0x582778,
  0x588060/0x588178). Beta 58 renamed **both** rows and pointed the OLB row's enum at 11. The
  retired enum 10 now keeps its retail name everywhere the game prints a roster position -- the
  abbreviation table entry `0x4F26F8` stays `OLB` (0xE69C54), `0xE69D40`/`0xE69EE8` stay
  `Outside Linebacker(s)`, and all fifteen filter records keep enum 10 and their own strings -- so
  every screen shows exactly one `Linebackers` row. The behaviour half of the merge is untouched:
  enum 10 still maps to the ILB kind, reads the LB lists, has a roster target of 0 and is emptied
  by the roster pass, so the `Outside Linebackers` row simply lists nobody, the way `Fullbacks`
  does for a team without one. Removing the row instead would mean restructuring fifteen abutting
  record arrays that have no count word, which cannot be proved without running the game. The
  patch is 46 sites / 655 bytes (was 75 / 935). Also found: the fifteenth OLB record (0x55EFB0,
  the draft board) carries the retail typo `outside Linebackers` at 0xEAE8CC, which is why beta
  58's exact-text sweep renamed only fourteen and left one screen mismatched.
  (`nfl2k5_position_pools.py`, new `filter_rows` / `retail_olb_identity` readbacks.)
- **The Player Card's TEAM column is consistent now.** The shipped nflverse history covers 5,042
  of the 5,838 rows the card can show, and the rest read `--`, about one row in seven, scattered
  down a career (Noah: "make it more consistent"). Every season the data does not cover is now
  filled with that player's **own 2004 club**, read from the roster's 32 team records (each starts
  with a NULL-terminated array of player pointers before its abbreviation at `+0x108`), and
  counted separately in the receipt and the shipped match log as `seasons_inferred` so the data's
  own coverage stays honest. Result on the retail roster: **5,746 of 5,838 rows name a team**
  (was 5,042), 704 seasons over 185 players inferred, pool 36,866 -> 42,612 of 50,000. Only three
  things still read `--`: the folded "pre" row and Total, a season the roster carries no stats for,
  and the 2004 free agents (41 players, 92 rows) who are on no club at all. A CSV row always wins
  over the fill, so one line corrects any inferred season; `infer_current_team=False` restores the
  data-only behaviour. The current-season row keeps reading the player's live team in every mode
  (the getter tests `ecx == 11` before it ever looks at field 87 -- now asserted under unicorn even
  with a field-87 entry present for that slot). (`nfl2k5_team_history.py`, repinned
  `SHIPPED_POOL_SHA256`.)
## v1.0 RC83 — ★ Rosters: the whole roster editable, on the disc and in a save (unreleased)

- **★ Rosters, a new top-level page — the studio's replacement for Flying Finn's NFL 2K5 GameSave
  Editor.** Team list → player grid → attribute cards, the layout everybody already knows, over the
  **disc** as well as over an Xbox save, with the things his 2008 Delphi build could not do: undo and
  redo, dirty markers per player and per field, a diff of the whole edit before anything is written,
  a validation pass, and a source file that is never touched. Every field of the 0x54 record is
  editable: names and college through the shared string pool, position, jersey, years pro, hand,
  height, weight, date of birth, play-by-play and portrait ids, every appearance and equipment slot,
  all 28 rating bytes, the depth rank and side, and the **contract block** (value, type, signing-bonus
  tier, length, remaining, with the derived penalty shown) — which no open tool has ever edited.
  Format credit: **Flying Finn (Glen Leskinen)** and **Bad_AL** (NFL2K5Tool); the map was re-verified
  byte for byte against the retail disc before a line of it was written.
- `mod_editor/core/nfl2k5_roster_records.py`: a typed codec whose field table claims **all 84 bytes
  with no gaps** — every named field plus one explicitly named `unknown_*` field for every bit nobody
  has named yet, which is why decode → encode is **byte-identical on all 2,547 retail records** and
  on the whole 0x90F60 body. Also the team record (65 pointers = the depth order, count byte, coach
  pointer, abbreviation), the 266-entry college table, the free-agent list, and both string pools.
- **The three style channels get first-class controls** (2026-09-04 executable study). **Power Run
  Style** (`+0x4D`) as a Finesse / Balanced / Power segmented control writing the game's own 1 / 50 /
  99 over its 33 / 66 thresholds; **Throw style**, the low bit of **Scramble** (`+0x4F`) — the only
  bit test on any rating byte anywhere in `.text` (`and ecx,ebx` at 0x002D92B1), which picks the
  animation-set family and is believed, not proved, to be the throw motion — as a toggle that moves
  only that bit, beside a Scramble slider that preserves it; and **Kicking Style** (`+0x4B`),
  EXPERIMENTAL, with the three values retail uses. **Best Hand** (`+0x18` bit 1) is a checkbox on the
  Appearance tab. There is no other parity scheme hidden in the ratings: the scan is exhaustive.
- **The name pool is modelled honestly.** 65,120 bytes hold 5,094 strings with **zero** free bytes, so
  it cannot grow: the editor reuses an existing string (Finn's shared-name trick, and how you beat the
  rename limit), rewrites in place when the current string has no other user, reclaims what shortening
  a name frees, and otherwise **refuses** with the number of bytes it needed. Nothing is ever written
  outside the span the pool was discovered from.
- **Xbox saves, read and re-signed.** `EXTRA` = HMAC-SHA1(SigKey16, the whole `SAVEGAME.DAT`); the key
  is the literal Finn carries, and it is byte-identical to what the studio's own
  `nfl2k5_save_writer.derive_sig_key` computes from the retail XBE certificate (asserted by the
  tests). A save whose stored `EXTRA` does not verify is refused rather than quietly re-signed; a
  written copy rebuilds only `SAVEGAME.DAT` and `EXTRA` and copies `SaveMeta.xbx`, `TYPE` and the
  images byte for byte. Franchise arenas are found at their own `+0x2E0` offset.
- **Finn's tools, ported and improved.** Global Attribute Editor with his "show affected players"
  preview plus a condition he never had ("every QB with Speed ≥ 80 → throw style B"); Copy /
  Paste / Paste-attributes-only / Paste-photo under his rules; Advance Years Pro; Restore
  Height/Weight/DOB; a CSV twin that reads his semicolon export as well as ours; position chips;
  search by name, years pro or college; ↑ ↓ depth reorder on the team's own pointer list.
- **Build & Share**: `BuildPlan.roster_edits` applies a roster-edits document
  (`2k5_mod_studio_roster_edits/v1`) to the ROST resource of the copy, **last** of the roster passes —
  it writes named record fields and shared name strings and leaves `+0x2C`, the season-stat pool, the
  generated-name pool and the `+0x53` star bit alone, so the star-tag, team-history, prospect-name and
  position-pool gates all stay intact (asserted by a test on the retail roster). Share detects the
  edit between two discs, rebuilds the document from the rosters themselves and packs it as an asset.
- Unwitnessed in game.
- **Community playbook packs (`.2k5book`): the stock books stop being the ceiling.** Measured over
  all 32 team books, shotgun is 18 % of offensive formations and only **14.5 % of the plays you can
  call**; six books (ATL, DEN, NYJ, PHI, SF, TB) have exactly one gun formation and in all six it is
  "Hail Mary"; there are zero pistol sets and 38.7 % of every route stem is exactly ten yards. A pack
  is a small JSON **recipe** — literally the `formation_creates` / `play_creates` / `formation_links`
  rows a `.2k5mod` already stores and the writer already compiles — so it carries **zero retail
  bytes**, reviews as a diff, merges, and compiles against the installer's own disc.
  **Playbooks & Plays → Install Playbook Pack…** (and a card on Create a Play step 1) shows a plan
  table before anything happens: per entry what it replaces and whether it is OK, a conflict with an
  edit you already staged, or over budget, under a live budget bar (`plays n/270, formations n/50,
  nodes n/3,500`). The team combo offers the pack's own team, a retarget to any other book, or all 32
  at once; a retarget re-resolves every `replace_index` **by name** through
  `suggest_plays_to_replace` / `suggest_formations_to_replace` and only falls back to the stored
  index when the name still matches there. Installed entries are ordinary project edits: they show in
  the edit list, revert one at a time, and serialise into `.2k5mod` with **no schema change**.
  **Export Playbook Pack…** is the mirror, so a contributor with no dev environment can author in the
  studio and attach the JSON to a thread. `BuildPlan.playbook_packs` (empty in every preset — a
  community book is a user choice like commentary) applies them through the existing compile path and
  the receipt lists every pack, its author, its licence and every book it touched.
  **Capacity is the binding constraint:** eight books are already at the 270-play cap and there are
  only 180 spare play slots across all 32, so packs **replace, never append**, and the check reports
  net growth on every run. `tools/nfl2k5_playbook_pack.py check` runs the first six rules with **no
  game data at all** (schema → budget → the ported retail validator on every play via
  `build_descriptor` → class-flag sanity → formation legality → the donor-header rule), then a real
  dry compile when a book is supplied; it exits 0 when green, so it drops into a GitHub Action over a
  `books/` directory. Rule 4 exists because of a real bug: a pass cloned from the book's first
  offensive play (a run in every retail book) is *played* as a run — the receiver icons vanish at the
  snap and the QB cannot throw. New: `mod_editor/core/nfl2k5_playbook_pack.py`,
  `mod_editor/gui/playbook_pack_dialog_qt.py`, `tools/nfl2k5_playbook_pack.py`,
  `docs/mod_editor/playbook_packs.md`.
- **A project may now hold designs for more than one book.** The session validated a new
  formation/play/link against *every* staged create, and the compiler edits one book per call, so
  staging a design for a second team failed with "One PLAY compiler call may edit only one
  playbook". The candidate set is now filtered to the book the request touches (Build already
  grouped by book), which is what "apply this pack to all 32" needs. `.2k5book` also joins the
  release gate's allowed text suffixes -- it is UTF-8 JSON with zero retail bytes, the same class
  as the shipped `.csv` data.
- **A retarget re-slots the chains, not just the coordinates.** 29 of the 32 books order their skill
  players differently from ATL, so pointing a pack at another team permutes the eleven formation
  slots. The chains now follow their players and every operand that names a slot (Snap To, Handoff
  To, Fake Handoff, a Move's follow slot in mode 2, a conditional's read slot for kinds 2/3/5/6) is
  renumbered with them — otherwise the tight end runs the split end's route and a handoff points at
  nobody. Proved per book: after a retarget, every position kind still runs the route its author drew.
- **Seed pack `data/playbooks/modern_gun_core.2k5book`** (Modern Gun Core, CC0-1.0), authored on ATL
  with the library's own concepts: **Gun Trips Rt / Gun Doubles / Gun Bunch Rt / Gun Empty** replacing
  Split Jokers / I Jokers / Strong I Pro / Weak I Jokers, and eleven concepts — Mesh, Levels, Stick,
  Dagger, 4 Verts, Curl-Flat, Snag, Smash, Y-Cross, Slant-Flat, Flood — each replacing a play already
  listed in the formation it takes over, so it lands in the new menu with no new link. Net growth
  **zero** formations and **zero** plays (+308 nodes, 2,438 → 2,746 of 3,500): it passes all seven
  checks on ATL and, retargeted by name, on all 32 team books including the eight at the play cap.
  Not in any preset. Never launched in game.
- **Two cheap wins in Create a Play step 5.** The **QB read order** — the four ordered 1-5 values every
  Dropback (`0x06`) node carries, 171 distinct tuples over the 3,225 retail dropbacks, editable since
  the codec shipped and never exposed, so an authored pass inherited whatever the generator hard-coded
  — is now four spin boxes per pass play. The **audible slot** — `FormationLinkRequest.group`, which
  the writer has always taken; every populated retail formation carries exactly one link in each of
  groups 0, 1 and 2, the same structure proved in APF's SPLB — is now a combo on both the wizard's link
  step and the panel's "List Selected Play in Selected Formation". What the four read values select,
  and what an audible slot does at the line, are readings of the corpus, not witnessed runtime claims.
- `nfl2k5_play_library.PASS_CONCEPTS` gains **Y-Cross** and **Snag** (14 concepts), so the wizard and
  any pack can build them from the library rather than by hand.
- **Honest limits, stated on every install:** the engine has no pre-snap motion (no opcode has a
  pre-snap phase and all 88,254 retail Start nodes sit at x=0, y=0), no give-or-throw RPO (the ball
  simulation walks each chain once, so a QB who hands off cannot throw later) and no tempo. Option
  routes and keep-or-throw RPOs are accepted by the ported validator but **unwitnessed in game**.

## v1.0 RC82 — the community list: Free Practice in Franchise, Position on Edit Player, jerseys anywhere, penalties, prospect names, Pro Bowl order, laces, the star; overtime and Models UV fixes (2026-09-04)

- **Fixed: modern overtime ended after a first-possession field goal** because the kickoff after
  a score is built (and its receiving team marked as "has possessed") in the same dead-ball pass
  that applies the score, before the post-play evaluator judges the scoring play; the evaluator
  then saw the opponent as already having had its possession and ended the game (Noah, 2026-09-04,
  Situation OT1 0-0, field goal, "game ended"). The receiving team of a kickoff is now only
  *pending* until the kickoff has been played, the Situation screen's game seed clears the
  possession flags (it never runs the overtime kickoff builder), and unicorn tests replay the
  exact scenario through the real score/kickoff/evaluator code: first-possession FG -> play on
  and the other team receives, tying FG -> sudden death, second FG -> game over; first-possession
  TD + PAT -> play on; safety -> game over. Same two caves (`nfl2k5_overtime.py`, 287/300 and
  216/233 bytes), one new 5-byte hook in `FUN_0010bd80`. Unwitnessed in game.
- **Position on the first page of Edit Player, in roster mode and in Franchise.** Create Player's own
  Position picker (17 positions, ratings kept, overall recomputed from the new position's weights)
  now sits after Last Name on both Edit Player screens; Franchise opens the same screens, so a
  position change no longer means a new player. Two 28-byte `.rdata` row-list edits
  (`nfl2k5_position_row.py`). Run Depth Chart -> Auto afterwards. In every preset. Unwitnessed.
- **Pro Bowl Votes tabs in football order.** Offence, defence, then K and P (retail put the kickers
  between the linemen and the defence). One 17-pointer list (`nfl2k5_probowl_order.py`); the vote
  scanner reads each tab's own position and no other screen shares the list. In every preset.
- `nfl2k5_rdata_sites.py`: the shared retail-pin / status / apply / digest-repin helper those two
  and future fixed-span `.rdata` patches use.
- **Penalties at NFL rates + a working Chop Block toggle** (`nfl2k5_penalties.py`, advanced and
  experimental presets; `BuildPlan.penalties = "nfl"`). Every penalty slider drives a hidden
  `.rdata` curve table read through the game's interpolator (`FUN_001b0ae0`); seven of the nine are
  re-knotted in place (offensive/defensive holding, clipping, roughing window, late-hit window, face
  mask, ineligible downfield; DPI hazard/radius and the NZI zone kept) so the default 50 lands near
  NFL 2024 per-team-game rates while 0 still means none and 100 keeps the retail extreme. The
  incidental face mask (idx 25) becomes 15 yards. The Chop Block On/Off toggle, dead in retail
  because idx 9 and 10 share the Clipping-slider case of the enable pass (`FUN_000b1440`), is wired
  through a 10-byte stub (`mov eax,[0xE60064]; jmp 0xB1558`) hosted in the dead `FUN_000b4a60`
  (zero references in the retail image; both cave gates pass) -- note retail profiles carry Chop
  Block **Off**, so switch it On in Penalty Settings. **The rates are ESTIMATED** pending a
  calibration playtest (the engine has no calls-per-game number; see the getting-started recipe).
  Illegal formation, illegal contact and 12 men on the field do not exist in the engine, so no
  patch can add them. 141 bytes over `.text`/`.rdata`/`.data`; unicorn-proven interpolator and
  enable-pass runs; unwitnessed in game.
- **Home/away jerseys at any stadium** (`nfl2k5_uniform_choice.py`, `BuildPlan.uniform_choice`).
  Retail decides the colour once per game load with one rule (home dark, visitor white; the
  Cowboys white at home and navy in Washington/Tennessee) and only lets you pick the era. The
  `choice` form (ADVANCED and EXPERIMENTAL; off in BASIC) rewrites the 97-byte rule block, the four
  era handlers and the slot reset in place: up/down past the last available era on Controller
  Assign or Team Select flips that side's colour and restarts at the first era, so each side
  cycles 15 eras x 2 colours with no new button; the retail default stays the default and both
  teams may choose white. Two flip words live in the writable `.rdata`/`.data` gap beside the
  7-on-7 flag and clear with the era slots; no cave. The `rule` form (opt-in) is the same block as
  `mov esi,0` + NOPs: home always dark everywhere, Cowboys included. Practice, Xbox Live and the
  Team Select preview art are not covered. Unicorn-proven on the real routines; unwitnessed in game.
- **Laces to the posts on field goals and PATs** (`nfl2k5_kick_laces.py`, `BuildPlan.kick_laces`;
  EXPERIMENTAL preset only, opt-in elsewhere until witnessed). The held ball's orientation is not a
  constant: `FUN_001ccfa0` samples the holder's animation ball track every frame, so the hold clip
  decides where the laces point (the kickoff tee is a code constant, `.rdata` 0x50D9A0, and already
  faces the target). The patch hooks the six-byte join point of the three held-ball orientation
  paths at 0x1CD3FB (`mov edx,[esp+0x14]; mov ecx,[edx]` -> `call cave; nop`) into a 143-byte cave
  in the dead `FUN_002979f0` (0x2979F0; zero references in the retail image, both cave gates pass):
  `pushad/pushfd`, live play (`[0xE602B8] == 0xE`) and the offence's chosen formation being the
  Field Goal formation (the `[[[0xE60280]+0xC]+8]` chain with the -4 sentinel guard, flags bits 8-13
  == 12, as the kick-rules PAT fixer reads it), then the ball quaternion at transform +0x20 is
  multiplied in place by a 16-byte roll constant kept in the cave through the game's own
  `FUN_003ca150` (`q <- q x r`, Hamilton order), default `(0, 0, 0, 1)` = 180 degrees about the
  ball's long axis (`(w,x,y,z) <- (-z, y, -x, w)`), so the laces swing from the kicker to the posts;
  `apply(..., roll=ROLL_90)` writes the 90-degree variant into those 16 bytes without touching the
  code. 78 bytes of code, writes only through `esi`; `popfd/popad`, the two instructions replayed,
  `ret`. Punts, kickoffs and scrimmage carries are not the Field Goal formation and stay retail; a
  fake field goal carries the rolled ball for that play only. Unicorn-proven on the real bytes
  (rolled on live FG, untouched on other formations / dead ball / the -4 sentinel, registers, flags
  and stack transparent); unwitnessed in game.
- **Modern draft-prospect names** (`nfl2k5_prospect_names.py`, advanced and experimental presets;
  `BuildPlan.prospect_names = "modern"` or a CSV path; disc images only). Retail names every
  generated rookie and free agent from the 1990 US Census lists (James, Harold, Walter... Smith,
  Garcia, Martinez): two independent uniform draws over a 485 + 485 pool in the roster template
  (ROST body: entry array 0x72FB4, UTF-16 strings 0x8B7D0..0x8EB86), so a fifth of every class
  carries a Hispanic-origin name and none reads like a 2020s roster. The pool is rewritten inside
  its own 13,238 bytes from `data/nfl2k5_modern_names.csv` (nflverse-data 2015-2025 rosters,
  CC-BY-4.0; `tools/nfl2k5_modern_names_generate.py` reproduces it): the 433 surnames the announcer
  has recorded stay at their index (the audio id is 9300 + index) and keep their call-out, the 52
  Hispanic-origin and developer slots take modern surnames (Diggs, Chubb, Kamara...) and every
  first name goes modern. A 27-byte cave on the generator's audio-id store (hook 0x2BE7B8; host =
  the tail of the dead `FUN_000b4a60` at 0xB4A70, beside the penalties stub) keeps 9300 + index for
  surname pointers below the layout's boundary and writes 9100 (no recorded cue: the announcer
  falls back to the jersey number) for replacements. The boundary is baked from the CSV, so
  `inspect` reports `applied` only with both halves present and agreeing (`partial` otherwise) and
  the build refuses a mismatch. Correction to the study: the 272 zero bytes before the pool are the
  empty names of the 68 spare player records (136 relative pointers land there), not free space, so
  the budget is the retail span. Custom lists: `first,last`, 485 rows, `index` optional, ASCII up to
  12 characters, within the byte budget; the receipt logs every slot as kept or replaced. New
  franchises only (a save carries its own roster copy). Unicorn-proven hook (retained pointer ->
  9300 + index, replacement -> 9100), both cave gates pass, order-independent with the other
  executable patches; unwitnessed in game.
- **Free Practice inside Franchise** (`nfl2k5_franchise_practice.py`, `BuildPlan.franchise_practice`;
  ADVANCED and EXPERIMENTAL presets, opt-in in BASIC until witnessed). Retail Practice exists only
  under Game Modes on the main menu, picks two random teams and has no way in from a franchise, and
  the Coach's Desk (descriptor `.rdata` 0x522190) has no spare row: its eleven rows run Schedule ..
  Quit and the type-3 terminator at 0x52215C ends exactly where the descriptor begins. The patch
  relocates the desk's 52-byte event-hook list into a cave (the same six `(event, record)` pairs
  with event 5 last, since the dispatcher `FUN_0006E4E0` scans for the first matching event), which
  frees precisely one 0x34 row slot at 0x521EEC, writes a **Practice** row there (type 9, label =
  the retail UTF-16 `L"Practice"` at 0xE9C3BC, always visible) and moves the descriptor's row
  pointer back one row, so Practice is the first row and the eleven retail rows follow unchanged.
  The row's activate stub is the tail of the retail Front Office callback `FUN_00142910` (start the
  fade, set the deferred next screen `[0xAA2408]`) pointed at a **clone of the Scrimmage Settings
  descriptor** in the cave -- byte-identical to 0x501834 except its own hook list (Team Select still
  on event 0xB) and its own START handler. The clone's event-1 stub runs retail `cb_00148AD0`
  (Practice Type 0, the `s32` practice field) and then `FUN_000C4D70`, the game's own "the team the
  user coaches" (`[0xE5775C]` -> `FUN_000C4C50`), and puts that team on **both** sides through
  `FUN_00077AE0` / `FUN_00077B20` at Practice Type = Full Scrimmage via `FUN_000E33F0`, so mode 1
  fields your first-team offence against your first-team defence in your away kit against your home
  kit, with the live franchise roster (there is one roster object, `[0xB72918]`, and the franchise
  load already overwrote it). The START stub is `FUN_00148B50` with **one** pop instead of two,
  because the franchise entry is one push deep, so a rep ends back on the Coach's Desk. 352-byte
  cave at 0x1D82D0 (eleven dead type-tag predicates; no branch target and no aligned pointer in any
  of the 23 sections lands inside), 100 bytes of code, four tables, **no mutable state and not one
  retail instruction byte changed**; no resource or pack change. Practice is mode 1 and the stat,
  clock and injury paths are gated on mode >= 4, so a session writes no season stats and no
  injuries, and the season state is only touched by franchise setters this path never calls.
  Unicorn-proven on the real bytes (both team globals and both playbook names = the coached team,
  Practice Type and the mode word set, retail practice untouched with no coached team; the START
  stub pops once where retail's pops twice); both cave gates pass, order-independent with the other
  executable patches. **Unwitnessed in game** -- the Coach's Desk has never been seen drawing a
  twelfth row, and a mode-1 game ending inside a franchise context has never been witnessed.

- **★ Models: texture coordinates now follow the game's own per-mesh rule.** Beta 56
  decoded every model's UVs with one fixed formula (`u = (n + 1) / 2`, `v = (1 - n) / 2`,
  "verified on the referee"). The game does not. Every NFL 2K5 vertex shader that routes
  register 6 to a texture coordinate computes `oT0.xy = v6.xy * c[-89].xy + c[-89].zw`, and
  `c[-89]` is four floats the draw path loads from each SHAPE record at `+0x30..+0x3C`
  (Su, Sv, Ou, Ov), right beside the proved position scale/offset at `+0x10`/`+0x20`
  (`movaps xmm0,[esi+0x30]` at VA 0x245B9 beside `[esi+0x10]` at 0x245FD). The exporter
  now writes `TEXCOORD_0 = n * S + O` per mesh with **no V flip** (Sv is positive on every
  shape sampled). 242 of 282 stadium shapes tile (S up to 12), so seat rows, crowd,
  concrete and ad boards had collapsed onto one repeat and were mirrored: that was the
  "scrambled stadium textures" report from the community Blender add-on. The referee's own
  constant is (0.81, 1.24, 0.55, 0.18), so the model the old rule was "verified" on was wrong
  too; the fixed rule was the S = O = 0.5 special case plus a flip that merely looked
  plausible on a striped shirt. Import inverts through the same constant (`(uv - O) / S`); a UV
  edit outside `O ± S` widens that mesh's constant one axis at a time, exactly as positions
  widen theirs, and the report says so; UVs stay off by default on import. Each mesh's extras
  carry `nfl2k5_uv_scale` / `nfl2k5_uv_offset` and a `texcoord_decode` block, the file
  carries `nfl2k5_texcoord_contract`, and the README lists each mesh's tiling.
- **Models exports speak the Stadium Studio contract.** Every material, texture and image
  carries `nfl2k5_texture_id` (`nfl2k5.stadium.o3610.c0004.scene4175.texture0002`; the scene
  number is the resource's position among the disc's SCNE resources, the Stadiums page's own
  enumeration; other models use their name in place of `stadium`), images are named after the
  first material that maps them, materials carry `nfl2k5_mapping_status`, and meshes,
  primitives and nodes carry the `source_*` extras the Stadium Studio and the add-on read
  (`source_shape_index`, `source_material_index`, `source_material_name`,
  `source_submesh_index`, `vertex_attribute_descriptors`, `position_decode`). The root node is
  `nfl2k5_units_centimetre_to_metre` and the file-level `nfl2k5_unit_contract` and
  `nfl2k5_texture_contract` blocks are written. A stadium exported from ★ Models and edited
  in Blender is accepted by the Stadiums page's texture write-back. The id format and keys
  now live in `nfl2k5_models.py`; the Stadium Studio imports them. The Stadiums page's own
  export is unchanged (positions only, copied byte for byte from the private cache, so no
  cache re-derive); its contract note now records the proved UV rule and points at the Models
  export for a UV-bearing file.
- **Vertex colours no longer darken the export.** The D3DCOLOR lane is the game's baked
  lighting (mean 155/255; the shaders multiply it into the texture). Written as `COLOR_0`,
  Blender multiplied it into every material's base colour and textures looked dark and
  blotchy. The lane is now the custom attribute `_NFL_COLOR` (VEC4 float, r g b a in 0..1),
  which Blender imports as a FLOAT_COLOR attribute without touching the material, and it
  comes back through import for exactly matched vertices (an unedited file writes nothing;
  new checkbox "Write vertex colours from the file", on by default). The export box gains
  "Bake vertex colours into COLOR_0" for the darker in-game look. A `COLOR_0` coming back
  from Blender is never read.
- Export schema `nfl2k5_model_export/v2`. Tests in `tests/mod_editor/test_nfl2k5_models.py`:
  the shader-rule transform, its exact inverse under real constants, per-axis widening, the
  D3DCOLOR codec and the contract ids without a disc; with the private extraction, the
  referee and a stadium scene export `TEXCOORD_0 == n * S + O` against the raw lanes with the
  full contract, an unchanged export re-imports to the original quantised lanes exactly, a UV
  pushed out of range widens only U, and a painted vertex colour lands in the lane. Proof
  renders (Blender 4.0 headless): referee stripes, number patch and hat crest, stadium banner,
  goal-line numeral, SPORTSCENTER board, crowd and seat rows are right under the per-shape
  rule and wrong under the fixed one. Unwitnessed in game: no UV or vertex-colour edit has
  been played back on a console or emulator yet.
- **Star decal under the players you tag** (`nfl2k5_player_star.py` + `nfl2k5_player_tags.py`,
  `BuildPlan.player_star` / `BuildPlan.player_tags`; off in BASIC, on in ADVANCED and EXPERIMENTAL
  because with no player tagged it draws nothing). Retail already draws this star and the art is
  literally called `icon_controller_star` (`.string_` 0xE6C16C): `FUN_000f8e60` loads it as the
  models `controller` / `controller100` (`[0xBA28A4]` / `[0xBA28A8]`), `FUN_000f8880` puts an
  instance at a player's feet as a **world-space decal** (it adds x/z into the instance transform
  at +0x30 / +0x38 and colours it from the per-user `.rdata` table 0x4ED9A0), `FUN_000f9030` walks
  the on-field entity list `[0xE60268]` once a frame and appends the players who get one to a list
  at 0xBA2824, and `FUN_000f9320` draws them. The **only** gate on that append is `FUN_00075d40`,
  an 80-byte leaf. So nothing is authored: the patch is an **in-place rewrite of that one routine**
  -- 80 retail bytes out, 80 new bytes in, entry unmoved, **no cave and no hook** -- that keeps every
  retail answer and adds "or this player's roster record carries the studio's star bit", refusing
  once the star list is full. The tag is byte **+0x53 bit 0** of the 0x54 roster record: `entity+0x3C`
  **is** that record (`FUN_000fa270` stores it into the marker queue at 0xFA2CB and the consumers
  read its +0x14 as the name pointer, its +0x20 bits 3..9 as the jersey number and its +0x35 as the
  position code -- the studio's own record fields), and +0x53 is the second of the two bytes Bad_AL's
  NFL2K5Tool calls "padded by 2 zero bytes", zero in all 2,547 retail records. Four earlier
  candidates were checked and every one is live: +0x27 bit 0 is **contract length** (981 primary
  records set it; +0x0A/+0x24/+0x26/+0x27 are the contract block and +0x08 the Player Type flags,
  per the Flying Finn V4 RE), +0x26 bit 0 and +0x08 bit 0 the same way, **+0x23** is bits 24..31 of
  the live dword at +0x20 (an 8-bit field at bits 22..29 with a getter at `FUN_000be290` and a
  setter at `FUN_000be2a0`, plus flag bits 30 and 31), and **+0x24 bit 7** is its own copied one-bit
  field that retail data actually sets. The decisive evidence for +0x53 is the game's own
  field-by-field player clone at 0xC16CD..0xC1DDB: it names every field of the record from +0x00 to
  +0x51 and never names +0x52 or +0x53 (a test pins this). The **9-entry clamp is not optional**: the list is 0xC bytes an entry with a byte count at
  0xBA2821 and `FUN_000f9030` flushes `[0xBA2820, 0xBA2820 + 4 + count*0xC)` at 0xF92E3, which with
  9 entries ends exactly at the next global (0xBA2890), so the tag path refuses at 9 while retail's
  own answers are never clamped. The rewrite is a leaf with no push, no pop, no call and no memory
  write at all (its last act is a tail `jmp` to the pure `FUN_0017ebd0`, whose 0/1 return is the
  retail answer); both cave gates and the memory-write gate pass, and unicorn runs the real bytes to
  prove retail-identical answers for untagged records over eleven entity states, 1 for a tagged one,
  a null record pointer never dereferenced, and the clamp at 9. Tagging is a **★ Star** checkbox
  column in Text & Rosters -> Current Roster Players (primary pool only: those are the records the
  on-field entity points at) which the Build tab reads as `player_tags`; the writer rewrites only
  those pad bytes in the ROST resource of the copy, runs last of the roster passes and leaves the
  team-history, reclassify, schedule and prospect-name digests intact. Side effect by design: the
  same predicate gates the on-field name/number indicator in `FUN_00075d90`, so a tagged player gets
  that too when Player Indicator Text is on. Tags need a disc image and reach franchises **created**
  from the copy. Unwitnessed in game.

## v1.0 RC81 — Update now: the studio updates itself on every platform (2026-09-03)

- **Update now.** When a newer release exists the banner and the Help menu's
  Check for Updates dialog offer **Update now** next to the old **Get the update**
  link. The studio downloads the release file that matches this copy, checks it
  against the SHA-256 the release published (a mismatch is discarded, never
  installed), and then:
  - **Windows installer** (the Setup.exe layout): starts the new installer
    silently with `/S /WAITPID=<pid> /RELAUNCH /D=<install folder>` and closes.
    The installer waits for the studio to exit before it touches a file,
    installs over the same folder, and reopens the studio.
  - **Unpacked release folder** (the tarball on Linux, macOS, or Windows): unpacks
    the new version beside the folder, swaps the two so shortcuts keep working,
    keeps the old one as `<folder>.previous`, starts the new version and closes.
    If the folder is held open (Windows, started from the .bat) the new version is
    placed beside it under the release's own name and the banner says where.
  - **A git checkout** is never updated in place; it only gets the link.
- The update runs off the GUI thread with progress in the banner; a failure is
  one sentence in the banner and the old copy is untouched.
- The first-run disclosure now says what the check does and that nothing is
  downloaded on its own. Nothing starts without the user pressing the button
  and confirming.
- Installer template: `.onInit` implements `/WAITPID=` (SYNCHRONIZE wait, ten
  minute cap) and `.onInstSuccess` implements `/RELAUNCH`; both are inert when a
  person runs the installer by hand. Proven under Wine 9: the install held until
  the waited process exited, then `runtime\pythonw.exe` started; the control run
  without `/RELAUNCH` started nothing; a dead pid does not hang.
- New module `mod_editor/core/self_update.py`, shipped in both studios; tests in
  `tests/mod_editor/test_self_update.py` (install-kind detection, asset choice per
  product and layout, sidecar verification, tarball swap + fallback, hostile
  archive refusal, the banner flow off the GUI thread).
- **TEAM column on the franchise Player Card.** A new executable patch (Build tab, Gameplay
  Patches page, both SOFTDRINK presets; `.2k5patch` carries it) adds a frozen TEAM column next to
  Yr on the Player Card's season-by-season stats. The current season shows the live team; every
  season rollover records the team the player finished the season with (field 87 of the game's own
  per-player history stream, written through its own writer), so past seasons show that club from
  then on. Seasons that ended before the patch was in the save, the folded "pre" row and the Total
  row read "--"; a mid-season trade shows the season-end team. Six column lists get the new
  pointer in place; the caves live in the unused tail of the dead `FUN_00046ee0` (0x47220..0x47420).
  Unwitnessed in game; the caves run under unicorn in `tests/mod_editor/test_nfl2k5_team_column.py`.
- **Real team history for the roster's past seasons.** The Build tab's "Real team history" toggle (ADVANCED and
  EXPERIMENTAL presets; disc images only) writes the real club of every past season the retail roster carries stats
  for into the roster template's own history pool (field 87, `data/nfl2k5_retail_team_history.csv`, generated from
  nflverse-data, CC-BY-4.0: 1,148 of the 1,325 retail players with history matched, 5,068 of 5,867 season rows, 86 %;
  5,042 rows land in the pool, 36,866 -> 41,908 of 50,000 dwords). Only franchises created from the copy show it; a
  user CSV (last_name, first_name, birth_date, season, team) replaces the built-in data and rides in the `.2k5patch`
  as `assets/text/`. Relocated franchises show the 2004 abbreviation (Oilers -> TEN, LA Raiders -> OAK). The pool
  writer runs after the position-pool and 2026-schedule passes. Unwitnessed in game.
- **Boot logo kept decodable.** Several executable patches keep code and constants in the XBE
  header's boot-logo bitmap (0x10A10..0x10CC2). The game never reads it, but the kernel draws it during
  the boot animation, and a bitmap full of code decodes to nonsense (a user's investigation of a
  freeze at the Xbox logo flagged exactly this). Whenever a cave has taken the bitmap the builder now
  copies the retail logo into the header's zero padding (0x10CD0) and points LogoBitmapAddr at the
  copy, so the kernel decodes the genuine 100 x 17 logo; the caves are untouched.
  `mod_editor/core/nfl2k5_boot_logo.py`, reported as `boot_logo` in every XBE status.
- **Disc names always end in .iso.** A save name typed without a suffix in Build or Apply produced a
  file xemu's picker could not see; a bare name now gets `.xiso.iso`.
- **In development, not in this release: 7-on-7 practice.** A fifth Practice Type that plays 7-on-7
  sets from the practice playbook is built and tested (executable patch, book writer, three runtime
  bugs found and fixed through xemu's debugger: a flag in read-only `.text`, menu links without
  bit 15, a cave over a live function). It reaches the play-call but has not been witnessed through
  a snap, so it is hidden in this build (`mod_build.SEVEN_ON_SEVEN_RELEASED`).
## v1.0 RC80 — ★ Models: export any model to Blender and back (2026-09-03)

- **New: ★ Models.** Every 3D model on the loaded disc (players, helmets and face
  masks, balls, referees, coaches, cheerleaders, crowds, props, the Crib, menus,
  trophies, stadiums; 4,616 scenes, listed by name in about a second) exports as a
  glTF 2.0 file that opens in Blender: triangles, normals, UVs, vertex colours,
  the embedded textures the game draws it with, a skin with the game's joints for
  every animated model, morph channel names, and a vertex-index lane. A README
  beside each export says what can change.
- **Import an edited glTF/GLB.** Move vertices freely and bring the file back:
  the game's vertex count, triangles, bones, weights and every other byte are
  kept; positions (and normals / UVs for exactly matched vertices) are re-encoded
  into the game's fixed-point lanes, the encodable range is widened when an edit
  needs it, Blender's re-ordered or split vertices are mapped back through the
  index lane (or by order / nearest vertex with a warning), the resource is
  rebuilt into its retail span with the wrapper untouched, and a COPY of the disc
  is written with the pack located through the disc's own directory. The report
  says exactly what changed before anything is written.
- The disc reserves a fixed compressed size per model; the importer packs with an
  optimal-parse VC-LZ encoder that beats the game's own packer by 0.4 to 1.3
  percent, which is the headroom an edit needs. Very heavy edits can still exceed
  it and are refused with the arithmetic.
- Not yet: adding or removing vertices or triangles, new bones or animations, and
  body-type / face morph deltas (channels are listed, not editable).

## v1.0 RC79 — every archive pack found through the disc directory (2026-09-03)

- **Fix: Build → Advanced on any dump of the disc.** A legal USA retail `.iso`
  laid out differently from the rip this studio was developed on (a raw dump
  with the video partition in front, or an image rebuilt by another ripper)
  failed the 2026 season step with `pack-0 schedule template is foreign: ROST
  stored size is not retail` while Basic built fine. The schedule step and
  every other pack writer read `vc_53450030/<pack>` at a byte offset measured
  on one image; they now resolve the pack through the image's own file table,
  exactly as `default.xbe` always was. Disc detection locates the game
  partition instead of assuming it starts at byte 0.
- The ESPN scorebug status no longer aborts the Build panel on machines
  without the developer-only retail scene file; it reports "not available".
- Verified with identical Advanced builds from the retail rip, a redump-style
  image and an extract-xiso reordered image, also with the POSIX-only `os`
  members removed (the simulated-Windows check).

## v1.0 RC78 — Build & Share with the SOFTDRINK patch presets (2026-09-03)

- **New: ★ Build & Share → Build.** One checklist builds a patched COPY of a
  disc image (or `default.xbe`) with every executable, text and presentation
  patch, and three buttons tick a preset first: **Basic** (the 2004 game plus
  the 2K5 fixes: throw ceiling 80 with realistic flight, real Catching and
  Interception sliders, draft and free-agency AI with the Rookie Report rule,
  real returners, kicking power to ~70 yards), **Advanced** (everything modern:
  EDGE, modern kicking 35 / 35 / PAT 15, modern overtime, acceleration ramp,
  progression, arc by distance, the ESPN scorebug, scheme labels, one-pool
  positions with corrected team ratings, the Far-look camera, the 2026 franchise
  with a three-game preseason and rookie birth years) and **Experimental**
  (widescreen hor+ and the dynamic-kickoff line-up). A preset ticks only what
  the source can still take and reports what it skipped.
- **New: Share tab.** `.2k5patch` export, inspect, check and apply: byte runs
  plus your source assets and a recipe, every run SHA-verified against the
  bytes it replaces before anything is written.
- **New: Audio → Sounds and Commentary.** Replace any game sound across every
  sub-bank from a WAV (export, fit line, verify); swap a commentary line.
- Throw Distance & Arc: the arc-by-distance lob-speed table now keeps the
  retail short-game points exactly (relocated 8-point table).
- Every patch is pattern-checked against retail, written to a copy, read back
  and receipted; xemu-only, like every executable edit.

## v1.0 RC77 — Create a Formation / Create a Play, Play Designer, Throw Distance & Arc (2026-09-02)

- **New: ★ Create a Play (last navigation entry).** A five-step wizard: pick
  a playbook, lay out a formation on a field canvas (modern templates; drag a
  player to move him, click to swap or change his position — RB2 instead of
  the FB, a WR instead of the TE), choose run or pass, draw routes by dragging
  from a player or pick a job from his menu, then replace outdated stock plays
  and build. Under it, the Play Designer and Design Formation panels edit
  assignments from the game's own route/block/coverage opcodes. The PLAY
  resource is decoded end to end — eleven 14-byte formation slot records in
  signed centimetres, 29 node opcodes with bit-exact operand encoders (round
  trip on all 91,833 stock nodes), and the retail validator (chain grammar,
  side nibble, feature byte, ball-possession simulation, handoff pairing)
  ported so nothing the game would reject is ever staged.
- **Fixed: authored passes no longer play as QB draws.** The game plays a play
  as the class in its header word (bits 12–15: pass / quick game / run, plus
  play-action, trick and specials bits — 139/139 stock ATL offensive plays
  obey it). The wizard now picks its donor and header from a stock play with
  the same QB-chain shape and writes `play_flags` end to end (writer, facade,
  build validator, Playbooks panel, designer, wizard); bits 0–8 must stay the
  donor's or the build is refused.
- **New: Throw Distance & Arc workspace (Sliders & Gameplay → Throw Distance
  && Arc).** NFL 2K5 caps every throw at a distance that is a curve of the
  passer's effective arm strength, read from five `count + (x, y)` float
  tables in default.xbe through one interpolator; deep balls are forced lobs
  and the accuracy pass re-clamps the target to the bullet curve (55 yd at 99
  arm in retail), then the launch is an exact ballistic solve with no velocity
  cap. Two sliders re-shape those tables on a COPY: the deep-ball ceiling
  (55–100 yd, scaled so a 70 arm gains ~2 yd at 80 while a 99 arm gets the
  full 80) and the pass arc (slows the last 25 yards of the ceiling so long
  balls hang and climb; 40 % at 80 yd is a 5.0 s, 33-yard-high bomb). The
  panel reads a default.xbe or a disc image, previews ceiling / hang / apex
  per arm live, refuses to write when the sliders already match, and verifies
  by read-back and byte diff. Witnessed in xemu with gdb breakpoints on the
  clamp and launch: retail launches pinned at 55.0 yd; the tuned copy launched
  80.0-yard, 5.00-second balls. `tools/nfl2k5_throw_distance.py` is the CLI
  (`read`, `sliders`, `curves`, `preview`).
- The browse-only facade shown before a disc is loaded now implements the
  extended Playbooks contract; the formation/play writer test file gained the
  `unittest` entry point CI's per-file runner needs.

## v1.0 RC76 — Windows binary-open hotfix for the bump workspace (2026-08-24)

Beta 51's new file paths opened disc images, extracted packs, XBE copies and
raw HDD images with `os.open` but without `O_BINARY`. POSIX ignores the flag;
Windows opens such descriptors in TEXT mode, where reads stop at the first
`0x1A` byte — silently truncating payloads (the synthetic uniform fixtures hit
this at byte 58 of the pack). Every `os.open` in the bump-map writer, the
bump-strength writer, the save writer, and the coach-name tool now carries
`getattr(os, "O_BINARY", 0)`, matching the long-shipped uniform-color patch
route. A new AST guard fails any future `os.open` in these modules that drops
the flag. No behavior change on Linux/macOS; the Bump Maps, Bump strength, and
Saves & Sliders workspaces now work on Windows exactly as they do elsewhere.

## v1.0 RC75 — bump maps, bump strength, saves & sliders, stadium glTF loop, speed (2026-08-23)

RC75 is the biggest 2K5-side release to date: four new native workspaces or
routes, all retail-free and fail-closed, plus an editor-wide speed pass for
projects with hundreds of edits.

- **New: Jersey Bump Maps workspace (Uniforms & Equipment → Bump Maps).**
  Every one of the 634 uniform packages carries four tangent-space bump maps
  (bump_jersey, bump_pants, bump_sleeve, bump_sock). The new panel browses
  them from the entry tables (no hardcoded offsets), exports any slot to PNG,
  previews a replacement before/after, and writes it into a COPY of the disc
  image at the exact retail footprint: box-filter mip chain, NV2A swizzle,
  VC-LZ recompressed into the fixed span, wrapper preserved except the
  loader scratch word, then independently re-decoded and verified. The
  retail image itself is browse/export-only and is recognized by full SHA.
- **New: cross-extent uniform packages are editable too.** Three retail
  packages (outers 3625, 3832, 4136) cross a pack boundary and were
  previously refused. Reads and writes are now segmented at pack boundaries
  while still touching only the exact span, so all 634/634 packages are
  first-class.
- **New: bump authoring templates.** One click writes a flat-normal starter
  PNG at the slot's exact size with the retail collar/shield UV zones
  outlined and labeled on bump_jersey (front V-neck band, NFL shield tab,
  back round collar) — the positions the retail art actually uses, graded
  honestly in the metadata.
- **New: bump strength editing.** The per-material detail-scale floats that
  control how strong each bump renders live in default.xbe (jersey 0.1,
  pants 0.3, sleeve shares jersey's float, sock fixed 0). The Bump Maps
  panel now finds those sites by byte pattern, reads them, and patches a
  COPY of the XBE with the touched section digest recomputed and byte-diff
  confinement verified. Honesty: the RSA signature cannot be regenerated,
  so patched XBEs are xemu-only, and sock stays read-only (its retail
  encoding has no room for a float).
- **New: Saves & Sliders workspace.** The settings block proven at RAM
  0xE5FF80 (the first 0x2E0 bytes of Settings1 and Franchise1 saves) is now
  editable: all 21 gameplay sliders (Human/CPU Blocking..Catching plus
  Injury, Fumble, Interception) with editable/mirror/consistent write modes,
  and the Franchise1 year field for franchise saves. Output is always a
  COPY: a mutated SAVEGAME.DAT plus a fresh 20-byte EXTRA signature
  (HMAC-SHA1 with the title-static key derived from your own default.xbe),
  verified at load by the game. A CLI (read/edit/writeback) covers the same
  lane, including write-back of a save container's extents inside a copied
  raw Xbox HDD image, which refuses saves whose stored EXTRA does not verify.
- **New: stadium glTF texture loop closed.** Stadium scenes already exported
  to glTF with every game texture embedded (tagged by canonical texture id)
  and re-imported same-topology vertex moves. Now the edited glTF's images
  come BACK too: Apply textures from glTF maps each Blender-edited image to
  its stadium texture slot (by id, falling back to material name) and writes
  it through the same fixed-allocation P8 route the Stadiums page uses.
  Export → edit in Blender → apply back, entirely in the GUI.
- **Speed: hundreds of edits no longer re-parse the world.** Identity-keyed
  memoization (path + device + inode + size + mtime) now caches the bump
  index volume parse, the retail-image probe verdict, the outer-archive
  parse used by every texture adapter, the 55MB uniform-inventory load plus
  an O(1) (outer, chunk) row index, the compatibility-report digest, and the
  large-file digests the helmet/nameplate/face/field-art/portrait importers
  recomputed PER EDIT. Per-edit structural cost drops to O(1) after the
  first edit; measured ~0.9-2s per edit → sub-second across 30 edit-shaped
  cycles, with deterministic cache tests instead of wall-clock asserts.
- **Flexibility without losing fail-closed guards.** Patched-XBE and
  edited-save outputs can now be re-generated in place with an explicit
  overwrite confirmation; same-file-as-source writes, retail-image writes,
  and unverified saves are still refused outright.

## v1.0 RC73 — Create Formation / Create Play, authorized end to end (2026-08-21)

The clone-based creation writer that shipped quietly in RC54-RC56 is now a
first-class, capability-authorized, project-persisted feature, and it gained
two bounded Stage-2 steps — all inside the proved empty capacity of the fixed
0x13390 PLAY bodies (317 empty formation slots and 739 empty play slots
corpus-wide; nothing relocates or grows):

- **Create Formation / Create Play** are authorized kinds
  (`play_formation_create`, `play_create`) in the unified backend and the
  capability registry, so projects that stage creates now Build instead of
  being refused at the provider gate.
- **Custom names (optional):** a created formation or play may carry a
  1-40-character printable-ASCII name appended to the name pool's verified
  zero tail; the pool count word at 0x1083C is checked against the retail
  invariant (37/37 books) and kept consistent. Donor-name reuse remains the
  default.
- **List Play in Formation** (`play_formation_link`): writes one play index
  into the formation's first empty 0x1FF menu slot so a created play is
  actually callable; the selection group inherits the formation's existing
  slots (or an explicit 0-3). Group-bit gameplay semantics remain unproved
  and are labeled as such.
- **One-pass composition:** creates, links, and stock route copies for one
  book compile against a single intermediate body into one pack-0 slice.
- **Projects persist creates and links:** Save Project writes
  `playbook_creates`/`playbook_links`; load re-validates per book through the
  writer before staging. No silent drops.
- Honesty: registry and panel copy state that runtime visibility of created
  formations/plays is not captured (no emulator gate in this release),
  freehand node synthesis stays refused, and the XBE is never touched.

## v1.0 RC72 — jersey digits that fit (2026-08-21)

Community report: "can't edit numbers in 2k5." The number *values* were
always editable; the digit *art* imports were refusing typical authored
sheets on the tightest retail VC-LZ spans. Root cause, same family as the
2K8 digit finding shipped in APF alpha.79: the mip chain was built with a
channel-box average, and averaging two flat region colours mints a blend
colour that is not in the artwork. The blends spend palette entries and
index entropy, so the compressed stream stops fitting fixed spans that the
same art fits with region-clean mips.

The digit/nameplate mip filter is now a region-majority downsample (majority
colour wins each 2x2 footprint; ties go to the rarer region, so thin
outlines survive). The palette ladder, fixed-span rebuild, and every gate
are unchanged; the importer manifest now names the filter. Measured on the
retail proof chain: the four Detroit fixtures compress from 12,084 changed
bytes to 11,684, and a thin-outline digit that overflowed its span under
box mips now fits (pinned by
`test_box_mips_spend_the_span_on_blends_the_majority_filter_saves`).

Also closed a stale-fixture hazard: the retained 32x1024 nameplate PNG stays
as the pinned historical proof input, and the pipeline now consumes the
generator's corrected 1024x32 atlas from
`reports/assets/nfl2k5_live_numbers_nameplate_fixtures/current/`, so the
live-art XISO proof chain runs green end to end again.

## v1.0 RC71 — Beta 47 identity (2026-08-21)

Identity-only bump: Beta 47 ships the shared desktop-shell fixes and the APF
alpha.80 surfaces; the 2K5 editing surface is unchanged from RC69. The
updater reports beta-47 and the packaged runtime closure re-pins.

This is the modder-facing record of functionality that is actually present in
runnable builds. A mapped resource is not listed as editable unless its product
writer is connected to Replace, Revert, project save/load, and the composed
build path.

## v1.0 RC69 — updater identity beta-46 — 2026-08-15

- Shared updater identity is `beta-46`. No 2K5 writer or importer changed.
  The Playbooks repair, raw-export withdrawal, and APF packaged-import closure
  check in this tag are APF-only.

## v1.0 RC68 — updater identity beta-45 — 2026-08-15

- Shared updater identity is `beta-45`. No 2K5 writer or importer changed.
  Field Art extras, jersey numbers, jersey capacity, and the G12 pack in this
  tag are APF-only.

## v1.0 RC67 — updater identity beta-44 — 2026-08-14

- Shared updater identity is `beta-44`. No 2K5 writer or importer changed.
  The Fine-tune Plays, empty-formation, and build-folder work in this tag is
  APF-only.

## v1.0 RC66 — Check My Images, and a camera map — 2026-08-14

- **New: Check My Images.** Sits directly above Build. Runs the real quantizer
  and the real encoder against the real slot contract for every staged image and
  reports, per slot: fits as authored, will be reduced to N colours, or will not
  fit. The palette ladder added in Beta 41/42 is lossy and used to happen
  silently; this is how you find out first. It changes nothing and starts no
  build.
- **The `sleeve` slot contract was wrong and is fixed.** It had been modelled as
  512x256 with six mips like the torso; the real slot is 128x128, five mips,
  with a 64-byte gap between the clean and mud palettes. Contracts are now
  derived from the importers themselves and cross-checked at import time, so a
  typed table cannot drift from the code that writes the bytes again.
- **Jersey numbers: do not paint them into the art.** The torso, sleeve and
  pants slot copy now says so. 2K5 draws numbers from separate digit textures in
  the same uniform set — Jersey and Arm digits at 64x64, Helmet digits at 32x32,
  and a 1024x32 nameplate atlas — so numbers baked into the jersey appear twice.
- **The nameplate atlas is 1024x32 horizontal**, not 32x1024 vertical. The
  transposed value came from a TXTR descriptor bug fixed long ago in the decoder,
  and three user-facing places still carried it.
- **New: `--inspect-camera-options nfl2k5`.** Seven named settings with their
  shipped ranges and six named presets. Camera Distance is a dimensionless
  multiplier and Camera Height is world units; only Camera Angle is 0..1. The
  three sliders only move the camera while the preset is set to Custom — that is
  how the shipped game works. Read-only: the values live in a signed save.
- **The published slider snapshot was mislabelling 12 of 18 entries.** The save
  stores each slider vector in its globals' address order, where Catching is
  last, not the menu's display order, where it is fourth. If you read a slider
  value out of this tool before, re-read it.

## v1.0 RC65 — pants too, and a test that finds the next one — 2026-08-13

- **The pants importer was missed in Beta 41 and is fixed here.** Building a
  pants replacement still refused with `pants: VC-LZ stream needs more than the
  75472-byte bound`. Beta 41 wired the palette ladder into live helmet, jersey,
  scorebug and create-team field art but not pants, because the sweep that
  found the offenders was truncated and the resulting list was then hard-coded
  into the test that was supposed to guard it — so the test agreed with the
  omission. Pants now uses the ladder like its siblings.
- **That test now derives the set from the tree instead of trusting a list.**
  Anything that compresses into a bounded VC-LZ span and still quantizes at a
  flat 256 fails the suite, so a missed or newly added importer cannot inherit
  this bug by being forgotten.
- **A failing edit is named by the coordinates it was picked by.** Beta 41's
  message said only `pants:` — a uniform edit carries no selector, so the label
  fell back to the bare kind. It now reads
  `pants (asset_code=NE, side=home, variant=0)`.

## v1.0 RC64 — a fixed VC-LZ span fits the art down instead of refusing — 2026-08-13

- **A texture that will not fit its retail compressed span is now quantized
  down instead of failing the build.** Building could refuse with
  `VC-LZ stream needs more than the 34416-byte bound` — 34,416 is a live
  helmet TXTR — and the message named no team, no slot, and no image.

  `quantize_levels_to_vc_lz_bound` has shipped for a while: it tries palettes
  from 256 down to 2 and returns the first that fits, which is what the sleeve,
  digit, all-texture and Crib importers already do. Four importers that
  compress into a bounded span still called the plain 256-entry quantizer and
  hard-failed: live helmet, jersey, scorebug, and the compressed create-team
  field art. They now use the ladder. **The ladder starts at 256, so art that
  already fit is byte-for-byte unchanged**; only art that used to fail steps
  down. When even a two-colour version will not fit, the message says so and
  says what to simplify.

  The three P8 importers that write *uncompressed* fixed spans — team select
  card, player portrait, Crib team photo — have no bound to overflow and are
  deliberately left alone.

- **Every build failure now names the edit that caused it.** The dispatcher
  knew each edit's kind and selector and attached neither, so any importer's
  message stood alone in a build carrying dozens of edits.

  Reported against Beta 40.

## v1.0 RC63 — Team Kit equipment edits can be built — 2026-08-13

- **Swapping a sock, glove, shoe, wristband, elbow pad, or long-sleeve texture
  no longer breaks the build.** Build Modded XISO refused with
  `Unknown uniform asset ID: tset:3660:4:0:socks00`, and Save Project, Load
  Project, Import Team Kit, Undo's restore and Revert All refused the same way.

  Only the uniform *sets* live in the uniform catalog. The Team Kit's 45
  package-local equipment parts are `tset:` assets minted by the extended
  visual catalog, along with `p8:` textures, portraits, live faces,
  create-field art and the scorebug — 47,237 assets the build could not name.
  Staging worked because the panel hands `replace()` an already-resolved asset
  object; every later step re-resolved the ID string through the wrong catalog.

  Every one of those steps now resolves through `Nfl2k5ProductVisualCatalog`,
  the aggregate that was written for exactly this and never handed to a
  session. A uniform edit resolves to the identical object it always did, so
  jersey, helmet and digit edits are unchanged.

  Reported against Beta 39. The routing dates to the first public beta; it
  became reachable in RC49, when Team Kit gained the equipment parts.

## v1.0 RC62 — no 2K5 changes — 2026-08-11

- This release fixes APF 2K8 team-crest mip regeneration and adds a two-layer
  crest import to APF's Team Logo panel. Nothing in 2K5 changed; the version
  moves so both products keep shipping from one release.

## v1.0 RC60 — validation harness PATH isolation — 2026-08-10

- The capability validation harness put the discovered ripgrep's whole
  directory on its fixed PATH while asserting that directory holds exactly one
  command. That held when ripgrep came from `/usr/bin` and failed on any machine
  whose ripgrep ships in a shared vendor bin. It now exposes ripgrep through a
  private single-entry directory, so the invariant holds everywhere instead of
  only where it happened to already. Maintainer tooling; nothing user-facing
  changed in 2K5 this release.

## v1.0 RC59 — stadium caches recover instead of dead-ending — 2026-08-10

### Fixed

- **"Private Stadium Studio result marker is incompatible or incomplete".**
  Beta 30 rebound derived stadium assets to the canonical game-content identity
  instead of a container hash — the right fix — but every private cache written
  before that change then failed its own marker check with no way back. Anyone
  who had already opened Stadium Studio met this error on every launch, on a
  game that had worked, with the only remedy being to delete a private directory
  nobody had told them about.
  A cache this build cannot read is now treated as stale and re-derived
  automatically. Safety refusals are unchanged and still refuse: a symlink, a
  junction, or anything outside the private root is never removed automatically.

## v1.0 RC58 — findable stadium geometry + real xemu setup — 2026-08-10

### Stadium models

- **The editable stadium scene is marked and opened first** — Stadium Studio
  indexes 477 scenes, and exactly one of them carries the catalog-pinned
  geometry targets that Import can write. That scene now shows a ✎ marker and
  its editable-mesh count, the list opens on it instead of on row 1, and a new
  **Only scenes with editable geometry** filter hides the rest. Every other
  scene's tooltip says plainly that it is view and glTF-export only, so Import
  staging nothing is never a mystery.

### Emulator

- **Configure xemu** — the footer can now point the editor at your own xemu
  program, and the choice is remembered between sessions. The old tooltip told
  people to "configure xemu" when nothing in the app could do it.
- **xemu is re-detected while it is still missing** — detection used to run once
  at startup, so installing xemu because the editor asked you to did nothing
  until you restarted the editor.
- **Flatpak xemu can open builds outside home** — a Flatpak launch now grants
  read-only sandbox access to the built XISO's own directory. Without it, a
  build on an external drive failed with an I/O error that looked like a bad
  build rather than a sandbox refusal.
- **Launch Latest Build never silently grays** — it stays clickable and names
  the one thing that is missing (no build yet, no xemu, or a build that has
  since moved) rather than one message covering all of them; when xemu is the
  missing piece, clicking offers to choose it.

### Reliability

- A window opened against an already-loaded game no longer fails during
  construction: the shared status/progress footer is built before the pages that
  report into it.
- The update check refuses to advertise a release older than the running build,
  and reads the highest published beta rather than trusting list order.

## v1.0 RC57 — valid-container shared-cache repair — 2026-08-09

- **Valid ISO layouts share one verified cache** — once the USA retail game is
  recognized and its extracted packs and inventory match their independent
  pins, container padding and partition placement no longer create competing
  cache identities.
- **Stadium Studio loads across layouts** — its private result marker and worker
  now bind the canonical validated game content, fixing the incompatible or
  incomplete result-marker error raised after an otherwise successful load.
- **Original previews stay source-correct** — ordinary and extended visuals,
  Crib art, standalone audio, and streaming-range sidecars use the canonical
  cache binding. Intact legacy visual and Crib entries refresh safely; altered
  bytes and unsafe paths still fail closed.
- **Audio safety data is reusable** — exact PCM fingerprints and containment
  inventories use the canonical cache identity, and containment parses the
  actual opened container size instead of assuming one disc-image layout.
- **Build sizes are honest** — build validation, free-space budgeting, and the
  returned result use the selected container's actual size. Direct source-file,
  recovery, and session race guards remain tied to the exact selected file.


## v1.0 RC56 — crib drop-parity + never-gray G1/G2 — 2026-08-09

### Beta 29 refresh

- **Updater identity corrected** — RC56 now identifies its release channel as
  `beta-29`, not the stale `beta-22` packaging label, so manual and automatic
  checks no longer offer Beta 29 to an already-current Beta 29 build.

### Community / product

- **G2 multi-Ace link-table pack** — Export G2 multi-Ace pack… copies the Quads
  play-link (menu) table onto every Ace-named formation in a private PLAY + honesty
  JSON sidecar. Offline-writer-proved for menu bytes only; runtime TE→WR unproved;
  package maps/assignments untouched.
- **Release allowlist ships G1 + formation clone** — `playbook_package_rule_spike.py` and
  `nfl2k5_formation_play_writer.py` were imported by the product but absent from
  `packaging/release-allowlist.txt` (Windows stage would crash on Playbooks G1 export
  / formation clone). Staged file count 195→197; runtime closure + release gate green.
- **Crib drag/drop fit** — off-size JPEG/PNG drops open the same Contain/Cover/
  Stretch chooser as the Replace dialog (shared `_fit_crib_image` path). Drop-
  parity tests mock the chooser under offscreen Qt so the modal never hangs CI.
- **pytest offscreen default** — `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`
  so monorepo GUI tests do not hang waiting on a display/modal.
- **G1/G2 experimental exports never silent-gray** — Export Package-Map Copy /
  Link-Table Copy stay clickable with disableReason + click-to-explain when the
  XISO/book/formations are not ready (runtime still unproved).
- **Playbooks community legend**
- **Extended visual browsers**
- **Stadium surface textures** — Export/Replace/Revert never silent-gray.
- **Universal inventory raw Export** never silent-gray. — Export/Edit/Replace/Master/Revert never silent-gray (export-only assets explain).
- **Unif colour filter-empty** — facemask/turtleneck/Apply/Revert stay clickable. — G1/G2/G13 one-liners under the ⚠ filter;
  empty-state text when Community-flagged matches zero books.
- **Text & Rosters** — All-Text Apply/Revert/Export, Current Player Apply/Revert,
  Historical Team/Player Apply/Revert stay clickable with disableReason +
  click-to-explain (no-change, unit limit, read-only, nothing staged).
- **Audio Export matching** never silent-gray — shortlist/raw/count/pending
  walls teach on click (1–256 row bound still enforced).
- **Audio Load waveform** never silent-gray for Load/select/raw/bank walls
  (cancel-in-flight may briefly lock while finishing).
- **Audio shortlist bulk** — Add all matching / Add this page / Review / Export
  selected WAVs never silent-gray; blocked clicks teach via progress_label.
- **Audio shortlist Add/Remove selected** never silent-gray.
- **Audio replacement template Export/Import** never silent-gray (busy/Load/
  shortlist walls).
- **Audio row Play/Export/Replace/Revert** never silent-gray (Load/select/raw walls).
- **Audio shortlist Move up/down** never silent-gray.
- **Audio soundtrack quick-view** never silent-gray.
- **Audio copy pack path** never silent-gray.
- **Gameplay Inspector Export JSON/CSV** never silent-gray on inspection failure.
- **Menus & UI Export JSON/CSV** never silent-gray when the named Main Menu map
  fails to load — click teaches the wall (read-only inspector; no menu rewrite).
- **Text & Rosters Export Number** (current + historical) never silent-gray —
  empty selection teaches “select a player first.”
- **Stadium Studio surface Export/Replace/Revert** never silent-gray at
  construction (boot disableReason before first texture selection).
- **All Resources Previous/Next** never silent-gray (first/last/busy/Load walls).
- **Playbooks “G1: Use Nickel donor”** — one-click set package-map donor to
  a Nickel formation when present (offline G1 helper; runtime unproved).
- **Playbooks “Export G1 multi-Dime pack…”** — offline experimental: copy the
  Nickel package map onto **every** Dime-named formation in the selected PLAY
  book; private PLAY + honesty JSON sidecar; multi-region byte-diff verifier;
  runtime G1 still unproved; source ISO never mutated.
- **Audio Previous/Next** never silent-gray — first/last page, pending search,
  busy, and unloaded walls teach via disableReason + progress_label (clicks no
  longer look dead).

### Honesty

- Freehand routes still not Editable; G1/G2 still offline-bytes only.

## v1.0 RC55 — package-map writer, playbooks inspector map, crib UX — 2026-08-08

### Community / product

- **G1 package map (Dime ILB surface)** — o0308 census: assignment-only gate
  failed; primary offline delta is formation `+0x0D` 11-byte role permutation
  (Nickel vs Dime). `build_formation_package_map_patch` + independent verifier
  offline-proved for map bytes. Runtime G1 fix **unproved** — no one-click pack.
- **G2 Ace menu** — formation play-link table copy offline-proved (Ace←Quads
  class); experimental Export Link-Table Copy in Playbooks (private PLAY only).
- **Playbooks inspector** — read-only package-map line under Formation; Dime/Nickel/Ace honesty tags.
- **Crib import fit** — Contain/Cover/Stretch chooser on dialog + drop.
- **Crib model import/export** — click-to-explain when XISO or scene missing (no silent gray).
- **Stadium model Import/Export** — never silent-gray; `disableReason` + click explain.
- **Unif facemask/turtleneck/Apply** — never silent-gray; status teaches Load XISO /
  clear filter / wait for set load (per physical set).
- **Keyboard** — Esc clears search; Ctrl+/ keyboard hints (parity with APF shell).
- **Broken-play ⚠ Ace/Dime/Bear** — still annotations only; G1 map text updated.

### Honesty

- Package-map / link-table exports never mutate the loaded ISO and are not
  project staged as Editable gameplay fixes.
- Freehand routes still not Editable.

## v1.0 RC54 — playbook host clone stubs, stadium import reasons, stretch fit, broken-play flags — 2026-08-07

### Community / product fixes

- **Import fit chooser** — off-size dialog/drop imports pick Contain, Cover, or Stretch (not silent auto-cover).
- **G1/G2 package-rule** — layout pins + o0308 census in `playbook_package_rule_spike`;
  offline writers for formation package-map (`+0x0D`) and link-table copy **proved
  for bytes only** (runtime fix packs unproved).

- **Studio launch / Playbooks host** — `BrowseOnlyFacade` and `StudioFacade`
  expose formation/play clone methods so `PlaybooksPanelHost` isinstance checks
  pass (unblocks every headless Studio GUI test that constructs the main window).
- **Import edited stadium model never silent-gray** — export/import scene buttons
  stay **enabled**; tooltips + `disableReason` + click QMessageBox explain
  load-required / no-scene-selected / same-topology contract (no dead gray).
- **Import resize** — shared `image_fit` gains **stretch** (Contain/Cover already
  shipped); dialog + drop still share `_fit_for_slot`.
- **Playbooks Ace / Dime / Bear annotations** — formation/play names matching
  community package bugs show ⚠ tags and tooltips pointing at
  `docs/product/APF_GAMEPLAY_BUG_MAP.md` (annotations only; no fake auto-fix).
- **Facemask / turtleneck** — still per physical uniform set (Unif words 0/1),
  not global.

### Ledger

- Fix-or-wall tracker: `docs/product/S61_EDITOR_BUG_WALLS.md`.

## v1.0 RC50 — complete uniform fixes, menu/presentation logos, model tools, and release hardening — 2026-08-04

### Uniform-equipment discoverability

- **Socks and other package-local equipment are now directly findable from
  Team Kit.** Select a physical uniform set and choose **Browse 45 Equipment
  Textures** to open the existing All Textures browser filtered to its exact 45
  socks, elbow-pad, glove, long-sleeve, shoe, and wristband records. Searching
  within that list narrows the selected set. The route reuses the canonical
  asset IDs and existing Export, Edit, Replace, Revert, project, and Build
  handlers; it does not create a second writer or duplicate edit IDs.

### Crib textures and bounded model editing

- **All 498 catalogued Crib textures are Editable.** Coverage is 242 raw Team
  Item P8 textures (including all 128 Team Photos), 68 standalone P8 textures,
  and 188 material/submesh-owned P8 surfaces across 36 SCNE scenes. The writer
  preserves the reflection texture's 109,440-byte source gap, the ticker's
  1024x32 linear layout, every unselected allocation, and the fixed compressed
  span.
- **The Crib now has a Models tab.** It exports seven proved scenes and imports
  same-count, same-topology position changes for ten exact electronics meshes.
  UVs, materials, collision, indices, normals, other registers, commands, and
  opaque tails stay source bytes. Changed topology and arbitrary model swaps
  remain explicitly unsupported.

### Jersey numbers and stock play routes

- **All 2,547 current-player jersey numbers are Editable, including the 68
  secondary-pool players that previously errored or stayed disabled.** The
  writer patches only the masked number bits. Secondary names remain read-only
  because their text allocation is zero; the UI now enables each field from its
  own proved contract instead of locking the whole row.
- **Every current and historical player now has a Face shield control.** It
  authors only player word `+0x20` bits 15..16 with exact choices **None**,
  **Clear**, and **Dark**; reserved value `3` is refused. Jersey and face shield
  changes compose into one four-byte replacement, preserving every unrelated
  bit. This is a per-player equipment type, not a HOME/AWAY visor tint, and a
  loaded roster or franchise save may override the disc seed.
- **Playbooks & Plays can copy exact stock assignment routes within one PLAY
  book.** Choose a target assignment and a donor assignment, then stage or
  Revert the copy. The writer changes only the target descriptor word and
  relative pointer to the donor's existing node chain, reparses the full PLAY
  resource, and refuses orphaning or count changes. Freehand waypoint/opcode
  authoring remains unsupported.

### A1 player strips in All Textures

- **The twelve explicit-size `p001`…`p006` / `p011`…`p016` A1R5G5B5
  families are no longer blanket-refused.** The authenticated source contains
  340 copies of each name: 4,080 strips total. All remain searchable,
  previewable, exportable, and editable through the composed-XISO build.
- The writer regenerates all five linear mip levels, keeps the measured
  source-owned video tail byte-exact, preserves every descriptor and the
  complete resource span, and independently decodes the fixed-span VC-LZ
  rebuild. If native five-bit colour is too complex for the retail allocation,
  it tries deterministic four-, three-, two-, then one-bit-per-channel tiers
  before refusing with a simplify-art message.
- **The boundary target is complete too:** outer 581 `p005` straddles physical
  packs 0 and 1 as exact 53,888-byte and 21,008-byte slices. The editor builds
  one logical TXTR, stages both pieces before reserving a new output, verifies
  both source packs, writes only the fresh copy, reads each piece back, and
  reassembles the complete 74,896-byte chain for an independent final check.

### Audited boundaries: stock midfield and PCSX2 packs

- The exact standalone `center_logo` corpus is 126 create-team weather/logo
  packages at outers 384–509. The stock disc has no additional TXTR named
  `center_logo`. Its 85 `NN_teamlogo_00_h0` P8 rasters are not a safe midpoint
  substitute: the executable formats that name at `0x00142AF0`, loads it as a
  TXTR, and attaches it to the `FRANCHISE2` / `coach_desk` scene element named
  `teamlogo`. Stock midfield texture ownership remains unproved and the editor
  does not relabel franchise-office art as field art.
- The supplied `NFL2K27` tree is not a complete PCSX2
  replacement pack: it contains 5,688 directories but only four distinct
  Roman Reigns cyberface PNGs, copied into three locations, with no PCSX2 hash
  filenames or mapping manifest. There is therefore no source-owned mapping to
  automate into Xbox slots. High-resolution authoring and native Xbox fitting
  remain available, but cross-console hash mapping waits for the actual pack.
- NFL 2K3/2K4 discs or extracted packs are also absent. The shared container
  parser is not treated as proof that a 2K5 resource selector or byte extent is
  valid in either earlier game; source admission/build stays closed until each
  title has a pinned executable identity and independently inventoried writer
  targets.

### Bounded Stadium model import

- **Stadium Studio now imports edited glTF vertex positions.** Export the proved
  full scene, move vertices in Blender, keep the sidecar `.bin` beside the
  `.gltf`, then choose **Import edited model…**. The importer requires every
  bounded mesh to keep its exact vertex count and equivalent triangle set.
  Adding/removing faces, welding, subdivision, decimation, sparse accessors, or
  another mesh is refused before the session changes.
- Only the 75 catalogued fixed `FLOAT3` position lanes can change. Game UVs,
  materials, collision data, selectors, LOD/other streams, and the fixed opaque
  SCNE tail are kept from the user's source bytes. Stadium texture edits in the
  same scene are composed with the geometry edit before one VC-LZ rebuild, so
  their spans cannot overwrite one another.
- The position recipe stays in the private working session because it is
  derived from the user's game. It can build a local XISO and supports Undo and
  Revert All, but it is deliberately excluded from shareable `.2k5mod` files.
  Offline topology and byte preservation are proved; visible in-game runtime
  ownership is still labeled unproved until a matched capture exists.

### High-resolution authoring masters

- The Portraits & Faces, Create-a-Team Field Art, Scorebug Presentation, and
  All Textures browsers now expose **Save high-resolution authoring master…**
  after a dialog or drag/drop import. The non-overwriting `.2ktexmaster`
  preserves the exact original bytes, exact native staged PNG, source hash,
  final scale/cover geometry and Lanczos compile metadata, plus a direct 2x or
  4x original-source render. It is an authoring sidecar, not a larger Xbox
  texture or an emulator pack.
- Exact-size JPEG and non-RGBA PNG inputs now receive the same confirmed
  conversion path as off-size images. The source file stays byte-exact; the
  private staged copy is an exact-size RGBA PNG.
- Built-in pixel painting after an external import retains the original master.
  The archive stores the exact native pre-edit canvas and verifies a native
  raster-edit layer over the direct high-resolution render. A retail-only edit
  cannot enable this export because a shareable bundle must not contain
  source-derived retail pixels.
- Existing `.2k5mod` v1 projects retain native replacement PNGs only. Masters
  are explicit sidecars and are not reconstructed from downsampled project
  content. See `high_resolution_texture_authoring.md` for the exact coverage
  boundary and RPCS3 explanation.

### Complete menu, mini-card, franchise, and draft logo coverage

- **All 1,755 team-linked presentation surfaces outside the uniform packages
  are now first-class All Textures assets.** Coverage is all 317 full 256×256
  menu logos, 317 compact logos, 317 shared flip chips, 634 home/away mini
  cards, 85 franchise-office logos, and 85 draft/PDA logos. Together with the
  existing catalog this raises the standalone editable inventory from 9,640
  to **11,395** targets.
- The browser exposes **Team Logos — Menus / Presentation**, **Team Mini Cards
  — Menus / Presentation**, and **Franchise & Draft Presentation** as separate
  groups. Every row carries the exact team asset code, style and home/away set
  owners where applicable, archive name, and statically established consumer
  scope. Searches such as `Eagles`, `21H0`, `menu logo`, `mini helmet`, `coach
  desk`, and `pda logo` reach the intended family. Franchise team logos remain
  explicitly separate from midfield art.
- `logos.cdf`, `mini.cdf`, and `flipchip.cdf` are raw P8 fixed-slot arrays, not
  VC-LZ streams. Their importer preserves the wrapper, descriptor/system
  region, exact 66,720/5,280-byte resource span, and 96-byte zero slot padding;
  only the swizzled indices and 1,024-byte palette are regenerated. This removes
  false “VC-LZ stream needs more” failures for these menu assets. Franchise and
  draft logos keep the existing bounded compressed-P8 path. All 1,755 targets
  support Preview, Export, Edit, resized dialog/drag-drop Replace, Revert,
  project persistence, and composed-XISO Build.

- **The report was correct: NFL 2K5 keeps presentation art separate from live
  uniform art.** Every one of the 634 physical uniform packages contains four
  additional standalone textures: `logo` (128×128), `chiclet` (64×64),
  `splayer` (256×128 with five mips), and `flipchip` (64×64). Those 2,536
  records are not either live helmet diffuse, and they are not the three
  pre-rendered Team Select uniform/helmet cards.
- **All 2,536 are now explicit in All Textures.** Open the new **Team
  Presentation — Menu / UI** group, or search a team name, abbreviation,
  physical selector such as `21H0`, `menu logo`, or the exact resource name.
  Preview, Export PNG, Edit, dialog/drag-drop Replace, Revert, project save/load,
  and Build Modded XISO all use the existing fixed-span P8 route. The editor
  labels this as presentation/menu/UI art because `logo` and team-chiclet
  lookups are statically present but a complete screen-by-screen consumer map
  is not proved.
- **Small presentation spans now get the same bounded palette recovery as
  numbers and sleeves.** A complex Eagles `logo` fixture overflowed its
  6,656-byte VC-LZ budget at 256, 128, 64, and 32 colours, then rebuilt and
  independently decoded at 16 colours inside the exact retail span. Build now
  tries deterministic quality tiers before showing a useful simplify-image
  error; it no longer stops at the first raw “VC-LZ stream needs more” message.
- **Pack-boundary uniforms are covered.** An outer package may cross two
  internal pack files while the selected texture remains wholly inside one of
  them. The resolver now maps the texture's exact physical extent and refuses
  only an individual TXTR that actually straddles a boundary.

## v1.0 RC48 Audio Converter, Stadium Model Export, Update Check - 2026-07-30

- **Facemask/faceshield and turtleneck colours are truly per uniform now.**
  The previous control patched two fixed records and called them global; those
  offsets are actually Detroit current HOME (`09H0`) and AWAY (`09A0`). The
  Colours tab now has a searchable 634-set team/uniform selector. Each project
  row carries only that logical selector and the two authored ARGB values, and
  Build resolves it against the user's pinned source before replacing exactly
  one eight-byte record. HOME, AWAY, throwbacks, and alternate sets can all keep
  independent values in one project. Word 0 jointly controls facemask and
  faceshield; there is no independently proved visor field. Word 1 controls
  `HI_turtleneck`.
- **Socks and the rest of each uniform's equipment are editable now.** All
  28,530 package-local socks, elbow-pad, glove, long-sleeve, shoe, and wristband
  P8 references across 634 physical sets are searchable in **All Textures**,
  with preview, PNG export, built-in Edit, dialog/drag-drop Replace, Revert,
  project persistence, and composed-XISO build. Each TSET shares one retail
  shape/mip index chain, so an import changes only the selected palette and
  proves every sibling byte and decoded image stayed exact. Deterministic colour
  tiers keep the complete compressed TSET inside its original fixed span; a
  target that cannot fit a usable two-colour result is refused. Facemask and
  faceshield colour are not TXTR entries and remain in the per-uniform Colours
  control above.
- **Team Kit export no longer mistakes an old cache for tampering.** The exact
  report was “A private original-backup file changed outside Mod Studio.” Team
  Kit uses the uniform cache lane, while the first repair covered only the
  extended-visual lane. Both now distinguish internally valid stale metadata
  from bytes actually changed behind the app's back, regenerate old-schema or
  old-dimension entries only after a fresh decode succeeds, and preserve the
  old pair if that decode fails. Real changed bytes still fail closed.
- **Titans arm/shoulder numbers are present at their authored size.** Retail did
  not use one dimension per digit family: 380 arm-digit targets are 32×32, and
  200 helmet-digit targets are 64×64. The catalog now resolves every digit from
  the same compatibility row its decoder uses; `28H0`, `28H7`, and `28H8` no
  longer inherit a false 64×64 arm-number size. A real-source regression exports
  and revalidates all 33 reported surfaces: one sleeve and all ten arm digits in
  each of those three Titans packages.
- **All Textures export is exercised through the public router.** The Windows
  filename `p8:386:endzone_north_left.png` is still sanitized to
  `p8-386-endzone_north_left.png`, and a functional regression test now proves
  a `p8_texture` export reaches the extended decoder instead of the uniform IO
  that reports “Export is not implemented.” The exact DM transcription
  `p8:386:endzone_north_;eft.png` is also pinned; its illegal colons are removed
  without guessing that the legal semicolon was meant to be another character.
- **The reported 1,568-byte number/sleeve build error is fixed.** Small P8
  targets now retry deterministic palette tiers until the complete VC-LZ stream
  fits their original allocation, keeping the richest tier that passes. A real
  1,568-byte number target is compiled through the public project route, bound
  to the source XISO, and independently reopened and decoded after composition.
- **Any audio file can now replace a sound.** Drop an MP3, WAV, FLAC, OGG, M4A
  or similar onto an editable sound and it is converted to that slot's exact
  channel count, sample rate and frame count before it is written. Building a
  file to match by hand in an audio editor is no longer necessary. The drop zone
  states what the selected sound needs, and after a replacement the status line
  names what changed: resampled, trimmed to fit, padded with silence, or level
  lowered. Hover it for the full explanation.
- **Nothing external is needed for the codec itself.** All 850 of this game's
  sounds are Xbox IMA ADPCM, which is fully documented, so the encoder is part
  of the app. FFmpeg is used only to read your own file. A file that already
  matches the slot exactly is passed through untouched, byte for byte.
- **This was measured, not assumed.** All 849 authorable slots were converted
  from one ordinary source file, validated by the app's own strict parser,
  encoded and decoded back: 849 of 849 succeeded, signal-to-noise 32.34 dB
  minimum and 32.53 dB median. Typical IMA implementations land nearer 20-25 dB;
  the difference comes from searching every candidate start index per block
  rather than carrying the previous one forward.
- **Long sounds no longer stall the window.** That exhaustive search cost about
  110 seconds for a 30-second sound. It is now vectorised across blocks and
  candidates together, roughly 24 times faster, producing byte-identical output.
  The tests assert byte equality against the original encoder, not similarity.
- **Export model (glTF) on the Stadiums page.** The viewport could draw a
  stadium but offered no way to save it. It now writes the model and its buffer,
  and says where both landed, because the buffer keeps its own name and has to
  travel with the model. The export is scaled to metres: the game stores stadium
  geometry in centimetres, so an unscaled file opens about a hundred times too
  large and disappears past Blender's default view distance. No vertex is
  rewritten; the buffer is copied unchanged.
- **Update check.** Help now offers Check for Updates, an automatic-check
  toggle, and a link to the downloads page. When a newer release exists a strip
  appears at the top of the window. It never downloads or installs anything, it
  cannot delay startup, a failed check is silent, and dismissing one version
  does not hide the next. The first automatic check explains itself once.
- **Wider disc support.** Reading a disc image no longer aborts over an empty
  folder, a single accented filename, or deep directory nesting. Extent bounds,
  cycle detection and filename-separator rejection are unchanged.
- **Nameplate Atlas is exportable again** for all 634 uniform sets. Its
  compatibility report still carried a transposed 32x1024 dimension after the
  texture descriptor fix moved to 1024x32, so every set was refused. The atlas
  is a wide strip and its mip chain halves from 1024x32, so written the other
  way round the check could never pass. All 19,654 art resources now report
  compatible, where 634 were refused before.
- **An unexpected error now tells you what happened.** Previously the window
  simply closed: Qt ends the process when an error reaches it and no handler is
  installed, and the editor runs from an icon with no console, so nothing was
  shown anywhere. There is now a message naming the problem, stating that your
  original game files were untouched, and giving the path of a log file to
  attach to a bug report. The editor keeps running. A fault that repeats is
  logged every time but only interrupts once, so a problem in a redraw cannot
  bury the screen in identical boxes.
- **Odd and broken disc images are answered in words.** An empty file, a partial
  download, an archive renamed to .iso, a folder, or a file that has since been
  moved or deleted each get a sentence saying what was wrong. A file picked from
  a recent list and since deleted used to raise a raw system error.
- **A disc image reached through a symlink is recognised.** Keeping the image on
  another drive and linking it into a working folder is ordinary, but the
  identifier refused to follow the link and called it "not an Xbox game" while
  the recogniser accepted the same file. The two now agree.
- **A corrupt disc image cannot exhaust the reader.** A directory whose entries
  form one long chain rather than a balanced tree recursed once per entry and
  ran the interpreter out of stack, which surfaced as a crash instead of a
  refusal. The reader now counts every recursive step and refuses well before
  that. A balanced directory of the same size still reads normally.

## v1.0 RC47 Player Assets, Save Roster Import, Stadium Round-Trip — 2026-07-28

- **Player Assets** joins Rosters & Players. Search a player and see the face
  textures and portrait that belong to them. The face link is real — it comes
  from the `face_id` in the player's own roster record — and is labelled as
  such; a portrait is matched by name because nothing in the bytes ties a
  portrait number to a player, and that is labelled too. Equipment is listed
  once with a plain statement that NFL 2K5 stores it as five shared textures,
  so editing one changes it for everybody.
- **Roster names can come off a PS2 memory card.**
  `tools/nfl2k5_save_roster_import.py` reads a save's ROST arena and emits a
  project the normal build applies. A name too long for its fixed slot is
  skipped and reported rather than truncated, and capacity is measured in
  UTF-16LE because that is what the disc stores.
- **Stadium geometry round-trips through Blender.**
  `tools/nfl_stadium_gltf_roundtrip.py` turns an edited glTF into the recipe
  the proved position writer already validates. Proved end to end on the real
  disc: the retail 574-vertex roof raised five units, composed into a patched
  volume 9, 670 decoded bytes changed, topology and every unrelated stream
  preserved. It moves vertices; it cannot add or remove them, and it says so.

## v1.0 RC46 A Built-In Pixel Editor — 2026-07-28

- **Edit…** next to Export/Replace in every texture browser opens the slot at
  its exact retail size. Pencil, eraser, fill, eyedropper, a full colour picker
  with alpha, brush sizes to 64, zoom to 16x with a pixel grid, and 24 steps of
  undo.
- **The canvas has no resize control** — it *is* the slot's size — so what you
  save can never be the wrong shape. That round trip through another program is
  where a resaved 512×256 came back 513×256, or a crest lost its alpha.
- Transparency is drawn over a chequerboard rather than white, because an
  accidentally transparent crest is a black box on a helmet and you should see
  that before you build, not after.
- Nothing is written until you press Save; Cancel leaves the slot untouched.
- `tools/nfl_fit_image.py` does the same conversion from a terminal, one file or
  a whole folder at a time, for batches a dialog cannot reach — a directory of
  textures lifted out of another mod, for instance.

## v1.0 RC45 Images Get Resized For You — 2026-07-28

- New shared image-fitting layer, used by both editors. A texture slot occupies
  a fixed byte span so its replacement must be the exact retail pixel size, and
  that will always be true — but refusing the file instead of offering to fit
  it was our choice, and it stopped people at step one.
- Three fits, picked to suit the content: an image that is already exact is
  passed through **untouched**; a same-aspect image is resampled with Lanczos;
  and a different aspect either **pads** (crests and logos, keeping the whole
  shape on transparency) or **crops** (jerseys and field panels, where
  transparent bars would show in game as holes).
- JPEG, BMP, GIF, WebP and TGA are read as well as PNG, so a texture lifted
  from another mod or a photo does not need converting first.

## v1.0 RC44 The Facemask Colour Is A Colour Picker — 2026-07-28

- **You can pick the facemask colour in the editor now.** Uniforms & Equipment
  → **Colours & Other Tools** has two swatches, Apply and Revert. Word 0 of the
  `Unif` pair tints the facemask and faceshield; word 1 tints `HI_turtleneck`,
  which the game reads only when a player's two-bit selector is 3.
- It is a project edit like any other: it counts toward pending edits, Revert
  All clears it, it saves with the project, and it reaches the disc through the
  same composed **Build Modded XISO** as every texture and audio change.
- This release's control was later found to be global only in the UI: the two
  fixed records were Detroit current HOME and AWAY. RC48 replaces that route
  with one independently selectable record for every physical uniform set.
- **Repainting the coloured square on a helmet texture still will not move the
  facemask.** It is a separate material fed by this value — the difference from
  CFB 2K3 that started this whole thread.
- Ownership is proved by executable trace. A controlled in-game capture is
  still outstanding and the capability continues to say so.

## v1.0 RC43 All Textures Previews And Exports Actually Work — 2026-07-28

- **Export PNG failed with "The file name is not valid."** The suggested
  filename was the asset id, `p8:386:endzone_north_left.png`, and `:` is
  reserved on Windows. The old code only replaced `.`, which happened to be
  enough for every id that existed before. Suggested names are now sanitised
  for every character Windows rejects, plus trailing dots and spaces and the
  reserved device names, for **all** asset kinds rather than just this one.
- **The preview sat on "Preparing…" forever.** Every preview and export goes
  through a per-kind decoder dispatch that had no `p8_texture` branch, so it
  raised, the error was swallowed, and the loading text was never replaced.
  The decoder is implemented: it parses the retail descriptor and decodes the
  texture exactly as the writer does.
- **A preview that cannot be produced now says so** instead of spinning. That
  silent failure is the only reason this shipped looking like it worked.

## v1.0 RC42 All Textures Is A Workspace Now, And Its Edits Reach The Disc — 2026-07-28

- **All Textures shipped as a sidebar entry with nothing behind it.** It is a
  real workspace now: **3,024 targets** you can search, preview, Export PNG,
  Replace PNG and Revert, exactly like every other visual family. That is 1,770
  end-zone panels, 1,024 goalpost pads, 225 grass `divots` overlays and the
  five shared equipment textures.
- **The half that mattered: those edits now survive Build Modded XISO.** A new
  `p8_texture` edit kind runs through the composed build, is validated, refuses
  duplicate targets, and binds per-extent — the build locates each pack in your
  own image, re-derives the offset from where it actually lands, and verifies
  the pack hash and retail span before writing. A browser whose edits vanished
  at build time would have been worse than the bare card it replaced.
- Proved end-to-end on **three differently packed dumps of the same game** --
  the project's canonical `.xiso`, a reporter's repack and a reporter's
  pressed-disc read. All three composed two texture edits and changed an
  identical **31,652 bytes**.
- This corpus is separate from Stadium Studio's 23,838. That lane edits
  textures embedded *inside* SCNE scenes; these are standalone `TXTR` chunks
  sitting beside them. Outer 3136 carries five SCNE chunks and eight separate
  TXTRs; outer 853 carries ten TXTRs and no SCNE at all.
- **The Nameplate Atlas exported as gibberish and now doesn't.** `names` is a
  1024x32 horizontal character strip; the descriptor reader was transposing it
  to 32x1024 and shredding every letterform. Only `VC_P8_LINEAR` orders its two
  size halfwords that way, so the 4,081 `A1R5G5B5` player strips are untouched.
- **Stadium geometry export is command-line only and now says so.** The
  Stadiums viewport renders private glTF exports but has no save-to-file
  control, so pointing its card at that page would have been another
  overpromise. Whole-model *import* still does not exist: only same-count
  position writers across 75 pinned targets, and no topology importer.

## v1.0 RC41 The Uniform Browser Comes Back, And Cards Stop Overpromising — 2026-07-28

- **Fixes a regression RC40 introduced.** Splitting Uniforms & Equipment into
  two tabs put the uniform browser behind a tab bar that had no styling at all,
  so it rendered in the platform's light style with near-unreadable labels. The
  tab strip is now styled for the dark theme and **Uniform Sets is always the
  landing tab**. Rosters & Players had carried the same unstyled tabs since it
  shipped and is fixed by the same rule.
- **Capability cards no longer imply you can edit from them.** A card is a
  description with no controls; only seven of the nineteen writers have a real
  workspace in the app. Clicking through to the facemask colours and finding a
  paragraph with an "Editable" pill on it reads as a broken button, and it was
  reported as one. Each writer card now either names the workspace that edits
  it, or says plainly that it is command-line only **and prints the command**.
- Twelve writers are command-line only today, including the facemask colours
  and the new All Textures lane. That is the honest state, and the next builds
  are the workspaces that change it.

## v1.0 RC40 The Facemask Option Is Actually On Screen — 2026-07-28

- **The facemask colours were switched on and still invisible.** Uniforms &
  Equipment builds its uniform-set browser around one capability
  (`nfl2k5.uniforms.all_visual`) and silently dropped the other three filed
  under that category -- the facemask/turtleneck packed colours, the Team Select
  cards, and the Detroit away runtime proof. Enabling one changed nothing a
  modder could see. The category is now two tabs: **Uniform Sets** and
  **Colours & Other Tools**, the same shape Rosters & Players already used.
- **The window said RC36 while running RC38.** `mod_editor.__version__` is what
  the title bar renders, and three releases bumped the changelog, STATUS.md and
  the docs without touching it -- so nobody, including us, could tell from a
  screenshot which build they were on. It is now checked against STATUS.md and
  the newest changelog heading, so it cannot drift again.

## v1.0 RC39 Your PNG Editor's Normal Export Now Works — 2026-07-28

- **"needs an exact 512×256 8-bit RGBA PNG with interlacing off" was half our
  fault.** The importer accepted only colour type 6 at bit depth 8,
  non-interlaced. An image editor saving a jersey normally writes colour type 2
  (RGB, no alpha) or 3 (indexed), because those are smaller -- so good art came
  back rejected with a message that read like the user had done something wrong.
- Every colour type and bit depth the PNG specification defines now imports:
  RGB, RGBA, greyscale, greyscale+alpha and indexed, at 1, 2, 4, 8 and 16 bits,
  interlaced or not, with `tRNS` transparency honoured. Each is widened to RGBA
  internally, so nothing about the retail side changed.
- Decoding is verified pixel-for-pixel against Pillow across every variant.
- **The size rule stays**, because it is the disc's rule and not ours: a texture
  occupies a byte span its index chain has to fill exactly, so an image of a
  different size genuinely cannot go there. The message now says that instead of
  telling you to convert a file that was already fine.

## v1.0 RC38 All Textures, And The Writers Stop Demanding One Exact Disc — 2026-07-28

- **New workspace: All Textures.** 36,761 of the disc's 57,208 textures can now
  be replaced from a PNG. That covers the things modders kept asking for and
  finding absent: the real teams' end-zone art, goalpost pads, `divots`, the
  `mark1`..`mark3` overlays, and the shared equipment textures `shoes_taped`,
  `wristband_qb` and the three `elbowpad_*` variants.
- Replacements are recompressed into the **exact byte span** the original
  occupied, so nothing on the disc moves and an image that cannot be made to
  fit is refused rather than shifting resources around.
- Only compressed, swizzled P8 textures whose index chain starts at the video
  buffer and whose palette follows it are editable. A1R5G5B5, A8R8G8B8, DXT1
  and VC_P8_LINEAR are refused, and the capability says so.
- **Four writers stopped demanding one exact disc image.** The audio lane, the
  generic texture import, the Crib bar-monitor patcher and the uniform colour
  patcher each gated on the whole container's size and SHA-256 -- so a legally
  dumped disc that differed from the developer's copy could not be used at all.
  Identity is now per-extent (`default.xbe` plus each touched pack), the same
  correction the load path already had. Pinned sector numbers and absolute
  offsets went with them; both are artifacts of how a disc was packed.
- **The facemask colour is on by default.** It was exposed but disabled.
- Proved on three legitimately different images of the same game: the project's
  canonical `.xiso`, a reporter's repack, and a reporter's pressed-disc read.
  The same two edits produced identical change counts at three different
  absolute offsets.
- Still not runtime-proved: no emulator was started, so on-screen visibility of
  a replaced texture is untested. Transport and byte-exactness are proved.

## v1.0 RC37 The Facemask Colour Is Named — 2026-07-28

- **The two `Unif` packed colour words now say what they own.** They were
  presented as "packed colours" whose "visual semantics remain incomplete",
  which is why a modder reported that nothing in the editor reads a facemask
  colour. The executable trace had in fact already resolved them:
  **word 0 is the facemask/faceshield tint** -- it reaches the selected
  `FACEMASK%02d` player records and the `LO_FACEMASK` / `HI_faceshield`
  materials, and a dedicated `facemask` scene colours `bar_01..bar_03` after a
  fixed darkening transform -- and **word 1 is the `HI_turtleneck` tint**, read
  only when a per-player two-bit selector is 3.
- This confirms the reported behaviour: **repainting the coloured square on a
  helmet texture cannot move the facemask**, because the facemask is a separate
  material fed by this value. That differs from CFB 2K3, where the square does
  drive it.
- Ownership is proved by static executable trace. A controlled runtime capture
  is still outstanding and the capability says so; the rung did not change.
- No writer, pin or file format changed.

## v1.0 RC36 Exporting A Team Kit Folder Works On Windows — 2026-07-28

- **Export Team Kit as a folder failed on Windows for everyone**, with
  `[WinError 5] Access is denied` naming a temporary path, which reads like a
  drive or permissions problem rather than a bug in the app.
- The export built the folder under a temporary name and published it by
  reserving the destination with `mkdir` and then renaming the finished tree
  onto that reservation. That is a POSIX idiom: `rename(2)` there replaces an
  existing *empty* directory. **Windows `MoveFileEx` cannot replace a directory
  at all** -- documented, not a quirk -- so the second step always failed.
- It now publishes through `platform_compat.publish_no_replace`, which already
  existed and already knew the correct primitive per platform:
  `renameat2(RENAME_NOREPLACE)` on Linux, `renamex_np(RENAME_EXCL)` on macOS, and
  a plain `os.rename` on Windows, where refusing to overwrite is precisely what
  that call does for a directory. The no-clobber guarantee is unchanged: an
  existing destination is still refused rather than overwritten.
- **Also fixed, found in the same place:** the ZIP export published with a hard
  link. That is the right no-clobber publish on POSIX, but on Windows it needs
  NTFS, and an external drive holding disc images is frequently exFAT, where
  `os.link` fails outright. The same helper uses `os.rename` there.
- Guarded by a test that asserts the rule rather than the symptom: no shipped
  module may reserve a directory with `mkdir` and then rename onto it. It runs on
  any platform, which is the point -- the failure cannot be reproduced on Linux,
  where replacing a directory simply works.

## v1.0 RC35 Saving Works On Any Legal Dump — 2026-07-27

- **RC34 let you load and edit your disc; it could not save.** Building refused
  every image but the project's own, and the reason was layout rather than
  content.
  - **Sector numbers were pinned.** extract-xiso relocates files when it
    rebuilds an image: all nineteen files sit at different sectors in a pressed
    disc, in an extract-xiso rebuild and in a repack, while every file is
    byte-identical. Pinning the sector meant no other image could ever match.
  - **Absolute byte offsets were pinned.** `1,631,188,992 + pack_offset` is
    where pack 0 happens to sit in this project's rebuild; on a pressed disc it
    is somewhere else entirely, so every downstream read would have landed in
    the wrong place.
  - The Crib scene texture was read at a pinned absolute offset. It now locates
    pack `c` by name -- names do not move -- and derives the span from wherever
    that pack actually starts.
- Sizes and content hashes are still verified exactly, because those are
  properties of the game rather than of the image someone built. What is gone is
  only the requirement that a file sit where ours does.
- Verified by building real mods from a reporter's own two images: a
  7,825,162,240-byte pressed-disc read and a 6,300,958,720-byte repack, each
  producing an output the size of its own source. Same span bytes read from
  5,399,363,856 in one image and 5,661,790,480 in the other.

## v1.0 RC34 Every Legal Dump, All The Way Through A Build — 2026-07-27

- **A genuine disc read is finally accepted.** Three separate causes, each
  hidden behind the last, all found against a real user's ISO:
  - A raw disc read contains **two** filesystems -- the video partition at byte 0
    holding only a placeholder, and the game further in. The reader stopped at
    the first one it found, saw no `default.xbe`, and called the disc wrong.
    Partitions are now enumerated and the one containing the game is chosen.
  - A **pressed disc marks its files `0x80`** (NORMAL). The reader demanded the
    ARCHIVE bit `0x20`, which extract-xiso happens to set on everything it
    rebuilds. On a real disc that rejected every file, `default.xbe` included.
    A node is now simply a directory or a file.
  - The generated game index embedded its pack path with `str()`, which is
    backslashes on Windows and three more bytes once JSON escapes them, so the
    index could not match its own pinned hash.
- **Build works too, not just loading.** The build lane still required the user's
  container to equal the project's own rip in three places, so an image that had
  loaded, indexed and been edited was refused at the last step. Container
  equality is gone; every copy length now follows the user's actual file, and
  identity comes from the located game partition, its file count and
  `default.xbe`.
- Audio preparation, the stadium writer and the stadium build lane carried the
  same container pins and are fixed the same way.
- **Stadium Studio no longer depends on which zlib you have.** It pinned the
  bytes of a PNG it generates, and zlib-ng -- shipped as the system zlib on
  Fedora 40+ and openSUSE -- emits different but perfectly valid output. It now
  verifies the decoded pixels, which are identical everywhere.
- Verified against the reporter's own two images: a 7,825,162,240-byte raw disc
  read and a 6,300,958,720-byte repack. Both are recognised, both index fully
  (16 packs, index byte-identical to its pin), and both pass the build lane's
  source validation.

## v1.0 RC33 The Game Index Is Byte-Identical On Windows — 2026-07-27

- **Fixed the error every Windows user hit, whatever disc image they had:**
  "The generated game index did not match NFL 2K5". The index was written in
  text mode, and text mode on Windows turns every `\n` into `\r\n`. With
  2,289,506 newlines in it, Windows produced a 58,035,920-byte file where the
  pinned size is 55,746,414 — same game, same packs, different bytes. It was
  never possible for a Windows user to get past this step, and the message
  blamed their game when nothing about their game was wrong.
- Fixed as a class rather than a line: **38 text writes across 29 shipped files**
  now pin the line ending, so nothing generated by this product can differ
  between platforms again. The shipped surface is at zero unguarded text writes,
  enforced by a test.
- The index content is unchanged — regenerated from the same packs it still
  hashes to the pinned value, with zero CRLF bytes.

## v1.0 RC32 Find The Filesystem, And Import On Windows — 2026-07-27

- **A raw disc read is accepted now, whatever tool made it.** RC31 checked a
  *list* of four known game-partition offsets, which is the same mistake as
  checking one, only with four guesses — and a real user's rip was not among
  them, so it was still refused. The reader now **searches** for the XDVDFS
  header rather than guessing where it should be, confirming a candidate by
  requiring the magic at both ends of its sector and a root directory that fits
  inside the image. Offsets nobody here has ever seen now work.
- **Fixed the error that reached people who install rather than unzip:**
  `Could not catalog the game files: ModuleNotFoundError: No module named
  'nfl_outer'`. The product runs `tools/*.py` as subprocesses and those scripts
  import each other. Any ordinary Python adds a script's own directory to
  `sys.path`; the embeddable runtime inside the installer does not, because a
  `._pth` file defines the path outright. So this failed **only** on installed
  Windows copies — not from the tarball, not in CI, not from source. Every
  shipped tool now restores its own directory, and the `._pth` lists
  `app\tools` as an independent second guard.
- Both are covered by tests that need no game data and no Windows: one resolves
  partition offsets deliberately absent from the known list, the other launches
  every shipped tool with its directory removed from `sys.path`. The second one
  immediately found six tools a hand-written check had missed, including
  `apf_texture_patch` and `apf_roster`.

## v1.0 RC31 Any Legal Dump Of The Disc — 2026-07-27

- **Your own dump of ESPN NFL 2K5 is now accepted, however you made it.** The
  editor used to require a file whose size and SHA-256 exactly matched the
  project's own rip, and it looked for the disc filesystem at the one offset an
  extracted `.xiso` puts it at. Both are properties of a *container*, not of a
  game, so people holding perfectly legal copies were told their file "is not
  the supported NFL 2K5 Xbox XISO" or was not the USA version. Two real reports
  drove this: a full raw disc read of 7,825,162,240 bytes, and a repack of the
  same game 224 sectors longer than ours.
- The filesystem is now *located* rather than assumed. A game partition at byte
  0 (extracted `.xiso`) and at the XGD1/XGD2/XGD3 raw-read offsets are all read
  identically, and trailing padding no longer matters.
- Identity now comes from `default.xbe` inside the image. That is the game; the
  wrapper around it is not.
- **Nothing was relaxed about the bytes you edit.** The archive packs pulled out
  of your image are still verified against their pinned SHA-256s, the derived
  game index against its own, and every writer still checks the exact extents it
  touches before and after. Those cover the bytes that matter, which a
  whole-file hash never did. Eleven separate checks moved from "equals our copy"
  to "is the right game"; the guarantees they were standing in for are all still
  enforced.
- Loading is also much faster: recognition hashes an 11.9 MB executable instead
  of 6.3 GB.

## v1.0 RC30 Off-Linux Direct Uniform-Colour Copy — 2026-07-27

- Fixed `tools/nfl_uniform_color_xiso_direct_patch.py`, whose whole-XISO copy
  called the Linux-only `os.copy_file_range` inside `except OSError`. On Windows
  and macOS the syscall does not exist, and its absence raises `AttributeError`,
  which that clause never caught — so the portable `pread`/`pwrite` fallback the
  function documents could not run and the copy aborted instead. The syscall is
  now resolved before the loop, and the fallback is chosen rather than crashed
  into. On Linux the accelerated path is unchanged.
- No capability, pin, writer contract or editable count changed. This is the 2K5
  half of the same portability sweep that produced APF `0.1.0-alpha.35`; the
  shared guard is `tests/mod_editor/test_shipped_tools_posix_only.py`, which
  drives every shipped writer with the POSIX-only names deleted from `os` and
  needs no retail data to do it.

## v1.0 RC29 Project-backed Audio Cue Labels — 2026-07-20

- Added custom titles and multiline notes for every playable standalone cue
  and indexed streaming range. Labels are keyed by stable logical cue ID, so
  shared physical aliases may carry separate human meanings.
- Added immediate title/note search, a **Labeled only** filter, pencil-marked
  table names, original game-label/ID preservation, character counters, and
  per-cue Save/Clear controls in the Audio inspector.
- Added deterministic `audio-annotations.json` project persistence with exact
  manifest filename, size, count, and SHA-256 binding. Annotation-only projects
  are valid; legacy projects remain compatible.
- Added one-action Undo and Revert All coverage plus autosave recovery. Cue
  labels are counted separately from game edits and never enable Build or
  enter the canonical XISO provider document.
- Retained unsaved title/note drafts while browsing, paging, or changing Audio
  filters. Labeled-only controls now appear only for project-backed hosts.
- Carried custom titles, notes, and the preserved game/catalog name into local
  matching and shortlist ZIP manifests; playlists use the custom title while
  stable IDs and canonical payload paths remain unchanged.
- Made project import, mixed Revert All, and its Undo atomic across PNG, WAV,
  text, Stadium, Crib, and cue-label state. Disk-full or final handoff failure
  restores the prior manifest/ledgers and removes the disposable candidate.
- Bounded user metadata to 54,421 logical cues, 120 title characters, 2,000
  note characters, and 16 MiB of UTF-8 text. NUL/unsupported controls,
  Unicode format controls, duplicate JSON keys/IDs, rich-text interpretation,
  malformed metadata, undeclared members, and checksum/size mismatches are
  refused.
- No retail audio, decoded PCM, source path, physical offset, rollback byte, or
  game asset is stored in an annotation or annotation-only project.

## v1.0 RC28 Audio Pack Preview and Apply — 2026-07-20

- Replaced one-click Audio replacement-pack import with an explicit two-step
  **Preview → Apply** workflow. Preview fully validates the folder or ZIP,
  manifest/source binding, baselines, supplied file set, WAV shapes, origin
  authorization, current staged bytes, and shared physical aliases without
  changing the project, manifest, Undo history, replacement tree, or source
  XISO.
- Added a frozen, sanitized preview summary for modders: supplied, would-change,
  already-current, restore-original, unique physical change/restore, linked
  alias, and resulting Modified counts, plus a bounded list of readable change
  labels. An unchanged-only pack succeeds as a preview but offers no Apply.
- Bound confirmation to an opaque session-local token covering the exact pack
  member digest, schema, loaded source, session identity, and monotonic
  project/audio mutation revision. The token is hidden from result
  representation and neither the public preview nor the session retains ZIP
  paths, WAV bytes, private source hashes, or private member hashes.
- Apply reopens the chosen pack, snapshots caller-controlled WAVs privately,
  reruns every validation, verifies the preview token, and only then performs
  the existing single atomic Undoable transaction. A changed valid WAV, source,
  session, or project state is refused and requires a new Preview.
- Added the confirmation dialog's logical-versus-physical counts, explicit
  restore and linked-alias disclosures, first-change labels, Cancel/no-change
  paths, and worker-drain handoff so Preview fully finishes before Apply starts.
  The release candidate remains headless; no audible-runtime claim is added.

## v1.0 RC27 All Playable Audio — 2026-07-20

- Made **All Playable Audio (54,421)** the default Audio scope. Its canonical
  order is domain-prefixed and stable: all 850 standalone `AUDO` rows first,
  followed by all 53,571 indexed streaming ranges. Complete streaming banks
  and opaque raw containers remain in their dedicated scopes because they are
  not individual playable sounds.
- Added combined search, stable paging, family filtering, and one global
  **Modified** filter without wrapping or changing either row type. Search
  reuses the existing standalone/range metadata haystacks instead of retaining
  another 54,421 copies of searchable strings.
- Kept meaning-confidence honest: the 1/152/697 confidence groups remain
  standalone-only and are not partially applied to the mixed scope. Select
  **Standalone sounds** to use them.
- Added bounded matching export for 1–256 mixed results as current playable
  WAVs. Each record keeps its truthful retail-derived or user-replacement label;
  raw `.bin` export remains available only from the dedicated streaming-bank or
  indexed-range scopes.
- Preserved the frozen v4 **all-850 standalone** replacement-pack contract. RC27
  does not claim an all-54,421 template: streaming ranges continue to use
  per-row Replace or the existing 1–256 selected-shortlist replacement pack.
- Closed the release candidate headlessly: the complete cross-title suite
  passes **1090/1090**, the 2K5 slice passes **603/603**, the release-focused
  selection passes **122/122**, and the Audio/Crib/project lifecycle selection
  passes **40/40**. Independent adversarial review reports GO with no P0/P1
  finding. No visible desktop, pointer, audio device, emulator, or external
  player was used.

## v1.0 RC26 Read-only Audio Waveforms — 2026-07-20

- Added an explicit **Load waveform** view for all 850 standalone cues and all
  53,571 playable streaming ranges. It reads the selected sound's private
  current PCM16 WAV, including a staged replacement, without autoplay or any
  project mutation. Whole streaming banks and opaque raw containers remain
  honestly unavailable as single waveforms.
- Kept long sounds bounded: the reader retains at most 640 normalized envelope
  columns and samples no more than 1,024 frames per column. It opens only a
  regular non-link file, detects a WAV that changes during reading, and leaves
  the private WAV byte-for-byte untouched.
- Bound the waveform to the exact source, selection, and current audio content.
  Replace, Revert, batch import, project load, Undo, Revert All, selection
  changes, and source transitions invalidate both stale waveforms and playback,
  even when the logical asset ID remains the same.
- Added **Cancel waveform** with truthful limits: bounded sampling is
  cooperative, while an in-process source decode finishes before its now-stale
  result is discarded. Audio and Crib now share one mutually exclusive worker
  lane; global actions and sibling editors remain fenced until its owner drains,
  while the owning Audio page keeps waveform Cancel reachable.
- Added seven bounded-reader tests and seventeen shell-integration tests for signal
  edges, direct and visible action fences, close refusal, autosave deferral, and
  same-ID invalidation, then expanded the lifecycle matrix for Audio/Crib mutual
  exclusion and source/project/save/recovery/Undo/Revert-All completion order.
  The complete combined headless suite passes **1088/1088**, the current 2K5
  slice passes **601/601**, the release-focused selection passes **107/107**,
  and the final independent review is GO with no P0/P1 finding. No visible
  desktop, audio device, emulator, or external player was used.

## v1.0 RC25 Recoverable Audio Curation — 2026-07-20

- Made Audio shortlist **Clear** reversible. After clearing 1–256 selected
  sounds, the same control becomes **Undo** and restores every standalone cue
  and streaming range in its exact prior order.
- Keeps one deliberately bounded restore snapshot. A successful add/remove
  consumes it, and a successful source load clears it; searches, filters,
  exports, project navigation, and a refused source load do not. Clear/Undo is
  session-only and emits no replacement/project mutations.
- Preserved the 930-pixel Audio-toolbar contract. The compact visible label is
  **Undo**; its accessible name, tooltip, and progress copy carry the restored
  count and behavior. Longer count-bearing labels were measured and rejected
  because they widened the panel.
- Closed a failed-source-load lifecycle bug found during independent review.
  Because source loading commits transactionally, a refused replacement source
  now restores the still-valid old Audio page/actions (or the honest empty Load
  XISO state on a first-load failure) while the invalidated preview stays stopped.
- Six new headless tests cover browser/review Clear, mixed 256-sound exact-order
  restoration, no project mutation, undo expiration, current/pending old-query
  recovery, and first-load refusal. The complete headless/offscreen product
  regression passes **1034/1034**, and the focused Audio/UI/source-bound/
  packaging selection passes **118/118**. No visible GUI, audio device,
  emulator, or external desktop player was launched.

## v1.0 RC24 Applied Audio Search Results — 2026-07-20

- Bound every Audio catalog page to the exact source epoch, search text, scope,
  family, edit status, and meaning-confidence controls that produced it. The
  220 ms typing debounce can no longer leave page-wide actions attached to the
  previous result set.
- Immediately disables and independently guards **Add this page**, **Add all
  matching**, **Export matching audio**, Previous, and Next while a new search
  is pending. The counter says **Updating audio results…** until the refreshed
  page is actually installed.
- Keeps safe selected-row work responsive during that brief update: Play,
  Export, Replace, Revert, and **Add selected sound** still target the exact row
  that remains visibly selected.
- Stops a pending search timer when a filter, scope, Soundtrack quick view, or
  source transition performs an immediate refresh. Shortlist-review pagination
  remains independent and usable.
- Five new offscreen race regressions cover stale page-add, matching export,
  all-matching requery/warnings, pagination/selection stability, and automatic
  timer application; a sixth covers the fast type/erase round trip. The complete
  headless/offscreen product regression passes **1028/1028**, and the focused
  Audio/UI/source-bound/packaging selection passes **112/112**. No visible GUI,
  audio device, emulator, or external desktop player was launched.

## v1.0 RC23 Selection-Bound Audio Preview — 2026-07-20

- Bound every preview request to a monotonically increasing source/selection
  epoch and exact asset ID. A delayed preparation success or error from A can
  no longer act after A → B → A, and a source switch invalidates old callbacks
  even when the new game exposes the same asset ID.
- Centralized all effective Audio selection changes. Refreshing the same row
  preserves current playback; selecting a different row, leaving a result set,
  or resetting the source stops the controlled player and restores **Play**.
- Queued one-click playback for a newly selected row while the old controlled
  process finishes stopping, instead of requiring a second click or racing two
  processes. The queue also drains when the old process reports FailedToStart,
  whose Qt signal path has no later `finished` event.
- Removed the unowned desktop-handler fallback. Playback now uses only
  `ffplay`, `paplay`, or `aplay`, which Mod Studio can stop; if none exists, the
  UI gives an actionable install message. Preparation/start failures clear all
  pending preview state instead of leaving **Preparing…** stuck.
- Source loading invalidates Audio before its worker begins and disables the
  embedded Audio panel for the entire global blocking operation. Five new
  Audio lifecycle tests plus one shell-order test prove these transitions.
- The complete headless/offscreen product regression passes **1022/1022**, and
  the focused Audio/UI/source-bound/packaging selection passes **106/106**. No
  visible GUI, audio device, emulator, or external desktop player was launched.

## v1.0 RC22 Responsive Audio Toolbars — 2026-07-20

- Reflowed the five Audio search/filter controls and seven shortlist controls
  into two deliberate rows instead of two oversized single-row toolbars. Every
  control remains visible; no action moved into an overflow menu.
- Reduced the Audio panel's normal minimum-width hint from 1,442 to 833 pixels.
  A conservative worst-case state—256-result add/review/export labels and a
  full shortlist counter—fits at 930 pixels, within the main window's 932-pixel
  workspace at its supported 1,180-pixel minimum width.
- Added an offscreen geometry regression that pins every grid position, applies
  the longest labels together, and proves all 12 controls are inside the panel,
  non-overlapping, and at least their own minimum usable width.
- Kept Audio behavior unchanged: search debounce, filters, selection, shortlist
  order, exports, replacement state, and Build routes use the same controls and
  signal connections as before.
- The complete headless/offscreen product regression passes **1016/1016**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **100/100**. No visible GUI or emulator was launched for this checkpoint.

## v1.0 RC21 Scrollable Audio Inspector — 2026-07-20

- Made the dense selected-sound inspector vertically scrollable while keeping
  the WAV drop target and Play/Export/Replace/Revert actions pinned below it.
  Long ownership lists can no longer push the actions out of reach.
- Preserved the complete technical truth. Names, exact IDs, format/WAV
  contracts, ownership and alias warnings, shared-slot owner IDs, and the
  all-850 replacement path remain unabridged and wrap without changing their
  copied text.
- Made the title, technical metadata, ownership details, action requirements,
  and pack path selectable by mouse and keyboard, with explicit accessible
  names for assistive technology.
- Reset the inspector to its top whenever the selected row changes, and reduced
  its bounded minimum width from 360 to 320 pixels. This checkpoint fixes the
  detail pane's constrained-height behavior; the separate single-row toolbar
  width is not claimed as solved here.
- The complete headless/offscreen product regression passes **1015/1015**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **99/99**. No visible GUI or emulator was launched for this checkpoint.

## v1.0 RC20 Add All Matching Audio — 2026-07-20

- Added a separate **Add all matching** Audio action beside **Add this page**.
  It collects one complete 1–256-row filtered result across Standalone Audio or
  Playable streaming ranges while preserving canonical order and keeping
  already-selected IDs once.
- Made the critical reviewed-label workflow one action: **Meaning confidence →
  Reviewed labels (152) → Add all matching (152) → Selected shortlist (1–256)**.
  The exported v2 replacement template receives those exact 152 IDs in the
  visible shortlist order.
- Kept the operation atomic and session-only. The current search, scope,
  family, edit status, meaning confidence, stable count/order, row types, and
  unique IDs are rechecked before mutation; an overflow or changed/hostile
  result adds nothing and never touches project replacements.
- Complete streaming banks and raw BANK/ABNK/WBNK containers remain ineligible,
  and results above 256 ask the modder to narrow the filters.
- The complete headless/offscreen product regression passes **1014/1014**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **98/98**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC19 Audio Meaning-Confidence Filter — 2026-07-20

- Added a dedicated **Meaning confidence** filter to Standalone Audio with the
  exact v4 cue-map groups: **Menu Back route (1)**, **Reviewed labels (152)**,
  and **Provisional labels (697)**. This signal no longer has to be inferred
  from warnings or confused with the separate Editable/Modified status filter.
- Used the same public `standalone_runtime_meaning_status` contract for CSV
  generation, catalog-host browsing, and the product facade. Filtered counts,
  pagination, search, family/edit-status combinations, and matching collection
  export therefore resolve the same canonical rows.
- Disabled and reset the filter for streaming banks, indexed AUSB ranges, and
  raw universal containers, where the standalone meaning domain does not apply.
  Shortlist review temporarily disables it without losing the underlying
  standalone selection.
- Preserved the honest boundary: all 850 physical standalone slots remain
  Editable. “Provisional” means the human label/runtime caller is unproved; it
  does not mean the fixed writer target is approximate or unsafe.
- The complete headless/offscreen product regression passes **1009/1009**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **93/93**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC18 In-App Audio Pack Paths — 2026-07-20

- Added an **All-850 replacement pack path** card to every standalone Audio
  detail view. It shows the exact generic v4 destination used by
  `AUDIO-CUE-MAP.csv`, so modders can move from search/playback to authoring
  without manually finding the same row in a spreadsheet.
- Added a selectable path and keyboard-accessible **Copy pack path** action with
  **Ctrl+Shift+C**. Clipboard access occurs only after explicit activation;
  browsing, selecting, filtering, and paging never replace clipboard contents.
- Derived the path from the same canonical catalog order used by v3/v4 export.
  The UI receives only `replacements/NNN__selected-audio.wav`; it does not gain
  physical selectors, offsets, source fingerprints, or other private metadata.
- Kept the boundary obvious: complete streaming banks, indexed AUSB ranges, and
  raw universal containers hide and disable the standalone-only action. Their
  existing selected-shortlist/export workflows are unchanged.
- The complete headless/offscreen product regression passes **1006/1006**, and
  the focused Audio UI/backend/streaming/facade/packaging selection passes
  **90/90**. No GUI or emulator was launched for this checkpoint.

## v1.0 RC17 Human-Friendly 850-Sound Cue Map — 2026-07-20

- Added `AUDIO-CUE-MAP.csv` to the default **All standalone sounds (850)**
  authoring hand-off. Each canonical row now connects its generic replacement
  filename to the public Audio-browser ID, display name, family, duration,
  channels, sample rate, exact frame count, edit route, legacy membership, alias
  status, and honest runtime-meaning status. Modders no longer have to manually
  cross-reference 850 raw IDs before authoring WAVs.
- Introduced a dedicated v4 format instead of changing the shipped v3 contract.
  Direct complete exports without the new map still produce byte-identical v3
  packs; v1 legacy, v2 selected, v3 complete, and v4 mapped packs all import.
  The GUI chooses v4 for the one-click all-850 workflow.
- Made the CSV deterministic, UTF-8/LF, single-line, formula-safe, and read-only
  reference metadata. Import verifies its exact manifest path, schema, row
  count, SHA-256, canonical row order, columns, values, and 1/152/697 meaning
  status distribution before any WAV can change the project. Modders can copy
  the CSV outside the pack for personal notes; a changed or reordered in-pack
  map is refused rather than silently trusted.
- Kept the hand-off retail-free: the new map contains no WAVs, decoded PCM,
  physical offsets, source/private audio fingerprints, rollback bytes, or
  originals. The template still binds to the user's whole source XISO, missing
  replacement WAVs still mean “skip,” and all accepted changes remain one
  atomic Undo action.
- The complete headless/offscreen product regression passes **1005/1005**, and
  the focused audio/facade/GUI/packaging selection passes **83/83**. No GUI or
  emulator was launched for this checkpoint.

## v1.0 RC16 Complete 850-Sound Authoring Pack — 2026-07-20

- Made **All standalone sounds (850)** the default batch-authoring choice in
  Audio. One click now exports a complete metadata-only folder or deterministic
  ZIP for Menu Back plus all 849 fixed-AUDO slots; modders can fill only the WAV
  paths they want to change and import all true changes as one Undo action.
- Added a dedicated v3 pack contract instead of changing either existing
  format. The v3 route validates the exact canonical 850-row source order,
  unique logical IDs and underlying physical selectors, one Menu Back row,
  exact PCM16 contracts, the whole-XISO SHA-256 binding, and current-edit
  baselines. Public rows do not expose those physical selectors. Missing
  replacement WAVs mean “skip”; changed guide/manifest/order, unknown or
  duplicate rows, invalid WAVs, stale baselines, and extra archive members fail
  before the project changes.
- Preserved both older workflows. Legacy v1 remains the same frozen ordered
  153-cue format, while selected v2 remains an ordered 1–256-sound pack that can
  mix standalone cues with exact soundtrack, commentary, crowd, stadium, and
  presentation ranges. Whole streaming banks remain excluded from all three.
- Kept hand-off files retail-free by construction. An empty v3 template contains
  only `EDIT-AUDIO.md`, `audio-replacement-pack.json`, and the empty
  `replacements/` directory marker—never original WAVs, decoded audio, game
  offsets, private per-audio PCM fingerprint inventories, originals, or
  rollback bytes. It does include the whole-XISO SHA-256 needed to bind the
  hand-off to the user's own source. The clean 144-file release stage
  independently reproduces the all-850 manifest and reports
  `private_inventory=false` and `retail=false`.
- The complete headless/offscreen product regression passes **1001/1001**, and
  the focused audio/facade/GUI/packaging selection passes **79/79**. RC16 does
  not claim that provisional cue names are semantically correct or that every
  edited slot has been heard in-game; those 697 uncertain rows retain their
  prominent physical-slot/runtime-meaning warning.

## v1.0 RC15 Complete Standalone Audio Editing — 2026-07-20

- Promoted all **850 standalone AUDO sounds** to Editable. Menu Back keeps its
  separate fixed-target route; all 849 other rows use stable outer/chunk IDs,
  exact non-overlapping physical allocations, strict per-row PCM16 shape
  validation, deterministic Xbox IMA encoding, and the unified copied-XISO
  build path.
- Replaced the old hidden lock on 697 alias-related rows with an honest warning:
  the physical slot being changed is exact, but its provisional name, semantic
  cue identity, and runtime selector owner may be unknown. Matching names or
  decoded content do not collapse distinct spans or imply that another slot
  changes.
- Preserved old v1 replacement packs exactly. **Legacy 153-cue pack** still
  resolves only Menu Back plus the original 152 classified rows in the same
  order; **Selected shortlist (1–256)** can now author any of the newly unlocked
  physical slots alongside exact AUSB soundtrack, commentary, stadium, crowd,
  and presentation ranges.
- Updated the capability registry, Audio panel copy/accessibility, product docs,
  runtime closure receipt, and pinned provider closure to report 850 Editable /
  0 Export-only standalone rows. Complete raw streaming banks remain
  Export-only; RC15 does not claim recovered cue names, loops, gain/pan,
  priority, mixer ownership, or audible runtime consumption.
- The complete headless/offscreen product regression passes **993/993**. A
  compatibility regression pins the RC14 ordered 153-ID set to SHA-256
  `156c3a02e4ef27ee1a245a0946a3033575dc3d30872f1664b2adf1dfbd488ecc`;
  the public stage separately proves all 850 modern edit routes while preserving
  the legacy manifest/guide contract.

## v1.0 RC14 Roster Workspace Navigation — 2026-07-20

- Moved the complete current and historical name/number workflow to the place
  modders expect it: **Rosters & Players → Players & Numbers**. The same page
  keeps **Portraits & Faces** one tab away, so a player can be renamed,
  renumbered, and visually updated without jumping to an unrelated category.
- Kept **Text & Team Identity** focused on the universal fixed-allocation text
  browser. No writer, project schema, source allocation, or build behavior
  changed; this checkpoint fixes product navigation and discoverability.
- Split the shared text/roster panel into scoped views. Each sidebar workspace
  now constructs and reloads only its own models instead of processing 23,346
  text rows and 6,522 roster rows twice. The legacy combined view remains
  available to internal callers and tests.
- Preserved source/project reload, Undo, Revert All, autosave, status reporting,
  and Ctrl+F routing across current players, historical players, portraits,
  faces, and universal text. All work and verification remained headless; no
  emulator or visible desktop session was launched.
- The final focused navigation/edit selection passes **44/44**, including real
  Apply operations in both scoped views. The complete headless desktop-tool
  regression passes **992/992**, and independent review returned **GO** after
  the scoped change-refresh path was exercised directly.

## v1.0 RC13 Modified-Range Collection Parity — 2026-07-20

- Fixed the last collection-export mismatch after fixed-range AUSB editing
  shipped. **Export matching audio** and **Export selected WAVs** now include a
  Modified streaming range's staged user-replacement WAV, in order, exactly as
  individual Play and Export WAV already do.
- Kept the retail boundary explicit: an unmodified range is still labeled
  `retail_derived`; complete streaming banks and exact raw-range `.bin` exports
  can never be labeled as user replacements. Collection ZIPs remain private
  listening exports and never enter project, Undo, recovery, or Build state.
- Improved keyboard search routing so the global **Ctrl+F** action discovers the
  visible search field in Text & Team Identity, The Crib, Playbooks, and other
  product workspaces instead of incorrectly reporting that the page has no
  search box.

## v1.0 RC12 Selected Audio-Shortlist Authoring Packs — 2026-07-20

- Added **Selected shortlist (1–256)** beside the existing **All standalone
  cues (153)** replacement-pack mode. A modder can now curate any ordered mix
  of Editable standalone cues and fixed-slot soundtrack, commentary, stadium,
  crowd, or presentation ranges, export one metadata-only folder/ZIP, fill only
  the desired WAV paths, and import all true changes as one Undo action.
- Kept old v1 153-cue packs compatible. New v2 packs preserve the shortlist's
  logical order and exact PCM16 channel/rate/frame contracts. They carry only
  logical IDs, user-replacement baselines, source binding, and disclosed logical
  alias owners—never physical slot IDs, offsets, bank filenames, private source
  fingerprints, original audio, or rollback bytes.
- Reused the shipped fixed-range writer and authorized batch transaction instead
  of adding another encoder. Every supplied WAV crosses exact shape and private
  source-origin checks before commit. Identical files for two logical owners of
  the one shared AUSB slot collapse to one physical edit; divergent files fail
  before the project changes.
- Corrected stale product copy that called individually Editable streaming
  ranges browse/export-only. Complete raw banks remain Export-only: RC12 does
  not claim whole-bank repacking, recovered cue names, loop/gain/pan/priority
  editing, mixer ownership, or in-game audible consumption.
- Kept the listening shortlist broader than the authoring pack without making
  the mismatch mysterious. Playable-but-Export-only standalone sounds can still
  stay in a listening/WAV collection, but Selected-shortlist template export is
  disabled with an exact count and removal instructions until every chosen row
  is Editable.
- Kept the rights boundary honest. The private gates reject exact source PCM and
  unchanged excerpts covered by their deterministic window/anchor rules. They
  cannot prove authorship or classify transformed/re-encoded copyrighted audio;
  mod authors remain responsible for what they use and distribute.
- The final headless/offscreen desktop-tool regression passes **973/973** and
  the focused RC12 catalog/audio/GUI/packaging selection passes **75/75**. A
  clean 144-file public stage passes release → runtime closure → desktop/Bash →
  release, including a source-free ordered standalone+AUSB v2 export/import
  probe and `audio_replacement_pack_v2=selected_mixed` receipt. No source XISO,
  WAV, private audio inventory, GUI, or emulator entered this checkpoint.

## v1.0 RC11 Complete Fixed-Range AUSB Editing — 2026-07-20

- Promoted all **53,571 logical AUSB streaming ranges** to Editable through
  **53,570 exact physical fixed slots**. Replace accepts a canonical authored
  PCM16 WAV with the selected row's exact channel/rate/frame shape, encodes
  Xbox IMA into the unchanged allocation, and composes the resulting one-span
  or pack-seam edit with every other Mod Studio category. The 17 complete raw
  banks remain Export-only; this is not a general bank repacker.
- Added one physical edit state behind logical aliases. The one shared slot
  displays both affected owners; Replace, Modified filtering, Play, WAV export,
  Revert, Undo, Revert All, project save/load, and Build change them together.
  Identical duplicate alias requests collapse to one record, while divergent
  WAVs fail atomically before the project changes.
- Added automatic first-use source-audio preparation. The first Replace,
  standalone batch import, or shared audio-project load can build the complete
  private exact and containment indexes with in-app progress. It normally takes
  about 20–35 minutes once, keeps the source XISO read-only, releases the main
  facade lock while working, and refuses a source/project switch before staging.
- All authored WAV paths now cross the same immutable-byte origin gate when
  staging, saving, loading, building, and independently verifying. Exact source
  PCM and unchanged source excerpts are refused. A shareable `.2k5mod` contains
  only a logical asset ID plus the user's WAV; canonical slots, offsets, source
  fingerprints, private inventories, original audio, and rollback bytes never
  enter it.
- Added the real registry capability
  `nfl2k5.audio.ausb_fixed_range_wav`, bringing the shared registry to **62**
  rows and the NFL 2K5 product catalog to **31**. The init-free unified provider
  pins its exact 60-file execution closure and receives private origin inputs
  only for audio builds; visual-only validation/builds remain unchanged.
- The clean release-stage review contains 144 allowlisted files and passes its
  runtime closure with 46 product modules plus 22 tool modules. It includes no
  XISO, WAV, private inventory, decoded source audio, or other retail payload.
  Headless/offscreen tests cover the complete UI/session/project/provider path;
  no audible runtime cue-identity claim is made until a game spot-check exists.
- Completed one real-source, authored-WAV product-flow proof through Replace,
  Modified playback/export, retail-free project save, fresh-session project
  load, Build, and independent Verify. The one logical edit compiled to one
  physical span; Build and Verify both passed, the 6.30 GB source remained
  byte-for-byte unchanged, and the generated test output was removed afterward.
  This proves the offline product path, not in-game audibility or semantic cue
  ownership.

## Post-RC10 Audio Scale and Project-Bounds Checkpoint — 2026-07-20

- Precomputed the metadata-only Audio search index once per loaded source.
  Real-source searches across 53,571 indexed streaming rows now take roughly
  23–35 ms median instead of rebuilding every row's search text for about
  367–424 ms on each query. Reloading a source replaces the catalog and search
  index together; a focused lifecycle test proves terms from the old catalog
  do not survive.
- Added one shared limit of 25,000 simultaneous visual-plus-audio edits per
  `.2k5mod`, a 1 GiB aggregate replacement-payload limit, and an expanded ZIP
  preflight. Loading rejects excessive declared expansion and insufficient
  staging space before extracting a replacement. Saving uses a descriptor-
  pinned, single-link read for each authored WAV and refuses a project that
  would exceed either its expanded or 2 GiB archive boundary.
- Replaced the unified backend's quadratic span-overlap loop with a sorted,
  adjacent check. A worst-budget 25,004-span synthetic set validates in about
  3.24 ms while retaining the same out-of-order overlap refusal. The release
  gate now also rejects private `derived/` audio-origin cache trees, the exact
  fingerprint schema, and both containment v1/v2 schemas even if a future
  allowlist names or renames them.
- Added the isolated fixed-allocation AUSB codec/span backend and private exact-
  PCM inventory store as internal source slices. They cover 53,570 physical
  streaming slots behind 53,571 visible catalog rows, including one two-owner
  alias and four pack-seam slots. The independently reviewed read-only source
  scanner has now directly decoded all 850 standalone cues and all 53,570
  physical streaming slots, passed a final complete-XISO recheck, and published
  one 13.84 MiB private, metadata-only exact-PCM inventory. A clean second pass
  loaded it without rebuilding. The source XISO and archive cache were not
  modified.
- Added an independently reviewed exact-containment primitive as another
  internal source slice. Quarter-second source windows on a quarter-second grid
  guarantee detection of unchanged, same-shape excerpts at the roughly 500 ms
  bound; short and sparse cues use deterministic nonzero anchors, and only
  all-zero windows are exempt.
- Persisted the approved real-source containment census after a hostile review
  closed directory-swap redirection, concurrent-publication source rechecking,
  and arbitrary owner-label leakage. The read-only scan covered 54,420 cues /
  54,421 logical owners and published 615,244 digest records in a 152,956,258-
  byte private mode-0600 document. It stores no WAV, PCM, encoded sound, source
  path, or game span. A clean reuse load completed without re-decoding streaming
  payloads and repeated the complete source authentication.
- Added the sealed final-Build authorization boundary for all three fixed audio
  routes: Menu Back, standalone AUDO, and indexed AUSB. Both private origin
  checks receive the exact immutable WAV bytes later consumed by the encoder;
  a forged lookalike cannot cross the hand-off. The AUSB compiler emits exactly
  one physical span or one two-pack seam, binds aliases to one slot, deduplicates
  identical alias edits, and rejects divergent ones. Audio projects pass the
  canonical private inventories to both Build and independent Verify, while
  visual-only builds require neither file. Streaming Replace remains hidden
  until the shared session/project/Audio-panel wiring completes; no new runtime
  consumption claim is made here.

## v1.0 RC10 Accessibility and Layout Checkpoint — 2026-07-20

- Advanced the current product version to **v1.0 RC10**. The sidebar release
  label continues to derive from the package version, so the visible product
  name and the version checked by the release tests cannot drift apart.
- Added **Ctrl+F** as a window-wide shortcut for the active workspace's search
  box. It focuses the relevant search field, selects any existing query, and
  reports a short instruction in the operation-status area. Pages without a
  search box point the modder to category navigation instead.
- Added **Ctrl+1** as a window-wide shortcut for the complete modding-category
  sidebar. The category list advertises the shortcut in its tooltip and
  assistive description, so mouse-free navigation is discoverable inside the
  product.
- Added clear keyboard-focus outlines to the category list, asset lists, and
  component trees. Search fields, the current-operation label and progress
  bar, **Build Modded XISO**, and **Launch Latest Build** now expose concise
  accessible names and instructions for assistive software.
- Made the shell more tolerant of larger desktop fonts: the header and footer
  can grow instead of being trapped at one fixed height, while roomier category
  rows, primary controls, spacing, and padding keep the main workflow easier to
  scan and target.
- Added focused headless coverage for shortcut routing, active-page search,
  assistive copy, visible-focus styling, and expandable shell chrome. This
  checkpoint changes product navigation and presentation only; it does not
  claim a new asset writer or runtime game proof. No GUI or emulator was
  launched for the source-and-documentation checkpoint.
- Removed workstation-specific home, mount, workspace, and game-dump paths
  from the public changelog and nine reviewed visual catalogs. Those catalog
  fields now use stable relative provenance labels; selectors, allocations,
  resource hashes, and writer meaning are unchanged. The release gate now
  refuses either known private workstation prefix anywhere in staged UTF-8
  text while continuing to allow unrelated portable absolute-path examples.

## v1.0 RC9 Batch Audio Authoring Checkpoint — 2026-07-19

- Added **Export replacement template** and **Import replacement pack** to the
  Audio workspace for all **153 currently Editable standalone cues**: 152
  fixed-AUDO slots plus Menu Back. The folder/ZIP template contains only a
  canonical JSON manifest, editing guide, and empty `replacements/` directory;
  it exports **zero retail WAVs**.
- Each manifest row gives the stable asset ID, declared filename, writer route,
  and exact PCM16 channel count, sample rate, frame count, and no-metadata
  requirement. Modders add only their authored WAVs at the declared paths;
  missing paths are skipped.
- Import validates the complete manifest/source/current-project baseline,
  duplicate and unknown paths, every supplied WAV, and every exact cue contract
  before staging. All true changes commit as **one Undo action**. An invalid,
  stale, duplicate, unknown, or unchanged-only pack leaves the project exactly
  as it was, and a commit failure restores every touched cue. Batch Undo uses
  the same all-cues transaction: a failure restores every current WAV and the
  session manifest, keeps the Undo action available, and can be retried.
- The project boundary compares decoded PCM against every one of the 850
  standalone source cues, not merely the selected target. Moving cue A's
  source WAV into a same-shaped cue B path is refused at Replace, batch import,
  project save, and project load. Decoded streaming ranges already present in
  the user's private cache are source-verified and covered by the same rule.
- The batch route deliberately rejects streaming soundtrack, commentary,
  stadium, and presentation banks/ranges. Those remain browse/play/export-only
  until cue ownership, loop/mixer semantics, and reversible bank repacking are
  decoded. Per-cue Replace/Revert and replacement-only `.2k5mod` save/build
  remain unchanged.
- Added an output-drive free-space preflight before private build staging.
  A 2K5 build now refuses before creating any temporary file unless the
  selected filesystem can hold one complete XISO plus a 512 MiB safety margin.
  The error reports available space, required space, and the exact shortfall in
  GiB, then tells the modder to free space or choose another drive. The source
  and output stay untouched on refusal. Focused cross-title build-safety tests
  pass **32/32**.
- Closed the batch transaction and retail-sharing boundary under adversarial
  review. Same-contract cross-cue source PCM is refused during Replace, batch
  import, project save, and project load; verified source streaming PCM already
  in the private cache is covered too. Injected second-item failures during
  validation, commit, and Undo preserve the complete session tree, leave no
  hidden `.audio-pack-*` or `.audio-undo-*` files, retain the Undo ledger, and
  can be retried. Template publication and contract reads are descriptor-pinned,
  no-replace, hardlink-refusing, and maximum-plus-one bounded. Import captures
  the exact pre-edit snapshot first, validates that same snapshot against the
  exported baseline, and retains it as Undo state; an injected same-shape
  mutation during snapshot capture is refused before commit. The final
  eight-module dependent gate passes **99/99**; an independent rerun passes
  **93/93** relevant tests plus **16/16** standalone-audio tests.
- RC9 was the headless-tested package for this audio checkpoint; sealed RC8
  remained its previous immutable checkpoint. The exact 136-file stage and
  independent extraction pass release → runtime → release with no retail data,
  private inventory, links, or undeclared files. Packaged docs remain self-hash-free;
  the adjacent `.sha256` sidecar authenticates the portable archive. No GUI or
  emulator was launched while assembling or checking RC9.

## v1.0 RC8 Complete Team Kit Checkpoint — 2026-07-18

- Added **Complete Team Kit** directly to **Uniforms & Equipment**. A modder can
  export any highlighted physical uniform set, or resolve the selected team's
  HOME, AWAY, or paired HOME + AWAY style/variant, as either an editable folder
  or deterministic ZIP.
- Every exported physical set contains all **39 supported components**:
  torso/jersey, sleeve, pants, both live helmet families, jersey/helmet/arm
  digits 0–9, the vertical nameplate atlas, and all three independent Team
  Select cards. Each folder includes exact dimensions, stable labels,
  ownership notes, practical UV limitations, and `EDITING-GUIDE.md`.
- Team Kit import validates the source identity, unchanged manifest/guide,
  complete set inventory, current working baseline, every declared path, every
  PNG, exact dimensions, and decoded RGBA pixels before staging anything. It
  stages only real pixel changes as **one Undo action**; unchanged imports add
  no replacement and no Undo entry. A commit failure restores the prior
  project state.
- The bundle is intentionally source-bound. If the active source or any
  exported working pixels change after export, the modder must export a fresh
  kit. This refuses stale hand-offs instead of overwriting newer edits.
- Team Kit folders/ZIPs are private working exports and may reproduce retail
  artwork from the user's own disc. They must not be distributed. The existing
  `.2k5mod` route remains the shareable format and stores only authored,
  pixel-changed replacements plus logical metadata.
- Per-component Export/Replace/Revert remains intact for small changes. A
  successful Team Kit import enters the same modified badges, autosave,
  project, Revert, Build, and independent output-publication flow as individual
  edits.
- RC8's public allowlist and source-free runtime closure now include the Team
  Kit service explicitly. No retail template, private bundle, source XISO,
  original PNG, or generated preview is packaged.
- The focused Team Kit/session/facade/packaging selection passes **47/47
  tests**, and the complete current cross-title headless suite passes
  **489/489**. This checkpoint was assembled headlessly; no visible GUI or
  emulator was launched and the user's desktop was not touched. Exact release
  counts, archive hash, and extraction-parity receipt are recorded in
  `STATUS.md` and the archive's adjacent checksum sidecar after sealing.
- Post-seal visual QA passed on isolated `DISPLAY=:99`. A fresh
  `v1.0 RC8 • Xbox Edition` window loaded the recognized XISO and visibly
  presented the 39-component **Complete Team Kit**, paired `HOME + AWAY`
  scope, editable-folder selector, Import/Export actions, private-retail-art
  warning, and unobstructed footer. No clipping, overlap, spacing, padding, or
  alignment defect was found, and the user's active desktop/pointer was never
  used.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC8-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC8-20260718.tar.gz.sha256`
- Archive size: **9,667,067 bytes**
- SHA-256:
  `17254d4030806e8636c67a9b90cfcee88a7711484d9ab6ef079aba875e569466`
- The stage and independent clean extraction each contain **135 files**, **14
  directories including the root**, **101,871,957 file bytes**, **36
  executables**, and zero links or special files. The tar has **149 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **37 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical with normalized inventory SHA-256
  `df710e64f5e7f441dfa51908a161425478c0b1c9b210a3b06cc50f0ae924df10`.
- RC7 and RC6 were reverified after sealing RC8 and remain immutable at
  SHA-256 `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`
  and `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`,
  respectively.

## v1.0 RC7 Audio Review Checkpoint — 2026-07-18

- Added a dedicated **Review selected** workspace for the session Audio
  Shortlist. It shows only the curated playable sounds, supports Play/Stop,
  remove, and **Move up / Move down**, and returns to the exact browser scope,
  family, status, search, page, and selected row through **Back to browser**.
  Reordering changes the exported sequence but remains session-only: it does
  not dirty a project, enter Undo/recovery, or affect Build.
- Every multi-WAV Audio collection now includes an ordered `playlist.m3u8`.
  Its relative entries match the exact ZIP member order, so shortlist order is
  immediately playable in ordinary media software. `manifest.json` records
  the playlist path and WAV-record count. Raw-only collections deliberately
  omit a playlist and declare `playlist: null` / `playlist_record_count: 0`.
- Added **Raw Bank Containers** as a fourth Audio scope. It exposes the exact
  nine universal-index containers—three `BANK`, three `ABNK`, and three
  `WBNK`—with search, paging, metadata, and byte-exact local `.bin` export.
  These rows are truthfully Export-only: they cannot Play, Replace, Revert, or
  join the playable shortlist, and they never enter projects, recovery, Undo,
  modified state, or Build. The scope fails closed if the exact nine-row
  inventory is incomplete.
- RC7 changes only local review/export ergonomics. It does not claim decoded
  cue ownership or safe writeback for streamed or raw bank audio.
- The focused RC7 Audio/packaging selection passes **42/42 tests**; the complete
  current cross-title headless suite passes **475/475**. The clean stage passed
  release, runtime closure, source-free registry, desktop-entry, launcher
  syntax, and post-runtime release gates before publication.
- The required new-layout visual inspection remains a separate isolated-display
  gate; no GUI or emulator was launched while assembling this
  source and package checkpoint. The exact archive receipt is recorded in
  `STATUS.md` and the archive's adjacent checksum sidecar.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC7-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC7-20260718.tar.gz.sha256`
- Archive size: **9,658,588 bytes**
- SHA-256:
  `a4785f363505b3f66e2cb3b16ad04ce48b8194b421308670ac4437bce327f13f`
- The stage and independent clean extraction each contain **134 files**, **14
  directories including the root**, **101,801,912 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates;
  runtime closure remains **36 product + 22 tool modules**, **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**. The extraction is byte- and
  mode-identical with normalized inventory SHA-256
  `e80313e49d9acade03e4dc8668eb4dda0059f6fd3e47320d0f8104e832917031`.
- RC6 was reverified after sealing RC7 and remains immutable at SHA-256
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`.

## v1.0 RC6 Audio Shortlist Checkpoint — 2026-07-18

- Added a session-only **Audio Shortlist** for hand-picking standalone AUDO
  sounds and playable streaming ranges across unrelated searches, pages,
  families, and scopes. Selected rows carry a visible `★ Selected` status and
  an ordered **Selected _n_ / 256** count.
- Added **Add/Remove selected sound**, atomic **Add this page**, **Clear**, and
  **Export selected WAVs** actions. Complete streaming banks are deliberately
  excluded because a bank is not one playable cue; its indexed ranges remain
  selectable.
- The exact selected-ID exporter is independent of current browser filters and
  mixes original standalone WAVs, staged replacement WAVs, and decoded
  streaming-range WAVs in selection order. The existing transactional bundle
  manifest records `retail_derived` versus `user_replacement` origin.
- The shortlist survives normal refresh, search/filter/page/scope changes, and
  project loads for the same source. Only a successful new-XISO load clears it.
  It never enters `.2k5mod`, recovery, Undo, modified state, or Build.
- Invalid empty, duplicate, unknown, complete-bank, or over-256 selections fail
  before output. Existing destinations remain untouched, and a failed decode
  still leaves no partial ZIP.
- The focused Audio backend/offscreen-Qt selection passes **18/18 tests**. The
  complete current cross-title desktop-tool suite passes **443/443** with
  `PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen`.
- Isolated-display visual QA inspected the RC6 Audio workspace on `DISPLAY=:99`. The
  Soundtrack, matching-export, shortlist Add/Remove, Add-page, count, Clear,
  and Export-selected controls are readable and unclipped; the browser/detail
  layout remains usable without touching the user's desktop or mouse.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC6-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC6-20260718.tar.gz.sha256`
- Archive size: **9,643,071 bytes**
- SHA-256:
  `8c01d4c7b47a1907edbf090cb75346d2d68b24318ffccca062e1ecd32ed23bec`
- The stage and independent extraction each contain **134 files**, **14
  directories including the root**, **101,773,880 file bytes**, **36
  executables**, and zero links or special files. The tar has **148 members**.
- Both trees passed release/runtime/registry/desktop/Bash/post-runtime gates.
  Runtime closure is **36 product + 22 tool modules**, **60 registry
  capabilities**, **11 sections**, and **30 NFL 2K5 capabilities**; extraction
  is byte- and mode-identical.
- RC5 remains immutable. Its sealed SHA-256 is
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`,
  and its complete receipt is preserved immediately below.

## v1.0 RC5 Active Project Checkpoint — 2026-07-18

- Added normal document-style project identity: an opened or first-saved
  `.2k5mod` becomes the active project, its name appears in the window title,
  and an asterisk marks changes since the last successful named save/load.
- **Save** / **Ctrl+S** now updates the active project directly. **File → Save
  Project As…** / **Ctrl+Shift+S** owns first-time naming and separately named
  copies. Recovered edit sets remain visibly **Untitled** until named.
- Protected fast-save with an in-memory target fingerprint. A missing target,
  symbolic/hard link, path substitution, or external file change fails closed
  with a Save As instruction; the remembered project, live session, and private
  recovery state stay intact.
- Corrected dirty-state semantics so every authored mutation remains unsaved
  even when it reduces the current replacement count to zero. In particular,
  **saved project → Revert All** shows **No edits • unsaved**, keeps Save and
  the close/source/project data-loss gates active, and leaves Build disabled.
- Added an explicit empty-project route for GUI Save/Save As and private
  recovery. The archive contains only `project.json`, an empty edit list, and
  the existing `user-replacements-only` policy; accidental backend empty saves
  remain rejected by default.
- Added six headless project-document/target-safety tests and extended recovery
  and facade checks. The focused project, recovery, facade, and session
  selection passes 35/35 tests without a visible desktop; the complete current
  desktop-tool suite passes 428/428.
- Isolated-display visual QA inspected the clean RC5 candidate on `DISPLAY=:99`.
  **File** visibly exposes **Save Project** (`Ctrl+S`) and **Save Project As…**
  (`Ctrl+Shift+S`); both are correctly disabled in the clean, no-edit state,
  and the complete menu renders without clipped or overlapping text. The check
  did not touch the user's desktop or mouse.

### Release receipt

- Runnable tree: `2K5-Mod-Studio-v1.0-RC5-20260718/`
- Portable archive: `2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz`
- Checksum sidecar:
  `2K5-Mod-Studio-v1.0-RC5-20260718.tar.gz.sha256`
- Archive size: **9,639,953 bytes**
- SHA-256:
  `1e8304dd189cd7868c39d03eee6b6d77c04e02e22621ba582c635ec1e3e3d441`
- The tar contains **148 members**. Both the original stage and independent
  clean extraction contain **134 files**, **14 directories including the
  release root** (**13 internal**), **101,750,965 file bytes**, **36 executable
  files**, and **zero links**.
- The original tree and independent clean extraction both passed the
  release/runtime/registry/desktop/bash/post-runtime gates. Runtime closure is
  **36 product + 22 tool modules**; the registry exposes **60 capabilities**,
  **11 sections**, and **30 NFL 2K5 capabilities**.
- The full desktop-tool suite passes **428/428**. The immutable RC4 checksum
  sidecar was reverified unchanged after the RC5 seal.

## v1.0 RC4 Audio Collections Checkpoint — 2026-07-18

- Added a one-click **Soundtrack & music (136)** view and transactional
  **Export matching audio** for any 1–256 filtered standalone cues, raw banks,
  or indexed streaming ranges. The complete known music view fits the bounded
  route at 136 rows and about 1.22 GiB of decoded PCM before ZIP compression.
- Added a deterministic local-audio manifest with stable catalog IDs, physical
  bank/range coordinates, PCM metadata, payload SHA-256, and explicit
  `user_replacement` versus `retail_derived` origin. The artifact identifies
  itself as local-only and never enters a shareable `.2k5mod` project.
- Bundle creation is all-or-nothing, capped at 256 rows and 2 GiB of payload,
  refuses overwrite/symlink targets, and publishes only after every decode,
  size check, checksum, and manifest entry succeeds. A failed row leaves no
  partial ZIP and does not change edits, Undo, recovery, or Build state.
- Added the **Modified** filter for instant review of staged standalone WAVs.
  Streaming banks/ranges correctly return no Modified rows because their
  replacement route remains disabled.
- Isolated-display visual QA checked the final Audio layout on `DISPLAY=:99`. It
  caught Qt consuming the first ampersand as a mnemonic marker; the button now
  visibly reads **Soundtrack & music (136)**, and both filter/action rows,
  browser table, and detail pane remain unclipped.
- The complete cross-title product gate passes 419/419 tests. RC4 is a new
  immutable checkpoint; RC2, RC3, and their checksums remain unchanged.

### Release receipt

- Portable archive: `2K5-Mod-Studio-v1.0-RC4-20260718.tar.gz`
- Size: `9,645,491` bytes
- SHA-256: `acde381520b8b0efb26266977f5e4d657fb478ce91299ce9cd152f03d36b2e22`
- The exact 134-file stage contains `101,736,199` file bytes. Its 36-product /
  22-tool-module runtime closure, 60-row registry, 11 product sections, and
  source-free desktop construction checks passed before archiving and again
  after clean extraction.
- The adjacent `.sha256` sidecar is the authoritative archive checksum.

## v1.0 RC3 Product Checkpoint — 2026-07-18

- Packaged the working-tree advances that followed RC2: complete indexed AUSB
  range browsing/playback/export, dedicated Gameplay and Menus inspectors,
  source-bound autosave/recovery, recent files, and shared Save/Discard/Cancel
  data-loss gates.
- Polished the Audio workspace so all three scopes remain readable at normal
  desktop size. Standalone sounds retain their truthful edit controls; complete
  banks and indexed ranges now use visibly disabled Replace/Revert controls,
  concise ownership summaries, and full technical tooltips.
- Corrected alternating-row colors in the Gameplay and Menus tables, preserved
  literal ampersands in tab labels, and tightened local status copy so no table
  presents a white or misleadingly writable row.
- Added the APF digital-font provider to the exact clean-release closure. This
  fixes a real clean-stage import failure while keeping the 2K5 application
  package source-free and retail-free.
- Ran four current-code visual checks on isolated `DISPLAY=:99`:
  recovery/recent files, every Audio scope, the complete
  Gameplay inspector, and both Menus inspector modes. All controls, disabled
  states, tables, tooltips, and status labels rendered without clipping or
  overlap; the isolated QA window and synthetic recovery fixture were removed.
- Passed 404/404 desktop-tool tests headlessly, including both title backends,
  before assembling the non-overwriting RC3 release tree and archive. The
  archive is `2K5-Mod-Studio-v1.0-RC3-20260718.tar.gz` (**9,635,511
  bytes**) with SHA-256
  `69b79986903152102093632c60c3f6ba177dd3c9dd5d615e8f18d9c4e025c548`;
  its adjacent `.sha256` sidecar carries the same checksum.

## Post-RC3 Audio Review — 2026-07-18

- Added a **Modified** Audio status filter so a modder can isolate every staged
  standalone WAV among the 850 indexed cues, then inspect or Revert it without
  paging through untouched sounds. Streaming banks/ranges truthfully return no
  Modified rows because their replacement controls remain disabled.

## Post-RC3 Audio Collections — 2026-07-18

- Added a one-click **Soundtrack & music** view for all 136 exact music ranges
  and a bounded **Export matching audio** action for any 1–256 filtered rows.
  The action packages current standalone WAVs, complete raw banks, or verified
  WAV/raw ranges in one manifest-backed ZIP instead of requiring one export per
  table row.
- Collection export is all-or-nothing, refuses an existing or linked target,
  caps both row count and predicted payload bytes, and publishes the ZIP only
  after every payload and checksum succeeds. A failed decode leaves no partial
  result.
- The manifest distinguishes staged `user_replacement` WAVs from
  `retail_derived` audio. Collection exports remain local-only and structurally
  separate from shareable `.2k5mod` projects, project mutations, Undo, recovery,
  and Build.

## Workspace Recovery and Recent Files — 2026-07-18

- Added immediate background autosave after every connected visual, text,
  roster, Crib, audio, Stadium, Undo, and Revert workflow. Autosave delegates
  to the normal validated `.2k5mod` writer, so it contains user-authored
  replacements and logical metadata only—never source or original game bytes.
- Bound every recovery snapshot to the active source SHA-256 while holding the
  facade session lock. A source switch cannot relabel one game's edit set as
  another game's recovery, and recovery refuses a source-identity mismatch.
- Added a startup recovery choice plus **File → Recover Unsaved Edits**. A
  missing/moved source produces an exact path instruction and keeps the
  replacement-only recovery archive rather than guessing at another dump.
- Added **Save Project / Discard Edits / Cancel** gates before source switches,
  project replacement, and app close. Cancelling or a failed load retains both
  the current session and its recovery snapshot.
- Added private, atomic recent-file state for the last eight XISOs and eight
  named projects, surfaced through File-menu submenus. Recent paths never enter
  shareable projects.
- Added seven focused headless recovery/state/connectivity tests and expanded
  the release allowlist so the recovery module cannot be omitted from the next
  package. The selected 50-test recovery/facade/session/UI-model/packaging
  regression passed without launching a GUI or touching a display.

## Current-Tree Source-Free Preflight — 2026-07-18

- Replaced the stale streaming-audio research boundary with the complete
  registry instruction: “Recover external music/commentary cue identities and
  directories, loop points, gain, pan, priority, runtime routing, and
  reversible rebuild rules before any bank writer.” A focused test requires
  this exact instruction once and refuses the former wording.
- Added the recovery-state module to the clean-stage runtime closure and
  exercised recent-source metadata, source-SHA binding, recovery discovery,
  retail-payload exclusion, and cleanup using synthetic files only.
- Extended the same closure receipt across current all-range Audio coverage and
  the dedicated Gameplay and Menus inspectors. The passing receipt covers 35
  product modules, 22 tool modules, 850 standalone sounds, 17 streaming-bank
  descriptors, and all 53,571 indexed streaming ranges without a display.
- Fixed a preflight defect found by the post-runtime retail scan: module imports
  could leave undeclared `__pycache__` files in an otherwise clean stage. The
  checker now disables bytecode publication before any product/tool import.
- Rebuilt a fresh disposable allowlist-only stage and passed the release gate,
  runtime closure, 60-row source-free registry validation, desktop-entry
  validation, launcher syntax, and the post-runtime release gate. The stage had
  132 files, 13 directories, 101,659,703 bytes, no private inventory, and zero
  retail payloads; its totals stayed identical after runtime probing.
- Passed 317/317 nonvisual 2K5 tests (295 product plus 22 NFL/shared-provider
  integrity cases) and preserved the exact 43-validator plan. GUI/visual QA and
  RC3 packaging remain root-owned follow-up work; neither was performed here.

## Gameplay and Menus Inspector Pass — 2026-07-18

- Replaced the static **Sliders & Gameplay** findings page with a dedicated
  read-only product inspector: all 21 named slider rows, the stock range, all
  17 CPU **Fantasy Draft** position weights, eight observed save containers,
  the save/signature boundary, and five bounded franchise findings are now
  directly browsable.
- Kept the proof boundary in the controls themselves. Fixture slider values are
  labeled as research observations rather than the user's profile; Fantasy
  Draft is not called Franchise Draft; and no preset, executable patch, save
  writer, or out-of-range control is offered.
- Added a specialized **Menus & UI** inspector for the named NFL Main Menu:
  seven initialized rows/transitions, two owned layout relationships, rendering
  boundaries, initial selection, and all three remaining blockers are visible.
- Preserved the existing complete archive-resource browser as **All Raw
  Resources** inside the Menus workspace, and kept the registry capability
  cards/limitations available in both specialized inspectors.
- Added non-overwriting, sanitized JSON and spreadsheet-ready CSV export routes
  in the flagship facade for both inspectors. These reports contain named
  evidence and status metadata, never retail executables, saves, or archive
  bodies.
- Added two small, hash-pinned product snapshots so the inspectors remain
  runnable when private research reports are correctly absent from a release.
  The snapshots contain named metadata only, are covered by the exact
  reviewed-metadata allowlist, and are checked against the proved core outputs
  when the development evidence set is present.
- Added fail-closed model validation for the exact 21/17/seven-row contracts
  plus focused facade and offscreen flagship connectivity tests. All **51**
  selected inspector, facade, existing gameplay/menu core, Qt model, and
  release-manifest tests passed without launching or visually inspecting a GUI
  and without building a package.
- Corrected product documentation to match the current layout: Rosters &
  Players presently owns portrait/live-face textures, while the Current and
  Historical roster forms still share the **Text & Team Identity** workspace.

## Continuous Audio Coverage Pass — 2026-07-18

- Split the Audio tab into **Standalone sounds (850)**, **Streaming banks
  (17)**, and **Indexed streaming ranges (53,571)** so soundtrack, commentary,
  stadium/PA/coach, broadcast, and ambient audio are visible in the dedicated
  editor rather than only as opaque rows in the archive-resource fallback.
- Added exact private-source parsing for all 17 NFL 2K5 `AUSB` descriptors,
  their 16 external `.bin` owners, and all 53,571 indexed ranges.
  The duplicate `cwdloop` descriptors visibly report their shared owner.
- Added searchable family and status filters plus explicit container, ownership,
  export-format, and replacement-status labels. Standalone audio exports as a
  playable WAV; streaming banks retain exact raw `.bin` export, and every
  individual range now supports both its raw `.bin` and decoded PCM16 WAV.
- Completed the main-facade paging contract used by the Audio panel, including
  stable first/last result numbers for cue, bank, and range pages.
- Proved the bank payload codec as Xbox IMA ADPCM: all 53,571 ranges are whole
  descriptor-channel block groups, and a complete 2,183,326,092-byte scan found
  60,647,947 valid physical channel-block headers with zero invalid step indices.
- Added private Play/Stop and PCM16 WAV export for all indexed ranges. Complete
  banks remain raw-only because they contain many cues. Replacement remains
  disabled because cue names, loops/durations, mixer rules, and reversible
  repacking are still unresolved. Raw and decoded retail audio remain local and
  are structurally excluded from shareable `.2k5mod` projects.
- Made the original bounded **Menu Back** replacement route explicit in the
  selected-cue instructions while preserving all 152 additional exact-shape
  standalone writers and 697 alias-safe Export-only rows.
- Live private-cache indexing returned 850 standalone cues, 153 Editable rows,
  17 streaming descriptors, 16 external owners, and 53,571 ranges with the
  source opened read-only. Focused retail-free catalog and panel backend tests
  cover raw-bank and exact-range discovery/export, decoded range playback paths,
  cache-tamper/failed-decode cleanup, search/filter behavior, WAV replacement,
  revert, and overwrite refusal.
- Exercised the largest real range end to end: 8,954,064 encoded bytes became a
  31,836,716-byte stereo WAV in 1.018681 seconds. Python 3.12 uses an optional
  standard-library accelerated path; an explicit test proves the exact fallback
  used when that module is absent.

## v1.0 RC2 UX Refresh — 2026-07-18

- Tightened the desktop shell so more useful content fits without crowding:
  the sidebar, header, footer, browser columns, panels, cards, and preview
  minimums now use one compact spacing rhythm.
- Normalized typography and control sizing around Noto Sans, 34-pixel form
  controls, and 40-pixel primary build/launch actions, with stronger contrast
  and explicit disabled states.
- Made **Build Modded XISO** the clear primary action and renamed the quieter
  emulator action **Launch Latest Build** so the normal workflow reads in the
  order a modder actually uses it.
- Added clear buttons, accessible names, and practical tooltips to search and
  filter controls across the asset browsers. Stadium labels and other internal
  status copy now use modder-facing language.
- Re-ran the complete non-visual 2K5 product suite after the UX refresh: 312
  headless tests passed with no failures, errors, or skips. The release/runtime
  gates are recorded in the release status alongside the final archive hash.
- Published the non-overwriting RC2 runnable tree as
  `2K5-Mod-Studio-v1.0-RC2-20260718/` and portable archive as
  `2K5-Mod-Studio-v1.0-RC2-20260718.tar.gz`. The archive is
  **9,575,103 bytes** with SHA-256
  `6df15767ff766d7eb2b7b87634d79dee495102c74db323067eedc01f796193d7`.
- Independently extracted that archive and reran its retail-free gate,
  runtime-closure probe, desktop-entry validator, launcher syntax check, and
  post-runtime retail-free gate. All passed; the archive contains 126 regular
  allowlisted files, 14 directories, no symlinks or hardlinks, no private
  inventory, and zero retail payloads.

## v1.0 Release Candidate — 2026-07-18

### Product shell and universal coverage

- Completed all 11 sidebar tabs: Uniforms & Equipment, Rosters & Players, Team
  Identity, Field Art & Create-Team Art, Stadiums, Scorebug & Presentation,
  Menus & UI, The Crib, Audio, Sliders & Gameplay, and Playbooks & Plays.
- Connected all 30 NFL 2K5 capability cards to the 60-row cross-title registry.
  Card status renders as **Editable**, **Preview/Export-only**, or **Coming
  Soon** from shared registry state; concrete editor actions remain explicitly
  wired per specialized workflow.
- Kept the archive-resource browser as the fallback home for every resource in
  that index that does not yet have a specialized editor. Raw fallback rows are
  honestly Export-only rather than inheriting a capability status they cannot
  perform.
- Indexed 32,038 specialized visual assets with searchable category browsers,
  previews/thumbnails where supported, stable asset IDs, Export, Modified
  badges, Replace for writable classes, and per-asset Revert.
- Extended the shared session across visual, text, roster, audio, Crib, and
  Stadium edits, including Undo, Revert All, modified counts, and retail-free
  `.2k5mod` project save/load.

### Uniforms, rosters, text, and presentation

- Shipped the complete proved Uniforms & Equipment workflow for jerseys/torsos,
  sleeves, pants, live helmets, digits/nameplates, and separate Team Select
  cards.
- Shipped bounded portrait, live-face, create-team field-art,
  scorebug/presentation, team-identity, player-name, and jersey-number editing.
- Added a dedicated **Current Roster Players** browser/editor inside the shared
  **Text & Team Identity** workspace. Every current player number has a
  searchable row with current/original name and number, status filtering,
  Apply, Revert, and number Export. Primary proved rows are Editable;
  secondary-pool rows remain visibly Preview/Export-only. Rosters & Players
  currently remains the portrait/live-face texture workspace.
- Added Historical Teams coverage for all 75 historical ROST resources and
  3,975 historical players.
- Proved that the current and historical player views cover all 6,522
  jersey-number assets exactly once; no current number is left accessible only
  through an internal catalog.
- Added universal text search across 716 banks and 23,346 strings. Exactly
  20,074 fixed-allocation strings are Editable; the other 3,272 remain
  read-only with a reason.
- Made all four display fields for each ESPN 25th Anniversary moment editable:
  title, historical description, challenge objective, and date. Team selectors,
  scenario state, and unlock conditions remain outside the text writer.

### Stadium Studio and The Crib

- Added Stadium Studio for all 477 indexed scenes, with private lazy glTF/PNG
  derivation, resumable generation, orbit/pan/zoom, surface highlighting, and
  material/texture ownership selection.
- Connected Export/Replace/Revert/project/build for all 23,838 indexed
  fixed-allocation P8 texture occurrences. Multiple edits to one SCNE compose in
  one rebuild instead of overwriting one another.
- Preserved existing Stadium geometry, UVs, materials, collision, archive
  extents, and fixed SCNE allocation. Images that cannot fit the original
  compressed slot fail closed with a modder-facing message.
- Added The Crib browser for all 498 inventoried assets. All 128 Team Photos and
  the exact `room:22 / bar_monitor` screen are Editable, for 129 Editable rows;
  the other 369 are Preview/Export-only.

### Audio, gameplay status, and playbooks

- Added browse/preview/export for all 850 standalone AUDO resources.
- Enabled fixed-contract WAV replacement for 153 resources: the existing
  menu-back cue plus 152 uniquely owned standalone slots. The other 697 remain
  Export-only because duplicate-name/content aliases make runtime cue ownership
  ambiguous.
- Added exact per-row PCM16 validation for channel count, sample rate, frame
  count, and WAV chunk layout. An invalid WAV leaves the project unchanged.
- Corrected the known 17-position Draft table's product label to **Fantasy
  Draft**, not Franchise rookie draft. Private Catching and Fantasy Draft patch
  transports remain experiments and do not appear as finished presets without
  a causal runtime A/B.
- Added the dedicated read-only Gameplay inspector and named Main Menu
  transition inspector described above, including sanitized JSON/CSV export and
  retained capability/limitation views. Neither inspector claims writeback.
- Added the mandated Playbooks & Plays fallback as a structured viewer for 37
  books, 1,533 formations, 9,251 plays, 32,502 assignment chains, 91,833 nodes,
  and 101,761 player-slot references. Selected raw PLAY resources can be
  exported; route drawing/import stays Coming Soon with its findings note.

### Build, rollback, and release safety

- The source XISO is always opened read-only and cannot be selected as a build
  destination.
- Every staged replacement retains a private original for per-asset Revert;
  Undo and Revert All operate across the full project.
- Builds use a temporary output and exclusive final creation. A failed build
  cannot leave a partial/corrupted requested output.
- Shareable `.2k5mod` projects carry only user-authored replacements and logical
  metadata. They do not contain source resource payloads, private originals, or
  compiled XISO spans.
- The clean release-candidate package stage passed with **126 allowlisted
  files**, **101,447,213 bytes**, and **zero retail game bytes/private source
  inventory**.

### v1.0 composed smoke

- One product-flow project staged 19 Tier 1 edits and built them into a new
  XISO. The output changed 1,027,710 bytes and has SHA-256
  `70cd2bc0acc57d358d800cd6c0952c1c89c1c09ee9039d9513e435c58dffa0a6`.
- The source remained read-only and retained SHA-256
  `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`
  before and after the build.
- Headless visual QA inspected xemu only on private Xvfb display `:99`. It saw the
  ESPN splash, stable attract sequence, and a clean NFL 2K5 title /
  **Press START** screen with no visible corruption.
- This was a boot-level spot check. The release does not claim that every edited
  asset was individually visited or judged in gameplay. A later isolated
  software-rendered harness retry logged a PFIFO assertion during or after the
  close attempt, so no clean long-duration gameplay claim is attached to it.

### Known limits in v1.0

- The 3,272 non-writable text entries stay visible and read-only because they
  have zero text capacity, selector semantics, or an unproved write contract.
- Secondary roster pools are browsable/exportable. Position codes/labels and
  selected ownership metadata are already decoded in research but are not yet
  surfaced in the product form; ratings, membership, depth charts, and unsafe
  secondary-pool writeback remain Coming Soon.
- Stadium texture editing does not imply arbitrary model import. General
  Stadium/Crib geometry serialization, transforms, collision, and relocation
  remain outside v1.0.
- Only the proved Crib `bar_monitor` electronics surface is writable; the other
  24 electronics-like rows remain export-only pending one-at-a-time ownership
  and fixed-span proof.
- The 697 alias-ambiguous AUDO rows are not routed through the unique-slot
  writer. Complete non-AUDO banks remain raw-only multi-cue containers; their
  53,571 individual ranges are playable/WAV-exportable, but are not writable.
- Catch-strength presets require matched drop-rate sampling. The known Draft
  weights require a Fantasy Draft runtime A/B and do not address the separate
  Franchise rookie-draft scorer.
- Route authoring remains blocked by undecoded coordinates, opcodes, player
  roles, custom-save ownership, and inverse compilation. The read-only PLAY
  inspector ships instead.
- ESPN 25th moment text is editable, while scenario fields and unlock logic
  remain findings-backed Coming Soon.
- xemu is the supported target. Original Xbox hardware is untested.

## Phase 1 Alpha — 2026-07-17

- Shipped the polished Linux desktop shell, source-XISO load/index flow,
  in-app Getting Started page, and searchable Uniforms & Equipment browser.
- Added PNG previews, drag-and-drop replacement, per-asset Revert, Undo, Revert
  All, and modified badges.
- Added end-to-end build of a separate modded XISO and xemu launch detection.
- Added shareable retail-free project files and private original storage.
- Added universal raw inventory browsing so every indexed resource had a
  visible home before specialized v1.0 editors were completed.
- Confirmed the Detroit torso smoke build reached the normal NFL 2K5 title
  screen in xemu.

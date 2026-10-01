# DESIGN: Giants concept library and engine boundary

PROVED OFFLINE: [catalog.json](catalog.json) lists all 148 authored play indices, formations, personnel, menu slots, primary reads and opcode inventories. [The sheet](diagrams/index.html) and [PDF](diagrams/GIANTS_PLAY_SHEET.pdf) render every play. Counts below come from that catalog, not observed CPU call rates. All football outcomes remain DESIGN until main supplies gameplay evidence.

## PROVED OFFLINE: evidence and common grammar

PROVED OFFLINE: The existing [play rules audit](../ASTRA_PLAY_RULES_REPORT.md), [evidence manifest](../docs/mod_editor/play_rules.evidence.json), [codec](../mod_editor/core/nfl2k5_play_codec.py), [library](../mod_editor/core/nfl2k5_play_library.py) and [screen audit](../ASTRA_SCREEN_PASS_REPORT.md) establish the assignment grammar used here. Every authored eleven-player script passes the ported retail validator, donor/class checks, carrier pairing and formation legality checks. The receipts prove serialization and menu behavior, not route separation, defender engagement or successful catches.

PROVED OFFLINE: All plays start with `0x01`; center uses `0x02` to snap to QB slot 0; QB uses `0x03` to take the snap. Pass protection uses `0x11` type 1. Route segments use `0x12`: 0 straight, 2 post, 3 60-degree inside break, 4 lateral inside, 5 lateral outside, 6 corner, 7 comeback outside. Inside/outside resolves from the receiver's original alignment, including mirrored formations. Type 7 has a fixed small return, not a new coverage-dependent stick choice. Sources: codec and library above.

PROVED OFFLINE: Ordinary pass QB scripts combine `0x04` drop and `0x06` pass/read priorities. Four read ordinals refer to eligible assignment slots 6..10, not roster IDs. TE1 is slot 6 in the preserved Kings/Ace/Pro personnel groups. No `0x1A` branch or option intent appears in this recipe. Source: [generator](build_giants.py) and [tests](../tests/mod_editor/test_nfl2k5_complete_offense.py).

## DESIGN: concept definitions

PROVED OFFLINE: The count and primitive columns describe serialized assignments. DESIGN: the concept column and football interpretation describe intended behavior that main must observe.

| DESIGN concept | PROVED OFFLINE count | PROVED OFFLINE primitives | DESIGN intent / lab question |
| --- | ---: | --- | --- |
| Inside Zone | 12 | QB `0x13` transfer, HB `0x16` take + `0x15` path; five OL `0x11` type 8/group 2, zero lateral, one yard forward | Interior zone track; observe actual targets, cutback and exchange |
| Outside Zone | 12 | Same transfer/path grammar; five OL type 8/group 2 with one-yard lateral step and corresponding turn | Stretch track with native zone assignment family; observe reach blocks against even/odd fronts |
| Counter | 9 | Type 0 drive legs; backside guard type 2 pull; QB handoff kind 5 | Misdirection with one puller; verify guard clears center and reaches point of attack |
| Downhill | 8 | Type 0 drive legs, fixed HB interior path | Conservative downhill complement; does not claim duo combo blocking |
| End Around | 7 | QB `0x13` kind 2 to WR; WR `0x16` + cross-formation `0x15`; HB type 4 lead; OL native zone family | Direct post-snap WR transfer; verify exchange and direction on both alignments |
| Mesh | 10 | Two `0x12` straight + inside routes at 3/4 yards from opposite sides, vertical/corner complements | TE/WR shallow crossing with clearance; fixed paths do not implement man/zone settle rules |
| Stick | 9 | TE straight six yards + type 7 comeback, vertical clear-outs and flat support | Fixed stick spacing and quick TE target |
| Levels | 7 | Short/intermediate/deeper inside breaks at distinct depths | Layer targets against zone; check spacing from each alignment |
| Y Cross | 6 | TE straight ten yards + type 3 inside break; post/comeback support | Feature TE across the field above the shallow area |
| Dagger | 5 | TE vertical, WR deep type 4 dig, shallow complement | TE clears for an intermediate dig; TE remains first read |
| Flood | 8 | Same-side deep vertical, TE intermediate out/cross, HB flat | Three depths toward one side; check flat and intermediate spacing |
| Drive | 6 | Same-side shallow and dig; HB pass protection | Fixed shallow/dig combination; one variant features WR instead of TE first |
| PA Boot | 8 | `0x14` fake, HB `0x17` fake-take, lateral `0x04` QB movement + `0x06`; vertical/intermediate/flat routes | Under-center play action into flood; observe fake timing, rollout and protection |
| RB Slip | 6 | Native screen QB pass mode 5; HB type 9 route; three OL finite type-1 holds -> `0x18` release -> type 3 block; two OL protect | Coordinated HB slip screen; measure release and catch timing, not only the art |
| TE Seam | 17 | TE type 0 vertical 24/26/28 yards; dig/corner and secondary TE drag where applicable | TE1 vertical priority; confirm Likely is the actual roster occupant |
| TE Drag | 18 | TE straight three yards + type 4 inside 18 yards; vertical/dig complements | TE1 shallow crossing priority; observe traffic and receiver eligibility |

PROVED OFFLINE: Zone OL legs match the audited retail Inside/Outside Zone family, type 8/group 2. The live blocker resolver chooses and coordinates targets. PLAY does not expose a proved new double-team-to-linebacker policy. Therefore correct serialized zone-family assignments do not prove NFL-quality reach/combo execution. Sources: play rules audit, consumers `0x2400B0`, `0x23F450`, `0x2FAFF0`.

PROVED OFFLINE: Slip-screen holds are 0.5 seconds with a seven-yard QB drop and no added pass delay. The center and playside guard/tackle release; two linemen stay. Receiver type 9 is the native screen idiom despite the older codec label "Pass block". Its endpoint depends on the movement solver; the drawn block mark is not a catch location. Source: screen audit and `screen_receiver_chain`, `screen_blocker_chain`, `screen_qb_chain` in the library.

## DESIGN: formation and personnel distribution

PROVED OFFLINE: Thirteen families each have left/right variants, for 26 formations: Gun Trips, Gun Bunch, Gun Empty, Singleback Ace, Ace Wing, Pistol Ace, Gun Doubles, Gun Y Trips, Gun Wing, Ace Bunch, Pistol Wing, UC Tight and Pistol Strong. Gun Empty flexes the HB within 11 personnel. Ace/Wing/Y Trips variants use 12; Pistol Strong uses 21. The book has 90 plays in 12, 48 in 11 and 10 in 21. Gun QB depth is five yards, pistol four and under center two; the writer sets the native snap/shotgun flags from depth. Seven players are on the line with eligible ends; no TE is covered by a wider on-line receiver. Source: generator and formation legality checks.

DESIGN: This is a 12-personnel-heavy menu allocation guided by 2026 camp reporting and the requested TE emphasis, not a claim that New York ran 60.8% 12 or that the CPU will select that rate. Menu choices do not configure a new coach AI policy. Scheme sources and denominators are in [SCHEMES.md](research/SCHEMES.md).

## DESIGN: held out of this book

| Requested feature | PROVED OFFLINE boundary | DESIGN disposition |
| --- | --- | --- |
| Duo | No dedicated authorable double-team/combo policy proved | Hold true duo; Downhill is explicitly a simpler drive-block alternative |
| Jet sweep | `0x1A` is a conditional decision/link; it does not establish a new automatic pre-snap motion phase | Hold true timed jet sweep; use direct post-snap end around |
| Under-center motion | No automatic motion timing policy proved by these recipes | Keep legal stationary starts; main may separately test retail user-controlled motion |
| RB middle screen | Type 9 distance is not a proved direct lateral endpoint selector; zero does not establish a middle catch | Hold middle screen until endpoint and release behavior are witnessed; ship native slip grammar only |
| RPO / read option | Requires read/mesh decisions beyond this fixed-call library | Excluded by request; no branches or option runtime hooks |

PROVED OFFLINE: All defense, defensive goal-line, FG, punt, kickoff, Hail Mary and clock-special records are retained semantically. Pool compaction relocates pointers, so the complete resource is not byte-identical in those regions; retained names, flags, descriptors, node bytes, menus and formation payloads are checked for equality. No executable-code patch is needed for this pack. The compiler preserves all stock personnel payloads; separately selected Build features remain responsible for their own changes.

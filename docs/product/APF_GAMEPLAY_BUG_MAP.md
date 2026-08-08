# APF 2K8 gameplay bug map (community §6.2)

Status: living research map. Offline-proved writers ship only when a surface is
byte-mapped with an independent verifier. Emulator-only XEX patches stay
`unsafe/deferred` unless explicitly labeled.

Sources: Discord (Urianus Magnus Ursulinus [PLOT], 2026-08-07), GitHub issue #2
(stock playbooks), prior RE under `docs/product/PLAY_*` and roster/save docs.

| ID | Severity | Symptom | Likely surface | Status | Unblock path |
| --- | --- | --- | --- | --- | --- |
| G1 | Huge | ILB→OLB in Dime (star ILBs benched) | Defensive playbook formation package / sub rules | **annotated in editor** (⚠ Dime); offline package writer **not** proved | Diff Dime vs Nickel assignment membership on MASTER PLAY + save package bits; spike ROST/PLAY package-rule writer on fixture o0308-class |
| G2 | Huge | TE→WR in Ace on long downs (practice OK, game broken) | Offensive Ace package membership | **annotated** (⚠ Ace); offline fix **not** proved | Same as G1 for Ace offensive packages; capture practice vs game package consumer |
| G3 | Huge | DL ignores pre-play pinch/spread/swap; slants instead | Play assignment / DL stunt bits / director | research | Map assignment descriptor bits + DRCT; FX/FY/FW/FT stack does not own this |
| G4 | Huge | Season mode always daytime | Schedule / time-of-day tables | research | Locate season generator table in 0A/ROST/save |
| G5 | Huge | Season weather only clear/rain | Weather enum / season generator | research | Census weather enums vs `divot_Grass*` names |
| G6 | Bug | LC Greenwood & Jack Lambert VO as “Number 68…” | PBP ID / name table for legends | research | Save Players PBP field + disc name table cross-ref |
| G7 | Bug | CPU fake punt: P stands still | Special-teams play script / CPU playcall | research | Special-teams PLAY book census |
| G8 | Exploit | CPU 2-min drill only 4th; opposite 2nd half | Clock / AI director | research | DRCT + XEX AI tables; likely XEX |
| G9 | Bug | Offensive false starts almost never | Slider→code / RNG | research | Slider binding census |
| G10 | HUGE | Bronze/silver no 2nd-level charge when user-controlled | Ability gate on input path | research | Save Players ability bits (77 booleans already editable) vs XEX user vs AI path |
| G11 | Huge | All golds get 2nd-level charge without skills | Same gate inverted | research | Same as G10 |
| G12 | #2 | TEs rarely on field; never 3rd/4th long except Shotgun PB | Offensive PB construction | **annotated** via Ace/package flags | Stock PB browser + assignment copy already ship; true per-team books need Save Assignments + stock PB edit |
| G13 | #2 | Bear DE man on TE1 / RLB edge leftovers | Formation slot roles | **annotated** (⚠ Bear) | Slot-role RE (PLAY_PLAYER_ROLE_HYPOTHESIS) |
| G14 | #2 | Many unused PB clones | Save Assignments + stock PB editor | partial | Assignment routes copy/swap offline-proved; freehand still blocked |

## Shipped offline-related surfaces (not full G-fixes)

- **2K5 / APF assignment-route copy-swap** — exact stock descriptor reuse; no freehand.
- **2K5 formation/play clone** — offline-proved on o0308 39→40 / 254→255.
- **Playbooks panel broken-play annotations** — Ace / Dime / Bear name flags with tooltips pointing here (annotations only).
- **Save Players** — 149 fields including 77 ability bits (G10/G11 research surface).

## RE spike notes (playbook-related)

| Item | Fixture / address hint | Proof status |
| --- | --- | --- |
| Clone writer | o0308 @ disc offset class `106803200` | offline-proved (formation 39→40, play 254→255) |
| FX/FY/FW/FT overlays | `docs/product/PLAY_F*_SIM_OVERLAY_PROOF.md` | 4/4 orthogonal file proofs landed beta-26..28 |
| Inverse compiler | `PLAY_INVERSE_COMPILER_SPEC.md` | gates defined; freehand not Editable |
| Package/sub rules G1/G2 | not yet mapped to byte offsets | **next spike** |

## Honesty

No community fix pack is offered as a one-click writer until package rules are
offline-proved. Editor ⚠ tags are discovery aids only.

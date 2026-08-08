# APF 2K8 gameplay bug map (community §6.2)

Status: living research map. Offline-proved writers ship only when a surface is
byte-mapped with an independent verifier. Emulator-only XEX patches stay
`unsafe/deferred` unless explicitly labeled.

Sources: Discord (Urianus Magnus Ursulinus [PLOT], 2026-08-07), GitHub issue #2
(stock playbooks), prior RE under `docs/product/PLAY_*` and roster/save docs.

| ID | Severity | Symptom | Likely surface | Status | Unblock path |
| --- | --- | --- | --- | --- | --- |
| G1 | Huge | ILB→OLB in Dime (star ILBs benched) | Defensive play assignment slots 4–5 + formation aux membership | **RE spike shipped** (`playbook_package_rule_spike.spike_g1_dime_ilb`); offline package writer **not** proved | See §G1 spike below |
| G2 | Huge | TE→WR in Ace on long downs (practice OK, game broken) | Offensive skill-slot descriptors + Ace formation play links | **RE spike shipped** (`spike_g2_ace_te`); offline fix **not** proved | See §G2 spike below |
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
| Package/sub rules G1/G2 | **mapped** — see below + `mod_editor/core/playbook_package_rule_spike.py` | **re_spike** (not offline-writer-proved) |

### G1 precise spike — Dime ILB→OLB

| Pin | Value |
| --- | --- |
| Fixture asset_id | `nfl2k5.resource.o0308.c0000.k504c4159` |
| Fixture pack_offset | `106803200` |
| PLAY body `PLAY_BASE` | `0x33FC` |
| PLAY record size | `0x60` |
| Assignment field | `PLAY_BASE + play*0x60 + 8 + slot*8` (8 bytes: descriptor u32 + chain_start u32) |
| Focus slots | **4, 5, 6** (start of defense `0x1b` LB/DB band; `PLAY_PLAYER_ROLE_HYPOTHESIS`) |
| Formation aux | `FORMATION_AUX_BASE 0x245C`, size `0x50`, `FORMATION_PLAY_LINKS=36` |
| Shipped API | `spike_g1_dime_ilb(book)` → slot snapshots with body offsets |
| Offline writer gate | Dime vs Nickel census on o0308: if only assignment 8-byte fields differ in slots 4–5, prove copy-only patch + independent reparse/volume byte-diff. **No fix pack until that gate.** |

### G2 precise spike — Ace TE→WR

| Pin | Value |
| --- | --- |
| Same fixture | o0308 asset_id + pack_offset above |
| Focus slots | **3, 6, 7, 8, 9** (skill/WR variance band) |
| Formation links | packed play-index in formation link table (low 9 bits; `0x1FF` empty) |
| Descriptor word | play-level at `PLAY_BASE + play*0x60 + 0x04` |
| Shipped API | `spike_g2_ace_te(book)` |
| Offline writer gate | Ace vs non-Ace twin: if only skill-slot assignments or link packed values differ, offline-prove copy of non-broken rule. **No fix pack until that gate.** |

### APF parallel surface

MASTER PLAY assignment-route copy/swap is offline-proved (586×11). G1/G2 need
the same class of **package membership** proof on APF MASTER once Dime/Ace
descriptor deltas are isolated on the 2K5 o0308 fixture (shared PLAY family
lineage) or an APF-named play census.

## Honesty

No community fix pack is offered as a one-click writer until package rules are
offline-proved. Editor ⚠ tags are discovery aids. The RE spike is precise enough
to start the offline writer without re-discovering layout constants.


### G10/G11 precise spike — ability charge gates (continuation)

| Pin | Value |
| --- | --- |
| Surface | Save Players packed fields (`mod_editor/apf_studio/save_roster_players.py`) |
| **Star tier** | `field_id=tier`, byte_offset **18**, storage_shift **0**, width **3**; choices `0=None, 2=Gold, 4=Silver, 6=Bronze` |
| Ability booleans | category `ability` e.g. `get_low` @ byte 44 bit0; `head_slap` @ byte 42 bit7; full 77-bit set in `FIELDS` |
| Status | **re_spike** — offline writers for tier + ability bits already ship; **runtime gate** (user input vs AI path) not located in XEX |
| Offline proved | Save Players Apply/Revert/raw handoff for tier + ability bits |
| Unproved | Code that checks tier/ability on user-controlled 2nd-level charge (G10 bronze/silver block; G11 gold always-on) |
| Next | Controlled Roster.ROS: set bronze+skills vs gold-no-skills; capture Xenia input-path failure; XEX cross-ref |
| Updated | 2026-08-07T21:48:59 |

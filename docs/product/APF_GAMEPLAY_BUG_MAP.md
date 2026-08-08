# APF 2K8 gameplay bug map (community §6.2)

Status: living research map. Offline-proved writers ship only when a surface is
byte-mapped with an independent verifier. Emulator-only XEX patches stay
`unsafe/deferred` unless explicitly labeled.

Sources: Discord (Urianus Magnus Ursulinus [PLOT], 2026-08-07), GitHub issue #2
(stock playbooks), prior RE under `docs/product/PLAY_*` and roster/save docs.

| ID | Severity | Symptom | Likely surface | Status | Unblock path |
| --- | --- | --- | --- | --- | --- |
| G1 | Huge | ILB→OLB in Dime (star ILBs benched) | Formation **package map** `+0x0D` (11-byte role perm); not assignment 8-byte | **package-map offline writer proved** (bytes); runtime G1 fix **unproved** | See §G1 census below |
| G2 | Huge | TE→WR in Ace on long downs (practice OK, game broken) | Play links / skill-slot descriptors / save — **not** package map (Ace=all offense) | **RE spike** + Ace map identity proved; offline fix **not** proved | See §G2 spike below |
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
- **2K5 formation package-map writer** — `build_formation_package_map_patch` /
  `verify_formation_package_map_patch` (11 bytes @ formation `+0x0D`);
  offline-writer-proved for bytes; **not** a runtime G1 fix pack.

## RE spike notes (playbook-related)

| Item | Fixture / address hint | Proof status |
| --- | --- | --- |
| Clone writer | o0308 @ disc offset class `106803200` | offline-proved (formation 39→40, play 254→255) |
| FX/FY/FW/FT overlays | `docs/product/PLAY_F*_SIM_OVERLAY_PROOF.md` | 4/4 orthogonal file proofs landed beta-26..28 |
| Inverse compiler | `PLAY_INVERSE_COMPILER_SPEC.md` | gates defined; freehand not Editable |
| Package map G1 | formation `+0x0D` 11-byte perm; see census | **offline_writer_proved** (bytes); runtime G1 **unproved** |
| Package/sub rules G2 | Ace shares offense package map | **re_spike** (map path closed; links/assignments next) |

### G1 precise spike — Dime ILB→OLB (updated 2026-08-07 census)

| Pin | Value |
| --- | --- |
| Fixture asset_id | `nfl2k5.resource.o0308.c0000.k504c4159` |
| Fixture pack_offset | `106803200` |
| PLAY body `PLAY_BASE` | `0x33FC` |
| PLAY record size | `0x60` |
| **Package map** | `FORMATION_BASE + fi*0xB4 + 0x0D` (11 bytes, permutation of 0..10) |
| o0308 Nickel map | `[4, 5, 0, 2, 3, 1, 7, 8, 9, 6, 10]` (form index 23) |
| o0308 Dime map | `[5, 0, 2, 3, 1, 7, 8, 9, 4, 6, 10]` (form index 24) |
| Role-4 delta | Nickel slot-index **0** → Dime slot-index **8** |
| Assignment-only gate | **FAILED** — 18 shared play indices are the same records (byte-identical); 8 only-Dime / 8 only-Nickel plays have different names; link table differs 16/26 |
| Formation aux | `FORMATION_AUX_BASE 0x245C`, size `0x50` = play-link table (not separate membership) |
| Shipped API | `census_g1_dime_vs_nickel`, `read_formation_package_map`, `build_formation_package_map_patch`, `verify_formation_package_map_patch`, `spike_g1_dime_ilb` |
| Offline writer | **proved** for the 11 map bytes (copy Nickel→Dime or any perm of 0..10); independent full-resource byte-diff |
| Runtime G1 fix | **unproved** — do not ship as community one-click fix pack until emulator witness |

### G2 precise spike — Ace TE→WR

| Pin | Value |
| --- | --- |
| Same fixture | o0308 asset_id + pack_offset above |
| Focus slots | **3, 6, 7, 8, 9** (skill/WR variance band) |
| Package map | Ace = Split Pro = all offense: `[0, 8, 6, 9, 7, 10, 1, 4, 3, 5, 2]` — **not** the G2 delta |
| Formation links | packed play-index in formation link table (low 9 bits; `0x1FF` empty) |
| Descriptor word | play-level at `PLAY_BASE + play*0x60 + 0x04` |
| Shipped API | `spike_g2_ace_te(book)` |
| o0308 Ace vs Quads census (2026-08-07) | 5 shared play indices are **same records** (zero assignment XOR). Only-Ace plays: 58 Strong Toss, 139 PA X Stop-n-Go, 140 RO X Post-Corner, 141 50 TE/Y Outs. Package map identical to all offense. **G2 offline delta is formation play-link menu composition**, not per-play assignment bytes. |
| Offline writer | **Menu link-table copy shipped** (`build_formation_link_table_copy_patch` / `verify_formation_link_table_copy_patch`) — copies donor formation aux 0x50 play-link table onto target (e.g. Ace←Quads). Offline-writer-proved for **menu bytes only**. **Not** a runtime TE→WR package-rule fix pack. Save Assignments / director remain candidates. |

### APF parallel surface

MASTER PLAY assignment-route copy/swap is offline-proved (586×11). G1 package-map
is proved on 2K5 o0308; APF MASTER needs the same formation-level package map
hunt (or equivalent personnel table) before an APF G1 fix pack. G2 remains open
on both products.

## Honesty

Package-map bytes may be offline-patched; that is **not** a runtime G1/G2 fix
pack. Editor ⚠ tags are discovery aids. Runtime claims need emulator witnesses.


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

DESIGN: event-slot memo for main, 2026-09-28. No event-field artwork, stadium routing, schedule or executable patch is implemented by fb.

PROVED OFFLINE: the first integration issue is a source-level disagreement. E enables `season_2026`; `mod_build.py` calls `season.apply(xbe)` without a venue override. Its calendar default changes the first Super Bowl jump-table entry from s40 to s44. The SoFi model supplies its neutral LXI venue in s40. No later SoFi selector override was found in the checked integration source. Thus the E recipe's season code requests s44 in season zero, although the SoFi art is in s40. This is static evidence, not a claim to have inspected tonight's final candidate executable. See `evidence/event_proof.json`, the checked bytes at VA 0x133354, and `mod_editor/core/nfl2k5_season_length.py`.

PROVED OFFLINE: E also enables the 18-week season. The 22-row schedule has rows 0 through 17 for the regular season and 18 through 21 for the four postseason rounds. The patch skips the Pro Bowl record write and changes the Pro Bowl predicate to week 22, outside that grid. Therefore the ordinary patched franchise schedule supplies no Pro Bowl game. The Pro Bowl assets remain present. This follows from `WEEK_SITES`, including `pro_bowl_record_skip` at 0x2A82AE and `is_pro_bowl_week` at 0x133A61; those original bytes were checked against the retail executable.

PROVED OFFLINE: retail `FUN_001332b0` calls `0xC4EB0`, which reads the persistent season index at `0xE576B8`. Indices 0 through 4 use five jump-table entries; all larger indices use s45. `0x247B40` increments the index. Pregame `0x134040` calls that selector after `0x133A30` reports the Super Bowl and gives its stadium record to `0x77470`. The existing `tools/nfl_franchise_limit_feasibility.py` validator confirms all three code-body hashes. The getter, event predicates, selector and pregame instructions are in `evidence/event_disassembly.txt`.

| Evidence | Slot | Retail automatic use | E season-code use with 2026 base | Audited field identity |
| --- | --- | --- | --- | --- |
| PROVED OFFLINE | s40 | Season index 0, 2004 season championship | Bypassed by the default season-zero redirection to s44 | SoFi module supplies SUPER BOWL LXI |
| PROVED OFFLINE | s42 | Index 1, 2005 season championship | Index 1, 2027 season | SUPER BOWL XL |
| PROVED OFFLINE | s43 | Index 2, 2006 season championship | Index 2, 2028 season | SUPER BOWL XLI |
| PROVED OFFLINE | s41 | Index 3, 2007 season championship | Index 3, 2029 season | SUPER BOWL XLII |
| PROVED OFFLINE | s44 | Index 4, 2008 season championship | Indices 0 and 4, 2026 and 2030 seasons | SUPER BOWL XLIII |
| PROVED OFFLINE | s45 | Every index 5 and later | 2031 season and later | Retail future championship venue; included to explain the clamp |
| PROVED OFFLINE | s31 | Pro Bowl selector default: index 0, and calls outside phase 9 | No scheduled Pro Bowl with the 18-week patch | PRO BOWL HAWAII '05 |
| PROVED OFFLINE | s39 | Pro Bowl selector in phase 9 with any nonzero season index | No scheduled Pro Bowl with the 18-week patch | PRO BOWL MIAMI |

PROVED OFFLINE: the Pro Bowl selector is `0x133370`. It starts with the UTF-16 s31 pointer at `0xE79558`, switches to s39 at `0xE79560` only in phase 9 with a nonzero index, and searches the roster stadium records. It does not alternate the two venues by year. Retail event predicates are phase 9/week 20 for the Super Bowl and phase 9/week 21 for the Pro Bowl. The season patch moves the Super Bowl to week 21. Slot names such as "Future Aloha Stadium" are roster metadata; they do not override what sn found painted on the field.

PROVED OFFLINE: the year arithmetic is a season year, not necessarily the calendar year in which the championship is played. The retail base is 2004 and E's base is 2026. Offline u6 documentation and the existing 2026 calendar specify Super Bowl LXI at SoFi on February 14, 2027. The on-disk Levi's source `/media/noah/Storage/.b76-research/st/levis/refs/wiki_Levis_Stadium.txt` records Super Bowl LX at Levi's Stadium on February 8, 2026; `docs/levis_model/README.md` also records that event. Consequently LX/2026 at Levi's is a valid retrospective identity, while LXI/2027 belongs to the end of a 2026 franchise season. No future host assignments beyond the supplied LXI evidence are asserted here.

PROVED OFFLINE: E's `all_stadiums` option expands the Create a Team stadium-ID list from 67 to 82. The original list includes s31. The added list includes s39 and every Super Bowl slot s40 through s45. `mod_editor/core/nfl2k5_roster_storage.py` explicitly describes a Create a Team picker and the team stadium pointer at +0x114. This is not proof that Quick Game has a separate selector listing each event stadium.

INFERRED: assigning an expanded stadium to a created team offers a plausible Quick Game route to that asset through the team's stadium pointer. The added previews, menu wording, unlocking rules and actual game load have not been witnessed. Ordinary Quick Game choices and any separate single-season mode should be checked by main before claiming an automatic event-year rotation there. The executable evidence above establishes the persistent franchise/postseason route; it does not establish that every menu mode drives the same state. These uncertainties do not justify painting a fixed 2026 identity on every future slot.

DESIGN: main should first align the season-zero selector with the existing s40 SoFi model, or choose to move that model. If s40 remains the SoFi event venue, use plain `SUPER BOWL LXI / 2027` there. This memo recommends no official marks, trophy art, league shields or imitations of the official numeral lockups.

| Evidence | Proposed plain-type identity | Decision needed |
| --- | --- | --- |
| DESIGN | s31 and s39: `PRO BOWL / ALL-STARS` | Remove dated host/year claims; these assets are not scheduled by E's 18-week franchise. A fixed `2026` line is appropriate only for an explicitly retrospective Quick Game choice. |
| DESIGN | s40: `SUPER BOWL LXI / 2027` | Resolve the s44 routing conflict and retain SoFi's neutral event model. |
| DESIGN | s42, s43, s41, s44: `SUPER BOWL / CHAMPIONSHIP` | Durable text avoids claiming those retail buildings host future actual games. |
| DESIGN | s45: `SUPER BOWL / CHAMPIONSHIP` | This one asset serves every index 5 and later; one fixed year cannot be correct for all of them. |
| DESIGN | Optional retrospective venue: `SUPER BOWL LX / 2026 / LEVI'S STADIUM` | Requires an explicit Quick Game slot/model assignment at Levi's, rather than relabeling a future franchise slot in an unrelated building. |

INFERRED: if main instead wants a strictly chronological numeral sequence after correcting season zero, the arithmetic would be index 1 LXII/2028, index 2 LXIII/2029, index 3 LXIV/2030, index 4 LXV/2031. That is a proposed progression from the documented LXI/2027 base, not evidence of future host cities or runtime date-driven texture switching. s45 still requires generic text or a later dynamic design.

PROVED OFFLINE: fb's added event-slot manifests contain sponsor panels only. The small SUPER BOWL LXI corporate cloth follows u4's already-approved sponsor-sheet policy (section 4c); it does not replace the event field logos listed above. Every automatic routing change and proposed identity in this memo remains DESIGN for main.

DESIGN: if main wants a literal 2026 exhibition identity rather than the durable franchise treatment above, the complete plain-type proposal is `PRO BOWL / 2026 ALL-STARS` for both s31 and s39, and `SUPER BOWL / 2026 SEASON CHAMPIONSHIP` for s42, s43, s41 and s44. No city, official mark, trophy silhouette or numeral lockup is proposed. These labels should be selected only with an explicit exhibition-only routing decision: the four Super Bowl slots currently serve later franchise seasons, and s44 also receives E's season-zero game. Main decides between this literal 2026 set and the recommended yearless text; fb2 implements neither.

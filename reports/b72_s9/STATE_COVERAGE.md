# Broadcast state and runtime research

The supplied full-game grammar is evidence. This job compiles a capability inventory, not new runtime event rules. The latest 17:15 instruction limits this job to fidelity and preservation of witnessed event behavior. No new timing rule was installed.

| Rule | Status | Evidence or blocker |
|---|---|---|
| Possession plate color | Existing | Possession and team slots already exposed; own official palette retained. |
| After snap: down alone, median 7 s | Not compiled | No new snap/spot state machine in this fidelity-only change; current native text retained. |
| Dead ball: ESPN plate, median 9 s | Not compiled | No validated administrative-dead-ball classifier; native event ownership preserved. |
| Flag yellow plate | Existing | Native FLAG record drives the plate; no new timer. |
| Flag yellow penalized end and attached foul strip | Not compiled | Penalized-team identity and full foul-string sprite binding unproved. |
| Play-clock red at <=5 | Not compiled | Numeric source exists, but a threshold tint rule is absent; normal white-pill artwork only. |
| Touchdown compact bug, mirrored by scorer, 6-8 s | Not compiled | Scores exist; no validated scoring-event edge/hold/hand-off or alternate scene; existing score slabs retained. |
| TIMEOUT strip 2-5 s before dark dash | Not compiled | Counts exist; delayed display requires a new timer and ownership decision; current native counts retained. |
| NN-YARD ATTEMPT | Not compiled | No proved field-goal-attempt distance accessor in the sprite owner; ball position alone is insufficient. |
| TONIGHT player strip, about 7 s | Not compiled | No proved per-player current-game stat/name accessor with lifetime and mode guards. |
| Team/drive stat strip after first downs | Not compiled | No proved drive plays/yards/time aggregation or current-drive identity/reset behavior. |
| Official/person insert | Not compiled | No equivalent game video/person graphic asset or trigger. |
| Broadcast shot/replay suppression | Not compiled | Native scorebug visibility retained; editorial shot state is not game state. |
| NFL/MNF corner selection | Existing | Existing tested calendar/mode selection retained; only raster masks changed. |
| Records | Omitted | No confirmed live wing records; no new option or Play Now record path. |

| Full-game state | Labelled seconds | Runtime coverage |
|---|---:|---|
| commercial_or_studio | 1539 | Outside game scorebug runtime; no broadcast director input. |
| end_of_quarter | 32 | Existing quarter/clock fields; no broadcast transition timer. |
| extra_point | 138 | Existing native event handling; no broadcast ESPN-on-plate replacement. |
| field_goal | 25 | Native kick/event information exists; no proved attempt-distance binding for a new tab. |
| first_and_ten | 973 | Existing native down and distance; no added first-down pop-up. |
| flag | 421 | Existing FLAG record and yellow plate; no penalized-wing or foul-strip binding. |
| fourth_down | 495 | Existing native down and distance. |
| goal_to_go | 345 | Existing native Goal string; traced live word. |
| halftime | 28 | Native game presentation retained; no broadcast studio transition. |
| injury | 1 | No sprite injury identity/text or timing binding. |
| kickoff | 62 | Native event/field-position handling; no broadcast ESPN-on-plate replacement. |
| no_scorebug | 1603 | Native scene visibility retained; no broadcast shot-based suppression. |
| normal | 1629 | Existing down/distance and clocks; preserved native visibility. |
| other | 350 | No reliable semantic trigger; no inferred action. |
| replay_or_review | 420 | Native scene behavior retained; no editorial replay/review classifier. |
| short_yardage | 175 | Existing native distance and Inches formatting; rare glyphs reconstructed. |
| third_and_long | 295 | Existing native down and distance. |
| timeout | 83 | Existing timeout counts; no TIMEOUT strip or delayed dash change. |
| touchdown | 34 | Existing score event slabs; no mirrored compact bug or 6-8 s timing. |
| two_minute_warning | 9 | Clock available; no separate warning strip or broadcast trigger binding. |

| Supplied Raiders-Texans raw label | Seconds | Runtime coverage |
|---|---:|---|
| commercial_or_studio | 9 | Outside game scorebug runtime; no broadcast director input. |
| extra_point | 17 | Existing native event handling; no broadcast ESPN-on-plate replacement. |
| field_goal | 32 | Native kick/event information exists; no proved attempt-distance binding for a new tab. |
| first_and_ten | 232 | Existing native down and distance; no added first-down pop-up. |
| flag | 5 | Existing FLAG record and yellow plate; no penalized-wing or foul-strip binding. |
| fourth_down | 27 | Existing native down and distance. |
| goal_to_go | 21 | Existing native Goal string; traced live word. |
| kickoff | 1 | Native event/field-position handling; no broadcast ESPN-on-plate replacement. |
| no_scorebug | 195 | Native scene visibility retained; no broadcast shot-based suppression. |
| normal | 203 | Existing down/distance and clocks; preserved native visibility. |
| other | 7 | No reliable semantic trigger; no inferred action. |
| replay_or_review | 28 | Native scene behavior retained; no editorial replay/review classifier. |
| short_yardage | 41 | Existing native distance and Inches formatting; rare glyphs reconstructed. |
| third_and_long | 46 | Existing native down and distance. |
| timeout | 24 | Existing timeout counts; no TIMEOUT strip or delayed dash change. |
| touchdown | 15 | Existing score event slabs; no mirrored compact bug or 6-8 s timing. |

| Attached graphic class | Labelled seconds | Median segment seconds | Built |
|---|---:|---:|---|
| down_distance_callout | 16 | 4 | No; see rule reasons above |
| drive_banner | 61 | 8.0 | No; see rule reasons above |
| flag_banner | 29 | 3 | No; see rule reasons above |
| other | 818 | 8.0 | No; see rule reasons above |
| player_stat_popup | 539 | 6 | No; see rule reasons above |
| records | 12 | 2.0 | No; see rule reasons above |
| score_banner | 26 | 6 | No; see rule reasons above |
| team_stat_popup | 215 | 6.0 | No; see rule reasons above |

The coarse grammar has 12 seconds labelled records, while its reconciled records_seen is empty. Those coarse labels are not evidence of live team W-L corners. The supplied human addendum explicitly says none were observed. The broad player_stat_popup median is 6 s; the later TONIGHT-specific brief says about 7 s. Neither becomes a universal timer.

The original s3 miner was also run with live Jev answers on 200 stratified Raiders-Texans crops. miner/states.json retains its confidence gate, accepted states and 131 rejected observations. It accepts 69 observations across normal, first-and-ten, short-yardage, third-and-long and fourth-down. It does not establish absence of other states. The supplied full Raiders labels have 903 rows and supplement coverage; no new 903-call rerun is claimed.

## Records and stats memory evidence

`mod_editor/core/nfl2k5_franchise_save.py:146` maps a team record ring at +0x19C, seven u16 values maintained by 0x13ED70/0x13ED30, and merged games at +0x1DC. The named passing/rushing season accumulators are +0x1AA/+0x1AC, merged by 0x134DD0. These save/season fields do not prove a safe current-game pointer from a sprite update. COACH_FIELDS wins/losses/ties at +0x20/+0x22/+0x24 and season values at +0x26/+0x28/+0x2A are coach records, not a demonstrated both-team current standings accessor.

The live calendar grid 0xE57C40 has 8-byte schedule records; mode 0xE576A0, week 0xE576B4 and slot 0xE576BC support the existing MNF decision. They do not contain a demonstrated team W-L pair. The MyCareer mode pins 0x150620, and the supersim probe observes play count 0xE53804. A play count is not drive plays/yards/time; a pinned helper is not a proved statistics API. This review found no validated current-player passing line or rushing-yards/name accessor in the scorebug owner. That is an evidence boundary, not a claim the game lacks those statistics.

The sprite owner exposes eight text sources: both scores, both timeout counts, quarter, game clock, play clock, and native down/distance. Atlas tokenization can draw bounded known strings, but its current alphabet is incomplete for arbitrary names. A new stat tab would need proved per-game pointers and validity/lifetime guards, name glyph coverage, vertices/material capacity, event edges, timers and reset rules. RX uses 4086 of 4096 bytes and RW remains 128 bytes; this leaves only 10 RX bytes in the existing reservation. The appended GAMEDATA remains below its ceiling, but remaining file space does not solve the code/state ownership problem.

Records are skipped because live evidence does not call for them and both-team franchise/MyCareer reads are unproved. There is no record code path in Play Now or any other mode. Stat pop-ups and CURRENT DRIVE are skipped because their required data bindings and runtime costs are unproved; no fake numbers or arbitrary names are rendered.

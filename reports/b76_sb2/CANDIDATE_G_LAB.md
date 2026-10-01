# DESIGN: candidate G, PHI at CHI capture card

DESIGN: use the current 2026 Eagles as AWAY and Bears as HOME, an MNF broadcast slot, 128 MB, and the candidate G integrated build. Record the exact build commit, manifest, aspect, roster identities and source-disc digest. This job ran no emulator and built no disc.

DESIGN: capture the following in 16:9, then repeat a normal possession state, a long label, FLAG and an ESPN plate in 4:3. Keep full frames and unscaled bar crops. Prefer natural play. Any injected state must be labelled FORCED, with the write, old/new values and time recorded.

| Label | Capture | Expected result and comparison bin in the supplied NFL video |
|---|---|---|
| DESIGN | CHI on offense, 1st & 10 | Orange right wing and orange plate; bear remains fully inside its cell. Bin 41: Q1 13:01, 0-0, PC 38. |
| DESIGN | PHI on offense, 1st & 10 | Teal left wing and plate; eagle points left. Bin 113: Q1 8:39, 0-7, PC 40. |
| DESIGN | Incomplete/short play advancing from first to second down | Capture the first visible frame, +1 s and +8 s. `2nd Down` should give way to `2nd & N`. Bin 28 has the interim label. Repeat third and fourth down. |
| DESIGN | CHI 4th & 1, user remains on offense | Hold pre-snap and capture PC 6, 5, 2 and 0. White at 6, red with white digits at 5 and below. Bins 69/70 are the 6/5 boundary, with Q1 10:54/10:53 and 0-0. This closes the prior lab's missing red-clock witness. |
| DESIGN | PHI 3rd & 16 | Full `3rd & 16`, with no truncation or overwide label. Bin 144: Q1 6:57, 0-7, PC 17. |
| DESIGN | Delay of game or another visible penalty | Yellow FLAG alone on its plate; no down text beneath it; rim remains above the plate. Bin 245: Q2 14:55, 0-7, PC 25. |
| DESIGN | CHI 2nd & GOAL | Uppercase GOAL, orange plate. Bin 270: Q2 14:40, 0-7, PC 31. |
| DESIGN | PHI 2nd & GOAL | Uppercase GOAL, teal plate. Bin 510: Q2 :00 during the last play, 0-10, PC 30, PHI timeouts exhausted. The lab may use any non-expiring clock for the geometry comparison. |
| DESIGN | Kickoff, punt in flight, post-punt and PAT | Black ESPN plate, unchanged wordmark footprint, uninterrupted rim, no retail Ball on or hang-time text. Bins 188/194 show punt/post-punt states. |
| DESIGN | Clock crossing 1:00 to :59 and then :05 | No leading zero under a minute. Bin 230: Q1 :05, 0-7, 2nd & 12, PC 40. |
| DESIGN | Timeout called by each side while play calling appears | TIMEOUT tab on the calling side and a spent pip; timer must not expire while the bar is hidden. This footage does not establish new timeout timing. |
| DESIGN | Play-call entry and exit, then replay/menu | Bar stays readable during play calling; no retail top bar; correct hide and restore on replay/menu. Check the previous B1 behavior after the smaller labels. |
| DESIGN | Short yardage with Inches, then OT if available | INCHES stays in capitals and fully legible at the new size; OT is unchanged. These are regression captures, not claims that this highlight reel showed either state. |
| DESIGN | A touchdown followed by PAT | Document the game's existing presentation. Broadcast player cutouts, touchdown slab, name/stat tags and drive banners remain outside the implemented bar. Do not mark them passed because the ESPN plate works. |

DESIGN: the sheets seed PHI 2-0 and CHI 1-1 to match the footage. These are preview inputs, not hard-coded game records. Check the game's actual franchise records; a mode without records may legitimately hide the tabs.

PROVED OFFLINE: the expected owner words after setup are home wing `0xFFFB6930`, away wing `0xFF1FB0C4`, home plate/rim `0xFFAC3100`, away plate/rim `0xFF26636B`. Native texture names are home `sb05h0`, away `sb21h0`. The passing SB2 native test reads both actual material bindings and both descriptor tint words.

DESIGN: resolve the sprite owner's RW address from candidate G's owner receipt, rather than copying candidate F's allocation. Read its 128-byte state alongside frames: wing words +16/+20, plate words +24/+28, last down +96, interim float +100, packed timeouts +104, tab float +108, tab side +112, red flag +116. Read draw gate `0xA95524`, scene `0xA95528`, possession `0xE60280`, phase `0xE602B4`, quarter `0xE602C4`, game-clock object pointer `0xE6028C` and play-clock object pointer `0xE60294` (both seconds at object +16). Capture before and after each transition, at least twice per second for the 6-to-5 boundary.

INFERRED: the 24 px label and bounded colour fits should improve candidate G, but software projection cannot establish the console GPU's final colour, edge coverage or legibility. Accept only after checking the original, unscaled game captures, especially 4:3 labels and the bright CHI wing.

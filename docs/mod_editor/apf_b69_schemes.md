# Offensive schemes and CPU book controls, beta 69

Open **Playbooks → CPU Play Calling → Scheme**. Choose a team and one of eight
schemes, review the book-copy plan and the before/after settings, then stage.
A shared offensive book gets a named copy for that team. Preview recalculates
from the staged book. One Undo restores the whole scheme operation, including
its copy assignment. Save Project preserves the recipe; Build writes and
reparses the named book and the team's ROST tendency fields.

These are **ADVANCED, opt-in** interpretations from general football knowledge.
No internet research was used. Their numeric preferences are authored tuning,
not quotes, statistical findings or exact installations from a coach's book.
Every in-game outcome is **UNWITNESSED**.

| Scheme | Team run tendency | Preferred personnel, in order | Emphasis |
|---|---:|---|---|
| Air Coryell | 42% | 12, 21, 11 | Vertical passes and complementary runs |
| Erhardt-Perkins | 50% | 12, 21, 11, 22 | Multiple personnel and balanced calls |
| West Coast | 45% | 21, 12, 11 | Timing passes, backs and tight ends |
| West Coast Spread | 40% | 11, 10, 12 | Timing passes with wider personnel |
| Spread-to-Run | 58% | 11, 20, 10, 12 | Runs from spread personnel |
| Wide Zone | 57% | 12, 21, 11 | Run emphasis and tight ends |
| Power/Gap | 62% | 22, 23, 21, 12 | Heavy personnel and runs |
| Pro Spread | 48% | 11, 12, 10, 21 | Balanced three-receiver offense |

Personnel notation counts backs, then tight ends; 12 means one back and two
tight ends. The writer derives the available groups from this book's actual
MASTER categories. Missing preferred groups are listed in the review. A scheme
does not add formations, routes, blocking concepts, motion, abilities or plays.

The data lives in `mod_editor/core/apf2k8_offensive_schemes.py`. Each scheme
defines eleven run/pass row-weight deltas, eleven intended run percentages,
personnel preferences, category-rating deltas and three formation-rating deltas.
Category preference works through the mean of its formations' ratings, because
the book has no independent category-rating field. The first two preferred
groups receive -1, other listed groups 0, unlisted groups +1, added to the
scheme's short/medium/long deltas. Results clamp to 1..7; plays, audibles and
membership stay intact. Both lotteries consume these same three fields, so
category and formation preferences are coupled. Reapplying adds the deltas
again; Undo before trying a replacement if you want the same starting point.

**Run percentages by row are coaching intent.** The overall tendency byte is
the direct team control. The 22 row bytes feed the game's optional tendency
cache, whose cached category/formation is not consumed by the ordinary CPU
lottery traced in beta 67. These bytes are written, reparsed and preserved in
the project; they are not advertised as independent CPU situation overrides.
The preview uses the overall tendency with the beta-67 situation adjustment,
plus the actual formation ratings, membership and play X weights. It does not
substitute the coaching-intent percentages into the prediction.

**Export play call spreadsheet** exports the current staged offense, including
later manual edits. CSV distinguishes last applied scheme, intended run share,
stored team share, modeled adjusted share and candidate probabilities. It
includes all 23 requested buckets. Supplied pick counts are planning notes,
not a scripted series of game calls; unspecified counts stay blank.

| Bucket | Representative down/distance, yards to goal | Row at neutral jitter |
|---|---|---:|
| Openers | 1/10, 50 | 4 |
| 1st and 10 | 1/10, 50 | 4 |
| 2nd and 2-3 | 2/2.5, 50 | 0 |
| 2nd and 4-6 | 2/5, 50 | 3 |
| 2nd and 7-10 | 2/8.5, 50 | 4 |
| 2nd and 11+ | 2/15, 50 | 7 |
| 3rd and 2-3 | 3/2.5, 50 | 4 |
| 3rd and 4-6 | 3/5, 50 | 7 |
| 3rd and 7-10 | 3/8.5, 50 | 10 |
| 3rd and 11+ | 3/15, 50 | 10 |
| 4th down | 4/2, 50 | 4 |
| Short yardage | 3/1, 50 | 1 |
| Red zone 25-21 | 1/10, 23 | 4 |
| Red zone 20-16 | 1/10, 18 | 4 |
| Red zone 15-11 | 1/10, 13 | 4 |
| Red zone 10 and in | 1/10, 7 | 4 |
| Goal line | 1/1, 1 | 0 |
| 2pt | 4/2, 2 | 4 |
| Backed-up | 1/10, 97 | 4 |
| After negative play | 2/15, 50 | 7 |
| Sudden change | 1/10, 50 | 4 |
| 4-minute | 1/10, 50 | 4 |
| 2-minute | 1/10, 50 | 4 |

Fourth-down and try-phase decisions are separate. The 2pt entry is a scrimmage
proxy; the real try phase can request row 19 or ordinary offense with down 4.
First-and-10 at the seven is a planning representative, not goal-to-go.

Each CSV row includes its computed engine row **0..10**, neutral jitter range,
the representative inputs and the mapping caveat. There is no one-to-one mapping
of 23 coaching buckets to eleven engine rows. Openers/sudden change and the four
red-zone bands cannot be distinguished as separate ordinary situation rows.
Clock state and previous plays can influence other native paths, so those
features are not claimed absent from the entire game.

The sparse BASE audit found Weather, Coin Toss and Huddle text in the XEX, but
no proved scheme policy writer for tempo, snap count, weather-dependent ratios
or receive/defer preference. Text is not a control. None is invented or enabled
by these schemes. See `docs/research/apf_b69_control_audit.json` and `ASTRA_REPORT.md`.

**Never call (ordinary CPU lottery)** clears an ordinary record's category
membership without deleting plays or compacting records. Another formation
must cover each affected personnel category. Unchecking restores memberships
saved in the project; Undo also works. Special records 151–162 stay protected:
a native cached Hail Mary call bypasses this gate. Saved USER books and global
merges may supply another copy. This is not a block on explicit user calls.

For **5-2**, expand Experimental MASTER personnel and choose **Make 5-2 an
ordinary candidate (row 13)**. This changes shared MASTER category `5-2:Big`
for every book, including clones. Add 5-2 first if the book lacks it. Preview
against offensive row 3 at midfield; the ordinary request is defensive row 13.

For **TEs on third down**, start with a book carrying Straight/other TE groups,
inspect third-and-3/8/15 in the preview and adjust their ratings or personnel.
The pass-fetch experiment only affects its separate subtype-fetch path; it
does not replace successful ordinary CPU calls. In beta 69, use the Studio's
install control, then launch through the Studio: managed patches are copied
to the exact launch storage folder. Check the Xenia log's `Storage root:` and
`Patcher: Applying patch for:` lines. Matching module hashes are BASE
`5447E5428AA2D52A` and TU 1.1 `CEA825F7C2012F5A`. Full witness steps are in
`ASTRA_REPORT.md`.

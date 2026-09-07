# r63 camera v2: paired presets and a bounded pass pullback

2026-09-07. Branch `astra/r63-camera-v2`, base `477443e`.
**EXPERIMENTAL / UNWITNESSED.** Noah's observation concerns the earlier disc;
this revision has CPU, executable and projection evidence, not a gameplay witness.
No network, game emulator, GUI display, audio, disc build, archive-pack load,
or push was used. Only the supplied retail executable and bounded synthetic
fixtures were loaded. Protected files and other worktrees were not edited.

## Delivered behavior and decisions

- Far still starts fresh settings, saved Settings/Franchise loads, games and
  practice through the existing selection hooks. Options is a session choice.
  All six menu choices still work; MyCareer uses the existing byte marker and
  its assembly/template has not changed. No new checkbox, BuildPlan field,
  Build preset setting, camera index or allocation was introduced.
- Far's six non-pass scrimmage records, including pre-snap, are byte-identical
  to r63-camera-far. State 15 now uses Far pre-snap geometry and lens 28.
- Standard retains the **actual retail Far eye relative to the focus**, its
  lens 28, and matches new Far's optical pitch per scrimmage state. Its three
  authored special kick descriptors take retail Far's geometry, matching the
  unchanged corresponding Far descriptors. Shared return/presentation records
  stay intact. Every recipient and alias is listed below.
- Native live growth retains its 1.02 multiplier but stops at a much smaller
  height threshold, including the native one-update overshoot. Pass Zoom Out
  retains its option and gates, with smaller geometry overrides. Both rows use
  lens 28 throughout the scrimmage/pass states, removing the 28-to-24 pass lens
  widening. The backend-only `broadcast_wide` key remains available; this
  witness proposal and its numeric bounds concern public `far_look`.

## PROVED: the previous fixture omitted part of the native eye position

The retail USA XBE is 11,948,032 bytes, SHA-256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
Camera data and instruction pins are checked before mutation. The camera map,
prior Far report and receipt, relevant allocator/MyCareer/widescreen reports,
RC85 changelog, prior ASTRA report summaries and camera references, the
read-only Ghidra corpus and actual XBE instructions were reviewed.

For native descriptor type 2, `5F760` computes:

```
look_at = focus + descriptor.target
settled_eye = look_at + descriptor.offset
```

The field direction changes the z terms. The old fixture incorrectly used
`focus + descriptor.offset` as the eye. Consequently its pitch and pixel
numbers, including the earlier report's 24.3-degree pre-snap pitch, are
superseded. This task corrects the fixture without moving Far's pre-snap
record. Its actual settled pre-snap eye is `(0,700,-2050)`, target
`(0,0,-250)`, pitch **21.250506 degrees**. Retail Far's actual pre-snap eye is
`(0,575,-1100)`, because its target `(0,175,200)` is added to offset
`(0,400,-1300)`.

Simply copying retail offset words and changing the target would move the
physical eye and would not change pitch. Standard instead solves the offset
and target together: preserve the old `target + offset`, use target y=0,
and set `offset.z = -eye.y / tan(Far pitch)`, rounded to float32. The exact
stored words and field deltas appear in the JSON. This is why Standard's
new +30 offset words differ even though its physical eye matches retail Far.
Distance in the pass bound is the Euclidean **eye-to-focus distance**, measured
from the native settled eye. The receipt also reports eye-to-target distance
(the offset norm); these are distinct quantities when look-at moves.

## PROVED: selection and pass transition

The six existing selection edits and the 39 instruction bytes in the 64-byte
RX allocation are unchanged. Fresh initialization still stores ESI=1 at
`E3C68`; saved callers at `16D1D4`, `16E7B1`, `16E864` retain their wrapper;
`64991 -> A55A0 -> A55EB` uses the native setter and session selector.
The zero-human branch still reads the same session row. Tests cover all old
rows 0..7 and common mode words 0..9, all six Options choices, saved word
restoration, source preservation, and both MyCareer install orders.

At `9FFB6..9FFD6`, the release dispatch reads `E602BC`: kind 3 selects state
13, kind 6 selects state 14, and other tested kinds select state **15** through
`89260`. That setter writes `B616C0` at `892A0`. `A5620` detects state/row
changes and `A572D..A5741` indexes `(row*29 + state)*8` at `4F03F8`, then
calls `60090` to copy the complete 80-byte record and run its setup callback.
The bounded test executes the release selector and native setter through the
state store, then separately executes all 58 row/state lookups in every aspect.

State 16 (also preview state 1) uses Standard `A88A00`, setup `A4990`, frame
`A4A50`; Far uses `A88D20`, setup `A4BC0`, frame `A4C30`. State 15 uses
Standard `A88A50` / setup `A49D0`, Far `A88D70` / setup `A4BF0`; both have no
frame callback. Setup applies pivot/control and optional zoom. The frame
callbacks preserve native possession/presentation predicates, direction and
end-zone reset checks and recopy their own revised live descriptor on reset.

`E5FFF4` is QB Pivot, `E5FFF8` Runner Pivot, `E5FFFC` Pass Play Zoom Out.
The pass setup retains QB-pivot writes to camera `+2D0` (Standard 0.85,
Far 0.9); Standard retains its human/team gate, whereas Far's zoom gate is
unconditional apart from the option. Neither routine changes the lens.
The lens is descriptor `+20`, copied into camera `+410`; the native lens
setter `5E100 -> 66A90` uses `lens/(18*aspect_parameter)`. The settled fixture
uses aspect_parameter=1 and widescreen v3 activation. Lens 28 is **not 28
FOV degrees**: actual matrix-derived FOVs are in the table below.

Default lag block `4F0380` starts `(32,14,32,14)`; Runner Pivot can select
`4F0394`. Live pending transition state `B6176C` selects `4F03E4`
`(8,5,8,5)` while `B61738 < 0.4`, then restores `4F0380`. These blocks and
all lag/callback/type/flag/padding words in the descriptors remain unchanged.
Native `60090` initializes lens lag `+394` to 0.25; Standard's general setup
`A4950` overrides it to 5.0. Far keeps its native value. No pooled literal
is modified, and no runtime state is allocated in executable code.

## Exact instruction edits added by this revision

All edits own complete existing instructions. The JSON includes old/new hex
and VAs. No detour or additional RX byte is needed.

| Sites | Retail | New |
| --- | --- | --- |
| `A4A2D..A4A4A`, Standard pass zoom | Three stores: offset.y=1000, offset.z=-2500, target.z=500 | offset.y=650, offset.z=-1671.4285888671875, target.z=471.4285888671875 |
| `A4C0C..A4C29`, Far pass zoom | Same three stores | offset.y=750, offset.z=-1900, target.z=-250 |
| `A4B1A..A4B21`, Standard live cap | `fld [A88A34]; fadd st(0),st(0)` | `fld [4EDA58]; fnop`, reading existing pinned 500.0 |
| `A4D1F..A4D26`, Far live cap | `fld [A88D54]; fadd st(0),st(0)` | `fld [A88BC4]; fnop`, reading unchanged Far pre-snap offset.y=700 |

Growth still multiplies offset.y and offset.z by the unchanged
`[4F0D5C]=1.0199999809265137` while current offset.y is at or below the
threshold. The old limit was twice the live descriptor height. Since the
comparison happens before the multiply, the cap can overshoot once; tests
execute 96 real callbacks and include that overshoot, rather than assuming
an exact doubling. The final heights are Standard **507.930573** and Far
**703.580933**. Reset and blocking-predicate paths have separate native tests.

## Exact Standard field deltas

T is descriptor `+10` target xyz, O is `+30` offset xyz, L is `+20` lens.
All x fields remain zero. Values are the stored float32 values printed exactly;
deltas are relative to **retail Standard**, not the prior Far patch. Every
other descriptor byte is unchanged. State 1 aliases 16; 14 aliases 10.

| State / VA | New T(y,z); delta | New O(y,z); delta | L; delta |
| --- | --- | --- | --- |
| 8 / `0xa88780` | (555,-1432); (95,-420) | (120,-815); (-90,285) | 28; -8 |
| 9 / `0xa88870` | (0,378.5714111328125); (-175,178.5714111328125) | (575,-1478.5714111328125); (175,-178.5714111328125) | 28; -7 |
| 10 / `0xa88820` | (185,0); (0,0) | (245,-700); (0,0) | 28; -7 |
| 11 / `0xa887d0` | (0,0); (0,-100) | (500,-1325); (0,0) | 28; -8 |
| 13 / `0xa888c0` | (0,-307.69232177734375); (0,-307.69232177734375) | (200,-492.30767822265625); (0,307.69232177734375) | 28; -7 |
| 15 / `0xa88a50` | (0,492.857177734375); (-100,492.857177734375) | (600,-1542.857177734375); (100,-142.857177734375) | 28; -2 |
| 16 / `0xa88a00` | (0,10.76922607421875); (-100,160.76922607421875) | (370,-910.7692260742188); (100,-160.76922607421875) | 28; -7 |
| 17 / `0xa88910` | (0,61.5384521484375); (-80,131.5384521484375) | (480,-1181.5384521484375); (80,-131.5384521484375) | 28; -7 |
| 18 / `0xa88960` | (0,-307.69232177734375); (0,-307.69232177734375) | (200,-492.30767822265625); (0,307.69232177734375) | 28; -7 |
| 19 / `0xa889b0` | (0,61.5384521484375); (0,1061.5384521484375) | (480,-1181.5384521484375); (-320,-181.5384521484375) | 28; -7 |

State 12 uses shared `A884B0`, with zero deltas. Other shared presentation,
replay/cutscene and inactive states (0,2..7,20..28) have zero deltas. FG, punt
and kickoff authored candidates 8/10/11 now use the corresponding retail Far
record values; the exact scene names of numeric kick states remain witness
labels rather than a newly proved exhaustive front-end mapping. The former
“after the catch” label for state 13 is inherited shorthand, not exclusivity:
the native release dispatcher also selects it for kind 3. No shared replay or
cutscene descriptor reads the Standard/Far geometry by an alias in this table;
preview state 1 does. All eight table rows are byte-preserved and no other
row references the modified recipients.

## The four requested cameras, every table state

The brief says “three cameras” but enumerates four; all four are shown here.
These are descriptor fields, not absolute eye positions. Full 80-byte record
hashes, flags, callbacks, aliases and field deltas for both rows are in the
receipt's `descriptor_inventory`. Shared presentation states retain their
native types, including types 0/1; no settled type-2 projection is claimed for
those scene-controlled views.

| State | Retail Standard | Retail Far | New Standard | New Far |
| --- | --- | --- | --- | --- |
| 0 | T(0,0,0); O(200,2000,0); L100 | T(0,0,0); O(200,2000,0); L100 | T(0,0,0); O(200,2000,0); L100 | T(0,0,0); O(200,2000,0); L100 |
| 1 | T(0,100,-150); O(0,270,-750); L35 | T(0,100,-150); O(0,270,-750); L28 | T(0,0,10.76922607421875); O(0,370,-910.7692260742188); L28 | T(0,0,-350); O(0,650,-1600); L28 |
| 2 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 |
| 3 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 |
| 4 | T(0,0,0); O(250,75,0); L50 | T(0,0,0); O(250,75,0); L50 | T(0,0,0); O(250,75,0); L50 | T(0,0,0); O(250,75,0); L50 |
| 5 | T(23,45,117); O(-418,-120,-522); L35 | T(23,45,117); O(-418,-120,-522); L35 | T(23,45,117); O(-418,-120,-522); L35 | T(23,45,117); O(-418,-120,-522); L35 |
| 6 | T(23,45,117); O(-418,-120,-522); L35 | T(23,45,117); O(-418,-120,-522); L35 | T(23,45,117); O(-418,-120,-522); L35 | T(23,45,117); O(-418,-120,-522); L35 |
| 7 | T(0,0,0); O(-5000,1200,600); L70 | T(0,0,0); O(-5000,1200,600); L70 | T(0,0,0); O(-5000,1200,600); L70 | T(0,0,0); O(-5000,1200,600); L70 |
| 8 | T(0,460,-1012); O(0,210,-1100); L36 | T(0,555,-1432); O(0,120,-815); L28 | T(0,555,-1432); O(0,120,-815); L28 | T(0,555,-1432); O(0,120,-815); L28 |
| 9 | T(0,175,200); O(0,400,-1300); L35 | T(0,175,200); O(0,400,-1300); L28 | T(0,0,378.5714111328125); O(0,575,-1478.5714111328125); L28 | T(0,0,-250); O(0,700,-1800); L28 |
| 10 | T(0,185,0); O(0,245,-700); L35 | T(0,185,0); O(0,245,-700); L28 | T(0,185,0); O(0,245,-700); L28 | T(0,185,0); O(0,245,-700); L28 |
| 11 | T(0,0,100); O(0,500,-1325); L36 | T(0,0,0); O(0,500,-1325); L28 | T(0,0,0); O(0,500,-1325); L28 | T(0,0,0); O(0,500,-1325); L28 |
| 12 | T(0,0,1250); O(0,1750,-4500); L35 | T(0,0,1250); O(0,1750,-4500); L35 | T(0,0,1250); O(0,1750,-4500); L35 | T(0,0,1250); O(0,1750,-4500); L35 |
| 13 | T(0,0,0); O(0,200,-800); L35 | T(0,0,0); O(0,200,-800); L28 | T(0,0,-307.69232177734375); O(0,200,-492.30767822265625); L28 | T(0,0,-250); O(0,650,-1600); L28 |
| 14 | T(0,185,0); O(0,245,-700); L35 | T(0,185,0); O(0,245,-700); L28 | T(0,185,0); O(0,245,-700); L28 | T(0,185,0); O(0,245,-700); L28 |
| 15 | T(0,100,0); O(0,500,-1400); L30 | T(0,100,0); O(0,500,-1050); L24 | T(0,0,492.857177734375); O(0,600,-1542.857177734375); L28 | T(0,0,-250); O(0,700,-1800); L28 |
| 16 | T(0,100,-150); O(0,270,-750); L35 | T(0,100,-150); O(0,270,-750); L28 | T(0,0,10.76922607421875); O(0,370,-910.7692260742188); L28 | T(0,0,-350); O(0,650,-1600); L28 |
| 17 | T(0,80,-70); O(0,400,-1050); L35 | T(0,80,-70); O(0,400,-1050); L28 | T(0,0,61.5384521484375); O(0,480,-1181.5384521484375); L28 | T(0,0,-250); O(0,650,-1600); L28 |
| 18 | T(0,0,0); O(0,200,-800); L35 | T(0,0,0); O(0,200,-800); L28 | T(0,0,-307.69232177734375); O(0,200,-492.30767822265625); L28 | T(0,0,-250); O(0,650,-1600); L28 |
| 19 | T(0,0,-1000); O(0,800,-1000); L35 | T(0,80,-70); O(0,400,-1050); L28 | T(0,0,61.5384521484375); O(0,480,-1181.5384521484375); L28 | T(0,0,-250); O(0,650,-1600); L28 |
| 20 | T(0,-27,0); O(550,140,275); L35 | T(0,-27,0); O(550,140,275); L35 | T(0,-27,0); O(550,140,275); L35 | T(0,-27,0); O(550,140,275); L35 |
| 21 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 |
| 22 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 |
| 23 | T(0,0,100); O(0,500,-1325); L36 | T(0,0,100); O(0,500,-1325); L36 | T(0,0,100); O(0,500,-1325); L36 | T(0,0,100); O(0,500,-1325); L36 |
| 24 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 | T(0,-80,0); O(2850,425,0); L250 |
| 25 | T(0,0,0); O(4300,830,2520); L32 | T(0,0,0); O(4300,830,2520); L32 | T(0,0,0); O(4300,830,2520); L32 | T(0,0,0); O(4300,830,2520); L32 |
| 26 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 | T(0,350,0); O(2200,3500,0); L80 |
| 27 | T(0,0,0); O(4300,830,2520); L32 | T(0,0,0); O(4300,830,2520); L32 | T(0,0,0); O(4300,830,2520); L32 | T(0,0,0); O(4300,830,2520); L32 |
| 28 | T(0,0,0); O(200,2000,0); L100 | T(0,0,0); O(200,2000,0); L100 | T(0,0,0); O(200,2000,0); L100 | T(0,0,0); O(200,2000,0); L100 |

## PROVED: native distances and FOV, before and after

D below is native settled eye-to-focus distance in centimetres; L is the lens
word. The position matrix, native lens scale, eye-to-target distance, pitch,
vertical/horizontal FOV, projected focus/backfield and receiver samples for
all **480 cases** are in [camera_far_receipts.json](docs/mod_editor/camera_far_receipts.json).
Each row below was repeated for both field directions and 4:3, 16:9 and 16:10.
“Cap” means 96 executions of the real live callback with the fixture's
blocking predicates false and its reset predicate false.

| State | Retail Standard D / L | Retail Far D / L | New Standard D / L | New Far D / L |
| --- | --- | --- | --- | --- |
| 1 | 973.088 / 35 | 973.088 / 28 | 973.088 / 28 | 2055.480 / 28 |
| 8 | 2215.727 / 36 | 2346.196 / 28 | 2346.196 / 28 | 2346.196 / 28 |
| 9 | 1241.219 / 35 | 1241.219 / 28 | 1241.219 / 28 | 2166.218 / 28 |
| 10 | 821.523 / 35 | 821.523 / 28 | 821.523 / 28 | 821.523 / 28 |
| 11 | 1323.112 / 36 | 1416.201 / 28 | 1416.201 / 28 | 1416.201 / 28 |
| 12 | 3691.206 / 35 | 3691.206 / 35 | 3691.206 / 35 | 3691.206 / 35 |
| 13 | 824.621 / 35 | 824.621 / 28 | 824.621 / 28 | 1960.867 / 28 |
| 14 | 821.523 / 35 | 821.523 / 28 | 821.523 / 28 | 821.523 / 28 |
| 15 | 1523.155 / 30 | 1209.339 / 24 | 1209.339 / 28 | 2166.218 / 28 |
| 15 zoom on | 2282.542 / 30 | 2282.542 / 24 | 1364.734 / 28 | 2277.060 / 28 |
| 16 | 973.088 / 35 | 973.088 / 28 | 973.088 / 28 | 2055.480 / 28 |
| 16 cap | 1801.559 / 35 | 1801.559 / 28 | 1339.555 / 28 | 2197.566 / 28 |
| 17 | 1218.524 / 35 | 1218.524 / 28 | 1218.524 / 28 | 1960.867 / 28 |
| 18 | 824.621 / 35 | 824.621 / 28 | 824.621 / 28 | 1960.867 / 28 |
| 19 | 2154.066 / 35 | 1218.524 / 28 | 1218.524 / 28 | 1960.867 / 28 |

| Lens | Vertical FOV | Horizontal FOV 4:3 | Horizontal FOV 16:9 | Horizontal FOV 16:10 |
| --- | --- | --- | --- | --- |
| 24 | 65.606093 | 80.311997 | 89.999995 | 83.974421 |
| 28 | 57.837387 | 71.749983 | 81.202589 | 75.295242 |
| 30 | 54.553531 | 68.038702 | 77.319620 | 71.507778 |
| 35 | 47.687436 | 60.104895 | 68.877979 | 63.361029 |
| 36 | 46.505188 | 58.715507 | 67.380135 | 61.927513 |

The maximum allowed positive extension uses retail Far's corresponding native
state delta from its own pre-snap eye distance, floored at zero. This makes
pass-zoom off permit no positive extension; pass-zoom on allows 1,041.323 cm;
the retail live cap allows 560.340 cm. This revision also passes a stricter
125 cm maximum extension test for both new rows.

| Transition / maximum positive extension beyond pre-snap | Retail Far | New Standard | New Far |
| --- | --- | --- | --- |
| Pass zoom off | 0.000 | 0.000 | 0.000 |
| Pass zoom on | 1041.323 | 123.515 | 110.842 |
| Live cap | 560.339 | 98.336 | 31.348 |

The earlier custom Far live cap reached **3849.384 cm** from the focus; now
it reaches **2197.566 cm**. Its pass-zoom-off eye changes 2311.926 to
2166.218 cm, with vertical FOV 65.606093 to 57.837387 degrees. With zoom on,
its focus distance changes 2258.871 to 2277.060 cm, while eye-to-target
separation drops 2692.582 to 2042.670 cm and the lens narrows from 24 to 28.
Thus not every definition of distance decreases; the actual projected framing
is tighter and the extension over pre-snap is small. The receipt retains the
prior custom Far baseline with the corrected native solver for comparison.

## Projection acceptance and limits

The regenerated [schematic](docs/mod_editor/camera_far_projection.png) uses
native projection of a synthetic field and players, not gameplay/GPU output.
`60090`, both setup callbacks, `5F760` including its type-2 eye addition,
`5E100/66A90`, native view basis installation and `2AC80/2AB40` execute.
Position/lag histories and lens start at the declared settled values. The
focus is fixed and velocity is zero; the only substituted predicates are
`12DF0`, `64BE0`, `887D0`, each explicitly false. Separate tests exercise the
latter two blocking paths and pending-transition lag/reset behavior.

Native framebuffer x is normalized from 720 to 640; y stays 480. The scorebar
rails are exactly `[84,381,560,429]`. New Standard's pre-snap line of scrimmage
is **y=288.320**, 92.680 px above the bar; Far's is **y=221.812**, 159.188 px
above. Vertical positions match across all three aspects within 0.001 px.
Pass receiver samples are feet/head at `(x,z)=(-800,500),(800,500),(-1600,2500),
(1600,2500),(0,4000)` cm relative to focus, with heights 0 and 175 cm.
All remain within x=0..640 and above y=381, for both rows, both pass options,
both directions and all three aspects.

**Known limit, PROVED in this fixture:** retaining retail Far's physical
Standard eye leaves its 500 cm backfield sample at y=420.216 inside the bar,
and its 700 cm sample at y=532.196 off screen. The requested **line-of-scrimmage**
clearance passes; this is not a promise that every deep backfield player's
feet clear the bar. Far's corresponding y values are 263.178 and 286.864.
Moving Standard's eye farther back would violate the specified original Far
physical position. This tradeoff is documented for Noah's witness, not hidden
by adjusting the fixture. No GPU, dynamic receiver-following, ball arc,
sideline, split-screen or full scene transition result has been witnessed.

## Ownership, integration and fail-closed behavior

`REQUESTS` remains `(("nfl2k5_camera", "code", 64, 16),)`: 23 entry-wrapper
bytes, 16 load-wrapper bytes, 25 CC padding bytes, no RW/RO request. No owner,
page count or budget fixture change. Both XBE gates compose this owner in
both orders. Sealed unions without it refuse. All changed sections are
repinned; exact replay changes zero bytes. Mixed/foreign fields, callbacks,
shared descriptors, pins and old descriptor-only/r63-camera-far installs
refuse before mutation. Rebuild old outputs from retail.

The first cave-gate run failed before its tests because the supplied release
manifest contained an obsolete 64-byte camera wrapper declaration at
`14DA400`, while its final directory assigned camera to `14DA830`.
The old recorder collected declarations from both the Experimental preset
and the complete owner probe. The correction validates the wrapper receipt
against its actual named allocation and publishes that child only at finish.
For the old protected manifest, the test projection derives the obsolete
address from `preset_values` through the dispatcher request planner and
accepts only that exact, complete, same-size/alignment camera span. Unknown,
partial and altered spans still refuse; retail reservations remain intact.
A dedicated test reproduces both layouts and verifies one final named child.
This is no allocation or free-space exemption.

The camera source pin in the unified provider is updated. No protected
runtime/build/GUI file was changed. Existing build behavior needs no wiring;
[WIRING.md](WIRING.md#r63-camera-v2-paired-presets-and-modest-pass-framing-2026-09-07)
contains the concrete protected tooltip refresh and manifest regeneration
handoff. The protected release manifest must be regenerated by Claude before
release; the local corrected gate projection is not a substitute release file.

## Validation

All tests were run standalone with plain Python; optional native tests have
precise missing-XBE/Capstone/Unicorn skips. No tests loaded a whole disc or
pack. Final results are listed below. No test exceeded 2 GB RSS; the larger
25 GB outer process limit was also respected.

| Command | Result | Peak RSS (KiB) |
| --- | --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_camera_far.py` | 16 passed, 57.496 s | 748448 |
| `python3 tests/mod_editor/test_nfl2k5_camera_far.py CameraPatchTests.test_every_partial_install_foreign_context_and_old_version_refuses` | 1 passed, 7.807 s | 142284 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 79 passed, 296.660 s | 292504 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 95 passed, 381.258 s | 515560 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | 3 passed, 5.942 s | 136252 |
| `python3 tests/mod_editor/test_nfl2k5_widescreen_polish.py` | 13 passed, 6.725 s | 341200 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | 13 passed, 5.843 s | 300092 |
| `python3 tests/nfl2k5_camera_test.py` | 10 passed, 13.342 s | 141200 |
| `PYTHONPATH=. python3 tests/mod_editor/test_camera_inspection.py` | 17 passed, 0.005 s | not measured |
| `python3 tools/nfl2k5_camera_far_proof.py --json docs/mod_editor/camera_far_receipts.json --png docs/mod_editor/camera_far_projection.png` | 480 cases; PNG inspected; 32.66 s | 588800 |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | Passed; unchanged camera 64-byte request | not measured |
| `python3 tools/nfl2k5_my_career_assemble.py --check` | Passed; template unchanged | not measured |
| `python3 -m mod_editor --inspect-camera-options nfl2k5` | Passed; read-only retail map | not measured |
| Provider `Nfl2k5UnifiedVisualProvider.module_pins` SHA-256 census | All 226 files match, including revised camera | not measured |
| `python3 -m py_compile` for all eight edited Python files; `git diff --check` | Passed | not measured |


The initial measured free space was **101,276,381,184 bytes**, above 100
decimal GB; a late reading was **107,350,835,200 bytes**. Only small XBE copies
in a resolved TemporaryDirectory were used by BuildPlan verification and
removed on exit. No acceptance disc or pack was created. Scratch was 1.1 MB
before bundle delivery and remains below 200 MB. No other worktree or retail
input was changed. The source XBE hash was checked again during final audit.

## Noah's witness and required play list

The only new gameplay observation supplied to this task was Noah's witness
of disc **2026-09-07az**, containing the landed r63-camera-far patch:

> before, regular cam was zoomed in, so I switched to far. Now it appears that you set it to far, which is even farther, and now when I switch back to default cam, it's how far used to be... I like the new far default presnap because it would be nicely over the scorebug area, that's fine, but when I throw it zooms out a tad too far, needs cleanup... normal camera looks better after switching to far... ideally, the current far stays as far, make default a bit further, somewhere in between where it was originally and the extra far, the OG far but at our custom angle.

This observation supports keeping Far pre-snap and reducing pass pullback.
It does not witness this revision. Required checks, both 4:3 and widescreen v3:

1. Boot; load old Standard, Far and Custom Settings/Franchise saves; enter
   Quick Game, Franchise and Practice. Confirm Far is selected each time.
2. Switch Standard/Far repeatedly in Options before the snap and after plays;
   confirm both camera steps feel sensible and the selection lasts for the
   session. Check the scorebar's top rail and deep shotgun/backfield feet,
   particularly Standard's known fixture limitation. Restart to confirm Far.
3. In each preset, throw short flat/screen, medium crossing and deep sideline
   passes, both directions, with Pass Play Zoom Out off and on. Follow the
   receiver, airborne ball, catch, incompletion, interception and sack. Check
   that the smaller pullback keeps the intended receiver readable.
4. Repeat with QB Pivot and Runner Pivot toggled, human/CPU control changes,
   near either goal line and with prolonged scrambling. Watch for growth,
   abrupt angle changes, lag, reset jumps or clipped targets.
5. Kick FG/PAT, punt and return kickoffs/punts in both camera choices. Check
   specialized views and transitions. Record which scene corresponds to each
   numeric state where identification is still a hypothesis.
6. Enter/leave replay and cutscenes, inspect the pause preview, then resume
   play. Test MyCareer using its existing setup and Options choices. Check
   that presentation does not lose the session choice or create a lens jump.

## Delivery

Camera-only patched XBE SHA-256: `291e20c0fe76c4b337631fd1e87923dd9ebb5e85167c2726243bfacb1cd436b9`.
All 28 edit receipts and repinned section identities are in the JSON.

The explicit-path `git add` attempt failed because the shared worktree git
metadata could not create `index.lock`: **Read-only file system**. The normal
branch index and HEAD remain unchanged. The authorized fallback is
`.scratch/r63-camera-v2.bundle`, containing an explicit-path commit on a local
`astra/r63-camera-v2` ref with parent `477443e`. Delivery metadata, including
the full commit ID and bundle hash, is in `.scratch/r63-camera-v2-delivery.json`.
The 13 deliverable paths remain in this worktree. `ASTRA_BRIEF.md` and all
scratch contents are excluded from the commit. No push was performed.

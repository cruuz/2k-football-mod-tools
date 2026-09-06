# APF 2K8 into NFL 2K5: port research

2026-09-06. Research against branch `astra/r62-apf-port-research`, base
`7d46618`. **EXPERIMENTAL / UNWITNESSED.** No gameplay was witnessed.

**Yes, APF can supply useful source material for improving 2K5. The strongest
near-term paths are selected play assignments and ordinary roster ratings.
Individual animations look technically achievable after additional binding and
retarget work. APF's tackle, blocking and coverage systems require deliberate
2K5 implementations; they cannot be installed by copying animation files or
compiled PowerPC code.**

The bounded work found:

- APF has 5,884 animation definition records and 5,256 distinct primary names.
  Exactly 632 primary names match the fresh 2K5 archive catalogue; 4,624 do not.
  These are name differences, not 4,624 proved missing football behaviors.
- The APF frontend animation exporter works, but its 17 rotation channels,
  six local translation channels, separate root trajectory and 21-joint rig do
  not match either pinned 2K5 embedded destination's 23 rotation words. All
  four supported 2K5 destinations passed native no-edit checks; the APF export
  failed the required import contract. **No APF converter is delivered.**
- Of 4,948 APF master PLAY nodes, 4,910 survive endian conversion followed by
  2K5 decode/re-encode exactly. All 38 failures are opcode `0x1C`, which loses
  operand bits. No APF numeric opcode lies outside 2K5's 29-entry table. This
  is substantial shared representation, still short of a safe play converter.
- Seven penalty curves have identical float-pair bytes in both executables
  after endian conversion. The 17 fantasy-draft priority weights are also
  identical. Copying these values provides no new improvement.
- Twenty-five ordinary, named APF rating fields were carried through the
  existing 2K5 record codec into a synthetic recipient, changing exactly those
  25 bytes. Rating transport works; equivalent on-field effects are unproved.

## Evidence and scope

**PROVED** below means bytes examined in this session, recovered corpus data
flow actually read, or bounded CPU checks actually run. **HYPOTHESIS** means
an interpretation, proposed rule, retarget choice, effort estimate or expected
football result. Reading an old passing test report does not make that test a
fresh execution. Old witnesses in other research are not witnesses for this
port. There was no network, emulator, display, audio, real-disc build or push.

Paths used throughout:

| Alias | Read-only source |
| --- | --- |
| `STORAGE` | `/media/noah/Storage/for codex 1.0` |
| `APF-DOC` | `/home/noah/2k-football-mod-tools/docs/research` |
| `APF-C` | `STORAGE/research/functions/apf2k8` (`ledger`, `pseudo_c`) |
| `APF-PPC` | `STORAGE/build-static-recomp-apf` |
| `NFL-C` | `/home/noah/2k-football-mod-tools/research/functions/nfl2k5` |
| Hub | `/home/noah/Desktop/2K5-8 Editors/BONE_ANIM_RESEARCH_2026-09-05.md` |

`docs/research` is absent from this worktree. Its existing main-checkout copies
were read in place; nothing under that checkout was written. Unqualified
code/report paths refer to this worktree. Small receipts and research scripts
are retained locally in `.scratch/apf-port/`, excluded from the commit.

## 1. Animations

### 1a. What APF has, and what the comparison actually measures

**PROVED, fresh retail bytes.** I decrypted/decompressed the pinned APF XEX
with the existing `tools/xex_extract_pe.cpp`, then read the definition table at
`0x84D75500..0x84DB4850`: 5,884 records, each `0x2C` bytes. The pointers at
`+00/+04/+08` select the filename, primary name and optional paired name;
`+0C/+10` select roots; `+14/+18` hold aggregate/variant information. The last
four words are zero throughout the table.

On 2K5, `tools/nfl_resource_scan.py` and the current
`python3 -m mod_editor.core.nfl2k5_animation ... catalog` command produced the
catalogue. This revision has **`catalog`, not `inspect`,** as its inventory
subcommand. To ground the extracted catalogue in the specified original disc,
I streamed every animation resource span from the XISO and compared it against
the extraction. All **61,096,560 bytes across 5,198 resource spans** matched.
The APF XEX, master PLAY and selected frontend clip were independently read
through the APF ISO's XDVDFS extents too.

| Measurement | APF | 2K5 |
| --- | ---: | ---: |
| Definition-table records | 5,884 | No equivalent complete XBE definition census claimed |
| Distinct primary `ANM_` names | 5,256 | 2,972 distinct archive resource names, including production names |
| Distinct literal `.ani` filename strings | 4,323 | No exact filename-stem match in the archive name set |
| Records with paired-name fields | 4,921 | 639 MMCD resources, a different counting unit |
| Distinct primary plus paired strings | 8,851 | 110 distinct XBE `ANM_` strings, all already in the archive name set |
| Archive animation resources | Existing corpus: 68 SingleMoCap resources, distinct from the embedded definition library | 4,559 SMCD + 639 MMCD = 5,198 |
| Parsed archive roots | Not equated to definition count | 6,068 |
| Direct, distinct, non-null APF registry roots | 8,349 | Only two embedded roots are pinned by the current tool |

Two of APF's 8,851 registry strings are paired names without the `ANM_`
prefix: `AMB_HUD_08_061213_01_M` and `AMB_HUD_11_061213_01_M`. Thus there
are **8,849 distinct `ANM_` identifiers**, consistent with the earlier string
scanner's 8,850 occurrences/8,849 unique strings. Twenty-five filename fields
have trailing spaces. They were preserved in the inventory, with whitespace
trimmed only for the explicit filename-stem comparison.

There are **1,480 null primary-root fields** and 3,945 non-null paired-root
fields. A named definition does not guarantee an embedded primary payload;
null does not prove absence from every other package or load path. Every one
of the 8,349 direct roots has the recovered 17-rotation/six-translation count
layout. Their stored rates are 8,161 at 15 Hz, 106 at 60 Hz, 72 at 12 Hz and
10 at 30 Hz. This is a header census, not a full decode of 8,349 clips.

The existing `apf_mocap.md` corpus covers 68 separately serialized
SingleMoCaps in outers 659/1310/1493: 67 normal bodies and one compact mirror
alias, 1,301,080 bytes total. Sixty-six normal clips are body motions and the
remaining `hand_pose` uses 15 rotation channels at 60 Hz. Those archive
counts are prior corpus results, not a new all-IFF scan performed here; the
selected `1493/59` body was checked directly against the ISO. The bulk APF
gameplay definition library must not be reduced to those 68 frontend/system
resources.

The exact-name join finds **1,081 matching definition records, representing
632 distinct primary names**. Across primary and paired names together, 995
distinct strings match the archive catalogue. The remaining 4,803 definition
records represent 4,624 unmatched primary names. Critically, **4,127 of 2K5's
5,198 resources use names without `ANM_`**, and most embedded gameplay
motions are not semantically catalogued. Renamed or embedded relatives remain
possible. A missing name is a candidate for investigation, not proof that
2K5 cannot perform that action.

The following bins are **PROVED lexical counts**, not recovered runtime
selectors. The classifier removes annual tags, then takes the first matching
prefix in this order: gang; blocking; celebration/taunt; catch/receive; QB;
contact; receiver release; movement; handoff/formation; official; remainder.
Examples include `BLOCK/BLK/PULL`, `CELEBRATE/CEL/TAUNT`,
`CATCH/RECEIVE/INCOMPLETE`, `QB/PASS/TOLINEQB`, and
`BUMPANDRUN/WRLAUNCH/TELAUNCH/WR`. Every primary definition enters one bin.

| Primary-name family | APF records | Distinct names | Exact matching 2K5 names | Unmatched distinct names |
| --- | ---: | ---: | ---: | ---: |
| Blocking | 826 | 826 | 0 | 826 |
| Receiver release / press | 388 | 388 | 0 | 388 |
| Other tackle / contact | 355 | 355 | 0 | 355 |
| Gang tackle | 78 | 78 | 0 | 78 |
| Catch / receive | 333 | 333 | 4 | 329 |
| Quarterback | 347 | 326 | 26 | 300 |
| Celebration / taunt | 229 | 178 | 126 | 52 |
| Movement / recovery | 570 | 570 | 86 | 484 |
| Handoff / formation action | 500 | 218 | 206 | 12 |
| Official / coach | 108 | 106 | 43 | 63 |
| Other / postplay / ambient | 2,150 | 1,878 | 141 | 1,737 |
| **Total** | **5,884** | **5,256** | **632** | **4,624** |

Zero in the blocking or gang-tackle match column does **not** mean 2K5 lacks
blocking or multi-player contact. The prefix bins also differ from substring
searches: for example, APF has 347 primary names containing `CATCH`, while
the ordered catch/receive bin has 333 entries.

Concrete APF donor candidates, all re-read from the definition table:

| Candidate | Definition VA | Primary root | Meaning established so far |
| --- | --- | --- | --- |
| `ANM_GANG_TACKLE_D_L_HIGH_G_F_HIGH_RH(0)` | `0x84D83838` | `0x83E6D6B0` | Gang-labelled variant, paired name, aggregate `0x83E6FE0C`; synchronization not retargeted |
| `ANM_CATCH_2K8_RUN_ACROBATIC_JUMP_L_0_RH` | `0x84D86120` | `0x83CE7728` | Acrobatic catch label and opposite-side partner |
| `ANM_2K8_PASS_REACT_ELWAY_WALK` | `0x84D8026C` | `0x83FCC930` | Named QB reaction, not proof of a throwing algorithm |
| `ANM_2K8_QB_POCKET_STAND_MARINO` | `0x84D908B4` | `0x83511790` | Signature pocket stance and paired/mirror root |
| `ANM_CELEBRATE_SIGNATURE_ICKEY_WOODS_L` | `0x84DA45D0` | `0x82167D88` | Signature celebration, a promising later single-actor donor |
| `ANM_BLOCK_2K6_PASS_LOW_B(0)` | `0x84D7E6C0` | `0x8409BB00` | Older-generation blocking variant, aggregate `0x8409C820` |
| `ANM_CELEBRATE_USER_34` | `0x84DA5498` | Null | Exact shared identity with 2K5 `archive:3092/163`, not a demonstrated equal APF payload |

There are five primary `SIGNATURE` celebration identifiers: Ickey Woods,
two Emmitt Smith gestures, Charley Hayes throwing the ball, and Dirty Bird.
Other names explicitly identify Montana, Marino, Elway, Payton's scissor
move and Sanders' high step. **PROVED:** these names and definitions exist.
**HYPOTHESIS:** their animations or selection logic would improve 2K5.

The question's phrase “the same 2K6-lineage clips 2K5 already has” needs a
chronology correction. APF retains later-generation material; 2K5 predates
2K6. The earlier `apf_2k6_animation_lineage.md` and
`apf_2k6_animation_runtime.md` identify 519 distinct `2K6` names across 597
primary/paired fields, 225 filenames, 597 roots and 75 aggregates. The fresh
primary-field census has 309 `2K6` records and **zero `2K6` archive names in
2K5**. Primary annual tags are 13 `2K3`, 102 `2K4`, 296 `2K5`, 309 `2K6`,
122 `2K7` and 2,119 `2K8`; the rest are untagged. The older shared identifiers
establish lineage, not identical animation samples.

The existing runtime study also connects 49 selector groups/149 names through
initializer `0x848AF560`, caller `0x848D55DC`, and lookup helper
`0x848AEB78` with `0x24` selector stride. That is stronger than finding text,
but does not bind every APF definition to every actor or make the stock
selectors compatible with 2K5.

### 1b. Skeleton, codec, basis and timing

**PROVED for the selected frontend branch:** the APF export chain joins the
clip lookup and map setup at `0x84A11B58`, matrix update at `0x84A11C24`,
shadow initializer `0x84AA4430`, wrapper `0x84AA4288` and hierarchy owner
`0x84B0FA88`. The selector/lookups include `0x84A121D0`, `0x84A12338`,
`0x84A12368` and `0x84A62394`; the map data are at `0x820FC510` and
`0x820FC55C`. These addresses do not establish a general full-player map.

| Property | APF source | 2K5 destination | Consequence |
| --- | --- | --- | --- |
| Named rig | `player_shadow`: 21 rows | Player low SCNE: 25 bones; high: 62; head: 27 | No one-to-one channel copy |
| Actual APF player assets | Low player: 52 `def_` bones; high player: 92 | 25/62 are 2K5's own hierarchy | Frontend proof must not be described as full gameplay skeleton proof |
| Packed body sample | Usually 17 rotations + six local translations | Player main stream: 23 rotations; referee: 21 | Both having “23” packed units is misleading |
| Root header | 48 bytes, big endian; archive relative pointers `+20..+2C`; embedded roots use absolute pointers | 52 bytes, little endian; archive pointers `+24..+30`; pinned XBE roots use absolute pointers | Headers cannot be copied or globally word-swapped |
| Quaternion words | Eight bytes, three signed 20-bit values plus selector | Four bytes, three biased 10-bit values plus selector | Decode, retarget, then quantize again |
| Rotation scale | `23 / 2^24` for signed values | Float bits `0x3AB55FA3`, approximately `0.00138377060648` | Lossy 2K5 representability must be measured |
| Quaternion lanes | Recovered APF WXYZ; glTF XYZW | Native WXYZ; glTF XYZW | Explicit reordering and hemisphere handling |
| Basis | Right-handed, Y up, centimeters | Right-handed, Y up, centimeters | glTF uses meters, scale `0.01`; matching axes alone does not match rest orientations |
| Local translations | Six animated vectors; signed-20 mode uses `/1024` cm | Current importer only replaces main rotation words | Cannot silently discard animated joint translations |
| External trajectory | Separate packed stream, short components times `0.125` cm | Separate actor/root trajectory; retained unchanged by import | A moving donor needs a root-motion solution outside today's writer |
| Stored rates | 12/15/30/60 Hz in registry root census | 6,022 archive roots at 15 Hz, 46 at 12 Hz | Destination times/counts remain fixed |
| Events and pairs | Timed events, mirror/variant aggregates, possible multi-actor binding | Events, trajectories, MMCD and selectors retained | A tackle/catch port includes more than pose keys |

APF's 21-row frontend hierarchy is:

```text
0 root (-1)
1 r_hip_hinge_base (0), 2 r_femur (1), 3 r_knee_hinge (2), 4 r_ankle (3)
5 l_hip_hinge_base (0), 6 l_femur (5), 7 l_knee_hinge (6), 8 l_ankle (7)
9 thorax (0)
10 l_clavicle (9), 11 l_shoulder_hinge_base (10), 12 l_humerus (11),
13 l_elbow (12), 14 l_hand (13)
15 head (9)
16 r_clavicle (9), 17 r_shoulder_hinge_base (16), 18 r_humerus (17),
19 r_elbow (18), 20 r_hand (19)
```

Numbers in parentheses are parents. The fresh 2K5 low-player SCNE has:

```text
0 root (-1)
1 lfemur (0), 2 ltibia (1), 3 lfoot (2), 4 ltoes (3)
5 rfemur (0), 6 rtibia (5), 7 rfoot (6), 8 rtoes (7)
9 waist (0), 10 thorax (9), 11 neck (10), 12 head (11)
13 lcollar (10), 14 lhumerus (13), 15 lelbow (14), 16 lwrist (15), 17 lhand (16)
18 rcollar (10), 19 rhumerus (18), 20 relbow (19), 21 rwrist (20), 22 rhand (21)
23 lshoulderpad (10), 24 rshoulderpad (10)
```

The named 2K5 hierarchy comes from `SCNE 3/113`, not SKEL. `SKEL 3/116`
contains 25 normalized axis records in 400 bytes and does not supply bone
names or parentage. High-player `3/114` has 62 records; head `3/115` has 27.
The low/high SCNE bone spans are 2,800/6,944 bytes. APF's 52-row low-player
BoneScaleMap order matches its low rig, while 26 rows move in its high rig.
Neither is a numeric mapping onto 2K5's SKEL.

The 2K5 player channel map at `0x0051CD70`, initialized at `0x00217E10`,
drives 23 primary channels; wrists 16/21 are derived through `0x00091890`.
The referee's 21-channel map is `0x0051D010`; its 25-row hierarchy includes
upper-arm twists and differs from the player rig. Higher detail also involves
`0x00092140`, hierarchy `0x00093800` and proportion scaling `0x00093850`.

**HYPOTHESIS, retarget starting correspondences:** APF femur/knee/ankle can be
related anatomically to 2K5 femur/tibia/foot; clavicle/humerus/elbow/hand to
collar/humerus/elbow/hand; thorax and head to their namesakes. APF's extra hip
and shoulder hinges require composing transforms. 2K5's waist, neck, toes,
shoulder pads and derived wrists require an explicit rest-pose and motion
distribution policy. Copying local quaternions by anatomical name is not that
policy. The candidate converter must compare world-space motion, reconstruct
destination-local transforms, retain the destination's proportions, then use
its compiled channel map. The two embedded recipients currently lack even
that last proved map.

Decoder anchors: APF `0x84638450` unpack, `0x846385A8` interpolation,
`0x8463A320` sample, `0x846394D0` matrix, `0x84638720` trajectory,
`0x846392C8` interval. NFL `0x000DED10` unpack, `0x000DF700` sample,
`0x003CA270` interpolation, `0x000DEE30` trajectory with scale at
`0x004F24E4`; actor trajectory continues through `0x002CC570` and
`0x00037EB0`. See the packed-pose, transform-semantics and bone-binding APF
memos, both bone reports, and `mod_editor/core/nfl2k5_animation_math.py`.

### 1c. The concrete glTF route and its exact boundary

The available APF derivative is
`STORAGE/assets/intermediate/apf2k8/skinned/1310_0415_player_shadow_mnu_stn_01_070130_01_lg.gltf`
and its adjacent `.bin`. Its source is SingleMoCap `1493/59`,
`mnu_stn_01_070130_01_lg`, **22,288 bytes**, 117 stored frames at 15 Hz and
duration `7.7166666984558105` seconds. There are 116 stored keys inside that
duration. The derivative has 927 baked keys at 120 Hz and 24 tracks: 17
rotations, six local translations and one external root translation. The mesh
has 351 vertices, 306 triangles and 21 one-hot joints.

**PROVED, fresh structural validator PASS:**
`tools/validate_apf_player_shadow_gltf.py` checked the source/derivative
hashes, joint/weight/accessor relationships and numerical export contracts.
It reported maximum angle `9.80911239e-06` degrees on its checked samples.
It did not execute the title or prove a continuous-time error bound. The
export uses normalized base/heading/scale and separate trajectory
`[X(t)-X(0), Y(t), Z(t)-Z(0)]`; Y stays absolute. The portable derivative is
not a claim of bit-identical Xenon interpolation.

The current 2K5 importer can receive **main-word replacements** for these
four selected identities:

| Identity | Frames × rotations, rate | Stored duration | Writable main-word budget | Binding status |
| --- | --- | --- | ---: | --- |
| `xbe:0086dfe0` | 29 × 23, 15 Hz | `1.8333333730697632` s | 2,668 bytes at `0x0086D540` | Embedded skeleton and football role unresolved |
| `xbe:008528e8` | 27 × 23, 15 Hz | `1.683333396911621` s | 2,484 bytes at `0x00851F00` | Embedded skeleton and football role unresolved |
| `archive:3092/163` | 93 × 23, 15 Hz | `6.083333492279053` s | 8,556 bytes | Proved player map; `ANM_CELEBRATE_USER_34` |
| `archive:3107/27` | 46 × 21, 15 Hz | `2.9666669368743896` s | 3,864 bytes | Proved referee map; delay-of-game gesture |

The table means “can receive an import compiled for this destination,” not
“already accepts a retargeted APF clip.” The core compiler can manipulate
additional single-root SMCDs, but the public archive check/import path rejects
an unknown skeleton family. **MMCD paired/multi-root import refuses before
reading a bundle.** There is no supported insertion of new motion identities,
channel counts, frame counts or arbitrary embedded spans.

The first embedded root occupies `0x0086D478..0x0086E014` (2,972 bytes):
29 trajectory records/174 bytes and five events remain untouched. The second
occupies `0x00851E38..0x0085291C` (2,788 bytes): 162 trajectory bytes and
six events remain untouched. Both have flags `0x0E`, mirror enabled, loop
disabled and time multiplier 1.0. These are occupied retail `.rdata` spans,
not caves. `nfl2k5_animation_xbe.py` replaces only allowed rotation words and
repins the section digest; it requests no executable allocation.

The nearby 2K5 animation-selection investigation connects roster byte `+4F`
to the parity test at `0x002D92B1`, branches `0x002D946B/0x002D94A7/0x002D94BF`
and selector tables `0x00AD2088/0x00AD2048/0x00AD2068`. It has **not** proved
that either writable embedded root is a particular quarterback's throw style.
Do not advertise one as a Marino/Elway release slot.

`nfl2k5_animation_import.compile_import` requires:

1. The literal filename `primary.gltf`, adjacent `primary.bin` and a fresh
   target-specific `animation.native.json` sidecar.
2. The JSON document equal to the target's native template, including identity,
   nodes, channels, samplers, accessors and timing. Whitespace/key order can
   vary; arbitrary glTF structure cannot.
3. Exact binary length and unchanged float32 frame times. After `4*F` time
   bytes, rotations are channel-major glTF XYZW, `16*C*F` bytes. Only rotation
   samples are editable. No `.glb`, extra track, new joint, root trajectory or
   translation-track import is supported.
4. Finite unit quaternions, native packing error at most 0.35 degrees, and
   numerical pose preflight at native frames, quarter intervals, mirrored
   variants, loops and duration boundaries. Limits are 0.75 degrees against
   the requested native pose and 1.0 degree against glTF interpolation. These
   finite samples are not a continuous motion or contact proof.

**What I actually did:** exported each of the four 2K5 seeds, ran its CLI
`check` against the original XBE/XISO, and got `changed_bytes: 0` with passing
pose preflight. Then attempted the APF derivative directly, which refused
with `Choose primary.gltf from a native export bundle`. Renaming it into each
target bundle, with that target's valid sidecar, refused with
`Fixed glTF structure, identity, channels or timing changed`. This is eight
expected APF refusals. A separate `archive:3098/0` MMCD probe refused with
`Paired and multi-root animation import is disabled`. Retail XBE SHA-256 was
unchanged afterward. Baseline bundles were restored after the refusal probe.

The existing standalone tests also proved that modest **native 2K5** edits can
change words, repin both embedded spans, remain idempotent and pass the pose
gates. That validates the recipient writer, not an APF retarget. There is no
APF-derived positive `changed_bytes` result in this session.

**Decision: no converter.** An exact APF-to-2K5 round trip was not established.
The blockers are the missing embedded skeleton/selector binding, unequal rest
hierarchies, six animated local translations, separate trajectory, immutable
destination time/count budgets, preserved contact events and lower precision.
The source duration is also much longer than either embedded slot. A time
warp or crop is an authored change, not an exact round trip. Durations are
not always `(frames-1)/rate`; endpoint/padding policy must follow the native
sampler. Numerically stuffing one APF channel into an unknown target channel
would not resolve these issues, even if the quantizer accepted it.

A future converter needs a versioned source/target map including rest frames
and parent composition; a declared policy for unmatched bones and translations;
an in-place or externally controlled root-motion contract; exact target sample
times; hemisphere-continuous sampling; and a measured fixed-word error/pose
receipt. Preserve the native target bundle and fill only its quaternion buffer.
For a single donor, decoded poses, both rigs, one sub-megabyte glTF and the
roughly 12 MB XBE fit comfortably in **64 MiB of intended working buffers**;
budget 256 MiB process RSS and 10 MiB retained output, with a hard 64 MiB
per-block APF decompression cap. These are proposed budgets, not measured
converter performance. No disc copy, whole pack, new cave or animation pool
growth is needed for a same-span single-actor experiment.

### 1d. Facial CurveAnim

**NOT PORTABLE through a known 2K5 consumer.** APF's separate corpus has
2,324 normal facial CurveAnim resources plus a sentinel. The established
registry is `0x82003E10`, type CRC `0xF4257702`, load `0x84668C00`, relocation
`0x84668528`, inverse `0x846684B0`, lookup `0x849CD578/0x849CD710`, and
runtime retention `0x84AAA310`. Its four relative pointer fields are known;
the facial curve codec and complete facial application semantics are not a
body-mocap retarget contract. See `APF-DOC/apf_curve_anim.md`.

Fresh searches found zero `CurveAnim` ASCII/UTF-16LE strings and zero literal
little-endian `0xF4257702` words in the pinned 2K5 XBE. The full archive
inventory and bounded corpus searches located no corresponding named type or
consumer. 2K5's head skeleton is not evidence of a CurveAnim reader. This is
**PROVED negative evidence within those searches**, not mathematical proof
that no computed or differently named facial system exists. Recreating a
facial rig, player binding and facial runtime is a separate engine/asset job;
it is a poor first port.

## 2. Gameplay data and code

### 2a. What is actually portable

The APF corpus does not establish a complete list of superior algorithms over
2K5. It establishes several data representations and code paths, many inherited
from the earlier engine. Names such as gang tackle, catch and signature stance
identify content; they do not settle the outcome rules. The table distinguishes
an existing 2K5 mechanism from an APF algorithm actually recovered.

Verdicts use the requested categories. **DATA-PORTABLE NOW** is restricted to
values an existing 2K5 writer can represent, with explicit no-op or synthetic
proof limits. **PORTABLE AS AN X86 OWNER** is a feasibility judgment for a
bounded rule; every proposed owner below is **HYPOTHESIS**, not installed
code. **NOT PORTABLE** means not through the demonstrated data/owner contract,
not impossible after an unrestricted engine rewrite. Estimates are incremental
RX/RW/RO bytes and hook counts, not reservations or promises of APF parity.

| APF subject | Existing 2K5 equivalent and address | Verdict, evidence and bounds |
| --- | --- | --- |
| Ordinary base ratings | Named bytes `+36..+51`; UI label/getter lists `0x004F5258/0x004F55B8`, labels `0x000E5CC0`; `nfl2k5_roster_records.py` | **DATA-PORTABLE NOW, PROVED field transport** for 25 ordinary named fields. No hooks or allocation. Different rating-to-action curves can produce different results. |
| Signature abilities / star tiers / style behavior | Existing abilities owner, native move entry/accounting paths and `+4F` animation-family selector | **PORTABLE AS AN X86 OWNER, HYPOTHESIS** for a narrowly specified ability. About 256-1,536 RX, 0-256 RW, 1-3 added hooks. APF star/ability metadata is not compatible with Studio's authored bit assignments. |
| Shared 21 gameplay sliders | UI table `0x00501F54`; synchronizer `0x000E3DC0`; factor builder `0x0017B8A0`, getter `0x0017B8F0` | **PROVED shared values/range; NOT PORTABLE as a ready automated profile import.** The existing cross-title surface is inspection, not a safe general profile writer. Values can be entered semantically in 2K5's menu; layouts must not be blob-copied. |
| Catch/drop odds, acrobatic catches | Outcome `0x001C78D0`, RNG call `0x001C8317`; existing `nfl2k5_catch_slider.py` | **PORTABLE AS AN X86 OWNER, HYPOTHESIS** for a measured probability rule: roughly 128-768 RX, 0-64 RW, 1-2 hooks. APF final catch probability/table consumer remains unresolved. Animation availability and catch eligibility are separate. |
| Fatigue and stamina | Human/CPU Fatigue globals `0x00E600F0/0x00E60114`, getters `0x0014AB20/0x0014B390`; Stamina record `+39`; shared factor access above | Stamina is **DATA-PORTABLE NOW** as a base rating. A changed depletion/recovery rule is **PORTABLE AS AN X86 OWNER, HYPOTHESIS**, 256-1,024 RX, 64-256 RW, 2-3 hooks after locating actual update/reset consumers. APF Fatigue controls are `0x84F3F9BC/0x84F3F9E0`; no APF recovery curve was proved. |
| Penalty rates and thresholds | Ten current typed curves, below; `0x001B0AE0` settings accessor; `0x000B1440` enable path; record table `0x00A89950` | **DATA-PORTABLE NOW, PROVED byte representation** for seven unchanged curve payloads; copying is a no-op. A different APF curve requires its count, x-domain, unit and consumer proved before using `nfl2k5_penalties.py`. No APF improvement is established by the matches. |
| Throw distance, accuracy, flight | `nfl2k5_throw_tuning.py`; lob-speed count/table `0x0050BCB8`, reads `0x002D898B/0x002D8992`; `nfl2k5_throw_arc.py` | **NOT PORTABLE as identified APF data today.** No corresponding APF source curve was recovered here. Same-count calibrated values could use the existing writer with zero hooks; a new rule is **HYPOTHESIS**, roughly 256-1,024 RX and 1-2 hooks. Signature QB pose does not establish flight physics. |
| Progression / aging curves | `0x004F31D0..0x004F4CB0`, profile map `0x004F27B0`, draw weights `0x00521680`; aging `0x000E63F0`, delta lookup `0x000E5890` | **NOT PORTABLE as an APF improvement established here.** 2K5 already has the system and a writer. APF retained franchise assets do not prove improved live aging. A future proven same-layout donor could be a data edit with no hooks. |
| Fantasy-draft priorities | 17 floats at `0x00589588`; `0x0036EE70`, rank `0x0036EDD0`, candidate `0x0036F0A0`, pick `0x0036F830` | **PROVED identical APF/NFL values**, so no worthwhile port. This fantasy-draft lane is distinct from the existing franchise draft/free-agency owner at `0x0031E0F0/0x00324414`. No improved APF draft owner was proved. |
| PLAY assignments, route landmarks, block types, reads | Opcode table `0x00521078`; validator `0x001A9840`; formation reader `0x0017FE60`; current PLAY codec/compiler | **HYPOTHESIS for a selected data translator**, no hooks if entirely stock 2K5 grammar. Existing writer can hold validated chains, but APF operands, links, formation extensions and `0x1C` differences prevent **DATA-PORTABLE NOW** for arbitrary APF plays. |
| Tackle resolution / contact momentum | Resolver `0x001D9C50`, Break Tackle accessor `0x0017B010`, reads `0x001D9D62/0x001DA39F`; reaction `0x001DBDB0` | **PORTABLE AS AN X86 OWNER, HYPOTHESIS** for a bounded outcome-input rule: 512-1,536 RX, 0-256 RW, two shared hooks. Existing Momentum already owns this lane. Full APF resolver behavior was not recovered or budgeted. |
| Gang tackles / synchronized contact | Native resolver and reaction family; paired motions require animation and actor coordination | **NOT PORTABLE as a clip/table port.** A full APF behavior needs participant ownership, matching poses, root alignment, transitions and interruption rules. A simpler second-contact rule might be an x86 project, but it would not be APF gang tackling. No honest small byte estimate for the full system. |
| Blocking target choice / double teams | `0x0023ABB0/0x0023F450`; target assignment `0x002FAFF0`; threat-side slide `0x0023B6E0` writes `0x00C16BAC` | **PORTABLE AS AN X86 OWNER, HYPOTHESIS** for one bounded target-choice rule: 1,024-4,096 RX, 128-512 RW, 2-4 hooks. Native block paths and double-target coordination already exist. An APF block animation does not replace those decisions. |
| Coverage reaction / pursuit | Reaction `0x001F4250`; zones `0x001A6220/0x001A5090/0x001A5790`; man `0x001A2E70`; movement/facing `0x00217AE0/0x003CA1E0` | **PORTABLE AS AN X86 OWNER, HYPOTHESIS** for a specified reaction/steering rule: 512-2,048 RX, 128-768 RW, 2-4 shared hooks. APF equivalent live algorithm not recovered. Existing Coverage/QB Spy owners must compose. |
| Lead-blocker control | NFL lead-block grammar `0x11` type 4 through `0x0023ABB0/0x0023F450`; actor control lifecycle differs from route data | **PORTABLE AS AN X86 OWNER, HYPOTHESIS** only after proving input/control transfer. Estimate 2-8 KiB RX, 256-1,024 RW, 4-8 hooks for an experiment; hook sites are unproved. Not a SPLB option, and not a scoped near-term recommendation. |
| General momentum / foot planting / locomotion blending | Existing NFL movement and Momentum owners; contact and animation systems above | A bounded acceleration/turn rule is **PORTABLE AS AN X86 OWNER, HYPOTHESIS**, typically 512-2,048 RX plus state. The whole APF blend tree, constraints and asset-dependent foot planting are **NOT PORTABLE** through a simple owner or data copy. |

### 2b. Data findings in detail

**Ratings.** The final, corrected section of
`APF-DOC/apf_rating_slot_settlement.md` is authoritative; the earlier
APFe-derived conclusions in the same memo were withdrawn. I independently
re-read all 27 descriptors at `0x820E4D94`, stride `0x60`: abbreviation at
`+00`, full name at `+0C`, setter at `+18`. The 44-byte setters contain the
actual `stb` displacement and a 0..100 clamp. The descriptor names and offsets
match `mod_editor/data/apf2k8_player_ratings.v1.json`.

| Rating | APF byte / setter | 2K5 record byte |
| --- | --- | --- |
| Speed | `BA` / `0x84745838` | `36` |
| Agility | `BB` / `0x84745878` | `37` |
| Arm strength | `BC` / `0x847458B8` | `38` |
| Stamina | `BE` / `0x84745938` | `39` |
| Strength | `C1` / `0x847459F8` | `3C` |
| Coverage | `C3` / `0x84745A78` | `3E` |
| Tackle / break tackle | `C6/C7` / `0x84745B38/0x84745B78` | `40/41` |
| Pass accuracy / read coverage | `C8/C9` / `0x84745BB8/0x84745BF8` | `42/43` |
| Catch | `CA` / `0x84745C38` | `44` |
| Run / pass blocking | `CB/CC` / `0x84745C78/0x84745CB8` | `45/46` |
| Secure Ball / Hold Onto Ball | `CD` / `0x84745CF8` | `47` |
| Leadership / composure | `D3/D5` / `0x84745E78/0x84745EF8` | `4C/4E` |
| Consistency / aggressiveness | `D7/D8` / `0x84745F78/0x84745FB8` | `50/51` |

The full 27-row receipt is `data_probe.json`. APF roster `1126/0` is
2,294,304 bytes, with 2,254 player records of `0x14C` bytes; 2K5 records are
`0x54` bytes. The fresh bounded test copied player index 0's 25 ordinary
named fields into a synthetic 84-byte 2K5 record through
`decode_record/encode_record`, changed exactly those 25 offsets and reproduced
the entire result through a second decode/encode. It did not create a roster
mod or preserve an arbitrary player's overall rating across titles.

APF's four neutral fields `BD/C5/D2/D4` stay unnamed. The probe excluded
Kicking Style and Scramble, even though their **labels** are proved, because
the 2K5 style/parity consumers require separate semantics. APF's schema has
31 fields/27 named; do not identify the whole `BA..D9` area as 32 ordinary
ratings. Stock observed values are 0..99, native setters allow 100, and the
schema says to display 100 exactly rather than silently clipping it.

**Sliders and fatigue.** Both games expose Human and CPU Blocking, Passing,
Running, Catching, Coverage, Pursuit, Tackling, Kicking and Fatigue, plus
Injury/Fumble/Interception: 21 names, range 0..1, UI step 0.025. APF offline
`0x84E4B088` and online `0x84E4C7C8` share callbacks/globals. APF
`0x8470A578/0x8470A630` exports/imports 84 bytes in the order Interception,
Human nine, CPU nine, Injury, Fumble. NFL's indexed synchronizer writes CPU
nine first, then Human nine, with separate global sliders. A blob copy would
misassign values.

APF synchronizer `0x849FE0D0` moves Human Catching `0x84F3F9C0` to
`0x84F3FC44` and CPU `0x84F3F9E4` to `0x84F3FC20`. I read its generated
PPC body and the importer. The final indexed APF catch-result consumer is
still unresolved. NFL Catching is `0x00E600F4/0x00E60118`; the current 2K5
catch owner already redirects RNG call `0x001C8317` and exposes different
offense/interception scaling. The older cross-title audit's unresolved NFL
catch-outcome statement is superseded by that later work. Neither fact proves
APF uses the same probability rule or that equal sliders give equal drop rates.

No safe general save/profile transfer was executed. Existing saves can
override executable defaults. An automated slider port needs a bounded
container/integrity writer or a separately proved live/default owner, not an
edit to inspection JSON. `gameplay_inspection.py` is an inspection surface.

**Penalty curves.** The brief and an old source comment say nine; the current
`nfl2k5_penalties.TABLES` actually contains **ten**, including neutral-zone
width. The following exact big-endian float-pair sequences were found uniquely
in the fresh APF image:

| 2K5 semantic table | 2K5 first pair | APF equal first pair | Pairs / units |
| --- | --- | --- | --- |
| Offensive holding | `0x0050CDF8` | `0x820CA1F8` | 5, probability |
| Defensive holding | `0x0050CE24` | `0x820CA224` | 5, probability |
| Clipping | `0x0050CE50` | `0x820CA250` | 5, probability |
| DPI | `0x0050C6D0` | `0x820C9B00` | 4, hazard multiplier |
| DPI radius | `0x0050C734` | `0x820C9B48` | 4, centimeters |
| Roughing | `0x0050C6AC` | `0x820C9ADC` | 4, seconds |
| Neutral-zone width | `0x0050C758` | `0x820C9B6C` | 3, multiplier |

**PROVED bytes:** all seven pair payloads match. **PROVED additional data
flow:** APF `0x84943480` selects the two holding tables with count 5, calls
clamped piecewise-linear interpolation `0x8463FC88`, compares its result to
RNG `0x84B3E8B8`, and dispatches `0x8493F9F8/0x8493FAF0`. This continuation
is visible in `APF-PPC/ppc-filtered/ppc_recomp.109.cpp`; Ghidra incorrectly
marks the interpolation calls non-returning and truncates the caller.
APF `0x8493E360` also supplies the neutral-zone candidate to that interpolation
leaf. The other exact matches were not all traced through complete consumers;
their APF semantic labels remain correspondences to confirm, rather than a
blanket proof of identical penalty systems.

The 2K5 writer requires the same knot counts and exact x coordinates, and
validates y values by their units. Its stock holding payloads are therefore
already the candidate APF payloads. The full-pair searches found no match for
late hit (`0x0050C6F4`), face mask (`0x0050CD48`) or ineligible downfield
(`0x0050C678`). That proves no *identical sequence* in the image, not the
absence of those APF penalties or the identity of any different nearby curve.
Do not relabel radius, grace-time or distance curves as probabilities.

**Draft and progression.** The fresh audit pins the 17 APF floats at
`0x820F4B70` and duplicate `0x820053F0` to exactly the 2K5 priority values:

```text
2.0, 0.1, 0.2, 1.4, 1.0, 1.1, 1.1, 1.7, 1.0,
1.2, 1.2, 0.7, 0.5, 1.1, 1.3, 1.4, 1.3
```

NFL table `0x00589588` is read inside `0x0036EE70` at operands
`0x0036EEFA/0x0036EF22`; the restoring return is `0x0036F095`, beyond the
older ledger's shortened range. The APF audit finds no conventional direct
materialization of the main donor table or proved equivalent live draft owner.
There is no reason to replace the already built 2K5 franchise draft AI with
these unchanged fantasy-draft weights.

APF's converted franchise, manual and reference material should not be read as
proof of better active franchise logic. The manual preserves 1,553 old text
slots, including edits from 60 to 40 Weekly Prep hours, and the reference
package is statically orphaned under the documented searches. These are
lineage findings in `apf_nfl_cut_content_lineage.md`,
`apf_manual_nfl_remnants.md` and `apf_reference_nfl_remnants.md`, not
evidence of a ready APF progression engine to install in 2K5.

### 2c. SPLB, PLAY, routes, blocking and reads

**SPLB is membership and selection data, not the action VM.** The existing APF
SPLB study describes 15 fixed 32,288-byte books, `0xB0` formation-selection
records and up to 84 packed 16-bit entries per selection list. The low ten
bits are the master play index; `1023` terminates the list. I read the actual
recompiled counter at `0x84A8AC30`: null checks, halfword loads, mask `0x3FF`,
sentinel and 84-entry bound. Related routines are nth selection `0x84A8BD20`,
find `0x84A8AA80`, master lookup `0x84AE8C40`, personnel construction
`0x84860020`, assignment `0x8485E768` and role map `0x820FC320`. Category
work at `0x8485BD38` is not automatically CPU down-and-distance AI.

The current `mod_editor/core/apf2k8_splb_writer.py` investigation has many callers of
`0x849FCF60`, but no closed down/yards-to-go selection rule. Picker
`0x8486CE88`'s `+2BC` field is a tab, not proof of third-down logic. Copying
SPLB order into a NFL book does not transplant APF CPU play calling.

**PROVED, fresh parse of actual PLAY bytes:**

| | APF | 2K5 |
| --- | --- | --- |
| Resource | MASTER `180/0`, `mpb`, 182,096 bytes | 37 fixed books, each 78,736-byte body / 78,768-byte wrapper |
| Formations | 163, stride `0xB8` | 1,533 total, stride `0xB4` |
| Plays | 586, stride `0x64` | 9,251 total, stride `0x60` |
| Categories | 28 | 835 total |
| Eight-byte nodes | 4,948 | 91,833 |
| Slot descriptors / pointers | Eleven pairs at play `+0C/+10` onward | Eleven pairs at `+08/+0C` onward |
| Extra fields | Additional play word `+08` and formation extension | No demonstrated corresponding field |

Shared case-folded names: 114 formations, 428 distinct plays, 23 categories.
The fresh `tools/playbook_lineage.py` result reproduces 88 unique APF versus
94 NFL descriptors, 78 common after transformation; 161 APF play occurrences
(155 names) have the same name and all eleven converted descriptors, and
101 occurrences/names also match all eleven **first** nodes. These are not
full-chain matches. For example, APF MASTER play 2, `Weak Iso`, matches
ARZ outer 307 play 81 at that first-node/descriptor boundary.

The descriptor transform is not just endian conversion. For APF numeric bytes
`[A,B,C,00]`, `C` must be `B0/B4/B8/BC`:

```text
H = 1 if C & 0x04 else 0
L = 0xB0 | (1 if C & 0x08 else 0)
NFL = (H << 24) | (L << 16) | (B << 8) | nibble_swap(A)
```

The inverse round-trips every observed descriptor. The ten APF descriptor
values absent in NFL are **not ten unsupported opcodes**.

For nodes, the established representation comparison keeps the first four
bytes and reverses the final four-byte operand word. I then applied the
current 2K5 `Node.from_bytes(...).to_bytes()` to every node. Positive control:
all **91,833 NFL nodes** re-encode exactly. APF: **4,910 exact, 38 changed,
zero exceptions**. Every changed node is `0x1C`; every APF numeric opcode has
a table entry in 2K5. The following labels are the **NFL decoder's labels**,
not an assertion that every APF action has identical semantics:

| Opcode(s) | NFL interpretation | APF node count |
| --- | --- | ---: |
| `01` | Start | 1,128 |
| `02/03/04` | Snap To / Ball Action / Special Move | 65 / 181 / 126 |
| `05/06/07/08` | Hold / Dropback-Pass / Punt / Place Kick | 1 / 143 / 1 / 5 |
| `09/0A/0B/0C` | Run point / Coverage sprint / Rush lanes | 17 / 78 / 179 / 32 |
| `0D/0E/10` | Zone / Man / Rush direction | 368 / 134 / 48 |
| `11/12` | Block leg / Route segment | 474 / 842 |
| `13/14/15/16/17/18` | Handoff / Fake / Follow / Take / Fake take / Release | 29 / 42 / 60 / 57 / 34 / 51 |
| `1A/1B/1C` | Motion-link / Defense start / Defense align | 88 / 727 / 38 |

Neither corpus uses `00`, `0F` or invalid `19`; NFL's stock node pool also
does not use `1C`, though its decoder/encoder table includes it. This makes
`1C` a concrete evolved/unused-path question rather than an out-of-range
opcode. APF node 2,967 at body `0x1D77C` illustrates the loss:

```text
APF bytes:                1c 60 00 00 40 05 2f 0b
Endian-only NFL candidate: 1c 60 00 00 0b 2f 05 40
NFL decode/re-encode:      1c 60 00 00 0b 03 05 00
Operand bits lost:        0x40002C00
```

Across the 38 cases, lost bits occupy the high two bits and portions of bits
10..13. Their APF meaning is unresolved. **Answer to “which opcodes have no
2K5 equivalent?”:** no numerically unsupported opcode was found; no semantic
equivalent has been proved for these extended `1C` operands. The remaining
opcodes still require APF consumer and chain-termination checks. A decoder
round trip alone does not validate receiver references, control flow or what
the game will execute. A bounded search for the exact NFL-style opcode flag
table in the APF image found no matching candidate at the tested 16/20/24/32
byte strides, so I did not invent an APF dispatch-table address.

2K5 can already express useful football assignments:

- Route segment `12` supports straight/break/in/out/comeback and chip/block
  variants. NFL node coordinates are biased one-foot values, converted with
  30.48 cm/foot; formation positions are signed centimeters. The APF operand
  consumer must establish the corresponding scale, including mirroring.
- Block `11` types 0/1/2/3/4 select drive, pass set, pull/trap, release then
  block and lead. Types 8/9 use absolute/named targets. `0x0023ABB0` and
  `0x0023F450` actually dispatch these paths. I read the pass-set branch adding
  `0x00C16BAC`, and its `0x0023B6E0` threat-side producer. Target coordinator
  `0x002FAFF0` already handles candidate exchange and double assignments.
- Zone `1B -> 0D` reaches `0x001A6220` and later zone callbacks; man `0E`
  reaches `0x001A2E70/0x001A5BC0`. A landmark does not author match-coverage
  policy. Read/motion `1A` reaches `0x001ACE40/0x001AC7B0`; its predicates
  are not a new edge/apex recognition system.
- Screens and option transfer already have native grammar and later owners.
  Screen timing uses `0x00229AE0/0x0019C740`; the landed screen hooks are
  `0x0023ECD2` and `0x0019C7E9`. Preserve read-option pairing and their shared
  pass-initializer contract instead of installing a second competing detour.

A safe selected-play converter must resolve SPLB selection to MASTER index,
map categories/personnel/formation slots, translate all eleven descriptors,
decode every reachable chain with proved APF termination/branch semantics,
map units and actor references, refuse unknown operands including unproved
`1C`, rebuild target-relative pointers through the NFL compiler, and pass the
NFL validator. It must preserve or explicitly translate APF's extra fields.
2K5 capacity is 50 formations/270 plays/26 categories per fixed book. Node
pool capacity is resource-specific; post-route opaque bytes are not free
space. Deduplicate/reuse legal chains and refuse overflow. The existing APF
route writer only clones descriptor/pointer pairs within MASTER; it does not
already translate APF actions into NFL nodes. No cross-title play writer was
created in this research task.

### 2d. Existing owners and the recompilation boundary

Do not build features already on this branch and describe them as APF ports.
The current owners provide the implementation pattern and several requested
effects already:

| Existing work | Concrete boundary |
| --- | --- |
| Momentum contact | Two Break Tackle reads in `0x001D9C50`; at most six added collision points, combined cap eight with run-up. No impulse solver or APF formula transplant. |
| Abilities runtime | 1,072 RX bytes; seven hooks at `0x00075CC8`, `0x0015647D`, `0x0018EC6D`, `0x001CD550`, `0x002D43F0`, `0x002D46D0`, `0x002D4740`; native move gates/accounting. |
| Coverage slider | 16-byte immutable allocation; operand sites `0x001F4282/0x001F432C`; reaction goes from `(C+0.25)*0.15` to `C*0.225`. No APF equation was used. |
| Zone drop / facing | Initializer hook `0x001A65D1`, 78-byte wrapper in 80 bytes; sustained facing is deferred. Fresh `nfl2k5_zone_facing` audit passed and reports `patch_available: false` for those later tiers. |
| QB Spy | Current source requests 2,048 RX / 768 RW / 512 RO, superseding the older 1,536 RX report. Shared zone callbacks `0x001A5790/0x001A5090`, with man/rush and reset ownership. |
| Screen hooks / read option | Screen owner 640 RX; existing paired PLAY intent and pass-initializer composition. |
| Defensive try, penalties, throw tuning, progression, draft AI | Existing rule/data owners. Their presence does not establish matching APF inputs. |

Sources: the corresponding `ASTRA_*_REPORT.md` files, current modules,
`ASTRA_PLAY_RULES_REPORT.md` and its executable evidence manifest. Older
reports' test counts are historical unless repeated in the validation section.

The brief's batch-2 addendum supersedes its old 1.5 KiB spare-code warning:
v3 has 104 KiB RX, 84 KiB RW, 16 KiB general RO and a directory page.
However, planned owners consume much of that capacity, especially RW. A new
build needs an explicit budget row and a plan against the full current request
union. This memo makes **no allocation**. Future code must expose `REQUESTS`,
install immutable code/data through `nfl2k5_xbe_space.py`, pin retail hooks,
refuse foreign/mixed bytes before mutation, repair digests and compose in both
orders through both XBE gates. Sharing a hook requires one coordinated owner
contract, not two detours that happen to target the same address.

The APF static recompilation is useful reference material, not a portable
gameplay library. I read generated code for the slider importer/synchronizer,
SPLB counter, personnel builder, packed decoder and holding rule. In
`ppc-filtered/ppc_recomp.1.cpp`, `0x84638450` still contains a
`__builtin_debugtrap()` for `vupkd3d128` and an unimplemented vector operation.
Later composed variants improve selected instructions, but their own report
still identifies 1,076 unresolved switch occurrences, 190 targets and 334
fail-fast import stubs. Those are report findings, not a fresh recompilation
or boot performed here.

Even a host-linked translation needs guest memory layout, big-endian loads,
PPC register/stack conventions, floating/vector status, indirect dispatch,
XDK imports, allocation and game-owned objects. The original Xbox executable
expects 32-bit x86 conventions and different objects/resources. A small
recovered rule can be rewritten as a 2K5 owner with its own tests; copying
generated C++ into a cave or treating successful linking as title execution
would not establish compatibility. See `apf_static_recomp_all_tus.md`,
`apf_static_recomp_opcode_switch_composed.md` and `apf_decompilation.md`.

## 3. Presentation

| Candidate | Yes/no and evidence |
| --- | --- |
| Camera framing as a native 2K5 preset | **Yes to authored 2K5 data; HYPOTHESIS for exact APF coefficients.** Fresh `camera_options_audit.py` confirms APF's menu table `0x84E40940`, names `0x820D9FA0` and blocks `0x84E11E00`, stride `0x440` with 17 `0x40` slots. Six authored names exist, five are reachable under current bounds `0x84A15D00/0x84A15D5C/0x84A15540`. NFL has six menu presets but eight internal rows at `0x004F03F8`, 29 states per row. Counts do not establish matching state slots. |
| HUD/scorebug layout and style | **Yes to rebuilding the appearance with 2K5 anchors/art; no direct SCNE/runtime copy.** APF global outer 1310 has seven scorebug components (inners 106/131/156/235/250/262/360), descriptor family `0x84EAD3F8..0x84EAD51B`, callbacks including `0x8472A660/0x84ABE4C8`. NFL uses `346/78 score_bug`, atlases `346/53 score_buga`, `346/26 shield_espn` and shared font `3/46`; loader `0x000FC1A0`, table `0x00A95C60`, init `0x000FCCD0`, update `0x000FCE70`. Reauthor into those bindings. |
| Replay overlays / wipes | **Yes to separately authored native art; no proved APF behavior/data transplant.** APF `gamedata.iff` outer 659 has `instantreplay` LAYT inner 45 using `replayoverlay`; loader `0x849D7A48`, wipe controller `0x847B7858`, event table `0x84A80AA8`. NFL's replay resources are separate from its field-scorebug binding. Camera cuts, event timing and replay state require native callbacks. |
| Xenos renderer, shaders, facial blend system or replay engine | **No within this scope.** Platform/asset/runtime dependencies do not fit a camera or HUD data writer. |

`nfl2k5_camera.py` already writes the seven Standard descriptors
`0x00A88870..0x00A88A50`, selecting only look-at/lens/offset words and
retaining type, lag and callbacks. Consumers are `0x00060090`,
`0x0005F760` and state/row owner `0x000A5490`. NFL's lens is passed as
`value/18` into projection, not simply degrees of FOV; matching APF field units
and state meaning is required. The current Far-look default already copies
proved NFL Far values. A second arbitrary “wider” preset is not evidence of
an APF port.

Current NFL layout/texture writers are newer than the old comparison memo's
writer-gap statements: use `tools/nfl2k5_scorebug_layout.py` and the current
scorebug owner/format tools. APF anchor counts and screen dimensions should
guide an authored layout, not direct coordinate copying. APF `game_cast_scorebug`
in season outer 1215 is not the field HUD. APF's digital font is tiled
DXT5A/alpha-only; NFL's atlas has a different codec. No GUI, raster export,
audio decode or renderer proof was run for this section. Source:
`APF-DOC/scorebug_presentation_modding.md`, fresh camera receipt and current
camera/scorebug code.

## 4. Five next builds, ranked by value times feasibility

Scores are **HYPOTHESIS**, each 1..5; they express engineering priority, not
measured gameplay improvement. A prerequisite that fails ends that build with
a documented blocker rather than an approximate “successful port.” Every
result remains EXPERIMENTAL / UNWITNESSED until Noah's listed witness.

| Rank | Build | Value × feasibility | Why this order |
| ---: | --- | ---: | --- |
| 1 | Selected APF play-assignment translation | 4 × 4 = 16 | Extensive byte lineage plus a complete destination codec/writer; no new animation engine |
| 2 | APF legend rating preset for named 2K5 recipients | 3 × 5 = 15 | Exact ordinary-field transport already demonstrated; small, reviewable data change |
| 3 | One independent celebration retarget | 5 × 2 = 10 | Directly answers the animation question with fewer synchronization dependencies than catches/tackles |
| 4 | One recovered APF blocking-choice rule as a 2K5 owner | 5 × 2 = 10 | Potential gameplay value; requires actual source-rule recovery and shared-hook work |
| 5 | APF-informed camera composition | 2 × 4 = 8 | Existing safe recipient writer, small data footprint and clear visual witness |

**1. Selected play translator.** Inputs: pinned APF MASTER `180/0`, its SPLB
selection entry, pinned NFL ARZ outer 307 and the two executable corpora.
Start with APF play 2 `Weak Iso` versus ARZ play 81 as a lineage control;
then choose one donor whose complete action chain differs meaningfully from
the target and uses only recovered operands. Recover APF termination,
descriptor/formation extensions, units and actor references first; explicitly
refuse `1C` and every unproved value. Write through
`nfl2k5_play_codec.py`, `nfl2k5_formation_play_writer.py` and the existing fixed-resource
compiler/pack pipeline, with **zero XBE hooks or allocated bytes**. Proof:
all eleven complete chains decode/re-encode, target stock validator accepts,
control is byte-identical, authored diff stays in exact declared spans,
overflow/mixed inputs refuse, and an idempotent receipt records every changed
byte. Witness: repeated calls against mirrored fronts, each eligible receiver
and blocker assignment, motion/audible, both field directions, sacks/pressure,
handoff timing and CPU use. One first-node match is not acceptance.

**2. Legend ratings preset.** Inputs: APF ROST `1126/0`, the 27-row descriptor
map and explicitly named existing 2K5 roster recipients. Select one small
position group, match people by explicit identity rather than numeric index,
and copy only the 25 ordinary semantic fields through
`nfl2k5_roster_records.py` and the current ROST/save writer. No new players,
ability bits, style bytes or global sliders in the first build; **zero hooks,
zero executable allocation**. Preserve all nonselected fields and native 100
values exactly, and refuse values outside the agreed destination range.
Proof: per-player before/after records, exactly allowed field offsets,
unchanged names/teams/pointers and resource size, valid destination container,
second-apply zero diff. Witness: player-card ratings, same play/difficulty and
sliders across controls, speed, catch, blocking, tackle and fatigue samples;
record whether the preset helps. This ports authored data, not APF's hidden
rating curves or star abilities.

**3. One celebration.** Inputs: pinned APF Ickey Woods candidate definition
`0x84DA45D0`/root `0x82167D88`, its actual in-game rig/map, and NFL
`archive:3092/163`. Use the known frontend export as a codec/basis control,
not as proof of this donor's rig. First prove donor map and recipient selector;
choose an in-place segment only if its local translations and trajectory can
be represented under an explicit exactness criterion. Build a versioned
retarget map and a converter that fills the target's existing `primary.bin`
without changing `primary.gltf`, sample count, sidecar identity or events;
writer is `nfl2k5_animation_import.py`, **zero hooks/allocation**, 64 MiB
working-buffer target. Proof must include a real APF-derived positive
`changed_bytes`, packed/pose limits, world-space joint/foot residuals,
refusal of unsupported translations, immutable retail input and exact allowed
span diff. Witness: trigger that celebration repeatedly, mirrored and both
directions; check feet/root sliding, hands/ball, body proportions, LOD changes,
entry/exit transitions and replay. Embedded slots wait for their missing map
and selector proof; no gang tackle or catch-contact promise in this build.

**4. One blocking rule.** Inputs: APF blocking definitions and recovered
gameplay consumers, NFL `0x0023B6E0`, `0x0023ABB0`, `0x0023F450` and
`0x002FAFF0`, existing screen/read-option/Momentum ownership. First identify
one APF target-choice or release condition with complete scalar data flow;
an animation name does not qualify. Re-express that condition around the
proved NFL target-choice path, retaining native animation selection and
engagement. Proposed ceiling **4,096 RX / 512 RW / 256 RO, 2-4 hooks**;
exact instruction boundaries and budget row require proof before code is
installed. Proof: bounded native-function comparisons on synthetic actor
geometry, retail fallback for unrelated assignments, null/stale/NaN guards,
reset and control-transfer tests, positive changed-byte receipts, both owner
orders and both XBE gates. Witness: fixed inside/outside rushes, double teams,
pullers, screen releases, user blocker control, both directions and no
teleport/oscillation. If no APF condition can be recovered, deliver that
finding instead of a generic “APF blocking” multiplier.

**5. Camera composition.** Inputs: APF camera block `0x84E11E00`, its actual
state/field consumers and pinned NFL Standard/Far descriptors. Recover one
APF scrimmage/live/pass framing policy in physical units, then author a native
NFL preset through `nfl2k5_camera.py`; retain its lag/type/callback ownership.
**Zero hooks/allocation** for representable fields; do not use an invented
FOV-degree conversion or change all 29 states. Proof: unit/state correspondence,
seven-recipient descriptor guards, only approved look-at/lens/offset diffs,
digest repair, idempotence and neutral unrelated camera rows. Witness: pre-snap,
run, deep pass, catch, sideline, both field directions, kick states, replay,
custom-camera/profile overrides and a same-scene comparison against the
already shipped Far-look option. If native fields cannot express the APF
policy, do not silently expand this into a replay-engine owner.

**Not worth attempting now:** bulk replacement of thousands of APF motions;
multi-actor gang-tackle import; a generic “APF gameplay.dll” made from static
recompilation; the facial CurveAnim subsystem; a whole renderer/replay/blend
tree transplant; a lead-blocker-control rewrite without recovered ownership;
copying identical draft/penalty numbers; restoring orphaned franchise material
as a gameplay upgrade; or replacing existing Momentum/Coverage/Abilities
owners merely to rename them APF. Simple catch/coverage calibration remains
useful within the existing owners, but this session found no recovered APF
formula that would justify calling such calibration an APF port.

## Validation and reproducibility

All reads were bounded by resource, executable or individual corpus shard.
The maximum measured RSS was **449,024 KiB**, from the fresh resource scan;
every test stayed well below 2 GiB. No whole disc or pack was loaded into RAM.
No game image was produced. The selected embedded-import test wrote only
temporary roughly 12 MB XBE copies and removed them on exit.

| Fresh execution | Result |
| --- | --- |
| Existing XEX extractor, built with `clang++-18` | 642 LZX blocks, 1,648 chunks, 54,001,664-byte pinned PE |
| `tools/nfl_resource_scan.py` | 4,323 outer entries, 86,882 resources; 4,559 SMCD + 639 MMCD |
| `nfl2k5_animation catalog` | 5,198 archive animations, 6,068 roots; two explicitly supplied embedded roots |
| `.scratch/apf-port/inventory_probe.py` | Full definition/name join; every archive animation matched original XISO span |
| `tools/validate_apf_player_shadow_gltf.py` | PASS, 21 joints, 927 keys, 24 tracks |
| `.scratch/apf-port/import_probe.py` | Four native CLI checks at zero changed bytes; eight expected APF refusals; MMCD refusal; retail XBE unchanged |
| `tests/mod_editor/test_nfl2k5_animation.py` | **16 passed**, independent portable C maximum lane difference 0 |
| `tests/mod_editor/test_nfl2k5_animation_import.py` | **18 passed** |
| Two selected `test_nfl2k5_animation_import_retail.py` tests | **2 passed**; both named archive seeds and both embedded roots |
| Existing gameplay audit via scratch provenance adapter | PASS, 21 sliders, 17 identical weights, no proved APF draft owner |
| `tools/camera_options_audit.py` | PASS, pinned cross-title camera descriptors and reachability bounds |
| `.scratch/apf-port/play_probe.py` + existing lineage tool | PASS, original APF ISO XEX/PLAY/clip hashes, all 37 NFL books, 4,910/38 APF node result, 91,833 exact NFL controls |
| `.scratch/apf-port/data_probe.py` | PASS, 27 setter/label pairings, 25-byte rating transport, seven identical penalty pair sequences, 38 explicit alignment differences, bounded CurveAnim negative search |
| `python3 -m mod_editor.core.nfl2k5_zone_facing --xbe ...` | PASS, source dependencies recognized; later facing policy still deferred |

The selected retail test command was:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.scratch/apf-port/tmp" \
NFL2K5_ANIMATION_INVENTORY="$PWD/.scratch/apf-port/resource_inventory.json" \
python3 tests/mod_editor/test_nfl2k5_animation_import_retail.py \
  RetailImportTests.test_gltf_roundtrip_and_edited_seed_pose_gates \
  EmbeddedTests.test_both_root_imports_repin_and_write_exact_copy
```

The resource scan/catalogue use the extracted NFL
`vc_53450030/0`, the fresh scratch inventory and the original `default.xbe`.
The APF glTF validator was given the absolute Storage model, skin, animation,
joint/vertex/binding TSV, inventory/corpus and export-report paths. Every input
and exact argument is recorded in the corresponding scratch log. The APF ISO
probe used known XDVDFS partition headers, selected partition base `0x0FD90000`,
streamed its XEX in 1 MiB blocks and decoded only the requested IFF blocks.

The generic gameplay audit initially failed because historical defaults pointed
to an absent APF ledger, then because it formatted external inputs using
`relative_to(worktree)`. The scratch adapter supplies the actual Storage
ledger and sets the in-memory report path anchor to `/`; no hash, instruction,
table or data-flow assertion was relaxed and no audit source was edited.
The extractor's initial `g++` build rejected vendored anonymous-union `be<>`
members; `clang++-18` built the same existing extractor successfully.
Scratch probe development also caught filename whitespace and a setter scan
that crossed into the next function; the final probes preserve whitespace
and check the actual 44-byte setter bodies. These were research harness
corrections, not production changes.

Pinned SHA-256 receipts:

| Input / span | SHA-256 |
| --- | --- |
| APF retail XEX, 38,408,192 bytes | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| Decoded APF image, 54,001,664 bytes | `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` |
| APF definition table | `40f063e925420c21076ccedc868524f0c83ea7f0eede25624e0b7606cc6f4497` |
| APF selected SingleMoCap body | `a665e57a7128f45d4394da8606e75215a17db444d3442ad7985b4aea48085af9` |
| APF MASTER PLAY | `2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891` |
| APF ROST body | `e959d3067ebcdbeb4f08979fa74d9fa61cf90fd91b90793863e6a3313be7f7ff` |
| NFL retail XBE | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| Concatenated, catalogue-ordered NFL animation spans | `5f53a4ad613826b0af69e58bb74f2be9de2310c2348851f35dfcc4a633fcce18` |
| NFL embedded `0086dfe0` occupied span | `c5e0c865cdb6b9f26d238311290f019e33f833f7b5f3f403018d6d48eea17b2a` |
| NFL embedded `008528e8` occupied span | `dd3667937fab95c93e265ef12300f24ce6d5aa9b5731d1204630b9351dad7999` |

No converter, patch owner, product setting or protected-file change was made.
Both XBE integration gates remain future acceptance requirements if an owner
is built; they were not needed or claimed as fresh passes for these two
documentation deliverables. The unresolved maps, APF extended operands and
source gameplay consumers are explicit next-work boundaries, not hidden
assumptions of a successful port.

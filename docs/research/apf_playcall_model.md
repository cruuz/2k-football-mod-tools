# APF 2K8 CPU offensive call: beta 67 P1

Research on branch `astra/b67-p1-offense`, 2026-09-12. Addresses below are BASE virtual addresses unless explicitly marked TU. Flat-file offset is VA minus `0x82000000`. No production play-calling code, studio code, writer, preset or patch was changed.

**PROVED** means pinned image/resource bytes inspected here, or bounded native execution recorded in `tests/mod_editor/test_apf_playcall_research_native.py`. It does not mean an in-game witness. **HYPOTHESIS** marks interpretation beyond those observations, the proposed design, and behavior that still needs a game witness. Each table row has a grade; a paragraph prefixed with a grade retains that grade throughout the paragraph. Proposed requirements in section 6 are HYPOTHESIS until implemented and tested.

**PROVED:** The premise supplied with this job needs correction. The ordinary CPU call uses a weighted category enumeration, followed by formation and play selection. Its four attempts do not walk the seven-step personnel row ladder. The separate lineup resolver has that ladder. An O-Singleback3WR compiled here with Jacks and Jokers survives the native normalizer and selects an added heavy formation at the goal line. The bounded result therefore does not establish any of the three proposed explanations for Urianus' exact observed failure.

**HYPOTHESIS:** Differences in his loaded book, saved working copy, match state, team tendencies or another caller can explain a different game result. None is singled out as the cause. His actual edited archive/save and an in-game call trace were not inputs to this job. The report gives a counterexample to a universal restriction, not a claim that his observation did not happen.

## Inputs and proof boundary

| Input | Pin / derivation | Grade |
|---|---|---|
| Owned `default.xex` | SHA-256 `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` | PROVED |
| Flat BASE | `apf2k8_xex.decode_xex`, 54,001,664 bytes; SHA-256 `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` | PROVED |
| Flat TU 1.1 | `apf2k8_xex.reconstruct_tu`; SHA-256 `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457` | PROVED |
| MASTER PLAY body | `0A`, decoded in memory; SHA-256 `2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891` | PROVED |
| Runtime MASTER | Native `0x84A8AD38` relocation and validation returns 1 after 7,189,487 instructions; all 586 plays acquire validity bit `0x80000` | PROVED |
| Book input | Real decoded SPLBs; additions compiled and verified with the existing SPLB writer, then normalized by native `0x84A8C790` | PROVED |
| Sparse disassembly and TU comparison | `docs/research/apf_playcall_b67_evidence.json`; full-span hashes, every changed instruction word in its listed spans, and numeric curve values | PROVED |

**PROVED:** Images remained in memory. The harness maps the flat image at `0x82000000`, SPLB at `0x00100000`, MASTER at `0x00200000`, and a small explicit match object graph in mapped scratch memory. MASTER relocation runs before any play-selection witness. Merely mapping the serialized MASTER is insufficient: its unvalidated plays would all fail the picker. Runtime metadata globals `0x8522C9B8` and `0x8522C9B4` must also hold MASTER and the native type metadata pointer, respectively.

**PROVED:** `tools/apf_playcall_research_probe.py` follows the existing Unicorn PPC32 big-endian pattern. It records adapted PCs and implements the inspected Xenon stack spills/restores, `extsw`, signed `fcfid`, low-word `rldicl`, immediate 64-bit compares, and two position-vector transports. Category, formation, play, normalizer and MASTER-validation callees execute native instructions. Integer RNG and uniform RNG are explicit boundary inputs, normally integer 1 and fraction 0.5. Kicker range is an explicit boundary return of 4,572 coordinate units. These three leaves are not represented as native RNG/kicker execution.

**PROVED:** Unless a test says otherwise, match state is first period, 900 clock units, tied score, three timeouts, zero urgency, no prior play history, and no player skill objects. Tests ending at `0x8486D0CC` execute selection and all output-tuple stores, but stop before the manager-current-call stores. The wrapper test stops at the selector entry. The ladder test stops before the 11-player builder. They prove those boundaries, not the final on-field lineup or animations.

**HYPOTHESIS:** The harness's scalar ABI adaptations suffice for the paths exercised here, not arbitrary Xenon code. Nonempty learned-history paths reach player/assignment objects absent from this minimal graph; their inspected reads and formulas below have static evidence, not a full native match witness. Random quantile examples are deterministic examples, not estimates of game frequencies.

## 1. Situation

### State graph and output contract

**PROVED:** Use these symbols: `G=0x851A2780`, `H=0x851595D0`, `U=0x84F3F8F8`, `M=[G+0]` current offensive manager, `D=[M+0x0C]` call/team state, `B=[M+0x20]` current SPLB, `S=[G+0x6C]` down/position state, `C=[G+0x0C]` clock object, `A=[M+8]` own score/team statistics, `O=[[M+0]+8]` opposing statistics. TU moves G and H by `+0x30`; U stays put. These are pointers to different objects, not offsets in one flat situation record.

| Address / instruction | Inputs read | Output or effect | Grade |
|---|---|---|---|
| `84815608..8481566C`; `lwz`, `cmp`, `stw`, `addi r4,r11,0x10`; tail `b 8486CE88` | Manager argument; `[85158350]` busy flag; `[G]`; `[U]` | For matching manager and mode >=5 or mode 2, clear the five output words at `85158360..85158370`, set busy=1, pass `r4=85158360` | PROVED |
| `8486CEB0..8486CF58`; `lwz r10,0x2BC(r11)` at `8486CEC4` | `[U]`, `[U+2BC]`, `[U+1F8]`, `D+40` | Only U modes 2/3 enter this override. Value 3 at +2BC tries the saved play pointer at D+40. Otherwise positive +1F8 indexes subtype table `84DBB2A8` and calls fetch | PROVED |
| `8486C9E4`; `lwz r11,0x34(r29)` | G+34 | Match-phase dispatch index. This is distinct from down | PROVED |
| `84867600`, `84866258`, `8493D800` | S+4 down; S+18 ball longitudinal coordinate; S+28 first-down target coordinate; `[[A+0C]+4]` direction float | Signed distance to gain; effective down; regular requested row | PROVED |
| `8486A250..A284`, repeated in special predicates | G+44 period; C+10 float clock; G+30 float | For period 1 or 3 add G+30 to C+10; clamp below zero. This is the effective time used in half/late-game decisions | PROVED |
| `8486A344..A3B8`, `84866B48..B64` | A+0 and O+0 | Own-minus-opponent score margin | PROVED |
| `8486A300..A32C`, `84866BE8`, `84866FCC` | A+4; opponent equivalents in clock estimates | Timeouts alter late-game run probability and clock-management decisions | PROVED |
| `8486A604/A614`, `8486A68C..A704`, `84868970` | Time-needed estimate, effective clock, score/late-state predicates | Resets and computes D+E4 float urgency. It is not the stored team pass/run slider | PROVED |
| `8486BD90` | Above fields; H+1BC or H+400 cached random value; H+1B8 or H+3FC time-needed estimate; kicker range | Special-play row or regular `84867600` row | PROVED |
| `8486D0B8..D0D8`; `stw r31,0(r23)`, `stw r30,4(r23)`, `stw r29,0xC/0x10(r23)` | Selected category, formation, play; output pointer | Tuple: +0 category pointer, +4 formation pointer, +8 untouched alternate field, +C/+10 duplicate play pointers. With null output argument use D+4. Then D+70=formation and D+68/+6C=play | PROVED |

**PROVED:** Coordinate constants include 91.44 per yard and 4,572 at the goal-line reference. The code computes distance to the attacking goal as `4572 - direction * ball_z`. Direction is reduced to a sign. The down/distance helper also clamps a small positive-distance interval. Field-position and distance are floats in this coordinate system; they are not integer yards in the state object.

**HYPOTHESIS:** G+44's user-facing interpretation is quarter/period, with 1/3 first quarters of each half, 2/4 second quarters and >4 overtime. This interpretation agrees with the inspected comparisons and time aggregation. UI labels for every clock-state bit and roster skill number are not established by this job.

### Both dispatch tables, entry by entry

**PROVED:** `0x8486C980` is a **formation-family** switch, used when C930 receives a non-null formation. At C958/C95C it reads formation+4 and arithmetic-shifts by 26. It is not thirteen situation buckets. Its entries are absolute code pointers. Family descriptions below follow their record use; the numeric dispatch and resulting row are pinned and natively exercised.

| Index | BASE target | Test / result before category enumeration | Grade |
|---:|---|---|---|
| 0 | 8486C9DC | Ordinary offensive family: request row 25, wildcard | PROVED |
| 1 | 8486C9DC | Ordinary offensive family: row 25 | PROVED |
| 2 | 8486C9DC | Ordinary offensive family: row 25 | PROVED |
| 3 | 8486C9DC | Ordinary offensive family: row 25 | PROVED |
| 4 | 8486CAC4 | Return null category | PROVED |
| 5 | 8486CAC4 | Return null category | PROVED |
| 6 | 8486CAC4 | Return null category | PROVED |
| 7 | 8486CAC4 | Return null category | PROVED |
| 8 | 8486C9BC | Kick family: UTF-16 name equals `Kickoff` => row 21; unequal => row 22 | PROVED |
| 9 | 8486CAC4 | Return family: null | PROVED |
| 10 | 8486C9B4 | Punt family: row 17 | PROVED |
| 11 | 8486CAC4 | Punt-return family: null | PROVED |
| 12 | 8486CA70 | Field-goal family: row 19 | PROVED |

**PROVED:** Family >12 returns null without indexing the table. C9C8 calls `84B438B0`, which returns **1 for equal strings, 0 for unequal**, not strcmp's conventional result. `cntlzw` and `addi ... 21` therefore mean Kickoff=21 and other family-8 names=22. The string is at `845EBB14`. This detail matters for Safety Kick as well as Onside Kickoff.

**PROVED:** With a null formation, `0x8486CA0C` is indexed by `[G+34]-1`:

| G+34 / index | BASE target | Decision | Grade |
|---|---|---|---|
| 1 / 0 | 8486CA1C | Row 21; kick/free-kick phase | PROVED |
| 2 / 1 | 8486CA24 | `848670C0` decides row 21 versus onside row 22; onside also stages D+3C play and a BC08 formation in H+680/+684 | PROVED |
| 3 / 2 | 8486CA60 | `84866C78` decides conventional try row 19 versus regular offensive row from 84867600 | PROVED |
| 4 / 3 | 8486CA80 | Scrimmage special/regular chooser 8486BD90 | PROVED |
| other | 8486CAC4 | Null | PROVED |

| Special leaf and decisive instructions | Inputs | Output and caller use | Grade |
|---|---|---|---|
| `8486B8E0`; call at BDD0, return row 19 at BDDC | Effective time, score, down, field position, cached random/time estimate and 84861288 kicker range | FG predicate gets first refusal | PROVED |
| `84866D28`; call at BDEC, row 17 at BDF8 | Down/distance, attacking field position, clock/score, urgency/late-state helpers | Punt predicate gets second refusal | PROVED |
| `84866B28`; BE08 then BE1C/BE30/BE3C | Period, score, effective clock, C+18 bits 1/2, own timeouts, attacking goal distance | Hail-Mary path stages formation D+58 and its first play; returns that formation's primary category row | PROVED |
| `84867150`; BE54 then BE68/BE74/BE9C | Score lead, period/clock, down, timeouts and clock-management predicates | Clock-management path stages D+38 play and D+50 formation, or resolves a formation if missing | PROVED |
| `848670C0`; CA24 | Trailing score, fourth-period test, clock versus time-needed estimate | Onside decision | PROVED |
| `84866C78`; CA64 and CFC8 | Period >=3 / late-state predicate; score differences including -10, -5, 1 and 5 | Two-point decision / fake allowance on try | PROVED |
| `8486BEF8..BF80` | Enough time relative to estimate, cached random > literal at 82003850, not try phase, fourth down, attacking goal distance | Additional punt/FG choice by kicker range; otherwise call 67600 | PROVED |

**PROVED:** These are predicates with several branches, not a table mapping a down to a special play. Their complete compared instruction spans are in the receipt (`situation` and `cpu_selection`); the table identifies the callable predicate boundaries and every kind of state used. This job does not replace them with a guessed high-level clock strategy. Hail-Mary and clock paths dereference cached formations before ordinary candidate enumeration; they are relevant to removal safety.

### Regular situation row

**PROVED:** `84867600` first checks the mode-specific override `84A3CEC8`. That override reads U mode 9, U+234, and an object under `85214608+118`; its supplied row is returned when the override applies. A try-phase branch can request row 19 using the cached random value. Otherwise the numerical path is:

1. Read effective down; the try phase substitutes down 4.
2. Read distance `d`. On down 2, distance in the 9-to-11-yard interval is treated as down 1.
3. Compute `x = d / max(4-down,1) * max(down/2,1)`.
4. Interpolate the four-point curve at `820C8884`: `(91.44,0), (301.752,4), (457.2,4), (1097.28,11)`.
5. An overtime/in-range branch subtracts `2*(1-goal_distance/kicker_range)`. Add uniform random jitter `2*u-1` and D+E4 urgency. In the late-state branch, select the offense's time-needed estimate when tied/trailing, the defense's when leading; when that estimate exceeds effective time, add another `2.5*urgency` at 848678D8.
6. Round using the signed half-unit path and clamp to 0..10.

**PROVED:** Thus a neutral 3rd-and-3 gives row 4, and neutral 3rd-and-8 or 3rd-and-15 gives row 10 with u=0.5. Different urgency, jitter or special-state predicates can change the request. There is no book-name input in this row calculation. It is not a request for category index 4 or category index 10.

### Team pass/run value and the other weights

| Address / instruction | Inputs | Output | Grade |
|---|---|---|---|
| ROST root table 4, team record +F8 | Relative pointer in a 384-byte team record | Points into root table 9: 42 records, stride 180. Every team pointer is aligned and in that table in the retail witness | PROVED |
| `8492F188..F21C`, specifically `lwz ...,0xF8(...)` at F1F8 | Native home/away team record, or custom object at M+24 | Installs D+0 tendency workspace. Custom data can use custom-object+28C8; retail buffers are 8519FB90 / 8519FC68 | PROVED |
| `8492A440`, A450/A458/A45C | Source tendency byte +5A, `s` | Two big-endian u16 counters: P+2=s, P+0=100-s, where P=[D+0] | PROVED |
| `8492A61C..A654` | Source +8E..98 and +99..A3 | Eleven u16 run row weights at P+9E, eleven pass row weights at P+B4 | PROVED |
| `8492A5CC..A618` | Source +84..8D | Formation-family preference fields within P+86..9C; implicit first entry plus five copied fields per side | PROVED |
| `84929AE4..84929B28`; `lhz`, `fdivs`, `bl 8486A1F8` | P+2/(P+0+P+2) | Situation-adjusted run probability at T+8 and T+C, T=`8519A718` | PROVED |
| `84929B4C..B90` | Uniform random draw and adjusted probability | Run/pass Bernoulli choice. Chosen run uses P+9E and family weights P+86; pass uses P+B4 and P+92. T+8 becomes 1 or 0 | PROVED |
| `84929CE4`, `84929D94..E44` | Requested row; 11 row weights, restricted to distance <=2; book categories and family weights | Optional category/formation cache at T+10/+14, valid bit 31 in T+4 | PROVED |
| `8492A2A8`, `8486A768..A778` | T+8 after preparation | H+67C used by the weighted selector | PROVED |
| `8486B328`, `8486B638`, `8486B690` | H+67C, or fixed 0.4 when fake allowance is set; individual play weights and pass/run sums | Separate normalization of pass and run candidates before the final cubed-weight draw | PROVED |

**PROVED:** All 42 retail source records have zeroes in the 22 optional row-weight bytes +8E..A3. Their +5A values are not all equal: the first is 42; the tested array includes values from 23 to 63. These are per-team tendency records, not per-SPLB profiles. Working data can differ from initial source data. T+10/+14 are written by the optional tendency routine; the examined CE88→C930→AEB0→BC08 path does not consume those cache getters. Its category calculation remains the weighted book enumeration in section 2.

**PROVED:** The native conversion test writes s=0, 50 and 100 into an in-memory copy of the actual source record and obtains `(P+0,P+2)=(100,0),(50,50),(0,100)`. Native tendency preparation at neutral 1st-and-10 observes probabilities 0, 0.5 and 1 at B28. With u=0.5, the final getter returns 0, 1 and 1; its optional category/formation valid bit stays clear because the source row arrays are zero.

**PROVED:** `8486A1F8` makes “controlled solely by each team's pass/run slider” too strong as a description of the actual choice. It adjusts the input for time versus estimated need, urgency, timeouts, down/distance, score and field position, and clamps to [0,1]. Its ordinary-distance correction uses distance divided by remaining downs, with a special third-down threshold. A 0.5 input becomes approximately **0.45, 0, 0** on the neutral 3rd-and-3/8/15 witnesses. In a late state it subtracts `0.8 * urgency`; a sub-120 clock branch additionally scales by timeouts/3. Other special predicates can force a run value. Play availability, formation restrictions, X ratings, previous-play suppression, skill weights, learned history and final cubing still intervene.

**HYPOTHESIS:** The source +5A percentage is the value Urianus means by his visible pass/run slider. Its native run-percentage behavior and storage path are proved; the exact UI slider widget and save-editing path were not executed here. Names such as “urgency” describe the observed use of D+E4, not an recovered retail symbol name.

## 2. Category choice

### Record model and namespaces

| Object / address | Instruction or access | Inputs / layout | Output | Grade |
|---|---|---|---|---|
| MASTER category +44, stride 16 | `lbz ...,4(category); clrlwi ...,26` | +0 name pointer; +4 low six bits situation row; +5..F eleven packed personnel role bytes | Category identity is its record index, distinct from row | PROVED |
| MASTER formation +244, stride 184 | `lwz ...,4(form); srawi ...,26` | +0 name; +4 family/style fields; +8 flags | Formation geometry/classification used with a separately selected category | PROVED |
| MASTER play +80C4, stride 100 | B3B4/B3D8 and membership helpers | +0 name; +4 high nibble play family; +8 flags; assignment/type data used by weighting leaves | Play candidate | PROVED |
| SPLB record B+70+i*B0, 176 records | Native reverse lookup `84A8A258` | 84 big-endian u16 memberships then two trailer words | Formation record lookup | PROVED |
| Membership u16 | `srwi ...,13` / `rlwinm ...,22,...` / low ten bits | X=bits15..13 rating, Y=bits12..10 audible slot, play ID=bits9..0, sentinel ID 3FF | Native membership/rating/tag lookups | PROVED |
| Trailer A at record+A8 | A258 callers and normalizer | bits31..24 formation ID; bits23..17 primary category ID; 3-bit ratings at shifts 14,11,8 | Primary category and three tendency ratings | PROVED |
| Trailer B at record+AC | `84A8A330`; normalizer CBB0 onward | Secondary/category membership bitmask | Category applicability for this formation | PROVED |
| SPLB caches | Native mask iterators; normalizer stores | +7D98 formation mask (24 bytes), +7DB0 play mask (84 bytes), +7E04 category mask (8 bytes), +7E0C MASTER pointer | Derived indexes, rebuilt from records | PROVED |

**PROVED:** Offensive category IDs / rows / TE counts are: Jacks 0/0/3; Jokers 1/2/2; Ace 2/3/2; Pro Set 3/4/1; Trio 4/5/2; Kings 5/6/1; Queens 6/7/0; Straight 7/8/1; Flush 8/9/0; 5 Wide 9/10/0; Load 26/0/2. Role is the low five bits of each packed role byte; role 8 is TE. Special category IDs also differ from their rows: Punt 15→17, Field Goal 17→19, Kickoff 19→21, Onside 20→22. There is no ordinary category on row 1.

| Retail offensive resource | Advertised category IDs before adding global content | Grade |
|---|---|---|
| O-ManBlock 130 | 0,1,3,6,26 | PROVED |
| O-TwoBack 259 | 0,1,3,6,26 | PROVED |
| O-SinglebackAce 369 | 0,1,2,8 | PROVED |
| O-Singleback3WR 767 | 2,5,8 | PROVED |
| O-WestCoast 891 | 0,1,3,6,26 | PROVED |
| O-ZoneBlock 943 | 0,2,3,5,8 | PROVED |
| O-Shotgun 1411 | 0,1,2,3,5,6,7,8,9 | PROVED |
| USER-o 1037 | 0,1,2,3,5,6,7,8 | PROVED |
| global-o 1439 | 1,7,15,17,19,20 | PROVED |

### The four attempts

| Address / instruction | Inputs | Outputs / next state | Grade |
|---|---|---|---|
| `8486CF60 li r25,-1`; CF78 increments | Attempt counter; initially null formation r30 and play r29 | Attempts 0,1,2,3 | PROVED |
| CF74 `mr r3,r30`; CF7C/CF80 clear H+680/+684; CF84 `bl C930` | Retained formation, current global offense/situation | Category r31; no attempt number is passed to C930 | PROVED |
| `8486CAB8 bl AEB0` | M, requested row, optional retained formation | Weighted category pointer or null | PROVED |
| `8486D038 bl BC08` | M, category, optional preselected play | Resolve formation only while r30 is null | PROVED |
| `8486D05C bl B2D0` | M, family wildcard 8, formation, category, fake allowance | Play or null | PROVED |
| D084 compare 3; D088 branch CF70 | Null play | Retry. A formation already chosen is retained | PROVED |
| D08C..D09C | M, family 0, null formation, subtype -1 | Last-resort fetch; category/formation are not reconstructed from the fetched play here | PROVED |

**PROVED:** The retry test clears only the real MASTER play-validity bits in mapped runtime data. It observes four C930 calls with attempt counters 0..3. The first formation argument is null; all later arguments are the same retained non-null formation. All weighted plays fail validity and the emergency fetch returns null. No increasing requested-row sequence appears. Once the formation exists, C930's ordinary-family dispatch requests wildcard row 25 on the next attempt, constrained by that formation's category membership.

### AEB0's category distribution

| Address / instruction | Inputs | Output / filter | Grade |
|---|---|---|---|
| AF18 `bl 84A89B40`, later `84A89C30` | B category mask, MASTER | Enumerate advertised category pointers | PROVED |
| AF64 `bl 84A8B660`, following `B7F8` | Category and live records | Find an associated formation with usable play content | PROVED |
| AFB8/AFCC or AFD4 onward | Formation family | Offensive path checks ordinary play enumeration; families 4..7 use defensive tagged-content helpers C2C0/C3D8 | PROVED |
| B00C onward | D+54/+5C/+64 special category caches; retained formation | Exclude/handle special categories; test explicit formation membership when supplied | PROVED |
| B124 and ordinary-row branch | Requested row and category+4 row | Rows 0..10 use row-distance curve; 11..16 use defensive curve; special rows use exact matching; 25 permits wildcard | PROVED |
| `84869318` | Every applicable formation's 69058 weight in category mode | Mean weight; an encountered nonpositive formation weight causes zero result | PROVED |
| B198 onward; `bl 84863388` with exponent 3 | Candidate pointers and weights | Cubed-weight category draw | PROVED |

**PROVED:** For ordinary requested rows 0..10, category rows through 10 participate. Absolute row distance is halved on downs <=2 while absolute urgency is below 0.5. The category distance curve at `820C88A8` is `(0,1),(1,1),(2,.85),(3,.5),(4,.05)`, clamped at its ends. Thus being more than three rows away is not an exclusion here. The weight is that curve multiplied by the formation-weight mean. The defensive curve at `820C88D4` is `(0,1),(1,.01),(2,0)` with its separate directional/range checks. Special requested rows match their special rows; row 25 is the ordinary-formation retry wildcard. Neither the optional per-team row arrays nor Y audible slots replace this calculation.

**PROVED:** Candidate arrays have 40 slots. When the counter reaches 40, the code replaces an RNG-selected slot from the last slot and returns the count to 39. This is the retail bounded overflow behavior, not a promise of an unbiased reservoir. The final helper mutates weights by exponentiation. Zero or one candidates return index zero; a near-zero total uses integer-RNG modulo count when count >=2.

### Urianus row 1, reproduced as a bounded experiment

> “Adding heavy run formations, like Jacks (2 RBs, 3 TEs) or Jokers (2 RBs, 2 TEs, 1 WR), to O-Singleback3WR ... doesn't trigger them in run situations, like on GL ... instead reverting to Ace forms as usual.”

**PROVED:** The test takes stock O-Singleback3WR (outer 767), adds formation 9/category 0 and formation 5/category 1 in its first two empty records, 27 and 28, using actual O-Shotgun memberships. It uses `MembershipChange` plus `TrailerReplace`, compiles, verifies, and executes `84A8C790(B,0,1)`. It does not forge a favorable runtime category mask after normalization.

| Witness | Native result | Grade |
|---|---|---|
| Added record trailers after normalization | Formation 9/category 0/word B=1; formation 5/category 1/word B=2 | PROVED |
| Stock versus added category mask | Stock `0x124`; added `0x127`, IDs 0,1,2,5,8 | PROVED |
| GL state: down1, distance1 yard, goal1 yard, neutral urgency, u=.5 | 67600 requests row 0 | PROVED |
| Added category weights at row0 | Jacks 1.0; Jokers 1.0; Ace 1.16285717; Kings .56428570; Flush .04826923 | PROVED |
| Category draw u=.01 | Jacks/category0 | PROVED |
| Category draw u=.5 | Jokers/category1 | PROVED |
| Full output call, run_share=0, u=.5 | `(category=1, formation=5, play=236)`; visits B2D0; does not visit 60730, AA80 audible lookup, or 699D8 emergency fetch | PROVED |
| TU 1.1 compiled/normalized heavy call | Category1, formation5, non-null play; third-down rows also agree | PROVED |

**PROVED:** Native O-Shotgun's Jacks/Jokers use A's rating fields `(2,4,4)`; the writer-created records here use its default `(2,2,2)`. This changes weights, not availability. At the tested neutral GL the native heavy category weight is .91 before row gain, versus 1.0 for the added default-rated record. Ace is eligible and can still win a weighted draw; seeing Ace is not evidence that Jacks or Jokers were never requested.

**PROVED:** In this reproduction, the normalizer does not drop word B, the category enumerator does not impose a book-name restriction, and the separate three-row ladder cannot be the cause because it never executes. **HYPOTHESIS:** Urianus' exact “never” result still needs a trace of the loaded SPLB identity, its post-normalization record trailers, M/D/G/H state and the category candidate vector. The three offered explanations are not an exhaustive set and none is proved for his game.

## 3. Formation, play and third-down personnel

### Formation selection and caches

| Address / instruction | Inputs | Output | Grade |
|---|---|---|---|
| `8486BC08` | Manager, category, optional play(s); category row/special names | Special formation shortcut or call to 693F8 | PROVED |
| `848693F8`; 6946C/694F4 `bl 84A89E08` | B's contiguous record prefix, not just a form mask | Two-pass formation candidate traversal | PROVED |
| `848694B0`, `848695C0` `lwz ...,0xA8(r3)` | Reverse-resolved formation record | Primary-category preference | PROVED |
| `848695A0 bl 84A8A330` | B, formation, requested category | Word-B applicability test | PROVED |
| `848695E4..F0` | MASTER formation+8 bit0; whether explicit play was supplied | Hidden/special records excluded during ordinary automatic formation choice | PROVED |
| `8486950C..530` | D+50/+58/+60 formation caches | Exclude cached special formations unless explicitly selecting their play | PROVED |
| `84869058` | Trailer ratings, down/distance interpolation, urgency, H+67C, formation family/style, field position, M+1C attribute object | Formation/category weight | PROVED |
| Formation roulette | Candidate weights; exponent 1 | Formation pointer | PROVED |

**PROVED:** The first pass asks whether an eligible formation has the requested category as its **primary** A category. If so, the second pass rejects secondary-only matches even though their B mask admits that category. Otherwise B membership permits a secondary-category pairing. Category selection and geometry selection therefore need to remain consistent. A category membership bit alone does not guarantee the same odds as a primary pairing.

**PROVED:** 69058 uses two related rating curves. Category mode, at `820C891C`, is `(-2,3),(-1,2),(0,1),(1,.5),(2,.1)`. Formation mode, at `820C88F0`, differs only at x=-2, whose value is .5. For neutral urgency it obtains t from `84868F58`: clamp the distance between a low and high threshold. On third down the interval is 2..7 yards; on fourth down 2..5; otherwise 0..20. The first half interpolates the shift14 and shift11 ratings; the second half interpolates shift11 and shift8. Neutral inputs subtract 2 before the rating curve. Urgency >.5 uses shift8 minus 1; urgency <-.5 uses shift14 minus 1.

**PROVED:** Further gates precede those ratings. Family 0 returns zero when H+67C >=.9. Style bits `formation+4 & 0x3000 == 0x2000` get a small direct weight .05 when attacking goal distance exceeds 90 yards. Urgency >.4 and that style can add an attribute-49 bonus through `84ADB2E0` when its returned value exceeds 2. These constants and branch instructions are included in the receipt. The field is an attribute object read, not a book-name test.

### Weighted play choice and audibles

| Address / instruction | Inputs | Output / effect | Grade |
|---|---|---|---|
| B36C `bl 84A8BA78`; B5DC `bl 84A8A0E0` | Book's global play cache and MASTER | Enumerate play pointers | PROVED |
| B3B4..B3CC | play+8 | Require bit19 (`0x80000`); reject bit10 (`0x400`) | PROVED |
| B3D0..B3E4 | play+4 high nibble, caller family filter | CE88 supplies wildcard 8; other callers may restrict family | PROVED |
| B3FC / B410 | Formation membership; `84865468(play,formation)` | Require membership and matching fake/special allowance | PROVED |
| B41C..B438 | Formation family, play family | Family-2 play restriction outside the matching special formation family | PROVED |
| B43C..B484 | Manager-control helper, phase 1/2, names `Kickoff Middle` / `Return Middle` | Special direct-return path | PROVED |
| B490..B5D0 | Ordinary offense candidate and explicit formation | Score variants with parameter 0 and 3; keep separate flip-state entries | PROVED |
| B4CC..B4E0 | D+24 previous play | Multiply repeated play weight by .05 | PROVED |
| B500 `bl 8486A860` | M, play, formation, category, variant, history | Base play weight | PROVED |
| B528..B558 | play+8 pass bit1/run bit3, H+67C | Exclude pass when run_share=1 and run when run_share=0; accumulate eligible pass/run sums | PROVED |
| B638/B690 and scalar remainder | Individual weights and those sums | Pass weights times `(1-run_share)/pass_sum`; run weights times `run_share/run_sum` | PROVED |
| B884 `bl 84863388`, r5=3 | Rebalanced weights | Cubed-weight draw, not a linear percentage draw | PROVED |
| B8A4..B8C0 | Selected variant, M+38 control flag, D+2C | Set/clear flip-related bits 0x1004 for automatic manager; return play | PROVED |
| `84A8B2B0`; B36C `srwi r3,r11,13` | Book, formation, play | X rating, default 6 if absent; independent of Y | PROVED |
| `84A8AA80`; AAB4 Y extract and AAB8 comparison | Book, formation, audible slot 0..3 | Tagged play pointer or null | PROVED |

**PROVED:** The X curve at `820C8990` is `(0,2),(1,1.4),(2,1),(3,.5),(4,.1)`, endpoint-clamped. Lower X means higher initial weight. The native test holds the play constant while varying all 25 combinations X=0..4 and Y=0..4; the rating getter always returns X. A separate native test resolves each actual Y slot through AA80. The full tested CPU GL call never visits AA80. Y is not the run/pass slider or the initial pick weight.

**PROVED:** In `8486A860`, play family 0/1 gets the corresponding team history block: H+0 or H+244, plus DC for the other family. It copies DC bytes. If the two initial float totals are zero, ordinary offense calls `84868C70` directly. Otherwise it normalizes the copied history with `848640C0`, derives candidate features with `848654D0`, combines 17 cells against H+494 and 35 cells against H+4D8, with totals H+48C/+490, and multiplies the resulting complement-weight sum by 68C70's weight at AC08. A third/fourth-down branch reshapes the 35-cell vector using down and distance. These are mutable play-history inputs, not SPLB Y tags.

**PROVED:** `84868C70` composes X-curve weight with distance/type suitability (`84A87B38`, then `8485EA20`), play+8 flag multipliers, attribute 39/195 reads from M+1C when bit9 applies, and player skill weights. A run candidate can multiply skill `(group1,index8)` from the involved player. A pass candidate can multiply `(1,7)` and the selected route player's `(1,6)`; assignment lookup is `84A877D8`, player lookup `8485EA20`, skill getter `84AA7410`. The short-type branch suppresses unsuitable distance ranges before these products. The provided empty-player graph exercises the null-player cases; it does not prove the meaning of every skill index.

**HYPOTHESIS:** Naming the variant “flipped” follows its D+2C writes and existing flip fields; this job did not render the resulting alignment. It also did not execute a live audible after a snap. The proved audible control surface is four tagged memberships in the chosen formation, and the normalizer's tag repair. Initial-call selection and subsequent audible selection must be tested separately in a follow-up.

### Last-resort fetch

**PROVED:** `848699D8(M,family,formation,subtype)` is a separate bounded fetch over book play availability and its classifier. It uses a 40-slot candidate buffer and integer-random choice. CE88's emergency call at D09C passes `(M,0,0,-1)` after four failed attempts. It is also called by the U-mode manual/subtype path before CF5C. The normal weighted GL and third-down witnesses do not execute it. Consequently, changing only this fetch is insufficient to change those CPU calls. A hook limited to pass subtypes 2/3/4 also does not match the emergency subtype -1 call.

### The seven-step ladder is a different consumer

| Address / instruction | Inputs | Output | Grade |
|---|---|---|---|
| `84860730..60764` | Manager argument, requested row, lineup options; home/away book getters `849FD6A8/B8` | Book for the lineup resolver | PROVED |
| 6076C `bl 84A8B438` | Requested row | Exact category lookup | PROVED |
| 60784..607DC / 607EC..60844 | Six signed offsets at `820B9080` | Try +1,-1,+2,-2,+3,-3, clamped to offense rows0..10 or defense11..16 | PROVED |
| 60848..60888 | Multiple categories sharing an exact row | Walk to the last same-row category | PROVED |
| 6088C..608AC | Selected category, possibly null | Pass it to the 11-player builder `84860020` | PROVED |

**PROVED:** The native witness exercises all 28 requested rows against O-ManBlock and matches the existing personnel resolver model. Rows 8,9,10 are served by Queens/category6 on row7. That explains the studio's conservative retirement refusal for a swap that leaves no category within the three-row reach. It does not explain the initial CPU category as a seven-step search: the traced initial call never reaches 60730. This consumer still matters when making category retirement safe.

### Urianus row 3: exact bounded third-down outputs

> “Same exact issue. And the patch doesn't work either afaict. ... TEs are still not on 3rd.”

**PROVED:** With period1, 900 clock, tied score, three timeouts, midfield goal distance, zero urgency, RNG fraction .5, integer1 and run_share=0, the full CPU selection produces these **category / formation / play IDs**:

| Book | 3rd-and-3, request row4 | 3rd-and-8, request row10 | 3rd-and-15, request row10 | Grade |
|---|---|---|---|---|
| O-ManBlock 130 | `1 / 27 / 42` Jokers, 2 TEs | `6 / 14 / 114` Queens, 0 TEs | `6 / 14 / 114` Queens, 0 TEs | PROVED |
| O-Singleback3WR 767 | `2 / 91 / 78` Ace, 2 TEs | `8 / 92 / 78` Flush, 0 TEs | `8 / 92 / 78` Flush, 0 TEs | PROVED |
| O-Shotgun 1411 | `3 / 119 / 114` Pro Set, 1 TE | `7 / 133 / 216` Straight, 1 TE | `7 / 133 / 216` Straight, 1 TE | PROVED |

**PROVED:** At row10, O-ManBlock's closest advertised ordinary category is Queens on row7; its weighted category draw and the separate ladder both serve Queens in these witnesses, by different algorithms. O-Singleback3WR serves Flush on row9. The selected MASTER category role bytes have no TE, so those calls do not request TE personnel. O-Shotgun demonstrates that third down itself does not prohibit a TE. Even the first two books request TEs in the 3rd-and-3 witness. A patch at emergency fetch cannot change the already successful B2D0 path.

**HYPOTHESIS:** These role requests explain the corresponding observed no-TE packages if his actual state/book matches the witness. They do not prove every third-down lineup he saw. Substitution, depth-chart eligibility, play rendering and whether his old patch was loaded remain outside this bounded result. The broad claim “no TEs on any third down” is not a property of these selector bytes.

## 4. Removal

| Address / instruction | Input condition | Result | Grade |
|---|---|---|---|
| `84A89E08/84A89EA8` first/next formation | Interior record has first membership sentinel | Contiguous enumeration stops there; later populated records can be hidden before normalization | PROVED |
| `84A8A258` reverse lookup | First O-Singleback3WR record (formation68) emptied | Returns null for removed68 and also later69 while the hole remains | PROVED |
| `84A8C5B0` calls A258; `84A8C5C8 lwz r11,0xA8(r3)` | Explicit request for removed formation, r3=0 after lookup | Unguarded read at address A8; harness raises unmapped-read failure at C5C8 | PROVED |
| `848694B0/848695C0`, `848691F4` | A reverse lookup unexpectedly returns null to a caller assuming a live record | Further unguarded trailer accesses; stale pointers must not reach these callers | PROVED |
| `84A8C790` entry and record cleanup | Real book, emptied first record, repair-tail flag1 | Cleans entries, repairs tags, compacts surviving formation records | PROVED |
| `84A8CAC0..CAC4`, following copy/update loop | Hole followed by live records | Moves surviving suffix records forward; removed68 stays absent and69 becomes first record | PROVED |
| `84A8CB6C`, `84A8CBB0..CCD4` | Surviving A primary and B memberships | Rebuild category/form/play masks | PROVED |
| `84A8CCF0` onward, conditional tail repair | Five-entry book tail arrays +7970/+7984, r5 flag | Repairs derived tail selections; does not recreate a removed main formation record in the witness | PROVED |

**PROVED:** After native normalization of the removal witness, formation69 resolves to `B+70`; formation68 remains absent. Emptying a record is not immediately equivalent to safe removal because it hides a suffix until compaction. Clearing only B+7E04's category mask is not retirement: the normalizer restores stock 3WR mask `0x124` from the still-live records. A retired category must be removed from every surviving A primary and B secondary membership, and the published book must have a contiguous record prefix.

**PROVED:** The native normalizer does not resurrect formation68 in this test. There are other book-copy/merge paths; the loaded-book installation has a `84A8D740` merge at `849D40E8`. A caller can reintroduce content independently of C790. An old manager special-play/formation cache can also bypass the ordinary live-record enumeration and reach a direct primary-category lookup.

> “The main limitation now, besides playcalling, is REMOVING formations because those PBs aren't blank obviously, so the CPU is going to use those stock ones no matter what we add on top.”

**PROVED answer to row 5:** Stock records left in a book remain eligible. They must actually be removed and the derived indexes rebuilt. Once removed and normalized here, the normalizer does not restore them. Native callers are not universally null-safe, so a safe feature must also validate selected/cached formations and repair lineup fallbacks. **HYPOTHESIS:** A stock formation reappearing in his game may come from an unchanged working/saved copy or later merge; this job does not prove which one.

## 5. USER and global books

| Resource | Outer index | Evidence | Grade |
|---|---:|---|---|
| USER-d | 293 | Decoded SPLB name and archive filename hash agree | PROVED |
| global-d | 656 | Decoded SPLB name and archive filename hash agree | PROVED |
| USER-o | 1037 | Decoded SPLB name and archive filename hash agree | PROVED |
| global-o | 1439 | Decoded SPLB name and archive filename hash agree | PROVED |

| Address / instruction | Inputs | Output / path | Grade |
|---|---|---|---|
| `849D6238/625C/6268` | Native team +E0 offense label / +E4 defense label | Label object | PROVED |
| `849D6280..6294`, `849D638C..63A0` | Label string | Special saved-working-buffer branches for UA and UB | PROVED |
| `849D6490 lwz r11,4(r30)`; 64B8 argument store; `849D64E4 bl 84B65B00` | Other label name | Ordinary name-based `-spb.iff` request formatting | PROVED |
| `849D4090/4118`, `849FD6C8/D8` | Loaded SPLB pointer | Native match book slots; MASTER pointer installed at book+7E0C | PROVED |
| `8486AED8 lwz r28,0x20(r27)` and full CE88 witness | M+20 = mapped USER-o or global-o | Same situation/category selector as stock CPU books | PROVED |

**PROVED:** USER-o has 20 populated records. It enters C930, AEB0, BC08 and B2D0 in the same GL harness and returns a category, formation and play. A separate bounded native label test enters 849D6270 with O-ManBlock, USER-o and global-o label objects; all three reach 849D6490 and the same `{0}-spb.iff` formatter inputs at 849D64B8. There is no comparison against `USER-o` that bypasses those constraints in these routines. UA/UB are separately named saved working buffers; assigning a USER-o resource label is not the same operation as selecting a UA/UB saved book slot.

**PROVED:** global-o has seven records: Hail Mary, Clock, Kickoff, Onside Kickoff, Punt, Field Goal and Safety Kick (formations151..157). MASTER flags on Hail Mary, Clock and Safety Kick have hidden bit0. As a directly assigned ordinary GL book in this state, global-o enters C930/AEB0/BC08, selects category1, finds no ordinary formation and finishes with null formation/play after emergency fetch. The normalizer does not change that result. It is not an unconstrained blank offensive book. Native loaded-book code merges global content into other working books; the standalone-global witness does not execute that whole load/merge lifecycle.

> “We might be able to go around those issues if we clone the O-User PB for everyone and edit it by team because I'm not sure it has any of those hard-coded limitations.”

**PROVED answer to row 4:** USER-o is a usable content donor in the bounded ordinary selector. Cloning its label does not select a different category algorithm. The four unnamed resources are identified above. **HYPOTHESIS:** A clone may improve actual calls because of its contents and ratings; it is not proved to remove situational constraints. A CPU assignment through the entire asynchronous resource loader and saved-book merge was not executed. The common filename branch and selection from the resolved resource have separate native witnesses; the intervening load/install chain has static evidence. Those boundaries must not be reported as an end-to-end in-game assignment witness.

## 6. Control surface for the follow-up

**HYPOTHESIS / proposed design:** Build a versioned per-team call profile plus a validated runtime book view. Use the smallest two policy interception points below for CPU choice and the separate ladder consumer. Treat book publication and cache invalidation as a required lifecycle operation. A table rewrite of C980 or CA0C alone cannot implement the feature: those are family/phase code switches, shared by all teams, and neither contains per-team category/formation/play choices. A pass-fetch-only hook misses successful ordinary calls.

| Proposed hook / resume address | Inputs / ABI contract | Desired output | Evidence grade |
|---|---|---|---|
| CPU entry `8486CE88` (TU `8486DB88`) | r3 manager, r4 optional output; preserve the retail ABI and execute/displace its original prologue exactly | Resolve team profile. No profile: original CE88 path. Profile: choose a complete validated category/formation/play/variant tuple | HYPOTHESIS design; entry/output contract PROVED |
| Retail tuple commit `8486D0A4` (TU `8486DDA4`) | With the original CE88 stack frame established: r26 manager, r23 output, r22 output-mode state, r31 category, r30 formation, r29 play | Reuse the retail output and manager stores; preserve its optional null-output postprocessing | HYPOTHESIS design; stores PROVED |
| Lineup category boundary `8486088C` (TU `8486152C`), or entry `84860730` (TU `848613D0`) | r26 manager, r27 requested row, r28 live book, r31 proposed category before builder | For profiled team, substitute the already chosen valid category or a prevalidated all-row fallback. Never pass a null category to the builder | HYPOTHESIS design; boundary PROVED |
| Book-publication boundary around `84A8C790` return and working-book install/merge | Book identity/generation and compiled profile | Build validated view after normalization/merges; invalidate old pointer caches before publication | HYPOTHESIS design; normalizer/merge behavior PROVED |

**HYPOTHESIS:** Two policy hooks suffice only if the follow-up owns book publication and can invalidate manager caches at a known point before they are used. If it edits live books or cannot own all load/merge paths, it also needs a lifecycle interception after the last normalization/merge, or a generation check before each profiled call. Do not claim that two instruction patches alone make every possible stale pointer safe. A null guard in C5B0 by itself also does not repair an incoherent tuple or an empty book.

### Profile record

**HYPOTHESIS / design:** Store identifiers, bounded lengths and weights, not serialized runtime pointers. Suggested fields:

| Record part | Required fields / invariant | Grade |
|---|---|---|
| Header | Magic, schema version, byte length, record counts, endianness, checksum, BASE/TU compatibility identity; reject truncated/overflowing records | HYPOTHESIS |
| Team key | Stable roster/team identity plus offense side; runtime binding to home/away manager at match load. Label/resource name hash alone is insufficient because teams can share a book | HYPOTHESIS |
| Book binding | Resolved SPLB name/hash, content-generation identifier, MASTER compatibility pin; never key a production profile by archive outer index | HYPOTHESIS |
| Situation bucket | Phase, effective down, distance interval, attacking field-position interval, period/half, clock interval, score-margin interval, timeouts, optional urgency/run-share range; explicit priority for overlapping predicates | HYPOTHESIS |
| Category policy | Ordered or weighted allowed category IDs; explicit primary/secondary pairing permission; forbidden categories; default fallback category | HYPOTHESIS |
| Formation policy | Allowed formation IDs/weights per category; forbid list; ensure a surviving populated record with compatible category and at least one eligible play | HYPOTHESIS |
| Play policy | Allowed play IDs/weights per pair, run/pass preference, fake/special permission, variant/flip choice; optional use of retail X/history weights | HYPOTHESIS |
| Audible policy | Up to four playable same-formation memberships; category compatibility; explicit absent-slot behavior; verify again after native tag repair | HYPOTHESIS |
| Coverage | Explicit fallback tuple for every reachable ordinary row 0..10; phase-specific safe defaults for kicks/tries; policy for incomplete book/profile and resource-load failure | HYPOTHESIS |

**HYPOTHESIS / design:** At load, normalize a private book copy and build a lookup from surviving formation ID to record and from category ID to compatible live formation/play pairs. Resolve numeric profile IDs through the active MASTER. Validate the exact flags and membership gates listed above. Publish book, profile view and generation atomically; clear/rebuild D+38/+3C/+40 special play pointers, D+50..64 special category/formation caches, D+68/+6C/+70 current tuple and any pending staging output that belongs to the previous generation. Do not blindly zero live state after a snap; choose a proved pre-call lifecycle boundary.

**HYPOTHESIS / design:** A profile bucket chooses a complete tuple, then validates it immediately before the retail tuple stores. If a requested category or formation has been retired, search the profile's finite compatible candidates, then its prevalidated fallback tuple. If that set is empty, reject publication and retain the previously valid book/profile generation. An entirely empty offensive book cannot satisfy an “always returns a play” contract. To allow a destructive content edit anyway, retain a separate known-good retail fallback book and switch the complete book binding with the fallback tuple; never return a play from a different book while keeping the edited book pointer. Teams without profiles execute unmodified retail selection.

**HYPOTHESIS / design:** The independent lineup boundary uses the selected category when it belongs to this generation, otherwise the per-row coverage entry. This removes the need to preserve artificial three-row stepping stones merely to keep 60730 alive. It also avoids changing the global six-offset ladder for other teams. The profile controls the selected personnel category as well as formation geometry; forcing only a play pointer would leave the no-TE category intact.

### Storage choice

**HYPOTHESIS / recommendation:** Prefer a new small versioned archive resource, loaded into owned writable runtime memory and resolved by name. The archive's name-hash directory and book-clone mechanisms show that extra resources are feasible, but this job has not proved a loader for a new profile resource type. The follow-up must provide and test that loader, ownership and lifetime. A code cave can hold the bounded dispatcher and, for an initial fixed prototype, a small immutable profile directory. No unused cave address or capacity is certified by this job. Do not reuse the existing beta-66 patch cave without its occupancy/compatibility audit.

**PROVED:** The existing team tendency workspace already has run/pass and eleven-row preference fields, but lacks the required explicit category/formation/play allowlists, complete fallback coverage, stable generation metadata and storage capacity contract. C790 owns the SPLB caches and tails; placing persistent policy only in a derived mask loses it. **HYPOTHESIS:** Keep policy outside those rebuilt fields and rebind it after normalizer/merge completion. Extending an existing tendency structure in place would need its allocation and save-format consumers proved first; it is not the smallest reliable implementation from this evidence.

### Bounded native proof plan

**HYPOTHESIS / required follow-up validation:**

1. Pin both images and displaced instructions separately. Disassemble the actual generated trampoline. Verify branch reach, scratch/cave ownership, stack, LR, CR, GPR and FPR preservation. No arithmetic “BASE plus one delta” relocator.
2. Run every existing native witness with no profile. Compare output bytes, manager stores, visited retail selector boundaries and RNG consumption, not just the chosen play ID.
3. Map a real compiled/normalized book and a profile forcing Jacks, Jokers, a TE passing package and a specified play. Run wrapper through tuple commit in both images, then the lineup boundary. Check category role requests as well as play membership and variant bits.
4. Sweep phase/down/distance/field/clock/score/period/timeout boundaries, RNG endpoints and both managers. Ensure bucket priority is deterministic and no-profile teams retain retail behavior.
5. Retire each category and remove first/middle/last formations. Normalize repeatedly, invalidate generations and execute both selector consumers. Guard unmapped pages and count instructions. Assert every emitted tuple is internally consistent and no dereference uses a removed record.
6. Test profiles with duplicate IDs, dead plays, no eligible pass/run candidate, bad flags, missing special formations, missing audible slots, corrupt counts/checksums and an entirely empty book. Prove bounded fallback or rejection of publication; no stale-record read and no zero-candidate modulo operation.
7. Exercise load/save, UA/UB working copies and the global merge around the same publication boundary. Reparse after every normalization/merge and compare the profile's resolved generation. Test BASE/TU differences below with a category whose secondary membership precedes its primary.
8. Only after these bounds pass, collect Noah's in-game witnesses for team assignment, goal-line heavy calls, 3rd-and-3/8/long TEs, live audibles, removals, and reload persistence. Native tuple proof alone does not prove those rendered outcomes.

## BASE versus TU 1.1

**PROVED:** `apf_playcall_b67_evidence.json` lists **every changed instruction word within each explicitly hashed span**, including changed branch operands, code-pointer table entries, addresses of data constants, insertions and changed register allocation. Equal instruction words are represented by the range hashes and mapping. It is not an executable-wide claim. Tests regenerate the whole receipt from both pinned images and compare it exactly.

| BASE routine / span | TU routine / mapping | Difference | Grade |
|---|---|---|---|
| 84815608 wrapper | 848162A8, +CA0 | Global-address/branch relocation | PROVED |
| 84860730 ladder; 84863388 roulette | 848613D0; 84864028, +CA0 | Relocated addresses; same inspected algorithm | PROVED |
| 84864AB8 formation→category helper | 84865758 | TU first calls C5B0 primary lookup, then `84A9CFA8(form,category,1)` compatibility check; if accepted returns primary before scanning B memberships | PROVED |
| 84866258..84867938 situation helpers, including 84867600 | +CD0; row helper848682D0 | Address/branch relocation | PROVED |
| 84867938 supplied-call commit | 84868608 | TU adds the same validated-primary preference at 848686A8..D4; book/formation register allocation changes and downstream code moves | PROVED |
| 84867BF8..8486D0F4 | +D00 | Core category/formation/play/fetch/retry algorithms retain their instruction forms; exact relocations listed in receipt | PROVED |
| 8486AEB0 / B2D0 / BC08 / BD90 / C930 / CE88 | 8486BBB0 / BFD0 / C908 / CA90 / D630 / DB88 | +D00 | PROVED |
| Tables 8486C980 / 8486CA0C | 8486D680 / 8486D70C | Every entry target moves +D00 | PROVED |
| 84928CF0..8492A6E0, 8492F188, label/install spans | +EC8 | Address/branch relocation in the compared spans | PROVED |
| 84A89B40..84A8D150, including normalizer84A8C790 | +FD0; normalizer84A8D760 | Same inspected record cleanup/rebuild algorithm, relocated callees/data | PROVED |
| MASTER validator / type and category compatibility helpers | +FD0 | Relocated pointers/callees | PROVED |
| Numeric curves 820C8884/88A8/88D4/88F0/891C/8990 | Each +20 | Byte-identical curve payloads | PROVED |
| Family0 run cutoff literal: BASE820B4544 | TU82017DB8, references at 84869E3C/E40 | Different literal-pool address, identical float .9; not a tuning change | PROVED |
| G, H, staging85158350, tendency8519A718, MASTER metadata globals | Generally +30 in these compared references | UI U and native book-slot base84F3F7D8 remain unchanged; string/constants also have +10/+20/+28 relocations, listed per instruction | PROVED |

**PROVED:** The semantic TU change is visible natively: with O-Singleback3WR formation72, `84864AB8` on BASE returns Ace/category2 (the earlier compatible membership), while `84865758` on TU returns its primary Kings/category5. The helper is adjacent to, but not the ordinary CE88→C930 category path. The supplied-call commit also gained that preference and returns category2 versus5 in its separate native witness. A follow-up that forces a formation through a different caller must handle this difference; merely moving BASE addresses misses it.

**HYPOTHESIS:** The unchanged core instruction forms, preserved numerical curves and agreeing bounded GL/third-down outputs support keeping one logical policy design for both images. They are not proof that the entire game or every upstream lifecycle is identical. The exact per-instruction receipt, rather than a global TU offset, is the reviewable version boundary.

# APF 2K8 true 0–99 player ratings

Product finding date: 2026-07-18  
Product status: **Exact on-disc base ratings are mapped; bounded writer exists**  
Writer status: **Token-preserving transport and edited-player load are runtime-positive; direct gameplay effect remains unproved**

## Product result

APF 2K8 already stores independent base ratings as one byte per attribute.
There is no need to invent a tier-to-number conversion or stretch a small
bucket scale into 0–99:

- 27 fields have exact executable UI labels, getters, setters, and record
  offsets.
- A 28th field has the same rating getter/setter and formula role, but its UI
  label is unresolved. The product names it **Unknown Rating 24**.
- Native setters clamp values to `0..100`.
- Populated stock records use `0..99`; no stock base-rating byte exceeds 99.
- Gameplay-style getters normalize the stored value by multiplying it by
  `0.01`; native 100 becomes `1.0`.

APF 2K8 Mod Studio therefore shows the exact integer already stored in each
player record. It never rescales, buckets, clips, or guesses these values.

## Current user experience

Rosters & Players now gives every player a searchable **Base Ratings** panel.
The panel shows:

- all 28 fields;
- each exact stored integer;
- the byte's player-record-relative coordinate;
- an exact 0..99 editor with per-field Apply/Revert and modified state; and
- the stock `0..99` / native `100` distinction.

The broader roster search also includes the rating labels and values. Filtered
roster-row JSON/CSV exports retain the complete base-rating metadata.

The sealed Alpha 14 release remains historical and Preview/read-only. The
current release exposes a bounded semantic rating writer compiled through
the repaired token-preserving H7A route. Projects store only player index,
rating ID, and the user-authored integer; Build composes rating and team-name
changes into one roster entry. A private Speed `40` → `99` candidate booted,
passed fresh-profile Team Create, and loaded and rendered the edited player
normally. The earlier guest-PC `0x84AB1D40` failure did not recur.

That result closes the common archive-transport blocker and proves player-record
load/selection. It does **not** yet prove the numeric gameplay effect: APF's
Star Card shows biography and abilities, not numeric base ratings. Product
status must distinguish runtime-load proof from a Speed-sensitive gameplay A/B.
See the new [player-rating runtime result](APF_PLAYER_RATINGS_TOKEN_PRESERVING_RUNTIME.md)
and the [historical generic-transport negative](APF_ROSTER_IDENTITY_RUNTIME_NEGATIVE.md).

## Exact record map

The decoded on-disc player table contains 2,254 records at stride `0x14C`.
The rating neighborhood is `+0xBA..+0xD9`.

| UI order | Attribute | Relative byte | Formula modifier index | Label status |
|---:|---|---:|---:|---|
| 1 | Speed | `+0xBA` | 0 | XEX UI named |
| 2 | Agility | `+0xBB` | 1 | XEX UI named |
| 3 | Strength | `+0xC1` | 2 | XEX UI named |
| 4 | Jumping | `+0xC2` | 3 | XEX UI named |
| 5 | Pass Arm Strength | `+0xBC` | 6 | XEX UI named |
| 6 | Stamina | `+0xBE` | 9 | XEX UI named |
| 7 | Aggressiveness | `+0xD8` | 27 | XEX UI named |
| 8 | Consistency | `+0xD7` | 22 | XEX UI named |
| 9 | Kick Power | `+0xBF` | 7 | XEX UI named |
| 10 | Kicking Style | `+0xD1` | 26 | XEX UI named |
| 11 | Durability | `+0xC0` | 11 | XEX UI named |
| 12 | Coverage | `+0xC3` | 20 | XEX UI named |
| 13 | Run Route | `+0xC4` | 14 | XEX UI named |
| 14 | Tackle | `+0xC6` | 17 | XEX UI named |
| 15 | Break Tackle | `+0xC7` | 12 | XEX UI named |
| 16 | Pass Accuracy | `+0xC8` | 5 | XEX UI named |
| 17 | Pass Read Coverage | `+0xC9` | 13 | XEX UI named |
| 18 | Catch | `+0xCA` | 4 | XEX UI named |
| 19 | Run Blocking | `+0xCB` | 15 | XEX UI named |
| 20 | Pass Blocking | `+0xCC` | 16 | XEX UI named |
| 21 | Secure Ball | `+0xCD` | 10 | XEX UI named |
| 22 | Pass Rush | `+0xCE` | 18 | XEX UI named |
| 23 | Run Coverage | `+0xCF` | 19 | XEX UI named |
| 24 | Kick Accuracy | `+0xD0` | 8 | XEX UI named |
| 25 | Leadership | `+0xD3` | 23 | XEX UI named |
| 26 | Unknown Rating 24 | `+0xD4` | 24 | Neutral/unresolved |
| 27 | Composure | `+0xD5` | 21 | XEX UI named |
| 28 | Scramble | `+0xD6` | 25 | XEX UI named |

Four neighboring bytes are deliberately excluded:

| Relative byte | Status |
|---:|---|
| `+0xBD` | Unknown; no rating label/consumer assignment |
| `+0xC5` | Unknown; no rating label/consumer assignment |
| `+0xD2` | Unknown; no rating label/consumer assignment |
| `+0xD9` | Height in inches, proved by the feet/inches formatter |

A generic clamped byte accessor is not enough to call an unknown byte a
rating. The excluded fields remain excluded until a specific consumer proves
their meaning.

## Executable evidence

The 27 named rows come from the XEX player-edit descriptor table at virtual
addresses `0x820E4D84..0x820E5744`, stride `0x60`. Each descriptor binds a UI
label to a rating getter and raw setter.

The corresponding getter groups are preserved in the local function corpus:

- Speed and Agility:
  `research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_15616_15871.c:8056-8118`.
- Remaining named ratings and hidden `+0xD4`:
  `research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_15872_16127.c:6-836`.
- Normalized gameplay-style getter family:
  `research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_06400_06655.c:888-1746`.

The generated recompilation makes the input contract explicit. For example,
the Speed setter clamps below zero to zero, above 100 to 100, and stores at
`+0xBA`:

- `build-static-recomp-apf/ppc/ppc_recomp.50.cpp:2305-2348`.

Agility has the same contract at `+0xBB`:

- `build-static-recomp-apf/ppc/ppc_recomp.50.cpp:2357-2400`.

The hidden rating at `+0xD4` also uses that contract:

- `build-static-recomp-apf/ppc/ppc_recomp.51.cpp:1032-1073`.

Height is separate. Its formatter divides `+0xD9` by 12 and displays the
quotient and remainder as feet and inches:

- `research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_15104_15359.c:1932-1960`.

## Stock-data observations

Across the supplied supported USA disc:

- records `0..1436` have a populated `+0xBA..+0xD9` block;
- records `1437..2253` have a zero block;
- there are 548 distinct complete neighborhood blocks;
- all bytes in the complete neighborhood are at most 99; and
- every proved rating has an observed value inside `0..99`.

These are aggregate observations only. The public schema contains no player
values, source spans, compressed data, preimages, or rollback bytes.

## Native 100 and the 0–99 product policy

The game accepts 100 even though the stock roster does not use it. The product
must preserve that distinction:

1. The default modder-facing scale is 0–99.
2. Values are displayed exactly as stored.
3. The product writer accepts new values `0..99`; native 100 is a display and
   revert compatibility case, not an authoring preset.
4. A source value of 100 must never be silently shown or saved as 99.
5. Values must never be linearly mapped from `0..255` or normalized against
   the minimum/maximum found in one roster.

The underlying storage is already the desired ratings system. “True 0–99” is
an editor exposure problem, not a conversion problem.

## Systems that remain separate

### Overall

Overall is derived, not stored. The engine selects a position-specific formula
using player position byte `+0x34`, multiplies its result by 100, and rounds it:

- `research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_15616_15871.c:731-760`.

The product must not invent or write an Overall byte. An engine-matching,
read-only Overall can be added after the complete position formula tables are
emitted and tested.

### Special abilities

Abilities are packed bits around `+0x18..+0x2C`; they are not rating bytes.
Representative direct bit accessors are preserved at:

- `build-static-recomp-apf/ppc/ppc_recomp.49.cpp:3679-3706`;
- `build-static-recomp-apf/ppc/ppc_recomp.50.cpp:2032-2059`.

Ability presence or count must not be converted into rating points.

### Gold, Silver, and Bronze tier

The game visibly enforces a first-run team composition of two Gold, three
Silver, and six Bronze players, but the exact tier field and consumer are not
mapped. Tier must not be inferred from ratings, abilities, art IDs, or unknown
tables. The supporting Coach's Desk experiment remains private research
evidence and is not distributed with the retail-free application.

### Effective runtime modifiers

Rating getters can apply a per-attribute multiplier when high bits of
`player +0x20` are set. The multiplier is selected through
`Function_84A06648`:

- `research/functions/apf2k8/pseudo_c/apf2k8_pseudoc_13312_13567.c:2615-2645`.

Its fatigue, injury, boost, or tier relationship remains unresolved. Mod Studio
therefore calls the on-disc bytes **Base Ratings**, not guaranteed live
effective values.

### Global sliders

Human/CPU gameplay sliders use a separate `0.0..1.0` settings system. They are
not player ratings and must remain in Sliders & Gameplay.

## Disc roster versus created-team saves

This map applies to the decoded on-disc ROST player structure. It does not
claim that persistent `.ROS`/profile players have identical offsets.

The disc contains 40 team records. The first 32 each own a fixed array of 42
player pointers; eight USER rows are empty. That separate capacity fact means:

- exposing base ratings does not create 53-player team records;
- it does not remove Gold/Silver/Bronze selection restrictions;
- it does not map created-team save integrity or signatures; and
- disc offsets must never be applied speculatively to a user profile.

The shipped parser that enforces the underlying roster layout is
[tools/apf_roster.py](../../tools/apf_roster.py). The 32-team and 53-player
boundary is documented separately in
[APF 32-team/53-player feasibility](APF_32_TEAM_53_ROSTER_FEASIBILITY.md).

## Retail-free implementation boundary

The shipped dictionary is
`mod_editor/data/apf2k8_player_ratings.v1.json`. It contains only:

- generic field names;
- record-relative integer coordinates;
- scale contracts;
- evidence classifications; and
- product/runtime findings.

It contains no game bytes and no player values. Projects store only a semantic
player identity, semantic rating ID, and user-authored integer. They never
store retail preimages, original values, or copied records.

Alpha 18 adds a private bulk-authoring layer without widening that public-data
boundary. A source-bound v2 CSV locally carries all 2,254 × 28 current values;
preview compares source, active project, and desired sheet values before one
atomic batch Apply. The CSV is never copied into `.apf2k8mod`. Only the authored
semantic deltas survive project save/share, and one Undo restores the complete
pre-import edit set.

## Route from runtime-load proof to gameplay proof

Completed:

1. Map the exact stored fields without rescaling them.
2. Diagnose the historical rebuilt-ROST crash at `0x84AB1D40`.
3. Replace generic full-stream recompression with token-preserving H7A repair.
4. Implement fixed one-byte edits addressed by semantic player/rating IDs.
5. Require the decoded diff to contain only selected rating bytes.
6. Preserve source ISO/folder immutability and publish builds atomically.
7. Boot a Speed `40` → `99` candidate and load/select/render its player record.
8. Export, preview, import, conflict-check, undo, and project-save a complete
   63,112-cell ratings sheet against the supported retail source without
   changing its `0A` hash.

Still required for the strongest capability claim:

1. Run a controlled stock-versus-patched Speed or Catch gameplay A/B.
2. Measure an effect rather than inferring it from a successful player-card
   render.
3. Spot-check `0`, `50`, `99`, and native `100` if a numeric consumer screen is
   recovered.
4. Decode ability bits and star tier as separate later capabilities.
5. Map profile/save representation from legal one-variable before/after pairs;
   never reuse the disc layout by assumption.

The honest conclusion is now stronger: arbitrary independent per-attribute
0–99 authoring is mapped, bounded, and survives the game's repaired roster
transport and player-load path. The remaining uncertainty is whether each
edited number produces its expected on-field magnitude—not whether APF needs a
new ratings conversion. Star tiers, created-team persistence, 53-player
capacity, and dynamic rating modifiers remain separate problems.

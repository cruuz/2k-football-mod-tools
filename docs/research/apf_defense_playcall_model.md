# APF defensive play calling, beta 67 P2

PROVED means pinned executable/resource bytes inspected here, or the bounded BASE instructions actually executed by `tools/apf_defense_native_probe.py`. HYPOTHESIS marks an interpretation or a path not executed. Every in-game result is **UNWITNESSED**. A function-shape comparison is not TU execution or proof of equivalent callees/data.

PROVED inputs: BASE flat SHA-256 `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`; TU 1.1 reconstructed flat SHA-256 `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457`; MASTER SHA-256 `2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891`. These are flat memory images, VA minus `0x82000000`, not ordinary PE raw-section offsets. No game payload accompanies this report. Names, counts, hashes and execution results are in [the receipt](apf_defense_playcall_receipt.json).

## Defensive model

| Grade | BASE address | TU address | Operation and evidence boundary |
|---|---|---|---|
| PROVED bytes and bounded BASE prefix | `8486D0F8` | `8486DDF8` | Defensive driver. Ordinary branch starts `D354`; category, formation, then two defensive play components. Native run stops at `D38C`, before scoring. |
| PROVED bytes and bounded ordinary branch | `8486CAD0` | `8486D7D0` | Reads the selected offensive category's personnel row; calls the defensive request mapper and category lottery. Cached special-call branches also exist. |
| PROVED bytes; rows 0..4 bounded | `84869B60` | `8486A860` | Offense row plus field position and special-state helpers produce requested defensive row. No ordinary arm returns row 12. |
| PROVED bytes | `848696E8` | `8486A3E8` | Special predicate, offensive detail `+E4`, manager state and clock influence rows 14/15 versus 16. |
| PROVED bytes and bounded | `8486AEB0` | `8486BBB0` | Advertised categories, component supply, one-sided personnel fit and cubed distance weights. This is not P1's offensive bounded row ladder. |
| PROVED bytes and bounded | `8486BC08`, `848693F8` | `8486C908`, `8486A0F8` | Formation selection: record/category fit, two component lists and weighted draw. |
| PROVED bytes and bounded formation path | `84869058` | `84869D58` | Formation weight from trailer A's three small ratings and offense detail `+E4`; power one in formation lottery. |
| PROVED bytes; native candidate helpers only | `8486C448` | `8486D148` | First defensive play component, runtime validity, formation membership, existence of a complementary component; `A860` score; power-three lottery. |
| PROVED bytes; native candidate helpers only | `8486C6C8` | `8486D3C8` | Second compatible component, score and power-three lottery; complete first components can return directly. |
| PROVED bytes, not executed end to end | `8486A860`, `84865AE0`, `84863F58` | `8486B560` for A860 | Situation/profile and lineup feature evaluation, multiplied by two entry weights and flag factors. No measured game-world play probabilities are claimed. |
| PROVED bytes and bounded | `84863388` | `84864028` | Shared weighted lottery, explicit exponent, zero-sum fallback and tie RNG consumption. |
| PROVED bytes and 120 native/reference steps | `84B3E858`, `84B3E8B8` | Not separately executed | Shared 55-word additive RNG; integer and float variants. |
| PROVED bytes and bounded record/cache region | `84A8C790` | `84A8D760` | Normaliser. Executed `C7C0..CCF4`; optional tail repair and comparison suffix not executed. |
| PROVED bytes | `84A8D740` | `84A8E710` | Merge can introduce records from another book, then normalise. |
| PROVED bytes | `849D6208` | `849D70D0` | Team label/override to resource filename or working USER buffer. |

PROVED correction to the shared context: the ordinary defensive driver calls `CAD0` at `D358`, `BC08` at `D384`, then dispatches formation families 4..7 to `C448` at `D41C` and `C6C8` at `D454`. It writes category at output `+0`, formation at `+4`, first play at `+0C`, second play at `+10` (`D490..D4A0`). Its other-family arm calls `B2D0` at `D474`. The offensive four-attempt loop around `8486CF5C` is not this defensive route.

HYPOTHESIS: calling the two outputs “front/rush” and “coverage” is useful football shorthand, but the proved distinction here is their assignment-slot compatibility. Follow-up code must preserve both outputs rather than assume one PLAY pointer is the entire defensive call.

## Where P1 and P2 meet

PROVED: `8486CAD0` obtains the chosen offensive call through the manager at `851A2780`. `8485D550` tests the offense detail flags `+2C` bit 3; the existing-call branch uses offense detail `+4`. Otherwise `84815298` can return staging `85158350+10` when its state permits. Cached Hail Mary formation/category fields are checked at `CC5C..CC9C`.

PROVED: at `CCA4` the code loads the selected offense CATEGORY pointer, at `CCA8` it reads byte `+4`, and at `CCAC` masks to the low six bits. It passes that **personnel row**, not the offensive SPLB ordinal or book name, to `84869B60` at `CCB0`; `CCC0` calls `AEB0` with the defense context. This is P2's handoff to sibling **P1, the offensive selector job**. P1 owns how that offense category was requested/chosen and the 11-player package built from it; this document does not duplicate that policy. P1's final artifact was not available in this worktree, so no unverified P1 result is cited.

## Requested row, fit and randomness

PROVED bytes: `84869B60` forms a signed field distance using game state `manager+6C -> +18`, offense team `manager+0 -> +8 -> +0C -> float+4`, and constants 4572 and 457.200012. The sign is selected from the team's direction value. The main row dispatch is:

| Grade | Selected offense row | Requested defense row |
|---|---|---|
| PROVED bytes; ordinary row 3 executed | 0..4 | 11 if distance <457.2; otherwise 13 |
| PROVED bytes | 5..7 | 13 if close; otherwise 14 or 16 according to `848696E8` |
| PROVED bytes | 8..10 | 14 if close; otherwise 15 or 16 according to `848696E8` |
| PROVED bytes | 17 | 18 when state `+4 == 4`; otherwise 13 |
| PROVED bytes | 19 | 20 when within the threshold returned by `84861288`; otherwise 13 |
| PROVED bytes | 21 / 22 | 23 / 24 |
| PROVED bytes | Other rows | 25 |

HYPOTHESIS: those field constants represent centimetres, so 457.2 is five yards; the execution fixture specifies the actual float coordinates, not a witnessed scoreboard distance. Semantic names for every state/clock flag are not established by this job.

PROVED bytes: `848696E8` first checks `84866B28`; otherwise it reads offense detail float `+E4`, manager `+44`, game-clock object `manager+0C -> float+10`, and manager carry float `+30` for states 1/3. Its comparisons use 1.0. The special predicate also examines score/clock/field state. This prevents a correct model from calling formation choice a personnel-only uniform draw. The requested-row mapping above is exact at the pointer/condition level; a complete catalogue of the producers of those state fields is HYPOTHESIS.

PROVED: `AEB0` enumerates category bits through `84A89B40`/`84A89C30`; `84A8B660`/`84A8B7F8` require formation supply. Defensive families 4..7 must have both `84A8C2C0` and `84A8C3D8` component supply. A supplied formation also must pass `84A8A330` category membership. For candidate rows 11..16, `B1C4` rejects `candidate_row < requested_row` with weight zero. Remaining raw weights interpolate `820C88D4`: points `(0,1), (1,.01), (2,0)` at the row difference. `B198..B1A4` invokes `84863388` with exponent **3**. Zero-weight candidates are retained, which matters for fallback/boundaries.

PROVED: category 11 (4-3, also Bear/4-4 records) and category 23 (3-4) both carry personnel row **13**. Category 27 (5-2) carries row **12**. In an ordinary request for row 13, 5-2 therefore receives **zero weight**. Category bit 27 is present and is enumerated. The added formation passes the supply path. The result is a fit/weight exclusion, not a missing bit, a formation blacklist, or the offensive ladder bound.

PROVED: `693F8` scans the contiguous record prefix, checks word B membership via `A330`, optionally primary category, and both component lists. It calls `69058`, then `696C0` calls the lottery with exponent **1**. Trailer A contains the three values `(A>>14)&7`, `(A>>11)&7`, `(A>>8)&7`. Detail `+E4 < -.5` selects the first; `> .5` selects the last; otherwise `84868F58` interpolates the three. After subtracting one, formation curve `820C88F0` has points `(-2,.5),(-1,2),(0,1),(1,.5),(2,.1)`. The alternate category-scoring curve at `820C891C` changes the first y value to 3. Family-specific offensive bonuses also exist in this helper. Thus shared fit does not imply every edited formation has the same weight.

PROVED: `84863388` raises every supplied float to its caller's exponent in place. It sums them, tracks a maximal candidate with RNG tie breaking (including the first candidate compared with itself), and normally selects by `U * sum(weights)` and cumulative subtraction. `U` is produced by `84B3E8B8`. If the sum is below the next representable value above zero, it uses `84B3E858 % candidate_count`; count below two returns index zero. A zero float draw can select a leading zero-weight candidate because the first comparison is `>=`. Category and formation candidate buffers use a 40-slot threshold and retain 39 entries with a random overwrite when saturated. These details invalidate unconditional “never” and simple seed-to-call assumptions.

PROVED: the selected RNG state is **`8505CD00`**, two 32-bit indices and 55 64-bit words at `+8`. Each draw adds the two indexed words modulo 2^64, stores the sum at the first index and decrements both indices, wrapping to 54. The float variant constructs `1.mantissa` from the low 23 sum bits and subtracts one, producing `[0,1)` on a 2^-23 grid. The reference test executes 120 alternating integer/float draws, verifies all 448 state bytes after every step and crosses both index wraps.

PROVED bytes, not executed: initialization `84B3E9B8` starts with a 32-bit LCG (`1664525*x + 1013904223`), mixes a 32-word scratch table into 55 words, ensures an odd word, installs indices 54/23 and advances the generator. Startup `846918C0..D4` obtains the low 32 bits from `84B20C00` (`mftb r3,0x10C`) and seeds this state. `84690950` also exposes an explicit reseed; `8470C490..C4C8` seeds it from the caller argument. Callers `8471201C` and `847139E4` load that argument from object `8501FAD0+804`. HYPOTHESIS: the complete network/replay ownership of that stored seed is not traced. The harness deliberately uses an explicitly documented synthetic 55-word state, not a claim to reproduce a retail match's initial seed or frequency.

## Urianus row 2: reproduced and qualified

> “It selects between them randomly whenever they both 'fit' the personnel matchup, as it does with 4-3 and Bear. Except 5-2, which is never selected if added.”

PROVED bounded BASE: compile X-43Cover2 (outer 134) with a fifth record through the production `TrailerReplace`/`MembershipChange` writer and reparse verifier. Use the 51 memberships of X-34Base record 0 in both experiments to isolate the formation/category change: first formation 147/category 23 (3-4), then formation 150/category 27 (5-2). This is a controlled reconstruction of his described edit, not his unavailable exact edited file. The 5-2 record deliberately uses the same donor components; it is not a claimed authored stock 5-2 playbook.

PROVED bounded BASE: execute the real defensive driver `8486D0F8..D38C`, including its offensive-package read, row mapper, category lottery and formation lottery. Offense category 3, ordinary formation pointer, detail `+E4=1`, direction `+4=1`, position 0, no special UI/cache state. Seeds 1..128 produce:

| Grade | Added formation | Raw category weights in category order 10,11,12,13,added | Native result |
|---|---|---|---|
| PROVED | 3-4 | 0,1,0.00999999046,0,1; cubed | 65 × category 11/form 141; 63 × category 23/form 147 |
| PROVED | 5-2 | 0,1,0.00999999046,0,0; cubed | 128 × category 11/form 141 |

PROVED: the retained small Nickel weight means these are finite deterministic outcomes, not a proof of exactly 50/50 over all games. At requested row 11, 5-2 is one row above the request, so its raw weight is about .01, cubed to about 10^-6 against Goal Line's 1. A constructed representable high RNG draw with position 4500 selects **category 27/form 150** in the same driver. There is no absolute code prohibition on 5-2. HYPOTHESIS: its zero ordinary-matchup weight and very small near-goal weight explain Urianus never observing it; his actual seed/state/edited record were not available.

## How the defensive plays are chosen

PROVED bytes: `C448` enumerates first components through `84A8D440`/`84A8D4D0` using book play/category membership. It requires runtime PLAY flags `+8 & 0x80000`, formation membership `84A8C0B8`, and a compatible partner through `848646B0`. It scores each through `A860` and invokes the shared lottery with power three at `C6A0`.

PROVED bytes: `C6C8` can return a complete first component directly; otherwise `84A8C4E0`/`84A8A488` enumerate compatible second components of the same play family. Their assignment descriptor bit `0x800` must jointly cover the 11 slots. `84A878B8` counts the first nine marked slots, returning zero when either last slot is marked; `84A87900` provides the complementary count rule. Candidates must retain runtime `0x80000` and same-formation membership. `A860` scores the pair; the second lottery uses power three at `C90C`.

PROVED bounded BASE: serialized MASTER pointers need relocation and runtime validity initialization. The harness rebases relative names and assignment chains, executes native opcode-table registration `84A877C8` and play validator `84A88E90`, then native candidate enumerators/membership/partner tests. X-43Cover2 category 11/form 141 has 12 accepted first components, each with 16 accepted partners, **192 compatible pairs**. Their IDs are in the receipt. This prevents a false empty result from raw serialized flags, which do not yet carry `0x80000`.

PROVED bytes: `A860` selects one of two context profiles rooted at `851595D0` (side stride `0x244`, profile `+DC`, copy length `DC`). The first two profile coefficients select a fallback when both zero. Otherwise `848640C0` normalizes the profile; `84865AE0` builds lineup/player features, including calls into lineup builder `847B2DA0`. In the defense arm `AC1C..AE9C`, field-distance bins use increments of 457.2 capped at five; a 17-float dot product uses local profile `+6C` and global features `+570`, scaled by global `+568`; the subsequent distance-dependent product uses profile `+B0` and features `+5B4`, scaled by `+56C`. The total is multiplied by `84863F58`. These are exact data dependencies, not named editable coaching sliders.

PROVED bytes: `84863F58` reads the two SPLB entry values through `84A8B2B0` (entry bits 13..15, fallback 6), maps each through curve `820C8990` with points `(0,2),(1,1.4),(2,1),(3,.5),(4,.1)`, then multiplies them and conditional PLAY flag/situation factors. It checks second-play bit 14, either-play bit 4, offense cached special formation plus bit `0x100`, or manager `+34==3`, global feature `+678` and bit `0x80`. This demonstrates that final play randomness is weighted by more than membership counts.

HYPOTHESIS/UNWITNESSED boundary: the full `84865AE0` game-world lineup evaluator and the final `C448`/`C6C8` lotteries were not executed end to end. Which football concepts each profile coefficient represents, the per-team producer of that profile, and probabilities in a live situation remain follow-up work. No replacement defensive scoring policy ships here.

## Removal on offense and defense

> “The main limitation now, besides playcalling, is REMOVING formations because those PBs aren't blank obviously, so the CPU is going to use those stock ones no matter what we add on top.”

PROVED: a SPLB record starts at `0x70 + record_index*0xB0`, with 84 big-endian 16-bit entries followed by trailer words A and B. Entry low ten bits `0x3FF` mean empty. Formation reverse lookup `84A8A258` stops at the **first** empty record (`A2B8..A2C4`), hiding populated records after a hole until normalisation. A record with a still-present stock play is not a removal. Duplicate records for the same formation also keep it reachable.

PROVED: `84A8C790` clears cached category words at `+7E04`, six formation words at `+7D98`, and 21 play words at `+7DB0`. `C888..CA4C` compacts entry holes and repairs tags. `CA50..CCF0` compacts whole record holes and rebuilds caches from surviving records. Formation comes from trailer A's high byte; primary category is `(A>>17)&127` at `CB6C..CB9C`; the loop at `CBA4..CCD4` additionally folds **all 32 bits of word B**. Merely clearing a category mask cannot retire a category while a surviving primary/B advertises it. The code has no stock-book lookup in this cache reconstruction.

PROVED bounded BASE: emptying the first X-43Cover2 record's 84 entries while leaving trailers removes form 141, but normalising that hole changes the last surviving Goal Line word B from `00000400` to `000013FF`; category mask becomes `000037FF`. USER-o's first-record hole similarly produces mask `000013FF`. The problematic compaction cleanup is `CAF4..CB1C`: halfword addresses use the source pointer and loop to `0x160`, reaching trailer space; `CB14` masks with `E3FF`, `CB18` ORs `1000`. This is a native record-compaction side effect, not evidence of a stock formation being recreated. The bounded regression preserves this observation.

PROVED bounded BASE data edit that avoids that path:

1. Delete **every whole 0xB0-byte record** for the retired formation.
2. Move surviving whole records, including all eight trailer bytes, into a contiguous prefix in original order.
3. Fill each unused record with 84 entries `13FF`, followed by neutral trailer `00009200 00000000`.
4. Rebuild `+7D98` formation bits, `+7DB0` play bits and `+7E04` category words solely from the surviving records' primary category and word B. For category retirement, remove that bit from **all** surviving B words and repoint/retire every surviving primary using it; do not clear only the cache.
5. Normalise and verify again. The five-item special tail and any independently loaded source/save must be audited separately.

PROVED bounded BASE: this edit retires form 141 from X-43Cover2 with remaining forms `[142,143,146]`, category mask `00003400`, and unchanged surviving trailers. Sixteen defensive driver seeds never reach form 141 afterward. Applied to USER-o, it retires form 0, preserves the 19 other records and mask `000001EF`. Both reverse lookups return null for the retired form; normalising twice yields identical bytes. The research helper `compact_remove` is not installed as a Studio removal feature. P1 owns the offense selector's behavior when the remaining personnel supply cannot serve its request ladder.

PROVED bytes: the context constructor `84864CA8` derives cached special formation/category fields `+50/+54`, `+58/+5C`, `+60/+64` from the supplied book. It does not carry a separate stock formation catalogue. Normaliser optional five-item tail repair is controlled by its fifth argument; `84A8D740` calls it at `D870..D87C` with arguments four/five zero. The bounded normaliser test omits that optional tail repair and final comparison/report suffix.

PROVED bytes: runtime merge `84A8D740` can add a record from another source. Combined-book loader calls at `849D40E8/4170` merge defensive into offensive working books; `849D41B4/41C8/420C/4220` merge global supplements into the working books. An edited disc template can also be bypassed by a saved USER bank. Therefore a single resource edit cannot prevent a different source from supplying the same formation. HYPOTHESIS: a warm stale context cache can retain references until reinitialization; no hot-reload or every-mode lifetime test was run. The exact data-only result proved here is for the edited, compacted current book and cold ordinary selector state, not every global/save/UI path.

## The four formerly unnamed SPLBs

PROVED from resource filename IDs, UTF-16BE body names at `+30..+68`, and roster labels:

| Grade | Pinned outer | Body name / filename | Filename ID | Populated records / memberships |
|---|---|---|---|---|
| PROVED | 293 | `USER-d` / `USER-d-spb.iff` | `2F551CF1` | 6 / 180 |
| PROVED | 656 | `global-d` / `global-d-spb.iff` | `6C4EBF6F` | 5 / 24 |
| PROVED | 1037 | `USER-o` / `USER-o-spb.iff` | `AD00822C` | 20 / 258 |
| PROVED | 1439 | `global-o` / `global-o-spb.iff` | `EE1B21B2` | 7 / 23 |

PROVED: all four bodies are 32,288 bytes. The resource identity is the uppercase filename CRC32, **not the outer number**; inserting a clone shifts later ordinals. Full body hashes are in the receipt. The supplied roster label table maps IDs 25..31 and 64..67 to `USER-o`, and 56..63 plus 68 to `USER-d`. No roster label has a global type. The prior writer already knew these names; the product change removes restrictions and stale ordinal assumptions elsewhere.

PROVED bytes: `849D6208(side, offense)` gets the team through `84682730`/`84682798`, reads offense label at team `+E0` or defense at `+E4`, then observes side overrides through `849FD608/618/628/638` (`84F3F7D8+1C/+20/+24/+28`). The normal path uses label type `+4` in the `{0}-spb.iff` formatter at `849D64E4`. A CPU team assigned a USER label therefore requests `USER-o-spb.iff` or `USER-d-spb.iff` by the same name path, **unless an override is active**. There is no USER-specific exemption in the defensive matchup/weight code.

PROVED bytes: USER A/B override branches instead obtain working buffers 0/1 through `849FCF60`, inspect buffer `+7E10`, bind the active buffer and return an empty filename. Human control alone is not the filename selector. User-team type `+D0==2` can obtain the user-bank ordinal through `84AE8F9C..8FC8` and `8474BA88`. Bank initialization `84AE8948` loads `user-o`/`user-d` via strings `84626010`/`846260A4`, copies offense and merges defense into eight slots of stride `0x7E20` at `8523F6F0+10`. Save/load paths `84751000 -> 84AE8BF8` and `847510A4 -> 84AE8C40` preserve those banks. This is why cloning a disc USER template is not proof of changing a previously saved user book.

PROVED bytes: global-o at string `845F20C4` is requested at `849D80B0`; global-d at `845F20E8` at `849D8160`. Their explicit loader requests and subsequent merge calls make them supplements rather than roster label choices. Cloning their contents into a team-specific book is now an authored content operation; it does not alter those global loader filenames.

PROVED: USER-d's populated records include 4-3 (141), Bear (144) and 4-4 (145) under category 11, plus Nickel, Dime and Goal Line. Its matching path is the same family 4..7 path as the four CPU defensive books. HYPOTHESIS: the complete UI/save lifecycle that activates USER A/B, and the ownership of every live book/profile, still needs an in-game witness. There is no proved “unrestricted USER defensive selector.”

## TU comparison and next profile job

PROVED: the 16 function comparisons in the receipt were rerun on both pinned images. Fourteen are normalized-equal, merge is byte-identical, and loader is normalized-different. The loader's one residual instruction difference is BASE `849D6498: addi r11,r11,0x1758` versus TU `849D7360: addi r11,r11,0x1780`; the surrounding branch builds the filename-format argument. HYPOTHESIS: relocated pointers and referenced data must still be validated before treating these as behaviorally interchangeable. No TU native execution was run.

HYPOTHESIS, proposed follow-up contract: use P1's actual selected offense category/formation, then identify the defensive team and its active **resolved book** after overrides, saved-bank choice and global merges. Intercept `CAD0`/`AEB0` request/weight policy only for teams with an explicit profile. Keep native behavior for teams without one, preserve component supply and special calls, and carry both output play pointers from the defensive driver. A profile needs separate category weights, formation weights, and paired-play weights; those are three different lotteries with exponents 3/1/3+3. Do not call the existing last-resort fetch patch a replacement for any of them.

HYPOTHESIS, remaining research: prove the producer and per-team lifetime of `851595D0`'s two profiles, name their feature coefficients, bind save/USER A/B state to the roster identity, run full paired-play scoring against a captured world fixture, and test cache reconstruction after retirement of special/global records. These are explicit limitations rather than claimed completed play-calling control.

## Reproduction

PROVED commands run here, with the read-only flat images produced by the prior verified extraction:

```sh
PYTHONPATH=. python3 tools/apf_defense_native_probe.py \
  --image /tmp/astra-coverage-17votk5s/base_reextracted.pe \
  --index 'extracted/All-Pro Football 2K8 (USA)/0A' \
  --report /tmp/b67-p2-native.json
QT_QPA_PLATFORM=offscreen PYTHONPATH=. \
APF_RETAIL_PE=/tmp/astra-coverage-17votk5s/base_reextracted.pe \
APF_RETAIL_TU_PE=/tmp/astra-coverage-17votk5s/verified_tu.pe \
python3 tests/mod_editor/test_apf_defense_research_native.py
PYTHONPATH=. python3 tests/mod_editor/test_apf_defense_research_identity.py
```

PROVED execution bounds: four million instructions per native call; full image hash checked before mapping; PPC64 integer instructions/ABI spills unsupported by Unicorn PPC32 are adapted individually, never replaced with selection results. The receipt lists adapted instruction sites. Synthetic memory only supplies explicit book/MASTER/context inputs. The native test can decode a local `default.xex` in memory when `APF_RETAIL_PE` is unset. Both research files raise precise SkipTest without retail; TU comparison skips without `APF_RETAIL_TU_PE`.

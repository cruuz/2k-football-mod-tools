# PROVED OFFLINE: native PLAY scoring contract, phase 5

PROVED OFFLINE: This contract refers to the USA executable SHA-256 `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`. Addresses are Xbox virtual addresses. Operand numbers below are zero based. The executable is supplied by the user, not redistributed. [Scorer](../mod_editor/core/nfl2k5_play_scoring.py), [code and table pins](../mod_editor/core/nfl2k5_play_scoring_pins.json), [direct call references](receipts/phase5/scoring-xrefs.json).

## PROVED OFFLINE: the exact crash

PROVED OFFLINE: Dallas PLAY 153, `17 Inside Zone`, slot 10, contains `0x16 Take Handoff` with operand 2 equal to **10**. The valid handoff-hole domain is **0 through 8**, not the rush-lane domain. Its packed location is bits 28 through 31 of the node's operand word. `0x2815F0` takes `ECX=PLAY*`, `EDX=transform flags`. With game-plan bit 0 enabled it calls `0x281300`, then reads `float[0xC5D4C0 + 4*classification]` at `0x281607`.

PROVED OFFLINE: `0x281300` obtains the primary carrier with `0x1A8DE0`, finds the first `0x16` in that assignment with `0x1A8C00`, evaluates operand 2 through `0x2B6FA0` and the real opcode callback `0x2B6620`, converts to integer, then reads `u32[0x51C980 + 4*hole]` at `0x281343`. There is no bounds check. The nine entries are `[2,4,3,3,2,2,1,1,0]`. The result must be 0 through 4 for the five run weights.

PROVED OFFLINE: Transform bit 1 mirrors a nonzero hole with `9-hole`; hole 0 remains 0. Thus authored 10 becomes **-1** for argument 3. The preceding word at `0x51C97C` is `0x3991A2B4`. Its use as the next index gives `(0xC5D4C0 + 4*0x3991A2B4) mod 2^32 = 0xE70C5F90`, exactly the saved fault. Values 9 through 15 are invalid even if a particular orientation happens to read mapped memory. [Original investigation](HEAP_REPORT.md), [saved-state replay](receipts/phase5/fixed-snapshot.json).

PROVED OFFLINE: The phase 1 generator used `lane_for_x(2 yards)`, which correctly returns **rush lane 10**, then passed that number into `carrier_chain` as a handoff hole. The library described that argument as a lane; the codec accepted any four-bit integer. Phases 2 through 4 reused that generator and compiler. Native load validation and menu replay accepted the record because they did not exercise the enabled game-plan scorer. This was an authoring-domain error, not increased book heap use.

PROVED OFFLINE: Native `0x2B6F50` also uses the hole as an unchecked index into the nine-entry position table at `0x521030`: `[17,15,13,11,9,7,5,3,1]`. Those indices select centimetres from `0x520FE8`. The hole coordinates are `[0,533.4,381,228.6,76.2,-76.2,-228.6,-381,-533.4]`. The corrected Dallas hole is **3**, mirrored to **6**, preserving the intended right-side inside aim. Hole 3 is the nearest native aim to two yards. The following run-path geometry is unchanged.

## PROVED OFFLINE: arguments and consumers

PROVED OFFLINE: The value 3 is a two-bit transform, not third down. The only direct caller of `0x2815F0` is `0x207D90`; the only direct caller of `0x281620` is `0x207E09`. Both forward the shared scorer's final stack argument. The direct shared-scorer call sites and argument construction are recorded in [callsite-arguments.txt](receipts/phase5/callsite-arguments.txt).

| PROVED OFFLINE consumer | Inputs read from PLAY or related state | Valid domain and reason |
| --- | --- | --- |
| `0x208820` shared scorer | PLAY `+4` bits 6..8, two PLAY pointers, formation, category, transform | Kind 0 selects offense, kind 1 defense; other three-bit values return the neutral score. Pointers must belong to the loaded book. Transform 0..3. |
| `0x2096A0` offensive selector | Callable bit 31, exclusion bit `0x400000`, kind bits 6..8, compatibility, formation | Family filter 0..7 or wildcard 8. Native loop scores transform 0 and 3 (`EBX += 3` at `0x2098C9`). Candidate arrays hold 30; overflow is handled by the native bounded replacement path. |
| `0x20A7F0`, `0x20AA40` defense front and coverage | PLAY flags, compatible formation, current play-call state | State bits `0x1000` and `4` become Boolean bits 0 and 1. All combinations yield 0..3, including independent mirror combinations. |
| UI consumers at `0x17E21A`, `0x17F5FD` | Saved play/formation/category references | Pass transform 0; lookup helpers resolve actual book references. |
| `0x281300` run classification | Primary carrier slot, assignment chain, first `0x16` operand 2 | Carrier slot 0..10; chain belongs to node pool; handoff hole 0..8. Missing handoff returns classification 2. |
| `0x2815F0` run weight | Run classification and game-plan enable bit 0 | Five weights, index 0..4. Other game-plan bits cannot change this index. |
| `0x281620` pass weight | Primary assignment, last `0x12` operand 0, trajectory, actor role | Route type 0..11 indexes the twelve entries at `0x51C9A4`. No route uses sentinel -1 without reading that table. |
| `0x280DF0` pass-zone classifier | Native trajectory endpoint, ball position, attack direction | Lateral index clamped to 0..4; depth index clamped to 0..3 before the weight reads at `0x281712`, `0x281721`. Field position changes weights within these bounds. |
| `0x280EF0` receiver-role classifier | Actor signed byte `+0x2C` | Roles 8,9,10,11 plus the default branch exhaust the four resulting indices 0..3. Game-plan bit 3 selects the special multiplier for index 3. |
| `0x281580` defensive game-plan filter | PLAY kind, flags `0x10000`, `0x100000`; global bits 0..2 | Eight effective global states. Reads no assignment operands and uses no authored table index. |
| `0x203F20` defensive flag weight | Two PLAY flags, bits 9..11, flags `0x4000000`, `0x10000` | Three-bit ratings 0..7 are passed to the bounded interpolation routine `0x1B0AE0` and curve `0x50AFE0`; they are not unchecked five-entry indices. |
| `0x204F10`, `0x205660` matchup readers | All eleven assignment descriptors and native trajectories; roster ratings | Fixed eleven-slot loops and bounded profile accumulation. The gate executes both native readers, with supplied roster/rating inputs. |

PROVED OFFLINE: Native PLAY records are 96 bytes. `+0` is the name pointer, `+4` flags; slots 0..10 have descriptor at `+8+8*slot` and chain pointer at `+12+8*slot`. The low descriptor nibble is chain length, 0..15; its role bits identify carrier/receiver and defensive responsibilities. The structural compiler verifies pool boundaries, pointer relocation, formation/menu links, opcode validity and native callable validation before the scoring check. A valid encoded nibble alone is insufficient.

PROVED OFFLINE: Native trajectory `0x191550` starts at the selected formation slot and visits assignment nodes, requesting at most eight output points in these scorers. `0x190FD0` dispatches opcodes 4..27 through a range-checked jump table after real operand decoding. Relevant operand classes follow; coordinates and times are decoded finite scalars, while table/slot operands require the narrower semantic domains. [Trajectory dispatch](receipts/phase5/trajectory-dispatch.txt), [trajectory reader](receipts/phase5/trajectory-reader.txt), [codec domains and native validator port](../mod_editor/core/nfl2k5_play_codec.py).

| PROVED OFFLINE operand class | Consumers / opcodes | Native domain |
| --- | --- | --- |
| Handoff hole | `0x16`, `0x17`, operand 2 | Integer 0..8; both scoring and trajectory tables have nine entries. |
| Rush lane | `0x0B`, `0x0C`, `0x1B`, `0x1C` lane fields | 0..16, or sentinel 17. `0x2B6F40` reads the eighteen-entry position table. Mirror maps ordinary lanes to `16-lane`, leaves 17 unchanged. |
| Route segment kind | `0x12`, operand 0 | 0..11. Both route geometry dispatch and pass-scoring classification use this enum. |
| Target/follow slot | `0x02`, `0x13`, `0x14`; recursive follow geometry in `0x15`/`0x18` | 0..10 when the selected mode uses a slot; chains and recursion must satisfy native validator constraints. |
| Lateral coordinate | Coordinate operands in movement, coverage, block, route and follow nodes | Eight-bit biased feet, -128..127 feet before mirror; finite arithmetic, not a raw table index. |
| Depth/distance coordinate | Same coordinate-bearing classes | Eight-bit biased feet, -64..191 feet; some mode callbacks reverse the sign. |
| Delay | Start, pass, lane, block and handoff nodes | Six-bit tenths, 0..6.3 seconds. Scoring geometry does not index a table with delay. |
| Other mode/flag operands | Branches in the trajectory dispatcher and native validator | Use the opcode-specific enum in `OPERAND_SCHEMAS` and `validate_play`; a packed field's bit width does not certify a meaningful football mode. |

## PROVED OFFLINE: situational selection and proof boundary

PROVED OFFLINE: `0x20B820` calls native `0x20B400` policy, `0x2093F0` category selection, `0x20A240` / `0x2081B0` formation selection, then the front/coverage selectors and shared scorer. Category IDs and formation types are filtered before scoring; the selectors do not reinterpret distance, down, score margin or clock as a handoff/route index. [Orchestration](receipts/phase5/selector-orchestration.txt), [situational policy](receipts/phase5/situational-policy.txt), [clock and zone helpers](receipts/phase5/situation-contract.txt).

PROVED OFFLINE: Offensive policy reads down from `[0xE602EC]+4`, field position at `+0x18`, line to gain at `+0x28`, attack direction through team `+8,+0xC,+4`, score difference through the two teams' `+8` records, quarter at `0xE602C4`, clock through `[0xE6028C]+0x10`, and play-call phase at `0xE602B4`. The `0x20B400` phase switch accepts 1..4. Quarter/clock, field distance and score influence category probabilities and scalar weights. They add no further possible transform values to the four values above. Saved-formation fields must contain initialized book pointers for late-clock reuse.

PROVED OFFLINE: The game-plan states are equivalence classes of the consumed bits: run scoring uses bit 0; pass scoring uses bit 0 and, only when enabled, bit 3. Therefore 0/1/9 exhaust the distinct paths; 8 follows the same disabled path as 0. Defense consumes only bits 0..2, exhausted by 0..7. Higher bits do not add scorer paths.

DESIGN: The release gate exhausts every PLAY record, every compatible formation, all four transforms, run and pass game-plan equivalence states 0/1/9, eight defense game-plan states, and five actor-role representatives. It invokes the shared scorer with zero and nonzero profile fixtures to enter both native matchup branches. Guards stop before unchecked table loads, including loads into mapped neighboring memory. Invalid accesses, instruction-budget exhaustion, stack imbalance, unsupported pinned code, missing Unicorn or a missing executable refuse compilation. Cache keys contain exact executable and resource bytes; returned receipts are copies.

DESIGN: Global floating-point ratings, clocks and field coordinates have enormous domains. They are not exhaustively enumerated as whole-game Cartesian states. The per-play indexed domains above are exhaustive; the outer-selector experiment is additional factored state coverage, recorded explicitly by `scoring_selectors.py`. Roster resolution and rating helpers are environmental inputs, not native gameplay proof. No selector, scoring function, compatibility function, trajectory function or opcode decoder is stubbed. The optional world experiment additionally supplies a kicker's range scalar. This distinction prevents a clean offline sweep from becoming an unsupported claim of universal game stability.

DESIGN: Both publication gates are mandatory: `apply_pack_to_resource` certifies the compiled resource; `mod_build._check_playbook_scoring` certifies every final disc PLAY after all PLAY writers. Missing tools/code cannot silently skip the gate. The final-draft proof also reopens the completed disc and runs the expanded scorer again using its actual patched executable. The shipped encoder rejects out-of-domain handoff values before nibble packing, and the editor labels the field as a handoff hole.

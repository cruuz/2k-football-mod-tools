# APF coverage research and TU 1.1 — 2026-09-09

Implemented a pinned, idempotent MASTER PLAY coverage-geometry writer, reconstructed the Xbox title update, and produced an address-level comparison of the base and updated images. **All gameplay outcomes are UNWITNESSED.** No emulator, GUI, audio device, or game-data network fetch was used. Retail inputs were read only; extracted executable material stayed in external temporary storage.

The strongest findings are:

- Zone landmarks and two directional extents come from opcode `0x0D` PLAY nodes. The writer exposes exactly those four fields.
- A zone helper clamps lateral coordinates to approximately ±71 feet. A separate deep-zone rule responds to the absence of an outside receiver. These are concrete candidates to investigate against the complaints, not a reproduced cause or a proved repair.
- Coverage rating participates through a callback and a cached effective rating read by threat-delay code. This does not establish that a better rating produces a sensible corner-route decision.
- The mapped zone selector, geometry routines, and sampled zone constants retain their instruction shapes/values in TU 1.1. A shared ratings contest changes substantially; a composure/pass-rush proximity calculation also changes. The available evidence does **not** support publishing the community's broad coverage/pursuit claim as confirmed patch notes.

## Evidence boundaries and inputs

`A_PROVEN` means a checked binary field, instruction, control-flow edge, typed value, or successful offline parser/writer observation. `B_INFERENCE` means a reasoned semantic interpretation or cross-image function alignment. `UNKNOWN` means the predicate, domain, or behavior is not settled. A_PROVEN static evidence is never a runtime witness. Normalized signatures deliberately erase address operands and external branch destinations; equality alone is not semantic equivalence.

| Input/output | Bytes | SHA-256 |
|---|---:|---|
| Retail `default.xex` | 38,408,192 | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |
| Base flat PE | 54,001,664 | `cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf` |
| LIVE title-update package | 839,680 | `5f71cdf4ec679f8e33fd95e02ff2b67981fbf918d4d03a2099576734c5cfb42b` |
| Extracted `default.xexp` | 776,192 | `14e272063536656d2aae9b4743fdcebb927566722dc1e2f34fe75029e1e8ada6` |
| Reconstructed TU flat PE | 54,001,664 | `65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457` |
| MASTER PLAY body | 182,096 | `2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891` |

Paths are the supplied paths in ASTRA_CONTEXT.md. The archive index for MASTER is **`0A`**, with `0B` alongside it. I independently re-extracted `default.xex` using the existing offline `xex_extract_pe` utility: 642 compressed blocks, 1,648 chunks, 54,001,664 bytes, exactly the supplied base PE hash. The reconstructed execution ID has title `0x54540807`, media `0x7744078F`, version `0x00000102`; the base version is `0x00000002`. The delta descriptor names the same source and target versions. “1.1” is the community label used in the brief.

All executable offsets below use **file offset = VA − `0x82000000`**. These are decompressed memory images. The PE `.text`/`.data` raw-file offsets must not be used. The discardable relocation section extends beyond the extracted memory payload; the reader allows that unused tail but bounds-checks the mapped sections it reads.

The complaint attribution remains the supplied September 5 transcript: PGaither84's 13:13 Tampa-2 example and 23:18–23:20 outside-the-numbers/leverage account; 7ET's 13:25 match-coverage interpretation and 13:35 corner/Smash request; Urianus's 21:52 update claim. The transcript's 22:16 discussion describes unpublished fixes as deductions. These are community observations, not official patch documentation or runtime tests performed here.

## Zone data and its consumers

The base codec table is `0x820FBFC8`, 29 records of four function pointers, 16 bytes each. The separate flag table is `0x820FBE68`, 29 u32 values. TU moves both by `+0x20`. The `0x0D` row names decoder `0x84A92148`, encoder `0x84A922B0`, and two other callbacks; it is a codec/drawing/validation table, **not** a claim that all four entries dispatch gameplay. `0x0E` is the man-assignment decoder; `0x1B`/`0x1C` are APF defensive setup opcodes. All rows and the 17 lane values are in [data_tables.json](docs/research/apf_coverage/data_tables.json).

`0x84A87958` selects a codec row from the node's leading opcode byte. `0x84A94098` calls the decoder with the second BE word as payload. `0x84A940F0` reads decoded operands, stride 12, value at +4. `0x8482DFA8` transfers the active node's seven zone operands into assignment state. The high nibble of each assignment descriptor is its node count: `0x84A87980` explicitly shifts by 28 and walks eight-byte nodes. This replaces an inferred sentinel or next-pointer boundary.

For the second BE word `w` of opcode `0x0D`:

| Operand | Exact field | Decoded meaning / boundary |
|---|---|---|
| X | `(w >> 24) - 128` | Landmark X in feet; multiply by 12 and binary32 2.54, truncate toward zero to integral cm, optionally mirror |
| Y | `((w >> 16) & 255) - 64` | Landmark depth in feet; multiply by 12 and binary32 2.54 |
| A | `w & 15` | Lateral extent, converted from yards to cm in the zone-record constructor |
| B | `(w >> 4) & 15` | Depth extent, converted from yards to cm in the constructor |
| Side/mode | `(w >> 8) & 15` | Numeric mode; mirror swaps its low-two-bit values 1 and 2 |
| F | `(w >> 12) & 1` | Preserved selector; full decision semantics UNKNOWN |
| G | `(w >> 13) & 7` | Copied into zone state +`0xF8`; full decision semantics UNKNOWN |

The writer preserves the complete first word and payload bits 8–15. It does not apply the NFL codec wholesale to APF. There are 368 zone nodes in the 4,948-node MASTER pool. [zone_nodes.json](docs/research/apf_coverage/zone_nodes.json) contains their derived fields and every `(play, slot, chain step)` user.

**Units and formation evidence.** Formation records begin at body `0x244`, stride `0xB8`; slot alignment starts at +`0x1E`, stride 14. `0x847D0278` reads signed halfwords at `formation + 0x20 + 14*slot + 2*column` and +`0x26`, converts directly to floats, and stores X/Z; its mirror path negates X. I Pro (formation 0) has guard X ±152, tackle X ±304, TE X −457, wide X ±1371, and the deepest back Z −731 in its first column. Those are truncated 5/10/15/45-foot and 24-foot alignments in centimeters. The zone decoder's explicit `12 × 2.54` conversion and these independently stored formation alignments establish cm, rather than assuming NFL units. Formation samples 0, 141 (4-3), and 147 (3-4) are in [stock_assignments.json](docs/research/apf_coverage/stock_assignments.json).

`0x847F0A08` creates 11 records of 32 bytes at base global `0x85135728` (TU `0x85135758`). Records hold actor +0, another target pointer +4, landmark X/Z +8/+12, extents +16/+20, a score +24, and mode/index bytes +28/+29. It fetches opcode-D operands, transforms the landmark relative to the current field origin, and converts A/B through `3 × 12 × 2.54`. The mode lookup at `0x820B7C68` is identity 0–15; mode bit 8 selects several deep-zone branches. A nondeep absolute-depth clamp uses `4937.759765625` cm (54 yards) at `0x820B7DB8`; this is **not** the sideline clamp.

Stock examples, before mirroring or live adjustment:

| Play / slot | Zone node | X, depth (feet) | Lateral, depth extents (yards) | Mode |
|---|---:|---|---|---:|
| Cover 3 / 7 | 3119 | 0, 54 | 5, 5 | 8 |
| Cover 3 / 9 and 10 | 3123 / 3121 | +45 / −45, 54 | 5, 5 | 9 / 10 |
| 4 Cloud / 9 | 3223 | 36, −3 | 6, 5 | 7 |
| Cover 4 / 7 and 8 | 3241 / 3243 | +15 / −15, 54 | 5, 5 | 8 |
| Combo Inside Zone / 7 and 8 | 3401 / 3403 | +15 / −15, 54 | 5, 5 | 11 |
| Combo Strong Zone / 10 | 3423 | −42, 0 | 8, 5 | 6 |

“Flat,” “hook,” “curl/flat,” “quarter,” and “cloud” are not proved global table names. The stock play, slot, geometry and mode are exact; their football-role labels are B_INFERENCE unless the actual assignment is specified. Notably ordinary Cover 4 reuses the same outside deep nodes as Cover 3. Combo Inside uses different mode values and additional man nodes.

## Boundary and threat decisions

**Lateral clamp, A_PROVEN.** `0x847EA7F8` (TU `0x847EB498`) copies a zone landmark, reads an external object's float values at +0 and +`0x10` via `[0x850CA6C8]+0x14`, adds them, and applies a lateral shift with explicit input/output clamps. Calling that object ball position/velocity is B_INFERENCE; the pointer ownership was not fully traced.

The constants are reciprocal `0.00046209015999920666` at `0x820B7CD8`, positive/negative binary32 `2164.079833984375` cm at `0x820B7CDC`/`0x820B7CE0`, and matching positive/negative binary64 values at `0x820B7CE8`/`0x820B7CF0`. TU adds `0x20` to those addresses and preserves every value. The input clamp uses compares/selects at `0x847EA86C..0x847EA880`; the output clamp is at `0x847EA8EC..0x847EA8F8`, stored at `0x847EA8FC`. The magnitude is approximately 71 feet, nine feet inside a field half-width of 80 feet. There is no proved comparison to painted numbers here.

The lateral-shift amplitude also depends on whether the source displacement and landmark are on the same side of the current origin and on parameter `r5`. Changing only one clamp constant would leave inconsistent float/double/reciprocal limits. This pass exposes no universal “sideline fix” control.

**Directional radius, A_PROVEN.** `0x847ECD48` calculates the direction from supplied center to candidate, then approximately `sqrt((sin(theta)*(A_cm+padding))² + (cos(theta)*(B_cm+padding))²)`. `0x84B0C970` gives quarter-turn for positive X and zero for positive Z, establishing A's lateral orientation and B's depth orientation. `0x847ECE78` scales an overlong displacement by radius/length and restores the center. This is a directional radius, not an asserted mathematical ellipse intersection or a hard receiver-carry distance. Padding is zero while the timer at game context +`0x1C`→+`0x10` is at most 5, otherwise approximately 914.4 cm (10 yards). The same gate is visible at `0x847EA128`. Timer ownership/units beyond this comparison are B_INFERENCE.

Capstone's unknown VMX128 words were checked with local XenonUtils: `0x847ECD6C` loads the candidate vector from `r6`; `0x847ECDBC` loads the center vector; `0x847ECDC0` subtracts them. `0x847ECEE4` multiplies the displacement vector by the radius scale. No retail instruction byte arrays are included in this report.

**No outside receiver, A_PROVEN branch; bug causality UNKNOWN.** `0x847EB628` gates on mode bit 8, scans 44-byte threat records, and returns without this adjustment if an eligible receiver lies farther outside. When none does, it can restrict the target X to the defender's X or center and, depending on primary/secondary target half, clear a state flag and set a 0.5 movement limit. This is a specific candidate for the reported lateral behavior. Its reachability under the reported Tampa-2/corner scenario is untested.

**Target selection, A_PROVEN.** `0x847EE0C0` reads threat records starting at global +`0x160`, count from `(global[0x2A8] >> 2) & 1023`, filters receiver flags, examines assigned defender pointers and scores, and maintains primary/secondary pointers at AI-state +`0x40`/+`0x48` with scores +`0x44`/+`0x4C`. Its no-new-primary path at `0x847EE76C` can use zone-record +4, promote a previous secondary, or retain the previous primary with a 0.9 score multiplier (`0x847EE7CC..0x847EE7DC`). “No other threats” therefore does not correspond to an unconditional discard in this routine. Upstream candidate construction, flags, assignment arbitration and the later movement branch still matter.

**Ratings.** At `0x847F5D58..0x847F5D6C`, zone initialization installs callback `0x847C0DB0` at `[actor+0x14]+0x2E4`. That leaf passes rating index 20 to `0x847CCC28`. Descriptor 20 at `0x84DB56F0` names getter `0x847CBED8`, whose `lbz` at `0x847CBF20` reads roster +`0xC3` (the existing Coverage rating contract). `0x847CCE48`, including its descriptor callback loop at `0x847CD060..0x847CD07C`, builds effective rating data. `0x847C1590` invokes the active callback and stores the result at +`0x2E0` (`0x847C1660..0x847C1668`). `0x847EC170` reads those cached values at `0x847EC278`, `0x847EC350`, and `0x847EC354` when computing response delays.

This proves a coverage-rating dependency in zone processing. It does not prove that every frame keeps that callback active, that primary receiver ordering is directly tier-dependent, or that a gold CB avoids the reported failure. Gold/silver/generic actors sharing control-flow code is compatible with different rating inputs. No independent “awareness” or star-tier predicate was established in the selector. Roster +`0xC9` is labelled Pass Read Coverage in the existing contract and must not be relabelled CB awareness. `0x847EA7A0` separately uses slider index 7 and a three-knot curve; a slider is not a roster rating.

**Combo/match coverage.** Play 344 Combo Inside Zone has slot-9 chain `0x1B → 0x0E → 0x0D` (nodes 3404–3406) and slot-10 equivalent 3407–3409. Their final zone nodes have F=1/G=1; safeties use mode 11. Play 345 Combo Strong Zone has the man/zone chain on one outside slot and a shallow zone on the other. Other sampled Combo plays preserve the same mixed-data pattern. `0x847EE8C8`, specifically `0x847EEB78..0x847EEB98`, searches assignments for opcode `0x0E` and takes distinct primary/secondary assignment paths. Thus the schemes have data-selected man/zone components **and** code arbitration. The sampled chains contain no `0x1A` condition node. The precise “#1 unless under,” “read #2,” and Smash/china predicates remain UNKNOWN; neither adding a fictitious condition nor changing F/G is authorized by this evidence.

## TU extraction and function comparison

[apf_coverage_tu_extract.py](tools/apf_coverage_tu_extract.py) implements the actual LIVE shape: single hash-table copies, one directory block, root consecutive `default.xexp`, at most two hash levels. Metadata SHA-1, the top table, both level-zero tables and all 191 referenced data blocks (190 file + one directory) pass. Header size is `0xAD0E`, first table `0xB000`, top table `0xB6000`, second level-zero table `0xB7000`. The source package's valid parent statuses are zero. Treating their bit `0x80` as a data-block allocation flag incorrectly rejects this TU; the new reader checks parent hashes and applies the allocation test only to data entries. **RSA signatures are not verified.**

[apf_coverage_tu_apply.cpp](tools/apf_coverage_tu_apply.cpp) is a thin adapter to the already installed XenonUtils XEX/LZX delta implementation. Python checks whole-input pins before invocation and the reconstructed PE pin afterward. The dependency verifies compressed block hashes and performs the delta reconstruction. This creates an analysis image and header, not a boot-tested or redistributable signed XEX. The extractor requires fresh binary outputs outside the checkout and reparses/re-hashes output before publishing the receipt.

The base has 18,472 `.pdata` functions; TU has 18,480. Base/TU prologue scans find 18,311/18,319 `mflr r12` words, of which 18,274/18,282 are `.pdata` starts. The remaining 37 are recorded, not blindly treated as new boundaries. `.pdata` function length is `((packed >> 8) & 0x3FFFFF) * 4`; ordering, alignment, overlap and section bounds are checked. There are 1,017,536/1,017,892 `.text` bytes outside `.pdata`, including leaf functions and padding. Manual leaf bounds supplement the coverage map.

[apf_coverage_function_diff.py](tools/apf_coverage_function_diff.py) aligns symbol-less normalized signatures in order, then monotonically pairs changed runs between anchors at shape similarity ≥0.55. It normalizes external direct branch destinations, `.text` pointer tables and common loaded addresses. Its register tracking is a heuristic, not full CFG dataflow. It cannot establish behavioral equality or label every patch function. The complete [function index](docs/research/apf_coverage/tu_function_index.json), [329-row diff table](docs/research/apf_coverage/tu_changed_functions.md), [detailed candidates](docs/research/apf_coverage/tu_changed_functions.json), and [leaf/padding gap differences](docs/research/apf_coverage/tu_gap_differences.json) preserve the unresolved cases.

| Function result | Count | Interpretation |
|---|---:|---|
| Byte-identical aligned body | 4,109 | Referenced callees/data may still change |
| Normalized equal | 14,023 | Same normalized shape; not a gameplay-equivalence proof |
| Normalized different | 329 | 35 size changes, 273 address-operand candidates, 21 other shape differences |
| Unmatched base / TU | 11 / 19 | UNKNOWN; not automatically removed / added |
| Anchored gaps | 9,245 identical; 2,436 normalized equal; 94 different; 22 unmatched | Gaps are not asserted to be single functions |

Of the 329 candidates, four directly touch mapped ratings routines. The other 325 have UNKNOWN domain and are labelled `other`, which does not exclude an indirect coverage or pursuit dependency. Zero candidate functions are **proved specifically pursuit changes** by this pass. Text before the first `.pdata` start and after the final function is not aligned by the gap pass. This is a reproducible static delta inventory, not complete official patch notes.

| Base → TU | Bytes | Checked change / classification |
|---|---:|---|
| `0x847CDD50 → 0x847CE978` | 756 → 880 | A_PROVEN shared ratings contest adds a sentinel-dependent coefficient choice and an output vector blend |
| `0x847CE048 → 0x847CECE8` | 312 → 316 | A_PROVEN caller supplies the additional output pointer; ratings |
| `0x848B9738 → 0x848BA580` | 1208 → 1188 | B_INFERENCE strength/break-tackle/tackle contest from actual indices 2/12/17; exact behavioral purpose unresolved |
| `0x848F1CD8 → 0x848F2B60` | 380 → 444 | A_PROVEN composure (21) / pass-rush (18) proximity sum adds object/flag checks and a conditional 0.9 multiplier before its distance comparison |

At TU `0x847CEBB0..0x847CEBCC`, the contest selects a three-float coefficient array based on `[[actor+0x10]+0] == -1`. Base array B `[0.7, 1.0, 0.9]` is retained for the sentinel path; the new non-sentinel array at `0x820B74A8` is `[0.6, 1.0, 0.95]`. Another base array `[0.8, 1.0, 0.8]` is retained. The input/angle/rating curves are unchanged but move by `+0x1C`, demonstrating why a universal rdata offset is invalid. TU `0x847CEC58..0x847CECCC` computes a bounded/fallback ratio from the two contest weights and blends actor +`0x1C`→+`0x40`/+`0x48` components into the new output. Calling this a velocity blend is B_INFERENCE. Controller ownership of the `-1` sentinel is also B_INFERENCE. The 28 rating descriptors keep their control words and five coefficients; their getter/setter addresses relocate.

The zone mode table, clamp constants, padding, initial-drop curves and sampled slider curve all have identical typed values at their individually checked TU locations. No instruction-shape difference appears in the mapped zone selector, no-outside-threat adjustment, zone setup, decoder, radius or steady update. Their callees/global state can still differ.

## Coverage writer and integration

[apf2k8_coverage_tuning.py](mod_editor/core/apf2k8_coverage_tuning.py) provides `ZoneEdit`, `inspect_zones`, `apply_geometry`, `verify_geometry`, `compose_geometry`, `compile_outer_entry`, and bounded shareable JSON `encode_profile`/`decode_profile` helpers. Its `status()` says offline writer/verifier, in-game UNWITNESSED, registered=false and rendered=false. Protected Studio and release files were left for the requested [WIRING.md](WIRING.md) handoff.

| Knob | Integer range | Proved scope |
|---|---|---|
| `landmark_x_feet` | −128..127 | Encoded zone landmark X, before live origin/mirror/shift |
| `drop_depth_feet` | −64..191 | Encoded zone depth, before live transformation |
| `lateral_extent_yards` | 0..15 | A extent used in the directional radius |
| `depth_extent_yards` | 0..15 | B extent used in the directional radius |

These are format bounds, not playability recommendations. No preset changes retail values by default. No “corner-route carry distance,” global flat width, awareness, China call, pass-rush angle, pre-snap shift correction, or universal sideline fix is fabricated. `.rdata` clamp editing is not shipped. The implemented pack lane needs neither a code cave nor an emulator patch hash, and its decoder/consumer layout is mapped for both versions. A raw text-page XXH3 calculation did not reproduce the context's existing Xenia module hash, so that value is not promoted into a TU patch recipe.

The pin is SHA-256 with **only** mask `0xFFFF00FF` of every valid zone payload zeroed: `ca1f83e389e9c6705438f5e05230fdc820c77c76c08e2828888121a9ee4aad28`. Everything else must match retail. This admits idempotent repeated coverage edits while rejecting foreign opcode, header, selector, route-pointer, membership, formation or name changes. For composition, apply coverage to the canonical MASTER first, then validated package/route changes, and encode outer 180 once. WIRING gives the exact order and final node-pool preservation check. Geometry belongs to a **shared node**; the preview reports every affected assignment rather than promising a single-play mutation.

Offline retail example: node 2983 depth 24→27 feet changes only body offset 120833, and affects `(278,4)`, `(439,4)`, `(473,0)`. Result body hash is `f8e7bd93a048e6d2ade46d6b68d99f1814a6ac1110d6dd37cd6ab5008bffe40f`. The full resource rebuild uses the existing H7A token-preserving encoder, including decoder equality, IFF reparse and fixed allocation checks. Output entry remains 57,344 bytes; compressed block 56,183; logical file length 56,267. The writer returns bytes for the existing transactional pack lane; it does not modify source packs. See [writer_receipt.json](docs/research/apf_coverage/writer_receipt.json).

## Verification and reproduction

The standalone new tests use authored synthetic PLAY/PE/STFS data. They cover exact geometry bit positions, preserved fields, shared assignment reporting, partial edits, range/type rejection, foreign pins, verifier tampering, idempotence, malformed chain bounds, JSON ambiguity, flat PE mapping, relocation versus numeric-immediate changes, function insertion, and STFS integrity at all supported levels. The retail test precisely skips when either required archive is absent; it ran here, including the full pack rebuild.

| Command | Result |
|---|---|
| `python3 tests/mod_editor/test_apf2k8_coverage_tuning.py` | 9 tests, OK; retail gate ran |
| `python3 tests/mod_editor/test_apf_coverage_research_tools.py` | 7 tests, OK |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf2k8_playbook_route_writer.py` | 12 tests, OK |
| `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_package_map_writer.py` | 27 tests, OK |

Exact test output is retained in [verification.json](docs/research/apf_coverage/verification.json).

The old route test initially failed under plain script execution because it does not add the repository root to `sys.path`; setting `PYTHONPATH=.` fixes that existing harness issue. Both new test files bootstrap their own imports and run with plain `python3`. No existing test file was edited.

Reproduce with a fresh external scratch directory; set `BASE_XEX`, `BASE_PE`, `TU_LIVE`, `INDEX_0A`, and `XENON_VENDOR` to the supplied local paths. `XENON_VENDOR` is the installed `tools/vendor/XenonRecomp` directory on Storage. No download is required:

```bash
ASTRA_SCRATCH=$(python3 -c 'import tempfile; print(tempfile.mkdtemp(prefix="astra-coverage-"))')
g++ -std=c++20 -O2 -I"$XENON_VENDOR/XenonUtils" \
  tools/apf_coverage_tu_apply.cpp "$XENON_VENDOR/build/XenonUtils/libXenonUtils.a" \
  -o "$ASTRA_SCRATCH/tu_apply"
python3 tools/apf_coverage_tu_extract.py --tu "$TU_LIVE" \
  --xexp-out "$ASTRA_SCRATCH/default.xexp" --receipt "$ASTRA_SCRATCH/tu_receipt.json" \
  --base-xex "$BASE_XEX" --delta-helper "$ASTRA_SCRATCH/tu_apply" \
  --pe-out "$ASTRA_SCRATCH/tu.pe" --header-out "$ASTRA_SCRATCH/tu.header"
python3 tools/apf_coverage_function_diff.py --base-pe "$BASE_PE" \
  --tu-pe "$ASTRA_SCRATCH/tu.pe" --json "$ASTRA_SCRATCH/function_diff.json"
python3 tools/apf_coverage_research.py --base-pe "$BASE_PE" --tu-pe "$ASTRA_SCRATCH/tu.pe" \
  --function-diff "$ASTRA_SCRATCH/function_diff.json" --master-index "$INDEX_0A" \
  --out docs/research/apf_coverage
```

The compiled dependency SHA-256 is `0653cc0005ae3904e0c8e856678101dcf54d887a1f1f96702e7f5e5205692b37`; `XenonUtils/xex_patcher.cpp` is `d7c780dabecd118b20186510169a2549300e852dcf868524cba0f29c3c978a9c`; its local `lzxd.c` is `622183f03bac71a12327bc9f036395dcb5c3b7c6cc7d766785de24ac1354256a`. The adapter contains no keys or retail data. The derived extraction receipt also records the helper/output hashes.

## Remaining questions, decided scope, and witness plan

The bounded build is the proved data writer. Receiver arbitration is code, but a code repair requires a proved condition to change. This pass therefore supplies exact investigation sites and **does not invent hook instructions, cave contents, or a design-only “fix” claiming an identified predicate**. The brief's data-writer branch applies; the alternative no-writer status stub is unnecessary.

For PGaither84's no-other-threat example, inspect the live candidate flags/assigned pointers entering `0x847EE0C0`, record +4 fallback, retained scores, and the deep adjustment at `0x847EB628`. For the outside-numbers example, record the two source floats and pre/post X at `0x847EA7F8`, then the steady callback's mode-specific path. Exact painted-number boundaries and the offending game's call sequence remain UNKNOWN. For 7ET's rules, finish the E operands/F/G transitions and the mode-11 branches in `0x847EED38`; the current evidence proves hybrid node data, not MOD/Palms semantics. Awareness/star-tier selection and the OLB/EDGE/pre-snap shift complaints remain untraced; no geometry control is advertised as fixing them.

For update semantics beyond the mapped routines, start with the 35 changed-size pairs and unmatched functions, then resolve the 21 other shape differences and 273 address candidates. Follow indirect descriptor callbacks and compare their data rather than treating the zero direct coverage/pursuit classification as proof of no change.

Noah's eventual witness should separate a stock base run, stock TU run, base geometry edit, and TU geometry edit. Use the same formation, play, receiver routes and coverage ratings; record drop landmarks and every affected shared-node assignment. Then isolate receiver configurations with one outside threat versus an added inside/flat threat, and low/high coverage ratings. A visible landmark change witnesses the geometry lever only; carry, contest quality, penalties, and stability require their own observations. This plan was not executed.

The following table contains every research function mapped in this pass. Complete offsets, sizes, body hashes, branch targets, bounds sources, and alignment grades are in [address_map.json](docs/research/apf_coverage/address_map.json). `N` means normalized equal, `I` byte-identical, `D` normalized different. Cross-image identities are B_INFERENCE even where the base instruction fact is A_PROVEN.

| Function / evidence | Base VA | TU VA | Bytes base → TU | Diff |
|---|---|---|---:|---|
| opcode_codec_row / A_PROVEN | `0x84a87958` | `0x84a88928` | 40 → 40 | N |
| descriptor_chain_length_loop / A_PROVEN | `0x84a87980` | `0x84a88950` | 140 → 140 | N |
| lane_cm_lookup / A_PROVEN | `0x84a94030` | `0x84a95000` | 20 → 20 | N |
| mirrored_lane_lookup / A_PROVEN | `0x84a94048` | `0x84a95018` | 32 → 32 | N |
| codec_table_address / A_PROVEN | `0x84a94068` | `0x84a95038` | 12 → 12 | N |
| generic_node_decode / A_PROVEN | `0x84a94098` | `0x84a95068` | 88 → 88 | I |
| decoded_operand_lookup / A_PROVEN | `0x84a940f0` | `0x84a950c0` | 128 → 128 | I |
| zone_decode / A_PROVEN | `0x84a92148` | `0x84a93118` | 360 → 360 | N |
| zone_encode / A_PROVEN | `0x84a922b0` | `0x84a93280` | 344 → 344 | N |
| man_decode / A_PROVEN | `0x84a92410` | `0x84a933e0` | 316 → 316 | N |
| assignment_opcode_search / A_PROVEN | `0x8482db10` | `0x8482e7b0` | 176 → 176 | N |
| assignment_float_operand / A_PROVEN | `0x8482dc00` | `0x8482e8a0` | 156 → 156 | I |
| assignment_integer_operand / A_PROVEN | `0x8482dca0` | `0x8482e940` | 104 → 104 | I |
| decode_current_assignment / A_PROVEN | `0x8482dfa8` | `0x8482ec48` | 324 → 324 | N |
| assignment_position_transform / A_PROVEN | `0x8482e180` | `0x8482ee20` | 144 → 144 | N |
| formation_alignment_cm / A_PROVEN | `0x847d0278` | `0x847d0f20` | 272 → 272 | I |
| construct_zone_records / A_PROVEN | `0x847f0a08` | `0x847f16a8` | 1448 → 1448 | N |
| initialize_zone_state / A_PROVEN | `0x847f5cb8` | `0x847f6958` | 1296 → 1296 | N |
| initial_zone_update / A_PROVEN | `0x847f4ed8` | `0x847f5b78` | 1636 → 1636 | N |
| steady_zone_update / A_PROVEN | `0x847f43c8` | `0x847f5068` | 2832 → 2832 | N |
| time_gated_zone_padding / A_PROVEN | `0x847ea128` | `0x847eadc8` | 56 → 56 | N |
| lateral_landmark_shift_and_clamp / A_PROVEN | `0x847ea7f8` | `0x847eb498` | 268 → 268 | N |
| slider_seven_curve / A_PROVEN | `0x847ea7a0` | `0x847eb440` | 88 → 88 | N |
| directional_radius / A_PROVEN | `0x847ecd48` | `0x847ed9e8` | 300 → 300 | N |
| limit_displacement_to_radius / A_PROVEN | `0x847ece78` | `0x847edb18` | 168 → 168 | I |
| deep_no_outside_threat_adjustment / A_PROVEN | `0x847eb628` | `0x847ec2c8` | 328 → 328 | N |
| select_two_zone_threats / A_PROVEN | `0x847ee0c0` | `0x847eed60` | 1992 → 1992 | N |
| assign_receivers_with_man_opcode_test / A_PROVEN | `0x847ee8c8` | `0x847ef568` | 1136 → 1136 | N |
| coverage_assignment_orchestration / B_INFERENCE | `0x847eed38` | `0x847ef9d8` | 6864 → 6864 | N |
| coverage_rating_dependent_delay / A_PROVEN | `0x847ec170` | `0x847ece10` | 880 → 880 | N |
| threat_response_geometry / B_INFERENCE | `0x847ec4e0` | `0x847ed180` | 1712 → 1712 | N |
| coverage_rating_index_twenty / A_PROVEN | `0x847c0db0` | `0x847c19d0` | 12 → 12 | N |
| roster_coverage_byte_getter / A_PROVEN | `0x847cbed8` | `0x847ccaf8` | 156 → 156 | N |
| refresh_cached_effective_rating / A_PROVEN | `0x847c1590` | `0x847c21b0` | 316 → 316 | N |
| effective_rating_and_slider_adjustment / A_PROVEN | `0x847ccc28` | `0x847cd850` | 528 → 528 | N |
| populate_effective_rating_rows / A_PROVEN | `0x847cce48` | `0x847cda70` | 3576 → 3576 | N |
| shared_ratings_contest_changed_in_tu / A_PROVEN | `0x847cdd50` | `0x847ce978` | 756 → 880 | D |
| ratings_contest_caller_changed_in_tu / A_PROVEN | `0x847ce048` | `0x847cece8` | 312 → 316 | D |
| strength_break_tackle_tackle_contest / B_INFERENCE | `0x848b9738` | `0x848ba580` | 1208 → 1188 | D |
| composure_pass_rush_proximity_sum / A_PROVEN | `0x848f1cd8` | `0x848f2b60` | 380 → 444 | D |
| tackle_rating_index_seventeen / A_PROVEN | `0x847f6430` | `0x847f70d0` | 12 → 12 | N |
| run_coverage_rating_index_nineteen / A_PROVEN | `0x847f6440` | `0x847f70e0` | 12 → 12 | N |

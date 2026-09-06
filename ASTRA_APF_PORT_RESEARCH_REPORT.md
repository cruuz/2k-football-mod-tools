# APF port research delivery

2026-09-06. Branch `astra/r62-apf-port-research`, base `7d46618`.
**EXPERIMENTAL / UNWITNESSED.**

Delivered [APF_TO_2K5_PORT_RESEARCH.md](APF_TO_2K5_PORT_RESEARCH.md), answering
the brief's animation, gameplay, presentation and priority questions in order.
No converter was justified by the bounded proof. No product code, protected
file, shared owner or integration configuration was changed.

## Results

- **PROVED:** fresh APF definition census, 5,884 records/5,256 primary names;
  632 primary names match the 2K5 catalogue. Every one of 2K5's 5,198 archive
  animation spans was compared with the original XISO, 61,096,560 bytes total.
  Name absence is not a complete census of missing gameplay behaviors.
- **PROVED:** original APF ISO XEX, master PLAY and selected frontend clip
  match pinned hashes. The existing APF glTF structural validator passes.
  Four supported 2K5 destinations pass native no-edit checks with zero changed
  bytes; eight direct/renamed APF attempts and one MMCD attempt refuse as
  expected. There is no successful APF-derived animation replacement.
- **PROVED:** all 91,833 NFL PLAY nodes reproduce exactly through the current
  codec. Of 4,948 APF nodes, 4,910 reproduce after endian conversion and 38
  opcode-`1C` nodes lose explicit operand bits. No APF numeric opcode is out of
  the NFL table's range. Complete APF chain semantics remain unresolved.
- **PROVED:** all 27 APF rating label/setter pairings match the current schema.
  Twenty-five ordinary rating values pass the 2K5 codec into a synthetic
  record, changing exactly 25 bytes. This is transport, not gameplay parity.
- **PROVED:** seven APF penalty pair sequences equal NFL values. The holding
  interpolation/RNG path was read in generated PPC code. All ten current NFL
  penalty payloads were checked against retail bytes. Both APF fantasy-draft
  tables are word-exact matches for NFL's 17-float table. These copies would
  provide no improvement.
- **HYPOTHESIS:** retarget maps, equivalent APF gameplay rules, owner byte
  estimates, expected football improvements and priority scores. Each next
  build has explicit inputs, destination writer, hooks/budgets, proof and
  witness requirements in the memo.

## Checks actually run

All tests ran with `PYTHONDONTWRITEBYTECODE=1`; test temporary directories
were under `.scratch/apf-port/tmp` and removed by their owners.

| Command / probe | Result | Peak RSS KiB |
| --- | --- | ---: |
| `python3 tests/mod_editor/test_nfl2k5_animation.py` | 16 passed | 35,440 |
| `python3 tests/mod_editor/test_nfl2k5_animation_import.py` | 18 passed | 40,992 |
| Selected retail importer tests, below | 2 passed | 222,264 |
| `tools/nfl_resource_scan.py`, fresh retail extraction | Passed | 449,024 |
| `python3 -m mod_editor.core.nfl2k5_animation ... catalog` | Passed | 214,808 |
| `.scratch/apf-port/inventory_probe.py` | Passed | 302,184 |
| `tools/validate_apf_player_shadow_gltf.py`, absolute Storage inputs | Passed | 25,300 |
| `.scratch/apf-port/import_probe.py` | Passed baseline/refusal assertions | 246,612 |
| `.scratch/apf-port/gameplay_probe.py` | Existing audit passed via provenance adapter | 95,464 |
| `.scratch/apf-port/play_probe.py` | Passed; existing lineage tool also passed | 253,940 |
| `.scratch/apf-port/data_probe.py` | Passed | 113,568 |
| `tools/camera_options_audit.py` | Passed | Not separately measured |
| `python3 -m mod_editor.core.nfl2k5_zone_facing --xbe <retail default.xbe>` | Passed, later facing policy deferred | Not separately measured |

The retail test invocation was:

```bash
PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/.scratch/apf-port/tmp" \
NFL2K5_ANIMATION_INVENTORY="$PWD/.scratch/apf-port/resource_inventory.json" \
python3 tests/mod_editor/test_nfl2k5_animation_import_retail.py \
  RetailImportTests.test_gltf_roundtrip_and_edited_seed_pose_gates \
  EmbeddedTests.test_both_root_imports_repin_and_write_exact_copy
```

The existing extractor built with `clang++-18` and reproduced the pinned
54,001,664-byte APF image. An initial `g++` attempt failed on vendored `be<>`
anonymous unions. The generic gameplay audit needed explicit external corpus
paths and a scratch-only display-path anchor adjustment; no evidence check
was relaxed. Harness development caught trailing filename spaces and bounded
the rating setter read before the next function. Final passing logs are kept
locally. No new tests or converter are committed.

The main memo records full retail hashes, exact dataflow addresses, source
locations, numerical limits and expected refusal text. Both XBE owner gates
were not rerun: no owner, hook or executable patch was introduced. The prior
owners' reported tests are historical evidence, not counted in the 36 tests
passed here.

## Decisions, gaps and witness

The first animation converter waits for proved recipient skeleton/selection,
donor gameplay-rig binding, local-translation/root-motion policy and a valid
fit to fixed target times/precision. The two embedded roots remain of unknown
football meaning. APF `1C` operands, complete chain termination and formation
extensions block a general play translator. Equal named ratings/sliders do
not establish equal catch, fatigue or tackle behavior. Generated PPC is
reference material with guest ABI/runtime dependencies, not an Xbox x86
module.

The five next builds are selected play translation, a small legend ratings
preset, one independent celebration, one recovered blocking-choice rule and
a camera preset. No gameplay artifact needs Noah's witness from this research
delivery. For each future build the memo specifies matched controls, both
directions/mirroring, relevant actor states, lifecycle and replay checks; no
future feature should be called witnessed until Noah actually plays it.

All writes were confined to the two requested documentation artifacts and
worktree `.scratch`. The main checkout and retail files were read-only. No
whole disc or pack was loaded, no disc image was built, no network/emulator/
display/audio was used, and nothing was pushed. Scratch receipts are excluded
from version control; large regenerable inventory/PE scratch files are removed
before handoff. Only the two report paths are authorized for the commit.

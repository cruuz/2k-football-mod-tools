# NFL 2K5 XBE cave oracle

This is a read-only research/build gate, not an executable patch. It requires Python 3.10+ and Capstone 5 (`python3 -m pip install -r tools/requirements-nfl2k5-cave-oracle.txt`). It needs no GUI, audio device, xemu, Ghidra installation, or cross-worktree imports. All shipped fixtures are synthetic; the optional retail regressions read the user's private USA executable.

```sh
env -u DISPLAY QT_QPA_PLATFORM=offscreen python3 tools/nfl2k5_cave_oracle.py scan default.xbe --min-size 64 --kind code --json code.json
env -u DISPLAY QT_QPA_PLATFORM=offscreen python3 tools/nfl2k5_cave_oracle.py scan default.xbe --min-size 64 --kind data --json data.json
python3 tools/nfl2k5_cave_oracle.py scan default.xbe --range 0x1AC260:16 --range 0xA69969:7 --json queries.json
```

The scan automatically loads `data/nfl2k5_cave_reservations.json` for the pinned USA retail XBE. It refuses a mismatched/incomplete manifest or stale writer-source fingerprints. Use `--retail-only` to explicitly analyze retail bytes without patch ownership, or `--manifest PATH` to supply another compatible ownership manifest. For an unpinned executable with no explicit manifest, the report says ownership was not supplied; it makes no claim about a studio stack. JSON output cannot overwrite the input, disc, or loaded manifest, including via a hard link.

The terminal summary lists up to 20 largest free candidates **per section**, with both neighbour reasons. An empty list is a valid and expected retail result. JSON contains every maximal verdict run at least `--min-size` bytes, complete per-section byte counts including shorter runs, roots, budgets, uncertainty counts/examples, static absolute writes, and exact `--range VA:SIZE` queries. Addresses and end points in range/evidence records are hex strings; end points are exclusive. Section metadata from the header uses integer fields. No executable byte payloads are exported.

## Verdicts and permissions

| Verdict | Meaning |
| --- | --- |
| `reachable` | A decoded instruction/path or explicit static reference covers at least one byte. The witness identifies its source. This is a statement within the root model, not an in-game execution claim. |
| `unknown` | Possible raw pointer/transfer, unbounded memory/table access, unresolved import/indirect transfer, invalid/truncated path, unmapped range, or exhausted analysis budget. Unknown is never allocatable. |
| `free-under-closed-world` | No recorded reference or applicable uncertainty covers the range, under the explicit model below. Permissions must also allow the requested use. |
| `reserved` | The current stack owns any overlapping byte. This overlay takes precedence over the three retail verdicts; owner names and reservation bases are returned. |

A **code** cave must be wholly file-backed in one executable section (flag `0x4`). An executable section need not be named `.text`: the retail XBE marks numerous library and data sections executable too. A **runtime-data** cave must additionally have writable flag `0x1`; `.text` is explicitly forbidden even if a foreign header advertises writability. The query returns `eligible` separately from reachability, so a reserved/readable range never becomes a data allocation by accident.

Header bytes, virtual zero-fill and inter-section gaps are not offered as offline caves. Existing header/logo allocations are still reserved by ownership. The write gate's `runtime_writable()` models a gap only when all sections sharing its page agree, and checks the entire access width. This explains existing flags at `0xA69970`, `0xA69974`, `0xA69978`, and `0xA6997C`; it does **not** certify a new flag in `0xA69969..0xA69980`. No new runtime flag is allocated by this tool.

## Closed-world model and bounds

The model is 32-bit x86 with validated, non-overlapping XBE virtual/raw mappings. File offsets are translated through the section table, never assumed to equal `VA - 0x10000` outside the header/retail `.text` layout.

Roots include retail/debug/Sega XOR-decoded entry and kernel-thunk addresses, TLS directory/template/index/callbacks, nonkernel import records and UTF-16 names, and the boot bitmap read by the loader. All byte alignments of complete dwords inside every file-backed section are examined for values pointing into mapped sections. Such a word is a **possible** pointer: floats and packed data often resemble addresses. Its storage and target remain speculative, and code reached from it is decoded with speculative certainty. It is never silently upgraded merely because disassembly succeeds.

The oracle also scans rel8, rel32 and near conditional encodings at every executable byte offset, including overlapping/data encodings. These become definite only on a rooted decoded path. Complete `mov [imm32], imm32` callback-store encodings provide explicit static store witnesses independent of entry-path coverage. In particular, `0x1B8777` stores `0x1AC260` into `0xBE51C8`; the witness is preserved even with a small decoding budget. Such a witness establishes the encoded store relationship, not that its enclosing function ran.

Recursive decoding records instruction extents, branch/call targets, fallthrough and call-return paths, immediate addresses, absolute data reads/writes, and pointers loaded from statically read words. Candidate neighbours include every recorded covering instruction, so an instruction interior cannot be mistaken for padding. Indexed absolute tables expose their base, contiguous pointer slots and possible targets. This version does **not** prove table-index ranges or table lengths, track general register values, or infer vtable types. Even `cmp; ja; jmp [table+index*4]` retains unresolved-index uncertainty. Register and stack-derived memory accesses, indirect calls/jumps, imported code effects, and implicit/string accesses conservatively leave all otherwise unobserved image bytes unknown.

Returns assume balanced calls and return to decoded call successors. The model excludes external code injection, self modification, address synthesis outside the decoded operations, DMA and undocumented loader entry points. It does not prove absence of references synthesized by those excluded mechanisms. No Ghidra function bound is treated as a liveness proof.

Default budgets are 250,000 decoded instructions and 2,000,000 non-instruction evidence records. Loader tables have 4,096-entry limits and image size is bounded at 256 MiB. `--instruction-budget` and `--reference-budget` can increase coverage. Reaching a limit marks incomplete work unknown; it cannot produce new free bytes. Definite roots get decoding priority; possible roots retain their uncertainty. Output truncates displayed witnesses/examples only, never the data used to choose the verdict. The retail image is expected to retain unknown ranges even with larger budgets because external/indirect effects remain unresolved.

## Ownership generation

```sh
env -u DISPLAY QT_QPA_PLATFORM=offscreen python3 tools/nfl2k5_cave_oracle.py manifest default.xbe \
  --xiso retail.xiso.iso --work-dir /writable/scratch --json data/nfl2k5_cave_reservations.json
```

Run this in a dedicated process with space for a disposable 6.3 GB disc. The source XBE must match SHA-256 `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`, and the disc's resolved `default.xbe` must match it byte for byte. The writer never passes the source disc to a mutating studio API.

Generation runs the real `mod_build.build()` experimental preset on the temporary target while scoped wrappers record each XBE writer's before/after hash and exact byte diff. It then adds the dormant seven-on-seven executable and playbook to that copy. Image-level position recoding/roster work, kickoff alignment, schedule, history, names, and scorebug mesh/XBE/HUD all execute. The scorebug's optional PNG texture repaint/import is disabled: it cannot affect executable ownership and depends on a presentation-audit fixture absent in a fresh checkout. This option is explicit in the manifest; this is not a claim that a fully textured release image was built.

The manifest unions exact diffs with declared edit/cave extents and unchanged runtime slots. Shared padding in `0xB4A60..0xB4A90`, the complete helper at `0x2BA840..0x2BA860`, relocated boot-logo capacity, and zero-initialized flags stay reserved. Playoffs/preseason sites name their child-module owner as well as the invoking season writer. Shared section-digest changes and nested writers can have multiple owners; ownership is a union, not an exclusive allocation table. Every final changed executable byte must have an observed writer, and all final section digests must verify using the studio's existing digest implementation. The temporary image is removed after completion or failure.

The generated JSON contains hashes/addresses/sizes and no retail byte strings. Source fingerprints cover the dispatcher, preset and current NFL2K5 writer/helper sources. Regenerate after Claude finishes beta-60 changes to those sources; stale reservations fail closed. Alternate settings that use the same sites do not create independent allocations. Arbitrary future plugins, user-authored patches and new site layouts require a new manifest.

## Gate use

```python
from mod_editor.core.nfl2k5_cave_oracle import CaveOracle, ReservationManifest, XbeImage

image = XbeImage(retail_bytes)
manifest = ReservationManifest.load(manifest_path, image, source_root=repo_root)
oracle = CaveOracle(retail_bytes, manifest=manifest).analyze()
oracle.require_cave(candidate_va, candidate_size, kind="code")
# For new mutable storage:
oracle.require_cave(flag_va, flag_size, kind="data")
```

`reserved` and `reachable` fail the allocation gate. `unknown` also fails: it is not an approval mechanism for existing unwitnessed patches. `exclude_owner` is only for examining that owner's already declared region; it must never hide another owner or be used to allocate new space.

The old reference gate intentionally permits calls to the first byte of a replaced function and references originating inside the replaced span. `legacy_references()` / `legacy_external_references()` reproduce that projection exactly, including its historical scanning endpoints and filters. A legacy negative means “no external reference under the old filters,” not proved free. The new tests compare every old target/source and retain both existing gates. Applying strict new-allocation rules retroactively to live-function replacement sites would confuse intentional hooks with new caves; certify new allocations separately.

`absolute_writes()` accepts complete code spans starting on known instruction boundaries, checks Capstone operand access flags and full widths, and returns unknown for unresolved writes or undecoded suffixes. Do not feed it raw byte-diff starts: a changed immediate can start in the middle of an instruction. The existing memory gate now also checks full-width writability with the oracle mapping. Synthetic fixtures cover permission failures, second-operand writes and partial instruction spans.

See `WIRING.md` for the beta-60 handoff and `ASTRA_CAVE_ORACLE_REPORT.md` for measured results.

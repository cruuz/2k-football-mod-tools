# Backbreaker Ghidra scripts (recovered)

These 15 Ghidra scripts are **recovered reverse-engineering sources** for
*Backbreaker* (Xbox 360), the third title in this workspace's modding roadmap.

## Provenance

The original `.java` sources were not retained. Only compiled `.class` artifacts
survived, in the Ghidra OSGi bundle cache at
`tools/ghidra-home/.config/noah-ghidra/ghidra_12.1.2_PUBLIC/osgi/compiled-bundles/57ec247a/Backbreaker*.class`.
They were reconstructed with the CFR 0.152 Java decompiler and cleaned until
they compile cleanly against the vendored Ghidra 12.1.2 API plus the
XEXLoaderWV extension (`javac --release 21` over
`tools/vendor/ghidra_12.1.2_PUBLIC/**/*.jar` and
`tools/vendor/ghidra_12.1.2_PUBLIC/Ghidra/Extensions/XEXLoaderWV/lib/XEXLoaderWV.jar`
produces all 25 classes with zero errors). The cleanup fixed:

- the CFR header was replaced with this provenance note;
- a mistranslated `ArrayList<CallSite>` (really a list of reference strings) was
  corrected to `ArrayList<String>`;
- CFR try-with-resources reassignment artifacts were rewritten as proper
  `try (BufferedWriter output = ...) { ... }` blocks;
- a stray-semicolon try-with-resources artifact (`)));){`) was repaired;
- extra closing parentheses left on the `references.add(...)` lines were removed;
- spurious `(Object)` casts were dropped from `compareTo`, for-each over
  `MemoryBlock[]` / `int[]`, and `Iterator` declarations (CFR had typed
  iterators as `Object`);
- in `BackbreakerTU2ReceiverIconHudAudit`, variables CFR had merged into
  dual-purpose `Object` holders were split back into `Iterator` and local
  `Function` variables, and two reused loop variables were renamed;
- `BackbreakerTU2TackleDefineAudit` for-each over the `long[]` focus list was
  restored from a bogus `(Iterator<Long>)` cast.

**These scripts compile-verify against the real Ghidra API**, but they have not
been *run* (no Backbreaker binary is loaded in this environment). Run them only
against a Backbreaker XEX whose MD5 matches the script's `EXPECTED_MD5`
constant — each script validates the loaded program MD5 and a set of critical
words/vtable slots and refuses to run on anything else.

## Source-revision pins (EXPECTED_MD5)

| MD5 | Used by |
| --- | --- |
| `4260a495ab98c6c3608b801628ea2200` | all `BackbreakerTU2*` scripts (the TU2 title-update XEX) |
| `4d425702e7cbfeec805e73511cb4b69f` | `BackbreakerCameraDispatchTrace` (a different Backbreaker build) |

No Backbreaker disc image or Ghidra project is currently in this tree; recreate
`ghidra_projects/backbreaker` from a legally owned copy before running these.

## What each script does

| Script | Purpose |
| --- | --- |
| `BackbreakerApplyXexpDump` | Dump XEXP (Xbox 360 patch/export) data. |
| `BackbreakerCameraDispatchTrace` | Trace camera dispatch boundaries (older build MD5). |
| `BackbreakerCameraVtableProbe` | Probe camera class vtables. |
| `BackbreakerTU2ActiveCameraTrace` | Emit active quarterback-camera facts + bounded assembly (FOV accessors, smoothing rates, vtable slots, QB camera ctor/update). |
| `BackbreakerTU2CameraStateDispatch` | Camera state dispatch facts, raw branch refs, vtable, D-form accesses, per-function assembly + pseudo-C. |
| `BackbreakerTU2DefenseOrientationAudit` | Audit defense-orientation ranges. |
| `BackbreakerTU2NativePassCameraAudit` | Native pass-camera facts, per-camera assembly, raw ranges, and decompiled C. |
| `BackbreakerTU2PassingFeasibility` | Passing feasibility: field accesses, function assembly, raw ranges, decompilation. |
| `BackbreakerTU2PassingInputMap` | Map passing input bindings. |
| `BackbreakerTU2PassingSelectorTrace` | Trace the passing selector (facts, assembly, raw window, decompilation). |
| `BackbreakerTU2PassPhaseGate` | Pass-phase gate analysis. |
| `BackbreakerTU2ReceiverIconHudAudit` | Audit receiver-icon HUD resources. |
| `BackbreakerTU2ReceiverOrderAndSchemeTrace` | Trace receiver order and route scheme. |
| `BackbreakerTU2TackleDefineAudit` | Audit tackle define tables. |
| `BackbreakerTU2TransitionPolicy` | Transition-policy analysis. |

## Running

1. Load the matching Backbreaker XEX into a Ghidra project (Xbox 360 / Xenon
   A2 language; the scripts note that undefined words are Xenon vector opcodes
   unsupported by Ghidra's A2 language and dump their raw bytes unchanged).
2. Confirm the program MD5 matches the script's `EXPECTED_MD5`.
3. Run the script with one argument: an output directory, e.g.
   `BackbreakerTU2ActiveCameraTrace.java /path/to/output`.
4. Each script writes machine-readable `*_facts.txt` / `*_assembly.txt` (and
   sometimes `*_pseudo_c.c` / `*_decompile.c`) into that directory and prints a
   `BACKBREAKER_*_COMPLETE` marker.

See `docs/research/backbreaker_tu2_recovered_tooling.md` for the recovered
architecture findings and the broader Backbreaker workstream plan.

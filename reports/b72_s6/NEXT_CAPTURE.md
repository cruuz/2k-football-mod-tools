# Decisive capture, bounded to one failing HUD submission

The existing 13:55:49 sample contains no sprite draws. Length in seconds and method count are not frame-completeness tests. Also, stock `nv2a_pgraph_method` omits every `ARRAY_ELEMENT16` parameter. Fix both capture limitations before taking another sample.

## Data that decides the cause

At the failing label and a bright score draw in the **same presented frame**, preserve:

1. Actual submitted index values, all referenced vertex attributes, resident vertex-program words from PROGRAM_START to FINAL and all constants read by that program, including viewport constants. Include texture DMA objects and resolved physical addresses.
2. Full PGRAPH register state, not just methods emitted during the interval. Include depth enable/function/write mask, colour and zeta surface format/pitch/offset, shade mode, logic operation, all clip/window/viewport/AA state, fog, alpha, blend, every texture register and all combiner constants. This captures values inherited before tracing began.
3. The exact guest texture and palette bytes at both draws and the **host uploaded texture actually bound to the draw**, along with the generated GLSL and the uniform values actually sent to GL. A guest RAM match alone cannot clear the texture-cache or shader-uniform path.
4. Colour and depth attachments immediately before and after the label draw, after the score draw and after the remaining HUD draws. Record an opaque core pixel identified by its UV and vertex identity, not a guessed screenshot rectangle. Retain an image from that exact presented frame.

If the sampled host core is already dark, compare it with the matching guest index/palette and the texture-cache upload. If texture is white but fragment output is dark, evaluate the captured shader/uniforms. If the shader predicts white but the draw leaves the target unchanged, inspect coverage/depth/stencil/alpha/logic state. If the label is bright immediately after its draw and dark at the frame end, the next attachment change names the overwriting draw. Those observations select a cause without guessing a reset.

## Correct the stock method logger

Use the installed source revision `fc24584ce88f0915ad7f04775bb7712c2e3f49ee` for the diagnostic build, or record any intentional revision change. In `hw/xbox/nv2a/pgraph/pgraph.c`, `pgraph_method_log` suppresses method `NV097_ARRAY_ELEMENT16` before calling `trace_nv2a_pgraph_method` (exact installed revision lines 489-512; supplied local source lines 525-550).

For the diagnostic build, remove the conditional suppression so that the existing block resolving `method_name`, `base` and `offset` and calling `trace_nv2a_pgraph_method(...)` also runs for `ARRAY_ELEMENT16`. The method table already names that method, and `pgraph_method_non_inc` calls this logger for every parameter. Keep the normal trace-event enabled guard; do not add unconditional stderr logging. The separate `_abbrev` event is unnecessary and still cannot supply indices.

This source edit is a capture instruction, not an installed or tested emulator modification from this job. The unmodified source and executable were not changed.

## Keep the trace off outside the sample

Start xemu with a trace output file but **no events enabled**. While navigating or waiting for the failure, keep all of these off:

```text
trace-event nv2a_pgraph_method off
trace-event nv2a_pgraph_method_unhandled off
trace-event nv2a_pgraph_method_abbrev off
```

When the dark scorebug is visible, use a controller around the monitor with the following sequence:

1. `stop`, record the output-file byte position and capture the initial complete PGRAPH snapshot at a synchronized renderer boundary. CPU stop alone does not guarantee the renderer has finished queued work.
2. Enable only `trace-event nv2a_pgraph_method on`, then `cont`. Leave `_unhandled` and `_abbrev` off. A `try/finally` in the controller must turn **all three** events off and stop the guest on success, error or timeout. Add an independent wall-clock watchdog, such as two seconds, that sends those same cleanup commands even if the main collector fails.
3. Stop after one complete target HUD submission has been collected between known frame boundaries, not after an assumed 0.1 seconds. In the instrumented renderer, arm a one-shot capture and disarm it after the target HUD and subsequent presented-frame colour attachment have been recorded. Target by the **resolved texture identity and HUD geometry**, since the current addresses `0x01e55480`/`0x01e75480` may change next boot. Require both the label and score index sets. A timeout without that condition is an incomplete sample and must be reported as such.
4. In cleanup, issue all three `off` commands, `stop`, and `info trace-events`; verify the events report disabled. Only then save the final byte range. Do not leave `_unhandled` enabled: the old sample ends with notifications from that still-active event.
5. Save the full physical RAM as synchronized evidence. `pmemsave 0 0x4000000 <unique-output-path>` must produce exactly **67,108,864 bytes**. Wait for completion and check length and hash. The previous `pmemsave_error=false` metadata did not detect its 7,901,184 missing bytes. Guest RAM saved later is not a replacement for the small per-draw resource/vertex snapshots.

For the one-shot snapshot implementation, the shared `PGRAPHState` holds `regs`, `program_data`, `vsh_constants`, vertex-array descriptors and inline elements. Capture these **before GL draw submission**, after any squashed draws have been resolved. In `pgraph/gl/draw.c`, bracket the actual draw, including the before/after colour and depth attachments. Capture the bound texture after the texture-cache lookup/upload in `pgraph/gl/texture.c`, and the selected program and uniforms after shader binding. This explicitly covers the values a method-only trace cannot recover. Persist the resolved DMA base/limit alongside every RAM offset and reject out-of-range reads.

A host graphics frame debugger may supply the GLSL, uniforms, textures and attachment history instead of custom GL dumps, provided it captures the exact same frame. Pair it with the corrected guest-method/state capture; do not infer guest state from an unrelated earlier frame.

No new emulator run is authorized or performed by these instructions. They are the integrator's capture specification. Do not build another gameplay test disc to test a guessed runtime change from this branch.

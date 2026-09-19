# b72-s5 GPU gate: FAIL, cause still unknown

The bounded native capture now crosses the material/shader boundary left open in s3. It still does not reproduce the dark label. The three model maxima are 255; the supplied screenshot maxima are 67, 90 and 74. A cause-specific GPU fix is therefore **not proved or applied**. This work is a diagnostic and team-colour branch, not a validated beta 72.1 label fix.

## What executed

Retail descriptor traversal `0x243d0`, vertex-array setup `0x315c0`, material binder `0x24160`, vertex-program upload `0x31430`, sampler/program binder `0x323d0`, combiner upload `0x32150`, and render-state encoding `0x2fc80` execute under Unicorn. New code ranges are SHA-256 guarded in `tools/scorebug_sprite/gpu.py`; the prior traversal/state guards remain. The matrix helper `0x22950` is still replaced by geometry already obtained by the native projection harness. `0x28110` returns an owned command bucket. Vertex-program residency uses owned slots and native upload instructions.

The harness has no preceding frame FIFO or PGRAPH snapshot. It invalidates CPU state-cache values to expose material writes and supplies the caller diffuse multiplier `(1,1,1,1)` at bucket+0x2e0. These actions do not establish the actual GPU state in Noah's running game. The owner continues to write white label vertex/material colours; its visibility logic is unchanged.

Ordered packets, last method writes, full vertex-program words and indexed vertex constants are in `baseline_gpu_False.json` and `baseline_gpu_True.json`. Active team-colour traces are in `gpu_False.json` and `gpu_True.json`. `gpu_methods.md` lists every emitted method side by side and separately lists important missing inherited state. S3's CPU ordering conclusion is retained; it is not presented as the new GPU proof.

## Decoded fragment path

Label material `yscore_buga1` and score material `yscore_buga` have the same values below, at both aspects in this fixture. Their element indices differ because they draw different quads.

| State | NV097 offsets | Label | Score digits |
|---|---|---|---|
| Texture format | 0x1b04 | 0x09810b29: swizzled P8/I8_A8R8G8B8, 2D, 256x512, one mip, DMA context 1 | Same |
| Texture base | 0x1b00 | 0x0004a680 in baseline fixture | Same |
| Palette | 0x1b20 | 0x0006a680: 256 BGRA entries; context 0 | Same |
| Address U/V/P | 0x1b08 | 0x00010101: repeat | Same |
| Enable and LOD clamps | 0x1b0c | 0x4003ffc0: enabled, minimum 0, maximum raw 0xfff | Same |
| Filter | 0x1b14 | 0x02062000: linear mag, linear/mipmap-linear min; bias 0; one available mip | Same |
| Texture stage program | 0x1e70 | 0x1: stage 0 PROJECT2D, stages 1..3 unused | Same |
| Vertex colour format | 0x176c | 0xa40: UB_D3D, four normalized BGRA bytes, stride 10 | Same |
| Vertex UV format | 0x1778 | 0xa21: two normalized signed shorts, stride 10 | Same |
| Vertex program | 0x0b00..0x0b7c upload ports; 0x1e9c/0x1ea0 | 13 instructions; colour write MUL oD0,v3,c6 | Same |
| Vertex UV transform | 0x1ea4 + 0x0b80..0x0bfc stream | c7=(0.5,0.5,0.5,0.5); oT0.xy=v6.xy*c7.xy+c7.zw, default q=1 | Same |
| Vertex colour multiplier | 0x1ea4 + 0x0b80..0x0bfc stream | c6=(0.5,0.5,0.5,0.5) | Same |
| Stage count/constant routing | 0x1e60 | 0x11101: one active stage, per-stage constants, mux MSB | Same |
| RGB stage input | 0x0ac0 | 0xc8c40000: signed T0.rgb * signed diffuse.rgb; zero C,D | Same |
| Alpha stage input | 0x0260 | 0xd8d41010: signed T0.a * signed diffuse.a; zero C,D | Same |
| Stage outputs | 0x0aa0 / 0x1e40 | 0x100c0: AB to R0, scale 2, clamp [-1,1], other outputs discarded | Same |
| Stage C0/C1 | 0x0a60..0x0a7c / 0x0a80..0x0a9c | All zero; unused by this multiply | Same |
| Inactive stages 1..7 | 0x0264..0x027c, 0x0aa4..0x0abc, 0x0ac4..0x0adc, 0x1e44..0x1e5c | All zero, inactive | Same |
| Final combiner | 0x0288 / 0x028c | 0x0f030c00 / 0x11331c80 | Same |
| Final C0/C1 | 0x1e20 / 0x1e24 | Both zero | Same |
| Fog enable | 0x02a4 | 0 | Same |
| Alpha test | 0x0300 / 0x033c / 0x0340 | Enabled, GEQUAL (0x206), reference 2 | Same |
| Blend | 0x0304 / 0x0344 / 0x0348 / 0x0350 | Enabled, SRC_ALPHA / ONE_MINUS_SRC_ALPHA, ADD | Same |
| Blend constant | 0x034c | 0, unused by those factors | Same |
| Write mask | 0x0358 | 0x01010101: RGBA enabled | Same |
| Shade mode | 0x037c | UNKNOWN, not emitted | UNKNOWN |
| Depth test enable | 0x030c | UNKNOWN, not emitted; depth func LEQUAL and mask 1 are emitted | UNKNOWN |
| Logic op enable/op | 0x17bc / 0x17c0 | UNKNOWN, not emitted | UNKNOWN |

There is no separate NV097 TFACTOR register in this captured stream. D3D texture-factor effects would be expressed through the combiner constants/program. All captured stage and final constants are recorded. The caller multiplier written as c5 is also recorded; the captured colour instruction reads c6, not c5.

The final combiner is `D + A*B + (1-A)*C`, alpha `G`, with A=E*F, B=fog RGB, C=R0 RGB, D=0, E=final C0 alpha, F=1-fog alpha, G=R0 alpha. Captured final C0 alpha is zero, so the final stage passes R0. A hypothetical nonzero final C0 alpha can mix in fog and darken output; the test exercises that equation. **No evidence establishes that hypothetical state in the failing game draw.** Applying it to the two identical fixture materials would affect both label and scores.

## Reference model and calibration

`tools/scorebug_sprite/xemu_model.py` follows local xemu commit `f9b14039e5bb56ae2d8f028e31e7cc19f13f7e12`. `xemu_source.json` pins the files inspected. The key references are `pgraph/texture.c` P8 palette expansion, `pgraph/swizzle.c` rectangular Morton order, `pgraph/glsl/vsh-prog.c` instruction decoding, `pgraph/glsl/psh.c` input mapping/stage/final equations, and `pgraph/gl/draw.c` blend factors. The reference independently decodes P8 indices and BGRA palette bytes, fetches bilinearly with captured repeat/clamp addressing, applies the captured vertex UV and colour instructions and combiner equations, alpha test and RGBA blending. It refuses other programs/formats instead of silently approximating them.

The full vertex instruction fields are retained in `vertex_program_decode.json`. Its UV instructions are MAD oT0.xy,v6.xy,c7.xy,c7.zw and MOV oT0.zw,v6.zw; the two-component S1 vertex array supplies z=0,w=1. The model uses the uploaded c7, including the PROJECT2D q=1 division. Position uses c0..c3 and indexed c27..c29; the omitted matrix helper and inherited viewport/surface state remain explicit geometry boundaries.

For this program, `oD0=v3*c6`, `R0=clamp(2*T0*oD0)`, and the final stage passes R0. White vertex colour with c6=0.5 therefore gives the fetched texture colour and alpha. The opaque white texture core is 255 over measured plate luminance 18 or 19; alpha 128 gives approximately 137. `measured_plate_probe.json` records these analytical blends. No fitted gain, bias, multiplier, or screenshot-derived shader constant is used.

The full baseline images use the exact s3 layout/template with revision-1 owner compatibility, both teams DET/LV, the existing display transform and software pixel coverage. The retained field-goal event text uses the older font raster; its GPU state is not captured. These are bounded fragment-model previews, not faithful whole-GPU emulation.

| Screenshot/state | Supplied label min/mean/max | Model min/mean/max | Absolute errors | Model score cores |
|---|---|---|---|---|
| ksnip_20260919-112349, Raiders ball | 19 / 27 / 67 | 24.83 / 82.43 / 255 | 5.83 / 55.43 / 188 | 253 / 253 |
| ksnip_20260919-112501, field-goal setup | 19 / 25 / 90 | 0 / 68.23 / 255 | 19 / 43.23 / 165 | 253 / 253 |
| ksnip_20260919-112603, Lions ball | 19 / 22 / 74 | 7.22 / 53.59 / 255 | 11.78 / 31.59 / 181 | 253 / 253 |

All three fail the within-15 gate. The existing descriptor's own screenshot crop measurements are also retained in `calibration.json`; they differ from supplied values, especially the field-goal maximum. Both comparisons reject calibration. Bright score predictions alone cannot validate the label model. The earlier `render_evidence.log` used 18 for the supplied Lions minimum; `calibration.json` and the table above correct that target to the brief's 19.

## Exact missing evidence and decision

The unknown is the **actual draw-time GPU state and sampled resource contents in the failing frame**, including values inherited before the bounded descriptor call. The decisive capture would pair one failing label draw with a bright score draw in the same frame:

1. Ordered PFIFO methods from the preceding game draw through both HUD draws, or PGRAPH register snapshots at those draws. Include texture DMA context objects and limits; surface format/pitch/offset; window clip/scissor; depth-test enable and depth buffer; shade mode; logic-op enable/op; anti-aliasing and z-clip controls. The offsets are listed in `gpu_methods.md`. Include the live command bucket's CPU shadow-cache words too: forcing those dirty in this fixture can conceal a disagreement between that cache and actual GPU registers.
2. Live vertex program and constants, all combiner words/C0/C1, sampler state, vertex attributes and UVs at both draws. This confirms whether the fixture's zero final C0, c6=0.5, and equal fragment state actually hold after the game's state-cache decisions.
3. Raw VRAM bytes at the texture/palette addresses for both draws, plus xemu's uploaded host texture and generated shader/uniforms. Matching container pixels does not prove matching VRAM fetches or host texture-cache contents.
4. The render target immediately before and after each draw and the actual surface-scale/AA settings. A labelled core pixel and nearby plate pixel then distinguish rejected/occluded fragments, wrong sampled RGB/alpha, shader darkening and blend/logic output.

The fixture already predicts that opaque white label texels survive its combiner and blend path. A full draw capture can localize the first divergence without retesting s3's CPU order conclusion. No new live emulator session, game result or disc test is claimed here. Until that evidence reproduces the failure, setting a guessed constant or changing material order would not be a proven fix.

`render.py` now defaults to the bounded xemu fragment path; `--naive` retains the earlier comparison. The images, CLI and JSON receipts explicitly report failed calibration. These previews must not be described as what Noah's game will show yet.

# APF 2K8 stadium renderer handoff — bounded runtime-debugger result

Date: 2026-07-18  
Result: **negative at the emulator/debugger boundary; material ownership remains unresolved**

## Question

Can Xenia Canary stop at the statically identified APF renderer material-apply
routine so the live material, shader, and texture-object arguments can be
captured for one stadium draw?

The target guest address was `0x84B15488`. Static work had already connected
the selected stadium scene to 116 meshes, 328 draws, 113 serialized material
records, and 13 shader families, but found no static reference from those
records to any of the 737 named texture identities. This experiment tested the
next narrow route: Xenia's `break_on_instruction` facility.

## Controls

- Private user-supplied game tree; no source-game file was patched.
- Private Xenia Canary build `canary_experimental@6e5b8324f` (2026-07-08).
- Wine-hosted Vulkan/FBO/SDL runtime on the isolated Spark Hands desktop
  `DISPLAY=:99`; the user's visible desktop and pointer were untouched.
- `break_on_instruction = 2226214024` (`0x84B15488`).
- `store_all_context_values = true` and `debug = true` for this attempt only.
- Existing source and emulator binaries were unchanged.
- Pre/post configuration SHA-256:
  `921e4c13d648c25cb7e01ee96e38a4ad8c8c7dcf80879211ee37d2a5865cf04f`.

## Observed result

Xenia initialized the title far enough to create the main Xbox thread, load
230 shaders, restore 428 pipeline descriptions, translate 215 shaders, create
the audio client, and attach the private virtual controller. Before any game
frame appeared, Wine reported:

```text
Unhandled exception 0x80000003 in thread 204 at address 00000000A0384604
```

The Xenia dialog identified a nested invalid-address failure with
`Last NTSTATUS: 0xC0000018` on `Main XThread (F8000008)`. Dismissing it exposed
a Wine debugger nested exception with `Last NTSTATUS: 0xC0000022`, also on the
main Xbox thread. The renderer's guest registers and live arguments were never
made available. The Xenia surface remained black; no game content rendered.

This behavior is consistent with Xenia implementing
`break_on_instruction` as a host `int3`: Wine intercepts the host breakpoint
and starts its debugger instead of delivering a usable guest execution stop in
Xenia's GUI debugger. Xenia's GUI guest debugger can pause a running title and
inspect state, but this build exposes no execution-breakpoint command in that
UI.

## Classification

This is a **completed negative experiment**, not evidence that the material
handoff address is wrong and not evidence that stadium textures are absent.
It falsifies this specific capture route in the current Wine-hosted Xenia
environment. Repeating the same configuration cannot reveal ownership and is
therefore out of scope.

The honest product state remains:

- stadium scenes, meshes, draws, materials, shader families, and candidate
  texture inventory are browsable/exportable;
- surface-to-texture ownership is unresolved;
- click-to-select texture and stadium Replace/Revert stay locked;
- no inferred or nearest-name texture is presented as owned.

## Rollback and best next route

The exception dialog and emulator were closed through the isolated desktop.
The private controller FIFO was removed. All three debug settings were restored
exactly (`break_on_instruction = 0`, `store_all_context_values = false`,
`debug = false`), and the configuration returned to its pre-experiment hash.

The best next ownership route is not another Xenia breakpoint attempt. It is a
small Xenia instrumentation build (or a native-Windows debugger run) that logs
the guest material-apply arguments at `0x84B15488` without raising a host
breakpoint. That remains a bounded future spike; it does not block the rest of
Stadium Studio.

# APF 2K8 roster-identity runtime experiment — 2026-07-18

> **Historical control, superseded in part:** this receipt covers the retired
> generic whole-stream H7A rebuild. A later team-only candidate using the
> retail-token-preserving encoder booted, visibly rendered `CODEXTEAM`, reached
> Team Select, and exited cleanly. The current positive receipt is
> [apf_roster_identity_token_preserving_runtime_20260718.md](apf_roster_identity_token_preserving_runtime_20260718.md).
> The player-name family remains unproved through the repaired route.

## Result

**Negative for the historical generic transport.** The bounded
fixed-allocation roster-name writer still passes its
offline rebuild and independent semantic reparse, but every changed ROST build
tested here crashes during startup in Xenia Canary at the same guest program
counter. The clean control reaches the APF title screen with the same emulator,
configuration, source dump, and empty persistent profile.

This falsified the claim that the generic on-disc ROST replacement was usable at
runtime. It no longer falsifies the repaired team display-name route: the later
token-preserving A/B isolated transport amplification and produced a positive
visible-consumption result. This report remains the exact negative side of that
causal comparison.

## Pinned environment

- Emulator: Xenia Canary `canary_experimental@6e5b8324f` (2026-07-08 build)
- Title: `54540807`, All Pro Football 2K8
- Emulator configuration SHA-256:
  `921e4c13d648c25cb7e01ee96e38a4ad8c8c7dcf80879211ee37d2a5865cf04f`
- Clean source `0A` SHA-256 before and after every build:
  `dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e`
- Each replay used a separate empty storage/content/cache root while copying the
  exact known-good Xenia configuration into that root.
- All GUI, emulator, controller, and visual work ran on the
  isolated `DISPLAY=:99`; the operator desktop was not touched.

## Builds and observations

| Build | Bounded edit | Output `0A` SHA-256 | Observation |
|---|---|---|---|
| Clean control | none | source hash above | Reached the normal APF title screen; no guest crash dialog. |
| Combined | Americans → `CODEXTEAM`; Marino → `CODEX` | `0219e730233327a63a6b54c1baea691dd43065bc459197b3dcbd997a8ca43a4c` | Crashed over the 2K/Visual Concepts intro. |
| Team only | Americans → `CODEXTEAM` | `fea265d2a58a7c331fdab399c10ff93fb3f9d64b2acc417b6d2fb81a918f621b` | Crashed over the same intro. |
| Player only | Marino → `CODEX` | `47f9f4c293f8c791d1480f56bacc7b1eff1b9dc863327d282c06a55d32ee8471` | Crashed over the same intro. |

All three changed builds reported:

```text
Thread Handle: 0xF8000028
PC: 0x84AB1D40
Access Violation: read at 0x0000000270000000
```

The identical failure for a team-only edit and a player-only edit rules out one
specific user string or one identity field family as the primary cause. The
common changed component is the rebuilt `roster/ROST` resource and its
H7A/IFF transport.

## What the experiment does and does not prove

It proves:

- the clean source and emulator path boot;
- a single legal same-allocation team-name edit is sufficient to trigger the
  failure;
- a single legal same-allocation player-name edit triggers the same failure;
- the source file is not modified and every copied build remains independently
  reproducible and revertible; and
- the failure occurs before the edited name could be visually checked.

It does **not** yet prove whether the defect is in H7A encoding compatibility,
IFF reconstruction, runtime relocation, a checksum/integrity field not modeled
by the offline parser, or a writer assumption shared by all changed builds.
Passing the project's own H7A decoder is insufficient evidence because a
self-consistent encoder/decoder pair can still disagree with the retail
decoder.

## Best next experiment

Instrument the guest execution around `0x84AB1D40` in an instrumented Xenia
build or a native Windows debugger and record the object/pointer chain that
produces `0x0000000270000000`. In parallel, compare the retail decoder's output
for one rebuilt block against the project's decoded body, rather than adding
more offline round trips. If the rebuilt H7A stream decodes differently in the
retail consumer, replace the encoder or implement a runtime-compatible literal
stream. If the decoded body agrees, trace the post-load relocation/integrity
owner before changing the writer again.

## Rollback receipt

The temporary private launcher was restored byte-for-byte to SHA-256
`724708e07c90fe49a90a5b3005aa5648053c2ad3effe4c84e6397eb483bd46aa`.
The persistent Xenia configuration retained the pinned hash above, no Xenia or
controller process remained, and `control.fifo` was absent after the experiment.

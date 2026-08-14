# Camera map — NFL 2K5 and APF 2K8

Status: research map. Nothing here is a runtime claim; no game was launched, no
emulator driven, no patch applied. Every address below was read from a binary.

**This document has a machine-readable companion.**
`tools/camera_options_audit.py` re-derives the whole surface from the two
executables — every row, label, kind, callback, decoded bound constant, preset
name and preset parameter block — into
`reports/gameplay_tuning/camera_options_audit.json`. The read-only public
projection is `mod_editor/core/camera_inspection.py`, reachable as:

```
python3 -m mod_editor --inspect-camera-options nfl2k5
python3 -m mod_editor --inspect-camera-options apf2k8
```

`tools/validate_camera_options_audit.sh` regenerates the audit, requires byte
identity with the checked-in report, and asserts that the projection publishes
no raw address and offers no writer. Prefer the audit over this prose when the
two disagree: the audit is derived, this is written.

Pinned inputs. NFL 2K5 `default.xbe` sha256
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`
(11,948,032 bytes). APF 2K8 decompressed executable sha256
`cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf`
(54,001,664 bytes), `file_offset = VA - 0x82000000`. **If your file hashes
differ, none of these addresses apply to it.**

2K5 section deltas (`tools/xbe_info.py`); the `.text` −0x10000 shortcut is wrong
for every UI string in this game:

| section | VA | raw | delta |
| --- | --- | --- | --- |
| `.text` | 0x00011000 | 0x00001000 | 0x10000 |
| `.rdata` | 0x004E3AE0 | 0x004D9000 | 0xAAE0 |
| `.data` | 0x00A69980 | 0x00A5F000 | 0xA980 |
| `.string_` | 0x00E60320 | 0x00AEF000 | 0x371320 |

`.data` has vsize 0x3F6988 against rawSize 0x8F95C, so the live camera globals
sit in the zero-init tail and hold **no value in the file** — the executable
carries only defaults, ranges and the menu table.

## The verdict

**Partially proved with a named boundary, on both products.** The map is proved;
the *writer* is blocked, and it is blocked by the same thing the 21 gameplay
sliders hit. Split by goal:

| | map | writer |
| --- | --- | --- |
| 2K5 — edit what the menu exposes | **proved** | blocked on one cryptographic question (T1) |
| 2K5 — new presets | partially proved (hybrid data+code) | same block |
| APF — edit what the menu exposes | **proved**, and richer than 2K5 | blocked harder: **no user-writable carrier exists at all** |
| APF — new presets | partially proved; holds the cheapest win | same block |

## NFL 2K5 — the menu

Reached from Options → `Camera Selection` (row base `0x005036C0`, label
`0x00E7E038`, submenu pointer `0x0052B8A0`). Row table **`0x0052B700`**, stride
`0x34`, 7 rows then a kind-3 terminator at `0x0052B86C`. Layout is byte-identical
to the proved 21-slider table at `0x00501F20`: `+0x00` kind, `+0x04` label ptr,
`+0x08` submenu ptr, `+0x0C` MAX, `+0x10` MIN, `+0x14` CURRENT, `+0x18` INC,
`+0x1C` DEC, and for enum rows `+0x20` label lookup, `+0x24` label-width.

**The on-disk callback order is MAX, MIN, CURRENT, INC, DEC** — not the
current/increment/decrement/maximum/minimum order used elsewhere in prose.

| # | Row VA | Kind | Label | Global | Range | Step | Notches | Default |
| ---: | --- | --- | --- | --- | --- | --- | ---: | --- |
| 0 | 0x0052B700 | 7 enum | Camera | 0x00E5FFF0 | 0..5 | wrap | 6 | 0 Standard |
| 1 | 0x0052B734 | 5 bool | QB Pivot Mode | 0x00E5FFF4 | 0..1 | toggle | 2 | 1 On |
| 2 | 0x0052B768 | 5 bool | Runner Pivot Mode | 0x00E5FFF8 | 0..1 | toggle | 2 | 0 Off |
| 3 | 0x0052B79C | 5 bool | Pass Play Zoom Out | 0x00E5FFFC | 0..1 | toggle | 2 | 0 Off |
| 4 | 0x0052B7D0 | 4 float | Camera Distance | 0x00E60000 | 0.2 .. 3.0 | 0.07 | 40 | 1.0 |
| 5 | 0x0052B804 | 4 float | Camera Angle | 0x00E60004 | 0.0 .. 1.0 | 0.025 | 40 | 0.5 |
| 6 | 0x0052B838 | 4 float | Camera Height | 0x00E60008 | 50.0 .. 300.0 | 6.25 | 40 | 100.0 |

**Distance is a dimensionless multiplier; Height is absolute world units; only
Angle is normalised.** A UI that renders Height as a 0–1 slider is wrong.
Defaults are written by the factory initialiser `FUN_000e3b90`
(`0x000E3B90`–`0x000E3DB7`).

Bound constants: `0x004E6C58`=0.2, `0x004E6D4C`=3.0, `0x004E4180`=0.0,
`0x004E419C`=1.0, `0x004E72A4`=50.0, `0x004E4188`=300.0. Camera-private step and
threshold constants: `0x0052B8CC`=0.07, `0x0052B8D0`=2.93, `0x0052B8D4`=0.27,
`0x0052B8D8`=6.25, `0x0052B8DC`=293.75, `0x0052B8E0`=56.25, `0x0052B8E4`=0.0555556.
Arithmetic self-check: (3.0−0.2)/0.07 = 40 and (300−50)/6.25 = 40, exactly.

### There are exactly six presets, and the extra names are a different enum

Label table **`0x004F25BC`**, six entries, ending at `0x004F25D0`:
`Standard, Far, Side, Iso, Blimp, Custom`.

`.rdata` here is a run of adjacent enum label tables, each ending in a `Custom`
entry pointing at the same string `0x00E6990C`. Walking the run proves the
boundary and refutes the tempting misreading:

```
0x004F25A8  Rookie Pro "All Pro" Legend Custom          <- Difficulty (5)
0x004F25BC  Standard Far Side Iso Blimp Custom          <- CAMERA (6)
0x004F25D4  "1st Person" Broadcast Realistic Quick
            Default "TV Broadcast" "In Stands"
            "On Field" Custom                           <- a DIFFERENT enum,
                                                           almost certainly the
                                                           replay camera
0x004F25F8  On Off
```

So `1st Person` and `Broadcast` are **not** hidden gameplay-camera presets, and
must not be described as unlockable. Consistent with that, the MAX callback
`0x002C66A0` is `mov eax,5; ret` and the label-width helper `0x002C66D0` does
`push 5`. The label lookup `0x002C66C0` is unbounded
(`mov eax,[0x00E5FFF0]; mov eax,[eax*4+0x004F25BC]; ret`), which is what makes
the adjacency misleading.

### Preset data is a hybrid — part table, part code

Level 1 at `0x004F03F8`: 8 modes × 29 situations × 8 bytes `{u32 flags; CamDesc*}`,
indexed `mode*0x1D + situation` (proved from code at `0x000A56A2`, not from a
data pattern). Level 2: `0x50`-byte descriptors based at `0x00A87F10` carrying
position, an FOV-like field, an aim vector, **and an update function pointer at
descriptor+0x40**.

| Preset | Descriptor VA | raw | kind | position | +0x20 | update fn |
| --- | --- | --- | ---: | --- | ---: | --- |
| Standard | 0x00A88A00 | 0xA7E080 | 2 | (0, 100, −150) | 35 | 0x000A4990 |
| Far | 0x00A88D20 | 0xA7E3A0 | 2 | (0, 100, −150) | 28 | 0x000A4BC0 |
| Side | 0x00A89090 | 0xA7E710 | 2 | (−350, 40, 250) | 35 | 0x000A4DC0 |
| Iso | 0x00A88F00 | 0xA7E580 | 2 | (100, 0, 0) | 50 | 0x000A4D90 |
| Blimp | 0x00A87F60 | 0xA7D5E0 | 2 | (0, 0, 400) | 40 | 0x000A4080 |
| Custom | 0x00A893B0 | 0xA7EA30 | 2 | (0, 100, −150) | 35 | 0x000A6A30 |

A preset that **reuses an existing update function is pure data**; one needing
new motion is code inside a signed binary. Modes 6 and 7 exist with full
29-situation columns and their own update functions (`0x000A4E00`, `0x000A4E60`,
`0x000A4610`); the mode gate `0x000A5490` defaults `ebx=7` and only reads the
user's selection when exactly one human controller is present, so they read as
multiplayer/special modes, **not** hidden presets. Not proved — see T5.

`+0x20` is FOV-*like* and is **not** proved to be FOV. It lands at `camera+0x410`
after the `0x50`-byte memcpy by `0x00060090`, and `0x00088597` does
`fld [eax+0x410]; fadd [0x004E6C6C](=200.0); fstp [eax+0x410]`, which reads oddly
for degrees.

### The Custom gate, and the solver

The three float settings only move the camera while `Camera` is set to **Custom**
(index 5), and conversely nudging any of them force-writes Custom into the
selection. That is shipped behaviour, not a tool limitation.

The polar transform, evaluable offline for any triple including out-of-range
values:

```
theta_bam = 32768.0 - Angle * 16201.0        ; [0x004E5C80]=32768, [0x004F0D80]=16201
offset.x  = sin(theta_bam)          * Distance * L
offset.z  = sin(theta_bam + 0x4000) * Distance * L   ; +quarter turn = cos
eye.y     = Height                                    ; copied verbatim to camera+0x404
```

Sine LUT base `0x004E53E8`, slope `0x004E53EC`, stride 8, index `(bam>>8)*8`.
In degrees: **Angle 0 = 180.0°, Angle 0.5 = 135.5°, Angle 1 = 91.0°** — an 89°
arc. Two functions compute this from the same globals and LUT: `FUN_002c6800`
(`0x002C6800`–`0x002C6957`, menu side, emits to `0x00C8DEF0`) and `0x000A6A30`
(the per-frame update fn on mode-5 descriptors, writing the camera array at
`0x00A82940`). Do not say "the camera solver" in the singular until T6 closes.

### Where the values live

The 736-byte settings payload is a flat image of `.data 0x00E5FF80..0x00E6025F`,
so `save_offset = global_VA − 0x00E5FF80`:

| field | SAVEGAME.DAT offset |
| --- | --- |
| preset index | 0x70 |
| QB Pivot Mode | 0x74 |
| Runner Pivot Mode | 0x78 |
| Pass Play Zoom Out | 0x7C |
| Camera Distance (f32) | 0x80 |
| Camera Angle (f32) | 0x84 |
| Camera Height (f32) | 0x88 |

Only `STG` (Settings) and `FXG` (Franchise) carry them; `USR` and `TMM` do not,
and **each franchise carries its own copy**. Fixture:
`~/.var/app/app.xemu.xemu/data/xemu/xemu/xbox_hdd.qcow2`, FATX partition E,
title `53450030`, containers `Settings1` `83C3760943CB` and `Franchise1`
`256B40374FD6`.

## APF 2K8 — the menu

Descriptor `0x820DD190` (title `Camera Selection` `0x845FA000`, name `CameraMenu`
`0x845FA024`), row table **`0x84E40940`**, stride `0x60`, 9 rows — richer than
2K5, including a fourth axis 2K5 lacks and separate Home/Away toggles. The camera
globals sit immediately after the 21 slider globals in the same settings struct
(base `0x84F3F8F8`, materialised as `lis rX,0x84F4; addi rX,rX,-0x708`).

| # | Row VA | Kind | Label | Global | Range | Step | Default |
| ---: | --- | ---: | --- | --- | --- | --- | --- |
| 0 | 0x84E40940 | 7 | Camera | 0x84F3F9F0 | 0..4 | wrap | 0 |
| 1 | 0x84E409A0 | 5 | QB Pivot Mode (Home) | 0x84F3F9F4 | 0..1 | toggle | 1 |
| 2 | 0x84E40A00 | 5 | Pass Play Zoom Out (Home) | 0x84F3FA00 | 0..1 | toggle | 0 |
| 3 | 0x84E40A60 | 5 | QB Pivot Mode (Away) | 0x84F3FA04 | 0..1 | toggle | 1 |
| 4 | 0x84E40AC0 | 5 | Pass Play Zoom Out (Away) | 0x84F3FA0C | 0..1 | toggle | 0 |
| 5 | 0x84E40B20 | 4 | Camera Distance | 0x84F3FA10 | 500 .. 2500 | 40.0 | 1350.0 |
| 6 | 0x84E40B80 | 4 | **Camera Pitch** | 0x84F3FA14 | 0.0 .. 1.0 | 0.025 | 0.2 |
| 7 | 0x84E40BE0 | 4 | Camera Angle | 0x84F3FA18 | 0.0 .. 1.0 | 0.025 | 0.5 |
| 8 | 0x84E40C40 | 4 | Camera Height | 0x84F3FA1C | 50 .. 500 | 9.0 | 50.0 |

Defaults from `Function_849FDEB0`. Bound constants `0x8200116C`=500.0 — which is
simultaneously **Distance-MIN and Height-MAX** — `0x82001174`=2500.0,
`0x82001210`=50.0, `0x820009A0`=0.0, `0x820009A4`=1.0; steps `0x82008574`=40.0,
`0x820AD0CC`=9.0, `0x820B4518`=0.025. The four float rows are grey-out gated on
`Camera Selection == 4` (Custom) by the shared callback at row+0x38 = `0x84A15470`.

### Blimp is a real authored preset the menu cannot reach

Name array **`0x820D9FA0`**, ten entries:
`Standard, Far, Side, Iso, Custom, Blimp, Broadcast, Realistic, Quick, Default`.
Menu exposes 0..4. Preset geometry at **`0x84E11E00`**, stride `0x440`, 17
situation slots of `0x40` — and unlike 2K5 there is **no function pointer in the
slot**, so APF preset geometry is pure data.

| idx | Name | Block VA | slot-0 eye | authored? |
| ---: | --- | --- | --- | --- |
| 0 | Standard | 0x84E11E00 | (0, 500, −1325) | yes, 17/17 slots |
| 1 | Far | 0x84E12240 | (0, 500, −1325) | yes, 17/17 |
| 2 | Side | 0x84E12680 | (1400, 900, 0) | yes, 17/17 |
| 3 | Iso | 0x84E12AC0 | (600, 350, −950) | yes, 17/17 |
| 4 | Custom | 0x84E12F00 | (0, 500, −1325) | runtime scratch |
| 5 | **Blimp** | 0x84E13340 | **(0, 3750, −20)** | **yes, 17/17 — unreachable** |
| 6 | Broadcast | 0x84E13780 | (0, 0, 0) | populated but zero geometry |
| 7 | Realistic | — | (0, 0, 0) | partial, 11/17 slots |
| 8 | Quick | — | — | empty stub |
| 9 | Default | — | — | empty stub |

Blimp's geometry — a camera 3,750 units up looking down at the field —
semantically matches its own name, which is the cross-check the 2K5 adjacency
never had. It is unreachable only because three immediates hard-code the bound,
and none of them reads `maximum()`:

```
0x84A15D00  2f0b0003   cmpwi cr6, r11, 3     ; increment bound
0x84A15D5C  38600004   li    r3, 4           ; decrement wrap
0x84A15540  38600004   li    r3, 4           ; maximum()
```

Full increment prologue, for re-derivation:

```
0x84A15CF0  3D6084F4  lis   r11, 0x84F4
0x84A15CF8  3BEBF8F8  addi  r31, r11, -1800   ; r31 = 0x84F3F8F8 settings base
0x84A15CFC  817F00F8  lwz   r11, 0xF8(r31)    ; = 0x84F3F9F0 camera selection
0x84A15D00  2F0B0003  cmpwi cr6, r11, 3
0x84A15D04  41990008  bgt   cr6, +8
```

**Safe unlock ceiling is index 5 (Blimp).** Index 6 has zero geometry, 7 is
partial, 8 and 9 are name-only. Do not expose 7–9.

### APF has no camera save carrier

An exhaustive scan of the 54 MB image finds no serializer. The slider exporter
`0x8470A578` and importer `0x8470A630` handle exactly 84 bytes
(`0x84F3F99C`–`0x84F3F9EC`) and **stop one dword short of `0x84F3F9F0`**. The
setter bank `0x849FC8F0`–`0x849FC9A8` has zero callers. The only bulk movement is
an in-RAM snapshot/restore pair (`0x84A15B58` / `0x84A15C20`). There is no camera
file to edit; the only route is a XEX patch.

## What is out of reach

- **Re-signing the 2K5 XBE.** Every camera patch site is in a digested section —
  `.text` `72edb599…`, `.rdata` `167a8c58…`, `.data` `8c86ae03…`. All 22 digests
  currently match.
- **Rebuilding the APF XEX** — normal_lzx + normal_aes, 824 page descriptors.
- **Any archive-only camera mod. Refuted, not merely unproved.** Exhaustive decode
  and search of both asset corpora: every SCNE camera node — 3,744 records across
  1,076 2K5 scenes, 730 across 519 APF files — belongs to intro, cutscene, UI or
  asset-preview scenes. **Zero stadium scenes contain a camera node in either
  game.** The strings "Camera Distance" and "Camera Angle" appear in the archives
  exactly once each, in a manual resource (2K5 `MANU` outer 109; APF `MANU` outer
  499 inner 8 `xenon-3`). Anyone shipping an archive-only camera claim will have
  to withdraw it.
- **A truly unlimited 2K5 range.** Each bound is enforced in three places (MIN/MAX
  operand, inc/dec threshold, clamp immediate) plus two runtime layers: the
  per-camera clamp box written by `0x000A6A30` (`camera+0x3A0`=−2600,
  `+0x3B0`=+2600, `+0x3A8`=−5800, `+0x3B8`=+5800, `+0x3D4`=5000) and an absolute
  floor `eye.y >= 20.0` at `0x00060043`. Five layers, three outside the menu.

### The trap that would corrupt the title

**Never edit a bound constant in place; repoint the instruction operand.** These
are pooled compiler literals: 2K5 `0x004E4180` (0.0) has **4,525** references,
`0x004E419C` (1.0) 1,461, `0x004E6C58` 161, `0x004E6D4C` 125, `0x004E72A4` 65,
`0x004E4188` 49. APF `0x820009A0` 4,366, `0x820009A4` 2,862 — and `0x8200116C`
serves as both Camera Distance's minimum and Camera Height's maximum.

2K5 private operand sites (raw): Distance MAX `0x2B66F2`, MIN `0x2B66E2`; Angle
MAX `0x2B6722`, MIN `0x2B6712`; Height MAX `0x2B6752`, MIN `0x2B6742`; inc/dec
thresholds and clamp immediates at `0x2B6B89`/`0x2B6BA0`, `0x2B6C09`/`0x2B6C20`,
`0x2B6C89`/`0x2B6CA0`, `0x2B6D09`/`0x2B6D39`, `0x2B6D89`/`0x2B6DA0`,
`0x2B6E09`/`0x2B6E20`. APF displacement sites: `0x2A15594`, `0x2A155A4`,
`0x2A15DD8`, `0x2A15DE8`, `0x2A15E78`, `0x2A15E88`, `0x2A15624`, `0x2A15634`,
`0x2A16188`, `0x2A16198`, `0x2A16228`, `0x2A16238`.

## Open questions

| ID | Question | The exact proof |
| --- | --- | --- |
| T1 | **Is the 2K5 `EXTRA` signature roamable?** This is the gate for any writer. | `XCalculateSignature(flags=0)` skips `XboxHDKey` (`0x0001FBD2`), so the key is `XboxSignatureKey` and is in principle console-independent. Produce the same 736-byte `SAVEGAME.DAT` on two consoles/xemu instances and compare the two `EXTRA` blobs. Identical → a writer is possible. Different → **no offline 2K5 camera writer will ever ship.** |
| T2 | Does the load path re-clamp camera values? | The save provably *contains* non-default values. Trace the deserializer from `container_filename_dispatch 0x0004B1F0` back to its buffer producer; an xref on `0x00E5FF80` fails (400+ generic sites). If the loader is a flat copy, out-of-range values survive **without patching the executable at all**. |
| T3 | Write-direction delta | Two `Settings1` containers identical but for Distance at min vs max; the diff must show exactly `0x80` changed, plus `EXTRA`. |
| T4 | Reconcile the two preset accessors | `FUN_000a5610` (`imul ecx,0xE8; mov eax,[ecx+0x004F047C]`) vs the situation-indexed `imul eax,0x1D; mov edx,[eax*8+0x004F03FC]`. They reconcile: `0x004F047C − 0x004F03FC = 0x80 = 16*8`, so `FUN_000a5610(mode)` returns **situation 16**. Confirm no caller passes a situation. Until then an editor must not call `0x004F047C` "the preset table". |
| T5 | Are 2K5 modes 6 and 7 multiplayer modes? | Decode the controller-count branch at `0x000A5490` fully. Closing this prevents someone shipping "two hidden 2K5 presets". |
| T6 | Two solvers, one formula | Confirm `FUN_002c6800`'s two callers are both menu paths and that `0x00C8DEF0` is not the gameplay camera array. |
| T7 | Is descriptor `+0x20` FOV? | Trace `camera+0x410` into `viewObj+0x270`, which `FUN_00066A60` reads as the FOV input. APF's analogue (`block+0x30`, read by `0x84970008`) is cleaner but is a different game. |
| T8 | APF view-matrix builder | Not found. `0x8496D000`–`0x84971400` is absent from the Ghidra corpus. Disassemble `0x84970630`–`0x84970E80` and follow the `bl` targets to the VMX cross-product/normalise pair. |
| T9 | Does an APF settings carrier exist outside the image? | The negative is exhaustive **for the executable**: 47 access sites to `0x84F3F9F0..0x84F3FA1F`, all accounted for, none within ±16 instructions of a `bl` to memcpy `0x84B45CE8`. Needs one APF non-roster container from `Content\<XUID>\4541xxxx\`. |
| T11 | Curve data may override matrices | 2K5 `aux_14` bindings point at each camera record's matrix bytes in 1,075/1,075 camera-bearing scenes. **All 279 APF `intro_cameras` matrices are exact identity — the pose exists only in curve data.** Until one `CurveAnim` channel is decoded, "edit the matrix" is a no-op on APF and may be overwritten on frame 1 on 2K5. |

## Honesty boundary

Nothing here was observed running. "The bytes say the camera would move" is not
"the camera moved". Any UI built on this map must say so, must not describe
`1st Person`/`Broadcast` as unlockable 2K5 presets, must not present Camera
Height as a 0–1 slider, and must not claim an archive-only camera mod is
possible.

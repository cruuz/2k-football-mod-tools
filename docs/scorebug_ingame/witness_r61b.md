# Scorebug r61b — first emulator witness (xemu)

Beta 61 (`cf349b7`) ships the runtime scorebug marked EXPERIMENTAL / UNWITNESSED.
I ran both the v7 and runtime builds in xemu. Here is what actually happened.

Short version: **v7 boots and plays. Runtime hangs on entry to a game.** Both
builds were made from the same retail source with the same toolchain, and the
only difference between them is the `scorebug_runtime` flag, so the hang is
isolated to the runtime layer (hooks + appended resources + native
registration), not the shared SCNE refit or placement patch.

---

## Environment

| | |
|---|---|
| Toolset | `cf349b7` (Beta 61 / RC85), merged clean into my fork |
| Emulator | xemu (please tell me if you want the exact build string) |
| Host | macOS, Apple silicon |
| Python | 3.12 venv (Apple CLT 3.9 still dies on `from datetime import UTC`) |
| Source ISO | USA retail, `default.xbe`-identified, **6,300,958,720 bytes** |

Note on the source: my rip is 458,752 bytes larger than
`modpack.RETAIL_XISO_SIZE` (6,300,499,968). `Nfl2k5SourceCache.index()` accepts
it — every extracted pack hashes to its pinned value, and the inventory hash
matches — but `tools/build_softdrink_modpacks60.py` refuses it with "Proof
requires the pinned retail XISO" because it still gates on whole-file
size/SHA-256. That is correct for a release-proof script; flagging only because
it means the modpack builder is unusable for anyone whose dump is padded
differently, even though the source cache deliberately tolerates exactly that
case. I built via `mod_build.build()` directly instead.

---

## Build A — v7 static (`scorebug=True`)

**Result: boots, enters a game, renders, plays. No hang.**

Screenshot attached (TB @ NE, 4:3). Working: bar is at bottom, red "1st & 10"
pill renders, both scores render, three timeout dashes per side, possession
team abbreviation is yellow. Neutral grey panels with no team logos, which is
what v7 is supposed to be.

**One issue: the bar is oversized and clipped at the bottom edge.** It occupies
roughly the bottom sixth of the frame and runs nearly the full width. Compared
against `docs/scorebug_ingame/target_NO_MIA.png` (also 4:3), where the bar is
compact, centered, and clear of the bottom edge, mine is substantially larger
and pushed down far enough that the clock strip that should sit under the
scores is not visible at all.

This is not an emulator display setting on my end — no overscan or scaling
adjustment is applied in xemu; this is the default output. So the oversize and
the bottom clipping look like a real placement/scale finding in the v7 build
rather than an artifact of how I am viewing it.

Relevant XBE fields from the receipt, in case the root position is the culprit:

```
0x10a40  reserved position floats  73f7d373e3f7430f -> 0000a0430000d443
0xfcffc  root x                    d805586d4e00     -> d805400a0100
0xfd07b  root x                    d80568694f00     -> d805400a0100
0xfd0eb  root x                    d805586d4e00     -> d805400a0100
0xfd15e  root y                    d8051c0f4f00     -> d805440a0100
```

The two reserved floats decode to 320.0 and 424.0, which for a 640x480 frame
puts the root at horizontal centre and y=424 — 56 pixels from the bottom. That
would explain a bar sitting lower than the reference render, though it does not
by itself account for the apparent size difference.

---

## Build B — runtime (`scorebug_runtime=True`)

**Result: hangs on entry to a game.** Audio loops continuously; the image is
frozen. Front end is fine; the hang is at the transition into gameplay, which is
where the setup hook at `0xfce56` fires and the scorebug scene initializes.
Retried per the known two-launch quirk; the hang persisted.

The build itself reported clean. From the receipt:

```
scorebug_runtime            applied
scorebug_xbe                applied
scorebug_runtime_resources  applied
scorebug                    foreign     <- expected in runtime mode
```

Resources:

```
version           scorebug-runtime-v1
growth            1,393,920 (sector-aligned 1,394,688)
outer 346         2,977,184 -> 4,371,104
pack 0            193,710,080 -> 195,104,768
resources         264 wrappers, 5,280 bytes each, all present in the receipt
scene_sha256      7db6d6ccb522fb2822cff3a188522afaf10cc0db296e187a9d65edd325bdca8e
atlas_sha256      72aee2c09b471c6f07e3658c00ef6f204021f3f6065cd96344c7c72d30df9947
appendix_sha256   5f56ff615439fa8d1f87a833393f29e565873250f523c31134e6f2fae4004c49
```

XBE, both hooks landed exactly as documented:

```
setup   0xfce56  e845f3ffff -> e865d43b01
update  0xfcfa2  e819faffff -> e84bd43b01
code_va 0x14ba2c0 (1408 bytes)   data_va 0x14bb000 (128 bytes)
changed_bytes 1454
xbe sha256  ce4633c6... -> 888f5d41...
```

Output image grew ~207 MB overall (6,300,958,720 -> 6,508,093,440) because pack
0 and `default.xbe` are both relocated to the tail rather than rewritten in
place. Full receipt JSON available on request.

---

## What this narrows down

Both builds share the SCNE refit and the placement/XBE field patches. v7 runs
those and is stable. The runtime build adds, and only adds:

1. the two call-site hooks (`0xfce56`, `0xfcfa2`) into owned code at `0x14ba2c0`
2. 264 appended TXTR wrappers in outer 346
3. the native registration/relocation path
   (`0x43E30 -> 0x43D20 -> 0x44DA0 -> 0x34DF0 -> 0x34C10`)
4. the name lookup hook (`0x449E0 -> 0x443D0 -> 0x30C40`) resolving
   `hscore_buga` / `zscore_buga`

The hang is somewhere in that set. Your own report already scopes the likely
area: asynchronous I/O, allocation lifetime and GPU consumption were not
executed end to end, and memory pressure was explicitly left unwitnessed. 1.39 MB
of extra resident texture on a 64 MB console through a loader path that had
never been run live is the obvious first suspect, but a stall in the collection
reader walking past the old end offset would look identical from the outside.

## What I can run next

Happy to do any of these — I have the source, the toolchain, and a reproducible
hang:

- exact xemu version and any log/console output it produces at the hang
- confirm whether the hang is mode-dependent (exhibition vs franchise)
- shoot the v7 bar at other render resolutions / aspect settings if you want to
  see whether the clipping tracks the output mode
- build with `--keep-drop-animation` or any flag combination you want compared
- bisect resource count if the compiler can emit a reduced set (e.g. neutral
  variants only, or a single team pair) — that would separate memory pressure
  from the registration path quickly

I do not have a Ghidra project set up for 2K5 (`ghidra_projects/`,
`tools/vendor/`, `research/` are all gitignored, so nothing came down with the
clone), so I cannot run traces on my end without doing that setup first. Tell me
if it is worth it and I will.

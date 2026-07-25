# Beta Release Notes

> **Superseded.** This file describes **Beta 1** and is kept as a record. Beta 1
> was Linux-first, so its platform notes below no longer describe the current
> tools. The current release is
> [**Beta 2**](https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-2),
> which runs on Windows, macOS and Linux; its notes live on that release page.

**Release:** Beta 1
**Date:** 2026-07-22
**Tools included:**
- **2K5 Mod Studio** — ESPN NFL 2K5 (original Xbox) — `v1.0-RC29`
- **APF 2K8 Mod Studio** — All-Pro Football 2K8 (Xbox 360) — `v0.1.0-alpha.34`

This is the first public beta of both editors. They are functional, retail-free,
and Linux-first. Read the [README](README.md) for install/usage and the
[license](LICENSE) for terms.

---

## What's in this beta

### 2K5 Mod Studio (v1.0-RC29)
- Unified visual mod project: uniforms/Complete Team Kit, portraits, live faces,
  create-team field art, scorebug/presentation art, Team Select cards.
- Stadium Studio: 477 scenes, 23,838 editable P8 textures, with a
  **"People & sideline only"** filter (fans, cheerleaders, coaches, officials,
  chain crew, camera/media, ushers, sideline props).
- Audio: all 850 standalone cues + all 53,571 playable streaming ranges
  (exact-slot), with cue labels/notes.
- Rosters: primary players (names + jersey), historical teams, and
  secondary-pool jersey numbers.
- Text: 20,074 editable strings across 716 banks.
- Project save/load, autosave/crash recovery, build-to-new-XISO, xemu launch.

### APF 2K8 Mod Studio (v0.1.0-alpha.34)
- Uniforms: 96 editable textures (jersey/pants/helmet/shoulder) + `digital_font`
  + `draft_logo`.
- Rosters & Players: team names, player names, all 28 ratings, exact Position,
  53-row roster planner.
- Audio: all 47,775 editable AUDO/AUSB cues (exact-slot XMA1 via a user-supplied
  encoder), cue labels/notes, batch folder/ZIP authoring.
- Field Art inventory, Stadium Studio, presentation inspectors.

---

## Release integrity

Each editor is shipped as a deterministic, byte-for-byte reproducible archive
with an adjacent SHA-256 sidecar:

| Editor | Archive | SHA-256 |
| --- | --- | --- |
| 2K5 Mod Studio v1.0-RC29 | `2K5-Mod-Studio-v1.0-RC29-20260720.tar.gz` | `c1000937cdc47861ce6e1a23c4696c052a0c7bc3cebb1c0279ed9cc1efcdd99d` |
| APF 2K8 Mod Studio v0.1.0-alpha.34 | `apf2k8-mod-studio-0.1.0-alpha.34-linux-x86_64.tar.gz` | `beb8b1409b83e052e6c432a9ddc4a79f9f990820c79e0b67dea894dc869393f4` |

Verify with `sha256sum -c <archive>.sha256` (must say `OK`).

Every archive passes an automated **retail-free gate** (no game bytes, decoded
pixels/audio, private paths, symlinks, or undeclared files) and a
**runtime-closure** check (every shipped module imports from the clean stage).

---

## Known limits (beta)

- **Offline-proved vs runtime-proved.** Most writers are offline-proved
  (copied-image byte-diff verified). A smaller set is also runtime-proved in an
  emulator. The capability registry labels each writer
  (`PROVED` / `READ ONLY` / `PORTME`).
- **Emulator-only executable patches.** Features that patch the game executable
  invalidate the retail signature and run only on the named emulators (xemu /
  Xenia), never original hardware.
- **Not done yet** (tracked in
  [`docs/product/NFL2K5_COMPLETION_STATUS_AND_WALLS.md`](docs/product/NFL2K5_COMPLETION_STATUS_AND_WALLS.md)):
  3D model import (Crib/stadium geometry), whole streaming-bank audio repack and
  per-cue loop/gain/pan/mixer editing, playbook route drawing/import, franchise
  rookie-draft AI variety, Xbox save editing (its saves are signed with a
  platform key; PS2 saves are writable — see below), and uniform
  pixel→body-region UV decoding.
- **Windows / macOS are a preview.** Launchers are now bundled for all three
  platforms and CI runs the suite on all three, but it does not yet pass on
  Windows or macOS and neither GUI has been manually driven. Linux is the
  supported platform. On Windows the bundled `extract-xiso` extractor is a Linux
  binary, so load an already-extracted game folder rather than an ISO.

---

## PlayStation 2 saves (preview)

2K5 Mod Studio can now edit **ESPN NFL 2K5 (PlayStation 2, `SLUS-20919`)
memory-card saves**, via **File → PS2 Save Editor…**. Open a save from a
`.psu`, an extracted save folder, or a `.ps2` card image; rename players with
live feedback on how many characters each slot holds; then write a new `.psu`
that PCSX2, mymc and PS2 Save Builder import. Your original save is never
modified.

The same capability is also available on the command line, and ships
separately as `NFL2K5-PS2-Save-Toolkit` on the Releases page for anyone who
wants it without the GUI (Python 3 only — no PyQt5, no Pillow). Note that the
`v1.0-RC29` and `v0.1.0-alpha.34` archives listed earlier predate all of this
and do not contain it.

Unlike the Xbox release — whose saves carry a platform-keyed signature and stay
read-only here — PS2 save integrity is a recomputable CRC-32, so an offline
writer is safe. Every edit is bounded to the bytes the original occupies and is
checked by an independent verifier (`tools/nfl2k5_ps2_save_verify.py`) that
confirms only the declared ranges changed, the checksum matches, and the roster
arena never moved. The capability is registered `offline-writer-proved`; an
in-game reload witness is the next step.

See [`docs/product/NFL2K5_PS2_SAVE_PIPELINE.md`](docs/product/NFL2K5_PS2_SAVE_PIPELINE.md)
for the approach, the already-proven Madden/NCAA PS2 save pipeline it builds on,
and the custom progression engine that generates historically accurate content
for any season from 2008 through 2026.

---

## How to run a mod

1. Install (extract the archive; `./install.sh` or run the launcher).
2. Load your own clean game ISO (or extracted folder).
3. Browse → Replace editable assets with your own files.
4. Save a project, then **Build** to a new empty folder.
5. Run the built `default.xbe` (xemu) or `default.xex` (Xenia).

See the getting-started guides in [`docs/mod_editor/`](docs/mod_editor/) for the
full walkthrough and the exact, evidence-backed boundary of each feature.

---

## Beta disclaimer

Provided "as is", without warranty. Work-in-progress software for enthusiasts
modding games they legally own. Keep backups of your original game files.

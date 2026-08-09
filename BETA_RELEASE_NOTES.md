# beta-30 — RC57 / alpha.62

**Date:** 2026-08-09

**2K5 Mod Studio:** `v1.0-RC57`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.62`

## Beta 30 fixes

- 2K5 now keeps every validated USA retail container layout on one canonical,
  content-verified private cache. Stadium Studio results and visual, Crib, and
  audio originals no longer become incompatible merely because the selected
  ISO has different wrapper padding or partition placement.
- Private audio fingerprint and containment inventories use that same validated
  game-content identity. Containment parsing uses the size of the container
  that was actually opened, while builds preserve and report that container's
  actual output size.
- The selected source file remains independently guarded for read-only scans,
  session recovery, and building; sharing derived cache data does not weaken
  source-change checks.
- APF alpha.62 revalidates the shipped ISO recognition, extraction, load, and
  read-only source path against a real USA game image. No private source path,
  image hash, or retail payload is included in this release record.
- APF install and uninstall helpers suppress Python bytecode before importing
  the installer, so a fail-closed release audit cannot be dirtied by a new
  `__pycache__` directory.

---

# beta-29 — RC56 / alpha.61

**Date:** 2026-08-09

**2K5 Mod Studio:** `v1.0-RC56`

**APF 2K8 Mod Studio:** `v0.1.0-alpha.61`

> **Beta 29 refresh (2026-08-09):** The assets were rebuilt in place after a
> stale shared updater label made both editors report `beta-22` and offer Beta
> 29 to Beta 29 users. Product versions remain RC56 / alpha.61. If an earlier
> Beta 29 download shows that notice, download the refreshed Beta 29 build.

This beta closes the editor-completion marathon with installable Windows builds
and portable source archives for both products. The changelogs remain the
feature-level source of truth:
[`docs/mod_editor/2k5_mod_studio_changelog.md`](docs/mod_editor/2k5_mod_studio_changelog.md)
and
[`docs/mod_editor/apf2k8_mod_studio_changelog.md`](docs/mod_editor/apf2k8_mod_studio_changelog.md).

## Highlights

- APF `logo_l0` / `logo_l1` format-15 (`4_4_4_4`) preview, PNG export, and the
  existing import/swap writer path are regression-covered; base-only DXN
  NameFont textures no longer decode as gibberish.
- Dialog and drag/drop imports share explicit **Contain / Cover / Stretch**
  fitting, including 2K5 Crib art.
- Equipment colours are taught and applied per physical HOME/AWAY uniform set;
  APF visor remains a per-player Save Players field.
- Blank previews fail closed after 45 seconds with recovery guidance, and
  formerly silent disabled editor actions now stay clickable and explain the
  exact load, selection, size, format, or ownership wall.
- APF Field Art can jump directly to the approximately 118 stock NFL endzone
  family for browse/export; the focused writer remains limited to its six
  offline-proved base slots.
- Playbook browsers annotate the community Ace/Dime/Bear cases. Experimental
  G1 multi-Dime package-map and G2 multi-Ace link-table exports ship as private
  offline packs with independent byte verifiers and honesty sidecars.
- The Windows release allowlist now includes the G1/package-map and formation
  clone modules, closing the staged-build crash path.

## Evidence boundaries

- G1 and G2 exports prove offline bytes only; emulator/gameplay fixes are not
  claimed.
- Freehand routes are not Editable. Stock route copy/swap reuses exact existing
  descriptors.
- APF per-team stock endzone writing, unseen formats/assets, and the G10/G11
  user-input ability gate remain explicit evidence walls in the product ledgers.

## Release integrity

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| `2K5-Mod-Studio-v1.0-RC56-20260809.tar.gz` | 10,985,098 | `7ec2a1916efd8bb2deb47493e18a12035c982d398b2c4e5ec6f26cc1adb75cb9` |
| `2K5-Mod-Studio-1.0-RC56-Setup.exe` | 56,722,195 | `64d783446f0297bbb26ab9c6fa44d5bf10a5e5a1fb49369014d32c28c9c46cc8` |
| `apf2k8-mod-studio-0.1.0-alpha.61-20260809.tar.gz` | 1,651,940 | `34768b81845d8feb6c5ba891be4d8c1a880ea3169312003254aa5081e474bb26` |
| `APF-2K8-Mod-Studio-0.1.0-alpha.61-Setup.exe` | 52,688,569 | `7d5a909d45847f4845814d16239cd981171abd9f48d07a62cf3a97b143bb9388` |

The `.tar.gz.sha256` sidecars are attached with the archives. Windows installers
are self-contained and reproducibly built, but not code-signed; the installer
explains the Windows warning before installation.

## Historical Beta 1 notes

Everything below this heading is retained as an archival record and does not
describe beta-29.

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
- Unified visual mod project: uniforms/Supported Team Kit, portraits, live faces,
  create-team field art, scorebug/presentation art, Team Select cards.
- Stadium Studio: 477 scenes, 23,838 editable P8 textures, with a
  **"People & sideline only"** filter (fans, cheerleaders, coaches, officials,
  chain crew, camera/media, ushers, sideline props).
- Audio: all 850 standalone cues + all 53,571 playable streaming ranges
  (exact-slot), with cue labels/notes.
- Rosters: primary players (names + jersey), historical teams, and jersey plus
  per-player None/Clear/Dark face-shield type for both pools. The face-shield
  selector is not a HOME/AWAY tint; loaded saves may override the disc seed.
- Text: 20,074 editable strings across 716 banks.
- Project save/load, autosave/crash recovery, build-to-new-XISO, xemu launch.

### APF 2K8 Mod Studio (v0.1.0-alpha.34)
- Uniforms: 96 editable textures (jersey/pants/helmet/shoulder) + `digital_font`
  + `draft_logo`.
- Rosters & Players: team names, player names, all 31 ratings, exact Position,
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
  (`Editable`, `Preview`/`Export-only`, `Proof boundary`, or `Research boundary`).
- **Emulator-only executable patches.** Features that patch the game executable
  invalidate the retail signature and run only on the named emulators (xemu /
  Xenia), never original hardware.
- **Still outside the proved boundary** (tracked in
  [`docs/product/NFL2K5_COMPLETION_STATUS_AND_WALLS.md`](docs/product/NFL2K5_COMPLETION_STATUS_AND_WALLS.md)):
  arbitrary/new-topology 3D model import (bounded position-only Stadium and
  Crib imports are available), whole streaming-bank audio repack and per-cue
  loop/gain/pan/mixer editing, freehand playbook route drawing/import (exact
  same-book stock assignment copying is available), franchise
  rookie-draft AI variety, Xbox save editing (its saves are signed with a
  platform key; PS2 saves are writable — see below), and uniform
  pixel→body-region UV decoding.
- **Historical Beta 1 platform note (not current): Windows / macOS were a
  preview.** Launchers were bundled for all three
  platforms and CI runs the suite on all three, but it does not yet pass on
  Windows or macOS and neither GUI has been manually driven. Linux is the
  supported platform. On Windows the bundled `extract-xiso` extractor is a Linux
  binary, so load an already-extracted game folder rather than an ISO.

---

## PlayStation 2 saves (preview — separate download)

**This is not part of the two archives above.** PS2 save support ships as its
own command-line package, `NFL2K5-PS2-Save-Toolkit`, on the Releases page. The
`v1.0-RC29` and `v0.1.0-alpha.34` archives listed earlier predate it and do not
contain it. The graphical editors do not expose PS2 saves yet.

The toolkit reads an **ESPN NFL 2K5 (PlayStation 2, `SLUS-20919`) memory-card
save** from a `.psu`, an extracted save folder, or a `.ps2` card image; applies
fixed-allocation roster name edits inside its `ROST` arena; reseals the CRC-32
integrity field; and writes a `.psu` that PCSX2, mymc and PS2 Save Builder
import. It needs only Python 3 — no PyQt5, no Pillow.

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

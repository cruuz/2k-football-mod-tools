# 2K Football Mod Tools

> **Beta.** Two retail-free mod editors — Windows, macOS and Linux — for classic
> 2K football games:
> **ESPN NFL 2K5** (original Xbox) and **All-Pro Football 2K8** (Xbox 360).
> Bring your own legally dumped game disc — the editors ship **no game data**.

These tools let you browse a decoded catalog of your game's assets and replace
the ones with a proven, independently verified write path — uniforms, portraits,
team art, scorebug graphics, stadium textures (including **fans, cheerleaders,
coaches, officials, chain crew, camera, and sideline props**), rosters, text,
and audio — then build a modded copy you can run in an emulator.

---

## The two editors

### 2K5 Mod Studio — ESPN NFL 2K5 (original Xbox)
- **Supported Team Kit** — 39 writable components per physical set (jersey,
  sleeve, pants, both helmet families, digits 0–9, nameplate, Team Select
  cards), HOME/AWAY, with GIMP folder/ZIP round-trip. All **28,530**
  package-local socks, elbow pads, gloves, long sleeves, shoes, and wristbands
  are separately searchable, previewable, exportable, and palette-editable
  through fixed-span TSET imports that preserve their shared retail shape and
  every unselected sibling.
- **All Textures** — 11,395 editable standalone targets, including every
  uniform-package presentation texture, all 1,585 raw menu-logo/mini-card
  slots, all 170 franchise-office and draft/PDA logo surfaces, and all 4,080
  reviewed player strips. The franchise-office set is editable as presentation
  art — its in-game home is the franchise/coach-desk screen, not midfield. Raw
  menu arrays preserve their complete fixed-slot structure and never invoke
  VC-LZ.
- **Stadium Studio** — 477 scenes, 23,838 editable P8 texture occurrences, with
  a **"People & sideline only"** filter to isolate fans, cheerleaders, coaches,
  officials, chain crew, camera/media, ushers, and sideline props. The proved
  full scene can also round-trip same-topology vertex-position edits through
  glTF while preserving game UV/material/collision and other stream bytes.
- **Audio** — all 850 standalone cues and all 53,571 playable streaming ranges
  (exact-slot replacement), with project-backed cue labels/notes.
- **Rosters** — current primary players (names + jersey numbers) and historical
  teams; jersey numbers plus per-player None/Clear/Dark face-shield type for
  both player pools via the generalized disc-roster writer. Face shield is not
  a HOME/AWAY tint, and loaded saves may override the disc seed.
- **Text** — 20,074 editable strings across 716 banks.
- Portraits, live faces, create-team field art, scorebug/presentation art.
- Runs in **xemu**.

### APF 2K8 Mod Studio — All-Pro Football 2K8 (Xbox 360)
- **Uniforms** — 96 editable textures (jersey/pants/helmet/shoulder) plus the
  shared `digital_font` and `draft_logo`.
- **Team crests** — all 118 `uniform_logo` packages; one staged crest is
  mirrored into `logo_l0` and `logo_l1`, both mip chains are regenerated, and
  the matching logo-cache entry is independently verified. The fixed
  `front_crown_to_rear_v1` profile bakes one semantic side canvas bilaterally
  into the exact retail high/low helmet-shell atlas, routes the shell to the
  existing crest material, and neutralizes the bounded overlay. Because that
  route is shared, all 118 packages must fit and reparse in memory first: the
  selected l0/l1 receive the shell atlas, every other retail l0/l1 is migrated
  at its existing physical side-logo placement with RGBA values preserved, and
  only the selected menu cache receives the undistorted semantic design.
  Full-shell designs carry an opaque shell body (alpha 255 on zero-RGB
  texels) so the routed shell renders solid in game; the retail 8/15 crest
  transport sentinel remains legal only in the bounded side-decal lane. One
  copied `0A` is created after every gate passes. No Xenia patch or
  `default.xex` edit is produced; gameplay and hardware behavior remain unproved.
- **Rosters & Players** — team display names, player names, all 31 base ratings
  per player, exact Position, and a 53-row roster planner. A paired 1,344-row
  RPCS3/Xenia stock-roster audit has zero unexplained rows after exact platform
  color-byte normalization.
- **Playbook assignments** — choose existing offensive and defensive books for
  all 40 team slots in a new, verified raw save; signed CON files are
  a verified raw handoff. The on-disc **Assignment Routes** editor can also copy
  or atomically swap an exact stock player-assignment descriptor and existing
  chain between any of the 586 plays × 11 slots. It fully reparses MASTER PLAY,
  preserves every route node and formation-membership bit, and refuses a copy
  that would orphan a game-authored chain. Drawing new waypoint/opcode routes
  remains unavailable.
- **Model round trip** — export the stock helmet and player as static glTF,
  then import same-count, same-topology POSITION-only edits into a new verified
  copied `0A`. Materials, UVs, skinning, attachment authoring, animation,
  collision, allocation growth, and changed-topology replacement remain outside
  this writer.
- **Audio** — all 47,775 individually editable AUDO/AUSB cues (exact-slot XMA1
  replacement via a user-supplied encoder), with cue labels/notes and batch
  folder/ZIP authoring.
- **Field Art & Stadiums** — edit six exact field-art base textures while the
  remaining semantic inventory stays browse/export-only; the proved stadium
  scene owns 78 editable embedded textures and 77 same-topology
  POSITION-editable surfaces. Other scenes and material/shader authoring remain
  bounded separately.
- The editor and its copied-`0A` build path run headlessly; emulator consumption,
  gameplay visibility, and Xbox 360 hardware parity are separate, unproved
  boundaries.

See [`docs/mod_editor/2k5_mod_studio_getting_started.md`](docs/mod_editor/2k5_mod_studio_getting_started.md)
and [`docs/mod_editor/apf2k8_mod_studio_getting_started.md`](docs/mod_editor/apf2k8_mod_studio_getting_started.md)
for the full, evidence-backed feature and boundary list.

---

## Beta status & honesty

This is a **beta**. What that means here:

- Every shipped writer is **offline-proved**: it rebuilds a copied game image
  and an independent verifier confirms only the intended bytes changed.
- A smaller set is also **runtime-proved** (visible in a running emulator).
  Many writers are offline-proved but not yet captured in gameplay; the
  capability registry labels each one (`Editable`, `Preview`/`Export-only`,
  `Proof boundary`, or `Research boundary`).
- Executable patches (e.g. gameplay experiments) are **emulator-only** — they
  invalidate the retail signature and are not for original hardware.
- Some advanced areas remain explicitly outside this release's proved
  authoring scope (general or changed-topology 3D model replacement,
  whole-bank audio repack, freehand playbook waypoint authoring, signed-container save
  writeback, and franchise draft AI) and are tracked
  in [`docs/product/NFL2K5_COMPLETION_STATUS_AND_WALLS.md`](docs/product/NFL2K5_COMPLETION_STATUS_AND_WALLS.md).

---

## Requirements

- **Python 3, PyQt5, Pillow** — on Linux, Windows, or macOS.
  - **Linux** (Debian/Mint/Ubuntu):
    ```bash
    sudo apt install python3 python3-pyqt5 python3-pil
    ```
  - **Windows / macOS** (the `apt` line above is Linux-only): install Python 3
    from [python.org](https://www.python.org/downloads/), then:
    ```bash
    pip install PyQt5 Pillow
    ```
- An emulator to run your modded game:
  - **xemu** for ESPN NFL 2K5.
  - **Xenia Canary** for All-Pro Football 2K8.
- Your own legally dumped game disc (an `.iso`/XISO, or its extracted folder).

**Platform support.** CI is configured to run the suite on Linux, Windows, and
macOS with Python 3.11 and 3.12. Linux is the locally exercised release path;
the other two platforms are automated compatibility targets rather than
manually driven GUI release witnesses.

**Linux remains the most exercised platform**: the desktop app has been
smoke-tested end to end there, and the GUI has not been manually driven on
Windows or macOS, so treat those as well-tested code with a less-tested
window on top. Two specific limits:

- Retail-dependent tests and release gates skip with an explicit reason when
  their private game data or generated build inputs are unavailable.
- The bundled `extract-xiso` extractor ships as **both** a Linux binary and a
  Windows `.exe`, built from the same vendored 2.7.1 source, so handing the
  editor a `.iso` works on either. **macOS** has no bundled build — point the
  editor at an **already-extracted game folder** there, or build extract-xiso
  yourself and pass it to `SourceManager(extract_xiso=...)`. See
  `tools/vendor/extract-xiso/BUILDING-THE-BUNDLED-BINARIES.md` for the exact
  build commands and hashes.

Double-click launchers are bundled for all three platforms (see *Install*).

---

## Install

### From a release archive (recommended)
1. Download the release archive for your editor from the
   [Releases](../../releases) page and verify it (on Windows use
   `certutil -hashfile <archive> SHA256` and compare against the `.sha256`):
   ```bash
   sha256sum -c 2K5-Mod-Studio-*.tar.gz.sha256      # must say OK
   ```
2. Extract it, then launch for your platform:
   - **Linux** — install per-user (no `sudo`) or run portable:
     ```bash
     tar -xzf 2K5-Mod-Studio-*.tar.gz
     cd 2K5-Mod-Studio-*/
     ./install.sh            # app-menu shortcut + command on PATH
     # or, portable:
     ./2K5-Mod-Studio.sh
     ```
   - **Windows** — extract the archive, then double-click
     **`2K5-Mod-Studio.bat`**.
   - **macOS** — extract the archive, then double-click
     **`2K5-Mod-Studio.command`** (the first time, right-click it and choose
     **Open** to clear Gatekeeper).

   Each launcher checks for Python 3, PyQt5, and Pillow and shows a plain
   message if something is missing. (APF 2K8 Mod Studio ships the same three
   launchers named `APF-2K8-Mod-Studio.sh` / `.bat` / `.command`.)

   **Windows permissions:** the editor and the per-user installer are intended
   to run as a normal user; do not use **Run as administrator**. Always build
   into a new empty folder under Documents or Desktop, never into Program
   Files, the original game folder, or a disc. If the source and output are on
   different drives, the editor can copy its read-only sibling packs when
   Windows will not allow a link. That may take longer, but it does not require
   elevation.

### From source
```bash
git clone https://github.com/<you>/2k-football-mod-tools.git
cd 2k-football-mod-tools
python3 -m mod_editor --studio          # 2K5 Mod Studio
# APF 2K8 Mod Studio: see docs/mod_editor/apf2k8_mod_studio_getting_started.md
```

---

## Usage (the short version)

1. **Load Game** → select your clean ISO (or its extracted folder). The editor
   hashes and recognizes a supported source revision; it never modifies your
   original.
2. **Browse** the asset catalog. Editable assets expose **Replace**; read-only
   ones expose **Inspect/Export**.
3. **Replace** an asset with your own file (e.g. a PNG or WAV of the exact
   shape). The editor validates it against the fixed-allocation contract.
4. **Save** a project (`.2k5mod` / `.apf2k8mod`) — a portable, human-readable
   plan that never contains game bytes.
5. **Build** to a **new, empty** folder. The editor copies your source and
   applies your edits there; it refuses to overwrite your source.
6. Run the built `default.xbe` / `default.xex` in your emulator.

---

## Safety, legal & privacy

- **Bring your own game.** The editors refuse to run without a recognized
  source and never ship, store, or transmit game data.
- **Retail-free by construction.** Release archives pass an automated gate that
  verifies they contain no game bytes, decoded pixels/audio, private paths,
  symlinks, or undeclared files, plus a runtime-closure check that imports every
  shipped module from the clean stage.
- **Your source is read-only.** All output goes to a freshly created folder.
- **No telemetry.** Nothing phones home.
- **Emulator-only executable patches.** Any feature that patches the game
  executable invalidates the retail signature and is supported only on the
  named emulators, never original hardware.

---

## Repository layout

```
mod_editor/        the editors (core/, gui/, studio/ = 2K5, apf_studio/ = APF)
packaging/         release tooling, allowlists, desktop entries, installer
tools/             CLI build/verify tools + Ghidra analysis scripts
docs/              getting-started guides, capability matrix, research notes
tests/             test suite (unittest)
```

The full internal research log is preserved in
[`docs/README_full.md`](docs/README_full.md).

The claims-graded SoftDrinkTV publication handoff is the
[`APF video brief`](docs/research/apf_softdrinktv_video_brief.md);
verify its pinned facts and visuals with
`bash tools/validate_apf_softdrinktv_video_brief.sh`.

---

## Contributing

Contributions are welcome — PS2 support arrived that way. Read
[`CONTRIBUTING.md`](CONTRIBUTING.md) first: this project classifies every
capability by how strongly it has been *proved*, and a writer only ships with an
independent verifier. Understanding that ladder before you write code will save
you a review round.

Bug reports and detailed feature requests are just as valuable. A request that
names the exact in-game symptom is often the research lead that makes a feature
possible at all.

Security issues, and any case where the tools claim a guarantee they do not
actually enforce, go to [`SECURITY.md`](SECURITY.md) — privately, please.

---

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE).

[`NOTICE.md`](NOTICE.md) covers what that licence does *not* grant: it applies to
these tools and their source only, and gives you no rights to any game, game
data or trademark. Bring your own legally obtained copy. It also carries the
retail-free statement and the attribution for the bundled `extract-xiso`.

Release history is in [`CHANGELOG.md`](CHANGELOG.md).

---

## Beta disclaimer

This software is provided "as is", without warranty of any kind. It is a
work-in-progress beta for enthusiasts modding games they legally own. Use at
your own risk; always keep backups of your original game files.

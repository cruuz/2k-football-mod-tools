# 2K Football Mod Tools

> **Beta.** Two retail-free Linux mod editors for classic 2K football games:
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
- **Complete Team Kit** — all 39 components per physical set (jersey, sleeve,
  pants, both helmet families, digits 0–9, nameplate, Team Select cards),
  HOME/AWAY, with GIMP folder/ZIP round-trip.
- **Stadium Studio** — 477 scenes, 23,838 editable P8 texture occurrences, with
  a **"People & sideline only"** filter to isolate fans, cheerleaders, coaches,
  officials, chain crew, camera/media, ushers, and sideline props.
- **Audio** — all 850 standalone cues and all 53,571 playable streaming ranges
  (exact-slot replacement), with project-backed cue labels/notes.
- **Rosters** — current primary players (names + jersey numbers) and historical
  teams; secondary-pool jersey numbers via the generalized disc-roster writer.
- **Text** — 20,074 editable strings across 716 banks.
- Portraits, live faces, create-team field art, scorebug/presentation art.
- Runs in **xemu**.

### APF 2K8 Mod Studio — All-Pro Football 2K8 (Xbox 360)
- **Uniforms** — 96 editable textures (jersey/pants/helmet/shoulder) plus the
  shared `digital_font` and `draft_logo`.
- **Rosters & Players** — team display names, player names, all 28 base ratings
  per player, exact Position, and a 53-row roster planner.
- **Audio** — all 47,775 individually editable AUDO/AUSB cues (exact-slot XMA1
  replacement via a user-supplied encoder), with cue labels/notes and batch
  folder/ZIP authoring.
- Field Art inventory, Stadium Studio, presentation inspectors.
- Runs in **Xenia Canary**.

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
  capability registry labels each one (`PROVED` / `READ ONLY` / `PORTME`).
- Executable patches (e.g. gameplay experiments) are **emulator-only** — they
  invalidate the retail signature and are not for original hardware.
- Some advanced areas (3D model import, whole-bank audio repack, playbook route
  authoring, franchise draft AI, save editing) are **not done** and are tracked
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

**Platform support.** **Linux is the supported platform**: the full test suite
passes there and the desktop app has been smoke-tested end to end.

**Windows and macOS are a preview.** CI does run the suite on all three
operating systems, but it does not yet pass on Windows or macOS — the
cross-platform port is in progress and the GUI has not been manually driven on
either. Two specific limits if you try them:

- Some of the suite is expected to fail on any CI runner regardless of OS,
  because this repository deliberately ships no game data and no generated
  reports.
- The bundled `extract-xiso` extractor is a Linux binary, so on Windows the
  **ISO** path will not work — point the editor at an **already-extracted game
  folder** instead.

Double-click launchers are bundled for all three platforms (see *Install*), but
treat anything other than Linux as experimental for now.

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

---

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE).

---

## Beta disclaimer

This software is provided "as is", without warranty of any kind. It is a
work-in-progress beta for enthusiasts modding games they legally own. Use at
your own risk; always keep backups of your original game files.

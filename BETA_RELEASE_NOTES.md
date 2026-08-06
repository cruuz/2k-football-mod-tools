# Beta Release Notes

> **Superseded.** This file describes **Beta 1** and is kept as a record. Beta 1
> was Linux-first, so its platform notes below no longer describe the current
> tools. The current release is
> [**Beta 2**](https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-2),
> which runs on Windows, macOS and Linux; its notes live on that release page.

> **Current candidate (unreleased) — 2026-08-06.** The working tree is
> **2K5 Mod Studio v1.0 RC50** + **APF 2K8 Mod Studio 0.1.0-alpha.55**. It is
> a release candidate, not a release: nothing here has been committed,
> packaged, or published. The latest published release remains
> [**beta-23**](https://github.com/cruuz/2k-football-mod-tools/releases/tag/beta-23)
> (2K5 v1.0 RC49 + APF 0.1.0-alpha.54, 2026-08-05), which supersedes the
> Beta 2 pointer above. The changelogs are the candidate's source of truth:
> [`docs/mod_editor/2k5_mod_studio_changelog.md`](docs/mod_editor/2k5_mod_studio_changelog.md)
> and [`docs/mod_editor/apf2k8_mod_studio_changelog.md`](docs/mod_editor/apf2k8_mod_studio_changelog.md).
>
> Headlines since beta-23:
>
> - **2K5 RC48:** drop-in ordinary-audio replacement (849/849 authorable slots
>   converted and re-verified), per-uniform facemask/faceshield/turtleneck
>   colours across all 634 sets, 28,530 package-local equipment textures
>   editable in All Textures, stadium glTF export scaled to metres, update
>   check.
> - **2K5 RC50:** standalone editable inventory raised from 9,640 to 11,395
>   (+1,755 menu/mini-card/franchise/draft presentation surfaces); the 4,080
>   explicit-size A1 player strips no longer blanket-refused; all 2,547
>   current jersey numbers editable including 68 secondary-pool rows;
>   per-player face shield (None/Clear/Dark); all 498 Crib textures editable
>   plus a Crib Models tab; Team Kit → Browse 45 Equipment Textures; bounded
>   stadium glTF vertex import (75 position lanes; runtime visibility
>   unproved); exact same-book playbook stock-route copy; high-resolution
>   authoring masters.
> - **APF alpha.51:** `default.xex` decryption settled the ratings — 31
>   editable rating bytes, up from 28; crest editor widened to all 118 logo
>   slots; `endzone_l0` accepts edits; stadium glTF opens at sane units.
> - **APF alpha.52:** Team Independence — every built-in team points at its
>   own uniform textures (95 assignments changed, nothing added); ordinary
>   audio accepted at the drop target with exact-slot conformance; external
>   XMA1 output compared with authored PCM before staging.
> - **APF alpha.53:** Custom Team Appearance owns shell colours for user slots
>   32–39 with a one-click 2017 Eagles preset; the full-shell crest route is a
>   normal headless editor build; raw-save appearance path with verified STFS
>   handoff; Save Assignments for all 40 teams / 69 books; paired RPCS3/Xenia
>   roster audit (zero unexplained rows); helmet/player same-topology POSITION
>   import.
> - **APF alpha.55:** whole-shell atlas v24 (all 118 packages / 236 layers
>   compile; 10-view static visual gate passed); complete 206-slot wordmark
>   editor; verified stock assignment-route copy/swap across 586 MASTER plays;
>   complete 149-field Save Players editor with verified STFS handoff; stadium
>   selected-mesh POSITION round trip (77 surfaces); explicit Team Logo
>   coupled-write disclosure; high-resolution helmet-logo masters.
> - **Known APF issue:** an accepted-team Xenia menu witness (Eagles helmet
>   preview in Manage Team → Logo Selection, 2026-08-03) passed with stated
>   caveats, but in live gameplay the v24 shell renders semi-transparent/flat
>   (known background-alpha `0x88` defect; fix in flight). Gameplay shell
>   proof is not claimed.

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

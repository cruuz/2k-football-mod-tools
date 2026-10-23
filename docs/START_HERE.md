# START HERE: SOFTDRINK 2K28 and 2K5 Mod Studio, step by step

Prepared by Claude on Noah's behalf.

This page is for people who have never modded a game. It takes you from nothing to playing the SOFTDRINK 2K28 disc in xemu, then
shows how to add your own roster, keep an old franchise, and where to ask for help. Nothing here needs a terminal.

SOFTDRINK 2K28 is an unofficial fan project for ESPN NFL 2K5 (USA, original Xbox). It is not affiliated with or endorsed by the NFL,
the NFLPA, ESPN, 2K or any team. The tools and the pack contain no game data: you bring your own disc.

## 1. What you need

1. **Your own ESPN NFL 2K5 (USA, Xbox) disc image**, dumped from a disc you own. It should be an untouched dump (an `.iso` or
   `.xiso`). A disc someone else already modded will be refused, and so will a rebuilt ("repacked") image when you apply a patch.
   If the Studio says so, start again from a clean dump.
2. **2K5 Mod Studio**, the free editor. Download it from the
   [Studio releases](https://github.com/cruuz/2k-football-mod-tools/releases) (use the newest one).
   - Windows: run the installer, then open 2K5 Mod Studio.
   - macOS: extract the archive and double-click `2K5-Mod-Studio.command` (the first time, right-click it and choose Open).
     macOS has no bundled disc extractor, so point the Studio at an already-extracted game folder if it asks.
   - Linux and Steam Deck (Desktop Mode): extract the archive, run `./2K5-Mod-Studio.sh --setup` once, then `./2K5-Mod-Studio.sh`.
3. **The SOFTDRINK 2K28 patch**: one file ending in `.2k5patch`, from the
   [pack releases](https://github.com/cruuz/softdrink-2k28/releases). Keep it exactly as downloaded. Do not unzip it.
   The `.sha256` file next to it only checks the download; the Studio does not need it.
4. **xemu**, the original Xbox emulator, from [xemu.app](https://xemu.app). xemu needs its own BIOS files, which neither this project
   nor the Studio supplies. See [xemu's required-files guide](https://xemu.app/docs/required-files/).
5. **Free disk space** for the new disc image. The finished SOFTDRINK disc is roughly 6 GB, so keep at least 8 GB free.

## 2. Install SOFTDRINK 2K28 (one-click path)

1. Open 2K5 Mod Studio.
2. In the left sidebar choose **Build & Share**, then the **Share** tab, then **Install SOFTDRINK 2K28**.
3. Pick your untouched NFL 2K5 disc image, then pick the `.2k5patch` file itself.
4. Choose where to save the new image, for example `SOFTDRINK 2K28.xiso.iso`.
5. Wait for **Disc ready**. The Studio checks everything it writes. Your original image is never changed.

For every new SOFTDRINK version, start again from your original untouched image, not from the previous SOFTDRINK disc.

## 3. Point xemu at the disc

1. In xemu, open the settings and set **System Memory** to **128 MiB**, then restart xemu. This matters: with the default 64 MiB
   some stadiums can repeat the pregame show.
2. In xemu choose **Machine, Load Disc** and select the new image. (Or click **Play latest disc in xemu** in the Studio.)
3. If the picture looks grainy, try **View, Int. Resolution Scale, 2x**.
4. Start the game. If it sits on the Xbox logo, restart xemu.

More detail: [recommended xemu settings](mod_editor/recommended_xemu_settings.md).

## 4. Load the roster and start a franchise

SOFTDRINK's 2026 players and depth charts live on the disc, but a game or save you made earlier keeps its own old players.

1. In the game, load the **disc roster** before you do anything else.
2. Start a **fresh franchise** (or a Quick Game, which uses the disc roster).

If the game looks unchanged or shows 2004 rosters, check in this order: you loaded the new image and not the old one; you
installed from the untouched image plus the `.2k5patch` file; you started a fresh franchise after loading the disc roster; xemu
memory is 128 MiB.

## 5. Keep an existing franchise (Franchise, Upgrade)

A franchise saved on an older build keeps its old coaches, years pro and (before this update) hair styles. To bring it up to date:

1. Copy your franchise save somewhere safe first.
2. In the Studio open **Rosters** (the star page in the sidebar), then **Open Xbox save...** and choose the save. An Action Replay
   `.zip`, an extracted save folder, or a loose `SAVEGAME.DAT` with its `EXTRA` file beside it all work.
3. A franchise save shows the **Franchise** page. Choose **Upgrade franchise save to the current build**. If it tells you to write your
   edits to a save copy and reload it first, do that.
4. Click **Choose disc...** and pick your current SOFTDRINK disc.
5. Click **Preview upgrade** and read it. It lists coach bodies and pictures, corrected years pro, playbook fields, hair styles
   taken from the disc (styles you set yourself are kept) and restored team history. Your source save is not touched.
6. Click **Write signed copy**. It writes a new save beside the original, with the name you chose. Load that copy where you keep
   your xemu saves, and keep the original as a backup.

Your season progress, contracts and stats are kept. The upgrade only works on SOFTDRINK 2026 franchises. If it refuses, it says why.

## 6. Add or change your own roster

Your changes go into a new disc build. They do not change a save you already have.

1. In the Studio open **Rosters**. Press **Use the open disc** (or **Open disc roster...** and pick a disc).
2. Pick a team on the left, a player in the middle, and change names, numbers, positions and ratings on the cards on the right.
   The depth chart is the order of the list; use **Move up** and **Move down**.
3. Press **Export roster edits (.json)...** and save the file.
4. Open **Build & Share**. Tick **Include exported Rosters edits** and use **Choose...** to pick that `.json` file.
   To keep the SOFTDRINK art and settings, start from **Customize SOFTDRINK 2K28** on the **Share** tab, which loads the SOFTDRINK
   sources and recipe into the Build tab.
5. Tick **Save disc copy as**, choose a file name, and click **Make my disc**. Review the confirmation, then wait for **Disc ready**.
6. Load the new disc in xemu and load the disc roster in the game, then start a fresh franchise.

Notes: **Check my rosters...** on the same page looks for problems before you build. A save can override the disc roster, so test a
fresh disc-roster load. To use the roster inside one of your saves on a new disc, there is **Use this save's roster on the
disc...** (marked experimental).

## 7. Common settings

- **Extra point distance.** The Studio cannot set a custom distance. In SOFTDRINK 2K28 extra points are snapped from the 15,
  and that is fixed. It comes from one on/off option, **Modern kick spots & kicking power**, and the only other choice is the
  original game's spot, the 2. That option controls four things together: kickoffs from the 35 instead of the 30, touchbacks on
  kickoffs to the 35 instead of the 20 (punts and safety kicks keep the original 20), extra points from the 15 instead of the 2
  (two-point tries stay at the 2), and a longer field goal range for strong kickers (about 65 to 69 yards for a 99 kicker).
  SOFTDRINK also turns on **Dynamic kickoff alignment** (kickoff coverage and return line-ups) and **Dynamic kickoff** (nobody
  moves until the ball comes down, a landing zone, CPU kicks and touchbacks to the 35), which are built for the 35-yard tee.
  To go back to the original extra point spot:
  1. Open **Build & Share**, **Share**, **Customize SOFTDRINK 2K28**.
  2. Untick **Dynamic kickoff: ready stance and close blocks**. Do this first: while it is ticked, a build switches
     **Modern kick spots & kicking power** back on by itself.
  3. Untick **Dynamic kickoff alignment**, and untick **Modern kick spots & kicking power**.
  4. Optional: tick **More kicking power; keep 2004 kick spots** to keep the longer field goals with the original spots. You
     cannot tick this and Modern kick spots together.
  5. Make my disc. This puts the extra point back at the 2, and also puts kickoffs back to the 30 and kickoff touchbacks back to
     the 20, with the original kickoff set-ups.
  A customized build is made from the pack's included sources. The pack notes say a rebuild from those sources has not been
  checked against the released disc byte for byte, so expect to test it yourself.
- **Choose what a build changes.** In **Build & Share** choose a preset (Basic, Modern, Experimental), read the list of changes,
  then **Make my disc**. The presets do not add the SOFTDRINK 2K28 pack itself; use Install SOFTDRINK 2K28 for that.
- **Play clock.** **Accelerated clock** and **Minimum Play Clock Time** are in Gameplay, Game Fixes. SOFTDRINK 2K28 has the
  accelerated clock on with a 20 second minimum.
- **Memory.** Always 128 MiB in xemu for SOFTDRINK.

## 8. If something goes wrong

- Build failed: in **Build & Share** click **Copy Build summary** and paste it, with the first error line, when you ask for help.
- Freeze or crash in the game: say what you were doing (mode, teams, stadium, play), your Studio version, the SOFTDRINK pack
  version, your xemu version and memory setting, and where it stopped. A screenshot or short clip helps most.
- Check the [FAQ](mod_editor/2k5_mod_studio_faq.md) first; it covers installing, freezes and common questions.

## 9. Where to report bugs and ask questions

- The project Discord: <https://discord.gg/dpMJCnJZD> (also under **Help, Join the Discord...** in the Studio). Post bugs in the
  **#2k5-bugs** channel.
- GitHub issues for the Studio: <https://github.com/cruuz/2k-football-mod-tools/issues>.
- Security problems: see [SECURITY.md](../SECURITY.md).

## 10. More reading

- [Install SOFTDRINK 2K28 in 5 steps](mod_editor/install_softdrink_2k28.md)
- [2K5 Mod Studio getting started](mod_editor/2k5_mod_studio_getting_started.md) (every page and option)
- [Franchise save notes](mod_editor/franchise_save.md)

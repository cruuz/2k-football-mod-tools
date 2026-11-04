# START HERE: SOFTDRINK 2K28 and 2K5 Mod Studio, step by step

Prepared by Claude on Noah's behalf.

This page is for people who have never modded a game. It takes you from nothing to playing the SOFTDRINK 2K28 disc in xemu, then
shows how to add your own roster, keep an old franchise, and where to ask for help. Nothing here needs a terminal.

SOFTDRINK 2K28 is an unofficial fan project for ESPN NFL 2K5 (USA, original Xbox). It is not affiliated with or endorsed by the NFL,
the NFLPA, ESPN, 2K or any team. The tools and the pack contain no game data: you bring your own disc.

## 1. What you need

1. **Your own ESPN NFL 2K5 (USA, Xbox) disc image**, dumped from a disc you own. It should be an untouched dump in one image
   file (an `.iso` or `.xiso`). A raw (redump) dump, an untrimmed image and a rebuilt ("repacked") image all install SOFTDRINK
   fine. A disc someone else already modded will be refused. If the Studio says so, start again from a clean dump.
   - **Install SOFTDRINK 2K28 needs an image file.** If your dump is an extracted ("HDD ready") game folder, turn the folder
     into an xiso first (for example with extract-xiso), then pick that file.
   - Pick the image file itself, not a shortcut or symbolic link to it. A symbolic link is refused.
2. **2K5 Mod Studio**, the free editor. Download it from the
   [Studio releases](https://github.com/cruuz/2k-football-mod-tools/releases) (use the newest one at the top of the list; it
   may be marked Pre-release). On the release page open
   **Assets** and download the release file. Do **not** use the green **Code > Download ZIP** button: that downloads the source
   code, not the ready-to-run Studio.
   - Windows: run `2K5-Mod-Studio-*-Setup.exe`, then open 2K5 Mod Studio from the Start Menu. The Setup includes Python, so you
     do not install anything else.
   - macOS: extract the archive and double-click `2K5-Mod-Studio.command` (the first time, right-click it and choose Open).
     macOS has no bundled disc extractor, so point the Studio at an already-extracted game folder if it asks. That works for
     Build & Share; Install SOFTDRINK 2K28 still needs an image file (see item 1).
   - Linux and Steam Deck (Desktop Mode): extract the archive, run `./2K5-Mod-Studio.sh --setup` once, then `./2K5-Mod-Studio.sh`.
     If setup says the packages need Python 3.11 or 3.12 (for example, your system has only 3.13), the
     [FAQ](mod_editor/2k5_mod_studio_faq.md#linux-setup-says-the-packages-need-python-311-or-312-and-i-have-313) has a no-root fix.

   If you already downloaded the source ZIP, see [If you downloaded the source ZIP](#if-you-downloaded-the-source-zip) below.

3. **The SOFTDRINK 2K28 patch**: one file ending in `.2k5patch`, from the
   [pack releases](https://github.com/cruuz/softdrink-2k28/releases). Keep it exactly as downloaded. Do not unzip it.
   The `.sha256` file next to it only checks the download; the Studio does not need it.
4. **xemu**, the original Xbox emulator, from [xemu.app](https://xemu.app). xemu needs its own BIOS files, which neither this project
   nor the Studio supplies. See [xemu's required-files guide](https://xemu.app/docs/required-files/).
5. **Free disk space** for the new disc image. The finished SOFTDRINK disc is roughly 6 GB, so keep at least 8 GB free on
   the drive where the new image goes, plus room for the downloaded patch.

### If you downloaded the source ZIP

The green **Code > Download ZIP** button on the repository page downloads the source code. You can still use it, but the first
run has to install the Studio packages:

1. Extract the ZIP. A folder inside a folder with the same name is fine; the launcher works from wherever `2K5-Mod-Studio.bat`
   sits.
2. Install 64-bit Python 3.12 from [python.org](https://www.python.org/downloads/windows/) and tick **Add python.exe to PATH**
   during setup. Skip this if `py -3.12 --version` already works.
3. Double-click `2K5-Mod-Studio.bat`. The first run creates a private `.venv` beside the launcher and installs the pinned
   packages (about 110 MB to download, about 400 MB on disk). It also downloads the reviewed data files the Studio needs
   from the same release (about 65 MB). Later runs start immediately. To repair the private runtime, run
   `2K5-Mod-Studio.bat --setup`.

No administrator rights are needed. If the launcher says Python was not found, install it from the address it prints and run
the same file again. If the package install fails, check the internet connection and run the same file again; it is safe to
repeat.

## 2. Install SOFTDRINK 2K28 (one-click path)

1. Open 2K5 Mod Studio.
2. In the left sidebar choose **Build & Share**, then the **Share** tab, then **Install SOFTDRINK 2K28**.
3. Pick your untouched NFL 2K5 disc image, then pick the `.2k5patch` file itself.
4. Choose where to save the new image, for example `SOFTDRINK 2K28.xiso.iso`.
5. Wait for **Disc ready**. The Studio checks everything it writes. Your original image is never changed.

For every new SOFTDRINK version, start again from your original untouched image, not from the previous SOFTDRINK disc.

## 3. Point xemu at the disc

1. In xemu, open the settings, set **System Memory** to **128 MiB** and choose the **Complex 4627** BIOS image as the Flash ROM
   (BIOS), then restart xemu. This is required for SOFTDRINK 2K28 v0.9: the disc uses the bigger roster built for the 128 MiB
   layout, and its startup patch needs the 4627 BIOS. Do not run this disc at 64 MiB. (For an original Xbox or Android
   hakuX, see **Memory** under Common settings below.)
2. In xemu choose **Machine, Load Disc** and select the new image. (Or click **Play latest disc in xemu** in the Studio.)
3. If the picture looks grainy, try **View, Int. Resolution Scale, 2x**.
4. Start the game. If it sits on the Xbox logo, restart xemu.

More detail: [recommended xemu settings](mod_editor/recommended_xemu_settings.md).

## 4. Load the roster and start a franchise

SOFTDRINK's 2026 players and depth charts live on the disc, but a game or save you made earlier keeps its own old players.

1. In the game, load the **disc roster** before you do anything else.
2. Start a **fresh franchise** (or a Quick Game, which uses the disc roster).

The Crib is now the **Trophy Room** only: bought items no longer open, and furniture you placed stays as decoration (to keep
the whole Crib on a disc you build yourself, see [the FAQ](mod_editor/2k5_mod_studio_faq.md#can-i-keep-the-whole-crib-with-its-shops)). In
Franchise, the Front Office **Player Progress** row shows your club's rating changes this season (press the Black button on
that screen to step back through last week, 2 weeks ago and so on, up to 8 weeks); an older save starts a fresh history the
first time it loads.

If the game looks unchanged or shows 2004 rosters, check in this order: you loaded the new image and not the old one; you
installed from the untouched image plus the `.2k5patch` file; you started a fresh franchise after loading the disc roster; xemu
memory is 128 MiB.

## 5. Keep an existing franchise (Franchise, Upgrade)

A franchise saved on an older build keeps its old coaches, years pro, hair styles (if it was started before the disc had
them), award history and free agent pool. To bring it up to date:

1. Copy your franchise save somewhere safe first.
2. In the Studio open **Rosters** (the star page in the sidebar), then **Open Xbox save...** and choose the save. An Action Replay
   `.zip`, an extracted save folder, or a loose `SAVEGAME.DAT` with its `EXTRA` file beside it all work.
3. A franchise save shows the **Franchise** page. Choose **Upgrade franchise save to the current build**. If it tells you to write your
   edits to a save copy and reload it first, do that.
4. Click **Choose disc...** and pick your current SOFTDRINK disc.
5. Click **Preview upgrade** and read it. It lists coach bodies and pictures, corrected years pro, playbook fields, restored
   team history, hair styles taken from the disc (styles you set yourself are kept), award history (Pro Bowls and other
   honors), and the new free agents, which also moves the save to the bigger SOFTDRINK roster. Your source save is not
   touched.
6. Click **Write signed copy**. It writes a new save beside the original, with the name you chose. Load that copy where you keep
   your xemu saves, and keep the original as a backup.

Your season progress, contracts and stats are kept. The upgrade only works on SOFTDRINK 2026 franchises. If it refuses, it says why.

The upgrade also writes the disc's Super Bowl history into the save (the champions page of the Player Card; seasons the game
already recorded in your franchise stay), adds the draft-class player records of the bigger roster file (this works whether or
not the new game has already saved your franchise), and, with the box under **New save folder** ticked, takes the disc's
default game settings (7 minute quarters, 15 minute Sim. Quarter Length, Chop Block on) into the franchise, but only for
settings that still hold the old values of 5 minutes, 5 minutes and Off. A setting you changed yourself is kept, and the
preview lists it. When the disc carries the 2026 coach data, the upgrade also gives each head coach the disc's ratings,
play-calling habits and generic announcer line, again only where your franchise still has the older value: a rating or habit
you changed yourself is kept.

The upgrade does not change player ratings, colleges, announcer names, name suffixes or equipment. A franchise keeps its own
roster copy, so those need a new franchise. Old saves still load without the upgrade; they just keep the old free agent pool.
Saves made with the 16 reserves option (724,140 bytes) do not load on the bigger-roster disc, and the upgrade cannot move them.

### Your saved settings profile (Gameplay, Saves & Sliders)

New game defaults only reach new profiles: the game copies all the options saved in your Settings save (and in each franchise)
over its own defaults when it loads them. To bring a saved profile up to date, open **Gameplay**, then **Saves & Sliders**,
choose your disc's `default.xbe` and your `SAVEGAME.DAT` (Settings1 or a franchise), look at the **Game defaults** table and
make a signed copy. Settings that still hold the old values are ticked; ones you changed yourself are not, and you can tick
them to replace them. Put the new `SAVEGAME.DAT` and `EXTRA` back together. Do this for the Settings save and for each
franchise you want, because each franchise keeps its own copy of these settings.

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
  accelerated clock on with a 20 second minimum. Its runoff stops at 2:00 in the second quarter, fourth quarter and overtime.
- **Memory.** Always 128 MiB in xemu for SOFTDRINK. An original Xbox console and the Android emulator hakuX have 64 MB:
  for them the Studio can make a **64 MB build** (Build tab, **Console memory**, or Share, **Build for**, then **Customize
  SOFTDRINK 2K28**). It is experimental, estimated, not yet tested on a real Xbox or hakuX, and it leaves out the options
  that need 128 MB. The 2026 rosters stay, fitted to the original game's roster size (the free agents beyond the original
  count are left out). For the full experience use xemu at 128 MiB. See
  [the FAQ](mod_editor/2k5_mod_studio_faq.md#can-i-play-softdrink-2k28-on-android-in-hakux).

## 8. If something goes wrong

- Build failed: in **Build & Share** click **Copy Build summary** and paste it, with the first error line, when you ask for
  help. The Studio also refuses some common first-run mistakes before it starts: **Make my disc** with nothing ticked (it
  points you to **Install SOFTDRINK 2K28**), an output folder inside OneDrive on Windows (use a plain folder such as
  `C:\2K5`), too little free space (keep at least the source size plus 512 MiB free; about 8 GB in practice), and a source
  that is neither an untouched retail dump nor a SOFTDRINK disc (choose your clean, unmodified USA retail ISO).
- The game will not start: go through the checklist in the FAQ,
  [The game will not start. What should I check?](mod_editor/2k5_mod_studio_faq.md#the-game-will-not-start-what-should-i-check)
  (memory, BIOS, the right disc, folders). Both `.iso` and `.xiso` files are fine; for xemu end the name in `.iso`.
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

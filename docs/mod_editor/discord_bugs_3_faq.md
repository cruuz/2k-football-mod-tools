# Community fixes, batch 3 (Discord, 10 to 20 October)

These answers come from reports on the community Discord after the beta 77 release.
Where a fix needs the next Studio release, it says so. Nothing here is a gameplay claim.

- **How do I run 2K5 Mod Studio on Linux, SteamOS or a Steam Deck?** Use Desktop Mode
  and open a terminal (Konsole) in the extracted folder. Run `./2K5-Mod-Studio.sh --setup`
  once. It makes a private Python runtime in that folder from
  `packaging/requirements-studio.txt` (Python 3.11 or 3.12, an internet connection, no
  `sudo`, nothing written to the system partition). After that, `./2K5-Mod-Studio.sh`
  starts the Studio, and you can make a shortcut to it. On Debian, Ubuntu and Mint the
  setup needs `sudo apt install python3-venv` first. Earlier archives named
  `./2K5-Mod-Studio.sh` and `./install.sh` in the README but contained neither; the
  next archive contains the launcher. `install.sh` belongs to APF 2K8 Mod Studio.
- **The launcher showed an empty error box or nothing at all.** The dialog text was read
  as markup, so a Python message containing `<module>` left the box blank. The next
  Studio shows the message. Until then, run `./tools/launch_2k5_mod_studio.sh` from a
  terminal to read it, or look at `~/.local/state/2k5-mod-studio/last-launch.log`.
- **"Out of space" while opening my disc, but my drive has plenty.** Opening a disc stores
  a private copy of the game's art, about 6 GiB, in the Studio's own folder in your user
  profile (on Windows, `%LOCALAPPDATA%\2k5-mod-studio\cache`, usually on C:). The drive
  holding your disc image does not matter for that step. Free about 6 GiB on the profile
  drive and open the disc again. The next Studio names the folder, its free space and the
  size instead of only saying "out of space". Building a disc then needs about another
  6 GiB where you save the new image.
- **A build with some SOFTDRINK items unchecked failed with "project repeats target
  live_number_nameplate".** Fixed since the v0.6.1 patch work: the v0.6 pack held 340
  repeated number targets, and the corrected pack has none. If an older project of yours
  still says "project repeats a live digit/nameplate target", extract fresh SOFTDRINK
  sources (Build & Share, Share, Customize) into a new folder and rebuild from those.
  The check now happens before the long steps, not after.
- **"Apply the SOFTDRINK settings" stopped on a charge-ups or move-locks message
  (Coach Edwards).** Fixed in the next Studio: applying a preset now clears move locks
  you had ticked. Until then, untick both move locks, then apply the preset.
- **The Modern Colour and Lighting controls were squashed in Build & Share.** Fixed in
  the next Studio: the tab scrolls and the controls keep their height.
- **I installed the patch but the game looks unchanged, or has 2004 rosters.** Check in
  this order. (1) The new image is the file you load: in xemu use **Machine, Load Disc**
  and pick the new image, or press **Play latest disc in xemu** in Studio. (2) You started
  from your **unmodified** USA disc image and the `.2k5patch` file itself, not an already
  patched image. (3) You started a **fresh franchise** after loading the disc roster; an
  existing franchise or a roster saved on the xemu hard disk keeps its own players. (4)
  xemu System Memory is 128 MiB. The `.sha256` file next to a download is only for
  checking the download; Studio does not need it.
- **APF 2K8 Mod Studio, Situations panel: the formation list would not sort, and each edit
  hitched.** Fixed in the next APF build: click a column heading to sort (click again to
  reverse), and an installed situation patch is compared in about 0.01 s instead of
  0.2 s per edit. Two items from the same report are still open: Preview formation weights
  "not updating" needs the screenshot to reproduce, and the base personnel set weights are
  not editable in this build.

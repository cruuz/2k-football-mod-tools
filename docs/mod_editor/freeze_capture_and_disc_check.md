# When the game freezes: check your disc, then capture the freeze

Some freezes look the same from the outside: the picture stops, and the commentators repeat the same words
over and over. That sound is the sound card replaying its last bit of audio after the game has stopped. Two
very different things cause it:

* **A damaged or incomplete copy of the disc.** The game reads commentary and other files from the disc all
  through a game, including between plays. A copy that was cut short or damaged (an SD card, a transfer that
  stopped early, a drive that filled up while installing) stops the game at the first read that fails.
* **A real game problem.** Then the useful thing to know is where the game stopped.

Two small tools tell these apart. Neither changes your disc or your saves.

## 1. Check your SOFTDRINK disc

In Studio, open **Help → Check my SOFTDRINK disc…** and select your finished game image. Studio compares the game files with its list of released discs. You can copy the result into a bug report.

Linux, Steam Deck and macOS (open a terminal in the 2K5 Mod Studio folder):

    python3 -m mod_editor.core.nfl2k5_disc_check "/path/to/SOFTDRINK 2K28 v0.10.xiso.iso"

Windows (installed Studio: open a Command Prompt in the Studio's `app` folder):

    ..\runtime\python.exe -m mod_editor.core.nfl2k5_disc_check "D:\Games\SOFTDRINK 2K28 v0.10.xiso.iso"

The check reads the game files across the entire disc and can take several minutes.

* **The files match.** If the game freezes, include the screen and last input in your report.
* **A file is cut short.** The image ends before the game can read the whole file. Install from your clean disc again and check the new image.
* **Some files differ.** The report names the files and shows the affected ranges in MiB. An intentional edit to a playbook or the game executable can produce this result. Compare it with your Build summary. If you expected the official game, use **Install SOFTDRINK 2K28** and check the new image.
* **The disc differs more broadly.** Customize and other build options can change file sizes or contents. To check the release, select an image made with the official patch.

For a script, pass `--json` to the same command. The existing `damaged` state covers both small differences and truncation. A nonempty `cut_short` list identifies a file that actually runs past the end of the image.

## 2. Capture a freeze

xemu has a built-in debugger port. When it is on, the capture tool can ask a frozen game where it stopped
and write a short text file to post with your report. It is off unless you turn it on, and it listens on your
own computer only.

**If you start the game from the Studio** (Play latest disc in xemu), turn it on once:

    python3 -m mod_editor.core.nfl2k5_freeze_capture --enable 1234

(Windows: `..\runtime\python.exe -m mod_editor.core.nfl2k5_freeze_capture --enable 1234`.) Turn it off again
with `--disable`.

**If you start xemu yourself**, add the debugger option to its command line:

* Linux Flatpak: `flatpak run app.xemu.xemu -gdb tcp:127.0.0.1:1234`
* Linux AppImage or Steam Deck: `./xemu.AppImage -gdb tcp:127.0.0.1:1234`
* Windows: make a shortcut to `xemu.exe` and add ` -gdb tcp:127.0.0.1:1234` after the program path.

Then play as usual. **When the game freezes**, leave xemu open and run:

    python3 -m mod_editor.core.nfl2k5_freeze_capture --port 1234

(Windows: `..\runtime\python.exe -m mod_editor.core.nfl2k5_freeze_capture --port 1234`.)

It samples where the processor is, reads the calls that led there and the game's play state (game mode, play
calling option, down, who has the ball, how many plays), lets the game run on, and writes
`2k5-freeze-capture-<date>-<time>.txt` in your home folder. Post that file, say what was on the screen, and
which disc you play (the released SOFTDRINK disc or your own build).

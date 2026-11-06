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

This compares your disc image with the released SOFTDRINK 2K28 disc, file by file, and says either that it
matches or which file is damaged and where.

Linux, Steam Deck and macOS (open a terminal in the 2K5 Mod Studio folder):

    python3 -m mod_editor.core.nfl2k5_disc_check "/path/to/SOFTDRINK 2K28 v0.8.xiso.iso"

Windows (installed Studio: open a Command Prompt in the Studio's `app` folder):

    ..\runtime\python.exe -m mod_editor.core.nfl2k5_disc_check "D:\Games\SOFTDRINK 2K28 v0.8.xiso.iso"

It takes a few minutes (it reads the whole disc). The answer is one of:

* **matches**: the copy is good. A freeze on it is a real problem; capture it (below) and report it.
* **damaged or incomplete copy**: it names the files and the places (in MiB) that differ, or says the file
  ends early. Install or copy the disc again (Install SOFTDRINK 2K28 in the Studio, or a fresh download) and
  check again.
* **a different disc**: most of it differs. That is normal for a disc made with Customize SOFTDRINK or other
  Build options, so the check cannot judge it. To test the released disc, install it and check that image.

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

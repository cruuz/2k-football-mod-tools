# Custom intro video (experimental)

ESPN NFL 2K5 plays four movies at startup. The fourth, `intro.mov`, is the
game's intro. The Build option **Custom intro video** replaces it with a movie
you make from any clip. The executable and the other three startup movies stay
as they are. The option is off by default, is in no preset, and is not yet
witnessed in game: check the new intro yourself before you share a disc.

## What the game's movies are

Every movie on the disc is a CRI Sofdec stream: an MPEG-1 program stream cut
into 2,048-byte packs, carrying MPEG-1 video (640 x 480 at 29.97 frames a
second for the startup and menu movies) and CRI ADX audio (48,000 Hz stereo).
The `.mov` ending is only a name; these are not QuickTime files.

The encoder follows CRI's muxing rules exactly. Rebuilt from their own video and
audio, all 29 retail movies that carry ADX audio come out byte for byte
identical to the originals, so a movie the tool makes is laid out the way the
game's own movies are.

## Make the movie

You need FFmpeg (version 6 or newer) on your PATH. Then:

```text
python3 tools/nfl2k5_intro_encode.py clip.mp4 --in 0 --out 14 -o intro.mov
```

- `--in` and `--out` are times in the clip (seconds, or `m:ss.s`). They default
  to the whole clip. The intro may run up to 180 seconds.
- `--audio-track N` picks the clip's audio stream (0 is the first). Use
  `--audio-track none` for a silent intro. By default the first audio stream is
  used, or silence when the clip has no audio.
- `--fit letterbox` (the default) keeps the whole picture with black bars, which
  looks right on a 4:3 display. `--fit anamorphic` squeezes a 16:9 picture into
  the frame, which looks right when the display stretches the game to 16:9.
  `--fit crop` keeps the centre 4:3 of the picture.
- `--loudness` sets the loudness target. The default, -14.1 LUFS, is the retail
  intro's own level, so the new intro is neither louder nor quieter than the
  game. `--loudness off` keeps the clip's level.
- `--video-bitrate` sets the average video rate in kbit/s (default 5000; the
  retail movies average 4,000 to 5,700).

The tool writes the movie and a JSON receipt beside it (`intro.mov.json`). It
checks the movie three ways before it keeps it: against the retail muxing rules,
by decoding it back to exactly the pictures and audio samples that went in, and,
when the retail executable is available on a developer machine, by running the
game's own movie header code on it, which must ask for the same memory as it
does for the retail intro. The receipt records all three.

## Build the disc

1. On the Build page, choose your disc image as the source.
2. Tick **Custom intro video** and choose the movie with **Choose...**.
3. Build as usual.

The option refuses to run together with **Trim intro videos**, which skips all
four startup movies, so the new intro would never play. It works with the
**Crib movie cut**: the build cuts the Crib movies first and writes the intro
last. The movies live in an archive that the disc stores in sixteen parts, and
only the last part used to change size. On the retail disc the Crib cut leaves
34,611,200 bytes in that part, less than a short intro frees, so the part before
it gives up the rest and the last part keeps one 2,048-byte sector; the archive's
own table of part sizes records the change, the same table every build that grows
the first part already rewrites. The build checks every other file on the disc
against the source before it publishes the output. The disc shrinks or grows by
the difference between the new intro and the retail one (the retail intro is
50,241,536 bytes).

To go back to the retail intro, build again from your retail disc without the
option, or restore it from the command line with your retail disc as the
reference:

```text
python3 -m mod_editor.core.nfl2k5_custom_intro restore custom.iso restored.iso retail.iso
```

A restore writes the pinned retail intro back. When the custom disc was built
from the retail disc, the restored disc is identical to the retail disc. With the
Crib movie cut, a restore also gives the part before the last its retail size
again, so the restored disc is identical to the retail disc with only the Crib
cut.

## Other commands

```text
python3 -m mod_editor.core.nfl2k5_custom_intro check intro.mov
python3 -m mod_editor.core.nfl2k5_custom_intro status disc.iso
python3 -m mod_editor.core.nfl2k5_custom_intro plan disc.iso intro.mov
```

`check` lists every way a movie departs from the retail rules (an empty list
means it conforms). `status` says whether a disc carries the retail intro, a
custom one, or something the tool does not recognise.

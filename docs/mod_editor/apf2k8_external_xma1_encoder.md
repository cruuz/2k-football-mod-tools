# APF 2K8 Mod Studio: authoring sounds from PCM16 WAV

APF 2K8 Mod Studio does not ship an XMA1 encoder. Alpha 28 can use an encoder
that the modder legally obtained and installed separately, then reject its
output unless it fits each selected APF sound exactly. The source game is never
modified.

There are two PCM routes: the selected-sound workflow for one WAV, or a
metadata-only v2 folder/ZIP pack containing up to 256 supplied WAVs per import.
The legacy v1 folder/ZIP route still accepts finished pre-encoded XMA1 and
remains the default.

## The short workflow

1. Load your own APF 2K8 game dump and open **Audio**.
2. Select one standalone AUDO sound or one AUSB-bank substream.
3. Choose **Export PCM authoring template…** and save the new WAV.
4. Replace the silence in that WAV with your own audio. Preserve its channel
   count, sample rate, 16-bit PCM format, and exact frame count.
5. Choose **Configure XMA1 encoder…** once and select your separately installed
   encoder. A Windows `.exe` can use a separately installed Wine executable.
6. Choose **Replace from PCM WAV…** and select the edited WAV.
7. Mod Studio privately runs the encoder, validates its finished XMA1 output,
   decodes it back, compares the decoded signal with the authored PCM, and adds
   one normal, revertible project edit only if every check passes.

The exported template is deterministic silence. It contains no original game
audio or other retail payload. Its receipt shows the selected sound's channel
count, sample rate, exact frame count, and fixed encoded-byte allocation.

## Batch PCM16 folder or ZIP workflow

1. In **Audio**, filter the complete inventory or review a hand-picked
   shortlist. Choose **Exact PCM16 WAV** and either **Editable folder** or
   **ZIP hand-off**, then create the replacement template.
2. Keep `replacement-pack.json` and `README.md` unchanged. Add an independently
   authored exact-shape WAV at any listed `pcm16/*.wav` path; missing listed
   files are intentional skips. One template may list all 47,775 editable
   sounds, but one import accepts no more than 256 supplied WAVs.
3. Configure the external encoder once, then choose **Review replacement
   folder…** or **Review replacement ZIP…**. Review auto-detects the v2 schema;
   the current export selector does not need to match the pack being opened.
4. Mod Studio privately copies and encodes each WAV and validates every final
   XMA1 result without staging an edit. It shows exact would-change and
   resulting-modified counts. Explicit **Apply** reopens and revalidates the
   pack, verifies that its exact member hashes and project-audio revision still
   match the preview, then commits the complete valid set as one Undo action.
   Failure, Cancel, unchanged-only input, stale target state, or divergent AUSB
   aliases stage nothing and remove new unreferenced private work.

The v2 manifest schema is
`apf2k8_mod_studio_audio_replacement_pack/v2`; its payload folder is `pcm16/`.
The v1 schema and deterministic `xma1/` ZIP output remain byte-compatible and
do not require an encoder during import. Do not mix WAV and XMA payloads in one
pack. FLAC, MP3, WMA, floating-point WAV, XMA1, and XMA2 are not valid v2
payloads; convert authored material to the listed target's exact signed
little-endian PCM16 shape first.

## Editing the WAV

The template is deliberately strict because APF points at fixed audio slots.
In an audio editor:

- keep the exact number of channels shown by Mod Studio;
- keep the exact sample rate;
- export uncompressed signed 16-bit PCM WAV;
- keep the exact duration/frame count, padding unused time with silence; and
- do not add a second audio stream.

Ordinary FLAC, MP3, floating-point WAV, and resampled WAV input are not accepted
by this route. Convert the authored sound to the template's exact PCM16 shape in
your audio editor first.

## Configuring an external encoder

The normal preset passes two arguments to the selected encoder:

```text
{input}
{output}
```

This means “input PCM WAV path, then output XMA path.” Microsoft encoder-tool
documentation is access-controlled, and legally obtained tools can have
different command-line interfaces. If a tool needs switches, open **Advanced:
customize encoder arguments** and enter one argument per line. This is an argv
list, not a shell command. Quotes, pipes, semicolons, redirection, and other
shell syntax are never interpreted.

The supported placeholders are:

| Placeholder | Value supplied for the selected sound |
|---|---|
| `{input}` | Private canonical PCM16 input path; required exactly once |
| `{output}` | Requested private XMA output path; required exactly once |
| `{channels}` | `1` or `2` |
| `{sample_rate}` | Samples per second, such as `48000` |
| `{sample_count}` | Required PCM frames per channel |
| `{encoded_size}` | Required APF XMA packet allocation in bytes |

Example for a hypothetical tool whose output switch and bitrate options are
separate arguments:

```text
{input}
/Output
{output}
/CustomOption
```

That example documents the editor, not a known encoder syntax. Use the
documentation supplied with the encoder you legally obtained. Mod Studio does
not download, bundle, license, or verify ownership of third-party tools.

On Linux, selecting a Windows `.exe` enables Wine mode. The GUI resolves the
normal `/usr/bin/wine` alternatives link to its real executable before saving
the setting. Encoder path, Wine path, and the argv template are PC-local
application settings. They are never written into a mod project.

Only run an encoder you trust: like any local executable, it runs with your user
account's permissions.

## What Mod Studio checks after encoding

Encoder exit code zero is not approval. Every final XMA1 output must also pass
the same independent admission path as **Replace with XMA1…**:

- one supported RIFF XMA1 stream, not XMA2, xWMA, or an arbitrary RIFF file;
- exact selected channel count and sample rate;
- exact fixed encoded allocation and `0x800`-byte APF packet framing;
- complete decoder acceptance and the bounded decoded-tail rule;
- for the PCM/external-encoder route, an alignment-aware signal comparison that
  rejects silence/collapse, channel swap/interleave, wrong rate or pitch, gross
  level change, new sustained clipping, excessive DC, and a corrupt tail;
- source-game fingerprint rejection, including cross-family AUDO/AUSB packet
  reuse;
- exact source and target identity; and
- shared-owner/alias consistency for the one physical AUSB range with two
  semantic owners.

If any check fails, no project edit and no Undo entry are added. The private
PCM copy, encoder output, and diagnostic file are removed when the operation
ends. The source ISO or extracted game folder is never opened for writing.

## Common messages

| Message | What it means | What to do |
|---|---|---|
| PCM shape does not match | Channels, rate, sample format, or duration changed | Re-open the exported template and export exact PCM16 without changing its length |
| Encoder is not ready | Tool path, executable permission, Wine path, or argv template is invalid | Re-open **Configure XMA1 encoder…** and correct the highlighted setting |
| Encoder failed | The selected tool returned an error | Read its bounded diagnostic, then check that tool's own documentation and arguments |
| Output is missing or too large | The tool did not write the requested file or exceeded the selected slot | Correct the output argument or encoder settings |
| Exact encoded size does not match | Valid-looking XMA1 still does not occupy the fixed APF allocation | Adjust the encoder's documented quality/packet options; Mod Studio will not truncate or pad encoded packets blindly |
| Complete decode failed | The file is malformed, unsupported, or not acceptable to the conservative decoder gate | Try a different legal encoder configuration or use a separately verified pre-encoded XMA1 file |
| Matches source audio | The supplied result contains one or more exact protected source packets | Use independently authored audio. Mod Studio blocks exact packet reuse; it cannot determine the copyright or license of newly encoded sound by listening to it |

## Honest Alpha 28 boundary

The silence-template writer, no-shell process adapter, cancellation/timeout
cleanup, Wine routing, selected and batch dispatch, 256-supplied-WAV ceiling,
Undo atomicity, final-validator handoff, and signal comparator have synthetic
automated proof. The comparator passes aligned lossy reconstruction and rejects
silence, wrong pitch/rate, channel swaps, clipping, DC, and tail corruption.
The decoder runner and fail-closed session wiring are also tested. These tests
do not claim that fake output is perceptually valid XMA1.

No distributable XMA1 encoder is bundled, and no real encoder was available in
the build environment for an end-to-end authored-audio acceptance test. The
earlier Xenia audio experiment proved boot, selection, and stability but did
not isolate audible modified-stream causality. The signal gate now prevents the
known gross artifact families from being staged, but it is not a listening test
or a transparency score. The PCM routes remain strict user-supplied-tool
bridges, not a promise that every encoder or every APF cue will work.

The project format structurally excludes original source bytes and exact source
XMA packet reuse. It cannot recognize whether separately encoded PCM resembles
copyrighted material. Mod authors remain responsible for using and sharing only
audio they have the right to distribute.

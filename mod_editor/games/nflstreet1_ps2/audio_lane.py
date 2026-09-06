"""NFL Street (PlayStation 2)'s ``SCHl`` streams and ``BNKl`` banks: catalogue and export.

The disc carries **679 ``SCHl`` streams and 236 ``BNKl`` banks** holding 1,031
sounds [M].  Both lanes are instances of the shared
:mod:`mod_editor.games._lanes.ea_audio`; this file is which containers hold the
audio on this disc and what the counts are.

Where it is, measured [M]
-------------------------

``CHATDATA.DAT`` 279,664,640 bytes, 637 streams · ``FEMUSIC.DAT``
140,980,224 bytes, 14 streams · ``UISOUND.DAT`` 25,067,520 bytes, 11 streams and 3
banks · ``PATHFIND.DAT`` 206,604,288 bytes, 9 streams · ``AMBSTRM.DAT`` 164,659,200
bytes, 8 streams · ``FIELDSFX.DAT`` 18,731,008 bytes, 233 banks [M].

**42 of the 679 streams carry a codec that decodes here** -- EA-XA ADPCM -- and the
other 637 are EA's MicroTalk, which no decoder in this repository or in ffmpeg
opens [M/S].  Those are listed with their rate, channels and length and their
audio is **refused by name** rather than guessed at.  All 236 banks open and hold
1,031 sounds [M], PlayStation ADPCM, and those export.

``extract-only``: a WAV comes out, nothing goes back in.  A writer would have to
re-encode into the bytes a sound already occupies **and** rewrite the 9
``QL01`` preload caches that copy the container, and no rebuilt NFL Street container
has ever been booted.

``CHATDATA.DAT``, ``PATHFIND.DAT``, ``AMBSTRM.DAT`` and
``FEMUSIC.DAT`` are all past this module's 48 MB read limit, so the image is
memory-mapped once and the lane hands out offsets: no payload is copied to build
a catalogue and nothing is decoded until an export asks for it.

Run it without a window::

    python3 -m mod_editor.games.nflstreet1_ps2.audio_lane --source DISC.iso

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

from mod_editor.games._lanes.ea_audio import BnklBankLane, SchlStreamLane
from mod_editor.games.contract import Refusal

from . import containers

STREAMS_CAPABILITY = "nflstreet1ps2.audio.streams"
STREAMS_LANE_ID = "audio.streams"
STREAMS_SCHEMA = "nflstreet1_ps2_audio_streams/v1"
STREAM_EXPORT_SCHEMA = "nflstreet1_ps2_audio_stream_export/v1"

BANKS_CAPABILITY = "nflstreet1ps2.audio.banks"
BANKS_LANE_ID = "audio.banks"
BANKS_SCHEMA = "nflstreet1_ps2_audio_banks/v1"
BANK_EXPORT_SCHEMA = "nflstreet1_ps2_audio_bank_export/v1"

#: What a sentence calls this game.
GAME_TITLE = "NFL Street (PlayStation 2)"


class AudioStreamsLane(SchlStreamLane):
    """The ``SCHl`` streams: catalogue and export.  Nothing is written back."""

    discs = containers
    lane_id = STREAMS_LANE_ID
    capability_id = STREAMS_CAPABILITY
    recipe_schema = STREAMS_SCHEMA
    export_schema = STREAM_EXPORT_SCHEMA
    game_title = GAME_TITLE
    audio_containers = containers.STREAM_CONTAINERS
    synthetic_name = "nflstreet1_ps2-streams-synthetic.iso"
    validators = (
        "tools/validate_nflstreet1_ps2_audio.sh",
        "tools/validate_nflstreet1_ps2_audio.bat",
    )
    NO_WRITER = (
        "A stream is not replaced here. 637 of this disc's 679 streams are EA MicroTalk, "
        "which no decoder in this repository or in ffmpeg opens; a writer for the other "
        "42 would have to keep the 9 QL01 preload caches in step with the container it "
        "rewrites, and no rebuilt NFL Street container has ever been booted. Export the WAV "
        "instead."
    )
    how_to_notes = (
        "Export the speech. 637 of this disc's 679 streams are EA MicroTalk, and no\n"
        "    decoder for it exists in this repository or in ffmpeg. They are listed with\n"
        "    their rate and length instead.",
    )


class AudioBanksLane(BnklBankLane):
    """The ``BNKl`` sound banks: catalogue and export.  Nothing is written back."""

    discs = containers
    lane_id = BANKS_LANE_ID
    capability_id = BANKS_CAPABILITY
    recipe_schema = BANKS_SCHEMA
    export_schema = BANK_EXPORT_SCHEMA
    game_title = GAME_TITLE
    audio_containers = containers.BANK_CONTAINERS
    synthetic_name = "nflstreet1_ps2-banks-synthetic.iso"
    validators = (
        "tools/validate_nflstreet1_ps2_audio.sh",
        "tools/validate_nflstreet1_ps2_audio.bat",
    )
    NO_WRITER = (
        "A bank sound is not replaced here. A writer would re-encode into the bytes the "
        "sound already occupies and rewrite the 9 QL01 preload caches that copy this "
        "container, and no rebuilt NFL Street container has ever been booted. Export the WAV "
        "instead."
    )
    how_to_notes = (
        "Export a sound that declares no rate. A WAV written from one would play at\n"
        "    a rate nobody measured, so the lane refuses it by name.",
    )


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.nflstreet1_ps2.audio_lane --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.nflstreet1_ps2.audio_lane",
        description="Catalogue and export the audio on a NFL Street (PlayStation 2) disc.",
    )
    parser.add_argument("--lane", default="streams", choices=("streams", "banks"))
    parser.add_argument("--source", help="the user's own SLUS-20841 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--export", metavar="MANIFEST.json",
                        help="write this NEW manifest and the WAVs in a folder beside it")
    parser.add_argument("--limit", type=int, default=8,
                        help="how many sounds --export writes (default 8)")
    parser.add_argument("--selftest", action="store_true",
                        help="run both lanes on their synthetic disc; needs no game data")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if arguments.selftest:
            import tempfile

            failures = 0
            for name, factory in (("streams", AudioStreamsLane), ("banks", AudioBanksLane)):
                lane = factory()
                with tempfile.TemporaryDirectory() as room:
                    source = lane.synthetic_source(Path(room))
                    catalogue = lane.build_catalogue(source)
                    edits = lane.conformance_edits(catalogue)
                    manifest = Path(room) / "export" / "manifest.json"
                    receipt = lane.build(source, manifest,
                                         lane.compose_recipe(edits), catalogue)
                    verdict = lane.verify(source, manifest, receipt)
                    print(f"  {name:8s} rows={len(catalogue.targets):5d} "
                          f"files={len(receipt.artifacts)} "
                          f"verify={'PASS' if verdict.passed else 'FAIL'}")
                    failures += 0 if verdict.passed else 1
            print(f"AUDIO lanes=2 failures={failures}")
            return 0 if failures == 0 else 1
        if not arguments.source:
            parser.error("give --source DISC.iso, or --selftest")
        lane = AudioStreamsLane() if arguments.lane == "streams" else AudioBanksLane()
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        if arguments.export:
            from mod_editor.games.contract import Edit

            picked = [target for target in catalogue.targets
                      if target.raw.get("decodable") or target.raw.get("playable")]
            edits = tuple(Edit(target.key, {}, note="export as it is")
                          for target in picked[:max(1, arguments.limit)])
            manifest = Path(arguments.export)
            receipt = lane.build(Path(arguments.source), manifest,
                                 lane.compose_recipe(edits), catalogue)
            verdict = lane.verify(Path(arguments.source), manifest, receipt)
            print(f"EXPORT files={len(receipt.artifacts)} "
                  f"verify={'PASS' if verdict.passed else 'FAIL'} \u2014 {verdict.summary}")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    if arguments.lane == "streams":
        print("STREAMS total=%d decodable=%d codecs=%s"
              % (document["streams"], document["streams_decodable"],
                 ",".join(f"{k}:{v}" for k, v in sorted(document["codecs"].items()))))
    else:
        print("BANKS banks=%d sounds=%d playable=%d"
              % (document["banks"], document["sounds"], document["sounds_playable"]))
    return 0


__all__ = ["AudioBanksLane", "AudioStreamsLane", "BANKS_CAPABILITY", "BANKS_LANE_ID",
           "BANKS_SCHEMA", "BANK_EXPORT_SCHEMA", "GAME_TITLE", "STREAMS_CAPABILITY",
           "STREAMS_LANE_ID", "STREAMS_SCHEMA", "STREAM_EXPORT_SCHEMA"]


if __name__ == "__main__":
    raise SystemExit(_main())

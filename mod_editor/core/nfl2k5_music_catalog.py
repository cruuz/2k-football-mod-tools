"""The 66 logical core music rows and 20 presentation slots, with exact twins.

Titles are transcribed from the retail XBE, not guessed from audio. Durations
always come from the selected source's validated AUSB boundaries.
"""
from __future__ import annotations
from dataclasses import dataclass
import zlib
from .nfl2k5_audio_catalog import Nfl2k5StreamingAudioRange

# name: (count, channels, descriptor outer, chunk, external outer, label)
BANKS = {
    "femusic": (7, 2, 3, 217, 3128, "Menu"),
    "cribmusic": (59, 2, 3, 222, 3123, "Jukebox"),
    "crib22": (59, 1, 3, 223, 3122, "Stadium"),
    "loadm": (3, 2, 3, 218, 3131, "Loading"),
    "wrapupm": (8, 2, 18, 14, 3135, "Wrap-up"),
    "halftimeaudio": (5, 1, 346, 137, 3129, "Halftime"),
    "drafta": (4, 2, 3, 219, 3127, "Draft"),
}
TRACKS = (
    ('Bounce', 'Big J', 'Select'),
    ('Take Off', 'Big J', 'Select'),
    ('Crank It Up', 'Big J', 'Select'),
    ("It Just Won't Be", 'Big J', 'Select'),
    ('Make The Stop', 'Opus 1', 'Rock'),
    ('Slow Down', 'Opus 1', 'Rock'),
    ("Sportin'", 'Opus 1', 'Rock'),
    ('Two Three', 'Opus 1', 'Rock'),
    ('2 Much', 'Mike Reagan', 'Hip Hop'),
    ('Come On', 'Mike Reagan', 'Hip Hop'),
    ('Hands Up', 'Brad Cross', 'Hip Hop'),
    ('Yo Groove', 'Brad Cross', 'Hip Hop'),
    ('Aw Yaz', 'Brad Cross', 'Electronica'),
    ('Code Breaker', 'Opus 1', 'Electronica'),
    ('Dance It', 'Opus 1', 'Electronica'),
    ('Tizaziz', 'Brad Cross', 'Electronica'),
    ("Can't Sit Still", 'The Danger', 'The Danger'),
    ('Fly Eater', 'The Danger', 'The Danger'),
    ("I Ain't Used", 'The Danger', 'The Danger'),
    ('Locket', 'The Danger', 'The Danger'),
    ('Outtake 1', 'Dan & Steve', 'Outtakes #1'),
    ('Outtake 2', 'Dan & Steve', 'Outtakes #1'),
    ('Outtake 3', 'Dan & Steve', 'Outtakes #1'),
    ('Outtake 4', 'Dan & Steve', 'Outtakes #1'),
    ('Outtake 5', 'Dan & Steve', 'Outtakes #2'),
    ('Outtake 6', 'Dan & Steve', 'Outtakes #2'),
    ('Outtake 7', 'Dan & Steve', 'Outtakes #2'),
    ('Outtake 8', 'Dan & Steve', 'Outtakes #2'),
    ('Outtake 9', 'Dan & Steve', 'Outtakes #3'),
    ('Outtake 10', 'Dan & Steve', 'Outtakes #3'),
    ('Outtake 11', 'Dan & Steve', 'Outtakes #3'),
    ('Outtake 12', 'Dan & Steve', 'Outtakes #3'),
    ('The Best', 'Raw Intel/RIC', 'Raw Intel/RIC'),
    ('Get In Line', 'Raw Intel/RIC', 'Raw Intel/RIC'),
    ("Can't Go Wrong", 'Raw Intel/RIC', 'Raw Intel/RIC'),
    ('Deep And Wide', 'Aceyalone', 'Aceyalone'),
    ('Ace Cowboy', 'Aceyalone', 'Aceyalone'),
    ('Superstar', 'The Good Brothers', 'Aceyalone'),
    ('Try Me', 'J. Boogie', 'J. Boogie'),
    ('Golden Nectar', 'J. Boogie', 'J. Boogie'),
    ('Le Sengre', 'J. Boogie', 'J. Boogie'),
    ('All Pleasure', 'Recliner', 'Recliner'),
    ('Irish Bullfight', 'Recliner', 'Recliner'),
    ('Gothic Voices', 'Concept', 'Concept'),
    ('Angel Of Truth', 'Concept', 'Concept'),
    ('Evolution!', 'Concept', 'Concept'),
    ('Drumbox', 'People Under the Stairs', 'People Under the Stairs'),
    ('Outrun', 'People Under the Stairs', 'People Under the Stairs'),
    ('Clean Living', 'Rjd2', 'Definitive Jux'),
    ('Pull Out Your Cut', 'MR. LIF', 'Definitive Jux'),
    ('Like Smak', 'Raw Intel/RIC', 'Hip Hop Sampler'),
    ('The God In Me', 'Aceyalone', 'Hip Hop Sampler'),
    ('Knock Me Down Girl', 'Slicker', 'Incite Sampler #1'),
    ('Oceanic Lullaby', 'J. Boogie', 'Incite Sampler #1'),
    ('Making A Friend', 'Recliner', 'Incite Sampler #1'),
    ('Eternal Life', 'Concept', 'Incite Sampler #2'),
    ('Disco Rout', 'Legowelt', 'Incite Sampler #2'),
    ('Sound In A Dark Room', 'Telefon Tel Aviv', 'Incite Sampler #2'),
    ('The Pharaoh', 'The Danger', 'Incite Sampler #2'),
)


@dataclass(frozen=True)
class MusicRow:
    row_id: str
    title: str
    artist: str
    collection: str
    context: str
    presentation: bool
    spoken: bool
    primary: Nfl2k5StreamingAudioRange
    twin: Nfl2k5StreamingAudioRange | None = None

    @property
    def targets(self):
        return (self.primary,) if self.twin is None else (self.primary, self.twin)

    @property
    def duration_seconds(self):
        return self.primary.duration_seconds

    @property
    def display_name(self):
        return f"{self.title} / {self.artist}" if self.artist else self.title


class MusicCatalog:
    def __init__(self, audio_catalog):
        banks = {}
        for bank in audio_catalog.streaming_banks:
            if bank.name not in BANKS:
                continue
            if bank.name in banks:
                raise ValueError(f"Duplicate music descriptor: {bank.name}")
            count, channels, outer, chunk, external, _label = BANKS[bank.name]
            crc = zlib.crc32(f"{bank.name}.bin".upper().encode("utf-16le")) & 0xffffffff
            if (bank.entry_count, bank.channel_word, bank.outer_index, bank.chunk_index,
                bank.external_outer_index, bank.sample_rate, bank.unit_word,
                bank.external_filename, bank.external_outer_id.lower()) != (
                    count, channels, outer, chunk, external, 22050, 0x12000,
                    f"{bank.name}.bin", f"0x{crc:08x}"):
                raise ValueError(f"Music descriptor ownership/shape differs: {bank.name}")
            b = bank.boundaries
            if (len(b) != count + 1 or b[0] != 0 or b[-1] != bank.external_size or
                any(type(x) is not int or not 0 <= x <= 0xffffffff for x in b) or
                any(a >= z or (z-a) % (36*channels) for a,z in zip(b,b[1:]))):
                raise ValueError(f"Music boundaries are invalid: {bank.name}")
            banks[bank.name] = bank
        if set(banks) != set(BANKS):
            raise ValueError("Music needs all seven verified music bank descriptors")
        if banks["cribmusic"].boundaries != tuple(2*x for x in banks["crib22"].boundaries):
            raise ValueError("Jukebox stereo and stadium mono durations disagree")
        rows = []
        for name, bank in banks.items():
            if name == "crib22":
                continue
            for index in range(bank.entry_count):
                title, artist, collection = (TRACKS[index] if name == "cribmusic" else
                    (f"{BANKS[name][-1]} {index+1:02d}", "", "Title unresolved"))
                primary = Nfl2k5StreamingAudioRange(bank, index, *bank.boundaries[index:index+2])
                twin = None
                if name == "cribmusic":
                    mono = banks["crib22"]
                    twin = Nfl2k5StreamingAudioRange(mono, index, *mono.boundaries[index:index+2])
                rows.append(MusicRow(f"{name}:{index}", title, artist, collection,
                    "Jukebox and linked stadium version" if twin else BANKS[name][-1],
                    name not in ("femusic", "cribmusic"), name == "cribmusic" and 20 <= index <= 31,
                    primary, twin))
        order = list(BANKS)
        self.rows = tuple(sorted(rows, key=lambda r: (order.index(r.primary.bank.name), r.primary.range_index)))
        self.by_id = {row.row_id: row for row in self.rows}

    def visible_rows(self, presentation=False):
        return tuple(row for row in self.rows if presentation or not row.presentation)

    def get(self, row_id):
        try:
            return self.by_id[row_id]
        except KeyError as exc:
            raise ValueError(f"Unknown music slot: {row_id}") from exc

    def assignments(self, paths, visible_ids, start_id=None):
        """Freeze URL and visible order; never wrap, duplicate or partially fill."""
        paths, ids = tuple(paths), tuple(visible_ids)
        if not paths or not ids or len(ids) != len(set(ids)):
            raise ValueError("A music drop needs files and a unique visible row order")
        for value in ids:
            self.get(value)
        start = ids.index(start_id) if start_id is not None else 0
        if start + len(paths) > len(ids):
            raise ValueError("Too many files for the remaining visible music slots; nothing changed")
        return tuple(zip(ids[start:start+len(paths)], paths))

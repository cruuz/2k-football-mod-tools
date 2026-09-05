"""EXPERIMENTAL / UNWITNESSED music-library plan / rebuild / verify service.

Recipes are JSON objects: {schema: 'nfl2k5_music_library/v1', bank: 'femusic'
or 'cribmusic', tracks: [{wav: 'relative.wav', title: '...', artist: '...'},
{source_index: 0}, ...]}. A recipe replaces the selected bank's complete list.
WAV inputs are canonical PCM16, 22050 Hz, mono or stereo; the Music tab can
conform other inputs first. Paths resolve relative to the recipe, never cwd.

Planning only reads. A build re-plans and authenticates the source, stages
bounded chunks, writes a private sibling image, independently reopens it and
verifies every outer before atomic publication. A failure leaves source and
existing destination untouched. Earlier edits in the selected source travel
with the rebuild. No binary patches or host paths are loaded as executable code.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import time
import wave

from . import nfl2k5_music_archive as archive
from . import nfl2k5_music_metadata as metadata
from . import platform_compat as io
from tools.xbox_ima_encoder import encode_stream
from .nfl2k5_ausb_fixed_slots import decode_xbox_ima_time_block

SCHEMA = 'nfl2k5_music_library/v1'
PLAN_SCHEMA = 'nfl2k5_music_plan/v1'
MAX_SOURCE_BYTES = 512 * 1024**2
MAX_TOTAL_BYTES = 2**31 - 1
MAX_FRAMES = 600 * 22050
ENCODE_FRAMES = 64 * 128
require = archive.require


def _identity(path):
    st = Path(path).stat()
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _load(recipe):
    if isinstance(recipe, (str, Path)):
        path = Path(recipe).resolve()
        require(path.stat().st_size <= 1024**2, 'music recipe exceeds 1 MiB')
        document = json.loads(path.read_text(encoding='utf-8'))
        root = path.parent
    else:
        document = json.loads(json.dumps(recipe))
        root = Path.cwd().resolve()
    require(isinstance(document, dict) and document.get('schema') == SCHEMA, 'unsupported music recipe schema')
    require(set(document) <= {'schema', 'bank', 'tracks'}, 'unknown music recipe fields')
    require(document.get('bank') in ('femusic', 'cribmusic'), 'music libraries support femusic or cribmusic')
    tracks = document.get('tracks')
    require(isinstance(tracks, list) and 1 <= len(tracks) <= 400, 'music library needs 1..400 tracks')
    # Retail Frontend random policy divides by N-2. Two entries would divide
    # by zero; this service does not silently change the tier-1 policy owner.
    require(document['bank'] != 'femusic' or len(tracks) != 2,
            'retail menu random policy cannot play two tracks; use one or at least three')
    for track in tracks:
        require(isinstance(track, dict) and set(track) <= {'wav', 'source_index', 'title', 'artist'}, 'invalid track fields')
        require(('wav' in track) != ('source_index' in track), 'track needs exactly one of wav/source_index')
        if 'wav' in track:
            require(isinstance(track['wav'], str), 'wav path must be text')
            track['wav'] = str((root / track['wav']).resolve())
        else:
            require(type(track['source_index']) is int and track['source_index'] >= 0, 'invalid source_index')
        for key in ('title', 'artist'):
            if key in track:
                require(isinstance(track[key], str) and 1 <= len(track[key]) <= 120
                        and all(ord(c) >= 32 for c in track[key]), 'invalid track text')
    return document


def _xbe(disc):
    entry = disc.entries.get('default.xbe')
    require(entry is not None and entry.size <= 16*1024**2, 'missing/oversized default.xbe')
    return disc.read(entry.size, entry.byte_offset)


def _text(payload, va):
    at = metadata._offset(payload, va, 2)
    end = at
    while end+2 <= len(payload) and end-at <= 512 and payload[end:end+2] != b'\0\0':
        end += 2
    require(end-at <= 512 and end+2 <= len(payload), 'unbounded song string')
    return payload[at:end].decode('utf-16le')


def _existing_songs(payload):
    if metadata.status(payload) == 'applied':
        return metadata.songs(payload)
    require(metadata.status(payload) == 'retail', 'foreign jukebox metadata')
    result = [None] * 59
    for count, pointer in metadata.RETAIL:
        at = metadata._offset(payload, pointer, count*16)
        for i in range(count):
            index, title, artist, _ = struct.unpack_from('<4I', payload, at+i*16)
            result[index] = dict(title=_text(payload, title), artist=_text(payload, artist))
    return result


def _tracks(document, disc):
    bank = disc.banks[document['bank']]
    old_songs = _existing_songs(_xbe(disc)) if bank.name == 'cribmusic' else []
    if bank.name == 'cribmusic':
        require(len(old_songs) == len(bank.boundaries)-1, 'mixed bank and jukebox metadata counts')
    result = []
    for i, spec in enumerate(document['tracks']):
        item = dict(spec)
        if 'wav' in spec:
            path = Path(spec['wav'])
            before = _identity(path)
            require(path.is_file() and 0 < path.stat().st_size <= MAX_SOURCE_BYTES, 'WAV source exceeds 512 MiB')
            with wave.open(str(path), 'rb') as wav:
                require(wav.getcomptype() == 'NONE' and wav.getsampwidth() == 2
                        and wav.getframerate() == 22050 and wav.getnchannels() in (1, 2),
                        'conform input to 22050 Hz mono/stereo PCM16 WAV first')
                frames = wav.getnframes()
                require(0 < frames <= MAX_FRAMES, 'track must be nonempty and at most 10 minutes')
                channels = wav.getnchannels()
                actual = sum(len(wav.readframes(ENCODE_FRAMES)) for _ in range((frames+ENCODE_FRAMES-1)//ENCODE_FRAMES))
                require(actual == frames*channels*2, 'truncated WAV data')
            item.update(input_frames=frames, input_channels=channels, source_sha256=archive.file_hash(path))
            require(_identity(path) == before, 'WAV source changed during plan')
            default_title = path.stem
            default_artist = 'Custom'
        else:
            index = spec['source_index']
            require(index < len(bank.boundaries)-1, 'retained index outside source bank')
            frames = (bank.boundaries[index+1]-bank.boundaries[index])//(36*bank.channels)*64
            require(frames <= ((MAX_FRAMES+63)//64)*64, 'retained song exceeds ten-minute budget')
            default_title = old_songs[index]['title'] if old_songs else f'Menu {index+1:02d}'
            default_artist = old_songs[index]['artist'] if old_songs else 'Unknown'
        item['frames'] = (frames+63)//64*64
        item['title'] = item.get('title', default_title)
        item['artist'] = item.get('artist', default_artist)
        require(1 <= len(item['title']) <= 120, 'title exceeds 120 characters')
        result.append(item)
    return result


def _project(document, disc, tracks):
    names = ('cribmusic', 'crib22') if document['bank'] == 'cribmusic' else ('femusic',)
    if len(names) == 2:
        stereo, mono = (disc.banks[n] for n in names)
        require(stereo.channels == 2 and mono.channels == 1
                and stereo.boundaries == tuple(b*2 for b in mono.boundaries), 'stereo/mono twins disagree')
    descriptors, boundaries, sizes = {}, {}, {}
    total = 0
    for name in names:
        bank = disc.banks[name]
        require(bank.channels == (1 if name == 'crib22' else 2), 'foreign music channels')
        b = [0]
        for track in tracks:
            b.append(b[-1]+track['frames']//64*36*bank.channels)
        boundaries[name] = b
        total += b[-1]
        sizes[bank.external] = b[-1]
        descriptors[(bank.outer, bank.chunk)] = archive.boundary_writer(bank, b)
    require(total <= MAX_TOTAL_BYTES, 'encoded library exceeds total 2 GiB budget (including twins)')
    containers = archive.rewrite_containers(disc, descriptors)
    sizes.update({index: len(data) for index, data in containers.items()})
    geometry = archive.layout(disc, sizes)
    new_xbe, xbe_receipt = None, None
    if document['bank'] == 'cribmusic':
        song_records = [{k: t[k] for k in ('title', 'artist', 'frames')} for t in tracks]
        original_xbe = _xbe(disc)
        new_xbe, xbe_receipt = metadata.apply(original_xbe, song_records)
        if new_xbe == original_xbe:
            new_xbe = None
        elif len(new_xbe) > len(original_xbe):
            geometry['image_size'] = archive.align_up(geometry['image_size']) + len(new_xbe)
    return geometry, boundaries, containers, new_xbe, xbe_receipt, total


def plan(source, recipe):
    """Read-only, JSON-serializable plan. Limits are checked before scratch I/O."""
    start = time.monotonic()
    source = Path(source).resolve()
    document = _load(recipe)
    before = _identity(source)
    with archive.Disc(source) as disc:
        tracks = _tracks(document, disc)
        geometry, boundaries, containers, new_xbe, xbe_receipt, total = _project(document, disc, tracks)
        source_hash = archive.digest(disc.read, disc.image_size)
        require(_identity(source) == before, 'source image changed during plan')
        result = dict(schema=PLAN_SCHEMA, experimental=True, runtime_witnessed=False,
            source=str(source), source_sha256=source_hash, source_size=disc.image_size,
            recipe=document, tracks=tracks, bank=document['bank'], count=len(tracks),
            old_count=len(disc.banks[document['bank']].boundaries)-1,
            descriptor_count=len(disc.descriptor_records), boundaries=boundaries,
            descriptor_changes=[dict(outer=i, before_size=len(disc.containers[i]), after_size=len(b),
                                     before_sha256=hashlib.sha256(disc.containers[i]).hexdigest(),
                                     after_sha256=hashlib.sha256(b).hexdigest()) for i,b in containers.items()],
            encoded_bytes=total, layout=geometry, xbe=xbe_receipt,
            # Private output + encoded banks + bounded containers and encoder.
            scratch_bytes=geometry['image_size']+total+sum(map(len, containers.values()))+32*1024**2,
            same_count_fast_path=len(tracks) == len(disc.banks[document['bank']].boundaries)-1,
            planning_seconds=time.monotonic()-start)
    return result


def estimate(source, *, count=200, seconds=180, twins=False):
    """Read-only size projection with whole-block duration rounding, no WAVs."""
    require(type(count) is int and 1 <= count <= 400, 'estimate count must be 1..400')
    require(isinstance(seconds,(int,float)) and 0 < seconds <= 600, 'estimate duration must be 0..600 seconds')
    frames = (int(seconds*22050)+63)//64*64
    bank = 'cribmusic' if twins else 'femusic'
    with archive.Disc(source) as disc:
        tracks = [dict(title=f'Song {i+1:03}',artist='Custom',frames=frames) for i in range(count)]
        geometry, _, _, _, _, encoded = _project({'bank':bank},disc,tracks)
        return dict(count=count,seconds=seconds,frames_per_track=frames,twins=twins,encoded_bytes=encoded,
                    encoded_stereo_bytes=count*frames//64*72,virtual_size=geometry['virtual_size'],
                    pack_f_bytes=geometry['packs'][-1]['size'],projected_iso_bytes=geometry['image_size'],
                    iso_growth=geometry['image_size']-disc.image_size,
                    scratch_bytes=geometry['image_size']+encoded+64*1024**2)


def _pcm_channels(pcm, source_channels, target_channels):
    if source_channels == target_channels:
        return pcm
    samples = struct.unpack(f'<{len(pcm)//2}h', pcm)
    if target_channels == 1:
        # Arithmetic mean with floor rounding, on the canonical stereo timeline.
        samples = [(samples[i]+samples[i+1])//2 for i in range(0,len(samples),2)]
    else:
        samples = [s for value in samples for s in (value, value)]
    return struct.pack(f'<{len(samples)}h', *samples)


def _ima_headers(data, channels):
    require(len(data) % (36*channels) == 0, 'partial Xbox IMA block')
    for at in range(0, len(data), 36):
        require(struct.unpack_from('<H', data, at+2)[0] <= 88, 'invalid Xbox IMA step header')


def _stage(disc, planned, directory, progress):
    names = tuple(planned['boundaries'])
    paths = {name: directory / (name+'.bin') for name in names}
    hashes = {name: [] for name in names}
    with ExitStack() as stack:
        outputs = {name: stack.enter_context(path.open('wb')) for name,path in paths.items()}
        for i, track in enumerate(planned['tracks']):
            progress('encode', i, len(planned['tracks']))
            per_track = {name: hashlib.sha256() for name in names}
            def put(name, data):
                _ima_headers(data, disc.banks[name].channels)
                outputs[name].write(data)
                per_track[name].update(data)
            if 'source_index' in track:
                index = track['source_index']
                for name in names:
                    bank = disc.banks[name]
                    start, end = bank.boundaries[index:index+2]
                    quantum = 36*bank.channels*2048
                    for at in range(start, end, quantum):
                        put(name, disc.read_entry_range(disc.archive_entries[bank.external], at, min(quantum,end-at)))
            else:
                path = Path(track['wav'])
                require(archive.file_hash(path) == track['source_sha256'], 'WAV source changed before encode')
                before = _identity(path)
                with wave.open(str(path), 'rb') as wav:
                    remaining = track['input_frames']
                    while remaining:
                        count = min(ENCODE_FRAMES, remaining)
                        pcm = wav.readframes(count)
                        require(len(pcm) == count*track['input_channels']*2, 'WAV changed/truncated during encode')
                        remaining -= count
                        if not remaining:
                            # At most 63 frames. Repeat final frame, avoiding a
                            # discontinuity into zero at the last partial block.
                            width = track['input_channels']*2
                            pcm += pcm[-width:] * ((-count) % 64)
                        for name in names:
                            channels = disc.banks[name].channels
                            put(name, encode_stream(_pcm_channels(pcm, track['input_channels'], channels), channels))
                require(_identity(path) == before and archive.file_hash(path) == track['source_sha256'],
                        'WAV source changed during encode')
            for name in names:
                require(outputs[name].tell() == planned['boundaries'][name][i+1], 'staged boundary differs')
                hashes[name].append(per_track[name].hexdigest())
        for stream in outputs.values():
            stream.flush()
            os.fsync(stream.fileno())
    return paths, hashes


def _write_archive(fd, disc, geometry, containers, banks, progress):
    replacements = {disc.banks[name].external: path for name,path in banks.items()}
    table = bytearray(disc.header)
    struct.pack_into('<I', table, 12+15*4, geometry['packs'][-1]['size']//2048)
    for e in geometry['entries']:
        table.extend(struct.pack('<3I', e['name_id'], e['size'], e['offset']//2048))
    table.extend(bytes(archive.align_up(len(table))-len(table)))
    archive.write_virtual(fd, geometry['packs'], 0, table)
    # Any relocated F must receive all its bytes, even if entry positions did
    # not change (e.g. a rebuild after earlier SPECIAL disc growth).
    relocated_f = geometry['packs'][-1]['offset'] != disc.pack_extents['F'].byte_offset
    for index, e in enumerate(geometry['entries']):
        progress('archive', index, len(geometry['entries']))
        old = disc.archive_entries[index]
        unchanged = old.virtual_offset == e['offset'] and old.size == e['size']
        touches_f = e['offset'] + e['size'] > disc.packs[-1].virtual_start
        if unchanged and index not in replacements and index not in containers and not (relocated_f and touches_f):
            continue
        with ExitStack() as stack:
            if index in replacements:
                stream = stack.enter_context(replacements[index].open('rb'))
                def read(n, at):
                    stream.seek(at)
                    return stream.read(n)
            elif index in containers:
                read = lambda n, at: containers[index][at:at+n]
            else:
                read = lambda n, at: disc.read_entry_range(old, at, n)
            for at in range(0, e['size'], archive.BLOCK):
                data = read(min(archive.BLOCK,e['size']-at), at)
                require(len(data) == min(archive.BLOCK,e['size']-at), 'short archive input')
                archive.write_virtual(fd, geometry['packs'], e['offset']+at, data)
        end = e['offset']+e['size']
        padding = archive.align_up(end)-end
        if padding:
            archive.write_virtual(fd, geometry['packs'], end, bytes(padding))
    for p in geometry['packs']:
        archive.write_all(fd, struct.pack('<II', p['sector'], p['size']), p['node'])


def verify(source, output, planned, *, track_hashes=None, progress=None):
    """Fresh read-back: geometry, all outer hashes, resources, twins, samples.

    Accept a rebuild receipt as well as a plan. Hashes from the receipt let a
    later CLI invocation verify the output without reopening any source WAV.
    """
    progress = progress or (lambda *_: None)
    if 'plan' in planned:
        track_hashes = track_hashes or planned['track_sha256']
        planned = planned['plan']
    require(planned.get('schema') == PLAN_SCHEMA, 'invalid music plan')
    with archive.Disc(source) as original, archive.Disc(output) as result:
        require(archive.digest(original.read, original.image_size) == planned['source_sha256'], 'verification source differs')
        expected = planned['layout']
        require(result.image_size == expected['image_size'], 'output image size differs')
        require(len(result.archive_entries) == len(expected['entries']), 'outer count changed')
        for e, projection in zip(result.archive_entries, expected['entries']):
            require((e.table_index,e.name_id,e.virtual_offset,e.size) ==
                    (projection['index'],projection['name_id'],projection['offset'],projection['size']), 'outer geometry differs')
        for p in expected['packs']:
            entry = result.pack_extents[p['name']]
            require((entry.byte_offset, entry.size) == (p['offset'],p['size']), 'pack geometry differs')
        replacements = {original.banks[n].external for n in planned['boundaries']}
        descriptors = {}
        for name, b in planned['boundaries'].items():
            bank = original.banks[name]
            require(list(result.banks[name].boundaries) == b, 'read-back boundaries differ')
            descriptors[(bank.outer,bank.chunk)] = archive.boundary_writer(bank,b)
        containers = archive.rewrite_containers(original,descriptors)
        unaffected, outer_hashes = 0, {}
        for index in range(len(original.archive_entries)):
            progress('verify', index, len(original.archive_entries))
            actual = result.outer_hash(index)
            if index in containers:
                expected_hash = hashlib.sha256(containers[index]).hexdigest()
            elif index not in replacements:
                expected_hash = original.outer_hash(index)
                unaffected += 1
            else:
                expected_hash = actual
            require(actual == expected_hash, f'outer {index} read-back hash differs')
            outer_hashes[str(index)] = actual
        require(set(original.entries) == set(result.entries), 'named disc files changed')
        unrelated = 0
        for name, old in original.entries.items():
            if name.startswith('vc_53450030/') or old.attributes & 0x10 or (name == 'default.xbe' and planned['xbe']):
                continue
            new = result.entries[name]
            require((new.byte_offset,new.size) == (old.byte_offset,old.size), 'unrelated disc extent changed')
            require(archive.digest(lambda n,at: original.read(n,old.byte_offset+at),old.size) ==
                    archive.digest(lambda n,at: result.read(n,new.byte_offset+at),new.size), f'unrelated file differs: {name}')
            unrelated += 1
        if planned['xbe']:
            song_records = [{k:t[k] for k in ('title','artist','frames')} for t in planned['tracks']]
            expected_xbe, _ = metadata.apply(_xbe(original),song_records)
            require(_xbe(result) == expected_xbe, 'jukebox XBE read-back differs')
        samples = []
        require(track_hashes is not None, 'track hashes from rebuild receipt required for complete verification')
        for name,b in planned['boundaries'].items():
            bank = result.banks[name]
            require(len(track_hashes[name]) == len(b)-1, 'receipt track count differs')
            for index in range(len(b)-1):
                start, end = b[index:index+2]
                read = lambda n,at: result.read_entry_range(result.archive_entries[bank.external], start+at,n)
                require(archive.digest(read,end-start) == track_hashes[name][index], f'{name}:{index} hash differs')
                if index in {0,(len(b)-1)//2,len(b)-2}:
                    decoded = hashlib.sha256()
                    quantum = 36*bank.channels*2048
                    for at in range(0,end-start,quantum):
                        data = read(min(quantum,end-start-at),at)
                        _ima_headers(data,bank.channels)
                        for j in range(0,len(data),36*bank.channels):
                            decoded.update(decode_xbox_ima_time_block(data[j:j+36*bank.channels],bank.channels))
                    samples.append(dict(bank=name,index=index,frames=(end-start)//(36*bank.channels)*64,
                                        decoded_pcm_sha256=decoded.hexdigest()))
        return dict(status='verified', unaffected_outers=unaffected, outer_sha256=outer_hashes,
                    unrelated_files=unrelated, decoded_samples=samples,
                    output_sha256=archive.digest(result.read,result.image_size))


def rebuild(source, output, recipe, *, expected_plan=None, overwrite=False, progress=None):
    """Transactional public build. All writers operate on a private image."""
    start = time.monotonic()
    progress = progress or (lambda *_: None)
    require(not Path(output).is_symlink(), 'output cannot be a symlink')
    source, output = Path(source).resolve(), Path(output).resolve()
    require(source != output and (not output.exists() or not os.path.samefile(source,output)), 'output must be a separate copy')
    require(not output.exists() or overwrite, 'output exists; overwrite was not selected')
    target_before = _identity(output) if output.exists() else None
    planned = plan(source,recipe)
    inputs = [Path(t['wav']) for t in planned['tracks'] if 'wav' in t]
    if isinstance(recipe,(str,Path)):
        inputs.append(Path(recipe).resolve())
    require(all(output != p and (not output.exists() or not os.path.samefile(output,p)) for p in inputs),
            'output aliases a music source/recipe')
    if expected_plan is not None:
        wanted = dict(expected_plan)
        fresh = dict(planned)
        wanted.pop('planning_seconds',None)
        fresh.pop('planning_seconds',None)
        require(wanted == fresh, 'stale music plan; source or recipe changed')
    require(output.parent.is_dir(), 'output parent does not exist')
    require(shutil.disk_usage(output.parent).free >= planned['scratch_bytes'], 'insufficient scratch space')
    source_before = _identity(source)
    with tempfile.TemporaryDirectory(prefix='.music-',dir=output.parent) as temp:
        directory = Path(temp).resolve()
        staged = directory/'image.iso'
        with archive.Disc(source) as disc:
            geometry, _, containers, new_xbe, _, _ = _project(planned['recipe'],disc,planned['tracks'])
            require(geometry == planned['layout'], 'source layout changed after planning')
            banks, hashes = _stage(disc,planned,directory,progress)
            progress('copy',0,disc.image_size)
            # Copy from the same open reader used by the plan projection.
            with staged.open('wb') as stream:
                for at in range(0,disc.image_size,archive.BLOCK):
                    stream.write(disc.read(min(archive.BLOCK,disc.image_size-at),at))
            fd = os.open(staged,os.O_RDWR | getattr(os,'O_BINARY',0))
            try:
                _write_archive(fd,disc,geometry,containers,banks,progress)
                if new_xbe is not None:
                    archive.write_named(fd,lambda n,at: io.pread(fd,n,at),disc.partition,'default.xbe',
                                        lambda n,at: new_xbe[at:at+n],len(new_xbe))
                os.fsync(fd)
            finally:
                os.close(fd)
        checked = verify(source,staged,planned,track_hashes=hashes,progress=progress)
        require(_identity(source) == source_before and archive.file_hash(source) == planned['source_sha256'],
                'source changed during build; output discarded')
        require((_identity(output) if output.exists() else None) == target_before, 'destination changed during build')
        # Every reader/writer is closed, including failed-constructor readers.
        os.replace(staged,output)
    return dict(schema='nfl2k5_music_receipt/v1',experimental=True,runtime_witnessed=False,
                output=str(output),plan=planned,track_sha256=hashes,verification=checked,
                elapsed_seconds=time.monotonic()-start)

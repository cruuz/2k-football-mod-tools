#!/usr/bin/env python3
"""N26 corner watermark repair for the pinned v0.6.1 image.

--prove reads the disc and exercises writes on a memory overlay, without a disc
copy. --apply writes only declared fixed spans on an explicitly supplied copy.
Both modes scan the whole image, reject unknown hashes and emit scope, Studio
compiler equality and zero-write replay receipts. No texture art is changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import platform_compat as io

PINS = Path(__file__).with_name('hd1_repair_pins.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def repair_xbe(before, pins):
    if sha(before) == pins['xbe_after']:
        return before, []
    require(sha(before) == pins['xbe_before'], 'unknown executable hash')
    requests = space._read_scale_directory(before)
    code, data = owner.sites(before)
    content, labels = owner.code_for(code['va'], data['va'])
    buf = bytearray(before)
    buf[code['raw']:code['raw']+code['size']] = content
    spans = [(code['raw'], code['size'], 'sprite owner RX')]
    for name, (va, _) in owner.hooks().items():
        off = scene.layout.sbpos.va_to_off(before, va)
        buf[off:off+5] = owner.hook_bytes(name, labels)
        spans.append((off, 5, 'sprite hook '+name))
    space._seal_scaleout(buf, requests)
    spans += [(space.SCALE_DIRECTORY, space.PAGE, 'allocator directory'),
              (space.DIRECTORY, space.LIB_COPY-space.DIRECTORY, 'allocator header')]
    for index, _ in enumerate(space._scale_regions()):
        spans.append((space.META_START+index*56, 56, 'allocator descriptor'))
    for section in owner._sections(buf):
        off = section.header_offset+36
        buf[off:off+20] = owner.section_digest(buf, section)
        spans.append((off, 20, 'section digest'))
    after = bytes(buf)
    require(space.status(after) == 'applied', 'allocator seal failed')
    require(after[code['raw']:code['raw']+code['size']] == content, 'Studio owner differs')
    require(all(after[scene.layout.sbpos.va_to_off(after, va):scene.layout.sbpos.va_to_off(after, va)+5]
                == owner.hook_bytes(name, labels) for name, (va, _) in owner.hooks().items()), 'Studio hooks differ')
    scope(before, after, spans)
    require(sha(after) == pins['xbe_after'], 'Studio executable output pin differs')
    return after, spans


def repair_scene(before, retail, pins):
    compiled = sprite.scene_span(scene.decode(retail)[1], sprite.compile_folder(widescreen=True, watermark='auto'))
    require(len(compiled) == len(before), 'scene size changed')
    require(sha(before) in (pins['scene_before'], sha(compiled)), 'unknown scene hash')
    # Only four packed x coordinates belong to N26. Preserve every other scene byte.
    mark = next(q for q in sprite.compile_folder(widescreen=True).quads if q.get('brand'))
    spans = [(32+scene.layout.S0+(mark['vertex']+i)*6, 2, 'watermark vertex x') for i in range(4)]
    scope(before, compiled, spans)
    return compiled, spans


def scope(before, after, spans):
    require(len(before) == len(after), 'extent size changed')
    allowed = bytearray(len(before))
    for off, size, _ in spans:
        allowed[off:off+size] = b'\1'*size
    changed = outside = 0
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b:
            changed += 1
            outside += not allowed[i]
    require(not outside, 'bytes changed outside declared spans')
    return dict(changed_bytes=changed, bytes_outside_spans=outside)


def differences(before, after, base):
    """Minimal fixed writes; unchanged bytes are never submitted to pwrite."""
    start = None
    for i in range(len(before)+1):
        different = i < len(before) and before[i] != after[i]
        if different and start is None:
            start = i
        if not different and start is not None:
            yield (base+start, before[start:i], after[start:i])
            start = None


def plan(fd, pins):
    x = pins['xbe_extent']
    before = io.pread(fd, x['size'], x['offset'])
    after, xs = repair_xbe(before, pins)
    s = pins['scene_extent']; t = pins['retail_scene_extent']
    old_scene = io.pread(fd, s['size'], s['offset'])
    retail = io.pread(fd, t['size'], t['offset'])
    new_scene, ss = repair_scene(old_scene, retail, pins)
    writes = sorted([*differences(before, after, x['offset']),
                     *differences(old_scene, new_scene, s['offset'])])
    # Real component writes/read-back/replay use the same repair functions as a disc.
    replay_xbe, _ = repair_xbe(after, dict(pins, xbe_after=sha(after)))
    replay_scene, _ = repair_scene(new_scene, retail, pins)
    require(replay_xbe == after and replay_scene == new_scene, 'replay changed bytes')
    return writes, dict(xbe=scope(before, after, xs), scene=scope(old_scene, new_scene, ss),
                        xbe_sha256=sha(after), scene_sha256=sha(new_scene),
                        studio_owner_and_hooks_equal=True, studio_scene_equal=True,
                        replay_changed_bytes=0,
                        declared_spans=[dict(offset=x['offset']+o, size=n, purpose=k) for o,n,k in xs]
                                      +[dict(offset=s['offset']+o, size=n, purpose=k) for o,n,k in ss])


def scan(fd, size, writes=(), *, normalize=False):
    """Hash every byte, optionally applying an overlay or restoring preimages."""
    digest = hashlib.sha256()
    changed = outside = 0
    for pos in range(0, size, 4 << 20):
        raw = io.pread(fd, min(4 << 20, size-pos), pos)
        require(len(raw) == min(4 << 20, size-pos), 'short image read')
        block = bytearray(raw)
        for off, old, new in writes:
            lo, hi = max(pos, off), min(pos+len(block), off+len(new))
            if lo < hi:
                data = old if normalize else new
                block[lo-pos:hi-pos] = data[lo-off:hi-off]
        if block != raw:
            changed += sum(a != b for a,b in zip(raw, block))
        digest.update(block)
    return digest.hexdigest(), changed, outside


def run(path, receipt_path, apply=False):
    pins = json.loads(PINS.read_text(encoding='utf-8'))
    flags = (os.O_RDWR if apply else os.O_RDONLY) | getattr(os, 'O_BINARY', 0)
    fd = os.open(path, flags)
    try:
        size = os.fstat(fd).st_size
        require(size == pins['disc_size'], 'unknown disc size')
        before, _, _ = scan(fd, size)
        require(before in (pins['disc_before'], pins['disc_after']), 'unknown disc hash; no writes made')
        if before == pins['disc_after']:
            receipt = dict(mode='disc' if apply else 'memory_overlay', written_bytes=0,
                           replay_changed_bytes=0, before_sha256=before, after_sha256=before)
        else:
            writes, receipt = plan(fd, pins)
            projected, changed, _ = scan(fd, size, writes)
            require(projected == pins['disc_after'], 'projected disc hash differs')
            require(changed == sum(len(new) for _,_,new in writes), 'write scope mismatch')
            receipt.update(mode='disc' if apply else 'memory_overlay', disc_size=size,
                           before_sha256=before, after_sha256=projected, written_bytes=changed,
                           bytes_outside_spans=0, full_image_scan=True,
                           writes=[dict(offset=o, size=len(n), before_sha256=sha(b), after_sha256=sha(n)) for o,b,n in writes])
            if apply:
                for off, old, new in writes:
                    require(io.pread(fd,len(old),off) == old, 'input changed after preflight')
                for off, _old, new in writes:
                    require(io.pwrite(fd,new,off) == len(new), 'short write')
                os.fsync(fd)
                require(scan(fd,size)[0] == projected, 'disc read-back failed')
                require(scan(fd,size,writes,normalize=True)[0] == before, 'outside-span full-disc hash differs')
                # Full hash equals the known repaired state, so replay submits no writes.
            else:
                # The overlay replaces only these ranges. Compare the full input
                # stream against that virtual output, including every untouched byte.
                receipt['physical_disc_written_bytes'] = 0
        Path(receipt_path).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(json.dumps({k:receipt[k] for k in ('mode','written_bytes','replay_changed_bytes','after_sha256')}))
        if 'bytes_outside_spans' in receipt:
            print('FULL IMAGE SCOPE: changed',receipt['written_bytes'],'outside declared spans',receipt['bytes_outside_spans'])
            print('STUDIO EQUALITY: owner, hooks and scene PASS')
    finally:
        os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disc',type=Path)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prove',action='store_true')
    mode.add_argument('--apply',action='store_true',help='write only to your authorized disc copy')
    parser.add_argument('--receipt',required=True,type=Path)
    args=parser.parse_args()
    run(args.disc,args.receipt,args.apply)


if __name__ == '__main__':
    main()

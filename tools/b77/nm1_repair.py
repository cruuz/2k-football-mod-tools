#!/usr/bin/env python3
"""Pinned, fixed-span nm1 repair using the Studio indicator compiler.

placeholder --retail ISO --out PRIVATE_FOLDER
disc --before BASE_ISO --disc COPY --atlas FOLDER --receipt JSON
scope --before BASE_ISO --disc COPY --atlas FOLDER --receipt JSON
The retail-derived placeholder must remain private and is identified in receipts.
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
from mod_editor.core import nfl2k5_indicator_names as names, xdvdfs_compact as xd

BASE_SHA256 = "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4"


def require(ok, message):
    if not ok:
        raise ValueError("nm1 repair refused: " + message)


def binary(path):
    return os.fdopen(os.open(path, os.O_RDONLY | getattr(os,"O_BINARY",0)), "rb")


def digest(stream, replacements=()):
    stream.seek(0)
    h = hashlib.sha256()
    at = 0
    while block := stream.read(8 << 20):
        for offset, data in replacements:
            lo, hi = max(at,offset), min(at+len(block),offset+len(data))
            if lo < hi:
                block = block[:lo-at]+data[lo-offset:hi-offset]+block[hi-at:]
        h.update(block)
        at += len(block)
    return h.hexdigest()


def plan(before, target, atlas):
    require(not os.path.samefile(before,target), "base and writable copy are the same file")
    require(before.stat().st_size == target.stat().st_size, "disc sizes differ")
    with binary(before) as src:
        require(digest(src) == BASE_SHA256, "unknown complete base disc hash")
        edits, receipt = names.image_plan(src,atlas)
    require(all(a != b for _,a,b,_ in edits), "base is already modified")
    with binary(target) as dst:
        for off,old,new,label in edits:
            dst.seek(off)
            require(dst.read(len(old)) in (old,new), "unknown bytes in " + label)
        require(digest(dst, [(off,old) for off,old,_,_ in edits]) == BASE_SHA256,
                "unknown complete input disc hash outside owned spans")
    return edits, receipt


def repair(before, target, atlas):
    edits, expected = plan(before,target,atlas)
    with binary(target) as src:
        prior = digest(src)
    receipt = names.apply_to_image(target,folder=atlas)
    with binary(target) as src:
        for off,old,new,label in edits:
            src.seek(off)
            require(src.read(len(new)) == new, "Studio output mismatch: " + label)
        require(digest(src,[(off,old) for off,old,_,_ in edits]) == BASE_SHA256,
                "out-of-scope bytes changed")
        after = digest(src)
    replay = names.apply_to_image(target,folder=atlas)
    require(replay["bytes_written"] == 0, "replay wrote bytes")
    return dict(receipt, schema="b773/nm1-repair/v1", before_sha256=prior, after_sha256=after,
                canonical_base_sha256=BASE_SHA256, studio_equal=True,
                replay_bytes_written=0, outside_scope_changed_bytes=0,
                studio_font_sha256=expected["font"]["font_sha256"])


def scope(before,target,atlas):
    edits, expected = plan(before,target,atlas)
    spans = [(off,off+len(old)) for off,old,_,_ in edits]
    changed=outside=at=0
    with binary(before) as a,binary(target) as b:
        while old := a.read(8 << 20):
            new=b.read(len(old))
            require(len(old)==len(new), "short comparison read")
            if old != new:
                for i,(x,y) in enumerate(zip(old,new)):
                    if x != y:
                        changed+=1
                        outside+=not any(lo<=at+i<hi for lo,hi in spans)
            at+=len(old)
        require(not b.read(1), "trailing disc bytes")
    require(outside==0,"full-disc comparison found out-of-scope differences")
    with binary(target) as stream:
        for off,old,new,label in edits:
            stream.seek(off)
            require(stream.read(len(new))==new,"repaired bytes differ from Studio output")
    return dict(schema="b773/nm1-scope/v1",compared_bytes=at,changed_bytes=changed,
                outside_scope_changed_bytes=outside,studio_equal=True,
                spans=[dict(offset=o,size=len(a),purpose=l) for o,a,b,l in edits],
                font=expected["font"])


def placeholder(retail,out):
    names._tools()
    import nfl_outer as outer
    import nfl_txtr as tx
    with binary(retail) as f:
        e=xd.read_layout(f).entries["vc_53450030/0"]
        f.seek(e.byte_offset+outer.HEADER_SIZE+3*12)
        identity,size,sector=struct.unpack("<3I",f.read(12))
        require(identity==0x8EE9EEED and size==2387424,"unknown font collection")
        f.seek(e.byte_offset+sector*2048)
        fonts=f.read(size)
        ch=tx.parse_chunks(fonts)[3]
        names.export_placeholder(fonts[ch.offset:ch.offset+32+ch.stored_size],out)
    _,r=names.compile_font(out)
    return dict(r,warning="PLACEHOLDER: retail-derived test asset; do not ship")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("placeholder")
    p.add_argument("--retail",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    for command in ("disc","scope"):
        p=sub.add_parser(command)
        for key in ("before","disc","atlas","receipt"):
            p.add_argument("--"+key,type=Path,required=True)
    args=parser.parse_args()
    if args.command=="placeholder":
        result=placeholder(args.retail,args.out)
    else:
        result=(repair if args.command=="disc" else scope)(args.before,args.disc,args.atlas)
        args.receipt.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()

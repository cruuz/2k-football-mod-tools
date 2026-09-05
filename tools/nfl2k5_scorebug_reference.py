#!/usr/bin/env python3
"""Build, preview or stage the experimental reference scorebug, entirely offline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
for entry in (ROOT,ROOT/"tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0,str(entry))
from mod_editor.core import nfl2k5_scorebug_ingame as r
import nfl2k5_scorebug_layout as layout


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")


def apply_copy(source: Path,target: Path, *, overwrite: bool=False):
    source=source.resolve(strict=True)
    target=target.absolute()
    if target.is_symlink() or source == target.resolve() or (target.exists() and os.path.samefile(source,target)):
        raise r.ScorebugError("output must be a separate, non-symlink copy")
    if target.exists() and not overwrite:
        raise r.ScorebugError("output already exists")
    with source.open("rb") as stream:
        # Full plan before copying; any foreign resource fails without an output.
        r.image_plan(stream.fileno(),os.fstat(stream.fileno()).st_size)
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".scorebug-",suffix=".iso",dir=target.parent.resolve())
    os.close(fd)
    temporary=Path(name).resolve()
    try:
        shutil.copyfile(source,temporary)
        receipt=r.apply_in_place(temporary)
        # Every reader/writer is closed before Windows/macOS publication.
        os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    return receipt


def panels(source,away,home):
    from PIL import Image
    out={}
    with source.open("rb") as stream:
        fd=stream.fileno()
        base,size=layout.xc.pack_extent(fd,os.fstat(fd).st_size,"0")
        if size != r.PACK_SIZE:
            raise r.ScorebugError("pack 0 size changed")
        for side,team in (("away",away),("home",home)):
            record=r.TEAM_LOGOS[team]
            span=layout._pread(fd,record["span_size"],base+record["pack_offset"])
            data,_=r.stage_team_panel(span,team,side=side)
            out[side]=Image.frombytes("RGBA",(128,32),data)
    return out


def stage(source: Path,output: Path):
    from PIL import Image
    output.mkdir(parents=True,exist_ok=True)
    receipts=[]
    with source.open("rb") as stream:
        fd=stream.fileno()
        base,size=layout.xc.pack_extent(fd,os.fstat(fd).st_size,"0")
        if size != r.PACK_SIZE:
            raise r.ScorebugError("pack 0 size changed")
        scene=r.RESOURCES["score_bug"]
        span=layout._pread(fd,scene["span_size"],base+scene["pack_offset"])
        binding,receipt=r.stage_binding_scene(span)
        (output/"binding_scene.span").write_bytes(binding)
        write_json(output/"binding_scene.json",receipt)
        for team,record in sorted(r.TEAM_LOGOS.items()):
            span=layout._pread(fd,record["span_size"],base+record["pack_offset"])
            for side in ("away","home"):
                data,receipt=r.stage_team_panel(span,team,side=side)
                stem=f"{team}_{side}"
                (output/(stem+".rgba")).write_bytes(data)
                Image.frombytes("RGBA",(128,32),data).save(output/(stem+".png"))
                receipts.append(receipt)
    write_json(output/"receipts.json",receipts)
    return receipts


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("apply");a.add_argument("source",type=Path);a.add_argument("target",type=Path)
    a.add_argument("--overwrite",action="store_true")
    a=sub.add_parser("preview");a.add_argument("out",type=Path);a.add_argument("--source",required=True,type=Path)
    a.add_argument("--widest",action="store_true");a.add_argument("--matchup",nargs=2,choices=sorted(r.TEAM_LOGOS))
    a=sub.add_parser("stage");a.add_argument("source",type=Path);a.add_argument("output",type=Path)
    a=sub.add_parser("status");a.add_argument("source",type=Path)
    a=sub.add_parser("scne");a.add_argument("retail_scne",type=Path);a.add_argument("out_scne",type=Path)
    a.add_argument("--span",required=True,type=Path)
    args=p.parse_args(argv)
    try:
        if args.command=="apply":
            receipt=apply_copy(args.source,args.target,overwrite=args.overwrite)
            write_json(Path(str(args.target)+".scorebug.json"),receipt)
            print(json.dumps(receipt,indent=2))
        elif args.command=="preview":
            m,texture=r.preview_data(args.source)
            team_panels=panels(args.source,*args.matchup) if args.matchup else None
            layout.preview_reference(m,texture,args.out,widest=args.widest,team_panels=team_panels)
            print(args.out)
        elif args.command=="stage":
            receipts=stage(args.source,args.output)
            print(f"Staged {len(receipts)} panels. Runtime binding is not installed.")
        elif args.command=="status":
            print(r.image_status(args.source))
        else:
            span=args.span.read_bytes()
            decoded=r.pinned(span,r.RESOURCES["score_bug"])
            if decoded != args.retail_scne.read_bytes():
                raise r.ScorebugError("scene and template disagree")
            result,receipt=r.apply(span,"score_bug")
            args.out_scne.write_bytes(r.decode(result)[1])
            write_json(Path(str(args.out_scne)+".receipt.json"),receipt)
        return 0
    except (OSError,ValueError,KeyError) as exc:
        p.exit(2,f"scorebug: {exc}\n")


if __name__=="__main__":
    raise SystemExit(main())

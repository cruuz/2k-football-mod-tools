#!/usr/bin/env python3
"""EXPERIMENTAL / UNWITNESSED music library planner, builder and verifier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_music_banks as banks
from mod_editor.core.nfl2k5_music_archive import Disc


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('inventory','estimate','plan','rebuild','verify'):
        p=commands.add_parser(name)
        p.add_argument('source',type=Path)
        p.add_argument('--json',type=Path,required=True,help='new JSON output (never overwrites an existing file)')
        if name in ('plan','rebuild'): p.add_argument('recipe',type=Path)
        if name in ('rebuild','verify'): p.add_argument('output',type=Path)
        if name=='rebuild':
            p.add_argument('--plan',type=Path)
            p.add_argument('--overwrite',action='store_true')
        if name=='verify': p.add_argument('receipt',type=Path)
        if name=='estimate':
            p.add_argument('--count',type=int,default=200)
            p.add_argument('--seconds',type=float,default=180)
            p.add_argument('--twins',action='store_true')
    args=parser.parse_args(argv)
    # Refuse an output collision before any expensive build/publication.
    if args.json.exists(): parser.error('JSON output already exists')
    if not args.json.parent.is_dir(): parser.error('JSON output parent does not exist')
    inputs=[args.source]+[getattr(args,n) for n in ('recipe','output','receipt','plan') if getattr(args,n,None)]
    if args.json.resolve() in [p.resolve() for p in inputs]: parser.error('JSON output aliases an input/image')
    last=0
    def progress(stage,done,total):
        nonlocal last
        if time.monotonic()-last>10:
            print(f'{stage}: {done}/{total}',file=sys.stderr,flush=True);last=time.monotonic()
    if args.command=='inventory':
        with Disc(args.source) as disc:
            result=dict(outers=len(disc.archive_entries),descriptors=[dict(bank=d.name,outer=d.outer,chunk=d.chunk,
                        offset=d.offset,body_bytes=len(d.raw)-32,channels=d.channels,count=len(d.boundaries)-1,
                        boundaries=d.boundaries) for d in disc.descriptor_records])
    elif args.command=='estimate': result=banks.estimate(args.source,count=args.count,seconds=args.seconds,twins=args.twins)
    elif args.command=='plan': result=banks.plan(args.source,args.recipe)
    elif args.command=='rebuild':
        planned=json.loads(args.plan.read_text()) if args.plan else None
        result=banks.rebuild(args.source,args.output,args.recipe,expected_plan=planned,overwrite=args.overwrite,progress=progress)
    else:
        result=banks.verify(args.source,args.output,json.loads(args.receipt.read_text()),progress=progress)
    with args.json.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(f'{args.command} complete: {args.json}')
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,EOFError) as exc: raise SystemExit(f'error: {exc}')

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
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8",newline="\n")


def apply_copy(source: Path,target: Path, *, overwrite: bool=False, runtime: bool=False, with_kickoff: bool=False):
    if with_kickoff and not runtime:
        raise r.ScorebugError("relocated kickoff requires --runtime")
    source=source.resolve(strict=True)
    target=target.absolute()
    if target.is_symlink() or source == target.resolve() or (target.exists() and os.path.samefile(source,target)):
        raise r.ScorebugError("output must be a separate, non-symlink copy")
    if target.exists() and not overwrite:
        raise r.ScorebugError("output already exists")
    with source.open("rb") as stream:
        # Full plan before copying; any foreign resource fails without an output.
        if runtime:
            r.runtime_image_plan(stream.fileno(), with_kickoff=with_kickoff)
        else:
            r.image_plan(stream.fileno(),os.fstat(stream.fileno()).st_size)
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".scorebug-",suffix=".iso",dir=target.parent.resolve())
    os.close(fd)
    temporary=Path(name).resolve()
    try:
        shutil.copyfile(source,temporary)
        receipt=(r.runtime_apply_in_place(temporary, with_kickoff=with_kickoff) if runtime else r.apply_in_place(temporary))
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


def runtime_preview(source, output, *, matchup=("LV", "HOU"), timeouts=(3, 3),
                    play_clock=12, score_flash=None, slide=1, widest=False):
    """Render the compiled scene and selected native P8 resources, not RGBA targets."""
    from PIL import Image
    from mod_editor.core import nfl2k5_scorebug_resources as art
    with Path(source).open("rb") as stream:
        base, size = layout.xc.pack_extent(stream.fileno(), os.fstat(stream.fileno()).st_size, "0")
        if size not in (r.PACK_SIZE, r.PACK_SIZE + art.RUNTIME_GROWTH):
            raise r.ScorebugError("unknown runtime pack extent")
        pack = layout._pread(stream.fileno(), size, base)
    if art.runtime_pack_status(pack) == "retail":
        pack, _ = art.compile_runtime_collection(pack)
    if art.runtime_pack_status(pack) != "applied":
        raise r.ScorebugError("foreign runtime scorebug resources")
    def decode_image(span):
        c, d, _ = r.decode(span);t = r.tx.parse_texture(d, c)
        return Image.frombytes("RGBA", (t.width, t.height), r.tx.texture_to_rgba(d, c, t))
    scene = art.RESOURCES["score_bug"]
    m = layout.Mesh(r.decode(pack[scene["pack_offset"]:scene["pack_offset"]+scene["span_size"]])[1], runtime=True)
    atlas = art.RESOURCES["score_buga"]
    texture = decode_image(pack[atlas["pack_offset"]:atlas["pack_offset"]+atlas["span_size"]])
    wanted = {art.runtime_panel_name(art.TEAM_LOGOS[team]["asset_code"], side, count): side
              for side, team, count in zip(("away", "home"), matchup, timeouts)}
    panels = {};selected = {}
    for offset in range(art.HUD_START + art.HUD_SIZE, art.HUD_START + art.HUD_SIZE + art.RUNTIME_APPEND_SIZE, art.RUNTIME_TEXTURE_SPAN):
        span = pack[offset:offset + art.RUNTIME_TEXTURE_SPAN]
        c, d, _ = r.decode(span);name = r.tx.parse_texture(d,c).name
        if name in wanted:
            panels[wanted[name]] = decode_image(span);selected[wanted[name]] = name
    if len(panels) != 2:
        raise r.ScorebugError("missing selected runtime texture")
    colors = {}
    if 0 <= play_clock < 5:colors["drop_clock"] = (208, 2, 27, 255)
    if score_flash:colors[score_flash+"_score"] = (255, 209, 102, 255)
    import math
    samples = {"away_city":matchup[0], "home_city":matchup[1], "drop_clock":f":{max(0,math.ceil(play_clock)):02d}"}
    layout.preview_reference(m,texture,Path(output),widest=widest,team_panels=panels,samples=samples,
                             runtime=True,text_colors=colors,slide=slide)
    receipt = dict(version=art.RUNTIME_VERSION, experimental=True, runtime_witnessed=False,
                   static_preview=True, selected=selected, timeouts=list(timeouts), play_clock=play_clock,
                   score_flash=score_flash, native_slide_fraction=slide,
                   scene_sha256=r.digest(bytes(m.buf)), font="approximation")
    write_json(Path(str(output)+".json"),receipt)
    return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("apply");a.add_argument("source",type=Path);a.add_argument("target",type=Path)
    a.add_argument("--overwrite",action="store_true")
    a.add_argument("--runtime",action="store_true")
    a.add_argument("--relocated-kickoff",action="store_true")
    a=sub.add_parser("preview");a.add_argument("out",type=Path);a.add_argument("--source",required=True,type=Path)
    a.add_argument("--widest",action="store_true");a.add_argument("--matchup",nargs=2,choices=sorted(r.TEAM_LOGOS))
    a.add_argument("--runtime",action="store_true")
    a.add_argument("--timeouts",type=int,nargs=2,choices=range(4),default=(3,3),metavar=("AWAY","HOME"))
    a.add_argument("--play-clock",type=float,default=12)
    a.add_argument("--score-flash",choices=("home","away"))
    a.add_argument("--slide",type=float,default=1)
    a=sub.add_parser("stage");a.add_argument("source",type=Path);a.add_argument("output",type=Path)
    a=sub.add_parser("status");a.add_argument("source",type=Path)
    a.add_argument("--runtime",action="store_true")
    a=sub.add_parser("scne");a.add_argument("retail_scne",type=Path);a.add_argument("out_scne",type=Path)
    a.add_argument("--span",required=True,type=Path)
    args=p.parse_args(argv)
    try:
        if args.command=="apply":
            receipt=apply_copy(args.source,args.target,overwrite=args.overwrite,runtime=args.runtime,with_kickoff=args.relocated_kickoff)
            write_json(Path(str(args.target)+".scorebug.json"),receipt)
            print(json.dumps(receipt,indent=2))
        elif args.command=="preview":
            if args.runtime:
                runtime_preview(args.source,args.out,matchup=args.matchup or ("LV","HOU"),
                                timeouts=args.timeouts,play_clock=args.play_clock,
                                score_flash=args.score_flash,slide=args.slide,widest=args.widest)
                print(args.out)
                return 0
            m,texture=r.preview_data(args.source)
            team_panels=panels(args.source,*args.matchup) if args.matchup else None
            layout.preview_reference(m,texture,args.out,widest=args.widest,team_panels=team_panels)
            print(args.out)
        elif args.command=="stage":
            receipts=stage(args.source,args.output)
            print(f"Staged {len(receipts)} panels. Runtime binding is not installed.")
        elif args.command=="status":
            print(r.runtime_image_status(args.source) if args.runtime else r.image_status(args.source))
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

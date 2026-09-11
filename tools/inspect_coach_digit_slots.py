#!/usr/bin/env python3
"""Read-only retail measurements and synthetic Coach Edwards regression study.

Writes measurements and synthetic-only art. Never exports retail pixels.
"""
from __future__ import annotations
import argparse
from collections import Counter, deque
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/fixtures")]
from PIL import Image, ImageDraw
from coach_digit_cases import ai_digit
from mod_editor.core.nfl2k5_digit_art import measure, prepare_digit, prepared_mips, edge_quantizer
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips, quantize_digit_levels, resize_cell
from mod_editor.core.nfl2k5_digit_preview import decode_digit_texture, render_digit_sample, _filtered_level
import nfl_live_numbers_nameplate_png_import as writer
from nfl_live_numbers_nameplate_targets import select_target, DEFAULT_REPORT
from nfl_tset_png_import import palette_bytes, rgba_from_indices, QualityBudgetError
from nfl_txtr import compress_vc_lz, swizzle_2d


def alpha_band(image):
    alpha = image.getchannel("A").tobytes()
    distances = [0 if a >= 240 else -1 for a in alpha]
    queue = deque(i for i, d in enumerate(distances) if d == 0)
    width, height = image.size
    while queue:
        i = queue.popleft(); x, y = i % width, i // width
        for dx, dy in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            if 0 <= x+dx < width and 0 <= y+dy < height:
                j=(y+dy)*width+x+dx
                if distances[j] < 0:
                    distances[j] = distances[i]+1; queue.append(j)
    return max((distances[i] for i,a in enumerate(alpha) if 0 < a < 240), default=0)


def border_alpha(mip):
    image=Image.frombytes('RGBA',(mip.width,mip.height),mip.rgba).getchannel('A')
    return max(max(image.crop(box).getdata()) for box in (
        (0,0,mip.width,1),(0,mip.height-1,mip.width,mip.height),
        (0,0,1,mip.height),(mip.width-1,0,mip.width,mip.height)))


def run(index, output):
    started=time.monotonic(); archive=writer.parse_archive(index); rows=[]
    figure=Image.new('RGB',(840,920),(245,245,245)); draw=ImageDraw.Draw(figure)
    draw.text((8,6),'SYNTHETIC ART ONLY: old 16-colour result / registered build result',fill='black')
    for col,size in enumerate((64,32,16,8)):
        draw.text((155+col*170,28),f'{size}px: old / build',fill='black')
    with tempfile.TemporaryDirectory(prefix="coach-digit-study-") as temp:
        png=Path(temp)/"digit.png"
        for code,side,variant in (("26","A",0),("06","H",0),("26","A",3)):
            for family in ("jersey","arm","helmet"):
                for digit in range(10):
                    target=select_target(family,code,side,variant,digit)[-1]
                    span=writer.read_entry_range(archive,archive.entries[target.outer_index],target.chunk_offset,target.span_size)
                    chunk,decoded,texture=writer.validate_template(span,target)
                    retail=decode_digit_texture(span)
                    base=retail.levels[0]
                    image=Image.frombytes("RGBA",(base.width,base.height),base.rgba)
                    recompressed,_=compress_vc_lz(decoded,stream_tag=target.stream_tag,offset_bits=target.offset_bits)
                    row={"selector":target.selector,"dimensions":[base.width,base.height],
                         "stored_size":target.stored_size,"retail_consumed":target.lz_consumed_bytes,
                         "retail_recompressed":len(recompressed),"retail_registration":measure(image),
                         "retail_alpha_nonzero_box":image.getchannel("A").getbbox(),
                         "retail_max_partial_band":alpha_band(image),
                         "retail_base_colours":len(set(zip(*[iter(base.rgba)]*4))),
                         "retail_chain_colours":len(set(c for m in retail.levels for c in zip(*[iter(m.rgba)]*4))),
                         "retail_mip_border_alpha_max":[border_alpha(m) for m in retail.levels],
                         "retail_partial_texels":sum(0<a<255 for a in base.rgba[3::4])}
                    if family == "helmet":
                        rows.append(row); continue
                    authored=resize_cell(ai_digit(digit),(base.width,base.height))
                    authored.save(png)
                    levels=make_digit_mips(authored.tobytes(),base.width,base.height,target.mip_levels)
                    gap=decoded[target.system_bytes+target.index_chain_bytes:target.system_bytes+target.palette_offset]
                    tiers=[]
                    for maximum in (256,128,64,32,16):
                        palette,indices,_=quantize_digit_levels(levels,maximum)
                        candidate=decoded[:target.system_bytes]+b"".join(swizzle_2d(i,m.width,m.height,1) for i,m in zip(indices,levels))+gap+palette_bytes(palette)
                        encoded,_=compress_vc_lz(candidate,stream_tag=target.stream_tag,offset_bits=target.offset_bits)
                        tiers.append({"tier":maximum,"colours":len(palette),"bytes":len(encoded),"fits":len(encoded)<=target.stored_size})
                    row.update({"authored_registration":measure(authored),"old_tiers":tiers})
                    try:
                        result,_,receipt=writer.build_import(index,DEFAULT_REPORT,family,code,side,variant,digit,png)
                        actual=decode_digit_texture(result)
                        row.update({"outcome":"authored","preparation":receipt["digit_preparation"],
                                    "encoded_bytes":receipt["rebuild"]["recompressed_bytes"],
                                    "palette_entries":receipt["quantization"]["palette_entries"],
                                    "written_mip_border_alpha_max":[border_alpha(m) for m in actual.levels]})
                    except QualityBudgetError as exc:
                        actual=retail
                        row.update({"outcome":"kept_retail","reason":str(exc),"attempts":exc.attempts})
                    # Render both actual and retail at identical selected mip
                    # levels, entirely in memory. Retain only comparison hashes.
                    row['renders']=[]
                    for s in (64,32,16,8):
                        level=max(0,min(len(actual.levels)-1,int(math.log2(base.height/s))))
                        shown=render_digit_sample(actual,height=s,level=level)
                        original=render_digit_sample(retail,height=s,level=level)
                        comparison=Image.new('RGB',(s*2,s)); comparison.paste(shown,(0,0)); comparison.paste(original,(s,0))
                        row['renders'].append({'size':s,'level':level,'actual_sha256':hashlib.sha256(shown.tobytes()).hexdigest(),
                                               'retail_sha256':hashlib.sha256(original.tobytes()).hexdigest(),
                                               'side_by_side_sha256':hashlib.sha256(comparison.tobytes()).hexdigest()})
                    if (code,side,variant,family)==('26','A',0,'jersey') and row['outcome']=='authored':
                        # Reconstruct the old 16-entry palette's decoded pixels,
                        # even when its compressed stream did not fit the slot.
                        old=replace(actual,palette=tuple(palette),levels=tuple(replace(m,rgba=rgba_from_indices(i,palette)) for m,i in zip(levels,indices)))
                        y=55+digit*85
                        draw.text((8,y+18),f'Digit {digit}',fill='black')
                        draw.text((8,y+34),'old overflow' if not tiers[-1]['fits'] else 'old fits',fill='black')
                        for col,s in enumerate((64,32,16,8)):
                            for half,texture in enumerate((old,actual)):
                                sample=render_digit_sample(texture,height=s,level=col)
                                x=145+col*170+half*76
                                draw.rectangle((x,y,x+65,y+65),fill=(20,40,60))
                                figure.paste(sample,(x+(64-s)//2,y+(64-s)//2))
                    rows.append(row)
                    print(target.selector,row["outcome"],row.get("encoded_bytes"),flush=True)
    summary={"slots":len(rows),"synthetic_slots":60,"old_overflow":sum(not any(t["fits"] for t in r.get("old_tiers",[])) for r in rows if "old_tiers" in r),
             "new_kept_retail":sum(r.get("outcome")=="kept_retail" for r in rows),"seconds":round(time.monotonic()-started,3)}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes((json.dumps({"summary":summary,"rows":rows},indent=2)+"\n").encode())
    figure.save(output.parent/'synthetic_comparison.png')
    print(json.dumps(summary),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index",type=Path,default=ROOT/"extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); run(args.index,args.output)

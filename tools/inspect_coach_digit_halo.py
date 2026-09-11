#!/usr/bin/env python3
"""Synthetic straight-alpha edge counterexample and decoded-palette check."""
from dataclasses import replace
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from PIL import Image,ImageDraw
from mod_editor.core.nfl2k5_digit_art import prepare_digit,prepared_mips,edge_quantizer
from mod_editor.core.nfl2k5_digit_texture import make_digit_mips,quantize_digit_levels
from mod_editor.core.nfl2k5_digit_preview import _filtered_level
from nfl_tset_png_import import rgba_from_indices


def run(output):
    colour=(224,219,208)
    source=Image.new('RGBA',(64,64),(250,0,250,0));source.paste((*colour,255),(15,7,49,58))
    reference=Image.new('RGBA',(64,64));reference.paste((*colour,255),(13,1,50,63))
    # Hold placement fixed to isolate filtering and transparent palette RGB.
    cleaned,_=prepare_digit(source,reference,'as_authored')
    old=make_digit_mips(source.tobytes(),64,64,4);new=prepared_mips(cleaned,4)
    rows=[];figure=Image.new('RGB',(850,340),(245,245,245));draw=ImageDraw.Draw(figure)
    draw.text((8,8),'Synthetic edge only. Old / new 16-entry decoded palette, bilinear 2x sampling.',fill='black')
    for tier in (256,32,16,12,8):
        p,indices,_=edge_quantizer(new,tier)
        oldp,oldindices,_=quantize_digit_levels(old,max(16,tier))
        for level,(m,i) in enumerate(zip(new,indices)):
            before=_filtered_level(replace(old[level],rgba=rgba_from_indices(oldindices[level],oldp)),(m.width*2,m.height*2))
            after=_filtered_level(replace(m,rgba=rgba_from_indices(i,p)),(m.width*2,m.height*2))
            def delta(image,low):
                return max((max(abs(c[k]-colour[k]) for k in range(3)) for c in image.getdata() if c[3]>=low),default=0)
            rows.append({'new_tier':tier,'old_tier':max(16,tier),'native_size':m.width,
                         'old_max_delta_alpha_ge_1':delta(before,1),'new_max_delta_alpha_ge_1':delta(after,1),
                         'old_max_delta_alpha_ge_16':delta(before,16),'new_max_delta_alpha_ge_16':delta(after,16)})
            if tier==16:
                x=12+level*210;draw.text((x,32),f'{m.width}px mip at 2x',fill='black')
                for y,image in ((55,before),(195,after)):
                    bg=Image.new('RGBA',image.size,(20,40,60,255));bg.alpha_composite(image)
                    figure.paste(bg.convert('RGB'),(x,y))
    output.mkdir(parents=True,exist_ok=True)
    (output/'halo.json').write_text(json.dumps(rows,indent=2)+'\n')
    figure.save(output/'synthetic_halo.png')
    tall=Image.new('RGBA',(64,64));tall.paste((*colour,255),(13,0,50,64))
    registered,_=prepare_digit(tall,reference)
    old=make_digit_mips(registered.tobytes(),64,64,4);new=prepared_mips(registered,4)
    from inspect_coach_digit_slots import border_alpha
    borders={'ordinary_area_border_alpha':[border_alpha(m) for m in old],
             'retail_margin_border_alpha':[border_alpha(m) for m in new]}
    (output/'mip_borders.json').write_text(json.dumps(borders,indent=2)+'\n')
    print('Old maximum RGB channel delta:',max(r['old_max_delta_alpha_ge_1'] for r in rows))
    print('New maximum RGB channel delta:',max(r['new_max_delta_alpha_ge_1'] for r in rows))
    print('Tall glyph mip borders:',borders)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)

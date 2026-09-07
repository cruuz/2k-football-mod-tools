#!/usr/bin/env python3
"""Author the v10 pixel/vector template. No retail texture or system font input.

The ESPN paths follow Noah's supplied geometric watermark lineage. The
broadcast photo guides the slim rim, neutral gradients and recessed cells.
PNG and SVG siblings use the same integer pixel shapes for portable edits.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from mod_editor.core import nfl2k5_scorebug_template as t

INK = (15, 17, 21, 255)
WHITE = (246, 247, 249, 255)
GREYS = [(v, v, min(255, v + 3), 255) for v in (19, 24, 31, 39, 49, 66, 93, 136, 188, 222, 245)]
REDS = [(v, 5, 28, 255) for v in (94, 128, 156, 184, 204, 225)]

# Original condensed block glyphs, drawn from rows rather than a bundled font.
GLYPHS = {
 '0':['01110','11011','11011','11011','11011','11011','01110'],
 '1':['00110','01110','00110','00110','00110','00110','01111'],
 '2':['01110','11011','00011','00110','01100','11000','11111'],
 '3':['11110','00011','00011','01110','00011','00011','11110'],
 '4':['00011','00111','01111','11011','11111','00011','00011'],
 '5':['11111','11000','11000','11110','00011','11011','01110'],
 '6':['01110','11000','11000','11110','11011','11011','01110'],
 '7':['11111','00011','00110','00110','01100','01100','01100'],
 '8':['01110','11011','11011','01110','11011','11011','01110'],
 '9':['01110','11011','11011','01111','00011','00011','01110'],
 'A':['01110','11011','11011','11111','11011','11011','11011'],
 'B':['11110','11011','11011','11110','11011','11011','11110'],
 'C':['01111','11000','11000','11000','11000','11000','01111'],
 'D':['11110','11011','11011','11011','11011','11011','11110'],
 'E':['11111','11000','11000','11110','11000','11000','11111'],
 'F':['11111','11000','11000','11110','11000','11000','11000'],
 'G':['01111','11000','11000','11011','11011','11011','01111'],
 'H':['11011','11011','11011','11111','11011','11011','11011'],
 'I':['11111','00110','00110','00110','00110','00110','11111'],
 'J':['00111','00011','00011','00011','11011','11011','01110'],
 'K':['11011','11011','11110','11100','11110','11011','11011'],
 'L':['11000','11000','11000','11000','11000','11000','11111'],
 'M':['11011','11111','11111','11011','11011','11011','11011'],
 'N':['11011','11111','11111','11111','11011','11011','11011'],
 'O':['01110','11011','11011','11011','11011','11011','01110'],
 'P':['11110','11011','11011','11110','11000','11000','11000'],
 'Q':['01110','11011','11011','11011','11111','01110','00011'],
 'R':['11110','11011','11011','11110','11100','11011','11011'],
 'S':['01111','11000','11000','01110','00011','00011','11110'],
 'T':['11111','00110','00110','00110','00110','00110','00110'],
 'U':['11011','11011','11011','11011','11011','11011','01110'],
 'V':['11011','11011','11011','11011','11011','01110','00100'],
 'W':['11011','11011','11011','11011','11111','11111','01010'],
 'X':['11011','11011','01110','00100','01110','11011','11011'],
 'Y':['11011','11011','11011','01110','00110','00110','00110'],
 'Z':['11111','00011','00110','00110','01100','11000','11111'],
 ':':['00000','00110','00110','00000','00110','00110','00000'],
 '&':['01100','11010','01100','01101','11010','11011','01101'],
 '-':['00000','00000','00000','11111','00000','00000','00000'],
 '.':['00000','00000','00000','00000','00000','00110','00110'],
 ' ':['00000']*7,
}


def svg_pixels(image, title):
    """Editable vector pixel runs, without external raster/font dependencies."""
    w, h = image.size
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             f'<title>{escape(title)}</title><g shape-rendering="crispEdges">']
    for y in range(h):
        x = 0
        while x < w:
            color = image.getpixel((x, y)); end = x + 1
            while end < w and image.getpixel((end, y)) == color:
                end += 1
            if color[3]:
                fill = '#%02X%02X%02X' % color[:3]
                opacity = f' fill-opacity="{color[3]/255:.6f}"' if color[3] < 255 else ''
                parts.append(f'<rect x="{x}" y="{y}" width="{end-x}" height="1" fill="{fill}"{opacity}/>')
            x = end
    return '\n'.join(parts + ['</g></svg>']) + '\n'


def save_layer(folder, name, image):
    for scale in (1, 2):
        target = folder / f'{scale}x'
        target.mkdir(parents=True, exist_ok=True)
        scaled = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
        scaled.save(target / (name + '.png'))
    (folder / '1x' / (name + '.svg')).write_text(svg_pixels(image, name), encoding='utf-8')
    svg = svg_pixels(image, name).replace(f'width="{image.width}" height="{image.height}"',
                                         f'width="{image.width*2}" height="{image.height*2}"', 1)
    (folder / '2x' / (name + '.svg')).write_text(svg, encoding='utf-8')


def mark():
    # Supersample the actual hand-built paths from the supplied watermark,
    # not a game bitmap or a font approximation. The small path reader only
    # serves these fixed M/H/V/Q/Z authoring paths; it is not an SVG importer.
    paths = [
        'M0 0H24V6H7V10H22V16H7V19H24V25H0Z',
        'M34 0H58V6H36V10H51Q58 10 58 17V18Q58 25 51 25H28V19H50V16H35Q28 16 28 9V7Q28 0 34 0Z',
        'M63 0H83Q91 0 91 8V9Q91 17 83 17H70V25H63Z',
        'M70 6V11H81Q84 11 84 8.5Q84 6 81 6Z',
        'M96 0H103L114 14V0H121V25H114L103 11V25H96Z',
    ]
    mask=Image.new('L',(1024,256));d=ImageDraw.Draw(mask)
    def outline(path):
        tokens=re.findall(r'[MHVLQZ]|-?\d+(?:\.\d+)?',path)
        points=[];i=0;x=y=0
        def number():
            nonlocal i
            value=float(tokens[i]);i+=1;return value
        while i<len(tokens):
            cmd=tokens[i];i+=1
            if cmd in ('M','L'):x,y=number(),number();points.append((x,y))
            elif cmd=='H':x=number();points.append((x,y))
            elif cmd=='V':y=number();points.append((x,y))
            elif cmd=='Q':
                qx,qy,nx,ny=number(),number(),number(),number()
                for k in range(1,17):
                    v=k/16;points.append(((1-v)**2*x+2*(1-v)*v*qx+v*v*nx,(1-v)**2*y+2*(1-v)*v*qy+v*v*ny))
                x,y=nx,ny
        return points
    for i,path in enumerate(paths):
        pts=[((4+(x-.176327*y)*.36)*16,(3+y*.4)*16) for x,y in outline(path)]
        d.polygon(pts,fill=0 if i==3 else 255)
    d.rectangle((0,int((3+6.5*.4)*16),49*16,int((3+9*.4)*16)),fill=0)
    # Match the watermark's independent, compact NFL block lettering.
    for offset,path in ((0,'M0 0H5L12 13V0H17V24H12L5 11V24H0Z'),
                        (21,'M0 0H15V5H5V10H14V15H5V24H0Z'),
                        (40,'M0 0H5V19H14V24H0Z')):
        pts=[((51+(x+offset)*.205)*16,(5+y*.27)*16) for x,y in outline(path)]
        d.polygon(pts,fill=255)
    mask=mask.resize((64,16),Image.Resampling.LANCZOS)
    # Five coverage levels are an authored choice recorded by the generator;
    # the product compiler itself never quantizes a user's input.
    image=Image.new('RGBA',(64,16),INK)
    image.putdata([tuple(round(a+(b-a)*(round(v/255*4)/4)) for a,b in zip(INK,WHITE))
                   for v in mask.getdata()])
    return image


def neutral_panel(home=False, primary=None):
    image = Image.new('RGBA', (32, 16), INK)
    d = ImageDraw.Draw(image)
    for x in range(32):
        k = min(4, x // 5)
        if primary:
            factor = (100, 78, 53, 33, 18)[k]
            c = tuple((p * factor + 15 * (100-factor)) // 100 for p in primary) + (255,)
        else:
            c = GREYS[4-k]
        d.line((x,0,x,15), fill=c)
    d.line((0,0,31,0), fill=GREYS[6])
    d.line((0,15,31,15), fill=GREYS[1])
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if home else image


def author(folder):
    # A fresh output folder is a complete painting kit. Read the supplied
    # non-generated sources first, so missing inputs cannot leave half a kit.
    sources = {name: t._read(t.DEFAULT_FOLDER / name) for name in
               ('README.md', 'teams.json', 'game_state.json',
                'lineage/scorebug_master.svg', 'lineage/espn_nfl_watermark.svg')}
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in sources.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    frame = Image.new('RGBA', (64, 8), INK)
    d = ImageDraw.Draw(frame)
    d.rectangle((0,0,63,7), outline=GREYS[4])
    d.line((0,0,63,0), fill=GREYS[7])
    d.line((1,1,62,1), fill=GREYS[2])
    d.line((1,7,62,7), fill=GREYS[6])
    clock = Image.new('RGBA', (64,12), INK)
    d = ImageDraw.Draw(clock)
    d.rounded_rectangle((0,0,63,11), radius=4, fill=GREYS[5], outline=GREYS[2])
    d.rounded_rectangle((1,1,62,10), radius=3, fill=GREYS[8])
    d.rounded_rectangle((2,2,61,9), radius=2, fill=WHITE)
    down = Image.new('RGBA', (64,12), INK)
    d = ImageDraw.Draw(down)
    d.polygon([(0,0),(63,0),(61,2),(59,10),(57,11),(6,11),(4,10),(2,2)], fill=REDS[0])
    d.polygon([(2,0),(61,0),(59,3),(58,9),(56,10),(7,10),(5,9),(4,3)], fill=REDS[3])
    d.line((3,1,60,1), fill=REDS[5])
    d.line((6,9,57,9), fill=REDS[2])
    score = Image.new('RGBA', (12,16), INK)
    d = ImageDraw.Draw(score)
    d.line((0,0,11,0),fill=GREYS[4]);d.line((0,15,11,15),fill=GREYS[1])
    layers = {'frame': frame, 'left_mark':mark(), 'away_block':neutral_panel(),
              'home_block':neutral_panel(True), 'away_score':score, 'home_score':score,
              'clock_quarter':clock, 'down':down}
    for name, image in layers.items():
        save_layer(folder,name,image)
    timeout = Image.new('RGBA',(12,2))
    d = ImageDraw.Draw(timeout)
    for x in (0,4,8):
        d.polygon([(x+1,0),(x+3,0),(x+2,1),(x,1)],fill=WHITE)
    save_layer(folder/'optional','timeout_marks',timeout)
    layout = {'schema': t.SCHEMA, 'source_scale': 1, 'atlas_size': [64,64],
              'hud_space':[640,480], 'rails':t.RAILS,
              'layers': {name:{'atlas_rect':a,'hud_rect':h} for name,(a,h) in t.LAYERS.items()},
              'live_text_anchors':t.ANCHORS, 'live_timeouts':False,
              'palette':{'max_colours':256,'count_alpha':True,'conversion':'exact RGBA; no reduction',
                         'vc_lz_span_bytes':2432,'wrapper_bytes':32,'wrapper_plus_0x14':16,
                         'rule':'nfl_vc_lz_fill must preserve all wrapper bytes, including +0x14, and native overlapping decode'},
              'live_text_colours':{'scores':'#FFFFFFFF','teams':'#FFFFFFFF','possession':'#FFC0C000',
                                  'down':'#FFFFFFFF','quarter_clock_play_clock':'#FF111118'},
              'optional_timeouts':{'file':'optional/1x/timeout_marks.png','installed':False,
                                   'runtime_counts':[0,1,2,3],'atlas_rect':None,
                                   'hud_rects':[[238,423,270,425],[442,423,474,425]]},
              'fonts':{'installed':['font1','font2','font5'],'new_sheet':'glyphs/1x/broadcast_glyphs.png',
                       'score_slot_fields':['0xA95950','0xA95988'],'score_slot':1,
                       'new_sheet_installed':False,'contract':'glyphs/glyphs.json'},
              'team_selection':{'static':'neutral','variants':'teams/1x/ABBR.png',
                                'runtime_bound':False,'away_parent':23,'home_parent':26,
                                'away_material':'zscore_buga','home_material':'hscore_buga',
                                'disable_element_material_visibility':2},
              'provenance':{'art':'new pixel paths and supplied SVG design lineage; no retail textures',
                            'photo':'scorebug_reference_2026-09-05.jpeg, research hub',
                            'lineage':['lineage/scorebug_master.svg','lineage/espn_nfl_watermark.svg'],
                            'adaptation':'left mark required by brief; broadcast photo has its watermark in upper right'}}
    (folder/'layout.json').write_text(json.dumps(layout,indent=2)+'\n',encoding='utf-8')
    teams = json.loads((folder/'teams.json').read_text(encoding='utf-8'))
    for team in teams:
        primary = tuple(bytes.fromhex(team['primary_hex'][1:]))
        save_layer(folder/'teams',team['abbr'],neutral_panel(primary=primary))
    sheet = Image.new('RGBA',(256,128))
    d=ImageDraw.Draw(sheet);metrics={}
    for index, code in enumerate(range(32,128)):
        char=chr(code);x=(index%16)*16;y=(index//16)*20
        rows=GLYPHS.get(char.upper(),GLYPHS[' '])
        for yy,row in enumerate(rows):
            for xx,bit in enumerate(row):
                if bit=='1':d.rectangle((x+2+xx*2,y+2+yy*2,x+3+xx*2,y+3+yy*2),fill=WHITE)
        metrics[str(code)]={'character':char,'rect':[x,y,x+16,y+20],'advance':12,
                            'supported':char.upper() in GLYPHS}
    save_layer(folder/'glyphs','broadcast_glyphs',sheet)
    (folder/'glyphs'/'glyphs.json').write_text(json.dumps({'schema':'nfl2k5_scorebug_glyph_source/v1',
        'atlas_size':[256,128],'metrics':metrics,'installed':False,
        'reason':'The static bar binds shared FONT objects, not digital_font. An isolated FONT resource and selector are required to install this sheet.'},indent=2)+'\n',encoding='utf-8')
    compiled=t.compile_folder(folder)
    compiled.image.save(folder/'atlas_1x.png')
    compiled.image.resize((128,128),Image.Resampling.NEAREST).save(folder/'atlas_2x.png')
    parts=['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1280" height="960" viewBox="0 0 640 480">',
           '<title>V10 static template layers, no baked live text</title>']
    for name,(_a,h) in t.LAYERS.items():
        x,y,r,b=h
        parts.append(f'<g id="{name}"><image x="{x}" y="{y}" width="{r-x}" height="{b-y}" preserveAspectRatio="none" xlink:href="1x/{name}.png"/></g>')
    parts.append('</svg>')
    (folder/'master_2x.svg').write_text('\n'.join(parts)+'\n',encoding='utf-8')
    (folder/'master_1x.svg').write_text('\n'.join(parts).replace('width="1280" height="960"','width="640" height="480"')+'\n',encoding='utf-8')
    print(json.dumps(compiled.receipt,indent=2))


def release_catalog(folder):
    """Exact reviewed PNG paths and identities; never a directory exemption."""
    records={}
    for path in sorted(folder.rglob('*.png')):
        with Image.open(path) as image:
            width,height=image.size
        raw=path.read_bytes()
        records[path.relative_to(ROOT).as_posix()]={
            'size':len(raw),'sha256':t.sha(raw),'width':width,'height':height}
    data=(json.dumps({'schema':'nfl2k5_scorebug_template_pngs/v1','files':records},indent=2)+'\n').encode()
    (ROOT/'packaging/nfl2k5_scorebug_template_pngs.json').write_bytes(data)
    print('SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = '+repr(t.sha(data)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=t.DEFAULT_FOLDER)
    parser.add_argument('--write-release-catalog',action='store_true',
                        help='Maintainer only: regenerate the exact default PNG catalog and print its checker pin')
    args=parser.parse_args()
    author(args.output)
    if args.write_release_catalog:
        if args.output.resolve()!=t.DEFAULT_FOLDER.resolve():
            parser.error('the release catalog is only for the shipped default folder')
        release_catalog(args.output)

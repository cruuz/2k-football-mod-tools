#!/usr/bin/env python3
"""Offline lg2 evidence: real x86 strings in native font atlases, illustrative layouts.

These are not xemu frames. No source image is edited. Requires private font
atlases under --hydrated and Unicorn only for this developer evidence tool.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests/mod_editor'),str(ROOT/'tools/b77')]
from f4_render import Fonts
from mod_editor.core import nfl2k5_letter_grades as lg
from mod_editor.core import nfl2k5_letter_grades_attributes as attr
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_supersim_draft_fixture import Machine


def wstr(m,p):
    return bytes(m.uc.mem_read(p,512)).decode('utf-16le').split('\0')[0]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('before','after','hydrated','out'):p.add_argument('--'+flag,type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    before,after=args.before.read_bytes(),args.after.read_bytes()
    if attr.status(after)!='applied':raise ValueError('after must contain lg2')
    machines=[Machine(b,trace_writes=False) for b in (before,after)]
    fonts=Fonts(args.hydrated)
    from PIL import Image
    samples={
        'player_card': [('CATCH',93),('RUN ROUTE',92),('SPEED',88),('AGILITY',83),('JUMPING',77),('STRENGTH',38),('RUN BLOCKING',47),('CONSISTENCY',80),('BREAK TACKLE',72),('LEADERSHIP',48)],
        'roster': [('SPEED',99),('AGILITY',94),('STRENGTH',85)],
        'depth_chart': [('SPEED',88),('CATCH',93),('RUN ROUTE',92)],
        'lineup': [('SPEED',99),('TACKLE',84),('COVERAGE',75)],
        'free_agency': [('SPEED',89),('AGILITY',74),('DURABILITY',60)],
        'draft_scouting': [('SPEED',95),('PASS ACCURACY',80),('STRENGTH',49)],
        'trade': [('SPEED',94),('PASS BLOCKING',79),('RUN BLOCKING',69)],
        'compare': [('SPEED / PLAYER A',93),('SPEED / PLAYER B',91)],
        're_sign_contract': [('SPEED',88),('AGILITY',83),('DURABILITY',64)],
        'franchise_weekly_prep': [('SPEED',99),('CATCH',94),('RUN ROUTE',89)],
        'create_player': [('SPEED',94),('SPEED AFTER ONE PRESS',95),('AGILITY',55)],
        'edit_player': [('STRENGTH',49),('STRENGTH AFTER ONE PRESS',50),('CONSISTENCY',70)],
        'in_game_overlay': [('SPEED',85),('STAMINA',60),('TACKLE',54)],
        'substitution': [('RTG / PLAYER A',95),('RTG / PLAYER B',94),('RTG / PLAYER C',49)],
    }
    literal_by_screen={'player_card':0x32057e,'depth_chart':0x243641,'draft_scouting':0x35ecc7,
                       'franchise_weekly_prep':0x2b0a7e,'in_game_overlay':0x6adac}
    descriptor_by_screen={'roster':0x541288,'lineup':0x53cc48,'free_agency':0x57dca8,
                          'trade':0x57dca8,'compare':0x55ae60,'re_sign_contract':0x57dca8,
                          'create_player':0x5639f0,'edit_player':0x564910,'substitution':0x515928}
    evidence={}
    for name,rows in samples.items():
        outputs=[]
        for m in machines:
            texts=[]
            for label,value in rows:
                dest,arg=m.ARENA+0x1000,m.ARENA+0x2000
                m.put(arg,value)
                if name in literal_by_screen:
                    m.call(0x4a400,ecx=dest,edx=m.get(literal_by_screen[name]),args=(arg,))
                else:
                    kind=bytes(m.uc.mem_read(descriptor_by_screen[name]+1,1))[0]
                    bits=struct.unpack('<I',struct.pack('<f',value))[0]
                    m.call(0x173120,eax=kind,ecx=dest,args=(bits,))
                texts.append(wstr(m,dest))
            outputs.append(texts)
        evidence[name]=dict(input_ratings=[v for _,v in rows],before=outputs[0],after=outputs[1],
                            literal_va=hex(literal_by_screen[name]) if name in literal_by_screen else None,
                            descriptor_va=hex(descriptor_by_screen[name]) if name in descriptor_by_screen else None)
        height=110+len(rows)*28
        canvas=Image.new('RGBA',(1140,height),(22,24,30,255))
        fonts.draw(canvas,'font9',name.replace('_',' ').upper(),12,10)
        for panel,texts in enumerate(outputs):
            x=12+panel*570
            fonts.draw(canvas,'font9','BEFORE' if panel==0 else 'AFTER',x,40)
            for i,((label,value),text) in enumerate(zip(rows,texts)):
                fonts.draw(canvas,'font4',label,x,70+i*28)
                fonts.draw(canvas,'font4',text,x+510-fonts.width('font4',text),70+i*28)
        fonts.draw(canvas,'font9','Native text and fonts; illustrative layout. Not a game frame.',12,height-24)
        canvas.save(args.out/(name+'.png'))
    # Capture the actual installed MyCareer format, with the game's mixed argument parser.
    code,data=career.allocations(after);_,labels=mode.code_for(code['va'],data['va'])
    outputs=[]
    for m in machines:
        dest,arg,name=m.ARENA+0x1000,m.ARENA+0x2000,m.ARENA+0x3000
        m.uc.mem_write(name,'Speed\0'.encode('utf-16le'))
        m.uc.mem_write(arg,struct.pack('<5I',name,94,99,20,123))
        m.call(0x4a400,ecx=dest,edx=labels['m3_upgrade_format'],args=(arg,))
        outputs.append(wstr(m,dest))
    evidence['mycareer']=dict(before=outputs[0],after=outputs[1],
        prospects_before=[wstr(machines[0],labels[n]) for n,_,_ in attr.CAREER_PROSPECTS],
        prospects_after=[wstr(machines[1],labels[n]) for n,_,_ in attr.CAREER_PROSPECTS])
    canvas=Image.new('RGBA',(1140,270),(22,24,30,255))
    for i,title in enumerate(('before','after')):
        fonts.draw(canvas,'font9','MYCAREER '+title.upper(),12+i*570,10)
        fonts.draw(canvas,'font9',outputs[i],12+i*570,50)
        for j,text in enumerate(evidence['mycareer']['prospects_'+title]):
            fonts.draw(canvas,'font9',text,12+i*570,90+j*28)
    fonts.draw(canvas,'font9','Native text and fonts; illustrative layout. Not a game frame.',12,245)
    canvas.save(args.out/'mycareer.png')
    from test_nfl2k5_letter_grades_progress import _rows
    prev=[49,54,59,64,89,94]*5;curr=[v+1 for v in prev]
    rows_before=_rows(before,0,prev,curr);rows_after=_rows(after,0,prev,curr)
    evidence['progression']=dict(before=rows_before,after=rows_after)
    canvas=Image.new('RGBA',(1140,310),(22,24,30,255))
    for i,rows in enumerate((rows_before,rows_after)):
        x=12+570*i
        fonts.draw(canvas,'font9','PROGRESSION '+('BEFORE' if i==0 else 'AFTER'),x,10)
        fonts.draw(canvas,'font9','PREVIOUS      CURRENT      CHANGE',x,50)
        for j,values in enumerate(rows):
            for k,text in enumerate(values):fonts.draw(canvas,'font4',text,x+k*135,85+j*28)
    fonts.draw(canvas,'font9','Native row loop; illustrative layout. Not a game frame.',12,285)
    canvas.save(args.out/'progression.png')
    widths={}
    for font in sorted({f for f,_ in fonts.table}):
        widths[font]=dict(max_grade=max(fonts.width(font,g) for _,g in lg.DEFAULT_BANDS),
                          digits_99=fonts.width(font,'99'),digits_100=fonts.width(font,'100'))
    evidence['font_widths']=widths
    (args.out/'native_text.json').write_text(json.dumps(evidence,indent=2)+'\n',newline='\n')
    print(json.dumps(dict(native_panels=16,game_frames=0,font_widths=widths),sort_keys=True))


if __name__=='__main__':main()

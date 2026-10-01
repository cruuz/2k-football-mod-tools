#!/usr/bin/env python3
"""DESIGN: printable and searchable schematics from the authored recipe only."""
from collections import Counter
from io import StringIO
import html
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_playbook_pack as p, nfl2k5_play_codec as c

OUT = Path(__file__).resolve().parent
COLORS = {8:'#cd6500',9:'#12639d',10:'#178054',11:'#178054'}


def panel(ax, form, play, row):
    ax.set_xlim(-27,27)
    ax.set_ylim(-12,33)
    ax.set_aspect('equal')
    ax.set_facecolor('#fafcf9')
    for y in range(0,31,5):
        ax.axhline(y,color='#d9e1db',linewidth=.5)
    ax.axhline(0,color='#657b6a',linewidth=1)
    ax.set_xticks([])
    ax.set_yticks([0,10,20,30])
    ax.tick_params(labelsize=6,length=0)
    ax.spines[['top','right','left','bottom']].set_visible(False)
    ax.set_title(f'{form.custom_name} | {play.concept}\np{play.replace_index} | {row["personnel"]} personnel | menu {row["menu_slot"]+1}',
                 fontsize=8,fontweight='bold',color='#163546',pad=5)
    for slot,(xy,code,chain) in enumerate(zip(form.slot_positions,form.position_codes,play.assignments)):
        kind = code & 31
        color = COLORS.get(kind,'#6a737b')
        if slot == row.get('te1_slot',6): color='#cd6500'
        x,y = (n/c.YD_CM for n in xy)
        nodes = [c.Node.from_bytes(c.Node(op,0,list(operands)).to_bytes()) for op,operands in chain]
        zone = any(n.op==0x11 and n.operands[0]==8 for n in nodes)
        segments = c.play_art([n for n in nodes if not (n.op==0x11 and n.operands[0]==8)],xy)
        for seg in segments:
            points = [(a/c.YD_CM,b/c.YD_CM) for a,b in seg.points]
            xs,ys = zip(*points)
            ax.plot(xs,ys,color=color,linewidth=1.05,linestyle='--' if seg.style=='dashed' else '-',alpha=.9)
            if len(points)>1 and points[-1]!=points[-2]:
                ax.annotate('',xy=points[-1],xytext=points[-2],
                            arrowprops=dict(arrowstyle='->',color=color,lw=.7,mutation_scale=6))
        if zone:
            node = next(n for n in nodes if n.op==0x11 and n.operands[0]==8)
            ax.text(x,y+1.6,'Z'+('>' if node.operands[5]>0 else '<' if node.operands[5]<0 else '^'),
                    color='#666',fontsize=5,ha='center')
        ax.scatter([x],[y],s=17,color=color,edgecolors='white',linewidths=.4,zorder=6)
        label = 'Y1' if slot==row.get('te1_slot',6) else c.position_label(code)
        ax.text(x,y-1.2,label,fontsize=5.5,ha='center',va='top',color=color,zorder=7)
    if play.concept=='RB Slip':
        ax.text(-26,31,'Screen endpoint is solver-dependent',fontsize=5,color='#526060')


def main():
    pack = p.load_pack(ROOT/'data/playbooks/softdrink_giants_modern.2k5book')
    catalog = json.loads((ROOT/'pb/catalog.json').read_text())
    rows = {r['play_index']:r for r in catalog}
    plays = {v.id:v for v in pack.plays}
    ordered = [(pack.formations_by_id[fid],plays[pid],rows[plays[pid].replace_index])
               for fid,menu in pack.menus for pid in menu]
    plt.rcParams['svg.fonttype']='none'
    plt.rcParams['svg.hashsalt']='giants-modern-pb'
    pages = (len(ordered)+5)//6
    with PdfPages(OUT/'GIANTS_PLAY_SHEET.pdf',metadata={
            'Title':'DESIGN: NFL 2K28 Giants play sheet',
            'Author':'SOFTDRINK / Astra', 'CreationDate':None,'ModDate':None}) as pdf:
        for page in range(pages):
            fig,axes = plt.subplots(2,3,figsize=(11.7,8.3))
            fig.suptitle('DESIGN | GIANTS MODERN | TE1 FEATURED',fontsize=14,color='#163546',fontweight='bold')
            for ax in axes.flat: ax.set_visible(False)
            for ax,entry in zip(axes.flat,ordered[page*6:page*6+6]):
                ax.set_visible(True)
                panel(ax,*entry)
            fig.text(.04,.017,'DESIGN schematic, not animation. Orange Y1 = TE1; blue = WR; green = backs; gray = OL/QB. Z = native zone leg, no target prediction.',fontsize=7)
            fig.text(.94,.017,f'{page+1}/{pages}',fontsize=7)
            fig.subplots_adjust(top=.9,bottom=.06,wspace=.13,hspace=.3)
            pdf.savefig(fig)
            if page==0: fig.savefig(ROOT/'.scratch/pb-first-page.png',dpi=130)
            plt.close(fig)
    cards=[]
    for form,play,row in ordered:
        fig,ax=plt.subplots(figsize=(5.2,4.5))
        panel(ax,form,play,row)
        fig.tight_layout()
        stream=StringIO()
        fig.savefig(stream,format='svg',metadata={'Date':None})
        plt.close(fig)
        svg=stream.getvalue()
        svg=svg[svg.index('<svg'):]
        search=html.escape(f'{form.custom_name} {play.concept} {play.replace_index} {row["personnel"]}'.lower())
        cards.append(f'<article data-search="{search}">{svg}</article>')
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><title>DESIGN: Giants play sheet</title>
<style>body{font:16px system-ui;margin:24px;background:#f0f4f1;color:#163546}header{max-width:1000px}h1{font-size:28px}input{font:inherit;padding:12px;width:min(90%,500px)}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:16px}article{background:white;border-radius:8px;overflow:hidden}svg{width:100%;height:auto}small{display:block;margin:12px 0}a{color:#12639d}</style>
<header><h1>DESIGN: Giants modern play sheet</h1><p>148 plays, 26 formations. Orange Y1 is TE1 (set Likely there on the roster); blue is WR; green is HB/FB; gray is OL/QB. Z marks a native zone assignment without predicting its live defender target.</p><p>DESIGN: schematic geometry from encoded assignments, not an animation or gameplay witness. Screen marks do not predict catch coordinates. No RPO/read option, automatic jet motion, guaranteed duo double-teams or middle screen.</p><p><a href="GIANTS_PLAY_SHEET.pdf">Printable PDF</a> | <a href="../CONCEPTS.md">Concepts and engine limits</a></p><label>Find a formation, concept, play index or personnel group<br><input id="search" type="search" placeholder="For example: Ace Wing, Mesh, 12"></label><small id="count">148 plays</small></header><main>'''
    document+='\n'.join(cards)+'''</main><script>const s=document.querySelector('#search'),cards=[...document.querySelectorAll('article')];s.addEventListener('input',()=>{const q=s.value.trim().toLowerCase();let n=0;for(const c of cards){c.hidden=!c.dataset.search.includes(q);if(!c.hidden)n++;}document.querySelector('#count').textContent=n+' plays';});</script></html>'''
    (OUT/'index.html').write_text('\n'.join(line.rstrip() for line in document.splitlines())+'\n')
    print(json.dumps(dict(status='DESIGN',plays=len(ordered),pdf_pages=pages,
                         concepts=dict(Counter(r['concept'] for r in catalog)))))


if __name__=='__main__':main()

#!/usr/bin/env python3
"""DESIGN: diagrams from each compiled defense, not gameplay images."""
import html
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
from matplotlib.backends.backend_pdf import PdfPages
from mod_editor.core import nfl2k5_playbook_inspector as ip,nfl2k5_play_library as lib,nfl2k5_play_codec as codec

def panel(ax,book,body,row,fi):
    form=lib.formation_record(body,fi);info=lib.defense_personnel(book,body,fi)
    front=lib.decoded_chains(body,row['preview_front']);coverage=lib.decoded_chains(body,row['play'])
    chains=lib.effective_defense(front,coverage)
    ax.set_facecolor('#f0f7f2');ax.set_xlim(-28,28);ax.set_ylim(-6,27);ax.set_aspect('equal')
    for y in (0,10,20):ax.axhline(y,color='#b6cabc',lw=.7)
    ax.axhline(0,color='#264c36',lw=1)
    for slot,ch in enumerate(chains):
        x,z=form.slots[slot].x[0]/lib.YD,form.slots[slot].z[0]/lib.YD
        actions=[(op,v) for op,v in ch if op in (0x0B,0x0D,0x0E)]
        color='#cf4935' if actions[0][0]==0x0B else '#265d9d' if actions[0][0]==0x0D else '#9848a0'
        for i,(op,v) in enumerate(actions):
            alpha=.7 if i==0 else .4;style='-' if i==0 else '--'
            if op==0x0D:
                tx,ty=v[0]/lib.YD,v[1]/lib.YD
                ax.annotate('',(tx,ty),(x,z),arrowprops=dict(arrowstyle='->',color='#265d9d',lw=.9,alpha=alpha,ls=style))
                ax.add_patch(Ellipse((tx,ty),7,3,fill=False,edgecolor='#265d9d',lw=.7,ls=style,alpha=.7))
            elif op==0x0B:
                tx=codec.LANE_TABLE_CM[int(v[1])]/lib.YD
                ax.annotate('',(tx,-4),(x,z),arrowprops=dict(arrowstyle='->',color='#cf4935',lw=1,alpha=alpha))
            elif op==0x0E:
                # DESIGN: target marker only, no guessed receiver coordinates or routes.
                ax.text(x+.5,z+1.2,'M'+('X' if len(actions)>1 else ''),fontsize=5,color='#9848a0')
        ax.scatter([x],[z],s=30 if z<2 else 105,color='white',edgecolors=color,zorder=4)
        ax.text(x,z,str(slot),ha='center',va='center',fontsize=4.8 if z<2 else 6,color='#142c38',zorder=5)
    spy_label=' + Spy' if row.get('spy_slots') else ''
    ax.set_title(f"{book.formations[fi].name} | {row['play']}: {row['concept']}{spy_label}",fontsize=8)
    ax.set_xticks([]);ax.set_yticks([0,10,20]);ax.tick_params(labelsize=6)
    for sp in ax.spines.values():sp.set_visible(False)
    labels=' '.join(f'{i}:{v}' for i,v in enumerate(info['labels']))
    ax.text(.5,-.10,labels,ha='center',transform=ax.transAxes,fontsize=4.7)

def main():
    out=Path(__file__).resolve().parent;profiles=json.loads((ROOT/'pb/research/defense_profiles.json').read_text())
    plt.rcParams['svg.fonttype']='none';plt.rcParams['svg.hashsalt']='pb-defense-v3';pages={};articles=[]
    with PdfPages(out/'DEFENSE_PLAY_SHEETS.pdf',metadata={'Title':'DESIGN: 32 team defenses','CreationDate':None,'ModDate':None}) as pdf:
        for team,profile in profiles.items():
            raw=(ROOT/f'.scratch/pb3/compiled/{team}.bin').read_bytes();body=raw[32:];book=ip.parse_playbook_resource(raw)
            cat=json.loads((ROOT/f'pb/defense/{team}.json').read_text());rows=[r for r in cat['plays'] if r['component']=='coverage']
            counts={r['concept']:sum(x['concept']==r['concept'] for x in rows) for r in rows}
            preferred=sorted(counts,key=lambda k:(-counts[k],k));choices=[];seen=set()
            for r in rows:
                if r.get('spy_slots'):
                    choices.append((r,r['formations'][0]));seen.add(r['concept'])
            for concept in preferred[:2]+['Creeper Three','Sim Two','Three Sky X','Three Cloud X','Four Exchange','One Robber','Zero','Six Split']+preferred:
                if concept in seen:continue
                candidates=[r for r in rows if r['concept']==concept]
                if not candidates:continue
                seen.add(concept);r=candidates[0]
                if not choices:fi=next((f for f in r['formations'] if 'Tite' in book.formations[f].name or 'Wide' in book.formations[f].name),r['formations'][0])
                else:fi=next((f for f in r['formations'] if 'Nickel' in book.formations[f].name),r['formations'][0])
                choices.append((r,fi))
                if len(choices)==6:break
            fig,axes=plt.subplots(2,3,figsize=(11.7,8.3));fig.suptitle(f'DESIGN | {team} DEFENSE | {profile["dc"]}',fontsize=15,color='#142c38',fontweight='bold')
            fig.text(.5,.923,profile['family']+' | 2025 baseline: '+str(profile['baseline_team'] or 'unavailable; LAC design fallback'),ha='center',fontsize=9)
            for ax,(row,fi) in zip(axes.flat,choices):panel(ax,book,body,row,fi)
            fig.text(.025,.043,'DESIGN: red = rush lane; blue = zone landmark; M = man; MX / dashed continuation = native exchange. Numbers are defender slots.',fontsize=7)
            fig.text(.025,.027,'DESIGN: assignment schematics only. Native personnel retained. Spy shows fallback landmark; runtime pursuit and complete match need a live lab.',fontsize=7)
            fig.text(.025,.011,'PROVED OFFLINE: compiled front plus coverage covers all 11 slots. DESIGN: pre-snap shell, live rotation and pressure need main lab.',fontsize=7)
            fig.subplots_adjust(top=.87,bottom=.13,wspace=.1,hspace=.38)
            svg=out/f'{team}_defense.svg';fig.savefig(svg,metadata={'Date':None});pdf.savefig(fig)
            svg.write_text('\n'.join(l.rstrip() for l in svg.read_text().splitlines())+'\n')
            if team in ('NYG','DAL'):fig.savefig(ROOT/f'.scratch/pb3/{team}-defense.png',dpi=110)
            plt.close(fig);pages[team]=dict(status='DESIGN',page=svg.name,plays=[r['play'] for r,fi in choices])
            articles.append(f'<article><h2>{team}: {html.escape(profile["dc"])}</h2><a href="{svg.name}"><img loading="lazy" src="{svg.name}" alt="DESIGN: {team} defensive assignments"></a></article>')
    (out/'defense_pages.json').write_text(json.dumps(pages,indent=2)+'\n')
    (out/'defense.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>DESIGN: team defenses</title><style>body{font:16px system-ui;background:#f0f5f3;color:#163546;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:20px}article{background:white;padding:16px}img{width:100%}</style><h1>DESIGN: 32 team defenses</h1><p>DESIGN: compiled assignment schematics, not live gameplay.</p><p><a href="DEFENSE_PLAY_SHEETS.pdf">32-page PDF</a> | <a href="../PB_REPORT.md">Report and rate comparison</a> | <a href="league.html">Phase 2 offenses</a></p><main>'+''.join(articles)+'</main></html>\n')
    print('DESIGN: 32 defense pages rendered')
if __name__=='__main__':main()

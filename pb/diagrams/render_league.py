#!/usr/bin/env python3
"""DESIGN: one role-correct schematic page per team; no runtime imagery."""
import html
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pb.diagrams.render import panel,plt,PdfPages,p


def main():
    out=Path(__file__).resolve().parent
    manifest=json.loads((ROOT/'pb/league_manifest.json').read_text())['teams']
    profiles=json.loads((ROOT/'pb/research/team_profiles.json').read_text())['teams']
    plt.rcParams['svg.fonttype']='none';plt.rcParams['svg.hashsalt']='pb-modern-league'
    links=[];receipt={}
    with PdfPages(out/'LEAGUE_PLAY_SHEETS.pdf',metadata={'Title':'DESIGN: 32 modern offenses','CreationDate':None,'ModDate':None}) as pdf:
        for entry in manifest:
            team=entry['team'];profile=profiles[team];pack=p.load_pack(ROOT/entry['pack'])
            catalog=json.loads((ROOT/f'pb/catalogs/{team}.json').read_text());by_index={r['play_index']:r for r in catalog}
            plays={v.id:v for v in pack.plays}
            ordered=[(pack.formations_by_id[f],plays[pid],by_index[plays[pid].replace_index]) for f,menu in pack.menus for pid in menu]
            choices=[];seen=set()
            for concept in profile['emphasis']+['Inside Zone','Outside Zone','Mesh','TE Seam','RB Slip','End Around','Y Cross']:
                if len(choices)==6:break
                if concept in seen:continue
                pick=next((v for v in ordered if v[1].concept==concept),None)
                if pick:
                    choices.append(pick);seen.add(concept)
            fig,axes=plt.subplots(2,3,figsize=(11.7,8.3))
            fig.suptitle(f'DESIGN | {team} MODERN | {profile["scheme"]}',fontsize=12,color='#163546',fontweight='bold')
            fig.text(.5,.925,profile['key_players']+' | '+profile['feature_role']+': '+profile['feature_player'],ha='center',fontsize=8)
            for ax,selection in zip(axes.flat,choices):panel(ax,*selection)
            fig.text(.03,.022,'DESIGN: six representative calls from the complete catalog. Encoded routes, not live animation. Orange Y1 = native TE1 role.',fontsize=7)
            fig.text(.03,.009,'DESIGN: roster role must be checked in-game. Zone Z = native leg; screen endpoint is solver-dependent. No RPO/read option.',fontsize=7)
            fig.subplots_adjust(top=.88,bottom=.065,wspace=.15,hspace=.32)
            svg=out/f'{team}.svg'
            fig.savefig(svg,metadata={'Date':None});pdf.savefig(fig)
            svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
            if team in ('MIA','NO','NYG'):fig.savefig(ROOT/f'.scratch/pb-{team}.png',dpi=100)
            plt.close(fig)
            receipt[team]=dict(status='DESIGN',page=f'{team}.svg',plays=[v[1].replace_index for v in choices])
            links.append(f'<article><h2>{team}</h2><p>{html.escape(profile["scheme"])}</p><a href="{team}.svg"><img loading="lazy" src="{team}.svg" alt="DESIGN: {team} representative play diagrams"></a></article>')
    document='<!doctype html><html lang="en"><meta charset="utf-8"><title>DESIGN: all-team modern play sheets</title><style>body{font:16px system-ui;background:#f1f4f3;color:#163546;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(450px,1fr));gap:16px}article{background:white;padding:16px}img{width:100%}a{color:#12639d}</style><h1>DESIGN: 32 modern team playbooks</h1><p>DESIGN: six representative calls per team, original schematics from the authored assignments. Gameplay remains unwitnessed.</p><p><a href="LEAGUE_PLAY_SHEETS.pdf">32-page printable sheet</a> | <a href="../PB_REPORT.md">Verification report and team summaries</a> | <a href="index.html">Complete Giants sheet</a></p><main>'+''.join(links)+'</main></html>\n'
    (out/'league.html').write_text(document)
    (out/'league_pages.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('DESIGN: 32 SVG pages; 32-page PDF; 192 representative play diagrams')

if __name__=='__main__':main()

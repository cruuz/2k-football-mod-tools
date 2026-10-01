#!/usr/bin/env python3
"""DESIGN: source-linked staff lineage and explicit prior-staff baselines."""
import json
from pathlib import Path
DATA='''ARZ|Nick Rallis|Gannon / Zimmer split coverage|odd|ARI|incumbent DC|azcardinals|nick-rallis
ATL|Jeff Ulbrich|Saleh / Seattle four-down|even|ATL|incumbent DC|atlantafalcons|jeff-ulbrich
BAL|Anthony Weaver|Ravens multiple under Minter|odd|MIA|new DC; 2025 Miami DC; Minter influence is not measured here|baltimoreravens|anthony-weaver
BUF|Jim Leonhard|Pettine / Ryan and Joseph pressure|odd|DEN|new DC; Denver pass-game assistant, Joseph called defense|buffalobills|jim-leonhard
CAR|Ejiro Evero|Fangio / Staley split coverage|odd|CAR|incumbent DC|panthers|ejiro-evero
CHI|Dennis Allen|Saints multiple man pressure|even|CHI|incumbent DC|chicagobears|dennis-allen
CIN|Al Golden|Notre Dame / Anarumo multiple|even|CIN|incumbent DC|bengals|al-golden
CLE|Mike Rutenberg|Saleh / Ulbrich four-down|even|ATL|new DC; Atlanta pass-game assistant, Ulbrich called defense|clevelandbrowns|mike-rutenberg
DAL|Christian Parker|Fangio split coverage|odd|PHI|new DC; Philadelphia pass-game assistant, Fangio called defense|dallascowboys|christian-parker
DEN|Vance Joseph|Phillips / Joseph pressure|odd|DEN|incumbent DC|denverbroncos|vance-joseph
DET|Kelvin Sheppard|Glenn / Allen man multiple|even|DET|incumbent DC|detroitlions|kelvin-sheppard
GB|Jonathan Gannon|Zimmer / Gannon split coverage|odd|ARI|new DC; Arizona HC, Rallis coordinated defense|packers|jonathan-gannon
HOU|Matt Burke|Ryans / Schwartz four-down|even|HOU|incumbent DC alongside Ryans|houstontexans|matt-burke
IND|Lou Anarumo|Anarumo multiple disguise|even|IND|incumbent DC|colts|lou-anarumo
JAX|Anthony Campanile|Hafley / Flores multiple|even|JAX|incumbent DC|jaguars|anthony-campanile
KC|Steve Spagnuolo|Jim Johnson pressure|even|KC|incumbent DC|chiefs|steve-spagnuolo
MIA|Sean Duggan|Hafley four-down|even|GB|new DC; Green Bay LB assistant, Hafley called defense|miamidolphins|sean-duggan
MIN|Brian Flores|Belichick pressure disguise|odd|MIN|incumbent DC|vikings|brian-flores
NE|Zak Kuhr|Vrabel / Bowen multiple|odd|NE|new title; 2025 interim playcaller on Vrabel staff|patriots|zak-kuhr
NO|Brandon Staley|Fangio split coverage|odd|NO|incumbent DC|neworleanssaints|brandon-staley
NYG|Dennard Wilson|Ravens / Eagles multiple|odd|TEN|new DC; Tennessee DC in 2025|giants|dennard-wilson
NYJ|Brian Duker|Glenn / Weaver multiple|even|MIA|new DC; Miami pass-game assistant; Glenn calls 2026 defense|newyorkjets|brian-duker
OAK|Rob Leonard|Graham / Ravens multiple|odd|LV|new DC; Raiders DL and run-game assistant under Graham|raiders|rob-leonard
PHI|Vic Fangio|Fangio split coverage|odd|PHI|incumbent DC|philadelphiaeagles|vic-fangio
PIT|Patrick Graham|Belichick multiple disguise|odd|LV|new DC; Raiders DC in 2025|steelers|patrick-graham
SD|Chris O'Leary|Minter / Notre Dame multiple|odd||new DC; Western Michigan DC in 2025; requested rates unavailable|chargers|chris-o-leary
SEA|Aden Durde|Macdonald / Quinn multiple|odd|SEA|incumbent DC; Macdonald calls defense|seahawks|aden-durde
SF|Raheem Morris|Tampa / Rams split coverage|even|ATL|new DC; Atlanta HC, Ulbrich called 2025 defense|49ers|raheem-morris
STL|Chris Shula|Phillips / Staley / Morris multiple|odd|LA|incumbent DC|therams|chris-shula
TB|Todd Bowles|Bowles / Arians pressure|odd|TB|HC and defensive playcaller; no separate DC|buccaneers|todd-bowles
TEN|Gus Bradley|Seattle / Saleh four-down|even|SF|new DC; 49ers assistant head coach, Saleh called defense|tennesseetitans|gus-bradley
WAS|Daronte Jones|Flores / Zimmer disguise|odd|MIN|new DC; Minnesota pass-game assistant, Flores called defense|commanders|daronte-jones'''

def main():
    profiles={}
    for line in DATA.splitlines():
        t,dc,fam,front,baseline,role,domain,slug=line.split('|')
        profiles[t]=dict(dc=dc,family=fam,base_front_inferred=front,baseline_team=baseline or None,baseline_role=role,
            design_fallback_team='LAC' if t=='SD' else None,
            source=f'https://www.{domain}.com/team/'+('coaches/' if t in ('CHI','PHI') else 'coaches-roster/')+slug,
            status='INFERRED',front_note='Scheme family inference, not measured aligned-front rate')
    (Path(__file__).parent/'defense_profiles.json').write_text(json.dumps(profiles,indent=2)+'\n')
if __name__=='__main__':main()

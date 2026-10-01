#!/usr/bin/env python3
"""PROVED OFFLINE: render the current defense appendix from saved receipts."""
from collections import Counter
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads((ROOT/p).read_text())
def main():
    profiles=read('pb/research/defense_profiles.json');real=read('pb/research/defense_tendencies_2025.json')['teams']
    comp=read('pb/receipts/defense/composition.json');sim=read('pb/receipts/defense/selector-summary.json')['teams']
    man=read('pb/defense_manifest.json')['teams'];nodes=max((r['nodes'],t) for t,r in comp['teams'].items());names=max((r['name_bytes'],t) for t,r in comp['teams'].items())
    totals={k:sum(r[k] for r in comp['teams'].values()) for k in ('native_validated','full_pairs','formations','pages')}
    counts=Counter();used=Counter();geometry=Counter();errors={}
    for t in profiles:
        rows=read(f'pb/defense/{t}.json');concepts=Counter(r['concept'] for r in rows['plays'] if r['component']=='coverage');counts.update(concepts);used.update(concepts.keys())
        for f in rows['formations'].values():
            for n in ('Mug','Tite','Wide','Bear'):
                if n in f['name']:geometry[n]+=1
        if profiles[t]['baseline_team']:
            rates=real[profiles[t]['baseline_team']]['rates'];errors[t]={k:sim[t]['rates'][k]-rates[k] for k in ('man','split_family','blitz')}
    maxima={k:max((abs(e[k]),t,e[k]) for t,e in errors.items()) for k in ('man','split_family','blitz')}
    lines=[
'# DESIGN: current defense composition appendix',
'',
'PROVED OFFLINE: The exact 64-pack list composes through the existing Build path into 32 team PLAY resources. All 32 defenses have distinct assignment/geometry hashes and distinct concept allocations. The phase 4 offense screens carry D timing. [Composition receipt](receipts/defense/composition.json), [defense manifest](defense_manifest.json), [phase 2 report](PB_REPORT_PHASE2.md).',
'',
'DESIGN: CPU-rate evidence is conditional. The retail candidate filters, header scores and lottery are exercised under explicit matchup/category fixtures; the full situational game plan is not reproduced. Actual pre-snap two-high, creeper and simulated-pressure rates are unavailable in the public inputs. Bounded exchanges are included; complete match policies remain omitted. KC has one versioned Spy intent; live tracking remains unwitnessed. These limits prevent claiming exact live DC replication. [Selector boundary](defense/SELECTOR.md), [library limits](defense/LIBRARY.md).',
'',
'PROVED OFFLINE: Deliverables are [32-row cited research](research/DEFENSES.md), [64-pack final overrides](recipes/final_playbooks.json), [pack removal reasons](recipes/final_playbooks.md), [32 diagram pages](diagrams/defense.html), [printable 32-page PDF](diagrams/DEFENSE_PLAY_SHEETS.pdf), [main-only CPU lab](lab/pb_lab_def.sh) and [review checklist](lab/DEFENSE_LAB.md). The final draft and frozen b76-u4 were not edited; no lab or xemu was run. The full build evidence is in PB_REPORT.md.',
'',
'PROVED OFFLINE: The phase 3 core change permits custom v2 defense validation: only CPU score bits 9-11 may differ from the verified source donor. Preset headers and every other header field remain exact. Native score-band and rejection tests cover this boundary. Import this validator change with the packs; the phase 2 validator intentionally rejects their tuned headers.',
'',
'## PROVED OFFLINE: composition and native checks',
'',
f'PROVED OFFLINE: One archive-compiler call applies all 64 packs to a read-only retail archive with in-memory writes. BuildPlan validation returns no blockers and the actual Build menu checker reports 37 books, zero problems. All five utility books stay unchanged. The largest node use is {nodes[0]:,}/3,500 ({nodes[1]}); the largest name pool is {names[0]:,}/11,088 bytes ({names[1]}). Every compiled resource remains 78,768 bytes.',
'',
f'PROVED OFFLINE: Retail `0x1A9840` accepts all {totals["native_validated"]:,} play records, then native `0x1A9A80` marks them usable. All {totals["full_pairs"]:,} enumerated defensive menu pairs cover all eleven slots. Native menu traversal covers {totals["formations"]:,} formations and {totals["pages"]:,} pages; all terminate and match their declared order. Every formation link sequence is identical before and after the defense stage, preventing the duplicate-link cycle behind the beta 59-75 hang. Six menu UI callbacks are fixture stubs.',
'',
'PROVED OFFLINE: Category codes/personnel bytes, protected special formations and their linked play names/flags/decoded scripts match retail. Goal line, prevent, FG block and punt return remain retail; phase 2 protects the other special offense/kicking menus. An independent [postcomposition preservation check](receipts/defense/preservation.json) compares every unowned phase 2 play and formation. Pool/name pointers may relocate during offense interning. Defense source fingerprints require the exact compiled phase 2 resource and reject raw retail or an incompatible offense.',
'',
'## PROVED OFFLINE: per-team comparison',
'',
'PROVED OFFLINE: Every real rate below comes from the hashed 2025 nflverse participation/PBP inputs in [research counts and denominators](research/defense_tendencies_2025.json). New coordinators use the prior staff named in [DEFENSES.md](research/DEFENSES.md); assistant/head-coach staff rates are not misrepresented as personal playcalling rates. SD has no accessible Western Michigan rates and uses an explicitly disclosed LAC design fallback.',
'',
'DESIGN: Each rate cell is real 2025 -> conditional native-model percentage. Man/zone and blitz use charted dropbacks; blitz means five or more rushers. Split is the post-snap Cover 2/2-Man/4/6/9 family proxy, not measured pre-snap two-high. Actual two-high remains NA for all 32 teams. The model folds Cover 9 into fixed Cover 6. Each team has 252 uniformly weighted synthetic down/distance/field/personnel state rows, not a replay of the 2025 opponent mix; distance is varied but not consumed by the category fixture. Goal-line selections stay in receipts and are excluded from the ordinary-defense comparison.',
'',
'| Team | INFERRED 2026 DC / family | PROVED OFFLINE man/zone % real -> model | PROVED OFFLINE split proxy % real -> model | PROVED OFFLINE blitz % real -> model | PROVED OFFLINE nodes / names | DESIGN page |',
'| --- | --- | --- | ---: | ---: | ---: | --- |']
    fmt=lambda v:f'{v:.1f}'
    for t,p in profiles.items():
        r=real[p['baseline_team']]['rates'] if p['baseline_team'] else None;s=sim[t]['rates'];b=comp['teams'][t]
        base=(fmt(r['man'])+'/'+fmt(r['zone'])) if r else 'NA/NA'
        split=fmt(r['split_family']) if r else 'NA';blitz=fmt(r['blitz']) if r else 'NA'
        cite=f'[receipt](receipts/defense/{t}-selector.json)'
        lines.append(f'| {t} | [{p["dc"]}]({p["source"]}); {p["family"]} | {base} -> {fmt(s["man"])}/{fmt(s["zone"])} | {split} -> {fmt(s["split_family"])} | {blitz} -> {fmt(s["blitz"])} {cite} | {b["nodes"]} / {b["name_bytes"]} | [{t}](diagrams/{t}_defense.svg) |')
    lines+=['',
'PROVED OFFLINE: Largest absolute model gaps among teams with a real baseline: '+ '; '.join(f'{k.replace("_"," ")} {v[0]:.2f} percentage points ({v[1]}, signed {v[2]:+.2f})' for k,v in maxima.items())+'. All gaps, including misses, remain visible; the table is not a live-game certification.',
'',
'PROVED OFFLINE: The [selector summary](receipts/defense/selector-summary.json) also reports Cover 0, replacement-pressure and authored-call shares. Finite menus and discrete score bands can make a low-frequency coverage disappear from a selected category, even when it exists in another formation. That mismatch is not hidden by counting unused calls. DESIGN: Full game-plan category selection and empirical tuning remain necessary for live distribution fidelity.',
'',
'## DESIGN: library feature use',
'',
'PROVED OFFLINE: The following counts are authored unique coverage records, not CPU probabilities or observed play counts. [Library grammar and omissions](defense/LIBRARY.md) explains the structure behind each name.',
'',
'| DESIGN concept | PROVED OFFLINE calls | PROVED OFFLINE teams using it |',
'| --- | ---: | ---: |']
    for c,n in sorted(counts.items()):lines.append(f'| {c} | {n} | {used[c]} |')
    lines+=['',
'PROVED OFFLINE: Front look counts by formation: '+', '.join(f'{k} {v}' for k,v in sorted(geometry.items()))+'. Native personnel and compatibility types remain unchanged. DESIGN: Tite spacing over retail 4-3 personnel is a geometry approximation; it does not claim a true odd roster or new gap-fit logic.',
'',
'DESIGN: Cover 3 sky/cloud and quarters exchanges use reciprocal native geometric signals. They do not implement complete modern route-distribution rules. Tampa Drop is a middle landmark, not proved vertical carry. Creeper Three and Sim Two encode four rushers with slot 5 coming from the second level and a lineman dropping; Fire Three uses five. Their live disguise/timing remains unproved. KC authors one runtime Spy; the other 31 teams declare empty records. See research/SPY.md.',
'',
'## DESIGN: final recipe and main lab',
'',
'DESIGN: Merge [final_playbooks.json](recipes/final_playbooks.json) into main\'s final recipe by replacing its whole pack array and applying `playbook_pair=false`, `read_option_runtime=false`. Drop `softdrink_option`, `modern_gun_core`, `softdrink_modern_defense` and `softdrink_match_coverage`; their generic calls are either excluded by Noah or subsumed by the per-team books. The [integration note](recipes/final_playbooks.md) gives the reason for each. QB Spy, screen D and the display-list fix inherit production settings.',
'',
'DESIGN: Main reviews and runs `bash pb/lab/pb_lab_def.sh`. It makes one retail-source build, one Giants home versus Cowboys away CPU-v-CPU attempt through the shared u5 route, timed frames and native statistics from RAM copies. No live operator commands or operator deadline are used. The supplied recipe copies the real final draft and changes only the playbook keys. Main checks both teams\' snap fronts/shells, rusher origins and counts, exchanges when visible, stat progress and repeated returns from play calling. A static screen stops the attempt without a nudge; animated stalls need frame/stat review.',
'',
'PROVED OFFLINE: Shell syntax, helper compilation, source-data checks, pack ownership and the existing Build stage ordering are checked. [New suite](receipts/defense/tests.txt), [phase 2 regression](receipts/defense/phase2-regression.txt), [defense/match regression](receipts/defense/core-regression.txt), [composition log](receipts/defense/verify-log.txt), [selector log](receipts/defense/sweep-log.txt). DESIGN: Lab execution and all gameplay conclusions remain for main.',
'',
'## PROVED OFFLINE: reproduction and delivery',
'',
'```bash',
'python3 pb/research/aggregate_defense.py --data /media/noah/Storage/.b76-research/r1/data/nflverse --output pb/research/defense_tendencies_2025.json',
'python3 pb/defense/build.py',
'python3 pb/defense/verify.py',
'python3 pb/defense/sweep.py',
'python3 pb/defense/preservation.py',
'MPLCONFIGDIR=/tmp/pb-mpl python3 pb/diagrams/render_defense.py',
'python3 pb/defense/report.py',
'python3 -m pytest -q tests/mod_editor/test_nfl2k5_dc_defenses.py',
'bash -n pb/lab/pb_lab_def.sh',
'```',
'',
'PROVED OFFLINE: Source hashes are in [source-pins.json](receipts/defense/source-pins.json). Retail resources used during offline checks stay only in private scratch, never in the commit or bundle. Derived research retains nflverse/FTN attribution and its stated license; authored packs retain CC0-1.0. Current delivery information is in PB_REPORT.md. No push, tags or writes to b76-u4 are performed.',
'',
'DESIGN: Remaining limits are the real pre-snap shell/creeper data gap, SD\'s missing prior-job baseline, full native situational selection, roster/personnel fidelity beyond native categories, live pressure and exchange behavior, actual menu stall freedom during CPU games, live Spy behavior and full match/Tampa policies. Offline validation is complete only for the specified inputs and fixtures; gameplay approval remains with main.','']
    (ROOT/'pb/DEFENSE_APPENDIX.md').write_text('\n'.join(lines))
    (ROOT/'pb/receipts/defense/rate-errors.json').write_text(json.dumps(dict(status='PROVED OFFLINE',scope='Conditional fixture versus charted baseline',teams=errors,maxima=maxima),indent=2)+'\n')
if __name__=='__main__':main()

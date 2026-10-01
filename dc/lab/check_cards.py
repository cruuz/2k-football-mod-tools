"""DESIGN: validate three recorded LAST PLAY cards; never launch an emulator."""
import argparse
import hashlib
import json
from pathlib import Path
import re
EXPECTED={'ari':('Devin Duvernay','Max Melton'),'det':('Tom Kennedy','Jacob Saylors'),
          'min':('Myles Price','Demond Claiborne')}
def check(text,names):
    lines=re.findall(r'Kickoff\s+returned\s+by\s+([^\r\n]+)',text,re.I)
    hits=[n for n in names if any(re.match(re.escape(n)+r'(?:\b|$)',line,re.I) for line in lines)]
    return {'matched':len(hits)==1,'returners':hits,'card_lines':lines}
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for team in EXPECTED:ap.add_argument('--'+team,type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    cases={}
    for team,names in EXPECTED.items():
        path=getattr(args,team);raw=path.read_bytes()
        cases[team]={**check(raw.decode(),names),'text_sha256':hashlib.sha256(raw).hexdigest(),'source':str(path)}
    report={'evidence':'PROVED OFFLINE','scope':'Text validation only; screenshot inspection belongs to main.',
            'pass':all(c['matched'] for c in cases.values()),'cases':cases}
    args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0 if report['pass'] else 1
if __name__=='__main__':raise SystemExit(main())

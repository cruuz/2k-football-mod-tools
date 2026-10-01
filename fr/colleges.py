"""DESIGN: explicit school aliases, and unused table slots for new source labels."""
import re
from .generate import readcsv,dump

ALIASES={'miamifl':'miami','southerncalifornia':'usc','louisianast':'lsu','louisianastate':'lsu','mississippi':'olemiss',
 'centralflorida':'ucf','floridaatlantic':'fau','southernmethodist':'smu','texaschristian':'tcu','brighamyoung':'byu',
 'pennst':'pennstate','ohiost':'ohiostate','michiganst':'michiganstate','floridast':'floridastate',
 'northcarolinast':'ncstate','northcarolinastate':'ncstate','connecticut':'uconn','massachusetts':'umass',
 'mississippist':'mississippistate','oregonst':'oregonstate','oklahomast':'oklahomastate','arizonast':'arizonastate',
 'iowast':'iowastate','kansasst':'kansasstate','fresnost':'fresnostate','washingtonst':'washingtonstate'}

def school(s):
    s=re.sub('[^a-z0-9]','',s.lower())
    return ALIASES.get(s,s)


# DESIGN: spelling/abbreviation equivalences, not changes of school. Preserve
# the existing shared labels rather than consuming slots for duplicate names.
SCHOOL_EQUIVALENTS = (
 ('East Tennessee State', 'East Tennessee St'),
 ('Fort Valley State College', 'Fort Valley St, GA'),
 ('Indiana PA,  University of', 'Indiana, PA'),
 ('Jackson State University', 'Jackson State'),
 ('Miami (Ohio)', 'Miami, OH'),
 ('Middle Tennessee State', 'Middle Tennessee St'),
 ('Penn', 'Pennsylvania'),
 ('Saginaw Valley State', 'Saginaw Valley'),
 ('South Carolina State', 'South Carolina St'),
 ('Southeast Missouri State', 'SE Missouri State'),
 ('Southern Mississippi', 'Southern Miss'),
 ('Southern Utah State', 'Southern Utah'),
 ('Stephen F. Austin State', 'Stephen F. Austin'),
 ('Tennessee-Chattanooga', 'Chattanooga'),
 ('Texas-El Paso', 'UTEP'),
 ('Troy', 'Troy State'),
 ('UAB', 'Alabama-Birmingham'),
 ('UMass Amherst', 'Massachusetts'),
 ('University of South Florida', 'South Florida'),
 ('Wisconsin-Whitewater', 'WI-Whitewater'),
 ('Tarleton State', 'Tarleton State, TX'),
 ('Tusculum College', 'Tusculum'),
 ('No College', 'None'),
)
for source_name, table_name in SCHOOL_EQUIVALENTS:
    ALIASES[re.sub('[^a-z0-9]', '', source_name.lower())] = school(table_name)


def update(result,doc,fa,out,*,protected_slots=None):
    if protected_slots is None:
        raise ValueError('college reclamation requires the complete disc and dataset reference census')
    rows={r['gsis_id']:r for r in readcsv(fa/'data/roster_2026.csv')}
    older={}
    for path in sorted((fa/'data').glob('roster_*.csv')):
        if path.name=='roster_2026.csv':continue
        for r in readcsv(path):
            if r['college']:older[r['gsis_id']]=(r['college'],path.name)
    wanted=[];by={(p.pool,p.index):p for p in doc.players}
    for identity in result['franchise_history']['players']:
        p=by[identity['pool'],identity['index']];g=identity['gsis_id']
        value=rows[g]['college'];src='roster_2026.csv'
        if not value:value,src=older.get(g,('Unknown','roster_2026.csv'))
        schools=[s.strip() for s in value.split(';')]
        targets={school(s) for s in schools}
        chosen=p.college if school(p.college) in targets else next((c for c in doc.colleges if school(c) in targets),schools[0])
        wanted.append(dict(pool=p.pool,index=p.index,first=p.first,last=p.last,college=chosen,
                           old_college=p.college,source=src,source_value=value,gsis_id=g))
    needed=sorted({r['college'] for r in wanted}-set(doc.colleges))
    destinations={(r['pool'],r['index']):r['college'] for r in wanted}
    used={p.college_index for p in doc.players
          if destinations.get((p.pool,p.index),p.college)==p.college} | set(protected_slots)
    # Do not retire any source label about to become referenced either.
    keep={r['college'] for r in wanted}
    slots=sorted((i for i,c in enumerate(doc.colleges) if i not in used and c not in keep),
                 key=lambda i:(-len(doc.colleges[i]),i))
    if len(slots)<len(needed):
        raise ValueError(f'only {len(slots)} globally unused college slots for {len(needed)} labels')
    result['college_aliases']=[dict(index=i,expected=doc.colleges[i],name=name) for i,name in zip(slots,needed)]
    result['college_updates']=[{k:r[k] for k in ('pool','index','first','last','college')} for r in wanted if r['college']!=r['old_college']]
    dump(out/'colleges.json',dict(aliases=result['college_aliases'],ledger=wanted,
                                protected_slots=sorted(protected_slots),school_equivalents=SCHOOL_EQUIVALENTS,
                                changed=len(result['college_updates']),unknown=[r for r in wanted if r['source_value']=='Unknown']))

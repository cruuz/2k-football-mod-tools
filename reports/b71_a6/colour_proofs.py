from concurrent.futures import ThreadPoolExecutor
from run import run
commands=[
 ('scorebug-layout',['python3','tests/nfl2k5_scorebug_layout_test.py']),
 ('scorebug-project',['python3','tests/nfl2k5_scorebug_mod_project_test.py']),
 ('colour-all-pins',['python3','tools/verify_colour_lighting_pins.py','extracted/ESPN NFL 2K5 (USA)/vc_53450030/0','--workers','4']),
]
with ThreadPoolExecutor(max_workers=2) as pool:
 codes=list(pool.map(lambda pair:run('final-'+pair[0],pair[1]),commands))
raise SystemExit(any(codes))

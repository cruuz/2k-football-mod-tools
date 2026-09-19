"""Focused checks after the fixture and immutable asset-cache improvements."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_checks as checks
checks.OUT=Path(__file__).resolve().parent/'checks_final';checks.OUT.mkdir(exist_ok=True)
names=['resources','ingame_fix','sprite','freeze_v2','freeze','assets','ingame','down_visibility','draw_order','sd','watermark','projection']
rows=[]
for name in names:
 rows.append(checks.run(checks.ROOT/'tests/mod_editor'/('test_nfl2k5_scorebug_'+name+'.py')))
 (checks.OUT/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
raise SystemExit(int(any(row['exit_code'] for row in rows)))

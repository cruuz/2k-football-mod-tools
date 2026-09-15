"""Rebuild final pins and decode the same in-memory outputs; save no retail payloads."""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from reports.b71_c5 import prove_sidelines as proof
mc = proof.mc
refit = mc._refit_fields
captured = {}

def collect(*args, **kwargs):
    result = refit(*args, **kwargs)
    captured.update(result)
    return result

mc._refit_fields = collect
try:
    pins = mc.build_pins(proof.SOURCE, workers=8,
                         progress=lambda message, done, total: print(message,flush=True) if done%50==0 else None)
finally:
    mc._refit_fields = refit
mc.PINS_PATH.write_bytes((json.dumps(pins, indent=0, sort_keys=True)+'\n').encode())
mc._PINS = pins
print('PINS_WRITTEN',len(pins['bundles']),len(pins['light_tables']),flush=True)
sys.argv = [str(Path(proof.__file__)), '--all']
proof.main(field_cache=captured)

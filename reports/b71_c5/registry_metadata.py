"""Prepare the protected registry's C5 prose update for integration; no new rows."""
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[2]
data = json.loads((ROOT/'mod_editor/capabilities/registry.v1.json').read_text())
row = next(r for r in data['capabilities'] if r['id']=='nfl2k5.presentation.modern_color_lighting')
row['input_constraints'][3] = 'Regrading needs the original retail source. Same-recipe builds can replay only recognized bytes; custom status requires its own per-bundle receipt and transform revision. C5 updates outside data in 477 bundle pins; all seven C4 rig pins and all field maps remain exact.'
row['input_constraints'][4] = 'PREDICTED turf uses the calibrated map-times-rig model. Outside uses a separate response calibrated from one day strip; other conditions and classes extrapolate it. Linked outside means, including neutral vertex shade, stay within 8 percent below FIELD and no more saturated under the model. Wear, bump detail and stripes remain outside the mean model.'
row['runtime']['scope'] = 'Offline custom parameter writes, decode read-back, byte-preserving wrappers, swatch calibration and offscreen project save/reload. All C4 field maps and seven rigs remain exact. Linked outside palettes and separate vertex tints follow FIELD predictions under every rig, including material-only fields. Outside colour across stadiums and conditions, custom settings and shimmer behaviour remain UNWITNESSED in game.'
row['selectors']['notes'] = 'Option remains Off in all presets. Broadcast resets daylight rigs to C4, outside surfaces to the C5 FIELD link, and other controls to v2.1. Retail resets every lever to its retail value. Unlink outside surfaces to use stored custom colour. Regrading needs original retail. Custom status is applied (custom) with a matching .colour-lighting.json receipt and transform revision.'
path = ROOT/'.scratch/b71_c5_registry.json'
path.write_text(json.dumps(data, indent=2)+'\n')
(ROOT/'reports/b71_c5/registry-metadata.json').write_text(json.dumps(row, indent=2)+'\n')
print('Prepared',path,'with four prose replacements, zero new capability rows')

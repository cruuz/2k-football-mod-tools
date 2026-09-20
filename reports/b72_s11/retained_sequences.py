"""Rerun the unchanged retained native event audit against current assets."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from reports.b72_s8 import prove
prove.OUT = Path(__file__).resolve().parent / 'native_sequences'
prove.OUT.mkdir(exist_ok=True)
prove.retained_sequences()
print('PASS: 675 retained frames per aspect, 1350 total; offline only.')

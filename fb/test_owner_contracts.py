"""Run the affected owner contracts; geometry/compiler source is unchanged."""
import sys,importlib,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
suite=unittest.TestSuite();loader=unittest.TestLoader()
for model in ['state_farm','mercedes_benz','highmark','att','lucas_oil','everbank','hard_rock','usbank','sofi','levis','allegiant','lambeau']:
 mod=importlib.import_module('tests.mod_editor.test_nfl2k5_'+model+'_model')
 for cls in ['Composition','ReleaseCatalog']:
  if hasattr(mod,cls):suite.addTests(loader.loadTestsFromTestCase(getattr(mod,cls)))
 if hasattr(mod,'Pins'):
  for name in loader.getTestCaseNames(mod.Pins):
   if 'compiled_stretches' not in name:suite.addTest(mod.Pins(name))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())

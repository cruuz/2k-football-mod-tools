import ast, subprocess, sys, textwrap, unittest
from pathlib import Path
sys.path[:0]=[str(Path.cwd()),str(Path.cwd()/'tests/mod_editor')]
import test_b661_workspace_qt as test
from mod_editor.studio.facade import Nfl2k5StudioFacade

def original(path, class_name, method, namespace):
    text=subprocess.check_output(['git','show','1d38df5e782ffe8115ed38e82c4c639c04b1d3b5:'+path],text=True)
    tree=ast.parse(text)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name)
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==method)
    scope={}
    exec(compile(textwrap.dedent(ast.get_source_segment(text,node)),'<base:'+path+':'+method+'>','exec'),namespace,scope)
    return scope[method]

def expect_failure(name):
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([test.WorkspaceTests(name)]))
    if len(result.failures)!=1 or result.errors:
        raise SystemExit('Baseline did not reproduce the expected assertion')
    print('EXPECTED_REGRESSION_REPRODUCED '+name,flush=True)

shell=test.shell
current=shell.StudioMainWindow._ensure_workspace
shell.StudioMainWindow._ensure_workspace=original('mod_editor/gui/studio_qt.py','StudioMainWindow','_ensure_workspace',vars(shell))
expect_failure('test_uniforms_first_cold_and_cached_without_navigation_and_no_stall')
shell.StudioMainWindow._ensure_workspace=current
from mod_editor.studio import facade
Nfl2k5StudioFacade.preview_asset=original('mod_editor/studio/facade.py','Nfl2k5StudioFacade','preview_asset',vars(facade))
expect_failure('test_cold_preview_does_not_hold_the_ui_state_lock')

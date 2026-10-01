import json,os,pathlib,subprocess,sys,time
root=pathlib.Path("/media/noah/Storage/.b76-research/a3")
modules=("test_apf_b76_situation_weights", "test_apf_b76_situation_weights_qt", "test_apf_b72_personnel_rows", "test_apf_b71_situation_mask", "test_apf_b71_situation_mask_qt", "test_apf_b71_situation_mask_install", "test_apf_playcalling_editor_qt", "test_apf_playcalling_editor_build", "test_apf_b71_editor_workflow", "test_apf_b71_editor_workflow_qt")
env=dict(os.environ,TMPDIR=str(root/"tmp"),QT_QPA_PLATFORM="offscreen")
results=[]
for module in modules:
 start=time.monotonic()
 target=root/(module+".log")
 with target.open("w") as log:
  result=subprocess.run([sys.executable,"-m","unittest","tests.mod_editor."+module,"-v"],stdout=log,stderr=subprocess.STDOUT,env=env)
 results.append(dict(module=module,exit=result.returncode,seconds=round(time.monotonic()-start,3),log=target.name))
 print(module,result.returncode,flush=True)
(root/"focused-results.json").write_text(json.dumps(dict(affinity=sorted(os.sched_getaffinity(0)),results=results),indent=2)+"\n")
sys.exit(int(any(r["exit"] for r in results)))

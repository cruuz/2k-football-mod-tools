import ast, json, os, signal, subprocess, sys, time
from pathlib import Path
root = Path(__file__).resolve().parents[2]
output = root / 'reports/b76_apf'
source = root / 'tests/mod_editor/test_apf_charge_abilities_native.py'
cls = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef))
cases = [f'tests/mod_editor/test_apf_charge_abilities_native.py::{cls.name}::{n.name}' for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
cases += ['tests/mod_editor/test_apf_b69_launch_patches.py', 'tests/mod_editor/test_apf_charge_abilities_qt.py']
env = {**os.environ, 'QT_QPA_PLATFORM':'offscreen', 'PYTHONDONTWRITEBYTECODE':'1'}
def rss_tree(pid):
    total = 0
    try:
        status = Path(f'/proc/{pid}/status').read_text()
        total += next((int(s.split()[1]) for s in status.splitlines() if s.startswith('VmRSS:')), 0)
        for child in Path(f'/proc/{pid}/task/{pid}/children').read_text().split():
            total += rss_tree(int(child))
    except (FileNotFoundError, ProcessLookupError):
        pass
    return total
rows=[]
for i,case in enumerate(cases):
    log=output/f'isolated-{i:02d}.log'
    command=['/usr/bin/time','-v',sys.executable,'-m','pytest','-q','-s','-p','no:cacheprovider',case]
    with log.open('w') as stream:
        p=subprocess.Popen(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        peak=0
        killed=False
        while p.poll() is None:
            peak=max(peak,rss_tree(p.pid))
            if peak>1_350_000:
                os.killpg(p.pid,signal.SIGKILL)
                killed=True
                break
            time.sleep(.05)
        code=p.wait()
    rows.append({'test':case,'returncode':code,'tree_peak_rss_kib':peak,'rss_guard_killed':killed,'log':str(log.relative_to(root))})
    print(json.dumps(rows[-1]),flush=True)
    (output/'isolated-results.json').write_text(json.dumps({'classification':'PROVED OFFLINE','cpu_affinity':sorted(os.sched_getaffinity(0)),'rss_guard_kib':1_350_000,'cases':rows},indent=2)+'\n')
    if code:
        sys.exit(code)

#!/usr/bin/env python3
"""Cold-boot lg2 capture runner, gated by disk/memory and the shared xemu lock.

serve --base-disc ISO --plan JSON --config TOML --scratch NEW_DIR
check --base-disc ISO
cmd --scratch DIR '{"op":"tap","button":"A","seconds":1}'

Serve makes one disc copy, applies the native repair, verifies the full physical
scope, then uses the existing private Xvfb/sound-off driver. Review every frame
before choosing another input. Save/load snapshot commands are prohibited.
The runner removes its disc, HDD and EEPROM copies on exit, retaining receipts,
frames and logs. The existing driver imposes a stricter 55 GB reserve.
"""
from __future__ import annotations
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
DRIVER=ROOT/'tools/b77/visual_xemu_driver.py'
REPAIR=ROOT/'tools/b77/lg2_repair.py'


def available_memory():
    rows=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return int(rows['MemAvailable'].split()[0])*1024


def personal_xemu():
    found=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:
            if 'xemu' not in (proc/'comm').read_text().strip().lower():continue
            argv=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
            config=None
            for i,arg in enumerate(argv):
                if arg=='-config_path' and i+1<len(argv):config=argv[i+1]
                if arg.startswith('-config_path='):config=arg.split('=',1)[1]
            if not config or not Path(config).resolve().is_relative_to(ROOT.parent.resolve()):
                found.append(int(proc.name))
        except (OSError,ValueError):continue
    return found


def gate(base_disc):
    free=shutil.disk_usage('/').free
    needed=max(40*1024**3,55_000_000_000+base_disc.stat().st_size+2*1024**3)
    memory=available_memory();personal=personal_xemu()
    return dict(ready=free>=needed and memory>=8*1024**3 and not personal,
                root_free_bytes=free,required_root_free_bytes=needed,
                memory_available_bytes=memory,personal_xemu_pids=personal)


def run(*args):
    subprocess.run([sys.executable,*map(str,args)],check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    check=sub.add_parser('check');check.add_argument('--base-disc',type=Path,required=True)
    serve=sub.add_parser('serve')
    for key in ('base-disc','plan','config','scratch'):serve.add_argument('--'+key,type=Path,required=True)
    cmd=sub.add_parser('cmd');cmd.add_argument('--scratch',type=Path,required=True);cmd.add_argument('json')
    a=p.parse_args()
    if a.command=='cmd':
        request=json.loads(a.json)
        if request.get('op') not in ('tap','wait','capture','note','status','diagnose','stop'):
            p.error('only cold-boot capture/navigation commands are allowed')
        if personal_xemu() and request['op']!='stop':p.error('personal xemu active')
        run(DRIVER,'cmd','--scratch',a.scratch,a.json);return
    conditions=gate(a.base_disc)
    print(json.dumps(conditions),flush=True)
    if a.command=='check':return
    if not conditions['ready']:p.error('live prerequisites not met; use offline proofs')
    target=a.scratch.resolve()
    if not target.is_relative_to((ROOT.parent/'.b77-scratch/lg2').resolve()):
        p.error('scratch must be inside this job scratch directory')
    if target.exists():p.error('choose a fresh scratch directory for a cold boot')
    with Path('/tmp/b77-xemu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not gate(a.base_disc)['ready']:p.error('prerequisites changed while waiting for lock')
        target.mkdir(parents=True)
        disc=target/'lg2.xiso.iso';process=None
        try:
            shutil.copyfile(a.base_disc,disc)
            run(REPAIR,'disc','--disc',disc,'--plan',a.plan,'--receipt',target/'write.json')
            run(REPAIR,'scope','--before',a.base_disc,'--after',disc,'--plan',a.plan,'--receipt',target/'scope.json')
            if personal_xemu() or available_memory()<8*1024**3:raise RuntimeError('launch gate changed')
            process=subprocess.Popen([sys.executable,str(DRIVER),'serve','--scratch',str(target),
                                      '--disc',str(disc),'--config',str(a.config),'--name','run01'])
            while process.poll() is None:
                if personal_xemu() or available_memory()<4*1024**3:
                    process.terminate()
                    raise RuntimeError('stopped private driver: personal xemu or low memory')
                time.sleep(1)
            if process.returncode:raise RuntimeError(f'driver exit {process.returncode}')
        finally:
            if process is not None and process.poll() is None:
                process.terminate();process.wait(timeout=45)
            for file in (disc,target/'snapshots.qcow2',target/'eeprom.bin'):
                file.unlink(missing_ok=True)


if __name__=='__main__':
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(143))
    main()

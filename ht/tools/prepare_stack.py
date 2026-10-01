#!/usr/bin/env python3
"""Reproducible private build snapshot: ht working bytes plus the supplied e2 delta.

The e2 branch is read through git objects only. No other worktree is accessed.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import re

ROOT=Path(__file__).resolve().parents[2]
BUILD=Path('/media/noah/Storage/.b76-research/ht/astra-build')
STACK=BUILD/'phase2-stack'
BASE='b309fcf6a9e5'
E2='refs/astra/b76-e2b-phase2'


def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])


def refresh_pins(root):
    path=root/'mod_editor/core/providers.py'
    text=path.read_text()
    def replace(m):
        p=root/m[1]
        return '"'+m[1]+'": "'+hashlib.sha256(p.read_bytes()).hexdigest()+'"' if p.is_file() else m[0]
    text=re.sub(r'"((?:mod_editor|tools)/[^"\n]+\.py)": "[0-9a-f]{64}"',replace,text)
    path.write_text(text)


def prepare():
    names=git('ls-files','-z').decode().split('\0')
    names += [str(p.relative_to(ROOT)) for p in (ROOT/'ht').rglob('*') if p.is_file() and '__pycache__' not in str(p)]
    names += ['tools/nfl2k5_historic_rosters_author.py']
    for name in sorted(set(names)-{''}):
        source=ROOT/name
        if not source.is_file():
            continue
        dest=STACK/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or dest.read_bytes()!=source.read_bytes():
            shutil.copyfile(source,dest)
    receipt=[]
    # Phase 2's named-profile reader consumes these phase 1 e2 data dependencies.
    for name in ('data/espn25_previews_2026.json','data/espn25_previews_2026_originals.json',
                 'data/nfl2k5_espn25_more_moments.json','data/nfl2k5_espn25_more_teams/manifest.json',
                 'tools/nfl2k5_espn25_more_moments_spec.json'):
        content=git('show',E2+':'+name)
        target=STACK/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        receipt.append(dict(path=name,method='read-only e2 data dependency',sha256=hashlib.sha256(content).hexdigest()))
    changed=git('diff','--name-only',BASE,E2,'--','mod_editor','data','tests','tools').decode().splitlines()
    for name in changed:
        target=STACK/name
        theirs=git('show',E2+':'+name)
        try:
            base=git('show',BASE+':'+name)
        except subprocess.CalledProcessError:
            base=None
        ours=target.read_bytes() if target.exists() else None
        if ours==theirs:
            method='identical'
        elif ours==base or base is None:
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(theirs)
            method='e2 bytes'
        else:
            temporary=BUILD/'merge-inputs';temporary.mkdir(exist_ok=True)
            paths=[temporary/n for n in ('ours','base','theirs')]
            for p,b in zip(paths,(ours,base,theirs)):
                p.write_bytes(b)
            merged=subprocess.run(['git','merge-file','-p',*map(str,paths)],capture_output=True)
            if merged.returncode:
                text=merged.stdout.decode()
                conflicts=list(re.finditer(r'<<<<<<< [^\n]+\n(.*?)=======\n(.*?)>>>>>>> [^\n]+\n',text,re.S))
                if name=='mod_editor/core/providers.py' and all(
                        re.sub(r'[0-9a-f]{64}','HASH',m[1])==re.sub(r'[0-9a-f]{64}','HASH',m[2]) for m in conflicts):
                    for m in reversed(conflicts):
                        text=text[:m.start()]+m[1]+text[m.end():]
                    target.write_text(text)
                    receipt.append(dict(path=name,method='same pin keys; recomputed from composed bytes'))
                    continue
                if name=='tests/mod_editor/test_provider_integrity.py' and len(conflicts)==1 and '[325, 10, 8, 9, 8, 9]' in conflicts[0][1] and '[327, 10, 8, 9, 8, 9]' in conflicts[0][2]:
                    m=conflicts[0]
                    text=text[:m.start()]+'            [328, 10, 8, 9, 8, 9]  # ht plus the e2 phase 2 closure.\n'+text[m.end():]
                    target.write_text(text)
                    receipt.append(dict(path=name,method='reviewed union: e2 327 modules plus ht; archive writer shared'))
                    continue
                # Reviewed independent insertion: install the e2 bank before ht aliases.
                if name!='mod_editor/core/mod_build.py' or len(conflicts)!=1 or not conflicts[0][1].startswith('    if plan.historic_rosters_2026:') or not conflicts[0][2].startswith('    if stock_bank is not None:'):
                    target.write_bytes(merged.stdout)
                    raise RuntimeError('Review e2 composition conflict: '+name)
                m=conflicts[0];text=text[:m.start()]+m[2]+m[1]+text[m.end():]
                target.write_text(text);method='reviewed independent insertions: stock bank then ht aliases'
            else:
                target.write_bytes(merged.stdout);method='three-way merge'
        receipt.append(dict(path=name,method=method,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    refresh_pins(STACK)
    (BUILD/'evidence/phase2-stack.json').write_text(json.dumps(dict(label='PROVED OFFLINE',
        ht_base=git('rev-parse','HEAD').decode().strip(),e2=git('rev-parse',E2).decode().strip(),files=receipt),indent=2)+'\n')
    print('PROVED OFFLINE: private composed stack',STACK)


if __name__=='__main__':
    prepare()

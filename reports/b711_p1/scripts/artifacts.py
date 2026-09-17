from pathlib import Path
import hashlib
import json
import subprocess
import tarfile

base=Path('/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/7d06c350-f66f-4c4d-acf4-cdbdbedff1da/scratchpad/b71/ship/assets71')
for path in sorted(base.iterdir()):
    if not path.name.endswith(('.exe','.tar.gz')): continue
    digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
    print(path.name, digest, 'sidecar=', path.with_name(path.name+'.sha256').read_text().strip(), flush=True)
    if path.suffix=='.exe':
        result=subprocess.run(['7z','l',str(path)],capture_output=True,text=True,check=True)
        for line in result.stdout.splitlines():
            if any(key in line for key in ('dist-info/METADATA','runtime/python','numpy/__init__.py','numpy/core/_multiarray_umath','numpy.libs/')): print(line)
    else:
        with tarfile.open(path) as archive:
            members=archive.getmembers()
            print('runtime entries', [m.name for m in members if '/runtime/' in m.name])
            print('requirements', [m.name for m in members if 'requirements' in m.name])
            for member in members:
                if member.name.endswith(('tools/launch_2k5_mod_studio.sh','tools/launch_apf2k8_mod_studio.sh')):
                    print(member.name, archive.extractfile(member).read().decode())

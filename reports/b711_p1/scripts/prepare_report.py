from pathlib import Path
import json
import shlex
import shutil

root=Path.cwd()
logs=root/'reports/b711_p1'
scripts=logs/'scripts'
scripts.mkdir(exist_ok=True)
for path in (root/'.scratch').glob('*.py'):
    shutil.copyfile(path,scripts/path.name)
report=root/'ASTRA_REPORT.md'
text=report.read_text().replace('No emulator was launched, no disc was copied or built,',
                              'No emulator was launched, no retail disc was copied or built,')
receipts=[]
for path in logs.glob('*.json'):
    value=json.loads(path.read_text())
    if isinstance(value,dict) and 'command' in value and 'seconds' in value:
        receipts.append((path,value))
lines=['### Standalone checks and artifact probes', '',
       '| UTC start | Seconds | Exit | Command and full output |',
       '| --- | ---: | ---: | --- |']
for path,value in sorted(receipts,key=lambda item:item[1]['start']):
    command=shlex.join(value['command']).replace('|','\\|').replace('\n',' ')
    log=path.with_suffix('.log').relative_to(root)
    lines.append(f"| {value['start']} | {value['seconds']} | {value['exit_code']} | `{command}` ([log]({log.as_posix()})) |")
lines += ['', '### Reconnaissance and orchestration commands', '',
          'The four initial calls below preceded the UTC command recorder. All used',
          'the tool-reported elapsed seconds; exact UTC starts were not retained.', '',
          '| Command | Exit | Tool seconds |', '| --- | ---: | ---: |',
          '| `pwd` and the initial `rg --files` catalog search | 0 | 0.000006171 |',
          '| `cat ASTRA_CONTEXT.md && cat BETA71_TRIAGE.md` | 0 | 0.000003978 |',
          '| `rg --files -g AGENTS.md -g !reports/** -g !external/** -g !vendor/** && git status --short && git log -1 --oneline` | 1 (no AGENTS.md match; following commands did not run) | 0.000002044 |',
          '| `rg --files packaging` plus the build-options/NumPy and CI import searches | 0 | 0.000003156 |', '',
          'Subsequent exact shell commands are also available as structured data in',
          '[shell-commands.json](reports/b711_p1/shell-commands.json). File mutations',
          'made with apply_patch are represented by the committed diff. Tool times',
          'below measure the initial tool response, not a detached job’s full run.', '']
for i,value in enumerate(json.loads((logs/'shell-commands.json').read_text()),1):
    lines.extend([f"<details><summary>{i}. {value['recorded_utc']}; exit {value.get('exit_code', 'see receipt')}; tool {value['tool_seconds']} seconds</summary>", '',
                  '```sh',value['command'],'```','','</details>',''])
lines += ['### Delivery', '',
          'Implementation commits: `f9f03c8b` and `c08b69f9`. The final evidence',
          'commit is included in `.scratch/astra-b71-p1.bundle` on',
          '`astra/b71-p1-numpy`, with the original HEAD as the prerequisite.', '',
          'The final commit, bundle creation, bundle verification and temporary-file',
          'cleanup record their exact arguments, exit codes and timings in',
          '[.scratch/delivery.json](.scratch/delivery.json). That receipt necessarily',
          'postdates the evidence commit; the executing script is retained at',
          '[scripts/finalize.py](reports/b711_p1/scripts/finalize.py).', '',
          'Retained scripts are review copies of the `.scratch` harnesses. To replay',
          'the original command layout, copy them back to `.scratch` first. No large',
          'runtime, wheel, stage, emulator prefix or retail input is in the bundle.']
text=text.split('<!-- COMMAND_LEDGER -->')[0]+'\n'.join(lines)+'\n'
report.write_text(text)
(root/'ASTRA_LAST_MESSAGE.md').write_text('''Implemented on astra/b71-p1-numpy in .scratch/private.git.

Build options work without NumPy; NumPy-dependent scorebug actions name the package and install command. Both products now declare pinned NumPy and audit staged third-party dependencies. Runtime preservation, studio, packaging and integrity checks pass after the recorded corrections.

The audited beta 71 Windows installers already contain NumPy 1.26.4. The tester's actual interpreter remains unverified. A fresh CPython ZIP rebuild and native Windows execution remain unwitnessed; the offline production wheel rebuild and package-removal gates are proved.

Delivery: .scratch/astra-b71-p1.bundle, ASTRA_REPORT.md, and reports/b711_p1. No push or emulator.
ASTRA_DONE
''')
print('REPORT_CHECK_RECEIPTS',len(receipts),'REPORT_BYTES',report.stat().st_size)

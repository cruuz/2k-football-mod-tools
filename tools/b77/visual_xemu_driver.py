#!/usr/bin/env python3
"""One action, one saved frame. No OCR or autonomous menu guesses.

Linux QA helper. Run `serve` under nice/ionice, then use `cmd` from another
terminal. Every input resumes the VM briefly, releases the pad, pauses the VM,
and captures its private window. The reviewer must inspect that frame before
choosing the next input. Snapshots live inside the standalone scratch QCOW2.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib

GUID = '030081b85e0400008e02000014010000'
CONTROLS = set('A B X Y START BACK LB RB UP DOWN LEFT RIGHT LT RT LS_LEFT LS_RIGHT LS_UP LS_DOWN RS_LEFT RS_RIGHT RS_UP RS_DOWN'.split())
MIN_FREE = 55_000_000_000  # More than 50 GiB, including a small reserve.


def run(args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw)


def write_json(path, value):
    with path.open('w', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def pids():
    r = subprocess.run(['pgrep', '-x', 'xemu'], capture_output=True, text=True)
    if r.returncode not in (0, 1):
        raise RuntimeError('Cannot check existing xemu processes')
    return [int(p) for p in r.stdout.split()]


def guard():
    free = shutil.disk_usage('/').free
    if free < MIN_FREE:
        raise RuntimeError(f'Root reserve reached: {free} bytes free')


def within(path, root):
    path = Path(path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Writable path must be inside scratch: {path}')
    return path


def config_text(original, files):
    data = tomllib.loads(original)
    # Explicit allowlist avoids inherited writable paths, snapshots or memory units.
    sections = {
        'general': {'show_welcome': False},
        'input': {'background_input_capture': True},
        'input.bindings': {'port1_driver': 'usb-xbox-gamepad', 'port1': GUID,
                           'port2': '', 'port3': '', 'port4': ''},
        'display.quality': {'surface_scale': 1},
        'display.window': {'startup_size': '640x480', 'last_width': 640, 'last_height': 480},
        'display.ui': {'aspect_ratio': '4x3', 'auto_scale': False},
        'sys': {'mem_limit': '128'},
        'sys.files': files,
    }
    # Reuse original read-only boot ROM paths; all mutable files are copied.
    for key in ('bootrom_path', 'flashrom_path'):
        sections['sys.files'][key] = data['sys']['files'][key]
    return '\n'.join('[' + section + ']\n' + '\n'.join(
        f'{k} = {json.dumps(v)}' for k, v in values.items()) + '\n'
        for section, values in sections.items())


class QMP:
    def __init__(self, path):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.settimeout(30)
        self.sock.connect(str(path))
        self.file = self.sock.makefile('rb')
        self.file.readline()
        self.call('qmp_capabilities')

    def call(self, name, args=None):
        message = {'execute': name}
        if args is not None:
            message['arguments'] = args
        self.sock.sendall((json.dumps(message) + '\n').encode())
        while True:
            raw = self.file.readline()
            if not raw:
                raise RuntimeError('QMP disconnected')
            response = json.loads(raw)
            if 'error' in response:
                raise RuntimeError(response['error'])
            if 'return' in response:
                return response['return']

    def hmp(self, line):
        result = self.call('human-monitor-command', {'command-line': line})
        if re.search(r'error|failed|could not|does not|not found', result, re.I):
            raise RuntimeError(result)
        return result

    def close(self):
        self.file.close()
        self.sock.close()


class Pad:
    def __init__(self, helper, log):
        self.log = log
        self.buffer = b''
        before = {p.resolve() for p in Path('/sys/class/input').glob('event*')}
        self.proc = subprocess.Popen(['/usr/bin/python3', str(helper)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            line = self.reply(25)
            match = re.search(r'READY path=(/dev/input/event\d+)', line)
            if not match:
                raise RuntimeError(f'Pad startup failed: {line}')
            node = Path('/sys/class/input') / Path(match[1]).name
            self.device = node.resolve()
            if self.device in before or '/devices/virtual/input/' not in str(self.device):
                raise RuntimeError('Pad is not a new virtual device')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if os.access(match[1], os.R_OK) and any(
                    os.access('/dev/input/' + p.name, os.R_OK) for p in (node / 'device').glob('js*')):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Pad input nodes are not readable')
            identity = node / 'device'
            for k, expected in {'bustype': '0003', 'vendor': '045e', 'product': '028e', 'version': '0114'}.items():
                if (identity / 'id' / k).read_text().strip() != expected:
                    raise RuntimeError('Wrong virtual pad identity')
            if not self.send('STATE').startswith('STATE keys='):
                raise RuntimeError('Pad STATE missing')
        except BaseException:
            self.close()
            raise

    def reply(self, timeout=5):
        deadline = time.monotonic() + timeout
        while b'\n' not in self.buffer:
            if not select.select([self.proc.stdout], [], [], max(0, deadline-time.monotonic()))[0]:
                raise RuntimeError('Pad ACK timeout')
            chunk = os.read(self.proc.stdout.fileno(), 4096)
            if not chunk:
                raise RuntimeError('Pad exited: ' + self.buffer.decode(errors='replace'))
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b'\n', 1)
        line = line.decode(errors='replace')
        with self.log.open('a', newline='\n') as f:
            f.write(line + '\n')
        return line

    def send(self, command):
        self.proc.stdin.write((command+'\n').encode())
        self.proc.stdin.flush()
        return self.reply()

    def tap(self, control, duration):
        ack = self.send(f'TAP {control} {duration}')
        if not ack.startswith('TAPPED ' + control + ' '):
            raise RuntimeError(ack)
        return ack

    def close(self):
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(b'QUIT\n')
                self.proc.stdin.flush()
                self.proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait(timeout=3)
        tail = self.buffer + self.proc.stdout.read()
        if tail:
            with self.log.open('a', newline='\n') as f:
                f.write(tail.decode(errors='replace'))
        for pipe in (self.proc.stdin, self.proc.stdout):
            pipe.close()
        if hasattr(self, 'device'):
            deadline = time.monotonic() + 3
            while self.device.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            if self.device.exists():
                raise RuntimeError('Owned virtual pad remains after cleanup')


class Session:
    def __init__(self, args):
        self.args = args
        self.root = args.scratch.resolve()
        self.run_dir = within(self.root / args.name, self.root)
        self.run_dir.mkdir(exist_ok=False)
        self.qmp = self.pad = self.xvfb = self.launcher = None
        self.owned = []
        self.frame_index = 0
        self.active_seconds = 0.0
        self.alive = True
        self.tag = str(self.run_dir)
        self.manifest = {}
        self.originals = {}

    def note(self, item):
        item = {'time': time.time(), **item}
        with (self.run_dir / 'events.jsonl').open('a', newline='\n') as f:
            f.write(json.dumps(item) + '\n')

    def owns(self, pid):
        try:
            return ('B77_VISUAL_RUN=' + self.tag).encode() in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0')
        except OSError:
            return False

    def start(self):
        guard()
        if pids():
            raise RuntimeError('xemu is already running; refusing launch')
        original = self.args.config.read_text()
        cfg = tomllib.loads(original)['sys']['files']
        source = Path(cfg['hdd_path']).resolve()
        hdd = self.root / 'snapshots.qcow2'
        eeprom = self.root / 'eeprom.bin'
        within(hdd, self.root)
        within(eeprom, self.root)
        if hdd.resolve() == source or eeprom.resolve() == Path(cfg['eeprom_path']).resolve():
            raise ValueError('Refusing to use original mutable files')
        for path in (self.args.config, source, Path(cfg['eeprom_path'])):
            self.originals[str(path)] = {'sha256': sha(path), 'size': path.stat().st_size,
                                         'mtime_ns': path.stat().st_mtime_ns}
        if hdd.exists():
            receipt = json.loads((self.root/'hdd_copy.json').read_text())
            if receipt['source_sha256'] != self.originals[str(source)]['sha256']:
                raise RuntimeError('Original HDD changed since copy; use a new scratch directory')
        else:
            run(['qemu-img', 'convert', '-c', '-O', 'qcow2', str(source), str(hdd)], timeout=240)
            compared = run(['qemu-img', 'compare', str(source), str(hdd)], timeout=120).stdout
            write_json(self.root/'hdd_copy.json', {'source': str(source),
                'source_sha256': self.originals[str(source)]['sha256'],
                'copy_initial_sha256': sha(hdd), 'compare': compared})
            shutil.copyfile(cfg['eeprom_path'], eeprom)
        info = json.loads(run(['qemu-img', 'info', '--output=json', str(hdd)]).stdout)
        if info['format'] != 'qcow2' or info.get('backing-filename'):
            raise RuntimeError('HDD must be a standalone QCOW2 copy')
        conf = config_text(original, {'hdd_path':str(hdd), 'eeprom_path':str(eeprom), 'dvd_path':str(self.args.disc.resolve())})
        config_path = self.run_dir / 'throwaway.toml'
        config_path.write_text(conf, newline='\n')
        for folder in ('cache', 'data', 'config', 'tmp'):
            (self.run_dir/folder).mkdir()
        for num in range(99,89,-1):
            if not Path(f'/tmp/.X11-unix/X{num}').exists():
                display = f':{num}'
                break
        else:
            raise RuntimeError('No free private display')
        self.xvfb = subprocess.Popen(['Xvfb', display, '-screen', '0', '960x720x24', '-nolisten', 'tcp'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.env = dict(os.environ, DISPLAY=display, TMPDIR=str(self.run_dir/'tmp'))
        for _ in range(50):
            if subprocess.run(['xdpyinfo'], env=self.env, capture_output=True).returncode == 0:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Private Xvfb did not start')
        for attempt in range(5):
            try:
                self.pad = Pad(Path(__file__).resolve().parents[1]/'xemu_virtual_gamepad.py', self.run_dir/'pad.log')
                break
            except RuntimeError as exc:
                self.note({'type': 'pad_retry', 'attempt': attempt + 1, 'error': str(exc)})
                if attempt == 4:
                    raise
                time.sleep(min(4, .5 * 2**attempt))
        guard()
        if pids():
            raise RuntimeError('xemu appeared during preparation; refusing launch')
        qmp_path = self.run_dir/'qmp.sock'
        command = ['flatpak','run','--socket=x11','--nosocket=pulseaudio',
            '--env=SDL_VIDEODRIVER=x11','--env=SDL_AUDIODRIVER=dummy',
            '--env=B77_VISUAL_RUN='+self.tag,
            '--env=XDG_CACHE_HOME='+str(self.run_dir/'cache'),
            '--env=XDG_DATA_HOME='+str(self.run_dir/'data'),
            '--env=XDG_CONFIG_HOME='+str(self.run_dir/'config'),
            '--env=TMPDIR='+str(self.run_dir/'tmp'),
            '--filesystem='+str(self.root), 'app.xemu.xemu',
            '-config_path',str(config_path), '-dvd_path',str(self.args.disc.resolve()),
            '-qmp', f'unix:{qmp_path},server=on,wait=off']
        with (self.run_dir/'xemu.log').open('w', newline='\n') as log:
            self.launcher = subprocess.Popen(command, env=self.env, stdout=log, stderr=subprocess.STDOUT,
                                              stdin=subprocess.DEVNULL, start_new_session=True)
        for _ in range(100):
            self.owned = [pid for pid in pids() if self.owns(pid)]
            if qmp_path.exists() and self.owned:
                break
            if self.launcher.poll() is not None:
                raise RuntimeError('xemu launcher exited; see xemu.log')
            time.sleep(.2)
        self.qmp = QMP(qmp_path)
        time.sleep(2)
        self.qmp.call('stop')
        self.manifest = {'pid':os.getpid(), 'xemu_pids':self.owned, 'display':display,
            'disc':str(self.args.disc.resolve()), 'hdd':str(hdd), 'command':command,
            'originals':self.originals, 'start_time':time.time()}
        write_json(self.run_dir/'manifest.json', self.manifest)
        return self.capture('boot')

    def capture(self, label):
        self.frame_index += 1
        clean = re.sub(r'[^A-Za-z0-9_-]', '_', label)[:65]
        path = self.run_dir/f'{self.frame_index:05d}_{clean}.png'
        wids = run(['xdotool','search','--class','xemu'], env=self.env).stdout.split()
        windows=[]
        for wid in wids:
            name=run(['xdotool','getwindowname',wid],env=self.env).stdout.strip()
            if name.lower().startswith('xemu'):
                windows.append(wid)
        if not windows:
            raise RuntimeError('No private xemu window')
        run(['import','-window',windows[-1],'-depth','8',str(path)],env=self.env,timeout=20)
        self.note({'type':'frame','path':str(path),'label':label,'active_seconds':self.active_seconds})
        return str(path)

    def execute(self, req):
        guard()
        op=req.get('op')
        note=str(req.get('note',''))
        if op in ('tap','wait'):
            seconds=float(req.get('seconds', .7 if op=='tap' else 5))
            hold=float(req.get('hold',.12))
            if not 0 <= seconds <= 55 or not .03 <= hold <= 2:
                raise ValueError('seconds must be 0..55 and hold .03..2')
            if op=='tap' and req.get('button') not in CONTROLS:
                raise ValueError('Unknown control')
            self.qmp.call('cont')
            started=time.monotonic()
            try:
                if op=='tap':
                    time.sleep(.1)
                    ack=self.pad.tap(req['button'],hold)
                    self.note({'type':'input','button':req['button'],'hold':hold,'ack':ack,'note':note})
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline:
                    guard()
                    time.sleep(min(.5,max(0,deadline-time.monotonic())))
            finally:
                self.qmp.call('stop')
                self.active_seconds += time.monotonic()-started
            time.sleep(.1)
            return {'frame':self.capture(note or req.get('button') or 'wait'), 'active_seconds':self.active_seconds}
        if op in ('save','load'):
            name=req.get('name','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',name):
                raise ValueError('Snapshot name must be 1..50 letters, digits, hyphens or underscores')
            output=self.qmp.hmp(('savevm ' if op=='save' else 'loadvm ')+name)
            self.qmp.call('stop')
            listing=self.qmp.hmp('info snapshots')
            if name not in listing:
                raise RuntimeError('Snapshot not listed')
            self.note({'type':'snapshot','op':op,'name':name,'output':output,'note':note})
            (self.root/'snapshots.txt').write_text(listing,newline='\n')
            return {'frame':self.capture(op+'_'+name),'snapshots':listing}
        if op=='capture':
            return {'frame':self.capture(note or 'inspect')}
        if op=='status':
            return {'vm':self.qmp.call('query-status'),'active_seconds':self.active_seconds,
                    'snapshots':self.qmp.hmp('info snapshots'),'free_root':shutil.disk_usage('/').free}
        if op=='diagnose':
            # Fixed read-only monitor commands. A dump writes only inside this run.
            result={'vm':self.qmp.call('query-status'), 'note':note,
                    'registers':self.qmp.hmp('info registers'),
                    'cpus':self.qmp.hmp('info cpus'),
                    'active_seconds':self.active_seconds}
            stem=self.run_dir/f'{self.frame_index:05d}_diagnostic'
            if req.get('dump_memory') is True:
                path=within(stem.with_suffix('.bin'),self.root)
                if path.exists():
                    raise ValueError('Memory dump exists; capture a new frame first')
                result['memory_output']=self.qmp.hmp(f'pmemsave 0 0x8000000 {json.dumps(str(path))}')
                result['memory_path']=str(path)
            write_json(stem.with_suffix('.json'),result)
            self.note({'type':'diagnostic','path':str(stem.with_suffix('.json'))})
            return result
        if op=='note':
            self.note({'type':'review','note':note,'frame_index':self.frame_index})
            return {'recorded':note}
        if op=='stop':
            self.alive=False
            return {'stopping':True}
        raise ValueError('Unknown operation')

    def close(self):
        if self.qmp:
            try:
                self.qmp.call('quit')
            except (OSError,RuntimeError):
                pass
            self.qmp.close()
        if self.launcher:
            try:
                self.launcher.wait(timeout=8)
            except subprocess.TimeoutExpired:
                for pid in self.owned:
                    if self.owns(pid):
                        os.kill(pid,signal.SIGTERM)
                try:
                    self.launcher.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    for pid in self.owned:
                        if self.owns(pid):
                            os.kill(pid,signal.SIGKILL)
        if self.pad:
            self.pad.close()
        if self.xvfb:
            self.xvfb.terminate()
            self.xvfb.wait(timeout=5)
        checks={path:sha(Path(path))==entry['sha256'] for path,entry in self.originals.items()}
        write_json(self.run_dir/'cleanup.json',{'original_hashes_unchanged':checks,
            'owned_xemu_remaining':[p for p in pids() if self.owns(p)],
            'active_seconds':self.active_seconds, 'end_time':time.time()})


def serve(args):
    args.scratch.mkdir(parents=True, exist_ok=True)
    if not re.fullmatch(r'run\d{2}',args.name):
        raise ValueError('Run name must be run01..run12')
    if not 1<=int(args.name[3:])<=12:
        raise ValueError('Maximum 12 runs')
    lock=(args.scratch/'driver.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    session=Session(args)
    sock_path=args.scratch.resolve()/'driver.sock'
    try:
        frame=session.start()
        if sock_path.exists():
            sock_path.unlink()
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(sock_path))
            os.chmod(sock_path,0o600)
            server.listen(1)
            server.settimeout(2)
            print(json.dumps({'ready':True,'frame':frame,'socket':str(sock_path)}),flush=True)
            while session.alive:
                guard()
                try:
                    conn,_=server.accept()
                except socket.timeout:
                    continue
                with conn:
                    conn.settimeout(60)
                    raw=b''
                    while b'\n' not in raw:
                        part=conn.recv(4096)
                        if not part:
                            break
                        raw+=part
                        if len(raw)>65536:
                            raise ValueError('Command too long')
                    try:
                        response=session.execute(json.loads(raw))
                    except Exception as exc:
                        response={'error':str(exc)}
                        session.note({'type':'error','request':raw.decode(errors='replace'),'error':str(exc)})
                    conn.sendall((json.dumps(response)+'\n').encode())
    except BaseException as exc:
        session.note({'type':'server_exit','exception':type(exc).__name__,
                      'detail':str(exc)})
        raise
    finally:
        session.close()
        sock_path.unlink(missing_ok=True)
        lock.close()


def request(scratch, message):
    """Send a single command; never retry an input with an ambiguous result."""
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(90)
        sock.connect(str(scratch.resolve()/'driver.sock'))
        sock.sendall((json.dumps(message)+'\n').encode())
        raw=b''
        while b'\n' not in raw:
            part=sock.recv(4096)
            if not part:
                raise RuntimeError('Driver disconnected before returning a result')
            raw+=part
        result=json.loads(raw)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result


def observe(args):
    """Passive frame collection. No controller input and no outcome judgment."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.label):
        raise ValueError('Observation label must be a simple filename stem')
    if not 1 <= args.seconds <= 7200 or not 1 <= args.interval <= 55:
        raise ValueError('Duration must be 1..7200 seconds; interval 1..55')
    output=within(args.scratch/(args.label+'_watch.json'),args.scratch)
    if output.exists():
        raise ValueError('Observation output exists; use a new label')
    record={'start':time.time(),'requested_active_seconds':0,'records':[]}
    write_json(output,record)
    while record['requested_active_seconds'] < args.seconds:
        seconds=min(args.interval,args.seconds-record['requested_active_seconds'])
        end=record['requested_active_seconds']+seconds
        response=request(args.scratch,{'op':'wait','seconds':seconds,
            'note':f'{args.label}_{int(end):04d}s'})
        record['requested_active_seconds']=end
        entry={'requested_active_seconds':end,**response}
        record['records'].append(entry)
        record['last_observation']=time.time()
        write_json(output,record)
        print(json.dumps(entry),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='mode',required=True)
    s=sub.add_parser('serve')
    s.add_argument('--scratch',type=Path,required=True)
    s.add_argument('--disc',type=Path,required=True)
    s.add_argument('--config',type=Path,required=True,help='Read only source config')
    s.add_argument('--name',required=True,help='run01..run12')
    c=sub.add_parser('cmd')
    c.add_argument('--scratch',type=Path,required=True)
    c.add_argument('json',help='One JSON command; see README')
    o=sub.add_parser('observe',help='Collect passive frames, with no controller input')
    o.add_argument('--scratch',type=Path,required=True)
    o.add_argument('--label',required=True)
    o.add_argument('--seconds',type=float,default=1210)
    o.add_argument('--interval',type=float,default=55)
    args=p.parse_args()
    if args.mode=='serve':
        signal.signal(signal.SIGTERM,lambda *_:sys.exit(143))
        serve(args)
    elif args.mode=='observe':
        observe(args)
    else:
        print(json.dumps(request(args.scratch,json.loads(args.json))))


if __name__=='__main__':
    main()

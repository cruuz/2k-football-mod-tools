"""DESIGN: Main-only, unwitnessed MyNFL finances and trade screen route.

Reuses the committed isolated CPU/controller harness. Every unknown screen is
an explicit miss. No trade is submitted and no existing save is loaded.
Astra must never execute this module. Syntax compilation is not a lab run.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))


def main():
    # Import only when Main actually runs the lab.
    import xemu_berman_probe as probe
    import xemu_practice_runtime as nav
    xr = probe.xr
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--xiso', type=Path, required=True)
    ap.add_argument('--run-dir', type=Path, required=True)
    args = ap.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    screens = args.run_dir / 'screens'
    screens.mkdir()
    xr.abort_if_xemu_running()
    isolation = xr.setup_isolation(args.run_dir, args.xiso)
    config = args.run_dir / 'xemu.toml'
    text = config.read_text()
    if 'mem_limit' not in text:
        text = text.replace('[sys]', '[sys]\nmem_limit = 128')
        config.write_text(text)
    port = 1234
    while not xr.port_free(port):
        port += 1
    run = probe.HeadlessRun(args.run_dir, xr.pick_display(), port)
    ledger = {'evidence': 'DESIGN', 'route': 'vb2 run4 MyNFL entry; fc finance/trade continuation unrun', 'isolation': isolation,
              'status': 'miss', 'captures': [], 'decisions': []}
    pad = None

    def capture(label):
        row = run.screenshot(label, screens)
        row['ocr'] = nav.screen_text(run)
        ledger['captures'].append(row)
        return row['ocr']

    def select_label(words, label):
        # INFERRED: retail selection uses a red horizontal highlight. Confirm
        # its text rather than guessing a front-office row number.
        for attempt in range(18):
            image = run._frame()
            w, h = image.size
            rows = []
            for y in range(h // 6, h * 9 // 10, 2):
                red = sum(1 for x in range(w // 5, w * 9 // 10, 4)
                          if (lambda c: c[0] > 80 and c[0] > c[1] * 1.7 and c[0] > c[2] * 1.7)(image.getpixel((x, y))))
                if red > w // 70:
                    rows.append(y)
            selected = ''
            if rows:
                # Several red logos are possible; inspect contiguous bands separately.
                groups = [[rows[0]]]
                for y in rows[1:]:
                    if y > groups[-1][-1] + 3:
                        groups.append([])
                    groups[-1].append(y)
                for band in groups:
                    crop = image.crop((w // 5, max(0, band[0] - 8), w * 9 // 10, min(h, band[-1] + 10)))
                    selected += ' ' + xr.normalized(xr._ocr_image(crop.resize((crop.width * 2, crop.height * 2)), 6))
            ledger['decisions'].append({'label': label, 'attempt': attempt, 'highlight_ocr': selected})
            if any(word in selected for word in words):
                nav.tap(pad, 'A', settle=2.0)
                return
            nav.tap(pad, 'DOWN', settle=0.4)
        capture('miss-' + label)
        raise xr.GateError(label, 'no verified highlighted target')

    try:
        run.start_display()
        pad = xr.Gamepad()
        run.start_xemu(args.xiso)
        state, _ = probe.reach_menu(run, pad, screens, ledger)
        if state != 'menu':
            raise xr.GateError('main-menu', 'expected fresh main menu')
        # PROVED OFFLINE: vb1 open_mycareer and vb2 run4/cmds.txt show a
        # wrapping main menu. Fresh PLAY NOW -> DOWN -> A reaches Game Modes;
        # repeated UP does not clamp at the top and previously entered The Crib.
        nav.tap(pad, 'DOWN', settle=0.8)
        nav.tap(pad, 'A', secs=0.2, settle=4.0)
        nav.wait_text(run, ('FRANCHISE', 'MYNFL', 'MY NFL'), 30, 'mynfl-entry', pad=pad)
        capture('01-game-modes')
        nav.tap(pad, 'A', secs=0.2, settle=5.0)  # MyNFL is already highlighted.
        capture('02-mynfl-settings')
        # DESIGN: replay vb2's recorded new-franchise setup. Its existing lab
        # reached Coach's Desk and Practice Squad; this fc variant is unrun.
        nav.hold(pad, 'START', 3.0)
        time.sleep(3.0)
        text = capture('02b-settings-continue')
        if 'ONTINUE' in text:
            nav.tap(pad, 'DOWN', settle=0.8)
            nav.tap(pad, 'A', secs=0.2, settle=4.0)
        time.sleep(2.0)
        capture('02c-team-select')
        nav.tap(pad, 'A', secs=0.2, settle=1.5)
        nav.hold(pad, 'START', 3.0)
        nav.wait_text(run, ('PRACTICE SQUAD', 'PRACTICESQUAD', "COACH'S DESK", "COACH'SDESK"),
                      60, 'mynfl-desk', pad=pad)
        capture('02d-coachs-desk')
        select_label(('FRONT OFFICE', 'FRONTOFFICE', 'TEAM MANAGEMENT'), 'front-office')
        capture('03-front-office')
        select_label(('FINANCES', 'SALARY CAP', 'TEAM SALARIES'), 'finances')
        text = capture('04-finances')
        if not any(word in text for word in ('CAP', 'SALAR', 'FINANC')):
            raise xr.GateError('finances', 'screen content did not confirm finances')
        nav.tap(pad, 'B', settle=2.0)
        select_label(('TRADE',), 'trade-menu')
        text = capture('05-trade')
        if 'TRADE' not in text:
            raise xr.GateError('trade', 'screen content did not confirm trade menu')
        ledger['status'] = 'captured-for-main-review'
    except Exception as exc:
        ledger['failure'] = f'{type(exc).__name__}: {exc}'
        try:
            capture('zz-failure')
        except Exception:
            pass
    finally:
        if pad is not None:
            pad.quit()
        ledger['shutdown'] = run.shutdown()
        (args.run_dir / 'fc_lab_result.json').write_text(json.dumps(ledger, indent=2) + '\n')
    return 0 if ledger['status'] == 'captured-for-main-review' else 2


if __name__ == '__main__':
    raise SystemExit(main())

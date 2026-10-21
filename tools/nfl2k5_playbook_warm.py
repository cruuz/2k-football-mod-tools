"""Compile playbook install chains in parallel, to warm the installer's memo.

A full Studio build compiles every pack into every team's book (about 15 s an
offense, 8 s a defense, one team after another). Books are independent, so this
helper compiles each book's chain of packs in its own worker process and hands
the compiled steps back. The caller only seeds its in-process memo with them,
keyed by every input of the step; the installer then runs exactly as before
(same order, same checks, same writes) and finds each step already compiled.
Anything this helper cannot compile is simply not handed back.

It is a separate script so the worker pool never re-runs the caller's main
module under the ``spawn`` start method (a build script, or the Studio GUI).

stdin:  pickle {"chains": [(before, [(pack, team), ...]), ...], "xbe": bytes | None,
                "workers": int}
stdout: pickle [[(key, compiled), ...] per chain]
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "tools")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def compile_chain(task):
    """One book: its packs in install order. Top-level for spawn pickling."""
    from mod_editor.core import nfl2k5_playbook_pack as packs

    before, steps, xbe = task
    results = []
    for pack, team in steps:
        try:
            book = packs.parse_playbook_resource(before, asset_id=f"book:{team}")
            body = before[packs.RESOURCE_HEADER_SIZE:]
            use = pack
            if team != pack.book.team or packs.book_fingerprint(body) != pack.base.book_fingerprint:
                use, _ = packs.retarget_pack(pack, team, book, body)
            compiled = packs.apply_pack_to_resource(before, use, asset_id=f"book:{team}", xbe=xbe)
        except Exception:  # noqa: BLE001 - the serial installer reports it
            break
        results.append((packs.install_step_key(before, use, team, xbe), compiled))
        before = compiled.replacement
    return results


def _exit_with_parent():
    """Pool worker initializer: end this worker as soon as the helper process ends.

    fx1 (review pr69 #1): a cancelled build kills this helper (process.kill() in prewarm_install_steps), and nothing
    ended the spawn pool's workers, which kept compiling. multiprocessing.parent_process() is the helper; its sentinel
    becomes ready when the helper exits for any reason, on Windows and POSIX alike, so a daemon thread waits on it and
    leaves at once. A normal run is unaffected: the pool ends its workers before the helper exits.
    """
    import multiprocessing
    import os
    import threading

    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def watch():
        parent.join()
        os._exit(1)

    threading.Thread(target=watch, name="exit-with-helper", daemon=True).start()


def main() -> int:
    request = pickle.load(sys.stdin.buffer)
    chains = request["chains"]
    workers = max(1, min(int(request["workers"]), len(chains)))
    tasks = [(before, steps, request["xbe"]) for before, steps in chains]
    if workers == 1:
        results = [compile_chain(task) for task in tasks]
    else:
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                 initializer=_exit_with_parent) as pool:
            results = list(pool.map(compile_chain, tasks))
    pickle.dump(results, sys.stdout.buffer, protocol=pickle.HIGHEST_PROTOCOL)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())

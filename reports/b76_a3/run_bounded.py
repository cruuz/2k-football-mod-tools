import os, pathlib, subprocess, sys, time
root = pathlib.Path("/media/noah/Storage/.b76-research/a3")
env = dict(os.environ, TMPDIR=str(root/"tmp"), APF_A3_RECEIPT=str(root/"native-receipt.json"), PYTHONUNBUFFERED="1")
with (root/"native.log").open("w") as log:
    process = subprocess.Popen([sys.executable, "-m", "unittest", "tests.mod_editor.test_apf_b76_situation_weights_native.WeightNativeTests", "-v"], stdout=log, stderr=subprocess.STDOUT, env=env)
    peak = 0
    start = time.monotonic()
    while process.poll() is None:
        try:
            status = pathlib.Path(f"/proc/{process.pid}/status").read_text()
            resident = next(int(l.split()[1]) for l in status.splitlines() if l.startswith("VmRSS:"))
            peak = max(peak, resident)
            if resident > 3_500_000:
                process.kill()
                log.write("RAM watchdog stopped test above 3,500,000 KiB\n")
        except (FileNotFoundError, StopIteration): pass
        time.sleep(.1)
    log.write(f"\nA3 elapsed_seconds={time.monotonic()-start:.3f} peak_rss_kib={peak} exit={process.returncode} affinity={sorted(os.sched_getaffinity(0))}\n")
sys.exit(process.returncode)

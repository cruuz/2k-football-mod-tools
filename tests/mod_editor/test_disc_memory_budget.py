"""Run the disc suspects in isolated processes with a 2 GiB ceiling and peak RSS.

Set NFL2K5_MUSIC_ACCEPTANCE=1 to include its four disposable retail builds.
The other suites retain their own precise missing-evidence skips.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LIMIT = 2 * 1024**3
SUSPECTS = (
    'test_nfl2k5_music_acceptance.py',
    'test_nfl2k5_music_banks.py',
    'test_nfl2k5_music_build.py',
    'test_nfl2k5_scorebug_resources.py',
    'test_xiso_layout_tolerance.py',
    'test_pack_extent_resolver.py',
    'test_nfl2k5_build_service.py',
    'test_modpack.py',
    'test_modpack_growth.py',
    'test_modpack_growth_acceptance.py',
)


def memory_meter():
    """Bound allocations before tests run, and return a native peak-RSS reader."""
    if os.name != 'nt':
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = min(LIMIT, hard) if hard != resource.RLIM_INFINITY else LIMIT
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        return lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)

    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [('PerProcessUserTimeLimit', c.c_longlong), ('PerJobUserTimeLimit', c.c_longlong),
                    ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', c.c_size_t),
                    ('MaximumWorkingSetSize', c.c_size_t), ('ActiveProcessLimit', w.DWORD),
                    ('Affinity', c.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]
    class Io(c.Structure):
        _fields_ = [(n, c.c_ulonglong) for n in ('ReadOperationCount', 'WriteOperationCount',
            'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
    class Extended(c.Structure):
        _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', Io), ('ProcessMemoryLimit', c.c_size_t),
                    ('JobMemoryLimit', c.c_size_t), ('PeakProcessMemoryUsed', c.c_size_t), ('PeakJobMemoryUsed', c.c_size_t)]
    class Counters(c.Structure):
        _fields_ = [('cb', w.DWORD), ('PageFaultCount', w.DWORD)] + [(n, c.c_size_t) for n in
            ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
             'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]; kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.GetCurrentProcess.argtypes = []; kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]; kernel.AssignProcessToJobObject.restype = w.BOOL
    job = kernel.CreateJobObjectW(None, None)
    process = kernel.GetCurrentProcess()
    limits = Extended(); limits.BasicLimitInformation.LimitFlags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.ProcessMemoryLimit = LIMIT
    if not job or not kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, process):
        raise c.WinError(c.get_last_error())
    psapi = c.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, c.c_void_p, w.DWORD]; psapi.GetProcessMemoryInfo.restype = w.BOOL
    def peak():
        counters = Counters(); counters.cb = c.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(process, c.byref(counters), counters.cb):
            raise c.WinError(c.get_last_error())
        return counters.PeakWorkingSetSize
    # Keep the job handle for this process's lifetime; process exit closes it.
    return peak


def child(path, receipt):
    peak = memory_meter()
    sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests/mod_editor')]
    sys.argv = [str(path)]
    try:
        runpy.run_path(str(path), run_name='__main__')
    finally:
        Path(receipt).write_text(json.dumps({'peak_rss_bytes': peak(), 'limit_bytes': LIMIT})+'\n')


class DiscMemoryBudgetTests(unittest.TestCase):
    def run_child(self, path, root):
        receipt = root / 'memory.json'
        receipt.unlink(missing_ok=True)
        env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM='offscreen',
                   MOD_STUDIO_NO_UPDATE_CHECK='1', OPENBLAS_NUM_THREADS='1')
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--memory-child',
                                 str(path), str(receipt)], cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=420)
        measured = json.loads(receipt.read_text()) if receipt.exists() else None
        return result, measured

    def test_each_disc_suspect_stays_below_two_gib(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for name in SUSPECTS:
                with self.subTest(test=name):
                    result, measured = self.run_child(ROOT / 'tests/mod_editor' / name, root)
                    self.assertEqual(result.returncode, 0, f'{name} failed under the 2 GiB ceiling:\n{result.stdout}\n{result.stderr}')
                    self.assertIsNotNone(measured, f'{name}: no peak memory receipt')
                    print(f"MEMORY {name}: {measured['peak_rss_bytes']} bytes", flush=True)
                    self.assertLess(measured['peak_rss_bytes'], LIMIT, name)

    def test_ceiling_refuses_an_oversized_allocation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            probe = root / 'oversized.py'
            probe.write_text(f'bytearray({LIMIT + 1})\n')
            result, measured = self.run_child(probe, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('MemoryError', result.stderr)
            self.assertIsNotNone(measured)
            self.assertLess(measured['peak_rss_bytes'], LIMIT)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--memory-child':
        child(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        unittest.main()

Use a Windows laptop checkout of `b72-t1` and the user's already extracted retail pack index. These commands exercise the Python path. The reviewed native helper is Linux-only, so allowing it on Windows still selects Python.

1. Import the bundle into an existing repository containing base `088e3f41`, then check out the branch:

   ```powershell
   git bundle verify C:\Downloads\b72-t1.bundle
   git fetch C:\Downloads\b72-t1.bundle b72-t1:b72-t1
   git switch b72-t1
   ```

2. In PowerShell at the checkout root, create a test runtime with the shipped dependency versions:

   ```powershell
   py -3.12 -m venv .venv
   $python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
   & $python -m pip install -r packaging\requirements-studio.txt
   & $python -m pip install pytest pytest-subtests
   $env:PYTHONPATH = (Get-Location).Path
   $env:B72_ROOT = (Get-Location).Path
   $env:QT_QPA_PLATFORM = 'offscreen'
   $env:MOD_STUDIO_NO_UPDATE_CHECK = '1'
   $env:NFL2K5_DISABLE_NATIVE_LZ = '1'
   $index = 'D:\2K5 Extracted\vc_53450030\0'
   $env:NFL2K5_RETAIL_INDEX = $index
   ```

   Set `$index` to the actual extracted index, including spaces as shown. No `chmod`, shell script, compiler, WSL, or native helper is needed on Windows. Pytest is only a verification dependency.

3. Run the same acceptance fixtures and save JSON results:

   ```powershell
   & $python tools\bench\b72\b72_speed_bench.py --mode import --helper off --out b72-import-off.json
   & $python tools\bench\b72\b72_retail_equipment_bench.py --no-disk-cache --index $index --out b72-retail-off.json
   & $python tools\bench\b72\b72_build_fit_bench.py --index $index --groups 32 --workers 1,8 --out b72-build-off.json
   & $python tools\bench\b72\b72_refit_bench.py b72-refit-off.json
   & $python tools\b71_t5_project_probe.py after 600
   & $python tools\bench\b72\b72_version_bench.py --index $index --design photo --out b72-version-off.json
   ```

   Check the 64x64 photographic shoe is below 5 seconds, the retail photographic sock plus mud below 6 seconds, the retail 256x256 shoe below 5 seconds with `suggestion.width = 64`, and 600-item open below 2 seconds. The 32-group benchmark must print `serial_compiles: 0`; it asserts that condition using Build's actual adapter. It measures equipment fit and serial reuse, without writing an output disc. The full version map requires the historical commits already present locally; `--revision current` measures only this candidate.

4. Allow helpers and repeat to check the fallback selection:

   ```powershell
   Remove-Item Env:\NFL2K5_DISABLE_NATIVE_LZ
   & $python tools\bench\b72\b72_speed_bench.py --mode import --helper on --out b72-import-on.json
   & $python tools\bench\b72\b72_retail_equipment_bench.py --no-disk-cache --index $index --out b72-retail-on.json
   & $python tools\bench\b72\b72_build_fit_bench.py --index $index --groups 32 --workers 1,8 --out b72-build-on.json
   ```

5. Run the byte and workflow gates:

   ```powershell
   & $python -m pytest tests\mod_editor\test_b72_equipment_speed.py tests\mod_editor\test_b70_t1_build_speed.py tests\mod_editor\test_b71_t4_equipment_project.py tests\mod_editor\test_b71_t5_project_open.py tests\mod_editor\test_nfl2k5_equipment_retail_roundtrip.py -q
   & $python -m pytest tests\mod_editor\test_shipped_tools_posix_only.py tests\mod_editor\test_shipped_tools_are_self_sufficient.py tests\mod_editor\test_nfl2k5_simulated_windows_build.py -q
   ```

6. Start Studio from this candidate checkout with its visible UI:

   ```powershell
   Remove-Item Env:\QT_QPA_PLATFORM
   & $python -m mod_editor --studio
   ```

   Open a copy of Coach Edwards's project, import one shoe and one sock, use the offered refit for an oversized shoe, then Build ALL with 32 equipment groups. Save and reopen, check the fitted or needs-refit labels, and exercise Undo. Record laptop specifications and elapsed times. Project open should not perform fitting; changing one item should check its physical group. The oversized shoe suggestion reduces detail explicitly. Inspect generated previews separately. These steps do not establish an in-game result.

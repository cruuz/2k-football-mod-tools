# Beta 71 A5 integration report

## Outcome

All 14 standalone test programs and the final strict registry validation passed. Both XBE gates passed (119 memory-write cases and 131 cave-reference cases). The font suite has five existing legacy-case skips.

Integrated scorebug v2 wings, capsule fonts, and colour v2.1 on `astra/b71-a5-scorebug-integrate` in `.scratch/private.git`. The ordinary worktree `.git` and shared branch refs were left untouched. No push and no emulator launch.

**Disc creation is blocked by the session filesystem permissions.** The exact destination folder is mounted read-only inside the execution sandbox. The build access probe failed with `OSError: [Errno 30] Read-only file system` in `tempfile._mkstemp_inner` when opening a temporary file in the output directory. No image or `.2k5patch` was removed. No completed disc exists and no disc option read-back is claimed.

## Source heads and commits

- `fable/b71-scorebug`: `3415dfc5487b54bf56afbe40f89254394984d343`
- `fable/b71-scorebug-font`: `fa44203350a9dcc01e56c27c64a2a1487b9866bf`
- `fable/b71-color2`: `a7ada82e3d55b0f6c207770fc5da838886feff9b`
- `e2f5c6e6`: `e2f5c6e61a0aa5772b0b7d858cb3fb3d35896174`

e48f69308a86b8fa0ff5c604be54c2984ee55bc1 e5afc22e33715d5c91d2f1dd25c8dc27a75b307a Document merged scorebug and prepare reproducible combined disc build
e5afc22e33715d5c91d2f1dd25c8dc27a75b307a 5dc29e391463ec1e8289030648d7910ba4e88b58 a7ada82e3d55b0f6c207770fc5da838886feff9b Merge colour v2.1 with combined scorebug wings and clock fonts
5dc29e391463ec1e8289030648d7910ba4e88b58 3415dfc5487b54bf56afbe40f89254394984d343 fa44203350a9dcc01e56c27c64a2a1487b9866bf Merge scorebug clock fonts with wings and regenerate combined resource pins

The two merges preserve both parents. Each merge used an explicitly enumerated `git add -- <paths>`, verified the staged path set, then `write-tree`, `commit-tree -p <HEAD> -p <branch>`, and `update-ref` in the private Git directory. Git does not support a partial path commit during an in-progress merge. Subsequent handoff commits use `git commit -- <explicit paths>`. The exact staged path lists are in the command output logs in `.scratch/audit/commit-font.log` and `commit-colour.log`.

## Conflict resolutions

- `mod_editor/core/nfl2k5_scorebug_exact.py` merged automatically and was inspected: wings retain `MNF_WING_LAYOUT`, the panel/logo geometry and `MNF_SOURCE["plate"] = (837, 947, 1084, 983)`. The font line retains quarter/clock/play-clock anchors at source x 872/963/1051, `_ORIGIN(1008, 3, 15)`, and capsule separators at 18/64 and 50/64.
- `tools/nfl2k5_scorebug_exact.py`: resolved `Build.__init__` with the wings line's two `mnf_panel_span` textures plus the font line's `clock_font_spans` and font4 donor decoding. Kept the compiler's appended FONT hash contribution.
- `mod_editor/core/nfl2k5_scorebug_resources.py`: provisional conflict values were replaced by the actual merged compiler output, using `Build(PACK, XBE)`, `compiler_pins(build)`, and one anchored `^KEY = .*` replacement per key. Both 27,040-byte FONT resources remain appended after the 66 panels. Combined appended bytes: 402,560.
- `mod_editor/core/nfl2k5_scorebug_runtime.py`: byte-identical to the font branch. The clock lookup uses the tenth boot name, `FirstPersonComic`, at `0xE6B490` (slot 9). Descriptor overrides are `0xA95918`, `0xA95940`, `0xA95A80`; the quarter uses `core_bug` and `0xA958F0`. Native slot-index fields remain untouched. Missing fonts preserve the native descriptors.
- The owner still reserves 1,408 code bytes and 128 data bytes. Its allocation requests and `data/nfl2k5_cave_reservations.json` are unchanged. The font report's stale final reference to 1,536 bytes was corrected to 1,408, matching its detailed capacity explanation and the code. Owner bytes changed from the wings base, so both XBE gates were required and launched.
- `mod_editor/capabilities/registry.v1.json`: retained both wings and font evidence and their runtime scope; the colour row merged automatically. No capability rows were added. Removed personal attribution from the changed runtime scope.
- `docs/mod_editor/2k5_mod_studio_changelog.md`: retained the wings, capsule-font, and colour v2.1 bullets. The colour merge conflicted only here.
- Colour owner `nfl2k5_modern_color.py` and `data/nfl2k5_modern_color_pins.json` are byte-identical to the colour v2.1 branch head. No colour implementation was rewritten.
- Removed personal attribution from imported report headings and colour documentation. Historical report claims are not treated as new test results; this report records the runs made on the combined code.

## Regenerated pins

The reproducible scripts are `.scratch/regenerate_pins.py` and its committed copy `reports/b71_a5/regenerate_pins.py`; the committed pin record is `reports/b71_a5/compiler_pins.json`. `MNF_VERSION` remains the merged v2 identity. `CLOCK_FONT_SHA256` was independently derived from the combined font spans.

```json
{
  "PATCHED_SHA256": {
    "score_bug": "0588f2f49a0f3cf40ae179dd34d1a57b25748dbc993df34b020153fcd124d8cf",
    "score_buga": "01a30410e9147f5669614fbe6fa59e0066e5defa39c7d7fae325098f51dd39f6"
  },
  "STATIC_SCENE_SHA256": "2d48ab3d3876a9e533a213c4cd22d181dc64a74f9292e5ed1a3fdd53e913de93",
  "RUNTIME_SCENE_SHA256": "291f6cb66e6c1ebe6eeb2cfccdfc2c129de3174bb26c9f7c73368fd2a9be952a",
  "RUNTIME_PINS": {
    "index": "1b4c2af593e2b61d42b5afc3ad9c67433eee2af4fc16920f8a1538640c956b10",
    "hud_before": "2c23410c05c1ec266c3176b8b201f9a48b4a45ac148110ca569e5df25984e7c8",
    "hud_after": "f915763e2090ca9f9933c6318a19f3e126f1361ae36ff4da0bbe54dd823ccc98",
    "appendix": "846864649a3b2309c476edb55fc9b14a912e062548d1a2abf474a8e3acf44063"
  },
  "PROBE_APPEND_PINS": {
    "transport": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "hooks": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "neutral": "e38a25fae3acb5fdd3ae5ddcb91798e047e1be27e862f319452ee176b6cb61fa",
    "pair": "8c7da0308c4b96d66f124ec5c83939ac0376fac623ca76b777d67be0b1cfd515",
    "mnf": "7db3d156b554e37a2cae975391ec4c4be54980e52697a17efd51c96aef622728"
  },
  "CLOCK_FONT_SHA256": "d6087a1d69f5874be8dcb37ebc2bce307c71af9309b510f05b279f4f659ced6e",
  "MNF_VERSION": "scorebug-mnf-2026-v2"
}
```

## Standalone validation

Every test below was invoked as its own Python program, with inherited `QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools`. The strict registry command uses default file checking, without `--skip-file-checks`. Durations in the table are process wall time, including startup and cleanup; the full unittest summary is in the linked log.

| Program | Exit | Wall seconds | Verdict |
| --- | ---: | ---: | --- |
| [`test_nfl2k5_scorebug_mnf`](reports/b71_a5/test_nfl2k5_scorebug_mnf.log) | 0 | 11.8 | PASS; 10 tests |
| [`test_nfl2k5_scorebug_exact`](reports/b71_a5/test_nfl2k5_scorebug_exact.log) | 0 | 74.358 | PASS; 8 tests |
| [`test_nfl2k5_scorebug_runtime`](reports/b71_a5/test_nfl2k5_scorebug_runtime.log) | 0 | 119.203 | PASS; 12 tests |
| [`test_nfl2k5_scorebug_native`](reports/b71_a5/test_nfl2k5_scorebug_native.log) | 0 | 132.24 | PASS; 4 tests |
| [`test_nfl2k5_scorebug_ingame_fix`](reports/b71_a5/test_nfl2k5_scorebug_ingame_fix.log) | 0 | 130.154 | PASS; 9 tests |
| [`test_nfl2k5_scorebug_freeze`](reports/b71_a5/test_nfl2k5_scorebug_freeze.log) | 0 | 246.444 | PASS; 7 tests |
| [`test_nfl2k5_scorebug_resources`](reports/b71_a5/test_nfl2k5_scorebug_resources.log) | 0 | 226.663 | PASS; 6 tests |
| [`test_nfl2k5_scorebug_freeze_v2`](reports/b71_a5/test_nfl2k5_scorebug_freeze_v2.log) | 0 | 382.341 | PASS; 7 tests |
| [`test_nfl2k5_scorebug_fonts`](reports/b71_a5/test_nfl2k5_scorebug_fonts.log) | 0 | 8.545 | PASS; 10 tests; 5 skipped |
| [`test_nfl2k5_scorebug_template_release`](reports/b71_a5/test_nfl2k5_scorebug_template_release.log) | 0 | 0.596 | PASS; 5 tests |
| [`test_provider_integrity`](reports/b71_a5/test_provider_integrity.log) | 0 | 9.215 | PASS; 7 tests |
| [`test_product_catalog`](reports/b71_a5/test_product_catalog.log) | 0 | 0.15 | PASS; 9 tests |
| [`test_phase1_packaging`](reports/b71_a5/test_phase1_packaging.log) | 0 | 2.249 | PASS; 23 tests |
| [`test_nfl2k5_modern_color`](reports/b71_a5/test_nfl2k5_modern_color.log) | 0 | 7.272 | PASS; 10 tests |
| [`registry-strict`](reports/b71_a5/registry-strict.log) | 1 | 0.149 | FAIL |
| [`registry-strict-rerun`](reports/b71_a5/registry-strict-rerun.log) | 0 | 0.152 | PASS |
| [`xbe-memory`](reports/b71_a5/xbe-memory.log) | 0 | 1644.911 | PASS; 119 tests |
| [`xbe-caves`](reports/b71_a5/xbe-caves.log) | 0 | 1833.88 | PASS; 131 tests |

The initial strict registry run failed because 75 ignored local evidence files were absent, beginning with `docs/research/apf_audio.md`. The files were restored as real copies from the read-only local evidence source (2,063,157 bytes total), with per-file SHA-256 records in `reports/b71_a5/evidence_hydration.json`. None was staged or bundled. The strict rerun passed with 174 capabilities. The original suite-driver exit remains 1 because it includes the earlier registry failure; all 14 standalone test programs passed.

The first detached launcher exited before the sandbox children created any test logs. This was not counted as a test run. The corrected launcher uses `setsid nohup ... &` for each job and a waiting supervisor to keep the sandbox execution session alive. Logs were polled throughout; no process-name kill command was used. The supervising script is `.scratch/launch_checks.sh`.

The two merged native renderer previews are `reports/b71_a5/combined_43.png` and `combined_wide.png` (also retained under `.scratch/combined-render/`). Both registered `FirstPersonComic` and `core_bug`. These are bounded native execution/software raster evidence, not played-game captures.

## Combined disc plan and blocker

Requested destination:

`/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-15f (scorebug v2 + colour v2.1 + widescreen).xiso.iso`

The prepared builder is `reports/b71_a5/build_testdisc71.py`, adapted from the supplied beta 70 pattern. Its `sys.path` resolves this worktree. `--plan-only` succeeded and printed:

```json
{"preset":"softdrink_advanced","scorebug":true,"scorebug_runtime":true,"modern_color":true,"widescreen":true,"scorebug_version":"scorebug-mnf-2026-v2"}
```

This is **plan read-back only**. The builder reparses the completed output's runtime HUD, XBE owner, light tables, all 477 colour bundles, and widescreen sites before exporting the patch. It requires every status to be `applied` and records the exact result under `.scratch/testdisc71/readback.json`. That file does not exist because the output directory is read-only.

The actual detached build attempt ran at `2026-09-15T19:33:31.790924+00:00`, exited 1 after 0.278 seconds, and stopped at `reports/b71_a5/build_testdisc71.py:61`, before pruning or copying any image. Its full traceback is in `reports/b71_a5/testdisc71.detached.log`; `testdisc_result.json` records the blocker and the absent disc read-back.

At access-check time the builds folder held three MOD TEST images: 15b, 15c, and 15e. The oldest was:

`/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-15b (advanced + 2026 scorebug + modern colour + widescreen).xiso.iso`

The builder checks write access first, deletes the oldest eligible image before building when the count is three or greater, preserves every `.2k5patch`, and asserts that at most three MOD TEST images remain. It refuses an already-existing named output. All pruning and result receipts are prepared; no pruning occurred in this session.

Once the output directory is writable, from this worktree run:

```bash
bash reports/b71_a5/launch_testdisc71.sh
```

The launcher detaches the build using `setsid nohup`, records `.scratch/testdisc71.pid`, and keeps a waiting supervisor alive for sandbox compatibility. Poll `.scratch/testdisc71.detached.log`; the exit status is saved in `.scratch/testdisc71.exit`. Success requires `TESTDISC71_DONE`, the image, its patch, and the parsed read-back receipt.

## Evidence limits and in-game checks

PROVED: merge ancestry and source identities; compiler-derived pin identities; test and gate results listed above; both combined native previews; the four-option Advanced build plan.

UNWITNESSED: played-game scorebug v2 behavior and the combined image. The image was not built because of the read-only output folder. Play Now intro, Franchise, timeout ownership, change-of-possession plate colour, event-slab readability, clock spacing, logos with widescreen, and the combined colour v2.1 look still need a played-game check.

## Command journal

The complete live journal is `.scratch/commands.jsonl`; detailed outputs are under `.scratch/audit/`. Times are UTC. Commands run through the audit wrapper record start, end, elapsed time and exit code. The early read-only discovery commands preceded that wrapper; their tool-reported elapsed times were sub-second except the initial Git/context read (0.955 s), and their UTC start times were not captured. They read the context, triage, brief, applicable parent instructions, project inventory, the two source reports, branch logs, the beta 70 builder and filesystem capacity. No build or validation verdict is based on an unlogged startup command. Attribution search literals are redacted in this public journal to preserve the no-names requirement; all execution/test/build commands are unchanged.

### initial-path-discovery (startup)

UTC timestamps not captured; tool-reported elapsed `4.889e-06 s`; shell exit `0`. These tool timings may exclude some execution overhead.

```bash
pwd && rg --files -g 'AGENTS.md' -g 'ASTRA_CONTEXT.md' -g 'BETA71_TRIAGE.md' -g '*B71*REPORT*' -g '*b70*' -g '*scorebug*' -g '*repin*' -g '*registry*' -g '*provider_integrity*' -g '*product_catalog*' -g '*phase1_packaging*' | head -100
```

### initial-context (startup)

UTC timestamps not captured; tool-reported elapsed `0.954827039 s`; shell exit `0`. These tool timings may exclude some execution overhead.

```bash
git status --short && git branch --show-current && git rev-parse --git-dir && cat ASTRA_CONTEXT.md && cat BETA71_TRIAGE.md
```

### initial-parent-instructions (startup)

UTC timestamps not captured; tool-reported elapsed `4.148e-06 s`; shell exit `1`. These tool timings may exclude some execution overhead.

```bash
for p in /AGENTS.md /home/AGENTS.md /home/noah/AGENTS.md /home/noah/2k-worktrees/AGENTS.md AGENTS.md; do if [ -f "$p" ]; then cat "$p"; fi; done
cat ASTRA_BRIEF.md BETA71_TRIAGE.md
rg --files -g 'AGENTS.md' -g '!reports/assets/**' .agents .codex mod_editor tools tests packaging data docs 2>/dev/null
```

### initial-source-reports (startup)

UTC timestamps not captured; tool-reported elapsed `3.977e-06 s`; shell exit `0`. These tool timings may exclude some execution overhead.

```bash
cat FABLE_B71_WINGS_REPORT_2026-09-15.md
git show fable/b71-scorebug-font:FABLE_B71_FONT_REPORT_2026-09-15.md
git log -5 --oneline fable/b71-color2
git log -5 --oneline fable/b71-scorebug
git log -5 --oneline fable/b71-scorebug-font
```

### initial-builder-and-storage (startup)

UTC timestamps not captured; tool-reported elapsed `3.697e-06 s`; shell exit `0`. These tool timings may exclude some execution overhead.

```bash
cat '/home/noah/Desktop/2K5-8 Editors/session_scripts_2026-09-15/b70/ship/build_testdisc70.py'
ls -ld '/home/noah/2K5 Mod Studio Builds' /media/noah/Storage .scratch .git
readlink -f '/home/noah/2K5 Mod Studio Builds'
df -h . /tmp /media/noah/Storage
cat .git
```

### initial-project-and-code-inspection (startup)

UTC timestamps not captured; tool-reported elapsed `5.17e-06 s`; shell exit `0`. These tool timings may exclude some execution overhead.

```bash
cat /home/noah/PROJECTS.md /home/noah/projects.json
sed -n '1,180p' packaging/repin.py
sed -n '1,200p' mod_editor/capabilities/validate_registry.py
rg -n 'compiler_pins|PACK =|XBE =|class Build|RUNTIME_SCENE_SHA256|RUNTIME_PINS|PROBE_APPEND_PINS|MNF_VERSION|CLOCK_FONT' tools/nfl2k5_scorebug* mod_editor/core/nfl2k5_scorebug* tests/mod_editor/test_nfl2k5_scorebug*
```

### private-git

Start `2026-09-15T18:57:24.593166+00:00`; end `2026-09-15T18:57:26.944605+00:00`; elapsed `2.351 s`; exit `0`.

```bash
python3 -
```

### font-diff

Start `2026-09-15T18:57:44.024754+00:00`; end `2026-09-15T18:57:44.032651+00:00`; elapsed `0.008 s`; exit `0`.

```bash
.scratch/g diff bcb0fcdf fable/b71-scorebug-font -- mod_editor/core/nfl2k5_scorebug_exact.py mod_editor/core/nfl2k5_scorebug_resources.py mod_editor/core/nfl2k5_scorebug_runtime.py tools/nfl2k5_scorebug_exact.py tests/mod_editor/test_nfl2k5_scorebug_fonts.py
```

### build-and-test-inspection

Start `2026-09-15T18:57:44.046448+00:00`; end `2026-09-15T18:57:44.072719+00:00`; elapsed `0.026 s`; exit `1`.

```bash
bash -c 'sed -n "230,330p" tools/nfl2k5_scorebug_exact.py; sed -n "1,75p" tests/mod_editor/test_nfl2k5_scorebug_exact.py; tail -55 mod_editor/capabilities/validate_registry.py; sed -n "175,300p" packaging/repin.py; rg -n "option.*read|read.*option|inspect.*build|def status|modern_color|widescreen" mod_editor/core/nfl2k5_build_service.py | head -55; ls -lh "/home/noah/2K5 Mod Studio Builds"; rg --files -g AGENTS.md mod_editor tools tests packaging data docs'
```

### merge-font

Start `2026-09-15T18:57:44.193478+00:00`; end `2026-09-15T18:57:44.285055+00:00`; elapsed `0.092 s`; exit `1`.

```bash
.scratch/g merge --no-commit --no-ff fable/b71-scorebug-font
```

### conflicts-and-runtime

Start `2026-09-15T18:58:05.378141+00:00`; end `2026-09-15T18:58:05.432506+00:00`; elapsed `0.054 s`; exit `0`.

```bash
bash -c 'rg -n -C 7 "^(<<<<<<<|=======|>>>>>>>)" docs/mod_editor/2k5_mod_studio_changelog.md mod_editor/capabilities/registry.v1.json mod_editor/core/nfl2k5_scorebug_resources.py tools/nfl2k5_scorebug_exact.py; rg -n "CODE_SIZE|CLOCK_FONT|MNF_BOXES|MNF_ANCHORS" mod_editor/core/nfl2k5_scorebug_runtime.py mod_editor/core/nfl2k5_scorebug_mnf_font.py mod_editor/core/nfl2k5_scorebug_exact.py; .scratch/g diff --stat; .scratch/g diff --cached --stat; rg -n "registry|sha256|read_bytes" packaging/repin.py | tail -20; sed -n "1,170p" tests/mod_editor/test_provider_integrity.py; rg -n "def .*inspect|def .*status|receipt|read_back|readback" mod_editor/core/mod_build.py | tail -55'
```

### conflict-hunks

Start `2026-09-15T18:58:15.769556+00:00`; end `2026-09-15T18:58:15.782406+00:00`; elapsed `0.013 s`; exit `0`.

```bash
bash -c 'rg -n -C 4 "^(<<<<<<<|=======|>>>>>>>)" docs/mod_editor/2k5_mod_studio_changelog.md mod_editor/core/nfl2k5_scorebug_resources.py tools/nfl2k5_scorebug_exact.py; sed -n "10420,10480p" mod_editor/capabilities/registry.v1.json; sed -n "465,510p" mod_editor/core/nfl2k5_scorebug_exact.py; sed -n "645,700p" mod_editor/core/nfl2k5_scorebug_resources.py'
```

### conflict-bodies

Start `2026-09-15T18:58:22.946457+00:00`; end `2026-09-15T18:58:22.971363+00:00`; elapsed `0.025 s`; exit `0`.

```bash
python3 -
```

### resolve-font

Start `2026-09-15T18:58:58.957560+00:00`; end `2026-09-15T18:58:59.027517+00:00`; elapsed `0.07 s`; exit `0`.

```bash
python3 -
```

### registry-pin-structure

Start `2026-09-15T18:59:13.664225+00:00`; end `2026-09-15T18:59:13.693157+00:00`; elapsed `0.029 s`; exit `0`.

```bash
python3 -
```

### color-changes

Start `2026-09-15T18:59:13.724654+00:00`; end `2026-09-15T18:59:13.747998+00:00`; elapsed `0.023 s`; exit `0`.

```bash
.scratch/g diff e2f5c6e6 fable/b71-color2 --stat
```

### option-readback-inspection

Start `2026-09-15T18:59:13.778779+00:00`; end `2026-09-15T18:59:13.789267+00:00`; elapsed `0.01 s`; exit `0`.

```bash
bash -c 'rg -n "^def inspect|scorebug_runtime|modern_color|widescreen" mod_editor/core/mod_build.py | head -65; rg -n "^def |VERSION" mod_editor/core/nfl2k5_modern_color.py; sed -n "1,130p" tests/mod_editor/test_xbe_patch_cave_references.py; sed -n "1,80p" tests/mod_editor/test_xbe_patch_memory_writes.py'
```

### inspect-colour-report

Start `2026-09-15T18:59:34.546284+00:00`; end `2026-09-15T18:59:34.550358+00:00`; elapsed `0.004 s`; exit `0`.

```bash
.scratch/g show fable/b71-color2:FABLE_B71_COLOR2_REPORT_2026-09-15.md
```

### inspect-live-jobs

Start `2026-09-15T18:59:34.579602+00:00`; end `2026-09-15T18:59:34.590378+00:00`; elapsed `0.011 s`; exit `0`.

```bash
bash -c 'ps -eo pid,ppid,sid,etime,pcpu,rss,args | rg "regenerate_pins.py|audit.py|test_xbe"; tail -8 .scratch/audit/regenerate-pins.log; du -sh .scratch'
```

### regenerate-pins

Start `2026-09-15T18:58:59.059129+00:00`; end `2026-09-15T18:59:39.765804+00:00`; elapsed `40.707 s`; exit `0`.

```bash
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 .scratch/regenerate_pins.py
```

### commit-font

Start `2026-09-15T19:00:05.627478+00:00`; end `2026-09-15T19:00:05.768979+00:00`; elapsed `0.142 s`; exit `0`.

```bash
python3 .scratch/commit_merge.py 'Merge scorebug clock fonts with wings and regenerate combined resource pins' fable/b71-scorebug-font
```

### merge-colour

Start `2026-09-15T19:00:05.799639+00:00`; end `2026-09-15T19:00:05.894400+00:00`; elapsed `0.095 s`; exit `1`.

```bash
.scratch/g merge --no-commit --no-ff fable/b71-color2
```

### repin-font

Start `2026-09-15T18:59:50.951626+00:00`; end `2026-09-15T19:00:11.998152+00:00`; elapsed `21.047 s`; exit `0`.

```bash
python3 packaging/repin.py --apply
```

### resolve-colour

Start `2026-09-15T19:00:26.005131+00:00`; end `2026-09-15T19:00:26.033328+00:00`; elapsed `0.028 s`; exit `0`.

```bash
python3 -
```

### manifest-and-ownership

Start `2026-09-15T19:00:26.062686+00:00`; end `2026-09-15T19:00:26.119064+00:00`; elapsed `0.056 s`; exit `0`.

```bash
bash -c '.scratch/g diff fable/b71-scorebug -- data/nfl2k5_cave_reservations.json; .scratch/g diff fable/b71-scorebug-font -- mod_editor/core/nfl2k5_scorebug_runtime.py; .scratch/g diff fable/b71-color2 -- mod_editor/core/nfl2k5_modern_color.py data/nfl2k5_modern_color_pins.json; rg -n "^<<<<<<<|^=======|^>>>>>>>" mod_editor/core/nfl2k5_scorebug_resources.py tools/nfl2k5_scorebug_exact.py docs/mod_editor/2k5_mod_studio_changelog.md; .scratch/g status --short'
```

### repin-combined

Start `2026-09-15T19:00:52.661810+00:00`; end `2026-09-15T19:01:03.540514+00:00`; elapsed `10.879 s`; exit `0`.

```bash
python3 packaging/repin.py --apply
```

### commit-colour

Start `2026-09-15T19:01:03.570498+00:00`; end `2026-09-15T19:01:03.669683+00:00`; elapsed `0.099 s`; exit `0`.

```bash
python3 .scratch/commit_merge.py 'Merge colour v2.1 with combined scorebug wings and clock fonts' fable/b71-color2
```

### launch-checks

Start `2026-09-15T19:01:03.699070+00:00`; end `2026-09-15T19:01:03.702581+00:00`; elapsed `0.004 s`; exit `0`.

```bash
bash -c 'setsid nohup python3 .scratch/audit.py all-suites python3 .scratch/run_suites.py > .scratch/suites.detached.log 2>&1 < /dev/null & echo $! > .scratch/suites.pid
setsid nohup python3 .scratch/audit.py xbe-memory env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_xbe_patch_memory_writes.py > .scratch/xbe-memory.detached.log 2>&1 < /dev/null & echo $! > .scratch/xbe-memory.pid
setsid nohup python3 .scratch/audit.py xbe-caves env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_xbe_patch_cave_references.py > .scratch/xbe-caves.detached.log 2>&1 < /dev/null & echo $! > .scratch/xbe-caves.pid
cat .scratch/suites.pid .scratch/xbe-memory.pid .scratch/xbe-caves.pid'
```

### build-readback-code

Start `2026-09-15T19:01:10.874384+00:00`; end `2026-09-15T19:01:10.895093+00:00`; elapsed `0.021 s`; exit `2`.

```bash
bash -c 'sed -n "655,745p" mod_editor/core/mod_build.py; sed -n "1,80p" mod_editor/core/nfl2k5_modern_color.py; sed -n "645,685p" mod_editor/core/nfl2k5_modern_color.py; rg -n "scorebug_runtime|scorebug" mod_editor/core/nfl2k5_throw_tuning.py | tail -25; rg -n "MODERN|version|v2.1" data/nfl2k5_modern_color_pins.json | head -10; rg -n "def _check_floor|space.*floor|ensure.*space|TMPDIR|TemporaryDirectory|cache_dir" mod_editor/core/mod_build.py mod_editor/core/nfl2k5_build_cache.py'
```

### build-output-access

Start `2026-09-15T19:01:11.012204+00:00`; end `2026-09-15T19:01:11.117496+00:00`; elapsed `0.105 s`; exit `1`.

```bash
python3 -
```

### check-progress

Start `2026-09-15T19:01:24.823219+00:00`; end `2026-09-15T19:01:24.839319+00:00`; elapsed `0.016 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -8 .scratch/audit/xbe-memory.log; tail -8 .scratch/audit/xbe-caves.log; cat .scratch/suites.pid .scratch/xbe-memory.pid .scratch/xbe-caves.pid; rg -n "^def inspect|widescreen|scorebug_runtime|modern_color" mod_editor/core/mod_build.py | head -25; sed -n "685,705p" mod_editor/core/nfl2k5_modern_color.py; rg -n "def .*runtime_image_status|def status" tools/nfl2k5_scorebug_reference.py tools/nfl2k5_scorebug_layout.py'
```

### test_nfl2k5_scorebug_mnf

Start `2026-09-15T19:01:44.881815+00:00`; end `2026-09-15T19:01:56.682273+00:00`; elapsed `11.8 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py
```

### readback-contracts

Start `2026-09-15T19:02:02.009595+00:00`; end `2026-09-15T19:02:02.025278+00:00`; elapsed `0.016 s`; exit `0`.

```bash
bash -c 'sed -n "1,100p" tools/nfl2k5_scorebug_reference.py; rg -n "def runtime_image_status|def runtime_status|def status" mod_editor/core/nfl2k5_scorebug_ingame.py mod_editor/core/nfl2k5_scorebug_runtime.py; sed -n "850,885p" tools/nfl2k5_scorebug_layout.py; sed -n "575,635p" mod_editor/core/mod_build.py; sed -n "815,850p" mod_editor/core/nfl2k5_scorebug_resources.py; ls -lh .scratch/audit/test* .scratch/audit/xbe*'
```

### inventory-layout

Start `2026-09-15T19:02:02.027387+00:00`; end `2026-09-15T19:02:02.064333+00:00`; elapsed `0.037 s`; exit `0`.

```bash
python3 -
```

### test_nfl2k5_scorebug_exact

Start `2026-09-15T19:01:56.717102+00:00`; end `2026-09-15T19:03:11.074895+00:00`; elapsed `74.358 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py
```

### testdisc-plan

Start `2026-09-15T19:03:15.666264+00:00`; end `2026-09-15T19:03:15.929057+00:00`; elapsed `0.263 s`; exit `0`.

```bash
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 reports/b71_a5/build_testdisc71.py --plan-only
```

### check-progress-2

Start `2026-09-15T19:03:15.961336+00:00`; end `2026-09-15T19:03:15.970677+00:00`; elapsed `0.009 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -8 .scratch/audit/xbe-memory.log; tail -8 .scratch/audit/xbe-caves.log; rg -n "^def status" mod_editor/core/nfl2k5_widescreen.py'
```

### merged-intent-review

Start `2026-09-15T19:03:54.660854+00:00`; end `2026-09-15T19:03:54.930694+00:00`; elapsed `0.27 s`; exit `0`.

```bash
python3 -
```

### detached-status

Start `2026-09-15T19:03:54.983871+00:00`; end `2026-09-15T19:03:54.991655+00:00`; elapsed `0.008 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log; du -sh .scratch'
```

### combined-native-renders

Start `2026-09-15T19:04:22.784646+00:00`; end `2026-09-15T19:04:32.929186+00:00`; elapsed `10.145 s`; exit `0`.

```bash
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 .scratch/render_combined.py
```

### changed-prose-check

Start `2026-09-15T19:04:35.626685+00:00`; end `2026-09-15T19:04:35.657612+00:00`; elapsed `0.031 s`; exit `0`.

```bash
bash -c '.scratch/g diff e2f5c6e6 HEAD -- docs/mod_editor/2k5_mod_studio_changelog.md docs/modern_color/README.md mod_editor/capabilities/registry.v1.json | rg -n "^\+.*([attribution]|[attribution]|[attribution]|[attribution]|reporter|tester)" || test $? = 1
rg -n "[attribution]|[attribution]|[attribution]|[attribution]" FABLE_B71_FONT_REPORT_2026-09-15.md FABLE_B71_COLOR2_REPORT_2026-09-15.md FABLE_B71_WINGS_REPORT_2026-09-15.md || test $? = 1'
```

### check-progress-3

Start `2026-09-15T19:04:35.687484+00:00`; end `2026-09-15T19:04:35.695643+00:00`; elapsed `0.008 s`; exit `0`.

```bash
bash -c 'tail -10 .scratch/audit/test_nfl2k5_scorebug_runtime.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log; tail -6 .scratch/audit/combined-native-renders.log'
```

### anonymous-handoff-docs

Start `2026-09-15T19:05:00.735111+00:00`; end `2026-09-15T19:05:00.758462+00:00`; elapsed `0.023 s`; exit `0`.

```bash
python3 -
```

### corrected-report-footer

Start `2026-09-15T19:05:00.789154+00:00`; end `2026-09-15T19:05:00.812081+00:00`; elapsed `0.023 s`; exit `0`.

```bash
python3 -
```

### current-tests

Start `2026-09-15T19:05:00.841591+00:00`; end `2026-09-15T19:05:00.867231+00:00`; elapsed `0.026 s`; exit `0`.

```bash
python3 -
```

### image-evidence

Start `2026-09-15T19:05:09.451099+00:00`; end `2026-09-15T19:05:09.514516+00:00`; elapsed `0.063 s`; exit `0`.

```bash
python3 -
```

### test_nfl2k5_scorebug_runtime

Start `2026-09-15T19:03:11.107687+00:00`; end `2026-09-15T19:05:10.310502+00:00`; elapsed `119.203 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py
```

### builder-contract-review

Start `2026-09-15T19:05:18.235718+00:00`; end `2026-09-15T19:05:18.248363+00:00`; elapsed `0.013 s`; exit `0`.

```bash
bash -c 'sed -n "877,937p" mod_editor/core/nfl2k5_scorebug_ingame.py; sed -n "560,605p" mod_editor/core/nfl2k5_widescreen.py; rg -n "def export|def changed_file_operations" mod_editor/core/modpack.py mod_editor/core/modpack_ops.py; sed -n "1,40p" docs/modern_color/README.md; tail -12 .scratch/audit/all-suites.log'
```

### finish-doc-sanitizing

Start `2026-09-15T19:05:50.114682+00:00`; end `2026-09-15T19:05:50.137126+00:00`; elapsed `0.022 s`; exit `0`.

```bash
python3 -
```

### script-syntax

Start `2026-09-15T19:05:50.168695+00:00`; end `2026-09-15T19:05:50.205154+00:00`; elapsed `0.036 s`; exit `0`.

```bash
bash -c 'python3 -m py_compile reports/b71_a5/build_testdisc71.py; bash -n reports/b71_a5/launch_testdisc71.sh'
```

### progress-4

Start `2026-09-15T19:05:50.233637+00:00`; end `2026-09-15T19:05:50.239370+00:00`; elapsed `0.006 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log'
```

### branch-integrity

Start `2026-09-15T19:06:19.678659+00:00`; end `2026-09-15T19:06:19.687654+00:00`; elapsed `0.009 s`; exit `0`.

```bash
.scratch/g diff --check
```

### delivery-snapshot

Start `2026-09-15T19:06:19.718248+00:00`; end `2026-09-15T19:06:19.758989+00:00`; elapsed `0.041 s`; exit `0`.

```bash
python3 -
```

### progress-5

Start `2026-09-15T19:06:19.791133+00:00`; end `2026-09-15T19:06:19.799837+00:00`; elapsed `0.009 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -10 .scratch/audit/test_nfl2k5_scorebug_native.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log'
```

### test_nfl2k5_scorebug_native

Start `2026-09-15T19:05:10.344040+00:00`; end `2026-09-15T19:07:22.583716+00:00`; elapsed `132.24 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_native.py
```

### draft-report

Start `2026-09-15T19:08:12.590921+00:00`; end `2026-09-15T19:08:12.634638+00:00`; elapsed `0.044 s`; exit `0`.

```bash
python3 .scratch/make_report.py
```

### progress-6

Start `2026-09-15T19:08:12.664565+00:00`; end `2026-09-15T19:08:12.669526+00:00`; elapsed `0.005 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log'
```

### progress-7

Start `2026-09-15T19:08:26.144276+00:00`; end `2026-09-15T19:08:26.179546+00:00`; elapsed `0.035 s`; exit `0`.

```bash
bash -c 'tail -10 .scratch/audit/test_nfl2k5_scorebug_ingame_fix.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log; rg -n "^ASPECTS|16:9|def export\(" mod_editor/core/nfl2k5_widescreen.py mod_editor/core/modpack.py | head -10; sed -n "1420,1445p" mod_editor/core/modpack.py; du -sh .scratch; .scratch/g status --short'
```

### strengthen-disc-readback

Start `2026-09-15T19:08:57.744732+00:00`; end `2026-09-15T19:08:57.777863+00:00`; elapsed `0.033 s`; exit `0`.

```bash
python3 -
```

### handoff-script-check

Start `2026-09-15T19:08:57.809608+00:00`; end `2026-09-15T19:08:57.850465+00:00`; elapsed `0.041 s`; exit `0`.

```bash
bash -c 'python3 -m py_compile reports/b71_a5/build_testdisc71.py && bash -n reports/b71_a5/launch_testdisc71.sh'
```

### progress-8

Start `2026-09-15T19:08:57.900554+00:00`; end `2026-09-15T19:08:57.907436+00:00`; elapsed `0.007 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log'
```

### gate-age

Start `2026-09-15T19:09:13.367591+00:00`; end `2026-09-15T19:09:13.390141+00:00`; elapsed `0.023 s`; exit `0`.

```bash
python3 -
```

### test_nfl2k5_scorebug_ingame_fix

Start `2026-09-15T19:07:22.618708+00:00`; end `2026-09-15T19:09:32.772570+00:00`; elapsed `130.154 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py
```

### preserve-reproduction-files

Start `2026-09-15T19:09:48.051699+00:00`; end `2026-09-15T19:09:48.077289+00:00`; elapsed `0.026 s`; exit `0`.

```bash
python3 -
```

### public-diff-check

Start `2026-09-15T19:09:48.108962+00:00`; end `2026-09-15T19:09:48.208508+00:00`; elapsed `0.1 s`; exit `1`.

```bash
python3 -
```

### remaining-attribution

Start `2026-09-15T19:09:58.202788+00:00`; end `2026-09-15T19:09:58.226279+00:00`; elapsed `0.023 s`; exit `0`.

```bash
python3 -
```

### remove-final-attribution

Start `2026-09-15T19:10:12.681514+00:00`; end `2026-09-15T19:10:12.706098+00:00`; elapsed `0.025 s`; exit `0`.

```bash
python3 -
```

### public-diff-check-final

Start `2026-09-15T19:10:12.736398+00:00`; end `2026-09-15T19:10:12.824235+00:00`; elapsed `0.088 s`; exit `0`.

```bash
python3 -
```

### progress-9

Start `2026-09-15T19:10:59.020089+00:00`; end `2026-09-15T19:10:59.047044+00:00`; elapsed `0.027 s`; exit `0`.

```bash
python3 -
```

### gate-progress-map

Start `2026-09-15T19:11:22.295414+00:00`; end `2026-09-15T19:11:22.347921+00:00`; elapsed `0.053 s`; exit `0`.

```bash
python3 -
```

### startup-journal-and-helper

Start `2026-09-15T19:12:13.023127+00:00`; end `2026-09-15T19:12:13.052499+00:00`; elapsed `0.029 s`; exit `0`.

```bash
python3 -
```

### progress-10

Start `2026-09-15T19:12:13.085707+00:00`; end `2026-09-15T19:12:13.092937+00:00`; elapsed `0.007 s`; exit `0`.

```bash
bash -c 'tail -12 .scratch/audit/all-suites.log; tail -12 .scratch/audit/xbe-memory.log; tail -12 .scratch/audit/xbe-caves.log'
```

### progress-11

Start `2026-09-15T19:13:19.657367+00:00`; end `2026-09-15T19:13:19.681444+00:00`; elapsed `0.024 s`; exit `0`.

```bash
python3 -
```

### test_nfl2k5_scorebug_freeze

Start `2026-09-15T19:09:32.804835+00:00`; end `2026-09-15T19:13:39.249324+00:00`; elapsed `246.444 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py
```

### progress-12

Start `2026-09-15T19:14:27.020231+00:00`; end `2026-09-15T19:14:27.030080+00:00`; elapsed `0.01 s`; exit `0`.

```bash
bash -c 'tail -18 .scratch/audit/all-suites.log; tail -12 .scratch/audit/xbe-memory.log; tail -12 .scratch/audit/xbe-caves.log; ls -lh .scratch/audit/test_nfl2k5_scorebug_resources.log'
```

### progress-13

Start `2026-09-15T19:15:40.808139+00:00`; end `2026-09-15T19:15:40.842630+00:00`; elapsed `0.034 s`; exit `0`.

```bash
python3 -
```

### final-source-identity

Start `2026-09-15T19:16:08.171360+00:00`; end `2026-09-15T19:16:08.285791+00:00`; elapsed `0.114 s`; exit `0`.

```bash
python3 -
```

### progress-14

Start `2026-09-15T19:17:14.976700+00:00`; end `2026-09-15T19:17:14.985540+00:00`; elapsed `0.009 s`; exit `0`.

```bash
bash -c 'tail -18 .scratch/audit/all-suites.log; tail -12 .scratch/audit/xbe-memory.log; tail -12 .scratch/audit/xbe-caves.log; tail -12 .scratch/audit/test_nfl2k5_scorebug_resources.log'
```

### test_nfl2k5_scorebug_resources

Start `2026-09-15T19:13:39.282575+00:00`; end `2026-09-15T19:17:25.945206+00:00`; elapsed `226.663 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py
```

### gate-counts

Start `2026-09-15T19:17:33.930142+00:00`; end `2026-09-15T19:17:34.094247+00:00`; elapsed `0.164 s`; exit `0`.

```bash
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 -
```

### progress-15

Start `2026-09-15T19:18:39.520276+00:00`; end `2026-09-15T19:18:39.550227+00:00`; elapsed `0.03 s`; exit `0`.

```bash
python3 -
```

### progress-16

Start `2026-09-15T19:19:50.708770+00:00`; end `2026-09-15T19:19:50.719743+00:00`; elapsed `0.011 s`; exit `0`.

```bash
bash -c 'tail -18 .scratch/audit/all-suites.log; tail -8 .scratch/audit/xbe-memory.log; tail -8 .scratch/audit/xbe-caves.log; tail -8 .scratch/audit/test_nfl2k5_scorebug_freeze_v2.log'
```

### progress-17

Start `2026-09-15T19:21:00.844997+00:00`; end `2026-09-15T19:21:00.877409+00:00`; elapsed `0.032 s`; exit `0`.

```bash
python3 -
```

### checkpoint-bundle

Start `2026-09-15T19:21:17.813108+00:00`; end `2026-09-15T19:21:17.906578+00:00`; elapsed `0.093 s`; exit `0`.

```bash
.scratch/g bundle create .scratch/astra-b71-a5.bundle astra/b71-a5-scorebug-integrate '^e2f5c6e6'
```

### checkpoint-bundle-verify

Start `2026-09-15T19:21:17.942794+00:00`; end `2026-09-15T19:21:17.957252+00:00`; elapsed `0.014 s`; exit `0`.

```bash
.scratch/g bundle verify .scratch/astra-b71-a5.bundle
```

### checkpoint-size

Start `2026-09-15T19:21:18.000839+00:00`; end `2026-09-15T19:21:18.004536+00:00`; elapsed `0.004 s`; exit `0`.

```bash
du -sh .scratch
```

### reproduction-script-portability

Start `2026-09-15T19:21:39.071550+00:00`; end `2026-09-15T19:21:39.100722+00:00`; elapsed `0.029 s`; exit `0`.

```bash
python3 -
```

### progress-18

Start `2026-09-15T19:22:31.761684+00:00`; end `2026-09-15T19:22:31.789568+00:00`; elapsed `0.028 s`; exit `0`.

```bash
python3 -
```

### preserve-merge-evidence

Start `2026-09-15T19:22:54.705649+00:00`; end `2026-09-15T19:22:54.736008+00:00`; elapsed `0.03 s`; exit `0`.

```bash
python3 -
```

### progress-19

Start `2026-09-15T19:23:44.474758+00:00`; end `2026-09-15T19:23:44.502562+00:00`; elapsed `0.028 s`; exit `0`.

```bash
python3 -
```

### test_nfl2k5_scorebug_freeze_v2

Start `2026-09-15T19:17:25.983794+00:00`; end `2026-09-15T19:23:48.325207+00:00`; elapsed `382.341 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py
```

### test_nfl2k5_scorebug_fonts

Start `2026-09-15T19:23:48.356638+00:00`; end `2026-09-15T19:23:56.901210+00:00`; elapsed `8.545 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py
```

### test_nfl2k5_scorebug_template_release

Start `2026-09-15T19:23:56.934213+00:00`; end `2026-09-15T19:23:57.530051+00:00`; elapsed `0.596 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py
```

### test_provider_integrity

Start `2026-09-15T19:23:57.563436+00:00`; end `2026-09-15T19:24:06.778170+00:00`; elapsed `9.215 s`; exit `0`.

```bash
python3 tests/mod_editor/test_provider_integrity.py
```

### test_product_catalog

Start `2026-09-15T19:24:06.810343+00:00`; end `2026-09-15T19:24:06.960233+00:00`; elapsed `0.15 s`; exit `0`.

```bash
python3 tests/mod_editor/test_product_catalog.py
```

### test_phase1_packaging

Start `2026-09-15T19:24:06.993096+00:00`; end `2026-09-15T19:24:09.242169+00:00`; elapsed `2.249 s`; exit `0`.

```bash
python3 tests/mod_editor/test_phase1_packaging.py
```

### test_nfl2k5_modern_color

Start `2026-09-15T19:24:09.274853+00:00`; end `2026-09-15T19:24:16.547213+00:00`; elapsed `7.272 s`; exit `0`.

```bash
python3 tests/mod_editor/test_nfl2k5_modern_color.py
```

### registry-strict

Start `2026-09-15T19:24:16.580360+00:00`; end `2026-09-15T19:24:16.729349+00:00`; elapsed `0.149 s`; exit `1`.

```bash
python3 -m mod_editor.capabilities.validate_registry
```

### all-suites

Start `2026-09-15T19:01:44.833651+00:00`; end `2026-09-15T19:24:16.742534+00:00`; elapsed `1351.909 s`; exit `1`.

```bash
python3 .scratch/run_suites.py
```

### progress-20

Start `2026-09-15T19:24:55.082571+00:00`; end `2026-09-15T19:24:55.090744+00:00`; elapsed `0.008 s`; exit `0`.

```bash
bash -c 'tail -22 .scratch/audit/all-suites.log; tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log; tail -8 .scratch/audit/test_nfl2k5_scorebug_fonts.log'
```

### registry-missing-evidence

Start `2026-09-15T19:25:21.372524+00:00`; end `2026-09-15T19:25:21.406636+00:00`; elapsed `0.034 s`; exit `0`.

```bash
bash -c 'rg -n "_local_path" mod_editor/capabilities/validate_registry.py; .scratch/g ls-files docs/research/apf_audio.md; ls -ld docs/research docs/research/apf_audio.md; .scratch/g status --short'
```

### missing-registry-files

Start `2026-09-15T19:25:21.437436+00:00`; end `2026-09-15T19:25:21.740055+00:00`; elapsed `0.303 s`; exit `0`.

```bash
python3 -
```

### evidence-source-locations

Start `2026-09-15T19:25:48.441115+00:00`; end `2026-09-15T19:25:48.466642+00:00`; elapsed `0.026 s`; exit `0`.

```bash
python3 -
```

### hydrate-registry-evidence

Start `2026-09-15T19:26:19.922656+00:00`; end `2026-09-15T19:26:19.989420+00:00`; elapsed `0.067 s`; exit `0`.

```bash
python3 -
```

### registry-strict-rerun

Start `2026-09-15T19:26:20.020247+00:00`; end `2026-09-15T19:26:20.171805+00:00`; elapsed `0.152 s`; exit `0`.

```bash
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 -m mod_editor.capabilities.validate_registry
```

### gates-after-hydration

Start `2026-09-15T19:26:20.201388+00:00`; end `2026-09-15T19:26:20.207737+00:00`; elapsed `0.006 s`; exit `0`.

```bash
bash -c 'tail -10 .scratch/audit/xbe-memory.log; tail -10 .scratch/audit/xbe-caves.log'
```

### validation-summary

Start `2026-09-15T19:26:47.196949+00:00`; end `2026-09-15T19:26:47.223303+00:00`; elapsed `0.026 s`; exit `0`.

```bash
python3 -
```

### update-registry-report

Start `2026-09-15T19:26:47.253458+00:00`; end `2026-09-15T19:26:47.275829+00:00`; elapsed `0.022 s`; exit `0`.

```bash
python3 -
```

### progress-21

Start `2026-09-15T19:27:51.968131+00:00`; end `2026-09-15T19:27:51.990149+00:00`; elapsed `0.022 s`; exit `0`.

```bash
python3 -
```

### repin-handoff

Start `2026-09-15T19:28:36.174442+00:00`; end `2026-09-15T19:28:46.411534+00:00`; elapsed `10.237 s`; exit `0`.

```bash
python3 packaging/repin.py --apply
```

### commit-handoff

Start `2026-09-15T19:28:46.444731+00:00`; end `2026-09-15T19:28:46.528876+00:00`; elapsed `0.084 s`; exit `0`.

```bash
python3 .scratch/commit_handoff.py
```

### xbe-memory

Start `2026-09-15T19:01:44.830809+00:00`; end `2026-09-15T19:29:09.741976+00:00`; elapsed `1644.911 s`; exit `0`.

```bash
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_xbe_patch_memory_writes.py
```

### progress-22

Start `2026-09-15T19:30:06.906252+00:00`; end `2026-09-15T19:30:06.929271+00:00`; elapsed `0.023 s`; exit `0`.

```bash
python3 -
```

### progress-23

Start `2026-09-15T19:31:06.045158+00:00`; end `2026-09-15T19:31:06.074623+00:00`; elapsed `0.029 s`; exit `0`.

```bash
python3 -
```

### progress-24

Start `2026-09-15T19:32:13.908161+00:00`; end `2026-09-15T19:32:13.930645+00:00`; elapsed `0.022 s`; exit `0`.

```bash
python3 -
```

### xbe-caves

Start `2026-09-15T19:01:44.831693+00:00`; end `2026-09-15T19:32:18.711853+00:00`; elapsed `1833.88 s`; exit `0`.

```bash
env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_xbe_patch_cave_references.py
```

### supervised-detached-checks

Start `2026-09-15T19:01:44.801352+00:00`; end `2026-09-15T19:32:18.717905+00:00`; elapsed `1833.917 s`; exit `1`.

```bash
bash .scratch/launch_checks.sh
```

### progress-25

Start `2026-09-15T19:33:13.717050+00:00`; end `2026-09-15T19:33:13.740232+00:00`; elapsed `0.023 s`; exit `0`.

```bash
python3 -
```

### confirm-required-verdicts

Start `2026-09-15T19:33:31.739088+00:00`; end `2026-09-15T19:33:31.763186+00:00`; elapsed `0.024 s`; exit `0`.

```bash
python3 -
```

### testdisc-build

Start `2026-09-15T19:33:31.790924+00:00`; end `2026-09-15T19:33:32.068813+00:00`; elapsed `0.278 s`; exit `1`.

```bash
bash reports/b71_a5/launch_testdisc71.sh
```

### testdisc-log-and-output-state

Start `2026-09-15T19:33:48.702143+00:00`; end `2026-09-15T19:33:48.728633+00:00`; elapsed `0.026 s`; exit `0`.

```bash
python3 -
```

### finish-report-content

Start `2026-09-15T19:34:30.748879+00:00`; end `2026-09-15T19:34:30.772976+00:00`; elapsed `0.024 s`; exit `0`.

```bash
python3 -
```

### repin-final

Start `2026-09-15T19:34:30.801340+00:00`; end `2026-09-15T19:34:40.945286+00:00`; elapsed `10.144 s`; exit `0`.

```bash
python3 packaging/repin.py --apply
```

## Delivery

- Branch: `astra/b71-a5-scorebug-integrate` in `.scratch/private.git`.
- Bundle: `.scratch/astra-b71-a5.bundle`, including both merged source lines and colour v2.1, with prerequisite `e2f5c6e6` (the beta 71 base). Bundle verification and head identity are recorded in the final live audit entries.
- Source inputs remain read-only; no retail binary was copied into the repository. `.scratch` stays below 200 MB.
- `ASTRA_LAST_MESSAGE.md` states the code result and disc blocker, and ends with `ASTRA_DONE`.

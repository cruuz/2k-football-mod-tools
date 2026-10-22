# On-demand modules: making the game "as big as we want"

## The short version (for Noah)

Until now, every new feature we added lived in the game's executable (`default.xbe`) and was loaded into memory the
moment the game booted, whether you ever used it or not. The executable has a fixed amount of "header" bookkeeping
room and the console has 64 MB (128 MB in xemu with K128), so that approach always runs into a wall eventually.

There are two answers, and this update ships the first and prototypes the second:

1. **More room right now (shipped, b778 xs1): the "pool".** The executable gets one more section that grows a page
   (4 KB) at a time whenever a feature needs space. Nothing that is already placed ever moves. The old limits on how
   many features the build can track are gone too (96 entries before, 320 now). This round's new features take about
   7 pages (28 KB). The pool can grow to 1,024 pages (4 MB) before its limit, and the real limit is memory, not the
   file.
2. **The long-term answer: features that load only when you open them.** The Xbox already has a built-in way to do
   this. A part of the executable can be marked "don't load at boot", and the game asks the system to read it from the
   disc when it is needed. 2K5 already links the two system calls for it (they are in the retail game, unused for
   our features until now). A feature that is only used on one screen, such as Career Home, the draft screen, the
   Trophy Room or the Player Card honors page, then costs no memory until that screen opens. It stays on the disc
   the rest of the time, and the disc has room for gigabytes.

**The prototype in this update:** Career Home (MyCareer's main screen) is read from the disc the moment you open
MyCareer, instead of at boot. It is OFF by default (`module_loader`) and stays off until every check below has passed
on Noah's own playthrough.

**What you should notice: nothing.** The load happens during the menu change into MyCareer, behind the transition the
game already does. It reads about 12 KB from the disc. If the read ever fails, it tries again (three times); if it
still fails, you simply stay on the Game Modes menu and can press A again. You never get a half-drawn or missing
screen. Practice, Play Now and every mode that is not MyCareer never call it.

## How it works

### The Xbox overlay mechanism (no new file format)

* An XBE section has a *preload* flag. Preloaded sections are read at boot. A section without the flag is mapped only
  when the title calls `XeLoadSection(section header)`; `XeUnloadSection` frees it again. The kernel keeps a
  reference count, commits the pages, reads the bytes from `default.xbe` on the disc and zero-fills the rest.
* The retail 2K5 executable imports both (`XeLoadSection`, kernel ordinal 327, thunk 0x4E3BFC; `XeUnloadSection`,
  328, 0x4E3C00).
* So a **module is an XBE section** of default.xbe: same build path, same digests the Studio already seals, same disc
  file. Its bytes are checked by the Studio when it builds (section SHA-1 digest, the allocator's sealed SHA-256 of
  the owner bytes), and the loader records the kernel's status for every load.

### Fixed load addresses, no relocation

Each module keeps the virtual address it was built for (Career Home: 0x14BC000, its existing section). Nothing is
relocated at run time, so a module's code is byte-for-byte what the Studio assembled and tested. Two modules that
are never needed at the same time could share one address window (classic overlays) and be loaded one after the
other; the prototype has only one.

### Hooks into a module that might not be loaded

The danger is a pointer into a module that is not in memory (a row table, a handler, a jump). The rule:

* **Every pointer into a module is reachable only from screens of that module's mode.** Career Home is named only by
  MyCareer's Apartment descriptor and by its own sub-screens.
* **A resident gate loads the module before any of those screens can open.** The gate sits on the native screen
  stack's two entries, push (0x6E39A, after MyCareer's own dispatch at 0x6E390) and replace (0x6E2E0). When the
  screen about to open is one of the module's mode (for Career Home: a descriptor in MyCareer's RW block, the M3
  page, or Career Home itself) and the module is not loaded, it calls `XeLoadSection`. Pop-to (0x6E450) only returns
  to screens that are already on the stack, so it cannot be the first screen of a mode.
* **Failure is a cancelled transition, never a dangling pointer.** Three tries; then the gate cancels that one screen
  change the same way MyCareer's own filter does (no screen pushed), so the player stays where he was.
* The gate costs a range compare per screen change (menus, not frames). Resident gameplay code never jumps into a
  module.

### What must stay resident

Anything that runs during gameplay frames stays in the pool or the v3 runs: CPU AI (QB reads, ball-carrier AI, coach
clock decisions), physics and rules hooks (force-out, run blocking, QB accuracy), the scorebug, camera, play art,
K128 and the save/load hooks. Loading those mid-play would be noticeable and they are small anyway. Modules are for
screens and modes: Career Home and the MyCareer menus, the draft screen, the Trophy Room, the player progression
screen, the honors page, schedule and owner/staff screens later.

### Loading without stalls

* A module is read during a menu transition the game already performs. Career Home is 12 KB (three 4 KB pages);
  xemu reads that in milliseconds. The gate records the exact time of every load (RDTSC cycles at the 733 MHz CPU)
  so the cost is measured, not guessed (see the report for the numbers).
* A bigger module (say 200 KB of draft-screen art and code) should load behind an existing load screen (entering
  the draft, entering a game) rather than a plain menu change.

### Unloading (not in the prototype)

The prototype never unloads: after the first MyCareer visit Career Home stays in memory, which is what happens today
for the whole session. Unloading (`XeUnloadSection`) is safe only when no screen of the module's mode is on the
screen stack. The next step is a check of the stack (the descriptors at `[stack + n*8]`, count at `+0x100`) when the
main menu is pushed, and unloading only then. That is what makes memory, not just the file, scale.

### Save and load

Modules hold code and fixed tables. Anything that must survive a save stays in the save formats the features already
use (MyCareer's checkpoint journal, the franchise members). Career Home stores nothing. A module never owns save
state, so a save written with a module loaded or not loaded is the same.

### 64 MB and 128 MB

`XeLoadSection` works the same on both. At 64 MB a loaded module takes its pages from the same free memory the game's
heaps use, so the rule there is: load only from menus, and unload before a game starts (the in-game heap is carved
when a game loads). At 128 MB (K128) there is about 63 MB of extra memory; module pages are an easy fit.

### How the Studio builds and checks modules

* The module is an allocator-owned section with a fixed slot (Career Home uses the optional extra section slot; the
  v4 pool keeps descriptor index 6, the extra section is index 7).
* `nfl2k5_module_loader` is a late allocator owner (256 code + 32 data bytes in the pool): the gate, its range table
  and its counters. It clears only the module's preload flag; the section's bytes, address and digest are unchanged.
* Guards: the two hook sites must be retail; the MyCareer and Contracts editor context hashes read the push hook as
  its retail bytes only when it is this owner's exact jump.
* Tests: `tests/mod_editor/test_nfl2k5_module_loader.py` (install, replay, refusals; the gate under Unicorn: loads
  once for a MyCareer screen, never for another screen, three tries and a cancelled screen change on failure,
  registers preserved).

## The limits

| Limit | Value | What it means |
|---|---|---|
| Section descriptors | The header page (4 KB) is full: the v4 pool is index 6, the extra section index 7 | One descriptor per resident module slot. More slots need header room: the live header caves at 0xA10..0xCC4 (catch slider, accel ramp, draft AI, EDGE rename, about 690 bytes = 12 descriptors) can move into the pool in a later round. One descriptor can also serve many modules in turn by rewriting its file offset/size before each load. |
| Disc image | XDVDFS addresses 2 KB sectors with 32-bit numbers; one file is at most 4 GB | default.xbe is 12 MB; the disc is 6 GB today and the Studio already builds larger images. Not a practical limit in xemu. |
| Memory at one time | 64 MB retail kernel (the pregame director heap is already near empty at some stadiums, K128 notes); 128 MB with K128 (a 63 MB extra region) | What one screen can use at once. Modules make features cost memory only while their screen is up. |
| Load time | DVD reads in xemu are fast; a real console seeks about 100 ms | Keep modules for menus and load screens. |
| Pool | 1,024 pages (4 MB virtual); resident cost = pages used | Today: 7 pages with this round's owners. |
| Requests | 320 allocation entries (document page in the pool) | Today: 127 with this round. |

## What is left before the loader ships on

1. Noah's witnessed MyCareer session on a disc built with `module_loader` on (enter, Career Home and every row,
   leave, re-enter, a game and back, save and load) at 128 MB and at 64 MB.
2. Unloading with the stack check, so memory scales and not just the file.
3. Moving the header caves into the pool to free descriptor slots for more modules (draft screen, Trophy Room).

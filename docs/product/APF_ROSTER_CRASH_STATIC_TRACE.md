# APF 2K8 rebuilt-ROST crash: static trace

Date: 2026-07-18  
Scope: the three identical Alpha 14 roster-name crashes  
Executable: retail `default.xex`, image base `0x82000000`  
Result: causal boundary identified; no executable or release artifact changed

## Result

Guest PC `0x84AB1D40` is the first instruction of a small one-based
relative-pointer fixup leaf. It is not an H7A decoder and is not a name
consumer. Its sole static call site is `0x8474C268`, inside the large ROST root
graph relocation routine that begins at `0x8474C088`. The caller is traversing
ROST root table 5: count at root `+0x28`, base pointer at root `+0x2C`, eight
bytes per record.

The crash registers reconstruct the bad address without assumptions:

```text
root                         r31 = 0xA3E7FD60
address of root + 0x2C       r27 = 0xA3E7FD8C
current record index         r28 = 0x01048914
current byte offset          r29 = 0x082448A0 = r28 * 8
rebased table pointer        r11 = 0x67DBB75F
leaf argument                r3  = 0x6FFFFFFF = r11 + r29
outer fixup return marker    r12 = 0x8474F970
```

The correct retail count is 295, not at least 17,074,453. The correct table-5
start is body offset `0x0BBC74`, not `0x67DBB75F`. The failing leaf is therefore
a downstream victim of an already-invalid root graph.

More importantly, the table pointer proves a prior relocation through the
other Xbox 360 physical-memory alias. Reversing the relocation performed by
the current pass gives:

```text
pre_pass_word = 0x67DBB75F - 0xA3E7FD8C + 1 (mod 2^32)
              = 0xC3F3B9D4

0xC3E7FD60 + 0x0BBC74
              = 0xC3F3B9D4
```

`0xC3F3B9D4` is exactly the correct absolute table-5 pointer when the same
physical buffer is viewed through its `0xC...` alias. The current pass then
applies the one-based relative-pointer formula again through the `0xA...`
alias and produces `0x67DBB75F`. This is direct evidence that this buffer was
already relocated before `Function_8474C088` tried to relocate it again. It
does **not** yet distinguish between a second call to the same routine and an
equivalent earlier relocation in the DRAM load/copy path.

## Faulting instruction

The decoded PE bytes at flat offset `0x02AB1D40` are:

```text
84AB1D40  81 63 00 00  lwz   r11,0(r3)       <- fault
84AB1D44  2F 0B 00 00  cmpwi cr6,r11,0
84AB1D48  40 9A 00 0C  bne   cr6,84AB1D54
84AB1D4C  91 63 00 00  stw   r11,0(r3)
84AB1D50  4E 80 00 20  blr
84AB1D54  7D 6B 1A 14  add   r11,r11,r3
84AB1D58  39 6B FF FF  addi  r11,r11,-1
84AB1D5C  91 63 00 00  stw   r11,0(r3)
84AB1D60  4E 80 00 20  blr
```

In C-like form:

```c
void fix_one_based_relative_pointer(uint32_t *field) {
    uint32_t value = *field;
    if (value != 0)
        *field = (uint32_t)field + value - 1;
}
```

The generated static recompilation shows the same leaf at
`build-static-recomp-apf/ppc/ppc_recomp.167.cpp:2126` and the first load at
line 2129.

## Exact caller and object chain

`Function_8474C088` is a large root relocation routine. Ghidra records only its
eight-byte PDATA prologue as a conventional function because it branches to a
shared save-GPR helper, but PDATA value `0x40033703` covers the detached body
through `0x8474CD64`. The static recompiler preserves that complete body in
`build-static-recomp-apf/ppc/ppc_recomp.53.cpp:3752-5599`.

The relevant table-5 sequence is at lines 3989-4037:

```text
8474C228  r27 = r31 + 0x2C
8474C22C  r11 = *(u32 *)r27
8474C240  r11 = r11 + r27
8474C244  r11 = r11 - 1
8474C248  *(u32 *)r27 = r11
8474C24C  r11 = *(u32 *)(r31 + 0x28)       // count
8474C25C  r29 = 0
8474C260  r11 = *(u32 *)r27                // table base
8474C264  r3 = r11 + r29                   // record +0 field
8474C268  bl 0x84AB1D40
8474C270  r28++
8474C274  r29 += 8
8474C278  compare r28 with root[+0x28]
```

The runtime `r12 = 0x8474F970` identifies the active parent: `0x8474F96C`
called `Function_8474C088`, and its link address was `0x8474F970`. This is the
first operation in `Function_8474F950`, the ROST post-load setup routine
(`ppc_recomp.53.cpp:11978-12000`).

The complete static call inventory is:

```text
Function_84AB1D40:
  0x8474C268 in Function_8474C088          (only call site)

Function_8474C088:
  0x846728B4 in Function_84672800
  0x84739E58 in Function_84739DC0
  0x8474F96C in Function_8474F950          (active crash path)

Function_8474F950:
  0x84739E50 in Function_84739DC0
  0x8473A704 in Function_8473A670
  0x8474FD78 in Function_8474FCE8
  0x84750F84 in Function_84750EF8          (DRAM/ROST load callback)
  0x84750FF4 in Function_84750FA0
  0x84751068 in Function_84751010
  0x847510EC in Function_847510B0
```

The outermost dynamic caller of `Function_8474F950` is not retained in the
crash dump because its LR was already saved on the stack. During this crash,
the saved address is at guest stack address `r1 + 0xE8` (`0x703EFC28`). Reading
that word in the next instrumented run will identify the exact outer call site.
The startup timing and known callback make `0x84750F84` the leading candidate,
but it is not asserted as proven until that saved word is captured.

## Meaning of host address `0x0000000270000000`

The guest register is `r3 = 0x6FFFFFFF`, not `0x70000000` and not a 64-bit
guest pointer. `lwz` needs four bytes, so the access begins at the final byte
before `0x70000000` and crosses into that uncommitted guest page.

Xenia Canary commit `6e5b8324f` tries host mapping bases at powers of two and
adds the 32-bit guest virtual address to the chosen base. In this run the base
is `0x200000000`; therefore the four-byte guest access spans host
`0x26FFFFFFF..0x270000002`. The first inaccessible host byte is exactly the
reported `0x270000000`. See the matching emulator source at
<https://github.com/xenia-canary/xenia-canary/blob/6e5b8324f/src/xenia/memory.cc#L204-L240>.

That same source maps both `0xA...` and `0xC...` as aliases of the physical
heap, which is why the `A3E7FD60` / `C3E7FD60` relationship above is meaningful
rather than coincidental.

## Concrete next runtime instrumentation

Use one modified and one untouched control build. Log only these bounded
points; no per-instruction trace is needed:

1. At `0x8474F950`, increment a call ordinal for each `r3` root and record
   `r3`, `r4`, LR, the saved outer LR, and the 80 root words `+0x00..+0x13F`.
2. At `0x8474C228`, before table-5 rebasing, record `r31`,
   `be32[r31+0x28]`, and `be32[r31+0x2C]`. If the pointer is already
   `C3F3B9D4` rather than raw `000BBC49`, the prior relocation is caught before
   this pass damages it.
3. At `0x8474C260`, trigger only when `r28 == 0`; record the same two root
   words plus `r27/r28/r29`. Expected control values are count `0x00000127`
   and an absolute table pointer equal to `root + 0x0BBC74` in one consistent
   alias.
4. Add a guard at `0x8474C264`: before the call, stop if `r3` is outside
   `[table_base, table_base + count * 8)` or outside the 2,294,304-byte ROST
   allocation. This converts the late access violation into an immediate,
   fully logged invariant failure.

The single best breakpoint is `0x8474C228`. It distinguishes “raw body arrived
correctly” from “body arrived already relocated” before the current relocation
mutates table 5, while `0x8474F950` call ordinals and the saved LR identify who
performed or requested the duplicate pass.

## Evidence references

- Crash/register dump: retained only in the private isolated runtime workspace;
  it is deliberately not part of the public package.
- Identical team-only and player-only dumps: retained under the same private
  evidence policy and omitted from the release.
- Leaf implementation:
  `build-static-recomp-apf/ppc/ppc_recomp.167.cpp:2126-2147`
- Root relocation and table-5 loop:
  `build-static-recomp-apf/ppc/ppc_recomp.53.cpp:3752-4037`
- Post-load call into root relocation:
  `build-static-recomp-apf/ppc/ppc_recomp.53.cpp:11978-12000`
- DRAM/ROST callback and post-load call:
  `build-static-recomp-apf/ppc/ppc_recomp.53.cpp:14974-15055`
- Proved ROST pointer rule and root table 5:
  `docs/research/apf_roster.md:106-130`, `docs/research/apf_roster.md:133-166`
- Static call metadata:
  `research/functions/apf2k8/ledger/apf2k8_functions_04608_05119.jsonl:204,224,231`

## Classification

Completed static experiment, positive result: the exact faulting leaf,
instruction, table, iteration arithmetic, active parent, alias relationship,
and earliest useful instrumentation point are identified. The remaining
question is narrowly runtime-specific: which loader/copy call first changes
raw table-5 word `0x000BBC49` into absolute `0xC3F3B9D4`, or which caller asks
for `Function_8474F950` twice on the same physical root.

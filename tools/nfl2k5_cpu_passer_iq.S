/* CPU quarterbacks throw on time and check down: the checkdown factor. EXPERIMENTAL / UNWITNESSED. GNU as --32.
 *
 * One hook in the CPU passer's field terms 0x199CE0, which every target point of the CPU QB's read grid passes
 * through (0x19B1F0 -> 0x19A7E0 -> 0x199CE0):
 *   short (0x199F23, call 0x1B0AE0 for the short-throw curve 0x50C494): the native term (-0.5 at 4 yd from the QB
 *         rising to 0 at 15 yd) is multiplied by a factor that is 1 until the fade start, then falls by k_rate a
 *         second to k_floor, and is k_floor at once while the pocket pressure 0xBE47C0 is k_pressure or more.
 *         The fade starts k_start seconds after the snap, or sooner, when the QB's first read cycle completed
 *         (the read advance 0x199100 raises 0xBE47FC when the read wraps back to the first row).
 * Targets 15 yd or more from the QB score exactly as retail (the native term is 0). A human passer, or anything
 * that is not a CPU passer (the QB's controller word is not -1), keeps the native term.
 *
 * In: ECX = curve points (0x50C498), EDX = point count, [ESP+4] = QB-to-target distance; EBP = the QB (the field
 * terms' first argument, live across the hooked call). Out: ST0 = term x factor, the argument popped (ret 4) as the
 * native interpolator does. EAX/ECX/EDX are clobbered, as the interpolator clobbers them; EBX/ESI/EDI/EBP and the
 * x87 depth are preserved (the native routine adds ST0 to its other terms right after the call).
 * State (16 RW bytes): the last play clock seen (a clock that goes back starts a new play), whether the first
 * read cycle completed this play and the clock when it did.
 */
.intel_syntax noprefix
.code32
.text
.global short, factor, code_end
.global k_pressure, k_start, k_rate, k_floor, k_one
.extern state, lerp

.set LAST, 0x00          /* f32 play clock at the previous scoring call */
.set SEEN, 0x04          /* u32 1 once the first read cycle completed this play */
.set CYCLE, 0x08         /* f32 play clock when it completed */

.set CLOCK_PTR, 0xe6029c /* [ptr]+0x10 = seconds since the snap */
.set PRESSURE, 0xbe47c0  /* smoothed pocket pressure (0x198860 at the end of each QB tick) */
.set CYCLED, 0xbe47fc    /* 1 while the read is back on the first row after a full cycle */

short:
    push dword ptr [esp+4]
    call lerp                                /* ST0 = native short-throw term; pops the copy */
    call factor                              /* ST0 = factor, ST1 = term */
    fmulp st(1), st
    ret 4

/* ---- factor: ST0 = checkdown factor in [k_floor, 1] (EBP = QB; clobbers EAX, ECX, EDX) ---- */
factor:
    mov eax, [ebp+0xc]
    test eax, eax
    jz f_one
    cmp dword ptr [eax], -1                  /* CPU passer only */
    je f_cpu
f_one:
    fld1
    ret
f_cpu:
    mov eax, [CLOCK_PTR]
    mov ecx, [eax+0x10]
    fld dword ptr [eax+0x10]                 /* ST0 = t */
    fcom dword ptr [state+LAST]
    fnstsw ax
    test ah, 1                               /* t < last: a new play */
    jz f_same
    mov dword ptr [state+SEEN], 0
f_same:
    mov [state+LAST], ecx
    cmp dword ptr [CYCLED], 0
    je f_known
    cmp dword ptr [state+SEEN], 0
    jne f_known
    mov dword ptr [state+SEEN], 1
    mov [state+CYCLE], ecx
f_known:
    fld dword ptr [PRESSURE]
    fcomp dword ptr [k_pressure]
    fnstsw ax
    test ah, 1                               /* pressure < k_pressure keeps the time rule */
    jz f_floor
    mov ecx, [k_start]
    cmp dword ptr [state+SEEN], 0
    je f_start
    fld dword ptr [state+CYCLE]
    fcomp dword ptr [k_start]
    fnstsw ax
    test ah, 1                               /* the first cycle completed before k_start */
    jz f_start
    mov ecx, [state+CYCLE]
f_start:
    push ecx
    fsub dword ptr [esp]                     /* t - start */
    pop ecx
    fmul dword ptr [k_rate]
    fsubr dword ptr [k_one]                  /* 1 - k_rate (t - start) */
    fcom dword ptr [k_one]
    fnstsw ax
    test ah, 0x41                            /* at most 1 */
    jz f_one_pop
    fcom dword ptr [k_floor]
    fnstsw ax
    test ah, 1                               /* at least k_floor */
    jz f_done
f_floor:
    fstp st(0)
    fld dword ptr [k_floor]
f_done:
    ret
f_one_pop:
    fstp st(0)
    fld1
    ret

.balign 4
k_pressure: .float 0.7
k_start:    .float 2.0
k_rate:     .float 0.8
k_floor:    .float 0.2
k_one:      .float 1.0
code_end:

/* CPU QB re-checks his read before throwing. EXPERIMENTAL / UNWITNESSED. GNU as --32.
 *
 * Three hooks in the CPU passing AI, all on native call/branch sites:
 *   stamp (0x19B7D3, call 0x19A7E0 in the target-grid updater): record when each of the
 *         20 grid points (5 receiver rows x 4 route points) was last scored, then score it natively.
 *   pick  (0x19BD8C, call 0x1985E0 in the QB tick): while the QB is not pressured, keep his
 *         read on the receiver he committed to and hide scores older than his read window from
 *         the native picker (they are restored right after it returns).
 *   hold  (0x19BC72, jne taken when committed and the release timer is 0.5 s or less):
 *         keep the read on the committed receiver; once every point of that receiver has been
 *         re-scored after the commit and none clears the pass threshold minus 0.05, drop the
 *         target (at most twice per play) and re-pick this frame. Otherwise continue natively.
 * Under pocket pressure above 0.7, the panic flag, or a non-CPU passer, every hook keeps the
 * retail path (the stamp is bookkeeping only). EDI is the QB player at pick/hold (0x19BB66).
 * All GPRs and EFLAGS are preserved except the picker's EAX result; x87 stays balanced.
 */
.intel_syntax noprefix
.code32
.text
.global stamp, pick, hold, code_end
.extern state, point_score, picker, rating, lerp, pick_path, release_path

.set LAST, 0x00          /* f32 last clock seen */
.set ABORTS, 0x04        /* u32 aborts this play */
.set THR, 0x08           /* f32 last pass threshold given to the picker */
.set COMMITTED, 0x0C     /* u32 receiver the QB committed to */
.set COMMIT_CLOCK, 0x10  /* f32 clock when he committed */
.set AGE, 0x14           /* f32 read window for this frame */
.set VALID, 0x18         /* u32 bit row*4+point: stamped this play */
.set SAVED, 0x1C         /* u32 bit row*4+point: openness hidden for the picker */
.set STAMPS, 0x20        /* f32[20] last scoring clock */
.set KEEP, 0x70          /* f32[20] hidden openness values */

.set CLOCK_PTR, 0xe6029c
.set READ_INDEX, 0xbe4810
.set ROW_COUNT, 0xbe480c
.set NEXT_SWITCH, 0xbe47c8
.set PRESSURE, 0xbe47c0
.set PANIC, 0xbe47f8
.set ROWS, 0xbe4820

/* ---- stamp: EAX row, EDX point, ECX QB, [ESP+4] native argument ---- */
stamp:
    pushad
    call new_play
    mov eax, [esp+28]
    mov edx, [esp+20]
    cmp eax, 5
    jae stamp_done
    cmp edx, 4
    jae stamp_done
    lea eax, [eax*4+edx]
    mov ecx, [CLOCK_PTR]
    mov ecx, [ecx+0x10]
    mov [state+STAMPS+eax*4], ecx
    bts dword ptr [state+VALID], eax
stamp_done:
    popad
    jmp point_score

/* ---- pick: stdcall picker(a1, a2, threshold, a4); EAX result ---- */
pick:
    pushad
    call new_play
    call commit_track
    mov eax, [esp+44]
    mov [state+THR], eax
    call gate
    test eax, eax
    jz pick_retail
    call lock_on
    call read_window
    fstp dword ptr [state+AGE]
    call hide_stale
    push dword ptr [esp+48]
    push dword ptr [esp+48]
    push dword ptr [esp+48]
    push dword ptr [esp+48]
    call picker
    mov [esp+28], eax
    call unhide
    popad
    ret 16
pick_retail:
    popad
    jmp picker

/* ---- hold: reached by the native jne at 0x19BC72 (flags as native) ---- */
hold:
    pushfd
    pushad
    call new_play
    call commit_track
    call gate
    test eax, eax
    jz hold_native
    call lock_on
    call should_abort
    test eax, eax
    jz hold_native
    mov eax, [edi+0x20]
    mov eax, [eax+0x310]
    mov dword ptr [eax+0x40], 0
    mov dword ptr [eax+0x60], 0x3d4ccccd     /* 0.05 s: no release on this frame */
    mov dword ptr [esp+36+0x18], 0           /* the tick's committed-target local */
    inc dword ptr [state+ABORTS]
    mov dword ptr [state+COMMITTED], 0
    popad
    popfd
    jmp pick_path
hold_native:
    popad
    popfd
    jmp release_path

/* ---- new_play: a clock that went back or jumped 2 s starts a new play (clobbers EAX) ---- */
new_play:
    mov eax, [CLOCK_PTR]
    fld dword ptr [eax+0x10]
    fld st(0)
    fsub dword ptr [state+LAST]
    fldz
    fcomp st(1)
    fnstsw ax
    test ah, 0x41
    jz np_reset_pop
    fcomp dword ptr [k_gap]
    fnstsw ax
    test ah, 1
    jnz np_keep
    jmp np_reset
np_reset_pop:
    fstp st(0)
np_reset:
    xor eax, eax
    mov [state+ABORTS], eax
    mov [state+VALID], eax
    mov [state+COMMITTED], eax
np_keep:
    fstp dword ptr [state+LAST]
    ret

/* ---- commit_track: note the clock whenever the committed receiver changes (EDI QB) ---- */
commit_track:
    mov eax, [edi+0x20]
    mov eax, [eax+0x310]
    mov eax, [eax+0x40]
    cmp eax, [state+COMMITTED]
    je ct_done
    mov [state+COMMITTED], eax
    mov eax, [CLOCK_PTR]
    mov eax, [eax+0x10]
    mov [state+COMMIT_CLOCK], eax
ct_done:
    ret

/* ---- gate: EAX=1 for a CPU passer with no panic and pressure at most 0.7 ---- */
gate:
    cmp dword ptr [PANIC], 0
    jne gate_no
    mov eax, [edi+0xc]
    test eax, eax
    jz gate_no
    cmp dword ptr [eax], -1
    jne gate_no
    fld dword ptr [PRESSURE]
    fcomp dword ptr [0x4efe08]               /* 0.7 */
    fnstsw ax
    test ah, 0x41
    jz gate_no
    mov eax, 1
    ret
gate_no:
    xor eax, eax
    ret

/* ---- find_row: ECX receiver -> EAX row index or -1, EDX row address ---- */
find_row:
    push esi
    mov esi, [ROW_COUNT]
    cmp esi, 5
    jbe fr_count
    mov esi, 5
fr_count:
    xor eax, eax
    mov edx, ROWS
fr_loop:
    cmp eax, esi
    jge fr_none
    cmp [edx], ecx
    je fr_found
    add edx, 0xa0
    inc eax
    jmp fr_loop
fr_none:
    or eax, -1
fr_found:
    pop esi
    ret

/* ---- lock_on: keep the native read on the committed receiver while his timer runs ---- */
lock_on:
    mov eax, [edi+0x20]
    mov eax, [eax+0x310]
    mov ecx, [eax+0x40]
    test ecx, ecx
    jz lock_done
    fld dword ptr [eax+0x60]
    fcomp dword ptr [0x4e4180]               /* 0 */
    fnstsw ax
    test ah, 0x45
    jnz lock_done                            /* timer <= 0 or unordered */
    call find_row
    test eax, eax
    js lock_done
    cmp eax, [READ_INDEX]
    je lock_hold
    mov [READ_INDEX], eax
    mov dword ptr [edx+4], 0                 /* restart his point cursor, as 0x199100 does */
lock_hold:
    mov eax, [CLOCK_PTR]
    fld dword ptr [eax+0x10]
    fadd dword ptr [0x4e6d5c]                /* + 0.1 s */
    fld dword ptr [NEXT_SWITCH]
    fcomp st(1)
    fnstsw ax
    test ah, 1
    jz lock_pop
    fst dword ptr [NEXT_SWITCH]
lock_pop:
    fstp st(0)
lock_done:
    ret

/* ---- read_window: ST0 = clamp(1.5 * native read dwell, 0.6, 1.5) s (EDI QB) ---- */
read_window:
    mov ecx, [edi+0x3c]
    push 8
    mov edx, 0xd                             /* Pass Read Coverage */
    call rating
    push eax
    fstp dword ptr [esp]
    mov edx, [0x50c548]
    mov ecx, 0x50c54c
    call lerp
    fmul dword ptr [k_window]
    fld dword ptr [k_window_min]
    fcomp st(1)
    fnstsw ax
    test ah, 1
    jnz rw_high
    fstp st(0)
    fld dword ptr [k_window_min]
    ret
rw_high:
    fld dword ptr [k_window_max]
    fcomp st(1)
    fnstsw ax
    test ah, 0x41
    jz rw_done
    fstp st(0)
    fld dword ptr [k_window_max]
rw_done:
    ret

/* ---- hide_stale: points not scored within the read window read -inf for the picker ---- */
hide_stale:
    push ebx
    push esi
    mov dword ptr [state+SAVED], 0
    mov eax, [CLOCK_PTR]
    fld dword ptr [eax+0x10]
    mov esi, [ROW_COUNT]
    cmp esi, 5
    jbe hs_count
    mov esi, 5
hs_count:
    shl esi, 2
    xor ebx, ebx
hs_loop:
    cmp ebx, esi
    jge hs_end
    bt dword ptr [state+VALID], ebx
    jnc hs_hide
    fld st(0)
    fsub dword ptr [state+STAMPS+ebx*4]
    fcomp dword ptr [state+AGE]
    fnstsw ax
    test ah, 0x41
    jnz hs_next
hs_hide:
    mov eax, ebx
    shr eax, 2
    imul eax, eax, 0xa0
    mov ecx, ebx
    and ecx, 3
    shl ecx, 5
    lea ecx, [eax+ecx+ROWS+0x34]
    mov eax, [ecx]
    mov [state+KEEP+ebx*4], eax
    mov dword ptr [ecx], 0xff800000
    bts dword ptr [state+SAVED], ebx
hs_next:
    inc ebx
    jmp hs_loop
hs_end:
    fstp st(0)
    pop esi
    pop ebx
    ret

/* ---- unhide: restore every hidden openness value ---- */
unhide:
    push ebx
    xor ebx, ebx
uh_loop:
    bt dword ptr [state+SAVED], ebx
    jnc uh_next
    mov eax, ebx
    shr eax, 2
    imul eax, eax, 0xa0
    mov ecx, ebx
    and ecx, 3
    shl ecx, 5
    lea ecx, [eax+ecx+ROWS+0x34]
    mov eax, [state+KEEP+ebx*4]
    mov [ecx], eax
uh_next:
    inc ebx
    cmp ebx, 20
    jb uh_loop
    mov dword ptr [state+SAVED], 0
    pop ebx
    ret

/* ---- should_abort: EAX=1 when all of the committed receiver's stamped points were re-scored
 *      after the commit and the best is below the pass threshold minus 0.05 ---- */
should_abort:
    push ebx
    push esi
    cmp dword ptr [state+ABORTS], 2
    jae sa_no
    mov eax, [edi+0x20]
    mov eax, [eax+0x310]
    mov ecx, [eax+0x40]
    test ecx, ecx
    jz sa_no
    call find_row
    test eax, eax
    js sa_no
    lea ebx, [eax*4]
    lea esi, [ebx+4]
    fld dword ptr [k_lowest]                 /* best */
    xor edx, edx                             /* stamped points */
sa_loop:
    cmp ebx, esi
    jge sa_judge
    bt dword ptr [state+VALID], ebx
    jnc sa_next
    inc edx
    fld dword ptr [state+STAMPS+ebx*4]
    fcomp dword ptr [state+COMMIT_CLOCK]
    fnstsw ax
    test ah, 0x45
    jnz sa_pop_no                            /* not re-scored since the commit */
    mov eax, ebx
    shr eax, 2
    imul eax, eax, 0xa0
    mov ecx, ebx
    and ecx, 3
    shl ecx, 5
    lea ecx, [eax+ecx+ROWS+0x34]
    fld dword ptr [ecx]
    fcomp st(1)
    fnstsw ax
    test ah, 0x45
    jnz sa_next                              /* not above the best so far */
    fstp st(0)
    fld dword ptr [ecx]
sa_next:
    inc ebx
    jmp sa_loop
sa_judge:
    test edx, edx
    jz sa_pop_no
    fld dword ptr [state+THR]
    fsub dword ptr [k_margin]
    fcomp st(1)                              /* threshold - 0.05 vs best */
    fnstsw ax
    fstp st(0)
    test ah, 0x45
    jnz sa_no                                /* best is not below it */
    mov eax, 1
    pop esi
    pop ebx
    ret
sa_pop_no:
    fstp st(0)
sa_no:
    xor eax, eax
    pop esi
    pop ebx
    ret

.balign 4
k_gap:        .float 2.0
k_window:     .float 1.5
k_window_min: .float 0.6
k_window_max: .float 1.5
k_margin:     .float 0.05
k_lowest:     .float -1.0e30
code_end:

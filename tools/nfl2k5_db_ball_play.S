/* Defenders break on the thrown ball. EXPERIMENTAL / UNWITNESSED. GNU as --32.
 *
 * Behavior 37 (0x2E95F0) starts a defender's reaction to a released pass: the man defender on
 * the intended receiver always, a zone defender by the native 1 - Coverage lottery. Retail
 * stores a fixed run-to point (task +0x20): the receiver's position plus 0.25 s of his velocity
 * for the man defender, the same around the offense's QB (0x1AB800 = [0xBE4F8C]) for a zone
 * defender, with the defender's depth held; the reaction task 0x2E7240 then runs there at 0.84.
 *
 * point (call at 0x2E978C, replacing the two-instruction store): performs the retail store, then,
 *   when the release stored a valid catch point (0xBF0E08 == 1) for an intended receiver
 *   ([0xE3C000] != 0), the point is downfield of the line of scrimmage and within 25 yd of this
 *   defender, replaces x and z with the catch point (0xBF0DF0 / 0xBF0DF8).
 * throttle (call at 0x2E7462, replacing "push 0.84"): leaves 1.0 on the stack instead of 0.84
 *   only while this task's run-to point is exactly that valid catch point (EDI = task there).
 * GPRs, EFLAGS and x87 balance are preserved; XMM0 keeps the retail value at the point hook.
 */
.intel_syntax noprefix
.code32
.text
.global point, throttle, code_end
.extern depth

point:
    movaps xmm0, xmmword ptr [esp+0x24]
    movaps xmmword ptr [esi+0x20], xmm0
    pushfd
    pushad
    cmp dword ptr [0xbf0e08], 1
    jne point_done
    cmp dword ptr [0xe3c000], 0
    je point_done
    push dword ptr [0xbf0df8]
    call depth                               /* ST0 = (z - line of scrimmage) * offense direction */
    fcomp dword ptr [0x4e4180]               /* 0 */
    fnstsw ax
    test ah, 0x45
    jnz point_done                           /* behind or on the line, or unordered */
    mov eax, [edi+0x18]
    fld dword ptr [0xbf0df0]
    fsub dword ptr [eax+0x30]
    fmul st(0), st(0)
    fld dword ptr [0xbf0df8]
    fsub dword ptr [eax+0x38]
    fmul st(0), st(0)
    faddp st(1), st(0)
    fcomp dword ptr [k_reach2]
    fnstsw ax
    and ah, 0x45
    cmp ah, 1
    jne point_done                           /* farther than 25 yd, or unordered */
    mov eax, [0xbf0df0]
    mov [esi+0x20], eax
    mov eax, [0xbf0df8]
    mov [esi+0x28], eax
point_done:
    popad
    popfd
    ret

/* Entered by "call throttle" where the native code pushed 0.84; returns with one dword more on the stack. */
throttle:
    lea esp, [esp-4]                         /* no flag change before they are saved */
    push eax
    pushfd                                   /* [esp] flags, [esp+4] eax, [esp+8] free, [esp+12] return */
    mov eax, [esp+12]
    mov [esp+8], eax                         /* return address one slot lower */
    mov eax, 0x3f570a3d                      /* 0.84, retail */
    cmp dword ptr [0xbf0e08], 1
    jne throttle_store
    push edx
    mov edx, [edi+0x20]
    cmp edx, [0xbf0df0]
    jne throttle_pop
    mov edx, [edi+0x28]
    cmp edx, [0xbf0df8]
    jne throttle_pop
    mov eax, 0x3f800000                      /* 1.0 */
throttle_pop:
    pop edx
throttle_store:
    mov [esp+12], eax                        /* the value the native push left */
    popfd
    pop eax
    ret

.balign 4
k_reach2: .float 5225796.0                  /* (25 yd = 2286 cm) squared */
code_end:

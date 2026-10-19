/* Defenders break on the thrown ball. EXPERIMENTAL / UNWITNESSED. GNU as --32.
 *
 * Behavior 37 (0x2E95F0) starts a defender's reaction to a released pass. Retail stores
 * the receiver's position plus 0.25 s of his velocity as the defender's run-to point
 * (task +0x20). This hook replaces the two-instruction store at 0x2E978C with a call:
 * it performs the retail store, then, when the release stored a valid catch point
 * (0xBF0E08 == 1) and this defender reacts to the intended receiver (task +0x40 ==
 * [0xE3C000]), the catch point is downfield of the line of scrimmage and within 25 yd
 * of him, it replaces the point's x and z with the catch point (0xBF0DF0 / 0xBF0DF8).
 * The run itself is the native reaction task 0x2E7240; its throttle immediate is a
 * separate site. ESI = task, EDI = defender at the hook. GPRs, EFLAGS and x87 balance are
 * preserved; XMM0 keeps the retail value exactly as the displaced instructions leave it.
 */
.intel_syntax noprefix
.code32
.text
.global point, code_end
.extern depth

point:
    movaps xmm0, xmmword ptr [esp+0x24]
    movaps xmmword ptr [esi+0x20], xmm0
    pushfd
    pushad
    cmp dword ptr [0xbf0e08], 1
    jne point_done
    mov eax, [0xe3c000]
    test eax, eax
    jz point_done
    cmp [esi+0x40], eax
    jne point_done
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

.balign 4
k_reach2: .float 5225796.0                  /* (25 yd = 2286 cm) squared */
code_end:

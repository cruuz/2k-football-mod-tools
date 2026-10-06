/* PROVED OFFLINE: bounded moment lookup and live overtime helpers. */
.intel_syntax noprefix
.code32
.text
.global profile, ot_check, ot_clock, ot_expiry
.extern profiles, state, native_ot_check

/* No cached profile: leaving mode 8 or an invalid ordinal immediately disables it. */
profile:
    xor eax, eax
    cmp dword ptr [0xe5ff80], 8
    jne profile_done
    mov eax, [0xbf1858]
    cmp eax, 51
    jae profile_none
    shl eax, 5
    add eax, offset profiles
    ret
profile_none:
    xor eax, eax
profile_done:
    ret

/* EAX = profile, returns EAX = game over. Native pending-possession tracking stays live. */
ot_check:
    cmp dword ptr [0xe602c4], 5
    jl not_over
    movzx ecx, byte ptr [eax+23]
    cmp ecx, 1
    je sudden_death
    cmp ecx, 2
    jne both
    mov edx, [0xe5fc28]
    mov edx, [edx]
    mov ecx, [0xe5fc68]
    sub edx, [ecx]
    jns magnitude
    neg edx
magnitude:
    cmp edx, 6
    jae over
both:
    call native_ot_check
    sete al
    movzx eax, al
    ret
sudden_death:
    mov ecx, [0xe5fc28]
    mov edx, [0xe5fc68]
    mov ecx, [ecx]
    cmp ecx, [edx]
    jne over
not_over:
    xor eax, eax
    ret
over:
    mov eax, 1
    ret

/* Absolute era minutes, independent of Quarter Length. Preserve flags across later OT periods. */
ot_clock:
    mov eax, [eax+16]
    mov [0xe602b0], eax
    mov ecx, [0xe6028c]
    test ecx, ecx
    jz clock_no_object
    mov [ecx+16], eax
clock_no_object:
    cmp dword ptr [state], 0
    jne clock_done
    mov dword ptr [state], 1
    mov byte ptr [0xe602a8], 0
    mov ecx, [0xe60284]
    test ecx, ecx
    jz clock_done
    mov al, 4
    cmp ecx, 0xe5fc20
    je clock_pending
    add al, al
clock_pending:
    or byte ptr [0xe602a8], al
clock_done:
    ret

/* EAX profile, returns 1 to continue a tied/postseason first possession at period expiry. */
ot_expiry:
    mov ecx, [0xe5fc28]
    mov edx, [0xe5fc68]
    mov ecx, [ecx]
    cmp ecx, [edx]
    je over
    test byte ptr [eax+22], 4
    jz not_over
    cmp byte ptr [eax+23], 2
    jb not_over
    mov ecx, [0xe60280]
    test ecx, ecx
    jz not_over
    mov edx, [ecx+8]
    mov edx, [edx]
    mov ecx, [ecx]
    mov ecx, [ecx+8]
    cmp edx, [ecx]
    jl over
    jmp not_over

/* Completed fair catch, not a signal or a muff. EDX is the receiving player.
 * Only 2023 free kicks caught in the field behind the receiving 25 qualify.
 * The native B6340 spot writer consumes the pending longitudinal coordinate. */
.global fair_catch
fair_catch:
    mov dword ptr [state+8], 0
    test byte ptr [eax+22], 32
    jz fair_done
    cmp dword ptr [0xe602b4], 2
    jne fair_done
    test edx, edx
    jz fair_done
    mov ecx, [edx+0x38]
    mov ecx, [ecx+8]
    mov ecx, [ecx+12]
    mov edx, [edx+0x18]
    fld dword ptr [edx+0x38]
    fmul dword ptr [ecx+4]
    fcomp dword ptr fair_25
    fnstsw ax
    test ah, 0x05
    jp fair_done
    fld dword ptr [edx+0x38]
    fmul dword ptr [ecx+4]
    fcomp dword ptr fair_goal
    fnstsw ax
    test ah, 0x41
    jnz fair_done
    fld dword ptr [ecx+4]
    fmul dword ptr fair_25
    fstp dword ptr [state+4]
    mov dword ptr [state+8], 1
fair_done:
    ret
fair_25: .float -2286.0
fair_goal: .float -4572.0

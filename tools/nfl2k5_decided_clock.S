/* Separate owner: native dead-ball return and huddle's play-clock helper.
 * Does not modify Accelerated clock's hooks, latch, options or exclusions.
 */
.intel_syntax noprefix
.code32
.text
.global huddle, dead_ball
.extern options, huddle_tail, native_lineup
huddle:
    call decide
    mov eax, [0xe602b4]
    jmp huddle_tail
dead_ball:
    call decide
    jmp native_lineup
decide:
    pushfd
    pushad
    cmp dword ptr [0xa83a18], 3
    jne done
    /* b780 modes2 (revision 2, Q26): never in game mode 8, the ESPN 25th Anniversary moments and the Situation mode
     * (mode 8 with flag 0xE6014C). The era rules excluded only a moment with a profile (0x14DDCB0 returns 0 for the
     * Situation flag and for moments past its 51 profiles), so a Situation scenario set in Q4 with 60 s or less and a
     * 17+ point lead ended at its first dead ball. A scenario plays to its own end. */
    cmp dword ptr [0xe5ff80], 8
    je done
    cmp dword ptr [0xe602c4], 4
    jne done
    cmp dword ptr [0xe602b4], 4
    jne done
    mov eax, [0xe602b8]
    cmp eax, 18
    je dead
    cmp eax, 12
    jne done
dead:
    mov esi, [0xe60280]
    cmp esi, 0xe5fc20
    je home
    cmp esi, 0xe5fc60
    jne done
    mov edi, 0xe5fc20
    jmp teams
home:
    mov edi, 0xe5fc60
teams:
    cmp [0xe60284], edi
    jne done
    mov esi, [esi+8]
    mov edi, [edi+8]
    test esi, esi
    jz done
    test edi, edi
    jz done
    mov eax, [esi]
    mov edx, [edi]
    cmp eax, 255
    ja done
    cmp edx, 255
    ja done
    sub eax, edx
    cmp eax, [options]
    jl done
    mov esi, [0xe6028c]
    test esi, esi
    jz done
    test byte ptr [esi+24], 12   /* paused or count-up clock */
    jnz done
    mov eax, [esi+16]
    test eax, eax
    jz done
    cmp eax, [options+4]        /* positive finite IEEE float, unsigned order */
    ja done                    /* also rejects negative, NaN, infinity */
    mov dword ptr [esi+16], 0  /* native period-end dispatcher owns completion */
done:
    popad
    popfd
    ret

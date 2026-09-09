/* EXPERIMENTAL / UNWITNESSED. Native plans, native temporary bonuses.
 * No new save fields, runtime globals or writable allocation. Options are
 * immutable build immediates. CPU and remembered human prep obey E6011C.
 */
.intel_syntax noprefix
.code32
.text
.global db_group, team_gate, team_seed, before_sim, before_play, remember_clear
.extern cpu_option, remember_option
.extern native_human, native_team, native_team_index, native_apply, native_clear
.extern native_sim_value, play_continue, db_continue

db_group:
    xor ecx, ecx
    sub eax, 4
    cmp eax, 2
    setbe cl                  /* CB, FS, SS use the existing DB drill. */
    jmp db_continue

team_gate:
    call native_human
    test eax, eax
    jnz gate_done
    cmp dword ptr [0xe576a0], 2
    jne gate_done
    test ebp, ebp             /* Always allow removal of an applied CPU plan. */
    jz gate_yes
    mov eax, offset cpu_option
    ret
gate_yes:
    mov eax, 1
gate_done:
    ret

team_seed:
    mov ecx, ebp              /* Player routine's actual team, not menu user. */
    jmp native_team_index

before_sim:
    call prepare_current
    jmp native_sim_value
before_play:
    call prepare_current
    mov eax, dword ptr [0xe60184]
    jmp play_continue

/* Preserve all caller state including x87/SSE across native preparation. */
prepare_current:
    pushfd
    pushad
    push ebp
    mov ebp, esp
    sub esp, 528
    and esp, -16
    fxsave [esp]
    cld
    cmp dword ptr [0xe576a0], 2
    jne current_done
    cmp dword ptr [0xe6011c], 1
    jne current_done
    cmp dword ptr [0xe576ac], 32
    jne current_done
    mov eax, dword ptr [0xe576a4]
    sub eax, 7
    cmp eax, 2
    ja current_done
    mov eax, dword ptr [0xe576b4]
    cmp eax, 22
    jae current_done
    mov edx, dword ptr [0xe576bc]
    cmp edx, 17
    jae current_done
    imul eax, eax, 17
    add eax, edx
    lea esi, [eax*8 + 0xe57c40]
    movzx eax, byte ptr [esi]
    and eax, 7
    cmp eax, 3
    jae current_done          /* Complete, unavailable or empty fixture. */
    movzx ecx, byte ptr [esi+1]
    movzx edx, byte ptr [esi+2]
    cmp ecx, 32
    jae current_done
    cmp edx, 32
    jae current_done
    cmp ecx, edx
    je current_done
    call prepare_team
    movzx ecx, byte ptr [esi+2]
    call prepare_team
current_done:
    fxrstor [esp]
    mov esp, ebp
    pop ebp
    popad
    popfd
    ret

prepare_team:
    pushad
    mov ebx, ecx
    cmp dword ptr [ebx*4+0xe51e60], 1
    ja team_done              /* 2 means applied; unknown states also refuse. */
    call native_team
    test eax, eax
    jz team_done
    mov ebp, eax
    movzx eax, byte ptr [ebp+0x11c]
    dec eax
    cmp eax, 64
    ja team_done
    xor edi, edi
check_roster:
    mov eax, dword ptr [ebp+edi*4]
    test eax, eax
    jz team_done
    cmp byte ptr [eax+0x35], 16
    ja team_done
    inc edi
    movzx eax, byte ptr [ebp+0x11c]
    cmp edi, eax
    jb check_roster
    imul esi, ebx, 2000
    add esi, 0xe42460
    cmp dword ptr [ebx*4+0xe5775c], 0
    je cpu_plan
    mov eax, offset remember_option
    test eax, eax
    jz team_done
    jmp check_plan
cpu_plan:
    mov eax, offset cpu_option
    test eax, eax
    jz team_done
    mov edi, esi
    mov ecx, 500
    mov eax, 0x01000000
    rep stosd
    mov edi, esi
    mov eax, 0x8200005d        /* Low full drill, 1st team, 2 h, Monday. */
    mov ecx, 5
cpu_days:
    stosd
    add eax, 3                /* 2nd and 3rd teams: identical intensity. */
    stosd
    add eax, 3
    stosd
    sub eax, 6
    add eax, 0x10000000
    loop cpu_days
    mov eax, 0xd1000067        /* One hour Day Off, Saturday and Sunday. */
    stosd
    add eax, 0x10000000
    stosd
check_plan:
    xor edi, edi
    xor edx, edx
check_row:
    mov eax, dword ptr [esi+edi*4]
    mov ecx, eax
    and ecx, 511
    jz next_row
    cmp ecx, 173
    jae team_done
    shr eax, 24
    mov ecx, eax
    and ecx, 15
    dec ecx
    cmp ecx, 7
    ja team_done
    and eax, 0x70
    cmp eax, 0x70
    je team_done
    inc edx
next_row:
    inc edi
    cmp edi, 500
    jb check_row
    test edx, edx
    jz team_done              /* Never silently apply an empty human plan. */
    imul edx, ebx, 195
    add edx, 0xe51f60
    xor edi, edi
snapshot:
    mov eax, dword ptr [ebp+edi*4]
    mov cl, byte ptr [eax+0x4c]
    mov byte ptr [edx], cl
    mov cl, byte ptr [eax+0x39]
    mov byte ptr [edx+1], cl
    mov cl, byte ptr [eax+0x3b]
    mov byte ptr [edx+2], cl
    add edx, 3
    inc edi
    movzx eax, byte ptr [ebp+0x11c]
    cmp edi, eax
    jb snapshot
    mov dword ptr [ebx*4+0xe51e60], 2
    mov ecx, ebx
    call native_apply
team_done:
    popad
    ret

/* Used only by postgame and season cleanup. Fresh franchise initialization
 * still wipes all plans. The native cleaner removes departed player targets
 * and completed rehab. Its repeat bit is already serialized, not spare data.
 */
remember_clear:
    push ecx
    push edx
    pushad
    cmp ecx, 32
    jae clear_retail
    cmp dword ptr [0xe576a0], 2
    jne clear_retail
    cmp dword ptr [ecx*4+0xe5775c], 0
    je clear_cpu
    mov eax, offset remember_option
    jmp clear_enabled
clear_cpu:
    mov eax, offset cpu_option
clear_enabled:
    test eax, eax
    jz clear_retail
    imul edi, ecx, 2000
    add edi, 0xe42460
    mov ecx, 500
mark_repeat:
    test dword ptr [edi], 511
    jz mark_next
    or dword ptr [edi], 0x80000000
mark_next:
    add edi, 4
    loop mark_repeat
    mov dword ptr [esp+32], 0 /* Retain valid repeat rows even across season. */
clear_retail:
    popad
    pop edx
    pop ecx
    jmp native_clear

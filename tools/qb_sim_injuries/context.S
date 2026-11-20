.intel_syntax noprefix
.code32
.section .text
.global match_entry,medical,contest,redzone,gain,slope,bias,flat,active,gamecast_restore
# Entered by the weekly simulation and Gamecast match initializers.
match_entry:
    pushfd
    pushad
    mov byte ptr [active],0
    # The match initializer's own return and both weekly parents disambiguate Pause > Simulate To End.
    mov eax,[esp+36]
    cmp eax,offset GAMECAST_RETURN
    je check_franchise
    cmp eax,offset WEEKLY_OR_PAUSE_RETURN
    jne skip
    cmp dword ptr [esp+64],offset WEEKLY_INNER_RETURN
    jne skip
    cmp dword ptr [esp+88],offset WEEKLY_OUTER_RETURN
    jne skip
check_franchise:
    cmp dword ptr [LEAGUE_KIND],2
    jne skip
    cmp dword ptr [GAME_KIND],4
    jne skip
    mov eax,[LEAGUE_STAGE]
    sub eax,7
    cmp eax,2
    ja skip
    mov eax,[ROSTER_ROOT]
    test eax,eax
    jz skip
    mov ebx,[eax+0x1c]
    test ebx,ebx
    jz skip
    mov esi,ecx
    sub esi,ebx
    cmp esi,15500
    ja skip
    mov edi,edx
    sub edi,ebx
    cmp edi,15500
    ja skip
    cmp esi,edi
    je skip
    mov ecx,500
    mov eax,esi
    xor edx,edx
    div ecx
    test edx,edx
    jnz skip
    mov eax,edi
    xor edx,edx
    div ecx
    test edx,edx
    jnz skip
    mov byte ptr [active],1
    # Reopening the same signed fixture must draw a fresh stream from this match.
    mov eax,[LEAGUE_YEAR]
    cmp eax,[CACHED_YEAR]
    jne admitted
    mov eax,[LEAGUE_WEEK]
    cmp eax,[CACHED_WEEK]
    jne admitted
    cmp esi,edi
    jb ordered
    xchg esi,edi
ordered:
    cmp esi,[CACHED_HOME]
    jne admitted
    cmp edi,[CACHED_AWAY]
    jne admitted
    mov dword ptr [CACHED_YEAR],-1
admitted:
    cmp dword ptr [esp+36],offset GAMECAST_RETURN
    je gamecast
    popad
    popfd
    jmp WEEKLY_ENTRY
skip:
    popad
    popfd
    jmp NATIVE_INIT
gamecast:
    mov dword ptr [UNDO],0
    cmp dword ptr [LEAGUE_STAGE],8
    jb gamecast_init
    # prepare(ax) applies the same managed-team, clean-recovery and lock checks used for a week simulation.
    mov eax,[esp+24]  # saved ECX
    call PREPARE
    mov eax,[esp+20]  # saved EDX
    call PREPARE
gamecast_init:
    popad
    popfd
    mov dword ptr [esp],offset gamecast_restore
    jmp NATIVE_INIT
gamecast_restore:
    pushfd
    pushad
    call RESTORE
    popad
    popfd
    jmp GAMECAST_RETURN
.macro route name, target
\name:
    pushfd
    cmp byte ptr [active],0
    je .Lphysical\@
    popfd
    jmp \target
.Lphysical\@:
    popfd
.endm
route medical,MEDICAL_ENTRY
    jmp NATIVE_MEDICAL
route contest,CONTEST_ENTRY
    mov edx,dword ptr [DEFENSE_SIDE]
    ret
route redzone,REDZONE_ENTRY
    fmul dword ptr [physical_redzone]
    ret
route gain,GAIN_ENTRY
    fmul dword ptr [physical_gain]
    ret
.macro scalar name, op, official, physical
\name:
    pushfd
    cmp byte ptr [active],0
    je .Lold\@
    popfd
    \op dword ptr [\official]
    ret
.Lold\@:
    popfd
    \op dword ptr [\physical]
    ret
.endm
scalar slope,fmul,SLOPE_ADDR,physical_slope
scalar bias,fadd,BIAS_ADDR,physical_bias
scalar flat,fcomp,BIAS_ADDR,physical_bias
.balign 4,0xcc
physical_redzone: .long PHYS_REDZONE
physical_gain: .long PHYS_GAIN
physical_slope: .long PHYS_SLOPE
physical_bias: .long PHYS_BIAS
active: .byte 0
.balign 4,0xcc
.global gamecast_screen_entry
gamecast_screen_entry:
    # A completed entry skips NATIVE_INIT. Starting a new screen forgets the old fixture in either case.
    # Resume, Change Game Plan and the live Gamecast ticker stay inside the existing screen.
    mov byte ptr [active],0
    jmp GAMECAST_BIND_RESOURCES
.section .note.GNU-stack,"",@progbits

/* Beta 81 review F1: a gadget substitution lasts one snap.
   The game rebuilds a lineup only on the play-call path (0x89590 -> 0x18AD10). The
   no-huddle / audible / re-pick handlers (0xA24B0 and others) store the next play
   with 0x9F990 and keep the eleven already on the field, so a GAD put in by this
   rule would stay. 0x9F990 calls 0xB8790 (ECX side, EDX play) right after storing
   the play; that call comes here. When the stored side is the offense whose last
   build carried a substitution, the offense lineup is rebuilt exactly as 0x89590
   builds it (0x18AD10 with the play-call record and the two packed situation
   values), which gives the game's own eleven for the new play. Every other store
   (the defense, a side without a substitution) only runs 0xB8790. */
.intel_syntax noprefix
.text
.global restore_after_store, gadget_team
.set formation_sync, 0xb8790
.set offense_build, 0x18ad10
.set offense_side, 0xe60280
restore_after_store:
    call formation_sync               /* the displaced call, same registers */
    cmp esi,dword ptr [gadget_team]   /* ESI: 0x9F990's side */
    jne done
    cmp esi,dword ptr [offense_side]
    jne done
    pushad
    mov dword ptr [gadget_team],0
    mov ecx,esi
    mov edx,dword ptr [ecx+0xc]       /* the side's play-call record */
    sub esp,8
    mov eax,dword ptr [edx+0xc8]
    shl eax,0x16
    sar eax,0x1d
    mov dword ptr [esp],eax
    mov eax,dword ptr [edx+0xc8]
    shl eax,0x13
    sar eax,0x1d
    mov dword ptr [esp+4],eax
    mov eax,esp
    push eax
    push 1
    push 0
    push 0
    add edx,4
    call offense_build                /* ret 0x10 */
    add esp,8
    popad
done:
    ret
.balign 4
gadget_team:                          /* RAM marker in this owned writable pool page; zero on disc */
    .long 0
.section .note.GNU-stack,"",@progbits

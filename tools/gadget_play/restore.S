/* Beta 81 review F1: a gadget substitution lasts one snap.
   The game rebuilds a lineup only on the play-call path (0x89590 -> 0x18AD10). The
   no-huddle / audible / re-pick handlers (0xA24B0 and others) store the next play
   with 0x9F990 and keep the eleven already on the field, so a GAD put in by this
   rule would stay. 0x9F990 calls 0xB8790 (ECX side, EDX play) right after storing
   the play; that call comes here. The first store for the side whose last build
   carried a substitution spends the mark. When that store is for the offense and
   is not the huddle play call (0x2074BC, which the play-call build 0x89590 always
   follows), the offense lineup is rebuilt exactly as 0x89590 builds it (0x18AD10
   with the play-call record and the two packed situation values), which gives the
   game's own eleven for the stored play; the rule does not act on that rebuild (it
   acts only under 0x89624). Every other store only runs 0xB8790.

   Fatigue. The snap path checks every pick with 0x188440 (call 0x18A6EE): a player on
   the field stays if his stamina is at least the field threshold ([0xE60194]/20 home,
   [0xE601A4]/20 away; 0.25 by default), a benched one comes in only at the bench
   threshold ([0xE60198]/20, [0xE601A8]/20; 0.80). Without the rule the receiver the GAD
   replaced would have stayed on the field and kept his place at 0.25; benched for one
   snap he would need 0.80, and the game's fallback (0x189360) would put another
   receiver, usually the GAD row player, in his place. So in the next build of that side
   (the play-call build or the restore's rebuild) that one receiver is checked with the
   field threshold, once; every other check is the game's own. */
.intel_syntax noprefix
.text
.global restore_after_store, available_or_kept, gadget_team, gadget_benched, gadget_grace
.set formation_sync, 0xb8790
.set offense_build, 0x18ad10
.set offense_side, 0xe60280
.set huddle_store_return, 0x2074c1    /* after 0x2074BC: call 0x9F990 (the play call) */
.set availability, 0x188440
.set field_home, 0xe60194
.set bench_home, 0xe60198
.set field_away, 0xe601a4
.set bench_away, 0xe601a8
restore_after_store:
    call formation_sync               /* the displaced call, same registers */
    cmp esi,dword ptr [gadget_team]   /* ESI: 0x9F990's side */
    jne done
    mov dword ptr [gadget_team],0     /* this side's next store spends the mark */
    cmp esi,dword ptr [offense_side]
    jne done
    cmp dword ptr [esp+0x10],huddle_store_return   /* 0x9F990's return: ebx, esi, edi pushed */
    je done
    pushad
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
    mov eax,dword ptr [gadget_benched]
    mov dword ptr [gadget_grace],eax
    mov dword ptr [gadget_benched],0
    call offense_build                /* ret 0x10 */
    mov dword ptr [gadget_grace],0
    add esp,8
    popad
done:
    ret

available_or_kept:                    /* replaces call 0x188440 at 0x18A6EE: EDX the pick, [esp+4] the fatigue flag; ret 4 */
    cmp edx,dword ptr [gadget_grace]
    jne availability                  /* the game's own check, same stack */
    mov dword ptr [gadget_grace],0
    push esi
    mov esi,dword ptr [field_home]
    xchg esi,dword ptr [bench_home]   /* bench threshold := field threshold, for this check only */
    push esi
    mov esi,dword ptr [field_away]
    xchg esi,dword ptr [bench_away]
    push esi
    push dword ptr [esp+0x10]         /* the fatigue flag */
    call availability                 /* ret 4 */
    pop esi
    mov dword ptr [bench_away],esi
    pop esi
    mov dword ptr [bench_home],esi
    pop esi
    ret 4

.balign 4
gadget_team:                          /* RAM marker in this owned writable pool page; zero on disc */
    .long 0
gadget_benched:                       /* the receiver the last substitution benched */
    .long 0
gadget_grace:                         /* that receiver, during the next build of his side */
    .long 0
.section .note.GNU-stack,"",@progbits

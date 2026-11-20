/* Called after both players are healthy and the GAD is absent from the
   native line. The surrounding builder restores all general registers. */
.intel_syntax noprefix
.text
.global assign_if_fast
.extern gadget_team, gadget_benched
assign_if_fast:
    mov ecx,[ebp-4]                   /* the designated receiving slot */
    push esi                          /* ESI is the offense's side (team) */
    mov esi,[edx+ecx*4]               /* the native pick for that slot */
    mov bl,[eax+0x36]                 /* unsigned native Speed attribute */
    cmp bl,[esi+0x36]
    jb slower
    /* Beta 81 review F1: remember whom the GAD sent to the bench (restore.S) */
    mov dword ptr [gadget_benched],esi
    pop esi
    mov [edx+ecx*4],eax
    mov dword ptr [gadget_team],esi   /* this side's lineup carries a substitution */
    ret
slower:
    pop esi
    ret
.section .note.GNU-stack,"",@progbits

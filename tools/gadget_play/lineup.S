/* Private proof overlay. The normal builder always picks all eleven first. */
.intel_syntax noprefix
.text
.global scoped_builder, tapped_ordinal, scope_return
.extern select_slot, native_gate, assign_if_fast
.set native_builder, 0xe89f0
.set ordinal, 0xe7530
.set list_length, 0xe75a0
.set list_read, 0xe7810

/* Entry from 0x18a641. At entry S, S+0xb4 returns from 0x18a5d0;
   S+0xdc returns from 0x18ad10. S+0x18 is the latter's saved ESI.
   Test the immediate caller before inspecting its parent's frame. */
scoped_builder:
    cmp dword ptr [esp+0xb4],0x18ad4b
    jne native_builder
    cmp dword ptr [esp+0xdc],0x89624
    jne native_builder
    cmp esi,dword ptr [0xe60280]
    jne native_builder
    cmp esi,0xe5fc20
    je home
    cmp esi,0xe5fc60
    jne native_builder
    cmp edx,dword ptr [0xe5fe84]
    jne native_builder
    jmp bound
home:
    cmp edx,dword ptr [0xe5fe80]
    jne native_builder
bound:
    push ebp
    mov ebp,esp
    sub esp,8                         /* slot and eventual eligible player */
    pushad
    mov eax,[esi+12]
    add eax,4
    cmp eax,[ebp+0x1c]                /* official selected descriptor */
    jne unselected
    push dword ptr [ebp+12]            /* builder's formation */
    push dword ptr [ebp+8]             /* builder's category */
    push eax
    push edx                          /* builder's active book */
    call select_slot
    add esp,16
    jmp selected
unselected:
    mov eax,-1
selected:
    mov [ebp-4],eax
    popad
    cmp dword ptr [ebp-4],11
    jb scoped
    leave
    jmp native_builder
scoped:
    mov dword ptr [ebp-8],0
    push dword ptr [ebp+20]
    push dword ptr [ebp+16]
    push dword ptr [ebp+12]
    push dword ptr [ebp+8]
    call native_builder
scope_return:
    pushad
    mov eax,[ebp-8]
    test eax,eax
    jz complete
    mov edx,[ebp+16]                  /* full native output, eleven rows */
    xor ecx,ecx
check_line:
    cmp dword ptr [edx+ecx*4],0
    je complete
    cmp [edx+ecx*4],eax               /* includes future or explicitly set slots */
    je complete
    inc ecx
    cmp ecx,11
    jb check_line
    call assign_if_fast                /* preserve source-linked entry addresses */
    nop
complete:
    popad
    leave
    ret 16

/* 0xe8afc calls this native ordinal helper only when the builder found no
 * explicit substitution for the slot. Every other caller runs the displaced
 * instructions unchanged. T+0x84 is the native builder's return address. */
tapped_ordinal:
    cmp dword ptr [esp],0xe8b01
    jne ordinal_original
    cmp dword ptr [esp+0x84],offset scope_return
    jne ordinal_original
    cmp edi,9
    jne ordinal_original
    cmp esi,[esp+0x9c]
    jne ordinal_original
    pushad
    mov ebp,[esp+0x24]                 /* actual native depth context */
    sub esp,4
    mov eax,9
    mov edx,7                         /* SPECIAL/GAD is WR paired side row 3 */
    mov esi,esp
    call ordinal
    mov edi,eax
    mov ecx,eax
    mov edx,ebp
    call list_length
    pop edx
    cmp eax,edx
    jle restore
    mov ecx,[esp+0x40]                 /* builder's active book */
    push edx
    push ebp
    mov eax,edi
    call list_read
    test eax,eax
    jz restore
    mov ebx,eax
    test byte ptr [ebx+0x23],0x80      /* active roster injury */
    jnz restore
    mov eax,[esp+0x1c]                /* category from the real builder */
    movzx eax,byte ptr [eax+4]
    and eax,63
    mov edx,[esp+4]                   /* saved ESI, actual slot */
    push 3
    push edx
    push eax
    mov ecx,ebp
    mov edx,ebx
    call native_gate                  /* forward picker's eligibility test */
    test eax,eax
    jz restore
    mov [esp+0x20+0x98],ebx            /* final duplicate check follows */
restore:
    popad
ordinal_original:
    push ebx
    push ebp
    mov ebp,[esp+0x10]
    jmp 0xe7766
.section .note.GNU-stack,"",@progbits

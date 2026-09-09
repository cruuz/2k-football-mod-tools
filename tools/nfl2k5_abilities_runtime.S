/* EXPERIMENTAL / UNWITNESSED. GNU as --32. No mutable owned data.
 * Seven stored bits, on-demand off-week, native entity charge meter.
 * All helper scratch is registers/stack; entry wrappers preserve flags/GPRs.
 */
.intel_syntax noprefix
.code32
.text
.global speed, decode, dispatch, initialize, generate, ai_ready, consume
.global config, instructions_end, move_masks, consumers, code_end
.extern retail_attribute, retail_decode, retail_account
.extern retail_initialize_tail, retail_generate_tail, retail_ai_tail, retail_consume_tail
.extern retail_attribute_tail

/* ECX=record -> EAX=known flags. No entity/render/controller side effects. */
effective:
    xor eax, eax
    test ecx, ecx
    jz effective_done
    cmp ecx, -1
    je effective_done
    cmp dword ptr [config], -1
    je effective_read
    cmp dword ptr [0xe576a0], 2
    jne effective_read
    cmp dword ptr [0xe576a4], 8
    jne effective_read
    mov eax, [config]
    cmp eax, [0xe576b4]
    je effective_zero
effective_read:
    movzx eax, word ptr [ecx+0x52]
    and eax, 0x1ee0
    /* Tier0 is legacy v1. Explicit tiers with excess flags fail closed. */
    push ebx
    push edx
    push ecx
    movzx edx, byte ptr [ecx+0x53]
    shr edx, 6
    jz tier_done
    mov dl, byte ptr [tier_limits+edx]
    mov ebx, eax
tier_count:
    test ebx, ebx
    jz tier_done
    dec dl
    js tier_overfull
    lea ecx, [ebx-1]
    and ebx, ecx
    jmp tier_count
tier_overfull:
    xor eax, eax
tier_done:
    pop ecx
    pop edx
    pop ebx
    ret
effective_zero:
    xor eax, eax
effective_done:
    ret

/* Stored abilities and unlocked permissions are deliberately separate.
 * Disabling a lock never grants a rating effect. */
permissions:
    call effective
    or eax, [unlocked_mask]
    ret

/* ZF=both move locks disabled: keep the full retail charge policy. */
unlocked_moves:
    mov eax, [unlocked_mask]
    and eax, 0x1ec0
    cmp eax, 0x1ec0
    ret

/* EBX=entity. CF=live attached carrier; ESI=state/0, EDX=steer/0.
 * Match the actual 1CE280 chain: [ball] is holder, holder+1C is kind. */
carrier:
    xor esi, esi
    xor edx, edx
    lea eax, [ebx+1]
    cmp eax, 1
    jbe carrier_no
    mov esi, [ebx+0x10]
    lea eax, [esi+1]
    cmp eax, 1
    jbe carrier_bad_state
    mov edx, [ebx+0x0c]
    lea eax, [edx+1]
    cmp eax, 1
    jbe carrier_bad_steer
    cmp dword ptr [0xe602b8], 14
    jne carrier_no
    mov eax, [0xe5fc00]
    inc eax
    cmp eax, 1
    jbe carrier_no
    dec eax
    cmp [eax], ebx
    jne carrier_no
    cmp dword ptr [ebx+0x1c], 1
    jne carrier_no
    stc
    ret
carrier_bad_state:
    xor esi, esi
carrier_bad_steer:
    xor edx, edx
carrier_no:
    clc
    ret

/* EDX=steer; CF=verified human running context or native CPU marker. */
running:
    mov eax, [edx]
    cmp eax, -1
    je running_yes
    cmp eax, 3
    ja running_no
    imul eax, eax, 44
    mov eax, [eax+0xa9b960]
    cmp eax, 8
    je running_yes
    cmp eax, 10
    je running_yes
running_no:
    clc
    ret
running_yes:
    stc
    ret

/* ECX=state/command -> EDI=required word mask; 0=outside five-move map.
 * Native callback18D480 resolves jukes to5C/5D. Context/holder guard is separate. */
move_mask:
    xor edi, edi
    cmp ecx, 0x5c
    je mask_juke
    cmp ecx, 0x5d
    je mask_juke
    sub ecx, 0x18
    cmp ecx, 0x13
    ja mask_done
    movzx edi, word ptr [move_masks+ecx*2]
mask_done:
    ret
mask_juke:
    mov edi, 0x80
    ret

/* Clear only the native charge fields and request. Validated ESI/EDX or0. */
clear_charge:
    test esi, esi
    jz clear_request
    and dword ptr [esi+0x90], -4
    mov dword ptr [esi+0x44], 0
    mov dword ptr [esi+0x48], 0xbf800000
clear_request:
    test edx, edx
    jz clear_done
    and dword ptr [edx+0x18], -5
clear_done:
    ret

/* EBX=entity -> CF=may generate charge. Also remove stale active permission.
 * Meter policy explicitly live-carrier-only. No controller-owned timer. */
maintain:
    call unlocked_moves
    je maintain_yes
    call carrier
    jnc maintain_clear
    mov ecx, [ebx+0x3c]
    call permissions
    mov ebp, eax
    test eax, 0x40
    jnz maintain_any
    and eax, 0xfffff7ff  /* hurdle requires stick permission too */
maintain_any:
    test eax, 0x1e80
    jz maintain_clear
    mov eax, [esi+0x90]
    and eax, 3
    cmp eax, 1
    jne maintain_yes
    mov ecx, [esi]
    call move_mask
    test edi, edi
    jz maintain_clear
    and ebp, edi
    cmp ebp, edi
    jne maintain_clear
maintain_yes:
    stc
    ret
maintain_clear:
    call clear_charge
    clc
    ret

/* EBX=entity. Filter decoded/CPU commands only in live running contexts.
 * Denial selects ordinary0 and clears the simultaneous charge request.
 * Steering direction/throttle and lower-priority input are never rewritten. */
filter:
    call maintain
    call carrier
    jnc filter_done
    call running
    jnc filter_done
    mov ecx, [edx+0x1c]
    call move_mask
    test edi, edi
    jz filter_done
    mov ecx, [ebx+0x3c]
    call permissions
    and eax, edi
    cmp eax, edi
    je filter_done
    mov dword ptr [edx+0x1c], 0
    call clear_charge
filter_done:
    ret

/* Retail attribute ABI ECX=record, EDX=attribute0, stack modifier, ST0 return.
 * Preserve record across the native call and forward exactly one ret4 arg. */
speed:
    push ecx
    push dword ptr [esp+8]
    call retail_attribute
    pop ecx
    pushfd
    pushad
    sub esp, 12
    fstp dword ptr [esp]
    mov dword ptr [esp+4], 0x3f7d70a4  /* .99 */
    call permissions
    test eax, 0x20
    jz speed_bound
    movzx eax, byte ptr [ecx+0x36]
    sub eax, 100
    cmp eax, 27
    ja speed_bound
    add eax, 100
    mov [esp+8], eax
    fild dword ptr [esp+8]
    fmul dword ptr [config+4]
    fst dword ptr [esp+4]
    fmul dword ptr [esp]
    fstp dword ptr [esp]
speed_bound:
    mov eax, [esp]
    test eax, eax
    js speed_zero
    cmp eax, 0x7f800000
    jae speed_zero
    cmp eax, [esp+4]
    jbe speed_load
    mov eax, [esp+4]
    jmp speed_store
speed_zero:
    xor eax, eax
speed_store:
    mov [esp], eax
speed_load:
    fld dword ptr [esp]
    add esp, 12
    popad
    popfd
    ret 4

decode:
    call retail_decode
    pushfd
    pushad
    /* EBX is the entity at156482. */
    call filter
    popad
    popfd
    ret

dispatch:
    pushfd
    pushad
    mov ebx, ecx
    call filter
    popad
    popfd
    /* Reload command for both accounting and the subsequent callback index. */
    mov eax, [ecx+0x0c]
    mov edi, [eax+0x1c]
    mov edx, edi
    jmp retail_account

/* Common state initializer, also reached by AI/direct transition paths.
 * On denial install the native ordinary descriptor with consistent state0. */
initialize:
    pushfd
    pushad
    mov ebx, ecx
    call carrier
    jnc initialize_done
    call running
    jnc initialize_done
    mov ebp, [esp+20]   /* saved EDX requested descriptor */
    mov ecx, [esi]
    cmp ecx, 0x5d
    ja initialize_steer
    cmp ebp, [0xad67f0+ecx*4]
    je initialize_mask
initialize_steer:
    mov ecx, [edx+0x1c]
    cmp ecx, 0x5d
    ja initialize_family
    cmp ebp, [0xad67f0+ecx*4]
    je initialize_mask
initialize_family:
    /* A direct transition with no matching numeric state uses the complete
     * descriptor-family permission (Spin+Juke for the shared initializer). */
    mov edi, offset families
    mov ecx, 7
initialize_find:
    cmp ebp, [edi]
    je initialize_family_found
    add edi, 8
    loop initialize_find
    jmp initialize_done
initialize_family_found:
    mov edi, [edi+4]
    jmp initialize_check
initialize_mask:
    call move_mask
initialize_check:
    test edi, edi
    jz initialize_done
    mov ecx, [ebx+0x3c]
    call permissions
    and eax, edi
    cmp eax, edi
    je initialize_done
    mov dword ptr [esp+20], 0x50f4ec
    mov dword ptr [esi], 0
    mov dword ptr [edx+0x1c], 0
    call clear_charge
initialize_done:
    popad
    popfd
    push ebx
    push esi
    push edi
    mov edi, ecx
    jmp retail_initialize_tail

generate:
    pushfd
    pushad
    mov ebx, ecx
    call maintain
    jnc generate_denied
    popad
    popfd
    mov eax, [0xe5ff80]
    jmp retail_generate_tail
generate_denied:
    popad
    popfd
    ret

ai_ready:
    pushfd
    pushad
    mov ebx, ecx
    call maintain
    jnc generate_denied
    popad
    popfd
    mov eax, [ecx+0x10]
    mov ecx, [eax+0x90]
    jmp retail_ai_tail

/* Consume only when BOTH the byte-scanned caller and current state agree.
 * No steering read is used to infer a delayed animation's move permission. */
consume:
    pushfd
    pushad
    mov ebx, ecx
    call unlocked_moves
    je consume_allowed
    call carrier
    jnc consume_denied
    mov eax, [esp+36]   /* original native caller return address */
    mov edi, offset consumers
    mov ecx, 15
consume_find:
    cmp eax, [edi]
    je consume_found
    add edi, 8
    loop consume_find
    jmp consume_denied
consume_found:
    mov ebp, [edi+4]    /* initializer entry or0: documented nonmove */
    test ebp, ebp
    jz consume_denied
    mov ecx, [esi]
    cmp ecx, 0x5d
    ja consume_denied
    mov eax, [0xad67f0+ecx*4]
    cmp [eax+4], ebp
    jne consume_denied
    call move_mask
    test edi, edi
    jz consume_denied
    mov ecx, [ebx+0x3c]
    call permissions
    and eax, edi
    cmp eax, edi
    jne consume_denied
consume_allowed:
    popad
    popfd
    push esi
    mov esi, [ecx+0x10]
    fld dword ptr [esi+0x44]
    jmp retail_consume_tail
consume_denied:
    call clear_charge
    popad
    popfd
    ret

/* Common effective-attribute entry. Forward native ret4 argument, then add
 * 0.02 * tier only for five mapped stored abilities during live phase14.
 * Retail clamps, condition, injury and sliders execute first. No rating
 * byte or cache is edited. Tier0 retains v1. Result remains in [0,1]. */
attribute:
    push edx
    push ecx
    push dword ptr [esp+12]
    call attribute_body
    pushfd
    pushad
    /* Keep the native call's volatile outputs too. Saved input record/index
     * live below the flags/GPR snapshot until the wrapper returns. */
    mov ecx, [esp+36]
    mov edx, [esp+40]
    cmp dword ptr [0xe602b8], 14
    jne attribute_done
    cmp edx, 18
    ja attribute_done
    mov esi, edx
    call effective
    test ax, word ptr [effect_masks+esi*2]
    jz attribute_done
    movzx eax, byte ptr [ecx+0x53]
    shr eax, 6
    jz attribute_done
    sub esp, 8
    mov [esp+4], eax
    fstp dword ptr [esp]
    mov eax, [esp]
    test eax, eax
    jle attribute_load
    cmp eax, 0x3f800000
    jae attribute_load
    fild dword ptr [esp+4]
    fmul dword ptr [effect_step]
    fadd dword ptr [esp]
    fstp dword ptr [esp]
    cmp dword ptr [esp], 0x3f800000
    jbe attribute_load
    mov dword ptr [esp], 0x3f800000
attribute_load:
    fld dword ptr [esp]
    add esp, 8
attribute_done:
    popad
    popfd
    lea esp, [esp+8]
    ret 4
attribute_body:
    sub esp, 8
    mov eax, [ecx+0x30]
    jmp retail_attribute_tail
instructions_end:
.balign 4, 0xcc
config:
    .long -1
    .float 0.01
move_masks:
    /*18,19,1A,1B,1C,1D,1E,1F,20,21,22,23,24..2B*/
    .word 0x1000,0x1000,0x0840,0x0200,0x0200,0x0080,0x0080,0
    .word 0x0080,0x0080,0x0080,0x0400
    .word 0x00c0,0x00c0,0x00c0,0x00c0,0x00c0,0x00c0,0x00c0,0x00c0
consumers:
    .long 0x18d2cb,0, 0x18df81,0, 0x1e7743,0, 0x1e7ba7,0, 0x2319d0,0
    .long 0x2908a0,0x290880, 0x291d65,0, 0x2dbbd1,0x2dbbc0
    .long 0x2dc808,0x2dc7f0, 0x2dcf98,0x2dcf70, 0x306dfc,0x306de0
    .long 0x308517,0, 0x30d2c7,0x30d2a0, 0x30edac,0, 0x317942,0
families:
    .long 0x530148,0x1000, 0x51cb08,0x840, 0x5300f8,0x280
    .long 0x531064,0x400, 0x530f5c,0xc0, 0x530134,0x80
    .long 0x530120,0x280
unlocked_mask:
    .long 0
effect_step:
    .float 0.02
effect_masks:
    /* Native table order, NOT the on-disc rating byte order:
     * Agility/Juke, Strength/Stiff-Arm, Jumping/Hurdle,
     * Break Tackle/Truck, Pass Rush/Spin. */
    .word 0,0x80,0x1000,0x800,0,0,0,0,0,0,0,0,0x400,0,0,0,0,0,0x200
tier_limits:
    .byte 7,2,4,7
code_end:

/* EXPERIMENTAL / UNWITNESSED. B is an additional shell; never an enum.
 * No persistent texture pointer or player-index bitmap. Re-evaluate current
 * context, record, mode and global resource registration at every bind/update.
 * All scratch is private stack/registers. Native helpers are integer-only.
 */
.intel_syntax noprefix
.code32
.text
.global bind, shine, clone, config, instructions_end, code_end
.extern retail_bind_tail, retail_shine_tail, retail_shine_next
.extern retail_texture, retail_bind_texture
.extern retail_clone_tail

/* Native field-by-field clone omits the pad bytes. EBP=source, EDI=new
 * record, proved by C16B0..C16CD. Carry ONLY this owner's bit. */
clone:
    pushfd
    push eax
    mov al, [ebp+0x53]
    xor al, [edi+0x53]
    and al, 0x20
    xor [edi+0x53], al
    pop eax
    popfd
    mov cx, [ebp+4]
    mov [edi+4], cx
    jmp retail_clone_tail

bind:
    pushfd
    pushad
    cld
    mov edx, [ebp+8]
    call refresh
    popad
    popfd
    mov edx, [ebp-0x14]
    mov eax, edx
    jmp retail_bind_tail

/* EAX=current material index, EBX=LOD*62, EDI=LOD. Intercept the
 * existing B comparison before its x87 shine calculation. Other materials
 * execute the displaced comparison and the original branch unchanged. */
shine:
    pushfd
    pushad
    movzx ecx, byte ptr [ebx+0xb6531f]
    cmp eax, ecx
    jne shine_retail
    cmp ecx, 255
    je shine_retail
    cld
    mov edx, edi
    mov esi, [ebp+8]
    mov ebx, [esi]
    mov edi, [esi+edx*4+0x14]
    call refresh
    popad
    popfd
    movzx ecx, byte ptr [ebx+0xb6531f]
    cmp eax, ecx
    jmp retail_shine_next
shine_retail:
    popad
    popfd
    movzx ecx, byte ptr [ebx+0xb6531f]
    cmp eax, ecx
    jmp retail_shine_tail

/* ESI=render context, EBX=roster record, EDI=scene, EDX=LOD (0 or 2).
 * Only the current B shell material is touched. Accessories stay disabled.
 * Return value is deliberately unused. Helper may clobber caller GPRs. */
refresh:
    cmp edx, 2
    ja refresh_done
    cmp edx, 1
    je refresh_done
    test edi, edi
    jz refresh_done
    imul eax, edx, 0x3e
    movzx eax, byte ptr [eax+0xb6531f]
    cmp eax, 255
    je refresh_done
    cmp eax, [edi+0x1c]
    jae refresh_done
    mov ecx, [edi+0x20]
    test ecx, ecx
    jz refresh_done
    push eax
    shl eax, 7
    add ecx, eax
    /* Verify the cached slot is B in this particular scene, not a stale
     * index from a different model. UTF-16 "HI_HELMET_B\0". */
    mov eax, [ecx]
    test eax, eax
    jz refresh_pop
    cmp dword ptr [eax], 0x00490048
    jne refresh_pop
    cmp dword ptr [eax+4], 0x0048005f
    jne refresh_pop
    cmp dword ptr [eax+8], 0x004c0045
    jne refresh_pop
    cmp dword ptr [eax+12], 0x0045004d
    jne refresh_pop
    cmp dword ptr [eax+16], 0x005f0054
    jne refresh_pop
    cmp dword ptr [eax+20], 0x00000042
    jne refresh_pop
    /* Invalidate before every decision, including failures and unregistration. */
    or byte ptr [ecx+8], 1
    mov byte ptr [ecx+9], 0
    mov dword ptr [ecx+0x30], 0
    mov dword ptr [ecx+0x34], 0
    push ecx
    /* The native live render-context array is stride 0x54. Standalone
     * equipment previews use a separate context and fail this membership. */
    mov eax, [0xb652d0]
    test eax, eax
    jz refresh_material_pop
    mov ecx, esi
    sub ecx, eax
    jb refresh_material_pop
    mov eax, ecx
    xor edx, edx
    mov ecx, 0x54
    div ecx
    test edx, edx
    jnz refresh_material_pop
    cmp eax, [0xb65274]
    jae refresh_material_pop
    test ebx, ebx
    jz refresh_material_pop
    cmp ebx, -1
    je refresh_material_pop
    cmp [esi], ebx
    jne refresh_material_pop
    cmp dword ptr [esi+4], 0
    jne refresh_material_pop
    cmp dword ptr [esi+8], 0
    jne refresh_material_pop
    mov eax, [esi+0x2c]
    test eax, eax
    jz refresh_material_pop
    cmp [eax], ebx
    jne refresh_material_pop
    movzx eax, byte ptr [ebx+0xc]
    shr eax, 6
    cmp eax, 1
    ja refresh_material_pop
    test byte ptr [ebx+0x53], 0x20
    jnz refresh_texture
    cmp byte ptr [config], 0
    je refresh_material_pop
    cmp dword ptr [0xe5ff80], 3
    ja refresh_material_pop
refresh_texture:
    /* Name is immutable owned code data; lookup returns the current native
     * descriptor or null. No own cache survives group release or reuse. */
    push offset texture_name
    xor ecx, ecx
    mov edx, 0x52545854
    call retail_texture
    test eax, eax
    jz refresh_material_pop
    push eax
    mov eax, [esp+8]
    mov ecx, edi
    call retail_bind_texture
refresh_material_pop:
    add esp, 4
refresh_pop:
    add esp, 4
refresh_done:
    ret
instructions_end:
.balign 4, 0xcc
config:
    .long 1
texture_name:
    .short 'h','e','l','m','e','t','0','1',0
code_end:

.intel_syntax noprefix
.code32
.global _start
_start:
Lfca87:
mov esi, dword ptr [0xe602b4]
Lfca8d:
cmp esi, edi
Lfca8f:
je Lfccc4
Lfca95:
push ebx
push ebp
mov ebp, 0xa95bb0
Lfca96:
mov ebx, dword ptr [0xe602ec]
Lfca9c:
xor edx, edx
cmp dword ptr [ebx + 0x160], edi
Lfcaa2:
jne Lfcaba
Lfcaa4:
cmp dword ptr [ebx + 0x98], edi
Lfcaaa:
je Lfcabf
Lfcaac:
cmp ebx, -0x90
Lfcab4:
je Lfcabf
Lfcaba:
inc edx
Lfcabf:
mov eax, dword ptr [0xe60280]
Lfcac4:
cmp eax, edi
Lfcac6:
mov ecx, dword ptr [0xe602b8]
Lfcacc:
mov dword ptr [ebp-96], edx
Lfcad2:
je Lfcbdd
Lfcad8:
mov eax, dword ptr [eax + 0xc]
Lfcadb:
add eax, 4
Lfcade:
je Lfcbdd
Lfcae4:
mov eax, dword ptr [eax + 4]
Lfcae7:
cmp eax, edi
Lfcae9:
je Lfcbdd
Lfcaef:
mov eax, dword ptr [eax + 4]
Lfcaf2:
shr eax, 8
Lfcaf5:
and eax, 0x3f
Lfcaf8:
cmp eax, 0xa
Lfcafb:
jne Lfcb75
Lfcafd:
cmp ecx, 0xe
Lfcb00:
jne Lfcbdd
Lfcb06:
cmp edx, edi
Lfcb08:
jne Lfcbdd
Lfcb0e:
fld dword ptr [ebp+132]
Lfcb14:
mov dword ptr [ebp-208], 1
Lfcb1e:
fcomp dword ptr [ebp+116]
Lfcb24:
fnstsw ax
Lfcb26:
test ah, 0x44
Lfcb29:
jnp Lfcb31
Lfcb2b:
mov dword ptr [ebp-208], edi
Lfcb31:
mov dword ptr [ebp+16], edi
jmp finalize
Lfcb75:
cmp eax, 0xc
Lfcb78:
jne Lfcbdd
Lfcb7a:
cmp esi, 3
Lfcb7d:
je Lfcbdd
Lfcb7f:
lea eax, [ecx-0xc]
cmp eax, 1
ja Lfcbdd
Lfcb89:
cmp edx, edi
Lfcb8b:
jne Lfcbdd
Lfcb8d:
push 1
pop ecx
mov dword ptr [0xba2f10], ecx
mov dword ptr [ebp-208], edi
mov dword ptr [ebp+16], ecx
jmp finalize
Lfcbdd:
fld dword ptr [ebp-92]
Lfcbe3:
mov edx, dword ptr [0xe602fc]
Lfcbe9:
fcomp dword ptr [ebp-108]
Lfcbef:
mov dword ptr [ebp-208], edi
Lfcbf5:
fnstsw ax
Lfcbf7:
test ah, 0x44
Lfcbfa:
jp Lfcc48
Lfcbfc:
test dh, dh
Lfcbfe:
js Lfcc48
Lfcc00:
fld dword ptr [ebp+132]
Lfcc06:
fcomp dword ptr [ebp+116]
Lfcc0c:
fnstsw ax
Lfcc0e:
test ah, 0x44
Lfcc11:
jp Lfcc48
Lfcc13:
cmp esi, 4
Lfcc16:
jne Lfcc48
Lfcc18:
cmp ecx, 0xe
Lfcc1b:
je Lfcc48
Lfcc1d:
cmp dword ptr [0xba2f14], edi
Lfcc23:
push 1
pop esi
Lfcc28:

Lfcc2e:
jne Lfcc40
Lfcc30:
cmp dword ptr [esp + 0x10], edi
Lfcc34:
je Lfcc53
Lfcc36:
cmp ecx, 0xc
Lfcc39:
je Lfcc40
Lfcc3b:
cmp ecx, 0xd
Lfcc3e:
jne Lfcc53
Lfcc40:
mov dword ptr [ebp+16], esi
Lfcc46:
jmp Lfcc59
Lfcc48:

Lfcc4e:
push 1
pop esi
Lfcc53:
mov dword ptr [ebp+16], edi
Lfcc59:
cmp ecx, 0xe
Lfcc5c:
jne Lfcc7f
Lfcc5e:
fld dword ptr [ebp-92]
Lfcc64:
fcomp dword ptr [ebp-108]
Lfcc6a:
fnstsw ax
Lfcc6c:
test ah, 0x44
Lfcc6f:
jp Lfcc7f
Lfcc71:
cmp dword ptr [ebx + 0x198], edi
Lfcc77:
mov dword ptr [ebp+128], esi
Lfcc7d:
jne Lfcc85
Lfcc7f:
mov dword ptr [ebp+128], edi
Lfcc85:

Lfccb4:
call 0xabe90
Lfccb9:
test eax, eax
Lfccbb:
je Lfccc3
Lfccbd:
mov dword ptr [ebp+16], esi
Lfccc3:
finalize:
push 1
pop eax
mov dword ptr [ebp-432], eax
mov dword ptr [ebp-320], eax
pop ebp
pop ebx
Lfccc4:
pop edi
Lfccc5:
pop esi
Lfccc6:
add esp, 8
Lfccc9:
ret 4

# EAX=context, ESI=output, EDX=panel offset. No persistent state.
.global panel_color
panel_color:
pushad
mov edi, edx
mov ebx, eax
test eax, eax
jz no_team
mov edx, dword ptr [eax+0x13c]
test edx, edx
jz no_team
mov ecx, esi
call 0x30ab0
cmp dword ptr [ebx+0x10c], 0
je no_color
mov ecx, ebx
call 0x68d70
mov ebp, eax
jmp contrast
no_team:
mov word ptr [esi], 0
no_color:
mov eax, 0xff252625
push eax
jmp silver
contrast:
test eax, 0x00808080
jnz shade
mov ecx, eax
add ecx, 0x000f0f0f
test ecx, 0x00808080
jz opaque
shade:
mov ecx, eax
and eax, 0x00fefefe
shr eax, 1
and ecx, 0x00f0f0f0
shr ecx, 4
sub eax, ecx
opaque:
or eax, 0xff000000
push eax
# The native accessors' unknown-code defaults are not team colours.
cmp ebp, 0xff0065e6
je silver
cmp eax, ebp
jne rim_ready
mov ecx, ebx
call 0x68dc0
mov ebp, eax
cmp eax, dword ptr [esp]
je silver
rim_ready:
jmp store
silver:
mov ebp, 0xffd1d2d3
store:
pop eax
mov ecx, dword ptr [0xa95528]
test ecx, ecx
jz color_done
cmp dword ptr [ecx+0x1c], 11
jne color_done
mov ecx, dword ptr [ecx+0x20]
test ecx, ecx
jz color_done
mov dword ptr [ecx+edi+0x18], eax
shr edi, 1
sub ecx, edi
mov dword ptr [ecx+12*128+0x18], ebp
color_done:
popad
ret
.global play_clock
play_clock:
mov ecx, dword ptr [0xe60294]
jecxz no_clock
test byte ptr [ecx+0x18], 6
jnz no_clock
jmp 0xfbb10
no_clock:
# This helper has only the FBE34 call site. Discard its return address and
# join the original formatter's register/stack epilogue after writing --.
pop eax
mov dword ptr [esi], 0x002d002d
mov word ptr [esi+4], 0
jmp 0xfbe4e
.global code_end
code_end:

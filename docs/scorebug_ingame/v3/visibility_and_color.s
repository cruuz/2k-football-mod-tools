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
Lfca96:
mov ebx, dword ptr [0xe602ec]
Lfca9c:
cmp dword ptr [ebx + 0x160], edi
Lfcaa2:
jne Lfcaba
Lfcaa4:
cmp dword ptr [ebx + 0x98], edi
Lfcaaa:
je Lfcab6
Lfcaac:
lea eax, [ebx + 0x90]
Lfcab2:
cmp eax, edi
Lfcab4:
jne Lfcaba
Lfcab6:
xor edx, edx
Lfcab8:
jmp Lfcabf
Lfcaba:
mov edx, 1
Lfcabf:
mov eax, dword ptr [0xe60280]
Lfcac4:
cmp eax, edi
Lfcac6:
mov ecx, dword ptr [0xe602b8]
Lfcacc:
mov dword ptr [0xa95b50], edx
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
fld dword ptr [0xa95c34]
Lfcb14:
mov dword ptr [0xa95ae0], 1
Lfcb1e:
fcomp dword ptr [0xa95c24]
Lfcb24:
fnstsw ax
Lfcb26:
test ah, 0x44
Lfcb29:
jnp Lfcb31
Lfcb2b:
mov dword ptr [0xa95ae0], edi
Lfcb31:
mov dword ptr [0xa95bc0], edi
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
mov eax, ecx
Lfcb81:
sub eax, 0xc
Lfcb84:
je Lfcb89
Lfcb86:
dec eax
Lfcb87:
jne Lfcbdd
Lfcb89:
cmp edx, edi
Lfcb8b:
jne Lfcbdd
Lfcb8d:
push 1
pop ecx
mov dword ptr [0xba2f10], ecx
mov dword ptr [0xa95ae0], edi
mov dword ptr [0xa95bc0], ecx
jmp finalize
Lfcbdd:
fld dword ptr [0xa95b54]
Lfcbe3:
mov edx, dword ptr [0xe602fc]
Lfcbe9:
fcomp dword ptr [0xa95b44]
Lfcbef:
mov dword ptr [0xa95ae0], edi
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
fld dword ptr [0xa95c34]
Lfcc06:
fcomp dword ptr [0xa95c24]
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
mov esi, 1
Lfcc28:

Lfcc2e:
jne Lfcc40
Lfcc30:
cmp dword ptr [esp + 0xc], edi
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
mov dword ptr [0xa95bc0], esi
Lfcc46:
jmp Lfcc59
Lfcc48:

Lfcc4e:
mov esi, 1
Lfcc53:
mov dword ptr [0xa95bc0], edi
Lfcc59:
cmp ecx, 0xe
Lfcc5c:
jne Lfcc7f
Lfcc5e:
fld dword ptr [0xa95b54]
Lfcc64:
fcomp dword ptr [0xa95b44]
Lfcc6a:
fnstsw ax
Lfcc6c:
test ah, 0x44
Lfcc6f:
jp Lfcc7f
Lfcc71:
cmp dword ptr [ebx + 0x198], edi
Lfcc77:
mov dword ptr [0xa95c30], esi
Lfcc7d:
jne Lfcc85
Lfcc7f:
mov dword ptr [0xa95c30], edi
Lfcc85:

Lfccb4:
call 0xabe90
Lfccb9:
test eax, eax
Lfccbb:
je Lfccc3
Lfccbd:
mov dword ptr [0xa95bc0], esi
Lfccc3:
finalize:
push 1
pop eax
mov dword ptr [0xa95a00], eax
mov dword ptr [0xa95a70], eax
pop ebx
Lfccc4:
pop edi
Lfccc5:
pop esi
Lfccc6:
add esp, 8
Lfccc9:
ret 4

# Called only by the already-live abbreviation formatters. EAX is their
# native team record, ESI their caller-owned UTF-16 buffer, EDX the byte
# offset of the panel material in the pinned eleven-record scene table.
.global panel_color
panel_color:
push ebx
push edi
mov edi, edx
mov ebx, eax
test eax, eax
jz no_team
mov edx, dword ptr [eax+0x13c]
test edx, edx
jz no_team
mov ecx, esi
call 0x30ab0
mov ecx, ebx
cmp dword ptr [ebx+0x10c], 0
jne lookup
xor ecx, ecx
lookup:
call 0x68d70
jmp contrast
no_team:
mov word ptr [esi], 0
mov eax, 0xff252625
contrast:
# Preserve already dark primary colours. With each byte below 128, adding
# 15 cannot carry into its neighbour; a high bit then means a byte >112.
test eax, 0x00808080
jnz shade
mov ecx, eax
add ecx, 0x000f0f0f
test ecx, 0x00808080
jz opaque
shade:
# Each byte becomes floor(c/2)-floor(c/16), bounded by 112. No colour table.
mov ecx, eax
and eax, 0x00fefefe
shr eax, 1
and ecx, 0x00f0f0f0
shr ecx, 4
sub eax, ecx
opaque:
or eax, 0xff000000
mov ecx, dword ptr [0xa95528]
test ecx, ecx
jz color_done
cmp dword ptr [ecx+0x1c], 11
jne color_done
mov ecx, dword ptr [ecx+0x20]
test ecx, ecx
jz color_done
mov dword ptr [ecx+edi+0x18], eax
color_done:
pop edi
pop ebx
ret
.global play_clock
play_clock:
mov eax, dword ptr [0xe60294]
test eax, eax
jz no_clock
test byte ptr [eax+0x18], 6
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

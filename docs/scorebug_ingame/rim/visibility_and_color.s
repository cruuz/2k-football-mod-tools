.intel_syntax noprefix
.code32
.global _start
_start:
Lfca87:
call timeout_update
mov esi, dword ptr [0xe602b4]
Lfca8d:
cmp esi, edi
Lfca8f:
je Lfccc4
Lfca95:
push ebx
push ebp
mov ebp, 0xa95b50
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
mov dword ptr [ebp+0], edx
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
mov dword ptr [ebp-112], 1
call compare_ball
Lfcb29:
jnp Lfcb31
Lfcb2b:
mov dword ptr [ebp-112], edi
Lfcb31:
mov dword ptr [ebp+112], edi
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
mov dword ptr [ebp-112], edi
mov dword ptr [ebp+112], ecx
jmp finalize
Lfcbdd:
call compare_play
Lfcbe3:
mov edx, dword ptr [0xe602fc]
Lfcbe9:
Lfcbef:
mov dword ptr [ebp-112], edi
Lfcbfa:
jp Lfcc48
Lfcbfc:
test dh, dh
Lfcbfe:
js Lfcc48
Lfcc00:
call compare_ball
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
mov dword ptr [ebp+112], esi
Lfcc46:
jmp Lfcc59
Lfcc48:

Lfcc4e:
push 1
pop esi
Lfcc53:
mov dword ptr [ebp+112], edi
Lfcc59:
cmp ecx, 0xe
Lfcc5c:
jne Lfcc7f
Lfcc5e:
call compare_play
Lfcc6f:
jp Lfcc7f
Lfcc71:
cmp dword ptr [ebx + 0x198], edi
Lfcc77:
mov dword ptr [ebp+224], esi
Lfcc7d:
jne Lfcc85
Lfcc7f:
mov dword ptr [ebp+224], edi
Lfcc85:

Lfccb4:
call 0xabe90
Lfccb9:
test eax, eax
Lfccbb:
je Lfccc3
Lfccbd:
mov dword ptr [ebp+112], esi
Lfccc3:
finalize:
push 1
pop eax
mov dword ptr [ebp-336], eax
mov dword ptr [ebp-224], eax
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
compare_ball:
fld dword ptr [ebp+228]
fcomp dword ptr [ebp+212]
fnstsw ax
test ah, 0x44
ret
compare_play:
fld dword ptr [ebp+4]
fcomp dword ptr [ebp-12]
fnstsw ax
test ah, 0x44
ret
timeout_counter:
push 6
pop ecx
jmp timeout_vertices
.global code_end
code_end:
.org 581, 0x90

# All 112 bytes, including the now obsolete quarter jump table, are pinned.
.section .quarter,"ax"
.global quarter_start
quarter_start:
push ecx
mov edx, dword ptr [0xe602c4]
lea eax, [edx-1]
cmp eax, 3
ja overtime
lea edx, [eax*8+0xe6c3e4]
call 0x30ab0
pop ecx
jmp 0x30f20
overtime:
sub edx, 4
mov dword ptr [esp], edx
push esp
mov edx, 0xe6c4e4
call 0x4a400
pop ecx
ret
.global timeout_update
timeout_update:
pushad
mov eax, dword ptr [0xa95528]
test eax, eax
.byte 0x74
.byte timeout_done - . - 1
cmp dword ptr [eax-0xa0], 0x33544f53
.byte 0x75
.byte timeout_done - . - 1
lea esi, [eax+0x2d20-256+274*10+6]
mov ebx, 0xe5fc28
timeout_side:
xor edx, edx
mov eax, dword ptr [ebx]
test eax, eax
jz timeout_count
mov edx, dword ptr [eax+4]
cmp edx, 3
jbe timeout_count
xor edx, edx
timeout_count:
.byte 0xeb
.byte timeout_row - . - 1
.global quarter_end
quarter_end:
.org 112, 0x90


# Share the two identical retail score formatter tails; fixed entries survive.
.section .scores,"ax"
.global timeout_done, timeout_row
.global home_score
home_score:
mov eax, dword ptr [0xe5fc28]
jmp score_common
timeout_vertices:
and byte ptr [esi+1], 0x0f
or byte ptr [esi+1], dh
add esi, 10
loop timeout_vertices
add bl, 64
jns timeout_side
timeout_done:
popad
ret
.org 32, 0x90
.global away_score
away_score:
mov eax, dword ptr [0xe5fc68]
score_common:
push dword ptr [eax]
push esp
mov edx, 0xe6c410
call 0x4a400
pop ecx
ret
timeout_row:
shl edx, 12
add dh, 0x90
jmp timeout_counter
.global scores_end
scores_end:
.org 64, 0x90

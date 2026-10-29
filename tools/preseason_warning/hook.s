# b779 rc1: the Coach's Desk pre-season warning hook (nfl2k5_preseason_warning.TEMPLATE). Assemble: as --32 hook.s
# The flag (0x11223344) and text (0x55667788) addresses and the four rel32 targets are filled in by code_for().
.intel_syntax noprefix
.code32
.org 0
hook:
  push ecx
  call 0x2486f0
  pop ecx
  cmp dword ptr [0xE576A4], 7
  jne clear
  mov eax, dword ptr [0xE576B4]
  inc eax
  cmp eax, dword ptr [0xE576B0]
  jb clear
  cmp byte ptr [0x11223344], 0
  jne done
  push ecx
  push ebx
  push esi
  call 0x13EC40
  mov esi, eax
  xor ebx, ebx
next:
  cmp ebx, esi
  jae none
  mov ecx, ebx
  call 0x13EBE0
  inc ebx
  test eax, eax
  jz next
  mov dl, byte ptr [eax + 0x11c]
  cmp dl, byte ptr [0x2BF978]
  jbe next
  pop esi
  pop ebx
  pop ecx
  mov byte ptr [0x11223344], 1
  mov edx, 0x55667788
  jmp 0x14E520
none:
  pop esi
  pop ebx
  pop ecx
done:
  ret
clear:
  mov byte ptr [0x11223344], 0
  ret

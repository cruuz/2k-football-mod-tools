/* Career Home handler (job ui1). EXPERIMENTAL / UNWITNESSED. */
.intel_syntax noprefix
.code32
.text
.global home_handler
home_handler:
 /* ECX manager, EDX event (the native dispatcher's fastcall). Every event
  * except the draw goes to MyCareer's own handler unchanged. */
 cmp edx,7
 jne mode_handler
 /* Draw: native F3E90 with MyCareer's handler visible in the top descriptor
  * (its selected-row tint tests it), then restore, then this owner's text. */
 push ecx
 mov eax,DWORD PTR [ecx+0x100]
 mov eax,DWORD PTR [ecx+eax*8]
 push eax
 mov DWORD PTR [eax+8],OFFSET FLAT:mode_handler
 call 0xf3e90
 pop eax
 mov DWORD PTR [eax+8],OFFSET FLAT:home_handler
 pop ecx
 jmp home_draw

.section .note.GNU-stack,"",@progbits

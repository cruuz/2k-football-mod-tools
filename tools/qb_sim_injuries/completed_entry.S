.intel_syntax noprefix
.code32
.section .text
.global route_completed_pass
route_completed_pass:
    pushfd
    cmp byte ptr [FIXTURE_ACTIVE], 0
    je pass_without_franchise_rules
    popfd
    jmp COMPLETED_PASS
pass_without_franchise_rules:
    popfd
    jmp STANDARD_PASS
.section .note.GNU-stack,"",@progbits

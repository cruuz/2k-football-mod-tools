#ifndef VC_STATIC_RUNTIME_APF_GUEST_INSTRUCTION_BUDGET_H
#define VC_STATIC_RUNTIME_APF_GUEST_INSTRUCTION_BUDGET_H

#ifndef __cplusplus
#error "The APF generated-instruction budget bridge is C++-only."
#endif

#include "static_runtime/apf_first_entry_gate.h"

#include <cstddef>
#include <cstdint>

/*
 * Exact translated-code range from the pinned APF XenonRecomp configuration.
 * The upper bound is exclusive.  Import thunks are not guest instructions and
 * are accounted separately by the first-entry function-dispatch ledger.
 */
#define VC_APF_GUEST_CODE_BASE UINT32_C(0x84630000)
#define VC_APF_GUEST_CODE_END_EXCLUSIVE UINT32_C(0x84D0904C)

enum class vc_apf_guest_instruction_stop_reason : std::uint32_t {
    unbound = 1,
    invalid_guest_address,
    budget_exhausted,
    ledger_failure,
};

struct vc_apf_guest_instruction_budget_stop {
    vc_apf_guest_instruction_stop_reason reason;
    vc_apf_first_entry_status ledger_status;
    std::uint32_t guest_address;
    std::uint64_t instructions_consumed;
    std::uint64_t instruction_limit;
};

#define VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY 16u

/*
 * Bounded, thread-local execution evidence for the currently bound ledger.
 * The addresses are returned in chronological order (oldest to newest).
 * This is diagnostic evidence only; it neither authorizes execution nor
 * changes the fail-closed budget semantics.
 */
struct vc_apf_guest_instruction_trace {
    std::uint64_t successful_instruction_count;
    std::uint32_t recent_count;
    std::uint32_t recent_addresses[VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY];
};

/* Bind one ledger to the current isolated execution thread. */
vc_apf_first_entry_status vc_apf_guest_instruction_budget_bind(
    vc_apf_first_entry_budget *budget);

void vc_apf_guest_instruction_budget_unbind();

bool vc_apf_guest_instruction_budget_is_bound();

vc_apf_first_entry_status vc_apf_guest_instruction_budget_snapshot(
    vc_apf_guest_instruction_trace *trace);

/*
 * Consume exactly one unit before the translated body for guest_address.
 * Failure throws vc_apf_guest_instruction_budget_stop, so the body following
 * the injected call cannot perform a guest-visible side effect or transfer.
 */
void vc_apf_guest_instruction_budget_step(std::uint32_t guest_address);

/* Token injected immediately after every audited guest-instruction marker. */
#define VC_APF_GUEST_INSTRUCTION_STEP(guest_address)                         \
    ::vc_apf_guest_instruction_budget_step((guest_address))

#endif

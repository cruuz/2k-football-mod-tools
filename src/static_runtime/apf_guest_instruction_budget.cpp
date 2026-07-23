#include "static_runtime/apf_guest_instruction_budget.h"

namespace {

thread_local vc_apf_first_entry_budget *vc_apf_bound_instruction_budget =
    nullptr;
thread_local std::uint32_t vc_apf_recent_guest_addresses[
    VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY]{};
thread_local std::uint32_t vc_apf_recent_guest_address_count = 0u;
thread_local std::uint32_t vc_apf_recent_guest_address_next = 0u;

[[noreturn]] void stop(vc_apf_guest_instruction_stop_reason reason,
                       vc_apf_first_entry_status status,
                       std::uint32_t guest_address) {
    const std::uint64_t consumed =
        vc_apf_bound_instruction_budget == nullptr
            ? 0u
            : vc_apf_bound_instruction_budget->instructions_consumed;
    const std::uint64_t limit =
        vc_apf_bound_instruction_budget == nullptr
            ? 0u
            : vc_apf_bound_instruction_budget->instruction_limit;
    throw vc_apf_guest_instruction_budget_stop{
        reason, status, guest_address, consumed, limit};
}

bool address_is_valid(std::uint32_t guest_address) {
    return guest_address >= VC_APF_GUEST_CODE_BASE &&
           guest_address < VC_APF_GUEST_CODE_END_EXCLUSIVE &&
           (guest_address & 3u) == 0u;
}

} // namespace

vc_apf_first_entry_status vc_apf_guest_instruction_budget_bind(
    vc_apf_first_entry_budget *budget) {
    if (budget == nullptr || vc_apf_bound_instruction_budget != nullptr ||
        budget->instruction_limit == 0u ||
        budget->function_dispatch_limit == 0u || budget->exhausted ||
        budget->instructions_consumed > budget->instruction_limit ||
        budget->function_dispatches_consumed >
            budget->function_dispatch_limit) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    vc_apf_bound_instruction_budget = budget;
    vc_apf_recent_guest_address_count = 0u;
    vc_apf_recent_guest_address_next = 0u;
    for (std::uint32_t &address : vc_apf_recent_guest_addresses) {
        address = 0u;
    }
    return VC_APF_FIRST_ENTRY_OK;
}

void vc_apf_guest_instruction_budget_unbind() {
    vc_apf_bound_instruction_budget = nullptr;
}

bool vc_apf_guest_instruction_budget_is_bound() {
    return vc_apf_bound_instruction_budget != nullptr;
}

vc_apf_first_entry_status vc_apf_guest_instruction_budget_snapshot(
    vc_apf_guest_instruction_trace *trace) {
    std::uint32_t oldest;

    if (trace == nullptr || vc_apf_bound_instruction_budget == nullptr) {
        return VC_APF_FIRST_ENTRY_INVALID_ARGUMENT;
    }
    *trace = vc_apf_guest_instruction_trace{};
    trace->successful_instruction_count =
        vc_apf_bound_instruction_budget->instructions_consumed;
    trace->recent_count = vc_apf_recent_guest_address_count;
    oldest = vc_apf_recent_guest_address_count <
                     VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY
                 ? 0u
                 : vc_apf_recent_guest_address_next;
    for (std::uint32_t index = 0u;
         index < vc_apf_recent_guest_address_count; ++index) {
        trace->recent_addresses[index] = vc_apf_recent_guest_addresses[
            (oldest + index) % VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY];
    }
    return VC_APF_FIRST_ENTRY_OK;
}

void vc_apf_guest_instruction_budget_step(std::uint32_t guest_address) {
    vc_apf_first_entry_status status;

    if (vc_apf_bound_instruction_budget == nullptr) {
        stop(vc_apf_guest_instruction_stop_reason::unbound,
             VC_APF_FIRST_ENTRY_NOT_AUTHORIZED, guest_address);
    }
    if (!address_is_valid(guest_address)) {
        stop(vc_apf_guest_instruction_stop_reason::invalid_guest_address,
             VC_APF_FIRST_ENTRY_INVALID_ARGUMENT, guest_address);
    }
    status = vc_apf_first_entry_consume_budget(
        vc_apf_bound_instruction_budget, 1u, 0u);
    if (status == VC_APF_FIRST_ENTRY_BUDGET_EXHAUSTED) {
        stop(vc_apf_guest_instruction_stop_reason::budget_exhausted, status,
             guest_address);
    }
    if (status != VC_APF_FIRST_ENTRY_OK) {
        stop(vc_apf_guest_instruction_stop_reason::ledger_failure, status,
             guest_address);
    }
    vc_apf_recent_guest_addresses[vc_apf_recent_guest_address_next] =
        guest_address;
    vc_apf_recent_guest_address_next =
        (vc_apf_recent_guest_address_next + 1u) %
        VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY;
    if (vc_apf_recent_guest_address_count <
        VC_APF_GUEST_INSTRUCTION_TRACE_CAPACITY) {
        ++vc_apf_recent_guest_address_count;
    }
}

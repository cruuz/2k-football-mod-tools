#include "static_runtime/apf_guest_instruction_budget.h"

#include <cstdio>
#include <cstring>

#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            std::fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__, \
                         __LINE__, #condition);                              \
            return 1;                                                        \
        }                                                                    \
    } while (0)

namespace {

void reset_budget(vc_apf_first_entry_budget &budget, std::uint64_t limit) {
    std::memset(&budget, 0, sizeof(budget));
    budget.instruction_limit = limit;
    budget.function_dispatch_limit = 17u;
}

void synthetic_two_instruction_body(unsigned int &effect) {
    VC_APF_GUEST_INSTRUCTION_STEP(0x84630000u);
    effect = 1u;
    VC_APF_GUEST_INSTRUCTION_STEP(0x84630004u);
    effect = 2u;
}

void synthetic_target(unsigned int &effect) {
    VC_APF_GUEST_INSTRUCTION_STEP(0x84630010u);
    effect = 3u;
}

void synthetic_branch(unsigned int &effect) {
    VC_APF_GUEST_INSTRUCTION_STEP(0x84630008u);
    synthetic_target(effect);
}

} // namespace

int main() {
    vc_apf_first_entry_budget budget{};
    vc_apf_guest_instruction_trace trace{};
    unsigned int effect = 0u;
    bool caught = false;

    CHECK(!vc_apf_guest_instruction_budget_is_bound());
    CHECK(vc_apf_guest_instruction_budget_snapshot(&trace) ==
          VC_APF_FIRST_ENTRY_INVALID_ARGUMENT);
    try {
        synthetic_two_instruction_body(effect);
    } catch (const vc_apf_guest_instruction_budget_stop &stop) {
        caught = stop.reason ==
                     vc_apf_guest_instruction_stop_reason::unbound &&
                 stop.ledger_status == VC_APF_FIRST_ENTRY_NOT_AUTHORIZED &&
                 stop.guest_address == 0x84630000u &&
                 stop.instructions_consumed == 0u &&
                 stop.instruction_limit == 0u;
    }
    CHECK(caught);
    CHECK(effect == 0u);

    reset_budget(budget, 1u);
    CHECK(vc_apf_guest_instruction_budget_bind(&budget) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(vc_apf_guest_instruction_budget_is_bound());
    CHECK(vc_apf_guest_instruction_budget_bind(&budget) ==
          VC_APF_FIRST_ENTRY_INVALID_ARGUMENT);
    caught = false;
    try {
        synthetic_two_instruction_body(effect);
    } catch (const vc_apf_guest_instruction_budget_stop &stop) {
        caught = stop.reason ==
                     vc_apf_guest_instruction_stop_reason::budget_exhausted &&
                 stop.ledger_status == VC_APF_FIRST_ENTRY_BUDGET_EXHAUSTED &&
                 stop.guest_address == 0x84630004u &&
                 stop.instructions_consumed == 1u &&
                 stop.instruction_limit == 1u;
    }
    CHECK(caught);
    CHECK(effect == 1u);
    CHECK(budget.instructions_consumed == 1u);
    CHECK(budget.function_dispatches_consumed == 0u);
    CHECK(budget.exhausted);
    CHECK(vc_apf_guest_instruction_budget_snapshot(&trace) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(trace.successful_instruction_count == 1u);
    CHECK(trace.recent_count == 1u);
    CHECK(trace.recent_addresses[0] == 0x84630000u);
    vc_apf_guest_instruction_budget_unbind();

    effect = 0u;
    reset_budget(budget, 1u);
    CHECK(vc_apf_guest_instruction_budget_bind(&budget) ==
          VC_APF_FIRST_ENTRY_OK);
    caught = false;
    try {
        synthetic_branch(effect);
    } catch (const vc_apf_guest_instruction_budget_stop &stop) {
        caught = stop.reason ==
                     vc_apf_guest_instruction_stop_reason::budget_exhausted &&
                 stop.guest_address == 0x84630010u;
    }
    CHECK(caught);
    CHECK(effect == 0u);
    CHECK(budget.instructions_consumed == 1u);
    vc_apf_guest_instruction_budget_unbind();

    reset_budget(budget, 3u);
    CHECK(vc_apf_guest_instruction_budget_bind(&budget) ==
          VC_APF_FIRST_ENTRY_OK);
    caught = false;
    try {
        VC_APF_GUEST_INSTRUCTION_STEP(0x84630002u);
    } catch (const vc_apf_guest_instruction_budget_stop &stop) {
        caught = stop.reason ==
                     vc_apf_guest_instruction_stop_reason::invalid_guest_address &&
                 stop.ledger_status == VC_APF_FIRST_ENTRY_INVALID_ARGUMENT &&
                 stop.instructions_consumed == 0u;
    }
    CHECK(caught);
    CHECK(!budget.exhausted);
    CHECK(budget.instructions_consumed == 0u);
    vc_apf_guest_instruction_budget_unbind();

    reset_budget(budget, 3u);
    CHECK(vc_apf_guest_instruction_budget_bind(&budget) ==
          VC_APF_FIRST_ENTRY_OK);
    for (unsigned int iteration = 0u; iteration < 3u; ++iteration) {
        VC_APF_GUEST_INSTRUCTION_STEP(0x84630020u);
    }
    CHECK(vc_apf_guest_instruction_budget_snapshot(&trace) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(trace.successful_instruction_count == 3u);
    CHECK(trace.recent_count == 3u);
    CHECK(trace.recent_addresses[0] == 0x84630020u);
    CHECK(trace.recent_addresses[2] == 0x84630020u);
    CHECK(budget.instructions_consumed == 3u);
    CHECK(!budget.exhausted);
    caught = false;
    try {
        VC_APF_GUEST_INSTRUCTION_STEP(0x84630020u);
    } catch (const vc_apf_guest_instruction_budget_stop &stop) {
        caught = stop.reason ==
                     vc_apf_guest_instruction_stop_reason::budget_exhausted &&
                 stop.instructions_consumed == 3u;
    }
    CHECK(caught);
    CHECK(budget.instructions_consumed == 3u);
    CHECK(budget.function_dispatches_consumed == 0u);
    vc_apf_guest_instruction_budget_unbind();

    CHECK(!vc_apf_guest_instruction_budget_is_bound());
    std::printf("APF_GUEST_INSTRUCTION_BUDGET_RUNTIME_PASS "
                "unbound_stop=1 exact_limit=1 pre_effect_stop=1 "
                "pre_transfer_stop=1 loop_dynamic=4 invalid_address=1\n");
    return 0;
}

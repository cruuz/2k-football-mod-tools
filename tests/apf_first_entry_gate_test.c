#include "static_runtime/apf_first_entry_gate.h"

#include <signal.h>
#include <stdio.h>
#include <string.h>

#define CHECK(condition)                                                     \
    do {                                                                     \
        if (!(condition)) {                                                  \
            fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__,       \
                    __LINE__, #condition);                                   \
            return 1;                                                        \
        }                                                                    \
    } while (0)

static int child_return(void *opaque) {
    return *(const int *)opaque;
}

static int child_signal(void *opaque) {
    (void)opaque;
    (void)raise(SIGKILL);
    return 0;
}

static int child_spin(void *opaque) {
    volatile unsigned int *value = opaque;
    for (;;) {
        *value = *value + 1u;
    }
    return 0;
}

int main(void) {
    const vc_apf_first_entry_import_binding *bindings;
    vc_apf_first_entry_budget budget;
    vc_apf_first_entry_state state;
    vc_apf_first_entry_readiness_result readiness;
    vc_apf_first_entry_child_result child;
    size_t binding_count = 0u;
    size_t left;
    size_t right;
    size_t resumable = 0u;
    size_t terminal = 0u;
    size_t exception_required = 0u;
    size_t thread_create_required = 0u;
    int child_value = 37;
    volatile unsigned int spin_value = 0u;

    bindings = vc_apf_first_entry_bindings(&binding_count);
    CHECK(bindings != NULL);
    CHECK(binding_count == VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT);
    for (left = 0u; left < binding_count; ++left) {
        CHECK(bindings[left].name != NULL);
        CHECK(bindings[left].thunk_address >=
              VC_APF_RETAIL_IMPORT_THUNK_BASE);
        CHECK(bindings[left].thunk_address <
              VC_APF_RETAIL_IMPORT_THUNK_BASE +
                  VC_APF_RETAIL_IMPORT_THUNK_SPAN);
        for (right = left + 1u; right < binding_count; ++right) {
            CHECK(bindings[left].thunk_address !=
                  bindings[right].thunk_address);
            CHECK(strcmp(bindings[left].name, bindings[right].name) != 0);
        }
        switch (bindings[left].classification) {
        case VC_APF_FIRST_ENTRY_IMPORT_RESUMABLE:
            ++resumable;
            break;
        case VC_APF_FIRST_ENTRY_IMPORT_TERMINAL:
            ++terminal;
            break;
        case VC_APF_FIRST_ENTRY_IMPORT_EXCEPTION_REQUIRED:
            ++exception_required;
            break;
        case VC_APF_FIRST_ENTRY_IMPORT_THREAD_CREATE_REQUIRED:
            ++thread_create_required;
            break;
        default:
            CHECK(false);
        }
    }
    CHECK(resumable == 24u);
    CHECK(terminal == 4u);
    CHECK(exception_required == 1u);
    CHECK(thread_create_required == 1u);

    memset(&budget, 0, sizeof(budget));
    budget.instruction_limit = 5u;
    budget.function_dispatch_limit = 2u;
    CHECK(vc_apf_first_entry_consume_budget(&budget, 3u, 1u) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(budget.instructions_consumed == 3u);
    CHECK(budget.function_dispatches_consumed == 1u);
    CHECK(vc_apf_first_entry_consume_budget(&budget, 2u, 1u) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(budget.instructions_consumed == 5u);
    CHECK(budget.function_dispatches_consumed == 2u);
    CHECK(vc_apf_first_entry_consume_budget(&budget, 1u, 0u) ==
          VC_APF_FIRST_ENTRY_BUDGET_EXHAUSTED);
    CHECK(budget.exhausted);
    CHECK(vc_apf_first_entry_consume_budget(&budget, 0u, 0u) ==
          VC_APF_FIRST_ENTRY_BUDGET_EXHAUSTED);

    vc_apf_first_entry_state_init(&state);
    vc_apf_first_entry_readiness(&state, &readiness);
    CHECK(!readiness.entry_call_authorized);
    CHECK(!readiness.entry_called);
    CHECK(!readiness.exact_first_boundary_proved);
    CHECK(readiness.child_containment_available);
    CHECK(readiness.function_budget_ledger_available);
    CHECK(readiness.instruction_budget_ledger_available);
    CHECK(readiness.blocker_count == 3u);
    CHECK(readiness.blockers[0] ==
          VC_APF_FIRST_ENTRY_BLOCKER_COMPOSED_DERIVED_CORPUS);
    CHECK(readiness.blockers[1] ==
          VC_APF_FIRST_ENTRY_BLOCKER_GENERATED_DISPATCH_BRIDGE_LINK);
    CHECK(readiness.blockers[2] ==
          VC_APF_FIRST_ENTRY_BLOCKER_INSTRUCTION_BUDGET_INSTRUMENTATION);
    vc_apf_first_entry_destroy(&state);

    CHECK(vc_apf_first_entry_run_contained(
              child_return, &child_value, 1000u, &child) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(child.outcome == VC_APF_FIRST_ENTRY_CHILD_EXITED);
    CHECK(child.callback_result == child_value);
    CHECK(child.signal_number == 0);

    CHECK(vc_apf_first_entry_run_contained(
              child_signal, NULL, 1000u, &child) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(child.outcome == VC_APF_FIRST_ENTRY_CHILD_SIGNALED);
    CHECK(child.signal_number == SIGKILL);

    CHECK(vc_apf_first_entry_run_contained(
              child_spin, (void *)&spin_value, 25u, &child) ==
          VC_APF_FIRST_ENTRY_OK);
    CHECK(child.outcome == VC_APF_FIRST_ENTRY_CHILD_TIMED_OUT);
    CHECK(child.signal_number == SIGKILL);

    CHECK(strcmp(vc_apf_first_entry_status_name(
                     VC_APF_FIRST_ENTRY_NOT_AUTHORIZED),
                 "not_authorized") == 0);
    CHECK(strcmp(vc_apf_first_entry_blocker_name(
                     VC_APF_FIRST_ENTRY_BLOCKER_COMPOSED_DERIVED_CORPUS),
                 "composed_derived_corpus") == 0);

    printf("APF_FIRST_ENTRY_GATE_PASS bindings=%zu resumable=%zu "
           "terminal=%zu exception=%zu thread_create=%zu blockers=%zu "
           "entry_authorized=0 entry_called=0 containment=3\n",
           binding_count, resumable, terminal, exception_required,
           thread_create_required, readiness.blocker_count);
    return 0;
}

#ifndef VC_STATIC_RUNTIME_APF_FIRST_ENTRY_XENON_BRIDGE_H
#define VC_STATIC_RUNTIME_APF_FIRST_ENTRY_XENON_BRIDGE_H

#ifndef __cplusplus
#error "The APF Xenon bridge is C++-only."
#endif

#include "static_runtime/apf_first_entry_gate.h"

#include <cstddef>
#include <cstdint>

struct PPCContext;
struct PPCFuncMapping;

struct vc_apf_first_entry_boundary_stop {
    vc_apf_first_entry_status gate_status;
    vc_apf_boot_leaf_status adapter_status;
    std::uint32_t import_thunk;
};

/* Bind one prepared gate to the current isolated child thread. */
vc_apf_first_entry_status vc_apf_first_entry_xenon_bridge_bind(
    vc_apf_first_entry_state *state);

void vc_apf_first_entry_xenon_bridge_unbind();

/* Zero all generated PPC architectural state, then install the loader SP. */
vc_apf_first_entry_status vc_apf_first_entry_xenon_context_init(
    PPCContext *context);

/*
 * Install the exact generated address-to-host-function mappings into the
 * guest-side XenonRecomp lookup span.  This writes no title bytes and calls no
 * generated function.
 */
vc_apf_first_entry_status vc_apf_first_entry_xenon_install_dispatch(
    vc_apf_first_entry_state *state,
    const PPCFuncMapping *mappings,
    std::size_t expected_mapping_count);

#endif

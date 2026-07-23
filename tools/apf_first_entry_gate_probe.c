#define _POSIX_C_SOURCE 200809L

#include "static_runtime/apf_first_entry_gate.h"

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int read_exact(int descriptor, uint8_t *bytes, size_t byte_count) {
    size_t offset = 0u;

    while (offset < byte_count) {
        ssize_t count = read(descriptor, bytes + offset, byte_count - offset);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count <= 0) {
            return -1;
        }
        offset += (size_t)count;
    }
    return 0;
}

static uint8_t *read_decoded_image(const char *path) {
    uint8_t *bytes;
    struct stat metadata;
    int descriptor = open(path, O_RDONLY);

    if (descriptor < 0 || fstat(descriptor, &metadata) != 0 ||
        metadata.st_size != (off_t)VC_APF_IMPORTED_DATA_IMAGE_SIZE) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        return NULL;
    }
    bytes = malloc(VC_APF_IMPORTED_DATA_IMAGE_SIZE);
    if (bytes == NULL ||
        read_exact(descriptor, bytes, VC_APF_IMPORTED_DATA_IMAGE_SIZE) != 0) {
        free(bytes);
        (void)close(descriptor);
        return NULL;
    }
    (void)close(descriptor);
    return bytes;
}

static int read_xex_prefix(const char *path,
                           uint8_t prefix[VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE]) {
    int descriptor = open(path, O_RDONLY);
    int status;

    if (descriptor < 0) {
        return -1;
    }
    status = read_exact(descriptor, prefix,
                        VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE);
    (void)close(descriptor);
    return status;
}

int main(int argc, char **argv) {
    vc_apf_first_entry_config config;
    vc_apf_first_entry_state state;
    vc_apf_first_entry_readiness_result readiness;
    vc_apf_first_entry_status status;
    uint8_t *decoded;
    uint8_t prefix[VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE];

    if (argc != 3) {
        fprintf(stderr, "usage: %s DECODED_PE DEFAULT_XEX\n", argv[0]);
        return 2;
    }
    decoded = read_decoded_image(argv[1]);
    if (decoded == NULL || read_xex_prefix(argv[2], prefix) != 0) {
        fprintf(stderr, "failed to read exact APF inputs\n");
        free(decoded);
        return 3;
    }

    memset(&config, 0, sizeof(config));
    config.decoded_image_bytes = decoded;
    config.decoded_image_byte_count = VC_APF_IMPORTED_DATA_IMAGE_SIZE;
    config.raw_xex_prefix_bytes = prefix;
    config.raw_xex_prefix_byte_count = sizeof(prefix);
    config.policy.configured_fields = VC_APF_BOOT_CONFIG_ALL;
    config.policy.process_type = 1u;
    config.policy.language = 1u;
    config.policy.av_pack = 6u;
    config.policy.executable_system_flags = 0x00000200u;
    config.policy.secured_av_region = 0u;
    config.policy.user_video_flags = 0u;
    config.policy.vm_arena_base = 0x40000000u;
    config.policy.vm_arena_size = 0x10000000u;
    config.instruction_budget = UINT64_C(1000000);
    config.function_dispatch_budget = UINT64_C(100000);

    vc_apf_first_entry_state_init(&state);
    status = vc_apf_first_entry_prepare(&state, &config);
    if (status != VC_APF_FIRST_ENTRY_OK) {
        fprintf(stderr, "prepare failed: %s\n",
                vc_apf_first_entry_status_name(status));
        free(decoded);
        return 4;
    }
    status = vc_apf_first_entry_probe_expected_boundary(&state);
    if (status != VC_APF_FIRST_ENTRY_OK) {
        fprintf(stderr, "typed-boundary probe failed: %s\n",
                vc_apf_first_entry_status_name(status));
        vc_apf_first_entry_destroy(&state);
        free(decoded);
        return 5;
    }
    vc_apf_first_entry_readiness(&state, &readiness);
    if (state.guest_address_space == NULL || !state.prepared ||
        state.guest_address_space_byte_count !=
            (size_t)VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE ||
        state.loader_context.gpr[1] != VC_APF_FIRST_ENTRY_STACK_TOP ||
        state.binding_count != VC_APF_FIRST_ENTRY_FRONTIER_IMPORT_COUNT ||
        state.imported_data.seeded_slot_count != 2u ||
        state.imported_data.preserved_ordinal_slot_count != 11u ||
        !readiness.exact_first_boundary_proved ||
        !readiness.first_boundary_adapter_probed ||
        readiness.blocker_count != 3u || readiness.entry_call_authorized ||
        readiness.entry_called) {
        fprintf(stderr, "prepared-state invariant failed\n");
        vc_apf_first_entry_destroy(&state);
        free(decoded);
        return 6;
    }

    printf("APF_FIRST_ENTRY_PROBE_PASS mapped_bytes=%llu image_bytes=%u "
           "raw_header_bytes=%u seeded_imports=%u preserved_ordinals=%u "
           "stack_top=0x%08X bindings=%zu first_call=0x%08X "
           "first_return=0x%08X first_thunk=0x%08X adapter_status=%s "
           "blockers=%zu entry_authorized=0 entry_called=0\n",
           (unsigned long long)VC_APF_FIRST_ENTRY_GUEST_ADDRESS_SPACE_SIZE,
           VC_APF_IMPORTED_DATA_IMAGE_SIZE,
           VC_APF_IMPORTED_DATA_XEX_PREFIX_SIZE,
           state.imported_data.seeded_slot_count,
           state.imported_data.preserved_ordinal_slot_count,
           VC_APF_FIRST_ENTRY_STACK_TOP, state.binding_count,
           VC_APF_FIRST_ENTRY_FIRST_IMPORT_CALL,
           VC_APF_FIRST_ENTRY_FIRST_IMPORT_RETURN,
           VC_APF_FIRST_ENTRY_FIRST_IMPORT_THUNK,
           vc_apf_boot_leaf_status_name(
               state.first_boundary_adapter_status),
           readiness.blocker_count);

    vc_apf_first_entry_destroy(&state);
    free(decoded);
    return 0;
}

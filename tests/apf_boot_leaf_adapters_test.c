#include "static_runtime/apf_boot_leaf_adapters.h"

#include <stdio.h>
#include <string.h>

#define CHECK(condition)                                                       \
    do {                                                                       \
        if (!(condition)) {                                                     \
            fprintf(stderr, "CHECK failed at %s:%d: %s\n", __FILE__, __LINE__, \
                    #condition);                                                \
            return 1;                                                          \
        }                                                                      \
    } while (0)

static vc_apf_boot_leaf_status call_import(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context,
    uint32_t thunk,
    uint32_t r3,
    uint32_t r4,
    uint32_t r5) {
    context->gpr[3] = r3;
    context->gpr[4] = r4;
    context->gpr[5] = r5;
    context->gpr[6] = 0u;
    context->gpr[7] = 0u;
    return vc_apf_boot_leaf_dispatch(runtime, thread, memory, context, thunk);
}

static vc_apf_boot_leaf_status call_import7(
    vc_apf_boot_leaf_runtime *runtime,
    vc_apf_guest_thread *thread,
    const vc_apf_guest_memory *memory,
    vc_apf_guest_ppc_context *context,
    uint32_t thunk,
    uint32_t r3,
    uint32_t r4,
    uint32_t r5,
    uint32_t r6,
    uint32_t r7) {
    context->gpr[3] = r3;
    context->gpr[4] = r4;
    context->gpr[5] = r5;
    context->gpr[6] = r6;
    context->gpr[7] = r7;
    return vc_apf_boot_leaf_dispatch(runtime, thread, memory, context, thunk);
}

static uint16_t load_be_u16(const uint8_t *bytes) {
    return (uint16_t)(((uint16_t)bytes[0] << 8u) | bytes[1]);
}

static uint32_t load_be_u32(const uint8_t *bytes) {
    return ((uint32_t)bytes[0] << 24u) | ((uint32_t)bytes[1] << 16u) |
           ((uint32_t)bytes[2] << 8u) | bytes[3];
}

static void store_be_u32(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)(value >> 24u);
    bytes[1] = (uint8_t)(value >> 16u);
    bytes[2] = (uint8_t)(value >> 8u);
    bytes[3] = (uint8_t)value;
}

static void store_be_u16(uint8_t *bytes, uint16_t value) {
    bytes[0] = (uint8_t)(value >> 8u);
    bytes[1] = (uint8_t)value;
}

static void store_be_u64(uint8_t *bytes, uint64_t value) {
    store_be_u32(bytes, (uint32_t)(value >> 32u));
    store_be_u32(bytes + 4u, (uint32_t)value);
}

static void store_be_utf16_ascii(uint8_t *bytes, const char *text) {
    size_t index = 0u;

    while (text[index] != '\0') {
        store_be_u16(bytes + index * 2u,
                     (uint16_t)(uint8_t)text[index]);
        ++index;
    }
    store_be_u16(bytes + index * 2u, 0u);
}

int main(void) {
    static uint8_t long_ansi_bytes[65552];
    static uint8_t vm_backing[0x00400000u];
    static uint8_t ui_guest_bytes[2048];
    static uint8_t thread_guest_bytes[512];
    vc_apf_boot_leaf_runtime runtime;
    vc_apf_guest_thread thread_a;
    vc_apf_guest_thread thread_b;
    vc_apf_guest_thread duplicate_identity_thread;
    vc_apf_guest_thread unregistered_thread;
    vc_apf_guest_ppc_context context;
    vc_apf_guest_ppc_context thread_b_context;
    vc_apf_guest_ppc_context exception_snapshot;
    vc_apf_guest_ppc_context ui_context;
    vc_apf_guest_ppc_context ui_context_snapshot;
    vc_apf_guest_ppc_context ui_resume_context;
    vc_apf_guest_ppc_context ui_resume_snapshot;
    vc_apf_guest_ppc_context thread_create_context;
    vc_apf_guest_ppc_context thread_create_snapshot;
    vc_apf_boot_leaf_config config;
    uint8_t guest_bytes[256];
    uint8_t dbg_format_bytes[VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_SIZE];
    uint8_t retail_xex_prefix[VC_APF_RETAIL_XEX_PREFIX_SIZE];
    uint8_t ansi_snapshot[VC_APF_ANSI_STRING_SIZE];
    uint8_t critical_snapshot[VC_APF_RTL_CRITICAL_SECTION_SIZE];
    uint8_t vm_information_snapshot[VC_APF_MEMORY_BASIC_INFORMATION_SIZE];
    uint8_t thread_create_bytes_snapshot[sizeof(thread_guest_bytes)];
    vc_apf_guest_memory memory;
    vc_apf_guest_memory dbg_memory;
    vc_apf_guest_memory retail_xex_memory;
    vc_apf_guest_memory long_ansi_memory;
    vc_apf_guest_memory ui_memory;
    vc_apf_guest_memory ui_truncated_memory;
    vc_apf_guest_memory thread_create_memory;
    vc_apf_guest_memory thread_create_truncated_memory;
    vc_apf_boot_debug_event debug_event_snapshot;
    vc_apf_boot_message_box_request ui_request_snapshot;
    vc_apf_boot_thread_create_request thread_create_request_snapshot;
    uint32_t slot;
    uint32_t i;
    uint32_t event_handle;
    uint32_t named_event_handle;
    uint32_t ui_request_id;
    const uint32_t ui_stack_pointer = 0x20000100u;
    const size_t ui_stack_offset = 0x100u;
    const uint32_t thread_create_stack_pointer = 0x30000100u;
    const size_t thread_create_stack_offset = 0x100u;
    const uint32_t thread_create_start_context = 0x30000020u;
    uint32_t event_handles[VC_APF_BOOT_MAX_EVENT_HANDLES];
    static const uint32_t retail_xex_options
        [VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT][2] = {
            {0x000002FFu, 0x00004F54u}, {0x000003FFu, 0x00004F68u},
            {0x00010100u, 0x84BE9D08u}, {0x00010201u, 0x82000000u},
            {0x000103FFu, 0x000064E8u}, {0x00018002u, 0x00004F8Cu},
            {0x000183FFu, 0x00004F94u}, {0x000200FFu, 0x00004FBCu},
            {0x00020104u, 0x00005070u}, {0x00020200u, 0x00200000u},
            {0x00030000u, 0x00000200u}, {0x00040006u, 0x00005080u},
            {0x00040310u, 0x00005098u}, {0x00040404u, 0x000050D8u},
            {0x000405FFu, 0x000050E8u},
        };
    memset(&runtime, 0, sizeof(runtime));
    memset(&thread_a, 0, sizeof(thread_a));
    memset(&thread_b, 0, sizeof(thread_b));
    memset(&duplicate_identity_thread, 0, sizeof(duplicate_identity_thread));
    memset(&unregistered_thread, 0, sizeof(unregistered_thread));
    memset(&context, 0, sizeof(context));
    memset(&thread_b_context, 0, sizeof(thread_b_context));
    memset(&exception_snapshot, 0, sizeof(exception_snapshot));
    memset(&ui_context, 0, sizeof(ui_context));
    memset(&ui_context_snapshot, 0, sizeof(ui_context_snapshot));
    memset(&ui_resume_context, 0, sizeof(ui_resume_context));
    memset(&ui_resume_snapshot, 0, sizeof(ui_resume_snapshot));
    memset(&ui_request_snapshot, 0, sizeof(ui_request_snapshot));
    memset(&thread_create_context, 0, sizeof(thread_create_context));
    memset(&thread_create_snapshot, 0, sizeof(thread_create_snapshot));
    memset(&thread_create_request_snapshot, 0,
           sizeof(thread_create_request_snapshot));
    memset(&config, 0, sizeof(config));
    vc_apf_boot_leaf_thread_init(&thread_a);
    vc_apf_boot_leaf_thread_init(&thread_b);
    vc_apf_boot_leaf_thread_init(&duplicate_identity_thread);
    vc_apf_boot_leaf_thread_init(&unregistered_thread);

    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.configured_fields = VC_APF_BOOT_CONFIG_ALL;
    config.process_type = 3u;
    config.language = 1u;
    config.av_pack = 6u;
    config.executable_system_flags = 0x00000200u;
    config.secured_av_region = 0x00000300u;
    config.user_video_flags = 0x00800000u;
    config.vm_arena_base = 0x40000000u;
    config.vm_arena_size = sizeof(vm_backing);
    config.vm_backing_bytes = vm_backing;
    config.vm_backing_byte_count = sizeof(vm_backing);
    config.vm_existing_range_count = 4u;
    config.vm_existing_ranges[0].guest_base = VC_APF_RETAIL_TITLE_BASE;
    config.vm_existing_ranges[0].byte_count = VC_APF_RETAIL_TITLE_SIZE;
    config.vm_existing_ranges[0].kind = VC_APF_BOOT_VM_RANGE_TITLE_IMAGE;
    config.vm_existing_ranges[1].guest_base = VC_APF_STATIC_DISPATCH_BASE;
    config.vm_existing_ranges[1].byte_count = VC_APF_STATIC_DISPATCH_SIZE;
    config.vm_existing_ranges[1].kind =
        VC_APF_BOOT_VM_RANGE_STATIC_DISPATCH;
    config.vm_existing_ranges[2].guest_base =
        VC_APF_RETAIL_IMPORT_THUNK_BASE;
    config.vm_existing_ranges[2].byte_count =
        VC_APF_RETAIL_IMPORT_THUNK_SPAN;
    config.vm_existing_ranges[2].kind = VC_APF_BOOT_VM_RANGE_IMPORT_THUNKS;
    config.vm_existing_ranges[3].guest_base = 0x403F1000u;
    config.vm_existing_ranges[3].byte_count = 0x00000100u;
    config.vm_existing_ranges[3].kind = VC_APF_BOOT_VM_RANGE_OTHER_MAPPING;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.process_type = 1u;
    config.language = 13u;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.language = 1u;
    config.configured_fields &= ~VC_APF_BOOT_CONFIG_SECURED_AV_REGION;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.configured_fields = VC_APF_BOOT_CONFIG_ALL;
    config.vm_existing_ranges[2].kind = VC_APF_BOOT_VM_RANGE_OTHER_MAPPING;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.vm_existing_ranges[2].kind = VC_APF_BOOT_VM_RANGE_IMPORT_THUNKS;
    config.vm_existing_ranges[1].byte_count =
        VC_APF_STATIC_DISPATCH_SIZE - 1u;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.vm_existing_ranges[1].byte_count = VC_APF_STATIC_DISPATCH_SIZE;
    config.vm_arena_base = VC_APF_RETAIL_TITLE_BASE;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.vm_arena_base = 0x40000000u;
    config.vm_backing_byte_count = sizeof(vm_backing) - 1u;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.vm_backing_byte_count = sizeof(vm_backing);
    config.vm_arena_base += 1u;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    config.vm_arena_base -= 1u;
    CHECK(vc_apf_boot_leaf_runtime_init(&runtime, &config) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.vm_page_count == 64u);
    CHECK(runtime.vm_pages[63].state != 0u);

    CHECK(vc_apf_boot_leaf_thread_attach(&runtime, &thread_a, 0x90001000u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(vc_apf_boot_leaf_thread_attach(&runtime, &thread_a, 0x90001000u) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    CHECK(vc_apf_boot_leaf_thread_attach(&runtime,
                                         &duplicate_identity_thread,
                                         0x90001000u) ==
          VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    CHECK(duplicate_identity_thread.owner == NULL);
    CHECK(runtime.thread_count == 1u);
    CHECK(vc_apf_boot_leaf_thread_attach(&runtime, &thread_b, 0x90002000u) ==
          VC_APF_BOOT_LEAF_OK);
    unregistered_thread.owner = &runtime;
    CHECK(call_import(&runtime, &unregistered_thread, NULL, &context,
                      VC_APF_THUNK_XGET_LANGUAGE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_THREAD_REQUIRED);
    unregistered_thread.owner = NULL;

    memset(guest_bytes, 0, sizeof(guest_bytes));
    memory.bytes = guest_bytes;
    memory.guest_base = 0x00001000u;
    memory.byte_count = sizeof(guest_bytes);

    memset(ui_guest_bytes, 0, sizeof(ui_guest_bytes));
    ui_memory.bytes = ui_guest_bytes;
    ui_memory.guest_base = 0x20000000u;
    ui_memory.byte_count = sizeof(ui_guest_bytes);
    ui_truncated_memory = ui_memory;

    memset(thread_guest_bytes, 0, sizeof(thread_guest_bytes));
    thread_create_memory.bytes = thread_guest_bytes;
    thread_create_memory.guest_base = 0x30000000u;
    thread_create_memory.byte_count = sizeof(thread_guest_bytes);
    thread_create_truncated_memory = thread_create_memory;

    memcpy(dbg_format_bytes, "[XAPI RETURN VALUE] %d\n",
           sizeof(dbg_format_bytes));
    dbg_memory.bytes = dbg_format_bytes;
    dbg_memory.guest_base = VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS;
    dbg_memory.byte_count = sizeof(dbg_format_bytes);

    memset(retail_xex_prefix, 0, sizeof(retail_xex_prefix));
    store_be_u32(retail_xex_prefix, 0x58455832u);
    store_be_u32(retail_xex_prefix + 4u, 0x00000001u);
    store_be_u32(retail_xex_prefix + 8u, 0x00007000u);
    store_be_u32(retail_xex_prefix + 12u, 0u);
    store_be_u32(retail_xex_prefix + 16u, 0x00000090u);
    store_be_u32(retail_xex_prefix + 20u,
                 VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT);
    for (i = 0u; i < VC_APF_RETAIL_XEX_OPTIONAL_HEADER_COUNT; ++i) {
        store_be_u32(retail_xex_prefix + 24u + (size_t)i * 8u,
                     retail_xex_options[i][0]);
        store_be_u32(retail_xex_prefix + 28u + (size_t)i * 8u,
                     retail_xex_options[i][1]);
    }
    retail_xex_memory.bytes = retail_xex_prefix;
    retail_xex_memory.guest_base = 0x90010000u;
    retail_xex_memory.byte_count = sizeof(retail_xex_prefix);

    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_GET_CURRENT_PROCESS_TYPE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 1u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XGET_LANGUAGE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 1u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XGET_AV_PACK, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 6u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE, 9u, 0u,
                      0u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 1u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE, 10u, 0u,
                      0u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);

    context.lr = 0x84BE9B88u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_EX_GET_XCONFIG_SETTING, 2u, 2u,
                       0x00001014u, 4u, 0x00001010u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);
    CHECK(load_be_u32(guest_bytes + 0x14u) == 0x00000300u);
    CHECK(load_be_u16(guest_bytes + 0x10u) == 4u);

    context.lr = 0x84BE9BB8u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_EX_GET_XCONFIG_SETTING, 3u, 10u,
                       0x00001024u, 4u, 0x00001020u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x24u) == 0x00800000u);
    CHECK(load_be_u16(guest_bytes + 0x20u) == 4u);

    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_EX_GET_XCONFIG_SETTING, 3u, 9u,
                       0x00001034u, 4u, 0x00001030u) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(load_be_u32(guest_bytes + 0x34u) == 0u);
    guest_bytes[0x40u] = 0x5Au;
    guest_bytes[0x41u] = 0xA5u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_EX_GET_XCONFIG_SETTING, 2u, 2u,
                       0x00001100u, 4u, 0x00001040u) ==
          VC_APF_BOOT_LEAF_MEMORY_FAULT);
    CHECK(guest_bytes[0x40u] == 0x5Au && guest_bytes[0x41u] == 0xA5u);
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_EX_GET_XCONFIG_SETTING, 2u, 2u,
                       0x00001044u, 4u, 0x00001046u) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);

    guest_bytes[0x60u] = 'A';
    guest_bytes[0x61u] = 'P';
    guest_bytes[0x62u] = 'F';
    guest_bytes[0x63u] = 0u;
    context.lr = 0x84BF0BB0u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INIT_ANSI_STRING, 0x00001050u,
                      0x00001060u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0x00001050u);
    CHECK(load_be_u16(guest_bytes + 0x50u) == 3u);
    CHECK(load_be_u16(guest_bytes + 0x52u) == 4u);
    CHECK(load_be_u32(guest_bytes + 0x54u) == 0x00001060u);

    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INIT_ANSI_STRING, 0x00001058u, 0u,
                      0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u16(guest_bytes + 0x58u) == 0u);
    CHECK(load_be_u16(guest_bytes + 0x5Au) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x5Cu) == 0u);

    memset(guest_bytes + 0x70u, 0xC3, VC_APF_ANSI_STRING_SIZE);
    memcpy(ansi_snapshot, guest_bytes + 0x70u, sizeof(ansi_snapshot));
    memset(guest_bytes + 0xF8u, 'B', 8u);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INIT_ANSI_STRING, 0x00001070u,
                      0x000010F8u, 0u) == VC_APF_BOOT_LEAF_MEMORY_FAULT);
    CHECK(memcmp(ansi_snapshot, guest_bytes + 0x70u,
                 sizeof(ansi_snapshot)) == 0);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INIT_ANSI_STRING, 0x000010FCu,
                      0x00001060u, 0u) == VC_APF_BOOT_LEAF_MEMORY_FAULT);

    memset(long_ansi_bytes, 0, sizeof(long_ansi_bytes));
    memset(long_ansi_bytes, 'A', 65540u);
    long_ansi_memory.bytes = long_ansi_bytes;
    long_ansi_memory.guest_base = 0x20000000u;
    long_ansi_memory.byte_count = sizeof(long_ansi_bytes);
    CHECK(call_import(&runtime, &thread_a, &long_ansi_memory, &context,
                      VC_APF_THUNK_RTL_INIT_ANSI_STRING, 0x20010008u,
                      0x20000000u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u16(long_ansi_bytes + 0x10008u) == UINT16_MAX - 1u);
    CHECK(load_be_u16(long_ansi_bytes + 0x1000Au) == UINT16_MAX);
    CHECK(load_be_u32(long_ansi_bytes + 0x1000Cu) == 0x20000000u);

    context.lr = 0x84BED958u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION,
                      0x00001080u, 0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(guest_bytes[0x80u] == 1u && guest_bytes[0x81u] == 0u);
    CHECK(guest_bytes[0x82u] == 4u && guest_bytes[0x83u] == 0u);
    CHECK(load_be_u32(guest_bytes + 0x84u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x88u) == 0x00001088u);
    CHECK(load_be_u32(guest_bytes + 0x8Cu) == 0x00001088u);
    CHECK(load_be_u32(guest_bytes + 0x90u) == UINT32_MAX);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x98u) == 0u);

    context.lr = 0x84BEDAE0u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x90u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 1u);
    CHECK(load_be_u32(guest_bytes + 0x98u) == 0x90001000u);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x90u) == 1u);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 2u);

    memcpy(critical_snapshot, guest_bytes + 0x80u, sizeof(critical_snapshot));
    thread_b_context.lr = 0x84BEDAE0u;
    CHECK(call_import(&runtime, &thread_b, &memory, &thread_b_context,
                      VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED);
    CHECK(memcmp(critical_snapshot, guest_bytes + 0x80u,
                 sizeof(critical_snapshot)) == 0);
    CHECK((uint32_t)thread_b_context.gpr[3] == 0x00001080u);
    CHECK(thread_b.scheduler_blocked);
    CHECK(thread_b.blocked_import_thunk ==
          VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION);
    CHECK(thread_b.blocked_guest_address == 0x00001080u);
    CHECK(thread_b.blocked_return_address == 0x84BEDAE0u);
    CHECK(thread_b.blocked_owner_guest_thread == 0x90001000u);
    CHECK(runtime.last_failure.related_guest_address == 0x00001080u);
    CHECK(runtime.last_failure.owning_guest_thread == 0x90001000u);
    CHECK(call_import(&runtime, &thread_b, NULL, &thread_b_context,
                      VC_APF_THUNK_XGET_LANGUAGE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED);
    CHECK((uint32_t)thread_b_context.gpr[3] == 0x00001080u);
    CHECK(thread_b.scheduler_blocked);
    CHECK(memcmp(critical_snapshot, guest_bytes + 0x80u,
                 sizeof(critical_snapshot)) == 0);

    context.lr = 0x84BEE168u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x90u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 1u);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x90u) == UINT32_MAX);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x98u) == 0u);

    CHECK(call_import(&runtime, &thread_b, &memory, &thread_b_context,
                      VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(!thread_b.scheduler_blocked);
    CHECK(load_be_u32(guest_bytes + 0x90u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 1u);
    CHECK(load_be_u32(guest_bytes + 0x98u) == 0x90002000u);
    thread_b_context.lr = 0x84BEE168u;
    CHECK(call_import(&runtime, &thread_b, &memory, &thread_b_context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x90u) == UINT32_MAX);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x98u) == 0u);

    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION,
                      0x00001080u, 0u, 0u) == VC_APF_BOOT_LEAF_OK);
    context.lr = 0x84BEDAE0u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    memcpy(critical_snapshot, guest_bytes + 0x80u, sizeof(critical_snapshot));
    CHECK(call_import(&runtime, &thread_b, &memory, &thread_b_context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_GUEST_STATE);
    CHECK(memcmp(critical_snapshot, guest_bytes + 0x80u,
                 sizeof(critical_snapshot)) == 0);
    context.lr = 0x84BEE168u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    context.lr = 0x84BD7C9Cu;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_GUEST_STATE);
    CHECK(runtime.last_failure.guest_return_address == 0x84BD7C9Cu);
    CHECK(runtime.last_failure.guest_call_address == 0x84BDE0C0u);

    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION,
                      0x00001080u, 0u, 0u) == VC_APF_BOOT_LEAF_OK);
    guest_bytes[0x82u] = 0u;
    memcpy(critical_snapshot, guest_bytes + 0x80u,
           sizeof(critical_snapshot));
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_GUEST_STATE);
    CHECK(memcmp(critical_snapshot, guest_bytes + 0x80u,
                 sizeof(critical_snapshot)) == 0);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION,
                      0x00001100u, 0u, 0u) == VC_APF_BOOT_LEAF_MEMORY_FAULT);

    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_INITIALIZE_CRITICAL_SECTION,
                      0x00001080u, 0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_ENTER_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    store_be_u32(guest_bytes + 0x88u, 0x00001040u);
    store_be_u32(guest_bytes + 0x8Cu, 0x00001044u);
    store_be_u32(guest_bytes + 0x90u, 1u);
    memcpy(critical_snapshot, guest_bytes + 0x80u,
           sizeof(critical_snapshot));
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED);
    CHECK(memcmp(critical_snapshot, guest_bytes + 0x80u,
                 sizeof(critical_snapshot)) == 0);
    CHECK(thread_a.scheduler_blocked);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XEX_CHECK_EXECUTABLE_PRIVILEGE, 32u, 0u,
                      0u) == VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED);
    CHECK((uint32_t)context.gpr[3] == 0x00001080u);
    store_be_u32(guest_bytes + 0x88u, 0x00001088u);
    store_be_u32(guest_bytes + 0x8Cu, 0x00001088u);
    store_be_u32(guest_bytes + 0x90u, 0u);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_LEAVE_CRITICAL_SECTION, 0x00001080u,
                      0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(!thread_a.scheduler_blocked);
    CHECK(load_be_u32(guest_bytes + 0x90u) == UINT32_MAX);
    CHECK(load_be_u32(guest_bytes + 0x94u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x98u) == 0u);

    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_ALLOC, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    slot = (uint32_t)context.gpr[3];
    CHECK(slot == 0u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_SET_VALUE, slot, 0x11223344u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 1u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_GET_VALUE, slot, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0x11223344u);
    CHECK(call_import(&runtime, &thread_b, NULL, &context,
                      VC_APF_THUNK_KE_TLS_GET_VALUE, slot, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);
    CHECK(call_import(&runtime, &thread_b, NULL, &context,
                      VC_APF_THUNK_KE_TLS_SET_VALUE, slot, 0xAABBCCDDu, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(call_import(&runtime, &thread_b, NULL, &context,
                      VC_APF_THUNK_KE_TLS_GET_VALUE, slot, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_C(0xFFFFFFFFAABBCCDD));
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_GET_VALUE, slot, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0x11223344u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_FREE, slot, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 1u);
    CHECK(thread_a.tls_values[slot] == 0u &&
          thread_b.tls_values[slot] == 0u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_SET_VALUE, slot, 1u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_FREE,
                      VC_APF_BOOT_TLS_OUT_OF_INDEXES, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);

    for (i = 0u; i < VC_APF_BOOT_TLS_SLOT_COUNT; ++i) {
        CHECK(call_import(&runtime, &thread_a, NULL, &context,
                          VC_APF_THUNK_KE_TLS_ALLOC, 0u, 0u, 0u) ==
              VC_APF_BOOT_LEAF_OK);
        CHECK((uint32_t)context.gpr[3] == i);
    }
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_TLS_ALLOC, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_MAX);
    CHECK((uint32_t)context.gpr[3] == VC_APF_BOOT_TLS_OUT_OF_INDEXES);

    memset(guest_bytes, 0, sizeof(guest_bytes));
    for (i = 0u; i < 3u; ++i) {
        guest_bytes[i * 4u + 0u] = 0x11u;
        guest_bytes[i * 4u + 1u] = 0x22u;
        guest_bytes[i * 4u + 2u] = 0x33u;
        guest_bytes[i * 4u + 3u] = 0x44u;
    }
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG, 0x00001000u, 12u,
                      0x11223344u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 12u);
    guest_bytes[7] = 0x45u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG, 0x00001000u, 12u,
                      0x11223344u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 4u);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG, 0x00001001u, 8u,
                      0x11223344u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG, 0x00001000u, 6u,
                      0x11223344u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);
    context.lr = 0x84BEC13Cu;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_RTL_COMPARE_MEMORY_ULONG, 0x000010FCu, 8u,
                      0x11223344u) == VC_APF_BOOT_LEAF_MEMORY_FAULT);
    CHECK((uint32_t)context.gpr[3] == 0u);
    CHECK(runtime.last_failure.guest_call_address == 0x84BEC138u);

    context.lr = 0x84BE9EB8u;
    CHECK(call_import(&runtime, &thread_a, &dbg_memory, &context,
                      VC_APF_THUNK_DBG_PRINT,
                      VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS,
                      0xFFFFFFD6u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);
    CHECK(runtime.last_debug_event.valid);
    CHECK(runtime.last_debug_event.kind ==
          VC_APF_BOOT_DEBUG_EVENT_XAPI_RETURN_VALUE_S32);
    CHECK(runtime.last_debug_event.import_thunk == VC_APF_THUNK_DBG_PRINT);
    CHECK(runtime.last_debug_event.guest_call_address == 0x84BE9EB4u);
    CHECK(runtime.last_debug_event.guest_return_address == 0x84BE9EB8u);
    CHECK(runtime.last_debug_event.guest_format_address ==
          VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS);
    CHECK(runtime.last_debug_event.raw_value == 0xFFFFFFD6u);
    CHECK(runtime.last_debug_event.signed_decimal_value == -42);
    debug_event_snapshot = runtime.last_debug_event;

    context.lr = 0x84BE9EBCu;
    CHECK(call_import(&runtime, &thread_a, &dbg_memory, &context,
                      VC_APF_THUNK_DBG_PRINT,
                      VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS, 7u,
                      0u) == VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(memcmp(&debug_event_snapshot, &runtime.last_debug_event,
                 sizeof(debug_event_snapshot)) == 0);
    context.lr = 0x84BE9EB8u;
    CHECK(call_import(&runtime, &thread_a, &dbg_memory, &context,
                      VC_APF_THUNK_DBG_PRINT,
                      VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS + 1u, 7u,
                      0u) == VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    dbg_memory.byte_count = sizeof(dbg_format_bytes) - 1u;
    CHECK(call_import(&runtime, &thread_a, &dbg_memory, &context,
                      VC_APF_THUNK_DBG_PRINT,
                      VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS, 7u,
                      0u) == VC_APF_BOOT_LEAF_MEMORY_FAULT);
    dbg_memory.byte_count = sizeof(dbg_format_bytes);
    dbg_format_bytes[0] = '!';
    CHECK(call_import(&runtime, &thread_a, &dbg_memory, &context,
                      VC_APF_THUNK_DBG_PRINT,
                      VC_APF_DBG_PRINT_XAPI_RETURN_FORMAT_ADDRESS, 7u,
                      0u) == VC_APF_BOOT_LEAF_GUEST_STATE);
    dbg_format_bytes[0] = '[';
    CHECK(memcmp(&debug_event_snapshot, &runtime.last_debug_event,
                 sizeof(debug_event_snapshot)) == 0);

    context.lr = 0x84BF188Cu;
    CHECK(call_import(&runtime, &thread_a, &retail_xex_memory, &context,
                      VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD,
                      retail_xex_memory.guest_base,
                      VC_APF_XEX_HEADER_DEFAULT_HEAP_SIZE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == 0u);
    CHECK(call_import(&runtime, &thread_a, &retail_xex_memory, &context,
                      VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD,
                      retail_xex_memory.guest_base, 0x00020200u, 0u) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    context.lr = 0x84BF1890u;
    CHECK(call_import(&runtime, &thread_a, &retail_xex_memory, &context,
                      VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD,
                      retail_xex_memory.guest_base,
                      VC_APF_XEX_HEADER_DEFAULT_HEAP_SIZE, 0u) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    context.lr = 0x84BF188Cu;
    retail_xex_memory.byte_count = sizeof(retail_xex_prefix) - 1u;
    CHECK(call_import(&runtime, &thread_a, &retail_xex_memory, &context,
                      VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD,
                      retail_xex_memory.guest_base,
                      VC_APF_XEX_HEADER_DEFAULT_HEAP_SIZE, 0u) ==
          VC_APF_BOOT_LEAF_MEMORY_FAULT);
    retail_xex_memory.byte_count = sizeof(retail_xex_prefix);
    retail_xex_prefix[31] ^= 1u;
    CHECK(call_import(&runtime, &thread_a, &retail_xex_memory, &context,
                      VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD,
                      retail_xex_memory.guest_base,
                      VC_APF_XEX_HEADER_DEFAULT_HEAP_SIZE, 0u) ==
          VC_APF_BOOT_LEAF_GUEST_STATE);
    retail_xex_prefix[31] ^= 1u;
    CHECK(call_import(&runtime, &thread_a, &retail_xex_memory, &context,
                      VC_APF_THUNK_RTL_IMAGE_XEX_HEADER_FIELD, 0u,
                      VC_APF_XEX_HEADER_DEFAULT_HEAP_SIZE, 0u) ==
          VC_APF_BOOT_LEAF_MEMORY_FAULT);

    /* Exact augmented-frontier 64 KiB virtual-memory ABI. */
    memset(vm_backing, 0xA5, sizeof(vm_backing));
    store_be_u32(guest_bytes, 0u);
    store_be_u32(guest_bytes + 4u, 0x00018000u);
    context.lr = 0x84BEBB20u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_RESERVE,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == 0u);
    CHECK(load_be_u32(guest_bytes) == 0x40000000u);
    CHECK(load_be_u32(guest_bytes + 4u) == 0x00020000u);
    CHECK(runtime.vm_allocation_count == 1u);
    CHECK(runtime.vm_pages[0].state == 1u);
    CHECK(runtime.vm_pages[1].state == 1u);
    CHECK(vm_backing[0] == 0xA5u && vm_backing[0x1FFFFu] == 0xA5u);

    memset(guest_bytes + 0x20u, 0xCC,
           VC_APF_MEMORY_BASIC_INFORMATION_SIZE);
    context.lr = 0x84BED6FCu;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY,
                      0x40001234u, 0x00001020u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x20u) == 0x40001234u);
    CHECK(load_be_u32(guest_bytes + 0x24u) == 0x40000000u);
    CHECK(load_be_u32(guest_bytes + 0x28u) ==
          VC_APF_X_PAGE_READWRITE);
    CHECK(load_be_u32(guest_bytes + 0x2Cu) == 0x00020000u);
    CHECK(load_be_u32(guest_bytes + 0x30u) == VC_APF_X_MEM_RESERVE);
    CHECK(load_be_u32(guest_bytes + 0x34u) ==
          VC_APF_X_PAGE_READWRITE);
    CHECK(load_be_u32(guest_bytes + 0x38u) == VC_APF_X_MEM_PRIVATE);

    memset(vm_backing, 0xA5, VC_APF_BOOT_VM_PAGE_SIZE);
    store_be_u32(guest_bytes, 0x40001234u);
    store_be_u32(guest_bytes + 4u, 0x00000100u);
    context.lr = 0x84BEBAD0u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_COMMIT,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes) == 0x40000000u);
    CHECK(load_be_u32(guest_bytes + 4u) == VC_APF_BOOT_VM_PAGE_SIZE);
    CHECK(runtime.vm_pages[0].state == 2u);
    for (i = 0u; i < VC_APF_BOOT_VM_PAGE_SIZE; ++i) {
        CHECK(vm_backing[i] == 0u);
    }
    memset(vm_backing, 0x3C, VC_APF_BOOT_VM_PAGE_SIZE);
    store_be_u32(guest_bytes, 0x40000000u);
    store_be_u32(guest_bytes + 4u, VC_APF_BOOT_VM_PAGE_SIZE);
    context.lr = 0x84BEBAD0u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_COMMIT,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(vm_backing[0] == 0x3Cu &&
          vm_backing[VC_APF_BOOT_VM_PAGE_SIZE - 1u] == 0x3Cu);

    context.lr = 0x84BED6FCu;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY,
                      0x40000000u, 0x00001020u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x2Cu) == VC_APF_BOOT_VM_PAGE_SIZE);
    CHECK(load_be_u32(guest_bytes + 0x30u) == VC_APF_X_MEM_COMMIT);
    context.lr = 0x84BED754u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY,
                      0x40010000u, 0x00001020u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x2Cu) == VC_APF_BOOT_VM_PAGE_SIZE);
    CHECK(load_be_u32(guest_bytes + 0x30u) == VC_APF_X_MEM_RESERVE);

    memset(vm_backing + VC_APF_BOOT_VM_PAGE_SIZE, 0x5A,
           VC_APF_BOOT_VM_PAGE_SIZE);
    store_be_u32(guest_bytes, 0x40010000u);
    store_be_u32(guest_bytes + 4u, 1u);
    context.lr = 0x84BEE1D0u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_COMMIT | VC_APF_X_MEM_NOZERO,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(vm_backing[VC_APF_BOOT_VM_PAGE_SIZE] == 0x5Au);
    CHECK(vm_backing[0x1FFFFu] == 0x5Au);

    store_be_u32(guest_bytes, 0x40000000u);
    store_be_u32(guest_bytes + 4u, 1u);
    context.lr = 0x84BED248u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u, VC_APF_X_MEM_DECOMMIT,
                       0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == VC_APF_X_STATUS_SUCCESS);
    CHECK(load_be_u32(guest_bytes + 4u) == VC_APF_BOOT_VM_PAGE_SIZE);
    CHECK(runtime.vm_pages[0].state == 1u);

    memset(vm_backing, 0xC3, VC_APF_BOOT_VM_PAGE_SIZE);
    store_be_u32(guest_bytes, 0x40000000u);
    store_be_u32(guest_bytes + 4u, 4u);
    context.lr = 0x84BEBB54u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_COMMIT,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(vm_backing[0] == 0u &&
          vm_backing[VC_APF_BOOT_VM_PAGE_SIZE - 1u] == 0u);

    store_be_u32(guest_bytes, 0x40000000u);
    store_be_u32(guest_bytes + 4u, 0u);
    context.lr = 0x84BEBB74u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u, VC_APF_X_MEM_RELEASE,
                       0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 4u) == 0x00020000u);
    CHECK(runtime.vm_allocation_count == 0u);
    CHECK(runtime.vm_pages[0].state == 0u &&
          runtime.vm_pages[1].state == 0u);

    context.lr = 0x84BED6FCu;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY,
                      0x40000010u, 0x00001020u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes + 0x24u) == 0u);
    CHECK(load_be_u32(guest_bytes + 0x2Cu) == 0x003F0000u);
    CHECK(load_be_u32(guest_bytes + 0x30u) == VC_APF_X_MEM_FREE);

    /* Failed guest operations leave both ledger and BE in/out cells intact. */
    store_be_u32(guest_bytes, 0x40000000u);
    store_be_u32(guest_bytes + 4u, 0x00020000u);
    context.lr = 0x84BED010u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_RESERVE,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.vm_allocation_count == 1u);
    store_be_u32(guest_bytes, 0x40000000u);
    store_be_u32(guest_bytes + 4u, 0x00010000u);
    context.lr = 0x84BED054u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_RESERVE,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_C(0xFFFFFFFFC0000017));
    CHECK(load_be_u32(guest_bytes) == 0x40000000u);
    CHECK(load_be_u32(guest_bytes + 4u) == 0x00010000u);
    CHECK(runtime.vm_allocation_count == 1u);
    CHECK(runtime.vm_pages[0].state == 1u &&
          runtime.vm_pages[1].state == 1u);

    context.lr = 0x84BED054u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_COMMIT,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(runtime.vm_allocation_count == 1u);

    store_be_u32(guest_bytes, 0u);
    store_be_u32(guest_bytes + 4u, 0xAABBCCDDu);
    context.lr = 0x84BED110u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u, VC_APF_X_MEM_RELEASE,
                       0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_C(0xFFFFFFFFC00000A0));
    CHECK(load_be_u32(guest_bytes) == 0u);
    CHECK(load_be_u32(guest_bytes + 4u) == 0xAABBCCDDu);
    CHECK(runtime.vm_allocation_count == 1u);

    memset(guest_bytes + 0x20u, 0xD7,
           VC_APF_MEMORY_BASIC_INFORMATION_SIZE);
    memcpy(vm_information_snapshot, guest_bytes + 0x20u,
           sizeof(vm_information_snapshot));
    context.lr = 0x84BED754u;
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY,
                      0x403F1000u, 0x00001020u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_C(0xFFFFFFFFC000000D));
    CHECK(memcmp(vm_information_snapshot, guest_bytes + 0x20u,
                 sizeof(vm_information_snapshot)) == 0);
    CHECK(call_import(&runtime, &thread_a, &memory, &context,
                      VC_APF_THUNK_NT_QUERY_VIRTUAL_MEMORY,
                      0x40000000u, 0x000010F0u, 0u) ==
          VC_APF_BOOT_LEAF_MEMORY_FAULT);
    CHECK(runtime.vm_allocation_count == 1u);

    store_be_u32(guest_bytes, 0x40000000u);
    store_be_u32(guest_bytes + 4u, 0u);
    context.lr = 0x84BED834u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u, VC_APF_X_MEM_RELEASE,
                       0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.vm_allocation_count == 0u);

    memset(vm_backing, 0x81, VC_APF_BOOT_VM_PAGE_SIZE);
    store_be_u32(guest_bytes, 0u);
    store_be_u32(guest_bytes + 4u, 16u);
    context.lr = 0x84BED80Cu;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_ALLOCATE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u,
                       VC_APF_X_MEM_LARGE_PAGES | VC_APF_X_MEM_HEAP |
                           VC_APF_X_MEM_COMMIT,
                       VC_APF_X_PAGE_READWRITE, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(load_be_u32(guest_bytes) == 0x40000000u);
    CHECK(vm_backing[0] == 0u &&
          vm_backing[VC_APF_BOOT_VM_PAGE_SIZE - 1u] == 0u);
    context.lr = 0x84BED834u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_FREE_VIRTUAL_MEMORY,
                       0x00001000u, 0x00001004u, VC_APF_X_MEM_RELEASE,
                       0u, 0u) == VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.vm_allocation_count == 0u);

    /* Exact APF event/handle/wait group; no Linux host thread ever blocks. */
    memset(guest_bytes, 0, sizeof(guest_bytes));
    store_be_u32(guest_bytes, 0xAABBCCDDu);
    context.lr = 0x84BE9A30u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_CREATE_EVENT,
                       0x00001000u, 0u, 1u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == VC_APF_X_STATUS_SUCCESS);
    event_handle = load_be_u32(guest_bytes);
    CHECK(event_handle == VC_APF_BOOT_FIRST_EVENT_HANDLE);
    CHECK(runtime.event_count == 1u);
    CHECK(runtime.events[0].active);
    CHECK(!runtime.events[0].manual_reset);
    CHECK(!runtime.events[0].signaled);

    /* A zero relative timeout is a real nonblocking poll. */
    store_be_u64(guest_bytes + 8u, 0u);
    context.lr = 0x84BF0E40u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX,
                       event_handle, 1u, 0u, 0x00001008u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] == VC_APF_X_STATUS_TIMEOUT);
    CHECK(!thread_a.scheduler_blocked);

    /* A pending relative wait stops at the scheduler boundary. */
    store_be_u64(guest_bytes + 8u, (uint64_t)(int64_t)-10000);
    context.lr = 0x84BF0E40u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX,
                       event_handle, 1u, 1u, 0x00001008u, 0u) ==
          VC_APF_BOOT_LEAF_SCHEDULER_BLOCKED);
    CHECK(thread_a.scheduler_blocked);
    CHECK(thread_a.blocked_import_thunk ==
          VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX);
    CHECK(thread_a.blocked_guest_address == event_handle);
    CHECK(thread_a.blocked_return_address == 0x84BF0E40u);
    CHECK(runtime.last_failure.related_guest_address == event_handle);
    CHECK(runtime.last_failure.guest_call_address == 0x84BF0E3Cu);
    runtime.events[0].signaled = true;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX,
                       event_handle, 1u, 1u, 0x00001008u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(!thread_a.scheduler_blocked);
    CHECK((uint32_t)context.gpr[3] == VC_APF_X_STATUS_SUCCESS);
    CHECK(!runtime.events[0].signaled); /* synchronization event auto-reset */

    context.lr = 0x84BE9A90u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_NT_CLOSE, event_handle, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.event_count == 0u);

    /*
     * The sole direct RtlNtStatusToDosError site is bounded to the two
     * negative statuses produced by resumable augmented-frontier callers.
     */
    context.lr = 0x84BF0D68u;
    context.gpr[3] = UINT64_C(0xFFFFFFFFC0000008);
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_a, NULL, &context,
              VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == VC_APF_X_ERROR_INVALID_HANDLE);
    context.gpr[3] = UINT64_C(0xFFFFFFFFC0000017);
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_a, NULL, &context,
              VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == VC_APF_X_ERROR_NOT_ENOUGH_MEMORY);

    context.gpr[3] = UINT64_C(0xFFFFFFFFC000000D);
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_a, NULL, &context,
              VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(runtime.last_failure.import_thunk ==
          VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR);
    CHECK(runtime.last_failure.guest_call_address == 0x84BF0D64u);
    CHECK(runtime.last_failure.guest_arguments[0] ==
          VC_APF_X_STATUS_INVALID_PARAMETER);
    CHECK((uint32_t)context.gpr[3] == 0u);

    context.lr = 0x84BF0D6Cu;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_RTL_NT_STATUS_TO_DOS_ERROR,
                      VC_APF_X_STATUS_INVALID_HANDLE, 0u, 0u) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(runtime.last_failure.guest_call_address == 0x84BF0D68u);
    CHECK(runtime.last_failure.guest_arguments[0] ==
          VC_APF_X_STATUS_INVALID_HANDLE);
    context.lr = 0x84BE9A90u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_NT_CLOSE, event_handle, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_C(0xFFFFFFFFC0000008));

    /* Invalid handles don't dereference a timeout pointer. */
    context.lr = 0x84BF0E40u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX,
                       event_handle, 1u, 0u, 0x00001100u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_C(0xFFFFFFFFC0000008));

    /* The general wrapper's exact helper-built named-object layout. */
    store_be_u32(guest_bytes + 0x20u, UINT32_C(0xFFFFFFFC));
    store_be_u32(guest_bytes + 0x24u, 0x00001030u);
    store_be_u32(guest_bytes + 0x28u, 0x00000080u);
    store_be_u16(guest_bytes + 0x30u, 4u);
    store_be_u16(guest_bytes + 0x32u, 5u);
    store_be_u32(guest_bytes + 0x34u, 0x00001038u);
    memcpy(guest_bytes + 0x38u, "EvNt", 5u);
    context.lr = 0x84BE708Cu;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_CREATE_EVENT,
                       0x00001000u, 0x00001020u, 0u, 1u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    named_event_handle = load_be_u32(guest_bytes);
    CHECK(named_event_handle == VC_APF_BOOT_FIRST_EVENT_HANDLE);
    CHECK(runtime.event_count == 1u);
    CHECK(runtime.events[0].manual_reset);
    CHECK(runtime.events[0].signaled);
    CHECK(runtime.events[0].named);
    CHECK(runtime.events[0].name_length == 4u);

    /* A case-insensitive named reopen keeps the first event's state/type. */
    memcpy(guest_bytes + 0x38u, "evnt", 5u);
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_CREATE_EVENT,
                       0x00001000u, 0x00001020u, 1u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK((uint32_t)context.gpr[3] ==
          VC_APF_X_STATUS_OBJECT_NAME_EXISTS);
    CHECK(load_be_u32(guest_bytes) == named_event_handle);
    CHECK(runtime.event_count == 1u);
    CHECK(runtime.events[0].handle_ref_count == 2u);
    CHECK(runtime.events[0].manual_reset && runtime.events[0].signaled);

    context.lr = 0x84BF0E40u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX,
                       named_event_handle, 1u, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.events[0].signaled);
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_WAIT_FOR_SINGLE_OBJECT_EX,
                       named_event_handle, 1u, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.events[0].signaled); /* notification event stays signaled */

    context.lr = 0x84BE9A90u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_NT_CLOSE, named_event_handle, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.event_count == 1u);
    CHECK(runtime.events[0].handle_ref_count == 1u);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_NT_CLOSE, named_event_handle, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.event_count == 0u);

    /* Guest-output and object-table changes are transactional on failures. */
    store_be_u32(guest_bytes, 0x11223344u);
    context.lr = 0x84BE9A30u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_CREATE_EVENT,
                       0x00001100u, 0u, 1u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_MEMORY_FAULT);
    CHECK(runtime.event_count == 0u);
    CHECK(load_be_u32(guest_bytes) == 0x11223344u);
    context.lr = 0x84BE9A34u;
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_CREATE_EVENT,
                       0x00001000u, 0u, 1u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(runtime.event_count == 0u);
    CHECK(load_be_u32(guest_bytes) == 0x11223344u);

    /* Exhaustion is a guest NTSTATUS and leaves the last handle cell intact. */
    for (i = 0u; i < VC_APF_BOOT_MAX_EVENT_HANDLES; ++i) {
        context.lr = 0x84BE9A30u;
        CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                           VC_APF_THUNK_NT_CREATE_EVENT,
                           0x00001000u, 0u, 1u, 0u, 0u) ==
              VC_APF_BOOT_LEAF_OK);
        event_handles[i] = load_be_u32(guest_bytes);
        CHECK(event_handles[i] ==
              VC_APF_BOOT_FIRST_EVENT_HANDLE + i * 4u);
    }
    CHECK(runtime.event_count == VC_APF_BOOT_MAX_EVENT_HANDLES);
    event_handle = load_be_u32(guest_bytes);
    CHECK(call_import7(&runtime, &thread_a, &memory, &context,
                       VC_APF_THUNK_NT_CREATE_EVENT,
                       0x00001000u, 0u, 1u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(context.gpr[3] == UINT64_C(0xFFFFFFFFC0000017));
    CHECK(load_be_u32(guest_bytes) == event_handle);
    CHECK(runtime.event_count == VC_APF_BOOT_MAX_EVENT_HANDLES);
    for (i = 0u; i < VC_APF_BOOT_MAX_EVENT_HANDLES; ++i) {
        context.lr = 0x84BE9A90u;
        CHECK(call_import(&runtime, &thread_a, NULL, &context,
                          VC_APF_THUNK_NT_CLOSE, event_handles[i], 0u, 0u) ==
              VC_APF_BOOT_LEAF_OK);
    }
    CHECK(runtime.event_count == 0u);

    /*
     * Exact one-button XamShowMessageBoxUIEx request. The host must complete
     * it explicitly; no button is chosen by the adapter.
     */
    context.lr = 0x84BE9A30u;
    CHECK(call_import7(&runtime, &thread_a, &ui_memory, &context,
                       VC_APF_THUNK_NT_CREATE_EVENT,
                       ui_stack_pointer + 124u, 0u, 1u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    event_handle = load_be_u32(ui_guest_bytes + ui_stack_offset + 124u);
    CHECK(event_handle == VC_APF_BOOT_FIRST_EVENT_HANDLE);
    CHECK(runtime.event_count == 1u);
    store_be_u32(ui_guest_bytes + ui_stack_offset + 84u,
                 ui_stack_pointer + 104u);
    store_be_u32(ui_guest_bytes + ui_stack_offset + 92u,
                 ui_stack_pointer + 112u);
    store_be_u32(ui_guest_bytes + ui_stack_offset + 204u,
                 ui_stack_pointer + 368u);
    store_be_utf16_ascii(ui_guest_bytes + ui_stack_offset + 368u, "OK");
    store_be_utf16_ascii(ui_guest_bytes + ui_stack_offset + 432u,
                         "Storage device required");

    memset(&ui_context, 0, sizeof(ui_context));
    ui_context.gpr[1] = ui_stack_pointer;
    ui_context.gpr[3] = 255u;
    ui_context.gpr[4] = 0u;
    ui_context.gpr[5] = ui_stack_pointer + 432u;
    ui_context.gpr[6] = 1u;
    ui_context.gpr[7] = ui_stack_pointer + 204u;
    ui_context.gpr[8] = 0u;
    ui_context.gpr[9] = 1u;
    ui_context.gpr[10] = 1u;
    ui_context.lr = 0x84BE9A70u;
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_a, &ui_memory, &ui_context,
              VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(!runtime.pending_message_box.active);
    CHECK(!thread_a.ui_requested);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 112u) == 0u);
    CHECK(!runtime.events[0].signaled);

    ui_context.gpr[3] = 255u;
    ui_context.lr = 0x84BE9A6Cu;
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_a, &ui_memory, &ui_context,
              VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX) ==
          VC_APF_BOOT_LEAF_UI_REQUESTED);
    CHECK(ui_context.gpr[3] == VC_APF_X_ERROR_IO_PENDING);
    CHECK(runtime.pending_message_box.active);
    CHECK(thread_a.ui_requested);
    CHECK(thread_a.ui_request_id ==
          runtime.pending_message_box.request_id);
    CHECK(runtime.pending_message_box.import_thunk ==
          VC_APF_THUNK_XAM_SHOW_MESSAGE_BOX_UI_EX);
    CHECK(runtime.pending_message_box.guest_call_address == 0x84BE9A68u);
    CHECK(runtime.pending_message_box.guest_return_address == 0x84BE9A6Cu);
    CHECK(runtime.pending_message_box.requesting_guest_thread ==
          thread_a.guest_thread_object);
    CHECK(runtime.pending_message_box.user_index == 255u);
    CHECK(runtime.pending_message_box.button_count == 1u);
    CHECK(runtime.pending_message_box.active_button == 0u);
    CHECK(runtime.pending_message_box.flags == 1u);
    CHECK(runtime.pending_message_box.opaque_r10_argument == 1u);
    CHECK(runtime.pending_message_box.result_address ==
          ui_stack_pointer + 104u);
    CHECK(runtime.pending_message_box.overlapped_address ==
          ui_stack_pointer + 112u);
    CHECK(runtime.pending_message_box.event_handle == event_handle);
    CHECK(runtime.pending_message_box.message_length == 23u);
    CHECK(runtime.pending_message_box.button_length == 2u);
    CHECK(runtime.pending_message_box.message[0] == (uint16_t)'S');
    CHECK(runtime.pending_message_box.message[22] == (uint16_t)'d');
    CHECK(runtime.pending_message_box.message[23] == 0u);
    CHECK(runtime.pending_message_box.button[0] == (uint16_t)'O');
    CHECK(runtime.pending_message_box.button[1] == (uint16_t)'K');
    CHECK(runtime.pending_message_box.button[2] == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 104u) == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 108u) == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 112u) ==
          VC_APF_X_ERROR_IO_PENDING);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 116u) == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 124u) ==
          event_handle);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 136u) == 0u);
    CHECK(!runtime.events[0].signaled);
    CHECK(runtime.last_failure.status == VC_APF_BOOT_LEAF_UI_REQUESTED);
    CHECK(runtime.last_failure.guest_call_address == 0x84BE9A68u);
    CHECK(runtime.last_failure.related_guest_address ==
          ui_stack_pointer + 112u);
    ui_request_id = runtime.pending_message_box.request_id;
    ui_context_snapshot = ui_context;
    ui_request_snapshot = runtime.pending_message_box;

    context.lr = 0x84BE9BD8u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XGET_LANGUAGE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_UI_REQUESTED);
    CHECK(memcmp(&context, &ui_context_snapshot, sizeof(context)) == 0);
    CHECK(vc_apf_boot_leaf_thread_detach(&runtime, &thread_a) ==
          VC_APF_BOOT_LEAF_UI_REQUESTED);

    memset(&ui_resume_context, 0xA5, sizeof(ui_resume_context));
    ui_resume_snapshot = ui_resume_context;
    CHECK(vc_apf_boot_leaf_complete_message_box_ui(
              &runtime, &thread_a, &ui_memory, ui_request_id + 1u, 0u,
              &ui_resume_context) == VC_APF_BOOT_LEAF_INVALID_ARGUMENT);
    CHECK(memcmp(&ui_resume_context, &ui_resume_snapshot,
                 sizeof(ui_resume_context)) == 0);
    CHECK(memcmp(&runtime.pending_message_box, &ui_request_snapshot,
                 sizeof(ui_request_snapshot)) == 0);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 112u) ==
          VC_APF_X_ERROR_IO_PENDING);
    CHECK(!runtime.events[0].signaled);

    CHECK(vc_apf_boot_leaf_complete_message_box_ui(
              &runtime, &thread_a, &ui_memory, ui_request_id, 1u,
              &ui_resume_context) == VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(memcmp(&ui_resume_context, &ui_resume_snapshot,
                 sizeof(ui_resume_context)) == 0);
    CHECK(runtime.pending_message_box.active);
    CHECK(!runtime.events[0].signaled);

    ui_truncated_memory.byte_count = ui_stack_offset + 120u;
    CHECK(vc_apf_boot_leaf_complete_message_box_ui(
              &runtime, &thread_a, &ui_truncated_memory, ui_request_id, 0u,
              &ui_resume_context) == VC_APF_BOOT_LEAF_MEMORY_FAULT);
    CHECK(memcmp(&ui_resume_context, &ui_resume_snapshot,
                 sizeof(ui_resume_context)) == 0);
    CHECK(runtime.pending_message_box.active);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 112u) ==
          VC_APF_X_ERROR_IO_PENDING);
    CHECK(!runtime.events[0].signaled);

    store_be_u32(ui_guest_bytes + ui_stack_offset + 104u, 1u);
    CHECK(vc_apf_boot_leaf_complete_message_box_ui(
              &runtime, &thread_a, &ui_memory, ui_request_id, 0u,
              &ui_resume_context) == VC_APF_BOOT_LEAF_GUEST_STATE);
    CHECK(memcmp(&ui_resume_context, &ui_resume_snapshot,
                 sizeof(ui_resume_context)) == 0);
    CHECK(runtime.pending_message_box.active);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 112u) ==
          VC_APF_X_ERROR_IO_PENDING);
    CHECK(!runtime.events[0].signaled);
    store_be_u32(ui_guest_bytes + ui_stack_offset + 104u, 0u);

    CHECK(vc_apf_boot_leaf_complete_message_box_ui(
              &runtime, &thread_a, &ui_memory, ui_request_id, 0u,
              &ui_resume_context) == VC_APF_BOOT_LEAF_OK);
    CHECK(memcmp(&ui_resume_context, &ui_context_snapshot,
                 sizeof(ui_resume_context)) == 0);
    CHECK(ui_resume_context.gpr[3] == VC_APF_X_ERROR_IO_PENDING);
    CHECK(!runtime.pending_message_box.active);
    CHECK(!thread_a.ui_requested);
    CHECK(thread_a.ui_request_id == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 104u) == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 108u) == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 112u) ==
          VC_APF_X_STATUS_SUCCESS);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 116u) == 0u);
    CHECK(load_be_u32(ui_guest_bytes + ui_stack_offset + 136u) ==
          VC_APF_X_STATUS_SUCCESS);
    CHECK(runtime.events[0].signaled);
    CHECK(strcmp(vc_apf_boot_leaf_status_name(
                     VC_APF_BOOT_LEAF_UI_REQUESTED),
                 "ui_requested") == 0);

    context.lr = 0x84BE9A90u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_NT_CLOSE, event_handle, 0u, 0u) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(runtime.event_count == 0u);

    context.lr = 0x84BF1998u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_HAL_RETURN_TO_FIRMWARE, 1u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_TERMINAL_OUTCOME);
    CHECK(runtime.last_failure.terminal_outcome ==
          VC_APF_BOOT_TERMINAL_FIRMWARE_RETURN);
    CHECK(runtime.last_failure.guest_arguments[0] == 1u);
    CHECK(runtime.last_failure.guest_call_address == 0x84BF1994u);

    context.lr = 0x84BEDAA0u;
    CHECK(call_import7(&runtime, &thread_a, NULL, &context,
                       VC_APF_THUNK_KE_BUG_CHECK_EX, 244u, 0x11111111u,
                       0x22222222u, 1459u, 0x44444444u) ==
          VC_APF_BOOT_LEAF_TERMINAL_OUTCOME);
    CHECK(runtime.last_failure.terminal_outcome ==
          VC_APF_BOOT_TERMINAL_BUGCHECK);
    CHECK(runtime.last_failure.guest_arguments[0] == 244u);
    CHECK(runtime.last_failure.guest_arguments[3] == 1459u);

    context.lr = 0x84BDAA00u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_KE_BUG_CHECK, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_TERMINAL_OUTCOME);
    CHECK(runtime.last_failure.terminal_outcome ==
          VC_APF_BOOT_TERMINAL_BUGCHECK);
    CHECK(runtime.last_failure.guest_arguments[0] == 0u);
    CHECK(runtime.last_failure.guest_call_address == 0x84BDAA24u);

    context.lr = 0x84BE9EC8u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XAM_LOADER_TERMINATE_TITLE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_TERMINAL_OUTCOME);
    CHECK(runtime.last_failure.terminal_outcome ==
          VC_APF_BOOT_TERMINAL_TITLE_TERMINATE);
    CHECK(runtime.last_failure.guest_call_address == 0x84BE9EC4u);

    context.lr = 0x84BE9EB8u;
    CHECK(call_import(&runtime, &thread_a, NULL, &context, 0xDEADBEEFu, 0u,
                      0u, 0u) == VC_APF_BOOT_LEAF_UNKNOWN_IMPORT);

    CHECK(vc_apf_boot_leaf_thread_detach(&runtime, &thread_b) ==
          VC_APF_BOOT_LEAF_OK);
    CHECK(call_import(&runtime, &thread_b, NULL, &context,
                      VC_APF_THUNK_XGET_LANGUAGE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_THREAD_REQUIRED);
    CHECK(vc_apf_boot_leaf_thread_attach(&runtime, &thread_b, 0x90003000u) ==
          VC_APF_BOOT_LEAF_OK);

    context.lr = 0x84BEE288u;
    context.gpr[10] = UINT64_C(0x1122334455667788);
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_RTL_RAISE_EXCEPTION, 0x00001080u, 0u,
                      0u) == VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED);
    CHECK(runtime.last_failure.terminal_outcome == VC_APF_BOOT_TERMINAL_NONE);
    CHECK(runtime.last_failure.guest_arguments[0] == 0x00001080u);
    CHECK((uint32_t)context.gpr[3] == 0x00001080u);
    CHECK(thread_a.exception_required);
    CHECK(thread_a.exception_import_thunk == VC_APF_THUNK_RTL_RAISE_EXCEPTION);
    CHECK(thread_a.exception_record == 0x00001080u);
    CHECK(thread_a.exception_return_address == 0x84BEE288u);
    exception_snapshot = context;
    CHECK(call_import(&runtime, &thread_a, NULL, &context,
                      VC_APF_THUNK_XGET_LANGUAGE, 0u, 0u, 0u) ==
          VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED);
    CHECK(memcmp(&exception_snapshot, &context, sizeof(context)) == 0);
    CHECK(runtime.last_failure.import_thunk ==
          VC_APF_THUNK_RTL_RAISE_EXCEPTION);
    CHECK(vc_apf_boot_leaf_dispatch(&runtime, &thread_a, NULL,
                                    &thread_a.exception_context,
                                    VC_APF_THUNK_XGET_LANGUAGE) ==
          VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED);
    CHECK(memcmp(&exception_snapshot, &thread_a.exception_context,
                 sizeof(exception_snapshot)) == 0);
    CHECK(vc_apf_boot_leaf_thread_detach(&runtime, &thread_a) ==
          VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED);
    CHECK(strcmp(vc_apf_boot_leaf_status_name(
                     VC_APF_BOOT_LEAF_EXCEPTION_REQUIRED),
                 "exception_required") == 0);

    /*
     * Exact frontier ExCreateThread shape. This publishes a scheduler request
     * without allocating a handle/object/stack or running guest code.
     */
    store_be_u32(thread_guest_bytes + 0x20u, 0x820046D4u);
    store_be_u32(thread_guest_bytes + 0x24u, UINT32_MAX);
    store_be_u32(thread_guest_bytes + 0x28u, 0x84502174u);
    store_be_u32(thread_guest_bytes + 0x2Cu, 0u);
    store_be_u32(thread_guest_bytes + 0x30u,
                 thread_create_start_context);
    store_be_u32(thread_guest_bytes + 0x34u, 0u);
    store_be_u32(thread_guest_bytes + 0x38u,
                 thread_create_start_context);
    store_be_u32(thread_guest_bytes + 0x3Cu, 0u);
    store_be_u32(thread_guest_bytes + 0x40u, 128u);
    store_be_u32(thread_guest_bytes + 0x44u, 0u);
    store_be_u32(thread_guest_bytes + thread_create_stack_offset + 80u,
                 0xA1B2C3D4u);
    store_be_u32(thread_guest_bytes + thread_create_stack_offset + 176u,
                 0x55667788u);
    memcpy(thread_create_bytes_snapshot, thread_guest_bytes,
           sizeof(thread_create_bytes_snapshot));

    memset(&thread_create_context, 0, sizeof(thread_create_context));
    thread_create_context.gpr[1] = thread_create_stack_pointer;
    thread_create_context.gpr[3] = thread_create_stack_pointer + 84u;
    thread_create_context.gpr[4] = 0u;
    thread_create_context.gpr[5] = 0u;
    thread_create_context.gpr[6] = 0u;
    thread_create_context.gpr[7] = 0x84BF6EE0u;
    thread_create_context.gpr[8] = 0u;
    thread_create_context.gpr[9] = 0x01000001u;
    thread_create_context.lr = 0x84BF75A0u;
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_b, &thread_create_memory,
              &thread_create_context, VC_APF_THUNK_EX_CREATE_THREAD) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(!runtime.pending_thread_create.active);
    CHECK(!thread_b.thread_create_requested);
    CHECK(memcmp(thread_create_bytes_snapshot, thread_guest_bytes,
                 sizeof(thread_create_bytes_snapshot)) == 0);

    memset(&thread_create_context, 0, sizeof(thread_create_context));
    thread_create_context.gpr[1] = thread_create_stack_pointer;
    thread_create_context.gpr[3] = thread_create_stack_pointer + 80u;
    thread_create_context.gpr[4] = 0x00010000u;
    thread_create_context.gpr[5] = thread_create_stack_pointer + 176u;
    thread_create_context.gpr[6] =
        VC_APF_BOOT_FRONTIER_XAPI_THREAD_STARTUP;
    thread_create_context.gpr[7] =
        VC_APF_BOOT_FRONTIER_THREAD_START_ADDRESS;
    thread_create_context.gpr[8] = thread_create_start_context;
    thread_create_context.gpr[9] = 0u;
    thread_create_context.lr = 0x84BF1090u;
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_b, &thread_create_memory,
              &thread_create_context, VC_APF_THUNK_EX_CREATE_THREAD) ==
          VC_APF_BOOT_LEAF_UNSUPPORTED_VARIANT);
    CHECK(!runtime.pending_thread_create.active);
    CHECK(memcmp(thread_create_bytes_snapshot, thread_guest_bytes,
                 sizeof(thread_create_bytes_snapshot)) == 0);

    thread_create_context.gpr[3] = thread_create_stack_pointer + 80u;
    thread_create_context.gpr[4] =
        VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE;
    thread_create_truncated_memory.byte_count =
        thread_create_stack_offset + 178u;
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_b, &thread_create_truncated_memory,
              &thread_create_context, VC_APF_THUNK_EX_CREATE_THREAD) ==
          VC_APF_BOOT_LEAF_MEMORY_FAULT);
    CHECK(!runtime.pending_thread_create.active);
    CHECK(memcmp(thread_create_bytes_snapshot, thread_guest_bytes,
                 sizeof(thread_create_bytes_snapshot)) == 0);

    thread_create_context.gpr[3] = thread_create_stack_pointer + 80u;
    store_be_u32(thread_guest_bytes + 0x28u, 0x84502175u);
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_b, &thread_create_memory,
              &thread_create_context, VC_APF_THUNK_EX_CREATE_THREAD) ==
          VC_APF_BOOT_LEAF_GUEST_STATE);
    CHECK(!runtime.pending_thread_create.active);
    CHECK(load_be_u32(thread_guest_bytes + 0x28u) == 0x84502175u);
    store_be_u32(thread_guest_bytes + 0x28u, 0x84502174u);

    thread_create_context.gpr[3] = thread_create_stack_pointer + 80u;
    thread_create_snapshot = thread_create_context;
    memcpy(thread_create_bytes_snapshot, thread_guest_bytes,
           sizeof(thread_create_bytes_snapshot));
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_b, &thread_create_memory,
              &thread_create_context, VC_APF_THUNK_EX_CREATE_THREAD) ==
          VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED);
    CHECK(memcmp(&thread_create_context, &thread_create_snapshot,
                 sizeof(thread_create_context)) == 0);
    CHECK(memcmp(thread_create_bytes_snapshot, thread_guest_bytes,
                 sizeof(thread_create_bytes_snapshot)) == 0);
    CHECK(runtime.pending_thread_create.active);
    CHECK(runtime.pending_thread_create.request_id == 1u);
    CHECK(runtime.pending_thread_create.requesting_guest_thread ==
          thread_b.guest_thread_object);
    CHECK(runtime.pending_thread_create.import_thunk ==
          VC_APF_THUNK_EX_CREATE_THREAD);
    CHECK(runtime.pending_thread_create.guest_call_address == 0x84BF108Cu);
    CHECK(runtime.pending_thread_create.guest_return_address == 0x84BF1090u);
    CHECK(runtime.pending_thread_create.handle_address ==
          thread_create_stack_pointer + 80u);
    CHECK(runtime.pending_thread_create.requested_stack_size ==
          VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE);
    CHECK(runtime.pending_thread_create.effective_stack_size ==
          VC_APF_BOOT_FRONTIER_THREAD_STACK_SIZE);
    CHECK(runtime.pending_thread_create.thread_id_address ==
          thread_create_stack_pointer + 176u);
    CHECK(runtime.pending_thread_create.xapi_thread_startup ==
          VC_APF_BOOT_FRONTIER_XAPI_THREAD_STARTUP);
    CHECK(runtime.pending_thread_create.start_address ==
          VC_APF_BOOT_FRONTIER_THREAD_START_ADDRESS);
    CHECK(runtime.pending_thread_create.start_context ==
          thread_create_start_context);
    CHECK(runtime.pending_thread_create.creation_flags == 0u);
    CHECK(!runtime.pending_thread_create.create_suspended);
    CHECK(runtime.pending_thread_create.processor_affinity_mask == 0u);
    CHECK(thread_b.thread_create_requested);
    CHECK(thread_b.thread_create_request_id == 1u);
    CHECK(runtime.last_failure.status ==
          VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED);
    CHECK(runtime.last_failure.related_guest_address ==
          thread_create_stack_pointer + 80u);
    CHECK(runtime.last_failure.owning_guest_thread ==
          thread_b.guest_thread_object);
    thread_create_request_snapshot = runtime.pending_thread_create;

    memset(&thread_create_context, 0x5A, sizeof(thread_create_context));
    CHECK(vc_apf_boot_leaf_dispatch(
              &runtime, &thread_b, NULL, &thread_create_context,
              VC_APF_THUNK_XGET_LANGUAGE) ==
          VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED);
    CHECK(memcmp(&thread_create_context, &thread_create_snapshot,
                 sizeof(thread_create_context)) == 0);
    CHECK(memcmp(&runtime.pending_thread_create,
                 &thread_create_request_snapshot,
                 sizeof(thread_create_request_snapshot)) == 0);
    CHECK(vc_apf_boot_leaf_thread_detach(&runtime, &thread_b) ==
          VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED);
    CHECK(strcmp(vc_apf_boot_leaf_status_name(
                     VC_APF_BOOT_LEAF_THREAD_CREATE_REQUESTED),
                 "thread_create_requested") == 0);

    printf("APF_BOOT_LEAF_ADAPTERS_PASS resumable_imports=24 "
           "terminal_imports=4 exception_imports=1 direct_sites=87 "
           "proved_indirect_import_sites=4 "
           "guest_threads=2 xconfig_writes=2 critical_sites=23 "
           "ansi_string_sites=2 be_compare_bytes=12 "
           "dbgprint_events=1 xex_absent=1 vm_sites=19 "
           "vm_pages=64 event_sites=4 event_capacity=64 "
           "ui_sites=1 ui_requests=1 thread_create_sites=1 "
           "thread_create_requests=1 unsupported_frontier_imports=0\n");
    return 0;
}

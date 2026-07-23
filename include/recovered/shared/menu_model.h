#ifndef VC_RECOVERED_SHARED_MENU_MODEL_H
#define VC_RECOVERED_SHARED_MENU_MODEL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum VcMenuSource {
    VC_MENU_SOURCE_HOST = 0,
    VC_MENU_SOURCE_NFL2K5 = 1,
    VC_MENU_SOURCE_APF2K8 = 2
} VcMenuSource;

typedef enum VcMenuLayoutLookupKind {
    VC_MENU_LAYOUT_NONE = 0,
    VC_MENU_LAYOUT_NAME_AND_FOURCC = 1,
    VC_MENU_LAYOUT_CRC32_AND_TYPE_HASH = 2
} VcMenuLayoutLookupKind;

typedef enum VcMenuActionKind {
    VC_MENU_ACTION_HOST_PLAY = 0,
    VC_MENU_ACTION_HOST_ROSTER = 1,
    VC_MENU_ACTION_HOST_MOD_BROWSER = 2,
    VC_MENU_ACTION_HOST_QUIT = 3,
    VC_MENU_ACTION_PUSH_STATE = 4,
    VC_MENU_ACTION_TRANSITION_STATE = 5,
    VC_MENU_ACTION_REPLACE_LIKE_STATE = 6,
    VC_MENU_ACTION_CALLBACK = 7
} VcMenuActionKind;

typedef struct VcMenuLayoutIdentity {
    const char *name;
    const char *archive_name;
    uint32_t outer_index;
    uint32_t inner_index;
    VcMenuLayoutLookupKind lookup_kind;
    uint32_t name_crc32;
    uint32_t type_id;
} VcMenuLayoutIdentity;

typedef struct VcMenuAction {
    VcMenuActionKind kind;
    uint32_t source_type_code;
    uint32_t target_state_address;
    uint32_t activation_address;
    uint32_t dispatch_address;
    uint32_t downstream_address;
    uint32_t callback_address;
    uint32_t preflight_callback_address;
    const char *portme;
} VcMenuAction;

typedef struct VcMenuRow {
    const char *label;
    uint32_t source_address;
    uint32_t label_address;
    VcMenuAction action;
} VcMenuRow;

typedef struct VcMenuModel {
    VcMenuSource source;
    const char *cli_name;
    const char *host_heading;
    const char *state_title;
    uint32_t state_descriptor_address;
    VcMenuLayoutIdentity state_layout;
    const VcMenuRow *rows;
    size_t row_count;
    bool recovered_guest_data;
} VcMenuModel;

bool vc_menu_source_parse(const char *text, VcMenuSource *source);
const VcMenuModel *vc_menu_model(VcMenuSource source);
const char *vc_menu_action_kind_name(VcMenuActionKind kind);
size_t vc_menu_move_selection(const VcMenuModel *model, size_t selected,
                              int direction);
bool vc_menu_format_host_activation(const VcMenuModel *model, size_t row,
                                    char *destination, size_t capacity);

#endif

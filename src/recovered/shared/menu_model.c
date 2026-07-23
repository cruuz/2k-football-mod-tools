#include "recovered/shared/menu_model.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#define VC_ARRAY_COUNT(values) (sizeof(values) / sizeof((values)[0]))

static const VcMenuRow host_rows[] = {
    {"PLAY EXHIBITION", 0, 0,
     {VC_MENU_ACTION_HOST_PLAY, 0, 0, 0, 0, 0, 0, 0, NULL}},
    {"TEAMS AND PLAYERS", 0, 0,
     {VC_MENU_ACTION_HOST_ROSTER, 0, 0, 0, 0, 0, 0, 0, NULL}},
    {"MOD BROWSER", 0, 0,
     {VC_MENU_ACTION_HOST_MOD_BROWSER, 0, 0, 0, 0, 0, 0, 0, NULL}},
    {"QUIT", 0, 0,
     {VC_MENU_ACTION_HOST_QUIT, 0, 0, 0, 0, 0, 0, 0, NULL}},
};

/* PORTME: NFL2K5 dispatcher 0x0006E390 must be reimplemented before any
   recovered push action may execute guest-equivalent state transitions. */
/* PORTME: NFL2K5 callback 0x0024D440 (The Crib) has no recovered semantics. */
static const VcMenuRow nfl2k5_rows[] = {
    {"Quick Game", UINT32_C(0x005154C0), UINT32_C(0x00E8B138),
     {VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x0052728C),
      UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0,
      "PORTME: 0x0006E390 host push bridge"}},
    {"Game Modes", UINT32_C(0x005154F4), UINT32_C(0x00E8B150),
     {VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x005015CC),
      UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0,
      "PORTME: 0x0006E390 host push bridge"}},
    {"The Crib|TM|", UINT32_C(0x00515528), UINT32_C(0x00E8B168),
     {VC_MENU_ACTION_CALLBACK, 9, 0, UINT32_C(0x00150020), 0, 0,
      UINT32_C(0x0024D440), 0, "PORTME: callback 0x0024D440"}},
    {"Features", UINT32_C(0x0051555C), UINT32_C(0x00E8B184),
     {VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x00525830),
      UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0,
      "PORTME: 0x0006E390 host push bridge"}},
    {"Options", UINT32_C(0x00515590), UINT32_C(0x00E8B198),
     {VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x00503288),
      UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0,
      "PORTME: 0x0006E390 host push bridge"}},
    {"Xbox Live", UINT32_C(0x005155C4), UINT32_C(0x00E8B1A8),
     {VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x00525FCC),
      UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0,
      "PORTME: 0x0006E390 host push bridge"}},
    {"Extras", UINT32_C(0x005155F8), UINT32_C(0x00E8B1BC),
     {VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x005408A8),
      UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0,
      "PORTME: 0x0006E390 host push bridge"}},
};

/* PORTME: APF2K8 transition routine 0x846F45E0 has no proved simple
   push/replace name; preserve it as a distinct transition action. */
/* PORTME: APF2K8 activation routine 0x846F59A8 is not connected to native
   input/state objects and must never be called as a host function pointer. */
/* PORTME: APF2K8 replace-like helper 0x846F8F00 is not connected to a host
   state; its complete contract is not proved. */
/* PORTME: APF2K8 callback 0x84A57F70 (Xbox Live action) is unresolved. */
/* PORTME: APF2K8 callback 0x846CAE10 (Xbox Live preflight) is unresolved. */
static const VcMenuRow apf2k8_rows[] = {
    {"Quick Game", UINT32_C(0x84E57340), UINT32_C(0x8460BFCC),
     {VC_MENU_ACTION_REPLACE_LIKE_STATE, 12, UINT32_C(0x820F6D38),
      UINT32_C(0x846F59A8), UINT32_C(0x846F9020), UINT32_C(0x846F8F00), 0,
      0, "PORTME: replace-like bridge 0x846F9020 -> 0x846F8F00"}},
    {"Teams", UINT32_C(0x84E573A0), UINT32_C(0x8460BFE4),
     {VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820F4278),
      UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0,
      "PORTME: transition 0x846F45E0"}},
    {"Season", UINT32_C(0x84E57400), UINT32_C(0x8460BFF0),
     {VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820F4308),
      UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0,
      "PORTME: transition 0x846F45E0"}},
    {"Practice", UINT32_C(0x84E57460), UINT32_C(0x8460C000),
     {VC_MENU_ACTION_REPLACE_LIKE_STATE, 12, UINT32_C(0x820E1DE0),
      UINT32_C(0x846F59A8), UINT32_C(0x846F9020), UINT32_C(0x846F8F00), 0,
      0, "PORTME: replace-like bridge 0x846F9020 -> 0x846F8F00"}},
    {"Options", UINT32_C(0x84E574C0), UINT32_C(0x8460C014),
     {VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820F4578),
      UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0,
      "PORTME: transition 0x846F45E0"}},
    {"Features", UINT32_C(0x84E57520), UINT32_C(0x8460C024),
     {VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820DDF30),
      UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0,
      "PORTME: transition 0x846F45E0"}},
    {"Xbox Live", UINT32_C(0x84E57580), UINT32_C(0x8460C038),
     {VC_MENU_ACTION_CALLBACK, 10, 0, UINT32_C(0x846F59A8), 0, 0,
      UINT32_C(0x84A57F70), UINT32_C(0x846CAE10),
      "PORTME: callbacks 0x846CAE10 and 0x84A57F70"}},
};

static const VcMenuModel models[] = {
    {
        VC_MENU_SOURCE_HOST,
        "host",
        "2K FOOTBALL LINUX PORT",
        "Native Host",
        0,
        {"host", NULL, 0, 0, VC_MENU_LAYOUT_NONE, 0, 0},
        host_rows,
        VC_ARRAY_COUNT(host_rows),
        false,
    },
    {
        VC_MENU_SOURCE_NFL2K5,
        "nfl2k5",
        "NFL 2K5 MAIN MENU",
        "Main Menu",
        UINT32_C(0x00515660),
        {"main_menu_sub", NULL, 8, 18, VC_MENU_LAYOUT_NAME_AND_FOURCC,
         UINT32_C(0x19815D9B), UINT32_C(0x5459414C)},
        nfl2k5_rows,
        VC_ARRAY_COUNT(nfl2k5_rows),
        true,
    },
    {
        VC_MENU_SOURCE_APF2K8,
        "apf2k8",
        "APF 2K8 MAIN MENU",
        "Main Menu",
        UINT32_C(0x820F4350),
        {"quicknav", "global.iff", 1310, 57,
         VC_MENU_LAYOUT_CRC32_AND_TYPE_HASH, UINT32_C(0x210FFA23),
         UINT32_C(0x86A1AC9E)},
        apf2k8_rows,
        VC_ARRAY_COUNT(apf2k8_rows),
        true,
    },
};

bool vc_menu_source_parse(const char *text, VcMenuSource *source)
{
    if (text == NULL || source == NULL) {
        return false;
    }
    for (size_t i = 0; i < VC_ARRAY_COUNT(models); ++i) {
        if (strcmp(text, models[i].cli_name) == 0) {
            *source = models[i].source;
            return true;
        }
    }
    return false;
}

const VcMenuModel *vc_menu_model(VcMenuSource source)
{
    for (size_t i = 0; i < VC_ARRAY_COUNT(models); ++i) {
        if (models[i].source == source) {
            return &models[i];
        }
    }
    return NULL;
}

const char *vc_menu_action_kind_name(VcMenuActionKind kind)
{
    switch (kind) {
    case VC_MENU_ACTION_HOST_PLAY: return "host-play";
    case VC_MENU_ACTION_HOST_ROSTER: return "host-roster";
    case VC_MENU_ACTION_HOST_MOD_BROWSER: return "host-mod-browser";
    case VC_MENU_ACTION_HOST_QUIT: return "host-quit";
    case VC_MENU_ACTION_PUSH_STATE: return "push-state";
    case VC_MENU_ACTION_TRANSITION_STATE: return "transition-state";
    case VC_MENU_ACTION_REPLACE_LIKE_STATE: return "replace-like-state";
    case VC_MENU_ACTION_CALLBACK: return "callback";
    default: return "unknown";
    }
}

size_t vc_menu_move_selection(const VcMenuModel *model, size_t selected,
                              int direction)
{
    if (model == NULL || model->row_count == 0) {
        return 0;
    }
    selected %= model->row_count;
    if (direction < 0) {
        return selected == 0 ? model->row_count - 1U : selected - 1U;
    }
    if (direction > 0) {
        return (selected + 1U) % model->row_count;
    }
    return selected;
}

bool vc_menu_format_host_activation(const VcMenuModel *model, size_t row,
                                    char *destination, size_t capacity)
{
    if (model == NULL || !model->recovered_guest_data || row >= model->row_count ||
        destination == NULL || capacity == 0) {
        return false;
    }
    const VcMenuAction *action = &model->rows[row].action;
    int written = 0;
    if (action->kind == VC_MENU_ACTION_CALLBACK) {
        if (action->preflight_callback_address != 0) {
            written = snprintf(
                destination, capacity,
                "HOST VIEW ONLY HANDLER 0X%08" PRIX32
                " CALLBACK 0X%08" PRIX32
                " PREFLIGHT 0X%08" PRIX32 " NOT EXECUTED",
                action->activation_address, action->callback_address,
                action->preflight_callback_address);
        } else {
            written = snprintf(
                destination, capacity,
                "HOST VIEW ONLY HANDLER 0X%08" PRIX32
                " CALLBACK 0X%08" PRIX32 " NOT EXECUTED",
                action->activation_address, action->callback_address);
        }
    } else if (action->downstream_address != 0) {
        written = snprintf(
            destination, capacity,
            "HOST VIEW ONLY %s TARGET 0X%08" PRIX32
            " HANDLER 0X%08" PRIX32 " VIA 0X%08" PRIX32
            " THEN 0X%08" PRIX32 " NOT EXECUTED",
            vc_menu_action_kind_name(action->kind),
            action->target_state_address, action->activation_address,
            action->dispatch_address, action->downstream_address);
    } else {
        written = snprintf(destination, capacity,
                           "HOST VIEW ONLY %s TARGET 0X%08" PRIX32
                           " HANDLER 0X%08" PRIX32 " VIA 0X%08" PRIX32
                           " NOT EXECUTED",
                           vc_menu_action_kind_name(action->kind),
                           action->target_state_address,
                           action->activation_address,
                           action->dispatch_address);
    }
    return written >= 0 && (size_t)written < capacity;
}

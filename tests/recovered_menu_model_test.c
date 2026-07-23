#include "recovered/shared/menu_model.h"

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct ExpectedRow {
    const char *label;
    uint32_t source_address;
    uint32_t label_address;
    VcMenuActionKind kind;
    uint32_t source_type;
    uint32_t target;
    uint32_t activation;
    uint32_t dispatch;
    uint32_t downstream;
    uint32_t callback;
    uint32_t preflight;
} ExpectedRow;

static int expect_true(bool condition, const char *message)
{
    if (condition) {
        return 0;
    }
    fprintf(stderr, "menu model: %s\n", message);
    return 1;
}

static int expect_u32(uint32_t actual, uint32_t expected,
                      const char *field, size_t row)
{
    if (actual == expected) {
        return 0;
    }
    fprintf(stderr,
            "menu row %zu %s: expected 0x%08" PRIX32
            ", got 0x%08" PRIX32 "\n",
            row, field, expected, actual);
    return 1;
}

static int expect_rows(const VcMenuModel *model, const ExpectedRow *expected,
                       size_t count)
{
    int failures = 0;
    failures += expect_true(model != NULL, "model is null");
    if (model == NULL) {
        return failures;
    }
    failures += expect_true(model->row_count == count, "row count mismatch");
    if (model->row_count != count) {
        return failures;
    }
    for (size_t i = 0; i < count; ++i) {
        const VcMenuRow *actual = &model->rows[i];
        failures += expect_true(strcmp(actual->label, expected[i].label) == 0,
                                "row label mismatch");
        failures += expect_u32(actual->source_address,
                               expected[i].source_address, "source record", i);
        failures += expect_u32(actual->label_address, expected[i].label_address,
                               "label address", i);
        failures += expect_true(actual->action.kind == expected[i].kind,
                                "row action kind mismatch");
        failures += expect_u32(actual->action.source_type_code,
                               expected[i].source_type, "source type", i);
        failures += expect_u32(actual->action.target_state_address,
                               expected[i].target, "target", i);
        failures += expect_u32(actual->action.activation_address,
                               expected[i].activation, "activation", i);
        failures += expect_u32(actual->action.dispatch_address,
                               expected[i].dispatch, "dispatch", i);
        failures += expect_u32(actual->action.downstream_address,
                               expected[i].downstream, "downstream", i);
        failures += expect_u32(actual->action.callback_address,
                               expected[i].callback, "callback", i);
        failures += expect_u32(actual->action.preflight_callback_address,
                               expected[i].preflight, "preflight", i);
        failures += expect_true(actual->action.portme != NULL,
                                "recovered action lacks PORTME evidence");

        char activation[256];
        failures += expect_true(
            vc_menu_format_host_activation(model, i, activation,
                                           sizeof(activation)),
            "activation evidence did not format");
        failures += expect_true(strstr(activation, "HOST VIEW ONLY") != NULL,
                                "activation lacks host-view guard");
        failures += expect_true(strstr(activation, "NOT EXECUTED") != NULL,
                                "activation lacks execution guard");
    }
    return failures;
}

int main(void)
{
    static const ExpectedRow nfl_rows[] = {
        {"Quick Game", UINT32_C(0x005154C0), UINT32_C(0x00E8B138),
         VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x0052728C),
         UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0},
        {"Game Modes", UINT32_C(0x005154F4), UINT32_C(0x00E8B150),
         VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x005015CC),
         UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0},
        {"The Crib|TM|", UINT32_C(0x00515528), UINT32_C(0x00E8B168),
         VC_MENU_ACTION_CALLBACK, 9, 0, UINT32_C(0x00150020), 0, 0,
         UINT32_C(0x0024D440), 0},
        {"Features", UINT32_C(0x0051555C), UINT32_C(0x00E8B184),
         VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x00525830),
         UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0},
        {"Options", UINT32_C(0x00515590), UINT32_C(0x00E8B198),
         VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x00503288),
         UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0},
        {"Xbox Live", UINT32_C(0x005155C4), UINT32_C(0x00E8B1A8),
         VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x00525FCC),
         UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0},
        {"Extras", UINT32_C(0x005155F8), UINT32_C(0x00E8B1BC),
         VC_MENU_ACTION_PUSH_STATE, 0, UINT32_C(0x005408A8),
         UINT32_C(0x00150020), UINT32_C(0x0006E390), 0, 0, 0},
    };
    static const ExpectedRow apf_rows[] = {
        {"Quick Game", UINT32_C(0x84E57340), UINT32_C(0x8460BFCC),
         VC_MENU_ACTION_REPLACE_LIKE_STATE, 12, UINT32_C(0x820F6D38),
         UINT32_C(0x846F59A8), UINT32_C(0x846F9020),
         UINT32_C(0x846F8F00), 0, 0},
        {"Teams", UINT32_C(0x84E573A0), UINT32_C(0x8460BFE4),
         VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820F4278),
         UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0},
        {"Season", UINT32_C(0x84E57400), UINT32_C(0x8460BFF0),
         VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820F4308),
         UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0},
        {"Practice", UINT32_C(0x84E57460), UINT32_C(0x8460C000),
         VC_MENU_ACTION_REPLACE_LIKE_STATE, 12, UINT32_C(0x820E1DE0),
         UINT32_C(0x846F59A8), UINT32_C(0x846F9020),
         UINT32_C(0x846F8F00), 0, 0},
        {"Options", UINT32_C(0x84E574C0), UINT32_C(0x8460C014),
         VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820F4578),
         UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0},
        {"Features", UINT32_C(0x84E57520), UINT32_C(0x8460C024),
         VC_MENU_ACTION_TRANSITION_STATE, 11, UINT32_C(0x820DDF30),
         UINT32_C(0x846F59A8), UINT32_C(0x846F45E0), 0, 0, 0},
        {"Xbox Live", UINT32_C(0x84E57580), UINT32_C(0x8460C038),
         VC_MENU_ACTION_CALLBACK, 10, 0, UINT32_C(0x846F59A8), 0, 0,
         UINT32_C(0x84A57F70), UINT32_C(0x846CAE10)},
    };

    int failures = 0;
    VcMenuSource source = VC_MENU_SOURCE_HOST;
    failures += expect_true(vc_menu_source_parse("host", &source) &&
                                source == VC_MENU_SOURCE_HOST,
                            "host CLI profile did not parse");
    failures += expect_true(vc_menu_source_parse("nfl2k5", &source) &&
                                source == VC_MENU_SOURCE_NFL2K5,
                            "NFL CLI profile did not parse");
    failures += expect_true(vc_menu_source_parse("apf2k8", &source) &&
                                source == VC_MENU_SOURCE_APF2K8,
                            "APF CLI profile did not parse");
    failures += expect_true(!vc_menu_source_parse("NFL2K5", &source),
                            "invalid case variant was accepted");
    failures += expect_true(!vc_menu_source_parse(NULL, &source),
                            "null profile was accepted");

    const VcMenuModel *host = vc_menu_model(VC_MENU_SOURCE_HOST);
    const VcMenuModel *nfl = vc_menu_model(VC_MENU_SOURCE_NFL2K5);
    const VcMenuModel *apf = vc_menu_model(VC_MENU_SOURCE_APF2K8);
    failures += expect_true(host != NULL && host->row_count == 4 &&
                                !host->recovered_guest_data,
                            "default host model changed");
    failures += expect_true(host != NULL &&
                                strcmp(host->rows[3].label, "QUIT") == 0 &&
                                host->rows[3].action.kind ==
                                    VC_MENU_ACTION_HOST_QUIT,
                            "host quit row changed");
    char host_activation[64];
    failures += expect_true(
        host != NULL && !vc_menu_format_host_activation(
                            host, 0, host_activation, sizeof(host_activation)),
        "host action was formatted as recovered guest evidence");

    failures += expect_rows(nfl, nfl_rows,
                            sizeof(nfl_rows) / sizeof(nfl_rows[0]));
    failures += expect_rows(apf, apf_rows,
                            sizeof(apf_rows) / sizeof(apf_rows[0]));

    failures += expect_true(nfl != NULL &&
                                nfl->state_descriptor_address ==
                                    UINT32_C(0x00515660) &&
                                strcmp(nfl->state_layout.name,
                                       "main_menu_sub") == 0 &&
                                nfl->state_layout.archive_name == NULL &&
                                nfl->state_layout.outer_index == 8 &&
                                nfl->state_layout.inner_index == 18 &&
                                nfl->state_layout.lookup_kind ==
                                    VC_MENU_LAYOUT_NAME_AND_FOURCC &&
                                nfl->state_layout.name_crc32 ==
                                    UINT32_C(0x19815D9B) &&
                                nfl->state_layout.type_id ==
                                    UINT32_C(0x5459414C),
                            "NFL state/layout identity mismatch");
    failures += expect_true(apf != NULL &&
                                apf->state_descriptor_address ==
                                    UINT32_C(0x820F4350) &&
                                strcmp(apf->state_layout.name, "quicknav") == 0 &&
                                strcmp(apf->state_layout.archive_name,
                                       "global.iff") == 0 &&
                                apf->state_layout.outer_index == 1310 &&
                                apf->state_layout.inner_index == 57 &&
                                apf->state_layout.lookup_kind ==
                                    VC_MENU_LAYOUT_CRC32_AND_TYPE_HASH &&
                                apf->state_layout.name_crc32 ==
                                    UINT32_C(0x210FFA23) &&
                                apf->state_layout.type_id ==
                                    UINT32_C(0x86A1AC9E),
                            "APF state/layout identity mismatch");

    failures += expect_true(host != NULL &&
                                vc_menu_move_selection(host, 0, -1) == 3 &&
                                vc_menu_move_selection(host, 3, 1) == 0,
                            "host selection wrap mismatch");
    failures += expect_true(nfl != NULL &&
                                vc_menu_move_selection(nfl, 0, -1) == 6 &&
                                vc_menu_move_selection(nfl, 6, 1) == 0,
                            "NFL selection wrap mismatch");
    failures += expect_true(apf != NULL &&
                                vc_menu_move_selection(apf, 0, -1) == 6 &&
                                vc_menu_move_selection(apf, 6, 1) == 0,
                            "APF selection wrap mismatch");
    failures += expect_true(vc_menu_model((VcMenuSource)99) == NULL,
                            "invalid model ID resolved");

    if (failures != 0) {
        fprintf(stderr, "RECOVERED_MENU_MODEL_FAIL: %d assertion(s)\n",
                failures);
        return 1;
    }
    puts("RECOVERED_MENU_MODEL_PASS");
    return 0;
}

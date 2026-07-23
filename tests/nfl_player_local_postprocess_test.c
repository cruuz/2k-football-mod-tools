#include "recovered/nfl2k5/player_local_postprocess.h"

#include <stdio.h>
#include <string.h>

int main(void)
{
    static const char *const expected_low[VC_NFL_PLAYER_LOW_MATRIX_COUNT] = {
        "root", "lfemur", "ltibia", "lfoot", "ltoes", "rfemur",
        "rtibia", "rfoot", "rtoes", "waist", "thorax", "neck", "head",
        "lcollar", "lhumerus", "lelbow", "lwrist", "lhand", "rcollar",
        "rhumerus", "relbow", "rwrist", "rhand", "lshoulderpad",
        "rshoulderpad"
    };
    static const char *const expected_high[VC_NFL_PLAYER_HIGH_MATRIX_COUNT] = {
        "root", "lfemur", "ltibia", "lfoot", "ltoes",
        "l_kneepad_muscle", "l_calf_muscle", "l_knee_hinge",
        "l_quad_center_muscle", "l_femur_twist_0", "l_femur_twist_50",
        "l_gluteus_muscle", "l_stripe_muscle", "rfemur", "rtibia",
        "rfoot", "rtoes", "r_kneepad_muscle", "r_calf_muscle",
        "r_knee_hinge", "r_quad_center_muscle", "r_femur_twist_0",
        "r_femur_twist_50", "r_gluteus_muscle", "r_stripe_muscle",
        "groin", "waist", "thorax", "neck", "head", "lcollar",
        "lhumerus", "lelbow", "l_forearm_twist_25",
        "l_forearm_twist_50", "l_forearm_twist_75",
        "l_forearm_twist_100", "lhand", "l_arm_hinge_muscle",
        "l_arm_hinge_muscle_2", "l_ulna_muscle", "l_triceps_muscle",
        "l_radius_muscle", "l_biceps_muscle", "rcollar", "rhumerus",
        "relbow", "r_forearm_twist_25", "r_forearm_twist_50",
        "r_forearm_twist_75", "r_forearm_twist_100", "rhand",
        "r_biceps_muscle", "r_triceps_muscle", "r_ulna_muscle",
        "r_radius_muscle", "r_arm_hinge_muscle",
        "r_arm_hinge_muscle_2", "lshoulderpad", "rshoulderpad",
        "r_gluteus_muscle_2", "l_gluteus_muscle_2"
    };
    VcNflPlayerLocalPostprocessTables tables;
    VcNflPlayerLocalMatrices matrices;
    VcNflPlayerLocalMatrices before;
    float skeleton[VC_NFL_PLAYER_LOW_MATRIX_COUNT][4];
    VcNflPlayerLocalPostprocessStatus status;
    size_t index;

    memset(&tables, 0, sizeof(tables));
    memset(&matrices, 0x5a, sizeof(matrices));
    memset(skeleton, 0, sizeof(skeleton));

    for (index = 0; index < VC_NFL_PLAYER_LOW_MATRIX_COUNT; ++index) {
        const char *actual = vc_nfl_player_low_matrix_name(index);
        if (actual == NULL || strcmp(actual, expected_low[index]) != 0) {
            fprintf(stderr, "low name mismatch at %zu\n", index);
            return 1;
        }
    }
    for (index = 0; index < VC_NFL_PLAYER_HIGH_MATRIX_COUNT; ++index) {
        const char *actual = vc_nfl_player_high_matrix_name(index);
        if (actual == NULL || strcmp(actual, expected_high[index]) != 0) {
            fprintf(stderr, "high name mismatch at %zu\n", index);
            return 1;
        }
    }
    if (vc_nfl_player_low_matrix_name(VC_NFL_PLAYER_LOW_MATRIX_COUNT) != NULL ||
            vc_nfl_player_high_matrix_name(VC_NFL_PLAYER_HIGH_MATRIX_COUNT) != NULL) {
        fputs("out-of-range name did not return null\n", stderr);
        return 1;
    }

    before = matrices;
    status = vc_nfl_player_local_postprocess_92140(
        (const float (*)[4])skeleton, &tables, &matrices, NULL, NULL);
    if (status != VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_TABLES ||
            memcmp(&before, &matrices, sizeof(matrices)) != 0) {
        fputs("bad tables mutated output or returned wrong status\n", stderr);
        return 1;
    }
    status = vc_nfl_player_local_postprocess_92140(
        NULL, &tables, &matrices, NULL, NULL);
    if (status != VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_ARGUMENT ||
            strcmp(vc_nfl_player_local_postprocess_status_name(status),
                "bad_argument") != 0) {
        fputs("bad argument status mismatch\n", stderr);
        return 1;
    }
    if (strcmp(
            vc_nfl_player_local_postprocess_status_name(
                VC_NFL_PLAYER_LOCAL_POSTPROCESS_BAD_TABLES),
            "bad_tables") != 0 ||
            strcmp(
                vc_nfl_player_local_postprocess_status_name(
                    VC_NFL_PLAYER_LOCAL_POSTPROCESS_OK),
                "ok") != 0) {
        fputs("status string mismatch\n", stderr);
        return 1;
    }

    puts("NFL_PLAYER_LOCAL_POSTPROCESS_TEST_PASS");
    return 0;
}

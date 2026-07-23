#include "recovered/shared/side_label.h"
#include "recovered/shared/value_bucket.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int expect_label(uint32_t code, const char *expected)
{
    const char *actual = vc_side_label(code);
    if (strcmp(actual, expected) == 0) {
        return 0;
    }
    fprintf(stderr, "side label %u: expected '%s', got '%s'\n",
            code, expected, actual);
    return 1;
}

int main(void)
{
    int failures = 0;

    failures += vc_side_code_nfl2k5(UINT32_C(0x8badf00d)) == 13U ? 0 : 1;
    failures += vc_side_code_apf2k8(UINT32_C(0xa8000000)) == 21U ? 0 : 1;
    failures += expect_label(0U, "unknown");
    failures += expect_label(1U, "left side");
    failures += expect_label(2U, "left side");
    failures += expect_label(3U, "up middle");
    failures += expect_label(4U, "up middle");
    failures += expect_label(5U, "up middle");
    failures += expect_label(6U, "up middle");
    failures += expect_label(7U, "right side");
    failures += expect_label(8U, "right side");
    failures += expect_label(9U, "unknown");
    failures += expect_label(UINT32_MAX, "unknown");
    failures += vc_signed_position_bucket(INT32_MIN) == 0U ? 0 : 1;
    failures += vc_signed_position_bucket(-12) == 0U ? 0 : 1;
    failures += vc_signed_position_bucket(-11) == 1U ? 0 : 1;
    failures += vc_signed_position_bucket(10) == 1U ? 0 : 1;
    failures += vc_signed_position_bucket(11) == 2U ? 0 : 1;
    failures += vc_signed_position_bucket(INT32_MAX) == 2U ? 0 : 1;
    failures += vc_paired_code_bucket(0U) == 0U ? 0 : 1;
    failures += vc_paired_code_bucket(2U) == 0U ? 0 : 1;
    failures += vc_paired_code_bucket(3U) == 1U ? 0 : 1;
    failures += vc_paired_code_bucket(4U) == 1U ? 0 : 1;
    failures += vc_paired_code_bucket(5U) == 2U ? 0 : 1;
    failures += vc_paired_code_bucket(6U) == 2U ? 0 : 1;
    failures += vc_paired_code_bucket(7U) == 3U ? 0 : 1;
    failures += vc_paired_code_bucket(8U) == 3U ? 0 : 1;
    failures += vc_paired_code_bucket(9U) == 0U ? 0 : 1;
    failures += vc_paired_code_bucket(UINT32_MAX) == 0U ? 0 : 1;

    if (failures != 0) {
        fprintf(stderr, "RECOVERED_SHARED_FAIL: %d assertion(s)\n", failures);
        return 1;
    }
    puts("RECOVERED_SHARED_PASS");
    return 0;
}

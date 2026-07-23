#include "recovered/nfl2k5/main_menu_row_layout.h"

#include <stdio.h>

static int expect_layout(int32_t mode, int32_t row,
                         float x, float y, float text_x, float text_y)
{
    VcNflMainMenuRowLayout layout = {0};
    if (!vc_nfl_main_menu_row_layout(mode, row, &layout)) {
        fprintf(stderr, "layout rejected mode=%d row=%d\n", mode, row);
        return 1;
    }
    if (layout.x != x || layout.y != y || layout.z != 20.0f ||
        layout.w != 0.0f || layout.text_x != text_x ||
        layout.text_y != text_y) {
        fprintf(stderr,
                "layout mismatch mode=%d row=%d got=(%g,%g,%g,%g;%g,%g)\n",
                mode, row, (double)layout.x, (double)layout.y,
                (double)layout.z, (double)layout.w,
                (double)layout.text_x, (double)layout.text_y);
        return 1;
    }
    return 0;
}

int main(void)
{
    int failures = 0;
    failures += expect_layout(0, 0, 0.0f, 0.0f, 8.0f, -4.0f);
    failures += expect_layout(0, 6, 0.0f, 228.0f, 8.0f, 224.0f);
    failures += expect_layout(0, 10, 200.0f, 0.0f, 208.0f, -4.0f);
    failures += expect_layout(0, 21, 400.0f, 38.0f, 408.0f, 34.0f);
    failures += expect_layout(1, 9, 0.0f, 342.0f, 8.0f, 338.0f);
    failures += expect_layout(2, 0, 144.0f, 86.0f, 152.0f, 82.0f);
    failures += expect_layout(2, 6, 144.0f, 266.0f, 152.0f, 262.0f);
    failures += expect_layout(2, 11, 344.0f, 86.0f, 352.0f, 82.0f);
    failures += expect_layout(2, 23, 544.0f, 116.0f, 552.0f, 112.0f);
    failures += expect_layout(2, -1, 144.0f, 56.0f, 152.0f, 52.0f);

    VcNflMainMenuRowLayout sentinel = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f};
    if (vc_nfl_main_menu_row_layout(-1, 0, &sentinel) ||
        vc_nfl_main_menu_row_layout(3, 0, &sentinel) ||
        vc_nfl_main_menu_row_layout(0, 0, NULL)) {
        fprintf(stderr, "invalid input was accepted\n");
        failures += 1;
    }
    if (sentinel.x != 1.0f || sentinel.text_y != 6.0f) {
        fprintf(stderr, "invalid mode mutated output\n");
        failures += 1;
    }
    if (failures != 0) {
        return 1;
    }
    puts("NFL_MAIN_MENU_ROW_LAYOUT_NATIVE_PASS modes=3 cases=10");
    return 0;
}

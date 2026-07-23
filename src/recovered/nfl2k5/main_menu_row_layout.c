#include "recovered/nfl2k5/main_menu_row_layout.h"

#include <stddef.h>

typedef struct VcNflMainMenuRowMode {
    float base_x;
    float base_y;
    int32_t wrap_rows;
    float row_step;
} VcNflMainMenuRowMode;

/* Exact little-endian table at default.xbe:0x00509A30. */
static const VcNflMainMenuRowMode row_modes[3] = {
    {0.0f, 0.0f, 10, 38.0f},
    {0.0f, 0.0f, 10, 38.0f},
    {144.0f, 86.0f, 11, 30.0f}
};

bool vc_nfl_main_menu_row_layout(int32_t mode, int32_t row,
                                 VcNflMainMenuRowLayout *layout)
{
    if (layout == NULL || mode < 0 || mode >= 3) {
        return false;
    }

    const VcNflMainMenuRowMode *config = &row_modes[(size_t)mode];
    float x = config->base_x;
    float y = config->base_y + config->row_step * (float)row;
    int32_t remaining = row;
    while (remaining >= config->wrap_rows) {
        x += 200.0f;
        y -= (float)config->wrap_rows * config->row_step;
        remaining -= config->wrap_rows;
    }

    layout->x = x;
    layout->y = y;
    layout->z = 20.0f;
    layout->w = 0.0f;
    layout->text_x = x + 8.0f;
    layout->text_y = y - 4.0f;

    /* PORTME(0x0014FB83): portable float results are value-equivalent for the
       bounded menu indices; original x87 intermediate/exception bit identity
       is not claimed for arbitrary int32 row values. */
    /* PORTME(0x0014FB7A): the human-facing meaning and valid lifecycle of the
       manager field at +0xA7C remain unnamed, so callers pass the proved
       serialized mode explicitly. */
    /* PORTME(0x0014FF21): the later viewport/projection transform is not yet
       recovered; these are exact title-space coordinates, not claimed Linux
       framebuffer pixels. */
    return true;
}

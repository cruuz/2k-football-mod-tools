#ifndef VC_RECOVERED_NFL2K5_MAIN_MENU_ROW_LAYOUT_H
#define VC_RECOVERED_NFL2K5_MAIN_MENU_ROW_LAYOUT_H

#include <stdbool.h>
#include <stdint.h>

typedef struct VcNflMainMenuRowLayout {
    float x;
    float y;
    float z;
    float w;
    float text_x;
    float text_y;
} VcNflMainMenuRowLayout;

/* Recovered from default.xbe:0x0014FB70 and its table at 0x00509A30.
   Mode is the original manager field at +0xA7C. */
bool vc_nfl_main_menu_row_layout(int32_t mode, int32_t row,
                                 VcNflMainMenuRowLayout *layout);

#endif

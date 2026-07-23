#ifndef VC_PORT_BITMAP_FONT_H
#define VC_PORT_BITMAP_FONT_H

#include "port/bitmap_font_metrics.h"
#include "port/png_texture.h"
#include "port/ui_renderer.h"

#include <stdbool.h>
#include <sys/types.h>
#include <time.h>

typedef struct VcBitmapFont {
    VcBitmapFontMetrics metrics;
    VcPngTexture atlas;
    struct timespec metrics_modified_time;
    off_t metrics_source_size;
    dev_t metrics_source_device;
    ino_t metrics_source_inode;
    char atlas_path[4096];
    char metrics_path[4096];
    bool loaded;
} VcBitmapFont;

bool vc_bitmap_font_load(VcBitmapFont *font, const char *atlas_path,
                         const char *metrics_path);
bool vc_bitmap_font_reload_if_changed(VcBitmapFont *font);
bool vc_bitmap_font_ready(const VcBitmapFont *font);
void vc_bitmap_font_text(VcUiRenderer *renderer, const VcBitmapFont *font,
                         const VcPngTexture *tm_icon, const char *text,
                         float x, float y, float scale,
                         float r, float g, float b, float a);
void vc_bitmap_font_destroy(VcBitmapFont *font);

#endif

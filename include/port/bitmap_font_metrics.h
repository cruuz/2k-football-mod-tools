#ifndef VC_PORT_BITMAP_FONT_METRICS_H
#define VC_PORT_BITMAP_FONT_METRICS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define VC_BITMAP_FONT_METRICS_SCHEMA "vc_bitmap_font_metrics_v1"
#define VC_BITMAP_FONT_MAX_GLYPHS 256U

typedef struct VcBitmapGlyph {
    uint32_t codepoint;
    int advance;
    int left;
    int top;
    int right;
    int bottom;
    int atlas_left;
    int atlas_top;
    int atlas_right;
    int atlas_bottom;
} VcBitmapGlyph;

typedef struct VcBitmapFontMetrics {
    int atlas_width;
    int atlas_height;
    int line_advance;
    int space_advance;
    uint32_t minimum_codepoint;
    uint32_t maximum_codepoint;
    size_t glyph_count;
    VcBitmapGlyph glyphs[VC_BITMAP_FONT_MAX_GLYPHS];
} VcBitmapFontMetrics;

bool vc_bitmap_font_metrics_load(VcBitmapFontMetrics *metrics,
                                 const char *path, char *error,
                                 size_t error_capacity);
const VcBitmapGlyph *vc_bitmap_font_glyph(
    const VcBitmapFontMetrics *metrics, uint32_t codepoint);
float vc_bitmap_font_measure_ascii(const VcBitmapFontMetrics *metrics,
                                   const char *text, float scale);

#endif

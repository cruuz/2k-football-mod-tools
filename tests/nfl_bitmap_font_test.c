#include "port/bitmap_font_metrics.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int expect_true(bool condition, const char *message)
{
    if (condition) {
        return 0;
    }
    fprintf(stderr, "NFL bitmap font test: %s\n", message);
    return 1;
}

static int expect_glyph(const VcBitmapFontMetrics *metrics, uint32_t codepoint,
                        int advance, int left, int top, int right, int bottom,
                        int atlas_left, int atlas_top, int atlas_right,
                        int atlas_bottom)
{
    const VcBitmapGlyph *glyph = vc_bitmap_font_glyph(metrics, codepoint);
    if (glyph != NULL && glyph->advance == advance && glyph->left == left &&
        glyph->top == top && glyph->right == right &&
        glyph->bottom == bottom && glyph->atlas_left == atlas_left &&
        glyph->atlas_top == atlas_top &&
        glyph->atlas_right == atlas_right &&
        glyph->atlas_bottom == atlas_bottom) {
        return 0;
    }
    fprintf(stderr, "NFL bitmap font test: U+%04X metrics mismatch\n",
            codepoint);
    return 1;
}

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s font7.metrics.tsv\n", argv[0]);
        return 2;
    }

    VcBitmapFontMetrics metrics;
    char error[256];
    int failures = 0;
    failures += expect_true(
        vc_bitmap_font_metrics_load(&metrics, argv[1], error, sizeof(error)),
        error);
    if (failures != 0) {
        return 1;
    }
    failures += expect_true(metrics.atlas_width == 256 &&
                                metrics.atlas_height == 256,
                            "font7 atlas dimensions mismatch");
    failures += expect_true(metrics.line_advance == 25 &&
                                metrics.space_advance == 9,
                            "font7 line/space advance mismatch");
    failures += expect_true(metrics.minimum_codepoint == UINT32_C(0x21) &&
                                metrics.maximum_codepoint == UINT32_C(0x7E) &&
                                metrics.glyph_count == 94U,
                            "font7 range/count mismatch");
    for (size_t index = 0U; index < metrics.glyph_count; ++index) {
        failures += expect_true(
            metrics.glyphs[index].codepoint == UINT32_C(0x21) + index,
            "font7 codepoint range is not contiguous");
    }
    failures += expect_glyph(&metrics, (uint32_t)'!', 8, 0, 6, 7, 24,
                             0, 0, 7, 18);
    failures += expect_glyph(&metrics, (uint32_t)'A', 23, 0, 6, 22, 24,
                             43, 20, 65, 38);
    failures += expect_glyph(&metrics, (uint32_t)'M', 26, 0, 6, 25, 24,
                             39, 41, 64, 59);
    failures += expect_glyph(&metrics, (uint32_t)'w', 23, 0, 9, 22, 24,
                             42, 177, 64, 192);
    failures += expect_glyph(&metrics, (uint32_t)'~', 14, 0, 13, 13, 19,
                             32, 240, 45, 246);
    failures += expect_true(vc_bitmap_font_glyph(&metrics, 0U) == NULL &&
                                vc_bitmap_font_glyph(&metrics, 0x7FU) == NULL,
                            "out-of-range codepoint resolved");

    const float quick_game =
        vc_bitmap_font_measure_ascii(&metrics, "Quick Game", 1.0f);
    failures += expect_true(fabsf(quick_game - 177.0f) < 0.0001f,
                            "Quick Game advance mismatch");
    failures += expect_true(
        fabsf(vc_bitmap_font_measure_ascii(&metrics, "Game Modes", 0.5f) -
              93.0f) < 0.0001f,
        "scaled Game Modes advance mismatch");
    failures += expect_true(
        fabsf(vc_bitmap_font_measure_ascii(&metrics,
                                           "Quick Game\nExtras", 1.0f) -
              177.0f) < 0.0001f,
        "multiline maximum advance mismatch");
    failures += expect_true(
        vc_bitmap_font_measure_ascii(NULL, "Quick Game", 1.0f) == 0.0f &&
            vc_bitmap_font_measure_ascii(&metrics, NULL, 1.0f) == 0.0f &&
            vc_bitmap_font_measure_ascii(&metrics, "Quick Game", 0.0f) ==
                0.0f,
        "invalid measurement arguments were not bounded");

    VcBitmapFontMetrics rejected;
    failures += expect_true(
        !vc_bitmap_font_metrics_load(&rejected,
                                     "/definitely/not/a/font.metrics.tsv",
                                     error, sizeof(error)) &&
            strstr(error, "could not open") != NULL,
        "missing metrics file was not rejected with a diagnostic");

    if (failures != 0) {
        fprintf(stderr, "NFL_BITMAP_FONT_NATIVE_FAIL assertions=%d\n",
                failures);
        return 1;
    }
    printf("NFL_BITMAP_FONT_NATIVE_PASS "
           "representation=recovered_host_representation "
           "glyphs=%zu atlas=%dx%d line=%d space=%d quick_game=%.0f\n",
           metrics.glyph_count, metrics.atlas_width, metrics.atlas_height,
           metrics.line_advance, metrics.space_advance, quick_game);
    return 0;
}

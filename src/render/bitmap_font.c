#include "port/bitmap_font.h"
#include "recovered/nfl2k5/formatted_token.h"

#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static bool same_timestamp(struct timespec left, struct timespec right)
{
    return left.tv_sec == right.tv_sec && left.tv_nsec == right.tv_nsec;
}

static bool metrics_file_changed(const VcBitmapFont *font)
{
    struct stat status;
    return stat(font->metrics_path, &status) != 0 ||
           !same_timestamp(status.st_mtim, font->metrics_modified_time) ||
           status.st_size != font->metrics_source_size ||
           status.st_dev != font->metrics_source_device ||
           status.st_ino != font->metrics_source_inode;
}

static bool atlas_file_changed(const VcBitmapFont *font)
{
    struct stat status;
    return stat(font->atlas_path, &status) != 0 ||
           !same_timestamp(status.st_mtim, font->atlas.modified_time) ||
           status.st_size != font->atlas.source_size ||
           status.st_dev != font->atlas.source_device ||
           status.st_ino != font->atlas.source_inode;
}

bool vc_bitmap_font_load(VcBitmapFont *font, const char *atlas_path,
                         const char *metrics_path)
{
    if (font == NULL || atlas_path == NULL || metrics_path == NULL ||
        atlas_path[0] == '\0' || metrics_path[0] == '\0' ||
        strlen(atlas_path) >= sizeof(font->atlas_path) ||
        strlen(metrics_path) >= sizeof(font->metrics_path)) {
        return false;
    }

    VcBitmapFontMetrics metrics;
    char error[256];
    if (!vc_bitmap_font_metrics_load(&metrics, metrics_path, error,
                                     sizeof(error))) {
        fprintf(stderr, "bitmap font: metrics rejected: %s\n", error);
        return false;
    }
    VcPngTexture atlas = {0};
    if (!vc_png_texture_load(&atlas, atlas_path)) {
        fprintf(stderr, "bitmap font: atlas load failed: %s\n", atlas_path);
        return false;
    }
    if (atlas.width != metrics.atlas_width ||
        atlas.height != metrics.atlas_height) {
        fprintf(stderr,
                "bitmap font: atlas/metrics dimensions differ: PNG=%dx%d "
                "metrics=%dx%d\n",
                atlas.width, atlas.height, metrics.atlas_width,
                metrics.atlas_height);
        vc_png_texture_destroy(&atlas);
        return false;
    }

    struct stat metrics_status;
    if (stat(metrics_path, &metrics_status) != 0) {
        fprintf(stderr, "bitmap font: could not stat metrics: %s\n",
                metrics_path);
        vc_png_texture_destroy(&atlas);
        return false;
    }

    vc_png_texture_destroy(&font->atlas);
    font->atlas = atlas;
    font->metrics = metrics;
    font->metrics_modified_time = metrics_status.st_mtim;
    font->metrics_source_size = metrics_status.st_size;
    font->metrics_source_device = metrics_status.st_dev;
    font->metrics_source_inode = metrics_status.st_ino;
    (void)snprintf(font->atlas_path, sizeof(font->atlas_path), "%s",
                   atlas_path);
    (void)snprintf(font->metrics_path, sizeof(font->metrics_path), "%s",
                   metrics_path);
    font->loaded = true;
    fprintf(stderr,
            "bitmap font: loaded font7 recovered host representation; "
            "glyphs=%zu atlas=%dx%d line=%d space=%d; "
            "original LAYT coordinates and boot are not claimed\n",
            font->metrics.glyph_count, font->metrics.atlas_width,
            font->metrics.atlas_height, font->metrics.line_advance,
            font->metrics.space_advance);
    fprintf(stderr, "bitmap font: atlas=%s metrics=%s\n",
            font->atlas_path, font->metrics_path);
    return true;
}

bool vc_bitmap_font_reload_if_changed(VcBitmapFont *font)
{
    if (!vc_bitmap_font_ready(font) ||
        (!metrics_file_changed(font) && !atlas_file_changed(font))) {
        return false;
    }
    char atlas_path[sizeof(font->atlas_path)];
    char metrics_path[sizeof(font->metrics_path)];
    (void)snprintf(atlas_path, sizeof(atlas_path), "%s", font->atlas_path);
    (void)snprintf(metrics_path, sizeof(metrics_path), "%s",
                   font->metrics_path);
    if (!vc_bitmap_font_load(font, atlas_path, metrics_path)) {
        fprintf(stderr,
                "bitmap font: loose reload rejected; keeping prior font7\n");
        return false;
    }
    return true;
}

bool vc_bitmap_font_ready(const VcBitmapFont *font)
{
    return font != NULL && font->loaded && font->atlas.id != 0 &&
           font->metrics.glyph_count != 0U;
}

void vc_bitmap_font_text(VcUiRenderer *renderer, const VcBitmapFont *font,
                         const VcPngTexture *tm_icon, const char *text,
                         float x, float y, float scale,
                         float r, float g, float b, float a)
{
    if (renderer == NULL || !vc_bitmap_font_ready(font) || text == NULL ||
        scale <= 0.0f) {
        return;
    }
    const float origin_x = x;
    const float atlas_width = (float)font->metrics.atlas_width;
    const float atlas_height = (float)font->metrics.atlas_height;
    const VcBitmapGlyph *fallback =
        vc_bitmap_font_glyph(&font->metrics, (uint32_t)'?');
    for (const unsigned char *cursor = (const unsigned char *)text;
         *cursor != 0U; ++cursor) {
        if (*cursor == (unsigned char)'|') {
            size_t consumed = 0U;
            const int token_index = vc_nfl_formatted_token_match_ascii(
                (const char *)cursor, &consumed);
            const VcNflFormattedToken *token = token_index >= 0
                ? vc_nfl_formatted_token_at((size_t)token_index)
                : NULL;
            if (token_index == 40 && token != NULL && tm_icon != NULL &&
                tm_icon->id != 0U) {
                const float font_height =
                    (float)font->metrics.line_advance * scale;
                const int icon_width =
                    vc_nfl_formatted_token_width(token, font_height);
                const int icon_height =
                    vc_nfl_formatted_token_height(token, font_height);
                if (icon_width > 0 && icon_height > 0) {
                    vc_ui_texture_region(
                        renderer, tm_icon->id, x, y,
                        (float)icon_width, (float)icon_height,
                        token->u0, token->v0, token->u1, token->v1,
                        r, g, b, a);
                    x += (float)icon_width;
                    cursor += consumed - 1U;
                    continue;
                }
            }
            /* PORTME(0x000EEDB0): the exact 57-record token table is
               recovered, but only the visible main-menu TM resource is bound
               in this host seam. Other or missing loose resources retain
               their source markup instead of inventing an inline object. */
        }
        if (*cursor == (unsigned char)'\n') {
            x = origin_x;
            y += (float)font->metrics.line_advance * scale;
            continue;
        }
        if (*cursor == (unsigned char)' ') {
            x += (float)font->metrics.space_advance * scale;
            continue;
        }
        if (*cursor == (unsigned char)'\t') {
            x += (float)(font->metrics.space_advance * 4) * scale;
            continue;
        }
        const VcBitmapGlyph *glyph =
            vc_bitmap_font_glyph(&font->metrics, (uint32_t)*cursor);
        if (glyph == NULL) {
            glyph = fallback;
        }
        if (glyph != NULL) {
            vc_ui_texture_region(
                renderer, font->atlas.id,
                x + (float)glyph->left * scale,
                y + (float)glyph->top * scale,
                (float)(glyph->right - glyph->left) * scale,
                (float)(glyph->bottom - glyph->top) * scale,
                (float)glyph->atlas_left / atlas_width,
                (float)glyph->atlas_top / atlas_height,
                (float)glyph->atlas_right / atlas_width,
                (float)glyph->atlas_bottom / atlas_height,
                r, g, b, a);
            x += (float)glyph->advance * scale;
        }
    }
}

void vc_bitmap_font_destroy(VcBitmapFont *font)
{
    if (font == NULL) {
        return;
    }
    vc_png_texture_destroy(&font->atlas);
    memset(font, 0, sizeof(*font));
}

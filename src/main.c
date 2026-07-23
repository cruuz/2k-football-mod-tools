#include "port/bitmap_font.h"
#include "port/model_loader.h"
#include "port/png_texture.h"
#include "port/ui_renderer.h"
#include "port/wav_audio.h"
#include "recovered/shared/menu_model.h"
#include "xdk/xdk_linux.h"

#include <GL/glew.h>
#include <SDL2/SDL.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef VC_PORT_VERSION
#define VC_PORT_VERSION "dev"
#endif

#ifndef VC_INSTALL_ASSET_RELATIVE
#define VC_INSTALL_ASSET_RELATIVE "../share/vc_football_linux_port/assets/mod/common"
#endif

typedef struct AppOptions {
    const char *asset_root;
    const char *model_path;
    const char *nfl_font_atlas_path;
    const char *nfl_font_metrics_path;
    const char *nfl_tm_icon_path;
    const char *screenshot_path;
    int smoke_frames;
    bool model_only;
    bool asset_root_explicit;
    bool nfl_font_paths_explicit;
    bool nfl_tm_icon_explicit;
    VcMenuSource menu_source;
} AppOptions;

typedef enum NflFontPathSource {
    NFL_FONT_PATH_EXPECTED_OVERRIDE = 0,
    NFL_FONT_PATH_LOOSE_OVERRIDE = 1,
    NFL_FONT_PATH_INTERMEDIATE = 2,
    NFL_FONT_PATH_EXPLICIT = 3
} NflFontPathSource;

static void print_usage(const char *program)
{
    printf("Usage: %s [--assets PATH] [--model GLTF] "
           "[--menu host|nfl2k5|apf2k8] [--smoke FRAMES] "
           "[--screenshot PNG] [--model-only] [--nfl-font-atlas PNG "
           "--nfl-font-metrics TSV] [--nfl-tm-icon PNG]\n", program);
    printf("  --assets PATH   Mod asset root (default: assets/mod/common)\n");
    printf("  --model GLTF    Preview this glTF/GLB instead of models/player.gltf\n");
    printf("  --model-only    Render the selected model full-frame for inspection\n");
    printf("  --menu NAME     Host menu (default) or a recovered host "
           "representation\n");
    printf("  --nfl-font-atlas PNG   User-owned NFL font7 loose atlas override\n");
    printf("  --nfl-font-metrics TSV Matching recovered-host glyph metrics override\n");
    printf("  --nfl-tm-icon PNG      User-owned NFL |TM| inline icon override\n");
    printf("  --smoke FRAMES  Render a hidden bounded smoke test and exit\n");
    printf("  --screenshot PNG Capture the final smoke-test frame\n");
    printf("Environment: VC_FOOTBALL_ASSETS, VC_FOOTBALL_MODEL, "
           "VC_NFL2K5_FONT7_ATLAS, VC_NFL2K5_FONT7_METRICS, and "
           "VC_NFL2K5_TM_ICON may set loose overrides.\n");
}

static bool parse_positive_int(const char *text, int *value)
{
    if (text == NULL || text[0] == '\0' || value == NULL) {
        return false;
    }
    errno = 0;
    char *end = NULL;
    const long parsed = strtol(text, &end, 10);
    if (errno == ERANGE || end == text || *end != '\0' || parsed <= 0 ||
        parsed > INT_MAX) {
        return false;
    }
    *value = (int)parsed;
    return true;
}

static bool parse_options(int argc, char **argv, AppOptions *options)
{
    const char *environment_assets = getenv("VC_FOOTBALL_ASSETS");
    const char *environment_model = getenv("VC_FOOTBALL_MODEL");
    const char *environment_font_atlas = getenv("VC_NFL2K5_FONT7_ATLAS");
    const char *environment_font_metrics = getenv("VC_NFL2K5_FONT7_METRICS");
    const char *environment_tm_icon = getenv("VC_NFL2K5_TM_ICON");
    options->asset_root = environment_assets != NULL &&
                                  environment_assets[0] != '\0'
                              ? environment_assets
                              : "assets/mod/common";
    options->model_path = environment_model != NULL &&
                                  environment_model[0] != '\0'
                              ? environment_model
                              : NULL;
    options->nfl_font_atlas_path =
        environment_font_atlas != NULL && environment_font_atlas[0] != '\0'
            ? environment_font_atlas
            : NULL;
    options->nfl_font_metrics_path =
        environment_font_metrics != NULL && environment_font_metrics[0] != '\0'
            ? environment_font_metrics
            : NULL;
    options->nfl_tm_icon_path =
        environment_tm_icon != NULL && environment_tm_icon[0] != '\0'
            ? environment_tm_icon
            : NULL;
    options->screenshot_path = NULL;
    options->smoke_frames = 0;
    options->model_only = false;
    options->menu_source = VC_MENU_SOURCE_HOST;
    options->asset_root_explicit = environment_assets != NULL &&
                                   environment_assets[0] != '\0';
    options->nfl_font_paths_explicit =
        options->nfl_font_atlas_path != NULL ||
        options->nfl_font_metrics_path != NULL;
    options->nfl_tm_icon_explicit = options->nfl_tm_icon_path != NULL;
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--assets") == 0) {
            if (i + 1 >= argc || argv[i + 1][0] == '\0') {
                fprintf(stderr, "--assets requires a non-empty path\n");
                return false;
            }
            options->asset_root = argv[++i];
            options->asset_root_explicit = true;
        } else if (strcmp(argv[i], "--model") == 0) {
            if (i + 1 >= argc || argv[i + 1][0] == '\0') {
                fprintf(stderr, "--model requires a non-empty path\n");
                return false;
            }
            options->model_path = argv[++i];
        } else if (strcmp(argv[i], "--menu") == 0) {
            if (i + 1 >= argc ||
                !vc_menu_source_parse(argv[i + 1], &options->menu_source)) {
                fprintf(stderr,
                        "--menu requires one of: host, nfl2k5, apf2k8\n");
                return false;
            }
            ++i;
        } else if (strcmp(argv[i], "--model-only") == 0) {
            options->model_only = true;
        } else if (strcmp(argv[i], "--nfl-font-atlas") == 0) {
            if (i + 1 >= argc || argv[i + 1][0] == '\0') {
                fprintf(stderr,
                        "--nfl-font-atlas requires a non-empty PNG path\n");
                return false;
            }
            options->nfl_font_atlas_path = argv[++i];
            options->nfl_font_paths_explicit = true;
        } else if (strcmp(argv[i], "--nfl-font-metrics") == 0) {
            if (i + 1 >= argc || argv[i + 1][0] == '\0') {
                fprintf(stderr,
                        "--nfl-font-metrics requires a non-empty TSV path\n");
                return false;
            }
            options->nfl_font_metrics_path = argv[++i];
            options->nfl_font_paths_explicit = true;
        } else if (strcmp(argv[i], "--nfl-tm-icon") == 0) {
            if (i + 1 >= argc || argv[i + 1][0] == '\0') {
                fprintf(stderr,
                        "--nfl-tm-icon requires a non-empty PNG path\n");
                return false;
            }
            options->nfl_tm_icon_path = argv[++i];
            options->nfl_tm_icon_explicit = true;
        } else if (strcmp(argv[i], "--smoke") == 0) {
            if (i + 1 >= argc ||
                !parse_positive_int(argv[i + 1], &options->smoke_frames)) {
                fprintf(stderr, "--smoke requires a positive frame count\n");
                return false;
            }
            ++i;
        } else if (strcmp(argv[i], "--screenshot") == 0) {
            if (i + 1 >= argc || argv[i + 1][0] == '\0') {
                fprintf(stderr, "--screenshot requires an output path\n");
                return false;
            }
            options->screenshot_path = argv[++i];
        } else if (strcmp(argv[i], "--help") == 0 ||
                   strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            exit(EXIT_SUCCESS);
        } else {
            fprintf(stderr, "Unknown option: %s\n", argv[i]);
            return false;
        }
    }
    if (options->screenshot_path != NULL && options->smoke_frames == 0) {
        options->smoke_frames = 1;
    }
    if (options->model_only && options->model_path == NULL &&
        environment_model == NULL) {
        fprintf(stderr, "--model-only requires --model or VC_FOOTBALL_MODEL\n");
        return false;
    }
    if ((options->nfl_font_atlas_path == NULL) !=
        (options->nfl_font_metrics_path == NULL)) {
        fprintf(stderr,
                "NFL font7 override requires both atlas PNG and metrics TSV\n");
        return false;
    }
    return true;
}

static bool path_exists(const char *path)
{
    struct stat status;
    return stat(path, &status) == 0 && S_ISREG(status.st_mode);
}

static bool directory_exists(const char *path)
{
    struct stat status;
    return path != NULL && path[0] != '\0' && stat(path, &status) == 0 &&
           S_ISDIR(status.st_mode);
}

static bool find_installed_asset_root(char *destination, size_t capacity)
{
    if (destination == NULL || capacity < 2) {
        return false;
    }
    const ssize_t length = readlink("/proc/self/exe", destination,
                                    capacity - 1U);
    if (length <= 0 || (size_t)length >= capacity - 1U) {
        return false;
    }
    destination[length] = '\0';
    char *separator = strrchr(destination, '/');
    if (separator == NULL) {
        return false;
    }
    *separator = '\0';
    const size_t directory_length = strlen(destination);
    const int count = snprintf(destination + directory_length,
                               capacity - directory_length, "/%s",
                               VC_INSTALL_ASSET_RELATIVE);
    return count >= 0 && (size_t)count < capacity - directory_length &&
           directory_exists(destination);
}

static bool asset_path(char *destination, size_t capacity, const char *root,
                       const char *relative)
{
    if (destination == NULL || capacity == 0 || root == NULL ||
        relative == NULL) {
        return false;
    }
    const int count = snprintf(destination, capacity, "%s/%s", root, relative);
    return count >= 0 && (size_t)count < capacity;
}

static const char *nfl_font_path_source_name(NflFontPathSource source)
{
    switch (source) {
    case NFL_FONT_PATH_LOOSE_OVERRIDE: return "loose mod override";
    case NFL_FONT_PATH_INTERMEDIATE: return "title-derived intermediate";
    case NFL_FONT_PATH_EXPLICIT: return "explicit loose override";
    case NFL_FONT_PATH_EXPECTED_OVERRIDE: return "expected loose override";
    default: return "unknown";
    }
}

static bool resolve_nfl_font_paths(const AppOptions *options,
                                   char *atlas, size_t atlas_capacity,
                                   char *metrics, size_t metrics_capacity,
                                   NflFontPathSource *source)
{
    if (options == NULL || atlas == NULL || metrics == NULL || source == NULL) {
        return false;
    }
    if (options->nfl_font_paths_explicit) {
        const int atlas_count = snprintf(atlas, atlas_capacity, "%s",
                                         options->nfl_font_atlas_path);
        const int metrics_count = snprintf(metrics, metrics_capacity, "%s",
                                           options->nfl_font_metrics_path);
        *source = NFL_FONT_PATH_EXPLICIT;
        return atlas_count >= 0 && (size_t)atlas_count < atlas_capacity &&
               metrics_count >= 0 && (size_t)metrics_count < metrics_capacity;
    }

    char loose_atlas[4096];
    char loose_metrics[4096];
    if (!asset_path(loose_atlas, sizeof(loose_atlas), options->asset_root,
                    "ui/nfl2k5_font7.png") ||
        !asset_path(loose_metrics, sizeof(loose_metrics), options->asset_root,
                    "ui/nfl2k5_font7.metrics.tsv")) {
        return false;
    }
    const bool loose_available = path_exists(loose_atlas) &&
                                 path_exists(loose_metrics);
    const char *chosen_atlas = loose_atlas;
    const char *chosen_metrics = loose_metrics;
    *source = loose_available ? NFL_FONT_PATH_LOOSE_OVERRIDE
                              : NFL_FONT_PATH_EXPECTED_OVERRIDE;
    if (!loose_available &&
        path_exists("assets/intermediate/nfl2k5/fonts/font7.png") &&
        path_exists("assets/intermediate/nfl2k5/fonts/font7.metrics.tsv")) {
        chosen_atlas = "assets/intermediate/nfl2k5/fonts/font7.png";
        chosen_metrics = "assets/intermediate/nfl2k5/fonts/font7.metrics.tsv";
        *source = NFL_FONT_PATH_INTERMEDIATE;
    }
    const int atlas_count = snprintf(atlas, atlas_capacity, "%s",
                                     chosen_atlas);
    const int metrics_count = snprintf(metrics, metrics_capacity, "%s",
                                       chosen_metrics);
    return atlas_count >= 0 && (size_t)atlas_count < atlas_capacity &&
           metrics_count >= 0 && (size_t)metrics_count < metrics_capacity;
}

static bool resolve_nfl_tm_icon_path(const AppOptions *options,
                                     char *path, size_t capacity,
                                     NflFontPathSource *source)
{
    if (options == NULL || path == NULL || source == NULL || capacity == 0U) {
        return false;
    }
    if (options->nfl_tm_icon_explicit) {
        const int count = snprintf(path, capacity, "%s",
                                   options->nfl_tm_icon_path);
        *source = NFL_FONT_PATH_EXPLICIT;
        return count >= 0 && (size_t)count < capacity;
    }
    char loose_path[4096];
    if (!asset_path(loose_path, sizeof(loose_path), options->asset_root,
                    "ui/nfl2k5_tm.png")) {
        return false;
    }
    const char *chosen = loose_path;
    *source = path_exists(loose_path) ? NFL_FONT_PATH_LOOSE_OVERRIDE
                                     : NFL_FONT_PATH_EXPECTED_OVERRIDE;
    const char *intermediate =
        "assets/intermediate/nfl2k5/textures/"
        "outer_0003_8ee9eeed/0047_tm.png";
    if (*source == NFL_FONT_PATH_EXPECTED_OVERRIDE &&
        path_exists(intermediate)) {
        chosen = intermediate;
        *source = NFL_FONT_PATH_INTERMEDIATE;
    }
    const int count = snprintf(path, capacity, "%s", chosen);
    return count >= 0 && (size_t)count < capacity;
}

static void activate_host_menu(size_t selected, bool *running, char *status,
                               size_t status_size)
{
    switch (selected) {
    case 0:
        snprintf(status, status_size,
                 "PORTME: GAMEPLAY ENTRY 0X84BE9D08 IS NOT WIRED YET");
        break;
    case 1:
        snprintf(status, status_size,
                 "ROSTER INVENTORY IS PROVED  PORTME: SAFE IMPORT AND EDIT UI");
        break;
    case 2:
        snprintf(status, status_size,
                 "MOD PNG RELOAD IS LIVE  GLTF VALIDATION IS AVAILABLE");
        break;
    case 3:
        *running = false;
        break;
    default:
        break;
    }
}

static void activate_recovered_menu(const VcMenuModel *menu, size_t selected,
                                    char *status, size_t status_size)
{
    if (menu == NULL || selected >= menu->row_count ||
        !vc_menu_format_host_activation(menu, selected, status, status_size)) {
        snprintf(status, status_size,
                 "HOST VIEW ONLY  INVALID RECOVERED MENU ACTION");
        return;
    }
    const VcMenuAction *action = &menu->rows[selected].action;
    fprintf(stderr,
            "menu host representation activation: title=%s row=%zu "
            "record=0x%08" PRIX32 " label_va=0x%08" PRIX32
            " label=\"%s\" source_type=%" PRIu32 " kind=%s "
            "target=0x%08" PRIX32 " activation=0x%08" PRIX32
            " dispatch=0x%08" PRIX32 " downstream=0x%08" PRIX32
            " callback=0x%08" PRIX32
            " preflight=0x%08" PRIX32
            "; guest code not executed\n",
            menu->cli_name, selected, menu->rows[selected].source_address,
            menu->rows[selected].label_address, menu->rows[selected].label,
            action->source_type_code,
            vc_menu_action_kind_name(action->kind),
            action->target_state_address, action->activation_address,
            action->dispatch_address, action->downstream_address,
            action->callback_address, action->preflight_callback_address);
}

static void activate_selected_menu(const VcMenuModel *menu, size_t selected,
                                   bool *running, char *status,
                                   size_t status_size)
{
    if (menu != NULL && menu->recovered_guest_data) {
        activate_recovered_menu(menu, selected, status, status_size);
        return;
    }
    activate_host_menu(selected, running, status, status_size);
}

static void draw_fallback_logo(VcUiRenderer *ui, float x, float y, float size)
{
    const float cell = size / 8.0f;
    for (int row = 0; row < 8; ++row) {
        for (int column = 0; column < 8; ++column) {
            const bool bright = ((row + column) & 1) == 0;
            vc_ui_rect(ui, x + (float)column * cell, y + (float)row * cell,
                       cell, cell,
                       bright ? 0.85f : 0.08f,
                       bright ? 0.20f : 0.12f,
                       bright ? 0.08f : 0.20f, 1.0f);
        }
    }
    vc_ui_text(ui, "PNG", x + size * 0.24f, y + size * 0.40f,
               size / 42.0f, 1.0f, 1.0f, 1.0f, 1.0f);
}

static void render_menu(VcUiRenderer *ui, const VcPngTexture *logo,
                        const VcBitmapFont *nfl_font,
                        const VcPngTexture *nfl_tm_icon, VcModel *model,
                        const VcMenuModel *menu,
                        size_t selected, const char *status,
                        float animation_seconds, float preview_angle)
{
    const bool recovered = menu->recovered_guest_data;
    const bool recovered_nfl_font =
        menu->source == VC_MENU_SOURCE_NFL2K5 &&
        vc_bitmap_font_ready(nfl_font);
    const float width = (float)ui->width;
    const float height = (float)ui->height;

    vc_ui_begin(ui, 0.018f, 0.027f, 0.055f, 1.0f);
    vc_ui_rect(ui, 0.0f, 0.0f, width, 10.0f, 0.86f, 0.15f, 0.06f, 1.0f);
    vc_ui_rect(ui, 0.0f, height - 10.0f, width, 10.0f,
               0.86f, 0.15f, 0.06f, 1.0f);

    const float panel_x = width * 0.08f;
    const float panel_y = height * 0.12f;
    const float panel_w = width * 0.84f;
    const float panel_h = height * 0.74f;
    vc_ui_rect(ui, panel_x, panel_y, panel_w, panel_h,
               0.04f, 0.075f, 0.13f, 0.96f);
    vc_ui_rect(ui, panel_x, panel_y, panel_w, 4.0f,
               0.22f, 0.45f, 0.72f, 1.0f);

    const float preview_x = panel_x + panel_w * 0.62f;
    const float preview_y = panel_y + panel_h * 0.49f;
    const float preview_w = panel_w * 0.32f;
    const float preview_h = panel_h * 0.28f;
    vc_ui_rect(ui, preview_x - 3.0f, preview_y - 3.0f,
               preview_w + 6.0f, preview_h + 6.0f,
               0.22f, 0.45f, 0.72f, 0.72f);
    vc_ui_rect(ui, preview_x, preview_y, preview_w, preview_h,
               0.015f, 0.025f, 0.05f, 1.0f);
    vc_model_render_preview(model, ui->width, ui->height,
                            (int)preview_x, (int)preview_y,
                            (int)preview_w, (int)preview_h,
                            animation_seconds, preview_angle);
    vc_ui_resume(ui);
    vc_ui_text(ui, "LOOSE GLTF PREVIEW", preview_x + 12.0f,
               preview_y + preview_h - 22.0f, 1.5f,
               0.58f, 0.76f, 0.94f, 1.0f);

    vc_ui_text(ui, menu->host_heading, panel_x + 36.0f,
               panel_y + 30.0f, 4.0f, 0.96f, 0.97f, 1.0f, 1.0f);
    vc_ui_text(ui, recovered ? "RECOVERED HOST REPRESENTATION"
                             : "RESEARCH SHELL",
               panel_x + 38.0f,
               panel_y + 66.0f, 2.0f, 0.45f, 0.70f, 0.92f, 1.0f);
    if (recovered) {
        vc_ui_text(ui,
                   "HOST VIEW ONLY  NO GUEST CODE OR ORIGINAL RENDERING",
                   panel_x + 38.0f, panel_y + 96.0f, 1.45f,
                   0.98f, 0.60f, 0.22f, 1.0f);
    }

    const float logo_size = height * 0.31f;
    const float logo_x = panel_x + panel_w - logo_size - 52.0f;
    const float logo_y = panel_y + 58.0f;
    if (logo->id != 0) {
        vc_ui_texture(ui, logo->id, logo_x, logo_y, logo_size, logo_size,
                      1.0f);
    } else {
        draw_fallback_logo(ui, logo_x, logo_y, logo_size);
    }

    const float menu_x = panel_x + 38.0f;
    const float menu_y = panel_y + (recovered ? 126.0f : 132.0f);
    const float item_w = panel_w * 0.48f;
    const float item_h = recovered ? 36.0f : 56.0f;
    const float item_gap = recovered ? 7.0f : 12.0f;
    const float item_text_scale = recovered ? 2.15f : 3.0f;
    for (size_t i = 0; i < menu->row_count; ++i) {
        const float y = menu_y + (float)i * (item_h + item_gap);
        const bool active = i == selected;
        vc_ui_rect(ui, menu_x, y, item_w, item_h,
                   active ? 0.82f : 0.07f,
                   active ? 0.18f : 0.13f,
                   active ? 0.05f : 0.21f,
                   active ? 1.0f : 0.92f);
        if (active) {
            vc_ui_text(ui, ">", menu_x + 15.0f,
                       y + (recovered ? 10.0f : 17.0f), item_text_scale,
                       1.0f, 1.0f, 1.0f, 1.0f);
        }
        if (recovered_nfl_font) {
            /* PORTME(0x0014FDA0): this deliberately binds recovered font7
               glyphs to the existing host row boxes. Original title-space
               LAYT coordinates, style passes, and boot are not claimed. */
            vc_bitmap_font_text(ui, nfl_font, nfl_tm_icon,
                                menu->rows[i].label,
                                menu_x + 46.0f, y + 4.5f, 0.9f,
                                1.0f, 1.0f, 1.0f, 1.0f);
        } else {
            vc_ui_text(ui, menu->rows[i].label, menu_x + 46.0f,
                       y + (recovered ? 10.0f : 17.0f), item_text_scale,
                       1.0f, 1.0f, 1.0f, 1.0f);
        }
    }

    if (recovered) {
        char layout_identity[160];
        snprintf(layout_identity, sizeof(layout_identity),
                 "STATE LAYOUT %s  OUTER %" PRIu32 "  INNER %" PRIu32,
                 menu->state_layout.name, menu->state_layout.outer_index,
                 menu->state_layout.inner_index);
        vc_ui_text(ui, layout_identity, preview_x,
                   panel_y + panel_h - 112.0f, 1.35f,
                   0.54f, 0.72f, 0.92f, 1.0f);
    }

    vc_ui_text(ui, status, panel_x + 38.0f, panel_y + panel_h - 80.0f,
               2.0f, 0.95f, 0.74f, 0.30f, 1.0f);
    vc_ui_text(ui,
               "ARROWS OR DPAD NAVIGATE  ENTER OR A SELECT  F5 RELOADS MOD ASSETS",
               panel_x + 38.0f, panel_y + panel_h - 42.0f, 1.65f,
               0.66f, 0.75f, 0.86f, 1.0f);

    char version[96];
    snprintf(version, sizeof(version), "HOST SCAFFOLD %s  OPENGL 3.3",
             VC_PORT_VERSION);
    vc_ui_text(ui, version, 18.0f, height - 30.0f, 1.5f,
               0.65f, 0.70f, 0.80f, 1.0f);
}

static void render_model_only(VcUiRenderer *ui, VcModel *model,
                              float animation_seconds,
                              float preview_angle)
{
    vc_ui_begin(ui, 0.018f, 0.027f, 0.055f, 1.0f);
    vc_model_render_preview(model, ui->width, ui->height, 0, 0,
                            ui->width, ui->height, animation_seconds,
                            preview_angle);
}

int main(int argc, char **argv)
{
    AppOptions options;
    if (!parse_options(argc, argv, &options)) {
        print_usage(argv[0]);
        return EXIT_FAILURE;
    }
    const VcMenuModel *menu = vc_menu_model(options.menu_source);
    if (menu == NULL || menu->row_count == 0) {
        fprintf(stderr, "menu: internal model lookup failed\n");
        return EXIT_FAILURE;
    }

    char installed_asset_root[4096];
    if (!options.asset_root_explicit && !directory_exists(options.asset_root) &&
        find_installed_asset_root(installed_asset_root,
                                  sizeof(installed_asset_root))) {
        options.asset_root = installed_asset_root;
    }

    char logo_path[4096];
    char default_model_path[4096];
    char audio_path[4096];
    char nfl_font_atlas_path[4096] = {0};
    char nfl_font_metrics_path[4096] = {0};
    char nfl_tm_icon_path[4096] = {0};
    NflFontPathSource nfl_font_path_source =
        NFL_FONT_PATH_EXPECTED_OVERRIDE;
    NflFontPathSource nfl_tm_icon_path_source =
        NFL_FONT_PATH_EXPECTED_OVERRIDE;
    if (!asset_path(logo_path, sizeof(logo_path), options.asset_root,
                    "ui/team_logo.png") ||
        !asset_path(audio_path, sizeof(audio_path), options.asset_root,
                    "audio/menu_select.wav")) {
        fprintf(stderr, "Asset root is too long: %s\n", options.asset_root);
        return EXIT_FAILURE;
    }
    if (menu->source == VC_MENU_SOURCE_NFL2K5 &&
        !resolve_nfl_font_paths(&options, nfl_font_atlas_path,
                                sizeof(nfl_font_atlas_path),
                                nfl_font_metrics_path,
                                sizeof(nfl_font_metrics_path),
                                &nfl_font_path_source)) {
        fprintf(stderr, "NFL font7 loose asset path is too long\n");
        return EXIT_FAILURE;
    }
    if (menu->source == VC_MENU_SOURCE_NFL2K5 &&
        !resolve_nfl_tm_icon_path(&options, nfl_tm_icon_path,
                                  sizeof(nfl_tm_icon_path),
                                  &nfl_tm_icon_path_source)) {
        fprintf(stderr, "NFL TM loose asset path is too long\n");
        return EXIT_FAILURE;
    }
    if (options.model_path == NULL) {
        if (!asset_path(default_model_path, sizeof(default_model_path),
                        options.asset_root, "models/player.gltf")) {
            fprintf(stderr, "Asset root is too long: %s\n", options.asset_root);
            return EXIT_FAILURE;
        }
        options.model_path = default_model_path;
    }
    const char *model_path = options.model_path;
    fprintf(stderr, "assets: %s\n", options.asset_root);
    fprintf(stderr, "model override: %s\n", model_path);
    if (menu->source == VC_MENU_SOURCE_NFL2K5) {
        fprintf(stderr,
                "menu font: NFL2K5 font7 recovered host representation; "
                "original LAYT coordinates and boot are not claimed\n");
        fprintf(stderr, "menu font source: %s\n",
                nfl_font_path_source_name(nfl_font_path_source));
        fprintf(stderr, "menu TM icon source: %s\n",
                nfl_font_path_source_name(nfl_tm_icon_path_source));
        if (nfl_font_path_source == NFL_FONT_PATH_INTERMEDIATE) {
            fprintf(stderr,
                    "menu font boundary: title-derived font7 remains under "
                    "assets/intermediate and is not an installed mod asset\n");
        }
        if (nfl_tm_icon_path_source == NFL_FONT_PATH_INTERMEDIATE) {
            fprintf(stderr,
                    "menu TM boundary: title-derived icon remains under "
                    "assets/intermediate and is not an installed mod asset\n");
        }
    }
    if (menu->recovered_guest_data) {
        fprintf(stderr,
                "menu: %s recovered host representation; descriptor=0x%08"
                PRIX32 " state_layout=%s archive=%s outer=%" PRIu32
                " inner=%" PRIu32 " crc32=0x%08" PRIX32
                " type_id=0x%08" PRIX32
                "; guest code and original rendering are not running\n",
                menu->cli_name, menu->state_descriptor_address,
                menu->state_layout.name,
                menu->state_layout.archive_name != NULL
                    ? menu->state_layout.archive_name
                    : "<none>",
                menu->state_layout.outer_index, menu->state_layout.inner_index,
                menu->state_layout.name_crc32, menu->state_layout.type_id);
    } else {
        fprintf(stderr, "menu: host native research shell\n");
    }

    /* OpenAL owns audio in this scaffold. Requesting SDL audio would make an
       otherwise usable host fail merely because no SDL backend is available. */
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | SDL_INIT_TIMER |
                 SDL_INIT_EVENTS) != 0) {
        fprintf(stderr, "SDL initialization failed: %s\n", SDL_GetError());
        return EXIT_FAILURE;
    }

    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 24);
    SDL_GL_SetAttribute(SDL_GL_FRAMEBUFFER_SRGB_CAPABLE, 1);

    Uint32 window_flags = SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE |
                          SDL_WINDOW_ALLOW_HIGHDPI;
    if (options.smoke_frames > 0) {
        window_flags |= SDL_WINDOW_HIDDEN;
    } else {
        window_flags |= SDL_WINDOW_SHOWN;
    }
    SDL_Window *window = SDL_CreateWindow(
        "2K Football Linux Port Research Shell", SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED, 1280, 720, window_flags);
    if (window == NULL) {
        fprintf(stderr, "Window creation failed: %s\n", SDL_GetError());
        SDL_Quit();
        return EXIT_FAILURE;
    }

    SDL_GLContext gl_context = SDL_GL_CreateContext(window);
    if (gl_context == NULL) {
        fprintf(stderr, "OpenGL context creation failed: %s\n", SDL_GetError());
        SDL_DestroyWindow(window);
        SDL_Quit();
        return EXIT_FAILURE;
    }
    if (SDL_GL_MakeCurrent(window, gl_context) != 0) {
        fprintf(stderr, "Could not activate OpenGL context: %s\n",
                SDL_GetError());
        SDL_GL_DeleteContext(gl_context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return EXIT_FAILURE;
    }
    SDL_GL_SetSwapInterval(options.smoke_frames > 0 ? 0 : 1);

    glewExperimental = GL_TRUE;
    const GLenum glew_result = glewInit();
    glGetError();
    if (glew_result != GLEW_OK) {
        fprintf(stderr, "GLEW initialization failed: %s\n",
                glewGetErrorString(glew_result));
        SDL_GL_DeleteContext(gl_context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return EXIT_FAILURE;
    }
    const GLubyte *renderer_name = glGetString(GL_RENDERER);
    const GLubyte *version_name = glGetString(GL_VERSION);
    fprintf(stderr, "renderer: %s\n",
            renderer_name != NULL ? (const char *)renderer_name : "unknown");
    fprintf(stderr, "OpenGL: %s\n",
            version_name != NULL ? (const char *)version_name : "unknown");

    int drawable_width = 0;
    int drawable_height = 0;
    SDL_GL_GetDrawableSize(window, &drawable_width, &drawable_height);
    if (drawable_width <= 0 || drawable_height <= 0) {
        fprintf(stderr, "OpenGL drawable has invalid dimensions %dx%d\n",
                drawable_width, drawable_height);
        SDL_GL_DeleteContext(gl_context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return EXIT_FAILURE;
    }
    VcUiRenderer ui;
    if (!vc_ui_init(&ui, drawable_width, drawable_height)) {
        fprintf(stderr, "UI renderer initialization failed\n");
        SDL_GL_DeleteContext(gl_context);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return EXIT_FAILURE;
    }
    vc_xdk_init();

    VcPngTexture logo = {0};
    if (path_exists(logo_path)) {
        vc_png_texture_load(&logo, logo_path);
    } else {
        fprintf(stderr,
                "texture: %s not found; using generated checkerboard fallback\n",
                logo_path);
    }
    VcModel model = {0};
    if (path_exists(model_path)) {
        vc_model_load(&model, model_path);
    }
    VcAudioClip menu_sound = {0};
    if (path_exists(audio_path)) {
        vc_audio_clip_load(&menu_sound, audio_path);
    }
    VcBitmapFont nfl_font = {0};
    VcPngTexture nfl_tm_icon = {0};
    if (menu->source == VC_MENU_SOURCE_NFL2K5) {
        if (!path_exists(nfl_font_atlas_path) ||
            !path_exists(nfl_font_metrics_path) ||
            !vc_bitmap_font_load(&nfl_font, nfl_font_atlas_path,
                                 nfl_font_metrics_path)) {
            fprintf(stderr,
                    "bitmap font: NFL font7 loose assets unavailable; "
                    "row labels use the 5x7 host fallback\n");
        }
        if (!path_exists(nfl_tm_icon_path) ||
            !vc_png_texture_load(&nfl_tm_icon, nfl_tm_icon_path)) {
            fprintf(stderr,
                    "formatted token: NFL TM loose PNG unavailable; "
                    "source markup remains visible\n");
        } else {
            fprintf(stderr,
                    "formatted token: |TM| uses recovered slot 9 loose PNG; "
                    "default original-menu draw is not claimed\n");
        }
    }

    bool running = true;
    size_t selected = 0;
    int rendered_frames = 0;
    Uint64 animation_start_counter = SDL_GetPerformanceCounter();
    const Uint64 performance_frequency = SDL_GetPerformanceFrequency();
    Uint32 last_reload_check = SDL_GetTicks();
    bool screenshot_written = false;
    bool screenshot_ok = true;
    char status[256];
    if (menu->recovered_guest_data) {
        snprintf(status, sizeof(status),
                 "HOST VIEW ONLY  STATE DESCRIPTOR 0X%08" PRIX32
                 "  ORIGINAL MENU NOT LAUNCHED",
                 menu->state_descriptor_address);
    } else {
        snprintf(status, sizeof(status),
                 "NATIVE HOST READY  ORIGINAL GAME LOGIC IS NOT YET CONNECTED");
    }

    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            vc_xdk_handle_event(&event);
            if (event.type == SDL_QUIT) {
                running = false;
            } else if (event.type == SDL_WINDOWEVENT &&
                       (event.window.event == SDL_WINDOWEVENT_SIZE_CHANGED ||
                        event.window.event == SDL_WINDOWEVENT_RESIZED)) {
                SDL_GL_GetDrawableSize(window, &drawable_width, &drawable_height);
                vc_ui_resize(&ui, drawable_width, drawable_height);
            } else if (event.type == SDL_KEYDOWN && !event.key.repeat) {
                switch (event.key.keysym.sym) {
                case SDLK_UP:
                case SDLK_w:
                    selected = vc_menu_move_selection(menu, selected, -1);
                    vc_audio_clip_play(&menu_sound);
                    break;
                case SDLK_DOWN:
                case SDLK_s:
                    selected = vc_menu_move_selection(menu, selected, 1);
                    vc_audio_clip_play(&menu_sound);
                    break;
                case SDLK_RETURN:
                case SDLK_SPACE:
                    vc_audio_clip_play(&menu_sound);
                    activate_selected_menu(menu, selected, &running, status,
                                           sizeof(status));
                    break;
                case SDLK_F5:
                {
                    bool reloaded_any = false;
                    bool reload_failed = false;
                    if (path_exists(logo_path)) {
                        if (vc_png_texture_load(&logo, logo_path)) {
                            reloaded_any = true;
                        } else {
                            reload_failed = true;
                        }
                    }
                    if (path_exists(model_path)) {
                        VcModel replacement = {0};
                        if (vc_model_load(&replacement, model_path)) {
                            vc_model_release(&model);
                            model = replacement;
                            animation_start_counter =
                                SDL_GetPerformanceCounter();
                            reloaded_any = true;
                        } else {
                            reload_failed = true;
                        }
                    }
                    if (path_exists(audio_path)) {
                        VcAudioClip replacement = {0};
                        if (vc_audio_clip_load(&replacement, audio_path)) {
                            vc_audio_clip_release(&menu_sound);
                            menu_sound = replacement;
                            reloaded_any = true;
                        } else {
                            reload_failed = true;
                        }
                    }
                    if (menu->source == VC_MENU_SOURCE_NFL2K5) {
                        const bool font_paths_ok = resolve_nfl_font_paths(
                            &options, nfl_font_atlas_path,
                            sizeof(nfl_font_atlas_path),
                            nfl_font_metrics_path,
                            sizeof(nfl_font_metrics_path),
                            &nfl_font_path_source);
                        if (font_paths_ok &&
                            path_exists(nfl_font_atlas_path) &&
                            path_exists(nfl_font_metrics_path) &&
                            vc_bitmap_font_load(&nfl_font,
                                                nfl_font_atlas_path,
                                                nfl_font_metrics_path)) {
                            reloaded_any = true;
                        } else if (options.nfl_font_paths_explicit) {
                            reload_failed = true;
                        }
                        const bool tm_path_ok = resolve_nfl_tm_icon_path(
                            &options, nfl_tm_icon_path,
                            sizeof(nfl_tm_icon_path),
                            &nfl_tm_icon_path_source);
                        if (tm_path_ok && path_exists(nfl_tm_icon_path) &&
                            vc_png_texture_load(&nfl_tm_icon,
                                                nfl_tm_icon_path)) {
                            reloaded_any = true;
                        } else if (options.nfl_tm_icon_explicit) {
                            reload_failed = true;
                        }
                    }
                    snprintf(status, sizeof(status), "%s",
                             reload_failed
                                 ? "MOD ASSET RELOAD PARTIAL  CHECK TERMINAL LOG"
                                 : reloaded_any
                                       ? "RELOADED LOOSE PNG GLTF WAV FONT AND TM ASSETS"
                                       : "NO LOOSE MOD ASSETS FOUND TO RELOAD");
                    break;
                }
                case SDLK_ESCAPE:
                    running = false;
                    break;
                default:
                    break;
                }
            } else if (event.type == SDL_CONTROLLERBUTTONDOWN) {
                switch (event.cbutton.button) {
                case SDL_CONTROLLER_BUTTON_DPAD_UP:
                    selected = vc_menu_move_selection(menu, selected, -1);
                    vc_audio_clip_play(&menu_sound);
                    break;
                case SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                    selected = vc_menu_move_selection(menu, selected, 1);
                    vc_audio_clip_play(&menu_sound);
                    break;
                case SDL_CONTROLLER_BUTTON_A:
                    vc_audio_clip_play(&menu_sound);
                    activate_selected_menu(menu, selected, &running, status,
                                           sizeof(status));
                    break;
                case SDL_CONTROLLER_BUTTON_B:
                case SDL_CONTROLLER_BUTTON_BACK:
                    running = false;
                    break;
                default:
                    break;
                }
            }
        }

        const Uint32 now = SDL_GetTicks();
        if (now - last_reload_check >= 500U) {
            bool font_reloaded = false;
            bool tm_reloaded = false;
            const bool discovered = logo.source_path[0] == '\0' &&
                                    path_exists(logo_path) &&
                                    vc_png_texture_load(&logo, logo_path);
            if (discovered || vc_png_texture_reload_if_changed(&logo)) {
                snprintf(status, sizeof(status),
                         "HOT RELOADED MOD TEXTURE UI TEAM LOGO PNG");
            }
            if (menu->source == VC_MENU_SOURCE_NFL2K5 &&
                resolve_nfl_font_paths(&options, nfl_font_atlas_path,
                                       sizeof(nfl_font_atlas_path),
                                       nfl_font_metrics_path,
                                       sizeof(nfl_font_metrics_path),
                                       &nfl_font_path_source) &&
                path_exists(nfl_font_atlas_path) &&
                path_exists(nfl_font_metrics_path)) {
                const bool source_changed =
                    !vc_bitmap_font_ready(&nfl_font) ||
                    strcmp(nfl_font.atlas_path, nfl_font_atlas_path) != 0 ||
                    strcmp(nfl_font.metrics_path, nfl_font_metrics_path) != 0;
                font_reloaded = source_changed
                    ? vc_bitmap_font_load(&nfl_font, nfl_font_atlas_path,
                                          nfl_font_metrics_path)
                    : vc_bitmap_font_reload_if_changed(&nfl_font);
            }
            if (font_reloaded) {
                snprintf(status, sizeof(status),
                         "HOT RELOADED NFL2K5 FONT7 LOOSE PNG AND METRICS");
            }
            if (menu->source == VC_MENU_SOURCE_NFL2K5 &&
                resolve_nfl_tm_icon_path(&options, nfl_tm_icon_path,
                                         sizeof(nfl_tm_icon_path),
                                         &nfl_tm_icon_path_source) &&
                path_exists(nfl_tm_icon_path)) {
                const bool source_changed = nfl_tm_icon.id == 0U ||
                    strcmp(nfl_tm_icon.source_path, nfl_tm_icon_path) != 0;
                tm_reloaded = source_changed
                    ? vc_png_texture_load(&nfl_tm_icon, nfl_tm_icon_path)
                    : vc_png_texture_reload_if_changed(&nfl_tm_icon);
            }
            if (tm_reloaded) {
                snprintf(status, sizeof(status),
                         "HOT RELOADED NFL2K5 TM INLINE ICON PNG");
            }
            last_reload_check = now;
        }

        const float animation_seconds = options.smoke_frames > 0
            ? (float)rendered_frames / 60.0f
            : performance_frequency != 0U
                ? (float)((double)(SDL_GetPerformanceCounter() -
                                    animation_start_counter) /
                          (double)performance_frequency)
                : 0.0f;
        if (options.model_only) {
            render_model_only(&ui, &model, animation_seconds,
                              animation_seconds * 0.6f);
        } else {
            render_menu(&ui, &logo, &nfl_font, &nfl_tm_icon, &model, menu,
                        selected, status, animation_seconds,
                        animation_seconds * 0.6f);
        }
        if (options.screenshot_path != NULL &&
            rendered_frames + 1 >= options.smoke_frames) {
            screenshot_written = true;
            screenshot_ok = vc_png_write_framebuffer(options.screenshot_path,
                                                      drawable_width,
                                                      drawable_height);
            if (!screenshot_ok) {
                fprintf(stderr, "screenshot: could not write %s\n",
                        options.screenshot_path);
                running = false;
            }
        }
        SDL_GL_SwapWindow(window);
        ++rendered_frames;
        if (options.smoke_frames > 0 && rendered_frames >= options.smoke_frames) {
            running = false;
        }
    }

    vc_audio_clip_release(&menu_sound);
    vc_model_release(&model);
    vc_bitmap_font_destroy(&nfl_font);
    vc_png_texture_destroy(&nfl_tm_icon);
    vc_png_texture_destroy(&logo);
    vc_xdk_shutdown();
    vc_ui_destroy(&ui);
    SDL_GL_DeleteContext(gl_context);
    SDL_DestroyWindow(window);
    SDL_Quit();

    if (options.screenshot_path != NULL &&
        (!screenshot_written || !screenshot_ok)) {
        fprintf(stderr, "SMOKE FAIL: screenshot capture did not complete\n");
        return EXIT_FAILURE;
    }
    if (options.smoke_frames > 0 && rendered_frames < options.smoke_frames) {
        fprintf(stderr, "SMOKE FAIL: rendered %d of %d requested frames\n",
                rendered_frames, options.smoke_frames);
        return EXIT_FAILURE;
    }
    if (options.smoke_frames > 0) {
        printf("SMOKE PASS: rendered %d frames\n", rendered_frames);
    }
    return EXIT_SUCCESS;
}

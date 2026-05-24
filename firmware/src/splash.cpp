#include "splash.h"
#ifdef SPLASH_THEME_WINE
#include "splash_animations_wine.h"
#else
#include "splash_animations.h"
#endif
#include "theme.h"
#include "usage_rate.h"
#include "hal/board_caps.h"
#include <Arduino.h>
#include <string.h>
#include <esp_heap_caps.h>

// Square canvas sized to fit the smaller display dimension. Cell pitch is
// derived per sprite from its `grid` field so 20×20 and 48×48 sets share the
// same render path and the same canvas — bigger grids just get smaller cells.
static int  canvas_dim = 480;     // recomputed in splash_init()

// Background fallback when palette is missing
#define COL_EMPTY    0x0000  // true black (matches THEME_BG)

LV_FONT_DECLARE(font_styrene_28);

static lv_obj_t *splash_container = NULL;
static lv_obj_t *canvas = NULL;
static lv_obj_t *label_status = NULL;     // shown only when no animations loaded
static uint16_t *canvas_buf = NULL;        // 480x480 RGB565 (PSRAM)

static uint16_t cur_anim = 0;
static uint16_t cur_frame = 0;
static uint32_t frame_started_ms = 0;
static uint32_t last_pick_ms = 0;
static bool active = false;

// While splash is showing, auto-cycle to the next animation in the current
// rate-driven group every this many ms.
#define SPLASH_ROTATE_INTERVAL_MS 20000

// Usage-rate animation groups: 4 groups × up to 4 animations each.
// Filled at init by matching literal names from splash_anims[].
#define GROUP_COUNT 4
#define GROUP_MAX   4
static int8_t  group_lists[GROUP_COUNT][GROUP_MAX];
static uint8_t group_size[GROUP_COUNT] = {0};
static uint8_t group_rotation[GROUP_COUNT] = {0};

#ifdef SPLASH_THEME_WINE
// Wine-Edition mapping. 48×48 PixelLab-generated sprites with full wine
// detail (gold-label bottle, bordeaux-filled glass, grape cluster with leaf,
// natural cork). Same sprite can appear in multiple groups for rotation.
static const char* GROUP_NAMES[GROUP_COUNT][GROUP_MAX] = {
    // Group 0 — idle / sleepy (cork resting, grapes still on the vine)
    { "wine cork", "wine grapes", NULL, NULL },
    // Group 1 — normal pace (glass poured, bottle next to it)
    { "wine glass red", "wine bottle bordeaux", NULL, NULL },
    // Group 2 — active (glass with bordeaux, grapes alongside)
    { "wine glass red", "wine grapes", NULL, NULL },
    // Group 3 — heavy (full table rotation)
    { "wine bottle bordeaux", "wine glass red", "wine grapes", NULL },
};
#else
static const char* GROUP_NAMES[GROUP_COUNT][GROUP_MAX] = {
    // Group 0 — idle / sleepy
    { "expression sleep", "idle breathe", "idle blink", "expression wink" },
    // Group 1 — normal pace
    { "idle look around", "work think", "work coding", NULL },
    // Group 2 — active
    { "dance sway", "expression surprise", "dance bounce", NULL },
    // Group 3 — heavy
    { "dance bounce dj", "dance sway dj", "dance djmix", NULL },
};
#endif

static void resolve_group_lists(void) {
    for (int g = 0; g < GROUP_COUNT; g++) {
        group_size[g] = 0;
        for (int s = 0; s < GROUP_MAX; s++) {
            group_lists[g][s] = -1;
            const char* want = GROUP_NAMES[g][s];
            if (!want) continue;
            for (int i = 0; i < SPLASH_ANIM_COUNT; i++) {
                if (strcmp(splash_anims[i].name, want) == 0) {
                    group_lists[g][group_size[g]++] = (int8_t)i;
                    break;
                }
            }
        }
    }
}

static uint16_t *row_buf = NULL;   // scratch row, sized to canvas_dim

static void render_anim_frame(const splash_anim_def_t *a, uint16_t frame_idx) {
    if (!row_buf || !canvas_buf || !a) return;
    const int grid = a->grid;
    if (grid <= 0) return;
    int cell = canvas_dim / grid;
    if (cell < 1) cell = 1;
    const int sprite_dim = grid * cell;                  // may be < canvas_dim
    const int margin     = (canvas_dim - sprite_dim) / 2; // letterbox if not exact

    // Clear the full canvas first so any letterbox margin reads as bg.
    for (int i = 0; i < canvas_dim * canvas_dim; i++) canvas_buf[i] = COL_EMPTY;

    const uint8_t *cells = a->frames + (size_t)frame_idx * grid * grid;
    for (int gy = 0; gy < grid; gy++) {
        for (int gx = 0; gx < grid; gx++) {
            uint8_t code = cells[gy * grid + gx];
            uint16_t color = (a->palette && code < a->palette_size)
                                 ? a->palette[code] : COL_EMPTY;
            uint16_t *p = &row_buf[gx * cell];
            for (int i = 0; i < cell; i++) p[i] = color;
        }
        for (int dy = 0; dy < cell; dy++) {
            int y = margin + gy * cell + dy;
            memcpy(&canvas_buf[y * canvas_dim + margin], row_buf, sprite_dim * 2);
        }
    }
    if (canvas) lv_obj_invalidate(canvas);
}

static void show_placeholder() {
    // Solid dark background + centered status label.
    if (canvas_buf) {
        for (int i = 0; i < canvas_dim * canvas_dim; i++) canvas_buf[i] = COL_EMPTY;
    }
    if (canvas) lv_obj_invalidate(canvas);
    if (label_status) lv_obj_clear_flag(label_status, LV_OBJ_FLAG_HIDDEN);
}

void splash_init(lv_obj_t *parent) {
    const BoardCaps& c = board_caps();
    int min_dim = (c.width < c.height) ? c.width : c.height;
    canvas_dim = min_dim;
    // Row buffer must be big enough for the canvas; one row of RGB565.
    canvas_buf = (uint16_t*)heap_caps_malloc(canvas_dim * canvas_dim * 2, MALLOC_CAP_SPIRAM);
    row_buf    = (uint16_t*)heap_caps_malloc(canvas_dim * 2,              MALLOC_CAP_SPIRAM);
    if (!canvas_buf || !row_buf) {
        Serial.println("splash: failed to alloc canvas buffer");
        return;
    }

    splash_container = lv_obj_create(parent);
    lv_obj_set_size(splash_container, c.width, c.height);
    lv_obj_set_pos(splash_container, 0, 0);
    lv_obj_set_style_bg_color(splash_container, THEME_BG, 0);
    lv_obj_set_style_bg_opa(splash_container, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(splash_container, 0, 0);
    lv_obj_set_style_pad_all(splash_container, 0, 0);
    lv_obj_clear_flag(splash_container, LV_OBJ_FLAG_SCROLLABLE);

    canvas = lv_canvas_create(splash_container);
    lv_canvas_set_buffer(canvas, canvas_buf, canvas_dim, canvas_dim, LV_COLOR_FORMAT_RGB565);
    lv_obj_center(canvas);

    // Placeholder label (visible only when no animations are loaded)
    label_status = lv_label_create(splash_container);
    lv_label_set_text(label_status,
        "no animations loaded\n\n"
        "run tools/scrape_claudepix.js\n"
        "then tools/convert_to_c.js");
    lv_obj_set_style_text_font(label_status, &font_styrene_28, 0);
    lv_obj_set_style_text_color(label_status, lv_color_hex(0xb0aea5), 0);
    lv_obj_set_style_text_align(label_status, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_center(label_status);

    resolve_group_lists();

    if (SPLASH_ANIM_COUNT == 0) {
        show_placeholder();
    } else {
        lv_obj_add_flag(label_status, LV_OBJ_FLAG_HIDDEN);
        render_anim_frame(&splash_anims[0], 0);
        frame_started_ms = millis();
    }

    lv_obj_add_flag(splash_container, LV_OBJ_FLAG_HIDDEN);
}

void splash_tick(void) {
    if (!active || SPLASH_ANIM_COUNT == 0) return;

    // Auto-rotate to the next animation in the current group.
    if (millis() - last_pick_ms >= SPLASH_ROTATE_INTERVAL_MS) {
        splash_pick_for_current_rate();
    }

    const splash_anim_def_t *a = &splash_anims[cur_anim];
    if (a->frame_count == 0) return;

    uint16_t hold = a->holds[cur_frame];
    if (millis() - frame_started_ms >= hold) {
        cur_frame = (cur_frame + 1) % a->frame_count;
        frame_started_ms = millis();
        render_anim_frame(a, cur_frame);
    }
}

void splash_next(void) {
    if (SPLASH_ANIM_COUNT == 0) return;
    cur_anim = (cur_anim + 1) % SPLASH_ANIM_COUNT;
    cur_frame = 0;
    frame_started_ms = millis();
    last_pick_ms = frame_started_ms;
    render_anim_frame(&splash_anims[cur_anim], 0);
    Serial.printf("splash: -> %s\n", splash_anims[cur_anim].name);
}

void splash_pick_for_current_rate(void) {
    if (SPLASH_ANIM_COUNT == 0) return;
    int g = usage_rate_group();
    if (g < 0 || g >= GROUP_COUNT) g = 0;
    if (group_size[g] == 0) return;

    uint8_t slot = group_rotation[g] % group_size[g];
    group_rotation[g]++;
    int8_t idx = group_lists[g][slot];
    if (idx < 0) return;

    cur_anim = (uint16_t)idx;
    cur_frame = 0;
    frame_started_ms = millis();
    last_pick_ms = frame_started_ms;
    render_anim_frame(&splash_anims[cur_anim], 0);
}

bool splash_is_active(void) { return active; }

void splash_show(void) {
    splash_pick_for_current_rate();
    if (splash_container) lv_obj_clear_flag(splash_container, LV_OBJ_FLAG_HIDDEN);
    active = true;
}

void splash_hide(void) {
    if (splash_container) lv_obj_add_flag(splash_container, LV_OBJ_FLAG_HIDDEN);
    active = false;
}

lv_obj_t* splash_get_root(void) {
    return splash_container;
}

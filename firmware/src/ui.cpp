#include "ui.h"
#include "splash.h"
#include <lvgl.h>
#include <math.h>
#ifdef SPLASH_THEME_WINE
#include "logo_wine.h"
#define LOGO_DATA   logo_wine_data
#define LOGO_W      LOGO_WINE_WIDTH
#define LOGO_H      LOGO_WINE_HEIGHT
#else
#include "logo.h"
#define LOGO_DATA   logo_data
#define LOGO_W      LOGO_WIDTH
#define LOGO_H      LOGO_HEIGHT
#endif
#include "icons.h"
#include "hal/board_caps.h"

// Custom fonts (scaled for 314 PPI, ~1.9x from original 165 PPI)
LV_FONT_DECLARE(font_tiempos_56);
LV_FONT_DECLARE(font_tiempos_34);
LV_FONT_DECLARE(font_styrene_48);
LV_FONT_DECLARE(font_styrene_28);
LV_FONT_DECLARE(font_styrene_24);
LV_FONT_DECLARE(font_styrene_20);
LV_FONT_DECLARE(font_styrene_16);
LV_FONT_DECLARE(font_styrene_14);
LV_FONT_DECLARE(font_mono_32);
LV_FONT_DECLARE(font_mono_18);

#include "theme.h"
#define COL_BG        THEME_BG
#define COL_PANEL     THEME_PANEL
#define COL_TEXT      THEME_TEXT
#define COL_DIM       THEME_DIM
#define COL_ACCENT    THEME_ACCENT
#define COL_GREEN     THEME_GREEN
#define COL_AMBER     THEME_AMBER
#define COL_RED       THEME_RED
#define COL_BAR_BG    THEME_BAR_BG

// ---------- Layout (board-responsive) ----------

struct Layout {
    int16_t scr_w, scr_h;
    int16_t margin;
    int16_t title_y;
    int16_t content_y;
    int16_t content_w;
    int16_t panel_h;
    int16_t panel_gap;
    int16_t bar_y;
    int16_t reset_y;
    int16_t bt_info_panel_h;
    int16_t bt_reset_zone_h;
    const lv_font_t* title_font;       // big screen title
    const lv_font_t* big_value_font;   // 48pt primary number
    const lv_font_t* mid_font;          // 28pt secondary
    const lv_font_t* small_font;        // 20pt note/reset
    const lv_font_t* tiny_font;         // 16/14pt
    const lv_font_t* bt_status_font;
    const lv_font_t* bt_device_font;
    const lv_font_t* bt_credit_1_font;
    const lv_font_t* bt_credit_2_font;
};
static Layout L = {};

static void compute_layout(const BoardCaps& c) {
    L.scr_w = c.width;
    L.scr_h = c.height;
    L.margin = 20;
    L.title_y = 30;

    if (c.height >= 460) {
        L.content_y = 100;
        L.panel_h = 150;
        L.panel_gap = 16;
        L.bar_y = 56;
        L.reset_y = 94;
        L.bt_info_panel_h = 160;
        L.bt_reset_zone_h = 110;
        L.title_font       = &font_tiempos_56;
        L.big_value_font   = &font_styrene_48;
        L.mid_font          = &font_styrene_28;
        L.small_font        = &font_styrene_20;
        L.tiny_font         = &font_styrene_16;
        L.bt_status_font   = &font_styrene_48;
        L.bt_device_font   = &font_styrene_28;
        L.bt_credit_1_font = &font_styrene_24;
        L.bt_credit_2_font = &font_styrene_20;
    } else {
        L.content_y = 85;
        L.panel_h = 130;
        L.panel_gap = 12;
        L.bar_y = 48;
        L.reset_y = 78;
        L.bt_info_panel_h = 140;
        L.bt_reset_zone_h = 90;
        L.title_font       = &font_tiempos_34;
        L.big_value_font   = &font_styrene_48;
        L.mid_font          = &font_styrene_24;
        L.small_font        = &font_styrene_16;
        L.tiny_font         = &font_styrene_14;
        L.bt_status_font   = &font_styrene_28;
        L.bt_device_font   = &font_styrene_20;
        L.bt_credit_1_font = &font_styrene_16;
        L.bt_credit_2_font = &font_styrene_14;
    }

    L.content_w = L.scr_w - 2 * L.margin;
}

// ---------- Per-screen widget storage ----------

// One container per possible provider slot. Built lazily — we set the kind
// of the layout the first time we see a non-zero ProviderUsage in that
// slot. If the kind changes for that slot in a subsequent cycle, we tear
// down the container's children and rebuild.
struct ProviderScreen {
    lv_obj_t* container;
    lv_obj_t* title_lbl;       // provider name (top-mid)
    lv_obj_t* note_lbl;        // optional sub-name (small, under title)
    ProviderKind built_kind;

    // Widgets created per-kind — only the ones used by `built_kind` are valid.
    lv_obj_t* m1_value_lbl;
    lv_obj_t* m1_unit_lbl;
    lv_obj_t* m1_bar;
    lv_obj_t* m2_value_lbl;
    lv_obj_t* m2_unit_lbl;
    lv_obj_t* m2_bar;
    lv_obj_t* m3_value_lbl;
    lv_obj_t* m3_unit_lbl;
    lv_obj_t* pace_lbl;
    lv_obj_t* reset_lbl;
    lv_obj_t* status_lbl;

    // tokens_abs visualisation extras (Sparkline + Donut).
    lv_obj_t* spark_chart;
    lv_chart_series_t* spark_series;
    lv_obj_t* donut_arcs[CLAWD_SHARES_MAX];
    lv_obj_t* legend_dot[CLAWD_SHARES_MAX];
    lv_obj_t* legend_lbl[CLAWD_SHARES_MAX];
};

static ProviderScreen g_screens[CLAWD_MAX_PROVIDERS] = {};

static lv_obj_t* empty_container = nullptr;
static lv_obj_t* empty_title = nullptr;
static lv_obj_t* empty_msg = nullptr;
static lv_obj_t* empty_hint = nullptr;

static lv_obj_t* ble_container = nullptr;
static lv_obj_t* lbl_ble_status = nullptr;
static lv_obj_t* lbl_ble_device = nullptr;
static lv_obj_t* lbl_ble_mac = nullptr;

static lv_obj_t* battery_img = nullptr;
static lv_obj_t* logo_img = nullptr;
static lv_image_dsc_t battery_dscs[5];
static lv_image_dsc_t logo_dsc;

static UsageState g_last_state = {};

static int g_current_screen = SCREEN_SPLASH;
static int g_prev_non_splash = SCREEN_USAGE_BASE;  // remembered for splash toggle

// ---------- Helpers ----------

static lv_color_t pct_color(float pct) {
    if (pct >= 80.0f) return COL_RED;
    if (pct >= 50.0f) return COL_AMBER;
    return COL_GREEN;
}

static lv_color_t pace_color(int8_t pace) {
    if (pace == CLAWD_PACE_UNSET) return COL_DIM;
    if (pace <= -2) return COL_GREEN;
    if (pace == -1) return COL_GREEN;
    if (pace == 0)  return COL_DIM;
    if (pace == 1)  return COL_AMBER;
    return COL_RED;  // +2, +3
}

static const char* pace_glyph(int8_t pace) {
    if (pace == CLAWD_PACE_UNSET) return "";
    switch (pace) {
        case -3: return "\xE2\x86\x93\xE2\x86\x93";  // ↓↓
        case -2: return "\xE2\x86\x93";              // ↓
        case -1: return "\xE2\x96\xBC";              // ▼
        case  0: return "\xE2\x80\x94";              // —
        case  1: return "\xE2\x96\xB2";              // ▲
        case  2: return "\xE2\x86\x91";              // ↑
        case  3: return "\xE2\x86\x91\xE2\x86\x91";  // ↑↑
    }
    return "";
}

static void format_reset_seconds(int32_t s, char* buf, size_t len) {
    if (s <= 0) {
        snprintf(buf, len, "Reset \xE2\x80\x94");  // em-dash
        return;
    }
    int mins = (s + 30) / 60;
    if (mins < 60)         snprintf(buf, len, "Reset in %dm", mins);
    else if (mins < 1440)  snprintf(buf, len, "Reset in %dh %dm", mins/60, mins%60);
    else                    snprintf(buf, len, "Reset in %dd %dh", mins/1440, (mins%1440)/60);
}

static void format_tokens(float n, char* buf, size_t len) {
    if (n < 1000)            snprintf(buf, len, "%.0f", n);
    else if (n < 1000000)     snprintf(buf, len, "%.1fk", n / 1000.0f);
    else if (n < 1000000000)  snprintf(buf, len, "%.2fM", n / 1000000.0f);
    else                       snprintf(buf, len, "%.2fG", n / 1000000000.0f);
}

static const char* currency_symbol(const char* cur) {
    if (!cur || !*cur) return "";
    if (strcmp(cur, "EUR") == 0) return "\xE2\x82\xAC";  // €
    if (strcmp(cur, "USD") == 0) return "$";
    if (strcmp(cur, "GBP") == 0) return "\xC2\xA3";       // £
    return cur;
}

// ---------- Reusable LVGL builders ----------

static lv_obj_t* make_panel(lv_obj_t* parent, int x, int y, int w, int h) {
    lv_obj_t* panel = lv_obj_create(parent);
    lv_obj_set_pos(panel, x, y);
    lv_obj_set_size(panel, w, h);
    lv_obj_set_style_bg_color(panel, COL_PANEL, 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(panel, 8, 0);
    lv_obj_set_style_border_width(panel, 0, 0);
    lv_obj_set_style_pad_left(panel, 16, 0);
    lv_obj_set_style_pad_right(panel, 16, 0);
    lv_obj_set_style_pad_top(panel, 12, 0);
    lv_obj_set_style_pad_bottom(panel, 12, 0);
    lv_obj_clear_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(panel, LV_OBJ_FLAG_EVENT_BUBBLE);
    return panel;
}

static lv_obj_t* make_bar(lv_obj_t* parent, int x, int y, int w, int h) {
    lv_obj_t* bar = lv_bar_create(parent);
    lv_obj_set_pos(bar, x, y);
    lv_obj_set_size(bar, w, h);
    lv_bar_set_range(bar, 0, 100);
    lv_bar_set_value(bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar, COL_BAR_BG, LV_PART_MAIN);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_radius(bar, 6, LV_PART_MAIN);
    lv_obj_set_style_bg_color(bar, COL_GREEN, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, LV_PART_INDICATOR);
    lv_obj_set_style_radius(bar, 6, LV_PART_INDICATOR);
    return bar;
}

static lv_obj_t* make_pill(lv_obj_t* parent, const char* text) {
    lv_obj_t* lbl = lv_label_create(parent);
    lv_label_set_text(lbl, text);
    lv_obj_set_style_text_font(lbl, L.small_font, 0);
    lv_obj_set_style_text_color(lbl, COL_TEXT, 0);
    lv_obj_set_style_bg_color(lbl, COL_BAR_BG, 0);
    lv_obj_set_style_bg_opa(lbl, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(lbl, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_pad_left(lbl, 14, 0);
    lv_obj_set_style_pad_right(lbl, 14, 0);
    lv_obj_set_style_pad_top(lbl, 4, 0);
    lv_obj_set_style_pad_bottom(lbl, 4, 0);
    return lbl;
}

static void init_icon_dsc(lv_image_dsc_t* dsc, int w, int h, const uint16_t* data) {
    dsc->header.w = w;
    dsc->header.h = h;
    dsc->header.cf = LV_COLOR_FORMAT_RGB565;
    dsc->header.stride = w * 2;
    dsc->data = (const uint8_t*)data;
    dsc->data_size = w * h * 2;
}

static void init_icon_dsc_rgb565a8(lv_image_dsc_t* dsc, int w, int h, const uint8_t* data) {
    dsc->header.w = w;
    dsc->header.h = h;
    dsc->header.cf = LV_COLOR_FORMAT_RGB565A8;
    dsc->header.stride = w * 2;
    dsc->data = data;
    dsc->data_size = w * h * 3;
}

static void init_battery_icons(void) {
    init_icon_dsc_rgb565a8(&battery_dscs[0], ICON_BATTERY_W, ICON_BATTERY_H, icon_battery_data);
    init_icon_dsc_rgb565a8(&battery_dscs[1], ICON_BATTERY_LOW_W, ICON_BATTERY_LOW_H, icon_battery_low_data);
    init_icon_dsc_rgb565a8(&battery_dscs[2], ICON_BATTERY_MEDIUM_W, ICON_BATTERY_MEDIUM_H, icon_battery_medium_data);
    init_icon_dsc_rgb565a8(&battery_dscs[3], ICON_BATTERY_FULL_W, ICON_BATTERY_FULL_H, icon_battery_full_data);
    init_icon_dsc_rgb565a8(&battery_dscs[4], ICON_BATTERY_CHARGING_W, ICON_BATTERY_CHARGING_H, icon_battery_charging_data);
}

// ---------- Per-kind layouts ----------

// Each builder is called once on first sight of a given kind for a slot,
// then update_*() is called every cycle to refresh the values without
// rebuilding the widget tree.

static void global_click_cb(lv_event_t* e);
static void ble_reset_click_cb(lv_event_t* e);

static lv_obj_t* attach_screen_container(lv_obj_t* scr) {
    lv_obj_t* c = lv_obj_create(scr);
    lv_obj_set_size(c, L.scr_w, L.scr_h);
    lv_obj_set_pos(c, 0, 0);
    lv_obj_set_style_bg_opa(c, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(c, 0, 0);
    lv_obj_set_style_pad_all(c, 0, 0);
    lv_obj_clear_flag(c, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(c, global_click_cb, LV_EVENT_CLICKED, NULL);
    lv_obj_add_flag(c, LV_OBJ_FLAG_HIDDEN);
    return c;
}

static void clear_children(lv_obj_t* obj) {
    lv_obj_clean(obj);  // recursively deletes all children
}

static void build_title_block(ProviderScreen& s) {
    // Provider-Screen-Titel ist absichtlich kleiner als L.title_font (was
    // Bluetooth/Splash nutzen): wir konkurrieren mit Logo + Sub-Header + Pace-
    // Indikator um die obere Screen-Zone. tiempos_34 räumt genug Luft für
    // den Sub-Header darunter.
    const lv_font_t* title_font = (L.scr_h >= 460) ? &font_tiempos_34 : &font_tiempos_34;
    const lv_font_t* note_font  = (L.scr_h >= 460) ? &font_styrene_20 : &font_styrene_16;

    s.title_lbl = lv_label_create(s.container);
    lv_label_set_text(s.title_lbl, "");
    lv_obj_set_style_text_font(s.title_lbl, title_font, 0);
    lv_obj_set_style_text_color(s.title_lbl, COL_TEXT, 0);
    lv_obj_align(s.title_lbl, LV_ALIGN_TOP_MID, 16, L.title_y + 4);

    s.note_lbl = lv_label_create(s.container);
    lv_label_set_text(s.note_lbl, "");
    lv_obj_set_style_text_font(s.note_lbl, note_font, 0);
    // Etwas heller als COL_DIM — der Sub-Header darf sichtbar sein.
    lv_obj_set_style_text_color(s.note_lbl, COL_TEXT, 0);
    lv_obj_set_style_text_opa(s.note_lbl, LV_OPA_70, 0);
    lv_obj_align(s.note_lbl, LV_ALIGN_TOP_MID, 16, L.title_y + 44);
}

// pct_window — Anthropic style: two stacked panels (5h + 7d), bar + pct label
static void build_pct_window(ProviderScreen& s) {
    clear_children(s.container);
    build_title_block(s);

    // Top panel — primary window
    lv_obj_t* p1 = make_panel(s.container, L.margin, L.content_y, L.content_w, L.panel_h);
    s.m1_value_lbl = lv_label_create(p1);
    lv_label_set_text(s.m1_value_lbl, "---%");
    lv_obj_set_style_text_font(s.m1_value_lbl, L.big_value_font, 0);
    lv_obj_set_style_text_color(s.m1_value_lbl, COL_TEXT, 0);
    lv_obj_set_pos(s.m1_value_lbl, 0, 0);

    s.m1_unit_lbl = make_pill(p1, "Aktuell");
    lv_obj_align(s.m1_unit_lbl, LV_ALIGN_TOP_RIGHT, 0, 1);

    s.pace_lbl = lv_label_create(p1);
    lv_label_set_text(s.pace_lbl, "");
    // Pace uses Mono — the arrow glyphs (↑↓▲▼—) only live in font_mono_*.
    lv_obj_set_style_text_font(s.pace_lbl, &font_mono_32, 0);
    lv_obj_set_style_text_color(s.pace_lbl, COL_DIM, 0);
    lv_obj_align(s.pace_lbl, LV_ALIGN_TOP_RIGHT, -100, 6);

    s.m1_bar = make_bar(p1, 0, L.bar_y, L.content_w - 32, 24);

    s.reset_lbl = lv_label_create(p1);
    lv_label_set_text(s.reset_lbl, "---");
    lv_obj_set_style_text_font(s.reset_lbl, L.mid_font, 0);
    lv_obj_set_style_text_color(s.reset_lbl, COL_DIM, 0);
    lv_obj_set_pos(s.reset_lbl, 0, L.reset_y);

    // Bottom panel — secondary window
    lv_obj_t* p2 = make_panel(s.container,
                              L.margin, L.content_y + L.panel_h + L.panel_gap,
                              L.content_w, L.panel_h);
    s.m2_value_lbl = lv_label_create(p2);
    lv_label_set_text(s.m2_value_lbl, "---%");
    lv_obj_set_style_text_font(s.m2_value_lbl, L.big_value_font, 0);
    lv_obj_set_style_text_color(s.m2_value_lbl, COL_TEXT, 0);
    lv_obj_set_pos(s.m2_value_lbl, 0, 0);

    s.m2_unit_lbl = make_pill(p2, "Wöchentlich");
    lv_obj_align(s.m2_unit_lbl, LV_ALIGN_TOP_RIGHT, 0, 1);

    s.m2_bar = make_bar(p2, 0, L.bar_y, L.content_w - 32, 24);

    s.status_lbl = lv_label_create(p2);
    lv_label_set_text(s.status_lbl, "");
    lv_obj_set_style_text_font(s.status_lbl, L.mid_font, 0);
    lv_obj_set_style_text_color(s.status_lbl, COL_DIM, 0);
    lv_obj_set_pos(s.status_lbl, 0, L.reset_y);
}

static void update_pct_window(ProviderScreen& s, const ProviderUsage& p) {
    int m1 = (int)(p.m1 + 0.5f);
    int m2 = (int)(p.m2 + 0.5f);
    lv_label_set_text_fmt(s.m1_value_lbl, "%d%%", m1);
    lv_bar_set_value(s.m1_bar, m1, LV_ANIM_ON);
    lv_obj_set_style_bg_color(s.m1_bar, pct_color(p.m1), LV_PART_INDICATOR);

    lv_label_set_text_fmt(s.m2_value_lbl, "%d%%", m2);
    lv_bar_set_value(s.m2_bar, m2, LV_ANIM_ON);
    lv_obj_set_style_bg_color(s.m2_bar, pct_color(p.m2), LV_PART_INDICATOR);

    char buf[48];
    format_reset_seconds(p.r1, buf, sizeof(buf));
    lv_label_set_text(s.reset_lbl, buf);
    format_reset_seconds(p.r2, buf, sizeof(buf));
    lv_label_set_text(s.status_lbl, buf);

    lv_label_set_text(s.pace_lbl, pace_glyph(p.pace));
    lv_obj_set_style_text_color(s.pace_lbl, pace_color(p.pace), 0);
}

// cost_budget — Langdock style: spent vs budget (or just spent if budget=0)
static void build_cost_budget(ProviderScreen& s) {
    clear_children(s.container);
    build_title_block(s);

    lv_obj_t* p = make_panel(s.container, L.margin, L.content_y, L.content_w, L.panel_h + 40);

    s.m1_value_lbl = lv_label_create(p);
    lv_label_set_text(s.m1_value_lbl, "---");
    lv_obj_set_style_text_font(s.m1_value_lbl, L.big_value_font, 0);
    lv_obj_set_style_text_color(s.m1_value_lbl, COL_TEXT, 0);
    lv_obj_set_pos(s.m1_value_lbl, 0, 0);

    s.m1_unit_lbl = lv_label_create(p);
    lv_label_set_text(s.m1_unit_lbl, "");
    lv_obj_set_style_text_font(s.m1_unit_lbl, L.mid_font, 0);
    lv_obj_set_style_text_color(s.m1_unit_lbl, COL_DIM, 0);
    lv_obj_align(s.m1_unit_lbl, LV_ALIGN_TOP_RIGHT, 0, 12);

    s.pace_lbl = lv_label_create(p);
    lv_label_set_text(s.pace_lbl, "");
    // Pace uses Mono — the arrow glyphs (↑↓▲▼—) only live in font_mono_*.
    lv_obj_set_style_text_font(s.pace_lbl, &font_mono_32, 0);
    lv_obj_align(s.pace_lbl, LV_ALIGN_TOP_RIGHT, -90, 14);

    s.m1_bar = make_bar(p, 0, L.bar_y + 12, L.content_w - 32, 24);

    s.m2_value_lbl = lv_label_create(p);
    lv_label_set_text(s.m2_value_lbl, "");
    lv_obj_set_style_text_font(s.m2_value_lbl, L.small_font, 0);
    lv_obj_set_style_text_color(s.m2_value_lbl, COL_DIM, 0);
    lv_obj_set_pos(s.m2_value_lbl, 0, L.reset_y + 6);

    s.reset_lbl = lv_label_create(p);
    lv_label_set_text(s.reset_lbl, "---");
    lv_obj_set_style_text_font(s.reset_lbl, L.small_font, 0);
    lv_obj_set_style_text_color(s.reset_lbl, COL_DIM, 0);
    lv_obj_align(s.reset_lbl, LV_ALIGN_TOP_RIGHT, 0, L.reset_y + 6);
}

static void update_cost_budget(ProviderScreen& s, const ProviderUsage& p) {
    const char* sym = currency_symbol(p.currency);
    char buf[64];
    snprintf(buf, sizeof(buf), "%s%.2f", sym, p.m1);
    lv_label_set_text(s.m1_value_lbl, buf);

    if (p.m2 > 0) {
        // Budget configured — show utilization bar + budget figure
        float pct = (p.m1 / p.m2) * 100.0f;
        if (pct > 100.0f) pct = 100.0f;
        lv_obj_clear_flag(s.m1_bar, LV_OBJ_FLAG_HIDDEN);
        lv_bar_set_value(s.m1_bar, (int)(pct + 0.5f), LV_ANIM_ON);
        lv_obj_set_style_bg_color(s.m1_bar, pct_color(pct), LV_PART_INDICATOR);

        snprintf(buf, sizeof(buf), "von %s%.0f", sym, p.m2);
        lv_label_set_text(s.m1_unit_lbl, buf);

        snprintf(buf, sizeof(buf), "%d%% Budget", (int)(pct + 0.5f));
        lv_label_set_text(s.m2_value_lbl, buf);
    } else {
        // No budget — hide bar, show plain "no budget"
        lv_obj_add_flag(s.m1_bar, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s.m1_unit_lbl, "");
        lv_label_set_text(s.m2_value_lbl, "Kein Budget gesetzt");
    }

    char rbuf[48];
    format_reset_seconds(p.r2, rbuf, sizeof(rbuf));
    lv_label_set_text(s.reset_lbl, rbuf);

    lv_label_set_text(s.pace_lbl, pace_glyph(p.pace));
    lv_obj_set_style_text_color(s.pace_lbl, pace_color(p.pace), 0);
}

// tokens_abs — OpenCode style: big number + 24h sparkline + provider donut.
// Layout inside the panel (480×480, compact: 368×448 numbers in parens):
//   y=0..52   big m1 value (left) + "Tokens heute" pill (right)
//   y=58..82  "+X vs. gestern" (left)
//   y=92..172 (88) 24h-sparkline bar chart, full width
//   y=190..278 (78) donut left + legend right
//   y=bottom  reset string (right)
static const lv_color_t DONUT_SLICE_COLORS[CLAWD_SHARES_MAX] = {
    LV_COLOR_MAKE(0xE5, 0x6C, 0x4C),  // primary (terra-cotta / Bordeaux)
    LV_COLOR_MAKE(0x8F, 0xA8, 0x6E),  // green
    LV_COLOR_MAKE(0xD8, 0xA8, 0x4A),  // amber
    LV_COLOR_MAKE(0x7A, 0x7A, 0x7A),  // grey ("other")
};

struct AbsMetrics {
    int spark_h;
    int donut_size;
    int sub_y;
    int spark_y;
    int donut_y;
    const lv_font_t* legend_font;
};

static AbsMetrics abs_metrics() {
    AbsMetrics m;
    bool large = (L.scr_h >= 460);
    m.spark_h    = large ? 80  : 60;
    m.donut_size = large ? 80  : 60;
    m.sub_y      = large ? 60  : 52;
    m.spark_y    = large ? 96  : 76;
    m.donut_y    = m.spark_y + m.spark_h + (large ? 14 : 8);
    m.legend_font = L.small_font;
    return m;
}

// Reserve room below the panel for the global idle-spinner label so it stays
// visible on the tokens_abs screen (the spinner lives on the screen root and
// sits at LV_ALIGN_BOTTOM_MID, -15 → ~50px from the bottom).
static int abs_panel_height() {
    return L.scr_h - L.content_y - L.margin - 50;
}

static void build_tokens_abs(ProviderScreen& s) {
    clear_children(s.container);
    build_title_block(s);

    AbsMetrics M = abs_metrics();
    int panel_h = abs_panel_height();
    lv_obj_t* p = make_panel(s.container, L.margin, L.content_y, L.content_w, panel_h);

    // --- Header row: big number left, unit pill right ---
    s.m1_value_lbl = lv_label_create(p);
    lv_label_set_text(s.m1_value_lbl, "---");
    lv_obj_set_style_text_font(s.m1_value_lbl, L.big_value_font, 0);
    lv_obj_set_style_text_color(s.m1_value_lbl, COL_TEXT, 0);
    lv_obj_set_pos(s.m1_value_lbl, 0, 0);

    s.m1_unit_lbl = lv_label_create(p);
    lv_label_set_text(s.m1_unit_lbl, "Tokens heute");
    lv_obj_set_style_text_font(s.m1_unit_lbl, L.mid_font, 0);
    lv_obj_set_style_text_color(s.m1_unit_lbl, COL_DIM, 0);
    lv_obj_align(s.m1_unit_lbl, LV_ALIGN_TOP_RIGHT, 0, 14);

    // Sub-line: day-over-day delta
    s.m3_value_lbl = lv_label_create(p);
    lv_label_set_text(s.m3_value_lbl, "");
    lv_obj_set_style_text_font(s.m3_value_lbl, L.small_font, 0);
    lv_obj_set_style_text_color(s.m3_value_lbl, COL_DIM, 0);
    lv_obj_set_pos(s.m3_value_lbl, 0, M.sub_y);

    // --- 24h Sparkline (lv_chart, bar mode) ---
    int chart_w = L.content_w - 32;  // panel inner width
    s.spark_chart = lv_chart_create(p);
    lv_obj_set_size(s.spark_chart, chart_w, M.spark_h);
    lv_obj_set_pos(s.spark_chart, 0, M.spark_y);
    lv_chart_set_type(s.spark_chart, LV_CHART_TYPE_BAR);
    lv_chart_set_point_count(s.spark_chart, CLAWD_SPARK_LEN);
    lv_chart_set_range(s.spark_chart, LV_CHART_AXIS_PRIMARY_Y, 0, 1);
    lv_chart_set_div_line_count(s.spark_chart, 0, 0);
    lv_obj_set_style_pad_all(s.spark_chart, 0, 0);
    lv_obj_set_style_pad_column(s.spark_chart, 2, 0);
    lv_obj_set_style_bg_opa(s.spark_chart, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(s.spark_chart, 0, 0);
    lv_obj_set_style_radius(s.spark_chart, 0, 0);
    // The bar fill — use the brand accent for a single coherent colour bar.
    lv_obj_set_style_bg_color(s.spark_chart, COL_ACCENT, LV_PART_ITEMS);
    lv_obj_set_style_bg_opa(s.spark_chart, LV_OPA_COVER, LV_PART_ITEMS);
    lv_obj_set_style_radius(s.spark_chart, 1, LV_PART_ITEMS);
    lv_obj_clear_flag(s.spark_chart, LV_OBJ_FLAG_SCROLLABLE);
    s.spark_series = lv_chart_add_series(
        s.spark_chart, COL_ACCENT, LV_CHART_AXIS_PRIMARY_Y);

    // --- Donut + legend ---
    int donut_x = 0;
    int legend_x = M.donut_size + 16;
    int legend_w = chart_w - legend_x;
    for (uint8_t i = 0; i < CLAWD_SHARES_MAX; ++i) {
        lv_obj_t* arc = lv_arc_create(p);
        lv_obj_set_size(arc, M.donut_size, M.donut_size);
        lv_obj_set_pos(arc, donut_x, M.donut_y);
        lv_arc_set_rotation(arc, 270);
        lv_arc_set_bg_angles(arc, 0, 360);
        lv_arc_set_value(arc, 0);
        lv_arc_set_range(arc, 0, 100);
        lv_obj_remove_style(arc, NULL, LV_PART_KNOB);
        lv_obj_clear_flag(arc, LV_OBJ_FLAG_CLICKABLE);
        // Background arc: panel-colour for the unused track.
        lv_obj_set_style_arc_color(arc, COL_BAR_BG, LV_PART_MAIN);
        lv_obj_set_style_arc_width(arc, 10, LV_PART_MAIN);
        lv_obj_set_style_arc_color(arc, DONUT_SLICE_COLORS[i], LV_PART_INDICATOR);
        lv_obj_set_style_arc_width(arc, 10, LV_PART_INDICATOR);
        // Hide every slice initially — populated in update_tokens_abs.
        lv_obj_add_flag(arc, LV_OBJ_FLAG_HIDDEN);
        s.donut_arcs[i] = arc;

        // Legend row (dot + label). Stacked at fixed Y offsets within the
        // donut row so the layout is stable regardless of slice count.
        int row_h = M.donut_size / CLAWD_SHARES_MAX;
        int row_y = M.donut_y + i * row_h + (row_h - 14) / 2;

        lv_obj_t* dot = lv_obj_create(p);
        lv_obj_set_size(dot, 12, 12);
        lv_obj_set_pos(dot, legend_x, row_y + 2);
        lv_obj_set_style_bg_color(dot, DONUT_SLICE_COLORS[i], 0);
        lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
        lv_obj_set_style_radius(dot, 6, 0);
        lv_obj_set_style_border_width(dot, 0, 0);
        lv_obj_clear_flag(dot, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_add_flag(dot, LV_OBJ_FLAG_HIDDEN);
        s.legend_dot[i] = dot;

        lv_obj_t* lbl = lv_label_create(p);
        lv_label_set_text(lbl, "");
        lv_obj_set_style_text_font(lbl, M.legend_font, 0);
        lv_obj_set_style_text_color(lbl, COL_TEXT, 0);
        lv_obj_set_pos(lbl, legend_x + 20, row_y);
        lv_obj_set_width(lbl, legend_w - 20);
        lv_obj_add_flag(lbl, LV_OBJ_FLAG_HIDDEN);
        s.legend_lbl[i] = lbl;
    }

    // Reset string (bottom-right of panel).
    s.reset_lbl = lv_label_create(p);
    lv_label_set_text(s.reset_lbl, "---");
    lv_obj_set_style_text_font(s.reset_lbl, L.small_font, 0);
    lv_obj_set_style_text_color(s.reset_lbl, COL_DIM, 0);
    lv_obj_align(s.reset_lbl, LV_ALIGN_BOTTOM_RIGHT, 0, -2);
}

static void update_tokens_abs(ProviderScreen& s, const ProviderUsage& p) {
    char buf[48];
    format_tokens(p.m1, buf, sizeof(buf));
    lv_label_set_text(s.m1_value_lbl, buf);

    if (p.m3_set && p.m3 > 0) {
        float delta = p.m1 - p.m3;
        char dbuf[40];
        format_tokens(fabsf(delta), dbuf, sizeof(dbuf));
        if (delta >= 0) snprintf(buf, sizeof(buf), "+%s vs. gestern", dbuf);
        else            snprintf(buf, sizeof(buf), "-%s vs. gestern", dbuf);
        lv_label_set_text(s.m3_value_lbl, buf);
    } else {
        lv_label_set_text(s.m3_value_lbl, "");
    }

    // Sparkline: rescale Y range to the actual max so quiet hours don't
    // flatten the active hours into invisibility.
    if (s.spark_chart && s.spark_series) {
        uint32_t peak = 1;  // avoid 0..0 collapse
        for (uint8_t i = 0; i < CLAWD_SPARK_LEN; ++i) {
            if (p.spark[i] > peak) peak = p.spark[i];
        }
        lv_chart_set_range(s.spark_chart, LV_CHART_AXIS_PRIMARY_Y, 0, (int32_t)peak);
        for (uint8_t i = 0; i < CLAWD_SPARK_LEN; ++i) {
            lv_chart_set_next_value(s.spark_chart, s.spark_series,
                                     p.spark_set ? (int32_t)p.spark[i] : 0);
        }
        lv_chart_refresh(s.spark_chart);
    }

    // Donut + legend: hide unused slices, lay out the active ones as a
    // contiguous arc starting at 12 o'clock.
    uint16_t cursor = 0;
    for (uint8_t i = 0; i < CLAWD_SHARES_MAX; ++i) {
        bool active = (i < p.shares_count) && (p.shares[i].pct > 0);
        if (!active) {
            lv_obj_add_flag(s.donut_arcs[i], LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(s.legend_dot[i], LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(s.legend_lbl[i], LV_OBJ_FLAG_HIDDEN);
            continue;
        }
        uint16_t span = (uint16_t)((uint32_t)p.shares[i].pct * 360u / 100u);
        if (span < 2) span = 2;  // keep tiny slices visible
        uint16_t end = cursor + span;
        if (end > 360) end = 360;
        lv_arc_set_bg_angles(s.donut_arcs[i], cursor, end);
        lv_arc_set_angles(s.donut_arcs[i], cursor, end);
        lv_obj_clear_flag(s.donut_arcs[i], LV_OBJ_FLAG_HIDDEN);
        cursor = end;

        snprintf(buf, sizeof(buf), "%s  %d%%", p.shares[i].slug, p.shares[i].pct);
        lv_label_set_text(s.legend_lbl[i], buf);
        lv_obj_clear_flag(s.legend_dot[i], LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s.legend_lbl[i], LV_OBJ_FLAG_HIDDEN);
    }

    char rbuf[48];
    format_reset_seconds(p.r2, rbuf, sizeof(rbuf));
    lv_label_set_text(s.reset_lbl, rbuf);
}

// tpm_rpm — Bedrock style: 2 percentage bars (TPM, RPM) + monthly tokens
static void build_tpm_rpm(ProviderScreen& s) {
    clear_children(s.container);
    build_title_block(s);

    lv_obj_t* p1 = make_panel(s.container, L.margin, L.content_y, L.content_w, L.panel_h);
    s.m1_value_lbl = lv_label_create(p1);
    lv_label_set_text(s.m1_value_lbl, "---%");
    lv_obj_set_style_text_font(s.m1_value_lbl, L.big_value_font, 0);
    lv_obj_set_style_text_color(s.m1_value_lbl, COL_TEXT, 0);
    lv_obj_set_pos(s.m1_value_lbl, 0, 0);

    s.m1_unit_lbl = make_pill(p1, "TPM");
    lv_obj_align(s.m1_unit_lbl, LV_ALIGN_TOP_RIGHT, 0, 1);

    s.pace_lbl = lv_label_create(p1);
    lv_label_set_text(s.pace_lbl, "");
    // Pace uses Mono — the arrow glyphs (↑↓▲▼—) only live in font_mono_*.
    lv_obj_set_style_text_font(s.pace_lbl, &font_mono_32, 0);
    lv_obj_align(s.pace_lbl, LV_ALIGN_TOP_RIGHT, -90, 6);

    s.m1_bar = make_bar(p1, 0, L.bar_y, L.content_w - 32, 24);

    s.m3_value_lbl = lv_label_create(p1);
    lv_label_set_text(s.m3_value_lbl, "");
    lv_obj_set_style_text_font(s.m3_value_lbl, L.small_font, 0);
    lv_obj_set_style_text_color(s.m3_value_lbl, COL_DIM, 0);
    lv_obj_set_pos(s.m3_value_lbl, 0, L.reset_y);

    lv_obj_t* p2 = make_panel(s.container,
                              L.margin, L.content_y + L.panel_h + L.panel_gap,
                              L.content_w, L.panel_h);
    s.m2_value_lbl = lv_label_create(p2);
    lv_label_set_text(s.m2_value_lbl, "---%");
    lv_obj_set_style_text_font(s.m2_value_lbl, L.big_value_font, 0);
    lv_obj_set_style_text_color(s.m2_value_lbl, COL_TEXT, 0);
    lv_obj_set_pos(s.m2_value_lbl, 0, 0);

    s.m2_unit_lbl = make_pill(p2, "RPM");
    lv_obj_align(s.m2_unit_lbl, LV_ALIGN_TOP_RIGHT, 0, 1);

    s.m2_bar = make_bar(p2, 0, L.bar_y, L.content_w - 32, 24);

    s.reset_lbl = lv_label_create(p2);
    lv_label_set_text(s.reset_lbl, "---");
    lv_obj_set_style_text_font(s.reset_lbl, L.mid_font, 0);
    lv_obj_set_style_text_color(s.reset_lbl, COL_DIM, 0);
    lv_obj_set_pos(s.reset_lbl, 0, L.reset_y);
}

static void update_tpm_rpm(ProviderScreen& s, const ProviderUsage& p) {
    int m1 = (int)(p.m1 + 0.5f);
    int m2 = (int)(p.m2 + 0.5f);
    lv_label_set_text_fmt(s.m1_value_lbl, "%d%%", m1);
    lv_bar_set_value(s.m1_bar, m1 > 100 ? 100 : m1, LV_ANIM_ON);
    lv_obj_set_style_bg_color(s.m1_bar, pct_color(p.m1), LV_PART_INDICATOR);

    lv_label_set_text_fmt(s.m2_value_lbl, "%d%%", m2);
    lv_bar_set_value(s.m2_bar, m2 > 100 ? 100 : m2, LV_ANIM_ON);
    lv_obj_set_style_bg_color(s.m2_bar, pct_color(p.m2), LV_PART_INDICATOR);

    char buf[48];
    if (p.m3_set) {
        format_tokens(p.m3, buf, sizeof(buf));
        char full[64];
        snprintf(full, sizeof(full), "%s Tokens / Monat", buf);
        lv_label_set_text(s.m3_value_lbl, full);
    } else {
        lv_label_set_text(s.m3_value_lbl, "");
    }

    format_reset_seconds(p.r2, buf, sizeof(buf));
    lv_label_set_text(s.reset_lbl, buf);

    lv_label_set_text(s.pace_lbl, pace_glyph(p.pace));
    lv_obj_set_style_text_color(s.pace_lbl, pace_color(p.pace), 0);
}

// ---------- Empty state ----------

static void init_empty_screen(lv_obj_t* scr) {
    empty_container = attach_screen_container(scr);

    empty_title = lv_label_create(empty_container);
    lv_label_set_text(empty_title, "Clawdmeter");
    // Empty-state uses a smaller title than provider screens — the big
    // "Keine Provider" message in the middle already carries the screen.
    lv_obj_set_style_text_font(empty_title, &font_tiempos_34, 0);
    lv_obj_set_style_text_color(empty_title, COL_TEXT, 0);
    lv_obj_align(empty_title, LV_ALIGN_TOP_MID, 16, L.title_y + 8);

    empty_msg = lv_label_create(empty_container);
    lv_label_set_text(empty_msg, "Keine Provider\nkonfiguriert");
    lv_obj_set_style_text_font(empty_msg, L.big_value_font, 0);
    lv_obj_set_style_text_color(empty_msg, COL_DIM, 0);
    lv_obj_set_style_text_align(empty_msg, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(empty_msg, LV_ALIGN_CENTER, 0, -10);

    empty_hint = lv_label_create(empty_container);
    lv_label_set_text(empty_hint, "clawdmeter-daemon setup");
    lv_obj_set_style_text_font(empty_hint, L.mid_font, 0);
    lv_obj_set_style_text_color(empty_hint, COL_ACCENT, 0);
    lv_obj_align(empty_hint, LV_ALIGN_BOTTOM_MID, 0, -L.content_y / 2);
}

// ---------- Bluetooth screen (unchanged behaviour) ----------

static void init_bluetooth_screen(lv_obj_t* scr) {
    ble_container = attach_screen_container(scr);

    lv_obj_t* lbl_ble_title = lv_label_create(ble_container);
    lv_label_set_text(lbl_ble_title, "Bluetooth");
    lv_obj_set_style_text_font(lbl_ble_title, L.title_font, 0);
    lv_obj_set_style_text_color(lbl_ble_title, COL_TEXT, 0);
    lv_obj_align(lbl_ble_title, LV_ALIGN_TOP_MID, 16, L.title_y);

    lv_obj_t* p_info = make_panel(ble_container, L.margin, L.content_y,
                                  L.content_w, L.bt_info_panel_h);

    static lv_image_dsc_t icon_bt_dsc;
    init_icon_dsc(&icon_bt_dsc, ICON_BLUETOOTH_W, ICON_BLUETOOTH_H, icon_bluetooth_data);

    lv_obj_t* bt_img = lv_image_create(p_info);
    lv_image_set_src(bt_img, &icon_bt_dsc);
    lv_obj_set_pos(bt_img, 0, 0);

    lbl_ble_status = lv_label_create(p_info);
    lv_label_set_text(lbl_ble_status, "Initialisierung...");
    lv_obj_set_style_text_font(lbl_ble_status, L.bt_status_font, 0);
    lv_obj_set_style_text_color(lbl_ble_status, COL_DIM, 0);
    lv_obj_set_pos(lbl_ble_status, 56, 2);

    lbl_ble_device = lv_label_create(p_info);
    lv_label_set_text(lbl_ble_device, "Gerät: ---");
    lv_obj_set_style_text_font(lbl_ble_device, L.bt_device_font, 0);
    lv_obj_set_style_text_color(lbl_ble_device, COL_DIM, 0);
    lv_obj_set_pos(lbl_ble_device, 0, 64);

    lbl_ble_mac = lv_label_create(p_info);
    lv_label_set_text(lbl_ble_mac, "Adresse: ---");
    lv_obj_set_style_text_font(lbl_ble_mac, L.bt_device_font, 0);
    lv_obj_set_style_text_color(lbl_ble_mac, COL_DIM, 0);
    lv_obj_set_pos(lbl_ble_mac, 0, 100);

    int reset_y = L.content_y + L.bt_info_panel_h + 16;
    lv_obj_t* reset_zone = lv_obj_create(ble_container);
    lv_obj_set_pos(reset_zone, L.margin, reset_y);
    lv_obj_set_size(reset_zone, L.content_w, L.bt_reset_zone_h);
    lv_obj_set_style_bg_color(reset_zone, COL_PANEL, 0);
    lv_obj_set_style_bg_opa(reset_zone, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(reset_zone, 8, 0);
    lv_obj_set_style_border_width(reset_zone, 0, 0);
    lv_obj_set_style_pad_column(reset_zone, 14, 0);
    lv_obj_set_flex_flow(reset_zone, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(reset_zone, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_clear_flag(reset_zone, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(reset_zone, ble_reset_click_cb, LV_EVENT_CLICKED, NULL);

    static lv_image_dsc_t icon_trash_dsc;
    init_icon_dsc(&icon_trash_dsc, ICON_TRASH2_W, ICON_TRASH2_H, icon_trash2_data);
    lv_obj_t* trash_img = lv_image_create(reset_zone);
    lv_image_set_src(trash_img, &icon_trash_dsc);

    lv_obj_t* reset_lbl = lv_label_create(reset_zone);
    lv_label_set_text(reset_lbl, "Bluetooth zurücksetzen");
    lv_obj_set_style_text_font(reset_lbl, L.bt_device_font, 0);
    lv_obj_set_style_text_color(reset_lbl, COL_DIM, 0);

    lv_obj_t* lbl_credit = lv_label_create(ble_container);
    lv_label_set_text(lbl_credit, "Built by Sascha");
    lv_obj_set_style_text_font(lbl_credit, L.bt_credit_1_font, 0);
    lv_obj_set_style_text_color(lbl_credit, COL_DIM, 0);
    lv_obj_align(lbl_credit, LV_ALIGN_BOTTOM_MID, 0, -46);

    lv_obj_t* lbl_credit2 = lv_label_create(ble_container);
    lv_label_set_text(lbl_credit2, "Inspired by hermannbjrgvin");
    lv_obj_set_style_text_font(lbl_credit2, L.bt_credit_2_font, 0);
    lv_obj_set_style_text_color(lbl_credit2, COL_DIM, 0);
    lv_obj_align(lbl_credit2, LV_ALIGN_BOTTOM_MID, 0, -20);
}

// ---------- Screen orchestration ----------

static void hide_all(void) {
    if (empty_container) lv_obj_add_flag(empty_container, LV_OBJ_FLAG_HIDDEN);
    if (ble_container)   lv_obj_add_flag(ble_container, LV_OBJ_FLAG_HIDDEN);
    for (int i = 0; i < CLAWD_MAX_PROVIDERS; ++i) {
        if (g_screens[i].container) lv_obj_add_flag(g_screens[i].container, LV_OBJ_FLAG_HIDDEN);
    }
    splash_hide();
}

static int provider_screen_count(void) {
    return (int)g_last_state.count;
}

static void apply_logo_visibility(int screen) {
    if (!logo_img) return;
    if (screen == SCREEN_SPLASH) lv_obj_add_flag(logo_img, LV_OBJ_FLAG_HIDDEN);
    else                          lv_obj_clear_flag(logo_img, LV_OBJ_FLAG_HIDDEN);
}

static void apply_battery_visibility(int screen) {
    if (!battery_img) return;
    if (screen == SCREEN_SPLASH) lv_obj_add_flag(battery_img, LV_OBJ_FLAG_HIDDEN);
    else                          lv_obj_clear_flag(battery_img, LV_OBJ_FLAG_HIDDEN);
}

static int clamp_screen(int screen) {
    int provider_count = provider_screen_count();
    if (screen == SCREEN_SPLASH || screen == SCREEN_BLUETOOTH) return screen;
    if (provider_count == 0) return SCREEN_EMPTY;
    if (screen == SCREEN_EMPTY) return SCREEN_USAGE_BASE;
    if (screen >= SCREEN_USAGE_BASE && screen < SCREEN_USAGE_BASE + provider_count) return screen;
    return SCREEN_USAGE_BASE;
}

// Auto-Cycle through provider screens. ms-counter resets on every screen
// change (auto, manual via PWR, programmatic via serial). On splash /
// bluetooth / empty we skip auto-cycling entirely.
static uint32_t g_auto_cycle_last_ms = 0;
#define AUTO_CYCLE_MS 15000   // 15 s pro Provider-Screen

void ui_show_screen(int screen) {
    hide_all();
    int target = clamp_screen(screen);

    if (target == SCREEN_SPLASH) {
        splash_show();
    } else if (target == SCREEN_BLUETOOTH) {
        if (ble_container) lv_obj_clear_flag(ble_container, LV_OBJ_FLAG_HIDDEN);
    } else if (target == SCREEN_EMPTY) {
        if (empty_container) lv_obj_clear_flag(empty_container, LV_OBJ_FLAG_HIDDEN);
    } else {
        int slot = target - SCREEN_USAGE_BASE;
        if (slot >= 0 && slot < CLAWD_MAX_PROVIDERS && g_screens[slot].container) {
            lv_obj_clear_flag(g_screens[slot].container, LV_OBJ_FLAG_HIDDEN);
        }
    }

    if (target != SCREEN_SPLASH) g_prev_non_splash = target;
    g_current_screen = target;
    g_auto_cycle_last_ms = lv_tick_get();  // jeder Wechsel resettet den Auto-Cycle
    apply_logo_visibility(target);
    apply_battery_visibility(target);
}

static void ui_tick_auto_cycle(void) {
    if (g_current_screen < SCREEN_USAGE_BASE) return;     // Splash/BT/Empty: kein Auto-Cycle
    int provider_count = provider_screen_count();
    if (provider_count <= 1) return;                       // nichts zum Wechseln
    uint32_t now = lv_tick_get();
    if (now - g_auto_cycle_last_ms < AUTO_CYCLE_MS) return;
    int slot = g_current_screen - SCREEN_USAGE_BASE;
    int next = (slot + 1) % provider_count;
    ui_show_screen(SCREEN_USAGE_BASE + next);
}

int ui_get_current_screen(void) { return g_current_screen; }

void ui_cycle_screen(void) {
    int provider_count = provider_screen_count();

    // Cycle order: provider0 → provider1 → ... → BLUETOOTH → provider0
    if (g_current_screen == SCREEN_BLUETOOTH) {
        ui_show_screen(provider_count > 0 ? SCREEN_USAGE_BASE : SCREEN_EMPTY);
        return;
    }
    if (g_current_screen == SCREEN_EMPTY) {
        ui_show_screen(SCREEN_BLUETOOTH);
        return;
    }
    if (g_current_screen >= SCREEN_USAGE_BASE) {
        int slot = g_current_screen - SCREEN_USAGE_BASE;
        if (slot + 1 < provider_count) ui_show_screen(SCREEN_USAGE_BASE + slot + 1);
        else                            ui_show_screen(SCREEN_BLUETOOTH);
        return;
    }
    ui_show_screen(provider_count > 0 ? SCREEN_USAGE_BASE : SCREEN_EMPTY);
}

void ui_toggle_splash(void) {
    if (g_current_screen == SCREEN_SPLASH) ui_show_screen(g_prev_non_splash);
    else                                    ui_show_screen(SCREEN_SPLASH);
}

static void global_click_cb(lv_event_t* e) {
    (void)e;
    ui_toggle_splash();
}

static void ble_reset_click_cb(lv_event_t* e) {
    (void)e;
    ble_clear_bonds();
}

// ---------- State application ----------

static void ensure_slot_built(int slot, ProviderKind kind) {
    ProviderScreen& s = g_screens[slot];
    if (!s.container) {
        s.container = attach_screen_container(lv_screen_active());
        s.built_kind = PK_UNKNOWN;
    }
    if (s.built_kind != kind) {
        switch (kind) {
            case PK_PCT_WINDOW:  build_pct_window(s); break;
            case PK_COST_BUDGET: build_cost_budget(s); break;
            case PK_TOKENS_ABS:  build_tokens_abs(s); break;
            case PK_TPM_RPM:     build_tpm_rpm(s); break;
            default:
                clear_children(s.container);
                build_title_block(s);
                break;
        }
        s.built_kind = kind;
    }
}

static void apply_titles(int slot, const ProviderUsage& p) {
    ProviderScreen& s = g_screens[slot];
    lv_label_set_text(s.title_lbl, p.name[0] ? p.name : p.slot_id);
    if (p.note[0]) {
        lv_obj_clear_flag(s.note_lbl, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s.note_lbl, p.note);
    } else {
        lv_obj_add_flag(s.note_lbl, LV_OBJ_FLAG_HIDDEN);
    }
}

void ui_set_state(const UsageState* st) {
    if (!st) return;
    g_last_state = *st;

    for (uint8_t i = 0; i < st->count; ++i) {
        const ProviderUsage& p = st->providers[i];
        if (!p.valid) continue;
        ensure_slot_built(i, p.kind);
        apply_titles(i, p);
        switch (p.kind) {
            case PK_PCT_WINDOW:  update_pct_window(g_screens[i], p); break;
            case PK_COST_BUDGET: update_cost_budget(g_screens[i], p); break;
            case PK_TOKENS_ABS:  update_tokens_abs(g_screens[i], p); break;
            case PK_TPM_RPM:     update_tpm_rpm(g_screens[i], p); break;
            default: break;
        }
    }

    // Hide containers beyond the active count (no longer in state)
    for (int i = st->count; i < CLAWD_MAX_PROVIDERS; ++i) {
        if (g_screens[i].container) {
            lv_obj_add_flag(g_screens[i].container, LV_OBJ_FLAG_HIDDEN);
        }
    }

    // Refresh visibility — if we were on an empty screen and providers
    // arrived, jump to the first provider screen automatically (but only
    // if we never received a screen-cycle from the user).
    if (g_current_screen == SCREEN_EMPTY && st->count > 0) {
        ui_show_screen(SCREEN_USAGE_BASE);
    }
}

float ui_primary_pct_for_rate(void) {
    for (uint8_t i = 0; i < g_last_state.count; ++i) {
        const ProviderUsage& p = g_last_state.providers[i];
        if (p.valid && p.kind == PK_PCT_WINDOW) return p.m1;
    }
    return 0.0f;
}

// ---------- Spinner animation ----------

static lv_obj_t* lbl_anim_global = nullptr;
static uint32_t anim_last_ms = 0;
static uint8_t anim_spinner_idx = 0;
static uint8_t anim_phase = 0;
static uint8_t anim_msg_idx = 0;
static uint32_t anim_msg_start = 0;
#define ANIM_MSG_MS     4000

static const char* const spinner_frames[] = {
    "\xC2\xB7", "\xE2\x9C\xBB", "\xE2\x9C\xBD",
    "\xE2\x9C\xB6", "\xE2\x9C\xB3", "\xE2\x9C\xA2",
};
#define SPINNER_COUNT 6
#define SPINNER_PHASES (2 * (SPINNER_COUNT - 1))

static const uint16_t spinner_ms[SPINNER_COUNT] = {
    260, 130, 130, 130, 130, 260,
};

#ifdef SPLASH_THEME_WINE
static const char* const anim_messages[] = {
    "Dekantieren", "Schwenken", "Verkosten",
    "Atmen lassen", "Schnuppern", "Degustieren",
    "Entkorken", "Einschenken", "Karaffieren",
    "Belüften", "Filtrieren", "Klären",
    "Reifen", "Lagern", "Würdigen",
    "Genießen", "Probieren", "Schlürfen",
    "Anstoßen", "Kredenzen", "Servieren",
};
#else
static const char* const anim_messages[] = {
    "Berechnen", "Verarbeiten", "Denken",
    "Sinnieren", "Reflektieren", "Erkunden",
    "Komponieren", "Konstruieren", "Modellieren",
    "Vermessen", "Skizzieren", "Planen",
    "Sortieren", "Bündeln", "Verweben",
    "Schmieden", "Schleifen", "Verfeinern",
    "Knobeln", "Tüfteln", "Werkeln",
};
#endif
#define ANIM_MSG_COUNT (sizeof(anim_messages) / sizeof(anim_messages[0]))

void ui_tick_anim(void) {
    // Auto-rotate through provider screens. Sits at the top so it runs
    // even if the spinner label was never created.
    ui_tick_auto_cycle();

    if (!lbl_anim_global) return;
    if (g_current_screen < SCREEN_USAGE_BASE) {
        lv_obj_add_flag(lbl_anim_global, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_clear_flag(lbl_anim_global, LV_OBJ_FLAG_HIDDEN);

    uint32_t now = lv_tick_get();
    if (now - anim_msg_start >= ANIM_MSG_MS) {
        anim_msg_idx = (anim_msg_idx + 1) % ANIM_MSG_COUNT;
        anim_msg_start = now;
    }
    if (now - anim_last_ms >= spinner_ms[anim_spinner_idx]) {
        anim_last_ms = now;
        anim_phase = (anim_phase + 1) % SPINNER_PHASES;
        anim_spinner_idx = (anim_phase < SPINNER_COUNT) ? anim_phase
                                                       : (SPINNER_PHASES - anim_phase);

        static char buf[80];
        snprintf(buf, sizeof(buf), "%s %s\xE2\x80\xA6",
                 spinner_frames[anim_spinner_idx],
                 anim_messages[anim_msg_idx]);
        lv_label_set_text(lbl_anim_global, buf);
    }
}

// ---------- Public init + BLE/battery ----------

void ui_init(void) {
    compute_layout(board_caps());

    lv_obj_t* scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, COL_BG, 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    init_icon_dsc_rgb565a8(&logo_dsc, LOGO_W, LOGO_H, LOGO_DATA);
    init_battery_icons();

    init_empty_screen(scr);
    init_bluetooth_screen(scr);
    splash_init(scr);

    if (splash_get_root()) {
        lv_obj_add_event_cb(splash_get_root(), global_click_cb, LV_EVENT_CLICKED, NULL);
    }

    logo_img = lv_image_create(scr);
    lv_image_set_src(logo_img, &logo_dsc);
    lv_obj_set_pos(logo_img, L.margin, L.title_y - 10);

    battery_img = lv_image_create(scr);
    lv_image_set_src(battery_img, &battery_dscs[0]);
    lv_obj_set_pos(battery_img, L.scr_w - 48 - L.margin, L.title_y);

    // Bottom-of-screen spinner — shared across all provider screens.
    lbl_anim_global = lv_label_create(scr);
    lv_label_set_text(lbl_anim_global, "");
    lv_obj_set_style_text_font(lbl_anim_global, &font_mono_32, 0);
    lv_obj_set_style_text_color(lbl_anim_global, COL_ACCENT, 0);
    lv_obj_align(lbl_anim_global, LV_ALIGN_BOTTOM_MID, 0, -15);
}

void ui_update_ble_status(ble_state_t state, const char* name, const char* mac) {
    if (!lbl_ble_status) return;
    switch (state) {
    case BLE_STATE_CONNECTED:
        lv_label_set_text(lbl_ble_status, "Verbunden");
        lv_obj_set_style_text_color(lbl_ble_status, COL_GREEN, 0);
        break;
    case BLE_STATE_ADVERTISING:
        lv_label_set_text(lbl_ble_status, "Sucht...");
        lv_obj_set_style_text_color(lbl_ble_status, COL_AMBER, 0);
        break;
    case BLE_STATE_DISCONNECTED:
        lv_label_set_text(lbl_ble_status, "Getrennt");
        lv_obj_set_style_text_color(lbl_ble_status, COL_RED, 0);
        break;
    default:
        lv_label_set_text(lbl_ble_status, "Initialisierung...");
        lv_obj_set_style_text_color(lbl_ble_status, COL_DIM, 0);
        break;
    }

    if (name && lbl_ble_device) {
        static char nbuf[48];
        snprintf(nbuf, sizeof(nbuf), "Gerät: %s", name);
        lv_label_set_text(lbl_ble_device, nbuf);
    }
    if (mac && lbl_ble_mac) {
        static char mbuf[48];
        snprintf(mbuf, sizeof(mbuf), "Adresse: %s", mac);
        lv_label_set_text(lbl_ble_mac, mbuf);
    }
}

void ui_update_battery(int percent, bool charging) {
    if (!battery_img) return;
    int idx;
    if (charging)            idx = 4;
    else if (percent < 0)    idx = 0;
    else if (percent <= 10)  idx = 0;
    else if (percent <= 35)  idx = 1;
    else if (percent <= 75)  idx = 2;
    else                      idx = 3;
    lv_image_set_src(battery_img, &battery_dscs[idx]);
    apply_battery_visibility(g_current_screen);
}

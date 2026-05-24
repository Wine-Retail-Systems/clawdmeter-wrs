#pragma once
#include "data.h"
#include "ble.h"

// Screen identifiers. The number of usage screens is dynamic — one per
// active provider slot — so SCREEN_USAGE_BASE is just the first; screens
// SCREEN_USAGE_BASE..SCREEN_USAGE_BASE+CLAWD_MAX_PROVIDERS-1 map to
// providers[0..count-1] at render time.
enum screen_t {
    SCREEN_SPLASH = 0,
    SCREEN_BLUETOOTH = 1,
    SCREEN_EMPTY = 2,                // shown when no provider has data yet
    SCREEN_USAGE_BASE = 100,         // SCREEN_USAGE_BASE + slot_index = that provider's screen
};

void      ui_init(void);
void      ui_set_state(const UsageState* st);    // called whenever a cycle completes
void      ui_tick_anim(void);
void      ui_show_screen(int screen);
void      ui_cycle_screen(void);
void      ui_toggle_splash(void);
int       ui_get_current_screen(void);
void      ui_update_ble_status(ble_state_t state, const char* name, const char* mac);
void      ui_update_battery(int percent, bool charging);

// Convenience for the splash / rate-grouping logic that used to read
// `session_pct` — returns the first PK_PCT_WINDOW provider's primary
// metric, or 0 if no such provider is connected.
float     ui_primary_pct_for_rate(void);

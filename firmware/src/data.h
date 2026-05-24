#pragma once
#include <Arduino.h>

// Multi-provider usage state — replaces the single-provider UsageData from
// the original single-provider firmware. The daemon sends one JSON line per
// active provider during each polling cycle, followed by an end-of-cycle
// marker `{"end":1}`. The firmware buffers incoming snapshots into the
// ProviderUsage array, keyed by `slot_id`, and treats the EOC marker as
// "the cycle is now complete — drop any provider we did not see this cycle".

#define CLAWD_MAX_PROVIDERS 6
#define CLAWD_SLOT_ID_LEN   13   // 12 chars + NUL
#define CLAWD_NAME_LEN      17   // 16 chars + NUL
#define CLAWD_NOTE_LEN      17
#define CLAWD_STATUS_LEN    17
#define CLAWD_CURRENCY_LEN  4    // 3 chars + NUL ("EUR", "USD")

#define CLAWD_PACE_UNSET    127  // sentinel — no pace data this cycle

#define CLAWD_SPARK_LEN     24   // hourly buckets for tokens_abs sparkline
#define CLAWD_SHARES_MAX    4    // donut slices for tokens_abs provider mix
#define CLAWD_SLUG_LEN      8    // 7 chars + NUL per share entry

enum ProviderKind : uint8_t {
    PK_PCT_WINDOW = 0,   // Anthropic-style: 5h-% + 7d-%, two resets
    PK_COST_BUDGET = 1,  // Langdock-style: spent vs budget (m2=0 → no budget)
    PK_TOKENS_ABS = 2,   // OpenCode-style: absolute tokens + optional backend %
    PK_TPM_RPM = 3,      // Bedrock-style: TPM/RPM %, plus monthly tokens
    PK_UNKNOWN = 255,
};

struct ProviderShare {
    char     slug[CLAWD_SLUG_LEN];
    uint8_t  pct;
};

struct ProviderUsage {
    char     slot_id[CLAWD_SLOT_ID_LEN];
    char     name[CLAWD_NAME_LEN];
    char     note[CLAWD_NOTE_LEN];
    char     status[CLAWD_STATUS_LEN];
    char     currency[CLAWD_CURRENCY_LEN];
    ProviderKind kind;
    float    m1;
    float    m2;
    float    m3;       // optional, NAN when unset
    int32_t  r1;       // seconds
    int32_t  r2;       // seconds
    int8_t   pace;     // -3..+3, CLAWD_PACE_UNSET if not provided
    float    regen;    // %/min, NAN when unset
    bool     m3_set;
    bool     regen_set;
    bool     ok;
    bool     valid;    // true once we've ever received this slot
    uint32_t last_update_ms;
    uint32_t cycle_seen;  // monotonic cycle counter — drop providers older than current

    // Optional tokens_abs visualisation extras. Populated when the daemon
    // sends "sp" / "sh" fields (currently only the OpenCode adapter).
    uint32_t spark[CLAWD_SPARK_LEN];    // hourly token buckets, oldest → newest
    bool     spark_set;
    ProviderShare shares[CLAWD_SHARES_MAX];
    uint8_t  shares_count;
};

struct UsageState {
    ProviderUsage providers[CLAWD_MAX_PROVIDERS];
    uint8_t       count;
    uint32_t      current_cycle;
    bool          any_received;  // true after the first end-of-cycle from daemon
};

// Backwards-compat alias removed — the rest of the firmware migrated to
// ProviderUsage / UsageState directly.

# UI-Layouts pro Provider-Kind

Stand 2026-05-24. Vier kind-Werte, vier Render-Funktionen in
[firmware/src/ui.cpp](../../firmware/src/ui.cpp). Jeder Provider-Screen
ruft genau eine davon basierend auf dem zuletzt gesehenen `kind`.

## `pct_window` — Anthropic-Stil

**Anwendung**: Anthropic Claude (5h + 7d Rolling Windows).

```
┌─────────────────────────────────────┐
│              Claude                  │   <- title (provider.name)
│                                      │
│  ┌───────────────────────────────┐  │
│  │  42%   ▲              Aktuell │  │   <- m1 + pace + pill
│  │  ████████████░░░░░░░░░░░░░░░░░│  │   <- bar (0-100%)
│  │  Reset in 2h 8m               │  │   <- r1 → format_reset_seconds
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  18%               Wöchentlich│  │   <- m2 + pill
│  │  ████░░░░░░░░░░░░░░░░░░░░░░░░░│  │   <- bar
│  │  Reset in 5d 4h               │  │   <- r2
│  └───────────────────────────────┘  │
│         · Berechnen…                 │   <- shared spinner
└─────────────────────────────────────┘
```

Bar-Farbe ist `pct_color(m1)` resp. `pct_color(m2)` (grün <50%, amber
50-80%, rot >=80%). Pace-Glyph erscheint nur, wenn `pace != UNSET`.

## `cost_budget` — Langdock-Stil

**Anwendung**: Workspace-Budgets in EUR/USD. Wenn `m2 > 0` (Budget
konfiguriert) gibt es einen Auslastungs-Bar; bei `m2 == 0` nur die
Verbrauchszahl mit der Note „Kein Budget gesetzt".

```
┌─────────────────────────────────────┐
│              Langdock                │
│                BYOK                  │   <- note (optional)
│                                      │
│  ┌───────────────────────────────┐  │
│  │  €87.40    ▼      von €250    │  │   <- m1+currency, pace, m2
│  │  ███████░░░░░░░░░░░░░░░░░░░░░░│  │   <- (m1/m2)*100 als Bar
│  │  35% Budget       Reset in 7d │  │   <- pct text + r2
│  └───────────────────────────────┘  │
│                                      │
│         · Reflektieren…              │
└─────────────────────────────────────┘
```

Bei `m2 == 0`:

```
│  €87.40                              │
│  Kein Budget gesetzt   Reset in 7d   │
```

## `tokens_abs` — OpenCode-Stil

**Anwendung**: Lokaler Token-Counter ohne harte Obergrenze. Optionaler
Backend-Quota-Bar (m2) wenn das Daemon-Polling die korrelierte
Backend-Auslastung erfolgreich ermitteln konnte.

```
┌─────────────────────────────────────┐
│              OpenCode                │
│         amazon-bedrock               │   <- active backend (note)
│                                      │
│  ┌───────────────────────────────┐  │
│  │  420k          Tokens heute   │  │   <- m1 (format_tokens)
│  │  +40k vs. gestern             │  │   <- (m1 - m3) Trend
│  │                                │  │
│  │  Backend: 52%                  │  │   <- m2 as bar
│  │  ███████████░░░░░░░░░░░░░░░░░░│  │
│  │                  Reset 9h 12m │  │   <- r2
│  └───────────────────────────────┘  │
│         · Werkeln…                   │
└─────────────────────────────────────┘
```

Ohne Backend-Korrelation (z.B. OpenCode auf Ollama) wird die Backend-Zeile
+ der Bar versteckt; nur die große Token-Zahl bleibt.

## `tpm_rpm` — Bedrock-Stil

> ⏸️ **Aktuell ohne aktiven Provider**: Der einzige Nutzer dieses Kinds
> ist heute der pausierte Bedrock-Adapter. Der Renderer kompiliert weiter
> mit und kann sofort genutzt werden, sobald Bedrock reaktiviert wird
> oder ein anderer Provider TPM/RPM-Daten liefert.

**Anwendung**: AWS Bedrock TPM/RPM-Quotas. Zwei stacked Bars wie bei
`pct_window`, aber semantisch unterschiedlich: m1 ist sub-minutige
Token-Throughput-Auslastung, m2 sub-minutige Request-Auslastung. m3
trägt zusätzlich die Monatssumme.

```
┌─────────────────────────────────────┐
│              Bedrock                 │
│           Sonnet 4.5                 │   <- note (model family)
│                                      │
│  ┌───────────────────────────────┐  │
│  │  42%    ▲                TPM  │  │   <- m1 + pace + pill
│  │  ████████████░░░░░░░░░░░░░░░░░│  │
│  │  12.5M Tokens / Monat         │  │   <- m3 (format_tokens)
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │  18%                      RPM │  │   <- m2 + pill
│  │  ████░░░░░░░░░░░░░░░░░░░░░░░░░│  │
│  │  Reset in 17d 8h              │  │   <- r2 (month end)
│  └───────────────────────────────┘  │
│         · Vermessen…                 │
└─────────────────────────────────────┘
```

## Empty-State

Wenn nach dem ersten EOC-Marker noch keine Provider in `g_state` sind
(Daemon läuft, schickt EOC ohne Payloads, weil im Config nichts aktiviert):

```
┌─────────────────────────────────────┐
│              Clawdmeter              │
│                                      │
│                                      │
│           Keine Provider             │
│           konfiguriert               │
│                                      │
│                                      │
│      clawdmeter-daemon setup         │
└─────────────────────────────────────┘
```

## Layout-Anpassung pro Board

`compute_layout()` in [firmware/src/ui.cpp](../../firmware/src/ui.cpp)
wählt anhand der Display-Höhe zwischen einem „Large"-Layout (>=460 px,
also AMOLED-2.16) und einem „Compact"-Layout (368×448 AMOLED-1.8). Der
einzige Unterschied ist Padding + Font-Größe; das Widget-Bauen ist
board-agnostic.

## Pace-Indikator

Ein einzelnes `lv_label` rechts oben neben m1. Glyph + Farbe aus
`pace_glyph()` resp. `pace_color()`. Bei `CLAWD_PACE_UNSET` (127) ist das
Label leer.

| pace | Glyph | Farbe          |
| ---- | ----- | -------------- |
| -3   | ↓↓    | COL_GREEN      |
| -2   | ↓     | COL_GREEN      |
| -1   | ▼     | COL_GREEN      |
|  0   | —     | COL_DIM        |
| +1   | ▲     | COL_AMBER      |
| +2   | ↑     | COL_RED        |
| +3   | ↑↑    | COL_RED        |

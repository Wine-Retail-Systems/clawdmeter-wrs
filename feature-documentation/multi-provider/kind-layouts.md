# UI-Layouts pro Provider-Kind

Stand 2026-10-07. Vier kind-Werte, vier Render-Funktionen in
[firmware/src/ui.cpp](../../firmware/src/ui.cpp). Jeder Provider-Screen
ruft genau eine davon basierend auf dem zuletzt gesehenen `kind`.

> **Wichtige Änderungen (2026-10-07):**
> - `cost_budget`: Budget-Balken ist jetzt nach Modellfamilie segmentiert (wenn `sh` vorhanden), mit Farblegend darunter.
> - `tokens_abs`: Sparkline und „vs. gestern"-Zeile entfernt — nur noch Wert, Donut und Reset-Countdown.

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

## `cost_budget` — Budget-Monitor mit Segmentierung

**Anwendung**: Workspace-Budgets in EUR/USD (Langdock, Bifrost, etc.). Wenn `m2 > 0` (Budget konfiguriert) gibt es einen Auslastungs-Bar. Bei Vorhandensein von `sh` (Modellfamilien-Anteile) ist der Balken nach Anteilen segmentiert; sonst einfarbig nach Auslastungsstatus. Bei `m2 == 0` nur die Verbrauchszahl mit der Note „Kein Budget gesetzt", ohne Pace-Glyph.

Beträge ab 10.000 erscheinen ohne Nachkommastellen mit Tausenderpunkt (`$16.500`, `von $15.000`), darunter mit zwei Nachkommastellen. Der Pace-Glyph (Mono 18) steht rechts neben der Prozentangabe, nicht in der Kopfzeile.

**Mit Segmentierung (z. B. Bifrost):**

```
┌─────────────────────────────────────┐
│            LLM Gateway               │
│              sascha.krinke           │   <- note (optional)
│                                      │
│  ┌───────────────────────────────┐  │
│  │  $3769.16       von $15.000   │  │   <- m1+currency, m2
│  │  ███████░░░░░░░░░░░░░░░░░░░░░░│  │   <- segmentiert nach sh
│  │  ● Opus 74%  ● Sonnet 26%     │  │   <- Legende mit Farbe + %
│  │  25% Budget ▲     Reset in 7d │  │   <- pct (Statusfarbe) + pace + r2
│  └───────────────────────────────┘  │
│                                      │
│         · Dekantieren…               │
└─────────────────────────────────────┘
```

**Ohne Segmentierung (Langdock oder Bifrost ohne `sh`):**

```
┌─────────────────────────────────────┐
│              Langdock                │
│                BYOK                  │
│                                      │
│  ┌───────────────────────────────┐  │
│  │  €87.40               von €250│  │   <- m1+currency, m2
│  │  ███████░░░░░░░░░░░░░░░░░░░░░░│  │   <- einfarbig nach Status
│  │  35% Budget       Reset in 7d │  │
│  └───────────────────────────────┘  │
│                                      │
│         · Reflektieren…              │
└─────────────────────────────────────┘
```

**Bei `m2 == 0` (kein Budget):**

```
│  €87.40                              │
│  Kein Budget gesetzt   Reset in 7d   │
```

**Segmentpalette:** Graustufenrampe aus hellem zu dunklerem Grau, absteigend nach Anteil. Keine Grün-/Amber-/Rot-Farben im Balken selbst — die Auslastungswarnung bleibt auf der Prozentangabe (z. B. rot ab 80 %), damit Status auch mit Segmentierung erkennbar bleibt.

## `tokens_abs` — Token-Aktivität

**Anwendung**: Token-Counter ohne harte Obergrenze (z. B. Langdock managed-Modus). Zeigt Tageswert, Donut-Breakdown nach Aktivitäts-Kategorie und Reset-Countdown bis Mitternacht.

Optionaler Backend-Quota-Bar (m2, 0–100 %), wenn das Gateway Quota-Daten liefert.

```
┌─────────────────────────────────────┐
│              Langdock                │
│              Aktivität               │   <- note
│                                      │
│  ┌───────────────────────────────┐  │
│  │  420k          Tokens heute   │  │   <- m1 (format_tokens)
│  │                                │  │
│  │  ● Chat 45%  ● Projekt 35%    │  │   <- Donut-Legende (sh)
│  │  ● Workflow 20%                │  │
│  │                  Reset 9h 12m │  │   <- r2
│  └───────────────────────────────┘  │
│         · Werkeln…                   │
└─────────────────────────────────────┘
```

Mit Backend-Quota (z. B. Langdock BYOK mit quota-Tracking):

```
│  Backend-Quota: 52%                │
│  ███████████░░░░░░░░░░░░░░░░░░     │
```

**Wichtig (seit 2026-10-07):** Die vorherige 24-Stunden-Sparkline und „vs. gestern"-Vergleich werden nicht mehr angezeigt. Das Feld `sp` im BLE-Payload wird ignoriert (Rückwärtskompatibilität mit älteren Daemons).

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

# Provider: Anthropic (Claude Pro/Max via OAuth)

Pollt `api.anthropic.com/v1/messages` mit einem minimalen Haiku-Request
(1 max_token) und liest die `anthropic-ratelimit-unified-*` Response-Header.
Der Request selbst kostet praktisch nichts; relevant sind nur die Header.

Quelle: [daemon/clawdmeter_daemon/providers/anthropic.py](../../daemon/clawdmeter_daemon/providers/anthropic.py)

## Snapshot-Mapping

| Snapshot-Feld | Header                                                                                       | Bedeutung |
|---------------|----------------------------------------------------------------------------------------------|-----------|
| `m1`          | `anthropic-ratelimit-unified-5h-utilization` × 100                                           | "Aktuell" — aktuelles 5h-Fenster, 0..100 % verbraucht |
| `r1`          | `anthropic-ratelimit-unified-5h-reset`                                                       | Sekunden bis zum nächsten 5h-Reset |
| `m2`          | `max(unified-7d-utilization, unified-7d-opus-utilization)` × 100                             | "Wöchentlich" — bindendes 7-Tage-Fenster (s. u.) |
| `r2`          | Reset des verbindlichen 7-Tage-Fensters                                                      | Sekunden bis zum nächsten 7d-Reset |
| `status`      | `anthropic-ratelimit-unified-5h-status`                                                      | i. d. R. `ok` oder `rate_limited` |
| `pace`        | berechnet aus `m1` vs. `(elapsed / 5h)`                                                      | -3..+3, gibt an, ob der User langsamer/schneller verbraucht als linear erwartet |
| `regen`       | berechnet aus zwei aufeinanderfolgenden `m1`-Werten                                          | %/min Regeneration (nur > 0, sonst `None`) |

## Zwei 7-Tage-Fenster

Pro/Max-Subscriptions haben **zwei** Weekly-Quoten:

- `unified-7d-utilization` — Summe über alle Modelle.
- `unified-7d-opus-utilization` — separate, strengere Opus-Quote.

Claude Code zeigt im `/status` jeweils das bindende, also knappere Limit.
Bei Opus-lastiger Nutzung ist das fast immer die Opus-Quote. Der Daemon
spiegelt das, indem er für `m2` `max(...)` der beiden Werte nimmt und den
Reset des bindenden Fensters mitliefert.

Vor dem Fix (2026-05-29) wurde nur `unified-7d-utilization` gelesen — bei
Opus-lastiger Nutzung zeigte das Display deutlich weniger Verbrauch, als der
User in seinem `claude` CLI sah.

## Bekannte Eigenheiten

- Token wird primär aus dem macOS-Keychain (`Claude Code-credentials`) gelesen,
  Fallback auf `~/.claude/.credentials.json`. Auf Linux/Windows nur Datei.
- `regen` ist eine Schätzung über zwei aufeinanderfolgende Polls (Anthropic
  liefert keinen Regen-Header). Resets zu `None` nach Window-Rollover.
- Die `unified-*`-Header sind **nicht** in der öffentlichen Anthropic-API-Doku
  beschrieben — sie existieren nur für OAuth-/Subscription-Traffic.

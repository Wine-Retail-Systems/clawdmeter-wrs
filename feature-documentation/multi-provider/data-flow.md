# Multi-Provider Datenfluss

Wie Daten von einem LLM-Provider zum Display kommen — Stand 2026-05-24.

> ⏸️ **Bedrock-Hinweis**: Der Bedrock-Adapter wird in diesem Dokument als
> Architektur-Beispiel weiter mitgeführt, ist aber aktuell pausiert. Im
> echten Polling-Lauf taucht er nicht auf. Details:
> [providers/bedrock.md](../providers/bedrock.md).

## Übersicht

```
┌──────────────────────────┐   poll(cfg)   ┌────────────────────────┐
│  LLM-Provider-APIs       │ ◄──────────── │  Provider-Adapter      │
│  (Anthropic / Codex /    │               │  (anthropic.py /       │
│   Langdock / Bedrock /   │ ───Snapshot──►│   codex.py / ...)      │
│   OpenCode-DB)           │               │                        │
└──────────────────────────┘               └───────────┬────────────┘
                                                       │
                                                       ▼
                                  ┌────────────────────────────────────┐
                                  │  polling.py                        │
                                  │  - Per-Provider TTL                │
                                  │  - Backend-Quota-Korrelation       │
                                  │    (OpenCode ↔ Bedrock etc.)       │
                                  └───────────┬────────────────────────┘
                                              │ list[Snapshot]
                                              ▼
                                  ┌────────────────────────────────────┐
                                  │  ble.Session.send_cycle()          │
                                  │  N × JSON-write + {"end":1}        │
                                  └───────────┬────────────────────────┘
                                              │ GATT RX
                                              ▼
                                  ┌────────────────────────────────────┐
                                  │  Firmware ble.cpp                  │
                                  │  → rx_buf, data_ready              │
                                  └───────────┬────────────────────────┘
                                              │
                                              ▼
                                  ┌────────────────────────────────────┐
                                  │  main.cpp parse_json()             │
                                  │  - Slot-Lookup nach "p"-Feld       │
                                  │  - bei EOC: prune_stale_slots()    │
                                  │  - UsageState g_state              │
                                  └───────────┬────────────────────────┘
                                              │ ui_set_state()
                                              ▼
                                  ┌────────────────────────────────────┐
                                  │  ui.cpp                            │
                                  │  - ensure_slot_built(kind)         │
                                  │  - update_pct_window / _cost_      │
                                  │    budget / _tokens_abs / _tpm_rpm │
                                  └────────────────────────────────────┘
```

## Pro Polling-Zyklus

Eine Iteration des Daemon-Loops (`polling.main_loop` → `connect_and_run`):

1. **Wake-Trigger**: `TICK=5s` Timer ODER device-initiierter Refresh-Request
   via REQ-Characteristic.
2. **Provider-Auswahl**: pro `ProviderState` prüfen, ob `next_poll_at <= now`
   ODER ob ein Refresh-Request einen Force-All ausgelöst hat.
3. **Poll**: jedes fällige Provider-Objekt liefert ein `Snapshot` oder
   `None` (Fehler/keine Credentials).
4. **Korrelation**: `correlate_backend_quota()` schaut, ob ein `tokens_abs`-
   Snapshot (typisch: OpenCode) einen `active_provider` im `extra`-Feld
   trägt, und kopiert in dem Fall den primären Auslastungswert (`m1`) des
   passenden Backend-Snapshots in das `m2`-Feld des OpenCode-Snapshots.
   Mapping: OpenCode-ID `amazon-bedrock` → unser Adapter-ID `bedrock`.
5. **BLE-Send**: `ble.Session.send_cycle(payloads)` schreibt sequentiell
   alle Snapshots als JSON-Strings auf die RX-Characteristic, mit 80 ms
   Pause zwischen Schreibvorgängen (sonst koalesziert NimBLE die Writes
   und verschluckt sich). Am Ende ein zusätzlicher `{"end":1}`-Write.
6. **Firmware-Aufnahme**: jeder Write triggert `RxCallbacks::onWrite`,
   setzt `data_ready=true`. Main-Loop ruft `parse_json` auf:
   - Provider-Payload → Slot-Suche/Erzeugung in `g_state.providers[]`,
     Update aller Felder, `cycle_seen = current_cycle`.
   - EOC-Marker → `prune_stale_slots()` (entfernt alles, was nicht in
     diesem Zyklus gesehen wurde), `current_cycle++`,
     `ui_set_state(&g_state)`.
7. **Render**: `ui_set_state` läuft pro Slot, baut bei Bedarf das
   kind-spezifische Widget-Set neu (`ensure_slot_built`), aktualisiert
   Werte. Springt aus `SCREEN_EMPTY` automatisch in den ersten Provider-
   Screen, sobald Daten ankommen.

## Wann wird ein Provider entfernt?

Wenn der User den `enabled = false` setzt oder den `[[provider]]`-Block
aus dem TOML löscht und den Daemon neustartet:

1. Beim nächsten erfolgreichen Cycle wird dieser Slot **nicht** mehr
   geschrieben.
2. Der EOC-Marker triggert `prune_stale_slots()` — der Slot verschwindet
   aus `g_state.providers[]`.
3. `ui_set_state` versteckt den zugehörigen Container.
4. Bei `provider_count == 0` greift `ui_show_screen(SCREEN_EMPTY)` beim
   nächsten Cycle-Wechsel.

## Was passiert bei einem Daemon-Fehler?

- **Adapter wirft Exception** (Netz weg, AWS-Profil broken, Langdock-CSV
  malformed) → `polling.run_cycle` fängt ab, der Snapshot bleibt
  `None`, `last_snapshot` zeigt weiterhin den vorherigen Wert. Der
  Slot wird im aktuellen Cycle **mitgesendet** — der User sieht den
  letzten bekannten Wert weiter, kein „leerer" Screen.
- **BLE-Disconnect** → Daemon räumt auf, scannt neu, reconnect. Der
  Firmware-Slot-State überlebt einen Reconnect (er wird erst durch
  einen EOC-Marker invalidiert, nicht durch BLE-State).
- **Daemon stirbt** → systemd/launchd/Task-Scheduler startet neu; bei
  Connect läuft der erste Cycle automatisch im `force_all`-Modus, so
  dass alle Slots sofort initialisiert werden.

## Per-Provider TTLs (Default)

| Provider  | Default `poll_seconds` | Begründung                                  |
| --------- | --------------------- | ------------------------------------------- |
| Anthropic | 60                    | Header-Polling ist quasi kostenfrei         |
| Codex     | 60                    | `wham/usage` ist genauso billig wie Anthropic-Header |
| OpenCode  | 15                    | Lokaler SQLite-Read, kein Netz              |
| Langdock  | 600                   | CSV-Export-Latenz ~30s; öfter ist sinnlos   |
| Bedrock   | 60 *(pausiert)*       | CloudWatch-GetMetricData kostet ~$2/Monat   |

Über `poll_seconds` im jeweiligen `[[provider]]`-Block individuell
überschreibbar.

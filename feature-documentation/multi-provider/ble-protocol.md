# BLE-Protokoll v2 — Multi-Provider

Stand 2026-05-24. Ablöst das alte Single-Provider-Schema mit `s/sr/w/wr/st/ok`.

> ⏸️ **Bedrock-Hinweis**: Der Bedrock-Adapter ist aktuell pausiert (siehe
> [providers/bedrock.md](../providers/bedrock.md)). Die `bedrock-*`-Beispiele
> in diesem Dokument zeigen die geplante Schema-Belegung für den Tag, an
> dem der Adapter reaktiviert wird — sie laufen aktuell nicht über die BLE.

## Transport

Unverändert gegenüber v1 — drei Characteristics auf dem custom GATT-Service:

| Rolle                   | UUID                                     | Properties        |
| ----------------------- | ---------------------------------------- | ----------------- |
| Service                 | `4c41555a-4465-7669-6365-000000000001`   |                   |
| RX (Daemon → Device)    | `4c41555a-4465-7669-6365-000000000002`   | WRITE, WRITE_NR   |
| TX (Device → Daemon)    | `4c41555a-4465-7669-6365-000000000003`   | READ, NOTIFY      |
| REQ (Device → Daemon)   | `4c41555a-4465-7669-6365-000000000004`   | NOTIFY            |

Die HID-Tastatur (Space / Shift+Tab) bleibt unter Standard-UUID `0x1812`
unabhängig davon.

## Nachrichtenformat

Eine RX-Write enthält **eine** UTF-8-kodierte JSON-Zeile, kein NDJSON. Pro
Polling-Zyklus schickt der Daemon **mehrere** Writes sequentiell:

```
N × Provider-Payload   (eine Zeile pro aktiver Provider-Slot)
1 × End-of-Cycle       ({"end":1})
```

Zwischen den Writes liegt ein konstanter 80 ms-Delay — kürzer und NimBLE
auf dem ESP32 verschluckt Pakete.

## Provider-Payload

```json
{
  "p":    "bedrock-s45",     // Slot-ID (max 12 chars). Eindeutig + Sort-Key.
  "n":    "Bedrock",          // Display-Name (max 16 chars).
  "note": "Sonnet 4.5",       // Optional sub-line (max 16 chars).
  "k":    "tpm_rpm",          // Kind: pct_window | cost_budget | tokens_abs | tpm_rpm
  "m1":   42.0,               // Primäre Metrik
  "m2":   18.5,               // Sekundäre Metrik
  "m3":   12500000,           // Optional, dritte Metrik
  "r1":   0,                  // Reset 1 in Sekunden (0 = nicht verwendet)
  "r2":   2592000,            // Reset 2 in Sekunden
  "pace": 2,                  // Optional, -3..+3 Burn-Rate-Indikator
  "regen": 3.2,               // Optional, %/min Rolling-Regen
  "cur":  "USD",              // Optional, Currency-Code
  "st":   "ok",               // Status-Text (max 16 chars)
  "ok":   true                // false bei Fehler beim Daemon → letzte Werte
}
```

Die Bedeutung von `m1/m2/m3` und `r1/r2` ist **kind-abhängig**:

| Kind          | m1                  | m2                          | m3                       | r1                | r2                  |
| ------------- | ------------------- | --------------------------- | ------------------------ | ----------------- | ------------------- |
| `pct_window`  | kurzes Fenster %    | langes Fenster %            | —                        | kurzer Reset (s)  | langer Reset (s)    |
| `cost_budget` | verbrauchter Betrag | Budget (0 = nicht gesetzt)  | —                        | —                 | sec bis Monatsende  |
| `tokens_abs`  | Tokens heute        | Backend-Quota % (0 = aus)   | gestern (Vergleich)      | —                 | sec bis Mitternacht |
| `tpm_rpm`     | TPM %               | RPM %                       | Monats-Tokens (absolut)  | —                 | sec bis Monatsende  |

Beispiele für die vier Kinds — alle echte Bytes-Größen unter 220 B:

```json
{"p":"anthropic","n":"Claude","k":"pct_window","m1":42.0,"m2":18.0,"r1":7200,"r2":432000,"pace":1,"regen":2.5,"st":"ok","ok":true}

{"p":"langdock","n":"Langdock","note":"BYOK","k":"cost_budget","m1":87.40,"m2":250.0,"r2":1209600,"pace":-1,"cur":"EUR","st":"ok","ok":true}

{"p":"opencode","n":"OpenCode","note":"amazon-bedrock","k":"tokens_abs","m1":420000,"m2":52.3,"m3":380000,"r2":54000,"st":"ok","ok":true}

{"p":"bedrock-s45","n":"Bedrock","note":"Sonnet 4.5","k":"tpm_rpm","m1":42.0,"m2":18.5,"m3":12500000,"r2":2592000,"pace":2,"cur":"USD","st":"ok","ok":true}
```

## End-of-Cycle Marker

```json
{"end":1}
```

Nichts anderes. Triggert auf dem Gerät:

1. `current_cycle++`
2. `prune_stale_slots()` — alle Provider, die in diesem Cycle **nicht**
   geschrieben wurden, werden aus `g_state` entfernt. So verschwindet ein
   deaktivierter Provider sauber.
3. `ui_set_state(&g_state)` → Render-Switch + Auto-Empty-Recovery.

## Pace-Mapping

`pace` ist auf der Daemon-Seite ein Integer von -3 bis +3, das jeder
Adapter selbst berechnet. Konvention:

- **Negativ** = User verbrennt langsamer als linear erwartet → grüne
  Indikator-Farbe, „du hast Reserve".
- **0** = on-track (Default-Anzeige neutral grau).
- **Positiv** = schneller als erwartet → amber/rot. Bei `+3` blinkt das
  UI optional (nicht implementiert, Reserve).

Die Glyphen kommen aus dem Mono-Font (UTF-8):

| pace | Glyph     | Bedeutung               |
| ---- | --------- | ----------------------- |
| -3   | ↓↓        | sehr langsam            |
| -2   | ↓         | spürbar langsam         |
| -1   | ▼         | leicht langsam          |
|  0   | —         | on-track                |
| +1   | ▲         | leicht schnell          |
| +2   | ↑         | spürbar schnell         |
| +3   | ↑↑        | sehr schnell (heiß)     |

## TX / Ack

Pro RX-Write antwortet das Gerät auf der TX-Char (NOTIFY) mit einem
ein-Wert-Ack:

```json
{"ack":true}    // Payload akzeptiert
{"err":true}    // Payload unparsebar
```

Der Daemon abonniert das nicht — die Acks sind nur fürs `tail -f` beim
Debugging.

## REQ — Device-initiierter Refresh

Wenn das Gerät beim Connect noch nie Daten gesehen hat, schickt es eine
NOTIFY auf der REQ-Char mit Payload `0x01`. Der Daemon (siehe
`polling.connect_and_run` → `force_all = True`) feuert dann sofort einen
vollen Cycle aller aktiven Provider, statt auf die individuellen TTLs zu
warten.

## Größen + MTU

ESP32 mit NimBLE handelt eine MTU von 247 (244 Bytes Nutzlast) aus. Unsere
Payloads bleiben deutlich darunter:

- Minimaler Provider-Payload (`pct_window` ohne optionale Felder): ~70 B
- Maximaler Provider-Payload (`tpm_rpm` mit allen optionalen + 16-Byte-
  Strings): ~220 B
- EOC: 10 B

Kein Chunking nötig. Wenn wir den 5. oder 6. Provider hinzufügen, ändert
sich nichts — pro Write je ein Payload, ein Write pro 80 ms.

## Versionsindikator

Es gibt **keinen** expliziten Protokoll-Version-Header. Das Schema ist:

- v1 (alt): Eine einzelne Zeile pro Cycle, Felder `s/sr/w/wr/st/ok`.
- v2 (aktuell): N Zeilen mit `p`-Feld + EOC.

Die Firmware-Parse-Logik ist gegen v1 nicht rückwärtskompatibel — beim
Update muss daemon und firmware gemeinsam aktualisiert werden. Bei
v2→v3 wird's einen Header geben (Reserve).

# AWS Bedrock Provider — Discovery

> ## ⏸️ Adapter aktuell pausiert (Stand 2026-05-24)
>
> Der Bedrock-Adapter ist nicht im aktiven Provider-Set. Hintergrund:
> CloudWatch (`GetMetricStatistics`) und Service Quotas (`ListServiceQuotas`)
> akzeptieren **keine** Bedrock-API-Keys, sondern nur klassische IAM-
> Credentials. Bis ein dedizierter Read-Only-IAM-User mit den unten gelisteten
> Berechtigungen eingerichtet ist, fragt der Setup-Wizard Bedrock nicht ab
> und der Daemon pollt nichts.
>
> Der Adapter-Code (`daemon/clawdmeter_daemon/providers/bedrock.py`) und der
> zugehörige UI-Renderer (`PK_TPM_RPM` in `firmware/src/ui.cpp`) bleiben
> vollständig im Repo erhalten — eine Reaktivierung ist ein reiner
> Config-Change plus `pip install boto3`.
>
> Diese Discovery-Notiz beschreibt die geplante Architektur und ist als
> Implementations-Spec gedacht, falls der IAM-Pfad später aufgesetzt wird.

Recherche-Stand: 2026-05-24. Quellen am Ende verlinkt.

## Datenquellen-Übersicht

AWS verteilt die für unseren Use-Case relevanten Informationen auf zwei
Dienste. Beide werden per `boto3` abgefragt; beide sind regionsgebunden.

| Frage                                              | Service                | API-Call                                              | Liefert                                       |
| -------------------------------------------------- | ---------------------- | ----------------------------------------------------- | --------------------------------------------- |
| Wie viel TPM/RPM ist gebucht? (Limit)              | `service-quotas`       | `list_service_quotas` / `get_service_quota`           | Zahl + Quota-Code, pro Region, pro Modell     |
| Wie viel wird gerade verbraucht? (Ist-Wert)        | `cloudwatch`           | `get_metric_data` über Namespace `AWS/Bedrock`        | Token-Zähler in 1-Minuten-Aggregation         |
| Welche Modelle sind verfügbar?                     | `bedrock`              | `list_foundation_models`, `list_inference_profiles`   | Modell-IDs / Inference-Profile-IDs            |
| Welche Modelle dürfen wir aufrufen?                | `bedrock`              | `get_foundation_model_availability` (optional)        | "ACCESS_GRANTED" / "NOT_AVAILABLE"            |
| Kontostand / Rechnung                              | `ce` (Cost Explorer)   | `get_cost_and_usage`                                  | nicht TPM, sondern USD — out of scope für MVP |

**Wichtig:** Bedrock liefert kein konsolidiertes "wie viele Tokens habe ich
heute genutzt?"-Endpoint analog zu Anthropics `/usage`. Wir müssen es aus
CloudWatch berechnen.

## Quota-Codes pro Modell

AWS publiziert die `L-XXXXXXXX`-Codes für die TPM/RPM-Quotas **nicht in der
General-Reference-Tabelle**. Sie sind nur via `service-quotas`-API
auffindbar. Der Quota-**Name** folgt aber einem stabilen Muster:

```
On-demand model inference tokens per minute for Anthropic Claude <Variante>
On-demand model inference requests per minute for Anthropic Claude <Variante>
```

Beispiele (Variante = der Modellname wie im Service-Quotas-Console-Eintrag):

- `On-demand model inference tokens per minute for Anthropic Claude Sonnet 4`
- `On-demand model inference tokens per minute for Anthropic Claude Sonnet 4.5`
- `On-demand model inference tokens per minute for Anthropic Claude Haiku 4.5`
- `On-demand model inference requests per minute for Anthropic Claude Sonnet 4.5`

Praktisch heißt das: Wir können beim Daemon-Start die Codes per Filter über
`list_service_quotas` ermitteln und cachen (siehe Code-Skizze unten).

```bash
aws service-quotas list-service-quotas \
  --service-code bedrock \
  --region us-east-1 \
  --query "Quotas[?contains(QuotaName, 'On-demand') && contains(QuotaName, 'Sonnet 4.5') && contains(QuotaName, 'tokens per minute')].{Name:QuotaName,Code:QuotaCode,Value:Value,Adjustable:Adjustable}" \
  --output table
```

Die zurückgegebenen QuotaCodes sind **pro Account und Region** stabil, aber
nicht öffentlich dokumentiert — daher dynamisch auflösen, nicht
hardcoden. Default-Werte (Stand Mai 2026, ohne Quota-Increase) bewegen
sich zwischen 200k und 8M TPM, je nach Modell und Region; neue Konten
starten teils mit deutlich reduzierten Quotas.

**Regions- und Modell-Bindung:** Jede Quota gilt
**pro Region pro Basismodell**. Cross-Region-Inference-Profile
(`us.anthropic.claude-sonnet-4-5-v1:0`,
`eu.anthropic.claude-sonnet-4-5-v1:0`, `apac.anthropic...`,
`global.anthropic...`) verteilen Requests auf mehrere Destination-Regionen,
verbrauchen aber die **Quota der jeweiligen Destination-Region**, die der
Router gewählt hat. Für UI-Zwecke aggregieren wir daher pro Source-Region,
nicht pro Inference-Profile-ID.

## CloudWatch-Metriken

Namespace: **`AWS/Bedrock`**. Alle Runtime-Metriken werden mit der Dimension
`ModelId` veröffentlicht; für Cross-Region-Profile ist das die
Inference-Profile-ID (z. B. `us.anthropic.claude-sonnet-4-5-v1:0`).

| Metric Name               | Unit         | Bedeutung                                            | Statistic empfohlen |
| ------------------------- | ------------ | ---------------------------------------------------- | ------------------- |
| `Invocations`             | SampleCount  | Erfolgreiche Calls (Converse/InvokeModel/…)          | Sum                 |
| `InvocationThrottles`     | SampleCount  | Vom System gedrosselte Calls                         | Sum                 |
| `InvocationLatency`       | Milliseconds | Time-to-last-token                                   | Average / p99       |
| `InvocationClientErrors`  | SampleCount  | 4xx                                                  | Sum                 |
| `InvocationServerErrors`  | SampleCount  | 5xx                                                  | Sum                 |
| `InputTokenCount`         | SampleCount  | Input-Tokens (ohne Cache-Reads)                      | Sum                 |
| `OutputTokenCount`        | SampleCount  | Output-Tokens (vor Burndown)                         | Sum                 |
| `CacheReadInputTokens`    | SampleCount  | Aus Prompt-Cache gelesen — **zählt NICHT auf TPM**   | Sum                 |
| `CacheWriteInputTokens`   | SampleCount  | In Prompt-Cache geschrieben — **zählt auf TPM**      | Sum                 |
| `EstimatedTPMQuotaUsage`  | Count        | Geschätzter TPM-Verbrauch nach AWS-Burndown-Formel   | Sum                 |
| `TimeToFirstToken`        | Milliseconds | TTFT (Streaming)                                     | Average / p50       |

**Dimensionen:** `ModelId` (universell), optional `ServiceTier`,
`ResolvedServiceTier`, `ContextWindow` (für Kontextfenster > 200k).
Es gibt **keine `Region`-Dimension** — die Region ist implizit durch den
CloudWatch-Endpoint, an den wir uns connecten.

**Period:** 60 Sekunden (auf 1-Min-Quota-Fenster ausgerichtet).
**Statistic:** `Sum` für Token-/Invocation-Zähler, `Average` für Latenzen.

`EstimatedTPMQuotaUsage` ist die einfachste Größe für unseren Use-Case —
AWS hat die Burndown-Formel hier schon angewendet (inkl. 5x-Multiplikator
auf Output bei Claude ≥ 3.7) und liefert direkt einen vergleichbaren Wert
gegen die TPM-Quota.

## TPM/RPM-Auslastung berechnen

**Burndown-Logik (Claude 3.7 und neuer, inklusive Sonnet 4.x / Haiku 4.5 /
Opus 4.x):**

```
quota_consumption = InputTokenCount + CacheWriteInputTokens + (OutputTokenCount * 5)
```

`CacheReadInputTokens` zählen **nicht** auf die TPM-Quota. Für ältere
Nicht-Claude-Modelle ist der Burndown 1:1.

**Auslastung pro Minute:**

```
tpm_used_last_minute   = Sum(EstimatedTPMQuotaUsage, period=60s)        # bequemer Weg
                       # oder manuell:
                       # Sum(InputTokenCount) + Sum(CacheWriteInputTokens) + 5 * Sum(OutputTokenCount)
tpm_limit              = service_quotas.GetServiceQuota(QuotaCode=...).Value
tpm_pct                = round(100 * tpm_used_last_minute / tpm_limit)

rpm_used_last_minute   = Sum(Invocations, period=60s)
rpm_limit              = service_quotas.GetServiceQuota(QuotaCode=RPM).Value
rpm_pct                = round(100 * rpm_used_last_minute / rpm_limit)
```

**Gotcha:** AWS warnt explizit, dass `EstimatedTPMQuotaUsage` **post-hoc**
ist und nicht die Reservierungs-Logik abbildet, mit der Throttling
entschieden wird. Echtes Throttling rechnet `InputTokenCount +
CacheWriteInputTokens + max_tokens` (Reservation upfront, vor der
Generierung). Für eine "wie ausgelastet bin ich gerade"-Anzeige reicht
`EstimatedTPMQuotaUsage` aber locker — wir messen Nutzung, nicht
Throttling-Risiko.

## Sekundäre Metrik (UX-Empfehlung)

Da TPM/RPM **pro Minute** zurücksetzen, ist "Reset in X Sekunden" für ein
Desk-Display unsinnig (würde jede Sekunde sichtbar tickern und keine
Information transportieren). Drei Optionen wurden geprüft:

| Option                                        | Pro                                                      | Contra                                              |
| --------------------------------------------- | -------------------------------------------------------- | --------------------------------------------------- |
| (a) Monatlicher Token-Verbrauch               | matched Anthropic-Provider-Layout; klare Story für Kosten | erfordert großes GetMetricData-Fenster (30d)        |
| (b) Burst der letzten 5 Minuten               | reagiert sichtbar, gibt "Trend"-Gefühl                   | mit TPM-Anzeige redundant — beides ist Kurzfristig  |
| (c) Anzahl Throttles letzte Stunde            | direkter "Pain"-Indikator                                | bei stabilem Setup meist 0, langweilige Anzeige     |

**Empfehlung: (a) — monatlicher Token-Verbrauch.** Begründung:

1. UX-Konsistenz mit dem geplanten Anthropic-Provider (dort gibt es eine
   echte Monatsrechnung; Bedrock-Token korrelieren stark damit, auch wenn
   AWS pro 1k Tokens abrechnet, nicht pauschal).
2. Eine schnelle und eine langsame Metrik nebeneinander ist die übliche
   Display-Logik (BPM vs. Tagesschritte bei Fitness-Trackern). TPM ist die
   schnelle (Sekunden), Monatsverbrauch die langsame (Tage).
3. Kostenseitig vertretbar: ein einzelner `GetMetricData`-Call über 30 Tage
   in 1-Stunden-Aggregation = 720 Datenpunkte, also ~720 Metric-Charges
   einmalig + Δ pro Minute (siehe Polling-Kosten).

Im BLE-Payload landen daher `m1 = tpm_pct`, `m2 = rpm_pct`, und z. B.
`r1 = monthly_input_tokens`, `r2 = monthly_output_tokens` (oder nur
`r1 = total monthly tokens`, je nach Display-Layout).

## IAM-Policy (minimal)

Read-only — der Daemon ändert nichts, er liest nur Metriken und Quotas.
`bedrock:*` selbst brauchen wir **nicht** (wir invoken keine Modelle).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadBedrockQuotas",
      "Effect": "Allow",
      "Action": [
        "servicequotas:ListServiceQuotas",
        "servicequotas:GetServiceQuota"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadBedrockMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "AWS/Bedrock"
        }
      }
    },
    {
      "Sid": "ListBedrockModels",
      "Effect": "Allow",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:ListInferenceProfiles"
      ],
      "Resource": "*"
    }
  ]
}
```

Die `cloudwatch:namespace`-Condition begrenzt den GetMetricData-Read auf
unseren Bedrock-Namespace — saubere Trennung von anderen Workloads im
selben Account.

## Auth-Konfiguration für unseren Daemon

`boto3` bringt seine eigene Credential-Chain mit; wir reiten darauf, statt
eigene Mechanik zu bauen. Reihenfolge wie üblich:

1. Environment-Variablen (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
   optional `AWS_SESSION_TOKEN`).
2. Shared Credentials File `~/.aws/credentials` + `AWS_PROFILE`.
3. IAM-Role (EC2 Instance Metadata / ECS Task Role / SSO).

Empfehlung für den User: einen **dedizierten Read-Only-IAM-User** mit obiger
Policy anlegen, Access-Key + Profile-Name in `~/.aws/credentials`
hinterlegen, und in unserer `clawdmeter.toml`:

```toml
[bedrock]
enabled       = true
profile       = "clawdmeter"          # AWS profile name
region        = "us-east-1"           # primäre Region; Liste s. unten
models        = ["us.anthropic.claude-sonnet-4-5-v1:0"]
poll_interval = 60                    # Sekunden
secondary     = "monthly_tokens"      # oder "burst_5m" / "throttles_1h"
```

Region ist Pflicht — siehe nächster Abschnitt. Falls leer, fällt boto3 auf
`AWS_DEFAULT_REGION` / die Profile-Region zurück; wir sollten das explizit
loggen, wenn nichts gesetzt ist.

## Polling-Kosten

CloudWatch berechnet GetMetricData mit **$0.01 pro 1.000 abgefragten
Metriken** (us-east-1; in opt-in-Regionen geringfügig anders). Eine
"Metrik" ist hier ein Datenpunkt-Stream, nicht eine API-Aufruf-Zeile.

Konkrete Kalkulation für unseren Daemon, 60-s-Polling, ein Modell, primäre
+ sekundäre Metrik:

```
Pro Poll:
  - TPM/RPM-Kern: 1 Call, 3 Metriken (EstimatedTPMQuotaUsage,
    Invocations, InvocationThrottles)              = 3 metrics
  - Sekundäre (monatlich aggregiert):              = 2 metrics
  Summe pro Poll: 5 metrics

Polls pro Tag: 86400 / 60 = 1440
Metriken pro Tag: 1440 * 5 = 7200
Metriken pro Monat (30d): 216_000

Kosten pro Monat: 216_000 / 1000 * $0.01 = $2.16
```

Bei mehreren Modellen multipliziert sich das linear pro Modell. Bei einem
typischen Single-Model-Setup also **rund 2 USD/Monat**. User-Hinweis: Wir
dokumentieren das prominent im Setup (analog zum Anthropic-Provider, der
gratis ist). Optimierungs-Tipp im Daemon: Sekundäre Metrik nicht jede
Minute pollen, sondern nur z. B. alle 5 Minuten — dann sind es nur
~$1.30/Monat.

## Cross-Region / Cross-Account

- **Region ist Pflicht.** CloudWatch-Metriken und Service-Quotas sind
  regionsgebunden. Der Daemon muss eine Region kennen.
- **Inference Profiles (`us.anthropic...`, `eu.anthropic...`,
  `apac.anthropic...`, `global.anthropic...`)** publizieren ihre Metriken
  in der **Source-Region**, von der aus der Call ausging — nicht in der
  Destination-Region. Wer aus `us-east-1` ein `us.anthropic`-Profile
  aufruft, dessen Metriken stehen in CloudWatch von `us-east-1`. Damit ist
  unser Region-Setting eindeutig, solange der User nur aus einer Region
  ruft.
- **Multi-Region:** Wenn der User aus mehreren Source-Regionen Bedrock
  ruft, müssten wir mehrere Region-Clients aufbauen und summieren. Für MVP
  unterstützen wir genau **eine Region pro Provider-Eintrag**; Mehrfach-
  Regionen kann man als getrennte "Bedrock"-Provider-Einträge in der
  TOML-Config konfigurieren (z. B. `bedrock_us`, `bedrock_eu`).
- **Cross-Account:** out of scope für MVP. Wer in mehreren Accounts
  Bedrock nutzt, müsste mehrere Provider-Einträge mit unterschiedlichen
  `profile`-Namen anlegen.

## Empfehlung für Clawdmeter — kompletter boto3-Aufruf

Pseudocode für eine `poll_bedrock(cfg) -> dict` Funktion. Konkrete
Daemon-Integration kommt in einem separaten Issue.

```python
import boto3
import calendar
from datetime import datetime, timedelta, timezone

def poll_bedrock(cfg: dict) -> dict:
    """
    cfg: {
        "profile": "clawdmeter",
        "region":  "us-east-1",
        "models":  ["us.anthropic.claude-sonnet-4-5-v1:0"],
        "secondary": "monthly_tokens",  # or "burst_5m"
    }
    """
    session  = boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"])
    sq       = session.client("service-quotas")
    cw       = session.client("cloudwatch")
    model_id = cfg["models"][0]   # MVP: erstes Modell

    # 1) Quota-Codes (einmalig auflösen + cachen — hier inline der Klarheit halber)
    tpm_code, tpm_limit = _resolve_quota(sq, model_id, "tokens per minute")
    rpm_code, rpm_limit = _resolve_quota(sq, model_id, "requests per minute")

    # 2) Aktuelle Auslastung (letzte 60 s)
    now   = datetime.now(timezone.utc)
    start = now - timedelta(seconds=120)   # 2 buckets für Stabilität
    end   = now

    tpm_used, rpm_used = _get_current_usage(cw, model_id, start, end)
    tpm_pct = min(100, round(100 * tpm_used / tpm_limit)) if tpm_limit else 0
    rpm_pct = min(100, round(100 * rpm_used / rpm_limit)) if rpm_limit else 0

    # 3) Sekundäre Metrik
    if cfg["secondary"] == "monthly_tokens":
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        in_t, out_t = _get_token_totals(cw, model_id, month_start, now)
        r1, r2 = int(in_t), int(out_t)
        last_day = calendar.monthrange(now.year, now.month)[1]
        sec_to_month_end = int(
            (now.replace(day=last_day, hour=23, minute=59, second=59) - now).total_seconds()
        )
    else:  # "burst_5m"
        burst_start = now - timedelta(minutes=5)
        in_t, out_t = _get_token_totals(cw, model_id, burst_start, now)
        r1, r2 = int(in_t), int(out_t)
        sec_to_month_end = 0

    return {
        "p":  "bedrock",
        "n":  "Bedrock",
        "k":  "tpm_rpm",
        "m1": tpm_pct,
        "m2": rpm_pct,
        "r1": r1,
        "r2": sec_to_month_end,         # monthly-mode: seconds to month end
                                        # burst-mode:   0
        "st": "ok" if tpm_pct < 80 else "warn",
    }


def _resolve_quota(sq, model_id: str, kind: str) -> tuple[str, float]:
    """
    kind: 'tokens per minute' | 'requests per minute'
    Sucht den Quota nach Name; Codes sind nicht in den Docs.
    """
    family = _model_family(model_id)   # "Sonnet 4.5" aus "us.anthropic.claude-sonnet-4-5-v1:0"
    paginator = sq.get_paginator("list_service_quotas")
    for page in paginator.paginate(ServiceCode="bedrock"):
        for q in page["Quotas"]:
            name = q["QuotaName"]
            if ("On-demand" in name and kind in name and family in name):
                return q["QuotaCode"], q["Value"]
    raise RuntimeError(f"Quota for {model_id} / {kind} not found")


def _get_current_usage(cw, model_id, start, end) -> tuple[float, float]:
    r = cw.get_metric_data(
        StartTime=start, EndTime=end,
        ScanBy="TimestampDescending",
        MetricDataQueries=[
            {
                "Id": "tpm",
                "MetricStat": {
                    "Metric": {
                        "Namespace":  "AWS/Bedrock",
                        "MetricName": "EstimatedTPMQuotaUsage",
                        "Dimensions": [{"Name": "ModelId", "Value": model_id}],
                    },
                    "Period": 60, "Stat": "Sum",
                },
            },
            {
                "Id": "rpm",
                "MetricStat": {
                    "Metric": {
                        "Namespace":  "AWS/Bedrock",
                        "MetricName": "Invocations",
                        "Dimensions": [{"Name": "ModelId", "Value": model_id}],
                    },
                    "Period": 60, "Stat": "Sum",
                },
            },
        ],
    )
    tpm = (r["MetricDataResults"][0]["Values"] or [0])[0]
    rpm = (r["MetricDataResults"][1]["Values"] or [0])[0]
    return tpm, rpm


def _get_token_totals(cw, model_id, start, end) -> tuple[float, float]:
    # für Monatswerte sinnvoll: 3600-s-Period damit GetMetricData nicht zu teuer wird
    period = 3600 if (end - start).total_seconds() > 6 * 3600 else 60
    r = cw.get_metric_data(
        StartTime=start, EndTime=end,
        MetricDataQueries=[
            {
                "Id": "input",
                "MetricStat": {
                    "Metric": {"Namespace": "AWS/Bedrock",
                               "MetricName": "InputTokenCount",
                               "Dimensions": [{"Name": "ModelId", "Value": model_id}]},
                    "Period": period, "Stat": "Sum",
                },
            },
            {
                "Id": "output",
                "MetricStat": {
                    "Metric": {"Namespace": "AWS/Bedrock",
                               "MetricName": "OutputTokenCount",
                               "Dimensions": [{"Name": "ModelId", "Value": model_id}]},
                    "Period": period, "Stat": "Sum",
                },
            },
        ],
    )
    return sum(r["MetricDataResults"][0]["Values"]), sum(r["MetricDataResults"][1]["Values"])


def _model_family(model_id: str) -> str:
    # Robust per Tabelle. MVP: simple regex.
    # 'us.anthropic.claude-sonnet-4-5-v1:0' -> 'Sonnet 4.5'
    import re
    m = re.search(r"claude-(sonnet|haiku|opus)-(\d+)-(\d+)", model_id)
    if not m: return model_id
    return f"{m.group(1).title()} {m.group(2)}.{m.group(3)}"
```

## Offene Punkte

1. **Region-Default.** Wollen wir `us-east-1` als Default annehmen, wenn der
   User keine Region setzt, oder hart fehlschlagen? Empfehlung: hart
   fehlschlagen mit klarer Fehlermeldung — Region ist ein bewusster Setup-
   Schritt.
2. **Modell-Auswahl.** MVP unterstützt genau **ein** Modell pro
   Bedrock-Provider. Will der User mehrere Modelle aggregiert sehen,
   müssen wir die Quotas separat ziehen und die Auslastung getrennt
   anzeigen — oder eine "primary model"-Logik in der Config einführen.
3. **`_model_family`-Mapping.** Der Regex ist fragil; AWS könnte
   Inference-Profile-IDs anders benennen (z. B. `claude-sonnet-4` ohne
   Minor). Vor Release: Whitelist mit allen aktuell unterstützten
   Modell-IDs anlegen und Quota-Name-Mapping einmal manuell kuratieren.
4. **`get_foundation_model_availability`** als Pre-Flight-Check? Nice-to-
   have für eine "Bedrock-Zugang nicht freigeschaltet"-Fehlermeldung beim
   Daemon-Start.
5. **Throttle-Signalisierung.** Wenn `InvocationThrottles > 0`, könnten
   wir das im `st`-Feld anders flaggen (`"throttled"` statt `"warn"`).
   UX-Entscheidung offen.
6. **AWS-Pricing-Hinweis im Setup.** ~$2/Monat Polling-Kosten muss prominent
   in der README/Setup-Doku stehen — sonst gibt es Beschwerden.
7. **Quota-Code-Cache.** Quota-Codes sind pro Account+Region stabil; einmal
   beim Daemon-Start auflösen und in `~/.config/clawdmeter/bedrock-quotas.json`
   cachen. Cache invalidieren, wenn `list_service_quotas` einen neuen
   Quota-Namen findet, der zum Modell passt.

## Quellen

- [Monitoring the performance of Amazon Bedrock — AWS Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/monitoring.html)
- [How tokens are counted in Amazon Bedrock — AWS Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html)
- [Quotas for Amazon Bedrock — AWS Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas.html)
- [Amazon Bedrock endpoints and quotas — AWS General Reference](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)
- [Supported Regions and models for inference profiles — AWS Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html)
- [Improve operational visibility with TTFT and Estimated Quota Consumption metrics — AWS Blog](https://aws.amazon.com/blogs/machine-learning/improve-operational-visibility-for-inference-workloads-on-amazon-bedrock-with-new-cloudwatch-metrics-for-ttft-and-estimated-quota-consumption/)
- [TPM & RPM Quota Monitoring Dashboard for Amazon Bedrock — AWS re:Post](https://repost.aws/articles/ARfUsSkaWeSLiWZbv0OVSG1Q/tpm-rpm-quota-monitoring-dashboard-for-amazon-bedrock)
- [Amazon CloudWatch Pricing](https://aws.amazon.com/cloudwatch/pricing/)
- [CloudWatch Metrics Pricing Explained — Vantage](https://www.vantage.sh/blog/cloudwatch-metrics-pricing-explained-in-plain-english)

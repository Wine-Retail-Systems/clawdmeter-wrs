# CodexBar — Referenz-Analyse

Stand: 2026-05-24. Quelle: https://github.com/steipete/CodexBar (Commit-Stand vom 2026-05-24, 13k Stars, MIT-Lizenz, Swift 6, macOS 14+). Analysiert wurde gezielt: README, `VISION.md`, `AGENTS.md`, `docs/architecture.md`, `docs/providers.md`, `docs/provider.md`, `docs/refresh-loop.md`, `docs/ui.md`, `docs/codex.md`, `docs/claude.md`, `docs/bedrock.md`, `docs/opencode.md`, `docs/status.md`, `docs/widgets.md` und die zentralen Swift-Dateien `ProviderDescriptor.swift`, `ProviderFetchPlan.swift`, `UsageFetcher.swift` (Datenmodell), `UsagePace.swift`, `ProviderCostSnapshot.swift`, `CreditsModels.swift`, `UsageStore+Refresh.swift`. Komplette Code-Lesung wurde bewusst vermieden.

## Was ist CodexBar (1 Absatz)

CodexBar ist eine native macOS-Menüleisten-App (Swift 6, macOS 14+, AGPL-frei MIT-lizenziert) von Peter Steinberger, die Token- und Quota-Nutzung von aktuell **48 KI-Anbietern** in einem konsistenten UI bündelt. Der Anspruch ist ausdrücklich „Every AI coding limit, in your menu bar" — das Tool macht das Einloggen bei den Provider-Dashboards überflüssig, indem es lokale OAuth-Tokens, CLI-Aufrufe, Browser-Cookies und Logfile-Scans wiederverwendet. Architektonisch ist es ein deskriptor-getriebenes Plugin-System: Jeder Provider definiert seinen `ProviderDescriptor` mit Branding, Capabilities, einer geordneten Fallback-Kette von Fetch-Strategien (`oauth → cli → web → apiToken → localProbe → webDashboard`) — die Shared-UI-Schicht rendert dann generisch aus einem einheitlichen `UsageSnapshot`. Das ist konzeptionell exakt das Problem, das wir mit dem Clawdmeter-Daemon ebenfalls lösen müssen, nur dass CodexBar viel breiter und (noch) viel unfertiger ist als unser Plan.

## Provider & Metriken (Tabelle)

CodexBar registriert in `ProviderDescriptorRegistry.descriptorsByID` heute **48 Provider** (gezählt aus dem Code). Für den Clawdmeter-Scope relevant:

| Provider | Daten-Quelle | Primäre Fenster | Sekundär | Sonstiges |
|---|---|---|---|---|
| **Codex / OpenAI ChatGPT** | OAuth → CLI-RPC → Web (Cookies) | 5h-Window % | 7-Tage-Window % | Credits remaining, Account-Email, Plan |
| **Claude Code** | OAuth → CLI-PTY → Web | 5h-Session % | 7-Tage-Weekly % | Pro-Modell-Splits (Sonnet/Opus), Extra-Usage-Cost (USD), Admin-API für Org-Spend |
| **AWS Bedrock** | Cost-Explorer (`ce:GetCostAndUsage`) | Month-to-date USD | — | Vergleich gegen `CODEXBAR_BEDROCK_BUDGET`, Daily-Cost-Historie |
| **OpenCode** | Browser-Cookies → `opencode.ai/_server` POST | 5h `rollingUsage.usagePercent` | Weekly `weeklyUsage.usagePercent` | Reset = `now + resetInSec` |
| **OpenAI API** | API-Key | Tagesnutzung | Monatsnutzung | Cost in USD, pro-Modell-Breakdown |
| **Cursor** | Cookies | Plan-Quota % | On-Demand-Budget (USD) | Request-Count, Auto/API-Splits |
| **Copilot** | OAuth | Premium-Requests pro Monat | — | Reset-Datum |
| **OpenRouter** | API-Key | Credits remaining | Tagesnutzung | Per-Model-Breakdown |
| **Kimi** | Web/API | Weekly-Quota | 5h-Rate-Limit (300 min) | — |
| **T3 Chat** | Cookies | 4h Base-Bucket | Monthly Overage-Bucket | Zwei verschachtelte Fenster |
| **Mistral, DeepSeek, Grok, Gemini, …** | API-Key / OAuth | je provider-spezifisch | — | meist Credits + Tagesnutzung |

**Was pro Provider angezeigt wird (UI-Pattern):**
- `usedPercent` als Balken (oder als Restprozent — User-Toggle "Show remaining" vs. "Show used")
- Reset-Countdown (`Lasts until reset` oder `Runs out in 2h 14m`)
- Pace-Status: `On pace`, `8% in deficit`, `12% in reserve`
- Konto-Identität (Email, Plan, Org) — strikt **per Provider isoliert** (Identity-Silo, siehe AGENTS.md)
- Bei API-Providern: Credits remaining + Cost in USD
- Bei Bedrock: ausschließlich Cost-Bar (Spend vs. Budget)
- Optional: Status-Badge (Incident vom Statuspage-Feed)

Screenshots im Repo gibt es kaum (`docs/screenshots/` enthält nur eine Bug-Repro `claude-extra-usage-bug.png`); die Marketing-Site `codex.bar` ist die Hauptquelle. Beschreibung aus `docs/ui.md`: 18×18-Template-Bar als Menüleisten-Icon, beim Klick aufklappendes Popover mit „Provider-Tiles", jede Tile = Karte mit Primary/Secondary/Tertiary/Extra-Window-Sektion plus optionalem Cost-Chart, ein „Switcher" zeigt im Overview-Mode bis zu drei Provider-Zeilen gleichzeitig.

## Datenmodell (mit Code-Snippets aus dem Repo)

Die zentrale Erkenntnis: CodexBar **vereinheitlicht alle Provider auf genau eine Struktur**, `UsageSnapshot`. Das ist exakt das Pattern, das wir für unser BLE-JSON nachbauen wollen — nur kompakter wegen MTU-Limits. Wörtlich aus `Sources/CodexBarCore/UsageFetcher.swift`:

```swift
public struct RateWindow: Codable, Equatable, Sendable {
    public let usedPercent: Double
    public let windowMinutes: Int?
    public let resetsAt: Date?
    /// Optional textual reset description (used by Claude CLI UI scrape).
    public let resetDescription: String?
    /// Optional percent restored on the next regeneration tick for providers with rolling recovery.
    public let nextRegenPercent: Double?

    public var remainingPercent: Double { max(0, 100 - self.usedPercent) }

    public func backfillingResetTime(from cached: RateWindow?, now: Date = .init()) -> RateWindow {
        if self.resetsAt != nil { return self }
        guard let cachedReset = cached?.resetsAt, cachedReset > now else { return self }
        return RateWindow(
            usedPercent: self.usedPercent,
            windowMinutes: self.windowMinutes ?? cached?.windowMinutes,
            resetsAt: cachedReset,
            resetDescription: self.resetDescription ?? cached?.resetDescription,
            nextRegenPercent: self.nextRegenPercent)
    }
}

public struct NamedRateWindow: Codable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let window: RateWindow
}

public struct UsageSnapshot: Codable, Sendable {
    public let primary: RateWindow?
    public let secondary: RateWindow?
    public let tertiary: RateWindow?
    public let extraRateWindows: [NamedRateWindow]?
    public let providerCost: ProviderCostSnapshot?
    public let kiroUsage: KiroUsageDetails?
    public let zaiUsage: ZaiUsageSnapshot?
    public let minimaxUsage: MiniMaxUsageSnapshot?
    public let openRouterUsage: OpenRouterUsageSnapshot?
    public let openAIAPIUsage: OpenAIAPIUsageSnapshot?
    public let claudeAdminAPIUsage: ClaudeAdminAPIUsageSnapshot?
    public let mistralUsage: MistralUsageSnapshot?
    public let deepgramUsage: DeepgramUsageSnapshot?
    public let cursorRequests: CursorRequestUsage?
    public let updatedAt: Date
    public let identity: ProviderIdentitySnapshot?
    // ...
}
```

**Beobachtungen:**

1. **Drei feste Fenster-Slots + ein Array** für „Extra" — das ist eine pragmatische Mischung aus festem Schema (für schnelle UI-Zugriffe) und Erweiterbarkeit (für Sonderfälle wie T3 Chats Doppelbucket).
2. **`usedPercent` als kanonische Metrik.** Egal ob TPM, RPM, Tokens, Requests oder USD — am Ende rechnet jeder Provider auf einen Prozentsatz herunter. Das macht UI generisch.
3. **`windowMinutes` ist optional**, weil rollende Fenster (5h) und kalendarische Resets (Monatsende) beide unterstützt werden müssen. `resetsAt` ist die absolute Wahrheit; `windowMinutes` ist nur Metadatum für Pace-Berechnung.
4. **Kacheln-spezifische Sub-Snapshots** (`kiroUsage`, `zaiUsage`, `minimaxUsage`, `cursorRequests` etc.) sind ein **Anti-Pattern**, das wir vermeiden wollen — siehe unten.
5. **`backfillingResetTime`** ist ein cleveres Detail: Wenn der Provider mal kein `resetsAt` liefert, wird das letzte bekannte aus dem Cache wiederverwendet, solange es in der Zukunft liegt. Das verhindert hektisches UI-Flackern bei API-Hiccups.
6. **`ProviderIdentitySnapshot`** ist strikt provider-scoped — `scoped(to: provider)` und die Guardrail in `AGENTS.md` („never display identity/plan fields sourced from a different provider") sind explizit. Beim Clawdmeter spielt das weniger eine Rolle, weil wir keine Account-Identitäten auf dem ESP zeigen, aber für den Daemon-Code relevant.

Der **Provider-Descriptor** (`Sources/CodexBarCore/Providers/ProviderDescriptor.swift`, wörtlich):

```swift
public struct ProviderDescriptor: Sendable {
    public let id: UsageProvider
    public let metadata: ProviderMetadata
    public let branding: ProviderBranding
    public let tokenCost: ProviderTokenCostConfig
    public let fetchPlan: ProviderFetchPlan
    public let cli: ProviderCLIConfig
    // ...
    public func fetch(context: ProviderFetchContext) async throws -> ProviderFetchResult {
        let outcome = await self.fetchOutcome(context: context)
        return try outcome.result.get()
    }
}
```

Die **Fetch-Strategie-Kette** (`ProviderFetchPlan.swift`):

```swift
public enum ProviderFetchKind: Sendable {
    case cli, web, oauth, apiToken, localProbe, webDashboard
}

public protocol ProviderFetchStrategy: Sendable {
    var id: String { get }
    var kind: ProviderFetchKind { get }
    func isAvailable(_ context: ProviderFetchContext) async -> Bool
    func fetch(_ context: ProviderFetchContext) async throws -> ProviderFetchResult
    func shouldFallback(on error: Error, context: ProviderFetchContext) -> Bool
}

public struct ProviderFetchPipeline: Sendable {
    public func fetch(context: ..., provider: UsageProvider) async -> ProviderFetchOutcome {
        let strategies = await self.resolveStrategies(context)
        for strategy in strategies {
            let available = await strategy.isAvailable(context)
            guard available else { /* record skip */; continue }
            do {
                let result = try await strategy.fetch(context)
                return .success(result)
            } catch {
                // record failure, optionally fall back
            }
        }
    }
}
```

Das ist die Blaupause für unsere Daemon-Plugin-Schicht: **ein Provider = eine geordnete Liste von Quellen mit `isAvailable` + `fetch` + `shouldFallback`**. Wir können das fast 1:1 übernehmen.

**Cost-Snapshot** (`ProviderCostSnapshot.swift`, wörtlich):

```swift
public struct ProviderCostSnapshot: Equatable, Codable, Sendable {
    public let used: Double
    public let limit: Double
    public let currencyCode: String
    public let period: String?          // "Monthly" etc.
    public let resetsAt: Date?
    public let nextRegenAmount: Double?
    public let updatedAt: Date
}
```

— Drei Felder, die wir bisher **nicht** in unserem BLE-Schema haben: `currencyCode` (wir gehen implizit von EUR aus → schlecht für Bedrock USD), `period` (menschen-lesbares Label), `nextRegenAmount` (rolling recovery).

**Pace / Burn-Rate** (`UsagePace.swift`, gekürzt aber strukturell vollständig):

```swift
public struct UsagePace: Sendable {
    public enum Stage: Sendable {
        case onTrack, slightlyAhead, ahead, farAhead,
             slightlyBehind, behind, farBehind
    }
    public let stage: Stage
    public let deltaPercent: Double       // actual - expected
    public let expectedUsedPercent: Double // (elapsed / duration) * 100
    public let actualUsedPercent: Double
    public let etaSeconds: TimeInterval?   // bis Quota auf 0
    public let willLastToReset: Bool
    public let runOutProbability: Double?
}
```

Die Logik: Wenn elapsed/duration = 30% und usedPercent = 45%, ist `delta = +15%` → Stage `farAhead` → UI zeigt „⚠ 15% in deficit, runs out in 2h 14m". **Das haben wir bisher nicht** — wäre für Clawdmeter eine echte Aufwertung.

## Datenquellen pro Provider

CodexBar nutzt **vier Wege**, in dieser Präferenz-Reihenfolge:

1. **OAuth-Token aus Provider-CLI-Auth-Datei** — z.B. `~/.codex/auth.json`, `~/.claude/credentials.json`. Token wird zum direkten API-Call gegen `chatgpt.com/backend-api/wham/usage` o.ä. genutzt. Token-Refresh ab Alter 8 Tage.
2. **CLI-Subprozess (`codex -s read-only -a untrusted app-server`)**, dann JSON-RPC über stdio: `account/read`, `account/rateLimits/read`. Für Claude: PTY-Wrapper, weil Claude-CLI nur an TTYs ausgibt.
3. **Headless WebView mit importierten Browser-Cookies** (Safari/Chrome/Firefox). Lädt z.B. `chatgpt.com/codex/settings/usage` und scrapt das DOM. Cookies werden im Keychain gecached, Re-Import nur bei Failure.
4. **Lokale JSONL-Logs scannen** — `~/.codex/sessions/YYYY/MM/DD/*.jsonl`, `~/.pi/agent/sessions/**/*.jsonl`. Aus den geloggten Assistant-Turns werden Token-Counts (`input`, `cache_read`, `cache_create`, `output`) pro Modell summiert und mit Modell-Pricing in USD-Cost umgerechnet. Konfigurierbar: 1–365 Tage rollende Historie.

Für **Anthropic spezifisch**: Vier Quellen parallel — OAuth-API, CLI-PTY, Web-API, Admin-API (Org-Level-Spend). Reihenfolge je Runtime (App vs. CLI) unterschiedlich.

Für **Bedrock**: Reiner Cost-Explorer-Call, `ce:GetCostAndUsage`, nichts Spezielles. Erfordert IAM-Permission, Override über `CODEXBAR_BEDROCK_API_URL` für Tests.

Für **OpenCode**: Cookie-basierter POST gegen `https://opencode.ai/_server`, Response ist `text/javascript`-serialisiertes JS-Objekt, wird per Regex extrahiert (sic). Workspace-ID kann per `CODEXBAR_OPENCODE_WORKSPACE_ID` überschrieben werden — auch ein nützliches Pattern für unseren Daemon (ENV-Override für Edge-Cases).

## Reset-/Periodenlogik

**Drei Periodentypen** werden gleichberechtigt im selben Schema abgebildet:

1. **Rollendes Fenster** (z.B. 5h Session, 300-Minuten-Rate-Limit): `windowMinutes` gesetzt, `resetsAt` ist absolutes Zeitstempel, an dem das Fenster vollständig regeneriert.
2. **Kalender-Reset** (Wochenreset Mo 00:00, Monatsende): `windowMinutes = nil` oder `10080` (Default für `weekly`), `resetsAt` = nächster Reset-Termin laut Provider.
3. **Rolling Recovery** (selten — z.B. Anthropic Token-Bucket): `nextRegenPercent` zeigt, wieviel beim nächsten Tick zurückkommt. Erlaubt UI wie „in 5 min +3%".

**Backfilling:** Wenn ein Fetch kein `resetsAt` liefert (passiert bei manchen CLI-Scrapes), wird der letzte bekannte Reset aus `lastKnownResetSnapshots` übernommen, solange er noch in der Zukunft liegt. Verhindert UI-Sprünge.

**Pace-Berechnung** (oben gezeigt): erwarteter Verbrauch = `elapsed / windowDuration * 100`. Delta zum tatsächlichen → Stufeneinteilung in 7 Stages.

**Reset-Description als Fallback-String:** Bei Claude-CLI-Scrape ist das Reset-Datum oft nur als Text verfügbar („resets in 4h 12m"). Das wird als `resetDescription` zusätzlich gespeichert, falls `resetsAt` nicht parsebar war — ein Detail, das wir auch berücksichtigen sollten (nicht jeder Provider liefert saubere Timestamps).

## UI-Patterns (mit Screenshot-Beschreibungen)

Im Repo sind kaum Screenshots; ich beschreibe basierend auf `docs/ui.md` und `codex.bar`:

- **Menüleisten-Icon:** 18×18 Template-Image (monochrom, passt sich Dark/Light an). Zwei Modi:
  - „Critter Bar" (Default): vertikaler Balken im Icon, dessen Höhe % verbleibend visualisiert.
  - „Brand + Label": Provider-Logo + Prozent als Text rechts daneben.
  - Bei Fehler/Stale-Data: Icon dimmt aus (Opacity reduziert).
  - **Merge Icons:** Wenn mehrere Provider aktiv → entweder ein kombiniertes Icon (worst-case Provider gewinnt) oder pro Provider ein eigenes Status-Item nebeneinander.
- **Popover beim Click:** SwiftUI-Cards, eine pro Provider. Jede Card:
  - Header: Provider-Brand-Icon + Name + Account-Email (geblurrbar via `PersonalInfoRedactor`).
  - Primary-Bar: großer horizontaler Progress-Bar, Farbverlauf grün→gelb→rot je nach % oder Pace-Stage.
  - Secondary/Tertiary: kleinere Bars darunter mit Title-Label.
  - Reset-Zeile: „Resets in 3h 14m" oder „Lasts until reset" + Pace-Status.
  - Optional: Inline-Linechart (`InlineUsageDashboardContent.swift`) — Daily-Cost-Historie als Sparkline.
  - Cost-Sektion: bei API-Providern: „$12.34 used / $50.00 limit" + Sparkline.
  - Extra-Quotas: aufgeklappte Liste mit `NamedRateWindow`s.
- **Switcher-Overview** (wenn aktiv): nur Top-3-Provider-Zeilen, jeweils kompakt (Icon + Name + kleine Bar + %).
- **Provider-Status-Badge:** ⚠ wenn Incident-Feed Aktiv-Status meldet (Statuspage.io).
- **Notifications:** Toasts bei `quotaWarning`-State-Transitions („You're 80% through your 5h window").

**Farbcodierung pro Provider:** Branding wird über `ProviderBranding` definiert (eigenes Icon + Akzentfarbe). Im Popover trägt das Brand-Icon die Farbe, nicht das Layout selbst. Bars sind universal grün→gelb→rot, nicht provider-spezifisch.

**Konfetti-Overlay** (`ScreenConfettiOverlayController`) bei vollem Reset/Refill — netter Touch, eher Easter-Egg.

## Features, die wir noch nicht hatten

Liste der Features, die ich in CodexBar gefunden habe, die in unserem Plan-Stand fehlen oder unscharf sind:

1. **`UsagePace` / Burn-Rate-Stage-Klassifikation.** 7 Stufen (`onTrack`, `slightlyAhead/Behind`, `ahead/behind`, `farAhead/farBehind`). Wir hatten nur „velocity" als vage Idee. CodexBar zeigt das als deltaPercent zwischen erwartetem (linearer Verbrauch über Fensterlaufzeit) und tatsächlichem Verbrauch.
2. **`etaSeconds` / `willLastToReset` / `runOutProbability`.** Hochrechnung: „in 2h 14m bei aktueller Rate aufgebraucht" vs. „reicht bis Reset". Auf einem Display wäre das eine zweite kleine Zahl unter der Hauptmetrik.
3. **`nextRegenPercent` / `nextRegenAmount`.** Für rolling-recovery Provider (Token-Bucket-Modell) — zeigt „in 5 min +3% zurück". Wir hatten das gar nicht im Schema.
4. **`extraRateWindows` als variable Liste benannter Fenster.** Wir haben max 4 feste Slots (m1–m4). Für Provider wie T3 Chat (zwei Buckets) oder Deepgram (3 rollende Fenster) reicht das nicht.
5. **`currencyCode` explizit.** Wir hatten implizit EUR. Bedrock liefert USD, Mistral EUR, Provider-Mix → unbedingt mitschicken.
6. **`identity` (Account-Email, Org, Login-Method).** Brauchen wir auf dem ESP wahrscheinlich nicht, im Daemon aber für Logging/Multi-Account schon.
7. **Multi-Account / Token-Accounts pro Provider.** `tokenAccounts: [TokenAccount]` mit eigenen API-Keys. Erlaubt z.B. „Anthropic Personal" + „Anthropic Arbeit" parallel. Wir haben das nicht im Schema vorgesehen.
8. **Pro-Modell-Aufschlüsselung** (Sonnet vs. Opus 7d-Quota separat). Für die Detail-UI auf einem Touchscreen denkbar; auf BLE sicher nicht alles, aber ein Provider könnte „dominant model" als String mitschicken (`note` haben wir ja schon).
9. **Cache-Hit-Tokens.** Im JSONL-Scan trackt CodexBar `cache_read` und `cache_create` separat — nützlich für Cost-Sparen. Im Display wäre eine kleine „Cache: 73%"-Anzeige cool.
10. **Status-Polling (Incident-Detection).** Statuspage.io API als zweite Datenquelle. Bei Anthropic-Outage zeigt das Icon ein ⚠. Auf dem ESP wäre das ein simpler Status-Badge im UI.
11. **Quota-Warning-Notifications mit Hysterese.** `handleQuotaWarningTransitions` + `lastKnownSessionRemaining` — verhindert, dass bei 79.9% ↔ 80.1% ständig Notifications feuern. Pattern sollten wir auf BLE-Push-Notifications anwenden.
12. **`failureGates` / Error-Resilience.** Per-Provider Failure-Counter mit Cooldown. Nach N Fails geht der Provider in Backoff statt jedes Mal neu zu hämmern.
13. **`sourceLabel` + `strategyID` als Provenance-Info.** Beim Fetch wird gespeichert, welche Strategie geliefert hat („OAuth API", „CLI v0.34.1"). Für Debugging auf dem ESP nicht nötig, im Daemon-Log sehr.
14. **Konfigurierbarer `costUsageHistoryDays` 1–365.** Mit `max(1, min(365, …))`-Clamping. Sauberes Input-Validation-Pattern.
15. **Bedrock-spezifisch: `CODEXBAR_BEDROCK_BUDGET` ENV.** Budget-Übersteuerung pro Provider via ENV. Genau das, was wir uns für `budget_eur` im k=`budget_eur`-Modus überlegt hatten — aber als Per-Provider-ENV explizit dokumentiert.
16. **WidgetKit-Snapshot** als separater compact-JSON-Container im AppGroup-Storage. Für ein zweites Display (Watch?) ist das praktisch — für uns: BLE-Payload **ist** der WidgetSnapshot, das Schema sollte also explizit für „compact JSON für constrained renderer" optimiert sein.
17. **CLI-Variante (`codexbar`)** als Headless-Binary. Nützliche Idee: unser Daemon könnte einen `clawdmeter status`-Befehl bieten, der dasselbe JSON ausgibt, das er per BLE schickt. Erleichtert Debugging massiv.

## Polling-Strategie

Aus `docs/refresh-loop.md` + `UsageStore+Refresh.swift`:

- **Globale Refresh-Cadence:** User-konfigurierbar als `Manual | 1m | 2m | 5m (Default) | 15m | 30m`. Gespeichert in `UserDefaults` über `SettingsStore`.
- **Kein per-Provider-Interval** — alle Provider werden bei jedem Tick parallel angefragt.
- **Async parallel via `TaskGroup`** — kein Round-Robin, kein Batching, jeder Provider eigener Task.
- **Pro-Provider FailureGate** (`failureGates[provider]`) — implementiert Cooldown nach N Fails. Details nicht voll im Code, aber das Pattern ist da.
- **Manueller Refresh** ignoriert FailureGates und feuert sofort.
- **Status-Polling separat:** Statuspage.io-Endpoints werden mit eigener (vermutlich seltenerer) Frequenz gepollt, nicht Teil des Usage-Refresh-Cycles.
- **Storage-Scans (JSONL-Logs) sind „opt-in throttled":** Werden bei Auto-Refresh seltener ausgeführt als bei Manual-Refresh, weil teuer.
- **Optimistische Snapshot-Übernahme:** Bei Success → sofortiger State-Update + `backfillingResetTimes`. Bei Failure → letzter bekannter Snapshot bleibt sichtbar, nur `errors[provider]` wird gesetzt.

**Was fehlt:** Explizites Exponential-Backoff, Retry-Headers (z.B. `Retry-After`-Auswertung), kein Provider-priorisiertes Scheduling. Das wirkt simpel — könnten wir besser machen.

## Schwächen / Lücken

Was CodexBar nicht so gut macht oder fehlt:

1. **Nur ein einziger globaler Refresh-Interval.** Bedrock-Cost-Explorer braucht keine 5-Minuten-Polls (Daten aktualisieren sich AWS-seitig stündlich), Claude-5h-Window dagegen schon. Eine **pro-Provider-Mindest-TTL** wäre überfällig.
2. **Kein echtes Backoff bei Rate-Limit-Responses.** `failureGates` ist eher ein Failure-Counter als ein RFC-konformes `Retry-After`-Honoring.
3. **Provider-spezifische Sub-Snapshots im Datenmodell** (`kiroUsage`, `zaiUsage`, `cursorRequests` etc.) verletzen das eigene Vereinheitlichungs-Ziel. Wird offensichtlich aufgenommen, wenn ein Provider Felder hat, die nicht in `RateWindow` passen. Konsequenz: `UsageSnapshot` ist heute eine Mischung aus generischem Kern + 8 Sonderfällen. Das skaliert nicht — mit dem 50. Provider kommen wieder neue Felder dazu.
4. **Identity-Silo wird durch Code-Review erzwungen, nicht durch Typensystem.** Wenn `accountEmail(for: provider)` mal vergessen wird, leakt Account-Info. Eine `ProviderScoped<Identity>`-Wrapper-Generic wäre robuster.
5. **WebView-Cookie-Scraping als „erste-Klasse"-Strategie** ist fragil (DOM ändert sich beim Provider-Redesign) und privacy-rechtlich grenzwertig (Lesen aus Safari/Chrome/Firefox-Cookie-DBs). Wir wollen das in unserem Daemon eher als letzten Notnagel, nicht als Default.
6. **Kein Multi-Region/Multi-Endpoint** für Bedrock — `us-east-1` ist Default, andere Regionen nur via env. Für EU-User mit `eu-central-1`-only Bedrock ist das schmerzhaft.
7. **Kein Local-Inference-Backend** (Ollama wird zwar gelistet, aber nur als Modell-Auswahl, nicht als Usage-Provider mit Quota — gibt's bei Ollama ja auch nicht).
8. **macOS-only.** Linux-Tests gibt es (`TestsLinux/`), aber kein Linux-UI. Headless-CLI funktioniert. Für unser Daemon-auf-Linux-Setup ist das eigentlich neutral — wir bauen ja sowieso ein anderes Frontend.
9. **Kein historisches Cost-Charting für alle Provider.** Daily-Buckets gibt's bei Bedrock + Claude + Codex; bei kleineren Providern fehlt das. Wir können das umgehen, weil wir keine Charts auf dem ESP rendern wollen — aber Daemon-seitig wäre eine TimescaleDB/SQLite-Historie nett.
10. **Kein Forecasting jenseits naiver linearer Hochrechnung.** `etaSeconds = remaining / rate` mit `rate = actual/elapsed` ist die Total-Trivial-Variante. Eine EMA-geglättete Burn-Rate (Tageszeit-Berücksichtigung: nachts wird weniger getippt) wäre genauer.
11. **Reset-Description ist Strings statt strukturiert.** „resets in 4h 12m" wird gespeichert, aber nicht später parsiert. Wenn `resetsAt` fehlt, kann das UI nur den String 1:1 anzeigen — keine Countdown-Animation möglich.
12. **Kein End-of-Cycle-Marker im Snapshot.** CodexBar überschreibt einfach immer den ganzen `snapshots[provider]`-Dict-Eintrag. Wenn der Daemon einen Provider entfernt hat, weiß die UI das nur durch Abwesenheit. Bei uns mit sequentiellen BLE-Payloads ist das ein Problem, das wir mit End-of-Cycle-Marker bewusst gelöst haben — das ist **besser** als bei CodexBar.

## Empfohlene Inspirationen für Clawdmeter (priorisiert)

In Reihenfolge des Mehrwerts. Jede Empfehlung mit konkretem Schema-Vorschlag.

### 1. Burn-Rate / Pace-Stage in Schema aufnehmen (HOCH)

CodexBar's `UsagePace.stage`-Klassifikation als kompaktes Feld ergänzen. Auf dem 480×480 AMOLED ist eine kleine Icon-Reihe oder Farbcodierung (grün/gelb/rot/rot-pulsierend) viel ausdrucksstärker als nackte %-Zahlen.

**Schema-Erweiterung:**
```json
{
  "p":"claude-pro","n":"Claude",
  "k":"pct_window",
  "m1":67.0, "m2":...,
  "pace":-8.5,           // delta vs. expected (-12..+12), >0 = ahead = bad
  "eta":7800,            // seconds bis 0% oder null wenn willLastToReset
  "regen":3.0,           // optional nextRegenPercent
  ...
}
```

Ein einzelnes `pace`-Feld (Double, kann –20..+20 sein) reicht; UI bucketed selbst in 7 Stufen.

### 2. `currencyCode` + `period` zu Cost-Mode ergänzen (HOCH, einfach)

Heute haben wir `k=budget_eur` mit implizitem EUR. Das bricht für Bedrock USD. **Schema-Fix:**
```json
{"k":"budget","cur":"USD","period":"monthly","m1":12.34,"m2":50.00,...}
```
oder einfacher: `"k":"budget_usd"` / `"k":"budget_eur"` als getrennte Modes. Variante mit `cur`-Feld ist flexibler.

### 3. `extraRateWindows` für 3+-Bucket-Provider (MITTEL)

Für T3 Chat / Deepgram / Kimi mit drei oder mehr Fenstern reicht unser m1–m4 nicht. Vorschlag: zusätzlich zu den 4 festen Slots optional ein kompaktes Array:
```json
{
  "p":"deepgram","n":"Deepgram",
  "m1":42.0,                   // primary
  "ex":[
    {"t":"Daily","u":12.5,"r":3600},
    {"t":"Monthly","u":67.0,"r":1296000}
  ]
}
```
MTU-mäßig riskant — bei mehr als 2 Extra-Windows lieber einen zweiten BLE-Frame schicken.

### 4. Provider-Status-Badge (Incident-Detection) (MITTEL)

Statuspage.io-Polling als zweite Datenquelle. Für Anthropic, OpenAI, Cursor gibt's offizielle Statuspages. Im Schema:
```json
{"st":"incident", "incident":"degraded performance"}
```
Wir haben schon `st: "ok"|"error"|"stale"` — einfach um `"incident"` ergänzen, optional ein 32-Zeichen-`incident`-String. Daemon pollt Statuspage 1×/min separat vom Provider-Refresh.

### 5. Pro-Provider Refresh-Cadence + Backoff (MITTEL)

Statt globalem 5-Minuten-Polling: jeder Provider deklariert in seinem Plugin eine `minPollInterval`. Bedrock = 30min (Cost-Explorer ist eh stündlich), Anthropic = 5min, OpenCode = 2min. Plus Exponential-Backoff bei Failures (CodexBar hat das nicht — wir können hier besser sein). Das ändert das BLE-Schema nicht, nur die Daemon-Architektur.

### 6. `sourceLabel` / `note` ausnutzen (LOW, kostenfrei)

CodexBar setzt bei jedem Fetch `sourceLabel: "OAuth API"` oder `"CLI v0.34.1"`. Wir haben schon `note` im Schema — den können wir nutzen, um dort z.B. „via OAuth", „Cached", „Stale 4min" reinzuschreiben. UI zeigt das in 12pt-Schrift unter dem Provider-Namen.

### 7. Failure-Hysterese für `st` (LOW)

Nicht jeder einzelne Fail soll Provider-Status auf „error" kippen. Erst nach N=3 Fails in Folge — sonst flickert die UI. Das ist eine reine Daemon-Logik, kein Schema-Change.

### 8. CLI-Echo des Daemon-Outputs (LOW, später)

Wie `codexbar status` — `clawdmeter status --json` gibt exakt das aus, was per BLE geht. Massiv hilfreich für Debugging ohne ESP. Reiner Daemon-Komfort.

## Anti-Patterns / nicht übernehmen

1. **Provider-spezifische Sub-Snapshots** (`kiroUsage`, `cursorRequests`, …) im Hauptdatenmodell. Wir wollen **strikt** nur generische Felder im BLE-Schema. Für Provider-Spezifika gibt's `note` (Freitext) — alles andere geht über `extraRateWindows` (typisiert) oder gar nicht.
2. **Identity im Snapshot mitschicken.** CodexBar trägt `accountEmail` durch alle Schichten, mit Identity-Silo-Guardrails. Auf dem ESP ist das überflüssig (kein Multi-Account-UI), im Daemon-Log reicht's. **Nicht** über BLE schicken.
3. **WebView-Cookie-Scraping als Default-Strategie.** Fragil und privacy-grenzwertig. Bei uns nur als allerletzte Fallback-Option, klar dokumentiert und opt-in.
4. **Globaler Refresh-Interval ohne Per-Provider-Override.** CodexBar pollt alle Provider gleich oft — wir machen das besser (siehe Empfehlung 5).
5. **`resetDescription` als String-Fallback.** Wenn der Daemon kein `resetsAt` parsen kann, sollten wir den Provider als `st: "stale"` markieren statt einen unparsbaren String durchzuschleifen. Auf einem 480×480-Display ist „resets in 4h 12m"-Plaintext keine echte Option — wir wollen Countdown-Animation.
6. **Konfetti-Overlay / Easter-Eggs im MVP.** CodexBar hat `ScreenConfettiOverlayController` — wir bleiben erstmal beim Wein-Glas-Spinner.
7. **Drei feste Fenster-Slots in Stein meißeln.** CodexBar hat `primary/secondary/tertiary` als Felder, was unflexibel ist. Wir nutzen lieber die generische `m1..m4` + optional `ex[]`-Liste — typenflexibler, klarer dokumentierbar.
8. **Provider-Sub-Snapshots als optional Codable-Property im Hauptstruct.** Sorgt für Wachstums-Bloat (siehe oben). Wenn ein Provider exotische Felder braucht, gehört das in ein eigenes BLE-Subschema oder in `note`.

## Quellen

Alle URLs sind raw.githubusercontent.com-Pfade auf `main` (Stand 2026-05-24):

- Repo-Übersicht: https://github.com/steipete/CodexBar
- Marketing: https://codex.bar
- VISION.md: https://raw.githubusercontent.com/steipete/CodexBar/main/VISION.md
- AGENTS.md: https://raw.githubusercontent.com/steipete/CodexBar/main/AGENTS.md
- README.md: https://raw.githubusercontent.com/steipete/CodexBar/main/README.md
- docs/architecture.md
- docs/providers.md (47-Provider-Liste mit Auth-Methoden)
- docs/provider.md (Authoring-Guide für neue Provider)
- docs/refresh-loop.md
- docs/ui.md
- docs/codex.md (OpenAI/Codex-Integration)
- docs/claude.md (Anthropic-Integration)
- docs/bedrock.md (AWS Bedrock)
- docs/opencode.md
- docs/status.md (Incident-Detection)
- docs/widgets.md (WidgetKit-Snapshot-Schema)

Swift-Quellcode:
- `Sources/CodexBarCore/UsageFetcher.swift` (UsageSnapshot, RateWindow, NamedRateWindow, ProviderIdentitySnapshot)
- `Sources/CodexBarCore/Providers/ProviderDescriptor.swift` (Descriptor + Registry mit 48 Providern)
- `Sources/CodexBarCore/Providers/ProviderFetchPlan.swift` (ProviderFetchStrategy-Protocol + Pipeline)
- `Sources/CodexBarCore/UsagePace.swift` (Burn-Rate-Stage-Klassifikation)
- `Sources/CodexBarCore/ProviderCostSnapshot.swift` (USD/EUR-Cost-Modell)
- `Sources/CodexBarCore/CreditsModels.swift` (CreditEvent + CreditsSnapshot)
- `Sources/CodexBar/UsageStore+Refresh.swift` (Refresh-Loop mit FailureGate + Backfill)

Code-Statistik: Repo-Größe 89 MB, 1.044 Forks, 13.254 Stars, 21 offene Issues. Swift 6 strict-concurrency. macOS 14+ erforderlich.

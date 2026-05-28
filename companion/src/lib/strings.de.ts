// Zentralisierte deutsche UI-Strings. EN/weitere Sprachen später nachrüstbar
// indem dieses Modul gegen ein i18n-Setup ausgetauscht wird.

export const STRINGS = {
  appTitle: "Clawdmeter",
  appTagline: "Companion-App für Onboarding, Flashen und Daemon-Lifecycle.",

  landing: {
    heading: "Was möchtest du tun?",
    flashCta: "Gerät einrichten",
    flashHelp: "Firmware auf ein neues Clawdmeter flashen.",
    setupCta: "Provider konfigurieren",
    setupHelp: "Anthropic, Bedrock, Codex, Langdock oder OpenCode hinzufügen.",
    pairCta: "Gerät koppeln",
    pairHelp: "Bluetooth-Discovery starten und mit dem System koppeln.",
    statusCta: "Status & Logs",
    statusHelp: "Daemon-Status prüfen, Live-Logs sehen, Fehler melden.",
  },

  daemon: {
    running: "Daemon läuft",
    stopped: "Daemon gestoppt",
    unknown: "Status unbekannt",
    error: "Daemon nicht erreichbar",
    notInstalled: "Daemon nicht installiert",
    installAction: "Daemon installieren",
    installing: "Installiere Daemon …",
    legacyHeading: "Älterer Daemon erkannt",
    legacyBody:
      "Auf diesem Mac läuft noch ein älterer Clawdmeter-Daemon. Die Companion-App kann ihn übernehmen: Sie entfernt die alte launchd-Registrierung und richtet den aktuellen Daemon ein. Deine Provider-Konfiguration unter ~/.config/clawdmeter bleibt unverändert.",
    legacyAction: "Alten Daemon übernehmen",
    legacyMigrating: "Migriere …",
    legacyDone: "Migration abgeschlossen.",
    legacyError: "Migration fehlgeschlagen",
  },

  flash: {
    title: "Firmware flashen",
    stepBoard: "Board wählen",
    stepPort: "USB-Port wählen",
    stepFlash: "Flashen",
    boardWine: "Wine Edition (2.16″) — empfohlen",
    boardStandard216: "Standard (2.16″)",
    boardStandard180: "Standard (1.8″)",
    refreshPorts: "Ports neu suchen",
    startFlash: "Flashen starten",
    flashing: "Flashe …",
    flashOk: "Fertig — Gerät kann jetzt gekoppelt werden.",
    flashError: "Flashen fehlgeschlagen",
  },

  setup: {
    title: "Provider einrichten",
    intro:
      "Wähle eine oder mehrere LLM-Quellen. Du kannst diese später jederzeit ändern.",
    providers: {
      anthropic: "Anthropic (Claude)",
      bedrock: "AWS Bedrock",
      codex: "Codex (OpenAI)",
      langdock: "Langdock",
      opencode: "OpenCode",
    },
    next: "Weiter",
    back: "Zurück",
    save: "Speichern",
    skip: "Überspringen",
    detecting: "Erkenne vorhandene Anmeldedaten …",
    detected: "Anmeldedaten erkannt",
    notDetected: "Keine Anmeldedaten gefunden",
    langdock: {
      apiKeyLabel: "Langdock API-Key",
      apiKeyPlaceholder: "lk_…",
      apiKeyHelp:
        "Bekommst du in app.langdock.com → Settings → API Keys (Admin-Rolle nötig).",
      apiKeyExists: "Aktuell hinterlegt:",
      apiKeyKeep: "Leer lassen, um den vorhandenen Wert zu behalten.",
      emailLabel: "Deine Workspace-E-Mail (optional)",
      emailPlaceholder: "you@firma.de",
      emailHelp:
        "Filtert die Aktivitätsanzeige auf einen User. Ohne Eintrag summiert der Slot alle Workspace-Mitglieder.",
      saved: "Gespeichert",
      saveError: "Speichern fehlgeschlagen",
    },
  },

  pair: {
    title: "Gerät koppeln",
    scanning: "Suche nach Clawdmeter …",
    foundNone: "Kein Gerät gefunden. Stelle sicher, dass es eingeschaltet ist.",
    rescan: "Erneut suchen",
    helpHeading: "Kopplung im Betriebssystem",
    helpBody:
      "Tauri kann das eigentliche Pairing nicht übernehmen. Öffne die Bluetooth-Einstellungen und klicke neben „Clawdmeter“ auf „Verbinden“. Der Daemon erkennt das Gerät automatisch.",
  },

  status: {
    title: "Status & Logs",
    daemonHeading: "Daemon",
    logsHeading: "Live-Logs",
    bugReport: "Fehler melden",
    bugReportHelp:
      "Sammelt anonymisierte Logs der letzten 5 Minuten und öffnet einen vorausgefüllten Issue-Entwurf.",
    restart: "Neustart",
    stop: "Stoppen",
    start: "Starten",
  },

  errors: {
    daemonUnavailable:
      "Der Daemon ist nicht erreichbar. Wurde er beim ersten Start installiert?",
    flashNoPort: "Bitte zuerst einen USB-Port auswählen.",
  },
} as const;

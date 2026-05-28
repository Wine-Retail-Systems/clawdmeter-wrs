import { useEffect, useState } from "react";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { Landing } from "./routes/Landing";
import { FlashWizard } from "./routes/flash/FlashWizard";
import { SetupWizard } from "./routes/setup/SetupWizard";
import { PairScreen } from "./routes/pair/PairScreen";
import { StatusScreen } from "./routes/status/StatusScreen";
import { getDaemonStatus, DaemonStatus } from "./lib/ipc";
import { applyOsAttribute } from "./lib/platform";
import { STRINGS } from "./lib/strings.de";
import { IconWine } from "./components/Icon";

export type Route = "landing" | "flash" | "setup" | "pair" | "status";

export function App() {
  const [route, setRoute] = useState<Route>("landing");
  const [status, setStatus] = useState<DaemonStatus | null>(null);

  useEffect(() => {
    applyOsAttribute();
  }, []);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await getDaemonStatus();
        if (alive) setStatus(s);
      } catch {
        if (alive) setStatus(null);
      }
    };
    tick();
    const id = setInterval(tick, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // Update-Check beim Start. Findet das Plugin ein Update, lädt es im
  // Hintergrund und startet die App nach der Bestätigung neu.
  useEffect(() => {
    (async () => {
      try {
        const update = await check();
        if (!update) return;
        const ok = window.confirm(
          `Neue Version ${update.version} verfügbar. Jetzt installieren?\n\n${update.body ?? ""}`,
        );
        if (!ok) return;
        await update.downloadAndInstall();
        await relaunch();
      } catch {
        // Kein Internet / kein Updater konfiguriert — silent.
      }
    })();
  }, []);

  return (
    <div className="app">
      <div className="titlebar" />

      <header className="app__header">
        <button
          type="button"
          className="brand brand--button"
          onClick={() => setRoute("landing")}
          aria-label="Zur Startseite"
        >
          <span className="brand__mark" aria-hidden="true">
            <IconWine size={20} />
          </span>
          <span className="brand__text">
            <span className="brand__name">{STRINGS.appTitle}</span>
            <span className="brand__sub">Wine Edition · Companion</span>
          </span>
        </button>

        <DaemonStatusChip status={status} />
      </header>

      <main className="app__main">
        {route === "landing" && (
          <Landing status={status} onNavigate={setRoute} />
        )}
        {route === "flash" && (
          <FlashWizard onDone={() => setRoute("landing")} />
        )}
        {route === "setup" && (
          <SetupWizard onDone={() => setRoute("landing")} />
        )}
        {route === "pair" && <PairScreen onDone={() => setRoute("landing")} />}
        {route === "status" && (
          <StatusScreen status={status} onDone={() => setRoute("landing")} />
        )}
      </main>

      <footer className="app__footer">
        Build with <span className="heart" aria-hidden="true">❤</span> &amp; KI
        in Düsseldorf by{" "}
        <a href="mailto:sascha@krinke.me">Sascha</a>
      </footer>
    </div>
  );
}

function DaemonStatusChip({ status }: { status: DaemonStatus | null }) {
  if (!status) {
    return (
      <span className="statuschip">
        <span className="status-dot status-dot--unknown" />
        {STRINGS.daemon.unknown}
      </span>
    );
  }
  if (!status.installed) {
    return (
      <span className="statuschip">
        <span className="status-dot status-dot--warn" />
        {STRINGS.daemon.notInstalled}
      </span>
    );
  }
  if (!status.reachable) {
    return (
      <span className="statuschip">
        <span className="status-dot status-dot--error" />
        {STRINGS.daemon.error}
      </span>
    );
  }
  if (!status.running) {
    return (
      <span className="statuschip">
        <span className="status-dot status-dot--warn" />
        {STRINGS.daemon.stopped}
      </span>
    );
  }
  return (
    <span className="statuschip">
      <span className="status-dot status-dot--ok status-dot--pulse" />
      <strong>{STRINGS.daemon.running}</strong>
    </span>
  );
}

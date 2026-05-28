import { useEffect, useState } from "react";
import { check } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";
import { Landing } from "./routes/Landing";
import { FlashWizard } from "./routes/flash/FlashWizard";
import { SetupWizard } from "./routes/setup/SetupWizard";
import { PairScreen } from "./routes/pair/PairScreen";
import { StatusScreen } from "./routes/status/StatusScreen";
import { getDaemonStatus, DaemonStatus } from "./lib/ipc";
import { STRINGS } from "./lib/strings.de";

export type Route = "landing" | "flash" | "setup" | "pair" | "status";

export function App() {
  const [route, setRoute] = useState<Route>("landing");
  const [status, setStatus] = useState<DaemonStatus | null>(null);

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
      <header className="app__hero">
        <h1>{STRINGS.appTitle}</h1>
        <p>{STRINGS.appTagline}</p>
      </header>

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
    </div>
  );
}

import { useEffect, useState } from "react";
import { open } from "@tauri-apps/plugin-shell";
import {
  DaemonStatus,
  collectCrashBundle,
  restartDaemon,
  startDaemon,
  stopDaemon,
  tailDaemonLogs,
} from "../../lib/ipc";
import { STRINGS } from "../../lib/strings.de";
import { IconArrowLeft, IconRefresh } from "../../components/Icon";

type Props = {
  status: DaemonStatus | null;
  onDone: () => void;
};

export function StatusScreen({ status, onDone }: Props) {
  const [logs, setLogs] = useState<string[]>([]);
  const [bundlePath, setBundlePath] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const l = await tailDaemonLogs(80);
        if (alive) setLogs(l);
      } catch {
        // Daemon nicht erreichbar — silently ignore, App-Status reicht
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  async function onBugReport() {
    const bundle = await collectCrashBundle();
    setBundlePath(bundle);
    const subject = encodeURIComponent("Clawdmeter Bug-Report");
    const body = encodeURIComponent(
      `Bitte beschreibe kurz, was passiert ist.\n\nAnhang (bitte beifügen):\n${bundle}\n`,
    );
    try {
      await open(`mailto:sascha@krinke.me?subject=${subject}&body=${body}`);
    } catch {
      // Mail-Client nicht verfügbar — Pfad bleibt im UI sichtbar.
    }
  }

  const stateText = status?.running
    ? STRINGS.daemon.running
    : status?.reachable
      ? STRINGS.daemon.stopped
      : STRINGS.daemon.unknown;
  const dotClass = status?.running
    ? "status-dot--ok status-dot--pulse"
    : status?.reachable
      ? "status-dot--warn"
      : "status-dot--unknown";

  return (
    <>
      <div className="subheader">
        <button
          type="button"
          className="subheader__back"
          onClick={onDone}
        >
          <IconArrowLeft size={14} /> Zurück
        </button>
      </div>

      <header className="page-heading">
        <h2>{STRINGS.status.title}</h2>
        <p>Daemon-Lifecycle und Diagnose.</p>
      </header>

      <div className="card">
        <p className="card__label">{STRINGS.status.daemonHeading}</p>
        <h3 className="card__heading">
          <span className={`status-dot ${dotClass}`} />
          {stateText}
        </h3>
        <div className="button-row">
          <button type="button" className="cta cta--ghost" onClick={startDaemon}>
            {STRINGS.status.start}
          </button>
          <button type="button" className="cta cta--ghost" onClick={stopDaemon}>
            {STRINGS.status.stop}
          </button>
          <button type="button" className="cta cta--ghost" onClick={restartDaemon}>
            <IconRefresh size={14} /> {STRINGS.status.restart}
          </button>
        </div>
      </div>

      <div className="card">
        <p className="card__label">{STRINGS.status.logsHeading}</p>
        <h3 className="card__heading">Live-Ausgabe</h3>
        <pre className="logview">
          {logs.join("\n") || "(keine Logs)"}
        </pre>
      </div>

      <div className="card">
        <p className="card__label">Diagnose</p>
        <h3 className="card__heading">{STRINGS.status.bugReport}</h3>
        <p className="card__body">{STRINGS.status.bugReportHelp}</p>
        <div className="button-row">
          <button type="button" className="cta" onClick={onBugReport}>
            {STRINGS.status.bugReport}
          </button>
        </div>
        {bundlePath && (
          <p className="card__hint-mono">{bundlePath}</p>
        )}
      </div>
    </>
  );
}

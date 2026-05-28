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

  return (
    <main>
      <h2>{STRINGS.status.title}</h2>

      <div className="card">
        <strong>{STRINGS.status.daemonHeading}</strong>
        <p>
          {status?.running
            ? STRINGS.daemon.running
            : status?.reachable
              ? STRINGS.daemon.stopped
              : STRINGS.daemon.unknown}
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="cta cta--ghost" onClick={startDaemon}>
            {STRINGS.status.start}
          </button>
          <button className="cta cta--ghost" onClick={stopDaemon}>
            {STRINGS.status.stop}
          </button>
          <button className="cta cta--ghost" onClick={restartDaemon}>
            {STRINGS.status.restart}
          </button>
        </div>
      </div>

      <div className="card">
        <strong>{STRINGS.status.logsHeading}</strong>
        <pre
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: 12,
            maxHeight: 320,
            overflow: "auto",
            fontSize: 12,
            lineHeight: 1.4,
            margin: 0,
          }}
        >
          {logs.join("\n") || "(keine Logs)"}
        </pre>
      </div>

      <div className="card">
        <strong>{STRINGS.status.bugReport}</strong>
        <p style={{ color: "var(--fg-muted)" }}>
          {STRINGS.status.bugReportHelp}
        </p>
        <button className="cta cta--ghost" onClick={onBugReport}>
          {STRINGS.status.bugReport}
        </button>
        {bundlePath && (
          <small style={{ color: "var(--fg-muted)" }}>
            Bundle gespeichert: <code>{bundlePath}</code>
          </small>
        )}
      </div>

      <button className="cta" onClick={onDone}>
        Fertig
      </button>
    </main>
  );
}

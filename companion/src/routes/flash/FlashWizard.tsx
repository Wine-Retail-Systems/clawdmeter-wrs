import { useEffect, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import {
  BoardId,
  FlashProgress,
  SerialPort,
  flashFirmware,
  listSerialPorts,
} from "../../lib/ipc";
import { STRINGS } from "../../lib/strings.de";

type Props = { onDone: () => void };
type Step = "board" | "port" | "flash";

export function FlashWizard({ onDone }: Props) {
  const [step, setStep] = useState<Step>("board");
  const [board, setBoard] = useState<BoardId>("wine-216");
  const [ports, setPorts] = useState<SerialPort[]>([]);
  const [selectedPort, setSelectedPort] = useState<string | null>(null);
  const [flashing, setFlashing] = useState(false);
  const [progress, setProgress] = useState<FlashProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (step === "port") refreshPorts();
  }, [step]);

  useEffect(() => {
    const unlistenPromise = listen<FlashProgress>("flash-progress", (e) => {
      setProgress(e.payload);
      if (e.payload.phase === "done") setDone(true);
      if (e.payload.phase === "error") {
        setError(e.payload.message ?? STRINGS.flash.flashError);
      }
    });
    return () => {
      unlistenPromise.then((unlisten) => unlisten());
    };
  }, []);

  async function refreshPorts() {
    try {
      const ps = await listSerialPorts();
      setPorts(ps);
      const esp = ps.find((p) => p.is_esp32s3);
      if (esp) setSelectedPort(esp.path);
    } catch (e) {
      setError(String(e));
    }
  }

  async function doFlash() {
    if (!selectedPort) {
      setError(STRINGS.errors.flashNoPort);
      return;
    }
    setFlashing(true);
    setError(null);
    try {
      await flashFirmware(board, selectedPort);
      setDone(true);
    } catch (e) {
      setError(STRINGS.flash.flashError + ": " + String(e));
    } finally {
      setFlashing(false);
    }
  }

  return (
    <main>
      <h2>{STRINGS.flash.title}</h2>

      {step === "board" && (
        <div className="card">
          <strong>{STRINGS.flash.stepBoard}</strong>
          <label>
            <input
              type="radio"
              checked={board === "wine-216"}
              onChange={() => setBoard("wine-216")}
            />{" "}
            {STRINGS.flash.boardWine}
          </label>
          <label>
            <input
              type="radio"
              checked={board === "standard-216"}
              onChange={() => setBoard("standard-216")}
            />{" "}
            {STRINGS.flash.boardStandard216}
          </label>
          <label>
            <input
              type="radio"
              checked={board === "standard-180"}
              onChange={() => setBoard("standard-180")}
            />{" "}
            {STRINGS.flash.boardStandard180}
          </label>
          <button className="cta" onClick={() => setStep("port")}>
            {STRINGS.setup.next}
          </button>
        </div>
      )}

      {step === "port" && (
        <div className="card">
          <strong>{STRINGS.flash.stepPort}</strong>
          {ports.length === 0 && (
            <p style={{ color: "var(--fg-muted)" }}>
              Kein ESP32-S3 erkannt. USB-Kabel prüfen, dann „Ports neu suchen".
            </p>
          )}
          {ports.map((p) => (
            <label key={p.path}>
              <input
                type="radio"
                checked={selectedPort === p.path}
                onChange={() => setSelectedPort(p.path)}
              />{" "}
              {p.path} {p.is_esp32s3 ? "(ESP32-S3)" : ""}
            </label>
          ))}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="cta cta--ghost" onClick={refreshPorts}>
              {STRINGS.flash.refreshPorts}
            </button>
            <button
              className="cta"
              onClick={() => setStep("flash")}
              disabled={!selectedPort}
            >
              {STRINGS.setup.next}
            </button>
          </div>
        </div>
      )}

      {step === "flash" && (
        <div className="card">
          <strong>{STRINGS.flash.stepFlash}</strong>
          <p>
            Board: <code>{board}</code> · Port: <code>{selectedPort}</code>
          </p>
          {!done && !flashing && (
            <button className="cta" onClick={doFlash}>
              {STRINGS.flash.startFlash}
            </button>
          )}
          {flashing && (
            <>
              <p>{STRINGS.flash.flashing}</p>
              <FlashProgressBar progress={progress} />
            </>
          )}
          {done && (
            <>
              <p style={{ color: "var(--ok)" }}>{STRINGS.flash.flashOk}</p>
              <button className="cta" onClick={onDone}>
                Fertig
              </button>
            </>
          )}
          {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
        </div>
      )}
    </main>
  );
}

function FlashProgressBar({ progress }: { progress: FlashProgress | null }) {
  if (!progress) return null;
  const pct =
    progress.bytes_total > 0
      ? Math.min(
          100,
          Math.round((progress.bytes_written / progress.bytes_total) * 100),
        )
      : 0;
  return (
    <div>
      <small style={{ color: "var(--fg-muted)" }}>
        {progress.phase}
        {progress.message ? ` — ${progress.message}` : ""}
      </small>
      <div
        style={{
          width: "100%",
          height: 8,
          background: "var(--border)",
          borderRadius: 4,
          marginTop: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: "var(--accent)",
            transition: "width 200ms ease-out",
          }}
        />
      </div>
    </div>
  );
}

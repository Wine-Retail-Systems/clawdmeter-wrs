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
import {
  IconArrowLeft,
  IconCheck,
  IconRefresh,
} from "../../components/Icon";

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
        <h2>{STRINGS.flash.title}</h2>
        <p>Schritt {stepIndex(step)} von 3</p>
      </header>

      {step === "board" && (
        <div className="card">
          <p className="card__label">{STRINGS.flash.stepBoard}</p>
          <h3 className="card__heading">Welches Gerät hast du?</h3>
          <div className="option-list">
            <BoardOption
              checked={board === "wine-216"}
              onClick={() => setBoard("wine-216")}
              label={STRINGS.flash.boardWine}
              meta="wine-216"
            />
            <BoardOption
              checked={board === "standard-216"}
              onClick={() => setBoard("standard-216")}
              label={STRINGS.flash.boardStandard216}
              meta="standard-216"
            />
            <BoardOption
              checked={board === "standard-180"}
              onClick={() => setBoard("standard-180")}
              label={STRINGS.flash.boardStandard180}
              meta="standard-180"
            />
          </div>
          <div className="button-row">
            <button
              type="button"
              className="cta"
              onClick={() => setStep("port")}
            >
              {STRINGS.setup.next}
            </button>
          </div>
        </div>
      )}

      {step === "port" && (
        <div className="card">
          <p className="card__label">{STRINGS.flash.stepPort}</p>
          <h3 className="card__heading">USB-Port wählen</h3>
          {ports.length === 0 && (
            <p className="card__body">
              Kein ESP32-S3 erkannt. USB-Kabel prüfen, dann „Ports neu suchen".
            </p>
          )}
          <div className="option-list">
            {ports.map((p) => (
              <label
                key={p.path}
                className={
                  selectedPort === p.path ? "option option--active" : "option"
                }
              >
                <input
                  type="radio"
                  checked={selectedPort === p.path}
                  onChange={() => setSelectedPort(p.path)}
                />
                <span className="option__label">
                  {p.path}
                  {p.is_esp32s3 ? " (ESP32-S3)" : ""}
                </span>
                {p.product && <span className="option__meta">{p.product}</span>}
              </label>
            ))}
          </div>
          <div className="button-row">
            <button
              type="button"
              className="cta cta--ghost"
              onClick={refreshPorts}
            >
              <IconRefresh size={14} /> {STRINGS.flash.refreshPorts}
            </button>
            <button
              type="button"
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
          <p className="card__label">{STRINGS.flash.stepFlash}</p>
          <h3 className="card__heading">Firmware übertragen</h3>
          <p className="card__body">
            Board: <code>{board}</code> · Port: <code>{selectedPort}</code>
          </p>
          {!done && !flashing && (
            <div className="button-row">
              <button type="button" className="cta" onClick={doFlash}>
                {STRINGS.flash.startFlash}
              </button>
            </div>
          )}
          {flashing && (
            <>
              <p className="card__body">{STRINGS.flash.flashing}</p>
              <FlashProgressBar progress={progress} />
            </>
          )}
          {done && (
            <>
              <p className="alert alert--ok">
                <IconCheck size={16} /> {STRINGS.flash.flashOk}
              </p>
              <div className="button-row">
                <button type="button" className="cta" onClick={onDone}>
                  Fertig
                </button>
              </div>
            </>
          )}
          {error && (
            <p className="alert alert--error">{error}</p>
          )}
        </div>
      )}
    </>
  );
}

function stepIndex(step: Step): number {
  if (step === "board") return 1;
  if (step === "port") return 2;
  return 3;
}

function BoardOption({
  checked,
  onClick,
  label,
  meta,
}: {
  checked: boolean;
  onClick: () => void;
  label: string;
  meta: string;
}) {
  return (
    <label className={checked ? "option option--active" : "option"}>
      <input type="radio" checked={checked} onChange={onClick} />
      <span className="option__label">{label}</span>
      <span className="option__meta">{meta}</span>
    </label>
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
      <small className="progress__meta">
        {progress.phase}
        {progress.message ? ` — ${progress.message}` : ""} · {pct}%
      </small>
      <div
        className="progress"
        style={{ ["--progress" as string]: `${pct}%` }}
      >
        <div className="progress__bar" />
      </div>
    </div>
  );
}

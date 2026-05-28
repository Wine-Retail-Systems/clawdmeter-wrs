import { useEffect, useState } from "react";
import {
  ProviderDetectResult,
  ProviderId,
  detectProvider,
  saveProvider,
} from "../../lib/ipc";
import { STRINGS } from "../../lib/strings.de";
import { IconArrowLeft } from "../../components/Icon";

type Props = { onDone: () => void };

const ORDER: ProviderId[] = [
  "anthropic",
  "codex",
  "langdock",
  "opencode",
  "bedrock",
];

export function SetupWizard({ onDone }: Props) {
  const [step, setStep] = useState(0);
  const [results, setResults] = useState<
    Record<ProviderId, ProviderDetectResult | "pending">
  >({} as Record<ProviderId, ProviderDetectResult | "pending">);

  const current = ORDER[step];

  useEffect(() => {
    if (results[current]) return;
    setResults((r) => ({ ...r, [current]: "pending" }));
    detectProvider(current)
      .then((res) => setResults((r) => ({ ...r, [current]: res })))
      .catch(() =>
        setResults((r) => ({
          ...r,
          [current]: { id: current, detected: false, source: null, notes: null },
        })),
      );
  }, [current, results]);

  const status = results[current];

  async function saveAndAdvance() {
    if (status && status !== "pending" && status.detected) {
      await saveProvider(current, { source: status.source ?? "" });
    }
    if (step + 1 < ORDER.length) {
      setStep(step + 1);
    } else {
      onDone();
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
        <h2>{STRINGS.setup.title}</h2>
        <p>{STRINGS.setup.intro}</p>
      </header>

      <div className="card">
        <p className="card__label">
          Schritt {step + 1} von {ORDER.length}
        </p>
        <h3 className="card__heading">{STRINGS.setup.providers[current]}</h3>

        {!status || status === "pending" ? (
          <p className="card__body">
            <span className="status-dot status-dot--unknown status-dot--pulse" />
            {STRINGS.setup.detecting}
          </p>
        ) : status.detected ? (
          <p className="card__body">
            <span className="status-dot status-dot--ok" />
            {STRINGS.setup.detected}
            {status.source && (
              <>
                {" — "}
                <code>{status.source}</code>
              </>
            )}
          </p>
        ) : (
          <p className="card__body">
            <span className="status-dot status-dot--warn" />
            {STRINGS.setup.notDetected}
            {status.notes && (
              <>
                <br />
                <small>{status.notes}</small>
              </>
            )}
          </p>
        )}

        <div className="button-row">
          {step > 0 && (
            <button
              type="button"
              className="cta cta--ghost"
              onClick={() => setStep(step - 1)}
            >
              <IconArrowLeft size={14} /> {STRINGS.setup.back}
            </button>
          )}
          <button type="button" className="cta" onClick={saveAndAdvance}>
            {step + 1 < ORDER.length
              ? STRINGS.setup.next
              : STRINGS.setup.save}
          </button>
        </div>
      </div>
    </>
  );
}

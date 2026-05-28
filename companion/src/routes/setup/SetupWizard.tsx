import { useEffect, useState } from "react";
import {
  ProviderDetectResult,
  ProviderId,
  detectProvider,
  saveProvider,
} from "../../lib/ipc";
import { STRINGS } from "../../lib/strings.de";

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
    <main>
      <h2>{STRINGS.setup.title}</h2>
      <p style={{ color: "var(--fg-muted)" }}>{STRINGS.setup.intro}</p>

      <div className="card">
        <strong>{STRINGS.setup.providers[current]}</strong>
        <small style={{ color: "var(--fg-muted)" }}>
          Schritt {step + 1} von {ORDER.length}
        </small>

        {!status || status === "pending" ? (
          <p>{STRINGS.setup.detecting}</p>
        ) : status.detected ? (
          <p>
            <span className="status-dot status-dot--ok" />
            {STRINGS.setup.detected}
            {status.source && <> — <code>{status.source}</code></>}
          </p>
        ) : (
          <p>
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

        <div style={{ display: "flex", gap: 8 }}>
          {step > 0 && (
            <button
              className="cta cta--ghost"
              onClick={() => setStep(step - 1)}
            >
              {STRINGS.setup.back}
            </button>
          )}
          <button className="cta" onClick={saveAndAdvance}>
            {step + 1 < ORDER.length
              ? STRINGS.setup.next
              : STRINGS.setup.save}
          </button>
        </div>
      </div>
    </main>
  );
}

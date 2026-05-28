import { useEffect, useState } from "react";
import {
  ProviderDetectResult,
  ProviderId,
  detectProvider,
  saveProvider,
  saveSecret,
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

const LANGDOCK_API_KEY_ENV = "LANGDOCK_API_KEY";

function isLoaded(
  s: ProviderDetectResult | "pending" | undefined,
): s is ProviderDetectResult {
  return !!s && s !== "pending";
}

export function SetupWizard({ onDone }: Props) {
  const [step, setStep] = useState(0);
  const [results, setResults] = useState<
    Record<ProviderId, ProviderDetectResult | "pending">
  >({} as Record<ProviderId, ProviderDetectResult | "pending">);

  // Per-Step-Form-Inputs. Bisher nur Langdock — andere Provider füllen das
  // nicht und benutzen den klassischen Auto-Detect-Save.
  const [langdockApiKey, setLangdockApiKey] = useState("");
  const [langdockEmail, setLangdockEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

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
  const loaded = isLoaded(status) ? status : null;
  const detected = loaded?.detected ?? false;

  async function saveAndAdvance() {
    setSaving(true);
    setSaveError(null);
    try {
      if (current === "langdock") {
        // Langdock: API-Key + Email aus dem Formular. Beides optional —
        // Key leer = vorhandenen behalten (oder Provider deaktiviert lassen),
        // Email leer = keine User-Filterung (Org-Summe).
        if (langdockApiKey.trim()) {
          await saveSecret(LANGDOCK_API_KEY_ENV, langdockApiKey.trim());
        }
        // Provider-Block nur dann persistieren, wenn jetzt ODER vorher ein
        // Key vorhanden ist — sonst macht "enabled = true" keinen Sinn.
        if (langdockApiKey.trim() || detected) {
          const fields: Record<string, string> = {
            api_key_env: LANGDOCK_API_KEY_ENV,
          };
          if (langdockEmail.trim()) {
            fields.user_email = langdockEmail.trim();
          }
          await saveProvider("langdock", fields);
        }
      } else if (loaded?.detected && loaded.source) {
        await saveProvider(current, { source: loaded.source });
      }
    } catch (e) {
      setSaveError(
        e instanceof Error ? e.message : STRINGS.setup.langdock.saveError,
      );
      setSaving(false);
      return;
    }
    setSaving(false);
    setLangdockApiKey("");
    setLangdockEmail("");
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

        {current === "langdock" && (
          <div className="form-stack">
            <label className="form-field">
              <span className="form-field__label">
                {STRINGS.setup.langdock.apiKeyLabel}
              </span>
              <input
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder={STRINGS.setup.langdock.apiKeyPlaceholder}
                value={langdockApiKey}
                onChange={(e) => setLangdockApiKey(e.target.value)}
                disabled={saving}
              />
              <small className="form-field__help">
                {detected
                  ? `${STRINGS.setup.langdock.apiKeyExists} ${
                      loaded?.source ?? ""
                    }. ${STRINGS.setup.langdock.apiKeyKeep}`
                  : STRINGS.setup.langdock.apiKeyHelp}
              </small>
            </label>

            <label className="form-field">
              <span className="form-field__label">
                {STRINGS.setup.langdock.emailLabel}
              </span>
              <input
                type="email"
                autoComplete="email"
                spellCheck={false}
                placeholder={STRINGS.setup.langdock.emailPlaceholder}
                value={langdockEmail}
                onChange={(e) => setLangdockEmail(e.target.value)}
                disabled={saving}
              />
              <small className="form-field__help">
                {STRINGS.setup.langdock.emailHelp}
              </small>
            </label>

            {saveError && (
              <p className="form-error">
                {STRINGS.setup.langdock.saveError}: {saveError}
              </p>
            )}
          </div>
        )}

        <div className="button-row">
          {step > 0 && (
            <button
              type="button"
              className="cta cta--ghost"
              onClick={() => setStep(step - 1)}
              disabled={saving}
            >
              <IconArrowLeft size={14} /> {STRINGS.setup.back}
            </button>
          )}
          <button
            type="button"
            className="cta"
            onClick={saveAndAdvance}
            disabled={saving}
          >
            {step + 1 < ORDER.length
              ? STRINGS.setup.next
              : STRINGS.setup.save}
          </button>
        </div>
      </div>
    </>
  );
}

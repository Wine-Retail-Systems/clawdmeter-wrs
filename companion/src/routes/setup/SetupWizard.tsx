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
  "bifrost",
  "codex",
  "langdock",
  "bedrock",
];

const LANGDOCK_API_KEY_ENV = "LANGDOCK_API_KEY";
const BIFROST_API_KEY_ENV = "BIFROST_VIRTUAL_KEY";
const BIFROST_DEFAULT_URL = "https://llm-gw.wineretailsystems.cloud";
const BIFROST_KEY_PREFIX = "sk-bf-";

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
  const [bifrostKey, setBifrostKey] = useState("");
  const [bifrostUrl, setBifrostUrl] = useState("");
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
          [current]: {
            id: current,
            detected: false,
            source: null,
            notes: null,
          },
        })),
      );
  }, [current, results]);

  const status = results[current];
  const loaded = isLoaded(status) ? status : null;
  const detected = loaded?.detected ?? false;

  function advance() {
    if (step + 1 < ORDER.length) {
      setStep(step + 1);
    } else {
      onDone();
    }
  }

  // Bifrost: der Daemon kopiert den erkannten Key selbst aus der
  // Claude-Code-Konfiguration; hier läuft nur das Kürzel "claude-settings".
  async function adoptDetectedBifrost() {
    setSaving(true);
    setSaveError(null);
    try {
      await saveProvider("bifrost", { source: "claude-settings" });
    } catch (e) {
      setSaveError(
        e instanceof Error ? e.message : STRINGS.setup.bifrost.saveError,
      );
      setSaving(false);
      return;
    }
    setSaving(false);
    advance();
  }

  async function saveAndAdvance() {
    setSaving(true);
    setSaveError(null);
    try {
      if (current === "bifrost") {
        const key = bifrostKey.trim();
        if (key) {
          if (!key.startsWith(BIFROST_KEY_PREFIX)) {
            setSaveError(STRINGS.setup.bifrost.apiKeyInvalid);
            setSaving(false);
            return;
          }
          await saveSecret(BIFROST_API_KEY_ENV, key);
          const fields: Record<string, string> = {
            api_key_env: BIFROST_API_KEY_ENV,
          };
          if (bifrostUrl.trim()) fields.base_url = bifrostUrl.trim();
          await saveProvider("bifrost", fields);
        }
      } else if (current === "langdock") {
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
    setBifrostKey("");
    setBifrostUrl("");
    advance();
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

        {current === "bifrost" && (
          <p className="card__body">{STRINGS.setup.bifrost.intro}</p>
        )}

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

        {current === "bifrost" && (
          <div className="form-stack">
            {detected && loaded?.masked && (
              <div className="form-field">
                <span className="form-field__label">
                  {STRINGS.setup.bifrost.detectedKey}
                </span>
                <code>{loaded.masked}</code>
                {loaded.source && (
                  <small className="form-field__help">{loaded.source}</small>
                )}
                <div className="button-row">
                  <button
                    type="button"
                    className="cta"
                    onClick={adoptDetectedBifrost}
                    disabled={saving}
                  >
                    {STRINGS.setup.bifrost.useDetected}
                  </button>
                </div>
              </div>
            )}

            <label className="form-field">
              <span className="form-field__label">
                {detected && loaded?.masked
                  ? STRINGS.setup.bifrost.manualHeading
                  : STRINGS.setup.bifrost.apiKeyLabel}
              </span>
              <input
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder={STRINGS.setup.bifrost.apiKeyPlaceholder}
                value={bifrostKey}
                onChange={(e) => setBifrostKey(e.target.value)}
                disabled={saving}
              />
              <small className="form-field__help">
                {STRINGS.setup.bifrost.apiKeyHelp}
              </small>
            </label>

            <label className="form-field">
              <span className="form-field__label">
                {STRINGS.setup.bifrost.baseUrlLabel}
              </span>
              <input
                type="url"
                autoComplete="off"
                spellCheck={false}
                placeholder={loaded?.base_url ?? BIFROST_DEFAULT_URL}
                value={bifrostUrl}
                onChange={(e) => setBifrostUrl(e.target.value)}
                disabled={saving}
              />
              <small className="form-field__help">
                {STRINGS.setup.bifrost.baseUrlHelp}
              </small>
            </label>

            {saveError && (
              <p className="form-error">
                {STRINGS.setup.bifrost.saveError}: {saveError}
              </p>
            )}
          </div>
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

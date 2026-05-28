import { useState } from "react";
import type { Route } from "../App";
import type { DaemonStatus } from "../lib/ipc";
import { installDaemonService, migrateLegacyDaemon } from "../lib/ipc";
import { STRINGS } from "../lib/strings.de";
import {
  IconActivity,
  IconArrowRight,
  IconBluetooth,
  IconFlash,
  IconKey,
} from "../components/Icon";

type Props = {
  status: DaemonStatus | null;
  onNavigate: (route: Route) => void;
};

export function Landing({ status, onNavigate }: Props) {
  return (
    <>
      <header className="page-heading">
        <h2>{STRINGS.landing.heading}</h2>
        <p>Onboarding, Flashen und Betrieb deines Clawdmeters.</p>
      </header>

      <DaemonInstallCard status={status} />

      <div className="action-grid stagger">
        <ActionCard
          variant="primary"
          icon={<IconFlash />}
          title={STRINGS.landing.flashCta}
          hint={STRINGS.landing.flashHelp}
          onClick={() => onNavigate("flash")}
        />
        <ActionCard
          icon={<IconKey />}
          title={STRINGS.landing.setupCta}
          hint={STRINGS.landing.setupHelp}
          onClick={() => onNavigate("setup")}
        />
        <ActionCard
          icon={<IconBluetooth />}
          title={STRINGS.landing.pairCta}
          hint={STRINGS.landing.pairHelp}
          onClick={() => onNavigate("pair")}
        />
        <ActionCard
          icon={<IconActivity />}
          title={STRINGS.landing.statusCta}
          hint={STRINGS.landing.statusHelp}
          onClick={() => onNavigate("status")}
        />
      </div>
    </>
  );
}

type ActionCardProps = {
  variant?: "primary" | "default";
  icon: React.ReactNode;
  title: string;
  hint: string;
  onClick: () => void;
};

function ActionCard({
  variant = "default",
  icon,
  title,
  hint,
  onClick,
}: ActionCardProps) {
  return (
    <button
      type="button"
      className={
        variant === "primary"
          ? "action-card action-card--primary"
          : "action-card"
      }
      onClick={onClick}
    >
      <span className="action-card__icon" aria-hidden="true">
        {icon}
      </span>
      <h3 className="action-card__title">{title}</h3>
      <p className="action-card__hint">{hint}</p>
      <span className="action-card__cta">
        Öffnen
        <IconArrowRight size={14} />
      </span>
    </button>
  );
}

/**
 * Drei Modi:
 *  • Legacy erkannt → Migrations-Karte (übernehmen + alten Daemon entfernen)
 *  • Daemon nicht installiert (und keine Legacy) → reguläre Installations-Karte
 *  • sonst (installiert) → keine Karte
 */
function DaemonInstallCard({ status }: { status: DaemonStatus | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  if (!status) return null;

  const hasLegacy = status.legacy_labels.length > 0;
  if (status.installed && !hasLegacy) return null;

  const handleClick = async () => {
    setBusy(true);
    setError(null);
    try {
      if (hasLegacy) {
        await migrateLegacyDaemon();
      } else {
        await installDaemonService();
      }
      setDone(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (hasLegacy) {
    return (
      <div className="card">
        <p className="card__label">{STRINGS.daemon.legacyHeading}</p>
        <h3 className="card__heading">Alten Daemon übernehmen</h3>
        <p className="card__body">{STRINGS.daemon.legacyBody}</p>
        <p className="card__hint-mono">{status.legacy_labels.join(", ")}</p>
        <button
          type="button"
          className="cta cta--spaced"
          onClick={handleClick}
          disabled={busy}
        >
          {busy ? STRINGS.daemon.legacyMigrating : STRINGS.daemon.legacyAction}
        </button>
        {done && (
          <p className="alert alert--ok">{STRINGS.daemon.legacyDone}</p>
        )}
        {error && (
          <p className="alert alert--error">
            {STRINGS.daemon.legacyError}: {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="card">
      <p className="card__label">Einmalige Einrichtung</p>
      <h3 className="card__heading">Daemon installieren</h3>
      <p className="card__body">
        Der Daemon liest deine Provider-Credentials und schickt die Nutzung an
        dein Clawdmeter. Er läuft unsichtbar im Hintergrund und startet mit
        dem System.
      </p>
      <button
        type="button"
        className="cta cta--spaced"
        onClick={handleClick}
        disabled={busy}
      >
        {busy ? STRINGS.daemon.installing : STRINGS.daemon.installAction}
      </button>
      {error && <p className="alert alert--error">{error}</p>}
    </div>
  );
}

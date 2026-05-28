import type { Route } from "../App";
import type { DaemonStatus } from "../lib/ipc";
import { STRINGS } from "../lib/strings.de";

type Props = {
  status: DaemonStatus | null;
  onNavigate: (route: Route) => void;
};

export function Landing({ status, onNavigate }: Props) {
  return (
    <main className="landing">
      <h2>{STRINGS.landing.heading}</h2>

      <div className="card">
        <DaemonStatusLine status={status} />
        <button className="cta" onClick={() => onNavigate("flash")}>
          {STRINGS.landing.flashCta}
        </button>
        <p style={{ color: "var(--fg-muted)", margin: 0 }}>
          {STRINGS.landing.flashHelp}
        </p>
      </div>

      <div className="card">
        <button
          className="cta cta--ghost"
          onClick={() => onNavigate("setup")}
        >
          {STRINGS.landing.setupCta}
        </button>
        <p style={{ color: "var(--fg-muted)", margin: 0 }}>
          {STRINGS.landing.setupHelp}
        </p>
      </div>

      <div className="card">
        <button
          className="cta cta--ghost"
          onClick={() => onNavigate("pair")}
        >
          {STRINGS.landing.pairCta}
        </button>
        <p style={{ color: "var(--fg-muted)", margin: 0 }}>
          {STRINGS.landing.pairHelp}
        </p>
      </div>

      <div className="card">
        <button
          className="cta cta--ghost"
          onClick={() => onNavigate("status")}
        >
          {STRINGS.landing.statusCta}
        </button>
        <p style={{ color: "var(--fg-muted)", margin: 0 }}>
          {STRINGS.landing.statusHelp}
        </p>
      </div>
    </main>
  );
}

function DaemonStatusLine({ status }: { status: DaemonStatus | null }) {
  if (!status) {
    return (
      <span>
        <span className="status-dot status-dot--unknown" />
        {STRINGS.daemon.unknown}
      </span>
    );
  }
  if (!status.reachable) {
    return (
      <span>
        <span className="status-dot status-dot--error" />
        {STRINGS.daemon.error}
      </span>
    );
  }
  if (!status.running) {
    return (
      <span>
        <span className="status-dot status-dot--warn" />
        {STRINGS.daemon.stopped}
      </span>
    );
  }
  return (
    <span>
      <span className="status-dot status-dot--ok" />
      {STRINGS.daemon.running}
    </span>
  );
}

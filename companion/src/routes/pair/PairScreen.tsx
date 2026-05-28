import { useEffect, useState } from "react";
import { BleDevice, scanBleDevices } from "../../lib/ipc";
import { STRINGS } from "../../lib/strings.de";
import {
  IconArrowLeft,
  IconBluetooth,
  IconRefresh,
} from "../../components/Icon";

type Props = { onDone: () => void };

export function PairScreen({ onDone }: Props) {
  const [scanning, setScanning] = useState(false);
  const [devices, setDevices] = useState<BleDevice[]>([]);

  useEffect(() => {
    rescan();
  }, []);

  async function rescan() {
    setScanning(true);
    try {
      const ds = await scanBleDevices(8000);
      setDevices(ds);
    } finally {
      setScanning(false);
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
        <h2>{STRINGS.pair.title}</h2>
        <p>Stelle sicher, dass dein Clawdmeter eingeschaltet ist.</p>
      </header>

      <div className="card">
        <p className="card__label">Geräte in Reichweite</p>

        {scanning && (
          <p className="card__body">
            <span className="status-dot status-dot--ok status-dot--pulse" />
            {STRINGS.pair.scanning}
          </p>
        )}

        {!scanning && devices.length === 0 && (
          <p className="card__body">
            <span className="status-dot status-dot--warn" />
            {STRINGS.pair.foundNone}
          </p>
        )}

        {devices.length > 0 && (
          <div className="option-list">
            {devices.map((d) => (
              <div key={d.address} className="option">
                <span aria-hidden="true">
                  <IconBluetooth size={18} />
                </span>
                <span className="option__label">
                  <strong>{d.name}</strong>
                </span>
                <span className="option__meta">
                  {d.address}
                  {d.rssi !== null && ` · ${d.rssi} dBm`}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="button-row">
          <button
            type="button"
            className="cta cta--ghost"
            onClick={rescan}
            disabled={scanning}
          >
            <IconRefresh size={14} /> {STRINGS.pair.rescan}
          </button>
          <button type="button" className="cta" onClick={onDone}>
            Fertig
          </button>
        </div>
      </div>

      <div className="card">
        <p className="card__label">Hinweis</p>
        <h3 className="card__heading">{STRINGS.pair.helpHeading}</h3>
        <p className="card__body">{STRINGS.pair.helpBody}</p>
      </div>
    </>
  );
}

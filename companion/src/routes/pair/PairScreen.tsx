import { useEffect, useState } from "react";
import { BleDevice, scanBleDevices } from "../../lib/ipc";
import { STRINGS } from "../../lib/strings.de";

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
    <main>
      <h2>{STRINGS.pair.title}</h2>

      <div className="card">
        {scanning && <p>{STRINGS.pair.scanning}</p>}
        {!scanning && devices.length === 0 && (
          <p style={{ color: "var(--fg-muted)" }}>{STRINGS.pair.foundNone}</p>
        )}
        {devices.map((d) => (
          <div key={d.address}>
            <strong>{d.name}</strong>
            <br />
            <small style={{ color: "var(--fg-muted)" }}>
              {d.address}
              {d.rssi !== null && <> · RSSI {d.rssi} dBm</>}
            </small>
          </div>
        ))}
        <div style={{ display: "flex", gap: 8 }}>
          <button
            className="cta cta--ghost"
            onClick={rescan}
            disabled={scanning}
          >
            {STRINGS.pair.rescan}
          </button>
          <button className="cta" onClick={onDone}>
            Fertig
          </button>
        </div>
      </div>

      <div className="card">
        <strong>{STRINGS.pair.helpHeading}</strong>
        <p>{STRINGS.pair.helpBody}</p>
      </div>
    </main>
  );
}

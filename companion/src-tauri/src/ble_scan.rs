//! BLE-Discovery via `btleplug`. Reine Read-Only-Discovery — das eigentliche
//! Pairing übernimmt das Betriebssystem (CoreBluetooth-Dialog auf macOS,
//! Windows-Bluetooth-Settings).

use serde::Serialize;
use std::time::Duration;

#[derive(Debug, Serialize, Clone)]
pub struct BleDeviceInfo {
    pub address: String,
    pub name: String,
    pub rssi: Option<i16>,
}

#[tauri::command]
pub async fn ble_scan(timeout_ms: u64) -> Result<Vec<BleDeviceInfo>, String> {
    use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter};
    use btleplug::platform::Manager;

    let manager = Manager::new().await.map_err(|e| e.to_string())?;
    let adapters = manager.adapters().await.map_err(|e| e.to_string())?;
    let Some(adapter) = adapters.into_iter().next() else {
        return Err("Kein Bluetooth-Adapter gefunden".into());
    };
    adapter
        .start_scan(ScanFilter::default())
        .await
        .map_err(|e| e.to_string())?;
    tokio::time::sleep(Duration::from_millis(timeout_ms)).await;

    let mut out = Vec::new();
    for p in adapter.peripherals().await.map_err(|e| e.to_string())? {
        let props = match p.properties().await {
            Ok(Some(p)) => p,
            _ => continue,
        };
        let name = props.local_name.unwrap_or_default();
        if !name.to_lowercase().contains("clawdmeter")
            && !name.to_lowercase().contains("claude")
        {
            continue;
        }
        out.push(BleDeviceInfo {
            address: props.address.to_string(),
            name,
            rssi: props.rssi,
        });
    }
    let _ = adapter.stop_scan().await;
    Ok(out)
}

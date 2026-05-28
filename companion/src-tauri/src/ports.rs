//! USB-Serial-Discovery. ESP32-S3 meldet sich mit VID 0x303A (Espressif) und
//! diversen PIDs (USB-JTAG 0x1001 für unsere Boards). Wir filtern auf VID,
//! die UI markiert ESP32-S3-Treffer prominent.

use serde::Serialize;

pub const ESP32_VID: u16 = 0x303A;

#[derive(Debug, Serialize, Clone)]
pub struct SerialPortInfo {
    pub path: String,
    pub product: Option<String>,
    pub manufacturer: Option<String>,
    pub vid: Option<u16>,
    pub pid: Option<u16>,
    pub is_esp32s3: bool,
}

#[tauri::command]
pub fn list_serial_ports() -> Result<Vec<SerialPortInfo>, String> {
    let ports = serialport::available_ports().map_err(|e| e.to_string())?;
    let mut out = Vec::new();
    for p in ports {
        let (vid, pid, product, manufacturer) = match &p.port_type {
            serialport::SerialPortType::UsbPort(usb) => (
                Some(usb.vid),
                Some(usb.pid),
                usb.product.clone(),
                usb.manufacturer.clone(),
            ),
            _ => (None, None, None, None),
        };
        let is_esp32s3 = vid == Some(ESP32_VID);
        out.push(SerialPortInfo {
            path: p.port_name,
            product,
            manufacturer,
            vid,
            pid,
            is_esp32s3,
        });
    }

    // macOS legt jedes USB-Serial-Gerät doppelt an: /dev/cu.X (call-up,
    // non-blocking — zum Flashen) und /dev/tty.X (incoming, blockiert
    // auf DCD). Nur cu.* ist zum Flashen brauchbar. Wenn beide Varianten
    // desselben Geräts vorhanden sind, werfen wir tty.* raus, damit die
    // Liste nicht doppelt erscheint und der Nutzer nicht versehentlich
    // den blockierenden tty-Node wählt.
    #[cfg(target_os = "macos")]
    {
        use std::collections::HashSet;
        let cu_suffixes: HashSet<String> = out
            .iter()
            .filter_map(|p| p.path.strip_prefix("/dev/cu.").map(String::from))
            .collect();
        out.retain(|p| {
            if let Some(suffix) = p.path.strip_prefix("/dev/tty.") {
                !cu_suffixes.contains(suffix)
            } else {
                true
            }
        });
    }

    // ESP32-S3 zuerst, dann der Rest — UI kann die Standardauswahl direkt
    // übernehmen.
    out.sort_by(|a, b| b.is_esp32s3.cmp(&a.is_esp32s3));
    Ok(out)
}

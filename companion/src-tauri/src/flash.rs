//! Wrapper um die `espflash`-Bibliothek. Wir öffnen den seriellen Port
//! direkt, verbinden uns mit der ROM-Bootloader-Stub-Routine des ESP32-S3
//! und schreiben das Image. Fortschritt streamt via Tauri-Events
//! (`flash-progress`) ans Frontend.
//!
//! ⚠ Vor dem ersten Release-Bau auf echter Hardware verifizieren: die
//! exakten Methoden-Signaturen der espflash-3.x-Lib-API (`Flasher::connect`,
//! `write_bin_to_flash`, `ProgressCallbacks`) sind hier gegen die Doku
//! geschrieben — falls die Crate-API zwischen Minor-Versionen leicht
//! abweicht, sind hier kleine Tweaks nötig.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Debug, Serialize, Clone)]
pub struct FlashProgress {
    pub phase: String,
    pub bytes_written: u64,
    pub bytes_total: u64,
    pub message: Option<String>,
}

fn firmware_path(app: &AppHandle, board: &str) -> Result<PathBuf, String> {
    let allowed = ["wine-216", "standard-216", "standard-180"];
    if !allowed.contains(&board) {
        return Err(format!("Unbekanntes Board: {board}"));
    }
    // ``{board}.bin`` ist die ``firmware.factory.bin`` aus PlatformIO —
    // gemergtes Image (Bootloader @ 0x0 + Partitions @ 0x8000 + App @ 0x10000),
    // flashbar als single-blob an Offset 0x0. Siehe
    // ``tools/copy_firmware_to_companion.py``.
    let rel = format!("resources/firmware/{board}.bin");
    app.path()
        .resolve(&rel, tauri::path::BaseDirectory::Resource)
        .map_err(|e| format!("Firmware {rel} nicht gefunden: {e}"))
}

#[tauri::command]
pub async fn flash_firmware(
    app: AppHandle,
    board: String,
    port: String,
) -> Result<(), String> {
    let bin = firmware_path(&app, &board)?;
    let total_bytes = std::fs::metadata(&bin)
        .map_err(|e| e.to_string())?
        .len();

    emit(
        &app,
        FlashProgress {
            phase: "erase".into(),
            bytes_written: 0,
            bytes_total: total_bytes,
            message: Some(format!("Verbinde mit {port} …")),
        },
    );

    let app_for_progress = app.clone();
    let result = tokio::task::spawn_blocking(move || {
        do_flash(&bin, &port, total_bytes, move |p| {
            let _ = app_for_progress.emit("flash-progress", p);
        })
    })
    .await
    .map_err(|e| e.to_string())?;

    match result {
        Ok(()) => {
            emit(
                &app,
                FlashProgress {
                    phase: "done".into(),
                    bytes_written: total_bytes,
                    bytes_total: total_bytes,
                    message: None,
                },
            );
            Ok(())
        }
        Err(e) => {
            emit(
                &app,
                FlashProgress {
                    phase: "error".into(),
                    bytes_written: 0,
                    bytes_total: total_bytes,
                    message: Some(e.clone()),
                },
            );
            Err(e)
        }
    }
}

fn emit(app: &AppHandle, p: FlashProgress) {
    let _ = app.emit("flash-progress", p);
}

/// Eigentliche Flash-Logik. Läuft in einem Blocking-Thread, weil
/// `espflash` synchron ist.
fn do_flash(
    bin: &std::path::Path,
    port: &str,
    total_bytes: u64,
    report: impl Fn(FlashProgress) + Send + Sync + 'static,
) -> Result<(), String> {
    use espflash::{
        connection::reset::{ResetAfterOperation, ResetBeforeOperation},
        flasher::{Flasher, ProgressCallbacks},
        targets::Chip,
    };

    // Wir öffnen den seriellen Port mit 115200 — espflash handelt das
    // Hochsetzen auf 460800 nach dem Handshake selbst.
    let serial_port = serialport::new(port, 115_200)
        .open_native()
        .map_err(|e| format!("Port {port} öffnen: {e}"))?;
    let usb_info = serialport::available_ports()
        .map_err(|e| e.to_string())?
        .into_iter()
        .find(|p| p.port_name == port)
        .ok_or_else(|| format!("Port-Info für {port} nicht gefunden"))?;
    let usb = match usb_info.port_type {
        serialport::SerialPortType::UsbPort(u) => u,
        _ => return Err(format!("Port {port} ist kein USB-Gerät")),
    };

    let report_arc: Arc<dyn Fn(FlashProgress) + Send + Sync> =
        Arc::new(report);

    let mut flasher = Flasher::connect(
        serial_port,
        usb,
        Some(460_800),
        true,  // use_stub
        true,  // verify
        false, // skip_padding
        Some(Chip::Esp32s3),
        ResetAfterOperation::default(),
        ResetBeforeOperation::default(),
    )
    .map_err(|e| format!("Verbinden zum ESP32-S3 fehlgeschlagen: {e}"))?;

    let data = std::fs::read(bin).map_err(|e| e.to_string())?;

    struct Cb {
        report: Arc<dyn Fn(FlashProgress) + Send + Sync>,
        total: u64,
        cur: Arc<Mutex<u64>>,
    }
    impl ProgressCallbacks for Cb {
        fn init(&mut self, _addr: u32, total: usize) {
            (self.report)(FlashProgress {
                phase: "write".into(),
                bytes_written: 0,
                bytes_total: total as u64,
                message: None,
            });
            *self.cur.lock().unwrap() = 0;
            // total kommt segment-weise — wir behalten den File-Gesamtwert
            let _ = total;
        }
        fn update(&mut self, current: usize) {
            let mut g = self.cur.lock().unwrap();
            *g = current as u64;
            (self.report)(FlashProgress {
                phase: "write".into(),
                bytes_written: *g,
                bytes_total: self.total,
                message: None,
            });
        }
        fn finish(&mut self) {
            (self.report)(FlashProgress {
                phase: "verify".into(),
                bytes_written: self.total,
                bytes_total: self.total,
                message: None,
            });
        }
    }

    let mut cb = Cb {
        report: report_arc,
        total: total_bytes,
        cur: Arc::new(Mutex::new(0)),
    };

    flasher
        .write_bin_to_flash(0x0, &data, Some(&mut cb))
        .map_err(|e| format!("Flash-Write: {e}"))?;

    Ok(())
}

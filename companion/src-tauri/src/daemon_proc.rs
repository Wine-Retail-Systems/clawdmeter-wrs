//! Daemon-Lifecycle: Start / Stop / Restart / Logs.
//!
//! Auf macOS sprechen wir mit `launchctl` (LaunchAgent), auf Windows mit
//! `schtasks` (Scheduled Task). Reine Sub-Process-Hülle — die eigentliche
//! Service-Installation lebt in `service.rs`.

use serde::Serialize;

use crate::ipc;

#[derive(Debug, Serialize, Clone, Default)]
pub struct DaemonStatus {
    pub reachable: bool,
    pub running: bool,
    pub device_connected: bool,
    pub last_poll_at: Option<String>,
    pub active_provider: Option<String>,
    pub message: Option<String>,
}

#[tauri::command]
pub async fn daemon_status() -> Result<DaemonStatus, String> {
    // Versuche IPC; bei Fehler liefert wir „unreachable", damit das UI das
    // sauber anzeigen kann.
    match ipc::request("status", serde_json::json!({})).await {
        Ok(v) => {
            let reply: ipc::DaemonStatusReply =
                serde_json::from_value(v).map_err(|e| e.to_string())?;
            Ok(DaemonStatus {
                reachable: reply.reachable,
                running: reply.running,
                device_connected: reply.device_connected,
                last_poll_at: reply.last_poll_at,
                active_provider: reply.active_provider,
                message: reply.message,
            })
        }
        Err(_) => Ok(DaemonStatus {
            reachable: false,
            ..Default::default()
        }),
    }
}

#[tauri::command]
pub fn daemon_start() -> Result<(), String> {
    crate::service::start().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn daemon_stop() -> Result<(), String> {
    crate::service::stop().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn daemon_restart() -> Result<(), String> {
    crate::service::restart().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn daemon_install_service(app: tauri::AppHandle) -> Result<(), String> {
    crate::service::ensure_installed(&app).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn daemon_tail_logs(lines: usize) -> Result<Vec<String>, String> {
    crate::service::tail_logs(lines).map_err(|e| e.to_string())
}

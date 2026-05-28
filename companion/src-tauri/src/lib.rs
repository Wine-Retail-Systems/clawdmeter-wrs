//! Tauri-Bootstrap. Hält die App schlank — sämtliche Domänen-Logik liegt in
//! den thematischen Modulen (flash, ports, daemon_proc, ipc, service,
//! ble_scan, crash, updater).

pub mod ble_scan;
pub mod crash;
pub mod daemon_proc;
pub mod flash;
pub mod ipc;
pub mod ports;
pub mod service;
pub mod tray;
pub mod updater;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or("info"),
    )
    .init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            tray::install(app.handle())?;
            // Daemon-Lifecycle: stelle sicher, dass beim ersten Start ein
            // LaunchAgent/Scheduled Task existiert. Stilles No-Op falls bereits
            // installiert.
            if let Err(e) = service::ensure_installed(app.handle()) {
                log::warn!("Service nicht installiert: {e:#}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // Daemon
            daemon_proc::daemon_status,
            daemon_proc::daemon_start,
            daemon_proc::daemon_stop,
            daemon_proc::daemon_restart,
            daemon_proc::daemon_install_service,
            daemon_proc::daemon_tail_logs,
            // Flash
            ports::list_serial_ports,
            flash::flash_firmware,
            // Provider-Setup (über Daemon-IPC)
            ipc::provider_detect,
            ipc::provider_save,
            // BLE
            ble_scan::ble_scan,
            // Bug-Report
            crash::collect_crash_bundle,
        ])
        .run(tauri::generate_context!())
        .expect("Tauri-Runtime konnte nicht gestartet werden");
}

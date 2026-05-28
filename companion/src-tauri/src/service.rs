//! LaunchAgent / Scheduled Task. Wird beim ersten App-Start angelegt und
//! verweist auf die mitgelieferte PyInstaller-Daemon-Binary aus
//! `resources/daemon/`.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;

use anyhow::{Context, Result};
use serde::Serialize;
use tauri::{AppHandle, Manager};

pub const SERVICE_LABEL: &str = "eu.wineretailsystems.clawdmeter.daemon";

/// Frühere Labels, die wir beim ersten Start des neuen Companion finden und
/// ablösen. Ergibt sich aus:
///   * `com.clawdmeter.daemon`        — vom alten `install-mac.sh`-Skript
///   * `de.jacques.clawdmeter.daemon` — frühere Companion-Beta
///
/// Die eigentliche Daemon-Konfiguration lebt label-agnostisch unter
/// `~/.config/clawdmeter/` bzw. `%APPDATA%\clawdmeter\` — Migration heißt
/// daher: LaunchAgent/Scheduled-Task austauschen, Config bleibt.
pub const LEGACY_LABELS: &[&str] = &[
    "com.clawdmeter.daemon",
    "de.jacques.clawdmeter.daemon",
];

#[derive(Debug, Serialize, Clone)]
pub struct LegacyInstall {
    pub label: String,
    pub running: bool,
}

/// Pfad zur gebündelten Daemon-Binary (plattformspezifisch).
fn daemon_binary(app: &AppHandle) -> Result<PathBuf> {
    let name = if cfg!(target_os = "windows") {
        "clawdmeter-daemon-win-x64.exe"
    } else if cfg!(target_arch = "aarch64") {
        "clawdmeter-daemon-macos-arm64"
    } else {
        "clawdmeter-daemon-macos-x64"
    };
    Ok(app
        .path()
        .resolve(
            format!("resources/daemon/{name}"),
            tauri::path::BaseDirectory::Resource,
        )
        .context("Daemon-Binary nicht in resources/daemon/ gefunden")?)
}

/// Pfad zum LaunchAgent-Plist für ein beliebiges Label (macOS).
#[cfg(target_os = "macos")]
fn plist_path_for(label: &str) -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("/tmp"))
        .join("Library/LaunchAgents")
        .join(format!("{label}.plist"))
}

/// Ist der Companion-Daemon für das aktuelle Label registriert?
#[cfg(target_os = "macos")]
pub fn is_installed() -> bool {
    plist_path_for(SERVICE_LABEL).exists()
}

#[cfg(target_os = "windows")]
pub fn is_installed() -> bool {
    std::process::Command::new("schtasks")
        .args(["/Query", "/TN", SERVICE_LABEL])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn is_installed() -> bool {
    false
}

/// Sucht nach Plists/Tasks unter alten Labels, damit das UI eine Migration
/// anbieten kann.
#[cfg(target_os = "macos")]
pub fn detect_legacy() -> Vec<LegacyInstall> {
    LEGACY_LABELS
        .iter()
        .filter(|l| plist_path_for(l).exists())
        .map(|l| LegacyInstall {
            label: (*l).into(),
            running: launchctl_label_loaded(l),
        })
        .collect()
}

#[cfg(target_os = "macos")]
fn launchctl_label_loaded(label: &str) -> bool {
    std::process::Command::new("launchctl")
        .args(["list", label])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

#[cfg(target_os = "windows")]
pub fn detect_legacy() -> Vec<LegacyInstall> {
    LEGACY_LABELS
        .iter()
        .filter_map(|label| {
            let out = std::process::Command::new("schtasks")
                .args(["/Query", "/TN", label])
                .output()
                .ok()?;
            if !out.status.success() {
                return None;
            }
            Some(LegacyInstall {
                label: (*label).into(),
                running: true,
            })
        })
        .collect()
}

#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn detect_legacy() -> Vec<LegacyInstall> {
    Vec::new()
}

/// Entlädt einen alten LaunchAgent und löscht das Plist (macOS) bzw.
/// löscht den Scheduled Task (Windows). Idempotent.
#[cfg(target_os = "macos")]
pub fn uninstall_label(label: &str) -> Result<()> {
    let plist = plist_path_for(label);
    if plist.exists() {
        let _ = std::process::Command::new("launchctl")
            .args(["unload", plist.to_str().unwrap_or_default()])
            .status();
        std::fs::remove_file(&plist)
            .with_context(|| format!("Plist {} konnte nicht entfernt werden", plist.display()))?;
    } else {
        // Plist weg, aber falls noch im launchd-Speicher: explizit entladen.
        let _ = std::process::Command::new("launchctl")
            .args(["remove", label])
            .status();
    }
    Ok(())
}

#[cfg(target_os = "windows")]
pub fn uninstall_label(label: &str) -> Result<()> {
    let _ = std::process::Command::new("schtasks")
        .args(["/End", "/TN", label])
        .status();
    let status = std::process::Command::new("schtasks")
        .args(["/Delete", "/TN", label, "/F"])
        .status()
        .context("schtasks /Delete")?;
    if !status.success() {
        anyhow::bail!("schtasks /Delete exit {status}");
    }
    Ok(())
}

#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn uninstall_label(_label: &str) -> Result<()> {
    Ok(())
}

/// Räumt alle bekannten Vorgänger-Installationen ab und installiert den
/// aktuellen Companion-Daemon. Die Daemon-Konfiguration (~/.config/clawdmeter)
/// wird bewusst nicht angefasst — sie ist label-agnostisch.
pub fn migrate_from_legacy(app: &AppHandle) -> Result<()> {
    for legacy in detect_legacy() {
        // Best-effort: wir loggen Fehler, brechen aber nicht ab — sonst bleibt
        // der User in einem halbmigrierten Zustand hängen.
        if let Err(e) = uninstall_label(&legacy.label) {
            log::warn!("Legacy-Label {} konnte nicht entfernt werden: {e:#}", legacy.label);
        }
    }
    ensure_installed(app)
}

fn log_path() -> PathBuf {
    let mut p = dirs::home_dir().unwrap_or_else(|| PathBuf::from("/tmp"));
    #[cfg(target_os = "macos")]
    {
        p.push("Library/Logs/clawdmeter-daemon.log");
    }
    #[cfg(not(target_os = "macos"))]
    {
        p.push(".clawdmeter/daemon.log");
    }
    p
}

#[cfg(target_os = "macos")]
pub fn ensure_installed(app: &AppHandle) -> Result<()> {
    use std::fs;
    let bin = daemon_binary(app)?;
    let home = dirs::home_dir().context("HOME nicht ermittelbar")?;
    let plist_path = home
        .join("Library/LaunchAgents")
        .join(format!("{SERVICE_LABEL}.plist"));
    let log = log_path();
    if let Some(parent) = log.parent() {
        fs::create_dir_all(parent).ok();
    }
    let home = dirs::home_dir().context("HOME nicht ermittelbar")?;
    let plist = format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{bin}</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key><false/>
    </dict>
    <key>ThrottleInterval</key><integer>10</integer>
    <key>StandardOutPath</key><string>{log}</string>
    <key>StandardErrorPath</key><string>{log}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key><string>{home}</string>
        <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>"#,
        label = SERVICE_LABEL,
        bin = bin.display(),
        log = log.display(),
        home = home.display(),
    );
    if let Some(parent) = plist_path.parent() {
        fs::create_dir_all(parent).ok();
    }
    fs::write(&plist_path, plist).context("Plist konnte nicht geschrieben werden")?;
    // Re-laden — idempotent.
    let _ = std::process::Command::new("launchctl")
        .args(["unload", plist_path.to_str().unwrap()])
        .status();
    std::process::Command::new("launchctl")
        .args(["load", "-w", plist_path.to_str().unwrap()])
        .status()
        .context("launchctl load fehlgeschlagen")?;
    Ok(())
}

#[cfg(target_os = "windows")]
pub fn ensure_installed(app: &AppHandle) -> Result<()> {
    let bin = daemon_binary(app)?;
    // schtasks /Create /SC ONLOGON /TN <label> /TR "<bin> run" /RL LIMITED /F
    let status = std::process::Command::new("schtasks")
        .args([
            "/Create",
            "/SC",
            "ONLOGON",
            "/TN",
            SERVICE_LABEL,
            "/TR",
            &format!("\"{}\" run", bin.display()),
            "/RL",
            "LIMITED",
            "/F",
        ])
        .status()
        .context("schtasks-Aufruf fehlgeschlagen")?;
    if !status.success() {
        anyhow::bail!("schtasks /Create exit {status}");
    }
    Ok(())
}

#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn ensure_installed(_app: &AppHandle) -> Result<()> {
    // Linux-Pfad ist explizites Non-Ziel im MVP.
    Ok(())
}

#[cfg(target_os = "macos")]
pub fn start() -> Result<()> {
    std::process::Command::new("launchctl")
        .args(["start", SERVICE_LABEL])
        .status()
        .context("launchctl start")?;
    Ok(())
}

#[cfg(target_os = "macos")]
pub fn stop() -> Result<()> {
    std::process::Command::new("launchctl")
        .args(["stop", SERVICE_LABEL])
        .status()
        .context("launchctl stop")?;
    Ok(())
}

#[cfg(target_os = "macos")]
pub fn restart() -> Result<()> {
    stop()?;
    start()
}

#[cfg(target_os = "windows")]
pub fn start() -> Result<()> {
    std::process::Command::new("schtasks")
        .args(["/Run", "/TN", SERVICE_LABEL])
        .status()
        .context("schtasks /Run")?;
    Ok(())
}

#[cfg(target_os = "windows")]
pub fn stop() -> Result<()> {
    std::process::Command::new("schtasks")
        .args(["/End", "/TN", SERVICE_LABEL])
        .status()
        .context("schtasks /End")?;
    Ok(())
}

#[cfg(target_os = "windows")]
pub fn restart() -> Result<()> {
    stop()?;
    start()
}

#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn start() -> Result<()> { Ok(()) }
#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn stop() -> Result<()> { Ok(()) }
#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn restart() -> Result<()> { Ok(()) }

pub fn tail_logs(lines: usize) -> Result<Vec<String>> {
    let path = log_path();
    let f = std::fs::File::open(&path).with_context(|| {
        format!("Log-Datei {} nicht lesbar", path.display())
    })?;
    let reader = BufReader::new(f);
    let all: Vec<String> = reader.lines().filter_map(|l| l.ok()).collect();
    let start = all.len().saturating_sub(lines);
    Ok(all[start..].to_vec())
}

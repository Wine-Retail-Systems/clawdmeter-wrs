//! LaunchAgent / Scheduled Task. Wird beim ersten App-Start angelegt und
//! verweist auf die mitgelieferte PyInstaller-Daemon-Binary aus
//! `resources/daemon/`.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;

use anyhow::{Context, Result};
use tauri::{AppHandle, Manager};

const SERVICE_LABEL: &str = "de.jacques.clawdmeter.daemon";

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

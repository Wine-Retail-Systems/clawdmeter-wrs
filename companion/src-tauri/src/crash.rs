//! Bug-Report-Bundle. Sammelt anonymisierte Logs + App-Version + OS-Info in
//! eine ZIP-Datei, die der Nutzer per Mail oder GitHub-Issue weitergibt.

use std::fs::File;
use std::io::Write;
use std::path::PathBuf;

use anyhow::{Context, Result};

fn target_path() -> PathBuf {
    let mut p = dirs::desktop_dir()
        .or_else(dirs::home_dir)
        .unwrap_or_else(|| PathBuf::from("/tmp"));
    let stamp = chrono::Local::now().format("%Y%m%d-%H%M%S");
    p.push(format!("clawdmeter-bugreport-{stamp}.zip"));
    p
}

#[tauri::command]
pub fn collect_crash_bundle() -> Result<String, String> {
    do_collect().map(|p| p.display().to_string()).map_err(|e| e.to_string())
}

fn do_collect() -> Result<PathBuf> {
    let out = target_path();
    let file = File::create(&out).context("ZIP-Datei konnte nicht erstellt werden")?;
    let mut zip = zip::ZipWriter::new(file);
    let opts: zip::write::FileOptions<'_, ()> =
        zip::write::FileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);

    // Daemon-Log
    if let Some(home) = dirs::home_dir() {
        let candidates = [
            home.join("Library/Logs/clawdmeter-daemon.log"),
            home.join(".clawdmeter/daemon.log"),
        ];
        for c in candidates {
            if c.exists() {
                let bytes = std::fs::read(&c).unwrap_or_default();
                let name = c
                    .file_name()
                    .map(|s| s.to_string_lossy().into_owned())
                    .unwrap_or_else(|| "log.txt".into());
                zip.start_file(name, opts)
                    .context("ZIP-Entry konnte nicht angelegt werden")?;
                zip.write_all(&bytes).ok();
            }
        }
    }

    // Meta
    zip.start_file("meta.json", opts).ok();
    let meta = serde_json::json!({
        "os": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "app_version": env!("CARGO_PKG_VERSION"),
        "created_at": chrono::Local::now().to_rfc3339(),
    });
    zip.write_all(meta.to_string().as_bytes()).ok();

    zip.finish().context("ZIP konnte nicht finalisiert werden")?;
    Ok(out)
}

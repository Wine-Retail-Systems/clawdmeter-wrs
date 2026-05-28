//! IPC-Client zum Python-Daemon. Protokoll: JSON-Lines über Unix-Socket
//! (mac) bzw. Named-Pipe (win). Jeder Request hat eine `id`, jeder Response
//! trägt dieselbe `id`. Events kommen als unsolicited Frames mit `event`-Feld.
//!
//! Vollständige Spezifikation:
//! `feature-documentation/companion-app/ipc-protocol.md`.

use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
#[allow(unused_imports)]
use interprocess::local_socket::{
    tokio::{prelude::*, Stream},
    GenericFilePath, GenericNamespaced, ToFsName, ToNsName,
};
use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ProviderDetectResult {
    pub id: String,
    pub detected: bool,
    pub source: Option<String>,
    pub notes: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone, Default)]
pub struct DaemonStatusReply {
    pub reachable: bool,
    pub running: bool,
    pub device_connected: bool,
    pub last_poll_at: Option<String>,
    pub active_provider: Option<String>,
    pub message: Option<String>,
}

/// Plattformabhängiger Endpoint.
pub fn socket_path() -> PathBuf {
    #[cfg(target_os = "macos")]
    {
        let mut p = dirs::home_dir().expect("HOME nicht ermittelbar");
        p.push("Library/Application Support/clawdmeter/daemon.sock");
        p
    }
    #[cfg(target_os = "windows")]
    {
        PathBuf::from(r"clawdmeter-daemon")
    }
    #[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
    {
        let mut p = dirs::home_dir().expect("HOME nicht ermittelbar");
        p.push(".config/clawdmeter/daemon.sock");
        p
    }
}

static NEXT_ID: AtomicU64 = AtomicU64::new(1);

fn next_id() -> String {
    let n = NEXT_ID.fetch_add(1, Ordering::Relaxed);
    format!("r{n}")
}

async fn connect() -> Result<Stream> {
    #[cfg(target_os = "windows")]
    let sock = socket_path();
    #[cfg(target_os = "windows")]
    let name = sock
        .as_os_str()
        .to_ns_name::<GenericNamespaced>()
        .context("Named-Pipe-Name konnte nicht erzeugt werden")?;
    #[cfg(not(target_os = "windows"))]
    let sock = socket_path();
    #[cfg(not(target_os = "windows"))]
    let name = sock
        .as_path()
        .to_fs_name::<GenericFilePath>()
        .context("Unix-Socket-Pfad konnte nicht erzeugt werden")?;

    let conn = tokio::time::timeout(Duration::from_millis(1500), Stream::connect(name))
        .await
        .map_err(|_| anyhow!("Timeout beim Verbinden zum Daemon-Socket"))?
        .context("Daemon-Socket nicht erreichbar")?;
    Ok(conn)
}

/// Sendet einen einzelnen JSON-Lines-Request und liest die Antwortzeile.
pub async fn request(
    command: &str,
    args: serde_json::Value,
) -> Result<serde_json::Value> {
    let id = next_id();
    let req = serde_json::json!({
        "id": id,
        "command": command,
        "args": args,
    });
    let mut payload = serde_json::to_vec(&req)?;
    payload.push(b'\n');

    let stream = connect().await?;
    let (rx, mut tx) = stream.split();
    tx.write_all(&payload).await.context("write request")?;
    tx.flush().await.ok();

    let mut reader = BufReader::new(rx);
    let mut line = String::new();
    tokio::time::timeout(Duration::from_secs(5), reader.read_line(&mut line))
        .await
        .map_err(|_| anyhow!("Timeout beim Lesen der Daemon-Antwort"))?
        .context("read response")?;

    let resp: serde_json::Value = serde_json::from_str(line.trim())
        .with_context(|| format!("invalid JSON: {line:?}"))?;
    let ok = resp.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
    if !ok {
        let err = resp
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown error");
        return Err(anyhow!("daemon error: {err}"));
    }
    Ok(resp.get("result").cloned().unwrap_or(serde_json::Value::Null))
}

#[tauri::command]
pub async fn provider_detect(
    id: String,
) -> Result<ProviderDetectResult, String> {
    match request("provider-detect", serde_json::json!({ "id": id })).await {
        Ok(v) => serde_json::from_value(v).map_err(|e| e.to_string()),
        Err(_) => Ok(ProviderDetectResult {
            id,
            detected: false,
            source: None,
            notes: Some(
                "Daemon nicht erreichbar. Wurde er installiert und gestartet?"
                    .into(),
            ),
        }),
    }
}

#[tauri::command]
pub async fn provider_save(
    id: String,
    fields: serde_json::Value,
) -> Result<(), String> {
    request(
        "provider-save",
        serde_json::json!({ "id": id, "fields": fields }),
    )
    .await
    .map(|_| ())
    .map_err(|e| e.to_string())
}

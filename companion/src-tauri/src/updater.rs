//! Auto-Update via Tauri-Updater-Plugin. Konfiguration steht in
//! `tauri.conf.json` → `plugins.updater`. Der Signing-Pubkey und ein
//! konkreter Release-Endpoint kommen mit Phase 8.

// Bewusst leer — das Plugin liefert die JS-Surface direkt im Frontend
// (`@tauri-apps/plugin-updater`). Diese Datei existiert als Andockpunkt, falls
// wir später eigene Logik (z. B. Pre-Update-Check für laufenden Daemon)
// einbauen wollen.

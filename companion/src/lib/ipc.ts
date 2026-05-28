// IPC-Wrapper. Sämtliche Rust-Commands sind hier typisiert gebündelt, damit
// Routen nicht direkt gegen das Tauri-API codieren. Mock-Modus aktivieren mit
// VITE_MOCK_IPC=1 — nützlich für UI-Entwicklung ohne laufenden Daemon.

import { invoke } from "@tauri-apps/api/core";

const MOCK = (import.meta as ImportMeta & { env: Record<string, string> }).env
  .VITE_MOCK_IPC === "1";

export type DaemonStatus = {
  reachable: boolean;
  running: boolean;
  device_connected: boolean;
  last_poll_at: string | null;
  active_provider: string | null;
  message: string | null;
  installed: boolean;
  legacy_labels: string[];
};

export type SerialPort = {
  path: string;
  product: string | null;
  manufacturer: string | null;
  vid: number | null;
  pid: number | null;
  is_esp32s3: boolean;
};

export type BoardId = "wine-216" | "standard-216" | "standard-180";

export type FlashProgress = {
  phase: "erase" | "write" | "verify" | "done" | "error";
  bytes_written: number;
  bytes_total: number;
  message: string | null;
};

export type ProviderId =
  | "anthropic"
  | "bedrock"
  | "codex"
  | "langdock"
  | "opencode";

export type ProviderDetectResult = {
  id: ProviderId;
  detected: boolean;
  source: string | null;
  notes: string | null;
};

export type BleDevice = {
  address: string;
  name: string;
  rssi: number | null;
};

// ---------- Daemon ----------

export async function getDaemonStatus(): Promise<DaemonStatus> {
  if (MOCK) {
    return {
      reachable: true,
      running: true,
      device_connected: false,
      last_poll_at: new Date().toISOString(),
      active_provider: "anthropic",
      message: null,
      installed: true,
      legacy_labels: [],
    };
  }
  return invoke<DaemonStatus>("daemon_status");
}

export async function startDaemon(): Promise<void> {
  if (MOCK) return;
  await invoke("daemon_start");
}

export async function stopDaemon(): Promise<void> {
  if (MOCK) return;
  await invoke("daemon_stop");
}

export async function restartDaemon(): Promise<void> {
  if (MOCK) return;
  await invoke("daemon_restart");
}

export async function installDaemonService(): Promise<void> {
  if (MOCK) return;
  await invoke("daemon_install_service");
}

export async function migrateLegacyDaemon(): Promise<void> {
  if (MOCK) return;
  await invoke("daemon_migrate_legacy");
}

export async function tailDaemonLogs(lines: number): Promise<string[]> {
  if (MOCK) return ["[mock] daemon idle"];
  return invoke<string[]>("daemon_tail_logs", { lines });
}

// ---------- Flash ----------

export async function listSerialPorts(): Promise<SerialPort[]> {
  if (MOCK) {
    return [
      {
        path: "/dev/cu.usbmodem101",
        product: "ESP32-S3",
        manufacturer: "Espressif",
        vid: 0x303a,
        pid: 0x1001,
        is_esp32s3: true,
      },
    ];
  }
  return invoke<SerialPort[]>("list_serial_ports");
}

export async function flashFirmware(
  board: BoardId,
  port: string,
): Promise<void> {
  if (MOCK) return;
  await invoke("flash_firmware", { board, port });
}

// ---------- Provider-Setup ----------

export async function detectProvider(
  id: ProviderId,
): Promise<ProviderDetectResult> {
  if (MOCK) {
    return { id, detected: id === "anthropic", source: null, notes: null };
  }
  return invoke<ProviderDetectResult>("provider_detect", { id });
}

export async function saveProvider(
  id: ProviderId,
  fields: Record<string, string>,
): Promise<void> {
  if (MOCK) return;
  await invoke("provider_save", { id, fields });
}

// ---------- BLE ----------

export async function scanBleDevices(timeoutMs: number): Promise<BleDevice[]> {
  if (MOCK) {
    return [{ address: "AA:BB:CC:DD:EE:FF", name: "Clawdmeter", rssi: -54 }];
  }
  return invoke<BleDevice[]>("ble_scan", { timeoutMs });
}

// ---------- Bug-Report ----------

export async function collectCrashBundle(): Promise<string> {
  if (MOCK) return "/tmp/clawdmeter-bundle.zip";
  return invoke<string>("collect_crash_bundle");
}

// OS-Detection für plattform-spezifisches Layout (Traffic-Lights links auf macOS,
// Window-Controls rechts auf Windows). Wir setzen ein data-os Attribut am
// <html>-Element; alles weitere passiert in styles.css via CSS-Variablen.

export type OsName = "macos" | "windows" | "linux" | "unknown";

export function detectOs(): OsName {
  if (typeof navigator === "undefined") return "unknown";
  const platform = (navigator.userAgent || "").toLowerCase();
  if (platform.includes("mac")) return "macos";
  if (platform.includes("win")) return "windows";
  if (platform.includes("linux")) return "linux";
  return "unknown";
}

export function applyOsAttribute(): OsName {
  const os = detectOs();
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-os", os);
  }
  return os;
}

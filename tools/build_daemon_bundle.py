#!/usr/bin/env python3
"""Baut den Clawdmeter-Daemon als single-file PyInstaller-Bundle.

Output landet in `companion/resources/daemon/`:

- macOS-arm64: `clawdmeter-daemon-macos-arm64`
- macOS-x86_64: `clawdmeter-daemon-macos-x64`
- Windows-x64: `clawdmeter-daemon-win-x64.exe`

Cross-Compile ist nicht unterstützt — pro Plattform getrennt ausführen
(GitHub Actions baut alle Targets in einer Matrix). Das ist Phase 1
aus `feature-documentation/companion-app/PLAN.md`.

Höchstes Risiko: `bleak` auf Windows. WinRT-Bindings werden ohne explizite
Hinted Imports manchmal nicht eingepackt. Wir fügen `--collect-all bleak`
plus die WinRT-Submodule defensiv hinzu.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DAEMON_ENTRY = REPO / "daemon" / "clawdmeter_daemon.py"
DAEMON_PKG = REPO / "daemon" / "clawdmeter_daemon"
OUTPUT_DIR = REPO / "companion" / "resources" / "daemon"
WORK_DIR = REPO / "companion" / "build" / "pyinstaller"

HIDDEN_IMPORTS = [
    # bleak — die WinRT-Backend-Pfade müssen wir explizit nennen, sonst zieht
    # PyInstaller sie auf Windows nicht mit
    "bleak.backends.winrt",
    "bleak.backends.winrt.client",
    "bleak.backends.winrt.scanner",
    "bleak.backends.winrt.util",
    "bleak.backends.corebluetooth",
    "bleak.backends.corebluetooth.client",
    "bleak.backends.corebluetooth.scanner",
    # tomli (für Python <3.11) — wir frieren mit aktuellem Python ein, daher
    # auf 3.11+ optional, schadet als hidden-import aber nicht
    "tomli",
    # provider-Module — PyInstaller findet die meisten automatisch, einige
    # werden aber via importlib geladen
    "clawdmeter_daemon.providers.anthropic",
    "clawdmeter_daemon.providers.bedrock",
    "clawdmeter_daemon.providers.codex",
    "clawdmeter_daemon.providers.langdock",
    "clawdmeter_daemon.providers.opencode",
]

COLLECT_ALL = [
    # bleak vollständig — drei `--collect-data` / `--collect-binaries` /
    # `--collect-submodules` in einem Switch
    "bleak",
    "httpx",
]


def target_name() -> str:
    sys_name = platform.system().lower()
    arch = platform.machine().lower()
    if sys_name == "darwin":
        return (
            "clawdmeter-daemon-macos-arm64"
            if arch in ("arm64", "aarch64")
            else "clawdmeter-daemon-macos-x64"
        )
    if sys_name == "windows":
        return "clawdmeter-daemon-win-x64.exe"
    if sys_name == "linux":
        return "clawdmeter-daemon-linux-x64"
    raise SystemExit(f"Nicht unterstütztes OS: {sys_name}")


def ensure_pyinstaller(python: str) -> None:
    proc = subprocess.run(
        [python, "-m", "PyInstaller", "--version"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        print(f"  PyInstaller {proc.stdout.strip()}")
        return
    print("[install] pyinstaller fehlt — installiere …")
    subprocess.check_call(
        [python, "-m", "pip", "install", "--quiet", "pyinstaller>=6.10"]
    )


def ensure_daemon_deps(python: str) -> None:
    """Installiert die Runtime-Deps des Daemons in die aktuelle Python-Env."""
    deps = ["bleak>=0.22", "httpx>=0.27"]
    if sys.version_info < (3, 11):
        deps.append("tomli>=2.0")
    print(f"[install] daemon-deps: {', '.join(deps)}")
    subprocess.check_call(
        [python, "-m", "pip", "install", "--quiet", *deps]
    )


def build(python: str, *, clean: bool) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    out_name = target_name()
    dist_dir = WORK_DIR / "dist"
    spec_dir = WORK_DIR / "spec"
    build_dir = WORK_DIR / "build"

    if clean:
        for d in (dist_dir, spec_dir, build_dir):
            shutil.rmtree(d, ignore_errors=True)

    cmd = [
        python, "-m", "PyInstaller",
        "--onefile",
        "--noconfirm",
        "--name", Path(out_name).stem,
        "--paths", str(REPO / "daemon"),
        "--workpath", str(build_dir),
        "--distpath", str(dist_dir),
        "--specpath", str(spec_dir),
    ]
    for hi in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", hi]
    for ca in COLLECT_ALL:
        cmd += ["--collect-all", ca]
    cmd.append(str(DAEMON_ENTRY))

    print(f"[build] {' '.join(cmd)}")
    subprocess.check_call(cmd)

    # PyInstaller hängt auf Windows .exe an, auf Unix nicht — wir vereinheitlichen
    # zu out_name (mit oder ohne .exe), abhängig von der Plattform.
    produced = dist_dir / Path(out_name).stem
    if platform.system().lower() == "windows":
        produced = dist_dir / (Path(out_name).stem + ".exe")
    if not produced.exists():
        raise SystemExit(f"PyInstaller hat keine Binary erzeugt: {produced}")

    final = OUTPUT_DIR / out_name
    shutil.copy2(produced, final)
    final.chmod(0o755)
    print(f"[done] {final}")
    return final


def smoke_test(binary: Path) -> None:
    """Ein Mini-Smoke: `--help` startet ohne Crash."""
    print(f"[smoke] {binary} doctor")
    try:
        proc = subprocess.run(
            [str(binary), "doctor"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        print(f"  exit={proc.returncode}")
        if proc.stdout:
            print("  stdout:", proc.stdout[:400].replace("\n", " | "))
        if proc.stderr:
            print("  stderr:", proc.stderr[:400].replace("\n", " | "))
    except subprocess.TimeoutExpired:
        print("  [warn] doctor hängt — vermutlich blockt es auf Netzwerk-IO.")
    except Exception as exc:
        print(f"  [warn] smoke übersprungen: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true", help="Build-Cache vor Bau leeren")
    ap.add_argument("--python", default=sys.executable, help="Python für den Build")
    ap.add_argument("--skip-deps", action="store_true", help="pip-install überspringen")
    ap.add_argument("--skip-smoke", action="store_true", help="Smoke-Test überspringen")
    args = ap.parse_args()

    if not DAEMON_ENTRY.exists():
        print(f"Daemon-Entry nicht gefunden: {DAEMON_ENTRY}", file=sys.stderr)
        return 2
    if not DAEMON_PKG.is_dir():
        print(f"Daemon-Paket fehlt: {DAEMON_PKG}", file=sys.stderr)
        return 2

    print(f"[env] python={args.python}")
    print(f"[env] platform={platform.system()} {platform.machine()}")
    print(f"[env] daemon={DAEMON_ENTRY}")
    print(f"[env] out_dir={OUTPUT_DIR}")

    if not args.skip_deps:
        ensure_pyinstaller(args.python)
        ensure_daemon_deps(args.python)
    binary = build(args.python, clean=args.clean)
    if not args.skip_smoke:
        smoke_test(binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

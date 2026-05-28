#!/usr/bin/env python3
"""Kopiert die PlatformIO-Factory-Images in `companion/resources/firmware/`.

Wir nehmen ``firmware.factory.bin`` (nicht ``firmware.bin``), weil das die
gemergte Variante ist: Bootloader @ 0x0 + Partition-Table @ 0x8000 +
App @ 0x10000 in einer Datei, paddinggerecht. Die Companion-App schreibt
diese Datei mit espflash an Flash-Offset 0x0 — ein frisch geflashtes Gerät
bootet damit aus dem Stand. Das normale ``firmware.bin`` (nur App-Image)
liefe als 0x0-Write den Bootloader-Bereich tot.

Erwartet, dass die PlatformIO-Envs ``wine-216``, ``standard-216`` und
``standard-180`` bereits gebaut wurden (siehe ``firmware/platformio.ini``).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "firmware" / ".pio" / "build"
DST = REPO / "companion" / "resources" / "firmware"

ENVS = ["wine-216", "standard-216", "standard-180"]


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    missing: list[str] = []
    for env in ENVS:
        bin_path = SRC / env / "firmware.factory.bin"
        if not bin_path.exists():
            missing.append(env)
            continue
        out = DST / f"{env}.bin"
        shutil.copy2(bin_path, out)
        print(f"  ok  {env}  → {out}")
    if missing:
        print(
            "\nFehlende Factory-Builds: "
            + ", ".join(missing)
            + "\nBitte zuerst bauen, z. B. `pio run -d firmware -e wine-216`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

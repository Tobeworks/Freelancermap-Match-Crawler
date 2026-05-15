#!/usr/bin/env python3
"""
Installationsscript für Freelancermap Match Crawler.
Ausführen: python install.py
"""

import subprocess
import sys
import os


def run(cmd, description):
    print(f"\n>> {description}")
    print(f"   {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"   FEHLER (Exit-Code {result.returncode})")
        sys.exit(result.returncode)
    print(f"   OK")


def main():
    print("=" * 55)
    print("  Freelancermap Match Crawler – Installation")
    print("=" * 55)

    pip = [sys.executable, "-m", "pip"]

    run(
        pip + ["install", "--upgrade", "pip", "--break-system-packages"],
        "pip aktualisieren",
    )

    req = os.path.join(os.path.dirname(__file__), "requirements.txt")
    run(
        pip + ["install", "-r", req, "--break-system-packages"],
        "Python-Pakete installieren (requirements.txt)",
    )

    run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        "Playwright Chromium-Browser installieren",
    )

    run(
        [sys.executable, "-m", "playwright", "install-deps", "chromium", "--break-system-packages"],
        "Playwright System-Abhängigkeiten installieren (nur Linux)",
    ) if sys.platform.startswith("linux") else None

    print("\n" + "=" * 55)
    print("  Installation abgeschlossen!")
    print("  Starten mit: python ui.py")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()

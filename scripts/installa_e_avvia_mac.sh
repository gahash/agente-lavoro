#!/bin/bash
# Installa Python 3.12 (installer ufficiale python.org, Intel/universal2) se manca,
# poi installa le librerie in .venv-mac e avvia Agente Lavoro.
# Uso:  bash ~/Desktop/Missionework/scripts/installa_e_avvia_mac.sh
# Ti verrà chiesta UNA volta la password del Mac (serve a macOS per installare Python).
set -euo pipefail
QUI="$(cd "$(dirname "$0")" && pwd)"
VER=3.12.10                                   # ultima 3.12 con installer macOS ufficiale
PKG="/tmp/python-$VER-macos11.pkg"
URL="https://www.python.org/ftp/python/$VER/python-$VER-macos11.pkg"

if ! command -v python3.12 >/dev/null 2>&1 && [ ! -x /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 ]; then
  echo "⬇︎  Scarico Python $VER da python.org…"
  curl -fL --progress-bar -o "$PKG" "$URL"
  echo "🔏 Verifico la firma dell'installer…"
  pkgutil --check-signature "$PKG" | grep -q "Python Software Foundation" \
    || { echo "❌ Firma non valida: mi fermo."; exit 1; }
  echo "🔑 Installo Python (macOS chiede la password del Mac)…"
  sudo installer -pkg "$PKG" -target /
  rm -f "$PKG"
  CERT="/Applications/Python 3.12/Install Certificates.command"
  [ -f "$CERT" ] && bash "$CERT" >/dev/null 2>&1 || true
fi
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"
echo "✅ $(python3.12 --version)"

exec bash "$QUI/avvia_mac.sh" --si

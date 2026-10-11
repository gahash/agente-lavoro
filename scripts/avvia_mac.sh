#!/bin/bash
# Avvia Agente Lavoro dal codice sorgente su macOS (Intel).
# Uso:  bash ~/Desktop/Missionework/scripts/avvia_mac.sh
# - Non tocca la vecchia .venv di Windows: usa un ambiente separato .venv-mac
# - Al primo avvio chiede conferma prima di installare le librerie Python (solo dentro .venv-mac)
set -euo pipefail
cd "$(dirname "$0")/.."
PROGETTO="$PWD"
VENV="$PROGETTO/.venv-mac"

# 1. Trova un Python >= 3.10 (il Python di sistema di macOS è 3.9: troppo vecchio)
PY=""
for c in python3.12 python3.11 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    PY=$(command -v "$c"); break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Serve Python 3.11 o 3.12. Non l'ho trovato."
  echo "   Installa da https://www.python.org/downloads/macos/  (oppure: brew install python@3.12)"
  exit 1
fi
echo "✅ Python: $PY ($("$PY" --version 2>&1))"

# 2. Ambiente virtuale dedicato al Mac (solo al primo avvio)
if [ ! -x "$VENV/bin/python" ]; then
  echo
  echo "Primo avvio: creo $VENV e installo le librerie di requirements.txt"
  echo "(esclusi pyinstaller e pywebview, non necessari per l'avvio: l'app si apre nel browser)."
  if [ "${1:-}" = "--si" ]; then ok=s; else read -r -p "Procedo? [s/N] " ok; fi
  [[ "$ok" =~ ^[sS]$ ]] || { echo "Annullato. Nulla è stato installato."; exit 0; }
  "$PY" -m venv "$VENV"
  grep -viE '^(pyinstaller|pywebview)' requirements.txt > "$VENV/requirements-mac.txt"
  "$VENV/bin/python" -m pip install -q --upgrade pip
  "$VENV/bin/python" -m pip install -r "$VENV/requirements-mac.txt"
fi

# 3. Ollama (non bloccante: l'app parte comunque, le funzioni AI restano in attesa)
if curl -s --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
  echo "✅ Ollama in esecuzione. Modelli: $(curl -s http://127.0.0.1:11434/api/tags | "$VENV/bin/python" -c 'import sys,json;print(", ".join(m["name"] for m in json.load(sys.stdin)["models"]) or "nessuno")')"
else
  echo "⚠️  Ollama non risponde su 127.0.0.1:11434: avvia l'app Ollama per usare le funzioni AI."
fi

# 4. Avvio (server solo su 127.0.0.1; si apre il browser)
echo "▶︎ Avvio Agente Lavoro… (Ctrl+C per fermarlo)"
exec "$VENV/bin/python" -m app.main

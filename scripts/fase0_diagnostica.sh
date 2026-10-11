#!/bin/bash
# FASE 0 — Diagnostica Mac (SOLA LETTURA: non installa, non modifica nulla)
# Uso:  bash ~/Desktop/Missionework/scripts/fase0_diagnostica.sh
# Scrive il risultato in ~/Desktop/Missionework/reports/fase0-diagnostica.txt

OUT="$HOME/Desktop/Missionework/reports/fase0-diagnostica.txt"
mkdir -p "$(dirname "$OUT")"
{
echo "== Data"; date
echo; echo "== macOS"; sw_vers
echo; echo "== Hardware"
sysctl -n machdep.cpu.brand_string
echo "Architettura: $(uname -m)"
echo "Core fisici: $(sysctl -n hw.physicalcpu)  Core logici: $(sysctl -n hw.logicalcpu)"
echo "RAM totale GB: $(( $(sysctl -n hw.memsize) / 1073741824 ))"
system_profiler SPHardwareDataType 2>/dev/null | grep -E "Model Name|Model Identifier|Memory:"
system_profiler SPDisplaysDataType 2>/dev/null | grep -E "Chipset Model|VRAM|Metal"
echo; echo "== Istruzioni CPU (AVX/AVX2/FMA/F16C/AVX512)"
sysctl -n machdep.cpu.features machdep.cpu.leaf7_features 2>/dev/null | tr ' ' '\n' | grep -E '^(AVX1\.0|AVX2|FMA|F16C|AVX512F|SSE4\.2)$' | tr '\n' ' '; echo
echo; echo "== Memoria in uso"; vm_stat | head -8; memory_pressure 2>/dev/null | tail -1
echo; echo "== Disco"; df -h / "$HOME"
echo; echo "== Strumenti"
for t in brew python3 python3.11 python3.12 pip3 git gh ollama node npm sqlite3 gitleaks ruff docker; do
  p=$(command -v $t 2>/dev/null); printf "%-10s %s\n" "$t" "${p:-NON TROVATO}"
done
python3 --version 2>&1; git --version 2>&1; node --version 2>&1
xcode-select -p 2>&1
brew --version 2>/dev/null | head -1
echo; echo "== Ollama"
ollama --version 2>&1
ollama list 2>&1
curl -s --max-time 3 http://127.0.0.1:11434/api/version || echo "Server Ollama non in ascolto su 11434"
ls -la "$HOME/.ollama" 2>&1 | head
du -sh "$HOME/.ollama/models" 2>/dev/null
echo; echo "== Porta 8000"; lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null || echo "libera"
echo; echo "== LaunchAgents utente"; ls "$HOME/Library/LaunchAgents" 2>&1
echo; echo "== Directory progetto"; ls -ld "$HOME/agente-lavoro" "$HOME/Desktop/Missionework" 2>&1
echo; echo "== Sicurezza"; fdesetup status 2>&1; spctl --status 2>&1; csrutil status 2>&1
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>&1
} > "$OUT" 2>&1
echo "Fatto. Risultato salvato in: $OUT"

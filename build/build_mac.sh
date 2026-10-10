#!/bin/bash
# Crea "Agente Lavoro.app" e il disco di installazione AgenteLavoro-<versione>-macos-intel.dmg.
# Uso (su un Mac, dalla cartella del progetto):  bash build/build_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=${PY:-python3}
VERSIONE=$("$PY" -c "import re;print(re.search(r'VERSION = \"(.+)\"', open('app/core/config.py').read()).group(1))")
ARCH=$(uname -m)                       # x86_64 su iMac Intel

"$PY" -m pip install -q -r requirements.txt
"$PY" build/crea_icona.py

"$PY" -m PyInstaller --noconfirm --clean --windowed \
  --name "AgenteLavoro" \
  --icon "$PWD/build/icona.ico" \
  --osx-bundle-identifier "it.gasparepettinati.agentelavoro" \
  --distpath dist --workpath build/tmp --specpath build/tmp \
  --add-data "$PWD/app/ui:ui" \
  --collect-all playwright \
  --collect-submodules uvicorn \
  --hidden-import keyring.backends.macOS \
  --hidden-import websockets.sync.client \
  --collect-all webview \
  "$PWD/app/main.py"

# nome leggibile nel Finder e nel Dock
rm -rf "dist/Agente Lavoro.app"
mv "dist/AgenteLavoro.app" "dist/Agente Lavoro.app"
/usr/libexec/PlistBuddy -c "Set :CFBundleName Agente Lavoro" "dist/Agente Lavoro.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string Agente Lavoro" "dist/Agente Lavoro.app/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSIONE" "dist/Agente Lavoro.app/Contents/Info.plist"
# firma "ad hoc" (senza certificato Apple): necessaria perché macOS avvii l'app
codesign --force --deep --sign - "dist/Agente Lavoro.app"

# disco di installazione: trascina l'app in Applicazioni
DMG="release/AgenteLavoro-$VERSIONE-macos-$ARCH.dmg"
mkdir -p release
rm -rf build/dmg "$DMG"
mkdir -p build/dmg
cp -R "dist/Agente Lavoro.app" build/dmg/
ln -s /Applications build/dmg/Applicazioni
cp build/LEGGIMI-mac.txt build/dmg/
hdiutil create -volname "Agente Lavoro" -srcfolder build/dmg -ov -format UDZO "$DMG"
echo "OK: $DMG"

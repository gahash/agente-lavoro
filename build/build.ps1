# Crea l'eseguibile "Agente Lavoro" e il collegamento sul Desktop.
# Uso:  powershell -ExecutionPolicy Bypass -File build\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root ".venv\Scripts\python.exe"
Set-Location $root

& $py -m pip install -q pillow
& $py build\crea_icona.py

& $py -m PyInstaller --noconfirm --clean --windowed `
  --name "AgenteLavoro" `
  --icon "$root\build\icona.ico" `
  --distpath dist --workpath build\tmp --specpath build\tmp `
  --add-data "$root\app\ui;ui" `
  --collect-all playwright `
  --collect-submodules uvicorn `
  --hidden-import keyring.backends.Windows `
  --collect-all webview `
  "$root\app\main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallito" }

$exe = Join-Path $root "dist\AgenteLavoro\AgenteLavoro.exe"
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Agente Lavoro.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $exe; $s.WorkingDirectory = Split-Path $exe; $s.IconLocation = "$exe,0"
$s.Description = "Agente Lavoro - Gaspare Pettinati"; $s.Save()
# Chrome dedicato (stesso profilo usato dall'app): il browser di tutti i giorni, con l'account Google sincronizzato
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) {
  $profilo = Join-Path $env:USERPROFILE "AgenteLavoro\dati\profilo-browser"
  New-Item -ItemType Directory -Force $profilo | Out-Null
  $c = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Chrome (Agente Lavoro).lnk"))
  $c.TargetPath = $chrome
  $c.Arguments = "--user-data-dir=`"$profilo`" --remote-debugging-port=9333 --remote-debugging-address=127.0.0.1 --no-first-run --no-default-browser-check"
  $c.IconLocation = "$chrome,0"; $c.Description = "Chrome usato da Agente Lavoro"; $c.Save()
  Write-Host "Collegamento Chrome creato"
}
Write-Host "OK: $exe"
Write-Host "Collegamento: $lnk"

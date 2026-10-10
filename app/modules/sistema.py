"""Integrazione con il sistema: collegamenti, avvio automatico, apertura di file (Windows e macOS)."""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

NOME = "Agente Lavoro"
MAC = sys.platform == "darwin"
LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "it.gasparepettinati.agentelavoro.plist"


def _exe() -> Path | None:
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def _app_mac() -> Path | None:
    """Il pacchetto .app che contiene l'eseguibile (…/Agente Lavoro.app/Contents/MacOS/AgenteLavoro)."""
    exe = _exe()
    if exe and exe.parent.name == "MacOS" and exe.parents[2].suffix == ".app":
        return exe.parents[2]
    return None


def apri(percorso: str | Path) -> None:
    """Apre un file o una cartella con l'app predefinita del sistema."""
    if hasattr(os, "startfile"):
        os.startfile(percorso)
    elif MAC:
        subprocess.Popen(["open", str(percorso)])
    else:
        subprocess.Popen(["xdg-open", str(percorso)])


# ---------------------------------------------------------------- Windows
def _startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def crea_collegamento(dest: Path, target: Path) -> None:
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{dest}');"
          f"$s.TargetPath='{target}';$s.WorkingDirectory='{target.parent}';"
          f"$s.IconLocation='{target},0';$s.Description='{NOME}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ---------------------------------------------------------------- avvio automatico
def avvio_automatico_attivo() -> bool:
    if MAC:
        return LAUNCH_AGENT.exists()
    return (_startup_dir() / f"{NOME}.lnk").exists()


def _imposta_mac(attivo: bool) -> dict:
    if not attivo:
        LAUNCH_AGENT.unlink(missing_ok=True)
        return {"ok": True, "attivo": False}
    app = _app_mac()
    if not app:
        return {"ok": False, "errore": "Disponibile solo dall'app installata."}
    LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT.write_bytes(plistlib.dumps({
        "Label": LAUNCH_AGENT.stem,
        "ProgramArguments": ["/usr/bin/open", "-a", str(app)],
        "RunAtLoad": True,
    }))
    return {"ok": True, "attivo": True}


def imposta_avvio_automatico(attivo: bool) -> dict:
    if MAC:
        return _imposta_mac(attivo)
    lnk = _startup_dir() / f"{NOME}.lnk"
    if not attivo:
        lnk.unlink(missing_ok=True)
        return {"ok": True, "attivo": False}
    exe = _exe()
    if not exe:
        return {"ok": False, "errore": "Disponibile solo dall'eseguibile."}
    crea_collegamento(lnk, exe)
    return {"ok": True, "attivo": True}

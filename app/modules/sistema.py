"""Integrazione con Windows: collegamenti sul Desktop e avvio automatico."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NOME = "Agente Lavoro"


def _exe() -> Path | None:
    return Path(sys.executable) if getattr(sys, "frozen", False) else None


def _startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def crea_collegamento(dest: Path, target: Path) -> None:
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{dest}');"
          f"$s.TargetPath='{target}';$s.WorkingDirectory='{target.parent}';"
          f"$s.IconLocation='{target},0';$s.Description='{NOME}';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def avvio_automatico_attivo() -> bool:
    return (_startup_dir() / f"{NOME}.lnk").exists()


def imposta_avvio_automatico(attivo: bool) -> dict:
    lnk = _startup_dir() / f"{NOME}.lnk"
    if not attivo:
        lnk.unlink(missing_ok=True)
        return {"ok": True, "attivo": False}
    exe = _exe()
    if not exe:
        return {"ok": False, "errore": "Disponibile solo dall'eseguibile."}
    crea_collegamento(lnk, exe)
    return {"ok": True, "attivo": True}

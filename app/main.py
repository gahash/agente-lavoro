"""Avvio di Agente Lavoro: server locale + finestra desktop."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

if __package__ in (None, ""):                      # avvio da eseguibile / script
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "app"

import uvicorn

from app.api import app as api_app
from app.core import db
from app.core.config import APP_NAME, LOGS
from app.modules import pianificatore


def porta_libera(preferita: int = 0) -> int:
    """La porta preferita (8000: serve al segnalibro del tuo Chrome) se libera, altrimenti una a caso."""
    for p in ((preferita, 0) if preferita else (0,)):
        try:
            with socket.socket() as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                return s.getsockname()[1]
        except OSError:
            continue
    raise OSError("Nessuna porta libera")


def chiudi_istanze_precedenti(attesa: float = 6.0) -> None:
    """Chiude le copie di Agente Lavoro già in esecuzione da questa cartella (anche su altre porte),
    così resta una sola app, con un solo pianificatore, sempre su 127.0.0.1:8000."""
    if sys.platform != "darwin":
        return
    import signal
    import subprocess
    try:
        out = subprocess.run(["/usr/bin/pgrep", "-U", str(os.getuid()), "-f", r"[Pp]ython.*-m app\.main"],
                             capture_output=True, text=True, timeout=5).stdout.split()
    except Exception:
        return
    qui = os.path.realpath(os.getcwd())
    chiusi = []
    for pid in map(int, out):
        if pid in (os.getpid(), os.getppid()):
            continue
        try:
            cwd = subprocess.run(["/usr/sbin/lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                                 capture_output=True, text=True, timeout=5).stdout
            if any(r[1:] and os.path.realpath(r[1:]) == qui for r in cwd.splitlines() if r.startswith("n")):
                os.kill(pid, signal.SIGTERM)
                chiusi.append(pid)
        except Exception:
            continue
    fine = time.time() + attesa
    while chiusi and time.time() < fine:
        chiusi = [p for p in chiusi if _vivo(p)]
        time.sleep(0.2)


def _vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    if getattr(sys, "frozen", False) and sys.stdout is None:   # exe senza console
        f = open(LOGS / "app.log", "a", encoding="utf-8")
        sys.stdout = sys.stderr = f
    chiudi_istanze_precedenti()
    db.init()
    pianificatore.avvia()
    pianificatore.recupero_avvio()
    from app.core import llm
    llm.assicura_modello_in_background()
    porta = porta_libera(int(os.environ.get("AGENTE_PORTA", "8000")))
    cfg = uvicorn.Config(api_app, host="127.0.0.1", port=porta, log_level="warning", log_config=None)
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    url = f"http://127.0.0.1:{porta}/"
    db.log("app", f"Avviata su {url}")
    try:
        import webview
        webview.create_window(APP_NAME, url, width=1360, height=880, min_size=(1000, 650))
        webview.start()
    except Exception as e:
        db.log("app", f"Finestra nativa non disponibile ({e}); apro il browser.")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    server.should_exit = True


if __name__ == "__main__":
    main()

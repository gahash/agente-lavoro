"""Avvio di Agente Lavoro: server locale + finestra desktop."""
from __future__ import annotations

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


def porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    if getattr(sys, "frozen", False) and sys.stdout is None:   # exe senza console
        f = open(LOGS / "app.log", "a", encoding="utf-8")
        sys.stdout = sys.stderr = f
    db.init()
    pianificatore.avvia()
    pianificatore.recupero_avvio()
    porta = porta_libera()
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

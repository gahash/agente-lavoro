"""Il browser di Gaspare: un Chrome normale con un profilo dedicato (dati/profilo-browser).

Gaspare vi accede con il suo account Google e attiva la sincronizzazione: ritrova password,
segnalibri e accessi, e da lì entra in LinkedIn, Indeed, gestionale e tutto il resto.
L'app avvia Chrome come un normale programma (porta di controllo solo su 127.0.0.1) e vi si
collega con Playwright. Chiudendo il collegamento, Chrome resta aperto: è il suo browser.
Playwright è single-thread: tutte le operazioni passano da un unico thread di lavoro.
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
from concurrent.futures import Future
from pathlib import Path

import httpx

from ..core import db
from ..core.config import BROWSER_PROFILE, load_settings

PORTA = 9333


def trova_browser() -> str | None:
    canale = load_settings().get("browser_canale", "chrome")
    pf, pf86, local = os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("LOCALAPPDATA", "")
    candidati = {
        "chrome": [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
                   rf"{local}\Google\Chrome\Application\chrome.exe"],
        "msedge": [rf"{pf86}\Microsoft\Edge\Application\msedge.exe", rf"{pf}\Microsoft\Edge\Application\msedge.exe"],
    }
    for p in candidati.get(canale, []) + candidati["chrome"] + candidati["msedge"]:
        if p and Path(p).exists():
            return p
    return None


def comando_browser(url: str = "") -> list[str]:
    exe = trova_browser()
    if not exe:
        raise RuntimeError("Chrome/Edge non trovato sul computer.")
    cmd = [exe, f"--user-data-dir={BROWSER_PROFILE}", f"--remote-debugging-port={PORTA}",
           "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check", "--start-maximized"]
    return cmd + ([url] if url else [])


def _cdp_attivo() -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{PORTA}/json/version", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        return False


def avvia_browser(url: str = "") -> None:
    """Apre il Chrome dell'app (se non è già aperto)."""
    if _cdp_attivo():
        return
    subprocess.Popen(comando_browser(url), creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(60):
        if _cdp_attivo():
            return
        time.sleep(0.5)
    raise RuntimeError("Chrome non risponde. Se il profilo dell'app è già aperto senza collegamento, chiudilo e riprova.")


class _Worker:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.t: threading.Thread | None = None
        self.ctx = None
        self.browser = None
        self.pw = None

    def _loop(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        while True:
            fn, fut = self.q.get()
            if fn is None:
                break
            try:
                fut.set_result(fn())
            except Exception as e:
                fut.set_exception(e)
        try:
            self.scollega()
            self.pw.stop()
        except Exception:
            pass

    def scollega(self):
        """Stacca l'app dal browser senza chiuderlo."""
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        self.browser = self.ctx = None

    def run(self, fn, timeout=180):
        if not self.t or not self.t.is_alive():
            self.t = threading.Thread(target=self._loop, daemon=True, name="browser")
            self.t.start()
        fut: Future = Future()
        self.q.put((fn, fut))
        return fut.result(timeout=timeout)

    def context(self):
        if self.ctx and self.browser and self.browser.is_connected() and _cdp_attivo():
            return self.ctx
        self.scollega()
        avvia_browser()
        self.browser = self.pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA}")
        self.ctx = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        return self.ctx

    def page(self):
        ctx = self.context()
        pages = [p for p in ctx.pages if not p.is_closed()]
        return pages[-1] if pages else ctx.new_page()


W = _Worker()


def apri(url: str) -> dict:
    def f():
        p = W.page()
        p.goto(url, wait_until="domcontentloaded", timeout=60000)
        p.bring_to_front()
        return {"ok": True, "url": p.url, "titolo": p.title()}
    return W.run(f)


def leggi_pagina() -> dict:
    def f():
        p = W.page()
        testo = p.evaluate("() => document.body ? document.body.innerText : ''")
        return {"url": p.url, "titolo": p.title(), "testo": re.sub(r"\n{3,}", "\n\n", testo)[:20000]}
    return W.run(f)


def chiudi() -> dict:
    """Stacca l'app dal browser: Chrome resta aperto e utilizzabile normalmente."""
    W.run(W.scollega)
    return {"ok": True}


def collega_google() -> dict:
    """Apre la pagina di accesso Google nel Chrome dell'app: Gaspare accede e attiva la sincronizzazione."""
    def f():
        p = W.context().new_page()
        p.goto("https://accounts.google.com/", wait_until="domcontentloaded", timeout=60000)
        p.bring_to_front()
        connesso = "myaccount.google.com" in p.url
        return {"ok": True, "collegato": connesso,
                "messaggio": ("Account Google già collegato ✅ — controlla che la sincronizzazione di Chrome sia attiva "
                              "(icona profilo in alto a destra)." if connesso else
                              "Accedi con il tuo account Google nella finestra di Chrome, poi dall'icona del profilo in alto "
                              "a destra scegli 'Attiva sincronizzazione'.")}
    return W.run(f)


def stato_browser() -> dict:
    return {"aperto": _cdp_attivo(), "eseguibile": trova_browser(), "profilo": str(BROWSER_PROFILE)}


# ---------------- gestionale del sito ----------------
# Come per LinkedIn e Indeed: il login lo fa Gaspare a mano una volta ("Resta connesso per 30 giorni"),
# la sessione resta nel profilo del browser dell'app. L'app non conosce la password del gestionale.
def login_crm() -> dict:
    """Apre il gestionale: se la sessione è attiva mostra la dashboard, altrimenti la pagina di login."""
    s = load_settings()

    def f():
        p = W.page()
        p.goto(s["crm_url_lead"] or s["crm_url_login"], wait_until="domcontentloaded", timeout=60000)
        p.bring_to_front()
        if p.locator("input[type=password]:visible").count():
            return {"ok": True, "collegato": False, "url": p.url,
                    "messaggio": "Accedi al gestionale nella finestra del browser (spunta 'Resta connesso'), poi premi 'Verifica'."}
        return {"ok": True, "collegato": True, "url": p.url, "titolo": p.title(), "menu": _menu(p)}
    r = W.run(f)
    db.log("crm", "Gestionale " + ("collegato" if r.get("collegato") else "in attesa di login"))
    return r


def crm_collegato() -> bool:
    """Controlla la sessione in una scheda separata, senza disturbare la pagina aperta."""
    s = load_settings()

    def f():
        p = W.context().new_page()
        try:
            p.goto(s["crm_url_lead"] or s["crm_url_login"], wait_until="domcontentloaded", timeout=60000)
            return p.locator("input[type=password]:visible").count() == 0
        finally:
            p.close()
    return W.run(f)


def _menu(p) -> list[dict]:
    return p.evaluate("""() => {
      const out = [], seen = new Set();
      for (const a of document.querySelectorAll('nav a, aside a, .sidebar a, .menu a, header a')) {
        const t = (a.innerText || '').trim(); const h = a.href;
        if (t && h && !seen.has(h) && !h.startsWith('javascript')) { seen.add(h); out.push({testo: t.slice(0,60), url: h}); }
      }
      return out.slice(0, 60);
    }""")


def leggi_tabelle(url: str | None = None) -> dict:
    """Legge le tabelle della pagina del gestionale (lead, clienti, preventivi...)."""
    def f():
        p = W.page()
        if url:
            p.goto(url, wait_until="domcontentloaded", timeout=60000)
            if p.locator("input[type=password]:visible").count():
                return {"ok": False, "errore": "Sessione scaduta: premi 'Accedi al gestionale'."}
        tabelle = p.evaluate("""() => [...document.querySelectorAll('table')].map(t => {
            const head = [...t.querySelectorAll('thead th, tr:first-child th')].map(th => th.innerText.trim());
            const rows = [...t.querySelectorAll('tbody tr')].map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim().slice(0,200)));
            return {intestazioni: head, righe: rows.filter(r => r.length).slice(0, 500)};
        }).filter(t => t.righe.length)""")
        return {"ok": True, "url": p.url, "titolo": p.title(), "tabelle": tabelle, "menu": _menu(p)}
    r = W.run(f)
    if r.get("ok"):
        for t in r["tabelle"]:
            for riga in t["righe"]:
                rec = dict(zip(t["intestazioni"] or [f"col{i}" for i in range(len(riga))], riga))
                db.insert("lead_crm", {"uid": f"{r['url']}|{'|'.join(riga[:3])}", "dati": db.dumps(rec), "letto": db.now()})
    return r

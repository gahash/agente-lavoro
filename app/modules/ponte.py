"""Ponte con il TUO Chrome (il profilo che usi tutti i giorni, già collegato a Google, LinkedIn, Indeed...).

Chrome non permette ai programmi di comandare il profilo personale (dalla versione 136 il controllo remoto
è bloccato sul profilo predefinito, per sicurezza). Quindi l'app non guida il browser: 
- apre le pagine nel tuo Chrome (open -a "Google Chrome" su macOS);
- tu premi il segnalibro "⭐ Invia ad Agente Lavoro": legge la pagina che stai guardando e la passa all'app
  (http://127.0.0.1/ponte). Nessuna password, nessun cookie: solo il testo visibile della pagina.
"""
from __future__ import annotations

import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlparse

from ..core import db
from ..core.config import load_settings
from . import lavoro, portali

PORTA = 8000
ORIGINE = f"http://127.0.0.1:{PORTA}"   # indirizzo fisso: il segnalibro resta valido a ogni riavvio
VERIFICA_RX = re.compile(r"security check|ulteriore verifica|verify you are human|verifica di essere|captcha|just a moment", re.I)


def personale() -> bool:
    return load_settings().get("browser_modalita", "personale") == "personale"


def apri(url: str) -> dict:
    """Apre l'indirizzo nel Chrome che stai usando (ultimo profilo attivo)."""
    if sys.platform == "darwin":
        chrome = any(Path(p).exists() for p in ("/Applications/Google Chrome.app",
                                                str(Path.home() / "Applications/Google Chrome.app")))
        subprocess.Popen(["open", "-a", "Google Chrome", url] if chrome else ["open", url])
    else:
        webbrowser.open(url)
    db.log("browser", f"Aperto nel tuo Chrome: {url[:200]}")
    return {"ok": True, "url": url}


# ------------------------------------------------------------------ segnalibro
def _js_segnalibro(origine: str) -> str:
    sel_li = ".jobs-search-results-list, .scaffold-layout__list > div, .scaffold-layout__list"
    return ("(async()=>{"
            f"const O={origine!r};const h=location.hostname,pa=location.pathname;"
            "const w=window.open('about:blank','_blank');"
            "const sc=async s=>{for(let i=0;i<6;i++){const el=[...document.querySelectorAll(s)].find(e=>e.scrollHeight>e.clientHeight+20)||document.scrollingElement;el.scrollBy(0,700);await new Promise(r=>setTimeout(r,450));}};"
            "let c=[];try{"
            f"if(/linkedin\\.com$/.test(h)&&pa.startsWith('/jobs/')&&!pa.includes('/jobs/view/')){{await sc({sel_li!r});c=({portali.JS_LINKEDIN})();}}"
            f"else if(/indeed\\./.test(h)&&!pa.includes('viewjob')){{await sc('body');c=({portali.JS_INDEED})();}}"
            "}catch(e){}"
            "const tb=[...document.querySelectorAll('table')].map(t=>({intestazioni:[...t.querySelectorAll('thead th, tr:first-child th')].map(x=>x.innerText.trim()),"
            "righe:[...t.querySelectorAll('tbody tr')].map(r=>[...r.querySelectorAll('td')].map(d=>d.innerText.trim().slice(0,200))).filter(r=>r.length).slice(0,500)})).filter(t=>t.righe.length).slice(0,20);"
            "const p={u:location.href,t:document.title,x:(document.body?document.body.innerText:'').slice(0,15000),c:c.slice(0,200),tb};"
            "const u=O+'/ponte#'+encodeURIComponent(JSON.stringify(p));"
            "if(w){w.location.href=u}else{location.href=u}"
            "})()")


def segnalibro(origine: str) -> str:
    return "javascript:" + quote(_js_segnalibro(origine), safe="")


# ------------------------------------------------------------------ ricezione
def _uid_da_url(url: str) -> str | None:
    m = re.search(r"linkedin\.com/jobs/view/(?:[^/]*-)?(\d{6,})", url) or re.search(r"linkedin\.com/.*[?&]currentJobId=(\d+)", url)
    if m:
        return f"linkedin-{m.group(1)}"
    m = re.search(r"indeed\.[^/]+/.*[?&]v?jk=([0-9a-f]+)", url)
    return f"indeed-{m.group(1)}" if m else None


def ricevi(p: dict) -> dict:
    url = str(p.get("u") or "")[:2000]
    testo = str(p.get("x") or "")[:20000]
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "errore": "Pagina non valida."}
    host = (urlparse(url).hostname or "").lower()
    if VERIFICA_RX.search((str(p.get("t") or "") + " " + testo[:1500])):
        return {"ok": False, "errore": "Il sito chiede una verifica di sicurezza: completala nel tuo Chrome e premi di nuovo il segnalibro."}
    if host.endswith("linkedin.com") and re.search(r"authwall|/login|/checkpoint|signup", url):
        return {"ok": False, "errore": "LinkedIn chiede l'accesso: accedi nel tuo Chrome e riprova."}

    cards = []
    for c in (p.get("c") or [])[:200]:
        if isinstance(c, dict) and c.get("id") and c.get("ruolo"):
            cards.append({k: str(c.get(k) or "")[:500] for k in ("id", "ruolo", "azienda", "luogo", "compenso", "extra")})
    portale = "linkedin" if host.endswith("linkedin.com") else "indeed" if ".indeed." in f".{host}" else None
    if portale and cards:
        r = portali.salva_cards(portale, cards, url)
        r["messaggio"] = f"{r['portale']}: {r['nuovi']} nuovi annunci su {r['letti']} (li trovi in Opportunità lavoro)"
        return r

    tabelle = [t for t in (p.get("tb") or [])[:20] if isinstance(t, dict) and isinstance(t.get("righe"), list)]
    if host.endswith("gasparepettinati.it") and tabelle:
        from .browser import salva_tabelle
        n = salva_tabelle(url, tabelle)
        return {"ok": True, "messaggio": f"Gestionale: {len(tabelle)} tabelle lette, {n} righe salvate."}

    if len(testo.strip()) < 200:
        return {"ok": False, "errore": "La pagina non contiene abbastanza testo da analizzare."}
    uid = _uid_da_url(url)
    esistente = db.q("SELECT * FROM opportunita WHERE uid=?", (uid,)) if uid else []
    if esistente:                                   # annuncio già importato dalla lista: lo rivaluto col testo completo
        o = esistente[0]
        d = lavoro.valuta_testo(testo, o)
        db.update("opportunita", o["id"], d)
        return {"ok": True, "messaggio": f"Annuncio valutato: {o['ruolo']} — punteggio {d.get('punteggio', '–')}"}
    r = lavoro.analizza_testo_annuncio(testo, url)
    if r.get("ok"):
        if uid and r.get("id"):
            db.update("opportunita", r["id"], {"uid": uid})
        r["messaggio"] = f"Annuncio aggiunto: {r.get('ruolo') or 'senza titolo'} — punteggio {r.get('punteggio')}"
    return r


PAGINA = """<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agente Lavoro — ricezione</title><style>
body{font:15px -apple-system,system-ui,sans-serif;background:#0b1220;color:#e5e7eb;max-width:640px;margin:60px auto;padding:0 16px}
h2{margin:0 0 12px}.b{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:15px;cursor:pointer;text-decoration:none;display:inline-block;margin-right:8px}
.s{background:#1f2937}</style></head><body>
<h2>Agente Lavoro</h2><p id="m">Ricezione…</p><p id="a"></p>
<script>
const TOKEN="__TOKEN__";const FIDATI=/(^|\\.)(linkedin\\.com|indeed\\.com|infojobs\\.it|gasparepettinati\\.it)$/;
const m=document.getElementById("m"),a=document.getElementById("a");
let p=null;try{p=JSON.parse(decodeURIComponent(location.hash.slice(1)))}catch(e){}
history.replaceState(null,"",location.pathname);
const fine=()=>{a.innerHTML='<a class="b" href="/">Apri Agente Lavoro</a><button class="b s" onclick="window.close()">Chiudi</button>'};
async function invia(){m.textContent="Elaboro… (se serve l'AI locale può volerci un minuto)";a.innerHTML="";
 try{const r=await fetch("/api/ponte",{method:"POST",headers:{"Content-Type":"application/json","X-Token":TOKEN},body:JSON.stringify(p)});
  const d=await r.json().catch(()=>({}));
  m.textContent=(!r.ok||d.ok===false)?"⚠️ "+(d.detail||d.errore||("Errore "+r.status)):"✅ "+(d.messaggio||"Fatto");
 }catch(e){m.textContent="⚠️ "+e.message}
 fine();}
if(!p||!p.u){m.textContent="Nessun dato ricevuto. Usa il segnalibro «⭐ Invia ad Agente Lavoro» dalla barra dei preferiti di Chrome.";fine();}
else{let host="",ref="";try{host=new URL(p.u).hostname}catch(e){}try{ref=new URL(document.referrer).hostname}catch(e){}
 if(FIDATI.test(host)&&ref===host)invia();
 else{m.textContent="Pagina ricevuta: «"+(p.t||p.u)+"» ("+host+"). Vuoi elaborarla?";a.innerHTML='<button class="b" id="ok">Elabora</button>';document.getElementById("ok").onclick=invia;}}
</script></body></html>"""

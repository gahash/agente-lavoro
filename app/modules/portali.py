"""LinkedIn e Indeed attraverso il browser dell'app.

- Il login lo fa Gaspare a mano, una volta sola (anche con verifica in due passaggi): la sessione resta
  nel profilo del browser dell'app. L'app non conosce né salva le password di questi siti.
- L'app legge solo ciò che è visibile nelle pagine di ricerca, quando lo chiede Gaspare, a ritmo umano.
- Nessun messaggio, collegamento o candidatura viene inviato in automatico (vietato dai termini dei
  portali e rischioso per l'account): i testi si preparano in "Da approvare" e si incollano a mano.
"""
from __future__ import annotations

import random
import re
import time
from urllib.parse import quote_plus

from ..core import db, safety
from ..core.config import load_settings
from . import lavoro
from .browser import W, crm_collegato

PORTALI = {
    "linkedin": {"nome": "LinkedIn", "login": "https://www.linkedin.com/login/it",
                 "home": "https://www.linkedin.com/feed/", "dominio": "linkedin.com", "cookie": {"li_at"}},
    "indeed": {"nome": "Indeed", "login": "https://secure.indeed.com/auth?hl=it_IT&co=IT",
               "home": "https://it.indeed.com/", "dominio": "indeed.com", "cookie": {"SHOE", "SOCK", "PPID"}},
}
REMOTO_RX = re.compile(r"remot|da casa|smart ?working|telelavoro|ibrido|hybrid", re.I)


def url_ricerca(portale: str, parole: str, giorni: int = 3) -> str:
    q = quote_plus(parole)
    if portale == "linkedin":
        # f_WT=2 remoto, f_TPR ultime N ore, ordinati per data
        return (f"https://www.linkedin.com/jobs/search/?keywords={q}&location=Italia&geoId=103350119"
                f"&f_WT=2&f_TPR=r{giorni * 86400}&sortBy=DD")
    return f"https://it.indeed.com/jobs?q={q}&l=Italia&sc=0kf%3Aattr%28DSQF7%29%3B&fromage={giorni}&sort=date"


def collega(portale: str) -> dict:
    p = PORTALI[portale]

    def f():
        pg = W.context().new_page()
        pg.goto(p["home"], wait_until="domcontentloaded", timeout=60000)
        if not _loggato(p):
            pg.goto(p["login"], wait_until="domcontentloaded", timeout=60000)
        pg.bring_to_front()
        return {"ok": True, "collegato": _loggato(p),
                "messaggio": f"Accedi a {p['nome']} nella finestra del browser, poi premi 'Verifica'."}
    return W.run(f)


def _loggato(p: dict) -> bool:
    cookies = W.context().cookies()
    return any(c["name"] in p["cookie"] and p["dominio"] in c["domain"] for c in cookies)


def stato() -> dict:
    def f():
        return {k: _loggato(p) for k, p in PORTALI.items()}
    r = W.run(f)
    try:
        r["gestionale"] = crm_collegato()
    except Exception:
        r["gestionale"] = False
    nomi = {**{k: p["nome"] for k, p in PORTALI.items()}, "gestionale": "Gestionale"}
    db.log("portali", "Collegamenti: " + ", ".join(f"{nomi[k]} {'sì' if v else 'no'}" for k, v in r.items()))
    return r


def apri_ricerca(portale: str, parole: str = "") -> dict:
    s = load_settings()
    parole = parole or s["ricerche_portali"][0]

    def f():
        pg = W.page()
        pg.goto(url_ricerca(portale, parole), wait_until="domcontentloaded", timeout=60000)
        pg.bring_to_front()
        return {"ok": True, "url": pg.url}
    return W.run(f)


# --------------------------------------------------------------- lettura annunci dalla pagina
JS_LINKEDIN = """() => {
  const out = [];
  const cards = document.querySelectorAll('li[data-occludable-job-id], div.job-card-container, li.jobs-search-results__list-item, div.base-card');
  for (const c of cards) {
    const id = c.getAttribute('data-occludable-job-id') || c.getAttribute('data-job-id') ||
               (c.querySelector('[data-job-id]')||{}).getAttribute?.('data-job-id') ||
               ((c.querySelector('a[href*="/jobs/view/"]')||{}).href||'').match(/view\\/(\\d+)/)?.[1];
    const t = s => (c.querySelector(s)?.innerText || '').trim().split('\\n')[0];
    const ruolo = t('.job-card-list__title--link, .job-card-list__title, a.job-card-container__link, .base-search-card__title, strong');
    if (!id || !ruolo) continue;
    out.push({id, ruolo,
      azienda: t('.artdeco-entity-lockup__subtitle, .job-card-container__primary-description, .base-search-card__subtitle'),
      luogo: t('.artdeco-entity-lockup__caption, .job-card-container__metadata-wrapper li, .job-search-card__location'),
      extra: (c.innerText || '').replace(/\\s+/g,' ').slice(0, 400)});
  }
  if (!out.length) {   // riserva: qualunque link ad annuncio, se LinkedIn cambia l'impaginazione
    const seen = new Set();
    for (const a of document.querySelectorAll('a[href*="/jobs/view/"]')) {
      const id = (a.href.match(/view\\/(?:[^/]*-)?(\\d{6,})/) || [])[1];
      if (!id || seen.has(id)) continue; seen.add(id);
      const box = a.closest('li') || a.parentElement;
      const righe = (box.innerText || '').split('\\n').map(s => s.trim()).filter((s, i, a) => s && s !== a[i - 1]);
      out.push({id, ruolo: (a.innerText || righe[0] || '').trim().split('\\n')[0], azienda: righe[1] || '',
                luogo: righe[2] || '', extra: righe.join(' ').slice(0, 400)});
    }
  }
  return out;
}"""

JS_INDEED = """() => {
  const out = [];
  for (const c of document.querySelectorAll('div.job_seen_beacon, td.resultContent, div.cardOutline, li [data-jk]')) {
    const a = c.querySelector('a[data-jk]') || c.closest('[data-jk]') || c.querySelector('[data-jk]');
    const id = a?.getAttribute('data-jk');
    const t = s => (c.querySelector(s)?.innerText || '').trim().split('\\n')[0];
    const ruolo = t('h2.jobTitle span[title], h2.jobTitle, a[data-jk] span');
    if (!id || !ruolo) continue;
    out.push({id, ruolo,
      azienda: t('[data-testid="company-name"], .companyName'),
      luogo: t('[data-testid="text-location"], .companyLocation'),
      compenso: t('[data-testid="attribute_snippet_testid"], .salary-snippet-container, .estimated-salary'),
      extra: (c.innerText || '').replace(/\\s+/g,' ').slice(0, 400)});
  }
  return out;
}"""


def _scorri(pg, portale: str) -> None:
    """Scorre la lista come farebbe una persona, così si caricano tutti gli annunci della pagina."""
    sel = ".jobs-search-results-list, .scaffold-layout__list > div, .scaffold-layout__list" if portale == "linkedin" else "body"
    for _ in range(8):
        try:
            pg.evaluate("""(sel) => { const el = [...document.querySelectorAll(sel)].find(e => e.scrollHeight > e.clientHeight + 20)
                                         || document.scrollingElement; el.scrollBy(0, 700); }""", sel)
        except Exception:
            break
        time.sleep(random.uniform(0.6, 1.3))


def importa_pagina() -> dict:
    """Importa gli annunci visibili nella pagina di ricerca aperta (LinkedIn o Indeed)."""
    def f():
        pg = W.page()
        url = pg.url
        testo_pagina = pg.evaluate("() => (document.title + ' ' + (document.body?.innerText || '').slice(0, 1500))")
        if re.search(r"security check|ulteriore verifica|verify you are human|verifica di essere|captcha|just a moment", testo_pagina, re.I):
            pg.bring_to_front()
            return {"ok": False, "verifica": True,
                    "errore": "Il sito chiede una verifica di sicurezza: completala tu nella finestra del browser, "
                              "poi premi 'Importa annunci dalla pagina'."}
        if "linkedin.com" in url and re.search(r"authwall|/login|/checkpoint|signup", url):
            pg.bring_to_front()
            return {"ok": False, "errore": "LinkedIn non è collegato: premi 'Collega / apri' e accedi."}
        if "linkedin.com" in url:
            portale = "linkedin"
            if "/jobs/" not in url:
                return {"ok": False, "errore": "Apri una pagina di ricerca lavoro di LinkedIn (sezione Lavoro)."}
            _scorri(pg, portale)
            cards = pg.evaluate(JS_LINKEDIN)
        elif "indeed." in url:
            portale = "indeed"
            _scorri(pg, portale)
            cards = pg.evaluate(JS_INDEED)
        else:
            return {"ok": False, "errore": "La pagina aperta non è LinkedIn né Indeed."}
        if not cards and re.search(r"authwall|/login|/checkpoint|signup|secure\.indeed\.com/auth", pg.url):
            pg.bring_to_front()
            return {"ok": False, "errore": f"{'LinkedIn' if portale == 'linkedin' else 'Indeed'} chiede l'accesso: "
                                           "premi 'Collega / apri' e accedi una volta."}
        filtro_remoto = "f_WT=2" in url or "DSQF7" in url     # ricerca già filtrata "da remoto"
        return {"ok": True, "portale": portale, "cards": cards, "filtro_remoto": filtro_remoto}
    r = W.run(f, timeout=240)
    if not r.get("ok"):
        return r
    s = load_settings()
    nuovi = 0
    for c in r["cards"]:
        portale = r["portale"]
        link = (f"https://www.linkedin.com/jobs/view/{c['id']}/" if portale == "linkedin"
                else f"https://it.indeed.com/viewjob?jk={c['id']}")
        testo = f"{c.get('luogo', '')} {c.get('extra', '')}"
        # le ricerche sono già filtrate sull'Italia: "remoto" qui vuol dire remoto dall'Italia
        luogo = c.get("luogo") or "Italia"
        remoto = (f"Sì (Italia · {luogo})" if (r["filtro_remoto"] or REMOTO_RX.search(testo)) else f"No ({luogo})")
        o = {"fonte": PORTALI[portale]["nome"], "uid": f"{portale}-{c['id']}", "azienda": c.get("azienda", ""),
             "ruolo": c["ruolo"], "link": link, "remoto": remoto, "compenso": c.get("compenso", ""), "tipo": "",
             "requisiti": "", "descrizione": c.get("extra", ""), "contatto": ""}
        sosp = safety.segnali_sospetti(testo)
        p, motivi = lavoro.pre_punteggio(o, s)
        motivi.append("da verificare: premi 'Analizza' per leggere l'annuncio completo")
        o.update({"punteggio": 0 if sosp else p, "sospetto": 1 if sosp else 0,
                  "motivazione": ("SOSPETTO: " + ", ".join(sosp)) if sosp else "; ".join(motivi)})
        nuovi += bool(db.insert("opportunita", o))
    db.log("portali", f"{PORTALI[r['portale']]['nome']}: {len(r['cards'])} annunci letti, {nuovi} nuovi")
    return {"ok": True, "portale": PORTALI[r["portale"]]["nome"], "letti": len(r["cards"]), "nuovi": nuovi}


def cerca_e_importa(portale: str, parole: str) -> dict:
    apri_ricerca(portale, parole)
    def attendi():
        try:
            W.page().wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass                              # LinkedIn non è mai del tutto "fermo": basta l'attesa
    W.run(attendi)
    time.sleep(random.uniform(2, 4))
    return importa_pagina()


def analizza_opportunita(opp_id: int) -> dict:
    """Apre l'annuncio nel browser, legge il testo completo e lo rivaluta con l'AI locale."""
    o = db.q("SELECT * FROM opportunita WHERE id=?", (opp_id,))[0]

    def f():
        pg = W.page()
        pg.goto(o["link"], wait_until="domcontentloaded", timeout=60000)
        time.sleep(random.uniform(2.5, 4))
        for sel in ("button.jobs-description__footer-button", "button[aria-label*='Mostra di più']",
                    "button[aria-label*='more']", "#jobDescriptionText ~ button"):
            try:
                b = pg.locator(sel).first
                if b.count() and b.is_visible():
                    b.click(timeout=2000)
                    break
            except Exception:
                pass
        main = pg.locator(".jobs-description, .jobs-search__job-details, #jobDescriptionText, main").first
        testo = main.inner_text(timeout=5000) if main.count() else pg.evaluate("() => document.body.innerText")
        return {"testo": testo[:12000], "url": pg.url}
    r = W.run(f)
    d = lavoro.valuta_testo(r["testo"], o)
    db.update("opportunita", opp_id, d)
    return {"ok": True, **d}

"""Modulo B — Ricerca PMI da dati pubblici (OpenStreetMap) e analisi del loro sito pubblico.

Solo dati aziendali pubblici; la fonte di ogni dato viene registrata (GDPR, legittimo interesse B2B).
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..core import db, llm, safety

UA = {"User-Agent": "AgenteLavoro/1.0 (ricerca B2B; info@gasparepettinati.it)"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://lz4.overpass-api.de/api/interpreter",
            "https://z.overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]

# servizi di intelligenza artificiale che Gaspare implementa (l'analisi sceglie SOLO da qui)
SERVIZI_AI = [
    "Agente telefonico AI che risponde 24/7, prende prenotazioni e smista le chiamate",
    "Assistente AI su WhatsApp per prenotazioni, domande frequenti e promemoria",
    "Chatbot AI sul sito addestrato sui contenuti dell'azienda (orari, servizi, prezzi, FAQ)",
    "Prenotazione online con conferme e promemoria automatici gestiti dall'AI",
    "Qualificazione automatica dei lead con AI e inserimento nel CRM",
    "Automazione AI di email, preventivi e documenti ripetitivi",
    "Risposte AI alle recensioni e ai messaggi social",
    "Integrazione AI con gestionale/CRM esistente (dati, report, flussi automatici)",
]

# settore -> (filtri OSM, servizio AI più probabile)
SETTORI = {
    "Farmacie": (['["amenity"="pharmacy"]'], SERVIZI_AI[0]),
    "Studi medici e dentistici": (['["amenity"="dentist"]', '["amenity"="doctors"]', '["healthcare"="clinic"]'], SERVIZI_AI[1]),
    "Ristoranti": (['["amenity"="restaurant"]'], SERVIZI_AI[0]),
    "Hotel e B&B": (['["tourism"="hotel"]', '["tourism"="guest_house"]'], SERVIZI_AI[2]),
    "Autofficine e concessionari": (['["shop"="car_repair"]', '["shop"="car"]'], SERVIZI_AI[1]),
    "Palestre": (['["leisure"="fitness_centre"]'], SERVIZI_AI[1]),
    "Agenzie immobiliari": (['["office"="estate_agent"]'], SERVIZI_AI[4]),
    "Studi professionali (commercialisti, avvocati)": (['["office"="accountant"]', '["office"="lawyer"]'], SERVIZI_AI[5]),
    "Centri estetici e parrucchieri": (['["shop"="beauty"]', '["shop"="hairdresser"]'], SERVIZI_AI[3]),
    "Negozi e e-commerce locali": (['["shop"="electronics"]', '["shop"="furniture"]', '["shop"="clothes"]'], SERVIZI_AI[2]),
}

# cosa c'è già sul sito: (nome, regex sull'HTML)
SEGNALI = [
    ("WhatsApp", r"wa\.me|api\.whatsapp|whatsapp"),
    ("chat sul sito", r"tawk\.to|crisp\.chat|intercom|livechat|zendesk|tidio|hubspot.*chat|messenger"),
    ("chatbot AI già presente", r"chatbot|openai|botpress|voiceflow|landbot|dialogflow"),
    ("prenotazione online", r"prenota online|prenotazione online|booking|calendly|thefork|quandoo|miodottore|doctolib|"
                            r"treatwell|uala|fresha|mindbody|resos|plateform|prenota ora|prenota un tavolo"),
    ("modulo contatti", r"<form[^>]*>(?:(?!</form>).)*(email|messaggio)"),
    ("e-commerce", r"woocommerce|shopify|add to cart|aggiungi al carrello|prestashop"),
    ("più lingue", r"hreflang=|/en/|lang=\"en"),
    ("social", r"instagram\.com|facebook\.com"),
]


def cerca_osm(settore: str, citta: str, limite: int = 40) -> dict:
    filtri, servizio = SETTORI[settore]
    # 1) confini della città con Nominatim (leggero), 2) ricerca per riquadro su Overpass (molto più veloce delle "area")
    g = httpx.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=20,
                  params={"city": citta, "country": "Italia", "format": "json", "limit": 1})
    if g.status_code != 200 or not g.json():
        raise RuntimeError(f"Città non trovata: {citta}")
    s_, n_, w_, e_ = g.json()[0]["boundingbox"]
    bbox = f"{s_},{w_},{n_},{e_}"
    corpo = "".join(f'nwr{f}["website"]({bbox});' for f in filtri)
    query = f"[out:json][timeout:25];({corpo});out tags center {limite};"
    r, errore = None, ""
    # il server pubblico limita le richieste (429/504 quando è occupato): ritenta con attese crescenti
    for tentativo, server in enumerate((OVERPASS[:3] * 3) + OVERPASS[3:]):
        try:
            r = httpx.post(server, data={"data": query}, headers=UA, timeout=40)
            if r.status_code == 200:
                break
            errore = f"{server}: HTTP {r.status_code}"
        except httpx.HTTPError as e:
            errore = f"{server}: {e}"
        r = None
        time.sleep(3)
    if r is None:
        raise RuntimeError(f"OpenStreetMap non raggiungibile, riprova tra qualche minuto ({errore})")
    nuovi = 0
    for el in r.json().get("elements", []):
        t = el.get("tags", {})
        nome, sito = t.get("name"), t.get("website") or t.get("contact:website")
        if not nome or not sito:
            continue
        if not sito.startswith("http"):
            sito = "https://" + sito
        email = t.get("email") or t.get("contact:email") or ""
        rid = db.insert("aziende", {
            "uid": f"osm-{el['type']}-{el['id']}", "nome": nome, "settore": settore, "citta": citta, "sito": sito,
            "email": email, "telefono": t.get("phone") or t.get("contact:phone") or "",
            "fonte_dato": f"OpenStreetMap + sito web pubblico ({urlparse(sito).netloc})", "servizio": servizio})
        nuovi += bool(rid)
    db.log("pmi", f"OSM {settore} / {citta}: {nuovi} nuove aziende")
    return {"trovate": len(r.json().get("elements", [])), "nuove": nuovi}


def _scarica(url: str) -> tuple[str, BeautifulSoup | None]:
    try:
        r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
        return r.text, BeautifulSoup(r.text, "html.parser")
    except Exception:
        return "", None


def _email_pubbliche(html: str) -> list[str]:
    found = set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html))
    return sorted(e for e in found if not re.search(r"\.(png|jpg|gif|webp|svg)$|example|sentry|wixpress|@2x", e, re.I))


def analizza(az_id: int) -> dict:
    a = db.q("SELECT * FROM aziende WHERE id=?", (az_id,))[0]
    html, soup = _scarica(a["sito"])
    if not soup:
        db.update("aziende", az_id, {"analisi": "Sito non raggiungibile", "stato": "Scartato"})
        return {"ok": False, "errore": "Sito non raggiungibile"}
    testo = re.sub(r"\s+", " ", soup.get_text(" "))[:4000]
    low = html.lower()
    presenti = [nome for nome, rx in SEGNALI if re.search(rx, low, re.S)]
    assenti = [nome for nome, _ in SEGNALI[:5] if nome not in presenti]
    segnali = ([f"ha: {', '.join(presenti)}"] if presenti else []) + ([f"manca: {', '.join(assenti)}"] if assenti else [])
    if len(testo) < 300:                         # sito vuoto, bloccato o solo JavaScript: l'AI non avrebbe nulla da leggere
        db.update("aziende", az_id, {"analisi": "Sito non leggibile (vuoto, bloccato o solo JavaScript): da verificare a mano. "
                                                "[interesse 0/10]", "stato": "Scartato"})
        return {"ok": False, "errore": "Sito non leggibile"}
    email = a["email"]
    if not email:
        cand = _email_pubbliche(html)
        for path in ("/contatti", "/contact", "/contatti/", "/chi-siamo"):
            if cand:
                break
            h2, _ = _scarica(urljoin(a["sito"], path))
            cand = _email_pubbliche(h2)
        dominio = urlparse(a["sito"]).netloc.replace("www.", "")
        cand.sort(key=lambda e: (dominio not in e, not e.startswith(("info@", "commerciale@", "contatti@"))))
        email = cand[0] if cand else ""
    servizi = "\n".join(f"{i + 1}. {x}" for i, x in enumerate(SERVIZI_AI))
    sys = ("Sei un consulente che implementa l'intelligenza artificiale nelle PMI italiane. Dal sito capisci cosa manca "
           "e quale servizio AI risolverebbe un problema reale dell'azienda. Scegli il servizio SOLO da questo elenco:\n"
           f"{servizi}\n"
           "Interesse (sii severo, usa tutta la scala): 8-10 = molte richieste dei clienti gestite a mano "
           "(telefono, email, niente prenotazione online) e attività che vive di prenotazioni/contatti; "
           "5-7 = qualcosa c'è già ma manca l'AI; 1-4 = è già automatizzato, oppure è una grande catena, un ente pubblico "
           "o una ONG. Usa SOLO ciò che vedi: non inventare. Rispondi SOLO in JSON: "
           "{\"cosa_manca\": \"1 riga\", \"servizio\": numero dall'elenco, "
           "\"caso_uso\": \"1 frase concreta: cosa farebbe l'AI per QUESTA azienda\", \"interesse\": numero 1-10}")
    try:
        d = llm.chat_json(sys, f"Azienda: {a['nome']} ({a['settore']}, {a['citta']}). Segnali dal sito: {'; '.join(segnali)}\n"
                          + llm.dati(testo, 1800), max_tokens=300)
        try:
            servizio = SERVIZI_AI[int(d.get("servizio")) - 1]
        except (TypeError, ValueError, IndexError):
            servizio = a["servizio"]
        analisi = (f"Manca: {d.get('cosa_manca', '')} | Caso d'uso AI: {d.get('caso_uso', '')} | "
                   f"Sul sito: {'; '.join(segnali)} [interesse {d.get('interesse', '?')}/10]")
    except llm.LLMError:
        analisi, servizio = "; ".join(segnali) or "Analisi AI non disponibile", a["servizio"]
    if safety.email_in_opt_out(email):
        db.update("aziende", az_id, {"opt_out": 1, "stato": "Opt-out"})
    db.update("aziende", az_id, {"analisi": analisi, "servizio": servizio, "email": email,
                                 "stato": "Analizzata" if a["stato"] == "Nuovo" else a["stato"]})
    return {"ok": True, "analisi": analisi, "email": email}

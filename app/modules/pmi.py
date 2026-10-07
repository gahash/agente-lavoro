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

# settore -> (filtri OSM, servizio più adatto)
SETTORI = {
    "Farmacie": (['["amenity"="pharmacy"]'], "Agente telefonico AI + WhatsApp per prenotazioni e disponibilità"),
    "Studi medici e dentistici": (['["amenity"="dentist"]', '["amenity"="doctors"]', '["healthcare"="clinic"]'],
                                  "Prenotazioni e promemoria via WhatsApp"),
    "Ristoranti": (['["amenity"="restaurant"]'], "Prenotazioni WhatsApp automatiche"),
    "Hotel e B&B": (['["tourism"="hotel"]', '["tourism"="guest_house"]'], "Assistente omnichannel per richieste e prenotazioni"),
    "Autofficine e concessionari": (['["shop"="car_repair"]', '["shop"="car"]'], "Promemoria tagliandi e preventivi via WhatsApp"),
    "Palestre": (['["leisure"="fitness_centre"]'], "Iscrizioni, rinnovi e CRM soci"),
    "Agenzie immobiliari": (['["office"="estate_agent"]'], "CRM lead e risposte automatiche agli annunci"),
    "Studi professionali (commercialisti, avvocati)": (['["office"="accountant"]', '["office"="lawyer"]'],
                                                       "Gestionale pratiche e assistente per i clienti"),
    "Centri estetici e parrucchieri": (['["shop"="beauty"]', '["shop"="hairdresser"]'], "Prenotazioni WhatsApp e promemoria"),
    "Negozi e e-commerce locali": (['["shop"="electronics"]', '["shop"="furniture"]', '["shop"="clothes"]'],
                                   "Supporto clienti omnichannel e integrazione con il gestionale"),
}


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
    segnali = []
    low = html.lower()
    if "wa.me" in low or "whatsapp" in low:
        segnali.append("usa già WhatsApp sul sito")
    if not re.search(r"prenot|booking|calendly|appuntament", low):
        segnali.append("nessuna prenotazione online visibile")
    if re.search(r"chat|tawk|crisp|intercom|livechat|zendesk", low):
        segnali.append("ha una chat sul sito")
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
    sys = ("Analizza il sito di una PMI italiana per capire se trarrebbe beneficio da automazioni (WhatsApp, "
           "agente telefonico AI, CRM, gestionale, integrazioni). Rispondi SOLO in JSON: "
           "{\"analisi\": \"2-3 righe concrete basate SOLO su ciò che vedi\", \"servizio\": \"il servizio più adatto\", "
           "\"interesse\": numero 1-10}")
    try:
        d = llm.chat_json(sys, f"Azienda: {a['nome']} ({a['settore']}). Segnali: {', '.join(segnali)}\n" + llm.dati(testo, 3500),
                          max_tokens=300)
        analisi = f"{d.get('analisi', '')} [interesse {d.get('interesse', '?')}/10]"
        servizio = d.get("servizio") or a["servizio"]
    except llm.LLMError:
        analisi, servizio = "; ".join(segnali) or "Analisi AI non disponibile", a["servizio"]
    if safety.email_in_opt_out(email):
        db.update("aziende", az_id, {"opt_out": 1, "stato": "Opt-out"})
    db.update("aziende", az_id, {"analisi": analisi, "servizio": servizio, "email": email,
                                 "stato": "Analizzata" if a["stato"] == "Nuovo" else a["stato"]})
    return {"ok": True, "analisi": analisi, "email": email}

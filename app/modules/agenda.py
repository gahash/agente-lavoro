"""Agenda: appuntamenti nel gestionale del sito (gasparepettinati.it/gestionale) e promemoria via email.

L'app parla con il gestionale tramite gestionale/api/agenda.php, protetta da un token
(lo stesso valore in config.php del sito e nelle credenziali dell'app). Gli orari proposti ai clienti
rispettano le ore occupate (riunioni) e gli appuntamenti già presenti nel gestionale.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import httpx

from ..core import db, vault
from ..core.config import load_settings

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
FMT = "%Y-%m-%d %H:%M"


class AgendaNonCollegata(RuntimeError):
    pass


# ------------------------------------------------------------------ gestionale
def _chiama(metodo: str, **kw) -> dict | list:
    token = vault.get_cred("gestionale_token")
    if not token:
        raise AgendaNonCollegata("Token del gestionale non impostato (Impostazioni → Credenziali).")
    r = httpx.request(metodo, load_settings()["agenda_api_url"], headers={"X-Agente-Token": token},
                      timeout=15, **kw)
    d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400:
        raise RuntimeError(d.get("error") or f"Gestionale: errore {r.status_code}")
    return d


def collegata() -> bool:
    try:
        _chiama("GET", params={"da": date.today().isoformat(), "a": date.today().isoformat()})
        return True
    except Exception:
        return False


def elenco(da: date | None = None, giorni: int = 14) -> list[dict]:
    da = da or date.today()
    d = _chiama("GET", params={"da": da.isoformat(), "a": (da + timedelta(days=giorni)).isoformat()})
    return d.get("appuntamenti", [])


def crea(titolo: str, inizio: str, durata: int | None = None, cliente: str = "", telefono: str = "",
         luogo: str = "", tipo: str = "call", descrizione: str = "", promemoria: int | None = None,
         forza: bool = False) -> dict:
    """Crea l'appuntamento nel gestionale. `inizio` = 'AAAA-MM-GG HH:MM'. Rifiuta le ore occupate se non `forza`."""
    s = load_settings()
    durata = int(durata or s["durata_appuntamento"])
    t = datetime.strptime(inizio, FMT)
    if not forza and _occupato(t, durata):
        return {"ok": False, "errore": f"{formatta(t)} cade nelle ore occupate ({', '.join(s['orari_occupato'])})."}
    d = _chiama("POST", json={"titolo": titolo, "inizio": inizio, "durata": durata, "cliente": cliente,
                              "telefono_cliente": telefono, "luogo": luogo, "tipo": tipo, "descrizione": descrizione,
                              "promemoria_minuti": promemoria if promemoria is not None else s["promemoria_minuti"]})
    db.log("agenda", f"Appuntamento creato nel gestionale: {titolo} — {inizio}")
    return {"ok": True, "id": d.get("id"), "quando": formatta(t)}


# ------------------------------------------------------------------ orari
def _intervalli(voci: list[str], giorno: date) -> list[tuple[datetime, datetime]]:
    out = []
    for v in voci:
        a, b = (x.strip() for x in v.split("-"))
        out.append((datetime.combine(giorno, datetime.strptime(a, "%H:%M").time()),
                    datetime.combine(giorno, datetime.strptime(b, "%H:%M").time())))
    return out


def _occupato(t: datetime, durata: int) -> bool:
    """Vero se l'intervallo cade nelle ore di riunione (lun-ven), fuori dagli spazi liberi."""
    if t.weekday() >= 5:
        return False
    s = load_settings()
    fine = t + timedelta(minutes=durata)
    if any(a <= t and fine <= b for a, b in _intervalli(s["spazi_liberi"], t.date())):
        return False
    return any(t < b and fine > a for a, b in _intervalli(s["orari_occupato"], t.date()))


def slot_liberi(n: int = 3, esistenti: list[dict] | None = None, adesso: datetime | None = None) -> list[datetime]:
    """Primi `n` orari da proporre ai clienti: giorni feriali da domani, mai nelle ore occupate o sovrapposti
    agli appuntamenti del gestionale. Al massimo uno per giorno, così il cliente sceglie tra giorni diversi."""
    s = load_settings()
    adesso = adesso or datetime.now()
    durata = timedelta(minutes=int(s["durata_appuntamento"]))
    if esistenti is None:
        esistenti = elenco(adesso.date(), 21)
    presi = []
    for a in esistenti:
        i = datetime.strptime(a["inizio"][:16], FMT)
        f = datetime.strptime(a["fine"][:16], FMT) if a.get("fine") else i + timedelta(hours=1)
        presi.append((i, f))
    out = []
    giorno = adesso.date() + timedelta(days=1)
    while len(out) < n and giorno <= adesso.date() + timedelta(days=21):
        if giorno.weekday() < 5:
            for hhmm in s["slot_clienti"]:
                t = datetime.combine(giorno, datetime.strptime(hhmm, "%H:%M").time())
                if _occupato(t, durata.seconds // 60) or any(t < f and t + durata > i for i, f in presi):
                    continue
                out.append(t)
                break
        giorno += timedelta(days=1)
    return out


def formatta(t: datetime) -> str:
    return f"{GIORNI[t.weekday()]} {t:%d/%m} alle {t:%H:%M}"


def _elenco_orari() -> str:
    try:
        slot = slot_liberi()
    except Exception as e:                       # gestionale non raggiungibile: niente orari inventati
        db.log("agenda", f"Orari non calcolati: {e}", "errore")
        return ""
    return "\n".join(f"- {formatta(t)}" for t in slot)


def frase_orari() -> str:
    """Coda per le bozze: orari liberi + link di prenotazione (o solo il punto finale)."""
    orari, link = _elenco_orari(), load_settings().get("link_prenota", "")
    out = (f", ad esempio:\n{orari}" if orari else ".")
    if link:
        out += f"\n\nSe preferisce, può scegliere l'orario direttamente qui: {link}"
    return out


def riempi_orari(testo: str) -> str:
    """Sostituisce il segnaposto [ORARI] con gli orari liberi; se non ci sono lo lascia, da compilare a mano."""
    if "[ORARI]" not in testo:
        return testo
    orari = _elenco_orari()
    return testo.replace("[ORARI]", "\n" + orari + "\n") if orari else testo


# ------------------------------------------------------------------ dalla pipeline
def fissa_da_pipeline(pid: int, inizio: str, tipo: str = "call", luogo: str = "", conferma: bool = True) -> dict:
    """Fissa l'appuntamento nel gestionale, aggiorna la pipeline e prepara l'email di conferma (Da approvare)."""
    from . import bozze
    p = db.q("SELECT * FROM pipeline WHERE id=?", (pid,))[0]
    s = load_settings()
    r = crea(f"Call — {p['azienda']}", inizio, cliente=p["azienda"], tipo=tipo, luogo=luogo,
             descrizione=f"Contatto: {p['contatto']}\nDalla pipeline di Agente Lavoro (voce {pid}).\n{p['note'] or ''}")
    if not r.get("ok"):
        return r
    db.update("pipeline", pid, {"stato": "Call", "prossimo_passo": f"Call {r['quando']}", "data_prossimo": inizio[:10]})
    if conferma and p["contatto"] and "@" in p["contatto"]:
        corpo = (f"Buongiorno,\n\nLe confermo il nostro appuntamento di {r['quando']} "
                 f"(durata circa {s['durata_appuntamento']} minuti){' — ' + luogo if luogo else ''}.\n"
                 "Se l'orario non dovesse più andarLe bene, mi risponda pure e ne troviamo un altro.\n\n"
                 f"Un saluto,\n{s['firma']}")
        r["bozza"] = bozze._salva("conferma_appuntamento", p["contatto"], f"Conferma appuntamento — {r['quando']}",
                                  corpo, "pipeline", pid)
    return r


# ------------------------------------------------------------------ promemoria per Gaspare
def _a_me(oggetto: str, testo: str) -> None:
    from . import posta
    posta.invia_a_me(oggetto, testo)


def promemoria(adesso: datetime | None = None) -> int:
    """Email a Gaspare prima di ogni appuntamento (minuti del gestionale, o quelli predefiniti). Una sola volta."""
    s = load_settings()
    adesso = adesso or datetime.now()
    n = 0
    for a in elenco(adesso.date(), 2):
        inizio = datetime.strptime(a["inizio"][:16], FMT)
        minuti = int(a.get("promemoria_minuti") or s["promemoria_minuti"])
        if not (inizio - timedelta(minutes=minuti) <= adesso < inizio):
            continue
        uid = f"{a['id']}|{a['inizio']}"
        if db.q("SELECT 1 FROM promemoria WHERE uid=?", (uid,)):
            continue
        mancano = int((inizio - adesso).total_seconds() // 60)
        testo = (f"⏰ Tra {mancano} minuti: {a['titolo']}\n\n📅 {formatta(inizio)}\n"
                 + (f"👤 {a['cliente']}\n" if a.get("cliente") else "")
                 + (f"📍 {a['luogo']}\n" if a.get("luogo") else "")
                 + f"\nAgenda: {s['crm_url_lead']}index.php?tab=appuntamenti")
        _a_me(f"⏰ {inizio:%H:%M} — {a['titolo']}", testo)
        db.insert("promemoria", {"uid": uid, "inviato": db.now()})
        db.log("agenda", f"Promemoria inviato: {a['titolo']} ({a['inizio']})")
        n += 1
    return n


def agenda_del_giorno(giorno: date | None = None) -> str:
    s = load_settings()
    giorno = giorno or date.today()
    app = [a for a in elenco(giorno, 0) if a["inizio"][:10] == giorno.isoformat()]
    righe = [f"Agenda di {GIORNI[giorno.weekday()]} {giorno:%d/%m}", ""]
    if giorno.weekday() < 5:
        righe.append(f"🔒 Riunioni: {', '.join(s['orari_occupato'])} — spazi liberi: {', '.join(s['spazi_liberi'])}")
    righe += [f"📅 {a['inizio'][11:16]} {a['titolo']}" + (f" — {a['cliente']}" if a.get("cliente") else "") for a in app] \
        or ["Nessun appuntamento nel gestionale."]
    nb = db.q("SELECT COUNT(*) n FROM bozze WHERE stato='da_approvare'")[0]["n"]
    if nb:
        righe += ["", f"✍️ {nb} bozze da approvare: quelle approvate partono da sole alle {', '.join(s['invio_approvate'])}."]
    return "\n".join(righe)


def email_mattino() -> None:
    oggi = date.today()
    testo = agenda_del_giorno(oggi)
    if oggi.weekday() >= 5 and "Nessun appuntamento" in testo:
        return
    _a_me(f"🗓️ Agenda di oggi {oggi:%d/%m}", testo)
    db.log("agenda", "Email con l'agenda del giorno inviata")

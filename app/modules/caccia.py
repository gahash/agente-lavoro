"""Caccia automatica (lun-ven): trova aziende e annunci e prepara le bozze, senza aspettare un clic.

Ogni giro: 1) cerca nuove PMI su OpenStreetMap (settore e città a rotazione), 2) analizza i loro siti,
3) scrive le proposte per quelle con un'email pubblica, 4) scrive le candidature per gli annunci migliori.
Tutto finisce in "Da approvare": parte solo ciò che Gaspare approva (vedi posta.invia_approvate).
"""
from __future__ import annotations

import re
import threading
from datetime import date

from ..core import db, safety
from ..core.config import load_settings
from . import bozze, pmi


# avanzamento del giro, letto dall'interfaccia (barra con percentuale)
STATO: dict = {"attivo": False, "percentuale": 0, "fase": "", "dettaglio": "", "inizio": None, "passo_dal": None,
               "ultimo_esito": None}
_lock = threading.Lock()
# peso di ogni fase sul totale: l'analisi dei siti è la parte più lunga
FASI = {"ricerca": (0, 10), "analisi": (10, 60), "proposte": (60, 90), "candidature": (90, 100)}


def _passo(fase: str, i: int, n: int, dettaglio: str) -> None:
    a, b = FASI[fase]
    STATO.update({"percentuale": round(a + (b - a) * (i / n if n else 1)), "fase": fase, "dettaglio": dettaglio,
                  "passo_dal": db.now()})


def avvia_in_background() -> dict:
    if STATO["attivo"]:
        return {"ok": False, "errore": "La ricerca clienti è già in corso."}
    threading.Thread(target=giro, daemon=True, name="caccia").start()
    return {"ok": True}


def _combinazione(s: dict) -> tuple[str, str]:
    """Settore e città del giro: ruotano a ogni giro, così si copre tutto senza ripetere la stessa ricerca."""
    combo = [(se, c) for c in s["caccia_citta"] for se in s["caccia_settori"] if se in pmi.SETTORI]
    if not combo:
        raise ValueError("Nessun settore/città valido nelle impostazioni della caccia.")
    giri = db.q("SELECT COUNT(*) n FROM eventi WHERE modulo='caccia' AND messaggio LIKE 'Giro:%'")[0]["n"]
    return combo[giri % len(combo)]


def _interesse(analisi: str) -> int:
    m = re.search(r"interesse (\d+)/10", analisi or "")
    return int(m.group(1)) if m else 5


def _bozze_oggi(tipo: str) -> int:
    return db.q("SELECT COUNT(*) n FROM bozze WHERE tipo=? AND creato LIKE ?", (tipo, date.today().isoformat() + "%"))[0]["n"]


def giro() -> dict:
    if not _lock.acquire(blocking=False):
        return {"ok": False, "errore": "La ricerca clienti è già in corso."}
    STATO.update({"attivo": True, "percentuale": 0, "fase": "ricerca", "dettaglio": "Avvio…", "inizio": db.now(),
                  "passo_dal": db.now()})
    try:
        esito = _giro()
        STATO["ultimo_esito"] = {**esito, "fine": db.now()}
        return esito
    except Exception as e:
        STATO["ultimo_esito"] = {"ok": False, "errore": str(e), "fine": db.now()}
        raise
    finally:
        STATO.update({"attivo": False, "percentuale": 100})
        _lock.release()


def _giro() -> dict:
    s = load_settings()
    esito = {"nuove_aziende": 0, "analizzate": 0, "proposte": 0, "candidature": 0, "errori": []}

    # 1) nuove aziende
    settore, citta = _combinazione(s)
    _passo("ricerca", 0, 1, f"Cerco {settore.lower()} a {citta} su OpenStreetMap")
    try:
        esito["nuove_aziende"] = pmi.cerca_osm(settore, citta, 30)["nuove"]
    except Exception as e:
        esito["errori"].append(f"ricerca {settore}/{citta}: {e}")

    # 2) analisi dei siti: prima quelle che hanno già un'email
    da_analizzare = db.q("SELECT id FROM aziende WHERE stato='Nuovo' AND opt_out=0 AND sito<>'' "
                         "ORDER BY (email<>'') DESC, id LIMIT ?", (int(s["caccia_analisi"]),))
    for i, a in enumerate(da_analizzare):
        nome = db.q("SELECT nome FROM aziende WHERE id=?", (a["id"],))[0]["nome"]
        _passo("analisi", i, len(da_analizzare), f"Analizzo il sito di {nome} ({i + 1}/{len(da_analizzare)})")
        try:
            esito["analizzate"] += bool(pmi.analizza(a["id"]).get("ok"))
        except Exception as e:
            esito["errori"].append(f"analisi {a['id']}: {e}")

    # 3) proposte: solo con email, interesse sufficiente, entro il tetto giornaliero e la quota anti-spam
    posti = min(int(s["caccia_proposte_giorno"]) - _bozze_oggi("proposta_pmi"), safety.pmi_quota_residua())
    pronte = db.q("SELECT id, nome, analisi FROM aziende WHERE stato='Analizzata' AND opt_out=0 AND email LIKE '%@%' ORDER BY id")
    scelte = [a for a in sorted(pronte, key=lambda x: -_interesse(x["analisi"]))
              if _interesse(a["analisi"]) >= int(s["caccia_interesse_min"])][:max(0, posti)]
    for i, a in enumerate(scelte):
        _passo("proposte", i, len(scelte), f"Scrivo la proposta per {a.get('nome', 'l’azienda')} ({i + 1}/{len(scelte)})")
        try:
            esito["proposte"] += bool(bozze.proposta_pmi(a["id"]).get("ok"))
        except Exception as e:
            esito["errori"].append(f"proposta {a['id']}: {e}")

    # 4) candidature agli annunci migliori
    posti = int(s["caccia_candidature_giorno"]) - _bozze_oggi("candidatura")
    if posti > 0:
        annunci = db.q("SELECT id, ruolo, azienda FROM opportunita WHERE stato='Nuovo' AND sospetto=0 AND punteggio>=? "
                       "ORDER BY punteggio DESC LIMIT ?", (s["soglia_annunci"], posti))
        for i, o in enumerate(annunci):
            _passo("candidature", i, len(annunci),
                   f"Scrivo la candidatura: {o.get('ruolo') or ''} — {o.get('azienda') or ''} ({i + 1}/{len(annunci)})")
            try:
                esito["candidature"] += bool(bozze.candidatura(o["id"]).get("ok"))
            except Exception as e:
                esito["errori"].append(f"candidatura {o['id']}: {e}")

    db.log("caccia", f"Giro: {settore} / {citta} — {esito['nuove_aziende']} aziende nuove, {esito['analizzate']} analizzate, "
                     f"{esito['proposte']} proposte e {esito['candidature']} candidature in Da approvare"
           + (f" — {len(esito['errori'])} errori: {'; '.join(esito['errori'])[:600]}" if esito["errori"] else ""))
    return {"ok": True, **esito}

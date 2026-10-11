"""Caccia automatica (lun-ven): trova aziende e annunci e prepara le bozze, senza aspettare un clic.

Ogni giro: 1) cerca nuove PMI su OpenStreetMap (settore e città a rotazione), 2) analizza i loro siti,
3) scrive le proposte per quelle con un'email pubblica, 4) scrive le candidature per gli annunci migliori.
Tutto finisce in "Da approvare": parte solo ciò che Gaspare approva (vedi posta.invia_approvate).
"""
from __future__ import annotations

import re
from datetime import date

from ..core import db, safety
from ..core.config import load_settings
from . import bozze, pmi


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
    s = load_settings()
    esito = {"nuove_aziende": 0, "analizzate": 0, "proposte": 0, "candidature": 0, "errori": []}

    # 1) nuove aziende
    settore, citta = _combinazione(s)
    try:
        esito["nuove_aziende"] = pmi.cerca_osm(settore, citta, 30)["nuove"]
    except Exception as e:
        esito["errori"].append(f"ricerca {settore}/{citta}: {e}")

    # 2) analisi dei siti: prima quelle che hanno già un'email
    da_analizzare = db.q("SELECT id FROM aziende WHERE stato='Nuovo' AND opt_out=0 AND sito<>'' "
                         "ORDER BY (email<>'') DESC, id LIMIT ?", (int(s["caccia_analisi"]),))
    for a in da_analizzare:
        try:
            esito["analizzate"] += bool(pmi.analizza(a["id"]).get("ok"))
        except Exception as e:
            esito["errori"].append(f"analisi {a['id']}: {e}")

    # 3) proposte: solo con email, interesse sufficiente, entro il tetto giornaliero e la quota anti-spam
    posti = min(int(s["caccia_proposte_giorno"]) - _bozze_oggi("proposta_pmi"), safety.pmi_quota_residua())
    pronte = db.q("SELECT id, analisi FROM aziende WHERE stato='Analizzata' AND opt_out=0 AND email LIKE '%@%' ORDER BY id")
    for a in sorted(pronte, key=lambda x: -_interesse(x["analisi"])):
        if posti <= 0:
            break
        if _interesse(a["analisi"]) < int(s["caccia_interesse_min"]):
            continue
        try:
            if bozze.proposta_pmi(a["id"]).get("ok"):
                esito["proposte"] += 1
                posti -= 1
        except Exception as e:
            esito["errori"].append(f"proposta {a['id']}: {e}")

    # 4) candidature agli annunci migliori
    posti = int(s["caccia_candidature_giorno"]) - _bozze_oggi("candidatura")
    if posti > 0:
        for o in db.q("SELECT id FROM opportunita WHERE stato='Nuovo' AND sospetto=0 AND punteggio>=? "
                      "ORDER BY punteggio DESC LIMIT ?", (s["soglia_annunci"], posti)):
            try:
                esito["candidature"] += bool(bozze.candidatura(o["id"]).get("ok"))
            except Exception as e:
                esito["errori"].append(f"candidatura {o['id']}: {e}")

    db.log("caccia", f"Giro: {settore} / {citta} — {esito['nuove_aziende']} aziende nuove, {esito['analizzate']} analizzate, "
                     f"{esito['proposte']} proposte e {esito['candidature']} candidature in Da approvare"
           + (f" — {len(esito['errori'])} errori: {'; '.join(esito['errori'])[:600]}" if esito["errori"] else ""))
    return {"ok": True, **esito}

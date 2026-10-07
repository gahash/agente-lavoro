"""Cose da fare: la routine quotidiana + attività generate dai dati + attività aggiunte a mano."""
from __future__ import annotations

from datetime import date

from ..core import db, safety
from ..core.config import load_settings


def genera(giorno: str | None = None) -> int:
    """Crea (senza duplicati) le attività del giorno. Si può richiamare quante volte si vuole."""
    g = giorno or date.today().isoformat()
    s = load_settings()
    n = 0

    def add(uid, titolo, dettaglio="", ora="", vista="", origine="auto", priorita=2):
        nonlocal n
        n += bool(db.insert("attivita", {"uid": f"{g}|{uid}", "data": g, "ora": ora, "titolo": titolo,
                                         "dettaglio": dettaglio, "origine": origine, "vista": vista,
                                         "priorita": priorita}))

    if date.fromisoformat(g).weekday() < 5:          # routine solo nei giorni feriali
        for r in s.get("routine", []):
            add("routine|" + r["titolo"], r["titolo"], ora=r.get("ora", ""), vista=r.get("vista", ""), origine="routine")

    # dai dati
    for m in db.q("SELECT id, mittente, oggetto FROM posta WHERE gestita=0 AND categoria='rosso'"):
        add(f"posta|{m['id']}", f"Rispondi: {m['oggetto'][:80]}", m["mittente"], vista="posta", priorita=1)
    for m in db.q("SELECT id, mittente, oggetto, allarme FROM posta WHERE gestita=0 AND categoria='stop'"):
        add(f"stop|{m['id']}", f"⚠️ Email sospetta: {m['oggetto'][:70]}", f"{m['mittente']} — {m['allarme']}. Non rispondere con dati o pagamenti.",
            vista="posta", priorita=1)
    nb = db.q("SELECT COUNT(*) n FROM bozze WHERE stato='da_approvare'")[0]["n"]
    if nb:
        add("bozze", f"{nb} bozze da approvare", vista="bozze", priorita=1)
    for p in db.q("SELECT id, azienda, contatto FROM pipeline WHERE stato='Contattato' AND data_prossimo<=?", (g,)):
        add(f"follow|{p['id']}", f"Follow-up: {p['azienda']}", p["contatto"], vista="pipeline", priorita=1)
    for p in db.q("SELECT id, azienda, prossimo_passo FROM pipeline WHERE data_prossimo=? AND stato NOT IN ('Contattato','Vinto','Perso')", (g,)):
        add(f"passo|{p['id']}", f"{p['azienda']}: {p['prossimo_passo'] or 'prossimo passo'}", vista="pipeline", priorita=1)
    top = db.q("SELECT id, azienda, ruolo, punteggio FROM opportunita WHERE stato='Nuovo' AND sospetto=0 AND punteggio>=? "
               "ORDER BY punteggio DESC LIMIT 3", (s["soglia_annunci"],))
    for o in top:
        add(f"opp|{o['id']}", f"Valuta/candidati: {o['ruolo'][:60]} — {o['azienda']} ({o['punteggio']})", vista="lavoro")
    quota = safety.pmi_quota_residua()
    pronte = db.q("SELECT COUNT(*) n FROM aziende WHERE stato='Analizzata' AND opt_out=0")[0]["n"]
    if quota and pronte:
        add("pmi", f"{min(quota, pronte)} PMI analizzate pronte per la proposta", vista="pmi")
    return n


def lista(giorno: str | None = None) -> list[dict]:
    g = giorno or date.today().isoformat()
    genera(g)
    return db.q("SELECT * FROM attivita WHERE data=? ORDER BY fatto, priorita, CASE WHEN ora='' THEN '99' ELSE ora END, id", (g,))


def aggiungi(titolo: str, ora: str = "", giorno: str | None = None, dettaglio: str = "") -> int:
    g = giorno or date.today().isoformat()
    return db.insert("attivita", {"uid": f"{g}|manuale|{db.now()}|{titolo}", "data": g, "ora": ora, "titolo": titolo,
                                  "dettaglio": dettaglio, "origine": "manuale", "priorita": 2}, ignore=False)


def segna(aid: int, fatto: bool) -> None:
    db.update("attivita", aid, {"fatto": int(fatto), "fatto_il": db.now() if fatto else None})


def elimina(aid: int) -> None:
    db.x("DELETE FROM attivita WHERE id=?", (aid,))


def riepilogo_testo() -> str:
    righe = []
    for a in lista():
        righe.append(f"[{'x' if a['fatto'] else ' '}] {a['ora'] or '--:--'} {a['titolo']}")
    return "\n".join(righe)

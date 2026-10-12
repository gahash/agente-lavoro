"""Modulo C — Bozze personalizzate (candidature, proposte PMI, follow-up, risposte).
Tutte finiscono in stato 'da_approvare'. L'invio avviene solo da modules/posta.invia_approvata."""
from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher

from ..core import db, llm, safety
from ..core.config import load_settings
from . import agenda


def _profilo(s: dict) -> str:
    prog = "; ".join(f"{p['nome']} ({p['tema']}){' ' + p['link'] if p.get('link') else ''}"
                     for p in s["progetti_vetrina"])
    return (f"Nome: {s['nome']}. Posizionamento: {s['headline']}. Sito: {s['sito']}. "
            f"Competenze: {', '.join(s['competenze'])}. Progetti reali (schede pubbliche, codice privato): {prog}. "
            f"Forme di collaborazione: {', '.join(s['contratti'])}.")


CHIUSURE = re.compile(r"\s*(best regards|kind regards|sincerely|regards|cordiali saluti|distinti saluti|un saluto|"
                      r"saluti|grazie e (a presto|cordiali saluti))[,.!]?\s*(gaspare( pettinati)?)?\s*$", re.I)


CHIUSURA_RX = re.compile(r"(best regards|kind regards|sincerely|regards|cordiali saluti|distinti saluti|"
                         r"un caro saluto|un saluto|a presto)\b", re.I)


def pulisci(corpo: str) -> str:
    """Toglie saluti/firma che il modello aggiunge comunque (la firma la mette il sistema)."""
    c = (corpo or "").strip()
    coda = max(0, len(c) - 250)
    m = None
    for m in CHIUSURA_RX.finditer(c, coda):
        pass
    if m:
        c = c[:m.start()]
    c = re.sub(r"\s*gaspare pettinati\s*[.,]?\s*$", "", c, flags=re.I)
    c = re.sub(r"[ \t]+\n", "\n", c)
    return CHIUSURE.sub("", c).strip().rstrip(",")


FRASE_RX = re.compile(r"(?<=[.!?])\s+")


def _parole(frase: str) -> list[str]:
    return re.findall(r"\w+", frase.lower())


def togli_ripetizioni(corpo: str) -> tuple[str, list[str]]:
    """Toglie le frasi che ripetono (quasi alla lettera) una frase precedente. Restituisce testo e frasi tolte."""
    viste, tolte, paragrafi = [], [], []
    for par in (corpo or "").split("\n"):
        tenute = []
        for frase in FRASE_RX.split(par):
            w = _parole(frase)
            if len(w) >= 6 and any(SequenceMatcher(None, w, v).ratio() >= 0.7 for v in viste):
                tolte.append(frase.strip())
                continue
            if len(w) >= 6:
                viste.append(w)
            tenute.append(frase)
        paragrafi.append(" ".join(tenute))
    return "\n".join(paragrafi), tolte


PROMESSE_RX = re.compile(r"gratuit|gratis|senza costi|costo zero|nessun costo|garantit|subito dopo|"
                         r"modifiche al (codice|sito)|(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica) prossim|"
                         r"entro \d+ (giorni|ore|settimane)|\d+ ?%", re.I)


def rifinisci(corpo: str) -> str:
    """Corregge gli errori ricorrenti del modello locale."""
    c = re.sub(r"^(Buongiorno|Buonasera|Gentile [^,\n]+),\n\n(\w)", lambda m: f"{m.group(1)},\n\n{m.group(2).lower()}", corpo or "")
    c = re.sub(r"demo di \d+ a (\d+) minuti", r"demo di \1 minuti", c)
    c = re.sub(r"\buna chatbot\b", "un chatbot", c)
    c = re.sub(r"\bdei client:", "dei clienti:", c)
    return c


def promesse_rischiose(corpo: str) -> list[str]:
    return sorted({m.group(0).lower() for m in PROMESSE_RX.finditer(corpo or "")})


TU_RX = re.compile(r"\b(tu|tuo|tua|tuoi|tue|ti|te|puoi|vuoi|hai)\b", re.I)
AUTO_TIPI = ("proposta_pmi", "follow_up")


def motivi_blocco(tipo: str, destinatario: str, oggetto: str, corpo: str) -> list[str]:
    """Controlli che una bozza deve superare per essere approvata senza Gaspare."""
    s = load_settings()
    testo = (corpo or "").split("—\n")[0]                 # senza il piè di pagina GDPR
    m = []
    if tipo not in AUTO_TIPI:
        m.append("tipo da approvare a mano")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", (destinatario or "").strip(), re.I):
        m.append("destinatario mancante o non valido")
    if promesse_rischiose(testo):
        m.append("promesse da controllare")
    if TU_RX.search(testo):
        m.append("dà del tu")
    if tipo == "proposta_pmi" and not 300 <= len(testo) <= 1600:
        m.append("lunghezza anomala")
    if not testo.lstrip().startswith(("Buongiorno", "Buonasera", "Gentile")):
        m.append("saluto iniziale mancante")
    if not oggetto or len(oggetto) > 90:
        m.append("oggetto mancante o troppo lungo")
    if db.q("SELECT 1 FROM aziende WHERE lower(email)=lower(?) AND opt_out=1", ((destinatario or "").strip(),)):
        m.append("il destinatario ha chiesto di non essere contattato")
    oggi = db.now()[:10]
    n = db.q("SELECT COUNT(*) n FROM bozze WHERE note LIKE '%approvata in automatico%' AND creato LIKE ?", (oggi + "%",))[0]["n"]
    if n >= int(s.get("auto_max_giorno", 8)):
        m.append("tetto giornaliero di approvazioni automatiche raggiunto")
    return m


def _salva(tipo, destinatario, oggetto, corpo, rif_tabella, rif_id, in_risposta_a="", note="") -> int:
    corpo, tolte = togli_ripetizioni(rifinisci(corpo))
    avvisi = []
    if tolte:
        avvisi.append("⚠️ Tolte frasi ripetute: " + " / ".join(t[:80] for t in tolte))
    promesse = promesse_rischiose(corpo.split("—\n")[0])      # il piè di pagina GDPR non conta
    if promesse:
        avvisi.append("⚠️ Controlla le promesse: " + ", ".join(promesse))
    stato = "da_approvare"
    if load_settings().get("approvazione_automatica") and tipo in AUTO_TIPI:
        blocchi = (["frasi ripetute"] if tolte else []) + motivi_blocco(tipo, destinatario, oggetto, corpo)
        if blocchi:
            avvisi.append("Da rivedere: " + ", ".join(blocchi))
        else:
            stato = "approvata"
            avvisi.append("✅ approvata in automatico (tutti i controlli superati)")
    if avvisi:
        note = " | ".join([note] + avvisi) if note else " | ".join(avvisi)
    return db.insert("bozze", {"tipo": tipo, "destinatario": destinatario or "", "oggetto": oggetto,
                               "corpo": corpo, "rif_tabella": rif_tabella, "rif_id": rif_id,
                               "in_risposta_a": in_risposta_a, "note": note, "stato": stato}, ignore=False)


def candidatura(opp_id: int) -> dict:
    o = db.q("SELECT * FROM opportunita WHERE id=?", (opp_id,))[0]
    if o["sospetto"]:
        return {"ok": False, "errore": "Annuncio segnalato come sospetto: niente candidatura."}
    s = load_settings()
    inglese = not any(w in (o["descrizione"] or "").lower() for w in (" il ", " della ", " per ", " con "))
    lingua = "inglese" if inglese else "italiano"
    sys = (f"Scrivi una email di candidatura in {lingua} (oggetto e testo entrambi in {lingua}), massimo 150 parole, "
           "tono professionale e diretto, 3-4 brevi paragrafi separati da una riga vuota. "
           "Usa SOLO i dati del profilo: non inventare esperienze, aziende, anni o numeri. Cita 1 progetto pertinente "
           "e collega 2 requisiti dell'annuncio a competenze reali. Chiudi proponendo una call. NON scrivere saluti finali "
           "né firma (li aggiunge il sistema). Rispondi in JSON: {\"oggetto\": \"...\", \"corpo\": \"...\"}")
    user = f"PROFILO:\n{_profilo(s)}\n\nANNUNCIO:\n" + llm.dati(
        f"{o['azienda']} — {o['ruolo']}\nRequisiti: {o['requisiti']}\n{o['descrizione']}", 3500)
    d = llm.chat_json(sys, user, max_tokens=500, temperature=0.4)
    corpo = pulisci(d.get("corpo", "")) + "\n\n" + ("Best regards,\n" if inglese else "Cordiali saluti,\n") + s["firma"]
    bid = _salva("candidatura", o["contatto"], d.get("oggetto") or f"Candidatura {o['ruolo']}", corpo,
                 "opportunita", opp_id, note=f"Annuncio: {o['link']} — candidarsi dal link se non c'è email")
    db.update("opportunita", opp_id, {"stato": "Bozza pronta"})
    return {"ok": True, "id": bid}


def messaggio_linkedin(opp_id: int) -> dict:
    o = db.q("SELECT * FROM opportunita WHERE id=?", (opp_id,))[0]
    s = load_settings()
    sys = ("Scrivi un messaggio LinkedIn per un recruiter o CTO, massimo 300 caratteri, in italiano, cordiale e "
           "concreto, con un solo riferimento a un progetto reale e il sito. Solo il testo, niente JSON.")
    txt = llm.chat(sys, f"PROFILO:\n{_profilo(s)}\n\nAZIENDA/RUOLO:\n" + llm.dati(f"{o['azienda']} — {o['ruolo']}", 500),
                   max_tokens=150)
    bid = _salva("linkedin", "", f"LinkedIn — {o['azienda']}", txt[:320], "opportunita", opp_id,
                 note="Da copiare e incollare a mano su LinkedIn")
    return {"ok": True, "id": bid}


def proposta_pmi(az_id: int) -> dict:
    a = db.q("SELECT * FROM aziende WHERE id=?", (az_id,))[0]
    if a["opt_out"]:
        return {"ok": False, "errore": "Questa azienda ha chiesto di non essere contattata."}
    s = load_settings()
    sys = ("Scrivi una prima email a una PMI italiana, massimo 120 parole, in italiano, 3 brevi paragrafi separati "
           "da una riga vuota. Usa SEMPRE il registro formale: 'Lei', 'il Suo sito', 'Le propongo' — MAI 'tu', 'tuo', 'ti'. "
           "Inizia con 'Buongiorno,'. "
           "Parti da UNA osservazione concreta sull'azienda (dall'analisi), proponi UN servizio di intelligenza artificiale "
           "(quello suggerito) descrivendo il caso d'uso dell'analisi in parole semplici, senza gergo tecnico, "
           "con un beneficio pratico, offri una demo di 20 minuti senza impegno. Niente clienti inventati, "
           "niente promesse su prezzi, costi, gratuità, tempi o date, niente giorni proposti per la demo (sceglie il cliente), "
           "non dire che non servono modifiche al sito. Italiano corretto: 'un chatbot', 'un assistente'. "
           "niente numeri inventati, niente superlativi. Niente firma. "
           "JSON: {\"oggetto\": \"max 8 parole, specifico per l'azienda\", \"corpo\": \"...\"}")
    user = (f"PROFILO:\n{_profilo(s)}\n\nAZIENDA:\n" +
            llm.dati(f"{a['nome']} — settore {a['settore']} — {a['citta']}\nSito: {a['sito']}\n"
                     f"Analisi: {a['analisi']}\nServizio suggerito: {a['servizio']}", 2500))
    d = llm.chat_json(sys, user, max_tokens=450, temperature=0.4)
    corpo = pulisci(d.get("corpo", "")) + "\n\nUn saluto,\n" + s["firma"] + safety.footer_opt_out(a["fonte_dato"])
    bid = _salva("proposta_pmi", a["email"], d.get("oggetto") or f"Una proposta per {a['nome']}", corpo,
                 "aziende", az_id)
    db.update("aziende", az_id, {"stato": "Bozza pronta"})
    return {"ok": True, "id": bid}


def risposta_email(posta_id: int) -> dict:
    m = db.q("SELECT * FROM posta WHERE id=?", (posta_id,))[0]
    s = load_settings()
    richiede_codice = any(w in (m["anteprima"] or "").lower() for w in ("codice sorgente", "source code", "repository", "repo", "github"))
    extra = (" Se chiede il codice: il codice è privato; offri la scheda pubblica del progetto, una demo dal vivo "
             "o una sessione in screen-share, e un NDA se serve. Non promettere mai l'accesso al repository."
             if richiede_codice else "")
    sys = ("Scrivi una risposta email in italiano (o nella lingua del messaggio), cortese e concreta, max 140 parole. "
           "Proponi il prossimo passo (call, preventivo, documenti) e, se serve una call, scrivi che proponi 3 orari "
           "lasciando il segnaposto [ORARI]. Non accettare pagamenti, non fornire dati bancari, non inventare prezzi." + extra +
           " Niente firma. JSON: {\"oggetto\": \"Re: ...\", \"corpo\": \"...\"}")
    user = f"PROFILO:\n{_profilo(s)}\n\nEMAIL RICEVUTA:\n" + llm.dati(
        f"Da: {m['mittente']}\nOggetto: {m['oggetto']}\n{m['anteprima']}", 4000)
    d = llm.chat_json(sys, user, max_tokens=450)
    corpo = agenda.riempi_orari(pulisci(d.get("corpo", ""))) + "\n\nCordiali saluti,\n" + s["firma"]
    ogg = d.get("oggetto") or ("Re: " + (m["oggetto"] or ""))
    bid = _salva("risposta", m["mittente"], ogg, corpo, "posta", posta_id, in_risposta_a=m["message_id"] or "")
    return {"ok": True, "id": bid}


def follow_up_dovuti() -> dict:
    """Routine: prepara i solleciti per i contatti senza risposta arrivati alla data prevista (uno alla volta)."""
    s = load_settings()
    fatti = 0
    for p in db.q("SELECT id FROM pipeline WHERE stato='Contattato' AND data_prossimo<=? AND solleciti<?",
                  (db.now()[:10], s["max_solleciti"])):
        if db.q("SELECT 1 FROM bozze WHERE tipo='follow_up' AND rif_id=? AND stato IN ('da_approvare','approvata')", (p["id"],)):
            continue
        fatti += bool(follow_up(p["id"]).get("ok"))
    if fatti:
        db.log("bozze", f"{fatti} solleciti preparati in automatico")
    return {"ok": True, "solleciti": fatti}


def follow_up(pipe_id: int) -> dict:
    p = db.q("SELECT * FROM pipeline WHERE id=?", (pipe_id,))[0]
    s = load_settings()
    if p["solleciti"] >= s["max_solleciti"]:
        return {"ok": False, "errore": f"Raggiunto il massimo di {s['max_solleciti']} solleciti."}
    try:
        quando = "del " + date.fromisoformat((p["ultimo_contatto"] or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        quando = "precedente"
    corpo = (f"Buongiorno,\n\nriprendo il mio messaggio {quando} nel caso fosse sfuggito. "
             "Resto disponibile per una breve call conoscitiva, anche di 15 minuti, nei prossimi giorni"
             f"{agenda.frase_orari()}\n\nUn saluto,\n{s['firma']}")
    bid = _salva("follow_up", p["contatto"], f"Re: {p['azienda']}", corpo, "pipeline", pipe_id)
    return {"ok": True, "id": bid}

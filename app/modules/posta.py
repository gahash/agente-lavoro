"""Modulo D — Posta.

Lettura in SOLA LETTURA (IMAP readonly + BODY.PEEK: i messaggi non vengono segnati come letti).
Le bozze approvate possono essere copiate nella cartella Bozze della casella (APPEND).
L'invio SMTP avviene solo per bozze approvate da Gaspare, con il suo clic su "Invia".
"""
from __future__ import annotations

import email
import imaplib
import re
import smtplib
import ssl
import time
from datetime import date, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr

from ..core import db, llm, safety, vault
from ..core.config import load_settings

CATEGORIE = {
    "rosso": "🔴 lavoro/cliente",
    "arancio": "🟠 collaborazione",
    "giallo": "🟡 informazioni",
    "bianco": "⚪ newsletter",
    "stop": "⛔ spam/phishing",
}
OPT_OUT_RX = re.compile(r"^\s*no\s*$|non (mi )?contatt|cancellami|rimuovimi|unsubscribe|non sono interessat", re.I | re.M)


def _dec(v) -> str:
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


def _corpo(msg: email.message.Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    testo, html = "", ""
    for p in parts:
        ct = p.get_content_type()
        if p.get_content_disposition() == "attachment":
            continue
        try:
            payload = p.get_payload(decode=True)
            if payload is None:
                continue
            s = payload.decode(p.get_content_charset() or "utf-8", errors="ignore")
        except Exception:
            continue
        if ct == "text/plain" and not testo:
            testo = s
        elif ct == "text/html" and not html:
            html = re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", s))
    return re.sub(r"\s+", " ", testo or html).strip()


ERR_LOGIN = ("Il server della posta rifiuta email o password ({server}). Controlla la password della casella "
             "(su Hostinger: hPanel → Email → {utente} → Cambia password) e reinseriscila in Impostazioni → Credenziali.")


def _credenziali() -> tuple[str, str]:
    user, pwd = vault.get_cred("imap_user"), vault.get_cred("imap_password")
    if not user or not pwd:
        raise RuntimeError("Credenziali email mancanti: inseriscile in Impostazioni → Credenziali.")
    return user, pwd


def _imap() -> imaplib.IMAP4_SSL:
    s = load_settings()
    user, pwd = _credenziali()
    try:
        m = imaplib.IMAP4_SSL(s["imap_host"], int(s["imap_port"]), ssl_context=ssl.create_default_context(), timeout=30)
    except OSError as e:
        raise RuntimeError(f"Non riesco a raggiungere {s['imap_host']}:{s['imap_port']} ({e}). Controlla server e porta IMAP.")
    try:
        m.login(user, pwd)
    except imaplib.IMAP4.error as e:
        raise RuntimeError(ERR_LOGIN.format(server=f"IMAP {s['imap_host']}", utente=user)) from e
    return m


def _smtp() -> smtplib.SMTP:
    s = load_settings()
    user, pwd = _credenziali()
    host, porta = s["smtp_host"], int(s["smtp_port"])
    try:
        if porta == 465:
            smtp = smtplib.SMTP_SSL(host, porta, context=ssl.create_default_context(), timeout=30)
        else:                                       # 587: STARTTLS
            smtp = smtplib.SMTP(host, porta, timeout=30)
            smtp.starttls(context=ssl.create_default_context())
    except OSError as e:
        raise RuntimeError(f"Non riesco a raggiungere {host}:{porta} ({e}). Controlla server e porta SMTP.")
    try:
        smtp.login(user, pwd)
    except smtplib.SMTPAuthenticationError as e:
        smtp.close()
        raise RuntimeError(ERR_LOGIN.format(server=f"SMTP {host}", utente=user)) from e
    return smtp


def prova_connessione() -> dict:
    """Verifica lettura (IMAP) e invio (SMTP) senza leggere né inviare messaggi."""
    esito = {}
    for nome, fn in (("imap", _imap), ("smtp", _smtp)):
        try:
            c = fn()
            esito[nome] = {"ok": True}
            try:
                c.logout() if nome == "imap" else c.quit()
            except Exception:
                pass
        except Exception as e:
            esito[nome] = {"ok": False, "errore": str(e)}
    esito["ok"] = esito["imap"]["ok"] and esito["smtp"]["ok"]
    db.log("posta", f"Prova connessione: IMAP {'ok' if esito['imap']['ok'] else 'ERRORE'}, "
                    f"SMTP {'ok' if esito['smtp']['ok'] else 'ERRORE'}", "info" if esito["ok"] else "errore")
    return esito


def classifica_regole(mitt: str, ogg: str, corpo: str, headers: email.message.Message) -> tuple[str | None, str]:
    t = f"{ogg} {corpo}".lower()
    if headers.get("List-Unsubscribe") or re.search(r"newsletter|unsubscribe|disiscriviti|no-?reply", f"{mitt} {t}"):
        return "bianco", "newsletter/mittente automatico"
    return None, ""


def classifica_ai(mitt: str, ogg: str, corpo: str) -> tuple[str, str]:
    sys = ("Classifica l'email ricevuta da uno sviluppatore freelance che cerca lavoro e clienti. Categorie: "
           "rosso = offerta di lavoro, richiesta di preventivo o potenziale cliente; arancio = proposta di collaborazione; "
           "giallo = richiesta di informazioni; bianco = newsletter/notifica automatica; stop = spam, phishing, truffa. "
           "JSON: {\"categoria\": \"rosso|arancio|giallo|bianco|stop\", \"motivo\": \"max 15 parole\"}")
    d = llm.chat_json(sys, llm.dati(f"Da: {mitt}\nOggetto: {ogg}\n{corpo}", 2500), max_tokens=80)
    cat = d.get("categoria", "giallo")
    return (cat if cat in CATEGORIE else "giallo"), str(d.get("motivo", ""))


def controlla(giorni: int = 3, max_msg: int = 40, usa_ai: bool = True) -> dict:
    m = _imap()
    try:
        m.select("INBOX", readonly=True)
        since = (date.today() - timedelta(days=giorni)).strftime("%d-%b-%Y")
        _, ids = m.search(None, f'(SINCE "{since}")')
        uids = ids[0].split()[-max_msg:]
        nuovi = opt_out = 0
        ai_ok = usa_ai and llm.disponibile()
        for i in reversed(uids):
            _, data = m.fetch(i, "(BODY.PEEK[] UID)")
            raw = next((d[1] for d in data if isinstance(d, tuple)), None)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            mid = msg.get("Message-ID") or f"no-id-{i.decode()}"
            if db.q("SELECT 1 FROM posta WHERE uid=?", (mid,)):
                continue
            mitt, ogg = _dec(msg.get("From")), _dec(msg.get("Subject"))
            corpo = _corpo(msg)
            allarmi = safety.segnali_sospetti(f"{ogg} {corpo}")
            cat, motivo = classifica_regole(mitt, ogg, corpo, msg)
            if not cat:
                if ai_ok:
                    try:
                        cat, motivo = classifica_ai(mitt, ogg, corpo)
                    except llm.LLMError:
                        cat, motivo = "giallo", "da classificare (AI non disponibile)"
                else:
                    cat, motivo = "giallo", "da classificare"
            if allarmi and cat != "bianco":
                cat = "stop" if len(allarmi) >= 2 else cat
                motivo = f"{motivo} | ATTENZIONE: {', '.join(allarmi)}"
            # opt-out automatico registrato
            addr = parseaddr(mitt)[1]
            if OPT_OUT_RX.search(corpo[:300]):
                n = db.x("UPDATE aziende SET opt_out=1, stato='Opt-out' WHERE lower(email)=lower(?)", (addr,))
                if n:
                    opt_out += 1
                    db.x("UPDATE registro_contatti SET opt_out=1, data_opt_out=? WHERE lower(referente)=lower(?)",
                         (db.now(), addr))
            db.insert("posta", {"uid": mid, "message_id": mid, "mittente": mitt, "oggetto": ogg,
                                "data": _dec(msg.get("Date")), "anteprima": safety.maschera(corpo[:4000]),
                                "categoria": cat, "motivo": motivo, "allarme": ", ".join(allarmi)})
            # risposta da un contatto in pipeline → stato "Risposta"
            db.x("UPDATE pipeline SET stato='Risposta', ultimo_contatto=? WHERE lower(contatto)=lower(?) AND stato='Contattato'",
                 (db.now(), addr))
            nuovi += 1
    finally:
        try:
            m.logout()
        except Exception:
            pass
    db.log("posta", f"Controllo posta: {nuovi} nuovi messaggi, {opt_out} opt-out registrati")
    return {"nuovi": nuovi, "opt_out": opt_out}


def _componi(b: dict) -> EmailMessage:
    s = load_settings()
    msg = EmailMessage()
    msg["From"] = f"{s['nome']} <{vault.get_cred('imap_user') or s['email']}>"
    msg["To"] = b["destinatario"]
    msg["Subject"] = b["oggetto"]
    msg["Message-ID"] = make_msgid(domain="gasparepettinati.it")
    if b.get("in_risposta_a"):
        msg["In-Reply-To"] = b["in_risposta_a"]
        msg["References"] = b["in_risposta_a"]
    msg.set_content(b["corpo"])
    return msg


def salva_in_bozze_casella(bozza_id: int) -> dict:
    """Copia la bozza nella cartella Bozze della casella (così si può inviare anche dal webmail)."""
    b = db.q("SELECT * FROM bozze WHERE id=?", (bozza_id,))[0]
    if not b["destinatario"]:
        return {"ok": False, "errore": "Manca il destinatario."}
    m = _imap()
    try:
        cartella = load_settings()["cartella_bozze"]
        m.append(cartella, r"(\Draft)", imaplib.Time2Internaldate(time.time()), bytes(_componi(b)))
    finally:
        m.logout()
    db.update("bozze", bozza_id, {"note": (b["note"] or "") + " | copiata in Bozze della casella"})
    return {"ok": True}


def invia_approvata(bozza_id: int) -> dict:
    s = load_settings()
    b = db.q("SELECT * FROM bozze WHERE id=?", (bozza_id,))[0]
    if b["stato"] != "approvata":
        return {"ok": False, "errore": "La bozza deve essere prima approvata."}
    if not b["destinatario"] or "@" not in b["destinatario"]:
        return {"ok": False, "errore": "Destinatario email mancante o non valido."}
    dest = parseaddr(b["destinatario"])[1]
    if safety.email_in_opt_out(dest):
        return {"ok": False, "errore": "Il destinatario ha chiesto di non essere contattato (opt-out)."}
    if b["tipo"] == "proposta_pmi" and safety.pmi_quota_residua() <= 0:
        return {"ok": False, "errore": f"Raggiunto il limite di {s['max_pmi_giorno']} nuovi contatti PMI oggi."}
    with _smtp() as smtp:
        smtp.send_message(_componi(b))
    esito = "inviato"
    db.log("posta", f"Inviata bozza {bozza_id} a {dest}")
    db.update("bozze", bozza_id, {"stato": "inviata", "inviato": db.now()})
    _dopo_invio(b, dest, esito)
    return {"ok": True, "esito": esito}


def _dopo_invio(b: dict, dest: str, esito: str) -> None:
    oggi = db.now()
    canale = "email"
    if b["tipo"] == "proposta_pmi":
        a = db.q("SELECT * FROM aziende WHERE id=?", (b["rif_id"],))
        if a:
            a = a[0]
            db.insert("registro_contatti", {"data": oggi, "azienda": a["nome"], "referente": dest,
                                            "fonte_dato": a["fonte_dato"], "base_giuridica": "Legittimo interesse (B2B, art. 6.1.f GDPR)",
                                            "canale": canale, "rif_bozza": b["id"]}, ignore=False)
            db.update("aziende", a["id"], {"stato": "Contattato"})
            _pipeline_upsert("cliente", a["nome"], dest, a["sito"], "OpenStreetMap")
    elif b["tipo"] == "candidatura":
        o = db.q("SELECT * FROM opportunita WHERE id=?", (b["rif_id"],))
        if o:
            o = o[0]
            db.update("opportunita", o["id"], {"stato": "Candidato"})
            _pipeline_upsert("lavoro", o["azienda"], dest, o["link"], o["fonte"])
    elif b["tipo"] == "follow_up":
        db.x("UPDATE pipeline SET solleciti=solleciti+1, ultimo_contatto=? WHERE id=?", (oggi, b["rif_id"]))


def _pipeline_upsert(tipo, azienda, contatto, link, fonte):
    esiste = db.q("SELECT id FROM pipeline WHERE azienda=? AND tipo=?", (azienda, tipo))
    giorni = load_settings()["follow_up_giorni"]
    prossimo = (date.today() + timedelta(days=giorni)).isoformat()
    if esiste:
        db.update("pipeline", esiste[0]["id"], {"ultimo_contatto": db.now(), "data_prossimo": prossimo})
    else:
        db.insert("pipeline", {"tipo": tipo, "azienda": azienda, "contatto": contatto, "canale": "email",
                               "stato": "Contattato", "primo_contatto": db.now(), "ultimo_contatto": db.now(),
                               "prossimo_passo": "Follow-up se nessuna risposta", "data_prossimo": prossimo,
                               "fonte": fonte, "link": link}, ignore=False)

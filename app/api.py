"""API locale (solo 127.0.0.1) usata dall'interfaccia."""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .core import db, llm, vault
from .core.config import APP_NAME, DATA, UI_DIR, VERSION, load_settings, save_settings
from .modules import (assistente, attivita, bozze, browser, lavoro, pianificatore, pmi, portali, posta, progetti,
                      report, sistema)

# token di sessione: solo la finestra dell'app lo conosce (protegge da altri siti aperti nel browser)
TOKEN = secrets.token_urlsafe(24)
app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)


def auth(x_token: str = Header(default="")):
    if not secrets.compare_digest(x_token, TOKEN):
        raise HTTPException(401, "Non autorizzato")


def ok(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except llm.LLMError as e:
        raise HTTPException(503, str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.log("api", f"{fn.__name__}: {e}", "errore")
        raise HTTPException(500, str(e))


@app.get("/", response_class=HTMLResponse)
def index():
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    return html.replace("__TOKEN__", TOKEN).replace("__VERSION__", VERSION)


app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
A = [Depends(auth)]


# ---------- stato e impostazioni ----------
@app.get("/api/stato", dependencies=A)
def stato():
    return {"numeri": report.numeri(), "modelli": llm.modelli(), "impostazioni": load_settings(),
            "credenziali": vault.stato(), "pianificazione": pianificatore.stato(), "cartella_dati": str(DATA),
            "avvio_automatico": sistema.avvio_automatico_attivo()}


@app.post("/api/impostazioni", dependencies=A)
def imposta(data: dict = Body(...)):
    s = save_settings(data)
    pianificatore.avvia()
    return s


@app.post("/api/credenziali", dependencies=A)
def credenziali(data: dict = Body(...)):
    for k, v in data.items():
        if k in vault.CAMPI and v is not None:
            vault.set_cred(k, v)
    return vault.stato()


@app.post("/api/avvio-automatico", dependencies=A)
def avvio_auto(data: dict = Body(...)):
    return ok(sistema.imposta_avvio_automatico, bool(data.get("attivo")))


@app.get("/api/eventi", dependencies=A)
def eventi():
    return db.q("SELECT * FROM eventi ORDER BY id DESC LIMIT 200")


# ---------- lavoro ----------
@app.post("/api/lavoro/cerca", dependencies=A)
def lavoro_cerca(data: dict = Body(default={})):
    return ok(lavoro.cerca, usa_ai=data.get("ai", True), max_ai=int(data.get("max_ai", 8)))


@app.get("/api/lavoro", dependencies=A)
def lavoro_lista(min: float = 0, stato: str = ""):
    sql = "SELECT * FROM opportunita WHERE punteggio>=?"
    p: list = [min]
    if stato:
        sql += " AND stato=?"
        p.append(stato)
    return db.q(sql + " ORDER BY punteggio DESC, id DESC LIMIT 300", p)


@app.get("/api/lavoro/ricerche", dependencies=A)
def lavoro_ricerche():
    return lavoro.ricerche_browser()


@app.post("/api/lavoro/{oid}/stato", dependencies=A)
def lavoro_stato(oid: int, data: dict = Body(...)):
    db.update("opportunita", oid, {"stato": data["stato"]})
    return {"ok": True}


@app.post("/api/lavoro/{oid}/candidatura", dependencies=A)
def lavoro_candidatura(oid: int):
    return ok(bozze.candidatura, oid)


@app.post("/api/lavoro/{oid}/linkedin", dependencies=A)
def lavoro_linkedin(oid: int):
    return ok(bozze.messaggio_linkedin, oid)


# ---------- PMI ----------
@app.get("/api/pmi/settori", dependencies=A)
def pmi_settori():
    return list(pmi.SETTORI)


@app.post("/api/pmi/cerca", dependencies=A)
def pmi_cerca(data: dict = Body(...)):
    return ok(pmi.cerca_osm, data["settore"], data["citta"].strip(), int(data.get("limite", 40)))


@app.get("/api/pmi", dependencies=A)
def pmi_lista():
    return db.q("SELECT * FROM aziende ORDER BY CASE stato WHEN 'Analizzata' THEN 0 WHEN 'Nuovo' THEN 1 ELSE 2 END, id DESC LIMIT 500")


@app.post("/api/pmi/{aid}/analizza", dependencies=A)
def pmi_analizza(aid: int):
    return ok(pmi.analizza, aid)


@app.post("/api/pmi/{aid}/proposta", dependencies=A)
def pmi_proposta(aid: int):
    return ok(bozze.proposta_pmi, aid)


@app.post("/api/pmi/{aid}/aggiorna", dependencies=A)
def pmi_aggiorna(aid: int, data: dict = Body(...)):
    campi = {k: v for k, v in data.items() if k in ("email", "stato", "opt_out")}
    db.update("aziende", aid, campi)
    return {"ok": True}


# ---------- bozze ----------
@app.get("/api/bozze", dependencies=A)
def bozze_lista(stato: str = "da_approvare"):
    return db.q("SELECT * FROM bozze WHERE stato=? ORDER BY id DESC", (stato,))


@app.post("/api/bozze/{bid}", dependencies=A)
def bozza_salva(bid: int, data: dict = Body(...)):
    campi = {k: v for k, v in data.items() if k in ("destinatario", "oggetto", "corpo", "stato", "note")}
    if campi.get("stato") not in (None, "da_approvare", "approvata", "scartata"):
        raise HTTPException(400, "Stato non valido")
    db.update("bozze", bid, campi)
    return {"ok": True}


@app.post("/api/bozze/{bid}/invia", dependencies=A)
def bozza_invia(bid: int):
    return ok(posta.invia_approvata, bid)


@app.post("/api/bozze/{bid}/in-casella", dependencies=A)
def bozza_casella(bid: int):
    return ok(posta.salva_in_bozze_casella, bid)


# ---------- posta ----------
@app.post("/api/posta/controlla", dependencies=A)
def posta_controlla(data: dict = Body(default={})):
    return ok(posta.controlla, giorni=int(data.get("giorni", 7)), max_ai=int(data.get("max_ai", 10)))


@app.post("/api/posta/prova", dependencies=A)
def posta_prova():
    return ok(posta.prova_connessione)


@app.get("/api/posta", dependencies=A)
def posta_lista(tutte: int = 0):
    sql = "SELECT * FROM posta" + ("" if tutte else " WHERE gestita=0")
    return db.q(sql + " ORDER BY CASE categoria WHEN 'rosso' THEN 0 WHEN 'stop' THEN 1 WHEN 'arancio' THEN 2 WHEN 'giallo' THEN 3 ELSE 4 END, id DESC LIMIT 200")


@app.post("/api/posta/{pid}/risposta", dependencies=A)
def posta_risposta(pid: int):
    return ok(bozze.risposta_email, pid)


@app.post("/api/posta/{pid}/gestita", dependencies=A)
def posta_gestita(pid: int):
    db.update("posta", pid, {"gestita": 1})
    return {"ok": True}


# ---------- pipeline ----------
@app.get("/api/pipeline", dependencies=A)
def pipe_lista():
    return db.q("SELECT * FROM pipeline ORDER BY data_prossimo IS NULL, data_prossimo, id DESC")


@app.post("/api/pipeline", dependencies=A)
def pipe_nuovo(data: dict = Body(...)):
    campi = {k: v for k, v in data.items() if k in ("tipo", "azienda", "contatto", "canale", "stato", "prossimo_passo",
                                                    "data_prossimo", "valore", "fonte", "link", "note")}
    pid = data.get("id")
    if pid:
        db.update("pipeline", int(pid), campi)
    else:
        campi.setdefault("stato", "Nuovo")
        campi["primo_contatto"] = db.now()
        pid = db.insert("pipeline", campi, ignore=False)
    return {"ok": True, "id": pid}


@app.post("/api/pipeline/{pid}/follow-up", dependencies=A)
def pipe_follow(pid: int):
    return ok(bozze.follow_up, pid)


@app.post("/api/export", dependencies=A)
def export():
    f = ok(report.esporta_excel)
    sistema.apri(f)
    return {"file": f}


@app.post("/api/report/{tipo}", dependencies=A)
def genera_report(tipo: str):
    return ok(report.report, tipo)


# ---------- chat ----------
@app.get("/api/chat", dependencies=A)
def chat_storia():
    return assistente.storia()


@app.delete("/api/chat", dependencies=A)
def chat_svuota():
    assistente.svuota()
    return {"ok": True}


@app.post("/api/chat", dependencies=A)
def chat_invia(data: dict = Body(...)):
    domanda = (data.get("testo") or "").strip()[:4000]
    if not domanda:
        raise HTTPException(400, "Messaggio vuoto")
    msgs = assistente.messaggi(domanda)          # costruito prima di salvare la domanda (niente doppioni)
    assistente.salva("utente", domanda)
    rapido = assistente.comando(domanda)

    def gen():
        if rapido:
            assistente.salva("assistente", rapido)
            yield rapido
            return
        out = []
        try:
            for pezzo in llm.chat_stream(msgs):
                out.append(pezzo)
                yield pezzo
        except Exception as e:
            msg = f"\n\n⚠️ {e}"
            out.append(msg)
            yield msg
        assistente.salva("assistente", "".join(out))
    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


# ---------- cose da fare ----------
@app.get("/api/attivita", dependencies=A)
def att_lista(giorno: str = ""):
    return attivita.lista(giorno or None)


@app.post("/api/attivita", dependencies=A)
def att_nuova(data: dict = Body(...)):
    titolo = (data.get("titolo") or "").strip()
    if not titolo:
        raise HTTPException(400, "Titolo vuoto")
    return {"id": attivita.aggiungi(titolo, data.get("ora", ""), data.get("giorno") or None, data.get("dettaglio", ""))}


@app.post("/api/attivita/{aid}", dependencies=A)
def att_segna(aid: int, data: dict = Body(...)):
    if data.get("elimina"):
        attivita.elimina(aid)
    else:
        attivita.segna(aid, bool(data.get("fatto")))
    return {"ok": True}


# ---------- LinkedIn / Indeed ----------
def _portale(p: str) -> str:
    if p not in portali.PORTALI:
        raise HTTPException(404, "Portale sconosciuto")
    return p


@app.post("/api/portali/{p}/collega", dependencies=A)
def portale_collega(p: str):
    return ok(portali.collega, _portale(p))


@app.post("/api/portali/stato", dependencies=A)
def portali_stato():
    return ok(portali.stato)


@app.post("/api/portali/{p}/cerca", dependencies=A)
def portale_cerca(p: str, data: dict = Body(default={})):
    return ok(portali.cerca_e_importa, _portale(p), data.get("parole") or load_settings()["ricerche_portali"][0])


@app.post("/api/portali/importa", dependencies=A)
def portali_importa():
    return ok(portali.importa_pagina)


@app.post("/api/lavoro/{oid}/analizza", dependencies=A)
def lavoro_analizza(oid: int):
    return ok(portali.analizza_opportunita, oid)


# ---------- browser e gestionale ----------
@app.post("/api/browser/apri", dependencies=A)
def br_apri(data: dict = Body(...)):
    url = data["url"]
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL non valido")
    return ok(browser.apri, url)


@app.post("/api/browser/analizza", dependencies=A)
def br_analizza():
    p = ok(browser.leggi_pagina)
    return ok(lavoro.analizza_testo_annuncio, p["testo"], p["url"])


@app.post("/api/browser/google", dependencies=A)
def br_google():
    return ok(browser.collega_google)


@app.post("/api/browser/avvia", dependencies=A)
def br_avvia():
    ok(browser.avvia_browser)
    return browser.stato_browser()


@app.post("/api/browser/ripara", dependencies=A)
def br_ripara():
    return ok(browser.ripara)


@app.post("/api/browser/chiudi", dependencies=A)
def br_chiudi():
    return ok(browser.chiudi)


@app.post("/api/crm/login", dependencies=A)
def crm_login():
    return ok(browser.login_crm)


@app.post("/api/crm/leggi", dependencies=A)
def crm_leggi(data: dict = Body(default={})):
    return ok(browser.leggi_tabelle, data.get("url") or None)


@app.get("/api/crm/lead", dependencies=A)
def crm_lead():
    return db.q("SELECT * FROM lead_crm ORDER BY id DESC LIMIT 500")


# ---------- progetti GitHub ----------
def _err_progetti(fn, *a, **kw):
    try:
        return ok(fn, *a, **kw)
    except HTTPException as e:
        raise HTTPException(400 if e.status_code == 500 else e.status_code, e.detail)


@app.get("/api/progetti", dependencies=A)
def progetti_lista():
    return {"progetti": progetti.elenco(), "github": progetti.stato_github()}


@app.post("/api/progetti/carica", dependencies=A)
async def progetti_carica(request: Request, nome: str, pulisci: int = 0):
    if not nome.lower().endswith(".zip"):
        raise HTTPException(400, "Serve un file .zip")
    tmp = progetti.nuovo_file_temporaneo()
    letti = 0
    try:
        with open(tmp, "wb") as f:
            async for pezzo in request.stream():
                letti += len(pezzo)
                if letti > progetti.MAX_ZIP:
                    raise HTTPException(413, "ZIP troppo grande (massimo 1 GB)")
                f.write(pezzo)
        return _err_progetti(progetti.carica_zip, tmp, nome, bool(pulisci))
    finally:
        tmp.unlink(missing_ok=True)


@app.get("/api/progetti/{slug}", dependencies=A)
def progetti_dettaglio(slug: str):
    return _err_progetti(progetti.dettaglio, slug)


@app.post("/api/progetti/{slug}/prepara", dependencies=A)
def progetti_prepara(slug: str, data: dict = Body(default={})):
    return _err_progetti(progetti.prepara, slug, data.get("pulisci"))


@app.post("/api/progetti/{slug}/pubblica", dependencies=A)
def progetti_pubblica(slug: str, data: dict = Body(...)):
    if data.get("conferma") is not True:
        raise HTTPException(400, "Serve la conferma")
    return _err_progetti(progetti.pubblica, slug, data.get("nome_repo", ""), data.get("descrizione", ""),
                         bool(data.get("pubblico")))


@app.post("/api/progetti/{slug}/rendi-pubblico", dependencies=A)
def progetti_pubblico(slug: str, data: dict = Body(...)):
    if data.get("conferma") is not True:
        raise HTTPException(400, "Serve la conferma")
    return _err_progetti(progetti.rendi_pubblico, slug)


@app.post("/api/progetti/{slug}/cartella", dependencies=A)
def progetti_cartella(slug: str):
    return _err_progetti(progetti.apri_cartella, slug)


@app.delete("/api/progetti/{slug}", dependencies=A)
def progetti_elimina(slug: str):
    return _err_progetti(progetti.elimina, slug)


@app.get("/api/file", dependencies=A)
def apri_file(percorso: str):
    try:
        file_path = Path(percorso).resolve()
        file_path.relative_to(DATA.resolve())
    except (OSError, RuntimeError, ValueError):
        raise HTTPException(403, "File non accessibile")
    if not file_path.is_file():
        raise HTTPException(404, "File non trovato")
    return FileResponse(file_path)

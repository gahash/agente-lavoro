"""Pubblicazione automatica dei post LinkedIn (testo + immagine) con l'API ufficiale "Share on LinkedIn".

È l'unico modo consentito da LinkedIn per pubblicare senza clic: Gaspare crea una volta un'app su
linkedin.com/developers, inserisce Client ID e Client Secret nelle Impostazioni e preme "Collega LinkedIn".
Il token (valido circa 60 giorni) resta nel Portachiavi. All'ora prevista i post approvati del giorno
escono da soli con la loro grafica.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from datetime import date
from urllib.parse import quote, urlencode

import httpx

from ..core import db, vault
from ..core.config import load_settings
from . import linkedin_post

REDIRECT = "http://localhost:8000/api/linkedin/oauth"
SCOPE = "openid profile w_member_social"
_stati: dict[str, float] = {}          # parametri "state" emessi, per verificare il ritorno da LinkedIn


def _versione() -> str:
    return load_settings().get("linkedin_api_versione", "202605")


def _token() -> dict | None:
    t = vault.get_cred("linkedin_token")
    try:
        t = json.loads(t) if t else None
    except ValueError:
        return None
    return t if t and t.get("scade", 0) > time.time() + 60 else None


def stato() -> dict:
    t = _token()
    return {"configurato": bool(vault.get_cred("linkedin_client_id") and vault.get_cred("linkedin_client_secret")),
            "collegato": bool(t), "nome": (t or {}).get("nome", ""), "redirect": REDIRECT,
            "scade": date.fromtimestamp(t["scade"]).isoformat() if t else ""}


def url_collega() -> str:
    cid = vault.get_cred("linkedin_client_id")
    if not cid or not vault.get_cred("linkedin_client_secret"):
        raise RuntimeError("Inserisci Client ID e Client Secret di LinkedIn nelle Impostazioni")
    st = secrets.token_urlsafe(16)
    _stati[st] = time.time()
    return "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(
        {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT, "state": st, "scope": SCOPE})


def _salva_token(token: str, durata: float) -> dict:
    """Verifica il token chiedendo a LinkedIn chi è l'utente, poi lo salva nel Portachiavi."""
    r = httpx.get("https://api.linkedin.com/v2/userinfo", timeout=30, headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 401:
        raise RuntimeError("LinkedIn non riconosce il token: generane uno nuovo con i permessi openid, profile e w_member_social")
    r.raise_for_status()
    me = r.json()
    vault.set_cred("linkedin_token", json.dumps({"token": token, "scade": time.time() + durata,
                                                 "autore": f"urn:li:person:{me['sub']}", "nome": me.get("name", "")}))
    db.log("linkedin", f"LinkedIn collegato per la pubblicazione automatica ({me.get('name', '')})")
    return stato()


def usa_token(token: str) -> dict:
    """Token incollato a mano dal generatore di LinkedIn (OAuth 2.0 tools): vale 60 giorni."""
    token = (token or "").strip()
    if not token:
        raise RuntimeError("Incolla il token di accesso generato su LinkedIn")
    return _salva_token(token, 60 * 86400)


def completa(code: str, state: str) -> dict:
    """Ritorno da LinkedIn dopo il consenso: scambia il codice con il token e lo salva nel Portachiavi."""
    if time.time() - _stati.pop(state, 0) > 900:
        raise RuntimeError("Richiesta scaduta o non valida: riprova da Impostazioni → Collega LinkedIn")
    r = httpx.post("https://www.linkedin.com/oauth/v2/accessToken", timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": vault.get_cred("linkedin_client_id"), "client_secret": vault.get_cred("linkedin_client_secret")})
    r.raise_for_status()
    d = r.json()
    return _salva_token(d["access_token"], d.get("expires_in", 60 * 86400))


def scollega() -> dict:
    vault.set_cred("linkedin_token", "")
    db.log("linkedin", "LinkedIn scollegato")
    return stato()


def _testo(t: str) -> str:
    """Il campo del post usa il formato "little text": i caratteri riservati vanno protetti, gli hashtag marcati."""
    t = re.sub(r"([\\|{}@\[\]()<>#*_~])", r"\\\1", t)
    return re.sub(r"\\#(\w+)", r"{hashtag|\\#|\1}", t)


def _sessione() -> tuple[dict, dict]:
    t = _token()
    if not t:
        raise RuntimeError("LinkedIn non è collegato (o il collegamento è scaduto): Impostazioni → Collega LinkedIn")
    return t, {"Authorization": f"Bearer {t['token']}", "LinkedIn-Version": _versione(), "X-Restli-Protocol-Version": "2.0.0"}


def _crea_post(c: httpx.Client, h: dict, autore: str, testo: str, titolo: str, media: str) -> dict:
    r = c.post("https://api.linkedin.com/rest/posts", headers=h, json={
        "author": autore, "commentary": _testo(testo), "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "content": {"media": {"title": titolo or "Post", "id": media}},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False})
    if r.status_code >= 400:
        raise RuntimeError(f"LinkedIn ha rifiutato il post ({r.status_code}): {r.text[:300]}")
    urn = r.headers.get("x-restli-id", "")
    return {"ok": True, "urn": urn, "url": f"https://www.linkedin.com/feed/update/{urn}/" if urn else ""}


def pubblica(pid: int) -> dict:
    p = db.q("SELECT tema, testo, stato FROM post_linkedin WHERE id=?", (pid,))[0]
    if p["stato"] == "pubblicato":
        return {"ok": True, "gia": True}
    t, h = _sessione()
    with httpx.Client(timeout=60) as c:
        r = c.post("https://api.linkedin.com/rest/images?action=initializeUpload", headers=h,
                   json={"initializeUploadRequest": {"owner": t["autore"]}})
        r.raise_for_status()
        up = r.json()["value"]
        c.put(up["uploadUrl"], headers={"Authorization": h["Authorization"]},
              content=linkedin_post.grafica(pid).read_bytes()).raise_for_status()
        esito = _crea_post(c, h, t["autore"], p["testo"], p["tema"], up["image"])
    linkedin_post.aggiorna(pid, {"stato": "pubblicato"})
    db.x("UPDATE attivita SET fatto=1, fatto_il=? WHERE uid LIKE ? AND fatto=0", (db.now(), f"%|linkedin|{pid}"))
    db.log("linkedin", f"Post pubblicato su LinkedIn con immagine: {p['tema']}")
    return esito


def pubblica_video(vid: int, attesa: float = 300) -> dict:
    """Carica l'MP4 a pezzi (Videos API), aspetta che LinkedIn lo elabori e pubblica il post con il video."""
    from . import video_brevi
    v = db.q("SELECT tema, testo, stato FROM video_brevi WHERE id=?", (vid,))[0]
    if v["stato"] == "pubblicato":
        return {"ok": True, "gia": True}
    dati = video_brevi.monta(vid).read_bytes()
    t, h = _sessione()
    with httpx.Client(timeout=120) as c:
        r = c.post("https://api.linkedin.com/rest/videos?action=initializeUpload", headers=h, json={
            "initializeUploadRequest": {"owner": t["autore"], "fileSizeBytes": len(dati),
                                        "uploadCaptions": False, "uploadThumbnail": False}})
        r.raise_for_status()
        up = r.json()["value"]
        parti = []
        for istr in up["uploadInstructions"]:
            rp = c.put(istr["uploadUrl"], headers={"Authorization": h["Authorization"]},
                       content=dati[istr["firstByte"]:istr["lastByte"] + 1])
            rp.raise_for_status()
            parti.append(rp.headers.get("etag", "").strip('"'))
        c.post("https://api.linkedin.com/rest/videos?action=finalizeUpload", headers=h, json={
            "finalizeUploadRequest": {"video": up["video"], "uploadToken": up.get("uploadToken", ""),
                                      "uploadedPartIds": parti}}).raise_for_status()
        fine = time.time() + attesa
        while True:                                      # LinkedIn deve elaborare il video prima del post
            st = c.get(f"https://api.linkedin.com/rest/videos/{quote(up['video'])}", headers=h).json().get("status")
            if st == "AVAILABLE":
                break
            if st == "PROCESSING_FAILED" or time.time() > fine:
                raise RuntimeError(f"LinkedIn non ha elaborato il video (stato: {st})")
            time.sleep(5)
        esito = _crea_post(c, h, t["autore"], v["testo"], v["tema"], up["video"])
    video_brevi.aggiorna(vid, {"stato": "pubblicato"})
    db.log("linkedin", f"Video pubblicato su LinkedIn: {v['tema']}")
    return esito


def pubblica_di_oggi() -> dict:
    """Routine: pubblica post e video approvati con data di oggi (o passata). Senza collegamento non fa nulla."""
    from . import video_brevi
    if not load_settings().get("linkedin_auto", True) or not _token():
        return {"ok": True, "pubblicati": 0}
    n = 0
    for tipo, lista, fn in (("post", linkedin_post.di_oggi(), pubblica), ("video", video_brevi.di_oggi(), pubblica_video)):
        for p in lista:
            try:
                fn(p["id"])
                n += 1
            except Exception as e:
                db.log("linkedin", f"Pubblicazione {tipo} non riuscita «{p['tema']}»: {e}", "errore")
    return {"ok": True, "pubblicati": n}

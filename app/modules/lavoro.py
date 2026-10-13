"""Modulo A — Ricerca opportunità di lavoro da fonti pubbliche con API/RSS ufficiali.

LinkedIn, Indeed, InfoJobs ecc. non vengono "raschiati": l'app apre le ricerche nel browser e
Gaspare può far analizzare l'annuncio aperto con "Analizza pagina" (vedi modules/browser.py).
"""
from __future__ import annotations

import html
import re
from urllib.parse import quote_plus

import feedparser
import httpx
from bs4 import BeautifulSoup

from ..core import db, llm, safety
from ..core.config import load_settings

UA = {"User-Agent": "AgenteLavoro/1.0 (ricerca personale; contatto: info@gasparepettinati.it)"}


def _testo(h: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(h or "", "html.parser").get_text(" ")).strip()


_CP1252 = "ŒœŠšŸŽžƒˆ˜–—‘-„†-•…‰‹›€™"
_MOJIBAKE = re.compile(f"[Â-ô][\u0080-¿{_CP1252}]+")


def _byte(ch: str) -> bytes:
    try:
        return ch.encode("cp1252")
    except UnicodeError:
        return ch.encode("latin-1")          # byte non definiti in cp1252 (es. \x8d) restano come Latin-1


def _ripara(s: str | None) -> str:
    """Remote OK manda testi UTF-8 decodificati come cp1252 (es. 'grabaciÃ³n'): ripara ogni pezzo rovinato."""
    s = s or ""

    def fix(m: re.Match) -> str:
        try:
            return b"".join(_byte(c) for c in m.group(0)).decode("utf-8")
        except UnicodeError:
            return m.group(0)
    for _ in range(3):                      # alcuni testi sono codificati male più volte
        nuovo = _MOJIBAKE.sub(fix, s)
        if nuovo == s:
            break
        s = nuovo
    return re.sub(r"Â(?=\s|$)", "", s)      # spazio non separabile perso: resta solo la 'Â'


# ---------------- fonti ----------------
def fonte_remoteok() -> list[dict]:
    r = httpx.get("https://remoteok.com/api", headers=UA, timeout=30)
    out = []
    for j in r.json()[1:]:
        out.append({"fonte": "Remote OK", "uid": f"rok-{j.get('id')}", "azienda": _ripara(j.get("company")),
                    "ruolo": _ripara(j.get("position")), "link": j.get("url"), "remoto": "Sì (100%)",
                    "compenso": f"{j.get('salary_min') or ''}-{j.get('salary_max') or ''} USD".strip("- USD"),
                    "requisiti": ", ".join(j.get("tags") or []),
                    "descrizione": _ripara(_testo(j.get("description")))[:3000],
                    "tipo": "", "contatto": ""})
    return out


def fonte_remotive(ricerca: str) -> list[dict]:
    r = httpx.get(f"https://remotive.com/api/remote-jobs?category=software-dev&search={quote_plus(ricerca)}&limit=50",
                  headers=UA, timeout=30)
    return [{"fonte": "Remotive", "uid": f"rmt-{j['id']}", "azienda": j.get("company_name"), "ruolo": j.get("title"),
             "link": j.get("url"), "remoto": f"Sì ({j.get('candidate_required_location') or 'mondo'})",
             "compenso": j.get("salary") or "", "tipo": j.get("job_type") or "",
             "requisiti": ", ".join(j.get("tags") or []), "descrizione": _testo(j.get("description"))[:3000],
             "contatto": ""} for j in r.json().get("jobs", [])]


def fonte_himalayas() -> list[dict]:
    r = httpx.get("https://himalayas.app/jobs/api?limit=50", headers=UA, timeout=30)
    out = []
    for j in r.json().get("jobs", []):
        loc = ", ".join(j.get("locationRestrictions") or []) or "mondo"
        comp = ""
        if j.get("minSalary"):
            comp = f"{j.get('minSalary')}-{j.get('maxSalary') or ''} {j.get('currency') or ''}"
        out.append({"fonte": "Himalayas", "uid": f"him-{j.get('guid') or j.get('applicationLink')}",
                    "azienda": j.get("companyName"), "ruolo": j.get("title"),
                    "link": j.get("applicationLink") or j.get("guid"), "remoto": f"Sì ({loc})", "compenso": comp,
                    "tipo": j.get("employmentType") or "", "requisiti": ", ".join(j.get("categories") or []),
                    "descrizione": _testo(j.get("description") or j.get("excerpt"))[:3000], "contatto": ""})
    return out


def fonte_wwr() -> list[dict]:
    out = []
    for cat in ("remote-full-stack-programming-jobs", "remote-back-end-programming-jobs"):
        f = feedparser.parse(httpx.get(f"https://weworkremotely.com/categories/{cat}.rss", headers=UA, timeout=30).text)
        for e in f.entries:
            titolo = html.unescape(e.get("title", ""))
            azienda, _, ruolo = titolo.partition(": ")
            out.append({"fonte": "We Work Remotely", "uid": f"wwr-{e.get('id') or e.get('link')}",
                        "azienda": azienda, "ruolo": ruolo or titolo, "link": e.get("link"),
                        "remoto": f"Sì ({e.get('region', 'mondo')})", "compenso": "", "tipo": e.get("type", ""),
                        "requisiti": "", "descrizione": _testo(e.get("summary"))[:3000], "contatto": ""})
    return out


def fonte_arbeitnow() -> list[dict]:
    r = httpx.get("https://www.arbeitnow.com/api/job-board-api", headers=UA, timeout=30)
    return [{"fonte": "Arbeitnow (EU)", "uid": f"arb-{j['slug']}", "azienda": j.get("company_name"),
             "ruolo": j.get("title"), "link": j.get("url"),
             "remoto": "Sì" if j.get("remote") else f"No ({j.get('location')})", "compenso": "",
             "tipo": ", ".join(j.get("job_types") or []), "requisiti": ", ".join(j.get("tags") or []),
             "descrizione": _testo(j.get("description"))[:3000], "contatto": ""}
            for j in r.json().get("data", []) if j.get("remote")]


EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)


def _annuncio_hn(c: dict) -> dict | None:
    """Un commento del thread "Who is hiring?": prima riga "Azienda | Ruolo | Luogo | REMOTE | ...".
    Si tengono solo gli annunci da remoto con un'email a cui candidarsi (spesso scritta come "nome [at] dominio")."""
    t = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<p>", "\n", c.get("text") or "")))
    t = re.sub(r"\s*[\[({<]\s*at\s*[\])}>]\s*", "@", t, flags=re.I)
    t = re.sub(r"\s*[\[({<]\s*dot\s*[\])}>]\s*", ".", t, flags=re.I)
    parti = [x.strip() for x in t.split("\n")[0].split("|")]
    remoto = next((x for x in parti if re.search(r"\bremote\b", x, re.I)), "")
    email = EMAIL_RX.findall(t)
    if len(parti) < 2 or not remoto or not email:
        return None
    if re.search(r"\b(us|usa|u\.s\.?|canada|north america|americas?)\b", remoto, re.I) and not OK_LOC.search(
            re.sub(r"\bremote\b", "", remoto, flags=re.I)):
        return None                                        # "Remote US", "REMOTE (US/Canada)": non aperto all'Italia
    luogo = re.search(r"\(([^)]*)\)", remoto)
    return {"fonte": "Hacker News", "uid": f"hn-{c['id']}", "azienda": parti[0][:120], "ruolo": parti[1][:160],
            "link": f"https://news.ycombinator.com/item?id={c['id']}", "remoto": f"Sì ({luogo.group(1) if luogo else remoto})",
            "compenso": next((x for x in parti if re.search(r"[$€£]\s?\d", x)), ""), "tipo": "",
            "requisiti": "", "descrizione": t[:3000], "contatto": email[0]}


def fonte_hn() -> list[dict]:
    """Thread mensile "Ask HN: Who is hiring?" (API pubblica di Algolia): annunci con email diretta."""
    r = httpx.get("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10",
                  headers=UA, timeout=30)
    thread = next(h for h in r.json()["hits"] if h["title"].startswith("Ask HN: Who is hiring?"))
    item = httpx.get(f"https://hn.algolia.com/api/v1/items/{thread['objectID']}", headers=UA, timeout=60).json()
    return [a for a in map(_annuncio_hn, item.get("children") or []) if a]


FONTI = {"Remote OK": fonte_remoteok, "Himalayas": fonte_himalayas, "We Work Remotely": fonte_wwr,
         "Arbeitnow": fonte_arbeitnow, "Hacker News": fonte_hn}


def ricerche_browser() -> list[dict]:
    """Ricerche pronte da aprire nel browser (portali senza API pubblica)."""
    q = quote_plus("sviluppatore full stack python")
    return [
        {"nome": "LinkedIn — sviluppatore remoto Italia", "url": "https://www.linkedin.com/jobs/search/?keywords=sviluppatore%20full%20stack&location=Italia&f_WT=2"},
        {"nome": "Indeed — full stack da remoto", "url": f"https://it.indeed.com/jobs?q={q}&l=da+remoto"},
        {"nome": "InfoJobs — sviluppatore", "url": "https://www.infojobs.it/offerte-lavoro/sviluppatore-full-stack"},
        {"nome": "Glassdoor — full stack Italia", "url": "https://www.glassdoor.it/Lavoro/italia-full-stack-developer-lavori-SRCH_IL.0,6_IN120_KO7,27.htm"},
        {"nome": "Wellfound — remote", "url": "https://wellfound.com/role/r/full-stack-engineer"},
        {"nome": "Malt — profilo freelance", "url": "https://www.malt.it/"},
        {"nome": "Upwork — AI automation", "url": "https://www.upwork.com/nx/search/jobs/?q=ai%20automation%20python"},
    ]


# ---------------- punteggio ----------------
OK_LOC = re.compile(r"mondo|world|anywhere|global|europe|europa|\beu\b|emea|ital|cet|gmt\+[12]|100%|remote", re.I)


USA_ONLY = re.compile(r"\b(us only|usa only|u\.s\. only|americas only|must be based in the us|us citizens?)\b", re.I)
COLLAB_RX = re.compile(r"freelance|contractor|\bcontract\b|collaborazion|consulenz|p\.? ?iva|partita iva|\bb2b\b|"
                       r"a progetto|prestazione occasionale|ritenuta d'acconto", re.I)


def ammesso(o: dict) -> tuple[bool, str]:
    """Si tengono solo i lavori completamente da remoto aperti all'Italia e le collaborazioni (freelance/P.IVA)."""
    if not load_settings().get("solo_remoto_o_collaborazione", True):
        return True, ""
    testo = " ".join(str(o.get(k) or "") for k in ("ruolo", "tipo", "requisiti", "descrizione"))
    rem = str(o.get("remoto") or "").strip().lower()
    loc = rem[rem.find("(") + 1:rem.rfind(")")] if "(" in rem else ""
    if rem.startswith(("sì", "si")) and loc and not OK_LOC.search(loc):   # remoto riservato ad altri paesi
        return False, f"remoto solo per: {loc[:60]}"
    if COLLAB_RX.search(testo):
        return True, "collaborazione"
    if not rem.startswith(("sì", "si", "yes", "remote", "100%")):
        return False, f"non da remoto ({o.get('remoto') or 'non indicato'})"
    if USA_ONLY.search(testo):
        return False, "remoto solo per residenti USA"
    if re.search(r"ibrid|hybrid", rem):
        return False, "ibrido"
    return True, "smart working"


def pre_punteggio(o: dict, s: dict) -> tuple[float, list[str]]:
    testo = " ".join(str(o.get(k) or "") for k in ("ruolo", "requisiti", "descrizione")).lower()
    motivi, p = [], 0.0
    rem = str(o.get("remoto", "")).lower()
    if rem.startswith("sì"):
        loc = rem[rem.find("(") + 1:rem.rfind(")")] if "(" in rem else ""
        if not loc or OK_LOC.search(loc):
            p += 2.5
            motivi.append("remoto, aperto all'Italia")
        else:
            p -= 3
            motivi.append(f"remoto ma solo per: {loc[:60]}")
        if USA_ONLY.search(testo):
            p -= 2
            motivi.append("richiesta residenza USA")
    hit = [k for k in s["parole_chiave"] if re.search(rf"\b{re.escape(k)}\b", testo)]
    p += min(2.5, 0.6 * len(hit))
    if hit:
        motivi.append("stack: " + ", ".join(hit[:6]))
    if o.get("compenso"):
        p += 1.5
        motivi.append("compenso indicato")
    if re.search(r"senior|lead|staff|principal", (o.get("ruolo") or "").lower()):
        p += 0.5
    if re.search(r"contract|freelance|contractor|part[- ]time|p\.? ?iva", testo + (o.get("tipo") or "").lower()):
        p += 1
        motivi.append("compatibile P.IVA/contratto")
    else:
        p += 0.5
    if o.get("azienda"):
        p += 1
    if len(o.get("descrizione") or "") > 400:
        p += 1
    return round(min(10, max(1, p)), 1), motivi


def valuta_con_ai(o: dict) -> dict:
    s = load_settings()
    sys = ("Sei un consulente di carriera. Valuta quanto l'annuncio è adatto al candidato. "
           "Rispondi SOLO in JSON: {\"punteggio\": numero 1-10, \"motivazione\": \"max 2 frasi in italiano\", "
           "\"sospetto\": true/false, \"requisiti_chiave\": \"max 6 voci separate da virgola\"}")
    user = (f"Candidato: {s['headline']}. Competenze: {', '.join(s['competenze'])}. "
            f"Contratti accettati: {', '.join(s['contratti'])}. Accetta solo lavori completamente da remoto (smart working dall'Italia) o collaborazioni freelance/P.IVA.\n\nAnnuncio:\n"
            + llm.dati(f"Azienda: {o.get('azienda')}\nRuolo: {o.get('ruolo')}\nRemoto: {o.get('remoto')}\n"
                       f"Compenso: {o.get('compenso')}\nTipo: {o.get('tipo')}\n{o.get('descrizione')}", 3500))
    return llm.chat_json(sys, user, max_tokens=250)


def cerca(usa_ai: bool = True, max_ai: int = 8, fonti: list[str] | None = None) -> dict:
    s = load_settings()
    nuovi, errori = 0, []
    raccolti: list[dict] = []
    for nome, fn in FONTI.items():
        if fonti and nome not in fonti:
            continue
        try:
            raccolti += fn()
        except Exception as e:
            errori.append(f"{nome}: {e}")
    try:
        for kw in ("python", "full stack"):
            raccolti += fonte_remotive(kw)
    except Exception as e:
        errori.append(f"Remotive: {e}")

    candidati_ai, esclusi = [], 0
    for o in raccolti:
        if not o.get("link") or not o.get("ruolo"):
            continue
        if not ammesso(o)[0]:
            esclusi += 1
            continue
        sosp = safety.segnali_sospetti(f"{o.get('descrizione')} {o.get('azienda')}")
        p, motivi = pre_punteggio(o, s)
        o.update({"punteggio": 0 if sosp else p,
                  "motivazione": ("SOSPETTO: " + ", ".join(sosp)) if sosp else "; ".join(motivi),
                  "sospetto": 1 if sosp else 0})
        rid = db.insert("opportunita", o)
        if rid:
            nuovi += 1
            if not sosp and p >= 5.5:
                candidati_ai.append((p, rid, o))

    valutati = 0
    if usa_ai and llm.disponibile():
        for p, rid, o in sorted(candidati_ai, key=lambda t: -t[0])[:max_ai]:
            try:
                v = valuta_con_ai(o)
                punt = float(v.get("punteggio", p))
                upd = {"punteggio": round((punt * 0.6 + p * 0.4), 1),
                       "motivazione": f"AI: {v.get('motivazione', '')} | regole: {o['motivazione']}"}
                if v.get("requisiti_chiave"):
                    upd["requisiti"] = str(v["requisiti_chiave"])[:300]
                if v.get("sospetto") is True:
                    upd.update({"sospetto": 1, "punteggio": 0})
                db.update("opportunita", rid, upd)
                valutati += 1
            except Exception as e:
                errori.append(f"AI: {e}")
                break
    db.log("lavoro", f"Ricerca: {len(raccolti)} annunci letti, {esclusi} esclusi (né remoto né collaborazione), "
                     f"{nuovi} nuovi, {valutati} valutati con AI")
    return {"letti": len(raccolti), "esclusi": esclusi, "nuovi": nuovi, "valutati_ai": valutati, "errori": errori}


def scarta_non_ammessi() -> int:
    """Mette in 'Scartato' gli annunci ancora da valutare che non sono né da remoto né collaborazioni."""
    n = 0
    for o in db.q("SELECT * FROM opportunita WHERE stato='Nuovo'"):
        ok_, motivo = ammesso(o)
        if not ok_:
            db.update("opportunita", o["id"], {"stato": "Scartato", "motivazione": f"Escluso: {motivo} | {o['motivazione'] or ''}"[:1000]})
            n += 1
    if n:
        db.log("lavoro", f"{n} annunci scartati: né da remoto né collaborazioni")
    return n


def valuta_testo(testo: str, o: dict) -> dict:
    """Rivaluta un annuncio già salvato leggendo il testo completo. Restituisce i campi da aggiornare."""
    sys = ("Estrai i dati dell'annuncio di lavoro. Rispondi SOLO in JSON con chiavi: tipo, remoto (es. 'Sì (Italia)' o "
           "'No (Milano)' o 'Ibrido (Roma)'), compenso, requisiti (max 8 voci separate da virgola), contatto, "
           "descrizione (riassunto max 600 caratteri).")
    d = llm.chat_json(sys, llm.dati(testo, 6000), max_tokens=500)
    agg = {**o}
    for k in ("tipo", "remoto", "compenso", "requisiti", "contatto"):
        if d.get(k):
            agg[k] = str(d[k])[:300]
    agg["descrizione"] = str(d.get("descrizione") or testo[:1500])
    if agg.get("remoto", "").lower().startswith("si"):
        agg["remoto"] = "Sì" + agg["remoto"][2:]
    sosp = safety.segnali_sospetti(testo)
    p, motivi = pre_punteggio(agg, load_settings())
    try:
        v = valuta_con_ai(agg)
        p = round(float(v.get("punteggio", p)) * 0.6 + p * 0.4, 1)
        motivi.insert(0, "AI: " + str(v.get("motivazione", "")))
        sosp += ["segnalato dall'AI"] if v.get("sospetto") is True else []
    except llm.LLMError:
        pass
    ok_, motivo = ammesso(agg)
    extra = {} if ok_ else {"stato": "Scartato"}
    return {k: agg[k] for k in ("tipo", "remoto", "compenso", "requisiti", "contatto", "descrizione")} | {
        "punteggio": 0 if sosp else p, "sospetto": 1 if sosp else 0,
        "motivazione": ("SOSPETTO: " + ", ".join(sosp)) if sosp else
                       ("; ".join(motivi) if ok_ else f"Escluso: {motivo} | " + "; ".join(motivi))} | extra


def analizza_testo_annuncio(testo: str, link: str = "") -> dict:
    """Usato da 'Analizza pagina' del browser per annunci LinkedIn/Indeed/InfoJobs."""
    sys = ("Estrai i dati dell'annuncio di lavoro. Rispondi SOLO in JSON con chiavi: azienda, ruolo, tipo, "
           "remoto, compenso, requisiti, contatto, descrizione (max 600 caratteri), è_un_annuncio (true/false).")
    d = llm.chat_json(sys, llm.dati(testo, 6000), max_tokens=500)
    if not d.get("è_un_annuncio", True):
        return {"ok": False, "errore": "La pagina non sembra un annuncio di lavoro."}
    o = {k: str(d.get(k) or "") for k in ("azienda", "ruolo", "tipo", "remoto", "compenso", "requisiti", "contatto", "descrizione")}
    o.update({"fonte": "Browser", "uid": f"web-{link}", "link": link})
    if o["remoto"] and not o["remoto"].lower().startswith(("sì", "si", "no")):
        o["remoto"] = ("Sì " if re.search(r"remot|smart|ovunque|anywhere", o["remoto"].lower()) else "No ") + f"({o['remoto']})"
    o["remoto"] = o["remoto"].replace("Si", "Sì", 1) if o["remoto"].startswith("Si") else o["remoto"]
    sosp = safety.segnali_sospetti(testo)
    p, motivi = pre_punteggio(o, load_settings())
    try:
        v = valuta_con_ai(o)
        p = round(float(v.get("punteggio", p)) * 0.6 + p * 0.4, 1)
        motivi.insert(0, "AI: " + str(v.get("motivazione", "")))
    except Exception:
        pass
    o.update({"punteggio": 0 if sosp else p, "sospetto": 1 if sosp else 0,
              "motivazione": ("SOSPETTO: " + ", ".join(sosp)) if sosp else "; ".join(motivi)})
    ok_, motivo = ammesso(o)
    if not ok_:
        o.update({"stato": "Scartato", "motivazione": f"Escluso: {motivo} | {o['motivazione']}"})
    rid = db.insert("opportunita", o)
    return {"ok": True, "id": rid, **o}

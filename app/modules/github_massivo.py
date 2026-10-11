"""Caricamento in blocco su GitHub, dall'app.

- Collega GitHub: scarica la GitHub CLI se manca (solo in dati/strumenti) e apre il Terminale per l'accesso.
- Importa una cartella (es. ~/Desktop/GitHub_Ready): ogni sottocartella diventa un progetto dell'app,
  copiato SENZA dump, database, CSV/Excel, audio, PDF, screenshot, .env, dipendenze e file oltre 95 MB,
  poi ripulito (segreti e dati personali sostituiti) e analizzato.
- Pubblica privati: carica come repository PRIVATI solo i progetti con controllo pulito
  (nessun segreto, nessun dato personale residuo).
- Pubblica vetrine: repository PUBBLICI con solo README + LICENSE, più il README del profilo.
Tutto gira in background; lo stato si legge con stato().
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

import httpx

from ..core import db
from ..core.config import BASE, DATA
from . import progetti

STRUMENTI = DATA / "strumenti"
VETRINE = BASE / "vetrine"
SOLO_DATI = {"billing-engine-data", "quality-audit-operator", "ripensamenti-audio-archive", "ticket-system-legacy"}
CARTELLE_NO = progetti.CARTELLE_ESCLUSE | {".tools", "storage", "registrazioni", "_archive", "archive", "old_monolith_bak",
                                           "output", "release", "staticfiles", ".private", ".claude", "Host mia-vm",
                                           "campioni_voce", "documentazione_legale_societaria", "data", "dati",
                                           ".npm-cache", "test-results", "playwright-report", ".turbo", ".parcel-cache",
                                           "dataset", "valutati", "audio", "voices", "models", "trascrizioni", "cache", ".playwright-cli"}
EST_NO = {".mp3", ".wav", ".ogg", ".m4a", ".mp4", ".mov", ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf", ".phar",
          ".apk", ".aab", ".exe", ".dmg", ".docx", ".doc", ".odt"}
# nomi di clienti/fornitori da non pubblicare mai nelle vetrine: uno per riga in dati/nomi_riservati.txt
# (file locale, fuori da git: l'elenco stesso è riservato)
def _nomi_riservati() -> re.Pattern | None:
    f = DATA / "nomi_riservati.txt"
    nomi = [r.strip() for r in f.read_text(encoding="utf-8").splitlines() if r.strip()] if f.exists() else []
    return re.compile("|".join(re.escape(n).replace(r"\ ", " ?") for n in nomi), re.I) if nomi else None

JOB: dict = {"attivo": False, "fase": "", "fatti": 0, "totale": 0, "log": []}
_lock = threading.Lock()


def _log(msg: str) -> None:
    JOB["log"] = (JOB["log"] + [msg])[-200:]
    db.log("github", msg)


def stato() -> dict:
    return {"github": progetti.stato_github(), "job": JOB,
            "vetrine": sorted(p.name for p in VETRINE.glob("*-showcase") if (p / "README.md").exists())}


# ---------------------------------------------------------------- GitHub CLI
def gh() -> str:
    try:
        return progetti._gh()
    except RuntimeError:
        pass
    for p in sorted(STRUMENTI.glob("gh*/bin/gh")) + [Path("/usr/local/bin/gh"), Path("/opt/homebrew/bin/gh")]:
        if p.exists():
            return str(p)
    if sys.platform != "darwin":
        raise RuntimeError("GitHub CLI (gh) non è installata.")
    rel = httpx.get("https://api.github.com/repos/cli/cli/releases/latest", timeout=30, follow_redirects=True).json()
    url = next(a["browser_download_url"] for a in rel["assets"] if a["name"].endswith("_macOS_amd64.zip"))
    STRUMENTI.mkdir(parents=True, exist_ok=True)
    z = STRUMENTI / "gh.zip"
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r, open(z, "wb") as f:
        for b in r.iter_bytes():
            f.write(b)
    with zipfile.ZipFile(z) as zz:
        zz.extractall(STRUMENTI)
    z.unlink()
    exe = next(STRUMENTI.glob("gh*/bin/gh"))
    exe.chmod(0o755)
    db.log("github", f"GitHub CLI scaricata in {exe}")
    return str(exe)


def _run(args: list[str], cwd: Path | None = None, timeout: int = 1800) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": os.environ.get("PATH", "") + ":/usr/local/bin:/opt/homebrew/bin:/usr/bin",
           "GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env,
                          stdin=subprocess.DEVNULL)


def collega() -> dict:
    g = shutil.which("git") or "/usr/bin/git"
    if _run([g, "--version"], timeout=30).returncode:
        return {"ok": False, "errore": "Git non è pronto: nel Terminale esegui  xcode-select --install  e riprova."}
    exe = gh()
    s = progetti.stato_github()
    if s.get("collegato"):
        _run([exe, "auth", "setup-git"], timeout=60)
        return {"ok": True, "collegato": True, "messaggio": f"GitHub già collegato come {s['account']} ✅"}
    cmd = f"'{exe}' auth login --web --git-protocol https --hostname github.com && '{exe}' auth setup-git && echo && echo 'Fatto: torna su Agente Lavoro'"
    if sys.platform == "darwin":
        script = f'tell application "Terminal" to do script "{cmd.replace(chr(34), chr(92) + chr(34))}"'
        subprocess.Popen(["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'])
        return {"ok": True, "collegato": False, "messaggio": "Si è aperto il Terminale: premi Invio, accedi a GitHub nel browser con il codice mostrato, poi torna qui e premi di nuovo 'Collega GitHub'."}
    return {"ok": False, "errore": f"Apri un terminale e lancia: {cmd}"}


# ---------------------------------------------------------------- anonimizzazione aggiuntiva (dati di clienti e dipendenti)
RX_POD = re.compile(r"\bIT\d{3}E\d{8}\b")
RX_PDR = re.compile(r"(?<!\d)\d{14}(?!\d)")
RX_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
EMAIL_OK = re.compile(r"(?i)@(?:example\.|esempio\.|test\.|localhost|users\.noreply\.github\.com)|^(?:no-?reply|info@gasparepettinati)")
RX_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
NOMI_FILE_DATI = re.compile(r"(?i)(contratt|anagrafic|clienti?[_\-.]|lead[s]?[_\-.]|export|estrazion|^mail[-_])")
EST_DATI = {".json", ".txt", ".md", ".xml", ".yaml", ".yml", ".ndjson", ".jsonl"}
LOCK = {"package-lock.json", "composer.lock", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock"}


IP_PRIVATI = re.compile(r"^(?:127\.|0\.|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.|255\.|203\.0\.113\.|8\.8\.|1\.1\.1\.1)")
RX_PERCORSI = [
    (re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+"), "/home/utente"),
    (re.compile(r"(?i)C:\\Users\\[A-Za-z0-9._ -]+"), r"C:\\Users\\utente"),
    (re.compile(r"/var/www/(?:vhosts/)?[A-Za-z0-9._-]+"), "/var/www/app"),
    (re.compile(r"/opt/(?!homebrew)[A-Za-z0-9._-]+"), "/opt/app"),
    (re.compile(r"/etc/(?!ssl|nginx|apache2|systemd|hosts|passwd)([A-Za-z0-9._-]+)/[A-Za-z0-9._-]+\.env"), "/etc/app/app.env"),
]
RX_SSH = re.compile(r"\b[A-Za-z0-9._-]+@(?:\d{1,3}\.){3}\d{1,3}\b")


def _domini_riservati() -> re.Pattern | None:
    f = DATA / "domini_riservati.txt"
    dom = [r.strip().lower() for r in f.read_text(encoding="utf-8").splitlines() if r.strip()] if f.exists() else []
    return re.compile(r"(?i)\b(?:[a-z0-9-]+\.)*(?:" + "|".join(re.escape(d) for d in dom) + r")\b") if dom else None


def anonimizza_server(testo: str) -> str:
    """Toglie i riferimenti ai server reali: IP pubblici, accessi ssh, domini aziendali, percorsi e utenti."""
    t = RX_SSH.sub("utente@203.0.113.10", testo)
    t = RX_IP.sub(lambda m: m.group(0) if (IP_PRIVATI.match(m.group(0)) or any(int(x) > 255 for x in m.group(0).split(".")))
                  else "203.0.113.10", t)
    rx = _domini_riservati()
    if rx:
        t = rx.sub(lambda m: (m.group(0).split(".")[0] + ".example.com") if m.group(0).count(".") >= 2 else "example.com", t)
    for r, sost in RX_PERCORSI:
        t = r.sub(sost, t)
    return t


def anonimizza(codice: Path, rimuovi=None) -> dict:
    """Toglie file di dati (contratti, anagrafiche, liste di IP/email) e sostituisce POD, PDR ed email reali."""
    rimuovi = rimuovi or progetti._rimuovi
    tolti, sostituiti = [], 0
    for p in list(codice.rglob("*")):
        if not p.is_file() or p.name in LOCK or ".git" in p.parts:
            continue
        rel = str(p.relative_to(codice))
        if p.suffix.lower() in EST_DATI and NOMI_FILE_DATI.search(p.name) and p.name.lower() not in ("readme.md",):
            tolti.append(rel); rimuovi(p); continue
        if p.suffix.lower() in EST_DATI:
            try:
                grezzo = p.read_bytes()[:20_000_000].decode("utf-8", "ignore")
            except OSError:
                grezzo = ""
            if p.stat().st_size > 3_000_000 or len(RX_IP.findall(grezzo)) > 50 or len(RX_EMAIL.findall(grezzo)) > 50:
                tolti.append(rel + " (dati: IP/email/file grande)"); rimuovi(p); continue
        letto = progetti._leggi_testo(p)
        if not letto:
            continue
        testo, enc = letto
        righe = [r for r in testo.splitlines() if r.strip()]
        if p.suffix.lower() in EST_DATI and len(righe) > 20 and \
                sum(bool(RX_IP.search(r) or RX_EMAIL.search(r)) for r in righe) > 0.3 * len(righe):
            tolti.append(rel + " (elenco di IP/email)"); rimuovi(p); continue
        nuovo = anonimizza_server(RX_POD.sub("IT000E00000000", testo))
        nuovo = "\n".join(RX_PDR.sub("00000000000000", r) if re.search(r"(?i)pdr|remi|gas", r) else r
                          for r in nuovo.split("\n"))
        nuovo = RX_EMAIL.sub(lambda m: m.group(0) if EMAIL_OK.search(m.group(0)) else "utente@example.com", nuovo)
        if nuovo != testo:
            sostituiti += 1
            p.write_text(nuovo, encoding=enc, newline="")
    return {"tolti": tolti, "file_modificati": sostituiti}


# ---------------------------------------------------------------- 1. importa una cartella
def _ignora(dirpath: str, nomi: list[str]) -> set[str]:
    out = set()
    for n in nomi:
        p = Path(dirpath) / n
        if p.is_symlink():
            out.add(n)
        elif p.is_dir():
            if n in CARTELLE_NO or n.startswith("_corrotti"):
                out.add(n)
        elif (progetti._escluso_file(n) or p.suffix.lower() in EST_NO or n.lower().startswith(("screenshot", "schermata"))
              or p.stat().st_size > progetti.MAX_FILE_GITHUB):
            out.add(n)
    return out


def _importa(radice: Path) -> None:
    cartelle = [d for d in sorted(radice.iterdir()) if d.is_dir() and not d.name.startswith(".") and d.name not in SOLO_DATI]
    JOB.update(totale=len(cartelle), fatti=0)
    for d in cartelle:
        slug = progetti._slug(d.name)
        dest = progetti._dir(slug)
        try:
            if (dest / "meta.json").exists() and progetti._leggi_meta(slug).get("repo"):
                _log(f"{d.name}: già su GitHub, salto")
                continue
            if dest.exists():
                progetti._rimuovi(dest)
            shutil.copytree(d, dest / "codice", ignore=_ignora, symlinks=False)
            progetti._scrivi_meta(slug, {"slug": slug, "nome": d.name, "file_zip": f"cartella {d}", "caricato": db.now(),
                                         "pulisci": True, "repo": None, "pulizia": None, "analisi": None, "origine": "cartella"})
            an = anonimizza(dest / "codice")
            _log(f"{d.name}: tolti {len(an['tolti'])} file di dati, anonimizzati {an['file_modificati']} file")
            v = progetti.prepara(slug, True)
            a = v["analisi"]
            _log(f"{d.name}: {a['n_file']} file, {a['peso_mb']} MB · segreti {a['n_critici']} · dati personali {a['n_personali']}"
                 f" → {'pronto' if a['ok_privato'] and not a['n_personali'] else 'da sistemare'}")
        except Exception as e:
            _log(f"{d.name}: errore {e}")
        finally:
            JOB["fatti"] += 1
    _log(f"Importazione finita: {len(cartelle)} progetti (esclusi perché contengono solo dati: {', '.join(sorted(SOLO_DATI))})")


# ---------------------------------------------------------------- 2. pubblica privati
def _descrizione(nome: str) -> str:
    mappa = {"energy-crm-platform": "erpcrm-energy", "ai-voice-agent": "ai-sales-voice-agent", "voice-assistant-sara": "customer-care-voice-agent",
             "call-quality-analytics": "call-quality-ai", "otp-signature-blockchain": "otp-e-signature",
             "offerta-activation-app": "energy-offer-activation", "pec-manager-service": "pec-ai-assistant",
             "pec-automation-service": "pec-ai-assistant", "sms-gateway-service": "sms-gateway",
             "raccomandata-tracker": "registered-mail-monitor", "social-crm-platform": "social-lead-platform",
             "hr-assunzioni-manager": "recruiting-portal"}
    f = VETRINE / f"{mappa.get(nome, '-')}-showcase" / ".descrizione"
    return (f.read_text(encoding="utf-8").strip() if f.exists() else nome.replace("-", " ").capitalize()) + " (codice privato)"


def _pubblica_privati() -> None:
    lista = [p for p in progetti.elenco() if not p.get("repo") and str(p.get("file_zip", "")).startswith("cartella ")]
    JOB.update(totale=len(lista), fatti=0)
    _run([gh(), "auth", "setup-git"], timeout=60)
    for p in lista:
        try:
            anonimizza(progetti._dir(p["slug"]) / "codice")          # ripasso di sicurezza subito prima
            a = progetti.analizza(progetti._dir(p["slug"]) / "codice")
            if not a["ok_privato"] or a["n_personali"]:
                _log(f"{p['nome']}: NON caricato (segreti {a['n_critici']}, dati personali {a['n_personali']}, "
                     f"file bloccati {len(a['grandi']) + len(a['sensibili'])}) — apri il progetto, controlla e premi Rianalizza")
                continue
            v = progetti.pubblica(p["slug"], p["slug"], _descrizione(p["nome"]), pubblico=False)
            _log(f"{p['nome']}: 🔒 privato su {v['repo']['url']}")
        except Exception as e:
            _log(f"{p['nome']}: errore {str(e)[:300]}")
        finally:
            JOB["fatti"] += 1


# ---------------------------------------------------------------- 3. pubblica vetrine + profilo
def _push_file(exe: str, repo: str, file: dict[str, Path], descrizione: str, messaggio: str) -> str:
    g = shutil.which("git") or "/usr/bin/git"
    u = progetti._identita_github()
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "r"
        if _run([exe, "repo", "view", f"{u['login']}/{repo}"], timeout=60).returncode == 0:
            r = _run([exe, "repo", "clone", f"{u['login']}/{repo}", str(d)], timeout=300)
            if r.returncode:
                raise RuntimeError(r.stderr.strip()[-300:])
        else:
            r = _run([exe, "repo", "create", f"{u['login']}/{repo}", "--public", "--description", descrizione[:300]], timeout=120)
            if r.returncode:
                raise RuntimeError(r.stderr.strip()[-300:])
            d.mkdir()
            _run([g, "init", "-q", "-b", "main"], cwd=d)
            _run([g, "remote", "add", "origin", f"https://github.com/{u['login']}/{repo}.git"], cwd=d)
        for nome, src in file.items():
            shutil.copy(src, d / nome)
        for args in (["config", "user.name", u.get("name") or u["login"]], ["config", "user.email", u["email"]],
                     ["add", *file.keys()]):
            _run([g, *args], cwd=d)
        r = _run([g, "commit", "-q", "-m", messaggio], cwd=d)
        if r.returncode:
            return "già aggiornato"
        r = _run([g, "push", "-q", "-u", "origin", "HEAD:main"], cwd=d, timeout=300)
        if r.returncode:
            raise RuntimeError(r.stderr.strip()[-300:])
    return f"https://github.com/{u['login']}/{repo}"


def _controlla_testo(p: Path) -> list[str]:
    t = p.read_text(encoding="utf-8")
    rx = _nomi_riservati()
    trovati = [m.group(0) for m in rx.finditer(t)] if rx else []
    trovati += [t[s:e] for tipo, grav, _r, s, e in progetti._trova(t, ".md") if grav in ("critico", "personale")]
    return trovati


def _pubblica_vetrine() -> None:
    exe = gh()
    _run([exe, "auth", "setup-git"], timeout=60)
    cartelle = sorted(p for p in VETRINE.glob("*-showcase") if (p / "README.md").exists() and (p / ".descrizione").exists())
    JOB.update(totale=len(cartelle) + 1, fatti=0)
    for d in cartelle:
        try:
            extra = sorted(x.name for x in d.iterdir() if x.name not in ("README.md", "LICENSE", ".descrizione"))
            problemi = _controlla_testo(d / "README.md")
            if extra or problemi:
                _log(f"{d.name}: NON pubblicata (file in più: {extra} · da togliere: {problemi[:5]})")
                continue
            url = _push_file(exe, d.name, {"README.md": d / "README.md", "LICENSE": d / "LICENSE"},
                             (d / ".descrizione").read_text(encoding="utf-8").strip(), "Scheda del progetto")
            _log(f"{d.name}: 🌍 {url}")
        except Exception as e:
            _log(f"{d.name}: errore {str(e)[:300]}")
        finally:
            JOB["fatti"] += 1
    prof = VETRINE / "profilo-github" / "README.md"
    try:
        if prof.exists() and not _controlla_testo(prof):
            login = progetti._identita_github()["login"]
            url = _push_file(exe, login, {"README.md": prof}, "Profilo GitHub", "Profilo: casi di studio aziendali")
            _log(f"Profilo: {url}")
        else:
            _log("Profilo: NON aggiornato (contenuto da controllare)")
    except Exception as e:
        _log(f"Profilo: errore {str(e)[:300]}")
    finally:
        JOB["fatti"] += 1


# ---------------------------------------------------------------- avvio in background
def avvia(fase: str, **kw) -> dict:
    def _tutto():
        _pubblica_privati()
        _pubblica_vetrine()
    funzioni = {"importa": _importa, "privati": _pubblica_privati, "vetrine": _pubblica_vetrine, "tutto": _tutto}
    with _lock:
        if JOB["attivo"]:
            return {"ok": False, "errore": f"È già in corso: {JOB['fase']}"}
        JOB.update(attivo=True, fase=fase, fatti=0, totale=0, log=[])

    def lavoro():
        try:
            funzioni[fase](**kw)
        except Exception as e:
            _log(f"Interrotto: {e}")
        finally:
            JOB["attivo"] = False
    threading.Thread(target=lavoro, daemon=True, name=f"github-{fase}").start()
    return {"ok": True, "messaggio": "Avviato: segui l'avanzamento qui sotto."}

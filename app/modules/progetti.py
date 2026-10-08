"""Progetti GitHub: carica uno ZIP, controlla segreti e dati personali, (se scelto) lo ripulisce,
poi lo pubblica con `gh`. Il repository nasce privato; diventa pubblico solo con una conferma esplicita
e solo se il controllo non trova più nulla di critico.

Regole:
- la cronologia git contenuta nello ZIP non viene mai caricata (può contenere segreti già rimossi);
- file sensibili (.env, chiavi, database, dump, log...) sono sempre esclusi con .gitignore;
  con "Pulisci" vengono anche cancellati dalla copia di lavoro;
- con "Pulisci" i segreti e i dati personali trovati nei file di testo vengono sostituiti da segnaposto;
- l'analisi guarda esattamente i file che git caricherebbe.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shutil
import stat
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from ..core import db
from ..core.config import DATA, load_settings, save_settings

PROGETTI = DATA / "progetti"
PROGETTI.mkdir(parents=True, exist_ok=True)

MAX_ZIP = 1024 ** 3                 # 1 GB compresso
MAX_ESTRATTO = 3 * 1024 ** 3        # 3 GB estratto
MAX_FILE_NEL_ZIP = 60_000
MAX_FILE_GITHUB = 95 * 1024 ** 2    # GitHub rifiuta i file oltre 100 MB
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------- cosa non va mai caricato
CARTELLE_ESCLUSE = {".git", ".svn", ".hg", "node_modules", "vendor", ".venv", "venv", "env", "__pycache__",
                    "dist", "build", ".next", ".nuxt", ".expo", ".gradle", ".idea", ".vs", "logs", "log",
                    "uploads", "recordings", "backup", "backups", "coverage", ".pytest_cache", ".mypy_cache",
                    ".cache", ".terraform", "__MACOSX"}
FILE_SENSIBILI = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "id_rsa*",
                  "id_ed25519*", "*.ppk", "google-services.json", "GoogleService-Info.plist", "credentials*.json",
                  "client_secret*.json", "service-account*.json", "token.json", "tokens.json", ".npmrc", ".pypirc",
                  ".netrc", ".htpasswd", "*.sqlite", "*.sqlite3", "*.db", "*.sql", "*.dump", "*.bak", "*.log",
                  "*.csv", "*.xlsx", "*.xls", ".DS_Store", "Thumbs.db", "desktop.ini"]
ECCEZIONI = [".env.example", ".env.sample", ".env.template", ".env.dist"]

GITIGNORE = """# --- Segreti ---
.env
.env.*
!.env.example
!.env.sample
*.pem
*.key
*.p12
*.pfx
*.keystore
*.jks
id_rsa*
id_ed25519*
*.ppk
google-services.json
GoogleService-Info.plist
credentials*.json
client_secret*.json
service-account*.json
token.json
tokens.json
.npmrc
.pypirc
.netrc
.htpasswd

# --- Dati ---
*.sqlite
*.sqlite3
*.db
*.sql
*.dump
*.bak
*.csv
*.xlsx
*.xls
uploads/
recordings/
backup/
backups/

# --- Dipendenze / build ---
node_modules/
vendor/
.venv/
venv/
env/
__pycache__/
dist/
build/
.next/
.nuxt/
.expo/
.gradle/
coverage/
.pytest_cache/
.mypy_cache/
.cache/
.terraform/

# --- Log / IDE / OS ---
*.log
logs/
log/
.idea/
.vs/
.DS_Store
Thumbs.db
desktop.ini
__MACOSX/
"""

# ---------------------------------------------------------------- cosa cercare nei file
EST_BINARIE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svgz", ".pdf", ".zip", ".gz", ".tgz",
               ".7z", ".rar", ".mp4", ".mov", ".avi", ".mp3", ".wav", ".ogg", ".woff", ".woff2", ".ttf", ".otf",
               ".eot", ".exe", ".dll", ".so", ".dylib", ".apk", ".aab", ".jar", ".class", ".pyc", ".lock", ".psd",
               ".ai", ".sketch", ".fig", ".docx", ".pptx", ".odt", ".bin", ".wasm"}
EST_CONFIG = {"", ".env", ".ini", ".cfg", ".conf", ".properties", ".toml", ".yaml", ".yml", ".example", ".sample",
              ".local", ".production", ".development", ".sh", ".bat", ".ps1", ".txt"}
EST_TESTO_DOC = {".md", ".txt", ".html", ".htm", ".rst", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".xml"}
SEGNAPOSTO = "***RIMOSSO***"

# (gravità, regex, gruppo da sostituire: 0 = tutto, "v" = solo il valore)
#   critico  -> blocca sempre la pubblicazione
#   personale -> blocca la pubblicazione come pubblico
#   avviso    -> solo segnalato
CONTROLLI: dict[str, tuple[str, re.Pattern, object]] = {
    "Chiave privata": ("critico", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----"), 0),
    "Chiave API LLM": ("critico", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), 0),
    "Chiave OpenAI": ("critico", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), 0),
    "Chiave Google": ("critico", re.compile(r"AIza[0-9A-Za-z_\-]{35}"), 0),
    "Chiave AWS": ("critico", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    "Token GitHub": ("critico", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"), 0),
    "Chiave Stripe": ("critico", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9a-zA-Z]{20,}"), 0),
    "Twilio": ("critico", re.compile(r"\b(?:AC|SK)[0-9a-f]{32}\b"), 0),
    "Token Slack": ("critico", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}"), 0),
    "Token Telegram": ("critico", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b"), 0),
    "Token Meta/WhatsApp": ("critico", re.compile(r"\bEAA[A-Za-z0-9]{50,}"), 0),
    "JWT": ("critico", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), 0),
    "Connessione DB con password": ("critico", re.compile(
        r"(?i)\b(?:mysql|mariadb|postgres(?:ql)?|mongodb(?:\+srv)?|redis|amqp)://[^\s:'\"/@]+:(?P<v>[^\s@'\"]+)@"), "v"),
    "Password in chiaro": ("critico", re.compile(
        r"""(?i)(?:\b|_)(?:password|passwd|pwd|pass|db_pass(?:word)?|smtp_pass(?:word)?)['"]?\s*(?:=>|[:=])\s*['"](?P<v>[^'"\s$]{4,})['"]"""), "v"),
    # solo nei file di configurazione (vedi EST_CONFIG): valori senza virgolette tipo  DB_PASSWORD=abc  /  password: abc
    "Segreto in configurazione": ("critico", re.compile(
        r"(?im)^\s*(?:export\s+)?[\w.\-]*(?:password|passwd|pwd|pass|secret|api_?key|apikey|token|private_?key)[\w.\-]*"
        r"[ \t]*[:=][ \t]*(?P<v>[^\s#'\"$%{}()\[\],;<>]{4,})[ \t]*$"), "v"),
    "Segreto/API key": ("critico", re.compile(
        r"""(?i)(?:api[_-]?key|apikey|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|private[_-]?key|client[_-]?secret)['"]?\s*(?:=>|[:=])\s*['"](?P<v>[A-Za-z0-9_\-./+=]{16,})['"]"""), "v"),
    "IBAN": ("critico", re.compile(r"\bIT\s?\d{2}\s?[A-Z]\s?(?:\d\s?){10}(?:[A-Z0-9]\s?){11}[A-Z0-9]\b"), 0),
    "Codice fiscale": ("critico", re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPRST]\d{2}[A-Z]\d{3}[A-Z]\b"), 0),
    "Telefono": ("personale", re.compile(r"(?<![\w+])(?:\+|00)39[ .\-]?\d{2,4}[ .\-]?\d{3,4}[ .\-]?\d{3,4}(?!\d)"), 0),
    "Cellulare": ("personale", re.compile(r"(?<![\w.])3\d{2}[ .\-]?\d{3}[ .\-]?\d{3,4}(?![\w.])"), 0),
    "Email personale": ("personale", re.compile(
        r"\b[A-Za-z0-9._%+\-]+@(?:gmail|googlemail|hotmail|outlook|live|libero|yahoo|icloud|me|virgilio|alice|tiscali|"
        r"tin|fastwebnet|email|inwind|aruba|pec|legalmail|protonmail|proton)\.(?:com|it|me|net)\b", re.I), 0),
    "Email": ("avviso", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), 0),
    "Indirizzo IP": ("avviso", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 0),
}
PAROLE_TELEFONO = re.compile(r"(?i)tel|cell|phone|telefono|whatsapp|chiama|contatt|mobile|fax")
EMAIL_INNOCUE = re.compile(r"(?i)@(?:example|esempio|test|localhost|domain|dominio|users\.noreply\.github|noreply|"
                           r"sentry|email\.com$)|^(?:noreply|no-reply|user|nome|name|info@example)")
IP_INNOCUI = re.compile(r"^(?:127\.|0\.0\.0\.0|255\.|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.|1\.1\.1\.1|8\.8\.[48]\.[48])")
VERSIONE = re.compile(r"(?i)version|\bv\d|@\d|==|>=|<=|~=|\^\d")


# ---------------------------------------------------------------- utilità
def _slug(nome: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(nome).stem.strip()).strip("-.").lower()
    return (s or "progetto")[:80]


def _dir(slug: str) -> Path:
    d = (PROGETTI / slug).resolve()
    if d.parent != PROGETTI.resolve():
        raise ValueError("Progetto non valido")
    return d


def _meta_path(slug: str) -> Path:
    return _dir(slug) / "meta.json"


def _leggi_meta(slug: str) -> dict:
    p = _meta_path(slug)
    if not p.exists():
        raise ValueError("Progetto non trovato")
    return json.loads(p.read_text(encoding="utf-8"))


def _scrivi_meta(slug: str, meta: dict) -> dict:
    _meta_path(slug).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _rimuovi(p: Path) -> None:
    def sblocca(fn, path, _exc):          # file di sola lettura (es. oggetti .git)
        os.chmod(path, stat.S_IWRITE)
        fn(path)
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p, onerror=sblocca)
    elif p.exists() or p.is_symlink():
        try:
            p.unlink()
        except PermissionError:
            os.chmod(p, stat.S_IWRITE)
            p.unlink()


def _cmd(args: list[str], cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW)


def _git() -> str:
    g = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"
    if not Path(g).exists() and not shutil.which("git"):
        raise RuntimeError("Git non è installato.")
    return g


def _gh() -> str:
    for c in (shutil.which("gh"), r"C:\Program Files\GitHub CLI\gh.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe")):
        if c and Path(c).exists():
            return c
    raise RuntimeError("GitHub CLI (gh) non è installato.")


def _escluso_file(nome: str) -> bool:
    if nome in ECCEZIONI:
        return False
    return any(fnmatch.fnmatch(nome, pat) for pat in FILE_SENSIBILI)


# ---------------------------------------------------------------- 1. carica lo ZIP
def carica_zip(sorgente: Path, nome_file: str, pulisci: bool) -> dict:
    if not zipfile.is_zipfile(sorgente):
        raise ValueError("Il file non è uno ZIP valido.")
    slug = base = _slug(nome_file)
    i = 2
    while (PROGETTI / slug).exists():
        slug, i = f"{base}-{i}", i + 1
    d = _dir(slug)
    codice = d / "codice"
    codice.mkdir(parents=True)
    try:
        _estrai(sorgente, codice)
    except Exception:
        _rimuovi(d)
        raise
    shutil.move(str(sorgente), d / "originale.zip")
    meta = {"slug": slug, "nome": Path(nome_file).stem, "file_zip": nome_file, "caricato": db.now(),
            "pulisci": pulisci, "repo": None, "pulizia": None, "analisi": None}
    _scrivi_meta(slug, meta)
    db.log("progetti", f"ZIP caricato: {nome_file} → {slug}")
    return prepara(slug, pulisci)


def _estrai(zip_path: Path, dest: Path) -> None:
    dest_r = dest.resolve()
    with zipfile.ZipFile(zip_path) as z:
        info = [i for i in z.infolist() if not i.is_dir()]
        if len(info) > MAX_FILE_NEL_ZIP:
            raise ValueError(f"Lo ZIP contiene troppi file ({len(info)}).")
        if sum(i.file_size for i in info) > MAX_ESTRATTO:
            raise ValueError("Lo ZIP estratto supera i 3 GB.")
        nomi = [i.filename.replace("\\", "/") for i in info]
        # se tutto sta in un'unica cartella, la "apro" (ZIP creato con tasto destro sulla cartella)
        primi = {n.split("/", 1)[0] for n in nomi if not n.startswith("__MACOSX/")}
        radice = next(iter(primi)) + "/" if len(primi) == 1 and all(
            n.startswith(next(iter(primi)) + "/") for n in nomi if not n.startswith("__MACOSX/")) else ""
        for i, nome in zip(info, nomi):
            if nome.startswith("__MACOSX/"):
                continue
            # i link simbolici negli ZIP Unix non vengono creati
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                continue
            rel = nome[len(radice):] if radice and nome.startswith(radice) else nome
            parti = PurePosixPath(rel).parts
            if not parti or rel.startswith("/") or ".." in parti or ":" in parti[0]:
                continue                                  # percorsi pericolosi (zip slip)
            out = (dest / Path(*parti)).resolve()
            if dest_r not in out.parents:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)


# ---------------------------------------------------------------- 2. prepara (pulizia + analisi)
def prepara(slug: str, pulisci: bool | None = None) -> dict:
    meta = _leggi_meta(slug)
    if pulisci is not None:
        meta["pulisci"] = bool(pulisci)
    codice = _dir(slug) / "codice"
    if meta.get("repo"):
        # già pubblicato: la cronologia locale serve per i prossimi caricamenti, non la tocco
        pass
    else:
        _rimuovi(codice / ".git")                      # mai caricare la cronologia dello ZIP
    _scrivi_gitignore(codice)
    if meta["pulisci"]:
        meta["pulizia"] = _pulisci(codice)
    meta["analisi"] = analizza(codice)
    meta["analizzato"] = db.now()
    _scrivi_meta(slug, meta)
    a = meta["analisi"]
    db.log("progetti", f"{slug}: {a['n_file']} file da caricare, {a['n_critici']} critici, "
                       f"{a['n_personali']} dati personali, pulizia={'sì' if meta['pulisci'] else 'no'}")
    return _vista(meta)


def _scrivi_gitignore(codice: Path) -> None:
    gi = codice / ".gitignore"
    esistente = gi.read_text(encoding="utf-8", errors="ignore") if gi.exists() else ""
    righe = set(l.strip() for l in esistente.splitlines())
    mancanti = [l for l in GITIGNORE.splitlines() if l.strip() and not l.startswith("#") and l.strip() not in righe]
    if mancanti:
        sep = "\n" if esistente and not esistente.endswith("\n") else ""
        gi.write_text(esistente + sep + ("\n" if esistente else "") +
                      "# --- Aggiunto da Agente Lavoro (sicurezza) ---\n" + "\n".join(mancanti) + "\n", encoding="utf-8")


def _pulisci(codice: Path) -> dict:
    rimossi: list[str] = []
    sostituiti: list[dict] = []
    env_example: list[str] = []
    for dirpath, dirnames, filenames in os.walk(codice, topdown=True):
        base = Path(dirpath)
        for dn in list(dirnames):
            if dn in CARTELLE_ESCLUSE:
                rimossi.append(str((base / dn).relative_to(codice)).replace("\\", "/") + "/")
                _rimuovi(base / dn)
                dirnames.remove(dn)
        for fn in filenames:
            p = base / fn
            rel = str(p.relative_to(codice)).replace("\\", "/")
            if fn == ".env" or (fn.startswith(".env.") and fn not in ECCEZIONI):
                es = _crea_env_example(p)
                if es:
                    env_example.append(str(es.relative_to(codice)).replace("\\", "/"))
            if _escluso_file(fn) or p.is_symlink():
                rimossi.append(rel)
                _rimuovi(p)
                continue
            try:
                if p.stat().st_size > MAX_FILE_GITHUB:
                    rimossi.append(rel + " (oltre 95 MB)")
                    _rimuovi(p)
                    continue
            except OSError:
                continue
            n = _ripulisci_testo(p)
            if n:
                sostituiti.append({"file": rel, "sostituzioni": n})
    return {"rimossi": rimossi, "sostituiti": sostituiti, "env_example": env_example, "quando": db.now()}


def _crea_env_example(env: Path) -> Path | None:
    """Da .env crea .env.example con le stesse chiavi e i valori vuoti (se non esiste già)."""
    es = env.with_name(".env.example")
    if es.exists():
        return None
    try:
        righe = env.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    out = []
    for r in righe:
        m = re.match(r"^\s*(export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", r)
        out.append(f"{m.group(1) or ''}{m.group(2)}=" if m else (r if r.strip().startswith("#") or not r.strip() else ""))
    if not any(o.strip() for o in out):
        return None
    es.write_text("\n".join(out) + "\n", encoding="utf-8")
    return es


def _leggi_testo(p: Path) -> tuple[str, str] | None:
    if p.suffix.lower() in EST_BINARIE:
        return None
    try:
        if p.stat().st_size > 3_000_000:
            return None
        raw = p.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:8192]:
        return None
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return None


def _trova(testo: str, est: str) -> list[tuple[str, str, int, int, int]]:
    """Restituisce (tipo, gravità, riga, inizio, fine) dei valori da segnalare/sostituire, nel testo intero."""
    out = []
    doc = est in EST_TESTO_DOC
    righe_inizio = [0]
    for m in re.finditer("\n", testo):
        righe_inizio.append(m.end())

    def riga_di(pos: int) -> int:
        lo, hi = 0, len(righe_inizio) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if righe_inizio[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    presi: list[tuple[int, int]] = []
    for tipo, (grav, rx, gruppo) in CONTROLLI.items():
        for m in rx.finditer(testo):
            s, e = (m.start("v"), m.end("v")) if gruppo == "v" else (m.start(), m.end())
            if any(s < pe and e > ps for ps, pe in presi):
                continue                                   # già preso da un controllo più grave
            v = testo[s:e]
            if SEGNAPOSTO in v or v.strip("*") == "RIMOSSO":
                continue                                   # già ripulito
            n_riga = riga_di(s)
            linea = testo[righe_inizio[n_riga - 1]: testo.find("\n", s) if testo.find("\n", s) != -1 else len(testo)]
            if tipo == "Segreto in configurazione" and est not in EST_CONFIG:
                continue
            if tipo == "Password in chiaro" and testo[max(0, m.start() - 6):m.start()].rstrip(" \t'\"").endswith("?"):
                continue                                   # ternario:  x ? "password" : "text"
            if tipo in ("Password in chiaro", "Segreto in configurazione", "Segreto/API key"):
                if re.fullmatch(r"(?i)(?:x+|\*+|changeme|password|secret|your[_-]?\w*|example\w*|placeholder|"
                                r"null|none|true|false|undefined|process\.env.*|os\.environ.*|getenv.*|env\(.*|"
                                r"\$\{?\w+\}?|<.*>|\{\{.*\}\}|" + re.escape(SEGNAPOSTO) + r")", v):
                    continue
            if tipo == "Cellulare" and not (doc or PAROLE_TELEFONO.search(linea)):
                continue
            if tipo in ("Email", "Email personale") and EMAIL_INNOCUE.search(v):
                continue
            if tipo == "Indirizzo IP":
                if IP_INNOCUI.match(v) or any(int(x) > 255 for x in v.split(".")) or VERSIONE.search(linea):
                    continue
            presi.append((s, e))
            out.append((tipo, grav, n_riga, s, e))
    return out


def _ripulisci_testo(p: Path) -> int:
    letto = _leggi_testo(p)
    if not letto:
        return 0
    testo, enc = letto
    trovati = [t for t in _trova(testo, p.suffix.lower()) if t[1] in ("critico", "personale")]
    if not trovati:
        return 0
    nuovo = testo
    for tipo, _g, _r, s, e in sorted(trovati, key=lambda t: t[3], reverse=True):
        if tipo == "Chiave privata":
            fine = nuovo.find("-----END", e)
            fine = nuovo.find("-----", fine + 8) + 5 if fine != -1 else e
            nuovo = nuovo[:s] + SEGNAPOSTO + nuovo[fine:]
        elif tipo == "Email personale":
            nuovo = nuovo[:s] + "email@example.com" + nuovo[e:]
        else:
            nuovo = nuovo[:s] + SEGNAPOSTO + nuovo[e:]
    p.write_text(nuovo, encoding=enc, newline="")
    return len(trovati)


def _maschera(v: str) -> str:
    v = v.strip()
    return (v[:3] + "…" + f" ({len(v)} car.)") if len(v) > 6 else "****"


def _file_da_caricare(codice: Path) -> list[str]:
    """Elenco esatto dei file che git caricherebbe (rispetta .gitignore)."""
    g = _git()
    if not (codice / ".git").exists():
        r = _cmd([g, "init", "-q", "-b", "main"], cwd=codice)
        if r.returncode:
            raise RuntimeError("git init non riuscito: " + r.stderr.strip())
    r = _cmd([g, "-c", "core.quotepath=off", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=codice)
    if r.returncode:
        raise RuntimeError("git ls-files non riuscito: " + r.stderr.strip())
    return sorted(f for f in r.stdout.split("\0") if f)


def analizza(codice: Path) -> dict:
    files = _file_da_caricare(codice)
    risultati, grandi, sensibili = [], [], []
    peso = 0
    for rel in files:
        p = codice / rel
        try:
            dim = p.stat().st_size
        except OSError:
            continue
        peso += dim
        if dim > MAX_FILE_GITHUB:
            grandi.append(rel)
        nome = PurePosixPath(rel).name
        if _escluso_file(nome):
            sensibili.append(rel)
        letto = _leggi_testo(p)
        if not letto:
            continue
        testo, _ = letto
        for tipo, grav, riga, s, e in _trova(testo, p.suffix.lower()):
            risultati.append({"file": rel, "riga": riga, "tipo": tipo, "gravita": grav, "anteprima": _maschera(testo[s:e])})
    critici = [r for r in risultati if r["gravita"] == "critico"]
    personali = [r for r in risultati if r["gravita"] == "personale"]
    blocchi_privato = len(critici) + len(grandi) + len(sensibili)
    return {"n_file": len(files), "peso_mb": round(peso / 1024 ** 2, 2), "file": files[:3000],
            "trovati": risultati[:1500], "n_critici": len(critici), "n_personali": len(personali),
            "n_avvisi": len(risultati) - len(critici) - len(personali), "grandi": grandi, "sensibili": sensibili,
            "ok_privato": blocchi_privato == 0 and len(files) > 0,
            "ok_pubblico": blocchi_privato == 0 and not personali and len(files) > 0}


# ---------------------------------------------------------------- 3. pubblica
def _identita_github() -> dict:
    gh = _gh()
    r = _cmd([gh, "api", "user", "--jq", "{login: .login, id: .id, name: .name}"], timeout=60)
    if r.returncode:
        raise RuntimeError("GitHub non è collegato: apri un terminale e lancia  gh auth login --web")
    u = json.loads(r.stdout)
    # email "noreply" di GitHub: la tua email vera non finisce nei commit pubblici
    u["email"] = f"{u['id']}+{u['login']}@users.noreply.github.com"
    return u


def stato_github() -> dict:
    try:
        u = _identita_github()
        return {"collegato": True, "account": u["login"]}
    except Exception as e:
        return {"collegato": False, "errore": str(e)}


def pubblica(slug: str, nome_repo: str, descrizione: str = "", pubblico: bool = False) -> dict:
    meta = _leggi_meta(slug)
    if meta.get("repo"):
        raise ValueError("Progetto già pubblicato su GitHub. Per una nuova versione carica un nuovo ZIP.")
    nome_repo = re.sub(r"[^A-Za-z0-9._-]+", "-", (nome_repo or meta["nome"]).strip()).strip("-.")[:100]
    if not nome_repo:
        raise ValueError("Nome del repository non valido.")
    codice = _dir(slug) / "codice"
    a = analizza(codice)                                   # ricontrollo sempre subito prima
    meta["analisi"] = a
    _scrivi_meta(slug, meta)
    if not a["ok_privato"]:
        raise ValueError("Il controllo ha trovato segreti, file sensibili o troppo grandi: attiva \"Pulisci\" "
                         "oppure correggi i file e premi \"Rianalizza\".")
    if pubblico and not a["ok_pubblico"]:
        raise ValueError("Ci sono ancora dati personali (telefono, email personali): non lo pubblico come pubblico.")
    u = _identita_github()
    g, gh = _git(), _gh()
    for args in (["config", "user.name", u.get("name") or load_settings()["nome"]], ["config", "user.email", u["email"]],
                 ["config", "core.autocrlf", "true"], ["add", "-A"]):
        r = _cmd([g, *args], cwd=codice)
        if r.returncode:
            raise RuntimeError(f"git {args[0]}: {r.stderr.strip()}")
    r = _cmd([g, "commit", "-q", "-m", f"{meta['nome']}: prima pubblicazione"], cwd=codice)
    if r.returncode and "nothing to commit" not in (r.stdout + r.stderr):
        raise RuntimeError("git commit: " + (r.stderr or r.stdout).strip())
    r = _cmd([gh, "repo", "create", nome_repo, "--private" if not pubblico else "--public", "--source", ".",
              "--remote", "origin", "--push", "--description", (descrizione or meta["nome"])[:300]], cwd=codice, timeout=1800)
    if r.returncode:
        raise RuntimeError("Creazione su GitHub non riuscita: " + (r.stderr or r.stdout).strip()[-600:])
    url = f"https://github.com/{u['login']}/{nome_repo}"
    meta["repo"] = {"nome": nome_repo, "url": url, "pubblico": pubblico, "creato": db.now(), "account": u["login"]}
    _scrivi_meta(slug, meta)
    _aggiungi_a_vetrina(meta["nome"], descrizione, url, pubblico)
    db.log("progetti", f"{slug}: pubblicato su {url} ({'pubblico' if pubblico else 'privato'})")
    return _vista(meta)


def rendi_pubblico(slug: str) -> dict:
    meta = _leggi_meta(slug)
    if not meta.get("repo"):
        raise ValueError("Prima pubblica il progetto come privato.")
    a = analizza(_dir(slug) / "codice")
    meta["analisi"] = a
    _scrivi_meta(slug, meta)
    if not a["ok_pubblico"]:
        raise ValueError("Il controllo trova ancora segreti o dati personali: non lo rendo pubblico.")
    r = _cmd([_gh(), "repo", "edit", f"{meta['repo']['account']}/{meta['repo']['nome']}", "--visibility", "public",
              "--accept-visibility-change-consequences"], timeout=120)
    if r.returncode:
        raise RuntimeError("GitHub: " + (r.stderr or r.stdout).strip()[-400:])
    meta["repo"]["pubblico"] = True
    _scrivi_meta(slug, meta)
    _aggiungi_a_vetrina(meta["nome"], "", meta["repo"]["url"], True)
    db.log("progetti", f"{slug}: reso pubblico {meta['repo']['url']}")
    return _vista(meta)


def _aggiungi_a_vetrina(nome: str, tema: str, url: str, pubblico: bool) -> None:
    """Il link entra nei progetti vetrina (usati da candidature e proposte) solo se il repository è pubblico."""
    if not pubblico:
        return
    s = load_settings()
    vetr = list(s.get("progetti_vetrina") or [])
    if any(p.get("link") == url for p in vetr):
        return
    vetr.append({"nome": nome, "tema": tema or "progetto su GitHub", "link": url})
    save_settings({"progetti_vetrina": vetr})


# ---------------------------------------------------------------- elenco / eliminazione / cartella
def _vista(meta: dict) -> dict:
    a = dict(meta.get("analisi") or {})
    return {**meta, "analisi": a, "cartella": str(_dir(meta["slug"]) / "codice")}


def elenco() -> list[dict]:
    out = []
    for d in sorted(PROGETTI.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if (d / "meta.json").exists():
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            a = m.get("analisi") or {}
            out.append({k: m.get(k) for k in ("slug", "nome", "file_zip", "caricato", "pulisci", "repo", "analizzato")} |
                       {"riassunto": {k: a.get(k) for k in ("n_file", "peso_mb", "n_critici", "n_personali", "n_avvisi",
                                                           "ok_privato", "ok_pubblico")}})
    return out


def dettaglio(slug: str) -> dict:
    return _vista(_leggi_meta(slug))


def elimina(slug: str) -> dict:
    """Elimina solo la copia locale nell'app (mai il repository su GitHub)."""
    d = _dir(slug)
    if not (d / "meta.json").exists():
        raise ValueError("Progetto non trovato")
    _rimuovi(d)
    db.log("progetti", f"{slug}: copia locale eliminata")
    return {"ok": True}


def apri_cartella(slug: str) -> dict:
    d = _dir(slug) / "codice"
    if hasattr(os, "startfile"):
        os.startfile(d)
    return {"ok": True, "cartella": str(d)}


def nuovo_file_temporaneo() -> Path:
    return PROGETTI / f".upload-{datetime.now():%Y%m%d%H%M%S%f}.zip"

"""Percorsi e impostazioni dell'app. Funziona sia da sorgente sia da eseguibile PyInstaller."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "Agente Lavoro"
VERSION = "1.1.0"

if getattr(sys, "frozen", False):          # eseguibile
    BASE = Path(sys.executable).resolve().parent
    RES = Path(getattr(sys, "_MEIPASS", BASE))
else:                                      # sorgente
    BASE = Path(__file__).resolve().parents[2]
    RES = Path(__file__).resolve().parents[1]

# i dati stanno fuori dalla cartella del programma: sopravvivono agli aggiornamenti dell'eseguibile
DATA = (Path.home() / "AgenteLavoro" / "dati") if getattr(sys, "frozen", False) else BASE / "dati"
DB_PATH = DATA / "agente.db"
REPORTS = DATA / "report"
EXPORTS = DATA / "export"
LOGS = DATA / "log"
BROWSER_PROFILE = DATA / "profilo-browser"
SETTINGS_FILE = DATA / "impostazioni.json"
UI_DIR = RES / "ui"

for d in (DATA, REPORTS, EXPORTS, LOGS, BROWSER_PROFILE):
    d.mkdir(parents=True, exist_ok=True)

DEFAULTS: dict = {
    # sicurezza
    "max_pmi_giorno": 15,
    "soglia_annunci": 7,
    "follow_up_giorni": 5,
    "max_solleciti": 2,
    # modello locale
    "ollama_url": "http://127.0.0.1:11434",
    "modello": "llama3.1:8b",
    # profilo
    "nome": "Gaspare Pettinati",
    "sito": "https://gasparepettinati.it",
    "email": "info@gasparepettinati.it",
    "telefono": "",
    "firma": "Gaspare Pettinati — https://gasparepettinati.it",
    "headline": "Sviluppatore full-stack e automazioni AI per PMI — disponibile in remoto",
    "contratti": ["Partita IVA", "Tramite società", "Contratto di lavoro dipendente", "Prestazione occasionale (ritenuta d'acconto)"],
    "competenze": ["Python", "FastAPI", "Node.js", "TypeScript", "React", "PHP", "MySQL", "PostgreSQL",
                   "Docker", "Linux", "LLM / agenti AI", "WhatsApp API", "VoIP / agenti vocali",
                   "CRM e gestionali", "Integrazioni API", "React Native / Expo", "Android/Kotlin"],
    "parole_chiave": ["python", "fastapi", "node", "typescript", "react", "php", "laravel", "full stack",
                      "fullstack", "backend", "ai", "llm", "automation", "api", "integrations", "django"],
    "progetti_vetrina": [
        {"nome": "Leila — receptionist AI per farmacie", "tema": "agente vocale, WhatsApp, SaaS multi-tenant", "link": ""},
        {"nome": "SENTINEL — control room OSINT", "tema": "FastAPI, React, realtime, mappe", "link": ""},
        {"nome": "CRM call center con lead Meta", "tema": "FastAPI, PostgreSQL, produzione", "link": ""},
        {"nome": "EnergyToken", "tema": "agenti AI, TypeScript, blockchain", "link": ""},
    ],
    # posta
    "imap_host": "imap.hostinger.com",
    "imap_port": 993,
    "smtp_host": "smtp.hostinger.com",
    "smtp_port": 465,
    "cartella_bozze": "INBOX.Drafts",
    # CRM del sito
    "crm_url_login": "https://gasparepettinati.it/gestionale/login.php",
    "crm_url_lead": "https://gasparepettinati.it/gestionale/",
    # LinkedIn / Indeed: ricerche usate dai pulsanti e dalla routine
    "ricerche_portali": ["sviluppatore full stack", "python developer", "sviluppatore AI", "backend developer"],
    "portali_auto": False,                 # importa da LinkedIn/Indeed anche alla ricerca automatica del mattino
    # browser
    "browser_canale": "chrome",            # chrome | msedge
    # routine quotidiana (lun-ven): diventa la lista "Cose da fare" di ogni giorno
    "routine": [
        {"ora": "08:30", "titolo": "Leggi il report del mattino", "vista": "home"},
        {"ora": "08:45", "titolo": "Approva o correggi le bozze in attesa", "vista": "bozze"},
        {"ora": "09:00", "titolo": "Rispondi alle email importanti (🔴🟠)", "vista": "posta"},
        {"ora": "09:30", "titolo": "Candidati ai 3 migliori annunci del giorno", "vista": "lavoro"},
        {"ora": "10:30", "titolo": "LinkedIn: 5 messaggi a recruiter/CTO + 1 post o commento", "vista": "lavoro"},
        {"ora": "11:30", "titolo": "PMI: analizza aziende e prepara le proposte (max 15)", "vista": "pmi"},
        {"ora": "14:30", "titolo": "Follow-up dei contatti senza risposta", "vista": "pipeline"},
        {"ora": "15:30", "titolo": "Lavora su vetrine GitHub / sito (30 min)", "vista": ""},
        {"ora": "17:30", "titolo": "Aggiorna la pipeline (stati, prossimi passi, call)", "vista": "pipeline"},
        {"ora": "18:30", "titolo": "Leggi il report della sera e pianifica domani", "vista": "home"},
    ],
    # pianificazione
    "report_mattino": "08:30",
    "report_sera": "18:30",
    "controllo_posta": ["08:15", "18:15"],
    "ricerca_lavoro_ora": "08:00",
}


class SettingsError(RuntimeError):
    pass


def load_settings() -> dict:
    s = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as e:
            raise SettingsError(f"Impossibile leggere le impostazioni da {SETTINGS_FILE}: {e}") from e
        if not isinstance(saved, dict):
            raise SettingsError(f"Il file delle impostazioni {SETTINGS_FILE} deve contenere un oggetto JSON.")
        s.update({k: v for k, v in saved.items() if k in DEFAULTS})
    return s


def save_settings(new: dict) -> dict:
    if not isinstance(new, dict):
        raise SettingsError("Le impostazioni devono essere un oggetto.")
    s = load_settings()
    for k, v in new.items():
        if k in DEFAULTS:
            s[k] = v
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=SETTINGS_FILE.parent, prefix=f".{SETTINGS_FILE.name}.", delete=False
        ) as f:
            temp_path = Path(f.name)
            json.dump(s, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        temp_path.replace(SETTINGS_FILE)
    except (OSError, TypeError, ValueError) as e:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise SettingsError(f"Impossibile salvare le impostazioni in {SETTINGS_FILE}: {e}") from e
    return s

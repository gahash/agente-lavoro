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
    "modello": "qwen3:4b",              # Mac Intel 12 GB, solo CPU: 4B è il massimo fluido
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
    "solo_remoto_o_collaborazione": True,   # annunci: solo smart working dall'Italia o collaborazioni freelance/P.IVA
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
    "browser_modalita": "personale",       # personale = il TUO Chrome + segnalibro | app = Chrome separato comandato dall'app
    # routine quotidiana (lun-ven): diventa la lista "Cose da fare" di ogni giorno
    # 09:00-16:00 riunioni: si lavora prima, negli spazi liberi delle 11:00 e 13:40, e dopo le 16
    "routine": [
        {"ora": "08:15", "titolo": "Leggi il report del mattino e l'agenda", "vista": "home"},
        {"ora": "08:30", "titolo": "Approva o correggi le bozze in attesa", "vista": "bozze"},
        {"ora": "08:45", "titolo": "Rispondi alle email importanti (🔴🟠)", "vista": "posta"},
        {"ora": "11:00", "titolo": "Spazio libero: approva le bozze nuove (partono alle 11:15)", "vista": "bozze"},
        {"ora": "13:40", "titolo": "Spazio libero: risposte e follow-up da approvare (partono alle 13:55)", "vista": "bozze"},
        {"ora": "16:15", "titolo": "Fissa le call con chi ha risposto (pipeline → 📅 Fissa)", "vista": "pipeline"},
        {"ora": "16:30", "titolo": "Candidati ai 3 migliori annunci del giorno", "vista": "lavoro"},
        {"ora": "17:00", "titolo": "LinkedIn: 5 messaggi a recruiter/CTO + 1 post o commento", "vista": "lavoro"},
        {"ora": "17:30", "titolo": "PMI: analizza aziende e prepara le proposte (max 15)", "vista": "pmi"},
        {"ora": "18:00", "titolo": "Aggiorna la pipeline (stati, prossimi passi, call)", "vista": "pipeline"},
        {"ora": "18:30", "titolo": "Leggi il report della sera e pianifica domani", "vista": "home"},
    ],
    # pianificazione
    "report_mattino": "08:10",
    "report_sera": "18:30",
    "controllo_posta": ["07:50", "10:50", "13:30", "18:15"],
    "ricerca_lavoro_ora": "07:30",
    # agenda (gestionale del sito) e invii
    "agenda_api_url": "https://gasparepettinati.it/gestionale/api/agenda.php",
    "link_prenota": "https://gasparepettinati.it/prenota.php",
    "orari_occupato": ["09:00-16:00"],          # riunioni, lun-ven: mai appuntamenti qui
    "spazi_liberi": ["11:00-11:20", "13:40-14:00"],  # finestre libere dentro le riunioni (per te, non per i clienti)
    "slot_clienti": ["16:30", "17:15", "18:00"],     # orari proposti ai clienti
    "durata_appuntamento": 30,
    "promemoria_minuti": 30,                    # se l'appuntamento nel gestionale non ne ha uno
    "agenda_mattino": "07:45",                  # email con l'agenda del giorno
    # caccia automatica (lun-ven): trova aziende/annunci e prepara le bozze da approvare
    "caccia_ore": ["07:00", "15:00"],
    "caccia_citta": ["Bergamo", "Milano"],
    "caccia_settori": ["Farmacie", "Studi medici e dentistici", "Ristoranti", "Hotel e B&B", "Autofficine e concessionari",
                       "Palestre", "Agenzie immobiliari", "Studi professionali (commercialisti, avvocati)",
                       "Centri estetici e parrucchieri"],
    "caccia_analisi": 10,                       # siti analizzati per giro (l'AI locale è lenta: non esagerare)
    "caccia_proposte_giorno": 10,               # proposte PMI scritte al giorno (sempre entro max_pmi_giorno)
    "caccia_candidature_giorno": 3,
    "caccia_interesse_min": 6,                  # su 10, dall'analisi del sito
    "invio_approvate": ["08:55", "11:15", "13:55", "16:20", "18:40"],  # partono solo le bozze già approvate
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

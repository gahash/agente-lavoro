"""Profili LinkedIn e Indeed: testi pronti da copiare e pagine di modifica da aprire nel Chrome di Gaspare.

L'app NON compila e NON salva i profili da sola: i termini di LinkedIn e Indeed vietano l'automazione e
l'account rischierebbe limitazioni. Qui ci sono i testi (coerenti con il CV) e i collegamenti diretti alle
pagine di modifica; Gaspare incolla e salva.
I testi stanno in dati/profili.json e si possono cambiare dall'interfaccia.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..core.config import DATA

FILE = DATA / "profili.json"
CV_DIR = DATA / "cv"

LI = "https://www.linkedin.com/in/me/"
PREDEFINITI = {
    "linkedin": [
        {"campo": "Titolo (headline)", "apri": LI + "edit/intro/", "limite": 220,
         "testo": "AI Engineer & Full-Stack Architect · Agenti vocali e WhatsApp con AI · LLM in produzione (anche "
                  "self-hosted) · CRM e automazioni per aziende · Remoto / P.IVA"},
        {"campo": "Informazioni", "apri": LI, "limite": 2600, "nota": "Nel profilo: matita della sezione Informazioni",
         "testo": "Porto l'intelligenza artificiale dentro i processi reali delle aziende.\n\n"
                  "Negli ultimi anni ho progettato e sviluppato:\n"
                  "• agenti telefonici AI che parlano italiano, qualificano i clienti e passano la chiamata all'operatore quando serve;\n"
                  "• un'assistente vocale per il customer care che legge bollette e pratiche dal CRM e apre ticket in autonomia;\n"
                  "• il controllo qualità delle chiamate con LLM, su migliaia di registrazioni;\n"
                  "• CRM e gestionali su misura: smistamento automatico dei lead da Facebook/Instagram, suite completa per "
                  "venditori di luce e gas, firma elettronica OTP, assistente PEC con AI;\n"
                  "• Leila, una receptionist AI per farmacie (telefono, chat e WhatsApp).\n\n"
                  "Oltre 10 anni di sviluppo full-stack, dalla fatturazione elettronica per PMI alle piattaforme AI per il "
                  "mercato dell'energia. Seguo i progetti dall'analisi alla produzione, con attenzione a sicurezza, GDPR e "
                  "costi, anche con LLM self-hosted quando i dati non devono uscire dall'azienda.\n\n"
                  "Stack: Python, FastAPI, Node.js, TypeScript, React, PHP/Laravel, PostgreSQL, MySQL, Docker, Linux · "
                  "LLM (OpenAI, Gemini, Bedrock, Ollama), Whisper, TTS, VoIP/SIP, WhatsApp API.\n\n"
                  "Disponibile da remoto per ruoli da AI engineer / full-stack e per collaborazioni (P.IVA). "
                  "Schede dei progetti: gasparepettinati.it · github.com/gahash"},
        {"campo": "Esperienza attuale", "apri": LI + "details/experience/", "nota": "Titolo: AI Engineer & Advisor · "
         "Tipo: libero professionista · Inizio: 2025 · Da remoto",
         "testo": "Agenti vocali e conversazionali, sistemi RAG e automazioni per aziende dei settori energia, sanità e "
                  "servizi. Progetti principali: agente vocale per vendite luce e gas, assistente vocale per il customer "
                  "care, controllo qualità delle chiamate con AI, ERPCRM Energy."},
        {"campo": "Competenze", "apri": LI + "details/skills/", "nota": "Aggiungile una alla volta; fissa in alto le prime 5",
         "testo": "Intelligenza artificiale (AI), Large Language Models (LLM), Python, FastAPI, Sviluppo full-stack, "
                  "Agenti AI vocali, Node.js, TypeScript, React, PostgreSQL, Docker, Integrazione API, CRM, "
                  "Automazione dei processi, WhatsApp Business API"},
        {"campo": "Disponibile a lavorare", "apri": LI, "nota": "Nel profilo: \"Disponibile per\" → \"Trovare un nuovo "
         "lavoro\" → visibile solo ai recruiter",
         "testo": "Ruoli: AI Engineer, Full Stack Engineer, Backend Engineer · Luogo: da remoto · "
                  "Tipo: tempo pieno, contratto, freelance"},
    ],
    "indeed": [
        {"campo": "Carica il CV", "apri": "https://profile.indeed.com/", "cv": True,
         "nota": "Premi \"Mostra il CV\" per trovarlo nel Finder e trascinalo nella pagina di Indeed", "testo": ""},
        {"campo": "Titolo", "apri": "https://profile.indeed.com/", "testo": "AI Engineer & Full-Stack Developer"},
        {"campo": "Riepilogo", "apri": "https://profile.indeed.com/",
         "testo": "Porto l'intelligenza artificiale dentro i processi reali delle aziende: agenti telefonici AI in "
                  "italiano, assistenti WhatsApp e chat, controllo qualità delle chiamate con LLM, CRM e gestionali su "
                  "misura. Oltre 10 anni di sviluppo full-stack, dall'analisi alla produzione.\n"
                  "Stack: Python, FastAPI, Node.js, TypeScript, React, PHP/Laravel, PostgreSQL, MySQL, Docker, Linux, "
                  "LLM, Whisper, VoIP/SIP, WhatsApp API."},
        {"campo": "Preferenze di lavoro", "apri": "https://profile.indeed.com/",
         "testo": "Da remoto · AI Engineer, Full Stack Developer, Backend Developer · tempo pieno, contratto, freelance"},
        {"campo": "Competenze", "apri": "https://profile.indeed.com/",
         "testo": "Intelligenza artificiale, LLM, Python, FastAPI, Node.js, TypeScript, React, PostgreSQL, Docker, "
                  "Integrazione API, CRM, Automazione dei processi"},
        {"campo": "Lingue", "apri": "https://profile.indeed.com/", "testo": "Italiano (madrelingua) · Inglese B1 (tecnico)"},
    ],
}


def leggi() -> dict:
    if FILE.exists():
        try:
            return json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return PREDEFINITI


def salva(dati: dict) -> dict:
    FILE.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    return dati


def cv() -> list[str]:
    return sorted(p.name for p in CV_DIR.glob("*.pdf")) if CV_DIR.exists() else []


def mostra_cv() -> dict:
    """Apre la cartella dei CV nel Finder con il primo file selezionato, pronto da trascinare su Indeed."""
    files = sorted(CV_DIR.glob("*.pdf")) if CV_DIR.exists() else []
    if not files:
        return {"ok": False, "errore": f"Nessun CV in {CV_DIR}"}
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(files[0])])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(files[0])])
    return {"ok": True, "cartella": str(CV_DIR), "file": [f.name for f in files]}

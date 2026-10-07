"""Controlli di sicurezza, anti-truffa, anti-spam e GDPR applicati in modo deterministico
(non dipendono dal modello AI)."""
from __future__ import annotations

import re
from datetime import date

from . import db
from .config import load_settings

SEGNALI_TRUFFA = [
    (r"\biban\b", "chiede IBAN"),
    (r"bonifico|ricarica|postepay|western union|moneygram|gift ?card|crypto|bitcoin|usdt", "pagamenti/denaro"),
    (r"corso a pagamento|quota di iscrizione|kit di avvio|investimento iniziale|deposito cauzionale", "richiesta di denaro"),
    (r"telegram|signal", "contatto su app anonima"),
    (r"password|credenziali|codice otp|codice di verifica", "chiede credenziali"),
    (r"documento d'identit|carta d'identit|passaporto|codice fiscale.*prima", "chiede documenti"),
    (r"urgente|entro 24 ?ore|ultimo avviso|account (sospeso|bloccato)", "pressione/urgenza"),
    (r"guadagn\w+ \d+.{0,10}(al giorno|a settimana)|lavora da casa e guadagna", "promessa di guadagno facile"),
    (r"ignora (le |tutte le )?istruzioni|ignore (all |previous )?instructions|system prompt", "tentativo di manipolare l'AI"),
]


def segnali_sospetti(testo: str) -> list[str]:
    t = (testo or "").lower()
    return sorted({motivo for rx, motivo in SEGNALI_TRUFFA if re.search(rx, t)})


def footer_opt_out(fonte: str) -> str:
    return (f"\n\n—\nHo trovato il suo contatto su {fonte or 'fonti pubbliche'}. "
            "Se preferisce non ricevere altri messaggi, risponda \"NO\" e non la ricontatterò.")


def contatti_pmi_oggi() -> int:
    oggi = date.today().isoformat()
    return db.q("SELECT COUNT(*) n FROM registro_contatti WHERE data LIKE ? AND canale LIKE 'email%'",
                (oggi + "%",))[0]["n"]


def pmi_quota_residua() -> int:
    return max(0, int(load_settings()["max_pmi_giorno"]) - contatti_pmi_oggi())


def email_in_opt_out(email: str) -> bool:
    if not email:
        return False
    r = db.q("SELECT 1 FROM aziende WHERE lower(email)=lower(?) AND opt_out=1", (email,))
    return bool(r)


def maschera(testo: str) -> str:
    """Rimuove dal testo password/token/IBAN prima di salvarlo o mostrarlo nei log."""
    t = re.sub(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", "[IBAN]", testo or "")
    t = re.sub(r"(?i)(password|pwd|token|secret)\s*[:=]\s*\S+", r"\1: [nascosto]", t)
    return t

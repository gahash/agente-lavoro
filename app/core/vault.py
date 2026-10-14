"""Credenziali nel Gestore credenziali di Windows (cifrate dal sistema con DPAPI).

Le credenziali le inserisce solo Gaspare dall'interfaccia. Non vengono mai scritte su file,
mai mostrate in chiaro nella UI, mai inviate al modello AI, mai registrate nei log.
"""
from __future__ import annotations

import keyring

SERVICE = "AgenteLavoro-GasparePettinati"

# chiave -> descrizione mostrata nella UI
CAMPI = {
    "imap_user": "Email (utente IMAP/SMTP)",
    "imap_password": "Password email / password per app",
    "gestionale_token": "Token agenda del gestionale (AGENTE_API_TOKEN in config.php)",
    "linkedin_client_id": "LinkedIn · Client ID (app su linkedin.com/developers)",
    "linkedin_client_secret": "LinkedIn · Client Secret",
    "elevenlabs_api_key": "ElevenLabs · chiave API (voce clonata per i video)",
}
SEGRETI = {"imap_password", "gestionale_token", "linkedin_client_secret", "elevenlabs_api_key"}
INTERNE = {"linkedin_token"}          # scritte solo dall'app (mai mostrate né modificabili dalla UI)


_cache: dict[str, str | None] = {}


def set_cred(key: str, value: str) -> None:
    if key not in CAMPI and key not in INTERNE:
        raise KeyError(key)
    _cache.pop(key, None)
    if value:
        keyring.set_password(SERVICE, key, value)
    else:
        try:
            keyring.delete_password(SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


def get_cred(key: str) -> str | None:
    """Letta dal Portachiavi una volta per avvio: le routine ogni 5 minuti non lo interrogano di nuovo."""
    if key not in _cache:
        _cache[key] = keyring.get_password(SERVICE, key)
    return _cache[key]


def stato() -> dict:
    """Solo presenza/assenza (e utente in chiaro), mai le password."""
    out = {}
    for k, label in CAMPI.items():
        v = get_cred(k)
        out[k] = {"label": label, "impostato": bool(v), "segreto": k in SEGRETI,
                  "valore": (v if (v and k not in SEGRETI) else "")}
    return out

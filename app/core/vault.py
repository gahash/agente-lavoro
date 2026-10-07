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
}
SEGRETI = {"imap_password"}


def set_cred(key: str, value: str) -> None:
    if key not in CAMPI:
        raise KeyError(key)
    if value:
        keyring.set_password(SERVICE, key, value)
    else:
        try:
            keyring.delete_password(SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


def get_cred(key: str) -> str | None:
    return keyring.get_password(SERVICE, key)


def stato() -> dict:
    """Solo presenza/assenza (e utente in chiaro), mai le password."""
    out = {}
    for k, label in CAMPI.items():
        v = get_cred(k)
        out[k] = {"label": label, "impostato": bool(v),
                  "valore": (v if (v and k not in SEGRETI) else "")}
    return out

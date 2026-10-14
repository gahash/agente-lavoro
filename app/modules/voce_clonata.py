"""La voce di Gaspare per i video brevi, clonata con ElevenLabs.

Gaspare carica alcuni campioni della sua voce (registrazioni pulite, idealmente 1-3 minuti in totale),
l'app crea la sua "voce" su ElevenLabs e da lì legge i copioni dei video con quella voce. Niente voci
sintetiche generiche: si usa solo la voce clonata di Gaspare. La chiave API sta nel Portachiavi.
Uso commerciale consentito solo con un piano a pagamento di ElevenLabs.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from ..core import db, vault
from ..core.config import DATA, load_settings, save_settings

API = "https://api.elevenlabs.io/v1"
CAMPIONI = DATA / "video" / "campioni"
ESTENSIONI = {".m4a", ".mp3", ".wav", ".webm", ".aac", ".ogg", ".caf"}


def _chiave() -> str:
    k = vault.get_cred("elevenlabs_api_key")
    if not k:
        raise RuntimeError("Inserisci la chiave API di ElevenLabs in Impostazioni → Credenziali")
    return k


def campioni() -> list[Path]:
    return sorted(p for p in CAMPIONI.glob("*") if p.suffix.lower() in ESTENSIONI) if CAMPIONI.exists() else []


def stato() -> dict:
    return {"chiave": bool(vault.get_cred("elevenlabs_api_key")), "voce_id": load_settings().get("elevenlabs_voce_id", ""),
            "campioni": [p.name for p in campioni()]}


def aggiungi_campione(sorgente: Path, nome: str) -> dict:
    ext = Path(nome or "").suffix.lower()
    if ext not in ESTENSIONI:
        sorgente.unlink(missing_ok=True)
        return {"ok": False, "errore": "Formato audio non supportato (usa m4a, mp3 o wav)"}
    CAMPIONI.mkdir(parents=True, exist_ok=True)
    dest = CAMPIONI / f"campione_{len(campioni()) + 1}{ext}"
    sorgente.rename(dest)
    return {"ok": True, "campioni": [p.name for p in campioni()]}


def crea_voce() -> dict:
    """Crea (o ricrea) la voce di Gaspare su ElevenLabs dai campioni caricati."""
    files = campioni()
    if not files:
        raise RuntimeError("Carica almeno un campione della tua voce")
    chiave = _chiave()
    vecchia = load_settings().get("elevenlabs_voce_id")
    r = httpx.post(f"{API}/voices/add", headers={"xi-api-key": chiave}, timeout=180,
                   data={"name": "Gaspare Pettinati", "remove_background_noise": "true",
                         "description": "Voce di Gaspare per i video LinkedIn"},
                   files=[("files", (p.name, p.read_bytes(), "audio/mpeg")) for p in files])
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs ha rifiutato i campioni ({r.status_code}): {r.text[:300]}")
    voce_id = r.json()["voice_id"]
    save_settings({"elevenlabs_voce_id": voce_id})
    if vecchia and vecchia != voce_id:                    # una sola voce attiva
        httpx.delete(f"{API}/voices/{vecchia}", headers={"xi-api-key": chiave}, timeout=30)
    db.log("video", f"Voce clonata creata su ElevenLabs da {len(files)} campioni")
    return {"ok": True, "voce_id": voce_id}


def leggi(testo: str, dest: Path) -> Path:
    """Legge il testo con la voce di Gaspare e salva l'MP3."""
    voce_id = load_settings().get("elevenlabs_voce_id")
    if not voce_id:
        raise RuntimeError("Prima crea la tua voce (Video brevi → La tua voce)")
    r = httpx.post(f"{API}/text-to-speech/{voce_id}", params={"output_format": "mp3_44100_128"}, timeout=180,
                   headers={"xi-api-key": _chiave(), "Accept": "audio/mpeg"},
                   json={"text": testo, "model_id": "eleven_multilingual_v2",
                         "voice_settings": {"stability": 0.5, "similarity_boost": 0.85, "style": 0.2,
                                            "use_speaker_boost": True}})
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs non ha letto il testo ({r.status_code}): {r.text[:300]}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest

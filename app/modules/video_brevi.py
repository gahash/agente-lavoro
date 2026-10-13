"""Video brevi: pillole di 20-30 secondi da pubblicare su LinkedIn.

Ogni video è un copione di poche frasi (una per riga = una scena). Ogni frase compare grande al centro,
animata, ed è letta dalla voce italiana del Mac (comando `say`). LinkedIn fa partire i video senza audio,
quindi il testo a schermo basta da solo. Formato quadrato 1080x1080, MP4 H.264 + AAC.
Il flusso è quello dei post: bozza → approvato → pubblicato da solo il giorno previsto.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

from ..core import db, llm
from ..core.config import DATA, load_settings
from .linkedin_grafica import ACCENTO, CHIARO, FONDO, FONDO2, TENUE, _a_capo, _font

CARTELLA = DATA / "video"
LATO, FPS = 1080, 24
CHIUSURA = "Seguimi per altre pillole di AI applicata."
STATI = ("bozza", "approvato", "pubblicato", "scartato")
SCHEMA = """CREATE TABLE IF NOT EXISTS video_brevi (
  id INTEGER PRIMARY KEY, tema TEXT, copione TEXT, testo TEXT, stato TEXT DEFAULT 'bozza', data_prevista TEXT,
  pubblicato_il TEXT, origine TEXT, creato TEXT, aggiornato TEXT)"""

SERIE_INIZIALE = [
    ("Chatbot o agente AI?",
     "Chatbot o agente AI? La differenza in 20 secondi.\nUn chatbot risponde alle domande.\n"
     "Un agente AI fa anche le cose: prenota, aggiorna il CRM, apre un ticket.\n"
     "Per farlo in sicurezza servono regole scritte nel codice.\nL'AI parla, le regole decidono cosa può fare.",
     "Chatbot o agente AI? La differenza in 20 secondi.\n\n#IntelligenzaArtificiale #AgentiAI #Automazione #PMI"),
    ("Cos'è un LLM",
     "Cos'è un LLM, in parole semplici?\nÈ un modello che ha letto tantissimo testo.\n"
     "Scrive prevedendo la parola successiva, una dopo l'altra.\n"
     "Per questo scrive bene, ma può sbagliare con sicurezza.\nRegola d'oro: in azienda il risultato va controllato.",
     "Cos'è un LLM, spiegato in 20 secondi.\n\n#LLM #IntelligenzaArtificiale #AI #Formazione"),
    ("RAG in 20 secondi",
     "Come far rispondere l'AI con i tuoi documenti?\nPrima cerca nei tuoi file le parti utili.\n"
     "Poi le passa al modello insieme alla domanda.\nCosì risponde con i tuoi dati, non a memoria.\n"
     "E puoi sempre mostrare la fonte della risposta.",
     "RAG: far rispondere l'AI con i documenti dell'azienda, in 20 secondi.\n\n#RAG #LLM #IntelligenzaArtificiale #AI"),
    ("Uscita strutturata",
     "Il trucco per azioni AI affidabili.\nIl modello non risponde in testo libero, ma con campi precisi.\n"
     "Il codice controlla ogni campo prima di agire.\nSe qualcosa non torna, chiede o passa a una persona.",
     "Uscita strutturata: il trucco per un'AI che agisce senza sorprese.\n\n#LLM #SoftwareEngineering #AI #Automazione"),
    ("Human in the loop",
     "Human in the loop: cosa vuol dire?\nL'AI prepara: bozze, risposte, classificazioni.\n"
     "Una persona controlla e decide.\nSi parte così, e si automatizza solo ciò che è sicuro.",
     "Human in the loop, in 15 secondi.\n\n#IntelligenzaArtificiale #Automazione #PMI #AI"),
    ("Cloud o server propri",
     "LLM nel cloud o sui tuoi server?\nCloud: si parte subito e si paga a consumo.\n"
     "Sui tuoi server: i dati non escono dall'azienda.\nLa scelta dipende dai dati che tratti, non dalla moda.",
     "LLM nel cloud o sui propri server? La regola in 15 secondi.\n\n#LLM #Privacy #IntelligenzaArtificiale #PMI"),
    ("Tre regole per un prompt",
     "Tre regole per un prompt che funziona.\nUno: dai il contesto, chi sei e per chi scrivi.\n"
     "Due: chiedi un formato preciso.\nTre: mostra un esempio di risultato giusto.",
     "Tre regole per scrivere un prompt che funziona.\n\n#Prompt #IntelligenzaArtificiale #AI #Produttività"),
    ("Prima di comprare un chatbot",
     "Prima di comprare un chatbot, fai tre domande.\nDove finiscono i dati dei miei clienti?\n"
     "Cosa succede quando l'AI non sa rispondere?\nPosso vedere e correggere le conversazioni?",
     "Tre domande da fare prima di comprare un chatbot.\n\n#Chatbot #IntelligenzaArtificiale #PMI #Privacy"),
]


def init() -> None:
    db.x(SCHEMA)
    if "file" not in {c["name"] for c in db.q("PRAGMA table_info(video_brevi)")}:
        db.x("ALTER TABLE video_brevi ADD COLUMN file TEXT")      # video caricato da Gaspare (non montato dall'app)


def _prossime_date(n: int, da: date | None = None) -> list[str]:
    giorni = load_settings().get("video_giorni", [2, 4])
    out, g = [], (da or date.today()) + timedelta(days=1)
    while len(out) < n:
        if g.weekday() in giorni:
            out.append(g.isoformat())
        g += timedelta(days=1)
    return out


def _prima_data_libera() -> str:
    occupate = {r["data_prevista"] for r in db.q("SELECT data_prevista FROM video_brevi WHERE stato IN ('bozza','approvato')")}
    return next((d for d in _prossime_date(200) if d not in occupate), "")


def crea_serie_iniziale() -> int:
    init()
    if db.q("SELECT 1 FROM video_brevi WHERE origine='serie iniziale'"):
        return 0
    for (tema, copione, testo), giorno in zip(SERIE_INIZIALE, _prossime_date(len(SERIE_INIZIALE))):
        db.x("INSERT INTO video_brevi (tema, copione, testo, data_prevista, origine, creato) VALUES (?,?,?,?,?,?)",
             (tema, copione, testo, giorno, "serie iniziale", db.now()))
    db.log("video", f"Video brevi: {len(SERIE_INIZIALE)} pillole create")
    return len(SERIE_INIZIALE)


def lista(caricati: bool = False) -> list[dict]:
    init()
    return db.q(f"SELECT * FROM video_brevi WHERE stato<>'scartato' AND origine {'=' if caricati else 'IS NOT'} 'caricato' "
                "ORDER BY stato='pubblicato', data_prevista, id")


ESTENSIONI = {".mp4", ".mov", ".m4v"}


def carica(sorgente: Path, nome: str) -> dict:
    """Salva un video registrato da Gaspare (titolo, testo e data si impostano dopo, con aggiorna).
    LinkedIn vuole MP4: i .mov/.m4v si convertono con ffmpeg."""
    import imageio_ffmpeg
    init()
    ext = Path(nome or "").suffix.lower()
    if ext not in ESTENSIONI:
        sorgente.unlink(missing_ok=True)
        return {"ok": False, "errore": "Formato non supportato: carica un video MP4 o MOV"}
    vid = db.x("INSERT INTO video_brevi (tema, copione, testo, data_prevista, origine, creato) VALUES (?,?,?,?,?,?)",
               (Path(nome).stem[:120], "", "", _prima_data_libera(), "caricato", db.now()))
    cartella = CARTELLA / "caricati"
    cartella.mkdir(parents=True, exist_ok=True)
    grezzo = cartella / f"video_{vid}_originale{ext}"
    sorgente.rename(grezzo)
    dest = cartella / f"video_{vid}.mp4"
    if ext == ".mp4":
        grezzo.rename(dest)
    else:
        r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(grezzo),
                            "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dest)],
                           capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            db.x("DELETE FROM video_brevi WHERE id=?", (vid,))
            return {"ok": False, "errore": "Conversione in MP4 non riuscita: " + r.stderr[:300]}
        grezzo.unlink(missing_ok=True)
    if dest.stat().st_size < 75_000:
        db.x("DELETE FROM video_brevi WHERE id=?", (vid,))
        dest.unlink(missing_ok=True)
        return {"ok": False, "errore": "Il video è troppo piccolo per LinkedIn"}
    db.x("UPDATE video_brevi SET file=? WHERE id=?", (str(dest), vid))
    db.log("video", f"Video caricato: {nome}")
    return {"ok": True, "id": vid}


def aggiorna(vid: int, campi: dict) -> dict:
    campi = {k: v for k, v in campi.items() if k in ("tema", "copione", "testo", "stato", "data_prevista")}
    if "stato" in campi and campi["stato"] not in STATI:
        return {"ok": False, "errore": "Stato non valido"}
    if campi.get("stato") == "pubblicato":
        campi["pubblicato_il"] = db.now()
    campi["aggiornato"] = db.now()
    db.x(f"UPDATE video_brevi SET {','.join(f'{k}=?' for k in campi)} WHERE id=?", [*campi.values(), vid])
    if "copione" in campi or "tema" in campi:
        percorso(vid).unlink(missing_ok=True)          # il video si rifà alla prossima richiesta
    return {"ok": True}


def di_oggi() -> list[dict]:
    init()
    return db.q("SELECT id, tema FROM video_brevi WHERE stato='approvato' AND data_prevista<=?", (date.today().isoformat(),))


def genera(tema: str) -> dict:
    """Nuova pillola scritta dal modello AI locale. Finisce in bozza."""
    init()
    s = load_settings()
    sys_ = ("Scrivi il copione di un video LinkedIn di 20 secondi in italiano per un AI engineer: 4 o 5 frasi brevissime "
            "(massimo 14 parole ciascuna), la prima è un gancio o una domanda, le altre spiegano un solo concetto in modo "
            "semplice e concreto. Niente numeri o risultati inventati, niente emoji. Poi una didascalia di una riga con "
            "4 hashtag. Rispondi in JSON: {\"frasi\": [\"...\"], \"didascalia\": \"...\"}")
    d = llm.chat_json(sys_, f"Competenze: {', '.join(s['competenze'])}.\nTEMA: {tema}", max_tokens=400, temperature=0.5)
    frasi = [str(f).strip() for f in d.get("frasi") or [] if str(f).strip()][:6]
    if len(frasi) < 3:
        return {"ok": False, "errore": "Il modello non ha prodotto un copione utilizzabile"}
    vid = db.x("INSERT INTO video_brevi (tema, copione, testo, data_prevista, origine, creato) VALUES (?,?,?,?,?,?)",
               (tema[:120], "\n".join(frasi), str(d.get("didascalia") or frasi[0])[:600], _prima_data_libera(),
                "AI locale", db.now()))
    db.log("video", f"Nuovo video breve scritto: {tema[:80]}")
    return {"ok": True, "id": vid}


# ------------------------------------------------------------------ montaggio

def percorso(vid: int) -> Path:
    return CARTELLA / f"video_{vid}.mp4"


def voci() -> list[str]:
    """Voci italiane disponibili sul Mac (vuoto altrove: il video esce senza audio)."""
    if sys.platform != "darwin":
        return []
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return [r.split(" it_IT")[0].strip() for r in out.splitlines() if " it_IT " in r]


def _audio(frase: str, voce: str, dest: Path) -> float:
    """Legge la frase con la voce del Mac in un WAV mono 22 kHz; restituisce la durata in secondi."""
    subprocess.run(["say", "-v", voce, "-r", "180", "--file-format=WAVE", "--data-format=LEI16@22050",
                    "-o", str(dest), frase], check=True, timeout=60)
    with wave.open(str(dest)) as w:
        return w.getnframes() / w.getframerate()


def _sfondo() -> Image.Image:
    img = Image.new("RGB", (LATO, LATO), FONDO)
    d = ImageDraw.Draw(img)
    for y in range(LATO):
        t = y / LATO
        d.line([(0, y), (LATO, y)], fill=tuple(int(FONDO[i] + (FONDO2[i] - FONDO[i]) * t * 0.9) for i in range(3)))
    s, m = load_settings(), 80
    d.text((m, LATO - 120), s["nome"], font=_font("grassetto", 34), fill=CHIARO)
    sito = s["sito"].replace("https://", "").replace("http://", "")
    fs = _font("grassetto", 28)
    d.text((LATO - m - d.textlength(sito, font=fs), LATO - 112), sito, font=fs, fill=ACCENTO)
    return img


def _scena(base: Image.Image, frase: str, etichetta: str, finale: bool) -> Image.Image:
    """Fotogramma completo di una scena (senza barra di avanzamento)."""
    img = base.copy()
    d = ImageDraw.Draw(img)
    m = 80
    d.rectangle([m, m, m + 100, m + 8], fill=ACCENTO)
    d.text((m, m + 28), etichetta.upper()[:50], font=_font("grassetto", 28), fill=ACCENTO)
    for size in (78, 70, 62, 56, 50):
        f = _font("titolo", size)
        righe = _a_capo(d, frase, f, LATO - 2 * m)
        if len(righe) <= 6:
            break
    alto = len(righe) * int(size * 1.25)
    y = (LATO - alto) // 2
    for r in righe:
        d.text((m, y), r, font=f, fill=ACCENTO if finale else CHIARO)
        y += int(size * 1.25)
    return img


def monta(vid: int, forza: bool = False) -> Path:
    """Crea (o riusa) l'MP4 del video: scene animate + voce italiana."""
    caricato = db.q("SELECT file FROM video_brevi WHERE id=?", (vid,))[0]["file"]
    if caricato:                                      # registrato da Gaspare: si usa così com'è
        return Path(caricato)
    dest = percorso(vid)
    if dest.exists() and not forza:
        return dest
    import imageio_ffmpeg
    v = db.q("SELECT tema, copione FROM video_brevi WHERE id=?", (vid,))[0]
    frasi = [f.strip() for f in (v["copione"] or "").splitlines() if f.strip()] + [CHIUSURA]
    voce = load_settings().get("video_voce", "Alice") if sys.platform == "darwin" else ""
    base = _sfondo()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        durate, wav = [], []
        for i, f in enumerate(frasi):
            if voce:
                p = tmp / f"s{i}.wav"
                durate.append(_audio(f, voce, p) + 0.5)
                wav.append(p)
            else:
                durate.append(min(5.0, 1.4 + 0.055 * len(f)))
        totale = sum(durate)
        audio = None
        if wav:                                       # unisce le frasi con mezzo secondo di pausa
            audio = tmp / "voce.wav"
            with wave.open(str(audio), "wb") as out:
                out.setnchannels(1), out.setsampwidth(2), out.setframerate(22050)
                for p, dur in zip(wav, durate):
                    with wave.open(str(p)) as w:
                        dati = w.readframes(w.getnframes())
                    out.writeframes(dati + b"\0\0" * (int(dur * 22050) - len(dati) // 2))
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{LATO}x{LATO}", "-r", str(FPS), "-i", "-"]
        cmd += (["-i", str(audio), "-c:a", "aac", "-b:a", "128k"] if audio else [])
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-shortest" if audio else "-an", str(dest)]
        dest.parent.mkdir(parents=True, exist_ok=True)
        enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        fatti, n_tot = 0, int(totale * FPS)
        for i, (f, dur) in enumerate(zip(frasi, durate)):
            scena = _scena(base, f, v["tema"] or "Pillola AI", i == len(frasi) - 1)
            entrata = int(0.35 * FPS)
            for k in range(int(dur * FPS)):
                if k < entrata:                       # dissolvenza + leggera salita del testo
                    t = (k + 1) / entrata
                    fot = Image.blend(base, scena.transform(scena.size, Image.AFFINE, (1, 0, 0, 0, 1, -int(30 * (1 - t))),
                                                             fillcolor=FONDO), t)
                else:
                    fot = scena.copy()
                ImageDraw.Draw(fot).rectangle([0, LATO - 10, int(LATO * fatti / max(n_tot, 1)), LATO], fill=ACCENTO)
                enc.stdin.write(fot.tobytes())
                fatti += 1
        enc.stdin.close()
        if enc.wait() != 0:
            dest.unlink(missing_ok=True)
            raise RuntimeError("Montaggio non riuscito: " + enc.stderr.read().decode()[:300])
    db.log("video", f"Video montato: {v['tema']} ({totale:.0f} s)")
    return dest


def mostra(vid: int) -> dict:
    dest = monta(vid)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(dest)])
    return {"ok": True, "file": str(dest)}


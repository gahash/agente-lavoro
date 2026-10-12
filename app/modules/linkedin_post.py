"""Contenuti LinkedIn: calendario editoriale, approvazione e pubblicazione assistita.

I post si preparano qui (scritti a mano, dal modello AI locale o dalla serie iniziale), Gaspare li approva
e il giorno previsto li pubblica con un clic: si apre LinkedIn con il testo già nel riquadro del post e
basta premere "Pubblica". L'app non pubblica da sola (i termini di LinkedIn vietano l'automazione).
"""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote

from ..core import db, llm
from ..core.config import load_settings
from . import linkedin_grafica

LIMITE = 3000                     # caratteri massimi di un post LinkedIn
SCHEMA = """CREATE TABLE IF NOT EXISTS post_linkedin (
  id INTEGER PRIMARY KEY, tema TEXT, testo TEXT, stato TEXT DEFAULT 'bozza', data_prevista TEXT,
  pubblicato_il TEXT, origine TEXT, creato TEXT, aggiornato TEXT)"""
STATI = ("bozza", "approvato", "pubblicato", "scartato")

TEMI = [
    "Un agente vocale AI che parla italiano: cosa ho imparato", "LLM con uscita strutturata: azioni affidabili",
    "Controllo qualità delle chiamate con l'AI", "LLM self-hosted o cloud: privacy e costi",
    "AI per farmacie, studi medici e ristoranti", "Human in the loop: l'AI propone, la persona decide",
    "Lead dalle campagne social: velocità di risposta", "Domande da fare prima di comprare un chatbot",
    "Progetto open source", "Firma elettronica e prove digitali", "Errori comuni nei progetti AI",
    "Automazioni per PMI che fanno risparmiare tempo",
]

SERIE_INIZIALE = [
    ("Presentazione",
     "L'intelligenza artificiale serve quando entra nei processi veri di un'azienda. Non nelle slide.\n\n"
     "Negli ultimi anni ho lavorato proprio lì:\n"
     "→ agenti telefonici che parlano italiano e passano la chiamata a una persona quando serve\n"
     "→ assistenti su WhatsApp e chat che rispondono su orari, disponibilità e pratiche\n"
     "→ valutazione automatica delle telefonate di un call center\n"
     "→ CRM e gestionali su misura, collegati ai sistemi che l'azienda usa già\n\n"
     "Sono uno sviluppatore full-stack da oltre 10 anni. Oggi progetto e realizzo soluzioni AI dall'analisi alla "
     "produzione, con un'attenzione costante a privacy, sicurezza e costi.\n\n"
     "Nei prossimi post racconterò i progetti, gli errori e le scelte tecniche. Cose concrete, niente hype.\n\n"
     "Su quale processo della tua azienda ti piacerebbe vedere l'AI al lavoro?\n\n"
     "#IntelligenzaArtificiale #AI #Automazione #PMI #SviluppoSoftware"),
    ("Agente vocale vendite",
     "Ho costruito un agente telefonico AI per la vendita di luce e gas. La parte difficile non è stata la voce.\n\n"
     "È stata la conformità.\n\n"
     "Nel mercato dell'energia una chiamata commerciale ha regole precise: presentarsi correttamente, spiegare costi e "
     "condizioni senza promettere risparmi certi, rispettare chi non vuole essere ricontattato.\n\n"
     "Un modello linguistico, da solo, non garantisce niente di tutto questo. Così le regole le ho scritte nel codice:\n"
     "• un motore decisionale guida la conversazione passo per passo\n"
     "• le frasi obbligatorie non dipendono dall'improvvisazione del modello\n"
     "• quando la richiesta esce dal copione, la chiamata passa a un operatore\n\n"
     "Riconoscimento vocale e sintesi girano su server propri: le conversazioni restano in azienda.\n\n"
     "Lezione: l'AI parla, ma sono le regole a decidere cosa può dire.\n\n"
     "#AgentiVocali #IntelligenzaArtificiale #Energia #Compliance #VoiceAI"),
    ("Uscita strutturata",
     "\"Il modello ha capito\" non basta quando l'AI deve aprire un ticket in un CRM.\n\n"
     "In \"Sara\", un'assistente vocale per il customer care, l'AI riconosce il cliente, legge bollette e pratiche e può "
     "aprire una segnalazione. Un'azione sbagliata qui è un problema reale.\n\n"
     "La regola che uso: il modello non esegue mai azioni in testo libero.\n"
     "1. Risponde in un formato strutturato (JSON) con campi precisi\n"
     "2. Il codice controlla ogni campo prima di fare qualsiasi cosa\n"
     "3. Se qualcosa non torna, chiede chiarimenti o passa a un operatore\n\n"
     "Così l'AI resta flessibile nel parlare e rigida nell'agire.\n\n"
     "È la differenza tra una demo che stupisce e un sistema che puoi lasciare in produzione.\n\n"
     "#LLM #IntelligenzaArtificiale #CustomerCare #SoftwareEngineering #AI"),
    ("Controllo qualità chiamate",
     "Nei call center il controllo qualità si fa quasi sempre a campione: qualcuno ascolta poche chiamate su tante.\n\n"
     "È lento, costoso e soggettivo. E le chiamate critiche, come i ripensamenti dei clienti, emergono tardi.\n\n"
     "Ho realizzato un sistema che:\n"
     "• trascrive automaticamente le registrazioni\n"
     "• le valuta con un LLM sui criteri di qualità definiti dall'azienda\n"
     "• restituisce punteggio, motivazioni e anomalie da controllare\n"
     "• lavora in coda, anche su migliaia di file, senza bloccare chi lo usa\n\n"
     "Il punto non è sostituire chi fa qualità. È fargli ascoltare le chiamate giuste invece di quelle a caso.\n\n"
     "Nel tuo settore cosa controlleresti per primo, se potessi farlo su tutto e non su un campione?\n\n"
     "#CallCenter #IntelligenzaArtificiale #QualityAssurance #LLM #Automazione"),
    ("Self-hosted o cloud",
     "LLM nel cloud o sui propri server? La risposta dipende dai dati, non dalla moda.\n\n"
     "Nei miei progetti uso entrambe le strade:\n\n"
     "Cloud quando:\n"
     "• i dati non sono sensibili\n"
     "• serve la massima qualità del modello\n"
     "• i volumi sono bassi o variabili\n\n"
     "Self-hosted (ad esempio con Ollama e Whisper) quando:\n"
     "• ci sono dati personali o sanitari e il GDPR va preso sul serio\n"
     "• i volumi sono alti e costanti, e i costi a consumo crescono\n"
     "• l'azienda vuole controllo totale su dove finiscono le informazioni\n\n"
     "Spesso la scelta giusta è ibrida: modello locale per i dati sensibili, cloud per il resto, con un fallback "
     "automatico se un servizio non risponde.\n\n"
     "Voi come avete deciso?\n\n"
     "#LLM #GDPR #Privacy #IntelligenzaArtificiale #SelfHosted"),
    ("AI per le attività locali",
     "In farmacia il telefono squilla mentre al bancone c'è la fila. Chi scegli?\n\n"
     "Da questa domanda è nata Leila, una receptionist AI per farmacie che risponde al telefono, in chat e su WhatsApp:\n"
     "• orari e disponibilità\n"
     "• prenotazione dei servizi\n"
     "• richiesta di ricontatto quando serve il parere del farmacista\n\n"
     "Lo stesso problema lo hanno studi medici, ristoranti, centri estetici, officine: tante domande ripetitive che "
     "tolgono tempo alle persone che dovrebbero occuparsi dei clienti presenti.\n\n"
     "L'AI non sostituisce nessuno: prende le domande semplici e lascia alle persone quelle che contano.\n\n"
     "Quante telefonate al giorno riceve la tua attività per chiedere gli orari?\n\n"
     "#PMI #IntelligenzaArtificiale #Farmacia #WhatsApp #Automazione"),
    ("Human in the loop",
     "La regola più importante che metto nei miei sistemi AI: niente parte senza conferma.\n\n"
     "• L'assistente PEC classifica i messaggi e prepara le risposte, ma le invia solo dopo l'OK di una persona.\n"
     "• Gli agenti che trovano e qualificano contatti preparano bozze, mai invii automatici.\n"
     "• Le azioni sensibili lasciano sempre una traccia: chi, cosa, quando.\n\n"
     "Non è sfiducia nella tecnologia. È progettazione.\n\n"
     "Un'AI che sbaglia una bozza costa trenta secondi di correzione. Un'AI che invia da sola un'email sbagliata a un "
     "cliente costa la fiducia.\n\n"
     "L'automazione migliore è quella che toglie il lavoro ripetitivo e lascia la decisione a chi ne risponde.\n\n"
     "#IntelligenzaArtificiale #HumanInTheLoop #AIResponsabile #Automazione #AI"),
    ("Lead dalle campagne",
     "Un contatto arrivato da una campagna Facebook o Instagram si raffredda in fretta.\n\n"
     "In un'azienda di servizi i lead venivano smistati a mano: distribuzione disomogenea tra gli operatori, "
     "duplicati, richiami dimenticati, esiti non tracciati.\n\n"
     "Il CRM che ho sviluppato, oggi in produzione:\n"
     "• riceve i lead in automatico dalle campagne Meta\n"
     "• elimina i duplicati\n"
     "• li assegna agli operatori secondo regole chiare\n"
     "• ricorda i richiami e registra ogni esito\n\n"
     "Risultato: nessun contatto perso per strada, e finalmente dati affidabili per capire quali campagne funzionano.\n\n"
     "Prima di spendere di più in pubblicità, conviene chiedersi cosa succede al lead dopo il clic.\n\n"
     "#LeadGeneration #CRM #Marketing #Automazione #PMI"),
    ("Prima di comprare un chatbot",
     "Stai pensando a un chatbot per la tua azienda? Prima fatti queste 5 domande.\n\n"
     "1. Quali sono le 10 domande che i clienti fanno più spesso? Se non lo sai, parti da lì.\n"
     "2. Dove arrivano oggi: telefono, WhatsApp, email, sito?\n"
     "3. Quando il bot non sa rispondere, chi interviene e come?\n"
     "4. Che dati personali tratterà, e dove verranno elaborati?\n"
     "5. Come misurerai se funziona? Tempo risparmiato, richieste gestite, clienti soddisfatti.\n\n"
     "Un chatbot che risponde a tutto in modo generico fa più danni di nessun chatbot.\n"
     "Uno addestrato sui contenuti reali dell'azienda, con un passaggio chiaro a una persona, fa risparmiare ore ogni settimana.\n\n"
     "Quale domanda aggiungeresti?\n\n"
     "#Chatbot #IntelligenzaArtificiale #PMI #CustomerService #Digitalizzazione"),
    ("SENTINEL open source",
     "Ho pubblicato SENTINEL, una control room per seguire in tempo reale gli eventi critici nel mondo.\n\n"
     "Terremoti, catastrofi, meteo estremo, minacce informatiche e crisi umanitarie su un'unica mappa, costruita solo "
     "su fonti pubbliche e senza abbonamenti:\n"
     "• raccoglie dieci fonti aperte internazionali\n"
     "• unisce le segnalazioni dello stesso evento\n"
     "• assegna un punteggio di rischio\n"
     "• prepara un briefing con un modello AI che gira in locale\n\n"
     "Stack: FastAPI, React, TypeScript, MapLibre, WebSocket, Docker.\n\n"
     "Utile a chi monitora rischi per lavoro: sicurezza, logistica, protezione civile, assicurazioni.\n\n"
     "Il codice è su GitHub: github.com/gahash/sentinel. Feedback e contributi benvenuti.\n\n"
     "#OpenSource #OSINT #Python #React #IntelligenzaArtificiale"),
    ("Firma elettronica e prove",
     "Far firmare un contratto a distanza è facile. Dimostrare dopo chi l'ha firmato, quando e su quale documento, molto meno.\n\n"
     "Per un operatore dell'energia ho sviluppato una firma elettronica con OTP che raccoglie le prove fin dall'inizio:\n"
     "• codice inviato via SMS ed email\n"
     "• registrazione di dispositivo, indirizzo IP e orario\n"
     "• PDF sigillato con l'impronta (hash) del documento\n"
     "• impronte raggruppate e ancorate in un albero di Merkle: se il documento cambia anche di una virgola, si vede\n\n"
     "Per il cliente è un codice da inserire. Per l'azienda è un fascicolo di prove pronto in caso di contestazione.\n\n"
     "La fiducia digitale si progetta, non si aggiunge alla fine.\n\n"
     "#FirmaElettronica #Sicurezza #Digitalizzazione #Compliance #SviluppoSoftware"),
    ("Errori nei progetti AI",
     "Tre errori che vedo spesso nei progetti di intelligenza artificiale.\n\n"
     "1. Partire dal modello invece che dal problema.\n"
     "\"Usiamo GPT\" non è un obiettivo. \"Rispondere alle richieste di disponibilità in un minuto invece che in un giorno\" sì.\n\n"
     "2. Dimenticare i sistemi che ci sono già.\n"
     "Un assistente che non legge dal CRM o dal gestionale risponde in modo generico. Il valore sta nell'integrazione.\n\n"
     "3. Non prevedere cosa succede quando l'AI sbaglia.\n"
     "Sbaglierà. Serve un passaggio a una persona, un registro delle azioni e un modo semplice per correggere.\n\n"
     "Un buon progetto AI assomiglia più a un buon progetto software che a un esperimento.\n\n"
     "Qual è l'errore più costoso che hai visto?\n\n"
     "#IntelligenzaArtificiale #AI #TrasformazioneDigitale #ProjectManagement #PMI"),
]


def init() -> None:
    db.x(SCHEMA)


def _prossime_date(n: int, da: date | None = None) -> list[str]:
    """Le prossime n date di pubblicazione secondo i giorni impostati (predefinito: martedì e giovedì)."""
    giorni = load_settings().get("linkedin_giorni", [1, 3])
    out, g = [], (da or date.today()) + timedelta(days=1)
    while len(out) < n:
        if g.weekday() in giorni:
            out.append(g.isoformat())
        g += timedelta(days=1)
    return out


def _prima_data_libera() -> str:
    occupate = {r["data_prevista"] for r in db.q("SELECT data_prevista FROM post_linkedin WHERE stato IN ('bozza','approvato')")}
    for d in _prossime_date(200):
        if d not in occupate:
            return d
    return ""


def crea_serie_iniziale() -> int:
    """Inserisce i post iniziali (una volta sola), uno per data del calendario."""
    init()
    if db.q("SELECT 1 FROM post_linkedin WHERE origine='serie iniziale'"):
        return 0
    for (tema, testo), giorno in zip(SERIE_INIZIALE, _prossime_date(len(SERIE_INIZIALE))):
        db.x("INSERT INTO post_linkedin (tema, testo, data_prevista, origine, creato) VALUES (?,?,?,?,?)",
             (tema, testo, giorno, "serie iniziale", db.now()))
    db.log("linkedin", f"Calendario LinkedIn: {len(SERIE_INIZIALE)} post creati")
    return len(SERIE_INIZIALE)


def lista() -> list[dict]:
    init()
    return db.q("SELECT * FROM post_linkedin WHERE stato<>'scartato' ORDER BY stato='pubblicato', data_prevista, id")


def aggiorna(pid: int, campi: dict) -> dict:
    campi = {k: v for k, v in campi.items() if k in ("tema", "testo", "stato", "data_prevista")}
    if "stato" in campi and campi["stato"] not in STATI:
        return {"ok": False, "errore": "Stato non valido"}
    if len(campi.get("testo") or "") > LIMITE:
        return {"ok": False, "errore": f"Il post supera i {LIMITE} caratteri di LinkedIn"}
    if campi.get("stato") == "pubblicato":
        campi["pubblicato_il"] = db.now()
    campi["aggiornato"] = db.now()
    db.x(f"UPDATE post_linkedin SET {','.join(f'{k}=?' for k in campi)} WHERE id=?", [*campi.values(), pid])
    if "testo" in campi or "tema" in campi:
        grafica(pid, rigenera=True)
    return {"ok": True}


def grafica(pid: int, rigenera: bool = False):
    """Percorso dell'immagine del post (la crea se manca o se richiesto)."""
    dest = linkedin_grafica.percorso(pid)
    if rigenera or not dest.exists():
        p = db.q("SELECT testo, tema FROM post_linkedin WHERE id=?", (pid,))[0]
        linkedin_grafica.disegna(p["testo"], p["tema"] or "", dest)
    return dest


def mostra_grafica(pid: int) -> dict:
    """Seleziona l'immagine nel Finder, pronta da trascinare nel post di LinkedIn."""
    import subprocess
    import sys
    dest = grafica(pid)
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(dest)])
    elif sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(dest)])
    return {"ok": True, "file": str(dest)}


def link_pubblica(pid: int) -> str:
    """Apre LinkedIn con il testo del post già inserito nel riquadro di pubblicazione."""
    testo = db.q("SELECT testo FROM post_linkedin WHERE id=?", (pid,))[0]["testo"]
    return "https://www.linkedin.com/feed/?shareActive=true&text=" + quote(testo)


def genera(tema: str) -> dict:
    """Nuovo post scritto dal modello AI locale, partendo dal profilo reale di Gaspare. Finisce in bozza."""
    init()
    s = load_settings()
    prog = "; ".join(f"{p['nome']} ({p['tema']})" for p in s["progetti_vetrina"])
    sys = ("Scrivi un post LinkedIn in italiano per un AI engineer e sviluppatore full-stack italiano. 150-230 parole. "
           "Prima riga: un gancio forte (una frase). Poi paragrafi brevi o un elenco con •. Tono professionale, concreto, "
           "in prima persona, niente hype e niente emoji eccessive. Usa SOLO fatti del profilo: non inventare clienti, "
           "numeri, percentuali o risultati. Chiudi con una domanda ai lettori e 4-5 hashtag su una riga.")
    user = (f"PROFILO: {s['headline']}. Competenze: {', '.join(s['competenze'])}. Progetti reali: {prog}.\n"
            f"Sito: {s['sito']}.\n\nTEMA DEL POST: {tema}")
    testo = llm.chat(sys, user, max_tokens=600, temperature=0.6).strip()
    if not testo:
        return {"ok": False, "errore": "Il modello non ha prodotto testo"}
    pid = db.x("INSERT INTO post_linkedin (tema, testo, data_prevista, origine, creato) VALUES (?,?,?,?,?)",
               (tema[:120], testo[:LIMITE], _prima_data_libera(), "AI locale", db.now()))
    grafica(pid, rigenera=True)
    db.log("linkedin", f"Nuovo post generato: {tema[:80]}")
    return {"ok": True, "id": pid}


def di_oggi() -> list[dict]:
    init()
    return db.q("SELECT id, tema FROM post_linkedin WHERE stato='approvato' AND data_prevista<=?", (date.today().isoformat(),))
